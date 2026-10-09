"""Web search retriever：以 SearXNG 為後端，提供 /askai 即時資訊能力（關鍵字模式先查好塞進 prompt；工具模式 `WebSearchTools` 由模型決定）。"""

from .intent import IntentResult, classify_route, clean_query, should_search
from .search import search_web
from .tools import WebSearchTools
from .searxng import (
    WebResult,
    WebRetrievalOutcome,
    fetch_web_results,
    format_web_context_lines,
)

__all__ = [
    "IntentResult",
    "classify_route",
    "clean_query",
    "should_search",
    "WebResult",
    "WebRetrievalOutcome",
    "fetch_web_results",
    "format_web_context_lines",
    "search_web",
    "WebSearchTools",
]
