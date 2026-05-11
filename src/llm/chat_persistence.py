"""Discord 聊天訊息批次持久化到 pgvector。

提供 buffer 機制，on_message 時加入 buffer，
滿 FLUSH_THRESHOLD 則或每 FLUSH_INTERVAL_SECONDS 秒自動 flush。
"""
from __future__ import annotations

import asyncio
import logging
import threading
from typing import Optional

import discord

from llm.emoji_text_utils import replace_custom_emoji_with_description
from llm.lemonade_gate import stream_exclusive
from llm.sticker_cache import get_sticker_text

logger = logging.getLogger("discord_bot")

# Buffer 設定
FLUSH_THRESHOLD = 30
FLUSH_INTERVAL_SECONDS = 300  # 5 分鐘

# 訊息過濾：太短的純噪音
MIN_TEXT_LENGTH = 2

# 全域 buffer
_buffer: list[dict] = []
_edit_buffer: list[dict] = []
_buffer_lock = asyncio.Lock()

# 跨批次共用的 LlamaIndex chat index，避免每次 flush 都 new 新 SafeLLMEmbedding / PGVectorStore；
# 大量短連線會塞滿 Windows ephemeral port 池。
# 只在 embed_model 換掉時重建；runtime config 熱切換仍會被感知。
_chat_index_cache: tuple[str, object] | None = None  # (embed_model_name, VectorStoreIndex)
# 多個 flush_buffer 可能在 executor threads 同時呼叫 _get_chat_index，加鎖防止重複 init
_chat_index_lock = threading.Lock()

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
    """組裝要寫入 pgvector 的文字（含貼圖描述、連結預覽）。

    custom emoji `<:name:id>` 會被語意化替換為 `[描述]`，避免 embed model
    把 emoji token 當亂碼。raw_message_store 不做這個替換（保留原文）。
    """
    text = (msg.content or "").strip()
    text = replace_custom_emoji_with_description(text)
    if msg.stickers:
        sticker_texts = []
        for sticker in msg.stickers:
            st = get_sticker_text(sticker)
            if st:
                sticker_texts.append(st)
        if sticker_texts:
            sticker_part = " ".join(sticker_texts)
            text = f"{text} {sticker_part}" if text else sticker_part
    # 附加 Discord 抓取的連結預覽（標題/描述）
    if msg.embeds:
        embed_parts = []
        for embed in msg.embeds:
            parts = []
            if embed.title:
                parts.append(embed.title)
            if embed.description:
                parts.append(embed.description[:100])
            if parts:
                embed_parts.append(" - ".join(parts))
        if embed_parts:
            embed_text = " ".join(f"[預覽：{p}]" for p in embed_parts)
            text = f"{text} {embed_text}" if text else embed_text
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


def enqueue_message_edit(after: discord.Message) -> None:
    """處理訊息編輯：更新 buffer 內已暫存的項目，或排隊等待 pgvector 更新。"""
    if after.author.bot:
        return
    message_id = str(after.id)
    text = _build_persist_text(after)
    if len(text) < MIN_TEXT_LENGTH:
        return

    # 還在新增 buffer 裡 → 直接更新文字
    for item in _buffer:
        if item["message_id"] == message_id:
            item["text"] = text
            return

    # 已持久化到 pgvector → 加入編輯 buffer
    if message_id not in _get_persisted_ids():
        return
    for item in _edit_buffer:
        if item["message_id"] == message_id:
            item["text"] = text
            return
    _edit_buffer.append({
        "message_id": message_id,
        "text": text,
        "author_id": str(after.author.id),
        "channel_id": str(after.channel.id),
        "guild_id": str(after.guild.id) if after.guild else "",
        "timestamp": after.created_at.isoformat(),
    })


