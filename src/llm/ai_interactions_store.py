"""ai_interactions：AI 插話的互動紀錄（普通 SQL 表，建在 pgvector 那個 Postgres）。

記每次「真的開口」的插話：被 @ 還是自發、什麼觸發的、它回的那段對話、它說了什麼。
獨立表 + 軟連結（存 id、不設 FK），日記與未來的好感度都讀這張表。

psycopg2 是同步——async caller（ambient/diary）請用 `asyncio.to_thread` 包，避免阻塞
event loop。所有函式 best-effort：失敗只記 log、不拋（互動紀錄不該拖垮插話/日記主流程）。
"""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from typing import Any, Optional


from sys_settings.llm_settings import LLMServiceSettings

logger = logging.getLogger("discord_bot")

_TABLE = "ai_interactions"
_settings: Optional[LLMServiceSettings] = None

# 共用 embedding 實例（與 RAG/印象卡同一顆 embed model）；lazy 初始化，sync 路徑用。
_embed_model: Any = None
_embed_init_lock = threading.Lock()

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
-- got_reply：**它講的這句話有沒有換到別人接話**。刻意不叫 followed_up——那個字面像「這筆
-- 已被跟進處理」，而且會跟 code 裡的 followup（**它**接續自己的話，主詞相反）撞名。
-- **刻意 nullable**：NULL＝未觀測（功能上線前的舊資料），FALSE＝已觀測但沒人接，TRUE＝有人接。
-- 鉤子的 k-NN 只吃非 NULL 的列 → 舊資料自動排除，不會被當成「全部都沒人接」而毒化統計。
-- 標籤比 reaction 好：reaction 負向樣本只有個位數，而「話被接下去」才是真人插話成功的定義。
ALTER TABLE {_TABLE} ADD COLUMN IF NOT EXISTS got_reply          BOOLEAN;
-- explore_sample：這筆是不是 ε-greedy 探索放行的（無視鉤子分數硬放行）。訓練時要能分層，
-- 否則探索樣本會被當成「鉤子看好的時機」而失去反例價值。
ALTER TABLE {_TABLE} ADD COLUMN IF NOT EXISTS explore_sample     BOOLEAN NOT NULL DEFAULT FALSE;
-- followup：這筆是不是「有人接它的話 → 它再回一句」。接續在 code 裡借用 directed 的回覆路徑，
-- 若不獨立記一欄，DB 裡就分不出「被 @」和「接續」。舊資料 FALSE 天然正確（當時沒這功能）。
ALTER TABLE {_TABLE} ADD COLUMN IF NOT EXISTS followup           BOOLEAN NOT NULL DEFAULT FALSE;
CREATE INDEX IF NOT EXISTS idx_ai_interactions_ts         ON {_TABLE} (ts DESC);
CREATE INDEX IF NOT EXISTS idx_ai_interactions_channel_ts ON {_TABLE} (channel_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_ai_interactions_author     ON {_TABLE} (trigger_author_id);
CREATE INDEX IF NOT EXISTS idx_ai_interactions_replymsg   ON {_TABLE} (reply_message_id);
"""

# embedding 欄需要 vector extension，獨立一段執行：缺 extension 時不該拖垮基礎建表。
# vector(1024) 對齊 pgvector_embed_dim（與 RAG/印象卡同一顆 embed model 的輸出維度）。
_EMBED_DDL = f"""
ALTER TABLE {_TABLE} ADD COLUMN IF NOT EXISTS embedding vector(1024);
CREATE INDEX IF NOT EXISTS idx_ai_interactions_embedding
  ON {_TABLE} USING hnsw (embedding vector_cosine_ops);
"""


def _get_settings() -> LLMServiceSettings:
    global _settings
    if _settings is None:
        _settings = LLMServiceSettings()
    return _settings


def _get_conn():
    return _get_settings().pgvector_connect()


def _get_embed_model():
    """lazy 取得共用 embedding 實例（與 RAG/印象卡同源）。沿用其他 store 的組裝路徑。"""
    global _embed_model
    if _embed_model is not None:
        return _embed_model
    with _embed_init_lock:
        if _embed_model is None:
            from llm.safe_llm_embedding import make_safe_llm_embedding
            from sys_settings.llm_settings import load_llm_runtime_config
            s = _get_settings()
            rc = load_llm_runtime_config(s.llm_runtime_model_path)
            _embed_model = make_safe_llm_embedding(settings=s, runtime_config=rc)
    return _embed_model


def _embed_text(text: Optional[str]) -> Optional[list]:
    """情境文字 → 向量（best-effort；失敗回 None、不拋，embedding 永遠不該拖垮主流程）。"""
    text = (text or "").strip()
    if not text:
        return None
    try:
        # 公開 API（與 context_retriever 一致）：內部走 _get_text_embedding + 事件/限流包裝
        return _get_embed_model().get_text_embedding(text)
    except Exception as exc:
        logger.warning("ai_interactions embed 失敗：%s", exc)
        return None


def _vec_literal(vec) -> Optional[str]:
    """list[float] → pgvector 文字字面值 '[...]'（給 SQL 的 %s::vector 用）。空向量回 None。"""
    if not vec:
        return None
    return "[" + ",".join(f"{float(x):.7g}" for x in vec) + "]"


def _situation_text(trigger_text: Optional[str], context_snippet: Optional[str]) -> str:
    """embedding 的對象＝「情境」：觸發文字 + 它在回的那段脈絡（語意召回靠它對齊當下場面）。"""
    parts = [p.strip() for p in (trigger_text, context_snippet) if p and p.strip()]
    return "\n".join(parts).strip()


def ensure_table() -> None:
    """建表 + 索引（idempotent）。啟動時呼叫一次。"""
    try:
        conn = _get_conn()
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(_DDL)
            # embedding 欄/索引獨立一段：缺 vector extension 時只記 warning，不拖垮基礎建表
            try:
                with conn:
                    with conn.cursor() as cur:
                        cur.execute(_EMBED_DDL)
            except Exception as exc:
                logger.warning(
                    "ai_interactions embedding 欄/索引建立略過（缺 vector extension？）：%s", exc
                )
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
    embedding: Optional[list] = None,
    explore_sample: bool = False,
    followup: bool = False,
    observe_reply: bool = False,
) -> None:
    """寫入一筆插話紀錄（sync；async caller 用 asyncio.to_thread 包）。

    embedding：當下情境的向量。caller 沒帶就現算（情境＝觸發+脈絡）；embed 不出來就存 NULL，
    純表示「這列暫不可語意召回」，不影響寫入。
    explore_sample：ε-greedy 探索放行的（鉤子分數沒過但硬放行）→ 訓練時分層用。
    followup：這筆是「有人接它的話 → 它再回」。與 directed（被 @/reply）互斥，三種來源在 DB
    裡分別是 directed=T / followup=T / 兩者皆 F（自發）。
    observe_reply=True → `got_reply` 初始化成 FALSE（＝「已納入觀測、目前還沒人接」），
    之後 `mark_got_reply` 偵測到有人接就翻成 TRUE。False 則留 NULL（不納入鉤子統計）。
    """
    _track_reply_id(reply_message_id)  # 記住這則訊息 id，之後它收到的反應才認得出是 bot 插話
    if embedding is None:
        embedding = _embed_text(_situation_text(trigger_text, context_snippet))
    emb_literal = _vec_literal(embedding)
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
                           reply_message_id, trace_id, embedding,
                           explore_sample, followup, got_reply)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::vector,%s,%s,%s)
                        """,
                        (
                            guild_id, channel_id, directed, trigger_kind, trigger_author_id,
                            trigger_message_id, trigger_text, context_snippet, reply_text,
                            reply_message_id, trace_id, emb_literal,
                            explore_sample, followup,
                            (False if observe_reply else None),
                        ),
                    )
        finally:
            conn.close()
    except Exception as exc:
        logger.warning("ai_interactions 寫入失敗 trace=%s：%s", trace_id, exc)


