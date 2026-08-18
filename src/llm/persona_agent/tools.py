"""Persona agent 的四支唯讀工具（function-calling 用）。

設計原則：

1. **全部唯讀**：agent 只能查，寫入永遠由程式碼（M3 的驗證層）執行。
2. **白名單強制**：每支工具都對 `user_id` 檢查 `ToolContext.allowed_ids`，避免 agent
   自行擴大查詢對象。`get_conversation` 檢查的是**錨點訊息的作者**——只能還原白名單
   使用者發言的現場，不能拿來瀏覽任意對話。
3. **上限由程式碼夾**：`days` / `limit` / 視窗大小超過就夾住並在回傳的 `clamped`
   欄位註明，**不報錯**（模型看得到自己被夾了，可以調整策略）。
4. **`guild_id` 一律帶上**：正確性不能靠「資料剛好乾淨」。2026-08-18 清掉的 12 筆
   `guild_id='0'` 殭屍列就是反例——漏帶條件會撈到數個月前的舊描述當 diff 基準。
5. **回傳一律 JSON 字串**：例外 catch 成 `{"error": ...}` 交還模型自行修正重試，
   不讓單一工具失敗中斷整個 loop。
6. **不 import discord**：純 SQL 層，職責乾淨、日後好搬。

查詢執行器 `fetch` 是可注入的 callable，預設打真的 pgvector；單元測試注入假的，
讓夾取／白名單／`guild_id` 必帶這些邏輯不碰 DB 就能驗。
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterable, Optional, Sequence

from sys_settings.pgvector_settings import HYBRID_RETRIEVAL_SETTINGS
from sys_settings.time_settings import APP_TZ


logger = logging.getLogger("discord_bot")

# ── 程式碼端硬上限（handoff 第 4 節）──────────────────────────────────────
MAX_DAYS = 90
MAX_MESSAGE_LIMIT = 120
MAX_SEARCH_LIMIT = 50
MAX_CONVERSATION_WINDOW = 30

DEFAULT_MESSAGE_DAYS = 7
DEFAULT_MESSAGE_LIMIT = 60
DEFAULT_SEARCH_DAYS = 90
DEFAULT_SEARCH_LIMIT = 50
DEFAULT_CONVERSATION_WINDOW = 15

FetchFn = Callable[[str, Sequence[Any]], list[tuple]]


def _default_fetch(sql: str, params: Sequence[Any]) -> list[tuple]:
    """預設查詢執行器：打真的 pgvector（同步，呼叫端負責丟 executor）。

    連線沿用 `personality_extractor._get_db_conn()`——專案裡已經有七處各自
    `psycopg2.connect(...)`，不再加第八份。延後 import 讓本模組在無 DB 驅動的
    環境也匯入得起來（單元測試注入假的 fetch，不會走到這裡）。
    """
    from llm.personality_extractor import _get_db_conn

    conn = _get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, list(params))
            return cur.fetchall()
    finally:
        conn.close()


@dataclass(frozen=True)
class ToolContext:
    """一次 agent 執行的共用上下文。

    `allowed_ids` 是本次樣本清單；工具層據此拒絕清單外的查詢。做成顯式參數（而非
    模組層全域）是為了讓測試彼此不污染，也讓「忘記帶白名單」變成 TypeError 而非
    靜默放行。
    """

    guild_id: int
    allowed_ids: frozenset[str]
    fetch: FetchFn = _default_fetch

    @classmethod
    def build(
        cls,
        *,
        guild_id: int,
        allowed_ids: Iterable[str],
        fetch: Optional[FetchFn] = None,
    ) -> "ToolContext":
        return cls(
            guild_id=int(guild_id),
            allowed_ids=frozenset(str(uid) for uid in allowed_ids),
            fetch=fetch or _default_fetch,
        )


# ── 內部工具 ────────────────────────────────────────────────────────────
def _chat_table() -> str:
    return HYBRID_RETRIEVAL_SETTINGS.chat_table()


def _profile_table() -> str:
    return HYBRID_RETRIEVAL_SETTINGS.source_table(
        "member_profile", default="discord_member_profiles_index"
    )


def _dump(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _error(message: str) -> str:
    """工具層錯誤一律回 JSON 給模型，讓它自行修正重試，而不是拋例外中斷 loop。"""
    return _dump({"error": message})


def _clamp(value: Any, *, default: int, maximum: int, minimum: int = 1) -> tuple[int, bool]:
    """夾取數值參數。回傳 (夾後值, 是否被夾)。無法解析時退回 default。"""
    try:
        raw = int(value)
    except (TypeError, ValueError):
        return default, False
    if raw < minimum:
        return minimum, True
    if raw > maximum:
        return maximum, True
    return raw, False


def _check_allowed(ctx: ToolContext, user_id: Any) -> Optional[str]:
    """白名單檢查。通過回 None，否則回錯誤 JSON 字串。"""
    uid = str(user_id or "").strip()
    if not uid:
        return _error("user_id 不可為空")
    if uid not in ctx.allowed_ids:
        return _error(f"user_id={uid} 不在本次樣本清單內，拒絕查詢")
    return None


def _cutoff_iso(days: int) -> str:
    """算 N 天前的時間界線，回傳與 DB 內同格式的 ISO 字串。

    **為什麼用字串比較而不是 `::timestamptz` 轉型**：轉型是 STABLE（依賴 TimeZone
    設定），無法建表達式索引；而聊天表 273,780 筆全部是 `+00:00` 的 ISO 字串，
    **字典序 == 時間序**（少數沒有微秒的列，`+` < `.` 讓它排在同秒有微秒者之前，
    方向仍正確）。改字串比較後 `(author_id, timestamp)` / `(channel_id, timestamp)`
    的表達式索引才吃得到——實測全表掃描 752~1,479ms 降到毫秒級。現有
    `personality_extractor.fetch_recent_messages` 也是字串比較，寫法一致。

    索引由維運手動建立（指令記在 handoff），刻意不寫進程式碼。
    """
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def _clean_text_for_extraction(text: str) -> str:
    """沿用 production 萃取的文字清理（自訂表情轉語意、去 URL、mention 轉 @某人）。

    **不是可有可無的**：本 agent 的 system prompt 直接沿用萃取那份，裡面整段在教
    「`:xxx:` 是自訂表情、不可逐字引用」。若這裡回傳原始文字，模型看到的是
    `<:貓咪哭哭:123456>` 而不是 `:貓咪哭哭:`——共用了規則卻沒共用前處理，等於讓
    prompt 對模型說謊。URL 也一樣：萃取刻意整段移除（對人格分析無用、且模型容易
    誤判成「愛分享資訊」），一條網址還要吃掉五十幾個字元的 context。
    """
    from llm.personality_extractor import _clean_text_for_extraction as _clean

    return _clean(text)


def _fmt_ts(raw: str) -> str:
    """`2026-08-16T19:59:14.082000+00:00` → `08-16 19:59`（台北時間）。

    砍掉年份、秒、微秒與時區尾綴：模型判斷「他都半夜發言」只需要到分鐘，
    但完整字串每則要吃掉十幾個 token。轉台北時區是因為群組作息以本地時間為準，
    也與 chat_history 的 `[HH:MM]` 呈現一致。
    """
    try:
        return datetime.fromisoformat(raw).astimezone(APP_TZ).strftime("%m-%d %H:%M")
    except (TypeError, ValueError):
        return raw or ""


def _rows_to_messages(
    rows: list[tuple], *, with_author: bool = False
) -> list[dict[str, str]]:
    """(message_id, channel_id, timestamp, author_id, text) → 精簡 dict 列表。

    **刻意只留必要欄位**：實測 200 則訊息帶完整欄位是 35,103 字元（約 1 萬 token），
    其中大半是每則重複的 channel_id、author_id 與微秒級時間戳。單人查詢時作者恆定、
    頻道幾乎恆定，留著只是在燒 context——而 context 是共用資源，被並行請求擠壓時
    會直接觸發 `Context size has been exceeded`。

    `with_author=True` 只給 `get_conversation` 用：那裡的作者會變，是判讀互動的關鍵。
    """
    out: list[dict[str, str]] = []
    for r in rows:
        item = {
            "id": r[0] or "",
            "ts": _fmt_ts(r[2] or ""),
            "text": _clean_text_for_extraction(r[4] or ""),
        }
        if with_author:
            item["author_id"] = r[3] or ""
        out.append(item)
    return out


_MESSAGE_COLUMNS = (
    "metadata_->>'message_id', metadata_->>'channel_id', "
    "metadata_->>'timestamp', metadata_->>'author_id', text"
)


def _parse_personality(raw_text: str) -> str:
    """從 `[Auto Personality]\\nalias: x\\npersonality: y` 取出 y。"""
    for line in (raw_text or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("personality:"):
            return stripped[len("personality:"):].strip()
    return (raw_text or "").strip()


# ── 工具 1：讀現有人格描述（diff 的基準）─────────────────────────────────
def get_current_persona(ctx: ToolContext, *, user_id: Any) -> str:
    """讀該使用者目前的人格描述，供 agent 產出 diff 時當基準。

    M1 只讀 production 的 `auto_personality`；M3 接上版本表後改為「有自己的版本就讀
    自己的最新版，否則退回 production」，並把來源記進 `based_on`。
    """
    rejected = _check_allowed(ctx, user_id)
    if rejected:
        return rejected
    uid = str(user_id).strip()

    sql = f"""
        SELECT text, metadata_->>'alias', metadata_->>'last_extracted_at'
        FROM {_profile_table()}
        WHERE metadata_->>'profile_kind' = 'auto_personality'
          AND metadata_->>'guild_id' = %s
          AND metadata_->>'author_id' = %s
        ORDER BY id DESC
        LIMIT 1
    """
    try:
        rows = ctx.fetch(sql, (str(ctx.guild_id), uid))
    except Exception as exc:
        logger.warning("get_current_persona 查詢失敗 uid=%s: %s", uid, exc)
        return _error(f"查詢失敗：{type(exc).__name__}")

    if not rows:
        return _dump({"user_id": uid, "persona_text": None, "source": None})
    text, alias, updated_at = rows[0]
    return _dump({
        "user_id": uid,
        "alias": alias or "",
        "persona_text": _parse_personality(text or ""),
        "updated_at": updated_at or "",
        "source": "production_auto_personality",
    })


# ── 工具 2：撈某人最近的發言 ────────────────────────────────────────────
def get_messages(
    ctx: ToolContext,
    *,
    user_id: Any,
    days: Any = DEFAULT_MESSAGE_DAYS,
    channel_id: Optional[str] = None,
    limit: Any = DEFAULT_MESSAGE_LIMIT,
) -> str:
    """撈該使用者最近 N 天的發言（時間由舊到新）。

    **注意**：本群訊息平均僅 11~38 字，單獨看某人的發言多半是脫離語境的碎片
    （「你開他」「剩我純心賞」）。要判斷語氣與人格，請對關鍵幾則再呼叫
    `get_conversation` 還原現場，不要只憑這裡的碎片下結論。
    """
    rejected = _check_allowed(ctx, user_id)
    if rejected:
        return rejected
    uid = str(user_id).strip()

    days_value, days_clamped = _clamp(days, default=DEFAULT_MESSAGE_DAYS, maximum=MAX_DAYS)
    limit_value, limit_clamped = _clamp(
        limit, default=DEFAULT_MESSAGE_LIMIT, maximum=MAX_MESSAGE_LIMIT
    )

    where = [
        "metadata_->>'doc_type' = 'discord_chat'",
        "metadata_->>'author_id' = %s",
        "metadata_->>'timestamp' >= %s",
    ]
    params: list[Any] = [uid, _cutoff_iso(days_value)]
    if channel_id:
        where.append("metadata_->>'channel_id' = %s")
        params.append(str(channel_id))

    # 先取「最近 N 則」再由呼叫端轉回正序：避免上限截掉的是新訊息而非舊訊息
    sql = f"""
        SELECT {_MESSAGE_COLUMNS}
        FROM {_chat_table()}
        WHERE {' AND '.join(where)}
        ORDER BY metadata_->>'timestamp' DESC
        LIMIT %s
    """
    params.append(limit_value)

    try:
        rows = ctx.fetch(sql, params)
    except Exception as exc:
        logger.warning("get_messages 查詢失敗 uid=%s: %s", uid, exc)
        return _error(f"查詢失敗：{type(exc).__name__}")

    messages = [m for m in _rows_to_messages(rows) if m["text"]]
    messages.reverse()
    return _dump({
        "user_id": uid,
        "days": days_value,
        "limit": limit_value,
        "count": len(messages),
        "clamped": {"days": days_clamped, "limit": limit_clamped},
        "messages": messages,
    })


# ── 工具 3：關鍵詞追查 ──────────────────────────────────────────────────
def search_messages(
    ctx: ToolContext,
    *,
    user_id: Any,
    keyword: str,
    days: Any = DEFAULT_SEARCH_DAYS,
    limit: Any = DEFAULT_SEARCH_LIMIT,
) -> str:
    """在該使用者的發言中做字面搜尋，供 agent 追查特定線索（如新舊描述衝突的佐證）。"""
    rejected = _check_allowed(ctx, user_id)
    if rejected:
        return rejected
    uid = str(user_id).strip()

    needle = (keyword or "").strip()
    if not needle:
        return _error("keyword 不可為空")

    days_value, days_clamped = _clamp(days, default=DEFAULT_SEARCH_DAYS, maximum=MAX_DAYS)
    limit_value, limit_clamped = _clamp(
        limit, default=DEFAULT_SEARCH_LIMIT, maximum=MAX_SEARCH_LIMIT
    )

    # ILIKE 走字面比對；`\` `%` `_` 先跳脫，避免關鍵詞裡的萬用字元擴大命中範圍
    escaped = needle.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    sql = f"""
        SELECT {_MESSAGE_COLUMNS}
        FROM {_chat_table()}
        WHERE metadata_->>'doc_type' = 'discord_chat'
          AND metadata_->>'author_id' = %s
          AND metadata_->>'timestamp' >= %s
          AND text ILIKE %s
        ORDER BY metadata_->>'timestamp' DESC
        LIMIT %s
    """
    params = [uid, _cutoff_iso(days_value), f"%{escaped}%", limit_value]

    try:
        rows = ctx.fetch(sql, params)
    except Exception as exc:
        logger.warning("search_messages 查詢失敗 uid=%s: %s", uid, exc)
        return _error(f"查詢失敗：{type(exc).__name__}")

    messages = _rows_to_messages(rows)
    messages.reverse()
    return _dump({
        "user_id": uid,
        "keyword": needle,
        "days": days_value,
        "limit": limit_value,
        "count": len(messages),
        "clamped": {"days": days_clamped, "limit": limit_clamped},
        "messages": messages,
    })


# ── 工具 4：還原對話現場（勝負手）────────────────────────────────────────
def get_conversation(
    ctx: ToolContext,
    *,
    around_msg_id: str,
    before: Any = DEFAULT_CONVERSATION_WINDOW,
    after: Any = DEFAULT_CONVERSATION_WINDOW,
    channel_id: Optional[str] = None,
) -> str:
    """還原某則訊息前後的完整對話（含其他人的發言）。

    存在理由：人格訊號在**互動**裡，不在單句裡。同樣一句「你也太廢」，前面是隊友剛
    失誤就是損友互虧，前面是有人在講難過的事就是白目——句子相同、結論相反。少了這支
    工具，agent 只能看碎片，不是寫空話就是腦補；而且 `evidence_msg_ids` 的稽核價值
    也會一併失效（人工翻回去看到孤句，同樣判斷不了對錯）。

    **白名單套在錨點訊息的作者身上**：只能還原樣本使用者發言的現場，不能瀏覽任意對話。
    回傳會包含旁人的發言——這與現有 pipeline 餵給模型的交錯 chat_log 屬同等級，
    不是新增的暴露面。
    """
    anchor_id = str(around_msg_id or "").strip()
    if not anchor_id:
        return _error("around_msg_id 不可為空")

    before_value, before_clamped = _clamp(
        before, default=DEFAULT_CONVERSATION_WINDOW, maximum=MAX_CONVERSATION_WINDOW, minimum=0
    )
    after_value, after_clamped = _clamp(
        after, default=DEFAULT_CONVERSATION_WINDOW, maximum=MAX_CONVERSATION_WINDOW, minimum=0
    )

    anchor_sql = f"""
        SELECT {_MESSAGE_COLUMNS}
        FROM {_chat_table()}
        WHERE metadata_->>'doc_type' = 'discord_chat'
          AND metadata_->>'message_id' = %s
        LIMIT 1
    """
    try:
        anchor_rows = ctx.fetch(anchor_sql, (anchor_id,))
    except Exception as exc:
        logger.warning("get_conversation 錨點查詢失敗 msg=%s: %s", anchor_id, exc)
        return _error(f"查詢失敗：{type(exc).__name__}")

    if not anchor_rows:
        return _error(f"找不到 message_id={anchor_id}")

    anchor = _rows_to_messages(anchor_rows, with_author=True)[0]
    anchor_channel = anchor_rows[0][1] or ""
    anchor_ts = anchor_rows[0][2] or ""  # 視窗查詢用未格式化的原始時間戳比大小
    rejected = _check_allowed(ctx, anchor["author_id"])
    if rejected:
        return rejected
    if channel_id and str(channel_id) != anchor_channel:
        return _error(
            f"channel_id={channel_id} 與 message_id={anchor_id} 實際所在頻道不符"
        )

    window_sql = f"""
        SELECT {_MESSAGE_COLUMNS}
        FROM {_chat_table()}
        WHERE metadata_->>'doc_type' = 'discord_chat'
          AND metadata_->>'channel_id' = %s
          AND metadata_->>'timestamp' {{op}} %s
        ORDER BY metadata_->>'timestamp' {{order}}
        LIMIT %s
    """
    try:
        before_rows = (
            ctx.fetch(
                window_sql.format(op="<", order="DESC"),
                (anchor_channel, anchor_ts, before_value),
            )
            if before_value
            else []
        )
        after_rows = (
            ctx.fetch(
                window_sql.format(op=">", order="ASC"),
                (anchor_channel, anchor_ts, after_value),
            )
            if after_value
            else []
        )
    except Exception as exc:
        logger.warning("get_conversation 視窗查詢失敗 msg=%s: %s", anchor_id, exc)
        return _error(f"查詢失敗：{type(exc).__name__}")

    earlier = _rows_to_messages(before_rows, with_author=True)
    earlier.reverse()
    anchor_line = dict(anchor)
    anchor_line["is_anchor"] = True
    conversation = earlier + [anchor_line] + _rows_to_messages(after_rows, with_author=True)

    return _dump({
        "around_msg_id": anchor_id,
        "channel": anchor_channel,
        "before": before_value,
        "after": after_value,
        "count": len(conversation),
        "clamped": {"before": before_clamped, "after": after_clamped},
        "messages": conversation,
    })


# ── function-calling 宣告與派發 ─────────────────────────────────────────
# 描述文字是**寫給模型看的**，不是註解——它決定模型會不會在對的時機呼叫對的工具。
# 特別是 get_conversation：不寫清楚「碎片沒有上下文就讀不出語氣」，模型會懶得用它。

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_current_persona",
            "description": "讀取該使用者目前的人格描述，作為本次 diff 的比對基準。應該最先呼叫。",
            "parameters": {
                "type": "object",
                "properties": {"user_id": {"type": "string", "description": "要分析的使用者 ID"}},
                "required": ["user_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_messages",
            "description": (
                "取得該使用者最近 N 天的發言（時間由舊到新）。"
                "這支是用來**找線索**的，不是用來讀完全部——本群訊息很短，"
                "單看某人自己的發言多半是脫離語境的碎片，看得出他講什麼、看不出他什麼語氣。"
                "預設筆數已足夠挑出值得深究的幾則；把 limit 開到最大只會吃光 context，"
                "讓後面的 get_conversation 沒有空間。判斷語氣一律靠 get_conversation。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                    "days": {"type": "integer", "description": f"回溯天數，預設 {DEFAULT_MESSAGE_DAYS}，上限 {MAX_DAYS}"},
                    "limit": {"type": "integer", "description": f"最多幾則，上限 {MAX_MESSAGE_LIMIT}"},
                    "channel_id": {"type": "string", "description": "限定頻道，通常不需要"},
                },
                "required": ["user_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_messages",
            "description": (
                "在該使用者的發言中做關鍵詞搜尋。用於追查特定線索——"
                "例如既有描述說他「愛講某個梗」，用這支確認他最近還講不講。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                    "keyword": {"type": "string", "description": "要搜尋的字串（字面比對）"},
                    "days": {"type": "integer", "description": f"回溯天數，上限 {MAX_DAYS}"},
                    "limit": {"type": "integer", "description": f"上限 {MAX_SEARCH_LIMIT}"},
                },
                "required": ["user_id", "keyword"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_conversation",
            "description": (
                "還原某則訊息前後的完整對話，包含其他人的發言。"
                "**這是判斷語氣的唯一方法**：同一句「你也太廢」，前面是隊友剛失誤就是損友互虧，"
                "前面是有人在講難過的事就是白目——句子一樣、結論相反。"
                "任何關於語氣、態度、人際關係的結論，都必須先用這支工具看過現場。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "around_msg_id": {"type": "string", "description": "要還原現場的那則訊息 ID"},
                    "before": {"type": "integer", "description": f"往前幾則，上限 {MAX_CONVERSATION_WINDOW}"},
                    "after": {"type": "integer", "description": f"往後幾則，上限 {MAX_CONVERSATION_WINDOW}"},
                },
                "required": ["around_msg_id"],
            },
        },
    },
]

_TOOL_FUNCS: dict[str, Callable[..., str]] = {
    "get_current_persona": get_current_persona,
    "get_messages": get_messages,
    "search_messages": search_messages,
    "get_conversation": get_conversation,
}


def dispatch(ctx: ToolContext, *, name: str, arguments: Any) -> str:
    """依模型指定的工具名與參數執行，回傳 JSON 字串。

    所有失敗（工具不存在、arguments 不是合法 JSON、參數名不符）都轉成
    `{"error": ...}` 回給模型自行修正，**不拋例外** —— agent loop 不該因為模型
    填錯一個參數就整個中斷。
    """
    fn = _TOOL_FUNCS.get(name)
    if fn is None:
        return _error(f"沒有名為 {name} 的工具；可用的是：{', '.join(_TOOL_FUNCS)}")

    if isinstance(arguments, str):
        try:
            kwargs = json.loads(arguments or "{}")
        except json.JSONDecodeError as exc:
            return _error(f"arguments 不是合法 JSON：{exc}")
    else:
        kwargs = arguments or {}

    if not isinstance(kwargs, dict):
        return _error("arguments 必須是 JSON object")

    try:
        return fn(ctx, **kwargs)
    except TypeError as exc:
        return _error(f"參數不符：{exc}")
