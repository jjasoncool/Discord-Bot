"""頻道綁定面板：每一項綁哪個頻道一目了然，選一項改綁、解除綁定；私訊與伺服器裡都能用，重啟後按鈕照樣有效。

架構定位：介面層（commands）的 view 與流程，沒有自己的 cog。
  上層：`commands.management_commands`（/server_manager → 頻道設定；`cog_load` 登記這裡的 DynamicItem）、私訊主控台。
  下層：`settings.channel_registry`（登記表、目前綁定、寫入與綁定後動作）、`utils.utils`（安全回覆、分頁選單、設定檔例外）、
  `utils.discord_members`（群主檢查、私訊裡找伺服器）、`sys_settings.admin_console_settings`（每頁幾項）。

介面：
- `send_panel(interaction, page=0)`：回一則面板（伺服器裡只有本人看得到；私訊裡是一般訊息）。
- `render(guild, page) -> (embed, view, page)`：面板內容：登記表現讀、依頻道型別分組、分頁，頁碼夾回合法範圍。
- `page_items(page)`：這一頁的項目、夾回合法範圍的頁碼、總頁數。
- `PanelButton`／`PanelPickSelect`：DynamicItem，custom_id 帶動作與頁碼；`DYNAMIC_ITEMS` 給 cog_load 登記。

規則：
- 寫 config.json 與綁定後動作只走 `channel_registry.apply`／`unbind`，這裡只管畫面與互動。
- 選單只列本頁的項目：登記表再長也碰不到一個選單 25 項的上限。
- 只有群主能操作（`_ACCESS`）；要放寬只改那一行。

例外與決策：
- 選頻道用 bot 自己列的清單（`create_paginated_view`，25 個一頁），不用 Discord 原生的頻道選單：原生選單在私訊裡列不出伺服器的頻道；
  表單類的流程（Telegram 路由）選目標頻道也走同一種清單。
- 伺服器裡的面板是只有本人看得到的訊息，bot 沒辦法主動重畫（那種訊息只能透過互動改）：改完綁定請按「重新整理」；
  私訊裡的面板是一般訊息，改完自動重畫。
"""
from __future__ import annotations

import logging
import math
from datetime import datetime
from typing import Sequence

import discord

from settings import channel_registry
from settings.channel_registry import ChannelSetting
from sys_settings.admin_console_settings import ADMIN_CONSOLE_SETTINGS
from sys_settings.time_settings import APP_TZ
from utils.discord_members import home_guild, require_access
from utils.utils import ConfigWriteError, create_paginated_view, safe_send_interaction_message

logger = logging.getLogger(__name__)

BUTTON_TEMPLATE = r"chpanel:(?P<action>prev|next|unbind|refresh):(?P<page>\d+)"
PICK_TEMPLATE = r"chpanel:pick:(?P<page>\d+)"
#: 誰能操作；要放寬到管理員只改這裡（私訊裡只放得了群主，管理員要回伺服器查身分組）
_ACCESS = dict(owner_only=True, allow_dm=True)
_NO_GUILD = "bot 不只在一個伺服器裡，請到伺服器裡用 /server_manager 操作。"
_CONFIG_BROKEN = "❌ 設定檔讀取失敗，這次沒有寫入，請檢查 config.json。"
_STALE = "找不到這一項，登記表可能改過了；按「重新整理」再試。"


def page_size() -> int:
    # 一個選單最多 25 個選項，一頁放不下更多
    return min(25, max(1, int(ADMIN_CONSOLE_SETTINGS.bindings_page_size)))


def page_count(total: int) -> int:
    return max(1, math.ceil(total / page_size()))


def page_items(page: int) -> tuple[list[ChannelSetting], int, int]:
    """這一頁的項目、夾回合法範圍的頁碼、總頁數（登記表每次現讀）。"""
    ordered = channel_registry.display_order()
    pages = page_count(len(ordered))
    page = min(max(0, int(page)), pages - 1)
    size = page_size()
    return ordered[page * size:(page + 1) * size], page, pages


