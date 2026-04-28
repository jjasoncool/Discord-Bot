"""OpenAI dialect 自寫 wire 薄殼。

不依賴 `openai` SDK 與 `llama-index-embeddings-openai` 等周邊套件，
只走標準 `/v1/chat/completions`、`/v1/embeddings`、`/v1/models` HTTP 端點。

設計動機：
  - wire 規格從 2023 年定下來後沒有破壞性更動，是 OpenAI-compatible 後端
    （Ollama / Lemonade / vLLM / LM Studio / llama.cpp server / LocalAI 等）
    的事實標準；綁協定不綁 SDK 可避免：
    1. 商業 SDK breaking change（過去 v0→v1 大改、Pydantic v1→v2 等都炸過）
    2. 周邊套件硬塞驗證（如 LlamaIndex `OpenAIEmbedding` 的 enum 白名單地雷）
  - sync + async 介面分別給 LlamaIndex BaseEmbedding 的 `_get_*` / `_aget_*`
    與本專案 async chat 路徑使用。

切後端：只需改 base_url；wire payload 三個後端都解析得了。
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

logger = logging.getLogger("discord_bot")

# 連線層 / 暫時性錯誤的指數退避：對齊原 openai SDK max_retries=2
DEFAULT_MAX_RETRIES = 2
DEFAULT_BACKOFF_INITIAL_S = 1.0
DEFAULT_BACKOFF_FACTOR = 2.0


class LlmAPIError(Exception):
    """HTTP 非 2xx 或回應格式異常。

    `status is not None` 表示 HTTP 層錯誤；
    `status is None` 表示 2xx 但回應格式不符預期。
    """

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        detail: str = "",
    ) -> None:
        super().__init__(message)
        self.status = status
        self.detail = detail


class LlmConnectionError(Exception):
    """無法連線到 LLM 後端（DNS / TCP / TLS 等已重試用盡）。"""


class LlmTimeoutError(Exception):
    """LLM 後端逾時（已重試用盡）。"""


def _should_retry_status(status: int | None) -> bool:
    """是否該重試：429（rate limit）與 5xx 重試；4xx 不重試。"""
    if status is None:
        return False
    return status == 429 or 500 <= status < 600


def _backoff_delay(attempt: int) -> float:
    return DEFAULT_BACKOFF_INITIAL_S * (DEFAULT_BACKOFF_FACTOR ** attempt)


class LlmHttpClient:
    """OpenAI dialect HTTP 薄殼：chat / embedding / models 三個端點。"""

    def __init__(
        self,
        *,
        base_url: str,
        timeout: float,
        max_retries: int = DEFAULT_MAX_RETRIES,
        api_key: str = "no-auth",
    ) -> None:
        # base_url 在實例化時固定為 "<host>/v1"，後續所有 path 走相對拼接
        self._base = base_url.rstrip("/") + "/v1"
        self._timeout = timeout
        self._max_retries = max_retries
        self._headers = {
            # 本機後端通常不驗 key，但部分客戶端 / proxy 會檢查 header 存在
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        # sync / async 各自一份 connection pool（httpx 自動處理 keep-alive）
        self._sync = httpx.Client(timeout=timeout, headers=self._headers)
        self._async = httpx.AsyncClient(timeout=timeout, headers=self._headers)

    def close(self) -> None:
        self._sync.close()

    async def aclose(self) -> None:
        await self._async.aclose()

    # ---------- chat ----------

    async def chat_completion(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        temperature: float | None = None,
        top_p: float | None = None,
        timeout: float | None = None,
        extra_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """POST /v1/chat/completions（async only）。

        `extra_body` 與 OpenAI SDK 同義：top-level 合併到 request body，
        後端不解析的欄位由後端決定忽略 / 報錯（建議搭配 backend profile 用）。
        """
        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
        }
        if temperature is not None:
            body["temperature"] = temperature
        if top_p is not None:
            body["top_p"] = top_p
        if extra_body:
            body.update(extra_body)
        return await self._apost_json("/chat/completions", body, timeout=timeout)

    # ---------- embedding ----------

    def embedding(self, *, model: str, input: str | list[str]) -> list[list[float]]:
        """POST /v1/embeddings（sync）。

        即使 `input` 是單一字串也回傳 list[list[float]]，caller 自取 `[0]`，
        簡化 batch / single 共用 code path。
        """
        data = self._post_json("/embeddings", {"model": model, "input": input})
        return [item["embedding"] for item in data["data"]]

    async def aembedding(
        self,
        *,
        model: str,
        input: str | list[str],
    ) -> list[list[float]]:
        data = await self._apost_json("/embeddings", {"model": model, "input": input})
        return [item["embedding"] for item in data["data"]]

    # ---------- models（啟動自我測試 / 觀測用）----------

    def list_models(self) -> list[str]:
        """GET /v1/models，回傳 model id 字串清單（去除空字串）。"""
        data = self._get_json("/models")
        return [m.get("id", "") for m in data.get("data", []) if m.get("id")]

    # ---------- low-level：retry + error mapping ----------

    def _get_json(self, path: str) -> dict[str, Any]:
        for attempt in range(self._max_retries + 1):
            try:
                resp = self._sync.get(self._base + path)
                self._raise_for_status(resp)
                return resp.json()
            except httpx.TimeoutException as exc:
                if attempt >= self._max_retries:
                    raise LlmTimeoutError(f"GET {path} timed out") from exc
                time.sleep(_backoff_delay(attempt))
            except httpx.RequestError as exc:
                if attempt >= self._max_retries:
                    raise LlmConnectionError(f"GET {path} 連線錯誤: {exc}") from exc
                time.sleep(_backoff_delay(attempt))
            except LlmAPIError as exc:
                if not _should_retry_status(exc.status) or attempt >= self._max_retries:
                    raise
                time.sleep(_backoff_delay(attempt))
        raise RuntimeError("unreachable")  # pragma: no cover

    def _post_json(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        for attempt in range(self._max_retries + 1):
            try:
                resp = self._sync.post(self._base + path, json=body)
                self._raise_for_status(resp)
                return resp.json()
            except httpx.TimeoutException as exc:
                if attempt >= self._max_retries:
                    raise LlmTimeoutError(f"POST {path} timed out") from exc
                time.sleep(_backoff_delay(attempt))
            except httpx.RequestError as exc:
                if attempt >= self._max_retries:
                    raise LlmConnectionError(f"POST {path} 連線錯誤: {exc}") from exc
                time.sleep(_backoff_delay(attempt))
            except LlmAPIError as exc:
                if not _should_retry_status(exc.status) or attempt >= self._max_retries:
                    raise
                time.sleep(_backoff_delay(attempt))
        raise RuntimeError("unreachable")  # pragma: no cover

    async def _apost_json(
        self,
        path: str,
        body: dict[str, Any],
        *,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        eff_timeout = timeout if timeout is not None else self._timeout
        for attempt in range(self._max_retries + 1):
            try:
                resp = await self._async.post(
                    self._base + path,
                    json=body,
                    timeout=eff_timeout,
                )
                self._raise_for_status(resp)
                return resp.json()
            except httpx.TimeoutException as exc:
                if attempt >= self._max_retries:
                    raise LlmTimeoutError(f"POST {path} timed out") from exc
                await asyncio.sleep(_backoff_delay(attempt))
            except httpx.RequestError as exc:
                if attempt >= self._max_retries:
                    raise LlmConnectionError(f"POST {path} 連線錯誤: {exc}") from exc
                await asyncio.sleep(_backoff_delay(attempt))
            except LlmAPIError as exc:
                if not _should_retry_status(exc.status) or attempt >= self._max_retries:
                    raise
                await asyncio.sleep(_backoff_delay(attempt))
        raise RuntimeError("unreachable")  # pragma: no cover

    @staticmethod
    def _raise_for_status(resp: httpx.Response) -> None:
        if resp.is_success:
            return
        try:
            detail = resp.text
        except Exception:
            detail = "<unreadable>"
        raise LlmAPIError(
            f"HTTP {resp.status_code}",
            status=resp.status_code,
            detail=detail,
        )
