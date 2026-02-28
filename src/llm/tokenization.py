"""Hybrid 檢索使用的文字正規化與分詞工具。"""

from __future__ import annotations

import re


def _normalize_retrieval_text(text: str) -> str:
    """做最小正規化，提升口語/中英混寫命中率。"""
    normalized = (text or "").lower().replace("　", " ")
    # 常見口語輸入：hen窮 / hen 帥
    normalized = re.sub(r"\bhen\b", "很", normalized)
    return " ".join(normalized.split())


def tokenize_for_retrieval(text: str) -> set[str]:
    """簡易分詞：中英數混合 + 中文 n-gram，供 BM25 使用。"""
    normalized = _normalize_retrieval_text(text)
    tokens: set[str] = set()

    # 英數 token
    tokens.update(re.findall(r"[a-z0-9_]{2,}", normalized))

    # 中文片段 token + bi/tri-gram
    zh_chunks = re.findall(r"[\u4e00-\u9fff]+", normalized)
    for chunk in zh_chunks:
        if len(chunk) >= 2:
            tokens.add(chunk)
        if len(chunk) >= 2:
            for i in range(len(chunk) - 1):
                tokens.add(chunk[i:i + 2])
        if len(chunk) >= 3:
            for i in range(len(chunk) - 2):
                tokens.add(chunk[i:i + 3])

    return {t for t in tokens if len(t) >= 2}


def tokens_for_debug(text: str) -> list[str]:
    """回傳排序後 token，供檢索除錯輸出使用。"""
    return sorted(tokenize_for_retrieval(text))
