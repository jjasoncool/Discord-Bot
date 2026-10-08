"""批次算向量（`services/search/embed.py`）：哪些文件要算、怎麼增量、怎麼讓路給 bot。

守的底線：
  - 只做指定日期之後的文件、新的先做；巴哈只做攻略、心得、情報、問題四類（回覆樓層照討論串標題判斷）
  - 內容沒變的段落不重算；改過的只重算改到的段；文件改短時刪掉多出來的舊段（只刪結尾、前面沒變也要刪）
  - 試算模式不呼叫 embedding
  - 補算（手動指令與每日維護共用的 `embed_pending`）先跟上 scraper 的新文章再算
  （和 bot 排隊用 GPU 閘門，在 `vectors.Embedder` 裡，見 test_search_vectors）

執行：
    cd src && python -m unittest test.test_search_embed -v
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from services.search.embed import embed_pending, plan, run  # noqa: E402
from test.test_search_index import SearchIndexTestBase  # noqa: E402


class FakeStore:
    def __init__(self):
        self.rows = {}           # chunk_id → (doc_id, text_hash)
        self.deleted = []

    def existing_chunks(self, doc_ids):
        found = {}
        for cid, (doc_id, text_hash) in self.rows.items():
            if doc_id in doc_ids:
                found.setdefault(doc_id, {})[cid] = text_hash
        return found

    def upsert(self, rows):
        for chunk_id, doc_id, _source, _published, text_hash, _vector in rows:
            self.rows[chunk_id] = (doc_id, text_hash)

    def delete_stale(self, doc_id, keep):
        for cid in [c for c, (d, _) in self.rows.items() if d == doc_id and c not in keep]:
            del self.rows[cid]
            self.deleted.append(cid)


class FakeEmbedder:
    def __init__(self):
        self.calls = []

    def embed_documents(self, texts):
        self.calls.append(list(texts))
        return [[float(len(t))] for t in texts]


class EmbedTests(SearchIndexTestBase):
    def build(self):
        index = self.make_index()
        index.sync()
        return index

    def test_plan_takes_recent_documents_and_only_some_bahamut_threads(self):
        self.db.ptt("M.1.A.001", "[鳴潮] 新文", "今年的內容", published="2026-03-01 10:00:00.000000")
        self.db.ptt("M.1.A.002", "[鳴潮] 舊文", "去年的內容", published="2025-03-01 10:00:00.000000")
        self.db.floor("10", 1, "500", "攻略主文", title="【攻略】景燃養成", published="2026-04-01 10:00:00.000000")
        self.db.floor("10", 2, "501", "回覆樓層", published="2026-04-02 10:00:00.000000")
        self.db.floor("11", 1, "600", "閒聊內容", title="【閒聊】今天好熱", published="2026-05-01 10:00:00.000000")
        index = self.build()

        planned = plan(index.index_path, since="2026-01-01")

        self.assertEqual([d.doc_id for d in planned], ["bahamut:501", "bahamut:500", "ptt:M.1.A.001"])
        # 回覆樓層的段落帶討論串標題（索引裡的標題已正規化，全形括號會變半形）
        self.assertTrue(planned[0].chunks[0].text.startswith("【攻略】景燃養成"))
        self.assertIn("2 樓", planned[0].chunks[0].text.split("\n", 1)[0])

    def test_second_run_only_recomputes_what_changed(self):
        self.db.ptt("M.1.A.001", "[鳴潮] 文", "第一段內容", published="2026-03-01 10:00:00.000000")
        self.db.ptt("M.1.A.002", "[鳴潮] 文二", "不會變的內容", published="2026-03-02 10:00:00.000000")
        index = self.build()
        store, embedder = FakeStore(), FakeEmbedder()
        run(plan(index.index_path, since="2026-01-01"), store, embedder, batch_size=8)

        again = run(plan(index.index_path, since="2026-01-01"), store, embedder, batch_size=8)
        self.assertEqual((again.embedded, again.skipped), (0, 2))

        self.db.update("UPDATE ptt_posts SET content=?, updated_at=? WHERE article_id='M.1.A.001'", "改過的內容",
                       self.db.tick())
        index.sync()
        changed = run(plan(index.index_path, since="2026-01-01"), store, embedder, batch_size=8)
        self.assertEqual((changed.embedded, changed.skipped), (1, 1))
        self.assertEqual(embedder.calls[-1][0].split("\n", 1)[1], "改過的內容")

    def test_shrunk_document_loses_its_extra_chunks(self):
        self.db.ptt("M.1.A.001", "[鳴潮] 長文", "\n".join(f"第{i}段" + "字" * 90 for i in range(8)),
                    published="2026-03-01 10:00:00.000000")
        index = self.build()
        store = FakeStore()
        run(plan(index.index_path, since="2026-01-01", max_chars=200, overlap=20), store, FakeEmbedder())
        self.assertGreater(len(store.rows), 2)

        self.db.update("UPDATE ptt_posts SET content=?, updated_at=? WHERE article_id='M.1.A.001'", "只剩一句",
                       self.db.tick())
        index.sync()
        run(plan(index.index_path, since="2026-01-01", max_chars=200, overlap=20), store, FakeEmbedder())

        self.assertEqual(list(store.rows), ["ptt:M.1.A.001#0"])

    def test_cutting_only_the_ending_still_removes_the_extra_chunk(self):
        # 三段各約 240 字切成 3 段；刪掉最後一段後切成 2 段，而且這 2 段和原本的前兩段一字不差
        paragraphs = ["".join(chr(0x4E00 + i * 300 + j) for j in range(240)) for i in range(4)]
        self.db.ptt("M.1.A.001", "[鳴潮] 長文", "\n".join(paragraphs), published="2026-03-01 10:00:00.000000")
        index = self.build()
        store, embedder = FakeStore(), FakeEmbedder()
        run(plan(index.index_path, since="2026-01-01", max_chars=500, overlap=80), store, embedder)
        before = sorted(store.rows)

        self.db.update("UPDATE ptt_posts SET content=?, updated_at=? WHERE article_id='M.1.A.001'",
                       "\n".join(paragraphs[:3]), self.db.tick())
        index.sync()
        report = run(plan(index.index_path, since="2026-01-01", max_chars=500, overlap=80), store, embedder)

        self.assertEqual(report.embedded, 0)            # 留下的段落一字不差，不必重算
        self.assertEqual(report.removed, len(before) - len(store.rows))
        self.assertLess(len(store.rows), len(before))
        self.assertNotIn(before[-1], store.rows)        # 含被刪內容的最後一段要清掉

    def test_dry_run_never_calls_the_embedder(self):
        self.db.ptt("M.1.A.001", "[鳴潮] 文", "內容", published="2026-03-01 10:00:00.000000")
        index = self.build()
        embedder = FakeEmbedder()

        report = run(plan(index.index_path, since="2026-01-01"), FakeStore(), embedder, dry_run=True)

        self.assertEqual(embedder.calls, [])
        self.assertEqual((report.docs, report.chunks, report.embedded), (1, 1, 0))
        self.assertGreater(report.chars, 0)

    def test_embed_pending_catches_up_on_articles_added_after_the_last_sync(self):
        self.db.ptt("M.1.A.001", "[鳴潮] 舊文", "內容", published="2026-03-01 10:00:00.000000")
        # 常駐服務的索引剛因為有人搜尋同步過（還在最短間隔內），補算時照樣要跟上
        index = self.make_index(sync_min_interval_seconds=3600)
        index.sync()
        self.db.ptt("M.1.A.002", "[鳴潮] 新文", "剛爬到的內容", published="2026-03-02 10:00:00.000000")
        store = FakeStore()
        store.embedder = FakeEmbedder()

        report = embed_pending(index, store, since="2026-01-01")

        self.assertEqual({doc_id for doc_id, _ in store.rows.values()}, {"ptt:M.1.A.001", "ptt:M.1.A.002"})
        self.assertEqual(report.embedded, 2)


if __name__ == "__main__":
    unittest.main()
