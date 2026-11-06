"""商品市集資料庫（services.market_db）：商品、品項、交易、交易品項、事件、週報紀錄的存取。

守的底線：
  1. 寫入只能在 transaction() 裡；區段裡出錯整段撤回；區段不能巢狀。
  2. 同一條連線上兩個協程同時寫會排隊：一段做完另一段才開始，讀的人也看不到寫到一半的資料。
  3. 品項編號只增不減：刪掉的不重用；上線匯入時指定的編號會把下一個編號往後推。
  4. 已下單份數＝上線前賣掉的＋交易品項，取消時還回去的不算。
  5. 事件的品項份數（{編號: 份數}）存進去讀得回來；補訊息 id 只填空的，不改已經有的。
  6. 可改的欄位有白名單（欄位名會拼進 SQL）；交付方式、品項類型、交易狀態只收認得的值。
  7. 資料庫的結構版本比程式新（退回舊版程式）就拒絕連線，免得照舊認知寫壞新欄位。
  8. snapshot 複製出來的是完整、可以直接開的資料庫。
  9. 共用連線關掉之後不再開新的（停機時不留沒人關的連線）。
"""

import asyncio
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
SRC_DIR = HERE.parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from services import market_db  # noqa: E402
from services.market_db import MarketDB  # noqa: E402

NOW = "2026-11-06T12:00:00+08:00"
LATER = "2026-11-07T12:00:00+08:00"


class MarketDBTestCase(unittest.TestCase):

    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.path = Path(self._dir.name) / "market.db"

    def tearDown(self):
        self._dir.cleanup()

    def run_db(self, body):
        """開一條新連線跑 body(db)，跑完關掉。"""
        async def main():
            db = MarketDB(self.path)
            await db.connect()
            try:
                return await body(db)
            finally:
                await db.close()
        return asyncio.run(main())

    @staticmethod
    async def add_listing(db, listing_id=500, **overrides):
        fields = dict(id=listing_id, owner_id=21, title="座姿玩偶", description="", unit="NT$",
                      delivery="physical", image=None, now=NOW)
        fields.update(overrides)
        async with db.transaction():
            await db.insert_listing(**fields)


class TransactionTests(MarketDBTestCase):

    def test_writes_need_a_transaction(self):
        async def body(db):
            with self.assertRaises(RuntimeError):
                await db.set_meta("x", "1")
            async with db.transaction():
                await db.set_meta("x", "1")
            return await db.get_meta("x")

        self.assertEqual(self.run_db(body), "1")

    def test_error_rolls_back_the_whole_block(self):
        async def body(db):
            with self.assertRaises(ValueError):
                async with db.transaction():
                    await db.set_meta("a", "1")
                    await db.insert_listing(id=1, owner_id=2, title="t", description="", unit="NT$",
                                            delivery="空運", image=None, now=NOW)
            return await db.get_meta("a"), await db.get_listing(1)

        self.assertEqual(self.run_db(body), (None, None))

    def test_no_nested_blocks(self):
        async def body(db):
            async with db.transaction():
                with self.assertRaises(RuntimeError):
                    async with db.transaction():
                        pass
                await db.set_meta("ok", "1")
            return await db.get_meta("ok")

        self.assertEqual(self.run_db(body), "1")

    def test_concurrent_blocks_queue_and_readers_see_whole_blocks(self):
        async def body(db):
            halfway = asyncio.Event()
            order = []

            async def writer(name, signal=None):
                async with db.transaction():
                    order.append(f"{name} 開始")
                    await db.set_meta(f"{name}:1", "x")
                    if signal is not None:
                        signal.set()  # 寫到一半：讓讀的人在這時候去讀
                    await asyncio.sleep(0.05)
                    await db.set_meta(f"{name}:2", "x")
                    order.append(f"{name} 結束")

            async def reader():
                await halfway.wait()
                return await db.get_meta("a:1"), await db.get_meta("a:2")

            _, seen, _ = await asyncio.gather(writer("a", halfway), reader(), writer("b"))
            return order, seen, [await db.get_meta(k) for k in ("a:1", "a:2", "b:1", "b:2")]

        order, seen, values = self.run_db(body)
        self.assertEqual(values, ["x"] * 4)
        self.assertEqual(order, ["a 開始", "a 結束", "b 開始", "b 結束"])  # 兩段沒有交錯
        self.assertEqual(seen, ("x", "x"))  # 讀的人等 a 整段寫完才讀，不會只看到 a:1


