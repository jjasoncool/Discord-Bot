"""重新排序（`services/search/rerank.py` 與 `SearchIndex._rerank`）：reranker 把前幾十篇重新排過。

守的底線：
  - 前 N 篇照 reranker 的分數重排，第 N 篇之後照原本的名次接在後面；同分照原本的名次
  - 重排在「每種來源最多幾筆」之前：先決定誰最相關，再套上限
  - reranker 壞掉、GPU 等太久、回傳筆數不對、開關關著：都照原本的名次，搜尋不能失敗
  - 每篇送給 reranker 的是標題＋和問題最相關的那一段，不是整篇
  - 呼叫端給了使用者的原句，reranker 讀原句（它是拿自然語言問句訓練的）；挑段落還是看查詢字
  - 打 reranker 要排 GPU 的隊，而且有等待上限；沒設定模型時不打
  - 一次搜尋共用一個等 GPU 的額度：向量那步等不到 GPU，重排就不再等（不呼叫 reranker）；
    向量那步花掉的時間從額度扣；向量是別的原因壞掉（pgvector 連不上）不影響重排
  - 後端回的分數依 index 放回原位（後端回傳的是依分數排好的）

執行：
    cd src && python -m unittest test.test_search_rerank -v
"""

import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from llm.client.http_client import LlmHttpClient  # noqa: E402
from services.search.rerank import HttpReranker, best_passage  # noqa: E402
from services.search.text import normalize  # noqa: E402
from llm.client.gpu_gate import GpuBusy  # noqa: E402
from test.test_search_index import SearchIndexTestBase, StubVectorStore  # noqa: E402


class StubReranker:
    """依段落裡有沒有指定的字給分；`error` 給了就丟出來；記下收到的問題與段落。"""

    def __init__(self, favourite="", error=None, wrong_count=False):
        self.favourite, self.error, self.wrong_count, self.calls = favourite, error, wrong_count, []
        self.queries, self.waits = [], []

    def rerank(self, query, passages, max_wait_seconds=None):
        self.queries.append(query)
        self.waits.append(max_wait_seconds)
        self.calls.append(list(passages))
        if self.error:
            raise self.error
        scores = [1.0 if self.favourite and self.favourite in p else 0.0 for p in passages]
        return scores[:-1] if self.wrong_count else scores


