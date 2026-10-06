"""Telegram 爬蟲：圖片下載的收尾（telegram_scraper/handlers.py、media_download.py、runner.py 補掃）。

守的底線：
- 下載出錯要攔下來、不往外拋：訊息照樣入庫；啟動的歷史掃描不能因為一張圖下載失敗就讓整個爬蟲當掉
  （容器 restart: always 會陷入重啟迴圈）
- 新訊息的圖第一次沒下載到：**先不通知轉發端**，補掃補到圖才通知（文字和圖一起送成一則，使用者要完整）；
  **有文字的單則**發文滿 30 分鐘還沒補到才通知一次讓文字先送，只放行一次；沒文字的單則和相簿組員不放行
  （轉發端會把沒文字的當空訊息略過、相簿只送有圖的組員，放行只有害處）。轉發端的單則不等圖，下載失敗就
  通知的話文字會先送、之後補到的圖再也送不出去。補掃關掉、下載功能關掉、/resend_article 的重抓、或發文
  早就超過 30 分鐘（漏收後才補進來）的不壓；這些在沒圖時就已通知過的，之後重試失敗不再重複通知
- 下載卡住要偵測：一段時間沒有進度就取消（照片曾經卡 1～1.6 小時、整輪補掃跟著卡住）；
  大檔只要持續有進度就不能被誤殺；關機（外層被取消）照常往外拋、下載也一併取消；
  Telethon 斷線時取消下載要當成下載失敗，不能當成關機（補掃迴圈會跟著結束）
- 下載失敗的，補掃要在「發文後 12 小時內」每輪重試；超過 12 小時、或圖已經有了就不再下載。
  重試只涵蓋補掃回看的最近 300 則（`CATCHUP_GAP_WINDOW`），12 小時和 300 則先到者為準；
  歷史上 12 小時內最多約 265 則，夠用，範圍外的留給爬蟲重啟時的歷史掃描
- 圖後來才補下載成功，要再通知轉發端一次（以前只在訊息第一次寫入時通知，轉發端不知道圖到了）；
  但重掃一則本來就完整的訊息不通知、超過 12 小時的不通知、/resend_article 的重抓不通知（它自己會送，
  爬蟲再通知會重複貼文）、重試又失敗的不通知
- 「有圖」只算真的下載得到的，照 Telethon 依外層型別分派：沒附圖的網頁預覽、過期照片、只有空尺寸的照片、
  網頁預覽附空殼文件、帳單、投票等不算（以前標成有圖卻永遠下載不到，轉發端的相簿因此空等）；
  看不懂的媒體型別記 WARNING 並帶上型別名
- 爬蟲下載媒體一律經過 `media_download.download_with_stall_guard`（守衛擋直接呼叫 download_media）

bot 容器沒有 Telethon（用假模組）；`RealTelethonTypesTests` 只在爬蟲容器跑，見 telegram_scraper_fakes。

執行：
    cd src && python -m unittest test.test_telegram_scraper_media -v
"""
import asyncio
import os
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from telegram_scraper_fakes import (  # noqa: E402
    CHANNEL, CHAT, REAL_TELETHON, FakeClient, FakeDB, FakeTelegramDatabase, FakeWatcher, fake_config, hours_ago,
    load_scraper, media, msg, photo_media, video_media, webpage_media,
)

S = load_scraper()
handlers, runner, media_download = S.handlers, S.runner, S.media_download


class MediaTestBase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.config = fake_config(tmp.name)
        os.makedirs(self.config.media_dir, exist_ok=True)
        self.watcher = FakeWatcher(self.config.media_dir)
        self.db = FakeDB()
        self.client = FakeClient()
        handlers._chat_title_cache.clear()
        handlers._hold_released.clear()
        runner._catchup_chat_id_cache.clear()
        runner._catchup_chat_id_cache[CHANNEL] = CHAT
        self.addCleanup(runner._catchup_chat_id_cache.clear)
        # 卡住偵測的門檻縮短，測試才不用等 3 分鐘
        patcher = mock.patch.object(media_download, "MEDIA_STALL_TIMEOUT_SEC", 0.05)
        patcher.start()
        self.addCleanup(patcher.stop)

    async def process(self, message, *, prefix="Telegram"):
        return await handlers._process_message(
            message=message, chat_id=message.chat_id, raw_text=message.message, client=self.client,
            config=self.config, runtime_watcher=self.watcher, db=self.db, log_prefix=prefix,
        )