def _option(setting: ChannelSetting) -> discord.SelectOption:
    return discord.SelectOption(
        label=setting.label[:100], value=setting.label[:100],
        description=(setting.desc or "")[:100] or None,
        emoji=channel_registry.type_icon(setting.channel_type),
    )


async def _where(setting: ChannelSetting, config: dict) -> str:
    """這一項現在綁哪裡：頻道（`<#id>` 在 Discord 顯示成可點的頻道名）、表單類自己描述、沒綁就「未綁定」。"""
    if setting.describe is not None:
        return setting.describe(config)
    channel_id = await channel_registry.bound_channel_id(setting)
    return f"<#{channel_id}>" if channel_id else "未綁定"


async def render(guild: discord.Guild, page: int) -> tuple[discord.Embed, discord.ui.View, int]:
    """面板內容與按鈕；回實際顯示的頁碼（夾回合法範圍）。"""
    items, page, pages = page_items(page)
    all_settings = channel_registry.all_settings()
    config = channel_registry.ChannelConfig.load_config(caller="channel_panel")
    bound = 0
    for setting in all_settings:
        if setting.config_key and await channel_registry.bound_channel_id(setting):
            bound += 1
    lines: list[str] = []
    last_type: object = ...
    for setting in items:
        if setting.channel_type != last_type:
            group = [s for s in all_settings if s.channel_type == setting.channel_type]
            lines.append(f"{channel_registry.type_icon(setting.channel_type)} "
                         f"**{channel_registry.type_name(setting.channel_type)}**（{len(group)}）")
            last_type = setting.channel_type
        lines.append(f"**{setting.label}**　{await _where(setting, config)}")
        if setting.desc:
            lines.append(f"-# {setting.desc}")
    embed = discord.Embed(title="頻道綁定", description="\n".join(lines) or "（登記表是空的）", color=discord.Color.blurple())
    now = datetime.now(APP_TZ).strftime("%H:%M")
    embed.set_footer(text=f"第 {page + 1}／{pages} 頁 · 共 {len(all_settings)} 項、已綁 {bound} 項 · 每頁 {page_size()} 項 · {now} 更新")
    view = discord.ui.View(timeout=None)
    view.add_item(PanelPickSelect(page, options=[_option(s) for s in items]))
    view.add_item(PanelButton("prev", page, label="◀ 上一頁", disabled=page <= 0))
    view.add_item(PanelButton("next", page, label="下一頁 ▶", disabled=page >= pages - 1))
    view.add_item(PanelButton("unbind", page, label="解除綁定", style=discord.ButtonStyle.danger))
    view.add_item(PanelButton("refresh", page, label="重新整理"))
    return embed, view, page


async def send_panel(interaction: discord.Interaction, page: int = 0) -> None:
    """回一則面板：伺服器裡只有本人看得到；私訊裡是一般訊息（bot 之後能重畫）。"""
    if not await require_access(interaction, **_ACCESS):
        return
    guild = home_guild(interaction)
    if guild is None:
        await safe_send_interaction_message(interaction, _NO_GUILD, ephemeral=True)
        return
    embed, view, _ = await render(guild, page)
    await safe_send_interaction_message(interaction, embed=embed, view=view, ephemeral=interaction.guild is not None)


async def _refresh_panel(message, guild: discord.Guild, page: int) -> None:
    """用 bot 自己的身分重畫面板（只有本人看得到的那種訊息改不了，留給「重新整理」）。"""
    if message is None or getattr(getattr(message, "flags", None), "ephemeral", False):
        return
    try:
        embed, view, _ = await render(guild, page)
        await message.edit(embed=embed, view=view)
    except discord.HTTPException as exc:
        logger.warning("頻道綁定面板重畫失敗：%s", exc)


