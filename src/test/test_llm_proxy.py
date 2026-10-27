"""Hermes 的模型端點（`services/llm_proxy.py`，掛在通知伺服器的 /v1）。

守的底線：
  - 只認 Bearer HERMES_API_KEY：沒帶、帶錯、或帶通知密鑰都回 401；沒設金鑰就根本不掛路由
  - 模型名不是 bot 正在用的那個回 400，而且不碰閘門、不打後端
  - 整段回應都拿著 GPU 閘門（持有者標 hermes），結束才放；串流每寫一塊就續租
  - 請求原樣送出：只夾 max_tokens 上限、串流補 include_usage；後端的回應（JSON 或 SSE 每一行）原樣交回去
  - 每次請求記一行 llm_usage feature=hermes（串流從最後一塊取）
  - 等閘門超過上限回 503＋Retry-After；正在產圖直接 503；後端非 2xx 的狀態碼與本文原樣交回；
    後端連不上或逾時回 503；串流途中出錯在串流裡回報、閘門照放
  - 通知伺服器掛路由時放大本文上限、開 handler_cancellation（對方斷線就取消、放鎖）

後端、閘門、LLMService 都換成假的；aiohttp 用測試用的本機伺服器（隨機 port、只在本機）。

執行：
    cd src && python -m unittest test.test_llm_proxy -v
"""
import asyncio
import contextlib
import json
import os
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from llm.client import gpu_gate  # noqa: E402
from llm.client.http_client import LlmAPIError, LlmTimeoutError  # noqa: E402
from services import llm_proxy, notify_server  # noqa: E402
from sys_settings.hermes_settings import HermesSettings  # noqa: E402
from sys_settings.notify_settings import NotifyServerSettings  # noqa: E402

KEY = "test-key-0123456789"
MODEL = "main-model"
AUTH = {"Authorization": f"Bearer {KEY}"}


class FakeLease:
    def __init__(self):
        self.renewals = 0

    def renew(self):
        self.renewals += 1


class FakeGate:
    """記下進出；`block=True` 時永遠進不去（模擬別人佔著 GPU）。"""

    def __init__(self, *, block=False):
        self.block = block
        self.events = []
        self.lease = FakeLease()

    @contextlib.asynccontextmanager
    async def __call__(self, owner, lease_seconds=None):
        if self.block:
            await asyncio.Event().wait()
        self.events.append(("enter", owner, lease_seconds))
        try:
            yield self.lease
        finally:
            self.events.append(("exit", owner))


class FakeUpstream:
    """假的 LlmHttpClient：記下送出的本文；回應、SSE 行、要丟的例外都由測試指定。"""

    def __init__(self, *, completion=None, lines=None, error=None, fail_after=None):
        self.completion = completion or {"choices": [{"message": {"content": "hi"}}], "usage": {"prompt_tokens": 3}}
        self.lines = lines or []
        self.error = error
        self.fail_after = fail_after
        self.calls = []

    async def chat_completion_raw(self, body, *, timeout=None):
        self.calls.append(("raw", body))
        if self.error:
            raise self.error
        return self.completion

    @contextlib.asynccontextmanager
    async def chat_completion_stream(self, body, *, timeout=None):
        self.calls.append(("stream", body))
        if self.error:
            raise self.error
        yield self

    async def aiter_lines(self):
        for index, line in enumerate(self.lines):
            if self.fail_after is not None and index == self.fail_after:
                raise LlmTimeoutError("後端讀取逾時")
            yield line


def fake_llm(model=MODEL):
    return SimpleNamespace(resolve_request_model=lambda: model, ensure_model_loaded=mock.AsyncMock())


SSE_LINES = [
    'data: {"choices":[{"delta":{"content":"你"}}]}', "",
    'data: {"choices":[{"delta":{"content":"好"}}]}', "",
    'data: {"choices":[],"usage":{"prompt_tokens":10,"completion_tokens":2},"timings":{"cache_n":4,"prompt_n":6}}', "",
    "data: [DONE]", "",
]


class ProxyTestBase(unittest.IsolatedAsyncioTestCase):
    def settings(self, **overrides):
        values = {"api_key": KEY, "proxy_max_wait_seconds": 0.05, "proxy_retry_after_seconds": 7, "proxy_max_tokens": 256}
        values.update(overrides)
        return HermesSettings(**values)

    async def client_for(self, proxy):
        app = web.Application()
        proxy.add_routes(app)
        client = TestClient(TestServer(app))
        await client.start_server()
        self.addAsyncCleanup(client.close)
        return client

    def proxy(self, *, upstream=None, gate=None, llm=None, **settings):
        self.upstream = upstream or FakeUpstream()
        self.gate = gate or FakeGate()
        return llm_proxy.LlmProxy(self.settings(**settings), llm=llm or fake_llm(), client=self.upstream, gate=self.gate)


