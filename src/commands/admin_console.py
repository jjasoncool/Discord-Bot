"""管理主控台：群主的管理操作都在一則訊息上輪流顯示幾個畫面（主選單、機器人狀態、頻道設定、角色管理、伺服器資訊、文章轉發、AI），
每個畫面都有「回主控台」，操作結果寫在畫面最上面一行；私訊與伺服器裡同一份，重啟後按鈕照樣能按。

架構定位：介面層（commands）的 view 與流程，沒有自己的 cog。
  上層：`commands.management_commands`（/server_manager、/server_info 進來；`cog_load` 登記這裡的 DynamicItem）。
  下層：各畫面的本體——`commands.admin_status.render_status`、`commands.channel_panel.render`（這兩個模組上有「回主控台」的按鈕、
  是它們 import 這裡；這裡要畫它們時才載入，模組層不互相 import）、各功能的 cog（用 `interaction.client.get_cog` 取，不 import：
  `ManagementCommands.open_roles`、`ArticleCommands` 的 `monitor_status_text`／`api_test_report`／`resend_result`／`baha_sync_result`、
  `RollCallCommands.deliver_admin_panel`、`PersonalityCommands.write_diary_now`／`start_persona_test`）、
  `utils.discord_content`（換畫面、錯誤邊界、訊息上的 custom_id）、`utils.discord_members`（群主檢查、私訊裡找伺服器、取成員）。

介面：
- `send_console(interaction, screen="home")`：回一則主控台（伺服器裡只有本人看得到；私訊裡一般訊息，並刪掉私訊裡上一則主控台）。
- `screen_box(title, notice=, colour=)`／`screen_view(box, *rows)`：畫面的外框與按鈕列，別的模組的畫面也用；`back_button()`：回主控台。
- `render_console(notice=, busy=)`：主選單；`render_info`／`render_info_list`／`render_articles`／`render_api_test`／`render_api_result`／
  `render_ai`：各畫面（都回 LayoutView）；`channel_lines(guild)`／`role_lines(guild)`：伺服器資訊的清單內容。
- `dispatch(interaction, screen, action=, page=)`：按鈕按下去的入口（檢查群主、找伺服器、換畫面、錯誤邊界）。
- `ConsoleButton`：DynamicItem，custom_id `console:<screen>[:<action>[:<page>]]`；`LegacyMenuButton`：舊版選單（伺服器管理三顆、
  伺服器資訊兩顆、角色管理三顆）的 custom_id，按了把那則訊息換成主控台；`DYNAMIC_ITEMS` 給 cog_load 登記。

規則：
- 入口只有 `/server_manager`（`/server_info` 直接開在伺服器資訊那一頁）：私訊裡傳文字不會叫出選單（私訊的對話留給之後的 AI 私聊）。
- 只有群主能用（`_ACCESS`）；每顆按鈕、每個表單都自己檢查，不信任選單是誰叫出來的。
- 每個操作都改主控台這一則（`edit_screen`），不另發訊息：子畫面有「回主控台」或「回上一層」、結果寫在標題下那一行、
  要等的先切成「處理中」（按鈕全灰）再做；一次互動是錯誤邊界（`guarded_screen`），做壞了換回主選單並標錯誤。
- 需要伺服器的操作在私訊裡用 bot 唯一的伺服器（`home_guild`）；bot 不只在一個伺服器就請到伺服器裡操作。
- 要輸入東西的（重送文章、人格測試）開表單，送出後一樣改回主控台那一則（表單從按鈕開的，送出的互動也能改原訊息）。

例外與決策：
- 各功能的本體留在各自的 cog，這裡只負責畫面與接線：斜線指令（/article_manager、/ai_diary、/persona_agent_test、/rollcall_panel）照舊能用。
- 「開始／停止監控」沒放進來：它綁的是「在哪個頻道打指令」，私訊裡沒有這個頻道，仍用 /article_manager。
- 幽靈點名面板是另一則常駐訊息（群主私訊；`RollCallCommands.deliver_admin_panel` 刪舊發新、記位置），主控台只回連結：
  面板常用、要固定找得到；主控台每次 /server_manager 都是新的一則。
- 測 API 的 JSON 檔只有 /article_manager 那條路會附；主控台畫面放文字摘要與截短的預覽（一則新版版面放不下三個檔）。
- 人格 agent 測試與立即寫日記都在背景跑、結果私訊一行（等模型可能超過互動 token 的 15 分鐘，畫面不能停在「處理中」），主控台只講「開始跑了」。
- 同一則訊息的 custom_id 不能重複（Discord 整則退件、錯誤看不出哪兩顆撞）：`screen_view` 組畫面時就擋，翻頁按鈕只在超過一頁時放。
- 私訊裡清舊主控台認的是按鈕的 custom_id：主控台自己的、舊版選單的，和停在子畫面時的頻道綁定／角色管理／機器人狀態按鈕；
  警報私訊（`owner:retest:`）與點名面板（`rollcall:`）是別的訊息，刻意不認。
- 私訊裡每次 /server_manager 會刪掉上一則主控台（翻最近幾則找 bot 自己發、上面有主控台按鈕的），不另記位置；
  伺服器裡的主控台是只有本人看得到的訊息，關掉就沒了，不用清。
"""
from __future__ import annotations

