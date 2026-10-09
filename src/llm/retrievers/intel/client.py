"""bot 端的情報搜尋客戶端：透過 MCP 連常駐的 search-mcp（`llm.mcp_server --http`），把它的 search／fetch
交給模型當工具用。

為什麼走 MCP、不直接 import `services.search`：搜尋索引只掛在 search-mcp 容器（discord-bot 沒掛 `search_data/`），
索引也只該有一個行程在寫；search-mcp 停掉時連線立刻失敗，/askai 照原本的方式回答（R12 之後的決定）。

  - **每次工具呼叫各開一條短連線**（列工具清單也是）：search-mcp 是 stateless HTTP，多一次握手只要幾毫秒。
    長連線的話，搜尋到一半服務重啟，MCP 套件背景 task 裡的連線錯誤會變成「取消」整個 /askai（接不到、
    排隊的工作者跟著結束；2026-10-09 最後審查實測）；短連線在關閉時會把它轉成一般的錯誤，回給模型就好。
    連線都在呼叫端的 task 裡開關，/askai 按取消時進行中的搜尋一起中斷
  - 工具定義每次請求從伺服器讀（search-mcp 可以單獨重啟，改了工具說明下一次就生效），不在啟動時快取
  - 怎麼用這組工具的規則（`settings/prompts/askai_intel_rules.txt`）只在真的有工具時才給模型：開關關著或連不上時，
    提示詞跟原本完全一樣，模型不會被要求「先查」卻沒有工具
  - 結果整理成精簡的 JSON 給模型：只留回答用得到的欄位；全文截斷（論壇留言很長，也是任何人都能寫的內容）
  - 模型呼叫 search 漏帶原句時自動補上使用者的原句：搜尋端的重新排序要讀自然語言的問句才準
  - 任何失敗（參數錯、工具不存在、逾時、搜尋端錯誤）都轉成 `{"error": ...}` 回給模型，不讓整個回答中斷
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Awaitable, Callable, Optional, Sequence, TypeVar

from mcp.client.client import Client

from llm.client.tool_calls import ToolArgumentError, ToolRunner, combine_runners, parse_arguments
from llm.prompt import prompt_files
from sys_settings.llm_settings import AskAIIntelSettings

logger = logging.getLogger(__name__)

T = TypeVar("T")

#: search 每筆結果給模型的欄位（id 給 fetch 用；official 讓它分開講官方與玩家說法；url 給它附連結）
_SEARCH_FIELDS = ("id", "title", "url", "source_label", "official", "published_at", "snippet")


class IntelSearchSession:
    """一次 /askai 請求的情報工具：宣告給模型的工具清單，以及執行模型要的工具呼叫。"""

    def __init__(self, target: Any, tools: list[Any], *, question: str, settings: AskAIIntelSettings,
                 instructions: str = ""):
        self._target = target
        self._tools = {tool.name: tool for tool in tools}
        self.question = question
        self.settings = settings
        #: 怎麼用這組工具（接在系統提示詞後面，見 `LLMService.generate_reply`）
        self.instructions = instructions
        #: 這次請求呼叫過的工具與結果摘要（寫進 /askai 的回應紀錄）
        self.calls: list[dict[str, Any]] = []

    @property
    def tools(self) -> list[dict[str, Any]]:
        """OpenAI 格式的工具宣告（`chat_with_tools` 的 tools），名稱與說明都照 search-mcp 給的。"""
        return [
            {"type": "function",
             "function": {"name": tool.name, "description": tool.description or "", "parameters": tool.input_schema}}
            for tool in self._tools.values()
        ]

    async def execute(self, name: str, arguments: Any) -> str:
        """執行一個工具呼叫，回傳給模型的 JSON 字串；失敗也回 `{"error": ...}`，不往外丟。"""
        started = time.perf_counter()
        record: dict[str, Any] = {"tool": name, "arguments": str(arguments)[:300]}
        try:
            payload = await self._execute(name, arguments, record)
        except Exception as exc:
            logger.warning("情報搜尋工具失敗 tool=%s：%s: %s", name, type(exc).__name__, exc)
            payload = {"error": f"這次查不到（{type(exc).__name__}），請就手上的資料回答"}
        record["elapsed_ms"] = int((time.perf_counter() - started) * 1000)
        if "error" in payload:
            record["error"] = str(payload["error"])[:200]
        self.calls.append(record)
        return json.dumps(payload, ensure_ascii=False)

    async def _execute(self, name: str, arguments: Any, record: dict[str, Any]) -> dict[str, Any]:
        if name not in self._tools:
            return {"error": f"沒有名為 {name} 的工具；可用的是：{', '.join(self._tools)}"}
        try:
            args = parse_arguments(arguments)
        except ToolArgumentError as exc:
            return {"error": str(exc)}
        if name == "search":
            args["limit"] = self._search_limit(args.get("limit"))
            if self.question and not str(args.get("question") or "").strip():
                args["question"] = self.question
        async with _connect(self._target, self.settings) as client:
            result = await client.call_tool(name, args, read_timeout_seconds=self.settings.call_timeout_seconds)
        if result.is_error:
            text = "".join(getattr(part, "text", "") for part in result.content or [])
            return {"error": text or "工具執行失敗"}
        data = result.structured_content or {}
        if name == "search":
            results = [{key: hit[key] for key in _SEARCH_FIELDS if hit.get(key) not in (None, "")}
                       for hit in data.get("results") or []]
            record["result_ids"] = [hit.get("id") for hit in results]
            return {"results": results}
        if name == "fetch":
            record["result_ids"] = [data.get("id")]
            return self._compact_document(data)
        return data

    def _search_limit(self, requested: Any) -> int:
        try:
            wanted = int(requested)
        except (TypeError, ValueError):
            return self.settings.search_limit
        return max(1, min(wanted, self.settings.search_limit))

    def _compact_document(self, data: dict[str, Any]) -> dict[str, Any]:
        meta = data.get("metadata") or {}
        text = data.get("text") or ""
        limit = self.settings.fetch_max_chars
        if len(text) > limit:
            # 正常不會發生：search-mcp 每頁字數（SEARCH_SETTINGS.fetch_page_chars）不超過這個上限，被截掉的
            # 內容一定能翻頁讀到（守衛測試看著）。真的發生時照實講這一頁後段沒附上，別讓模型以為翻頁就接得上
            text = text[:limit] + f"…（這一頁後段約 {len(text) - limit} 字沒有附上）"
        doc = {
            "id": data.get("id"), "title": data.get("title"), "url": data.get("url"),
            "source_label": meta.get("source_label"), "official": meta.get("official"),
            "published_at": meta.get("published_at"), "page": data.get("page"),
            "total_pages": data.get("total_pages"), "text": text,
        }
        return {key: value for key, value in doc.items() if value not in (None, "")}


def _connect(target: Any, settings: AskAIIntelSettings) -> Client:
    """一條短連線（`async with` 用）。`target` 是網址，單元測試換成同一個行程裡的 `MCPServer`。"""
    return Client(target, read_timeout_seconds=settings.call_timeout_seconds)


async def prepare_intel_session(*, question: str, settings: Optional[AskAIIntelSettings] = None,
                                server: Any = None) -> Optional[IntelSearchSession]:
    """讀 search-mcp 的工具清單、準備這次請求的工具。連不上（服務沒開、網路斷）回 None：呼叫端照原本的方式回答。

    `server` 給單元測試用（同一個行程裡的 `MCPServer`）；正式環境連設定裡的網址。"""
    settings = settings or AskAIIntelSettings()
    target = server if server is not None else settings.mcp_url
    try:
        async with _connect(target, settings) as client:
            listed = await client.list_tools()
    except Exception as exc:
        logger.warning("連不上情報搜尋服務（%s），這次不查：%s: %s", settings.mcp_url, type(exc).__name__, exc)
        return None
    instructions = prompt_files.read_text(settings.rules_path, label="情報查詢規則")
    return IntelSearchSession(target, list(listed.tools), question=question, settings=settings,
                              instructions=instructions)


async def run_with_intel(generate: Callable[[Optional[ToolRunner]], Awaitable[T]], *, question: str,
                         enabled: bool, meta: dict[str, Any], settings: Optional[AskAIIntelSettings] = None,
                         server: Any = None, also: Sequence[Optional[ToolRunner]] = ()) -> T:
    """開關開著就準備情報工具、交給 `generate`；關著或連不上就不給情報工具（照原本的方式回答）。

    `also`：其他一起交給模型的工具（/askai 的網路搜尋），和情報工具合成一組（`combine_runners`），模型在同一個
    工具輪裡挑要查哪邊；情報關著或連不上時就只給它們，都沒有時 `generate(None)`。
    查情報的經過寫進 `meta`（`connected`：有沒有連上；`calls`：呼叫了哪些情報工具），給 /askai 的回應紀錄用。
    每次工具呼叫的短連線都在呼叫端的 task 裡開關：/askai 把整段包成一個 task，按取消時搜尋一起中斷。"""
    if not enabled:
        return await generate(combine_runners(*also))
    session = await prepare_intel_session(question=question, settings=settings, server=server)
    meta["connected"] = session is not None
    try:
        return await generate(combine_runners(session, *also))
    finally:
        if session is not None:
            meta["calls"] = session.calls
