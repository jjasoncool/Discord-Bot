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

#### J) 本輪 parser 修正（2026-03-29 上午）
- 已確認先前樣本只抓到較前段文章，且多為置頂文；原因是列表 parser 以 title link 為主掃描，未明確以 `tr.b-list__row.b-list-item` 為單位做完整 row 解析。
- 已修正列表 parser：
  - 改以 `tr.b-list__row.b-list-item` 為主體逐列解析
  - 補抓 `author` / `author_user_id`
  - 補抓 `last_reply_user` / `last_reply_user_id`
  - 補抓 `category`
  - 加入 `is_sticky`
- 已修正留言 parser：
  - 新增 fallback 文字拆解，嘗試解析 `floor` / `user_name` / `published_at`
  - 若 DOM 無 `data-userid`，改嘗試從使用者小屋連結反解 `userid`

> 備註：這版仍屬 HTML selector + fallback parser，下一輪要用新樣本驗證是否已覆蓋非置頂文與留言 user 欄位。

#### K) 巴哈姆特爬蟲開發原則（2026-03-29，使用者新增規範）

> 目的：現在先不提前抽象，但 Bahamut 實作需遵守未來跨來源模組化整合的隱性契約，降低後續包成 `SourceFetchPort / SourceFetchOrchestrator / MessageRenderAdapter` 的成本。

1. **公開方法命名與回傳契約固定**
   - `fetch_board_articles(session)` → `Dict[str, Any]`，且至少含 `ok`, `articles`
   - `fetch_article_detail(session, url)` → `Dict[str, Any]`，且至少含 `ok`, `content`, `comments`
   - `fetch_bahamut_articles_with_content()` → `Dict[str, Any]`，且至少含 `ok`, `articles`, `detailed_count`
   - `save_articles_to_db(articles)` → `int`（saved count）
   - 所有 fetch 方法一律維持 `Dict[str, Any]` + `ok: bool`

2. **依賴注入規則**
   - `__init__(self, db_manager=None)`
   - `config.py` 的 `BAHAMUT_CONFIG` 照現有慣例直接 import
   - 不在 service 內建立 DB session/engine，交由 `container.py`
   - `db_manager` 必須允許為 `None`（方便 JSON-only 測試）

3. **抓取與寫 DB 必須分離**
   - `fetch_bahamut_articles_with_content()` 只負責抓取
   - `save_articles_to_db(articles)` 只負責持久化
   - `main.py` 應採：`fetch -> save_articles_to_db -> commit`

4. **資料結構採 normalized + raw 雙軌**
   - normalized：`post_id, title, author, content, published_at, url, comments`
   - raw：原始 HTML preview / 探測資訊
   - 每篇文章需補 `source_type = "bahamut"`

5. **Session 生命週期由 Bahamut service 自行管理**
   - `with self._build_session() as session:`
   - 不把 HTTP session 管理外洩到 `main.py` / `container.py`

6. **main.py task 結構比照 PTT**
   - `container.create_database_tables()`
   - `service = container.create_bahamut_scraper_service()`
   - `result = service.fetch_bahamut_articles_with_content()`
   - `saved = service.save_articles_to_db(result["articles"])`
   - `service.db_manager.commit()`
   - `finally -> close db_manager`

7. **目前不要做的事**
   - 不提前抽 base class / ABC
   - 不改其他 scraper service
   - 不把 Bahamut gate/cloudscraper 抽到共用 utils
   - 不改 `container.py` 既有方法簽名，只新增 `create_bahamut_scraper_service()`
   - 不新增 Bahamut feature flag，直接由 `main.py` 排程

8. **DB model 命名慣例（後續）**
   - `bahamut_posts`, `bahamut_post_comments`
   - 與現有 `Base` 同體系
   - `post_id` unique constraint
   - 預留 `raw_json`, `moderation_status`

9. **未來模組化包裝方式**
   - 未來將以 `BahamutFetchAdapter` 包裝現有 `BahamutScraperService`
   - 因此當前 service 介面需保持乾淨穩定，不需提前為 adapter 反向改設計

#### K.1) 目前 Bahamut 實作與原則差異（待調整）

- **已對齊**
  - `__init__(db_manager=None)` 已符合
  - `fetch_*` 方法命名模式已符合
  - `fetch_bahamut_articles_with_content()` 由 service 自行管理 session 已符合
  - `container.py` 僅新增 `create_bahamut_scraper_service()` 已符合

