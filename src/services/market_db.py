"""商品市集的資料庫（SQLite，`services/market.db`）：商品、品項、交易、交易品項、交易事件、週報紀錄的正本。

架構定位：服務層（`services/`），只依賴標準庫、aiosqlite 與基礎層（`sys_settings.paths`）；不 import discord。
  - 上層（誰呼叫）：功能層的商品與交易模組（`services.community` 裡的商品、交易、上線匯入、週報），
    以及每日備份；`discord_bot` 停機時呼叫 `close_shared_market_db`。
  - 下層（呼叫誰）：aiosqlite；共用連線的「只開一次、關了不再開」交給 `utils.shared_resource`。

介面：
  - `MarketDB(path)`：`connect()`／`close()`；`transaction()` 是寫入用的區段；各表的讀寫方法分段寫在類別裡。
  - `get_shared_market_db()`／`close_shared_market_db()`：全程式共用一條連線；關掉之後不再開新的。
  - `MarketDB.snapshot(target)`：把整個資料庫線上複製成一個新檔（SQLite backup API，寫入中也能做），做完檢查完整性。
  - `backup_daily(db, backup_dir, today=)`：每天一份 `market_YYYY-MM-DD.db`，只留最新 `BACKUP_KEEP` 份。
  - 列的資料類別：`ListingRow`、`VariantRow`、`TradeRow`、`TradeItemRow`、`TradeEventRow`。

規則：
  - 這裡是正本：Discord 上的商品貼文、選單、交易對話裡的訊息都從這裡畫；呼叫端先寫這裡、成功後才發 Discord。
  - 交易事件只增不改；品項在交易裡走到哪一步由功能層從事件算，這裡不存那種狀態。交易本身的
    open／completed／cancelled／ended 例外：週報、看板、加購沿用都要用它查。
  - 寫入只能在 `transaction()` 裡；讀取在區段外也行，會等正在寫的區段做完。共用一條連線，
    不排隊的話兩個協程的語句會交錯，混進同一個交易，讀的人也會看到寫到一半的資料。
  - 時間存 ISO 8601 字串（帶時區）；金額存整數，幣別在商品上。

例外與決策：
  - 用 SQLite、不用 Postgres：交易量很小，這個檔只有 bot 一個行程寫；Postgres 給 AI 功能用，維護時段負載重。
  - 跟 `sent_articles.db` 分開成兩個檔：轉發的去重資料與買賣紀錄各自備份、還原，互不影響。
  - 表結構版本記在 `meta.schema_version`；改結構時在 `_MIGRATIONS` 尾端加一段，已套過的不再套。
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator, Iterable, Mapping, Optional, Sequence

import aiosqlite

from sys_settings.paths import MARKET_DB
from utils.safe_write import prune_backups
from utils.shared_resource import SharedResource

logger = logging.getLogger(__name__)

DELIVERY_KINDS = ("digital", "physical")
VARIANT_KINDS = ("instant", "preorder", "deposit")
TRADE_SOURCES = ("listing", "forum")
TRADE_STATUSES = ("open", "completed", "cancelled", "ended")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- 一篇商品（商品論壇的一則貼文；id＝貼文所在的論壇 thread id）
CREATE TABLE IF NOT EXISTS listings (
    id INTEGER PRIMARY KEY,
    owner_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    unit TEXT NOT NULL,
    delivery TEXT NOT NULL CHECK (delivery IN ('digital', 'physical')),
    image TEXT,
    closed INTEGER NOT NULL DEFAULT 0,
    next_key INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    -- 貼文標題與鎖定要跟著資料庫（改標題、下架）：要改一次 post_wanted 加一，背景改好了把 post_done 記成那個數。
    -- post_wanted 比 post_done 大＝還沒改好（改名撞到限速、做到一半重啟），排程照資料庫補；同時改兩次時照最新的改
    post_wanted INTEGER NOT NULL DEFAULT 0,
    post_done INTEGER NOT NULL DEFAULT 0
);

-- 一個品項；key 在同一篇商品裡只增不減，刪掉的不重用（舊訂單才不會對到新的品項）
CREATE TABLE IF NOT EXISTS variants (
    listing_id INTEGER NOT NULL REFERENCES listings(id),
    key INTEGER NOT NULL,
    name TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('instant', 'preorder', 'deposit')),
    price INTEGER NOT NULL,
    balance INTEGER,
    limit_qty INTEGER,
    sold_before INTEGER NOT NULL DEFAULT 0,
    cutoff TEXT,
    cutoff_done INTEGER NOT NULL DEFAULT 0,
    expected_at TEXT,
    delays INTEGER NOT NULL DEFAULT 0,
    balance_started_at TEXT,
    -- 一次付清的預購截止後延期、貨提早到了按「開始交貨」的時刻（之後又延期就清掉）：補發通知時分得出
    -- 這次是「貨提早到了」還是一般的截止通知（預計交貨日過了不代表貨到了）
    delivery_started_at TEXT,
    -- 截止（或開始交貨）的通知發完了沒、延期通知發到第幾次：先寫狀態再逐一通知，做到一半重啟時照這兩欄補發
    cutoff_noticed INTEGER NOT NULL DEFAULT 0,
    delays_noticed INTEGER NOT NULL DEFAULT 0,
    deleted INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (listing_id, key)
);

-- 一個交易對話（id＝購物車裡的私人 thread id）；source 是商品貼文或自由市場的需求貼文
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY,
    source_kind TEXT NOT NULL CHECK (source_kind IN ('listing', 'forum')),
    source_id INTEGER NOT NULL,
    requester_id INTEGER NOT NULL,
    supplier_id INTEGER NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('open', 'completed', 'cancelled', 'ended')),
    legacy INTEGER NOT NULL DEFAULT 0,
    opened_at TEXT NOT NULL,
    closed_at TEXT,
    progress_message_id INTEGER,
    -- 那張交易進度是照到哪一筆事件畫的：之後有改變狀態的事件，卡片就過期了、要重畫
    progress_event_id INTEGER,
    -- 結束後 Discord 那邊收尾（留底、結束訊息、收按鈕、改名鎖定、私訊）做完了沒：做到一半重啟時由排程補做
    wrapped_up INTEGER NOT NULL DEFAULT 0,
    -- 交易對話裡最後一則真人訊息的時間（有人講話時記；看板、週報算「幾天沒動靜」不用去翻對話）
    last_chat_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_trades_supplier ON trades(supplier_id, status);
CREATE INDEX IF NOT EXISTS idx_trades_source ON trades(source_id, status);

-- 交易裡的一個品項，每次下單（含加購）各一列；金額是下單當時的
CREATE TABLE IF NOT EXISTS trade_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id INTEGER NOT NULL REFERENCES trades(id),
    order_event_id INTEGER NOT NULL,
    variant_key INTEGER NOT NULL,
    name TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('instant', 'preorder', 'deposit')),
    qty INTEGER NOT NULL CHECK (qty > 0),
    unit_price INTEGER NOT NULL,
    unit_balance INTEGER,
    -- 取消時還回商品的份數（沒交付、沒寄出的才還）
    returned INTEGER NOT NULL DEFAULT 0 CHECK (returned >= 0 AND returned <= qty)
);
CREATE INDEX IF NOT EXISTS idx_trade_items_trade ON trade_items(trade_id);

-- 交易裡發生的一件事，只增不改；items 是 {品項編號: 份數} 的 JSON
CREATE TABLE IF NOT EXISTS trade_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id INTEGER NOT NULL REFERENCES trades(id),
    kind TEXT NOT NULL,
    items TEXT,
    amount INTEGER,
    actor_id INTEGER,
    source TEXT,
    reference TEXT,
    message_id INTEGER,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_trade_events_trade ON trade_events(trade_id, id);

-- 每週報告：誰、哪一週、送到沒
CREATE TABLE IF NOT EXISTS weekly_reports (
    week TEXT NOT NULL,
    recipient_id INTEGER NOT NULL,
    sent_at TEXT,
    error TEXT,
    PRIMARY KEY (week, recipient_id)
);
"""

