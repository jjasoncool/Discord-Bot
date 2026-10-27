"""模型後端壞掉時的自癒與通知：`llm/client/lemonade_admin.py` 的 `LemonadeAdmin.heal`／`admin_for`、`http_client` 的
`is_backend_fault` 與薄迴圈叫 admin 重載的規則，`utils/dm_notifier.py` 的 `notify_owner_lemonade_heal`。

守的底線：
  - 5xx 的內容帶後端壞掉的訊號（ErrorDeviceLost、decode() failed、vk::、CUDA error）：重載那顆模型一次再重送原請求，
    sync 與 async 都一樣；看不懂的 5xx 照一般重試、不重載
  - 重載不看還剩幾次重試：不重試的呼叫端（拿著 GPU 閘門的 embedding、替 Hermes 轉送的 raw 與串流）後端壞了照樣重載，
    只是重載完不重送、照原錯誤丟出；重載等多久照客戶端的 heal_load_timeout（拿著閘門時是短的那個）
  - 每個模型 60 秒冷卻；一小時最多重載 3 次，第 4 次放棄：記一次 ERROR、通知一次，之後一小時內不再吵；重載失敗也通知
  - 自癒事件經 `lemonade_admin.set_heal_listener` 交給介面層；回呼出錯不影響原本的請求
  - 重載是後端專屬的事：只有 Lemonade 有 admin（`admin_for`），沒有 admin 的後端（Ollama）遇到同樣的 5xx 只照一般重試收尾
  - 群主私訊：三種結果各一行、帶模型與原因；`OWNER_ID` 沒設就不送

hermetic：假的 HTTP 回應、假的載入；不碰網路。

執行：
    cd src && python -m unittest test.test_lemonade_heal -v
"""

import asyncio
import contextlib
import os
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from llm.client import http_client, lemonade_admin  # noqa: E402
from llm.client.http_client import LlmAPIError, LlmConnectionError, LlmHttpClient, backend_looks_broken  # noqa: E402
from llm.client.backend_admin import admin_for  # noqa: E402
from llm.client.lemonade_admin import LemonadeAdmin  # noqa: E402
from utils import dm_notifier  # noqa: E402

BROKEN = '{"error":{"message":"decode() failed: vk::Queue::submit: ErrorDeviceLost","type":"server_error"}}'


def resp(status, text="", payload=None):
    return SimpleNamespace(is_success=status < 400, status_code=status, text=text, json=lambda: payload or {})


