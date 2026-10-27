"""Ollama 後端專屬的事：卸載（keep_alive=0）。Ollama 沒有載入與重載 API，上下文長度走每次請求的 options。

架構定位：技術層（llm/client），只依賴 httpx、標準庫與同層的 http_client（例外分類）。
  上層：`backend_admin.admin_for`（建 `LlmHttpClient` 時掛上）。下層：Ollama 的 /api/generate。

介面：
- `OllamaAdmin(host)`：`unwrap` 原樣回（Ollama 的錯誤走 HTTP 狀態碼，沒有信封）、`heal` 回 False（沒有重載 API，要救只能在主機端重啟）、
  `ensure_loaded` 不做（沒有載入 API）、`unload(model=)`：送一個空的 /api/generate 帶 keep_alive=0，把模型從 VRAM 帶下去。

規則：
- 卸載走原生 /api/generate、不走對話端點：呼叫端拿著 GPU 閘門時不能再走會回頭要閘門的對話路徑。

例外與決策：
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

    def heal(self, model: str, reason: str = "") -> bool:
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
