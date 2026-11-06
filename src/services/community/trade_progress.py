"""交易進度：從交易品項與事件算出每個品項走到哪一步、現在等誰、哪些動作現在允許、等待提醒何時該發（純邏輯）。

架構定位：功能層（`services.community`），只依賴標準庫與基礎層的時區；不 import discord、不碰資料庫。
  - 上層（誰呼叫）：商品服務（交易進度卡、按鈕的檢查、取消時的提醒文字、等待提醒、週報與看板的「等誰」）。
  - 下層（呼叫誰）：無；輸入是 `services.market_db` 讀出來的交易品項與事件（或同樣欄位的物件）。

介面：
  - `progress(items, events, delivery=)` → `Progress`：每個品項一列 `Line`（份數、付款方式、已付到哪、交付到哪、
    狀態名稱、等誰），整串的 `money_done`、`all_delivered`、`all_received`、`paid`（已收的定金、尾款、全額金額）。
  - `allowed(progress, action, key=None)`：這個動作現在能不能做；不能就回給人看的理由。
  - `pending_for(progress, action, key=None)` → {品項編號: 份數}：這個動作要套用到哪些份數。
  - `due_reminders(progress, events, now=, ready_at=)` → (現在該發的提醒, 下一次要醒來的時刻)。
  - `latest_state_event(events)`：最新一筆會改變交易進度卡的事件（卡片過期了沒有看它）。
  - `held_by_requester(events)`：需求方說還沒領收、還在等供應方補交時回那筆事件。
  - 事件種類的常數（`ORDER`、`DEPOSIT_RECEIVED`…），寫事件與讀事件都用它們。

規則：
  - 狀態只從事件算，不另外存；同一份輸入一定得到同一個結果，按鈕的檢查與畫面都問這裡。
  - 一個品項買好幾份時一起走（按一次就是整列），加購的份數另外從頭走（例：定金已付 1 份、加購 1 份 → 那 1 份待付定金）。
  - 數位商品：錢收齊 → 已交付；全部交付後由交易模組發領收通知。實體商品：錢收齊 → 已寄出 → 需求方已收到；全部收到就完成。
  - 等待提醒：需求方沒付錢，3 天後提醒、之後每 7 天、最多 3 次；需求方按了「我已付」而供應方沒確認、
    或錢收齊了供應方沒交付或沒寄出、或數位商品需求方按了「還沒領收」，3 天後提醒供應方一次（之後只進週報）；
    實體寄出 7 天起每 3 天提醒雙方，直到收到或取消。
  - 「我已付」每個品項各自算：按過之後那個品項有新的一筆要付的錢（下單、請尾款）或錢收到了，就不再算數。
    22:00～隔天 10:00 到期的順延到 10:00；同一個對話一天最多一則。上線前的舊交易不提醒（由呼叫端不傳進來）。

例外與決策：
  - 等貨中（定金收了、還沒開始收尾款）不提醒：貨還沒到，催誰都沒用。
  - 預購的交付提醒從截止那一刻算（`ready_at` 由呼叫端給：截止時間或延期後的預計交貨日），截止前不催交貨。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from typing import Iterable, Mapping, Optional, Sequence

from sys_settings.time_settings import APP_TZ

# ── 事件種類（trade_events.kind）──
OPENED = "opened"                         # 開單（message_id＝開單訊息）
ORDER = "order"                           # 一次下單；品項與金額在 trade_items
PAID_CLAIM = "paid_claim"                 # 需求方按「我已付」（reference：deposit／balance／full）
DEPOSIT_RECEIVED = "deposit_received"     # 供應方確認收到定金（items、amount）
BALANCE_REQUESTED = "balance_requested"   # 開始收尾款時發到這個對話的請款（items、amount）
BALANCE_RECEIVED = "balance_received"     # 供應方確認收到尾款
FULL_RECEIVED = "full_received"           # 供應方確認收到款項（一次付清）
DELIVERED = "delivered"                   # 數位：已交付（items）
SHIPPED = "shipped"                       # 實體：已寄出（items）
RECEIVED = "received"                     # 實體：需求方已收到（items）
RECEIPT_REQUESTED = "receipt_requested"   # 領收通知（message_id）；24 小時沒按自動完成
RECEIPT_HELD = "receipt_held"             # 需求方按「還沒領收」：最近一次領收通知失效
RECEIPT_REMINDED = "receipt_reminded"     # 領收到期前的提醒
REMINDER = "reminder"                     # 等待提醒（reference：提醒的是哪件事、第幾次）
CUTOFF_NOTICE = "cutoff_notice"           # 預購截止、可以開始交貨的通知（reference：品項編號）
DELAY_NOTICE = "delay_notice"             # 延期通知（reference：品項編號:第幾次）
COMPLETED = "completed"
ARCHIVED = "archived"                     # 完成時的留底（商品）或封存需求貼文（自由市場）做過了：重啟補收尾時不重做
NOTIFIED = "notified"                     # 結束時私訊雙方做過了：重啟補收尾（可能補好幾輪）時不重發
ADOPTED = "adopted"                       # 上線前的舊交易接上新流程（items＝當時的份數；message_id＝補發的交易進度）
CANCELLED = "cancelled"
ENDED = "ended"                           # 自由市場同一篇需求由別人完成

# ── 動作 ──
CLAIM_PAID = "claim_paid"                 # 需求方：我已付
CONFIRM_DEPOSIT = "confirm_deposit"       # 供應方：已收到定金
CONFIRM_BALANCE = "confirm_balance"       # 供應方：已收到尾款
CONFIRM_FULL = "confirm_full"             # 供應方：已收到款項
DELIVER = "deliver"                       # 供應方：已交付（數位，單一品項）
SHIP = "ship"                             # 供應方：已寄出（實體，單一品項）
RECEIVE = "receive"                       # 需求方：已收到（實體，單一品項）
DELIVER_REST = "deliver_rest"             # 供應方：剩下的一起交付或寄出（開單訊息上的「通知需求方領收」）

SUPPLIER = "supplier"
REQUESTER = "requester"
BOTH = "both"

# ── 每個品項的狀態（給人看的名字也是它）──
AWAIT_DEPOSIT = "待付定金"
WAIT_GOODS = "已付定金・等貨"
AWAIT_BALANCE = "待付尾款"
AWAIT_PAYMENT = "待付款"
AWAIT_DELIVERY = "待交付"
AWAIT_SHIPPING = "待寄出"
DELIVERED_STATE = "已交付"
SHIPPED_STATE = "已寄出"
RECEIVED_STATE = "已收到"

#: 會改變交易進度卡內容的事件：卡片照到哪一筆畫的，比這裡最新的一筆舊就是過期了
STATE_EVENTS = frozenset({ORDER, DEPOSIT_RECEIVED, BALANCE_REQUESTED, BALANCE_RECEIVED, FULL_RECEIVED,
                          DELIVERED, SHIPPED, RECEIVED})

#: 等待提醒的間隔
FIRST_REMINDER = timedelta(days=3)
REPEAT_PAYMENT = timedelta(days=7)
MAX_PAYMENT_REMINDERS = 3
SHIPPED_FIRST = timedelta(days=7)
SHIPPED_REPEAT = timedelta(days=3)
QUIET_START = time(22, 0)
QUIET_END = time(10, 0)


def _get(obj, name, default=None):
    if isinstance(obj, Mapping):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _when(text_or_dt) -> datetime:
    if isinstance(text_or_dt, datetime):
        return text_or_dt
    return datetime.fromisoformat(text_or_dt)


@dataclass(frozen=True)
class Line:
    """交易裡一個品項（同一個品項的所有份數加起來）。"""

    key: int
    name: str
    kind: str                    # instant／preorder／deposit（下單當時的類型）
    qty: int                     # 還算數的份數（取消還回的不算）
    deposit_paid: int = 0
    balance_requested: int = 0
    balance_paid: int = 0
    full_paid: int = 0
    delivered: int = 0           # 數位：已交付
    shipped: int = 0             # 實體：已寄出
    received: int = 0            # 實體：需求方已收到
    unit_price: int = 0          # 一次付清＝全額；定金＋尾款＝定金
    unit_balance: int = 0
    claimed: bool = False        # 需求方對目前待付的這筆按過「我已付」

    @property
    def deposit(self) -> bool:
        return self.kind == "deposit"

    @property
    def money_done(self) -> bool:
        return self.balance_paid >= self.qty if self.deposit else self.full_paid >= self.qty

    def state(self, delivery: str) -> str:
        if self.deposit:
            if self.deposit_paid < self.qty:
                return AWAIT_DEPOSIT
            if self.balance_requested < self.qty:
                return WAIT_GOODS
            if self.balance_paid < self.qty:
                return AWAIT_BALANCE
        elif self.full_paid < self.qty:
            return AWAIT_PAYMENT
        if delivery == "physical":
            if self.shipped < self.qty:
                return AWAIT_SHIPPING
            return SHIPPED_STATE if self.received < self.qty else RECEIVED_STATE
        return AWAIT_DELIVERY if self.delivered < self.qty else DELIVERED_STATE

    def waiting_for(self, delivery: str) -> Optional[str]:
        """現在等誰動手；等貨中、完成了回 None。"""
        state = self.state(delivery)
        if state in (AWAIT_DEPOSIT, AWAIT_BALANCE, AWAIT_PAYMENT):
            return SUPPLIER if self.claimed else REQUESTER
        if state in (AWAIT_DELIVERY, AWAIT_SHIPPING):
            return SUPPLIER
        if state == SHIPPED_STATE:
            return REQUESTER
        return None


@dataclass(frozen=True)
class Progress:
    delivery: str
    lines: tuple[Line, ...]
    paid: dict[str, int] = field(default_factory=dict)   # 已收的金額：deposit／balance／full

    def line(self, key: int) -> Optional[Line]:
        return next((line for line in self.lines if line.key == key), None)

    @property
    def money_done(self) -> bool:
        return all(line.money_done for line in self.lines)

    @property
    def all_delivered(self) -> bool:
        """數位：全部交付；實體：全部寄出。"""
        if self.delivery == "physical":
            return all(line.shipped >= line.qty for line in self.lines)
        return all(line.delivered >= line.qty for line in self.lines)

    @property
    def all_received(self) -> bool:
        return self.delivery == "physical" and all(line.received >= line.qty for line in self.lines)

    @property
    def any_paid(self) -> bool:
        return any(amount > 0 for amount in self.paid.values())


def progress(items: Iterable, events: Iterable, *, delivery: str) -> Progress:
    """交易品項（每次下單一列）＋事件 → 進度。取消時還回的份數不算。"""
    rows: dict[int, dict] = {}
    for item in items:
        qty = _get(item, "qty") - (_get(item, "returned") or 0)
        if qty <= 0:
            continue
        key = _get(item, "variant_key")
        row = rows.setdefault(key, dict(name=_get(item, "name"), kind=_get(item, "kind"), qty=0,
                                        unit_price=_get(item, "unit_price") or 0,
                                        unit_balance=_get(item, "unit_balance") or 0))
        row["qty"] += qty
    counts = {name: {} for name in ("deposit", "requested", "balance", "full", "delivered", "shipped", "received")}
    which = {DEPOSIT_RECEIVED: "deposit", BALANCE_REQUESTED: "requested", BALANCE_RECEIVED: "balance",
             FULL_RECEIVED: "full", DELIVERED: "delivered", SHIPPED: "shipped", RECEIVED: "received"}
    paid = {"deposit": 0, "balance": 0, "full": 0}
    # 「我已付」每個品項各自算：按過之後，那個品項有新的一筆要付的錢（下單、請尾款）或錢收到了，就不再算數
    last_money: dict[int, int] = {}
    last_claim: dict[int, int] = {}
    for event in events:
        kind, event_id = _get(event, "kind"), _get(event, "id") or 0
        keys = [int(key) for key in (_get(event, "items") or {})]
        if kind in which:
            bucket = counts[which[kind]]
            for key, qty in (_get(event, "items") or {}).items():
                bucket[int(key)] = bucket.get(int(key), 0) + int(qty)
            if kind in (DEPOSIT_RECEIVED, BALANCE_RECEIVED, FULL_RECEIVED):
                paid[which[kind]] += _get(event, "amount") or 0
                last_money.update({key: event_id for key in keys})
            elif kind == BALANCE_REQUESTED:
                # 請尾款是新的一筆錢；但定金還沒確認收齊的品項，需求方說的「已付定金」照樣算數
                last_money.update({key: event_id for key in keys
                                   if counts["deposit"].get(key, 0) >= rows.get(key, {}).get("qty", 0)})
        elif kind == ORDER:
            last_money.update({key: event_id for key in keys})
        elif kind == PAID_CLAIM:
            # 在舊卡片上按的（source＝v卡片版本）只算那張卡畫好之前的份數：之後加購的照樣要再按一次。
            # 沒寫品項的（舊寫法）算整個對話
            source = _get(event, "source") or ""
            seen = int(source[1:]) if source.startswith("v") and source[1:].isdigit() else event_id
            last_claim.update({key: seen for key in (keys or rows)})
    lines = []
    for key in sorted(rows):
        row = rows[key]
        lines.append(Line(
            key=key, name=row["name"], kind=row["kind"], qty=row["qty"],
            deposit_paid=counts["deposit"].get(key, 0), balance_requested=counts["requested"].get(key, 0),
            balance_paid=counts["balance"].get(key, 0), full_paid=counts["full"].get(key, 0),
            delivered=counts["delivered"].get(key, 0), shipped=counts["shipped"].get(key, 0),
            received=counts["received"].get(key, 0), unit_price=row["unit_price"],
            # 卡片版本 v＝畫的時候已經包含編號 ≤ v 的事件，所以等於那筆錢也算看過了
            unit_balance=row["unit_balance"],
            claimed=key in last_claim and last_claim[key] >= last_money.get(key, 0)))
    return Progress(delivery=delivery, lines=tuple(lines), paid=paid)


# ── 動作的檢查 ──

_ACTOR = {CLAIM_PAID: REQUESTER, RECEIVE: REQUESTER, CONFIRM_DEPOSIT: SUPPLIER, CONFIRM_BALANCE: SUPPLIER,
          CONFIRM_FULL: SUPPLIER, DELIVER: SUPPLIER, SHIP: SUPPLIER, DELIVER_REST: SUPPLIER}


def actor_of(action: str) -> str:
    """誰能按這個動作（需求方或供應方）。"""
    return _ACTOR[action]


def pending_for(prog: Progress, action: str, key: Optional[int] = None) -> dict[int, int]:
    """這個動作現在要套用的份數 {品項編號: 份數}；沒有可套用的回空。"""
    result: dict[int, int] = {}
    for line in prog.lines:
        if key is not None and line.key != key:
            continue
        state = line.state(prog.delivery)
        if action == CONFIRM_DEPOSIT and state == AWAIT_DEPOSIT:
            result[line.key] = line.qty - line.deposit_paid
        elif action == CONFIRM_BALANCE and state == AWAIT_BALANCE:
            result[line.key] = line.balance_requested - line.balance_paid
        elif action == CONFIRM_FULL and state == AWAIT_PAYMENT:
            result[line.key] = line.qty - line.full_paid
        elif action == CLAIM_PAID and state in (AWAIT_DEPOSIT, AWAIT_BALANCE, AWAIT_PAYMENT) and not line.claimed:
            # 份數＝這一步還沒付的份數（通知供應方時寫得出是幾份）
            result[line.key] = {AWAIT_DEPOSIT: line.qty - line.deposit_paid,
                                AWAIT_BALANCE: line.balance_requested - line.balance_paid,
                                AWAIT_PAYMENT: line.qty - line.full_paid}[state]
        elif action in (DELIVER, DELIVER_REST) and prog.delivery != "physical" and state == AWAIT_DELIVERY:
            result[line.key] = line.qty - line.delivered
        elif action in (SHIP, DELIVER_REST) and prog.delivery == "physical" and state == AWAIT_SHIPPING:
            result[line.key] = line.qty - line.shipped
        elif action == RECEIVE and state == SHIPPED_STATE:
            result[line.key] = line.shipped - line.received
    return result


def allowed(prog: Progress, action: str, key: Optional[int] = None) -> Optional[str]:
    """這個動作現在能不能做：可以回 None，不行回給按的人看的理由。誰能按由呼叫端另外檢查（`actor_of`）。"""
    if key is not None and prog.line(key) is None:
        return "這筆交易沒有這個品項。"
    if pending_for(prog, action, key):
        if action == DELIVER_REST and not prog.money_done:
            return _unpaid_reason(prog)
        return None
    if action == CONFIRM_DEPOSIT:
        return "這個對話目前沒有待收的定金。"
    if action == CONFIRM_BALANCE:
        return "這個對話目前沒有待收的尾款。"
    if action == CONFIRM_FULL:
        return "這個對話目前沒有待收的款項。"
    if action == CLAIM_PAID:
        if any(line.state(prog.delivery) in (AWAIT_DEPOSIT, AWAIT_BALANCE, AWAIT_PAYMENT) for line in prog.lines):
            return "已經通知過供應方了，請等他確認。"
        return "這個對話目前沒有要付的款項。"
    if action in (DELIVER, SHIP, DELIVER_REST):
        if any(not line.money_done for line in prog.lines if key is None or line.key == key):
            return _unpaid_reason(prog, key)
        return "這些品項都已經交付了。" if prog.delivery != "physical" else "這些品項都已經寄出了。"
    if action == RECEIVE:
        return "這個品項還沒寄出，或已經按過收到了。"
    return "這個動作現在不能做。"


#: 錢沒收齊的理由最多列幾個品項（只有按的人看得到的回覆一則最多 2000 字，後面還要接下一步怎麼做）
_UNPAID_ROWS_MAX = 12


def _unpaid_reason(prog: Progress, key: Optional[int] = None) -> str:
    rows = [f"・{line.name} ×{line.qty}：{line.state(prog.delivery)}"
            for line in prog.lines if (key is None or line.key == key) and not line.money_done]
    if len(rows) > _UNPAID_ROWS_MAX:
        rows = rows[:_UNPAID_ROWS_MAX] + [f"・…等 {len(rows)} 項"]
    return "還有品項的錢沒收齊，暫時不能交付：\n" + "\n".join(rows)


# ── 等待提醒 ──

@dataclass(frozen=True)
class Reminder:
    reference: str              # 寫進 REMINDER 事件的 reference：哪件事、第幾次（重啟不重發靠它）
    to: str                     # requester／supplier／both
    key: int
    reason: str                 # pay／confirm／deliver／receive
    number: int                 # 第幾次
    days: int = 0               # receive：寄出到現在幾天（停機晚發的照實際天數寫）


def held_by_requester(events: Sequence):
    """需求方按了「還沒領收」、之後還沒有新的領收通知或新的交付：回那筆事件（在等供應方補交）；否則 None。"""
    last = None
    for event in events:
        if _get(event, "kind") in (RECEIPT_REQUESTED, RECEIPT_HELD, DELIVERED):
            last = event
    if last is not None and _get(last, "kind") == RECEIPT_HELD and _get(last, "reference") == "held":
        return last
    return None


def latest_state_event(events: Iterable) -> Optional[int]:
    """最新一筆會改變交易進度卡的事件編號（沒有就 None）。"""
    ids = [_get(event, "id") or 0 for event in events if _get(event, "kind") in STATE_EVENTS]
    return max(ids) if ids else None


def _shift_out_of_quiet(moment: datetime) -> datetime:
    local = moment.astimezone(APP_TZ)
    if local.time() >= QUIET_START:
        return datetime.combine(local.date() + timedelta(days=1), QUIET_END, APP_TZ)
    if local.time() < QUIET_END:
        return datetime.combine(local.date(), QUIET_END, APP_TZ)
    return moment


def _next_day_morning(moment: datetime) -> datetime:
    local = moment.astimezone(APP_TZ)
    return datetime.combine(local.date() + timedelta(days=1), QUIET_END, APP_TZ)


def due_reminders(prog: Progress, events: Sequence, *, now: datetime,
                  ready_at: Optional[Mapping[int, datetime]] = None) -> tuple[list[Reminder], Optional[datetime]]:
    """現在該發的等待提醒（同一個對話一次併成一則），以及下一次要醒來的時刻。

    ready_at：預購品項「可以開始交貨」的時刻（截止時間，或延期後的預計交貨日）；在那之前不催交貨。"""
    ready_at = ready_at or {}
    sent: dict[str, datetime] = {}
    last_sent: Optional[datetime] = None
    anchor: dict[tuple[str, int], tuple[int, datetime]] = {}
    for event in events:
        kind, when, event_id = _get(event, "kind"), _when(_get(event, "created_at")), _get(event, "id") or 0
        if kind == REMINDER:
            sent[_get(event, "reference")] = when
            last_sent = when if last_sent is None or when > last_sent else last_sent
            continue
        for key in (int(k) for k in (_get(event, "items") or {})):
            if kind in (ORDER, ADOPTED):
                # 定金、全額從下單那一刻開始要付；舊交易從接上新流程那一刻算（照上線前的下單時間算會一轉過來就催）
                anchor[("order", key)] = (event_id, when)
            if kind == BALANCE_REQUESTED:
                anchor[("balance", key)] = (event_id, when)      # 尾款從請款那一刻開始要付
            if kind == DEPOSIT_RECEIVED and ("balance", key) in anchor:
                # 請了尾款之後定金才確認：尾款從這一刻才真的輪到需求方付，催款從這裡算
                anchor[("balance", key)] = (event_id, when)
            if kind in (BALANCE_RECEIVED, FULL_RECEIVED):
                anchor[("ready", key)] = (event_id, when)        # 錢收齊、輪到供應方交付的那一刻
            if kind == SHIPPED:
                anchor[("shipped", key)] = (event_id, when)
        if kind == PAID_CLAIM:
            for key in ([int(k) for k in (_get(event, "items") or {})] or [line.key for line in prog.lines]):
                anchor[("claim", key)] = (event_id, when)

    candidates: list[tuple[datetime, Reminder]] = []
    for line in prog.lines:
        state = line.state(prog.delivery)
        if state in (AWAIT_DEPOSIT, AWAIT_BALANCE, AWAIT_PAYMENT):
            if line.claimed and ("claim", line.key) in anchor:
                event_id, when = anchor[("claim", line.key)]
                ref = f"confirm:{line.key}:{event_id}:1"
                if ref not in sent:
                    candidates.append((when + FIRST_REMINDER, Reminder(ref, SUPPLIER, line.key, "confirm", 1)))
            elif ("balance" if state == AWAIT_BALANCE else "order", line.key) in anchor:
                # 催款的編號跟著這一段的起點走：定金沒確認就請了尾款，催定金用掉的次數不會吃掉尾款的
                event_id, when = anchor[("balance" if state == AWAIT_BALANCE else "order", line.key)]
                for number in range(1, MAX_PAYMENT_REMINDERS + 1):
                    ref = f"pay:{line.key}:{event_id}:{number}"
                    if ref in sent:
                        continue
                    at = when + FIRST_REMINDER + REPEAT_PAYMENT * (number - 1)
                    previous = sent.get(f"pay:{line.key}:{event_id}:{number - 1}")
                    if previous is not None:
                        # 上一次晚發了（停機）：間隔照上一次實際發的時間算，不會接連幾天都催
                        at = max(at, previous + REPEAT_PAYMENT)
                    candidates.append((at, Reminder(ref, REQUESTER, line.key, "pay", number)))
                    break
        elif state in (AWAIT_DELIVERY, AWAIT_SHIPPING) and ("ready", line.key) in anchor:
            event_id, when = anchor[("ready", line.key)]
            start = max(when, ready_at.get(line.key, when))
            ref = f"deliver:{line.key}:{event_id}:1"
            if ref not in sent:
                candidates.append((start + FIRST_REMINDER, Reminder(ref, SUPPLIER, line.key, "deliver", 1)))
        elif state == SHIPPED_STATE and ("shipped", line.key) in anchor:
            event_id, when = anchor[("shipped", line.key)]
            number = 1
            while f"receive:{line.key}:{event_id}:{number}" in sent:
                number += 1
            at = when + SHIPPED_FIRST + SHIPPED_REPEAT * (number - 1)
            previous = sent.get(f"receive:{line.key}:{event_id}:{number - 1}")
            if previous is not None:
                at = max(at, previous + SHIPPED_REPEAT)
            days = max(0, (now - when) // timedelta(days=1))
            candidates.append((at, Reminder(f"receive:{line.key}:{event_id}:{number}", BOTH, line.key, "receive",
                                            number, days)))

    held = held_by_requester(events)
    if prog.delivery != "physical" and prog.lines and prog.all_delivered and held is not None:
        # 需求方按了「還沒領收」：回到等供應方補交，跟「錢收齊、還沒交付」一樣 3 天後提醒供應方一次
        event_id, when = _get(held, "id") or 0, _when(_get(held, "created_at"))
        ref = f"redeliver:{event_id}:1"
        if ref not in sent:
            candidates.append((when + FIRST_REMINDER, Reminder(ref, SUPPLIER, prog.lines[0].key, "redeliver", 1)))

    if not candidates:
        return [], None
    adjusted = []
    for at, reminder in candidates:
        if last_sent is not None:
            at = max(at, _next_day_morning(last_sent))   # 同一個對話一天最多一則：最早等到上次提醒的隔天早上
        adjusted.append((_shift_out_of_quiet(at), reminder))
    # 停機期間到期、夜裡才重啟補做的也不發，等到早上
    morning = _shift_out_of_quiet(now)
    if morning > now:
        return [], min(max(at, morning) for at, _ in adjusted)
    due = [reminder for at, reminder in adjusted if at <= now]
    later = [at for at, _ in adjusted if at > now]
    return due, min(later) if later else None
