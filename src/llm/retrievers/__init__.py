"""Retrievers：給 LLM 的 context 來源集中處。

目前有 context_retriever（Discord 聊天與成員檔案的 RAG）與 web（SearXNG）。
"""

from . import web

__all__ = ["web"]