class RerankInSearchTests(SearchIndexTestBase):
    def setUp(self):
        super().setUp()
        # 關鍵字排名：001（標題、內文都有，最多次）> 002 > 003；只有 003 真的回答了「每兩週」
        self.db.ptt("M.1.A.001", "[鳴潮] 深塔海墟", "深塔海墟深塔海墟深塔海墟，閒聊")
        self.db.ptt("M.1.A.002", "[鳴潮] 心得", "深塔海墟好難打")
        self.db.ptt("M.1.A.003", "[鳴潮] 整理", "深塔海墟每兩週重置一次")

    def test_reranker_moves_the_real_answer_up(self):
        plain = self.ids(self.make_index().search("深塔海墟"))
        reranked = self.ids(self.make_index(reranker=StubReranker("每兩週")).search("深塔海墟"))

        self.assertNotEqual(plain[0], "ptt:M.1.A.003")
        self.assertEqual(reranked[0], "ptt:M.1.A.003")
        self.assertEqual(reranked[1:], [d for d in plain if d != "ptt:M.1.A.003"])   # 同分照原本的名次

    def test_only_the_first_candidates_are_reranked(self):
        index = self.make_index(reranker=StubReranker("每兩週"))
        index.rerank_candidates = 2

        ids = self.ids(index.search("深塔海墟"))

        self.assertEqual(len(index.reranker.calls[0]), 2)
        self.assertEqual(ids[-1], "ptt:M.1.A.003")   # 在前 2 篇之外，不參加重排

    def test_failures_and_switch_off_keep_the_original_order(self):
        plain = self.ids(self.make_index().search("深塔海墟"))
        for name, kwargs in (
            ("出錯", {"reranker": StubReranker("每兩週", error=TimeoutError("GPU 等太久"))}),
            ("筆數不對", {"reranker": StubReranker("每兩週", wrong_count=True)}),
        ):
            with self.subTest(name), self.assertLogs("services.search.index", level="WARNING"):
                self.assertEqual(self.ids(self.make_index(**kwargs).search("深塔海墟")), plain)
        off = StubReranker("每兩週")
        self.assertEqual(self.ids(self.make_index(reranker=off, rerank_enabled=lambda: False).search("深塔海墟")), plain)
        self.assertEqual(off.calls, [])

    def test_rerank_happens_before_the_per_source_cap(self):
        index = self.make_index(reranker=StubReranker("每兩週"), per_source_limit=1)

        self.assertEqual(self.ids(index.search("深塔海墟")), ["ptt:M.1.A.003"])

    def test_passages_are_title_plus_the_most_relevant_part(self):
        long_body = "\n".join(["版本更新的其他說明。" * 30, "深塔海墟每兩週重置一次", "其他無關內容。" * 30])
        self.db.article(1, "3.7 版本說明", f"<p>{long_body}</p>")
        stub = StubReranker()
        self.make_index(reranker=stub).search("深塔海墟 重置")

        passage = next(p for p in stub.calls[0] if p.startswith("3.7 版本說明"))
        self.assertIn("深塔海墟每兩週重置一次", passage)
        self.assertLessEqual(len(passage), 500 + len("3.7 版本說明\n"))


    def test_reranker_reads_the_original_question_but_passages_follow_the_query(self):
        # 切成兩段：第一段全是「版本更新的其他說明」，第二段才有答案
        long_body = "\n".join(["版本更新的其他說明。" * 49, "深塔海墟每兩週重置一次。" + "其他無關內容。" * 30])
        self.db.article(1, "3.7 版本說明", f"<p>{long_body}</p>")
        stub = StubReranker()
        # 原句和第一段重疊的兩字組比較多：挑段落若改看原句，會把沒有答案的那段送去重排
        question = "請問多久一次？版本更新的其他說明裡有寫嗎"
        self.make_index(reranker=stub).search("深塔海墟 重置", question=question)

        self.assertEqual(stub.queries, [normalize(question)])
        passage = next(p for p in stub.calls[0] if p.startswith("3.7 版本說明"))
        self.assertIn("深塔海墟每兩週重置一次", passage)

    def test_blank_question_falls_back_to_the_query(self):
        stub = StubReranker()
        self.make_index(reranker=stub).search("深塔海墟", question="  ")

        self.assertEqual(stub.queries, [normalize("深塔海墟")])


class GpuBudgetTests(SearchIndexTestBase):
    """問句向量與重排共用一次搜尋的等 GPU 額度（10-08 實測：bot 插話時兩步各等 10 秒，白等 20 秒）。"""

    def setUp(self):
        super().setUp()
        self.db.ptt("M.1.A.001", "[鳴潮] 深塔海墟", "深塔海墟深塔海墟，閒聊")
        self.db.ptt("M.1.A.002", "[鳴潮] 整理", "深塔海墟每兩週重置一次")

    def test_gpu_busy_for_vectors_skips_rerank_without_waiting_again(self):
        stub = StubReranker("每兩週")
        index = self.make_index(vector_store=StubVectorStore(error=GpuBusy("GPU 被別的工作佔著")), reranker=stub)
        plain = self.ids(self.make_index().search("深塔海墟"))

        with self.assertLogs("services.search.index", level="INFO"):
            self.assertEqual(self.ids(index.search("深塔海墟")), plain)
        self.assertEqual(stub.calls, [])

    def test_time_spent_on_vectors_comes_out_of_the_rerank_budget(self):
        stub = StubReranker("每兩週")
        index = self.make_index(vector_store=StubVectorStore(delay=0.3), reranker=stub, gpu_wait_seconds=1.0)

        index.search("深塔海墟")

        self.assertEqual(index.vector_store.calls[0]["max_wait_seconds"], 1.0)
        self.assertGreater(stub.waits[0], 0)
        self.assertLess(stub.waits[0], 0.75)

    def test_budget_used_up_by_vectors_skips_rerank(self):
        stub = StubReranker("每兩週")
        index = self.make_index(vector_store=StubVectorStore(delay=0.3), reranker=stub, gpu_wait_seconds=0.2)

        index.search("深塔海墟")

        self.assertEqual(stub.calls, [])

    def test_other_vector_failures_leave_the_budget_for_rerank(self):
        stub = StubReranker("每兩週")
        index = self.make_index(vector_store=StubVectorStore(error=ConnectionError("pgvector 連不上")),
                                reranker=stub, gpu_wait_seconds=1.0)

        with self.assertLogs("services.search.index", level="WARNING"):
            ids = self.ids(index.search("深塔海墟"))

        self.assertEqual(ids[0], "ptt:M.1.A.002")
        self.assertGreater(stub.waits[0], 0.9)