import logging
import re
from typing import Awaitable, Callable, Optional, Sequence

import discord

from sys_settings.admin_console_settings import ADMIN_CONSOLE_SETTINGS
from utils import owner_alerts
from utils.background_tasks import spawn
from utils.discord_content import edit_screen, guarded_screen, message_custom_ids
from utils.discord_members import NO_HOME_GUILD, home_guild, require_access, resolve_member
from utils.utils import paginate, safe_send_interaction_message

logger = logging.getLogger(__name__)

#: 畫面、畫面裡的動作、頁碼；動作不能是純數字，純數字那段才會被當成頁碼
CONSOLE_TEMPLATE = r"console:(?P<screen>[a-z_]+)(?::(?P<action>[a-z][a-z0-9_]*))?(?::(?P<page>\d+))?"
LEGACY_TEMPLATE = (r"(?P<action>role_manager|set_channel|bot_status|list_channels|list_roles|"
                   r"set_role_permissions|list_role_permissions|remove_role_permissions)")
#: 日記與人格測試的 cog 名稱（`commands.llm_commands` 裡 /askai 與這兩個指令是兩個 cog）
AI_COG = "PersonalityCommands"
#: 誰能用；要放寬到管理員只改這裡（私訊裡只放得了群主）
_ACCESS = dict(owner_only=True, allow_dm=True)
_NO_COG = "⚠️ 這個功能的模組沒有載入，請看 log。"
#: 一則新版版面的文字總長上限是 4000，清單類的內容留一點給標題與結果那行
_TEXT_LIMIT = 3600
#: 私訊裡找上一則主控台要翻幾則
_DM_SCAN_LIMIT = 25
#: 選單上的每一組：畫面代號、名稱、說明、按鈕文字
ACTIONS: tuple[tuple[str, str, str, str], ...] = (
    ("status", "機器人狀態", "九項紅黃綠：模型後端、資料庫、爬蟲、Discord 權限…，每項可重測", "開啟"),
    ("channels", "頻道設定", "每一項功能綁在哪個頻道、改綁、解除", "開啟"),
    ("roles", "角色管理", "Trader、Moderator 對應哪些身份組", "開啟"),
    ("info", "伺服器資訊", "列出頻道與身份組的 ID（一頁一頁翻）", "開啟"),
    ("articles", "文章轉發", "監控狀態、測 API、重送一篇、同步巴哈最近 3 天", "開啟"),
    ("rollcall", "幽靈點名", "管理面板私訊給你：開關、手動點名、身份組、點名範圍", "私訊面板"),
    ("ai", "AI", "立即寫今天的日記、對一個人跑人格 agent", "開啟"),
)
_RESEND_KINDS = (("article", "官網公告（文章 ID）"), ("fb", "FB 貼文（資料庫 ID）"),
                 ("it_article", "IT 文章（hkepc_id）"), ("telegram", "Telegram（db id 或 msg #id）"))


