"""影片連結轉貼（utils/link_fix.py、services/relay/link_repost.py）與給模型看的連結預覽（chat_line、插話）。

真實案例：11-04 一支 X 影片 bot 轉了 fixupx，Discord 卻沒長出預覽，原預覽又在轉貼前就被壓掉，群組那則什麼都看不到；
11-08 群友回覆 vxbilibili 連結問「你看到了哪些摘要」，模型拿到的只有網址，回「連結我打不開」；
回覆 bot 轉貼的 8 次都被當成在叫它、一定回，有一次還回成像是它自己貼的連結。

守的底線：
- bilibili 只轉 bilibili.com/video/BV…（www.、m.、語言路徑都認），b23.tv 與已經是 vx 的不轉；只留 p、t 參數
- X 只轉影片；fixupx 做不出預覽換 vxtwitter，都做不出來就不轉；圖片貼文不轉也不預檢
- 預檢照 Discord 的讀法：頁面標籤（vxtwitter 用 name=）或 fixupx 的 Mastodon 相容 API 有影片或圖片才算
- 原連結在暴雷裡，轉貼也包 `||`
- 轉貼用回覆送出、不 @ 原貼者；轉貼長出影片或圖片預覽才壓原訊息的預覽，等不到就刪掉轉貼、原預覽留著
- 聊天行：群友打的字一字不改，預覽用 `[預覽：…]` 接在後面；bot 的自動轉貼標「（自動轉貼 #N 的連結）」、不加 ↩；
  bot 自己組的 embed、暴雷的連結不給預覽；fixupx 描述裡的 markdown 連結只留文字
- 存進向量庫的文字跟以前一字不差
- 插話：回 bot 的自動轉貼不算在叫它（內文真的打 @ 才算）；被回覆的轉貼標出原貼者；原訊息的預覽被壓掉時拿轉貼上的；
  降溫閘不把影片標題當成群友在嫌它吵
- 標記的意思寫在共用的 system_safety_prompt

執行：
    cd src && python -m unittest test.test_link_fix -v
"""

import asyncio
import json
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

import discord  # noqa: E402

from llm.ambient import ambient_reply  # noqa: E402
from llm.preprocess import chat_line  # noqa: E402
from llm.preprocess.chat_line import fetch_recent_lines, format_chat_line, name_with_anchor  # noqa: E402
from llm.storage import store_chat  # noqa: E402
from services.relay import link_repost  # noqa: E402
from utils import link_fix  # noqa: E402
from utils.link_fix import FixedLink  # noqa: E402

TZ8 = timezone(timedelta(hours=8))
WHEN = datetime(2026, 11, 9, 4, 0, tzinfo=timezone.utc)
BOT_ID = 900000000000009999

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


# ── 聊天行 ──

def _author(name, uid, bot=False):
    return SimpleNamespace(display_name=name, name=name, id=uid, bot=bot)


def _msg(mid, content, author, *, embeds=(), ref=None, created=WHEN):
    return SimpleNamespace(id=mid, content=content, author=author, created_at=created, stickers=[], attachments=[],
                           embeds=list(embeds), reference=(SimpleNamespace(message_id=ref) if ref else None))


class _Channel:
    def __init__(self, newest_first):
        self._msgs = newest_first

    def history(self, **kwargs):
        msgs = self._msgs

        async def gen():
            for m in msgs:
                yield m
        return gen()


A = _author("群友A", 111100001234)
B = _author("群友B", 222200005678)
BOT = _author("Violette", BOT_ID, bot=True)
BILI = _embed(title="【鳴潮】小朋友走散了", description="因為看其他人做的二創人物都有糯糯的說話", thumbnail="https://i.hdslb/a.jpg",
              url="https://www.vxbilibili.com/video/BV1")


