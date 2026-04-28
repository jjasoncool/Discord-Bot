"""SafeLLMEmbedding：自寫 `BaseEmbedding` 子類，走 `LlmHttpClient` 打 `/v1/embeddings`。

不依賴 `llama-index-embeddings-openai`（其父類 `OpenAIEmbedding` 在 init 階段對 model
名做 enum 白名單驗證，自訂 model 名直接拋 `ValueError`）；也不依賴 `openai` SDK。
LlamaIndex 核心介面 `BaseEmbedding` 穩定、不參與 wire IO，繼承它最安全。

保留：
  - 「空格 perturbation」retry：Ollama Windows 版 #7288 GGML_ASSERT bug 觸發時，
    把 text 加一個空格繞過特定 tokenized 序列，語意影響極小。
  - 全域 `_EMBED_SEMAPHORE` 限流：同時最多 N 個 embed 打後端，避免 KV cache fragmentation。

切後端：只要 `LlmHttpClient` 用的 base_url 換掉即可（Ollama / Lemonade / vLLM 都有
`/v1/embeddings`）。
"""
from __future__ import annotations

import logging
import threading
from typing import Any, Callable, TypeVar

from llama_index.core.embeddings import BaseEmbedding
from pydantic import PrivateAttr

from llm.llm_http_client import LlmHttpClient

logger = logging.getLogger("discord_bot")

# 繞過順序：先試尾空格（多數狀況能救），再試前空格
_PERTURBATION_SUFFIXES: tuple[str, ...] = (" ",)
_PERTURBATION_PREFIXES: tuple[str, ...] = (" ",)

# 全域 embedding 並發上限（client 端序列化）。
# 對齊 OLLAMA_NUM_PARALLEL=1：兩邊一致避免 queue 堆到 server 端。AMD Vulkan backend
# 在 KV cache 倍增時容易觸發 allocator fragmentation → runner crash，此處保守化。
# /askai 每次只需 1 次 embed（問題），on_message flush 本來就 sequential，1 足夠。
_EMBED_CONCURRENCY = 1
_EMBED_SEMAPHORE = threading.Semaphore(_EMBED_CONCURRENCY)

# embedding num_ctx 提示：8192 可涵蓋幾乎所有 Discord 訊息情境（單則 4000 字元上限）。
# 走 OpenAI dialect 後，per-request 注入 num_ctx 已不可用；保住 VRAM 省的 ~2.6GB
# 請在 Ollama server 端設 `OLLAMA_DEFAULT_NUM_CTX=8192` env 或 Modelfile 設定。
_EMBED_NUM_CTX = 8192

_T = TypeVar("_T")


def embed_with_perturbation_retry(
    embed_fn: Callable[[str], _T],
    text: str,
    *,
    context_label: str = "embed",
    log: logging.Logger | None = None,
) -> _T:
    """通用 perturbation retry helper（跨 subsystem 共用）。

    先用原 text 呼叫 `embed_fn`；若 fail 就依序加尾空格 / 前空格重試。
    全部失敗時拋出**原始第一個例外**（保留 traceback 給呼叫端診斷）。

    設計理念：Ollama #7288 的 GGML_ASSERT bug 會讓特定 tokenized 序列 crash，
    加空格改變 token 序列即可繞過，語意影響極小。

    使用場景：
      - bot 裡透過 `SafeLLMEmbedding`
      - re-embed script 裡直接打後端 HTTP 的 fallback
    兩邊邏輯一致，避免 drift。
    """
    use_log = log or logger
    try:
        return embed_fn(text)
    except Exception as first_exc:
        for suffix in _PERTURBATION_SUFFIXES:
            variant = text + suffix
            try:
                result = embed_fn(variant)
                use_log.info(
                    "%s: 尾 perturbation 成功 text=%r",
                    context_label, variant[:40],
                )
                return result
            except Exception:
                continue
        for prefix in _PERTURBATION_PREFIXES:
            variant = prefix + text
            try:
                result = embed_fn(variant)
                use_log.info(
                    "%s: 前 perturbation 成功 text=%r",
                    context_label, variant[:40],
                )
                return result
            except Exception:
                continue
        raise first_exc


class SafeLLMEmbedding(BaseEmbedding):
    """LlamaIndex `BaseEmbedding` 子類 + 空格 perturbation retry + 全域並發限流。

    內部直接用 `LlmHttpClient` 打 `/v1/embeddings`，不經 `openai` SDK 也不經
    `llama-index-embeddings-openai`，避免兩邊的 breaking change / 白名單地雷。

    建構子簽名與舊版相同（`model_name` / `base_url` / `request_timeout`），
    既有 caller（context_retriever / chat_persistence / intro_rag_port）零改動。
    """

    # 內部 wire client，不參與 Pydantic 驗證
    _http_client: LlmHttpClient = PrivateAttr()

    def __init__(
        self,
        model_name: str,
        base_url: str,
        request_timeout: float | None = None,
        **kwargs: Any,
    ) -> None:
        timeout = float(request_timeout) if request_timeout is not None else 60.0
        super().__init__(model_name=model_name, **kwargs)
        # __init__ 內 super 會凍結 fields；用 PrivateAttr 規避 Pydantic 限制
        self._http_client = LlmHttpClient(
            base_url=base_url,
            timeout=timeout,
        )

    # ---------- sync embed（LlamaIndex 內部某些路徑會走 sync）----------

    def _embed_one(self, text: str) -> list[float]:
        return self._http_client.embedding(model=self.model_name, input=text)[0]

    def _get_text_embedding(self, text: str) -> list[float]:
        with _EMBED_SEMAPHORE:
            return embed_with_perturbation_retry(
                self._embed_one, text,
                context_label="SafeLLMEmbedding.text",
            )

    def _get_query_embedding(self, query: str) -> list[float]:
        with _EMBED_SEMAPHORE:
            return embed_with_perturbation_retry(
                self._embed_one, query,
                context_label="SafeLLMEmbedding.query",
            )

    def _get_text_embeddings(self, texts: list[str]) -> list[list[float]]:
        # batch 層持鎖一次；batch 失敗走逐筆 fallback 時，先釋放再讓內層 acquire，
        # 避免同一執行緒重入 semaphore（threading.Semaphore 非 reentrant）。
        with _EMBED_SEMAPHORE:
            try:
                return self._http_client.embedding(model=self.model_name, input=texts)
            except Exception as exc:
                logger.warning(
                    "SafeLLMEmbedding: batch 失敗（size=%d），改逐筆 + perturbation: %s",
                    len(texts), exc,
                )
        return [self._get_text_embedding(t) for t in texts]

    # ---------- async embed ----------

    async def _aembed_one(self, text: str) -> list[float]:
        result = await self._http_client.aembedding(model=self.model_name, input=text)
        return result[0]

    async def _aget_text_embedding(self, text: str) -> list[float]:
        try:
            return await self._aembed_one(text)
        except Exception:
            # async 失敗時走 sync helper（取得 semaphore 限流 + perturbation retry）。
            # 切 sync 比重複實作 async perturbation 還簡單，且 embedding crash 場景
            # 本來就無法 async 快速恢復，sync retry 影響不大。
            return self._get_text_embedding(text)

    async def _aget_query_embedding(self, query: str) -> list[float]:
        try:
            return await self._aembed_one(query)
        except Exception:
            return self._get_query_embedding(query)
