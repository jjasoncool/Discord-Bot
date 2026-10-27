"""重算聊天向量的工作（`llm.storage.chat_reembed`）。

守的底線：
  - 照 id 由新到舊分頁、每批寫回就 commit；中斷再跑從還是 NULL 的列接著做
  - 送去算的字串就是 text 原樣；寫回的是 `%s::vector` 的字面
  - GPU 忙（等不到閘門）就睡一陣再試同一批，不硬闖；後端連不上就停、不寫
  - 一批裡某一則算不出來就逐筆，仍失敗的列沿用舊向量（不留 NULL）；向量維度不對或有 nan 也算失敗
  - 整批逐筆都失敗、或最近幾批沿用舊向量太多就停、不寫；整批連不上先探一則，探得出來就逐筆
  - 影子欄已存在就不下 ALTER；讀完就結束交易，等鎖、睡覺時不持著表
  - 維護時段（04:00～07:30）不跑，等到結束
  - dry-run 不算也不寫；欄位名不合法就拒絕；--column embedding 沒配 --redo-copied 就拒絕
  - 給了 min_id 就只看 id 大於它的列（count 與每批查詢都帶 `id > %s`）；沒給就不加條件
  - `search_chat` 的評估用 embedding_column 進得了 SQL、不合法會被擋

hermetic：假連線、假 embedding、假閘門、假時鐘與 sleep，不碰模型與資料庫。

執行：
    cd src && python -m unittest test.test_chat_reembed -v
"""

import logging
import os
import sys
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from llm.client.lemonade_gate import GpuBusy  # noqa: E402
from llm.storage import chat_reembed as cre  # noqa: E402
from sys_settings.time_settings import APP_TZ  # noqa: E402

LOG = logging.getLogger(__name__)