# ────────────────────────────────────────────
#  畫面：只看現況，回 LayoutView
# ────────────────────────────────────────────

def screen_box(title: str, *, notice: Optional[str] = None,
               colour: discord.Color = discord.Color.blurple()) -> discord.ui.Container:
    """每個畫面的外框：標題（結果那一行接在標題下）加一條分隔線；別的模組畫的畫面（狀態、頻道、角色）也用它。"""
    box = discord.ui.Container(accent_colour=colour)
    box.add_item(discord.ui.TextDisplay(title + (f"\n{notice[:500]}" if notice else "")))
    box.add_item(discord.ui.Separator())
    return box


def screen_view(box: discord.ui.Container, *rows: Sequence[discord.ui.Item]) -> discord.ui.LayoutView:
    """外框加幾排按鈕（一排最多 5 顆、選單一排一個）組成一個畫面。同一則訊息的 custom_id 不能重複（Discord 會整則退件、
    錯誤訊息看不出是哪兩顆撞），這裡先擋下來。"""
    view = discord.ui.LayoutView(timeout=None)
    view.add_item(box)
    for items in rows:
        row = discord.ui.ActionRow()
        for item in items:
            row.add_item(item)
        view.add_item(row)
    ids = [getattr(getattr(c, "item", c), "custom_id", None) for c in view.walk_children()]
    ids = [cid for cid in ids if cid]
    if len(ids) != len(set(ids)):
        raise ValueError(f"同一則訊息的 custom_id 重複：{sorted(cid for cid in set(ids) if ids.count(cid) > 1)}")
    return view


def _clip(text: str) -> str:
    return text if len(text) <= _TEXT_LIMIT else text[:_TEXT_LIMIT] + "\n…（太長，後面截掉）"


def back_button(*, disabled: bool = False) -> "ConsoleButton":
    """各畫面（含別的模組畫的機器人狀態、頻道設定）共用的「回主控台」。"""
    return ConsoleButton("home", label="↩️ 回主控台", disabled=disabled)


def render_console(*, notice: Optional[str] = None, busy: bool = False) -> discord.ui.LayoutView:
    """主選單：一段標題、每組一段說明加一顆按鈕；busy 時全灰（處理中，防再按一次）。"""
    box = screen_box("## 伺服器管理\n-# 只有群主能用；私訊裡打 /server_manager 也能叫出來", notice=notice)
    for screen, title, desc, label in ACTIONS:
        style = discord.ButtonStyle.primary if screen == "status" else discord.ButtonStyle.secondary
        box.add_item(discord.ui.Section(discord.ui.TextDisplay(f"**{title}**\n-# {desc}"),
                                        accessory=ConsoleButton(screen, label=label, style=style, disabled=busy)))
    return screen_view(box)


# ── 伺服器資訊 ──

def channel_lines(guild: discord.Guild) -> list[tuple[str, str]]:
    """(分組, 一行)：頻道依類別與位置排、照型別分組。"""
    groups = {"📁 類別": [], "📝 文字頻道": [], "🔊 語音頻道": [], "📌 論壇頻道": [], "⚪ 其他頻道": []}
    for channel in sorted(guild.channels, key=lambda c: (c.category.position if c.category else -1, c.position)):
        if isinstance(channel, discord.CategoryChannel):
            group = "📁 類別"
        elif isinstance(channel, discord.TextChannel):
            group = "📝 文字頻道"
        elif isinstance(channel, discord.VoiceChannel):
            group = "🔊 語音頻道"
        elif isinstance(channel, discord.ForumChannel):
            group = "📌 論壇頻道"
        else:
            group = "⚪ 其他頻道"
        groups[group].append(f"{channel.name}（ID: {channel.id}）")
    return [(f"{group}（{len(lines)}）", line) for group, lines in groups.items() for line in lines]