# ── S2：下載出錯、卡住 ──────────────────────────────────────────────────────

async def boom(*args):
    raise RuntimeError("連線被重設")


class DownloadFailureTests(MediaTestBase):
    async def test_download_error_is_contained_and_held(self):
        self.client.download_impl = boom
        with self.assertLogs("handlers", "WARNING") as logs:
            ok = await self.process(msg(10, text="爆料", media_obj=photo_media()))
        self.assertTrue(ok)
        pk = self.db.pk_of(10)
        self.assertEqual(self.db.media.get(pk), None, "下載失敗不寫媒體列")
        self.assertEqual(self.db.notified, [], "圖還沒到先不通知：等補掃補到圖，文字和圖一起送")
        self.assertTrue(any("message_id=10" in line and "MessageMediaPhoto" in line for line in logs.output), logs.output)

    async def test_missed_message_already_past_30_minutes_is_not_held(self):
        """漏收後才補進來、發文早就超過 30 分鐘的：等待時間已經過了，照樣先通知讓文字送出。"""
        self.client.download_impl = boom
        await self.process(msg(10, text="爆料", media_obj=photo_media(), date=hours_ago(1)), prefix="CatchUp")
        self.assertEqual(self.db.notified, [self.db.pk_of(10)])

    async def test_refetch_new_message_is_not_held(self):
        self.client.download_impl = boom
        await self.process(msg(10, text="爆料", media_obj=photo_media()), prefix="Refetch")
        self.assertEqual(self.db.notified, [self.db.pk_of(10)], "重抓的新訊息照舊立刻通知")

    async def test_download_disabled_notifies_immediately_and_never_downloads(self):
        self.watcher.snapshot.download_media = False
        await self.process(msg(10, text="爆料", media_obj=photo_media()))
        self.assertEqual(self.db.notified, [self.db.pk_of(10)])
        self.assertEqual(self.client.downloads, [])

    async def test_notified_without_media_is_not_notified_again_on_failed_retry(self):
        """沒壓（插入時就已通知）的訊息，之後重試又失敗時不能再「放行」通知一次。"""
        self.client.download_impl = boom
        await self.process(msg(10, text="爆料", media_obj=photo_media(), date=hours_ago(1)), prefix="CatchUp")
        pk = self.db.pk_of(10)
        self.assertEqual(self.db.notified, [pk])
        await self.process(msg(10, text="爆料", media_obj=photo_media(), date=hours_ago(1.25)), prefix="CatchUp")
        self.assertEqual(self.db.notified, [pk])

    async def test_not_held_when_catch_up_is_off(self):
        """補掃關掉時沒有人會再試下載，壓著就永遠不通知了。"""
        self.watcher.snapshot.catchup_interval_min = 0
        self.client.download_impl = boom
        await self.process(msg(10, text="爆料", media_obj=photo_media()))
        self.assertEqual(self.db.notified, [self.db.pk_of(10)])

    async def test_shutdown_still_propagates(self):
        """關機（外層被取消）時，訊息處理照常往外拋 CancelledError，不能被當成下載失敗吞掉。"""
        async def hang(target, file, progress_callback):
            await asyncio.Event().wait()
        self.client.download_impl = hang
        with mock.patch.object(media_download, "MEDIA_STALL_TIMEOUT_SEC", 30):
            task = asyncio.ensure_future(self.process(msg(10, media_obj=photo_media())))
            await asyncio.sleep(0.05)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task


