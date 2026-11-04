"""FB 貼文發到 Discord：影片、重發、已送紀錄（services.relay.fb_monitor、commands.article_commands）。

守的底線：
  1. 影片貼文傳影片；回覆主文，不 @ 人；檔名是 .mp4，才會被當影片播。沒有圖片的影片貼文，主文不帶附件也不帶
     embed 圖（封面由爬蟲端濾掉，這裡只看 bot 收到沒有圖時的行為）。
  2. 高畫質超過上限、被 Discord 退回或上傳時連線中斷，就改標準畫質，都不行才給文章連結；連結用 pfbid，不用 url 欄。
  3. 主文一送出就記已送；之後的圖片、影片不管怎麼壞，這篇都算送過，不能讓主文每小時多發一次。
     圖片壞掉不能擋影片，一支影片壞掉不能擋下一支，也不能少了連結。主文本身沒送出去才不算。
     這裡把 post_to_channel 換成替身，所以它退純文字後補送失敗那條路不在這裡守，缺口寫在 fb_monitor 開頭。
  4. 影片網址沒有存：影片貼文第一次發文請爬蟲重開一次，多頻道共用；照片貼文不重開。
  5. /resend_article 一定先重開拿新網址；重開失敗沿用舊的圖並告訴操作者；少了什麼要回給操作者，
     頁面表示的格數（影片也佔一格）比重開拿到的多也要講，全部拿到就不講。
  6. 影片下載超過上限就中止，不整支讀完；403 或連線錯誤回 None，不丟例外。

不連網、不碰資料庫：發文、下載、已送紀錄、活動都換掉（活動走真的 StateDB，不換會寫正式資料庫）。
"""
import io
import unittest
from types import SimpleNamespace
from unittest import mock

import aiohttp
import discord

from commands.article_commands import ArticleCommands
from services.relay import fb_monitor as module
from services.relay.fb_monitor import FBMonitor
from utils.discord_content import upload_limit

URL = "https://www.facebook.com/x/posts/pfbid0abc"
HD = "https://video.fbcdn.net/hd.mp4?oe=1"
SD = "https://video.fbcdn.net/sd.mp4?oe=1"
VIDEO = {"id": "111", "hd_url": HD, "sd_url": SD, "duration_ms": 70000, "permalink_url": "https://www.facebook.com/reel/111/"}
GUILD = SimpleNamespace(filesize_limit=100 * 1024 * 1024)


def http_error(status=413):
    return discord.HTTPException(SimpleNamespace(status=status, reason="too large"), "檔案太大")


class FakeChannel:
    def __init__(self, events, fail=()):
        self.events = events
        self.guild = GUILD
        self.sent = []
        self.fail = list(fail)
        self.id = 1

    async def send(self, content=None, **kw):
        if self.fail:
            error = self.fail.pop(0)
            if error:
                raise error
        self.sent.append({"content": content, **kw})
        file = kw.get("file")
        self.events.append(f"傳 {file.filename}" if file else ("傳圖" if kw.get("files") else f"文字 {content}"))
        return SimpleNamespace(id=len(self.sent))


def post(**over):
    data = {"id": 926, "post_id": "fb_1", "url": None, "pfbid_url": URL, "text": "內容", "text_md": "內容", "timestamp": None, "created_at": "2026-11-03T10:11:52", "images": [], "has_video": False}
    data.update(over)
    return data


