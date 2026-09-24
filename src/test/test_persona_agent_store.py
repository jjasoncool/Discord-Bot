"""`persona_agent.store` 的寫入層（hermetic，不碰 DB）。

**為什麼需要這個檔**：`record_run` 原本零測試覆蓋，於是一次加必填參數時，
第二個呼叫端（`agent.run_and_persist` 的隔離路徑，連續失敗 3 次才會走）漏掉沒改，
324 個測試全綠、`py_compile` 也過——因為那個分支從沒被執行過。同一類的坑這個
專案踩過兩次（另一次是 `ESTIMATE_SCALE_RANGE` 沒被寫進檔案卻被引用）。

所以這裡守的不是 SQL 語意，是**呼叫端與簽章之間的契約**：
  - 欄位數／佔位符數／參數數三者必須一致（少一個就整列寫不進去）
  - 每一個真實呼叫端都要能跑得起來（包含平常不會執行的隔離路徑）
  - 序列化失敗只能丟掉那個欄位，不能賠掉整列 run 記錄

執行：
    cd src && python -m unittest test.test_persona_agent_store -v
"""

import asyncio
import os
import re
import sys
import unittest
from contextlib import contextmanager
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from llm.persona_agent import store  # noqa: E402

GUILD = 1276158257576284274
ALICE = "1001"


class FakeCursor:
    """記下最後一次 execute 的 SQL 與參數。"""

    def __init__(self):
        self.sql = None
        self.params = None
        self.rows = []

    def execute(self, sql, params=None):
        self.sql, self.params = sql, params

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


@contextmanager
def _fake_cursor_cm(cur):
    yield cur


def _patch_cursor(cur):
    """把 `LLMServiceSettings().pgvector_cursor()` 換成假的。"""
    settings = mock.MagicMock()
    settings.pgvector_cursor.side_effect = lambda **kw: _fake_cursor_cm(cur)
    return mock.patch.object(store, "LLMServiceSettings", return_value=settings)


def _record(cur, **overrides):
    kwargs = dict(
        run_id="batch-1", guild_id=GUILD, author_id=ALICE, status="ok",
        steps=4, tool_calls=10, prompt_tokens=17000, thinking_exhausted=False,
        evidence_claimed=22, evidence_bogus=2, accepted_changes=6,
        rejected_changes=1, skip_reason=None,
        trace=[{"step": 1, "tool": "get_messages"}],
        rejected=[{"change": {"trait": "假的"}, "why": "引用了不存在的 msg_id"}],
        quote_unmatched=3, quote_misses=["肥矮醜就是我了"],
        skipped_changes=None,
        ref_accounting={"unaccounted": [3], "duplicated": [], "unknown": []},
        duration_ms=250_000, error=None,
    )
    kwargs.update(overrides)
    with _patch_cursor(cur):
        return store.record_run(**kwargs)