class _Cursor:
    def __init__(self, db):
        self.db = db
        self._rows = []

    def execute(self, sql, params=None):
        self.db.statements.append((sql, params))
        s = " ".join(sql.split())
        if s.startswith("SELECT count(*)"):
            self._rows = [(len(self.db.pending()),)]
        elif s.startswith("SELECT 1 FROM information_schema.columns"):
            self._rows = [(1,)] if self.db.column_exists else []
        elif s.startswith("SELECT id, text"):
            before, *rest = params                       # (before, size) 或 (before, min_id, size)
            size, min_id = rest[-1], (rest[0] if len(rest) == 2 else None)
            self._rows = [(rid, text) for rid, text in sorted(self.db.pending(), reverse=True)
                          if rid < before and (min_id is None or rid > min_id)][:size]
        elif "SET embedding_v2 = embedding WHERE id = ANY" in s:
            for rid in params[0]:
                self.db.vectors[rid] = "copied"
        else:
            self._rows = []

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _Db:
    """假的聊天向量表：id → text；vectors 記影子欄寫了什麼。"""

    def __init__(self, rows):
        self.rows = dict(rows)
        self.column_exists = False
        self.vectors = {}
        self.statements = []
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def pending(self):
        return [(rid, text) for rid, text in self.rows.items() if rid not in self.vectors]

    def cursor(self):
        return _Cursor(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True


def _fake_execute_values(db):
    def execute_values(cur, sql, rows, template=None):
        cur.db.statements.append((sql, rows))
        assert template == "(%s, %s::vector)"
        for rid, literal in rows:
            cur.db.vectors[rid] = literal
    return execute_values


class _Model:
    def __init__(self, fail_texts=(), error=None, batch_error=None, bad_vectors=(), short_by=0):
        self.fail_texts, self.error, self.batch_error = set(fail_texts), error, batch_error
        self.bad_vectors, self.short_by, self.batches, self.singles = set(bad_vectors), short_by, [], []

    def _vec(self, text):
        return [float("nan"), 1.0] if text in self.bad_vectors else [0.5, len(text)]

    def get_text_embedding_batch(self, texts):
        self.batches.append(list(texts))
        if self.error:
            raise self.error
        if self.batch_error:
            raise self.batch_error
        if any(t in self.fail_texts for t in texts):
            raise RuntimeError("某一則讓後端出錯")
        out = [self._vec(t) for t in texts]
        return out[: len(out) - self.short_by] if self.short_by else out

    def get_text_embedding(self, text):
        self.singles.append(text)
        if self.error:
            raise self.error
        if text in self.fail_texts:
            raise RuntimeError("這一則算不出來")
        return self._vec(text)


class _Gate:
    def __init__(self, busy_times=0):
        self.busy_times, self.calls = busy_times, 0

    def __call__(self, *, max_wait_seconds=None):
        gate = self

        class _Ctx:
            def __enter__(self_inner):
                gate.calls += 1
                if gate.busy_times > 0:
                    gate.busy_times -= 1
                    raise GpuBusy("busy")

            def __exit__(self_inner, *exc):
                return False

        return _Ctx()


class ReembedRunTests(unittest.TestCase):
    def setUp(self):
        self.db = _Db({10: "維護到幾點", 11: "晚餐吃什麼", 12: "笑死", 13: "好喔"})
        self.sleeps = []
        dim = mock.patch.object(cre, "EMBED_DIM", 2)   # 假向量只有兩維
        dim.start()
        self.addCleanup(dim.stop)
        self.clock = datetime(2026, 10, 27, 12, 0, tzinfo=APP_TZ)
        self.ev = mock.patch.object(cre, "execute_values", _fake_execute_values(self.db))
        self.ev.start()
        self.addCleanup(self.ev.stop)

    def _run(self, model=None, gate=None, **kwargs):
        kwargs.setdefault("batch", 2)
        kwargs.setdefault("pause", 0.0)
        return cre.run(connect=lambda: self.db, embedder=lambda batch: model or _Model(), gate=gate or _Gate(),
                       sleep=self.sleeps.append, now=lambda: self.clock, **kwargs)

    def test_pages_from_newest_and_commits_every_batch(self):
        report = self._run()
        self.assertEqual(report.scanned, 4)
        self.assertEqual(report.embedded, 4)
        self.assertEqual(sorted(self.db.vectors), [10, 11, 12, 13])
        self.assertEqual(self.db.vectors[10], "[0.5,5.0]")        # 寫回的是 %s::vector 的字面
        self.assertGreaterEqual(self.db.rollbacks, 3)                # 每次讀完就結束交易，等鎖時不持著表
        befores = [params[0] for s, params in self.db.statements if s.startswith("SELECT id, text")]
        self.assertEqual(befores, [cre._ID_START, 12, 10])          # keyset：下一批從上一批最後的 id 往下，不從頭掃
        self.assertGreaterEqual(self.db.commits, 3)                  # 建欄一次、每批一次
        self.assertIn(("SET LOCAL lock_timeout = '3s'", None), self.db.statements)   # 只在建欄的交易裡限時
        self.assertTrue(self.db.closed)

    def test_resumes_with_only_the_rows_still_null(self):
        self.db.vectors[13] = "[1,1]"
        self.db.column_exists = True
        report = self._run()
        self.assertEqual(report.scanned, 3)
        self.assertFalse(any("ALTER TABLE" in s for s, _ in self.db.statements if isinstance(s, str)))   # 欄位在就不排鎖

    def test_a_whole_batch_failing_row_by_row_stops_instead_of_copying(self):
        report = self._run(model=_Model(fail_texts={"維護到幾點", "晚餐吃什麼", "笑死", "好喔"}))
        self.assertTrue(report.stopped)
        self.assertEqual(self.db.vectors, {})                        # 一列都沒沿用舊向量
        self.assertEqual(report.scanned, 0)

    def test_too_many_copied_rows_stops_the_run(self):
        rows = {i: f"句子{i}" for i in range(100, 100 + 120)}
        self.db = _Db(rows)
        self.ev.stop(); self.ev = mock.patch.object(cre, "execute_values", _fake_execute_values(self.db)); self.ev.start()
        bad = {f"句子{i}" for i in range(100, 100 + 120) if i % 2 == 0}   # 每批 4 則壞 2 則：比例 50%，超過 5%
        with mock.patch.object(cre, "COPY_LIMIT_MIN", 10):
            report = self._run(model=_Model(fail_texts=bad), batch=4)
        self.assertTrue(report.stopped)
        self.assertLess(report.scanned, 120)

    def test_gpu_busy_sleeps_and_retries_the_same_batch(self):
        report = self._run(gate=_Gate(busy_times=1))
        self.assertEqual(report.scanned, 4)
        self.assertIn(cre.BUSY_SLEEP_SECONDS, self.sleeps)

    def test_unreachable_backend_stops_without_writing(self):
        model = _Model(error=RuntimeError("down"))
        with mock.patch.object(cre, "is_unreachable", lambda exc: True):
            report = self._run(model=model)
        self.assertTrue(report.stopped)
        self.assertEqual(self.db.vectors, {})

    def test_a_bad_row_falls_back_to_per_row_and_keeps_the_old_vector(self):
        report = self._run(model=_Model(fail_texts={"笑死"}))
        self.assertEqual(report.scanned, 4)
        self.assertEqual(report.copied, 1)
        self.assertEqual(report.failed_ids, [12])
        self.assertEqual(self.db.vectors[12], "copied")              # 沿用舊向量，不留 NULL
        self.assertEqual(self.db.vectors[13], "[0.5,2.0]")

    def test_waits_out_the_maintenance_window(self):
        times = iter([datetime(2026, 10, 27, 5, 0, tzinfo=APP_TZ)] * 2 + [datetime(2026, 10, 27, 7, 31, tzinfo=APP_TZ)] * 20)
        report = cre.run(connect=lambda: self.db, embedder=lambda b: _Model(), gate=_Gate(), sleep=self.sleeps.append,
                         now=lambda: next(times), batch=4, pause=0.0)
        self.assertEqual(self.sleeps[:2], [60, 60])
        self.assertEqual(report.scanned, 4)

    def test_dry_run_counts_but_never_writes(self):
        report = self._run(dry_run=True)
        self.assertEqual(report.remaining_at_start, 4)
        self.assertEqual(self.db.vectors, {})
        self.assertFalse(any("ALTER TABLE" in s for s, _ in self.db.statements if isinstance(s, str)))

    def test_limit_and_pause_let_the_bot_go_first(self):
        report = self._run(limit=3, pause=0.5)
        self.assertEqual(report.scanned, 3)
        self.assertEqual(self.sleeps, [0.5, 0.5])                  # 每批放鎖後讓一拍

    def test_rejects_unsafe_column_names(self):
        with self.assertRaises(ValueError):
            self._run(column="embedding_v2; drop table x")

    def test_min_id_keeps_the_redo_to_the_newest_rows(self):
        """切換後補尾巴的比對（值等於 embedding_v1）要讀兩欄的向量，沒有 id 範圍就是掃整張表。"""
        report = self._run(column="embedding", redo_copied=True, min_id=11)
        self.assertEqual(report.scanned, 2)
        self.assertEqual(sorted(self.db.vectors), [12, 13])
        selects = [(s, params) for s, params in self.db.statements if isinstance(s, str) and s.startswith("SELECT id, text")]
        self.assertTrue(selects)
        for sql, params in selects:
            self.assertIn("id > %s", sql)
            self.assertEqual(params[1], 11)                          # (before, min_id, size)
        count = [(s, params) for s, params in self.db.statements if isinstance(s, str) and s.startswith("SELECT count(*)")][0]
        self.assertIn("id > %s", count[0])
        self.assertEqual(count[1], (11,))

    def test_without_min_id_the_predicate_has_no_id_floor(self):
        self._run()
        sqls = [s for s, _ in self.db.statements if isinstance(s, str) and s.startswith(("SELECT id, text", "SELECT count(*)"))]
        self.assertTrue(sqls)
        self.assertFalse(any("id > %s" in s for s in sqls))

    def test_rewriting_the_live_column_requires_redo_copied(self):
        with self.assertRaises(ValueError):
            self._run(column="embedding")                       # 述詞恆假，會「做了 0 列」假裝成功

    def test_bad_vectors_and_short_batches_fall_back_without_losing_rows(self):
        report = self._run(model=_Model(bad_vectors={"笑死"}))
        self.assertEqual(report.copied, 1)
        self.assertEqual(self.db.vectors[12], "copied")              # nan 的向量不寫、沿用舊向量
        self.db = _Db({10: "維護到幾點", 11: "晚餐吃什麼"})
        self.ev.stop(); self.ev = mock.patch.object(cre, "execute_values", _fake_execute_values(self.db)); self.ev.start()
        model = _Model(short_by=1)
        report = self._run(model=model)
        self.assertEqual(sorted(self.db.vectors), [10, 11])          # 後端少回一個：改逐筆，一列都不漏
        self.assertEqual(len(model.singles), 2)

    def test_batch_timeout_probes_one_row_before_giving_up(self):
        model = _Model(batch_error=RuntimeError("timeout"))
        with mock.patch.object(cre, "is_unreachable", lambda exc: str(exc) == "timeout"):
            report = self._run(model=model)
        self.assertEqual(report.scanned, 4)                          # 整批逾時但單則算得出來：逐筆做完
        self.assertEqual(report.stopped, "")
        self.assertEqual(sorted(self.db.vectors), [10, 11, 12, 13])

    def test_a_probe_row_that_fails_on_its_own_does_not_stop_the_run(self):
        model = _Model(batch_error=RuntimeError("timeout"), fail_texts={"好喔"})   # 探測的第一則（最新）本身算不出來
        with mock.patch.object(cre, "is_unreachable", lambda exc: str(exc) == "timeout"):
            report = self._run(model=model)
        self.assertEqual(report.stopped, "")
        self.assertEqual(report.scanned, 4)
        self.assertEqual(report.failed_ids, [13])                    # 那一則照規則沿用舊向量，其餘算完


class SearchChatColumnTests(unittest.TestCase):
    def test_evaluation_can_point_search_chat_at_the_shadow_column(self):
        from llm.retrievers import context_retriever as cr

        statements = []

        class _Cur:
            def execute(self, sql, params=None):
                statements.append(sql)

            def fetchall(self):
                return []

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        class _Conn:
            def cursor(self):
                return _Cur()

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        embed = SimpleNamespace(get_query_embedding=lambda q: [0.1])
        with mock.patch.object(cr, "psycopg2", cr.psycopg2 or object()), \
             mock.patch.object(cr, "_get_embed_model", lambda logger: embed), \
             mock.patch.object(cr, "_pgvector_connect", lambda: _Conn()), \
             mock.patch.object(cr.switches, "current", lambda: SimpleNamespace(chat_vector_index="full")):
            cr.search_chat(question="x", limit=3, logger=LOG, embedding_column="embedding_v2")
            select = [s for s in statements if s.lstrip().startswith("SELECT")][0]
            self.assertIn("embedding_v2 <=> %s::vector", select)
            self.assertIn("embedding_v2 IS NOT NULL", select)
            with self.assertRaises(ValueError):
                cr.search_chat(question="x", limit=3, logger=LOG, embedding_column="embedding; drop")


if __name__ == "__main__":
    unittest.main()
