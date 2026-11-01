"""
官方文章更新管理命令
"""
import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import functools
import logging
import aiohttp
import json
import io
from typing import Optional
from dataclasses import dataclass, field
from utils.utils import ChannelConfig, safe_send_interaction_message
from utils.background_tasks import spawn, supervise

logger = logging.getLogger(__name__)


@dataclass
class ApiTestReport:
    """一次 API 測試的結果：每個端點過沒過、最後一筆的 JSON 預覽、附檔；主控台畫成文字、/article_manager 畫成 embed。"""

    target: str = "all"
    results: list[tuple[str, bool, str]] = field(default_factory=list)
    previews: dict[str, str] = field(default_factory=dict)
    files: list[discord.File] = field(default_factory=list)
    omitted: list[str] = field(default_factory=list)      # JSON 太大、沒附檔的端點
    error: Optional[str] = None                           # 測試本身出錯（監控器沒初始化、連不上）

    _ICONS = {"主要文章 API": "📰", "FB API": "📘", "PTT API": "🧵"}

    @property
    def passed(self) -> int:
        return sum(1 for _, ok, _ in self.results if ok)

    @property
    def all_passed(self) -> bool:
        return bool(self.results) and self.passed == len(self.results)

    def headline(self) -> str:
        if self.error:
            return f"❌ 測試失敗：{self.error}"
        return (f"✅ 全部通過（{self.passed}/{len(self.results)}）" if self.all_passed
                else f"⚠️ 部分失敗（{self.passed}/{len(self.results)}）")

    def embed(self) -> discord.Embed:
        colour = discord.Color.red() if self.error else discord.Color.green() if self.all_passed else discord.Color.orange()
        embed = discord.Embed(title="🧪 src/scraper API 測試結果", description=self.headline(), color=colour)
        for label, ok, detail in self.results:
            embed.add_field(name=f"{'✅' if ok else '❌'} {label}", value=detail[:1024], inline=False)
        for label, preview in self.previews.items():
            embed.add_field(name=f"{self._ICONS.get(label, '📄')} {label} 最後一筆", value=f"```json\n{preview}\n```", inline=False)
        for label in self.omitted:
            embed.add_field(name=f"📎 {label} JSON 檔案", value="⚠️ JSON 太大，已略過附件，請看上方預覽。", inline=False)
        return embed

    def text(self) -> str:
        lines = [self.headline()]
        lines += [f"{'✅' if ok else '❌'} **{label}**：{detail}" for label, ok, detail in self.results]
        for label, preview in self.previews.items():
            lines += ["", f"**{self._ICONS.get(label, '📄')} {label} 最後一筆**", f"```json\n{preview}\n```"]
        if self.previews:
            lines.append("-# 要 JSON 檔用 /article_manager 的「測試 API」。")
        return "\n".join(lines)


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
        self.fb_monitor = None
        self.ptt_monitor = None
        self.it_article_monitor = None
        self.monitoring_task = None
        self.ptt_monitoring_task = None
        self._bahamut_sync_started_at = None  # 批次同步開始時間
        self.monitored_channels = []

    async def cog_load(self):
        """Cog 載入時初始化各來源監控器"""
        from services.relay.article_monitor import ArticleMonitor
        from services.relay.fb_monitor import FBMonitor
        from services.relay.ptt_monitor import PTTMonitor
        from services.relay.it_article_monitor import ItArticleMonitor
        self.article_monitor = ArticleMonitor(self.bot)
        self.fb_monitor = FBMonitor(self.bot)
        self.ptt_monitor = PTTMonitor(self.bot)
        self.it_article_monitor = ItArticleMonitor(self.bot)
        self.bot.add_view(ArticleManagerView(self))
        logger.info("已註冊 ArticleManagerView persistent view")
        logger.info("官方文章更新器、FB 監控器、PTT 監控器、IT 文章監控器已初始化")

    @app_commands.command(name="article_manager", description="官方文章更新管理中心")
    async def article_manager(self, interaction: discord.Interaction):
        """官方文章更新管理中心 - 統一入口"""
        from utils.discord_members import require_access

        # 檢查權限
        if not await require_access(interaction, admin_only=True):
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
                self.monitoring_task = supervise(
                    lambda: self.article_monitor.start_monitoring(
                        channel_ids=self.monitored_channels,
                        check_interval=interval
                    ),
                    name="monitoring_task",
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

    def _monitor_running(self) -> bool:
        return bool(self.monitoring_task and not self.monitoring_task.done())

    def monitor_status_text(self) -> str:
        """監控現況的一段文字（主控台的「文章轉發」畫面直接顯示）。"""
        if not self._monitor_running():
            return "📊 官方文章更新：❌ 未啟動\n-# 到要發文的頻道用 /article_manager 開始"
        channels = "、".join(f"<#{cid}>" for cid in self.monitored_channels) or "無"
        return (f"📊 官方文章更新：✅ 更新中\n更新頻道：{channels}\n"
                f"狀態：{'運行中' if self.article_monitor else '未初始化'} · HTML 解析器：html2text + BeautifulSoup")

    async def _handle_monitor_status(self, interaction: discord.Interaction):
        """處理監控狀態查詢功能（/article_manager 那條路：embed）"""
        if not self._monitor_running():
            embed = discord.Embed(title="📊 官方文章更新狀態", description="❌ 未啟動更新", color=discord.Color.red())
            embed.add_field(name="💡 提示", value="使用 `/article_manager` 開始更新", inline=False)
        else:
            channels_text = "\n".join([f"<#{channel_id}>" for channel_id in self.monitored_channels])
            embed = discord.Embed(title="📊 官方文章更新狀態", description="✅ 更新中", color=discord.Color.green())
            embed.add_field(name="📍 更新頻道", value=channels_text if channels_text else "無", inline=False)
            embed.add_field(name="📝 狀態", value="運行中" if self.article_monitor else "未初始化", inline=True)
            embed.add_field(name="🔧 HTML 解析器", value="html2text + BeautifulSoup", inline=True)

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
        """實際執行 API 測試（/article_manager 那條路：embed 加 JSON 檔）"""
        await interaction.response.defer(ephemeral=True)
        report = await self.api_test_report(target)
        await safe_send_interaction_message(interaction, embed=report.embed(), ephemeral=True, files=report.files or None)

    async def api_test_report(self, target: str = "all") -> "ApiTestReport":
        """打 scraper 服務：健康檢查過了才測主要文章／FB／PTT 端點。回結果（主控台畫成文字、/article_manager 畫成 embed 加 JSON 檔）；
        任何錯都收進結果，不往外丟。"""
        report = ApiTestReport(target=target)
        if not self.article_monitor:
            report.error = "監控器未初始化"
            return report
        try:
            base_url = self.article_monitor.scraper_api_url.rstrip("/")

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
                            report.results.append(("健康檢查", False, f"HTTP {response.status}"))
                        else:
                            health_data = await response.json(content_type=None)
                            health_status = str(health_data.get("status", "unknown"))
                            health_ok = health_status.lower() in {"healthy", "ok"}
                            report.results.append(("健康檢查", health_ok, f"status={health_status}"))
                except Exception as exc:
                    report.results.append(("健康檢查", False, str(exc)))

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

                # 2) 健康正常才測主要文章 / FB / PTT 端點
                for label, endpoint, params, list_key, filename in api_targets:
                    if label not in selected_labels:
                        continue
                    if not health_ok:
                        report.results.append((label, False, "略過（健康檢查未通過）"))
                        continue
                    try:
                        async with session.get(f"{base_url}{endpoint}", params=params) as response:
                            if response.status != 200:
                                report.results.append((label, False, f"HTTP {response.status}"))
                                continue

                            data = await response.json(content_type=None)
                            if not (isinstance(data, dict) and data.get("success")):
                                report.results.append((label, False, "API success=false"))
                                continue

                            items = data.get(list_key) or []
                            report.results.append((label, True, f"{list_key}={len(items)}"))

                            if items:
                                preview, file_obj = _build_json_preview_and_file(items[-1], filename)
                                report.previews[label] = preview
                                if file_obj is None:
                                    report.omitted.append(label)
                                else:
                                    report.files.append(file_obj)
                    except Exception as exc:
                        report.results.append((label, False, str(exc)))
        except Exception as e:  # 邊界：測試本身出錯也要回報，呼叫端的畫面不能停在「處理中」
            logger.error(f"測試文章取得失敗: {e}")
            report.error = str(e)
        return report

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
        id="要重新發送的內容 ID（telegram 用 db id 或 footer 的 msg #id）",
        type="內容類型 (article / fb / it_article / telegram)"
    )
    @app_commands.choices(type=[
        app_commands.Choice(name="article", value="article"),
        app_commands.Choice(name="fb", value="fb"),
        app_commands.Choice(name="it_article", value="it_article"),
        app_commands.Choice(name="telegram", value="telegram"),
    ])
    async def resend_article(self, interaction: discord.Interaction, id: str, type: str = "article"):
        """根據 ID 重新發送文章或 FB 貼文到監控的頻道，用於測試"""
        from utils.discord_members import require_access

        # 檢查權限
        if not await require_access(interaction, admin_only=True):
            return
        await self.resend(interaction, id, type)

    async def resend(self, interaction: discord.Interaction, id: str, type: str = "article") -> None:
        """重送（/resend_article 那條路）：先 defer 再回結果；權限由呼叫端檢查（指令是管理員）。"""
        await interaction.response.defer(ephemeral=True)
        await safe_send_interaction_message(interaction, await self.resend_result(id, type), ephemeral=True)

    async def resend_result(self, id: str, type: str = "article") -> str:
        """重送的本體：回要給人看的結果一句（主控台寫在畫面上、指令回訊息）。目標頻道都從設定讀，私訊裡也能用；任何錯都包成一句。"""
        try:
            content_type = type.lower()
            logger.info(f"[RESEND_ROUTE] 收到重送請求: id={id}, type={content_type}")

            # Telegram：走 relay worker（重抓自訂表情 → 上傳 App Emoji → 重送），
            # 與 article/fb 流程完全不同，且不需要 article_monitor。
            if content_type == "telegram":
                return await self._resend_telegram(id)

            if not self.article_monitor:
                return "❌ 官方文章更新器未初始化"

            if content_type not in ["article", "fb", "fb_post", "it_article"]:
                return "❌ 內容類型必須是 'article'、'fb'、'it_article' 或 'telegram'"

            # 決定發送目標：it_article → 系統設備新知頻道；其餘 → article/fb 監控的頻道
            if content_type == "it_article":
                hw_id = ChannelConfig.load_config(caller="resend_it_article").get("hardware_news_channel_id")
                target_channels = [hw_id] if hw_id else []
                if not target_channels:
                    return "❌ 尚未設定「系統設備新知」頻道，請先用 `/server_manager` 指定。"
            else:
                target_channels = self.monitored_channels
                if not target_channels:
                    return "❌ 沒有設定監控頻道，請先使用 `/article_manager` 開始監控。"

            # 根據類型處理
            if content_type == "article":
                article_id = self._parse_positive_int(id)
                if article_id is None:
                    return "❌ 文章 ID 必須是數字"
                content = await self.article_monitor.fetch_article_by_id(article_id)
                content_name = f"文章 `{article_id}`"
                # 人明確要求重抓 → 允許解除「使用者刪掉活動」的墓碑並重建
                send_method = functools.partial(
                    self.article_monitor.send_article_to_channel, force_event_rebuild=True)
                logger.info(f"[RESEND_ROUTE] 路由到文章流程: article_id={article_id}")

            elif content_type in ("fb", "fb_post"):
                fb_db_id = self._parse_positive_int(id)
                if fb_db_id is None:
                    return "❌ FB 貼文 ID 必須是數字（資料庫 ID）"
                try:
                    content = await self.fb_monitor.fetch_fb_post_by_id(fb_db_id)
                except Exception as e:
                    logger.error(f"獲取 FB 貼文資料庫 ID {fb_db_id} 失敗: {e}", exc_info=True)
                    return "❌ 獲取 FB 貼文時發生錯誤，請稍後再試。"
                content_name = f"FB 貼文 `{fb_db_id}`"
                send_method = functools.partial(
                    self.fb_monitor.send_fb_post_to_channel, force_event_rebuild=True)
                logger.info(f"[RESEND_ROUTE] 路由到 FB 流程: fb_db_id={fb_db_id}")

            else:  # it_article（系統設備新知 / IT快訊）
                hkepc_id = self._parse_positive_int(id)
                if hkepc_id is None:
                    return "❌ IT 文章 ID 必須是數字（hkepc_id）"
                content = await self.it_article_monitor.fetch_it_article_by_id(hkepc_id)
                content_name = f"IT 文章 `{hkepc_id}`"
                send_method = self.it_article_monitor.send_to_channel
                logger.info(f"[RESEND_ROUTE] 路由到 IT 文章流程: hkepc_id={hkepc_id}")

            if not content:
                return f"❌ 找不到 {content_name}。"

            # 發送到目標頻道
            success_count = 0
            for channel_id in target_channels:
                logger.info(f"[RESEND_ROUTE] 準備發送到頻道: channel_id={channel_id}, type={content_type}, id={id}")
                success = await send_method(channel_id, content)
                if success:
                    success_count += 1

            if success_count > 0:
                channel_names = []
                for channel_id in target_channels:
                    channel = self.bot.get_channel(channel_id)
                    channel_names.append(f"#{channel.name}" if channel else f"<#{channel_id}>")
                return f"✅ 已成功將{content_name}重新發送到 {success_count} 個頻道：{', '.join(channel_names)}"
            return f"❌ 發送{content_name}到所有頻道都失敗，請查看日誌。"

        except Exception as e:  # 邊界：一次重送；結果要回給人看，不能讓畫面停在「處理中」
            logger.error(f"重新發送內容 {id} 失敗: {e}")
            return f"❌ 重新發送內容時發生錯誤：{str(e)}"

    async def _resend_telegram(self, id: str) -> str:
        """type:telegram：透過 relay worker 重抓自訂表情並重送一則 Telegram 訊息；回結果一句。"""
        worker = getattr(self.bot, "telegram_relay_worker", None)
        if worker is None or not getattr(worker, "running", False):
            return "❌ Telegram Relay Worker 尚未啟動。"

        msg_id = self._parse_positive_int(id)
        if msg_id is None:
            return "❌ Telegram ID 必須是數字（db id 或 msg id）。"

        logger.info(f"[RESEND_ROUTE] 路由到 Telegram 流程: id={msg_id}")
        try:
            result = await worker.resend_telegram_by_id(msg_id)
        except Exception as e:
            logger.error(f"重送 Telegram 訊息 {msg_id} 失敗: {e}", exc_info=True)
            return f"❌ 重送 Telegram 訊息時發生錯誤：{e}"

        if not result.get("ok"):
            reason = result.get("reason")
            if reason == "not_found":
                return f"❌ 找不到 Telegram 訊息 `{msg_id}`（db id 或 msg id 都查不到）。"
            if reason == "ambiguous":
                lines = [
                    f"• db#{c['id']} ← msg #{c['telegram_message_id']}（{c.get('chat_title') or c['telegram_chat_id']}）"
                    for c in result.get("candidates", [])
                ]
                return "⚠️ `{}` 跨頻道撞號，請改用 db id 重送：\n{}".format(msg_id, "\n".join(lines))
            return f"❌ 重送失敗：{reason}"

        refetch_note = "已即時重抓" if result.get("refetch_ok") else "重抓逾時/未變動（用現有 DB 內容）"
        return (
            f"✅ 已重送 Telegram 訊息 db#{result['db_id']}（msg #{result['telegram_message_id']}）"
            f"到 {result['sent']} 個頻道。\n"
            f"自訂表情：找到 {result['emoji_found']} 個、成功轉出 {result['emoji_rendered']} 個；{refetch_note}。"
        )

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
        from utils.discord_members import require_access
        if not await require_access(interaction, admin_only=True):
            return
        await self.baha_sync(interaction, post_id, board_id)

    async def baha_sync(self, interaction: discord.Interaction, post_id: Optional[str] = None,
                        board_id: str = "74934") -> None:
        """巴哈同步（/get_baha_post 那條路）：先 defer 再回結果；權限由呼叫端檢查。"""
        await interaction.response.defer(ephemeral=True)
        await interaction.followup.send(await self.baha_sync_result(post_id, board_id), ephemeral=True)

    async def baha_sync_result(self, post_id: Optional[str] = None, board_id: str = "74934") -> str:
        """巴哈同步的本體（單篇或最近 3 天）：單篇直接等結果；批次在背景跑、先回「開始了」。論壇頻道從設定讀，私訊裡也能用。"""
        forum_channel_id = ChannelConfig.load_config(caller="get_baha_post").get("forum_article_channel_id")
        if not forum_channel_id:
            return "❌ config.json 中沒有設定 forum_article_channel_id"

        from services.relay.bahamut_monitor import BahamutMonitor
        monitor = BahamutMonitor(self.bot)

        if post_id:
            # 單篇模式（通常快，直接等結果）
            state = await monitor.test_send_single_thread(
                forum_channel_id=forum_channel_id,
                board_id=board_id,
                post_id=post_id,
            )
            if state:
                posts_count = len(state.get("posts", {}))
                return (f"✅ 巴哈討論串已發送！\n"
                        f"Thread ID: {state.get('thread_id')}\n"
                        f"文章數（含主文+回覆）: {posts_count}")
            return f"❌ 發送失敗或無變化，請查看日誌。board_id={board_id}, post_id={post_id}"

        # 批次模式：檢查是否已在執行中
        if self._bahamut_sync_started_at is not None:
            from datetime import datetime
            elapsed = (datetime.now() - self._bahamut_sync_started_at).total_seconds()
            minutes = int(elapsed // 60)
            seconds = int(elapsed % 60)
            return f"⚠️ 巴哈批次同步已在執行中（已執行 {minutes} 分 {seconds} 秒），請等待完成。"

        threads = await monitor.fetch_recent_threads(days=3, limit=50, board_id=board_id)
        if not threads:
            return "ℹ️ 沒有找到最近 3 天的巴哈討論串"

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

        spawn(_batch_sync(), name="巴哈批次同步")
        return f"⏳ 開始背景同步 {len(threads)} 個巴哈討論串，完成後會在論壇頻道看到結果。"


async def setup(bot):
    """載入 Cog"""
    await bot.add_cog(ArticleCommands(bot))
