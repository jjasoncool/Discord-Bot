"""聊天檢索的重複折疊、品質閘與 /askai 相關訊息的重排。

守的底線：
  - `search_chat`：同一人同一句（空白、標點不計）只回一則（名次與距離取最近那筆、代表取最新那則）並記 repeat_count；
    不同人的同一句各自保留；純標點不折；`min_chars` 擋在 SQL；折疊前多撈、折疊後才裁到 limit
  - /askai 視窗：同一人同一句只留最新的一則，關鍵字與向量兩路都吃折好的清單（兩路投同一則）
  - /askai 相關名額：純貼圖／純表情描述／純連結不佔名額、不同人說的同一句只留一則；保底的最近幾則不受影響
  - 有 reranker 時在 bot 的 GPU 閘門裡重排、照它的分數挑相關訊息、低於門檻的不進；閘門等不到、reranker 壞掉或回錯筆數
    就照融合名次
  - 品質閘認得寫進向量庫的格式（`:描述:`、`[貼圖：…]`）
  - 查詢前設 HNSW 的 ef_search 與 iterative_scan（索引建好才有作用，沒索引時無害）；全庫搜尋把 ef_search 開到上限 1000，窗內重排不用
  - 專用的聊天表不帶 doc_type 篩選（沒統計的 JSON 欄位會讓規劃器放著 HNSW 走全表掃描）；只有和別的來源共用一張表時才篩
  - 插話回憶把 min_chars 交給 search_chat，注入行尾標「同一人說過 N 次」

hermetic：假的連線、假的 embedding、假的 reranker，不碰模型與資料庫。

執行：
    cd src && python -m unittest test.test_rag_collapse -v
"""

import asyncio
import logging
import os
import sys
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from llm.preprocess import emoji_text_utils as etu  # noqa: E402
from llm.preprocess.tokenization import dedup_key  # noqa: E402
from llm.retrievers import context_retriever as cr  # noqa: E402

LOG = logging.getLogger(__name__)


class DedupKeyTests(unittest.TestCase):
    def test_same_words_with_different_punctuation_and_spacing_share_a_key(self):
        self.assertEqual(dedup_key("笑死！"), dedup_key("笑 死～"))
        self.assertEqual(dedup_key("LOL"), dedup_key("lol"))
        self.assertEqual(dedup_key(":安可瘋狂:"), dedup_key("安可瘋狂"))

    def test_different_words_differ(self):
        self.assertNotEqual(dedup_key("笑死"), dedup_key("笑死了"))


class QualityGateTests(unittest.TestCase):
    def test_stored_emoji_and_sticker_formats_count_as_symbol_only(self):
        self.assertTrue(etu.is_emoji_or_symbol_only(":安可瘋狂:"))
        self.assertTrue(etu.is_emoji_or_symbol_only("????????"))
        self.assertTrue(etu.is_emoji_or_symbol_only("……！！"))
        self.assertFalse(etu.is_emoji_or_symbol_only("123"))
        self.assertTrue(etu.is_emoji_or_symbol_only(":安可瘋狂: :吃瓜看戲:"))
        self.assertTrue(etu.is_emoji_or_symbol_only("[貼圖：卜靈比讚]"))
        self.assertTrue(etu.is_emoji_or_symbol_only("<:anko:123> 😂"))

    def test_text_next_to_a_sticker_or_emoji_is_content(self):
        self.assertFalse(etu.is_emoji_or_symbol_only("笑死 :安可瘋狂:"))
        self.assertFalse(etu.is_emoji_or_symbol_only("[貼圖：卜靈比讚] 這張太可愛"))
        self.assertFalse(etu.is_emoji_or_symbol_only("時間 10:30 集合"))

    def test_link_only(self):
        self.assertTrue(etu.is_link_only("https://x.test/a https://x.test/b"))
        self.assertTrue(etu.is_link_only("https://x.test/a [預覽：3.1 版本前瞻 - 直播時間]"))   # 存檔格式帶預覽
        self.assertFalse(etu.is_link_only("看這個 https://x.test/a"))
        self.assertFalse(etu.is_link_only(""))


