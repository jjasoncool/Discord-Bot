"""交易的 Discord 介面：接單表情、交易按鈕、領收期限的定時檢查。

架構定位：介面層（`commands`）。
  - 上層：discord.py 的事件與互動。
  - 下層：交易模組 `services.community.trade_service`（做事的都在那裡）、`utils.due_loop`、`utils.background_tasks`。

介面：`ForumMonitor`（cog，`trade` 是交易模組的實例）、`TradeButton`（交易按鈕）、`make_trade_view`。

規則：這裡只把 Discord 事件交給交易模組，不判斷交易狀態。

例外與決策：檔名沿用 forum_monitor（程式結構整理時決定不改名），內容其實是交易。
"""
import asyncio
import logging
from typing import Optional, Sequence

import discord
from discord.ext import commands

from services.community.trade_service import (
    CANCEL,
    CANCEL_OK,
    CUSTOM_ID_TEMPLATE,
    HELP,
    HOLD,
    KEEP,
    NOTIFY,
    RECEIVE,
    TradeRef,
    TradeService,
    legacy_ref_from_text,
    ref_from_match,
)
from sys_settings.trade_settings import TradeSettings
from utils.due_loop import run_due_loop
from utils.utils import safe_send_interaction_message
from utils.background_tasks import supervise

logger = logging.getLogger(__name__)

_BUTTON_LOOK = {
    NOTIFY: ("通知需求方領收", discord.ButtonStyle.green),
    CANCEL: ("取消交易", discord.ButtonStyle.red),
    CANCEL_OK: ("確定取消交易", discord.ButtonStyle.red),
    KEEP: ("返回", discord.ButtonStyle.secondary),
    RECEIVE: ("已領收", discord.ButtonStyle.green),
    HOLD: ("還沒領收", discord.ButtonStyle.secondary),
    HELP: ("請群主協助", discord.ButtonStyle.secondary),
}


class TradeButton(discord.ui.DynamicItem[discord.ui.Button], template=CUSTOM_ID_TEMPLATE):
    """交易按鈕：bot 重啟後按下照樣有效；交易是誰的由交易模組照按鈕所在的對話查資料庫。"""

    def __init__(self, action: str, ref: TradeRef):
        label, style = _BUTTON_LOOK[action]
        super().__init__(discord.ui.Button(label=label, style=style, custom_id=ref.custom_id(action)))
        self.action = action
        self.ref = ref

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button, match, /):
        return cls(match["action"], ref_from_match(match))

    async def callback(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("ForumMonitor")
        if cog is None:
            await safe_send_interaction_message(interaction, "交易功能目前沒有載入，請通知管理員。", ephemeral=True)
            return
        await cog.trade.handle_button(interaction, self.action, self.ref)


def make_trade_view(ref: TradeRef, actions: Sequence[str]) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    for action in actions:
        view.add_item(TradeButton(action, ref))
    return view


class LegacyTransactionView(discord.ui.View):
    """改版前開的交易對話上的舊按鈕：交給同一個交易模組（身分照對話查資料庫）。
    舊對話都結束後就可以刪掉這個類別與 `legacy_ref_from_text`。"""

    def __init__(self, cog: "ForumMonitor"):
        super().__init__(timeout=None)
        self.cog = cog

    async def _forward(self, interaction: discord.Interaction, action: str):
        ref = legacy_ref_from_text(interaction.message.content if interaction.message else "")
        await self.cog.trade.handle_button(interaction, action, ref)

    # 舊按鈕由供應方按，等同新的「通知需求方領收」；已經發出去的訊息上的字以訊息為準，這裡的只用來註冊
    @discord.ui.button(label="通知需求方領收", style=discord.ButtonStyle.green, custom_id="forum_trade_confirm")
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._forward(interaction, NOTIFY)

    @discord.ui.button(label="取消交易", style=discord.ButtonStyle.red, custom_id="forum_trade_cancel")
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._forward(interaction, CANCEL)


class ForumMonitor(commands.Cog):
    def __init__(self, bot: commands.Bot, settings: Optional[TradeSettings] = None):
        self.bot = bot
        self.settings = settings or TradeSettings()
        self.trade = TradeService(bot, make_view=make_trade_view, settings=self.settings)
        # 新開的接單對話附上供應方的物品價格（匯入期間記下、做完才補開的也一樣）
        self.trade.on_reaction_opened = self._send_prices
        self._deadline_task: Optional[asyncio.Task] = None

    async def cog_load(self):
        self.bot.add_dynamic_items(TradeButton)
        self.bot.add_view(LegacyTransactionView(self))
        self._deadline_task = supervise(
            lambda: run_due_loop(
                "交易領收期限",
                self.trade.run_receipt_deadlines,
                wait_ready=self.bot.wait_until_ready,
                max_sleep=self.settings.deadline_check_max_sleep_seconds,
            ),
            name="trade_receipt_deadlines",
        )

    async def cog_unload(self):
        if self._deadline_task is not None:
            self._deadline_task.cancel()
            self._deadline_task = None
        self.bot.remove_dynamic_items(TradeButton)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        try:
            await self.trade.note_chat(message)
        except Exception:  # 邊界：每則訊息；記不到只影響「幾天沒動靜」的天數
            logger.warning("交易：記錄交易對話的動靜失敗 channel=%s", getattr(message.channel, "id", None),
                           exc_info=True)

    @commands.Cog.listener()
    async def on_raw_thread_delete(self, payload: discord.RawThreadDeleteEvent):
        try:
            await self.trade.handle_thread_deleted(payload.thread_id)
        except Exception:  # 邊界：每個刪除事件；沒處理到的，下次啟動時的檢查會補
            logger.error("交易：處理交易對話被刪掉失敗 thread=%s", payload.thread_id, exc_info=True)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        try:
            await self.trade.handle_reaction(payload)
        except Exception:
            logger.error("交易：處理接單表情失敗 channel=%s message=%s user=%s",
                         payload.channel_id, payload.message_id, payload.user_id, exc_info=True)

    async def _send_prices(self, opened) -> None:
        await opened.thread.send(embed=await self._price_embed(opened.supplier))

    async def _price_embed(self, supplier: discord.Member) -> discord.Embed:
        """新開的交易 thread 附上供應方在 /set_item_prices 設的價格。"""
        title = f"{supplier.display_name} 的物品價格"
        user_cog = self.bot.get_cog("UserCommands")
        if user_cog is None:
            return discord.Embed(title="無法取得物品價格", description="無法取得供應方的物品價格資訊。",
                                 color=discord.Color.red())
        embed = discord.Embed(title=title, description="以下是供應方設定的物品價格：", color=discord.Color.blue())
        prices = await user_cog.get_user_item_prices(supplier.id)
        for details in (prices or {}).values():
            if details["price"] != "無價格設定":
                embed.add_field(name=f"{details['label']} ({details['description']})",
                                value=f"價格: {details['price']}", inline=False)
        if not embed.fields:
            embed.description = "供應方沒有設定任何物品價格。"
        return embed


async def setup(bot):
    await bot.add_cog(ForumMonitor(bot))
