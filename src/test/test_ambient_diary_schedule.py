"""AI 日記的排程判斷（llm/ambient/ambient_diary._tick）。

守的底線：
  - 排定時刻沒到不寫，回傳今天的時刻
  - 時刻到了（10 分鐘內）寫一篇、同一天不再寫、回傳明天的時刻
  - 醒來已超過那 10 分鐘（例如重啟錯過）就當錯過、等明天，不補寫、也不會一天兩篇

不連 Discord、不叫模型：寫日記的函式換成計數器。
"""
import os
import sys
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from llm.ambient import ambient_diary as diary  # noqa: E402
from sys_settings.time_settings import APP_TZ  # noqa: E402


class DiaryTickTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.written = 0

        async def fake_reflection(bot):
            self.written += 1

        for target, value in (("run_daily_reflection", fake_reflection),
                              ("_SETTINGS", SimpleNamespace(schedule_hour=23, schedule_minute=30))):
            p = mock.patch.object(diary, target, value)
            p.start()
            self.addCleanup(p.stop)
        diary._ran_on = None
        self.addCleanup(setattr, diary, "_ran_on", None)
        self.bot = object()

    @staticmethod
    def at(hour, minute=0, second=0, day=14):
        return datetime(2026, 10, day, hour, minute, second, tzinfo=APP_TZ)

    async def test_writes_once_when_the_time_arrives(self):
        self.assertEqual(self.at(23, 30), await diary._tick(self.bot, self.at(22)))
        self.assertEqual(0, self.written)
        self.assertEqual(self.at(23, 30, day=15), await diary._tick(self.bot, self.at(23, 30, 5)))
        self.assertEqual(1, self.written)
        await diary._tick(self.bot, self.at(23, 35))
        self.assertEqual(1, self.written, "同一天不寫第二篇")
        await diary._tick(self.bot, self.at(23, 30, 1, day=15))
        self.assertEqual(2, self.written)

    async def test_waking_up_too_late_waits_for_tomorrow(self):
        self.assertEqual(self.at(23, 30, day=15), await diary._tick(self.bot, self.at(23, 50)))
        self.assertEqual(0, self.written, "重啟錯過排定時刻就不補寫")
