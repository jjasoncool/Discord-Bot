# AI Handoff & TODO

> 【AI 維護義務】凡讀取本檔的 AI，在本輪結束前必須：
> 1. **僅在本輪有實作異動、共識變更、或使用者明確要求時**，更新已變動區塊的 `@meta` status 與 last_confirmed
> 2. 若有新共識，就地更新對應主題區塊（不另開新編號）
> 3. 若某區塊已過期，將 status 改為 deprecated
> 4. 每項事實只存在一個地方 — 不需要同步多處
> 5. **若本輪僅閱讀、未實作、且使用者未要求回寫，可不強制留下盤點紀錄**

> 【AI 可建立的結構化索引】
> 本檔每個主題區塊都帶有 `@meta` HTML 註解標頭，包含：
> - `id`: 唯一識別碼，可用於跨區塊引用
> - `type`: STATE / CONTRACT / DECISION / RISK / TODO
> - `status`: confirmed / draft / deprecated / blocked
> - `depends_on` / `affects`: 區塊間的依賴與影響關係
> - `last_confirmed`: 最後確認日期
>
> AI 讀取本檔時，可利用這些 metadata 建立高維度索引，
> **優先只讀取與當前任務直接相關的區塊**，快速判斷區塊間的關聯、依賴、時效性，而不需逐字重讀全文。

> 【主題切換 / 歸檔規則】若後續主線從 A 議題切到 B 議題，舊主線內容**不應直接刪除**，而應：
> 1. 先將原主線區塊的 `status` 改成 `deprecated` 或 `confirmed`（視是否仍有效）
> 2. 若已不屬於當前主線，移入 `TODO-completed.md` 作為 archive / completed 記錄
> 3. 在現況摘要 / 管理級總覽中移除其「當前主線」身份
> 4. 保留可追溯來源，避免之後重複討論同一件事

最後盤點紀錄：
- 2026-04-03：清理 handoff，已完成的設計文件和歷史盤點移至 `TODO-completed.md`。
- 2026-04-05：續文/多圖/並行/子看板等完成，已歸檔至 `TODO-completed.md`。
- 2026-04-06：Telegram embed title 來源頻道名稱修正，已歸檔至 `TODO-completed.md`。
- 2026-04-07：Telegram media group 合併（grouped_id + 多圖合併為單則 Discord 訊息），已歸檔至 `TODO-completed.md`。

---

## 協作流程契約（強制，優先於全文其他段落）

<!-- @meta
id: collaboration-rules
type: CONTRACT
status: confirmed
last_confirmed: 2026-03-31
-->

### 使用者指定的討論流程

1. 每次討論先給**完整架構**，不能只回片段。
2. 清楚標示「本輪改了哪些共識」。
3. 最後做「整體確認」：已定案 / 未定案 / 下一步。
4. 盡量避免反覆單題選單式問答，改用完整方案溝通。

### 文件閉環規範

每一輪原則上遵循：`讀取需要區塊 -> 沿用共識 -> 討論/執行 -> 必要時回寫 -> 下輪再讀`

補充：
- 不要求每輪都全文重讀。
- 應優先讀取與當前任務直接相關的區塊；只有在需要交叉確認依賴、主線變更、或資訊不足時，才擴大閱讀範圍。
- 只有在本輪有實作異動、共識更新、TODO 狀態變更、或使用者明確要求時，才需要回寫本檔。

### TODO 更新規則

1. 完成項目要打勾。
2. 完成且無未完成關聯時，應自待辦移除。
3. 若仍有依賴未完成項目，保留並註記依賴。
4. 僅在本輪有實作異動、共識更新、TODO 狀態變更、或使用者明確要求時，才需要回寫本檔進度。
5. 若主線已切換，必須同步更新：
   - 現況摘要
   - 管理級總覽
   - 原主線區塊 status
   - 必要時將舊主線移入 `TODO-completed.md`

