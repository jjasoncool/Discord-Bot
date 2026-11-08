"""影片連結轉貼（utils/link_fix.py、services/relay/link_repost.py）。

真實案例：11-04 一支 X 影片 bot 轉了 fixupx，Discord 卻沒長出預覽，原預覽又在轉貼前就被壓掉，群組那則什麼都看不到。

守的底線：
- bilibili 只轉 bilibili.com/video/BV…（www.、m.、語言路徑都認），b23.tv 與已經是 vx 的不轉；只留 p、t 參數
- X 只轉影片；fixupx 做不出預覽換 vxtwitter，都做不出來就不轉；圖片貼文不轉也不預檢
- 預檢照 Discord 的讀法：頁面標籤（vxtwitter 用 name=）或 fixupx 的 Mastodon 相容 API 有影片或圖片才算
- 原連結在暴雷裡，轉貼也包 `||`
- 轉貼用回覆送出、不 @ 原貼者；轉貼長出影片或圖片預覽才壓原訊息的預覽，等不到就刪掉轉貼、原預覽留著

執行：
    cd src && python -m unittest test.test_link_fix -v
"""

import asyncio
import os
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

import discord  # noqa: E402

from services.relay import link_repost  # noqa: E402
from utils import link_fix  # noqa: E402
from utils.link_fix import FixedLink  # noqa: E402


VIDEO_PAGE = '<meta property="og:title" content="t"><meta property="og:video" content="https://media.example/v.mp4">'
VX_PAGE = '<meta name="og:title" content="t" /><meta name="twitter:player:stream" content="https://video.twimg.com/a.mp4" />'
TITLE_ONLY_PAGE = '<meta property="og:title" content="WuWa News (@WutheringNews)"/><meta property="twitter:card" content="player"/>'
# fixupx：頁面只有標題，影片在 activity+json 連結指的 Mastodon 相容 API
FX_PAGE = (TITLE_ONLY_PAGE + "<link href='https://fixupx.com/users/WutheringNews/statuses/6608666766' "
           "rel='alternate' type='application/activity+json'>")
FX_API = "https://fixupx.com/api/v1/statuses/6608666766"
VIDEO_TWEET = {"__typename": "Tweet", "id_str": "1", "mediaDetails": [{"type": "video"}]}
PHOTO_TWEET = {"__typename": "Tweet", "id_str": "1", "mediaDetails": [{"type": "photo"}]}


# ── 假的 HTTP ──

class _Resp:
    def __init__(self, status=200, body="", data=None):
        self.status = status
        self._body = body.encode("utf-8")
        self._data = data
        self.content = SimpleNamespace(read=self._read)

    async def _read(self, n=-1):
        return self._body if n < 0 else self._body[:n]

    async def json(self, content_type=None):
        return self._data

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _Session:
    """依網址回假頁面；syndication 回貼文 JSON。記下打過哪些網址。"""

    def __init__(self, pages=None, tweet=None):
        self.pages = pages or {}
        self.tweet = tweet
        self.urls: list[str] = []

    def get(self, url, headers=None, timeout=None):
        self.urls.append(url)
        if "syndication" in url:
            return _Resp(200, data=self.tweet)
        status, body, *data = self.pages.get(url, (404, ""))
        return _Resp(status, body, data[0] if data else None)


def _select(content, session):
    return asyncio.run(link_fix.select_fixed_links(content, session=session))


