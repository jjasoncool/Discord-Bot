"""商品上架的 Discord 介面：置頂說明的按鈕、商品貼文的購買選單與管理按鈕、管理面板與各個表單、交易進度上的按鈕。

架構定位：介面層（`commands`）。
  - 上層：discord.py 的互動（按鈕、選單、表單送出）與 cog 載入。
  - 下層：商品服務 `services.community.shop_service`（做事的都在那裡）、商品交易 `shop_trade`（交易進度的按鈕）、
    `shop_listing`（解析供應方填的內容、畫選單）、`utils.due_loop`（截止與等待提醒的排程）。

介面：`ShopCommands`（cog）、`DiscordShopViews`（交給商品服務的元件工廠）、各個 DynamicItem 與 Modal。

規則：
  - 這裡只負責元件長相，並把互動交給商品服務；資料一律查資料庫，按鈕與選單的 custom_id 只帶編號。
  - 按鈕與選單都是 DynamicItem，bot 重啟後按下去照樣有效；表單和只有自己看得到的暫時訊息本來就是一次性的。
  - 管理面板一則最多 5 列：第一列新增品項、批次新增、編輯商品資訊；第二列延期、開始收尾款或開始交貨；
    第三列下架；第四、五列編輯、刪除品項的選單。之後沒有空間再加列。

例外與決策：
  - Discord 的選單選過同一項就不會再通知 bot（實測：編輯一次之後選單卡在那一項）：商品貼文與管理面板
    每次操作完都重畫，選單回到未選取。
"""
import asyncio
import logging
import re
from datetime import datetime, time, timedelta
from typing import Optional, Sequence

import discord
from discord.ext import commands

from services.community import market_report
from services.community import trade_progress as tp
from services.community.market_import import run_import
from services.community.shop_listing import (
    BUY_TEMPLATE,
    DELIVERY_LABELS,
    KIND_LABELS,
    LIMIT_MAX,
    NAME_LIMIT,
    PRICE_FIELD_LIMIT,
    TITLE_LIMIT,
    UNIT_LIMIT,
    Listing,
    ShopError,
    Variant,
    buy_custom_id,
    decode_items,
    encode_items,
    format_cutoff,
    money,
    parse_batch,
    parse_draft,
    select_options,
    unavailable_text,
)
from services.community import market_transition as transition
from services.community.shop_service import UNIT_EXAMPLES, PriceChanged, ShopService
from services.community.shop_trade import STEP_TEMPLATE, Step
from services.market_db import backup_daily
from sys_settings.paths import MARKET_BACKUP_DIR
from sys_settings.shop_settings import ShopSettings
from sys_settings.time_settings import APP_TZ
from utils import owner_alerts
from utils.background_tasks import spawn, supervise
from utils.due_loop import run_due_loop
from utils.utils import safe_send_interaction_message, safe_send_interaction_text

logger = logging.getLogger(__name__)

GUIDE_CUSTOM_ID = "shop:new"
MINE_CUSTOM_ID = "shop:mine"
#: 群主通知的種類：上線匯入失敗時私訊群主，「重新偵測」＝重跑匯入
ALERT_KIND = "market"
NOT_READY_TEXT = "商品與交易功能更新中，請稍後再試。"
MANAGE_CUSTOM_ID = "shop:manage"
_CODE_BLOCK = re.compile(r"```\n?(.*?)```", re.DOTALL)
#: modal 開著沒送出就關掉時，最多在記憶體裡留這麼久（跟專案其他 modal 一致）
_MODAL_TIMEOUT = 600
#: 市集資料庫每天備份的時刻：避開 04:00 起的維護時段
_BACKUP_AT = time(3, 30)
#: 交易進度上品項按鈕超過這麼多顆就改用選單（一則最多 5 列、每列 5 顆，第一列留給付款）
_ITEM_BUTTONS_MAX = 20
_ERROR_TEXT = "處理時發生錯誤，請截圖通知管理員。"
#: 管理面板 embed 說明的長度上限（Discord 是 4096，留一點給標題）
_PANEL_TEXT_LIMIT = 4000


def _shop(interaction: discord.Interaction) -> Optional[ShopService]:
    return getattr(interaction.client.get_cog("ShopCommands"), "shop", None)


async def _reply(interaction: discord.Interaction, text: str, **kwargs) -> None:
    await safe_send_interaction_message(interaction, text, ephemeral=True, **kwargs)


async def _missing(interaction: discord.Interaction) -> None:
    await _reply(interaction, "商品上架功能目前沒有載入，請通知管理員。")


def _now() -> datetime:
    return datetime.now(APP_TZ)


# ── 交給商品服務的元件 ──

class DiscordShopViews:
    """`ShopViews` 的實作：商品貼文、置頂說明、交易進度上的元件。"""

    def __init__(self, settings: ShopSettings):
        self.settings = settings

    def listing(self, listing: Listing, now: datetime) -> discord.ui.View:
        view = discord.ui.View(timeout=None)
        if listing.variants:
            options = select_options(listing, now)
            # 下架或全部都不能買就停用選單、原因直接寫在選單上；供應方補貨後重畫，選單自己恢復
            blocked = "已下架" if listing.closed else unavailable_text(listing, now)
            view.add_item(ShopBuySelect(listing.thread_id, options=options,
                                        max_values=min(self.settings.max_pick, len(options)),
                                        disabled=blocked is not None, placeholder=blocked))
        view.add_item(ShopManageButton(disabled=listing.closed))
        return view

    def guide(self) -> discord.ui.View:
        return GuideView()

    def progress(self, steps: Sequence[Step]) -> Optional[discord.ui.View]:
        if not steps:
            return None
        view = discord.ui.View(timeout=None)
        money_steps = [s for s in steps if s.key is None]
        item_steps = [s for s in steps if s.key is not None]
        for step in money_steps:
            view.add_item(ShopStepButton(step.action, None, step.version, label=step.label, who=step.who, row=0))
        if len(item_steps) <= _ITEM_BUTTONS_MAX:
            for number, step in enumerate(item_steps):
                view.add_item(ShopStepButton(step.action, step.key, step.version, label=step.label, who=step.who,
                                             row=1 + number // 5))
        else:
            # 品項多到按鈕放不下：每種動作一個選單（選了就是按了那個品項的按鈕）
            for row, action in enumerate(dict.fromkeys(s.action for s in item_steps), start=1):
                options = [discord.SelectOption(label=s.label[:100], value=str(s.key))
                           for s in item_steps if s.action == action][:25]
                view.add_item(ShopStepSelect(action, options=options, row=row))
        return view


class ShopBuySelect(discord.ui.DynamicItem[discord.ui.Select], template=BUY_TEMPLATE):
    """商品貼文的購買下拉：選項的 value 是品項編號，資料查資料庫。"""

    def __init__(self, listing_id: int, *, options: Sequence[discord.SelectOption] = (),
                 max_values: int = 1, disabled: bool = False, placeholder: Optional[str] = None):
        super().__init__(discord.ui.Select(
            custom_id=buy_custom_id(listing_id), placeholder=placeholder or "選擇要購買的品項（可多選）",
            min_values=1, max_values=max(1, max_values), disabled=disabled,
            options=list(options) or [discord.SelectOption(label="（沒有品項）", value="-")],
        ))
        self.listing_id = listing_id

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Select, match, /):
        return cls(int(match["listing"]), options=item.options, max_values=item.max_values, disabled=item.disabled,
                   placeholder=item.placeholder)

    async def callback(self, interaction: discord.Interaction):
        shop = _shop(interaction)
        if shop is None:
            return await _missing(interaction)
        if not shop.trade.ready.is_set():
            return await _reply(interaction, NOT_READY_TEXT)
        # 舊貼文的選項 value 是「編號:價格:…」，新的只有編號；都只取最前面的編號
        keys = [int(v.split(":", 1)[0]) for v in self.item.values if v.split(":", 1)[0].isdigit()]
        try:
            variants = await shop.check_pick(self.listing_id, interaction.user, keys)
        except ShopError as exc:
            await _reply(interaction, str(exc))
            # 拿著商品鎖重畫：跟截止、下單的重畫排隊，晚到的舊畫面才不會蓋掉新的（選單又能選、剩餘數量變回去）
            async with shop.lock(self.listing_id):
                await shop.refresh_listing(self.listing_id)
            return
        await interaction.response.send_modal(QuantityModal(self.listing_id, variants))
        # 回應只能有一個（跳出視窗），選單會停在剛選的項目；按取消後再選同一項，Discord 不會通知 bot。
        # 所以視窗跳出後，bot 重畫商品貼文清空選單；視窗要問的品項已經決定好了，不受影響
        async with shop.lock(self.listing_id):
            await shop.refresh_listing(self.listing_id)


class ShopManageButton(discord.ui.DynamicItem[discord.ui.Button],
                       template=r"shop:manage(?::[^:]*:[^:]*:[^:]*)?"):
    """「⚙️ 管理商品（供應方）」：大家都看得到（Discord 沒辦法依身份組隱藏），只有供應方與管理員能用。
    舊貼文的 custom_id 帶著供應方、編號、幣別，現在一律查資料庫，所以兩種寫法都認。"""

    def __init__(self, *, disabled: bool = False):
        super().__init__(discord.ui.Button(
            label="管理商品（供應方）", emoji="⚙️", style=discord.ButtonStyle.secondary,
            custom_id=MANAGE_CUSTOM_ID, disabled=disabled))

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button, match, /):
        return cls(disabled=item.disabled)

    async def callback(self, interaction: discord.Interaction):
        shop = _shop(interaction)
        if shop is None:
            return await _missing(interaction)
        if not shop.trade.ready.is_set():
            return await _reply(interaction, NOT_READY_TEXT)
        try:
            listing = await shop.check_manager(interaction.channel.id, interaction.user, guild=interaction.guild)
        except ShopError as exc:
            return await _reply(interaction, str(exc))
        embed, view = await _panel(shop, listing)
        await safe_send_interaction_message(interaction, embed=embed, view=view, ephemeral=True)


