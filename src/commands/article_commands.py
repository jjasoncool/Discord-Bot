"""
官方文章更新管理命令
"""
import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import logging
import aiohttp
import json
import io
from typing import Optional
from utils.utils import safe_send_interaction_message

logger = logging.getLogger('discord_bot')


class ArticleManagerView(discord.ui.View):
    """/article_manager 主入口 persistent view"""

    def __init__(self, cog: "ArticleCommands"):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.select(
        placeholder="選擇要執行的功能...",
        custom_id="article_manager_action_select",
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
                label="🧪 測試 API",
                value="test",
                description="測試 src/scraper API 服務連線與回應",
                emoji="🧪"
            )
        ]
    )
    async def article_manager_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        action = select.values[0]
        logger.info(
            "interaction_start source=article_manager_action custom_id=%s action=%s user_id=%s guild_id=%s channel_id=%s",
            getattr(select, "custom_id", None),
            action,
            interaction.user.id if interaction.user else None,
            interaction.guild.id if interaction.guild else None,
            interaction.channel.id if interaction.channel else None,
        )

        if action == "start":
            await self.cog._handle_start_monitor(interaction)
        elif action == "stop":
            await self.cog._handle_stop_monitor(interaction)
        elif action == "status":
            await self.cog._handle_monitor_status(interaction)
        elif action == "test":
            await self.cog._handle_test_fetch(interaction)

