"""商品上架：觀星者在商品論壇上架商品，買家挑選下單後，用交易模組開私人交易 thread。

決定（使用者 2026-10-03，交接文件 TR-Q6～Q24）：
  - 入口是商品論壇置頂「上架說明」裡的「上架商品」按鈕，只有觀星者能按；bot 代發商品貼文。
  - 一篇商品放同一系列的多個品項；買家用下拉只挑自己要的，一次最多 5 種，填數量、確認後下單。
  - 下單就預留數量，取消時還回去；一篇商品可以賣給很多人，每位買家一個交易 thread、加購沿用。
  - 預購有截止時間：截止前可下單；截止時在含這個品項、還沒完成的交易 thread @ 雙方提醒交付。
  - 不加資料表：商品資料存在商品貼文上（見 shop_listing），預購用論壇標籤「預購中」找。

名字一律用伺服器暱稱（`TradeService.member`：先查快取，沒有再向 API 查）。
按鈕與選單長什麼樣子屬於 Discord 介面，由 commands/shop_commands.py 以 `views` 交進來。
"""
from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import replace
from datetime import datetime
from typing import Callable, Optional, Protocol, Sequence

import discord

from services.community.shop_listing import (
    Draft,
    Listing,
    ShopError,
    TITLE_LIMIT,
    UNIT_LIMIT,
    Variant,
    apply_order,
    format_cutoff,
    listing_from_message,
    money,
    order_summary,
    order_total,
    orders_on,
    quote_order,
    release_order,
    render_embed,
    unit_fits,
)
from services.community.trade_service import OpenedTrade, TradeNote, TradeRef, TradeService, mentions_to_names
from sys_settings.shop_settings import ShopSettings
from sys_settings.time_settings import APP_TZ
from utils.discord_content import post_to_channel
from utils.utils import ChannelConfig, check_role

logger = logging.getLogger(__name__)

CLOSED_PREFIX = "【已下架】"
#: 幣別的範例：擋下來時與欄位說明都用這組（使用者 2026-10-03 指定 NT$、USD$、JPY¥；欄位名稱同日改叫「幣別」）
UNIT_EXAMPLES = "NT$、USD$、JPY¥、PY幣"