def mark_got_reply(
    reply_message_id: str, *, attempts: int = 4, retry_delay: float = 2.5
) -> bool:
    """標記「它這句話換到了別人接話」＝鉤子學習的正標籤。sync；async caller 用 to_thread。

    只翻已納入觀測的列（`got_reply IS NOT NULL`）；功能上線前的舊資料維持 NULL 不動，
    免得混入沒有對照組的樣本。

    **必須重試**：偵測到有人接話，可能發生在這筆插話紀錄 INSERT 完成**之前**——`record_interaction`
    要先算 embedding，耗時可達數秒，而實測有「插話送出後 1 秒就被接話」的真實案例（trace
    11:36:40 送出 / 11:36:41 接話 → 當時 UPDATE 影響 0 列，標籤靜默丟失）。rowcount=0 不是
    例外，不重試就永遠標不到、而且無聲無息。本函式跑在 to_thread 裡，sleep 不阻塞 event loop。

    回傳有沒有真的標到（caller 可忽略；失敗只影響一筆訓練樣本，不影響行為）。
    """
    for attempt in range(max(1, attempts)):
        try:
            conn = _get_conn()
            try:
                with conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            f"""UPDATE {_TABLE} SET got_reply = TRUE
                                WHERE reply_message_id = %s AND got_reply IS NOT NULL""",
                            (str(reply_message_id),),
                        )
                        if cur.rowcount > 0:
                            return True
            finally:
                conn.close()
        except Exception as exc:
            logger.debug("ai_interactions got_reply 標記失敗 mid=%s：%s", reply_message_id, exc)
        if attempt < attempts - 1:
            time.sleep(retry_delay)  # 等 INSERT（含 embedding）落地
    logger.info(
        "ai_interactions got_reply 標記不到 mid=%s（重試 %d 次；該筆可能未納入觀測或寫入失敗）",
        reply_message_id, attempts,
    )
    return False