class StallGuardTests(MediaTestBase):
    async def test_stalled_download_is_cancelled(self):
        cancelled = []

        async def hang(target, file, progress_callback):
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.append(True)
        self.client.download_impl = hang
        with self.assertRaises(media_download.MediaDownloadStalled):
            await asyncio.wait_for(
                media_download.download_with_stall_guard(self.client, msg(1), file="/tmp/x.jpg"), 2)
        self.assertEqual(cancelled, [True], "卡住的下載要被取消，不能留在背景")

    async def test_slow_but_progressing_download_completes(self):
        # 門檻 0.5 秒、每 0.02 秒有進度、總共約 0.6 秒：門檻留大一點，啟動 gate 裡偶爾慢一點也不會誤判
        async def trickle(target, file, progress_callback):
            for i in range(30):
                await asyncio.sleep(0.02)
                progress_callback(i + 1, 30)
            return file
        self.client.download_impl = trickle
        path = await asyncio.wait_for(
            media_download.download_with_stall_guard(self.client, msg(1), file="/tmp/x.jpg", stall_sec=0.5), 5)
        self.assertEqual(path, "/tmp/x.jpg", "總共花的時間比門檻長，但一直有進度，不能被誤殺")

    async def test_shutdown_cancels_the_download_too(self):
        """關機時外層被取消：CancelledError 照常往外拋，下載也一併取消。"""
        cancelled = []

        async def hang(target, file, progress_callback):
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.append(True)
        self.client.download_impl = hang
        with mock.patch.object(media_download, "MEDIA_STALL_TIMEOUT_SEC", 30):
            task = asyncio.ensure_future(
                media_download.download_with_stall_guard(self.client, msg(1), file="/tmp/x.jpg"))
            await asyncio.sleep(0.05)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertEqual(cancelled, [True])

    async def test_shutdown_during_stall_cleanup_still_propagates(self):
        """判定卡住、正在等下載收尾時剛好關機：要拋 CancelledError，不能變成「卡住」被當下載失敗吞掉。"""
        async def slow_to_stop(target, file, progress_callback):
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                await asyncio.sleep(0.3)   # 被取消後還要一點時間才結束
                raise
        self.client.download_impl = slow_to_stop
        task = asyncio.ensure_future(
            media_download.download_with_stall_guard(self.client, msg(1), file="/tmp/x.jpg", stall_sec=0.05))
        await asyncio.sleep(0.15)   # 已判定卡住、正在等下載收尾
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task

    async def test_library_cancel_is_a_download_failure_not_shutdown(self):
        """Telethon 斷線時會取消進行中的下載：當成下載失敗（補掃迴圈才不會跟著結束）。"""
        async def dropped(target, file, progress_callback):
            raise asyncio.CancelledError()
        self.client.download_impl = dropped
        with self.assertRaises(ConnectionError):
            await media_download.download_with_stall_guard(self.client, msg(1), file="/tmp/x.jpg")

    async def test_stall_in_message_download_is_contained(self):
        async def hang(target, file, progress_callback):
            await asyncio.Event().wait()
        self.client.download_impl = hang
        ok = await asyncio.wait_for(self.process(msg(10, text="t", media_obj=photo_media())), 2)
        self.assertTrue(ok)
        self.assertEqual(self.db.media.get(self.db.pk_of(10)), None)

    async def test_custom_emoji_download_is_guarded(self):
        async def hang(target, file, progress_callback):
            await asyncio.Event().wait()

        class EmojiClient(FakeClient):
            async def __call__(self, request):   # GetCustomEmojiDocumentsRequest
                return [SimpleNamespace(id=9001, mime_type="image/webp")]
        client = EmojiClient()
        client.download_impl = hang
        entities = [{"type": "MessageEntityCustomEmoji", "offset": 0, "length": 2, "document_id": 9001}]
        # 卡住的自訂表情下載也要被取消，不能讓整則訊息的處理卡死
        await asyncio.wait_for(handlers._download_custom_emojis(
            message_pk=1, entities=entities, client=client, media_dir=self.config.media_dir,
            db=self.db, log_prefix="Telegram"), 2)
        self.assertEqual(len(client.downloads), 1, "要真的試過下載（不是提早結束才沒卡住）")


