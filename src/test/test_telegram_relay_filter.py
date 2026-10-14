"""Telegram 轉發端接上 LLM 過濾與隔離區（services/relay/telegram_relay_service.py、telegram_quarantine.py）。

守的底線：
- 判成垃圾的（正式模式）送進主頻道底下的「垃圾訊息」thread，最上面一行「判定：標籤｜理由」，主頻道沒有；
  發送紀錄記 thread 的 id。放行的照常送主頻道。只記錄模式、沒開過濾都照常送主頻道
- 每個發送單位判一次：相簿整本判一次、整本一起去同一處
- 晚到的圖跟著同一本的去向（隔離的進同一個 thread、放行的進主頻道），以「（補圖）」送出、不再判
- 被隔離的再被排進來（爬蟲通知、輪詢、重啟補償）不重判、不重貼；thread 被刪重建後，舊紀錄仍認得出來
- 沒看到完整內容不判、照常送：相簿等待逾時只到齊一部分、單則的圖等太久還沒到（只看一部分會錯關情報）
- 單則有圖標示、圖還沒下載到：先不送、不判、不記成處理過，等爬蟲補到圖的通知；有文字的滿 30 分鐘先送文字，
  沒文字的等到補圖時限
- 隔離 thread 開在主頻道底下、7 天才封存，之後一直用同一個（重啟也是）；封存的先解封；開不了就這次不送、
  不寫紀錄（之後重試），主頻道也不送
- 一次性搬移腳本（只走 HTTP、沒有 thread 快取）也找得到開著的那個；腳本與 bot 各自記 thread 時不互相蓋掉
- 要補判（每則訊息都要被檢查過）：正式模式下模型沒判到（沒回應、出錯、看不懂）照常送主頻道，
  紀錄記成要補判（`needs_recheck`）；補判判成垃圾就搬進隔離區（主頻道原貼文刪掉）、判成情報就清掉；還是判不到的留著、不一則一則
  再問；看不了的檔案、只記錄模式不記；相簿過了補圖時效才搬；模型一回應就叫醒補判；判成垃圾卻搬不動的清掉並記 log
- 開了過濾一次只處理一則（模型一次只能判一則，並行只會打亂順序）；排隊或處理中又收到的通知，處理完再排一次

執行：
    cd src && python -m unittest test.test_telegram_relay_filter -v
"""
import asyncio
import json
import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from services.relay.telegram_filter import Verdict
from services.relay.telegram_quarantine import QuarantineThreads
from test.telegram_relay_fakes import CHANNEL, FakeBot, FakeFilter, make_worker, media_of


def ago(**kwargs) -> datetime:
    return datetime.now(timezone.utc) - timedelta(**kwargs)


class FilterTestBase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.filter = FakeFilter("on")
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        self.runtime = str(Path(tmp) / "quarantine_runtime.json")
        self.bot = FakeBot()
        self.worker, self.repo, self.routes, self.publisher = make_worker(
            content_filter=self.filter, quarantine=True, bot=self.bot, runtime_path=self.runtime,
        )

    def thread(self):
        threads = self.bot.main.all_threads
        return threads[-1] if threads else None

    def restart(self):
        """用同一份資料庫與 runtime 檔開新的 worker（記憶體裡的處理紀錄清空）。"""
        self.worker, _, self.routes, self.publisher = make_worker(
            content_filter=self.filter, quarantine=True, bot=self.bot, repo=self.repo, runtime_path=self.runtime,
        )