def fetch_reply_rate_stats(
    situation_text: str, *, k: int = 20, max_distance: float = 0.50
) -> tuple[int, float]:
    """k-NN：過去「語意相近的情境」下自發插話，被接話的比例。回 (樣本數, 比率)。

    這是鉤子的軟特徵——不是 LLM 推理，只是最近鄰查詢。只吃 `got_reply IS NOT NULL`（已觀測）
    且 `directed = FALSE AND followup = FALSE`（**純自發**）的列：被 @ 本來就有人在跟它講話，
    接續則是對話已在來回，兩者混進來都會把比率灌高。
    撈不到 / 失敗回 (0, 0.0)，caller 據此決定不使用此特徵（而非當成 0 分）。
    """
    vec = _vec_literal(_embed_text(situation_text))
    if not vec:
        return (0, 0.0)
    try:
        conn = _get_conn()
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        f"""
                        SELECT got_reply, (embedding <=> %s::vector) AS distance
                        FROM {_TABLE}
                        WHERE embedding IS NOT NULL
                          AND got_reply IS NOT NULL
                          AND directed = FALSE
                          AND followup = FALSE
                        ORDER BY embedding <=> %s::vector
                        LIMIT %s
                        """,
                        (vec, vec, k),
                    )
                    rows = [
                        r for r in cur.fetchall()
                        if r[1] is not None and float(r[1]) <= max_distance
                    ]
        finally:
            conn.close()
    except Exception as exc:
        logger.debug("ai_interactions followup 統計失敗：%s", exc)
        return (0, 0.0)
    if not rows:
        return (0, 0.0)
    return (len(rows), sum(1 for r in rows if r[0]) / len(rows))


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


def fetch_similar_positive(
    situation_text: str, *, k: int = 8, max_distance: float = 0.45, min_positive: int = 1
) -> list[dict[str, Any]]:
    """撈與當下情境語意相近、且被群裡按過正向反應（且無負向）的舊插話＝「打中過的好回答」。

    回 [{trigger_text, context_snippet, reply_text, reply_message_id, positive_reactions,
        directed, distance}]，按 cosine 距離由近到遠、且只留 distance <= max_distance 的。sync。
    用途：當「風格靈感」注入 ambient（學味道、別照抄），不是事實來源。
    """
    lit = _vec_literal(_embed_text(situation_text))
    if lit is None:
        return []
    rows: list[dict[str, Any]] = []
    try:
        conn = _get_conn()
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        f"""
                        SELECT trigger_text, context_snippet, reply_text, reply_message_id,
                               positive_reactions, directed, (embedding <=> %s::vector) AS distance
                        FROM {_TABLE}
                        WHERE embedding IS NOT NULL
                          AND positive_reactions >= %s
                          AND negative_reactions = 0
                        ORDER BY embedding <=> %s::vector
                        LIMIT %s
                        """,
                        (lit, min_positive, lit, k),
                    )
                    for r in cur.fetchall():
                        dist = r[6]
                        if dist is None or float(dist) > max_distance:
                            continue
                        rows.append({
                            "trigger_text": r[0], "context_snippet": r[1], "reply_text": r[2],
                            "reply_message_id": r[3], "positive_reactions": r[4],
                            "directed": r[5], "distance": float(dist),
                        })
        finally:
            conn.close()
    except Exception as exc:
        logger.warning("ai_interactions 相似召回失敗：%s", exc)
    return rows


def backfill_embeddings(*, batch: int = 50, max_rows: Optional[int] = None) -> int:
    """回填 embedding IS NULL 且有情境文字的舊列（idempotent、best-effort）。

    以 id 為游標往前走——即使某筆 embed 失敗也不會回頭重撈、不會卡死。啟動時於背景執行緒呼叫。
    回傳本輪成功回填筆數。
    """
    done = 0
    last_id = 0
    try:
        conn = _get_conn()
        conn.autocommit = True  # 每筆 UPDATE 即時 commit，簡化交易、可隨時中止
        try:
            while True:
                with conn.cursor() as cur:
                    cur.execute(
                        f"""SELECT id, trigger_text, context_snippet FROM {_TABLE}
                            WHERE embedding IS NULL
                              AND COALESCE(trigger_text, context_snippet, '') <> ''
                              AND id > %s
                            ORDER BY id LIMIT %s""",
                        (last_id, batch),
                    )
                    fetched = cur.fetchall()
                if not fetched:
                    break
                for rid, tt, cs in fetched:
                    last_id = rid  # 游標前進（這筆 embed 失敗也不再重撈）
                    lit = _vec_literal(_embed_text(_situation_text(tt, cs)))
                    if lit is None:
                        continue
                    with conn.cursor() as cur2:
                        cur2.execute(
                            f"UPDATE {_TABLE} SET embedding=%s::vector WHERE id=%s", (lit, rid)
                        )
                    done += 1
                    if max_rows is not None and done >= max_rows:
                        logger.info("ai_interactions embedding 回填達上限 %d，先停", max_rows)
                        return done
            logger.info("ai_interactions embedding 回填完成：本輪 %d 筆", done)
        finally:
            conn.close()
    except Exception as exc:
        logger.warning("ai_interactions embedding 回填中止（已完成 %d）：%s", done, exc)
    return done
