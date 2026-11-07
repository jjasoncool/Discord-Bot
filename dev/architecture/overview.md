# 專案 AI 架構總覽（Ollama 時代）

<!-- 給 AI：這份是歸檔檔，改之前先看完這段
結構：上半部（一頁看懂、時間線、定案與理由、踩過的坑）是整理過的重點；「## 原文」以下是當時的紀錄。
新增一段：
1. 原文放在「## 原文」目錄表下方的最前面，照現有各段的格式（## 標題、> 摘要與關鍵字、<details> 包正文，標籤前後各空一行）。
2. 目錄表加一列；dev/README.md 的「依日期」加一列。
3. 同一輪更新上半部，並把下面的「整理到」改成新段的日期。
不要改：原文正文、既有的段落標題（README 和其他檔用標題當錨點）。
找細節用搜尋，不必整份讀。改完跑 python3 dev/check.py。完整規則：AI_HANDOFF_AND_TODO.md「本檔維護規則」的「歸檔放哪」。
整理到：2026-10-02
-->

> 交接檔已經沒有這個主題的區塊；現況以 [交接檔](../../AI_HANDOFF_AND_TODO.md) 與程式為準。
> 這裡是歷史。上半部是整理過的重點；「原文」是當時的紀錄，提到的檔名、函式、狀態可能已經改了。原文提到的 `TODO-completed.md` 是 2026-11-07 以前的單一歸檔檔，內容都拆到 `dev/` 了，從 [dev/README.md](../README.md) 找。

## 一頁看懂

這個檔是 2026 年 3 月 Ollama 時代的 AI 架構總覽：各模組放在哪、當時已有的 AI 能力、模型設定，以及「先做產品閉環、不急著做 SFT」的判斷。內容已過時。

- **03-31**：記下模組位置與五類能力：/askai（排隊、system prompt 檔案化、圖片輸入）、多來源 RAG（最近訊息保底＋BM25＋向量、RRF 融合、分數門檻；成員自介與印象做成 persona 卡）、pgvector 持久化、安全（檢索內容一律視為不可信、印象入庫前審核）、可觀測性（prompt trace、debug log、回應歷史）。
- **04-15**：生成模型切到 `gemma4:31b`，timeout 從 180 秒調到 300 秒；兩個 system message 合併成一個。
- **產品判斷**：當時缺的不是 SFT，而是產品互動閉環：使用者回饋、好玩的機制、回覆品質 KPI 與 A/B 實驗。
- **10-02**：原文過時，整段歸檔；交接檔只留一個佔位區塊，因為其他區塊的 `depends_on` 指向它。SFT 決策門檻搬到「產品能力 TODO」。
- **11-07**：佔位區塊也搬出交接檔，交接檔不再追蹤這個主題。

**歸檔時（10-02）的狀態**

- [x] 3 月時的模組位置、AI 能力與模型設定整理
- [ ] 照 `AGENTS.md` 與 `src/` 現在的分層重寫架構總覽
- [ ] 產品互動閉環：使用者回饋、玩法機制、回覆品質 KPI 與 A/B（03-31 列為優先缺口）

最新狀況看交接檔。

## 時間線

| 日期 | 發生什麼 | 結果 |
|---|---|---|
| 03-31 | 寫下 AI 架構總覽 | 模組位置、五類能力、產品優先缺口、SFT 決策門檻、給外部 AI 的分析 prompt |
| 04-15 | 生成模型切到 `gemma4:31b` | timeout 180 → 300 秒；兩個 system message 合併成一個 |
| 10-02 | 原文過時，整段歸檔 | 交接檔留佔位區塊；SFT 決策門檻搬到「產品能力 TODO」 |
| 11-07 | 佔位區塊搬出交接檔 | 交接檔不再追蹤 |

## 定案與理由

| 決定 | 為什麼 |
|---|---|
| /askai 用排隊（`ASKAI_QUEUE`＋worker） | 避免高併發卡死 |
| 聊天訊息持久化進 pgvector 採 best effort | 不阻斷主流程 |
| intro 與 impression 採應用層 replace＋唯一索引 | 避免重複資料 |
| timeout 從 180 秒調到 300 秒（04-15） | 新的生成模型帶 context 時回應較慢 |
| 兩個 system message 合併成一個（04-15） | 避免部分模型只認最後一個 system message |
| 先不做 SFT，先做產品迭代＋資料閉環 | 要有足量高品質資料、清楚的評估集與 KPI、prompt／RAG／模型路由都優化過仍卡住，才值得投入 |
| 交接檔保留佔位區塊（10-02） | 其他區塊的 `depends_on` 指向 `project-architecture` |

