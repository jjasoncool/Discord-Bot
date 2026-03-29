# 【必讀】協作流程契約（優先於全文其他段落）

> 任何 AI/協作者先讀這段，再讀後文。

## 0) 使用者指定的討論流程（強制）

1. 每次討論先給**完整架構**，不能只回片段。
2. 清楚標示「本輪改了哪些共識」。
3. 最後做「整體確認」：
   - 已定案
   - 未定案
   - 下一步
4. 盡量避免反覆單題選單式問答，改用完整方案溝通。

## 1) 文件閉環規範（強制）

每一輪都要遵循：

1. 讀本檔（先讀本段）。
2. 沿用既有共識。
3. 討論/執行。
4. 回寫本檔（新增或修正共識）。
5. 下輪再先讀本檔。

> 簡式：`讀檔 -> 沿用共識 -> 討論/執行 -> 回寫 -> 下輪再讀`

## 2) TODO 更新規則（強制）

1. 完成項目要打勾。
2. 完成且無未完成關聯時，應自待辦移除。
3. 若仍有依賴未完成項目，保留並註記依賴。
4. **凡 AI/協作者在本輪「讀取過本檔」後，於本輪結束前必須回寫本檔進度**（至少更新：完成勾選、狀態註記或新增/修正共識）。
5. 若本輪無實作異動，也要在本檔留下「已讀取、已盤點、待確認事項」的最小紀錄，避免只讀不更。

## 2.1) 【高嚴重性】禁止未經確認刪除/覆寫使用者資料檔（強制）

> 這是高嚴重性事件，後續所有 AI/協作者必須遵守。

1. **禁止**在未取得使用者明確同意前，執行任何可能刪除、清空、覆寫資料檔的操作。
2. 針對以下類型檔案，一律視為「高風險資料」：
   - runtime 狀態檔（例如：`src/services/sent_articles.json`）
   - 使用者設定檔、快取、歷史紀錄、session、資料庫檔
3. 如需修改高風險資料檔，必須先：
   - 說明風險與影響
   - 提供備份/回復方案
   - 取得使用者同意後才可執行
4. 若發生誤刪/誤覆寫，需立即升級為**高嚴重性事故**，優先進行：
   - 現場凍結（停止進一步破壞）
   - 復原（git/reflog/stash/log/備份）
   - 事故紀錄與防再發措施回寫本檔

## 3) Telegram -> Discord（已完成，歸檔至 TODO-completed.md）

---

# Discord Bot AI 現況交接包（給其他 AI 分析用）

> 目的：快速讓外部 AI/顧問模型理解本專案現在的 AI 能力、缺口、優先順序。

## 1) 專案 AI 架構總覽

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

## 2) 目前已實作 AI 能力（重點）

### A. 對話能力（/askai）
- 有排隊機制（`ASKAI_QUEUE` + worker），避免高併發卡死。
- 支援 system prompt 檔案化（可維運調整）。
- 支援圖片輸入（jpg/png/webp，轉 base64 丟給 Ollama）。

### B. 多來源上下文（RAG）
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

### C. 向量資料庫與持久化
- 使用 pgvector（docker compose 有 `pgvector` service）。
- 聊天訊息可自動持久化進 pgvector（best effort，不阻斷主流程）。
- intro/impression 採「應用層 replace + 唯一索引」避免重複資料。

### D. 安全與防護
- Context 一律視為不可信（untrusted context safety prompt）。
- 防 prompt injection 的系統規則與邊界標記。
- Impression 入庫前審核：
  - 規則 prefilter
  - moderation model 二次判定
  - 硬閘道（prompt injection / meme spam / fake story）

### E. 可觀測性（Observability）
- askai prompt trace log
- askai prompt debug log（含 retrieval debug）
- askai response history（jsonl）
- 有 context/retrieval 統計欄位（fetched/relevant/trimmed/sent）

## 3) 模型與設定現況