class ListingAndVariantTests(MarketDBTestCase):

    def test_variant_keys_never_reused(self):
        async def body(db):
            await self.add_listing(db)
            async with db.transaction():
                first = await db.insert_variant(500, name="玩偶A", kind="deposit", price=500, balance=1300,
                                                cutoff="2026-11-30T23:59:00+08:00", now=NOW)
                second = await db.insert_variant(500, name="玩偶B", kind="instant", price=800, now=NOW)
                await db.update_variant(500, second, deleted=True, now=LATER)
                third = await db.insert_variant(500, name="吊飾C", kind="preorder", price=200, now=NOW)
            return first, second, third, [v.key for v in await db.variants(500)], \
                [v.key for v in await db.variants(500, include_deleted=True)]

        self.assertEqual(self.run_db(body), (1, 2, 3, [1, 3], [1, 2, 3]))

    def test_imported_next_key_is_kept_even_above_existing_keys(self):
        """Discord 上的舊商品真的刪過品項：記下的下一個編號比現有最大值大，新品項要照它發，不能撿回刪掉的編號。"""
        async def body(db):
            await self.add_listing(db, next_key=10)
            async with db.transaction():
                await db.insert_variant(500, key=3, name="還在的品項", kind="instant", price=30, now=NOW)
                fresh = await db.insert_variant(500, name="新品項", kind="instant", price=30, now=NOW)
            return fresh

        self.assertEqual(self.run_db(body), 10)

    def test_imported_keys_push_the_next_key(self):
        async def body(db):
            await self.add_listing(db)
            async with db.transaction():
                await db.insert_variant(500, key=7, name="舊品項", kind="instant", price=30, sold_before=4, now=NOW)
                fresh = await db.insert_variant(500, name="新品項", kind="instant", price=30, now=NOW)
            return fresh, (await db.get_listing(500)).next_key

        self.assertEqual(self.run_db(body), (8, 9))

    def test_updates_only_known_fields_and_values(self):
        async def body(db):
            await self.add_listing(db)
            async with db.transaction():
                key = await db.insert_variant(500, name="玩偶A", kind="instant", price=500, now=NOW)
                await db.update_variant(500, key, name="玩偶A・漂泊者", price=600, now=LATER)
                await db.update_listing(500, title="座姿玩偶 第一彈", delivery="digital", now=LATER)
            for bad in (dict(owner_id=1), dict(delivery="空運")):
                with self.subTest(bad=bad), self.assertRaises(ValueError):
                    async with db.transaction():
                        await db.update_listing(500, now=LATER, **bad)
            for bad in (dict(sold_before=9), dict(kind="團購")):
                with self.subTest(bad=bad), self.assertRaises(ValueError):
                    async with db.transaction():
                        await db.update_variant(500, key, now=LATER, **bad)
            variant, listing = await db.get_variant(500, key), await db.get_listing(500)
            return variant.name, variant.price, variant.updated_at, listing.title, listing.delivery

        self.assertEqual(self.run_db(body), ("玩偶A・漂泊者", 600, LATER, "座姿玩偶 第一彈", "digital"))

    def test_taken_counts_sold_before_and_items_not_returned(self):
        async def body(db):
            await self.add_listing(db)
            async with db.transaction():
                a = await db.insert_variant(500, name="玩偶A", kind="instant", price=500, sold_before=2, now=NOW)
                b = await db.insert_variant(500, name="玩偶B", kind="instant", price=500, now=NOW)
                for trade_id, qty_a, qty_b in ((9001, 1, 3), (9002, 4, 1)):
                    await db.insert_trade(id=trade_id, source_kind="listing", source_id=500, requester_id=trade_id,
                                          supplier_id=21, now=NOW)
                    order = await db.add_event(trade_id, "order", items={a: qty_a, b: qty_b}, now=NOW)
                    await db.insert_items(trade_id, order, [
                        dict(variant_key=a, name="玩偶A", kind="instant", qty=qty_a, unit_price=500),
                        dict(variant_key=b, name="玩偶B", kind="instant", qty=qty_b, unit_price=500)])
                await db.return_items(9002, {a: 3})  # 9002 取消：玩偶A 4 份裡 3 份沒交付、還回去；玩偶B 已交付、不還
            return await db.taken(500)

        self.assertEqual(self.run_db(body), {1: 2 + 1 + 1, 2: 3 + 1})

    def test_returns_start_from_the_latest_order_and_never_exceed_what_was_ordered(self):
        async def body(db):
            await self.add_listing(db)
            async with db.transaction():
                a = await db.insert_variant(500, name="玩偶A", kind="instant", price=500, now=NOW)
                await db.insert_trade(id=9001, source_kind="listing", source_id=500, requester_id=11,
                                      supplier_id=21, now=NOW)
                for qty in (4, 2):  # 先買 4 份，再加購 2 份
                    order = await db.add_event(9001, "order", items={a: qty}, now=NOW)
                    await db.insert_items(9001, order, [dict(variant_key=a, name="玩偶A", kind="instant", qty=qty,
                                                             unit_price=500)])
                await db.return_items(9001, {a: 3})
                first = [item.returned for item in await db.items(9001)]
                await db.return_items(9001, {a: 10})
            return first, [item.returned for item in await db.items(9001)], await db.taken(500)

        self.assertEqual(self.run_db(body), ([1, 2], [4, 2], {1: 0}))


