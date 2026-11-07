"""商品與品項的模型、供應方填的內容怎麼解析、商品貼文與選單怎麼畫（純資料與畫面，不連網路、不碰資料庫）。

架構定位：功能層（`services.community`）。
  - 上層（誰呼叫）：商品服務 `shop_service`（從資料庫讀出來轉成這裡的模型、檢查下單、畫貼文）、
    介面 `commands.shop_commands`（選單、表單的長相與解析）、上線匯入 `market_import`、上線銜接 `market_transition`。
  - 下層（呼叫誰）：discord（只用 Embed、SelectOption 畫畫面）、`utils.user_dates`（日期寫法）、時區設定。

介面：
  - 模型：`Listing`、`Variant`、`Draft`；`listing_from_rows(商品列, 品項列, 已下單)` 把資料庫的列轉成模型。
  - 解析：`parse_price`（「500/1300」＝定金/尾款）、`parse_draft`、`parse_batch`、`parse_cutoff`。
  - 畫面：`render_embed`、`select_options`、`unavailable_text`、`Variant.status`、`money`、`format_cutoff`。
  - 論壇標籤：`forum_tags(商品, now, taking_orders=)` 回這篇該掛哪些（`PREORDER_TAG`、`INSTOCK_TAG`）。
  - 下單：`quote_order`、`order_summary`（現在要付、到貨後再付）、`price_signature`（確認畫面的價格指紋）、
    `encode_items`／`decode_items`（確認按鈕上的「編號x數量」）。

規則：
  - 正本在資料庫（`services.market_db`）；這裡的模型是讀出來的一份，改了要寫回資料庫才算數。
  - 品項類型：instant＝立即購買、preorder＝預購（有截止）、deposit＝定金＋尾款（有截止，價格是定金、另有尾款）。
    預購與定金都一定要填截止時間。
  - 給群友看的字：品項（不是商品）、需求方與供應方（不是買家、上架者）。

例外與決策：
  - 選單選項的 value 只放品項編號：資料一律查資料庫，選項不再當資料用（以前整筆品項塞在 value 裡，
    讀不懂的品項會被默默略過、下次寫入就消失）。
  - 金額存整數、顯示時才加幣別與千分位。
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, replace
from datetime import datetime, time, timedelta
from typing import Iterable, Mapping, Optional
from urllib.parse import urlparse

import discord

from sys_settings.time_settings import APP_TZ
from utils.user_dates import parse_user_datetime

BUY_PREFIX = "shop:buy:"
#: 購買下拉選單：shop:buy:商品貼文id
BUY_TEMPLATE = r"shop:buy:(?P<listing>\d+)"
_ITEM_RE = re.compile(r"(\d+)x(\d+)")

KINDS = ("instant", "preorder", "deposit")
KIND_LABELS = {"instant": "立即購買", "preorder": "預購", "deposit": "定金＋尾款"}
DELIVERIES = ("physical", "digital")
DELIVERY_LABELS = {"physical": "實體（要寄送）", "digital": "數位（帳號、代儲、道具）"}

#: 截止時間一律寫年份，伺服器時間
CUTOFF_FORMAT = "%Y/%m/%d %H:%M"
#: 只寫日期＝當天結束
CUTOFF_DEFAULT_TIME = time(23, 59)
#: 截止時間最遠幾年後：擋年份打錯（例：2062），預購頂多幾年（定五年）
CUTOFF_MAX_YEARS = 5
NAME_LIMIT = 80    # 下拉選項 label 上限 100
PRICE_MAX = 999_999_999   # 定金、尾款、全額各自最多 9 位
PRICE_FIELD_LIMIT = 19    # 表單價格欄：「999999999/999999999」
LIMIT_MAX = 999_999       # 數量上限（6 位）
TITLE_LIMIT = 90   # 貼文標題上限 100，留空間給【已下架】
UNIT_LIMIT = 10
#: 商品貼文作者欄掛的連結：點供應方的名字開他的 Discord 個人檔案
PROFILE_URL = "https://discord.com/users/{user_id}"
#: 論壇標籤的種類（標籤名字在 ShopSettings）：預購中、現貨
PREORDER_TAG = "preorder"
INSTOCK_TAG = "instock"
_SEPARATORS = re.compile(r"[｜|]")
_PRICE_SPLIT = re.compile(r"\s*[/／]\s*")


class ShopError(Exception):
    """要直接告訴使用者的錯誤；訊息就是給人看的文字。"""


def parse_cutoff(text: str) -> datetime:
    """截止時間（伺服器時間）。寫法由 utils.user_dates 讀：全形、`/` `-`、只寫日期都收。"""
    moment = parse_user_datetime(text, default_time=CUTOFF_DEFAULT_TIME)
    if moment is None:
        raise ShopError(f"截止時間「{text.strip()}」看不懂，請寫成 2026/10/20 23:59（只寫日期＝當天 23:59）")
    return moment.replace(tzinfo=APP_TZ)


def money(unit: str, amount: int) -> str:
    """金額顯示：幣別＋千分位（例 NT$100,005,000）；存的資料不變。"""
    return f"{unit}{amount:,}"


def format_cutoff(moment: datetime) -> str:
    return moment.astimezone(APP_TZ).strftime(CUTOFF_FORMAT)


def format_date(moment: datetime) -> str:
    return moment.astimezone(APP_TZ).strftime("%Y/%m/%d")


@dataclass(frozen=True)
class Variant:
    """一篇商品裡的一個品項。"""

    key: int                                # 商品內的編號，建立後不變（訂單與提醒靠它對應）
    name: str
    price: int                              # 一次付清＝全額；定金＋尾款＝定金
    kind: str = "instant"
    balance: Optional[int] = None           # 定金＋尾款才有：尾款
    limit: Optional[int] = None             # None＝不限量；是總數（已下單＋剩餘）
    taken: int = 0                          # 已下單的份數（進行中＋已完成；取消會還回來）
    cutoff: Optional[datetime] = None       # 預購、定金的截止時間
    cutoff_done: bool = False               # 截止已處理（停止下單、該通知的都通知了）
    expected_at: Optional[datetime] = None  # 延期後的預計交貨（定金是預計到貨）日
    delays: int = 0
    balance_started: bool = False           # 定金品項已開始收尾款（停收定金）
    delivery_started: bool = False          # 截止後延期的預購，供應方按了開始交貨（貨提早到了）

    @property
    def preorder(self) -> bool:
        return self.kind == "preorder"

    @property
    def deposit(self) -> bool:
        return self.kind == "deposit"

    @property
    def remaining(self) -> Optional[int]:
        return None if self.limit is None else max(self.limit - self.taken, 0)

    def cutoff_passed(self, now: datetime) -> bool:
        return self.cutoff is not None and (self.cutoff_done or now >= self.cutoff)

    def unavailable_reason(self, now: datetime) -> Optional[str]:
        if self.deposit and (self.balance_started or self.cutoff_passed(now)):
            return "已停收定金"
        if self.preorder and self.cutoff_passed(now):
            return "預購已截止"
        if self.remaining == 0:
            return "已售完"
        return None

    def price_text(self, unit: str) -> str:
        if self.deposit:
            return f"定金 {money(unit, self.price)}｜尾款 {money(unit, self.balance or 0)}"
        return money(unit, self.price)

    def kind_text(self) -> str:
        if self.preorder:
            text = f"預購（{format_cutoff(self.cutoff)} 截止）"
        elif self.deposit:
            text = f"收定金至 {format_cutoff(self.cutoff)}"
        else:
            text = "立即購買"
        if self.expected_at is not None:
            what = "到貨" if self.deposit else "交貨"
            text += f"｜預計 {format_date(self.expected_at)} {what}"
        if self.delays:
            text += f"（已延期 {self.delays} 次）"
        return text

    def status(self, unit: str, now: datetime, *, rich: bool = False) -> str:
        """品項狀態。不能買的要一眼看得出來、但不突兀：
        rich＝給 embed 用，價格與類型加刪除線、後面接灰底標籤；選單的說明文字不能用 Markdown，
        就把狀態放最前面，手機上後面被截斷也看得到。"""
        body = f"{self.price_text(unit)}｜{self.kind_text()}"
        reason = self.unavailable_reason(now)
        if reason:
            if rich:
                return f"~~{discord.utils.escape_markdown(body)}~~ `{reason}`"
            return f"{reason}｜{body}"
        stock = "不限量" if self.remaining is None else f"剩 {self.remaining}"
        return f"{body}｜{stock}"


@dataclass(frozen=True)
class Draft:
    """供應方填的一個品項（還沒有編號與已下單數量）。"""

    name: str
    price: int
    limit: Optional[int]
    cutoff: Optional[datetime]
    kind: str = "instant"
    balance: Optional[int] = None

    def line(self) -> str:
        """批次格式的一行；預覽與「回去修改」都用它，往返不會走樣。"""
        price = f"{self.price}/{self.balance}" if self.kind == "deposit" else str(self.price)
        limit = "" if self.limit is None else str(self.limit)
        cutoff = "" if self.cutoff is None else format_cutoff(self.cutoff)
        return f"{self.name}｜{price}｜{limit}｜{cutoff}"


def _amount(text: str, name: str, what: str) -> int:
    try:
        value = int(text.strip())
    except ValueError:
        raise ShopError(f"「{name}」的{what}要填整數") from None
    if value < 0:
        raise ShopError(f"「{name}」的{what}不能是負的")
    if value > PRICE_MAX:
        raise ShopError(f"「{name}」的{what}最多 9 位數")
    return value


def parse_price(text: str, name: str) -> tuple[int, Optional[int]]:
    """價格欄：一個數字＝全額；「定金/尾款」兩個數字（例 500/1300）＝定金＋尾款。回傳（價格, 尾款或 None）。"""
    parts = _PRICE_SPLIT.split((text or "").strip())
    if len(parts) == 1:
        return _amount(parts[0], name, "價格"), None
    if len(parts) == 2:
        return _amount(parts[0], name, "定金"), _amount(parts[1], name, "尾款")
    raise ShopError(f"「{name}」的價格要填一個數字，定金＋尾款填「定金/尾款」，例如 500/1300")


def parse_draft(name: str, price: str, limit: str, cutoff: str, *, kind: Optional[str], now: datetime,
                min_limit: int = 1, allow_unused_cutoff: bool = False,
                keep_cutoff: Optional[datetime] = None) -> Draft:
    """檢查供應方填的品項。kind＝None 時從內容推（批次新增用）：價格有斜線＝定金＋尾款，填了截止＝預購。

    min_limit：新增時數量至少 1；編輯時填的是「剩餘數量」，可以填 0（停賣、標成已售完）。
    allow_unused_cutoff：選立即購買卻填了截止時間時忽略它（編輯時從預購改成立即購買，截止欄還留著預填的時間）。
    keep_cutoff：截止欄鎖住時（已經有人下單、要改日期請用延期）沿用原本的截止時間，不再檢查是不是已經過了。"""
    name = (name or "").strip()
    if not name:
        raise ShopError("名稱不能空白")
    if len(name) > NAME_LIMIT:
        raise ShopError(f"名稱最多 {NAME_LIMIT} 個字")
    price_value, balance = parse_price(price, name)
    if kind is None:
        kind = "deposit" if balance is not None else ("preorder" if (cutoff or "").strip() else "instant")
    if kind not in KINDS:
        raise ShopError(f"「{name}」的類型看不懂")
    if kind == "deposit" and balance is None:
        raise ShopError(f"「{name}」是定金＋尾款，價格要填「定金/尾款」，例如 500/1300")
    if kind != "deposit" and balance is not None:
        raise ShopError(f"「{name}」的價格寫了定金/尾款：要收定金請把類型選「定金＋尾款」，不然只填一個價格")
    limit_value = None
    if (limit or "").strip():
        try:
            limit_value = int(limit.strip())
        except ValueError:
            raise ShopError(f"「{name}」的數量要填整數，不限量就留空") from None
        if limit_value < min_limit:
            raise ShopError(f"「{name}」的數量至少 {min_limit}，不限量就留空")
        if limit_value > LIMIT_MAX:
            raise ShopError(f"「{name}」的數量最多 6 位數")
    cutoff_text = (cutoff or "").strip()
    needs_cutoff = kind in ("preorder", "deposit")
    if not needs_cutoff and cutoff_text and not allow_unused_cutoff:
        raise ShopError(f"「{name}」填了截止時間：要預購請把類型選「預購」，要立即購買就把截止時間清空")
    cutoff_value = None
    if needs_cutoff:
        if keep_cutoff is not None:
            cutoff_value = keep_cutoff
        elif not cutoff_text:
            what = "預購" if kind == "preorder" else "定金＋尾款"
            raise ShopError(f"「{name}」是{what}，要填截止時間（例：2026/10/20 23:59）")
        else:
            cutoff_value = parse_cutoff(cutoff_text)
            if cutoff_value <= now:
                raise ShopError(f"「{name}」的截止時間已經過了")
            if cutoff_value > now + timedelta(days=round(365.25 * CUTOFF_MAX_YEARS)):
                raise ShopError(f"「{name}」的截止時間太遠了，最多 {CUTOFF_MAX_YEARS} 年內，請檢查年份")
    return Draft(name, price_value, limit_value, cutoff_value, kind, balance)


def parse_batch(text: str, *, now: datetime) -> tuple[list[Draft], list[str]]:
    """批次新增：一行一項「名稱｜價格｜數量｜截止」，數量與截止可留空；價格寫「定金/尾款」就是定金＋尾款。"""
    drafts: list[Draft] = []
    errors: list[str] = []
    for number, raw in enumerate((text or "").splitlines(), start=1):
        if not raw.strip():
            continue
        fields = [f.strip() for f in _SEPARATORS.split(raw)]
        if len(fields) < 2 or len(fields) > 4:
            errors.append(f"第 {number} 行：要寫成「名稱｜價格｜數量｜截止」")
            continue
        fields += [""] * (4 - len(fields))
        try:
            drafts.append(parse_draft(*fields, kind=None, now=now))
        except ShopError as exc:
            errors.append(f"第 {number} 行：{exc}")
    return drafts, errors


@dataclass(frozen=True)
class Listing:
    thread_id: int
    owner_id: int
    unit: str
    title: str
    description: str
    image: Optional[str] = None             # embed 引用的附件檔名（attachment://檔名）
    variants: tuple[Variant, ...] = ()
    closed: bool = False                    # 已下架
    delivery: str = "physical"

    def variant(self, key: int) -> Optional[Variant]:
        return next((v for v in self.variants if v.key == key), None)

    def has_deposit(self) -> bool:
        return any(v.deposit for v in self.variants)


def forum_tags(listing: Listing, now: datetime, *, taking_orders: bool) -> set[str]:
    """這篇商品該掛哪些論壇標籤，跟著「現在能不能買」，群友篩出來的才都買得到。

    taking_orders：下單那一關會不會擋整篇（供應方不在或不是觀星者、付款方式還在設定），由呼叫端照下單的檢查算。
    下架或整篇不接單就都不掛；有現在買得到的預購或收定金品項掛「預購中」、立即購買品項掛「現貨」
    （截止、開始收尾款、賣完都算買不到；有人取消、份數還回來就掛回去）。截止後等交貨的兩個都不掛。"""
    if listing.closed or not taking_orders:
        return set()
    open_kinds = {v.kind for v in listing.variants if v.unavailable_reason(now) is None}
    tags = set()
    if open_kinds & {"preorder", "deposit"}:
        tags.add(PREORDER_TAG)
    if "instant" in open_kinds:
        tags.add(INSTOCK_TAG)
    return tags


def _moment(text: Optional[str]) -> Optional[datetime]:
    return datetime.fromisoformat(text) if text else None


def listing_from_rows(row, variant_rows: Iterable, taken: Mapping[int, int]) -> Listing:
    """資料庫的商品列、品項列（不含已刪除的）與已下單份數 → 模型。"""
    variants = tuple(
        Variant(key=v.key, name=v.name, price=v.price, kind=v.kind, balance=v.balance, limit=v.limit_qty,
                taken=taken.get(v.key, v.sold_before), cutoff=_moment(v.cutoff), cutoff_done=v.cutoff_done,
                expected_at=_moment(v.expected_at), delays=v.delays, balance_started=v.balance_started_at is not None,
                delivery_started=v.delivery_started_at is not None)
        for v in variant_rows if not v.deleted)
    return Listing(thread_id=row.id, owner_id=row.owner_id, unit=row.unit, title=row.title,
                   description=row.description, image=row.image, variants=variants, closed=row.closed,
                   delivery=row.delivery)


def buy_custom_id(listing_id: int) -> str:
    return f"{BUY_PREFIX}{listing_id}"


def embed_image_name(embed) -> Optional[str]:
    """embed 引用的附件檔名。送出後 Discord 回的是 CDN 網址（…/item_1.png?ex=…），自己組的則是 attachment://item_1.png。"""
    image_url = getattr(getattr(embed, "image", None), "url", None) if embed else None
    if not image_url:
        return None
    if image_url.startswith("attachment://"):
        return image_url[len("attachment://"):] or None
    return urlparse(image_url).path.rsplit("/", 1)[-1] or None


