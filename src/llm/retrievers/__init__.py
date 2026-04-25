"""Retrievers：給 LLM 的 context 來源集中處。

目前只含 web（SearXNG）；未來可加 stock / weather / news 等姊妹模組。
"""

from . import web

__all__ = ["web"]
