"""情報搜尋的評估：程式、考卷、報告放在一起。

  - `evaluate.py`：考搜尋本身（search-mcp 容器裡 `python -m services.search.eval.evaluate`）
  - `agent_eval.py`：正式模型跑完 /askai 工具輪之後的算分（跑題目的是 `test/integration/it_askai_agent_eval.py`）
  - `questions.json`、`keyword_queries.json`：考卷與外部 agent 改寫的查詢字
  - `reports/`：每次評估的報告（進 git）；`private/`：證據句、回答全文等論壇原文（不進 git）

bot 與 search-mcp 執行時都不會 import 這個資料夾，只有手動評估與測試會用到。
"""
