"""SafeOllamaEmbedding：包住 LlamaIndex 的 OllamaEmbedding，加上「空格 perturbation」retry。

動機：Ollama Windows 版有已知 bug（#7288）— 某些 text 的 tokenize 結果會讓內部 runner
subprocess 觸發 `GGML_ASSERT(i01 >= 0 && i01 < ne01) failed` C-level assertion 而崩掉，
回 HTTP 400/500 帶 `wsarecv forcibly closed`。

Workaround：若 embedding 呼叫失敗，把 text 加一個空格（尾或前）再 retry。空格會改變 tokenizer
產出的 token 序列，繞過會觸發 bug 的特定 pattern；語意影響極小（embedding 向量近乎相同）。

使用：把專案中所有 `OllamaEmbedding(...)` 換成 `SafeOllamaEmbedding(...)` 即可，
介面完全相容。
"""
from __future__ import annotations

import logging
from typing import Any, Callable, TypeVar

from llama_index.embeddings.ollama import OllamaEmbedding

logger = logging.getLogger("discord_bot")

# 繞過順序：先試尾空格（多數狀況能救），再試前空格
_PERTURBATION_SUFFIXES: tuple[str, ...] = (" ",)
_PERTURBATION_PREFIXES: tuple[str, ...] = (" ",)

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
      - bot 裡透過 LlamaIndex 的 `SafeOllamaEmbedding`
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


class SafeOllamaEmbedding(OllamaEmbedding):
    """OllamaEmbedding + 空格 perturbation retry。內部轉用共用 `embed_with_perturbation_retry` helper。"""

    def _get_text_embedding(self, text: str) -> list[float]:
        return embed_with_perturbation_retry(
            super()._get_text_embedding, text,
            context_label="SafeOllamaEmbedding.text",
        )

    def _get_query_embedding(self, query: str) -> list[float]:
        return embed_with_perturbation_retry(
            super()._get_query_embedding, query,
            context_label="SafeOllamaEmbedding.query",
        )

    def _get_text_embeddings(self, texts: list[str]) -> list[list[float]]:
        try:
            return super()._get_text_embeddings(texts)
        except Exception as exc:
            logger.warning(
                "SafeOllamaEmbedding: batch 失敗（size=%d），改逐筆 + perturbation: %s",
                len(texts), exc,
            )
            return [self._get_text_embedding(t) for t in texts]

    async def _aget_text_embedding(self, text: str) -> list[float]:
        try:
            return await super()._aget_text_embedding(text)
        except Exception:
            # async fallback 直接走 sync helper（Ollama 崩潰場景本來就無法 async 快速恢復，
            # 切 sync retry 避免重複實作兩套 perturbation 邏輯）
            return embed_with_perturbation_retry(
                super()._get_text_embedding, text,
                context_label="SafeOllamaEmbedding.async_text",
            )

    async def _aget_query_embedding(self, query: str) -> list[float]:
        try:
            return await super()._aget_query_embedding(query)
        except Exception:
            return embed_with_perturbation_retry(
                super()._get_query_embedding, query,
                context_label="SafeOllamaEmbedding.async_query",
            )

    def _get_agg_embedding_from_queries(
        self, queries: list[str], agg_fn: Any = None,
    ) -> list[float]:
        # LlamaIndex 內部方法；維持父類預設行為，底層每個 query 會走 _get_query_embedding 吃到 retry
        return super()._get_agg_embedding_from_queries(queries, agg_fn)