class PanelButton(discord.ui.DynamicItem[discord.ui.Button], template=BUTTON_TEMPLATE):
    """上一頁、下一頁、解除綁定、重新整理；custom_id 帶現在這一頁。"""

    def __init__(self, action: str, page: int, *, label: str,
                 style: discord.ButtonStyle = discord.ButtonStyle.secondary, disabled: bool = False):
        super().__init__(discord.ui.Button(label=label, style=style, custom_id=f"chpanel:{action}:{page}", disabled=disabled))
        self.action = action
        self.page = int(page)

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button, match, /):
        return cls(match["action"], int(match["page"]), label=item.label, style=item.style, disabled=item.disabled)

    async def callback(self, interaction: discord.Interaction):
        if not await require_access(interaction, **_ACCESS):
            return
        guild = home_guild(interaction)
        if guild is None:
            await safe_send_interaction_message(interaction, _NO_GUILD, ephemeral=True)
            return
        if self.action == "unbind":
            await _start_unbind(interaction, guild, self.page)
            return
        target = {"prev": self.page - 1, "next": self.page + 1}.get(self.action, self.page)
        embed, view, _ = await render(guild, target)
        await interaction.response.edit_message(embed=embed, view=view)


class PanelPickSelect(discord.ui.DynamicItem[discord.ui.Select], template=PICK_TEMPLATE):
    """「改這一頁的哪一項」：選項只有本頁的項目。"""

    def __init__(self, page: int, *, options: Sequence[discord.SelectOption] = ()):
        super().__init__(discord.ui.Select(
            custom_id=f"chpanel:pick:{page}", placeholder="改這一頁的哪一項…", min_values=1, max_values=1,
            options=list(options) or [discord.SelectOption(label="（沒有項目）", value="-")], disabled=not options,
        ))
        self.page = int(page)

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Select, match, /):
        return cls(int(match["page"]), options=item.options)

    async def callback(self, interaction: discord.Interaction):
        if not await require_access(interaction, **_ACCESS):
            return
        guild = home_guild(interaction)
        if guild is None:
            await safe_send_interaction_message(interaction, _NO_GUILD, ephemeral=True)
            return
        label = self.item.values[0] if self.item.values else "-"
        setting = channel_registry.get_setting(label)
        if setting is None:
            await safe_send_interaction_message(interaction, _STALE, ephemeral=True)
            return
        if setting.custom_handler is not None:
            await setting.custom_handler(interaction)
            # 表單跳出後選單還停在剛選的項目（再選同一項 Discord 不會通知 bot）：私訊裡的面板用 bot 的身分重畫
            await _refresh_panel(interaction.message, guild, self.page)
            return
        await _start_pick(interaction, guild, self.page, setting)


