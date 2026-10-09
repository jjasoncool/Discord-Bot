"""遊戲情報（官網公告、官方 FB、PTT、巴哈）給模型用的工具：bot 當 MCP 客戶端連常駐的 search-mcp。"""

from .client import IntelSearchSession, prepare_intel_session, run_with_intel

__all__ = ["IntelSearchSession", "prepare_intel_session", "run_with_intel"]
