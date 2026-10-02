"""到期迴圈（utils.due_loop.run_due_loop）。

守的底線：
  1. 先等 bot 準備好，接著馬上做一次：停機期間錯過的到期項目在啟動時補做。
  2. 睡到 tick 回傳的時刻（多 1 秒，避免醒太早又空轉），但不超過 max_sleep；
     沒有下一個時刻就睡 max_sleep；時刻已經過了也至少睡 1 秒，不會原地狂轉。
  3. tick 出錯只記 log，隔 retry_after 再試，排程不會就此停掉。
"""

import asyncio
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from utils.due_loop import run_due_loop  # noqa: E402

T0 = datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc)


class _Stop(Exception):
    pass


def _run(results, *, max_sleep=3600, retry_after=300, rounds=None, wait_ready=None):
    """依序讓 tick 回傳 results 裡的值（Exception 就拋出），回傳 (tick 收到的時刻, 每次睡的秒數)。"""
    clock = {"now": T0}
    ticks, sleeps = [], []
    results = list(results)
    rounds = len(results) if rounds is None else rounds

    async def tick(now):
        ticks.append(now)
        value = results.pop(0)
        if isinstance(value, Exception):
            raise value
        return value

    async def sleep(seconds):
        sleeps.append(seconds)
        clock["now"] += timedelta(seconds=seconds)
        if len(sleeps) >= rounds:
            raise _Stop

    async def main():
        with_ready = {} if wait_ready is None else {"wait_ready": wait_ready}
        try:
            await run_due_loop("測試", tick, max_sleep=max_sleep, retry_after=retry_after,
                               now=lambda: clock["now"], sleep=sleep, **with_ready)
        except _Stop:
            pass

    asyncio.run(main())
    return ticks, sleeps


class DueLoopTests(unittest.TestCase):

    def test_waits_until_ready_then_ticks_immediately(self):
        order = []

        async def wait_ready():
            order.append("ready")

        ticks, sleeps = _run([None], wait_ready=wait_ready, rounds=1)

        self.assertEqual(order, ["ready"])
        self.assertEqual(ticks[0], T0)  # 啟動當下就做一次，不是先睡
        self.assertEqual(len(sleeps), 1)

    def test_sleeps_until_the_returned_time_capped_by_max_sleep(self):
        _, sleeps = _run([
            T0 + timedelta(minutes=10),   # 10 分鐘後
            T0 + timedelta(days=3),       # 很遠 → 上限
            None,                         # 沒有下一個 → 上限
            T0 - timedelta(hours=1),      # 已經過了 → 至少 1 秒
        ], max_sleep=3600)

        self.assertEqual(sleeps[0], 601)
        self.assertEqual(sleeps[1:3], [3600, 3600])
        self.assertEqual(sleeps[3], 1)

    def test_errors_are_logged_and_retried(self):
        with self.assertLogs("utils.due_loop", level="ERROR"):
            ticks, sleeps = _run([RuntimeError("boom"), None], retry_after=300)

        self.assertEqual(len(ticks), 2)  # 出錯後還有下一輪
        self.assertEqual(sleeps[0], 300)


if __name__ == "__main__":
    unittest.main()