# ── 管理面板（只有供應方看得到的暫時訊息） ──

_PANEL_ACTIONS = {
    # 主要動作藍、一般灰、會刪東西的紅；編輯／刪除品項是面板裡的兩個選單
    "add": ("新增品項", discord.ButtonStyle.primary, 0),
    "batch": ("批次新增", discord.ButtonStyle.primary, 0),
    "info": ("編輯商品資訊", discord.ButtonStyle.secondary, 0),
    "delay": ("📅 延期", discord.ButtonStyle.secondary, 1),
    "balance": ("📦 開始收尾款（準備交貨）", discord.ButtonStyle.secondary, 1),
    "deliver": ("⏩ 開始交貨", discord.ButtonStyle.secondary, 1),
    "convert": ("💰 改成定金＋尾款", discord.ButtonStyle.secondary, 1),
    "close": ("下架", discord.ButtonStyle.danger, 2),
    "back": ("返回", discord.ButtonStyle.secondary, None),  # 子畫面用，不放在主面板
}


async def _panel(shop: ShopService, listing: Listing) -> tuple[discord.Embed, discord.ui.View]:
    now = _now()
    counts = await shop.trades.deposit_counts(listing.thread_id) if listing.has_deposit() else {}
    lines = []
    for number, variant in enumerate(listing.variants, start=1):
        line = f"{number}. {variant.name}｜{variant.status(listing.unit, now, rich=True)}"
        if variant.key in counts:
            ordered, deposits, balances = counts[variant.key]
            line += f"\n　下單 {ordered}｜已確認定金 {deposits}｜已付尾款 {balances}"
        lines.append(line)
    description = "\n".join(lines)
    if len(description) > _PANEL_TEXT_LIMIT:
        # 品項多、名稱長時（25 個、名稱 80 字）一行行寫會超過 embed 上限，面板就開不起來：改寫精簡版
        lines = [f"{n}. {v.name[:30]}｜{v.unavailable_reason(now) or v.price_text(listing.unit)}"
                 for n, v in enumerate(listing.variants, start=1)]
        description = "\n".join(lines)[:_PANEL_TEXT_LIMIT]
    embed = discord.Embed(title=f"⚙️ 管理商品：{listing.title}"[:256], color=discord.Color.gold(),
                          description=description or "還沒有品項，先按「新增品項」或「批次新增」。")
    if await transition.holds_orders(shop.trade, listing):
        embed.add_field(name="⚠️ 目前不接新訂單", inline=False, value=transition.PANEL_NOTE)
    embed.set_footer(text=f"交付方式：{DELIVERY_LABELS.get(listing.delivery, listing.delivery)}｜這個面板只有你看得到")
    view = discord.ui.View(timeout=None)
    for action in ("add", "batch", "info"):
        view.add_item(ShopPanelButton(action, listing.thread_id))
    if any(v.cutoff is not None for v in listing.variants):
        view.add_item(ShopPanelButton("delay", listing.thread_id))
    if listing.has_deposit():
        view.add_item(ShopPanelButton("balance", listing.thread_id))
    elif any(v.preorder for v in listing.variants) and not transition.waits_for_deposit(listing):
        # 還沒改成定金的【定金】商品不放「開始交貨」：按了會記成已截止，改成定金後收定金就再也打不開
        view.add_item(ShopPanelButton("deliver", listing.thread_id))
    if await transition.can_convert(shop.trade, listing):
        # 上線前匯入、標題寫【定金】的商品：舊格式沒有定金＋尾款，整篇一起改（一個一個改會被「不能跟一次付清混放」擋下）
        view.add_item(ShopPanelButton("convert", listing.thread_id))
    view.add_item(ShopPanelButton("close", listing.thread_id))
    if listing.variants:
        options = [discord.SelectOption(label=f"{n}. {v.name}"[:100], value=str(v.key))
                   for n, v in enumerate(listing.variants, start=1)]
        view.add_item(ShopPickSelect("edit", listing.thread_id, options=options))
        view.add_item(ShopPickSelect("delete", listing.thread_id, options=options))
    return embed, view


async def _show_panel(interaction: discord.Interaction, shop: ShopService, listing: Listing,
                      text: Optional[str] = None) -> None:
    """重畫管理面板（這則只有供應方看得到的訊息）。呼叫前要先回應過互動。"""
    embed, view = await _panel(shop, listing)
    await interaction.edit_original_response(content=text, embed=embed, view=view)


async def _panel_with_error(interaction: discord.Interaction, shop: ShopService, listing_id: int, text: str) -> None:
    """失敗時也重畫面板（選單才會回到未選取），讀不到商品就只顯示訊息。"""
    try:
        listing = await shop.check_manager(listing_id, interaction.user)
    except ShopError:
        await interaction.edit_original_response(content=text, embed=None, view=None)
        return
    await _show_panel(interaction, shop, listing, text)


async def _clear_panel_after_modal(interaction: discord.Interaction, shop: ShopService, listing_id: int) -> None:
    """跳出視窗之後重畫面板，選單才會回到未選取：取消視窗後再選同一項，Discord 不會通知 bot。

    面板只有供應方看得到，只能透過互動改它，而 Discord 文件沒寫跳出視窗後還能不能改：
    先改這次互動的原始回應，不行再指定這則訊息改；都不行就留 log，供應方按「返回」一樣會重畫。"""
    try:
        listing = await shop.check_manager(listing_id, interaction.user)
    except ShopError:
        return
    embed, view = await _panel(shop, listing)
    panel = dict(content=None, embed=embed, view=view)
    try:
        await interaction.edit_original_response(**panel)
        return
    except discord.HTTPException as exc:
        first = exc
    try:
        await interaction.followup.edit_message(interaction.message.id, **panel)
        logger.info("商品上架：跳出視窗後改用訊息 id 重畫管理面板（原始回應不行：%s）", first)
    except discord.HTTPException:
        logger.warning("商品上架：跳出視窗後重畫管理面板失敗（原始回應：%s）", first, exc_info=True)


