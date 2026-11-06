"""交易模組：自由市場的需求被供應方接單、或需求方在商品貼文下單後，在購物車開私人交易對話，處理領收、取消、封存。

架構定位：功能層（`services.community`）。
  - 上層（誰呼叫）：介面 `commands.forum_monitor`（接單表情、交易按鈕、領收期限的排程）、
    商品服務 `shop_service`（下單開單、交易進度上的按鈕在這裡的鎖裡做）、上線匯入（讀舊交易對話）。
  - 下層（呼叫誰）：市集資料庫 `services.market_db`（交易的正本）、交易事件的名字 `trade_progress`、
    discord（開 thread、發訊息、私訊）、`utils.discord_threads`、`utils.discord_members`、頻道設定。

角色（交易不一定是買賣，所以不叫買家賣家）：
  - 需求方（requester）：自由市場發需求的人（`/select_item` 由 bot 代發的貼文是內文裡被 @ 的人），或在商品貼文下單的人。
  - 供應方（supplier）：對需求貼文按表情接單的觀星者（Trader 身份組），或上架那篇商品的人。

介面：
  - `TradeService.handle_reaction`：供應方接單。`open_trade`：開（或沿用）一個交易對話，商品下單也走這裡。
  - `handle_button`：交易對話裡的按鈕（通知領收、取消、已領收、還沒領收、請群主協助、取消的確認）；
    `receive`（已領收：只認目前有效的那則通知，來源的 `complete_blocker` 也要同意）。
  - `run_receipt_deadlines`：領收期限（24 小時自動完成、到期前提醒一次）；`utils.due_loop` 每次醒來呼叫。
  - `locked(thread_id)`：拿著這個交易對話的鎖、回傳還在進行中的交易（結束了回 None）；
    在鎖裡用 `request_receipt_locked`／`retire_receipt_locked`／`complete_locked`／`send`／`strip_notice`；
    寫訂單的資料庫交易裡用 `supersede_receipt_tx`（加購時跟訂單一起作廢領收通知）。
  - `read(thread)` → `TradeThreadLog`：讀整串交易對話；只給上線匯入（舊交易）與交易結束時收按鈕用。
  - `add_source_kind`：登記自由市場以外的來源（商品貼文，`SourceKind`）。`ready`：上線匯入做完才開放；
    匯入期間的接單表情先記著，匯入做完 `replay_deferred` 補開。

規則：
  - 交易的正本在資料庫：誰是需求方與供應方、進行中或結束、領收通知在等誰，全部查資料庫，不翻 Discord。
    每次動作先寫資料庫，成功後才發 Discord；按鈕的 custom_id 只用來找到元件，身分照資料庫。
  - 同一個交易對話的動作排隊（`locked`）；鎖不能重入，鎖裡只呼叫 `*_locked`。商品那邊的鎖要先拿：
    商品鎖 → 交易鎖，反過來會卡死。
  - 只 @ 下一步要動手的人：每次發訊息都明確指定 `allowed_mentions`；交易結束時對話裡不 @、改私訊雙方。
  - 只有供應方與群主能取消（避免需求方受領服務後擅自取消）；來源說有已收的款時先跳確認。
  - 同一篇需求可以有多位供應方，各開一個對話；一位完成後需求貼文封存刪除，其他人的對話一併結束。
    商品貼文成交後保留，可以賣給很多人，取消時把沒交付的數量還回去（由來源種類處理）。

例外與決策：
  - 按鈕長什麼樣子屬於 Discord 介面，由 `commands.forum_monitor` 以 `make_view` 交進來；這裡不 import 指令層
    （互相 import 會循環）。
  - 舊按鈕（`forum_trade_confirm`、`trade:動作:來源:需求方:供應方`）照樣能按：custom_id 帶的身分不用，
    一律用按鈕所在的交易對話去查資料庫。
  - 上線前開的舊交易（`legacy`）沒有交易進度，「通知需求方領收」照舊直接發領收通知、不檢查付款。
  - 結束時資料庫先記狀態、再做 Discord 那邊的收尾，做完才記 `wrapped_up`；中途重啟的由領收期限的排程補做
    （留底與封存需求貼文做過會記一筆，不重做；結束訊息與私訊可能重複一次）。
"""
from __future__ import annotations

import asyncio
import contextlib
import io
import json
import logging
import math
import re
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Any, AsyncIterator, Awaitable, Callable, Iterator, Optional, Protocol, Sequence

import discord
from discord.utils import snowflake_time

from services.community import trade_progress as tp
from services.market_db import MarketDB, TradeEventRow, TradeRow, get_shared_market_db
from sys_settings.time_settings import APP_TZ
from sys_settings.trade_settings import TradeSettings
from utils.discord_content import DISCORD_MESSAGE_LIMIT, get_forum_tags, post_to_channel, send_model_text
from utils.discord_members import check_role, resolve_member
from utils.discord_threads import fetch_thread, reopen_thread
from utils.dm_notifier import send_dm
from utils.utils import ChannelConfig, safe_send_interaction_message

logger = logging.getLogger(__name__)

# ── 按鈕動作 ──
NOTIFY = "notify"        # 供應方：通知需求方領收（商品交易＝剩下的品項一起交付）
CANCEL = "cancel"        # 供應方或群主：取消交易
CANCEL_OK = "cancelok"   # 取消的確認畫面：確定取消
KEEP = "keep"            # 取消的確認畫面：返回
RECEIVE = "receive"      # 需求方：已領收
HOLD = "hold"            # 需求方：還沒領收（暫停自動領收）
HELP = "help"            # 雙方：請群主協助
_SUPPLIER_ACTIONS = (NOTIFY,)
_CANCEL_ACTIONS = (CANCEL, CANCEL_OK, KEEP)
_REQUESTER_ACTIONS = (RECEIVE, HOLD)

#: 交易按鈕 custom_id 的格式；forum_monitor 的 DynamicItem 用同一個 template 解析。
#: 身分欄位只為了相容已經發出去的按鈕，處理時一律查資料庫
CUSTOM_ID_TEMPLATE = (
    r"trade:(?P<action>notify|cancel|cancelok|keep|receive|hold|help)"
    r":(?P<source>\d+):(?P<requester>\d+):(?P<supplier>\d+)"
)
_CUSTOM_ID_RE = re.compile(CUSTOM_ID_TEMPLATE)
#: 交易對話裡所有屬於交易的按鈕都用這個開頭（含商品交易進度上的），交易結束時一起收掉
BUTTON_PREFIX = "trade:"

# ── 交易狀態（trades.status）──
OPEN = "open"
COMPLETED = "completed"
CANCELLED = "cancelled"
ENDED = "ended"

# ── 交易對話標題：「前綴 需求方 與 供應方 - 來源貼文id」──
OPEN_PREFIX = "【交易中】"
COMPLETED_PREFIX = "【已完成】"
CANCELLED_PREFIX = "【已取消】"
ENDED_PREFIX = "【已結束】"  # 同一篇需求由別的供應方完成
#: 改版前的標題「交易確認 - 需求方 和 供應方 - 需求貼文id」
LEGACY_PREFIX = "交易確認 - "
_TITLE_LIMIT = 100

#: 改版前開單訊息的文字與按鈕（forum_monitor.LegacyTransactionView）。上線匯入靠它認出舊交易；舊交易都結束後可刪。
#: 舊文字裡「使用者」是按表情的人（供應方），「貼文者」是被 @ 的人（需求方）。
_LEGACY_BUTTON_IDS = ("forum_trade_confirm", "forum_trade_cancel")
_LEGACY_RE = re.compile(
    r"使用者 <@!?(?P<supplier>\d+)> 對交易貼文.*?貼文者為 <@!?(?P<requester>\d+)>.*?來源貼文 ID: (?P<source>\d+)",
    re.DOTALL,
)

NOT_READY_TEXT = "商品與交易功能更新中，請稍後再試。"
#: 交易結束多久之後還沒收尾完，就當成做到一半被打斷、由排程補做（剛結束的可能還在做）
WRAP_UP_GRACE = timedelta(minutes=10)
NO_RECORD_TEXT = "找不到這筆交易的紀錄，請截圖通知管理員。"
#: 匯入期間記下的接單表情（資料庫 meta 的鍵）
DEFERRED_META = "deferred_reactions"


@dataclass(frozen=True)
class _SavedReaction:
    """記進資料庫的接單表情（補開時代替 Discord 的表情事件；沒有成員資料，補開時再查）。"""

    guild_id: int
    channel_id: int
    message_id: int
    user_id: int
    emoji: str
    member: None = None


def _deferred_key(payload) -> tuple[int, int, str]:
    return payload.channel_id, payload.user_id, str(payload.emoji)


def _saved(payload) -> _SavedReaction:
    return _SavedReaction(payload.guild_id, payload.channel_id, payload.message_id, payload.user_id, str(payload.emoji))

# 封存需求貼文的結果
_ARCHIVED = "archived"
_ARCHIVED_KEPT = "archived_kept"  # 已複製到封存頻道，但刪除原貼文失敗
_MISSING = "missing"    # 需求貼文已經不在（被刪、或別的供應方完成時已封存）
_LOCKED = "locked"      # 封存頻道沒設定，只鎖定需求貼文
_FAILED = "failed"      # 複製失敗，保留原貼文
_FOREIGN = "foreign"    # 來源不在自由市場，不封存、不刪、不結束其他交易
_LOCK_FAILED = "lock_failed"  # 封存頻道沒設定，連鎖定需求貼文都失敗
# 給群友看的只說結果、要不要通知管理員；原因寫在 log
_ARCHIVE_NOTE = {
    _ARCHIVED: "需求貼文已封存。",
    _ARCHIVED_KEPT: "需求貼文沒能自動移除，請通知管理員。",
    _MISSING: "",
    _LOCKED: "需求貼文已鎖定。",
    _FAILED: "需求貼文沒能自動封存，請通知管理員。",
    _FOREIGN: "",
    _LOCK_FAILED: "需求貼文沒能自動鎖定，請通知管理員。",
}


