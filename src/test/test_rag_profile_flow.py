"""守的底線：/askai 與插話撈人物卡（`retrieve_rag_context_sync`）從查詢到卡片的行為不因拆段而改變。

斷言呼叫端看得到的事：哪些情況不查、三路 SQL 各在什麼條件下查、查的參數、一路失敗其他照常、
語意檢索只收本伺服器、同一份文件只留一筆且留精度高的來源、卡片數受上限、meta 的計數。
DB 與向量索引都是假的，卡片產生器是真的。
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

from llm.retrievers import context_retriever as cr  # noqa: E402

GUILD = 9
ASKER = 1001
MIRA = 2002
NUO = 3003
LOG = logging.getLogger("rag-flow-test")


def _doc(row_id, kind, person, alias="", text=None, guild=GUILD):
    md = {"doc_type": "member_profile", "profile_kind": kind, "guild_id": str(guild),
          "ref_doc_id": f"{kind}:{person}:{row_id}"}
    if kind == "impression":
        md.update(author_id=str(ASKER), target_user_id=str(person), target_alias=alias)
    else:
        md.update(author_id=str(person), alias=alias)
    label = {"intro_profile": "[Intro Profile]\nbio:", "impression": "[Member Impression]\nimpression:",
             "auto_personality": "[Auto Personality]\nsummary:"}[kind]
    return (row_id, f"{label} {text or f'文件{row_id}'}", md)


class _Cursor:
    def __init__(self, harness):
        self.h = harness
        self.rows = []

    def execute(self, sql, params=None):
        if "ILIKE ANY" in sql:
            route = "alias"
        elif "ANY(%s)" in sql:
            route = "participant"
        else:
            route = "identity"
        self.h.queries.append((route, sql, params))
        if route in self.h.failing:
            raise RuntimeError(f"{route} 壞了")
        self.rows = list(self.h.rows.get(route, []))

    def fetchall(self):
        return self.rows

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _Node:
    """像 LlamaIndex 的 NodeWithScore：ref_doc_id 在 node 上，不在 metadata 裡。"""
    def __init__(self, row):
        _id, self.text, md = row
        self.metadata = {k: v for k, v in md.items() if k != "ref_doc_id"}
        self.node = SimpleNamespace(ref_doc_id=md["ref_doc_id"])


@unittest.skipIf(cr.psycopg2 is None or cr.VectorStoreIndex is None, "需要 psycopg2 與 llama_index")
class ProfileRetrievalTests(unittest.TestCase):

    def setUp(self):
        self.queries = []
        self.rows = {}
        self.failing = set()
        self.vector_rows = []
        self.vector_kwargs = {}
        self.source_enabled = True
        self.vector_fails = False
        self.captured = {}

    @contextlib.contextmanager
    def _fakes(self):
        h = self

        @contextlib.contextmanager
        def connect():
            yield SimpleNamespace(cursor=lambda: _Cursor(h))

        def retrieve(question):
            if h.vector_fails:
                raise RuntimeError("向量壞了")
            return [_Node(r) for r in h.vector_rows]

        def as_retriever(**kwargs):
            h.vector_kwargs.update(kwargs)
            return SimpleNamespace(retrieve=retrieve)

        settings = SimpleNamespace(
            get_source=lambda name: SimpleNamespace(table_name="member_profiles") if h.source_enabled else None,
            physical_table=lambda table: f"data_{table}",
            hybrid_candidate_pool=10,
        )
        real_build = cr.build_persona_cards

        def spy(**kwargs):
            h.captured["docs"] = kwargs["docs"]
            h.captured["build_kwargs"] = kwargs
            return real_build(**kwargs)

        with mock.patch.object(cr, "HYBRID_RETRIEVAL_SETTINGS", settings), \
                mock.patch.object(cr, "_pgvector_connect", connect), \
                mock.patch.object(cr, "_get_or_build_vector_index",
                                  lambda *a: SimpleNamespace(as_retriever=as_retriever)), \
                mock.patch.object(cr, "build_persona_cards", spy):
            yield

    def _run(self, question="米拉最近在幹嘛", *, requester=ASKER, participants=(), top_k=5,
             mentioned=None, member_names=None):
        with self._fakes():
            return cr.retrieve_rag_context_sync(question, GUILD, requester, list(participants), LOG, top_k,
                                                mentioned_user_ids=mentioned, member_names=member_names)

    def _routes(self):
        return [r for r, _s, _p in self.queries]

    # ── 不查的情況 ──
    def test_empty_question_or_no_guild_skips_everything(self):
        with self._fakes():
            ctx, meta = cr.retrieve_rag_context_sync("  ", GUILD, ASKER, [], LOG, 5)
            ctx2, meta2 = cr.retrieve_rag_context_sync("嗨", None, ASKER, [], LOG, 5)
        self.assertEqual(([], []), (ctx, ctx2))
        self.assertEqual([], self.queries)
        self.assertTrue(meta["enabled"] and meta2["enabled"])

    def test_disabled_source_is_reported_in_meta(self):
        self.source_enabled = False
        ctx, meta = self._run()
        self.assertEqual([], ctx)
        self.assertFalse(meta["enabled"])
        self.assertEqual([], self.queries)

    # ── 三路 SQL 各在什麼條件下查、查什麼 ──
    def test_identity_route_needs_a_requester_and_asks_for_their_three_kinds(self):
        self._run("嗨", requester=ASKER)
        self.assertEqual(["identity"], self._routes())
        _r, sql, params = self.queries[0]
        self.assertIn("data_member_profiles", sql)
        self.assertEqual((str(GUILD), str(ASKER), str(ASKER), str(ASKER), 5), params)
        self.queries.clear()
        self._run("嗨", requester=None)
        self.assertEqual([], self._routes())

    def test_participant_route_dedups_caps_and_skips_blanks(self):
        ids = [MIRA, MIRA, 0, NUO, 4, 5, 6, 7]
        _ctx, meta = self._run("嗨", requester=None, participants=ids)
        self.assertEqual(["participant"], self._routes())
        _r, _sql, params = self.queries[0]
        self.assertEqual([str(MIRA), str(NUO), "4", "5", "6"], params[1])
        self.assertEqual(5, meta["participant_count"])
        self.assertEqual(8, params[-1])             # max(8, top_k + 3)

    def test_alias_route_fires_on_hints_or_names(self):
        self._run("米拉最近在幹嘛", requester=None)
        self.assertEqual(["alias"], self._routes())
        _r, sql, params = self.queries[0]
        self.assertIn("%米拉%", params)
        self.assertEqual(["0"], params[-3], "沒有對到 id 時用不會中的 0")
        self.queries.clear()
        self._run("<@2002> 嗨", requester=None, mentioned=[str(MIRA)])
        self.assertEqual(["alias"], self._routes())
        self.assertEqual([str(MIRA)], self.queries[0][2][-3])
        self.queries.clear()
        self._run("嗨", requester=None)
        self.assertEqual([], self._routes())

    def test_mentioned_ids_come_from_the_caller_or_are_re_extracted(self):
        self._run("<@2002> 嗨", requester=None)
        self.assertEqual([str(MIRA)], self.captured["build_kwargs"]["mentioned_user_ids"])
        self._run("米拉 嗨", requester=None, mentioned=[str(NUO)])
        self.assertEqual([str(NUO)], self.captured["build_kwargs"]["mentioned_user_ids"])

    def test_discord_name_match_joins_the_alias_query(self):
        self._run("一野最近在幹嘛", requester=None, member_names={str(NUO): ["糯糯", "一野shout死你"]})
        alias = [p for r, _s, p in self.queries if r == "alias"]
        self.assertEqual([str(NUO)], alias[0][-3])

    def test_all_three_routes_run_in_order_and_are_counted(self):
        self.rows = {"identity": [_doc(1, "intro_profile", ASKER, "我")],
                     "participant": [_doc(2, "intro_profile", NUO, "糯糯"), _doc(3, "impression", NUO, "糯糯")],
                     "alias": [_doc(4, "intro_profile", MIRA, "米拉")]}
        _ctx, meta = self._run("米拉最近在幹嘛", participants=[NUO])
        self.assertEqual(["identity", "participant", "alias"], self._routes())
        self.assertEqual((1, 2, 1), (meta["sql_identity_hits"], meta["sql_participant_hits"], meta["sql_alias_hits"]))
        # 排序只認 identity → alias → vector；在場者那一路沒有名次，排在最後（現況，拆段不改）
        self.assertEqual(["sql_identity", "sql_alias", "sql_participant", "sql_participant"],
                         [d["source"] for d in self.captured["docs"]])

    def test_one_route_failing_keeps_the_others(self):
        self.failing = {"participant"}
        self.rows = {"identity": [_doc(1, "intro_profile", ASKER, "我")], "alias": [_doc(4, "intro_profile", MIRA, "米拉")]}
        with self.assertLogs(LOG, level="WARNING") as cm:
            _ctx, meta = self._run("米拉最近在幹嘛", participants=[NUO])
        self.assertTrue(any("participant" in line for line in cm.output))
        self.assertEqual(0, meta["sql_participant_hits"])
        self.assertEqual(["sql_identity", "sql_alias"], [d["source"] for d in self.captured["docs"]])

    def test_string_metadata_from_sql_is_parsed(self):
        import json
        rid, text, md = _doc(4, "intro_profile", MIRA, "米拉")
        self.rows = {"alias": [(rid, text, json.dumps(md))]}
        ctx, _meta = self._run("米拉最近在幹嘛", requester=None)
        self.assertEqual(str(MIRA), self.captured["docs"][0]["metadata"]["author_id"])
        self.assertTrue(any(c.get("person_id") == str(MIRA) for c in ctx))

    # ── 語意檢索 ──
    def test_vector_route_pulls_a_wider_pool_and_keeps_only_this_guild(self):
        self.vector_rows = [_doc(7, "intro_profile", MIRA, "米拉"), _doc(8, "intro_profile", 777, "外人", guild=99)]
        _ctx, meta = self._run("嗨", requester=None, top_k=2)
        self.assertEqual(5, self.vector_kwargs["similarity_top_k"])      # max(top_k*2=4, pool//2=5)
        self.assertEqual(2, meta["vector_hits"])
        docs = self.captured["docs"]
        self.assertEqual(["vector"], [d["source"] for d in docs])
        self.assertEqual("intro_profile:2002:7", docs[0]["db_id"], "ref_doc_id 從 node 拿，才能和 SQL 那筆去重")

    def test_vector_failure_keeps_sql_results(self):
        self.vector_fails = True
        self.rows = {"identity": [_doc(1, "intro_profile", ASKER, "我")]}
        with self.assertLogs(LOG, level="WARNING"):
            ctx, meta = self._run("嗨")
        self.assertEqual(0, meta["vector_hits"])
        self.assertTrue(any(c.get("person_id") == str(ASKER) for c in ctx))

    # ── 去重與排序 ──
    def test_same_doc_from_two_routes_keeps_the_more_precise_one(self):
        shared = _doc(5, "impression", MIRA, "米拉", text="很會吐槽")
        self.rows = {"participant": [shared]}
        self.vector_rows = [shared]
        ctx, meta = self._run("嗨", requester=None, participants=[MIRA])
        self.assertEqual(1, meta["dedup_hits"])
        self.assertEqual(["sql_participant"], [d["source"] for d in self.captured["docs"]])
        card = next(c["content"] for c in ctx if c.get("person_id") == str(MIRA))
        self.assertEqual(1, card.count("很會吐槽"))

    def test_identity_beats_alias_beats_vector_then_newest_first(self):
        self.rows = {"identity": [_doc(1, "intro_profile", ASKER, "我")],
                     "alias": [_doc(2, "intro_profile", MIRA, "米拉"), _doc(9, "impression", MIRA, "米拉")]}
        self.vector_rows = [_doc(3, "intro_profile", NUO, "糯糯")]
        self._run("米拉最近在幹嘛")
        self.assertEqual([("sql_identity", 1), ("sql_alias", 9), ("sql_alias", 2), ("vector", "intro_profile:3003:3")],
                         [(d["source"], d["db_id"]) for d in self.captured["docs"]])

    # ── 卡片與 meta ──
    def test_match_counts_describe_who_the_docs_are_about(self):
        self.rows = {"identity": [_doc(1, "intro_profile", ASKER, "我"), _doc(2, "impression", ASKER, "阿問")],
                     "alias": [_doc(3, "intro_profile", MIRA, "米拉")]}
        _ctx, meta = self._run("米拉最近在幹嘛")
        self.assertEqual((2, 1, 1), (meta["self_match_count"], meta["target_match_count"], meta["alias_match_count"]))

    def test_cards_are_capped_by_top_k_and_the_hard_limit(self):
        self.vector_rows = [_doc(i, "intro_profile", 5000 + i, f"人{i}") for i in range(6)]
        ctx, meta = self._run("嗨", requester=None, top_k=10)
        self.assertEqual(cr.PERSONA_MAX_CARDS, meta["cards_generated"])
        self.assertEqual(cr.PERSONA_MAX_CARDS, meta["cards_sent"])
        self.assertEqual("persona_card_header", ctx[0]["metadata"])
        self.assertEqual(cr.PERSONA_MAX_CARDS + 1, len(ctx))
        ctx1, meta1 = self._run("嗨", requester=None, top_k=1)
        self.assertEqual(2, len(ctx1))
        self.assertEqual(2, meta1["sent_count"])

    def test_more_cards_than_the_budget_are_trimmed_to_the_last_ones(self):
        """卡片產生器自己會限量，這段是安全網：真的多出來時留表頭與最後幾張。"""
        items = [{"role": "system", "content": "", "metadata": "persona_card_header"}] + \
                [{"role": "system", "content": f"卡{i}", "person_id": str(i)} for i in range(5)]
        with self._fakes(), mock.patch.object(cr, "format_persona_cards_for_context", lambda cards: list(items)):
            ctx, meta = cr.retrieve_rag_context_sync("嗨", GUILD, None, [], LOG, 2)
        self.assertEqual(3, meta["trimmed_count"])
        self.assertEqual(["persona_card_header", None, None], [c.get("metadata") for c in ctx])
        self.assertEqual(["卡3", "卡4"], [c["content"] for c in ctx[1:]])
        self.assertEqual(3, meta["sent_count"])

    def test_nothing_found_is_an_empty_context_with_zero_counts(self):
        ctx, meta = self._run("嗨")
        self.assertEqual([], ctx)
        self.assertEqual((0, 0, 0), (meta["dedup_hits"], meta["cards_generated"], meta["sent_count"]))
        self.assertEqual("general", meta["intent"])


if __name__ == "__main__":
    unittest.main()
