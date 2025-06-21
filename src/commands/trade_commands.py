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

        select = discord.ui.Select(
            placeholder="選擇一件物品...",
            options=[
                discord.SelectOption(label="月相觀測卡", value="moon_card", description="每日提供90星聲"),
                discord.SelectOption(label="寰宇電台", value="universe_radio", description="提供額外資源"),
                discord.SelectOption(label="寰宇特約", value="universe_special", description="提供額外資源與橫幅"),
                discord.SelectOption(label="一條龍", value="dragon_first_charge", description="全部雙倍首儲一次購買"),
                discord.SelectOption(label="60月相", value="moon_60", description="60月相"),
                discord.SelectOption(label="300月相", value="moon_300", description="額外+30"),
                discord.SelectOption(label="980月相", value="moon_980", description="額外+110"),
                discord.SelectOption(label="1980月相", value="moon_1980", description="額外+260"),
                discord.SelectOption(label="3280月相", value="moon_3280", description="額外+600"),
                discord.SelectOption(label="6480月相", value="moon_6480", description="額外+1600"),
                discord.SelectOption(label="32400月相", value="moon_32400", description="額外+8000"),
                discord.SelectOption(label="64800月相", value="moon_64800", description="額外+16000")
            ]
        )

        async def select_callback(interaction: discord.Interaction):
            # 獲取選中選項的標籤
            selected_option = next((option for option in select.options if option.value == select.values[0]), None)
            if selected_option:
                from datetime import datetime
                current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                logger.info(f"用戶 {interaction.user.id} ({interaction.user.name}) 在 {current_time} 選擇了物品 {selected_option.label}")
                await interaction.response.send_message(f"您選擇了 {selected_option.label}", ephemeral=True)
            else:
                await interaction.response.send_message("選擇出錯，請重試", ephemeral=True)

        select.callback = select_callback
        view = discord.ui.View()
        view.add_item(select)

        await interaction.response.send_message(embed=embed, view=view, file=file, ephemeral=True)

async def setup(bot):
    await bot.add_cog(TradeCommands(bot))