class ChatLineTests(unittest.TestCase):
    def test_preview_is_marked_after_the_members_own_words(self):
        line = format_chat_line(_msg(1, "看這個 https://youtu.be/x", A, embeds=[BILI]), TZ8, time_only=True)
        self.assertIn("群友A#1234: 看這個 https://youtu.be/x [預覽：【鳴潮】小朋友走散了 - 因為看其他人做的二創人物都有糯糯的說話]", line)

    def test_bots_own_embeds_are_not_link_previews(self):
        line = format_chat_line(_msg(1, "今天的公告整理", BOT, embeds=[_embed(title="公告", description="內文")]), TZ8)
        self.assertNotIn("預覽", line)

    def test_repost_line_is_marked_as_a_repost_of_the_original_not_a_reply(self):
        original = _msg(1, "https://www.bilibili.com/video/BV1", A)
        repost = _msg(2, "https://www.vxbilibili.com/video/BV1", BOT, embeds=[BILI], ref=1)
        reply = _msg(3, "好可愛", B, ref=2)
        lines, _ = asyncio.run(fetch_recent_lines(_Channel([reply, repost, original]), tz=TZ8, limit=10,
                                                  self_id=BOT_ID, thread_replies=True))
        self.assertTrue(lines[0].endswith("群友A#1234: https://www.bilibili.com/video/BV1"), lines[0])
        self.assertIn("Violette#9999(你自己): https://www.vxbilibili.com/video/BV1（自動轉貼 #1 的連結） [預覽：【鳴潮】小朋友走散了", lines[1])
        self.assertNotIn("↩", lines[1])
        self.assertTrue(lines[2].endswith("群友B#5678: 好可愛 ↩#2"), lines[2])

    def test_older_reposts_without_a_reply_link_still_say_they_are_reposts(self):
        line = format_chat_line(_msg(2, "https://fixupx.com/a/status/2", BOT), TZ8)
        self.assertIn("https://fixupx.com/a/status/2（自動轉貼的連結）", line)

    def test_spoilered_links_get_no_preview_or_thumbnail(self):
        msg = _msg(1, "||https://www.bilibili.com/video/BV1||", A, embeds=[BILI])
        self.assertNotIn("預覽", format_chat_line(msg, TZ8))
        self.assertEqual(chat_line.preview_image_urls(msg, limit=2), [])

    def test_fixupx_markdown_links_keep_only_their_text(self):
        desc = "看完这个视频\n\n**[💬](https://x.com/intent/tweet?in_reply_to=2) 12 [🔁](https://x.com/intent/retweet?tweet_id=2) 3**"
        line = format_chat_line(_msg(2, "https://fixupx.com/a/status/2", BOT, embeds=[_embed(description=desc)]), TZ8)
        self.assertIn("[預覽：看完这个视频 💬 12 🔁 3]", line)
        self.assertNotIn("](https", line)

    def test_thumbnails_prefer_the_discord_proxy_and_skip_x(self):
        proxied = SimpleNamespace(title="t", description=None, url="https://youtu.be/x", video=None, image=None,
                                  thumbnail=SimpleNamespace(url="https://i.ytimg/a.jpg", proxy_url="https://media.discordapp.net/a.jpg"))
        tweet = _embed(image="https://pbs.twimg.com/a.jpg", url="https://twitter.com/a/status/2")
        msg = _msg(1, "https://youtu.be/x https://x.com/a/status/2", A, embeds=[tweet, proxied])
        self.assertEqual(chat_line.preview_image_urls(msg, limit=2), ["https://media.discordapp.net/a.jpg"])

    def test_text_stored_in_the_vector_store_is_unchanged(self):
        self.assertEqual(
            store_chat.compose_persist_text("https://youtu.be/x", [], ["標題 - 描述"]),
            "https://youtu.be/x [預覽：標題 - 描述]",
        )
        msg = _msg(1, "https://fixupx.com/a/status/2", A, embeds=[_embed(description="[x](https://x.com/y) **z**")])
        self.assertEqual(store_chat._build_persist_text(msg),
                         "https://fixupx.com/a/status/2 [預覽：[x](https://x.com/y) **z**]",
                         "向量庫的寫法不動（markdown 清理只做在給模型看的聊天行）")


# ── 插話 ──

def _bot(*cached):
    return SimpleNamespace(user=SimpleNamespace(id=BOT_ID), cached_messages=list(cached))


def _reply_to(target, content="笑死", *, mentions=()):
    return SimpleNamespace(content=content, mentions=list(mentions),
                           reference=SimpleNamespace(resolved=target, message_id=getattr(target, "id", None)))


