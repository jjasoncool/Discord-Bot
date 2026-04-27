"""SafeLLMEmbedding：包住 LlamaIndex 的 OpenAIEmbedding 打 Ollama `/v1/embeddings`，
加上「空格 perturbation」retry 與全域並發 semaphore。

動機（perturbation）：Ollama Windows 版有已知 bug（#7288）— 某些 text 的 tokenize 結果會
讓內部 runner subprocess 觸發 `GGML_ASSERT(i01 >= 0 && i01 < ne01) failed` C-level
assertion 而崩掉，回 HTTP 400/500 帶 `wsarecv forcibly closed`。OpenAI 相容端點走的還是
同一個 Ollama embedding 內部 path，因此這個 bug 與 retry 仍然適用。

Workaround：失敗時把 text 加一個空格（尾或前）再 retry，改變 tokenizer 產生的序列繞過 bug。

底層已切換為 OpenAI dialect（保留 `SafeLLMEmbedding` 檔名與類別名以避免動 caller）；
未來換 LM Studio / Lemonade 只需改 base_url，不用動這個檔。
"""
from __future__ import annotations

import logging
import threading
from typing import Any, Callable, TypeVar

from llama_index.embeddings.openai import OpenAIEmbedding

logger = logging.getLogger("discord_bot")

# 繞過順序：先試尾空格（多數狀況能救），再試前空格
_PERTURBATION_SUFFIXES: tuple[str, ...] = (" ",)
_PERTURBATION_PREFIXES: tuple[str, ...] = (" ",)

# 全域 embedding 並發上限（client 端序列化）。
# 對齊 OLLAMA_NUM_PARALLEL=1：兩邊一致避免 queue 堆到 server 端。AMD Vulkan backend
# 在 KV cache 倍增時容易觸發 allocator fragmentation → runner crash，此處保守化。
# Plan C 後 /askai 只需 1 次 embed（問題），on_message flush 本來就 sequential，1 足夠。
# 若 server 端  OLLAMA_NUM_PARALLEL 升級，請同步調整此值。
_EMBED_CONCURRENCY = 1
_EMBED_SEMAPHORE = threading.Semaphore(_EMBED_CONCURRENCY)

# embedding num_ctx：Ollama 預設依 VRAM 算出（雙卡 31.7GB → 32K），但 embedding 不需要
# 那麼長的 context，預分配 KV cache ≈ 3.5GB（qwen3-embedding:0.6b 28 layers）純浪費。
# 8192 可涵蓋幾乎所有 Discord 訊息情境（單則 4000 字元上限），KV cache 降到 ~880MB，
# 省 ~2.6GB VRAM。
#
# 切到 OpenAI dialect 後，per-request 注入 num_ctx 的路徑（`ollama_additional_kwargs`）
# 失效——OpenAI 標準沒有這欄位。要保住 VRAM 省的這 2.6GB，請在 Ollama server 端設
# `OLLAMA_DEFAULT_NUM_CTX=8192` env 或在 Modelfile 裡 `PARAMETER num_ctx 8192`。
# 此常數保留作 server 端配置的參考值。
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
      - bot 裡透過 LlamaIndex 的 `SafeLLMEmbedding`
      - re-embed script 裡直接打 Ollama HTTP 的 fallback
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


class SafeLLMEmbedding(OpenAIEmbedding):
    """OpenAIEmbedding（指 Ollama `/v1/embeddings`）+ 空格 perturbation retry +
    全域並發上限 semaphore。

    所有 embed 呼叫都經過 `_EMBED_SEMAPHORE` 限流，同時最多 N 個 request 打後端。
    batch 方法（`_get_text_embeddings`）只在最外層 acquire 一次，避免巢狀持鎖。

    Constructor 維持原 caller 簽名（`model_name` / `base_url` / `request_timeout`），
    內部翻譯成 OpenAIEmbedding 的 `model` / `api_base` / `timeout`。
    """

    def __init__(
        self,
        model_name: str,
        base_url: str,
        request_timeout: float | None = None,
        **kwargs: Any,
    ) -> None:
        api_base = f"{base_url.rstrip('/')}/v1"
        timeout = request_timeout if request_timeout is not None else 60.0
        super().__init__(
            model=model_name,
            api_base=api_base,
            api_key="ollama",  # Ollama 不驗 key，但 SDK 必填
            timeout=timeout,
            **kwargs,
        )

    def _get_text_embedding(self, text: str) -> list[float]:
        with _EMBED_SEMAPHORE:
            return embed_with_perturbation_retry(
                super()._get_text_embedding, text,
                context_label="SafeLLMEmbedding.text",
            )

    def _get_query_embedding(self, query: str) -> list[float]:
        with _EMBED_SEMAPHORE:
            return embed_with_perturbation_retry(
                super()._get_query_embedding, query,
                context_label="SafeLLMEmbedding.query",
            )

    def _get_text_embeddings(self, texts: list[str]) -> list[list[float]]:
        # batch 層持鎖一次；batch 失敗走逐筆 fallback 時，我們先釋放再讓內層 acquire，
        # 避免同一執行緒重入 semaphore（threading.Semaphore 非 reentrant）。
        with _EMBED_SEMAPHORE:
            try:
                return super()._get_text_embeddings(texts)
            except Exception as exc:
                logger.warning(
                    "SafeLLMEmbedding: batch 失敗（size=%d），改逐筆 + perturbation: %s",
                    len(texts), exc,
                )
        return [self._get_text_embedding(t) for t in texts]

    async def _aget_text_embedding(self, text: str) -> list[float]:
        try:
            return await super()._aget_text_embedding(text)
        except Exception:
            # async fallback 走 sync helper（Ollama 崩潰場景本來就無法 async 快速恢復，
            # 切 sync retry 避免重複實作兩套 perturbation 邏輯）。
            # 這裡直接呼叫 self._get_text_embedding 取得 semaphore 限流。
            return self._get_text_embedding(text)

    async def _aget_query_embedding(self, query: str) -> list[float]:
        try:
            return await super()._aget_query_embedding(query)
        except Exception:
            return self._get_query_embedding(query)

    def _get_agg_embedding_from_queries(
        self, queries: list[str], agg_fn: Any = None,
    ) -> list[float]:
        # LlamaIndex 內部方法；維持父類預設行為，底層每個 query 會走 _get_query_embedding 吃到 retry
        return super()._get_agg_embedding_from_queries(queries, agg_fn)
