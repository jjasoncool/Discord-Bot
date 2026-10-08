"""搜尋索引每日維護（`services/search/nightly.py`）：search-mcp 服務每天同步索引、補算新文章的向量。

守的底線：
  - 每天 03:00～04:00 之間做一次；同一天不重做（出錯也不在同一個時段裡反覆重試、一直佔 GPU）
  - 04:00 之後（含 04:00～07:30 維護時段）才啟動的話不補做，等明天 03:00；03:00 前啟動就等到 03:00
  - 向量開關關著只同步、不算向量；開著就同步並補算
  - 工作在別的執行緒做，不卡住排程自己的 event loop

執行：
    cd src && python -m unittest test.test_search_nightly -v
"""

import asyncio
import os
import sys
import threading
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from services.search import nightly  # noqa: E402
from services.search.index import SyncReport  # noqa: E402

TZ = timezone(timedelta(hours=8))


def at(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, day, hour, minute, tzinfo=TZ)


class NightlyScheduleTests(unittest.TestCase):
    def setUp(self):
        self.runs = []
        self.job = nightly.NightlyJob(lambda: self.runs.append(threading.current_thread().name))

    def tick(self, now: datetime) -> datetime:
        return asyncio.run(self.job.tick(now))

    def test_runs_once_inside_the_window_then_waits_for_tomorrow(self):
        self.assertEqual(self.tick(at(9, 3, 5)), at(10, 3))
        self.assertEqual(self.tick(at(9, 3, 40)), at(10, 3))      # 同一天再醒來不重做
        self.assertEqual(len(self.runs), 1)
        self.assertNotEqual(self.runs[0], threading.current_thread().name)   # 丟到別的執行緒做

        self.tick(at(10, 3, 0))
        self.assertEqual(len(self.runs), 2)

    def test_started_before_three_waits_until_three(self):
        self.assertEqual(self.tick(at(9, 1, 30)), at(9, 3))
        self.assertEqual(self.runs, [])

    def test_started_after_four_does_not_catch_up(self):
        for now in (at(9, 4, 0), at(9, 5, 30), at(9, 18, 0)):
            with self.subTest(now=now):
                self.assertEqual(self.tick(now), at(10, 3))
        self.assertEqual(self.runs, [])

    def test_a_failed_run_is_not_retried_in_the_same_window(self):
        calls = []

        def boom():
            calls.append(1)
            raise RuntimeError("pgvector 連不上")

        job = nightly.NightlyJob(boom)
        with self.assertRaises(RuntimeError):
            asyncio.run(job.tick(at(9, 3, 1)))
        # run_due_loop 會在 retry_after 之後再 tick 一次：同一個時段裡不能又打一次 GPU
        self.assertEqual(asyncio.run(job.tick(at(9, 3, 6))), at(10, 3))
        self.assertEqual(len(calls), 1)


class RunOnceTests(unittest.TestCase):
    def run_with(self, mode: str):
        index = mock.Mock(vector_store=object())
        index.sync.return_value = SyncReport(1, 0, 0)
        with mock.patch("services.search.index.default_index", return_value=index), \
                mock.patch("sys_settings.switches.current", return_value=SimpleNamespace(search_vector_mode=mode)), \
                mock.patch("services.search.embed.embed_pending") as embed:
            nightly.run_once()
        return index, embed

    def test_vector_switch_off_only_syncs(self):
        index, embed = self.run_with("off")

        index.sync.assert_called_once_with(force=True)
        embed.assert_not_called()

    def test_vector_switch_on_syncs_and_embeds_new_documents(self):
        index, embed = self.run_with("on")

        embed.assert_called_once_with(index, index.vector_store)   # embed_pending 自己會先同步


if __name__ == "__main__":
    unittest.main()