- **待調整**
  1. 尚未實作 `save_articles_to_db(articles) -> int`
  2. `main.py` 的 `bahamut_scrape_task()` 目前仍是 JSON sample 輸出，尚未切成 `fetch -> save -> commit`
  3. 每篇文章尚未全面補齊 `source_type = "bahamut"`
  4. normalized/raw 雙軌雖已有雛型，但欄位命名仍需再收斂到固定契約

#### K.2) 手機版強制導向追因（2026-03-30）

- 使用者決議：先做「追因版」，找出為何 request 會被 server 判成 mobile 並導向 `m.gamer.com.tw`
- 已在 `BahamutScraperService._fetch_html()` 加入 debug log：
  - request start（url / referer / UA / mobile hint / cookies）
  - first response（final_url / status / redirect history / Location / Set-Cookie）
  - desktop retry response（若被導向 mobile，再記錄一次）
- 目的：釐清是以下哪一類原因造成 mobile redirect：
  1. request header / client hints 組合
  2. cookie 狀態
  3. response `Set-Cookie` 導致 server 後續黏到 mobile
  4. cloudscraper / requests fingerprint 被站方判為 mobile/非完整 desktop client

#### K.3) Bahamut 版本路由策略新共識（2026-03-30）

- 使用者最新決議：**回到原本策略**。
- 即使 server 回 `302 -> m.gamer.com.tw`，crawler 仍應：
  1. 記錄 redirect 事實（保留追因 log）
  2. **堅持再請求 desktop forum URL**
  3. 後續解析一律以 desktop forum HTML 為主，不改走 mobile API 路線
- 換句話說：
  - `mobile redirect` 視為 server routing 行為
  - 但 scraper 的資料來源策略仍維持 **desktop HTML first**
  - 不因為被導 mobile 就切換整體 parser 設計到 mobile 版

#### K.4) Redirect 行為測試目標（2026-03-30）

- 使用者希望先驗證：
  1. 當 crawler 堅持請求 desktop URL 時，Bahamut 會不會進入「無限 302」
  2. 還是 server 只會做一次/有限次 redirect，之後接受請求
- 本輪測試重點：
  - 觀察 redirect chain（`resp.history`）長度
  - 觀察 `Location` 是否反覆在 desktop/mobile 間來回
  - 觀察最終是否仍穩定落在 `m.gamer.com.tw`
- 判讀原則：
  - 若每次 desktop request 都只出現 **單次 302 -> mobile**，代表不是無限 redirect，而是 server 穩定拒絕 desktop routing
  - 若出現 desktop <-> mobile 反覆跳轉，才算真正的 redirect loop

#### K.5) 留言 XHR（moreCommend.php）參數與抓取共識（2026-03-30）

- 已確認巴哈文章頁留言有 XHR 補抓機制：
  - endpoint: `https://forum.gamer.com.tw/ajax/moreCommend.php`
- 參數語意（目前已可視為固定契約）：
  1. `bsn`：看板 ID（例：`74934`）
  2. `snB`：留言容器所屬樓層/篇的 ID（**不是**整串主題 `snA`）
  3. `returnHtml=1`：回傳格式為 `{"next_snC":..., "html":[...]}`
  4. `snC`：分頁/游標；搭配回應的 `next_snC` 逐頁抓取
- 重要觀察：
  - 同一個 `snA` 頁面可能對應多個可展開留言區，各自有不同 `snB`
  - 因此同 Referer 下，換不同 `snB` 仍可能抓到不同留言集合
- 實作結論（第一版 parser 補強方向）：
  1. 先由 `C.php` 解析出所有候選 `snB`
  2. 逐一呼叫 `moreCommend.php`
  3. 依 `next_snC` 翻頁直到 0

#### K.6) Bahamut 留言入庫去重 / 增量更新 / HOT 標籤共識（2026-03-30）

- 入庫避免重複抓取的建議主鍵：
  - 文章：`source=bahamut + post_id(snA)`
  - 留言：`source=bahamut + post_id(snA) + comment_id`
- 同步策略建議：
  1. 每次重抓文章時，以 `post_id` 做 upsert 更新主文欄位
  2. 留言以 `comment_id` 做 upsert：
     - 已存在：更新內容、時間、熱門標記、raw_text
     - 不存在：新增
  3. 文章額外維護：`comments_count`、`last_seen_at`、`last_comment_sync_at`
  4. 若新抓取留言數 > 舊留言數，視為動態更新成功
