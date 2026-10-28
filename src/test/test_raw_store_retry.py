"""raw 備份的批次寫入（llm/storage/raw_message_store._sync_flush）：連線重試，以及壞的那筆只影響自己。

守的底線：
  - 連線池給到已斷的連線（寫入時丟連線層的錯誤）：那條連線丟掉、換一條再寫一次，整批不丟
  - 第二條還是連線錯誤：往外丟（呼叫端記 ERROR），不會一直重試
  - 逸出逐筆邊界的資料錯誤不換連線重試：rollback 後往外丟，連線照常放回池子
  - 寫成功的連線放回池子，壞掉的不放回
  - 一批裡有一筆資料在資料庫端寫不進去（jsonb 的 \\u0000 這類）：只略過那一筆，同一批的新增、編輯、刪除、反應照常提交；
    有沒有刪除的批次都一樣；那筆只在一行 WARNING 出現一次、不帶訊息內容，沒有 ERROR；統計只算真的寫進去的，另記略過幾筆
  - 壞的那筆在編輯或反應時，同樣只影響它自己；內文含 NUL（送出前就失敗）同樣只略過那筆；違反限制（23 類）、
    超過上限（54000，psycopg2 歸在 OperationalError）也只略過那筆，不當成連線壞了去換連線
  - 反應的讀改寫鎖住那一列（FOR UPDATE），照 message_id 排序處理：兩個 flush 重疊時不會互相蓋掉、也不會互相卡死
  - commit 時沒有沒收掉的保存點
  - 寫到一半斷線：不當成單筆失敗略過，換一條連線把整批重寫一次，每筆只寫一次
  - 權限不足、表不見這類每筆都會失敗的錯誤：整批往外丟、不逐筆略過、不重試
  - flush_raw_buffer 的回傳與 INFO 帶出略過的筆數

不連資料庫：連線池與連線都是假物件；逐筆寫入的測試用照 PostgreSQL 交易規則行為的假連線。
"""
import asyncio
import copy
import json
import logging
import os
import sys
import unittest
from contextlib import contextmanager
from unittest import mock

import psycopg2
import psycopg2.errors

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
        self.returned: list[tuple[object, bool]] = []

    def getconn(self):
        conn = self.conns.pop(0)
        self.handed_out.append(conn)
        return conn

    def putconn(self, conn, close=False):
        self.returned.append((conn, close))


class RawStoreRetryTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(mock.patch.object(raw, "_write_inserts", lambda cur, batch: (len(batch), 0)))

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


# ── 照 PostgreSQL 交易規則行為的假資料庫 ─────────────────────────────────────────


class PgDatabase:
    """一張假的 discord_messages_raw（提交後的內容）加上兩種會失敗的設定。

    bad_ids：這些訊息的新增、編輯、反應更新在資料庫端出錯；給 dict 時值是例外的種類，給清單時一律是 DataError
    （像 jsonb 裡有 \\u0000）。錯誤訊息帶一段 CONTEXT（訊息內容），驗 log 不會把它寫出來。deny：每一句資料語句都丟權限不足。
    """

    def __init__(self, rows=None, bad_ids=(), deny=False):
        self.rows = copy.deepcopy(rows or {})
        self.bad_ids = (dict(bad_ids) if isinstance(bad_ids, dict)
                        else {mid: psycopg2.errors.UntranslatableCharacter for mid in bad_ids})
        self.deny = deny
        self.reaction_reads: list[tuple[str, str]] = []   # (message_id, 送出的 SQL)


class PgConn:
    """一條連線、一個交易：一句在伺服器端出錯，交易就進入失敗狀態，之後除了 ROLLBACK TO 每一句都被拒；
    失敗狀態下 commit 不丟例外，但整個交易的寫入都不算數（和真的 psycopg2 一樣）。保存點：ROLLBACK TO 撤回
    保存點之後的寫入、解除失敗狀態、保存點還在；RELEASE 拿掉它與它之上的保存點。break_at：送出第幾句時斷線。"""

    def __init__(self, db: PgDatabase, break_at: int | None = None):
        self.db, self.break_at = db, break_at
        self.autocommit = True
        self.sent = 0
        self.broken = False
        self.commits = 0
        self.savepoints_at_commit: list[list[str]] = []
        self._begin()

    def _begin(self):
        self.work = copy.deepcopy(self.db.rows)
        self.failed = False
        self.savepoints: list[tuple[str, dict]] = []

    @contextmanager
    def cursor(self):
        yield PgCursor(self)

    def commit(self):
        if self.broken:
            raise psycopg2.InterfaceError("connection already closed")
        self.savepoints_at_commit.append([name for name, _ in self.savepoints])
        if not self.failed:
            self.db.rows = self.work
        self.commits += 1
        self._begin()

    def rollback(self):
        if self.broken:
            raise psycopg2.InterfaceError("connection already closed")
        self._begin()