def role_lines(guild: discord.Guild) -> list[tuple[str, str]]:
    """(分組, 一行)：身份組由高到低，@everyone 不列。"""
    roles = [r for r in sorted(guild.roles, key=lambda r: r.position, reverse=True) if not r.is_default()]
    return [(f"🎭 身份組（{len(roles)}）", f"{role.name}（ID: {role.id}）") for role in roles]


def _grouped_page(entries: list[tuple[str, str]], page: int) -> tuple[str, int, int]:
    """分頁後這一頁的文字：組別變了就補標題；從上一頁接著的組別標「（續）」。"""
    size = ADMIN_CONSOLE_SETTINGS.list_page_size
    items, page, pages = paginate(entries, page, size)
    carried = entries[page * size - 1][0] if page else None
    lines: list[str] = []
    current = None
    for group, line in items:
        if group != current:
            if lines:
                lines.append("")
            lines.append(f"**{group}**" + ("（續）" if current is None and group == carried else ""))
            current = group
        lines.append(line)
    return _clip("\n".join(lines) or "（沒有）"), page, pages


def render_info(guild: discord.Guild, *, notice: Optional[str] = None) -> discord.ui.LayoutView:
    """伺服器資訊的入口：兩個清單各一顆按鈕。"""
    roles = sum(1 for r in guild.roles if not r.is_default())
    box = screen_box("## 伺服器資訊\n-# 列出頻道與身份組的 ID，一頁一頁翻", notice=notice, colour=discord.Color.greyple())
    box.add_item(discord.ui.TextDisplay(f"**{guild.name}**　頻道 {len(guild.channels)} 個 · 身份組 {roles} 個"))
    return screen_view(box, [
        ConsoleButton("info", "channels", 0, label="📝 列出頻道", style=discord.ButtonStyle.primary),
        ConsoleButton("info", "roles", 0, label="🎭 列出身份組"),
        back_button(),
    ])


def render_info_list(guild: discord.Guild, kind: str, page: int) -> discord.ui.LayoutView:
    """頻道或身份組的清單一頁；超過一頁才有上一頁／下一頁，頁碼夾回合法範圍。"""
    if kind == "channels":
        title, entries = "📝 頻道列表", channel_lines(guild)
        footnote = "-# 綁定功能用的頻道請走主控台的「頻道設定」，不必抄 ID。"
    else:
        title, entries = "🎭 身份組列表", role_lines(guild)
        footnote = "-# Trader、Moderator 對應哪些身份組在「角色管理」設。"
    text, page, pages = _grouped_page(entries, page)
    box = screen_box(f"## {title}\n-# {guild.name} · 共 {len(entries)} 個 · 第 {page + 1}／{pages} 頁", colour=discord.Color.greyple())
    box.add_item(discord.ui.TextDisplay(text))
    box.add_item(discord.ui.Separator())
    box.add_item(discord.ui.TextDisplay(footnote))
    buttons: list[discord.ui.Item] = []
    if pages > 1:
        buttons.append(ConsoleButton("info", kind, max(page - 1, 0), label="◀ 上一頁", disabled=page <= 0))
        buttons.append(ConsoleButton("info", kind, min(page + 1, pages - 1), label="下一頁 ▶", disabled=page >= pages - 1))
    buttons.append(ConsoleButton("info", label="↩️ 回上一層"))
    return screen_view(box, buttons)


# ── 文章轉發 ──

def render_articles(cog, *, notice: Optional[str] = None, busy: bool = False) -> discord.ui.LayoutView:
    """文章轉發：監控現況直接寫在畫面上；測 API、重送、巴哈同步的結果寫在標題下那一行。"""
    box = screen_box("## 📰 文章轉發\n-# 開始／停止監控要在要發文的頻道用 /article_manager", notice=notice, colour=discord.Color.blue())
    box.add_item(discord.ui.TextDisplay(cog.monitor_status_text()))
    return screen_view(box, [
        ConsoleButton("articles", label="🔄 監控狀態", disabled=busy),
        ConsoleButton("articles", "test", label="🧪 測試 API", disabled=busy),
        ConsoleButton("articles", "resend", label="📨 重送一篇", style=discord.ButtonStyle.primary, disabled=busy),
        ConsoleButton("articles", "baha", label="🔁 同步巴哈最近 3 天", disabled=busy),
    ], [back_button(disabled=busy)])


