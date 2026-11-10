"""商品上架：觀星者在商品論壇上架商品、管理品項；需求方挑選下單後，用交易模組開私人交易對話。

架構定位：功能層（`services.community`）。
  - 上層（誰呼叫）：介面 `commands.shop_commands`（置頂上架說明、商品貼文的選單與按鈕、管理面板、表單、排程）。
  - 下層（呼叫誰）：市集資料庫 `services.market_db`（商品、品項的正本）、`shop_listing`（模型、解析、貼文畫面）、
    交易模組 `trade_service`（開單、交易鎖）、商品交易 `shop_trade`（交易進度、付款與交付、通知；開單時交給它）、
    discord（論壇貼文、標籤）。

介面：
  - 權限：`can_sell`、`can_manage`、`check_manager`。置頂說明：`ensure_guide`。
  - 商品：`create_listing`、`load`、`edit_info`、`close_listing`、`redraw`／`refresh_listing`。
  - 品項：`add_variants`、`edit_variant`（回 (商品, 補充說明)）、`delete_variant`、`cutoff_locked`。
  - 下單：`check_pick`、`quote`（→ `Quote`）、`place_order`（確認畫面的價格指紋對不上就丟 `PriceChanged`）。
  - 截止與交貨：`run_cutoffs`（排程）、`delay`、`balance_preview`／`start_balance`、`delivery_preview`／`start_delivery`、
    `schedule_targets`（延期、開始收尾款、開始交貨各自能選哪些品項）。

規則：
  - 正本在資料庫；商品貼文、選單、管理面板都從資料庫畫。先寫資料庫、成功後才改 Discord；
    Discord 改失敗只影響顯示，下一次重畫會補上（`redraw` 失敗只記 log，不讓已經成立的動作看起來失敗）。
  - 改同一篇商品（下單、管理、截止）排隊：商品鎖。要同時拿交易鎖時一律先商品鎖、再交易鎖。
  - 交易中的品項不能改類型；有交易在進行時不能改交付方式；定金品項不能和一次付清的放在同一篇；
    有人下單或已截止的品項，截止時間鎖住，改日期走延期（需求方才會收到通知）。
  - 還有定金或預購的交易沒做完就不能下架（下架後管理面板按不了，延期、開始收尾款都做不了）。
  - 名字一律用伺服器暱稱（`TradeService.member`：先查快取，沒有再向 API 查）。

例外與決策：
  - 截止只看資料庫，不再靠論壇標籤「預購中」找商品；標籤留著給群友篩選。
  - 論壇標籤（預購中、現貨）不另外跑排程：每次重畫貼文時照 `forum_tags` 對一次，不同才改；
    「預購中」在截止那一刻跟著截止排程的重畫拿掉。供應方被拿掉觀星者身份組不會觸發重畫，
    標籤留到那篇下次有變動（不監聽身份組變動：很少發生，下單時本來就會擋並說明）。
  - 改價格只影響之後的新訂單：交易品項記著下單當時的金額。
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, Optional, Protocol, Sequence

import discord

from services.community import trade_progress as tp
from services.community.shop_listing import (
    DELIVERIES,
    INSTOCK_TAG,
    PREORDER_TAG,
    TITLE_LIMIT,
    UNIT_LIMIT,
    Draft,
    Listing,
    ShopError,
    Variant,
    embed_image_name,
    format_cutoff,
    format_date,
    forum_tags,
    listing_from_rows,
    money,
    order_summary,
    parse_cutoff,
    price_signature,
    quote_order,
    render_embed,
)
from services.community import market_transition as transition
from services.community.shop_trade import ListingTrades, Notified, Step
from services.community.trade_service import NOT_READY_TEXT, WRAP_UP_GRACE, OpenedTrade, TradeService
from services.market_db import TradeRow
from sys_settings.paths import APP_ROOT
from sys_settings.shop_settings import ShopSettings
from sys_settings.time_settings import APP_TZ
from utils.background_tasks import spawn
from utils.discord_content import ensure_forum_tags, find_forum_tags, post_to_channel, sanitize_forum_thread_title
from utils.discord_members import check_role
from utils.discord_threads import reopen_thread
from utils.utils import ChannelConfig

logger = logging.getLogger(__name__)

CLOSED_PREFIX = "【已下架】"
#: 截止、延期通知有對話一時取不到時，多久之後再補
NOTICE_RETRY = timedelta(minutes=10)
#: 幣別的範例：擋下來時與欄位說明都用這組（欄位叫「幣別」）
UNIT_EXAMPLES = "NT$、USD$、JPY¥、PY幣"


class PriceChanged(ShopError):
    """確認下單時金額跟確認畫面上的不一樣（供應方剛好改了價格）：要重新顯示讓需求方再確認一次。"""


@dataclass(frozen=True)
class Quote:
    """下單前給需求方看的明細。"""

    listing: Listing
    rows: list[str]
    now_total: int          # 現在要付（定金、一次付清的全額）
    later_total: int        # 到貨後再付（尾款）
    signature: str          # 這些金額的指紋，確認下單時比對
    joins_open_trade: bool  # 會加進跟這位供應方還在進行的交易對話


@dataclass(frozen=True)
class OrderRecord:
    order_event_id: int
    rows: list[str]
    now_total: int
    later_total: int
    #: 加購時跟訂單一起作廢的領收通知（之後拿掉上面的按鈕）；沒有就是 None
    retired_message_id: Optional[int] = None


class ShopViews(Protocol):
    """商品相關的 Discord 元件（commands/shop_commands.py 實作）。"""

    def listing(self, listing: Listing, now: datetime) -> discord.ui.View:
        """商品貼文上的購買選單＋「⚙️ 管理商品（供應方）」。"""

    def guide(self) -> discord.ui.View:
        """置頂上架說明的按鈕。"""

    def progress(self, steps: Sequence[Step]) -> Optional[discord.ui.View]:
        """交易進度上這一步能按的按鈕；沒有就回 None。"""


#: 開始收尾款、開始交貨時沒人下單（還沒截止）：按下去只是提早停收，告訴他暫停販售有可以改回來的做法
_NO_ORDERS_WARNING = "⚠️ 此操作無法復原。若只想暫停販售，請改用「編輯品項」將剩餘數量設為 0，之後可以再改回來。"


class ShopService:
    def __init__(
        self,
        bot: discord.Client,
        *,
        trade: TradeService,
        views: ShopViews,
        settings: Optional[ShopSettings] = None,
        now: Optional[Callable[[], datetime]] = None,
    ):
        self.bot = bot
        self.trade = trade
        self.views = views
        self.settings = settings or ShopSettings()
        self._now = now or (lambda: datetime.now(APP_TZ))
        #: 每篇商品最多一個背景工作在改貼文標題（`_sync_post_later`）；做的時候又有新的要求就記在 _post_again
        self._post_tasks: dict[int, asyncio.Task] = {}
        self._post_again: set[int] = set()
        #: 品項新增或編輯過：叫醒截止的排程重算（不然截止時間改到一小時內會晚提醒）
        self.cutoffs_changed = asyncio.Event()
        self._locks: dict[object, asyncio.Lock] = {}
        #: 商品交易：交易進度、付款與交付；也是交給交易模組的來源種類（cog 載入時登記）
        self.trades = ListingTrades(self)
        self.source = self.trades

    def now(self) -> datetime:
        return self._now()

    def stamp(self) -> str:
        return self._now().isoformat()

    async def db(self):
        return await self.trade.db()

    # ── 權限 ──

    async def can_sell(self, member: discord.Member) -> bool:
        return await check_role(member, self.settings.seller_role)

    async def _check_deposit_ready(self, listing: Listing) -> None:
        if await transition.holds_orders(self.trade, listing):
            raise ShopError(transition.ORDERS_HELD_TEXT)

    async def _selling_owner(self, listing: Listing, guild) -> discord.Member:
        """這篇商品的供應方，還能接新訂單才回傳：人不在伺服器、或被拿掉觀星者身份組就擋下。
        拿掉身份組＝不讓他繼續賣：新訂單（含加購）不接，進行中的照常做完，管理面板照常能用（延期、收尾款、取消）。"""
        owner = await self.trade.member(guild, listing.owner_id)
        if owner is None:
            raise ShopError("供應方已經不在伺服器裡，暫時不能下單。")
        if not await self.can_sell(owner):
            raise ShopError("這篇商品目前不接新訂單。")
        return owner

    def can_manage(self, member: discord.Member, listing: Listing, guild=None) -> bool:
        """供應方本人或管理員（伺服器擁有者、有管理員權限的人）。guild 用商品貼文所在的伺服器。"""
        if member.id == listing.owner_id:
            return True
        guild = guild or getattr(member, "guild", None)
        if guild is not None and member.id == getattr(guild, "owner_id", None):
            return True
        permissions = getattr(member, "guild_permissions", None)
        return bool(permissions and permissions.administrator)

    async def check_manager(self, listing_id: int, member: discord.Member, *, guild=None) -> Listing:
        listing = await self.load(listing_id)
        if guild is None and getattr(member, "guild", None) is None:
            # 群主、管理員要看商品貼文所在的伺服器（互動帶來的成員有 guild，服務自己叫的不一定有）
            guild = getattr(await self.trade.get_thread(listing_id), "guild", None)
        if not self.can_manage(member, listing, guild):
            raise ShopError("只有供應方可以管理這篇商品。")
        return listing

    def _check_ready(self) -> None:
        if not self.trade.ready.is_set():
            raise ShopError(NOT_READY_TEXT)

    async def _load_for_manage(self, listing_id: int, actor: discord.Member) -> Listing:
        self._check_ready()
        listing = await self.check_manager(listing_id, actor)
        if listing.closed:
            raise ShopError("這篇商品已經下架了。")
        return listing

    # ── 上架說明（綁定商品論壇時） ──

    async def ensure_guide(self, forum: discord.ForumChannel) -> str:
        """商品論壇置頂一篇上架說明；已經有就確認它還置頂著、文字是最新的。回傳給管理員看的說明。"""
        guide = await self._find_guide(forum)
        if guide is None:
            image = await self._guide_image()
            message = await post_to_channel(
                forum, embed=self._guide_embed(image[0] if image else None), thread_title=self.settings.guide_title,
                files=[discord.File(io.BytesIO(image[1]), filename=image[0])] if image else None,
                view=self.views.guide())
            guide = message.channel
            await guide.edit(pinned=True)
            note = f"🛒 已發置頂的上架說明：{guide.jump_url}"
        else:
            await reopen_thread(guide)
            if not getattr(getattr(guide, "flags", None), "pinned", False):
                await guide.edit(pinned=True)
            note = f"🛒 置頂的上架說明已經在了：{guide.jump_url}"
            note += await self._refresh_guide(guide)
        # 先把標籤建好，群友才篩得出來
        names = self._tag_names()
        tags = await ensure_forum_tags(forum, names.values())
        missing = [name for name in names.values() if name not in tags]
        if missing:
            note += (f"\n⚠️ 建不了{'、'.join(f'「{name}」' for name in missing)}標籤"
                     "（bot 需要這個論壇的「管理頻道」權限），商品不會掛這些標籤。")
        return note

    async def _refresh_guide(self, guide: discord.Thread) -> str:
        """說明文字、橫幅圖或按鈕改過就更新已置頂的那篇，管理員重綁一次商品論壇即可。

        圖沒換就不傳附件清單（傳了會把貼文上的檔案換掉）。"""
        image = await self._guide_image()
        try:
            starter = await guide.fetch_message(guide.id)  # 論壇第一則訊息 id＝thread id
            have = starter.embeds[0] if starter.embeds else None
            have_image = embed_image_name(have)
            # 圖檔讀不到時沿用貼文上原本的圖，不把它拿掉
            want_image = image[0] if image else have_image
            want = self._guide_embed(want_image)
            have_buttons = [getattr(c, "custom_id", None) for row in getattr(starter, "components", None) or ()
                            for c in getattr(row, "children", None) or ()]
            want_buttons = [getattr(c, "custom_id", None) for c in self.views.guide().children]
            if have is not None and (have.title, have.description, have_image, have_buttons) == (
                    want.title, want.description, want_image, want_buttons):
                return ""
            if image and have_image != image[0]:
                await starter.edit(embed=want, view=self.views.guide(),
                                   attachments=[discord.File(io.BytesIO(image[1]), filename=image[0])])
            else:
                await starter.edit(embed=want, view=self.views.guide())
        except discord.HTTPException:
            logger.error("商品上架：更新上架說明失敗 thread=%s", guide.id, exc_info=True)
            return "\n⚠️ 上架說明沒能更新成最新版，請查看 log。"
        logger.info("商品上架：更新上架說明 thread=%s", guide.id)
        return "（已更新成最新版）"

    async def _guide_image(self) -> Optional[tuple[str, bytes]]:
        """置頂說明的橫幅圖：（貼文上的檔名, 內容）。檔名帶內容的雜湊，換了圖重綁時才認得出要更新。"""
        path = APP_ROOT / self.settings.guide_image
        try:
            data = await asyncio.to_thread(path.read_bytes)
        except OSError:
            logger.warning("商品上架：讀不到上架說明的圖 %s，只發文字", path)
            return None
        return f"guide_{hashlib.sha1(data).hexdigest()[:8]}{path.suffix.lower()}", data

    async def _find_guide(self, forum: discord.ForumChannel) -> Optional[discord.Thread]:
        db = await self.db()

        async def is_guide(thread: discord.Thread) -> bool:
            # 商品貼文也是 bot 發的：有商品紀錄的一定不是置頂說明
            return (thread.owner_id == self.bot.user.id and thread.name == self.settings.guide_title
                    and await db.get_listing(thread.id) is None)

        for thread in list(getattr(forum, "threads", None) or ()):
            if await is_guide(thread):
                return thread
        async for thread in forum.archived_threads(limit=None):
            if await is_guide(thread):
                return thread
        return None

    def _guide_embed(self, image: Optional[str] = None) -> discord.Embed:
        embed = discord.Embed(
            title="上架說明",
            color=discord.Color.gold(),
            description=(
                "**觀星者上架商品**\n"
                "1. 按下方「🛒 上架商品」，填標題、說明、幣別（金額前面的符號，例 NT$）、交付方式（實體或數位），"
                "可以附商品圖（最多 10 張）。金額在加入品項時各自填。\n"
                "2. 到你的商品貼文按「⚙️ 管理商品（供應方）」加入品項：一次一個，或用「批次新增」一次加很多個。\n"
                "　・類型：立即購買；預購（要填截止時間）；定金＋尾款（價格填「定金/尾款」，例 500/1300，"
                "也要填收定金的截止時間）。時間一律寫年份，例：2026/10/20 23:59。\n\n"
                "**需求方怎麼買**\n"
                "在商品貼文的下拉選單只挑自己要的（一次最多 5 種）→ 填數量 → 確認下單，"
                "就會開一個只有你和供應方的私人交易對話。\n\n"
                "**交易流程**\n"
                "交易對話裡的「交易進度」列出每個品項到哪一步：需求方付款後可以按「我已付」，供應方收到錢後按「已收到」；"
                "錢收齊後供應方按「已交付」（實體商品是「已寄出」，需求方收到後按「已收到」）。"
                "有爭議可以按「請群主協助」。"
            ),
        )
        if image:
            # 引用附件：圖顯示在說明裡，論壇列表的縮圖也會用它
            embed.set_image(url=f"attachment://{image}")
        return embed

    # ── 商品 ──

    async def load(self, listing_id: int) -> Listing:
        """從資料庫讀一篇商品（含已下單份數）；沒有就丟 ShopError。"""
        db = await self.db()
        row = await db.get_listing(listing_id)
        if row is None:
            raise ShopError("找不到這篇商品。")
        return listing_from_rows(row, await db.variants(listing_id), await db.taken(listing_id))

    async def create_listing(self, owner: discord.Member, *, title: str, description: str, unit: str,
                             delivery: str = "physical",
                             attachments: Sequence[discord.Attachment] = ()) -> discord.Thread:
        self._check_ready()
        forum = await self._forum()
        if forum is None:
            raise ShopError("商品論壇還沒設定，請管理員到 /server_manager 綁定「商品上架論壇」。")
        if not await self.can_sell(owner):
            raise ShopError("只有觀星者可以上架商品。")
        title, description, unit = self._clean_info(title, description, unit)
        delivery = self._clean_delivery(delivery)
        files = await self._image_files(attachments, forum.guild)
        now = self._now()
        listing = Listing(thread_id=0, owner_id=owner.id, unit=unit, title=title, description=description,
                          image=files[0].filename if files else None, delivery=delivery)
        message = await post_to_channel(
            forum, embed=render_embed(listing, owner.display_name, now, owner_avatar=owner.display_avatar.url),
            files=files,
            thread_title=title, view=self.views.listing(listing, now))
        thread = message.channel
        saved = False
        try:
            db = await self.db()
            async with db.transaction():
                await db.insert_listing(id=thread.id, owner_id=owner.id, title=title, description=description,
                                        unit=unit, delivery=delivery, image=listing.image, now=self.stamp())
            saved = True
        finally:
            if not saved:
                # 資料庫沒有這篇，貼文留著只會有一顆按了沒反應的管理按鈕
                try:
                    await thread.delete()
                except discord.HTTPException:
                    logger.error("商品上架：寫入資料庫失敗後刪貼文也失敗 thread=%s", thread.id, exc_info=True)
        try:
            # 論壇貼文沒人講話就會自動封存，封存中的訊息改不了；拉到最長，少一點解除封存的次數
            await thread.edit(auto_archive_duration=self.settings.listing_auto_archive_minutes)
        except discord.HTTPException:
            logger.warning("商品上架：設定自動封存時間失敗 thread=%s", thread.id, exc_info=True)
        logger.info("商品上架：上架 thread=%s 供應方=%s 交付=%s", thread.id, owner.id, delivery)
        return thread

    def _clean_info(self, title: str, description: str, unit: str) -> tuple[str, str, str]:
        title = (title or "").strip()
        if not title:
            raise ShopError("標題不能空白。")
        if title == self.settings.guide_title:
            # 跟置頂說明同名的話，重綁商品論壇時會被當成置頂說明、整篇蓋掉
            raise ShopError("這個標題是置頂上架說明在用的，請換一個。")
        if len(title) > TITLE_LIMIT:
            raise ShopError(f"標題最多 {TITLE_LIMIT} 個字。")
        unit = (unit or "").strip() or self.settings.default_unit
        # 幣別只是金額前面的符號，金額在各品項各自填；擋數字，免得供應方把金額填在這裡
        if any(ch.isdigit() for ch in unit):
            raise ShopError(f"幣別不能有數字，只填金額前面的符號，例如 {UNIT_EXAMPLES}。"
                            "金額請在加入品項時各自填。")
        if len(unit) > UNIT_LIMIT:
            raise ShopError(f"幣別最多 {UNIT_LIMIT} 個字，例如 {UNIT_EXAMPLES}。")
        return title, (description or "").strip(), unit

    @staticmethod
    def _clean_delivery(delivery: Optional[str]) -> str:
        if delivery not in DELIVERIES:
            raise ShopError("交付方式要選實體或數位。")
        return delivery

    async def _image_files(self, attachments: Sequence[discord.Attachment], guild) -> list[discord.File]:
        if len(attachments) > self.settings.max_images:
            raise ShopError(f"商品圖最多 {self.settings.max_images} 張。")
        # 先檢查大小再下載：圖會整個讀進記憶體，太大的也發不出去
        size_limit = getattr(guild, "filesize_limit", None) or 10 * 1024 * 1024
        for attachment in attachments:
            if not (attachment.content_type or "").startswith("image/"):
                raise ShopError(f"「{attachment.filename}」不是圖片，商品圖只能放圖片。")
            if (attachment.size or 0) > size_limit:
                raise ShopError(f"「{attachment.filename}」太大了，每張最多 {size_limit // (1024 * 1024)} MB。")
        files = []
        for number, attachment in enumerate(attachments, start=1):
            extension = os.path.splitext(attachment.filename)[1].lower() or ".png"
            # 檔名換成固定格式：embed 要用 attachment://檔名 引用第一張
            files.append(await attachment.to_file(filename=f"item_{number}{extension}"))
        return files

    async def redraw(self, listing_id: int, *, files: Optional[list[discord.File]] = None) -> None:
        """照資料庫重畫商品貼文。不傳 files 就不動原本的圖（只傳 embed，圖會留著）。

        封存中的貼文改不了訊息，先解除封存，改完再封存回去（例：已下架的商品被取消還回時）。"""
        listing = await self.load(listing_id)
        thread = await self.trade.get_thread(listing_id)
        if thread is None:
            logger.warning("商品上架：找不到商品貼文 %s，沒有重畫", listing_id)
            return
        was_archived = getattr(thread, "archived", False)
        if not await reopen_thread(thread):
            return
        message = await thread.fetch_message(listing_id)
        now = self._now()
        try:
            owner = await self.trade.member(thread.guild, listing.owner_id, raise_errors=True)
            owner_known = True
        except discord.HTTPException:
            # 沒權限或 Discord 一時出錯：查不到不代表人不在，這次照畫貼文、標籤先不動（不然會被當成不接單拿掉）
            logger.warning("商品上架：重畫時查不到供應方 %s，標籤這次不動 商品=%s", listing.owner_id, listing_id,
                           exc_info=True)
            owner, owner_known = None, False
        if owner is None:
            embed = render_embed(listing, str(listing.owner_id), now)
        else:
            embed = render_embed(listing, owner.display_name, now, owner_avatar=owner.display_avatar.url)
        if files is None:
            await message.edit(embed=embed, view=self.views.listing(listing, now))
        else:
            await message.edit(embed=embed, view=self.views.listing(listing, now), attachments=files)
        if owner_known:
            # 標籤跟下單用同一套檢查：供應方還在、還能賣、付款方式不在設定中（品項本身買不買得到由 forum_tags 看）
            taking_orders = (owner is not None and await self.can_sell(owner)
                             and not await transition.holds_orders(self.trade, listing))
            await self._sync_tags(thread, forum_tags(listing, now, taking_orders=taking_orders))
        if was_archived:
            await thread.edit(archived=True)

    async def refresh_listing(self, listing_id: int) -> None:
        """資料已經寫好、重畫商品貼文；失敗只記 log（之後的重畫會補上）。

        也用來讓購買選單回到未選取：Discord 的選單選過同一組就不會再通知 bot。"""
        try:
            await self.redraw(listing_id)
        except (ShopError, discord.HTTPException):
            logger.warning("商品上架：重畫商品貼文失敗 商品=%s", listing_id, exc_info=True)

    def _tag_names(self) -> dict[str, str]:
        """bot 管的論壇標籤：種類 → 名字（順序就是掛上去的順序）。"""
        return {PREORDER_TAG: self.settings.preorder_tag_name, INSTOCK_TAG: self.settings.instock_tag_name}

    async def _sync_tags(self, thread: discord.Thread, wanted: set[str]) -> None:
        """照這次算的結果掛上或拿掉 bot 管的標籤；別的標籤（管理員手動掛的）不動，跟現在一樣就不改。
        要掛的標籤論壇上還沒有就先建（建不了就不掛）。"""
        forum = getattr(thread, "parent", None)
        if forum is None:
            return
        names = self._tag_names()
        wanted_names = [names[kind] for kind in names if kind in wanted]
        created = await ensure_forum_tags(forum, wanted_names) if wanted_names else {}
        tags = {**find_forum_tags(forum, names.values()), **created}
        ours = {tag.id for tag in tags.values()}
        current = list(thread.applied_tags)
        want = [tag for tag in current if tag.id not in ours] + [tags[name] for name in wanted_names if name in tags]
        if {tag.id for tag in want} != {tag.id for tag in current}:
            await thread.edit(applied_tags=want)

    async def edit_info(self, listing_id: int, actor: discord.Member, *, title: str, description: str, unit: str,
                        delivery: Optional[str] = None,
                        attachments: Sequence[discord.Attachment] = ()) -> Listing:
        title, description, unit = self._clean_info(title, description, unit)
        # 下載圖片在鎖外：下載期間不要擋住這篇的下單
        files = await self._image_files(attachments, getattr(actor, "guild", None)) if attachments else None
        async with self._lock(listing_id):
            listing = await self._load_for_manage(listing_id, actor)
            await transition.check_title(self.trade, listing, title)
            delivery = listing.delivery if delivery is None else self._clean_delivery(delivery)
            trading = [t for t in await self.trade.open_trades_for_source(listing_id) if not t.legacy]
            if delivery != listing.delivery and trading:
                # 交易做到一半換一套按鈕（已寄出、已收到 ↔ 已交付、領收），對話會接不上；
                # 上線前的舊交易沒有交易進度、照舊流程，不受影響
                raise ShopError("有交易在進行時不能改交付方式，等那些交易完成或取消後再改。" + _thread_list(trading))
            if unit != listing.unit:
                # 金額存的是數字、幣別在商品上：已收的錢、說好的尾款會整批換成新幣別顯示；
                # 上線前的舊交易也存了下單金額（完成時的留底照商品幣別寫），一起算
                every = await self.trade.open_trades_for_source(listing_id)
                if every:
                    raise ShopError("有交易在進行時不能改幣別，等那些交易完成或取消後再改。" + _thread_list(every))
            db = await self.db()
            async with db.transaction():
                await db.update_listing(listing_id, now=self.stamp(), title=title, description=description,
                                        unit=unit, delivery=delivery,
                                        image=files[0].filename if files else listing.image)
                if title != listing.title:
                    await db.want_post_sync(listing_id)
            await self._redraw_or_log(listing_id, files=files)
        if title != listing.title:
            self._sync_post_later(listing_id)
        return await self.load(listing_id)

    async def close_listing(self, listing_id: int, actor: discord.Member) -> Listing:
        """下架：不再接單，已成立的交易照常進行。還有定金或預購的交易沒做完就擋：下架後管理面板按不了，
        延期、開始收尾款、開始交貨都做不了，那些交易會卡住。"""
        async with self._lock(listing_id):
            listing = await self._load_for_manage(listing_id, actor)
            pending = [trade for trade, kinds in await self._open_trades_with(listing_id)
                       if kinds & {"deposit", "preorder"} and not trade.legacy]
            if await transition.holds_orders(self.trade, listing):
                # 下架後管理面板按不了，就改不成定金＋尾款，上面的舊交易永遠接不上新流程
                raise ShopError(transition.CLOSE_HELD_TEXT)
            if pending:
                raise ShopError(
                    f"還有 {len(pending)} 筆定金或預購的交易沒做完，現在不能下架（下架後就不能延期、開始收尾款或開始交貨）。"
                    "要停止接單可以等截止，或把品項的剩餘數量改成 0。\n" + _thread_list(pending))
            db = await self.db()
            async with db.transaction():
                await db.update_listing(listing_id, now=self.stamp(), closed=True)
                await db.want_post_sync(listing_id)
            await self._redraw_or_log(listing_id)
        # 資料庫已標成下架，新的下單會被擋下；改名、鎖定只是外觀，放到背景
        self._sync_post_later(listing_id)
        logger.info("商品上架：下架 thread=%s by=%s", listing_id, actor.id)
        return await self.load(listing_id)

    def _sync_post_later(self, listing_id: int) -> None:
        """在背景讓商品貼文的標題（下架時連同鎖定、封存）跟上資料庫。改名每 10 分鐘只能 2 次，撞到時 discord.py
        會睡到限速解除（可能九分多鐘），按鈕的互動不能一直卡在「處理中」；資料庫已經寫好，標題只是外觀。
        每篇最多一個在做：做的時候又改了，做完照資料庫最新的再做一次（不會停在舊的標題）。"""
        if listing_id in self._post_tasks:
            self._post_again.add(listing_id)
            return

        async def run() -> None:
            applied: Optional[str] = None
            try:
                while True:
                    self._post_again.discard(listing_id)
                    applied = await self._sync_post(listing_id, applied)
                    if listing_id not in self._post_again:
                        return
            finally:
                self._post_tasks.pop(listing_id, None)

        self._post_tasks[listing_id] = spawn(run(), name=f"商品貼文改名 {listing_id}")

    async def _sync_post(self, listing_id: int, applied: Optional[str] = None) -> Optional[str]:
        """照資料庫改一次貼文；回傳現在貼文上的標題。applied＝上一次剛改好的標題：剛改完名，快取裡的
        thread 還沒收到更新事件、名字還是舊的，照它比會把「改回原本的標題」當成不用改。"""
        db = await self.db()
        row = await db.get_listing(listing_id)
        if row is None or not row.post_pending:
            return applied
        version = row.post_wanted
        thread = await self.trade.get_thread(listing_id, raise_errors=True)
        name = sanitize_forum_thread_title((CLOSED_PREFIX if row.closed else "") + row.title)
        current = applied if applied is not None else getattr(thread, "name", None)
        try:
            if thread is not None and (current != name or (row.closed and not getattr(thread, "locked", False))):
                # 上架一週以上的貼文多半是封存的（只改首則不算新動靜），封存中改不了名也鎖不了，重畫完又會封存回去：
                # 一律先解封（手上這份不一定看得出剛封存）
                await reopen_thread(thread, force=True)
                if row.closed:
                    await thread.edit(name=name, locked=True, archived=True)
                else:
                    await thread.edit(name=name)
                current = name
        except discord.Forbidden:
            # 沒有權限改：再試也一樣，記下來不再重試（標題只是外觀）
            logger.warning("商品上架：沒有權限改貼文標題 商品=%s", listing_id, exc_info=True)
        except discord.HTTPException:
            logger.warning("商品上架：改貼文標題失敗，排程之後再試 商品=%s", listing_id, exc_info=True)
            return applied
        async with db.transaction():
            await db.post_synced(listing_id, version)
        return current

    async def settle(self) -> None:
        """等背景裡的貼文改名做完（測試用；重啟時做到一半的由截止排程照資料庫補）。"""
        while self._post_tasks:
            await asyncio.gather(*list(self._post_tasks.values()), return_exceptions=True)

    async def refresh_guide(self) -> None:
        """重啟（上線匯入）後把已置頂的上架說明更新成這一版的文字與按鈕；沒有置頂說明就不發新的（綁商品論壇時才發）。"""
        forum = await self._forum()
        if forum is None:
            return
        guide = await self._find_guide(forum)
        if guide is None or not await reopen_thread(guide):
            return
        await self._refresh_guide(guide)

    # ── 品項 ──

    def cutoff_locked(self, variant: Variant) -> bool:
        """截止時間鎖住（編輯品項時不能改，要改走延期）：有人下單了，或已經截止。"""
        return variant.cutoff is not None and (variant.taken > 0 or variant.cutoff_passed(self._now()))

    @staticmethod
    def _check_mix(kinds: Sequence[str]) -> None:
        if "deposit" in kinds and any(kind != "deposit" for kind in kinds):
            raise ShopError("定金＋尾款的品項不能和一次付清的品項放在同一篇商品：一起買的現貨會被拖到尾款收完才完成。"
                            "有現貨請另開一篇" + (
                                "；上線前的【定金】商品要整篇改成定金＋尾款，請按管理面板的「💰 改成定金＋尾款」"
                                "（有上線後開的交易在進行時要先完成或取消）。" if transition.enabled() else "。"))

    async def add_variants(self, listing_id: int, actor: discord.Member, drafts: Sequence[Draft]) -> Listing:
        async with self._lock(listing_id):
            listing = await self._load_for_manage(listing_id, actor)
            if len(listing.variants) + len(drafts) > self.settings.max_variants:
                raise ShopError(f"一篇商品最多 {self.settings.max_variants} 個品項，"
                                f"目前有 {len(listing.variants)} 個。")
            self._check_mix([v.kind for v in listing.variants] + [d.kind for d in drafts])
            db = await self.db()
            async with db.transaction():
                for draft in drafts:
                    await db.insert_variant(listing_id, name=draft.name, kind=draft.kind, price=draft.price,
                                            balance=draft.balance, limit_qty=draft.limit,
                                            cutoff=draft.cutoff.isoformat() if draft.cutoff else None,
                                            now=self.stamp())
            await self._redraw_or_log(listing_id)
        self.cutoffs_changed.set()
        return await self.load(listing_id)

    async def edit_variant(self, listing_id: int, actor: discord.Member, key: int,
                           draft: Draft) -> tuple[Listing, str]:
        """編輯品項。draft.limit 是「剩餘數量」（還要賣幾個，None＝不限量）：
        存的上限＝已下單＋剩餘，補貨 5 個就填 5，不用自己算。回傳 (商品, 給供應方的補充說明)。"""
        async with self._lock(listing_id):
            listing = await self._load_for_manage(listing_id, actor)
            variant = listing.variant(key)
            if variant is None:
                raise ShopError("找不到這個品項，可能已經被刪除。")
            trades = await self._open_trades_for_variant(listing_id, key)
            # 上線前的舊交易沒有交易進度、照舊流程，改類型不影響它們
            trading = [trade for trade, _ in trades if not trade.legacy]
            if draft.kind != variant.kind and trading:
                raise ShopError(f"「{variant.name}」還有 {len(trading)} 筆交易在進行，交易中不能改類型。"
                                f"要改請先取消這些交易：{_thread_list(trading)}\n名稱、數量可以照常改。")
            self._check_mix([v.kind for v in listing.variants if v.key != key] + [draft.kind])
            fields = dict(name=draft.name, kind=draft.kind, price=draft.price, balance=draft.balance,
                          limit_qty=None if draft.limit is None else variant.taken + draft.limit)
            if draft.kind == "instant":
                fields.update(cutoff=None, cutoff_done=False, expected_at=None)
            elif self.cutoff_locked(variant):
                pass  # 截止時間鎖住：照原本的（延期才會通知需求方）
            elif draft.cutoff is not None:
                fields.update(cutoff=draft.cutoff.isoformat(), cutoff_done=False)
            db = await self.db()
            async with db.transaction():
                await db.update_variant(listing_id, key, now=self.stamp(), **fields)
            await self._redraw_or_log(listing_id)
        self.cutoffs_changed.set()
        note = ""
        if draft.kind == "deposit" and draft.kind != variant.kind:
            # 改成定金＋尾款：這篇上的舊交易照新的類型接上新流程、補發交易進度（例：只有一個品項的【定金】舊商品）
            adopted = await self.adopt_legacy_on(listing_id)
            if adopted:
                note = f"上線前的 {adopted} 筆交易已接上新流程（定金照下單時的金額、尾款照這次填的），補發了交易進度。"
        kept = [(trade, qty) for trade, qty in trades if not trade.legacy]
        if kept and (draft.price, draft.balance) != (variant.price, variant.balance):
            note += f"已下單的 {sum(qty for _, qty in kept)} 份照原本的金額。"
        return await self.load(listing_id), note

    async def delete_variant(self, listing_id: int, actor: discord.Member, key: int) -> Listing:
        async with self._lock(listing_id):
            listing = await self._load_for_manage(listing_id, actor)
            variant = listing.variant(key)
            if variant is None:
                raise ShopError("找不到這個品項，可能已經被刪除。")
            trades = await self._open_trades_for_variant(listing_id, key)
            if trades:
                raise ShopError(f"還有進行中的交易買了「{variant.name}」，請先完成或取消那些交易："
                                + _thread_list([t for t, _ in trades]))
            db = await self.db()
            async with db.transaction():
                await db.update_variant(listing_id, key, now=self.stamp(), deleted=True)
            await self._redraw_or_log(listing_id)
        return await self.load(listing_id)

    async def _open_trades_with(self, listing_id: int) -> list[tuple[TradeRow, set[str]]]:
        """這篇商品還在進行的交易，各自買了哪些類型的品項（取消還回的不算）。"""
        db = await self.db()
        found = []
        for trade in await self.trade.open_trades_for_source(listing_id):
            if trade.source_kind != "listing":
                continue
            kinds = {item.kind for item in await db.items(trade.id) if item.qty > item.returned}
            found.append((trade, kinds))
        return found

    async def _open_trades_for_variant(self, listing_id: int, key: int) -> list[tuple[TradeRow, int]]:
        """還在進行、買了這個品項的交易與份數。"""
        db = await self.db()
        found = []
        for trade in await self.trade.open_trades_for_source(listing_id):
            if trade.source_kind != "listing":
                continue
            qty = sum(item.qty - item.returned for item in await db.items(trade.id) if item.variant_key == key)
            if qty > 0:
                found.append((trade, qty))
        return found

    async def _redraw_or_log(self, listing_id: int, *, files=None) -> None:
        """資料庫已經寫好；重畫失敗只影響顯示，記 log 就好（下一次重畫會補上）。"""
        try:
            await self.redraw(listing_id, files=files)
        except (ShopError, discord.HTTPException):
            logger.error("商品上架：重畫商品貼文失敗 商品=%s", listing_id, exc_info=True)

    # ── 購買 ──

    async def check_pick(self, listing_id: int, buyer: discord.Member, keys: Sequence[int]) -> list[Variant]:
        """需求方在下拉選完：檢查這些品項現在能不能買，回傳要填數量的品項。真正下單時會在鎖裡再檢查一次。"""
        self._check_ready()
        listing = await self.load(listing_id)
        self._check_buyer(buyer, listing)
        if len(keys) > self.settings.max_pick:
            raise ShopError(f"一次最多挑 {self.settings.max_pick} 種。")
        lines = quote_order(listing, {key: 1 for key in keys}, self._now())
        return [variant for variant, _ in lines]

    async def quote(self, listing_id: int, buyer: discord.Member, picks: dict[int, int]) -> Quote:
        """下單前給需求方看的明細：現在要付多少、到貨後還要付多少，分開寫。"""
        self._check_ready()
        listing = await self.load(listing_id)
        self._check_buyer(buyer, listing)
        # 在確認畫面前就擋：不然需求方看完明細、按了確認才被告知不接單
        guild = getattr(buyer, "guild", None) or getattr(await self.trade.get_thread(listing_id), "guild", None)
        await self._selling_owner(listing, guild)
        await self._check_deposit_ready(listing)
        lines = quote_order(listing, picks, self._now())
        rows, now_total, later_total = order_summary(lines, listing.unit)
        # 上線前的舊交易不會被沿用（新訂單另開對話），不能寫成「會加進還在進行的交易對話」
        joins = any(not trade.legacy for trade in await (await self.db()).trades(
            source_id=listing_id, requester_id=buyer.id, supplier_id=listing.owner_id, status="open"))
        return Quote(listing, rows, now_total, later_total, price_signature(lines, listing.unit), joins)

    async def place_order(self, listing_id: int, buyer: discord.Member, picks: dict[int, int],
                          signature: Optional[str] = None) -> OpenedTrade:
        """下單：在同一個資料庫交易裡記這次下單的品項（下單當時的金額）與事件，再開（或沿用）交易對話。

        signature 是確認畫面上的價格指紋：對不上就丟 PriceChanged（供應方剛好改了價格，需求方要看過新的金額）。"""
        self._check_ready()
        # 整段在商品鎖裡：檢查剩餘到寫進資料庫之間，不能有別的下單或管理插進來
        async with self._lock(listing_id):
            listing = await self.load(listing_id)
            self._check_buyer(buyer, listing)
            lines = quote_order(listing, picks, self._now())
            if signature is not None and price_signature(lines, listing.unit) != signature:
                raise PriceChanged("價格剛剛改過了，請看過新的金額再確認一次。")
            thread = await self.trade.get_thread(listing_id)
            if thread is None:
                raise ShopError("找不到這篇商品。")
            owner = await self._selling_owner(listing, thread.guild)
            await self._check_deposit_ready(listing)
            rows, now_total, later_total = order_summary(lines, listing.unit)

            async def record(db, trade_id: int, created: bool) -> OrderRecord:
                taken = await db.taken(listing_id)
                for variant, qty in lines:
                    left = None if variant.limit is None else variant.limit - taken.get(variant.key, 0)
                    if left is not None and qty > left:
                        raise ShopError(f"「{variant.name}」只剩 {max(left, 0)} 個。")
                # 加購：原本的領收通知跟訂單在同一個資料庫交易裡作廢，加購的東西才不會跟著舊通知被自動領收
                retired = None if created else await self.trade.supersede_receipt_tx(db, trade_id)
                order_id = await db.add_event(trade_id, tp.ORDER, now=self.stamp(), items=picks,
                                              amount=now_total, actor_id=buyer.id)
                await db.insert_items(trade_id, order_id, [
                    dict(variant_key=v.key, name=v.name, kind=v.kind, qty=qty, unit_price=v.price,
                         unit_balance=v.balance) for v, qty in lines])
                return OrderRecord(order_id, rows, now_total, later_total, retired)

            async def after(trade_thread, trade, recorded: OrderRecord, created: bool) -> None:
                await self.trades.after_order(trade_thread, trade, listing, recorded, created)

            opened = await self.trade.open_trade(thread, buyer, owner, kind=self.trades, record=record, after=after)
            if opened is None:
                raise ShopError("目前無法開啟交易，請通知管理員。")  # 原因（購物車頻道沒設定）交易模組已寫進 log
            await self._redraw_or_log(listing_id)
        logger.info("商品上架：下單 商品=%s 需求方=%s 內容=%s thread=%s", listing_id, buyer.id, picks, opened.thread.id)
        return opened

    def _check_buyer(self, buyer: discord.Member, listing: Listing) -> None:
        if buyer.id == listing.owner_id:
            raise ShopError("不能買自己上架的商品。")

    # ── 截止（utils.due_loop 每次醒來呼叫）、延期、開始交貨、開始收尾款 ──

    async def run_cutoffs(self, now: datetime) -> Optional[datetime]:
        """處理到期的截止：一次付清的預購停止下單、@ 雙方可以開始交貨；定金只停收定金。回傳下一個截止時間。

        截止、開始交貨、延期、開始收尾款都是先寫資料庫再逐一通知；做到一半重啟時，這裡把還沒通知的對話補發
        （每個對話通知過會記一筆，不會重複 @）。"""
        if not self.trade.ready.is_set():
            return now + timedelta(minutes=1)  # 上線匯入還沒做完：一分鐘後再看
        db = await self.db()
        next_due: Optional[datetime] = None
        try:
            next_due = await self._delete_orphan_posts(now)
        except Exception:  # 邊界：排程的一步，清不掉下一輪再試，不影響截止
            logger.error("商品上架：清沒上架成功的貼文失敗", exc_info=True)
        for row in await db.listings():
            if row.post_pending:
                # 改標題、下架時貼文還沒改好（撞到限速、做到一半重啟）：照資料庫補
                self._sync_post_later(row.id)
        await transition.adopt_ready(self)
        for row in await db.listings():
            for variant in await db.variants(row.id):
                try:
                    if variant.balance_started_at is not None:
                        await self._resume_balance(row.id, variant.key)
                    if variant.cutoff_done and not variant.cutoff_noticed and not variant.deleted:
                        await self._announce_cutoff(row.id, variant.key)
                    if variant.delays > variant.delays_noticed and not variant.deleted:
                        await self._resume_delay(row.id, variant.key)
                    if variant.cutoff is not None and not variant.cutoff_done:
                        cutoff = datetime.fromisoformat(variant.cutoff)
                        if cutoff > now:
                            next_due = cutoff if next_due is None else min(next_due, cutoff)
                        else:
                            await self._process_cutoff(row.id, variant.key, now)
                    after = await db.get_variant(row.id, variant.key)
                    if after is not None and not after.deleted and (
                            (after.cutoff_done and not after.cutoff_noticed) or after.delays > after.delays_noticed):
                        # 有對話一時取不到、還沒通知完：過一陣子再補（不然要等到下一個截止才會醒來）
                        retry = now + NOTICE_RETRY
                        next_due = retry if next_due is None else min(next_due, retry)
                except Exception:  # 邊界：排程的一個品項，壞了不影響其他品項，下一輪再試
                    logger.error("商品上架：處理截止失敗 商品=%s 品項=%s", row.id, variant.key, exc_info=True)
        return next_due

    async def _process_cutoff(self, listing_id: int, key: int, now: datetime) -> Optional[int]:
        """到時間的截止：停止下單、通知。回傳通知了幾個對話；還沒到或已經截止過回 None。"""
        async with self._lock(listing_id):
            listing = await self.load(listing_id)
            variant = listing.variant(key)
            if variant is None or variant.cutoff is None or variant.cutoff_done or variant.cutoff > now:
                return None
            # 先停止下單（寫資料庫），再逐一通知；通知做到一半重啟，排程照 cutoff_noticed 補發
            db = await self.db()
            async with db.transaction():
                await db.update_variant(listing_id, key, now=self.stamp(), cutoff_done=True)
            await self._redraw_or_log(listing_id)
        count = await self._announce_cutoff(listing_id, key)
        logger.info("商品上架：截止 商品=%s 品項=%s 類型=%s", listing_id, key, variant.kind)
        return count

    async def _delete_orphan_posts(self, now: datetime) -> Optional[datetime]:
        """上架做到一半中斷（貼文發了、資料庫還沒寫就停機）留下的貼文：沒有紀錄，誰都管理不了。
        跟上架寫資料庫失敗時一樣刪掉。只看還在活躍清單裡、bot 發的、匯入之後發的、發了一陣子的。
        回傳最早一篇還太新、要再來看的時刻。"""
        forum = await self._forum()
        since = self.trade.orphans_after
        if forum is None or since is None:
            return None
        db = await self.db()
        later: Optional[datetime] = None
        for thread in list(getattr(forum, "threads", None) or ()):
            created = discord.utils.snowflake_time(thread.id)
            if (getattr(thread, "owner_id", None) != getattr(self.bot.user, "id", None)
                    or thread.name == self.settings.guide_title or created < since
                    or await db.get_listing(thread.id) is not None):
                continue
            if created + WRAP_UP_GRACE > now:
                later = min(filter(None, (later, created + WRAP_UP_GRACE)))
                continue
            logger.warning("商品上架：刪掉沒上架成功的貼文 thread=%s 標題=%s", thread.id, thread.name)
            try:
                await thread.delete()
            except discord.HTTPException:
                logger.warning("商品上架：刪沒上架成功的貼文失敗 thread=%s", thread.id, exc_info=True)
        return later

    async def _announce_cutoff(self, listing_id: int, key: int, *, early: bool = False) -> int:
        """截止（或開始交貨）之後的通知：一次付清的預購 @ 雙方可以開始交貨；定金重畫交易進度。
        每個對話都通知到才記 cutoff_noticed（有對話一時取不到，截止排程之後補）。回傳這次通知了幾個對話。"""
        async with self._lock(listing_id):
            listing = await self.load(listing_id)
            variant = listing.variant(key)
            if variant is None:
                return 0
            if variant.preorder:
                # 截止後延期、又按了開始交貨（記了 delivery_started_at）：這次是貨提早到。只是預計交貨日過了不算
                # （截止通知還沒補完、日子就過了的，照樣補發截止通知）。每次開始交貨之間一定隔著一次延期，
                # 記號帶延期次數，第二次開始交貨才不會被當成已經通知過
                arrived = variant.cutoff_done and variant.delivery_started
                if arrived:
                    result = await self.trades.announce_ready(listing, variant, how="arrived",
                                                              reference=f"{key}:start:{variant.delays}")
                else:
                    result = await self.trades.announce_ready(listing, variant, how="early" if early else "cutoff",
                                                              reference=str(key))
            elif variant.deposit:
                result = await self.trades.mark_deposit_closed(listing, variant)
            else:
                result = Notified(0)
            if not result.retry:
                db = await self.db()
                async with db.transaction():
                    await db.update_variant(listing_id, key, now=self.stamp(), cutoff_noticed=True)
            return result.count

    async def _resume_delay(self, listing_id: int, key: int) -> None:
        """延期寫進資料庫後、通知發到一半重啟：補發（原因沒記下來，補發的不寫原因）。"""
        async with self._lock(listing_id):
            listing = await self.load(listing_id)
            variant = listing.variant(key)
            row = await (await self.db()).get_variant(listing_id, key)
            if variant is None or row is None or row.delays <= row.delays_noticed:
                return
            if variant.delivery_started or variant.balance_started or (variant.cutoff_done and variant.expected_at is None):
                # 延期通知還沒補完，供應方就按了開始交貨或開始收尾款、或截止前延的那個截止已經到了：
                # 之後那則通知已經講了最新的，延期的不補（內容過期了）
                db = await self.db()
                async with db.transaction():
                    await db.update_variant(listing_id, key, now=self.stamp(), delays_noticed=row.delays)
                return
            what, shown = self._delay_text(variant)
            result = await self.trades.announce_delay(listing, variant, what=what, shown=shown, number=row.delays,
                                                      reason="")
            if not result.retry:
                db = await self.db()
                async with db.transaction():
                    await db.update_variant(listing_id, key, now=self.stamp(), delays_noticed=row.delays)

    @staticmethod
    def _delay_text(variant: Variant) -> tuple[str, str]:
        """延期之後要講的是哪個日期：已截止才延期的是預計交貨（定金是預計到貨）日，不然是截止。"""
        if variant.expected_at is not None:
            return ("預計到貨" if variant.deposit else "預計交貨"), format_date(variant.expected_at)
        return ("收定金截止" if variant.deposit else "預購截止"), format_cutoff(variant.cutoff)

    async def schedule_targets(self, listing_id: int, actor: discord.Member, action: str) -> list[Variant]:
        """管理面板上「延期」「開始收尾款」「開始交貨」各自能選的品項。"""
        listing = await self._load_for_manage(listing_id, actor)
        if action == "delay":
            return [v for v in listing.variants if v.cutoff is not None and not v.balance_started]
        if action == "balance":
            return [v for v in listing.variants if v.deposit and not v.balance_started]
        if action == "deliver":
            return [v for v in listing.variants if self._can_start_delivery(v)]
        return []

    async def delay(self, listing_id: int, actor: discord.Member, key: int, date_text: str, reason: str) -> str:
        """延期：還沒截止就把截止往後（收單跟著延長）；已經截止就只設預計交貨（定金是預計到貨）日，不重新開放下單。
        每個買了這個品項的交易對話 @ 需求方，寫第幾次延期與原因。只能往後。"""
        moment = parse_cutoff(date_text)
        reason = (reason or "").strip()[:200]
        now = self._now()
        # 截止時間已經到了、排程還沒處理（剛重啟、排程還在睡）：先照時間截止，延期才接在截止後面，
        # 不然截止通知會被當成延期後的「貨提早到」
        await self._process_cutoff(listing_id, key, now)
        async with self._lock(listing_id):
            listing = await self._load_for_manage(listing_id, actor)
            variant = listing.variant(key)
            if variant is None or variant.cutoff is None or variant.balance_started:
                raise ShopError("這個品項現在不能延期。")
            if moment > now + timedelta(days=round(365.25 * 5)):
                raise ShopError("日期太遠了，請檢查年份。")
            if not variant.cutoff_passed(now):
                if moment <= variant.cutoff:
                    raise ShopError(f"延期只能往後：新的時間要晚於原本的截止 {format_cutoff(variant.cutoff)}。"
                                    "要提早請用「開始交貨」或「開始收尾款」。")
                fields = dict(cutoff=moment.isoformat())
                what = "收定金截止" if variant.deposit else "預購截止"
                shown = format_cutoff(moment)
            else:
                base = variant.expected_at or variant.cutoff
                if moment <= base:
                    raise ShopError(f"延期只能往後：新的日期要晚於 {format_date(base)}。")
                if moment <= now:
                    raise ShopError("新的日期已經過了，請填之後的日期（年份也檢查一下）。")
                # 按過開始交貨又延期＝貨其實還沒到：清掉開始交貨的記號
                fields = dict(expected_at=moment.isoformat(), delivery_started_at=None)
                what = "預計到貨" if variant.deposit else "預計交貨"
                shown = format_date(moment)
            number = variant.delays + 1
            db = await self.db()
            async with db.transaction():
                await db.update_variant(listing_id, key, now=self.stamp(), delays=number, **fields)
            result = await self.trades.announce_delay(listing, variant, what=what, shown=shown, number=number,
                                                      reason=reason)
            if not result.retry:
                # 有對話一時取不到就先不記：截止排程照 delays_noticed 補發（補發的不寫原因）
                async with db.transaction():
                    await db.update_variant(listing_id, key, now=self.stamp(), delays_noticed=number)
            await self._redraw_or_log(listing_id)
        self.cutoffs_changed.set()
        later = "，有幾個對話一時連不上，稍後會補發" if result.retry else ""
        return (f"已把「{variant.name}」的{what}延到 {shown}（第 {number} 次延期），"
                f"通知了 {result.count} 個交易對話{later}。")

    async def adopt_legacy_on(self, listing_id: int) -> int:
        """這篇商品上還開著的上線前舊交易，照品項現在的類型接上新流程（補發交易進度、換開單說明）。回傳轉了幾筆。
        一筆出錯不影響其他筆（做到一半中斷的，補發由等待提醒的排程照 adopted 那筆補）。"""
        listing = await self.load(listing_id)
        adopted = 0
        for trade in await self.trade.open_trades_for_source(listing_id):
            if not trade.legacy:
                continue
            try:
                adopted += await self.trades.adopt_legacy(trade.id, listing)
            except Exception:  # 邊界：一筆舊交易，壞了下一輪再試
                logger.error("商品上架：舊交易接上新流程失敗 thread=%s", trade.id, exc_info=True)
        return adopted

    async def delivery_preview(self, listing_id: int, actor: discord.Member, key: int) -> str:
        """「⏩ 開始交貨」的確認畫面：會發生什麼、通知幾個對話，最後一行講收不回（停止下單、通知馬上發出去）。"""
        listing = await self._load_for_manage(listing_id, actor)
        variant = self._schedule_variant(listing, key, "deliver")
        count = len(await self._open_trades_for_variant(listing_id, key))
        lines = [f"**⏩ 開始交貨「{discord.utils.escape_markdown(variant.name)}」**"]
        if not count:
            lines.append("・目前沒有人下單，不會發送任何通知")
        if variant.cutoff_done:
            was = f"由 {format_date(variant.expected_at)} " if variant.expected_at else ""
            lines.append(f"・已截止，不會重新開放下單；預計交貨日{was}改為今天")
        else:
            was = f"（原訂 {format_cutoff(variant.cutoff)} 截止）" if variant.cutoff else ""
            lines.append(f"・立即停止下單{was}")
        if count:
            lines.append(f"・將通知 {count} 個交易對話可以開始交貨")
            warning = ("⚠️ 此操作無法復原：送出後會立即通知雙方" + ("" if variant.cutoff_done else "，此品項也不會再開放下單")
                       + "。請確認貨品已到再執行。")
        else:
            warning = _NO_ORDERS_WARNING if not variant.cutoff_done else "⚠️ 此操作無法復原。"
        return "\n".join(lines + ["", warning])

    async def start_delivery(self, listing_id: int, actor: discord.Member, key: int) -> str:
        """一次付清的預購提早開始交貨：還沒截止就現在截止、停止下單；截止後延期過的就把預計交貨日改成現在。
        都先寫資料庫再通知（做到一半重啟由排程補發）。"""
        # 截止時間已經到了、排程還沒處理：照時間截止（那則通知就是「可以開始交貨」），不再另發提早開始
        await self._load_for_manage(listing_id, actor)
        cut = await self._process_cutoff(listing_id, key, self._now())
        if cut is not None:
            variant = (await self.load(listing_id)).variant(key)
            if not self._can_start_delivery(variant):
                return f"「{variant.name}」剛好到了截止時間：已經停止下單，通知了 {cut} 個交易對話可以開始交貨。"
        async with self._lock(listing_id):
            listing = await self._load_for_manage(listing_id, actor)
            variant = self._schedule_variant(listing, key, "deliver")
            after_cutoff = variant.cutoff_done
            db = await self.db()
            async with db.transaction():
                if after_cutoff:
                    # 已截止、延期設了預計交貨日：貨提早到，預計交貨日改成現在（貼文寫今天、催交貨的提醒從這一刻算）；
                    # 通知做到一半重啟，排程照 cutoff_noticed 補發
                    await db.update_variant(listing_id, key, now=self.stamp(), expected_at=self.stamp(),
                                            delivery_started_at=self.stamp(), cutoff_noticed=False)
                else:
                    # 現在就截止：貼文上的截止時間、催交貨的提醒都從這一刻算
                    await db.update_variant(listing_id, key, now=self.stamp(), cutoff=self.stamp(),
                                            cutoff_done=True, cutoff_noticed=False)
            await self._redraw_or_log(listing_id)
        count = await self._announce_cutoff(listing_id, key, early=True)
        self.cutoffs_changed.set()
        logger.info("商品上架：開始交貨 商品=%s 品項=%s by=%s", listing_id, key, actor.id)
        done = "現在可以交貨" if after_cutoff else "停止下單"
        return f"已開始交貨「{variant.name}」：{done}，通知了 {count} 個交易對話。"

    async def balance_preview(self, listing_id: int, actor: discord.Member, key: int) -> str:
        """「📦 開始收尾款」的確認畫面：每份尾款、通知幾個對話，最後一行講收不回（停收定金、不能再延期、通知馬上發出去）。"""
        listing = await self._load_for_manage(listing_id, actor)
        variant = self._schedule_variant(listing, key, "balance")
        plan = await self.trades.balance_plan(listing_id, key)
        lines = [f"**📦 開始收「{discord.utils.escape_markdown(variant.name)}」的尾款**"]
        if plan:
            units = sorted({unit for row in plan for unit in row.units})
            if len(units) > 5:
                # 收定金期間改過很多次尾款：全列會超過一則的上限，只寫範圍
                each = f"{money(listing.unit, units[0])}～{money(listing.unit, units[-1])}，共 {len(units)} 種"
            else:
                each = "、".join(money(listing.unit, unit) for unit in units)
            lines.append(f"每份尾款 {each}（依下單時約定的金額）")
        else:
            lines.append("・目前沒有人下單，不會發送任何通知")
        cut = variant.cutoff_passed(self._now())
        until = format_cutoff(variant.cutoff) if variant.cutoff else None
        if not cut:
            lines.append("・立即停收定金，不再接受下單" + (f"（原訂收至 {until}）" if until else ""))
        else:
            lines.append(f"・收定金已於 {until} 截止" if until else "・收定金已截止")
        if plan:
            lines.append(f"・將通知 {len(plan)} 個交易對話的需求方付尾款，共 {sum(row.qty for row in plan)} 份")
            unconfirmed = sum(row.unconfirmed for row in plan)
            if unconfirmed:
                lines.append(f"・其中 {unconfirmed} 份尚未確認收到定金，該對話會先請你確認")
            warning = "⚠️ 此操作無法復原：送出後會立即通知需求方付尾款，此品項也無法再延期收定金。請確認貨品已到再執行。"
        else:
            warning = _NO_ORDERS_WARNING if not cut else "⚠️ 此操作無法復原。"
        return "\n".join(lines + ["", warning])

    async def start_balance(self, listing_id: int, actor: discord.Member, key: int) -> str:
        """貨到了：這個品項停收定金，在每個買了它的交易對話照下單時說好的金額請款。

        先在資料庫記下「開始收尾款」，再逐一通知、每個對話記一筆請款；做到一半重啟，截止排程會補發沒發的。"""
        async with self._lock(listing_id):
            listing = await self._load_for_manage(listing_id, actor)
            variant = self._schedule_variant(listing, key, "balance")
            db = await self.db()
            async with db.transaction():
                # 停收定金；截止的通知不用另外發（每個對話接著就收到請款）
                await db.update_variant(listing_id, key, now=self.stamp(), balance_started_at=self.stamp(),
                                        cutoff_done=True, cutoff_noticed=True)
            done = await self.trades.request_balances(listing, key)
            await self._redraw_or_log(listing_id)
        logger.info("商品上架：開始收尾款 商品=%s 品項=%s by=%s 對話=%s", listing_id, key, actor.id, len(done))
        text = (f"已通知 {len(done)} 個交易對話付尾款：{variant.name} 共 {sum(row.qty for row in done)} 份、"
                f"{money(listing.unit, sum(row.amount for row in done))}。")
        unconfirmed = sum(row.unconfirmed for row in done)
        if unconfirmed:
            text += f"其中 {unconfirmed} 份待你確認定金。"
        return text

    async def _resume_balance(self, listing_id: int, key: int) -> None:
        """開始收尾款做到一半重啟：補發還沒通知的交易對話（已經請過款的不會重發）。"""
        if not await self.trades.balance_plan(listing_id, key):
            return
        async with self._lock(listing_id):
            listing = await self.load(listing_id)
            await self.trades.request_balances(listing, key)

    def _can_start_delivery(self, variant: Variant) -> bool:
        """一次付清的預購：還沒截止，或截止後延期設了還沒到的預計交貨日（貨提早到）。"""
        if not variant.preorder:
            return False
        return not variant.cutoff_done or (variant.expected_at is not None and variant.expected_at > self._now())

    def _schedule_variant(self, listing: Listing, key: int, action: str) -> Variant:
        variant = listing.variant(key)
        if action == "balance" and (variant is None or not variant.deposit or variant.balance_started):
            raise ShopError("這個品項現在不能開始收尾款。")
        if action == "deliver" and (variant is None or not self._can_start_delivery(variant)):
            raise ShopError("這個品項現在不能開始交貨。")
        return variant

    # ── 內部 ──

    def _lock(self, key: object) -> asyncio.Lock:
        return self._locks.setdefault(key, asyncio.Lock())

    def lock(self, listing_id: int) -> asyncio.Lock:
        """商品鎖（商品交易那邊取消後重畫、匯入時用）。拿著交易鎖時不要再拿它。"""
        return self._lock(listing_id)

    async def _forum_id(self) -> Optional[int]:
        # 每次重讀（有 5 分鐘快取）：頻道是使用者在 /server_manager 綁的，bot 不重啟也可能改
        return await ChannelConfig.get_configured_id(self.settings.forum_channel_key, caller="shop")

    async def _forum(self):
        forum_id = await self._forum_id()
        return self.bot.get_channel(forum_id) if forum_id is not None else None

    async def guild(self) -> Optional[discord.Guild]:
        """市集所在的伺服器（商品論壇的，沒綁就用購物車的）：組連結、查名字都用它。"""
        forum = await self._forum()
        if forum is not None:
            return forum.guild
        cart = await self.trade._channel(self.trade.settings.cart_channel_key)
        return getattr(cart, "guild", None)


#: 擋下操作時列出的交易對話最多幾個（每個連結約 23 字；全列的話交易一多，訊息超過上限、面板就卡住）
_THREAD_LIST_MAX = 15


def _thread_list(trades: Sequence[TradeRow]) -> str:
    shown = " ".join(f"<#{trade.id}>" for trade in trades[:_THREAD_LIST_MAX])
    rest = len(trades) - _THREAD_LIST_MAX
    return shown + (f" 等 {len(trades)} 筆" if rest > 0 else "")
