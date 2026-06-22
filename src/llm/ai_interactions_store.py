"""ai_interactions：AI 插話的互動紀錄（普通 SQL 表，建在 pgvector 那個 Postgres）。

記每次「真的開口」的插話：被 @ 還是自發、什麼觸發的、它回的那段對話、它說了什麼。
獨立表 + 軟連結（存 id、不設 FK），日記與未來的好感度都讀這張表。

psycopg2 是同步——async caller（ambient/diary）請用 `asyncio.to_thread` 包，避免阻塞
event loop。所有函式 best-effort：失敗只記 log、不拋（互動紀錄不該拖垮插話/日記主流程）。
"""
from __future__ import annotations

import logging
from collections import deque
from typing import Any, Optional

import psycopg2

from sys_settings.llm_settings import LLMServiceSettings

logger = logging.getLogger("discord_bot")

_TABLE = "ai_interactions"
_settings: Optional[LLMServiceSettings] = None

# 追蹤「最近 bot 自己插話的訊息 id」——反應事件先查這個記憶體集合，命中才打 DB，
# 避免整個 server 每個反應都對 DB 做無謂 UPDATE。重啟後重填（只影響重啟前舊訊息的反應）。
_RECENT_REPLY_ORDER: "deque[str]" = deque(maxlen=2000)
_RECENT_REPLY_IDS: set[str] = set()


def _track_reply_id(mid: Optional[str]) -> None:
    if not mid or mid in _RECENT_REPLY_IDS:
        return
    if len(_RECENT_REPLY_ORDER) == _RECENT_REPLY_ORDER.maxlen:
        _RECENT_REPLY_IDS.discard(_RECENT_REPLY_ORDER[0])  # 即將被擠出的最舊一筆
    _RECENT_REPLY_ORDER.append(mid)
    _RECENT_REPLY_IDS.add(mid)


def is_tracked_reply(message_id: str) -> bool:
    """這個訊息 id 是不是最近 bot 自己的插話（反應 handler 先用這個過濾，命中才打 DB）。"""
    return message_id in _RECENT_REPLY_IDS

_DDL = f"""
CREATE TABLE IF NOT EXISTS {_TABLE} (
  id                 BIGSERIAL PRIMARY KEY,
  ts                 TIMESTAMPTZ NOT NULL DEFAULT now(),
  guild_id           TEXT NOT NULL,
  channel_id         TEXT NOT NULL,
  directed           BOOLEAN NOT NULL,
  trigger_kind       TEXT NOT NULL,
  trigger_author_id  TEXT,
  trigger_message_id TEXT,
  trigger_text       TEXT,
  context_snippet    TEXT,
  reply_text         TEXT NOT NULL,
  reply_message_id   TEXT,
  trace_id           TEXT,
  reaction_count     INT NOT NULL DEFAULT 0,
  positive_reactions INT NOT NULL DEFAULT 0,
  negative_reactions INT NOT NULL DEFAULT 0
);
-- 既有表補欄（idempotent；表先前已建、無這三欄時用）
ALTER TABLE {_TABLE} ADD COLUMN IF NOT EXISTS reaction_count     INT NOT NULL DEFAULT 0;
ALTER TABLE {_TABLE} ADD COLUMN IF NOT EXISTS positive_reactions INT NOT NULL DEFAULT 0;
ALTER TABLE {_TABLE} ADD COLUMN IF NOT EXISTS negative_reactions INT NOT NULL DEFAULT 0;
CREATE INDEX IF NOT EXISTS idx_ai_interactions_ts         ON {_TABLE} (ts DESC);
CREATE INDEX IF NOT EXISTS idx_ai_interactions_channel_ts ON {_TABLE} (channel_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_ai_interactions_author     ON {_TABLE} (trigger_author_id);
CREATE INDEX IF NOT EXISTS idx_ai_interactions_replymsg   ON {_TABLE} (reply_message_id);
"""


def _get_settings() -> LLMServiceSettings:
    global _settings
    if _settings is None:
        _settings = LLMServiceSettings()
    return _settings


def _get_conn():
    s = _get_settings()
    return psycopg2.connect(
        host=s.pgvector_host,
        port=s.pgvector_port,
        dbname=s.pgvector_db,
        user=s.pgvector_user,
        password=s.pgvector_password,
    )


