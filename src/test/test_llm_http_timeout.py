"""LLM 客戶端的逾時處理（llm/client/http_client.LlmHttpClient）。

守的底線：
  - 對話請求（/chat/completions）逾時不重試：逾時代表模型還在寫或後端卡住，再送只會讓同一題拿著顯示卡寫三遍
  - 其他 POST（例如 embedding）逾時照原本重試到用盡
  - 連線錯誤照樣重試（那才是連線抖動）

不打後端：把 httpx 的 post 換成會丟逾時的假物件、退避的 sleep 換成不等。
"""
import asyncio
import os
import sys
import unittest
from unittest import mock

import httpx

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from llm.client import http_client  # noqa: E402


class TimeoutRetryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.client = http_client.LlmHttpClient(base_url="http://backend", timeout=1.0, max_retries=2)
        self.addCleanup(self.client.close)
        self.posts = 0

        async def timing_out(*args, **kwargs):
            self.posts += 1
            raise httpx.ReadTimeout("still generating")

        self.client._async.post = timing_out
        self.enterContext(mock.patch.object(http_client.asyncio, "sleep", mock.AsyncMock()))

    async def test_chat_completion_timeout_is_not_retried(self):
        with self.assertRaises(http_client.LlmTimeoutError):
            await self.client.chat_completion(model="m", messages=[{"role": "user", "content": "hi"}])
        self.assertEqual(1, self.posts, "對話請求逾時只能打一次")

    async def test_connect_timeout_on_chat_still_retries(self):
        """連線階段的逾時是網路問題，不是模型在寫：對話請求也照舊重試。"""
        async def cannot_connect(*args, **kwargs):
            self.posts += 1
            raise httpx.ConnectTimeout("backend not answering the handshake")

        self.client._async.post = cannot_connect
        with self.assertRaises(http_client.LlmTimeoutError):
            await self.client.chat_completion(model="m", messages=[])
        self.assertEqual(3, self.posts)

    async def test_other_posts_still_retry_on_timeout(self):
        with self.assertRaises(http_client.LlmTimeoutError):
            await self.client._apost_json("/embeddings", {"input": "x"})
        self.assertEqual(3, self.posts, "非對話請求照原本重試兩次")

    async def test_connection_errors_on_chat_still_retry(self):
        async def refused(*args, **kwargs):
            self.posts += 1
            raise httpx.ConnectError("refused")

        self.client._async.post = refused
        with self.assertRaises(http_client.LlmConnectionError):
            await self.client.chat_completion(model="m", messages=[])
        self.assertEqual(3, self.posts)


if __name__ == "__main__":
    unittest.main()
