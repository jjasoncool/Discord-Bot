"""search-mcp 的背景工作（`services/search/background.py`）：定期同步索引、每天補算新文章的向量。

守的底線：
  - 定期同步：每次同步完排下一次（固定間隔），同步本身丟到別的執行緒做；常駐模式一開就同時跑定期同步與每日維護
  - 定期同步一直失敗：同樣的錯誤只完整記一次、間隔逐次拉長（有上限），恢復時記一行
  - 每天 03:00～04:00 之間做一次；同一天不重做（出錯也不在同一個時段裡反覆重試、一直佔 GPU）
  - 04:00 之後（含 04:00～07:30 維護時段）才啟動的話不補做，等明天 03:00；03:00 前啟動就等到 03:00
  - 向量開關關著只同步、不算向量；開著就同步並補算
  - 工作在別的執行緒做，不卡住排程自己的 event loop

執行：
    cd src && python -m unittest test.test_search_background -v
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

from services.search import background  # noqa: E402
from services.search.index import SyncReport  # noqa: E402

TZ = timezone(timedelta(hours=8))


def at(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, day, hour, minute, tzinfo=TZ)


class NightlyScheduleTests(unittest.TestCase):
    def setUp(self):
        self.runs = []
        self.job = background.NightlyJob(lambda: self.runs.append(threading.current_thread().name))

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

        job = background.NightlyJob(boom)
        with self.assertRaises(RuntimeError):
            asyncio.run(job.tick(at(9, 3, 1)))
        # run_due_loop 會在 retry_after 之後再 tick 一次：同一個時段裡不能又打一次 GPU
        self.assertEqual(asyncio.run(job.tick(at(9, 3, 6))), at(10, 3))
        self.assertEqual(len(calls), 1)


class PeriodicSyncTests(unittest.TestCase):
    def test_syncs_off_the_event_loop_thread_and_schedules_the_next_round(self):
        threads = []
        periodic = background.PeriodicSync(lambda: threads.append(threading.current_thread().name), every_seconds=50)

        self.assertEqual(asyncio.run(periodic.tick(at(9, 14, 0))), at(9, 14, 0) + timedelta(seconds=50))
        self.assertEqual(len(threads), 1)
        self.assertNotEqual(threads[0], threading.current_thread().name)

    def test_repeated_failures_log_one_traceback_and_back_off(self):
        def boom():
            raise RuntimeError("索引是新版程式建的")

        periodic = background.PeriodicSync(boom, every_seconds=50)
        with self.assertLogs("services.search.background", level="INFO") as logs:
            delays = [(asyncio.run(periodic.tick(at(9, 14))) - at(9, 14)).total_seconds() for _ in range(3)]
            periodic.sync = lambda: None
            recovered = asyncio.run(periodic.tick(at(9, 15)))

        self.assertEqual(delays, [100, 200, 400])               # 間隔逐次拉長
        errors = [r for r in logs.records if r.levelname == "ERROR"]
        self.assertEqual(len(errors), 1)                         # 同樣的錯誤只完整記一次
        self.assertIsNotNone(errors[0].exc_info)
        self.assertEqual(sum(r.levelname == "WARNING" for r in logs.records), 2)
        self.assertTrue(any("恢復" in r.getMessage() for r in logs.records))
        self.assertEqual(recovered, at(9, 15) + timedelta(seconds=50))

        # 恢復後又壞：從頭算（間隔回到第一次的長度、再完整記一次錯誤）
        periodic.sync = boom
        with self.assertLogs("services.search.background", level="ERROR"):
            again = asyncio.run(periodic.tick(at(9, 16)))
        self.assertEqual(again, at(9, 16) + timedelta(seconds=100))

    def test_backoff_is_capped(self):
        periodic = background.PeriodicSync(lambda: 1 / 0, every_seconds=50, max_backoff_seconds=3600)
        with self.assertLogs("services.search.background", level="WARNING"):
            for _ in range(10):
                last = asyncio.run(periodic.tick(at(9, 14)))
        self.assertEqual(last, at(9, 14) + timedelta(seconds=3600))

    def test_background_runs_both_the_periodic_sync_and_the_nightly_job(self):
        started = []

        async def fake_loop(name, tick, **kwargs):
            started.append(name)

        with mock.patch.object(background, "run_due_loop", fake_loop):
            background.start_in_background(job=lambda: None, sync=lambda: None).join(5)

        self.assertEqual(sorted(started), sorted(["搜尋索引定期同步", "搜尋索引每日維護"]))

    def test_background_sync_shares_the_search_index_and_ignores_the_min_interval(self):
        index = mock.Mock()
        with mock.patch("services.search.index.default_index", return_value=index):
            background.sync_index()

        index.sync.assert_called_once_with(force=True)


class RunOnceTests(unittest.TestCase):
    def run_with(self, mode: str):
        index = mock.Mock(vector_store=object())
        index.sync.return_value = SyncReport(1, 0, 0)
        with mock.patch("services.search.index.default_index", return_value=index), \
                mock.patch("sys_settings.switches.current", return_value=SimpleNamespace(search_vector_mode=mode)), \
                mock.patch("services.search.embed.embed_pending") as embed:
            background.run_once()
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
