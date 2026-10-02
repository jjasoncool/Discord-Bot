"""交易模組：自由市場的需求被供應方接單後，在購物車開私人 thread，處理領收、取消、封存。

角色（使用者 2026-10-03 定名；交易不一定是買賣，所以不叫買家賣家）：
  - 需求方（requester）：在自由市場發需求的人。使用者自己發的貼文就是貼文作者；
    `/select_item` 由 bot 代發的貼文，是內文裡被 @ 的人。
  - 供應方（supplier）：對需求貼文按表情接單的人，必須有 Trader 身份組（伺服器上叫觀星者）。

交易紀錄就是 Discord 本身，沒有資料表（使用者 2026-10-03 決定）：
  - 身分（需求貼文、需求方、供應方）寫在按鈕的 custom_id。只有 bot 寫得進去，重啟後照樣讀得到；
    以前寫在一段中文句子裡，四個地方各自用字串切割讀回來。
  - 狀態看交易 thread：沒鎖定＝進行中；結束時一次改名加上結果前綴並鎖定。
    標題結尾的需求貼文 id 用來找同一篇需求的其他交易。
  - 領收期限＝目前有效的那則「通知需求方領收」訊息的時間＋設定時數，不另外存。
    需求方按「還沒領收」時，bot 拿掉那則通知上的按鈕，期限就不存在了（自動領收暫停）；
    到期前的提醒做過沒有，看 bot 有沒有在那則通知上按 ⏰。都是在 Discord 上做的註記。

同一篇需求可以有多位供應方，每位各開一個 thread、只加入雙方（不同供應方很正常）。
一位完成後需求貼文會封存並刪除，其他供應方的 thread 一併結束（TR-Q8）。
只有供應方能取消（TR-Q4：避免需求方受領服務後擅自取消；需求方想取消就跟供應方說）。

按鈕長什麼樣子屬於 Discord 介面，由 commands/forum_monitor.py 以 `make_view` 交進來；
這裡不 import 指令層（理由同點名服務：互相 import 會形成循環）。
"""
from __future__ import annotations

import asyncio
import contextlib
import io
import logging
import math
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import AsyncIterator, Callable, Iterator, Optional, Sequence

import discord
from discord.utils import snowflake_time

from sys_settings.time_settings import APP_TZ
from sys_settings.trade_settings import TradeSettings
from utils.discord_content import get_forum_tags, post_to_channel
from utils.utils import ChannelConfig, check_role, safe_send_interaction_message

logger = logging.getLogger(__name__)

# ── 按鈕動作 ──
NOTIFY = "notify"    # 供應方：通知需求方領收
CANCEL = "cancel"    # 供應方：取消交易
RECEIVE = "receive"  # 需求方：已領收
HOLD = "hold"        # 需求方：還沒領收（暫停自動領收）
HELP = "help"        # 雙方：請群主協助
_SUPPLIER_ACTIONS = (NOTIFY, CANCEL)
_REQUESTER_ACTIONS = (RECEIVE, HOLD)

#: 交易按鈕 custom_id 的格式；forum_monitor 的 DynamicItem 用同一個 template 解析
CUSTOM_ID_TEMPLATE = (
    r"trade:(?P<action>notify|cancel|receive|hold|help):(?P<source>\d+):(?P<requester>\d+):(?P<supplier>\d+)"
)
_CUSTOM_ID_RE = re.compile(CUSTOM_ID_TEMPLATE)

# ── 交易 thread 標題：「前綴 需求方 與 供應方 - 需求貼文id」──
OPEN_PREFIX = "【交易中】"
COMPLETED_PREFIX = "【已完成】"
CANCELLED_PREFIX = "【已取消】"
ENDED_PREFIX = "【已結束】"  # 同一篇需求由別的供應方完成
#: 改版前的標題「交易確認 - 需求方 和 供應方 - 需求貼文id」
LEGACY_PREFIX = "交易確認 - "
_TITLE_LIMIT = 100

#: 改版前開單訊息的文字。舊 thread 上的舊按鈕靠它還原交易身分；舊 thread 都結束後可刪。
#: 舊文字裡「使用者」是按表情的人（供應方），「貼文者」是被 @ 的人（需求方）。
_LEGACY_RE = re.compile(
    r"使用者 <@!?(?P<supplier>\d+)> 對交易貼文.*?貼文者為 <@!?(?P<requester>\d+)>.*?來源貼文 ID: (?P<source>\d+)",
    re.DOTALL,
)

