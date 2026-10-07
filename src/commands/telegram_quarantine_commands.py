"""Telegram 過濾的隔離區面板：「垃圾訊息」thread 最底下一個面板，把判錯的放回主頻道（使用者 10-06 TF-Q1～Q4）。

- 置底面板只有日期選單（固定 custom_id，重啟後照樣能用）。選日期 → 只有自己看得到的訊息選單 → 選訊息 →
  只有自己看得到的確認（附連到隔離那則的連結）→ 按「放回主頻道」才送，避免選錯就公開送出。
- 第二層以後都是只有按的人看得到的訊息，兩位管理員同時操作不互相干擾；放回本身在轉發端一次只做一則，
  同一則只會送一次。
- 只有在這裡有「管理訊息」權限的人能操作（TF-Q2）。
- 有新的隔離訊息、或有人放回時，面板置底並更新日期（`QuarantineThreads.on_change`）。
- 選單只列被隔離、還沒放回的；依發文時間排，有文字顯示文字開頭，沒文字顯示「圖片」「影片」。
  Discord 一個選單最多 25 項：日期只列最近 25 天，一天也最多列 25 則（一天約一則，夠用）。
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Sequence

import discord
from discord.ext import commands

from services.relay.telegram_relay_service import QuarantineItem
from sys_settings.time_settings import APP_TZ
from utils.discord_threads import reopen_thread
from utils.panel_bump import PanelBumper
from utils.utils import check_guild, safe_send_interaction_message

logger = logging.getLogger(__name__)

DATE_SELECT_ID = "tgq:date"
PICK_TEMPLATE = r"tgq:pick:(?P<parent>\d+):(?P<day>\d{8})"
RESTORE_TEMPLATE = r"tgq:restore:(?P<pk>\d+)"
#: 面板位置（bot 自己寫的狀態，不進版控）。跟隔離 thread 的紀錄分開放，兩邊寫入不會互相蓋掉
PANEL_RUNTIME_PATH = str(Path(__file__).parents[1] / "settings" / "telegram_quarantine_panel_runtime.json")
_MAX_OPTIONS = 25
_PERMISSION = "manage_messages"

PANEL_TEXT = (
    # 給群友看的：不寫訊息從哪裡、怎麼來（使用者 10-07：「這邊可以不要寫出 telegram 轉發」）
    "🗑️ **垃圾訊息**：被判成沒有遊戲資訊的訊息放在這裡，每則最上面寫著判定理由。\n"
    "判錯的可以放回主頻道：選日期 → 選訊息 → 確認。需要「管理訊息」權限。"
)


def day_key(item: QuarantineItem) -> str:
    """發文日期（本機時區）→ 選單的值，例：20261006。"""
    if item.posted is None:
        return "00000000"
    return item.posted.astimezone(APP_TZ).strftime("%Y%m%d")


def _media_label(item: QuarantineItem) -> str:
    parts = []
    if item.image_count:
        parts.append("圖片" if item.image_count == 1 else f"圖片 ×{item.image_count}")
    if item.video_count:
        parts.append("影片" if item.video_count == 1 else f"影片 ×{item.video_count}")
    return "、".join(parts)


def item_option(item: QuarantineItem) -> discord.SelectOption:
    """選單的一項：「時間 文字開頭」，沒文字時是「時間 圖片 ×N」；有文字也有媒體時，媒體寫在說明。"""
    when = item.posted.astimezone(APP_TZ).strftime("%H:%M") if item.posted is not None else "--:--"
    text = " ".join(item.text.split())
    media = _media_label(item)
    head = text or media or "（沒有內容）"
    label = f"{when} {head}"
    if len(label) > 100:
        label = label[:99] + "…"
    return discord.SelectOption(label=label, value=str(item.pk),
                                description=f"附{media}" if text and media else None)


def date_options(items: Sequence[QuarantineItem]) -> list[discord.SelectOption]:
    """有還沒放回的日期，新的在前，最多 25 天。"""
    counts: dict[str, int] = {}
    for item in items:
        counts[day_key(item)] = counts.get(day_key(item), 0) + 1
    days = sorted(counts, reverse=True)[:_MAX_OPTIONS]
    return [discord.SelectOption(label=f"{d[4:6]}/{d[6:8]}（{counts[d]} 則）", value=d) for d in days]


def _parent_id(interaction: discord.Interaction) -> Optional[int]:
    return getattr(interaction.channel, "parent_id", None)


def _current_options(interaction: discord.Interaction) -> list[discord.SelectOption]:
    """面板上現在的日期選項（重畫成沒選取時沿用，不必先查資料庫）。"""
    for row in getattr(getattr(interaction, "message", None), "components", None) or []:
        for child in getattr(row, "children", ()):
            if getattr(child, "custom_id", None) == DATE_SELECT_ID:
                return [discord.SelectOption(label=o.label, value=o.value) for o in child.options if o.value != "-"]
    return []


async def _not_running(interaction: discord.Interaction) -> None:
    await safe_send_interaction_message(interaction, "放回功能目前沒有在運作，請通知管理員。", ephemeral=True)


class QuarantinePanelView(discord.ui.View):
    """置底面板：日期選單（persistent：timeout=None＋固定 custom_id）。"""

    def __init__(self, cog: "TelegramQuarantineCommands", options: Sequence[discord.SelectOption] = ()):
        super().__init__(timeout=None)
        self.cog = cog
        select = discord.ui.Select(
            custom_id=DATE_SELECT_ID,
            placeholder="選日期，挑要放回主頻道的訊息" if options else "目前沒有被隔離的訊息",
            options=list(options) or [discord.SelectOption(label="（目前沒有）", value="-")],
            disabled=not options,
        )
        select.callback = self._on_select
        self.add_item(select)
        self._select = select

    async def _on_select(self, interaction: discord.Interaction) -> None:
        await self.cog.handle_date(interaction, self._select.values[0] if self._select.values else "-")


class QuarantinePickSelect(discord.ui.DynamicItem[discord.ui.Select], template=PICK_TEMPLATE):
    """某一天被隔離的訊息（只有按的人看得到）。"""

    def __init__(self, parent_id: int, day: str, *, options: Sequence[discord.SelectOption] = ()):
        super().__init__(discord.ui.Select(
            custom_id=f"tgq:pick:{parent_id}:{day}", placeholder="選要放回主頻道的訊息",
            options=list(options) or [discord.SelectOption(label="（沒有）", value="-")],
        ))
        self.parent_id = parent_id
        self.day = day

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Select, match, /):
        return cls(int(match["parent"]), match["day"], options=item.options)

    async def callback(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("TelegramQuarantineCommands")
        value = self.item.values[0] if self.item.values else "-"
        if cog is None or not value.isdigit():
            return await _not_running(interaction)
        await cog.handle_pick(interaction, int(value))


class QuarantineRestoreButton(discord.ui.DynamicItem[discord.ui.Button], template=RESTORE_TEMPLATE):
    """確認：放回主頻道。"""

    def __init__(self, pk: int):
        super().__init__(discord.ui.Button(label="放回主頻道", emoji="↩️", style=discord.ButtonStyle.success,
                                           custom_id=f"tgq:restore:{pk}"))
        self.pk = pk

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button, match, /):
        return cls(int(match["pk"]))

    async def callback(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("TelegramQuarantineCommands")
        if cog is None:
            return await _not_running(interaction)
        await cog.handle_restore(interaction, self.pk)


def _view(*items: discord.ui.Item) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    for item in items:
        view.add_item(item)
    return view


class TelegramQuarantineCommands(commands.Cog):
    """隔離區面板（沒有 slash 指令；面板由轉發端在有隔離訊息時發出、置底）。"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        #: 轉發端 worker（`discord_bot.auto_start_telegram_relay` 建立時接上；面板與放回都經過它）
        self.worker = None
        self._panels: dict[int, PanelBumper] = {}

    async def cog_load(self):
        self.bot.add_view(QuarantinePanelView(self, [discord.SelectOption(label="-", value="-")]))
        self.bot.add_dynamic_items(QuarantinePickSelect, QuarantineRestoreButton)

    def _worker(self):
        worker = self.worker
        return worker if worker is not None and worker.running else None

    def _panel(self, parent_id: int) -> PanelBumper:
        if parent_id not in self._panels:
            async def send(channel, parent_id=parent_id):
                items = await self.worker.quarantine_items(parent_id) if self.worker is not None else []
                return await channel.send(content=PANEL_TEXT, view=QuarantinePanelView(self, date_options(items)),
                                          allowed_mentions=discord.AllowedMentions.none())
            self._panels[parent_id] = PanelBumper(PANEL_RUNTIME_PATH, send, custom_ids=(DATE_SELECT_ID,),
                                                  key_prefix=f"panel_{parent_id}_")
        return self._panels[parent_id]

    async def on_quarantine_change(self, parent_id: int, thread: discord.Thread) -> None:
        """隔離區多一則或放回一則：面板置底、日期重算。封存的 thread 先解封，舊面板才刪得掉。"""
        await reopen_thread(thread)
        self._panel(parent_id).request_bump(thread)

    async def post_panel(self, parent_id: int, thread: discord.Thread) -> None:
        """馬上置底並等它完成（一次性腳本搬移完用；腳本結束前背景工作來不及跑）。"""
        await reopen_thread(thread)
        await self._panel(parent_id).bump(thread)

    async def _allowed(self, interaction: discord.Interaction) -> bool:
        return await check_guild(interaction, permission=_PERMISSION)

    async def handle_date(self, interaction: discord.Interaction, day: str) -> None:
        # 選單選過的項目會停在那裡，再選同一天 Discord 不會通知 bot：**不管後面成不成**，先把面板重畫成沒選取。
        # 封存的 thread 先解封（一週沒新訊息就會自動封存），不然改不了面板
        if getattr(interaction.channel, "archived", False):
            await reopen_thread(interaction.channel)
        shown = _current_options(interaction)
        await interaction.response.edit_message(view=QuarantinePanelView(self, shown))
        if not await self._allowed(interaction):
            return
        worker, parent_id = self._worker(), _parent_id(interaction)
        if worker is None or parent_id is None:
            return await _not_running(interaction)
        items = await worker.quarantine_items(parent_id, current_thread_id=interaction.channel.id)
        fresh = date_options(items)
        if [o.value for o in fresh] != [o.value for o in shown]:
            try:
                await interaction.edit_original_response(view=QuarantinePanelView(self, fresh))
            except discord.HTTPException as exc:
                logger.info("隔離區面板：更新日期失敗（下次有變動會再置底）：%s", exc)
        picks = [item_option(i) for i in items if day_key(i) == day][:_MAX_OPTIONS]
        if not picks:
            await interaction.followup.send("這天沒有還沒放回的訊息了。", ephemeral=True)
            return
        await interaction.followup.send(
            f"{day[4:6]}/{day[6:8]} 被隔離的訊息（依發文時間）：",
            view=_view(QuarantinePickSelect(parent_id, day, options=picks)), ephemeral=True,
        )

    async def handle_pick(self, interaction: discord.Interaction, pk: int) -> None:
        if not await self._allowed(interaction):
            return
        worker = self._worker()
        if worker is None:
            return await _not_running(interaction)
        # 找隔離那則要翻 thread 歷史，可能超過 3 秒：先回應，再改這則只有自己看得到的訊息
        await interaction.response.defer()
        try:
            found = await worker.find_quarantine_messages([pk])
        except Exception as exc:
            logger.warning("隔離區面板：找隔離那則失敗 pk=%s：%s", pk, exc)
            found = []      # 找不到連結照樣可以放回
        link = f"\n{found[-1].jump_url}" if found else ""
        await interaction.edit_original_response(
            content=f"要把這則放回主頻道嗎？{link}", view=_view(QuarantineRestoreButton(pk)),
        )

    async def handle_restore(self, interaction: discord.Interaction, pk: int) -> None:
        if not await self._allowed(interaction):
            return
        worker = self._worker()
        if worker is None:
            return await _not_running(interaction)
        # 先拿掉按鈕，避免連按；送出可能要壓縮影片，做完再回報
        await interaction.response.edit_message(content="放回中……", view=None)
        try:
            ok, message = await worker.restore(pk, interaction.user.display_name)
        except Exception as exc:
            logger.error("隔離區面板：放回出錯 pk=%s：%s", pk, exc, exc_info=True)
            ok, message = False, "放回時出錯了，請通知管理員看 log；先確認主頻道有沒有送出，再決定要不要重按。"
        await interaction.edit_original_response(content=("✅ " if ok else "⚠️ ") + message)


async def setup(bot: commands.Bot):
    await bot.add_cog(TelegramQuarantineCommands(bot))
