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
        logger.info(f"獲取到交易論壇頻道 ID: {forum_channel_id}")

        channel = self.bot.get_channel(payload.channel_id)
        if channel is None:
            logger.error(f"無法找到頻道 {payload.channel_id}")
            return

        # 檢查頻道是否為目標頻道或其線程
        is_target_channel = False
        if payload.channel_id == forum_channel_id:
            is_target_channel = True
            logger.info(f"頻道 ID 匹配目標交易論壇頻道 ID: {forum_channel_id}")
        elif hasattr(channel, 'parent_id'):
            if channel.parent_id == forum_channel_id:
                is_target_channel = True
                logger.info(f"頻道 ID {payload.channel_id} 是一個線程，其父頻道 ID 匹配目標交易論壇頻道 ID: {forum_channel_id}")
            else:
                logger.debug(f"頻道 ID {payload.channel_id} 是一個線程，但其父頻道 ID {channel.parent_id} 不匹配目標交易論壇頻道 ID: {forum_channel_id}")
        else:
            logger.debug(f"頻道 ID {payload.channel_id} 不是線程，且不匹配目標交易論壇頻道 ID: {forum_channel_id}")

        if not is_target_channel:
            logger.info(f"頻道 ID 不匹配，忽略此事件。收到的事件頻道 ID: {payload.channel_id}，目標交易論壇頻道 ID: {forum_channel_id}")
            return  # 只處理交易論壇頻道或其線程中的反應，無需記錄日誌

        logger.info(f"收到反應事件: 表情符號={str(payload.emoji)}, 頻道ID={payload.channel_id}, 訊息ID={payload.message_id}, 使用者ID={payload.user_id}")

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
                logger.error(f"無法找到使用者 {payload.user_id}")
                return
            except Exception as e:
                logger.error(f"獲取使用者 {payload.user_id} 時發生錯誤: {str(e)}")
                return

            logger.info(f"使用者 {user.name} 在交易論壇頻道對訊息 {message.id} 新增了 {self.target_emoji} 反應")
            await self.send_cart_delivery_notification(message, user)
        except Exception as e:
            logger.error(f"處理反應事件時發生錯誤: {str(e)}")

    async def send_cart_delivery_notification(self, message, reacting_user):
        """發送購物車交付通知到指定頻道"""
        from utils import get_cart_delivery_channel_id
        logger.debug("準備調用 get_cart_delivery_channel_id 函數 (調用者: ForumMonitor)")
        delivery_channel_id = await get_cart_delivery_channel_id(config_file="config.json", caller="ForumMonitor")
        logger.info(f"獲取到購物車交付頻道 ID: {delivery_channel_id}")

        delivery_channel = self.bot.get_channel(delivery_channel_id)
        if delivery_channel:
            # 獲取貼文者 (必須是本機器人，並從第一句內容中抓取被提及的人)
            post_author = None
            if message.author == self.bot.user:
                content_lines = message.content.split('\n')
                if content_lines:
                    first_line = content_lines[0]
                    for mention in message.mentions:
                        if mention.id != reacting_user.id:
                            post_author = mention
                            break
                    if not post_author and message.mentions:
                        post_author = message.mentions[0]
            else:
                logger.info(f"訊息作者不是本機器人，忽略此反應事件。訊息作者: {message.author.name}")
                return

            if not post_author:
                logger.error("無法確定貼文者，忽略此反應事件")
                return

            # 檢查是否已經為此貼文創建過 thread
            source_thread_id = message.channel.id if hasattr(message.channel, 'parent_id') else message.channel.id
            thread_name = f"交易確認 - {post_author.name} 和 {reacting_user.name} - {source_thread_id}"

            # 檢查是否已存在具有相同來源貼文 ID 的 thread
            existing_thread = None
            for thread in delivery_channel.threads:
                if str(source_thread_id) in thread.name:
                    existing_thread = thread
                    break

            if existing_thread:
                await existing_thread.send(
                    f"提醒：使用者 {reacting_user.mention} 對交易貼文 {message.jump_url} 有興趣\n"
                    f"貼文者為 {post_author.mention}\n"
                    f"來源貼文 ID: {source_thread_id}\n"
                    f"請在這裡確認交易細節。"
                )
                logger.info(f"已在現有 thread {existing_thread.name} 中重新發送通知，來源貼文 ID: {source_thread_id}")
            else:
                try:
                    thread = await delivery_channel.create_thread(
                        name=thread_name,
                        type=discord.ChannelType.private_thread,
                        reason=f"為使用者 {post_author.name} 和 {reacting_user.name} 創建交易確認 thread，來源貼文 ID: {source_thread_id}",
                        invitable=False  # 設置為 False 以關閉任何人可以邀請的選項
                    )
                    # 在創建後將使用者加入 thread
                    await thread.add_user(post_author)
                    await thread.add_user(reacting_user)
                    await thread.send(
                        f"使用者 {reacting_user.mention} 對交易貼文 {message.jump_url} 有興趣\n"
                        f"貼文者為 {post_author.mention}\n"
                        f"來源貼文 ID: {source_thread_id}\n"
                        f"請在這裡確認交易細節。"
                    )
                    logger.info(f"已在頻道 {delivery_channel.name} 中為交易創建私有 thread: {thread_name}，來源貼文 ID: {source_thread_id}")
                except Exception as e:
                    logger.error(f"創建私有 thread 時發生錯誤: {str(e)}")
        else:
            logger.error(f"無法找到購物車交付頻道 {delivery_channel_id}")

async def setup(bot):
    await bot.add_cog(ForumMonitor(bot))
