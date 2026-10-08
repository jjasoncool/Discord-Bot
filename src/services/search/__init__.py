"""情報搜尋：官網公告、官方 FB、PTT、巴哈的關鍵字全文搜尋與讀全文。

對外只有兩件事（MCP 工具與之後 bot 的工具呼叫都用這兩個）：
  - `SearchIndex.search(query, sources=, since=, until=, limit=)`：每種來源各取前幾筆，標明來源
  - `SearchIndex.fetch(doc_id, page=)`：讀全文（附 PTT 推文、巴哈留言），分頁

本套件**不 import discord 與 mcp**：它跑在獨立的 MCP 行程裡，之後 bot 也會直接 import 它。
用語（文件、來源、段落）與評估數字見 `AI_HANDOFF_AND_TODO.md` 的 `mcp-search-tools` 區塊。
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