class AuthAndAllowlistTests(ProxyTestBase):
    async def test_missing_wrong_or_notify_secret_is_rejected(self):
        client = await self.client_for(self.proxy())
        for headers in ({}, {"Authorization": "Bearer nope"}, {notify_server.SECRET_HEADER: KEY}):
            with self.subTest(headers=headers):
                response = await client.post("/v1/chat/completions", json={"model": MODEL, "messages": []}, headers=headers)
                self.assertEqual(401, response.status)
                response = await client.get("/v1/models", headers=headers)
                self.assertEqual(401, response.status)
        self.assertEqual([], self.gate.events, "沒通過驗證不能碰閘門")
        self.assertEqual([], self.upstream.calls)

    async def test_models_lists_only_the_bot_model(self):
        client = await self.client_for(self.proxy())
        response = await client.get("/v1/models", headers=AUTH)
        self.assertEqual(200, response.status)
        self.assertEqual([MODEL], [m["id"] for m in (await response.json())["data"]])

    async def test_other_model_is_rejected_without_touching_the_gpu(self):
        client = await self.client_for(self.proxy())
        response = await client.post("/v1/chat/completions", json={"model": "other", "messages": []}, headers=AUTH)
        self.assertEqual(400, response.status)
        self.assertEqual("model_not_found", (await response.json())["error"]["code"])
        self.assertEqual([], self.gate.events)
        self.assertEqual([], self.upstream.calls)

    async def test_bad_json_or_missing_messages_is_400(self):
        client = await self.client_for(self.proxy())
        response = await client.post("/v1/chat/completions", data=b"{not json", headers={**AUTH, "Content-Type": "application/json"})
        self.assertEqual(400, response.status)
        response = await client.post("/v1/chat/completions", json={"model": MODEL}, headers=AUTH)
        self.assertEqual(400, response.status)


