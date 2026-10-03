"""商品上架的 Discord 介面：置頂說明的「上架商品」、商品貼文的購買選單與管理按鈕、管理面板與各個 modal。

做事的是 `services.community.shop_service`；這裡只負責元件長相，並把互動交給它。
按鈕與選單都把需要的資料寫在 custom_id（DynamicItem），bot 重啟後按下去照樣有效；
modal 和只有自己看得到的暫時訊息本來就是一次性的。
"""
import asyncio
import logging
import re
from datetime import datetime
from typing import Optional, Sequence
from urllib.parse import unquote

import discord
from discord.ext import commands

from services.community.shop_listing import (
    BUY_TEMPLATE,
    MANAGE_TEMPLATE,
    NAME_LIMIT,
    TITLE_LIMIT,
    UNIT_LIMIT,
    Listing,
    ShopError,
    Variant,
    buy_custom_id,
    decode_items,
    encode_items,
    format_cutoff,
    listing_from_message,
    manage_custom_id,
    money,
    order_custom_id,
    parse_batch,
    parse_draft,
    select_options,
)
from services.community.shop_service import UNIT_EXAMPLES, ShopService
from sys_settings.shop_settings import ShopSettings
from sys_settings.time_settings import APP_TZ
from utils.due_loop import run_due_loop
from utils.utils import safe_send_interaction_message

logger = logging.getLogger(__name__)

GUIDE_CUSTOM_ID = "shop:new"
_CODE_BLOCK = re.compile(r"```\n?(.*?)```", re.DOTALL)
#: modal 開著沒送出就關掉時，最多在記憶體裡留這麼久（跟專案其他 modal 一致）
_MODAL_TIMEOUT = 600


def _shop(interaction: discord.Interaction) -> Optional[ShopService]:
    return getattr(interaction.client.get_cog("ShopCommands"), "shop", None)


async def _reply(interaction: discord.Interaction, text: str, **kwargs) -> None:
    await safe_send_interaction_message(interaction, text, ephemeral=True, **kwargs)


async def _missing(interaction: discord.Interaction) -> None:
    await _reply(interaction, "商品上架功能目前沒有載入，請通知管理員。")


def _now() -> datetime:
    return datetime.now(APP_TZ)


# ── 商品貼文上的元件 ──

class DiscordShopViews:
    """`ShopViews` 的實作：交給 ShopService 產生商品貼文、訂單訊息、置頂說明上的元件。"""

    def __init__(self, settings: ShopSettings):
        self.settings = settings

    def listing(self, listing: Listing, now: datetime) -> discord.ui.View:
        view = discord.ui.View(timeout=None)
        if listing.variants:
            options = select_options(listing, now)
            view.add_item(ShopBuySelect(listing.thread_id, options=options,
                                        max_values=min(self.settings.max_pick, len(options)),
                                        disabled=listing.closed))
        view.add_item(ShopManageButton(listing.owner_id, listing.next_key(), listing.unit, disabled=listing.closed))
        return view

    def order(self, listing_id: int, picks: dict[int, int]) -> discord.ui.View:
        # 停用的按鈕只是用來記錄訂單（custom_id 帶「商品編號x數量」），取消時靠它還回預留
        view = discord.ui.View(timeout=None)
        view.add_item(discord.ui.Button(label="訂單紀錄", emoji="🧾", style=discord.ButtonStyle.secondary,
                                        disabled=True, custom_id=order_custom_id(listing_id, picks)))
        return view

    def guide(self) -> discord.ui.View:
        return GuideView()


class ShopBuySelect(discord.ui.DynamicItem[discord.ui.Select], template=BUY_TEMPLATE):
    """商品貼文的購買下拉：選項就是品相資料（見 shop_listing）。"""

    def __init__(self, listing_id: int, *, options: Sequence[discord.SelectOption] = (),
                 max_values: int = 1, disabled: bool = False):
        super().__init__(discord.ui.Select(
            custom_id=buy_custom_id(listing_id), placeholder="選擇要購買的商品（可多選）",
            min_values=1, max_values=max(1, max_values), disabled=disabled,
            options=list(options) or [discord.SelectOption(label="（沒有商品）", value="-")],
        ))
        self.listing_id = listing_id

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Select, match, /):
        return cls(int(match["listing"]), options=item.options, max_values=item.max_values, disabled=item.disabled)

    async def callback(self, interaction: discord.Interaction):
        shop = _shop(interaction)
        if shop is None:
            return await _missing(interaction)
        keys = [int(v.split(":", 1)[0]) for v in self.item.values if v.split(":", 1)[0].isdigit()]
        try:
            # 互動帶來的就是商品貼文第一則，跟重讀一樣新；送出 modal 要在 3 秒內，所以不再讀一次
            variants = await shop.check_pick(self.listing_id, interaction.user, keys,
                                             listing=listing_from_message(interaction.message))
        except ShopError as exc:
            return await _reply(interaction, str(exc))
        await interaction.response.send_modal(QuantityModal(self.listing_id, variants))


