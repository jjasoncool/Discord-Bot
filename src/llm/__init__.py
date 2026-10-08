"""LLM 技術：依角色分子資料夾（client、preprocess、prompt、retrievers、persona、ambient、storage）。

刻意**不在這裡集中轉出**：import 任何子模組（例：`llm.mcp_server`）都會先執行本檔，以前這裡轉出
聊天檢索，連帶載入 llama_index、discord 與 pgvector 設定（約 1.5 秒，還要 pgvector 帳密）。
MCP server 是獨立行程、只需要搜尋，不該被拖著載入這些。要用什麼就從子模組直接 import。
"""
