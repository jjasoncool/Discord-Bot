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
  - 還沒寫進去就被刪的訊息照樣寫入、標成已刪，內容留著（發出後馬上刪的也查得到）；刪除時間是收到事件的時刻，
    不是寫入那一批的時刻；同一則收到兩次刪除事件，記先到的那次
  - 編輯留下第一次改之前的原文：再改不覆蓋、文字沒變的編輯事件不算；還沒寫進去就被改的（10 秒內修錯字）也留得下
  - 正式表還沒加後來的欄位：那幾欄不寫、其餘照常寫進去，ERROR 只記一次；之後欄位加上了，不必重啟就開始寫
  - 誰刪的：審核日誌裡同頻道、同作者的刪除紀錄多了一則＝別人刪的、記那人的 id；沒有多＝作者自己刪的、記作者 id；
    同一筆紀錄多兩則時兩次刪除各認領一則；判斷不了（基準還沒記好、讀審核日誌失敗、表裡沒有這則）記 NULL
  - 讀：頻道與討論串拆成 channel_id／thread_id 的方式和寫入同一份；查被刪的訊息前先把緩衝寫進去；前後文照時間排；
    編輯前的原文連還在緩衝裡的改動也算（寫入緩衝帶著原文、排隊中的編輯拿表裡現在的內容當原文）

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
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest import mock

import discord
import psycopg2
import psycopg2.errors

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from llm.storage import raw_message_store as raw  # noqa: E402


def setUpModule():
    # 預設正式表上欄位都在、已經查過：其他測試不必管查欄位那一句（數第幾句斷線的測試才對得上）
    patcher = mock.patch.object(raw, "_added_columns", frozenset(raw.ADDED_COLUMNS))
    patcher.start()
    unittest.addModuleCleanup(patcher.stop)


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
        self.enterContext(mock.patch.object(raw, "_write_inserts", lambda cur, batch, **_: (len(batch), 0)))

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

        def violate(cur, batch, **_):
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

    def __init__(self, rows=None, bad_ids=(), deny=False, columns=raw.ADDED_COLUMNS):
        self.rows = copy.deepcopy(rows or {})
        self.columns = tuple(columns)   # 後來才加的欄位裡，這張表上有哪些
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
        self._rows = []

    def fetchone(self):
        return self._row

    def fetchall(self):
        return list(self._rows)

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
        if words.startswith("SELECT column_name FROM information_schema.columns"):
            self._rows = [(name,) for name in conn.db.columns if name in params[0]]
            return
        if words.startswith("INSERT INTO discord_messages_raw"):
            self._require_columns(words)
            mid = params["message_id"]
            self._maybe_bad(mid)
            if mid in conn.work:
                self.rowcount = 0
            else:
                conn.work[mid] = {"content": params["content"], "is_deleted": False, "reaction_breakdown": None,
                                  "author_id": params["author_id"]}
                if "original_content" in words:
                    conn.work[mid]["original_content"] = params["original_content"]
                self.rowcount = 1
        elif words.startswith("UPDATE discord_messages_raw SET content"):
            self._require_columns(words)
            mid = params["message_id"]
            self._maybe_bad(mid)
            self.rowcount = int(mid in conn.work)
            if mid in conn.work:
                row = conn.work[mid]
                if "original_content = CASE WHEN original_content IS NULL AND content IS DISTINCT FROM" in words:
                    if row.get("original_content") is None and row["content"] != params["content"]:
                        row["original_content"] = row["content"]
                row["content"] = params["content"]
        elif words.startswith("UPDATE discord_messages_raw SET is_deleted"):
            self._require_columns(words)
            with_by = "deleted_by" in words
            mids, times, bys = params if with_by else (*params, [None] * len(params[0]))
            hits = [(mid, at, by) for mid, at, by in zip(mids, times, bys) if mid in conn.work]
            for mid, at, by in hits:
                conn.work[mid].update(is_deleted=True, deleted_at=at)
                if with_by:
                    to_author = by == raw.DELETED_BY_AUTHOR and (
                        f"WHEN d.deleted_by = '{raw.DELETED_BY_AUTHOR}' THEN discord_messages_raw.author_id" in words)
                    conn.work[mid]["deleted_by"] = conn.work[mid]["author_id"] if to_author else by
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

    def _require_columns(self, words):
        for name in raw.ADDED_COLUMNS:
            if name in words and name not in self.conn.db.columns:
                self._fail(psycopg2.errors.UndefinedColumn(f'column "{name}" does not exist'))

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


