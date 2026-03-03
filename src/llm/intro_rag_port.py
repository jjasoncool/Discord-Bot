"""Intro RAG 串接層（技術介接層）。

職責：定義「如何把資料送進 RAG/向量庫」的介面。
不放業務流程判斷。
"""
from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

from sys_settings.llm_settings import LLMServiceSettings, load_ollama_runtime_config
from sys_settings.pgvector_settings import HYBRID_RETRIEVAL_SETTINGS

try:
    from llama_index.core import Document, VectorStoreIndex
    from llama_index.embeddings.ollama import OllamaEmbedding
    from llama_index.vector_stores.postgres import PGVectorStore
except Exception:  # pragma: no cover - 依賴可能在部份環境尚未安裝
    Document = None
    VectorStoreIndex = None
    OllamaEmbedding = None
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
    ) -> None:
        """將他人印象資料寫入 RAG/向量資料庫。"""


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
    ) -> None:
        _ = (
            guild_id,
            channel_id,
            author_id,
            target_user_id,
            target_alias,
            target_habit,
            impression,
        )


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

    def _dependencies_ready(self) -> bool:
        if any(dep is None for dep in (Document, VectorStoreIndex, OllamaEmbedding, PGVectorStore)):
            logger.warning("Intro RAG 依賴未就緒，略過 pgvector 寫入。")
            return False
        return True

    def _get_embed_model(self):
        runtime_config = load_ollama_runtime_config(self.settings.ollama_runtime_model_path)
        embed_model_name = runtime_config.embed_model
        if self._embed_model is not None and self._embed_model_name == embed_model_name:
            return self._embed_model

        self._embed_model = OllamaEmbedding(
            model_name=embed_model_name,
            base_url=self.settings.ollama_base_url,
            request_timeout=self.settings.ollama_timeout,
        )
        self._embed_model_name = embed_model_name
        self._index = None
        return self._embed_model

    def _get_index(self):
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
        return self._index

    def _insert(self, *, doc_id: str, text: str, metadata: dict[str, str]) -> None:
        index = self._get_index()
        doc = Document(
            text=text,
            doc_id=doc_id,
            metadata=metadata,
        )
        index.insert(doc)

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
            self._insert(doc_id=doc_id, text=text, metadata=metadata)
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
            doc_id = f"impression:{guild_id}:{author_id}:{target_user_id}"
            self._insert(doc_id=doc_id, text=text, metadata=metadata)
        except Exception as exc:
            logger.error("寫入 member impression 至 pgvector 失敗: %s", exc, exc_info=True)