class _Cursor:
    def __init__(self, rows):
        self.rows = rows
        self.sql = None
        self.params = None
        self.statements: list[str] = []
        self.ef_values: list[int] = []

    def execute(self, sql, params=None):
        self.statements.append(sql)
        if "hnsw.ef_search" in sql:
            self.ef_values.append(int(params[0]))
        if sql.lstrip().startswith("SELECT"):
            self.sql, self.params = sql, params

    def fetchall(self):
        return self.rows

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _Conn:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class SearchChatCollapseTests(unittest.TestCase):
    ROWS = [
        ("1", ":吃瓜看戲:", "A", 0.01, "t1"),
        ("2", ":吃瓜看戲:", "A", 0.02, "t2"),
        ("3", "吃瓜看戲！", "A", 0.03, "t3"),
        ("4", ":吃瓜看戲:", "B", 0.05, "t4"),
        ("5", "維護到幾點", "A", 0.20, "t5"),
    ]

    def _run(self, **kwargs):
        cursor = _Cursor(list(self.ROWS))
        embed = SimpleNamespace(get_query_embedding=lambda q: [0.1, 0.2])
        with mock.patch.object(cr, "psycopg2", cr.psycopg2 or object()), \
             mock.patch.object(cr, "_get_embed_model", lambda logger: embed), \
             mock.patch.object(cr, "_pgvector_connect", lambda: _Conn(cursor)):
            result = cr.search_chat(question="吃瓜", limit=2, logger=LOG, **kwargs)
        return result, cursor

    def test_full_corpus_search_opens_ef_search_to_the_pgvector_limit(self):
        """同一句話重複幾十次的向量一模一樣，ef_search 太窄會把整團繞過（實測 200 一列都沒回來、1000 才回來）。"""
        _, cursor = self._run(return_meta=True)
        self.assertEqual(cursor.ef_values, [1000])

    def test_window_reranking_keeps_the_small_ef_search(self):
        _, cursor = self._run(return_meta=True, candidate_ids=["1", "2", "3"])
        self.assertEqual(cursor.ef_values, [100])   # max(100, 2×撈取筆數)；走 message_id 索引，這個值其實用不到

    def test_a_dedicated_chat_table_is_queried_without_a_doc_type_filter(self):
        """專用表帶了 doc_type 篩選，規劃器會放著 HNSW 不用（那個欄位沒統計、估成只剩 0.5% 的列）。"""
        _, cursor = self._run(return_meta=True)
        self.assertNotIn("doc_type", cursor.sql)
        self.assertIn("IS NOT NULL", cursor.sql)

    def test_a_shared_chat_table_still_filters_by_doc_type(self):
        from sys_settings.pgvector_settings import HybridRetrievalSettings, RetrievalSourceConfig
        shared = HybridRetrievalSettings(retrieval_sources={
            "discord_chat": RetrievalSourceConfig(source_key="discord_chat", table_name="shared_index",
                                                  doc_type="discord_chat", enabled=True, persist_mode="auto"),
            "member_profile": RetrievalSourceConfig(source_key="member_profile", table_name="shared_index",
                                                    doc_type="member_profile", enabled=True, persist_mode="manual"),
        })
        self.assertTrue(shared.chat_table_is_shared())
        self.assertFalse(cr.HYBRID_RETRIEVAL_SETTINGS.chat_table_is_shared())   # 預設設定：各來源各一張表
        with mock.patch.object(cr, "HYBRID_RETRIEVAL_SETTINGS", shared):
            _, cursor = self._run(return_meta=True)
        self.assertIn("metadata_->>'doc_type' = %s", cursor.sql)
        self.assertIn("discord_chat", cursor.params)

    def test_same_author_same_text_collapses_to_the_latest_copy_with_the_nearest_distance(self):
        result, _ = self._run(return_meta=True)
        self.assertEqual([r["message_id"] for r in result], ["3", "4"])   # 代表是最新那則，名次仍是最近那筆的
        self.assertEqual(result[0]["repeat_count"], 3)
        self.assertEqual(result[0]["distance"], 0.01)
        self.assertEqual(result[0]["timestamp"], "t3")
        self.assertEqual(result[1]["repeat_count"], 1)

    def test_ids_only_mode_is_collapsed_too(self):
        result, cursor = self._run()
        self.assertEqual(result, ["3", "4"])
        self.assertNotIn("length(text)", cursor.sql)   # 沒給 min_chars 就不擋

    def test_overfetch_before_collapse_and_min_chars_reach_the_database(self):
        _, cursor = self._run(return_meta=True, min_chars=8)
        self.assertIn(8, cursor.params)                 # 最短字數交給資料庫擋
        self.assertGreater(cursor.params[-1], 2)        # 折疊前多撈（LIMIT 大於 limit）

    def test_punctuation_only_rows_are_not_collapsed_together(self):
        rows = [{"message_id": "1", "text": "????????", "author_id": "A", "repeat_count": 1},
                {"message_id": "2", "text": "........", "author_id": "A", "repeat_count": 1}]
        self.assertEqual([r["message_id"] for r in cr._collapse_repeats(rows, 5)], ["1", "2"])

    def test_hnsw_session_settings_are_set_before_the_query(self):
        _, cursor = self._run(return_meta=True)
        self.assertTrue(any("hnsw.ef_search" in st for st in cursor.statements))
        self.assertTrue(any("hnsw.iterative_scan = relaxed_order" in st for st in cursor.statements))
        self.assertTrue(cursor.statements[-1].lstrip().startswith("SELECT"))   # 設定在查詢之前

    def test_ef_search_never_exceeds_the_pgvector_limit(self):
        cursor = _Cursor([])
        embed = SimpleNamespace(get_query_embedding=lambda q: [0.1, 0.2])
        with mock.patch.object(cr, "psycopg2", cr.psycopg2 or object()), \
             mock.patch.object(cr, "_get_embed_model", lambda logger: embed), \
             mock.patch.object(cr, "_pgvector_connect", lambda: _Conn(cursor)):
            cr.search_chat(question="x", limit=500, logger=LOG)
        self.assertLessEqual(max(cursor.ef_values), 1000)

    def test_rows_are_ordered_by_distance_before_collapse_and_cut(self):
        rows = [("5", "維護到幾點", "A", 0.20, "t5"), ("4", ":吃瓜看戲:", "B", 0.05, "t4"), ("1", ":吃瓜看戲:", "A", 0.01, "t1")]
        cursor = _Cursor(rows)
        embed = SimpleNamespace(get_query_embedding=lambda q: [0.1, 0.2])
        with mock.patch.object(cr, "psycopg2", cr.psycopg2 or object()), \
             mock.patch.object(cr, "_get_embed_model", lambda logger: embed), \
             mock.patch.object(cr, "_pgvector_connect", lambda: _Conn(cursor)):
            self.assertEqual(cr.search_chat(question="x", limit=2, logger=LOG), ["1", "4"])   # 索引回來的順序亂也照距離

    def test_collapse_can_be_turned_off(self):
        result, cursor = self._run(return_meta=True, collapse=False)
        self.assertEqual([r["message_id"] for r in result], ["1", "2"])
        self.assertEqual(cursor.params[-1], 2)