class ShopManageButton(discord.ui.DynamicItem[discord.ui.Button], template=MANAGE_TEMPLATE):
    """「⚙️ 管理商品（上架者）」：custom_id 帶上架者、下一個品相編號、幣別。
    大家都看得到（Discord 沒辦法依身份組隱藏），只有上架者與管理員能用。"""

    def __init__(self, owner_id: int, key_seq: int, unit: str, *, disabled: bool = False):
        super().__init__(discord.ui.Button(
            label="管理商品（上架者）", emoji="⚙️", style=discord.ButtonStyle.secondary,
            custom_id=manage_custom_id(owner_id, key_seq, unit), disabled=disabled))

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button, match, /):
        return cls(int(match["owner"]), int(match["seq"]), unquote(match["unit"]), disabled=item.disabled)

    async def callback(self, interaction: discord.Interaction):
        shop = _shop(interaction)
        if shop is None:
            return await _missing(interaction)
        try:
            listing = await shop.check_manager(interaction.channel.id, interaction.user,
                                               listing=listing_from_message(interaction.message),
                                               guild=interaction.guild)
        except ShopError as exc:
            return await _reply(interaction, str(exc))
        await safe_send_interaction_message(
            interaction, embed=_panel_embed(listing), view=_panel_view(listing), ephemeral=True)


# ── 管理面板（只有上架者看得到的暫時訊息） ──

_PANEL_ACTIONS = {
    # 主要動作藍、一般灰、會刪東西的紅（使用者 2026-10-03）；編輯／刪除品相是面板裡的兩個選單
    "add": ("新增品相", discord.ButtonStyle.primary),
    "batch": ("批次新增", discord.ButtonStyle.primary),
    "info": ("編輯商品資訊", discord.ButtonStyle.secondary),
    "close": ("下架", discord.ButtonStyle.danger),
}


def _panel_embed(listing: Listing) -> discord.Embed:
    now = _now()
    lines = [f"{n}. {v.name}｜{v.status(listing.unit, now)}" for n, v in enumerate(listing.variants, start=1)]
    embed = discord.Embed(title=f"管理商品：{listing.title}", color=discord.Color.gold(),
                          description="\n".join(lines) or "還沒有品相，先按「新增品相」或「批次新增」。")
    embed.set_footer(text="這個面板只有你看得到")
    return embed


def _panel_view(listing: Listing) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    for action in _PANEL_ACTIONS:
        view.add_item(ShopPanelButton(action, listing.thread_id))
    if listing.variants:
        # 選項的 value 就是品相資料：選了直接開 modal，不必再向 Discord 讀（modal 要在 3 秒內送出）
        options = [discord.SelectOption(label=f"{n}. {v.name}", value=v.encode())
                   for n, v in enumerate(listing.variants, start=1)]
        view.add_item(ShopPickSelect("edit", listing.thread_id, options=options))
        view.add_item(ShopPickSelect("delete", listing.thread_id, options=options))
    return view


class ShopPanelButton(discord.ui.DynamicItem[discord.ui.Button],
                      template=r"shop:panel:(?P<action>add|batch|info|close):(?P<listing>\d+)"):
    """管理面板的按鈕。面板只有上架者看得到；真正寫入時 ShopService 會再檢查一次權限。"""

    def __init__(self, action: str, listing_id: int):
        label, style = _PANEL_ACTIONS[action]
        super().__init__(discord.ui.Button(label=label, style=style, custom_id=f"shop:panel:{action}:{listing_id}"))
        self.action = action
        self.listing_id = listing_id

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button, match, /):
        return cls(match["action"], int(match["listing"]))

    async def callback(self, interaction: discord.Interaction):
        shop = _shop(interaction)
        if shop is None:
            return await _missing(interaction)
        if self.action == "add":
            await interaction.response.send_modal(VariantModal(self.listing_id))
        elif self.action == "batch":
            await interaction.response.send_modal(BatchModal(self.listing_id))
        elif self.action == "close":
            view = discord.ui.View(timeout=None)
            view.add_item(ShopConfirmButton("close", self.listing_id))
            await _reply(interaction, "確定要下架這篇商品嗎？下架後不再接單，已成立的交易照常進行。", view=view)
        else:
            # 編輯商品資訊要帶入目前的標題與說明，只能讀一次商品貼文（偶爾慢於 3 秒時 modal 會開不起來）
            try:
                listing = await shop.check_manager(self.listing_id, interaction.user)
            except ShopError as exc:
                return await _reply(interaction, str(exc))
            await interaction.response.send_modal(ListingInfoModal(listing=listing))