def render_api_test(*, notice: Optional[str] = None, busy: bool = False) -> discord.ui.LayoutView:
    """測哪個 API：單一個或全部。"""
    box = screen_box("## 🧪 測試 API\n-# 測 scraper 服務的健康檢查與資料端點；結果會換成一頁文字", notice=notice, colour=discord.Color.blue())
    return screen_view(box, [
        ConsoleButton("articles", "test_article", label="主要文章 API", disabled=busy),
        ConsoleButton("articles", "test_fb", label="FB API", disabled=busy),
        ConsoleButton("articles", "test_ptt", label="PTT API", disabled=busy),
        ConsoleButton("articles", "test_all", label="全部 API", style=discord.ButtonStyle.success, disabled=busy),
    ], [ConsoleButton("articles", label="↩️ 回上一層", disabled=busy)])


def render_api_result(text: str) -> discord.ui.LayoutView:
    box = screen_box("## 🧪 API 測試結果", colour=discord.Color.blue())
    box.add_item(discord.ui.TextDisplay(_clip(text)))
    return screen_view(box, [ConsoleButton("articles", "test", label="🔁 再測"), ConsoleButton("articles", label="↩️ 回上一層")])


# ── AI ──

def render_ai(*, notice: Optional[str] = None, busy: bool = False) -> discord.ui.LayoutView:
    box = screen_box("## AI\n-# 立即寫今天的日記、對一個人跑人格 agent", notice=notice, colour=discord.Color.purple())
    box.add_item(discord.ui.TextDisplay("「立即寫日記」在背景產生並發到日記頻道（要等模型，幾十秒到幾分鐘），做完私訊你一行。\n"
                                        "「人格 agent 測試」對一個成員跑一次，預設不寫入資料庫，結果私訊給你。"))
    return screen_view(box, [
        ConsoleButton("ai", "diary", label="🖊️ 立即寫日記", style=discord.ButtonStyle.primary, disabled=busy),
        ConsoleButton("ai", "persona", label="🔬 人格 agent 測試", disabled=busy),
        back_button(disabled=busy),
    ])


# ────────────────────────────────────────────
#  入口與互動：每個操作都改主控台這一則
# ────────────────────────────────────────────

def _cog(interaction: discord.Interaction, name: str):
    return interaction.client.get_cog(name)


async def _ready(interaction: discord.Interaction) -> Optional[discord.Guild]:
    """群主、找得到伺服器兩樣都齊才回伺服器；少一樣就自己回話。"""
    if not await require_access(interaction, **_ACCESS):
        return None
    guild = home_guild(interaction)
    if guild is None:
        await safe_send_interaction_message(interaction, NO_HOME_GUILD, ephemeral=True)
    return guild


#: 停在子畫面的主控台上只有這幾種按鈕（頻道綁定、角色管理、機器人狀態的子畫面），也要認得；
#: 警報私訊的 `owner:retest:`、點名面板的 `rollcall:`／`rollcall_admin_` 是別的訊息，刻意不認
_SUBSCREEN_PREFIXES = ("chpanel:", "roles:", "owner:status:", "owner:panel:")


def _is_console(message) -> bool:
    ids = message_custom_ids(message)
    return any(re.fullmatch(CONSOLE_TEMPLATE, cid) or re.fullmatch(LEGACY_TEMPLATE, cid) or cid.startswith(_SUBSCREEN_PREFIXES)
               for cid in ids)