def _confirm_view(action: str, listing_id: int, key: Optional[int] = None) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    view.add_item(ShopConfirmButton(action, listing_id, key))
    view.add_item(ShopPanelButton("back", listing_id))
    return view


class ShopPanelButton(discord.ui.DynamicItem[discord.ui.Button],
                      template=r"shop:panel:(?P<action>add|batch|info|delay|balance|deliver|convert|close|back):(?P<listing>\d+)"):
    """管理面板的按鈕。面板只有供應方看得到；真正寫入時商品服務會再檢查一次權限。"""

    def __init__(self, action: str, listing_id: int):
        label, style, row = _PANEL_ACTIONS[action]
        super().__init__(discord.ui.Button(label=label, style=style, row=row,
                                           custom_id=f"shop:panel:{action}:{listing_id}"))
        self.action = action
        self.listing_id = listing_id

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button, match, /):
        return cls(match["action"], int(match["listing"]))

    async def callback(self, interaction: discord.Interaction):
        shop = _shop(interaction)
        if shop is None:
            return await _missing(interaction)
        try:
            if self.action == "add":
                return await interaction.response.send_modal(VariantModal(self.listing_id))
            if self.action == "batch":
                return await interaction.response.send_modal(BatchModal(self.listing_id))
            if self.action == "close":
                # 確認畫面直接換在面板上（不另開訊息），按「返回」回到面板；下架不能恢復，只想暫停的話改數量就好
                return await interaction.response.edit_message(
                    content="確定要下架這篇商品嗎？下架後不能恢復，已成立的交易照常進行。"
                            "只想暫停販售的話，把品項的剩餘數量改成 0 就好。",
                    embed=None, view=_confirm_view("close", self.listing_id))
            if self.action == "back":
                await interaction.response.defer()
                listing = await shop.check_manager(self.listing_id, interaction.user)
                return await _show_panel(interaction, shop, listing)
            if self.action == "info":
                # 編輯商品資訊要帶入目前的標題與說明（讀資料庫，很快）
                listing = await shop.check_manager(self.listing_id, interaction.user)
                return await interaction.response.send_modal(ListingInfoModal(listing=listing))
            if self.action == "convert":
                listing = await shop.check_manager(self.listing_id, interaction.user)
                return await interaction.response.send_modal(DepositConvertModal(listing))
            targets = await shop.schedule_targets(self.listing_id, interaction.user, self.action)
            if not targets:
                return await _reply(interaction, {"delay": "沒有可以延期的品項（只有預購、還沒開始收尾款的定金品項可以延期）。",
                                                  "balance": "沒有還沒開始收尾款的定金品項。",
                                                  "deliver": "沒有還沒截止的預購品項。"}[self.action])
            if self.action == "delay":
                return await interaction.response.send_modal(DelayModal(self.listing_id, targets))
            await interaction.response.defer()
            if len(targets) == 1:
                return await _schedule_confirm(interaction, shop, self.action, self.listing_id, targets[0].key)
            question = "要開始收哪個品項的尾款？" if self.action == "balance" else "要開始交貨哪個品項？"
            view = discord.ui.View(timeout=None)
            # 收尾款前要看得到每個品項收了幾份定金（選了之後的確認畫面還會再列一次）
            counts = await shop.trades.deposit_counts(self.listing_id) if self.action == "balance" else {}
            view.add_item(ShopScheduleSelect(self.action, self.listing_id, options=[
                discord.SelectOption(label=_schedule_label(v, counts.get(v.key)), value=str(v.key)) for v in targets]))
            view.add_item(ShopPanelButton("back", self.listing_id))
            await interaction.edit_original_response(content=question, embed=None, view=view)
        except ShopError as exc:
            await _reply(interaction, str(exc))


def _schedule_label(variant, counts: Optional[tuple[int, int, int]]) -> str:
    """開始收尾款、開始交貨的品項選項；收尾款的寫已確認定金幾份（選項文字最多 100 字，名稱先截）。"""
    if counts is None:
        return variant.name[:100]
    tail = f"（已確認定金 {counts[1]} 份）"
    return variant.name[:100 - len(tail)] + tail


async def _schedule_confirm(interaction: discord.Interaction, shop: ShopService, action: str,
                            listing_id: int, key: int) -> None:
    """開始收尾款、開始交貨的確認畫面（換在面板上）。要先回應過互動。"""
    try:
        if action == "balance":
            text = await shop.balance_preview(listing_id, interaction.user, key)
        else:
            text = await shop.delivery_preview(listing_id, interaction.user, key)
    except ShopError as exc:
        return await _panel_with_error(interaction, shop, listing_id, f"⚠️ {exc}")
    await interaction.edit_original_response(content=text, embed=None,
                                             view=_confirm_view(action, listing_id, key))


class ShopScheduleSelect(discord.ui.DynamicItem[discord.ui.Select],
                         template=r"shop:sched:(?P<action>balance|deliver):(?P<listing>\d+)"):
    """開始收尾款、開始交貨時選品項（不只一個可選時）。"""

    def __init__(self, action: str, listing_id: int, *, options: Sequence[discord.SelectOption] = ()):
        super().__init__(discord.ui.Select(
            custom_id=f"shop:sched:{action}:{listing_id}", min_values=1, max_values=1,
            options=list(options) or [discord.SelectOption(label="（沒有品項）", value="0")]))
        self.action = action
        self.listing_id = listing_id

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Select, match, /):
        return cls(match["action"], int(match["listing"]), options=item.options)

    async def callback(self, interaction: discord.Interaction):
        shop = _shop(interaction)
        if shop is None:
            return await _missing(interaction)
        await interaction.response.defer()
        await _schedule_confirm(interaction, shop, self.action, self.listing_id, int(self.item.values[0]))


class ShopPickSelect(discord.ui.DynamicItem[discord.ui.Select],
                     template=r"shop:pick:(?P<action>edit|delete):(?P<listing>\d+)"):
    """管理面板裡的「編輯品項」「刪除品項」選單；選項 value 是品項編號。"""

    def __init__(self, action: str, listing_id: int, *, options: Sequence[discord.SelectOption] = ()):
        super().__init__(discord.ui.Select(
            custom_id=f"shop:pick:{action}:{listing_id}", min_values=1, max_values=1,
            placeholder="編輯品項⋯" if action == "edit" else "刪除品項⋯", row=3 if action == "edit" else 4,
            options=list(options) or [discord.SelectOption(label="（沒有品項）", value="0")]))
        self.action = action
        self.listing_id = listing_id

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Select, match, /):
        return cls(match["action"], int(match["listing"]), options=item.options)

    async def callback(self, interaction: discord.Interaction):
        shop = _shop(interaction)
        if shop is None:
            return await _missing(interaction)
        value = self.item.values[0].split(":", 1)[0]
        try:
            listing = await shop.check_manager(self.listing_id, interaction.user)
        except ShopError as exc:
            return await _reply(interaction, str(exc))
        variant = listing.variant(int(value)) if value.isdigit() else None
        if variant is None:
            return await _reply(interaction, "找不到這個品項，可能已經被刪除。")
        if self.action == "edit":
            # 選了直接跳出編輯視窗（不用再多按一次），跳出後再重畫面板清空選單
            await interaction.response.send_modal(VariantModal(self.listing_id, variant,
                                                               cutoff_locked=shop.cutoff_locked(variant)))
            await _clear_panel_after_modal(interaction, shop, self.listing_id)
        else:
            await interaction.response.edit_message(content=f"確定要刪除「{variant.name}」嗎？", embed=None,
                                                    view=_confirm_view("delete", self.listing_id, variant.key))


