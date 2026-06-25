"""chat_line 共用格式化層單元測試。

覆蓋 askai / ambient / 日記三條路徑共用的組行邏輯：名字錨點、時間戳（完整 vs time_only）、
單行空白壓縮、max_len 截斷、自訂 emoji 不殘留 raw 代碼。

執行：
    cd src && python -m pytest test/test_chat_line.py -v
或：
    cd src && python -m unittest test.test_chat_line -v
"""

import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from llm.chat_line import (
    fetch_recent_lines,
    format_chat_line,
    name_with_anchor,
    semantic_message_text,
)

TZ8 = timezone(timedelta(hours=8))


def _msg(content="", *, author_name="老哥", author_id=123456789012341234, bot=False,
         created=datetime(2026, 6, 25, 15, 30, tzinfo=timezone.utc), stickers=()):
    """造一個夠用的假 discord.Message（只放 chat_line 會碰到的欄位）。"""
    author = SimpleNamespace(display_name=author_name, name=author_name, id=author_id, bot=bot)
    return SimpleNamespace(content=content, author=author, created_at=created, stickers=list(stickers))


class _FakeChannel:
    """假頻道：history(**kwargs) 回 async iterator（依 discord 慣例 newest-first 餵入）。"""

    def __init__(self, msgs_newest_first, *, raise_exc=None):
        self._msgs = msgs_newest_first
        self._raise = raise_exc

    def history(self, **kwargs):
        msgs = self._msgs[: kwargs.get("limit")]
        raise_exc = self._raise

        async def _gen():
            if raise_exc is not None:
                raise raise_exc
            for m in msgs:
                yield m

        return _gen()


class NameAnchorTests(unittest.TestCase):
    def test_appends_last4_of_id(self):
        self.assertEqual(name_with_anchor(_msg().author), "老哥#1234")

    def test_fallback_to_name_when_no_display(self):
        author = SimpleNamespace(display_name=None, name="純帳號", id=999888)
        self.assertEqual(name_with_anchor(author), "純帳號#9888")

    def test_no_id_no_anchor(self):
        author = SimpleNamespace(display_name="無id", name="無id", id="")
        self.assertEqual(name_with_anchor(author), "無id")


class SemanticTextTests(unittest.TestCase):
    def test_plain_text_passthrough(self):
        # 純文字走 emoji fast-path，不動內容（壓縮交給 format_chat_line）
        self.assertEqual(semantic_message_text(_msg("今天天氣不錯")), "今天天氣不錯")

    def test_custom_emoji_code_not_left_raw(self):
        # 不論字典有沒有登錄，raw <:name:id> 都不該殘留在輸出
        out = semantic_message_text(_msg("讚<:dogehehe:1279489099534827611>"))
        self.assertNotIn("<:", out)
        self.assertNotIn("1279489099534827611", out)


class FormatChatLineTests(unittest.TestCase):
    def test_full_timestamp_default(self):
        # UTC 15:30 → 台北 23:30；預設帶完整日期
        line = format_chat_line(_msg("哈囉"), TZ8)
        self.assertEqual(line, "[2026-06-25 23:30] 老哥#1234: 哈囉")

    def test_time_only(self):
        line = format_chat_line(_msg("哈囉"), TZ8, time_only=True)
        self.assertEqual(line, "[23:30] 老哥#1234: 哈囉")

    def test_whitespace_collapsed_to_single_line(self):
        # 換行 / 多空白壓成單行，避免破壞 [時間] 名: 內容 行結構
        line = format_chat_line(_msg("第一行\n第二行   有空白"), TZ8, time_only=True)
        self.assertEqual(line, "[23:30] 老哥#1234: 第一行 第二行 有空白")

    def test_max_len_truncates_content_only(self):
        line = format_chat_line(_msg("一二三四五六七八九十"), TZ8, time_only=True, max_len=5)
        self.assertEqual(line, "[23:30] 老哥#1234: 一二三四五…")

    def test_max_len_no_truncate_when_within(self):
        line = format_chat_line(_msg("短"), TZ8, time_only=True, max_len=5)
        self.assertEqual(line, "[23:30] 老哥#1234: 短")

    def test_compact_false_preserves_whitespace(self):
        # compact=False（ambient/日記既有行為）：保留換行與多空白
        line = format_chat_line(_msg("第一行\n第二行   有空白"), TZ8, time_only=True, compact=False)
        self.assertEqual(line, "[23:30] 老哥#1234: 第一行\n第二行   有空白")