`src/sys_settings/ollama_runtime_config.json`：
- generation model: `ministral-3:14b`
- embedding model: `bge-m3:latest`
- moderation model: `qwen2.5:7b`

特性：runtime config 可熱更新，不一定要重啟整個服務。

## 4) 目前不是「缺 SFT」，而是先缺產品互動閉環

### 判斷
現在已經有：RAG、長短期記憶、檢索融合、安全機制、觀測資料。

### 真正優先缺口
1. 使用者回饋信號蒐集（喜歡/不喜歡、是否有幫助）
2. 有趣玩法機制（事件、任務、成就、排行榜、角色互動）
3. 回覆品質 KPI 與 A/B 實驗機制

## 5) 給「另一個 AI」的分析 Prompt（可直接貼）

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

## 6) 後續 TODO（工程可執行版）

### Phase 0（1 週，先拿數據）
- [ ] 在 `/askai` 回覆後加入快速反饋（👍/👎 或按鈕）
- [ ] 寫入回饋日誌（含問題、回覆、model、context meta、feedback）
- [ ] 建立每日 KPI 彙總腳本（互動量、滿意率、平均回覆長度、失敗率）

### Phase 1（1~2 週，提升好玩度）
- [ ] 增加「每日話題/今日任務」指令
- [ ] 增加「群友印象小卡」展示指令（讓記憶對使用者可見）
- [ ] 增加「梗庫/金句」功能（可收藏、可引用）
- [ ] 增加「輕量遊戲化」：連續互動天數、活躍徽章

### Phase 2（2 週，品質優化）
- [ ] 建立 Prompt A/B 實驗（至少 2 組 system prompt）
- [ ] 模型路由策略（閒聊/技術問答/審核分流不同模型）
- [ ] RAG 召回評估集（固定 50~100 題做離線比較）

### Phase 3（資料成熟後再做 SFT）
- [ ] 蒐集 3k~10k 高品質多輪對話（含偏好標註）
- [ ] 先做偏好對齊（DPO/ORPO）小模型實驗
- [ ] 若明顯優於 prompt-only，再擴大 SFT

## 7) SFT 決策門檻（建議）

滿足以下條件再投入 SFT：
- 有足量高品質資料（非噪音對話）
- 有清楚評估集與 KPI（不是憑感覺）
- 已做過 prompt/RAG/模型路由優化仍卡住

否則先不做 SFT，先做產品迭代 + 資料閉環，通常 ROI 更高。

---

## 8) 跨來源整合方案（按部就班）

> Telegram Relay 已完成（架構/設定/流程盤點已歸檔至 `TODO-completed.md`）。
> 以下為仍待執行的跨來源整合計畫。

### 8.5 與新 class 整合方案（按部就班）

#### Step 1（先整合「讀資料流程」，不先動 Publisher）
1. 新增 `SourceFetchPort`（讀資料介面）與來源實作：
   - `ArticleFetchAdapter`
   - `FbFetchAdapter`
   - `PttFetchAdapter`
   - `TelegramFetchAdapter`
2. 新增 `SourceFetchOrchestrator`（依 source type 分派，類似 strategy/case router）。
3. 保留各來源原本去重邏輯（`sent_*`）不動，避免一次改壞。

#### Step 2（統一事件模型，仍不動 Publisher）
1. 定義 `MessageRenderAdapter`（標準輸入模型）。
2. 新增：
   - `ArticleRenderAdapter`
   - `FbRenderAdapter`
   - `PttRenderAdapter`
   - `TelegramRenderAdapter`
3. 讓 Publisher 只吃統一 payload，不直接懂來源細節。