_CONFIRM_LOOK = {
    "delete": ("del", "確定刪除", discord.ButtonStyle.danger),
    "close": ("closeok", "確定下架", discord.ButtonStyle.danger),
    "balance": ("balok", "確定開始收尾款", discord.ButtonStyle.primary),
    "deliver": ("dlvok", "確定開始交貨", discord.ButtonStyle.primary),
}
_CONFIRM_CODES = {code: action for action, (code, _, _) in _CONFIRM_LOOK.items()}


class ShopConfirmButton(discord.ui.DynamicItem[discord.ui.Button],
                        template=r"shop:(?P<action>del|closeok|balok|dlvok):(?P<listing>\d+)(?::(?P<key>\d+))?"):
    """刪除品項、下架、開始收尾款、開始交貨前的確認。"""

    def __init__(self, action: str, listing_id: int, key: Optional[int] = None):
        code, label, style = _CONFIRM_LOOK[action]
        custom_id = f"shop:{code}:{listing_id}" + (f":{key}" if key is not None else "")
        super().__init__(discord.ui.Button(label=label, style=style, custom_id=custom_id))
        self.action = action
        self.listing_id = listing_id
        self.key = key

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button, match, /):
        key = int(match["key"]) if match["key"] else None
        return cls(_CONFIRM_CODES[match["action"]], int(match["listing"]), key)

    async def callback(self, interaction: discord.Interaction):
        shop = _shop(interaction)
        if shop is None:
            return await _missing(interaction)
        # 先拿掉按鈕，避免連按；開始收尾款要逐一發到很多交易對話，可能超過 3 秒
        await interaction.response.edit_message(content="處理中……", view=None)
        try:
            if self.action == "delete":
                listing = await shop.delete_variant(self.listing_id, interaction.user, self.key)
                return await _show_panel(interaction, shop, listing, "已刪除這個品項。")
            if self.action == "close":
                await shop.close_listing(self.listing_id, interaction.user)
                return await interaction.edit_original_response(content="已下架。", embed=None, view=None)
            if self.action == "balance":
                text = await shop.start_balance(self.listing_id, interaction.user, self.key)
            else:
                text = await shop.start_delivery(self.listing_id, interaction.user, self.key)
            listing = await shop.check_manager(self.listing_id, interaction.user)
            return await _show_panel(interaction, shop, listing, text)
        except ShopError as exc:
            text = f"⚠️ {exc}"
        except Exception:  # 邊界：一次按鈕互動，做壞了要把面板救回來
            logger.error("商品上架：%s 失敗 商品=%s", self.action, self.listing_id, exc_info=True)
            text = _ERROR_TEXT
        await _panel_with_error(interaction, shop, self.listing_id, text)


# ── 批次新增 ──

def _batch_preview(listing_id: int, text: str, max_variants: int = 25) -> tuple[list[discord.Embed], discord.ui.View]:
    """批次新增的預覽：沒錯是一張預覽；有錯是兩張，錯誤一張、原文一張（「回去修改」從原文那張讀回完整內容）。"""
    drafts, errors = parse_batch(text, now=_now())
    if len(drafts) > max_variants:
        errors.append(f"一篇商品最多 {max_variants} 個品項，這次填了 {len(drafts)} 個。")
    view = discord.ui.View(timeout=None)
    if errors or not drafts:
        # 一則訊息的 embed 合計 6000 字：錯誤最多列 15 行、每行最多 120 字（錯誤裡會帶使用者打的整段文字），
        # 原文另一張放得下表單上限的 4000 字
        shown = [e if len(e) <= 120 else e[:119] + "…" for e in errors[:15]]
        shown += [f"……還有 {len(errors) - 15} 行有錯"] if len(errors) > 15 else []
        embeds = [discord.Embed(title="格式有錯，請修改", color=discord.Color.red(),
                                description="\n".join(shown or ["沒有填任何品項。"])),
                  discord.Embed(title="你填的內容", color=discord.Color.red(), description=f"```\n{text[:4000]}\n```")]
    else:
        lines = "\n".join(d.line() for d in drafts)
        embeds = [discord.Embed(title=f"預覽：要新增 {len(drafts)} 個品項", color=discord.Color.gold(),
                                description=f"```\n{lines}\n```\n數量空白＝不限量；截止時間空白＝立即購買；"
                                            "價格寫「定金/尾款」＝定金＋尾款。")]
        view.add_item(ShopBatchButton("ok", listing_id))
    view.add_item(ShopBatchButton("fix", listing_id))
    return embeds, view


def _preview_text(message: Optional[discord.Message]) -> str:
    """從預覽訊息讀回內容（預覽就是暫存，不另外記在記憶體）：最後一張 embed 的最後一個程式碼區塊。"""
    for embed in reversed(list(getattr(message, "embeds", None) or [])):
        blocks = _CODE_BLOCK.findall(embed.description or "")
        if blocks:
            return blocks[-1].strip("\n")
    return ""


class ShopBatchButton(discord.ui.DynamicItem[discord.ui.Button],
                      template=r"shop:batch(?P<action>ok|fix):(?P<listing>\d+)"):
    def __init__(self, action: str, listing_id: int):
        label, style = ("確認新增", discord.ButtonStyle.primary) if action == "ok" else \
            ("回去修改", discord.ButtonStyle.secondary)
        super().__init__(discord.ui.Button(label=label, style=style, custom_id=f"shop:batch{action}:{listing_id}"))
        self.action = action
        self.listing_id = listing_id

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button, match, /):
        return cls(match["action"], int(match["listing"]))

    async def callback(self, interaction: discord.Interaction):
        shop = _shop(interaction)
        if shop is None:
            return await _missing(interaction)
        text = _preview_text(interaction.message)
        if self.action == "fix":
            return await interaction.response.send_modal(BatchModal(self.listing_id, text))
        drafts, errors = parse_batch(text, now=_now())
        if errors:  # 預覽之後時間過了（例：截止時間變成過去）
            embeds, view = _batch_preview(self.listing_id, text)
            return await interaction.response.edit_message(embeds=embeds, view=view)
        await interaction.response.edit_message(content="新增中……", embed=None, view=None)
        try:
            listing = await shop.add_variants(self.listing_id, interaction.user, drafts)
            return await _show_panel(interaction, shop, listing, f"已新增 {len(drafts)} 個品項。")
        except ShopError as exc:
            result = str(exc)
        except Exception:  # 邊界：一次按鈕互動
            logger.error("商品上架：批次新增失敗 商品=%s", self.listing_id, exc_info=True)
            result = _ERROR_TEXT
        await _panel_with_error(interaction, shop, self.listing_id, result)


_BATCH_HELP = (
    "**每行一個品項**，四欄用「｜」隔開（半形 | 也可以）：\n"
    "`名稱｜價格｜數量｜截止`\n"
    "・**價格**：只填數字，單位用這篇商品設定的；定金＋尾款填「定金/尾款」，例 `500/1300`\n"
    "・**數量**：留空＝不限量；賣完會自動標「已售完」\n"
    "・**截止**：留空＝立即購買；寫含年份的時間就是預購，例 `2026/10/20 23:59`（只寫日期＝當天 23:59）。"
    "定金＋尾款一定要填（收定金的截止）\n"
    "送出後會先給你看預覽、標出格式有錯的行，按「確認新增」才會加進商品。一篇最多 25 個品項；"
    "定金＋尾款的品項不能和一次付清的放在同一篇。"
)