class HealOnBackendErrorTests(unittest.TestCase):
    def setUp(self):
        lemonade_admin.reset_cache()
        self.events = []
        lemonade_admin.set_heal_listener(self.events.append)
        self.addCleanup(lemonade_admin.set_heal_listener, None)
        self.addCleanup(lemonade_admin.reset_cache)
        patcher = mock.patch.object(http_client, "_backoff_delay", lambda attempt: 0)   # 不真的睡
        patcher.start()
        self.addCleanup(patcher.stop)

    def client(self, *responses, heal_load_timeout=120.0, **kwargs):
        admin = LemonadeAdmin("http://backend.test", heal_load_timeout=heal_load_timeout)
        admin.load = mock.Mock()   # 不真的打管理 API
        client = LlmHttpClient(base_url="http://backend.test", timeout=1.0, admin=admin, **kwargs)
        client._sync = SimpleNamespace(post=mock.Mock(side_effect=list(responses)))
        client._async = SimpleNamespace(post=mock.AsyncMock(side_effect=list(responses)))
        return client

    def test_signatures(self):
        self.assertTrue(backend_looks_broken(LlmAPIError("HTTP 500", status=500, detail=BROKEN)))
        self.assertTrue(backend_looks_broken(LlmAPIError("HTTP 503", status=503, detail="CUDA error: device-side assert")))
        self.assertFalse(backend_looks_broken(LlmAPIError("HTTP 500", status=500, detail="boom")))
        self.assertFalse(backend_looks_broken(LlmAPIError("HTTP 400", status=400, detail=BROKEN)))

    def test_sync_device_error_reloads_the_model_once_and_retries(self):
        client = self.client(resp(500, BROKEN), resp(200, payload={"data": [{"embedding": [0.1]}]}))
        self.assertEqual(client.embedding(model="emb", input="x"), [[0.1]])
        client.admin.load.assert_called_once()
        self.assertEqual(client.admin.load.call_args.kwargs["model_name"], "emb")
        self.assertFalse(client.admin.load.call_args.kwargs["save_options"], "只重生、不覆寫 recipe options")
        self.assertEqual([e["outcome"] for e in self.events], ["healed"])
        self.assertIn("ErrorDeviceLost", self.events[0]["reason"])

    def test_async_path_does_the_same(self):
        client = self.client(resp(500, BROKEN), resp(200, payload={"data": [{"embedding": [0.2]}]}))
        self.assertEqual(asyncio.run(client.aembedding(model="emb", input="x")), [[0.2]])
        client.admin.load.assert_called_once()
        self.assertEqual([e["outcome"] for e in self.events], ["healed"])

    def test_unknown_5xx_is_retried_but_never_reloads(self):
        client = self.client(resp(500, "boom"), resp(500, "boom"), resp(500, "boom"))
        with self.assertRaises(LlmAPIError):
            client.embedding(model="emb", input="x")
        client.admin.load.assert_not_called()
        self.assertEqual(self.events, [])

    def test_cooldown_allows_one_reload_per_minute(self):
        client = self.client(resp(500, BROKEN), resp(500, BROKEN), resp(500, BROKEN))
        with self.assertRaises(LlmAPIError):
            client.embedding(model="emb", input="x")
        client.admin.load.assert_called_once()        # 第二次 5xx 在冷卻內：不再重載，照一般重試收尾

    def test_hourly_cap_gives_up_once_then_stays_quiet(self):
        client = self.client()
        with mock.patch.object(lemonade_admin, "_HEAL_COOLDOWN_S", 0.0):
            results = [client.admin.heal("emb", reason="r") for _ in range(3)]
            with self.assertLogs("llm.client.lemonade_admin", "ERROR") as logs:
                fourth = client.admin.heal("emb", reason="r")
            fifth = client.admin.heal("emb", reason="r")
        self.assertEqual(results, [True, True, True])
        self.assertFalse(fourth)
        self.assertFalse(fifth)
        self.assertEqual(client.admin.load.call_count, 3)
        self.assertEqual([e["outcome"] for e in self.events], ["healed", "healed", "healed", "gave_up"], "放棄只通知一次")
        self.assertEqual(len([l for l in logs.output if "自癒放棄" in l]), 1)
        self.assertEqual(self.events[-1]["heals"], 3)

    def test_failed_reload_reports_and_returns_false(self):
        client = self.client()
        client.admin.load.side_effect = LlmConnectionError("admin down")
        with self.assertLogs("llm.client.lemonade_admin", "WARNING"):
            self.assertFalse(client.admin.heal("emb", reason="r"))
        self.assertEqual([e["outcome"] for e in self.events], ["failed"])
        self.assertIn("admin down", self.events[0]["reason"])

    def test_no_retry_client_reloads_then_raises_the_original_error(self):
        client = self.client(resp(500, BROKEN), resp(200, payload={"data": [{"embedding": [0.1]}]}), max_retries=0)
        with self.assertRaises(LlmAPIError):
            client.embedding(model="emb", input="x")
        client.admin.load.assert_called_once()
        self.assertEqual(client._sync.post.call_count, 1, "沒有重試額度：重載完不重送")
        self.assertEqual([e["outcome"] for e in self.events], ["healed"])

    def test_raw_forwarding_reloads_on_device_error_without_resending(self):
        client = self.client(resp(500, BROKEN), resp(200, payload={"choices": []}))
        with self.assertRaises(LlmAPIError):
            asyncio.run(client.chat_completion_raw({"model": "chat", "messages": []}))
        client.admin.load.assert_called_once()
        self.assertEqual(client.admin.load.call_args.kwargs["model_name"], "chat")
        self.assertEqual(client._async.post.await_count, 1)

    def test_stream_reloads_on_device_error(self):
        broken = SimpleNamespace(is_success=False, status_code=500, text=BROKEN, aread=mock.AsyncMock())

        @contextlib.asynccontextmanager
        async def stream(*args, **kwargs):
            yield broken

        client = self.client()
        client._async = SimpleNamespace(stream=stream)

        async def run():
            async with client.chat_completion_stream({"model": "chat", "messages": []}):
                pass

        with self.assertRaises(LlmAPIError):
            asyncio.run(run())
        client.admin.load.assert_called_once()
        self.assertEqual(client.admin.load.call_args.kwargs["model_name"], "chat")

    def test_reload_waits_the_client_load_timeout(self):
        client = self.client(heal_load_timeout=60.0)
        self.assertTrue(client.admin.heal("emb", reason="r"))
        self.assertEqual(client.admin.load.call_args.kwargs["timeout"], 60.0)

    def test_gated_embedding_client_reloads_with_its_short_load_timeout(self):
        from llm.client.embedding_client import SafeLLMEmbedding

        embedding = SafeLLMEmbedding(model_name="emb", base_url="http://backend.test", backend="lemonade",
                                     max_retries=0, load_timeout=45.0)
        self.assertEqual(embedding._http_client.admin._heal_load_timeout, 45.0)
        self.assertEqual(embedding._http_client._max_retries, 0)

    def test_backend_without_admin_never_reloads(self):
        client = LlmHttpClient(base_url="http://backend.test", timeout=1.0, max_retries=0)
        client._sync = SimpleNamespace(post=mock.Mock(side_effect=[resp(500, BROKEN)]))
        with self.assertRaises(LlmAPIError):
            client.embedding(model="emb", input="x")
        self.assertEqual(self.events, [], "沒有管理 API 的後端不重載")

    def test_only_lemonade_reloads(self):
        from llm.client.embedding_client import SafeLLMEmbedding
        from llm.client.ollama_admin import OllamaAdmin

        self.assertIsInstance(admin_for("lemonade", "http://backend.test"), LemonadeAdmin)
        self.assertIsInstance(admin_for("ollama", "http://backend.test"), OllamaAdmin)
        self.assertIsNone(admin_for("vllm", "http://backend.test"))
        self.assertIsNone(SafeLLMEmbedding(model_name="emb", base_url="http://backend.test", backend="vllm")._http_client.admin)
        # Ollama 有 admin（會卸載）但沒有重載 API：同樣的 5xx 不重載、照原錯誤丟
        client = LlmHttpClient(base_url="http://backend.test", timeout=1.0, max_retries=0, admin=OllamaAdmin("http://backend.test"))
        client._sync = SimpleNamespace(post=mock.Mock(side_effect=[resp(500, BROKEN)]))
        with self.assertRaises(LlmAPIError):
            client.embedding(model="emb", input="x")
        self.assertEqual(self.events, [])

    def test_envelope_is_only_unwrapped_through_the_admin(self):
        payload = {"error": {"type": "server_error", "message": "boom"}}
        with_admin = self.client(resp(200, payload=payload))
        with self.assertRaises(LlmAPIError) as caught:
            with_admin.embedding(model="emb", input="x")
        self.assertIn("envelope", str(caught.exception), "有 admin 才認得信封，錯誤要講出 upstream 的原文")
        plain = LlmHttpClient(base_url="http://backend.test", timeout=1.0)
        plain._sync = SimpleNamespace(post=mock.Mock(side_effect=[resp(200, payload={"data": [{"embedding": [0.3]}]})]))
        self.assertEqual(plain.embedding(model="emb", input="x"), [[0.3]])

    def test_listener_errors_do_not_break_the_request(self):
        lemonade_admin.set_heal_listener(lambda event: (_ for _ in ()).throw(RuntimeError("dm broke")))
        client = self.client(resp(500, BROKEN), resp(200, payload={"data": [{"embedding": [0.1]}]}))
        with self.assertLogs("llm.client.lemonade_admin", "WARNING"):
            self.assertEqual(client.embedding(model="emb", input="x"), [[0.1]])


