"""/askai 的聊天脈絡檢索只在「伺服器裡、讀得到歷史」的頻道抓訊息，而且不靠 discord 的型別判斷。

守的底線：
  - 私訊（沒有 guild）不抓歷史，回空的脈絡
  - 沒有 `history` 的頻道（分類、論壇）不抓歷史，回空的脈絡
  - 文字頻道、thread（有 guild、有 history）會抓歷史
  - 判斷看的是能力（guild、history），不是 discord 的類別：服務層不 import discord（守衛 `test_layering`）

hermetic：假的 interaction 與頻道，BM25 與向量排名都換成空結果，不碰模型與資料庫。

執行：
    cd src && python -m unittest test.test_context_retriever_channel -v
"""

import logging
import os
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from llm.retrievers import context_retriever as cr  # noqa: E402
from sys_settings.time_settings import APP_TZ  # noqa: E402


class _Channel:
    def __init__(self, *, guild, with_history=True):
        self.id = 5
        self.guild = guild
        self.history_calls = 0
        if with_history:
            self.history = self._history   # 像文字頻道、thread
        # 沒給 history 就像分類、論壇頻道：discord.py 的這些類別沒有 history()

    def _history(self, limit):
        self.history_calls += 1

        async def gen():
            if False:
                yield None
        return gen()


def _interaction(channel):
    return SimpleNamespace(channel=channel, client=SimpleNamespace(user=SimpleNamespace(id=1)))


class ChannelGateTests(unittest.IsolatedAsyncioTestCase):
    async def _run(self, channel):
        with mock.patch.object(cr, "_build_bm25_rank", return_value={}), \
             mock.patch.object(cr, "_build_vector_rank", return_value={}):
            return await cr.retrieve_discord_context(
                _interaction(channel), "今汐怎麼配隊",
                max_context_messages=20, min_recent_context=5, max_relevant_context=5, max_context_to_send=10,
                taipei_tz=APP_TZ, logger=logging.getLogger("test"),
            )

    async def test_dm_without_guild_is_skipped(self):
        channel = _Channel(guild=None)
        with self.assertNoLogs("test", level="WARNING"):   # 是安靜地跳過，不是讀失敗被接住
            context, bot_context, meta = await self._run(channel)
        self.assertEqual((context, bot_context), ([], []))
        self.assertEqual(channel.history_calls, 0, "私訊不該去讀歷史")
        self.assertEqual(meta["fetched_count"], 0)

    async def test_channel_without_history_is_skipped(self):
        channel = _Channel(guild=SimpleNamespace(id=9), with_history=False)
        with self.assertNoLogs("test", level="WARNING"):
            context, bot_context, _ = await self._run(channel)
        self.assertEqual((context, bot_context), ([], []))

    async def test_guild_text_channel_is_read(self):
        channel = _Channel(guild=SimpleNamespace(id=9))
        _, _, meta = await self._run(channel)
        self.assertEqual(channel.history_calls, 1, "伺服器裡的文字頻道要讀歷史")
        self.assertEqual(meta["fetched_count"], 0)


if __name__ == "__main__":
    unittest.main()
