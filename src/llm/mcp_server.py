"""MCP server：把情報搜尋（`services.search`）包成兩個工具，給 LLM 客戶端呼叫。

兩種跑法：
  - 常駐（正式）：docker-compose 的 `search-mcp` 服務執行 `python -m llm.mcp_server --http`，聽 8765 port
    （主機那端只綁 127.0.0.1）；順便在背景跑每日維護（同步索引、補算向量，見 `services.search.nightly`）。
    客戶端是這台的 Claude Code，照 repo 根目錄的 `.mcp.json` 連 `http://127.0.0.1:8765/mcp`。不用 token：
    只有本機連得到
  - stdio：不帶參數執行，給除錯或沒有常駐服務時用（`docker exec -i search-mcp python -m llm.mcp_server`）

這一層只做協定（宣告工具、轉進呼叫、把結果包回去）；查詢、同步、讀全文都在 `services.search`。
之後 bot 要用搜尋是直接 import `services.search`，不當 MCP 客戶端。

**stdio 模式下 stdout 是協定通道**：不能 print，log 一律寫 `mcp_server.log`（見 `main`）。
"""
from __future__ import annotations

import argparse
import logging
from typing import Any, Literal, Optional

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings

from services.search import SOURCES, DocumentNotFound, IndexTooNew, SearchIndex, default_index
from sys_settings.search_settings import SEARCH_SETTINGS

logger = logging.getLogger(__name__)

#: 測試換成假資料庫的索引用；正式執行用 SEARCH_SETTINGS 建的共用索引
index_provider = default_index

#: 這些錯誤的訊息是寫給模型看的（例：可用的來源有哪些），要原文送回去讓它改參數重試；
#: 其他例外 SDK 只回「Error executing tool」，細節留在 log
_READABLE_ERRORS = (ValueError, DocumentNotFound, FileNotFoundError, IndexTooNew)

#: 來源代號由登記表產生：加來源只要在 services.search.sources 登記，工具定義跟著變
SourceKey = Literal[tuple(SOURCES)]  # type: ignore[valid-type]

_SOURCE_HELP = "、".join(f"{key}（{s.label}，{'官方' if s.official else '玩家說法'}）" for key, s in SOURCES.items())

server = MCPServer(
    name="wuwa-intel",
    instructions=(
        "鳴潮（Wuthering Waves）的情報搜尋：官網公告、官方 FB、PTT、巴哈姆特的全文。"
        "先用 search 找，再用 fetch 讀全文。回答時分開講官方說法與玩家說法，並附上連結。"
    ),
)


@server.tool(description=(
    "搜尋鳴潮的官網公告、官方 FB、PTT、巴哈文章。"
    "query 用空白分隔關鍵字，直接寫角色名、活動名、版本號（例：「3.2 前瞻 兌換碼」）；"
    "搜不到時換同義詞或拆短再搜。"
    f"sources 可選，不給就全部搜：{_SOURCE_HELP}。"
    "since、until 是 YYYY-MM-DD，起訖都含當天。"
    "question 可選：使用者原本問的整句話（例：「卜靈是什麼身分？」）；給了的話，最後排序會用它判斷哪篇真的在回答，"
    "比只看關鍵字準。換關鍵字重搜時也照樣帶同一句。"
    "每種來源各取前幾筆，每筆標明來源與是否官方；要看全文用 fetch 帶 id。"
))
def search(
    query: str,
    sources: Optional[list[SourceKey]] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
    limit: int = 10,
    question: Optional[str] = None,
) -> dict[str, Any]:
    index: SearchIndex = index_provider()
    try:
        hits = index.search(query, sources=sources, since=since, until=until, limit=limit, question=question)
    except _READABLE_ERRORS as exc:
        raise ToolError(str(exc)) from exc
    logger.info("search query=%r question=%r sources=%s since=%s until=%s → %d 筆",
                query, question, sources, since, until, len(hits))
    return {"results": [
        {
            "id": h.doc_id,
            "title": h.title,
            "url": h.url,
            "source": h.source,
            "source_label": h.source_label,
            "official": h.official,
            "published_at": h.published_at,
            "snippet": h.snippet,
        }
        for h in hits
    ]}


@server.tool(description=(
    "讀一份文件的全文（id 來自 search 的結果）。PTT 會附推文、巴哈會附留言。"
    "內容太長會分頁，page 從 1 開始，回傳裡有 total_pages。"
))
def fetch(id: str, page: int = 1) -> dict[str, Any]:  # noqa: A002 — 參數名照 MCP search/fetch 慣例
    try:
        doc = index_provider().fetch(id, page)
    except _READABLE_ERRORS as exc:
        raise ToolError(str(exc)) from exc
    logger.info("fetch id=%s page=%d/%d", id, doc.page, doc.total_pages)
    return {
        "id": doc.doc_id,
        "title": doc.title,
        "url": doc.url,
        "text": doc.text,
        "page": doc.page,
        "total_pages": doc.total_pages,
        "metadata": {
            "source": doc.source,
            "source_label": doc.source_label,
            "official": doc.official,
            "published_at": doc.published_at,
        },
    }


def http_options() -> dict[str, Any]:
    """常駐模式的 HTTP 設定（`main` 與測試共用）。

    - 容器裡聽 0.0.0.0；只綁本機是 docker-compose 的 `ports` 在做
    - Host 標頭白名單：MCP 套件預設只認 127.0.0.1，改聽 0.0.0.0 後要自己列（防 DNS rebinding：
      惡意網頁讓瀏覽器把自己的網域解析到 127.0.0.1 來打這個 port，Host 會是那個網域，被擋下）
    - stateless：每個請求各自獨立、不記 session。容器重開（例如改了程式）後客戶端不必重新連線
    """
    return {
        "host": SEARCH_SETTINGS.mcp_host,
        "stateless_http": True,
        "transport_security": TransportSecuritySettings(
            enable_dns_rebinding_protection=True, allowed_hosts=list(SEARCH_SETTINGS.mcp_allowed_hosts)),
    }


def main(argv: Optional[list[str]] = None) -> None:
    from utils.logger_config import configure_logging

    parser = argparse.ArgumentParser(description="情報搜尋的 MCP server")
    parser.add_argument("--http", action="store_true", help="常駐模式：走 HTTP，並在背景跑每日維護")
    args = parser.parse_args(argv)

    if not args.http:
        # stdio：stdout 是協定通道，log 只寫自己的檔
        configure_logging(force=True, root_handlers=["mcp_file"])
        logger.info("MCP server 啟動（stdio）")
        server.run("stdio")
        return

    from services.search import nightly

    # 自己一個容器：log 寫自己的檔，也輸出到畫面（docker logs search-mcp 看得到）
    configure_logging(force=True, root_handlers=["console", "mcp_file"])
    logger.info("MCP server 啟動（HTTP，port %d）", SEARCH_SETTINGS.mcp_port)
    nightly.start_in_background()
    server.run("streamable-http", port=SEARCH_SETTINGS.mcp_port, **http_options())


if __name__ == "__main__":
    main()
