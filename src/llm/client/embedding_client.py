"""SafeLLMEmbedding：自寫 `BaseEmbedding` 子類，走 `LlmHttpClient` 打 `/v1/embeddings`。

不依賴 `llama-index-embeddings-openai`（其父類 `OpenAIEmbedding` 在 init 階段對 model
名做 enum 白名單驗證，自訂 model 名直接拋 `ValueError`）；也不依賴 `openai` SDK。
LlamaIndex 核心介面 `BaseEmbedding` 穩定、不參與 wire IO，繼承它最安全。

保留：
  - 「空格 perturbation」retry：Ollama Windows 版 #7288 GGML_ASSERT bug 觸發時，
    把 text 加一個空格繞過特定 tokenized 序列，語意影響極小。
    **連不上或逾時不重試**（batch 改逐筆也不做）：那是後端整個卡住，換寫法重送只會再等一輪逾時。
    2026-10-09 Lemonade 卡住時，一則聊天訊息被「batch → 逐筆 → 尾空格 → 前空格」各等一次逾時，
    呼叫端（聊天記憶寫入）又拿著 GPU 閘門，插話與 /askai 跟著卡了一個多小時。
  - 全域 `_EMBED_SEMAPHORE` 限流：同時最多 N 個 embed 打後端，避免 KV cache fragmentation。

切後端：只要 `LlmHttpClient` 用的 base_url 換掉即可（Ollama / Lemonade / vLLM 都有
`/v1/embeddings`）。
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import threading
from typing import Any, Callable, TypeVar

from llama_index.core.embeddings import BaseEmbedding
from pydantic import PrivateAttr

from llm.client.http_client import LlmHttpClient, LlmTimeoutError, is_backend_fault
from llm.client.backend_admin import admin_for

from sys_settings.llm_settings import LLMRuntimeConfig, LLMServiceSettings

logger = logging.getLogger(__name__)

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

    後端本身的問題（`is_backend_fault`：連不上、逾時、回 5xx）直接往外丟、不重試：那不是文字的問題。
    """
    use_log = log or logger
    try:
        return embed_fn(text)
    except Exception as first_exc:
        if is_backend_fault(first_exc):
            raise
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

    建構子保留舊簽名（`model_name` / `base_url` / `request_timeout`）；
    新增 optional `backend` / `model_load_options` 兩個欄位讓 caller 帶入後端
    與 per-model 載入參數，命中 Lemonade 時會在第一次 embed 之前先 push
    `/api/v1/load` 確保 ctx_size 對齊。其他後端忽略這兩個欄位。

    `max_retries`（傳輸層重試，預設照 `LlmHttpClient`）、`slot_timeout`（排隊等全域 embedding 名額最多幾秒，
    None＝一直等）、`load_timeout`（載入模型最多幾秒，None＝admin 的預設）：
    拿著 GPU 閘門的呼叫端用 `make_safe_llm_embedding(holding_gpu_gate=True)` 一次設好。
    """

    # 內部 wire client + per-instance 後端 / load options，不參與 Pydantic 驗證
    _http_client: LlmHttpClient = PrivateAttr()
    _backend: str = PrivateAttr(default="ollama")
    _load_options: dict[str, Any] | None = PrivateAttr(default=None)
    _slot_timeout: float | None = PrivateAttr(default=None)
    _load_timeout: float | None = PrivateAttr(default=None)

    def __init__(
        self,
        model_name: str,
        base_url: str,
        request_timeout: float | None = None,
        *,
        backend: str = "ollama",
        model_load_options: dict[str, Any] | None = None,
        max_retries: int | None = None,
        slot_timeout: float | None = None,
        load_timeout: float | None = None,
        **kwargs: Any,
    ) -> None:
        timeout = float(request_timeout) if request_timeout is not None else 60.0
        super().__init__(model_name=model_name, **kwargs)
        # __init__ 內 super 會凍結 fields；用 PrivateAttr 規避 Pydantic 限制
        retry_kwargs = {"max_retries": max_retries} if max_retries is not None else {}
        # 後端有管理 API（Lemonade）才掛 admin；自癒重載也照 load_timeout 等，拿著閘門時才不會卡太久
        admin_kwargs = {"heal_load_timeout": load_timeout} if load_timeout is not None else {}
        self._http_client = LlmHttpClient(
            base_url=base_url,
            timeout=timeout,
            admin=admin_for(backend, base_url, **admin_kwargs),
            **retry_kwargs,
        )
        self._backend = backend
        self._load_options = model_load_options or None
        self._slot_timeout = slot_timeout
        self._load_timeout = load_timeout

    @contextlib.contextmanager
    def _embed_slot(self):
        """拿全域 embedding 名額（`_EMBED_SEMAPHORE`）。有 `slot_timeout` 時等太久就當逾時往外丟：
        拿著 GPU 閘門的呼叫端不能無限期排在別的 embedding（例如後端卡住時正在等逾時的 /askai 檢索）後面。"""
        if not _EMBED_SEMAPHORE.acquire(timeout=self._slot_timeout):
            raise LlmTimeoutError(f"排隊等 embedding 名額超過 {self._slot_timeout:g} 秒（別的 embedding 還沒結束）")
        try:
            yield
        finally:
            _EMBED_SEMAPHORE.release()

    def _load_kwargs(self) -> dict[str, Any]:
        return {"load_timeout": self._load_timeout} if self._load_timeout is not None else {}

    def _ensure_loaded(self) -> None:
        """打 embedding 之前先確認後端已用對的載入選項（ctx_size、固定在哪張卡）載入 model。

        沒有管理 API 的後端（admin 是 None）不做；admin 對沒變的 (model, options) 組合會快取命中，第二次以後是毫秒級。
        """
        admin = self._http_client.admin
        if admin is None or not self._load_options:
            return
        admin.ensure_loaded(model=self.model_name, options=self._load_options, **self._load_kwargs())

    # ---------- sync embed（LlamaIndex 內部某些路徑會走 sync）----------

    def _embed_one(self, text: str) -> list[float]:
        self._ensure_loaded()
        return self._http_client.embedding(model=self.model_name, input=text)[0]

    def _get_text_embedding(self, text: str) -> list[float]:
        with self._embed_slot():
            return embed_with_perturbation_retry(
                self._embed_one, text,
                context_label="SafeLLMEmbedding.text",
            )

    def _get_query_embedding(self, query: str) -> list[float]:
        with self._embed_slot():
            return embed_with_perturbation_retry(
                self._embed_one, query,
                context_label="SafeLLMEmbedding.query",
            )

    def _get_text_embeddings(self, texts: list[str]) -> list[list[float]]:
        # batch 層持鎖一次；batch 失敗走逐筆 fallback 時，先釋放再讓內層 acquire，
        # 避免同一執行緒重入 semaphore（threading.Semaphore 非 reentrant）。
        with self._embed_slot():
            try:
                self._ensure_loaded()
                return self._http_client.embedding(model=self.model_name, input=texts)
            except Exception as exc:
                if is_backend_fault(exc):
                    raise       # 後端整個卡住或壞了：逐筆再試只會每筆各等一次逾時、各吃一次 5xx
                logger.warning(
                    "SafeLLMEmbedding: batch 失敗（size=%d），改逐筆 + perturbation: %s",
                    len(texts), exc,
                )
        return [self._get_text_embedding(t) for t in texts]

    # ---------- async embed ----------

    async def _aembed_one(self, text: str) -> list[float]:
        # 管理 API 是 sync HTTP，async path 包 to_thread 避免阻塞 loop
        if self._http_client.admin is not None and self._load_options:
            await asyncio.to_thread(self._ensure_loaded)
        result = await self._http_client.aembedding(model=self.model_name, input=text)
        return result[0]

    async def _aget_text_embedding(self, text: str) -> list[float]:
        try:
            return await self._aembed_one(text)
        except Exception as exc:
            if is_backend_fault(exc):
                raise
            # async 失敗時走 sync helper（取得 semaphore 限流 + perturbation retry）。
            # 切 sync 比重複實作 async perturbation 還簡單，且 embedding crash 場景
            # 本來就無法 async 快速恢復，sync retry 影響不大。
            return self._get_text_embedding(text)

    async def _aget_query_embedding(self, query: str) -> list[float]:
        try:
            return await self._aembed_one(query)
        except Exception as exc:
            if is_backend_fault(exc):
                raise
            return self._get_query_embedding(query)


def make_safe_llm_embedding(
    *,
    settings: LLMServiceSettings,
    runtime_config: LLMRuntimeConfig,
    holding_gpu_gate: bool = False,
) -> SafeLLMEmbedding:
    """Factory：從 settings + runtime_config 組裝 `SafeLLMEmbedding`。

    自動帶入後端類型 + 該 embedding model 在 `model_load_options` 裡的設定，
    讓 caller 不用重複組裝這些後端不可知的 wiring（context_retriever /
    store_chat / member_profile_store 三處共用）。

    `holding_gpu_gate=True`：呼叫端算 embedding 時拿著 GPU 閘門（聊天記憶寫入、情報搜尋算向量），插話與 /askai
    都排在後面。單次請求、排隊等 embedding 名額、載入模型各最多 `settings.gated_embed_timeout` 秒，傳輸層也不重試
    ——後端卡住時早點放掉閘門，由呼叫端下一輪再試。預設（False）照模型呼叫的逾時與重試。
    """
    backend = runtime_config.backend
    profile = runtime_config.backends.get(backend)
    options = (
        profile.model_load_options.get(runtime_config.embed_model)
        if profile is not None
        else None
    )
    gated = settings.gated_embed_timeout if holding_gpu_gate else None
    return SafeLLMEmbedding(
        model_name=runtime_config.embed_model,
        base_url=settings.llm_base_url,
        request_timeout=gated if gated is not None else settings.llm_timeout,
        backend=backend,
        model_load_options=options,
        max_retries=0 if holding_gpu_gate else None,
        slot_timeout=gated,
        load_timeout=gated,
    )
