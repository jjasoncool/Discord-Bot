"""LLM 模組入口。

集中 re-export 常用函式，讓外部可以用 `from llm import ...`。
"""

from .tokenization import tokenize_for_retrieval
from .context_retriever import retrieve_discord_context, retrieve_rag_context, retrieve_rag_context_sync
from .prompt_builder import build_askai_prompt_log
from .persona_card_builder import build_persona_cards

__all__ = [
    "tokenize_for_retrieval",
    "retrieve_discord_context",
    "retrieve_rag_context",
    "retrieve_rag_context_sync",
    "build_askai_prompt_log",
    "build_persona_cards",
]
