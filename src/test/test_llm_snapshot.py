"""chat_raw 失敗路徑 anomaly snapshot 行為（不打真正的 LLM backend）。

驗證重點：
  1. 三條失敗路徑（no_choices / empty_content / connection / timeout）都會觸發 snapshot
  2. backend dispatch：依 runtime.backend 從 _BACKEND_PROBES 挑要打哪些 endpoints
  3. 未註冊的 backend 安全跳過（不打 admin_get、不影響原本 raise）
  4. snapshot 自身爆炸時要走 warning + 仍 raise 原本錯（次要診斷不能蓋主錯）

執行：
    cd src && python -m unittest test.test_llm_snapshot -v
"""

import asyncio
import logging
import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from llm.llm_http_client import LlmConnectionError, LlmTimeoutError
from services import llm_service as llm_service_module


def _make_service(backend: str = "lemonade"):
    """建出一個 LLMService 但跳過 settings / runtime config 載入，固定回指定 backend。"""
    svc = llm_service_module.LLMService.__new__(llm_service_module.LLMService)
    svc.settings = MagicMock(default_temperature=0.7, default_top_p=0.95, llm_timeout=300)
    svc.timeout = 300
    svc.model_default = "test-model"
    svc.context_safety_rules = ""
    svc._client = MagicMock()
    svc._client.chat_completion = AsyncMock()
    svc._client.admin_get = AsyncMock(return_value={"status": 200, "body": {"x": 1}})
    svc._ensure_model_loaded = AsyncMock()
    svc._build_chat_extra_body = MagicMock(return_value={})
    runtime = MagicMock()
    runtime.backend = backend
    svc._load_runtime_config_cached = MagicMock(return_value=runtime)
    return svc