class SingleMessageTests(FilterTestBase):
    async def test_junk_goes_to_quarantine_thread_with_verdict_line(self):
        self.repo.add_row(9, 200, grouped_id=None, text="今日首水", has_media=False)
        self.filter.quarantine(9, "灌水", "每日打卡")
        await self.worker._process_one(9)

        thread = self.thread()
        self.assertIsNotNone(thread)
        self.assertEqual(thread.name, "垃圾訊息")
        self.assertEqual(self.publisher.to(CHANNEL), [], "主頻道不能出現垃圾")
        [plan] = self.publisher.to(thread.id)
        self.assertEqual(plan.header, "判定：灌水｜每日打卡")
        self.assertEqual(self.repo.channels_of(9), {thread.id})

    async def test_info_goes_to_main_channel(self):
        self.repo.add_row(9, 200, grouped_id=None, text="已开服", has_media=False)
        await self.worker._process_one(9)
        self.assertEqual(len(self.publisher.to(CHANNEL)), 1)
        self.assertEqual(self.publisher.to(CHANNEL)[0].header, "")
        self.assertIsNone(self.thread(), "放行的不必開隔離 thread")
        self.assertEqual(self.repo.channels_of(9), {CHANNEL})

    async def test_dry_run_and_off_send_to_main(self):
        for mode in ("dry_run", "off"):
            with self.subTest(mode=mode):
                self.setUp()
                self.filter.mode = mode
                self.repo.add_row(9, 200, grouped_id=None, text="今日首水", has_media=False)
                self.filter.quarantine(9)
                await self.worker._process_one(9)
                self.assertEqual(len(self.publisher.to(CHANNEL)), 1)
                self.assertIsNone(self.thread())
                self.assertEqual(len(self.filter.calls), 1 if mode == "dry_run" else 0)

    async def test_quarantined_single_is_not_judged_or_posted_again(self):
        self.repo.add_row(9, 200, grouped_id=None, text="今日首水", has_media=False)
        self.filter.quarantine(9)
        await self.worker._process_one(9)
        self.restart()
        await self.worker._process_one(9)
        self.assertEqual(len(self.filter.calls), 1, "重啟後再排進來不能重判")
        self.assertEqual(self.publisher.sent, [], "也不能再貼一次或改送主頻道")

    async def test_thread_cannot_be_opened_sends_nothing_and_records_nothing(self):
        self.bot.main.fail_create = True
        self.repo.add_row(9, 200, grouped_id=None, text="今日首水", has_media=False)
        self.filter.quarantine(9)
        await self.worker._process_one(9)
        self.assertEqual(self.publisher.sent, [])
        self.assertEqual(self.repo.channels_of(9), set(), "不寫紀錄，之後重試")

    async def test_send_failure_records_nothing(self):
        self.repo.add_row(9, 200, grouped_id=None, text="已开服", has_media=False)
        self.publisher.fail_channels.add(CHANNEL)
        await self.worker._process_one(9)
        self.assertEqual(self.repo.channels_of(9), set())


class WaitForMediaTests(FilterTestBase):
    async def test_image_not_downloaded_yet_is_left_for_later(self):
        self.repo.add_row(9, 200, grouped_id=None, text="水", date=ago(minutes=5))
        await self.worker._process_one(9)
        self.assertEqual(self.publisher.sent, [])
        self.assertEqual(self.filter.calls, [], "圖還沒到不判（只看文字會錯關設計稿那種）")
        self.assertFalse(self.worker._seen_processed(9), "不能記成處理過，爬蟲補到圖的通知才進得來")

        self.repo.add_media(9)          # 爬蟲補到圖、通知
        await self.worker._process_one(9)
        self.assertEqual(len(self.filter.calls), 1)
        self.assertEqual(self.filter.calls[0]["media"], ["9.jpg"], "文字和圖一起判")
        self.assertEqual(self.publisher.to(CHANNEL)[0]["media"], media_of(9), "文字和圖一起送")

    async def test_text_single_waits_30_minutes_then_text_goes_unjudged(self):
        self.repo.add_row(9, 200, grouped_id=None, text="今日首水", date=ago(minutes=31))
        self.filter.quarantine(9)
        await self.worker._process_one(9)
        self.assertEqual(self.filter.calls, [], "沒看到圖不判")
        self.assertEqual(len(self.publisher.to(CHANNEL)), 1, "等滿 30 分鐘先送文字")

    async def test_textless_single_waits_up_to_12_hours(self):
        self.repo.add_row(9, 200, grouped_id=None, date=ago(hours=2))
        await self.worker._process_one(9)
        self.assertEqual(self.publisher.sent, [])
        self.assertFalse(self.worker._seen_processed(9), "沒文字的不能被當成空訊息記成處理過")

        self.repo.add_row(10, 201, grouped_id=None, date=ago(hours=13))
        await self.worker._process_one(10)
        self.assertEqual(self.publisher.sent, [])
        self.assertTrue(self.worker._seen_processed(10), "超過補圖時限才當空訊息略過")