def ensure_table() -> None:
    """建表 + 索引（idempotent）。啟動時呼叫一次。"""
    try:
        conn = _get_conn()
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(_DDL)
        finally:
            conn.close()
        logger.info("ai_interactions 表已就緒")
    except Exception as exc:
        logger.error("ai_interactions 建表失敗：%s", exc, exc_info=True)


def record_interaction(
    *,
    guild_id: str,
    channel_id: str,
    directed: bool,
    trigger_kind: str,
    trigger_author_id: Optional[str],
    trigger_message_id: Optional[str],
    trigger_text: Optional[str],
    context_snippet: Optional[str],
    reply_text: str,
    reply_message_id: Optional[str],
    trace_id: Optional[str],
) -> None:
    """寫入一筆插話紀錄（sync；async caller 用 asyncio.to_thread 包）。"""
    _track_reply_id(reply_message_id)  # 記住這則訊息 id，之後它收到的反應才認得出是 bot 插話
    try:
        conn = _get_conn()
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        f"""
                        INSERT INTO {_TABLE}
                          (guild_id, channel_id, directed, trigger_kind, trigger_author_id,
                           trigger_message_id, trigger_text, context_snippet, reply_text,
                           reply_message_id, trace_id)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        """,
                        (
                            guild_id, channel_id, directed, trigger_kind, trigger_author_id,
                            trigger_message_id, trigger_text, context_snippet, reply_text,
                            reply_message_id, trace_id,
                        ),
                    )
        finally:
            conn.close()
    except Exception as exc:
        logger.warning("ai_interactions 寫入失敗 trace=%s：%s", trace_id, exc)


def note_reaction(message_id: str, emoji_name: str, emoji_id: Any, action: str) -> None:
    """某則 bot 插話收到/移除反應 → 依 emoji 分類更新該筆的正/負向計數。

    caller 應先用 is_tracked_reply() 確認是 bot 插話再呼叫（避免對非 bot 訊息打 DB）。
    正向＝agree/laugh、負向＝negative、其餘只計入 reaction_count。sync；async caller 用 to_thread。
    """
    try:
        from llm.reaction_classifier import classify_reaction
        cat = classify_reaction(emoji_name, str(emoji_id) if emoji_id else None)
    except Exception:
        cat = "neutral"
    delta = 1 if action == "add" else -1
    pos = delta if cat in ("agree", "laugh") else 0
    neg = delta if cat == "negative" else 0
    try:
        conn = _get_conn()
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        f"""UPDATE {_TABLE}
                            SET reaction_count     = GREATEST(reaction_count + %s, 0),
                                positive_reactions = GREATEST(positive_reactions + %s, 0),
                                negative_reactions = GREATEST(negative_reactions + %s, 0)
                            WHERE reply_message_id = %s""",
                        (delta, pos, neg, str(message_id)),
                    )
        finally:
            conn.close()
    except Exception as exc:
        logger.warning("ai_interactions 反應更新失敗 msg=%s：%s", message_id, exc)


def fetch_recent(
    channel_id: str, *, hours: int = 24, limit: int = 200
) -> list[dict[str, Any]]:
    """撈某頻道過去 hours 小時的插話紀錄（回時序：舊→新）。sync；async caller 用 to_thread。"""
    rows: list[dict[str, Any]] = []
    try:
        conn = _get_conn()
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        f"""
                        SELECT ts, directed, trigger_kind, trigger_author_id,
                               trigger_text, context_snippet, reply_text,
                               positive_reactions, reaction_count
                        FROM {_TABLE}
                        WHERE channel_id = %s
                          AND ts > now() - make_interval(hours => %s)
                        ORDER BY ts DESC
                        LIMIT %s
                        """,
                        (channel_id, hours, limit),
                    )
                    for r in cur.fetchall():
                        rows.append({
                            "ts": r[0], "directed": r[1], "trigger_kind": r[2],
                            "trigger_author_id": r[3], "trigger_text": r[4],
                            "context_snippet": r[5], "reply_text": r[6],
                            "positive_reactions": r[7], "reaction_count": r[8],
                        })
        finally:
            conn.close()
    except Exception as exc:
        logger.warning("ai_interactions 讀取失敗 channel=%s：%s", channel_id, exc)
    rows.reverse()  # newest-first → 時序
    return rows
