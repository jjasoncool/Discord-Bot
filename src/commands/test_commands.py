import logging
import discord
from discord import app_commands
from discord.ext import commands

# 獲取 logger
logger = logging.getLogger('discord_bot')

class TestCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # 斜線命令
    @app_commands.command(name="ping", description="測試機器人是否在線")
    async def ping_cmd(self, interaction: discord.Interaction):
        """斜線命令：測試機器人是否在線"""
        logger.info(f'收到來自 {interaction.user} 的 /ping 斜線命令')
        await interaction.response.send_message('Pong!', ephemeral=True)

    @app_commands.command(name="hello", description="獲取一個 Hello World 訊息")
    async def hello_cmd(self, interaction: discord.Interaction):
        """斜線命令：Hello World"""
        logger.info(f'收到來自 {interaction.user} 的 /hello 斜線命令')
        await interaction.response.send_message(
            f'👋 Hello World! 您好，{interaction.user.mention}！我是一個由 Discord.py 驅動的機器人。',
            ephemeral=True
        )

    @app_commands.command(name="echo", description="讓機器人回傳一段訊息")
    @app_commands.describe(
        message="要回傳的訊息",
        private="是否只有您能看到回應 (默認: 是)"
    )
    async def echo_cmd(self, interaction: discord.Interaction, message: str, private: bool = False):
        """斜線命令：回傳用戶輸入的訊息"""
        logger.info(f'收到來自 {interaction.user} 的 /echo 斜線命令，參數: message="{message}", private={private}')
        await interaction.response.send_message(
            f'📣 {interaction.user.mention} 說: {message}',
            ephemeral=private
        )    # list_channels 命令已移至 management_commands.py

    # 傳統前綴命令
    @commands.command(name='ping')
    async def ping(self, ctx):
        """回應一個 Pong 訊息，用於測試機器人是否在線"""
        logger.info(f'收到來自 {ctx.author} 的 ping 前綴命令')
        await ctx.send('Pong!')

    @commands.command(name='helloworld')
    async def hello_world(self, ctx):
        """回應一個 Hello World 訊息"""
        logger.info(f'收到來自 {ctx.author} 的 helloworld 前綴命令')
        await ctx.send(f'👋 Hello World! 您好，{ctx.author.mention}！我是一個由 Discord.py 驅動的機器人。')

async def setup(bot):
    await bot.add_cog(TestCommands(bot))
    # 不需要在這裡同步命令，我們將在主程式中一次性同步所有命令
