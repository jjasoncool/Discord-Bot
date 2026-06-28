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

from datetime import tzinfo
from typing import TYPE_CHECKING, Callable, Optional

from llm.emoji_text_utils import replace_custom_emoji_with_description
from llm.sticker_cache import get_sticker_text

if TYPE_CHECKING:  # 僅型別註解用；runtime 不依賴 discord（保持 leaf 輕量）
    import discord


def name_with_anchor(author) -> str:
    """顯示名稱 + #XXXX（user_id 後四碼），跟 persona card 標題對齊，穩定分辨同名/相似的人。

    完整 user_id 不進 prompt（降敏 + 省 token）；撞號代價只在 LLM 描述層。
    """
    name = getattr(author, "display_name", None) or author.name
    uid = str(getattr(author, "id", "") or "")
    short = uid[-4:] if len(uid) >= 4 else ""
    return f"{name}#{short}" if short else name


def semantic_message_text(msg: discord.Message) -> str:
    """訊息文字 + 語意化自訂表情（<:name:id>→:描述:）+ 貼圖描述。

    純貼圖（無文字）訊息會回傳貼圖描述而非空字串，避免被當空訊息整則跳過。
    回傳前不壓空白（保留原樣讓 caller 決定）；單行壓縮由 format_chat_line 負責。
    """
    text = replace_custom_emoji_with_description((msg.content or "").strip())
    if msg.stickers:
        parts = [s for s in (get_sticker_text(st) for st in msg.stickers) if s]
        if parts:
            sticker_part = " ".join(parts)
            text = f"{text} {sticker_part}" if text else sticker_part
    return text


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
    - empty_placeholder：內容為空（純圖等）時改用此字串當內容，讓「被回覆的純圖訊息」也能
      成行被 ↩#N 指到（caller 仍可選擇對非目標的空訊息直接跳過、不傳此參數）。
    """
    name = name_with_anchor(msg.author)
    if self_id is not None and getattr(msg.author, "id", None) == self_id:
        name += "(你自己)"
    text = semantic_message_text(msg)
    if not text and empty_placeholder is not None:
        text = empty_placeholder
    if compact:
        text = " ".join(text.split())
    if max_len is not None and len(text) > max_len:
        text = text[:max_len] + "…"
    fmt = "%H:%M" if time_only else "%Y-%m-%d %H:%M"
    ts = msg.created_at.astimezone(tz).strftime(fmt)
    return f"{prefix}[{ts}] {name}: {text}{suffix}"


def _reply_target_placeholder(msg) -> str:
    """被回覆、但本身無文字（純圖/附件）的訊息，給個佔位內容讓它能成行被 ↩#N 指到。"""
    atts = getattr(msg, "attachments", None) or []
    for a in atts:
        fn = (getattr(a, "filename", "") or "").lower()
        if fn.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif")):
            return "(圖)"
    return "(附件)" if atts else "(訊息)"


def _thread_render(msgs: list, tz: tzinfo, max_len: int | None, self_id: int | None) -> list[str]:
    """把時序訊息渲染成帶 reply 編號 threading 的行。

    clutter 隨「回覆邊數」而非行數成長：
    - 只有「視窗內被回覆過」的訊息給短編號，前綴 `#N `；其餘行不加編號。
    - 是回覆的行加後綴 ` ↩#M`（M＝被回那則的編號）；被回的在視窗外 → ` ↩(較早)`。
    - 非目標的空訊息照舊整則跳過；但「被回覆的純圖訊息」改顯示 `(圖)` 一行（才指得到）。
    回覆只會指向更早的訊息 → 目標必在其回覆者之前出現，編號無前向引用問題。
    """
    in_window = {m.id for m in msgs}

    def _ref_id(m):
        ref = getattr(m, "reference", None)
        return getattr(ref, "message_id", None) if ref is not None else None

    referenced = {rid for m in msgs if (rid := _ref_id(m)) is not None and rid in in_window}
    thread_no: dict = {}
    for m in msgs:
        if m.id in referenced:
            thread_no[m.id] = len(thread_no) + 1

    lines: list[str] = []
    for m in msgs:
        is_target = m.id in thread_no
        has_text = bool(semantic_message_text(m))
        if not has_text and not is_target:
            continue  # 非目標的空訊息照舊跳過（不增 token）
        rid = _ref_id(m)
        suffix = ""
        if rid is not None:
            suffix = f" ↩#{thread_no[rid]}" if rid in thread_no else " ↩(較早)"
        lines.append(
            format_chat_line(
                m, tz, time_only=True, max_len=max_len, compact=False, self_id=self_id,
                prefix=(f"#{thread_no[m.id]} " if is_target else ""),
                suffix=suffix,
                empty_placeholder=(None if has_text else _reply_target_placeholder(m)),
            )
        )
    return lines


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
    - thread_replies=True → 行加 reply 編號 threading（見 _thread_render）；預設 False＝既有扁平輸出。
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

    if thread_replies:
        lines = _thread_render(msgs, tz, max_len, self_id)
    else:
        # compact=False：ambient / 日記歷史上不壓縮空白，保留原貌（嚴格等價）；空訊息整則跳過
        lines = [
            format_chat_line(m, tz, time_only=True, max_len=max_len, compact=False, self_id=self_id)
            for m in msgs
            if semantic_message_text(m)
        ]
    return lines, pids
