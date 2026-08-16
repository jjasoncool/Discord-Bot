"""Discord 聊天行的統一格式化層。

askai（context_retriever）、ambient（ambient_reply）與日記（diary_reflection）三條路徑
共用這裡，確保「[時間] 顯示名#XXXX: 內容」的組行邏輯只有一份：名字錨點、自訂 emoji
語意化、貼圖描述、空白壓縮、時間戳。各 caller 的差異（要不要日期、單則長度上限）以
參數控制，不再各自維護一套。

歷史背景：原本 askai 在 context_retriever 內聯組行（且未做 emoji 語意化，prompt 會出現
raw `<:name:id>`），ambient / diary 又各有 `_name_with_anchor` / `_semantic_msg_text`，
三處重複又有 drift。收斂到此模組後，askai 也順帶吃到 emoji 語意化。
"""

from __future__ import annotations

import logging
import re
from datetime import tzinfo
from typing import TYPE_CHECKING, Callable, Optional

from llm.emoji_text_utils import replace_custom_emoji_with_description
from llm.sticker_cache import get_sticker_text
from llm.vision_image import is_vision_image

if TYPE_CHECKING:  # 僅型別註解用；runtime 不依賴 discord（保持 leaf 輕量）
    import discord

logger = logging.getLogger("discord_bot")

# Discord 原始 mention：<@123>、<@!123>（舊版帶暱稱的寫法）
_MENTION_RE = re.compile(r"<@!?(\d+)>")


def name_with_anchor(author) -> str:
    """顯示名稱 + #XXXX（user_id 後四碼），跟 persona card 標題對齊，穩定分辨同名/相似的人。

    完整 user_id 不進 prompt（降敏 + 省 token）；撞號代價只在 LLM 描述層。
    """
    name = getattr(author, "display_name", None) or author.name
    uid = str(getattr(author, "id", "") or "")
    short = uid[-4:] if len(uid) >= 4 else ""
    return f"{name}#{short}" if short else name


def resolve_user_mentions(text: str, msg) -> str:
    """把原始 `<@123456789>` 換成 `顯示名#XXXX`（與 chat_history 其他行同格式）。

    **對照靠的是 `#XXXX`（user_id 後四碼），不是名字**——群友會改暱稱、persona card 又用
    自填別名，唯一穩定的串接點就是這個錨點。所以名字查不到也無妨：輸出 `某人#6490`，
    模型看到 chat_history 別行的 `克羅#6490` 一樣對得上是同一個人。

    解析順序：`msg.mentions`（discord.py 已解析好，連已離開伺服器的 User 都在）→
    guild member cache → 純錨點。全部零 API、零 DB。

    修的是實測 **53% 的 chat_history 含有裸 `<@id>`** ——模型只看到一長串數字，
    完全不知道那是誰，也對不上任何人（emoji_text_utils 的註解早就寫明它不動 mention）。
    """
    if "<@" not in text:
        return text  # fast path：絕大多數訊息沒有 mention
    by_id = {str(getattr(u, "id", "")): u for u in (getattr(msg, "mentions", None) or [])}
    guild = getattr(msg, "guild", None)

    def _sub(m: re.Match) -> str:
        uid = m.group(1)
        user = by_id.get(uid)
        if user is None and guild is not None:
            try:
                user = guild.get_member(int(uid))
            except (ValueError, TypeError, AttributeError):
                user = None
        if user is not None:
            return name_with_anchor(user)
        return f"某人#{uid[-4:]}" if len(uid) >= 4 else "某人"

    return _MENTION_RE.sub(_sub, text)


def semantic_message_text(msg: discord.Message) -> str:
    """訊息文字 + 語意化自訂表情（<:name:id>→:描述:）+ 人名 mention + 貼圖描述。

    純貼圖（無文字）訊息會回傳貼圖描述而非空字串，避免被當空訊息整則跳過。
    回傳前不壓空白（保留原樣讓 caller 決定）；單行壓縮由 format_chat_line 負責。
    """
    text = replace_custom_emoji_with_description((msg.content or "").strip())
    text = resolve_user_mentions(text, msg)
    if msg.stickers:
        parts = [s for s in (get_sticker_text(st) for st in msg.stickers) if s]
        if parts:
            sticker_part = " ".join(parts)
            text = f"{text} {sticker_part}" if text else sticker_part
    return text


def image_marker(msg) -> str:
    """訊息帶了幾張圖 → `(圖)` / `(圖×N)`；沒帶就空字串。

    有文字又有圖的訊息本來不會在 chat_history 留下任何痕跡（只印得出文字），模型從
    vision payload 收到圖、卻不知道那張圖掛在哪一行——多人同時貼圖時就會安錯人。
    """
    atts = getattr(msg, "attachments", None) or []
    n = sum(1 for a in atts if is_vision_image(getattr(a, "filename", "") or ""))
    if not n:
        return ""
    return "(圖)" if n == 1 else f"(圖×{n})"


