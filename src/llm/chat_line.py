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
) -> str:
    """組一行聊天紀錄：`[時間] 顯示名#XXXX: 內容`。

    - time_only=True → 時間只標 `HH:MM`（日期交給 caller 以換日 header 處理）；
      False → 完整 `YYYY-MM-DD HH:MM`。
    - max_len 設定時，內容超過長度截斷補「…」（時間 / 名字不計入）。
    - compact=True（預設，/askai 既有行為）→ 內容壓成單行（換行 / 多空白合一），
      避免單則內換行破壞 `[時間] 名: 內容` 行結構。compact=False → 保留原始空白
      （ambient / 日記既有行為；嚴格等價用）。
    """
    name = name_with_anchor(msg.author)
    text = semantic_message_text(msg)
    if compact:
        text = " ".join(text.split())
    if max_len is not None and len(text) > max_len:
        text = text[:max_len] + "…"
    fmt = "%H:%M" if time_only else "%Y-%m-%d %H:%M"
    ts = msg.created_at.astimezone(tz).strftime(fmt)
    return f"[{ts}] {name}: {text}"


async def fetch_recent_lines(
    channel,
    *,
    tz: tzinfo,
    limit: int,
    before=None,
    after=None,
    max_len: int | None = None,
    collect_participant_ids: bool = False,
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
    - on_error：抓取失敗時呼叫（讓 caller 決定 log 等級/訊息）；失敗仍回已收集到的部分。
    """
    lines: list[str] = []
    pids: Optional[list[int]] = [] if collect_participant_ids else None
    hist_kwargs: dict = {"limit": limit}
    if before is not None:
        hist_kwargs["before"] = before
    if after is not None:
        hist_kwargs["after"] = after
        hist_kwargs["oldest_first"] = False  # 抓最新，最後反轉成時序（與舊行為一致）
    try:
        async for msg in channel.history(**hist_kwargs):
            if pids is not None and not msg.author.bot and msg.author.id not in pids:
                pids.append(msg.author.id)
            if not semantic_message_text(msg):  # 純空訊息（無文字/貼圖）整則跳過
                continue
            # compact=False：ambient / 日記歷史上不壓縮空白，保留原貌（嚴格等價）
            lines.append(
                format_chat_line(msg, tz, time_only=True, max_len=max_len, compact=False)
            )
    except Exception as exc:  # noqa: BLE001 — best-effort，失敗回部分結果
        if on_error is not None:
            on_error(exc)
    lines.reverse()  # newest-first → 時序（舊→新）
    return lines, pids
