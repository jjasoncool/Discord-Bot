"""pgvector 那一路（`services/search/vectors.py`）：不連真的資料庫，用假連線檢查查詢與門檻。

守的底線：
  - 查詢帶上來源與日期篩選、照距離排序、限制筆數；HNSW 的搜尋寬度跟著要的筆數放大
  - 同一篇多段只留距離最近的那段，順序照最近的距離
  - 門檻：距離超過的段落不算；沒設門檻全部照收
  - 查詢前面加任務說明，文件本身不加

執行：
    cd src && python -m unittest test.test_search_vectors -v
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from services.search.vectors import Embedder, PgVectorStore  # noqa: E402


class FakeCursor:
    def __init__(self, con):
        self.con = con

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        self.con.executed.append((" ".join(sql.split()), params))

    def fetchall(self):
        return self.con.rows


class FakeConnection:
    def __init__(self, rows):
        self.rows, self.executed = rows, []

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


class FakeEmbedder:
    def embed_query(self, text, max_wait_seconds=None):
        self.last_query, self.last_wait = text, max_wait_seconds
        return [0.1, 0.2]


class PgVectorStoreTests(unittest.TestCase):
    def make_store(self, rows):
        self.con = FakeConnection(rows)
        return PgVectorStore(embedder=FakeEmbedder(), dim=2, connect=lambda: self.con)

    def test_query_filters_by_source_and_date_and_orders_by_distance(self):
        store = self.make_store([])
        store.search("深塔", sources=["ptt", "bahamut"], start="2026-01-01", end="2026-04-01", k=60)

        sql, params = self.con.executed[-1]
        self.assertIn("source = ANY(%s)", sql)
        self.assertIn("ORDER BY distance LIMIT %s", sql)
        self.assertEqual(params[1:], (["ptt", "bahamut"], "2026-01-01", "2026-04-01", 60))
        self.assertIn(("SET LOCAL hnsw.ef_search = %s", (120,)), self.con.executed)

    def test_search_passes_the_wait_limit_to_the_query_embedding(self):
        store = self.make_store([])
        store.search("深塔", sources=["ptt"], start="", end="9", k=10, max_wait_seconds=3)

        self.assertEqual(store.embedder.last_wait, 3)

    def test_one_document_keeps_its_closest_chunk(self):
        store = self.make_store([("ptt:a", 0.20), ("bahamut:1", 0.30), ("ptt:a", 0.35), ("fb:9", 0.60)])

        self.assertEqual(store.search_with_distances("q", sources=["ptt"], start="", end="9", k=10),
                         [("ptt:a", 0.20), ("bahamut:1", 0.30), ("fb:9", 0.60)])

    def test_threshold_drops_distant_chunks(self):
        store = self.make_store([("ptt:a", 0.20), ("bahamut:1", 0.30), ("fb:9", 0.60)])

        self.assertEqual(store.search("q", sources=["ptt"], start="", end="9", k=10, max_distance=0.5),
                         ["ptt:a", "bahamut:1"])
        self.assertEqual(store.search("q", sources=["ptt"], start="", end="9", k=10),
                         ["ptt:a", "bahamut:1", "fb:9"])


class EmbedderTests(unittest.TestCase):
    def test_only_queries_get_the_task_instruction(self):
        class Client:
            def get_text_embedding(self, text):
                self.query = text
                return [0.0]

            def get_text_embedding_batch(self, texts):
                self.docs = texts
                return [[0.0] for _ in texts]

        entered = []

        class Gate:
            def __init__(self, max_wait_seconds=None):
                waits.append(max_wait_seconds)

            def __enter__(self):
                entered.append("進")

            def __exit__(self, *exc):
                entered.append("出")

        waits = []

        embedder = Embedder(query_instruction="找答案", gate=Gate)
        client = Client()
        embedder._model = client

        embedder.embed_query("深塔多久重置")
        embedder.embed_documents(["深塔每兩週重置"])
        embedder.embed_query("深塔多久重置", max_wait_seconds=4)   # 搜尋給的剩餘額度

        self.assertEqual(client.query, "Instruct: 找答案\nQuery:深塔多久重置")
        self.assertEqual(client.docs, ["深塔每兩週重置"])
        # 都經過 GPU 閘門（和 bot 的串流排同一個隊）；問句等不起、有上限，文件批次照預設一直等
        self.assertEqual(entered, ["進", "出"] * 3)
        self.assertEqual(waits, [embedder.query_gpu_wait_seconds, None, 4])
        self.assertIsNotNone(embedder.query_gpu_wait_seconds)

    def test_closest_chunk_wins_even_when_rows_come_back_out_of_order(self):
        # iterative_scan 可能讓較遠的段先回來：每篇仍要記最近那段的距離，門檻才不會誤濾
        con = FakeConnection([("ptt:a", 0.50), ("bahamut:1", 0.30), ("ptt:a", 0.20)])
        store = PgVectorStore(embedder=FakeEmbedder(), dim=2, connect=lambda: con)

        self.assertEqual(store.search_with_distances("q", sources=["ptt"], start="", end="9", k=10),
                         [("ptt:a", 0.20), ("bahamut:1", 0.30)])
        self.assertEqual(store.search("q", sources=["ptt"], start="", end="9", k=10, max_distance=0.4),
                         ["ptt:a", "bahamut:1"])


if __name__ == "__main__":
    unittest.main()
