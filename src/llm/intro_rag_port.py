"""Intro RAG 串接層（技術介接層）。

職責：定義「如何把資料送進 RAG/向量庫」的介面。
不放業務流程判斷。
"""
from __future__ import annotations

import asyncio
import logging
import re
import threading
from datetime import datetime, timezone
from typing import Protocol, runtime_checkable

from sys_settings.llm_settings import LLMServiceSettings, load_llm_runtime_config
from sys_settings.pgvector_settings import HYBRID_RETRIEVAL_SETTINGS

import psycopg2

try:
    from llama_index.core import Document, VectorStoreIndex
    from llama_index.vector_stores.postgres import PGVectorStore
    from llm.safe_ollama_embedding import SafeOllamaEmbedding
except Exception:  # pragma: no cover - 依賴可能在部份環境尚未安裝
    Document = None
    VectorStoreIndex = None
    SafeOllamaEmbedding = None
    PGVectorStore = None


logger = logging.getLogger("discord_bot")


@runtime_checkable
class IntroRAGPort(Protocol):
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


class NullIntroRAGPort:
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


class PgVectorIntroRAGPort:
    """以 pgvector 實作的 IntroRAGPort。"""

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
        """LlamaIndex PGVectorStore 的實體表名稱通常為 data_<table_name>。"""
        # 僅允許英數與底線，避免 identifier 注入
        safe = re.sub(r"[^a-zA-Z0-9_]", "", self.table_name)
        return f"data_{safe}"

    def _get_db_conn(self):
        return psycopg2.connect(
            host=self.settings.pgvector_host,
            port=self.settings.pgvector_port,
            dbname=self.settings.pgvector_db,
            user=self.settings.pgvector_user,
            password=self.settings.pgvector_password,
        )

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
        if any(dep is None for dep in (Document, VectorStoreIndex, SafeOllamaEmbedding, PGVectorStore)):
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
            self._embed_model = SafeOllamaEmbedding(
                model_name=embed_model_name,
                base_url=self.settings.ollama_base_url,
                request_timeout=self.settings.ollama_timeout,
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


# --- module-level singleton ---
# 為什麼：原本每個呼叫端 (`personality_extractor`, `management_commands`)
# 都 new 一個 PgVectorIntroRAGPort，每個 instance 有自己的 _index / embed_model，
# 每次呼叫 index.insert 都會開新的 HTTP 連線打 Ollama；
# 大量請求下會塞爆 Windows ephemeral port 池（TIME_WAIT socket 累積）。
# 改為全 process 共用單一 instance，內部 index 物件被 LlamaIndex 的 HTTP client 重用。
_pgvector_intro_rag_port_singleton: PgVectorIntroRAGPort | None = None
_singleton_lock = threading.Lock()


def get_pgvector_intro_rag_port() -> PgVectorIntroRAGPort:
    """取得 PgVectorIntroRAGPort 單例。"""
    global _pgvector_intro_rag_port_singleton
    if _pgvector_intro_rag_port_singleton is not None:
        return _pgvector_intro_rag_port_singleton
    with _singleton_lock:
        if _pgvector_intro_rag_port_singleton is None:
            _pgvector_intro_rag_port_singleton = PgVectorIntroRAGPort()
        return _pgvector_intro_rag_port_singleton
