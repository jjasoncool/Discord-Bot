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
- 2026-03-31：已依新共識調整規範為「非每輪強制回寫」，並允許 AI 僅讀取任務所需區塊。
- 2026-03-31：本輪已讀取、已盤點全文；未實作、不變更既有共識。
- 2026-03-31：完成 Bahamut DB 第一版落地（model + upsert + save_articles_to_db + main.py 串接）。詳見 BAHAMUT.STATE / BAHAMUT.CONTRACT / DB Schema 各區塊。
- 2026-04-01：新增 GP/BP 數字提取（主文 + 留言）、文章多頁遍歷（C.php 分頁）、列表分頁範圍（B.php start/end page）、CLI 預設寫 DB。
- 2026-04-01：定案 Bahamut → Discord relay 架構：HTTP webhook 通知 + Scraper API + embed 呈現 + 留言格預建/溢出機制。
- 2026-04-01：Telegram Relay 大檔案處理 — publish_to_channel 加入檔案大小檢查與自動壓縮（ffmpeg 影片 / Pillow 圖片），Dockerfile 加裝 ffmpeg。壓縮失敗或仍超限則跳過該檔，不阻斷其他內容。
- 2026-04-02：完成 Bahamut → Discord relay 首版 + 增量更新 + SQLite state 遷移。詳細變更如下：
  - Scraper API：`/api/bahamut/recent` + `/api/bahamut/{board_id}/{post_id}`
  - `bahamut_monitor.py`：embed 格式化（主文藍/回覆綠/留言灰）+ 留言格預建3格 + 鏈式溢出導航
  - `/get_baha_post` 斜線命令（article_commands.py，board_id 預設 74934）
  - 增量更新：GP/BP 同步 + 新留言 edit + 新回覆 append，hash 比對跳過無變化（防 rate limit）
  - `state_db.py`：SQLite 取代 sent_articles.json，5 張表（sent_content / forum_thread_state / bahamut_post_state / bahamut_comment_slot / bahamut_synced_comment）
  - `base_monitor.py`：所有 state 方法改 async，全域共用 StateDB + asyncio.Lock 併發安全
  - `article_monitor.py`：所有 state 呼叫加 await
  - 留言格式：作者連結巴哈小屋、圖片 URL 轉 `[🖼 圖片](url)`、🔥/👍/👎 條件顯示
  - JSON → SQLite 手動遷移腳本：`migrate_json_to_sqlite.py`