class AlbumTests(FilterTestBase):
    async def test_album_judged_once_and_sent_together(self):
        for pk in (1, 2, 3):
            self.repo.add_ready(pk, 100 + pk, text="說明" if pk == 1 else "")
        self.filter.quarantine(1, "無關圖片", "奶龍")
        await self.worker._process_one(2)

        self.assertEqual(len(self.filter.calls), 1, "整本判一次")
        self.assertEqual(self.filter.calls[0]["text"], "說明")
        self.assertEqual(self.filter.calls[0]["media"], ["1.jpg", "2.jpg", "3.jpg"])
        thread = self.thread()
        [plan] = self.publisher.to(thread.id)
        self.assertEqual(plan["media"], media_of(1, 2, 3))
        self.assertEqual(plan.header, "判定：無關圖片｜奶龍")
        self.assertEqual(self.publisher.to(CHANNEL), [])

    async def test_late_image_of_quarantined_album_follows_into_thread(self):
        self.repo.add_ready(1, 101)
        self.repo.add_ready(2, 102)
        self.filter.quarantine(1)
        await self.worker._process_one(1)
        thread = self.thread()

        self.repo.add_ready(3, 103)     # 晚到的組員
        await self.worker._process_one(3)
        self.assertEqual(len(self.filter.calls), 1, "補圖不再判")
        plans = self.publisher.to(thread.id)
        self.assertEqual([p["media"] for p in plans], [media_of(1, 2), media_of(3)])
        self.assertEqual(plans[1]["title_suffix"], "（補圖）")
        self.assertEqual(self.publisher.to(CHANNEL), [], "不能被當成新相簿送進主頻道")

    async def test_late_image_of_passed_album_follows_into_main(self):
        self.repo.add_ready(1, 101)
        await self.worker._process_one(1)
        self.repo.add_ready(2, 102)
        self.filter.quarantine(1)       # 就算現在判會不同，補圖也不再判
        await self.worker._process_one(2)
        self.assertEqual(len(self.filter.calls), 1)
        self.assertEqual([p["media"] for p in self.publisher.to(CHANNEL)], [media_of(1), media_of(2)])

    async def test_quarantined_album_requeued_after_restart_is_left_alone(self):
        self.repo.add_ready(1, 101)
        self.repo.add_ready(2, 102)
        self.filter.quarantine(1)
        await self.worker._process_one(1)
        self.restart()
        await self.worker._process_one(2)
        self.assertEqual(len(self.filter.calls), 1)
        self.assertEqual(len(self.publisher.sent), 0)

    async def test_partial_album_after_timeout_is_not_judged(self):
        self.worker._GROUP_MAX_WAIT_SEC = 0.2
        self.repo.add_ready(1, 101, text="水")
        self.repo.add_row(2, 102)       # 下載一直沒完成
        self.filter.quarantine(1)
        await self.worker._process_one(1)
        self.assertEqual(self.filter.calls, [], "只到齊一部分不判")
        self.assertEqual(self.publisher.to(CHANNEL)[0]["media"], media_of(1))

    async def test_late_image_goes_to_rebuilt_thread(self):
        self.repo.add_ready(1, 101)
        self.repo.add_ready(2, 102)
        self.filter.quarantine(1)
        await self.worker._process_one(1)
        old = self.thread()
        old.delete()                    # 有人把 thread 刪了
        # 先有別的垃圾觸發重建：之後「現在的 thread」已經是新的，舊紀錄只能靠歷來的清單認
        self.repo.add_row(9, 200, grouped_id=None, text="今日首水", has_media=False)
        self.filter.quarantine(9)
        await self.worker._process_one(9)
        new = self.thread()
        self.assertNotEqual(new.id, old.id)

        self.repo.add_ready(3, 103)
        await self.worker._process_one(3)
        plans = self.publisher.to(new.id)
        self.assertEqual([p["media"] for p in plans[1:]], [media_of(3)], "只補晚到的那張，不是整本重貼")
        self.assertEqual(plans[1]["title_suffix"], "（補圖）")
        self.assertEqual(len(self.filter.calls), 2, "補圖不再判")
        self.assertEqual(self.publisher.to(CHANNEL), [], "舊 thread 的紀錄要認得出來是隔離")

    async def test_lost_runtime_file_still_recognises_quarantine(self):
        self.repo.add_ready(1, 101)
        self.repo.add_ready(2, 102)
        self.filter.quarantine(1)
        await self.worker._process_one(1)
        thread = self.thread()
        Path(self.runtime).unlink()     # runtime 檔被刪或寫入失敗
        self.restart()
        self.repo.add_ready(3, 103)
        await self.worker._process_one(3)
        self.assertEqual(len(self.filter.calls), 1, "不能當成新相簿重判")
        self.assertEqual(self.publisher.to(CHANNEL), [], "不能整本貼進主頻道")
        self.assertEqual([p["media"] for p in self.publisher.to(thread.id)], [media_of(3)], "補圖跟進原本的 thread")

    async def test_late_image_follows_quarantine_even_when_filter_is_off(self):
        self.repo.add_ready(1, 101)
        self.repo.add_ready(2, 102)
        self.filter.quarantine(1)
        await self.worker._process_one(1)
        thread = self.thread()
        self.filter.mode = "off"        # 之後把過濾關掉
        self.repo.add_ready(3, 103)
        await self.worker._process_one(3)
        self.assertEqual(self.publisher.to(CHANNEL), [])
        self.assertEqual(len(self.publisher.to(thread.id)), 2)