class ArticleCommands(commands.Cog):
    """官方文章更新相關命令"""

    def __init__(self, bot):
        self.bot = bot
        self.article_monitor = None
        self.monitoring_task = None
        self.fb_monitoring_task = None
        self.monitored_channels = []

    async def cog_load(self):
        """Cog 載入時初始化官方文章更新器"""
        from services.article_monitor import ArticleMonitor
        self.article_monitor = ArticleMonitor(self.bot)
        self.bot.add_view(ArticleManagerView(self))
        logger.info("已註冊 ArticleManagerView persistent view")
        logger.info("官方文章更新器已初始化")

    @app_commands.command(name="article_manager", description="官方文章更新管理中心")
    async def article_manager(self, interaction: discord.Interaction):
        """官方文章更新管理中心 - 統一入口"""
        from utils.utils import check_guild

        # 檢查權限
        if not await check_guild(interaction, admin_only=True):
            return

        view = ArticleManagerView(self)

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
            name="🧪 測試 API",
            value="測試 src/scraper API 服務健康與資料端點",
            inline=True
        )

        await safe_send_interaction_message(interaction, embed=embed, view=view, ephemeral=True)

    async def _handle_start_monitor(self, interaction: discord.Interaction):
        """處理開始監控功能"""
        # 創建間隔設定選單
        interval_select = discord.ui.Select(
            placeholder="選擇檢查間隔...",
            custom_id="article_manager_interval_select",
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
            channel_id = interval_interaction.channel.id if interval_interaction.channel else None
            if channel_id is None:
                await safe_send_interaction_message(
                    interval_interaction,
                    "❌ 找不到目前頻道，請稍後再試。",
                    ephemeral=True
                )
                return
            logger.info(
                "interaction_start source=article_manager_interval custom_id=%s interval=%s user_id=%s guild_id=%s channel_id=%s",
                getattr(interval_select, "custom_id", None),
                interval,
                interval_interaction.user.id if interval_interaction.user else None,
                interval_interaction.guild.id if interval_interaction.guild else None,
                interval_interaction.channel.id if interval_interaction.channel else None,
            )

            # 檢查是否已經在監控
            if self.monitoring_task and not self.monitoring_task.done():
                await safe_send_interaction_message(
                    interval_interaction,
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

                await safe_send_interaction_message(
                    interval_interaction,
                    f"✅ 已開始官方文章更新！\n"
                    f"📍 更新頻道：<#{channel_id}>\n"
                    f"⏰ 檢查間隔：{interval} 秒\n"
                    f"📊 將自動發送最近3天的新文章",
                    ephemeral=False
                )

                logger.info(f"開始官方文章更新，頻道 ID: {channel_id}，間隔: {interval} 秒")

            except Exception as e:
                logger.error(f"啟動官方文章更新失敗: {e}")
                await safe_send_interaction_message(
                    interval_interaction,
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
            await safe_send_interaction_message(
                interaction,
                "❌ 官方文章更新沒有在運行",
                ephemeral=True
            )
            return

        try:
            # 取消監控任務
            self.monitoring_task.cancel()
            self.monitored_channels.clear()

            await safe_send_interaction_message(
                interaction,
                "✅ 已停止官方文章更新！",
                ephemeral=False
            )

            logger.info("已停止官方文章更新")

        except Exception as e:
            logger.error(f"停止官方文章更新失敗: {e}")
            await safe_send_interaction_message(
                interaction,
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
            embed.add_field(
                name="🔧 HTML 解析器",
                value="html2text + BeautifulSoup",
                inline=True
            )

        await safe_send_interaction_message(interaction, embed=embed, ephemeral=True)

    async def _handle_test_fetch(self, interaction: discord.Interaction):
        """處理測試 src/scraper API 服務功能"""
        await interaction.response.defer(ephemeral=True)

        try:
            if not self.article_monitor:
                await safe_send_interaction_message(interaction, "❌ 官方文章更新器未初始化", ephemeral=True)
                return

            base_url = self.article_monitor.scraper_api_url.rstrip("/")
            endpoint_results: list[tuple[str, bool, str]] = []
            latest_article_json_preview: str | None = None
            latest_article_file: discord.File | None = None

            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                # 1) 先做健康檢查
                health_ok = False
                health_url = f"{base_url}/health"
                try:
                    async with session.get(health_url) as response:
                        if response.status != 200:
                            endpoint_results.append(("健康檢查", False, f"HTTP {response.status}"))
                        else:
                            health_data = await response.json(content_type=None)
                            health_status = str(health_data.get("status", "unknown"))
                            health_ok = health_status.lower() in {"healthy", "ok"}
                            endpoint_results.append(("健康檢查", health_ok, f"status={health_status}"))
                except Exception as exc:
                    endpoint_results.append(("健康檢查", False, str(exc)))

                # 2) 健康正常才測文章端點，並抓最後一筆
                if health_ok:
                    article_url = f"{base_url}/api/articles/discord"
                    params = {"days": 30, "limit": 1, "order": "desc"}
                    try:
                        async with session.get(article_url, params=params) as response:
                            if response.status != 200:
                                endpoint_results.append(("Discord 文章端點", False, f"HTTP {response.status}"))
                            else:
                                data = await response.json(content_type=None)
                                if not (isinstance(data, dict) and data.get("success")):
                                    endpoint_results.append(("Discord 文章端點", False, "API success=false"))
                                else:
                                    articles = data.get("articles") or []
                                    endpoint_results.append(("Discord 文章端點", True, f"articles={len(articles)}"))

                                    if articles:
                                        latest_article = articles[-1]
                                        pretty_json = json.dumps(latest_article, ensure_ascii=False, indent=2)

                                        json_bytes = pretty_json.encode("utf-8")
                                        max_discord_file_bytes = 7_500_000
                                        if len(json_bytes) <= max_discord_file_bytes:
                                            latest_article_file = discord.File(
                                                io.BytesIO(json_bytes),
                                                filename="latest_article.json",
                                            )

                                        max_preview_chars = 900
                                        latest_article_json_preview = (
                                            pretty_json[:max_preview_chars] + "\n...（已截斷）"
                                            if len(pretty_json) > max_preview_chars
                                            else pretty_json
                                        )
                    except Exception as exc:
                        endpoint_results.append(("Discord 文章端點", False, str(exc)))
                else:
                    endpoint_results.append(("Discord 文章端點", False, "略過（健康檢查未通過）"))

            passed_count = sum(1 for _, ok, _ in endpoint_results if ok)
            all_passed = passed_count == len(endpoint_results)

            embed = discord.Embed(
                title="🧪 src/scraper API 測試結果",
                description=(
                    f"✅ 全部通過（{passed_count}/{len(endpoint_results)}）"
                    if all_passed
                    else f"⚠️ 部分失敗（{passed_count}/{len(endpoint_results)}）"
                ),
                color=discord.Color.green() if all_passed else discord.Color.orange(),
            )

            for label, ok, detail in endpoint_results:
                embed.add_field(
                    name=f"{'✅' if ok else '❌'} {label}",
                    value=detail[:1024],
                    inline=False,
                )

            if latest_article_json_preview:
                embed.add_field(
                    name="📰 最後一筆文章（JSON pretty）",
                    value=f"```json\n{latest_article_json_preview}\n```",
                    inline=False,
                )

            if latest_article_file is None and latest_article_json_preview:
                embed.add_field(
                    name="📎 JSON 檔案",
                    value="⚠️ JSON 太大，已略過附件，請看上方預覽。",
                    inline=False,
                )

            await safe_send_interaction_message(
                interaction,
                embed=embed,
                ephemeral=True,
                file=latest_article_file,
            )

        except Exception as e:
            logger.error(f"測試文章取得失敗: {e}")
            embed = discord.Embed(
                title="🧪 API 測試結果",
                description=f"❌ 測試失敗：{str(e)}",
                color=discord.Color.red()
            )
            await safe_send_interaction_message(interaction, embed=embed, ephemeral=True)

    @staticmethod
    def _parse_positive_int(raw_id: str) -> Optional[int]:
        """將字串 ID 解析為正整數，失敗則回傳 None。"""
        try:
            parsed = int(raw_id)
            return parsed if parsed > 0 else None
        except (TypeError, ValueError):
            return None

    @app_commands.command(name="resend_article", description="根據 ID 重新發送文章或 FB 貼文")
    @app_commands.describe(
        id="要重新發送的內容 ID",
        type="內容類型 (article 或 fb)"
    )
    @app_commands.choices(type=[
        app_commands.Choice(name="article", value="article"),
        app_commands.Choice(name="fb", value="fb"),
    ])
    async def resend_article(self, interaction: discord.Interaction, id: str, type: str = "article"):
        """根據 ID 重新發送文章或 FB 貼文到監控的頻道，用於測試"""
        from utils.utils import check_guild

        # 檢查權限
        if not await check_guild(interaction, admin_only=True):
            return

        await interaction.response.defer(ephemeral=True)

        try:
            if not self.article_monitor:
                await safe_send_interaction_message(interaction, "❌ 官方文章更新器未初始化", ephemeral=True)
                return

            # 檢查是否有監控的頻道
            if not self.monitored_channels:
                await safe_send_interaction_message(interaction, "❌ 沒有設定監控頻道，請先使用 `/article_manager` 開始監控。", ephemeral=True)
                return

            content_type = type.lower()
            logger.info(f"[RESEND_ROUTE] 收到 /resend_article 請求: id={id}, type={content_type}")
            if content_type not in ["article", "fb", "fb_post"]:
                await safe_send_interaction_message(interaction, "❌ 內容類型必須是 'article' 或 'fb'", ephemeral=True)
                return

            # 根據類型處理
            if content_type == "article":
                # 處理文章
                article_id = self._parse_positive_int(id)
                if article_id is None:
                    await safe_send_interaction_message(interaction, "❌ 文章 ID 必須是數字", ephemeral=True)
                    return

                # 根據 ID 取得文章
                content = await self.article_monitor.fetch_article_by_id(article_id)
                content_name = f"文章 `{article_id}`"
                send_method = self.article_monitor.send_article_to_channel
                logger.info(f"[RESEND_ROUTE] 路由到文章流程: article_id={article_id}")

            else:  # fb or fb_post
                # 處理 FB 貼文
                fb_db_id = self._parse_positive_int(id)
                if fb_db_id is None:
                    await safe_send_interaction_message(interaction, "❌ FB 貼文 ID 必須是數字（資料庫 ID）", ephemeral=True)
                    return

                try:
                    content = await self.article_monitor.fetch_fb_post_by_id(fb_db_id)
                except Exception as e:
                    logger.error(f"獲取 FB 貼文資料庫 ID {fb_db_id} 失敗: {e}", exc_info=True)
                    await safe_send_interaction_message(interaction, "❌ 獲取 FB 貼文時發生錯誤，請稍後再試。", ephemeral=True)
                    return

                content_name = f"FB 貼文 `{fb_db_id}`"
                send_method = self.article_monitor.send_fb_post_to_channel
                logger.info(f"[RESEND_ROUTE] 路由到 FB 流程: fb_db_id={fb_db_id}")

            if not content:
                await safe_send_interaction_message(interaction, f"❌ 找不到 {content_name}。", ephemeral=True)
                return

            # 發送到所有監控的頻道
            success_count = 0
            for channel_id in self.monitored_channels:
                logger.info(f"[RESEND_ROUTE] 準備發送到頻道: channel_id={channel_id}, type={content_type}, id={id}")
                success = await send_method(channel_id, content)
                if success:
                    success_count += 1

            if success_count > 0:
                channel_names = []
                for channel_id in self.monitored_channels:
                    channel = self.bot.get_channel(channel_id)
                    channel_names.append(f"#{channel.name}" if channel else f"<#{channel_id}>")

                await safe_send_interaction_message(
                    interaction,
                    f"✅ 已成功將{content_name}重新發送到 {success_count} 個頻道：{', '.join(channel_names)}",
                    ephemeral=True
                )
            else:
                await safe_send_interaction_message(interaction, f"❌ 發送{content_name}到所有頻道都失敗，請查看日誌。", ephemeral=True)

        except Exception as e:
            logger.error(f"重新發送內容 {id} 失敗: {e}")
            await safe_send_interaction_message(interaction, f"❌ 重新發送內容時發生錯誤：{str(e)}", ephemeral=True)


async def setup(bot):
    """載入 Cog"""
    await bot.add_cog(ArticleCommands(bot))
