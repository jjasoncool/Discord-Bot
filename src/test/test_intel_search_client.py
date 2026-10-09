"""bot 端的情報搜尋客戶端（`llm/retrievers/intel/client.py`）：/askai 透過 MCP 用 search-mcp 的 search／fetch。

守的底線：
  - 工具清單照 search-mcp 給的（名稱、說明、參數），轉成模型看得懂的 OpenAI 格式
  - search 結果只給模型回答用得到的欄位；模型漏帶原句時補上使用者的原句（重新排序才準）；筆數有上限
  - fetch 的全文有長度上限；search-mcp 每頁字數不超過這個上限（被截掉的一定能翻頁讀到）
  - 參數錯、工具不存在、搜尋端錯誤都回 `{"error": ...}` 給模型，不往外丟；每次呼叫都記下來
  - **搜尋到一半連線斷掉（服務重啟）也只是回 `{"error": ...}`**：不能變成「取消」整個 /askai
  - 服務連不上就給 None（呼叫端照原本的方式回答）；工具的使用規則跟著工具一起給（只有真的有工具時才有）
  - `run_with_intel`：開關關著不連線；開著就把工具交給回答流程，並記下有沒有連上、呼叫了哪些工具
  - /askai 的接線：照開關決定、經過寫進回應紀錄、長回答切成多則

測試直接連同一個行程裡的 MCP server（`llm.mcp_server.server`），索引換成假資料，不碰網路。

執行：
    cd src && python -m unittest test.test_intel_search_client -v
"""

import asyncio
import json
import os
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from llm import mcp_server  # noqa: E402
from llm.retrievers.intel import prepare_intel_session, run_with_intel  # noqa: E402
from llm.retrievers.intel import client as intel_client  # noqa: E402
from llm.retrievers.intel.client import _SEARCH_FIELDS  # noqa: E402
from services.search.text import normalize  # noqa: E402
from sys_settings.llm_settings import AskAIIntelSettings  # noqa: E402
from sys_settings.search_settings import SEARCH_SETTINGS  # noqa: E402
from test.test_search_index import SearchIndexTestBase  # noqa: E402
from test.test_search_rerank import StubReranker  # noqa: E402


class _IntelServerBase(SearchIndexTestBase, unittest.IsolatedAsyncioTestCase):
    """同一個行程裡的 MCP server，索引換成假資料。"""

    def setUp(self):
        super().setUp()
        self.db.article(4930, "巡迴演唱會台北站", "<p>演出場館在桃園會展中心</p>")
        self.db.ptt("M.1.A.001", "[鳴潮] 演唱會心得", "第一次來桃園會展中心看表演。" + "心得很長。" * 600)
        self.reranker = StubReranker()
        index = self.make_index(reranker=self.reranker)
        self._original_provider = mcp_server.index_provider
        mcp_server.index_provider = lambda: index

    def tearDown(self):
        mcp_server.index_provider = self._original_provider
        super().tearDown()

    async def prepare(self, question="演唱會在哪裡辦？", **settings):
        session = await prepare_intel_session(question=question, settings=AskAIIntelSettings(**settings),
                                              server=mcp_server.server)
        self.assertIsNotNone(session)
        return session


