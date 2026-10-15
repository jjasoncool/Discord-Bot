"""停機收尾（discord_bot.MyBot.close：docker stop 送 SIGINT 後由 discord.py 呼叫）。

守的底線：
  1. 順序：先把 raw 備份寫進資料庫 → 停掉爬蟲通知、Telegram 轉發 → discord.py 的關閉（卸載 cog、斷語音、關 Discord 連線）
     → 停掉還在跑的工作 → 關共用的 StateDB（要在用它的工作都停了之後；不關的話行程退不出去）→ 再補寫一次 raw。
  2. Docker 只給 10 秒：每一步（包括 discord.py 的關閉）卡住、失敗都不擋後面，關 StateDB 一定會做；
     各步的時限加起來還留得下 asyncio.run 收尾的時間。第一次寫 raw 就逾時的話不再寫第二次（那批還在執行緒裡寫）。
  3. 只收尾一次：discord.py 之後再呼叫 close 時直接交給它，不重做一遍。

不連 Discord：discord.py 的關閉與各個停止函式都換成假的，記錄被呼叫的順序；時限調成幾十毫秒。
"""
import asyncio
import contextlib
import os
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from discord.ext import commands  # noqa: E402

import discord_bot  # noqa: E402
from music import player as music_player  # noqa: E402

FULL_ORDER = ["raw", "notify", "relay", "discord", "tasks", "statedb", "raw"]


async def hang():
    await asyncio.Event().wait()


class BudgetTests(unittest.TestCase):
    def test_real_time_limits_leave_room_inside_dockers_ten_seconds(self):
        self.assertLessEqual(discord_bot._SHUTDOWN_BUDGET + discord_bot._SHUTDOWN_TIMEOUTS["statedb"], 9,
                             "至少留 1 秒給 asyncio.run 收尾（等執行緒、關 event loop）")
        self.assertLess(music_player.CLOSE_LOOP_TIMEOUT + music_player.CLOSE_DISCONNECT_TIMEOUT,
                        discord_bot._SHUTDOWN_TIMEOUTS["discord"],
                        "音樂收尾在 discord.py 的關閉裡面，要放得進那一步的時限")


class BotCloseTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.order: list[str] = []
        patchers = [
            mock.patch.dict(discord_bot._SHUTDOWN_TIMEOUTS,
                            {"raw": 0.05, "intake": 0.05, "discord": 0.05, "tasks": 0.05, "statedb": 0.05}),
            mock.patch.object(discord_bot, "_SHUTDOWN_BUDGET", 0.5),
        ]
        for patcher in patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

    def _stopper(self, name, *, hang_forever=False, fail=False):
        async def stop():
            self.order.append(name)
            if hang_forever:
                await hang()
            if fail:
                raise RuntimeError("連不上")
        return SimpleNamespace(stop=stop)

    @contextlib.contextmanager
    def _patched(self, flush, *, discord_close=None):
        async def default_discord_close(_bot):
            self.order.append("discord")

        async def cancel_other_tasks(timeout):
            self.order.append("tasks")
            return 3

        async def close_shared_state_db():
            self.order.append("statedb")

        with mock.patch.object(commands.Bot, "close", new=discord_close or default_discord_close), \
             mock.patch.object(discord_bot, "cancel_other_tasks", new=cancel_other_tasks), \
             mock.patch("llm.storage.raw_message_store.flush_raw_buffer", new=flush), \
             mock.patch("services.state_db.close_shared_state_db", new=close_shared_state_db):
            yield

    async def _flush(self):
        self.order.append("raw")

    async def test_steps_run_in_order(self):
        bot = discord_bot.MyBot()
        bot._notify_server = self._stopper("notify")
        bot.telegram_relay_worker = self._stopper("relay")

        with self._patched(self._flush):
            await asyncio.wait_for(bot.close(), timeout=5)

        self.assertEqual(self.order, FULL_ORDER)

    async def test_stuck_or_failing_steps_do_not_block_closing_the_state_db(self):
        async def flush_stuck():
            self.order.append("raw")
            await hang()

        async def discord_close_stuck(_bot):
            self.order.append("discord")
            await hang()

        bot = discord_bot.MyBot()
        bot._notify_server = self._stopper("notify", hang_forever=True)
        bot.telegram_relay_worker = self._stopper("relay", fail=True)

        with self._patched(flush_stuck, discord_close=discord_close_stuck), \
                self.assertLogs("discord_bot", level="WARNING") as logs:
            await asyncio.wait_for(bot.close(), timeout=5)

        self.assertEqual(self.order, ["raw", "notify", "relay", "discord", "tasks", "statedb"],
                         "第一次寫 raw 就逾時：那批還在執行緒裡寫，不再排第二次")
        warnings = "\n".join(logs.output)
        for step in ("raw 訊息備份寫入", "停止 Notify Server", "連不上", "discord.py 的關閉"):
            self.assertIn(step, warnings)

    async def test_discord_close_raising_still_closes_the_state_db(self):
        async def discord_close_raises(_bot):
            self.order.append("discord")
            raise RuntimeError("關 Discord 連線失敗")

        bot = discord_bot.MyBot()

        with self._patched(self._flush, discord_close=discord_close_raises), \
                self.assertLogs("discord_bot", level="WARNING"):
            await asyncio.wait_for(bot.close(), timeout=5)

        self.assertEqual(self.order, ["raw", "discord", "tasks", "statedb", "raw"])

    async def test_without_notify_server_or_relay_the_rest_still_runs(self):
        bot = discord_bot.MyBot()   # 還沒連上 Discord 就停機：on_ready 沒跑，兩個入口都沒開

        with self._patched(self._flush):
            await asyncio.wait_for(bot.close(), timeout=5)

        self.assertEqual(self.order, ["raw", "discord", "tasks", "statedb", "raw"])

    async def test_second_close_goes_straight_to_discord(self):
        bot = discord_bot.MyBot()

        with self._patched(self._flush):
            await bot.close()
            self.order.clear()
            await bot.close()

        self.assertEqual(self.order, ["discord"])


class LateStartTests(unittest.IsolatedAsyncioTestCase):
    async def test_entry_points_are_not_started_once_shutdown_began(self):
        """啟動沒幾秒就停機：on_ready 還在跑，收尾已經跳過停 notify server 與轉發那一步，這時才開就沒人停。"""
        bot = discord_bot.MyBot()
        bot._shutdown_started = True

        with mock.patch("services.notify_server.NotifyServer") as notify_server, \
             mock.patch.object(discord_bot, "TelegramMessageRepository") as repository, \
             mock.patch.object(discord_bot, "MessageRelayWorker") as relay_worker:
            await discord_bot.auto_start_notify_server(bot)
            await discord_bot.auto_start_telegram_relay(bot)

        notify_server.assert_not_called()
        repository.assert_not_called()
        relay_worker.assert_not_called()
        self.assertIsNone(getattr(bot, "_notify_server", None))
        self.assertIsNone(bot.telegram_relay_worker)


if __name__ == "__main__":
    unittest.main()