def _msg(mid, content, author_id=1, bot=False):
    return SimpleNamespace(
        id=mid, content=content,
        author=SimpleNamespace(id=author_id, bot=bot, display_name=f"u{author_id}", name=f"u{author_id}"),
        created_at=datetime(2026, 10, 1, tzinfo=timezone.utc), channel=SimpleNamespace(id=5),
    )


class WindowCollapseTests(unittest.TestCase):
    def test_same_author_same_line_keeps_only_the_latest_in_order(self):
        messages = [_msg(1, "維護到幾點", 7), _msg(2, "維護到幾點！", 7), _msg(3, "維護到幾點", 8),
                    _msg(4, "晚餐吃什麼", 7), _msg(5, "????", 7), _msg(6, "......", 7), _msg(7, "  ", 7)]
        collapsed, representative = cr._collapse_window(messages)
        kept = [str(m.id) for m in collapsed]
        self.assertEqual(kept, ["2", "3", "4", "5", "6"])   # 同一人留最新；別人另算；純標點各自算；空白的不算
        self.assertEqual(representative["1"], "2")          # 舊的那則指向最新那則
        self.assertEqual(representative["3"], "3")

    def test_vector_route_queries_every_copy_but_ranks_the_representative(self):
        seen = {}

        def fake_search_chat(**kwargs):
            seen.update(kwargs)
            return ["1", "4", "2"]          # 向量庫只找得到舊的那則（1），最新的 2 還在緩衝；4 是別人的

        messages = [_msg(1, "維護到幾點", 7), _msg(2, "維護到幾點", 7), _msg(4, "晚餐吃什麼", 8)]
        with mock.patch.object(cr, "search_chat", fake_search_chat):
            rank = cr._build_vector_rank(question="維護幾點", messages=messages, candidate_pool=2, logger=LOG,
                                         representative={"1": "2", "2": "2", "4": "4"})
        self.assertEqual(seen["candidate_ids"], ["1", "2", "4"])   # 全部的 id 都去查
        self.assertEqual(seen["limit"], 3)                          # 副本會佔名額：候選池 2 組＋1 個副本
        self.assertEqual(rank, {"2": 1, "4": 2})                   # 名次落在代表那則、同一組只留最好的