# 封存需求貼文的結果
_ARCHIVED = "archived"
_ARCHIVED_KEPT = "archived_kept"  # 已複製到封存頻道，但刪除原貼文失敗
_MISSING = "missing"    # 需求貼文已經不在（被刪、或別的供應方完成時已封存）
_LOCKED = "locked"      # 封存頻道沒設定，只鎖定需求貼文
_FAILED = "failed"      # 複製失敗，保留原貼文
_ARCHIVE_NOTE = {
    _ARCHIVED: "需求貼文已封存。",
    _ARCHIVED_KEPT: "需求貼文已封存，但刪除原貼文失敗，請通知管理員刪除。",
    _MISSING: "",
    _LOCKED: "封存頻道未設定，需求貼文已鎖定。",
    _FAILED: "需求貼文封存失敗，已保留原貼文，請通知管理員。",
}


@dataclass(frozen=True)
class TradeRef:
    """一筆交易的身分。需求貼文是自由市場論壇裡的 thread，它第一則訊息的 id 等於 thread id。"""

    source_id: int
    requester_id: int
    supplier_id: int

    def custom_id(self, action: str) -> str:
        return f"trade:{action}:{self.source_id}:{self.requester_id}:{self.supplier_id}"


@dataclass(frozen=True)
class OpenedTrade:
    thread: discord.Thread
    #: False＝同一位供應方對同一篇需求已經有進行中的 thread，沿用它
    created: bool
    supplier: discord.Member


def ref_from_match(match: re.Match) -> TradeRef:
    return TradeRef(int(match["source"]), int(match["requester"]), int(match["supplier"]))


def parse_custom_id(custom_id: str) -> Optional[tuple[str, TradeRef]]:
    match = _CUSTOM_ID_RE.fullmatch(custom_id or "")
    if match is None:
        return None
    return match["action"], ref_from_match(match)


def legacy_ref_from_text(content: str) -> Optional[TradeRef]:
    match = _LEGACY_RE.search(content or "")
    return ref_from_match(match) if match else None


def resolve_requester(starter: discord.Message, *, bot_user_id: int, supplier_id: int) -> Optional[int]:
    """需求貼文的需求方是誰（交易來源判定，全模組只在這裡判斷）。

    - bot 代發的貼文（/select_item）：內文裡第一個不是供應方的 @。
    - 使用者自己發的貼文：貼文作者。
    供應方對自己的需求按表情不算交易，回 None。
    """
    if starter.author.id == bot_user_id:
        return next((m.id for m in starter.mentions if m.id != supplier_id), None)
    if starter.author.id == supplier_id:
        return None
    return starter.author.id


def _fit_title(head: str, source_id: int) -> str:
    """標題上限 100 字；太長時截掉前段，保住結尾的需求貼文 id（找同一篇需求的交易靠它）。"""
    tail = f" - {source_id}"
    return head[: _TITLE_LIMIT - len(tail)] + tail


def open_title(requester_name: str, supplier_name: str, source_id: int) -> str:
    return _fit_title(f"{OPEN_PREFIX}{requester_name} 與 {supplier_name}", source_id)


def closed_title(title: str, prefix: str) -> str:
    base = title[len(OPEN_PREFIX):] if title.startswith(OPEN_PREFIX) else title
    head, sep, tail = base.rpartition(" - ")
    if not sep or not tail.isdigit():
        return (prefix + base)[:_TITLE_LIMIT]
    return _fit_title(prefix + head, int(tail))


def source_id_in_title(title: str) -> Optional[int]:
    _, sep, tail = title.rpartition(" - ")
    return int(tail) if sep and tail.isdigit() else None


def is_trade_title(title: str) -> bool:
    return title.startswith(OPEN_PREFIX) or title.startswith(LEGACY_PREFIX)


def _refs_on(message: discord.Message) -> Iterator[tuple[str, TradeRef]]:
    """訊息上的交易按鈕（動作, 交易身分）。"""
    for row in getattr(message, "components", None) or ():
        for child in getattr(row, "children", None) or ():
            parsed = parse_custom_id(getattr(child, "custom_id", None) or "")
            if parsed:
                yield parsed


