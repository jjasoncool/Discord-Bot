"""telegram-scraper 的停止流程（`telegram_scraper/main.py` 的 `run_until_stopped`）。

守的底線：
  - 容器收到 SIGTERM（`docker stop`）走正常的取消路徑：主要工作被取消、它的收尾（Telethon 斷線、關 DB）跑完、
    行程乾淨結束，不是等 10 秒被 SIGKILL
  - SIGINT（Ctrl+C，首次登入的互動模式）同樣處理
  - 不是訊號造成的取消照樣往外丟，不會被吞掉
  - 結束後不留訊號 handler
  - 收尾不能卡住：runner 停止時要歸還掛 LISTEN 的那條 pool 連線（pool.close() 會等它），
    連線池關閉有時間上限、逾時就強制切斷——不然 10 秒寬限一到就是 SIGKILL

bot 容器沒有 Telethon（用 telegram_scraper_fakes 的假模組）；在爬蟲容器跑的方式見該檔開頭。

執行：
    cd src && python -m unittest test.test_telegram_scraper_stop -v
"""
import asyncio
import importlib.util
import os
import signal
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
for path in (HERE, SRC_DIR):
    if path not in sys.path:
        sys.path.insert(0, path)

from telegram_scraper_fakes import CHANNEL, CHAT, FakeClient, FakeTelegramDatabase, FakeWatcher, fake_config, load_scraper  # noqa: E402
from test import timing_sensitive  # noqa: E402


def load_main():
    """main.py 用裸 import 找 runner、tg_config：先讓 fakes 裝好假 telethon、把爬蟲目錄加進路徑，
    再以獨立的模組名載入（不叫 `main`，免得和別的 main 撞名）。"""
    load_scraper()
    for candidate in (os.path.join(SRC_DIR, "telegram_scraper", "main.py"), "/app/main.py"):
        if os.path.isfile(candidate):
            spec = importlib.util.spec_from_file_location("telegram_scraper_main", candidate)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
    raise FileNotFoundError("找不到 telegram_scraper/main.py")


class RunUntilStoppedTests(unittest.TestCase):
    def setUp(self):
        self.tg_main = load_main()
        self.cleanup_ran = False
        self.started = None

    async def job(self):
        if self.started is not None:
            self.started.set()
        try:
            await asyncio.sleep(60)
        finally:
            self.cleanup_ran = True

    def _stop_with(self, sig):
        self.too_late = False

        async def scenario():
            loop = asyncio.get_running_loop()
            loop.call_later(0.05, os.kill, os.getpid(), sig)
            # 1 秒還沒停就算失敗：不能靠 wait_for 的逾時替它收尾（那也是取消，程式會當成訊號造成的乾淨停止）
            loop.call_later(1.0, setattr, self, "too_late", True)
            await asyncio.wait_for(self.tg_main.run_until_stopped(self.job()), timeout=5)
        asyncio.run(scenario())
        self.assertFalse(self.too_late, "收到訊號後 1 秒內沒有停下來")

    @timing_sensitive
    def test_sigterm_cancels_the_job_and_its_cleanup_runs(self):
        self._stop_with(signal.SIGTERM)   # 沒丟例外＝乾淨結束
        self.assertTrue(self.cleanup_ran)

    @timing_sensitive
    def test_sigint_is_handled_the_same_way(self):
        self._stop_with(signal.SIGINT)
        self.assertTrue(self.cleanup_ran)

    def test_cancellation_without_a_signal_is_not_swallowed(self):
        async def scenario():
            self.started = asyncio.Event()
            task = asyncio.ensure_future(self.tg_main.run_until_stopped(self.job()))
            await self.started.wait()   # job 真的跑起來才取消，不然 finally 根本沒進去
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        asyncio.run(scenario())
        self.assertTrue(self.cleanup_ran)

    def test_handlers_are_removed_afterwards(self):
        async def scenario():
            async def quick():
                return None
            await self.tg_main.run_until_stopped(quick())
            loop = asyncio.get_running_loop()
            # remove 回 False＝沒有登記中的 handler
            return loop.remove_signal_handler(signal.SIGTERM), loop.remove_signal_handler(signal.SIGINT)
        self.assertEqual(asyncio.run(scenario()), (False, False))


class _FakePool:
    """記下 acquire／release 的順序；release 之外的操作都不需要。"""

    def __init__(self):
        self.conn = mock.AsyncMock(name="listen_conn")
        self.events: list[str] = []

    async def acquire(self):
        self.events.append("acquire")
        return self.conn

    async def release(self, conn):
        assert conn is self.conn
        self.events.append("release")


class ShutdownReleasesListenConnectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_listen_connection_is_released_before_the_pool_closes(self):
        S = load_scraper()
        runner = S.runner
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        config = fake_config(tmp.name)
        watcher = FakeWatcher(config.media_dir)
        runner._catchup_chat_id_cache.clear()
        runner._catchup_chat_id_cache[CHANNEL] = CHAT
        self.addCleanup(runner._catchup_chat_id_cache.clear)

        pool = _FakePool()

        class DB(FakeTelegramDatabase):
            def __init__(self, *a, **k):
                super().__init__()
                self.pool = pool

            async def close(self):
                pool.events.append("close")

        db_class = mock.Mock(return_value=DB())
        db_class.ensure_database_exists = FakeTelegramDatabase.ensure_database_exists
        with mock.patch.object(runner, "TelegramClient", lambda *a, **k: FakeClient()), \
             mock.patch.object(runner, "TelegramDatabase", db_class), \
             mock.patch.object(runner, "TelegramRuntimeConfigWatcher", lambda **k: watcher):
            await runner.run_telegram_scraper(config)   # run_until_disconnected 立刻返回，等於正常停止

        self.assertEqual(pool.events, ["acquire", "release", "close"])


class PoolCloseHasATimeLimitTests(unittest.IsolatedAsyncioTestCase):
    def _db(self, pool):
        load_scraper()
        import db as db_module   # 爬蟲模組用裸 import，load_scraper 已把目錄加進路徑
        database = db_module.TelegramDatabase("postgresql://unused")
        database.pool = pool
        return database

    async def test_hanging_close_is_cut_off_by_terminate(self):
        class HangingPool:
            terminated = False

            async def close(self):
                await asyncio.Event().wait()   # 有連線沒歸還：永遠等不到

            def terminate(self):
                self.terminated = True

        pool = HangingPool()
        database = self._db(pool)
        await asyncio.wait_for(database.close(timeout=0.05), timeout=5)
        self.assertTrue(pool.terminated)
        self.assertIsNone(database.pool)

    async def test_clean_close_does_not_terminate(self):
        class QuickPool:
            terminated = False
            closed = False

            async def close(self):
                self.closed = True

            def terminate(self):
                self.terminated = True

        pool = QuickPool()
        database = self._db(pool)
        await database.close(timeout=0.05)
        self.assertTrue(pool.closed)
        self.assertFalse(pool.terminated)


if __name__ == "__main__":
    unittest.main()
