"""商品貼文的資料，以及它在 Discord 訊息上的寫法（純資料，不連網路）。

商品貼文本身就是紀錄（使用者 2026-10-03 決定不加資料表，延續交易的做法）：
  - 標題、說明、商品圖：貼文第一則訊息的 embed。
  - 上架者 id、下一個品項編號、幣別、是否已下架：「⚙️ 管理商品（上架者）」按鈕的 custom_id 與停用狀態。
  - 每個商品（品項）：購買下拉選單的一個選項，名稱寫在 label，其餘寫在 value（`Variant.encode`）。
    選項只有 bot 寫得進去，重啟後照樣讀得回來；embed 上的商品清單只是依它產生的顯示。
  - 下單：交易 thread 裡訂單訊息上的一顆停用按鈕，custom_id 帶「商品編號x數量」（`order_custom_id`）。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Iterator, Optional
from urllib.parse import quote, unquote, urlparse

import discord

from sys_settings.time_settings import APP_TZ

BUY_PREFIX = "shop:buy:"
MANAGE_PREFIX = "shop:manage:"
ORDER_PREFIX = "shop:order:"
#: 購買下拉選單：shop:buy:商品貼文id
BUY_TEMPLATE = r"shop:buy:(?P<listing>\d+)"
#: 管理按鈕：shop:manage:上架者id:下一個品項編號:幣別（URL 編碼，單位裡有冒號也不會亂）
#: 品項編號只增不減：刪掉的編號不重用，舊訂單、舊選單才不會對到新的品項
MANAGE_TEMPLATE = r"shop:manage:(?P<owner>\d+):(?P<seq>\d+):(?P<unit>[^:]*)"
CUSTOM_ID_LIMIT = 100
_MANAGE_RE = re.compile(MANAGE_TEMPLATE)
_ITEM_RE = re.compile(r"(\d+)x(\d+)")

#: 預購截止時間一律寫年份（使用者 2026-10-03），伺服器時間
CUTOFF_FORMAT = "%Y/%m/%d %H:%M"
_CUTOFF_FORMATS = ("%Y/%m/%d %H:%M", "%Y-%m-%d %H:%M")
NAME_LIMIT = 80    # 下拉選項 label 上限 100
PRICE_MAX = 999_999_999   # 跟單一新增的 modal 一致（9 位），選項 value 才不會超過 100 字
LIMIT_MAX = 999_999       # 數量上限（6 位）
TITLE_LIMIT = 90   # 貼文標題上限 100，留空間給【已下架】
UNIT_LIMIT = 10
_SEPARATORS = re.compile(r"[｜|]")


class ShopError(Exception):
    """要直接告訴使用者的錯誤；訊息就是給人看的文字。"""


def parse_cutoff(text: str) -> datetime:
    text = text.strip()
    for fmt in _CUTOFF_FORMATS:
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=APP_TZ)
        except ValueError:
            continue
    raise ShopError(f"預購截止時間「{text}」看不懂，請寫成 2026/10/20 23:59")


def money(unit: str, amount: int) -> str:
    """金額顯示：幣別＋千分位（例 NT$100,005,000）；存的資料不變。"""
    return f"{unit}{amount:,}"


def format_cutoff(moment: datetime) -> str:
    return moment.astimezone(APP_TZ).strftime(CUTOFF_FORMAT)


@dataclass(frozen=True)
class Variant:
    """一篇商品裡的一個品項。"""

    key: int                            # 商品內的編號，建立後不變（訂單與提醒靠它對應）
    name: str
    price: int
    limit: Optional[int] = None         # None＝不限量
    taken: int = 0                      # 已下單的數量（進行中＋已完成；取消會還回來）
    cutoff: Optional[datetime] = None   # None＝立即購買；有值＝預購截止時間
    closed: bool = False                # 預購已截止，而且交易雙方都提醒過了

    @property
    def preorder(self) -> bool:
        return self.cutoff is not None

    @property
    def remaining(self) -> Optional[int]:
        return None if self.limit is None else max(self.limit - self.taken, 0)

    def unavailable_reason(self, now: datetime) -> Optional[str]:
        if self.preorder and (self.closed or now >= self.cutoff):
            return "預購已截止"
        if self.remaining == 0:
            return "已售完"
        return None

    def status(self, unit: str, now: datetime, *, rich: bool = False) -> str:
        """品項狀態。不能買的要一眼看得出來、但不突兀（使用者 2026-10-04，TR-Q38）：
        rich＝給 embed 用，價格與類型加刪除線、後面接灰底標籤；選單的說明文字不能用 Markdown，
        就把狀態放最前面，手機上後面被截斷也看得到。"""
        price = money(unit, self.price)
        kind = f"預購（{format_cutoff(self.cutoff)} 截止）" if self.preorder else "立即購買"
        reason = self.unavailable_reason(now)
        if reason:
            if rich:
                return f"~~{discord.utils.escape_markdown(f'{price}｜{kind}')}~~ `{reason}`"
            return f"{reason}｜{price}｜{kind}"
        stock = "不限量" if self.remaining is None else f"剩 {self.remaining}"
        return f"{price}｜{kind}｜{stock}"

    def encode(self) -> str:
        limit = "" if self.limit is None else str(self.limit)
        cutoff = "" if self.cutoff is None else str(int(self.cutoff.timestamp()))
        return f"{self.key}:{self.price}:{limit}:{self.taken}:{cutoff}:{int(self.closed)}"

    @classmethod
    def decode(cls, value: str, name: str) -> Optional["Variant"]:
        parts = (value or "").split(":")
        if len(parts) != 6:
            return None
        key, price, limit, taken, cutoff, closed = parts
        try:
            return cls(
                key=int(key), name=name, price=int(price),
                limit=int(limit) if limit else None, taken=int(taken),
                cutoff=datetime.fromtimestamp(int(cutoff), APP_TZ) if cutoff else None,
                closed=closed == "1",
            )
        except ValueError:
            return None


@dataclass(frozen=True)
class Draft:
    """上架者填的一個品項（還沒有編號與已下單數量）。"""

    name: str
    price: int
    limit: Optional[int]
    cutoff: Optional[datetime]

    def line(self) -> str:
        """批次格式的一行；預覽與「回去修改」都用它，往返不會走樣。"""
        limit = "" if self.limit is None else str(self.limit)
        cutoff = "" if self.cutoff is None else format_cutoff(self.cutoff)
        return f"{self.name}｜{self.price}｜{limit}｜{cutoff}"


def parse_draft(name: str, price: str, limit: str, cutoff: str, *,
                preorder: Optional[bool], now: datetime, min_limit: int = 1) -> Draft:
    """檢查上架者填的品項。preorder＝None 時看有沒有填截止時間（批次新增用）。

    min_limit：新增時數量至少 1；編輯時填的是「剩餘數量」，可以填 0（停賣、標成已售完）。"""
    name = (name or "").strip()
    if not name:
        raise ShopError("名稱不能空白")
    if len(name) > NAME_LIMIT:
        raise ShopError(f"名稱最多 {NAME_LIMIT} 個字")
    try:
        price_value = int((price or "").strip())
    except ValueError:
        raise ShopError(f"「{name}」的價格要填整數") from None
    if price_value < 0:
        raise ShopError(f"「{name}」的價格不能是負的")
    if price_value > PRICE_MAX:
        raise ShopError(f"「{name}」的價格最多 9 位數")
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
    if preorder is None:
        preorder = bool(cutoff_text)
    cutoff_value = None
    if preorder:
        if not cutoff_text:
            raise ShopError(f"「{name}」是預購，要填截止時間（例：2026/10/20 23:59）")
        cutoff_value = parse_cutoff(cutoff_text)
        if cutoff_value <= now:
            raise ShopError(f"「{name}」的截止時間已經過了")
    return Draft(name, price_value, limit_value, cutoff_value)


def parse_batch(text: str, *, now: datetime) -> tuple[list[Draft], list[str]]:
    """批次新增：一行一項「名稱｜價格｜數量｜預購截止」，數量與截止可留空。回傳（品項, 錯誤）。"""
    drafts: list[Draft] = []
    errors: list[str] = []
    for number, raw in enumerate((text or "").splitlines(), start=1):
        if not raw.strip():
            continue
        fields = [f.strip() for f in _SEPARATORS.split(raw)]
        if len(fields) < 2 or len(fields) > 4:
            errors.append(f"第 {number} 行：要寫成「名稱｜價格｜數量｜預購截止」")
            continue
        fields += [""] * (4 - len(fields))
        try:
            drafts.append(parse_draft(*fields, preorder=None, now=now))
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
    key_seq: int = 1                        # 下一個品項編號（只增不減）

    def variant(self, key: int) -> Optional[Variant]:
        return next((v for v in self.variants if v.key == key), None)

    def next_key(self) -> int:
        return max(self.key_seq, max((v.key for v in self.variants), default=0) + 1)

    def add(self, draft: "Draft") -> "Listing":
        key = self.next_key()
        variant = Variant(key=key, name=draft.name, price=draft.price, limit=draft.limit, cutoff=draft.cutoff)
        return replace(self.with_variant(variant), key_seq=key + 1)

    def has_open_preorder(self) -> bool:
        return any(v.preorder and not v.closed for v in self.variants)

    def with_variant(self, variant: Variant) -> "Listing":
        if self.variant(variant.key) is None:
            return replace(self, variants=self.variants + (variant,))
        return replace(self, variants=tuple(variant if v.key == variant.key else v for v in self.variants))

    def without_variant(self, key: int) -> "Listing":
        return replace(self, variants=tuple(v for v in self.variants if v.key != key))


def manage_custom_id(owner_id: int, key_seq: int, unit: str) -> str:
    return f"{MANAGE_PREFIX}{owner_id}:{key_seq}:{quote(unit, safe='')}"


def unit_fits(unit: str) -> bool:
    """幣別編碼後要塞得進管理按鈕的 custom_id（中文一個字編碼後佔 9 個字元）。

    用最長的使用者 id（20 位）與三位數的品項編號估算，規則就不會因人而異：中文大約 7 個字以內。"""
    return len(manage_custom_id(10 ** 19, 999, unit)) <= CUSTOM_ID_LIMIT


def buy_custom_id(listing_id: int) -> str:
    return f"{BUY_PREFIX}{listing_id}"


def _children(message) -> Iterator[object]:
    for row in getattr(message, "components", None) or ():
        yield from getattr(row, "children", None) or ()


def listing_from_message(message) -> Optional[Listing]:
    """從商品貼文的第一則訊息讀回商品；不是商品貼文就回 None。"""
    owner_id = unit = None
    key_seq = 1
    closed = False
    variants: list[Variant] = []
    for child in _children(message):
        custom_id = getattr(child, "custom_id", None) or ""
        if custom_id.startswith(MANAGE_PREFIX):
            match = _MANAGE_RE.fullmatch(custom_id)
            if match:
                owner_id, unit = int(match["owner"]), unquote(match["unit"])
                key_seq = int(match["seq"])
                closed = bool(getattr(child, "disabled", False))
        elif custom_id.startswith(BUY_PREFIX):
            for option in getattr(child, "options", None) or ():
                variant = Variant.decode(option.value, option.label)
                if variant is not None:
                    variants.append(variant)
    if owner_id is None:
        return None
    embed = message.embeds[0] if getattr(message, "embeds", None) else None
    image = None
    image_url = getattr(getattr(embed, "image", None), "url", None) if embed else None
    if image_url:
        # 送出後 Discord 回的是 CDN 網址（…/item_1.png?ex=…），自己組的則是 attachment://item_1.png
        if image_url.startswith("attachment://"):
            image = image_url[len("attachment://"):] or None
        else:
            image = urlparse(image_url).path.rsplit("/", 1)[-1] or None
    return Listing(
        thread_id=message.channel.id, owner_id=owner_id, unit=unit,
        title=(embed.title if embed else "") or "", description=(embed.description if embed else "") or "",
        image=image, variants=tuple(variants), closed=closed, key_seq=key_seq,
    )


def render_embed(listing: Listing, owner_name: str, now: datetime) -> discord.Embed:
    embed = discord.Embed(title=listing.title, description=listing.description or None, color=discord.Color.gold())
    embed.set_author(name=f"上架者：{owner_name}")
    for number, variant in enumerate(listing.variants, start=1):
        embed.add_field(name=f"{number}. {variant.name}", value=variant.status(listing.unit, now, rich=True), inline=False)
    if not listing.variants:
        embed.add_field(name="商品", value="上架者還沒加入商品，暫時不能購買。", inline=False)
    if listing.closed:
        embed.set_footer(text="這篇商品已下架")
    else:
        embed.set_footer(text="從下方選單挑要買的商品；上架者用「⚙️ 管理商品（上架者）」管理")
    if listing.image:
        embed.set_image(url=f"attachment://{listing.image}")
    return embed


def select_options(listing: Listing, now: datetime) -> list[discord.SelectOption]:
    """購買下拉選單的選項。賣完或截止的也留著：品項資料就存在這裡。"""
    return [
        discord.SelectOption(label=v.name, value=v.encode(), description=v.status(listing.unit, now)[:100])
        for v in listing.variants
    ]


# ── 下單 ──

def encode_items(picks: dict[int, int]) -> str:
    return ",".join(f"{key}x{qty}" for key, qty in picks.items())


def decode_items(text: str) -> dict[int, int]:
    picks: dict[int, int] = {}
    for part in (text or "").split(","):
        match = _ITEM_RE.fullmatch(part)
        if match is None:
            return {}
        picks[int(match[1])] = picks.get(int(match[1]), 0) + int(match[2])
    return picks


def order_custom_id(listing_id: int, picks: dict[int, int]) -> str:
    return f"{ORDER_PREFIX}{listing_id}:{encode_items(picks)}"


def orders_on(message) -> Iterator[tuple[int, dict[int, int]]]:
    """交易 thread 裡一則訊息上的訂單（商品貼文id, {商品編號: 數量}）。"""
    for child in _children(message):
        custom_id = getattr(child, "custom_id", None) or ""
        if not custom_id.startswith(ORDER_PREFIX):
            continue
        listing_id, _, items = custom_id[len(ORDER_PREFIX):].partition(":")
        picks = decode_items(items)
        if listing_id.isdigit() and picks:
            yield int(listing_id), picks


def quote_order(listing: Listing, picks: dict[int, int], now: datetime) -> list[tuple[Variant, int]]:
    """檢查這筆訂單現在能不能下；不行就丟 ShopError（給買家看的理由）。"""
    if listing.closed:
        raise ShopError("這篇商品已經下架了。")
    if not picks:
        raise ShopError("沒有選任何商品。")
    lines = []
    for key, qty in picks.items():
        variant = listing.variant(key)
        if variant is None:
            raise ShopError("有商品已經被上架者刪除，請重新選擇。")
        reason = variant.unavailable_reason(now)
        if reason:
            raise ShopError(f"「{variant.name}」{reason}。")
        if qty < 1:
            raise ShopError(f"「{variant.name}」的數量至少 1。")
        if variant.remaining is not None and qty > variant.remaining:
            raise ShopError(f"「{variant.name}」只剩 {variant.remaining} 個。")
        lines.append((variant, qty))
    return lines


def apply_order(listing: Listing, picks: dict[int, int]) -> Listing:
    for key, qty in picks.items():
        variant = listing.variant(key)
        if variant is not None:
            listing = listing.with_variant(replace(variant, taken=variant.taken + qty))
    return listing


def release_order(listing: Listing, picks: dict[int, int]) -> Listing:
    """取消時把預留的數量還回去（品項被刪掉的就略過）。"""
    for key, qty in picks.items():
        variant = listing.variant(key)
        if variant is not None:
            listing = listing.with_variant(replace(variant, taken=max(variant.taken - qty, 0)))
    return listing


def order_summary(lines: list[tuple[Variant, int]], unit: str) -> tuple[list[str], int]:
    """訂單明細（每行一項）與總計。"""
    rows, total = [], 0
    for variant, qty in lines:
        subtotal = variant.price * qty
        total += subtotal
        note = f"，預購 {format_cutoff(variant.cutoff)} 截止" if variant.preorder else ""
        rows.append(f"{variant.name} ×{qty}（{money(unit, variant.price)}{note}）＝{money(unit, subtotal)}")
    return rows, total