class _Msg(discord.Message):
    """讓 isinstance(…, discord.Message) 成立的假訊息。"""

    def __init__(self, mid, content, author, *, embeds=(), ref=None):  # noqa: D107 — 不呼叫 discord 的建構子
        self.id = mid
        self.content = content
        self.author = author
        self.embeds = list(embeds)
        self.stickers = []
        self.attachments = []
        self.reference = SimpleNamespace(message_id=ref, resolved=None) if ref else None
        self.channel = SimpleNamespace(fetch_message=mock.AsyncMock(side_effect=discord.NotFound(
            SimpleNamespace(status=404, reason="Not Found"), "gone")))

    def __repr__(self):
        return f"<_Msg {self.id}>"


class DirectedTests(unittest.TestCase):
    def setUp(self):
        self.bot = _bot()
        self.me = self.bot.user
        self.repost = _Msg(2, "https://fixupx.com/a/status/2", _author("Violette", BOT_ID, bot=True), ref=1)
        self.bot_talk = _Msg(3, "耀眼的人去日K", _author("Violette", BOT_ID, bot=True))

    def test_replying_to_a_repost_with_the_default_ping_is_not_calling_it(self):
        self.assertFalse(ambient_reply._is_directed(self.bot, _reply_to(self.repost, mentions=[self.me])))
        self.assertFalse(ambient_reply._is_directed(self.bot, _reply_to(self.repost)))

    def test_typing_an_at_mention_still_calls_it(self):
        msg = _reply_to(self.repost, f"<@{BOT_ID}> 這影片在講什麼", mentions=[self.me])
        self.assertTrue(ambient_reply._is_directed(self.bot, msg))

    def test_replying_to_what_it_said_still_calls_it(self):
        self.assertTrue(ambient_reply._is_directed(self.bot, _reply_to(self.bot_talk, mentions=[self.me])))
        self.assertTrue(ambient_reply._is_directed(self.bot, _reply_to(self.bot_talk)))

    def test_plain_mentions_and_unresolved_replies_still_count(self):
        self.assertTrue(ambient_reply._is_directed(
            self.bot, SimpleNamespace(content=f"<@!{BOT_ID}> 嗨", mentions=[self.me], reference=None)))
        self.assertTrue(ambient_reply._is_directed(
            self.bot, SimpleNamespace(content="嗨", mentions=[self.me],
                                      reference=SimpleNamespace(resolved=None, message_id=9))))


class LinkPreviewContextTests(unittest.TestCase):
    def setUp(self):
        self.original = _Msg(1, "https://www.bilibili.com/video/BV1", A)   # 預覽已被壓掉
        self.repost = _Msg(2, "https://www.vxbilibili.com/video/BV1", _author("Violette", BOT_ID, bot=True),
                           embeds=[BILI], ref=1)
        self.bot = _bot(self.original, self.repost)
        self.downloads = []

        async def fake_download(session, urls, **kwargs):
            self.downloads.append(list(urls))
            return ["IMG"] * len(urls)

        patcher = mock.patch.object(ambient_reply, "download_images", fake_download)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _ctx(self, msg):
        return asyncio.run(ambient_reply._link_preview_context(self.bot, msg))

    def test_replied_repost_names_who_posted_the_video(self):
        note, images = self._ctx(self.repost)
        self.assertEqual(
            note,
            f"（自動轉貼 {name_with_anchor(A)} 的連結） [預覽：【鳴潮】小朋友走散了 - 因為看其他人做的二創人物都有糯糯的說話]",
        )
        self.assertEqual(images, ["IMG"])
        self.assertEqual(self.downloads, [["https://i.hdslb/a.jpg"]])

    def test_suppressed_original_borrows_the_reposts_preview(self):
        note, images = self._ctx(self.original)
        self.assertTrue(note.startswith(" [預覽：【鳴潮】小朋友走散了"), note)
        self.assertNotIn("自動轉貼", note)
        self.assertEqual(images, ["IMG"])

    def test_plain_text_gets_nothing_and_downloads_nothing(self):
        self.assertEqual(self._ctx(_Msg(5, "今天抽卡又歪了", A)), ("", []))
        self.assertEqual(self.downloads, [])

    def test_waits_for_a_late_preview_but_not_for_plain_text_or_x(self):
        late = _Msg(6, "這是什麼 https://youtu.be/x", A)
        sleeps = []

        async def fake_sleep(seconds):
            sleeps.append(seconds)
            if len(sleeps) == 2:
                late.embeds = [BILI]   # Discord 的更新事件就地改了訊息物件

        with mock.patch.object(ambient_reply, "_async_sleep", fake_sleep):
            asyncio.run(ambient_reply._await_link_previews(self.bot, late))
            self.assertEqual(len(sleeps), 2)
            for content in ("今天抽卡又歪了", "https://x.com/a/status/2", "||https://youtu.be/x||"):
                sleeps.clear()
                asyncio.run(ambient_reply._await_link_previews(self.bot, _Msg(7, content, A)))
                self.assertEqual(sleeps, [], content)

    def test_gives_up_waiting_after_the_limit(self):
        sleeps = []

        async def fake_sleep(seconds):
            sleeps.append(seconds)

        with mock.patch.object(ambient_reply, "_async_sleep", fake_sleep):
            asyncio.run(ambient_reply._await_link_previews(self.bot, _Msg(8, "https://youtu.be/x", A)))
        self.assertAlmostEqual(sum(sleeps), ambient_reply._SETTINGS.link_preview_wait_seconds)