class RecordRunContractTests(unittest.TestCase):
    """欄位／佔位符／參數三者對齊——不齊就整列寫不進去。"""

    def test_column_placeholder_and_param_counts_agree(self):
        cur = FakeCursor()
        self.assertTrue(_record(cur))
        cols = re.search(r"INSERT INTO \w+\s*\(([^)]*)\)", cur.sql, re.S).group(1)
        n_cols = len([c for c in cols.replace("\n", " ").split(",") if c.strip()])
        n_holders = cur.sql.count("%s")
        self.assertEqual(n_cols, n_holders, "欄位數與佔位符數不一致")
        self.assertEqual(n_cols, len(cur.params), "佔位符數與參數數不一致")

    def test_new_columns_are_written(self):
        cur = FakeCursor()
        _record(cur)
        for col in ("rejected", "quote_unmatched", "quote_misses",
                    "skipped_changes", "ref_accounting"):
            self.assertIn(col, cur.sql, f"{col} 沒有出現在 INSERT")
        self.assertIn(3, cur.params, "quote_unmatched 的值沒進參數")
        self.assertTrue(
            any(isinstance(p, str) and "肥矮醜就是我了" in p for p in cur.params),
            "quote_misses 的內容沒進參數",
        )

    def test_rejected_content_is_serialised_not_just_counted(self):
        """這個欄位存在的理由就是「只記數字查不下去」。"""
        cur = FakeCursor()
        _record(cur)
        self.assertTrue(
            any(isinstance(p, str) and "不存在的 msg_id" in p for p in cur.params),
            "被退掉的原因沒有被存下來",
        )

    def test_empty_list_is_not_conflated_with_none(self):
        """`[]`＝沒有任何一項被退；`None`＝本次沒算。兩者不能都寫成 NULL。"""
        cur = FakeCursor()
        _record(cur, rejected=[], quote_misses=[])
        self.assertIn("[]", [p for p in cur.params if isinstance(p, str)])

    def test_none_stays_none(self):
        """`None` 不可以被序列化成字串 "null"——那樣 SQL 端就不是 NULL 了。"""
        cur = FakeCursor()
        _record(cur, rejected=None, quote_unmatched=None, quote_misses=None)
        self.assertNotIn("null", [p for p in cur.params if isinstance(p, str)])
        # trace 有給值，所以字串型參數裡應該只剩 trace 那一個 jsonb
        jsonb_params = [p for p in cur.params if isinstance(p, str) and p.startswith("[")]
        self.assertEqual(len(jsonb_params), 1, "只有 trace 該被序列化")


class SkippedChangesTests(unittest.TestCase):
    """通過驗證卻沒寫成版本時，內容也要留下來。

    `confidence=low` 的執行會產出正確的觀察卻不寫版本（模型自認資料不足）。
    只記 `accepted_changes=5` 的話，「那五項寫了什麼」就永遠查不到——而低量使用者
    到底寫不寫得出東西，正是 M6 要判斷的。實測 09-02 有 6 個人這樣，19 項零幻覺的
    觀察全部消失。
    """

    def test_skipped_content_is_stored(self):
        cur = FakeCursor()
        _record(cur, skipped_changes=[{"trait": "夜貓", "text": "只在凌晨出現"}])
        self.assertTrue(
            any(isinstance(p, str) and "只在凌晨出現" in p for p in cur.params),
            "沒寫成版本的內容應該留在 runs 表",
        )

    def test_none_when_the_version_was_written(self):
        """有寫成版本時不必重複存——內容在 persona_agent_versions 裡。"""
        cur = FakeCursor()
        _record(cur, skipped_changes=None)
        self.assertIn("skipped_changes", cur.sql)


class SerialisationFailureTests(unittest.TestCase):
    """序列化炸掉只能丟欄位，不能賠掉整列。

    `rejected` 裝的是 LLM 原樣輸出。整列寫不進去的話，`consecutive_failures`
    數不到這次執行，隔離機制就永遠爬不到門檻——沉默失敗比丟一個欄位嚴重得多。
    """

    def test_unserialisable_payload_still_records_the_run(self):
        cur = FakeCursor()
        self.assertTrue(_record(cur, rejected=[{"bad": {1, 2, 3}}]))  # set 不能 json
        self.assertIsNotNone(cur.sql, "整列應該還是有寫出去")

    def test_null_byte_is_stripped_not_fatal(self):
        """`\\u0000` 是 jsonb 唯一不吃的字元。"""
        cur = FakeCursor()
        self.assertTrue(_record(cur, quote_misses=["前\x00後"]))
        self.assertFalse(
            any(isinstance(p, str) and "\\u0000" in p for p in cur.params),
            "null byte 應該在送進 jsonb 前就被抹掉",
        )


class LatestVersionTests(unittest.TestCase):
    """「沒有舊版本」與「讀取失敗」必須分得開——後者當成前者會寫出殘缺版本。"""

    def test_no_row_returns_none(self):
        cur = FakeCursor()
        with _patch_cursor(cur):
            self.assertIsNone(store.latest_version(GUILD, ALICE))

    def test_db_failure_raises_instead_of_returning_none(self):
        settings = mock.MagicMock()
        settings.pgvector_cursor.side_effect = RuntimeError("db down")
        with mock.patch.object(store, "LLMServiceSettings", return_value=settings):
            with self.assertRaises(RuntimeError):
                store.latest_version(GUILD, ALICE)


