"""網路搜尋做成給模型的工具（`llm/retrievers/web/tools.py` 的 `WebSearchTools`）：/askai 的 `askai_web_search_mode=tool`。

守的底線：
  - 宣告一個 web_search 工具，query 必填、kind（題目類型）選填；使用規則讀 `askai_web_rules.txt`（正式環境的預設路徑讀得到，
    只在有這個工具時才給模型）
  - 說明與規則不把《鳴潮》寫死排除：情報工具不在時（開關關著、search-mcp 連不上）只剩這個工具，遊戲問題也要能查
  - 題目類型由模型選，不用關鍵字分類（關鍵字過濾分不準）：一般搜尋不限時間；新聞也不限時間（結果照日期新到舊排，排法在 search）；
    天氣、匯率指定專用引擎（天氣用英文語系）；查詢字沒有中文時用英文語系；沒給 kind 就是一般；不認得的 kind 回錯誤
  - 天氣、匯率的查詢字先整理成引擎認得的樣子（天氣只留英文地名、匯率整理成「1000 USD to TWD」）
  - 天氣、匯率的引擎有跑卻沒答案時回寫法提示（note）；引擎這次沒回應時照實回錯誤，不叫模型改寫
  - 查詢字只去掉「幫我查」這類贅字，不套用關鍵字模式的新聞剝字（會切壞專有名詞、把中文查詢誤判成英文）
  - 結果只給回答用得到的欄位（標題、網址、摘要、日期取到日）；經過記在 `calls`（查了什麼、走哪條路由、幾筆、補查）
  - 直接答案（匯率、天氣、維基摘要）排在網頁結果前面；只有直接答案時就算 SearXNG 回報錯誤也照給
  - 任何失敗（參數錯、空查詢、不認得的工具、SearXNG 出錯、意外例外）都回 `{"error": ...}`，不往外丟

執行：
    cd src && python -m unittest test.test_web_tools -v
"""

import asyncio
import json
import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from llm.retrievers.web import WebResult, WebRetrievalOutcome, WebSearchTools  # noqa: E402
from sys_settings.llm_settings import AskAIWebSettings  # noqa: E402

SETTINGS = AskAIWebSettings()
RULES_FILE = os.path.join(SRC_DIR, "settings", "prompts", "askai_web_rules.txt")


def hits(*dates):
    return [WebResult(title=f"t{i}", url=f"https://n.example/{i}", snippet=f"s{i}", engine="bing", published_date=d)
            for i, d in enumerate(dates)]


