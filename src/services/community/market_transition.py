"""上線銜接：上線前的【定金】商品（舊格式沒有「定金＋尾款」，照一次付清匯入）在觀星者整篇改成定金＋尾款之前的規則與動作。

架構定位：功能層（`services.community`），只依賴商品模型（`shop_listing`）、功能開關與傳進來的商品服務。
  - 上層（誰呼叫）：商品服務（下單、下架、排程補轉）、商品交易（舊交易能不能往下走、截止與延期通知）、
    市集統計（週報與「📋 我的交易」的待辦）、上線匯入（哪些舊交易匯入時就轉）、介面的管理面板與表單。
  - 下層（呼叫誰）：`ShopService` 公開的方法（鎖、讀寫、重畫、舊交易接上新流程）、`TradeService.open_trades_for_source`。

介面：
  - `enabled()`：開關 `market_transition`（`settings/switches.json`，on／off，改了下一次用到就生效、不用重啟）。
  - `waits_for_deposit(listing)`：標題寫【定金】、品項還不是定金＋尾款。
  - `holds_orders(trade, listing)`：那種商品還掛著上線前的舊交易：先不接新訂單、不能下架。
  - `can_convert(trade, listing)`：管理面板要不要放「💰 改成定金＋尾款」。
  - `convert(shop, listing_id, actor, cutoff_text, balances)`：整篇改成定金＋尾款，上面的舊交易接上新流程。
    尾款是 {品項編號: 填的字}（表單每個品項一格，`FIELD_LIMIT` 個以內）或一段多行文字（品項太多時）。
  - `adopt_ready(shop)`：商品準備好了的舊交易接上新流程（匯入時、截止排程每一輪；做到一半中斷也補得完）。
  - 給人看的句子：`WAITS_TEXT`（舊交易先不能往下走）、`ORDERS_HELD_TEXT`、`CLOSE_HELD_TEXT`、`TODO_TEXT`。

規則：
  - 開關關掉時這裡的判斷一律回「不擋、不轉」，核心流程照一般規則（商品可以下單、舊交易照舊流程做完）。
    所以要等那幾篇都改好才關；改好之後這些判斷本來就不會再成立，關掉不影響其他商品。
  - 確認沒問題、開關關掉之後，刪掉這個模組與核心裡問它的那幾行；「改類型時舊交易接上新流程」
    （`ShopService.adopt_legacy_on`、`ListingTrades.adopt_legacy`）是一般功能，留著。

例外與決策：
  - 【定金】從標題認（觀星者自己的命名習慣）：上線時 5 篇都是這樣寫，舊格式沒有別的欄位分得出來。
  - 表單每個品項一格、格子底下寫出定金：觀星者最容易把總價當尾款，寫進舊交易後他自己改不回來。
    表單最多 5 格、扣掉截止剩 4 格，超過才退回一格多行（「編號. 名稱｜尾款」）。
  - 兩個品項以上的商品不能一個一個改：定金品項不能跟一次付清的放同一篇（一起買的現貨會被拖到尾款收完才完成），
    所以按鈕整篇一起改；原本的價格當定金，每個品項填尾款、整篇一個收定金截止。
"""
from __future__ import annotations

import logging
import re
from datetime import timedelta
from typing import TYPE_CHECKING, Mapping, Sequence

import discord

from services.community.shop_listing import PRICE_MAX, Listing, ShopError, Variant, format_cutoff, parse_cutoff
from sys_settings import switches

if TYPE_CHECKING:
    from services.community.shop_service import ShopService
    from services.community.trade_service import TradeService

logger = logging.getLogger(__name__)

#: 標題寫這個的商品是定金＋尾款
DEPOSIT_TITLE = "【定金】"
WAITS_TEXT = ("這篇商品要先改成定金＋尾款（供應方在商品的管理面板按「💰 改成定金＋尾款」），"
              "改好後這筆交易會接上新的交易進度再繼續。")
