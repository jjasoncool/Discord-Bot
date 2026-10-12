"""搜尋評估（`services/search/eval/evaluate.py`）：Hit Rate@k 與 MRR@10 的算法。

守的底線：
  - 名次是「第一篇正確答案」的位置；考卷裡任何一篇正確答案都算，「只答一半」的不算
  - Hit@k＝前 k 名有正確答案的題目比例；MRR@10＝名次倒數的平均，前 10 名以外與沒找到都算 0
  - 排名看搜尋實際回傳的那一串（含來源上限），查詢字是群友原句
  - 關鍵字模式也把原句交給重新排序（模擬 MCP 客戶端拆關鍵字時附上使用者原句）
  - 只考使用者確認過的題目

執行：
    cd src && python -m unittest test.test_search_eval -v
"""

import json
import math
import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from services.search.eval.evaluate import (  # noqa: E402
    QuestionResult,
    evaluate,
    first_relevant_rank,
    load_questions,
    ndcg_at,
    recall_at,
    split_questions,
    summarize,
)
from test.test_search_index import SearchIndexTestBase  # noqa: E402


def _result(rank, category="情報"):
    return QuestionResult(qid="q", question="?", query="?", category=category, origin="ptt", type="字面",
                          rank=rank, vector_covered=None, returned=[], relevant=[], elapsed_ms=1.0)


class MetricTests(unittest.TestCase):
    def test_rank_is_the_first_relevant_document(self):
        self.assertEqual(first_relevant_rank(["a", "b", "c", "d"], ["d", "b"]), 2)
        self.assertIsNone(first_relevant_rank(["a", "b"], ["x"]))

    def test_hit_rate_and_mrr(self):
        # 名次 1、3、沒找到、12（前 10 名外）
        s = summarize([_result(1), _result(3), _result(None), _result(12)])

        self.assertEqual(s["n"], 4)
        self.assertAlmostEqual(s["hit@1"], 1 / 4)
        self.assertAlmostEqual(s["hit@5"], 2 / 4)
        self.assertAlmostEqual(s["hit@10"], 2 / 4)
        self.assertAlmostEqual(s["mrr@10"], (1 + 1 / 3) / 4)

    def test_recall_and_ndcg(self):
        # 正確答案 a、b、c；前 10 名裡有 a（第 1）與 c（第 3）
        returned, relevant = ["a", "x", "c", "y"], ["a", "b", "c"]
        self.assertAlmostEqual(recall_at(returned, relevant), 2 / 3)
        ideal = 1 + 1 / math.log2(3) + 1 / math.log2(4)
        self.assertAlmostEqual(ndcg_at(returned, relevant), (1 + 1 / math.log2(4)) / ideal)
        self.assertAlmostEqual(ndcg_at(["a", "b", "c"], relevant), 1.0)   # 全部排在最前面＝1
        self.assertEqual(recall_at(["x"], []), 0.0)
        beyond = [f"x{i}" for i in range(10)] + ["a"]   # 正確答案排第 11 名：不算找回
        self.assertEqual(recall_at(beyond, ["a"]), 0.0)
        self.assertEqual(ndcg_at(beyond, ["a"]), 0.0)

    def test_ndcg_rewards_relevant_documents_beyond_the_first(self):
        # 兩份結果第一篇正確答案都排第 1（MRR 一樣），但其中一份把其他正確答案也排在前面
        relevant = ["a", "b"]
        self.assertGreater(ndcg_at(["a", "b", "x"], relevant), ndcg_at(["a", "x", "b"], relevant))

    def test_empty_set_does_not_divide_by_zero(self):
        self.assertEqual(summarize([])["mrr@10"], 0.0)


class SplitTests(unittest.TestCase):
    def test_halves_are_disjoint_cover_everything_and_keep_category_balance(self):
        questions = ([{"qid": f"q{i:02d}", "category": "情報"} for i in range(1, 11)]
                     + [{"qid": f"q{i:02d}", "category": "攻略-配隊"} for i in range(11, 15)])
        a, b = split_questions(questions, "A"), split_questions(questions, "B")

        self.assertEqual({q["qid"] for q in a} & {q["qid"] for q in b}, set())
        self.assertEqual(len(a) + len(b), len(questions))
        self.assertEqual(sum(q["category"] == "攻略-配隊" for q in a), 2)
        self.assertEqual(split_questions(questions, "A"), a)   # 固定拆法，每次一樣
        self.assertEqual(split_questions(questions, "全部"), questions)


