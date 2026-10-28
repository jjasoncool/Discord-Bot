"""Discord 原始訊息備份：每則訊息、編輯、刪除、表情反應全量寫進 postgres 的 discord_messages_raw 表。

架構定位：功能層（`llm/storage`），吃 Discord 訊息物件、寫資料庫。和 `store_chat`（篩選後的語意索引）並列、互不依賴；
raw 表是備份層，也是互動（反應）的真相來源。
  - 上層（誰呼叫）：`discord_bot` 的 on_message／on_message_edit／on_raw_message_delete／on_raw_reaction_add／remove
    （各自的 `enqueue_*`；on_message 另外在滿門檻時 `flush_raw_buffer`）、on_ready（用 `utils.background_tasks.periodic`
    定期呼叫 `flush_raw_buffer`）與停機收尾（`MyBot.close` 呼叫 `flush_raw_buffer`）；要看一則訊息被按了多少反應的功能查
    `get_reaction_salience`。`llm.storage.chat_index_backfill` 直接讀 discord_messages_raw 表，從這裡補寫聊天向量庫漏掉的訊息。
  - 下層（呼叫誰）：psycopg2 連線池（獨立 pool，不和 pgvector 的 LlamaIndex 共用）、`sys_settings.llm_settings.pg_savepoint`、
    `llm.preprocess.sticker_cache`。

介面：`enqueue_raw_message`、`enqueue_raw_edit`、`enqueue_raw_delete`、`enqueue_reaction_change`、`should_trigger_flush`、
  `flush_raw_buffer`、`get_reaction_salience`、`buffer_sizes`／`total_buffer_size`。

規則：四種事件各自一個緩衝；新訊息進來時任一緩衝滿 50 則就寫一批，另外每 60 秒定期寫（反應要夠即時），單次 flush 合併處理；
  純 SQL、不算 embedding；刪除是軟刪（is_deleted=TRUE）。
  一批在同一個交易裡逐筆寫，每筆各自一個保存點：這筆自己的資料寫不進去（內容不合法、違反限制）只略過這筆、記 WARNING
  （只記錯誤的第一行，PostgreSQL 的 DETAIL／CONTEXT 會帶出訊息內容）；連線斷掉換一條連線整批重寫一次；
  權限、表不見這類每筆都會失敗的錯誤整批往外丟。統計是 commit 之後真的寫進去的筆數，另記略過幾筆。
  聊天向量庫的補寫照 channel_id／thread_id 的拆法與 stickers、tenor_gifs 的內容組文字：改這些欄位的語意時，
  要一起改 `chat_index_backfill.build_items`，不然補寫的文字會和即時寫入的不一樣。

例外與決策：連不上（換連線也失敗）時這批就丟了，不放回緩衝。放回要同時有緩衝上限、同時只跑一個 flush、失敗後暫停滿門檻
  觸發，少了這三件，資料庫停著時每則新訊息都會開一個 flush、各佔一條執行緒，放回的反應與編輯還可能被舊的蓋回去。
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import threading
from typing import Any, Literal, Optional

import discord
import psycopg2
from psycopg2.errors import ProgramLimitExceeded
from psycopg2.pool import ThreadedConnectionPool

from llm.preprocess.sticker_cache import get_sticker_text
from sys_settings.llm_settings import LLMServiceSettings, pg_savepoint

logger = logging.getLogger(__name__)

#: 這一筆自己的資料寫不進去：內容不合法（22 類，例如 jsonb 裡的 \u0000）、違反限制（23 類）、超過上限（54000；psycopg2
#: 把它歸在 OperationalError，要單獨列出來）。只略過這筆；其他資料庫錯誤（連線、權限、表不見）每一筆都會一樣失敗，
#: 整批往外丟交給 `_sync_flush`
_ROW_DATA_ERRORS = (psycopg2.DataError, psycopg2.IntegrityError, ProgramLimitExceeded)

_EMPTY_STATS = {"inserted": 0, "updated": 0, "deleted": 0, "reactions_applied": 0, "failed": 0}

# ========== 設定 ==========

RAW_FLUSH_THRESHOLD = 50        # 任一 buffer 達到此量立即觸發 flush
RAW_FLUSH_INTERVAL_SECONDS = 60  # 定時 flush 週期（reaction 要夠即時）

_POOL_MIN_CONN = 1
_POOL_MAX_CONN = 4

# 匹配 Tenor GIF URL（訊息 embed 裡的 url）
_TENOR_URL_PATTERN = re.compile(r"tenor\.com/view/", re.IGNORECASE)

# ========== 模組狀態 ==========

# 四種事件的獨立 buffer
_insert_buffer: list[dict] = []
_edit_buffer: list[dict] = []
_delete_buffer: list[str] = []        # message_id 列表
_reaction_buffer: list[dict] = []     # reaction 事件原始列表

_buffer_lock = asyncio.Lock()

_pool: ThreadedConnectionPool | None = None
_pool_lock = threading.Lock()


def _get_pool() -> ThreadedConnectionPool:
    """延遲建立 connection pool，跨 flush 共用。"""
    global _pool
    if _pool is not None:
        return _pool
    with _pool_lock:
        if _pool is not None:
            return _pool
        settings = LLMServiceSettings()
        _pool = ThreadedConnectionPool(
            minconn=_POOL_MIN_CONN,
            maxconn=_POOL_MAX_CONN,
            host=settings.pgvector_host,
            port=settings.pgvector_port,
            dbname=settings.pgvector_db,
            user=settings.pgvector_user,
            password=settings.pgvector_password,
        )
        logger.info(
            "raw_message_store: connection pool 建立 (min=%d max=%d)",
            _POOL_MIN_CONN, _POOL_MAX_CONN,
        )
        return _pool


# ========== 訊息結構化解析 ==========

def _extract_stickers(msg: discord.Message) -> list[dict] | None:
    """從 msg.stickers 抽出結構化資料。None 表示無貼圖。"""
    if not msg.stickers:
        return None
    result = []
    for s in msg.stickers:
        # StickerFormatType 是 enum；取 .value 才是 int。
        # 兼容未來 discord.py 回傳直接是 int 的情況。
        fmt = getattr(s, "format", None)
        fmt_raw = getattr(fmt, "value", fmt)
        try:
            format_type = int(fmt_raw) if fmt_raw is not None else 0
        except (TypeError, ValueError):
            format_type = 0

        entry: dict[str, Any] = {
            "id": str(s.id),
            "name": s.name,
            "format_type": format_type,
        }
        # 如果 sticker_cache 有描述就補上；去掉 [貼圖：xxx] 外層包裝
        desc = get_sticker_text(s)
        if desc:
            desc = desc.strip()
            if desc.startswith("[貼圖：") and desc.endswith("]"):
                desc = desc[len("[貼圖："):-1]
            entry["description"] = desc
        result.append(entry)
    return result if result else None


def _extract_tenor_gifs(msg: discord.Message) -> list[dict] | None:
    """從 msg.embeds 抽出 Tenor GIF（只記 url/title/description）。"""
    if not msg.embeds:
        return None
    result = []
    for embed in msg.embeds:
        url = embed.url or ""
        if not _TENOR_URL_PATTERN.search(url):
            continue
        entry: dict[str, Any] = {"url": url}
        if embed.title:
            entry["title"] = embed.title
        if embed.description:
            entry["description"] = embed.description[:200]
        result.append(entry)
    return result if result else None


def _has_non_tenor_embed(msg: discord.Message) -> bool:
    """訊息是否有 Tenor 以外的 embed（連結預覽等）。"""
    if not msg.embeds:
        return False
    for embed in msg.embeds:
        url = embed.url or ""
        if not _TENOR_URL_PATTERN.search(url):
            return True
    return False


def _resolve_channel_thread(msg: discord.Message) -> tuple[str, str | None]:
    """解析訊息的 channel_id / thread_id。

    若訊息在 thread 內：channel_id = parent 頻道、thread_id = thread 本身
    否則：            channel_id = msg.channel、thread_id = None
    """
    ch = msg.channel
    if isinstance(ch, discord.Thread):
        parent_id = getattr(ch, "parent_id", None)
        if parent_id:
            return str(parent_id), str(ch.id)
        # 防禦：parent_id 取不到就退而求其次
        return str(ch.id), str(ch.id)
    return str(ch.id), None


def _build_row(msg: discord.Message) -> dict:
    """把 discord.Message 拆解成 raw 表欄位 dict（供 INSERT/UPDATE 使用）。"""
    channel_id, thread_id = _resolve_channel_thread(msg)
    return {
        "message_id": str(msg.id),
        "guild_id": str(msg.guild.id) if msg.guild else "",
        "channel_id": channel_id,
        "thread_id": thread_id,
        "author_id": str(msg.author.id),
        "content": msg.content or "",
        "stickers": _extract_stickers(msg),
        "tenor_gifs": _extract_tenor_gifs(msg),
        "has_attachment": bool(msg.attachments),
        "has_embed": _has_non_tenor_embed(msg),
        "created_at": msg.created_at.isoformat(),
        "edited_at": msg.edited_at.isoformat() if msg.edited_at else None,
        "reply_to_id": (
            str(msg.reference.message_id)
            if msg.reference and msg.reference.message_id
            else None
        ),
        "mention_count": len(msg.mentions),
        "mentioned_users": [str(u.id) for u in msg.mentions] if msg.mentions else None,
    }


# ========== 公開 API（被 discord_bot 事件呼叫）==========

def enqueue_raw_message(msg: discord.Message) -> None:
    """on_message 呼叫：全量寫入 raw 表（bot 訊息除外）。

    任何欄位抽取失敗都只 log、不 raise，避免污染 on_message 事件流。
    """
    if msg.author.bot:
        return
    try:
        row = _build_row(msg)
    except Exception as exc:
        logger.warning(
            "raw_message_store enqueue_raw_message 建列失敗 mid=%s: %s",
            getattr(msg, "id", "?"), exc,
        )
        return
    _insert_buffer.append(row)


def enqueue_raw_edit(after: discord.Message) -> None:
    """on_message_edit 呼叫：content/embeds/stickers 更新。

    若訊息還在 _insert_buffer（尚未落盤），直接原地替換，不排入 edit_buffer。
    """
    if after.author.bot:
        return
    mid = str(after.id)
    try:
        new_row = _build_row(after)
    except Exception as exc:
        logger.warning(
            "raw_message_store enqueue_raw_edit 建列失敗 mid=%s: %s",
            mid, exc,
        )
        return
    for i, row in enumerate(_insert_buffer):
        if row["message_id"] == mid:
            _insert_buffer[i] = new_row
            return
    _edit_buffer.append(new_row)


def enqueue_raw_delete(message_id: int | str) -> None:
    """on_raw_message_delete 呼叫：軟刪標記。

    若訊息還在 _insert_buffer，直接移除（反正還沒寫入 DB）。
    """
    mid = str(message_id)
    for i, row in enumerate(_insert_buffer):
        if row["message_id"] == mid:
            _insert_buffer.pop(i)
            return
    _delete_buffer.append(mid)


def enqueue_reaction_change(
    message_id: int | str,
    emoji_name: str,
    emoji_id: str | int | None,
    user_id: int | str,
    action: Literal["add", "remove"],
) -> None:
    """on_raw_reaction_add/remove 呼叫。

    參數：
        emoji_name: Unicode emoji 字元 或 自訂 emoji 名稱（不含 : :）
        emoji_id:   自訂 emoji 才有；Unicode emoji 傳 None
        user_id:    點 reaction 的使用者
        action:     "add" 或 "remove"
    """
    _reaction_buffer.append({
        "message_id": str(message_id),
        "emoji_name": emoji_name,
        "emoji_id": str(emoji_id) if emoji_id else None,
        "user_id": str(user_id),
        "action": action,
    })


def buffer_sizes() -> dict[str, int]:
    """各 buffer 當下筆數，供監控用。"""
    return {
        "insert": len(_insert_buffer),
        "edit": len(_edit_buffer),
        "delete": len(_delete_buffer),
        "reaction": len(_reaction_buffer),
    }


def total_buffer_size() -> int:
    return sum(buffer_sizes().values())


def should_trigger_flush() -> bool:
    """任一 buffer 達閾值或總量超標時觸發立即 flush。"""
    sizes = buffer_sizes()
    if any(v >= RAW_FLUSH_THRESHOLD for v in sizes.values()):
        return True
    return total_buffer_size() >= RAW_FLUSH_THRESHOLD * 2


async def flush_raw_buffer() -> dict[str, int]:
    """批次處理所有 buffer；回傳 {inserted, updated, deleted, reactions_applied, failed}（failed＝資料壞掉、略過的筆數）。"""
    empty_stats = dict(_EMPTY_STATS)
    if total_buffer_size() == 0:
        return empty_stats

    async with _buffer_lock:
        if total_buffer_size() == 0:
            return empty_stats
        insert_batch = list(_insert_buffer)
        edit_batch = list(_edit_buffer)
        delete_batch = list(_delete_buffer)
        reaction_batch = list(_reaction_buffer)
        _insert_buffer.clear()
        _edit_buffer.clear()
        _delete_buffer.clear()
        _reaction_buffer.clear()

    loop = asyncio.get_running_loop()
    try:
        stats = await loop.run_in_executor(
            None,
            _sync_flush,
            insert_batch, edit_batch, delete_batch, reaction_batch,
        )
    except Exception as exc:
        logger.error("raw_message_store flush 執行失敗: %s", exc, exc_info=True)
        return empty_stats

    if any(stats.values()):
        logger.info(
            "raw_message_store flush: inserted=%d updated=%d deleted=%d reactions=%d failed=%d",
            stats["inserted"], stats["updated"],
            stats["deleted"], stats["reactions_applied"], stats["failed"],
        )
    return stats


def get_reaction_salience(message_ids: list[str]) -> dict[str, int]:
    """批次讀每則訊息的「不重複反應人數」當 salience 訊號（給 ambient callback 的 importance）。

    讀 discord_messages_raw.reaction_breakdown(jsonb) 的 reactors 數；沒進 raw 表 / 無反應 → 0
    （caller 自行視為 0）。sync——async caller 用 run_in_executor / to_thread。
    失敗回空 dict（caller 降級為「全 0」，不影響主流程）。
    """
    if not message_ids:
        return {}
    ids = [str(m) for m in message_ids]
    pool = _get_pool()
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT message_id, reaction_breakdown FROM discord_messages_raw "
                "WHERE message_id = ANY(%s)",
                (ids,),
            )
            rows = cur.fetchall()
        conn.rollback()  # 唯讀查詢：rollback 結束 txn（不留 idle-in-transaction 回 pool）
    except Exception as exc:
        conn.rollback()
        logger.warning("raw_message_store get_reaction_salience 失敗: %s", exc)
        return {}
    finally:
        pool.putconn(conn)

    out: dict[str, int] = {}
    for mid, breakdown in rows:
        # jsonb 多半已是 dict；少數 psycopg2 設定會回字串 → 補 json.loads（同 context_retriever 做法）
        if isinstance(breakdown, str):
            try:
                breakdown = json.loads(breakdown)
            except Exception:
                breakdown = None
        reactors = breakdown.get("reactors") if isinstance(breakdown, dict) else None
        out[str(mid)] = len(reactors) if isinstance(reactors, dict) else 0
    return out


# ========== 同步 DB 操作（在 executor thread 執行）==========

def _sync_flush(
    insert_batch: list[dict],
    edit_batch: list[dict],
    delete_batch: list[str],
    reaction_batch: list[dict],
) -> dict[str, int]:
    """寫一批到資料庫。連線層的錯誤（池子給到已斷的連線、伺服器端把閒置連線關了）換一條連線再寫一次：
    這批寫不進去就整批丟了，停機收尾和聊天向量庫的補寫都靠這張表完整。資料本身的錯誤不重試。"""
    pool = _get_pool()
    for attempt in (1, 2):
        conn = pool.getconn()
        broken = False
        try:
            return _write_all(conn, insert_batch, edit_batch, delete_batch, reaction_batch)
        except (psycopg2.OperationalError, psycopg2.InterfaceError) as exc:
            broken = True
            if attempt == 1:
                logger.warning("raw_message_store: 連線壞了（%s），換一條連線重試一次", exc)
                continue
            raise
        finally:
            pool.putconn(conn, close=broken)   # 壞掉的連線不放回池子，下一個拿到的人才不會再踩到
    return dict(_EMPTY_STATS)   # 迴圈一定 return 或 raise；給型別檢查看


def _write_all(conn, insert_batch: list[dict], edit_batch: list[dict], delete_batch: list[str],
               reaction_batch: list[dict]) -> dict[str, int]:
    """整批在同一個交易裡寫；每筆各自包保存點（`_write_row`），壞的那筆只撤回那筆，交易不會進入失敗狀態，
    所以 commit 之後的統計就是真的寫進去的筆數。"""
    stats = dict(_EMPTY_STATS)
    try:
        conn.autocommit = False
        with conn.cursor() as cur:
            for key, batch, write in (
                ("inserted", insert_batch, _write_inserts),
                ("updated", edit_batch, _write_edits),
                ("deleted", delete_batch, _write_deletes),
                ("reactions_applied", reaction_batch, _apply_reactions),
            ):
                if batch:
                    stats[key], failed = write(cur, batch)
                    stats["failed"] += failed
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass   # 連線已經斷了就 rollback 不了，交給呼叫端換連線
        raise
    return stats


def _json_or_none(value: Any) -> str | None:
    """List/dict → JSON 字串；None → None（讓 psycopg2 以 NULL 送入）。"""
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


def _first_line(exc: BaseException) -> str:
    """錯誤訊息只留第一行：PostgreSQL 的 DETAIL／CONTEXT 會帶出原始值（貼圖、Tenor 的標題），不寫進 log。"""
    text = str(exc).strip()
    return text.splitlines()[0] if text else type(exc).__name__


def _write_row(cur, kind: str, mid: Any, write):
    """包一個保存點寫一筆（或一則訊息的一組反應），回傳 `write()` 的結果。

    這筆自己的資料寫不進去（`_ROW_DATA_ERRORS`，或送出前就失敗的 Python 錯誤，例如內文有 NUL）：撤回這筆、記 WARNING、
    回 None，交易照常往下寫。其他資料庫錯誤往外丟：每一筆都會一樣失敗，交給 `_sync_flush`。
    """
    try:
        with pg_savepoint(cur, "raw_row"):
            return write()
    except Exception as exc:  # 邊界：一筆訊息；這筆的資料寫不進去只略過這筆，其餘照常提交
        if isinstance(exc, psycopg2.Error) and not isinstance(exc, _ROW_DATA_ERRORS):
            raise
        logger.warning("raw_message_store %s 失敗、略過 mid=%s：%s: %s", kind, mid, type(exc).__name__, _first_line(exc))
        return None


def _write_inserts(cur, batch: list[dict]) -> tuple[int, int]:
    """回 (新寫進去的筆數, 略過的筆數)；已經在表裡的（ON CONFLICT）兩邊都不算。"""
    sql = """
        INSERT INTO discord_messages_raw (
            message_id, guild_id, channel_id, thread_id, author_id,
            content, stickers, tenor_gifs, has_attachment, has_embed,
            created_at, edited_at,
            reply_to_id, mention_count, mentioned_users
        ) VALUES (
            %(message_id)s, %(guild_id)s, %(channel_id)s, %(thread_id)s, %(author_id)s,
            %(content)s, %(stickers)s::jsonb, %(tenor_gifs)s::jsonb,
            %(has_attachment)s, %(has_embed)s,
            %(created_at)s, %(edited_at)s,
            %(reply_to_id)s, %(mention_count)s, %(mentioned_users)s::jsonb
        )
        ON CONFLICT (message_id) DO NOTHING
    """
    inserted = failed = 0
    for row in batch:
        def write(row=row):
            params = {**row}
            params["stickers"] = _json_or_none(row["stickers"])
            params["tenor_gifs"] = _json_or_none(row["tenor_gifs"])
            params["mentioned_users"] = _json_or_none(row["mentioned_users"])
            cur.execute(sql, params)
            return cur.rowcount   # 要在保存點收掉之前讀：RELEASE 之後 rowcount 會變成 -1

        written = _write_row(cur, "新增", row.get("message_id"), write)
        if written is None:
            failed += 1
        elif written > 0:
            inserted += 1
    return inserted, failed


def _write_edits(cur, batch: list[dict]) -> tuple[int, int]:
    """回 (改到的筆數, 略過的筆數)；訊息不在表裡（bot 啟動前的舊訊息）時改到 0 筆、不算略過。"""
    sql = """
        UPDATE discord_messages_raw SET
            content = %(content)s,
            stickers = %(stickers)s::jsonb,
            tenor_gifs = %(tenor_gifs)s::jsonb,
            has_attachment = %(has_attachment)s,
            has_embed = %(has_embed)s,
            edited_at = %(edited_at)s
        WHERE message_id = %(message_id)s
    """
    updated = failed = 0
    for row in batch:
        def write(row=row):
            params = {
                "message_id": row["message_id"],
                "content": row["content"],
                "stickers": _json_or_none(row["stickers"]),
                "tenor_gifs": _json_or_none(row["tenor_gifs"]),
                "has_attachment": row["has_attachment"],
                "has_embed": row["has_embed"],
                "edited_at": row["edited_at"],
            }
            cur.execute(sql, params)
            return cur.rowcount

        changed = _write_row(cur, "編輯", row.get("message_id"), write)
        if changed is None:
            failed += 1
        else:
            updated += changed
    return updated, failed


def _write_deletes(cur, batch: list[str]) -> tuple[int, int]:
    """軟刪；message_id 不存在（事件先於 insert）時 ANY 匹配不到、自然是 0。回 (標記的筆數, 略過的筆數)。"""
    def write():
        cur.execute(
            """
            UPDATE discord_messages_raw
            SET is_deleted = TRUE, deleted_at = NOW()
            WHERE message_id = ANY(%s)
            """,
            (batch,),
        )
        return cur.rowcount

    shown = "、".join(str(mid) for mid in batch[:3]) + ("…" if len(batch) > 3 else "")
    marked = _write_row(cur, "刪除", f"{len(batch)} 則（{shown}）", write)
    return (0, len(batch)) if marked is None else (marked, 0)


# ========== Reaction 合併邏輯 ==========

def _build_emoji_key(emoji_name: str, emoji_id: str | None) -> str:
    """把 (name, id) 壓縮成唯一 key。

    - Unicode emoji：emoji_id=None → key = name（即 emoji 字元本身，例如 "👍"）
    - Custom emoji：emoji_id 有值 → key = "name:id"（避免跨 guild 同名衝突）
    """
    if emoji_id:
        return f"{emoji_name}:{emoji_id}"
    return emoji_name


def _classify_emoji_category(emoji_name: str, emoji_id: str | None) -> str:
    """呼叫 reaction_classifier 做分類。若 P2 還沒實作，fallback 為 neutral。"""
    try:
        from llm.persona.reaction_classifier import classify_reaction
        return classify_reaction(emoji_name, emoji_id)
    except ImportError:
        return "neutral"


def _recompute_derived(reactors: dict[str, list[str]]) -> dict[str, Any]:
    """從 reactors 重新算 by_emoji、by_category、各總計。

    reactors schema: {"user_id": ["emoji_key_1", "emoji_key_2", ...]}
      → 同一 user 對同一 message 可能點多種 emoji，但 Discord 不允許同一 emoji 點兩次
    """
    by_emoji: dict[str, int] = {}
    by_category: dict[str, int] = {
        "agree": 0, "laugh": 0, "think": 0, "negative": 0, "neutral": 0,
    }
    for user_id, emoji_keys in reactors.items():
        for key in emoji_keys:
            by_emoji[key] = by_emoji.get(key, 0) + 1
            # 從 key 還原 (name, id) 再送分類
            if ":" in key:
                name, _, emoji_id = key.rpartition(":")
                # 判斷是否為合法 custom emoji id（全數字）
                if emoji_id.isdigit():
                    cat = _classify_emoji_category(name, emoji_id)
                else:
                    cat = _classify_emoji_category(key, None)
            else:
                cat = _classify_emoji_category(key, None)
            by_category[cat] = by_category.get(cat, 0) + 1

    total = sum(by_emoji.values())
    return {
        "by_emoji": by_emoji,
        "by_category": by_category,
        "_total": total,
        "_unique_users": len(reactors),
        "_diversity": len(by_emoji),
    }


def _apply_reactions(cur, batch: list[dict]) -> tuple[int, int]:
    """套用 reaction 增減事件到 raw 表；回 (套用的訊息數, 略過的訊息數)。

    策略：
    1. 先按 message_id 分組，每組是同一訊息的多筆事件
    2. 對每則訊息：鎖住那一列讀當前 reaction_breakdown → 套 delta → 寫回（讀與寫包在同一個保存點）
    3. 若訊息還沒進 raw 表（事件比 insert 先到），直接 skip 並記 log

    讀那句鎖列（FOR UPDATE）：定期 flush 和滿門檻的 flush 可能同時在兩條執行緒寫，都讀到同一個舊值的話，
    後提交的會把先提交那批的反應蓋掉。照 message_id 排序處理，兩批同時鎖到同幾列時順序一致、不會互相卡死。
    """
    # 按 message_id 分組
    by_msg: dict[str, list[dict]] = {}
    for ev in batch:
        by_msg.setdefault(ev["message_id"], []).append(ev)

    applied = failed = skipped_missing = 0
    for mid, events in sorted(by_msg.items()):
        def write(mid=mid, events=events) -> bool:
            cur.execute(
                "SELECT reaction_breakdown FROM discord_messages_raw WHERE message_id = %s FOR UPDATE",
                (mid,),
            )
            row = cur.fetchone()
            if row is None:
                # 訊息不在 raw 表：可能是 bot 啟動前的舊訊息，或事件順序問題
                return False

            breakdown = row[0] or {"reactors": {}, "by_emoji": {}, "by_category": {}}
            reactors: dict[str, list[str]] = dict(breakdown.get("reactors") or {})

            for ev in events:
                key = _build_emoji_key(ev["emoji_name"], ev["emoji_id"])
                uid = ev["user_id"]
                current = list(reactors.get(uid, []))
                if ev["action"] == "add":
                    if key not in current:
                        current.append(key)
                    reactors[uid] = current
                else:  # remove
                    if key in current:
                        current.remove(key)
                    if current:
                        reactors[uid] = current
                    else:
                        reactors.pop(uid, None)

            derived = _recompute_derived(reactors)
            new_breakdown = {
                "reactors": reactors,
                "by_emoji": derived["by_emoji"],
                "by_category": derived["by_category"],
            }

            cur.execute(
                """
                UPDATE discord_messages_raw SET
                    reaction_total = %s,
                    reaction_unique_users = %s,
                    reaction_diversity = %s,
                    reaction_breakdown = %s::jsonb,
                    reactions_updated_at = NOW()
                WHERE message_id = %s
                """,
                (
                    derived["_total"],
                    derived["_unique_users"],
                    derived["_diversity"],
                    json.dumps(new_breakdown, ensure_ascii=False),
                    mid,
                ),
            )
            return True

        done = _write_row(cur, "反應", mid, write)
        if done is None:
            failed += 1
        elif done:
            applied += 1
        else:
            skipped_missing += 1

    if skipped_missing > 0:
        logger.debug(
            "raw_message_store: %d 筆 reaction 事件對應的訊息尚未入庫，先 skip",
            skipped_missing,
        )
    return applied, failed