- 動態更新建議：
  - 針對最近活躍文章定時重抓
  - 若 `comments_count` 持續增加，保留在高頻同步名單
  - 若連續多次無變化，再降頻
- JSON / parser 新增欄位：
  - BeautifulSoup 額外辨識 `<span class="comment_hot-tag">HOT</span>`
  - 輸出欄位：`is_hot: true/false`
  - 語意：代表該留言具有熱門標籤（熱門留言）

#### K.7) 文章被編輯時的「雙版本保留」最簡化方案（2026-03-31）

- 使用者要求：
  - 若文章後續被編輯，希望可以留下「至少兩個版本」
  - 但資料庫設計**不要太複雜**

- 建議採用 **主表 + 單一前版本快照欄位**，不要一開始就拆完整版本歷史表：
  1. `bahamut_posts` 保留目前最新版欄位：
     - `content`（最新）
     - `title`（最新）
     - `content_hash`（最新內容 hash）
     - `updated_at` / `last_seen_at`
  2. 另外只新增一組「上一版本」欄位：
     - `prev_content`
     - `prev_title`
     - `prev_content_hash`
     - `prev_updated_at`

- 更新規則：
  1. 每次重抓文章時先算新的 `content_hash`
  2. 若 hash 與目前主表相同：
     - 視為未編輯
     - 只更新 `last_seen_at`
  3. 若 hash 與目前主表不同：
     - 先把「目前最新版」搬到 `prev_*`
     - 再把新內容寫進正式欄位（`content/title/content_hash`）

- 這樣可達成：
  - 永遠保留 **最新版本 + 上一個版本**
  - 結構非常簡單，不需要額外版本表
  - 查詢容易，不需要 join

- 缺點（可接受）：
  - 只能保留 2 個版本
  - 若文章被多次編輯，最舊版本會被覆蓋

- 若未來真的需要完整歷史，再升級成：
  - `bahamut_post_revisions` 歷史表
  - 但目前**不建議第一版就上**，避免 schema 與同步邏輯複雜化

#### K.8) 防惡意覆蓋保護（2026-03-31）

- 使用者新增要求：
  - 若文章後續被編輯，不可無條件覆蓋最新版本
  - 需防止「惡意清空 / 大量刪文 / 異常縮水」直接把原文洗掉

- 建議採 **內容縮水防呆規則**，保持簡單、不增加太多表：

1. 每次更新前，先比較：
   - `old_len = len(目前 content)`
   - `new_len = len(新抓 content)`
   - `shrink_ratio = new_len / old_len`

2. 預設允許正常更新條件：
   - `new_hash != old_hash` 且
   - `shrink_ratio >= 0.7`

3. 若出現以下情況，**取消覆蓋正式內容**：
   - `old_len` 足夠大（例如 `>= 500`）
   - 且 `shrink_ratio < 0.5`
   - 或 `new_len` 幾乎清空（例如 `< 100`）

4. 被阻擋時的處理方式：
   - 不更新 `content`
   - 不滾動 `prev_*`
   - 只寫入：
     - `last_seen_at`
     - `update_blocked = true`
     - `update_block_reason = 'suspicious_massive_shrink'`
     - `blocked_content_snapshot`（可選，保留本次抓到的異常版本）

5. 若想再更穩一點，但仍維持低複雜度，可加第二層條件：
   - 新內容必須同時包含：
     - 最低字數門檻
     - 至少一段正文 selector 命中
   - 若只剩空殼 DOM / 少量殘字，也視為阻擋

- 簡化後的實務建議：
  - **正式欄位只接受「正常變更」**
  - **異常縮水版本只記錄、不覆蓋**

- 這樣可達成：
  - 保護原始文章不被惡意編輯洗掉
  - 仍不需要完整 revision 歷史表
  - 只多幾個防呆欄位即可

#### K.9) Bahamut DB Schema / pgvector 相容 / migration 可維護原則（2026-03-31）

- 使用者新增要求：
  - Bahamut 資料表設計要**可維護**
  - 後續要與 **pgvector 資料庫**共存
  - **不要影響其他既有資料表**
  - 每個 migration 都要**可追蹤、可閱讀、可回滾**

- 設計原則：
  1. **Bahamut 使用獨立資料表**，不改動既有 `article_* / fb_* / ptt_*` 表
  2. **先做關聯式正規化 + raw 備份欄位**，向量索引不直接塞在這批表裡
  3. pgvector 後續 ingestion 時，從 Bahamut 表讀資料再寫入向量層；**不要把 scraper 主表直接和 embedding schema 綁死**
  4. migration 一律採 Alembic，單一檔案只做一個清楚主題