> 重要補充（避免資料被過濾掉）：
> Adapter 採「**無損封裝（lossless envelope）**」而不是「裁剪欄位」。
>
> - `normalized_payload`：給 Publisher 需要的最小共用欄位（發文文字、附件、目標型態等）
> - `source_payload_raw`：完整保留來源原始資料（article/fb/ptt/telegram 各自差異欄位）
> - `source_meta`：來源型別、版本、追蹤 key
>
> 原則：
> 1) Publisher 只依賴 `normalized_payload`，不碰來源細節。
> 2) 任何來源特有欄位不得丟棄，必須保留在 `source_payload_raw`。
> 3) 若某來源需要特殊顯示（例如 PTT 留言串、Forum tag、Telegram spoiler），
>    由對應 Adapter 在轉換階段映射到 `normalized_payload` 的擴充欄位，
>    或由來源專屬 post-processor 處理，避免硬塞到 Publisher。

#### Step 3（導入 Route Resolver）
1. 新增 `MessageRouteResolver`，讓 route 規則從流程碼中抽離。
2. Telegram 先接 `telegram_channel_routes`。
3. 其他來源（Article/FB/PTT）逐步納入統一 route 規則。

#### Step 4（最後才整合 Publisher）
1. 新增/補強 `DiscordMessagePublisher`（文字、附件分批、重試、錯誤紀錄）。
2. 保留 `send_article_to_channel/send_fb_post_to_channel/send_ptt_post_to_forum_channel` 外觀，
   內部逐步改呼叫 publisher。
3. 先做 capability 共用，不做來源語意硬整併。

#### Step 5（最後才收斂 Worker）
1. 視穩定度決定是否導入 `MessageRelayWorker` 作為統一事件協調器。
2. 若導入，先把 Telegram 事件觸發收斂進來，再評估其他 source。

#### Step 6（設定與管理命令統一）
1. 保持 `config.json` 為單一 runtime 設定來源。
2. 新增 route 管理命令（查詢/設定 Telegram routes）。
3. 逐步把分散 `open(config.json)` 的寫法統一到 `ChannelConfig`。

### 8.6 新共識（2026-03-25）

- 優先整合順序調整為：
  1) **先整合讀資料（fetch/orchestrator）**
  2) 再整合 render/route
  3) **Publisher 放後面整合**
- 理由：
  - Article/FB/PTT 在取文與去重流程有高度相似性，先抽讀資料風險較低。
  - 發文端差異（TextChannel / ForumThread / 留言增量 / 圖片策略）較大，適合後置整合。

### 8.7 格式保留策略（你已確認的方向）

> 核心原則：
> **同一個 Publisher 只負責「對頻道發文能力」，內容與格式邏輯留在 Adapter。**

#### A) 分層責任（避免格式被洗平）
1. `*RenderAdapter`（來源專屬）
   - 負責：
     - 內容組裝（文字段落、欄位順序、標題、footer）
     - 視覺格式（Embed 樣式、Forum thread 命名、留言分段）
     - 來源特化（PTT 留言續推、FB 首圖策略、Telegram spoiler）
   - 輸出：`RenderPlan`（發文計畫，不是單一字串）

2. `DiscordMessagePublisher`（共用能力）
   - 只負責執行 `RenderPlan`：
     - send/edit/reply/thread 建立
     - 附件分批
     - retry/backoff
     - 錯誤處理與 observability log
   - **不決定內容文案與版型**

#### B) RenderPlan 建議結構（保留現有格式）
- `target_type`: `text_channel | forum_channel | thread`
- `operations[]`: 順序化操作清單，例如：
  - `create_thread`
  - `send_embed_with_files`
  - `send_files_batch`
  - `send_comment_chunks`
- `payload_meta`: source/type/version/trace id

> 這樣可讓 PTT 保持「先開 thread -> 送附圖 -> 補留言」、
> FB 保持「主文+首圖 -> 其餘分批」、
> Article 保持「現有 embed 欄位與圖像策略」，
> 而 Publisher 只做可靠執行。

#### C) 遷移原則（不破壞你滿意的格式）
1. 先做 adapter 輸出與舊行為對照（golden output 比對）。
2. 逐來源切換（Article -> FB -> PTT -> Telegram），一次只切一條。
3. 每切一條都要做「發文結果快照比對」：
   - 文字內容
   - embed 欄位順序
   - 圖片順序與分批行為
   - thread / 留言行為
