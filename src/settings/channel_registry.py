"""頻道功能的登記表：哪個功能綁哪種頻道、存到 config.json 的哪個 key、綁定後要做什麼；綁定與解除的唯一寫入點。

架構定位：基礎層（settings）裡的 Discord 工具（登記在 `test_layering.DISCORD_HELPERS_IN_BASE`），依賴 discord.py、
  `utils.utils`（config.json 讀寫）、`shared.telegram`（Telegram 來源名稱正規化）。
  上層：`commands.channel_panel`（頻道綁定面板）、`commands.management_commands`（/server_manager）；各功能的設定模組只讀這裡登記的 key。
  下層：`ChannelConfig`；綁定後動作透過 `ctx.bot.get_cog(...)` 叫各 cog（寫在各功能的登記旁邊）。

介面：
- `register_channel(label, channel_type, config_key, *, color, desc)`：登記一個「選頻道」功能；當裝飾器用就把下方函式設成綁定後動作。
- `register_custom(label, *, color, desc, describe=)`：登記一個自己接管互動的功能（例：Telegram 路由先開表單）；
  `describe(config)` 回面板上「現在設了什麼」的一行。
- `all_settings()`／`get_setting(label)`／`display_order()`（面板的順序：論壇、文字、語音分組，表單類最後）。
- `bound_channel_id(setting)`／`telegram_routes(config=None)`：現在綁哪裡（沒綁回 None／空 dict）。
- `apply(setting, *, bot, guild, channel) -> str`：寫進 config.json、跑綁定後動作，回要附在成功訊息後的附註；寫不進去丟 `ConfigWriteError`。
- `unbind(setting) -> Optional[int]`：刪掉那個 key，回原本的頻道 id（本來就沒綁回 None）。
- `type_icon(channel_type)`／`type_name(channel_type)`：面板與選單用的圖示與名稱（只認文字、論壇、語音）。

規則：
- 綁頻道寫 config.json 只走 `apply`／`unbind`（守衛擋別處直接寫 `*_channel_id`）；UI 只管畫面。
- 選頻道一律用 bot 自己列的清單（`create_paginated_view`）：Discord 原生的頻道選單在私訊裡列不出伺服器的頻道，而主控台在私訊裡。
- 三種登記方式：純綁頻道直接呼叫 `register_channel(...)`；綁頻道＋後續動作用 `@register_channel(...)` 裝飾 on_set；
  不是「選一個頻道存 id」的（Telegram 路由要先輸入來源）用 `@register_custom(...)` 裝飾一個 handler，由它自己接管 interaction。
- 登記順序＝組內顯示順序。

例外與決策：
- 綁定後動作可能失敗（cog 沒載入、沒權限發面板）：寫入已經完成，動作失敗只回附註、不回滾——頻道綁好是主要目的。
- 解除綁定只刪 key、不刪已發出去的面板訊息：那些訊息要不要留由人決定。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional

import discord

from utils.discord_members import home_guild
from utils.utils import ChannelConfig, ConfigWriteError, create_paginated_view, safe_send_interaction_message
from shared.telegram import normalize_channel_identifier

logger = logging.getLogger(__name__)


@dataclass
class ChannelSetContext:
    """傳給 on_set hook 的情境，包含設定頻道後可能需要的一切。"""

    guild: discord.Guild
    channel: discord.abc.GuildChannel
    config: dict                  # 寫入後的設定（複本；頻道已經先寫進檔案，hook 讀設定檔就拿得到新頻道）
    bot: Any                      # commands.Bot；避免額外 import 用 Any


# on_set 簽名：吃 ctx，回傳要附加到成功訊息後面的 note（沒有就回 None）
OnSet = Callable[[ChannelSetContext], Awaitable[Optional[str]]]
# custom_handler 簽名：完全接管該次互動（例如 send_modal），不走標準選頻道流程
CustomHandler = Callable[[discord.Interaction], Awaitable[None]]


# describe 簽名：吃 config.json 的內容，回面板上「現在設了什麼」的一行（custom 類用；選頻道類顯示綁的頻道）
Describe = Callable[[dict], str]


@dataclass
class ChannelSetting:
    label: str                                  # 選單顯示名稱，例："音樂語音頻道"
    channel_type: Optional[discord.ChannelType] # 要綁的頻道型別；custom_handler 類為 None
    config_key: Optional[str]                   # 存到 config.json 的 key；custom_handler 類可為 None
    color: discord.Color                        # 選單 / embed 用色
    desc: str                                   # 選單說明
    on_set: Optional[OnSet] = None              # 設定完成後要做的事，沒有就 None
    custom_handler: Optional[CustomHandler] = None  # 走特殊輸入流程，取代標準選頻道
    describe: Optional[Describe] = None         # custom 類在面板上顯示現況的一行


_REGISTRY: list[ChannelSetting] = []

#: 面板的分組順序與圖示（圖示沿用選頻道清單的那三個）；不在表裡的（表單類）排最後
TYPE_ORDER: tuple[discord.ChannelType, ...] = (discord.ChannelType.forum, discord.ChannelType.text, discord.ChannelType.voice)
_TYPE_LABELS: dict[Optional[discord.ChannelType], tuple[str, str]] = {
    discord.ChannelType.forum: ("📌", "論壇頻道"),
    discord.ChannelType.text: ("📝", "文字頻道"),
    discord.ChannelType.voice: ("🔊", "語音頻道"),
}


def type_icon(channel_type: Optional[discord.ChannelType]) -> str:
    return _TYPE_LABELS.get(channel_type, ("⚙️", "其他設定"))[0]


def type_name(channel_type: Optional[discord.ChannelType]) -> str:
    return _TYPE_LABELS.get(channel_type, ("⚙️", "其他設定"))[1]


def register_channel(
    label: str,
    channel_type: discord.ChannelType,
    config_key: str,
    *,
    color: discord.Color,
    desc: str,
) -> Callable[[OnSet], OnSet]:
    """登記一個「選頻道」功能。

    可當一般函式呼叫（無 hook），也可當裝飾器用（把下方函式設為 on_set）。
    """
    setting = ChannelSetting(label, channel_type, config_key, color, desc)
    _REGISTRY.append(setting)

    def deco(fn: OnSet) -> OnSet:
        setting.on_set = fn
        return fn

    return deco


def register_custom(
    label: str,
    *,
    color: discord.Color,
    desc: str,
    describe: Optional[Describe] = None,
) -> Callable[[CustomHandler], CustomHandler]:
    """登記一個「特殊輸入流程」功能（裝飾它的 handler）；`describe` 回面板上現況的一行。"""
    setting = ChannelSetting(label, None, None, color, desc, describe=describe)
    _REGISTRY.append(setting)

    def deco(fn: CustomHandler) -> CustomHandler:
        setting.custom_handler = fn
        return fn

    return deco


def all_settings() -> list[ChannelSetting]:
    return list(_REGISTRY)


def get_setting(label: str) -> Optional[ChannelSetting]:
    return next((s for s in _REGISTRY if s.label == label), None)


def display_order() -> list[ChannelSetting]:
    """面板的順序：依 `TYPE_ORDER` 分組、組內照登記順序；表單類（沒有頻道型別）排最後。"""
    grouped = [s for channel_type in TYPE_ORDER for s in _REGISTRY if s.channel_type == channel_type]
    return grouped + [s for s in _REGISTRY if s.channel_type not in TYPE_ORDER]


async def bound_channel_id(setting: ChannelSetting) -> Optional[int]:
    """這一項現在綁的頻道 id；沒綁（缺 key 或佔位符）回 None。"""
    if not setting.config_key:
        return None
    return await ChannelConfig.get_configured_id(setting.config_key, caller="channel_registry")


def telegram_routes(config: Optional[dict] = None) -> dict[str, list[int]]:
    """config.json 的 Telegram 路由：來源 → Discord 頻道 id 清單（壞掉的值略過、去重）。"""
    if config is None:
        config = ChannelConfig.load_config(caller="channel_registry")
    routes = config.get("telegram_channel_routes")
    cleaned: dict[str, list[int]] = {}
    if not isinstance(routes, dict):
        return cleaned
    for source, raw in routes.items():
        if isinstance(raw, list):
            candidates = raw
        elif raw in (None, ""):
            candidates = []
        else:
            candidates = [raw]
        ids: list[int] = []
        for rid in candidates:
            try:
                rid_int = int(rid)
            except (TypeError, ValueError):
                continue
            if rid_int > 0 and rid_int not in ids:
                ids.append(rid_int)
        cleaned[str(source)] = ids
    return cleaned


async def apply(setting: ChannelSetting, *, bot: Any, guild: discord.Guild, channel: discord.abc.GuildChannel) -> str:
    """把頻道寫進 config.json（只改這一個 key），再跑綁定後動作；回要附在成功訊息後面的附註（沒有就空字串）。
    寫不進去丟 `ConfigWriteError`，什麼都沒改。"""
    if not setting.config_key:
        raise ValueError(f"「{setting.label}」不是選頻道的設定")
    config = await ChannelConfig.update_config(
        lambda c: c.__setitem__(setting.config_key, int(channel.id)), caller="channel_registry")
    logger.info("%s 已設定為 %s (ID: %s)", setting.label, getattr(channel, "name", "?"), channel.id)
    if setting.on_set is None:
        return ""
    note = await setting.on_set(ChannelSetContext(guild=guild, channel=channel, config=config, bot=bot))
    return note or ""


async def unbind(setting: ChannelSetting) -> Optional[int]:
    """解除綁定：刪掉那個 key（各功能讀到沒綁就靜默）。回原本的頻道 id，本來就沒綁回 None。"""
    if not setting.config_key:
        return None
    previous = await bound_channel_id(setting)
    await ChannelConfig.update_config(lambda c: c.pop(setting.config_key, None), caller="channel_registry")
    logger.info("%s 已解除綁定（原本 %s）", setting.label, previous)
    return previous


# ════════════════════════════ 功能登記 ════════════════════════════
# 順序即選單顯示順序，與重構前一致。

register_channel(
    "交易頻道",
    discord.ChannelType.forum,
    "trade_forum_channel_id",
    color=discord.Color.blue(),
    desc="交易記錄頻道",
)

register_channel(
    "交易紀錄封存",
    discord.ChannelType.forum,
    "archive_channel_id",
    color=discord.Color.dark_grey(),
    desc="交易紀錄封存頻道",
)

register_channel(
    "論壇文章頻道",
    discord.ChannelType.forum,
    "forum_article_channel_id",
    color=discord.Color.gold(),
    desc="自動發布論壇文章的論壇頻道",
)

register_channel(
    "購物車交付",
    discord.ChannelType.text,
    "cart_delivery_channel_id",
    color=discord.Color.green(),
    desc="購物車交付通知頻道",
)


# ── 商品上架論壇：設定完自動發置頂的上架說明（行為依賴 ShopCommands cog）──
@register_channel(
    "商品上架論壇",
    discord.ChannelType.forum,
    "shop_forum_channel_id",
    color=discord.Color.gold(),
    desc="觀星者上架商品的論壇（綁定後自動發置頂的上架說明）",
)
async def _on_set_shop(ctx: ChannelSetContext) -> Optional[str]:
    cog = ctx.bot.get_cog("ShopCommands")
    shop = getattr(cog, "shop", None)
    if shop is None:
        return "\n⚠️ 商品上架模組尚未載入，置頂的上架說明沒有發"
    try:
        return "\n" + await shop.ensure_guide(ctx.channel)
    except Exception as e:
        logger.error(f"設定商品上架論壇後發置頂上架說明失敗: {e}", exc_info=True)
        return "\n⚠️ 置頂的上架說明發送失敗，請確認 bot 在這個論壇有發文、管理貼文的權限後再綁定一次。"

register_channel(
    "官方文章更新",
    discord.ChannelType.text,
    "article_monitor_channel_id",
    color=discord.Color.orange(),
    desc="自動發送官方最新文章的頻道",
)


# ── Telegram 路由：特殊輸入流程（表單輸入來源 → 只有本人看得到的文字頻道清單選目標）──
class _TelegramRouteInputModal(discord.ui.Modal):
    """第一步：輸入來源。送出後回一則只有本人看得到的頻道清單選目標：清單是 bot 自己列的，私訊裡也能用。"""

    def __init__(self, guild: discord.Guild):
        super().__init__(title="設定 Telegram 路由", timeout=300)
        self.guild = guild
        self.telegram_source = discord.ui.TextInput(
            label="Telegram 來源（名稱或 chat_id）",
            placeholder="例如：Seele_WW_leak、@Seele_WW_leak、-1001234567890",
            required=True,
            max_length=128,
        )
        self.add_item(self.telegram_source)

    async def on_submit(self, modal_interaction: discord.Interaction):
        source_raw = self.telegram_source.value.strip()
        source_key = normalize_channel_identifier(source_raw).lower()
        if not source_key:
            await safe_send_interaction_message(modal_interaction, "來源值不可為空，請重新設定。", ephemeral=True)
            return
        channels = [c for c in self.guild.channels if c.type == discord.ChannelType.text]
        if not channels:
            await safe_send_interaction_message(modal_interaction, "這個伺服器沒有文字頻道，沒辦法設路由。", ephemeral=True)
            return
        options = [
            discord.SelectOption(label=c.name[:100], value=str(c.id), description=f"ID: {c.id}",
                                 emoji=type_icon(discord.ChannelType.text))
            for c in channels
        ]

        async def on_select(pick: discord.Interaction, value: str) -> None:
            selected_channel_id = int(value)

            def add_route(config: dict) -> None:
                routes = telegram_routes(config)
                normalized_ids = routes.get(source_key, [])
                if selected_channel_id not in normalized_ids:
                    normalized_ids.append(selected_channel_id)
                routes[source_key] = normalized_ids
                config["telegram_channel_routes"] = routes

            try:
                config = await ChannelConfig.update_config(add_route, caller="channel_registry")
            except ConfigWriteError as e:
                logger.error(f"Telegram 路由寫入設定檔失敗: {e}")
                await safe_send_interaction_message(
                    pick, "❌ 設定檔讀取失敗，這次沒有寫入，請檢查 config.json。", ephemeral=True)
                return
            normalized_ids = config["telegram_channel_routes"][source_key]
            await pick.response.edit_message(
                content=f"✅ 已新增 Telegram 路由：`{source_key}` -> <#{selected_channel_id}>\n目前目標頻道數：{len(normalized_ids)}",
                embed=None, view=None)

        title = f"Telegram 路由：{source_key}"
        description = "選擇要轉發到的 Discord 文字頻道。同一個來源可以轉到好幾個頻道：再設一次就多一個。"
        _, view = create_paginated_view(options, "選擇要轉發的 Discord 文字頻道…", title, description,
                                        discord.Color.teal(), on_select, custom_id_prefix="telegram_route_target")
        await safe_send_interaction_message(
            modal_interaction, embed=discord.Embed(title=title, description=description, color=discord.Color.teal()),
            view=view, ephemeral=True)


def _describe_telegram_routes(config: dict) -> str:
    """面板上的現況：每條來源轉到哪些頻道。"""
    routes = telegram_routes(config)
    if not routes:
        return "（還沒有路由）"
    return "、".join(f"{source} → " + ("、".join(f"<#{cid}>" for cid in ids) or "（沒有頻道）")
                     for source, ids in routes.items())


@register_custom(
    "Telegram 路由設定",
    color=discord.Color.teal(),
    desc="先輸入 Telegram 來源（名稱/chat_id），再選要轉發到的 Discord 文字頻道",
    describe=_describe_telegram_routes,
)
async def _handle_telegram_route(interaction: discord.Interaction):
    guild = home_guild(interaction)
    if guild is None:
        await safe_send_interaction_message(interaction, "bot 不只在一個伺服器裡，請到伺服器裡用 /server_manager 操作。", ephemeral=True)
        return
    await interaction.response.send_modal(_TelegramRouteInputModal(guild))


# ── 自我介紹頻道：設定完自動發填寫面板（行為依賴 ManagementCommands cog）──
@register_channel(
    "自我介紹頻道",
    discord.ChannelType.text,
    "intro_channel_id",
    color=discord.Color.purple(),
    desc="使用者填寫自我介紹的頻道",
)
async def _on_set_intro(ctx: ChannelSetContext) -> Optional[str]:
    cog = ctx.bot.get_cog("ManagementCommands")
    if cog is None:
        return "\n⚠️ ManagementCommands Cog 尚未載入，面板未自動發送"
    try:
        panel_message, deleted_old = await cog.intro_panel.bump(ctx.channel)
        note = f"\n🤖 已自動發送填寫面板:{panel_message.jump_url}"
        if deleted_old:
            note += "\n🧹 舊頻道面板已刪除。"
        return note
    except Exception as e:
        logger.error(f"設定自我介紹頻道後自動發送面板失敗: {e}", exc_info=True)
        return "\n⚠️ 自動發送面板失敗，系統會在下一次有人送出表單時自動重新 bump。"


register_channel(
    "音樂語音頻道",
    discord.ChannelType.voice,
    "music_voice_channel_id",
    color=discord.Color.red(),
    desc="音樂機器人掛機與點歌的語音頻道",
)

register_channel(
    "幽靈點名頻道",
    discord.ChannelType.text,
    "rollcall_channel_id",
    color=discord.Color.dark_orange(),
    desc="幽靈點名訊息與管理面板的文字頻道",
)


# 有後續動作：設定完自動部署社群查詢面板（行為就寫在它旁邊）。
@register_channel(
    "社群查詢頻道",
    discord.ChannelType.text,
    "community_lookup_channel_id",
    color=discord.Color.teal(),
    desc="社群 ID 查詢（PTT / 巴哈）的面板頻道",
)
async def _on_set_community_lookup(ctx: ChannelSetContext) -> Optional[str]:
    community_cog = ctx.bot.get_cog("CommunityLookupCommands")
    if community_cog is None:
        return "\n⚠️ CommunityLookupCommands Cog 尚未載入，面板未自動部署"
    try:
        # 頻道在呼叫 hook 之前就已寫進設定檔，cog 內 get_panel_channel 讀得到新頻道
        panel_message, deleted_old = await community_cog.panel.bump(ctx.channel)
        note = f"\n🤖 已自動部署社群查詢面板：{panel_message.jump_url}"
        if deleted_old:
            note += "\n🧹 舊頻道面板已刪除。"
        return note
    except Exception as e:
        logger.error(f"設定社群查詢頻道後自動部署面板失敗: {e}", exc_info=True)
        return "\n⚠️ 自動部署面板失敗，可稍後手動重發"


# 純綁定文字頻道（無後續動作）；爬蟲本體之後讀這個 key 發送。
# key 用「主題（硬體）」而非站名，之後可再接多個硬體新聞來源共用同一頻道。
register_channel(
    "系統設備新知",
    discord.ChannelType.text,
    "hardware_news_channel_id",
    color=discord.Color.blue(),
    desc="自動發送IT快訊（系統設備／硬體新知）的文字頻道",
)


# 功能二「AI 偶爾插話 / 閒聊」白名單頻道（純綁定）；ambient_reply 之後讀這個 key。
# 只在此頻道內 AI 才會自發冒泡 + @ 必回；未設定則整個功能靜默。
register_channel(
    "AI 插話頻道",
    discord.ChannelType.text,
    "ambient_chat_channel_id",
    color=discord.Color.magenta(),
    desc="AI 會在此頻道偶爾插話閒聊；被 @ 一定回（功能二）",
)

# AI 每日日記頻道（純綁定）；ambient_diary 每天 00:00 在此頻道用琇紫口吻寫一段當天感想。
# 回顧的社交來源預設＝上面的插話頻道；未設定則整個日記功能靜默。
register_channel(
    "AI 日記頻道",
    discord.ChannelType.text,
    "ai_diary_channel_id",
    color=discord.Color.dark_purple(),
    desc="AI 每天凌晨在此頻道寫一段當天的日記感想",
)

# 新成員歡迎訊息（純綁定）；member_welcome 在有人加入時讀這個 key 發送。
# 未設定則整個功能靜默。
register_channel(
    "歡迎頻道",
    discord.ChannelType.text,
    "welcome_channel_id",
    color=discord.Color.green(),
    desc="新成員加入時自動發送歡迎訊息的文字頻道",
)


# 週期活動提醒（深塔／海墟）；綁定當下自動建立訂閱身份組並發出訂閱面板。
# 未設定則整個提醒功能靜默（排程照跑但不發）。
@register_channel(
    "週期提醒頻道",
    discord.ChannelType.text,
    "periodic_reminder_channel_id",
    color=discord.Color.gold(),
    desc="深塔／海墟重置提醒與訂閱面板的文字頻道",
)
async def _on_set_periodic_reminder(ctx: ChannelSetContext) -> Optional[str]:
    cog = ctx.bot.get_cog("PeriodicReminderCommands")
    if cog is None:
        return "\n⚠️ PeriodicReminderCommands Cog 尚未載入，面板未自動部署"
    try:
        role = await cog.ensure_role(ctx.guild)
        panel_message, deleted_old = await cog.panel.bump(ctx.channel)
        note = f"\n🔔 訂閱身份組：{role.mention}\n🤖 已發出訂閱面板：{panel_message.jump_url}"
        if deleted_old:
            note += "\n🧹 舊面板已刪除。"
        return note
    except Exception as e:
        logger.error(f"設定週期提醒頻道後部署面板失敗: {e}", exc_info=True)
        return "\n⚠️ 建立身份組或發送面板失敗，下一次發提醒時會再試一次。"