### 禁止未經確認刪除/覆寫使用者資料檔（高嚴重性）

1. **禁止**在未取得使用者明確同意前，執行任何可能刪除、清空、覆寫資料檔的操作。
2. 針對以下類型檔案，一律視為「高風險資料」：
   - runtime 狀態檔（例如：`src/services/sent_articles.json`）
   - 使用者設定檔、快取、歷史紀錄、session、資料庫檔
3. 如需修改高風險資料檔，必須先說明風險與影響、提供備份/回復方案、取得使用者同意。
4. 若發生誤刪/誤覆寫，需立即升級為高嚴重性事故（凍結 -> 復原 -> 紀錄防再發）。

### 注意事項

- AI 禁止執行會變更環境狀態的 Docker 指令（`docker compose up/down/build/restart`、`docker rm`、`docker rmi` 等）。
- 允許 AI 執行唯讀/除錯類 Docker 指令（`docker ps`、`docker logs`、`docker exec` 查詢、`docker inspect`）。
- 若需要變更環境，AI 只能提供建議指令，由使用者自行在終端執行。
- 碼風慣例：4 空白縮排、繁體中文註解。
- 非同步開發：`asyncio` / `Telethon` / `asyncpg`。

---

## 現況摘要

> 本區只放指標與錨點。詳細內容請跳到對應區塊。
> 若某主題不再是當前主線，應從此區移除或降級，不應永久停留在現況摘要。

