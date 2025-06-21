import logging
import discord
from discord.ext import commands
import json
import os

# 獲取 logger
logger = logging.getLogger('discord_bot')

class ForumMonitor(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.target_emoji = "✅"  # :white_check_mark: 的 Unicode 表示

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        """監控交易論壇頻道上的表情符號反應"""
        from utils import get_trade_forum_channel_id
        logger.debug("準備調用 get_trade_forum_channel_id 函數 (調用者: ForumMonitor)")
        forum_channel_id = await get_trade_forum_channel_id(config_file="config.json", caller="ForumMonitor")
        logger.debug(f"從 get_trade_forum_channel_id 函數返回的 forum_channel_id: {forum_channel_id} (調用者: ForumMonitor)")

        channel = self.bot.get_channel(payload.channel_id)
        if channel is None:
            logger.error(f"無法找到頻道 {payload.channel_id}")
            return

        # 檢查頻道是否為目標頻道或其線程
        is_target_channel = False
        if payload.channel_id == forum_channel_id:
            is_target_channel = True
            logger.debug(f"頻道 ID 匹配目標交易論壇頻道 ID: {forum_channel_id}")
        elif hasattr(channel, 'parent_id'):
            if channel.parent_id == forum_channel_id:
                is_target_channel = True
                logger.debug(f"頻道 ID {payload.channel_id} 是一個線程，其父頻道 ID 匹配目標交易論壇頻道 ID: {forum_channel_id}")
            else:
                logger.debug(f"頻道 ID {payload.channel_id} 是一個線程，但其父頻道 ID {channel.parent_id} 不匹配目標交易論壇頻道 ID: {forum_channel_id}")
        else:
            logger.debug(f"頻道 ID {payload.channel_id} 不是線程，且不匹配目標交易論壇頻道 ID: {forum_channel_id}")

        if not is_target_channel:
            logger.debug(f"頻道 ID 不匹配，忽略此事件。收到的事件頻道 ID: {payload.channel_id}，目標交易論壇頻道 ID: {forum_channel_id}")
            return  # 只處理交易論壇頻道或其線程中的反應，無需記錄日誌

        logger.debug(f"收到反應事件: 表情符號={str(payload.emoji)}, 頻道ID={payload.channel_id}, 訊息ID={payload.message_id}, 用戶ID={payload.user_id}")

        if str(payload.emoji) != self.target_emoji:
            logger.debug(f"忽略非目標表情符號: {str(payload.emoji)}")
            return  # 只處理指定的表情符號

        channel = self.bot.get_channel(payload.channel_id)
        if channel is None:
            logger.error(f"無法找到頻道 {payload.channel_id}")
            return

        try:
            message = await channel.fetch_message(payload.message_id)
            try:
                user = await self.bot.fetch_user(payload.user_id)
            except discord.NotFound:
                logger.error(f"無法找到用戶 {payload.user_id}")
                return
            except Exception as e:
                logger.error(f"獲取用戶 {payload.user_id} 時發生錯誤: {str(e)}")
                return

            logger.info(f"用戶 {user.name} 在交易論壇頻道對訊息 {message.id} 新增了 {self.target_emoji} 反應")
            # 可以在這裡添加通知或其他處理邏輯
            # 例如：通知特定用戶或頻道
            notification_channel_id = 1234567890  # 替換為實際的通知頻道 ID
            notification_channel = self.bot.get_channel(notification_channel_id)
            if notification_channel:
                await notification_channel.send(f"用戶 {user.mention} 對交易貼文 {message.jump_url} 新增了 {self.target_emoji} 反應")
            else:
                logger.warning(f"無法找到通知頻道 {notification_channel_id}")
        except Exception as e:
            logger.error(f"處理反應事件時發生錯誤: {str(e)}")

async def setup(bot):
    await bot.add_cog(ForumMonitor(bot))