async def _delete_old_consoles(interaction: discord.Interaction, *, keep: Optional[int]) -> None:
    """私訊裡只留最新的一則主控台：翻最近幾則，bot 自己發、上面有主控台按鈕的都刪；刪不掉只記一行。"""
    me = interaction.client.user
    channel = interaction.channel
    if me is None or channel is None or not hasattr(channel, "history"):
        return
    try:
        async for message in channel.history(limit=_DM_SCAN_LIMIT):
            if message.id == keep or message.author.id != me.id or not _is_console(message):
                continue
            await message.delete()
    except discord.HTTPException as exc:
        logger.warning("主控台：清掉私訊裡的舊主控台失敗：%s", exc)


async def send_console(interaction: discord.Interaction, *, screen: str = "home") -> None:
    """回一則主控台：伺服器裡只有本人看得到；私訊裡是一般訊息，發完刪掉上一則（私訊裡永遠只有一則主控台）。"""
    guild = await _ready(interaction)
    if guild is None:
        return
    view = render_info(guild) if screen == "info" else render_console()
    in_dm = interaction.guild is None
    await safe_send_interaction_message(interaction, view=view, ephemeral=not in_dm)
    if in_dm:
        # 先回應再清舊的：翻歷史與刪訊息要幾百毫秒，不能擠在回應的 3 秒裡
        sent = await interaction.original_response()
        await _delete_old_consoles(interaction, keep=sent.id)


async def dispatch(interaction: discord.Interaction, screen: str, action: Optional[str] = None, page: int = 0) -> None:
    """按鈕按下去：檢查群主、找得到伺服器，再換到那個畫面；做壞了換回主選單並標錯誤。"""
    guild = await _ready(interaction)
    if guild is None:
        return
    handler = _SCREENS.get(screen)
    label = f"主控台：{screen}" + (f":{action}" if action else "")

    async def run() -> None:
        if handler is None:
            await edit_screen(interaction, view=render_console(notice=f"⚠️ 沒有「{screen}」這個功能。"))
            return
        await handler(interaction, guild, action, page)

    await guarded_screen(interaction, label, run, log=logger,
                         rescue=lambda notice: edit_screen(interaction, view=render_console(notice=notice)))


async def _no_cog(interaction: discord.Interaction) -> None:
    await edit_screen(interaction, view=render_console(notice=_NO_COG))


async def _open_home(interaction, guild, action, page) -> None:
    await edit_screen(interaction, view=render_console())


async def _open_status(interaction, guild, action, page) -> None:
    # 狀態面板上有「回主控台」、是它 import 這裡；用到才載入，模組層不互相 import
    from commands import admin_status
    await edit_screen(interaction, view=await admin_status.render_status())


async def _open_channels(interaction, guild, action, page) -> None:
    from commands import channel_panel
    view, _ = await channel_panel.render(guild, 0)
    await edit_screen(interaction, view=view)


async def _open_roles(interaction, guild, action, page) -> None:
    cog = _cog(interaction, "ManagementCommands")
    if cog is None:
        await _no_cog(interaction)
        return
    await cog.open_roles(interaction, guild)


async def _open_info(interaction, guild, action, page) -> None:
    view = render_info_list(guild, action, page) if action in ("channels", "roles") else render_info(guild)
    await edit_screen(interaction, view=view)


async def _open_articles(interaction, guild, action, page) -> None:
    cog = _cog(interaction, "ArticleCommands")
    if cog is None:
        await _no_cog(interaction)
        return
    if action in (None, "status"):
        await edit_screen(interaction, view=render_articles(cog))
    elif action == "test":
        await edit_screen(interaction, view=render_api_test())
    elif action.startswith("test_"):
        # 打 scraper 服務要幾秒：先切成「處理中」再測
        await edit_screen(interaction, view=render_api_test(notice="⏳ 正在測試…", busy=True))
        report = await cog.api_test_report(action[len("test_"):])
        await edit_screen(interaction, view=render_api_result(report.text()))
    elif action == "resend":
        await interaction.response.send_modal(ResendModal())
    elif action == "baha":
        await edit_screen(interaction, view=render_articles(cog, notice="⏳ 正在抓最近 3 天的巴哈討論串…", busy=True))
        text = await cog.baha_sync_result()
        await edit_screen(interaction, view=render_articles(cog, notice=text))
    else:
        await edit_screen(interaction, view=render_articles(cog, notice=f"⚠️ 沒有「{action}」這個操作。"))