class EvidenceHistoryTests(unittest.TestCase):
    """同一段文字在所有版本引用過的證據——被換掉的正確證據要找得回來。"""

    RIGHT = "1549060752508452916"   # 「智障的8:2原則還是太煩了」
    WRONG = "1550426276672577557"   # 「看過有遊戲業的人發影片…」
    TEXT = "會用具體的商業/管理術語形容遊戲/商業決策（「智障的8:2原則還是太煩了」）"

    def _history(self, rows):
        cur = FakeCursor()
        cur.rows = rows
        with _patch_cursor(cur):
            return store.evidence_history(GUILD, ALICE), cur

    def test_real_case_swapped_evidence_is_recovered(self):
        """米拉第 6 項：v7～v10 引對的，v11 起被換成無關的那則。"""
        rows = [([{"type": "add", "text": self.TEXT, "evidence_msg_ids": [self.RIGHT]}],),
                ([{"type": "keep", "text": self.TEXT, "evidence_msg_ids": [self.RIGHT]}],),
                ([{"type": "keep", "text": self.TEXT, "evidence_msg_ids": [self.WRONG]}],)]
        history, cur = self._history(rows)
        self.assertEqual(history[self.TEXT], [self.RIGHT, self.WRONG], "依版本先後、去重")
        self.assertIn("guild_id", cur.sql)
        self.assertIn("ORDER BY version", cur.sql, "先後順序決定誰排前面、誰會被上限擠掉")

    def test_drops_and_empty_entries_are_ignored(self):
        rows = [([{"type": "drop", "text": "刪掉的", "evidence_msg_ids": ["x"]},
                  {"type": "add", "text": "  ", "evidence_msg_ids": ["y"]},
                  {"type": "add", "text": "壞資料", "evidence_msg_ids": None},
                  "不是物件"],)]
        history, _ = self._history(rows)
        self.assertEqual(history, {})

    def test_text_is_matched_after_strip(self):
        rows = [([{"type": "add", "text": " 同一句 ", "evidence_msg_ids": ["a"]}],),
                ([{"type": "keep", "text": "同一句", "evidence_msg_ids": ["b"]}],)]
        history, _ = self._history(rows)
        self.assertEqual(history["同一句"], ["a", "b"])

    def test_db_failure_returns_empty_not_raise(self):
        """讀不到歷史就只沿用上一版——不可以因此擋掉整個人的寫入。"""
        settings = mock.MagicMock()
        settings.pgvector_cursor.side_effect = RuntimeError("db down")
        with mock.patch.object(store, "LLMServiceSettings", return_value=settings):
            self.assertEqual(store.evidence_history(GUILD, ALICE), {})


class CallSiteTests(unittest.TestCase):
    """每個真實呼叫端都要跑得起來——包含平常不會執行的那個。"""

    def test_quarantine_path_calls_record_run_with_every_required_kwarg(self):
        """隔離路徑：連續失敗 3 次才會走，所以不寫測試就等於沒測。"""
        from llm.persona_agent import agent

        seen = {}

        def fake_record_run(**kw):
            seen.update(kw)
            return True

        with mock.patch.object(store, "consecutive_failures", return_value=99), \
             mock.patch.object(store, "record_run", side_effect=fake_record_run):
            run, validated = asyncio.run(agent.run_and_persist(
                user_id=ALICE, guild_id=GUILD, ctx=object(), model="m",
                run_id="batch-x", llm_service=None, save=True,
            ))

        self.assertEqual(run.status, "quarantined")
        self.assertIsNone(validated)
        import inspect
        required = {
            n for n, p in inspect.signature(store.record_run).parameters.items()
            if p.default is inspect.Parameter.empty
        }
        self.assertEqual(required - set(seen), set(), "隔離路徑漏帶了必填參數")


if __name__ == "__main__":
    unittest.main()