4. 若比對不一致，先修 adapter，不改 publisher。

### 8.8 Source 路徑分流共識（再次確認）

> 這段為明確對應，避免後續 AI 誤解。

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

## 9) 注意事項

- 🚫 **硬性規則**：AI 禁止執行會變更環境狀態的 Docker 指令（例如 `docker compose up/down/build/restart`、`docker rm`、`docker rmi` 等）。
- ✅ 允許 AI 執行唯讀/除錯類 Docker 指令（例如 `docker ps`、`docker logs`、`docker exec` 查詢、`docker inspect`）。
- ✅ 若需要變更環境，AI 只能提供建議指令，由使用者自行在終端執行。
- 碼風慣例：4 空白縮排、繁體中文註解。
- 非同步開發：`asyncio` / `Telethon` / `asyncpg`。

---

## 10) TODO（跨來源整合追蹤）

> Telegram Relay 已全部完成並歸檔至 `TODO-completed.md`。以下為跨來源整合待辦。

### P0（本期必做）
- [ ] 建立 `SourceFetchPort` 與來源實作（Article/FB/PTT/Telegram）
- [ ] 建立 `SourceFetchOrchestrator`（strategy/case 分派）

### P1（穩定化）
- [ ] 建立 `MessageRenderAdapter` 無損封裝模型
- [ ] 統一 config 讀寫方式，減少直接 `open(config.json)` 的分散寫法

### P2（整合擴充）
- [ ] 保留外部 API 不變，逐步內部改接 publisher（Article/FB/PTT）
- [ ] 規劃/新增管理命令：telegram route 查詢與設定

---

## 11) 巴哈姆特論壇爬蟲 / 資料庫 / AI 整合 TODO

### 第一階段：先真的抓到文章與留言（MVP）
**目標**
- 能穩定抓到巴哈姆特指定看板/搜尋條件的文章列表
- 能抓到單篇文章主文、分類、作者、時間、URL
- 能抓到主文留言
- 能評估並確認回文、回文留言的可抓性與實際欄位來源

**交付成果**
- `bahamut_scraper_service.py` MVP 骨架
- 可用 `cloudscraper` / `requests session` 抓取巴哈頁面
- 列表頁抓取成功
- 文章頁抓取成功
- 留言抓取成功
- 產出 JSON 範例檔，確認欄位結構

**本階段 TODO**
- [ ] 研究巴哈文章列表頁、文章頁、留言區、回文區的實際 HTML / API 結構
- [ ] 確認是否需要登入 cookie、額外 headers、referer、anti-bot 處理
- [ ] 以 `cloudscraper` 建立 Bahamut session 與 retry 機制
- [ ] 實作文章列表抓取：標題、分類、作者、時間、URL、文章 ID
- [ ] 實作文章主文抓取：主文內容、作者資訊、發文時間、分類
- [ ] 實作主文留言抓取：留言者、內容、時間、樓層/位置
- [ ] 研究回文與回文留言資料來源，決定第一版是否先支援主文留言、第二版再補回文
- [ ] 定義 Bahamut JSON payload 結構（post / comments / replies / reply_comments）
- [ ] 先以檔案輸出驗證資料正確性，不急著寫 DB
- [ ] 建立錯誤處理、限速、重試、日誌紀錄

**完成標準**
- 能針對指定巴哈板面穩定抓到文章列表
- 能抓取至少一篇完整文章與 300~500 則留言樣本
- JSON 結構可供後續資料庫與 AI pipeline 直接使用

---

### 第二階段：整合資料庫（可查詢、可審查）
**目標**
- 把巴哈文章、留言、回文正式存入資料庫
- 支援未來依使用者、文章、時間、分類查詢
- 預留 moderation / 審查欄位