class OwnerNoticeTests(unittest.IsolatedAsyncioTestCase):
    def test_each_outcome_has_its_own_line(self):
        healed = dm_notifier.lemonade_heal_notice({"outcome": "healed", "model": "emb", "reason": "ErrorDeviceLost", "heals": 1})
        gave_up = dm_notifier.lemonade_heal_notice({"outcome": "gave_up", "model": "emb", "reason": "ErrorDeviceLost", "heals": 3})
        failed = dm_notifier.lemonade_heal_notice({"outcome": "failed", "model": "emb", "reason": "admin down"})
        self.assertIn("已重載", healed)
        self.assertIn("第 1 次", healed)
        self.assertIn("放棄", gave_up)
        self.assertIn("3 次", gave_up)
        self.assertIn("失敗", failed)
        for text in (healed, gave_up, failed):
            self.assertIn("emb", text)

    async def test_owner_gets_a_dm_only_when_owner_id_is_set(self):
        sent = []

        async def fake_send(user, *, content=None, **kwargs):
            sent.append((user, content))
            return True

        with mock.patch.object(dm_notifier, "resolve_user", mock.AsyncMock(return_value="owner-user")), \
             mock.patch.object(dm_notifier, "send_dm", fake_send):
            with mock.patch.dict(os.environ, {"OWNER_ID": "0"}):
                self.assertFalse(await dm_notifier.notify_owner_lemonade_heal(None, {"outcome": "healed", "model": "emb"}))
            self.assertEqual(sent, [])
            with mock.patch.dict(os.environ, {"OWNER_ID": "5"}):
                self.assertTrue(await dm_notifier.notify_owner_lemonade_heal(None, {"outcome": "healed", "model": "emb", "reason": "r", "heals": 1}))
        self.assertEqual(sent[0][0], "owner-user")
        self.assertIn("emb", sent[0][1])


if __name__ == "__main__":
    unittest.main()
