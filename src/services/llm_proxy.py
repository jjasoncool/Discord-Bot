"""給 Hermes 用的模型端點：掛在通知伺服器上的 `/v1/models` 與 `/v1/chat/completions`，
驗金鑰、擋模型名、排 GPU 閘門之後把請求原樣轉給 Lemonade。

架構定位：服務層（`services`），不 import discord。上層：`services.notify_server`（把路由掛到它的 aiohttp app）。
下層：`services.llm_service`（模型名稱、推 ctx）、`llm.client.http_client`（原樣送出）、`llm.client.gpu_gate`（閘門）。

介面：
- `LlmProxy(settings, llm=, client=, gate=)`：`add_routes(app)` 掛兩條路由；`handle_models`、`handle_chat` 是 aiohttp 處理函式。
- `allowed_models()`：目前放行的模型名稱（bot 正在用的那個）。

規則：
- 只認 `Authorization: Bearer <HERMES_API_KEY>`；通知端點的 `X-Notify-Secret` 在這裡無效，反過來也一樣。
- 模型名不是 bot 正在用的那個一律 400：Lemonade 一次只載得下一顆大模型，放行別的名字等於讓它再載一顆。
- 整段回應（含串流）都拿著 GPU 閘門，和插話、/askai 排同一個隊；串流每寫出一塊就續租，租約到期代表卡住、放鎖。
- 不重試、不改請求內容（溫度、思考開關都照對方給的）；只補 `max_tokens` 上限與串流的 `stream_options.include_usage`。
- 每次請求記一行 `llm_usage`（功能名 hermes），和 bot 自己的請求同一個檔。

例外與決策：
- 等閘門最多 `proxy_max_wait_seconds`，超過回 503＋Retry-After：Hermes 自己會退避重試，在外面等比在 bot 裡排一長串好。
- 正在產圖（`imagegen_busy`）直接回 503：那是數十分鐘的獨佔，不值得排。
- 放在 bot 行程而不是另開容器：讓位（`stream_busy`）在同一行程才看得到，`llm_usage` 也在同一個檔。
- bot 之後呼叫 Hermes 時**不能拿著 GPU 閘門**：Hermes 會回頭打這裡要同一把鎖，行程內的鎖沒有等待上限，會互等到逾時。
"""
from __future__ import annotations

import asyncio
import contextlib
import hmac
import json
import logging
import time
from typing import Any, Callable

from aiohttp import web

from llm.client.http_client import LlmAPIError, LlmHttpClient, is_unreachable
from llm.client.gpu_gate import gpu_exclusive, imagegen_busy
from llm.client.backend_admin import admin_for
from services.llm_service import LLM_SERVICE_SETTINGS, LLMService, log_llm_usage
from sys_settings.hermes_settings import HermesSettings
from sys_settings.llm_settings import load_llm_runtime_config

logger = logging.getLogger(__name__)

_BEARER = "Bearer "
_SSE_DATA = "data: "


def _error(status: int, message: str, *, code: str, retry_after: int | None = None) -> web.Response:
    """OpenAI 風格的錯誤本文：客戶端照 `error.code` 與狀態碼決定要不要重試。"""
    headers = {"Retry-After": str(retry_after)} if retry_after is not None else None
    kind = "invalid_request_error" if status < 500 else "server_error"
    return web.json_response({"error": {"message": message, "type": kind, "code": code}}, status=status, headers=headers)


def _upstream_error_body(exc: LlmAPIError) -> dict[str, Any]:
    """後端回的非 2xx：本文是 JSON 就原樣交回去（客戶端看得懂 OpenAI 格式的錯），不是就包一層。"""
    try:
        parsed = json.loads(exc.detail)
    except ValueError:
        parsed = None
    if isinstance(parsed, dict):
        return parsed
    return {"error": {"message": exc.detail or str(exc), "type": "server_error", "code": "upstream_error"}}


