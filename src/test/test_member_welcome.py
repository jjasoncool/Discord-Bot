"""新成員歡迎訊息：文案組裝與發送條件。

守的是「接手 ProBot」這件事的三個底線：
- 文案照原本格式，規則頻道沒設時不留下半句話
- bot 帳號、未綁歡迎頻道、頻道不在本伺服器時都不發
- 只允許 @ 到新成員本人，不會被伺服器名稱等內容帶出 @everyone

執行：
    cd src && python -m unittest test.test_member_welcome -v
"""

import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

import discord

from services.community.member_welcome import build_welcome_text, send_welcome
from utils.utils import ChannelConfig

WELCOME_ID = 111
GUILD_NAME = "漂泊者觀星台 - WutheringWaves"


class BuildWelcomeTextTests(unittest.TestCase):
    def test_with_rules_channel(self):
        text = build_welcome_text("<@1>", GUILD_NAME, "<#2>")
        self.assertEqual(
            text,
            "歡迎 漂泊者 <@1> 加入 漂泊者觀星台 - WutheringWaves，與我們分享你的故事吧"
            "\n\n請到 <#2> 查看規定並領取身份後開始聊天",
        )

    def test_without_rules_channel_drops_guide_line(self):
        text = build_welcome_text("<@1>", GUILD_NAME, None)
        self.assertNotIn("請到", text)
        self.assertNotIn("None", text)


def _member(*, bot=False, channel=None, rules=True):
    member = MagicMock()
    member.bot = bot
    member.id = 1
    member.mention = "<@1>"
    member.guild.name = GUILD_NAME
    member.guild.get_channel.return_value = channel
    member.guild.rules_channel = MagicMock(mention="<#2>") if rules else None
    return member


def _text_channel():
    channel = MagicMock(spec=discord.TextChannel)
    channel.send = AsyncMock()
    return channel


class SendWelcomeTests(unittest.IsolatedAsyncioTestCase):
    def _patch_channel_id(self, value):
        return patch.object(ChannelConfig, "get_channel_id", AsyncMock(return_value=value))

    async def test_sends_to_welcome_channel(self):
        channel = _text_channel()
        member = _member(channel=channel)
        with self._patch_channel_id(WELCOME_ID):
            await send_welcome(member)
        member.guild.get_channel.assert_called_once_with(WELCOME_ID)
        channel.send.assert_awaited_once()
        text = channel.send.await_args.args[0]
        self.assertIn("<@1>", text)
        self.assertIn("<#2>", text)
        mentions = channel.send.await_args.kwargs["allowed_mentions"]
        self.assertFalse(mentions.everyone)
        self.assertFalse(mentions.roles)
        self.assertEqual(mentions.users, [member])

    async def test_skips_bot_accounts(self):
        channel = _text_channel()
        with self._patch_channel_id(WELCOME_ID):
            await send_welcome(_member(bot=True, channel=channel))
        channel.send.assert_not_awaited()

    async def test_silent_when_channel_not_configured(self):
        member = _member(channel=_text_channel())
        with self._patch_channel_id(ChannelConfig.DEFAULT_ID):
            await send_welcome(member)
        member.guild.get_channel.assert_not_called()

    async def test_skips_when_channel_not_in_guild(self):
        with self._patch_channel_id(WELCOME_ID):
            await send_welcome(_member(channel=None))  # 不應拋例外

    async def test_skips_non_text_channel(self):
        voice = MagicMock(spec=discord.VoiceChannel)
        voice.send = AsyncMock()
        with self._patch_channel_id(WELCOME_ID):
            await send_welcome(_member(channel=voice))
        voice.send.assert_not_awaited()

    async def test_send_failure_is_swallowed(self):
        channel = _text_channel()
        channel.send.side_effect = discord.HTTPException(MagicMock(status=403), "Missing Permissions")
        with self._patch_channel_id(WELCOME_ID):
            await send_welcome(_member(channel=channel))  # 不應拋例外


if __name__ == "__main__":
    unittest.main()