class ForwardingTests(ProxyTestBase):
    async def test_non_stream_passes_body_through_and_logs_usage(self):
        client = await self.client_for(self.proxy())
        body = {"model": MODEL, "messages": [{"role": "user", "content": "hi"}], "temperature": 0.3,
                "tools": [{"type": "function"}], "max_tokens": 9999}
        with self.assertLogs("services.llm_service", "INFO") as logs:
            response = await client.post("/v1/chat/completions", json=body, headers=AUTH)
        self.assertEqual(200, response.status)
        self.assertEqual(self.upstream.completion, await response.json())
        sent = self.upstream.calls[0][1]
        self.assertEqual(0.3, sent["temperature"])
        self.assertEqual(body["tools"], sent["tools"])
        self.assertEqual(256, sent["max_tokens"], "超過上限要夾到上限")
        self.assertEqual([("enter", "hermes", mock.ANY), ("exit", "hermes")], self.gate.events)
        self.assertTrue(any("llm_usage feature=hermes" in line for line in logs.output), logs.output)

    async def test_stream_reproduces_upstream_lines_and_renews_the_lease(self):
        client = await self.client_for(self.proxy(upstream=FakeUpstream(lines=SSE_LINES)))
        with self.assertLogs("services.llm_service", "INFO") as logs:
            response = await client.post("/v1/chat/completions",
                                         json={"model": MODEL, "messages": [], "stream": True}, headers=AUTH)
            self.assertEqual(200, response.status)
            self.assertTrue(response.headers["Content-Type"].startswith("text/event-stream"))
            received = await response.read()
        self.assertEqual("".join(line + "\n" for line in SSE_LINES), received.decode())
        sent = self.upstream.calls[0][1]
        self.assertTrue(sent["stream_options"]["include_usage"], "串流要請後端在最後一塊附 usage")
        self.assertEqual(len(SSE_LINES) + 1, self.gate.lease.renewals, "載入完成續一次，之後每寫出一行就續租")
        self.assertEqual(("exit", "hermes"), self.gate.events[-1])
        usage_line = next(line for line in logs.output if "llm_usage feature=hermes" in line)
        self.assertIn("prompt=10", usage_line)
        self.assertIn("cached=4", usage_line)

    async def test_gate_busy_returns_503_with_retry_after(self):
        client = await self.client_for(self.proxy(gate=FakeGate(block=True)))
        response = await client.post("/v1/chat/completions", json={"model": MODEL, "messages": []}, headers=AUTH)
        self.assertEqual(503, response.status)
        self.assertEqual("7", response.headers["Retry-After"])
        self.assertEqual([], self.upstream.calls, "沒拿到閘門不能打後端")

    async def test_imagegen_in_progress_returns_503_immediately(self):
        client = await self.client_for(self.proxy())
        with mock.patch.object(llm_proxy, "imagegen_busy", return_value=True):
            response = await client.post("/v1/chat/completions", json={"model": MODEL, "messages": []}, headers=AUTH)
        self.assertEqual(503, response.status)
        self.assertEqual([], self.gate.events)

    async def test_upstream_rejection_is_passed_through_with_its_status(self):
        detail = json.dumps({"error": {"message": "context too long", "code": "ctx"}})
        client = await self.client_for(self.proxy(upstream=FakeUpstream(error=LlmAPIError("HTTP 400", status=400, detail=detail))))
        response = await client.post("/v1/chat/completions", json={"model": MODEL, "messages": []}, headers=AUTH)
        self.assertEqual(400, response.status)
        self.assertEqual("ctx", (await response.json())["error"]["code"])
        self.assertEqual(("exit", "hermes"), self.gate.events[-1], "出錯也要放閘門")

    async def test_unreachable_backend_is_503(self):
        client = await self.client_for(self.proxy(upstream=FakeUpstream(error=LlmTimeoutError("timed out"))))
        response = await client.post("/v1/chat/completions", json={"model": MODEL, "messages": []}, headers=AUTH)
        self.assertEqual(503, response.status)
        self.assertEqual("backend_unavailable", (await response.json())["error"]["code"])
        self.assertEqual(("exit", "hermes"), self.gate.events[-1])

    async def test_non_ascii_bearer_is_401_not_500(self):
        client = await self.client_for(self.proxy())
        response = await client.get("/v1/models", headers={"Authorization": "Bearer caf\u00e9"})
        self.assertEqual(401, response.status)

    async def test_n_predict_and_max_completion_tokens_cannot_bypass_the_cap(self):
        client = await self.client_for(self.proxy())
        body = {"model": MODEL, "messages": [], "max_tokens": 99999, "n_predict": -1, "max_completion_tokens": 99999}
        await client.post("/v1/chat/completions", json=body, headers=AUTH)
        sent = self.upstream.calls[-1][1]
        self.assertEqual(256, sent["max_tokens"])
        self.assertNotIn("n_predict", sent)
        self.assertNotIn("max_completion_tokens", sent)
        await client.post("/v1/chat/completions", json={"model": MODEL, "messages": [], "max_tokens": 100, "n_predict": 50}, headers=AUTH)
        self.assertEqual(50, self.upstream.calls[-1][1]["max_tokens"], "幾個欄位都有效時取最小")

    async def test_upstream_auth_failure_becomes_502(self):
        client = await self.client_for(self.proxy(upstream=FakeUpstream(error=LlmAPIError("HTTP 401", status=401, detail="{}"))))
        response = await client.post("/v1/chat/completions", json={"model": MODEL, "messages": []}, headers=AUTH)
        self.assertEqual(502, response.status)
        self.assertEqual("upstream_auth", (await response.json())["error"]["code"])

    async def test_big_body_is_accepted_on_the_model_endpoint_only(self):
        client = await self.client_for(self.proxy(proxy_max_body_bytes=4 * 1024 * 1024))
        padding = "x" * (2 * 1024 * 1024)
        response = await client.post("/v1/chat/completions", json={"model": "other", "messages": [], "pad": padding}, headers=AUTH)
        self.assertEqual(400, response.status, "2 MiB 的本文要讀得進來（卡在模型白名單，不是 413）")
        response = await client.post("/v1/chat/completions", json={"model": MODEL, "messages": [], "pad": padding * 3}, headers=AUTH)
        self.assertEqual(413, response.status)

    async def test_lease_is_renewed_once_the_model_is_loaded(self):
        client = await self.client_for(self.proxy())
        await client.post("/v1/chat/completions", json={"model": MODEL, "messages": []}, headers=AUTH)
        self.assertEqual(1, self.gate.lease.renewals)

    async def test_failure_right_after_a_data_line_still_ends_the_event_first(self):
        client = await self.client_for(self.proxy(upstream=FakeUpstream(lines=SSE_LINES, fail_after=1)))
        response = await client.post("/v1/chat/completions", json={"model": MODEL, "messages": [], "stream": True}, headers=AUTH)
        text = (await response.read()).decode()
        self.assertIn(SSE_LINES[0] + "\n\ndata: {\"error\"", text, "錯誤塊前要有空行，不能黏進前一個 event")

    async def test_failure_mid_stream_is_reported_inside_the_stream(self):
        client = await self.client_for(self.proxy(upstream=FakeUpstream(lines=SSE_LINES, fail_after=2)))
        response = await client.post("/v1/chat/completions", json={"model": MODEL, "messages": [], "stream": True}, headers=AUTH)
        self.assertEqual(200, response.status)
        text = (await response.read()).decode()
        self.assertTrue(text.startswith(SSE_LINES[0] + "\n"), "出錯前的內容要先到")
        self.assertIn('"code": "stream_failed"', text)
        self.assertEqual(("exit", "hermes"), self.gate.events[-1])