**交付成果**
- SQLAlchemy models
- Alembic migration
- upsert / 增量同步流程
- 可查特定 user 在哪些文章留言過
- 可查某篇文章的完整討論串

**本階段 TODO**
- [ ] 設計 `bahamut_posts` 主表
- [ ] 設計 `bahamut_post_comments` 留言表
- [ ] 設計 `bahamut_post_replies` 回文表
- [ ] 設計 `bahamut_reply_comments` 回文留言表
- [ ] 規劃 `raw_json` / `snapshot_json` 保存策略
- [ ] 規劃 `discussion_hash`、`last_comment_sync_at`、`last_reply_sync_at` 等增量同步欄位
- [ ] 預留 moderation 欄位：`moderation_status`、`moderation_score`、`moderation_labels`、`moderation_reason`
- [ ] 建立必要索引：`post_id`、`user_id`、`published_at`、`category`、`moderation_status`
- [ ] 在 scraper service 中實作 upsert 與增量更新
- [ ] 補上查詢 service：依文章、依使用者、依時間範圍查資料
- [ ] 驗證 Discord bot 後續取用資料時的查詢效率

**完成標準**
- 新抓到的巴哈文章能自動寫入資料庫
- 舊文章可做留言/回文增量補抓
- 可以 SQL 查詢特定留言使用者的歷史發言
- 可以針對單篇文章完整還原主文與討論結構

---

### 第三階段：整合 AI / pgvector / RAG
**目標**
- 讓 Discord bot 可以用巴哈資料做語意搜尋、摘要、審查輔助
- 讓結構化查詢與向量檢索並存

**交付成果**
- Bahamut RAG ingestion pipeline
- pgvector embeddings 與 metadata 設計
- Discord bot 查人 / 查文 / 摘要 / 審查指令雛型
- SQL + Vector 雙軌查詢流程

**本階段 TODO**
- [ ] 在 `retrieval_sources` 新增 `bahamut_forum` 資料來源設定
- [ ] 設計 Bahamut chunk 策略：主文 chunk、留言 chunk、回文 chunk、回文留言 chunk
- [ ] 設計 pgvector metadata：`doc_type`、`post_id`、`comment_id`、`reply_id`、`user_id`、`category`、`published_at`、`moderation_status`
- [ ] 建立 embedding / ingestion pipeline，將 Bahamut 資料寫入 pgvector
- [ ] 設計 SQL filter + Vector retrieval 的混合查詢流程
- [ ] 設計 Discord bot 指令：查主題、查文章、查特定使用者、查高風險留言
- [ ] 將審查欄位與 AI 分析結果串接（例如 review / blocked / summary）
- [ ] 建立摘要 prompt：單篇文章摘要、討論風向摘要、特定使用者發言摘要
- [ ] 建立觀測指標：索引筆數、查詢延遲、命中率、審查覆蓋率
- [ ] 驗證 Discord 問答是否可同時引用 Discord 聊天資料與巴哈論壇資料

**完成標準**
- Discord bot 可回答巴哈相關問題
- 可對特定使用者或主題進行 RAG 搜尋與摘要
- 可結合 moderation 資料做文章審查輔助
- 可與既有 `discord_chat` / `member_profile` retrieval 共存

---

### 巴哈姆特建議執行順序
- [ ] 先完成第一階段 MVP，不先碰 AI
- [ ] 第一階段抓到穩定資料後，再做第二階段資料庫正規化
- [ ] 第二階段查詢穩定後，再做第三階段 pgvector / RAG / AI 整合
- [ ] 每階段都保留 JSON 範例與測試案例，避免後續 parser 改版難以驗證

### 11.1 本輪實作討論草案（2026-03-29 上午，待你確認）

> 目的：依現有 `ptt_scraper_service.py` 與 DB 結構習慣，規劃 Bahamut 第一版最小可行實作（MVP）。