class CatchUpRetryTests(MediaTestBase):
    async def test_retries_recent_row_missing_media(self):
        self.db.add_row(100, has_media=True, date=hours_ago(1))
        self.client.history = {CHANNEL: [msg(100, text="t", media_obj=photo_media(), date=hours_ago(1))]}
        await runner._catch_up_channel(CHANNEL, self.client, self.config, self.watcher, self.db, runner.KeyedLock())
        pk = self.db.pk_of(100)
        self.assertEqual(len(self.client.downloads), 1, "發文 12 小時內、還沒有圖的要重試下載")
        self.assertTrue(self.db.media.get(pk))
        self.assertEqual(self.db.notified, [pk], "補到圖要通知轉發端")

    async def test_no_retry_when_download_is_disabled(self):
        self.watcher.snapshot.download_media = False
        self.db.add_row(100, has_media=True, date=hours_ago(1))
        self.client.history = {CHANNEL: [msg(100, text="t", media_obj=photo_media(), date=hours_ago(1))]}
        await runner._catch_up_channel(CHANNEL, self.client, self.config, self.watcher, self.db, runner.KeyedLock())
        self.assertEqual(self.db.upserts, [], "下載功能關掉時不重跑缺圖的訊息（重跑也不會下載，只是每輪白做）")

    async def test_retry_covers_only_the_catch_up_window(self):
        """最新是 400 號時只回看 100 號以後：150 號重試，10 號雖然還在 12 小時內也不重試（接受的上限）。"""
        self.db.add_row(10, has_media=True, date=hours_ago(2))
        self.db.add_row(150, has_media=True, date=hours_ago(1))
        self.db.add_row(400, has_media=False, date=hours_ago(0.5))
        self.client.history = {CHANNEL: [msg(10, text="t", media_obj=photo_media(1), date=hours_ago(2)),
                                         msg(150, text="t", media_obj=photo_media(2), date=hours_ago(1)),
                                         msg(400, text="t", date=hours_ago(0.5))]}
        await runner._catch_up_channel(CHANNEL, self.client, self.config, self.watcher, self.db, runner.KeyedLock())
        self.assertEqual([target.id for target in self.client.downloads], [150])
        self.assertEqual(self.db.notified, [self.db.pk_of(150)])

    async def test_skips_old_or_complete_rows(self):
        self.db.add_row(100, has_media=True, date=hours_ago(13))
        self.db.add_row(101, has_media=True, date=hours_ago(1), with_media=True)
        self.client.history = {CHANNEL: [msg(100, media_obj=photo_media(), date=hours_ago(13)),
                                         msg(101, media_obj=photo_media(), date=hours_ago(1))]}
        await runner._catch_up_channel(CHANNEL, self.client, self.config, self.watcher, self.db, runner.KeyedLock())
        self.assertEqual(self.client.downloads, [], "超過 12 小時、或已經有圖的都不再下載")


class HistoryScanResilienceTests(MediaTestBase):
    async def test_history_scan_survives_download_error(self):
        calls = []

        async def first_fails(target, file, progress_callback):
            calls.append(target.id)
            if target.id == 10:
                raise RuntimeError("下載失敗")
            return file
        client = FakeClient(history={CHANNEL: [msg(10, media_obj=photo_media(1)), msg(11, media_obj=photo_media(2))]})
        client.download_impl = first_fails
        db = FakeTelegramDatabase()
        db_class = mock.Mock(return_value=db)
        db_class.ensure_database_exists = FakeTelegramDatabase.ensure_database_exists
        with mock.patch.object(runner, "TelegramClient", lambda *a, **k: client), \
             mock.patch.object(runner, "TelegramDatabase", db_class), \
             mock.patch.object(runner, "TelegramRuntimeConfigWatcher", lambda **k: self.watcher):
            await runner.run_telegram_scraper(self.config)   # 不能拋
        self.assertIn((CHAT, 10), db.rows, "下載失敗的那則照樣入庫")
        self.assertIn((CHAT, 11), db.rows, "第一則下載失敗，第二則照樣入庫")
        self.assertNotIn(db.pk_of(10), db.notified, "剛發的、圖沒到：先壓著")
        self.assertIn(db.pk_of(11), db.notified)


# ── S3：圖後來才到，要再通知轉發端 ──────────────────────────────────────────

