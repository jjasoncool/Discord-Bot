"""IT快訊：內頁晚到時，把先前只帶摘要的訊息就地更新成完整內文（services.relay.it_article_monitor）。

守的底線：
  1. HKEPC 內頁被擋時照樣先發摘要；scraper 之後補到內文，下一次通知就把「同一則」訊息改成完整內文，
     標題連結不變、不另發新訊息，也不用刪舊訊息。站方改了標題（網址裡的標題變了）也對得上。
  2. 只改真的是「摘要版」的那則：內文還沒到的、已經是完整內文的、排版對不上的、別人發的、
     其他文章的訊息都不動（寧可漏補，也不誤改）。
  3. 讀頻道從最新的讀起：剛發出、最需要補的那幾則不能因為讀取上限被擠掉。
  4. 圖片：原本沒圖、內文帶圖時補上第一張，訊息原有的附件保留；帶圖更新失敗時退回只換文字；
     原本就有圖時沿用，並改用附件引用（讀回來的圖片網址會過期）。
  5. 每次通知都會檢查（就算這次沒有新文章），而且新文先發、再補舊訊息，補內文不拖慢新文。

Discord 與 scraper API 都以假物件取代；不讀寫任何資料檔。
"""

import asyncio
import io
import os
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

import discord

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from services.relay.it_article_monitor import ItArticleMonitor  # noqa: E402

BOT_ID = 1
URL = "https://www.hkepc.com/26838/%E5%89%8D_EVGA_%E7%94%A2%E5%93%81"
INTRO = "【大哥 😭】「大哥」EVGA 於 2022 年 9 月正式宣布終止與晶片巨頭 NVIDIA 的合作關係"
CONTENT = INTRO + "……\n\n他指出，這場危機的種子早在 2016 年便已埋下。"


def _item(**over):
    base = {
        "hkepc_id": 26838, "title": "前 EVGA 產品經理首度公開內幕", "url": URL,
        "introduction": INTRO, "content": CONTENT, "images": [], "reference_url": None,
        "tags": "IT快訊", "published_at": "2026-09-30 00:00:00",
    }
    base.update(over)
    return base


class _Channel:
    """messages 由舊到新；history 照 discord.py 的規則：給了 after 時預設由舊到新，再套 limit。"""

    def __init__(self, messages, log=None):
        self.messages = messages
        self.log = log if log is not None else []
        self.history_kwargs = None
        self.send = mock.AsyncMock()

    def history(self, limit=100, after=None, oldest_first=None):
        self.history_kwargs = {"limit": limit, "after": after, "oldest_first": oldest_first}
        self.log.append("history")
        if oldest_first is None:
            oldest_first = after is not None
        ordered = list(self.messages) if oldest_first else list(reversed(self.messages))

        async def gen():
            for m in ordered[:limit]:
                yield m
        return gen()


def _message(monitor, item_as_sent, author_id=BOT_ID, msg_id=100, attachments=None):
    """照「當初發送時」的 item 排出 embed，模擬頻道裡那則訊息。"""
    return SimpleNamespace(
        id=msg_id,
        author=SimpleNamespace(id=author_id),
        embeds=[monitor.format_embed(item_as_sent)],
        attachments=list(attachments or []),
        edit=mock.AsyncMock(),
    )


def _monitor(channel):
    bot = SimpleNamespace(user=SimpleNamespace(id=BOT_ID), get_channel=lambda cid: channel)
    monitor = ItArticleMonitor(bot)
    monitor.SEND_INTERVAL = 0
    return monitor


def _intro_only(item):
    return {**item, "content": None, "reference_url": None, "images": []}


def _refresh(monitor, items):
    return asyncio.run(monitor.refresh_intro_only_messages([555], items))


class RefreshIntroOnlyTests(unittest.TestCase):

    def test_intro_only_message_is_edited_in_place_with_full_content(self):
        channel = _Channel([])
        monitor = _monitor(channel)
        msg = _message(monitor, _intro_only(_item()))
        channel.messages.append(msg)

        self.assertEqual(_refresh(monitor, [_item()]), 1)

        msg.edit.assert_awaited_once()
        embed = msg.edit.await_args.kwargs["embed"]
        self.assertIn("這場危機的種子", embed.description)
        self.assertEqual(embed.url, URL)
        channel.send.assert_not_awaited()

    def test_only_intro_only_messages_of_known_articles_are_touched(self):
        channel = _Channel([])
        monitor = _monitor(channel)
        full = _message(monitor, _item(), msg_id=1)                                  # 已經是完整內文
        stranger = _message(monitor, _intro_only(_item()), author_id=99, msg_id=2)   # 別人發的
        other = _message(monitor, _intro_only(_item(url="https://www.hkepc.com/1/x")), msg_id=3)  # 其他文章
        channel.messages.extend([full, stranger, other])

        self.assertEqual(_refresh(monitor, [_item()]), 0)
        for m in (full, stranger, other):
            m.edit.assert_not_awaited()

    def test_message_in_another_layout_is_left_alone(self):
        # 同一篇、但描述既不是摘要版也不是現在的完整版（例如排版規則以後改了）：寧可漏補，也不誤改
        channel = _Channel([])
        monitor = _monitor(channel)
        msg = _message(monitor, _intro_only(_item()))
        msg.embeds[0].description = "舊版排版：" + INTRO
        channel.messages.append(msg)

        self.assertEqual(_refresh(monitor, [_item()]), 0)
        msg.edit.assert_not_awaited()

    def test_nothing_changes_while_content_is_still_missing(self):
        channel = _Channel([])
        monitor = _monitor(channel)
        msg = _message(monitor, _intro_only(_item()))
        channel.messages.append(msg)

        self.assertEqual(_refresh(monitor, [_intro_only(_item())]), 0)
        msg.edit.assert_not_awaited()

    def test_url_encoding_differences_still_match(self):
        channel = _Channel([])
        monitor = _monitor(channel)
        msg = _message(monitor, _intro_only(_item(url="https://www.hkepc.com/26838/前_EVGA_產品")))
        channel.messages.append(msg)

        self.assertEqual(_refresh(monitor, [_item()]), 1)

    def test_title_change_on_the_site_still_matches_by_article_id(self):
        channel = _Channel([])
        monitor = _monitor(channel)
        msg = _message(monitor, _intro_only(_item(url="https://www.hkepc.com/26838/舊標題")))
        channel.messages.append(msg)

        self.assertEqual(_refresh(monitor, [_item(url="https://www.hkepc.com/26838/新標題")]), 1)

    def test_reads_the_newest_messages_first(self):
        channel = _Channel([])
        monitor = _monitor(channel)
        monitor.REFRESH_HISTORY_LIMIT = 1
        older = _message(monitor, _intro_only(_item(hkepc_id=1, url="https://www.hkepc.com/1/x")), msg_id=1)
        newest = _message(monitor, _intro_only(_item()), msg_id=2)
        channel.messages.extend([older, newest])

        self.assertEqual(_refresh(monitor, [_item()]), 1)
        newest.edit.assert_awaited_once()
        self.assertIs(channel.history_kwargs["oldest_first"], False)


