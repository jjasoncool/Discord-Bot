"""共用發文接口 utils.discord_content.post_to_channel。

守的底線：
  1. 呼叫端給的按鈕（view）與提及設定（allowed_mentions）一定帶到第一則：論壇開新貼文、文字頻道直接發都一樣。
     封存轉貼別人的對話時靠 allowed_mentions 才不會又通知一次。
  2. 帶附件的第一則發不出去時退成純文字重發，按鈕與提及設定照樣帶著，附件改在後面補送。
"""

import asyncio
import io
import os
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import discord  # noqa: E402

from utils import discord_content  # noqa: E402


def _file(name="a.txt"):
    return discord.File(io.BytesIO(b"x"), filename=name)


class PostToChannelTests(unittest.TestCase):

    def setUp(self):
        self.quiet = discord.AllowedMentions.none()
        self.view = object()
        sleep = mock.patch.object(discord_content.asyncio, "sleep", new=mock.AsyncMock())
        sleep.start()
        self.addCleanup(sleep.stop)

    def post(self, channel, **kwargs):
        return asyncio.run(discord_content.post_to_channel(channel, **kwargs))

    def test_forum_post_carries_view_and_mentions(self):
        starter = SimpleNamespace(channel=mock.AsyncMock())
        forum = mock.MagicMock(spec=discord.ForumChannel)
        forum.create_thread = mock.AsyncMock(return_value=SimpleNamespace(message=starter))

        result = self.post(forum, content="內容", thread_title="標題", view=self.view, allowed_mentions=self.quiet)

        self.assertIs(result, starter)
        sent = forum.create_thread.await_args.kwargs
        self.assertIs(sent["view"], self.view)
        self.assertIs(sent["allowed_mentions"], self.quiet)

    def test_text_channel_send_carries_mentions(self):
        channel = mock.MagicMock(spec=discord.TextChannel)
        channel.send = mock.AsyncMock(return_value=SimpleNamespace(channel=channel))

        self.post(channel, content="內容", allowed_mentions=self.quiet)

        self.assertIs(channel.send.await_args.kwargs["allowed_mentions"], self.quiet)

    def test_fallback_without_files_keeps_view_and_mentions(self):
        thread = mock.AsyncMock()
        channel = mock.MagicMock(spec=discord.TextChannel)
        failed = discord.HTTPException(mock.MagicMock(status=413), "too large")
        channel.send = mock.AsyncMock(side_effect=[failed, SimpleNamespace(channel=thread)])

        self.post(channel, content="內容", files=[_file()], view=self.view, allowed_mentions=self.quiet)

        retry = channel.send.await_args_list[1].kwargs
        self.assertNotIn("files", retry)
        self.assertIs(retry["view"], self.view)
        self.assertIs(retry["allowed_mentions"], self.quiet)
        self.assertEqual(len(thread.send.await_args.kwargs["files"]), 1)  # 附件改在後面補送


if __name__ == "__main__":
    unittest.main()