class FindLinksTests(unittest.TestCase):
    def test_bilibili_variants_become_vxbilibili_keeping_part_and_time(self):
        cases = {
            "https://www.bilibili.com/video/BV1qq4p68EmR/?spm_id_from=333.1387&vd_source=15bf": "https://www.vxbilibili.com/video/BV1qq4p68EmR",
            "https://m.bilibili.com/video/BV1dxiYB3Ejh?share_source=copy_web&p=2": "https://www.vxbilibili.com/video/BV1dxiYB3Ejh?p=2",
            "https://www.bilibili.com/en/video/BV132q1BuEF9/?t=38&trackid=web": "https://www.vxbilibili.com/video/BV132q1BuEF9?t=38",
            "看這個 https://bilibili.com/video/BV1eF4e6sEra 好笑": "https://www.vxbilibili.com/video/BV1eF4e6sEra",
        }
        for content, want in cases.items():
            with self.subTest(content=content):
                links = link_fix.find_fixable_links(content)
                self.assertEqual([lk.candidates for lk in links], [(want,)])

    def test_short_links_and_already_fixed_links_are_left_alone(self):
        for content in ("【小朋友走散了-嗶哩嗶哩】 https://b23.tv/DnSLnYq",
                        "https://vxbilibili.com/video/BV1VSsd6CE5F?t=38",
                        "https://www.VXbilibili.com/video/BV1MexS6WEjR",
                        "https://fixupx.com/a/status/1",
                        "https://x.com/someone"):
            with self.subTest(content=content):
                self.assertEqual(link_fix.find_fixable_links(content), [])

    def test_x_candidates_are_fixupx_then_vxtwitter(self):
        links = link_fix.find_fixable_links("https://x.com/WutheringNews/status/2117883410727547031?a=b&s=20")
        self.assertEqual(links[0].candidates, (
            "https://fixupx.com/WutheringNews/status/2117883410727547031",
            "https://vxtwitter.com/WutheringNews/status/2117883410727547031",
        ))
        self.assertEqual(links[0].tweet_id, "2117883410727547031")

    def test_spoilered_links_are_reposted_inside_spoilers(self):
        links = link_fix.find_fixable_links("||https://x.com/a/status/2?s=20|| 和 https://www.bilibili.com/video/BV1eF4e6sEra")
        self.assertEqual([lk.spoiler for lk in links], [True, False])
        text = link_fix.repost_text([FixedLink("https://fixupx.com/a/status/2", True),
                                     FixedLink("https://www.vxbilibili.com/video/BV1eF4e6sEra", False)])
        self.assertEqual(text, "||https://fixupx.com/a/status/2||\nhttps://www.vxbilibili.com/video/BV1eF4e6sEra")

    def test_repost_text_is_recognised_and_chat_is_not(self):
        self.assertTrue(link_fix.is_repost_text("||https://fixupx.com/a/status/2||\nhttps://www.vxbilibili.com/video/BV1"))
        self.assertTrue(link_fix.is_repost_text("https://vxtwitter.com/a/status/2"))
        self.assertFalse(link_fix.is_repost_text("https://fixupx.com/a/status/2 笑死"))
        self.assertFalse(link_fix.is_repost_text("https://www.bilibili.com/video/BV1eF4e6sEra"))
        self.assertFalse(link_fix.is_repost_text(""))


class ProbeTests(unittest.TestCase):
    def test_media_tags_in_either_attribute_style(self):
        self.assertTrue(link_fix.has_media_meta(VIDEO_PAGE))
        self.assertTrue(link_fix.has_media_meta(VX_PAGE), "vxtwitter 用 name= 與 twitter:player:stream")
        self.assertTrue(link_fix.has_media_meta('<meta content="https://i.example/a.jpg" property="og:image">'))

    def test_title_only_or_empty_media_is_not_a_preview(self):
        self.assertFalse(link_fix.has_media_meta(TITLE_ONLY_PAGE))
        self.assertFalse(link_fix.has_media_meta('<meta property="og:image" content="  ">'))

    def test_status_api_is_found_from_the_activity_link(self):
        self.assertEqual(link_fix.status_api_url(FX_PAGE), FX_API)
        self.assertIsNone(link_fix.status_api_url(TITLE_ONLY_PAGE))

    def test_probe_sends_discordbot_ua_and_fails_on_non_200(self):
        seen = {}

        class S(_Session):
            def get(self, url, headers=None, timeout=None):
                seen["ua"] = (headers or {}).get("User-Agent", "")
                return super().get(url, headers, timeout)

        session = S({"https://ok": (200, VIDEO_PAGE), "https://gone": (404, VIDEO_PAGE)})
        self.assertTrue(asyncio.run(link_fix.probe_preview(session, "https://ok")))
        self.assertIn("Discordbot", seen["ua"])
        self.assertFalse(asyncio.run(link_fix.probe_preview(session, "https://gone")))


