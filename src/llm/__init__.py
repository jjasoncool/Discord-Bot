"""LLM 模組入口。

集中 re-export 常用函式，讓外部可以用 `from llm import ...`。
"""

from .relevance import (
    context_relevance_score,
    is_context_relevant,
    tokenize_for_relevance,
)
from .context_retriever import retrieve_discord_context, retrieve_rag_context
from .prompt_builder import build_askai_prompt_log

__all__ = [
    "tokenize_for_relevance",
    "context_relevance_score",
    "is_context_relevant",
    "retrieve_discord_context",
    "retrieve_rag_context",
    "build_askai_prompt_log",
]