class BatchModal(discord.ui.Modal):
    def __init__(self, listing_id: int, text: str = ""):
        super().__init__(title="批次新增品項", timeout=_MODAL_TIMEOUT)
        self.listing_id = listing_id
        self.lines = discord.ui.TextInput(
            style=discord.TextStyle.paragraph, max_length=4000, default=text or None,
            placeholder="60 月相｜30｜10｜\n6480 月相｜3000｜3｜2026/10/20 23:59")
        # 說明放在最上面（modal 支援純文字說明），輸入框本身的標題只能 45 字，寫不完
        self.add_item(discord.ui.TextDisplay(_BATCH_HELP))
        self.add_item(discord.ui.Label(text="品項清單", description="一行一個，例：60 月相｜30｜10｜",
                                       component=self.lines))

    async def on_submit(self, interaction: discord.Interaction):
        embeds, view = _batch_preview(self.listing_id, self.lines.value)
        await safe_send_interaction_message(interaction, embeds=embeds, view=view, ephemeral=True)


# ── 單一品項 ──

class VariantModal(discord.ui.Modal):
    def __init__(self, listing_id: int, variant: Optional[Variant] = None, *, cutoff_locked: bool = False):
        super().__init__(title="編輯品項" if variant else "新增品項", timeout=_MODAL_TIMEOUT)
        self.listing_id = listing_id
        self.variant = variant
        self.cutoff_locked = bool(variant and cutoff_locked)
        kind = variant.kind if variant else "instant"
        price = None
        if variant:
            price = f"{variant.price}/{variant.balance}" if variant.deposit else str(variant.price)
        self.name = discord.ui.TextInput(max_length=NAME_LIMIT, default=variant.name if variant else None)
        self.price = discord.ui.TextInput(max_length=PRICE_FIELD_LIMIT, default=price)
        self.kind = discord.ui.Select(min_values=1, max_values=1, required=True, options=[
            discord.SelectOption(label=KIND_LABELS[k], value=k, default=k == kind)
            for k in ("instant", "preorder", "deposit")])
        self.cutoff = discord.ui.TextInput(required=False, max_length=16, placeholder="2026/10/20 23:59",
                                           default=format_cutoff(variant.cutoff) if variant and variant.cutoff else None)
        # 編輯時填「剩餘數量」：預填目前還剩幾個（賣光＝0），補貨幾個就填幾個
        # 預填不能超過欄位上限（6 位）：剩餘數量填到上限之後有人取消，剩的會比上限多
        self.limit = discord.ui.TextInput(
            required=False, max_length=6,
            default=str(min(variant.remaining, LIMIT_MAX)) if variant and variant.remaining is not None else None)
        # modal 最多 5 個欄位，放不下整段說明，改在每個欄位底下各寫一行
        self.add_item(discord.ui.Label(text="名稱", description="需求方在購買選單看到的名字，最多 80 字",
                                       component=self.name))
        self.add_item(discord.ui.Label(text="價格", description="只填數字。定金＋尾款填「定金/尾款」，例 500/1300",
                                       component=self.price))
        self.add_item(discord.ui.Label(text="類型", description="預購、定金＋尾款要再填下面的截止時間",
                                       component=self.kind))
        if self.cutoff_locked:
            cutoff_hint = "已有人下單或已截止，截止時間鎖住；要改日期請用管理面板的「📅 延期」"
        else:
            cutoff_hint = "預購、定金＋尾款必填，要寫年份，例 2026/10/20 23:59；只寫日期＝當天 23:59"
        self.add_item(discord.ui.Label(text="截止時間", description=cutoff_hint, component=self.cutoff))
        if variant is None:
            limit_label = discord.ui.Label(text="數量", description="總共要賣幾個；不限量就留空；賣完會自動標「已售完」",
                                           component=self.limit)
        else:
            limit_label = discord.ui.Label(
                text="剩餘數量",
                description=f"還要賣幾個（已賣出 {variant.taken} 個不用算進去）；填 0＝停賣；不限量就留空",
                component=self.limit)
        self.add_item(limit_label)

    async def on_submit(self, interaction: discord.Interaction):
        shop = _shop(interaction)
        if shop is None:
            return await _missing(interaction)
        # 從面板打開的 modal：延後回應後直接更新那則面板（選單回到未選取、清單是最新的）
        await interaction.response.defer()
        try:
            kind = (self.kind.values or ["instant"])[0]
            draft = parse_draft(self.name.value, self.price.value, self.limit.value, self.cutoff.value,
                                kind=kind, now=_now(), min_limit=0 if self.variant is not None else 1,
                                allow_unused_cutoff=self.variant is not None,
                                keep_cutoff=self.variant.cutoff if self.cutoff_locked else None)
            if self.variant is None:
                listing = await shop.add_variants(self.listing_id, interaction.user, [draft])
                return await _show_panel(interaction, shop, listing, f"已新增「{draft.name}」。")
            listing, note = await shop.edit_variant(self.listing_id, interaction.user, self.variant.key, draft)
            return await _show_panel(interaction, shop, listing, f"已更新「{draft.name}」。{note}")
        except ShopError as exc:
            text = f"⚠️ {exc}"
        except Exception:  # 邊界：一次表單送出
            logger.error("商品上架：儲存品項失敗 商品=%s", self.listing_id, exc_info=True)
            text = _ERROR_TEXT
        await _panel_with_error(interaction, shop, self.listing_id, text)


class DelayModal(discord.ui.Modal):
    """延期：選品項、填新日期，原因選填（會寫在給需求方的通知裡）。"""

    def __init__(self, listing_id: int, variants: Sequence[Variant]):
        super().__init__(title="延期", timeout=_MODAL_TIMEOUT)
        self.listing_id = listing_id
        now = _now()
        self.variant = discord.ui.Select(min_values=1, max_values=1, required=True, options=[
            discord.SelectOption(label=v.name[:100], value=str(v.key),
                                 description=("已截止" if v.cutoff_passed(now) else f"{format_cutoff(v.cutoff)} 截止")[:100])
            for v in variants[:25]])
        self.date = discord.ui.TextInput(max_length=16, placeholder="2027/03/31")
        self.reason = discord.ui.TextInput(required=False, max_length=200, style=discord.TextStyle.paragraph)
        self.add_item(discord.ui.Label(text="品項", component=self.variant))
        self.add_item(discord.ui.Label(
            text="延到", description="還沒截止：新的截止時間；已截止：預計交貨（定金是預計到貨）日，不會重新開放下單",
            component=self.date))
        self.add_item(discord.ui.Label(text="原因", description="選填，會寫在給需求方的通知裡", component=self.reason))

    async def on_submit(self, interaction: discord.Interaction):
        shop = _shop(interaction)
        if shop is None:
            return await _missing(interaction)
        await interaction.response.defer()
        try:
            text = await shop.delay(self.listing_id, interaction.user, int(self.variant.values[0]),
                                    self.date.value, self.reason.value)
            listing = await shop.check_manager(self.listing_id, interaction.user)
            return await _show_panel(interaction, shop, listing, text)
        except ShopError as exc:
            text = f"⚠️ {exc}"
        except Exception:  # 邊界：一次表單送出
            logger.error("商品上架：延期失敗 商品=%s", self.listing_id, exc_info=True)
            text = _ERROR_TEXT
        await _panel_with_error(interaction, shop, self.listing_id, text)


