"""SearXNG 用戶端（`llm/retrievers/web/searxng.py` 的 `fetch_web_results`）：用一個假的 SearXNG（本機 aiohttp）測。

守的底線：
  - 每次查詢都帶成人內容過濾（`safesearch`）
  - 回應裡的 `unresponsive_engines` 記進 meta；被擋的（真人驗證、限流、拒絕存取，含 SearXNG 因此暫停的
    「Suspended: CAPTCHA」）記一行 WARNING，接下來一段時間不再問它（10-09 duckduckgo 被真人驗證擋了幾個小時，
    bot 只記「0 results」看不出來）
  - 只是一時沒回應（逾時；SearXNG 因逾時暫停幾秒的「Suspended: timeout」也是）不暫避
  - 全部引擎都在暫避時照原樣問，不會一個都不送
  - 暫避時間過了就恢復

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

from llm.retrievers.web import fetch_web_results  # noqa: E402
from llm.retrievers.web import searxng  # noqa: E402
from sys_settings.llm_settings import AskAIWebSettings  # noqa: E402


class FakeSearxng:
    """記下每次收到的參數；`unresponsive` 是下一次要回報的沒回應引擎。"""

    def __init__(self):
        self.requests = []
        self.unresponsive = []

    async def handle(self, request):
        self.requests.append(dict(request.query))
        body = {
            "results": [{"url": "https://n.example/1", "title": "標題", "content": "摘要", "engine": "bing"}],
            "unresponsive_engines": self.unresponsive,
        }
        self.unresponsive = []
        return web.json_response(body)


class FetchWebResultsTests(unittest.IsolatedAsyncioTestCase):
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


if __name__ == "__main__":
    unittest.main()