class RefreshImageTests(unittest.TestCase):

    def _setup(self, attachments=None):
        channel = _Channel([])
        monitor = _monitor(channel)
        msg = _message(monitor, _intro_only(_item()), attachments=attachments)
        channel.messages.append(msg)
        return monitor, msg

    def _download(self, monitor):
        return mock.patch.object(monitor, "_download_image_as_file",
                                 new=mock.AsyncMock(return_value=(io.BytesIO(b"jpg"), "jpg")))

    def test_first_image_is_attached_and_existing_attachments_are_kept(self):
        existing = SimpleNamespace(filename="old.png")
        monitor, msg = self._setup(attachments=[existing])
        item = _item(images=["https://img.hkepc.com/a.jpg", "https://img.hkepc.com/b.jpg"])

        with self._download(monitor) as download:
            _refresh(monitor, [item])

        download.assert_awaited_once()
        self.assertEqual(download.await_args.args[0], "https://img.hkepc.com/a.jpg")
        kwargs = msg.edit.await_args.kwargs
        self.assertIs(kwargs["attachments"][0], existing)       # 列出的舊附件才會保留
        self.assertIsInstance(kwargs["attachments"][1], discord.File)
        self.assertTrue(kwargs["embed"].image.url.startswith("attachment://"))

    def test_falls_back_to_text_only_when_the_image_edit_fails(self):
        monitor, msg = self._setup()
        too_large = discord.HTTPException(SimpleNamespace(status=413, reason="Payload Too Large"), "too large")
        msg.edit.side_effect = [too_large, None]

        with self._download(monitor):
            updated = _refresh(monitor, [_item(images=["https://img.hkepc.com/a.jpg"])])

        self.assertEqual(updated, 1)
        self.assertEqual(msg.edit.await_count, 2)
        retry = msg.edit.await_args_list[1].kwargs
        self.assertNotIn("attachments", retry)
        self.assertIn("這場危機的種子", retry["embed"].description)
        self.assertIsNone(retry["embed"].image.url)

    def test_existing_image_is_referenced_by_attachment_not_expiring_url(self):
        att = SimpleNamespace(filename="pic.jpg")
        monitor, msg = self._setup(attachments=[att])
        msg.embeds[0].set_image(url="https://cdn.discordapp.com/attachments/1/2/pic.jpg?ex=abc&is=def&hm=123")

        _refresh(monitor, [_item()])

        kwargs = msg.edit.await_args.kwargs
        self.assertEqual(kwargs["embed"].image.url, "attachment://pic.jpg")
        self.assertEqual(kwargs["attachments"], [att])


class NotifyFlowTests(unittest.TestCase):

    def test_every_notify_checks_even_without_new_articles(self):
        channel = _Channel([])
        monitor = _monitor(channel)
        msg = _message(monitor, _intro_only(_item()))
        channel.messages.append(msg)

        with mock.patch.object(monitor, "fetch_recent_it_articles", new=mock.AsyncMock(return_value=[_item()])), \
             mock.patch.object(monitor, "is_content_sent", new=mock.AsyncMock(return_value=True)), \
             mock.patch.object(monitor, "send_to_channel", new=mock.AsyncMock()) as send:
            asyncio.run(monitor.check_and_send_new([555]))

        msg.edit.assert_awaited_once()
        send.assert_not_awaited()

    def test_new_articles_are_sent_before_old_messages_are_refreshed(self):
        log = []
        channel = _Channel([], log=log)
        monitor = _monitor(channel)
        new_item = _item(hkepc_id=26839, url="https://www.hkepc.com/26839/x")

        async def fake_send(channel_id, item):
            log.append("send")
            return True

        with mock.patch.object(monitor, "fetch_recent_it_articles", new=mock.AsyncMock(return_value=[_item(), new_item])), \
             mock.patch.object(monitor, "is_content_sent", new=mock.AsyncMock(side_effect=lambda t, i: i != 26839)), \
             mock.patch.object(monitor, "send_to_channel", new=mock.AsyncMock(side_effect=fake_send)):
            asyncio.run(monitor.check_and_send_new([555]))

        self.assertEqual(log, ["send", "history"])


if __name__ == "__main__":
    unittest.main()
