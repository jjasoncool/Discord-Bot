"""Telegram 爬蟲：啟動時對好各頻道的「更新起點」，相簿才不會缺開頭（telegram_scraper/runner.py）。

守的底線：
- 啟動時先讀一次對話清單（`get_dialogs`），**在歷史掃描之前**：Telethon 要有各頻道的起點才看得出
  中間少了訊息、自己補回來；沒有起點時，起點會落在「啟動後第一則推送」，比它早的相簿開頭被當成
  已處理而略過（2026-10-05 根因分析：啟動後各頻道第一則即時漏收 53%）
- 監聽的頻道不在對話清單裡要記 WARNING（Telegram 不會即時推送它，只能靠補掃）
- 讀對話清單失敗不能擋住啟動，退回現況
- 每輪補掃前再對一次（起點被 Telethon 無聲刪掉時，最晚一輪補回）
- 啟動的歷史掃描也要上單則鎖：起點對好後 Telethon 會在掃描期間主動補抓並派發，會撞到同一則
- 讀對話清單要在連上之後（start 之後）：沒連線時讀不到，起點就沒對好
- 真 Telethon（只在爬蟲容器跑）：讀對話清單確實會設好頻道起點，已有的起點不被覆蓋——S1 成立的前提

bot 容器沒有 Telethon（用 telegram_scraper_fakes 的假模組）；爬蟲容器有真的，見該檔的執行方式。

執行：
    cd src && python -m unittest test.test_telegram_scraper_updates -v
"""
import asyncio
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from telegram_scraper_fakes import (  # noqa: E402
    CHANNEL, CHAT, REAL_TELETHON, FakeClient, FakeDB, FakeTelegramDatabase, FakeWatcher, fake_config, load_scraper, msg,
    photo_media,
)

S = load_scraper()
runner = S.runner


class RunnerTestBase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = tmp.name
        self.config = fake_config(self.tmp)
        self.watcher = FakeWatcher(self.config.media_dir)
        runner._catchup_chat_id_cache.clear()
        runner._catchup_chat_id_cache[CHANNEL] = CHAT
        self.addCleanup(runner._catchup_chat_id_cache.clear)
        S.handlers._chat_title_cache.clear()

    async def run_scraper(self, client, db=None):
        """跑完整的 run_telegram_scraper：client、DB、設定都換成假的；run_until_disconnected 立刻返回。"""
        db = db or FakeTelegramDatabase()
        db_class = mock.Mock(return_value=db)
        db_class.ensure_database_exists = FakeTelegramDatabase.ensure_database_exists
        with mock.patch.object(runner, "TelegramClient", lambda *a, **k: client), \
             mock.patch.object(runner, "TelegramDatabase", db_class), \
             mock.patch.object(runner, "TelegramRuntimeConfigWatcher", lambda **k: self.watcher):
            await runner.run_telegram_scraper(self.config)
        return db


class StartupPrimingTests(RunnerTestBase):
    async def test_startup_reads_dialogs_before_history_scan(self):
        client = FakeClient(history={CHANNEL: [msg(10, text="a")]})
        await self.run_scraper(client)
        names = [c[0] for c in client.calls]
        self.assertIn("get_dialogs", names, "啟動時要讀一次對話清單")
        self.assertLess(names.index("start"), names.index("get_dialogs"), "要連上之後才讀得到對話清單")
        self.assertLess(names.index("get_dialogs"), names.index("iter_messages"),
                        "要在歷史掃描之前：起點之前的由歷史掃描補，之後的由 Telethon 補，中間不留空窗")

    async def test_warns_when_listen_channel_missing_from_dialogs(self):
        client = FakeClient(history={CHANNEL: []}, dialogs=[SimpleNamespace(id=-100777, name="別的頻道")])
        with self.assertLogs("runner", "WARNING") as logs:
            await self.run_scraper(client)
        self.assertTrue(any(CHANNEL in line for line in logs.output), logs.output)

    async def test_dialog_failure_does_not_block_startup(self):
        client = FakeClient(history={CHANNEL: [msg(10, text="a")]}, dialogs_error=RuntimeError("網路斷了"))
        db = await self.run_scraper(client)
        self.assertIn((CHAT, 10), db.rows, "讀不到對話清單也要照常掃歷史")