async def flush_buffer() -> int:
    """將 buffer 中的訊息批次寫入/更新 pgvector，回傳處理數量。"""
    if not _buffer and not _edit_buffer:
        return 0
    if not _check_flush_deps():
        return 0

    async with _buffer_lock:
        if not _buffer and not _edit_buffer:
            return 0
        insert_batch = list(_buffer)
        _buffer.clear()
        update_batch = list(_edit_buffer)
        _edit_buffer.clear()

    # _buffer_lock 已釋放（不卡新訊息入 buffer）；
    # 接下來的 batch embedding 必須等 lemonade 沒人在 stream LLM，否則
    # 會把對方連線 reset 掉（詳見 lemonade_gate.py）。
    loop = asyncio.get_running_loop()
    count = 0
    async with stream_exclusive():
        if insert_batch:
            count += await loop.run_in_executor(None, _sync_write_batch, insert_batch)
        if update_batch:
            count += await loop.run_in_executor(None, _sync_update_batch, update_batch)
    return count


def _get_chat_index():
    """取得跨批次共用的 chat pgvector VectorStoreIndex（快取機制）。

    只在 embed_model 名稱改變時才重建，避免每次 flush 都 new 新 embed / vector store，
    造成大量 Ollama HTTP 短連線耗盡 Windows ephemeral port。
    """
    global _chat_index_cache

    from llama_index.core import VectorStoreIndex
    from llama_index.vector_stores.postgres import PGVectorStore
    from llm.safe_llm_embedding import make_safe_llm_embedding
    from sys_settings.llm_settings import LLMServiceSettings, load_llm_runtime_config
    from sys_settings.pgvector_settings import HYBRID_RETRIEVAL_SETTINGS

    settings = LLMServiceSettings()
    runtime_config = load_llm_runtime_config(settings.llm_runtime_model_path)
    embed_model_name = runtime_config.embed_model

    # Fast path：無鎖 double-check
    if _chat_index_cache is not None and _chat_index_cache[0] == embed_model_name:
        return _chat_index_cache[1]

    with _chat_index_lock:
        if _chat_index_cache is not None and _chat_index_cache[0] == embed_model_name:
            return _chat_index_cache[1]
        embed_model = make_safe_llm_embedding(
            settings=settings,
            runtime_config=runtime_config,
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
        _chat_index_cache = (embed_model_name, index)
        logger.info("chat_persistence: 建立新 VectorStoreIndex（embed_model=%s）", embed_model_name)
        return index


def _sync_write_batch(batch: list[dict]) -> int:
    """同步寫入一批訊息到 pgvector（在 executor 中執行）。"""
    from llama_index.core import Document

    try:
        index = _get_chat_index()

        persisted_ids = _get_persisted_ids()
        written = 0
        skipped = 0
        for item in batch:
            mid = item["message_id"]
            if mid in persisted_ids:
                skipped += 1
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
            except Exception as exc:
                exc_str = str(exc).lower()
                if "duplicate" in exc_str or "unique" in exc_str:
                    persisted_ids.add(mid)
                    skipped += 1
                else:
                    logger.warning("on_message 單筆寫入失敗（將重試）: mid=%s err=%s", mid, exc)

        logger.info(
            "on_message 批次處理 pgvector: 新寫入 %d / 已存在跳過 %d / 共 %d",
            written, skipped, len(batch),
        )
        return written
    except Exception as exc:
        logger.warning("on_message 批次寫入 pgvector 失敗: %s", exc)
        return 0


def _sync_update_batch(batch: list[dict]) -> int:
    """同步更新已持久化的訊息（delete + re-insert 以刷新 embedding）。"""
    from llama_index.core import Document

    try:
        index = _get_chat_index()

        updated = 0
        for item in batch:
            mid = item["message_id"]
            try:
                index.delete_ref_doc(mid)
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
                updated += 1
            except Exception as exc:
                logger.warning("on_message_edit 單筆更新失敗: mid=%s err=%s", mid, exc)

        logger.info("on_message_edit 批次更新 pgvector: %d 則", updated)
        return updated
    except Exception as exc:
        logger.warning("on_message_edit 批次更新 pgvector 失敗: %s", exc)
        return 0


def buffer_size() -> int:
    """回傳目前 buffer 中的訊息數量。"""
    return len(_buffer)