class RouteTests(FilterTestBase):
    async def test_duplicate_route_is_sent_once(self):
        self.routes.routes = [CHANNEL, CHANNEL]
        self.repo.add_row(9, 200, grouped_id=None, text="已开服", has_media=False)
        await self.worker._process_one(9)
        self.assertEqual(len(self.publisher.to(CHANNEL)), 1)


class ThreadTests(FilterTestBase):
    async def test_thread_is_reused_across_restart_and_unarchived(self):
        self.repo.add_row(9, 200, grouped_id=None, text="今日首水", has_media=False)
        self.repo.add_row(10, 201, grouped_id=None, text="今天还水吗", has_media=False)
        self.filter.quarantine(9)
        self.filter.quarantine(10)
        await self.worker._process_one(9)
        thread = self.thread()
        self.assertEqual(self.bot.main.created[0]["auto_archive_duration"], 10080, "一週才封存")
        saved = json.loads(Path(self.runtime).read_text(encoding="utf-8"))
        self.assertEqual(saved["threads"][str(CHANNEL)], thread.id)

        thread.archived = True          # 一天沒人講話就封存
        self.restart()
        await self.worker._process_one(10)
        self.assertEqual(len(self.bot.main.created), 1, "重啟後用同一個，不重開")
        self.assertIn({"archived": False}, thread.edits, "封存的先解封")
        self.assertEqual(len(self.publisher.to(thread.id)), 1)

    async def test_lost_runtime_file_finds_thread_by_name(self):
        self.repo.add_row(9, 200, grouped_id=None, text="今日首水", has_media=False)
        self.repo.add_row(10, 201, grouped_id=None, text="今天还水吗", has_media=False)
        self.filter.quarantine(9)
        self.filter.quarantine(10)
        await self.worker._process_one(9)
        thread = self.thread()
        thread.archived = True
        Path(self.runtime).unlink()
        self.restart()
        await self.worker._process_one(10)
        self.assertEqual(len(self.bot.main.created), 1, "依名稱找回封存的 thread，不重開")
        self.assertEqual(len(self.publisher.to(thread.id)), 1)

    async def test_without_thread_cache_finds_the_active_thread(self):
        # 一次性腳本只走 HTTP：頻道的 thread 快取永遠是空的，開著的 thread 要另外問 Discord
        self.repo.add_row(9, 200, grouped_id=None, text="今日首水", has_media=False)
        self.repo.add_row(10, 201, grouped_id=None, text="今天还水吗", has_media=False)
        self.filter.quarantine(9)
        self.filter.quarantine(10)
        await self.worker._process_one(9)
        thread = self.thread()
        Path(self.runtime).unlink()
        self.restart()
        self.bot.main.guild.active_threads = mock.AsyncMock(return_value=[thread])
        with mock.patch.object(type(self.bot.main), "threads", new_callable=mock.PropertyMock, return_value=[]):
            await self.worker._process_one(10)
        self.assertEqual(len(self.bot.main.created), 1, "開著的那個找得到，不重開")
        self.assertEqual(len(self.publisher.to(thread.id)), 1)

    async def test_two_processes_keep_each_others_thread(self):
        # bot 先讀過 runtime 檔（那時還沒有 thread），之後腳本開了 thread 並記下；bot 認出它時不能拿舊記憶體整份蓋回去
        bot_side = self.worker._quarantine
        await bot_side.parent_of(123)
        script_side = QuarantineThreads(self.bot, self.runtime)
        thread = await script_side.thread_for(self.bot.main)
        self.assertEqual(await bot_side.parent_of(thread.id), CHANNEL)
        saved = json.loads(Path(self.runtime).read_text(encoding="utf-8"))
        self.assertEqual(saved["threads"], {str(CHANNEL): thread.id})
        self.assertEqual(saved["thread_parents"], {str(thread.id): CHANNEL})