class SnapshotOnFailureTests(unittest.TestCase):

    def _capture_anomaly(self):
        """攔住 anomaly_logger 把 record 收進 list（同時抓 ERROR 跟 WARNING）。"""
        records = []
        handler = logging.Handler()
        handler.emit = lambda record: records.append(record)  # type: ignore[assignment]
        llm_service_module.anomaly_logger.addHandler(handler)
        llm_service_module.anomaly_logger.setLevel(logging.DEBUG)
        return records, handler

    def _release(self, handler):
        llm_service_module.anomaly_logger.removeHandler(handler)

    # ---------- 失敗類型 × 是否觸發 snapshot ----------

    def test_snapshot_on_no_choices(self):
        svc = _make_service("lemonade")
        svc._client.chat_completion.return_value = {"choices": [], "usage": None}
        records, handler = self._capture_anomaly()
        try:
            with self.assertRaises(llm_service_module.LLMAPIError):
                asyncio.run(svc.chat_raw(model="m", messages=[{"role": "user", "content": "hi"}], trace_id="t1"))
        finally:
            self._release(handler)
        msgs = [r.getMessage() for r in records]
        self.assertTrue(any("no_choices trace=t1" in m for m in msgs), msgs)
        self.assertTrue(
            any("snapshot trace=t1 kind=no_choices backend=lemonade" in m for m in msgs),
            msgs,
        )

    def test_snapshot_on_empty_content(self):
        svc = _make_service("lemonade")
        svc._client.chat_completion.return_value = {
            "choices": [{"message": {"content": ""}, "finish_reason": "stop"}],
            "usage": None,
        }
        records, handler = self._capture_anomaly()
        try:
            with self.assertRaises(llm_service_module.LLMAPIError):
                asyncio.run(svc.chat_raw(model="m", messages=[{"role": "user", "content": "hi"}], trace_id="t2"))
        finally:
            self._release(handler)
        msgs = [r.getMessage() for r in records]
        self.assertTrue(any("empty_content trace=t2" in m for m in msgs), msgs)
        self.assertTrue(
            any("snapshot trace=t2 kind=empty_content backend=lemonade" in m for m in msgs),
            msgs,
        )

    def test_snapshot_on_connection_error(self):
        svc = _make_service("lemonade")
        svc._client.chat_completion.side_effect = LlmConnectionError("boom")
        records, handler = self._capture_anomaly()
        try:
            with self.assertRaises(LlmConnectionError):
                asyncio.run(svc.chat_raw(model="m", messages=[{"role": "user", "content": "hi"}], trace_id="t3"))
        finally:
            self._release(handler)
        msgs = [r.getMessage() for r in records]
        self.assertTrue(any("connection trace=t3" in m for m in msgs), msgs)
        self.assertTrue(
            any("snapshot trace=t3 kind=connection backend=lemonade" in m for m in msgs),
            msgs,
        )

    def test_snapshot_on_timeout_error(self):
        svc = _make_service("lemonade")
        svc._client.chat_completion.side_effect = LlmTimeoutError("slow")
        records, handler = self._capture_anomaly()
        try:
            with self.assertRaises(LlmTimeoutError):
                asyncio.run(svc.chat_raw(model="m", messages=[{"role": "user", "content": "hi"}], trace_id="t4"))
        finally:
            self._release(handler)
        msgs = [r.getMessage() for r in records]
        self.assertTrue(any("timeout trace=t4" in m for m in msgs), msgs)
        self.assertTrue(
            any("snapshot trace=t4 kind=timeout backend=lemonade" in m for m in msgs),
            msgs,
        )

    # ---------- backend dispatch ----------

    def test_snapshot_dispatches_lemonade_probes(self):
        svc = _make_service("lemonade")
        svc._client.chat_completion.return_value = {"choices": [], "usage": None}
        with self.assertRaises(llm_service_module.LLMAPIError):
            asyncio.run(svc.chat_raw(model="m", messages=[{"role": "user", "content": "hi"}], trace_id="ld1"))
        svc._client.admin_get.assert_any_await("/api/v1/health")
        svc._client.admin_get.assert_any_await("/api/v1/system-info")

    def test_snapshot_dispatches_ollama_probes(self):
        svc = _make_service("ollama")
        svc._client.chat_completion.return_value = {"choices": [], "usage": None}
        records, handler = self._capture_anomaly()
        try:
            with self.assertRaises(llm_service_module.LLMAPIError):
                asyncio.run(svc.chat_raw(model="m", messages=[{"role": "user", "content": "hi"}], trace_id="ol1"))
        finally:
            self._release(handler)
        # Ollama 該打的兩個端點
        svc._client.admin_get.assert_any_await("/api/ps")
        svc._client.admin_get.assert_any_await("/api/tags")
        # Lemonade 端點不該被打
        for call in svc._client.admin_get.await_args_list:
            self.assertNotIn(call.args[0], ("/api/v1/health", "/api/v1/system-info"))
        # log 標 backend=ollama
        msgs = [r.getMessage() for r in records]
        self.assertTrue(
            any("snapshot trace=ol1 kind=no_choices backend=ollama" in m for m in msgs),
            msgs,
        )

    def test_snapshot_dispatches_vllm_probes(self):
        svc = _make_service("vllm")
        svc._client.chat_completion.return_value = {"choices": [], "usage": None}
        with self.assertRaises(llm_service_module.LLMAPIError):
            asyncio.run(svc.chat_raw(model="m", messages=[{"role": "user", "content": "hi"}], trace_id="v1"))
        svc._client.admin_get.assert_any_await("/health")
        svc._client.admin_get.assert_any_await("/v1/models")

    def test_snapshot_skipped_for_unknown_backend(self):
        svc = _make_service("weird-backend-not-in-registry")
        svc._client.chat_completion.return_value = {"choices": [], "usage": None}
        records, handler = self._capture_anomaly()
        try:
            with self.assertRaises(llm_service_module.LLMAPIError):
                asyncio.run(svc.chat_raw(model="m", messages=[{"role": "user", "content": "hi"}], trace_id="u1"))
        finally:
            self._release(handler)
        # no_choices 主錯仍要寫；snapshot 不打、admin_get 一次也不能呼叫
        msgs = [r.getMessage() for r in records]
        self.assertTrue(any("no_choices trace=u1" in m for m in msgs), msgs)
        self.assertFalse(any("snapshot trace=u1" in m for m in msgs), msgs)
        svc._client.admin_get.assert_not_awaited()

    # ---------- 故障路徑診斷不能蓋主錯 ----------

    def test_snapshot_failure_does_not_mask_original_raise(self):
        """admin_get 自己炸時，仍要走 warning + raise 原本的錯（不能蓋掉主錯）。"""
        svc = _make_service("lemonade")
        svc._client.chat_completion.return_value = {"choices": [], "usage": None}
        svc._client.admin_get.side_effect = RuntimeError("admin probe broken")
        records, handler = self._capture_anomaly()
        try:
            with self.assertRaises(llm_service_module.LLMAPIError):
                asyncio.run(svc.chat_raw(model="m", messages=[{"role": "user", "content": "hi"}], trace_id="t6"))
        finally:
            self._release(handler)
        msgs = [r.getMessage() for r in records]
        self.assertTrue(any("snapshot failed trace=t6" in m for m in msgs), msgs)


if __name__ == "__main__":
    unittest.main()