- 第一版建議資料表：

1. `bahamut_posts`（主表）
   - `id` PK
   - `source_type` (`bahamut`，方便未來跨來源一致化)
   - `board_id`（`bsn`）
   - `post_id`（`snA`，unique）
   - `title`
   - `category`
   - `author_id`
   - `author_name`
   - `url`
   - `published_at`
   - `last_seen_at`
   - `last_comment_sync_at`
   - `content`
   - `content_hash`
   - `prev_title`
   - `prev_content`
   - `prev_content_hash`
   - `prev_updated_at`
   - `comments_count`
   - `discussion_hash`
   - `update_blocked` (bool)
   - `update_block_reason`
   - `blocked_content_snapshot`
   - `raw_json`
   - `snapshot_json`
   - `parser_version`
   - `created_at`
   - `updated_at`

2. `bahamut_post_comments`（主文留言表）
   - `id` PK
   - `post_id_fk` -> `bahamut_posts.id`
   - `comment_id`（頁面 / XHR 唯一留言 ID）
   - `position`
   - `floor`
   - `user_id`
   - `user_name`
   - `content`
   - `content_hash`
   - `is_hot`
   - `source`（`html` / `xhr_moreCommend`）
   - `published_at`
   - `raw_text`
   - `raw_json`
   - `created_at`
   - `updated_at`
   - unique: (`post_id_fk`, `comment_id`)

3. `bahamut_sync_runs`（可選，但很推薦）
   - 用來記錄每次爬蟲同步批次
   - 欄位：`id`, `source_type`, `started_at`, `finished_at`, `status`, `articles_seen`, `articles_saved`, `comments_saved`, `notes`
   - 目的：
     - 讓 migration / schema 與同步結果追蹤分開
     - 日後查異常（哪次同步導致內容被 block）會很方便

- 第一版**不建議先建**：
  - `bahamut_post_revisions`
  - `bahamut_post_replies`
  - `bahamut_reply_comments`
  - 原因：先把主文 + 主文留言 + 版本保護做穩，避免 schema 過重

- 索引建議：
  - `bahamut_posts.post_id` unique index
  - `bahamut_posts.board_id` index
  - `bahamut_posts.published_at` index
  - `bahamut_posts.last_comment_sync_at` index
  - `bahamut_posts.content_hash` index
  - `bahamut_post_comments (post_id_fk, comment_id)` unique index
  - `bahamut_post_comments.user_id` index
  - `bahamut_post_comments.published_at` index
  - `bahamut_post_comments.content_hash` index

- 與 pgvector 共存方式：
  - Bahamut 關聯表保留為**來源真實資料層**
  - 之後若要做 RAG：
    - 以 `bahamut_posts` / `bahamut_post_comments` 為來源
    - chunk 後寫入獨立 vector documents / embeddings 表
    - metadata 帶：`source_type`, `post_id`, `comment_id`, `board_id`, `published_at`
  - 這樣 Bahamut schema 不會被 embedding provider / vector 綁住

- migration 命名與紀錄原則：
  1. 一個 migration 做一件事，例如：
     - `20260331_0135_add_bahamut_posts_table.py`
     - `20260331_0145_add_bahamut_post_comments_table.py`
     - `20260331_0155_add_bahamut_post_guard_fields.py`
  2. revision docstring 必須寫清楚：
     - 做了什麼
     - 為什麼要做
     - `Revises` 接哪個版本
  3. 每個 migration 必須有完整 downgrade
  4. 若是「欄位新增」與「索引新增」可分開 migration，方便出問題時局部回退
  5. migration 檔名與 revision id 都應可由人直接辨識，不要只用模糊名稱

- 建議 migration 執行順序：
  1. 先建 `bahamut_posts`
  2. 再建 `bahamut_post_comments`
  3. 再補 version / guard 欄位
  4. 最後若需要，再加 sync_runs

- 結論：
  - **Bahamut 先做自己的關聯表，不碰 pgvector schema 本體**
  - **向量層後掛**，降低耦合
  - **migration 小步、可回滾、可讀**，維護成本最低

#### K.10) SQLite vs pgvector / PostgreSQL 決策修正（2026-03-31）

