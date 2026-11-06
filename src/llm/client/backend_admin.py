"""哪家後端掛哪個 admin、對話請求的思考設定怎麼寫、出錯時看哪些端點，只在這裡決定；通用流程（`http_client`、服務層）不出現廠商名字。

架構定位：技術層（llm/client）。上層：建 `LlmHttpClient` 的地方（LLMService、SafeLLMEmbedding、HttpReranker、LlmProxy）；
  組對話請求、抓狀態快照的 `LLMService`。下層：各家的 admin 模組（`lemonade_admin`、`ollama_admin`）。

介面：
- `admin_for(backend, host, *, heal_load_timeout)`：回那家後端的 `BackendAdmin`；沒有專屬功能的後端（vLLM、不認得的名字）回 None，
  `LlmHttpClient` 就不拆信封、不重載，服務層也不載入、不卸載。
- `chat_style_for(backend)`：回那家的 `ChatStyle`，把思考開關、強度與每次請求的閒置卸載、上下文長度、重複懲罰翻成那家認得的欄位。
- `snapshot_probes(backend)`：對話失敗時抓狀態快照要打的唯讀端點 (log 裡的標籤, 路徑)；沒登記的後端回空。

規則：
- 介面照能力定（拆信封、重載、確認載入、卸載），實作照廠商各一個 class、只實作它有的；兩家的呼叫方式一字不差就共用，不複製。
- 新後端有專屬功能：加一個 admin 模組、在這裡登記一行；沒有就什麼都不用加。
- 思考開關與強度只在設定檔頂層設（`think`、`reasoning_effort`）。寫法照「誰讀這個欄位」分、不照廠商分：`enable_thinking`、
  `reasoning_effort` 是模型模板的變數，Lemonade 與 vLLM 都把 `chat_template_kwargs` 原樣交給模板，共用 `TemplateStyle`；
  Ollama 的 OpenAI 相容端點沒有模板參數，寫法在 `ollama_admin.OllamaChatStyle`。設定檔 extra_body 裡的思考設定與那家收不到的欄位
  由寫法拿掉，呼叫端照 `dropped` 記警告。
- 後端名字、`isinstance(…, LemonadeAdmin)` 這類判斷只寫在這裡與各家的 admin 模組（`test_shared_conventions` 守衛擋）。

例外與決策：
- 寫法不掛在 admin 上：vLLM 沒有 admin，None 代表「沒有管理 API」（不拆信封、不載入、不卸載）；為了寫法給它一個 admin，
  卸載會回報成功卻沒卸，產圖以為顯示卡空了。
- 不認得的後端（含讀不到設定檔）用模板變數的寫法：llama.cpp、vLLM 都認得，其他伺服器多半略過不認得的欄位。
"""
from __future__ import annotations

from typing import Any, Protocol

from llm.client.http_client import BackendAdmin
from llm.client.lemonade_admin import LemonadeAdmin
from llm.client.ollama_admin import OllamaAdmin, OllamaChatStyle


def admin_for(backend: str | None, host: str, *, heal_load_timeout: float = 120.0) -> BackendAdmin | None:
    if backend == "lemonade":
        return LemonadeAdmin(host, heal_load_timeout=heal_load_timeout)
    if backend == "ollama":
        return OllamaAdmin(host)
    return None


class ChatStyle(Protocol):
    """一種對話請求的寫法。"""

    def apply(self, body: dict[str, Any], *, think: bool, reasoning_effort: str | None,
              keep_alive: str | None, repeat_penalty: float | None, num_ctx: int | None) -> list[str]:
        """把設定寫進 body（呼叫端給的是複本，可以直接改）；回這種寫法收不到、沒寫進去的參數名稱。"""
        ...

    def dropped(self, extra_body: dict[str, Any]) -> list[str]:
        """設定檔 extra_body 裡 `apply` 會拿掉的欄位：思考設定（改由頂層決定）與這家收不到的欄位。"""
        ...


class TemplateStyle:
    """模型模板變數：思考開關與強度放進 `chat_template_kwargs`，伺服器原樣交給模板。"""

    _KEYS = ("enable_thinking", "reasoning_effort")

    def apply(self, body: dict[str, Any], *, think: bool, reasoning_effort: str | None,
              keep_alive: str | None, repeat_penalty: float | None, num_ctx: int | None) -> list[str]:
        kwargs = {key: value for key, value in (body.get("chat_template_kwargs") or {}).items() if key not in self._KEYS}
        kwargs["enable_thinking"] = bool(think)
        if reasoning_effort:
            kwargs["reasoning_effort"] = reasoning_effort
        body["chat_template_kwargs"] = kwargs
        # 閒置卸載由 release_model 明確做；上下文長度在載入模型時定（admin 的 model_load_options）
        return [name for name, value in (("keep_alive", keep_alive), ("repeat_penalty", repeat_penalty),
                                         ("num_ctx", num_ctx)) if value is not None]

    def dropped(self, extra_body: dict[str, Any]) -> list[str]:
        kwargs = extra_body.get("chat_template_kwargs") or {}
        return [f"chat_template_kwargs.{key}" for key in self._KEYS if key in kwargs]


_TEMPLATE_STYLE = TemplateStyle()
#: 寫法跟模板變數不同的後端；其餘（Lemonade、vLLM、不認得的）都用模板變數
_CHAT_STYLES: dict[str, ChatStyle] = {"ollama": OllamaChatStyle()}


def chat_style_for(backend: str | None) -> ChatStyle:
    return _CHAT_STYLES.get(backend or "", _TEMPLATE_STYLE)


#: 某個端點不存在由 `admin_get` 收成 dict，不影響其他端點
_SNAPSHOT_PROBES: dict[str, tuple[tuple[str, str], ...]] = {
    # health 看當下載了哪些模型、system-info 看後端 recipe
    "lemonade": (("health", "/api/v1/health"), ("system_info", "/api/v1/system-info")),
    # /api/ps 看已載的模型、各自的 VRAM 與 TTL 倒數；/api/tags 補註冊表
    "ollama": (("ps", "/api/ps"), ("tags", "/api/tags")),
    # 一個行程一個模型、沒有 swap，只能看活著沒、服務哪個模型
    "vllm": (("health", "/health"), ("models", "/v1/models")),
}


def snapshot_probes(backend: str | None) -> tuple[tuple[str, str], ...]:
    return _SNAPSHOT_PROBES.get(backend or "", ())