class TradeAndEventTests(MarketDBTestCase):

    def test_trade_lookup_and_status(self):
        async def body(db):
            async with db.transaction():
                for trade_id, supplier in ((1, 21), (2, 21), (3, 22)):
                    await db.insert_trade(id=trade_id, source_kind="listing", source_id=500, requester_id=40 + trade_id,
                                          supplier_id=supplier, now=NOW)
                await db.set_trade_status(2, "completed", now=LATER)
            with self.assertRaises(ValueError):
                async with db.transaction():
                    await db.set_trade_status(1, "暫停", now=LATER)
            open_21 = [t.id for t in await db.trades(status="open", supplier_id=21)]
            done = await db.get_trade(2)
            return open_21, done.status, done.closed_at

        self.assertEqual(self.run_db(body), ([1], "completed", LATER))

    def test_event_items_round_trip_and_message_ids_fill_once(self):
        async def body(db):
            async with db.transaction():
                await db.insert_trade(id=1, source_kind="listing", source_id=500, requester_id=41, supplier_id=21, now=NOW)
                paid = await db.add_event(1, "deposit_received", items={1: 1, 2: 1}, amount=1000, actor_id=21,
                                          source="manual", now=NOW)
                await db.add_event(1, "paid_claim", actor_id=41, now=NOW)
                await db.set_event_message(paid, 777)
                await db.set_event_message(paid, 888)  # 已經有了就不改
            events = await db.events(1)
            received = await db.events(1, kinds=["deposit_received"])
            return [e.kind for e in events], received[0].items, received[0].amount, received[0].message_id

        self.assertEqual(self.run_db(body), (["deposit_received", "paid_claim"], {1: 1, 2: 1}, 1000, 777))

    def test_weekly_report_records(self):
        async def body(db):
            before = await db.weekly_report("2026-W46", 21)
            async with db.transaction():
                await db.record_weekly_report("2026-W46", 21, sent_at=NOW)
                await db.record_weekly_report("2026-W46", 22, error="私訊關閉")
            return before, await db.weekly_report("2026-W46", 21), await db.weekly_report("2026-W46", 22)

        self.assertEqual(self.run_db(body), (None, (NOW, None), (None, "私訊關閉")))


class SchemaAndBackupTests(MarketDBTestCase):

    def test_reconnect_keeps_data_and_records_the_version(self):
        self.run_db(lambda db: self.add_listing(db))

        async def body(db):
            return (await db.get_listing(500)).title, await db.get_meta("schema_version")

        self.assertEqual(self.run_db(body), ("座姿玩偶", str(market_db.SCHEMA_VERSION)))

    def test_refuses_a_database_newer_than_the_program(self):
        self.run_db(lambda db: self.add_listing(db))
        with sqlite3.connect(self.path) as raw:
            raw.execute("UPDATE meta SET value=? WHERE key='schema_version'", (str(market_db.SCHEMA_VERSION + 1),))

        async def main():
            db = MarketDB(self.path)
            try:
                await db.connect()
            except RuntimeError:
                return True
            await db.close()  # 沒擋下來：先關掉連線，測試行程才退得出去
            return False

        self.assertTrue(asyncio.run(main()), "比程式新的資料庫沒有被拒絕")

    def test_snapshot_is_a_complete_database(self):
        target = Path(self._dir.name) / "copy.db"

        async def body(db):
            await self.add_listing(db)
            async with db.transaction():
                await db.insert_variant(500, name="玩偶A", kind="instant", price=500, now=NOW)
            await db.snapshot(target)

        self.run_db(body)
        with sqlite3.connect(target) as copy:
            self.assertEqual(copy.execute("SELECT title FROM listings").fetchall(), [("座姿玩偶",)])
            self.assertEqual(copy.execute("SELECT name FROM variants").fetchall(), [("玩偶A",)])


