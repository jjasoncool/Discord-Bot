import logging
import discord
from discord.ext import commands

# 獲取 logger
logger = logging.getLogger('discord_bot')

class ForumMonitor(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.target_emojis = ["✅", "🤝", "💰"]  # 監控的表情符號列表

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        """監控交易論壇頻道上的表情符號反應"""
        if str(payload.emoji) not in self.target_emojis:
            logger.debug(f"忽略非目標表情符號: {str(payload.emoji)}，目標表情符號列表: {self.target_emojis}")
            return  # 只處理指定的表情符號

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
            logger.debug(f"頻道 ID 不匹配，忽略此事件。收到的事件頻道 ID: {payload.channel_id}，目標交易論壇頻道 ID: {forum_channel_id}")
            return  # 只處理交易論壇頻道或其線程中的反應，無需記錄日誌

        logger.info(f"收到反應事件: 表情符號={str(payload.emoji)}, 頻道ID={payload.channel_id}, 訊息ID={payload.message_id}, 使用者ID={payload.user_id}")

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

            # 檢查使用者是否具有 Trader 角色
            guild = self.bot.get_guild(payload.guild_id)
            if guild is None:
                logger.error(f"無法找到伺服器 {payload.guild_id}")
                return

            member = guild.get_member(payload.user_id)
            if member is None:
                logger.error(f"無法找到伺服器中的使用者 {payload.user_id}")
                return

            # 使用 check_role 函數檢查角色權限
            from utils import check_role
            has_trader_role = await check_role(member, required_role="Trader")
            logger.info(f"使用者 {member.name} 是否具有 Trader 角色: {has_trader_role}")
            if not has_trader_role:
                logger.info(f"使用者 {member.name} 沒有 Trader 角色，忽略反應事件")
                return

            logger.info(f"使用者 {user.name} 在交易論壇頻道對訊息 {message.id} 新增了 {str(payload.emoji)} 反應")
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
                if str(source_thread_id) in thread.name and not thread.locked and not thread.archived:
                    existing_thread = thread
                    break

            class TransactionView(discord.ui.View):
                def __init__(self, bot):
                    super().__init__(timeout=None)  # 設置為 None 以永久有效
                    self.bot = bot

                async def extract_info_from_message(self, message_content):
                    """從訊息內容中提取 reacting_user_id 和 source_post_id"""
                    reacting_user_id = None
                    source_post_id = None

                    # 提取 reacting_user_id
                    try:
                        reacting_user_mention = message_content.split("使用者 ")[1].split(" 對交易貼文")[0]
                        reacting_user_id = int(reacting_user_mention.split("<@")[1].split(">")[0])
                    except (IndexError, ValueError) as e:
                        logger.error(f"無法從訊息中提取 reacting_user_id: {str(e)}")

                    # 提取 source_post_id
                    try:
                        source_post_id = message_content.split("來源貼文 ID:")[1].strip().split('\n')[0]
                        logger.info(f"提取來源貼文 ID: {source_post_id}")
                    except IndexError:
                        logger.error(f"無法從訊息中提取來源貼文 ID: {message_content}")

                    return reacting_user_id, source_post_id

                @discord.ui.button(label="買家領收", style=discord.ButtonStyle.green)
                async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                    message_content = interaction.message.content
                    reacting_user_id, source_post_id = await self.extract_info_from_message(message_content)

                    if reacting_user_id is None:
                        await interaction.response.send_message("無法識別使用者身份，請手動確認交易狀態。", ephemeral=True)
                        logger.error("無法識別使用者身份")
                        return

                    if interaction.user.id == reacting_user_id:
                        await interaction.response.send_message(f"{interaction.user.mention} 通知買家領收。", ephemeral=False)
                        # 調用 handle_trade_confirmation 流程
                        try:
                            from commands.trade_commands import TradeCommands
                            trade_cog = self.bot.get_cog('TradeCommands')
                            if trade_cog:
                                # 由於 handle_trade_confirmation 期望接收 message 對象而非 interaction
                                # 我們需要將 interaction.message 作為參數傳遞
                                if source_post_id:
                                    await trade_cog.handle_trade_confirmation(interaction.message, source_post_id)
                                else:
                                    await interaction.followup.send("無法從訊息中提取來源貼文 ID，請手動確認交易狀態。", ephemeral=True)
                                    logger.error("無法從訊息中提取來源貼文 ID")
                            else:
                                await interaction.followup.send("無法找到交易命令模組，請稍後再試。", ephemeral=True)
                                logger.error("無法找到交易命令模組 'TradeCommands'")
                        except Exception as e:
                            error_message = f"調用交易確認流程時發生錯誤: {str(e)}，請截圖通知管理員。"
                            await interaction.followup.send(error_message, ephemeral=True)
                            logger.error(error_message, exc_info=True)
                    else:
                        await interaction.response.send_message("只有賣家可以進行此操作。", ephemeral=True)

                @discord.ui.button(label="取消交易", style=discord.ButtonStyle.red)
                async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                    message_content = interaction.message.content
                    reacting_user_id, source_post_id = await self.extract_info_from_message(message_content)

                    if reacting_user_id is None:
                        await interaction.response.send_message("無法識別使用者身份，請手動確認交易狀態。", ephemeral=True)
                        logger.error("無法識別使用者身份")
                        return

                    if interaction.user.id == reacting_user_id:
                        for item in self.children:
                            item.disabled = True
                        await interaction.message.edit(view=self)

                        # 調用 cancel_trade_cmd 流程
                        try:
                            from commands.trade_commands import TradeCommands
                            trade_cog = self.bot.get_cog('TradeCommands')
                            if trade_cog:
                                await interaction.response.send_message(f"{interaction.user.mention} 已取消交易。", ephemeral=False)
                                await trade_cog.cancel_trade_cmd(interaction)
                            else:
                                await interaction.response.send_message("無法找到交易命令模組，請稍後再試。", ephemeral=True)
                                logger.error("無法找到交易命令模組 'TradeCommands'")
                        except Exception as e:
                            error_message = f"調用取消交易流程時發生錯誤: {str(e)}，請截圖通知管理員。"
                            await interaction.response.send_message(error_message, ephemeral=True)
                            logger.error(error_message, exc_info=True)
                    else:
                        await interaction.response.send_message("只有賣家可以進行此操作。", ephemeral=True)

            if existing_thread:
                await existing_thread.send(
                    f"提醒：使用者 {reacting_user.mention} 對交易貼文 {message.jump_url} 有興趣\n"
                    f"貼文者為 {post_author.mention}\n"
                    f"來源貼文 ID: {source_thread_id}\n"
                    f"請在這裡確認交易細節。",
                    view=TransactionView(self.bot)
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
                    # 獲取 reacting_user 的價格資訊
                    from commands.user_commands import UserCommands
                    user_cog = self.bot.get_cog('UserCommands')
                    if user_cog:
                        user_prices = await user_cog.get_user_item_prices(reacting_user.id)
                        if user_prices:
                            price_embed = discord.Embed(
                                title=f"{reacting_user.display_name} 的物品價格",
                                description="以下是對方設定的物品價格資訊：",
                                color=discord.Color.blue()
                            )
                            has_price = False
                            for item_value, details in user_prices.items():
                                price = details['price']
                                if price != "無價格設定":
                                    price_embed.add_field(
                                        name=f"{details['label']} ({details['description']})",
                                        value=f"價格: {price}",
                                        inline=False
                                    )
                                    has_price = True
                            if not has_price:
                                price_embed.description = "對方未設定任何物品價格。"
                        else:
                            price_embed = discord.Embed(
                                title=f"{reacting_user.display_name} 的物品價格",
                                description="對方未設定任何物品價格。",
                                color=discord.Color.blue()
                            )
                    else:
                        price_embed = discord.Embed(
                            title="無法獲取物品價格",
                            description="無法獲取對方的物品價格資訊。",
                            color=discord.Color.red()
                        )

                    await thread.send(
                        f"使用者 {reacting_user.mention} 對交易貼文 {message.jump_url} 有興趣\n"
                        f"貼文者為 {post_author.mention}\n"
                        f"來源貼文 ID: {source_thread_id}\n"
                        f"請在這裡確認交易細節。",
                        view=TransactionView(self.bot)
                    )
                    await thread.send(embed=price_embed)
                    logger.info(f"已在頻道 {delivery_channel.name} 中為交易創建私有 thread: {thread_name}，來源貼文 ID: {source_thread_id}")
                except Exception as e:
                    logger.error(f"創建私有 thread 時發生錯誤: {str(e)}")
        else:
            logger.error(f"無法找到購物車交付頻道 {delivery_channel_id}")

async def setup(bot):
    await bot.add_cog(ForumMonitor(bot))
