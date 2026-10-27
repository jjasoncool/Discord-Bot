"""後端 admin 的登記與 Ollama 的 admin：`llm/client/backend_admin.py`、`llm/client/ollama_admin.py`。

守的底線：
  1. `admin_for`：lemonade → LemonadeAdmin、ollama → OllamaAdmin、其他（vLLM、None）→ None；通用流程靠這個 None 不做後端專屬的事。
  2. OllamaAdmin：卸載是空的 /api/generate 帶 keep_alive=0（不走對話端點）；非 2xx 丟 LlmAPIError、連不上丟 LlmConnectionError；
     沒有載入與重載 API：ensure_loaded 不打任何東西、heal 回 False、unwrap 原樣回。

不打網路：把 httpx 的 post 換成假的。
"""

import os
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

import httpx

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from llm.client.backend_admin import admin_for  # noqa: E402
from llm.client.http_client import LlmAPIError, LlmConnectionError  # noqa: E402
from llm.client.lemonade_admin import LemonadeAdmin  # noqa: E402
from llm.client.ollama_admin import OllamaAdmin  # noqa: E402


class AdminForTests(unittest.TestCase):
    def test_each_backend_gets_its_own_admin_or_none(self):
        self.assertIsInstance(admin_for("lemonade", "http://b"), LemonadeAdmin)
        self.assertIsInstance(admin_for("ollama", "http://b"), OllamaAdmin)
        self.assertIsNone(admin_for("vllm", "http://b"))
        self.assertIsNone(admin_for(None, "http://b"))


class OllamaAdminTests(unittest.TestCase):
    def _admin(self, post):
        admin = OllamaAdmin("http://ollama.test/")
        admin._http = SimpleNamespace(post=post)
        return admin

    def test_unload_sends_keep_alive_zero_to_generate(self):
        post = mock.Mock(return_value=SimpleNamespace(is_success=True, status_code=200, text=""))
        self._admin(post).unload(model="m1")
        url, kwargs = post.call_args.args[0], post.call_args.kwargs
        self.assertEqual(url, "http://ollama.test/api/generate")
        self.assertEqual(kwargs["json"], {"model": "m1", "keep_alive": 0})

    def test_unload_failures_use_the_shared_exceptions(self):
        bad = mock.Mock(return_value=SimpleNamespace(is_success=False, status_code=500, text="boom"))
        with self.assertRaises(LlmAPIError):
            self._admin(bad).unload(model="m1")
        with self.assertRaises(LlmConnectionError):
            self._admin(mock.Mock(side_effect=httpx.ConnectError("refused"))).unload(model="m1")

    def test_no_load_or_reload_api(self):
        post = mock.Mock()
        admin = self._admin(post)
        admin.ensure_loaded(model="m1", options={"ctx_size": 8192})
        self.assertFalse(admin.heal("m1", reason="r"))
        self.assertEqual(admin.unwrap({"data": [1]}), {"data": [1]})
        post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