class RawCompletionEnvelopeTests(unittest.IsolatedAsyncioTestCase):
    """真的 LlmHttpClient 的 raw 路徑：Lemonade 回 200＋error 信封時不能當成功交回去。"""

    def _client(self, payload):
        from llm.client.http_client import LlmHttpClient

        from llm.client.lemonade_admin import LemonadeAdmin

        client = LlmHttpClient(base_url="http://backend.test", timeout=1.0, admin=LemonadeAdmin("http://backend.test"))
        resp = SimpleNamespace(is_success=True, status_code=200, json=lambda: payload, text="")
        client._async = SimpleNamespace(post=mock.AsyncMock(return_value=resp))
        client.admin.heal = mock.Mock(return_value=True)
        return client

    async def test_network_error_envelope_heals_once_and_counts_as_unreachable(self):
        from llm.client.http_client import LlmConnectionError

        client = self._client({"error": {"type": "network_error", "message": "Couldn't connect to server"}})
        with self.assertRaises(LlmConnectionError):
            await client.chat_completion_raw({"model": MODEL, "messages": []})
        client.admin.heal.assert_called_once()
        self.assertEqual(MODEL, client.admin.heal.call_args.args[0])

    async def test_other_envelopes_are_upstream_errors_and_normal_bodies_pass(self):
        client = self._client({"error": {"type": "server_error", "message": "boom"}})
        with self.assertRaises(LlmAPIError):
            await client.chat_completion_raw({"model": MODEL, "messages": []})
        client = self._client({"choices": [{"message": {"content": "ok"}}]})
        self.assertEqual("ok", (await client.chat_completion_raw({"model": MODEL, "messages": []}))["choices"][0]["message"]["content"])


class NotifyServerWiringTests(unittest.IsolatedAsyncioTestCase):
    def server(self, api_key):
        return notify_server.NotifyServer(SimpleNamespace(), settings=NotifyServerSettings(shared_secret="n"),
                                          hermes_settings=HermesSettings(api_key=api_key, proxy_max_body_bytes=12345))

    def routes(self, server):
        return {r.resource.canonical for r in server._app.router.routes()}

    async def test_routes_only_exist_with_a_key(self):
        self.assertNotIn("/v1/chat/completions", self.routes(self.server("")))
        with_key = self.server(KEY)
        self.assertIn("/v1/chat/completions", self.routes(with_key))
        self.assertIn("/v1/models", self.routes(with_key))
        self.assertNotEqual(12345, with_key._app._client_max_size, "本文上限只放大 /v1 端點，/notify 維持預設")

    async def test_start_enables_handler_cancellation(self):
        server = self.server(KEY)
        runner = mock.AsyncMock()
        with mock.patch.object(notify_server.web, "AppRunner", return_value=runner) as AppRunner, \
                mock.patch.object(notify_server.web, "TCPSite", return_value=mock.AsyncMock()):
            await server.start(port=0)
        self.assertTrue(AppRunner.call_args.kwargs.get("handler_cancellation"))


class RealGateTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_gate_marks_hermes_as_owner_and_releases(self):
        """用真的閘門跑一次非串流：持有期間 current_owner 是 hermes，結束後沒人持有。"""
        seen = {}

        class Upstream(FakeUpstream):
            async def chat_completion_raw(self, body, *, timeout=None):
                seen["owner"] = gpu_gate.current_owner()
                seen["busy"] = gpu_gate.stream_busy()
                return await super().chat_completion_raw(body, timeout=timeout)

        proxy = llm_proxy.LlmProxy(HermesSettings(api_key=KEY), llm=fake_llm(), client=Upstream())
        app = web.Application()
        proxy.add_routes(app)
        client = TestClient(TestServer(app))
        await client.start_server()
        self.addAsyncCleanup(client.close)
        response = await client.post("/v1/chat/completions", json={"model": MODEL, "messages": []}, headers=AUTH)
        self.assertEqual(200, response.status)
        self.assertEqual({"owner": "hermes", "busy": True}, seen)
        self.assertIsNone(gpu_gate.current_owner())
        self.assertFalse(gpu_gate.stream_busy())


if __name__ == "__main__":
    unittest.main()