class LateMediaNotifyTests(MediaTestBase):
    async def test_late_media_on_existing_row_notifies_once(self):
        pk = self.db.add_row(10, has_media=True, date=hours_ago(1))
        await self.process(msg(10, media_obj=photo_media(), date=hours_ago(1)), prefix="CatchUp")
        self.assertEqual(self.db.notified, [pk])

    async def test_complete_row_rescan_does_not_notify(self):
        self.db.add_row(10, has_media=True, date=hours_ago(1), with_media=True)
        await self.process(msg(10, media_obj=photo_media(), date=hours_ago(1)), prefix="History")
        self.assertEqual(self.db.notified, [], "重啟時重掃幾百則完整的訊息，不能每則都通知")

    async def test_late_media_for_old_post_does_not_notify(self):
        self.db.add_row(10, has_media=True, date=hours_ago(13))
        await self.process(msg(10, media_obj=photo_media(), date=hours_ago(13)), prefix="History")
        self.assertEqual(self.db.notified, [], "超過 12 小時轉發端本來就不補送")

    async def test_refetch_landing_does_not_notify(self):
        self.db.add_row(10, has_media=True, date=hours_ago(1))
        await self.process(msg(10, media_obj=photo_media(), date=hours_ago(1)), prefix="Refetch")
        self.assertEqual(self.db.notified, [], "/resend_article 自己會送；再通知會重複貼文")

    async def test_failed_retry_within_30_minutes_does_not_notify(self):
        self.db.add_row(10, has_media=True, date=hours_ago(10 / 60))
        self.client.download_impl = boom
        await self.process(msg(10, text="爆料", media_obj=photo_media(), date=hours_ago(10 / 60)), prefix="CatchUp")
        self.assertEqual(self.db.notified, [], "還在 30 分鐘內，繼續壓著")

    async def test_history_landing_within_window_notifies(self):
        """爬蟲重啟時的歷史掃描補到圖，也要通知（12 小時內）。"""
        pk = self.db.add_row(10, has_media=True, date=hours_ago(1))
        await self.process(msg(10, media_obj=photo_media(), date=hours_ago(1)), prefix="History")
        self.assertEqual(self.db.notified, [pk])


class HoldReleaseTests(MediaTestBase):
    async def test_held_message_notifies_once_media_lands(self):
        self.client.download_impl = boom
        await self.process(msg(10, text="爆料", media_obj=photo_media()))
        self.assertEqual(self.db.notified, [])
        self.client.download_impl = None   # 下一輪補掃下載成功
        await self.process(msg(10, text="爆料", media_obj=photo_media()), prefix="CatchUp")
        self.assertEqual(self.db.notified, [self.db.pk_of(10)], "補到圖才通知：轉發端一次收到文字和圖")

    async def test_held_album_member_notifies_once_media_lands(self):
        """相簿組員不放行，但補到圖要通知：轉發端以「（補圖）」補上，或趕得上就跟同組一起送。"""
        self.client.download_impl = boom
        await self.process(msg(10, text="說明", media_obj=photo_media(), grouped_id=77))
        self.assertEqual(self.db.notified, [])
        self.client.download_impl = None
        await self.process(msg(10, text="說明", media_obj=photo_media(), date=hours_ago(40 / 60), grouped_id=77),
                           prefix="CatchUp")
        self.assertEqual(self.db.notified, [self.db.pk_of(10)])

    async def test_released_once_after_30_minutes(self):
        pk = self.db.add_row(10, has_media=True, date=hours_ago(31 / 60))
        self.client.download_impl = boom
        await self.process(msg(10, text="爆料", media_obj=photo_media(), date=hours_ago(31 / 60)), prefix="CatchUp")
        self.assertEqual(self.db.notified, [pk], "等滿 30 分鐘還沒補到：通知一次讓文字先送")
        await self.process(msg(10, text="爆料", media_obj=photo_media(), date=hours_ago(46 / 60)), prefix="CatchUp")
        self.assertEqual(self.db.notified, [pk], "之後每輪又失敗，不再重複通知")

    async def test_release_only_counts_once_30_minutes_have_passed(self):
        """0 分、15 分重試失敗都不能用掉放行名額，31 分那輪才放行。"""
        self.client.download_impl = boom
        await self.process(msg(10, text="爆料", media_obj=photo_media()))
        pk = self.db.pk_of(10)
        await self.process(msg(10, text="爆料", media_obj=photo_media(), date=hours_ago(15 / 60)), prefix="CatchUp")
        self.assertEqual(self.db.notified, [])
        await self.process(msg(10, text="爆料", media_obj=photo_media(), date=hours_ago(31 / 60)), prefix="CatchUp")
        self.assertEqual(self.db.notified, [pk])

    async def test_text_less_single_is_not_released(self):
        """沒文字的單則放行後，轉發端會當空訊息略過並記成處理過，之後補到的圖要等 bot 重啟才送——不放行。"""
        self.db.add_row(10, has_media=True, date=hours_ago(31 / 60))
        self.client.download_impl = boom
        await self.process(msg(10, media_obj=photo_media(), date=hours_ago(31 / 60)), prefix="CatchUp")
        self.assertEqual(self.db.notified, [])

    async def test_album_member_is_not_released(self):
        """相簿只送已經有圖的組員，放行只會讓轉發端白等。"""
        self.db.add_row(10, has_media=True, date=hours_ago(31 / 60))
        self.client.download_impl = boom
        await self.process(msg(10, text="說明", media_obj=photo_media(), date=hours_ago(31 / 60), grouped_id=77),
                           prefix="CatchUp")
        self.assertEqual(self.db.notified, [])

    async def test_refetch_retry_does_not_release(self):
        self.db.add_row(10, has_media=True, date=hours_ago(31 / 60))
        self.client.download_impl = boom
        await self.process(msg(10, text="爆料", media_obj=photo_media(), date=hours_ago(31 / 60)), prefix="Refetch")
        self.assertEqual(self.db.notified, [])

    async def test_not_released_after_12_hours(self):
        self.db.add_row(10, has_media=True, date=hours_ago(13))
        self.client.download_impl = boom
        await self.process(msg(10, text="爆料", media_obj=photo_media(), date=hours_ago(13)), prefix="History")
        self.assertEqual(self.db.notified, [])