class Base(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.events = []
        self.channel = FakeChannel(self.events)
        self.main = SimpleNamespace(channel=self.channel, jump_url="https://discord/1", id=99)
        self.monitor = FBMonitor.__new__(FBMonitor)
        self.monitor.bot = SimpleNamespace(get_channel=lambda cid: self.channel)
        self.monitor.scraper_api_url = "http://scraper:8000"

        async def mark(kind, content_id):
            self.events.append("記已送")

        self.monitor.mark_content_as_sent = mock.AsyncMock(side_effect=mark)
        self.monitor.refresh_media = mock.AsyncMock(return_value={"images": [], "videos": [VIDEO]})
        self.monitor._download_image_as_file = mock.AsyncMock(return_value=(io.BytesIO(b"img"), ".jpg"))
        self.monitor._download_video = mock.AsyncMock(side_effect=lambda url, session, limit: io.BytesIO(url.encode()))

        async def post_to_channel(channel, **kw):
            if getattr(self, "main_fails", False):
                raise http_error(500)
            self.events.append("主文")
            self.main_kwargs = kw
            return self.main

        for target, replacement in (
            ("services.relay.fb_monitor.post_to_channel", post_to_channel),
            ("services.events.event_scheduler.schedule_from_fb", mock.AsyncMock()),
            ("services.relay.fb_monitor.asyncio.sleep", mock.AsyncMock()),
        ):
            patcher = mock.patch(target, replacement)
            patcher.start()
            self.addCleanup(patcher.stop)

    async def send(self, fb_post, **kw):
        return await self.monitor.send_fb_post_to_channel(1, fb_post, **kw)


class VideoPostTest(Base):
    async def test_video_is_sent_as_reply_after_main_post(self):
        self.assertTrue(await self.send(post(has_video=True)))
        self.assertEqual(self.events, ["主文", "記已送", "傳 fb_111.mp4"])
        sent = self.channel.sent[0]
        self.assertIs(sent["reference"], self.main)
        self.assertIs(sent["mention_author"], False)

    async def test_main_post_has_no_attachment_without_images(self):
        await self.send(post(has_video=True))
        self.assertFalse(self.main_kwargs.get("files"))
        self.assertIsNone(self.main_kwargs["embed"].image.url)
        self.monitor._download_image_as_file.assert_not_called()

    async def test_hd_is_tried_first(self):
        await self.send(post(has_video=True))
        self.assertEqual(self.monitor._download_video.await_args_list[0].args[0], HD)
        self.assertEqual(self.monitor._download_video.await_count, 1, "高畫質成功就不用再下載")

    async def test_limit_comes_from_the_server(self):
        await self.send(post(has_video=True))
        self.assertEqual(self.monitor._download_video.await_args.args[2], upload_limit(self.channel))

    async def test_too_large_falls_back_to_sd(self):
        self.monitor._download_video = mock.AsyncMock(side_effect=[None, io.BytesIO(b"sd")])
        await self.send(post(has_video=True))
        self.assertEqual([c.args[0] for c in self.monitor._download_video.await_args_list], [HD, SD])
        self.assertEqual(self.events[-1], "傳 fb_111.mp4")

    async def test_rejected_upload_falls_back_to_sd(self):
        self.channel.fail = [http_error(413)]
        await self.send(post(has_video=True))
        self.assertEqual(self.monitor._download_video.await_count, 2)
        self.assertEqual(self.events[-1], "傳 fb_111.mp4")

    async def test_connection_errors_fall_back_to_sd(self):
        """連線中斷不是 HTTPException，discord.py 也不會重試。"""
        for error in (aiohttp.ClientOSError(104, "reset"), aiohttp.ServerDisconnectedError(), TimeoutError(), OSError("斷線")):
            with self.subTest(type(error).__name__):
                self.events.clear()
                self.channel.sent.clear()
                self.channel.fail = [error]
                self.monitor._download_video.reset_mock()
                await self.send(post(has_video=True))
                self.assertEqual([c.args[0] for c in self.monitor._download_video.await_args_list], [HD, SD])
                self.assertEqual(self.events[-1], "傳 fb_111.mp4")

    async def test_connection_errors_on_both_give_the_link(self):
        self.channel.fail = [aiohttp.ClientOSError(104, "reset"), aiohttp.ServerDisconnectedError()]
        notes = []
        self.assertTrue(await self.send(post(has_video=True), notes=notes))
        self.assertIn(URL, self.channel.sent[-1]["content"])
        self.assertEqual(notes, ["影片沒傳成，改放連結"])
        self.assertEqual(self.monitor.mark_content_as_sent.await_count, 1)

    async def test_one_broken_video_does_not_stop_the_next(self):
        videos = [dict(VIDEO, id="1"), dict(VIDEO, id="2")]
        self.monitor.refresh_media = mock.AsyncMock(return_value={"images": [], "videos": videos})
        real_upload = self.monitor._upload_video

        async def upload(target, reply, video):
            if video["id"] == "1":
                raise KeyError("id")
            return await real_upload(target, reply, video)

        self.monitor._upload_video = upload
        await self.send(post(has_video=True))
        self.assertIn("傳 fb_2.mp4", self.events)
        self.assertIn(URL, self.channel.sent[-1]["content"], "第一支壞掉要給連結")

    async def test_nothing_works_gives_the_article_link(self):
        self.monitor._download_video = mock.AsyncMock(return_value=None)
        notes = []
        self.assertTrue(await self.send(post(has_video=True, url="https://www.facebook.com/x/posts/別篇"), notes=notes))
        self.assertEqual(self.events[:2], ["主文", "記已送"])
        self.assertIn(URL, self.channel.sent[-1]["content"], "連結用 pfbid，url 欄可能是別篇")
        self.assertIs(self.channel.sent[-1]["reference"], self.main)
        self.assertEqual(notes, ["影片沒傳成，改放連結"])

    async def test_refresh_failure_gives_the_link_without_cover(self):
        self.monitor.refresh_media = mock.AsyncMock(return_value=None)
        self.assertTrue(await self.send(post(has_video=True)))
        self.monitor._download_video.assert_not_called()
        self.assertIn(URL, self.channel.sent[-1]["content"])

    async def test_video_without_download_url_gives_the_link(self):
        self.monitor.refresh_media = mock.AsyncMock(return_value={"images": [], "videos": [{"id": "1", "hd_url": None, "sd_url": None}]})
        await self.send(post(has_video=True))
        self.assertIn(URL, self.channel.sent[-1]["content"])

    async def test_extra_videos_get_a_link(self):
        videos = [dict(VIDEO, id=str(i)) for i in range(module._MAX_VIDEOS + 1)]
        self.monitor.refresh_media = mock.AsyncMock(return_value={"images": [], "videos": videos})
        await self.send(post(has_video=True))
        self.assertEqual(sum(1 for e in self.events if e.endswith(".mp4")), module._MAX_VIDEOS)
        self.assertIn(URL, self.channel.sent[-1]["content"])

    async def test_refreshes_once_across_channels(self):
        fb_post = post(has_video=True)
        await self.send(fb_post)
        await self.send(fb_post)
        self.monitor.refresh_media.assert_awaited_once_with(926)

    async def test_failed_refresh_is_not_repeated_for_the_next_channel(self):
        """爬蟲重開最久要等幾分鐘，已經失敗就不要每個頻道再等一次。"""
        self.monitor.refresh_media = mock.AsyncMock(return_value=None)
        fb_post = post(has_video=True)
        await self.send(fb_post)
        await self.send(fb_post)
        self.monitor.refresh_media.assert_awaited_once_with(926)

    async def test_partial_refetch_on_first_send_is_logged_and_counts_as_sent(self):
        """自動發文沒有操作者可以告訴，少圖要留在 log；這篇照樣算送過。"""
        self.monitor.refresh_media = mock.AsyncMock(return_value={"images": ["https://a/1.jpg"], "videos": [VIDEO], "expected_images": 14})
        with self.assertLogs(module.logger, "WARNING") as logs:
            self.assertTrue(await self.send(post(has_video=True)))
        self.assertTrue(any("少了 12 張" in line for line in logs.output))
        self.assertEqual(self.monitor.mark_content_as_sent.await_count, 1)

    async def test_photo_post_is_not_refreshed(self):
        await self.send(post(images=["https://a/1.jpg", "https://a/2.jpg"]))
        self.monitor.refresh_media.assert_not_called()
        self.monitor._download_video.assert_not_called()
        self.assertEqual(self.events, ["主文", "記已送", "傳圖"])

    async def test_video_plus_photos_sends_photos_then_video(self):
        self.monitor.refresh_media = mock.AsyncMock(return_value={"images": ["https://a/1.jpg", "https://a/2.jpg"], "videos": [VIDEO]})
        await self.send(post(has_video=True))
        self.assertEqual(self.events, ["主文", "記已送", "傳圖", "傳 fb_111.mp4"])


class SentRecordTest(Base):
    async def test_unexpected_video_error_still_counts_as_sent(self):
        """沒列到的例外也一樣：這裡漏接的話，主文會每小時重發。"""
        self.monitor._upload_video = mock.AsyncMock(side_effect=KeyError("id"))
        notes = []
        self.assertTrue(await self.send(post(has_video=True), notes=notes))
        self.assertEqual(self.monitor.mark_content_as_sent.await_count, 1)
        self.assertEqual(self.events.count("主文"), 1)
        self.assertIn(URL, self.channel.sent[-1]["content"], "影片壞掉也要有連結")
        self.assertTrue(notes)

    async def test_link_failure_still_counts_as_sent(self):
        self.monitor._download_video = mock.AsyncMock(return_value=None)
        self.channel.fail = [aiohttp.ClientOSError(104, "reset")]
        notes = []
        self.assertTrue(await self.send(post(has_video=True), notes=notes))
        self.assertEqual(self.monitor.mark_content_as_sent.await_count, 1)
        self.assertEqual(notes, ["影片送到一半失敗，請看 log"])

    async def test_image_connection_error_is_counted_and_video_still_goes(self):
        self.monitor.refresh_media = mock.AsyncMock(return_value={"images": ["https://a/1.jpg", "https://a/2.jpg"], "videos": [VIDEO]})
        self.channel.fail = [aiohttp.ClientOSError(104, "reset")]
        notes = []
        self.assertTrue(await self.send(post(has_video=True), notes=notes))
        self.assertIn("傳 fb_111.mp4", self.events)
        self.assertEqual(notes, ["少了 1 張圖"])

    async def test_unexpected_image_error_does_not_stop_the_video(self):
        self.monitor._send_rest_images = mock.AsyncMock(side_effect=KeyError("圖"))
        notes = []
        self.assertTrue(await self.send(post(has_video=True), notes=notes))
        self.assertIn("傳 fb_111.mp4", self.events)
        self.assertEqual(notes, ["圖片送到一半失敗，請看 log"])

    async def test_image_batch_failure_still_counts_as_sent(self):
        self.channel.fail = [http_error(500)]
        notes = []
        self.assertTrue(await self.send(post(images=["https://a/1.jpg", "https://a/2.jpg", "https://a/3.jpg"]), notes=notes))
        self.assertEqual(self.monitor.mark_content_as_sent.await_count, 1)
        self.assertEqual(notes, ["少了 2 張圖"])

    async def test_download_failures_are_counted(self):
        self.monitor._download_image_as_file = mock.AsyncMock(return_value=None)
        notes = []
        await self.send(post(images=["https://a/1.jpg", "https://a/2.jpg"]), notes=notes)
        self.assertEqual(notes, ["少了 2 張圖"])

    async def test_failed_main_post_is_not_marked(self):
        self.main_fails = True
        self.assertFalse(await self.send(post()))
        self.monitor.mark_content_as_sent.assert_not_called()

    async def test_marked_before_anything_else_is_sent(self):
        await self.send(post(images=["https://a/1.jpg", "https://a/2.jpg"], has_video=True))
        self.assertEqual(self.events[:2], ["主文", "記已送"])

    async def test_no_notes_argument_is_fine(self):
        self.monitor._download_video = mock.AsyncMock(return_value=None)
        self.channel.fail = []
        self.assertTrue(await self.send(post(has_video=True)))


class ResendTest(Base):
    async def test_resend_uses_fresh_urls(self):
        self.monitor.fetch_fb_post_by_id = mock.AsyncMock(return_value=post(images=["https://a/old.jpg"]))
        self.monitor.refresh_media = mock.AsyncMock(return_value={"images": ["https://a/new.jpg"], "videos": []})
        fb_post = await self.monitor.fetch_fb_post_for_resend(926)
        self.assertEqual(fb_post["images"], ["https://a/new.jpg"])

    async def test_resend_finds_video_even_without_cover_flag(self):
        self.monitor.fetch_fb_post_by_id = mock.AsyncMock(return_value=post())
        fb_post = await self.monitor.fetch_fb_post_for_resend(926)
        self.assertTrue(fb_post["has_video"])
        await self.send(fb_post)
        self.assertIn("傳 fb_111.mp4", self.events)
        self.assertEqual(self.monitor.refresh_media.await_count, 1, "發送時不用再重開一次")

    async def test_refresh_failure_keeps_stored_images_and_tells_operator(self):
        self.monitor.fetch_fb_post_by_id = mock.AsyncMock(return_value=post(images=["https://a/old.jpg"]))
        self.monitor.refresh_media = mock.AsyncMock(return_value=None)
        notes = []
        fb_post = await self.monitor.fetch_fb_post_for_resend(926, notes=notes)
        self.assertEqual(fb_post["images"], ["https://a/old.jpg"])
        self.assertEqual(len(notes), 1)

    async def test_empty_refresh_keeps_stored_images(self):
        self.monitor.fetch_fb_post_by_id = mock.AsyncMock(return_value=post(images=["https://a/old.jpg"]))
        self.monitor.refresh_media = mock.AsyncMock(return_value={"images": [], "videos": []})
        fb_post = await self.monitor.fetch_fb_post_for_resend(926)
        self.assertEqual(fb_post["images"], ["https://a/old.jpg"])

    async def test_partial_refetch_tells_operator(self):
        """翻照片可能中途放棄：重開只拿到一部分時要講，不能只回成功。"""
        self.monitor.fetch_fb_post_by_id = mock.AsyncMock(return_value=post(images=[f"https://a/{i}.jpg" for i in range(14)]))
        self.monitor.refresh_media = mock.AsyncMock(return_value={"images": ["https://a/n1.jpg", "https://a/n2.jpg", "https://a/n3.jpg"], "videos": [], "expected_images": 14})
        notes = []
        fb_post = await self.monitor.fetch_fb_post_for_resend(926, notes=notes)
        self.assertEqual(len(fb_post["images"]), 3, "舊網址可能都過期了，3 張新的還是比較可靠")
        self.assertEqual(notes, ["重開少了 11 張（頁面表示 14 張）"])

    async def test_stored_duplicate_rows_are_not_missing_images(self):
        self.monitor.fetch_fb_post_by_id = mock.AsyncMock(return_value=post(images=["https://a/1.jpg"] * 4))
        self.monitor.refresh_media = mock.AsyncMock(return_value={"images": ["https://a/n1.jpg"], "videos": [], "expected_images": None})
        notes = []
        await self.monitor.fetch_fb_post_for_resend(926, notes=notes)
        self.assertEqual(notes, [], "資料庫的重複列不算少圖")

    async def resend_with(self, images, videos, expected):
        self.monitor.fetch_fb_post_by_id = mock.AsyncMock(return_value=post())
        self.monitor.refresh_media = mock.AsyncMock(return_value={
            "images": [f"https://a/{i}.jpg" for i in range(images)], "videos": videos, "expected_images": expected,
        })
        notes = []
        await self.monitor.fetch_fb_post_for_resend(926, notes=notes)
        return notes

    async def test_every_image_back_says_nothing(self):
        self.assertEqual(await self.resend_with(14, [], 14), [])

    async def test_more_than_the_page_shows_says_nothing(self):
        self.assertEqual(await self.resend_with(15, [], 14), [])

    async def test_video_takes_one_cell_of_the_page_total(self):
        self.assertEqual(await self.resend_with(13, [VIDEO], 14), [], "13 張加 1 支影片就是全部，不能回報少圖")

    async def test_real_shortfall_with_a_video_is_reported(self):
        self.assertEqual(await self.resend_with(12, [VIDEO], 14), ["重開少了 1 張（頁面表示 14 張）"])

    async def test_failed_refetch_of_post_without_images_does_not_mention_images(self):
        self.monitor.fetch_fb_post_by_id = mock.AsyncMock(return_value=post(images=[]))
        self.monitor.refresh_media = mock.AsyncMock(return_value=None)
        notes = []
        await self.monitor.fetch_fb_post_for_resend(926, notes=notes)
        self.assertEqual(notes, ["沒能重開原貼文"])

    async def test_missing_post(self):
        self.monitor.fetch_fb_post_by_id = mock.AsyncMock(return_value=None)
        self.assertIsNone(await self.monitor.fetch_fb_post_for_resend(926))
        self.monitor.refresh_media.assert_not_called()

    async def resend_result(self, fb):
        cog = ArticleCommands.__new__(ArticleCommands)
        cog.bot = SimpleNamespace(get_channel=lambda cid: SimpleNamespace(name="官方公告"))
        cog.article_monitor = object()
        cog.fb_monitor = fb
        cog.__dict__["monitored_channels"] = [1]
        with mock.patch.object(ArticleCommands, "monitored_channels", [1], create=True):
            return await cog.resend_result("926", "fb")

    async def test_operator_sees_what_is_missing(self):
        fb = SimpleNamespace()

        async def fetch(fb_id, notes=None):
            notes.append("沒能重開原貼文")
            return post()

        async def send(channel_id, content, *, force_event_rebuild=False, notes=None):
            self.assertTrue(force_event_rebuild)
            notes.append("影片沒傳成，改放連結")
            return True

        fb.fetch_fb_post_for_resend = fetch
        fb.send_fb_post_to_channel = send
        result = await self.resend_result(fb)
        self.assertIn("✅", result)
        self.assertIn("影片沒傳成", result)
        self.assertIn("沒能重開原貼文", result)

    async def test_operator_sees_plain_success_when_nothing_is_missing(self):
        fb = SimpleNamespace()

        async def fetch(fb_id, notes=None):
            return post()

        async def send(channel_id, content, *, force_event_rebuild=False, notes=None):
            return True

        fb.fetch_fb_post_for_resend = fetch
        fb.send_fb_post_to_channel = send
        result = await self.resend_result(fb)
        self.assertIn("✅", result)
        self.assertNotIn("⚠️", result)


class FakeContent:
    def __init__(self, chunks, seen):
        self.chunks = chunks
        self.seen = seen

    async def iter_chunked(self, size):
        for chunk in self.chunks:
            self.seen.append(len(chunk))
            yield chunk


class FakeResponse:
    def __init__(self, status=200, content_length=None, chunks=(), seen=None):
        self.status = status
        self.content_length = content_length
        self.content = FakeContent(list(chunks), seen if seen is not None else [])

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class FakeSession:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.kwargs = None

    def get(self, url, **kw):
        self.kwargs = kw
        if self.error:
            raise self.error
        return self.response


class DownloadVideoTest(unittest.IsolatedAsyncioTestCase):
    async def download(self, session, limit=10):
        return await FBMonitor._download_video(HD, session, limit)

    async def test_downloads_whole_file(self):
        data = await self.download(FakeSession(FakeResponse(content_length=6, chunks=[b"abc", b"def"])))
        self.assertEqual(data.read(), b"abcdef", "要回到開頭，不然會傳出空檔")

    async def test_declared_too_large_is_not_read(self):
        seen = []
        data = await self.download(FakeSession(FakeResponse(content_length=11, chunks=[b"x" * 11], seen=seen)))
        self.assertIsNone(data)
        self.assertEqual(seen, [])

    async def test_undeclared_too_large_stops_reading(self):
        seen = []
        data = await self.download(FakeSession(FakeResponse(chunks=[b"x" * 8, b"y" * 8, b"z" * 8], seen=seen)))
        self.assertIsNone(data)
        self.assertEqual(len(seen), 2, "超過就中止，不把整支讀完")

    async def test_exactly_at_limit_is_fine(self):
        data = await self.download(FakeSession(FakeResponse(content_length=10, chunks=[b"x" * 10])))
        self.assertIsNotNone(data)

    async def test_expired_url(self):
        self.assertIsNone(await self.download(FakeSession(FakeResponse(status=403))))

    async def test_connection_error(self):
        self.assertIsNone(await self.download(FakeSession(error=aiohttp.ClientError("斷線"))))

    async def test_timeout(self):
        self.assertIsNone(await self.download(FakeSession(error=TimeoutError())))

    async def test_uses_video_timeout(self):
        session = FakeSession(FakeResponse(chunks=[b"x"]))
        await self.download(session)
        self.assertEqual(session.kwargs["timeout"], module._VIDEO_DOWNLOAD_TIMEOUT)


class RefreshMediaTest(unittest.IsolatedAsyncioTestCase):
    async def call(self, status=200, body=None, error=None):
        class Resp:
            def __init__(self):
                self.status = status

            async def json(self):
                return body

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

        class Session:
            def __init__(self, timeout=None):
                Session.timeout = timeout

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            def post(self, url):
                Session.url = url
                if error:
                    raise error
                return Resp()

        monitor = FBMonitor.__new__(FBMonitor)
        monitor.scraper_api_url = "http://scraper:8000"
        with mock.patch.object(module.aiohttp, "ClientSession", Session):
            result = await monitor.refresh_media(926)
        return result, Session

    async def test_success(self):
        body = {"success": True, "images": ["https://a/1.jpg"], "videos": []}
        result, session = await self.call(body=body)
        self.assertEqual(result, body)
        self.assertEqual(session.url, "http://scraper:8000/api/fb_posts/926/refresh")
        self.assertGreater(session.timeout.total, 300, "可能要排隊等每小時那一輪")

    async def test_scraper_says_no(self):
        self.assertIsNone((await self.call(body={"success": False, "message": "壞了"}))[0])

    async def test_bad_status(self):
        self.assertIsNone((await self.call(status=500))[0])

    async def test_connection_error(self):
        self.assertIsNone((await self.call(error=aiohttp.ClientError("斷線")))[0])


class UploadLimitTest(unittest.TestCase):
    def test_channel_uses_its_guild(self):
        self.assertEqual(upload_limit(SimpleNamespace(guild=GUILD)), GUILD.filesize_limit - 512 * 1024)

    def test_guild_directly(self):
        self.assertEqual(upload_limit(GUILD), GUILD.filesize_limit - 512 * 1024)

    def test_no_guild_uses_the_fallback(self):
        self.assertEqual(upload_limit(SimpleNamespace(guild=None)), 25 * 1024 * 1024 - 512 * 1024)
        self.assertEqual(upload_limit(object()), 25 * 1024 * 1024 - 512 * 1024)


if __name__ == "__main__":
    unittest.main()