#: 表結構的版本：第 n 個版本＝`_SCHEMA`（第 0 版）之後依序套過前 n 段。上線之後 `_SCHEMA` 與已有的段都不改，
#: 新的改動只能接在尾端：新建的資料庫也是從第 0 版一段段套上來，兩條路才會得到一樣的結構。
_MIGRATIONS: tuple[tuple[str, ...], ...] = ()
SCHEMA_VERSION = len(_MIGRATIONS)


# ── 列的資料類別 ──

@dataclass(frozen=True)
class ListingRow:
    id: int
    owner_id: int
    title: str
    description: str
    unit: str
    delivery: str
    image: Optional[str]
    closed: bool
    next_key: int
    created_at: str
    updated_at: str
    post_wanted: int = 0
    post_done: int = 0

    @property
    def post_pending(self) -> bool:
        return self.post_wanted > self.post_done


@dataclass(frozen=True)
class VariantRow:
    listing_id: int
    key: int
    name: str
    kind: str
    price: int
    balance: Optional[int]
    limit_qty: Optional[int]
    sold_before: int
    cutoff: Optional[str]
    cutoff_done: bool
    expected_at: Optional[str]
    delays: int
    balance_started_at: Optional[str]
    deleted: bool
    created_at: str
    updated_at: str
    cutoff_noticed: bool = False
    delays_noticed: int = 0
    delivery_started_at: Optional[str] = None


