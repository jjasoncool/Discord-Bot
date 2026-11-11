"""說出群友刪了什麼、改過什麼：從原始訊息表讀被刪的訊息與編輯前的原文，組成給模型看的文字。

架構定位：功能層（`llm/storage`），讀原始訊息表、吃 Discord 的伺服器、頻道、訊息物件（查名字、@ 換名字）。
  - 上層（誰呼叫）：插話（`llm.ambient.ambient_reply`：被點名時拿 `deleted_context`、整理近況時把 `edit_notes`
    交給 `fetch_recent_lines`）、/askai（`commands.llm_commands`：`deleted_context`）。
  - 下層（呼叫誰）：`llm.storage.raw_message_store`（查詢）、`llm.storage.chat_index_backfill.row_text`（一列組文字）、
    `llm.preprocess.chat_line`（名字#尾碼、@ 換名字）、`sys_settings.switches`。

介面：
  - `deleted_context(guild, channel, *, tz)`：這個頻道最近被作者自己刪掉的訊息連同前後文，一行一則；沒有、開關關著
    或查不到回 None。交給 `generate_reply(deleted_messages=…)`，怎麼用寫在 prompt 的 <deleted_messages> 開頭。
  - `edit_notes(messages)`：{訊息 id: 「（改過，原本打：…）」}，接在近況那一行後面；`fetch_recent_lines(annotate=…)` 用。

規則：
  - 只給作者自己刪的（deleted_by＝作者）：管理員或 bot 刪別人的、判斷不了是誰刪的（NULL）一律不給，前後文裡也拿掉。
  - 只給同一個頻道或討論串、最近 `WINDOW` 內刪的，最多 `MAX_DELETED` 則；每則附前 `BEFORE` 則、刪掉之後到現在最多
    `AFTER` 則，重疊的併成一段。
  - 被刪的那則含電話、email、一長串數字：內容換成「不給看」，說出去收不回。
  - 編輯附註只附字真的改了的（只差空白、標點不算），原文太長截斷。
  - 開關：`deleted_messages_mode`、`edit_notes_mode`。資料庫出錯只少這段，記 WARNING，不擋回覆。
  - 原始訊息表的 deleted_by 只在這裡和 `raw_message_store` 讀寫（守衛擋）：誰刪的這條篩選只有一份。

例外與決策：
  - 管理員刪的不給看：那是處理過的結果（洗版、🔞、罵人），模型從前後文看不出來，講出來等於把刪掉的貼回去。
  - 刪掉之後的訊息比之前的重要（「有鬼」「請po」「你敢 PO 出來…」都在後面），所以後面給得多。
  - 圖、檔案只記「有附件」，刪掉之後拿不回來，只能說附了東西。
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone, tzinfo
from types import SimpleNamespace
from typing import Optional

import psycopg2

from llm.preprocess.chat_line import name_with_anchor, resolve_user_mentions
from llm.preprocess.emoji_text_utils import replace_custom_emoji_with_description
from llm.preprocess.person_anchor import label
from llm.storage import raw_message_store
from llm.storage.chat_index_backfill import row_text
from sys_settings import switches

logger = logging.getLogger(__name__)

WINDOW = timedelta(hours=24)
MAX_DELETED = 3
BEFORE = 5
AFTER = 20
#: 一行最多幾個字（前後文也一樣），原文附註再短一點
LINE_MAX_CHARS = 200
ORIGINAL_MAX_CHARS = 80
#: 一次多撈幾則已刪的：管理員刪的會被篩掉
_DELETED_FETCH = 20

# email、八位以上的數字（中間可以夾空白或 -，電話常這樣寫）
_PRIVATE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+|(?<!\d)(?:\d[ -]?){7,}\d(?!\d)")
_HIDDEN = "（內容有電話、email 或一長串數字，不給看）"
# 比較改前改後時拿掉的：空白、標點、符號（中日韓文字、英數字留著）
_NOT_WORDS = re.compile(r"[\W_]+")


async def deleted_context(guild, channel, *, tz: tzinfo) -> Optional[list[str]]:
    """這個頻道最近被作者自己刪掉的訊息連同前後文；段與段之間空一行。"""
    if switches.current().deleted_messages_mode != "on" or guild is None or channel is None:
        return None
    channel_id, thread_id = raw_message_store.channel_keys(channel)
    try:
        deleted = await raw_message_store.recent_deletions(
            channel_id, thread_id, since=datetime.now(timezone.utc) - WINDOW, limit=_DELETED_FETCH)
        targets = [row for row in deleted if _self_deleted(row)][:MAX_DELETED]
        segments: list[list[dict]] = []
        for target in sorted(targets, key=lambda row: row["created_at"]):
            earlier, later = await raw_message_store.rows_around(
                channel_id, thread_id, target["created_at"], before=BEFORE, after=AFTER)
            _merge(segments, [*earlier, target, *later])
    except psycopg2.Error as exc:
        logger.warning("讀被刪的訊息失敗，這次不帶：%s", exc)
        return None
    lines: list[str] = []
    for segment in segments:
        rendered = [line for row in segment if (line := _line(row, guild, tz)) is not None]
        if rendered:
            lines += ([""] if lines else []) + rendered
    return lines or None


async def edit_notes(messages: list) -> dict[int, str]:
    """改過的訊息 → 接在那一行後面的「（改過，原本打：…）」。"""
    if switches.current().edit_notes_mode != "on":
        return {}
    edited = [m for m in messages if getattr(m, "edited_at", None) is not None and not m.author.bot]
    if not edited:
        return {}
    try:
        originals = await raw_message_store.original_texts([m.id for m in edited])
    except psycopg2.Error as exc:
        logger.warning("讀編輯前的原文失敗，這次不附：%s", exc)
        return {}
    notes: dict[int, str] = {}
    for msg in edited:
        original = originals.get(str(msg.id))
        if original is None or _same_words(original, msg.content or ""):
            continue
        shown = _compact(resolve_user_mentions(replace_custom_emoji_with_description(original), msg), ORIGINAL_MAX_CHARS)
        notes[msg.id] = f"（改過，原本打：{shown}）"
    return notes


def _self_deleted(row: dict) -> bool:
    return row.get("deleted_by") is not None and row["deleted_by"] == row["author_id"]


def _merge(segments: list[list[dict]], rows: list[dict]) -> None:
    """前後文跟上一段重疊就併進去（照時間排、不重複），不然另起一段。"""
    ids = {row["message_id"] for row in rows}
    if segments and ids & {row["message_id"] for row in segments[-1]}:
        merged = {row["message_id"]: row for row in segments[-1] + rows}
        segments[-1] = sorted(merged.values(), key=lambda row: row["created_at"])
    else:
        segments.append(rows)


def _line(row: dict, guild, tz: tzinfo) -> Optional[str]:
    if row["is_deleted"] and not _self_deleted(row):
        return None   # 別人刪的、不知道誰刪的：連前後文裡也不給
    text = _text(row, guild)
    if row["is_deleted"]:
        if _PRIVATE.search(text):
            text = _HIDDEN
        when = f"【已刪，發出後{_elapsed(row['deleted_at'] - row['created_at'])}刪掉】"
    elif not text:
        return None
    else:
        when = ""
    ts = row["created_at"].astimezone(tz).strftime("%m/%d %H:%M")
    return f"[{ts}] {_name(guild, row['author_id'])}{when}: {text or '（沒有文字）'}"


def _text(row: dict, guild) -> str:
    text = resolve_user_mentions(row_text(row), SimpleNamespace(mentions=[], guild=guild))
    if row.get("has_attachment"):
        text = f"{text} (附件)" if text else "(附件)"
    return _compact(text, LINE_MAX_CHARS)


def _name(guild, author_id: str) -> str:
    member = guild.get_member(int(author_id))
    return name_with_anchor(member) if member is not None else label("已離開的群友", author_id)


def _elapsed(delta: timedelta) -> str:
    seconds = max(0, int(delta.total_seconds()))
    if seconds < 60:
        return f" {seconds} 秒"
    if seconds < 3600:
        return f" {seconds // 60} 分鐘"
    return f" {seconds // 3600} 小時"


def _compact(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit] + "…"


def _same_words(before: str, after: str) -> bool:
    return _NOT_WORDS.sub("", before) == _NOT_WORDS.sub("", after)
