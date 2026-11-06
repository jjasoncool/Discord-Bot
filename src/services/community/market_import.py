"""上線匯入：把 Discord 上的舊商品貼文與還開著的交易對話一次搬進市集資料庫，搬完才開放商品與交易按鈕。

架構定位：功能層（`services.community`）。
  - 上層（誰呼叫）：介面 `commands.shop_commands`（bot 連上後跑一次；失敗私訊群主，群主按「重新偵測」重跑）。
  - 下層（呼叫誰）：商品服務（商品論壇、照資料庫重畫貼文）、交易模組（購物車裡的交易對話、讀整串）、
    市集資料庫；舊格式（品項資料寫在選單選項、訂單寫在停用按鈕）的解析在這裡，只有匯入用。

介面：
  - `run_import(shop)` → `ImportResult`：做完（或之前已經做完）回結果並打開 `TradeService.ready`；失敗丟例外。
  - `preview_import(shop)` → 文字：照同一套讀法列出會匯入什麼（上線前給群主核對），不寫資料庫、不動 Discord。
  - 舊格式解析：`legacy_listing`（商品貼文第一則訊息）、`legacy_orders`（交易對話裡一則訂單訊息）、`order_unit_prices`。

規則：
  - 先把 Discord 讀完、把舊格式原文匯出成一個 JSON 檔（跟每日備份放一起），再在一個資料庫交易裡全部寫進去
    （全有或全無），寫完記 `meta.import_written`；
    接著把每篇商品貼文照資料庫重畫成新格式，全部重畫完記 `meta.import_done`。重跑時寫過的不再寫，只補重畫。
  - 匯入的商品交付方式一律實體（現有商品都是寄送的）。商品的交易寫成舊交易（legacy）後，接著轉成新流程、
    在每個交易對話補發交易進度（不 @ 人；上線時都還沒付）；標題寫【定金】的（舊格式沒有定金＋尾款）先留在舊流程，
    等觀星者在管理面板整篇改成定金＋尾款時才轉。自由市場的交易照舊流程。
    已結束的交易不匯。商品論壇或購物車讀不到時當成失敗（不然會記下「匯入完成」，之後綁好也不再匯）。
  - 做完才打開 `TradeService.ready`，再補開匯入期間收到的接單表情。

例外與決策：
  - 舊商品貼文的「已下單」包含已完成的交易；資料庫裡已下單＝sold_before＋還開著的交易品項，
    所以 sold_before＝舊的已下單－這次匯入的交易份數（算出負的就當 0、記 WARNING）。
  - 舊訂單的單價從訂單文字讀，用按鈕上的總計核對；讀不到就用品項現價並記 WARNING。
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Iterator, Optional
from urllib.parse import unquote

import discord

from services.community import trade_progress as tp
from services.community import market_transition as transition
from services.community.shop_listing import embed_image_name
from sys_settings.paths import MARKET_BACKUP_DIR
from sys_settings.time_settings import APP_TZ

if TYPE_CHECKING:
    from services.community.shop_service import ShopService

logger = logging.getLogger(__name__)

META_WRITTEN = "import_written"
META_DONE = "import_done"
#: 寫進資料庫時的數字（JSON：商品、交易、警告幾則）；重畫失敗重跑時，回報的還是第一次匯入的數字
META_SUMMARY = "import_summary"
#: 認不出身分的舊交易對話（JSON 的 thread id 清單）：沒有匯入，群主的交易看板列出來請人工處理
UNRECOGNIZED_META = "import_unrecognized"

_MANAGE_RE = re.compile(r"shop:manage:(?P<owner>\d+):(?P<seq>\d+):(?P<unit>[^:]*)")
_ORDER_PREFIX = "shop:order:"
_ITEMS_RE = re.compile(r"(\d+)x(\d+)")
_ROW_RE = re.compile(r"^・(?P<name>.+?) ×(?P<qty>\d+)（(?P<price>[^，）]+)", re.MULTILINE)
_DIGITS_RE = re.compile(r"([\d,]+)\s*$")


@dataclass(frozen=True)
class LegacyVariant:
    key: int
    name: str
    price: int
    limit: Optional[int]
    taken: int
    cutoff: Optional[datetime]
    closed: bool


@dataclass(frozen=True)
class LegacyListing:
    thread_id: int
    owner_id: int
    unit: str
    seq: int
    closed: bool
    title: str
    description: str
    image: Optional[str]
    variants: tuple[LegacyVariant, ...]
    #: 選單上原本的（名稱, value），匯出備份用；讀不懂的也在這裡
    raw_options: tuple[tuple[str, str], ...] = ()
    #: 讀不懂、沒有匯入的選項名稱
    skipped: tuple[str, ...] = ()


@dataclass
class LegacyOrder:
    message_id: int
    created_at: datetime
    picks: dict[int, int]
    prices: dict[int, int]
    total: Optional[int]


@dataclass
class LegacyTrade:
    thread_id: int
    kind: str
    source_id: int
    requester_id: int
    supplier_id: int
    opened_at: datetime
    opening_id: Optional[int]
    orders: list[LegacyOrder] = field(default_factory=list)
    receipt: Optional[tuple[int, datetime, bool]] = None   # (訊息, 時間, 提醒過沒)
    last_chat: Optional[datetime] = None                   # 最後一則真人訊息（看板算幾天沒動靜）


@dataclass(frozen=True)
class ImportResult:
    listings: int = 0
    trades: int = 0
    warnings: tuple[str, ...] = ()
    already_done: bool = False

    def summary(self) -> str:
        if self.already_done:
            return "商品市集之前已經匯入過。"
        text = f"商品市集匯入完成：商品 {self.listings} 篇、進行中的交易 {self.trades} 筆。"
        if self.warnings:
            text += f"有 {len(self.warnings)} 則要看一下（詳細寫在 log）。"
        return text


def _children(message) -> Iterator[object]:
    for row in getattr(message, "components", None) or ():
        yield from getattr(row, "children", None) or ()


def _decode_variant(value: str, name: str) -> Optional[LegacyVariant]:
    """舊選項 value「編號:價格:上限:已下單:截止(epoch):已截止」。"""
    parts = (value or "").split(":")
    if len(parts) != 6:
        return None
    key, price, limit, taken, cutoff, closed = parts
    try:
        return LegacyVariant(key=int(key), name=name, price=int(price), limit=int(limit) if limit else None,
                             taken=int(taken), cutoff=datetime.fromtimestamp(int(cutoff), APP_TZ) if cutoff else None,
                             closed=closed == "1")
    except ValueError:
        return None


def legacy_listing(message) -> Optional[LegacyListing]:
    """舊商品貼文的第一則訊息 → 商品；不是舊格式的商品貼文回 None。"""
    owner_id = unit = None
    seq, closed = 1, False
    variants: list[LegacyVariant] = []
    raw: list[tuple[str, str]] = []
    skipped: list[str] = []
    for child in _children(message):
        custom_id = getattr(child, "custom_id", None) or ""
        match = _MANAGE_RE.fullmatch(custom_id)
        if match:
            owner_id, unit, seq = int(match["owner"]), unquote(match["unit"]), int(match["seq"])
            closed = bool(getattr(child, "disabled", False))
        elif custom_id.startswith("shop:buy:"):
            for option in getattr(child, "options", None) or ():
                raw.append((option.label, option.value))
                variant = _decode_variant(option.value, option.label)
                if variant is not None:
                    variants.append(variant)
                else:
                    skipped.append(option.label)
    if owner_id is None:
        return None
    embed = message.embeds[0] if getattr(message, "embeds", None) else None
    return LegacyListing(
        thread_id=message.channel.id, owner_id=owner_id, unit=unit, seq=seq, closed=closed,
        title=(embed.title if embed else "") or "", description=(embed.description if embed else "") or "",
        image=embed_image_name(embed), variants=tuple(variants), raw_options=tuple(raw), skipped=tuple(skipped))


def legacy_orders(message) -> list[tuple[int, dict[int, int], Optional[int]]]:
    """交易對話裡一則訊息上的舊訂單：(商品貼文id, {編號: 份數}, 按鈕上的總計或 None)。"""
    found = []
    for child in _children(message):
        custom_id = getattr(child, "custom_id", None) or ""
        if not custom_id.startswith(_ORDER_PREFIX):
            continue
        listing_id, _, items = custom_id[len(_ORDER_PREFIX):].partition(":")
        picks: dict[int, int] = {}
        for part in items.split(","):
            match = _ITEMS_RE.fullmatch(part)
            if match is None:
                picks = {}
                break
            picks[int(match[1])] = picks.get(int(match[1]), 0) + int(match[2])
        label = getattr(child, "label", None) or ""
        total_match = _DIGITS_RE.search(label) if label.startswith("總計") else None
        total = int(total_match[1].replace(",", "")) if total_match else None
        if listing_id.isdigit() and picks:
            found.append((int(listing_id), picks, total))
    return found


def order_unit_prices(content: str, picks: dict[int, int]) -> dict[int, int]:
    """從訂單文字讀每個品項的單價。一行一項，順序跟訂單按鈕上的品項一樣；份數對不上就整筆不信。"""
    rows = list(_ROW_RE.finditer(content or ""))
    if len(rows) != len(picks):
        return {}
    prices = {}
    for (key, qty), row in zip(picks.items(), rows):
        digits = _DIGITS_RE.search(row["price"].strip())
        if int(row["qty"]) != qty or digits is None:
            return {}
        prices[key] = int(digits[1].replace(",", ""))
    return prices


async def run_import(shop: "ShopService", *, export_dir: Optional[Path] = None) -> ImportResult:
    """export_dir：重畫貼文前把讀到的舊格式原文匯出成一個 JSON 檔的資料夾（預設跟每日備份放一起）。"""
    trade = shop.trade
    db = await trade.db()
    done_at = await db.get_meta(META_DONE)
    if done_at:
        # 平常的重啟：連上到這裡的那幾秒按的接單表情也要補開
        trade.orphans_after = datetime.fromisoformat(done_at)
        trade.ready.set()
        await trade.replay_deferred()
        return ImportResult(already_done=True)
    if not await db.get_meta(META_WRITTEN):
        warnings: list[str] = []
        unrecognized: list[int] = []
        listings = await _collect_listings(shop, warnings)
        trades = await _collect_trades(shop, {listing.thread_id: listing for listing in listings}, warnings,
                                       unrecognized)
        sold_before = _sold_before(listings, trades, warnings)
        for warning in warnings:
            logger.warning("市集匯入：%s", warning)
        # 重畫之後舊格式的資料就只剩資料庫一份：先把原文留一份，匯入有問題時可以對照或重來
        await _export(export_dir or MARKET_BACKUP_DIR, shop.stamp(), listings, trades, warnings)
        await _write(shop, listings, trades, warnings, unrecognized, sold_before)
    summary = json.loads(await db.get_meta(META_SUMMARY) or "{}")
    for row in await db.listings():
        async with shop.lock(row.id):
            await shop.redraw(row.id)
    # 舊交易接上新流程（上線時都還沒付）：標題寫【定金】的等觀星者整篇改成定金＋尾款時才轉（尾款與截止只有他知道）。
    # 一筆出錯不擋匯入：截止排程每一輪照同一條規則補轉
    await transition.adopt_ready(shop)
    done_at = shop.stamp()
    async with db.transaction():
        await db.set_meta(META_DONE, done_at)
    trade.orphans_after = datetime.fromisoformat(done_at)
    trade.ready.set()
    replayed = await trade.replay_deferred()
    result = ImportResult(summary.get("listings", 0), summary.get("trades", 0),
                          tuple(f"警告 {i + 1}" for i in range(summary.get("warnings", 0))))
    logger.info("市集匯入：%s（匯入期間的接單補開 %s 個）", result.summary(), replayed)
    return result


async def preview_import(shop: "ShopService") -> str:
    """不寫資料庫、不動 Discord，照上線匯入的讀法列出會匯入的商品、品項與進行中的交易，加上警告。
    跟正式匯入用同一組讀取與解析（`_collect_listings`、`_collect_trades`、`_sold_before`），列出來的就是會寫進去的。"""
    warnings: list[str] = []
    unrecognized: list[int] = []
    listings = await _collect_listings(shop, warnings)
    by_id = {listing.thread_id: listing for listing in listings}
    trades = await _collect_trades(shop, by_id, warnings, unrecognized)
    sold_before = _sold_before(listings, trades, warnings)
    forum = await shop._forum()
    people = {listing.owner_id for listing in listings} | {t.requester_id for t in trades} | {t.supplier_id for t in trades}
    names = await shop.trade.display_names(getattr(forum, "guild", None), sorted(people))

    def who(user_id: int) -> str:
        return names.get(user_id) or f"（不在伺服器）{user_id}"

    open_qty: dict[tuple[int, int], int] = {}
    for trade in trades:
        for order in trade.orders:
            for key, qty in order.picks.items():
                open_qty[(trade.source_id, key)] = open_qty.get((trade.source_id, key), 0) + qty
    lines = [f"# 上線匯入預覽（只讀，什麼都還沒寫）", "",
             f"商品 {len(listings)} 篇（交付方式一律實體）、進行中的交易 {len(trades)} 筆、警告 {len(warnings)} 條、"
             f"認不出身分的交易對話 {len(unrecognized)} 個", "", "## 商品"]
    for number, listing in enumerate(listings, start=1):
        flags = "，已下架" if listing.closed else ""
        lines.append(f"{number}. {listing.title}（貼文 {listing.thread_id}）　供應方：{who(listing.owner_id)}　"
                     f"幣別：{listing.unit or '（沒寫）'}{flags}")
        for variant in listing.variants:
            kind = f"預購，截止 {variant.cutoff.astimezone(APP_TZ):%Y/%m/%d %H:%M}" if variant.cutoff else "現貨"
            if variant.closed:
                kind += "（已截止）"
            limit = "不限量" if variant.limit is None else f"上限 {variant.limit}"
            in_trades = open_qty.get((listing.thread_id, variant.key), 0)
            lines.append(f"   - 品項 {variant.key}「{variant.name}」{variant.price}｜{kind}｜{limit}｜"
                         f"舊貼文上的已下單 {variant.taken} ＝ 上線前賣掉的 {sold_before[(listing.thread_id, variant.key)]}"
                         f" ＋ 進行中的交易 {in_trades}")
        if listing.skipped:
            lines.append(f"   - 讀不懂、不會匯入的選項：{'、'.join(listing.skipped)}")
    lines += ["", "## 進行中的交易"]
    for number, trade in enumerate(trades, start=1):
        if trade.kind == "listing":
            listing = by_id.get(trade.source_id)
            source = f"商品「{listing.title}」" if listing else f"商品 {trade.source_id}"
            if listing is not None and listing.title.startswith(transition.DEPOSIT_TITLE):
                after = "先留在舊流程，等觀星者整篇改成定金＋尾款時轉成新流程、補發交易進度"
            else:
                after = "匯入時轉成新流程、補發交易進度（不 @ 人）"
        else:
            source = f"自由市場需求 {trade.source_id}"
            after = "自由市場：照舊流程"
        lines.append(f"{number}. 交易對話 {trade.thread_id}　{source}　需求方：{who(trade.requester_id)}　"
                     f"供應方：{who(trade.supplier_id)}　開單 {trade.opened_at.astimezone(APP_TZ):%Y/%m/%d}　→ {after}")
        for order in trade.orders:
            picks = "、".join(f"品項 {key} ×{qty}（單價 {order.prices.get(key, 0)}）" for key, qty in order.picks.items())
            total = f"，按鈕上的總計 {order.total}" if order.total is not None else ""
            lines.append(f"   - 訂單 {order.created_at.astimezone(APP_TZ):%Y/%m/%d}：{picks}{total}")
        if trade.kind == "listing" and not trade.orders:
            lines.append("   - 沒讀到訂單")
        if trade.receipt is not None:
            lines.append(f"   - 有一則還在等的領收通知（{trade.receipt[1].astimezone(APP_TZ):%Y/%m/%d %H:%M}），"
                         "匯入後照舊倒數自動領收")
    if warnings:
        lines += ["", "## 警告"] + [f"- {warning}" for warning in warnings]
    if unrecognized:
        lines += ["", "## 認不出身分的交易對話（不會匯入，會列在群主的交易看板）"] + [f"- {i}" for i in unrecognized]
    return "\n".join(lines)


async def _export(folder: Path, stamp: str, listings: list[LegacyListing], trades: list[LegacyTrade],
                  warnings: list[str]) -> Path:
    data = {
        "exported_at": stamp,
        "listings": [dict(thread_id=l.thread_id, owner_id=l.owner_id, unit=l.unit, seq=l.seq, closed=l.closed,
                          title=l.title, description=l.description, image=l.image,
                          options=[dict(label=label, value=value) for label, value in l.raw_options],
                          skipped=list(l.skipped)) for l in listings],
        "trades": [dict(thread_id=t.thread_id, kind=t.kind, source_id=t.source_id, requester_id=t.requester_id,
                        supplier_id=t.supplier_id, opened_at=t.opened_at.isoformat(), opening_id=t.opening_id,
                        orders=[dict(message_id=o.message_id, created_at=o.created_at.isoformat(), picks=o.picks,
                                     prices=o.prices, total=o.total) for o in t.orders],
                        receipt=None if t.receipt is None else dict(message_id=t.receipt[0],
                                                                    at=t.receipt[1].isoformat(),
                                                                    reminded=t.receipt[2]))
                   for t in trades],
        "warnings": warnings,
    }
    path = Path(folder) / f"import_source_{stamp[:19].replace(':', '').replace('-', '')}.json"

    def write() -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    await asyncio.to_thread(write)
    logger.info("市集匯入：舊格式原文已匯出 %s", path)
    return path


async def _collect_listings(shop: "ShopService", warnings: list[str]) -> list[LegacyListing]:
    forum = await shop._forum()
    if forum is None:
        # 當成失敗：照樣算成功的話會記下「匯入完成」，之後綁好頻道也不會再匯
        raise RuntimeError("商品論壇沒有綁定或讀不到，沒辦法匯入；綁好後按「重新偵測」重跑")
    threads: dict[int, discord.Thread] = {t.id: t for t in list(getattr(forum, "threads", None) or ())}
    async for thread in forum.archived_threads(limit=None):
        threads.setdefault(thread.id, thread)
    found = []
    for thread in threads.values():
        try:
            starter = await thread.fetch_message(thread.id)
        except discord.NotFound:
            continue
        listing = legacy_listing(starter)
        if listing is not None:
            found.append(listing)
            if listing.skipped:
                warnings.append(f"商品 {listing.thread_id} 有讀不懂的品項沒有匯入：{'、'.join(listing.skipped)}")
    return found


async def _collect_trades(shop: "ShopService", listings: dict[int, LegacyListing],
                          warnings: list[str], unrecognized: list[int]) -> list[LegacyTrade]:
    trade_service = shop.trade
    db = await trade_service.db()
    if await trade_service._channel(trade_service.settings.cart_channel_key) is None:
        raise RuntimeError("購物車頻道沒有綁定或讀不到，沒辦法匯入進行中的交易；綁好後按「重新偵測」重跑")
    found = []
    async for thread in trade_service.open_trade_threads():
        if await db.get_trade(thread.id) is not None:
            continue
        log = await trade_service.read(thread)
        ref = log.ref
        if ref is None:
            warnings.append(f"認不出身分的舊交易對話 {thread.id}（{thread.name}），沒有匯入")
            unrecognized.append(thread.id)
            continue
        opening = log.opening()
        orders = []
        for message in log.bot_messages():
            for listing_id, picks, total in legacy_orders(message):
                if listing_id != ref.source_id:
                    continue
                prices = order_unit_prices(message.content, picks)
                listing = listings.get(listing_id)
                if not prices:
                    current = {v.key: v.price for v in listing.variants} if listing else {}
                    prices = {key: current.get(key, 0) for key in picks}
                    warnings.append(f"交易 {thread.id} 的訂單 {message.id} 讀不到單價，改用品項現價 {prices}")
                computed = sum(prices[key] * qty for key, qty in picks.items())
                if total is not None and total != computed:
                    warnings.append(f"交易 {thread.id} 的訂單 {message.id} 總計 {total} 跟單價算出的 {computed} 對不上")
                orders.append(LegacyOrder(message.id, message.created_at, picks, prices, total))
        kind = "listing" if orders or ref.source_id in listings else "forum"
        receipt = None
        pending = log.pending_receipt()
        if pending is not None:
            emoji = trade_service.settings.receipt_reminded_emoji
            reminded = any(str(r.emoji) == emoji and getattr(r, "me", False)
                           for r in getattr(pending, "reactions", None) or ())
            receipt = (pending.id, pending.created_at, reminded)
        opened_at = opening.created_at if opening is not None else getattr(thread, "created_at", None)
        people = [m.created_at for m in log.messages if not getattr(m.author, "bot", False)]
        found.append(LegacyTrade(thread.id, kind, ref.source_id, ref.requester_id, ref.supplier_id,
                                 opened_at or shop.now(), opening.id if opening is not None else None, orders, receipt,
                                 max(people) if people else None))
    return found


def _sold_before(listings: list[LegacyListing], trades: list[LegacyTrade],
                 warnings: list[str]) -> dict[tuple[int, int], int]:
    """每個品項上線前賣掉、沒有匯入交易的份數（＝舊的已下單－這次匯入的交易份數）；算出負的記 0 並加一條警告。"""
    open_qty: dict[tuple[int, int], int] = {}
    for trade in trades:
        for order in trade.orders:
            for key, qty in order.picks.items():
                open_qty[(trade.source_id, key)] = open_qty.get((trade.source_id, key), 0) + qty
    result = {}
    for listing in listings:
        for variant in listing.variants:
            in_trades = open_qty.get((listing.thread_id, variant.key), 0)
            value = variant.taken - in_trades
            if value < 0:
                warnings.append(f"商品 {listing.thread_id} 品項 {variant.key} 的已下單 {variant.taken} "
                                f"比進行中的交易份數 {in_trades} 少，sold_before 記 0")
                value = 0
            result[(listing.thread_id, variant.key)] = value
    return result


async def _write(shop: "ShopService", listings: list[LegacyListing], trades: list[LegacyTrade],
                 warnings: list[str], unrecognized: list[int], sold_before: dict[tuple[int, int], int]) -> None:
    db = await shop.trade.db()
    now = shop.stamp()
    variants_by_listing = {listing.thread_id: {v.key: v for v in listing.variants} for listing in listings}
    async with db.transaction():
        for listing in listings:
            if await db.get_listing(listing.thread_id) is not None:
                continue
            next_key = max([listing.seq] + [v.key + 1 for v in listing.variants])
            # 現有的商品都是實體交付（寄出、需求方按已收到）；上線前的舊交易照舊流程，不受影響
            await db.insert_listing(id=listing.thread_id, owner_id=listing.owner_id, title=listing.title,
                                    description=listing.description, unit=listing.unit, delivery="physical",
                                    image=listing.image, now=now, closed=listing.closed, next_key=next_key)
            for variant in listing.variants:
                # 已經截止的舊預購：截止通知舊程式已經發過了，記成發過，不會在上線時再 @ 一輪
                await db.insert_variant(
                    listing.thread_id, key=variant.key, name=variant.name,
                    kind="preorder" if variant.cutoff else "instant", price=variant.price,
                    limit_qty=variant.limit, sold_before=sold_before[(listing.thread_id, variant.key)],
                    cutoff=variant.cutoff.isoformat() if variant.cutoff else None,
                    cutoff_done=variant.closed, cutoff_noticed=variant.closed, now=now)
        for trade in trades:
            await db.insert_trade(id=trade.thread_id, source_kind=trade.kind, source_id=trade.source_id,
                                  requester_id=trade.requester_id, supplier_id=trade.supplier_id,
                                  now=trade.opened_at.isoformat(), legacy=True)
            await db.add_event(trade.thread_id, tp.OPENED, now=trade.opened_at.isoformat(),
                               actor_id=trade.supplier_id, message_id=trade.opening_id, source="import")
            if trade.last_chat is not None:
                await db.note_chat(trade.thread_id, trade.last_chat.isoformat())
            known = variants_by_listing.get(trade.source_id, {})
            for order in trade.orders:
                order_id = await db.add_event(
                    trade.thread_id, tp.ORDER, now=order.created_at.isoformat(), items=order.picks,
                    amount=sum(order.prices[key] * qty for key, qty in order.picks.items()),
                    actor_id=trade.requester_id, message_id=order.message_id, source="import")
                await db.insert_items(trade.thread_id, order_id, [
                    dict(variant_key=key, name=known[key].name if key in known else f"品項 {key}",
                         kind="preorder" if key in known and known[key].cutoff else "instant", qty=qty,
                         unit_price=order.prices[key])
                    for key, qty in order.picks.items()])
            if trade.receipt is not None:
                message_id, at, reminded = trade.receipt
                await db.add_event(trade.thread_id, tp.RECEIPT_REQUESTED, now=at.isoformat(),
                                   actor_id=trade.supplier_id, message_id=message_id, source="import")
                if reminded:
                    await db.add_event(trade.thread_id, tp.RECEIPT_REMINDED, now=at.isoformat(), source="import")
        await db.set_meta(UNRECOGNIZED_META, json.dumps(unrecognized))
        await db.set_meta(META_SUMMARY, json.dumps(dict(listings=len(listings), trades=len(trades),
                                                        warnings=len(warnings))))
        await db.set_meta(META_WRITTEN, now)
    logger.info("市集匯入：寫進資料庫 商品 %s 篇、交易 %s 筆", len(listings), len(trades))