- 使用者補充：
  - 目前 `PTT / FB / article_*` 那批 scraper 資料表，本質上是走 **SQLite**
  - 前面討論中不可誤以為它們已經在 pgvector / PostgreSQL 裡

- 決策建議修正為：
  1. **若 Bahamut 只是先做 crawler + 結構化保存 + upsert + 查詢**
     - 優先沿用 **SQLite**
     - 理由：
       - 與現有 scraper 層一致
       - migration / model / database manager 可直接沿用既有模式
       - 不會提早把 Bahamut 綁進 AI / vector 基礎設施
  2. **若 Bahamut 很快就要進 RAG / 多條件查詢 / 跨來源整合查詢**
     - 才考慮直接進 **PostgreSQL + pgvector 同庫共存**
     - 但也建議維持：
       - 關聯資料表（posts/comments）
       - 向量資料表（embeddings/documents）
       - 兩層分離，不要把 embedding 直接塞進 crawler 主表

- 目前最務實建議：
  - **第一階段先用 SQLite** 完成 Bahamut 的：
    - `bahamut_posts`
    - `bahamut_post_comments`
    - upsert / 版本保留 / 防惡意覆蓋
  - 等資料結構穩定後，再做第二階段：
    - 將 Bahamut 資料同步/搬運到 PostgreSQL + pgvector
    - 或讓 RAG ingestion 從 SQLite 讀出後寫入 pgvector

- 這樣的好處：
  - 不影響現有 scraper 架構
  - 開發風險最低
  - schema 可先穩定，再處理 AI / 向量層

#### K.11) 是否能依作者 ID 查詢發文與留言（2026-03-31）

- 結論：**可以，前提是 schema 一開始就把文章作者與留言作者分開存好。**

- 最低需求欄位：
  1. `bahamut_posts.author_id`
  2. `bahamut_posts.author_name`
  3. `bahamut_post_comments.user_id`
  4. `bahamut_post_comments.user_name`

- 這樣後續就能做兩種查詢：
  1. 查某作者 ID 發過哪些主文
  2. 查某作者 ID 留過哪些留言

- 也可以再包成一個「單一作者活動查詢」：
  - 先查 `bahamut_posts.author_id = :target_user_id`
  - 再查 `bahamut_post_comments.user_id = :target_user_id`
  - 最後在應用層合併成同一份活動紀錄

- 索引建議（第一版就該加）：
  - `bahamut_posts.author_id`
  - `bahamut_post_comments.user_id`

- 注意：
  - 若巴哈頁面有時抓不到穩定 `user_id`，至少也要保留 `user_name`
  - 但查詢主鍵仍應優先以 `user_id` 為主，`user_name` 只做輔助顯示與 fallback

#### K.12) Discord 論壇呈現策略（Bahamut 主文 / 回文 / 留言）討論結論（2026-03-31）

- 使用者新增考量：
  - Bahamut 一篇主文下可能持續有回文 / 留言
  - 若每次有新動態都在 Discord 新開文章，版面會很亂
  - 若只維持單一訊息並讓機器人一直 edit，也會很亂

- 建議採 **「一篇 Bahamut 主題 = 一個 Discord thread / forum post」** 的折衷方案：

1. **首次發現 Bahamut 主文時**
   - 在 Discord 建立一個 thread（或 forum post）
   - 首則訊息只放：
     - 標題
     - 作者
     - 原文連結
     - 主文摘要 / 截斷內容
     - 基本 metadata（分類、發文時間）

2. **後續新留言 / 新回文**
   - 不新增新的主題文章
   - 改為發在同一個 Discord thread 底下
   - 以「增量訊息」方式追加，例如：
     - `新增留言 3 則`
     - `新增回文 1 篇`
     - 每次只貼新增加的內容，不重貼整串

3. **不要高頻 edit 首則主文**
   - 首則主文訊息僅做低頻更新：
     - 例如標題修正
     - 主文內容真的被編輯且通過防呆規則
   - 留言/回文更新不要一直去改首則，避免洗版感與審計困難

4. **增量推送建議規則**
   - 若新留言少量（例如 1~3 則）：直接新增一則 bot 訊息摘要
   - 若短時間大量新增：合併成批次訊息
   - 每則增量訊息都應帶：
     - 來源時間
     - 留言者 / 回文者
     - 內容截斷
     - 原文樓層 / comment_id / reply_id

5. **避免亂版的核心原則**
   - 不為每則留言都新開 thread
   - 不為每次同步都 edit 同一則訊息
   - 採「主題固定、更新增量 append」

