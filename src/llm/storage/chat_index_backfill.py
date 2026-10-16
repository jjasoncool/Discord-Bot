"""從 raw 備份補寫聊天向量庫漏掉的訊息：raw 表有、聊天向量庫沒有的，組成同樣的文字排進聊天記憶的寫入佇列。

架構定位：功能層（`llm/storage`），讀 pgvector 的兩張表，交給 `store_chat` 寫。
  - 上層（誰呼叫）：`discord_bot` 的 on_ready（`supervise` ＋ `periodic` 定期呼叫 `run_once`）。
  - 下層（呼叫誰）：`LLMServiceSettings().pgvector_cursor()`（查詢）、`HYBRID_RETRIEVAL_SETTINGS.chat_table()`（表名）、
    `store_chat`（組文字、判斷哪些要排、排進寫入佇列）、`llm.preprocess.sticker_cache`（貼圖描述）、`sys_settings.switches`（開關）。

介面：`run_once()`（查一次，依開關排進佇列或只記 log）、`build_items(rows)`（raw 的列 → 寫入佇列的項目）。

規則：
  - 為什麼會漏：聊天記憶先放記憶體、每 5 分鐘寫一次，停機時來不及寫的會丟；後端斷太久、緩衝滿了也會丟最舊的。
    raw 備份每 60 秒寫一次、停機時也會補寫，所以拿它來補。
  - 只排進 `store_chat` 的寫入佇列，寫入走同一條 flush（GPU 閘門、時間預算、連不上放回）；一次最多排 BATCH_LIMIT 則
    （比提早寫入的門檻小，不讓一輪補寫就觸發一次大批寫入）。聊天向量庫的 message_id 有唯一索引，重複的寫不進去。
  - 先補最新的：最近一次停機丟的最常被用到。這個行程啟動前建立的訊息不可能在這個行程的緩衝裡，所以不必等
    SETTLE_MINUTES（那段只用來避開還在緩衝裡、等下一次寫入的）；啟動後第一輪就補得到停機前那幾分鐘。
  - 不補：bot 的訊息（raw 本來就不收）、已刪除的、組出來的文字太短的（跟即時寫入同一條規則）。同一個行程排過、
    跳過或判定不寫的不再查：寫入失敗的那則不會每輪重試，也不會一直佔住每輪的名額。
  - 要從聊天向量庫永久移除某則訊息，raw 那列也要標成已刪除（is_deleted），否則 WINDOW_DAYS 天內會被補回來。
  - 開關 `chat_index_backfill_mode`：off＝不查；dry_run＝查、記 log 不排；on＝排進佇列。

例外與決策：
  - raw 表沒存 Tenor 以外的連結預覽（只有 has_embed），補寫的文字少了那段「[預覽：…]」；Tenor 動圖有存，照樣附上。
  - 貼圖用補寫當下的描述快取組字（即時寫入用的也是寫入當下的快取）。
  - 查詢要拿範圍內 raw 的每一列去比對聊天向量庫的 message_id 索引：快取熱的時候幾十毫秒，冷的時候要幾秒。
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from llm.preprocess.sticker_cache import get_sticker_text
from llm.storage import store_chat
from sys_settings import switches
from sys_settings.llm_settings import LLMServiceSettings
from sys_settings.pgvector_settings import HYBRID_RETRIEVAL_SETTINGS

logger = logging.getLogger(__name__)

#: 往回查幾天
WINDOW_DAYS = 14
#: 這個行程啟動後建立的訊息，最近幾分鐘內的不補：可能還在聊天記憶的緩衝裡，等下一次定期寫入
SETTLE_MINUTES = 15
#: 一次最多排幾則進寫入佇列（要小於 store_chat.FLUSH_THRESHOLD）
BATCH_LIMIT = 20
#: 多久查一次；啟動後第一次在幾秒後查（避開剛啟動時大家都在搶資源）
INTERVAL_SECONDS = 900
FIRST_RUN_AFTER_SECONDS = 300

#: 這個行程什麼時候開始的：在這之前建立的訊息不會在這個行程的緩衝裡
_STARTED_AT = datetime.now(timezone.utc)
#: 這個行程排過、跳過或判定不寫的 message_id：之後的查詢跳過它們
_skip_ids: set[str] = set()


def _query(chat_table: str) -> str:
    # 文字長度先在資料庫粗篩一次（0～1 字又沒貼圖、動圖的一定寫不進去），省得每輪的名額都被它們佔掉
    return f"""
        SELECT r.message_id, r.guild_id, r.channel_id, r.thread_id, r.author_id,
               r.content, r.stickers, r.tenor_gifs, r.created_at,
               count(*) OVER () AS candidates
        FROM discord_messages_raw r
        WHERE r.created_at >= %(since)s AND r.created_at < %(until)s
          AND NOT r.is_deleted
          AND (char_length(btrim(r.content)) >= 2 OR r.stickers IS NOT NULL OR r.tenor_gifs IS NOT NULL)
          AND r.message_id <> ALL(%(skip)s::text[])
          AND NOT EXISTS (
              SELECT 1 FROM {chat_table} i WHERE i.metadata_->>'message_id' = r.message_id
          )
        ORDER BY r.created_at DESC
        LIMIT %(limit)s
    """


def _fetch_missing(since: datetime, until: datetime, limit: int, skip: list[str]) -> tuple[int, list[dict]]:
    """raw 有、聊天向量庫沒有的訊息（最新的 `limit` 則，回傳時排成由舊到新）；回傳 (符合條件的總則數, 列)。

    同步，丟執行緒跑。
    """
    with LLMServiceSettings().pgvector_cursor() as cur:
        cur.execute("SET LOCAL statement_timeout = '60s'")
        cur.execute(_query(HYBRID_RETRIEVAL_SETTINGS.chat_table()),
                    {"since": since, "until": until, "limit": limit, "skip": skip})
        columns = [d[0] for d in cur.description]
        rows = [dict(zip(columns, values)) for values in cur.fetchall()]
    rows.reverse()   # 排進佇列時照時間順序
    total = rows[0]["candidates"] if rows else 0
    return total, rows


def _json_list(value) -> list:
    """jsonb 欄位多半已解成 list；少數設定會回字串。"""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return []
    return value if isinstance(value, list) else []


def build_items(rows: list[dict]) -> tuple[list[dict], list[str]]:
    """raw 的列 → `store_chat` 寫入佇列的項目（欄位、組文字的規則都和即時寫入一樣）。

    回傳 (項目, 文字太短、不會寫的 message_id)。
    """
    items: list[dict] = []
    too_short: list[str] = []
    for row in rows:
        sticker_texts = [
            get_sticker_text(SimpleNamespace(id=int(s["id"]), name=s.get("name") or ""))
            for s in _json_list(row.get("stickers"))
        ]
        previews = [
            p for p in (store_chat.preview_text(g.get("title"), g.get("description"))
                        for g in _json_list(row.get("tenor_gifs")))
            if p
        ]
        text = store_chat.compose_persist_text(row.get("content") or "", sticker_texts, previews)
        if len(text) < store_chat.MIN_TEXT_LENGTH:
            too_short.append(row["message_id"])
            continue
        items.append({
            "message_id": row["message_id"],
            "text": text,
            "author_id": row["author_id"],
            # 即時寫入記的是 msg.channel.id：討論串裡的訊息記討論串本身。raw 表把它拆成上層頻道＋thread_id
            "channel_id": row.get("thread_id") or row["channel_id"],
            "guild_id": row.get("guild_id") or "",
            # 即時寫入是 Discord 的 created_at（UTC）.isoformat()；資料庫回來的時區看連線設定，統一轉回 UTC
            "timestamp": row["created_at"].astimezone(timezone.utc).isoformat(),
        })
    return items, too_short


async def run_once() -> int:
    """查一次 raw 有、聊天向量庫沒有的訊息，依開關排進寫入佇列（on）或只記 log（dry_run）；回傳排進幾則。"""
    mode = switches.current().chat_index_backfill_mode
    if mode == "off":
        return 0
    now = datetime.now(timezone.utc)
    until = max(now - timedelta(minutes=SETTLE_MINUTES), _STARTED_AT)
    total, rows = await asyncio.to_thread(
        _fetch_missing, now - timedelta(days=WINDOW_DAYS), until, BATCH_LIMIT, sorted(_skip_ids),
    )
    items, too_short = build_items(rows)
    _skip_ids.update(too_short)
    if mode == "dry_run":
        would_queue, skipped = store_chat.backfill_candidates(items)
        if total:
            logger.info("聊天向量庫補寫（dry_run，沒有寫）：近 %d 天 raw 有、向量庫沒有的約 %d 則；最新的 %d 則裡，"
                        "會排 %d、已在佇列或已記成寫過 %d、太短 %d（每輪都看同一批最新的，切到 on 才會往下補）",
                        WINDOW_DAYS, total, len(rows), len(would_queue), len(skipped), len(too_short))
        return 0
    queued, skipped = store_chat.enqueue_backfill(items)
    _skip_ids.update(queued)
    _skip_ids.update(skipped)
    if queued:
        logger.info("聊天向量庫補寫：近 %d 天約 %d 則待補，這輪排進 %d 則（%s ～ %s）message_id=%s",
                    WINDOW_DAYS, total, len(queued), items[0]["timestamp"], items[-1]["timestamp"], ",".join(queued))
    return len(queued)
