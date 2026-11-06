"""Ollama 後端專屬的事：卸載（keep_alive=0）與對話請求的寫法。Ollama 沒有載入與重載 API。

架構定位：技術層（llm/client），只依賴 httpx、標準庫與同層的 http_client（例外分類）。
  上層：`backend_admin.admin_for`（建 `LlmHttpClient` 時掛上）、`backend_admin.chat_style_for`（組對話請求時）。
  下層：Ollama 的 /api/generate。

介面：
- `OllamaAdmin(host)`：`unwrap` 原樣回（Ollama 的錯誤走 HTTP 狀態碼，沒有信封）、`heal` 回 False（沒有重載 API，要救只能在主機端重啟）、
  `ensure_loaded` 不做（沒有載入 API）、`unload(model=)`：送一個空的 /api/generate 帶 keep_alive=0，把模型從 VRAM 帶下去。
- `OllamaChatStyle`：思考開關與強度寫成頂層 `reasoning_effort`（不思考＝`none`），閒置卸載寫成 `keep_alive`；
  設定檔 extra_body 裡的 `think`、`options` 拿掉不送。

規則：
- 卸載走原生 /api/generate、不走對話端點：呼叫端拿著 GPU 閘門時不能再走會回頭要閘門的對話路徑。

例外與決策：
- 對話走 OpenAI 相容端點，它的請求格式（原始碼 `openai/openai.go` 的 `ChatCompletionRequest`）沒有 `think`、`options`：
  思考只能用 `reasoning_effort`／`reasoning.effort`，上下文長度與重複懲罰送了也收不到（要在 Modelfile 設）。
- 沒在真的 Ollama 上實測過（目前後端是 Lemonade）；行為若不符，要改的只有這個檔。
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from llm.client.http_client import LlmAPIError, judge_failure, raise_verdict

logger = logging.getLogger(__name__)


class OllamaAdmin:
    """Ollama 的管理：只有卸載；給 `LlmHttpClient(admin=…)`。"""

    def __init__(self, host: str, *, api_key: str = "no-auth") -> None:
        self._host = host.rstrip("/")
        self._http = httpx.Client(headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})

    def unwrap(self, data: Any) -> Any:
        return data

    def heal(self, model: str, reason: str = "", kind: str | None = None) -> bool:
        logger.debug("Ollama 沒有重載 API，model=%s 的錯誤照一般流程收尾（%s）", model, reason)
        return False

    def ensure_loaded(self, *, model: str, options: dict[str, Any] | None, load_timeout: float = 180.0) -> None:
        return None

    def unload(self, *, model: str, timeout: float = 60.0) -> None:
        """空的 generate 請求帶 keep_alive=0：Ollama 文件寫的卸載方式。"""
        path = "/api/generate"
        try:
            resp = self._http.post(self._host + path, json={"model": model, "keep_alive": 0}, timeout=timeout)
        except httpx.RequestError as exc:
            raise_verdict(judge_failure(exc, label=f"Ollama unload {model}", path=path, attempt=0, max_retries=0), exc)
        if not resp.is_success:
            raise LlmAPIError(f"HTTP {resp.status_code}", status=resp.status_code, detail=resp.text)
        logger.info("Ollama model unloaded (keep_alive=0): model=%s", model)


class OllamaChatStyle:
    """Ollama OpenAI 相容端點的對話請求寫法；給 `backend_admin.chat_style_for`。"""

    #: 這個端點讀思考設定的欄位（`reasoning` 優先於 `reasoning_effort`，都由頂層設定決定），加上它沒有、送了也收不到的
    #: `think`、`options`
    _KEYS = ("think", "reasoning_effort", "reasoning", "options")

    def apply(self, body: dict[str, Any], *, think: bool, reasoning_effort: str | None,
              keep_alive: str | None, repeat_penalty: float | None, num_ctx: int | None) -> list[str]:
        for key in self._KEYS:
            body.pop(key, None)
        if not think:
            body["reasoning_effort"] = "none"
        elif reasoning_effort:
            body["reasoning_effort"] = reasoning_effort
        if keep_alive is not None:
            body["keep_alive"] = keep_alive
        return [name for name, value in (("repeat_penalty", repeat_penalty), ("num_ctx", num_ctx)) if value is not None]

    def dropped(self, extra_body: dict[str, Any]) -> list[str]:
        return [key for key in self._KEYS if key in extra_body]