class ShopViews(Protocol):
    """商品項關的 Discord 元件（commands/shop_commands.py 實作）。"""

    def listing(self, listing: Listing, now: datetime) -> discord.ui.View:
        """商品貼文上的購買選單＋「⚙️ 管理商品（上架者）」。"""

    def order(self, listing_id: int, picks: dict[int, int], total: str) -> discord.ui.View:
        """交易 thread 裡訂單訊息上的停用按鈕：custom_id 帶訂單內容，字寫這筆的總計（total 已含幣別）。"""

    def guide(self) -> discord.ui.View:
        """置頂上架說明的「上架商品」按鈕。"""


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
        # 改同一篇商品（下單預留、管理品項、取消還回）要排隊：資料在同一則訊息上，先讀再寫
        self._locks: dict[object, asyncio.Lock] = {}
        #: 交給交易模組的來源種類（cog 載入時用 TradeService.add_source_kind 登記）
        self.source = ListingSource(self)

    # ── 權限 ──

    async def can_sell(self, member: discord.Member) -> bool:
        return await check_role(member, self.settings.seller_role)

    def can_manage(self, member: discord.Member, listing: Listing, guild=None) -> bool:
        """上架者本人或管理員（伺服器擁有者、有管理員權限的人）。guild 用商品貼文所在的伺服器。"""
        if member.id == listing.owner_id:
            return True
        guild = guild or getattr(member, "guild", None)
        if guild is not None and member.id == getattr(guild, "owner_id", None):
            return True
        permissions = getattr(member, "guild_permissions", None)
        return bool(permissions and permissions.administrator)

    # ── 上架說明（綁定商品論壇時） ──

    async def ensure_guide(self, forum: discord.ForumChannel) -> str:
        """商品論壇置頂一篇上架說明；已經有就確認它還置頂著、文字是最新的。回傳給管理員看的說明。"""
        guide = await self._find_guide(forum)
        if guide is None:
            message = await post_to_channel(
                forum, embed=self._guide_embed(), thread_title=self.settings.guide_title, view=self.views.guide())
            guide = message.channel
            await guide.edit(pinned=True)
            note = f"🛒 已發置頂的上架說明：{guide.jump_url}"
        else:
            if guide.archived:
                await guide.edit(archived=False)
            if not getattr(getattr(guide, "flags", None), "pinned", False):
                await guide.edit(pinned=True)
            note = f"🛒 置頂的上架說明已經在了：{guide.jump_url}"
            note += await self._refresh_guide(guide)
        # 先把「預購中」標籤建好：預購截止的提醒靠它找商品，建不了就整個不會提醒
        if await self._preorder_tag(forum, create=True) is None:
            note += (f"\n⚠️ 建不了「{self.settings.preorder_tag_name}」標籤（bot 需要這個論壇的「管理頻道」權限），"
                     "預購截止時不會提醒。")
        return note

    async def _refresh_guide(self, guide: discord.Thread) -> str:
        """說明文字改過（例：品相改叫品項）就更新已置頂的那篇，管理員重綁一次商品論壇即可。

        只改 embed：按鈕不動，也不傳附件清單（傳了會把貼文上的檔案刪掉）。"""
        want = self._guide_embed()
        try:
            starter = await guide.fetch_message(guide.id)  # 論壇第一則訊息 id＝thread id
            have = starter.embeds[0] if starter.embeds else None
            if have is not None and (have.title, have.description) == (want.title, want.description):
                return ""
            await starter.edit(embed=want)
        except discord.HTTPException:
            logger.error("商品上架：更新上架說明失敗 thread=%s", guide.id, exc_info=True)
            return "\n⚠️ 上架說明的文字沒能更新成最新版，請查看 log。"
        logger.info("商品上架：更新上架說明 thread=%s", guide.id)
        return "（文字已更新成最新版）"

    async def _find_guide(self, forum: discord.ForumChannel) -> Optional[discord.Thread]:
        def is_guide(thread: discord.Thread) -> bool:
            return thread.owner_id == self.bot.user.id and thread.name == self.settings.guide_title

        for thread in list(getattr(forum, "threads", None) or ()):
            if is_guide(thread):
                return thread
        async for thread in forum.archived_threads(limit=None):
            if is_guide(thread):
                return thread
        return None

    def _guide_embed(self) -> discord.Embed:
        return discord.Embed(
            title="上架說明",
            color=discord.Color.gold(),
            description=(
                "**觀星者上架商品**\n"
                "1. 按下方「🛒 上架商品」，填標題、說明、幣別（金額前面的符號，例 NT$），"
                "可以附商品圖（最多 10 張）。金額在加入品項時各自填。\n"
                "2. 到你的商品貼文按「⚙️ 管理商品（上架者）」加入品項：一次一個，或用「批次新增」一次加很多個。\n"
                "　・沒填截止時間＝立即購買；填了＝預購。時間一律寫年份，例：2026/10/20 23:59。\n\n"
                "**買家怎麼買**\n"
                "在商品貼文的下拉選單只挑自己要的（一次最多 5 種）→ 填數量 → 確認下單，"
                "就會開一個只有你和上架者的私人交易 thread。\n\n"
                "**交易流程**\n"
                "上架者交付後按「通知需求方領收」，買家收到後按「已領收」；還沒收到可以按「還沒領收」。"
                "有爭議可以按「請群主協助」。"
            ),
        )

    # ── 上架 ──

    async def create_listing(self, owner: discord.Member, *, title: str, description: str, unit: str,
                             attachments: Sequence[discord.Attachment] = ()) -> discord.Thread:
        forum = await self._forum()
        if forum is None:
            raise ShopError("商品論壇還沒設定，請管理員到 /server_manager 綁定「商品上架論壇」。")
        if not await self.can_sell(owner):
            raise ShopError("只有觀星者可以上架商品。")
        title, description, unit = self._clean_info(title, description, unit, owner.id)
        files = await self._image_files(attachments, forum.guild)
        now = self._now()
        listing = Listing(thread_id=0, owner_id=owner.id, unit=unit, title=title, description=description,
                          image=files[0].filename if files else None)
        message = await post_to_channel(
            forum, embed=render_embed(listing, owner.display_name, now), files=files,
            thread_title=title, view=self.views.listing(listing, now))
        thread = message.channel
        try:
            # 論壇貼文沒人講話就會自動封存，封存中的訊息改不了；拉到最長，少一點解除封存的次數
            await thread.edit(auto_archive_duration=self.settings.listing_auto_archive_minutes)
        except discord.HTTPException:
            logger.warning("商品上架：設定自動封存時間失敗 thread=%s", thread.id, exc_info=True)
        logger.info("商品上架：上架 thread=%s 上架者=%s", thread.id, owner.id)
        return thread

    def _clean_info(self, title: str, description: str, unit: str, owner_id: int) -> tuple[str, str, str]:
        title = (title or "").strip()
        if not title:
            raise ShopError("標題不能空白。")
        if len(title) > TITLE_LIMIT:
            raise ShopError(f"標題最多 {TITLE_LIMIT} 個字。")
        unit = (unit or "").strip() or self.settings.default_unit
        # 幣別只是金額前面的符號，金額在各品項各自填；擋數字，免得上架者把金額填在這裡（使用者 2026-10-03）
        if any(ch.isdigit() for ch in unit):
            raise ShopError(f"幣別不能有數字，只填金額前面的符號，例如 {UNIT_EXAMPLES}。"
                            "金額請在加入品項時各自填。")
        if len(unit) > UNIT_LIMIT or not unit_fits(unit):
            raise ShopError(f"幣別太長，請縮短（中文大約 7 個字以內），例如 {UNIT_EXAMPLES}。")
        return title, (description or "").strip(), unit

    async def _image_files(self, attachments: Sequence[discord.Attachment], guild) -> list[discord.File]:
        if len(attachments) > self.settings.max_images:
            raise ShopError(f"商品圖最多 {self.settings.max_images} 張。")
        # 先檢查大小再下載：圖會整個讀進記憶體，太大的也發不出去（貼文會先發成沒有圖的）
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

    # ── 讀寫商品貼文 ──

    async def load(self, listing_id: int) -> tuple[discord.Thread, discord.Message, Listing]:
        forum_id = await self._forum_id()
        thread = await self.trade.get_thread(listing_id)
        if thread is None or forum_id is None or getattr(thread, "parent_id", None) != forum_id:
            raise ShopError("找不到這篇商品。")
        message = await thread.fetch_message(listing_id)
        listing = listing_from_message(message)
        if listing is None:
            raise ShopError("找不到這篇商品。")
        return thread, message, listing

    async def is_listing(self, source_id: int) -> bool:
        forum_id = await self._forum_id()
        if forum_id is None:
            return False
        thread = await self.trade.get_thread(source_id)
        return thread is not None and getattr(thread, "parent_id", None) == forum_id

    async def _save(self, thread: discord.Thread, message: discord.Message, listing: Listing,
                    *, files: Optional[list[discord.File]] = None) -> None:
        """依商品資料重畫商品貼文。不傳 files 就不動原本的圖（只傳 embed，圖會留著）。

        封存中的 thread 改不了訊息，先解除封存，改完再封存回去（例：已下架的商品被取消還回時）。"""
        was_archived = thread.archived
        if was_archived:
            await thread.edit(archived=False)
        now = self._now()
        names = await self.trade.display_names(thread.guild, (listing.owner_id,))
        embed = render_embed(listing, names.get(listing.owner_id) or str(listing.owner_id), now)
        if files is None:
            await message.edit(embed=embed, view=self.views.listing(listing, now))
        else:
            await message.edit(embed=embed, view=self.views.listing(listing, now), attachments=files)
        await self._sync_tag(thread, listing)
        if was_archived:
            await thread.edit(archived=True)

    async def _sync_tag(self, thread: discord.Thread, listing: Listing) -> None:
        """還有沒截止的預購就掛「預購中」，沒有就拿掉（預購截止的提醒靠它找商品）。

        下架的商品也一樣：已成立的預購交易照常，截止時仍要提醒。"""
        want = listing.has_open_preorder()
        forum = thread.parent
        tag = await self._preorder_tag(forum, create=want)
        if tag is None:
            return
        current = list(thread.applied_tags)
        has = any(t.id == tag.id for t in current)
        if want and not has:
            await thread.edit(applied_tags=current + [tag])
        elif has and not want:
            await thread.edit(applied_tags=[t for t in current if t.id != tag.id])

    async def _preorder_tag(self, forum, *, create: bool) -> Optional[discord.ForumTag]:
        if forum is None:
            return None
        for tag in forum.available_tags:
            if tag.name == self.settings.preorder_tag_name:
                return tag
        if not create:
            return None
        # create_tag 會拿快取的標籤清單整份覆寫，同時建兩次後一次會蓋掉前一次，所以排隊
        async with self._lock(("tag", forum.id)):
            for tag in forum.available_tags:
                if tag.name == self.settings.preorder_tag_name:
                    return tag
            return await self._create_tag(forum)

    async def _create_tag(self, forum) -> Optional[discord.ForumTag]:
        try:
            return await forum.create_tag(name=self.settings.preorder_tag_name)
        except discord.HTTPException:
            logger.warning("商品上架：建立「%s」標籤失敗（缺 Manage Channels 權限？），預購截止的提醒會找不到這篇",
                           self.settings.preorder_tag_name, exc_info=True)
            return None

    # ── 管理（上架者或管理員） ──

    async def check_manager(self, listing_id: int, member: discord.Member, *,
                            listing: Optional[Listing] = None, guild=None) -> Listing:
        """listing 可以直接給（按鈕所在的商品貼文訊息讀出來的），省一趟讀 Discord。"""
        if listing is None:
            thread, _, listing = await self.load(listing_id)
            guild = thread.guild
        if not self.can_manage(member, listing, guild):
            raise ShopError("只有上架者可以管理這篇商品。")
        return listing

    async def add_variants(self, listing_id: int, actor: discord.Member, drafts: Sequence[Draft]) -> Listing:
        async with self._lock(listing_id):
            thread, message, listing = await self._load_for_manage(listing_id, actor)
            if len(listing.variants) + len(drafts) > self.settings.max_variants:
                raise ShopError(f"一篇商品最多 {self.settings.max_variants} 個品項，"
                                f"目前有 {len(listing.variants)} 個。")
            for draft in drafts:
                listing = listing.add(draft)
            await self._save(thread, message, listing)
            return listing

    async def edit_variant(self, listing_id: int, actor: discord.Member, key: int, draft: Draft) -> Listing:
        """編輯品項。draft.limit 是「剩餘數量」（還要賣幾個，None＝不限量）：
        存的上限＝已下單＋剩餘，補貨 5 個就填 5，不用自己算（使用者 2026-10-03，TR-Q27）。"""
        async with self._lock(listing_id):
            thread, message, listing = await self._load_for_manage(listing_id, actor)
            variant = listing.variant(key)
            if variant is None:
                raise ShopError("找不到這個品項，可能已經被刪除。")
            limit = None if draft.limit is None else variant.taken + draft.limit
            # 編輯後一律重新開放：parse_draft 保證預購的截止時間在未來，改成立即購買也就沒有截止
            listing = listing.with_variant(replace(
                variant, name=draft.name, price=draft.price, limit=limit, cutoff=draft.cutoff, closed=False))
            await self._save(thread, message, listing)
            return listing

    async def delete_variant(self, listing_id: int, actor: discord.Member, key: int) -> Listing:
        async with self._lock(listing_id):
            thread, message, listing = await self._load_for_manage(listing_id, actor)
            variant = listing.variant(key)
            if variant is None:
                raise ShopError("找不到這個品項，可能已經被刪除。")
            if any(key in picks for _, _, picks in await self._open_orders(listing_id)):
                raise ShopError(f"還有進行中的交易買了「{variant.name}」，請先完成或取消那些交易。")
            listing = listing.without_variant(key)
            await self._save(thread, message, listing)
            return listing

    async def edit_info(self, listing_id: int, actor: discord.Member, *, title: str, description: str, unit: str,
                        attachments: Sequence[discord.Attachment] = ()) -> Listing:
        title, description, unit = self._clean_info(title, description, unit, actor.id)
        # 下載圖片在鎖外：下載期間不要擋住這篇的下單
        files = await self._image_files(attachments, getattr(actor, "guild", None)) if attachments else None
        async with self._lock(listing_id):
            thread, message, listing = await self._load_for_manage(listing_id, actor)
            listing = replace(listing, title=title, description=description, unit=unit,
                              image=files[0].filename if files else listing.image)
            await self._save(thread, message, listing, files=files)
        # 改名在鎖外：改名限速很嚴，等待期間不要擋住這篇的下單
        if thread.name != title:
            await thread.edit(name=title)
        return listing

    async def close_listing(self, listing_id: int, actor: discord.Member) -> Listing:
        """下架：不再接單，已成立的交易照常進行。"""
        async with self._lock(listing_id):
            thread, message, listing = await self._load_for_manage(listing_id, actor)
            listing = replace(listing, closed=True)
            await self._save(thread, message, listing)
        # 改名、鎖定在鎖外（改名限速很嚴）；這時貼文已標成下架，新的下單會被擋下
        await thread.edit(name=(CLOSED_PREFIX + listing.title)[:100], locked=True, archived=True)
        logger.info("商品上架：下架 thread=%s by=%s", thread.id, actor.id)
        return listing

    async def _load_for_manage(self, listing_id: int, actor: discord.Member):
        thread, message, listing = await self.load(listing_id)
        if not self.can_manage(actor, listing, thread.guild):
            raise ShopError("只有上架者可以管理這篇商品。")
        if listing.closed:
            raise ShopError("這篇商品已經下架了。")
        return thread, message, listing

    # ── 購買 ──

    async def refresh_listing(self, listing_id: int) -> None:
        """資料不變、重畫商品貼文：購買選單回到未選取。

        Discord 的選單選過同一組就不會再通知 bot；買家填完數量後如果取消，下次才選得回同樣的商品。"""
        try:
            async with self._lock(listing_id):
                thread, message, listing = await self.load(listing_id)
                await self._save(thread, message, listing)
        except Exception:
            logger.warning("商品上架：重畫商品貼文失敗 商品=%s", listing_id, exc_info=True)

    async def check_pick(self, listing_id: int, buyer: discord.Member, keys: Sequence[int], *,
                         listing: Optional[Listing] = None) -> list[Variant]:
        """買家在下拉選完：檢查這些品項現在能不能買，回傳要填數量的品項。

        listing 可以直接給（下拉所在的商品貼文訊息讀出來的，跟重讀一樣新），省一趟讀 Discord；
        真正下單時會在鎖裡重讀再檢查一次。"""
        if listing is None:
            _, _, listing = await self.load(listing_id)
        self._check_buyer(buyer, listing)
        if len(keys) > self.settings.max_pick:
            raise ShopError(f"一次最多挑 {self.settings.max_pick} 種。")
        lines = quote_order(listing, {key: 1 for key in keys}, self._now())
        return [variant for variant, _ in lines]

    async def quote(self, listing_id: int, buyer: discord.Member,
                    picks: dict[int, int]) -> tuple[list[str], int, Listing]:
        """下單前給買家看的明細（每行一項）、總計。"""
        _, _, listing = await self.load(listing_id)
        self._check_buyer(buyer, listing)
        rows, total = order_summary(quote_order(listing, picks, self._now()), listing.unit)
        return rows, total, listing

    async def place_order(self, listing_id: int, buyer: discord.Member, picks: dict[int, int]) -> OpenedTrade:
        """下單：先預留數量，再開（或沿用）買家與上架者的交易 thread；開不起來就把預留還回去。"""
        # 整段在商品鎖裡：預留之後、訂單發出之前，刪品項與預購截止都看不到這筆訂單，所以不能放掉鎖
        async with self._lock(listing_id):
            thread, message, listing = await self.load(listing_id)
            self._check_buyer(buyer, listing)
            lines = quote_order(listing, picks, self._now())
            owner = await self.trade.member(thread.guild, listing.owner_id)
            if owner is None:
                raise ShopError("上架者已經不在伺服器裡，暫時不能下單。")
            await self._save(thread, message, apply_order(listing, picks))
            try:
                rows, total = order_summary(lines, listing.unit)
                note = TradeNote(content=self._order_text(buyer, owner, listing, rows, lines),
                                 view=self.views.order(listing_id, picks, money(listing.unit, total)))
                opened = await self.trade.open_trade(thread, buyer, owner, note=note, kind=self.source)
                if opened is None:
                    raise ShopError("交易 thread 開不起來（購物車頻道沒有設定），請通知管理員。")
            except Exception:
                thread, message, listing = await self.load(listing_id)
                await self._save(thread, message, release_order(listing, picks))
                raise
            if note.view is not None:
                note.view.stop()  # 訂單紀錄的按鈕是停用的，不必一直留在記憶體裡等互動
        logger.info("商品上架：下單 商品=%s 買家=%s 內容=%s thread=%s", listing_id, buyer.id, picks, opened.thread.id)
        return opened

    def _check_buyer(self, buyer: discord.Member, listing: Listing) -> None:
        if buyer.id == listing.owner_id:
            raise ShopError("不能買自己上架的商品。")

    def _order_text(self, buyer, owner, listing: Listing, rows: list[str], lines) -> str:
        # 總計寫在底下的按鈕上，文字裡不再寫一次（使用者 2026-10-04，TR-Q40）
        text = (f"🧾 {buyer.mention} 向 {owner.mention} 下單（{listing.title}）：\n"
                + "\n".join(f"・{row}" for row in rows))
        if any(variant.preorder for variant, _ in lines):
            text += "\n預購的商品會在截止後由供應方安排交付，截止時 bot 會在這裡提醒雙方。"
        return text

    # ── 取消時還回預留（交易模組呼叫，見 ListingSource） ──

    async def release_thread_orders(self, thread: discord.Thread, ref: TradeRef) -> None:
        picks = await self._orders_in(thread, ref.source_id)
        if picks:
            await self._release(ref.source_id, picks)

    async def _release(self, listing_id: int, picks: dict[int, int]) -> None:
        async with self._lock(listing_id):
            try:
                thread, message, listing = await self.load(listing_id)
            except ShopError:
                return  # 商品貼文已經不在
            await self._save(thread, message, release_order(listing, picks))
        logger.info("商品上架：還回預留 商品=%s 內容=%s", listing_id, picks)

    async def archive_trade(self, thread: discord.Thread, ref: TradeRef) -> str:
        """商品交易完成時在封存頻道留底：摘要是每筆下單（下單當時的價格），附檔是整個交易 thread 的對話。

        商品貼文本身不動（還要賣給別人）；自由市場是把需求貼文搬過去，這裡是另發一篇備份
        （使用者 2026-10-03）。回傳要加在完成訊息裡的說明。"""
        try:
            names = await self.trade.display_names(thread.guild, (ref.requester_id, ref.supplier_id))
            requester = names.get(ref.requester_id) or str(ref.requester_id)
            supplier = names.get(ref.supplier_id) or str(ref.supplier_id)
            try:
                _, _, listing = await self.load(ref.source_id)
                title = listing.title
            except ShopError:
                title = f"商品 {ref.source_id}"  # 商品貼文已經不在，仍要留底
            orders = []
            async for message in thread.history(limit=None, oldest_first=True):
                if message.author.id == self.bot.user.id and any(
                        listing_id == ref.source_id for listing_id, _ in orders_on(message)):
                    total = order_total(message)  # 總計在按鈕上，留底要一起帶上
                    orders.append(mentions_to_names(message.content, names) + (f"\n{total}" if total else ""))
            summary = (f"商品：{title}（<#{ref.source_id}>）\n"
                       f"需求方：{requester}　供應方：{supplier}\n"
                       f"完成時間：{self._now().astimezone(APP_TZ):%Y-%m-%d %H:%M}\n\n"
                       + "\n\n".join(orders))
            # 放得下就整段寫在貼文、放不下才附 .txt：由 post_archive 決定（TR-Q28）
            posted = await self.trade.post_archive(
                title=f"【市集】{title}｜{requester} 與 {supplier}"[:100],
                summary=summary,
                transcript=await self.trade.transcript(thread, limit=None),
                filename=f"shop_{ref.source_id}_{thread.id}.txt",
            )
        except Exception:
            logger.error("商品上架：交易留底失敗 thread=%s", thread.id, exc_info=True)
            return "交易紀錄留底失敗，請通知管理員。"
        return "交易紀錄已留底到封存頻道。" if posted else "封存頻道沒有設定，這筆交易沒有留底。"

    async def _orders_in(self, thread: discord.Thread, listing_id: int) -> dict[int, int]:
        """交易 thread 裡這篇商品的訂單加總（首次下單＋加購）。"""
        total: dict[int, int] = {}
        # 整個 thread 都要讀：第一筆訂單在最舊那端，只讀最新幾則會先漏掉它
        async for message in thread.history(limit=None):
            if message.author.id != self.bot.user.id:
                continue
            for order_listing, picks in orders_on(message):
                if order_listing == listing_id:
                    for key, qty in picks.items():
                        total[key] = total.get(key, 0) + qty
        return total

    async def _open_orders(self, listing_id: int) -> list[tuple[discord.Thread, Optional[TradeRef], dict[int, int]]]:
        found = []
        for thread, ref in await self.trade.open_trades_for_source(listing_id):
            found.append((thread, ref, await self._orders_in(thread, listing_id)))
        return found

    # ── 預購截止（utils.due_loop 每次醒來呼叫） ──

    async def run_preorder_cutoffs(self, now: datetime) -> Optional[datetime]:
        """截止的預購：在含這個品項、還沒完成的交易 thread @ 雙方，再把品項標成已截止。回傳下一個截止時間。

        只看掛著「預購中」標籤的商品；已封存的貼文清單本身就帶標籤，不用一篇篇打開。"""
        forum = await self._forum()
        if forum is None:
            return None
        tag = await self._preorder_tag(forum, create=False)
        if tag is None:
            return None
        next_due: Optional[datetime] = None
        for thread in await self._tagged(forum, tag):
            try:
                due = await self._process_cutoffs(thread.id, now)
            except Exception:
                logger.error("商品上架：處理預購截止失敗 商品=%s", thread.id, exc_info=True)
                continue
            if due is not None:
                next_due = due if next_due is None else min(next_due, due)
        return next_due

    async def _tagged(self, forum, tag: discord.ForumTag) -> list[discord.Thread]:
        found: dict[int, discord.Thread] = {}

        def tagged(thread) -> bool:
            return any(t.id == tag.id for t in thread.applied_tags)

        for thread in list(getattr(forum, "threads", None) or ()):
            if tagged(thread):
                found[thread.id] = thread
        async for thread in forum.archived_threads(limit=None):
            if thread.id not in found and tagged(thread):
                found[thread.id] = thread
        return list(found.values())

    async def _process_cutoffs(self, listing_id: int, now: datetime) -> Optional[datetime]:
        async with self._lock(listing_id):
            thread, message, listing = await self.load(listing_id)
            pending = [v for v in listing.variants if v.preorder and not v.closed]
            due = [v for v in pending if v.cutoff <= now]
            upcoming = min((v.cutoff for v in pending if v.cutoff > now), default=None)
            if due:
                trades = await self._open_orders(listing_id)
                for variant in due:
                    for trade_thread, ref, picks in trades:
                        if ref is not None and variant.key in picks:
                            # 一個 thread 發不出去不影響其他人；不然品項一直標不成已截止，每小時重複 @ 大家
                            try:
                                await trade_thread.send(
                                    f"⏰ <@{ref.requester_id}> <@{ref.supplier_id}> 預購商品「{variant.name}」"
                                    f"已截止（{format_cutoff(variant.cutoff)}），請依已購買的內容安排交付。")
                            except Exception:
                                logger.error("商品上架：預購截止提醒發送失敗 thread=%s", trade_thread.id, exc_info=True)
                    listing = listing.with_variant(replace(variant, closed=True))
                await self._save(thread, message, listing)
            elif not pending:
                await self._sync_tag(thread, listing)  # 標籤殘留（例：品項被刪）就拿掉
            return upcoming

    # ── 內部 ──

    def _lock(self, key: object) -> asyncio.Lock:
        return self._locks.setdefault(key, asyncio.Lock())

    async def _forum_id(self) -> Optional[int]:
        # 每次重讀（有 5 分鐘快取）：頻道是使用者在 /server_manager 綁的，bot 不重啟也可能改
        return await ChannelConfig.get_configured_id(self.settings.forum_channel_key, caller="shop")

    async def _forum(self):
        forum_id = await self._forum_id()
        return self.bot.get_channel(forum_id) if forum_id is not None else None