class SelectTests(unittest.TestCase):
    URL = "https://x.com/WutheringNews/status/2117883410727547031"
    FIXUPX = "https://fixupx.com/WutheringNews/status/2117883410727547031"
    VX = "https://vxtwitter.com/WutheringNews/status/2117883410727547031"

    def test_fixupx_video_is_read_from_its_mastodon_api_like_discord_does(self):
        session = _Session({self.FIXUPX: (200, FX_PAGE),
                            FX_API: (200, "", {"media_attachments": [{"type": "video", "url": "https://v.mp4"}]})},
                           tweet=VIDEO_TWEET)
        self.assertEqual(_select(self.URL, session), [FixedLink(self.FIXUPX, False)])

    def test_fixupx_api_without_attachments_falls_back(self):
        session = _Session({self.FIXUPX: (200, FX_PAGE), FX_API: (200, "", {"media_attachments": []}),
                            self.VX: (200, VX_PAGE)}, tweet=VIDEO_TWEET)
        self.assertEqual(_select(self.URL, session), [FixedLink(self.VX, False)])

    def test_falls_back_to_vxtwitter_when_fixupx_has_no_video(self):
        session = _Session({self.FIXUPX: (200, TITLE_ONLY_PAGE), self.VX: (200, VX_PAGE)}, tweet=VIDEO_TWEET)
        self.assertEqual(_select(self.URL, session), [FixedLink(self.VX, False)])

    def test_nothing_is_reposted_when_no_service_has_a_preview(self):
        session = _Session({self.FIXUPX: (200, TITLE_ONLY_PAGE), self.VX: (500, "")}, tweet=VIDEO_TWEET)
        self.assertEqual(_select(self.URL, session), [])

    def test_photo_tweets_are_not_probed(self):
        session = _Session({self.FIXUPX: (200, VIDEO_PAGE)}, tweet=PHOTO_TWEET)
        self.assertEqual(_select(self.URL, session), [])
        self.assertFalse([u for u in session.urls if "syndication" not in u], "圖片貼文不該去抓替代網址")

    def test_bilibili_only_needs_the_probe(self):
        vx = "https://www.vxbilibili.com/video/BV1qq4p68EmR"
        session = _Session({vx: (200, VIDEO_PAGE)})
        self.assertEqual(_select("https://www.bilibili.com/video/BV1qq4p68EmR/?vd_source=x", session),
                         [FixedLink(vx, False)])
        self.assertEqual(session.urls, [vx])

    def test_plain_chat_never_opens_a_session(self):
        with mock.patch("aiohttp.ClientSession") as factory:
            self.assertEqual(asyncio.run(link_fix.select_fixed_links("今天抽卡又歪了")), [])
        factory.assert_not_called()


# ── 轉貼流程 ──

def _embed(*, video=None, image=None, thumbnail=None, title=None, description=None, url=None):
    def part(u):
        return SimpleNamespace(url=u, proxy_url=None) if u else SimpleNamespace(url=None, proxy_url=None)
    return SimpleNamespace(title=title, description=description, url=url,
                           video=part(video), image=part(image), thumbnail=part(thumbnail))


class _Repost:
    def __init__(self, embeds=(), fetched_embeds=()):
        self.id = 555
        self.embeds = list(embeds)
        self.channel = SimpleNamespace(fetch_message=mock.AsyncMock(
            return_value=SimpleNamespace(embeds=list(fetched_embeds))))
        self.delete = mock.AsyncMock()