DELETED_AT = "2026-10-28T00:02:00+00:00"

EXISTING = {
    "m-edit": {"content": "原本", "is_deleted": False, "reaction_breakdown": None},
    "m-del": {"content": "要刪的", "is_deleted": False, "reaction_breakdown": None, "author_id": "9"},
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
                          deletes=[("m-del", DELETED_AT, None)] if with_delete else [], reactions=[_react("m-react", "u1")])

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

    def test_the_first_edit_keeps_the_original_text(self):
        db = PgDatabase(rows=EXISTING)
        self.flush(db, edits=[_edit("m-edit", "改過")])
        self.flush(db, edits=[_edit("m-edit", "改第二次")])
        self.assertEqual(("改第二次", "原本"), (db.rows["m-edit"]["content"], db.rows["m-edit"]["original_content"]),
                         "原文是第一次改之前的，再改不覆蓋")

    def test_an_edit_event_that_keeps_the_text_is_not_an_edit(self):
        db = PgDatabase(rows=EXISTING)
        self.flush(db, edits=[_edit("m-edit", "原本")])   # 連結預覽載入
        self.assertIsNone(db.rows["m-edit"].get("original_content"))

    def test_without_the_added_columns_the_rest_is_still_written(self):
        self.enterContext(mock.patch.object(raw, "_added_columns", None))
        db = PgDatabase(rows=EXISTING, columns=())
        with self.assertLogs(raw.logger, "ERROR") as logs:
            stats = self.flush(db, inserts=[_new("n1")], edits=[_edit("m-edit", "改過")])
        self.assertEqual((1, 1, 0), (stats["inserted"], stats["updated"], stats["failed"]))
        self.assertEqual("改過", db.rows["m-edit"]["content"])
        self.assertEqual(1, len([line for line in logs.output if "缺欄位" in line]))
        with self.assertNoLogs(raw.logger, "ERROR"):
            self.flush(db, edits=[_edit("m-edit", "又改")])

    def test_columns_added_later_are_used_without_a_restart(self):
        self.enterContext(mock.patch.object(raw, "_added_columns", None))
        db = PgDatabase(rows=EXISTING, columns=())
        with self.assertLogs(raw.logger, "ERROR"):
            self.flush(db, edits=[_edit("m-edit", "改過")])
        db.columns = raw.ADDED_COLUMNS
        self.enterContext(mock.patch.object(raw, "_added_columns_checked_at",
                                            raw._added_columns_checked_at - raw._ADDED_COLUMNS_RECHECK_SECONDS - 1))
        self.flush(db, edits=[_edit("m-edit", "再改")])
        self.assertEqual("改過", db.rows["m-edit"]["original_content"])

    def test_who_deleted_is_written(self):
        for by, expected in ((raw.DELETED_BY_AUTHOR, "9"), ("77", "77"), (None, None)):
            with self.subTest(by=by):
                db = PgDatabase(rows=EXISTING)
                self.flush(db, deletes=[("m-del", DELETED_AT, by)])
                self.assertEqual(expected, db.rows["m-del"]["deleted_by"], "作者自己刪的記作者 id、別人刪的記那人、不知道記空")

    def test_without_the_deleted_by_column_the_deletion_is_still_marked(self):
        self.enterContext(mock.patch.object(raw, "_added_columns", frozenset({"original_content"})))
        db = PgDatabase(rows=EXISTING, columns=("original_content",))
        stats = self.flush(db, deletes=[("m-del", DELETED_AT, raw.DELETED_BY_AUTHOR)])
        self.assertEqual(1, stats["deleted"])
        self.assertTrue(db.rows["m-del"]["is_deleted"])
        self.assertNotIn("deleted_by", db.rows["m-del"])

    def test_repeated_delete_events_keep_the_first_time(self):
        db = PgDatabase(rows=EXISTING)
        stats = self.flush(db, deletes=[("m-del", DELETED_AT, "77"), ("m-del", "2026-10-28T00:09:00+00:00", None)])
        self.assertEqual(DELETED_AT, db.rows["m-del"]["deleted_at"])
        self.assertEqual("77", db.rows["m-del"]["deleted_by"], "誰刪的以知道的那次為準")
        self.assertEqual(1, stats["deleted"])


