"""Discord 聊天訊息批次寫進 pgvector 的聊天向量庫：on_message 先進緩衝，滿 30 則或每 5 分鐘寫一批。

架構定位：功能層（`llm/storage`），吃 Discord 訊息物件、寫資料庫。
  - 上層（誰呼叫）：`discord_bot` 的 on_message／on_message_edit（`enqueue_message`、`enqueue_message_edit`，滿門檻就
    `flush_buffer`）與 on_ready（用 `utils.background_tasks.periodic` 定期呼叫 `flush_buffer`）；
    `llm.storage.chat_index_backfill`（從 raw 備份補寫漏掉的，排進同一個 buffer）。
  - 下層（呼叫誰）：`llm.client.lemonade_gate`（GPU 閘門）、`llm.client.http_client.is_unreachable`、
    `llm.preprocess`（表情描述、貼圖描述）、`llm.retrievers.context_retriever`（共用的已寫入 id 集合）、LlamaIndex 的 pgvector 索引。

介面：`enqueue_message(msg)`、`enqueue_message_edit(after)`、`should_flush_now()`、`flush_buffer()`；
  從 raw 備份補寫用的 `compose_persist_text`、`preview_text`（組文字的規則）、`backfill_candidates`／`enqueue_backfill`
  （哪些會排、排進 buffer）。

規則：
  - 寫入時拿著 GPU 閘門（算 embedding 要用顯示卡），插話與 /askai 都在後面排隊，所以一次 flush 最多寫
    FLUSH_GPU_BUDGET_SECONDS 秒，時間到就放鎖、沒寫完的留到下一輪；embedding 用「拿著閘門」模式
    （`make_safe_llm_embedding(holding_gpu_gate=True)`：短逾時、不重試）。
  - 後端連不上時沒寫成的放回緩衝等定期 flush；緩衝有上限（MAX_BUFFER_SIZE），斷太久丟最舊的。
  - 同一時間只跑一個 flush；上一輪因連不上而中止後，一段時間內不因滿門檻提早 flush。

例外與決策：2026-10-09 Lemonade 卡住時這裡拿著閘門一個多小時、整個 bot 的 AI 全卡 → 寫入預算與短逾時；
  連不上時放回緩衝而不是丟掉：後端多半幾分鐘內回來，丟了就少一段紀錄；上限 1,000 是讓斷太久時記憶體不會無限長，
  超過就丟最舊的。
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import Optional

import discord

from llm.client.http_client import is_unreachable
from llm.preprocess.emoji_text_utils import replace_custom_emoji_with_description
from llm.client.lemonade_gate import stream_exclusive
from llm.preprocess.sticker_cache import get_sticker_text

logger = logging.getLogger(__name__)

# Buffer 設定
FLUSH_THRESHOLD = 30
FLUSH_INTERVAL_SECONDS = 300  # 5 分鐘
# 失敗的訊息會放回 buffer，沒有上限的話後端斷越久積越多。以熱絡時段每 5 分鐘
# 10～20 則估，約可撐 4～5 小時；超過時丟最舊的，因為插話與 RAG 比較需要最近的對話。
MAX_BUFFER_SIZE = 1000
# 一次 flush 拿著 GPU 閘門最多寫幾秒；到了就停，剩下的放回 buffer 下一輪再寫（不會丟）。每則寫入前檢查，
# 所以最壞再多一則的時間：排隊等 embedding 名額＋請求本身（各最多 LLMServiceSettings.gated_embed_timeout，
# 模型要重新載入時再加一次）。後端卡住時第一則就逾時、立刻停，通常只佔一次逾時
FLUSH_GPU_BUDGET_SECONDS = 120

# 訊息過濾：太短的純噪音
MIN_TEXT_LENGTH = 2

# 全域 buffer
_buffer: list[dict] = []
_edit_buffer: list[dict] = []
_buffer_lock = asyncio.Lock()

# 同一時間只跑一個 flush：後端連不上時 buffer 一直超過門檻，不擋的話每則新訊息都會再開一個。
_flush_running = False
# 上一輪因後端連不上而中止後，到這個時間點前不因「滿門檻」提早 flush，只等定期 flush 重試。
_threshold_paused_until = 0.0
# 超過上限丟掉的則數，留到下一次 flush 才記一行 log，避免斷線期間每則訊息各記一行。
_dropped_overflow = 0

# 跨批次共用的 LlamaIndex chat index，避免每次 flush 都 new 新 SafeLLMEmbedding / PGVectorStore；
# 大量短連線會塞滿 Windows ephemeral port 池。
# 只在 embed_model 換掉時重建；runtime config 熱切換仍會被感知。
_chat_index_cache: tuple[str, object] | None = None  # (embed_model_name, VectorStoreIndex)
# 多個 flush_buffer 可能在 executor threads 同時呼叫 _get_chat_index，加鎖防止重複 init
_chat_index_lock = threading.Lock()

# 去重集合：與 context_retriever._PERSISTED_MESSAGE_IDS 共用，避免重複寫入
def _get_persisted_ids() -> set[str]:
    """延遲取得共用去重集合，避免循環 import。"""
    from llm.retrievers.context_retriever import _PERSISTED_MESSAGE_IDS
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


def compose_persist_text(content: str, sticker_texts: list[str], previews: list[str]) -> str:
    """組裝要寫入 pgvector 的文字：內文＋貼圖描述＋連結預覽。

    即時寫入（Discord 訊息物件）和從 raw 備份補寫（`chat_index_backfill`）都走這一份，兩邊寫進去的文字才一樣。
    custom emoji `<:name:id>` 會被語意化替換為 `[描述]`，避免 embed model
    把 emoji token 當亂碼。raw_message_store 不做這個替換（保留原文）。
    """
    text = replace_custom_emoji_with_description((content or "").strip())
    if sticker_texts:
        sticker_part = " ".join(sticker_texts)
        text = f"{text} {sticker_part}" if text else sticker_part
    if previews:
        embed_text = " ".join(f"[預覽：{p}]" for p in previews)
        text = f"{text} {embed_text}" if text else embed_text
    return text


def preview_text(title: Optional[str], description: Optional[str]) -> Optional[str]:
    """一個連結預覽要寫進去的文字（標題 - 描述前 100 字）；兩個都沒有回 None。"""
    parts = []
    if title:
        parts.append(title)
    if description:
        parts.append(description[:100])
    return " - ".join(parts) if parts else None


def _build_persist_text(msg: discord.Message) -> str:
    """組裝要寫入 pgvector 的文字（含貼圖描述、Discord 抓取的連結預覽）。"""
    sticker_texts = [t for t in (get_sticker_text(s) for s in (msg.stickers or [])) if t]
    previews = [p for p in (preview_text(e.title, e.description) for e in (msg.embeds or [])) if p]
    return compose_persist_text(msg.content, sticker_texts, previews)


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
    _trim_oldest(_buffer)


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
    _trim_oldest(_edit_buffer)


def backfill_candidates(items: list[dict]) -> tuple[list[dict], list[str]]:
    """補寫的訊息哪些會排進 buffer（不改 buffer）：回傳 (會排的項目, 已寫過或已在 buffer 而跳過的 message_id)。

    「已寫過」看的是這個行程記的已寫入集合，資料庫查到缺、這裡卻記成已寫的也算在跳過裡（例如被切成兩段、撞到唯一
    索引而沒寫成的長訊息），呼叫端別每輪再排它。會排的只取 buffer 剩下的空間：補寫的是舊訊息，不擠掉即時的。
    """
    persisted = _get_persisted_ids()
    queued = {item["message_id"] for item in _buffer} | {item["message_id"] for item in _edit_buffer}
    fresh = [item for item in items if item["message_id"] not in persisted and item["message_id"] not in queued]
    skipped = [item["message_id"] for item in items if item["message_id"] in persisted or item["message_id"] in queued]
    room = max(MAX_BUFFER_SIZE - len(_buffer), 0)
    return fresh[:room], skipped


def enqueue_backfill(items: list[dict]) -> tuple[list[str], list[str]]:
    """把補寫的訊息（`chat_index_backfill` 從 raw 備份組好，欄位同 buffer）排進 buffer 前端。

    回傳 (排進去的 message_id, 跳過的 message_id)，規則見 `backfill_candidates`。
    寫入走同一條 flush（GPU 閘門、時間預算、連不上放回），這裡不自己寫資料庫。
    """
    fresh, skipped = backfill_candidates(items)
    _buffer[:0] = fresh   # 放前面：時間順序跟即時寫入的一致（較舊的先寫）
    return [item["message_id"] for item in fresh], skipped


def _trim_oldest(buf: list[dict]) -> None:
    """超過 MAX_BUFFER_SIZE 就丟最舊的（list 前端）；丟掉的則數留給下一次 flush 記 log。"""
    global _dropped_overflow
    overflow = len(buf) - MAX_BUFFER_SIZE
    if overflow > 0:
        del buf[:overflow]
        _dropped_overflow += overflow


def _is_backend_unreachable(exc: BaseException) -> bool:
    """embedding 後端或 pgvector 暫時連不上——跟訊息內容無關，下一輪重試就會好。

    其他錯誤（例如後端回 4xx／5xx）可能是那則訊息本身的問題，重試也不會好；
    照舊略過該則，避免一則壞訊息永遠卡在 buffer。
    """
    if is_unreachable(exc):
        return True
    try:
        from sqlalchemy.exc import InterfaceError, OperationalError
    except Exception:
        return False
    return isinstance(exc, (OperationalError, InterfaceError))


def should_flush_now() -> bool:
    """on_message 用：滿門檻、沒有 flush 在跑、也不在失敗後的暫停期間，才提早 flush。"""
    return (
        len(_buffer) >= FLUSH_THRESHOLD
        and not _flush_running
        and time.monotonic() >= _threshold_paused_until
    )


async def flush_buffer() -> int:
    """將 buffer 中的訊息批次寫入/更新 pgvector，回傳處理數量。

    後端連不上時，沒寫成的訊息放回 buffer 前端（維持時間順序），
    並暫停「滿門檻提早 flush」，等下一輪定期 flush 再試。
    """
    global _flush_running, _threshold_paused_until, _dropped_overflow
    if _dropped_overflow:
        logger.warning(
            "聊天 buffer 超過上限 %d 則，已丟棄最舊的 %d 則（這些訊息不會寫進 pgvector）",
            MAX_BUFFER_SIZE, _dropped_overflow,
        )
        _dropped_overflow = 0
    if not _buffer and not _edit_buffer:
        return 0
    if _flush_running:
        return 0
    if not _check_flush_deps():
        return 0

    _flush_running = True
    try:
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
        insert_left: list[dict] = []
        update_left: list[dict] = update_batch
        async with stream_exclusive():
            # 從拿到閘門起算：排隊等閘門的時間不算在內
            deadline = time.monotonic() + FLUSH_GPU_BUDGET_SECONDS
            if insert_batch:
                written, insert_left = await loop.run_in_executor(
                    None, _sync_write_batch, insert_batch, deadline
                )
                count += written
            # 新增那批已經連不上（或時間用完）就不必再試編輯：一樣會失敗，還多佔 GPU 閘門
            if update_batch and not insert_left:
                updated, update_left = await loop.run_in_executor(
                    None, _sync_update_batch, update_batch, deadline
                )
                count += updated

        if insert_left or update_left:
            async with _buffer_lock:
                _buffer[:0] = insert_left
                _trim_oldest(_buffer)
                # flush 期間同一則又被編輯過的話，以 buffer 裡較新的那份為準
                newer = {item["message_id"] for item in _edit_buffer}
                _edit_buffer[:0] = [i for i in update_left if i["message_id"] not in newer]
                _trim_oldest(_edit_buffer)
            _threshold_paused_until = time.monotonic() + FLUSH_INTERVAL_SECONDS
            logger.warning(
                "聊天寫入 pgvector 中止：%d 則新訊息、%d 則編輯放回 buffer，等下一輪定期 flush 重試",
                len(insert_left), len(update_left),
            )
        else:
            _threshold_paused_until = 0.0
        return count
    finally:
        _flush_running = False


def _get_chat_index():
    """取得跨批次共用的 chat pgvector VectorStoreIndex（快取機制）。

    只在 embed_model 名稱改變時才重建，避免每次 flush 都 new 新 embed / vector store，
    造成大量 Ollama HTTP 短連線耗盡 Windows ephemeral port。
    """
    global _chat_index_cache

    from llama_index.core import VectorStoreIndex
    from llama_index.vector_stores.postgres import PGVectorStore
    from llm.client.embedding_client import make_safe_llm_embedding
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
            holding_gpu_gate=True,     # flush 拿著 GPU 閘門算 embedding
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


def _out_of_time(deadline: Optional[float]) -> bool:
    return deadline is not None and time.monotonic() >= deadline


def _chat_node(item: dict):
    """一則訊息一個節點，不經 LlamaIndex 的切段器。

    經切段器的話，內文加預覽超過切段長度的訊息會被切成兩段，第二段撞到 message_id 的唯一索引、整則回滾，
    卻被當成已存在而從此漏掉；編輯後變長的更慘，舊的先刪、新的寫不進去。embedding 的上下文（8192）放得下
    任何一則 Discord 訊息，所以不需要切。節點以訊息 id 當來源，`delete_ref_doc(message_id)` 才刪得到它。
    """
    from llama_index.core.schema import NodeRelationship, RelatedNodeInfo, TextNode

    mid = item["message_id"]
    return TextNode(
        id_=mid,
        text=item["text"],
        metadata={
            "message_id": mid,
            "author_id": item["author_id"],
            "channel_id": item["channel_id"],
            "timestamp": item["timestamp"],
            "doc_type": "discord_chat",
        },
        relationships={NodeRelationship.SOURCE: RelatedNodeInfo(node_id=mid)},
    )


def _sync_write_batch(batch: list[dict], deadline: Optional[float] = None) -> tuple[int, list[dict]]:
    """同步寫入一批訊息到 pgvector（在 executor 中執行）。

    回傳 (新寫入則數, 沒寫成、要放回 buffer 的訊息)。後端連不上時立刻停下、剩下的整批放回：
    逐則硬試的話每則都要等到連線逾時，這段時間一直佔著 GPU 閘門，/askai 與插話都得等。
    過了 `deadline`（`time.monotonic()` 的時刻）也停：後端只是很慢時，不讓一批訊息拖住閘門。
    """
    try:
        index = _get_chat_index()
    except Exception as exc:
        logger.warning("on_message 批次寫入 pgvector 失敗（無法取得 index）: %s", exc)
        return 0, list(batch)

    persisted_ids = _get_persisted_ids()
    written = 0
    skipped = 0
    for pos, item in enumerate(batch):
        mid = item["message_id"]
        if mid in persisted_ids:
            skipped += 1
            continue
        if _out_of_time(deadline):
            logger.warning(
                "on_message 批次寫入 pgvector 先停（佔 GPU 閘門超過 %d 秒，已寫 %d 則），剩下的下一輪再寫",
                FLUSH_GPU_BUDGET_SECONDS, written,
            )
            return written, batch[pos:]
        try:
            index.insert_nodes([_chat_node(item)])
            persisted_ids.add(mid)
            written += 1
        except Exception as exc:
            exc_str = str(exc).lower()
            if "duplicate" in exc_str or "unique" in exc_str:
                persisted_ids.add(mid)
                skipped += 1
            elif _is_backend_unreachable(exc):
                logger.warning(
                    "on_message 批次寫入 pgvector 中止（後端連不上，已寫 %d 則）: %s",
                    written, exc,
                )
                return written, batch[pos:]
            else:
                logger.warning("on_message 單筆寫入失敗，略過: mid=%s err=%s", mid, exc)

    logger.info(
        "on_message 批次處理 pgvector: 新寫入 %d / 已存在跳過 %d / 共 %d",
        written, skipped, len(batch),
    )
    return written, []


def _sync_update_batch(batch: list[dict], deadline: Optional[float] = None) -> tuple[int, list[dict]]:
    """同步更新已持久化的訊息（delete + re-insert 以刷新 embedding）。

    回傳 (更新則數, 要放回編輯 buffer 的訊息)，規則（連不上、時間用完）同 `_sync_write_batch`。
    刪掉舊的之後才連不上的那則也會放回去，下一輪補寫，不會從 pgvector 消失。
    """
    try:
        index = _get_chat_index()
    except Exception as exc:
        logger.warning("on_message_edit 批次更新 pgvector 失敗（無法取得 index）: %s", exc)
        return 0, list(batch)

    updated = 0
    for pos, item in enumerate(batch):
        mid = item["message_id"]
        if _out_of_time(deadline):
            logger.warning(
                "on_message_edit 批次更新 pgvector 先停（佔 GPU 閘門超過 %d 秒，已更新 %d 則），剩下的下一輪再更新",
                FLUSH_GPU_BUDGET_SECONDS, updated,
            )
            return updated, batch[pos:]
        try:
            index.delete_ref_doc(mid)
            index.insert_nodes([_chat_node(item)])
            updated += 1
        except Exception as exc:
            if _is_backend_unreachable(exc):
                logger.warning(
                    "on_message_edit 批次更新 pgvector 中止（後端連不上，已更新 %d 則）: %s",
                    updated, exc,
                )
                return updated, batch[pos:]
            logger.warning("on_message_edit 單筆更新失敗，略過: mid=%s err=%s", mid, exc)

    logger.info("on_message_edit 批次更新 pgvector: %d 則", updated)
    return updated, []
