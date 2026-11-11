"""說出群友刪了什麼、改過什麼（llm.storage.deleted_and_edited）。

守的底線：
  - 只給作者自己刪的：管理員或 bot 刪的、不知道誰刪的，被刪的那則和前後文裡都不給
  - 被刪的那則標【已刪，發出後幾秒刪掉】，前後文照時間排、帶名字#尾碼；重疊的併成一段、不重疊的空一行分開；最多 3 則
  - 含電話、email、一長串數字的被刪訊息，內容換成不給看；只有附件的寫 (附件)
  - 開關關著不查；資料庫出錯不帶、記 WARNING
  - 改過的訊息附「（改過，原本打：…）」：只差空白標點不附、bot 的不附、沒改過的不查；原文的 @ 換成名字、太長截斷
  - 插話整理近況時把附註函式交給 fetch_recent_lines

不連資料庫：原始訊息表的讀取換成假的。
"""
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest import mock

import psycopg2

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from llm.ambient import ambient_reply  # noqa: E402
from llm.preprocess.person_anchor import label  # noqa: E402
from llm.storage import deleted_and_edited as de  # noqa: E402
from llm.storage import raw_message_store  # noqa: E402

TZ8 = timezone(timedelta(hours=8))
T0 = datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc)   # 台灣 20:00
A, B = "111122223333441111", "111122223333442222"          # 甲、乙
MEMBERS = {int(A): "甲", int(B): "乙"}


def _guild():
    def get_member(uid):
        name = MEMBERS.get(uid)
        return SimpleNamespace(display_name=name, name=name, id=uid) if name else None
    return SimpleNamespace(get_member=get_member, id=1)


def _row(mid, author, text, *, at, deleted=False, by=None, after=2, attachment=False):
    return {"message_id": mid, "author_id": author, "content": text, "stickers": None, "tenor_gifs": None,
            "has_attachment": attachment, "created_at": T0 + timedelta(seconds=at), "is_deleted": deleted,
            "deleted_at": T0 + timedelta(seconds=at + after) if deleted else None, "deleted_by": by}


def _gone(mid, author, text, *, at, by=None, **kwargs):
    """作者自己刪的（by 沒給就是作者本人）。"""
    return _row(mid, author, text, at=at, deleted=True, by=author if by is None else by, **kwargs)


class DeletedContextTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.deleted: list[dict] = []
        self.around: dict[str, tuple[list, list]] = {}
        self.asked_around: list[str] = []
        self.error = None
        self.switch = SimpleNamespace(deleted_messages_mode="on", edit_notes_mode="on")

        async def recent_deletions(channel_id, thread_id, *, since, limit):
            if self.error is not None:
                raise self.error
            self.query = (channel_id, thread_id, since, limit)
            return list(self.deleted)

        async def rows_around(channel_id, thread_id, created_at, *, before, after):
            target = next(r for r in self.deleted if r["created_at"] == created_at)
            self.asked_around.append(target["message_id"])
            return self.around.get(target["message_id"], ([], []))

        self.enterContext(mock.patch.object(raw_message_store, "recent_deletions", recent_deletions))
        self.enterContext(mock.patch.object(raw_message_store, "rows_around", rows_around))
        self.enterContext(mock.patch.object(de.switches, "current", lambda: self.switch))

    async def _context(self):
        return await de.deleted_context(_guild(), SimpleNamespace(id=77), tz=TZ8)

    async def test_a_self_deleted_message_comes_with_what_was_said_around_it(self):
        self.deleted = [_gone("d1", A, "儲值跟 @我 請款", at=10)]
        self.around["d1"] = ([_row("a1", B, "前一句", at=5)], [_row("a2", B, "有鬼", at=20)])
        self.assertEqual([
            f"[11/11 20:00] {label('乙', B)}: 前一句",
            f"[11/11 20:00] {label('甲', A)}【已刪，發出後 2 秒刪掉】: 儲值跟 @我 請款",
            f"[11/11 20:00] {label('乙', B)}: 有鬼",
        ], await self._context())
        self.assertEqual(("77", None), self.query[:2], "查的是問的那個頻道")

    async def test_messages_someone_else_deleted_are_never_shown(self):
        self.deleted = [_gone("mod", A, "洗版", at=30, by=B), _gone("who", A, "不知道誰刪的", at=20, by=""),
                        _gone("d1", A, "打錯了", at=10)]
        self.deleted[1]["deleted_by"] = None
        self.around["d1"] = ([], [_row("x", B, "接著講", at=15), _gone("mod2", B, "罵人", at=16, by=A)])
        lines = await self._context()
        self.assertEqual(["d1"], self.asked_around, "管理員刪的、不知道誰刪的不當成要講的那則")
        text = "\n".join(lines)
        for hidden in ("洗版", "不知道誰刪的", "罵人"):
            self.assertNotIn(hidden, text)
        self.assertIn("打錯了", text)

    async def test_private_details_in_a_deleted_message_are_hidden(self):
        for secret in ("我電話 0912-345-678", "寄到 someone@example.com", "帳號 12345678"):
            with self.subTest(secret=secret):
                self.deleted = [_gone("d1", A, secret, at=10)]
                line = (await self._context())[0]
                self.assertIn(de._HIDDEN, line)
                self.assertNotIn(secret.split()[-1], line)

    async def test_a_deleted_attachment_only_says_there_was_one(self):
        self.deleted = [_gone("d1", A, "", at=10, attachment=True)]
        self.assertTrue((await self._context())[0].endswith(": (附件)"))

    async def test_overlapping_contexts_merge_and_separate_ones_are_split(self):
        self.deleted = [_gone("d3", A, "第三", at=600), _gone("d2", A, "第二", at=20), _gone("d1", A, "第一", at=10)]
        shared = _row("s", B, "中間", at=15)
        self.around = {"d1": ([], [shared]), "d2": ([shared], []), "d3": ([_row("far", B, "很久以後", at=590)], [])}
        lines = await self._context()
        texts = [line.split(": ", 1)[1] if line else "" for line in lines]
        self.assertEqual(["第一", "中間", "第二", "", "很久以後", "第三"], texts)

    async def test_at_most_three_deleted_messages(self):
        self.deleted = [_gone(f"d{i}", A, f"第{i}則", at=100 - i) for i in range(5)]
        await self._context()
        self.assertEqual({"d0", "d1", "d2"}, set(self.asked_around), "最近刪的三則")

    async def test_nothing_deleted_means_no_block(self):
        self.assertIsNone(await self._context())

    async def test_switch_off_does_not_look(self):
        self.switch.deleted_messages_mode = "off"
        self.error = AssertionError("開關關著不該查")
        self.assertIsNone(await self._context())

    async def test_a_database_error_drops_the_block(self):
        self.error = psycopg2.OperationalError("down")
        with self.assertLogs(de.logger, "WARNING"):
            self.assertIsNone(await self._context())


class EditNotesTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.originals: dict[str, str] = {}
        self.asked: list = []
        self.error = None
        self.switch = SimpleNamespace(deleted_messages_mode="on", edit_notes_mode="on")

        async def original_texts(ids):
            if self.error is not None:
                raise self.error
            self.asked.append(sorted(str(i) for i in ids))
            return dict(self.originals)

        self.enterContext(mock.patch.object(raw_message_store, "original_texts", original_texts))
        self.enterContext(mock.patch.object(de.switches, "current", lambda: self.switch))

    def _msg(self, mid, content, *, edited=True, bot=False):
        return SimpleNamespace(id=mid, content=content, edited_at=T0 if edited else None,
                               author=SimpleNamespace(bot=bot), mentions=[], guild=_guild())

    async def test_an_edited_message_gets_its_original_text(self):
        self.originals = {"1": "今天舔器很好"}
        notes = await de.edit_notes([self._msg(1, "今天天氣很好")])
        self.assertEqual({1: "（改過，原本打：今天舔器很好）"}, notes)

    async def test_only_punctuation_or_spaces_changed_is_not_noted(self):
        self.originals = {"1": "好喔", "2": "等 一下"}
        notes = await de.edit_notes([self._msg(1, "好喔！"), self._msg(2, "等一下")])
        self.assertEqual({}, notes)

    async def test_only_edited_messages_from_people_are_looked_up(self):
        await de.edit_notes([self._msg(1, "a"), self._msg(2, "b", edited=False), self._msg(3, "c", bot=True)])
        self.assertEqual([["1"]], self.asked)

    async def test_nothing_edited_does_not_look(self):
        self.assertEqual({}, await de.edit_notes([self._msg(1, "a", edited=False)]))
        self.assertEqual([], self.asked)

    async def test_mentions_become_names_and_long_originals_are_cut(self):
        self.originals = {"1": f"<@{B}> " + "很長" * 60}
        note = (await de.edit_notes([self._msg(1, "短")]))[1]
        self.assertIn(label("乙", B), note)
        self.assertNotIn("<@", note)
        self.assertTrue(note.endswith("…）"))

    async def test_switch_off_does_not_look(self):
        self.switch.edit_notes_mode = "off"
        self.assertEqual({}, await de.edit_notes([self._msg(1, "a")]))
        self.assertEqual([], self.asked)

    async def test_a_database_error_drops_the_notes(self):
        self.error = psycopg2.OperationalError("down")
        with self.assertLogs(de.logger, "WARNING"):
            self.assertEqual({}, await de.edit_notes([self._msg(1, "a")]))


class AmbientWiringTests(unittest.IsolatedAsyncioTestCase):
    async def test_recent_lines_carry_the_edit_notes(self):
        fetch = mock.AsyncMock(return_value=([], []))
        message = SimpleNamespace(channel=object(), guild=None, author=SimpleNamespace(id=1))
        with mock.patch.object(ambient_reply, "fetch_recent_lines", fetch):
            await ambient_reply._fetch_recent(message)
        self.assertIs(de.edit_notes, fetch.await_args.kwargs["annotate"])


if __name__ == "__main__":
    unittest.main()