class FlushReportTests(unittest.TestCase):
    def test_an_edit_before_the_batch_is_written_keeps_the_original(self):
        db = PgDatabase()
        pool = FakePool([PgConn(db)])
        raw._insert_buffer.append(_new("n1", "打措字"))
        author = SimpleNamespace(bot=False)
        for text in ("打錯字", "打錯字了"):
            with mock.patch.object(raw, "_build_row", lambda msg, text=text: {**_new("n1", text), "original_content": None}):
                raw.enqueue_raw_edit(SimpleNamespace(id="n1", author=author))
        with mock.patch.object(raw, "_get_pool", lambda: pool):
            asyncio.run(raw.flush_raw_buffer())
        self.assertEqual(("打錯字了", "打措字"), (db.rows["n1"]["content"], db.rows["n1"]["original_content"]))

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

    def test_deletions_not_yet_written_can_be_asked_for(self):
        # 刪除記號是批次寫的：要馬上知道「這則被刪了沒」的讀取端拿得到還沒寫進資料庫的那幾則
        self.assertEqual(set(), raw.pending_deleted_ids())
        raw.enqueue_raw_delete(123)
        raw.enqueue_raw_delete("456")
        self.assertEqual({"123", "456"}, raw.pending_deleted_ids())
        raw._delete_buffer.clear()
        self.assertEqual(set(), raw.pending_deleted_ids())

    def test_message_deleted_before_its_batch_is_written_is_kept_and_marked(self):
        db = PgDatabase()
        pool = FakePool([PgConn(db)])
        raw._insert_buffer.extend([_new("n1", "打錯了趕快刪"), _new("n2")])
        raw.enqueue_raw_delete(1)   # bot 沒存過的訊息：對不到，不影響別則
        raw.enqueue_raw_delete("n1")
        received_at = raw._delete_buffer[-1][1]
        with mock.patch.object(raw, "_get_pool", lambda: pool):
            stats = asyncio.run(raw.flush_raw_buffer())
        self.assertEqual("打錯了趕快刪", db.rows["n1"]["content"], "還在緩衝裡就被刪的訊息要留下內容")
        self.assertTrue(db.rows["n1"]["is_deleted"])
        self.assertEqual(received_at, db.rows["n1"]["deleted_at"], "刪除時間是收到事件的時刻")
        self.assertFalse(db.rows["n2"]["is_deleted"])
        self.assertEqual((2, 1), (stats["inserted"], stats["deleted"]))


def _audit(entry_id, count, *, channel=10, target=3, user=99):
    """審核日誌裡一筆「刪了別人的訊息」：誰刪的（user）、刪了誰的（target）、哪個頻道、累計幾則。"""
    return SimpleNamespace(id=entry_id, user_id=user, target=SimpleNamespace(id=target),
                           extra=SimpleNamespace(count=count, channel=SimpleNamespace(id=channel)))


class FakeGuild:
    def __init__(self, entries=(), fail=None):
        self.id = 1
        self.entries = list(entries)
        self.fail = fail
        self.reads = 0

    def audit_logs(self, *, limit, action):
        self.reads += 1
        guild = self

        async def read():
            if guild.fail is not None:
                raise guild.fail
            for entry in guild.entries[:limit]:
                yield entry
        return read()