class ProcessLoopTests(FilterTestBase):
    async def wait_idle(self, timeout=10.0):
        """等到佇列空了、也沒有處理中的（連續幾次都是）；不用固定睡幾秒——啟動檢查時機器忙，固定等待會偶發失敗。"""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        quiet = 0
        while quiet < 5:
            idle = self.worker._queue.empty() and not self.worker._queued_set and not self.worker._processing
            quiet = quiet + 1 if idle else 0
            if loop.time() > deadline:
                self.fail("轉發一直沒處理完")
            await asyncio.sleep(0.01)

    async def run_loop(self, pks):
        self.worker._running = True
        loop_task = asyncio.create_task(self.worker._process_loop())
        try:
            for pk in pks:
                await self.worker._enqueue_message_pk(pk)
            await self.wait_idle()
        finally:
            self.worker._running = False
            loop_task.cancel()
            await asyncio.gather(loop_task, return_exceptions=True)

    async def test_one_at_a_time_when_filtering(self):
        for pk in (9, 10, 11):
            self.repo.add_row(pk, 200 + pk, grouped_id=None, text=f"情報 {pk}", has_media=False)
        self.filter.delay = 0.05
        await self.run_loop([9, 10, 11])
        self.assertEqual(len(self.filter.calls), 3)
        self.assertEqual(self.filter.max_active, 1)
        self.assertEqual([p["pks"] for p in self.publisher.to(CHANNEL)], [9, 10, 11], "照順序送")

    async def test_failed_album_is_judged_and_sent_once(self):
        """相簿送不出去時，同一本其他組員的通知不能各自重判、重送（半則會貼 N 份）。"""
        for pk in (1, 2, 3, 4):
            self.repo.add_ready(pk, 100 + pk)
        self.publisher.fail_channels.add(CHANNEL)
        self.worker._GROUP_QUIET_SEC = 0.05
        await self.run_loop([1, 2, 3, 4])
        self.assertEqual(len(self.filter.calls), 1)
        self.assertEqual(self.repo.reads.count(1), 2, "嘗試送一次（讀觸發的那則＋合併時讀）")

    async def test_album_without_any_image_does_not_block_others(self):
        """整本都還沒圖的相簿不等 60 秒（爬蟲補到圖會再通知），後面的情報照常送。"""
        self.worker._GROUP_MAX_WAIT_SEC = 5.0
        for pk in (1, 2):
            self.repo.add_row(pk, 100 + pk)           # 有圖標示、圖還沒到
        self.repo.add_row(9, 200, grouped_id=None, text="已开服", has_media=False)
        started = asyncio.get_running_loop().time()
        await self.run_loop([1, 2, 9])
        self.assertEqual([p["pks"] for p in self.publisher.to(CHANNEL)], [9])
        self.assertLess(asyncio.get_running_loop().time() - started, 2.0)

    async def test_album_waiting_for_images_is_sent_once_they_land(self):
        """整本還沒圖時先不送，但不能記成處理過：爬蟲補到圖的通知進來時要整本送出。"""
        for pk in (1, 2):
            self.repo.add_row(pk, 100 + pk)           # 有圖標示、圖還沒到（每小時輪詢或重啟補償撿到）
        await self.run_loop([1, 2])
        self.assertEqual(self.publisher.sent, [])
        self.repo.add_media(1)
        self.repo.add_media(2)                        # 爬蟲補到圖、通知
        await self.run_loop([1])
        self.assertEqual([p["media"] for p in self.publisher.to(CHANNEL)], [media_of(1, 2)])

    async def test_late_video_of_sent_album_is_sent_when_it_lands(self):
        """圖先送出、大影片還沒下載完；之後輪詢撿到影片那則（還沒到）不能把它記成處理過。"""
        self.worker._GROUP_MAX_WAIT_SEC = 0.2
        self.repo.add_ready(1, 101)
        self.repo.add_row(2, 102)                     # 影片還在下載
        await self.run_loop([1])
        await self.run_loop([2])          # 輪詢撿到影片那則，還沒到
        self.repo.add_media(2)
        await self.run_loop([2])          # 影片下載完、爬蟲通知
        self.assertEqual([p["media"] for p in self.publisher.to(CHANNEL)], [media_of(1), media_of(2)])

    async def test_queued_twice_is_processed_once(self):
        # 圖還沒到、先不處理的訊息不會被記成處理過：重複排入的話會多處理一次
        self.repo.add_row(9, 200, grouped_id=None, text="水", date=ago(minutes=5))
        await self.worker._enqueue_message_pk(9)
        await self.worker._enqueue_message_pk(9)    # 啟動時補償與游標掃描重疊排入
        await self.run_loop([])
        self.assertEqual(self.repo.reads.count(9), 1, "還在佇列裡的不用重排，輪到時本來就會讀到最新的資料")

    async def test_notification_during_processing_is_handled_afterwards(self):
        self.repo.add_row(9, 200, grouped_id=None, text="水", date=ago(minutes=5))   # 圖還沒到
        self.repo.read_delay = 0.1
        self.worker._running = True
        loop_task = asyncio.create_task(self.worker._process_loop())
        await self.worker._enqueue_message_pk(9)
        while 9 not in self.worker._processing:   # 等它開始處理（讀資料庫中）
            await asyncio.sleep(0.005)
        self.repo.add_media(9)                    # 這時爬蟲補到圖並通知
        await self.worker._enqueue_message_pk(9)
        try:
            await self.wait_idle()
        finally:
            self.worker._running = False
            loop_task.cancel()
            await asyncio.gather(loop_task, return_exceptions=True)
        self.assertEqual(self.publisher.to(CHANNEL)[0]["media"], media_of(9), "處理中收到的通知不能丟掉")