def format_chat_line(
    msg: discord.Message,
    tz: tzinfo,
    *,
    time_only: bool = False,
    max_len: int | None = None,
    compact: bool = True,
    self_id: int | None = None,
    prefix: str = "",
    suffix: str = "",
    empty_placeholder: str | None = None,
) -> str:
    """組一行聊天紀錄：`[時間] 顯示名#XXXX: 內容`。

    - time_only=True → 時間只標 `HH:MM`（日期交給 caller 以換日 header 處理）；
      False → 完整 `YYYY-MM-DD HH:MM`。
    - max_len 設定時，內容超過長度截斷補「…」（時間 / 名字不計入）。
    - compact=True（預設，/askai 既有行為）→ 內容壓成單行（換行 / 多空白合一），
      避免單則內換行破壞 `[時間] 名: 內容` 行結構。compact=False → 保留原始空白
      （ambient / 日記既有行為；嚴格等價用）。
    - self_id 設定且該則作者＝self_id（bot 自己）→ 名字後標「(你自己)」，讓模型在
      混合的 chat_history 裡認得哪幾行是自己講的，不致把自己的話當成別人的。
    - prefix / suffix：在 `[時間]…內容` 前後接字串（給 reply threading 用：prefix 放被回覆
      訊息的編號錨 `#N `、suffix 放回覆指標 ` ↩#M`）；預設空＝不影響既有 caller。
    - 帶圖的訊息會在內容尾端補 `(圖)` / `(圖×N)`（見 `image_marker`），純圖訊息則整行內容
      就是那個標記。圖是走 vision payload 另外送的，文字裡沒有痕跡的話模型對不出「哪張圖
      是哪一行的」。
    - empty_placeholder：內容為空（純附件等）時改用此字串當內容，讓「被回覆的空訊息」也能
      成行被 ↩#N 指到（caller 仍可選擇對非目標的空訊息直接跳過、不傳此參數）。
    """
    name = name_with_anchor(msg.author)
    if self_id is not None and getattr(msg.author, "id", None) == self_id:
        name += "(你自己)"
    text = semantic_message_text(msg)
    if compact:
        text = " ".join(text.split())
    if max_len is not None and len(text) > max_len:
        text = text[:max_len] + "…"
    # 圖片標記接在截斷之後：內容再長也不能把「這則有圖」這件事截掉
    marker = image_marker(msg)
    if marker:
        text = f"{text} {marker}" if text else marker
    if not text and empty_placeholder is not None:
        text = empty_placeholder
    fmt = "%H:%M" if time_only else "%Y-%m-%d %H:%M"
    ts = msg.created_at.astimezone(tz).strftime(fmt)
    return f"{prefix}[{ts}] {name}: {text}{suffix}"


# 已警告過的撞號組合（避免同一組每次組 prompt 都洗一次 log）
_WARNED_ANCHOR_COLLISIONS: set = set()


def _check_anchor_collision(msgs: list) -> None:
    """偵測「兩個人的 user_id 後四碼相同」→ prompt 裡的 `#XXXX` 會同時指向兩個人。

    錨點是模型辨認「這幾行是同一個人」的唯一依據（顯示名會改、persona card 用自填別名），
    撞號等於讓它把兩個人當成一個，而且完全無聲無息。實測 78 位發言者目前 0 撞號，但機率
    隨群成長上升（約：100 人 39%、150 人 67% 會出現至少一組），所以留個警報。

    真的撞到再處理——加長到 5 碼會讓既有 persona card 文字裡存的 4 碼對不上，要一併重建。
    """
    seen: dict = {}
    for m in msgs:
        uid = str(getattr(getattr(m, "author", None), "id", "") or "")
        if len(uid) < 4:
            continue
        anchor = uid[-4:]
        prev = seen.setdefault(anchor, uid)
        if prev == uid:
            continue
        key = (anchor, *sorted((prev, uid)))
        if key in _WARNED_ANCHOR_COLLISIONS:
            continue
        _WARNED_ANCHOR_COLLISIONS.add(key)
        logger.warning(
            "chat_line 錨點撞號：user_id %s 與 %s 的後四碼都是 #%s → prompt 裡的 #%s 會指向"
            "兩個人，模型可能把他們當同一人。要修得把 name_with_anchor 加長到 5 碼，"
            "並一併重建 persona card（那裡的文字存了 4 碼）。",
            prev, uid, anchor, anchor,
        )


def _reply_target_placeholder(msg) -> str:
    """被回覆、但本身無文字的訊息，給個佔位內容讓它能成行被 ↩#N 指到。

    圖片已由 `image_marker` 標掉（純圖訊息的整行內容就是那個標記），這裡只剩其餘附件與空訊息。
    """
    return "(附件)" if (getattr(msg, "attachments", None) or []) else "(訊息)"


