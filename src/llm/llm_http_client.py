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
import json
import logging
import threading
import time
from typing import Any

import httpx

logger = logging.getLogger("discord_bot")

# 跨 LlmHttpClient instance 共用：(host, model, options_json) → True
# Lemonade 的「已載入此 model + 此 options」狀態是 server 端全域屬性，
# bot 內 LLMService / SafeLLMEmbedding 各有自己的 client 但打的是同一個 Lemonade，
# 共用 cache 才不會每個 instance 重複 push 一遍 /api/v1/load。
_LEMONADE_LOADED: dict[tuple[str, str, str], bool] = {}
_LEMONADE_LOAD_LOCK = threading.Lock()

# 自癒：偵測到「Lemonade admin 活著、但它 CURL 轉發的 downstream backend 卡死」(upstream
# network_error) 時，重發 /api/v1/load 把那顆 backend respawn。每個 (host, model) 設冷卻，
# 避免 Lemonade 真的整台掛掉時狂發 load。
_LEMONADE_HEAL_COOLDOWN_S = 60.0
_LEMONADE_LAST_HEAL: dict[tuple[str, str], float] = {}


def reset_lemonade_load_cache() -> None:
    """清掉 Lemonade load cache（測試 / Lemonade 端被外部改動時手動觸發 re-ensure 用）。"""
    with _LEMONADE_LOAD_LOCK:
        _LEMONADE_LOADED.clear()
        _LEMONADE_LAST_HEAL.clear()

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


class _LemonadeUpstreamWedge(httpx.ConnectError):
    """Lemonade admin 活著、但它 CURL 轉發的 downstream backend process 卡死/不回應
    （回 200 + {"error":{"type":"network_error", message 含 "Couldn't connect to server"}}）。

    繼承 httpx.ConnectError → 既有的 `except httpx.RequestError` 仍照常退避重試（向後相容），
    但低階 retry loop 可特別攔它做「重發 /api/v1/load respawn backend → retry 原請求」的自癒。
    與「Lemonade 整台掛掉」不同：後者連 admin 都連不上（真正的 httpx.ConnectError），重載
    也沒用、不會走到這支自癒。
    """


def _should_retry_status(status: int | None) -> bool:
    """是否該重試：429（rate limit）與 5xx 重試；4xx 不重試。"""
    if status is None:
        return False
    return status == 429 or 500 <= status < 600


def _backoff_delay(attempt: int) -> float:
    return DEFAULT_BACKOFF_INITIAL_S * (DEFAULT_BACKOFF_FACTOR ** attempt)