class BackoffTests(unittest.TestCase):
    def test_video_titles_are_not_members_telling_it_to_shut_up(self):
        msg = SimpleNamespace(content="笑死")
        ctx = ["#1 [12:00] 群友A#1234: https://youtu.be/x [預覽：叫你閉嘴你聽不懂 - 精華]"]
        self.assertFalse(ambient_reply._has_chime_backoff_signal(msg, ctx))
        self.assertTrue(ambient_reply._has_chime_backoff_signal(msg, ["#1 [12:00] 群友A#1234: 你可以閉嘴嗎"]))


class WiredInTests(unittest.TestCase):
    """on_message 丟背景跑新的轉貼流程；插話的被回覆那則、最新那則都有接上預覽。"""

    def test_on_message_and_ambient_use_it(self):
        import inspect

        with open(os.path.join(SRC_DIR, "discord_bot.py"), encoding="utf-8") as f:
            bot_src = f.read()
        self.assertIn("spawn(repost_fixed_links(bot, message)", bot_src)
        self.assertNotIn("select_video_links", bot_src)
        src = inspect.getsource(ambient_reply._gather_inputs)
        self.assertIn("await _link_preview_context(bot, replied_msg)", src)
        self.assertIn("replied_to_text = rtext + reply_link_note", src)
        self.assertIn("await _await_link_previews(bot, message)", src)
        self.assertIn("await _link_preview_context(bot, message)", src)

    def test_latest_message_carries_its_link_note_exactly_once(self):
        msg = _msg(10, "這是什麼 https://youtu.be/x", A, embeds=[BILI])
        note = " [預覽：從轉貼拿的]"
        prompt, _, _ = ambient_reply._frame_latest(msg, True, "這是什麼 https://youtu.be/x", None, [], [], {},
                                                   "群友A#1234", note)
        self.assertEqual(prompt, "這是什麼 https://youtu.be/x [預覽：從轉貼拿的]")
        _, ctx, _ = ambient_reply._frame_latest(msg, False, "這是什麼 https://youtu.be/x", None, [], [], {},
                                                "群友A#1234", note)
        self.assertEqual(ctx[-1].count("[預覽："), 1, ctx[-1])
        self.assertTrue(ctx[-1].endswith("https://youtu.be/x [預覽：從轉貼拿的]"), ctx[-1])


class PromptExplainsMarkersTests(unittest.TestCase):
    def test_shared_safety_prompt_explains_both_markers(self):
        with open(os.path.join(SRC_DIR, "settings", "prompts", "llm_context_safety_rules.json"), encoding="utf-8") as f:
            prompt = json.load(f)["system_safety_prompt"]
        self.assertIn("[預覽：…]", prompt)
        self.assertIn("不是發話者打的字", prompt)
        self.assertIn("自動轉貼", prompt)


if __name__ == "__main__":
    unittest.main()