class _Channel:
    def __init__(self, messages):
        self.id = 5
        self.guild = object()
        self._messages = messages

    async def history(self, limit):
        for msg in reversed(self._messages):   # discord 由新到舊
            yield msg


class _Reranker:
    def __init__(self, scores=None, error=None):
        self.scores, self.error, self.calls = scores, error, []

    def rerank(self, query, passages, *, max_wait_seconds=None):
        self.calls.append((query, list(passages)))
        if self.error:
            raise self.error
        return list(self.scores)


class _Gate:
    """假的 GPU 閘門：記下誰拿、拿了幾次；`stuck=True` 永遠拿不到（模擬顯示卡被佔著）。"""

    def __init__(self, stuck=False):
        self.stuck, self.owners = stuck, []

    def __call__(self, owner, *, lease_seconds=None):
        gate = self

        class _Ctx:
            async def __aenter__(self_inner):
                if gate.stuck:
                    await asyncio.sleep(30)
                gate.owners.append((owner, lease_seconds))
                if getattr(gate, "expire", False):
                    asyncio.current_task().cancel()   # 模擬租約到期：看門狗取消持有閘門的 task

            async def __aexit__(self_inner, *exc):
                return False

        return _Ctx()


class RelevantSelectionTests(unittest.TestCase):
    MESSAGES = [
        _msg(1, "維護到晚上十一點", 1),
        _msg(2, "[貼圖：卜靈比讚]", 2),
        _msg(3, "維護到晚上十一點", 2),
        _msg(4, "https://example.com/x", 3),
        _msg(5, "伺服器開了嗎", 1),
        _msg(6, "今天晚餐吃什麼", 2),
        _msg(7, "笑死", 3),
        _msg(8, "好喔", 1),
    ]
    VECTOR_RANK = {"2": 1, "3": 2, "1": 3, "4": 4, "5": 5, "6": 6}

    def _run(self, *, max_relevant=3, messages=None, bm25=None, gate=None, **kwargs):
        interaction = SimpleNamespace(channel=_Channel(messages or self.MESSAGES),
                                      client=SimpleNamespace(user=SimpleNamespace(id=999)))
        self.gate = gate or _Gate()
        with mock.patch.object(cr, "_build_bm25_rank", bm25 or (lambda **kw: {})), \
             mock.patch.object(cr, "_build_vector_rank", lambda **kw: dict(self.VECTOR_RANK)), \
             mock.patch.object(cr, "gpu_exclusive", self.gate), \
             mock.patch.object(cr, "_build_discord_context_item",
                               lambda msg, tz: {"role": "user", "content": msg.content, "message_id": str(msg.id)}):
            return asyncio.run(cr.retrieve_discord_context(
                interaction, "維護到幾點", max_context_messages=100, min_recent_context=2,
                max_relevant_context=max_relevant, max_context_to_send=50, taipei_tz=timezone.utc, logger=LOG, **kwargs,
            ))

    @staticmethod
    def _ids(context):
        return [item["message_id"] for item in context if item.get("message_id")]

    def test_noise_and_repeats_do_not_take_relevant_slots(self):
        context, _, meta = self._run()
        self.assertEqual(self._ids(context), ["3", "5", "6", "7", "8"])   # 貼圖、連結、別人的重複句不佔名額；最近兩則保底
        self.assertGreaterEqual(meta["relevant_skipped_noise"], 1)
        self.assertGreaterEqual(meta["relevant_skipped_repeat"], 1)
        self.assertEqual(meta["reranked_count"], 0)
        self.assertEqual(self.gate.owners, [])    # 沒給 reranker 就不碰 GPU 閘門

    def test_same_author_repeats_are_collapsed_before_both_routes(self):
        received = []

        def bm25(*, question, messages):
            received.extend(str(m.id) for m in messages)
            return {str(m.id): i for i, m in enumerate(messages, 1)}

        messages = [_msg(1, "維護到幾點", 1), _msg(2, "維護到幾點", 1), _msg(3, "維護到幾點", 2),
                    _msg(4, "晚餐吃什麼", 3), _msg(5, "笑死", 3), _msg(6, "好喔", 1)]
        with mock.patch.object(self, "VECTOR_RANK", {}):
            context, _, meta = self._run(messages=messages, bm25=bm25)
        self.assertNotIn("1", received)                     # 同一人的舊重複沒進任何一路
        self.assertIn("2", received)
        self.assertEqual(self._ids(context), ["2", "4", "5", "6"])   # 2 進相關；3 是別人的同一句被跨作者去重
        self.assertEqual(meta["relevant_skipped_repeat"], 1)        # 計到的只有跨作者的那次

    def test_reranker_scores_decide_the_relevant_picks(self):
        reranker = _Reranker(scores=[0.1, 0.9, 0.5])       # 對應 picked 順序 3, 5, 6
        context, _, meta = self._run(max_relevant=2, reranker=reranker, rerank_min_score=0.3, rerank_candidates=30)
        self.assertEqual(self._ids(context), ["5", "6", "7", "8"])
        self.assertEqual(reranker.calls[0][0], "維護到幾點")
        self.assertIn("u2: 維護到晚上十一點", reranker.calls[0][1])   # 給 reranker 看誰說的
        self.assertEqual(meta["reranked_count"], 3)
        reranked = meta["retrieval_debug"]["reranked"]
        self.assertEqual([r["message_id"] for r in reranked], ["5", "6", "3"])
        self.assertEqual([o for o, _ in self.gate.owners], ["askai-rerank"])   # 重排在 bot 的 GPU 閘門裡做

    def test_an_expired_lease_cancels_only_the_rerank_and_falls_back(self):
        reranker = _Reranker(scores=[0.1, 0.9, 0.5])
        gate = _Gate()
        gate.expire = True
        context, _, meta = self._run(max_relevant=2, reranker=reranker, gate=gate, rerank_candidates=30)
        self.assertEqual(self._ids(context), ["3", "5", "7", "8"])   # 照融合名次，發問的人照樣拿到回答
        self.assertEqual(meta["reranked_count"], 0)
        self.assertEqual([o for o, _ in gate.owners], ["askai-rerank"])

    def test_gpu_busy_falls_back_to_fused_order_without_calling_the_reranker(self):
        reranker = _Reranker(scores=[0.1, 0.9, 0.5])
        context, _, meta = self._run(max_relevant=2, reranker=reranker, gate=_Gate(stuck=True),
                                     rerank_gpu_wait_seconds=0.05)
        self.assertEqual(self._ids(context), ["3", "5", "7", "8"])
        self.assertEqual(reranker.calls, [])
        self.assertEqual(meta["reranked_count"], 0)

    def test_min_score_drops_weak_candidates_even_if_slots_remain(self):
        reranker = _Reranker(scores=[0.1, 0.9, 0.2])
        context, _, meta = self._run(max_relevant=3, reranker=reranker, rerank_min_score=0.5, rerank_candidates=30)
        self.assertEqual(self._ids(context), ["5", "7", "8"])

    def test_reranker_failure_or_wrong_count_falls_back_to_fused_order(self):
        for reranker in (_Reranker(error=RuntimeError("GPU busy")), _Reranker(scores=[0.9, 0.1]),
                         _Reranker(scores=[float("-inf"), float("-inf"), float("nan")])):
            context, _, meta = self._run(max_relevant=2, reranker=reranker, rerank_candidates=30)
            self.assertEqual(self._ids(context), ["3", "5", "7", "8"])
            self.assertEqual(meta["reranked_count"], 0)

    def test_documents_the_backend_skipped_are_never_kept(self):
        reranker = _Reranker(scores=[float("-inf"), 0.9, 0.5])     # 後端漏了第一則
        context, _, meta = self._run(max_relevant=3, reranker=reranker, rerank_candidates=30, rerank_min_score=None)
        self.assertEqual(self._ids(context), ["5", "6", "7", "8"])
        self.assertEqual(meta["reranked_count"], 2)