def _unwrap_response_envelope(data: Any) -> Any:
    """處理 Lemonade 風格的「200 OK + {"error": {...}}」反 HTTP envelope。

    Lemonade 在內部 CURL 轉發到 downstream backend 失敗時，會把錯誤包成 200 OK
    回傳，與正常 OpenAI 格式同一 endpoint 但 payload 是 `{"error": {...}}` 而非
    `{"data": [...]}` / `{"choices": [...]}`。下游若直接 `data["data"]` 會撞
    KeyError、訊息僅 `'data'` 兩字，無法判斷實際後端狀態。

    分流：
      - `error.type == "network_error"` → `httpx.ConnectError`（連線層暫時錯誤，
        交給上層退避重試）
      - 其他 error type → `LlmAPIError(status=None)`（服務端永久錯誤，不重試）
      - 非 envelope / 無 error key → 原樣回傳

    這層接在 `_post_json` / `_apost_json` 出口，所有 POST 端點（chat / embedding /
    未來新增）都自動享有相同的錯誤護網，不必每個 endpoint 各寫一份。
    """
    if not isinstance(data, dict):
        return data
    err = data.get("error")
    if not isinstance(err, dict):
        return data
    err_type = str(err.get("type", "")).strip()
    err_msg = str(err.get("message", "")).strip()
    if err_type == "network_error":
        # downstream backend 卡死 → 專屬 wedge 例外，讓低階 retry loop 觸發「重載 backend」自癒
        raise _LemonadeUpstreamWedge(f"upstream network_error: {err_msg}")
    raise LlmAPIError(
        f"upstream error envelope: type={err_type or '<unknown>'} message={err_msg or '<empty>'}",
        status=None,
        detail=str(data)[:1000],
    )


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
    ) -> None:
        # 保存 host 而非預組 /v1：因為 Lemonade 的 admin API 在 /api/v1/...，
        # OpenAI dialect 在 /v1/...，兩條路徑共用同一台 server 不同 prefix
        self._host = base_url.rstrip("/")
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

    # ---------- models（啟動自我測試 / 觀測用）----------

    def list_models(self) -> list[str]:
        """GET /v1/models，回傳 model id 字串清單（去除空字串）。"""
        data = self._get_json("/models")
        return [m.get("id", "") for m in data.get("data", []) if m.get("id")]

    # ---------- Lemonade admin（/api/v1/load, /api/v1/health, ...） ----------

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

    def ensure_lemonade_model(
        self,
        *,
        model: str,
        options: dict[str, Any] | None,
        load_timeout: float = 180.0,
    ) -> None:
        """確認 Lemonade 已用指定 `recipe_options` 載入 `model`，若沒有就觸發 reload。

        process 內 cache：同一個 (host, model, options) 組合只會打一次 `/api/v1/load`。
        Lemonade 端對未變動的 options 通常會 short-circuit 不重載，但避免每次 chat /
        embed 都打一次 admin API 還是值得 cache。

        本方法是 sync HTTP；async caller 請用 `asyncio.to_thread` 包起來避免阻塞 loop。

        非 Lemonade 後端不該呼叫這個 method（caller 負責判斷 backend type）。
        """
        if not options:
            return
        opts_json = json.dumps(options, sort_keys=True)
        cache_key = (self._host, model, opts_json)
        with _LEMONADE_LOAD_LOCK:
            if cache_key in _LEMONADE_LOADED:
                return
            self._lemonade_load_model(
                model_name=model,
                recipe_options=options,
                timeout=load_timeout,
            )
            _LEMONADE_LOADED[cache_key] = True
            logger.info(
                "Lemonade model loaded: model=%s recipe_options=%s",
                model, options,
            )

    def _lemonade_load_model(
        self,
        *,
        model_name: str,
        recipe_options: dict[str, Any],
        timeout: float,
        save_options: bool = True,
    ) -> None:
        """POST /api/v1/load（Lemonade 原生 admin API）。

        Lemonade 載入大模型可能要 30-60 秒，因此用較長的 timeout（呼叫端傳入）。
        重試政策跟一般 wire 不同：admin API 失敗多半是 server 設定問題，
        retry 沒意義，直接拋 `LlmAPIError` / `LlmConnectionError` 出去。
        """
        url = self._host + "/api/v1/load"
        # Lemonade /api/v1/load 用「平鋪」參數（ctx_size 等直接在 top-level，會翻成 llama-server 旗標）。
        # save_options=True：把 ctx_size 持久化進 Lemonade 的 recipe_options.json
        #   → 之後每次載入（含 /askai swap 後重載）模型都吃對的 ctx，不會回退預設 4096。
        #
        # ⚠️ 鐵則（違反會像 --embeddings 那次把整顆模型載掛、且被 save_options 永久存住）：
        #   recipe_options（＝ config 的 model_load_options）**只准放非 reserved 的選項**（如 ctx_size）。
        #   **絕不可放 Lemonade 的 reserved 旗標**（--embeddings / --ctx-size / --device / --gpu-layers …）——
        #   那些由 Lemonade 依模型「標籤」自動管理；手動帶 + save_options = model_load_error 且永久毒化。
        body: dict[str, Any] = {
            "model_name": model_name,
            **dict(recipe_options),
            "save_options": save_options,
        }
        try:
            resp = self._sync.post(url, json=body, timeout=timeout)
        except httpx.TimeoutException as exc:
            raise LlmTimeoutError(
                f"Lemonade /api/v1/load timed out after {timeout}s for {model_name}"
            ) from exc
        except httpx.RequestError as exc:
            raise LlmConnectionError(
                f"Lemonade /api/v1/load 連線錯誤 ({model_name}): {exc}"
            ) from exc
        self._raise_for_status(resp)

    def _try_heal_lemonade_backend(self, model: str) -> bool:
        """偵測到 upstream wedge（downstream backend process 卡死）時，重發 /api/v1/load 把
        它 respawn。沿用該 model 最後一次載入的 recipe_options（ctx_size / llamacpp_args，從
        load cache 取），但 save_options=False → 只重生、不覆寫 recipe_options.json（不毒化）。
        帶回原 options 是為了避免裸 reload 讓 ctx 掉回 Lemonade 預設(4096)、害原請求改撞 ctx 超限。

        回 True＝已送出 reload（值得 retry 原請求）；False＝冷卻中 / 無 model / reload 失敗。
        每個 (host, model) 設冷卻，避免 Lemonade 真的整台掛掉時狂發 load。
        """
        if not model:
            return False
        key = (self._host, model)
        now = time.monotonic()
        with _LEMONADE_LOAD_LOCK:
            last = _LEMONADE_LAST_HEAL.get(key)
            if last is not None and now - last < _LEMONADE_HEAL_COOLDOWN_S:
                return False  # 冷卻中：別在 Lemonade 真的掛掉時狂發 load
            _LEMONADE_LAST_HEAL[key] = now
            # 取這顆 model 最後一次載入用的 recipe_options（最近一筆）。掃 cache 在鎖內、安全；
            # 找不到就 fallback 裸 reload（{}）。沿用 options 才不會讓 respawn 的 ctx 掉回預設。
            recipe: dict[str, Any] = {}
            for (cached_host, cached_model, opts_json) in _LEMONADE_LOADED:
                if cached_host == self._host and cached_model == model:
                    try:
                        parsed = json.loads(opts_json)
                        if isinstance(parsed, dict):
                            recipe = parsed
                    except Exception:
                        pass
        try:
            self._lemonade_load_model(
                model_name=model,
                recipe_options=recipe,  # 沿用 ctx_size / llamacpp_args
                timeout=120.0,
                save_options=False,  # 只重生、不持久化
            )
        except Exception as exc:  # reload 也失敗（admin 掛了？）→ 交回原 retry 流程收尾
            logger.warning("Lemonade backend 自癒重載失敗 model=%s：%s", model, exc)
            return False
        logger.warning(
            "Lemonade backend 自癒：偵測到 upstream wedge，已重發 /api/v1/load 重載 model=%s",
            model,
        )
        return True

    # ---------- low-level：retry + error mapping ----------

    def _get_json(self, path: str) -> dict[str, Any]:
        for attempt in range(self._max_retries + 1):
            try:
                resp = self._sync.get(self._host + "/v1" + path)
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
                resp = self._sync.post(self._host + "/v1" + path, json=body)
                self._raise_for_status(resp)
                # envelope unwrap：跟 async path 對稱，所有 POST 端點共用同一層護網
                return _unwrap_response_envelope(resp.json())
            except _LemonadeUpstreamWedge as exc:
                # downstream backend 卡死：重載它再 retry（自癒）。冷卻中/重試用盡則照連線錯誤收尾。
                if attempt < self._max_retries and self._try_heal_lemonade_backend(
                    str(body.get("model", ""))
                ):
                    continue  # 已 respawn → 立刻重試（reload 本身已耗時，不再 backoff）
                if attempt >= self._max_retries:
                    raise LlmConnectionError(
                        f"POST {path} upstream backend 卡死未癒: {exc}"
                    ) from exc
                time.sleep(_backoff_delay(attempt))
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
                    self._host + "/v1" + path,
                    json=body,
                    timeout=eff_timeout,
                )
                self._raise_for_status(resp)
                # envelope unwrap：與 sync path 共用同一層護網（含非 network_error
                # 類型的 error envelope，避免下游 caller 撞 `KeyError: 'data'`）
                return _unwrap_response_envelope(resp.json())
            except _LemonadeUpstreamWedge as exc:
                # downstream backend 卡死：重載它再 retry（自癒）。load 是 sync → to_thread 不擋 loop。
                healed = False
                if attempt < self._max_retries:
                    healed = await asyncio.to_thread(
                        self._try_heal_lemonade_backend, str(body.get("model", ""))
                    )
                if healed:
                    continue  # 已 respawn → 立刻重試
                if attempt >= self._max_retries:
                    raise LlmConnectionError(
                        f"POST {path} upstream backend 卡死未癒: {exc}"
                    ) from exc
                await asyncio.sleep(_backoff_delay(attempt))
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