- 2026-04-02：完成 HTTP webhook 通知 + 共用工具抽取 + config 快取。詳細變更：
  - `notify_server.py`：通用 aiohttp.web 通知伺服器，`POST /notify/{source}` 分派架構
  - `main.py`（scraper）：巴哈抓完存 DB 後呼叫 `_notify_discord_bot("bahamut", ...)`
  - `discord_bot.py`：on_ready 啟動 notify server (port 5000)
  - `docker-compose.yaml`：discord-bot 加 `expose: ["5000"]`
  - `discord_content.py`：共用工具抽取（sanitize_forum_thread_title / linkify_image_urls / content_hash / chunk_discord_files / get_forum_tags）
  - `ChannelConfig`：加入 TTL 5 分鐘記憶體快取，避免重複讀檔
  - Scraper config：`board_end_page` 1→2（自動抓前 2 頁）、`export_sample_json` 關閉

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
| Bahamut parser | **目前最活躍主線**，結構已收斂，含多頁遍歷 | 85% | [Bahamut 專區](#bahamut-專區) |
| Bahamut DB schema / upsert | **第一版已落地**，含 GP/BP | 80% | [DB 設計](#bahamut-db-schema-設計) |
| Bahamut → Discord relay | **全自動閉環已實作，待端到端測試** | 90% | [呈現策略](#bahamut-discord-呈現策略) |
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

#### BAHAMUT.STATE

<!-- @meta
id: bahamut-state-formal
type: STATE
status: confirmed
depends_on: []
affects: [bahamut-contract-formal, bahamut-next-formal, bahamut-risk-formal]
last_confirmed: 2026-04-02
-->

**目前主線**
- Bahamut parser 結構已收斂，DB 第一版已落地。
- 主文 + 回文共用 `bahamut_posts` 表（以 `position` 區分），留言獨立 `bahamut_post_comments` 表。

**目前已落地**
- 可抓 board list（支援 `--start-page` / `--end-page` 指定範圍，頁間有延遲）
- 可抓 article detail（支援文章多頁遍歷，自動偵測 C.php 分頁數並逐頁抓取）
- 可處理 gate / 進版圖
- 可抓 HTML + XHR 留言（`moreCommend.php`）
- 可保留主文圖片 `content_images`
- 可輸出 `post + replies`
- 可單篇除錯：`python services/bahamut_scraper_service.py --sna 16219`
- `save_articles_to_db(articles)` 已實作（主文 + 回文 + 各自留言全部入庫）
- DB upsert 邏輯已實作（文章以 `(board_id, sn)` 做 upsert，留言以 `(parent_sn, comment_id)` 做 upsert）
- `main.py` 已串接：`fetch -> save_articles_to_db -> commit`
- 留言 `published_at` 已清除「留言時間 」前綴，格式統一為 `YYYY-MM-DD HH:MM:SS`
- `source_type` 已移除（表名已隱含來源）
- JSON sample 輸出改為可設定開關（`config.py` 的 `export_sample_json`）
- GP/BP 數字提取：主文/回文從 `div.gp > a.count` / `div.bp > a.count` 取，留言從 `a.gp-count[data-gp]` / `a.bp-count[data-bp]` 取，fallback 從 `raw_text` 提取
- CLI 預設寫 DB（透過 container 注入 db_manager），不需額外 flag

**目前已落地（Discord relay + 增量更新，2026-04-02）**
- Scraper API：`/api/bahamut/recent`、`/api/bahamut/{board_id}/{post_id}`（含主文+回覆+留言，按 snA 分組）
- Discord Bot：`bahamut_monitor.py`（embed 格式化 + 留言格預建/溢出 + 鏈式導航連結）
- 斜線命令：`/get_baha_post post_id:<snA> [board_id:74934]`
- 留言格式：`🔥 B1 **user** 👍107 — content`，圖片 URL 轉 `[🖼 圖片](url)`，作者名連結巴哈小屋
- 溢出導航：格3→格4→格5 鏈式 reply + `⬇️ 更多留言...` 導航連結
- 增量更新：已存在 thread 時自動走 `_update_existing_thread`（GP/BP edit + 新留言重組 slot + 新回覆 append）
- hash 比對：無變化的 embed/留言格跳過不 edit（防 Discord rate limit）
- `BahamutMonitor` 繼承 `BaseContentMonitor`，共用 StateDB

**目前已落地（State 追蹤 SQLite 遷移，2026-04-02）**
- `state_db.py`：async SQLite 封裝，5 張表（`sent_content` / `forum_thread_state` / `bahamut_post_state` / `bahamut_comment_slot` / `bahamut_synced_comment`）
- `base_monitor.py`：所有 state 方法改 async，全域共用 StateDB + `asyncio.Lock` 併發安全
- `article_monitor.py`：所有 state 呼叫加 `await`
- `migrate_json_to_sqlite.py`：手動遷移腳本，sent_articles.json → sent_articles.db
- 遷移已執行完成（446 articles + 386 fb + 507 ptt）

**目前已落地（webhook 通知 + 共用工具，2026-04-02）**
- `notify_server.py`：通用 aiohttp.web server，`POST /notify/{source}` 分派架構，日後加新來源只需加 handler
- Scraper `main.py`：巴哈抓完存 DB 後自動 POST `http://discord-bot:5000/notify/bahamut`
- `discord_bot.py`：on_ready 啟動 notify server (port 5000)
- `discord_content.py`：共用工具（sanitize_forum_thread_title / linkify_image_urls / content_hash / chunk_discord_files / get_forum_tags）
- `ChannelConfig` 快取：TTL 5 分鐘，避免每次讀檔
- Scraper config：自動抓前 2 頁、關閉 JSON sample 輸出

**目前尚未落地**
- 正式 DB migration（第一版用 `create_tables()` 自動建表）
- 防惡意覆蓋機制（`prev_*` / `content_hash` / `shrink_ratio`）
- RAG ingestion

#### BAHAMUT.CONTRACT

<!-- @meta
id: bahamut-contract-formal
type: CONTRACT
status: confirmed
depends_on: [bahamut-state-formal, bahamut-id-formal]
affects: [bahamut-db-formal, bahamut-next-formal]
last_confirmed: 2026-03-31
-->

**方法契約**
- `fetch_board_articles(session)` -> `Dict[str, Any]`，至少含 `ok`, `articles`
- `fetch_article_detail(session, url)` -> `Dict[str, Any]`，至少含 `ok`, `content`, `comments`
- `fetch_bahamut_articles_with_content()` -> `Dict[str, Any]`，至少含 `ok`, `articles`, `detailed_count`
- `save_articles_to_db(articles)` -> `int`（已實作，存主文 + 回文 + 各自留言）

**資料流契約**
- 抓取與寫 DB 必須分離
- service 自己管理 HTTP session
- `main.py` 最終應採：`fetch -> save_articles_to_db -> commit`

**JSON 正式契約**
- 主文欄位展平在頂層
- 主文 `snA` 與主文 `sn` 必須同層
- 不再重複輸出巢狀 `post`
- 回覆文章放 `replies[]`
- 每個 reply 自帶自己的 `comments[]`

**留言欄位語意契約**
- `comment_id` = 留言來源識別值候選，應作為留言辨識主鍵核心
- `floor` = 顯示樓層（如 `B8`、`B10`），可能跳號，不可當唯一鍵
- `position` = parser 輸出用排序序號，僅供呈現/檢查，不可當唯一鍵或 upsert key
- 若留言要做正式 upsert，應以「父文章作用域 + comment_id」作唯一鍵

**主文頂層關鍵欄位順序**
- `post_id`
- `snA`
- `sn`
- `position`
- `title`
- `url`
- `final_url`
- `author`
- `author_id`
- `ip`
- `area`
- `gp_count`
- `bp_count`
- `published_at`
- `content`
- `content_images`
- `content_length`
- `comments_count`
- `comments`
- `replies`
- `replies_count`
- `total_pages`

> `source_type` 已移除（DB 表名已隱含來源）。`ip`、`area`、`gp_count`、`bp_count`、`total_pages` 為後加欄位，已補進契約。

#### BAHAMUT.ID_MODEL

<!-- @meta
id: bahamut-id-formal
type: DECISION
status: confirmed
depends_on: []
affects: [bahamut-contract-formal, bahamut-db-formal, bahamut-risk-formal]
last_confirmed: 2026-03-31
-->

**ID 分層正式理解**
- `snA` = thread / 全文頁 / group ID
- `sn` = 單篇文章 ID（本文或回覆文章）
- `snB` = 留言 XHR 目標文章 ID
- `comment_id` = 單則留言識別值候選；目前視為該父文章作用域下最適合的留言唯一鍵核心

**目前最可信抓取來源**
- `section.c-section#post_<sn>`
- `a[name="<sn>"]`
- `Co.php?...&sn=<sn>`
- `Commendlist_<snB>`

**注意**
- `snA` 不是最細粒度單文 ID
- `snB` 目前高度吻合該 block 的 `sn`，但仍列為持續驗證項
- `floor` 會因刪除留言而跳號，不能當唯一鍵
- `position` 只代表本次輸出的排序結果，不能當資料層唯一鍵

#### BAHAMUT.STRUCTURE

<!-- @meta
id: bahamut-structure-formal
type: DECISION
status: confirmed
depends_on: [bahamut-id-formal]
affects: [bahamut-contract-formal, bahamut-risk-formal]
last_confirmed: 2026-03-31
-->

**文章切分規則**
- `section.c-section[id^='post_']` = 文章級 block
- 第一個 block = 本文
- 後續 block = 回覆文章

**留言歸屬規則**
- 每個文章級 block 都可能有自己的留言區
- 對應：`Commendlist_<sn>`
- 也就是：reply 的留言不屬於主文，要留在 reply 自己的 `comments[]`

**圖片歸屬規則**
- 主文圖片不可混入回覆文章圖片
- 需先鎖定主文 root，再排除 reply/comment 區塊後取 `img`

#### BAHAMUT.RISK

<!-- @meta
id: bahamut-risk-formal
type: RISK
status: confirmed
depends_on: [bahamut-id-formal, bahamut-structure-formal]
affects: [bahamut-next-formal]
last_confirmed: 2026-04-02
-->

**目前主要風險**
1. `snB == sn` 雖高度吻合，但不能當作 100% 已證明事實
2. HTML 結構若再變，`section.c-section` / `Commendlist_*` selector 可能失效

**已解除的風險**
- ~~DB 層尚未實作~~ — 已落地，upsert 邏輯已驗證
- ~~sample JSON 與程式意圖不一致~~ — 已驗證通過
- ~~post_id / snA / sn 命名未收斂~~ — 已定案 `post_id = snA`
- ~~State 追蹤尚未實作~~ — SQLite 已遷移，增量更新含去重
- ~~sent_articles.json 膨脹~~ — 已遷移至 SQLite

#### BAHAMUT.NEXT

<!-- @meta
id: bahamut-next-formal
type: TODO
status: confirmed
depends_on: [bahamut-state-formal, bahamut-contract-formal, bahamut-risk-formal]
affects: []
last_confirmed: 2026-04-02
-->

**已完成項目已歸檔整理（截至 2026-04-02）**
- 已完成項目不再保留於此待辦清單，避免重複追蹤。
- 主要完成里程碑已反映於 STATE 區塊。

**下一步（依優先序）**
1. 端到端測試：重啟兩容器後等 Scraper 自動抓取 → 確認 Bot 自動發文/更新
2. RAG ingestion

### Bahamut 歷史附錄（raw history / appendix）

> 下方保留完整歷史脈絡與細節決策。
> 用途：
> - 回溯脈絡
> - 驗證某項共識的來源
> - 對照舊設計與新設計差異
>
> 但後續 AI **不應直接只往下追加**，應優先更新上方正式知識層。

### Bahamut 目前狀態

<!-- @meta
id: bahamut-state
type: STATE
status: confirmed
depends_on: []
affects: [bahamut-db-schema, bahamut-rag]
last_confirmed: 2026-03-31
-->

**使用者確認（2026-03-29）：**
- 第一版先做「主文 + 主文留言」
- 回文/回文留言延到第二版（第一版僅做可抓性探測與 raw 保存）

**已落地到程式（`src/scraper/services/bahamut_scraper_service.py`）：**
- `cloudscraper + retry` session
- 進版圖 gate 偵測與導頁處理（預熱 + hop）
- 列表抓取（以 `tr.b-list__row.b-list-item` 為主體逐列解析）
- 單篇抓取（含單篇模式 `--sna 16219`）
- HTML + XHR 留言抓取（`moreCommend.php`）
- `post + replies` 結構（以 `section.c-section[id^='post_']` 切 block）
- 主文圖片 `content_images`（已排除回覆區圖片）
- `HOT -> is_hot`、推/噓 icon -> `👍`/`👎`
- `has_thumbsup_button` / `has_thumbsdown_button`
- `is_sticky` 置頂標記
- 列表補抓：`author`/`author_user_id`/`last_reply_user`/`last_reply_user_id`/`category`

**已更新的基礎設施：**
- `src/scraper/config.py` — `BAHAMUT_CONFIG`，預設 `bsn=74934`
- `src/scraper/container.py` — `create_bahamut_scraper_service()`
- `src/scraper/main.py` — `bahamut_scrape_task()`，啟動即執行 + 每小時排程

**目前正在收斂：**
- sample JSON 是否完全符合最新輸出契約
- 主文頂層欄位順序
- `post_id / snA / sn` 最終命名

**單篇抓取模式：**
- `python services/bahamut_scraper_service.py --sna 16219`
- `bsn=74934` 為鳴潮板預設值，沿用設定檔
- 用途：parser 除錯、驗證特定文章圖片/留言/HOT/引用格式

**`post + replies` 已實作進 parser：**
- 以 `section.c-section[id^='post_']` 切文章級 block
- 第一個 block 輸出為 root article（展平成頂層欄位）
- 後續 block 輸出為 `replies[]`
- 不再重複輸出一份巢狀 `post` 物件
- 舊欄位仍暫時保留相容：`content`、`comments`、`comments_count`

**已對齊開發原則的項目：**
- `__init__(db_manager=None)` 已符合
- `fetch_*` 方法命名模式已符合
- `fetch_bahamut_articles_with_content()` 由 service 自行管理 session 已符合
- `container.py` 僅新增 `create_bahamut_scraper_service()` 已符合

**已完成（2026-03-31 ~ 2026-04-01）：**
- `save_articles_to_db(articles)` 已實作（主文 + 回文 + 各自留言）
- `main.py` 已切成正式 `fetch -> save_articles_to_db -> commit`
- `source_type` 已移除（表名已隱含來源）
- DB model 已落地：`BahamutPost`（主文 + 回文共用）+ `BahamutPostComment`（留言獨立表）
- DB upsert 已落地：文章 `(board_id, sn)` / 留言 `(parent_sn, comment_id)`
- 留言 `published_at` 格式已清理（清除「留言時間 」前綴）
- JSON sample 輸出改為設定開關（`config.py` 的 `export_sample_json`）
- `post_id / snA / sn` 命名已收斂：`post_id = snA`，DB unique key 為 `(board_id, sn)`
- GP/BP 數字提取：主文從 `div.gp > a.count` / `div.bp > a.count`，留言從 `a.gp-count[data-gp]` / `a.bp-count[data-bp]`，DB 兩張表都有 `gp_count` / `bp_count`
- 文章多頁遍歷（C.php 分頁）：自動偵測 `p.BH-pagebtnA` 取總頁數，逐頁抓取合併 blocks，跨頁 position 重編
- 列表分頁範圍（B.php）：config 支援 `board_start_page` / `board_end_page`，CLI 支援 `--start-page` / `--end-page`，頁間延遲 `page_delay_range`
- CLI 預設寫 DB（透過 container 注入 db_manager）

**尚未完成：**
- 正式 DB migration（第一版用 `create_tables()` 自動建表）
- 防惡意覆蓋機制（`prev_*` / `content_hash` / `shrink_ratio`）
- RAG / pgvector ingestion

### Bahamut 方法與 JSON 契約

<!-- @meta
id: bahamut-contracts
type: CONTRACT
status: confirmed
depends_on: [bahamut-id-semantics]
affects: [bahamut-db-schema, bahamut-state]
last_confirmed: 2026-03-31
-->

**方法契約：**
- `fetch_board_articles(session)` → `Dict[str, Any]`，至少含 `ok`, `articles`
- `fetch_article_detail(session, url)` → `Dict[str, Any]`，至少含 `ok`, `content`, `comments`
- `fetch_bahamut_articles_with_content()` → `Dict[str, Any]`，至少含 `ok`, `articles`, `detailed_count`
- `save_articles_to_db(articles)` → `int`（saved count）（尚未實作）
- 所有 fetch 方法一律維持 `Dict[str, Any]` + `ok: bool`

**JSON 輸出契約：**
- 主文欄位放**頂層**（含 `snA` 與主文 `sn` 同層）
- 不再重複包一層 `post`
- 回覆文章放在 `replies[]`
- 每個 reply 各自有 `comments[]`
- 主文頂層欄位順序：`post_id -> snA -> sn -> position -> title ... -> comments_count`

**留言欄位契約（新增收斂）：**
- `comment_id`：留言來源識別值，作為留言 upsert 的核心欄位
- `floor`：顯示樓層，允許跳號，不可作唯一鍵
- `position`：本次輸出排序序號，僅供呈現與檢查，不可作唯一鍵
- 若入庫，留言唯一鍵應採：`(parent_sn, comment_id)` 或實作層等價的 `(post_id_fk, comment_id)`

**每個文章級 block 的標準欄位：**
`sn`, `author`, `author_id`, `published_at`, `content`, `content_images`, `comments[]`

### Bahamut ID 語意

<!-- @meta
id: bahamut-id-semantics
type: DECISION
status: confirmed
affects: [bahamut-contracts, bahamut-db-schema]
last_confirmed: 2026-03-31
-->

| ID | 語意 | 來源 |
|---|---|---|
| `snA` | thread / 全文頁 / group ID | URL param、`post2.php` form action |
| `sn` | 單篇文章 ID（本文或回覆文章） | `a[name]`、`section#post_<sn>`、`Co.php?...&sn=` |
| `snB` | 留言 XHR 目標 ID | `Commendlist_<sn>`，高度對應該 block 的 `sn`（持續驗證中） |
| `comment_id` | 單則留言識別值候選 | 留言 DOM id 尾碼 / moreCommend 回傳 HTML 解析 |

來源證據：
- `<a name="117959">` + `<section id="post_117959">` → `sn=117959` 是單篇 ID
- `post2.php?bsn=74934&all=0&snA=16219` → `snA` 是 group/thread ID
- option menu 同時帶 `snA: 16219` + `sn: 118000` → 兩者層級不同

### Bahamut 文章結構判斷

<!-- @meta
id: bahamut-article-structure
type: DECISION
status: confirmed
depends_on: [bahamut-id-semantics]
affects: [bahamut-contracts]
last_confirmed: 2026-03-31
-->

**畫面結構：**
- `section.c-section[id^='post_']` = 一篇文章級 block
- 第一個 block = 本文
- 後續 block = 回覆文章
- 每個 block 底下可能有 `Commendlist_<sn>` = 該 block 的留言區

**HTML 結構證據：**
- 本文/回覆文章都是 `section.c-section` 層級：
  - `<a name="117959"></a><section class="c-section" id="post_117959">...`
  - `a[name]` / `section#post_*` 可作為切分邊界
- 單篇 ID 可由多處取得：`a name="117959"`、`id="post_117959"`、`href="Co.php?bsn=74934&sn=117959&subbsn=15..."`
- `c-reply__editor` 可作為文章區塊結尾的輔助訊號（但不適合單獨當主判斷依據）
- 穩定的切分仍應優先靠：`a[name]`、`section.c-section#post_<sn>`、`Co.php?...&sn=<sn>`

**第一版主文 root 判斷 selector（舊版，已被 block 切分取代但仍有參考價值）：**
- 主文：`.c-article__content`、`.c-post__body`、`#article-content`、`.post-content`、`article`
- 回覆/留言/討論區：`.c-reply__item`、`.reply-content`、`.comment-list`、`.c-post__footer__reply`、`Commendlist_*`
- 重要限制：若巴哈頁面把回覆文章 DOM 混進主文容器內，未來仍可能需要更細的 selector / data attribute 規則

**parser 切分邏輯（新版，基於 block）：**
1. 先以 `section.c-section` 當文章級 block
2. 第一個 block → 主文（展平成頂層）
3. 後續 block → `replies[]`
4. 每個 block 內各自解析 `sn`、`author`、`content`、`images`、`comments`

**每個 block 的留言處理：**
- 本文 block 有自己的留言，每個回覆文章 block 也有自己的留言
- 實作上以該 block 的 `sn` 去找 `Commendlist_<sn>` 與 `snB = <該 block 的 sn>`
- 避免的做法：不要把所有留言都混在主文同一層 `comments[]`、不要把回覆文章打平成和留言同一層級

**主文圖片規則：**
- 先鎖定主文 root
- 排除留言/回覆區節點：`.c-reply__item`、`.reply-content`、`.comment-list`、`.c-post__footer__reply`、`Commendlist_*`
- `content_images` 只保留主文真正內嵌圖片（不可混入回覆文章圖片）
- 圖片從主文 DOM 的 `img` 節點擷取 `src / data-src / data-original`

### Bahamut 留言抓取契約

<!-- @meta
id: bahamut-xhr-comments
type: CONTRACT
status: confirmed
depends_on: [bahamut-id-semantics]
affects: [bahamut-db-schema]
last_confirmed: 2026-03-31
-->

**XHR endpoint:** `https://forum.gamer.com.tw/ajax/moreCommend.php`

**參數：**
| 參數 | 語意 |
|---|---|
| `bsn` | 看板 ID（如 `74934`） |
| `snB` | 留言容器所屬樓層/篇的 ID（不是 `snA`） |
| `returnHtml=1` | 回傳 `{"next_snC":..., "html":[...]}` |
| `snC` | 分頁游標，搭配 `next_snC` 逐頁抓取 |

**實作流程：**
1. 由 `C.php` 解析出所有候選 `snB`
2. 逐一呼叫 `moreCommend.php`
3. 依 `next_snC` 翻頁直到 0

**同一 `snA` 頁面可能有多個留言區，各自不同 `snB`。**

### Bahamut 留言 parser 規則

<!-- @meta
id: bahamut-comment-parser
type: DECISION
status: confirmed
affects: [bahamut-contracts]
last_confirmed: 2026-03-31
-->

**推/噓 icon 轉換：**
- `<i class="material-icons">thumb_up</i>` → `👍`（判斷依據：`onclick="Forum.C.commentGp(this);"` / `class="gp"` / `title="推一個！"`）
- `<i class="material-icons">thumb_down</i>` → `👎`（判斷依據：`onclick="Forum.C.commentBp(this);"` / `class="bp"` / `title="我要噓…"`）
- DOM 判斷優先於純文字 glyph

**保留欄位：**
- `has_thumbsup_button`、`has_thumbsdown_button`（布林）
- `thumbsup_emoji` / `thumbsdown_emoji` 不進正式 JSON/DB（顯示層資料，render 階段臨時映射）

**HOT 標籤：**
- BeautifulSoup 辨識 `<span class="comment_hot-tag">HOT</span>`
- 輸出欄位：`is_hot: true/false`

**已修正的 parser 問題：**
- 舊版 `content` 被錯抓成 `HOT #`、`published_at` 被錯抓成樓層（如 `B12`）
- 修正：新增專用 helper 先移除 `.comment_hot-tag` / floor / time 等 metadata 再取文字
- `published_at` 僅接受真正時間格式
- fallback 文字拆解嘗試解析 `floor` / `user_name` / `published_at`
- 若 DOM 無 `data-userid`，改嘗試從使用者小屋連結反解 `userid`

**留言排序 / 唯一鍵共識（2026-03-31）：**
- `floor` 可能因刪除留言而跳號（如 `B8 -> B10`），不可當唯一鍵
- `position` 會依輸出結果重編，只能做排序序號，不可當唯一鍵
- `comment_id` 允許跳號，但應檢查整體是否大致 asc
- 正式資料層應以 `comment_id` 為留言唯一鍵核心，並綁定父文章作用域

### Bahamut `sn` 抓取策略

<!-- @meta
id: bahamut-sn-extraction
type: DECISION
status: confirmed
depends_on: [bahamut-id-semantics]
last_confirmed: 2026-03-31
-->

`sn` 可能由前端 JS「複製連結」功能組出（`<a data-action="copyLink" href="javascript:;">`），不在靜態 HTML href。

**抓取優先順序：**
1. **先找頁面內嵌資料源**（首選）：搜尋 HTML / inline script 中的 `copyLink`、`data-sn`、`sn:` / `"sn"` 等
2. **再找 DOM data-* 屬性**：`data-sn`、`data-article-sn`、`data-share-url`
3. **最後才考慮 JS 行為還原**：反推 `copyLink` 對應的前端函式。仍優先 HTTP 靜態解析，不先升級瀏覽器自動化

### Bahamut 版本路由策略

<!-- @meta
id: bahamut-routing
type: DECISION
status: confirmed
last_confirmed: 2026-03-31
-->

**決策：維持 desktop HTML first。**

即使 server 回 `302 -> m.gamer.com.tw`，crawler 仍應：
1. 記錄 redirect 事實（保留追因 log）
2. 堅持再請求 desktop forum URL
3. 解析一律以 desktop forum HTML 為主，不改走 mobile API

**手機版強制導向追因：**
- 已在 `_fetch_html()` 加入 debug log，用於釐清 mobile redirect 原因：
  - request start（url / referer / UA / mobile hint / cookies）
  - first response（final_url / status / redirect history / Location / Set-Cookie）
  - desktop retry response（若被導向 mobile，再記錄一次）
- 可能原因：request header/client hints 組合、cookie 狀態、response Set-Cookie 黏 mobile、cloudscraper fingerprint 被判為 mobile

**Redirect 行為測試重點：**
- 觀察 redirect chain（`resp.history`）長度
- 觀察 `Location` 是否反覆在 desktop/mobile 間來回
- 判讀原則：
  - 若每次 desktop request 都只出現單次 302 → mobile，代表 server 穩定拒絕 desktop routing（不是無限 redirect）
  - 若出現 desktop ↔ mobile 反覆跳轉，才算真正的 redirect loop

**進版圖處理：**
- 目標板面：`https://forum.gamer.com.tw/B.php?bsn=74934`
- 機制：巴哈部分看板首次進入會先導到進版圖頁（含「進入看板」按鈕），若 session/cookie 尚未建立，直接抓列表可能拿到進版圖 HTML
- 迴避方式：
  1. 啟動 crawler 時先做預熱請求，檢查是否為 gate page
  2. 若偵測到進版圖，模擬點擊流程建立 cookie/session
  3. 成功進入後保存同一個 session 供後續抓取重用
- 偵測條件：URL/path 含進版圖特徵，或 HTML 包含「進入看板」等關鍵字；若未偵測到文章列表必要 selector，回退判定為 gate page
- gate handling 失敗時記錄 raw html 快照與關鍵 log（url/status/selector 命中率），走有限次重試

### Bahamut 抓取模式與套件

<!-- @meta
id: bahamut-scraping-mode
type: DECISION
status: confirmed
last_confirmed: 2026-03-29
-->

**第一版模式：** HTTP pull + session 持續化 + gate handling

**套件：**
- `cloudscraper`（優先）：處理常見 anti-bot
- `requests`（fallback）
- `BeautifulSoup4`：HTML 解析
- `fake-useragent`：隨機 User-Agent
- `urllib3.Retry + HTTPAdapter`：重試與 backoff

**為何不先上 Playwright/Selenium：**
第一版目標是穩定拿資料與建立欄位契約。HTTP 模式維護成本較低、部署較輕、除錯較快。若後續遇到強 JS 渲染或更嚴格防護，再升級為瀏覽器模式。

### Bahamut 開發原則

<!-- @meta
id: bahamut-dev-principles
type: CONTRACT
status: confirmed
last_confirmed: 2026-03-29
-->

1. **先做 Bahamut 專屬 service，不先硬抽通用框架**
   - 理由：先把 anti-bot / 解析規則跑通，避免過早抽象導致除錯困難
   - 流程比照 PTT：`fetch_list -> fetch_detail -> parse_comments -> 產出標準 payload ->（先 JSON 驗證）-> 再接 DB upsert`
2. **依賴注入**：`__init__(self, db_manager=None)`
   - `config.py` 的 `BAHAMUT_CONFIG` 照現有慣例直接 import
   - 不在 service 內建立 DB session/engine，交由 `container.py`
   - `db_manager` 必須允許為 `None`（方便 JSON-only 測試）
3. **抓取與寫 DB 分離**：`fetch_bahamut_articles_with_content()` 只抓取，`save_articles_to_db()` 只持久化
   - `main.py` 應採：`fetch -> save_articles_to_db -> commit`
4. **normalized + raw 雙軌**
   - normalized：`post_id, title, author, content, published_at, url, comments`（供 API / Discord / RAG）
   - raw：原始 HTML preview / 探測資訊（方便 parser 失效時回溯）
   - 每篇文章需補 `source_type = "bahamut"`
5. **Session 生命週期由 service 自行管理**：`with self._build_session() as session:`
   - 不把 HTTP session 管理外洩到 `main.py` / `container.py`
6. **main.py task 結構比照 PTT**：
   - `container.create_database_tables()`
   - `service = container.create_bahamut_scraper_service()`
   - `result = service.fetch_bahamut_articles_with_content()`
   - `saved = service.save_articles_to_db(result["articles"])`
   - `service.db_manager.commit()`
   - `finally -> close db_manager`

**目前不要做：**
- 不提前抽 base class / ABC
- 不改其他 scraper service
- 不把 gate/cloudscraper 抽到共用 utils
- 不改 `container.py` 既有方法簽名
- 不新增 feature flag

**未來包裝方式：** 以 `BahamutFetchAdapter` 包裝現有 service，因此當前介面需保持乾淨穩定

### Bahamut DB Schema 設計

<!-- @meta
id: bahamut-db-schema
type: CONTRACT
status: confirmed
depends_on: [bahamut-contracts, bahamut-id-semantics, bahamut-xhr-comments]
affects: [bahamut-rag]
last_confirmed: 2026-03-31
-->

**SQLite vs PostgreSQL 決策：**
- 目前 PTT/FB/article 那批 scraper 資料表本質上走 **SQLite**（不可誤以為在 pgvector/PostgreSQL 裡）
- 第一階段先用 **SQLite**（與現有 scraper 層一致）：
  - migration / model / database manager 可直接沿用既有模式
  - 不會提早把 Bahamut 綁進 AI / vector 基礎設施
- 若 Bahamut 很快要進 RAG / 多條件查詢 / 跨來源整合查詢，才考慮直接進 PostgreSQL + pgvector
- 等資料結構穩定後再同步到 PostgreSQL + pgvector（或讓 RAG ingestion 從 SQLite 讀出後寫入 pgvector）

**設計原則：**
1. Bahamut 使用獨立資料表，不改動既有 `article_* / fb_* / ptt_*` 表
2. 先做關聯式正規化 + raw 備份欄位，向量索引不直接塞在這批表裡
3. pgvector 後續 ingestion 時，從 Bahamut 表讀資料再寫入向量層；不要把 scraper 主表直接和 embedding schema 綁死
4. migration 一律採 Alembic，單一檔案只做一個清楚主題

**第一版資料表（已落地 2026-03-31）：**

**`bahamut_posts`（主文 + 回文共用表，以 `position` 區分）：**
`id` PK, `board_id`(`bsn`), `post_id`(`snA`, thread 分群), `sn`(單篇 unique ID), `position`(1=主文, >1=回文), `title`, `category`, `author_name`, `author_id`(indexed), `url`, `ip`, `area`, `published_at`(indexed), `content`, `content_images_json`(JSON array), `comments_count`, `replies_count`, `raw_json`, `last_seen_at`, `created_at`, `updated_at`
- unique: `(board_id, sn)`
- index: `post_id`（查 thread）, `author_id`（查作者文章）, `published_at`

**`bahamut_post_comments`（留言表，主文 + 回文留言共用）：**
`id` PK, `bahamut_post_id` FK -> `bahamut_posts.id`(indexed), `parent_sn`(留言所屬文章 block 的 `sn`), `comment_id`, `floor`, `position`, `user_id`(indexed), `user_name`, `content`, `is_hot`, `published_at`, `raw_text`, `created_at`, `updated_at`
- unique: `(parent_sn, comment_id)`

**與先前規劃的差異：**
- 主文與回文共用一張表（不再分 `bahamut_reply_posts`），靠 `position` 區分
- 移除 `source_type`（表名已隱含來源）
- 移除第一版不需要的欄位：`prev_*`、`content_hash`、`update_blocked`、`discussion_hash`、`snapshot_json`、`parser_version`、`last_comment_sync_at`
- 留言移除 `content_hash`、`source`、`raw_json`（第一版簡化）

**`bahamut_sync_runs`（可選但推薦）：**
`id`, `source_type`, `started_at`, `finished_at`, `status`, `articles_seen`, `articles_saved`, `comments_saved`, `notes`

**第一版不建議先建：** `bahamut_post_revisions`（完整歷史表可後置）；`bahamut_reply_posts` / `bahamut_reply_comments` 可待主文留言契約完全穩定後再拆

**索引：**
- `bahamut_posts`: `post_id`(unique), `root_sn`, `board_id`, `author_id`, `published_at`, `last_comment_sync_at`, `content_hash`
- `bahamut_post_comments`: `(parent_sn, comment_id)`(unique), `post_id_fk`, `user_id`, `published_at`, `content_hash`, `floor`

**文章版本保留（雙版本方案）：**
- 主表保留最新版 + 上一版本（`prev_*` 欄位），不要一開始就拆完整版本歷史表
- 更新規則：
  1. 每次重抓文章時先算新的 `content_hash`
  2. 若 hash 與目前主表相同 → 視為未編輯，只更新 `last_seen_at`
  3. 若 hash 與目前主表不同 → 先把「目前最新版」搬到 `prev_*`，再把新內容寫進正式欄位
- 效果：永遠保留最新版本 + 上一個版本，結構簡單、查詢容易不需 join
- 缺點（可接受）：只保留 2 個版本，多次編輯最舊版本會被覆蓋
- 若未來需要完整歷史，再升級成 `bahamut_post_revisions` 歷史表（目前不建議第一版就上）

**防惡意覆蓋規則：**
- 每次更新前先比較：`shrink_ratio = new_len / old_len`
- 預設允許正常更新條件：`new_hash != old_hash` 且 `shrink_ratio >= 0.7`
- 取消覆蓋條件：`old_len >= 500` 且 `shrink_ratio < 0.5`，或 `new_len < 100`（幾乎清空）
- 被阻擋時的處理：
  - 不更新 `content`、不滾動 `prev_*`
  - 只寫入：`last_seen_at`、`update_blocked = true`、`update_block_reason = 'suspicious_massive_shrink'`、`blocked_content_snapshot`
- 可選第二層條件：新內容必須同時包含最低字數門檻 + 至少一段正文 selector 命中，若只剩空殼 DOM / 少量殘字也視為阻擋
- 原則：**正式欄位只接受「正常變更」，異常縮水版本只記錄、不覆蓋**

**入庫去重/增量更新：**
- 文章：`source=bahamut + post_id(snA)` 做 upsert
- 留言以 `parent_sn + comment_id` 做 upsert：
  - 已存在：更新內容、時間、熱門標記、raw_text
  - 不存在：新增
- 文章額外維護：`comments_count`、`last_seen_at`、`last_comment_sync_at`
- 若新抓取留言數 > 舊留言數，視為動態更新成功
- 動態更新策略：
  - 針對最近活躍文章定時重抓
  - 若 `comments_count` 持續增加，保留在高頻同步名單
  - 若連續多次無變化，再降頻

**migration 命名與紀錄原則：**
1. 一個 migration 做一件事，例如：
   - `20260331_0135_add_bahamut_posts_table.py`
   - `20260331_0145_add_bahamut_post_comments_table.py`
   - `20260331_0155_add_bahamut_post_guard_fields.py`
2. revision docstring 必須寫清楚：做了什麼、為什麼要做、`Revises` 接哪個版本
3. 每個 migration 必須有完整 downgrade
4. 若是「欄位新增」與「索引新增」可分開 migration，方便出問題時局部回退
5. migration 檔名與 revision id 都應可由人直接辨識，不要只用模糊名稱
- 執行順序：`bahamut_posts` → `bahamut_post_comments` → version/guard 欄位 → sync_runs

**與 pgvector 共存：**
- Bahamut 關聯表 = 來源真實資料層
- RAG 時從這些表讀出 → chunk → 寫入獨立 vector 表
- metadata 帶 `source_type`, `post_id`, `comment_id`, `board_id`, `published_at`

### Bahamut Discord 呈現策略

<!-- @meta
id: bahamut-discord-display
type: DECISION
status: confirmed
depends_on: [bahamut-db-schema]
last_confirmed: 2026-04-02
-->

**核心原則：1 snA = 1 Discord Forum Thread，主文 + 回覆共存同一 thread。**

#### 通知機制（Scraper → Bot）

- Scraper 與 Bot 分屬不同資料庫（Scraper: SQLite / Bot: pgvector），**無法使用 PG NOTIFY**
- 改用 **HTTP webhook**：Scraper 寫完 DB 後 POST `http://discord-bot:5000/notify/bahamut`
- Payload 只帶辨識 ID（如 `board_id`、`post_id`），Bot 收到後回呼 Scraper API 拿完整資料
- Bot 端用 `aiohttp.web` 起輕量 HTTP server，日後可擴充其他 source 的 notify

#### Thread 結構

```
Forum Thread: 【心得】文章標題
├─ 📄 主文 embed（藍色）                     ← create_thread 首則
├─ 💬 主文留言 embed 1（灰色，預建）          ← edit 更新
├─ 💬 主文留言 embed 2（灰色，預建）          ← 格1滿了接這
├─ 💬 主文留言 embed 3（灰色，預建）          ← 格2滿了接這
├─ ↩️ 溢出留言（reply to 留言格3）            ← 格3滿了，追加
│
├─ 📝 回覆 #2 embed（綠色）
├─ 💬 回覆#2 留言 embed 1~3（灰色，預建）
│   ...
```

#### Embed 格式

- 全部使用 **embed**（description 上限 4096 字元，比純文字 2000 更大）
- 主文：藍色 embed，含作者、分類、GP/BP、連結、內文
- 回覆：綠色 embed，含回覆者、GP/BP、內文
- 留言格：灰色 embed，格式如下：

```
🔥 `B1` **super** 👍107 — 留言內容
`B2` **某某某** 👍5 — 推推
`B3` **路人甲** — 普通留言（GP=0 不顯示）
`B4` **另一位** 👍3 👎1 — 有 BP 的情況
```

規則：🔥 只在 is_hot=true / 👍 只在 gp>0 / 👎 只在 bp>0 / 不顯示留言時間

#### 留言格管理

- 每個文章 block（主文或回覆）預建 **3 格**留言 embed
- 留言切割以 **整則留言為單位**，塞不下就放下一格，不切斷單則留言
- 3 格都滿後溢出：`send(reference=格3_msg_id)` 追加新訊息
- 溢出訊息也用 **edit 重組**，塞滿才開新的溢出訊息
- GP/BP 隨每次更新同步 edit 主文/回覆 embed

#### 狀態追蹤（sent_articles.json）

```python
"sent_bahamut_state": {
    "bahamut:74934:16219": {           # bahamut:{board_id}:{snA}
        "thread_id": 111111,
        "posts": {
            "117959": {                # sn（主文）
                "msg_id": 222222,
                "comment_slots": [
                    {"msg_id": 333333, "used_chars": 3900},
                    {"msg_id": 333334, "used_chars": 4050},
                    {"msg_id": 333335, "used_chars": 4000}
                ],
                "overflow_anchor": 333335,
                "overflow_slots": [
                    {"msg_id": 444444, "used_chars": 3800},
                    {"msg_id": 444445, "used_chars": 1200}
                ],
                "synced_comment_ids": ["3935219", "3935220", ...]
            },
            "117960": { ... }          # sn（回覆）
        }
    }
}
```

#### 更新邏輯

1. 新 thread → create + 主文 embed + 預建 3 格留言 embed → 記錄所有 msg_id
2. 新回覆 → append 回覆 embed + 預建 3 格留言 embed
3. 新留言 → 找到對應 sn 的 comment_slots → 找第一個未滿 slot → **重組整個 slot 內容** → `message.edit()`
4. 留言溢出 → reply 第三格 msg_id → 溢出訊息也是 edit 重組，滿了才開新的
5. GP/BP 更新 → edit 主文/回覆 embed

### Bahamut 作者查詢能力

<!-- @meta
id: bahamut-author-query
type: DECISION
status: confirmed
depends_on: [bahamut-db-schema]
last_confirmed: 2026-03-31
-->

可依 `author_id` / `user_id` 查詢：
1. 某作者發過哪些主文（`bahamut_posts.author_id`）
2. 某作者留過哪些留言（`bahamut_post_comments.user_id`）
3. 應用層合併成單一作者活動紀錄

索引第一版就該加：`bahamut_posts.author_id`、`bahamut_post_comments.user_id`

注意：若頁面抓不到穩定 `user_id`，至少保留 `user_name`，但查詢主鍵仍以 `user_id` 優先。

### Bahamut 風險

<!-- @meta
id: bahamut-risks
type: RISK
status: confirmed
last_confirmed: 2026-03-31
-->

1. `snB == sn` 目前高度吻合，但仍應視為持續驗證中
2. 若 HTML 結構再變，`section.c-section` / `Commendlist_*` selector 有風險
3. `comment_id` 雖目前最適合當留言唯一鍵核心，但仍需在更多 sample 中持續驗證其穩定性

### Bahamut TODO

<!-- @meta
id: bahamut-todo
type: TODO
status: confirmed
last_confirmed: 2026-04-02
-->

**當前待辦：**
1. 端到端測試：重啟兩容器後等 Scraper 自動抓取 → 確認全自動閉環
2. RAG ingestion（不急）

**現在不該優先做：** 不要先抽象過度泛化 base class

#### 第一階段 MVP + 第二階段 DB — ✅ 已完成，歸檔至 `TODO-completed.md`

#### 剩餘待辦（第二階段）

- [ ] 規劃增量同步欄位（`discussion_hash`、`last_comment_sync_at`、`last_reply_sync_at`）
- [ ] 預留 moderation 欄位
- [ ] 驗證 Discord bot 後續取用資料時的查詢效率

#### 第三階段：整合 AI / pgvector / RAG

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
- 第一階段 MVP ✅ 已完成
- 第二階段 DB ✅ 大部分完成（剩餘 moderation / 增量同步欄位）
- [ ] 第二階段穩定後再做第三階段 RAG
- [ ] 每階段保留 JSON 範例與測試案例

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