class DeleterClaimTests(unittest.TestCase):
    """審核日誌對上這次刪除的規則（純函式）。"""

    def test_a_new_record_in_this_channel_for_this_author_is_someone_else(self):
        claimed = {}
        entries = [_audit(500, 1)]
        self.assertEqual("99", raw._claim_deleter(claimed, entries, 10, "3"))
        self.assertEqual(raw.DELETED_BY_AUTHOR, raw._claim_deleter(claimed, entries, 10, "3"), "同一則不認領兩次")

    def test_a_grown_count_is_someone_else(self):
        claimed = {500: 2}
        self.assertEqual("99", raw._claim_deleter(claimed, [_audit(500, 3)], 10, "3"))
        self.assertEqual({500: 3}, claimed)

    def test_two_new_deletions_in_one_record_are_claimed_one_each(self):
        claimed = {500: 1}
        entries = [_audit(500, 3)]
        self.assertEqual(["99", "99", raw.DELETED_BY_AUTHOR],
                         [raw._claim_deleter(claimed, entries, 10, "3") for _ in range(3)])

    def test_records_elsewhere_or_for_someone_else_mean_the_author_deleted_it(self):
        cases = {"別的頻道": ({}, _audit(500, 1, channel=11)), "刪的是別人的訊息": ({}, _audit(500, 1, target=4)),
                 "則數沒變": ({500: 2}, _audit(500, 2))}
        for name, (claimed, entry) in cases.items():
            with self.subTest(name):
                self.assertEqual(raw.DELETED_BY_AUTHOR, raw._claim_deleter(claimed, [entry], 10, "3"))

    def test_records_that_left_the_window_are_dropped(self):
        claimed = {400: 1, 500: 1}
        raw._claim_deleter(claimed, [_audit(500, 1)], 10, "3")
        self.assertEqual({500: 1}, claimed)


class RecordDeletionTests(unittest.IsolatedAsyncioTestCase):
    """刪除事件：先記時刻，等審核日誌再判斷誰刪的，然後排進寫入。"""

    def setUp(self):
        self.enterContext(mock.patch.dict(raw._audit_claimed, clear=True))
        self.waits = []

        async def no_wait(seconds):
            self.waits.append(seconds)
        self.enterContext(mock.patch.object(raw, "_sleep", no_wait))
        self.enterContext(mock.patch.object(raw, "_author_in_db", lambda mid: "3"))
        for buffer in (raw._insert_buffer, raw._delete_buffer):
            self.addCleanup(buffer.clear)
            buffer.clear()

    async def test_someone_elses_deletion_is_recorded_with_their_id(self):
        guild = FakeGuild([_audit(500, 1)])
        await raw.prime_delete_audit(guild)
        guild.entries = [_audit(500, 2)]
        await raw.record_deletion(guild, 7, 10)
        self.assertEqual([("7", "99")], [(mid, by) for mid, _, by in raw._delete_buffer])
        self.assertEqual([raw.AUDIT_WAIT_SECONDS], self.waits, "要等審核日誌寫好再讀")

    async def test_no_new_record_means_the_author_deleted_it(self):
        guild = FakeGuild([_audit(500, 1)])
        await raw.prime_delete_audit(guild)
        await raw.record_deletion(guild, 7, 10, author_id=3)
        self.assertEqual(raw.DELETED_BY_AUTHOR, raw._delete_buffer[0][2])

    async def test_before_the_baseline_is_known_the_deleter_is_unknown(self):
        guild = FakeGuild([_audit(500, 1)])
        await raw.record_deletion(guild, 7, 10)
        self.assertIsNone(raw._delete_buffer[0][2], "基準還沒記好，分不出這筆紀錄是不是這次的")
        self.assertIn(guild.id, raw._audit_claimed, "順手把基準記好")
        await raw.record_deletion(guild, 8, 10)
        self.assertEqual(raw.DELETED_BY_AUTHOR, raw._delete_buffer[1][2])

    async def test_a_failed_audit_read_is_unknown(self):
        guild = FakeGuild()
        await raw.prime_delete_audit(guild)
        guild.fail = discord.HTTPException(SimpleNamespace(status=500, reason="boom"), "boom")
        with self.assertLogs(raw.logger, "WARNING"):
            await raw.record_deletion(guild, 7, 10)
        self.assertIsNone(raw._delete_buffer[0][2])

    async def test_a_message_the_table_does_not_have_skips_the_audit_log(self):
        guild = FakeGuild()
        await raw.prime_delete_audit(guild)
        with mock.patch.object(raw, "_author_in_db", lambda mid: None):
            await raw.record_deletion(guild, 7, 10)
        self.assertEqual(1, guild.reads, "只有記基準那一次")
        self.assertIsNone(raw._delete_buffer[0][2])

    async def test_the_author_of_a_buffered_message_is_read_from_the_buffer(self):
        raw._insert_buffer.append({**_new("7"), "author_id": "4"})
        guild = FakeGuild([_audit(500, 1, target=4)])
        await raw.prime_delete_audit(guild)
        guild.entries = [_audit(500, 2, target=4)]
        with mock.patch.object(raw, "_author_in_db", lambda mid: self.fail("緩衝裡有就不查表")):
            await raw.record_deletion(guild, 7, 10)
        self.assertEqual("99", raw._delete_buffer[0][2])

    async def test_the_deletion_time_is_taken_before_waiting(self):
        guild = FakeGuild()
        await raw.prime_delete_audit(guild)
        ticks = iter(range(1, 10))

        class Ticking:   # 每讀一次時間多一秒：看得出刪除時間是等之前還是等之後讀的
            @staticmethod
            def now(tz=None):
                return datetime(2026, 11, 11, 12, 0, next(ticks), tzinfo=tz)

        async def wait(seconds):
            Ticking.now(timezone.utc)
        with mock.patch.object(raw, "datetime", Ticking), mock.patch.object(raw, "_sleep", wait):
            await raw.record_deletion(guild, 7, 10)
        self.assertEqual("2026-11-11T12:00:01+00:00", raw._delete_buffer[0][1])