#: 一則 embed 所有文字合計的上限（Discord 是 6000，留一點給作者與頁尾）
EMBED_TOTAL_LIMIT = 5800


def render_embed(listing: Listing, owner_name: str, now: datetime, *,
                 owner_avatar: Optional[str] = None) -> discord.Embed:
    """商品貼文。說明寫滿、品項放滿 25 個又名稱很長時，合計會超過 embed 上限、貼文就改不了：
    先把品項狀態改成不加樣式的短版，還不夠再截短說明。

    供應方放在作者欄，名字連到他的 Discord 個人檔案、旁邊是頭像（作者欄不能 @ 人，只能掛網址）；
    名字與頭像是畫的那時候的，換了要等下次重畫。"""
    description = listing.description or None
    statuses = [variant.status(listing.unit, now, rich=True) for variant in listing.variants]
    names = [f"{number}. {variant.name}" for number, variant in enumerate(listing.variants, start=1)]
    fixed = len(listing.title) + len(owner_name) + 120
    if fixed + len(description or "") + sum(map(len, names + statuses)) > EMBED_TOTAL_LIMIT:
        statuses = [(variant.unavailable_reason(now) or variant.price_text(listing.unit))[:100]
                    for variant in listing.variants]
        room = EMBED_TOTAL_LIMIT - fixed - sum(map(len, names + statuses))
        if description and len(description) > room:
            description = description[:max(room - 1, 0)] + "…"
    embed = discord.Embed(title=listing.title, description=description, color=discord.Color.gold())
    embed.set_author(name=f"供應方：{owner_name}", url=PROFILE_URL.format(user_id=listing.owner_id),
                     icon_url=owner_avatar)
    for name, status in zip(names, statuses):
        embed.add_field(name=name, value=status, inline=False)
    if not listing.variants:
        embed.add_field(name="品項", value="供應方還沒加入品項，暫時不能購買。", inline=False)
    delivery = f"交付方式：{DELIVERY_LABELS.get(listing.delivery, listing.delivery)}"
    if listing.closed:
        embed.set_footer(text=f"{delivery}｜這篇商品已下架")
    else:
        embed.set_footer(text=f"{delivery}｜從下方選單挑要買的品項；供應方用「⚙️ 管理商品（供應方）」管理")
    if listing.image:
        embed.set_image(url=f"attachment://{listing.image}")
    return embed