class PgCursor:
    def __init__(self, conn: PgConn):
        self.conn = conn
        self.rowcount = -1
        self._row = None

    def fetchone(self):
        return self._row

    def _savepoint_index(self, name):
        for index in range(len(self.conn.savepoints) - 1, -1, -1):
            if self.conn.savepoints[index][0] == name:
                return index
        raise psycopg2.errors.InvalidSavepointSpecification(f'savepoint "{name}" does not exist')

    def _fail(self, exc):
        self.conn.failed = True
        raise exc

    def execute(self, sql, params=None):
        conn = self.conn
        if conn.broken:
            raise psycopg2.InterfaceError("connection already closed")
        values = params.values() if isinstance(params, dict) else (params or ())
        if any(isinstance(v, str) and "\x00" in v for v in values):
            raise ValueError("A string literal cannot contain NUL (0x00) characters.")   # 送出前就失敗
        conn.sent += 1
        if conn.break_at is not None and conn.sent == conn.break_at:
            conn.broken = True
            raise psycopg2.OperationalError("server closed the connection unexpectedly")
        words = " ".join(sql.split())
        self.rowcount, self._row = -1, None
        if words.startswith("ROLLBACK TO SAVEPOINT "):
            index = self._savepoint_index(words.split()[-1])
            conn.work = copy.deepcopy(conn.savepoints[index][1])
            del conn.savepoints[index + 1:]
            conn.failed = False
            return
        if conn.failed:
            raise psycopg2.errors.InFailedSqlTransaction(
                "current transaction is aborted, commands ignored until end of transaction block")
        if words.startswith("SAVEPOINT "):
            conn.savepoints.append((words.split()[-1], copy.deepcopy(conn.work)))
            return
        if words.startswith("RELEASE SAVEPOINT "):
            del conn.savepoints[self._savepoint_index(words.split()[-1]):]
            return
        if conn.db.deny:
            self._fail(psycopg2.errors.InsufficientPrivilege("permission denied for table discord_messages_raw"))
        if words.startswith("INSERT INTO discord_messages_raw"):
            mid = params["message_id"]
            self._maybe_bad(mid)
            if mid in conn.work:
                self.rowcount = 0
            else:
                conn.work[mid] = {"content": params["content"], "is_deleted": False, "reaction_breakdown": None}
                self.rowcount = 1
        elif words.startswith("UPDATE discord_messages_raw SET content"):
            mid = params["message_id"]
            self._maybe_bad(mid)
            self.rowcount = int(mid in conn.work)
            if mid in conn.work:
                conn.work[mid]["content"] = params["content"]
        elif words.startswith("UPDATE discord_messages_raw SET is_deleted"):
            hits = [mid for mid in params[0] if mid in conn.work]
            for mid in hits:
                conn.work[mid]["is_deleted"] = True
            self.rowcount = len(hits)
        elif words.startswith("SELECT reaction_breakdown"):
            mid = params[0]
            conn.db.reaction_reads.append((mid, words))
            self._row = (copy.deepcopy(conn.work[mid].get("reaction_breakdown")),) if mid in conn.work else None
            self.rowcount = int(mid in conn.work)
        elif words.startswith("UPDATE discord_messages_raw SET reaction_total"):
            mid = params[-1]
            self._maybe_bad(mid)
            conn.work[mid]["reaction_breakdown"] = json.loads(params[3])
            self.rowcount = 1
        else:
            raise AssertionError(f"假資料庫不認得這句：{words[:80]}")

    def _maybe_bad(self, mid):
        error = self.conn.db.bad_ids.get(mid)
        if error is not None:
            self._fail(error(
                "unsupported Unicode escape sequence\nDETAIL:  \\u0000 cannot be converted to text.\n"
                "CONTEXT:  JSON data, line 1: {\"title\": \"秘密內容"))