@dataclass(frozen=True)
class TradeRow:
    id: int
    source_kind: str
    source_id: int
    requester_id: int
    supplier_id: int
    status: str
    legacy: bool
    opened_at: str
    closed_at: Optional[str]
    progress_message_id: Optional[int]
    progress_event_id: Optional[int] = None
    wrapped_up: bool = False
    last_chat_at: Optional[str] = None


@dataclass(frozen=True)
class TradeItemRow:
    id: int
    trade_id: int
    order_event_id: int
    variant_key: int
    name: str
    kind: str
    qty: int
    unit_price: int
    unit_balance: Optional[int]
    returned: int                       # 取消時還回商品的份數


@dataclass(frozen=True)
class TradeEventRow:
    id: int
    trade_id: int
    kind: str
    items: dict[int, int]
    amount: Optional[int]
    actor_id: Optional[int]
    source: Optional[str]
    reference: Optional[str]
    message_id: Optional[int]
    created_at: str


def _listing(row) -> ListingRow:
    return ListingRow(row["id"], row["owner_id"], row["title"], row["description"], row["unit"], row["delivery"],
                      row["image"], bool(row["closed"]), row["next_key"], row["created_at"], row["updated_at"],
                      row["post_wanted"], row["post_done"])


def _variant(row) -> VariantRow:
    return VariantRow(row["listing_id"], row["key"], row["name"], row["kind"], row["price"], row["balance"],
                      row["limit_qty"], row["sold_before"], row["cutoff"], bool(row["cutoff_done"]),
                      row["expected_at"], row["delays"], row["balance_started_at"], bool(row["deleted"]),
                      row["created_at"], row["updated_at"], bool(row["cutoff_noticed"]), row["delays_noticed"],
                      row["delivery_started_at"])


def _trade(row) -> TradeRow:
    return TradeRow(row["id"], row["source_kind"], row["source_id"], row["requester_id"], row["supplier_id"],
                    row["status"], bool(row["legacy"]), row["opened_at"], row["closed_at"],
                    row["progress_message_id"], row["progress_event_id"], bool(row["wrapped_up"]),
                    row["last_chat_at"])


def _item(row) -> TradeItemRow:
    return TradeItemRow(row["id"], row["trade_id"], row["order_event_id"], row["variant_key"], row["name"],
                        row["kind"], row["qty"], row["unit_price"], row["unit_balance"], row["returned"])


def _event(row) -> TradeEventRow:
    items = {int(k): int(v) for k, v in json.loads(row["items"]).items()} if row["items"] else {}
    return TradeEventRow(row["id"], row["trade_id"], row["kind"], items, row["amount"], row["actor_id"],
                         row["source"], row["reference"], row["message_id"], row["created_at"])


def _items_json(items: Optional[Mapping[int, int]]) -> Optional[str]:
    return json.dumps({str(k): int(v) for k, v in items.items()}, sort_keys=True) if items else None


#: 可以改的欄位（白名單）：欄位名會直接拼進 SQL，不能讓呼叫端傳任意字串
_LISTING_FIELDS = frozenset({"title", "description", "unit", "delivery", "image", "closed"})
_VARIANT_FIELDS = frozenset({"name", "kind", "price", "balance", "limit_qty", "cutoff", "cutoff_done",
                             "expected_at", "delays", "balance_started_at", "deleted", "cutoff_noticed",
                             "delays_noticed", "delivery_started_at"})


