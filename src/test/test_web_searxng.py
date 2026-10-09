"""SearXNG 用戶端（`llm/retrievers/web/searxng.py` 的 `fetch_web_results`）：用一個假的 SearXNG（本機 aiohttp）測。

守的底線：
  - 每次查詢都帶成人內容過濾（`safesearch`）
  - 回應裡的 `unresponsive_engines` 記進 meta；被擋的（真人驗證、限流、拒絕存取，含 SearXNG 因此暫停的
    「Suspended: CAPTCHA」）記一行 WARNING，接下來一段時間不再問它（10-09 duckduckgo 被真人驗證擋了幾個小時，
    bot 只記「0 results」看不出來）
  - 只是一時沒回應（逾時；SearXNG 因逾時暫停幾秒的「Suspended: timeout」也是）不暫避
  - 全部引擎都在暫避時照原樣問，不會一個都不送
  - 暫避時間過了就恢復
  - 直接答案（匯率、天氣引擎的 `answers`）整理成文字放進 `answers`，不再丟掉；最多 3 則；
    關鍵字模式的 <web_context> 排在最前面標「[答]」；SearXNG 外掛的答案（self_info 會回主機 IP）不收
  - 天氣整理成地點（國別）、現在、往後最多 3 天的高低溫與天氣狀況：日期換成當地時間再分天；
    第一天不是從 0 點開始就標「剩下時段」，免得被當成整天的高低溫

執行：
    cd src && python -m unittest test.test_web_searxng -v
"""

import asyncio
import os
import sys
import unittest

from aiohttp import web

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from llm.retrievers.web import WebResult, fetch_web_results, format_web_context_lines  # noqa: E402
from llm.retrievers.web import searxng  # noqa: E402
from sys_settings.llm_settings import AskAIWebSettings  # noqa: E402


class FakeSearxng:
    """記下每次收到的參數；`unresponsive` 是下一次要回報的沒回應引擎。"""

    def __init__(self):
        self.requests = []
        self.unresponsive = []
        self.extra = {}

    async def handle(self, request):
        self.requests.append(dict(request.query))
        body = {
            "results": [{"url": "https://n.example/1", "title": "標題", "content": "摘要", "engine": "bing"}],
            "unresponsive_engines": self.unresponsive,
            **self.extra,
        }
        self.unresponsive = []
        return web.json_response(body)


def forecast(stamp, temperature, condition):
    return {"location": {"name": "Taipei"}, "temperature": {"val": temperature, "unit": "°C"},
            "condition": condition, "datetime": {"datetime": stamp}}


WEATHER = {
    "engine": "openmeteo", "template": "answer/weather.html",
    "current": {"location": {"name": "Taipei"}, "temperature": {"val": 23.2, "unit": "°C"},
                "condition": "partly cloudy", "humidity": {"val": 85}, "datetime": None},
    "forecasts": [forecast("2026-10-10T00:00:00", 23.5, "partly cloudy"),
                  forecast("2026-10-10T06:00:00", 27.8, "light drizzle"),
                  forecast("2026-10-10T09:00:00", 26.0, "partly cloudy"),
                  forecast("2026-10-11T00:00:00", 22.0, "overcast"),
                  forecast("2026-10-12T00:00:00", 21.0, "rain"),
                  forecast("2026-10-13T00:00:00", 20.0, "fog")],
}


class _FakeSearxngTestCase(unittest.IsolatedAsyncioTestCase):
    """每個測試開一個假的 SearXNG；`fetch` 打它一次。"""

    async def asyncSetUp(self):
        searxng._blocked_until.clear()
        self.addCleanup(searxng._blocked_until.clear)
        self.fake = FakeSearxng()
        app = web.Application()
        app.router.add_get("/search", self.fake.handle)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        self.settings = AskAIWebSettings(searxng_url=f"http://127.0.0.1:{port}/search",
                                         default_engines="bing,duckduckgo", blocked_engine_cooldown_seconds=60,
                                         safesearch=1, timeout_seconds=5)

    async def asyncTearDown(self):
        await self.runner.cleanup()

    async def fetch(self, settings=None, **kwargs):
        return await fetch_web_results("台積電 股價", settings=settings or self.settings, **kwargs)



