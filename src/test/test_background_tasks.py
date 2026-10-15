"""背景任務的統一入口（`utils/background_tasks.py`）：建任務、留參照、結束時看得到結果，該一直跑的掛了就重啟。

守的底線：
  - `spawn` 留著參照到做完為止（做完就放掉，不會越積越多）
  - `spawn` 的任務拋例外要記 ERROR，而且記得出是哪一個（名稱）；做完沒事不記；被取消不算失敗
  - `supervise` 的迴圈拋例外：記 ERROR、等一下重新呼叫 factory；間隔每次加倍、有上限；跑得夠久再掛的間隔重算
  - `supervise` 的迴圈自己結束：記 WARNING、不重啟
  - `supervise` 被取消：停下來、不重啟、不記 ERROR
  - `supervise` 第一次呼叫 factory 是當場呼叫：factory 本身寫錯會在呼叫端立刻炸，不會躲進背景一直重試
  - `periodic` 每隔固定秒數做一次、做失敗記 WARNING（含名稱）繼續、被取消就停
  - `cancel_all` 取消所有還在跑的
  - `cancel_other_tasks`（關機用）取消目前這個以外的所有 task（不只 spawn 建的）、等它們收尾才回來、不取消自己；
    把取消吞掉停不下來的不會讓它一直等
  - 守衛：結果被丟掉的 `asyncio.create_task(...)` 要被 `test_shared_conventions` 抓到（那條規則在那個檔測）

執行：
    cd src && python -m unittest test.test_background_tasks -v
"""

import asyncio
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from utils import background_tasks as bg  # noqa: E402

LOGGER = "utils.background_tasks"


class SpawnTests(unittest.IsolatedAsyncioTestCase):
    async def asyncTearDown(self):
        bg.cancel_all()
        await bg.wait_all(timeout=1)

    async def test_reference_is_kept_until_done_then_released(self):
        gate = asyncio.Event()

        async def job():
            await gate.wait()

        task = bg.spawn(job(), name="等門")
        await asyncio.sleep(0)
        self.assertIn("等門", bg.pending())
        self.assertIn(task, bg._tasks)

        gate.set()
        await task
        await asyncio.sleep(0)
        self.assertNotIn("等門", bg.pending())
        self.assertNotIn(task, bg._tasks)

    async def test_failure_is_logged_with_the_task_name(self):
        async def boom():
            raise ValueError("寫入失敗")

        with self.assertLogs(LOGGER, level="ERROR") as logs:
            task = bg.spawn(boom(), name="聊天記憶寫入")
            await asyncio.sleep(0)
            await asyncio.sleep(0)
        self.assertTrue(task.done())
        self.assertIn("聊天記憶寫入", logs.output[0])
        self.assertIn("ValueError", logs.output[0])
        self.assertIn("寫入失敗", logs.output[0])

    async def test_success_and_cancellation_are_not_errors(self):
        async def fine():
            return 1

        async def forever():
            await asyncio.sleep(3600)

        with self.assertNoLogs(LOGGER, level="WARNING"):
            ok = bg.spawn(fine(), name="沒事")
            await ok
            long = bg.spawn(forever(), name="被取消")
            await asyncio.sleep(0)
            long.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await long
            await asyncio.sleep(0)
        self.assertEqual(bg.pending(), [])


class SuperviseTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.calls = 0
        self.delays: list[float] = []
        self.now = 0.0

        async def fake_sleep(seconds):
            # 被取消之後還來睡＝把取消當成故障要重啟。這種任務殺不死，連測試收尾（取消所有任務）都會卡住，
            # 所以在這裡炸掉讓測試紅，而不是卡住。正確的實作被取消後不會再呼叫 sleep
            if asyncio.current_task().cancelling():
                raise AssertionError(f"取消後不該重啟（還去睡 {seconds} 秒）")
            self.delays.append(seconds)
            await asyncio.sleep(0)

        self.sleep = fake_sleep
        self.clock = lambda: self.now

    async def asyncTearDown(self):
        bg.cancel_all()
        await bg.wait_all(timeout=1)

    async def test_crashing_loop_is_logged_and_restarted_with_growing_delay(self):
        async def loop():
            self.calls += 1
            if self.calls <= 3:
                raise RuntimeError(f"第 {self.calls} 次掛")
            await asyncio.sleep(3600)

        with self.assertLogs(LOGGER, level="ERROR") as logs:
            bg.supervise(loop, name="Telegram 監聯", restart_after=5, max_restart_after=12, sleep=self.sleep,
                         clock=self.clock)
            for _ in range(12):
                await asyncio.sleep(0)

        self.assertEqual(self.calls, 4)                          # 掛三次、第四次活著
        self.assertEqual(self.delays, [5, 10, 12])               # 5 → 10 → 封頂 12
        self.assertEqual(len(logs.output), 3)
        self.assertIn("Telegram 監聯", logs.output[0])
        self.assertIn("第 1 次掛", logs.output[0])
        self.assertIn("5 秒後重新啟動", logs.output[0])

    async def test_delay_resets_after_a_long_healthy_run(self):
        async def loop():
            self.calls += 1
            if self.calls == 2:
                self.now += 600                                   # 第二次跑了 600 秒才掛
            if self.calls <= 2:
                raise RuntimeError("掛")
            await asyncio.sleep(3600)

        with self.assertLogs(LOGGER, level="ERROR"):
            bg.supervise(loop, name="迴圈", restart_after=5, healthy_after=60, sleep=self.sleep, clock=self.clock)
            for _ in range(10):
                await asyncio.sleep(0)

        self.assertEqual(self.delays, [5, 5])                    # 第二次沒有變成 10

    async def test_loop_that_returns_is_warned_and_not_restarted(self):
        async def loop():
            self.calls += 1

        with self.assertLogs(LOGGER, level="WARNING") as logs:
            task = bg.supervise(loop, name="忘了 while True", sleep=self.sleep)
            await task

        self.assertEqual(self.calls, 1)
        self.assertEqual(self.delays, [])
        self.assertEqual(len(logs.output), 1)
        self.assertIn("WARNING", logs.output[0])
        self.assertIn("忘了 while True", logs.output[0])

    async def test_cancel_stops_without_restart_or_error(self):
        started = asyncio.Event()

        async def loop():
            self.calls += 1
            started.set()
            await asyncio.sleep(3600)

        with self.assertNoLogs(LOGGER, level="WARNING"):
            task = bg.supervise(loop, name="要關機", sleep=self.sleep)
            await started.wait()
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            await asyncio.sleep(0)

        self.assertEqual(self.calls, 1)
        self.assertEqual(self.delays, [])

    async def test_factory_is_called_right_away_so_bad_arguments_fail_fast(self):
        order = []

        def factory():
            order.append("factory")
            return asyncio.sleep(3600)

        bg.supervise(factory, name="立刻建", sleep=self.sleep)
        self.assertEqual(order, ["factory"])                   # 還沒讓 event loop 跑，factory 就已經被叫了

        def broken():
            raise TypeError("參數錯了")

        with self.assertRaises(TypeError):
            bg.supervise(broken, name="寫錯", sleep=self.sleep)  # 在呼叫端炸，不是躲進背景

    async def test_cancel_all_cancels_everything_still_running(self):
        async def forever():
            await asyncio.sleep(3600)

        bg.spawn(forever(), name="a")
        bg.spawn(forever(), name="b")
        bg.supervise(forever, name="c", sleep=self.sleep)
        await asyncio.sleep(0)
        self.assertEqual(bg.pending(), ["a", "b", "c"])

        self.assertEqual(bg.cancel_all(), 3)
        await bg.wait_all(timeout=1)
        self.assertEqual(bg.pending(), [])


class PeriodicTests(unittest.IsolatedAsyncioTestCase):
    """固定間隔的定期工作：每隔幾秒做一次、失敗記 WARNING 繼續、取消就停。"""

    def setUp(self):
        self.slept: list[float] = []
        self.runs = 0

        async def fake_sleep(seconds):
            self.slept.append(seconds)
            if len(self.slept) >= 3:
                raise asyncio.CancelledError()   # 像 supervise 收掉迴圈

        async def job():
            self.runs += 1
            if self.runs == 1:
                raise RuntimeError("後端連不上")

        self.sleep, self.job = fake_sleep, job

    async def test_runs_every_interval_and_survives_a_failure(self):
        with self.assertLogs(LOGGER, level="WARNING") as logs:
            with self.assertRaises(asyncio.CancelledError):
                await bg.periodic(300, self.job, name="聊天記憶定期寫入", sleep=self.sleep)
        self.assertEqual(self.slept, [300, 300, 300])
        self.assertEqual(self.runs, 2, "第一次失敗後下一輪照常再做")
        self.assertEqual(len(logs.output), 1)
        self.assertIn("聊天記憶定期寫入", logs.output[0])
        self.assertIn("後端連不上", logs.output[0])


class CancelOtherTasksTests(unittest.IsolatedAsyncioTestCase):
    """關機用：取消目前這個以外還在跑的所有 task，等它們收尾；時間到就不再等。"""

    async def test_cancels_everything_but_the_caller_and_waits_for_their_cleanup(self):
        cleaned: list[str] = []

        async def worker(name):
            try:
                await asyncio.sleep(3600)
            finally:
                cleaned.append(name)

        plain = asyncio.create_task(worker("plain"))   # 不是 spawn 建的，例如 discord.py 派發事件的 task
        spawned = bg.spawn(worker("spawned"), name="spawned")
        await asyncio.sleep(0)

        stopped = await bg.cancel_other_tasks(timeout=5)

        self.assertEqual(stopped, 2)
        self.assertTrue(plain.cancelled())
        self.assertTrue(spawned.cancelled())
        self.assertEqual(sorted(cleaned), ["plain", "spawned"], "要等它們的 finally 跑完才回來")

    async def test_a_task_that_swallows_the_cancel_does_not_hold_it_up(self):
        release = asyncio.Event()
        # 斷言失敗時也要放它走：不然測試收尾會一直等這個 task，整個 unittest 卡住（啟動 gate 會永遠起不來）
        self.addCleanup(release.set)

        async def stubborn():
            while not release.is_set():
                try:
                    await asyncio.sleep(3600)
                except asyncio.CancelledError:
                    pass   # 像 discord.py 斷語音時把取消吞掉

        task = asyncio.create_task(stubborn())
        await asyncio.sleep(0)

        stopped = await asyncio.wait_for(bg.cancel_other_tasks(timeout=0.05), timeout=5)

        self.assertEqual(stopped, 1)
        self.assertFalse(task.done())
        release.set()
        task.cancel()
        await task


if __name__ == "__main__":
    unittest.main()