class WebSearchToolsTests(unittest.TestCase):
    def setUp(self):
        self.searches = []
        self.outcome = WebRetrievalOutcome(results=hits("2026-10-09T08:00:00", None), meta={"error": None})

        async def fake_search(query, **kwargs):
            self.searches.append({"query": query, **kwargs})
            if isinstance(self.outcome, Exception):
                raise self.outcome
            return self.outcome

        patcher = mock.patch("llm.retrievers.web.tools.search_web", side_effect=fake_search)
        patcher.start()
        self.addCleanup(patcher.stop)

    def tools(self):
        return WebSearchTools(settings=SETTINGS, instructions="【網路搜尋規則】")

    def run_tool(self, runner, arguments, name="web_search"):
        return json.loads(asyncio.run(runner.execute(name, arguments)))

    def test_declares_one_tool_with_a_required_query_and_a_kind(self):
        (tool,) = self.tools().tools
        params = tool["function"]["parameters"]
        self.assertEqual(tool["function"]["name"], "web_search")
        self.assertEqual(params["required"], ["query"])
        self.assertEqual(params["properties"]["kind"]["enum"], ["general", "news", "weather", "currency"])

    def test_rules_come_from_the_default_rules_file(self):
        with open(RULES_FILE, encoding="utf-8") as f:
            expected = f.read().strip()
        runner = WebSearchTools(settings=AskAIWebSettings())                   # 正式環境的預設路徑
        self.assertEqual(runner.instructions.strip(), expected)
        self.assertIn("【網路搜尋規則】", runner.instructions)

    def test_game_questions_can_use_it_when_there_is_no_intel_tool(self):
        (tool,) = self.tools().tools
        description = tool["function"]["description"]
        self.assertNotIn("《鳴潮》以外", description)
        self.assertIn("沒有時也用這個查", description)
        with open(RULES_FILE, encoding="utf-8") as f:
            rules = f.read()
        self.assertNotIn("《鳴潮》以外", rules)
        self.assertIn("沒有 search 可以用時", rules)

    def route(self, search):
        return tuple(search[key] for key in ("categories", "time_range", "language", "engines"))

    def test_general_has_no_time_range_and_no_keyword_routing(self):
        runner = self.tools()

        self.run_tool(runner, '{"query": "幫我查 台北 天氣 明天"}')                    # 沒給 kind：一般搜尋
        self.run_tool(runner, '{"query": "台積電 股價 今天", "kind": "general"}')

        weather_words, stock = self.searches
        self.assertEqual(weather_words["query"], "台北 天氣 明天")                   # 去掉「幫我查」
        self.assertEqual(self.route(weather_words), (None, None, None, None))      # 不因「天氣」「今天」被分去別類
        self.assertEqual(self.route(stock), (None, None, None, None))
        self.assertEqual(runner.calls[0]["kind"], "general")

    def test_news_is_not_limited_in_time_and_keeps_the_model_keywords(self):
        runner = self.tools()

        self.run_tool(runner, '{"query": "nasdaq tech stocks", "kind": "news"}')
        self.run_tool(runner, '{"query": "iPhone 17 新聞", "kind": "news"}')

        english, chinese = self.searches
        self.assertEqual(self.route(english), ("news", None, "en", None))          # 沒有中文：英文語系；不限時間
        self.assertEqual(chinese["query"], "iPhone 17 新聞")                       # 不剝字
        self.assertEqual(self.route(chinese), ("news", None, None, None))          # 有中文就用中文語系

    def test_weather_and_currency_use_their_own_engines(self):
        self.outcome = WebRetrievalOutcome(results=[], meta={"error": None}, answers=["答案"])
        runner = self.tools()

        self.run_tool(runner, '{"query": "Taipei", "kind": "weather"}')
        self.run_tool(runner, '{"query": "1 USD to TWD", "kind": "currency"}')

        weather, currency = self.searches
        self.assertEqual(self.route(weather), (None, None, "en", SETTINGS.weather_engines))
        self.assertEqual(self.route(currency), (None, None, "en", SETTINGS.currency_engines))
        self.assertEqual(runner.calls[0]["route"]["engines"], SETTINGS.weather_engines)

    def test_weather_and_currency_queries_are_tidied_for_their_engines(self):
        self.outcome = WebRetrievalOutcome(results=[], meta={"error": None}, answers=["答案"])
        runner = self.tools()

        self.run_tool(runner, '{"query": "Taipei tomorrow weather", "kind": "weather"}')
        self.run_tool(runner, '{"query": "New Taipei", "kind": "weather"}')
        self.run_tool(runner, '{"query": "台北", "kind": "weather"}')
        self.run_tool(runner, '{"query": "換 1,000 usd to twd", "kind": "currency"}')

        self.assertEqual([s["query"] for s in self.searches],
                         ["Taipei", "New Taipei", "台北", "1000 USD to TWD"])

    def test_a_silent_engine_is_not_reported_as_a_wrong_query(self):
        self.outcome = WebRetrievalOutcome(results=[], answers=[],
                                           meta={"error": None, "unresponsive_engines": [["openmeteo", "timeout"]]})
        reply = self.run_tool(self.tools(), '{"query": "Taipei", "kind": "weather"}')
        self.assertIn("天氣服務這次沒回應", reply["error"])
        self.assertNotIn("note", reply)

    def test_no_direct_answer_tells_the_model_how_to_ask(self):
        self.outcome = WebRetrievalOutcome(results=[], meta={"error": None})
        for kind, words in (("weather", "英文地名"), ("currency", "1 USD to TWD")):
            with self.subTest(kind=kind):
                reply = self.run_tool(self.tools(), json.dumps({"query": "台北", "kind": kind}))
                self.assertIn(words, reply["note"])
                self.assertEqual(reply["answers"], [])
        reply = self.run_tool(self.tools(), '{"query": "台北", "kind": "general"}')
        self.assertNotIn("note", reply)
        self.assertEqual(self.searches[0]["language"], "en")          # 天氣就算給了中文地名也用英文語系

    def test_unknown_kind_is_an_error_for_the_model(self):
        reply = self.run_tool(self.tools(), '{"query": "台北", "kind": "stocks"}')
        self.assertIn("general", reply["error"])
        self.assertEqual(self.searches, [])

    def test_results_are_compact_and_the_call_is_recorded(self):
        fallback = {"attempted": True, "result_count": 2, "error": None}
        self.outcome = WebRetrievalOutcome(results=self.outcome.results, meta={"error": None, "fallback": fallback})
        runner = self.tools()

        reply = self.run_tool(runner, '{"query": "颱風 動態"}')

        self.assertEqual(reply["results"][0], {"title": "t0", "url": "https://n.example/0", "snippet": "s0",
                                               "published_date": "2026-10-09"})
        self.assertNotIn("published_date", reply["results"][1])
        (call,) = runner.calls
        self.assertEqual((call["tool"], call["query"], call["result_count"]), ("web_search", "颱風 動態", 2))
        self.assertEqual(call["result_urls"], ["https://n.example/0", "https://n.example/1"])
        self.assertEqual(call["fallback"], fallback)
        self.assertNotIn("error", call)

    def test_direct_answers_come_first(self):
        self.outcome = WebRetrievalOutcome(results=hits(None), meta={"error": None}, answers=["1.0 USD = 31.96 TWD"])
        runner = self.tools()

        reply = self.run_tool(runner, '{"query": "1 USD to TWD"}')

        self.assertEqual(list(reply), ["answers", "results"])
        self.assertEqual(reply["answers"], ["1.0 USD = 31.96 TWD"])
        self.assertEqual(runner.calls[0]["answer_count"], 1)

    def test_an_answer_is_enough_even_when_searxng_reports_an_error(self):
        self.outcome = WebRetrievalOutcome(results=[], meta={"error": "timeout"}, answers=["Taipei 天氣"])
        self.assertEqual(self.run_tool(self.tools(), '{"query": "Taipei"}'), {"answers": ["Taipei 天氣"], "results": []})

    def test_failures_come_back_to_the_model(self):
        cases = {
            "參數不是 JSON": ("web_search", "{壞掉"),
            "空的查詢": ("web_search", '{"query": "  "}'),
            "不認得的工具": ("weather", '{"query": "台北"}'),
        }
        for label, (name, arguments) in cases.items():
            with self.subTest(label):
                runner = self.tools()
                reply = self.run_tool(runner, arguments, name=name)
                self.assertIn("error", reply)
                self.assertIn("error", runner.calls[0])
        self.assertEqual(self.searches, [])

    def test_searxng_errors_and_surprises_do_not_escape(self):
        self.outcome = WebRetrievalOutcome(results=[], meta={"error": "timeout"})
        self.assertIn("timeout", self.run_tool(self.tools(), '{"query": "颱風"}')["error"])

        self.outcome = RuntimeError("boom")
        with self.assertLogs("llm.retrievers.web.tools", level="WARNING"):
            self.assertIn("RuntimeError", self.run_tool(self.tools(), '{"query": "颱風"}')["error"])


if __name__ == "__main__":
    unittest.main()
