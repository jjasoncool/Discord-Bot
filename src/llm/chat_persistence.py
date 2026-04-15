"""Discord 聊天訊息批次持久化到 pgvector。

提供 buffer 機制，on_message 時加入 buffer，
滿 FLUSH_THRESHOLD 則或每 FLUSH_INTERVAL_SECONDS 秒自動 flush。
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

import discord

from llm.sticker_cache import get_sticker_text

logger = logging.getLogger("discord_bot")

# Buffer 設定
FLUSH_THRESHOLD = 30
FLUSH_INTERVAL_SECONDS = 300  # 5 分鐘

# 訊息過濾：太短的純噪音
MIN_TEXT_LENGTH = 2

# 全域 buffer
_buffer: list[dict] = []
_buffer_lock = asyncio.Lock()

# 去重集合：與 context_retriever._PERSISTED_MESSAGE_IDS 共用，避免重複寫入
def _get_persisted_ids() -> set[str]:
    """延遲取得共用去重集合，避免循環 import。"""
    from llm.context_retriever import _PERSISTED_MESSAGE_IDS
    return _PERSISTED_MESSAGE_IDS

# 延遲 import 避免循環依賴
_flush_deps_ready: Optional[bool] = None


def _check_flush_deps() -> bool:
    """檢查 pgvector 相關依賴是否可用。"""
    global _flush_deps_ready
    if _flush_deps_ready is not None:
        return _flush_deps_ready
    try:
        from llama_index.core import Document, VectorStoreIndex
        from llama_index.vector_stores.postgres import PGVectorStore
        _flush_deps_ready = all(dep is not None for dep in (Document, VectorStoreIndex, PGVectorStore))
    except Exception:
        _flush_deps_ready = False
    return _flush_deps_ready


def _build_persist_text(msg: discord.Message) -> str:
    """組裝要寫入 pgvector 的文字（含貼圖描述）。"""
    text = (msg.content or "").strip()
    if msg.stickers:
        sticker_texts = []
        for sticker in msg.stickers:
            st = get_sticker_text(sticker)
            if st:
                sticker_texts.append(st)
        if sticker_texts:
            sticker_part = " ".join(sticker_texts)
            text = f"{text} {sticker_part}" if text else sticker_part
    return text


def enqueue_message(msg: discord.Message) -> None:
    """將訊息加入持久化 buffer（non-blocking，從 on_message 呼叫）。"""
    # 過濾
    if msg.author.bot:
        return
    message_id = str(msg.id)
    if message_id in _get_persisted_ids():
        return

    text = _build_persist_text(msg)
    if len(text) < MIN_TEXT_LENGTH:
        return

    _buffer.append({
        "message_id": message_id,
        "text": text,
        "author_id": str(msg.author.id),
        "channel_id": str(msg.channel.id),
        "guild_id": str(msg.guild.id) if msg.guild else "",
        "timestamp": msg.created_at.isoformat(),
    })


async def flush_buffer() -> int:
    """將 buffer 中的訊息批次寫入 pgvector，回傳寫入數量。"""
    if not _buffer:
        return 0
    if not _check_flush_deps():
        return 0

    async with _buffer_lock:
        if not _buffer:
            return 0
        batch = list(_buffer)
        _buffer.clear()

    # 在 executor 中執行同步的 pgvector 寫入
    loop = asyncio.get_running_loop()
    count = await loop.run_in_executor(None, _sync_write_batch, batch)
    return count


def _sync_write_batch(batch: list[dict]) -> int:
    """同步寫入一批訊息到 pgvector（在 executor 中執行）。"""
    from llama_index.core import Document, VectorStoreIndex
    from llama_index.vector_stores.postgres import PGVectorStore
    from sys_settings.llm_settings import LLMServiceSettings, load_ollama_runtime_config
    from llama_index.embeddings.ollama import OllamaEmbedding
    from sys_settings.pgvector_settings import HYBRID_RETRIEVAL_SETTINGS

    settings = LLMServiceSettings()
    try:
        runtime_config = load_ollama_runtime_config(settings.ollama_runtime_model_path)
        embed_model = OllamaEmbedding(
            model_name=runtime_config.embed_model,
            base_url=settings.ollama_base_url,
            request_timeout=settings.ollama_timeout,
        )
        vector_store = PGVectorStore.from_params(
            database=settings.pgvector_db,
            host=settings.pgvector_host,
            password=settings.pgvector_password,
            port=settings.pgvector_port,
            user=settings.pgvector_user,
            table_name=HYBRID_RETRIEVAL_SETTINGS.get_chat_table_name(),
            embed_dim=HYBRID_RETRIEVAL_SETTINGS.pgvector_embed_dim,
            hybrid_search=True,
        )
        index = VectorStoreIndex.from_vector_store(
            vector_store=vector_store,
            embed_model=embed_model,
        )

        persisted_ids = _get_persisted_ids()
        written = 0
        for item in batch:
            mid = item["message_id"]
            if mid in persisted_ids:
                continue
            try:
                doc = Document(
                    text=item["text"],
                    doc_id=mid,
                    metadata={
                        "message_id": mid,
                        "author_id": item["author_id"],
                        "channel_id": item["channel_id"],
                        "timestamp": item["timestamp"],
                        "doc_type": "discord_chat",
                    },
                )
                index.insert(doc)
                persisted_ids.add(mid)
                written += 1
            except Exception:
                # unique index 重複或其他單筆錯誤，跳過繼續
                persisted_ids.add(mid)

        logger.info("on_message 批次寫入 pgvector: %d 則", written)
        return written
    except Exception as exc:
        logger.warning("on_message 批次寫入 pgvector 失敗: %s", exc)
        return 0


def buffer_size() -> int:
    """回傳目前 buffer 中的訊息數量。"""
    return len(_buffer)