class RecheckTests(FilterTestBase):
    async def post_unanswered(self, pk, text="水"):
        self.repo.add_row(pk, 200 + pk, grouped_id=None, text=text, has_media=False)
        self.filter.unanswered(pk)
        await self.worker._process_one(pk)

    async def test_unanswered_goes_to_main_and_is_marked(self):
        await self.post_unanswered(9)
        self.assertEqual(len(self.publisher.to(CHANNEL)), 1, "判不到照常送主頻道，不擋情報")
        self.assertEqual(self.repo.needs_recheck, {(9, CHANNEL)})

    async def test_recheck_moves_spam(self):
        await self.post_unanswered(9)
        self.filter.quarantine(9, "灌水", "每日打卡")
        self.assertEqual(await self.worker.run_recheck(), 1)
        thread = self.thread()
        self.assertEqual(self.repo.channels_of(9), {thread.id})
        self.assertEqual(self.repo.needs_recheck, set())
        self.assertEqual(self.bot.main.messages, [], "主頻道原貼文刪掉")
        self.assertIn("判定：灌水｜每日打卡", thread.messages[0].content)

    async def test_recheck_pass_clears_the_mark(self):
        await self.post_unanswered(9)
        self.filter.verdicts[9] = Verdict(False, reason="有情報")
        await self.worker.run_recheck()
        self.assertEqual(self.repo.needs_recheck, set())
        self.assertEqual(self.repo.channels_of(9), {CHANNEL})
        self.assertEqual(len(self.bot.main.messages), 1)

    async def test_still_unanswered_stays_marked_and_stops_asking(self):
        await self.post_unanswered(9)
        await self.post_unanswered(10)
        self.filter.calls.clear()
        self.assertEqual(await self.worker.run_recheck(), 0)
        self.assertEqual(self.repo.needs_recheck, {(9, CHANNEL), (10, CHANNEL)})
        self.assertEqual(len(self.filter.calls), 1, "模型還沒好，後面的不一則一則再問")

    async def test_not_marked_when_rechecking_would_not_help_or_not_on(self):
        self.repo.add_row(9, 209, grouped_id=None, text="聽這個", has_media=False)
        self.filter.verdicts[9] = Verdict(False, reason="附有看不了的檔案（語音、壓縮檔）", by_model=False)
        await self.worker._process_one(9)
        self.assertEqual([c["pk"] for c in self.filter.calls], [9], "有送去判")
        self.filter.mode = "dry_run"
        await self.post_unanswered(10)
        self.assertEqual(self.repo.needs_recheck, set())
        self.assertEqual(await self.worker.run_recheck(), 0, "只記錄模式不補判")

    async def test_new_album_waits_for_the_followup_window(self):
        for pk in (1, 2):
            self.repo.add_ready(pk, 500 + pk, grouped_id=77, text="說明" if pk == 1 else "")
        self.filter.unanswered(1)
        await self.worker._process_one(1)
        self.assertEqual(self.repo.needs_recheck, {(1, CHANNEL), (2, CHANNEL)})
        self.filter.quarantine(1, "無關圖片", "奶龍")
        self.filter.calls.clear()
        await self.worker.run_recheck()
        self.assertEqual(self.filter.calls, [], "補圖時效內搬不動，先不判")
        self.assertEqual(len(self.repo.needs_recheck), 2)
        for pk in (1, 2):
            self.repo.delivered[(pk, CHANNEL)] = ago(hours=13)
        await self.worker.run_recheck()
        thread = self.thread()
        self.assertEqual((self.repo.channels_of(1), self.repo.channels_of(2)), ({thread.id}, {thread.id}), "整本一起搬")
        self.assertEqual(self.repo.needs_recheck, set())

    async def test_model_answer_wakes_the_recheck(self):
        await self.post_unanswered(9)
        self.assertFalse(self.worker._recheck_wake.is_set(), "判不到的那則不算模型恢復")
        self.repo.add_row(10, 210, grouped_id=None, text="已开服", has_media=False)
        await self.worker._process_one(10)
        self.assertTrue(self.worker._recheck_wake.is_set())

    async def test_spam_that_cannot_be_moved_is_cleared_and_logged(self):
        await self.post_unanswered(9)
        self.bot.main.messages.clear()   # 原貼文先被人刪了
        self.filter.quarantine(9)
        with self.assertLogs("services.relay.telegram_relay_service", "ERROR") as logs:
            await self.worker.run_recheck()
        self.assertTrue(any("手動處理" in line for line in logs.output))
        self.assertEqual(self.repo.needs_recheck, set(), "不再一直補判")


if __name__ == "__main__":
    unittest.main()
