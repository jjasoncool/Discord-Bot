"""商品交易：交易對話裡的交易進度（每個品項付到哪、交到哪）、付款與交付的按鈕、截止與延期的通知、等待提醒、
取消與完成時對商品的處理。

架構定位：功能層（`services.community`）。
  - 上層（誰呼叫）：商品服務 `shop_service`（建立它；下單後 `after_order`，截止、延期、開始收尾款叫 `announce_*`、
    `request_balances`）、交易模組 `trade_service`（透過 `SourceKind`：開單說明、通知領收＝剩下的一起交付、
    取消、完成）、介面 `commands.shop_commands`（交易進度上的按鈕 → `handle_step`；等待提醒的排程 → `run_waiting_reminders`）。
  - 下層（呼叫誰）：`trade_progress`（狀態、允許表、等待提醒的時間）、`services.market_db`（交易品項與事件）、
    交易模組的鎖與發訊息（`TradeService.locked`／`send`／`request_receipt_locked`／`complete_locked`）。

介面：
  - `ListingTrades`：交易模組的來源種類（name＝"listing"），以及上面列的那些方法。
  - `Step`：交易進度上一顆按鈕（動作、品項、文字、誰按）；`STEP_TEMPLATE`／`step_custom_id`：它的 custom_id。

規則：
  - 每次按按鈕都在交易鎖裡重讀資料庫、照允許表（`trade_progress.allowed`）判斷、寫一筆事件，成功後才發訊息；
    重複按、兩人同時按、按到舊卡片上的按鈕都不會記兩次。
  - 交易進度卡每次狀態變了就發一則新的，上一則的按鈕收起來；卡片從資料庫畫，壞了可以重畫。
  - 只 @ 下一步要動手的人。錢只由收錢的人確認：「已收到…」只有供應方能按；需求方的「我已付」只 @ 供應方、不改狀態。
  - 上線前的舊交易（legacy）沒有交易進度、不發等待提醒；截止通知照發。

例外與決策：
  - 每筆金額照交易品項記的下單當時金額算（同一個品項加購時價格可能不同），從最早下單的那份開始算。
  - 截止、延期、請款的通知先記事件再發：一個對話發不出去不影響其他人，也不會每次排程醒來就重複 @；
    請款另外記「發出去的那則訊息」，沒發出去的由截止排程補發。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Iterable, Optional, Sequence

import discord

from services.community import trade_progress as tp
from services.community import market_transition as transition
from services.community.shop_listing import Listing, Variant, format_cutoff, format_date, money
from services.community.trade_service import NO_RECORD_TEXT, NOT_READY_TEXT, TradeRef, receipt_state, thread_link
from services.market_db import MarketDB, TradeItemRow, TradeRow
from sys_settings.time_settings import APP_TZ
from utils.discord_content import masked_link

if TYPE_CHECKING:
    from services.community.shop_service import ShopService

logger = logging.getLogger(__name__)

#: 交易進度上的按鈕：trade:step:動作[:品項編號][:v卡片版本]（開頭跟交易按鈕一樣，交易結束時一起收掉）。
#: 版本＝那張卡照到哪一筆事件畫的：確認收款只算那張卡上看得到的份數（同時有人加購，加購的不會被一起記成已收）
STEP_TEMPLATE = (r"trade:step:(?P<action>claim_paid|confirm_deposit|confirm_balance|confirm_full|deliver|ship|receive)"
                 r"(?::(?P<key>\d+))?(?::v(?P<version>\d+))?")
_RECORD_FAILED = "交易紀錄沒能自動保存，請通知管理員。"
_PAY_LABEL = {"deposit": "定金", "balance": "尾款", "full": "款項", "mixed": "款項"}
#: 「我已付…」「已付…」的說法（一次付清說「付款」，不說「付款項」）
_CLAIM_LABEL = {"deposit": "定金", "balance": "尾款", "full": "款", "mixed": "款"}
_STATE_LOOK = {
    tp.AWAIT_DEPOSIT: ("🟡", tp.AWAIT_DEPOSIT),
    tp.WAIT_GOODS: ("⚪", tp.WAIT_GOODS),
    tp.AWAIT_BALANCE: ("🟡", tp.AWAIT_BALANCE),
    tp.AWAIT_PAYMENT: ("🟡", tp.AWAIT_PAYMENT),
    tp.AWAIT_DELIVERY: ("🟢", "錢已收齊・待交付"),
    tp.AWAIT_SHIPPING: ("🟢", "錢已收齊・待寄出"),
    tp.DELIVERED_STATE: ("✔️", tp.DELIVERED_STATE),
    tp.SHIPPED_STATE: ("📦", tp.SHIPPED_STATE),
    tp.RECEIVED_STATE: ("✔️", tp.RECEIVED_STATE),
}


def step_custom_id(action: str, key: Optional[int] = None, version: Optional[int] = None) -> str:
    return (f"trade:step:{action}" + (f":{key}" if key is not None else "")
            + (f":v{version}" if version is not None else ""))


@dataclass(frozen=True)
class Step:
    """交易進度上一顆按鈕。who：誰能按（trade_progress.SUPPLIER／REQUESTER），介面用它決定顏色。"""

    action: str
    key: Optional[int]
    label: str
    who: str
    version: Optional[int] = None

    @property
    def custom_id(self) -> str:
        return step_custom_id(self.action, self.key, self.version)


@dataclass(frozen=True)
class BalanceRow:
    """開始收尾款時一個交易對話要請的款。"""

    trade: TradeRow
    qty: int
    amount: int
    unconfirmed: int        # 其中幾份供應方還沒確認定金
    units: tuple[int, ...]  # 這些份數的每份尾款（加購時可能不同）


def _units(items: Iterable[TradeItemRow], key: int, field: str) -> list[int]:
    """這個品項每一份的金額（field＝unit_price 或 unit_balance），照下單先後；取消還回的份數不算。"""
    units: list[int] = []
    for item in sorted(items, key=lambda i: i.id):
        if item.variant_key == key:
            units += [getattr(item, field) or 0] * (item.qty - item.returned)
    return units


def _amount(items: Sequence[TradeItemRow], key: int, field: str, skip: int, qty: int) -> int:
    """跳過已經處理的 skip 份，再算接下來 qty 份的金額。"""
    return sum(_units(items, key, field)[skip:skip + qty])


_STATE_PAY = {tp.AWAIT_DEPOSIT: "deposit", tp.AWAIT_BALANCE: "balance", tp.AWAIT_PAYMENT: "full"}


def claim_kind(prog: tp.Progress, keys: Optional[Iterable[int]] = None) -> Optional[str]:
    """需求方現在按「我已付」是付哪一種錢（只看還沒按過的品項，或給定的 keys）；定金、尾款混在一起回 "mixed"。"""
    wanted = set(keys) if keys is not None else None
    kinds = {_STATE_PAY[line.state(prog.delivery)] for line in prog.lines
             if line.state(prog.delivery) in _STATE_PAY and (wanted is None and not line.claimed
                                                             or wanted is not None and line.key in wanted)}
    if not kinds:
        return None
    return kinds.pop() if len(kinds) == 1 else "mixed"


def due_amount(prog: tp.Progress, items: Sequence[TradeItemRow], kind: str,
               keys: Optional[Iterable[int]] = None) -> int:
    """這一種錢（deposit／balance／full；mixed＝三種都算）現在還要付多少；給 keys 就只算那幾個品項。"""
    wanted = set(keys) if keys is not None else None
    total = 0
    for line in prog.lines:
        if wanted is not None and line.key not in wanted:
            continue
        state = line.state(prog.delivery)
        if kind == "mixed":
            total += due_amount(prog, items, _STATE_PAY.get(state, ""), [line.key]) if state in _STATE_PAY else 0
            continue
        if kind == "deposit" and state == tp.AWAIT_DEPOSIT:
            total += _amount(items, line.key, "unit_price", line.deposit_paid, line.qty - line.deposit_paid)
        elif kind == "balance" and state == tp.AWAIT_BALANCE:
            total += _amount(items, line.key, "unit_balance", line.balance_paid,
                             line.balance_requested - line.balance_paid)
        elif kind == "full" and state == tp.AWAIT_PAYMENT:
            total += _amount(items, line.key, "unit_price", line.full_paid, line.qty - line.full_paid)
    return total


def ready_at(variant: Variant) -> Optional[datetime]:
    """預購品項可以開始交貨的時刻（截止，或延期後的預計交貨日）；不是預購回 None。提醒與週報都看它。"""
    if not variant.preorder or variant.cutoff is None:
        return None
    return max(variant.cutoff, variant.expected_at or variant.cutoff)


#: 訊息裡列品項的長度上限：收款確認、交付的訊息跟交易進度卡在同一則，一則最多 2000 字、不能切段。
#: 部分交付那則同時列「交付了什麼」和「還沒交付的」，兩段加起來也要放得下
_DESCRIBE_LIMIT = 1200
_REST_LIMIT = 600
#: 取消時「已收的錢」每一種列的品項長度上限
_PAID_LIMIT = 450


def _join_capped(parts: list[str], limit: int) -> str:
    """用頓號串起來；超過 limit 只列前面幾項，後面寫「…等 N 項」。"""
    text = "、".join(parts)
    if len(text) <= limit:
        return text
    shown: list[str] = []
    for part in parts:
        if len("、".join(shown + [part])) > limit - 10:
            break
        shown.append(part)
    return "、".join(shown) + f"…等 {len(parts)} 項"


def _describe(prog: tp.Progress, picks: dict[int, int]) -> str:
    """「名稱 ×份數」用頓號串起來。品項很多、名稱又長時只列前面幾項（金額另外照全部算）。"""
    return _join_capped([f"{prog.line(key).name} ×{qty}" for key, qty in picks.items() if prog.line(key)],
                        _DESCRIBE_LIMIT)


def render_card(prog: tp.Progress, items: Sequence[TradeItemRow], unit: str, *, version: Optional[int] = None,
                listing: Optional[Listing] = None) -> tuple[discord.Embed, list[Step]]:
    """交易進度卡：每個品項一行（份數、狀態、這一步要付的金額），已收的金額，以及這一步能按的按鈕。
    version 是這張卡照到哪一筆事件畫的（寫進按鈕）；給 listing 的話，收定金截止的品項會標出來。"""
    closed = {v.key for v in (listing.variants if listing else ()) if v.deposit and (v.cutoff_done or v.balance_started)}
    rows = []
    for line in prog.lines:
        state = line.state(prog.delivery)
        emoji, text = _STATE_LOOK[state]
        due = 0
        if state == tp.AWAIT_DEPOSIT:
            due = _amount(items, line.key, "unit_price", line.deposit_paid, line.qty - line.deposit_paid)
        elif state == tp.AWAIT_BALANCE:
            due = _amount(items, line.key, "unit_balance", line.balance_paid, line.balance_requested - line.balance_paid)
        elif state == tp.AWAIT_PAYMENT:
            due = _amount(items, line.key, "unit_price", line.full_paid, line.qty - line.full_paid)
        # 還沒付定金的要講清楚：已經下單的照樣要付（等待提醒還會催），只寫「已截止」會以為來不及、不用付了
        note = ""
        if line.key in closed and state == tp.WAIT_GOODS:
            note = "（收定金已截止）"
        elif line.key in closed and state == tp.AWAIT_DEPOSIT:
            note = "（收定金已截止，這筆已經下單，定金照樣要付）"
        rows.append(f"{line.name} ×{line.qty}　{emoji} {text}" + (f" {money(unit, due)}" if due else "") + note)
    embed = discord.Embed(title="交易進度", description="\n".join(rows) or "（沒有品項）", color=discord.Color.gold())
    paid = "｜".join(f"已收{_PAY_LABEL[kind]} {money(unit, amount)}" for kind, amount in prog.paid.items() if amount)
    if paid:
        embed.set_footer(text=paid)

    steps: list[Step] = []
    states = {line.state(prog.delivery) for line in prog.lines}
    for state, action, label in _CONFIRM_STEPS:
        if state in states:
            steps.append(Step(action, None, label, tp.SUPPLIER, version))
    kind = claim_kind(prog)
    if kind is not None:
        steps.append(Step(tp.CLAIM_PAID, None, f"我已付{_CLAIM_LABEL[kind]}", tp.REQUESTER, version))
    for line in prog.lines:
        state = line.state(prog.delivery)
        name = line.name[:60]
        if state == tp.AWAIT_DELIVERY:
            steps.append(Step(tp.DELIVER, line.key, f"📦 已交付：{name}", tp.SUPPLIER))
        elif state == tp.AWAIT_SHIPPING:
            steps.append(Step(tp.SHIP, line.key, f"📦 已寄出：{name}", tp.SUPPLIER))
        elif state == tp.SHIPPED_STATE:
            steps.append(Step(tp.RECEIVE, line.key, f"✅ 已收到：{name}", tp.REQUESTER))
    return embed, steps


@dataclass(frozen=True)
class Notified:
    """截止、延期通知發完的結果：通知了幾個對話；retry＝有對話一時取不到，還沒通知完、要下一輪再補。"""

    count: int
    retry: bool = False


_MONEY_RECEIVED = (tp.DEPOSIT_RECEIVED, tp.BALANCE_RECEIVED, tp.FULL_RECEIVED)

#: 交易進度上供應方確認收款的按鈕：(品項狀態, 動作, 按鈕文字)
_CONFIRM_STEPS = ((tp.AWAIT_DEPOSIT, tp.CONFIRM_DEPOSIT, "已收到定金（供應方）"),
                  (tp.AWAIT_BALANCE, tp.CONFIRM_BALANCE, "已收到尾款（供應方）"),
                  (tp.AWAIT_PAYMENT, tp.CONFIRM_FULL, "已收到款項（供應方）"))


class ListingTrades:
    """交易模組的來源種類：商品貼文。成交後商品保留、可以賣給很多人；取消時還回沒交付的數量。"""

    name = "listing"
    label = "商品貼文"

    def __init__(self, shop: "ShopService"):
        self.shop = shop

    @property
    def trade(self):
        return self.shop.trade

    async def _state(self, db: MarketDB, trade: TradeRow, delivery: str):
        items = await db.items(trade.id)
        events = await db.events(trade.id)
        return items, events, tp.progress(items, events, delivery=delivery)

    # ── 交易模組的 SourceKind ──

    async def opening(self, ref: TradeRef) -> tuple[str, str]:
        description = (f"需求方 <@{ref.requester_id}> 向供應方 <@{ref.supplier_id}> 下單了，"
                       "請在這裡討論交易細節。下單明細與交易進度在下面。")
        listing = await self.shop.load(ref.source_id)
        cancel = "只有供應方和群主可以取消交易；有爭議可以按「請群主協助」。"
        if listing.has_deposit():
            pay = "這筆要先付定金。需求方付了可以按「我已付定金」，供應方收到後按「已收到定金」；到貨後這裡會通知付尾款。"
        else:
            pay = "需求方付款後可以按「我已付款」，供應方收到後按「已收到款項」。"
        if listing.delivery == "physical":
            deliver = "每個品項寄出後，供應方在交易進度按「已寄出」，需求方收到後按「已收到」，全部收到就完成。"
        else:
            hours = self.trade.settings.receipt_timeout_hours
            deliver = (f"每個品項交付後，供應方在交易進度按它的「已交付」；全部交付後需求方按「已領收」即完成"
                       f"（{hours} 小時都沒按會自動完成）。")
        return description, pay + deliver + cancel

    async def deliver_rest(self, thread: discord.Thread, trade: TradeRow, actor_id: int) -> Optional[str]:
        """開單訊息上的「通知需求方領收」：剩下的品項一起交付（實體＝一起寄出），錢沒收齊就擋。"""
        db = await self.trade.db()
        listing = await self.shop.load(trade.source_id)
        items, events, prog = await self._state(db, trade, listing.delivery)
        reason = tp.allowed(prog, tp.DELIVER_REST)
        if reason is None:
            await self._apply(thread, trade, listing, items, prog, tp.DELIVER_REST, None, actor_id)
            return None
        if prog.money_done and prog.all_delivered and listing.delivery == "digital":
            if receipt_state(events).request is not None:
                hours = self.trade.settings.receipt_timeout_hours
                return f"已經通知需求方領收了，請等他確認（{hours} 小時都沒按會自動完成）。"
            # 需求方按過「還沒領收」、供應方補交後再按一次：重新發領收通知
            await self.trade.request_receipt_locked(thread, trade)
            return None
        await self.ensure_card(thread, trade, listing)
        if not prog.money_done:
            # 照舊習慣先按這顆的供應方最常卡在這：告訴他下一步按哪一顆
            states = [line.state(prog.delivery) for line in prog.lines if not line.money_done]
            hints = []
            confirm = [label for state, _, label in _CONFIRM_STEPS if state in states]
            if confirm:
                hints.append("收到錢後先在交易進度按" + "、".join(f"「{label}」" for label in confirm))
            if tp.WAIT_GOODS in states:
                hints.append("等貨的品項到貨後，在商品的管理面板按「📦 開始收尾款（準備交貨）」")
            if any(line.state(prog.delivery) in (tp.AWAIT_DELIVERY, tp.AWAIT_SHIPPING) for line in prog.lines):
                # 卡片上真的有那顆按鈕才提（錢收齊、還沒交付的品項）
                button = "已寄出" if listing.delivery == "physical" else "已交付"
                hints.append(f"錢收齊的品項可以先按它自己的「{button}」")
            return reason.replace("暫時不能交付", "暫時不能全部交付") + "\n" + "；".join(hints) + "。"
        return reason

    async def complete_blocker(self, trade: TradeRow) -> Optional[str]:
        """領收前的最後一道檢查：上線後的商品交易要每個品項都交付了才能完成；實體商品不走領收，要逐項按已收到。
        上線前的舊交易照舊流程（上線銜接期間【定金】商品還沒改好的除外，見 market_transition）。"""
        listing = await self.shop.load(trade.source_id)
        if trade.legacy:
            # 上線銜接：【定金】商品還沒改成定金＋尾款時先不能往下走（照舊流程做完就變成一次付清、沒有尾款）
            return transition.WAITS_TEXT if transition.waits_for_deposit(listing) else None
        db = await self.trade.db()
        _, _, prog = await self._state(db, trade, listing.delivery)
        if listing.delivery == "physical":
            return "實體商品要在交易進度上每個品項按「已收到」。"
        if not prog.all_delivered:
            return "還有品項沒交付，供應方交付完會再發領收通知。"
        return None

    async def on_complete(self, thread: discord.Thread, trade: TradeRow) -> str:
        """商品交易完成時在封存頻道留底：每筆下單（下單當時的金額）＋交易對話的連結，不附對話內容。

        封存頻道所有觀星者都看得到：價格公開透明，但對話裡可能有遊戲帳號、付款資料、寄送地址，
        只留在私人交易對話裡。成功就不說，沒保存到才請大家通知管理員，原因寫在 log。"""
        try:
            db = await self.trade.db()
            guild = getattr(thread, "guild", None) or await self.shop.guild()
            names = await self.trade.display_names(guild, (trade.requester_id, trade.supplier_id))
            requester = names.get(trade.requester_id) or str(trade.requester_id)
            supplier = names.get(trade.supplier_id) or str(trade.supplier_id)
            listing = await db.get_listing(trade.source_id)
            title = listing.title if listing else f"商品 {trade.source_id}"
            unit = listing.unit if listing else ""
            items = await db.items(trade.id)
            orders = []
            for event in await db.events(trade.id, kinds=[tp.ORDER]):
                when = datetime.fromisoformat(event.created_at).astimezone(APP_TZ)
                rows = [f"・{i.name} ×{i.qty}（" + (f"定金 {money(unit, i.unit_price)}，尾款 {money(unit, i.unit_balance or 0)}"
                                                    if i.kind == "deposit" else money(unit, i.unit_price))
                        + "）" + (f"，取消還回 {i.returned} 份" if i.returned else "")
                        for i in items if i.order_event_id == event.id]
                orders.append(f"🧾 {when:%Y-%m-%d %H:%M} 下單：\n" + "\n".join(rows))
            # 留底時交易對話已經鎖定封存、商品貼文也可能封存了：給連結，<#id> 會顯示成「# 不明」點不進去。
            # 交易對話是私人的，沒參與的人點了進不去，管理員可以直接點進去看
            conversation = masked_link("點這裡查看", thread.jump_url)
            summary = (f"商品：{thread_link(guild, trade.source_id, title)}\n"
                       f"需求方：{requester}　供應方：{supplier}\n"
                       f"完成時間：{self.trade.finished_at(trade).astimezone(APP_TZ):%Y-%m-%d %H:%M}\n"
                       f"交易對話：{conversation}\n\n" + "\n\n".join(orders))
            posted = await self.trade.post_archive(
                title=f"【市集】{title}｜{requester} 與 {supplier}"[:100], summary=summary, transcript="",
                filename=f"shop_{trade.source_id}_{trade.id}.txt")
        except Exception:  # 邊界：交易已經完成，留底失敗只在完成訊息裡請大家通知管理員
            logger.error("商品上架：交易留底失敗 thread=%s", trade.id, exc_info=True)
            return _RECORD_FAILED
        if not posted:
            logger.warning("商品上架：封存頻道沒有設定，交易沒有留底 thread=%s", trade.id)
            return _RECORD_FAILED
        return ""

    async def cancel_summary(self, trade: TradeRow) -> Optional[str]:
        db = await self.trade.db()
        items, events, prog = await self._state(db, trade, "digital")
        if not prog.any_paid:
            return None
        listing = await db.get_listing(trade.source_id)
        unit = listing.unit if listing else ""
        return "\n".join(f"・{_PAY_LABEL[kind]} {money(unit, amount)}（{self._paid_desc(prog, kind)}）"
                         for kind, amount in prog.paid.items() if amount)

    async def cancel_note(self, trade: TradeRow) -> str:
        db = await self.trade.db()
        # 照取消前的份數算（重啟後補收尾時，沒交付的份數已經還回去了，照樣要列出付了哪些）
        items = [replace(item, returned=0) for item in await db.items(trade.id)]
        events = await db.events(trade.id)
        prog = tp.progress(items, events, delivery="digital")
        listing = await db.get_listing(trade.source_id)
        unit = listing.unit if listing else ""
        parts = []
        if prog.any_paid:
            # 每一種錢各寫各的份數：加購那份沒付、或只付了定金的品項，不能被寫成已付
            paid = "；".join(f"{_PAY_LABEL[kind]}已付：{self._paid_desc(prog, kind)}，共 {money(unit, amount)}"
                            for kind, amount in prog.paid.items() if amount)
            parts.append(f"⚠️ {paid}。請雙方記得處理後續。")
        kept = [line for line in prog.lines if max(line.delivered, line.shipped)]
        if kept:
            parts.append("已交付或寄出的不還回：" + "、".join(
                f"{line.name} ×{max(line.delivered, line.shipped)}" for line in kept) + "。")
        return "\n".join(parts)

    async def on_cancel_tx(self, db: MarketDB, trade: TradeRow) -> None:
        """沒交付、沒寄出的份數還回商品；已交付或寄出的不還（貨已經在需求方手上或路上）。"""
        items, events, prog = await self._state(db, trade, "digital")
        give_back = {line.key: line.qty - max(line.delivered, line.shipped) for line in prog.lines}
        await db.return_items(trade.id, {key: qty for key, qty in give_back.items() if qty > 0})

    async def after_cancel(self, trade: TradeRow) -> None:
        async with self.shop.lock(trade.source_id):
            await self.shop.refresh_listing(trade.source_id)

    @staticmethod
    def _paid_desc(prog: tp.Progress, kind: str) -> str:
        field = {"deposit": "deposit_paid", "balance": "balance_paid", "full": "full_paid"}[kind]
        # 取消確認畫面、取消訊息、私訊最多三種錢各列一次，加起來要放得下一則
        return _join_capped([f"{line.name} ×{getattr(line, field)}" for line in prog.lines if getattr(line, field)],
                            _PAID_LIMIT)

    # ── 下單、交易進度卡 ──

    async def after_order(self, thread: discord.Thread, trade: TradeRow, listing: Listing, recorded,
                          created: bool) -> None:
        """下單寫進資料庫之後（拿著交易鎖）：發訂單明細、拿掉已作廢的領收通知上的按鈕、發新的交易進度。
        領收通知在寫訂單的同一個資料庫交易裡就作廢了（加購的東西不能跟著被自動領收）：這裡哪一步發失敗都不影響。"""
        if recorded.later_total:
            total = (f"定金合計 {money(listing.unit, recorded.now_total)}，"
                     f"到貨後尾款合計 {money(listing.unit, recorded.later_total)}")
        else:
            total = f"總計 {money(listing.unit, recorded.now_total)}"
        text = (f"🧾 <@{trade.requester_id}> 向 <@{trade.supplier_id}> {'下單' if created else '加購'}（{listing.title}）：\n"
                + "\n".join(f"・{row}" for row in recorded.rows) + f"\n{total}")
        # 新開的對話開單訊息已經 @ 過雙方；加購沒有開單訊息，@ 供應方一次
        await self.trade.send(thread, text, mention=() if created else (trade.supplier_id,))
        if recorded.retired_message_id:
            await self.trade.strip_notice(thread, recorded.retired_message_id,
                                          "（有新的加購，這次通知已作廢，請供應方交付後重新通知）")
        # 卡片上寫這次要付多少、付了按哪顆（名字照顯示、不另外 @：開單訊息或訂單明細已經通知過了）
        prompt = None
        if recorded.now_total:
            # 按鈕名稱照卡片上的寫：加購時同一個對話還有沒付的尾款，卡片上是一顆「我已付款」
            _, _, prog = await self._state(await self.trade.db(), trade, listing.delivery)
            kind = claim_kind(prog)
            what = "定金" if listing.has_deposit() else "款"
            button = f"我已付{_CLAIM_LABEL[kind]}" if kind else f"我已付{what}"
            which = "" if created else "這次加購的"
            prompt = (f"<@{trade.requester_id}> 請照供應方說的方式付{which}{what} {money(listing.unit, recorded.now_total)}。"
                      f"付了可以按「{button}」通知供應方。")
        await self.post_card(thread, trade, listing, prompt=prompt)

    async def adopt_legacy(self, trade_id: int, listing: Listing) -> bool:
        """上線前的舊交易接上新流程：品項的類型與尾款照商品現在的寫（金額照下單當時的）、標成新交易、記一筆 adopted
        （催款從這一刻起算），再補發交易進度、換掉開單訊息上的舊流程說明（`heal_adoption`，做到一半中斷時排程照它補）。
        只給還沒有任何收款、交付紀錄的交易用（舊流程本來就不記收款，上線時這些都還沒付）。回傳有沒有轉。"""
        async with self.trade.locked(trade_id) as trade:
            if trade is None or not trade.legacy or trade.source_kind != "listing":
                return False
            db = await self.trade.db()
            if not await db.items(trade.id):
                # 沒讀到訂單的舊交易：轉過來沒有任何品項、再也完成不了，留在舊流程照樣能領收
                return False
            async with db.transaction():
                picks: dict[int, int] = {}
                for item in await db.items(trade.id):
                    variant = listing.variant(item.variant_key)
                    if variant is not None:
                        await db.set_item_terms(trade.id, item.variant_key, kind=variant.kind,
                                                unit_balance=variant.balance if variant.deposit else None)
                    picks[item.variant_key] = picks.get(item.variant_key, 0) + item.qty - item.returned
                await db.adopt_legacy_trade(trade.id)
                # 舊流程的領收通知不算數了（新流程要先收款、交付才領收）
                await self.trade.supersede_receipt_tx(db, trade.id)
                await db.add_event(trade.id, tp.ADOPTED, now=self.shop.stamp(), items=picks)
            await self.heal_adoption(await db.get_trade(trade.id), listing)
            return True

    async def heal_adoption(self, trade: TradeRow, listing: Listing, thread: Optional[discord.Thread] = None) -> None:
        """（要拿著交易鎖）接上新流程後還沒補發的：換掉開單訊息的流程說明、拿掉作廢的舊領收通知上的按鈕、
        補發一張帶說明的交易進度（不 @ 人），發出去才在 adopted 那筆記下訊息編號。"""
        db = await self.trade.db()
        events = await db.events(trade.id)
        adopted = next((e for e in reversed(events) if e.kind == tp.ADOPTED), None)
        if adopted is None or adopted.message_id is not None:
            return
        thread = thread or await self.trade.get_thread(trade.id)
        if thread is None:
            return
        await self.trade.refresh_opening(thread, trade)
        for event in events:
            if event.kind == tp.RECEIPT_REQUESTED and event.message_id and event.id < adopted.id:
                await self.trade.strip_notice(thread, event.message_id, "（交易功能更新了，這則通知已作廢）")
        items, _, prog = await self._state(db, trade, listing.delivery)
        kind = claim_kind(prog)
        head = "🔄 交易功能更新了：這筆交易的進度改記在下面的交易進度，開單訊息上的流程說明也換成新的了。"
        if kind is None:
            prompt = head
        else:
            due = money(listing.unit, due_amount(prog, items, kind))
            what = "定金" if kind == "deposit" else _CLAIM_LABEL[kind]
            later = "，到貨後這裡會通知付尾款" if kind == "deposit" else ""
            prompt = (f"{head}請需求方照供應方說的方式付{what} {due}{later}；"
                      f"付了可以按「我已付{_CLAIM_LABEL[kind]}」通知供應方。")
        await self.post_card(thread, trade, listing, prompt=prompt, sent_event=adopted.id)

    async def post_card(self, thread: discord.Thread, trade: TradeRow, listing: Optional[Listing] = None, *,
                        prompt: Optional[str] = None, mention: Sequence[int] = (),
                        sent_event: Optional[int] = None) -> Optional[discord.Message]:
        """發一則新的交易進度（prompt 寫在卡片上面），上一則的按鈕收起來。要拿著交易鎖。
        sent_event：這則同時是哪一筆事件的通知（例：請尾款）；發出去就在同一個資料庫交易裡補上訊息編號。"""
        db = await self.trade.db()
        listing = listing or await self.shop.load(trade.source_id)
        items, events, prog = await self._state(db, trade, listing.delivery)
        version = tp.latest_state_event(events)
        embed, steps = render_card(prog, items, listing.unit, version=version, listing=listing)
        view = self.shop.views.progress(steps) if steps else None
        previous = (await db.get_trade(trade.id)).progress_message_id
        kwargs = {"embed": embed}
        if view is not None:
            kwargs["view"] = view
        message = await self.trade.send(thread, prompt, mention=mention, **kwargs)
        async with db.transaction():
            await db.set_progress_message(trade.id, message.id, version)
            if sent_event is not None:
                await db.set_event_message(sent_event, message.id)
        if previous:
            try:
                old = await thread.fetch_message(previous)
                await old.edit(view=None)
            except discord.HTTPException:
                logger.warning("商品上架：收起舊交易進度的按鈕失敗 thread=%s message=%s", thread.id, previous)
        return message

    async def ensure_card(self, thread: discord.Thread, trade: TradeRow, listing: Optional[Listing] = None) -> bool:
        """交易進度卡過期了（之後有改變狀態的事件，或根本還沒發出去）就重畫一張；要拿著交易鎖。回傳有沒有重畫。

        事件先寫進資料庫、卡片後發：卡片發失敗或剛好重啟，下一步的按鈕就只在那張沒發出去的卡上，交易會卡住。
        按按鈕時、通知需求方領收被擋時、等待提醒的排程每次醒來都檢查一次。"""
        db = await self.trade.db()
        row = await db.get_trade(trade.id)
        if row is None or row.status != "open" or row.legacy or row.source_kind != "listing":
            return False
        latest = tp.latest_state_event(await db.events(trade.id))
        if latest is None or (row.progress_message_id is not None and (row.progress_event_id or 0) >= latest):
            return False
        await self.post_card(thread, row, listing)
        return True

    async def heal_receipt(self, thread: discord.Thread, trade: TradeRow, listing: Listing) -> bool:
        """數位商品全部交付了卻沒有有效的領收通知（最後那則沒發出去、或剛好重啟），也不是需求方說還沒領收：
        補發一則。要拿著交易鎖。回傳有沒有補發。"""
        if trade.legacy or listing.delivery != "digital":
            return False
        db = await self.trade.db()
        items, events, prog = await self._state(db, trade, listing.delivery)
        if not prog.lines or not prog.all_delivered or receipt_state(events).request is not None:
            return False
        if tp.held_by_requester(events) is not None:
            return False   # 需求方說還沒領收、之後也沒有新的交付：等供應方補交後自己再按通知
        await self.trade.request_receipt_locked(thread, trade)
        return True

    async def heal_completion(self, thread: discord.Thread, trade: TradeRow, listing: Listing) -> bool:
        """實體商品每個品項都按了已收到、交易卻還開著（最後一個已收到寫進去後剛好重啟）：補做完成。要拿著交易鎖。"""
        if trade.legacy or listing.delivery != "physical":
            return False
        db = await self.trade.db()
        _, _, prog = await self._state(db, trade, listing.delivery)
        if not prog.lines or not prog.all_received:
            return False
        await self.trade.complete_locked(thread, trade, auto=False, how=f"需求方 <@{trade.requester_id}> 已收到全部品項")
        return True

    # ── 交易進度上的按鈕 ──

    async def handle_step(self, user, thread: discord.Thread, action: str, key: Optional[int],
                          version: Optional[int] = None) -> Optional[str]:
        """按下交易進度上的按鈕。做完回 None；不能做回給按的人看的理由。呼叫端要先回應互動（defer）。

        version 是按鈕所在那張卡照到哪一筆事件畫的：確認收款、我已付只算那張卡上看得到的份數。"""
        if not self.trade.ready.is_set():
            return NOT_READY_TEXT
        db = await self.trade.db()
        async with self.trade.locked(thread.id) as trade:
            if trade is None:
                return "這筆交易已經結束。" if await db.get_trade(thread.id) else NO_RECORD_TEXT
            if trade.source_kind != "listing" or trade.legacy:
                return "這個按鈕已經不能用了。"
            who = tp.actor_of(action)
            need = trade.requester_id if who == tp.REQUESTER else trade.supplier_id
            if user.id != need:
                return f"只有{'需求方' if who == tp.REQUESTER else '供應方'} <@{need}> 可以按這個按鈕。"
            listing = await self.shop.load(trade.source_id)
            items, events, prog = await self._state(db, trade, listing.delivery)
            if version is not None and action == tp.CLAIM_PAID and any(
                    e.kind in _MONEY_RECEIVED and e.id > version for e in events):
                # 卡片畫好之後供應方確認過收款：卡上的「我已付定金」可能已經變成該付尾款，照現況算會把付定金
                # 說成付了尾款。請需求方看新的那張（下面 ensure_card 會畫好）
                await self.ensure_card(thread, trade, listing)
                return "交易進度剛更新過（供應方確認了收款），請看最新的交易進度再按。"
            if version is not None and action in (tp.CLAIM_PAID, tp.CONFIRM_DEPOSIT, tp.CONFIRM_BALANCE,
                                                  tp.CONFIRM_FULL):
                # 卡片畫好之後才有的下單、請款都不算；已收到的錢照現在的（不會重複記）
                items = [item for item in items if item.order_event_id <= version]
                events = [e for e in events if not (e.kind in (tp.ORDER, tp.BALANCE_REQUESTED) and e.id > version)]
                prog = tp.progress(items, events, delivery=listing.delivery)
            reason = tp.allowed(prog, action, key)
            if reason is None:
                await self._apply(thread, trade, listing, items, prog, action, key, user.id, version=version)
            await self.ensure_card(thread, trade, listing)
            return reason

    async def _apply(self, thread: discord.Thread, trade: TradeRow, listing: Listing, items, prog: tp.Progress,
                     action: str, key: Optional[int], actor_id: int, *, version: Optional[int] = None) -> None:
        """允許表已經放行：寫事件、發訊息、畫新的交易進度（要拿著交易鎖）。"""
        db = await self.trade.db()
        unit = listing.unit
        req, sup = trade.requester_id, trade.supplier_id
        picks = tp.pending_for(prog, action, key)
        desc = _describe(prog, picks)
        now = self.shop.stamp()

        if action == tp.CLAIM_PAID:
            # 只算還沒按過「我已付」的品項：前面按過、供應方還沒確認的不重算
            kind = claim_kind(prog, picks)
            amount = due_amount(prog, items, kind, picks)
            async with db.transaction():
                # source 記按的是哪一版的卡：舊卡上按的，只算那張卡畫好之前的份數
                await db.add_event(trade.id, tp.PAID_CLAIM, now=now, items=picks, reference=kind, amount=amount,
                                   actor_id=actor_id, source=f"v{version}" if version is not None else None)
            # 定金與尾款一起付（不同品項在不同階段）時，卡上是兩顆確認按鈕
            button = "「已收到定金」和「已收到尾款」" if kind == "mixed" else f"「已收到{_PAY_LABEL[kind]}」"
            await self.trade.send(thread, f"<@{sup}>，<@{req}> 表示已付{_CLAIM_LABEL[kind]} {money(unit, amount)}"
                                          f"（{desc}），確認收到後請按交易進度上的{button}。", mention=(sup,))
            return

        if action in (tp.CONFIRM_DEPOSIT, tp.CONFIRM_BALANCE, tp.CONFIRM_FULL):
            kind, event_kind, field, done_attr = {
                tp.CONFIRM_DEPOSIT: ("deposit", tp.DEPOSIT_RECEIVED, "unit_price", "deposit_paid"),
                tp.CONFIRM_BALANCE: ("balance", tp.BALANCE_RECEIVED, "unit_balance", "balance_paid"),
                tp.CONFIRM_FULL: ("full", tp.FULL_RECEIVED, "unit_price", "full_paid"),
            }[action]
            amount = sum(_amount(items, k, field, getattr(prog.line(k), done_attr), qty) for k, qty in picks.items())
            async with db.transaction():
                # source＝誰確認的：m＝供應方按的；串金流後由金流通知寫，同一個函式
                await db.add_event(trade.id, event_kind, now=now, items=picks, amount=amount, actor_id=actor_id,
                                   source="m")
            text = f"✅ <@{req}> 供應方已確認收到{_PAY_LABEL[kind]} {money(unit, amount)}（{desc}）。"
            _, _, after = await self._state(db, trade, listing.delivery)
            if kind == "deposit":
                balance_due = due_amount(after, items, "balance")
                text += (f"接著請付尾款 {money(unit, balance_due)}，付了可以按「我已付尾款」。" if balance_due
                         else "到貨後會在這裡通知付尾款。")
            await self.post_card(thread, trade, listing, prompt=text, mention=(req,))
            return

        if action in (tp.DELIVER, tp.SHIP, tp.DELIVER_REST):
            physical = listing.delivery == "physical"
            async with db.transaction():
                await db.add_event(trade.id, tp.SHIPPED if physical else tp.DELIVERED, now=now, items=picks,
                                   actor_id=actor_id)
            _, _, after = await self._state(db, trade, listing.delivery)
            if physical:
                text = f"📦 <@{req}> 供應方已寄出 {desc}。收到後請按交易進度上的「已收到」。"
                await self.post_card(thread, trade, listing, prompt=text, mention=(req,))
                return
            if after.all_delivered:
                await self.post_card(thread, trade, listing, prompt=f"📦 供應方已交付 {desc}。全部品項都交付了。")
                await self.trade.request_receipt_locked(thread, trade)
                return
            rest = _join_capped([line.name for line in after.lines if line.delivered < line.qty], _REST_LIMIT)
            await self.post_card(thread, trade, listing, mention=(req,),
                                 prompt=f"📦 <@{req}> 供應方已交付 {desc}。{rest} 還沒交付，這個交易對話會繼續開著。")
            return

        if action == tp.RECEIVE:
            async with db.transaction():
                await db.add_event(trade.id, tp.RECEIVED, now=now, items=picks, actor_id=actor_id)
            _, _, after = await self._state(db, trade, listing.delivery)
            if after.all_received:
                await self.trade.complete_locked(thread, trade, auto=False, how=f"需求方 <@{req}> 已收到全部品項")
                return
            await self.post_card(thread, trade, listing, prompt=f"✅ <@{sup}> 需求方已收到 {desc}。", mention=(sup,))
            return
        raise ValueError(f"不認得的交易進度動作：{action}")

    # ── 截止、延期、開始收尾款（商品服務拿著商品鎖時叫）──

    async def announce_ready(self, listing: Listing, variant: Variant, *, how: str, reference: str) -> Notified:
        """一次付清的預購截止（或供應方按開始交貨）：每個買了它、還在進行的交易對話 @ 雙方可以開始交貨。
        how：cutoff＝時間到截止；early＝截止前提早開始交貨；arrived＝截止後延期、貨提早到。
        reference 是去重用的記號（同一件事重跑不重發，不同的事要用不同的記號）。"""
        what = "寄出" if listing.delivery == "physical" else "交付"

        async def notify(thread, current):
            people = f"<@{current.requester_id}> <@{current.supplier_id}>"
            if how == "arrived":
                head = f"⏩ {people} 「{variant.name}」的貨提早到了，"
            elif how == "early":
                head = f"⏩ {people} 供應方提早開始交貨：預購「{variant.name}」停止下單，"
            elif variant.expected_at is not None:
                # 截止通知還沒補完就延期了：照延期後的日子講，不能說「可以開始交貨」（跟剛收到的延期通知矛盾）
                await self.trade.send(
                    thread, f"⏰ {people} 預購「{variant.name}」已截止（{format_cutoff(variant.cutoff)}），停止下單；"
                            f"預計 {format_date(variant.expected_at)} 交貨。",
                    mention=(current.requester_id, current.supplier_id))
                return
            else:
                head = f"⏰ {people} 預購「{variant.name}」已截止（{format_cutoff(variant.cutoff)}），"
            if current.legacy:
                # 上線前開的舊交易沒有交易進度，照舊流程交付後按開單訊息上的按鈕
                tail = f"可以開始交貨。供應方{what}後請按開單訊息上的「通知需求方領收」。"
            else:
                tail = f"可以開始交貨。供應方{what}後會在交易進度按「已{what}」。"
            await self.trade.send(thread, head + tail, mention=(current.requester_id, current.supplier_id))

        return await self._notify_all(listing, variant, tp.CUTOFF_NOTICE, reference, notify, delivered=False)

    async def mark_deposit_closed(self, listing: Listing, variant: Variant) -> Notified:
        """定金品項收定金截止：不 @ 人，每個買了它的對話重畫交易進度（標成收定金已截止）。listing 要是截止後重讀的。"""

        async def redraw(thread, current):
            await self.post_card(thread, current, listing)

        return await self._notify_all(listing, variant, tp.CUTOFF_NOTICE, str(variant.key), redraw, legacy=False)

    async def announce_delay(self, listing: Listing, variant: Variant, *, what: str, shown: str, number: int,
                             reason: str) -> Notified:

        async def notify(thread, current):
            text = (f"📅 <@{current.requester_id}> 供應方把「{variant.name}」的{what}延後到 {shown}（第 {number} 次延期）。"
                    + (f"原因：{reason}。" if reason else "") + "有問題可以直接在這裡跟供應方討論。")
            await self.trade.send(thread, text, mention=(current.requester_id,))

        return await self._notify_all(listing, variant, tp.DELAY_NOTICE, f"{variant.key}:{number}", notify,
                                      delivered=False)

    async def _notify_all(self, listing: Listing, variant: Variant, kind: str, reference: str, notify, *,
                          legacy: bool = True, delivered: bool = True) -> Notified:
        """每個買了這個品項、還在進行的交易對話通知一次。legacy=False＝跳過上線前的舊交易；
        delivered=False＝這個品項在那筆交易裡已經全部交付或寄出的跳過（截止前就先交貨了，不用再說可以開始交貨、延期）。"""
        count, retry = 0, False
        db = await self.trade.db()
        for trade, _ in await self.shop._open_trades_for_variant(listing.thread_id, variant.key):
            if trade.legacy and (not legacy or transition.waits_for_deposit(listing)):
                # 還在等整篇改成定金＋尾款的舊交易：改好接上新流程時會補發交易進度，現在講截止、交貨只會照舊流程走
                continue
            if not delivered and not trade.legacy:
                _, _, prog = await self._state(db, trade, listing.delivery)
                line = prog.line(variant.key)
                done = (line.shipped if prog.delivery == "physical" else line.delivered) if line else 0
                if line is not None and done >= line.qty:
                    continue
            sent = await self._notify_once(trade, kind, reference, notify)
            if sent is None:
                retry = True
            elif sent:
                count += 1
        return Notified(count, retry)

    async def _notify_once(self, trade: TradeRow, kind: str, reference: str, notify) -> Optional[bool]:
        """在交易鎖裡：這件事沒通知過就先記事件、再發。一個對話壞了不影響其他對話。
        回傳 True＝發了；False＝不用發（通知過、交易結束、對話不在了）或發的時候出錯（事件已記，不重發）；
        None＝對話一時取不到、什麼都還沒記，下一輪再試。"""
        try:
            async with self.trade.locked(trade.id) as current:
                if current is None:
                    return False
                db = await self.trade.db()
                if any(e.reference == reference for e in await db.events(current.id, kinds=[kind])):
                    return False
                try:
                    thread = await self.trade.get_thread(current.id, raise_errors=True)
                except discord.Forbidden:
                    logger.warning("商品上架：沒有權限讀交易對話 %s，沒有通知", current.id)
                    return False
                except Exception:  # 邊界：Discord 暫時取不到對話，這個對話下一輪再補，不影響其他對話
                    logger.warning("商品上架：一時取不到交易對話 %s，下一輪再通知", current.id, exc_info=True)
                    return None
                if thread is None:
                    logger.warning("商品上架：找不到交易對話 %s，沒有通知", current.id)
                    return False
                async with db.transaction():
                    await db.add_event(current.id, kind, now=self.shop.stamp(), reference=reference)
                await notify(thread, current)
                return True
        except Exception:  # 邊界：一個交易對話發不出去，不影響其他對話；事件已記，不會每次醒來重複 @
            logger.error("商品上架：通知交易對話失敗 thread=%s 事件=%s", trade.id, kind, exc_info=True)
            return False

    async def balance_plan(self, listing_id: int, key: int) -> list[BalanceRow]:
        """開始收尾款要通知哪些交易對話、各多少（還沒請過款的份數，或請過款但通知沒發出去的）。"""
        db = await self.trade.db()
        plan = []
        for trade, _ in await self.shop._open_trades_for_variant(listing_id, key):
            if trade.legacy:
                continue
            row = await self._balance_row(db, trade, key)
            if row is not None:
                plan.append(row)
        return plan

    async def _balance_row(self, db: MarketDB, trade: TradeRow, key: int) -> Optional[BalanceRow]:
        items, events, prog = await self._state(db, trade, "digital")
        line = prog.line(key)
        if line is None or not line.deposit:
            return None
        need = line.qty - line.balance_requested
        unsent = self._unsent_request(events, key)
        if need <= 0 and (unsent is None or line.balance_paid >= line.balance_requested):
            # 沒發出去的請款，錢已經收了（卡片先重畫、供應方照卡片確認過）就不再補發「請付尾款」
            return None
        if need > 0:
            units = _units(items, key, "unit_balance")[line.balance_requested:line.balance_requested + need]
            qty = need
        else:
            qty = int((unsent.items or {}).get(key, 0))
            units = _units(items, key, "unit_balance")[line.balance_requested - qty:line.balance_requested]
        return BalanceRow(trade, qty, sum(units), max(0, line.qty - line.deposit_paid), tuple(sorted(set(units))))

    @staticmethod
    def _unsent_request(events, key: int):
        return next((e for e in reversed(events) if e.kind == tp.BALANCE_REQUESTED and e.message_id is None
                     and key in (e.items or {})), None)

    async def request_balances(self, listing: Listing, key: int) -> list[BalanceRow]:
        """在每個買了這個品項的交易對話請尾款：先記請款，發出通知後補上訊息編號；已經請過、發過的不重發。"""
        variant = listing.variant(key)
        name = variant.name if variant else f"品項 {key}"
        done = []
        for trade, _ in await self.shop._open_trades_for_variant(listing.thread_id, key):
            if trade.legacy:
                continue
            try:
                async with self.trade.locked(trade.id) as current:
                    if current is None:
                        continue
                    db = await self.trade.db()
                    row = await self._balance_row(db, current, key)
                    if row is None:
                        continue
                    items, events, prog = await self._state(db, current, listing.delivery)
                    line = prog.line(key)
                    event = self._unsent_request(events, key)
                    if line.qty - line.balance_requested > 0:
                        async with db.transaction():
                            event_id = await db.add_event(current.id, tp.BALANCE_REQUESTED, now=self.shop.stamp(),
                                                          items={key: row.qty}, amount=row.amount,
                                                          actor_id=current.supplier_id)
                    else:
                        event_id = event.id
                    thread = await self.trade.get_thread(current.id)
                    if thread is None:
                        logger.warning("商品上架：請尾款時找不到交易對話 %s", current.id)
                        continue
                    req, sup = current.requester_id, current.supplier_id
                    if row.unconfirmed:
                        text = (f"📦 「{name}」到貨了。<@{sup}> 這筆的定金還沒確認，收到定金後請先按「已收到定金」，"
                                f"再向 <@{req}> 收尾款 {money(listing.unit, row.amount)}。")
                        mention = (sup,)
                    else:
                        text = (f"📦 <@{req}> 「{name}」到貨了，請付尾款 {money(listing.unit, row.amount)}（×{row.qty}）。"
                                "付了可以按「我已付尾款」通知供應方。")
                        mention = (req,)
                    await self.post_card(thread, current, listing, prompt=text, mention=mention, sent_event=event_id)
                    done.append(row)
            except Exception:  # 邊界：一個交易對話請款失敗不影響其他對話；沒發出去的由截止排程補發
                logger.error("商品上架：請尾款失敗 thread=%s 品項=%s", trade.id, key, exc_info=True)
        return done

    async def deposit_counts(self, listing_id: int) -> dict[int, tuple[int, int, int]]:
        """管理面板上每個定金品項的進度：(下單份數, 已確認定金, 已付尾款)；取消的交易不算。"""
        db = await self.trade.db()
        counts: dict[int, list[int]] = {}
        for trade in await db.trades(source_id=listing_id, source_kind="listing"):
            if trade.status not in ("open", "completed"):
                continue
            _, _, prog = await self._state(db, trade, "digital")
            for line in prog.lines:
                if line.deposit:
                    row = counts.setdefault(line.key, [0, 0, 0])
                    row[0] += line.qty
                    row[1] += line.deposit_paid
                    row[2] += line.balance_paid
        return {key: tuple(row) for key, row in counts.items()}

    # ── 等待提醒（utils.due_loop 每次醒來呼叫）──

    async def run_waiting_reminders(self, now: datetime) -> Optional[datetime]:
        """有人卡著才提醒：時間表在 `trade_progress.due_reminders`。回傳下一次要醒來的時刻。"""
        if not self.trade.ready.is_set():
            return now + timedelta(minutes=1)
        db = await self.trade.db()
        next_due: Optional[datetime] = None
        listings: dict[int, Listing] = {}
        for trade in await db.trades(status="open", source_kind="listing"):
            if trade.legacy:
                continue  # 上線前的舊交易只進週報與看板，不在對話裡提醒
            try:
                listing = listings.get(trade.source_id) or await self.shop.load(trade.source_id)
                listings[trade.source_id] = listing
                wake = await self._remind(trade.id, listing, now)
                if wake is not None:
                    next_due = wake if next_due is None else min(next_due, wake)
            except Exception:  # 邊界：排程的一筆交易，壞了不影響其他交易，下一輪再試
                logger.error("商品上架：等待提醒失敗 thread=%s", trade.id, exc_info=True)
        return next_due

    @staticmethod
    def _ready_at(listing: Listing) -> dict[int, datetime]:
        """預購品項可以開始交貨的時刻：在那之前不催交貨。"""
        return {v.key: ready_at(v) for v in listing.variants if ready_at(v) is not None}

    async def _remind(self, trade_id: int, listing: Listing, now: datetime) -> Optional[datetime]:
        async with self.trade.locked(trade_id) as trade:
            if trade is None:
                return None
            thread = await self.trade.get_thread(trade.id)
            if thread is None:
                logger.warning("商品上架：等待提醒找不到交易對話 %s", trade.id)
                return None
            if await self.heal_completion(thread, trade, listing):
                return None
            await self.heal_adoption(trade, listing, thread)
            await self.ensure_card(thread, trade, listing)
            await self.heal_receipt(thread, trade, listing)
            db = await self.trade.db()
            items, events, prog = await self._state(db, trade, listing.delivery)
            due, wake = tp.due_reminders(prog, events, now=now, ready_at=self._ready_at(listing))
            if not due:
                return wake
            text, mention = self._reminder_text(trade, listing, prog, due)
            async with db.transaction():
                for reminder in due:
                    await db.add_event(trade.id, tp.REMINDER, now=self.shop.stamp(), reference=reminder.reference,
                                       items={reminder.key: 1})
            await self.trade.send(thread, text, mention=mention)
            _, wake = tp.due_reminders(prog, await db.events(trade.id), now=now, ready_at=self._ready_at(listing))
            return wake

    @staticmethod
    def _reminder_text(trade: TradeRow, listing: Listing, prog: tp.Progress, due) -> tuple[str, tuple[int, ...]]:
        req, sup = trade.requester_id, trade.supplier_id
        physical = listing.delivery == "physical"
        parts: list[str] = []
        mention: list[int] = []
        for reminder in due:
            line = prog.line(reminder.key)
            name = line.name if line else f"品項 {reminder.key}"
            if reminder.reason == "pay":
                state = line.state(prog.delivery)
                what = {tp.AWAIT_DEPOSIT: "定金", tp.AWAIT_BALANCE: "尾款"}.get(state, "款")
                # 按鈕名稱跟卡片上的一樣：定金、尾款都有人還沒付時，卡片上只有一顆「我已付款」
                button = f"我已付{_CLAIM_LABEL[claim_kind(prog) or _STATE_PAY.get(state, 'full')]}"
                part = (f"「{name}」還沒付{what}（第 {reminder.number} 次提醒）。"
                        f"付了請按交易進度上的「{button}」，有問題請跟供應方討論。")
                who = (req,)
            elif reminder.reason == "confirm":
                part = "需求方表示已付款，確認收到後請按交易進度上的「已收到」。"
                who = (sup,)
            elif reminder.reason == "redeliver":
                part = "需求方表示還沒領收。補交後請按開單訊息上的「通知需求方領收」，有問題請雙方在這裡溝通。"
                who = (sup,)
            elif reminder.reason == "deliver":
                button = "已寄出" if physical else "已交付"
                part = f"「{name}」的錢收齊了，{button[1:]}後請按交易進度上的「{button}：{name}」。"
                who = (sup,)
            else:
                days = reminder.days or 7 + 3 * (reminder.number - 1)
                part = (f"「{name}」寄出超過 {days} 天，需求方還沒按收到。收到了請按「已收到：{name}」；"
                        "有問題請雙方在這裡溝通，沒成交請取消交易。")
                who = (req, sup)
            if part not in parts:
                parts.append(part)
            mention += [i for i in who if i not in mention]
        head = "⏰ " + " ".join(f"<@{i}>" for i in mention)
        return head + "\n" + "\n".join(f"・{part}" for part in parts), tuple(mention)