class MarketDB:
    """商品市集資料庫的一條連線。寫入一律在 `transaction()` 裡。"""

    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path is not None else MARKET_DB
        self._db: Optional[aiosqlite.Connection] = None
        self._lock = asyncio.Lock()
        self._owner: Optional[asyncio.Task] = None

    # ── 連線 ──

    async def connect(self) -> None:
        if self._db is not None:
            return
        db = await aiosqlite.connect(str(self.path), isolation_level=None)
        ready = False
        try:
            db.row_factory = aiosqlite.Row
            # WAL：備份與讀取不擋寫入；busy_timeout：備份或外部工具開著時等一下而不是馬上失敗
            await db.execute("PRAGMA journal_mode=WAL")
            await db.execute("PRAGMA busy_timeout=5000")
            await db.execute("PRAGMA foreign_keys=ON")
            await db.executescript(_SCHEMA)
            await self._migrate(db)
            ready = True
        finally:
            if not ready:
                await db.close()  # 連線背後有一條執行緒，不關的話行程退不出去
        self._db = db
        logger.info("市集資料庫已連線：%s（結構版本 %s）", self.path, SCHEMA_VERSION)

    async def _migrate(self, db: aiosqlite.Connection) -> None:
        async with db.execute("SELECT value FROM meta WHERE key='schema_version'") as cursor:
            row = await cursor.fetchone()
        current = int(row["value"]) if row else 0
        if current > SCHEMA_VERSION:
            # 資料庫比程式新（退回舊版程式）：照舊程式的認知去寫會弄壞新欄位，寧可起不來
            raise RuntimeError(f"市集資料庫的結構版本 {current} 比程式認得的 {SCHEMA_VERSION} 新，請用新版程式")
        for version in range(current, SCHEMA_VERSION):
            await db.execute("BEGIN IMMEDIATE")
            committed = False
            try:
                for statement in _MIGRATIONS[version]:
                    await db.execute(statement)
                await db.execute("INSERT OR REPLACE INTO meta(key, value) VALUES ('schema_version', ?)",
                                 (str(version + 1),))
                await db.execute("COMMIT")
                committed = True
            finally:
                if not committed:  # 這一段沒套完就整段撤回，版本號也不前進
                    await db.execute("ROLLBACK")
        if row is None:
            await db.execute("INSERT OR IGNORE INTO meta(key, value) VALUES ('schema_version', ?)",
                             (str(SCHEMA_VERSION),))

    async def close(self) -> None:
        if self._db is not None:
            async with self._lock:
                db, self._db = self._db, None
                await db.close()

    @property
    def db(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("市集資料庫尚未連線，請先呼叫 connect()")
        return self._db

    def _in_transaction(self) -> bool:
        return self._owner is not None and self._owner is asyncio.current_task()

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator["MarketDB"]:
        """寫入區段：同一時間只有一段；區段裡丟例外就整段撤回。區段裡不能再開區段。"""
        if self._in_transaction():
            raise RuntimeError("市集資料庫的寫入區段不能巢狀")
        async with self._lock:
            self._owner = asyncio.current_task()
            committed = False
            try:
                await self.db.execute("BEGIN IMMEDIATE")
                yield self
                await self.db.execute("COMMIT")
                committed = True
            finally:
                try:
                    if not committed and self.db.in_transaction:
                        await self.db.execute("ROLLBACK")  # 區段裡丟例外（含取消）：整段撤回，例外照樣往外走
                finally:
                    self._owner = None

    @asynccontextmanager
    async def _reading(self) -> AsyncIterator[None]:
        if self._in_transaction():
            yield
            return
        async with self._lock:
            yield

    async def _all(self, sql: str, params: Sequence = ()) -> list:
        async with self._reading():
            async with self.db.execute(sql, params) as cursor:
                return list(await cursor.fetchall())

    async def _one(self, sql: str, params: Sequence = ()):
        rows = await self._all(sql, params)
        return rows[0] if rows else None

    async def _write(self, sql: str, params: Sequence = ()) -> aiosqlite.Cursor:
        if not self._in_transaction():
            raise RuntimeError("市集資料庫的寫入要在 transaction() 裡")
        return await self.db.execute(sql, params)

    async def snapshot(self, target: Path) -> None:
        """把整個資料庫複製成 target（新檔；已存在就覆蓋），做完檢查完整性，沒過就刪掉並丟 RuntimeError。

        拿著鎖做：同一條連線上不會有寫到一半的區段，複本是某一瞬間的完整內容。"""
        target = Path(target)
        await asyncio.to_thread(target.unlink, missing_ok=True)
        async with self._reading():
            async with aiosqlite.connect(str(target)) as copy:
                await self.db.backup(copy)
                result = await _integrity_check(copy)
        if result != ["ok"]:
            await asyncio.to_thread(target.unlink, missing_ok=True)
            raise RuntimeError(f"市集資料庫備份的完整性檢查沒過：{result[:3]}")

    # ── meta ──

    async def get_meta(self, key: str) -> Optional[str]:
        row = await self._one("SELECT value FROM meta WHERE key=?", (key,))
        return row["value"] if row else None

    async def set_meta(self, key: str, value: str) -> None:
        await self._write("INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)", (key, value))

    # ── 商品 ──

    async def insert_listing(self, *, id: int, owner_id: int, title: str, description: str, unit: str,
                             delivery: str, image: Optional[str], now: str, closed: bool = False,
                             next_key: int = 1) -> None:
        if delivery not in DELIVERY_KINDS:
            raise ValueError(f"交付方式只能是 {DELIVERY_KINDS}：{delivery!r}")
        await self._write(
            "INSERT INTO listings(id, owner_id, title, description, unit, delivery, image, closed, next_key,"
            " created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (id, owner_id, title, description, unit, delivery, image, int(closed), next_key, now, now))

    async def get_listing(self, listing_id: int) -> Optional[ListingRow]:
        row = await self._one("SELECT * FROM listings WHERE id=?", (listing_id,))
        return _listing(row) if row else None

    async def listings(self, *, include_closed: bool = True) -> list[ListingRow]:
        sql = "SELECT * FROM listings" + ("" if include_closed else " WHERE closed=0") + " ORDER BY id"
        return [_listing(row) for row in await self._all(sql)]

    async def update_listing(self, listing_id: int, *, now: str, **fields) -> None:
        unknown = set(fields) - _LISTING_FIELDS
        if unknown:
            raise ValueError(f"商品沒有這些可改的欄位：{sorted(unknown)}")
        if "delivery" in fields and fields["delivery"] not in DELIVERY_KINDS:
            raise ValueError(f"交付方式只能是 {DELIVERY_KINDS}：{fields['delivery']!r}")
        if "closed" in fields:
            fields["closed"] = int(fields["closed"])
        assignments = ", ".join(f"{name}=?" for name in fields)
        await self._write(f"UPDATE listings SET {assignments}, updated_at=? WHERE id=?",
                          (*fields.values(), now, listing_id))

    async def want_post_sync(self, listing_id: int) -> None:
        """標題或下架改了：貼文要跟著改（背景做，見建表說明）。"""
        await self._write("UPDATE listings SET post_wanted=post_wanted+1 WHERE id=?", (listing_id,))

    async def post_synced(self, listing_id: int, version: int) -> None:
        """貼文已經照第 version 次的要求改好了（之後又有新的要求就還是沒改好）。"""
        await self._write("UPDATE listings SET post_done=? WHERE id=? AND post_done<?", (version, listing_id, version))

    # ── 品項 ──

    async def insert_variant(self, listing_id: int, *, name: str, kind: str, price: int, now: str,
                             balance: Optional[int] = None, limit_qty: Optional[int] = None,
                             cutoff: Optional[str] = None, sold_before: int = 0, key: Optional[int] = None,
                             cutoff_done: bool = False, deleted: bool = False, cutoff_noticed: bool = False) -> int:
        """新增品項並回傳它的編號。key 只給上線匯入用（沿用 Discord 上的編號）；平常照商品的 next_key 發。"""
        if kind not in VARIANT_KINDS:
            raise ValueError(f"品項類型只能是 {VARIANT_KINDS}：{kind!r}")
        listing = await self._one("SELECT next_key FROM listings WHERE id=?", (listing_id,))
        if listing is None:
            raise ValueError(f"沒有這篇商品：{listing_id}")
        new_key = listing["next_key"] if key is None else key
        await self._write(
            "INSERT INTO variants(listing_id, key, name, kind, price, balance, limit_qty, sold_before, cutoff,"
            " cutoff_done, deleted, cutoff_noticed, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (listing_id, new_key, name, kind, price, balance, limit_qty, sold_before, cutoff, int(cutoff_done),
             int(deleted), int(cutoff_noticed), now, now))
        await self._write("UPDATE listings SET next_key=MAX(next_key, ?) WHERE id=?", (new_key + 1, listing_id))
        return new_key

    async def variants(self, listing_id: int, *, include_deleted: bool = False) -> list[VariantRow]:
        sql = "SELECT * FROM variants WHERE listing_id=?" + ("" if include_deleted else " AND deleted=0")
        return [_variant(row) for row in await self._all(sql + " ORDER BY key", (listing_id,))]

    async def get_variant(self, listing_id: int, key: int) -> Optional[VariantRow]:
        row = await self._one("SELECT * FROM variants WHERE listing_id=? AND key=?", (listing_id, key))
        return _variant(row) if row else None

    async def update_variant(self, listing_id: int, key: int, *, now: str, **fields) -> None:
        unknown = set(fields) - _VARIANT_FIELDS
        if unknown:
            raise ValueError(f"品項沒有這些可改的欄位：{sorted(unknown)}")
        if "kind" in fields and fields["kind"] not in VARIANT_KINDS:
            raise ValueError(f"品項類型只能是 {VARIANT_KINDS}：{fields['kind']!r}")
        for flag in ("cutoff_done", "deleted", "cutoff_noticed"):
            if flag in fields:
                fields[flag] = int(fields[flag])
        assignments = ", ".join(f"{name}=?" for name in fields)
        await self._write(f"UPDATE variants SET {assignments}, updated_at=? WHERE listing_id=? AND key=?",
                          (*fields.values(), now, listing_id, key))

    async def taken(self, listing_id: int) -> dict[int, int]:
        """每個品項已下單的份數：上線前賣掉的＋還算數的交易品項（取消時還回去的不算）。"""
        rows = await self._all(
            "SELECT v.key AS key, v.sold_before + COALESCE(SUM(i.qty - i.returned), 0) AS n"
            " FROM variants v"
            " LEFT JOIN trades t ON t.source_kind='listing' AND t.source_id=v.listing_id"
            " LEFT JOIN trade_items i ON i.trade_id=t.id AND i.variant_key=v.key"
            " WHERE v.listing_id=? GROUP BY v.key", (listing_id,))
        return {row["key"]: row["n"] for row in rows}

    # ── 交易 ──

    async def insert_trade(self, *, id: int, source_kind: str, source_id: int, requester_id: int,
                           supplier_id: int, now: str, legacy: bool = False) -> None:
        if source_kind not in TRADE_SOURCES:
            raise ValueError(f"交易來源只能是 {TRADE_SOURCES}：{source_kind!r}")
        await self._write(
            "INSERT INTO trades(id, source_kind, source_id, requester_id, supplier_id, status, legacy, opened_at)"
            " VALUES (?, ?, ?, ?, ?, 'open', ?, ?)",
            (id, source_kind, source_id, requester_id, supplier_id, int(legacy), now))

    async def get_trade(self, trade_id: int) -> Optional[TradeRow]:
        row = await self._one("SELECT * FROM trades WHERE id=?", (trade_id,))
        return _trade(row) if row else None

    async def trades(self, *, status: Optional[str] = None, supplier_id: Optional[int] = None,
                     source_id: Optional[int] = None, requester_id: Optional[int] = None,
                     source_kind: Optional[str] = None) -> list[TradeRow]:
        clauses, params = [], []
        for column, value in (("status", status), ("supplier_id", supplier_id), ("source_id", source_id),
                              ("requester_id", requester_id), ("source_kind", source_kind)):
            if value is not None:
                clauses.append(f"{column}=?")
                params.append(value)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        return [_trade(row) for row in await self._all(f"SELECT * FROM trades{where} ORDER BY opened_at, id", params)]

    async def set_trade_status(self, trade_id: int, status: str, *, now: str) -> None:
        if status not in TRADE_STATUSES:
            raise ValueError(f"交易狀態只能是 {TRADE_STATUSES}：{status!r}")
        closed_at = None if status == "open" else now
        await self._write("UPDATE trades SET status=?, closed_at=? WHERE id=?", (status, closed_at, trade_id))

    async def unwrapped_trades(self) -> list[TradeRow]:
        """已經結束、Discord 那邊還沒收尾完的交易。"""
        return [_trade(row) for row in await self._all(
            "SELECT * FROM trades WHERE status != 'open' AND wrapped_up=0 ORDER BY closed_at, id")]

    async def set_wrapped_up(self, trade_id: int) -> None:
        await self._write("UPDATE trades SET wrapped_up=1 WHERE id=?", (trade_id,))

    async def note_chat(self, trade_id: int, at: str) -> None:
        """交易對話裡有人講話：記下時間（只往後記；不是進行中的交易就不動）。"""
        await self._write("UPDATE trades SET last_chat_at=? WHERE id=? AND status='open'"
                          " AND (last_chat_at IS NULL OR last_chat_at < ?)", (at, trade_id, at))

    async def set_progress_message(self, trade_id: int, message_id: Optional[int],
                                   event_id: Optional[int] = None) -> None:
        """記下目前那張交易進度（訊息）與它照到哪一筆事件畫的。"""
        await self._write("UPDATE trades SET progress_message_id=?, progress_event_id=? WHERE id=?",
                          (message_id, event_id, trade_id))

    # ── 交易品項 ──

    async def insert_items(self, trade_id: int, order_event_id: int, items: Iterable[Mapping]) -> None:
        """一次下單的品項：每筆要有 variant_key、name、kind、qty、unit_price，定金＋尾款再加 unit_balance。"""
        for item in items:
            if item["kind"] not in VARIANT_KINDS:
                raise ValueError(f"品項類型只能是 {VARIANT_KINDS}：{item['kind']!r}")
            await self._write(
                "INSERT INTO trade_items(trade_id, order_event_id, variant_key, name, kind, qty, unit_price,"
                " unit_balance) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (trade_id, order_event_id, item["variant_key"], item["name"], item["kind"], item["qty"],
                 item["unit_price"], item.get("unit_balance")))

    async def set_item_terms(self, trade_id: int, variant_key: int, *, kind: str,
                             unit_balance: Optional[int]) -> None:
        """改一筆交易裡某個品項的類型與尾款（上線前的舊交易接上新流程時用；金額照下單當時的不動）。"""
        if kind not in VARIANT_KINDS:
            raise ValueError(f"品項類型只能是 {VARIANT_KINDS}：{kind!r}")
        await self._write("UPDATE trade_items SET kind=?, unit_balance=? WHERE trade_id=? AND variant_key=?",
                          (kind, unit_balance, trade_id, variant_key))

    async def adopt_legacy_trade(self, trade_id: int) -> None:
        """上線前的舊交易改成新流程（之後照交易進度走、會提醒）。"""
        await self._write("UPDATE trades SET legacy=0 WHERE id=?", (trade_id,))

    async def items(self, trade_id: int) -> list[TradeItemRow]:
        return [_item(row) for row in await self._all(
            "SELECT * FROM trade_items WHERE trade_id=? ORDER BY id", (trade_id,))]

    async def return_items(self, trade_id: int, picks: Mapping[int, int]) -> None:
        """取消時把 {品項編號: 份數} 還回商品（只傳沒交付、沒寄出的份數）。從最後下單的那列開始還：
        加購的份數比較晚、通常還沒交付；份數超過還沒還的部分就只還到那裡。"""
        for key, qty in picks.items():
            left = int(qty)
            rows = await self._all("SELECT id, qty, returned FROM trade_items WHERE trade_id=? AND variant_key=?"
                                   " ORDER BY id DESC", (trade_id, key))
            for row in rows:
                take = min(left, row["qty"] - row["returned"])
                if take > 0:
                    await self._write("UPDATE trade_items SET returned=returned+? WHERE id=?", (take, row["id"]))
                    left -= take

    # ── 交易事件 ──

    async def add_event(self, trade_id: int, kind: str, *, now: str, items: Optional[Mapping[int, int]] = None,
                        amount: Optional[int] = None, actor_id: Optional[int] = None, source: Optional[str] = None,
                        reference: Optional[str] = None, message_id: Optional[int] = None) -> int:
        cursor = await self._write(
            "INSERT INTO trade_events(trade_id, kind, items, amount, actor_id, source, reference, message_id,"
            " created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (trade_id, kind, _items_json(items), amount, actor_id, source, reference, message_id, now))
        return cursor.lastrowid

    async def set_event_message(self, event_id: int, message_id: int) -> None:
        """補上事件對應的 Discord 訊息（先寫事件、發出訊息後才知道 id）。只填空的，不改已經有的。"""
        await self._write("UPDATE trade_events SET message_id=? WHERE id=? AND message_id IS NULL",
                          (message_id, event_id))

    async def events(self, trade_id: int, *, kinds: Optional[Iterable[str]] = None) -> list[TradeEventRow]:
        sql, params = "SELECT * FROM trade_events WHERE trade_id=?", [trade_id]
        if kinds is not None:
            kinds = list(kinds)
            sql += f" AND kind IN ({', '.join('?' for _ in kinds)})"
            params += kinds
        return [_event(row) for row in await self._all(sql + " ORDER BY id", params)]

    # ── 週報 ──

    async def weekly_report(self, week: str, recipient_id: int) -> Optional[tuple[Optional[str], Optional[str]]]:
        """(送出時間, 沒送到的原因)；沒有紀錄回 None。"""
        row = await self._one("SELECT sent_at, error FROM weekly_reports WHERE week=? AND recipient_id=?",
                              (week, recipient_id))
        return (row["sent_at"], row["error"]) if row else None

    async def record_weekly_report(self, week: str, recipient_id: int, *, sent_at: Optional[str] = None,
                                   error: Optional[str] = None) -> None:
        await self._write("INSERT OR REPLACE INTO weekly_reports(week, recipient_id, sent_at, error) VALUES (?, ?, ?, ?)",
                          (week, recipient_id, sent_at, error))


async def _integrity_check(connection: aiosqlite.Connection) -> list[str]:
    """SQLite 的完整性檢查；沒問題時是 ["ok"]。"""
    async with connection.execute("PRAGMA integrity_check") as cursor:
        return [row[0] for row in await cursor.fetchall()]


#: 每日備份保留幾份（一天一份，壞一份只少一天）
BACKUP_KEEP = 14
_BACKUP_GLOB = "market_????-??-??.db"


async def backup_daily(db: MarketDB, backup_dir: Path, *, today: str, keep: int = BACKUP_KEEP) -> Optional[Path]:
    """每天一份備份 `market_<today>.db`（today 是 YYYY-MM-DD）：今天已經有就不做，回傳 None。

    先寫成同一個資料夾裡的暫存檔、檢查過完整性才換名（換名是原子的，正式檔名不會是寫到一半的檔；
    暫存檔要跟正式檔在同一個掛載點，換名才不會失敗），再只留最新的 keep 份。"""
    backup_dir = Path(backup_dir)
    target = backup_dir / f"market_{today}.db"
    await asyncio.to_thread(backup_dir.mkdir, parents=True, exist_ok=True)
    if await asyncio.to_thread(target.exists):
        return None
    tmp = backup_dir / f".market_{today}.db.tmp"
    done = False
    try:
        await db.snapshot(tmp)
        await asyncio.to_thread(os.replace, tmp, target)
        done = True
    finally:
        if not done:
            await asyncio.to_thread(tmp.unlink, missing_ok=True)
    removed = await asyncio.to_thread(prune_backups, backup_dir, _BACKUP_GLOB, keep)
    logger.info("市集資料庫已備份：%s（刪掉舊備份 %s 份）", target, len(removed))
    return target


async def _open_shared() -> MarketDB:
    db = MarketDB(MARKET_DB)
    await db.connect()
    return db


async def _close_shared(db: MarketDB) -> None:
    await db.close()


_shared = SharedResource("市集資料庫", _open_shared, _close_shared)


async def get_shared_market_db() -> MarketDB:
    """全程式共用的市集資料庫連線；停機關掉之後丟 RuntimeError。"""
    return await _shared.get()


async def close_shared_market_db() -> None:
    """停機時關掉共用連線；之後不再開新的（理由見 `utils.shared_resource`）。"""
    await _shared.close()