class ShopPickSelect(discord.ui.DynamicItem[discord.ui.Select],
                     template=r"shop:pick:(?P<action>edit|delete):(?P<listing>\d+)"):
    """管理面板裡的「編輯品相」「刪除品相」選單；選項 value 是品相資料，label 是「序號. 名稱」。"""

    def __init__(self, action: str, listing_id: int, *, options: Sequence[discord.SelectOption] = ()):
        super().__init__(discord.ui.Select(
            custom_id=f"shop:pick:{action}:{listing_id}", min_values=1, max_values=1,
            placeholder="編輯品相⋯" if action == "edit" else "刪除品相⋯",
            options=list(options) or [discord.SelectOption(label="（沒有品相）", value="0")]))
        self.action = action
        self.listing_id = listing_id

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Select, match, /):
        return cls(match["action"], int(match["listing"]), options=item.options)

    async def callback(self, interaction: discord.Interaction):
        shop = _shop(interaction)
        if shop is None:
            return await _missing(interaction)
        value = self.item.values[0]
        option = next((o for o in self.item.options if o.value == value), None)
        name = option.label.split(". ", 1)[-1] if option else ""
        variant = Variant.decode(value, name)
        if variant is None:
            return await _reply(interaction, "找不到這個品相，可能已經被刪除。")
        if self.action == "edit":
            await interaction.response.send_modal(VariantModal(self.listing_id, variant))
        else:
            view = discord.ui.View(timeout=None)
            view.add_item(ShopConfirmButton("delete", self.listing_id, variant.key))
            await _reply(interaction, f"確定要刪除「{variant.name}」嗎？", view=view)


class ShopConfirmButton(discord.ui.DynamicItem[discord.ui.Button],
                        template=r"shop:(?P<action>del|closeok):(?P<listing>\d+)(?::(?P<key>\d+))?"):
    """刪除品相、下架前的確認。"""

    def __init__(self, action: str, listing_id: int, key: Optional[int] = None):
        code = "del" if action == "delete" else "closeok"
        custom_id = f"shop:{code}:{listing_id}" + (f":{key}" if key is not None else "")
        super().__init__(discord.ui.Button(label="確定刪除" if action == "delete" else "確定下架",
                                           style=discord.ButtonStyle.danger, custom_id=custom_id))
        self.action = action
        self.listing_id = listing_id
        self.key = key

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button, match, /):
        key = int(match["key"]) if match["key"] else None
        return cls("delete" if match["action"] == "del" else "close", int(match["listing"]), key)

    async def callback(self, interaction: discord.Interaction):
        shop = _shop(interaction)
        if shop is None:
            return await _missing(interaction)
        await interaction.response.edit_message(content="處理中……", view=None)  # 先拿掉按鈕，避免連按
        try:
            if self.action == "delete":
                await shop.delete_variant(self.listing_id, interaction.user, self.key)
                text = "已刪除這個品相。"
            else:
                await shop.close_listing(self.listing_id, interaction.user)
                text = "已下架。"
        except ShopError as exc:
            text = str(exc)
        except Exception:
            logger.error("商品上架：%s 失敗 商品=%s", self.action, self.listing_id, exc_info=True)
            text = "處理時發生錯誤，請截圖通知管理員。"
        await interaction.edit_original_response(content=text)


# ── 批次新增 ──

