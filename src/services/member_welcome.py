"""新成員加入歡迎訊息（接手原本 ProBot 的工作）。

觸發點在 discord_bot.py 的 on_member_join；這裡只管「組文案 + 發到歡迎頻道」。
歡迎頻道由 /server_manager 綁定（welcome_channel_id），未設定則整個功能靜默。
規範頻道連結取 Discord 內建的 guild.rules_channel（社群伺服器設定），不另開 config key。
"""
from __future__ import annotations

import logging
from typing import Optional

import discord

from utils.utils import ChannelConfig

logger = logging.getLogger(__name__)

WELCOME_CHANNEL_KEY = "welcome_channel_id"


def build_welcome_text(member_mention: str, guild_name: str, rules_mention: Optional[str]) -> str:
    """組歡迎文案；伺服器沒設規則頻道時省略引導那一行。"""
    text = f"歡迎 漂泊者 {member_mention} 加入 {guild_name}，與我們分享你的故事吧"
    if rules_mention:
        text += f"\n\n請到 {rules_mention} 查看規定並領取身份後開始聊天"
    return text


async def send_welcome(member: discord.Member) -> None:
    """在歡迎頻道發歡迎訊息；bot 帳號、未綁頻道、頻道失效都靜默略過。"""
    if member.bot:
        return

    channel_id = await ChannelConfig.get_channel_id(WELCOME_CHANNEL_KEY, caller="member_welcome")
    if channel_id == ChannelConfig.DEFAULT_ID:
        return

    channel = member.guild.get_channel(int(channel_id))
    if channel is None:
        # 可能是 bot 所在的其他伺服器（歡迎頻道不屬於它），不算錯誤
        logger.debug("歡迎頻道 %s 不在伺服器 %s，略過", channel_id, member.guild.id)
        return
    if not isinstance(channel, discord.TextChannel):
        logger.warning("歡迎頻道 %s 不是文字頻道，略過", channel_id)
        return

    rules = member.guild.rules_channel
    text = build_welcome_text(member.mention, member.guild.name, rules.mention if rules else None)
    try:
        # 只允許 @ 到新成員本人，避免伺服器名稱等內容誤觸 @everyone / 身份組
        await channel.send(text, allowed_mentions=discord.AllowedMentions(everyone=False, roles=False, users=[member]))
        logger.info("已發送歡迎訊息：%s (%s)", member.display_name, member.id)
    except discord.HTTPException as e:
        logger.warning("發送歡迎訊息失敗 (member=%s): %s", member.id, e)
