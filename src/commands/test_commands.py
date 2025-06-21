import logging
import discord
import traceback
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

    @app_commands.command(name="list_forum_posts", description="列出特定論壇頻道的前20則留言")
    async def list_forum_posts_cmd(self, interaction: discord.Interaction):
        """斜線命令：列出特定論壇頻道的前20則留言"""
        logger.info(f'收到來自 {interaction.user} 的 /list_forum_posts 斜線命令')

        if not interaction.guild:
            await interaction.response.send_message("此命令只能在伺服器中使用！", ephemeral=True)
            return

        forum_channels = [ch for ch in interaction.guild.channels if isinstance(ch, discord.ForumChannel)]
        if not forum_channels:
            await interaction.response.send_message("此伺服器中沒有論壇頻道。", ephemeral=True)
            return

        embed = discord.Embed(
            title="選擇一個論壇頻道",
            description="請從以下論壇頻道中選擇一個以查看前20則貼文：",
            color=discord.Color.blue()
        )

        for i, channel in enumerate(forum_channels, 1):
            embed.add_field(
                name=f"{i}. {channel.name}",
                value=f"ID: {channel.id}",
                inline=False
            )

        select = discord.ui.Select(
            placeholder="選擇一個論壇頻道...",
            options=[
                discord.SelectOption(label=channel.name, value=str(channel.id), description=f"ID: {channel.id}")
                for channel in forum_channels
            ]
        )

        async def select_callback(interaction: discord.Interaction):
            logger.info(f'開始執行 select_callback 函數，選擇的頻道ID: {select.values[0]}')
            try:
                channel_id = int(select.values[0])
                channel = interaction.guild.get_channel(channel_id)
                if not channel:
                    await interaction.response.send_message("找不到指定的論壇頻道，請重試。", ephemeral=True)
                    return

                threads = channel.threads
                if not threads:
                    await interaction.response.send_message("此論壇頻道中沒有任何貼文。", ephemeral=True)
                    return

                embed = discord.Embed(
                    title=f"{channel.name} 論壇頻道的前20則貼文",
                    description="以下是此論壇頻道中的前20則貼文：",
                    color=discord.Color.green()
                )

                for i, thread in enumerate(threads[:20], 1):
                    owner_mention = "未知用戶"
                    if thread.owner_id:
                        try:
                            owner = await interaction.guild.fetch_member(thread.owner_id)
                            if owner:
                                owner_mention = owner.mention
                        except discord.NotFound:
                            owner_mention = "未知用戶 (已離開群組)"
                        except Exception as e:
                            logger.error(f"獲取貼文擁有者信息時發生錯誤: {str(e)}")
                    tags = ", ".join(tag.name for tag in thread.applied_tags) if thread.applied_tags else "無標籤"
                    embed.add_field(
                        name=f"貼文 {i}: {thread.name}",
                        value=f"由 {owner_mention} 創建於 {thread.created_at.strftime('%Y-%m-%d %H:%M:%S')}\n標籤: {tags}",
                        inline=False
                    )

                await interaction.response.send_message(embed=embed, ephemeral=True)
                logger.info(f'成功執行 select_callback 函數，頻道名稱: {channel.name}')
            except Exception as e:
                error_details = ''.join(traceback.format_exception(type(e), e, e.__traceback__))
                logger.error(f'在 select_callback 函數中發生錯誤: {str(e)}\n詳細錯誤信息:\n{error_details}')
                await interaction.response.send_message("發生錯誤，請稍後再試。", ephemeral=True)

        select.callback = select_callback
        view = discord.ui.View()
        view.add_item(select)

        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

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
