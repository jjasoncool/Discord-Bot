"""聊天檢索的評估程式（`llm/retrievers/eval/evaluate.py`）。

守的底線：
  - 考卷兩種答案寫法都認：relevant（`chat:<message_id>`，有沒有 chat: 前綴都行）比 message_id；口頭禪題 author＋phrase
    比「同一個作者、句子包含那句話」，標點與空白不計；兩種都沒給的題目讀考卷時就報錯
  - 每題一次 `search_chat`：全庫（不限頻道）、return_meta、預設不折疊、用先算好的問句向量（不再逐題找模型）
  - Hit@k 是題數不是比例；名次中位數只算進了前 25 名的題；分類別各算一份，表格最後一列是 all
  - 報告寫 reports/<時間>-<名稱>.json，帶設定、總表、分類別、每題名次與回傳的 message_id

hermetic：假的 search_chat，不碰模型與資料庫。

執行：
    cd src && python -m unittest test.test_chat_retrieval_eval -v
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from llm.retrievers.eval import evaluate as ev  # noqa: E402


def row(mid, text, author, dist=0.1, channel="c1"):
    return {"message_id": mid, "text": text, "author_id": author, "distance": dist, "timestamp": "t", "channel_id": channel,
            "repeat_count": 1}


class RankTests(unittest.TestCase):
    def test_relevant_ids_match_with_or_without_the_chat_prefix(self):
        rows = [row("10", "a", "A"), row("11", "b", "B")]
        self.assertEqual(ev.rank_of(rows, {"relevant": ["chat:11"]}), 2)
        self.assertEqual(ev.rank_of(rows, {"relevant": ["10"]}), 1)
        self.assertIsNone(ev.rank_of(rows, {"relevant": ["chat:99"]}))

    def test_phrase_questions_need_the_same_author_and_ignore_punctuation(self):
        rows = [row("1", "好了啦～ 又在裝", "B"), row("2", "好 了 啦！", "A"), row("3", "好了", "A")]
        self.assertEqual(ev.rank_of(rows, {"author": "A", "phrase": "好了啦"}), 2)   # 第 1 則作者不對
        self.assertIsNone(ev.rank_of(rows, {"author": "C", "phrase": "好了啦"}))
        self.assertIsNone(ev.rank_of(rows, {"author": "A", "phrase": ""}))           # 空句子不算全對


class QuestionFileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def _write(self, questions):
        path = self.tmp / "q.json"
        path.write_text(json.dumps({"questions": questions}, ensure_ascii=False), encoding="utf-8")
        return path

    def test_both_answer_forms_load_and_a_question_without_an_answer_is_rejected(self):
        ok = self._write([{"qid": "a01", "question": "x", "category": "A", "relevant": ["chat:1"]},
                          {"qid": "c01", "question": "y", "category": "C", "author": "A", "phrase": "好了啦"}])
        self.assertEqual([q["qid"] for q in ev.load_questions(ok)], ["a01", "c01"])
        bad = self._write([{"qid": "b01", "question": "z", "category": "B"}])
        with self.assertRaises(ValueError):
            ev.load_questions(bad)


class EvaluateTests(unittest.TestCase):
    QUESTIONS = [
        {"qid": "a01", "question": "誰不喝水", "category": "A", "relevant": ["chat:2"]},
        {"qid": "c01", "question": "誰常說好了啦", "category": "C", "author": "A", "phrase": "好了啦"},
        {"qid": "c02", "question": "誰常說發財", "category": "C", "author": "A", "phrase": "發財"},
    ]

    def _run(self, **kwargs):
        calls = []

        def fake_search(**kw):
            calls.append(kw)
            return [row("1", "我幾乎不喝水", "B", 0.2), row("2", "好了啦", "A", 0.3)]

        with mock.patch.object(ev.context_retriever, "search_chat", side_effect=fake_search):
            results = ev.evaluate(self.QUESTIONS, embeddings={"a01": [0.1], "c01": [0.2], "c02": [0.3]}, **kwargs)
        return results, calls

    def test_each_question_runs_one_full_corpus_search_with_its_precomputed_vector(self):
        results, calls = self._run(limit=7)
        self.assertEqual(len(calls), 3)
        first = calls[0]
        self.assertEqual(first["query_embedding"], [0.1])
        self.assertTrue(first["return_meta"])
        self.assertFalse(first["collapse"])                    # 預設量檢索本身，不折
        self.assertEqual(first["limit"], 7)
        self.assertNotIn("channel_id", first)                  # 全庫、不限頻道
        self.assertEqual([r.rank for r in results], [2, 2, None])
        self.assertEqual(results[0].returned, ["1", "2"])

    def test_summary_counts_hits_and_reports_the_median_rank_per_category(self):
        results, _ = self._run()
        total = ev.summarize(results)
        self.assertEqual((total["n"], total["hit@1"], total["hit@5"], total["hit@25"]), (3, 0, 2, 2))
        self.assertEqual(total["median_rank"], 2)
        per = ev.by_category(results)
        self.assertEqual(per["C"]["hit@5"], 1)
        self.assertEqual(ev.summarize([])["median_rank"], None)
        table = ev.format_table(results)
        self.assertIn("all", table.splitlines()[-1])

    def test_hit_at_k_counts_a_rank_equal_to_k(self):
        """Hit@5 的第 5 名算命中：邊界用 <=，不是 <。"""
        results = [ev.QuestionResult(qid=str(i), question="q", category="A", rank=r, returned=[], elapsed_ms=1.0)
                   for i, r in enumerate([1, 5, 25, None])]
        s = ev.summarize(results)
        self.assertEqual((s["hit@1"], s["hit@5"], s["hit@25"]), (1, 2, 3))
        self.assertEqual(s["median_rank"], 5)

    def test_report_is_written_under_reports_with_the_label_in_the_name(self):
        results, _ = self._run()
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        with mock.patch.object(ev, "REPORTS_DIR", tmp / "reports"):
            path = ev.write_report(results, label="基準線", settings={"limit": 25})
        self.assertTrue(path.name.endswith("-基準線.json"))
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload["settings"], {"limit": 25})
        self.assertEqual(payload["summary"]["hit@5"], 2)
        self.assertEqual(payload["by_category"]["A"]["n"], 1)
        self.assertEqual(payload["questions"][0]["qid"], "a01")


if __name__ == "__main__":
    unittest.main()