| 主軸 | 狀態 | 進度 | 詳見 |
|---|---|---:|---|
| Discord Bot / AI 對話能力 | 已有可用基礎能力 | 70% | [專案架構](#專案-ai-架構總覽) |
| 跨來源整合（Article/FB/PTT/TG） | 有方向，尚未全面收斂 | 35% | [跨來源整合](#跨來源整合專區) |
| Bahamut RAG / AI 整合 | 尚未開始 | 5% | [RAG TODO](#第三階段整合-ai--pgvector--rag) |
| Discord Bot 管理入口 | 規劃中 | 10% | [管理 TODO](#discord-bot-管理入口與指令整理-todo) |

---

## 專案 AI 架構總覽

<!-- @meta
id: project-architecture
type: STATE
status: confirmed
last_confirmed: 2026-03-31
-->

- Bot 入口：`src/discord_bot.py`
- LLM 指令：`src/commands/llm_commands.py`（`/askai`）
- LLM 服務：`src/services/llm_service.py`（Ollama chat API 封裝）
- 檢索核心：`src/llm/context_retriever.py`
- Persona 卡片：`src/llm/persona_card_builder.py`
- Prompt 與 log 組裝：`src/llm/prompt_builder.py`
- Profile/Impression 寫入 RAG：
  - 服務層：`src/services/intro_profile_service.py`
  - pgvector 介接層：`src/llm/intro_rag_port.py`
- Impression 審核：`src/services/impression_moderation_service.py`
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
- generation: `ministral-3:14b`
- embedding: `bge-m3:latest`
- moderation: `qwen2.5:7b`
- 特性：runtime 可熱更新

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

---

## Bahamut 專區

> 本專區已改為雙層：
> 1. **正式知識層（AI-first）**：給下一個 AI 直接接手與維護
> 2. **歷史附錄層（raw history）**：保留完整脈絡，不作為第一閱讀入口

### Bahamut 正式知識層（AI-first）

> 這一層是後續 AI 應優先維護的主體。
> 原則：
> - 新結論優先更新在這裡
> - 舊細節保留在後面的歷史附錄
> - 若正式知識層與歷史附錄衝突，以正式知識層為準，再回頭修正附錄註記

#### BAHAMUT.RISK

<!-- @meta
id: bahamut-risk-formal
type: RISK
status: confirmed
last_confirmed: 2026-04-03
-->

**目前風險**
1. `snB == sn` 高度吻合但未 100% 證明
2. HTML 結構若再變，`section.c-section` / `Commendlist_*` selector 可能失效

#### BAHAMUT.NEXT

<!-- @meta
id: bahamut-next-formal
type: TODO
status: confirmed
last_confirmed: 2026-04-03
-->

**下一步（依優先序）**
1. 端到端測試：重啟兩容器 → 確認續文 + 多圖 + 自動閉環
2. 正式 DB migration（Alembic）
3. 跨來源整合（base_monitor 共用層擴展）
4. RAG ingestion

### 已歸檔設計文件（移至 TODO-completed.md）

> 以下設計文件已落地且歸檔：方法與 JSON 契約、ID 語意、文章結構判斷、留言抓取契約、留言 parser 規則、sn 抓取策略、版本路由策略、抓取模式與套件、開發原則、DB Schema 設計、Discord 呈現策略、作者查詢能力。
> 詳見 `TODO-completed.md`。

<!--  以下區塊已移至 TODO-completed.md，此處僅保留錨點供跨區塊引用 -->

### Bahamut TODO

<!-- @meta
id: bahamut-todo
type: TODO
status: confirmed
last_confirmed: 2026-04-05
-->

**當前待辦：**
1. 端到端測試：重啟兩容器 → 確認續文 + 多圖 + subbsn + 自動閉環
2. 正式 DB migration（Alembic）
3. RAG ingestion（不急）

#### 第三階段：整合 AI / pgvector / RAG

> **前置已完成：** Bahamut 全流程（scraper → DB → API → Discord）已 100% 完成並持續運行中。
> 詳見 `TODO-completed.md`（Bahamut Scraper MVP、增量更新、續文/多圖/並行/子看板等）。

**目標：** Discord bot 可用巴哈資料做語意搜尋、摘要、審查輔助；讓結構化查詢與向量檢索並存

**交付成果：**
- Bahamut RAG ingestion pipeline
- pgvector embeddings 與 metadata 設計
- Discord bot 查人 / 查文 / 摘要 / 審查指令雛型
- SQL + Vector 雙軌查詢流程

**完成標準：**
- Discord bot 可回答巴哈相關問題
- 可對特定使用者或主題進行 RAG 搜尋與摘要
- 可結合 moderation 資料做文章審查輔助
- 可與既有 `discord_chat` / `member_profile` retrieval 共存

- [ ] 在 `retrieval_sources` 新增 `bahamut_forum` 資料來源設定
- [ ] 設計 chunk 策略：主文/留言/回文/回文留言
- [ ] 設計 pgvector metadata：`doc_type`, `post_id`, `comment_id`, `reply_id`, `user_id`, `category`, `published_at`, `moderation_status`
- [ ] 建立 embedding / ingestion pipeline
- [ ] 設計 SQL filter + Vector retrieval 混合查詢
- [ ] 設計 Discord bot 指令：查主題、查文章、查使用者、查高風險留言
- [ ] 建立摘要 prompt：單篇摘要、討論風向摘要、使用者發言摘要
- [ ] 建立觀測指標：索引筆數、查詢延遲、命中率、審查覆蓋率
- [ ] 驗證 Discord 問答是否可同時引用 Discord 聊天資料與巴哈論壇資料

**建議執行順序：**
- 第三階段前先補端到端測試與 migration
- [ ] 第二階段穩定後再做第三階段 RAG
- [ ] 每階段保留 JSON 範例與測試案例

---

---

## 跨來源整合專區

<!-- @meta
id: cross-source-integration
type: STATE
status: confirmed
depends_on: []
affects: [project-architecture]
last_confirmed: 2026-03-31
-->

> Telegram Relay 已完成（歸檔至 `TODO-completed.md`）。

### 整合方案（按部就班）

**優先整合順序（2026-03-25 共識）：**
1. 先整合讀資料（fetch/orchestrator）
2. 再整合 render/route
3. Publisher 放後面
- 理由：Article/FB/PTT 在取文與去重流程有高度相似性，先抽讀資料風險較低；發文端差異（TextChannel / ForumThread / 留言增量 / 圖片策略）較大，適合後置整合

**Step 1 — 整合讀資料流程：**
- 新增 `SourceFetchPort` + 來源實作：`ArticleFetchAdapter`、`FbFetchAdapter`、`PttFetchAdapter`、`TelegramFetchAdapter`
- 新增 `SourceFetchOrchestrator`（strategy/case 分派）
- 保留各來源原本去重邏輯不動

**Step 2 — 統一事件模型：**
- 定義 `MessageRenderAdapter`（標準輸入模型）+ 各來源實作
- Adapter 採**無損封裝**：
  - `normalized_payload`：共用欄位（給 Publisher）
  - `source_payload_raw`：完整原始資料
  - `source_meta`：來源型別、版本、追蹤 key
- 原則：
  1. Publisher 只依賴 `normalized_payload`，不碰來源細節
  2. 任何來源特有欄位不得丟棄，必須保留在 `source_payload_raw`
  3. 若某來源需要特殊顯示（例如 PTT 留言串、Forum tag、Telegram spoiler），由對應 Adapter 在轉換階段映射到 `normalized_payload` 的擴充欄位，或由來源專屬 post-processor 處理，避免硬塞到 Publisher

**Step 3 — 導入 Route Resolver：**
- `MessageRouteResolver`，route 規則從流程碼中抽離
- Telegram 先接 `telegram_channel_routes`，其他來源逐步納入

**Step 4 — 整合 Publisher：**
- 新增/補強 `DiscordMessagePublisher`（文字、附件分批、重試、錯誤紀錄）
- 保留 `send_article_to_channel/send_fb_post_to_channel/send_ptt_post_to_forum_channel` 外觀，內部逐步改呼叫 publisher
- 先做 capability 共用，不做來源語意硬整併

**Step 5 — 收斂 Worker：**
- 視穩定度決定是否導入 `MessageRelayWorker` 作為統一事件協調器
- 若導入，先把 Telegram 事件觸發收斂進來，再評估其他 source

**Step 6 — 設定與管理命令統一：**
- 保持 `config.json` 為單一 runtime 設定來源
- 新增 route 管理命令（查詢/設定 Telegram routes）
- 逐步把分散 `open(config.json)` 的寫法統一到 `ChannelConfig`

### 格式保留策略

**核心原則：同一個 Publisher 只負責「對頻道發文能力」，內容與格式邏輯留在 Adapter。**

**分層責任（避免格式被洗平）：**

1. `*RenderAdapter`（來源專屬）
   - 負責：內容組裝（文字段落、欄位順序、標題、footer）、視覺格式（Embed 樣式、Forum thread 命名、留言分段）、來源特化（PTT 留言續推、FB 首圖策略、Telegram spoiler）
   - 輸出：`RenderPlan`（發文計畫，不是單一字串）

2. `DiscordMessagePublisher`（共用能力）
   - 只負責執行 `RenderPlan`：send/edit/reply/thread 建立、附件分批、retry/backoff、錯誤處理與 observability log
   - **不決定內容文案與版型**

> 這樣可讓 PTT 保持「先開 thread → 送附圖 → 補留言」、FB 保持「主文+首圖 → 其餘分批」、Article 保持「現有 embed 欄位與圖像策略」，而 Publisher 只做可靠執行。

**RenderPlan 結構：**
- `target_type`: `text_channel | forum_channel | thread`
- `operations[]`: `create_thread`、`send_embed_with_files`、`send_files_batch`、`send_comment_chunks`
- `payload_meta`: source/type/version/trace id

**遷移原則：**
1. 先做 adapter 輸出與舊行為 golden output 比對
2. 逐來源切換（Article → FB → PTT → Telegram），一次只切一條
3. 每切一條做發文結果快照比對（文字、embed 欄位順序、圖片順序、thread/留言行為）
4. 若不一致，先修 adapter 不改 publisher

### Source 路徑分流

1. **Telegram（TG）走事件消費層 + Telegram Repository**
   - 入口：`MessageRelayWorker`
   - 即時：`LISTEN telegram_new_message`
   - 補償：每 1 小時 polling 補漏
   - 查詢：`TelegramMessageRepository` 依 message key 取完整訊息 + 媒體

2. **PTT / FB / Article 走來源資料存取層（SourceMessageRepository/Fetch）**
   - 目前來源型態：API pull
   - 由對應 fetch/repository adapter 取資料（非 Telegram notify 路徑）
   - 後續再進入 render adapter 與共用 publisher

3. **整合原則**
   - TG 與 PTT/FB/Article 允許「入口不同」
   - 但在 render/publish 階段收斂到同一套契約（`RenderPlan` + `DiscordMessagePublisher`）

### 跨來源 TODO

**P0（本期必做）：**
- [ ] 建立 `SourceFetchPort` 與來源實作（Article/FB/PTT/Telegram）
- [ ] 建立 `SourceFetchOrchestrator`（strategy/case 分派）

**P1（穩定化）：**
- [ ] 建立 `MessageRenderAdapter` 無損封裝模型
- [ ] 統一 config 讀寫方式，減少直接 `open(config.json)` 的分散寫法

**P2（整合擴充）：**
- [ ] 保留外部 API 不變，逐步內部改接 publisher（Article/FB/PTT）
- [ ] 規劃/新增管理命令：telegram route 查詢與設定

---

## 產品能力 TODO

<!-- @meta
id: product-todo
type: TODO
status: confirmed
last_confirmed: 2026-03-31
-->

### Phase 0（1 週，先拿數據）
- [ ] 在 `/askai` 回覆後加入快速反饋（👍/👎 或按鈕）
- [ ] 寫入回饋日誌（含問題、回覆、model、context meta、feedback）
- [ ] 建立每日 KPI 彙總腳本（互動量、滿意率、平均回覆長度、失敗率）

### Phase 1（1~2 週，提升好玩度）
- [ ] 增加「每日話題/今日任務」指令
- [ ] 增加「群友印象小卡」展示指令
- [ ] 增加「梗庫/金句」功能
- [ ] 增加「輕量遊戲化」：連續互動天數、活躍徽章

### Phase 2（2 週，品質優化）
- [ ] 建立 Prompt A/B 實驗（至少 2 組 system prompt）
- [ ] 模型路由策略（閒聊/技術問答/審核分流不同模型）
- [ ] RAG 召回評估集（固定 50~100 題做離線比較）

### Phase 3（資料成熟後再做 SFT）
- [ ] 蒐集 3k~10k 高品質多輪對話（含偏好標註）
- [ ] 先做偏好對齊（DPO/ORPO）小模型實驗
- [ ] 若明顯優於 prompt-only，再擴大 SFT

---

## Discord Bot 管理入口與指令整理 TODO

<!-- @meta
id: discord-management-todo
type: TODO
status: confirmed
last_confirmed: 2026-03-31
-->

### 目標 1：入口整合
- [ ] 建立 `/panel admin` 空殼
- [ ] 將 `/article_manager` 掛入主控台（保留舊命令）

### 目標 2：指令分層（使用者 vs 管理者 vs 開發）
- [ ] `test_commands` 改成 dev-only 載入
- [ ] 完成命令分類清單

### 目標 3：子命令化
- [ ] 提出子命令設計稿（`/article start|stop|status|test`）

### 追蹤指標
- [ ] 管理操作是否可由單一入口完成
- [ ] 指令數量是否下降或更清楚
- [ ] 正式環境是否已隔離開發命令
- [ ] 是否維持可回滾（舊入口仍可用）