def _batch_preview(listing_id: int, text: str, max_variants: int = 25) -> tuple[discord.Embed, discord.ui.View]:
    drafts, errors = parse_batch(text, now=_now())
    if len(drafts) > max_variants:
        errors.append(f"一篇商品最多 {max_variants} 個品相，這次填了 {len(drafts)} 個。")
    view = discord.ui.View(timeout=None)
    if errors or not drafts:
        # embed 說明上限 4096 字：錯誤最多列 15 行、原文最多 3000 字（回去修改時拿得回完整的就好）
        shown = errors[:15] + ([f"……還有 {len(errors) - 15} 行有錯"] if len(errors) > 15 else [])
        embed = discord.Embed(title="格式有錯，請修改", color=discord.Color.red(),
                              description="\n".join(shown or ["沒有填任何品相。"]) + f"\n\n你填的內容：\n```\n{text[:3000]}\n```")
    else:
        lines = "\n".join(d.line() for d in drafts)
        embed = discord.Embed(title=f"預覽：要新增 {len(drafts)} 個品相", color=discord.Color.gold(),
                              description=f"```\n{lines}\n```\n數量空白＝不限量；截止時間空白＝立即購買。")
        view.add_item(ShopBatchButton("ok", listing_id))
    view.add_item(ShopBatchButton("fix", listing_id))
    return embed, view


def _preview_text(message: Optional[discord.Message]) -> str:
    """從預覽訊息讀回內容（預覽就是暫存，不另外記在記憶體）。"""
    description = message.embeds[0].description if message and message.embeds else ""
    blocks = _CODE_BLOCK.findall(description or "")
    return blocks[-1].strip("\n") if blocks else ""


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
            embed, view = _batch_preview(self.listing_id, text)
            return await interaction.response.edit_message(embed=embed, view=view)
        await interaction.response.edit_message(content="新增中……", embed=None, view=None)
        try:
            await shop.add_variants(self.listing_id, interaction.user, drafts)
            result = f"已新增 {len(drafts)} 個品相。"
        except ShopError as exc:
            result = str(exc)
        except Exception:
            logger.error("商品上架：批次新增失敗 商品=%s", self.listing_id, exc_info=True)
            result = "處理時發生錯誤，請截圖通知管理員。"
        await interaction.edit_original_response(content=result)


_BATCH_HELP = (
    "**每行一個品相**，四欄用「｜」隔開（半形 | 也可以）：\n"
    "`名稱｜價格｜數量｜預購截止`\n"
    "・**價格**：只填數字，單位用這篇商品設定的\n"
    "・**數量**：留空＝不限量；賣完會自動標「已售完」\n"
    "・**預購截止**：留空＝立即購買；要預購就寫含年份的時間，例 `2026/10/20 23:59`\n"
    "送出後會先給你看預覽、標出格式有錯的行，按「確認新增」才會加進商品。一篇最多 25 個品相。"
)


class BatchModal(discord.ui.Modal):
    def __init__(self, listing_id: int, text: str = ""):
        super().__init__(title="批次新增品相", timeout=_MODAL_TIMEOUT)
        self.listing_id = listing_id
        self.lines = discord.ui.TextInput(
            style=discord.TextStyle.paragraph, max_length=4000, default=text or None,
            placeholder="60 月相｜30｜10｜\n6480 月相｜3000｜3｜2026/10/20 23:59")
        # 說明放在最上面（modal 支援純文字說明），輸入框本身的標題只能 45 字，寫不完
        self.add_item(discord.ui.TextDisplay(_BATCH_HELP))
        self.add_item(discord.ui.Label(text="品相清單", description="一行一個，例：60 月相｜30｜10｜",
                                       component=self.lines))

    async def on_submit(self, interaction: discord.Interaction):
        embed, view = _batch_preview(self.listing_id, self.lines.value)
        await safe_send_interaction_message(interaction, embed=embed, view=view, ephemeral=True)


# ── 單一品相 ──