def _thread_render(
    msgs: list, tz: tzinfo, max_len: int | None, self_id: int | None
) -> tuple[list[str], dict]:
    """把時序訊息渲染成帶編號的行；回 (行, {編號: 訊息})。

    - **每一行都給編號**（前綴 `#N `，N 從 1 依序遞增、只算實際成行的訊息）。
      舊版只編「被回覆過」的訊息，但多數人聊天不按 reply → 大部分行沒編號；模型要表態
      「我這句在接哪一條線」時無錨可指。多組人各聊各的時，這個編號就是唯一的指線方式。
    - 是回覆的行加後綴 ` ↩#M`（M＝被回那則的編號）；被回的在視窗外 → ` ↩(較早)`。
    - 空訊息（純圖等）照舊跳過、不佔編號；但「被回覆過的空訊息」要成行顯示 `(圖)` 才指得到。
    回覆只會指向更早的訊息 → 目標必在其回覆者之前出現，編號無前向引用問題。
    """
    in_window = {m.id for m in msgs}

    def _ref_id(m):
        ref = getattr(m, "reference", None)
        return getattr(ref, "message_id", None) if ref is not None else None

    referenced = {rid for m in msgs if (rid := _ref_id(m)) is not None and rid in in_window}

    # 文字只算一次（semantic_message_text 有 regex 替換成本），過濾與渲染共用
    texts = {m.id: semantic_message_text(m) for m in msgs}
    # 先決定哪些會成行，再依序編號 → 編號連續、不因跳過的空訊息而跳號
    rendered = [m for m in msgs if texts[m.id] or m.id in referenced]
    thread_no = {m.id: i + 1 for i, m in enumerate(rendered)}

    lines: list[str] = []
    for m in rendered:
        rid = _ref_id(m)
        suffix = ""
        if rid is not None:
            suffix = f" ↩#{thread_no[rid]}" if rid in thread_no else " ↩(較早)"
        lines.append(
            format_chat_line(
                m, tz, time_only=True, max_len=max_len, compact=False, self_id=self_id,
                prefix=f"#{thread_no[m.id]} ",
                suffix=suffix,
                empty_placeholder=(None if texts[m.id] else _reply_target_placeholder(m)),
            )
        )
    return lines, {thread_no[m.id]: m for m in rendered}


async def fetch_recent_lines(
    channel,
    *,
    tz: tzinfo,
    limit: int,
    before=None,
    after=None,
    max_len: int | None = None,
    collect_participant_ids: bool = False,
    self_id: int | None = None,
    thread_replies: bool = False,
    thread_map: Optional[dict] = None,
    on_error: Optional[Callable[[Exception], None]] = None,
) -> tuple[list[str], Optional[list[int]]]:
    """抓近期頻道訊息 → 時序（舊→新）的 `[HH:MM] 名#XXXX: 內容` 行（time_only）。

    ambient 與日記共用：兩者都「撈近窗 + 即時格式化 + 空訊息整則跳過 + 反轉成時序」，
    只差視窗界（before 一則訊息 vs after 一個時間）與長度上限。/askai 不走這裡——它撈
    raw 訊息物件、排序後才格式化，形狀不同。

    - before / after：對應 discord channel.history 的視窗界（after 模式內部用
      oldest_first=False 抓最新、最後統一反轉，與既有行為一致）。
    - collect_participant_ids=True 時，回傳 (lines, 非 bot 發話者 id[出現序])；否則第二項為 None。
      lines 含 bot 自己的話以維持對話連續性；participant_ids 只收非 bot。
    - thread_replies=True → 每行加編號（見 _thread_render）；預設 False＝既有扁平輸出。
    - thread_map：傳一個 dict 進來，thread_replies 模式下會被填成 `{編號: discord.Message}`。
      out-param 而非改回傳簽章＝不動既有 caller 的 unpack。caller 拿它把模型回的 `#N`
      還原成真正的訊息物件（reply 錨定用）。
    - on_error：抓取失敗時呼叫（讓 caller 決定 log 等級/訊息）；失敗仍回已收集到的部分。
    """
    pids: Optional[list[int]] = [] if collect_participant_ids else None
    hist_kwargs: dict = {"limit": limit}
    if before is not None:
        hist_kwargs["before"] = before
    if after is not None:
        hist_kwargs["after"] = after
        hist_kwargs["oldest_first"] = False  # 抓最新，最後反轉成時序（與舊行為一致）
    msgs: list = []
    try:
        async for msg in channel.history(**hist_kwargs):
            if pids is not None and not msg.author.bot and msg.author.id not in pids:
                pids.append(msg.author.id)
            msgs.append(msg)
    except Exception as exc:  # noqa: BLE001 — best-effort，失敗回部分結果
        if on_error is not None:
            on_error(exc)
    msgs.reverse()  # newest-first → 時序（舊→新）
    _check_anchor_collision(msgs)  # #XXXX 指向兩個人時出警報（見函式說明）

    if thread_replies:
        lines, no_to_msg = _thread_render(msgs, tz, max_len, self_id)
        if thread_map is not None:
            thread_map.update(no_to_msg)
    else:
        # compact=False：ambient / 日記歷史上不壓縮空白，保留原貌（嚴格等價）；空訊息整則跳過
        lines = [
            format_chat_line(m, tz, time_only=True, max_len=max_len, compact=False, self_id=self_id)
            for m in msgs
            if semantic_message_text(m)
        ]
    return lines, pids
