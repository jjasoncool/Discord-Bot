"""幽靈點名的 Discord 介面：群主私訊裡的管理面板（一則訊息、幾個畫面輪流顯示）、點名訊息上的回覆按鈕。

架構定位：介面層（commands/）。上層：discord_bot 載入這個 cog；管理主控台（commands.admin_console）的「幽靈點名」叫 `open_admin_panel`。
下層：services.community.rollcall_service（抽選、逾期踢人、狀態）、utils.discord_members（權限、home_guild、取成員、身份組清單）、
utils.discord_content（換畫面、錯誤邊界）、utils.utils（設定檔、分頁）。

介面：
- `RollCallCommands.deliver_admin_panel(user, guild) -> str`：把管理面板私訊給這個人：舊面板刪掉、新面板發到私訊、位置記進 runtime，
  回要給人看的結果一句（連結；私訊發不出去也包成一句）；主控台寫在它自己的畫面上。`open_admin_panel(interaction)`：
  `/rollcall_panel` 與舊面板按鈕那條路，defer 後把同一句回成只有本人看得到的訊息。權限由呼叫端先驗。
- `render_home`／`render_pending`／`render_scope`／`render_roles`／`render_pick`：各畫面的 (embed, view)；畫面只看現況，不碰互動。
- `RollCallButton`／`RollCallPickSelect`：面板上的按鈕與身份組選單（DynamicItem，custom_id 帶動作、哪一組、新增或移除、頁碼）；
  `LegacyPanelButton`：舊面板的按鈕，按了把面板搬到私訊；`DYNAMIC_ITEMS` 給 cog_load 登記。
- `RollCallResponseView`：點名訊息上的回覆按鈕，交給 `service.handle_response`。

規則：
- 面板上的每個操作都改面板這一則訊息（`_show`），不另發訊息：子畫面（待回覆、點名範圍、身份組設定、勾選）都有「回上一層」，
  操作結果寫在畫面最上面一行；要等幾秒的（手動點名、算點名範圍）先把面板切成「處理中」、按鈕全灰，做完再換回來。
- 面板只在群主私訊：按鈕與入口都 owner_only＋allow_dm；私訊裡沒有 `interaction.guild`，伺服器一律用 `home_guild` 取。
- 身份組選單由 bot 自己列（由高到低、超過 25 個分頁、一次送出一頁）：Discord 原生身份組選單在私訊裡列不出東西。
- 點名本身（發到哪個頻道、踢人）看 config 的 `rollcall_channel_id`，和面板在哪無關。

例外與決策：
- 分頁不用 `utils.utils.create_paginated_view`：它靠閉包記住選項與頁碼，bot 重啟就失效；常駐面板要重啟後還能翻頁，
  頁碼得寫在 custom_id 裡，選項每次照伺服器現況重列。
- 按鈕的一次互動是錯誤邊界：做到一半出錯要把面板從「處理中」換回主畫面並標錯誤，不能停在全灰沒按鈕。
- 沒綁點名頻道也發面板（面板上標「未綁定」）：面板是設定入口，先看到面板再去綁比較順；手動點名時才擋下並講原因。
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Awaitable, Callable, Optional, Sequence

import discord
from discord import app_commands
from discord.ext import commands

from utils.discord_content import edit_screen, guarded_screen
from utils.discord_members import (
    NO_HOME_GUILD, addable_role_ids, home_guild, require_access, resolve_member, role_ids_after, role_ids_changed, role_name,
    role_select_options, roles_by_position,
)
from utils.utils import CONFIG_FILE, ChannelConfig, ConfigWriteError, ITEMS_PER_PAGE, paginate, safe_send_interaction_message
from services.community.rollcall_service import RollCallService, _now_utc8

logger = logging.getLogger(__name__)

#: 面板上的按鈕與兩條入口的權限：只有群主，私訊裡也只放群主
_ACCESS = dict(owner_only=True, allow_dm=True)
_NOT_READY = "系統尚未就緒。"
_CONFIG_BROKEN = "❌ 設定檔讀取失敗，這次沒有寫入，請檢查 config.json。"
BUTTON_TEMPLATE = (r"rollcall:btn:(?P<action>home|enable|disable|manual|pending|scope|roles|pick)"
                   r"(?::(?P<key>target|exclude))?(?::(?P<mode>add|remove))?(?::(?P<page>\d+))?")
PICK_TEMPLATE = r"rollcall:pick:(?P<key>target|exclude):(?P<mode>add|remove):(?P<page>\d+)"
LEGACY_TEMPLATE = r"rollcall_admin_(?P<action>[a-z_]+)"
#: 面板管的兩組身份組：代號 →（config 的 key、畫面標題、說明）
_ROLE_KEYS = {
    "target": ("rollcall_target_role_ids", "🎯 目標身份組", "擁有這些身份組的成員會被點名。"),
    "exclude": ("rollcall_exclude_role_ids", "🛡️ 排除身份組", "擁有這些身份組的成員不會被點名。"),
}
#: embed 說明欄的上限是 4096，清單再長就截掉
_DESCRIPTION_LIMIT = 4000


# ────────────────────────────────────────────
#  點名訊息上的回覆按鈕（persistent View）
# ────────────────────────────────────────────

class RollCallResponseView(discord.ui.View):
    """點名回覆按鈕（每則點名訊息附帶，persistent）"""

    def __init__(self, service: RollCallService = None, target_user_id: int = None):
        super().__init__(timeout=None)
        self._service = service
        self._target_user_id = target_user_id

    @discord.ui.button(
        label="✋ 我是活人",
        style=discord.ButtonStyle.success,
        custom_id="rollcall_response",
    )
    async def respond(self, interaction: discord.Interaction, button: discord.ui.Button):
        service = self._service
        if service is None:
            cog = interaction.client.get_cog("RollCallCommands")
            if cog:
                service = cog.service

        if service is None:
            await interaction.response.send_message(
                "系統尚未就緒，請稍後再試。", ephemeral=True
            )
            return

        user_id = interaction.user.id

        # 以 message_id 反查這則點名訊息真正對應的目標使用者，
        # 避免重啟後 persistent view 的 _target_user_id 為 None 而失去綁定。
        target_user_id = self._target_user_id
        msg = interaction.message
        if msg is not None:
            for uid_str, info in service.runtime.pending.items():
                if info.get("message_id") == msg.id:
                    target_user_id = int(uid_str)
                    break

        # 只有被點名本人能回覆「自己的」點名訊息，
        # 防止 A 透過 B 的按鈕解掉自己（或誤動）的點名。
        if target_user_id is not None and user_id != target_user_id:
            await interaction.response.send_message(
                "這不是你的點名訊息，只有被點名本人可以回覆。", ephemeral=True
            )
            return

        if not service.runtime.is_pending(user_id):
            await interaction.response.send_message(
                "你目前沒有待回覆的點名，可能已經回覆過了。", ephemeral=True
            )
            return

        await service.handle_response(user_id, interaction)


# ────────────────────────────────────────────
#  畫面：只看現況，回 (embed, view)
# ────────────────────────────────────────────

def _current_role_ids(config_key: str) -> list[int]:
    ids = ChannelConfig.load_config(CONFIG_FILE, caller="RollCallCommands").get(config_key, [])
    return list(ids) if isinstance(ids, list) else []


def _with_notice(embed: discord.Embed, notice: Optional[str]) -> discord.Embed:
    """操作結果放在畫面最上面一行（embed 的說明欄開頭）。"""
    if notice:
        embed.description = f"{notice}\n\n{embed.description}" if embed.description else notice
    return embed


def _clip(text: str) -> str:
    return text if len(text) <= _DESCRIPTION_LIMIT else text[:_DESCRIPTION_LIMIT] + "…"


def _back_button(action: str = "home", key: Optional[str] = None, *, row: Optional[int] = None) -> "RollCallButton":
    return RollCallButton(action, key, label="↩️ 回上一層", row=row)


def render_home(service: RollCallService, guild: discord.Guild, *, notice: Optional[str] = None,
                busy: bool = False) -> tuple[discord.Embed, discord.ui.View]:
    """主畫面：狀態 embed 加全部按鈕。開關兩顆只亮不是現況的那顆；busy 時全灰（處理中，防再按一次）。"""
    embed = _with_notice(service.get_status_embed(guild), notice)
    enabled = bool(service.runtime.enabled)
    view = discord.ui.View(timeout=None)
    for item in (
        RollCallButton("enable", label="✅ 開啟", style=discord.ButtonStyle.success, row=0, disabled=busy or enabled),
        RollCallButton("disable", label="❌ 關閉", style=discord.ButtonStyle.danger, row=0, disabled=busy or not enabled),
        RollCallButton("manual", label="🎲 手動點名", style=discord.ButtonStyle.primary, row=0, disabled=busy),
        RollCallButton("home", label="🔄 刷新狀態", row=0, disabled=busy),
        RollCallButton("pending", label="📋 待回覆清單", row=1, disabled=busy),
        RollCallButton("scope", label="👥 點名範圍", row=1, disabled=busy),
        RollCallButton("roles", "target", label="🎯 目標身份組", row=1, disabled=busy),
        RollCallButton("roles", "exclude", label="🛡️ 排除身份組", row=1, disabled=busy),
    ):
        view.add_item(item)
    return embed, view


def _sub_view(refresh: str) -> discord.ui.View:
    """子畫面的按鈕：重看一次、回主畫面。"""
    view = discord.ui.View(timeout=None)
    view.add_item(RollCallButton(refresh, label="🔄 刷新"))
    view.add_item(_back_button())
    return view


async def render_pending(service: RollCallService, guild: discord.Guild) -> tuple[discord.Embed, discord.ui.View]:
    """待回覆清單。私訊裡 <@id> 要靠客戶端快取才顯示得出名字，幽靈成員多半不在快取；名字自己印、提及留著可點。"""
    pending = service.runtime.get_pending_list()
    if not pending:
        text = "目前沒有待回覆的點名。"
    else:
        now = _now_utc8()
        lines = []
        for item in pending:
            deadline = datetime.fromisoformat(item["deadline"])
            days_left = max(0, (deadline - now).days)
            member = await resolve_member(guild, item["user_id"])
            who = member.display_name if member else "已離開？"
            lines.append(f"• {who}（<@{item['user_id']}>）— 剩餘 {days_left} 天（截止 {deadline.strftime('%m/%d %H:%M')}）")
        text = _clip("\n".join(lines))
    embed = discord.Embed(title="📋 待回覆點名清單", description=text, color=discord.Color.orange())
    embed.set_footer(text=f"共 {len(pending)} 人待回覆")
    return embed, _sub_view("pending")


async def render_scope(service: RollCallService, guild: discord.Guild) -> tuple[discord.Embed, discord.ui.View]:
    """點名範圍：會被點名的人依身份組組合分組計數（要拉全伺服器成員，幾秒）。"""
    target_ids = list(service._get_target_role_ids())
    exclude_ids = list(service._get_exclude_role_ids())
    total = 0
    if not target_ids:
        text = "尚未設定目標身份組。"
    else:
        members = [m async for m in guild.fetch_members(limit=None)]
        candidates = service._collect_candidates_from_list(members, target_ids, exclude_ids)
        if not candidates:
            text = "目前沒有成員會被點名（可能全部被排除、豁免中、或待回覆中）。"
        else:
            # 機器人管理的身份組不列入組合顯示
            managed_role_ids = {r.id for r in guild.roles if r.managed or r.is_default()}
            combo_counts: dict[frozenset[int], int] = {}
            for member in candidates:
                display_roles = frozenset(r.id for r in member.roles if r.id not in managed_role_ids)
                combo_counts[display_roles] = combo_counts.get(display_roles, 0) + 1
            lines = []
            for combo, count in sorted(combo_counts.items(), key=lambda x: -x[1]):
                role_names = sorted(role_name(guild, rid) for rid in combo)
                lines.append(f"• {' + '.join(role_names)}（{count} 人）")
            total = sum(combo_counts.values())
            text = _clip("\n".join(lines))
    embed = discord.Embed(title="👥 點名範圍（身份組組合）", description=text, color=discord.Color.blue())
    embed.set_footer(text=f"共 {total} 人可被點名\n已排除 Bot、管理員、排除身份組、豁免中、待回覆中")
    return embed, _sub_view("scope")


def render_roles(service: RollCallService, guild: discord.Guild, key: str, *,
                 notice: Optional[str] = None) -> tuple[discord.Embed, discord.ui.View]:
    """一組身份組的設定畫面：列目前設定，按「新增」「移除」進勾選畫面。沒得加、沒得減的那顆灰掉。"""
    config_key, title, description = _ROLE_KEYS[key]
    current = roles_by_position(guild, _current_role_ids(config_key))
    current_text = _clip("\n".join(f"• {role_name(guild, rid)}" for rid in current) or "（無）")
    embed = discord.Embed(title=title, description=f"{description}\n\n**目前設定：**\n{current_text}",
                          color=discord.Color.dark_orange())
    view = discord.ui.View(timeout=None)
    view.add_item(RollCallButton("pick", key, "add", 0, label="➕ 新增", style=discord.ButtonStyle.success,
                                 disabled=not addable_role_ids(guild, current)))
    view.add_item(RollCallButton("pick", key, "remove", 0, label="➖ 移除", style=discord.ButtonStyle.danger,
                                 disabled=not current))
    view.add_item(_back_button())
    return _with_notice(embed, notice), view


def render_pick(service: RollCallService, guild: discord.Guild, key: str, mode: str,
                page: int) -> tuple[discord.Embed, discord.ui.View]:
    """勾選畫面：這一頁的身份組一個選單（可多選、一次送出一頁），超過 25 個才有上一頁／下一頁；頁碼夾回合法範圍。
    沒東西可選就退回設定畫面並說原因。"""
    config_key, _, _ = _ROLE_KEYS[key]
    current = _current_role_ids(config_key)
    adding = mode == "add"
    role_ids = addable_role_ids(guild, current) if adding else roles_by_position(guild, current)
    if not role_ids:
        return render_roles(service, guild, key,
                            notice="⚠️ 所有身份組都已設定，沒有可新增的。" if adding else "⚠️ 目前沒有已設定的身份組可移除。")
    shown, page, pages = paginate(role_ids, page, ITEMS_PER_PAGE)
    options = role_select_options(guild, shown)
    verb = "新增" if adding else "移除"
    text = f"勾選要{verb}的身份組（可多選；一次送出一頁）。"
    if pages > 1:
        text += f"\n第 {page + 1}／{pages} 頁，共 {len(role_ids)} 個。"
    embed = discord.Embed(title=f"{'➕' if adding else '➖'} {verb}身份組", description=text,
                          color=discord.Color.green() if adding else discord.Color.red())
    view = discord.ui.View(timeout=None)
    view.add_item(RollCallPickSelect(key, mode, page, options=options))
    if pages > 1:
        view.add_item(RollCallButton("pick", key, mode, max(page - 1, 0), label="上一頁",
                                     style=discord.ButtonStyle.primary, row=1, disabled=page <= 0))
        view.add_item(RollCallButton("pick", key, mode, min(page + 1, pages - 1), label="下一頁",
                                     style=discord.ButtonStyle.primary, row=1, disabled=page >= pages - 1))
    view.add_item(_back_button("roles", key, row=1))
    return embed, view


# ────────────────────────────────────────────
#  互動：每個操作都改面板這一則訊息
# ────────────────────────────────────────────

async def _show(interaction: discord.Interaction, embed: discord.Embed, view: discord.ui.View) -> None:
    """換畫面一律改面板這一則（還沒回應就用回應改；回應過、已經切成「處理中」就改原訊息）。"""
    await edit_screen(interaction, view=view, embed=embed)


async def _ready(interaction: discord.Interaction) -> Optional[tuple[RollCallService, discord.Guild]]:
    """權限、服務、伺服器三樣都齊才回；少一樣就自己回話。"""
    if not await require_access(interaction, **_ACCESS):
        return None
    cog = interaction.client.get_cog("RollCallCommands")
    service = cog.service if cog else None
    if service is None:
        await safe_send_interaction_message(interaction, _NOT_READY, ephemeral=True)
        return None
    guild = home_guild(interaction)
    if guild is None:
        await safe_send_interaction_message(interaction, NO_HOME_GUILD, ephemeral=True)
        return None
    return service, guild


async def _guarded(interaction: discord.Interaction, label: str,
                   run: Callable[[RollCallService, discord.Guild], Awaitable[None]]) -> None:
    """面板上一次操作的外殼：先驗三樣，做壞了把面板換回主畫面並標錯誤（不能停在「處理中」全灰）。"""
    ready = await _ready(interaction)
    if ready is None:
        return
    service, guild = ready
    await guarded_screen(interaction, f"幽靈點名面板：{label}", lambda: run(service, guild), log=logger,
                         rescue=lambda notice: _show(interaction, *render_home(service, guild, notice=notice)))


async def _act_home(interaction, service, guild, key, mode, page) -> None:
    await _show(interaction, *render_home(service, guild))


async def _act_enable(interaction, service, guild, key, mode, page) -> None:
    await _set_enabled(interaction, service, guild, True)


async def _act_disable(interaction, service, guild, key, mode, page) -> None:
    await _set_enabled(interaction, service, guild, False)


async def _set_enabled(interaction: discord.Interaction, service: RollCallService, guild: discord.Guild, enabled: bool) -> None:
    service.runtime.enabled = enabled
    service.runtime.save()
    logger.info("幽靈點名：%s 已%s自動點名", interaction.user, "開啟" if enabled else "關閉")
    await _show(interaction, *render_home(service, guild, notice=f"{'✅ 已開啟' if enabled else '⏸️ 已關閉'}自動點名。"))


async def _act_manual(interaction, service, guild, key, mode, page) -> None:
    # 點名訊息發到綁定的點名頻道：沒綁或頻道不見了要講清楚，不然服務層只記 warning、這裡會變成「沒人可抽」
    channel_id = service._get_channel_id()
    if not channel_id:
        await _show(interaction, *render_home(service, guild, notice="⚠️ 還沒綁點名頻道：到主控台的「頻道設定」綁一個文字頻道。"))
        return
    if interaction.client.get_channel(channel_id) is None:
        await _show(interaction, *render_home(
            service, guild, notice=f"⚠️ 找不到點名頻道（ID: {channel_id}），可能被刪了：到「頻道設定」重綁。"))
        return
    # 「處理中」只擋得住同一個畫面上的重按；另一個裝置、或剛好撞上自動排程的那一場，服務層的鎖會略過這次，這裡先講清楚
    if service.picking:
        await _show(interaction, *render_home(service, guild, notice="⏳ 正在抽選中（自動排程或另一次手動），等它做完再按。"))
        return
    # 要拉全伺服器成員、逐一發訊息，幾秒：先把面板切成「處理中」（按鈕全灰，群主不會以為沒按到再抽一批）
    await _show(interaction, *render_home(service, guild, notice="⏳ 正在抽選…", busy=True))
    picked = await service.do_roll_call(manual=True)
    if picked:
        notice = f"✅ 已手動點名 {len(picked)} 人：{', '.join(m.display_name for m in picked)}"
    else:
        notice = "⚠️ 沒有符合資格的成員可抽選（可能全部在豁免期或待回覆中，或還沒設目標身份組）。"
    await _show(interaction, *render_home(service, guild, notice=notice))


async def _act_pending(interaction, service, guild, key, mode, page) -> None:
    await _show(interaction, *await render_pending(service, guild))


async def _act_scope(interaction, service, guild, key, mode, page) -> None:
    if service._get_target_role_ids():
        # 拉全伺服器成員要幾秒：先切成「處理中」再算
        await _show(interaction, *render_home(service, guild, notice="⏳ 正在計算點名範圍…", busy=True))
    await _show(interaction, *await render_scope(service, guild))


async def _act_roles(interaction, service, guild, key, mode, page) -> None:
    await _show(interaction, *render_roles(service, guild, key))


async def _act_pick(interaction, service, guild, key, mode, page) -> None:
    await _show(interaction, *render_pick(service, guild, key, mode, page))


_ACTIONS = {
    "home": _act_home, "enable": _act_enable, "disable": _act_disable, "manual": _act_manual,
    "pending": _act_pending, "scope": _act_scope, "roles": _act_roles, "pick": _act_pick,
}


async def _write_roles(config_key: str, mode: str, role_ids: Sequence[int]) -> None:
    """把這幾個身份組加進或拿掉設定檔（重讀最新內容、只動這幾個）；寫不進去丟 ConfigWriteError。"""
    await ChannelConfig.update_config(lambda c: c.__setitem__(config_key, role_ids_after(c.get(config_key), mode, role_ids)),
                                      CONFIG_FILE, caller="RollCallCommands")


async def _apply_roles(interaction: discord.Interaction, service: RollCallService, guild: discord.Guild,
                       key: str, mode: str, role_ids: Sequence[int]) -> None:
    """勾好送出：寫設定檔，回到那一組的設定畫面並在最上面講結果。"""
    config_key, _, _ = _ROLE_KEYS[key]
    adding = mode == "add"
    changed = role_ids_changed(_current_role_ids(config_key), role_ids, mode)
    verb = "新增" if adding else "移除"
    if not changed:
        notice = "⚠️ 勾的身份組都已經在設定裡了。" if adding else "⚠️ 勾的身份組都不在設定裡。"
    else:
        # 名字在寫檔前就算好：寫完才查，查不到會變成「寫進去了但畫面說失敗」
        names = [role_name(guild, rid) for rid in changed]
        try:
            await _write_roles(config_key, mode, changed)
        except ConfigWriteError as exc:
            logger.error("幽靈點名：%s身份組寫入設定檔失敗: %s", verb, exc)
            notice = _CONFIG_BROKEN
        else:
            logger.info("幽靈點名：%s %s %s → %s", interaction.user, verb, config_key, ", ".join(names))
            notice = f"✅ 已{verb} {len(names)} 個身份組：{', '.join(f'**{n}**' for n in names)}"
    await _show(interaction, *render_roles(service, guild, key, notice=notice))


class RollCallButton(discord.ui.DynamicItem[discord.ui.Button], template=BUTTON_TEMPLATE):
    """面板上的一顆按鈕：custom_id 帶動作，身份組的還帶哪一組、新增或移除、頁碼，重啟後照樣能按。"""

    def __init__(self, action: str, key: Optional[str] = None, mode: Optional[str] = None, page: Optional[int] = None, *,
                 label: str, style: discord.ButtonStyle = discord.ButtonStyle.secondary,
                 row: Optional[int] = None, disabled: bool = False):
        parts = ["rollcall", "btn", action] + [p for p in (key, mode) if p] + ([str(int(page))] if page is not None else [])
        super().__init__(discord.ui.Button(label=label, style=style, custom_id=":".join(parts), disabled=disabled), row=row)
        self.action, self.key, self.mode = action, key, mode
        self.page = int(page) if page is not None else 0

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button, match, /):
        return cls(match["action"], match["key"], match["mode"], match["page"],
                   label=item.label or "…", style=item.style, disabled=item.disabled)

    async def callback(self, interaction: discord.Interaction):
        await _guarded(interaction, self.custom_id,
                       lambda service, guild: _ACTIONS[self.action](interaction, service, guild, self.key, self.mode, self.page))


class RollCallPickSelect(discord.ui.DynamicItem[discord.ui.Select], template=PICK_TEMPLATE):
    """勾選畫面的選單：選項是這一頁的身份組，可多選；送出就寫設定檔。"""

    def __init__(self, key: str, mode: str, page: int, *, options: Sequence[discord.SelectOption] = ()):
        opts = list(options) or [discord.SelectOption(label="（沒有項目）", value="-")]
        super().__init__(discord.ui.Select(
            custom_id=f"rollcall:pick:{key}:{mode}:{int(page)}",
            placeholder=f"勾選要{'新增' if mode == 'add' else '移除'}的身份組…",
            min_values=1, max_values=len(opts), options=opts, disabled=not options,
        ))
        self.key, self.mode, self.page = key, mode, int(page)

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Select, match, /):
        return cls(match["key"], match["mode"], int(match["page"]), options=item.options)

    async def callback(self, interaction: discord.Interaction):
        role_ids = [int(v) for v in self.item.values if v.isdigit()]
        await _guarded(interaction, self.custom_id,
                       lambda service, guild: _apply_roles(interaction, service, guild, self.key, self.mode, role_ids))


class LegacyPanelButton(discord.ui.DynamicItem[discord.ui.Button], template=LEGACY_TEMPLATE):
    """舊面板（還留在點名頻道那張）的按鈕：按了就把面板搬到私訊（刪舊的、發新的），不讓它變成「此互動失敗」。"""

    def __init__(self, action: str, *, label: str = "開啟面板"):
        super().__init__(discord.ui.Button(label=label, style=discord.ButtonStyle.secondary, custom_id=f"rollcall_admin_{action}"))
        self.action = action

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button, match, /):
        return cls(match["action"], label=item.label or "開啟面板")

    async def callback(self, interaction: discord.Interaction):
        if not await require_access(interaction, **_ACCESS):
            return
        cog = interaction.client.get_cog("RollCallCommands")
        if cog is None:
            await safe_send_interaction_message(interaction, _NOT_READY, ephemeral=True)
            return
        await cog.open_admin_panel(interaction)


DYNAMIC_ITEMS = (RollCallButton, RollCallPickSelect, LegacyPanelButton)


# ────────────────────────────────────────────
#  Cog
# ────────────────────────────────────────────

class RollCallCommands(commands.Cog):
    """幽靈點名管理"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.service = RollCallService(bot, response_view_factory=RollCallResponseView)

    async def cog_load(self):
        # 點名訊息上的回覆按鈕是固定 custom_id 的 persistent view；面板的按鈕狀態在 custom_id 裡，走 DynamicItem
        self.bot.add_view(RollCallResponseView())
        self.bot.add_dynamic_items(*DYNAMIC_ITEMS)
        logger.info("已註冊 RollCall persistent views")

        # 啟動背景排程
        await self.service.start()

    async def cog_unload(self):
        self.bot.remove_dynamic_items(*DYNAMIC_ITEMS)
        await self.service.stop()

    @app_commands.command(
        name="rollcall_panel",
        description="把幽靈點名管理面板私訊給你（只有群主；私訊裡也能用）",
    )
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=False)
    async def send_admin_panel(self, interaction: discord.Interaction):
        if not await require_access(interaction, **_ACCESS):
            return
        await self.open_admin_panel(interaction)

    async def open_admin_panel(self, interaction: discord.Interaction) -> None:
        """/rollcall_panel 與舊面板按鈕那條路：把面板私訊給按的人，再用只有本人看得到的訊息回連結。權限由呼叫端先驗（只有群主）。"""
        guild = home_guild(interaction)
        if guild is None:
            await safe_send_interaction_message(interaction, NO_HOME_GUILD, ephemeral=True)
            return
        # 從舊面板按進來是按鈕互動，defer 要 thinking=True 才有「思考中」；斜線指令那條本來就有，thinking 不影響
        await interaction.response.defer(thinking=True, ephemeral=True)
        await interaction.followup.send(await self.deliver_admin_panel(interaction.user, guild), ephemeral=True)

    async def deliver_admin_panel(self, user, guild: discord.Guild) -> str:
        """把管理面板私訊給這個人：舊面板刪掉、新面板發到私訊、位置記進 runtime；回要給人看的結果一句（連結、舊面板刪不掉的附註）。
        私訊發不出去（沒開伺服器成員私訊、封鎖了 bot）也包成一句，呼叫端的畫面不會停在「處理中」。"""
        dm = await user.create_dm()
        leftover = await self._remove_old_panel(dm)
        try:
            message = await self._post_panel(dm, guild)
        except discord.HTTPException as exc:
            logger.warning("幽靈點名：面板私訊發不出去：%s", exc)
            return f"❌ 面板私訊發不出去（{exc.text or type(exc).__name__}）：確認你允許伺服器成員私訊、沒有封鎖 bot。"
        text = f"✅ 點名管理面板已私訊給你：{message.jump_url}"
        if leftover:
            text += f"\n⚠️ {leftover}"
        return text

    async def _remove_old_panel(self, new_channel) -> Optional[str]:
        """刪掉上一張面板（可能還在公開頻道）。刪不掉就回一句要手動刪哪則的話，不擋發新的。"""
        runtime = self.service.runtime
        old_msg_id, old_channel_id = runtime.admin_panel_message_id, runtime.channel_id
        if not old_msg_id:
            return None
        # 私訊頻道重啟後不在快取裡；面板固定在群主私訊，所以快取裡找不到的就是正要發的這個私訊
        old_channel = (self.bot.get_channel(old_channel_id) if old_channel_id else None) or new_channel
        try:
            old_msg = await old_channel.fetch_message(old_msg_id)
            await old_msg.delete()
        except discord.NotFound:
            return None   # 已經被手動刪了
        except discord.HTTPException as exc:
            logger.warning("幽靈點名：舊面板刪不掉 channel=%s message=%s：%s", old_channel_id, old_msg_id, exc)
            where = getattr(old_channel, "mention", None) or "私訊"
            return f"舊面板刪不掉（{where} 的訊息 {old_msg_id}：{exc.text or type(exc).__name__}），請手動刪掉。"
        return None

    async def _post_panel(self, channel, guild: discord.Guild) -> discord.Message:
        embed, view = render_home(self.service, guild)
        message = await channel.send(embed=embed, view=view)
        runtime = self.service.runtime
        runtime.admin_panel_message_id = message.id
        runtime.channel_id = channel.id
        runtime.save()
        return message


async def setup(bot: commands.Bot):
    await bot.add_cog(RollCallCommands(bot))