## 踩過的坑

- **Ollama 不支援 GIF**：送 GIF 會回 `image: unknown format`，圖片只收 jpg、png、webp。
- **部分模型只認最後一個 system message**：兩段 system 要合併成一段。

## 原文

新的在前。每段標題下面是摘要，正文在「展開原文」裡。

| 日期 | 段落 | 摘要 |
|---|---|---|
| 2026-10-02 | [架構總覽佔位區塊（10-02）](#專案-ai-架構總覽佔位區塊原文為-ollama-時代歸檔-2026-11-07原至-2026-10-02) | 原文已過時另外歸檔，留佔位是因為其他區塊 depends_on 指向它；重寫以 AGENTS.md 與 src/ 為準。 |
| 2026-03-31 | [Ollama 時代架構總覽（03-31）](#專案-ai-架構總覽ollama-時代歸檔-2026-10-02原-2026-03-31) | 模組位置、已實作的五類 AI 能力、模型設定、產品優先缺口與 SFT 決策門檻。 |

## 專案 AI 架構總覽（佔位區塊，原文為 Ollama 時代）（歸檔 2026-11-07，原至 2026-10-02）

> 原文已過時另外歸檔，留佔位是因為其他區塊 depends_on 指向它；重寫以 AGENTS.md 與 src/ 為準。
>
> 關鍵字：架構總覽、Ollama、gemma4、ollama_runtime_config、depends_on、分層、SFT 決策門檻

<details>
<summary>展開原文（約 341 字）</summary>

> 從 `AI_HANDOFF_AND_TODO.md`「專案 AI 架構總覽（已過時，待重寫）」區塊（`project-architecture`）整塊搬來；交接檔已不再追蹤。

> 原內容停在 2026-03 的 Ollama 時代（gemma4、`ollama_runtime_config.json`），已歸檔到 `TODO-completed.md`「專案 AI 架構總覽（Ollama 時代）（歸檔 2026-10-02，原 2026-03-31）」。留著這個區塊是因為其他區塊的 `depends_on` 指向 `project-architecture`；重寫時以 `AGENTS.md` 與 `src/` 現在的分層為準。

SFT 決策門檻已搬到「產品能力 TODO」。

</details>

## 專案 AI 架構總覽（Ollama 時代）（歸檔 2026-10-02，原 2026-03-31）

> 模組位置、已實作的五類 AI 能力、模型設定、產品優先缺口與 SFT 決策門檻。
>
> 關鍵字：架構總覽、Ollama 時代、gemma4、給外部 AI 的分析 prompt

<details>
<summary>展開原文（約 3,092 字）</summary>

<!-- @meta
id: project-architecture
type: STATE
status: confirmed
last_confirmed: 2026-03-31
-->

- Bot 入口：`src/discord_bot.py`
- LLM 指令：`src/commands/llm_commands.py`（`/askai`）
- LLM 服務：`src/services/llm_service.py`（Ollama chat API 封裝）
- 檢索核心：`src/llm/retrievers/context_retriever.py`
- Persona 卡片：`src/llm/persona/persona_card_builder.py`
- Prompt 組裝：`src/llm/prompt/prompt_builder.py`；/askai 除錯 log 組裝：`src/llm/logger_factory.py`
- Profile/Impression 寫入 RAG：
  - 服務層：`src/services/community/intro_profile_service.py`
  - pgvector 介接層：`src/llm/storage/member_profile_store.py`（原 `intro_rag_port.py`，`b80c509` 改名）
- Impression 審核：`src/services/community/impression_moderation_service.py`
- 設定：
  - `src/sys_settings/llm_settings.py`
  - `src/sys_settings/pgvector_settings.py`
  - `src/sys_settings/ollama_runtime_config.json`

### 已實作 AI 能力

**A. 對話能力（/askai）：**
- 有排隊機制（`ASKAI_QUEUE` + worker），避免高併發卡死
- 支援 system prompt 檔案化（可維運調整）
- 支援圖片輸入（jpg/png/webp，轉 base64 丟給 Ollama）

**B. 多來源上下文（RAG）：**
- Discord 聊天上下文檢索：
  - 最近訊息保底（recent）
  - BM25（字面）+ 向量檢索（語意）
  - RRF 融合排序
  - 分數門檻過濾（`hybrid_min_fused_score`）
- 會員 Persona RAG（member_profile）：
  - 自我介紹（intro_profile）
  - 他人印象（impression）
  - SQL identity / participant / alias + vector 混合召回
  - 去重、加權、卡片化（persona cards）後再送給模型

**C. 向量資料庫與持久化：**
- 使用 pgvector（docker compose 有 `pgvector` service）
- 聊天訊息可自動持久化進 pgvector（best effort，不阻斷主流程）
- intro/impression 採「應用層 replace + 唯一索引」避免重複資料

**D. 安全與防護：**
- Context 一律視為不可信（untrusted context safety prompt）
- 防 prompt injection 的系統規則與邊界標記
- Impression 入庫前審核：
  - 規則 prefilter
  - moderation model 二次判定
  - 硬閘道（prompt injection / meme spam / fake story）

**E. 可觀測性（Observability）：**
- askai prompt trace log
- askai prompt debug log（含 retrieval debug）
- askai response history（jsonl）
- 有 context/retrieval 統計欄位（fetched/relevant/trimmed/sent）

### 模型設定

`src/sys_settings/ollama_runtime_config.json`：
- generation: `gemma4:31b`（2026-04-15 切換）
- embedding: `bge-m3:latest`
- moderation: `qwen2.5:7b`
- 特性：runtime 可熱更新
- timeout: 300 秒（2026-04-15 從 180 秒調高，因 gemma4:31b 帶 context 回應較慢）

**注意事項：**
- `gemma4:31b` 支援 `think: true/false`，API 傳遞方式與 CLI `--think` 一致
- 圖片支援 jpg/png/webp，**不支援 GIF**（Ollama 回傳 `image: unknown format`）
- 已合併兩個 system message 為一個（2026-04-15），避免部分模型只認最後一個 system message

### 產品優先缺口

目前不是「缺 SFT」，而是先缺產品互動閉環：
1. 使用者回饋信號蒐集（喜歡/不喜歡、是否有幫助）
2. 有趣玩法機制（事件、任務、成就、排行榜、角色互動）
3. 回覆品質 KPI 與 A/B 實驗機制

### 給外部 AI 的分析 Prompt（可直接貼）

你是一位資深 LLM 產品與 Discord 社群互動設計顧問。請根據以下專案現況提出「提高好玩度與留存」的具體方案，並以可落地的工程分期規劃輸出。

【專案現況】
1. Discord Bot 已有 /askai，採佇列化處理。
2. LLM 使用 Ollama，本體模型可 runtime 切換。
3. 檢索層已實作：Discord chat 的 BM25+Vector + RRF 融合。
4. 向量庫使用 pgvector，聊天與 member profile 有持久化。
5. member profile 包含 intro_profile 與 impression，並會生成 persona cards。
6. 有 context 安全規則，將檢索內容視為 untrusted context。
7. impression 入庫前有 moderation（規則 + LLM + 硬閘道）。
8. 有 prompt/debug/response log 可做觀測。

【目標】
- 讓 bot 更好玩、有記憶感、提高互動率與回訪率。

【請你輸出】
1. 先做 30 天產品路線圖（每週可驗收）。
2. 將功能切成 P0/P1/P2，並標示依賴關係。
3. 為每項功能定義 KPI（互動率、留存、滿意度、回覆品質）。
4. 提出資料標註策略，說明何時值得做 SFT/DPO。
5. 給出「不做 SFT 也能明顯提升」的 10 個快改項目。
6. 所有建議都要附最小可行實作（MVP）與風險。

### SFT 決策門檻

滿足以下條件再投入 SFT：
- 有足量高品質資料（非噪音對話）
- 有清楚評估集與 KPI（不是憑感覺）
- 已做過 prompt/RAG/模型路由優化仍卡住

否則先不做 SFT，先做產品迭代 + 資料閉環。

</details>
