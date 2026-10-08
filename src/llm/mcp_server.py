"""MCP server：把情報搜尋（`services.search`）包成兩個工具，給 LLM 客戶端呼叫。

目前的客戶端只有這台的 Claude Code：它照 repo 根目錄的 `.mcp.json` 執行
`docker exec -i discord-bot python -m llm.mcp_server`，走 stdio。不開 port、不用 token。

這一層只做協定（宣告工具、轉進呼叫、把結果包回去）；查詢、同步、讀全文都在 `services.search`。
之後 bot 要用搜尋是直接 import `services.search`，不當 MCP 客戶端。

**stdout 是協定通道**：這個行程不能 print，log 一律寫 `mcp_server.log`（見 `main`）。
"""
from __future__ import annotations

import logging
from typing import Any, Literal, Optional

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from services.search import SOURCES, DocumentNotFound, IndexTooNew, SearchIndex, default_index

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


def main() -> None:
    from utils.logger_config import configure_logging

    # 跟 bot 同一個容器：root 改寫自己的檔，不碰 bot 的輪替 log；也不輸出到 stdout
    configure_logging(force=True, root_handlers=["mcp_file"])
    logger.info("MCP server 啟動（stdio）")
    server.run("stdio")


if __name__ == "__main__":
    main()