class IntelSessionTests(_IntelServerBase):

    async def test_tools_come_from_the_server_in_openai_format(self):
        session = await self.prepare()
        tools = {t["function"]["name"]: t["function"] for t in session.tools}

        self.assertEqual(set(tools), {"search", "fetch"})
        self.assertIn("query", tools["search"]["parameters"]["properties"])
        self.assertIn("question", tools["search"]["parameters"]["properties"])
        self.assertTrue(tools["fetch"]["description"])

    async def test_search_gives_compact_results_and_fills_in_the_question(self):
        session = await self.prepare()
        out = json.loads(await session.execute("search", '{"query": "桃園會展中心"}'))

        ids = [hit["id"] for hit in out["results"]]
        self.assertIn("article:4930", ids)
        self.assertTrue(all(set(hit) <= set(_SEARCH_FIELDS) for hit in out["results"]))
        self.assertEqual(self.reranker.queries, [normalize("演唱會在哪裡辦？")])   # 模型沒帶原句，補上
        self.assertEqual(session.calls[0]["tool"], "search")
        self.assertEqual(session.calls[0]["result_ids"], ids)

    async def test_question_from_the_model_is_kept_and_the_limit_is_capped(self):
        session = await self.prepare(search_limit=1)
        out = json.loads(await session.execute(
            "search", {"query": "桃園會展中心", "question": "場館在哪", "limit": 20}))

        self.assertEqual(len(out["results"]), 1)
        self.assertEqual(self.reranker.queries, [normalize("場館在哪")])

    async def test_fetch_text_is_capped(self):
        session = await self.prepare(fetch_max_chars=100)
        out = json.loads(await session.execute("fetch", '{"id": "ptt:M.1.A.001"}'))

        self.assertTrue(out["text"].startswith("第一次來桃園會展中心看表演"))
        self.assertLess(len(out["text"]), 140)
        self.assertIn("沒有附上", out["text"])
        self.assertEqual(out["source_label"], "PTT")
        self.assertFalse(out["official"])

    async def test_failures_come_back_to_the_model(self):
        session = await self.prepare()
        for name, args, reason in (("telegram", "{}", "沒有名為 telegram 的工具"),
                                   ("search", "{壞掉", "不是合法 JSON"),
                                   ("search", '{"query": "演唱會", "since": "上個月"}', "YYYY-MM-DD"),
                                   ("fetch", '{"id": "ptt:M.9.A.999"}', "沒有這份文件")):
            with self.subTest(name=name, args=args):
                out = json.loads(await session.execute(name, args))
                self.assertIn(reason, out["error"])

        self.assertEqual(len(session.calls), 4)
        self.assertTrue(all("error" in call for call in session.calls))

    async def test_timeouts_also_come_back_as_errors(self):
        session = await self.prepare()
        with mock.patch.object(intel_client.Client, "call_tool", side_effect=TimeoutError("讀取逾時")), \
                self.assertLogs("llm.retrievers.intel.client", level="WARNING"):
            out = json.loads(await session.execute("search", '{"query": "演唱會"}'))

        self.assertIn("查不到", out["error"])
        self.assertIn("error", session.calls[0])

    async def test_connection_dropped_mid_search_is_an_error_not_a_cancellation(self):
        """服務在列完工具、查到一半時重啟：HTTP 連線錯誤發生在 MCP 套件的背景 task 裡。長連線的話它會變成
        「取消」整個 /askai（2026-10-09 最後審查實測）；每次呼叫各開短連線，就只是一般的錯誤回給模型。"""
        import httpx2
        from mcp.client.streamable_http import streamable_http_client

        app = mcp_server.server.streamable_http_app(**{k: v for k, v in mcp_server.http_options().items()
                                                         if k != "host"})

        class DropToolCalls(httpx2.AsyncBaseTransport):
            def __init__(self, inner):
                self.inner = inner

            async def handle_async_request(self, request):
                if b"tools/call" in request.content:
                    raise httpx2.ConnectError("服務重啟中", request=request)
                return await self.inner.handle_async_request(request)

        def connect(target, settings):
            http = httpx2.AsyncClient(transport=DropToolCalls(httpx2.ASGITransport(app=app)))
            return intel_client.Client(streamable_http_client("http://127.0.0.1:8765/mcp", http_client=http))

        async with app.router.lifespan_context(app):
            with mock.patch.object(intel_client, "_connect", connect):
                session = await prepare_intel_session(question="q", server=mcp_server.server)
                with self.assertLogs("llm.retrievers.intel.client", level="WARNING"):
                    out = json.loads(await session.execute("search", '{"query": "演唱會"}'))

        self.assertIn("查不到", out["error"])
        self.assertFalse(asyncio.current_task().cancelling())

    async def test_unreachable_service_gives_none(self):
        with self.assertLogs("llm.retrievers.intel.client", level="WARNING"):
            session = await prepare_intel_session(question="x",
                                                  settings=AskAIIntelSettings(mcp_url="http://127.0.0.1:9/mcp"))
        self.assertIsNone(session)

    async def test_usage_rules_come_with_the_tools(self):
        session = await self.prepare()
        self.assertIn("遊戲情報查詢規則", session.instructions)

    def test_server_pages_fit_in_what_the_model_is_given(self):
        # 每頁不能比給模型的上限長：否則 bot 截掉的每頁後段，翻頁也讀不到
        self.assertLessEqual(SEARCH_SETTINGS.fetch_page_chars, AskAIIntelSettings().fetch_max_chars)