class TradeService:
    def __init__(
        self,
        bot: discord.Client,
        *,
        make_view: Callable[[TradeRef, Sequence[str]], discord.ui.View],
        settings: Optional[TradeSettings] = None,
    ):
        self.bot = bot
        self.settings = settings or TradeSettings()
        self._make_view = make_view
        # 同一筆交易的按鈕可能被連按、或和期限檢查同時到；鎖住後再確認一次是否已結束
        self._locks: dict[object, asyncio.Lock] = {}
        # 這個行程裡已經結束的 thread（Discord 的鎖定狀態要等事件回來才會更新到快取）
        self._closed: set[int] = set()

    # ── 入口：供應方對需求貼文按表情 ──

    async def handle_reaction(self, payload: discord.RawReactionActionEvent) -> Optional[OpenedTrade]:
        """供應方接單：對自由市場貼文本身按表情。不符合條件的反應一律略過（回 None）。"""
        if str(payload.emoji) not in self.settings.accept_emojis or payload.guild_id is None:
            return None
        # 只認貼文本身：論壇貼文第一則訊息的 id 就是 thread id。
        # 對貼文裡別人的回覆按 ✅ 表示「收到」很常見，不能因此開單。
        if payload.message_id != payload.channel_id:
            return None
        if self.bot.user is not None and payload.user_id == self.bot.user.id:
            return None
        forum_id = await self._channel_id(self.settings.forum_channel_key)
        if forum_id is None:
            return None
        source = await self._get_thread(payload.channel_id)
        if source is None or getattr(source, "parent_id", None) != forum_id:
            return None

        guild = self.bot.get_guild(payload.guild_id)
        # 表情事件本身帶著 Discord 當下送來的成員資料（含伺服器暱稱與身份組，不是快取）；
        # 沒帶才走快取 → API
        supplier = payload.member or await self._member(guild, payload.user_id)
        if supplier is None or supplier.bot:
            return None
        if not await check_role(supplier, self.settings.supplier_role):
            logger.info("交易：%s 沒有 %s 身份組，不算接單（需求貼文 %s）",
                        supplier.display_name, self.settings.supplier_role, source.id)
            return None

        starter = await source.fetch_message(payload.message_id)
        requester_id = resolve_requester(starter, bot_user_id=self.bot.user.id, supplier_id=supplier.id)
        if requester_id is None:
            logger.info("交易：需求貼文 %s 找不到需求方（或需求方就是供應方），不開單", source.id)
            return None
        requester = await self._member(guild, requester_id)
        if requester is None or requester.bot:
            logger.info("交易：需求方 %s 不在伺服器裡或是 bot，不開單（需求貼文 %s）", requester_id, source.id)
            return None
        return await self.open_trade(source, requester, supplier)

    async def open_trade(
        self, source: discord.Thread, requester: discord.Member, supplier: discord.Member
    ) -> Optional[OpenedTrade]:
        """為（需求貼文, 供應方）開一個私人交易 thread；同一組已經有進行中的就沿用。"""
        cart = await self._channel(self.settings.cart_channel_key)
        if cart is None:
            logger.error("交易：購物車頻道未設定或找不到，無法開交易 thread（需求貼文 %s）", source.id)
            return None
        async with self._lock(("open", source.id, supplier.id)):
            for thread, ref in await self._open_trades_for(cart, source.id):
                if ref is not None and ref.supplier_id == supplier.id:
                    await thread.send(f"{supplier.mention} 又對需求貼文按了表情；這筆交易還在這個 thread 進行中。")
                    return OpenedTrade(thread, False, supplier)

            ref = TradeRef(source.id, requester.id, supplier.id)
            thread = await cart.create_thread(
                name=open_title(requester.display_name, supplier.display_name, source.id),
                type=discord.ChannelType.private_thread,
                invitable=False,  # 只有需求方和這位供應方，不讓人再邀別人進來
                # 購物車頻道預設 3 天沒人講話就封存；拉到最長，等領收的交易比較不會在期限前被封存
                auto_archive_duration=10080,
                reason=f"交易：需求貼文 {source.id}，需求方 {requester.id}，供應方 {supplier.id}",
            )
            try:
                await thread.add_user(requester)
                await thread.add_user(supplier)
                await thread.send(
                    content=f"{requester.mention} {supplier.mention}",
                    embed=self._opening_embed(ref),
                    view=self._make_view(ref, (NOTIFY, CANCEL, HELP)),
                )
            except Exception:
                # 沒有開單訊息就讀不到交易身分，同一位供應方再按會又開一個，所以整個刪掉
                with contextlib.suppress(discord.HTTPException):
                    await thread.delete()
                raise
            logger.info("交易：開單 thread=%s 需求貼文=%s 需求方=%s 供應方=%s",
                        thread.id, source.id, requester.id, supplier.id)
            return OpenedTrade(thread, True, supplier)

    # ── 入口：交易 thread 裡的按鈕 ──

    async def handle_button(self, interaction: discord.Interaction, action: str, ref: TradeRef) -> None:
        if action in _SUPPLIER_ACTIONS and interaction.user.id != ref.supplier_id:
            await safe_send_interaction_message(
                interaction, f"只有供應方 <@{ref.supplier_id}> 可以操作這個按鈕。", ephemeral=True)
            return
        if action in _REQUESTER_ACTIONS and interaction.user.id != ref.requester_id:
            await safe_send_interaction_message(
                interaction, f"只有需求方 <@{ref.requester_id}> 可以操作這個按鈕。", ephemeral=True)
            return
        if action == HELP and interaction.user.id not in (ref.requester_id, ref.supplier_id):
            await safe_send_interaction_message(interaction, "只有這筆交易的雙方可以請群主協助。", ephemeral=True)
            return
        thread = interaction.channel
        if thread is None or getattr(thread, "locked", False) or thread.id in self._closed:
            await safe_send_interaction_message(interaction, "這筆交易已經結束。", ephemeral=True)
            return
        if not interaction.response.is_done():
            await interaction.response.defer()
        try:
            if action == NOTIFY:
                await self.request_receipt(thread, ref)
            elif action == CANCEL:
                await self.cancel(thread, ref)
            elif action == HOLD:
                await self.hold_receipt(thread, ref, interaction.message)
            elif action == HELP:
                if not await self.call_owner(thread, ref, interaction.user):
                    await safe_send_interaction_message(interaction, "群主已經在這個 thread 裡了。", ephemeral=True)
            else:
                await self.complete(thread, ref, auto=False)
        except Exception:
            logger.error("交易：處理按鈕 %s 失敗 thread=%s ref=%s", action, thread.id, ref, exc_info=True)
            await safe_send_interaction_message(interaction, "處理交易時發生錯誤，請截圖通知管理員。", ephemeral=True)

    async def request_receipt(self, thread: discord.Thread, ref: TradeRef) -> None:
        hours = self.settings.receipt_timeout_hours
        # 上鎖再確認一次：完成流程跑到一半時發訊息，會把剛鎖定的 thread 重新打開
        async with self._lock(thread.id):
            if thread.id in self._closed:
                return
            # 同一時間只有一則有效的通知：期限從它起算，舊的拿掉按鈕
            async for message in thread.history(limit=100):
                if self._is_active_request(message):
                    await message.edit(content=f"{message.content}\n（已由新的通知取代）", view=None)
            await thread.send(
                content=(f"<@{ref.requester_id}>，供應方 <@{ref.supplier_id}> 已通知交付完成。"
                         "收到後請按「已領收」；還沒收到請按「還沒領收」，自動領收會暫停。"
                         f"{hours} 小時內都沒有按，將自動視為已領收。"),
                view=self._make_view(ref, (RECEIVE, HOLD, HELP)),
            )

    async def hold_receipt(self, thread: discord.Thread, ref: TradeRef, message: Optional[discord.Message]) -> None:
        """需求方說還沒領收：拿掉那則通知上的按鈕（期限跟著消失），請供應方交付後再通知一次。"""
        async with self._lock(thread.id):
            if thread.id in self._closed or message is None or not self._is_active_request(message):
                return
            await message.edit(content=f"{message.content}\n（需求方表示還沒領收，自動領收已暫停）", view=None)
            await thread.send(f"<@{ref.supplier_id}>，需求方 <@{ref.requester_id}> 表示還沒領收，自動領收已暫停。"
                              "交付後請再按一次「通知需求方領收」；有爭議可以按「請群主協助」。")
        logger.info("交易：需求方表示還沒領收 thread=%s ref=%s", thread.id, ref)

    async def call_owner(self, thread: discord.Thread, ref: TradeRef, user: discord.abc.User) -> bool:
        """請群主（伺服器擁有者）進來協助：加進這個私人 thread 並 @ 他。群主已經在裡面就回 False。"""
        owner_id = getattr(thread.guild, "owner_id", None)
        if owner_id is None:
            raise RuntimeError("找不到伺服器擁有者")
        async with self._lock(("help", thread.id)):
            try:
                await thread.fetch_member(owner_id)
                return False
            except discord.NotFound:
                pass
            await thread.add_user(discord.Object(id=owner_id))
            await thread.send(f"<@{owner_id}>，{user.mention} 請群主協助處理這筆交易"
                              f"（需求方 <@{ref.requester_id}>、供應方 <@{ref.supplier_id}>）。")
        logger.info("交易：請群主協助 thread=%s by=%s", thread.id, user.id)
        return True

    async def cancel(self, thread: discord.Thread, ref: TradeRef) -> None:
        async with self._lock(thread.id):
            if thread.id in self._closed:
                return
            # 先發訊息再鎖定：對已封存的 thread 發訊息會把它重新打開
            await thread.send(f"<@{ref.requester_id}>，供應方 <@{ref.supplier_id}> 已取消這筆交易，"
                              "此 thread 將鎖定。需求貼文保留，其他供應方仍可接單。")
            await self._close(thread, CANCELLED_PREFIX)
        await self._clear_supplier_reactions(ref)
        logger.info("交易：取消 thread=%s ref=%s", thread.id, ref)

    async def complete(self, thread: discord.Thread, ref: TradeRef, *, auto: bool) -> None:
        async with self._lock(thread.id):
            if thread.id in self._closed:
                return
            result = await self._archive_source(ref)
            if auto:
                who = (f"<@{ref.requester_id}> 在 {self.settings.receipt_timeout_hours} 小時內沒有按已領收，"
                       "自動視為已領收")
            else:
                who = f"<@{ref.requester_id}> 已領收"
            await thread.send(f"{who}，交易完成。{_ARCHIVE_NOTE[result]}此 thread 將鎖定。")
            await self._close(thread, COMPLETED_PREFIX)
        logger.info("交易：完成 thread=%s ref=%s auto=%s 需求貼文=%s", thread.id, ref, auto, result)
        # 在鎖外處理：兩位供應方同時完成時，各自拿著自己的鎖去等對方的鎖會卡死
        await self._end_other_trades(ref, keep_thread_id=thread.id)

    # ── 入口：定時檢查領收期限（utils.due_loop 每次醒來呼叫）──

    async def run_receipt_deadlines(self, now: datetime) -> Optional[datetime]:
        """把超過期限還沒按已領收的交易自動完成；回傳下一個期限。

        期限從 Discord 上的訊息時間推算，連停機期間被自動封存的交易 thread 也會翻出來，
        所以 bot 重啟過也照樣補做。"""
        cart = await self._channel(self.settings.cart_channel_key)
        if cart is None:
            return None
        timeout = timedelta(hours=self.settings.receipt_timeout_hours)
        archived_since = now - timedelta(days=self.settings.archived_scan_days)
        next_due: Optional[datetime] = None
        async for thread in self._open_trade_threads(cart, archived_since=archived_since):
            # 一個 thread 讀不到不影響其他 thread 這一輪的檢查
            try:
                pending = await self._pending_receipt(thread)
                if pending is None:
                    continue
                ref, request = pending
                due = request.created_at + timeout
                if due <= now:
                    await self.complete(thread, ref, auto=True)
                    continue
                wake = [due]
                remind_at = self._remind_at(due)
                if remind_at is not None and not self._reminded(request):
                    if remind_at <= now:
                        await self._remind_receipt(thread, ref, request, due, now)
                    else:
                        wake.append(remind_at)
                next_due = min([t for t in (next_due, *wake) if t is not None])
            except Exception:
                logger.error("交易：檢查領收期限失敗 thread=%s", thread.id, exc_info=True)
        return next_due

    # ── 內部 ──

    def _lock(self, key: object) -> asyncio.Lock:
        return self._locks.setdefault(key, asyncio.Lock())

    async def _close(self, thread: discord.Thread, prefix: str) -> None:
        self._closed.add(thread.id)
        try:
            # 改名、鎖定、封存一次做完：改名有很嚴的限速，一筆交易只改這一次
            await thread.edit(name=closed_title(thread.name, prefix), locked=True, archived=True)
        except Exception:
            self._closed.discard(thread.id)
            raise

    async def _open_trades_for(
        self, cart: discord.TextChannel, source_id: int
    ) -> list[tuple[discord.Thread, Optional[TradeRef]]]:
        """同一篇需求、還沒結束的交易 thread（含改版前的舊 thread、已被自動封存的）。"""
        found = []
        # 交易 thread 一定比需求貼文晚建立，往回翻已封存的翻到需求貼文建立時間就夠了
        async for thread in self._open_trade_threads(cart, archived_since=snowflake_time(source_id)):
            if source_id_in_title(thread.name) == source_id:
                found.append((thread, await self._ref_in(thread)))
        return found

    async def _open_trade_threads(
        self, cart: discord.TextChannel, *, archived_since: datetime
    ) -> AsyncIterator[discord.Thread]:
        """購物車裡還沒結束的交易 thread。

        discord.py 的 thread 快取只有活躍的：thread 一封存（沒人講話一段時間就自動封存）
        就被移出快取、`cart.threads` 看不到，所以還要往回翻已封存的私人 thread
        （按封存時間由新到舊），翻到 `archived_since` 為止。需要 Manage Threads 權限。"""
        seen: set[int] = set()

        def is_open(thread: discord.Thread) -> bool:
            return not thread.locked and thread.id not in self._closed and is_trade_title(thread.name)

        for thread in list(getattr(cart, "threads", None) or ()):
            seen.add(thread.id)
            if is_open(thread):
                yield thread
        try:
            async for thread in cart.archived_threads(private=True, limit=None):
                if thread.archive_timestamp < archived_since:
                    break
                if thread.id not in seen and is_open(thread):
                    seen.add(thread.id)
                    yield thread
        except discord.HTTPException:
            logger.warning("交易：讀不到購物車已封存的 thread（缺 Manage Threads 權限？）", exc_info=True)

    async def _ref_in(self, thread: discord.Thread) -> Optional[TradeRef]:
        """從開單訊息讀出交易身分（新格式看按鈕，舊格式讀文字）。"""
        async for message in thread.history(limit=10, oldest_first=True):
            if message.author.id != self.bot.user.id:
                continue
            for _, ref in _refs_on(message):
                return ref
            legacy = legacy_ref_from_text(message.content)
            if legacy is not None:
                return legacy
        return None

    def _is_active_request(self, message: discord.Message) -> bool:
        """還有效的領收通知：bot 發的、上面還有「已領收」按鈕。"""
        return message.author.id == self.bot.user.id and any(a == RECEIVE for a, _ in _refs_on(message))

    async def _pending_receipt(self, thread: discord.Thread) -> Optional[tuple[TradeRef, discord.Message]]:
        """目前有效的領收通知；需求方按過「還沒領收」就沒有（自動領收暫停）。"""
        async for message in thread.history(limit=100):
            if self._is_active_request(message):
                for action, ref in _refs_on(message):
                    if action == RECEIVE:
                        return ref, message
        return None

    def _remind_at(self, due: datetime) -> Optional[datetime]:
        before = self.settings.receipt_reminder_hours_before
        if not 0 < before < self.settings.receipt_timeout_hours:
            return None
        return due - timedelta(hours=before)

    def _reminded(self, request: discord.Message) -> bool:
        emoji = self.settings.receipt_reminded_emoji
        return any(str(r.emoji) == emoji and getattr(r, "me", False) for r in getattr(request, "reactions", None) or ())

    async def _remind_receipt(self, thread: discord.Thread, ref: TradeRef, request: discord.Message,
                              due: datetime, now: datetime) -> None:
        """到期前提醒需求方一次：讓「一直沒反應」才等於已領收。提醒過就在那則通知上按 ⏰ 當記號。"""
        hours_left = max(1, math.ceil((due - now).total_seconds() / 3600))
        await thread.send(f"⏰ <@{ref.requester_id}>，再 {hours_left} 小時將自動視為已領收。"
                          "還沒收到請按上面通知裡的「還沒領收」；有爭議可以按「請群主協助」。")
        await request.add_reaction(self.settings.receipt_reminded_emoji)

    async def _end_other_trades(self, ref: TradeRef, *, keep_thread_id: int) -> None:
        cart = await self._channel(self.settings.cart_channel_key)
        if cart is None:
            return
        for other, other_ref in await self._open_trades_for(cart, ref.source_id):
            if other.id == keep_thread_id:
                continue
            async with self._lock(other.id):
                if other.id in self._closed:
                    continue
                try:
                    who = f"<@{other_ref.requester_id}> <@{other_ref.supplier_id}> " if other_ref else ""
                    await other.send(f"{who}這篇需求已由其他供應方完成交易，此 thread 結束並鎖定。")
                    await self._close(other, ENDED_PREFIX)
                except Exception:
                    logger.error("交易：結束同一篇需求的其他交易失敗 thread=%s", other.id, exc_info=True)

    async def _archive_source(self, ref: TradeRef) -> str:
        """把需求貼文的對話複製到封存頻道（完整內容附 .txt），成功才刪除原貼文。"""
        # 同一篇需求只封存一次：兩位供應方同時完成時，後到的會發現貼文已經不在
        async with self._lock(("source", ref.source_id)):
            source = await self._get_thread(ref.source_id)
            if source is None:
                return _MISSING
            archive = await self._channel(self.settings.archive_channel_key)
            if archive is None:
                logger.error("交易：封存頻道未設定，只鎖定需求貼文 %s", ref.source_id)
                await source.edit(locked=True, archived=True)
                return _LOCKED
            try:
                transcript = await self._transcript(source)
                summary = await self._archive_summary(source, ref)
                tags = None
                if hasattr(archive, "available_tags"):  # 論壇才有標籤
                    tags = await get_forum_tags(archive, self.settings.archive_tag_name)
                # 對話放附檔：全部塞進一則訊息，超過 2000 字就發不出去
                posted = await post_to_channel(
                    archive,
                    content=summary,
                    thread_title=_fit_title(f"已封存 - {source.name}", ref.source_id),
                    tags=tags,
                    files=[discord.File(io.BytesIO(transcript.encode("utf-8")),
                                        filename=f"trade_{ref.source_id}.txt")],
                )
                if posted is None:
                    raise RuntimeError("封存頻道沒有回傳訊息")
            except Exception:
                logger.error("交易：封存需求貼文 %s 失敗，保留原貼文", ref.source_id, exc_info=True)
                return _FAILED
            try:
                await source.delete()
            except discord.HTTPException:
                logger.error("交易：需求貼文 %s 已封存，但刪除原貼文失敗", ref.source_id, exc_info=True)
                return _ARCHIVED_KEPT
            return _ARCHIVED

    async def _transcript(self, source: discord.Thread) -> str:
        messages = [m async for m in source.history(limit=self.settings.archive_history_limit, oldest_first=True)]
        # 向 API 抓回來的歷史訊息，作者不在快取時只有全域名稱；名字一律從伺服器取
        names = await self._display_names(source.guild, (m.author.id for m in messages))
        lines = [f"需求貼文：{source.name}", ""]
        for message in messages:
            when = message.created_at.astimezone(APP_TZ).strftime("%Y-%m-%d %H:%M")
            name = names.get(message.author.id) or message.author.display_name
            lines.append(f"[{when}] {name}: {message.content}")
            urls = [a.url for a in getattr(message, "attachments", None) or ()]
            if urls:
                lines.append("    附件：" + " ".join(urls))
        return "\n".join(lines)

    async def _archive_summary(self, source: discord.Thread, ref: TradeRef) -> str:
        # 封存貼文寫名字不寫 @，免得每次封存都去提醒雙方
        names = await self._display_names(source.guild, (ref.requester_id, ref.supplier_id))
        return (f"需求貼文：{source.name}\n"
                f"需求方：{names.get(ref.requester_id) or ref.requester_id}　"
                f"供應方：{names.get(ref.supplier_id) or ref.supplier_id}\n"
                f"完成時間：{datetime.now(APP_TZ):%Y-%m-%d %H:%M}\n"
                f"完整對話（最多 {self.settings.archive_history_limit} 則）見附檔。")

    async def _clear_supplier_reactions(self, ref: TradeRef) -> None:
        """取消後清掉這位供應方在需求貼文上的接單表情，之後要再接單可以重按。

        自由市場的貼文一小時沒人講話就會被自動封存，對封存中的 thread 改反應會被 Discord 拒絕，
        所以先解除封存（貼文會回到活躍列表，也剛好表示這篇需求又可以接了）。"""
        source = await self._get_thread(ref.source_id)
        if source is None:
            return
        try:
            if getattr(source, "archived", False):
                await source.edit(archived=False)
            starter = await source.fetch_message(ref.source_id)
        except discord.HTTPException:
            logger.warning("交易：清供應方表情前讀不到需求貼文 %s", ref.source_id, exc_info=True)
            return
        failed = []
        for emoji in self.settings.accept_emojis:
            try:
                await starter.remove_reaction(emoji, discord.Object(id=ref.supplier_id))
            except discord.HTTPException as exc:
                failed.append(f"{emoji}({exc.status})")
        if failed:
            logger.warning("交易：清掉供應方 %s 在需求貼文 %s 上的表情失敗：%s",
                           ref.supplier_id, ref.source_id, "、".join(failed))

    def _opening_embed(self, ref: TradeRef) -> discord.Embed:
        embed = discord.Embed(
            title="交易確認",
            description=(f"供應方 <@{ref.supplier_id}> 接下了需求方 <@{ref.requester_id}> 的需求，"
                         "請在這裡討論交易細節。"),
            color=discord.Color.gold(),
        )
        embed.add_field(name="需求貼文", value=f"<#{ref.source_id}>", inline=False)
        embed.add_field(
            name="流程",
            value=(f"供應方交付後按「通知需求方領收」，需求方收到後按「已領收」即完成；"
                   f"還沒收到可以按「還沒領收」暫停（{self.settings.receipt_timeout_hours} 小時都沒按會自動完成）。"
                   "只有供應方可以取消交易；有爭議可以按「請群主協助」。"),
            inline=False,
        )
        return embed

    async def _channel_id(self, key: str) -> Optional[int]:
        # 每次重讀（有 5 分鐘快取）：頻道是使用者在 /server_manager 綁的，bot 不重啟也可能改
        channel_id = await ChannelConfig.get_channel_id(key, caller="trade")
        if not channel_id or channel_id == ChannelConfig.DEFAULT_ID:
            return None
        return int(channel_id)

    async def _channel(self, key: str):
        channel_id = await self._channel_id(key)
        return self.bot.get_channel(channel_id) if channel_id is not None else None

    async def _get_thread(self, thread_id: int) -> Optional[discord.Thread]:
        channel = self.bot.get_channel(thread_id)
        if channel is not None:
            return channel
        try:
            # 已封存的貼文不在快取裡
            return await self.bot.fetch_channel(thread_id)
        except discord.HTTPException:
            return None

    async def _member(self, guild: Optional[discord.Guild], user_id: int) -> Optional[discord.Member]:
        """取伺服器成員；要顯示的名字一律用它的 display_name（伺服器暱稱）。

        沿用 2025-07 `b456d91` 的做法：成員快取有時候拿不到人（當時接單就因此失敗），
        所以先查快取、沒有再向 Discord API 查；API 也查不到才當作不在伺服器。"""
        if guild is None:
            return None
        member = guild.get_member(user_id)
        if member is not None:
            return member
        logger.debug("交易：快取中沒有成員 %s，改向 API 查", user_id)
        try:
            member = await guild.fetch_member(user_id)
            logger.info("交易：從 API 取得成員 %s", user_id)
            return member
        except discord.NotFound:
            logger.warning("交易：成員 %s 不在伺服器中，可能已離開伺服器", user_id)
        except discord.HTTPException:
            logger.warning("交易：向 API 查成員 %s 失敗，可能是權限或 Discord 狀態問題", user_id, exc_info=True)
        return None

    async def _display_names(self, guild: Optional[discord.Guild], user_ids) -> dict[int, str]:
        """一批使用者的伺服器暱稱（每人只查一次）；查不到的不在結果裡，由呼叫端決定怎麼顯示。"""
        names: dict[int, str] = {}
        for user_id in dict.fromkeys(user_ids):
            member = await self._member(guild, user_id)
            if member is not None:
                names[user_id] = member.display_name
        return names
