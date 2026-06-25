"""LLM 模組入口。

集中 re-export 常用函式，讓外部可以用 `from llm import ...`。
"""

from .tokenization import tokenize_for_retrieval
from .context_retriever import (
    retrieve_discord_context,
    retrieve_rag_context_sync,
    search_chat,
)
from .prompt_builder import build_askai_prompt_log
from .persona_card_builder import build_persona_cards, extract_mentioned_user_ids
from .retrievers.web import (
    IntentResult,
    WebResult,
    WebRetrievalOutcome,
    classify_route,
    clean_query,
    fetch_web_results,
    format_web_context_lines,
    should_search,
)

__all__ = [
    "tokenize_for_retrieval",
    "retrieve_discord_context",
    "retrieve_rag_context_sync",
    "search_chat",
    "build_askai_prompt_log",
    "build_persona_cards",
    "extract_mentioned_user_ids",
    "IntentResult",
    "WebResult",
    "WebRetrievalOutcome",
    "classify_route",
    "clean_query",
    "fetch_web_results",
    "format_web_context_lines",
    "should_search",
]
