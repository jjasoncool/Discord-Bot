"""轉向量（`llm/client/embedding_client.py` 的 `SafeLLMEmbedding`）遇到錯誤時怎麼重試。

聊天記憶寫入、/askai 的 RAG、情報搜尋算向量都走這裡；聊天記憶寫入還拿著 GPU 閘門，重試多久插話與 /askai 就卡多久。

守的底線：
  - 某段文字讓後端出錯（`LlmAPIError` 4xx）：照舊加空白重試、整批失敗改逐筆（舊版 Ollama 特定文字會當掉）
  - 後端回 5xx（`is_backend_fault`）：和連不上一樣直接往外丟——後端自己壞了（顯示卡裝置掉了）不是文字的問題，逐筆只會每則各吃一次 5xx
  - 連不上或逾時（`is_unreachable`）：直接往外丟、不重試、不改逐筆——後端整個卡住，重試只會每次各等一次逾時
    （2026-10-09 一則訊息被拖到四次逾時，bot 的 AI 全卡一個多小時）
  - async 路徑一樣：逾時不再改走 sync 重試
  - 「拿著 GPU 閘門」模式（`make_safe_llm_embedding(holding_gpu_gate=True)`，聊天記憶寫入與情報搜尋算向量用）：
    單次請求、排隊等 embedding 名額、載入模型各最多 `gated_embed_timeout` 秒，傳輸層不重試；
    等名額等太久當成逾時往外丟。沒指定時照模型呼叫的逾時與重試

執行：
    cd src && python -m unittest test.test_embedding_retry -v
"""

import asyncio
import os
import sys
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from llm.client import embedding_client  # noqa: E402
from llm.client.embedding_client import SafeLLMEmbedding, make_safe_llm_embedding  # noqa: E402
from llm.client.http_client import (  # noqa: E402
    DEFAULT_MAX_RETRIES, LlmAPIError, LlmConnectionError, LlmTimeoutError, is_backend_fault, is_unreachable,
)
from sys_settings.llm_settings import LLMServiceSettings, load_llm_runtime_config  # noqa: E402


class FakeHttp:
    """假的後端：記錄每次請求的輸入，依設定丟錯。"""

    def __init__(self, error=None):
        self.error = error
        self.calls = []

    def embedding(self, *, model, input):
        self.calls.append(input)
        if self.error:
            raise self.error
        return [[0.1] for _ in (input if isinstance(input, list) else [input])]

    async def aembedding(self, *, model, input):
        return self.embedding(model=model, input=input)

    def ensure_lemonade_model(self, **kwargs):
        self.loads = getattr(self, "loads", []) + [kwargs]


def embedder(error=None, **kwargs):
    emb = SafeLLMEmbedding(model_name="m", base_url="http://127.0.0.1:9", **kwargs)
    emb._http_client = FakeHttp(error)
    return emb


