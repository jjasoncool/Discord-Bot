"""週期活動提醒（深塔／海墟／終焉矩陣）：排程發提醒、面板置底、自助訂閱身份組。

- 提醒頻道由 /server_manager 綁定（channel_registry「週期提醒頻道」），綁定當下自動
  建立身份組並發出訂閱面板；未綁定時整個功能靜默。
- 面板置底走共用的 `utils.panel_bump.PanelBumper`：發完提醒、或頻道裡有人講話，就立即
  「刪舊發新」頂到最下面；提醒本身不附按鈕。
- 何時該發、文案怎麼寫在 `services/events/periodic_reminder.py`；已發過的記在 StateDB
  `sent_content`（source=periodic_reminder），重啟或補發都不會重複。
- 矩陣的時刻跟著版本走：每輪排程都重讀官方公告（`VersionDateResolver.update_starts()`），
  版本延期或提前公告一出來，提醒與面板日期就跟著變；面板內容一有變化就自動重發。
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Optional

import discord
from discord.ext import commands

from services.state_db import get_shared_state_db
from services.events.event_scheduler import VersionDateResolver
from services.events.event_time_parser import SERVER_TZ
from services.events.periodic_reminder import (
    SENT_SOURCE,
    KIND_ENDING,
    Reminder,
    build_panel_description,
    build_panel_title,
    build_reminder_text,
    due_reminders,
    format_moment,
    upcoming_reminders,
)
from sys_settings.periodic_reminder_settings import PeriodicReminderSettings, VersionStageItem
from utils.panel_bump import PanelBumper, load_runtime, update_runtime
from utils.utils import ChannelConfig

logger = logging.getLogger(__name__)

CUSTOM_ID_SUBSCRIBE = "periodic_reminder:subscribe"
CUSTOM_ID_UNSUBSCRIBE = "periodic_reminder:unsubscribe"

#: 排程最長睡多久就醒來重算一次（避免主機休眠、時鐘校正後錯過）
_MAX_SLEEP_SECONDS = 3600


class ReminderPanelView(discord.ui.View):
    """訂閱面板的兩顆按鈕（persistent：timeout=None + 固定 custom_id，重啟後仍可按）。"""

    def __init__(self, cog: "PeriodicReminderCommands"):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="訂閱", emoji="🔔", style=discord.ButtonStyle.success,
                       custom_id=CUSTOM_ID_SUBSCRIBE)
    async def subscribe(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.handle_subscription(interaction, subscribe=True)

    @discord.ui.button(label="取消訂閱", emoji="🔕", style=discord.ButtonStyle.secondary,
                       custom_id=CUSTOM_ID_UNSUBSCRIBE)
    async def unsubscribe(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.handle_subscription(interaction, subscribe=False)


class PeriodicReminderCommands(commands.Cog):
    """週期活動提醒（沒有 slash 指令，入口是 /server_manager 綁頻道與面板按鈕）"""

    def __init__(self, bot: commands.Bot, settings: Optional[PeriodicReminderSettings] = None):
        self.bot = bot
        self.settings = settings or PeriodicReminderSettings()
        self._role_lock = asyncio.Lock()
        self._task: Optional[asyncio.Task] = None
        #: 已知的版本更新維護開始時刻（每輪排程從官方公告重讀）
        self._update_starts: list[datetime] = []
        self.panel = PanelBumper(self.settings.runtime_path, self._send_panel,
                                 custom_ids=(CUSTOM_ID_SUBSCRIBE, CUSTOM_ID_UNSUBSCRIBE))

    async def cog_load(self):
        self.bot.add_view(ReminderPanelView(self))
        if self.settings.enabled:
            self._task = asyncio.create_task(self._schedule_loop(), name="periodic_reminder")

    async def cog_unload(self):
        if self._task:
            self._task.cancel()
            self._task = None

    # ── 排程 ──

    async def _refresh_update_starts(self) -> None:
        if self.settings.version_stages:
            # 讀 articles.db 是同步的全文比對，丟到執行緒，不卡 event loop
            self._update_starts = await asyncio.to_thread(VersionDateResolver().update_starts)

    async def _schedule_loop(self):
        await self.bot.wait_until_ready()
        await self._refresh_update_starts()
        self._log_upcoming(datetime.now(SERVER_TZ))
        channel = self.reminder_channel()
        if channel is not None:
            await self.ensure_role(channel.guild)  # 啟動時把身份組名稱同步成設定值
        while True:
            try:
                await self._refresh_update_starts()
                now = datetime.now(SERVER_TZ)
                await self.run_due(now)
                channel = self.reminder_channel()
                if channel is not None:
                    await self.refresh_panel_if_changed(channel)
                upcoming = upcoming_reminders(datetime.now(SERVER_TZ), self.settings, self._update_starts)
                delay = _MAX_SLEEP_SECONDS
                if upcoming:
                    # +1 秒：避免醒得稍早、還沒到 send_at 又空轉一輪
                    delay = min(delay, (upcoming[0].send_at - datetime.now(SERVER_TZ)).total_seconds() + 1)
                await asyncio.sleep(max(delay, 1))
            except asyncio.CancelledError:
                return
            except Exception as e:
                logger.error("週期提醒排程錯誤: %s", e, exc_info=True)
                await asyncio.sleep(300)

    def _log_upcoming(self, now: datetime) -> None:
        def label(r: Reminder) -> str:
            if isinstance(r.item, VersionStageItem):
                return "本階段結束前提醒" if r.kind == KIND_ENDING else "新階段開放提醒"
            return "結束前提醒" if r.kind == KIND_ENDING else "重置提醒"
        parts = [f"{r.item.emoji}{r.item.name}{label(r)} {format_moment(r.send_at)}"
                 for r in upcoming_reminders(now, self.settings, self._update_starts)[:5]]
        logger.info("週期提醒：接下來 → %s", "；".join(parts) or "（無）")

    def _configured_channel_id(self) -> Optional[int]:
        # 直接讀 config（有快取），避免未綁定時 get_channel_id 每次都噴警告
        config = ChannelConfig.load_config(caller="periodic_reminder")
        channel_id = config.get(self.settings.channel_config_key, ChannelConfig.DEFAULT_ID)
        return None if channel_id == ChannelConfig.DEFAULT_ID else int(channel_id)

    def reminder_channel(self) -> Optional[discord.TextChannel]:
        """綁定的提醒頻道；未綁定或失效回 None。"""
        channel_id = self._configured_channel_id()
        if channel_id is None:
            return None
        channel = self.bot.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            logger.warning("週期提醒頻道 %s 不是有效的文字頻道，略過", channel_id)
            return None
        return channel

    async def run_due(self, now: datetime) -> int:
        """發出現在該發、還沒發過的提醒；有發就把面板置底。回傳發了幾則。"""
        due = due_reminders(now, self.settings, self._update_starts)
        if not due:
            return 0
        channel = self.reminder_channel()
        if channel is None:
            return 0
        db = await get_shared_state_db()
        sent = 0
        for reminder in due:
            if await db.is_content_sent(SENT_SOURCE, reminder.dedup_key):
                continue
            if await self.send_reminder(channel, reminder, now):
                await db.mark_content_as_sent(SENT_SOURCE, reminder.dedup_key)
                sent += 1
        if sent:
            await self.panel.bump_safe(channel)
        return sent

    async def send_reminder(self, channel: discord.TextChannel, reminder: Reminder, now: datetime) -> bool:
        try:
            role = await self.ensure_role(channel.guild)
            text = build_reminder_text(reminder, role.mention, now)
            # 只允許 @ 這個身份組；reset 用靜音（有提及紅點、不推播）
            await channel.send(
                text,
                silent=reminder.silent,
                allowed_mentions=discord.AllowedMentions(everyone=False, users=False, roles=[role]),
            )
        except discord.HTTPException as e:
            logger.warning("週期提醒發送失敗 (%s): %s", reminder.dedup_key, e)
            return False
        logger.info("已發送週期提醒：%s（silent=%s）", reminder.dedup_key, reminder.silent)
        return True

    # ── 身份組與面板 ──

    async def ensure_role(self, guild: discord.Guild) -> discord.Role:
        """取得訂閱身份組：先用記錄的 id，再用名稱找既有的，都沒有才建立。"""
        async with self._role_lock:
            path = self.settings.runtime_path
            role_id = load_runtime(path).get("role_id")
            role = guild.get_role(int(role_id)) if role_id else None
            if role is None:
                role = discord.utils.get(guild.roles, name=self.settings.role_name)
            if role is None:
                role = await guild.create_role(
                    name=self.settings.role_name,
                    permissions=discord.Permissions.none(),
                    mentionable=False,  # bot 有管理員權限照樣能 @；設 True 等於誰都能 @ 它
                    reason="週期活動提醒：自助訂閱用身份組",
                )
                logger.info("已建立週期提醒身份組 %s (%s)", role.name, role.id)
            if role.name != self.settings.role_name:
                # 名稱以設定為準（改名只要改設定）；在 Discord 手動改的名字會在這裡被改回來
                try:
                    old_name = role.name
                    await role.edit(name=self.settings.role_name, reason="週期活動提醒：依設定同步名稱")
                    logger.info("週期提醒身份組改名：%s → %s", old_name, self.settings.role_name)
                except discord.HTTPException as e:
                    logger.warning("週期提醒身份組改名失敗: %s", e)
            if role.id != role_id:
                update_runtime(path, role_id=role.id)
            return role

    def _panel_content(self) -> tuple[str, str]:
        title = build_panel_title(self.settings)
        return title, build_panel_description(datetime.now(SERVER_TZ), self.settings, self._update_starts)

    async def _send_panel(self, channel: discord.TextChannel) -> discord.Message:
        title, description = self._panel_content()
        embed = discord.Embed(title=title, description=description, color=discord.Color.gold())
        message = await channel.send(embed=embed, view=ReminderPanelView(self))
        # 記住面板目前顯示的內容：日期因新公告或重置而改變、或改了名稱時，排程才知道要重發
        update_runtime(self.settings.runtime_path, panel_content="\n".join((title, description)))
        return message

    async def refresh_panel_if_changed(self, channel: discord.TextChannel) -> bool:
        """面板該顯示的內容跟上次發出的不同就重發；回傳有沒有重發。"""
        shown = load_runtime(self.settings.runtime_path).get("panel_content")
        if shown == "\n".join(self._panel_content()):
            return False
        return await self.panel.bump_safe(channel) is not None

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """提醒頻道裡有人講話就立即把面板置底（bot 自己的面板與提醒不算，避免循環）。"""
        if message.guild is None or message.author.id == self.bot.user.id:
            return
        if message.channel.id == self._configured_channel_id():
            self.panel.request_bump(message.channel)

    async def handle_subscription(self, interaction: discord.Interaction, *, subscribe: bool) -> None:
        member = interaction.user
        if interaction.guild is None or not isinstance(member, discord.Member):
            await interaction.response.send_message("請在伺服器內使用。", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            role = await self.ensure_role(interaction.guild)
            has_role = member.get_role(role.id) is not None
            if subscribe and has_role:
                text = f"你已經訂閱 {role.mention} 了。"
            elif subscribe:
                await member.add_roles(role, reason="週期活動提醒：自助訂閱")
                text = f"已訂閱 {role.mention}，重置前一天 {self.settings.ending_reminder_hour:02d}:00 會 @ 你。"
            elif has_role:
                await member.remove_roles(role, reason="週期活動提醒：自助取消訂閱")
                text = f"已取消訂閱 {role.mention}。"
            else:
                text = f"你沒有訂閱 {role.mention}。"
        except discord.Forbidden:
            text = "bot 沒有權限調整身份組，請通知管理員。"
        except discord.HTTPException as e:
            logger.warning("週期提醒訂閱處理失敗 (user=%s): %s", member.id, e)
            text = "處理失敗，請稍後再試。"
        await interaction.followup.send(text, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())


async def setup(bot: commands.Bot):
    await bot.add_cog(PeriodicReminderCommands(bot))