class RepostFlowTests(unittest.TestCase):
    def _run(self, repost, *, fixed=(FixedLink("https://www.vxbilibili.com/video/BV1", False),),
             event=None, suppress_error=None):
        message = SimpleNamespace(content="https://www.bilibili.com/video/BV1", reply=mock.AsyncMock(return_value=repost),
                                  edit=mock.AsyncMock(side_effect=suppress_error))
        checks = []

        async def wait_for(name, check=None, timeout=None):
            checks.append((name, check, timeout))
            if event is not None and check(event):
                return event
            raise asyncio.TimeoutError

        bot = SimpleNamespace(wait_for=wait_for)
        with mock.patch.object(link_repost, "select_fixed_links", mock.AsyncMock(return_value=list(fixed))):
            asyncio.run(link_repost.repost_fixed_links(bot, message))
        return message, checks

    def test_reply_without_ping_and_suppress_after_the_preview_arrives(self):
        repost = _Repost()
        event = SimpleNamespace(message_id=555, data={"embeds": [{"type": "video", "video": {"url": "https://v"}}]})
        message, checks = self._run(repost, fixed=[FixedLink("https://fixupx.com/a/status/2", True)], event=event)
        message.reply.assert_awaited_once_with("||https://fixupx.com/a/status/2||", mention_author=False)
        message.edit.assert_awaited_once_with(suppress=True)
        repost.delete.assert_not_awaited()
        self.assertEqual(checks[0][0], "raw_message_edit")
        self.assertEqual(checks[0][2], link_repost.PREVIEW_WAIT_SECONDS)

    def test_updates_for_other_messages_or_text_only_previews_do_not_count(self):
        repost = _Repost()
        _, checks = self._run(repost)
        check = checks[0][1]
        self.assertFalse(check(SimpleNamespace(message_id=1, data={"embeds": [{"image": {"url": "https://i"}}]})))
        self.assertFalse(check(SimpleNamespace(message_id=555, data={"embeds": [{"title": "只有標題"}]})))
        self.assertTrue(check(SimpleNamespace(message_id=555, data={"embeds": [{"thumbnail": {"url": "https://t"}}]})))

    def test_missed_event_is_rechecked_through_the_api(self):
        repost = _Repost(fetched_embeds=[_embed(image="https://i")])
        message, _ = self._run(repost)
        message.edit.assert_awaited_once_with(suppress=True)
        repost.delete.assert_not_awaited()

    def test_no_preview_in_time_takes_the_repost_back_and_keeps_the_original(self):
        repost = _Repost(fetched_embeds=[_embed(title="WuWa News")])
        message, _ = self._run(repost)
        message.edit.assert_not_awaited()
        repost.delete.assert_awaited_once()

    def test_preview_already_there_skips_waiting(self):
        repost = _Repost(embeds=[_embed(video="https://v")])
        message, checks = self._run(repost)
        self.assertEqual(checks, [])
        message.edit.assert_awaited_once_with(suppress=True)

    def test_nothing_to_fix_sends_nothing(self):
        message, _ = self._run(_Repost(), fixed=())
        message.reply.assert_not_awaited()

    def test_missing_permission_to_suppress_is_only_logged(self):
        repost = _Repost(embeds=[_embed(video="https://v")])
        forbidden = discord.Forbidden(SimpleNamespace(status=403, reason="Forbidden"), "no")
        message, _ = self._run(repost, suppress_error=forbidden)
        repost.delete.assert_not_awaited()


class WiredInTests(unittest.TestCase):
    """on_message 丟背景跑新的轉貼流程。"""

    def test_on_message_uses_it(self):
        with open(os.path.join(SRC_DIR, "discord_bot.py"), encoding="utf-8") as f:
            bot_src = f.read()
        self.assertIn("spawn(repost_fixed_links(bot, message)", bot_src)
        self.assertNotIn("select_video_links", bot_src)


if __name__ == "__main__":
    unittest.main()