class BestPassageTests(unittest.TestCase):
    def test_short_document_is_sent_whole_and_long_one_sends_the_overlapping_chunk(self):
        self.assertEqual(best_passage("深塔", "標題\n深塔每兩週重置", 500), "標題\n深塔每兩週重置")
        text = "標題\n" + "\n".join(["無關的段落內容。" * 40, "卜靈是夢州方士、黑海岸客卿", "另一段無關內容。" * 40])
        self.assertIn("卜靈是夢州方士", best_passage("卜靈是什麼身分", text, 200))


class HttpRerankerTests(unittest.TestCase):
    def test_goes_through_the_gpu_gate_with_a_wait_limit(self):
        waits, client = [], mock.Mock()
        client.rerank.return_value = [0.9, 0.1]

        class Gate:
            def __init__(self, max_wait_seconds=None):
                waits.append(max_wait_seconds)

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        reranker = HttpReranker(client=client, gate=Gate, max_wait_seconds=7, model="reranker-x")

        self.assertEqual(reranker.rerank("問題", ["甲", "乙"]), [0.9, 0.1])
        reranker.rerank("問題", ["甲", "乙"], max_wait_seconds=3)   # 這次搜尋剩下的額度
        self.assertEqual(waits, [7, 3])
        self.assertEqual(client.rerank.call_count, 2)
        client.rerank.assert_called_with(model="reranker-x", query="問題", documents=["甲", "乙"])

    def test_without_a_model_it_refuses_instead_of_calling_the_backend(self):
        client = mock.Mock()
        reranker = HttpReranker(client=client, gate=mock.MagicMock())
        runtime = mock.Mock(rerank_model=None, backend="lemonade", backends={})
        with mock.patch.object(HttpReranker, "_settings", return_value=(mock.Mock(), runtime)):
            with self.assertRaises(RuntimeError):
                reranker.rerank("問題", ["甲"])
        client.rerank.assert_not_called()


class HttpClientRerankTests(unittest.TestCase):
    def test_scores_are_put_back_in_document_order(self):
        client = LlmHttpClient(base_url="http://example.invalid", timeout=1)
        # 後端依分數排好回傳；漏掉的文件給負無限大
        response = {"results": [{"index": 2, "relevance_score": 0.9}, {"index": 0, "relevance_score": 0.3}]}
        with mock.patch.object(client, "_post_json", return_value=response) as post:
            scores = client.rerank(model="m", query="q", documents=["a", "b", "c"])

        self.assertEqual(scores[0], 0.3)
        self.assertEqual(scores[2], 0.9)
        self.assertEqual(scores[1], float("-inf"))
        self.assertEqual(post.call_args[0][0], "/rerank")
        self.assertEqual(post.call_args[0][1]["top_n"], 3)
        client.close()


if __name__ == "__main__":
    unittest.main()