def select_options(listing: Listing, now: datetime) -> list[discord.SelectOption]:
    """購買下拉選單的選項：value 只放品項編號，資料查資料庫。賣完或截止的也列出來（看得到狀態）。"""
    return [
        discord.SelectOption(label=v.name, value=str(v.key), description=v.status(listing.unit, now)[:100])
        for v in listing.variants
    ]


def unavailable_text(listing: Listing, now: datetime) -> Optional[str]:
    """品項全部都不能買時，購買選單要停用並寫上的原因；還有能買的回 None。"""
    reasons = {v.unavailable_reason(now) for v in listing.variants}
    if not reasons or None in reasons:
        return None
    return reasons.pop() if len(reasons) == 1 else "目前沒有可購買的品項"


# ── 下單 ──

def encode_items(picks: Mapping[int, int]) -> str:
    return ",".join(f"{key}x{qty}" for key, qty in picks.items())


def decode_items(text: str) -> dict[int, int]:
    picks: dict[int, int] = {}
    for part in (text or "").split(","):
        match = _ITEM_RE.fullmatch(part)
        if match is None:
            return {}
        picks[int(match[1])] = picks.get(int(match[1]), 0) + int(match[2])
    return picks


def quote_order(listing: Listing, picks: Mapping[int, int], now: datetime) -> list[tuple[Variant, int]]:
    """檢查這筆訂單現在能不能下；不行就丟 ShopError（給需求方看的理由）。"""
    if listing.closed:
        raise ShopError("這篇商品已經下架了。")
    if not picks:
        raise ShopError("沒有選任何品項。")
    lines = []
    for key, qty in picks.items():
        variant = listing.variant(key)
        if variant is None:
            raise ShopError("有品項已經被供應方刪除，請重新選擇。")
        reason = variant.unavailable_reason(now)
        if reason:
            raise ShopError(f"「{variant.name}」{reason}。")
        if qty < 1:
            raise ShopError(f"「{variant.name}」的數量至少 1。")
        if variant.remaining is not None and qty > variant.remaining:
            raise ShopError(f"「{variant.name}」只剩 {variant.remaining} 個。")
        lines.append((variant, qty))
    return lines


