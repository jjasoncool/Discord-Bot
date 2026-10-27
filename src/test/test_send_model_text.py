"""送出模型文字 utils.discord_content.send_model_text 與 Bot 的提及預設。

守的底線：
  1. 模型寫的文字送出時不會通知任何人：@everyone、身分組、<@某人> 都擋掉；呼叫端指定的人（/askai 的發問者）
     只在第一段被 @，後面的段落一樣不 @。
  2. 長文照 split_message 切段，每段都經同一份提及設定送出，回傳各段的訊息。
  3. /askai、插話、日記三條送出模型文字的路都走 send_model_text，不自己組 AllowedMentions。
  4. Bot 的全域預設擋 @everyone 與身分組：沒指定提及設定的送出（轉貼外站內容）也通知不到全伺服器。
"""

import asyncio
import os
import re
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from utils.discord_content import DISCORD_MESSAGE_LIMIT, send_model_text  # noqa: E402

SRC = os.path.dirname(HERE)


def _read(rel):
    with open(os.path.join(SRC, rel), encoding="utf-8") as fh:
        return fh.read()


class SendModelTextTests(unittest.TestCase):
    def setUp(self):
        self.send = mock.AsyncMock(side_effect=lambda part, **kw: SimpleNamespace(content=part, kwargs=kw))

    def _mentions(self, call):
        return call.kwargs["allowed_mentions"]

    def test_model_text_never_pings_anyone(self):
        text = "@everyone 大家好 <@&123> <@456> 來看"
        sent = asyncio.run(send_model_text(self.send, text))
        self.assertEqual(1, len(sent))
        mentions = self._mentions(self.send.await_args)
        self.assertFalse(mentions.everyone)
        self.assertFalse(mentions.roles)
        self.assertFalse(mentions.users)
        self.assertFalse(mentions.replied_user)
        self.assertEqual(text, self.send.await_args.args[0])

    def test_only_the_first_part_pings_the_users_the_caller_names(self):
        asker = SimpleNamespace(id=42)
        text = "第一段\n" + ("x" * DISCORD_MESSAGE_LIMIT) + "\n第二段"
        sent = asyncio.run(send_model_text(self.send, text, mention_users=[asker]))
        self.assertEqual(2, len(sent))
        first, second = self.send.await_args_list
        self.assertEqual([asker], self._mentions(first).users)
        self.assertFalse(self._mentions(first).everyone)
        self.assertIs(False, self._mentions(second).users)
        self.assertTrue(second.args[0].endswith("第二段"))

    def test_parts_are_split_to_fit_discord(self):
        text = "\n".join("一行" * 100 for _ in range(30))
        sent = asyncio.run(send_model_text(self.send, text))
        self.assertGreater(len(sent), 1)
        for call in self.send.await_args_list:
            self.assertLessEqual(len(call.args[0]), DISCORD_MESSAGE_LIMIT)


class ModelTextCallersTests(unittest.TestCase):
    """三條送出路徑都走 send_model_text；Bot 的全域預設擋 everyone 與身分組。"""

    def test_askai_ambient_and_diary_use_the_shared_sender(self):
        for rel in ("commands/llm_commands.py", "llm/ambient/ambient_reply.py", "llm/ambient/ambient_diary.py"):
            src = _read(rel)
            self.assertIn("send_model_text(", src, rel)
            self.assertNotIn("AllowedMentions.none()", src, f"{rel} 不自己組提及設定")

    def test_bot_default_blocks_everyone_and_roles(self):
        src = _read("discord_bot.py")
        init = src[src.index("class MyBot"):src.index("async def setup_hook")]
        self.assertRegex(init, re.compile(r"allowed_mentions=discord\.AllowedMentions\(\s*everyone=False,\s*roles=False,\s*users=True"))


if __name__ == "__main__":
    unittest.main()