class FetchWebResultsTests(_FakeSearxngTestCase):
    async def test_every_query_asks_for_safe_search(self):
        await self.fetch()
        self.assertEqual(self.fake.requests[0]["safesearch"], "1")
        self.assertEqual(self.fake.requests[0]["engines"], "bing,duckduckgo")

    async def test_a_blocked_engine_is_reported_and_skipped_for_a_while(self):
        self.fake.unresponsive = [["duckduckgo", "CAPTCHA"]]
        with self.assertLogs("llm.retrievers.web.searxng", "WARNING") as logs:
            first = await self.fetch()
        self.assertEqual(first.meta["unresponsive_engines"], [["duckduckgo", "CAPTCHA"]])
        self.assertTrue(any("duckduckgo" in line and "CAPTCHA" in line for line in logs.output))

        second = await self.fetch()

        self.assertEqual(self.fake.requests[1]["engines"], "bing")
        self.assertEqual(second.meta["skipped_engines"], ["duckduckgo"])

    async def test_other_kinds_of_block_count_too(self):
        for reason in ("too many requests", "access denied", "Suspended: CAPTCHA", "Suspended: too many requests"):
            with self.subTest(reason=reason):
                searxng._blocked_until.clear()
                self.fake.unresponsive = [["duckduckgo", reason]]
                with self.assertLogs("llm.retrievers.web.searxng", "WARNING"):
                    await self.fetch()
                await self.fetch()
                self.assertEqual(self.fake.requests[-1]["engines"], "bing")

    async def test_a_timeout_is_not_a_block(self):
        for reason in ("timeout", "Suspended: timeout", "Suspended: HTTP error"):
            with self.subTest(reason=reason):
                searxng._blocked_until.clear()
                self.fake.unresponsive = [["duckduckgo", reason]]
                with self.assertLogs("llm.retrievers.web.searxng", "INFO") as logs:
                    await self.fetch()
                self.assertFalse(any("WARNING" in line for line in logs.output))
                await self.fetch()
                self.assertEqual(self.fake.requests[-1]["engines"], "bing,duckduckgo")

    async def test_when_everything_is_blocked_it_still_asks(self):
        self.fake.unresponsive = [["bing", "CAPTCHA"], ["duckduckgo", "CAPTCHA"]]
        with self.assertLogs("llm.retrievers.web.searxng", "WARNING"):
            await self.fetch()

        result = await self.fetch()

        self.assertEqual(self.fake.requests[1]["engines"], "bing,duckduckgo")
        self.assertEqual(result.meta["skipped_engines"], [])

    async def test_the_engine_comes_back_after_the_cooldown(self):
        short = AskAIWebSettings(searxng_url=self.settings.searxng_url, default_engines="bing,duckduckgo",
                                 blocked_engine_cooldown_seconds=0.2, timeout_seconds=5)
        self.fake.unresponsive = [["duckduckgo", "CAPTCHA"]]
        with self.assertLogs("llm.retrievers.web.searxng", "WARNING"):
            await self.fetch(short)
        await asyncio.sleep(0.3)

        await self.fetch(short)

        self.assertEqual(self.fake.requests[1]["engines"], "bing,duckduckgo")



class DirectAnswerTests(_FakeSearxngTestCase):

    async def test_currency_answer_is_kept(self):
        self.fake.extra = {"answers": [{"engine": "currency", "url": "https://duckduckgo.com/?q=USD+to+TWD",
                                        "answer": "1.0 USD = 31.96 TWD"}]}
        result = await self.fetch(engines="currency")
        self.assertEqual(result.answers, ["1.0 USD = 31.96 TWD（currency）"])
        self.assertEqual(result.meta["answer_count"], 1)

    async def test_weather_names_the_country_and_marks_a_partial_today(self):
        weather = {**WEATHER, "current": {**WEATHER["current"],
                                          "location": {"name": "Zhongshan", "country_code": "CN"}},
                   "forecasts": [forecast("2026-10-09T15:00:00", 27.0, "clear sky"),
                                 forecast("2026-10-09T21:00:00", 24.0, "clear sky"),
                                 forecast("2026-10-10T00:00:00", 23.0, "rain")]}
        self.fake.extra = {"answers": [weather]}

        (line,) = (await self.fetch(engines="openmeteo")).answers

        self.assertTrue(line.startswith("Zhongshan（CN） 天氣"))
        self.assertIn("10-09（剩下時段）：24～27°C", line)
        self.assertIn("10-10：23～23°C，rain", line)

    async def test_weather_days_follow_the_local_clock(self):
        # SearXNG 給的是台灣時間；倫敦（夏令 UTC+1）的 10-10 是台灣 10-10 07:00 到 10-11 06:59
        london = {"name": "London", "country_code": "GB", "timezone": "Europe/London"}
        weather = {"engine": "openmeteo", "current": {"location": london, "temperature": {"val": 12}},
                   "forecasts": [{**forecast("2026-10-10T06:00:00", 9.0, "fog"), "location": london},
                                 {**forecast("2026-10-10T07:00:00", 10.0, "clear sky"), "location": london},
                                 {**forecast("2026-10-11T06:00:00", 15.0, "clear sky"), "location": london}]}
        self.fake.extra = {"answers": [weather]}

        (line,) = (await self.fetch(engines="openmeteo")).answers

        self.assertIn("10-09（剩下時段）：9～9°C，fog", line)
        self.assertIn("10-10：10～15°C，clear sky", line)

    async def test_weather_answer_becomes_a_short_forecast(self):
        self.fake.extra = {"answers": [WEATHER]}

        (line,) = (await self.fetch(engines="openmeteo")).answers

        self.assertTrue(line.startswith("Taipei 天氣（openmeteo 預報）：現在 23.2°C、partly cloudy、濕度 85%"))
        self.assertIn("10-10：23.5～27.8°C，partly cloudy、light drizzle", line)
        self.assertIn("10-11：22～22°C，overcast", line)
        self.assertIn("10-12", line)
        self.assertNotIn("10-13", line)                       # 最多 3 天

    async def test_plugin_answers_and_infoboxes_are_left_out(self):
        self.fake.extra = {"answers": [{"engine": "plugin: self_info", "answer": "Your IP is: 1.2.3.4"}],
                           "infoboxes": [{"infobox": "台積電", "content": "晶圓代工公司"}]}
        result = await self.fetch()
        self.assertEqual(result.answers, [])

    async def test_odd_answers_are_ignored_and_the_count_is_capped(self):
        self.fake.extra = {"answers": ["純文字", {"engine": "x"}, {"answer": "  "}] +
                                      [{"answer": f"答案{i}"} for i in range(5)]}
        result = await self.fetch()
        self.assertEqual(result.answers, ["答案0", "答案1", "答案2"])

    def test_keyword_mode_puts_answers_first(self):
        hit = WebResult(title="標題", url="https://n.example/1", snippet="摘要", engine="bing")
        self.assertEqual(format_web_context_lines([hit], ["1.0 USD = 31.96 TWD"]),
                         ["[答] 1.0 USD = 31.96 TWD", "[1] 標題 — 摘要 <https://n.example/1>"])
        self.assertEqual(format_web_context_lines([hit]), ["[1] 標題 — 摘要 <https://n.example/1>"])


if __name__ == "__main__":
    unittest.main()
