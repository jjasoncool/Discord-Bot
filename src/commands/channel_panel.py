"""頻道綁定面板：每一項綁哪個頻道一目了然，選一項改綁、解除某一項、表單類先輸入再選頻道——都在主控台那一則訊息上換畫面；
私訊與伺服器裡都能用，重啟後按鈕照樣有效。

架構定位：介面層（commands）的 view 與流程，沒有自己的 cog。
  上層：`commands.admin_console`（主控台的「頻道設定」把這裡的面板畫在主控台那一則上；用到時才 import 這裡）、
  `commands.management_commands`（`cog_load` 登記這裡的 DynamicItem）。
  下層：`settings.channel_registry`（登記表、目前綁定、寫入與綁定後動作、表單類的輸入規格與寫入）、`commands.admin_console.back_button`
  （回主控台）、`utils.discord_content`（換畫面、錯誤邊界）、`utils.utils`（分頁、設定檔例外）、`utils.discord_members`（群主檢查、
  私訊裡找伺服器）、`sys_settings.admin_console_settings`（每頁幾項）。

介面：
- `render(guild, page, notice=, busy=) -> (view, page)`：面板本體（新版版面）：登記表現讀、依頻道型別分組、分頁，頁碼夾回合法範圍。
- `render_channel_pick(guild, setting, page, sub, text=)`：選頻道的畫面（只列那一項允許的頻道種類、超過 25 個分頁）；
  `render_unbind(guild, page)`：解除某一項的畫面（只列本頁已綁的）。
- `page_items(page)`：這一頁的項目、夾回合法範圍的頁碼、總頁數。
- `PanelButton`／`PanelPickSelect`／`ChannelSelect`／`UnbindSelect`：DynamicItem，custom_id 帶動作、頁碼、哪一項、表單輸入；
  `InputModal`：表單類的那一格輸入；`DYNAMIC_ITEMS` 給 cog_load 登記。

規則：
- 寫 config.json 與綁定後動作只走 `channel_registry.apply`／`unbind`／各表單類的 `apply_input`，這裡只管畫面與互動。
- 每個操作都改面板這一則（`edit_screen`）：子畫面有「回上一層」、結果寫在標題下那一行、寫檔前先切成「處理中」（按鈕全灰）；
  一次互動是錯誤邊界（`guarded_screen`），做壞了換回面板並標錯誤。
- 選單只列本頁的項目：登記表再長也碰不到一個選單 25 項的上限。
- 只有群主能操作（`_ACCESS`）；要放寬只改那一行。

例外與決策：
- 版面照使用者看過的草稿：標題下一行頁碼與統計、每一組一個標題、每一項一行「名稱　頻道　說明」、底部一段說明、
  一個選單加五顆按鈕。Discord 做不出三欄對齊與灰色小字夾在同一行，說明接在同一行後面。
- 頻道清單由 bot 自己列、分頁寫在 custom_id：Discord 原生的頻道選單在私訊裡列不出伺服器的頻道；閉包版的分頁選單重啟就失效。
- 表單類（Telegram 路由）送出表單後把面板換成「選目標頻道」：表單是從面板的選單開的，送出的互動能改原訊息；輸入的文字帶在
  custom_id 裡（上限 60 字、不能有冒號），重啟後也接得回去。表單取消的話選單會停在剛選的項目，私訊裡的面板用 bot 的身分重畫一次。
- 綁定後動作出錯：寫入已經完成，告訴群主出了什麼錯、面板照現況重畫，不回滾。
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Awaitable, Callable, Optional, Sequence

import discord

from commands.admin_console import back_button, screen_view
from settings import channel_registry
from settings.channel_registry import ChannelSetting
from sys_settings.admin_console_settings import ADMIN_CONSOLE_SETTINGS
from sys_settings.time_settings import APP_TZ
from utils.discord_content import edit_screen, guarded_screen
from utils.discord_members import NO_HOME_GUILD, home_guild, require_access
from utils.utils import ConfigWriteError, ITEMS_PER_PAGE, paginate, safe_send_interaction_message

logger = logging.getLogger(__name__)

#: 動作、面板頁碼；選頻道的畫面再帶哪一項（名稱）、頻道清單的頁碼、表單輸入的文字
BUTTON_TEMPLATE = (r"chpanel:(?P<action>prev|next|unbind|refresh|chan):(?P<page>\d+)"
                   r"(?::(?P<label>[^:]+):(?P<sub>\d+)(?::(?P<text>[^:]*))?)?")
PICK_TEMPLATE = r"chpanel:pick:(?P<page>\d+)"
CHANNEL_TEMPLATE = r"chpanel:chansel:(?P<page>\d+):(?P<label>[^:]+):(?P<sub>\d+)(?::(?P<text>[^:]*))?"
UNBIND_TEMPLATE = r"chpanel:unbsel:(?P<page>\d+)"
#: 誰能操作；要放寬到管理員只改這裡（私訊裡只放得了群主，管理員要回伺服器查身分組）
_ACCESS = dict(owner_only=True, allow_dm=True)
_CONFIG_BROKEN = "❌ 設定檔讀取失敗，這次沒有寫入，請檢查 config.json。"
_STALE = "⚠️ 找不到這一項，登記表可能改過了；面板已重畫，請再選一次。"
#: 表單輸入帶在 custom_id 裡（整串上限 100 字），留給文字的長度
_INPUT_LIMIT = 60
_FOOTNOTE = ("-# 項目從頻道登記表讀出來，新加一個功能就多一列、頁數跟著算。"
             "要改：下面選這一頁的一項，再選頻道（只會列那一項允許的頻道種類）。")


def page_size() -> int:
    # 一個選單最多 25 個選項，一頁放不下更多
    return min(25, max(1, int(ADMIN_CONSOLE_SETTINGS.bindings_page_size)))


def page_count(total: int) -> int:
    return paginate(range(total), 0, page_size())[2]


def page_items(page: int) -> tuple[list[ChannelSetting], int, int]:
    """這一頁的項目、夾回合法範圍的頁碼、總頁數（登記表每次現讀）。"""
    return paginate(channel_registry.display_order(), page, page_size())


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


def _pick_type(setting: ChannelSetting) -> Optional[discord.ChannelType]:
    """這一項要選哪種頻道：選頻道類是它綁的型別，表單類是輸入完要選的型別。"""
    return setting.input.pick_type if setting.input is not None else setting.channel_type


async def render(guild: discord.Guild, page: int, *, notice: Optional[str] = None,
                 busy: bool = False) -> tuple[discord.ui.LayoutView, int]:
    """面板內容與按鈕；回實際顯示的頁碼（夾回合法範圍）。結果那一行接在標題下；busy 時全灰（寫檔中，防再按一次）。
    文字用 `utils.discord_content.layout_text(view)` 取。"""
    items, page, pages = page_items(page)
    all_settings = channel_registry.all_settings()
    config = channel_registry.ChannelConfig.load_config(caller="channel_panel")
    bound = 0
    for setting in all_settings:
        if setting.config_key and await channel_registry.bound_channel_id(setting):
            bound += 1
    now = datetime.now(APP_TZ).strftime("%H:%M")

    box = discord.ui.Container(accent_colour=discord.Color.blurple())
    box.add_item(discord.ui.TextDisplay(
        f"## 頻道綁定\n-# 第 {page + 1}／{pages} 頁 · 共 {len(all_settings)} 項、已綁 {bound} 項 · "
        f"每頁 {page_size()} 項 · 改了馬上生效 · 最後更新 {now}" + (f"\n{notice[:500]}" if notice else "")))
    box.add_item(discord.ui.Separator())
    groups: list[tuple[object, list[str]]] = []
    for setting in items:
        if not groups or groups[-1][0] != setting.channel_type:
            same_type = [s for s in all_settings if s.channel_type == setting.channel_type]
            groups.append((setting.channel_type, [
                f"**{channel_registry.type_icon(setting.channel_type)} "
                f"{channel_registry.type_name(setting.channel_type)}（{len(same_type)}）**"]))
        line = f"**{setting.label}**　{await _where(setting, config)}"
        if setting.desc:
            line += f"　· {setting.desc}"
        groups[-1][1].append(line)
    if not groups:
        box.add_item(discord.ui.TextDisplay("（登記表是空的）"))
    for index, (_, lines) in enumerate(groups):
        if index:
            box.add_item(discord.ui.Separator(visible=False))
        box.add_item(discord.ui.TextDisplay("\n".join(lines)))
    box.add_item(discord.ui.Separator())
    box.add_item(discord.ui.TextDisplay(_FOOTNOTE))

    view = screen_view(box, [PanelPickSelect(page, options=[_option(s) for s in items], disabled=busy)], [
        PanelButton("prev", page, label="◀ 上一頁", disabled=busy or page <= 0),
        PanelButton("next", page, label="下一頁 ▶", disabled=busy or page >= pages - 1),
        PanelButton("unbind", page, label="解除某一項", style=discord.ButtonStyle.danger, disabled=busy),
        PanelButton("refresh", page, label="重新整理", disabled=busy),
        back_button(disabled=busy),
    ])
    return view, page


async def render_channel_pick(guild: discord.Guild, setting: ChannelSetting, page: int, sub: int,
                              text: Optional[str] = None) -> discord.ui.LayoutView:
    """選頻道的畫面：只列那一項允許的頻道種類、超過 25 個分頁（頁碼夾回合法範圍）；伺服器沒有那種頻道就退回面板並說原因。"""
    kind_type = _pick_type(setting)
    icon, kind = channel_registry.type_icon(kind_type), channel_registry.type_name(kind_type)
    channels = [c for c in guild.channels if c.type == kind_type]
    if not channels:
        view, _ = await render(guild, page, notice=f"⚠️ 這個伺服器沒有{kind}，沒辦法綁「{setting.label}」。")
        return view
    shown, sub, pages = paginate(channels, sub, ITEMS_PER_PAGE)
    if text is not None:
        title = f"## {setting.label}：{text}\n-# 選要轉到的{icon} {kind}；同一個來源再設一次就多一個頻道。"
    else:
        current = await channel_registry.bound_channel_id(setting)
        title = (f"## 改「{setting.label}」\n-# 目前綁 {f'<#{current}>' if current else '未綁定'}。"
                 f"這一項只能綁{icon} {kind}；選一個，選完就寫進設定。")
    if pages > 1:
        title += f"\n-# 第 {sub + 1}／{pages} 頁，共 {len(channels)} 個{kind}。"
    box = discord.ui.Container(accent_colour=setting.color)
    box.add_item(discord.ui.TextDisplay(title))
    options = [discord.SelectOption(label=c.name[:100], value=str(c.id), description=f"ID: {c.id}", emoji=icon) for c in shown]
    buttons: list[discord.ui.Item] = []
    if pages > 1:
        buttons.append(PanelButton("chan", page, setting.label, max(sub - 1, 0), text, label="◀ 上一頁", disabled=sub <= 0))
        buttons.append(PanelButton("chan", page, setting.label, min(sub + 1, pages - 1), text, label="下一頁 ▶",
                                   disabled=sub >= pages - 1))
    buttons.append(PanelButton("refresh", page, label="↩️ 回上一層"))
    return screen_view(box, [ChannelSelect(page, setting.label, sub, text, options=options, kind=kind)], buttons)


async def render_unbind(guild: discord.Guild, page: int) -> discord.ui.LayoutView:
    """解除某一項的畫面：只列本頁已綁的項目；這一頁沒有已綁的就退回面板並說原因。"""
    items, page, _ = page_items(page)
    options = []
    for setting in items:
        channel_id = await channel_registry.bound_channel_id(setting)
        if channel_id:
            options.append(discord.SelectOption(
                label=setting.label[:100], value=setting.label[:100],
                description=f"目前：{getattr(guild.get_channel(channel_id), 'name', channel_id)}"[:100],
                emoji=channel_registry.type_icon(setting.channel_type)))
    if not options:
        view, _ = await render(guild, page, notice="⚠️ 這一頁沒有已綁定的項目。")
        return view
    box = discord.ui.Container(accent_colour=discord.Color.red())
    box.add_item(discord.ui.TextDisplay("## 解除某一項\n-# 解除綁定後那個功能會停用，直到再綁一次；已發出去的面板訊息不會刪。只列這一頁已綁的。"))
    return screen_view(box, [UnbindSelect(page, options=options)], [PanelButton("refresh", page, label="↩️ 回上一層")])


async def _refresh_panel(message, guild: discord.Guild, page: int) -> None:
    """用 bot 自己的身分重畫面板（只有本人看得到的那種訊息改不了）：表單跳出後選單還停在剛選的項目，取消表單就會卡在那。"""
    if message is None or getattr(getattr(message, "flags", None), "ephemeral", False):
        return
    try:
        view, _ = await render(guild, page)
        await message.edit(content=None, embed=None, view=view)
    except discord.HTTPException as exc:
        logger.warning("頻道綁定面板重畫失敗：%s", exc)


# ────────────────────────────────────────────
#  互動：每個操作都改面板這一則訊息
# ────────────────────────────────────────────

async def _ready(interaction: discord.Interaction) -> Optional[discord.Guild]:
    if not await require_access(interaction, **_ACCESS):
        return None
    guild = home_guild(interaction)
    if guild is None:
        await safe_send_interaction_message(interaction, NO_HOME_GUILD, ephemeral=True)
    return guild


async def _guarded(interaction: discord.Interaction, label: str, page: int,
                   run: Callable[[discord.Guild], Awaitable[None]]) -> None:
    """面板上一次操作的外殼：先驗群主與伺服器，做壞了把面板換回來並標錯誤（不能停在「處理中」全灰）。"""
    guild = await _ready(interaction)
    if guild is None:
        return

    async def rescue(notice: str) -> None:
        view, _ = await render(guild, page, notice=notice)
        await edit_screen(interaction, view=view)

    await guarded_screen(interaction, f"頻道綁定面板：{label}", lambda: run(guild), rescue=rescue, log=logger)


async def _show_panel(interaction: discord.Interaction, guild: discord.Guild, page: int, *,
                      notice: Optional[str] = None, busy: bool = False) -> None:
    view, _ = await render(guild, page, notice=notice, busy=busy)
    await edit_screen(interaction, view=view)


async def _bind(interaction: discord.Interaction, guild: discord.Guild, setting: ChannelSetting, page: int,
                channel, text: Optional[str]) -> None:
    """選好頻道：先切「處理中」再寫檔（寫檔加綁定後動作可能超過 Discord 等回應的 3 秒），結果寫回面板。"""
    kind_type = _pick_type(setting)
    if channel is None or channel.type != kind_type:
        await _show_panel(interaction, guild, page,
                          notice=f"⚠️ 選的頻道無效或不是{channel_registry.type_name(kind_type)}，請重選。")
        return
    await _show_panel(interaction, guild, page, notice=f"⏳ 正在寫入「{setting.label}」…", busy=True)
    try:
        if setting.apply_input is not None:
            notice = await setting.apply_input(text or "", int(channel.id))
        else:
            note = await channel_registry.apply(setting, bot=interaction.client, guild=guild, channel=channel)
            notice = f"✅ 已將「{setting.label}」設定為 {channel.mention}{note}"
    except ConfigWriteError as exc:
        logger.error("綁定「%s」寫入設定檔失敗: %s", setting.label, exc)
        notice = _CONFIG_BROKEN
    except Exception as exc:  # 邊界：綁定後動作出錯也要告訴群主（設定可能已經寫進去了），面板照現況重畫
        logger.error("綁定「%s」出錯: %s", setting.label, exc, exc_info=True)
        notice = f"❌ 綁定「{setting.label}」時出錯：{type(exc).__name__}: {exc}"[:400] + "（設定可能已寫入，下面是現況）"
    await _show_panel(interaction, guild, page, notice=notice[:900])


class PanelButton(discord.ui.DynamicItem[discord.ui.Button], template=BUTTON_TEMPLATE):
    """上一頁、下一頁、解除某一項、重新整理（也是子畫面的「回上一層」）、選頻道畫面的翻頁；custom_id 帶現在這一頁。"""

    def __init__(self, action: str, page: int, label_of: Optional[str] = None, sub: Optional[int] = None,
                 text: Optional[str] = None, *, label: str, style: discord.ButtonStyle = discord.ButtonStyle.secondary,
                 disabled: bool = False):
        parts = ["chpanel", action, str(int(page))]
        if label_of is not None:
            parts += [label_of, str(int(sub or 0))]
            if text is not None:
                parts.append(text)
        super().__init__(discord.ui.Button(label=label, style=style, custom_id=":".join(parts), disabled=disabled))
        self.action, self.page, self.label_of, self.text = action, int(page), label_of, text
        self.sub = int(sub) if sub is not None else 0

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button, match, /):
        return cls(match["action"], int(match["page"]), match["label"], match["sub"], match["text"],
                   label=item.label, style=item.style, disabled=item.disabled)

    async def callback(self, interaction: discord.Interaction):
        async def run(guild: discord.Guild) -> None:
            if self.action == "unbind":
                await edit_screen(interaction, view=await render_unbind(guild, self.page))
            elif self.action == "chan":
                setting = channel_registry.get_setting(self.label_of or "")
                if setting is None:
                    await _show_panel(interaction, guild, self.page, notice=_STALE)
                    return
                await edit_screen(interaction, view=await render_channel_pick(guild, setting, self.page, self.sub, self.text))
            else:
                target = {"prev": self.page - 1, "next": self.page + 1}.get(self.action, self.page)
                await _show_panel(interaction, guild, target)

        await _guarded(interaction, self.custom_id, self.page, run)


class PanelPickSelect(discord.ui.DynamicItem[discord.ui.Select], template=PICK_TEMPLATE):
    """「改這一頁的哪一項」：選項只有本頁的項目；選頻道類換成選頻道的畫面，表單類先開表單。"""

    def __init__(self, page: int, *, options: Sequence[discord.SelectOption] = (), disabled: bool = False):
        super().__init__(discord.ui.Select(
            custom_id=f"chpanel:pick:{page}", placeholder="改這一頁的哪一項…", min_values=1, max_values=1,
            options=list(options) or [discord.SelectOption(label="（沒有項目）", value="-")], disabled=disabled or not options,
        ))
        self.page = int(page)

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Select, match, /):
        return cls(int(match["page"]), options=item.options)

    async def callback(self, interaction: discord.Interaction):
        label = self.item.values[0] if self.item.values else "-"

        async def run(guild: discord.Guild) -> None:
            setting = channel_registry.get_setting(label)
            if setting is None:
                await _show_panel(interaction, guild, self.page, notice=_STALE)
                return
            if setting.input is not None:
                await interaction.response.send_modal(InputModal(setting, self.page))
                # 表單取消的話選單會停在剛選的項目（再選同一項 Discord 不會通知 bot）：私訊裡的面板用 bot 的身分重畫
                await _refresh_panel(interaction.message, guild, self.page)
                return
            await edit_screen(interaction, view=await render_channel_pick(guild, setting, self.page, 0))

        await _guarded(interaction, self.custom_id, self.page, run)


class ChannelSelect(discord.ui.DynamicItem[discord.ui.Select], template=CHANNEL_TEMPLATE):
    """選頻道畫面的選單：這一頁的頻道；選了就寫進設定。"""

    def __init__(self, page: int, label_of: str, sub: int, text: Optional[str] = None, *,
                 options: Sequence[discord.SelectOption] = (), kind: str = "頻道"):
        parts = ["chpanel", "chansel", str(int(page)), label_of, str(int(sub))] + ([text] if text is not None else [])
        super().__init__(discord.ui.Select(
            custom_id=":".join(parts), placeholder=f"選一個{kind}…", min_values=1, max_values=1,
            options=list(options) or [discord.SelectOption(label="（沒有項目）", value="-")], disabled=not options,
        ))
        self.page, self.label_of, self.sub, self.text = int(page), label_of, int(sub), text

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Select, match, /):
        return cls(int(match["page"]), match["label"], int(match["sub"]), match["text"], options=item.options)

    async def callback(self, interaction: discord.Interaction):
        value = self.item.values[0] if self.item.values else "-"

        async def run(guild: discord.Guild) -> None:
            setting = channel_registry.get_setting(self.label_of)
            if setting is None:
                await _show_panel(interaction, guild, self.page, notice=_STALE)
                return
            channel = guild.get_channel(int(value)) if value.isdigit() else None
            await _bind(interaction, guild, setting, self.page, channel, self.text)

        await _guarded(interaction, self.custom_id, self.page, run)


class UnbindSelect(discord.ui.DynamicItem[discord.ui.Select], template=UNBIND_TEMPLATE):
    """解除哪一項：選了就刪 key、面板重畫。"""

    def __init__(self, page: int, *, options: Sequence[discord.SelectOption] = ()):
        super().__init__(discord.ui.Select(
            custom_id=f"chpanel:unbsel:{page}", placeholder="解除哪一項的綁定…", min_values=1, max_values=1,
            options=list(options) or [discord.SelectOption(label="（沒有項目）", value="-")], disabled=not options,
        ))
        self.page = int(page)

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Select, match, /):
        return cls(int(match["page"]), options=item.options)

    async def callback(self, interaction: discord.Interaction):
        label = self.item.values[0] if self.item.values else "-"

        async def run(guild: discord.Guild) -> None:
            setting = channel_registry.get_setting(label)
            if setting is None:
                await _show_panel(interaction, guild, self.page, notice=_STALE)
                return
            await _show_panel(interaction, guild, self.page, notice=f"⏳ 正在解除「{setting.label}」…", busy=True)
            try:
                previous = await channel_registry.unbind(setting)
            except ConfigWriteError as exc:
                logger.error("解除「%s」寫入設定檔失敗: %s", setting.label, exc)
                await _show_panel(interaction, guild, self.page, notice=_CONFIG_BROKEN)
                return
            was = f"（原本是 <#{previous}>）" if previous else ""
            await _show_panel(interaction, guild, self.page,
                              notice=f"✅ 已解除「{setting.label}」的綁定{was}。那個功能會停用到再綁一次；已發出去的面板訊息不會刪。")

        await _guarded(interaction, self.custom_id, self.page, run)


class InputModal(discord.ui.Modal):
    """表單類的那一格輸入（例：Telegram 來源）；送出後把面板換成「選目標頻道」，輸入帶在 custom_id 裡。"""

    def __init__(self, setting: ChannelSetting, page: int):
        super().__init__(title=setting.label[:45], timeout=300)
        spec = setting.input
        self.setting, self.page = setting, int(page)
        self.text = discord.ui.TextInput(label=spec.label[:45], placeholder=spec.placeholder[:100], required=True,
                                         max_length=spec.max_length)
        self.add_item(self.text)

    async def on_submit(self, interaction: discord.Interaction):
        async def run(guild: discord.Guild) -> None:
            value = self.setting.input.normalize(self.text.value or "")
            if not value:
                await _show_panel(interaction, guild, self.page, notice=f"⚠️ 「{self.setting.label}」的輸入不可為空，請再選一次。")
                return
            if ":" in value or len(value) > _INPUT_LIMIT:
                await _show_panel(interaction, guild, self.page,
                                  notice=f"⚠️ 「{self.setting.label}」的輸入太長或含冒號（{value[:40]}…），請改短一點再選一次。")
                return
            await edit_screen(interaction, view=await render_channel_pick(guild, self.setting, self.page, 0, value))

        await _guarded(interaction, f"表單 {self.setting.label}", self.page, run)


DYNAMIC_ITEMS = (PanelButton, PanelPickSelect, ChannelSelect, UnbindSelect)