#### A) 實作策略（先可用、再擴充）
1. **先做 Bahamut 專屬 service，不先硬抽通用框架**
   - 新增：`src/scraper/services/bahamut_scraper_service.py`
   - 理由：先把 anti-bot / 解析規則跑通，避免過早抽象導致除錯困難。
2. **流程比照 PTT 現有模式**
   - `fetch_list -> fetch_detail -> parse_comments -> 產出標準 payload ->（先 JSON 驗證）-> 再接 DB upsert`
3. **資料保存採「raw + normalized」雙軌**
   - raw（原始回應/片段）保留，方便 parser 失效時回溯
   - normalized（結構化欄位）供 API / Discord / RAG 使用

#### B) 第一階段（MVP）具體落地
1. Session / 請求層
   - 優先 `cloudscraper` + retry + timeout + headers + referer
   - 固定加上 observability log（url, status, latency, retry_count）
2. 列表抓取
   - 輸出欄位：`post_id`, `title`, `author`, `category`, `published_at`, `url`
3. 單篇抓取
   - 主文欄位：`content`, `author_meta`, `published_at`, `category`
   - 留言欄位：`comment_id/position`, `user_id`, `content`, `published_at`
4. 回文策略
   - 第一版先完成「主文 + 主文留言」
   - 回文/回文留言先做可抓性探測（保留 raw），第二版再正式結構化
5. 驗證輸出
   - 落地 JSON 樣本：`src/scraper/data/bahamut_samples/*.json`

#### C) 第二階段（DB）建議欄位方向
1. `bahamut_posts`
   - `post_id`(uniq), `title`, `category`, `author_id`, `author_name`, `url`, `content`, `published_at`
   - `raw_json`, `snapshot_json`, `discussion_hash`, `last_comment_sync_at`, `last_reply_sync_at`
2. `bahamut_post_comments`
   - `post_id`(fk), `comment_id`, `user_id`, `user_name`, `content`, `published_at`, `raw_json`
3. `bahamut_post_replies` / `bahamut_reply_comments`
   - 先建表與索引，待第二版 parser 穩定後啟用寫入
4. moderation 預留
   - `moderation_status`, `moderation_score`, `moderation_labels`, `moderation_reason`

#### D) 風險與對策
1. anti-bot / 結構變動風險高
   - 對策：保留 raw + selector fallback + parser version
2. 文章/留言量大
   - 對策：先增量 cursor，同步窗口限制 + retry/backoff
3. 欄位易漂移
   - 對策：先定 JSON contract，再進 DB migration

#### E) 建議先做的實作順序（我會照這個做）
1. 建 `bahamut_scraper_service.py` + list/detail parse + sample JSON
2. 建 Bahamut models + migration + upsert
3. 加 API 查詢端點（recent / post detail / user comments）
4. 最後接 RAG ingestion

#### F) 使用者本輪確認（2026-03-29）
- 已確認：**第一版先做「主文 + 主文留言」**。
- 已確認：**回文/回文留言延到第二版**（第一版僅做可抓性探測與 raw 保存）。

#### G) 第一版目標板面與進版圖機制（2026-03-29）
- 目標板面：`https://forum.gamer.com.tw/B.php?bsn=74934`
- 使用者提醒：第一次進板會出現「進版圖/看板入口頁」，後續通常不再出現。

進版圖機制與迴避策略（第一版要實作）：
1. **機制說明**
   - 巴哈部分看板在首次進入時，會先導到進版圖頁（含「進入看板」按鈕或導頁流程）。
   - 若 session/cookie 尚未建立，直接抓列表可能拿到進版圖 HTML，而非文章列表。
2. **迴避方式（程式化）**
   - 啟動 crawler 時先做一次「預熱請求」：先 GET 看板 URL，檢查是否為進版圖頁。
   - 若偵測到進版圖，模擬點擊流程（依頁面按鈕/跳轉連結再請求一次）以建立 cookie/session。
   - 成功進入後保存同一個 session（cookies）供後續列表/內文抓取重用。
