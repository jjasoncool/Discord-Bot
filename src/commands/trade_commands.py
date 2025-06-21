import logging
import discord
from discord import app_commands
from discord.ext import commands

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
            {"label": "月相觀測卡", "value": "moon_card", "description": "每日提供90星聲"},
            {"label": "寰宇電台", "value": "universe_radio", "description": "提供額外資源"},
            {"label": "寰宇特約", "value": "universe_special", "description": "提供額外資源與橫幅"},
            {"label": "一條龍", "value": "dragon_first_charge", "description": "全部雙倍首儲一次購買"},
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
                logger.info(f"用戶 {interaction.user.id} ({interaction.user.name}) 確認購買 {qty} 個 {selected_label}")
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
                logger.info(f"用戶 {interaction.user.id} ({interaction.user.name}) 取消購買 {qty} 個 {selected_label}")
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
                logger.info(f"用戶 {interaction.user.id} ({interaction.user.name}) 在 {current_time} 選擇了物品 {selected_option.label}")

                # 檢查是否為限制只能購買一個的物品
                restricted_items = ["universe_radio", "universe_special", "dragon_first_charge"]
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

                    quantity_select = discord.ui.Select(
                        placeholder="選擇數量...",
                        options=[
                            discord.SelectOption(label="1", value="1"),
                            discord.SelectOption(label="2", value="2"),
                            discord.SelectOption(label="3", value="3"),
                            discord.SelectOption(label="4", value="4"),
                            discord.SelectOption(label="5", value="5"),
                            discord.SelectOption(label="10", value="10")
                        ]
                    )

                    async def quantity_callback(interaction: discord.Interaction):
                        quantity = quantity_select.values[0]
                        logger.info(f"用戶 {interaction.user.id} ({interaction.user.name}) 選擇了數量 {quantity} 個 {selected_option.label}")
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
