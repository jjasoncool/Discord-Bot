"""頻道功能設定的宣告式 registry。

把「哪個功能要綁哪種頻道、存到哪個 config key、設定後要做什麼」
從 management_commands.set_channel_cmd 那包寫死的大 dict / if-elif 中抽出來，
變成「一個功能 = 一筆登記」。加功能只動這裡，不用碰 UI 流程。

三種登記方式：
  1. 純綁頻道（無後續動作）—— 直接呼叫 register_channel(...) 登記即可。
  2. 綁頻道 + 後續動作 —— 用 @register_channel(...) 裝飾 on_set 函式，
     資料與行為寫在同一處。
  3. 特殊輸入流程（不是「選一個頻道存 id」，例如 Telegram 路由要先輸入來源）——
     用 @register_custom(...) 裝飾一個 handler，由它自己接管 interaction。

選單顯示順序 = 下方登記順序。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional

import discord

from utils.utils import ChannelConfig, safe_send_interaction_message
from telegram_scraper.tg_config import normalize_channel_identifier

logger = logging.getLogger(__name__)


@dataclass
class ChannelSetContext:
    """傳給 on_set hook 的情境，包含設定頻道後可能需要的一切。"""

    guild: discord.Guild
    channel: discord.abc.GuildChannel
    config: dict
    bot: Any                      # commands.Bot；避免額外 import 用 Any
    save: Callable[[], None]      # 立即把目前 config 寫回磁碟（hook 需先存才讀得到時用）


# on_set 簽名：吃 ctx，回傳要附加到成功訊息後面的 note（沒有就回 None）
OnSet = Callable[[ChannelSetContext], Awaitable[Optional[str]]]
# custom_handler 簽名：完全接管該次互動（例如 send_modal），不走標準選頻道流程
CustomHandler = Callable[[discord.Interaction], Awaitable[None]]


@dataclass
class ChannelSetting:
    label: str                                  # 選單顯示名稱，例："音樂語音頻道"
    channel_type: Optional[discord.ChannelType] # 要綁的頻道型別；custom_handler 類為 None
    config_key: Optional[str]                   # 存到 config.json 的 key；custom_handler 類可為 None
    color: discord.Color                        # 選單 / embed 用色
    desc: str                                   # 選單說明
    on_set: Optional[OnSet] = None              # 設定完成後要做的事，沒有就 None
    custom_handler: Optional[CustomHandler] = None  # 走特殊輸入流程，取代標準選頻道


_REGISTRY: list[ChannelSetting] = []


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
) -> Callable[[CustomHandler], CustomHandler]:
    """登記一個「特殊輸入流程」功能（裝飾它的 handler）。"""
    setting = ChannelSetting(label, None, None, color, desc)
    _REGISTRY.append(setting)

    def deco(fn: CustomHandler) -> CustomHandler:
        setting.custom_handler = fn
        return fn

    return deco


def all_settings() -> list[ChannelSetting]:
    return list(_REGISTRY)


def get_setting(label: str) -> Optional[ChannelSetting]:
    return next((s for s in _REGISTRY if s.label == label), None)


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

register_channel(
    "官方文章更新",
    discord.ChannelType.text,
    "article_monitor_channel_id",
    color=discord.Color.orange(),
    desc="自動發送官方最新文章的頻道",
)


# ── Telegram 路由：特殊輸入流程（先輸入來源，再綁 Discord 文字頻道）──
class _TelegramRouteInputModal(discord.ui.Modal):
    def __init__(self):
        super().__init__(title="設定 Telegram 路由", timeout=300)
        self.telegram_source = discord.ui.TextInput(
            label="Telegram 來源（名稱或 chat_id）",
            placeholder="例如：Seele_WW_leak、@Seele_WW_leak、-1001234567890",
            required=True,
            max_length=128,
        )
        self.target_channel = discord.ui.ChannelSelect(
            placeholder="選擇要轉發的 Discord 文字頻道...",
            min_values=1,
            max_values=1,
            channel_types=[discord.ChannelType.text],
            required=True,
        )
        self.add_item(self.telegram_source)
        self.add_item(discord.ui.Label(text="Discord 目標頻道", component=self.target_channel))

    async def on_submit(self, modal_interaction: discord.Interaction):
        source_raw = self.telegram_source.value.strip()
        source_key = normalize_channel_identifier(source_raw).lower()

        if not source_key:
            await safe_send_interaction_message(modal_interaction, "來源值不可為空，請重新設定。", ephemeral=True)
            return

        if not self.target_channel.values:
            await safe_send_interaction_message(modal_interaction, "請選擇 Discord 目標頻道。", ephemeral=True)
            return

        selected_channel = self.target_channel.values[0]
        selected_channel_id = int(getattr(selected_channel, "id", 0) or 0)
        if selected_channel_id <= 0:
            await safe_send_interaction_message(modal_interaction, "選擇的頻道無效，請重試。", ephemeral=True)
            return

        config_file = "config.json"
        config = ChannelConfig.load_config(config_file, caller="ManagementCommands")
        routes = config.get("telegram_channel_routes")
        if not isinstance(routes, dict):
            routes = {}

        raw_existing = routes.get(source_key, [])
        if isinstance(raw_existing, list):
            existing_ids = raw_existing
        elif raw_existing in (None, ""):
            existing_ids = []
        else:
            existing_ids = [raw_existing]

        normalized_ids: list[int] = []
        for rid in existing_ids:
            try:
                rid_int = int(rid)
            except (TypeError, ValueError):
                continue
            if rid_int > 0 and rid_int not in normalized_ids:
                normalized_ids.append(rid_int)

        if selected_channel_id not in normalized_ids:
            normalized_ids.append(selected_channel_id)

        routes[source_key] = normalized_ids
        config["telegram_channel_routes"] = routes
        ChannelConfig.save_config(config, config_file, caller="ManagementCommands")

        await safe_send_interaction_message(
            modal_interaction,
            (
                f"✅ 已新增 Telegram 路由：`{source_key}` -> <#{selected_channel_id}>\n"
                f"目前目標頻道數：{len(normalized_ids)}"
            ),
            ephemeral=True,
        )


@register_custom(
    "Telegram 路由設定",
    color=discord.Color.teal(),
    desc="先輸入 Telegram 來源（名稱/chat_id），再綁定 Discord 文字頻道",
)
async def _handle_telegram_route(interaction: discord.Interaction):
    await interaction.response.send_modal(_TelegramRouteInputModal())


# ── 自我介紹頻道：設定完自動發填寫面板（行為依賴 ManagementCommands cog）──
@register_channel(
    "自我介紹頻道",
    discord.ChannelType.text,
    "intro_channel_id",
    color=discord.Color.purple(),
    desc="使用者填寫自我介紹的頻道",
)
async def _on_set_intro(ctx: ChannelSetContext) -> Optional[str]:
    # lazy import 避免與 management_commands 互相 import 造成循環
    from commands.management_commands import (
        _load_intro_panel_runtime_config,
        _save_intro_panel_runtime_config,
    )

    cog = ctx.bot.get_cog("ManagementCommands")
    if cog is None:
        return "\n⚠️ ManagementCommands Cog 尚未載入，面板未自動發送"
    try:
        panel_message, deleted_old = await cog._replace_intro_panel_message(
            ctx.guild, ctx.channel, ctx.config,
        )
        note = f"\n🤖 已自動發送填寫面板:{panel_message.jump_url}"
        if deleted_old:
            note += "\n🧹 舊頻道面板已刪除。"
        return note
    except Exception as e:
        logger.error(f"設定自我介紹頻道後自動發送面板失敗: {e}", exc_info=True)
        runtime_cfg = _load_intro_panel_runtime_config()
        runtime_cfg.pop("intro_panel_message_id", None)
        _save_intro_panel_runtime_config(ChannelConfig.DEFAULT_ID)
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
        # 先寫 config，讓 cog 內 get_panel_channel 讀得到新頻道
        ctx.save()
        panel_message, deleted_old = await community_cog.replace_community_panel_message(
            ctx.guild, ctx.channel,
        )
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