class ListingSource:
    """交易模組的來源種類：商品貼文。成交後商品保留、可以賣給很多人；取消時還回預留的數量。"""

    label = "商品貼文"

    def __init__(self, shop: ShopService):
        self.shop = shop

    async def owns(self, thread: discord.Thread, ref: TradeRef) -> bool:
        # 看交易 thread 裡有沒有這篇商品的訂單紀錄：商品交易一開單就有，自由市場的交易不會有
        return bool(await self.shop._orders_in(thread, ref.source_id))

    def opening_text(self, ref: TradeRef) -> str:
        return (f"需求方 <@{ref.requester_id}> 向供應方 <@{ref.supplier_id}> 下單了，"
                "請在這裡討論交易細節。下單明細在下面。")

    async def on_complete(self, thread: discord.Thread, ref: TradeRef) -> str:
        note = await self.shop.archive_trade(thread, ref)
        return f"商品貼文保留，其他買家不受影響。{note}"

    def cancel_text(self, ref: TradeRef) -> str:
        return (f"<@{ref.requester_id}>，供應方 <@{ref.supplier_id}> 已取消這筆交易，"
                "此 thread 將鎖定，預留的數量會還回商品。")

    async def on_cancel(self, thread: discord.Thread, ref: TradeRef) -> None:
        await self.shop.release_thread_orders(thread, ref)