class FetchRecentLinesTests(unittest.IsolatedAsyncioTestCase):
    def _m(self, mins, content, *, uid, bot=False):
        # created 用分鐘區分先後；TZ 不影響時序測試
        return _msg(content, author_name=f"u{uid}", author_id=uid, bot=bot,
                    created=datetime(2026, 6, 25, 15, mins, tzinfo=timezone.utc))

    async def test_reversed_to_chronological(self):
        # 餵入 newest-first，輸出應為時序（舊→新）
        ch = _FakeChannel([
            self._m(30, "新", uid=111122223333444401),
            self._m(20, "中", uid=111122223333444402),
            self._m(10, "舊", uid=111122223333444403),
        ])
        lines, pids = await fetch_recent_lines(ch, tz=TZ8, limit=10)
        self.assertEqual([l.split(": ", 1)[1] for l in lines], ["舊", "中", "新"])
        self.assertIsNone(pids)  # 沒要求收集

    async def test_collect_participant_ids_skips_bot_in_iter_order(self):
        ch = _FakeChannel([
            self._m(30, "a", uid=900000000000000001),
            self._m(20, "b", uid=900000000000000002, bot=True),  # bot 不進 pids
            self._m(10, "c", uid=900000000000000001),  # 重複不重收
        ])
        lines, pids = await fetch_recent_lines(ch, tz=TZ8, limit=10, collect_participant_ids=True)
        self.assertEqual(pids, [900000000000000001])  # iteration(newest-first) 序、去重、排除 bot
        self.assertEqual(len(lines), 3)  # bot 的話仍進 lines（維持連續性）

    async def test_empty_message_skipped_but_counts_for_pid(self):
        ch = _FakeChannel([
            self._m(20, "", uid=800000000000000001),  # 空訊息：不進 lines，但 author 算 pid
            self._m(10, "嗨", uid=800000000000000002),
        ])
        lines, pids = await fetch_recent_lines(ch, tz=TZ8, limit=10, collect_participant_ids=True)
        self.assertEqual(len(lines), 1)
        self.assertEqual(pids, [800000000000000001, 800000000000000002])

    async def test_max_len_applied(self):
        ch = _FakeChannel([self._m(10, "一二三四五六", uid=700000000000000001)])
        lines, _ = await fetch_recent_lines(ch, tz=TZ8, limit=10, max_len=3)
        self.assertTrue(lines[0].endswith("一二三…"))

    async def test_preserves_whitespace_strict_equivalence(self):
        # fetch_recent_lines 走 compact=False，保留 ambient/日記原本不壓縮的行為
        ch = _FakeChannel([self._m(10, "a\nb  c", uid=600000000000000001)])
        lines, _ = await fetch_recent_lines(ch, tz=TZ8, limit=10)
        self.assertTrue(lines[0].endswith(": a\nb  c"))

    async def test_on_error_called_returns_partial(self):
        seen = []
        ch = _FakeChannel([], raise_exc=RuntimeError("boom"))
        lines, pids = await fetch_recent_lines(
            ch, tz=TZ8, limit=10, collect_participant_ids=True,
            on_error=lambda e: seen.append(str(e)),
        )
        self.assertEqual(lines, [])
        self.assertEqual(seen, ["boom"])


if __name__ == "__main__":
    unittest.main()