# ── S4：怎樣才算「有圖」 ────────────────────────────────────────────────────

class DownloadableMediaTests(MediaTestBase):
    async def test_link_preview_without_photo_is_text_only(self):
        with self.assertNoLogs("handlers", "WARNING"):   # 很常見，記 INFO 就好，不要洗版
            await self.process(msg(10, text="https://x.com/a", media_obj=webpage_media(with_photo=False)))
        self.assertFalse(self.db.upserts[-1]["has_media"])
        self.assertEqual(self.client.downloads, [])
        self.assertEqual(self.db.notified, [self.db.pk_of(10)])

    async def test_expired_photo_is_not_media(self):
        await self.process(msg(10, media_obj=media("MessageMediaPhoto", photo=None, spoiler=False)))
        self.assertFalse(self.db.upserts[-1]["has_media"])
        self.assertEqual(self.client.downloads, [])

    async def test_unsupported_media_logs_type_name(self):
        with self.assertLogs("handlers", "WARNING") as logs:
            await self.process(msg(10, media_obj=media("MessageMediaPoll", poll=object())))
        self.assertTrue(any("MessageMediaPoll" in line for line in logs.output), logs.output)
        self.assertFalse(self.db.upserts[-1]["has_media"])

    async def test_none_from_downloadable_logs_type(self):
        async def none(*args):
            return None
        self.client.download_impl = none
        with self.assertLogs("handlers", "WARNING") as logs:
            await self.process(msg(10, media_obj=photo_media()))
        self.assertTrue(any("MessageMediaPhoto" in line for line in logs.output), logs.output)

    async def test_link_preview_with_photo_still_downloads(self):
        await self.process(msg(10, text="https://x.com/a", media_obj=webpage_media(with_photo=True)))
        self.assertTrue(self.db.upserts[-1]["has_media"])
        self.assertEqual(len(self.client.downloads), 1)

    async def test_shell_types_are_not_media(self):
        shells = {
            "帳單": media("MessageMediaInvoice", photo=SimpleNamespace(size=100, url="https://x")),
            "只有空尺寸的照片": media("MessageMediaPhoto", photo=SimpleNamespace(id=1, sizes=[media("PhotoSizeEmpty")]),
                                     spoiler=False),
            "只有輪廓尺寸的照片": media("MessageMediaPhoto", photo=SimpleNamespace(id=3, sizes=[media("PhotoPathSize")]),
                                       spoiler=False),
            "網頁預覽附空殼文件": media("MessageMediaWebPage", webpage=SimpleNamespace(
                document=SimpleNamespace(id=9), photo=SimpleNamespace(id=2, sizes=[object()]))),
        }
        for label, media_obj in shells.items():
            self.assertIsNone(handlers._downloadable_media(msg(10, media_obj=media_obj)), label)

    async def test_video_document_is_media(self):
        await self.process(msg(10, media_obj=video_media()))
        self.assertTrue(self.db.upserts[-1]["has_media"])
        self.assertEqual(len(self.client.downloads), 1)