- 實務上最推薦的 Discord 呈現模型：
  - `Bahamut 主文` -> Discord thread/forum post
  - `Bahamut 新留言 / 新回文` -> 該 thread 內的 bot 增量訊息
  - `Bahamut 主文被編輯` -> 低頻更新首則 + 必要時發一則「主文已更新」提示

- 若未來要更進一步降低干擾，可加：
  - 批次同步視窗（例如 10~15 分鐘彙整一次）
  - 每篇文章維護 `discord_thread_id`、`discord_root_message_id`
  - 每次只推送「尚未發送到 Discord 的新留言 ID / 回文 ID」

#### K.13) 留言 parser 問題修正紀錄（2026-03-31）

- 使用者回報新樣本問題：
  - `content` 被錯抓成 `HOT #`
  - `published_at` 被錯抓成樓層（如 `B12`）
  - `HOT` 沒被正確轉成 `is_hot`

- 判斷原因：
  - 部分留言 DOM 文字混合了：`HOT`、引用片段 `#B10:...#`、樓層、時間
  - 舊 parser 直接取整段文字 / 不夠精準的 selector，導致正文與 metadata 混在一起

- 修正方向：
  1. 新增專用 helper，優先從留言內容節點抽乾淨正文
  2. 先移除 `.comment_hot-tag` / floor / time 等 metadata 再取文字
  3. `published_at` 僅接受真正時間格式，避免把 `B12` 當時間
  4. HTML 與 XHR 留言路徑都補上 `is_hot`

#### K.14) Bahamut 留言推/噓 icon custom 規則（2026-03-31）

- 使用者指定 custom 規則：
  - `<i class="material-icons"></i>` 轉成 `👍`
  - `<i class="material-icons"></i>` 轉成 `👎`

- 安全判斷方式不只看 glyph，還要看按鈕語意：
  - 讚：
    - `onclick="Forum.C.commentGp(this);"`
    - `class="gp ..."`
    - `title="推一個！"`
  - 倒讚：
    - `onclick="Forum.C.commentBp(this);"`
    - `class="bp"`
    - `title="我要噓…"`

- 實作共識：
  1. 留言 `raw_text` / `content` 中若含這兩個 material icon 字元，轉為 `👍 / 👎`
  2. 額外保留結構化欄位：
     - `has_thumbsup_button`
     - `has_thumbsdown_button`
     - `thumbsup_emoji`
     - `thumbsdown_emoji`
  3. DOM 判斷優先於純文字 glyph，避免單靠字元誤判
  4. 與 HTML 內已出現留言合併去重，避免重複

#### K.15) JSON 是否需要保留 `thumbsup_emoji` / `thumbsdown_emoji`（2026-03-31）

- 結論建議：**正式 JSON / DB 不必特別保留 `thumbsup_emoji` / `thumbsdown_emoji`。**

- 理由：
  1. 這兩個欄位是顯示層資料，不是核心結構化資料
  2. 真正有價值的是「是否偵測到推/噓按鈕語意」
  3. emoji 可在 Discord render 階段臨時映射，不需要長期存檔

- 建議保留的最小欄位：
  - `has_thumbsup_button`
  - `has_thumbsdown_button`

- 若後續還要再精簡，可連這兩個都不進正式資料層，只保留在 debug/sample JSON；
  但目前建議先留布林欄位、拿掉 emoji 欄位即可。

#### K.16) 主文圖片保留與單篇文章抓取模式（2026-03-31）

- 使用者新增需求：
  1. 主文內若有圖片，JSON 應保留
  2. 希望主程式可傳入特定文章 ID（`snA`），只抓單篇文章

- 實作共識：
  1. 每篇文章新增：
     - `content_images: []`
     - 從主文 DOM 的 `img` 節點擷取 `src / data-src / data-original`
  2. `bahamut_scraper_service.py` 支援單篇模式：
     - 建議用法：`python services/bahamut_scraper_service.py --sna 16219`
     - `bsn=74934` 為鳴潮板預設值，沿用設定檔
     - 只需帶入 `snA=16219`（主文 ID）
     - 舊的 positional 寫法已移除，避免語意混淆
  3. 單篇模式主要用於：
     - parser 除錯
     - 驗證特定文章圖片 / 留言 / HOT / 引用格式

#### K.17) 主文圖片不可混入回覆文章圖片（2026-03-31）

