"""OpenAI 相容後端的 HTTP 薄殼：對話、embedding、重排、模型清單；後端專屬的事（管理 API、自癒）交給掛上來的 admin。

架構定位：技術層（llm/client），只依賴 httpx 與標準庫；不認得 Discord、不讀設定檔、不認得任何一家後端的管理 API。
  上層：服務層的 LLMService（對話）、SafeLLMEmbedding（embedding）、HttpReranker（重排）、LlmProxy（替 Hermes 原樣轉送）。
  下層：httpx。後端專屬的事由 `admin`（`BackendAdmin`，例：`llm.client.lemonade_admin.LemonadeAdmin`）做，沒掛就不做。

介面：
  - chat_completion／embedding／aembedding／rerank／list_models：標準端點，照 max_retries 重試。
  - chat_completion_raw／chat_completion_stream：別人組好的請求原樣送出，不重試（對方自己有退避）。
  - admin_get(path)：任何後端的唯讀觀測端點，給故障快照用；永不 raise。
  - is_unreachable／is_backend_fault／backend_looks_broken：給呼叫端分類錯誤。
  - judge_failure／raise_verdict：送出失敗的分類與丟出，admin 的管理 API 也用同一份。
  - `admin`：建構時掛上的 `BackendAdmin`（`unwrap(data)` 拆後端特有的錯誤信封、`heal(model, reason)` 重載），可為 None。

規則：
  - 送出失敗怎麼辦只有 `judge_failure` 一份：重不重試看錯誤種類與剩幾次；重不重載只看後端是不是卡死或壞了，
    和還剩幾次重試無關。sync 與 async 各一個只負責送出與等待的薄迴圈（`_send`／`_asend`），都照它。
  - 要不要重載、怎麼重載是 admin 的事；沒有 admin 的後端（Ollama、vLLM）遇到同樣的錯誤只照一般重試收尾。
  - 不綁 openai SDK：wire 格式自 2023 年沒有破壞性更動，是各家本機後端（Ollama、Lemonade、vLLM、llama.cpp server）
    的事實標準；SDK 與周邊套件（LlamaIndex 的 OpenAIEmbedding 模型名稱白名單）反而炸過。切後端只改 base_url 與 admin。

例外與決策：
  - 不重試的呼叫端（拿著 GPU 閘門算 embedding、替 Hermes 轉送、串流）後端壞了照樣重載，只是重載完不重送、
    照原錯誤丟出，由它下一輪再做：聊天記憶的寫入就走這條路，不重載就只能等別的路徑碰到同樣的錯順便修好。
  - 對話請求等回應的逾時不重試：逾時代表模型還在寫，再送只會讓同一題拿著顯示卡寫三遍。
  - `UpstreamWedge` 繼承 httpx.ConnectError：它是 admin 拆信封時丟出的「後端卡死」，對呼叫端來說就是連不上。
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from dataclasses import dataclass
from typing import Any, Callable, NoReturn, Protocol

import httpx

logger = logging.getLogger(__name__)

#: 後端自己說它壞了的訊號（5xx 的 body）：顯示卡裝置掉了、解碼失敗。行程還活著、健康檢查仍是 ready，
#: 只有重載那顆模型才會好。其他 5xx（可能是這筆請求讓後端出錯）不重載
_BACKEND_BROKEN_SIGNATURES = ("ErrorDeviceLost", "device lost", "decode() failed", "vk::", "CUDA error", "HIP error")

# 連線層 / 暫時性錯誤的指數退避：對齊原 openai SDK max_retries=2
DEFAULT_MAX_RETRIES = 2
DEFAULT_BACKOFF_INITIAL_S = 1.0
DEFAULT_BACKOFF_FACTOR = 2.0


class LlmAPIError(Exception):
    """HTTP 非 2xx 或回應格式異常。

    `status is not None` 表示 HTTP 層錯誤；
    `status is None` 表示 2xx 但回應格式不符預期。
    `kind` 用來分類 2xx 異常（"no_choices" / "empty_content" 等），
    讓 caller 不需要靠 message 字串判斷類型。
    """

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        detail: str = "",
        kind: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.detail = detail
        self.kind = kind


class LlmConnectionError(Exception):
    """無法連線到 LLM 後端（DNS / TCP / TLS 等已重試用盡）。"""


class LlmTimeoutError(Exception):
    """LLM 後端逾時（已重試用盡）。"""


def is_unreachable(exc: BaseException) -> bool:
    """連不上或逾時（已重試用盡）：跟請求內容無關，後端恢復前換個寫法重送也不會好，呼叫端該停手、晚點再試。

    和「某個請求本身有問題」（`LlmAPIError`，例如某段文字讓後端出錯）分開：後者換個寫法或略過那筆就好。
    """
    return isinstance(exc, (LlmConnectionError, LlmTimeoutError))


def is_backend_fault(exc: BaseException) -> bool:
    """後端本身的問題：連不上、逾時，或回 5xx——跟這筆請求的內容無關，換個寫法重送也不會好，呼叫端該停手、晚點再試。

    和 `is_unreachable` 的差別只在 5xx：後端有回應但它自己壞了（例如顯示卡裝置掉了，行程還活著）。以前 5xx 被當成
    「這筆文字的問題」逐則略過，後端壞四小時就丟四小時的訊息。"""
    return is_unreachable(exc) or (isinstance(exc, LlmAPIError) and exc.status is not None and exc.status >= 500)


def backend_looks_broken(exc: BaseException) -> bool:
    """5xx 而且 body 帶後端壞掉的訊號（`_BACKEND_BROKEN_SIGNATURES`）：值得重載那顆模型再試。"""
    if not (isinstance(exc, LlmAPIError) and exc.status is not None and exc.status >= 500):
        return False
    detail = exc.detail or ""
    return any(signature in detail for signature in _BACKEND_BROKEN_SIGNATURES)


class UpstreamWedge(httpx.ConnectError):
    """後端的閘道活著、但它後面那顆推論行程卡死不回應（admin 拆信封時丟出）。

    繼承 httpx.ConnectError：對呼叫端就是連不上，照常退避重試；薄迴圈認得它，會先叫 admin 重載再送。
    與「整台掛掉」不同：後者連閘道都連不上（真正的 httpx.ConnectError），重載也沒用。
    """


class BackendAdmin(Protocol):
    """後端專屬的兩件事；掛在 `LlmHttpClient.admin`，沒掛就都不做。"""

    def unwrap(self, data: Any) -> Any:
        """拆這家後端「200 但內容是錯誤」的信封：卡死丟 `UpstreamWedge`，其他錯誤丟 `LlmAPIError`，不是信封原樣回。"""
        ...

    def heal(self, model: str, reason: str = "") -> bool:
        """後端卡死或壞了：重載那顆模型。回 True＝已重載。"""
        ...


def _should_retry_status(status: int | None) -> bool:
    """是否該重試：429（rate limit）與 5xx 重試；4xx 不重試。"""
    if status is None:
        return False
    return status == 429 or 500 <= status < 600


def _backoff_delay(attempt: int) -> float:
    return DEFAULT_BACKOFF_INITIAL_S * (DEFAULT_BACKOFF_FACTOR ** attempt)


@dataclass(frozen=True)
class _Verdict:
    """一次送出失敗後的處置：丟什麼例外、還要不要重送、要不要先重載那顆模型（None＝不用）。"""

    error: BaseException
    retry: bool
    heal_reason: str | None


def judge_failure(
    exc: BaseException, *, label: str, path: str, attempt: int, max_retries: int, retry_on_read_timeout: bool = True,
) -> _Verdict:
    """送出失敗的分類只有這一份：連不上、逾時、非 2xx、後端自己說它壞了，各該怎麼辦。

    重不重試看錯誤種類與剩幾次；重不重載只看錯誤是不是「後端卡死或壞了」，不看還剩幾次重試：
    不重試的呼叫端也要把壞掉的後端救回來，只是重載完不重送、照原錯誤丟出。
    """
    more = attempt < max_retries
    if isinstance(exc, UpstreamWedge):
        return _Verdict(LlmConnectionError(f"{label} {path} upstream backend 卡死未癒: {exc}"), more, "upstream wedge")
    if isinstance(exc, httpx.TimeoutException):
        # 連線階段的逾時（ConnectTimeout）是網路問題照舊重試；等回應的逾時由呼叫端決定要不要
        waited_for_reply = isinstance(exc, httpx.ReadTimeout)
        retry = more and (retry_on_read_timeout or not waited_for_reply)
        return _Verdict(LlmTimeoutError(f"{label} {path} timed out"), retry, None)
    if isinstance(exc, httpx.RequestError):
        return _Verdict(LlmConnectionError(f"{label} {path} 連線錯誤: {exc}"), more, None)
    if isinstance(exc, LlmAPIError):
        reason = (exc.detail or "")[:160] if backend_looks_broken(exc) else None
        return _Verdict(exc, more and _should_retry_status(exc.status), reason)
    return _Verdict(exc, False, None)


def raise_verdict(verdict: _Verdict, exc: BaseException) -> NoReturn:
    if verdict.error is exc:
        raise exc
    raise verdict.error from exc


def _require_json_key(data: Any, key: str, *, op_label: str) -> Any:
    """從回應 dict 安全取 key；缺 key / 型別不符時 raise `LlmAPIError` 並附結構摘要。

    取代各 endpoint 內裸寫 `data[key]` 的反模式——當後端回應結構漂移（換版本、
    換 OpenAI compat vs native shape、邊界 error envelope 沒被 unwrap 等）時，
    給 caller 看得懂的訊息而非空泛的 `KeyError: 'data'`。

    回傳該 key 的值；長度 / 內容由 caller 自行檢查。
    """
    if not isinstance(data, dict):
        raise LlmAPIError(
            f"{op_label} 回應不是 dict：type={type(data).__name__} sample={str(data)[:300]}",
            status=None,
            detail=str(data)[:1000],
        )
    if key not in data:
        raise LlmAPIError(
            f"{op_label} 回應缺少 key='{key}'：keys={list(data.keys())} sample={str(data)[:300]}",
            status=None,
            detail=str(data)[:1000],
        )
    return data[key]


class LlmHttpClient:
    """OpenAI dialect HTTP 薄殼：chat / embedding / models 三個端點。"""

    def __init__(
        self,
        *,
        base_url: str,
        timeout: float,
        max_retries: int = DEFAULT_MAX_RETRIES,
        api_key: str = "no-auth",
        admin: BackendAdmin | None = None,
    ) -> None:
        # 保存 host 而非預組 /v1：觀測端點（admin_get）在別的 prefix，兩條路徑共用同一台 server
        self._host = base_url.rstrip("/")
        self._timeout = timeout
        self._max_retries = max_retries
        #: 後端專屬的拆信封與重載；None＝這家後端沒有（或不需要）
        self.admin = admin
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

        等回應的逾時不重試：對話請求等到逾時，代表模型還在寫（或後端卡住），不是連線抖動；
        再送兩次只會讓同一題拿著顯示卡寫三遍（實測一題卡了 12 分半）。連不上（連線階段逾時）、連線錯誤與 5xx 照樣重試。
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
        return await self._apost_json("/chat/completions", body, timeout=timeout, retry_on_read_timeout=False)

    async def chat_completion_raw(self, body: dict[str, Any], *, timeout: float | None = None) -> dict[str, Any]:
        """把別人組好的 /v1/chat/completions 請求原樣送出（非串流），回後端的 JSON；**不重試**。

        給轉發用：對方（Hermes 這類客戶端）自己有重試與退避，這裡再重試會變成同一題佔著顯示卡寫好幾遍。
        非 2xx 丟 `LlmAPIError`（帶後端原文，讓呼叫端原樣交回去）；連不上、逾時的分類和 `chat_completion` 相同。
        後端卡死（admin 拆信封認出來）或壞了（5xx 帶裝置掉了的訊號）時，有 admin 就重載一次（有冷卻），
        但不重送：卡死當連不上丟出去，轉發端才會回 503 讓對方退避。
        """
        return await self._asend(
            lambda: self._async.post(self._host + "/v1/chat/completions", json=body, timeout=timeout or self._timeout),
            label="POST", path="/chat/completions", model=str(body.get("model") or ""), max_retries=0,
        )

    @contextlib.asynccontextmanager
    async def chat_completion_stream(self, body: dict[str, Any], *, timeout: float | None = None):
        """原樣送出串流請求，交出後端的 SSE 回應（`httpx.Response`，用 `aiter_lines()` 讀）；**不重試**。

        進入區段前已確認是 2xx：非 2xx 先把本文讀完再丟 `LlmAPIError`，呼叫端才能把狀態碼與原文原樣交回去；
        後端壞了（5xx 帶裝置掉了的訊號）也重載一次再丟。離開區段就關掉回應，後端收到客戶端斷線會停止生成。
        讀取途中的逾時、連線錯誤也轉成同一套例外。
        """
        model = str(body.get("model") or "")
        try:
            async with self._async.stream("POST", self._host + "/v1/chat/completions", json=body,
                                          timeout=timeout or self._timeout) as resp:
                if not resp.is_success:
                    await resp.aread()
                    self._raise_for_status(resp)
                yield resp
        except (httpx.RequestError, LlmAPIError) as exc:
            verdict = judge_failure(exc, label="POST", path="/chat/completions (stream)", attempt=0, max_retries=0)
            if verdict.heal_reason is not None and self.admin is not None:
                await asyncio.to_thread(self.admin.heal, model, verdict.heal_reason)
            raise_verdict(verdict, exc)

    # ---------- embedding ----------

    def embedding(self, *, model: str, input: str | list[str]) -> list[list[float]]:
        """POST /v1/embeddings（sync）。

        即使 `input` 是單一字串也回傳 list[list[float]]，caller 自取 `[0]`，
        簡化 batch / single 共用 code path。
        """
        data = self._post_json("/embeddings", {"model": model, "input": input})
        items = _require_json_key(data, "data", op_label="embedding(sync)")
        return [item["embedding"] for item in items]

    async def aembedding(
        self,
        *,
        model: str,
        input: str | list[str],
    ) -> list[list[float]]:
        data = await self._apost_json("/embeddings", {"model": model, "input": input})
        items = _require_json_key(data, "data", op_label="embedding(async)")
        return [item["embedding"] for item in items]

    # ---------- rerank ----------

    def rerank(self, *, model: str, query: str, documents: list[str]) -> list[float]:
        """POST /v1/rerank（sync；llama.cpp 與 Lemonade 的格式，和 Jina 相容）。

        回傳的分數順序對齊 `documents`（後端回的 results 依分數排序，這裡照 index 放回原位）；
        後端漏掉的文件給負無限大，排到最後。
        """
        if not documents:
            return []
        data = self._post_json("/rerank", {"model": model, "query": query, "documents": documents,
                                           "top_n": len(documents)})
        items = _require_json_key(data, "results", op_label="rerank(sync)")
        scores = [float("-inf")] * len(documents)
        for item in items:
            index = item.get("index")
            if isinstance(index, int) and 0 <= index < len(documents):
                scores[index] = float(item.get("relevance_score", item.get("score", float("-inf"))))
        return scores

    # ---------- models（啟動自我測試 / 觀測用）----------

    def list_models(self) -> list[str]:
        """GET /v1/models，回傳 model id 字串清單（去除空字串）。"""
        data = self._get_json("/models")
        return [m.get("id", "") for m in data.get("data", []) if m.get("id")]

    # ---------- 觀測端點（故障快照用） ----------

    async def admin_get(
        self,
        path: str,
        *,
        timeout: float = 2.0,
    ) -> dict[str, Any]:
        """Best-effort GET，給故障路徑診斷快照用。

        `path` 是完整路徑（例如 ``"/api/v1/health"``、``"/api/v1/system-info"``），
        跟 chat / embedding 自動加 ``/v1`` 前綴的低階路徑不同。

        任何錯誤吞掉、永不 raise；回值描述：
          - 成功：``{"status": 200, "body": <json|str-truncated>}``
          - HTTP 非 2xx：``{"status": <code>, "body": <text>[:500]}``
          - 連線/timeout：``{"err": "<ExceptionType>: <msg>"}``

        只給 snapshot helper 呼叫；不該塞進熱路徑或 retry 邏輯。
        """
        url = self._host + path
        try:
            resp = await self._async.get(url, timeout=timeout)
        except httpx.TimeoutException as exc:
            return {"err": f"timeout after {timeout}s: {exc}"}
        except httpx.RequestError as exc:
            return {"err": f"{type(exc).__name__}: {exc}"}
        ct = resp.headers.get("content-type", "")
        if "application/json" in ct:
            try:
                return {"status": resp.status_code, "body": resp.json()}
            except Exception:
                return {"status": resp.status_code, "body": resp.text[:500]}
        return {"status": resp.status_code, "body": resp.text[:500]}

    # ---------- low-level：送出與等待的薄迴圈；失敗怎麼辦交給 _judge ----------

    def _send(
        self, do_request: Callable[[], Any], *, label: str, path: str, model: str, max_retries: int | None = None,
    ) -> Any:
        """同步：送出、等回應、交給 admin 拆信封；失敗照 `judge_failure`，要重載就叫 admin（沒有 admin 就不重載）。"""
        max_retries = self._max_retries if max_retries is None else max_retries
        for attempt in range(max_retries + 1):
            try:
                resp = do_request()
                self._raise_for_status(resp)
                return self._unwrap(resp.json())
            except (httpx.RequestError, LlmAPIError) as exc:
                verdict = judge_failure(exc, label=label, path=path, attempt=attempt, max_retries=max_retries)
                healed = (verdict.heal_reason is not None and self.admin is not None
                          and self.admin.heal(model, verdict.heal_reason))
                if not verdict.retry:
                    raise_verdict(verdict, exc)
                if not healed:
                    time.sleep(_backoff_delay(attempt))   # 重載過就立刻重送：載入本身已經等過了
        raise RuntimeError("unreachable")  # pragma: no cover

    async def _asend(
        self, do_request: Callable[[], Any], *, label: str, path: str, model: str,
        max_retries: int | None = None, retry_on_read_timeout: bool = True,
    ) -> Any:
        """非同步版的 `_send`；重載是同步 HTTP，包 to_thread 不擋 event loop。"""
        max_retries = self._max_retries if max_retries is None else max_retries
        for attempt in range(max_retries + 1):
            try:
                resp = await do_request()
                self._raise_for_status(resp)
                return self._unwrap(resp.json())
            except (httpx.RequestError, LlmAPIError) as exc:
                verdict = judge_failure(exc, label=label, path=path, attempt=attempt, max_retries=max_retries,
                                        retry_on_read_timeout=retry_on_read_timeout)
                healed = (verdict.heal_reason is not None and self.admin is not None
                          and await asyncio.to_thread(self.admin.heal, model, verdict.heal_reason))
                if not verdict.retry:
                    raise_verdict(verdict, exc)
                if not healed:
                    await asyncio.sleep(_backoff_delay(attempt))
        raise RuntimeError("unreachable")  # pragma: no cover

    def _unwrap(self, data: Any) -> Any:
        return self.admin.unwrap(data) if self.admin is not None else data

    def _get_json(self, path: str) -> dict[str, Any]:
        return self._send(lambda: self._sync.get(self._host + "/v1" + path), label="GET", path=path, model="")

    def _post_json(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        return self._send(
            lambda: self._sync.post(self._host + "/v1" + path, json=body),
            label="POST", path=path, model=str(body.get("model", "")),
        )

    async def _apost_json(
        self,
        path: str,
        body: dict[str, Any],
        *,
        timeout: float | None = None,
        retry_on_read_timeout: bool = True,
    ) -> dict[str, Any]:
        eff_timeout = timeout if timeout is not None else self._timeout
        return await self._asend(
            lambda: self._async.post(self._host + "/v1" + path, json=body, timeout=eff_timeout),
            label="POST", path=path, model=str(body.get("model", "")), retry_on_read_timeout=retry_on_read_timeout,
        )

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