class DepositConvertModal(discord.ui.Modal):
    """上線銜接（market_transition）：整篇改成定金＋尾款，原本的價格當定金；填一個收定金截止、每個品項的尾款。"""

    def __init__(self, listing: Listing):
        super().__init__(title="改成定金＋尾款", timeout=_MODAL_TIMEOUT)
        self.listing_id = listing.thread_id
        cutoff = next((v.cutoff for v in listing.variants if v.cutoff is not None), None)
        self.cutoff = discord.ui.TextInput(max_length=16, placeholder="2027/02/28 23:59",
                                           default=format_cutoff(cutoff) if cutoff and cutoff > _now() else None)
        lines = "\n".join(f"{n}. {v.name[:60]}｜" for n, v in enumerate(listing.variants, start=1))
        self.balances = discord.ui.TextInput(style=discord.TextStyle.paragraph, max_length=4000, default=lines[:4000])
        self.add_item(discord.ui.Label(text="收定金截止", description="整篇一起；只寫日期＝當天 23:59",
                                       component=self.cutoff))
        self.add_item(discord.ui.Label(
            text="每個品項的尾款", description="在每行的「｜」後面填尾款，例「1. 標準版｜1300」；原本的價格當定金",
            component=self.balances))

    async def on_submit(self, interaction: discord.Interaction):
        shop = _shop(interaction)
        if shop is None:
            return await _missing(interaction)
        await interaction.response.defer()
        try:
            text = await transition.convert(shop, self.listing_id, interaction.user, self.cutoff.value,
                                            self.balances.value)
            listing = await shop.check_manager(self.listing_id, interaction.user)
            return await _show_panel(interaction, shop, listing, text)
        except ShopError as exc:
            text = f"⚠️ {exc}"
        except Exception:  # 邊界：一次表單送出
            logger.error("商品上架：改成定金＋尾款失敗 商品=%s", self.listing_id, exc_info=True)
            text = _ERROR_TEXT
        await _panel_with_error(interaction, shop, self.listing_id, text)


# ── 商品資訊（上架、編輯） ──

def _selected_ids(data: Optional[dict], custom_id: str) -> list[str]:
    """表單送出資料裡，某個上傳元件的附件 id，照使用者選的順序（Label、ActionRow 裡的也找得到）。"""
    pending = list((data or {}).get("components") or [])
    while pending:
        component = pending.pop(0)
        if component.get("type") == 1:
            pending[0:0] = component.get("components") or []
        elif component.get("type") == 18:
            pending.insert(0, component.get("component") or {})
        elif component.get("custom_id") == custom_id:
            return [str(value) for value in component.get("values") or []]
    return []


def _uploaded_in_order(interaction: discord.Interaction, upload: discord.ui.FileUpload) -> list:
    """上傳的圖照使用者選的順序排：第一張當商品大圖，其餘照選的順序排在上面。

    discord.py 的 `FileUpload.values` 是照互動資料裡附件對照表（resolved）的順序排，不看元件送來的
    `values` 清單；照那張表排，商品圖曾整串倒過來（大圖是最後選的那張）。找不到順序清單時照收到的順序。"""
    received = list(upload.values or [])
    order = _selected_ids(getattr(interaction, "data", None), upload.custom_id)
    rank = {attachment_id: index for index, attachment_id in enumerate(order)}
    ordered = sorted(received, key=lambda attachment: rank.get(str(attachment.id), len(rank)))
    if [a.id for a in ordered] != [a.id for a in received]:
        logger.info("商品上架：上傳的圖照選取順序重排 選取=%s 收到=%s", order, [str(a.id) for a in received])
    return ordered


class ListingInfoModal(discord.ui.Modal):
    def __init__(self, *, listing: Optional[Listing] = None, default_unit: str = "NT$"):
        super().__init__(title="編輯商品資訊" if listing else "上架商品", timeout=_MODAL_TIMEOUT)
        self.listing = listing
        self.title_input = discord.ui.TextInput(label="標題", max_length=TITLE_LIMIT,
                                                default=listing.title if listing else None)
        self.description = discord.ui.TextInput(
            label="說明（交貨時間、需要需求方提供的資料等）", style=discord.TextStyle.paragraph, required=False,
            max_length=2000, default=(listing.description or None) if listing else None)
        self.unit = discord.ui.TextInput(required=False, max_length=UNIT_LIMIT,
                                         default=listing.unit if listing else default_unit)
        self.images = discord.ui.FileUpload(min_values=0, max_values=10, required=False)
        # 新上架預設實體：數位選成實體頂多多按一次「已收到」，實體選成數位卻會 24 小時自動完成
        delivery = listing.delivery if listing else "physical"
        self.delivery = discord.ui.Select(min_values=1, max_values=1, required=True, options=[
            discord.SelectOption(label="實體（要寄送，需求方收到後確認）", value="physical", default=delivery == "physical"),
            discord.SelectOption(label="數位（帳號、代儲、道具，交付後就到手）", value="digital",
                                 default=delivery == "digital"),
        ])
        # 短的、必選的放前面，長篇的說明放最後
        self.add_item(self.title_input)
        self.add_item(discord.ui.Label(
            text="幣別",
            description=f"金額前面的符號，例：{UNIT_EXAMPLES}（金額在品項裡填）",
            component=self.unit))
        self.add_item(discord.ui.Label(text="交付方式", description="有交易在進行時不能改", component=self.delivery))
        self.add_item(discord.ui.Label(
            text="換商品圖（不上傳就沿用原本的圖）" if listing else "商品圖（最多 10 張，可不傳）",
            component=self.images))
        self.add_item(self.description)

    async def on_submit(self, interaction: discord.Interaction):
        shop = _shop(interaction)
        if shop is None:
            return await _missing(interaction)
        attachments = _uploaded_in_order(interaction, self.images)
        delivery = (self.delivery.values or [None])[0]
        if self.listing is not None:
            # 從管理面板打開的：更新那則面板
            await interaction.response.defer()
            try:
                listing = await shop.edit_info(self.listing.thread_id, interaction.user, title=self.title_input.value,
                                               description=self.description.value, unit=self.unit.value,
                                               delivery=delivery, attachments=attachments)
                return await _show_panel(interaction, shop, listing, "已更新商品資訊。")
            except ShopError as exc:
                text = f"⚠️ {exc}"
            except Exception:  # 邊界：一次表單送出
                logger.error("商品上架：儲存商品資訊失敗", exc_info=True)
                text = _ERROR_TEXT
            return await _panel_with_error(interaction, shop, self.listing.thread_id, text)
        # 從置頂說明打開的（上架）：另發一則只有自己看得到的結果，不能去改置頂說明
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            thread = await shop.create_listing(
                interaction.user, title=self.title_input.value, description=self.description.value,
                unit=self.unit.value, delivery=delivery or "physical", attachments=attachments)
            text = f"已上架：{thread.mention}\n接著到貼文按「⚙️ 管理商品（供應方）」加入品項。"
        except ShopError as exc:
            text = str(exc)
        except Exception:  # 邊界：一次表單送出
            logger.error("商品上架：上架失敗", exc_info=True)
            text = _ERROR_TEXT
        await _reply(interaction, text)


# ── 購買 ──

def _quote_embed(quote) -> discord.Embed:
    unit = quote.listing.unit
    text = "\n".join(f"・{row}" for row in quote.rows)
    if quote.later_total:
        text += (f"\n\n**現在要付：定金 {money(unit, quote.now_total)}**\n"
                 f"到貨後再付：尾款 {money(unit, quote.later_total)}（會在交易對話通知你）")
    else:
        text += f"\n\n**總計 {money(unit, quote.now_total)}**"
    if quote.joins_open_trade:
        text += "\n會加進你和供應方還在進行的交易對話。"
    elif len(quote.rows) > 1:
        text += f"\n這 {len(quote.rows)} 個品項會在同一個交易對話。"
    embed = discord.Embed(title=f"確認下單：{quote.listing.title}", color=discord.Color.gold(), description=text)
    embed.set_footer(text="按「確認下單」後會預留數量，並開啟交易對話，請在裡面溝通細節。")
    return embed


def _quote_view(listing_id: int, picks: dict[int, int], signature: str) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    view.add_item(ShopConfirmOrder(listing_id, picks, signature))
    view.add_item(ShopAbort())
    return view


