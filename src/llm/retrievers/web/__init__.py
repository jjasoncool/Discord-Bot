"""Web search retriever：以 SearXNG 為後端，提供 /askai 即時資訊能力。"""

from .intent import IntentResult, classify_route, clean_query, should_search
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
]
