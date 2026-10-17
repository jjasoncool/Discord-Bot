"""一次網路搜尋（`llm/retrievers/web/search.py` 的 `search_web`）：/askai 的關鍵字模式與工具模式共用。

守的底線：
  - 新聞路由改送新聞引擎、不送 categories（同送時 SearXNG 取聯集，會把停用的引擎叫來陪跑）；有日期的引擎不限時間、
    結果照日期新到舊排，沒日期的引擎另外一次請求、用自己的時間條件、排在有日期的後面；只有一邊出錯不算整次失敗
  - 窄路由（限類別或限時間，任一個就算）結果太少：換通用引擎、不限類別與時間再查一次，合併去重、窄路由的排前面、不超過 top_k；
    經過記在 meta.fallback
  - 補查也沒結果：留著主搜的結果，meta 記下補查過
  - 不補查：主搜出錯（SearXNG 本身異常，重試無益）、結果夠多、本來就是通用不限時的
  - 同一個查詢（同字串、同路由）短時間內直接用上次的結果，少打引擎；出錯、0 筆、有引擎沒回應（結果不完整）的不記
  - 補查合併後，主搜的引擎狀況另外留在 meta，答案數照合併後的算
  - 直接答案（匯率、天氣、維基摘要）在快取與補查之後都留著；只有直接答案、沒有網頁也算有結果
  - 守衛：別處直接呼叫 `fetch_web_results` 會被擋

執行：
    cd src && python -m unittest test.test_web_search -v
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from llm.retrievers.web import WebResult, WebRetrievalOutcome, search_web  # noqa: E402
from llm.retrievers.web import search as web_search_module  # noqa: E402
from sys_settings.llm_settings import AskAIWebSettings  # noqa: E402
from test.test_shared_conventions import _find_direct_searxng_queries  # noqa: E402

SETTINGS = AskAIWebSettings(top_k=5, fallback_min_results=3)   # 容器的通用環境變數（TOP_K）會蓋預設值


def hit(n, prefix="a", date=None):
    return WebResult(title=f"{prefix}{n}", url=f"https://{prefix}.example/{n}", snippet="s", engine="bing",
                     published_date=date)


def outcome(results, error=None, answers=()):
    return WebRetrievalOutcome(results=list(results), meta={"result_count": len(results), "error": error},
                               answers=list(answers))


class SearchWebTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.calls = []
        self.replies = []
        web_search_module._cache.clear()
        self.addCleanup(web_search_module._cache.clear)

        async def fake_fetch(query, **kwargs):
            self.calls.append({"query": query, **kwargs})
            return self.replies.pop(0)

        patcher = mock.patch("llm.retrievers.web.search.fetch_web_results", side_effect=fake_fetch)
        patcher.start()
        self.addCleanup(patcher.stop)

    async def test_news_goes_to_the_news_engines_without_categories(self):
        self.replies = [outcome([hit(i) for i in range(5)]), outcome([])]

        await search_web("台股 收盤", settings=SETTINGS, categories="news")

        dated, undated = self.calls
        self.assertEqual((dated["engines"], dated["categories"], dated["time_range"]),
                         (SETTINGS.news_engines, None, None))                          # 有日期的引擎不限時間
        self.assertEqual((undated["engines"], undated["categories"], undated["time_range"]),
                         (SETTINGS.news_undated_engines, None, SETTINGS.news_undated_time_range))   # 沒日期的用自己的一週

    async def test_news_is_newest_first_with_undated_results_last(self):
        self.replies = [outcome([hit(1, date="2026-10-10"), hit(2, date="2026-10-16"), hit(3), hit(4, date="2026-10-14")]),
                        outcome([hit(9, "b"), hit(2, date="2026-10-16")])]           # 同一個網址兩邊都有：只留一份

        result = await search_web("颱風", settings=SETTINGS, categories="news")

        self.assertEqual([r.title for r in result.results], ["a2", "a4", "a1", "a3", "b9"])
        self.assertNotIn("fallback", result.meta, "合起來夠多就不補查")

    async def test_news_is_sorted_over_more_than_the_top_k_before_cutting(self):
        # SearXNG 回的是相關度順序；只抓前 5 筆再排，相關度第 6 名以後的新聞永遠進不來
        dated = [hit(i, date=f"2026-09-{10 + i:02d}") for i in range(1, 8)] + [hit(8, date="2026-10-16")]
        self.replies = [outcome(dated), outcome([])]

        result = await search_web("鳴潮 改版", settings=SETTINGS, categories="news")

        self.assertEqual(SETTINGS.top_k * 4, self.calls[0]["limit"], "有日期的那次多抓幾倍")
        self.assertEqual("a8", result.results[0].title, "最新的排第一，就算相關度排在第 8")
        self.assertEqual(SETTINGS.top_k, len(result.results))

    async def test_default_engines_leave_bing_out(self):
        # 24 小時穩定度測試：bing 對題只七成、常回 0 筆，回垃圾時 SearXNG 不算錯誤、會直接混進結果（出過成人內容）
        engines = AskAIWebSettings().default_engines.split(",")
        self.assertNotIn("bing", engines)
        self.assertIn("yahoo", engines)

    async def test_news_with_one_side_failing_is_not_a_failed_search(self):
        self.replies = [outcome([], error="timeout"), outcome([hit(i, "b") for i in range(3)])]

        result = await search_web("颱風", settings=SETTINGS, categories="news")

        self.assertIsNone(result.meta["error"])
        self.assertEqual(len(result.results), 3)
        self.assertEqual(result.meta["undated"]["result_count"], 3)

    async def test_too_few_narrow_results_are_topped_up_from_general_engines(self):
        self.replies = [outcome([hit(1), hit(2)]),
                        outcome([hit(2), hit(3, "b"), hit(4, "b"), hit(5, "b"), hit(6, "b")])]

        result = await search_web("颱風 動態", settings=SETTINGS, time_range="day", language="zh-TW")

        primary, fallback = self.calls
        self.assertEqual(primary["time_range"], "day")
        self.assertEqual((fallback["engines"], fallback["categories"], fallback["time_range"], fallback["language"]),
                         (None, None, None, "zh-TW"))
        self.assertEqual([r.title for r in result.results], ["a1", "a2", "b3", "b4", "b5"])   # 主搜在前、去重、top_k
        self.assertEqual(result.meta["fallback"]["result_count"], 5)
        self.assertEqual(result.meta["result_count"], 5)

    async def test_a_category_alone_is_narrow_too(self):
        self.replies = [outcome([hit(1)]), outcome([hit(2, "b"), hit(3, "b")])]

        result = await search_web("鳴潮 鄉民", settings=SETTINGS, categories="social media")

        primary, fallback = self.calls
        self.assertEqual((primary["categories"], primary["time_range"]), ("social media", None))
        self.assertEqual((fallback["categories"], fallback["time_range"]), (None, None))
        self.assertEqual([r.title for r in result.results], ["a1", "b2", "b3"])

    async def test_empty_fallback_keeps_the_primary_results(self):
        self.replies = [outcome([hit(1)]), outcome([]), outcome([])]      # 有日期的、沒日期的、補查

        result = await search_web("NBA 戰績", settings=SETTINGS, categories="news", time_range="week")

        self.assertEqual([r.title for r in result.results], ["a1"])
        self.assertTrue(result.meta["fallback"]["attempted"])

    async def test_no_fallback_when_it_would_not_help(self):
        cases = {
            "主搜出錯": (outcome([], error="timeout"), {"time_range": "day"}),
            "結果夠多": (outcome([hit(i) for i in range(3)]), {"time_range": "day"}),
            "本來就是通用不限時": (outcome([hit(1)]), {}),
        }
        for label, (first, route) in cases.items():
            with self.subTest(label):
                self.calls.clear()
                self.replies = [first]
                result = await search_web("q", settings=SETTINGS, **route)
                self.assertEqual(len(self.calls), 1)
                self.assertNotIn("fallback", result.meta)

    async def test_the_same_query_soon_after_reuses_the_last_answer(self):
        self.replies = [outcome([hit(i) for i in range(5)])]

        first = await search_web("颱風 動態", settings=SETTINGS)
        again = await search_web("颱風 動態", settings=SETTINGS)

        self.assertEqual(len(self.calls), 1)
        self.assertEqual([r.title for r in again.results], [r.title for r in first.results])
        self.assertTrue(again.meta["cached"])
        self.replies = [outcome([hit(i, "b") for i in range(5)])]
        await search_web("颱風 動態", settings=SETTINGS, time_range="day")    # 路由不同就重查
        self.assertEqual(len(self.calls), 2)

    async def test_errors_and_empty_answers_are_not_remembered(self):
        for label, first in (("出錯", outcome([], error="timeout")), ("0 筆", outcome([]))):
            with self.subTest(label):
                self.calls.clear()
                self.replies = [first, outcome([hit(1)])]
                await search_web(f"颱風 {label}", settings=SETTINGS)
                await search_web(f"颱風 {label}", settings=SETTINGS)
                self.assertEqual(len(self.calls), 2)

    async def test_direct_answers_survive_the_cache_and_the_top_up(self):
        self.replies = [outcome([], answers=["1.0 USD = 31.96 TWD"])]
        await search_web("1 USD to TWD", settings=SETTINGS)
        again = await search_web("1 USD to TWD", settings=SETTINGS)
        self.assertEqual((len(self.calls), again.answers), (1, ["1.0 USD = 31.96 TWD"]))

        self.replies = [outcome([hit(1)], answers=["颱風警報"]), outcome([hit(2, "b")])]
        topped_up = await search_web("颱風", settings=SETTINGS, time_range="day")
        self.assertEqual(topped_up.answers, ["颱風警報"])
        self.replies = [outcome([hit(1)], answers=["颱風警報"]), outcome([])]
        not_found = await search_web("颱風 2", settings=SETTINGS, time_range="day")
        self.assertEqual(not_found.answers, ["颱風警報"])

    async def test_named_engines_skip_the_category_choice(self):
        self.replies = [outcome([], answers=["Taipei 天氣"]), outcome([], answers=["1 USD = 31.96 TWD"])]

        await search_web("Taipei", settings=SETTINGS, engines="openmeteo", language="en")
        await search_web("Taipei", settings=SETTINGS, engines="currency", language="en")    # 引擎不同就不共用快取

        weather, currency = self.calls
        self.assertEqual((weather["engines"], weather["categories"], weather["language"]), ("openmeteo", None, "en"))
        self.assertEqual(currency["engines"], "currency")

    async def test_incomplete_results_are_not_remembered(self):
        partial = WebRetrievalOutcome(results=[hit(i) for i in range(5)],
                                      meta={"error": None, "unresponsive_engines": [["duckduckgo", "timeout"]]})
        self.replies = [partial, outcome([hit(i) for i in range(5)])]
        await search_web("颱風", settings=SETTINGS)
        await search_web("颱風", settings=SETTINGS)
        self.assertEqual(len(self.calls), 2)

    async def test_the_top_up_keeps_what_the_first_search_saw(self):
        primary = WebRetrievalOutcome(results=[hit(1)], answers=["颱風警報"],
                                      meta={"error": None, "unresponsive_engines": [["duckduckgo", "CAPTCHA"]]})
        self.replies = [primary, outcome([hit(2, "b"), hit(3, "b")])]

        merged = await search_web("颱風", settings=SETTINGS, time_range="day")

        self.assertEqual(merged.meta["primary_unresponsive_engines"], [["duckduckgo", "CAPTCHA"]])
        self.assertEqual(merged.meta["answer_count"], 1)

    async def test_cache_can_be_turned_off(self):
        no_cache = AskAIWebSettings(top_k=5, fallback_min_results=3, cache_seconds=0)
        self.replies = [outcome([hit(i) for i in range(5)]), outcome([hit(i) for i in range(5)])]
        await search_web("颱風", settings=no_cache)
        await search_web("颱風", settings=no_cache)
        self.assertEqual(len(self.calls), 2)


class DirectSearxngGuardTests(unittest.TestCase):
    def test_guard_flags_direct_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.py"
            path.write_text(
                "from llm.retrievers import web\n"
                "async def f(q, s):\n"
                "    a = await web.fetch_web_results(q, settings=s)\n"
                "    b = await web.search_web(q, settings=s)\n",
                encoding="utf-8",
            )
            self.assertEqual(_find_direct_searxng_queries(path), [3])


if __name__ == "__main__":
    unittest.main()