@dataclass(frozen=True)
class TradeRef:
    """一筆交易的身分（來源貼文、需求方、供應方）；只用來組按鈕的 custom_id，處理時以資料庫為準。"""

    source_id: int
    requester_id: int
    supplier_id: int

    def custom_id(self, action: str) -> str:
        return f"trade:{action}:{self.source_id}:{self.requester_id}:{self.supplier_id}"


def ref_of(trade: TradeRow) -> TradeRef:
    return TradeRef(trade.source_id, trade.requester_id, trade.supplier_id)


@dataclass(frozen=True)
class OpenedTrade:
    thread: discord.Thread
    #: False＝同一組已經有進行中的對話，沿用它
    created: bool
    supplier: discord.Member
    trade: TradeRow
    #: `open_trade` 的 record 回傳的東西（例：這次下單的事件編號）
    recorded: Any = None


class SourceKind(Protocol):
    """自由市場以外的交易來源（例：商品貼文）。自由市場的需求貼文是預設，不用實作這個。"""

    #: 資料庫 trades.source_kind 的值
    name: str
    #: 開單訊息裡指向來源的欄位名稱，例「商品貼文」
    label: str

    async def opening(self, ref: TradeRef) -> tuple[str, str]:
        """開單訊息的（說明, 流程）。"""

    async def deliver_rest(self, thread: discord.Thread, trade: TradeRow, actor_id: int) -> Optional[str]:
        """供應方按「通知需求方領收」（在交易鎖裡）：做完回 None，不能做回給他看的理由。舊交易不會叫這個。"""

    async def complete_blocker(self, trade: TradeRow) -> Optional[str]:
        """領收（手動或自動）前的最後一道檢查：還有沒交付的就回理由、不能完成；可以就回 None。"""

    async def on_complete(self, thread: discord.Thread, trade: TradeRow) -> str:
        """交易完成時處理來源；回傳要加在完成訊息裡的說明（可以是空字串）。"""

    async def cancel_summary(self, trade: TradeRow) -> Optional[str]:
        """有已收的款時，取消前確認畫面上要列的內容；沒有就回 None（直接取消）。"""

    async def cancel_note(self, trade: TradeRow) -> str:
        """取消訊息與私訊後面要接的提醒（例：「⚠️ 定金已付…請雙方記得處理後續」）；沒有回空字串。"""

    async def on_cancel_tx(self, db: MarketDB, trade: TradeRow) -> None:
        """取消的資料庫交易裡（跟交易狀態一起寫）：例如把沒交付的數量還回去。"""

    async def after_cancel(self, trade: TradeRow) -> None:
        """取消、對話鎖定之後（在交易鎖外）：例如重畫商品貼文的剩餘數量。"""


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


_MENTION_RE = re.compile(r"<@!?(\d+)>")


def mentions_to_names(text: str, names: dict[int, str]) -> str:
    """把 <@id> 換成 @名字：封存與留底要看得懂是誰，也不能在發封存時又通知到人。"""
    return _MENTION_RE.sub(lambda m: f"@{names.get(int(m[1])) or m[1]}", text or "")


def mention_only(*user_ids: int) -> discord.AllowedMentions:
    """只 @ 這幾個人（全域預設會 @ 訊息裡寫到的每個人）；不給人＝誰都不 @。"""
    return discord.AllowedMentions(everyone=False, roles=False, replied_user=False,
                                   users=[discord.Object(id=i) for i in user_ids])


def _fit_title(head: str, source_id: int) -> str:
    """標題上限 100 字；太長時截掉前段，保住結尾的來源貼文 id（認舊交易的來源靠它）。"""
    tail = f" - {source_id}"
    return head[: _TITLE_LIMIT - len(tail)] + tail


def open_title(requester_name: str, supplier_name: str, source_id: int) -> str:
    return _fit_title(f"{OPEN_PREFIX}{requester_name} 與 {supplier_name}", source_id)


def closed_title(title: str, prefix: str) -> str:
    base = title
    for known in (OPEN_PREFIX, COMPLETED_PREFIX, CANCELLED_PREFIX, ENDED_PREFIX):
        if base.startswith(known):
            base = base[len(known):]
            break
    head, sep, tail = base.rpartition(" - ")
    if not sep or not tail.isdigit():
        return (prefix + base)[:_TITLE_LIMIT]
    return _fit_title(prefix + head, int(tail))


def source_id_in_title(title: str) -> Optional[int]:
    _, sep, tail = title.rpartition(" - ")
    return int(tail) if sep and tail.isdigit() else None


def is_trade_title(title: str) -> bool:
    return title.startswith(OPEN_PREFIX) or title.startswith(LEGACY_PREFIX)


def _button_ids(message: discord.Message) -> list[str]:
    return [getattr(child, "custom_id", None) or ""
            for row in getattr(message, "components", None) or ()
            for child in getattr(row, "children", None) or ()]


def _refs_on(message: discord.Message) -> Iterator[tuple[str, TradeRef]]:
    """訊息上的交易按鈕（動作, 交易身分）。"""
    for custom_id in _button_ids(message):
        parsed = parse_custom_id(custom_id)
        if parsed:
            yield parsed


def is_active_request(message: discord.Message, *, bot_user_id: int) -> bool:
    """舊交易對話裡還有效的領收通知：bot 發的、上面還有「已領收」按鈕（只給上線匯入認舊交易用）。"""
    return message.author.id == bot_user_id and any(a == RECEIVE for a, _ in _refs_on(message))


@dataclass(frozen=True)
class TradeThreadLog:
    """讀出來的一整串交易對話（由舊到新）。交易的狀態在資料庫；這裡只給兩種用途：

    - 上線匯入讀舊交易：`ref`（開單訊息上的身分，新格式看按鈕、舊格式讀文字）、`pending_receipt()`、`bot_messages()`。
    - 交易結束時收按鈕：`button_messages()`（bot 發的、帶交易按鈕的訊息，含商品的交易進度）。
    """

    messages: tuple[discord.Message, ...]
    bot_user_id: int

    def bot_messages(self) -> list[discord.Message]:
        return [m for m in self.messages if m.author.id == self.bot_user_id]

    @property
    def ref(self) -> Optional[TradeRef]:
        for message in self.bot_messages():
            for _, ref in _refs_on(message):
                return ref
            legacy = legacy_ref_from_text(message.content)
            if legacy is not None:
                return legacy
        return None

    def opening(self) -> Optional[discord.Message]:
        """開單訊息：第一則帶交易身分的 bot 訊息。"""
        for message in self.bot_messages():
            if any(True for _ in _refs_on(message)) or legacy_ref_from_text(message.content) is not None:
                return message
        return None

    def active_requests(self) -> list[discord.Message]:
        """由新到舊。"""
        return [m for m in reversed(self.messages) if is_active_request(m, bot_user_id=self.bot_user_id)]

    def pending_receipt(self) -> Optional[discord.Message]:
        requests = self.active_requests()
        return requests[0] if requests else None

    def button_messages(self) -> list[discord.Message]:
        return [m for m in self.bot_messages()
                if any(i.startswith(BUTTON_PREFIX) or i in _LEGACY_BUTTON_IDS for i in _button_ids(m))]


async def read_trade_thread(thread: discord.Thread, *, bot_user_id: int) -> TradeThreadLog:
    """讀整串交易對話。一律讀完：開單訊息在最舊那端，只讀一部分曾經漏掉第一筆訂單。"""
    return TradeThreadLog(tuple([m async for m in thread.history(limit=None, oldest_first=True)]), bot_user_id)


@dataclass(frozen=True)
class ReceiptState:
    """領收通知的現況（從事件算）：目前有效的那則通知、到期前提醒過沒。"""

    request: Optional[TradeEventRow]
    reminded: bool

    @property
    def since(self) -> Optional[datetime]:
        return datetime.fromisoformat(self.request.created_at) if self.request else None


def receipt_state(events: Sequence[TradeEventRow]) -> ReceiptState:
    """最新那則領收通知算數；之後有「還沒領收」（或被加購作廢）就沒有有效的通知。"""
    request, reminded = None, False
    for event in events:
        if event.kind == tp.RECEIPT_REQUESTED:
            request, reminded = event, False
        elif event.kind == tp.RECEIPT_HELD:
            request, reminded = None, False
        elif event.kind == tp.RECEIPT_REMINDED and request is not None:
            reminded = True
    return ReceiptState(request, reminded)