ORDERS_HELD_TEXT = "這篇商品的付款方式還在設定（定金＋尾款），暫時不能下單，請稍後再試。"
CLOSE_HELD_TEXT = "這篇還有上線前的定金交易，請先按「💰 改成定金＋尾款」，改好後再下架。"
#: 表單最多 5 格，扣掉收定金截止，品項這麼多個以內才每個品項一格
FIELD_LIMIT = 4
TODO_TEXT = "上線前開的定金交易：先在商品的管理面板按「💰 改成定金＋尾款」填尾款與截止"
PANEL_NOTE = ("上線前的定金交易還在等：按「💰 改成定金＋尾款」填好收定金截止與尾款，就會開放下單、"
              "舊交易也會接上新的交易進度。")
_BALANCE_LINE = re.compile(r"^\s*(\d+)\s*[.．、]?.*?[｜|]\s*([\d,，]+)\s*$")


def enabled() -> bool:
    return switches.current().market_transition == "on"


def waits_for_deposit(listing) -> bool:
    """標題寫【定金】、品項卻還不是定金＋尾款（開關關掉時一律 False）。"""
    return (enabled() and listing is not None and listing.title.startswith(DEPOSIT_TITLE)
            and not listing.has_deposit())


async def holds_orders(trade: "TradeService", listing: Listing) -> bool:
    """還掛著上線前的舊交易、還沒改成定金＋尾款：先不接新訂單、不能下架（改好前開的單會是一次付清、沒有尾款，
    而且一有上線後的交易，整篇就改不成定金、舊交易也接不上了）。上線後新開的【定金】商品沒有舊交易要等，不擋。"""
    if not waits_for_deposit(listing):
        return False
    return any(t.legacy for t in await trade.open_trades_for_source(listing.thread_id))


async def can_convert(trade: "TradeService", listing: Listing) -> bool:
    """有上線後開的交易就不行（交易中不能改類型）。"""
    if not listing.variants or not waits_for_deposit(listing):
        return False
    return not any(not t.legacy for t in await trade.open_trades_for_source(listing.thread_id))


def parse_balances(text: str, variants: Sequence[Variant]) -> dict[int, int]:
    """「改成定金＋尾款」表單的尾款：每行「編號. 名稱｜尾款」，編號照管理面板的順序（1 起）。每個品項都要有。"""
    found: dict[int, int] = {}
    for line in (text or "").splitlines():
        if not line.strip():
            continue
        match = _BALANCE_LINE.match(line)
        digits = match.group(2).replace(",", "").replace("，", "") if match else ""
        if match is None or not digits:   # 只打了逗號也算看不懂
            raise ShopError(f"「{line.strip()[:40]}」看不懂，每行寫成「1. 品項名稱｜尾款」，例「1. 標準版｜1300」。")
        number, amount = int(match.group(1)), int(digits)
        if not 1 <= number <= len(variants):
            raise ShopError(f"沒有第 {number} 個品項。")
        if not 1 <= amount <= PRICE_MAX:
            raise ShopError(f"第 {number} 個品項的尾款要是 1～{PRICE_MAX:,} 的整數。")
        found[variants[number - 1].key] = amount
    missing = [f"{n}. {v.name}" for n, v in enumerate(variants, start=1) if v.key not in found]
    if missing:
        raise ShopError("這幾個品項還沒填尾款：" + "、".join(missing)[:300])
    return found


def parse_balance_fields(values: Mapping[int, str], variants: Sequence[Variant]) -> dict[int, int]:
    """每個品項一格的尾款：{品項編號: 填的字}。只收數字（可以有千分位逗號）；每個品項都要有。
    表單打開後品項被改過（新增、刪除）就整張退回，免得尾款對到別的品項。"""
    if set(values) != {v.key for v in variants}:
        raise ShopError("表單打開之後品項有變動，請重新按「💰 改成定金＋尾款」再填一次。")
    found: dict[int, int] = {}
    for number, variant in enumerate(variants, start=1):
        text = (values[variant.key] or "").strip()
        digits = text.replace(",", "").replace("，", "")
        if not digits:
            raise ShopError(f"「{number}. {variant.name}」還沒填尾款。")
        try:
            amount = int(digits)   # 跟其他金額欄一樣：全形數字也收
        except ValueError:
            raise ShopError(f"「{number}. {variant.name}」的尾款「{text[:20]}」看不懂，只填數字，例 1300。") from None
        if not 1 <= amount <= PRICE_MAX:
            raise ShopError(f"「{number}. {variant.name}」的尾款要是 1～{PRICE_MAX:,} 的整數。")
        found[variant.key] = amount
    return found