async def _open_rollcall(interaction, guild, action, page) -> None:
    cog = _cog(interaction, "RollCallCommands")
    if cog is None:
        await _no_cog(interaction)
        return
    # 面板私訊給按的人（只有群主會走到這）；刪舊發新要幾個 API 呼叫，先切成「處理中」。沒綁點名頻道也發，面板上會標「未綁定」
    await edit_screen(interaction, view=render_console(notice="⏳ 正在把點名管理面板私訊給你…", busy=True))
    text = await cog.deliver_admin_panel(interaction.user, guild)
    await edit_screen(interaction, view=render_console(notice=text))


async def _open_ai(interaction, guild, action, page) -> None:
    cog = _cog(interaction, AI_COG)
    if cog is None:
        await _no_cog(interaction)
        return
    if action == "diary":
        # 等模型可能超過互動 token 的 15 分鐘（排隊等顯示卡、模型重載）：在背景寫、做完私訊一行，畫面不留在「處理中」
        async def write_and_tell() -> None:
            owner_alerts.inform("ai_diary", "manual", await cog.write_diary_now())

        spawn(write_and_tell(), name="主控台手動日記")
        await edit_screen(interaction, view=render_ai(notice="🖊️ 開始寫今天的日記了（要等模型，幾十秒到幾分鐘），做完會私訊你一行。"))
    elif action == "persona":
        await interaction.response.send_modal(PersonaTestModal())
    else:
        await edit_screen(interaction, view=render_ai())


_SCREENS: dict[str, Callable[..., Awaitable[None]]] = {
    "home": _open_home, "status": _open_status, "channels": _open_channels, "roles": _open_roles, "info": _open_info,
    "articles": _open_articles, "rollcall": _open_rollcall, "ai": _open_ai,
}


class ConsoleButton(discord.ui.DynamicItem[discord.ui.Button], template=CONSOLE_TEMPLATE):
    """主控台上的一顆按鈕：custom_id 帶畫面、動作、頁碼，重啟後照樣能按。"""

    def __init__(self, screen: str, action: Optional[str] = None, page: Optional[int] = None, *, label: str,
                 style: discord.ButtonStyle = discord.ButtonStyle.secondary, disabled: bool = False):
        parts = ["console", screen] + ([action] if action else []) + ([str(int(page))] if page is not None else [])
        super().__init__(discord.ui.Button(label=label, style=style, custom_id=":".join(parts), disabled=disabled))
        self.screen, self.action = screen, action
        self.page = int(page) if page is not None else 0

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button, match, /):
        return cls(match["screen"], match["action"], match["page"], label=item.label or "開啟", style=item.style,
                   disabled=item.disabled)

    async def callback(self, interaction: discord.Interaction):
        await dispatch(interaction, self.screen, self.action, self.page)


class ResendModal(discord.ui.Modal, title="重送一篇"):
    """重送文章的表單：類型用選單、ID 用文字；送出後結果寫回主控台那一則。"""

    def __init__(self):
        super().__init__(timeout=600)
        self.kind = discord.ui.Select(
            options=[discord.SelectOption(label=label, value=value) for value, label in _RESEND_KINDS],
            min_values=1, max_values=1)
        self.add_item(discord.ui.Label(text="類型", component=self.kind))
        self.ident = discord.ui.TextInput(label="ID", placeholder="文章 ID、資料庫 ID 或 msg #id", max_length=40)
        self.add_item(self.ident)

    async def on_submit(self, interaction: discord.Interaction):
        guild = await _ready(interaction)
        if guild is None:
            return
        cog = _cog(interaction, "ArticleCommands")
        if cog is None:
            await _no_cog(interaction)
            return
        kind = self.kind.values[0] if self.kind.values else "article"
        ident = self.ident.value.strip()

        async def run() -> None:
            await edit_screen(interaction, view=render_articles(cog, notice=f"⏳ 正在重送 {kind} {ident}…", busy=True))
            text = await cog.resend_result(ident, kind)
            await edit_screen(interaction, view=render_articles(cog, notice=text))

        await guarded_screen(interaction, f"主控台：重送 {kind} {ident}", run, log=logger,
                             rescue=lambda notice: edit_screen(interaction, view=render_articles(cog, notice=notice)))


