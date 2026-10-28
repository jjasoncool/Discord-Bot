"""Telegram relay media group（相簿）收集與補圖的單元測試（假 repository / publisher，不需 DB、Discord）。

背景：scraper 逐則寫入相簿組員（先寫訊息列、下載完才寫媒體列），舊版 relay 只要 0.5 秒
數量沒變就合併送出，晚到的組員被當成「交由首則處理」丟掉 → 相簿只發出前 1~2 張。

也守「發文太久的不送」：爬蟲補掃替發文少的頻道補進幾個月前的訊息時，單則、相簿都不送進頻道，
記成頻道 0 讓重啟的補償不再撿回來；人指定的重送照送。

執行：
    cd src && python -m unittest test.test_telegram_relay_media_group -v
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

from services.relay.telegram_relay_service import MessageRelayWorker
from sys_settings.telegram_relay_settings import TelegramRelaySettings
from telegram_scraper.media_download import MEDIA_RETRY_WINDOW
from test import timing_sensitive
from test.fake_clock import FakeClock
from test.telegram_relay_fakes import CHANNEL, make_worker, media_of


class ScraperAgreementTests(unittest.TestCase):
    def test_followup_age_matches_scraper_retry_window(self):
        """爬蟲補掃重試、補到圖再通知都只做到發文後這段時間；轉發端補圖的時限若比它長，等不到圖，
        比它短，爬蟲補到圖的通知會被轉發端丟掉。兩邊在不同容器，只能靠這裡守住一致。"""
        self.assertEqual(MessageRelayWorker._GROUP_FOLLOWUP_MAX_AGE, MEDIA_RETRY_WINDOW)


class MediaGroupCollectTests(unittest.IsolatedAsyncioTestCase):

    async def test_members_written_one_by_one_are_sent_together(self):
        # 重現 GameData #3223：8 張逐則進來，每張「列先到、媒體後到」，間隔短於安靜期。
        # 用假時鐘：worker 的輪詢與餵料的間隔都是虛擬時間，機器忙不忙結果都一樣
        worker, repo, _, publisher = make_worker()
        clock = FakeClock()
        worker._clock, worker._sleep = clock.now, clock.sleep
        pks = list(range(901, 909))
        repo.add_ready(pks[0], 5001, text="相簿說明")

        async def scraper():
            for i, pk in enumerate(pks[1:], start=1):
                await clock.sleep(0.03)
                repo.add_row(pk, 5001 + i)
                await clock.sleep(0.03)
                repo.add_media(pk)

        feeder = asyncio.create_task(scraper())
        await worker._process_one(pks[0])
        await feeder

        self.assertEqual(len(publisher.plans), 1)
        self.assertEqual(publisher.plans[0]["media"], media_of(*pks))
        self.assertEqual(publisher.plans[0]["title_suffix"], "")
        self.assertTrue(all((pk, CHANNEL) in repo.delivered for pk in pks))

    @timing_sensitive
    async def test_waits_for_member_whose_media_is_not_written_yet(self):
        # 組員數早就不變，但最後一則的媒體還在下載：不能先發
        worker, repo, _, publisher = make_worker()
        repo.add_ready(1, 100)
        repo.add_row(2, 101)

        async def finish_download():
            await asyncio.sleep(0.3)  # 超過安靜期好幾倍
            repo.add_media(2)

        feeder = asyncio.create_task(finish_download())
        await worker._process_one(1)
        await feeder

        self.assertEqual(len(publisher.plans), 1)
        self.assertEqual(publisher.plans[0]["media"], media_of(1, 2))

    @timing_sensitive
    async def test_member_arriving_during_collection_does_not_block_or_duplicate(self):
        worker, repo, _, publisher = make_worker()
        repo.add_ready(1, 100)
        repo.add_ready(2, 101)

        collector = asyncio.create_task(worker._process_one(1))
        await asyncio.sleep(0.02)
        # 組員 2 的 NOTIFY 在收集中到達：應立即返回，不等收集者
        await asyncio.wait_for(worker._process_one(2), timeout=0.05)
        await collector

        self.assertEqual(len(publisher.plans), 1)
        self.assertEqual(publisher.plans[0]["media"], media_of(1, 2))

    async def test_member_arriving_while_sending_is_sent_as_followup(self):
        worker, repo, _, publisher = make_worker()
        repo.add_ready(1, 100)
        repo.add_ready(2, 101)
        publisher.delay = 0.05

        def late_member_arrives():
            # 首批送出途中，第 3 張才寫進 DB 並 NOTIFY
            if len(publisher.plans) == 1:
                repo.add_ready(3, 102)
                asyncio.get_running_loop().create_task(worker._process_one(3))

        publisher.on_publish = late_member_arrives
        await worker._process_one(1)

        self.assertEqual([p["media"] for p in publisher.plans], [media_of(1, 2), media_of(3)])
        self.assertEqual(publisher.plans[1]["title_suffix"], "（補圖）")
        self.assertIn((3, CHANNEL), repo.delivered)

    async def test_late_member_after_group_sent_is_followup_not_dropped(self):
        # 舊版在這裡走「交由首則處理」直接丟棄
        worker, repo, _, publisher = make_worker()
        repo.add_ready(1, 100)
        repo.add_ready(2, 101)
        repo.mark(1)
        repo.mark(2)
        repo.add_ready(3, 102)

        await worker._process_one(3)

        self.assertEqual(len(publisher.plans), 1)
        self.assertEqual(publisher.plans[0]["media"], media_of(3))
        self.assertEqual(publisher.plans[0]["title_suffix"], "（補圖）")

    async def test_timeout_sends_ready_members_and_leaves_rest_for_followup(self):
        worker, repo, _, publisher = make_worker()
        worker._GROUP_MAX_WAIT_SEC = 0.2
        repo.add_ready(1, 100)
        repo.add_row(2, 101)  # 下載一直沒完成

        await worker._process_one(1)
        self.assertEqual(publisher.plans[0]["media"], media_of(1))
        self.assertNotIn((2, CHANNEL), repo.delivered)

        # 之後下載完成、NOTIFY 到達 → 以補圖送出
        repo.add_media(2)
        await worker._process_one(2)
        self.assertEqual(publisher.plans[1]["media"], media_of(2))
        self.assertEqual(publisher.plans[1]["title_suffix"], "（補圖）")

    async def test_stale_followup_is_skipped_without_waiting(self):
        # 重啟時 reconcile 會排入舊相簿沒標記的組員：過了補圖時效就不發，也不空等安靜期
        worker, repo, _, publisher = make_worker()
        worker._GROUP_QUIET_SEC = 5.0
        repo.add_ready(1, 100)
        repo.add_ready(2, 101)
        repo.mark(1, datetime.now(timezone.utc) - timedelta(hours=13))

        await asyncio.wait_for(worker._process_one(2), timeout=0.5)

        self.assertEqual(publisher.plans, [])
        self.assertNotIn((2, CHANNEL), repo.delivered)

    async def test_fully_delivered_group_exits_without_waiting(self):
        worker, repo, _, publisher = make_worker()
        worker._GROUP_QUIET_SEC = 5.0
        repo.add_ready(1, 100)
        repo.add_ready(2, 101)
        repo.mark(1)
        repo.mark(2)

        await asyncio.wait_for(worker._process_one(2), timeout=0.5)
        self.assertEqual(publisher.plans, [])

    async def test_force_replay_sends_group_once(self):
        worker, repo, routes, publisher = make_worker()
        routes.replay_msg_id = 100
        repo.replay_pk = 1
        repo.add_ready(1, 100)
        repo.add_ready(2, 101)
        repo.mark(1)
        repo.mark(2)

        await worker._process_one(1)
        await worker._process_one(2)  # 重送模式會把每個組員都排入，第二則不可再送一次

        self.assertEqual(len(publisher.plans), 1)
        self.assertEqual(publisher.plans[0]["media"], media_of(1, 2))

    async def test_caption_is_kept_when_first_member_has_text(self):
        worker, repo, _, publisher = make_worker()
        repo.add_ready(1, 100, text="公告")
        repo.add_ready(2, 101)

        await worker._process_one(2)  # 由非首則觸發也一樣整組送出

        self.assertEqual(publisher.plans[0]["text"], "公告")
        self.assertEqual(publisher.plans[0]["media"], media_of(1, 2))


class SingleMessageTests(unittest.IsolatedAsyncioTestCase):

    async def test_single_message_sent_once(self):
        worker, repo, _, publisher = make_worker()
        repo.add_ready(9, 200, grouped_id=None, text="hi")

        await worker._process_one(9)
        worker._processed_set.clear()
        await worker._process_one(9)  # 已有 delivery 記錄 → 不重送

        self.assertEqual(len(publisher.plans), 1)
        self.assertIn((9, CHANNEL), repo.delivered)


class StaleMessageTests(unittest.IsolatedAsyncioTestCase):
    """發文超過 `max_message_age_days` 的不送；期限內的、重送模式的照送。"""

    def _days_ago(self, days: float) -> datetime:
        return datetime.now(timezone.utc) - timedelta(days=days)

    def _limit(self) -> float:
        return TelegramRelaySettings().max_message_age_days

    async def test_old_single_message_is_not_sent_and_stops_tracking(self):
        worker, repo, _, publisher = make_worker()
        repo.add_ready(9, 200, grouped_id=None, text="三月的爆料", date=self._days_ago(self._limit() + 1))

        await worker._process_one(9)

        self.assertEqual(publisher.plans, [])
        # 頻道 0＝停止追蹤：重啟補償只撈完全沒紀錄的，有這列就不會再撿回來
        self.assertEqual(repo.channels_of(9), {0})

    async def test_old_album_is_not_sent(self):
        worker, repo, _, publisher = make_worker()
        old = self._days_ago(self._limit() + 1)
        repo.add_ready(1, 100, date=old)
        repo.add_ready(2, 101, date=old)

        await worker._process_one(1)
        await worker._process_one(2)

        self.assertEqual(publisher.plans, [])
        self.assertEqual(repo.channels_of(1), {0})
        self.assertEqual(repo.channels_of(2), {0})

    async def test_message_within_limit_is_sent(self):
        worker, repo, _, publisher = make_worker()
        repo.add_ready(9, 200, grouped_id=None, text="上週的爆料", date=self._days_ago(self._limit() - 1))

        await worker._process_one(9)

        self.assertEqual(len(publisher.plans), 1)
        self.assertEqual(repo.channels_of(9), {CHANNEL})

    async def test_force_replay_sends_old_message(self):
        worker, repo, routes, publisher = make_worker()
        routes.replay_msg_id = 200
        repo.replay_pk = 9
        repo.add_ready(9, 200, grouped_id=None, text="指定重送", date=self._days_ago(self._limit() + 30))

        await worker._process_one(9)

        self.assertEqual(len(publisher.plans), 1)
        self.assertIn((9, CHANNEL), repo.delivered)


if __name__ == "__main__":
    unittest.main()