class TradeService:
    def __init__(
        self,
        bot: discord.Client,
        *,
        make_view: Callable[[TradeRef, Sequence[str]], discord.ui.View],
        settings: Optional[TradeSettings] = None,
        db: Optional[Callable[[], Awaitable[MarketDB]]] = None,
        now: Optional[Callable[[], datetime]] = None,
    ):
        self.bot = bot
        self.settings = settings or TradeSettings()
        self._make_view = make_view
        self._db = db or get_shared_market_db
        self._now = now or (lambda: datetime.now(APP_TZ))
        # 同一筆交易的按鈕可能被連按、或和期限檢查同時到；鎖住後再查一次資料庫
        self._locks: dict[object, asyncio.Lock] = {}
        self._kinds: dict[str, SourceKind] = {}
        #: 上線匯入做完才開放按鈕與接單（匯入時要翻舊交易對話，中途開新單會重複）
        self.ready = asyncio.Event()
        #: 匯入還沒做完時收到的接單表情（也記進資料庫：匯入失敗、修好前重啟過也補得回來）
        self._deferred: list = []
        #: 匯入期間已經私訊說過「接單記下了」的 (供應方, 需求貼文)
        self._deferred_told: set[tuple[int, int]] = set()
        #: 這次啟動檢查過停機期間被刪掉的交易對話了沒
        self._deleted_checked = False
        #: 沒開成的交易對話已經說過一次的（鎖不起來時下一輪只重試鎖定，不再發同一句）
        self._orphans_told: set[int] = set()
        #: 上線匯入做完的時刻（匯入設定）：這之後開的交易對話、商品貼文一定有資料庫紀錄，沒有的就是做到一半中斷的
        self.orphans_after: Optional[datetime] = None
        #: 接單開出新對話後要再發的東西（介面層交進來，例：供應方的物品價格表）
        self.on_reaction_opened: Optional[Callable[[OpenedTrade], Awaitable[None]]] = None

    async def replay_deferred(self) -> int:
        """匯入做完後補處理匯入期間的接單表情（記憶體裡的，加上資料庫裡記下的：修好前重啟過也補得回來）；
        回傳補開了幾個對話。表情之後被拿掉的不開（匯入失敗可能拖好幾天）。"""
        pending, self._deferred = self._deferred, []
        db = await self.db()
        seen = {_deferred_key(p) for p in pending}
        for entry in json.loads(await db.get_meta(DEFERRED_META) or "[]"):
            saved = _SavedReaction(**entry)
            if _deferred_key(saved) not in seen:
                seen.add(_deferred_key(saved))
                pending.append(saved)
        opened = 0
        failed = []
        for payload in pending:
            try:
                if not await self._still_reacted(payload):
                    logger.info("交易：匯入期間的接單表情已經拿掉，不補開（需求貼文 %s、使用者 %s）",
                                payload.channel_id, payload.user_id)
                    continue
                result = await self.handle_reaction(payload, replaying=True)
                opened += bool(result and result.created)
            except Exception:  # 邊界：一個表情補開失敗不影響其他的；留著下次啟動再補（私訊說過不用重按）
                logger.error("交易：補處理接單表情失敗 需求貼文=%s", payload.channel_id, exc_info=True)
                failed.append(asdict(_saved(payload)))
        async with db.transaction():
            await db.set_meta(DEFERRED_META, json.dumps(failed))
        return opened

    async def _still_reacted(self, payload) -> bool:
        """這位供應方現在還有沒有在需求貼文上按著那個表情。貼文或第一則訊息確定不在了回 False；
        Discord 暫時出錯就往外丟（留著下次再補，私訊說過不用重按）。"""
        source = await self.get_thread(payload.channel_id, raise_errors=True)
        if source is None:
            return False
        try:
            starter = await source.fetch_message(payload.message_id)
        except discord.NotFound:
            return False
        for reaction in getattr(starter, "reactions", None) or ():
            if str(reaction.emoji) == str(payload.emoji):
                async for user in reaction.users():
                    if user.id == payload.user_id:
                        return True
        return False

    async def _defer_reaction(self, payload, source: discord.Thread) -> None:
        """匯入還沒做完時的接單表情：記下來（記憶體＋資料庫），匯入做完再補開；私訊供應方說一聲，不然他看不出有沒有接到。"""
        self._deferred.append(payload)
        entry = asdict(_saved(payload))
        try:
            db = await self.db()
            async with db.transaction():
                saved = json.loads(await db.get_meta(DEFERRED_META) or "[]")
                if entry not in saved:
                    await db.set_meta(DEFERRED_META, json.dumps(saved + [entry]))
        except Exception:  # 邊界：記不進資料庫就只留在記憶體（這次沒重啟照樣補開），私訊照發
            logger.warning("交易：匯入期間的接單表情記不進資料庫 需求貼文=%s", source.id, exc_info=True)
        told = (payload.user_id, source.id)
        if told in self._deferred_told:
            return
        self._deferred_told.add(told)
        member = payload.member or await self.member(self.bot.get_guild(payload.guild_id), payload.user_id)
        if member is not None:
            await send_dm(member, content=f"交易功能正在更新，你在「{source.name}」的接單已經記下了，"
                                          "更新完成後會自動開交易對話，不用重按。")

    def add_source_kind(self, kind: SourceKind) -> None:
        """登記自由市場以外的交易來源（商品上架的 cog 載入時呼叫）。"""
        self._kinds[kind.name] = kind

    def kind_of(self, trade: TradeRow) -> Optional[SourceKind]:
        """交易屬於哪一種來源；None＝自由市場的需求貼文（或來源模組沒載入）。"""
        return self._kinds.get(trade.source_kind)

    async def db(self) -> MarketDB:
        return await self._db()

    def now(self) -> datetime:
        return self._now()

    def stamp(self) -> str:
        return self._now().isoformat()

    # ── 入口：供應方對需求貼文按表情 ──

    async def handle_reaction(self, payload: discord.RawReactionActionEvent, *,
                              replaying: bool = False) -> Optional[OpenedTrade]:
        """供應方接單：對自由市場貼文本身按表情。不符合條件的反應一律略過（回 None）。
        replaying＝補開匯入期間記下的：取需求貼文碰到 Discord 暫時出錯就往外丟（留著下次再補，不能當成不符條件丟掉）。"""
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
        source = await self.get_thread(payload.channel_id, raise_errors=replaying)
        if source is None or getattr(source, "parent_id", None) != forum_id:
            return None

        guild = self.bot.get_guild(payload.guild_id)
        # 表情事件本身帶著 Discord 當下送來的成員資料（含伺服器暱稱與身份組，不是快取）；
        # 沒帶才走快取 → API
        supplier = payload.member or await self.member(guild, payload.user_id, raise_errors=replaying)
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
        requester = await self.member(guild, requester_id, raise_errors=replaying)
        if requester is None or requester.bot:
            logger.info("交易：需求方 %s 不在伺服器裡或是 bot，不開單（需求貼文 %s）", requester_id, source.id)
            return None
        if not self.ready.is_set():
            # 匯入時要翻舊交易對話，中途開新單會重複；先記下來，匯入做完再補開（`replay_deferred`）。
            # 身分都檢查過才記（不然會跟不能接單的人說「記下了」）
            logger.info("交易：上線匯入還沒做完，接單表情先記下（需求貼文 %s、使用者 %s）", source.id, payload.user_id)
            await self._defer_reaction(payload, source)
            return None
        opened = await self.open_trade(source, requester, supplier)
        if opened is not None and opened.created and self.on_reaction_opened is not None:
            try:
                await self.on_reaction_opened(opened)
            except Exception:  # 邊界：對話已經開好，附帶的訊息發不出去不影響接單
                logger.error("交易：接單後的附帶訊息發送失敗 thread=%s", opened.thread.id, exc_info=True)
        return opened

    async def open_trade(
        self, source: discord.Thread, requester: discord.Member, supplier: discord.Member,
        *, kind: Optional[SourceKind] = None,
        record: Optional[Callable[[MarketDB, int, bool], Awaitable[Any]]] = None,
        after: Optional[Callable[[discord.Thread, TradeRow, Any, bool], Awaitable[None]]] = None,
    ) -> Optional[OpenedTrade]:
        """為（來源貼文, 需求方, 供應方）開一個私人交易對話；同一組已經有進行中的就沿用。

        record(db, 交易編號, 是不是新開的)：在寫交易的同一個資料庫交易裡記來源自己的資料（例：這次下單的品項），
        失敗就整個撤回（新開的對話也刪掉）。after(對話, 交易, record 的結果, 是不是新開的)：資料庫寫好之後、
        還拿著這個交易對話的鎖時發來源自己的訊息（例：訂單明細、交易進度）；它失敗時交易照樣成立、只記 log，
        之後的動作會重畫。沿用既有對話時沒給 after 就只提醒供應方在這裡繼續。"""
        cart = await self._channel(self.settings.cart_channel_key)
        if cart is None:
            logger.error("交易：購物車頻道未設定或找不到，無法開交易對話（來源 %s）", source.id)
            return None
        db = await self.db()
        async with self._lock(("open", source.id, requester.id, supplier.id)):
            # 同一組＝同一篇來源、同一位需求方、同一位供應方：商品貼文是很多需求方對同一位供應方，
            # 只看供應方會把不同人的單混進同一個對話
            for trade in await db.trades(source_id=source.id, requester_id=requester.id,
                                         supplier_id=supplier.id, status=OPEN):
                if trade.legacy and record is not None:
                    continue  # 上線前的舊交易沒有交易進度：新的訂單另開對話，才走得了付款與交付
                async with self.locked(trade.id) as current:
                    if current is None:
                        continue  # 剛好被取消或完成：不能再收訂單
                    # 只有真的不存在才另開；沒權限或 Discord 5xx 往外丟（下單失敗、請對方再試），免得同一組開出兩個對話
                    thread = await fetch_thread(self.bot, current.id, raise_errors=True)
                    if thread is None:
                        logger.warning("交易：資料庫裡進行中的交易 %s 找不到交易對話，改開新的", current.id)
                        continue
                    recorded = None
                    if record is not None:
                        async with db.transaction():
                            recorded = await record(db, current.id, False)
                    if after is not None:
                        await self._after(after, thread, current, recorded, False)
                    else:
                        await self.send(thread, f"{supplier.mention}，這筆交易還在進行中，請在這裡繼續。",
                                        mention=(supplier.id,))
                    return OpenedTrade(thread, False, supplier, current, recorded)

            ref = TradeRef(source.id, requester.id, supplier.id)
            description, flow = await kind.opening(ref) if kind is not None else self._forum_opening(ref)
            thread = await cart.create_thread(
                name=open_title(requester.display_name, supplier.display_name, source.id),
                type=discord.ChannelType.private_thread,
                invitable=False,  # 只有需求方和這位供應方，不讓人再邀別人進來
                # 購物車頻道預設 3 天沒人講話就封存；拉到最長，封存了 bot 發訊息時會再打開
                auto_archive_duration=10080,
                reason=f"交易：來源 {source.id}，需求方 {requester.id}，供應方 {supplier.id}",
            )
            created = False
            try:
                await thread.add_user(requester)
                await thread.add_user(supplier)
                opening = await thread.send(
                    content=f"{requester.mention} {supplier.mention}",
                    embed=self._opening_embed(ref, kind, description, flow),
                    view=self._make_view(ref, (NOTIFY, CANCEL, HELP)),
                    allowed_mentions=mention_only(requester.id, supplier.id),
                )
                async with db.transaction():
                    await db.insert_trade(id=thread.id, source_kind=kind.name if kind else "forum",
                                          source_id=source.id, requester_id=requester.id,
                                          supplier_id=supplier.id, now=self.stamp())
                    await db.add_event(thread.id, tp.OPENED, now=self.stamp(), actor_id=supplier.id,
                                       message_id=opening.id)
                    recorded = await record(db, thread.id, True) if record is not None else None
                created = True
            finally:
                if not created:
                    # 資料庫沒有這筆交易，對話留著只會有一串按了沒反應的按鈕
                    with contextlib.suppress(discord.HTTPException):
                        await thread.delete()
            trade = await db.get_trade(thread.id)
            if after is not None:
                async with self._lock(thread.id):
                    await self._after(after, thread, trade, recorded, True)
            logger.info("交易：開單 thread=%s 來源=%s(%s) 需求方=%s 供應方=%s",
                        thread.id, source.id, trade.source_kind, requester.id, supplier.id)
            return OpenedTrade(thread, True, supplier, trade, recorded)

    async def _after(self, after, thread, trade, recorded, created: bool) -> None:
        try:
            await after(thread, trade, recorded, created)
        except Exception:  # 邊界：交易已經寫進資料庫，來源自己的訊息發失敗不影響交易成立，之後的動作會重畫
            logger.error("交易：開單後發來源的訊息失敗 thread=%s", thread.id, exc_info=True)

    # ── 入口：交易對話裡的按鈕 ──

    async def handle_button(self, interaction: discord.Interaction, action: str, ref: Optional[TradeRef]) -> None:
        """ref 只是按鈕上寫的；身分一律照按鈕所在的交易對話查資料庫。"""
        if not self.ready.is_set():
            await self._ephemeral(interaction, NOT_READY_TEXT)
            return
        thread = interaction.channel
        trade = await (await self.db()).get_trade(getattr(thread, "id", 0))
        if trade is None:
            logger.warning("交易：按鈕 %s 所在的對話 %s 沒有交易紀錄（按鈕上寫 %s）",
                           action, getattr(thread, "id", None), ref)
            await self._ephemeral(interaction, NO_RECORD_TEXT)
            return
        user_id = interaction.user.id
        if action in _SUPPLIER_ACTIONS and user_id != trade.supplier_id:
            await self._ephemeral(interaction, f"只有供應方 <@{trade.supplier_id}> 可以操作這個按鈕。")
            return
        if action in _CANCEL_ACTIONS and not self.can_cancel(trade, interaction.user, thread):
            await self._ephemeral(interaction, f"只有供應方 <@{trade.supplier_id}> 或群主可以取消交易。")
            return
        if action in _REQUESTER_ACTIONS and user_id != trade.requester_id:
            await self._ephemeral(interaction, f"只有需求方 <@{trade.requester_id}> 可以操作這個按鈕。")
            return
        if action == HELP and user_id not in (trade.requester_id, trade.supplier_id):
            await self._ephemeral(interaction, "只有這筆交易的雙方可以請群主協助。")
            return
        if action == KEEP:
            await interaction.response.edit_message(content="沒有取消，交易照常進行。", view=None)
            return
        if trade.status != OPEN or getattr(thread, "locked", False):
            await self._ephemeral(interaction, "這筆交易已經結束。")
            return
        try:
            if action == CANCEL:
                summary = await self._cancel_summary(trade)
                if summary:
                    # 有已收的款：先確認，等了幾個月的對話不該誤按一次就沒了
                    await self._ephemeral(
                        interaction,
                        f"這筆交易有已收的款：\n{summary}\n取消後對話會關閉、不能復原，錢要由雙方自己處理。確定要取消嗎？",
                        view=self._make_view(ref_of(trade), (CANCEL_OK, KEEP)))
                    return
            if action == CANCEL_OK:
                await interaction.response.edit_message(content="處理中……", view=None)
            elif not interaction.response.is_done():
                await interaction.response.defer()
            if action == NOTIFY:
                reason = await self.notify(thread, trade.id, actor_id=user_id)
                if reason:
                    await self._ephemeral(interaction, reason)
            elif action in (CANCEL, CANCEL_OK):
                cancelled = await self.cancel(thread, trade.id, actor=interaction.user)
                if action == CANCEL_OK:
                    await interaction.edit_original_response(
                        content="已取消這筆交易。" if cancelled else "這筆交易剛好已經結束，沒有取消。")
            elif action == HOLD:
                reason = await self.hold_receipt(thread, trade.id, interaction.message)
                if reason:
                    await self._ephemeral(interaction, reason)
            elif action == HELP:
                if not await self.call_owner(thread, trade, interaction.user):
                    await self._ephemeral(interaction, "群主已經在這個對話裡了。")
            elif action == RECEIVE:
                reason = await self.receive(thread, trade.id, interaction.message)
                if reason:
                    await self._ephemeral(interaction, reason)
        except Exception:  # 邊界：一次按鈕互動，做壞了要回按的人一句，不讓互動顯示失敗
            logger.error("交易：處理按鈕 %s 失敗 thread=%s", action, thread.id, exc_info=True)
            await self._ephemeral(interaction, "處理交易時發生錯誤，請截圖通知管理員。")

    def can_cancel(self, trade: TradeRow, user, thread=None) -> bool:
        """供應方或群主（供應方離開或一直不回時，對話才不會永遠卡著）。"""
        owner_id = getattr(getattr(thread, "guild", None), "owner_id", None)
        return user.id == trade.supplier_id or (owner_id is not None and user.id == owner_id)

    async def _cancel_summary(self, trade: TradeRow) -> Optional[str]:
        kind = self.kind_of(trade)
        return await kind.cancel_summary(trade) if kind is not None else None

    async def notify(self, thread: discord.Thread, trade_id: int, *, actor_id: int) -> Optional[str]:
        """供應方按「通知需求方領收」。商品交易（上線後開的）＝剩下的品項一起交付，由來源判斷能不能；
        自由市場與舊交易直接發領收通知。不能做回理由。"""
        async with self.locked(trade_id) as trade:
            if trade is None:
                return None
            kind = self.kind_of(trade)
            if kind is not None and not trade.legacy:
                return await kind.deliver_rest(thread, trade, actor_id)
            # 舊交易照舊流程直接發領收通知；來源不准完成（例：【定金】商品還沒改成定金＋尾款）就先不發
            blocker = await kind.complete_blocker(trade) if kind is not None else None
            if blocker:
                return blocker
            await self.request_receipt_locked(thread, trade)
            return None

    async def request_receipt_locked(self, thread: discord.Thread, trade: TradeRow) -> None:
        """發領收通知（要拿著這個交易的鎖）：舊的通知先失效，期限從這則起算。

        先記事件（訊息編號空著）再發，發出去才補上編號：沒發出去就讓它失效；剛好在中間停機的（記了、沒發），
        領收期限的排程過一陣子補發一則新的。訊息編號空著的通知不會被自動領收。"""
        await self.retire_receipt_locked(thread, trade, "（已由新的通知取代）")
        hours = self.settings.receipt_timeout_hours
        db = await self.db()
        async with db.transaction():
            event_id = await db.add_event(trade.id, tp.RECEIPT_REQUESTED, now=self.stamp(),
                                          actor_id=trade.supplier_id)
        try:
            message = await self.send(
                thread,
                f"<@{trade.requester_id}>，供應方 <@{trade.supplier_id}> 已通知交付完成。"
                "收到後請按「已領收」；還沒收到請按「還沒領收」，自動領收會暫停。"
                f"{hours} 小時內都沒有按，將自動視為已領收。",
                view=self._make_view(ref_of(trade), (RECEIVE, HOLD, HELP)),
                mention=(trade.requester_id,),
            )
        except discord.HTTPException as exc:
            # Discord 明確拒絕（沒權限、對話不在了）＝確定沒發出去、再發也一樣：讓它失效。其他情況（Discord 自己
            # 出錯、停機時被取消、連線斷了）不知道發了沒、晚點可能就好了：留著訊息編號空著的紀錄，由期限排程補發新的
            if not isinstance(exc, discord.DiscordServerError):
                async with db.transaction():
                    await db.add_event(trade.id, tp.RECEIPT_HELD, now=self.stamp(), reference="unsent")
            raise
        async with db.transaction():
            await db.set_event_message(event_id, message.id)

    async def supersede_receipt_tx(self, db: MarketDB, trade_id: int) -> Optional[int]:
        """在呼叫端的資料庫交易裡讓目前有效的領收通知失效（例：跟加購的訂單一起寫），回傳那則通知的訊息編號
        （呼叫端之後拿掉上面的按鈕）；沒有有效的通知回 None。"""
        state = receipt_state(await db.events(trade_id))
        if state.request is None:
            return None
        await db.add_event(trade_id, tp.RECEIPT_HELD, now=self.stamp(), reference="superseded")
        return state.request.message_id

    async def strip_notice(self, thread: discord.Thread, message_id: Optional[int], note: str) -> None:
        """在一則已經失效的通知後面加一行說明、拿掉按鈕（找不到就算了）。"""
        await self._strip_message(thread, message_id, note)

    async def retire_receipt_locked(self, thread: discord.Thread, trade: TradeRow, note: str) -> bool:
        """讓目前有效的領收通知失效（要拿著這個交易的鎖）：記一筆事件、拿掉那則通知上的按鈕。沒有就回 False。"""
        db = await self.db()
        state = receipt_state(await db.events(trade.id))
        if state.request is None:
            return False
        async with db.transaction():
            await db.add_event(trade.id, tp.RECEIPT_HELD, now=self.stamp(), reference="superseded")
        await self._strip_message(thread, state.request.message_id, note)
        return True

    async def hold_receipt(self, thread: discord.Thread, trade_id: int,
                           message: Optional[discord.Message]) -> Optional[str]:
        """需求方說還沒領收：那則通知失效（自動領收暫停），請供應方交付後再通知一次。
        按到失效的通知上的按鈕不算，回給他看的說明（不然他以為暫停了，有效的那則還在倒數）。"""
        async with self.locked(trade_id) as trade:
            if trade is None:
                return "這筆交易已經結束。"
            db = await self.db()
            state = receipt_state(await db.events(trade.id))
            if state.request is None or message is None or state.request.message_id != message.id:
                return "這則領收通知已經失效，請看對話裡最新的通知。"
            async with db.transaction():
                await db.add_event(trade.id, tp.RECEIPT_HELD, now=self.stamp(), actor_id=trade.requester_id,
                                   reference="held")
            await self._strip_message(thread, message.id, "（需求方表示還沒領收，自動領收已暫停）", message=message)
            await self.send(thread, f"<@{trade.supplier_id}>，需求方 <@{trade.requester_id}> 表示還沒領收，"
                                    "自動領收已暫停。交付後請再按一次「通知需求方領收」；有爭議可以按「請群主協助」。",
                            mention=(trade.supplier_id,))
        logger.info("交易：需求方表示還沒領收 thread=%s", thread.id)
        return None

    async def call_owner(self, thread: discord.Thread, trade: TradeRow, user: discord.abc.User) -> bool:
        """請群主（伺服器擁有者）進來協助：加進這個私人對話並 @ 他。群主已經在裡面就回 False。"""
        owner_id = getattr(thread.guild, "owner_id", None)
        if owner_id is None:
            raise RuntimeError("找不到伺服器擁有者")
        async with self._lock(("help", thread.id)):
            try:
                await thread.fetch_member(owner_id)
                return False
            except discord.NotFound:
                pass
            # 封存中的對話加不了人（安靜很久的等貨交易常常是封存的）；按按鈕不會解封，要先解
            await reopen_thread(thread)
            await thread.add_user(discord.Object(id=owner_id))
            await self.send(thread, f"<@{owner_id}>，{user.mention} 請群主協助處理這筆交易"
                                    f"（需求方 <@{trade.requester_id}>、供應方 <@{trade.supplier_id}>）。",
                            mention=(owner_id,))
        logger.info("交易：請群主協助 thread=%s by=%s", thread.id, user.id)
        return True

    async def cancel(self, thread: discord.Thread, trade_id: int, *, actor: discord.abc.User) -> bool:
        """回傳有沒有真的取消（剛好已經結束就沒有）。"""
        async with self.locked(trade_id) as trade:
            if trade is None:
                return False
            kind = self.kind_of(trade)
            # 提醒在發取消訊息前就算好、一起發：對話關閉後再補發會把它重新打開
            note = await kind.cancel_note(trade) if kind is not None else ""
            who = "供應方" if actor.id == trade.supplier_id else "群主"
            if kind is None:
                text = (f"<@{trade.requester_id}>，{who} <@{actor.id}> 已取消這筆交易，此對話將關閉。"
                        "需求貼文保留，其他供應方仍可接單。")
            else:
                text = f"<@{trade.requester_id}>，{who} <@{actor.id}> 已取消這筆交易，此對話將關閉，沒交付的數量會還回商品。"
            db = await self.db()
            async with db.transaction():
                await db.add_event(trade.id, tp.CANCELLED, now=self.stamp(), actor_id=actor.id)
                await db.set_trade_status(trade.id, CANCELLED, now=self.stamp())
                if kind is not None:
                    await kind.on_cancel_tx(db, trade)
            await self._finish(thread, text + (f"\n{note}" if note else ""), CANCELLED_PREFIX)
        if kind is None:
            await self._clear_supplier_reactions(trade)
        else:
            try:
                await kind.after_cancel(trade)
            except Exception:  # 邊界：交易已取消，重畫來源失敗只影響顯示
                logger.error("交易：取消後處理來源失敗 thread=%s", thread.id, exc_info=True)
        logger.info("交易：取消 thread=%s by=%s", thread.id, actor.id)
        await self._notify_parties(thread, trade, "交易取消", f"{who} <@{actor.id}> 取消了這筆交易。",
                                   note=note, extra_ids=(actor.id,))
        await self._mark_wrapped(trade.id)
        return True

    async def handle_thread_deleted(self, thread_id: int) -> bool:
        """交易對話被刪掉了：這筆交易記成取消（商品的份數還回去、貼文重畫），私訊雙方；不是交易對話回 False。
        不然交易永遠是進行中：份數一直佔著、擋著刪品項與下架，取消按鈕也跟著對話不見了。"""
        if not self.ready.is_set():
            return False
        async with self.locked(thread_id) as trade:
            if trade is None:
                return False
            kind = self.kind_of(trade)
            note = await kind.cancel_note(trade) if kind is not None else ""
            db = await self.db()
            async with db.transaction():
                await db.add_event(trade.id, tp.CANCELLED, now=self.stamp(), source="deleted")
                await db.set_trade_status(trade.id, CANCELLED, now=self.stamp())
                if kind is not None:
                    await kind.on_cancel_tx(db, trade)
        logger.warning("交易：交易對話被刪掉了，記成取消 thread=%s", thread_id)
        if kind is None:
            await self._clear_supplier_reactions(trade)
        else:
            try:
                await kind.after_cancel(trade)
            except Exception:  # 邊界：交易已取消，重畫來源失敗只影響顯示
                logger.error("交易：對話刪掉後處理來源失敗 thread=%s", thread_id, exc_info=True)
        await self._notify_parties(None, trade, "交易取消", "交易對話被刪除了，這筆交易已取消。", note=note)
        await self._mark_wrapped(trade.id)
        return True

    async def _close_deleted(self) -> None:
        """啟動後檢查一次：停機期間被刪掉的交易對話（收不到刪除事件）也記成取消。"""
        db = await self.db()
        for trade in await db.trades(status=OPEN):
            try:
                if await fetch_thread(self.bot, trade.id, raise_errors=True) is None:
                    await self.handle_thread_deleted(trade.id)
            except Exception:  # 邊界：一筆讀不到（沒權限、Discord 暫時出錯）就算了，不影響其他筆
                logger.warning("交易：檢查交易對話還在不在失敗 thread=%s", trade.id, exc_info=True)

    async def receive(self, thread: discord.Thread, trade_id: int, message: Optional[discord.Message]) -> Optional[str]:
        """需求方按「已領收」：只認目前有效的那則通知（被加購作廢、被新通知取代的舊通知不算），
        來源也同意（例：商品還有沒交付的）才完成。不能完成回理由。"""
        async with self.locked(trade_id) as trade:
            if trade is None:
                return "這筆交易已經結束。"
            state = receipt_state(await (await self.db()).events(trade.id))
            if state.request is None or (message is not None and state.request.message_id != message.id):
                return "這則領收通知已經失效，請看對話裡最新的通知。"
            kind = self.kind_of(trade)
            blocker = await kind.complete_blocker(trade) if kind is not None else None
            if blocker:
                return blocker
            ended_source = await self.complete_locked(thread, trade, auto=False)
        await self._close_out(trade, thread, ended_source)
        return None

    async def complete(self, thread: discord.Thread, trade_id: int, *, auto: bool) -> None:
        async with self.locked(trade_id) as trade:
            if trade is None:
                return
            ended_source = await self.complete_locked(thread, trade, auto=auto)
        await self._close_out(trade, thread, ended_source)

    async def complete_locked(self, thread: discord.Thread, trade: TradeRow, *, auto: bool,
                              how: Optional[str] = None) -> bool:
        """完成交易（要拿著這個交易的鎖）。how：完成的原因（例：實體商品全部收到）；沒給就照領收寫。
        回傳要不要結束同一篇需求的其他交易（自由市場的需求貼文封存了才要）。"""
        kind = self.kind_of(trade)
        db = await self.db()
        async with db.transaction():
            await db.add_event(trade.id, tp.COMPLETED, now=self.stamp(), source="auto" if auto else None,
                               actor_id=None if auto else trade.requester_id)
            await db.set_trade_status(trade.id, COMPLETED, now=self.stamp())
        result, note = await self._archive_once(thread, trade)
        hours = self.settings.receipt_timeout_hours
        if how is not None:
            done = how
        elif auto:
            done = f"需求方 <@{trade.requester_id}> 在 {hours} 小時內沒有按已領收，自動視為已領收"
        else:
            done = f"需求方 <@{trade.requester_id}> 已領收"
        await self._finish(thread, f"{done}，交易完成。{note}此對話將關閉。", COMPLETED_PREFIX)
        logger.info("交易：完成 thread=%s auto=%s 來源=%s", thread.id, auto, result)
        await self._notify_parties(thread, trade, "交易完成", f"{done}，交易完成。")
        ended_source = kind is None and result != _FOREIGN
        if not ended_source:
            await self._mark_wrapped(trade.id)
        return ended_source

    async def _archive_once(self, thread: discord.Thread, trade: TradeRow) -> tuple[Optional[str], str]:
        """完成時處理來源（自由市場：封存需求貼文；商品：留底），做過就記一筆，重啟補收尾時不重做。
        回傳 (結果, 要加在完成訊息裡的說明)；之前做過的回當時記下的結果（補收尾照它決定要不要結束其他交易）、說明空白。"""
        db = await self.db()
        done = list(await db.events(trade.id, kinds=[tp.ARCHIVED]))
        if done:
            return done[-1].reference, ""
        kind = self.kind_of(trade)
        if kind is None:
            try:
                result = await self._archive_source(trade)
            except Exception:  # 邊界：資料庫已經記了完成，後面的結束訊息、鎖定、私訊一定要做完
                logger.error("交易：完成時處理需求貼文失敗 thread=%s", trade.id, exc_info=True)
                result = _FAILED
            note = _ARCHIVE_NOTE[result]
        else:
            result = "kept"
            note = await kind.on_complete(thread, trade)
        async with db.transaction():
            await db.add_event(trade.id, tp.ARCHIVED, now=self.stamp(), reference=result)
        return result, note

    async def _mark_wrapped(self, trade_id: int) -> None:
        db = await self.db()
        async with db.transaction():
            await db.set_wrapped_up(trade_id)

    async def _close_out(self, trade: TradeRow, thread: discord.Thread, ended_source: bool) -> None:
        """自由市場的需求貼文成交後結束同一篇的其他交易，都做完才算這筆收尾完（沒做完的由期限排程補）。
        在交易鎖外做：兩位供應方同時完成時，各自拿著自己的鎖去等對方的鎖會卡死。"""
        if ended_source and await self._end_other_trades(trade, keep_thread_id=thread.id):
            await self._mark_wrapped(trade.id)

    # ── 入口：定時檢查領收期限（utils.due_loop 每次醒來呼叫）──

    async def run_receipt_deadlines(self, now: datetime) -> Optional[datetime]:
        """把超過期限還沒按已領收的交易自動完成、到期前提醒一次；回傳下一個要醒來的時刻。

        期限從資料庫裡的領收通知時間算，bot 重啟、停機期間對話被自動封存都照樣補做。"""
        if not self.ready.is_set():
            return now + timedelta(minutes=1)  # 上線匯入還沒做完：一分鐘後再看
        if not self._deleted_checked:
            self._deleted_checked = True
            await self._close_deleted()
        db = await self.db()
        timeout = timedelta(hours=self.settings.receipt_timeout_hours)
        next_due: Optional[datetime] = await self._wrap_up_unfinished(now)
        orphan_due = await self._close_orphans(now)
        if orphan_due is not None:
            next_due = orphan_due if next_due is None else min(next_due, orphan_due)
        for trade in await db.trades(status=OPEN):
            # 一筆讀不到或發不出去，不影響其他交易這一輪的檢查
            try:
                state = receipt_state(await db.events(trade.id))
                if state.request is None:
                    continue
                if state.request.message_id is None:
                    # 記了、沒發出去（發的時候剛好停機）：剛記的可能還在發，過一陣子才補
                    if state.since + WRAP_UP_GRACE <= now:
                        await self._resend_receipt(trade.id)
                    else:
                        next_due = min(filter(None, (next_due, state.since + WRAP_UP_GRACE)))
                    continue
                due = state.since + timeout
                if due <= now:
                    thread = await self.get_thread(trade.id)
                    if thread is None:
                        logger.warning("交易：領收到期但找不到交易對話 %s", trade.id)
                        continue
                    await self._auto_complete(thread, trade.id, now)
                    continue
                wake = [due]
                remind_at = self._remind_at(due)
                if remind_at is not None and not state.reminded:
                    if remind_at <= now:
                        thread = await self.get_thread(trade.id)
                        if thread is not None:
                            await self._remind_receipt(thread, trade.id, due, now)
                    else:
                        wake.append(remind_at)
                next_due = min([t for t in (next_due, *wake) if t is not None])
            except Exception:  # 邊界：排程的一筆交易，壞了下一輪再試
                logger.error("交易：檢查領收期限失敗 thread=%s", trade.id, exc_info=True)
        return next_due

    async def _close_orphans(self, now: datetime) -> Optional[datetime]:
        """開單做到一半中斷（對話建好、開單訊息發了，資料庫還沒寫就停機）留下的對話：上面的按鈕都會回
        「找不到紀錄」。說一聲、鎖起來，免得雙方以為已經下單。只看還在活躍清單裡、匯入之後開的、開了一陣子的。
        回傳最早一個還太新、要再來看的時刻（不然沒有別的事時排程一睡就是一小時）。"""
        if self.orphans_after is None:
            return None
        cart = await self._channel(self.settings.cart_channel_key)
        if cart is None:
            return None
        db = await self.db()
        later: Optional[datetime] = None
        for thread in list(getattr(cart, "threads", None) or ()):
            created = snowflake_time(thread.id)
            if (thread.locked or not is_trade_title(thread.name) or created < self.orphans_after
                    or await db.get_trade(thread.id) is not None):
                continue
            if created + WRAP_UP_GRACE > now:
                later = min(filter(None, (later, created + WRAP_UP_GRACE)))
                continue
            logger.warning("交易：關掉沒開成的交易對話 thread=%s", thread.id)
            try:
                if thread.id not in self._orphans_told:
                    await self.send(thread, "這個交易對話沒有開成功（開到一半中斷），上面的按鈕都不能用了。"
                                            "請重新下單或重新接單。")
                    self._orphans_told.add(thread.id)
                await thread.edit(name=closed_title(thread.name, CANCELLED_PREFIX), locked=True, archived=True)
            except discord.HTTPException:
                logger.warning("交易：關掉沒開成的交易對話失敗 thread=%s", thread.id, exc_info=True)
        return later

    async def _resend_receipt(self, trade_id: int) -> None:
        async with self.locked(trade_id) as trade:
            if trade is None:
                return
            state = receipt_state(await (await self.db()).events(trade.id))
            if state.request is None or state.request.message_id is not None:
                return
            thread = await fetch_thread(self.bot, trade.id, raise_errors=True)
            if thread is None:
                return
            logger.info("交易：補發沒發出去的領收通知 thread=%s", trade.id)
            await self.request_receipt_locked(thread, trade)

    async def _wrap_up_unfinished(self, now: datetime) -> Optional[datetime]:
        """資料庫已經記了結束、Discord 那邊（留底、結束訊息、收按鈕、改名鎖定、私訊）卻沒做完的交易：補做。
        只看結束超過 WRAP_UP_GRACE 的：剛結束的可能還在做。回傳最早一筆還太新、要再來看的時刻。"""
        db = await self.db()
        later: Optional[datetime] = None
        for trade in await db.unwrapped_trades():
            closed = datetime.fromisoformat(trade.closed_at) if trade.closed_at else now
            if closed + WRAP_UP_GRACE > now:
                later = min(filter(None, (later, closed + WRAP_UP_GRACE)))
                continue
            try:
                ended_source = False
                async with self._lock(trade.id):
                    row = await db.get_trade(trade.id)
                    if row is None or row.wrapped_up or row.status == OPEN:
                        continue
                    ended_source = await self._wrap_up(row)
                kind = self.kind_of(row)
                if row.status == CANCELLED and kind is not None:
                    # 在交易鎖外：重畫來源要拿商品鎖，鎖的順序是商品鎖 → 交易鎖，拿著交易鎖去等商品鎖會跟截止通知互等
                    await kind.after_cancel(row)
                # 同一篇的其他交易都結束了才算收尾完：哪一筆出錯，這筆下一輪再補（跟正常完成的順序一樣）
                if ended_source and not await self._end_other_trades(row, keep_thread_id=row.id):
                    continue
                await self._mark_wrapped(row.id)
                logger.info("交易：補做結束後的收尾 thread=%s 狀態=%s", row.id, row.status)
            except Exception:  # 邊界：排程的一筆交易，壞了下一輪再試
                logger.error("交易：補做結束後的收尾失敗 thread=%s", trade.id, exc_info=True)
        return later

    async def _wrap_up(self, trade: TradeRow) -> bool:
        """補做一筆已結束交易的收尾（要拿著這個交易的鎖）。回傳要不要再結束同一篇需求的其他交易。

        取對話只有「真的不存在」才當沒有（Discord 暫時出錯就往外丟，下一輪再來，不能記成做完）；
        對話不在了照樣封存需求貼文、結束其他交易；已經鎖好的對話不再發一次結束訊息。"""
        thread = await fetch_thread(self.bot, trade.id, raise_errors=True)
        kind = self.kind_of(trade)
        ended_source = False
        note = ""
        if trade.status == COMPLETED:
            if thread is not None or kind is None:
                result, note = await self._archive_once(thread, trade)
                ended_source = kind is None and result != _FOREIGN
            text, prefix, title = f"交易完成。{note}此對話將關閉。", COMPLETED_PREFIX, "交易完成"
        elif trade.status == CANCELLED:
            # 取消時的提醒（定金已付…）從資料庫再算一次：雙方之後處理退款要看它
            note = await kind.cancel_note(trade) if kind is not None else ""
            text, prefix, title = "這筆交易已取消，此對話將關閉。", CANCELLED_PREFIX, "交易取消"
        else:
            text, prefix, title = "這篇需求已由其他供應方完成，這個對話將結束並關閉。", ENDED_PREFIX, "交易結束"
        if trade.status == CANCELLED and kind is None:
            # 自由市場：清掉這位供應方的接單表情，之後要再接這篇可以直接重按（取消當下沒做完的補做）
            await self._clear_supplier_reactions(trade)
        if thread is None:
            return ended_source
        if not getattr(thread, "locked", False):
            await self._finish(thread, text + (f"\n{note}" if trade.status == CANCELLED and note else ""), prefix)
        await self._notify_parties(thread, trade, title, text, note=note if trade.status == CANCELLED else "")
        return ended_source

    async def _auto_complete(self, thread: discord.Thread, trade_id: int, now: datetime) -> None:
        """鎖裡再確認一次通知還有效、真的到期了（剛好被按「還沒領收」就不能自動完成）。"""
        async with self.locked(trade_id) as trade:
            if trade is None:
                return
            state = receipt_state(await (await self.db()).events(trade.id))
            if (state.request is None or state.request.message_id is None
                    or state.since + timedelta(hours=self.settings.receipt_timeout_hours) > now):
                return
            kind = self.kind_of(trade)
            blocker = await kind.complete_blocker(trade) if kind is not None else None
            if blocker:
                # 不該發生（加購時通知已經作廢）；保險：讓這則通知失效，不然每次醒來都會再碰到
                logger.warning("交易：領收到期但還不能完成 thread=%s：%s", thread.id, blocker)
                await self.retire_receipt_locked(thread, trade, "（還有品項沒交付，這次通知已作廢）")
                return
            ended_source = await self.complete_locked(thread, trade, auto=True)
        await self._close_out(trade, thread, ended_source)

    # ── 鎖、發訊息 ──

    def _lock(self, key: object) -> asyncio.Lock:
        return self._locks.setdefault(key, asyncio.Lock())

    @asynccontextmanager
    async def locked(self, trade_id: int) -> AsyncIterator[Optional[TradeRow]]:
        """拿著這個交易對話的鎖；交易已經結束（或沒有紀錄）時給 None。鎖不能重入。"""
        async with self._lock(trade_id):
            trade = await (await self.db()).get_trade(trade_id)
            if trade is None or trade.status != OPEN:
                yield None
            else:
                yield trade

    async def send(self, thread: discord.Thread, content: Optional[str] = None, *,
                   mention: Sequence[int] = (), **kwargs) -> discord.Message:
        """在交易對話發訊息，只 @ mention 裡的人（訊息裡寫到的其他人只顯示名字、不通知）。

        超過一則的上限（加購累積很多品項時的等待提醒、我已付的通知）切成幾則送、回傳最後一則，@ 只放第一則；
        帶按鈕、embed 或附件的不切（按鈕與卡片要跟著那一則），呼叫端要自己把文字控制在上限內。"""
        if content and len(content) > DISCORD_MESSAGE_LIMIT and not kwargs:
            sent = await send_model_text(thread.send, content, mention_users=[discord.Object(id=i) for i in mention])
            return sent[-1]
        return await thread.send(content=content, allowed_mentions=mention_only(*mention), **kwargs)

    async def _strip_message(self, thread: discord.Thread, message_id: Optional[int], note: str,
                             *, message: Optional[discord.Message] = None) -> None:
        """在某則 bot 訊息後面加一行說明、拿掉上面的按鈕（領收通知失效時）。找不到那則就算了。"""
        if message is None and message_id:
            with contextlib.suppress(discord.HTTPException):
                await reopen_thread(thread)
                message = await thread.fetch_message(message_id)
        if message is None or note in (message.content or ""):
            return   # 已經處理過（補做時再跑一次不重複加說明）
        try:
            await message.edit(content=f"{message.content}\n{note}", view=None)
        except discord.HTTPException:
            logger.warning("交易：拿掉通知上的按鈕失敗 thread=%s message=%s", thread.id, message.id, exc_info=True)

    async def _finish(self, thread: discord.Thread, text: str, prefix: str) -> None:
        """結束時在對話留一句（不 @ 人，改私訊雙方）、收掉交易按鈕、改名鎖定封存。資料庫要先寫好：
        這裡哪一步失敗，按鈕都會回「已經結束」，對話沒鎖上只是外觀，所以每一步各自記 log、照樣往下做。"""
        try:
            await self.send(thread, text)
        except discord.HTTPException:
            logger.error("交易：結束訊息發送失敗 thread=%s", thread.id, exc_info=True)
        try:
            # 交易結束就拿掉交易按鈕（做完了按鈕還在，看起來像還能按）。要在封存前做：封存中的對話改不了訊息
            await self._strip_buttons(thread)
        except discord.HTTPException:
            logger.error("交易：讀交易對話收按鈕失敗 thread=%s", thread.id, exc_info=True)
        try:
            # 改名、鎖定、封存一次做完：改名有很嚴的限速，一筆交易只改這一次
            await thread.edit(name=closed_title(thread.name, prefix), locked=True, archived=True)
        except discord.HTTPException:
            logger.error("交易：鎖定交易對話失敗 thread=%s", thread.id, exc_info=True)

    async def _notify_parties(self, thread: Optional[discord.Thread], trade: TradeRow, title: str, text: str,
                              *, note: str = "", extra_ids: Sequence[int] = ()) -> None:
        """交易結束時私訊雙方，附上交易對話的連結。text、note 裡的 <@id> 換成名字（私訊裡的 @ 看不出是誰）。

        對話一結束就封存、從頻道列表消失；封存後點連結仍進得去（對話被刪掉時 thread 是 None，不附連結）。
        私訊關閉或已離開伺服器的人就略過。每筆交易只私訊一次（記一筆 notified）：補收尾可能因為結束其他交易失敗而重跑好幾輪。"""
        try:
            db = await self.db()
            if any(True for _ in await db.events(trade.id, kinds=[tp.NOTIFIED])):
                return
            guild = getattr(thread, "guild", None)
            if guild is None:
                guild = getattr(await self._channel(self.settings.cart_channel_key), "guild", None)
            names = await self.display_names(guild, (trade.requester_id, trade.supplier_id, *extra_ids))
            requester = names.get(trade.requester_id) or str(trade.requester_id)
            supplier = names.get(trade.supplier_id) or str(trade.supplier_id)
            description = mentions_to_names(text, names)
            if note:
                description += f"\n\n{mentions_to_names(note, names)}"
            # embed 說明最多 4096 字：超過整則送不出去，雙方就收不到「定金已付…」的提醒
            embed = discord.Embed(title=title, color=discord.Color.gold(), description=description[:4000])
            embed.add_field(name="需求方", value=requester, inline=True)
            embed.add_field(name="供應方", value=supplier, inline=True)
            if thread is not None:
                embed.add_field(name="交易對話", value=f"[點這裡查看]({thread.jump_url})", inline=False)
            if guild is not None:
                embed.set_footer(text=getattr(guild, "name", "") or "")
            for user_id in (trade.requester_id, trade.supplier_id):
                member = await self.member(guild, user_id)
                if member is not None:
                    await send_dm(member, embed=embed)
            async with db.transaction():
                await db.add_event(trade.id, tp.NOTIFIED, now=self.stamp())
        except Exception:  # 邊界：交易已經結束，私訊失敗不影響結果
            logger.error("交易：私訊雙方失敗 thread=%s", trade.id, exc_info=True)

    async def _strip_buttons(self, thread: discord.Thread) -> None:
        """拿掉對話裡 bot 訊息上的交易按鈕（含舊按鈕、商品的交易進度）。"""
        await reopen_thread(thread)
        for message in (await self.read(thread)).button_messages():
            try:
                await message.edit(view=None)
            except discord.HTTPException:
                logger.warning("交易：拿掉按鈕失敗 thread=%s message=%s", thread.id, message.id, exc_info=True)

    async def has_open_trades(self, supplier_id: int) -> bool:
        """這個人有沒有自己當供應方、還沒結束的交易。"""
        return bool(await (await self.db()).trades(status=OPEN, supplier_id=supplier_id))

    async def open_trades_for_source(self, source_id: int) -> list[TradeRow]:
        """同一篇來源還沒結束的交易（例：預購截止時要通知的那些）。"""
        return await (await self.db()).trades(source_id=source_id, status=OPEN)

    async def open_trade_threads(self, *, archived_since: Optional[datetime] = None) -> AsyncIterator[discord.Thread]:
        """購物車裡標題還是進行中的交易對話（上線匯入翻舊交易用）。

        discord.py 的 thread 快取只有活躍的：一封存就不在 `cart.threads` 裡，所以還要往回翻已封存的私人 thread
        （按封存時間由新到舊），翻到 archived_since 為止（None＝全部）。需要 Manage Threads 權限。"""
        cart = await self._channel(self.settings.cart_channel_key)
        if cart is None:
            return
        seen: set[int] = set()
        for thread in list(getattr(cart, "threads", None) or ()):
            seen.add(thread.id)
            if not thread.locked and is_trade_title(thread.name):
                yield thread
        async for thread in cart.archived_threads(private=True, limit=None):
            if archived_since is not None and thread.archive_timestamp < archived_since:
                break
            if thread.id not in seen and not thread.locked and is_trade_title(thread.name):
                seen.add(thread.id)
                yield thread

    async def read(self, thread: discord.Thread) -> TradeThreadLog:
        """讀一整串交易對話（見 `TradeThreadLog`）。"""
        return await read_trade_thread(thread, bot_user_id=self.bot.user.id)

    def _remind_at(self, due: datetime) -> Optional[datetime]:
        before = self.settings.receipt_reminder_hours_before
        if not 0 < before < self.settings.receipt_timeout_hours:
            return None
        return due - timedelta(hours=before)

    async def _remind_receipt(self, thread: discord.Thread, trade_id: int, due: datetime, now: datetime) -> None:
        """到期前提醒需求方一次：讓「一直沒反應」才等於已領收。提醒過記在資料庫，重啟不重發。"""
        async with self.locked(trade_id) as trade:
            if trade is None:
                return
            db = await self.db()
            state = receipt_state(await db.events(trade.id))
            if state.request is None or state.request.message_id is None or state.reminded:
                return
            hours_left = max(1, math.ceil((due - now).total_seconds() / 3600))
            async with db.transaction():
                await db.add_event(trade.id, tp.RECEIPT_REMINDED, now=self.stamp())
            await self.send(thread, f"⏰ <@{trade.requester_id}>，再 {hours_left} 小時將自動視為已領收。"
                                    "還沒收到請按上面通知裡的「還沒領收」；有爭議可以按「請群主協助」。",
                            mention=(trade.requester_id,))

    async def _end_other_trades(self, trade: TradeRow, *, keep_thread_id: int) -> bool:
        """結束同一篇需求的其他交易；回傳是不是每一筆都做完了（一筆壞了不影響其他筆，下一輪再補那一筆）。"""
        all_done = True
        for other in await self.open_trades_for_source(trade.source_id):
            if other.id == keep_thread_id or other.source_kind != "forum":
                continue
            try:
                await self._end_one(other)
            except Exception:  # 邊界：一筆對話結束失敗，不影響其他筆
                logger.error("交易：結束同一篇需求的其他交易失敗 thread=%s", other.id, exc_info=True)
                all_done = False
        return all_done

    async def _end_one(self, other: TradeRow) -> None:
        """同一篇需求由別的供應方完成：這一筆記成結束、收尾、私訊。已經結束的不動。"""
        async with self.locked(other.id) as current:
            if current is None:
                return
            # 只有真的不存在才當沒有：Discord 暫時出錯就往外丟（這筆還沒寫、下一輪再來），不能記成結束又沒收尾
            thread = await fetch_thread(self.bot, current.id, raise_errors=True)
            db = await self.db()
            async with db.transaction():
                await db.add_event(current.id, tp.ENDED, now=self.stamp())
                await db.set_trade_status(current.id, ENDED, now=self.stamp())
            if thread is not None:
                await self._finish(thread, "這篇需求已由其他供應方完成，這個對話將結束並關閉。", ENDED_PREFIX)
        if thread is not None:
            await self._notify_parties(thread, current, "交易結束", "這篇需求已由其他供應方完成交易，這筆交易結束。")
        await self._mark_wrapped(current.id)

    async def _archive_source(self, trade: TradeRow) -> str:
        """把需求貼文的對話複製到封存頻道（完整內容附 .txt），成功才刪除原貼文。
        取貼文只有「真的不存在」才當沒有：Discord 暫時出錯就往外丟（記成處理失敗、完成訊息請大家通知管理員），
        不能記成「貼文已經不在」——這個結果只做一次，記錯了貼文就一直開著、還能被接單。"""
        # 同一篇需求只封存一次：兩位供應方同時完成時，後到的會發現貼文已經不在
        async with self._lock(("source", trade.source_id)):
            source = await self.get_thread(trade.source_id, raise_errors=True)
            if source is None:
                return _MISSING
            # 保險：只有確定在自由市場裡的貼文才封存、刪除（刪掉的東西救不回來）
            if getattr(source, "parent_id", None) != await self._channel_id(self.settings.forum_channel_key):
                logger.warning("交易：來源 %s 不在自由市場，不封存也不刪除", trade.source_id)
                return _FOREIGN
            archive = await self._channel(self.settings.archive_channel_key)
            if archive is None:
                logger.error("交易：封存頻道未設定，只鎖定需求貼文 %s", trade.source_id)
                try:
                    await reopen_thread(source)   # 封存中的貼文鎖不了
                    await source.edit(locked=True, archived=True)
                except discord.HTTPException:
                    logger.error("交易：鎖定需求貼文 %s 失敗", trade.source_id, exc_info=True)
                    return _LOCK_FAILED
                return _LOCKED
            try:
                await self.post_archive(
                    title=_fit_title(f"已封存 - {source.name}", trade.source_id),
                    summary=await self._archive_summary(source, trade),
                    transcript=await self.transcript(source),
                    filename=f"trade_{trade.source_id}.txt",
                )
            except Exception:  # 邊界：封存失敗就保留原貼文，原因寫 log、對話裡請大家通知管理員
                logger.error("交易：封存需求貼文 %s 失敗，保留原貼文", trade.source_id, exc_info=True)
                return _FAILED
            try:
                await source.delete()
            except discord.HTTPException:
                logger.error("交易：需求貼文 %s 已封存，但刪除原貼文失敗", trade.source_id, exc_info=True)
                return _ARCHIVED_KEPT
            return _ARCHIVED

    async def post_archive(self, *, title: str, summary: str, transcript: str, filename: str) -> bool:
        """在封存頻道發一篇封存。自由市場的封存與商品交易的留底都用它。

        放得下 2000 字就把摘要＋對話整段寫在貼文裡（打開就看得到，Discord 搜尋也找得到）；
        放不下時貼文只放摘要，完整內容放 .txt 附檔，封存才不會因為太長而失敗。
        封存頻道沒設定回 False；發不出去丟例外。"""
        archive = await self._channel(self.settings.archive_channel_key)
        if archive is None:
            return False
        tags = None
        if hasattr(archive, "available_tags"):  # 論壇才有標籤
            tags = await get_forum_tags(archive, self.settings.archive_tag_name)
        # 對話是別人寫的，裡面的 @everyone、@身分組 不能在封存時又通知一次
        quiet = discord.AllowedMentions.none()
        full = f"{summary}\n\n對話紀錄：\n{transcript}" if transcript else summary
        if len(full) <= 2000:
            posted = await post_to_channel(archive, content=full, thread_title=title, tags=tags,
                                           allowed_mentions=quiet)
        else:
            head = summary if len(summary) <= 1900 else summary[:1900] + "……"
            posted = await post_to_channel(
                archive, content=f"{head}\n\n對話太長，完整內容見附檔。", thread_title=title, tags=tags,
                files=[discord.File(io.BytesIO(full.encode("utf-8")), filename=filename)],
                allowed_mentions=quiet,
            )
        if posted is None:
            raise RuntimeError("封存頻道沒有回傳訊息")
        return True

    async def transcript(self, thread: discord.Thread) -> str:
        """自由市場需求貼文的對話紀錄（給封存用）：每則「[時間] 名字: 內容」，@ 換成名字，最多讀設定的則數。
        需求貼文本來就公開；商品交易的私人對話不複製進封存頻道，所以只有這裡用。"""
        messages = [m async for m in thread.history(limit=self.settings.archive_history_limit, oldest_first=True)]
        # 向 API 抓回來的歷史訊息，作者不在快取時只有全域名稱；名字一律從伺服器取（被 @ 的人也一樣）
        mentioned = {int(i) for m in messages for i in _MENTION_RE.findall(m.content or "")}
        names = await self.display_names(thread.guild, [m.author.id for m in messages] + sorted(mentioned))
        lines = []
        for message in messages:
            when = message.created_at.astimezone(APP_TZ).strftime("%Y-%m-%d %H:%M")
            name = names.get(message.author.id) or message.author.display_name
            lines.append(f"[{when}] {name}: {mentions_to_names(message.content, names)}")
            urls = [a.url for a in getattr(message, "attachments", None) or ()]
            if urls:
                lines.append("    附件：" + " ".join(urls))
        return "\n".join(lines)

    async def _archive_summary(self, source: discord.Thread, trade: TradeRow) -> str:
        # 封存貼文寫名字不寫 @，免得每次封存都去提醒雙方
        names = await self.display_names(source.guild, (trade.requester_id, trade.supplier_id))
        return (f"需求貼文：{source.name}\n"
                f"需求方：{names.get(trade.requester_id) or trade.requester_id}　"
                f"供應方：{names.get(trade.supplier_id) or trade.supplier_id}\n"
                f"完成時間：{self.finished_at(trade).astimezone(APP_TZ):%Y-%m-%d %H:%M}")

    async def _clear_supplier_reactions(self, trade: TradeRow) -> None:
        """取消後清掉這位供應方在需求貼文上的接單表情，之後要再接單可以重按。

        自由市場的貼文一小時沒人講話就會被自動封存，對封存中的 thread 改反應會被 Discord 拒絕，
        所以先解除封存（貼文會回到活躍列表，也剛好表示這篇需求又可以接了）。"""
        source = await self.get_thread(trade.source_id)
        if source is None:
            return
        if not await reopen_thread(source):
            return
        try:
            starter = await source.fetch_message(trade.source_id)
        except discord.HTTPException:
            logger.warning("交易：清供應方表情前讀不到需求貼文 %s", trade.source_id, exc_info=True)
            return
        failed = []
        for emoji in self.settings.accept_emojis:
            try:
                await starter.remove_reaction(emoji, discord.Object(id=trade.supplier_id))
            except discord.HTTPException as exc:
                failed.append(f"{emoji}({exc.status})")
        if failed:
            logger.warning("交易：清掉供應方 %s 在需求貼文 %s 上的表情失敗：%s",
                           trade.supplier_id, trade.source_id, "、".join(failed))

    def _forum_opening(self, ref: TradeRef) -> tuple[str, str]:
        return (f"供應方 <@{ref.supplier_id}> 接下了需求方 <@{ref.requester_id}> 的需求，請在這裡討論交易細節。",
                f"供應方交付後按「通知需求方領收」，需求方收到後按「已領收」即完成；"
                f"還沒收到可以按「還沒領收」暫停（{self.settings.receipt_timeout_hours} 小時都沒按會自動完成）。"
                "只有供應方和群主可以取消交易；有爭議可以按「請群主協助」。")

    async def refresh_opening(self, thread: discord.Thread, trade: TradeRow) -> None:
        """把開單訊息的流程說明換成這筆交易現在的（上線前的舊交易接上新流程時：舊說明講的是領收、自動完成）。
        按鈕不動；找不到開單訊息就算了。"""
        opened = next((e for e in await (await self.db()).events(trade.id, kinds=[tp.OPENED]) if e.message_id), None)
        kind = self.kind_of(trade)
        if opened is None or kind is None:
            return
        ref = TradeRef(trade.source_id, trade.requester_id, trade.supplier_id)
        description, flow = await kind.opening(ref)
        try:
            await reopen_thread(thread)
            message = await thread.fetch_message(opened.message_id)
            await message.edit(embed=self._opening_embed(ref, kind, description, flow))
        except discord.HTTPException:
            logger.warning("交易：更新開單訊息的流程說明失敗 thread=%s", thread.id, exc_info=True)

    def _opening_embed(self, ref: TradeRef, kind: Optional[SourceKind], description: str, flow: str) -> discord.Embed:
        embed = discord.Embed(title="交易確認", description=description, color=discord.Color.gold())
        embed.add_field(name=kind.label if kind else "需求貼文", value=f"<#{ref.source_id}>", inline=False)
        embed.add_field(name="流程", value=flow, inline=False)
        return embed

    async def _ephemeral(self, interaction: discord.Interaction, text: str, **kwargs) -> None:
        await safe_send_interaction_message(interaction, text, ephemeral=True, **kwargs)

    async def _channel_id(self, key: str) -> Optional[int]:
        # 每次重讀（有 5 分鐘快取）：頻道是使用者在 /server_manager 綁的，bot 不重啟也可能改
        return await ChannelConfig.get_configured_id(key, caller="trade")

    async def _channel(self, key: str):
        channel_id = await self._channel_id(key)
        return self.bot.get_channel(channel_id) if channel_id is not None else None

    async def note_chat(self, message: discord.Message) -> None:
        """購物車的交易對話裡有真人講話：記進資料庫（看板、週報的「幾天沒動靜」直接查它，不用去翻對話）。
        bot 自己的訊息（提醒、通知）不算；停機期間的訊息記不到，只會讓那幾筆看起來比實際更久沒動靜。"""
        if getattr(message.author, "bot", False) or not self.ready.is_set():
            return
        channel = message.channel
        cart_id = await self._channel_id(self.settings.cart_channel_key)
        if cart_id is None or getattr(channel, "parent_id", None) != cart_id:
            return
        db = await self.db()
        async with db.transaction():
            await db.note_chat(channel.id, message.created_at.isoformat())

    def finished_at(self, trade: TradeRow) -> datetime:
        """交易結束的時刻（留底、封存寫的完成時間）：重啟後補收尾也寫當初結束的時間，不是補做那一刻。"""
        return datetime.fromisoformat(trade.closed_at) if trade.closed_at else self._now()

    async def get_thread(self, thread_id: int, *, raise_errors: bool = False) -> Optional[discord.Thread]:
        """交易或商品的 thread（已封存的也拿得到）；不存在或不是 thread 回 None。
        raise_errors：Discord 暫時出錯時往外丟（呼叫端要分得出「不在了」和「晚點再試」時用）。"""
        return await fetch_thread(self.bot, thread_id, raise_errors=raise_errors)

    async def member(self, guild: Optional[discord.Guild], user_id: int, *,
                     raise_errors: bool = False) -> Optional[discord.Member]:
        """取伺服器成員；要顯示的名字一律用它的 display_name（伺服器暱稱）。raise_errors：暫時出錯往外丟。"""
        return await resolve_member(guild, user_id, raise_errors=raise_errors)

    async def display_names(self, guild: Optional[discord.Guild], user_ids) -> dict[int, str]:
        """一批使用者的伺服器暱稱（每人只查一次）；查不到的不在結果裡，由呼叫端決定怎麼顯示。"""
        names: dict[int, str] = {}
        for user_id in dict.fromkeys(user_ids):
            member = await self.member(guild, user_id)
            if member is not None:
                names[user_id] = member.display_name
        return names
