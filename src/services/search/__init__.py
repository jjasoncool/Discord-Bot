"""情報搜尋：官網公告、官方 FB、PTT、巴哈的關鍵字全文搜尋與讀全文。

對外只有兩件事（MCP 工具用這兩個；bot 的 /askai 透過 MCP 間接用）：
  - `SearchIndex.search(query, sources=, since=, until=, limit=)`：每種來源各取前幾筆，標明來源
  - `SearchIndex.fetch(doc_id, page=)`：讀全文（附 PTT 推文、巴哈留言），分頁

本套件**不 import discord 與 mcp**：它跑在獨立的 search-mcp 行程裡。bot 不用這裡的索引（discord-bot 沒掛索引目錄
`/search_data`），而是當 MCP 客戶端連 search-mcp（`llm.retrievers.intel`）；bot 只借 `rerank.HttpReranker`
（打模型的 reranker 客戶端）給 /askai 重排相關訊息，import 時不碰索引。
用語：文件＝可以直接給人一個連結的那一篇（`sources.py`）；評估數字記在 `AI_HANDOFF_AND_TODO.md` 的 `mcp-search-tools` 區塊。
"""
from services.search.index import (
    DocumentNotFound,
    IndexTooNew,
    FetchedDoc,
    SearchHit,
    SearchIndex,
    SyncReport,
    default_index,
)
from services.search.sources import SOURCES

__all__ = [
    "DocumentNotFound", "IndexTooNew", "FetchedDoc", "SearchHit", "SearchIndex", "SyncReport", "default_index", "SOURCES",
]