class PersonaTestModal(discord.ui.Modal, title="人格 agent 測試"):
    """選一個成員跑 persona agent：私訊裡沒有成員選單，用名稱或 ID 找；送出後主控台只講「開始跑了」，結果私訊。"""

    def __init__(self):
        super().__init__(timeout=600)
        self.target = discord.ui.TextInput(label="成員（名稱或 ID）", placeholder="顯示名稱、帳號名稱或數字 ID", max_length=100)
        self.add_item(self.target)
        self.model = discord.ui.TextInput(label="模型（可不填）", required=False, max_length=120,
                                          placeholder="不填就跟夜間批次一樣")
        self.add_item(self.model)
        self.save = discord.ui.Select(options=[
            discord.SelectOption(label="否：只看結果不留痕", value="no", default=True),
            discord.SelectOption(label="是：寫入版本表（和夜間批次一樣）", value="yes"),
        ], min_values=1, max_values=1)
        self.add_item(discord.ui.Label(text="寫入資料庫", component=self.save))

    async def on_submit(self, interaction: discord.Interaction):
        guild = await _ready(interaction)
        if guild is None:
            return
        cog = _cog(interaction, AI_COG)
        if cog is None:
            await _no_cog(interaction)
            return

        async def run() -> None:
            member = await find_member(guild, self.target.value)
            if member is None:
                await edit_screen(interaction, view=render_ai(
                    notice=f"⚠️ 找不到「{self.target.value.strip()}」這個成員，或有好幾個人叫這個名字；可以改填數字 ID。"))
                return
            save = bool(self.save.values) and self.save.values[0] == "yes"
            text = await cog.start_persona_test(interaction, member, self.model.value.strip() or None, save)
            await edit_screen(interaction, view=render_ai(notice=text))

        await guarded_screen(interaction, "主控台：人格 agent 測試", run, log=logger,
                             rescue=lambda notice: edit_screen(interaction, view=render_ai(notice=notice)))


async def find_member(guild: discord.Guild, text: str) -> Optional[discord.Member]:
    """用數字 ID、`<@id>`、顯示名稱、帳號名稱或全域名稱找成員；名字只認完全相同（不分大小寫），對到好幾個人回 None。"""
    raw = (text or "").strip()
    digits = raw.strip("<@!>")
    if digits.isdigit():
        return await resolve_member(guild, int(digits))
    wanted = raw.casefold()
    if not wanted:
        return None
    hits = [m for m in getattr(guild, "members", []) if wanted in {
        (getattr(m, "display_name", "") or "").casefold(), (getattr(m, "name", "") or "").casefold(),
        (getattr(m, "global_name", "") or "").casefold()}]
    return hits[0] if len(hits) == 1 else None


class LegacyMenuButton(discord.ui.DynamicItem[discord.ui.Button], template=LEGACY_TEMPLATE):
    """舊版選單的按鈕（伺服器管理三顆、伺服器資訊兩顆、角色管理三顆；私訊裡那些訊息還在）：按了把那則訊息換成主控台，
    不讓它變成「此互動失敗」。"""

    def __init__(self, action: str, *, label: str = "開啟主控台"):
        super().__init__(discord.ui.Button(label=label, style=discord.ButtonStyle.secondary, custom_id=action))
        self.action = action

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button, match, /):
        return cls(match["action"], label=item.label or "開啟主控台")

    async def callback(self, interaction: discord.Interaction):
        await dispatch(interaction, "home")


DYNAMIC_ITEMS = (ConsoleButton, LegacyMenuButton)
