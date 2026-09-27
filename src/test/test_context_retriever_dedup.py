"""member_profile 召回的去重：同一份文件被 SQL 與語意檢索各撈到一次，卡片裡只能出現一次。

實際發生過：語意檢索回來的 node.metadata 不含 ref_doc_id，去重鍵退回文字雜湊，跟 SQL 那筆
對不上——同一則印象在卡片裡出現兩次，那一行因此超過上限（persona agent 精簡版的預算也就
算不準）。hermetic：假的 DB 連線與向量索引，不碰 DB／embedding。

執行：
    cd src && python -m unittest test.test_context_retriever_dedup -v
"""

import contextlib
import logging
import os
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from llm import context_retriever as cr  # noqa: E402

DOC_ID = "impression:9:2:1"
MD = {"doc_type": "member_profile", "profile_kind": "impression", "guild_id": "9",
      "author_id": "2", "target_user_id": "1", "target_alias": "米拉"}
TEXT = ("[Member Impression]\ntarget_user_id: 1\ntarget_alias: 米拉\n"
        "target_habit: -\nimpression: 很會吐槽")


class _Cursor:
    def execute(self, *args, **kwargs):
        pass

    def fetchall(self):
        # SQL 撈到的 metadata_ 帶著 LlamaIndex 寫入的 ref_doc_id／doc_id／document_id
        return [(1, TEXT, {**MD, "ref_doc_id": DOC_ID, "doc_id": DOC_ID, "document_id": DOC_ID})]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _Conn(_Cursor):
    def cursor(self):
        return _Cursor()


def _vector_index():
    from llama_index.core.schema import NodeRelationship, NodeWithScore, RelatedNodeInfo, TextNode

    # 語意檢索回來的 node：metadata 裡沒有 ref_doc_id，它在 node 的 SOURCE 關係上
    node = TextNode(text=TEXT, metadata=dict(MD),
                    relationships={NodeRelationship.SOURCE: RelatedNodeInfo(node_id=DOC_ID)})
    retriever = SimpleNamespace(retrieve=lambda question: [NodeWithScore(node=node, score=0.9)])
    return SimpleNamespace(as_retriever=lambda **kwargs: retriever)


@unittest.skipIf(cr.psycopg2 is None or cr.VectorStoreIndex is None, "需要 psycopg2 與 llama_index")
class ProfileDedupTests(unittest.TestCase):

    @staticmethod
    @contextlib.contextmanager
    def _fakes():
        settings = SimpleNamespace(
            get_source=lambda name: SimpleNamespace(table_name="member_profiles"),
            physical_table=lambda table: f"data_{table}",
            hybrid_candidate_pool=10,
        )
        with mock.patch.object(cr, "HYBRID_RETRIEVAL_SETTINGS", settings), \
             mock.patch.object(cr, "_pgvector_connect", lambda: _Conn()), \
             mock.patch.object(cr, "_get_or_build_vector_index", lambda *a: _vector_index()):
            yield

    def test_same_doc_from_sql_and_vector_appears_once(self):
        with self._fakes():
            context, meta = cr.retrieve_rag_context_sync(
                "米拉是怎樣的人", 9, None, [1], logging.getLogger("test"), 5)

        self.assertGreater(meta["vector_hits"], 0, "語意檢索那一路要真的有撈到")
        self.assertEqual(meta["dedup_hits"], 1)
        card = next(c["content"] for c in context if c.get("person_id") == "1")
        self.assertEqual(card.count("很會吐槽"), 1)

    def test_participant_copy_beats_vector_copy(self):
        """兩路都撈到時留 SQL 那筆：卡片的來源加分是 sql_participant 24、vector 10，
        留錯的話在場的人反而排到後面。問句「嗨」不觸發別名那一路，只剩在場者 SQL 與語意檢索。"""
        captured = {}
        real = cr.build_persona_cards

        def spy(**kwargs):
            captured["docs"] = kwargs["docs"]
            return real(**kwargs)

        with self._fakes(), mock.patch.object(cr, "build_persona_cards", spy):
            cr.retrieve_rag_context_sync("嗨", 9, None, [1], logging.getLogger("test"), 5)
        self.assertEqual([d["source"] for d in captured["docs"]], ["sql_participant"])


if __name__ == "__main__":
    unittest.main()