class CatchUpRoundTests(RunnerTestBase):
    async def test_each_round_reprimes_before_scanning(self):
        db = FakeDB()
        db.add_row(5, has_media=False)
        client = FakeClient(history={CHANNEL: [msg(5), msg(6, text="新的")]})
        await runner._catch_up_round(client, self.config, self.watcher, db, [CHANNEL], runner.KeyedLock())
        names = [c[0] for c in client.calls]
        self.assertLess(names.index("get_dialogs"), names.index("iter_messages"))
        self.assertIn((CHAT, 6), db.rows, "補掃照常收下漏收的訊息")


class CatchUpLoopTests(RunnerTestBase):
    async def test_loop_runs_a_full_round_each_interval(self):
        """補掃迴圈每輪都要走 _catch_up_round（它會先再對一次起點），不能直接逐頻道補掃。"""
        sleeps = []

        async def fake_sleep(seconds):
            sleeps.append(seconds)
            if len(sleeps) > 1:
                raise asyncio.CancelledError()
        rounds = mock.AsyncMock()
        db, locks = FakeDB(), runner.KeyedLock()
        with mock.patch.object(runner, "asyncio", SimpleNamespace(sleep=fake_sleep, CancelledError=asyncio.CancelledError)), \
             mock.patch.object(runner, "_catch_up_round", rounds):
            with self.assertRaises(asyncio.CancelledError):
                await runner._catch_up_loop(FakeClient(), self.config, self.watcher, db, [CHANNEL], locks)
        rounds.assert_awaited_once_with(mock.ANY, self.config, self.watcher, db, [CHANNEL], locks)


class HistoryScanLockTests(RunnerTestBase):
    async def test_history_scan_holds_the_message_lock(self):
        held = []
        locks_made = []

        class SpyLock(runner.KeyedLock):
            def __init__(self):
                super().__init__()
                locks_made.append(self)

        async def fake_history(message, *args, **kwargs):
            lock = locks_made[0]._locks.get((message.chat_id, message.id))
            held.append(bool(lock and lock.locked()))
            return True

        client = FakeClient(history={CHANNEL: [msg(10), msg(11)]})
        with mock.patch.object(runner, "KeyedLock", SpyLock), \
             mock.patch.object(runner, "handle_history_message", fake_history):
            await self.run_scraper(client)
        self.assertEqual(held, [True, True], "歷史掃描處理每則時都要持有那則的鎖")


@unittest.skipUnless(REAL_TELETHON, "要真的 Telethon：在爬蟲容器用 docker exec 跑")
class RealTelethonDialogPrimingTests(unittest.IsolatedAsyncioTestCase):
    """S1 成立的前提：讀對話清單時 Telethon 會設好頻道的更新起點，已有的不覆蓋。
    用不連線的 client（StringSession、只覆寫送請求的那一層），不碰爬蟲的 session、不連 Telegram。"""

    async def test_reading_dialogs_sets_channel_pts(self):
        from telethon import TelegramClient
        from telethon.sessions import StringSession
        from telethon.tl import types

        channel_id = 2405953050

        class OfflineClient(TelegramClient):
            async def __call__(self, request, ordered=False, flood_sleep_threshold=None):
                return types.messages.Dialogs(
                    dialogs=[types.Dialog(
                        peer=types.PeerChannel(channel_id=channel_id), top_message=0, read_inbox_max_id=0,
                        read_outbox_max_id=0, unread_count=0, unread_mentions_count=0, unread_reactions_count=0,
                        unread_poll_votes_count=0, notify_settings=types.PeerNotifySettings(), pts=555)],
                    messages=[],
                    chats=[types.Channel(id=channel_id, title="Seele", photo=types.ChatPhotoEmpty(),
                                         date=datetime.now(timezone.utc), access_hash=777, broadcast=True)],
                    users=[])

        client = OfflineClient(StringSession(), 1, "x")
        runner._catchup_chat_id_cache.clear()
        runner._catchup_chat_id_cache[CHANNEL] = -1000000000000 - channel_id
        self.addCleanup(runner._catchup_chat_id_cache.clear)
        self.assertNotIn(channel_id, client._message_box.map)
        self.assertTrue(await runner._prime_update_state(client, [CHANNEL], startup=True),
                        "監聽頻道在對話清單裡（Dialog.id 是帶 -100 前綴的 id）")
        self.assertEqual(client._message_box.map[channel_id].pts, 555, "讀對話清單要設好頻道起點")
        client._message_box.map[channel_id].pts = 999
        await runner._prime_update_state(client, [CHANNEL], startup=False)
        self.assertEqual(client._message_box.map[channel_id].pts, 999, "已有的起點不能被覆蓋")


if __name__ == "__main__":
    unittest.main()