async def _start_pick(interaction: discord.Interaction, guild: discord.Guild, page: int, setting: ChannelSetting) -> None:
    """選了一項：面板重畫成沒選取，再回一則只有本人看得到的頻道清單（只列那一項允許的頻道型別）。"""
    icon = channel_registry.type_icon(setting.channel_type)
    kind = channel_registry.type_name(setting.channel_type)
    panel_message = interaction.message
    embed, view, _ = await render(guild, page)
    await interaction.response.edit_message(embed=embed, view=view)
    channels = [c for c in guild.channels if c.type == setting.channel_type]
    if not channels:
        await interaction.followup.send(f"這個伺服器沒有{kind}，沒辦法綁「{setting.label}」。", ephemeral=True)
        return
    current = await channel_registry.bound_channel_id(setting)
    options = [
        discord.SelectOption(label=channel.name[:100], value=str(channel.id), description=f"ID: {channel.id}", emoji=icon)
        for channel in channels
    ]

    async def on_select(pick: discord.Interaction, value: str) -> None:
        if not await require_access(pick, **_ACCESS):
            return
        channel = guild.get_channel(int(value))
        if channel is None or channel.type != setting.channel_type:
            await safe_send_interaction_message(pick, f"選的頻道無效或不是{kind}，請重選。", ephemeral=True)
            return
        # 先回應再寫檔：寫檔加綁定後動作（建身分組、發面板）可能超過 Discord 等回應的 3 秒
        await pick.response.edit_message(content=f"寫入「{setting.label}」…", embed=None, view=None)
        try:
            note = await channel_registry.apply(setting, bot=pick.client, guild=guild, channel=channel)
        except ConfigWriteError as exc:
            logger.error("綁定頻道寫入設定檔失敗: %s", exc)
            await pick.edit_original_response(content=_CONFIG_BROKEN)
            return
        except Exception as exc:
            # 互動的邊界：綁定後動作出錯也要告訴群主，不能停在「寫入中」（設定可能已經寫進去了，面板照樣重畫）
            logger.error("綁定「%s」出錯: %s", setting.label, exc, exc_info=True)
            await pick.edit_original_response(content=f"❌ 綁定「{setting.label}」時出錯：{type(exc).__name__}: {exc}"[:1900])
            await _refresh_panel(panel_message, guild, page)
            return
        await pick.edit_original_response(content=f"✅ 已將「{setting.label}」設定為 {channel.mention}{note}"[:1900])
        await _refresh_panel(panel_message, guild, page)

    title = f"改「{setting.label}」"
    description = (f"目前綁 {f'<#{current}>' if current else '未綁定'}。這一項只能綁{icon} {kind}；"
                   "選一個，選完就寫進設定、面板跟著更新。")
    _, picker = create_paginated_view(options, f"選一個{kind}…", title, description, setting.color, on_select,
                                      custom_id_prefix=f"chpanel_pick_{setting.config_key}")
    await interaction.followup.send(embed=discord.Embed(title=title, description=description, color=setting.color),
                                    view=picker, ephemeral=True)


async def _start_unbind(interaction: discord.Interaction, guild: discord.Guild, page: int) -> None:
    """解除綁定：只有本人看得到的選單，列本頁已綁的項目；選了就刪 key、面板重畫。"""
    items, page, _ = page_items(page)
    panel_message = interaction.message
    bound: list[tuple[ChannelSetting, int]] = []
    for setting in items:
        channel_id = await channel_registry.bound_channel_id(setting)
        if channel_id:
            bound.append((setting, channel_id))
    if not bound:
        await safe_send_interaction_message(interaction, "這一頁沒有已綁定的項目。", ephemeral=True)
        return
    select = discord.ui.Select(placeholder="解除哪一項的綁定…", options=[
        discord.SelectOption(
            label=setting.label[:100], value=setting.label[:100],
            description=f"目前：{getattr(guild.get_channel(channel_id), 'name', channel_id)}"[:100],
            emoji=channel_registry.type_icon(setting.channel_type),
        )
        for setting, channel_id in bound
    ])

    async def on_select(pick: discord.Interaction) -> None:
        if not await require_access(pick, **_ACCESS):
            return
        setting = channel_registry.get_setting(select.values[0] if select.values else "-")
        if setting is None:
            await safe_send_interaction_message(pick, _STALE, ephemeral=True)
            return
        await pick.response.edit_message(content=f"解除「{setting.label}」…", embed=None, view=None)
        try:
            previous = await channel_registry.unbind(setting)
        except ConfigWriteError as exc:
            logger.error("解除綁定寫入設定檔失敗: %s", exc)
            await pick.edit_original_response(content=_CONFIG_BROKEN)
            return
        was = f"（原本是 <#{previous}>）" if previous else ""
        await pick.edit_original_response(
            content=f"✅ 已解除「{setting.label}」的綁定{was}。那個功能會停用到再綁一次；已發出去的面板訊息不會刪。")
        await _refresh_panel(panel_message, guild, page)

    select.callback = on_select
    view = discord.ui.View()
    view.add_item(select)
    await safe_send_interaction_message(interaction, "解除綁定後那個功能會停用，直到再綁一次。", view=view, ephemeral=True)


DYNAMIC_ITEMS = (PanelButton, PanelPickSelect)
