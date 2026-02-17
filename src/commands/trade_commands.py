import logging
import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import traceback
# 從 constants.py 導入物品選項配置
from constants import ITEMS
from utils.utils import safe_send_interaction_message

# 獲取 logger
logger = logging.getLogger('discord_bot')

class TradeCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot


    @app_commands.command(name="trade_info", description="查詢交易相關資訊")
    async def trade_info_cmd(self, interaction: discord.Interaction):
        """斜線命令：提供交易相關資訊"""
        logger.info(f'收到來自 {interaction.user} 的 /trade_info 斜線命令')

        from utils.utils import check_guild
        if not await check_guild(interaction, required_role="Trader"):
            return

        embed = discord.Embed(
            title="交易資訊",
            description="這是一個交易資訊頁面，您可以在這裡查看交易相關的資訊。",
            color=discord.Color.gold()
        )

        embed.add_field(
            name="使用頻道監控功能",
            value="您可以使用 `/monitor_channel` 命令來監控特定頻道中的訊息，"
                  "當有特定關鍵字出現時，機器人會通知您。\n"
                  "相關命令已移至 Management 模組。",
            inline=False
        )

        embed.add_field(
            name="交易指令",
            value="將在未來版本中加入更多交易相關功能。",
            inline=False
        )

        await safe_send_interaction_message(interaction, embed=embed, ephemeral=True)


    async def cancel_trade_cmd(self, interaction: discord.Interaction):
        """斜線命令：取消當前交易並鎖定 thread"""
        logger.info(f'收到來自 {interaction.user} 的 /cancel_trade 斜線命令')

        # 延遲回應以避免交互被提前回應
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)

        if interaction.channel.type != discord.ChannelType.private_thread:
            await safe_send_interaction_message(interaction, "此命令只能在私人 thread 中使用。", ephemeral=True)
            return

        thread = interaction.channel
        logger.info(f"開始處理交易取消，thread 名稱: {thread.name}，來自使用者: {interaction.user.name}")

        # 從機器人發送的訊息中提取來源貼文 ID 和相關使用者
        source_post_id = None
        reacting_user = None
        async for msg in thread.history(limit=10, oldest_first=True):
            if msg.author == self.bot.user and msg.content:
                content_lines = msg.content.split('\n')
                for line in content_lines:
                    if "來源貼文 ID:" in line:
                        try:
                            source_post_id = line.split("來源貼文 ID:")[1].strip()
                            logger.info(f"提取來源貼文 ID: {source_post_id}")
                        except IndexError:
                            logger.error(f"無法從行中提取來源貼文 ID: {line}")
                    elif "對交易貼文" in line and "有興趣" in line:
                        reacting_user_mention = line.split("對交易貼文")[0].replace("使用者", "").strip()
                        try:
                            user_id = int(reacting_user_mention.split("<@")[1].split(">")[0])
                            reacting_user = await self.bot.fetch_user(user_id)
                            logger.info(f"提取反應使用者: {reacting_user_mention}")
                        except (IndexError, ValueError, discord.NotFound):
                            logger.error(f"無法從提及中提取使用者 ID 或找到使用者: {reacting_user_mention}")
                if source_post_id and reacting_user:
                    break

        logger.info(f"提取結果 - 來源貼文 ID: {source_post_id}, 反應使用者: {reacting_user.name if reacting_user else '未找到'}")

        if not source_post_id or not reacting_user:
            logger.error("無法從訊息中提取來源貼文 ID 或反應使用者")
            await safe_send_interaction_message(interaction, "無法識別此交易 thread 的來源貼文或相關使用者，請手動處理。", ephemeral=True)
            return

        # 鎖定當前 thread
        await thread.edit(locked=True, archived=True)
        logger.info(f"已鎖定並封存 thread {thread.name}，ID: {thread.id}")

        # 清除來源貼文中的反應
        from utils.utils import get_trade_forum_channel_id
        try:
            forum_channel_id = await get_trade_forum_channel_id(config_file="config.json", caller="TradeCommands")
            logger.info(f"獲取到交易論壇頻道 ID: {forum_channel_id}")
        except Exception as e:
            logger.error(f"調用 get_trade_forum_channel_id 時發生錯誤: {str(e)}")
            await thread.send("無法獲取交易論壇頻道 ID，請手動確認交易狀態。")
            return

        forum_channel = self.bot.get_channel(forum_channel_id)
        if not forum_channel:
            logger.error(f"無法找到交易論壇頻道 {forum_channel_id}")
            await thread.send("無法找到交易論壇頻道，請手動確認交易狀態。")
            return

        source_message = None
        try:
            if forum_channel.type == discord.ChannelType.forum:
                source_thread = forum_channel.get_thread(int(source_post_id))
                if not source_thread:
                    source_thread = await forum_channel.fetch_channel(int(source_post_id))
                if source_thread:
                    async for msg in source_thread.history(limit=1, oldest_first=True):
                        source_message = msg
                        break
                else:
                    logger.error(f"無法找到來源 thread {source_post_id}")
                    await thread.send("無法找到來源 thread，請手動確認交易狀態。")
                    return
            else:
                source_message = await forum_channel.fetch_message(int(source_post_id))
        except discord.NotFound:
            logger.error(f"無法找到來源貼文 {source_post_id}")
            await thread.send("無法找到來源貼文，請手動確認交易狀態。")
            return
        except Exception as e:
            logger.error(f"獲取來源貼文 {source_post_id} 時發生錯誤: {str(e)}")
            await thread.send("獲取來源貼文時發生錯誤，請手動確認交易狀態。")
            return

        # 清除反應
        target_emojis = ["✅", "🤝", "💰"]  # 與交易相關的表情符號列表
        for reaction in source_message.reactions:
            if str(reaction.emoji) in target_emojis:
                async for user in reaction.users():
                    if user == reacting_user:
                        await source_message.remove_reaction(reaction.emoji, user)
                        logger.info(f"已清除使用者 {reacting_user.name} 在來源貼文 {source_post_id} 上的反應 {reaction.emoji}")
                        break

        await safe_send_interaction_message(interaction, "交易已取消，此 thread 已鎖定，來源貼文的反應已清除。", ephemeral=True)
        await thread.send(f"交易已被 {interaction.user.mention} 取消。此 thread 已鎖定，來源貼文的反應已清除。")


    async def handle_trade_confirmation(self, message, source_post_id):
        """處理交易確認請求"""
        from utils.utils import get_trade_forum_channel_id
        thread = message.channel
        thread_name = thread.name

        logger.info(f"開始處理交易確認，thread 名稱: {thread_name}，來自使用者: {message.author.name}")
        # 使用提供的來源貼文 ID
        source_thread_id = int(source_post_id)
        logger.info(f"使用提供的來源貼文 ID: {source_thread_id}")

        # 獲取交易論壇頻道 ID
        logger.debug("準備調用 get_trade_forum_channel_id 函數 (調用者: TradeCommands)")
        try:
            forum_channel_id = await get_trade_forum_channel_id(config_file="config.json", caller="TradeCommands")
            logger.info(f"獲取到交易論壇頻道 ID: {forum_channel_id}")
        except Exception as e:
            logger.error(f"調用 get_trade_forum_channel_id 時發生錯誤: {str(e)}")
            await thread.send("無法獲取交易論壇頻道 ID，請手動確認交易狀態。")
            return

        # 獲取來源貼文
        forum_channel = self.bot.get_channel(forum_channel_id)
        if not forum_channel:
            logger.error(f"無法找到交易論壇頻道 {forum_channel_id}")
            await thread.send("無法找到交易論壇頻道，請手動確認交易狀態。")
            return

        source_message = None
        try:
            if forum_channel.type == discord.ChannelType.forum:
                # 直接通過 ID 獲取 thread
                source_thread = forum_channel.get_thread(source_thread_id)
                if not source_thread:
                    # 如果 get_thread 無法找到，嘗試 fetch_channel
                    source_thread = await forum_channel.fetch_channel(source_thread_id)
                if source_thread:
                    # 獲取 thread 的第一條訊息作為來源貼文
                    async for msg in source_thread.history(limit=1, oldest_first=True):
                        source_message = msg
                        break
                else:
                    logger.error(f"無法找到來源 thread {source_thread_id}")
                    await thread.send("無法找到來源 thread，請手動確認交易狀態。")
                    return
            else:
                source_message = await forum_channel.fetch_message(source_thread_id)
        except discord.NotFound:
            logger.error(f"無法找到來源貼文 {source_thread_id}")
            await thread.send("無法找到來源貼文，請手動確認交易狀態。")
            return
        except Exception as e:
            logger.error(f"獲取來源貼文 {source_thread_id} 時發生錯誤: {str(e)}")
            await thread.send("獲取來源貼文時發生錯誤，請手動確認交易狀態。")
            return

        # 獲取貼文者 (必須是本機器人，並從第一句內容中抓取被提及的人)
        post_author = None
        if source_message.author == self.bot.user:
            content_lines = source_message.content.split('\n')
            if content_lines:
                first_line = content_lines[0]
                for mention in source_message.mentions:
                    if mention.id != message.author.id:
                        post_author = mention
                        break
                if not post_author and source_message.mentions:
                    post_author = source_message.mentions[0]
        else:
            logger.info(f"來源貼文作者不是本機器人，忽略此交易確認請求。訊息作者: {source_message.author.name}")
            await thread.send("來源貼文作者不是本機器人，無法處理交易確認。")
            return

        if not post_author:
            logger.error("無法確定貼文者，忽略此交易確認請求")
            await thread.send("無法確定貼文者，無法處理交易確認。")
            return

        # 發送確認對話給買家
        confirmation_message = await thread.send(
            f"{post_author.mention}，賣家已確認交易完成，請點選下面的 ✅ 反應來確認您已收到商品或服務。確認後，此 thread 及來源貼文將被鎖定。"
        )
        await confirmation_message.add_reaction("✅")

        logger.info(f"已發送交易確認對話給買家 {post_author.name}，thread ID: {thread.id}")

        # 監控買家的確認反應
        def check(reaction, user):
            return user == post_author and str(reaction.emoji) == "✅" and reaction.message.id == confirmation_message.id

        try:
            reaction, user = await self.bot.wait_for('reaction_add', timeout=86400.0, check=check)  # 等待24小時
            logger.info(f"收到買家 {user.name} 的交易確認反應")

            # 鎖定並封存 thread
            await thread.edit(locked=True, archived=True)
            logger.info(f"已鎖定並封存 thread {thread.name}，ID: {thread.id}")

            # 將來源貼文內容複製到 archive 頻道並刪除來源貼文
            await self.archive_source_message(thread, source_message)

            await thread.send(f"交易已由雙方確認完成。此 thread 及來源貼文已被鎖定。")
        except asyncio.TimeoutError:
            logger.warning(f"交易確認超時，買家 {post_author.name} 未在24小時內確認")
            await thread.send(f"{post_author.mention}，您未在24小時內確認交易，交易已自動確認領收。")
            # 自動確認領收，鎖定並封存 thread
            await thread.edit(locked=True, archived=True)
            logger.info(f"已因超時自動鎖定並封存 thread {thread.name}，ID: {thread.id}")
            # 將來源貼文內容複製到 archive 頻道並刪除來源貼文
            await self.archive_source_message(thread, source_message)
            await thread.send(f"交易已自動確認完成。此 thread 及來源貼文已被鎖定。")
        except Exception as e:
            logger.error(f"處理交易確認反應時發生錯誤: {str(e)}")
            await thread.send("處理交易確認時發生錯誤，請手動確認交易狀態。")

    async def archive_source_message(self, thread, source_message):
        """將來源貼文內容複製到 archive 頻道並刪除來源貼文"""
        from utils.utils import get_archive_channel_id
        try:
            archive_channel_id = await get_archive_channel_id(config_file="config.json", caller="TradeCommands")
            archive_channel = self.bot.get_channel(archive_channel_id)
            if archive_channel:
                if isinstance(archive_channel, discord.ForumChannel):
                    # 如果是論壇頻道，創建一個新的 thread
                    thread_title = f"已封存 - {source_message.channel.name if isinstance(source_message.channel, discord.Thread) else '貼文'} {source_message.id}"
                    # 獲取 thread 中的所有訊息，按時間順序排列
                    conversation_history = []
                    async for msg in source_message.channel.history(limit=100, oldest_first=True):
                        conversation_history.append(f"{msg.author.name}: {msg.content}")

                    thread_content = f"已封存的來源貼文 {source_message.id} 對話內容：\n" + "\n".join(conversation_history)
                    applied_tags = []
                    for tag in archive_channel.available_tags:
                        if tag.name == "封存":
                            applied_tags.append(tag)
                            break
                    if not applied_tags:
                        try:
                            new_tag = await archive_channel.create_tag(name="封存")
                            applied_tags.append(new_tag)
                            logger.info(f"已創建新標籤「封存」並應用到貼文")
                        except Exception as tag_error:
                            logger.error(f"創建新標籤「封存」時發生錯誤: {str(tag_error)}")
                    archived_thread = await archive_channel.create_thread(name=thread_title, content=thread_content, applied_tags=applied_tags)
                    logger.info(f"已將來源貼文 {source_message.id} 複製到 archive 頻道 {archive_channel_id} 的新 thread 中，使用標籤: {applied_tags if applied_tags else '無'}")
                else:
                    # 如果是文字頻道，直接發送訊息
                    # 獲取 thread 中的所有訊息，按時間順序排列
                    conversation_history = []
                    async for msg in source_message.channel.history(limit=100, oldest_first=True):
                        conversation_history.append(f"{msg.author.name}: {msg.content}")

                    archived_message = await archive_channel.send(f"已封存的來源貼文 {source_message.id} 對話內容：\n" + "\n".join(conversation_history))
                    logger.info(f"已將來源貼文 {source_message.id} 複製到 archive 頻道 {archive_channel_id}")
                # 刪除來源貼文
                if isinstance(source_message.channel, discord.Thread) and isinstance(source_message.channel.parent, discord.ForumChannel):
                    # 如果來源訊息在論壇 thread 中，刪除整個 thread
                    await source_message.channel.delete()
                    logger.info(f"已刪除來源貼文 {source_message.id} 的整個 thread")
                else:
                    # 否則只刪除訊息
                    await source_message.delete()
                    logger.info(f"已刪除來源貼文 {source_message.id}")
            else:
                logger.error(f"無法找到 archive 頻道 {archive_channel_id}")
                await thread.send("無法找到 archive 頻道，來源貼文將被鎖定並關閉。")
                await source_message.channel.edit(locked=True, archived=True)
                logger.info(f"已因無法找到 archive 頻道而鎖定並關閉來源貼文 {source_message.id} 的頻道")
        except Exception as e:
            logger.error(f"處理來源貼文封存時發生錯誤: {str(e)}", exc_info=True)
            await thread.send("處理來源貼文封存時發生錯誤，來源貼文未被處理。詳細錯誤已記錄，請通知管理員處理。")
            logger.info(f"已因錯誤而無法處理來源貼文 {source_message.id}，詳細錯誤訊息已記錄")

    @app_commands.command(name="set_item_prices", description="設定物品價格（賣家專用）")
    async def set_item_prices_cmd(self, interaction: discord.Interaction):
        """斜線命令：允許賣家設定物品價格，使用分頁功能"""
        logger.info(f'收到來自 {interaction.user} 的 /set_item_prices 斜線命令')

        from utils.utils import check_guild
        if not await check_guild(interaction, owner_only=False, required_role="Trader"):
            return

        import json
        import os

        # 確保 settings 目錄存在
        os.makedirs("/app/settings", exist_ok=True)
        prices_file_path = "/app/settings/item_prices.json"

        # 讀取現有的價格設定
        seller_prices = {}
        if os.path.exists(prices_file_path):
            try:
                with open(prices_file_path, 'r', encoding='utf-8') as f:
                    seller_prices = json.load(f)
            except Exception as e:
                logger.error(f"讀取價格檔案時發生錯誤: {str(e)}")
                await safe_send_interaction_message(interaction, "無法讀取價格設定，請稍後再試。", ephemeral=True)
                return

        user_id = str(interaction.user.id)
        if user_id not in seller_prices:
            seller_prices[user_id] = {}

        # 分頁設定
        items_per_page = 5
        total_pages = (len(ITEMS) + items_per_page - 1) // items_per_page
        current_page = 0

        def create_embed(page):
            embed = discord.Embed(
                title=f"設定物品價格 - 第 {page + 1} 頁 / {total_pages} 頁",
                description="請使用「編輯」按鈕來設定價格，或使用按鈕切換頁面。",
                color=discord.Color.purple()
            )
            start_idx = page * items_per_page
            end_idx = min(start_idx + items_per_page, len(ITEMS))
            for item in ITEMS[start_idx:end_idx]:
                price = seller_prices[user_id].get(item['value'], 0)
                embed.add_field(
                    name=f"{item['label']} ({item['description']})",
                    value=f"目前價格: {price}",
                    inline=False
                )
            return embed

        def create_view(page):
            view = discord.ui.View()
            if total_pages > 1:
                if page > 0:
                    prev_button = discord.ui.Button(
                        label="上一頁",
                        style=discord.ButtonStyle.blurple,
                        custom_id=f"set_prices_prev_{page}"
                    )
                    prev_button.callback = lambda inter: update_page(inter, page - 1)
                    view.add_item(prev_button)
                if page < total_pages - 1:
                    next_button = discord.ui.Button(
                        label="下一頁",
                        style=discord.ButtonStyle.blurple,
                        custom_id=f"set_prices_next_{page}"
                    )
                    next_button.callback = lambda inter: update_page(inter, page + 1)
                    view.add_item(next_button)
            edit_button = discord.ui.Button(label="編輯", style=discord.ButtonStyle.primary, custom_id=f"set_prices_edit_{page}")
            edit_button.callback = lambda inter: edit_items(inter, page)
            view.add_item(edit_button)
            finish_button = discord.ui.Button(label="完成", style=discord.ButtonStyle.success, custom_id="set_prices_finish")
            finish_button.callback = lambda inter: finish_editing(inter)
            view.add_item(finish_button)
            cancel_button = discord.ui.Button(label="取消", style=discord.ButtonStyle.danger, custom_id="set_prices_cancel")
            cancel_button.callback = lambda inter: self.handle_cancel(inter, "設定物品價格", "操作已取消。")
            view.add_item(cancel_button)
            return view

        async def update_page(interaction: discord.Interaction, new_page):
            nonlocal current_page
            current_page = new_page
            await interaction.response.edit_message(embed=create_embed(current_page), view=create_view(current_page))

        async def edit_items(interaction: discord.Interaction, page):
            start_idx = page * items_per_page
            end_idx = min(start_idx + items_per_page, len(ITEMS))
            items_to_edit = ITEMS[start_idx:end_idx]

            class EditItemPricesModal(discord.ui.Modal):
                def __init__(self):
                    super().__init__(title=f"編輯物品價格 - 第 {page + 1} 頁")
                    self.inputs = []
                    for item in items_to_edit:
                        price_input = discord.ui.TextInput(
                            label=item['label'],
                            placeholder="輸入價格（整數）",
                            default=str(seller_prices[user_id].get(item['value'], 0))
                        )
                        self.add_item(price_input)
                        self.inputs.append((item['value'], price_input))

                async def on_submit(self, interaction: discord.Interaction):
                    try:
                        for value, input_field in self.inputs:
                            price = int(input_field.value)
                            if price < 0:
                                await safe_send_interaction_message(interaction, f"{input_field.label} 的價格不能為負數，請重試。", ephemeral=True)
                                return
                            seller_prices[user_id][value] = price

                        with open(prices_file_path, 'w', encoding='utf-8') as f:
                            json.dump(seller_prices, f, ensure_ascii=False, indent=2)

                        await safe_send_interaction_message(interaction, "已更新所有物品價格。", ephemeral=True)
                        await interaction.followup.edit_message(
                            interaction.message.id,
                            embed=create_embed(current_page),
                            view=create_view(current_page)
                        )
                    except ValueError:
                        await safe_send_interaction_message(interaction, "所有價格必須是有效的整數，請重試。", ephemeral=True)
                    except Exception as e:
                        logger.error(f"處理物品價格提交時發生錯誤: {str(e)}")
                        await safe_send_interaction_message(interaction, "處理價格時發生錯誤，請重試。", ephemeral=True)

            await interaction.response.send_modal(EditItemPricesModal())

        async def finish_editing(interaction: discord.Interaction):
            await interaction.response.edit_message(view=None)
            await safe_send_interaction_message(interaction, "價格設定已完成。", ephemeral=True)

        await safe_send_interaction_message(interaction, embed=create_embed(current_page), view=create_view(current_page), ephemeral=True)

    @app_commands.command(name="select_item", description="選擇一或多樣物品進行購買")
    async def select_item_cmd(self, interaction: discord.Interaction):
        """斜線命令：顯示圖片和選擇器以選擇多件物品"""
        logger.info(f'收到來自 {interaction.user} 的 /select_item 斜線命令')

        # 檢查是否在伺服器中使用並檢查角色權限
        from utils.utils import check_guild
        if not await check_guild(interaction, owner_only=False):
            return

        embed = discord.Embed(
            title="選擇物品",
            description="請從以下選項中選擇一件或多件物品進行購買。",
            color=discord.Color.blue()
        )
        # 從本地上傳圖片文件
        file = discord.File("/app/static/items.png", filename="items.png")
        embed.set_image(url="attachment://items.png")

        select = discord.ui.Select(
            placeholder="選擇多件物品...",
            min_values=1,
            max_values=len(ITEMS),
            custom_id="select_item_main",
            options=[discord.SelectOption(**item) for item in ITEMS]
        )

        async def handle_cancel(interaction: discord.Interaction, operation: str, message: str, additional_log: str = ""):
            """處理取消操作"""
            await interaction.response.edit_message(view=None)
            await safe_send_interaction_message(interaction, message, ephemeral=True)
            logger.info(f'用戶 {interaction.user} 已取消{operation}操作。{additional_log}')


        async def select_callback(interaction: discord.Interaction):
            """處理多選下拉選單的回調，進入數量指定階段"""
            logger.info(f'開始執行 select_item select_callback，選擇的選項: {select.values}')
            try:
                if not select.values:
                    await safe_send_interaction_message(interaction, "您未選擇任何選項。", ephemeral=True)
                    return

                selected_items = {value: 1 for value in select.values}
                items_per_page = 5
                total_pages = (len(selected_items) + items_per_page - 1) // items_per_page
                current_page = 0

                def create_embed(page):
                    embed = discord.Embed(
                        title=f"選取物品 - 第 {page + 1} 頁 / {total_pages} 頁",
                        description="請使用「編輯」按鈕來設定數量，或使用按鈕切換其他項目編輯數量。",
                        color=discord.Color.blue()
                    )
                    start_idx = page * items_per_page
                    end_idx = min(start_idx + items_per_page, len(selected_items))
                    page_items = list(selected_items.keys())[start_idx:end_idx]
                    all_items = list(selected_items.keys())
                    for value in all_items:
                        label = next(opt.label for opt in select.options if opt.value == value)
                        if value in page_items:
                            embed.add_field(
                                name=" ",
                                value=f"**{label}: {selected_items[value]}個**",
                                inline=False
                            )
                        else:
                            embed.add_field(
                                name=" ",
                                value=f"{label}: {selected_items[value]}個",
                                inline=False
                            )
                    return embed

                def create_view(page):
                    view = discord.ui.View()
                    if total_pages > 1:
                        if page > 0:
                            prev_button = discord.ui.Button(
                                label="上一頁",
                                style=discord.ButtonStyle.blurple,
                                custom_id=f"select_item_prev_{page}"
                            )
                            prev_button.callback = lambda inter: update_page(inter, page - 1)
                            view.add_item(prev_button)
                        if page < total_pages - 1:
                            next_button = discord.ui.Button(
                                label="下一頁",
                                style=discord.ButtonStyle.blurple,
                                custom_id=f"select_item_next_{page}"
                            )
                            next_button.callback = lambda inter: update_page(inter, page + 1)
                            view.add_item(next_button)
                    edit_button = discord.ui.Button(label="編輯", style=discord.ButtonStyle.primary, custom_id=f"select_item_edit_{page}")
                    edit_button.callback = lambda inter: edit_items(inter, page)
                    view.add_item(edit_button)
                    finish_button = discord.ui.Button(label="完成", style=discord.ButtonStyle.success, custom_id="select_item_finish")
                    finish_button.callback = lambda inter: finish_editing(inter)
                    view.add_item(finish_button)
                    cancel_button = discord.ui.Button(label="取消", style=discord.ButtonStyle.danger, custom_id="select_item_cancel")
                    cancel_button.callback = lambda inter: handle_cancel(inter, "選取物品", "操作已取消。")
                    view.add_item(cancel_button)
                    return view

                async def update_page(interaction: discord.Interaction, new_page):
                    nonlocal current_page
                    current_page = new_page
                    await interaction.response.edit_message(embed=create_embed(current_page), view=create_view(current_page))

                async def edit_items(interaction: discord.Interaction, page):
                    start_idx = page * items_per_page
                    end_idx = min(start_idx + items_per_page, len(selected_items))
                    page_items = list(selected_items.keys())[start_idx:end_idx]

                    class EditItemQuantitiesModal(discord.ui.Modal):
                        def __init__(self):
                            super().__init__(title=f"編輯數量 - 第 {page + 1} 頁")
                            self.inputs = []
                            self.restricted_items = ["universe_radio", "universe_special", "dragon_first_charge"]

                            for value in page_items:
                                label = next(opt.label for opt in select.options if opt.value == value)
                                qty_input = discord.ui.TextInput(
                                    label=label,
                                    placeholder="輸入數量（1-10）",
                                    default=str(selected_items[value]),
                                    style=discord.TextStyle.short,
                                    required=False if value in self.restricted_items else True,
                                    custom_id=f"qty_{value}"
                                )
                                if value in self.restricted_items:
                                    qty_input.disabled = True
                                self.add_item(qty_input)
                                self.inputs.append((value, qty_input))

                        async def on_submit(self, interaction: discord.Interaction):
                            error_fields = []
                            try:
                                for value, input_field in self.inputs:
                                    qty_str = input_field.value.strip()
                                    if not qty_str.isdigit():
                                        error_fields.append(f"{input_field.label}: 必須是有效的整數")
                                        continue

                                    qty = int(qty_str)
                                    if qty < 1 or qty > 10:
                                        error_fields.append(f"{input_field.label}: 數量必須介於 1 到 10 之間")
                                        continue

                                    if value in self.restricted_items and qty > 1:
                                        error_fields.append(f"{input_field.label}: 此物品限制只能購買 1 個")
                                        continue

                                    selected_items[value] = qty

                                if error_fields:
                                    error_embed = discord.Embed(
                                        title="輸入錯誤",
                                        description="以下項目的數量輸入有誤，請修正後重新提交：\n" + "\n".join(error_fields),
                                        color=discord.Color.red()
                                    )
                                    await safe_send_interaction_message(interaction, embed=error_embed, ephemeral=True)
                                    return

                                await safe_send_interaction_message(interaction, f"已更新第 {page + 1} 頁的數量。", ephemeral=True)
                                await interaction.followup.edit_message(
                                    interaction.message.id,
                                    embed=create_embed(current_page),
                                    view=create_view(current_page)
                                )
                            except Exception as e:
                                logger.error(f"處理數量提交時發生錯誤: {str(e)}")
                                await safe_send_interaction_message(interaction, "處理數量時發生錯誤，請重試。", ephemeral=True)

                    await interaction.response.send_modal(EditItemQuantitiesModal())

                async def finish_editing(interaction: discord.Interaction):
                    summary_embed = discord.Embed(
                        title="最終確認",
                        description="您的選擇如下：",
                        color=discord.Color.green()
                    )
                    purchase_summary = []
                    for value in selected_items:
                        label = next(opt.label for opt in select.options if opt.value == value)
                        summary_embed.add_field(name=label, value=f"數量: {selected_items[value]}", inline=False)
                        purchase_summary.append(f"{selected_items[value]} 個 {label}")

                    def create_confirm_view():
                        view = discord.ui.View()
                        confirm_button = discord.ui.Button(label="確定購買", style=discord.ButtonStyle.green, custom_id="select_item_confirm_purchase")
                        cancel_button = discord.ui.Button(label="取消購買", style=discord.ButtonStyle.red, custom_id="select_item_cancel_purchase")

                        async def confirm_callback(interaction: discord.Interaction):
                            await interaction.response.edit_message(view=None)
                            await safe_send_interaction_message(interaction, f"您已確認購買：\n" + "\n".join(purchase_summary), ephemeral=True)
                            logger.info(f'用戶已確認購買: {selected_items}')

                            # 檢查是否已設定交易論壇頻道
                            from utils.utils import get_trade_forum_channel_id
                            logger.debug("準備調用 get_trade_forum_channel_id 函數 (調用者: TradeCommands)")
                            forum_channel_id = await get_trade_forum_channel_id(config_file="config.json", caller="TradeCommands")
                            logger.debug(f"從 get_trade_forum_channel_id 函數返回的 forum_channel_id: {forum_channel_id} (調用者: TradeCommands)")
                            if forum_channel_id == 1234567890:
                                await safe_send_interaction_message(
                                    interaction,
                                    "交易論壇頻道尚未設定，請通知管理員。",
                                    ephemeral=True
                                )
                                logger.warning("交易論壇頻道未設定，使用預設佔位符 ID")
                                return

                            try:
                                forum_channel = interaction.guild.get_channel(forum_channel_id)
                                if forum_channel and forum_channel.type == discord.ChannelType.forum:
                                    if len(purchase_summary) == 1:
                                        thread_title = f"{interaction.user.display_name} - 需要購買 {purchase_summary[0]}"
                                    else:
                                        thread_title = f"{interaction.user.display_name} - 需要購買多件物品"
                                    thread_content = f"群友 {interaction.user.mention} ({interaction.user.name}) 需要購買：\n" + "\n".join(purchase_summary)
                                    # 嘗試找到名為「代儲」的標籤，如果找不到則嘗試創建一個新標籤
                                    applied_tags = []
                                    for tag in forum_channel.available_tags:
                                        if tag.name == "代儲":
                                            applied_tags.append(tag)
                                            break
                                    if not applied_tags:
                                        try:
                                            # 嘗試創建新標籤
                                            new_tag = await forum_channel.create_tag(name="代儲")
                                            applied_tags.append(new_tag)
                                            logger.info(f"已創建新標籤「代儲」並應用到貼文")
                                        except Exception as tag_error:
                                            logger.error(f"創建新標籤「代儲」時發生錯誤: {str(tag_error)}")
                                            # 如果創建標籤失敗，則不使用標籤繼續創建貼文

                                    await forum_channel.create_thread(name=thread_title, content=thread_content, applied_tags=applied_tags)
                                    logger.info(f"在論壇頻道 {forum_channel_id} 新增貼文: {thread_title}，使用標籤: {applied_tags if applied_tags else '無'}")
                                else:
                                    logger.error(f"無法找到論壇頻道 {forum_channel_id} 或該頻道不是論壇類型")
                                    await safe_send_interaction_message(
                                        interaction,
                                        "無法找到設定的論壇頻道，請確認設定或重新使用 `/set_trade_forum_channel` 命令設定。",
                                        ephemeral=True
                                    )
                            except Exception as e:
                                logger.error(f"處理論壇頻道 {forum_channel_id} 時發生錯誤: {str(e)}")
                                await safe_send_interaction_message(
                                    interaction,
                                    "無法處理論壇頻道操作，請確認機器人有相關權限或聯繫管理員。",
                                    ephemeral=True
                                )

                        async def cancel_callback(interaction: discord.Interaction):
                            await interaction.response.edit_message(view=None)
                            await safe_send_interaction_message(interaction, "您已取消購買。", ephemeral=True)
                            logger.info(f'用戶已取消購買: {selected_items}')

                        confirm_button.callback = confirm_callback
                        cancel_button.callback = cancel_callback
                        view.add_item(confirm_button)
                        view.add_item(cancel_button)
                        return view

                    await interaction.response.edit_message(embed=summary_embed, view=create_confirm_view())

                await safe_send_interaction_message(interaction, embed=create_embed(current_page), view=create_view(current_page), ephemeral=True)
            except Exception as e:
                error_details = ''.join(traceback.format_exception(type(e), e, e.__traceback__))
                logger.error(f'select_item select_callback 錯誤: {str(e)}\n詳細錯誤信息:\n{error_details}')
                await safe_send_interaction_message(interaction, "發生錯誤，請稍後再試。", ephemeral=True)

        select.callback = select_callback
        view = discord.ui.View()
        view.add_item(select)

        await safe_send_interaction_message(interaction, embed=embed, view=view, file=file, ephemeral=True)


async def setup(bot):
    await bot.add_cog(TradeCommands(bot))