- 使用者回報：
  - 某些 `content_images` 會混入「回覆文章」中的圖片
  - 例如主文 `snA=16219` 的第三張圖其實屬於回覆，不應算在主文圖片

- 修正共識：
  1. 主文圖片擷取必須先鎖定主文 root
  2. 再排除留言 / 回覆區節點，例如：
     - `.c-reply__item`
     - `.reply-content`
     - `.comment-list`
     - `.c-post__footer__reply`
     - `Commendlist_*`
  3. `content_images` 只能保留主文真正內嵌圖片，不可混入回覆文章圖片

#### K.18) 如何分辨主文 vs 回覆文章（2026-03-31）

- 使用者要求：需要明確記錄目前 parser 是如何區分「主文」與「回覆文章」。

- 目前第一版的判斷方式：
  1. **主文**：
     - 以文章頁主內容 root 為準，例如：
       - `.c-article__content`
       - `.c-post__body`
       - `#article-content`
       - `.post-content`
       - `article`
  2. **回覆 / 留言 / 後續討論區**：
     - 視為主文之外的獨立區塊，例如：
       - `.c-reply__item`
       - `.reply-content`
       - `.comment-list`
       - `.c-post__footer__reply`
       - `Commendlist_*`

- 圖片擷取的實務規則：
  - 先鎖定主文 root
  - 再刪除上述回覆/留言區塊
  - 剩下的 `img` 才算 `content_images`

- 重要限制：
  - 這是第一版的 DOM 區塊判斷，不代表已完整結構化「回覆文章」
  - 若巴哈頁面把回覆文章 DOM 混進主文容器內，未來仍可能需要更細的 selector / data attribute 規則

#### K.19) Bahamut 連結參數語意修正（2026-03-31）

- 使用者補充的重要觀察：
  - 複製主文連結時，可能看到像 `sn=117959` 這種主文用的獨立 sn ID
  - 而 `snA` 比較像整篇全文/整串討論所屬的 group ID

- 因此目前需記錄：
  1. `sn`：
     - 可視為單篇主文/單一內容實體的獨立 ID
  2. `snA`：
     - 應視為全文頁 / 討論串層級 / group 型 ID
     - 不是最細粒度的單文 ID

- 後續 parser / DB 設計提醒：
  - 不應過早假設 `snA` 就是唯一單文 ID
  - 若頁面上能穩定取得 `sn`，後續應評估：
    - `sn` 作為主文唯一識別
    - `snA` 作為 thread / group / parent 識別
  - 目前第一版仍以既有 `snA` 路徑運作，但這點已列為**高優先觀察事項**，避免後續資料模型設錯

#### K.20) `sn` 資訊抓取策略（面對 JS「複製連結」按鈕）（2026-03-31）

- 使用者補充：
  - `sn` 是從頁面上的「複製連結」功能取得
  - 該入口是：`<a data-action="copyLink" href="javascript:;">複製連結</a>`
  - 這代表 `sn` 很可能不是直接寫在靜態 HTML href，而是由前端 JS 在點擊時組出

- 因此抓取策略不應只看這個 `href="javascript:;"` 本身，而應採以下順序：

1. **先找頁面內嵌資料源**（首選）
   - 搜尋 HTML / inline script 中是否有：
     - `copyLink`
     - `data-sn`
     - `sn:` / `"sn"`
     - 與文章分享/複製相關的 JS config 物件
   - 若 `sn` 已存在於頁面初始化資料或 script 變數，就不需要模擬點擊

2. **再找 DOM 上的 data-* 屬性**
   - 有些站會把真正值放在：
     - `data-sn`
     - `data-article-sn`
     - `data-share-url`
     - 相鄰節點的 dataset

3. **最後才考慮 JS 行為還原**
   - 若前兩者都沒有，才去研究 `data-action="copyLink"` 對應的前端函式
   - 做法是：
     - 從 HTML / JS bundle / inline script 搜 `copyLink`
     - 反推出它組 URL 時讀了哪些欄位
   - 原則上仍優先用 HTTP 靜態解析，不先升級到瀏覽器自動化

- 目前共識：
  - `href="javascript:;"` 本身沒有資訊價值
  - 真正要抓的是「被 JS 組裝前的資料來源」
  - 若能在 HTML / script / dataset 找到 `sn`，這是第一優先方案

#### K.21) 由 HTML 結構判斷「本文 / 回覆文章 / 留言」的新線索（2026-03-31）

- 使用者提供的 HTML 片段已足夠支持更精確的結構判斷：