class LlmProxy:
    def __init__(
        self,
        settings: HermesSettings,
        *,
        llm: LLMService | None = None,
        client: LlmHttpClient | None = None,
        gate: Callable[..., Any] = gpu_exclusive,
    ) -> None:
        self.settings = settings
        self._llm = llm or LLMService()
        self._timeout = float(LLM_SERVICE_SETTINGS.llm_timeout)
        if client is None:
            try:
                backend = load_llm_runtime_config(LLM_SERVICE_SETTINGS.llm_runtime_model_path).backend
            except RuntimeError:   # 缺檔或壞檔：當作沒有管理 API 的後端，照樣能轉送
                backend = None
            base_url = LLM_SERVICE_SETTINGS.llm_base_url
            client = LlmHttpClient(base_url=base_url, timeout=self._timeout, admin=admin_for(backend, base_url))
        self._client = client
        self._gate = gate

    def add_routes(self, app: web.Application) -> None:
        app.router.add_get("/v1/models", self.handle_models)
        app.router.add_post("/v1/chat/completions", self.handle_chat)

    def allowed_models(self) -> set[str]:
        return {self._llm.resolve_request_model()}

    def _authorized(self, request: web.Request) -> bool:
        header = request.headers.get("Authorization", "")
        if not header.startswith(_BEARER):
            return False
        # 用 bytes 比：str 版的 compare_digest 只收 ASCII，標頭帶非 ASCII 會變 TypeError、沒驗證的請求就打出 500
        token = header[len(_BEARER):].encode("utf-8", "surrogateescape")
        return hmac.compare_digest(token, self.settings.api_key.encode("utf-8"))

    async def handle_models(self, request: web.Request) -> web.Response:
        if not self._authorized(request):
            return _error(401, "金鑰不符", code="unauthorized")
        data = [{"id": name, "object": "model", "owned_by": "local"} for name in sorted(self.allowed_models())]
        return web.json_response({"object": "list", "data": data})

    async def handle_chat(self, request: web.Request) -> web.StreamResponse:
        if not self._authorized(request):
            logger.warning("拒絕模型請求：金鑰不符 remote=%s", request.remote)
            return _error(401, "金鑰不符", code="unauthorized")
        try:
            # 本文上限只放大這個端點（長 context 的對話會超過 aiohttp 預設的 1 MiB），/notify 維持預設
            body = await request.clone(client_max_size=self.settings.proxy_max_body_bytes).json()
        except web.HTTPRequestEntityTooLarge:
            return _error(413, "請求本文太大", code="body_too_large")
        except Exception:  # 邊界：對外的一次請求，本文壞掉只回 400
            return _error(400, "請求本文不是 JSON", code="invalid_json")
        if not isinstance(body, dict) or not isinstance(body.get("messages"), list):
            return _error(400, "缺少 messages", code="invalid_request")

        model = str(body.get("model") or "")
        allowed = self.allowed_models()
        if model not in allowed:
            return _error(400, f"模型 {model!r} 不在白名單，只放行 {sorted(allowed)}", code="model_not_found")

        cap = self.settings.proxy_max_tokens
        # llama.cpp 以 n_predict 優先蓋掉 max_tokens、OpenAI 的 max_completion_tokens 也等價：三個一起夾、只留 max_tokens，
        # 不然帶 n_predict:-1 就能繞過上限寫到 ctx 填滿（租約每塊都續、擋不住）
        requested = [body.pop(key, None) for key in ("max_tokens", "n_predict", "max_completion_tokens")]
        valid = [v for v in requested if isinstance(v, int) and not isinstance(v, bool) and v > 0]
        body["max_tokens"] = min(min(valid), cap) if valid else cap
        stream = bool(body.get("stream"))
        if stream:
            options = dict(body.get("stream_options") or {})
            options["include_usage"] = True
            body["stream_options"] = options

        if imagegen_busy():
            return _error(503, "正在產圖，顯示卡被占用", code="gpu_busy", retry_after=self.settings.proxy_retry_after_seconds)

        trace = f"hermes-{int(time.time() * 1000)}"
        lease_seconds = self._timeout + self.settings.proxy_lease_extra_seconds
        try:
            async with contextlib.AsyncExitStack() as stack:
                try:
                    async with asyncio.timeout(self.settings.proxy_max_wait_seconds):
                        lease = await stack.enter_async_context(self._gate("hermes", lease_seconds=lease_seconds))
                except TimeoutError:
                    logger.warning("模型請求等 GPU 閘門超過 %.0f 秒，回 503 trace=%s", self.settings.proxy_max_wait_seconds, trace)
                    return _error(503, "顯示卡忙碌，請稍後重試", code="gpu_busy",
                                  retry_after=self.settings.proxy_retry_after_seconds)
                await self._llm.ensure_model_loaded(model)
                if lease is not None:
                    lease.renew()   # 冷載入可能吃掉大半租約；載入完成是可觀測的進展
                if stream:
                    return await self._stream(request, body, model, trace, lease)
                completion = await self._client.chat_completion_raw(body, timeout=self._timeout)
                log_llm_usage(trace, model, completion)
                return web.json_response(completion)
        except LlmAPIError as exc:
            if exc.status in (401, 403):
                # 原樣透傳 401 對方會以為是自己給 bot 的金鑰錯；這是後端在拒絕 bot，換成 502 並標明
                logger.warning("模型後端拒絕驗證 HTTP %s trace=%s", exc.status, trace)
                return _error(502, f"模型後端拒絕驗證（HTTP {exc.status}）", code="upstream_auth")
            # 後端回非 2xx：狀態碼與本文原樣交回去，對方才知道是請求的問題還是後端的問題
            return web.json_response(_upstream_error_body(exc), status=exc.status or 502)
        except Exception as exc:  # 邊界：對外的一次請求，連不上、逾時在這裡轉成狀態碼
            if is_unreachable(exc):
                logger.warning("模型請求轉發失敗（後端連不上或逾時）trace=%s: %s", trace, exc)
                return _error(503, f"模型後端連不上或逾時: {exc}", code="backend_unavailable",
                              retry_after=self.settings.proxy_retry_after_seconds)
            logger.exception("模型請求轉發失敗 trace=%s", trace)
            return _error(500, f"轉發失敗: {exc}", code="proxy_error")

    async def _stream(self, request: web.Request, body: dict[str, Any], model: str, trace: str, lease: Any) -> web.StreamResponse:
        """把後端的 SSE 一行一行原樣寫給對方；進入串流前後端已回 2xx（非 2xx 在 `chat_completion_stream` 就丟出去）。

        送出 200 之後出錯只能在串流裡講：寫一個 `data: {"error": …}` 再結束。對方斷線就直接收工（閘門照放）。
        """
        async with self._client.chat_completion_stream(body, timeout=self._timeout) as upstream:
            response = web.StreamResponse(status=200, headers={"Content-Type": "text/event-stream", "Cache-Control": "no-cache"})
            await response.prepare(request)
            usage_chunk: dict[str, Any] = {}
            last_blank = True   # SSE 的 event 以空行結束；錯誤塊要寫在新的 event 裡，不能黏在前一個 data 行後面
            try:
                async for line in upstream.aiter_lines():
                    await response.write((line + "\n").encode("utf-8"))
                    last_blank = line == ""
                    if lease is not None:
                        lease.renew()
                    if line.startswith(_SSE_DATA) and ('"usage"' in line or '"timings"' in line):
                        try:
                            chunk = json.loads(line[len(_SSE_DATA):])
                        except ValueError:
                            continue
                        if isinstance(chunk, dict):
                            for key in ("usage", "timings"):
                                if chunk.get(key):
                                    usage_chunk[key] = chunk[key]
            except (ConnectionResetError, ConnectionError):
                logger.info("模型請求的對方中途斷線 trace=%s", trace)
                return response
            except Exception as exc:  # 邊界：200 已經送出，只能在串流裡回報
                logger.warning("模型請求串流中斷 trace=%s: %s", trace, exc)
                with contextlib.suppress(ConnectionResetError, ConnectionError):
                    payload = {"error": {"message": str(exc), "type": "server_error", "code": "stream_failed"}}
                    prefix = "" if last_blank else "\n"
                    await response.write((prefix + _SSE_DATA + json.dumps(payload, ensure_ascii=False) + "\n\n").encode("utf-8"))
            with contextlib.suppress(ConnectionResetError, ConnectionError):
                await response.write_eof()
        log_llm_usage(trace, model, usage_chunk)
        return response
