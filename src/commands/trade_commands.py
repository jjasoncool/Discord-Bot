import logging
import discord
from discord import app_commands
from discord.ext import commands
import asyncio

# 獲取 logger
logger = logging.getLogger('discord_bot')

class TradeCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="trade_info", description="查詢交易相關資訊")
    async def trade_info_cmd(self, interaction: discord.Interaction):
        """斜線命令：提供交易相關資訊"""
        logger.info(f'收到來自 {interaction.user} 的 /trade_info 斜線命令')

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

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @commands.Cog.listener()
    async def on_message(self, message):
        """監控私人 thread 中的訊息，處理交易確認"""
        if message.channel.type != discord.ChannelType.private_thread:
            return

        if message.author == self.bot.user:
            return

        content = message.content.strip()
        if content == "請領收" or "🤝" in content:
            logger.info(f"收到交易確認請求，訊息內容: {content}，來自使用者: {message.author.name}")
            # 從機器人發送的前三則非空訊息中提取賣家和買家資訊
            message_count = 0
            async for msg in message.channel.history(limit=10, oldest_first=True):
                if msg.content:  # 檢查訊息內容是否為空
                    message_count += 1
                    logger.info(f"檢查訊息 {message_count}/3，作者: {msg.author.name}, 內容: {msg.content[:150]}...")
                    if msg.author == self.bot.user:
                        logger.info(f"找到機器人發送的訊息，完整內容: {msg.content}")
                        content_lines = msg.content.split('\n')
                        seller_mention = None
                        buyer_mention = None
                        source_post_id = None
                        for line in content_lines:
                            if "貼文者為" in line:
                                buyer_mention = line.split("貼文者為 ")[1].strip()
                                logger.info(f"提取買家提及: {buyer_mention}")
                            elif "對交易貼文" in line and "有興趣" in line:
                                seller_mention = line.split("對交易貼文")[0].replace("使用者", "").strip()
                                logger.info(f"提取賣家提及: {seller_mention}")
                            elif "來源貼文 ID:" in line:
                                try:
                                    source_post_id = line.split("來源貼文 ID:")[1].strip()
                                    logger.info(f"提取來源貼文 ID: {source_post_id}")
                                except IndexError:
                                    logger.error(f"無法從行中提取來源貼文 ID: {line}")
                        if seller_mention and buyer_mention and source_post_id:
                            if message.author.mention == seller_mention:
                                logger.info(f"確認使用者 {message.author.name} 為賣方，處理交易確認請求")
                                await self.handle_trade_confirmation(message, source_post_id)
                                return
                            else:
                                logger.info(f"使用者 {message.author.name} 不是賣方，忽略交易確認請求")
                                return
                        elif seller_mention and buyer_mention:
                            if message.author.mention == seller_mention:
                                logger.info(f"確認使用者 {message.author.name} 為賣方，但缺少來源貼文 ID")
                                logger.error("無法從訊息中提取來源貼文 ID")
                                await message.channel.send("無法識別此交易 thread 的來源貼文 ID，請手動確認交易狀態。")
                                return
                            else:
                                logger.info(f"使用者 {message.author.name} 不是賣方，忽略交易確認請求")
                                return
                        else:
                            logger.error(f"無法從機器人訊息中提取賣方和買方資訊: {msg.content}")
                            await message.channel.send("無法識別此交易 thread 的賣方和買方，請手動確認交易狀態。")
                            return
                    if message_count >= 3:
                        break
            if message_count == 0 or (message_count < 3 and not any(msg.author == self.bot.user for msg in message.channel.history(limit=10, oldest_first=True))):
                logger.error(f"無法找到足夠的非空訊息或機器人發送的訊息")
                await message.channel.send("無法識別此交易 thread 的賣方和買方，請手動確認交易狀態。")
                return

    async def handle_trade_confirmation(self, message, source_post_id):
        """處理交易確認請求"""
        from utils import get_trade_forum_channel_id
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

            # 鎖定並封存來源貼文
            await source_message.channel.edit(locked=True, archived=True)
            logger.info(f"已鎖定並封存來源貼文 {source_message.id} 的頻道")

            await thread.send(f"交易已由雙方確認完成。此 thread 及來源貼文已被鎖定。")
        except asyncio.TimeoutError:
            logger.warning(f"交易確認超時，買家 {post_author.name} 未在24小時內確認")
            await thread.send(f"{post_author.mention}，您未在24小時內確認交易，交易已自動確認領收。")
            # 自動確認領收，鎖定並封存 thread 和來源貼文
            await thread.edit(locked=True, archived=True)
            logger.info(f"已因超時自動鎖定並封存 thread {thread.name}，ID: {thread.id}")
            await source_message.channel.edit(locked=True, archived=True)
            logger.info(f"已因超時自動鎖定並封存來源貼文 {source_message.id} 的頻道")
            await thread.send(f"交易已自動確認完成。此 thread 及來源貼文已被鎖定。")
        except Exception as e:
            logger.error(f"處理交易確認反應時發生錯誤: {str(e)}")
            await thread.send("處理交易確認時發生錯誤，請手動確認交易狀態。")

    @app_commands.command(name="select_item", description="選擇一件物品進行購買")
    async def select_item_cmd(self, interaction: discord.Interaction):
        """斜線命令：顯示圖片和選擇器以選擇物品"""
        logger.info(f'收到來自 {interaction.user} 的 /select_item 斜線命令')

        embed = discord.Embed(
            title="選擇物品",
            description="請從以下選項中選擇一件物品進行購買。",
            color=discord.Color.blue()
        )
        # 從本地上傳圖片文件
        file = discord.File("/app/static/items.png", filename="items.png")
        embed.set_image(url="attachment://items.png")

        # 物品選項配置，未來可以從配置文件或數據庫中讀取
        ITEMS = [
            {"label": "月相觀測卡", "value": "moon_card", "description": "小月卡"},
            {"label": "寰宇電台", "value": "universe_radio", "description": "大月卡"},
            {"label": "寰宇特約", "value": "universe_special", "description": "特約月卡 - 含名片"},
            {"label": "一條龍", "value": "dragon_first_charge", "description": "各檔位月相一次購買"},
            {"label": "商城禮包", "value": "store_gift_pack", "description": "商城禮包自選"},
            {"label": "60月相", "value": "moon_60", "description": "60月相"},
            {"label": "300月相", "value": "moon_300", "description": "額外+30"},
            {"label": "980月相", "value": "moon_980", "description": "額外+110"},
            {"label": "1980月相", "value": "moon_1980", "description": "額外+260"},
            {"label": "3280月相", "value": "moon_3280", "description": "額外+600"},
            {"label": "6480月相", "value": "moon_6480", "description": "額外+1600"},
            {"label": "32400月相", "value": "moon_32400", "description": "額外+8000"},
            {"label": "64800月相", "value": "moon_64800", "description": "額外+16000"}
        ]

        select = discord.ui.Select(
            placeholder="選擇一件物品...",
            options=[discord.SelectOption(**item) for item in ITEMS]
        )

        def create_confirm_view(interaction: discord.Interaction, selected_option, quantity):
            embed = discord.Embed(
                title="確認購買",
                description=f"您選擇了 {quantity} 個 {selected_option.label}，請確認或取消。",
                color=discord.Color.blue()
            )

            confirm_button = discord.ui.Button(label="確定", style=discord.ButtonStyle.green)
            cancel_button = discord.ui.Button(label="取消", style=discord.ButtonStyle.red)

            async def confirm_callback(interaction: discord.Interaction, selected_label=selected_option.label, qty=quantity):
                logger.info(f"使用者 {interaction.user.id} ({interaction.user.name}) 確認購買 {qty} 個 {selected_label}")
                await interaction.response.edit_message(view=None)
                await interaction.followup.send(f"您已確認購買 {qty} 個 {selected_label}", ephemeral=True)
                # 完全移除所有互動元素
                await interaction.followup.edit_message(interaction.message.id, view=None)

                # 檢查是否已設定交易論壇頻道
                from utils import get_trade_forum_channel_id
                logger.debug("準備調用 get_trade_forum_channel_id 函數 (調用者: TradeCommands)")
                forum_channel_id = await get_trade_forum_channel_id(config_file="config.json", caller="TradeCommands")
                logger.debug(f"從 get_trade_forum_channel_id 函數返回的 forum_channel_id: {forum_channel_id} (調用者: TradeCommands)")
                if forum_channel_id == 1234567890:
                    await interaction.followup.send(
                        "交易論壇頻道尚未設定，請通知管理員。",
                        ephemeral=True
                    )
                    logger.warning("交易論壇頻道未設定，使用預設佔位符 ID")
                    return

                try:
                    forum_channel = interaction.guild.get_channel(forum_channel_id)
                    if forum_channel and forum_channel.type == discord.ChannelType.forum:
                        thread_title = f"{interaction.user.display_name} - 需要購買 {qty} 個 {selected_label}"
                        thread_content = f"群友 {interaction.user.mention} ({interaction.user.name}) 需要購買 {qty} 個 {selected_label}。"
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
                        await interaction.followup.send(
                            "無法找到設定的論壇頻道，請確認設定或重新使用 `/set_trade_forum_channel` 命令設定。",
                            ephemeral=True
                        )
                except Exception as e:
                    logger.error(f"處理論壇頻道 {forum_channel_id} 時發生錯誤: {str(e)}")
                    await interaction.followup.send(
                        "無法處理論壇頻道操作，請確認機器人有相關權限或聯繫管理員。",
                        ephemeral=True
                    )

            async def cancel_callback(interaction: discord.Interaction, selected_label=selected_option.label, qty=quantity):
                logger.info(f"使用者 {interaction.user.id} ({interaction.user.name}) 取消購買 {qty} 個 {selected_label}")
                await interaction.response.edit_message(view=None)
                await interaction.followup.send(f"您已取消購買 {qty} 個 {selected_label}", ephemeral=True)
                # 完全移除所有互動元素
                await interaction.followup.edit_message(interaction.message.id, view=None)

            confirm_button.callback = lambda inter: confirm_callback(inter)
            cancel_button.callback = lambda inter: cancel_callback(inter)

            confirm_view = discord.ui.View()
            confirm_view.add_item(confirm_button)
            confirm_view.add_item(cancel_button)

            return embed, confirm_view

        async def select_callback(interaction: discord.Interaction):
            # 獲取選中選項的標籤
            selected_option = next((option for option in select.options if option.value == select.values[0]), None)
            if selected_option:
                from datetime import datetime
                current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                logger.info(f"使用者 {interaction.user.id} ({interaction.user.name}) 在 {current_time} 選擇了物品 {selected_option.label}")

                # 檢查是否為限制只能購買一個的物品
                restricted_items = ["universe_radio", "universe_special", "dragon_first_charge", "store_gift_pack"]
                if selected_option.value in restricted_items:
                    # 直接進入確認購買步驟，數量固定為1
                    embed, confirm_view = create_confirm_view(interaction, selected_option, 1)
                    await interaction.response.send_message(embed=embed, view=confirm_view, ephemeral=True)
                else:
                    # 先發送數量選擇框
                    embed = discord.Embed(
                        title="選擇數量",
                        description=f"您選擇了 {selected_option.label}，請選擇購買數量。",
                        color=discord.Color.blue()
                    )

                    # 根據所選物品動態設置數量選項
                    quantity_options = [
                        discord.SelectOption(label="1", value="1"),
                        discord.SelectOption(label="2", value="2"),
                        discord.SelectOption(label="3", value="3"),
                        discord.SelectOption(label="4", value="4"),
                        discord.SelectOption(label="5", value="5")
                    ]
                    if selected_option.value != "moon_card":
                        quantity_options.append(discord.SelectOption(label="10", value="10"))

                    quantity_select = discord.ui.Select(
                        placeholder="選擇數量...",
                        options=quantity_options
                    )

                    async def quantity_callback(interaction: discord.Interaction):
                        quantity = quantity_select.values[0]
                        logger.info(f"使用者 {interaction.user.id} ({interaction.user.name}) 選擇了數量 {quantity} 個 {selected_option.label}")
                        await interaction.response.edit_message(view=None)
                        embed, confirm_view = create_confirm_view(interaction, selected_option, quantity)
                        await interaction.followup.send(embed=embed, view=confirm_view, ephemeral=True)

                    quantity_select.callback = quantity_callback
                    quantity_view = discord.ui.View()
                    quantity_view.add_item(quantity_select)

                    await interaction.response.send_message(embed=embed, view=quantity_view, ephemeral=True)
            else:
                await interaction.response.send_message("選擇出錯，請重試", ephemeral=True)

        select.callback = select_callback
        view = discord.ui.View()
        view.add_item(select)

        await interaction.response.send_message(embed=embed, view=view, file=file, ephemeral=True)


async def setup(bot):
    await bot.add_cog(TradeCommands(bot))