def order_summary(lines: Iterable[tuple[Variant, int]], unit: str) -> tuple[list[str], int, int]:
    """訂單明細（每行一項）、現在要付的（定金＋一次付清的全額）、到貨後再付的（尾款）。"""
    rows, now_total, later_total = [], 0, 0
    for variant, qty in lines:
        if variant.deposit:
            now_total += variant.price * qty
            later_total += (variant.balance or 0) * qty
            rows.append(f"{variant.name} ×{qty}（定金 {money(unit, variant.price)}，"
                        f"尾款 {money(unit, variant.balance or 0)}）＝定金 {money(unit, variant.price * qty)}")
        else:
            now_total += variant.price * qty
            note = f"，預購 {format_cutoff(variant.cutoff)} 截止" if variant.preorder else ""
            rows.append(f"{variant.name} ×{qty}（{money(unit, variant.price)}{note}）＝{money(unit, variant.price * qty)}")
    return rows, now_total, later_total


def price_signature(lines: Iterable[tuple[Variant, int]], unit: str = "") -> str:
    """確認畫面上看到的金額（含幣別）的指紋（8 碼）：按「確認下單」時重算一次，對不上就是價格在這中間改過。"""
    text = unit + "|" + ";".join(f"{v.key}:{v.price}:{v.balance or 0}:{qty}"
                                 for v, qty in sorted(lines, key=lambda line: line[0].key))
    return hashlib.sha1(text.encode()).hexdigest()[:8]


def with_taken(listing: Listing, taken: Mapping[int, int]) -> Listing:
    """換上新的已下單份數（重畫貼文前查一次資料庫）。"""
    return replace(listing, variants=tuple(replace(v, taken=taken.get(v.key, v.taken)) for v in listing.variants))