class EvaluateTests(SearchIndexTestBase):
    def test_partial_answers_do_not_count_and_raw_question_is_the_query(self):
        self.db.ptt("M.1.A.001", "[鳴潮] 只提一句", "深塔海墟要重置了")
        self.db.ptt("M.1.A.002", "[鳴潮] 重置時間整理", "深塔海墟每兩週一的四點重置")
        index = self.make_index()
        questions = [
            {"qid": "q01", "question": "深塔海墟多久重置", "relevant": ["ptt:M.1.A.002"], "partial": ["ptt:M.1.A.001"]},
            {"qid": "q02", "question": "完全無關的問題喔", "relevant": ["ptt:M.1.A.002"], "partial": []},
        ]

        results = {r.qid: r for r in evaluate(index, questions)}

        self.assertIsNotNone(results["q01"].rank)
        self.assertIn("ptt:M.1.A.002", results["q01"].returned)
        self.assertEqual(results["q01"].returned.index("ptt:M.1.A.002") + 1, results["q01"].rank)
        self.assertIsNone(results["q02"].rank)

    def test_keyword_mode_searches_the_rewritten_query(self):
        self.db.ptt("M.1.A.001", "[鳴潮] 坎特蕾拉主C聲骸", "坎特蕾拉主C用沉日劫明，首位夢魘無冠者")
        index = self.make_index()
        questions = [{"qid": "q01", "question": "家主當主C的話聲骸要穿哪套", "relevant": ["ptt:M.1.A.001"]}]

        original = evaluate(index, questions)[0]
        keyword = evaluate(index, questions, {"q01": "坎特蕾拉 主C 聲骸"})[0]

        self.assertEqual(original.query, "家主當主C的話聲骸要穿哪套")
        self.assertEqual(keyword.query, "坎特蕾拉 主C 聲骸")
        self.assertEqual(keyword.rank, 1)

    def test_keyword_mode_still_gives_the_reranker_the_original_question(self):
        from services.search.text import normalize
        from test.test_search_rerank import StubReranker

        self.db.ptt("M.1.A.001", "[鳴潮] 坎特蕾拉主C聲骸", "坎特蕾拉主C用沉日劫明")
        self.db.ptt("M.1.A.002", "[鳴潮] 坎特蕾拉聲骸心得", "坎特蕾拉聲骸怎麼配")
        stub = StubReranker()
        questions = [{"qid": "q01", "question": "家主當主C的話聲骸要穿哪套", "relevant": ["ptt:M.1.A.001"]}]

        evaluate(self.make_index(reranker=stub), questions, {"q01": "坎特蕾拉 聲骸"})

        self.assertEqual(stub.queries, [normalize("家主當主C的話聲骸要穿哪套")])

    def test_marks_whether_the_answer_has_vectors(self):
        self.db.ptt("M.1.A.001", "[鳴潮] 文", "深塔海墟每兩週重置")
        index = self.make_index()
        questions = [{"qid": "q01", "question": "深塔海墟", "relevant": ["ptt:M.1.A.001"]},
                     {"qid": "q02", "question": "深塔海墟", "relevant": ["ptt:M.9.A.999"]}]

        marked = {r.qid: r.vector_covered for r in evaluate(index, questions, embedded={"ptt:M.1.A.001"})}
        unmarked = evaluate(index, questions)

        self.assertEqual(marked, {"q01": True, "q02": False})
        self.assertIsNone(unmarked[0].vector_covered)

    def test_only_reviewed_questions_are_used(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "q.json"
            path.write_text(json.dumps({"questions": [
                {"qid": "q01", "question": "a", "relevant": [], "reviewed": True},
                {"qid": "q02", "question": "b", "relevant": [], "reviewed": False},
            ]}), encoding="utf-8")

            self.assertEqual([q["qid"] for q in load_questions(path)], ["q01"])


if __name__ == "__main__":
    unittest.main()