@unittest.skipUnless(REAL_TELETHON, "要真的 Telethon：在爬蟲容器用 docker exec 跑")
class RealTelethonTypesTests(unittest.TestCase):
    """假物件的「長相」要跟真的 Telethon 型別一致，不然上面的測試都在測錯的東西。"""

    def test_real_types(self):
        from datetime import datetime, timezone
        from telethon.tl import types
        photo = types.Photo(id=1, access_hash=1, file_reference=b"", date=datetime.now(timezone.utc),
                            sizes=[types.PhotoSize(type="x", w=1, h=1, size=1)], dc_id=1)
        doc = types.Document(id=2, access_hash=1, file_reference=b"", date=datetime.now(timezone.utc),
                             mime_type="video/mp4", size=10, dc_id=1, attributes=[])
        downloadable = handlers._downloadable_media
        self.assertIsNotNone(downloadable(msg(1, media_obj=types.MessageMediaPhoto(photo=photo))))
        self.assertIsNotNone(downloadable(msg(1, media_obj=types.MessageMediaDocument(document=doc))))
        self.assertIsNone(downloadable(msg(1, media_obj=types.MessageMediaPhoto(photo=None))))
        self.assertIsNone(downloadable(msg(1, media_obj=types.MessageMediaWebPage(webpage=types.WebPageEmpty(id=1)))))
        self.assertIsNone(downloadable(msg(1, media_obj=types.MessageMediaPhoto(photo=types.PhotoEmpty(id=3)))))
        self.assertIsNone(downloadable(msg(1, media_obj=types.MessageMediaDocument(document=types.DocumentEmpty(id=4)))))
        self.assertIsNone(downloadable(msg(1, media_obj=types.MessageMediaGeo(geo=types.GeoPointEmpty()))))
        invoice = types.MessageMediaInvoice(
            title="t", description="d", currency="USD", total_amount=1, start_param="s",
            photo=types.WebDocument(url="https://x", access_hash=1, size=10, mime_type="image/jpeg", attributes=[]))
        self.assertIsNone(downloadable(msg(1, media_obj=invoice)), "帳單的圖 Telethon 不會下載")
        empty_sizes = types.Photo(id=5, access_hash=1, file_reference=b"", date=datetime.now(timezone.utc),
                                  sizes=[types.PhotoSizeEmpty(type="x")], dc_id=1)
        self.assertIsNone(downloadable(msg(1, media_obj=types.MessageMediaPhoto(photo=empty_sizes))))
        path_only = types.Photo(id=7, access_hash=1, file_reference=b"", date=datetime.now(timezone.utc),
                                sizes=[types.PhotoPathSize(type="j", bytes=b"x")], dc_id=1)
        self.assertIsNone(downloadable(msg(1, media_obj=types.MessageMediaPhoto(photo=path_only))))
        page = types.WebPage(id=1, url="https://x", display_url="x", hash=0,
                             photo=photo, document=types.DocumentEmpty(id=6))
        self.assertIsNone(downloadable(msg(1, media_obj=types.MessageMediaWebPage(webpage=page))),
                          "Telethon 取 document or photo：文件是空殼就不會改抓照片")
        page_ok = types.WebPage(id=2, url="https://x", display_url="x", hash=0, photo=photo)
        self.assertIsNotNone(downloadable(msg(1, media_obj=types.MessageMediaWebPage(webpage=page_ok))))


if __name__ == "__main__":
    unittest.main()
