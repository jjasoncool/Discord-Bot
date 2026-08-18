"""member_profile 向量庫存取層（技術介接層）。

職責：定義「如何把 member_profile 各類資料（intro_profile / impression /
auto_personality / preference_fact / signature_tag）讀寫進 pgvector」的介面與實作。
不放業務流程判斷。
（原名 intro_rag_port，因已長成通用的 member_profile store 而更名。）
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import threading
from datetime import datetime, timezone
from typing import Protocol, runtime_checkable

from sys_settings.llm_settings import LLMServiceSettings, load_llm_runtime_config
from sys_settings.pgvector_settings import HYBRID_RETRIEVAL_SETTINGS


try:
    from llama_index.core import Document, VectorStoreIndex
    from llama_index.vector_stores.postgres import PGVectorStore
    from llm.safe_llm_embedding import SafeLLMEmbedding, make_safe_llm_embedding
except Exception:  # pragma: no cover - 依賴可能在部份環境尚未安裝
    Document = None
    VectorStoreIndex = None
    SafeLLMEmbedding = None
    make_safe_llm_embedding = None
    PGVectorStore = None


logger = logging.getLogger("discord_bot")


@runtime_checkable
class MemberProfileStore(Protocol):
    async def index_intro_profile(
        self,
        *,
        guild_id: int,
        channel_id: int,
        author_id: int,
        alias: str,
        wuwa_uid: str,
        bio: str,
        message_to_all: str,
    ) -> None:
        """將自我介紹資料寫入 RAG/向量資料庫。"""

    async def index_impression(
        self,
        *,
        guild_id: int,
        channel_id: int,
        author_id: int,
        target_user_id: int,
        target_alias: str,
        target_habit: str,
        impression: str,
        moderation_metadata: dict[str, str] | None = None,
    ) -> None:
        """將他人印象資料寫入 RAG/向量資料庫。"""

    async def index_auto_personality(
        self,
        *,
        guild_id: int,
        author_id: int,
        alias: str,
        personality: str,
    ) -> None:
        """將 LLM 自動萃取的人格描述寫入 RAG/向量資料庫。"""


class NullMemberProfileStore:
    """預設 no-op 串接，尚未接真正向量庫前使用。"""

    async def index_intro_profile(
        self,
        *,
        guild_id: int,
        channel_id: int,
        author_id: int,
        alias: str,
        wuwa_uid: str,
        bio: str,
        message_to_all: str,
    ) -> None:
        _ = (guild_id, channel_id, author_id, alias, wuwa_uid, bio, message_to_all)

    async def index_impression(
        self,
        *,
        guild_id: int,
        channel_id: int,
        author_id: int,
        target_user_id: int,
        target_alias: str,
        target_habit: str,
        impression: str,
        moderation_metadata: dict[str, str] | None = None,
    ) -> None:
        _ = (
            guild_id,
            channel_id,
            author_id,
            target_user_id,
            target_alias,
            target_habit,
            impression,
            moderation_metadata,
        )

    async def index_auto_personality(
        self,
        *,
        guild_id: int,
        author_id: int,
        alias: str,
        personality: str,
    ) -> None:
        _ = (guild_id, author_id, alias, personality)


class PgVectorMemberProfileStore:
    """以 pgvector 實作的 MemberProfileStore。"""

    def __init__(self) -> None:
        self.settings = LLMServiceSettings()
        source = HYBRID_RETRIEVAL_SETTINGS.get_source("member_profile")
        self.table_name = (
            source.table_name
            if source is not None
            else "discord_member_profiles_index"
        )
        self.embed_dim = HYBRID_RETRIEVAL_SETTINGS.pgvector_embed_dim
        self._embed_model = None
        self._embed_model_name: str | None = None
        self._index = None
        self._schema_ready = False
        # 保護 _get_index / _get_embed_model 的 lazy init 與熱切換，避免多 thread race。
        # 用 RLock 允許 _get_index 持有 lock 時呼叫 _get_embed_model（後者也會 acquire 同一把）。
        self._index_lock = threading.RLock()

    def _get_physical_table_name(self) -> str:
        """LlamaIndex PGVectorStore 的實體表名稱通常為 data_<table_name>。

        消毒（僅允許英數與底線，避免 identifier 注入）已收斂到
        `HybridRetrievalSettings.physical_table()`，四處呼叫端共用同一份。
        """
        return HYBRID_RETRIEVAL_SETTINGS.physical_table(self.table_name)

    def _get_db_conn(self):
        return self.settings.pgvector_connect()

    def _ensure_schema_constraints(self) -> None:
        """建立跨環境可重現的約束（idempotent）。"""
        if self._schema_ready:
            return

        table = self._get_physical_table_name()

        try:
            with self._get_db_conn() as conn:
                with conn.cursor() as cur:
                    # 1) 先去重：同 ref_doc_id 只保留最新一筆
                    cur.execute(
                        f"""
                        WITH ranked AS (
                            SELECT
                                id,
                                metadata_->>'ref_doc_id' AS ref_doc_id,
                                ROW_NUMBER() OVER (
                                    PARTITION BY metadata_->>'ref_doc_id'
                                    ORDER BY id DESC
                                ) AS rn
                            FROM {table}
                            WHERE metadata_->>'ref_doc_id' IS NOT NULL
                        )
                        DELETE FROM {table} t
                        USING ranked r
                        WHERE t.id = r.id
                          AND r.rn > 1;
                        """
                    )

                    # 2) 對 ref_doc_id 建立唯一索引，確保相同業務 key 不重複
                    cur.execute(
                        f"""
                        CREATE UNIQUE INDEX IF NOT EXISTS {self.table_name}_uniq_ref_doc_id
                        ON {table} ((metadata_->>'ref_doc_id'))
                        WHERE metadata_->>'ref_doc_id' IS NOT NULL;
                        """
                    )

                    # 3) 補常用查詢索引（guild + profile_kind + author/target）
                    cur.execute(
                        f"""
                        CREATE INDEX IF NOT EXISTS {self.table_name}_idx_profile_author
                        ON {table} (
                            (metadata_->>'guild_id'),
                            (metadata_->>'profile_kind'),
                            (metadata_->>'author_id')
                        );
                        """
                    )
                    cur.execute(
                        f"""
                        CREATE INDEX IF NOT EXISTS {self.table_name}_idx_profile_target
                        ON {table} (
                            (metadata_->>'guild_id'),
                            (metadata_->>'profile_kind'),
                            (metadata_->>'target_user_id')
                        );
                        """
                    )

            self._schema_ready = True
            logger.info("Intro RAG schema constraints ready: table=%s", table)
        except Exception as exc:
            logger.error("建立 Intro RAG schema constraints 失敗: %s", exc, exc_info=True)

    def _delete_existing_doc(self, *, doc_id: str) -> None:
        """應用層 replace：寫入前刪除相同 ref_doc_id/doc_id 舊資料。"""
        table = self._get_physical_table_name()
        try:
            with self._get_db_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        f"""
                        DELETE FROM {table}
                        WHERE metadata_->>'ref_doc_id' = %s
                           OR metadata_->>'doc_id' = %s
                           OR metadata_->>'document_id' = %s;
                        """,
                        (doc_id, doc_id, doc_id),
                    )
        except Exception as exc:
            logger.error("刪除舊 Intro RAG 文件失敗: doc_id=%s err=%s", doc_id, exc, exc_info=True)

    def _dependencies_ready(self) -> bool:
        if any(dep is None for dep in (Document, VectorStoreIndex, SafeLLMEmbedding, PGVectorStore)):
            logger.warning("Intro RAG 依賴未就緒，略過 pgvector 寫入。")
            return False
        return True

    def _get_embed_model(self):
        runtime_config = load_llm_runtime_config(self.settings.llm_runtime_model_path)
        embed_model_name = runtime_config.embed_model
        # Fast path：model 沒變直接返回，不進 lock
        if self._embed_model is not None and self._embed_model_name == embed_model_name:
            return self._embed_model

        # 首次 init 或 runtime 熱切換 → 進 lock 保護 mutation
        # （self._embed_model / self._embed_model_name / self._index 三個欄位）
        with self._index_lock:
            if self._embed_model is not None and self._embed_model_name == embed_model_name:
                return self._embed_model
            self._embed_model = make_safe_llm_embedding(
                settings=self.settings,
                runtime_config=runtime_config,
            )
            self._embed_model_name = embed_model_name
            self._index = None
            return self._embed_model

    def _get_index(self):
        # Fast path：已 init 過直接返回，不進 lock
        if self._index is not None:
            return self._index

        # 首次 init 由 lock 保護；double-checked 避免 lock 釋放後重複建立
        with self._index_lock:
            if self._index is not None:
                return self._index

            embed_model = self._get_embed_model()
            vector_store = PGVectorStore.from_params(
                database=self.settings.pgvector_db,
                host=self.settings.pgvector_host,
                password=self.settings.pgvector_password,
                port=self.settings.pgvector_port,
                user=self.settings.pgvector_user,
                table_name=self.table_name,
                embed_dim=self.embed_dim,
                hybrid_search=True,
            )
            self._index = VectorStoreIndex.from_vector_store(
                vector_store=vector_store,
                embed_model=embed_model,
            )
            self._ensure_schema_constraints()
            return self._index

    def _insert(self, *, doc_id: str, text: str, metadata: dict[str, str]) -> None:
        index = self._get_index()
        # 應用層 replace：同 business key 重送時更新為新版本
        self._delete_existing_doc(doc_id=doc_id)
        doc = Document(
            text=text,
            doc_id=doc_id,
            metadata=metadata,
        )
        index.insert(doc)

    async def _ainsert(self, *, doc_id: str, text: str, metadata: dict[str, str]) -> None:
        """把同步 _insert 丟到 executor thread，避免阻塞 event loop。

        _insert 內含 embedding HTTP + pgvector DELETE/INSERT 皆為同步 IO，
        直接 await 會讓整個 event loop 停住（影響語音 heartbeat / 其他 callback）。
        """
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            lambda: self._insert(doc_id=doc_id, text=text, metadata=metadata),
        )

    async def index_intro_profile(
        self,
        *,
        guild_id: int,
        channel_id: int,
        author_id: int,
        alias: str,
        wuwa_uid: str,
        bio: str,
        message_to_all: str,
    ) -> None:
        if not self._dependencies_ready():
            return

        try:
            text = (
                f"[Intro Profile]\n"
                f"alias: {alias or '-'}\n"
                f"wuwa_uid: {wuwa_uid or '-'}\n"
                f"bio: {bio or '-'}\n"
                f"message_to_all: {message_to_all or '-'}"
            )
            metadata = {
                "doc_type": "member_profile",
                "profile_kind": "intro_profile",
                "guild_id": str(guild_id),
                "channel_id": str(channel_id),
                "author_id": str(author_id),
                "alias": alias or "",
                "wuwa_uid": wuwa_uid or "",
            }
            doc_id = f"intro_profile:{guild_id}:{author_id}"
            await self._ainsert(doc_id=doc_id, text=text, metadata=metadata)
        except Exception as exc:
            logger.error("寫入 intro profile 至 pgvector 失敗: %s", exc, exc_info=True)

    async def index_impression(
        self,
        *,
        guild_id: int,
        channel_id: int,
        author_id: int,
        target_user_id: int,
        target_alias: str,
        target_habit: str,
        impression: str,
        moderation_metadata: dict[str, str] | None = None,
    ) -> None:
        if not self._dependencies_ready():
            return

        try:
            text = (
                f"[Member Impression]\n"
                f"target_user_id: {target_user_id}\n"
                f"target_alias: {target_alias or '-'}\n"
                f"target_habit: {target_habit or '-'}\n"
                f"impression: {impression or '-'}"
            )
            metadata = {
                "doc_type": "member_profile",
                "profile_kind": "impression",
                "guild_id": str(guild_id),
                "channel_id": str(channel_id),
                "author_id": str(author_id),
                "target_user_id": str(target_user_id),
                "target_alias": target_alias or "",
            }
            if moderation_metadata:
                for key, value in moderation_metadata.items():
                    if value is None:
                        continue
                    metadata[str(key)] = str(value)
            doc_id = f"impression:{guild_id}:{author_id}:{target_user_id}"
            await self._ainsert(doc_id=doc_id, text=text, metadata=metadata)
        except Exception as exc:
            logger.error("寫入 member impression 至 pgvector 失敗: %s", exc, exc_info=True)

    async def index_auto_personality(
        self,
        *,
        guild_id: int,
        author_id: int,
        alias: str,
        personality: str,
    ) -> None:
        if not self._dependencies_ready():
            return

        try:
            text = (
                f"[Auto Personality]\n"
                f"alias: {alias or '-'}\n"
                f"personality: {personality or '-'}"
            )
            metadata = {
                "doc_type": "member_profile",
                "profile_kind": "auto_personality",
                "guild_id": str(guild_id),
                "author_id": str(author_id),
                "alias": alias or "",
                # 用 UTC ISO 8601；排程啟動補跑判斷會 query 這個欄位
                "last_extracted_at": datetime.now(timezone.utc).isoformat(),
            }
            doc_id = f"auto_personality:{guild_id}:{author_id}"
            await self._ainsert(doc_id=doc_id, text=text, metadata=metadata)
        except Exception as exc:
            logger.error("寫入 auto personality 至 pgvector 失敗: %s", exc, exc_info=True)

    # ── 功能二記憶：使用者偏好事實 preference_fact（Phase C-1 儲存層）─────────
    # 與 intro/impression/auto_personality 同表，用 profile_kind='preference_fact' 區分。
    # 不同於前三者「一人一卡」，preference_fact 是「一人多筆原子事實」，doc_id 含 fact_key 雜湊。

    @staticmethod
    def _preference_doc_id(guild_id: int, author_id: int, fact_key: str) -> str:
        """同一件偏好（同 fact_key）→ 同 doc_id → app 層 replace，不重複堆積。"""
        key_hash = hashlib.sha1(
            f"{guild_id}:{author_id}:{fact_key}".encode("utf-8")
        ).hexdigest()[:12]
        return f"preference_fact:{guild_id}:{author_id}:{key_hash}"

    async def index_preference_fact(
        self,
        *,
        guild_id: int,
        author_id: int,
        alias: str,
        fact: str,
        fact_key: str,
        category: str,
        confidence: float,
        status: str,
        mention_count: int,
        first_seen: str,
        last_seen: str,
    ) -> str | None:
        """寫入/更新一筆使用者偏好事實。回傳 doc_id（失敗回 None）。

        status: "tentative"（首見、不公開引用）| "trusted"（≥2 次或 /remember，才會被召回）。
        同 fact_key 重送＝replace（呼叫端先讀舊 mention_count 再 +1 帶進來）。
        """
        if not self._dependencies_ready():
            return None
        try:
            doc_id = self._preference_doc_id(guild_id, author_id, fact_key)
            text = (
                f"[Preference Fact]\n"
                f"alias: {alias or '-'}\n"
                f"category: {category or '-'}\n"
                f"fact: {fact or '-'}"
            )
            metadata = {
                "doc_type": "member_profile",
                "profile_kind": "preference_fact",
                "guild_id": str(guild_id),
                "author_id": str(author_id),
                "alias": alias or "",
                "doc_id": doc_id,
                "fact": fact or "",
                "fact_key": fact_key or "",
                "category": category or "",
                "confidence": f"{float(confidence):.2f}",
                "status": status or "tentative",
                "mention_count": str(int(mention_count)),
                "first_seen": first_seen or "",
                "last_seen": last_seen or "",
            }
            await self._ainsert(doc_id=doc_id, text=text, metadata=metadata)
            return doc_id
        except Exception as exc:
            logger.error("寫入 preference_fact 至 pgvector 失敗: %s", exc, exc_info=True)
            return None

    def list_preference_facts(
        self,
        *,
        guild_id: int,
        author_id: int | None = None,
        only_trusted: bool = False,
    ) -> list[dict[str, str]]:
        """直接 SQL 撈 preference_fact（給升等比對 / 召回 / 管理）。同步，呼叫端自行包 executor。"""
        table = self._get_physical_table_name()
        conditions = [
            "metadata_->>'profile_kind' = 'preference_fact'",
            "metadata_->>'guild_id' = %s",
        ]
        params: list[str] = [str(guild_id)]
        if author_id is not None:
            conditions.append("metadata_->>'author_id' = %s")
            params.append(str(author_id))
        if only_trusted:
            conditions.append("metadata_->>'status' = 'trusted'")
        where = " AND ".join(conditions)
        rows: list[dict[str, str]] = []
        try:
            with self._get_db_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        f"""
                        SELECT metadata_->>'doc_id', metadata_->>'author_id',
                               metadata_->>'alias', metadata_->>'fact',
                               metadata_->>'fact_key', metadata_->>'category',
                               metadata_->>'confidence', metadata_->>'status',
                               metadata_->>'mention_count', metadata_->>'first_seen',
                               metadata_->>'last_seen'
                        FROM {table}
                        WHERE {where};
                        """,
                        params,
                    )
                    cols = (
                        "doc_id", "author_id", "alias", "fact", "fact_key",
                        "category", "confidence", "status", "mention_count",
                        "first_seen", "last_seen",
                    )
                    for record in cur.fetchall():
                        rows.append({col: (record[i] or "") for i, col in enumerate(cols)})
        except Exception as exc:
            logger.error("查詢 preference_fact 失敗: %s", exc, exc_info=True)
        return rows

    def delete_preference_fact(self, *, doc_id: str) -> None:
        """刪除一筆 preference_fact（管理用：刪錯 / 禁記）。同步，呼叫端自行包 executor。"""
        self._delete_existing_doc(doc_id=doc_id)

    def find_user_ids_by_alias(self, *, guild_id: int, aliases: list[str]) -> list[str]:
        """別名字串 → 該成員 user_id（給 ambient callback 解析「在講誰」）。同步；呼叫端包 executor。

        以本人 alias（intro_profile / auto_personality，author_id=本人）＋ impression 的
        target_alias（target_user_id=被描述者）做 substring ILIKE，回 distinct user_id。
        回空＝沒對到；多筆由呼叫端判斷（保守：非唯一就不採用）。失敗回空（不影響主流程）。
        """
        if not aliases:
            return []
        table = self._get_physical_table_name()
        like_values = [f"%{a}%" for a in aliases]
        ph = ",".join(["%s"] * len(like_values))
        uids: list[str] = []
        try:
            with self._get_db_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        f"""
                        SELECT DISTINCT uid FROM (
                          SELECT metadata_->>'author_id' AS uid FROM {table}
                          WHERE metadata_->>'doc_type'='member_profile'
                            AND metadata_->>'guild_id'=%s
                            AND metadata_->>'profile_kind' IN ('intro_profile','auto_personality')
                            AND metadata_->>'alias' ILIKE ANY(ARRAY[{ph}])
                          UNION
                          SELECT metadata_->>'target_user_id' AS uid FROM {table}
                          WHERE metadata_->>'doc_type'='member_profile'
                            AND metadata_->>'guild_id'=%s
                            AND metadata_->>'profile_kind'='impression'
                            AND metadata_->>'target_alias' ILIKE ANY(ARRAY[{ph}])
                        ) t WHERE uid IS NOT NULL AND uid <> '';
                        """,
                        [str(guild_id), *like_values, str(guild_id), *like_values],
                    )
                    uids = [r[0] for r in cur.fetchall() if r[0]]
        except Exception as exc:
            logger.error("find_user_ids_by_alias 失敗: %s", exc, exc_info=True)
        return uids

    # ── 功能二記憶：招牌梗 signature_tag（持久印象層；corroboration + 慢衰減）─────────
    # 與 preference_fact 同表同形（profile_kind='signature_tag'），但治理更硬：歸屬必須是程式碼
    # 驗證過的真實 sender、spicy 非對稱門檻、本人可 opt-out。與 preference_fact 平行維護（刻意
    # 不共用 SQL：本層 list 多了 author_ids=ANY 批撈與多個治理欄，硬合併反而易漂移）。

    @staticmethod
    def _signature_tag_doc_id(guild_id: int, author_id: int, tag_key: str) -> str:
        """同一個梗（同 tag_key）→ 同 doc_id → app 層 replace。author_id 必為驗證過的真實梗本人。"""
        key_hash = hashlib.sha1(
            f"{guild_id}:{author_id}:{tag_key}".encode("utf-8")
        ).hexdigest()[:12]
        return f"signature_tag:{guild_id}:{author_id}:{key_hash}"

    # 結構符號黑名單：半形/全形括號、引號、分隔、標點、控制字元——一律剝除，避免在 prompt 內偽造結構。
    # 〈-〟 蓋 〈〉《》「」『』【】〔〕…；＀-／、：-＠、［-｀、｛-･ 蓋全形標點/括號。
    _STRUCT_CHARS_RE = re.compile(
        r"[<>\[\]{}()\n\r\t`|/\\:;，。、；：！？!?～~　"
        r"〈-〟＀-／：-＠［-｀｛-･]"
    )
    # 指令類關鍵詞（容忍夾雜空白；ignore previous 不論有無空白都吃）。
    _INSTR_RE = re.compile(
        r"(?i)system|assistant|ignore\s*previous|instruction|prompt|系\s*統\s*提\s*示|指\s*令|忽\s*略\s*前",
    )

    @classmethod
    def _normalize_tag_text(cls, text: str) -> str:
        """招牌梗正文硬約束：剝離偽結構符號／換行／指令類關鍵詞、≤20 字。短結構化梗本身抗注入。"""
        if not text:
            return ""
        t = cls._STRUCT_CHARS_RE.sub("", text.strip())
        t = cls._INSTR_RE.sub("", t)
        return re.sub(r"\s+", " ", t).strip()[:20]

    async def index_signature_tag(
        self,
        *,
        guild_id: int,
        author_id: int,
        alias: str,
        tag: str,
        tag_key: str,
        tag_kind: str,
        sensitivity: str,
        self_claimed: str,
        confidence: float,
        status: str,
        mention_count: int,
        first_seen: str,
        last_seen: str,
        last_corroborated_day: str = "",
        suppressed: str = "0",
        blacklisted: str = "0",
    ) -> str | None:
        """寫入/更新一筆招牌梗。回傳 doc_id（失敗回 None）。同 tag_key 重送＝replace。

        sensitivity: 'low'（外號/口頭禪）| 'spicy'（身材/調情玩笑，非對稱高門檻+短半衰期）。
        去重以 last_corroborated_day（UTC 日）為準：同一天再被提到不重複計 mention_count。
        """
        if not self._dependencies_ready():
            return None
        try:
            doc_id = self._signature_tag_doc_id(guild_id, author_id, tag_key)
            safe_tag = self._normalize_tag_text(tag)
            text = (
                f"[Signature Tag]\n"
                f"alias: {alias or '-'}\n"
                f"kind: {tag_kind or '-'}\n"
                f"tag: {safe_tag or '-'}"
            )
            metadata = {
                "doc_type": "member_profile",
                "profile_kind": "signature_tag",
                "guild_id": str(guild_id),
                "author_id": str(author_id),
                "alias": alias or "",
                "doc_id": doc_id,
                "tag": safe_tag or "",
                "tag_key": tag_key or "",
                "tag_kind": tag_kind or "",
                "sensitivity": sensitivity or "low",
                "self_claimed": "1" if str(self_claimed) in ("1", "True", "true") else "0",
                "suppressed": str(suppressed),
                "blacklisted": str(blacklisted),
                "confidence": f"{float(confidence):.2f}",
                "status": status or "tentative",
                "mention_count": str(int(mention_count)),
                "first_seen": first_seen or "",
                "last_seen": last_seen or "",
                "last_corroborated_day": last_corroborated_day or "",
            }
            await self._ainsert(doc_id=doc_id, text=text, metadata=metadata)
            return doc_id
        except Exception as exc:
            logger.error("寫入 signature_tag 至 pgvector 失敗: %s", exc, exc_info=True)
            return None

    def list_signature_tags(
        self,
        *,
        guild_id: int,
        author_id: int | None = None,
        author_ids: list[int] | None = None,
        only_trusted: bool = False,
    ) -> list[dict[str, str]]:
        """撈 signature_tag（升等比對 / 召回 / 衰減 sweep）。支援 author_ids 批撈（=ANY，修 N+1）。"""
        table = self._get_physical_table_name()
        conditions = [
            "metadata_->>'profile_kind' = 'signature_tag'",
            "metadata_->>'guild_id' = %s",
        ]
        params: list = [str(guild_id)]
        if author_ids:
            conditions.append("metadata_->>'author_id' = ANY(%s)")
            params.append([str(a) for a in author_ids])
        elif author_id is not None:
            conditions.append("metadata_->>'author_id' = %s")
            params.append(str(author_id))
        if only_trusted:
            conditions.append("metadata_->>'status' = 'trusted'")
        where = " AND ".join(conditions)
        cols = (
            "doc_id", "author_id", "alias", "tag", "tag_key", "tag_kind",
            "sensitivity", "self_claimed", "suppressed", "blacklisted",
            "confidence", "status", "mention_count", "first_seen", "last_seen",
            "last_corroborated_day",
        )
        select_cols = ", ".join(f"metadata_->>'{c}'" for c in cols)
        rows: list[dict[str, str]] = []
        try:
            with self._get_db_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(f"SELECT {select_cols} FROM {table} WHERE {where};", params)
                    for record in cur.fetchall():
                        rows.append({c: (record[i] or "") for i, c in enumerate(cols)})
        except Exception as exc:
            logger.error("查詢 signature_tag 失敗: %s", exc, exc_info=True)
        return rows

    def delete_signature_tag(self, *, doc_id: str) -> None:
        """刪除一筆 signature_tag（封存 / 本人 forget）。同步，呼叫端自行包 executor。"""
        self._delete_existing_doc(doc_id=doc_id)

    def sweep_signature_tags(
        self,
        *,
        guild_id: int,
        halflife_low_days: float,
        halflife_spicy_days: float,
        demote_floor: float,
        archive_floor: float,
    ) -> dict[str, int]:
        """招牌梗衰減 sweep（單一 transaction、純 metadata UPDATE/DELETE、**不重嵌入**）。

        effective = mention_count × 0.5^(沉默天數/半衰期)，spicy 用較短半衰期、淡得快：
          - effective < archive_floor      → 直接刪（GC 死梗）
          - trusted 且 < demote_floor       → 降回 tentative（不再被 only_trusted 召回）
        suppressed / blacklisted 一律不動（屬本人治理紀錄，GC 不得碰；blacklisted 留作禁學墓碑）。
        回傳 {scanned, demoted, archived}。
        """
        from datetime import datetime, timezone

        rows = self.list_signature_tags(guild_id=guild_id)
        if not rows:
            return {"scanned": 0, "demoted": 0, "archived": 0}
        now = datetime.now(timezone.utc)
        demote_ids: list[str] = []
        archive_ids: list[str] = []
        for r in rows:
            if r.get("suppressed") == "1" or r.get("blacklisted") == "1":
                continue
            try:
                count = int(r.get("mention_count", "1") or "1")
            except ValueError:
                count = 1
            days = 0.0
            try:
                last_dt = datetime.fromisoformat(r.get("last_seen", ""))
                days = max(0.0, (now - last_dt).total_seconds() / 86400.0)
            except Exception:
                pass
            halflife = (
                halflife_spicy_days if r.get("sensitivity") == "spicy" else halflife_low_days
            )
            eff = count * (0.5 ** (days / max(halflife, 1.0)))
            doc_id = r.get("doc_id") or ""
            if not doc_id:
                continue
            if eff < archive_floor:
                archive_ids.append(doc_id)
            elif r.get("status") == "trusted" and eff < demote_floor:
                demote_ids.append(doc_id)
        if not demote_ids and not archive_ids:
            return {"scanned": len(rows), "demoted": 0, "archived": 0}
        table = self._get_physical_table_name()
        try:
            with self._get_db_conn() as conn:
                with conn.cursor() as cur:
                    if archive_ids:
                        cur.execute(
                            f"DELETE FROM {table} WHERE metadata_->>'doc_id' = ANY(%s);",
                            (archive_ids,),
                        )
                    if demote_ids:
                        cur.execute(
                            f"""
                            UPDATE {table}
                            SET metadata_ = jsonb_set(
                                metadata_::jsonb, '{{status}}', '"tentative"'::jsonb
                            )::json
                            WHERE metadata_->>'doc_id' = ANY(%s);
                            """,
                            (demote_ids,),
                        )
        except Exception as exc:
            logger.error("signature_tag sweep 失敗 guild=%s: %s", guild_id, exc, exc_info=True)
            return {"scanned": len(rows), "demoted": 0, "archived": 0}
        return {"scanned": len(rows), "demoted": len(demote_ids), "archived": len(archive_ids)}

    def set_signature_tag_flags(
        self,
        *,
        doc_id: str,
        suppressed: bool | None = None,
        blacklisted: bool | None = None,
    ) -> bool:
        """本人 opt-out：設 suppressed/blacklisted 旗標（純 metadata UPDATE、不重嵌入）。

        suppressed=軟性收回（不再 callback，仍留庫）；blacklisted=永久封鎖（連同 suppress，且禁止
        再學）。回傳是否有更新到列（doc_id 不存在 → False）。
        """
        import json as _json

        updates: dict[str, str] = {}
        if suppressed is not None:
            updates["suppressed"] = "1" if suppressed else "0"
        if blacklisted is not None:
            updates["blacklisted"] = "1" if blacklisted else "0"
        if not updates:
            return False
        expr = "metadata_::jsonb"
        params: list = []
        for k, v in updates.items():
            expr = f"jsonb_set({expr}, '{{{k}}}', %s::jsonb)"
            params.append(_json.dumps(v))  # → '"1"'，cast 成 jsonb 字串值
        params.append(doc_id)
        table = self._get_physical_table_name()
        try:
            with self._get_db_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        f"UPDATE {table} SET metadata_ = ({expr})::json "
                        f"WHERE metadata_->>'doc_id' = %s;",
                        params,
                    )
                    return cur.rowcount > 0
        except Exception as exc:
            logger.error("set_signature_tag_flags 失敗 doc_id=%s: %s", doc_id, exc, exc_info=True)
            return False


# --- module-level singleton ---
# 為什麼：原本每個呼叫端 (`personality_extractor`, `management_commands`)
# 都 new 一個 PgVectorMemberProfileStore，每個 instance 有自己的 _index / embed_model，
# 每次呼叫 index.insert 都會開新的 HTTP 連線打 Ollama；
# 大量請求下會塞爆 Windows ephemeral port 池（TIME_WAIT socket 累積）。
# 改為全 process 共用單一 instance，內部 index 物件被 LlamaIndex 的 HTTP client 重用。
_member_profile_store_singleton: PgVectorMemberProfileStore | None = None
_singleton_lock = threading.Lock()


def get_member_profile_store() -> PgVectorMemberProfileStore:
    """取得 PgVectorMemberProfileStore 單例。"""
    global _member_profile_store_singleton
    if _member_profile_store_singleton is not None:
        return _member_profile_store_singleton
    with _singleton_lock:
        if _member_profile_store_singleton is None:
            _member_profile_store_singleton = PgVectorMemberProfileStore()
        return _member_profile_store_singleton