class QuantityModal(discord.ui.Modal):
    def __init__(self, listing_id: int, variants: Sequence[Variant]):
        super().__init__(title="填寫數量", timeout=_MODAL_TIMEOUT)
        self.listing_id = listing_id
        self.inputs: list[tuple[int, str, discord.ui.TextInput]] = []
        for variant in variants:
            hint = "不限量" if variant.remaining is None else f"剩 {variant.remaining}"
            field = discord.ui.TextInput(label=variant.name[:45], default="1", placeholder=hint, max_length=4)
            self.add_item(field)
            self.inputs.append((variant.key, variant.name, field))

    async def on_submit(self, interaction: discord.Interaction):
        shop = _shop(interaction)
        if shop is None:
            return await _missing(interaction)
        picks: dict[int, int] = {}
        for key, name, field in self.inputs:
            text = field.value.strip()
            # isdecimal：只收十進位數字（含全形）；isdigit 會放過「²」「①」，int() 卻讀不了
            if not text.isdecimal() or int(text) < 1:
                return await _reply(interaction, f"「{name}」的數量要填正整數。")
            picks[key] = int(text)
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            quote = await shop.quote(self.listing_id, interaction.user, picks)
        except ShopError as exc:
            return await _reply(interaction, str(exc))
        await safe_send_interaction_message(interaction, embed=_quote_embed(quote),
                                            view=_quote_view(self.listing_id, picks, quote.signature), ephemeral=True)


class ShopConfirmOrder(discord.ui.DynamicItem[discord.ui.Button],
                       template=r"shop:confirm:(?P<listing>\d+):(?P<items>[0-9x,]+)(?::(?P<sig>[0-9a-f]{8}))?"):
    """確認下單：custom_id 帶品項×數量與確認畫面上金額的指紋，按下時重算，對不上就重新顯示。"""

    def __init__(self, listing_id: int, picks: dict[int, int], signature: Optional[str] = None):
        custom_id = f"shop:confirm:{listing_id}:{encode_items(picks)}" + (f":{signature}" if signature else "")
        super().__init__(discord.ui.Button(label="確認下單", style=discord.ButtonStyle.green, custom_id=custom_id))
        self.listing_id = listing_id
        self.picks = picks
        self.signature = signature

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button, match, /):
        return cls(int(match["listing"]), decode_items(match["items"]), match["sig"])

    async def callback(self, interaction: discord.Interaction):
        shop = _shop(interaction)
        if shop is None:
            return await _missing(interaction)
        await interaction.response.edit_message(content="下單中……", embed=None, view=None)  # 先拿掉按鈕，避免連按
        try:
            opened = await shop.place_order(self.listing_id, interaction.user, self.picks, self.signature)
            text = f"已下單，請到交易對話跟供應方確認細節：{opened.thread.mention}"
        except PriceChanged as exc:
            try:
                quote = await shop.quote(self.listing_id, interaction.user, self.picks)
            except ShopError as again:
                return await interaction.edit_original_response(content=f"沒有下單：{again}")
            return await interaction.edit_original_response(
                content=f"⚠️ {exc}", embed=_quote_embed(quote),
                view=_quote_view(self.listing_id, self.picks, quote.signature))
        except ShopError as exc:
            text = f"沒有下單：{exc}"
        except Exception:  # 邊界：一次按鈕互動
            logger.error("商品上架：下單失敗 商品=%s", self.listing_id, exc_info=True)
            text = "下單時發生錯誤，請截圖通知管理員。"
        await interaction.edit_original_response(content=text)


class ShopAbort(discord.ui.DynamicItem[discord.ui.Button], template=r"shop:abort"):
    def __init__(self):
        super().__init__(discord.ui.Button(label="取消", style=discord.ButtonStyle.secondary, custom_id="shop:abort"))

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button, match, /):
        return cls()

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.edit_message(content="已取消，沒有下單。", embed=None, view=None)


# ── 交易進度上的按鈕 ──

_STEP_STYLE = {
    tp.CONFIRM_DEPOSIT: discord.ButtonStyle.success,
    tp.CONFIRM_BALANCE: discord.ButtonStyle.success,
    tp.CONFIRM_FULL: discord.ButtonStyle.success,
    tp.CLAIM_PAID: discord.ButtonStyle.secondary,
    tp.DELIVER: discord.ButtonStyle.primary,
    tp.SHIP: discord.ButtonStyle.primary,
    tp.RECEIVE: discord.ButtonStyle.success,
}


async def _run_step(interaction: discord.Interaction, action: str, key: Optional[int],
                    version: Optional[int] = None) -> None:
    shop = _shop(interaction)
    if shop is None:
        return await _missing(interaction)
    await interaction.response.defer()
    try:
        reason = await shop.trades.handle_step(interaction.user, interaction.channel, action, key, version)
    except Exception:  # 邊界：一次按鈕互動，做壞了回按的人一句
        logger.error("商品上架：交易進度 %s 失敗 thread=%s", action, getattr(interaction.channel, "id", None),
                     exc_info=True)
        reason = "處理交易時發生錯誤，請截圖通知管理員。"
    if reason:
        # 理由會列出卡住的品項，品項很多、名稱又長時會超過一則的上限：切段回
        await safe_send_interaction_text(interaction, reason, ephemeral=True)


class ShopStepButton(discord.ui.DynamicItem[discord.ui.Button], template=STEP_TEMPLATE):
    """交易進度上的按鈕：custom_id 只帶動作、品項編號與卡片版本，交易是哪一筆、誰能按照所在的交易對話查資料庫。"""

    def __init__(self, action: str, key: Optional[int], version: Optional[int] = None, *, label: str = "",
                 who: str = "", row: Optional[int] = None):
        super().__init__(discord.ui.Button(label=(label or action)[:80], row=row,
                                           style=_STEP_STYLE.get(action, discord.ButtonStyle.secondary),
                                           custom_id=Step(action, key, label, who, version).custom_id))
        self.action = action
        self.key = key
        self.version = version

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button, match, /):
        return cls(match["action"], int(match["key"]) if match["key"] else None,
                   int(match["version"]) if match["version"] else None, label=item.label or "")

    async def callback(self, interaction: discord.Interaction):
        await _run_step(interaction, self.action, self.key, self.version)


class ShopStepSelect(discord.ui.DynamicItem[discord.ui.Select],
                     template=r"trade:step:pick:(?P<action>deliver|ship|receive)"):
    """品項多到按鈕放不下時的選單：選一個品項＝按它的按鈕。"""

    def __init__(self, action: str, *, options: Sequence[discord.SelectOption] = (), row: Optional[int] = None):
        placeholder = {tp.DELIVER: "選擇已交付的品項", tp.SHIP: "選擇已寄出的品項", tp.RECEIVE: "選擇已收到的品項"}[action]
        super().__init__(discord.ui.Select(
            custom_id=f"trade:step:pick:{action}", min_values=1, max_values=1, placeholder=placeholder, row=row,
            options=list(options) or [discord.SelectOption(label="（沒有品項）", value="0")]))
        self.action = action

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Select, match, /):
        return cls(match["action"], options=item.options)

    async def callback(self, interaction: discord.Interaction):
        await _run_step(interaction, self.action, int(self.item.values[0]))


# ── 置頂上架說明 ──

