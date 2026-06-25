"""Discord 原始訊息批次持久化到 postgres raw 表（discord_messages_raw）。

職責：
- on_message             → 全量寫入（不做 pgvector 那種過濾）
- on_message_edit        → 更新 content / embeds / stickers
- on_raw_message_delete  → 軟刪標記（is_deleted=TRUE）
- on_raw_reaction_add/remove → 即時更新 reaction 結構化資料

和 chat_persistence（寫 LlamaIndex pgvector）並列，兩者互不依賴。
raw 表是「備份層 + 互動真相來源」，pgvector 表是「篩選後的語意索引」。

Buffer 策略：
- 閾值 50 則或 60 秒任一滿足就 flush（reaction 要夠即時）
- 不同事件類型（insert/edit/delete/reaction）各自獨立 buffer，單次 flush 合併處理

DB 連線：
- 走獨立 ThreadedConnectionPool，不和 pgvector LlamaIndex 共用 pool
- 純 SQL，不觸發 embedding
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
from psycopg2.pool import ThreadedConnectionPool

from llm.sticker_cache import get_sticker_text
from sys_settings.llm_settings import LLMServiceSettings

logger = logging.getLogger("discord_bot")

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
    """批次處理所有 buffer；回傳 {inserted, updated, deleted, reactions_applied}。"""
    empty_stats = {"inserted": 0, "updated": 0, "deleted": 0, "reactions_applied": 0}
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
            "raw_message_store flush: inserted=%d updated=%d deleted=%d reactions=%d",
            stats["inserted"], stats["updated"],
            stats["deleted"], stats["reactions_applied"],
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
    pool = _get_pool()
    conn = pool.getconn()
    stats = {"inserted": 0, "updated": 0, "deleted": 0, "reactions_applied": 0}
    try:
        conn.autocommit = False
        with conn.cursor() as cur:
            if insert_batch:
                stats["inserted"] = _write_inserts(cur, insert_batch)
            if edit_batch:
                stats["updated"] = _write_edits(cur, edit_batch)
            if delete_batch:
                stats["deleted"] = _write_deletes(cur, delete_batch)
            if reaction_batch:
                stats["reactions_applied"] = _apply_reactions(cur, reaction_batch)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)
    return stats


def _json_or_none(value: Any) -> str | None:
    """List/dict → JSON 字串；None → None（讓 psycopg2 以 NULL 送入）。"""
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


def _write_inserts(cur, batch: list[dict]) -> int:
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
    count = 0
    for row in batch:
        params = {**row}
        params["stickers"] = _json_or_none(row["stickers"])
        params["tenor_gifs"] = _json_or_none(row["tenor_gifs"])
        params["mentioned_users"] = _json_or_none(row["mentioned_users"])
        try:
            cur.execute(sql, params)
            if cur.rowcount > 0:
                count += 1
        except Exception as exc:
            logger.warning(
                "raw_message_store insert 失敗 mid=%s: %s",
                row["message_id"], exc,
            )
    return count


def _write_edits(cur, batch: list[dict]) -> int:
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
    count = 0
    for row in batch:
        params = {
            "message_id": row["message_id"],
            "content": row["content"],
            "stickers": _json_or_none(row["stickers"]),
            "tenor_gifs": _json_or_none(row["tenor_gifs"]),
            "has_attachment": row["has_attachment"],
            "has_embed": row["has_embed"],
            "edited_at": row["edited_at"],
        }
        try:
            cur.execute(sql, params)
            count += cur.rowcount
        except Exception as exc:
            logger.warning(
                "raw_message_store edit 失敗 mid=%s: %s",
                row["message_id"], exc,
            )
    return count


def _write_deletes(cur, batch: list[str]) -> int:
    # 軟刪；若 message_id 不存在（事件先於 insert），ANY 匹配不到自然 0
    cur.execute(
        """
        UPDATE discord_messages_raw
        SET is_deleted = TRUE, deleted_at = NOW()
        WHERE message_id = ANY(%s)
        """,
        (batch,),
    )
    return cur.rowcount


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
        from llm.reaction_classifier import classify_reaction
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


def _apply_reactions(cur, batch: list[dict]) -> int:
    """套用 reaction 增減事件到 raw 表。

    策略：
    1. 先按 message_id 分組，每組是同一訊息的多筆事件
    2. 對每則訊息：讀當前 reaction_breakdown → 套 delta → 寫回
    3. 若訊息還沒進 raw 表（事件比 insert 先到），直接 skip 並記 log
    """
    # 按 message_id 分組
    by_msg: dict[str, list[dict]] = {}
    for ev in batch:
        by_msg.setdefault(ev["message_id"], []).append(ev)

    applied = 0
    skipped_missing = 0
    for mid, events in by_msg.items():
        try:
            cur.execute(
                "SELECT reaction_breakdown FROM discord_messages_raw WHERE message_id = %s",
                (mid,),
            )
            row = cur.fetchone()
            if row is None:
                # 訊息不在 raw 表：可能是 bot 啟動前的舊訊息，或事件順序問題
                skipped_missing += 1
                continue

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
            applied += 1
        except Exception as exc:
            logger.warning(
                "raw_message_store apply_reactions 失敗 mid=%s: %s",
                mid, exc,
            )

    if skipped_missing > 0:
        logger.debug(
            "raw_message_store: %d 筆 reaction 事件對應的訊息尚未入庫，先 skip",
            skipped_missing,
        )
    return applied
