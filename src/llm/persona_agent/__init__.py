"""Persona Extraction Agent：把每日人格萃取從固定 pipeline 升級成 tool-calling agent。

影子模式——與現有 `personality_extractor` 並行、寫獨立資料表，不動 production。
規劃與工程節點詳見 `AI_HANDOFF_AND_TODO.md` 的 Persona Extraction Agent 區塊。

模組分工：
  - `tools`  ：四支唯讀工具 + function-calling 宣告與派發
  - `schema` ：diff 輸出的 JSON schema
  - `agent`  ：agent loop（收集 → 產出）
  - `store`  ：兩張獨立資料表的讀寫（M3，尚未建立）

**刻意不在這裡 re-export**：所有呼叫端都走子模組（`from llm.persona_agent import agent,
tools`），re-export 一份只會是死程式碼，而且會讓「碰到套件」就 eager import `agent`
（連帶拉進 lemonade_gate、llm_settings）。要用什麼就 import 那個子模組。
"""