class GuideView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="上架商品", emoji="🛒", style=discord.ButtonStyle.primary, custom_id=GUIDE_CUSTOM_ID)
    async def new_listing(self, interaction: discord.Interaction, button: discord.ui.Button):
        shop = _shop(interaction)
        if shop is None:
            return await _missing(interaction)
        if not shop.trade.ready.is_set():
            return await _reply(interaction, NOT_READY_TEXT)
        if not await shop.can_sell(interaction.user):
            return await _reply(interaction, "只有觀星者可以上架商品。")
        await interaction.response.send_modal(ListingInfoModal(default_unit=shop.settings.default_unit))

    @discord.ui.button(label="我的交易", emoji="📋", style=discord.ButtonStyle.secondary, custom_id=MINE_CUSTOM_ID)
    async def my_trades(self, interaction: discord.Interaction, button: discord.ui.Button):
        """只列按的人當供應方、還沒結束的交易；要讀每個交易對話看有沒有動靜，先回應再查。"""
        shop = _shop(interaction)
        if shop is None:
            return await _missing(interaction)
        if not shop.trade.ready.is_set():
            return await _reply(interaction, NOT_READY_TEXT)
        # 被拿掉觀星者身份組的人手上可能還有交易（週報也會叫他來按）：有自己當供應方的交易就給看
        if not await shop.can_sell(interaction.user) and not await shop.trade.has_open_trades(interaction.user.id):
            return await _reply(interaction, "只有觀星者有自己的交易清單。")
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            # 只整理自己當供應方的：每一筆都要讀交易對話看有沒有動靜，不必把別人的也讀一遍
            summaries = await market_report.summarize(shop, _now(), supplier_id=interaction.user.id)
            text = market_report.my_trades_text(summaries, interaction.user.id)
        except Exception:  # 邊界：一次按鈕互動
            logger.error("商品上架：我的交易清單失敗", exc_info=True)
            text = _ERROR_TEXT
        await safe_send_interaction_text(interaction, text, ephemeral=True)


_DYNAMIC_ITEMS = (ShopBuySelect, ShopManageButton, ShopPanelButton, ShopScheduleSelect, ShopPickSelect,
                  ShopConfirmButton, ShopBatchButton, ShopConfirmOrder, ShopAbort, ShopStepButton, ShopStepSelect)


class ShopCommands(commands.Cog):
    def __init__(self, bot: commands.Bot, settings: Optional[ShopSettings] = None):
        self.bot = bot
        self.settings = settings or ShopSettings()
        self.shop: Optional[ShopService] = None
        self._tasks: list[asyncio.Task] = []
        # 第一次匯入與群主按「重新偵測」不能同時跑
        self._import_lock = asyncio.Lock()

    async def cog_load(self):
        # 下單要靠交易模組開對話；COMMAND_MODULES 依字母順序載入，forum_monitor 在前面
        trade_cog = self.bot.get_cog("ForumMonitor")
        if trade_cog is None:
            logger.error("商品上架：交易模組（ForumMonitor）沒有載入，商品上架停用")
            return
        self.shop = ShopService(self.bot, trade=trade_cog.trade, views=DiscordShopViews(self.settings),
                                settings=self.settings)
        trade_cog.trade.add_source_kind(self.shop.source)
        self.bot.add_dynamic_items(*_DYNAMIC_ITEMS)
        self.bot.add_view(GuideView())
        owner_alerts.register(ALERT_KIND, title="商品市集", retest=self._retest_import, status=self._import_status)
        self._tasks = [
            spawn(self._first_import(), name="market_import"),
            supervise(lambda: run_due_loop("商品截止", self.shop.run_cutoffs, wait_ready=self.bot.wait_until_ready,
                                           max_sleep=self.settings.cutoff_check_max_sleep_seconds,
                                           wake=self.shop.cutoffs_changed),
                      name="shop_cutoffs"),
            supervise(lambda: run_due_loop("商品交易等待提醒", self.shop.trades.run_waiting_reminders,
                                           wait_ready=self.bot.wait_until_ready,
                                           max_sleep=self.settings.cutoff_check_max_sleep_seconds),
                      name="shop_waiting_reminders"),
            supervise(lambda: run_due_loop("市集資料庫備份", self._backup, wait_ready=self.bot.wait_until_ready,
                                           max_sleep=6 * 3600),
                      name="market_backup"),
            supervise(lambda: run_due_loop("市集週報", lambda now: market_report.run_weekly(self.shop, now),
                                           wait_ready=self.bot.wait_until_ready, max_sleep=6 * 3600),
                      name="market_weekly"),
        ]

    async def dashboard(self, supplier_id: Optional[int] = None) -> tuple[str, list[tuple[int, str]]]:
        """主控台的交易看板（群主）：(總表, 可以點進去看的觀星者 [(id, 名字)])；給 supplier_id 就是那一位的清單。"""
        if self.shop is None:
            return "商品市集沒有載入。", []
        if not self.shop.trade.ready.is_set():
            return NOT_READY_TEXT, []
        if supplier_id is not None:
            # 群主看的是別人的清單：標題寫是誰、說「他」不說「你」
            summaries = await market_report.summarize(self.shop, _now(), supplier_id=supplier_id)
            names = await self.shop.trade.display_names(await market_report.guild_of(self.shop), (supplier_id,))
            return market_report.my_trades_text(summaries, supplier_id,
                                                name=names.get(supplier_id, f"已離開的成員 {supplier_id}")), []
        summaries = await market_report.summarize(self.shop, _now())
        ids = sorted({s.supplier_id for s in summaries})
        names = await self.shop.trade.display_names(await market_report.guild_of(self.shop), ids)
        return (await market_report.dashboard_text(self.shop, summaries, _now()),
                [(i, names.get(i, str(i))) for i in ids])

    async def _backup(self, now: datetime) -> datetime:
        """每天固定時刻一份備份（今天已經有就不做）；開機時已經過了今天的時刻就先補。
        排程最多睡 6 小時就會醒一次：換日後、還沒到時刻的那次不做，不然備份時刻會跟著開機時間漂。"""
        local = now.astimezone(APP_TZ)
        today_at = datetime.combine(local.date(), _BACKUP_AT, APP_TZ)
        if local < today_at:
            return today_at
        if not self.shop.trade.ready.is_set():
            # 上線匯入還沒做完：這時備份到的是空的資料庫，而今天有了一份就不會再備，等匯入做完
            return now + timedelta(minutes=5)
        await backup_daily(await self.shop.db(), MARKET_BACKUP_DIR, today=local.date().isoformat())
        return today_at + timedelta(days=1)

    async def _first_import(self) -> None:
        await self.bot.wait_until_ready()
        await self._import()

    async def _import(self) -> bool:
        """上線匯入：做完才開放商品與交易按鈕；失敗私訊群主，按鈕維持擋住，修好後「重新偵測」重跑。"""
        async with self._import_lock:
            try:
                result = await run_import(self.shop)
            except Exception as exc:  # 邊界：匯入失敗要告訴群主、按鈕擋著，不能讓 cog 的背景任務默默結束
                logger.error("市集匯入失敗", exc_info=True)
                owner_alerts.emit(ALERT_KIND, "import",
                                  f"商品市集上線匯入失敗（{type(exc).__name__}: {exc}）。商品與交易的按鈕先擋著，"
                                  "原因寫在 log；修好後按「重新偵測」重跑，已經匯好的不會重複。")
                return False
        if not result.already_done:
            owner_alerts.inform(ALERT_KIND, "import", result.summary())
        try:
            # 置頂的上架說明照這一版更新（新按鈕、新的流程說明），不用等群主重綁商品論壇
            await self.shop.refresh_guide()
        except Exception:  # 邊界：說明沒更新只影響顯示，按鈕已經開放
            logger.warning("商品上架：重啟後更新上架說明失敗", exc_info=True)
        return True

    async def _retest_import(self, key: str) -> owner_alerts.RetestResult:
        ok = await self._import()
        return owner_alerts.RetestResult(ok, "匯入完成，商品與交易已開放。" if ok else "還是失敗，原因寫在 log。")

    def _import_status(self):
        if self.shop is not None and self.shop.trade.ready.is_set():
            return "商品與交易已開放"
        return owner_alerts.Status("watch", "上線匯入還沒做完，商品與交易按鈕擋著")

    async def cog_unload(self):
        for task in self._tasks:
            task.cancel()
        self._tasks = []
        self.bot.remove_dynamic_items(*_DYNAMIC_ITEMS)


async def setup(bot):
    await bot.add_cog(ShopCommands(bot))
