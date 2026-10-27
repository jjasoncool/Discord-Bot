"""取 thread 與取成員只有一份：utils.discord_threads.fetch_thread、utils.dm_notifier.resolve_member。

守的底線：
  1. fetch_thread：快取有就不打 API；封存的（不在快取）用 fetch 拿得到；不存在回 None；不是 thread 回 None。
     預設拿不到就回 None（顯示用途）；raise_errors=True 時沒權限與 5xx 往外丟——「找不到就清紀錄重建」的呼叫端
     （巴哈增量更新、社群查詢）要用它，Discord 抖一下才不會把紀錄清掉重開一串。
  2. resolve_member：快取有就不打 API；快取沒有再問 API；API 說不存在、沒權限、5xx 都回 None 不丟。
     resolve_user 也先走它（快取優先），不再先問 API。
  3. 巴哈、社群查詢用 raise_errors=True；PTT 改用 fetch_thread（封存串的新推文送得到）。
"""

import asyncio
import os
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import discord  # noqa: E402

from utils import dm_notifier  # noqa: E402
from utils.discord_threads import fetch_thread  # noqa: E402

SRC = os.path.dirname(HERE)


def _not_found():
    return discord.NotFound(mock.MagicMock(status=404), "unknown")


def _forbidden():
    return discord.Forbidden(mock.MagicMock(status=403), "no access")


def _server_error():
    return discord.HTTPException(mock.MagicMock(status=502), "bad gateway")


def _thread(tid=7):
    return SimpleNamespace(id=tid, archived=True)


def _client(cached=None, fetched=None):
    return SimpleNamespace(
        get_channel=lambda cid: cached,
        fetch_channel=mock.AsyncMock(side_effect=fetched) if isinstance(fetched, BaseException) else mock.AsyncMock(return_value=fetched),
    )


class FetchThreadTests(unittest.TestCase):
    def test_cached_thread_does_not_hit_the_api(self):
        client = _client(cached=_thread())
        self.assertIs(client.get_channel(7), asyncio.run(fetch_thread(client, 7)))
        client.fetch_channel.assert_not_awaited()

    def test_archived_thread_is_fetched(self):
        thread = _thread()
        client = _client(fetched=thread)
        self.assertIs(thread, asyncio.run(fetch_thread(client, 7)))
        client.fetch_channel.assert_awaited_once_with(7)

    def test_missing_thread_is_none_even_when_errors_are_raised(self):
        client = _client(fetched=_not_found())
        self.assertIsNone(asyncio.run(fetch_thread(client, 7, raise_errors=True)))
        self.assertIsNone(asyncio.run(fetch_thread(client, 7)))

    def test_text_channel_is_not_a_thread(self):
        client = _client(cached=SimpleNamespace(id=7, name="general"))
        self.assertIsNone(asyncio.run(fetch_thread(client, 7)))

    def test_server_error_is_swallowed_by_default_but_raised_on_request(self):
        client = _client(fetched=_server_error())
        with self.assertLogs("utils.discord_threads", level="WARNING"):
            self.assertIsNone(asyncio.run(fetch_thread(client, 7)))
        with self.assertRaises(discord.HTTPException):
            asyncio.run(fetch_thread(client, 7, raise_errors=True))
        with self.assertRaises(discord.Forbidden):
            asyncio.run(fetch_thread(_client(fetched=_forbidden()), 7, raise_errors=True))


class ResolveMemberTests(unittest.TestCase):
    def _guild(self, cached=None, fetched=None):
        fetch = mock.AsyncMock(side_effect=fetched) if isinstance(fetched, BaseException) else mock.AsyncMock(return_value=fetched)
        return SimpleNamespace(get_member=lambda uid: cached, fetch_member=fetch)

    def test_cached_member_does_not_hit_the_api(self):
        member = SimpleNamespace(id=5)
        guild = self._guild(cached=member)
        self.assertIs(member, asyncio.run(dm_notifier.resolve_member(guild, 5)))
        guild.fetch_member.assert_not_awaited()

    def test_cache_miss_asks_the_api(self):
        member = SimpleNamespace(id=5)
        guild = self._guild(fetched=member)
        self.assertIs(member, asyncio.run(dm_notifier.resolve_member(guild, "5")))
        guild.fetch_member.assert_awaited_once_with(5)

    def test_api_failures_mean_no_member_and_never_raise(self):
        for exc in (_not_found(), _forbidden(), _server_error()):
            with self.subTest(exc=type(exc).__name__):
                self.assertIsNone(asyncio.run(dm_notifier.resolve_member(self._guild(fetched=exc), 5)))
        self.assertIsNone(asyncio.run(dm_notifier.resolve_member(None, 5)))

    def test_resolve_user_prefers_the_member_cache(self):
        member = SimpleNamespace(id=5)
        guild = self._guild(cached=member)
        bot = SimpleNamespace(get_user=lambda uid: None, fetch_user=mock.AsyncMock())
        self.assertIs(member, asyncio.run(dm_notifier.resolve_user(bot, 5, guild=guild)))
        guild.fetch_member.assert_not_awaited()
        bot.fetch_user.assert_not_awaited()


class CallersTests(unittest.TestCase):
    """「找不到就重建」的兩處一定要 raise_errors=True；PTT 要走 fetch_thread。"""

    def _read(self, rel):
        with open(os.path.join(SRC, rel), encoding="utf-8") as fh:
            return fh.read()

    def test_rebuilders_raise_on_server_errors(self):
        for rel in ("services/relay/bahamut_monitor.py", "commands/community_lookup_commands.py"):
            self.assertIn("raise_errors=True", self._read(rel), rel)

    def test_ptt_fetches_archived_threads(self):
        self.assertIn("await fetch_thread(self.bot, thread_id)", self._read("services/relay/ptt_monitor.py"))


if __name__ == "__main__":
    unittest.main()