class VariantModal(discord.ui.Modal):
    def __init__(self, listing_id: int, variant: Optional[Variant] = None):
        super().__init__(title="編輯品相" if variant else "新增品相", timeout=_MODAL_TIMEOUT)
        self.listing_id = listing_id
        self.variant = variant
        preorder = bool(variant and variant.preorder)
        self.name = discord.ui.TextInput(max_length=NAME_LIMIT, default=variant.name if variant else None)
        self.price = discord.ui.TextInput(max_length=9, default=str(variant.price) if variant else None)
        self.kind = discord.ui.Select(min_values=1, max_values=1, required=True, options=[
            discord.SelectOption(label="立即購買", value="instant", default=not preorder),
            discord.SelectOption(label="預購", value="preorder", default=preorder),
        ])
        self.cutoff = discord.ui.TextInput(required=False, max_length=16, placeholder="2026/10/20 23:59",
                                           default=format_cutoff(variant.cutoff) if preorder else None)
        self.limit = discord.ui.TextInput(
            required=False, max_length=6,
            default=str(variant.limit) if variant and variant.limit is not None else None)
        # modal 最多 5 個欄位，放不下整段說明，改在每個欄位底下各寫一行
        self.add_item(discord.ui.Label(text="名稱", description="買家在購買選單看到的名字，最多 80 字",
                                       component=self.name))
        self.add_item(discord.ui.Label(text="價格", description="只填數字，單位用這篇商品設定的",
                                       component=self.price))
        self.add_item(discord.ui.Label(text="類型", description="選「預購」要再填下面的截止時間",
                                       component=self.kind))
        self.add_item(discord.ui.Label(text="預購截止", description="選預購才填，要寫年份，例 2026/10/20 23:59；過了就不能再買",
                                       component=self.cutoff))
        self.add_item(discord.ui.Label(text="數量上限", description="不限量就留空；賣完會自動標「已售完」",
                                       component=self.limit))

    async def on_submit(self, interaction: discord.Interaction):
        shop = _shop(interaction)
        if shop is None:
            return await _missing(interaction)
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            draft = parse_draft(self.name.value, self.price.value, self.limit.value, self.cutoff.value,
                                preorder=(self.kind.values or ["instant"])[0] == "preorder", now=_now())
            if self.variant is None:
                await shop.add_variants(self.listing_id, interaction.user, [draft])
                text = f"已新增「{draft.name}」。"
            else:
                await shop.edit_variant(self.listing_id, interaction.user, self.variant.key, draft)
                text = f"已更新「{draft.name}」。"
        except ShopError as exc:
            text = str(exc)
        except Exception:
            logger.error("商品上架：儲存品相失敗 商品=%s", self.listing_id, exc_info=True)
            text = "處理時發生錯誤，請截圖通知管理員。"
        await _reply(interaction, text)


# ── 商品資訊（上架、編輯） ──

class ListingInfoModal(discord.ui.Modal):
    def __init__(self, *, listing: Optional[Listing] = None, default_unit: str = "NT$"):
        super().__init__(title="編輯商品資訊" if listing else "上架商品", timeout=_MODAL_TIMEOUT)
        self.listing = listing
        self.title_input = discord.ui.TextInput(label="標題", max_length=TITLE_LIMIT,
                                                default=listing.title if listing else None)
        self.description = discord.ui.TextInput(
            label="說明（交付方式、需要買家提供的資料等）", style=discord.TextStyle.paragraph, required=False,
            max_length=2000, default=(listing.description or None) if listing else None)
        self.unit = discord.ui.TextInput(required=False, max_length=UNIT_LIMIT,
                                         default=listing.unit if listing else default_unit)
        self.images = discord.ui.FileUpload(min_values=0, max_values=10, required=False)
        self.add_item(self.title_input)
        self.add_item(self.description)
        self.add_item(discord.ui.Label(
            text="幣別",
            description=f"只是金額前面的符號，不能有數字，例：{UNIT_EXAMPLES}（中文約 7 字內）。金額在加入品相時各自填",
            component=self.unit))
        self.add_item(discord.ui.Label(
            text="換商品圖（不上傳就沿用原本的圖）" if listing else "商品圖（最多 10 張，可不傳）",
            component=self.images))

    async def on_submit(self, interaction: discord.Interaction):
        shop = _shop(interaction)
        if shop is None:
            return await _missing(interaction)
        await interaction.response.defer(ephemeral=True, thinking=True)
        attachments = list(self.images.values or [])
        try:
            if self.listing is None:
                thread = await shop.create_listing(
                    interaction.user, title=self.title_input.value, description=self.description.value,
                    unit=self.unit.value, attachments=attachments)
                text = f"已上架：{thread.mention}\n接著到貼文按「⚙️ 管理商品（上架者）」加入品相。"
            else:
                await shop.edit_info(self.listing.thread_id, interaction.user, title=self.title_input.value,
                                     description=self.description.value, unit=self.unit.value,
                                     attachments=attachments)
                text = "已更新商品資訊。"
        except ShopError as exc:
            text = str(exc)
        except Exception:
            logger.error("商品上架：儲存商品資訊失敗", exc_info=True)
            text = "處理時發生錯誤，請截圖通知管理員。"
        await _reply(interaction, text)


