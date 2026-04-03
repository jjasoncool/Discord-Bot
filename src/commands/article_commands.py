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


class ArticleApiTestView(discord.ui.View):
    """API 測試選單 view"""

    def __init__(self, cog: "ArticleCommands"):
        super().__init__(timeout=180)
        self.cog = cog

    @discord.ui.select(
        placeholder="選擇要測試的 API...",
        custom_id="article_api_test_select",
        options=[
            discord.SelectOption(label="主要文章 API", value="article", description="測試 /api/articles/discord"),
            discord.SelectOption(label="FB API", value="fb", description="測試 /api/fb_posts/recent"),
            discord.SelectOption(label="PTT API", value="ptt", description="測試 /api/ptt_posts/recent"),
            discord.SelectOption(label="全部 API", value="all", description="一次測試全部 API"),
        ]
    )
    async def api_test_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        target = select.values[0]
        await self.cog._run_api_test(interaction, target=target)

class ArticleCommands(commands.Cog):
    """官方文章更新相關命令"""

    def __init__(self, bot):
        self.bot = bot
        self.article_monitor = None
        self.monitoring_task = None
        self.fb_monitoring_task = None
        self.ptt_monitoring_task = None
        self._bahamut_sync_started_at = None  # 批次同步開始時間
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
        embed = discord.Embed(
            title="🧪 選擇要測試的 API",
            description="請選擇單一 API 或全部 API 進行測試。",
            color=discord.Color.blurple()
        )
        await interaction.response.edit_message(embed=embed, view=ArticleApiTestView(self))

    async def _run_api_test(self, interaction: discord.Interaction, target: str = "all"):
        """實際執行 API 測試"""
        await interaction.response.defer(ephemeral=True)

        try:
            if not self.article_monitor:
                await safe_send_interaction_message(interaction, "❌ 官方文章更新器未初始化", ephemeral=True)
                return

            base_url = self.article_monitor.scraper_api_url.rstrip("/")
            endpoint_results: list[tuple[str, bool, str]] = []
            latest_article_json_preview: str | None = None
            latest_article_file: discord.File | None = None
            latest_fb_json_preview: str | None = None
            latest_fb_file: discord.File | None = None
            latest_ptt_json_preview: str | None = None
            latest_ptt_file: discord.File | None = None

            def _build_json_preview_and_file(payload: dict, filename: str):
                pretty_json = json.dumps(payload, ensure_ascii=False, indent=2)
                json_bytes = pretty_json.encode("utf-8")
                max_discord_file_bytes = 7_500_000
                file_obj = None
                if len(json_bytes) <= max_discord_file_bytes:
                    file_obj = discord.File(io.BytesIO(json_bytes), filename=filename)

                max_preview_chars = 900
                preview = (
                    pretty_json[:max_preview_chars] + "\n...（已截斷）"
                    if len(pretty_json) > max_preview_chars
                    else pretty_json
                )
                return preview, file_obj

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

                # 2) 健康正常才測主要文章 / FB / PTT 端點
                if health_ok:
                    api_targets = [
                        ("主要文章 API", "/api/articles/discord", {"days": 30, "limit": 1, "order": "desc"}, "articles", "latest_article.json"),
                        ("FB API", "/api/fb_posts/recent", {"days": 30, "limit": 1}, "posts", "latest_fb_post.json"),
                        ("PTT API", "/api/ptt_posts/recent", {"days": 30, "limit": 1, "order": "desc"}, "posts", "latest_ptt_post.json"),
                    ]

                    target_map = {
                        "article": {"主要文章 API"},
                        "fb": {"FB API"},
                        "ptt": {"PTT API"},
                        "all": {"主要文章 API", "FB API", "PTT API"},
                    }
                    selected_labels = target_map.get(target, target_map["all"])

                    for label, endpoint, params, list_key, filename in api_targets:
                        if label not in selected_labels:
                            continue
                        try:
                            async with session.get(f"{base_url}{endpoint}", params=params) as response:
                                if response.status != 200:
                                    endpoint_results.append((label, False, f"HTTP {response.status}"))
                                    continue

                                data = await response.json(content_type=None)
                                if not (isinstance(data, dict) and data.get("success")):
                                    endpoint_results.append((label, False, "API success=false"))
                                    continue

                                items = data.get(list_key) or []
                                endpoint_results.append((label, True, f"{list_key}={len(items)}"))

                                if items:
                                    preview, file_obj = _build_json_preview_and_file(items[-1], filename)
                                    if label == "主要文章 API":
                                        latest_article_json_preview, latest_article_file = preview, file_obj
                                    elif label == "FB API":
                                        latest_fb_json_preview, latest_fb_file = preview, file_obj
                                    elif label == "PTT API":
                                        latest_ptt_json_preview, latest_ptt_file = preview, file_obj
                        except Exception as exc:
                            endpoint_results.append((label, False, str(exc)))
                else:
                    if target in ("article", "all"):
                        endpoint_results.append(("主要文章 API", False, "略過（健康檢查未通過）"))
                    if target in ("fb", "all"):
                        endpoint_results.append(("FB API", False, "略過（健康檢查未通過）"))
                    if target in ("ptt", "all"):
                        endpoint_results.append(("PTT API", False, "略過（健康檢查未通過）"))

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
                    name="📰 主要文章 API 最後一筆",
                    value=f"```json\n{latest_article_json_preview}\n```",
                    inline=False,
                )

            if latest_fb_json_preview:
                embed.add_field(
                    name="📘 FB API 最後一筆",
                    value=f"```json\n{latest_fb_json_preview}\n```",
                    inline=False,
                )

            if latest_ptt_json_preview:
                embed.add_field(
                    name="🧵 PTT API 最後一筆",
                    value=f"```json\n{latest_ptt_json_preview}\n```",
                    inline=False,
                )

            if latest_article_file is None and latest_article_json_preview:
                embed.add_field(
                    name="📎 主要文章 API JSON 檔案",
                    value="⚠️ JSON 太大，已略過附件，請看上方預覽。",
                    inline=False,
                )

            if latest_fb_file is None and latest_fb_json_preview:
                embed.add_field(
                    name="📎 FB API JSON 檔案",
                    value="⚠️ JSON 太大，已略過附件，請看上方預覽。",
                    inline=False,
                )

            if latest_ptt_file is None and latest_ptt_json_preview:
                embed.add_field(
                    name="📎 PTT API JSON 檔案",
                    value="⚠️ JSON 太大，已略過附件，請看上方預覽。",
                    inline=False,
                )

            files = [f for f in [latest_article_file, latest_fb_file, latest_ptt_file] if f is not None]
            await safe_send_interaction_message(
                interaction,
                embed=embed,
                ephemeral=True,
                files=files if files else None,
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

    # ── 巴哈文章指令 ──

    @app_commands.command(name="get_baha_post", description="取得巴哈討論串並發送到論壇頻道（不填 ID 則同步最近 3 天）")
    @app_commands.describe(
        post_id="討論串 ID（snA），不填則同步最近 3 天所有文章",
        board_id="看板 ID（預設 74934）",
    )
    async def get_baha_post(
        self,
        interaction: discord.Interaction,
        post_id: str = None,
        board_id: str = "74934",
    ):
        """從 Scraper API 取得巴哈討論串並發送到論壇頻道。"""
        from utils.utils import check_guild
        if not await check_guild(interaction, admin_only=True):
            return

        await interaction.response.defer(ephemeral=True)

        from utils.utils import ChannelConfig
        forum_channel_id = ChannelConfig.load_config(caller="get_baha_post").get("forum_article_channel_id")
        if not forum_channel_id:
            await interaction.followup.send("❌ config.json 中沒有設定 forum_article_channel_id", ephemeral=True)
            return

        from services.bahamut_monitor import BahamutMonitor
        monitor = BahamutMonitor(self.bot)

        if post_id:
            # 單篇模式（通常快，直接等結果）
            await interaction.followup.send(
                f"⏳ 正在處理巴哈討論串 post_id={post_id}...",
                ephemeral=True,
            )
            state = await monitor.test_send_single_thread(
                forum_channel_id=forum_channel_id,
                board_id=board_id,
                post_id=post_id,
            )
            if state:
                posts_count = len(state.get("posts", {}))
                await interaction.followup.send(
                    f"✅ 巴哈討論串已發送！\n"
                    f"Thread ID: {state.get('thread_id')}\n"
                    f"文章數（含主文+回覆）: {posts_count}",
                    ephemeral=True,
                )
            else:
                await interaction.followup.send(
                    f"❌ 發送失敗或無變化，請查看日誌。board_id={board_id}, post_id={post_id}",
                    ephemeral=True,
                )
        else:
            # 批次模式：檢查是否已在執行中
            if self._bahamut_sync_started_at is not None:
                from datetime import datetime
                elapsed = (datetime.now() - self._bahamut_sync_started_at).total_seconds()
                minutes = int(elapsed // 60)
                seconds = int(elapsed % 60)
                await interaction.followup.send(
                    f"⚠️ 巴哈批次同步已在執行中（已執行 {minutes} 分 {seconds} 秒），請等待完成。",
                    ephemeral=True,
                )
                return

            threads = await monitor.fetch_recent_threads(days=3, limit=50, board_id=board_id)
            if not threads:
                await interaction.followup.send("ℹ️ 沒有找到最近 3 天的巴哈討論串", ephemeral=True)
                return

            await interaction.followup.send(
                f"⏳ 開始背景同步 {len(threads)} 個巴哈討論串，完成後會在論壇頻道看到結果。",
                ephemeral=True,
            )

            cog = self  # 給 closure 用

            async def _batch_sync():
                from datetime import datetime
                cog._bahamut_sync_started_at = datetime.now()
                try:
                    # 每篇文章各自背景處理，不互相阻塞
                    tasks = []
                    for thread_data in threads:
                        tasks.append(asyncio.create_task(
                            monitor.send_bahamut_thread_to_forum(forum_channel_id, thread_data)
                        ))
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    processed = sum(1 for r in results if r and not isinstance(r, Exception))
                    errors = sum(1 for r in results if isinstance(r, Exception))
                    logger.info("巴哈批次同步完成: 掃描=%s 處理=%s 失敗=%s", len(threads), processed, errors)
                finally:
                    cog._bahamut_sync_started_at = None

            asyncio.create_task(_batch_sync())


async def setup(bot):
    """載入 Cog"""
    await bot.add_cog(ArticleCommands(bot))