async def convert(shop: "ShopService", listing_id: int, actor: discord.Member, cutoff_text: str,
                  balances: str | Mapping[int, str]) -> str:
    """整篇改成定金＋尾款：原本的價格當定金，每個品項填尾款、整篇一個收定金截止（已經截止的照樣截止）；
    改好後這篇上的舊交易接上新流程（品項換成定金＋尾款、補發交易進度，不 @ 人）。"""
    now = shop.now()
    moment = parse_cutoff(cutoff_text)
    if moment <= now:
        raise ShopError("收定金截止已經過了，請填之後的時間。")
    if moment > now + timedelta(days=round(365.25 * 5)):
        raise ShopError("截止時間太遠了，請檢查年份。")
    async with shop.lock(listing_id):
        listing = await shop.check_manager(listing_id, actor)
        if listing.closed:
            raise ShopError("這篇商品已經下架了。")
        if not await can_convert(shop.trade, listing):
            raise ShopError("這篇商品現在不能整篇改成定金＋尾款（只給標題寫【定金】、品項還不是定金＋尾款的商品；"
                            "上線後開的交易要先完成或取消）。")
        if isinstance(balances, str):
            amounts = parse_balances(balances, listing.variants)
        else:
            amounts = parse_balance_fields(balances, listing.variants)
        db = await shop.db()
        async with db.transaction():
            for variant in listing.variants:
                if variant.cutoff_done:
                    # 已經截止的照樣截止（不能因為改類型就重新開放收定金）
                    await db.update_variant(listing_id, variant.key, now=shop.stamp(), kind="deposit",
                                            balance=amounts[variant.key])
                else:
                    await db.update_variant(listing_id, variant.key, now=shop.stamp(), kind="deposit",
                                            balance=amounts[variant.key], cutoff=moment.isoformat(),
                                            cutoff_noticed=False, expected_at=None, delivery_started_at=None)
        await shop.refresh_listing(listing_id)
    adopted = await shop.adopt_legacy_on(listing_id)
    shop.cutoffs_changed.set()
    logger.info("上線銜接：整篇改成定金＋尾款 商品=%s by=%s 舊交易=%s", listing_id, actor.id, adopted)
    title = (await shop.load(listing_id)).title
    return (f"已把「{title}」改成定金＋尾款（{len(listing.variants)} 個品項，收定金到 {format_cutoff(moment)}），"
            f"補發了 {adopted} 個交易對話的交易進度。")


async def adopt_ready(shop: "ShopService") -> int:
    """上線前的舊交易，商品準備好了就接上新流程：標題不是【定金】的（匯入時），或已經改成定金＋尾款的
    （不管是按「💰 改成定金＋尾款」還是一個一個編輯品項改的）。一篇出錯不影響其他篇。回傳這次轉了幾筆。"""
    if not enabled():
        return 0
    db = await shop.db()
    adopted = 0
    for listing_id in sorted({row.source_id for row in await db.trades(status="open", source_kind="listing")
                              if row.legacy}):
        if await db.get_listing(listing_id) is None:
            continue
        try:
            if not waits_for_deposit(await shop.load(listing_id)):
                adopted += await shop.adopt_legacy_on(listing_id)
        except Exception:  # 邊界：一篇商品的舊交易，壞了下一輪再試
            logger.error("上線銜接：舊交易接上新流程失敗 商品=%s", listing_id, exc_info=True)
    return adopted
