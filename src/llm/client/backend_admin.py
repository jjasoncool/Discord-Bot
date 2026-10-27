"""哪家後端掛哪個 admin，只在這裡決定；通用流程（`http_client`、服務層）不出現廠商名字。

架構定位：技術層（llm/client）。上層：建 `LlmHttpClient` 的地方（LLMService、SafeLLMEmbedding、HttpReranker、LlmProxy）。
  下層：各家的 admin 模組（`lemonade_admin`、`ollama_admin`）。

介面：
- `admin_for(backend, host, *, heal_load_timeout)`：回那家後端的 `BackendAdmin`；沒有專屬功能的後端（vLLM、不認得的名字）回 None，
  `LlmHttpClient` 就不拆信封、不重載，服務層也不載入、不卸載。

規則：
- 介面照能力定（拆信封、重載、確認載入、卸載），實作照廠商各一個 class、只實作它有的；兩家的呼叫方式一字不差就共用，不複製。
- 新後端有專屬功能：加一個 admin 模組、在這裡登記一行；沒有就什麼都不用加。
"""
from __future__ import annotations

from llm.client.http_client import BackendAdmin
from llm.client.lemonade_admin import LemonadeAdmin
from llm.client.ollama_admin import OllamaAdmin


def admin_for(backend: str | None, host: str, *, heal_load_timeout: float = 120.0) -> BackendAdmin | None:
    if backend == "lemonade":
        return LemonadeAdmin(host, heal_load_timeout=heal_load_timeout)
    if backend == "ollama":
        return OllamaAdmin(host)
    return None
