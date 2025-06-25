"""
官方文章更新管理命令
"""
import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import logging

logger = logging.getLogger('article_commands')

class ArticleCommands(commands.Cog):
    """官方文章更新相關命令"""

    def __init__(self, bot):
        self.bot = bot
        self.article_monitor = None
        self.monitoring_task = None
        self.monitored_channels = []

    async def cog_load(self):
        """Cog 載入時初始化官方文章更新器"""
        from services.article_monitor import ArticleMonitor
        self.article_monitor = ArticleMonitor(self.bot)
        logger.info("官方文章更新器已初始化")

    @app_commands.command(name="article_manager", description="官方文章更新管理中心")
    async def article_manager(self, interaction: discord.Interaction):
        """官方文章更新管理中心 - 統一入口"""
        from utils import check_guild

        # 檢查權限
        if not await check_guild(interaction, admin_only=True):
            return

        # 創建功能選擇選單
        select_menu = discord.ui.Select(
            placeholder="選擇要執行的功能...",
            options=[
                discord.SelectOption(
                    label="🚀 開始監控",
                    value="start",
                    description="開始官方文章更新並自動發送到此頻道",
                    emoji="🚀"
                ),
                discord.SelectOption(
                    label="⏹️ 停止監控",
                    value="stop",
                    description="停止官方文章更新",
                    emoji="⏹️"
                ),
                discord.SelectOption(
                    label="📊 監控狀態",
                    value="status",
                    description="查看官方文章更新狀態",
                    emoji="📊"
                ),
                discord.SelectOption(
                    label="🧪 測試功能",
                    value="test",
                    description="測試從爬蟲 API 取得文章",
                    emoji="🧪"
                )
            ]
        )

        async def select_callback(select_interaction: discord.Interaction):
            action = select_menu.values[0]

            if action == "start":
                await self._handle_start_monitor(select_interaction)
            elif action == "stop":
                await self._handle_stop_monitor(select_interaction)
            elif action == "status":
                await self._handle_monitor_status(select_interaction)
            elif action == "test":
                await self._handle_test_fetch(select_interaction)

        select_menu.callback = select_callback

        view = discord.ui.View()
        view.add_item(select_menu)

        embed = discord.Embed(
            title="📰 官方文章更新管理中心",
            description="請選擇要執行的功能：",
            color=discord.Color.blue()
        )
        embed.add_field(
            name="🚀 開始監控",
            value="在此頻道開始官方文章更新",
            inline=True
        )
        embed.add_field(
            name="⏹️ 停止監控",
            value="停止正在運行的文章監控",
            inline=True
        )
        embed.add_field(
            name="📊 監控狀態",
            value="查看當前監控狀態和統計",
            inline=True
        )
        embed.add_field(
            name="🧪 測試功能",
            value="測試 API 連接和文章取得",
            inline=True
        )

        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    async def _handle_start_monitor(self, interaction: discord.Interaction):
        """處理開始監控功能"""
        # 創建間隔設定選單
        interval_select = discord.ui.Select(
            placeholder="選擇檢查間隔...",
            options=[
                discord.SelectOption(label="1分鐘", value="60", description="快速檢查（測試用）"),
                discord.SelectOption(label="3分鐘", value="180", description="預設間隔（推薦）"),
                discord.SelectOption(label="5分鐘", value="300", description="標準間隔"),
                discord.SelectOption(label="10分鐘", value="600", description="較慢間隔"),
                discord.SelectOption(label="30分鐘", value="1800", description="低頻檢查")
            ]
        )

        async def interval_callback(interval_interaction: discord.Interaction):
            interval = int(interval_select.values[0])
            channel_id = interaction.channel.id

            # 檢查是否已經在監控
            if self.monitoring_task and not self.monitoring_task.done():
                await interval_interaction.response.send_message(
                    "❌ 官方文章更新已經在運行中！",
                    ephemeral=True
                )
                return

            # 添加頻道到監控列表
            if channel_id not in self.monitored_channels:
                self.monitored_channels.append(channel_id)

            try:
                # 啟動監控任務
                self.monitoring_task = asyncio.create_task(
                    self.article_monitor.start_monitoring(
                        channel_ids=self.monitored_channels,
                        check_interval=interval
                    )
                )

                await interval_interaction.response.send_message(
                    f"✅ 已開始官方文章更新！\n"
                    f"📍 更新頻道：<#{channel_id}>\n"
                    f"⏰ 檢查間隔：{interval} 秒\n"
                    f"📊 將自動發送最近3天的新文章",
                    ephemeral=False
                )

                logger.info(f"開始官方文章更新，頻道 ID: {channel_id}，間隔: {interval} 秒")

            except Exception as e:
                logger.error(f"啟動官方文章更新失敗: {e}")
                await interval_interaction.response.send_message(
                    f"❌ 啟動官方文章更新失敗：{str(e)}",
                    ephemeral=True
                )

        interval_select.callback = interval_callback
        interval_view = discord.ui.View()
        interval_view.add_item(interval_select)

        embed = discord.Embed(
            title="⏰ 設定檢查間隔",
            description="請選擇文章檢查的時間間隔：",
            color=discord.Color.green()
        )
        await interaction.response.edit_message(embed=embed, view=interval_view)

    async def _handle_stop_monitor(self, interaction: discord.Interaction):
        """處理停止監控功能"""
        if not self.monitoring_task or self.monitoring_task.done():
            await interaction.response.send_message(
                "❌ 官方文章更新沒有在運行",
                ephemeral=True
            )
            return

        try:
            # 取消監控任務
            self.monitoring_task.cancel()
            self.monitored_channels.clear()

            await interaction.response.send_message(
                "✅ 已停止官方文章更新！",
                ephemeral=False
            )

            logger.info("已停止官方文章更新")

        except Exception as e:
            logger.error(f"停止官方文章更新失敗: {e}")
            await interaction.response.send_message(
                f"❌ 停止官方文章更新失敗：{str(e)}",
                ephemeral=True
            )

    async def _handle_monitor_status(self, interaction: discord.Interaction):
        """處理監控狀態查詢功能"""
        if not self.monitoring_task or self.monitoring_task.done():
            embed = discord.Embed(
                title="📊 官方文章更新狀態",
                description="❌ 未啟動更新",
                color=discord.Color.red()
            )
            embed.add_field(
                name="💡 提示",
                value="使用 `/article_manager` 開始更新",
                inline=False
            )
        else:
            channels_text = "\n".join([f"<#{channel_id}>" for channel_id in self.monitored_channels])
            embed = discord.Embed(
                title="📊 官方文章更新狀態",
                description="✅ 更新中",
                color=discord.Color.green()
            )
            embed.add_field(
                name="📍 更新頻道",
                value=channels_text if channels_text else "無",
                inline=False
            )
            embed.add_field(
                name="📝 已發送文章數",
                value=str(len(self.article_monitor.sent_articles) if self.article_monitor else 0),
                inline=True
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def _handle_test_fetch(self, interaction: discord.Interaction):
        """處理測試文章取得功能"""
        await interaction.response.defer(ephemeral=True)

        try:
            if not self.article_monitor:
                await interaction.followup.send("❌ 官方文章更新器未初始化", ephemeral=True)
                return

            # 測試取得文章
            articles = await self.article_monitor.fetch_recent_articles(days=3)

            if not articles:
                embed = discord.Embed(
                    title="🧪 測試結果",
                    description="❌ 沒有取得任何文章",
                    color=discord.Color.red()
                )
            else:
                embed = discord.Embed(
                    title="🧪 測試結果",
                    description=f"✅ 成功取得 {len(articles)} 篇文章",
                    color=discord.Color.green()
                )

                # 顯示前3篇文章的標題
                article_list = ""
                for i, article in enumerate(articles[:3]):
                    article_list += f"{i+1}. {article['article_title'][:50]}...\n"

                if len(articles) > 3:
                    article_list += f"... 還有 {len(articles) - 3} 篇文章"

                embed.add_field(
                    name="📰 文章預覽",
                    value=article_list if article_list else "無文章內容",
                    inline=False
                )

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"測試文章取得失敗: {e}")
            embed = discord.Embed(
                title="🧪 測試結果",
                description=f"❌ 測試失敗：{str(e)}",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

async def setup(bot):
    """載入 Cog"""
    await bot.add_cog(ArticleCommands(bot))