3. **偵測條件（建議）**
   - URL/path 含進版圖特徵，或 HTML 包含「進入看板」等關鍵字。
   - 若未偵測到文章列表必要 selector，回退判定為 gate page 並走 gate handling。
4. **容錯與重試**
   - gate handling 失敗時，記錄 raw html 快照與關鍵 log（url/status/selector 命中率），
     走有限次重試，避免卡死在首輪。

#### H) 本輪實作落地（2026-03-29）
- 已新增 `src/scraper/services/bahamut_scraper_service.py`（MVP）
  - 具備 `cloudscraper + retry` session
  - 具備進版圖 gate 偵測與導頁處理（預熱 + hop）
  - 具備列表抓取、單篇主文抓取、主文留言解析
  - 具備回文可抓性探測與 raw preview 保留（不入庫）
  - 具備 JSON 樣本輸出：`data/bahamut_samples/bahamut_sample_*.json`
- 已更新 `src/scraper/config.py`
  - 新增 `BAHAMUT_CONFIG`，預設目標板面：`bsn=74934`
- 已更新 `src/scraper/container.py`
  - 新增 `create_bahamut_scraper_service()`
- 已更新 `src/scraper/main.py`
  - 新增 `bahamut_scrape_task()`
  - 納入啟動即執行與每小時排程

> 備註：目前為第一版可運行骨架，後續會依實際頁面 selector 再微調欄位解析精度。

#### I) 抓取模式與套件討論草案（2026-03-29，待確認）

1. **抓取模式（第一版建議）**
   - 模式：`HTTP pull + session 持續化 + gate handling`
   - 流程：
     - 先打看板 URL（預熱）
     - 若命中進版圖（gate page）就跟隨「進入看板」導頁建立 cookie/session
     - 用同一個 session 抓列表頁
     - 逐篇抓主文與主文留言
     - 產出 JSON 樣本（raw + normalized）
   - 第一版不做：瀏覽器自動化登入、回文結構化入庫。

2. **抓取套件（目前採用）**
   - `cloudscraper`（優先）：處理常見 anti-bot 挑戰，維持 requests 介面。
   - `requests`（fallback）：cloudscraper 不可用時退回。
   - `BeautifulSoup4`：HTML 解析（列表/主文/留言 selector）。
   - `fake-useragent`：隨機 User-Agent，降低固定指紋風險。
   - `urllib3.Retry + HTTPAdapter`：重試與 backoff。

3. **為何不先上 Playwright/Selenium**
   - 第一版目標是穩定拿資料與建立欄位契約，非完整模擬人機互動。
   - 先用 HTTP 模式維護成本較低、部署較輕、除錯較快。
   - 若後續遇到強 JS 渲染或更嚴格防護，再升級為瀏覽器模式（第二版候選）。

---

## 12) Discord Bot 管理入口與指令整理 TODO

### 目標 1：入口整合（管理操作集中）
**要交付的成果**
- 一個管理入口：`/panel admin`
- 文章監控（開始/停止/狀態/測試）集中在主控台

**行動**
- [ ] 建立 `/panel admin` 空殼
- [ ] 將 `/article_manager` 掛入主控台（保留舊命令）

### 目標 2：指令分層（使用者 vs 管理者 vs 開發）
**要交付的成果**
- 正式環境只保留必要命令
- 開發測試命令不干擾正式使用

**行動**
- [ ] `test_commands` 改成 dev-only 載入
- [ ] 完成命令分類清單（管理 / 使用者 / 開發）

### 目標 3：未來擴充（子命令化）
**要交付的成果**
- 規劃子命令樹（例如 `/article start|stop|status|test`）

**行動**
- [ ] 提出子命令設計稿（先不改線上行為）

### 主管追蹤指標（每週看這 4 個）
- [ ] 管理操作是否可由單一入口完成
- [ ] 指令數量是否下降或更清楚
- [ ] 正式環境是否已隔離開發命令
- [ ] 是否維持可回滾（舊入口仍可用）