1. **本文 / 回覆文章都是 `section.c-section` 層級**
   - 例如：
     - `<a name="117959"></a><section class="c-section" id="post_117959">...`
     - `<a name="118000"></a><section class="c-section" id="post_118000">...`
   - 這表示：
     - `a[name]` / `section#post_*` 對應的是「一篇文章樓層」
     - 可用來當本文/回覆文章的切分邊界

2. **主文 / 回覆文章的單篇 ID 可由這層取得**
   - `a name="117959"`
   - `id="post_117959"`
   - `href="Co.php?bsn=74934&sn=117959&subbsn=15..."`
   - 這些都支持：`sn=117959` 是單篇文章級 ID

3. **`snA=16219` 仍像 thread / 全文頁級 ID**
   - 例如 form action：`post2.php?bsn=74934&all=0&snA=16219`
   - 以及 option menu data 中同時帶：
     - `snA: 16219`
     - `sn: 118000`
   - 這更加支持：
     - `snA` = 全串/全文頁/group ID
     - `sn` = 單篇本文或單篇回覆文章 ID

4. **留言則屬於文章底下的 `Commendlist_<sn>` 區塊**
   - 例如：`<div id="Commendlist_118000">`
   - 留言的 `snB` 應對應單篇文章 `sn=118000`
   - 也就是：
     - 主文/回覆文章：`sn`
     - 該篇底下留言容器：`snB == sn`

5. **`c-reply__editor` 可作為文章區塊結尾的輔助訊號**
   - 因為它出現在某篇文章/回覆文章底下的留言編輯區
   - 但它不適合單獨當主判斷依據
   - 真正穩定的切分仍應優先靠：
     - `a[name]`
     - `section.c-section#post_<sn>`
     - `Co.php?...&sn=<sn>`

- 新共識：
  - 後續要分辨「本文 vs 回覆文章」，不應只靠主內容 root / 排除留言區
  - 應升級為：
    1. 先以 `section.c-section` 當文章級 block
    2. 第一個 block 視為本文
    3. 後續 block 視為回覆文章
    4. 每個 block 內再各自解析：
       - `sn`
       - `author`
       - `content`
       - `images`
       - `comments`

#### K.22) block 留言處理與 JSON 包裝層級（2026-03-31）

- 使用者追問：
  1. 每個 block 的留言是否都要處理
  2. 回覆文章是否要包在主文 JSON 之中

- 目前建議架構：**要處理，而且要包在主文 JSON 裡，但分層清楚，不要打平。**

1. **每個文章級 block 都應各自處理留言**
   - 本文 block 有自己的留言
   - 每個回覆文章 block 也有自己的留言
   - 實作上應以該 block 的 `sn` 去找對應：
     - `Commendlist_<sn>`
     - `snB = <該 block 的 sn>`

2. **JSON 包裝層級建議**
   - 最外層仍是一篇 thread / 全文頁（`snA`）
   - 主文作為 root article
   - 回覆文章包在主文 JSON 內的 `replies[]`

3. **建議資料結構**
   - thread / group：`snA`
   - root post：主文 block
   - reply posts：`replies[]`
   - 每個 post/reply 都各自有：
     - `sn`
     - `author`
     - `content`
     - `content_images`
     - `comments[]`

4. **避免的做法**
   - 不要把所有留言都混在主文同一層 `comments[]`
   - 不要把回覆文章打平成和留言同一層級

- 結論：
  - **每個 block 的留言都要處理**
  - **回覆文章要包在主文 JSON 之中，但以 `replies[]` 獨立結構呈現**

#### K.23) `post + replies` 已實作進 parser（2026-03-31）

- 本輪已落地：
  1. 以 `section.c-section[id^='post_']` 切文章級 block
  2. 第一個 block 輸出為 `post`
  3. 後續 block 輸出為 `replies[]`
  4. 每個 block 各自帶：
     - `sn`
     - `author`
     - `author_id`
     - `published_at`
     - `content`
     - `content_images`
     - `comments[]`
  5. 舊欄位仍暫時保留相容：
     - `content`
     - `comments`
     - `comments_count`

- 目前輸出層級：
  - thread/group：`snA`
  - root article：展平成頂層欄位（含 `sn`, `position`, `title`, `content`）
  - reply articles：`replies[]`

- 補充修正：
  - 不再重複輸出一份巢狀 `post` 物件，避免與頂層主文欄位重複

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
