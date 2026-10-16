"""raw 備份寫入的連線重試（llm/storage/raw_message_store._sync_flush）。

守的底線：
  - 連線池給到已斷的連線（寫入時丟連線層的錯誤）：那條連線丟掉、換一條再寫一次，整批不丟
  - 第二條還是連線錯誤：往外丟（呼叫端記 ERROR），不會一直重試
  - 資料本身的錯誤（違反唯一索引之類）不換連線重試：rollback 後往外丟，連線照常放回池子
  - 寫成功的連線放回池子，壞掉的不放回

不連資料庫：連線池與連線都是假物件。
"""
import os
import sys
import unittest
from contextlib import contextmanager
from unittest import mock

import psycopg2

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from llm.storage import raw_message_store as raw  # noqa: E402


class FakeConn:
    def __init__(self, fail: Exception | None = None):
        self.fail = fail
        self.committed = False
        self.rolled_back = False
        self.autocommit = True

    @contextmanager
    def cursor(self):
        if self.fail is not None:
            raise self.fail
        yield object()

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


class FakePool:
    def __init__(self, conns):
        self.conns = list(conns)
        self.handed_out = []
        self.returned: list[tuple[FakeConn, bool]] = []

    def getconn(self):
        conn = self.conns.pop(0)
        self.handed_out.append(conn)
        return conn

    def putconn(self, conn, close=False):
        self.returned.append((conn, close))


class RawStoreRetryTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(mock.patch.object(raw, "_write_inserts", lambda cur, batch: len(batch)))

    def flush_with(self, *conns):
        pool = FakePool(conns)
        with mock.patch.object(raw, "_get_pool", lambda: pool):
            stats = raw._sync_flush([{"message_id": "1"}, {"message_id": "2"}], [], [], [])
        return pool, stats

    def test_dead_connection_is_replaced_and_the_batch_still_written(self):
        dead = FakeConn(fail=psycopg2.OperationalError("server closed the connection unexpectedly"))
        good = FakeConn()

        with self.assertLogs(raw.logger, "WARNING"):
            pool, stats = self.flush_with(dead, good)

        self.assertEqual(2, stats["inserted"])
        self.assertTrue(good.committed)
        self.assertEqual([(dead, True), (good, False)], pool.returned, "壞的丟掉、好的放回")

    def test_second_connection_failure_is_raised(self):
        dead1 = FakeConn(fail=psycopg2.InterfaceError("connection already closed"))
        dead2 = FakeConn(fail=psycopg2.OperationalError("server closed the connection unexpectedly"))
        pool = FakePool([dead1, dead2, FakeConn()])

        with mock.patch.object(raw, "_get_pool", lambda: pool), self.assertLogs(raw.logger, "WARNING"):
            with self.assertRaises(psycopg2.OperationalError):
                raw._sync_flush([{"message_id": "1"}], [], [], [])

        self.assertEqual(2, len(pool.handed_out), "只重試一次")
        self.assertEqual([(dead1, True), (dead2, True)], pool.returned)

    def test_data_errors_are_not_retried(self):
        bad_data = FakeConn()
        pool = FakePool([bad_data, FakeConn()])

        def violate(cur, batch):
            raise psycopg2.IntegrityError("duplicate key value violates unique constraint")

        with mock.patch.object(raw, "_get_pool", lambda: pool), mock.patch.object(raw, "_write_inserts", violate):
            with self.assertRaises(psycopg2.IntegrityError):
                raw._sync_flush([{"message_id": "1"}], [], [], [])

        self.assertEqual(1, len(pool.handed_out), "資料錯誤換連線也沒用，不重試")
        self.assertTrue(bad_data.rolled_back)
        self.assertEqual([(bad_data, False)], pool.returned, "連線沒壞，照常放回")


if __name__ == "__main__":
    unittest.main()