class EmbeddingRetryTests(unittest.TestCase):
    def test_unreachable_means_connection_or_timeout_only(self):
        self.assertTrue(is_unreachable(LlmTimeoutError("timed out")))
        self.assertTrue(is_unreachable(LlmConnectionError("refused")))
        self.assertFalse(is_unreachable(LlmAPIError("HTTP 500", status=500)))
        self.assertFalse(is_unreachable(ValueError("x")))

    def test_backend_fault_also_covers_5xx(self):
        self.assertTrue(is_backend_fault(LlmAPIError("HTTP 500", status=500)))
        self.assertTrue(is_backend_fault(LlmTimeoutError("timed out")))
        self.assertFalse(is_backend_fault(LlmAPIError("HTTP 400", status=400)))
        self.assertFalse(is_backend_fault(LlmAPIError("no data", status=None)))
        emb = embedder(LlmAPIError("HTTP 500", status=500, detail="ErrorDeviceLost"))
        with self.assertRaises(LlmAPIError):
            emb.get_text_embedding("深塔")
        self.assertEqual(emb._http_client.calls, ["深塔"], "5xx 不加空白重試")
        emb = embedder(LlmAPIError("HTTP 500", status=500))
        with self.assertRaises(LlmAPIError):
            emb.get_text_embedding_batch(["a", "b"])
        self.assertEqual(emb._http_client.calls, [["a", "b"]], "5xx 不逐筆")

    def test_text_problems_are_retried_with_a_space(self):
        emb = embedder(LlmAPIError("HTTP 400", status=400))
        with self.assertRaises(LlmAPIError):
            emb.get_text_embedding("深塔")
        self.assertEqual(emb._http_client.calls, ["深塔", "深塔 ", " 深塔"])

    def test_a_stuck_backend_is_not_retried(self):
        for error in (LlmTimeoutError("POST /embeddings timed out"), LlmConnectionError("refused")):
            with self.subTest(error=type(error).__name__):
                emb = embedder(error)
                with self.assertRaises(type(error)):
                    emb.get_text_embedding("深塔")
                self.assertEqual(emb._http_client.calls, ["深塔"])

    def test_a_failed_batch_goes_one_by_one_only_for_text_problems(self):
        emb = embedder(LlmAPIError("HTTP 400", status=400))
        with self.assertLogs("llm.client.embedding_client", "WARNING"), self.assertRaises(LlmAPIError):
            emb.get_text_embedding_batch(["a", "b"])
        self.assertEqual(emb._http_client.calls[:2], [["a", "b"], "a"])         # 整批失敗後改逐筆

        emb = embedder(LlmTimeoutError("timed out"))
        with self.assertRaises(LlmTimeoutError):
            emb.get_text_embedding_batch(["a", "b"])
        self.assertEqual(emb._http_client.calls, [["a", "b"]])                  # 逾時就不逐筆

    def test_async_timeout_does_not_fall_back_to_the_sync_retry(self):
        for method in ("aget_text_embedding", "aget_query_embedding"):
            with self.subTest(method=method):
                emb = embedder(LlmTimeoutError("timed out"))
                with self.assertRaises(LlmTimeoutError):
                    asyncio.run(getattr(emb, method)("深塔"))
                self.assertEqual(emb._http_client.calls, ["深塔"])

    def test_gpu_gate_mode_is_short_and_does_not_retry(self):
        settings = LLMServiceSettings()
        runtime = load_llm_runtime_config(settings.llm_runtime_model_path)

        default = make_safe_llm_embedding(settings=settings, runtime_config=runtime)
        gated = make_safe_llm_embedding(settings=settings, runtime_config=runtime, holding_gpu_gate=True)

        self.assertEqual((default._http_client._timeout, default._http_client._max_retries),
                         (float(settings.llm_timeout), DEFAULT_MAX_RETRIES))
        self.assertEqual((default._slot_timeout, default._load_timeout), (None, None))
        limit = float(settings.gated_embed_timeout)
        self.assertEqual((gated._http_client._timeout, gated._http_client._max_retries), (limit, 0))
        self.assertEqual((gated._slot_timeout, gated._load_timeout), (limit, limit))
        self.assertLess(settings.gated_embed_timeout, settings.llm_timeout)

    def test_waiting_too_long_for_the_shared_slot_counts_as_a_timeout(self):
        emb = embedder(slot_timeout=0.1)
        self.assertTrue(embedding_client._EMBED_SEMAPHORE.acquire(timeout=5))   # 別的 embedding 正佔著名額
        try:
            started = time.monotonic()
            with self.assertRaises(LlmTimeoutError) as ctx:
                emb.get_text_embedding_batch(["a"])
            self.assertLess(time.monotonic() - started, 2)
            self.assertTrue(is_unreachable(ctx.exception))                     # 呼叫端會當成連不上、放回再試
            self.assertEqual(emb._http_client.calls, [])
        finally:
            embedding_client._EMBED_SEMAPHORE.release()
        self.assertEqual(emb.get_text_embedding("a"), [0.1])                    # 名額空出來就照常

    def test_model_load_uses_the_shorter_limit(self):
        emb = embedder(backend="lemonade", model_load_options={"ctx_size": 8192}, load_timeout=7)
        emb.get_text_embedding("a")
        asyncio.run(emb.aget_query_embedding("b"))
        self.assertEqual([load["load_timeout"] for load in emb._http_client.loads], [7, 7])


if __name__ == "__main__":
    unittest.main()
