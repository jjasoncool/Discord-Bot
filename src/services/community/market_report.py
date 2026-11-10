"""市集的交易統計：週報（週一中午私訊有待辦的觀星者）、「📋 我的交易」、主控台的交易看板。三個讀同一份整理，數字一致。

架構定位：功能層（`services.community`）。
  - 上層（誰呼叫）：介面 `commands.shop_commands`（週報的排程、置頂說明的「📋 我的交易」）、
    `commands.admin_console`（群主的交易看板，經 ShopCommands 取用）。
  - 下層（呼叫誰）：市集資料庫（交易、品項、事件、週報紀錄）、`trade_progress`（每個品項到哪一步）、
    交易模組（讀交易對話找最後一則真人訊息、取成員、私訊）。

介面：
  - `summarize(shop, now)` → 每筆還沒結束的交易一個 `TradeSummary`（要供應方處理的事、在等什麼、開了幾天、幾天沒動靜）。
  - `my_trades_text(summaries, supplier_id)`：一位供應方的清單（「📋 我的交易」、看板點進去的畫面）。
  - `weekly_text(summaries, supplier_id, now)`：一位供應方的週報；沒有待辦回 None。
  - `run_weekly(shop, now)`：週報的排程（`utils.due_loop` 每次醒來呼叫）。
  - `dashboard_text(shop, summaries, now)`：群主看板的總表。

規則：
  - 「沒動靜」只算真人講話與交易紀錄；提醒、截止與延期的通知不算（不然一直提醒，對話就永遠不會沒動靜）。
  - 每筆交易寫成交易對話的連結（`trade_service.thread_link`），字是標題加需求方：週報在私訊裡、對話會封存，
    `<#id>` 在那裡顯示成「# 不明」點不進去；同一篇商品有好幾位需求方時，靠名字分得出是哪一筆。
  - 週報太長時從換行處截掉，結尾照樣留「全部清單」那句（太長時最需要指路去看全部）。
  - 週報只給有待辦的觀星者，群主不收；每週一份、記在資料庫，重啟不重發；週一 23:59 前開機會補發，過了等下週。
  - 上線前的舊交易算待辦（沒有交易進度，只能請供應方自己完成或取消）。第一版不統計金額。
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import TYPE_CHECKING, Optional, Sequence

import discord

from services.community import trade_progress as tp
from services.community.market_import import UNRECOGNIZED_META
from services.community import market_transition as transition
from services.community.shop_trade import ready_at
from services.community.trade_service import party_name, receipt_state, thread_link
from sys_settings.time_settings import APP_TZ
from utils.discord_content import masked_link, split_message
from utils.dm_notifier import send_dm

if TYPE_CHECKING:
    from services.community.shop_service import ShopService

logger = logging.getLogger(__name__)

#: 多久沒動靜算卡住
IDLE_DAYS = 14
#: 實體商品寄出多久還沒按收到要列出來
SHIPPED_DAYS = 7
#: 週報在週一幾點發
WEEKLY_AT = time(12, 0)
#: 週報說明欄的上限（Discord 是 4096，留一點餘裕）
_WEEKLY_LIMIT = 4000
_ALL_TRADES_HINT = "全部清單：在商品論壇置頂說明按「📋 我的交易」。"
_CUT_NOTE = f"\n…（太長，後面截掉）\n{_ALL_TRADES_HINT}"
#: 這些事件是 bot 自己發的通知，不算「有動靜」
#: 接上新流程（adopted）算動靜：舊交易從那一刻重新算，不然一上線就整批算成「超過 14 天沒動靜」被週報催
_NOT_ACTIVITY = {tp.REMINDER, tp.RECEIPT_REMINDED, tp.CUTOFF_NOTICE, tp.DELAY_NOTICE}


@dataclass
class TradeSummary:
    trade_id: int
    supplier_id: int
    requester_id: int
    title: str
    legacy: bool
    days_open: int
    days_idle: int
    todo: list[str] = field(default_factory=list)      # 要供應方處理的事
    waiting: Optional[str] = None                       # 不用供應方處理時在等什麼
    #: 每個品項都在等貨：本來就會安靜好幾個月，不算「沒動靜」（不然等貨的交易兩週後每週都被週報催）
    waiting_for_goods: bool = False
    link: str = ""                                      # 清單上的那一筆：交易對話的連結，字是標題加需求方

    @property
    def idle(self) -> bool:
        return self.days_idle >= IDLE_DAYS and not self.waiting_for_goods

    @property
    def needs_supplier(self) -> bool:
        return bool(self.todo) or self.legacy or self.idle


def _days(since: datetime, now: datetime) -> int:
    return max(0, (now - since).days)


async def summarize(shop: "ShopService", now: datetime, *, supplier_id: Optional[int] = None) -> list[TradeSummary]:
    """每筆還沒結束的交易（商品與自由市場都算）整理成一列；給 supplier_id 就只整理那一位的。"""
    trade_service = shop.trade
    db = await trade_service.db()
    listings: dict[int, object] = {}
    summaries = []
    trades = await db.trades(status="open", supplier_id=supplier_id)
    guild = await shop.guild()
    names = await trade_service.display_names(guild, (trade.requester_id for trade in trades))
    for trade in trades:
        events = await db.events(trade.id)
        title = "自由市場需求"
        listing = None
        if trade.source_kind == "listing":
            if trade.source_id not in listings:
                try:
                    listings[trade.source_id] = await shop.load(trade.source_id)
                except Exception:  # 邊界：一篇商品讀不到只影響那幾筆的標題與狀態，清單照出
                    logger.warning("市集統計：讀不到商品 %s", trade.source_id, exc_info=True)
                    listings[trade.source_id] = None
            listing = listings[trade.source_id]
            title = listing.title if listing else f"商品 {trade.source_id}"
        last = max((datetime.fromisoformat(e.created_at) for e in events if e.kind not in _NOT_ACTIVITY),
                   default=datetime.fromisoformat(trade.opened_at))
        if trade.last_chat_at and datetime.fromisoformat(trade.last_chat_at) > last:
            last = datetime.fromisoformat(trade.last_chat_at)
        # 找不到伺服器就查不到名字，只寫標題（不然每一位都會被寫成已離開）
        label = f"{title}｜{party_name(names, trade.requester_id)}" if guild is not None else title
        summary = TradeSummary(trade.id, trade.supplier_id, trade.requester_id, title, trade.legacy,
                               _days(datetime.fromisoformat(trade.opened_at), now), _days(last, now),
                               link=thread_link(guild, trade.id, label))
        _classify(summary, trade, listing, await db.items(trade.id), events, now)
        summaries.append(summary)
    return summaries


def _classify(summary: TradeSummary, trade, listing, items, events, now: datetime) -> None:
    if trade.legacy:
        if transition.waits_for_deposit(listing):
            # 上線銜接：照舊流程做完就變成一次付清、沒有尾款，先把商品改好，這筆會接上新流程
            summary.todo.append(transition.TODO_TEXT)
        else:
            summary.todo.append("上線前開的交易：交付了請按「通知需求方領收」，沒成交請取消")
        return
    if trade.source_kind != "listing" or listing is None:
        if receipt_state(events).request is not None:
            summary.waiting = "等需求方領收"
        else:
            summary.todo.append(f"交付後按「通知需求方領收」（開了 {summary.days_open} 天）")
        return
    prog = tp.progress(items, events, delivery=listing.delivery)
    # 每件待辦從哪一刻開始等（清單上寫等了幾天，不是交易開了幾天：定金交易一開就是好幾個月）
    shipped_at: dict[int, datetime] = {}
    claimed_at: dict[int, datetime] = {}
    paid_at: dict[int, datetime] = {}
    delivered_at: Optional[datetime] = None
    for event in events:
        when = datetime.fromisoformat(event.created_at)
        keys = [int(key) for key in event.items or {}]
        if event.kind == tp.SHIPPED:
            shipped_at.update(dict.fromkeys(keys, when))
        elif event.kind == tp.PAID_CLAIM:
            claimed_at.update(dict.fromkeys(keys or [line.key for line in prog.lines], when))
        elif event.kind in (tp.BALANCE_RECEIVED, tp.FULL_RECEIVED):
            paid_at.update(dict.fromkeys(keys, when))
        elif event.kind == tp.DELIVERED:
            delivered_at = when
    held = tp.held_by_requester(events)

    def waited(since: Optional[datetime]) -> str:
        return f"（{_days(since, now)} 天）" if since is not None else ""
    variants = {v.key: v for v in listing.variants}
    waiting = []
    for line in prog.lines:
        state = line.state(prog.delivery)
        variant = variants.get(line.key)
        # 跟等待提醒用同一個時刻：截止（或延期後的預計交貨日）之前不算該交貨
        ready = ready_at(variant) if variant is not None else None
        not_ready = ready is not None and now < ready
        if state in (tp.AWAIT_DEPOSIT, tp.AWAIT_BALANCE, tp.AWAIT_PAYMENT):
            what = {tp.AWAIT_DEPOSIT: "定金", tp.AWAIT_BALANCE: "尾款"}.get(state, "款")
            if line.claimed:
                summary.todo.append(f"{line.name}：需求方表示已付{what}，等你確認{waited(claimed_at.get(line.key))}")
            else:
                waiting.append("等需求方付款")
        elif state == tp.WAIT_GOODS or (state in (tp.AWAIT_DELIVERY, tp.AWAIT_SHIPPING) and not_ready):
            waiting.append("等貨中")
        elif state in (tp.AWAIT_DELIVERY, tp.AWAIT_SHIPPING):
            # 錢收齊之後才輪到交付；預購要等到可以交貨的那一刻
            since = max(filter(None, (paid_at.get(line.key), ready)), default=None)
            verb = "交付" if state == tp.AWAIT_DELIVERY else "寄出"
            summary.todo.append(f"{line.name}：錢收齊，等你{verb}{waited(since)}")
        elif state == tp.SHIPPED_STATE:
            days = _days(shipped_at.get(line.key, now), now)
            if days >= SHIPPED_DAYS:
                summary.todo.append(f"{line.name}：寄出 {days} 天，需求方還沒按收到")
            else:
                waiting.append("等需求方收貨")
    if prog.lines and prog.all_delivered and listing.delivery == "digital":
        if receipt_state(events).request is not None:
            waiting.append("等需求方領收")
        elif held is not None:
            since = datetime.fromisoformat(held.created_at)
            summary.todo.append(f"需求方表示還沒領收，補交後按「通知需求方領收」{waited(since)}")
        else:
            summary.todo.append(f"全部交付了，按「通知需求方領收」{waited(delivered_at)}")
    summary.waiting = waiting[0] if waiting else None
    summary.waiting_for_goods = bool(waiting) and not summary.todo and all(w == "等貨中" for w in waiting)


def _line(summary: TradeSummary) -> str:
    return f"・{summary.link}"


def my_trades_text(summaries: Sequence[TradeSummary], supplier_id: int, *, name: Optional[str] = None) -> str:
    """一位供應方的清單。給 name＝群主在看板看別人的（「他」，標題寫是誰），沒給＝本人按「📋 我的交易」（「你」）。"""
    you = "他" if name is not None else "你"
    mine = [s for s in summaries if s.supplier_id == supplier_id]
    if not mine:
        return f"{name} 目前沒有還沒結束的交易。" if name is not None else "你目前沒有還沒結束的交易。"
    title = f"{name} 的交易" if name is not None else "我的交易"
    lines = [f"📋 **{title}：{len(mine)} 筆還沒結束**"]
    todo = [s for s in mine if s.todo and not s.legacy]
    if todo:
        lines.append(f"\n**要{you}處理**")
        for summary in todo:
            reasons = "；".join(summary.todo)
            lines.append(f"{_line(summary)}：" + (reasons.replace("等你", "等他") if name is not None else reasons))
    legacy = [s for s in mine if s.legacy]
    if legacy:
        lines.append("\n**上線前開的交易**")
        lines += [f"{_line(s)}：{s.todo[0] if s.todo else ''}（開了 {s.days_open} 天）" for s in legacy]
    idle = [s for s in mine if s.idle]
    if idle:
        lines.append(f"\n**超過 {IDLE_DAYS} 天沒動靜**")
        lines += [f"{_line(s)}（{s.days_idle} 天）" for s in idle]
    others = [s for s in mine if not s.todo and not s.legacy]
    if others:
        lines.append(f"\n**不用{you}處理**")
        lines += [f"{_line(s)}：{s.waiting or '進行中'}" for s in others]
    return "\n".join(lines)


def weekly_text(summaries: Sequence[TradeSummary], supplier_id: int, now: datetime) -> Optional[str]:
    """一位供應方的週報；沒有要他處理的就回 None（不發）。"""
    mine = [s for s in summaries if s.supplier_id == supplier_id]
    acting = [s for s in mine if s.needs_supplier]
    if not acting:
        return None
    legacy = [s for s in mine if s.legacy]
    if len(legacy) == len(mine):
        # 每一筆照自己的待辦寫：【定金】舊商品還沒改好的要先改成定金＋尾款，不能叫他照舊流程發領收通知
        lines = [f"你有 {len(mine)} 筆交易還沒結束，都是新功能上線前開的："]
        lines += [f"{_line(s)}：" + "；".join(s.todo) for s in legacy]
    else:
        lines = [f"你有 {len(mine)} 筆交易還沒結束，其中 {len(acting)} 筆要你處理："]
        for summary in acting:
            reasons = summary.todo or ([f"超過 {IDLE_DAYS} 天沒動靜"] if summary.idle else [])
            lines.append(f"{_line(summary)}：" + "；".join(reasons))
        rest = [s for s in mine if not s.needs_supplier]
        if rest:
            lines.append(f"另外 {len(rest)} 筆在等需求方或等貨，不用處理。")
    idle = [s for s in acting if s.idle]
    if idle:
        lines.append(f"\n超過 {IDLE_DAYS} 天沒動靜：{len(idle)} 筆")
        lines += [f"{_line(s)}（{s.days_idle} 天）" for s in idle]
    lines.append(f"\n{_ALL_TRADES_HINT}")
    return "\n".join(lines)


def week_key(day: date) -> str:
    year, week, _ = day.isocalendar()
    return f"{year}-W{week:02d}"


async def run_weekly(shop: "ShopService", now: datetime) -> datetime:
    """週一 12:00～23:59 之間：還沒收過這週週報、而且有待辦的觀星者各私訊一份。回傳下一次要醒來的時刻。"""
    local = now.astimezone(APP_TZ)
    monday = local.date() - timedelta(days=local.weekday())
    start = datetime.combine(monday, WEEKLY_AT, APP_TZ)
    end = datetime.combine(monday, time(23, 59, 59), APP_TZ)
    if local < start:
        return start
    if local > end or not shop.trade.ready.is_set():
        return start + timedelta(days=7) if local > end else local + timedelta(minutes=5)
    db = await shop.trade.db()
    week = week_key(monday)
    summaries = await summarize(shop, now)
    guild = await shop.guild()
    for supplier_id in sorted({s.supplier_id for s in summaries}):
        if await db.weekly_report(week, supplier_id) is not None:
            continue
        text = weekly_text(summaries, supplier_id, now)
        if text is None:
            continue
        member = await shop.trade.member(guild, supplier_id)
        sent = None
        if member is not None:
            embed = discord.Embed(title=f"每週交易提醒（{monday:%Y/%m/%d}）", description=_fit_weekly(text),
                                  color=discord.Color.gold())
            sent = await send_dm(member, embed=embed)
        async with db.transaction():
            if sent is not None:
                await db.record_weekly_report(week, supplier_id, sent_at=shop.stamp())
            else:
                reason = "私訊沒送到" if member is not None else "供應方已不在伺服器"
                await db.record_weekly_report(week, supplier_id, error=reason)
        logger.info("市集週報：%s 給 %s %s", week, supplier_id, "已送" if sent is not None else "沒送到")
    return start + timedelta(days=7)


def _fit_weekly(text: str) -> str:
    """放進說明欄：太長時從換行處切（不留半截網址），結尾補上截掉了與「全部清單」那句。"""
    if len(text) <= _WEEKLY_LIMIT:
        return text
    return split_message(text, _WEEKLY_LIMIT - len(_CUT_NOTE))[0] + _CUT_NOTE


async def dashboard_text(shop: "ShopService", summaries: Sequence[TradeSummary], now: datetime) -> str:
    """群主看板的總表：整體數字、每位觀星者一列、要注意的幾類交易。"""
    db = await shop.trade.db()
    local = now.astimezone(APP_TZ)
    monday = datetime.combine(local.date() - timedelta(days=local.weekday()), time(0, 0), APP_TZ)
    done = cancelled = 0
    for trade in await db.trades():
        if trade.closed_at and datetime.fromisoformat(trade.closed_at) >= monday:
            done += trade.status == "completed"
            cancelled += trade.status == "cancelled"
    oldest = max((s.days_open for s in summaries), default=0)
    lines = [f"還沒結束 {len(summaries)} 筆｜本週完成 {done}、取消 {cancelled}｜最久 {oldest} 天"]
    guild = await shop.guild()
    names = await shop.trade.display_names(guild, sorted({s.supplier_id for s in summaries}))
    gone = 0
    for supplier_id in sorted({s.supplier_id for s in summaries}, key=lambda i: names.get(i, str(i))):
        mine = [s for s in summaries if s.supplier_id == supplier_id]
        if supplier_id not in names:
            gone += len(mine)
        acting = sum(1 for s in mine if s.needs_supplier)
        idle = sum(1 for s in mine if s.idle)
        lines.append(f"**{party_name(names, supplier_id)}**　還沒結束 {len(mine)}｜"
                     f"要他處理 {acting}" + (f"｜超過 {IDLE_DAYS} 天 {idle}" if idle else ""))
    unknown = []
    for thread_id in json.loads(await db.get_meta(UNRECOGNIZED_META) or "[]"):
        # 群主處理掉（鎖定或刪除）的就不再列
        thread = await shop.trade.get_thread(thread_id)
        if thread is not None and not getattr(thread, "locked", False):
            unknown.append(masked_link(thread.name, thread.jump_url))
    failed = 0
    week = week_key(local.date() - timedelta(days=local.weekday()))
    for supplier_id in {s.supplier_id for s in summaries}:
        record = await db.weekly_report(week, supplier_id)
        failed += bool(record and record[1])
    # 一行一條連結：主控台太長時從換行處切，擠在同一行會切在連結中間
    lines += ["", f"認不出身分的舊交易：{len(unknown)} 筆", *(f"・{link}" for link in unknown),
              f"供應方已離開伺服器的交易：{gone} 筆", f"這週週報沒送到：{failed} 位"]
    return "\n".join(lines)