class CallbackLinesTests(unittest.TestCase):
    def test_min_chars_goes_to_sql_and_repeats_are_marked(self):
        from llm.ambient import ambient_reply as ar

        rows = [
            {"message_id": "11", "text": "卜靈真的很強啊打王超快", "distance": 0.2,
             "timestamp": "2026-10-01T00:00:00+00:00", "author_id": "42", "repeat_count": 3},
            {"message_id": "12", "text": "今天維護到晚上十一點喔", "distance": 0.3,
             "timestamp": "2026-10-02T00:00:00+00:00", "author_id": "43", "repeat_count": 1},
        ]
        captured = {}

        def fake_search_chat(**kwargs):
            captured.update(kwargs)
            return rows

        async def no_target(message, query):
            return None

        message = SimpleNamespace(guild=SimpleNamespace(get_member=lambda uid: None), channel=SimpleNamespace(id=5))
        with mock.patch("llm.retrievers.context_retriever.search_chat", fake_search_chat), \
             mock.patch("llm.storage.raw_message_store.get_reaction_salience", lambda ids: {}), \
             mock.patch.object(ar, "_resolve_callback_target", no_target):
            lines = asyncio.run(ar._build_chat_callback_context(message, "卜靈強不強"))

        self.assertEqual(captured["min_chars"], ar._SETTINGS.callback_min_chars)
        self.assertEqual(len(lines), 2)
        marked = [line for line in lines if "卜靈真的很強" in line][0]
        self.assertIn("（同一人說過 3 次）", marked)
        self.assertNotIn("說過", [line for line in lines if "維護" in line][0])


class CommandWiringTests(unittest.TestCase):
    def test_reranker_is_handed_in_only_when_the_switch_is_on(self):
        from commands import llm_commands as lc

        made = []
        with mock.patch.object(lc, "_ASKAI_RERANKER", None), \
             mock.patch.object(lc.switches, "current", lambda: SimpleNamespace(askai_rerank_mode="off")):
            self.assertIsNone(lc._askai_reranker())
        with mock.patch.object(lc, "_ASKAI_RERANKER", None), \
             mock.patch.object(lc.switches, "current", lambda: SimpleNamespace(askai_rerank_mode="on")), \
             mock.patch.object(lc, "LemonadeReranker", lambda **kw: made.append(kw) or "reranker"):
            self.assertEqual(lc._askai_reranker(), "reranker")
            self.assertEqual(lc._askai_reranker(), "reranker")
        self.assertEqual(len(made), 1)   # 只建一次
        with made[0]["gate"](max_wait_seconds=1):    # reranker 自己不拿鎖：給它的閘門是空的
            pass


if __name__ == "__main__":
    unittest.main()