class RawReadTests(unittest.IsolatedAsyncioTestCase):
    """讀被刪的訊息與編輯前的原文（給 deleted_and_edited）。"""

    def setUp(self):
        for buffer in (raw._insert_buffer, raw._edit_buffer):
            self.addCleanup(buffer.clear)
            buffer.clear()
        self.steps: list = []
        self.results: list[list[dict]] = []

        def select(sql, params):
            self.steps.append(("查", " ".join(sql.split()), params))
            return self.results.pop(0) if self.results else []

        async def flush():
            self.steps.append(("寫入",))
            return {}
        self.enterContext(mock.patch.object(raw, "_select", select))
        self.enterContext(mock.patch.object(raw, "flush_raw_buffer", flush))

    def test_threads_are_stored_under_their_parent_channel(self):
        thread = mock.Mock(spec=discord.Thread, id=5, parent_id=4)
        self.assertEqual(("4", "5"), raw.channel_keys(thread))
        self.assertEqual(("7", None), raw.channel_keys(SimpleNamespace(id=7)))

    async def test_recent_deletions_write_the_buffer_first(self):
        since = datetime(2026, 11, 11, tzinfo=timezone.utc)
        await raw.recent_deletions("4", "5", since=since, limit=20)
        self.assertEqual(("寫入",), self.steps[0], "剛刪的、剛發的前後文都要先寫進去才查得到")
        _, sql, params = self.steps[1]
        self.assertIn("is_deleted", sql)
        self.assertEqual(("4", "5", since), params[:3])
        self.assertEqual(20, params[-1])

    async def test_rows_around_come_back_in_time_order(self):
        self.results = [[{"message_id": "b2"}, {"message_id": "b1"}], [{"message_id": "a1"}, {"message_id": "a2"}]]
        earlier, later = await raw.rows_around("4", None, datetime(2026, 11, 11, tzinfo=timezone.utc),
                                                before=5, after=20)
        self.assertEqual((["b1", "b2"], ["a1", "a2"]),
                         ([r["message_id"] for r in earlier], [r["message_id"] for r in later]))

    async def test_original_texts_count_edits_that_are_not_written_yet(self):
        raw._insert_buffer.append({**_new("n1", "改好了"), "original_content": "改壞了"})
        raw._edit_buffer.append(_edit("m1", "新的"))
        self.results = [[
            {"message_id": "m1", "content": "舊的", "original_content": None},       # 編輯還在排隊
            {"message_id": "m2", "content": "現在", "original_content": "最早"},      # 表裡已經記了
            {"message_id": "m3", "content": "沒改過", "original_content": None},
        ]]
        found = await raw.original_texts(["n1", "m1", "m2", "m3"])
        self.assertEqual({"n1": "改壞了", "m1": "舊的", "m2": "最早"}, found)
        self.assertEqual(["m1", "m2", "m3"], self.steps[0][2][0], "緩衝裡已經知道的不再查表")


if __name__ == "__main__":
    unittest.main()