def _new(mid, content="嗨"):
    return {"message_id": mid, "guild_id": "1", "channel_id": "2", "thread_id": None, "author_id": "3",
            "content": content, "stickers": None, "tenor_gifs": None, "has_attachment": False, "has_embed": False,
            "created_at": "2026-10-28T00:00:00+00:00", "edited_at": None, "reply_to_id": None,
            "mention_count": 0, "mentioned_users": None}


def _edit(mid, content):
    return {"message_id": mid, "content": content, "stickers": None, "tenor_gifs": None,
            "has_attachment": False, "has_embed": False, "edited_at": "2026-10-28T00:01:00+00:00"}


def _react(mid, user):
    return {"message_id": mid, "emoji_name": "👍", "emoji_id": None, "user_id": user, "action": "add"}


EXISTING = {
    "m-edit": {"content": "原本", "is_deleted": False, "reaction_breakdown": None},
    "m-del": {"content": "要刪的", "is_deleted": False, "reaction_breakdown": None},
    "m-react": {"content": "被按讚的", "is_deleted": False, "reaction_breakdown": None},
}


class RowIsolationTests(unittest.TestCase):
    """一批裡壞的那筆只影響自己；整批的錯誤（斷線、權限）不逐筆略過。"""

    def flush(self, db, *, inserts=(), edits=(), deletes=(), reactions=(), conns=None):
        self.conns = conns or [PgConn(db)]
        self.pool = FakePool(self.conns)
        with mock.patch.object(raw, "_get_pool", lambda: self.pool):
            return raw._sync_flush(list(inserts), list(edits), list(deletes), list(reactions))

    def full_batch(self, db, *, with_delete=True, new=None):
        return self.flush(db, inserts=new or [_new("n1"), _new("n-bad"), _new("n2")], edits=[_edit("m-edit", "改過")],
                          deletes=["m-del"] if with_delete else [], reactions=[_react("m-react", "u1")])

    def assert_others_committed(self, db, *, with_delete=True):
        self.assertIn("n1", db.rows)
        self.assertIn("n2", db.rows)
        self.assertEqual("改過", db.rows["m-edit"]["content"])
        self.assertEqual(with_delete, db.rows["m-del"]["is_deleted"])
        self.assertIn("u1", db.rows["m-react"]["reaction_breakdown"]["reactors"])

    def test_a_bad_row_only_skips_itself(self):
        for with_delete in (True, False):   # 有刪除時以前是整批 ERROR，沒有刪除時是 INFO 寫著有寫入、其實全回滾
            with self.subTest(with_delete=with_delete):
                db = PgDatabase(rows=EXISTING, bad_ids={"n-bad"})
                with self.assertLogs(raw.logger, "WARNING") as logs:
                    stats = self.full_batch(db, with_delete=with_delete)

                self.assert_others_committed(db, with_delete=with_delete)
                self.assertNotIn("n-bad", db.rows)
                self.assertEqual({"inserted": 2, "updated": 1, "deleted": int(with_delete), "reactions_applied": 1,
                                  "failed": 1}, stats)
                skipped = [line for line in logs.output if "失敗、略過" in line]
                self.assertEqual(1, len(skipped))
                self.assertIn("n-bad", skipped[0])
                self.assertNotIn("秘密內容", "\n".join(logs.output), "錯誤只記第一行，不帶訊息內容")
                self.assertFalse([r for r in logs.records if r.levelno >= logging.ERROR])

    def test_a_bad_edit_or_reaction_only_skips_itself(self):
        for bad in ("m-edit", "m-react"):
            with self.subTest(bad=bad):
                db = PgDatabase(rows=EXISTING, bad_ids={bad})
                with self.assertLogs(raw.logger, "WARNING"):
                    stats = self.full_batch(db, new=[_new("n1"), _new("n2")])
                self.assertIn("n1", db.rows)
                self.assertIn("n2", db.rows)
                self.assertTrue(db.rows["m-del"]["is_deleted"])
                self.assertEqual(bad != "m-edit", db.rows["m-edit"]["content"] == "改過")
                self.assertEqual(bad != "m-react", db.rows["m-react"]["reaction_breakdown"] is not None)
                self.assertEqual(1, stats["failed"])

    def test_constraint_and_limit_errors_only_skip_that_message(self):
        for error in (psycopg2.errors.NotNullViolation, psycopg2.errors.ProgramLimitExceeded):
            with self.subTest(error=error.__name__):
                db = PgDatabase(rows=EXISTING, bad_ids={"n-bad": error})
                with self.assertLogs(raw.logger, "WARNING") as logs:
                    stats = self.full_batch(db)
                self.assert_others_committed(db)
                self.assertEqual(1, stats["failed"])
                self.assertEqual(1, len(self.pool.handed_out), "不是連線壞了，不換連線")
                self.assertFalse([line for line in logs.output if "換一條連線" in line])

    def test_reaction_rows_are_locked_and_processed_in_message_order(self):
        rows = {mid: {"content": "", "is_deleted": False, "reaction_breakdown": None} for mid in ("m3", "m1", "m2")}
        db = PgDatabase(rows=rows)
        self.flush(db, reactions=[_react("m3", "u1"), _react("m1", "u1"), _react("m2", "u2"), _react("m1", "u3")])
        self.assertEqual(["m1", "m2", "m3"], [mid for mid, _ in db.reaction_reads])
        self.assertTrue(all(sql.endswith("FOR UPDATE") for _, sql in db.reaction_reads), "讀改寫要鎖住那一列")
        self.assertEqual({"u1", "u3"}, set(db.rows["m1"]["reaction_breakdown"]["reactors"]))

    def test_nul_in_content_only_skips_that_message(self):
        db = PgDatabase(rows=EXISTING)
        with self.assertLogs(raw.logger, "WARNING") as logs:
            stats = self.flush(db, inserts=[_new("n1"), _new("n-nul", "壞\x00掉"), _new("n2")])
        self.assertEqual((2, 1), (stats["inserted"], stats["failed"]))
        self.assertNotIn("n-nul", db.rows)
        self.assertIn("n-nul", "\n".join(logs.output))

    def test_no_savepoint_is_left_open_at_commit(self):
        db = PgDatabase(rows=EXISTING, bad_ids={"n-bad"})
        with self.assertLogs(raw.logger, "WARNING"):
            self.full_batch(db)
        self.assertEqual([[]], self.conns[0].savepoints_at_commit)

    def test_a_dropped_connection_rewrites_the_whole_batch_once(self):
        db = PgDatabase(rows=EXISTING)
        # 每筆新增是 SAVEPOINT、INSERT、RELEASE 三句：第 5 句是第二筆的 INSERT
        conns = [PgConn(db, break_at=5), PgConn(db)]
        with self.assertLogs(raw.logger, "WARNING") as logs:
            stats = self.flush(db, inserts=[_new("n1"), _new("n2"), _new("n3")], conns=conns)
        self.assertEqual((3, 0), (stats["inserted"], stats["failed"]))
        self.assertTrue(all(mid in db.rows for mid in ("n1", "n2", "n3")))
        self.assertFalse([line for line in logs.output if "失敗、略過" in line], "斷線不是那一筆的錯，不能逐筆略過")
        self.assertTrue([line for line in logs.output if "換一條連線" in line])
        self.assertEqual([(conns[0], True), (conns[1], False)], self.pool.returned)
        self.assertEqual(1, conns[1].commits)

    def test_database_wide_errors_abort_the_batch_instead_of_skipping_rows(self):
        db = PgDatabase(rows=EXISTING, deny=True)
        with self.assertRaises(psycopg2.ProgrammingError):
            self.flush(db, inserts=[_new("n1"), _new("n2")])
        self.assertEqual(1, len(self.pool.handed_out), "權限不足換連線也沒用，不重試")
        self.assertEqual(EXISTING.keys(), db.rows.keys())


class FlushReportTests(unittest.TestCase):
    def setUp(self):
        for buffer in (raw._insert_buffer, raw._edit_buffer, raw._delete_buffer, raw._reaction_buffer):
            self.addCleanup(buffer.clear)
            buffer.clear()

    def test_flush_reports_skipped_rows(self):
        db = PgDatabase(rows=EXISTING, bad_ids={"n-bad"})
        pool = FakePool([PgConn(db)])
        raw._insert_buffer.extend([_new("n1"), _new("n-bad")])
        with mock.patch.object(raw, "_get_pool", lambda: pool), self.assertLogs(raw.logger, "INFO") as logs:
            stats = asyncio.run(raw.flush_raw_buffer())
        self.assertEqual((1, 1), (stats["inserted"], stats["failed"]))
        self.assertTrue([line for line in logs.output if "inserted=1" in line and "failed=1" in line])
        self.assertEqual(0, raw.total_buffer_size())


if __name__ == "__main__":
    unittest.main()
