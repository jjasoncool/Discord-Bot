"""與 LLM 上下文相關性的純函式工具。"""

from __future__ import annotations

import re


def tokenize_for_relevance(text: str) -> set[str]:
    """簡易分詞：中英數混合，供關聯度判斷使用。"""
    tokens = set(re.findall(r"[\u4e00-\u9fff]{1,}|[a-zA-Z0-9_]{2,}", text.lower()))
    return {t for t in tokens if len(t) >= 2}


def context_relevance_score(question: str, context_text: str) -> int:
    """以 token 交集數量做關聯分數，分數越高代表越相關。"""
    q_tokens = tokenize_for_relevance(question)
    c_tokens = tokenize_for_relevance(context_text)
    if not q_tokens or not c_tokens:
        return 0
    return len(q_tokens.intersection(c_tokens))


def is_context_relevant(question: str, context_text: str) -> bool:
    """回傳該訊息是否與問題有基本關聯。"""
    return context_relevance_score(question, context_text) > 0