class DailyBackupTests(MarketDBTestCase):
    """每日備份：一天一份、檢查過才用正式檔名、不留暫存檔、只留最新 14 份。"""

    def setUp(self):
        super().setUp()
        self.backups = Path(self._dir.name) / "market_backup"

    def test_one_backup_a_day_and_no_leftover_temp_file(self):
        async def body(db):
            await self.add_listing(db)
            first = await market_db.backup_daily(db, self.backups, today="2026-11-06")
            again = await market_db.backup_daily(db, self.backups, today="2026-11-06")
            return first, again

        first, again = self.run_db(body)
        self.assertEqual(first, self.backups / "market_2026-11-06.db")
        self.assertIsNone(again)
        self.assertEqual(sorted(p.name for p in self.backups.iterdir()), ["market_2026-11-06.db"])
        with sqlite3.connect(first) as copy:
            self.assertEqual(copy.execute("SELECT title FROM listings").fetchall(), [("座姿玩偶",)])

    def test_keeps_only_the_newest(self):
        self.backups.mkdir()
        for day in range(1, 16):  # 10-01～10-15 已經有 15 份
            (self.backups / f"market_2026-10-{day:02d}.db").write_bytes(b"")
        (self.backups / "notes.txt").write_text("別的檔不動", encoding="utf-8")

        self.run_db(lambda db: market_db.backup_daily(db, self.backups, today="2026-11-06", keep=14))
        names = sorted(p.name for p in self.backups.glob("market_*.db"))
        self.assertEqual(len(names), 14)
        self.assertEqual(names[0], "market_2026-10-03.db")
        self.assertEqual(names[-1], "market_2026-11-06.db")
        self.assertTrue((self.backups / "notes.txt").exists())

    def test_a_copy_that_fails_the_integrity_check_is_not_kept(self):
        async def broken_check(connection):
            return ["*** in database main ***", "Page 2 is never used"]

        async def body(db):
            await self.add_listing(db)
            with mock.patch.object(market_db, "_integrity_check", broken_check):
                with self.assertRaises(RuntimeError):
                    await market_db.backup_daily(db, self.backups, today="2026-11-06")

        self.run_db(body)
        self.assertEqual(list(self.backups.iterdir()), [])

    def test_failed_snapshot_leaves_no_file(self):
        async def body(db):
            async def broken(target):
                Path(target).write_bytes(b"half")
                raise RuntimeError("備份到一半壞了")
            db.snapshot = broken
            with self.assertRaises(RuntimeError):
                await market_db.backup_daily(db, self.backups, today="2026-11-06")

        self.run_db(body)
        self.assertEqual(list(self.backups.iterdir()), [])


class SharedConnectionTests(unittest.TestCase):

    def test_no_new_connection_after_close(self):
        async def main():
            with tempfile.TemporaryDirectory() as folder:
                original = market_db.MARKET_DB
                market_db.MARKET_DB = Path(folder) / "market.db"
                saved = market_db._shared.reset()
                try:
                    first = await market_db.get_shared_market_db()
                    again = await market_db.get_shared_market_db()
                    await market_db.close_shared_market_db()
                    try:
                        reopened = await market_db.get_shared_market_db()
                    except RuntimeError:
                        reopened = None
                    if reopened is not None:
                        await reopened.close()  # 不關的話連線的執行緒會讓測試行程退不出去
                    self.assertIsNone(reopened, "共用連線關掉之後又開了一條新的")
                    return first is again and first.path == Path(folder) / "market.db"
                finally:
                    market_db.MARKET_DB = original
                    market_db._shared.restore(saved)

        self.assertTrue(asyncio.run(main()))


if __name__ == "__main__":
    unittest.main()