# ── 購買 ──

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
            if not text.isdigit() or int(text) < 1:
                return await _reply(interaction, f"「{name}」的數量要填正整數。")
            picks[key] = int(text)
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            rows, total, listing = await shop.quote(self.listing_id, interaction.user, picks)
        except ShopError as exc:
            return await _reply(interaction, str(exc))
        embed = discord.Embed(title=f"確認下單：{listing.title}", color=discord.Color.gold(),
                              description="\n".join(f"・{row}" for row in rows) + f"\n\n**總計 {money(listing.unit, total)}**")
        embed.set_footer(text="按「確認下單」後會預留數量，並開一個只有你和上架者的交易 thread。")
        view = discord.ui.View(timeout=None)
        view.add_item(ShopConfirmOrder(self.listing_id, picks))
        view.add_item(ShopAbort())
        await safe_send_interaction_message(interaction, embed=embed, view=view, ephemeral=True)


class ShopConfirmOrder(discord.ui.DynamicItem[discord.ui.Button],
                       template=r"shop:confirm:(?P<listing>\d+):(?P<items>[0-9x,]+)"):
    def __init__(self, listing_id: int, picks: dict[int, int]):
        super().__init__(discord.ui.Button(label="確認下單", style=discord.ButtonStyle.green,
                                           custom_id=f"shop:confirm:{listing_id}:{encode_items(picks)}"))
        self.listing_id = listing_id
        self.picks = picks

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button, match, /):
        return cls(int(match["listing"]), decode_items(match["items"]))

    async def callback(self, interaction: discord.Interaction):
        shop = _shop(interaction)
        if shop is None:
            return await _missing(interaction)
        await interaction.response.edit_message(content="下單中……", embed=None, view=None)  # 先拿掉按鈕，避免連按
        try:
            opened = await shop.place_order(self.listing_id, interaction.user, self.picks)
            text = f"已下單，請到交易 thread 跟上架者確認細節：{opened.thread.mention}"
        except ShopError as exc:
            text = f"沒有下單：{exc}"
        except Exception:
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


# ── 置頂上架說明 ──

class GuideView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="上架商品", emoji="🛒", style=discord.ButtonStyle.primary, custom_id=GUIDE_CUSTOM_ID)
    async def new_listing(self, interaction: discord.Interaction, button: discord.ui.Button):
        shop = _shop(interaction)
        if shop is None:
            return await _missing(interaction)
        if not await shop.can_sell(interaction.user):
            return await _reply(interaction, "只有觀星者可以上架商品。")
        await interaction.response.send_modal(ListingInfoModal(default_unit=shop.settings.default_unit))


_DYNAMIC_ITEMS = (ShopBuySelect, ShopManageButton, ShopPanelButton, ShopPickSelect, ShopConfirmButton,
                  ShopBatchButton, ShopConfirmOrder, ShopAbort)


class ShopCommands(commands.Cog):
    def __init__(self, bot: commands.Bot, settings: Optional[ShopSettings] = None):
        self.bot = bot
        self.settings = settings or ShopSettings()
        self.shop: Optional[ShopService] = None
        self._task: Optional[asyncio.Task] = None

    async def cog_load(self):
        # 下單要靠交易模組開 thread；COMMAND_MODULES 依字母順序載入，forum_monitor 在前面
        trade_cog = self.bot.get_cog("ForumMonitor")
        if trade_cog is None:
            logger.error("商品上架：交易模組（ForumMonitor）沒有載入，商品上架停用")
            return
        self.shop = ShopService(self.bot, trade=trade_cog.trade, views=DiscordShopViews(self.settings),
                                settings=self.settings)
        trade_cog.trade.add_source_kind(self.shop.source)
        self.bot.add_dynamic_items(*_DYNAMIC_ITEMS)
        self.bot.add_view(GuideView())
        self._task = asyncio.create_task(
            run_due_loop("商品預購截止", self.shop.run_preorder_cutoffs, wait_ready=self.bot.wait_until_ready,
                         max_sleep=self.settings.cutoff_check_max_sleep_seconds),
            name="shop_preorder_cutoffs",
        )

    async def cog_unload(self):
        if self._task is not None:
            self._task.cancel()
            self._task = None
        self.bot.remove_dynamic_items(*_DYNAMIC_ITEMS)


async def setup(bot):
    await bot.add_cog(ShopCommands(bot))
