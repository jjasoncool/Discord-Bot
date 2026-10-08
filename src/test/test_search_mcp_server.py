"""MCP server（`llm/mcp_server.py`）：情報搜尋包給 LLM 客戶端的那一層。

守的底線：
  - 只開兩個工具：`search` 與 `fetch`（工具少，模型才選得準；加來源不加工具）
  - `sources` 能選的值由來源登記表產生，跟 `services.search.SOURCES` 永遠一致
  - 每筆結果都標明來源、是否官方、連結，模型才能分開講官方與玩家說法並附連結
  - 參數錯（不認得的來源、沒有的 id）要把**可讀的原因**送回模型，讓它改參數重試
  - 模型給了使用者的原句（`question`），重新排序要讀到原句，不是拆過的關鍵字

執行：
    cd src && python -m unittest test.test_search_mcp_server -v
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from mcp.server.mcpserver.exceptions import ToolError, UnexpectedToolError  # noqa: E402

from llm import mcp_server  # noqa: E402
from services.search import SOURCES  # noqa: E402
from services.search.text import normalize  # noqa: E402
from test.test_search_index import SearchIndexTestBase  # noqa: E402
from test.test_search_rerank import StubReranker  # noqa: E402


def _find_enums(schema) -> list[list]:
    """在 JSON schema 裡找出所有 enum（Optional[list[Literal]] 會包好幾層 anyOf／items）。"""
    found = []
    if isinstance(schema, dict):
        if "enum" in schema:
            found.append(schema["enum"])
        for value in schema.values():
            found += _find_enums(value)
    elif isinstance(schema, list):
        for value in schema:
            found += _find_enums(value)
    return found


class McpServerTests(SearchIndexTestBase, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        self.db.article(4930, "巡迴演唱會台北站", "<p>演出場館在桃園會展中心</p>")
        self.db.ptt("M.1.A.001", "[鳴潮] 演唱會心得", "第一次來桃園會展中心看表演",
                    comments=[{"tag": "推", "user": "alice", "content": "好看", "time": "09/06"}])
        index = self.make_index()
        self._original_provider = mcp_server.index_provider
        mcp_server.index_provider = lambda: index

    def tearDown(self):
        mcp_server.index_provider = self._original_provider
        super().tearDown()

    async def test_exposes_exactly_search_and_fetch(self):
        tools = await mcp_server.server.list_tools()
        self.assertEqual({t.name for t in tools}, {"search", "fetch"})

    async def test_source_choices_come_from_the_registry(self):
        tools = {t.name: t for t in await mcp_server.server.list_tools()}
        schema = tools["search"].input_schema
        self.assertIn(list(SOURCES), _find_enums(schema["properties"]["sources"]))

    async def test_search_results_are_labeled_with_source_and_link(self):
        result = await mcp_server.server.call_tool("search", {"query": "桃園會展中心"})

        results = {r["id"]: r for r in result.structured_content["results"]}
        self.assertEqual(set(results), {"article:4930", "ptt:M.1.A.001"})
        self.assertTrue(results["article:4930"]["official"])
        self.assertEqual(results["article:4930"]["source_label"], "官網公告")
        self.assertFalse(results["ptt:M.1.A.001"]["official"])
        self.assertTrue(results["ptt:M.1.A.001"]["url"].startswith("https://www.ptt.cc/"))

    async def test_fetch_returns_full_text_with_pushes(self):
        result = await mcp_server.server.call_tool("fetch", {"id": "ptt:M.1.A.001"})

        doc = result.structured_content
        self.assertIn("第一次來桃園會展中心", doc["text"])
        self.assertIn("alice", doc["text"])
        self.assertEqual((doc["page"], doc["total_pages"]), (1, 1))
        self.assertEqual(doc["metadata"]["source_label"], "PTT")

    async def test_bad_arguments_come_back_as_readable_reasons(self):
        for name, args, reason in (
            ("fetch", {"id": "telegram:1"}, "沒有這份文件"),
            ("fetch", {"id": "ptt:M.1.A.001", "page": 9}, "頁數超出範圍"),
            ("search", {"query": "演唱會", "since": "上個月"}, "YYYY-MM-DD"),
        ):
            with self.subTest(name=name, args=args):
                with self.assertRaises(ToolError) as ctx:
                    await mcp_server.server.call_tool(name, args)
                self.assertNotIsInstance(ctx.exception, UnexpectedToolError)  # 不是只剩「Error executing tool」
                self.assertIn(reason, str(ctx.exception))

    async def test_unknown_source_is_rejected_before_searching(self):
        with self.assertRaises(ToolError):
            await mcp_server.server.call_tool("search", {"query": "演唱會", "sources": ["telegram"]})

    async def test_question_reaches_the_reranker(self):
        stub = StubReranker()
        index = self.make_index(reranker=stub)
        mcp_server.index_provider = lambda: index

        await mcp_server.server.call_tool("search", {"query": "桃園會展中心", "question": "演唱會在哪裡辦？"})
        await mcp_server.server.call_tool("search", {"query": "桃園會展中心"})

        self.assertEqual(stub.queries, [normalize("演唱會在哪裡辦？"), normalize("桃園會展中心")])


if __name__ == "__main__":
    unittest.main()