class RunWithIntelTests(_IntelServerBase):
    async def test_enabled_hands_the_tools_to_the_answer_and_records_the_calls(self):
        meta = {"mode": "on"}

        async def generate(session):
            self.assertIsNotNone(session)
            await session.execute("search", '{"query": "桃園會展中心"}')
            return "回答"

        result = await run_with_intel(generate, question="演唱會在哪？", enabled=True, meta=meta,
                                      server=mcp_server.server)

        self.assertEqual(result, "回答")
        self.assertIs(meta["connected"], True)
        self.assertEqual([c["tool"] for c in meta["calls"]], ["search"])

    async def test_disabled_does_not_connect(self):
        meta = {"mode": "off"}
        seen = []

        async def generate(session):
            seen.append(session)
            return "回答"

        with mock.patch("llm.retrievers.intel.client.prepare_intel_session") as opener:
            self.assertEqual(await run_with_intel(generate, question="q", enabled=False, meta=meta), "回答")
        opener.assert_not_called()
        self.assertEqual(seen, [None])
        self.assertEqual(meta, {"mode": "off"})

    async def test_unreachable_service_answers_without_tools(self):
        meta = {"mode": "on"}
        seen = []

        async def generate(session):
            seen.append(session)
            return "回答"

        with self.assertLogs("llm.retrievers.intel.client", level="WARNING"):
            await run_with_intel(generate, question="q", enabled=True, meta=meta,
                                 settings=AskAIIntelSettings(mcp_url="http://127.0.0.1:9/mcp"))
        self.assertEqual(seen, [None])
        self.assertIs(meta["connected"], False)


class AskaiWiringTests(unittest.TestCase):
    """/askai 的指令處理要接 Discord 互動，難以整段跑；這裡守住接線的關鍵點。"""

    def setUp(self):
        with open(os.path.join(SRC_DIR, "commands", "llm_commands.py"), encoding="utf-8") as f:
            self.askai = f.read()

    def test_askai_uses_the_switch_and_hands_the_tools_to_the_answer(self):
        self.assertIn("switches.current().askai_intel_search_mode", self.askai)
        self.assertIn('enabled=intel_mode == "on"', self.askai)
        self.assertIn("tool_runner=tool_runner,", self.askai)
        self.assertIn("await send_followup_in_parts(interaction, response_text)", self.askai)

    def test_long_replies_go_out_in_parts_and_only_the_first_mentions_the_asker(self):
        from commands import llm_commands

        sent = []

        async def send(**kwargs):
            sent.append(kwargs)

        user = SimpleNamespace(id=7)
        interaction = SimpleNamespace(user=user, followup=SimpleNamespace(send=send))
        text = "\n".join(f"第{i}行，" + "回答內容" * 30 for i in range(40))
        asyncio.run(llm_commands.send_followup_in_parts(interaction, text))

        self.assertGreater(len(sent), 1)
        self.assertTrue(all(len(m["content"]) <= 2000 for m in sent))
        self.assertEqual(sent[0]["allowed_mentions"].users, [user])
        self.assertTrue(all(m["allowed_mentions"].users is False for m in sent[1:]))

    def test_response_log_records_the_intel_lookup(self):
        from commands import llm_commands

        written = []
        fake_logger = SimpleNamespace(info=written.append)
        interaction = SimpleNamespace(guild=None, channel=None,
                                      user=SimpleNamespace(id=1, name="a", display_name="甲"))
        meta = {"mode": "on", "connected": True, "calls": [{"tool": "search", "elapsed_ms": 12}]}
        with mock.patch.object(llm_commands, "get_or_create_file_logger", return_value=fake_logger):
            llm_commands.append_askai_response_log(
                interaction=interaction, question="q", reply="r", model="m", think=True,
                discord_meta={}, rag_meta={}, intel_meta=meta)

        self.assertEqual(json.loads(written[0])["intel_meta"], meta)


if __name__ == "__main__":
    unittest.main()
