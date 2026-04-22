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
- 2026-04-07：FB 貼文改推送模式 + 圖片 URL 刷新機制（詳見跨來源整合專區）。
- 2026-04-18：Context/Prompt 完整重構 + askai 身份感（2026-04-15 ~ 2026-04-18 整串工作）全數歸檔至 `TODO-completed.md`，包含 on_message 持久化、自動人格萃取、LLM 服務穩定性修復、askai 排隊顯示修正、Bahamut 主文 `author_id` 修復、Bahamut 增量更新 429 治本（per-message 冷卻）、askai 發問者身份注入（asker_profile + 撞名偵測 + persona 拆分 + safety rules 修飾）。
- 2026-04-18：新增主線「Reaction 統計與社群互動玩法」TODO，規劃 Phase 1 基礎統計（/askai 整合前置）→ Phase 2 askai 整合（殺手級應用）→ Phase 3 強化人格萃取。詳見對應區塊。
- 2026-04-18：點歌機器人與幽靈點名系統的架構、設計決策、已實作功能、音訊鏈路、管理面板、使用方式等完整內容歸檔至 `TODO-completed.md`；handoff 僅保留專區錨點 + 未完 TODO（音樂 P1/P2、點名部署驗證 + P1）。
- 2026-04-18：/askai 效能調優三連。①context 量上調（`max_context_to_send` 20→50、`min_recent_context` 15→25、`max_relevant_context` 14→25），覆蓋典型 ~50 則討論。②Plan C：`_build_vector_rank` 改查持久化 pgvector（既有 `chat_persistence` 寫入端），/askai 的 embed 呼叫從「100 則 in-memory」降到「1 次問題」。③修 BM25 tokenization TF bug（`tokenize_for_retrieval` 回傳 `set`→`list`），保留重複 token 讓 BM25 能用詞頻。附帶清掉無用的 in-memory VectorStoreIndex LRU cache。`_EMBED_CONCURRENCY` 2→1 對齊 server 端 `OLLAMA_NUM_PARALLEL=1`，避免 AMD Vulkan KV cache 倍增風險。音樂機器人播音斷斷續續的根因是 default ThreadPoolExecutor 被 BM25+embedding 佔用 + GIL 爭用，此三項改動後預期大幅緩解。
- 2026-04-19：Ollama chat 呼叫統一化 Stage 1 完成。`OllamaService` 新增 `chat_raw()` 底層方法（純 HTTP + payload 組裝，raise `OllamaAPIError` / `aiohttp.ClientError`），`generate_reply()` 改為高階封裝（prompt bundle + context 注入 + 錯誤字串化）；`chat_raw` 新增 `timeout` 參數讓 caller 覆蓋預設。`personality_extractor.extract_personalities` 從自寫 aiohttp 遷移到 `service.chat_raw(timeout=600, num_ctx=32768, temperature=0.3, top_p=0.8)`，消除唯一一處 /api/chat 重複實作。附帶修掉「Ollama 呼叫發生未預期錯誤: （空字串）」log 診斷困難（加 `type(exc).__name__`，例：`TimeoutError: `）。
- 2026-04-19：`chat_raw` / `generate_reply` 新增 `keep_alive` 參數，caller 按用途傳不同值。/askai 傳 `"1h"`（連續互動期間 chat model 常駐）、moderation 傳 `"30m"`（間歇性任務）、personality_extractor 傳 `"30m"`（4am 排程跑完 30 分鐘後釋放）。payload 策略：caller 明確傳值才加 `keep_alive` 欄位，否則沿用 server 端全域 `OLLAMA_KEEP_ALIVE`，不覆蓋；embed 模型目前還是走 server 全域設定（沒動 LlamaIndex 層），待後續需要時再做 Stage 2。
- 2026-04-19：社群 ID 查詢 Phase 0 Step 2~5 實作完成（Step 2 state_db 新表 + CRUD、Step 3 `services/community_lookup_service.py` 查詢核心、Step 4 `commands/community_lookup_commands.py` Panel/Modal/Flow/日期 hybrid section 管理、Step 5 `/server_manager` 頻道選項 + 自動部署 + `discord_bot.py` COMMAND_MODULES 掛載）。所有 smoke test 通過（CRUD、真實 DB 查詢、cog 實例化 + persistent views 註冊、Modal children 結構、embed 格式）。Step 6 部署驗證待使用者執行。涉及新檔：`src/services/community_lookup_service.py`、`src/commands/community_lookup_commands.py`、`src/scripts/bench_ptt_comment_lookup.py`；涉及改動：`src/services/state_db.py`、`src/commands/management_commands.py`、`src/discord_bot.py`。未動 scraper DB schema。
- 2026-04-19：社群 ID 查詢 Phase 0 Step 1（JSON1 效能驗證）完成。`src/scripts/bench_ptt_comment_lookup.py` 對現有 `articles.db`（810 篇 / 39,890 留言 / 367 MB）實測，全部 query p95 < 30ms，遠低於 500ms 判準。意外收穫：`ix_ptt_posts_published_at` 早已存在（scraper models.py `published_at=Column(..., index=True)`），EXPLAIN QUERY PLAN 顯示 SQLite 已先走時間 index 縮小範圍再做 `json_each`，所以 `idx_ptt_author` 完全不必加，原定的 PTT index migration 取消 — scraper DB schema 零變更。
- 2026-04-19：新增主線「社群 ID 查詢（PTT / 巴哈）」，架構已定案（status: draft）。核心概念：`/server_manager` 設定「社群查詢頻道」→ 面板兩顆按鈕（查 PTT / 查巴哈）→ Modal 填目標帳號 + 範圍 Select（7/15/30/60/90/180，預設 30）→ 每個 `(source, lookup_id)` 建立唯一 public thread（命名 `[PTT] JohnDoe` / `[巴哈] 小明 (ABC123)`，auto-archive 7 天）→ 結果 append 模式「日期 hybrid」（同日 edit、跨日 append 新 section）→ 父頻道發公開通知 + bump panel。PTT 走 SQLite JSON1（零 migration，只加 `idx_ptt_author` / `idx_ptt_published_at`），巴哈走 ORM。保底 100 留言 / 20 主文（區間內不足補區間外），hard cap 1000 筆/來源。Phase 0 Step 1 將先跑 JSON1 效能驗證 script 後再動正式 code。詳見[社群 ID 查詢專區](#社群-id-查詢專區)。
- 2026-04-19：Ollama 穩定性與 VRAM 優化兩連。①`chat_raw` 自動重試：檔頭新增常數 `OLLAMA_MAX_ATTEMPTS=2` / `OLLAMA_RETRY_DELAY=3.0` / `OLLAMA_RETRY_STATUS_CODES={500,502,503,504}`，HTTP 區塊改 2-attempt 迴圈，每次建立新 ClientSession + ClientTimeout 讓 timeout 自動重置；會重試 500/502/503/504 + asyncio.TimeoutError + aiohttp.ClientError，**不重試** 4xx 與回應格式異常。觸發背景：17:14 出現 `500 model runner has unexpectedly stopped`，使用者確認 VRAM 還剩 20GB 排除 OOM，判定為 Ollama runner 暫時性崩潰。②`SafeOllamaEmbedding` 預設注入 `num_ctx=8192`：Ollama VRAM-based 預設 32768 讓 0.6B embedding 吃 5.7GB VRAM（KV cache ~3.5GB 預分配但用不到），調成 8192 後 KV cache 降到 ~880MB，省 ~2.6GB。實作方式：檔頭常數 `_EMBED_NUM_CTX=8192` + `__init__` 覆寫把 `num_ctx` 塞進 `ollama_additional_kwargs`，caller 仍可覆寫；三個 call site（chat_persistence / intro_rag_port / context_retriever）一行都不用改（context_retriever 早已用 `SafeOllamaEmbedding as OllamaEmbedding` alias）。③澄清：人格萃取排程本來就會自動寫 RAG（`run_personality_extraction` 預設 `write_rag=True`，排程 caller 沒傳 False），無需改動；現況語意 = 排程自動 / 手動人審。④embedding 長度稽核：所有 call site 最大輸入 ~4200 字元（Discord 訊息上限），用掉 8192 token 的 51%，有 2 倍 buffer；intro/impression/personality 都有 modal `max_length` 或程式常數硬限制；未來 Bahamut / Article 若需 embed 長文應先切 chunk，不是調大 num_ctx。
- 2026-04-22：研究紀錄「X.com / Twitter 影片嵌入原理」歸檔至[跨來源整合專區](#xcom-twitter-影片嵌入研究2026-04-22)。結論：Discord bot（ermiana 等）靠替換 `x.com` → `fxtwitter.com` / `fixupx.com` / `vxtwitter.com` 讓 Discord unfurler 讀到 `og:video` meta 即可直接播放，背後是 X 免費但無保證的 Syndication API（`cdn.syndication.twimg.com/tweet-result`），只能單篇 tweet lookup、無搜尋能力；若本專案未來要加 x.com 來源，最簡單做法是 `on_message` domain replace（一小時可完工），搜尋/timeline 則需付費 v2 API。本輪無 code 異動。
- 2026-04-23：DM 通知模組抽出 + 音樂面板收藏按鈕。①新增 `src/utils/dm_notifier.py`（系統模組層，與 `logger_config.py` 同層），提供 `resolve_user`（user_id → User/Member，`guild.fetch_member` → `bot.fetch_user` → `bot.get_user` → `guild.get_member`）、`send_dm`（底層發送，吃掉所有例外，回 bool）、`notify_keyword_hit`、`notify_song_liked` 四個函式，所有 discord DM 發送的共通 user resolution + 例外處理集中於此。②`commands/user_commands.py` 的 keyword 監控命中段（原 ~60 行 user resolution + embed + try/except）縮到 `await notify_keyword_hit(self.bot, user_id, message, found_keywords, guild=message.guild)` 一行。③`music/announcer.py` 的 `MusicControlView` 第一排加入 `⭐ 收藏` Secondary 按鈕（順序：點歌 → 歌單 → 收藏），按下後寄 DM 給按鈕觸發者（含歌名、長度、YT 連結、縮圖、語音頻道），`custom_id="music_favorite"` 可持久化；失敗給 ephemeral 提示「你的私訊已關閉」。④純 DM 無記檔、無 de-dup（按幾次寄幾次，符合 MVP）。附帶整理：`src/services/migrate_json_to_sqlite.py` 搬到 `src/scripts/`（用 `git mv` 保留歷史，與 `migrate_emoji_text_format.py` / `reembed_pgvector.py` 同性質），docstring 執行路徑同步更新。

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
| Discord Bot / AI 對話能力 | 已有可用基礎能力 | 75% | [專案架構](#專案-ai-架構總覽) |
| Context / Prompt 優化 | 已實作（含 askai 身份感），待部署驗證 | 95% | [Context 優化](#context--prompt-優化專區) |
| Reaction 統計 / 社群互動玩法 | 規劃中 | 5% | [Reaction TODO](#reaction-統計與社群互動玩法) |
| 點歌機器人（Music Bot） | 已上線運作 | 85% | [點歌機器人](#點歌機器人專區) |
| 跨來源整合（Article/FB/PTT/TG） | 有方向，尚未全面收斂 | 35% | [跨來源整合](#跨來源整合專區) |
| Bahamut RAG / AI 整合 | 尚未開始 | 5% | [RAG TODO](#第三階段整合-ai--pgvector--rag) |
| 幽靈點名系統（Roll Call） | 已實作，待部署驗證 | 80% | [幽靈點名](#幽靈點名系統專區) |
| 社群 ID 查詢（PTT / 巴哈） | Phase 0 Step 1~5 實作完成，待部署驗證 | 85% | [社群 ID 查詢](#社群-id-查詢專區) |
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

---

## Context / Prompt 優化專區

<!-- @meta
id: context-prompt-optimization
type: TODO
status: confirmed
depends_on: [project-architecture]
affects: [product-todo]
last_confirmed: 2026-04-19
-->

> **目標：** 提升 bot 的群聊參與感與個性表現，讓回覆更自然、更有記憶感。

### 已完成（2026-04-15 ~ 2026-04-18）

> 詳細項目已歸檔至 `TODO-completed.md` 的「Context/Prompt 完整重構 + askai 身份感（歸檔 2026-04-18）」。
> 摘要：context/prompt 格式重構、貼圖描述、on_message 持久化、自動人格萃取 pipeline、/askai 體驗優化（timeout / 抓取量 / 取消 / 排隊顯示）、LLM 服務穩定性修復（SafeOllamaEmbedding + HTTP 連線重用 + thread-safety）、/askai 發問者身份注入（`<asker_profile>` + `<latest_user_message from=...>` + persona 拆分 + 撞名偵測 `#xxxx` + safety rules 修飾）。

### 待處理

- [ ] System prompt 禁忌清單精簡（待定案）
- [ ] `/personality_extract` 的「寫入 RAG」改為背景 task：按鈕按下後先立即回應，避免 interaction 長時間停在 loading。（目前仍在前景等完，但已加進度訊息降低體感不安。）
- [ ] 若背景寫入超時或 followup 失敗，規劃 fallback（例如 DM 或至少補 log / 狀態查詢入口）。
- [ ] 為 `save_personality_results()` / `index_auto_personality()` 補上逐筆或批次成功 log 與耗時統計，方便判斷卡點是在 embedding、delete、還是 pgvector insert。
- [ ] `asker_profile` 的 `roles` 欄位目前為 `(未啟用)`，未來視需求再填：可選混合 Discord 身份組名稱 + 權限層級（admin/moderator/member）。
- [ ] 部署後觀察 /askai 回覆是否正確認出發問者；若發現「撞名誤判」或 `asker_profile` 洩漏 user_id 等問題，回到 prompt/safety rules 調整。
- [ ] **Windows Ollama server 待調整**（使用者本機設定，AI 無法直接改）：`OLLAMA_KEEP_ALIVE=24h`（原 5m，每 5 分鐘反覆 unload/reload 是 Windows `wsarecv` / ephemeral port 耗盡主因）。`OLLAMA_MAX_LOADED_MODELS=2` 已設好（chat + embed 各一條 runner）、`OLLAMA_NUM_PARALLEL=1` 已設好。改完重啟 Ollama 後驗證 `server.log` 不再出現 5 分鐘一次的 `load request`。AMD 顯卡維持 `OLLAMA_VULKAN=true`。
- [ ] 觀察 /askai 執行時音樂機器人是否還會斷音。Plan C + `_EMBED_CONCURRENCY=1` 後理論上 default ThreadPoolExecutor 爭用大幅下降；若仍斷音，考慮將 BM25/embedding 隔離到獨立 ThreadPoolExecutor（治標），或改 `ProcessPoolExecutor` 脫離 GIL（治本但 IPC overhead 高）。
- [ ] **部署驗證 Ollama 重試邏輯**（2026-04-19 實作）：重啟 discord-bot 後觀察 `[WARNING] Ollama 第 1 次呼叫失敗（...），3.0s 後重試` log 是否按預期出現、使用者端 500 錯誤是否消失。
- [ ] **部署驗證 embedding num_ctx=8192**（2026-04-19 實作）：重啟 discord-bot 觸發一次 embed（如 /askai），然後 `curl http://192.168.56.1:11434/api/ps` 確認 `qwen3-embedding:0.6b` 的 `size_vram` 從 ~5.7GB 降到 ~3.1GB。
- [ ] **/askai 指定 thread 查詢（新議題，未開工）**：使用者提問能否讓 askai 看某個 thread 的貼文評論。現況結論：情境 A（人在 thread 內 `/askai`）已支援；情境 B（在他處指定 thread）不支援，因 slash command 無 thread 參數 + pgvector metadata 無 `thread_id` / `parent_id`。兩方案待選：Minimum 版（加 thread 參數 + retriever 吃 thread.history，3 處以內改動）/ 完整版（Minimum + chat_persistence 寫 thread_id + RAG 查詢加 thread 過濾，需 migration）。AI 建議先 Minimum 版。使用者尚未選。

### 設計決策備忘

**Persona Card 資料來源與合併：**

| profile_kind | 來源 | 更新方式 |
|---|---|---|
| `intro_profile` | 使用者 `/intro` | 手動 |
| `impression` | 群友 `/impression` | 手動 |
| `auto_personality` | LLM 批次萃取 | 每日自動覆蓋 |

卡片標題 alias 優先級：intro_profile > impression > auto_personality
卡片內容顯示：自介 → 印象 → AI觀察

**萃取 Pipeline 架構：**
```
每日 04:00 UTC+8
    ↓ pgvector SQL 撈最近 14 天聊天
    ↓ 按 author_id 分組（≥10 則才分析）
    ↓ 反查 display_name（guild member 優先 → DB alias fallback）
    ↓ 清理噪音（emoji 字典替換、移除 URL/mention）
    ↓ 每批 4 人送 qwen2.5:14b
    ↓ 寫入 auto_personality:{guild_id}:{user_id}（覆蓋式）
```

**手動人格萃取 UI / 寫入流程現況（2026-04-17 確認）：**
- `/personality_extract` 啟動訊息與「查看結果」按鈕為 ephemeral；結果分頁與「寫入 RAG / 捨棄」按鈕也為 ephemeral。
- 「寫入 RAG」按下後目前會先把原 ephemeral 訊息改成 `⏳ 正在寫入 RAG...`，再同步執行整個寫入流程；完成後才 followup 一則 `✅ 已寫入 RAG：X 筆`。
- 若改成背景 task，使用者偏好方案是：**額外發一筆新的 ephemeral** 當作「已開始寫入 / 完成通知」，而不是只 edit 原本那筆。
- 風險提醒：新的 ephemeral followup 仍受 interaction token / webhook 時效限制，不適合無上限超長任務；若要更穩，後續仍需保留 fallback 機制。

**涉及檔案（設計參考）：**

完整檔案清單見 `TODO-completed.md` 對應歸檔。重要入口：

| 檔案 | 角色 |
|---|---|
| `src/services/llm_service.py` | prompt bundle、`asker_profile` 參數、generate_reply |
| `src/commands/llm_commands.py` | context 分離、asker_profile 組裝、撞名偵測 |
| `src/llm/persona_card_builder.py` | 自然語言化、`person_id` 保留 |
| `src/llm/context_retriever.py` | discord_context item（含 `display_name`）、vector index cache |
| `src/llm/chat_persistence.py` | buffer 批次寫入、SafeOllamaEmbedding |
| `src/llm/personality_extractor.py` | 人格萃取 pipeline |
| `src/llm/intro_rag_port.py` | `index_auto_personality`、`_ainsert`、singleton |
| `src/settings/prompts/askai_system_prompt.txt` | 人設 prompt |
| `src/settings/prompts/llm_context_safety_rules.json` | untrusted intro + asker_profile 白名單 |

---

## Reaction 統計與社群互動玩法

<!-- @meta
id: reaction-stats-todo
type: TODO
status: draft
depends_on: [project-architecture]
affects: [product-todo, context-prompt-optimization]
last_confirmed: 2026-04-18
-->

> **目標：** 用 Discord reaction 統計把群內互動量化，餵回 `/askai` 與人格萃取，讓 bot 更有「社群感」。

### 現況
- `intents.reactions = True` 已開（`src/discord_bot.py:43`）
- 僅 `src/commands/forum_monitor.py:123` 在監聽 `on_raw_reaction_add`（論壇管理用途）
- **尚無任何「某 user 的訊息被按了多少表情」的累積統計**

### Phase 1 — 基礎統計 + 公開玩法（共用一組 DB）

- [ ] 在 `discord_bot.py` 註冊全域 `on_raw_reaction_add` / `on_raw_reaction_remove` 監聽
- [ ] `state_db` 新增 `message_reactions` 表：欄位至少含 `message_id`, `message_author_id`, `guild_id`, `channel_id`, `emoji`, `reactor_id`, `added_at`；索引 `(message_author_id, emoji)`、`(message_id)`
- [ ] 排除機器人自己按的 reaction（避免污染）
- [ ] emoji normalize：unicode emoji vs custom emoji（`<:name:id>`）統一比對鍵
- [ ] **每週金句頒獎**：排程每週日發佈過去 7 天 top 3 reacted 訊息到指定頻道
- [ ] **神級發言名人堂**：訊息 reaction 數達門檻（預設 10）自動複製到 `#hall-of-fame` 頻道
- [ ] **個人招牌 emoji**：新增 `/my_emoji` 查被按最多的 emoji、top N 送反應的人

### Phase 2 — /askai 整合（殺手級應用）

- [ ] `_handle_askai_request` 查詢 asker 近 N 天 reaction 熱點（top 1~3 熱門發言 + 招牌 emoji）
- [ ] 在 `asker_profile` 下方新增 `<asker_recent_highlights>` 區塊餵給 LLM
- [ ] LLM 能自然帶出「你上週說的那句 XXX 大家反應很好」等社群感回答
- [ ] 記得 safety rules 中標為「可信」並提醒不要直接引述完整原文以免尷尬

### Phase 3 — 強化人格萃取

- [ ] `personality_extractor` prompt 餵入該使用者的 reaction-received 模式（常收到哪類 emoji → 推論人格面向）
- [ ] 設計加權規則：例如收到 🤣 多 → 加權「幽默感」；收到 😢 多 → 加權「共感」
- [ ] 跟 `emoji_dictionary.txt` 聯動，把 emoji 語意轉成自然語言特徵

### 設計備忘

- **歷史回補**（批次掃 `channel.history()` 抓既有 reaction）**不納入 Phase 1**；先跑一段時間累積自然資料，有需要再做
- Discord 只會回傳「目前還存在的 reaction」，撤回的無法回補
- 大群 `channel.history` 有 rate limit，需批次 + 退避
- 隱私：使用者退群後的 reaction 記錄保留政策待定（預設保留，需評估）
- reaction vs /askai 整合可能加 context token 成本，需在 Phase 2 實測並設上限

### 建議實作順序

**先 Phase 1 全做完**（事件收集 + DB + 三個玩法）→ **再 Phase 2**（用 Phase 1 累積資料 + askai 整合）→ **最後 Phase 3**（人格萃取加權）。
Phase 1 三個玩法**共用同一張 DB**，不要拆開做。

### 涉及檔案（預估）

| 檔案 | 角色 |
|---|---|
| `src/discord_bot.py` | 註冊 reaction 事件監聽 |
| `src/services/state_db.py` | 新增 `message_reactions` 表 + 查詢 API |
| `src/services/reaction_stats_service.py`（新增） | 聚合查詢、排程邏輯 |
| `src/commands/reaction_commands.py`（新增） | `/my_emoji`、每週金句公告 |
| `src/commands/llm_commands.py` | Phase 2：組 `asker_recent_highlights` |
| `src/llm/personality_extractor.py` | Phase 3：萃取時加權 reaction 訊號 |

---

## 社群 ID 查詢專區

<!-- @meta
id: community-lookup
type: TODO
status: draft
depends_on: [project-architecture]
affects: []
last_confirmed: 2026-04-19
-->

> **目標：** 讓使用者在 Discord 上輸入 PTT 帳號或巴哈 ID/名稱，查出該 ID 在兩站的發文與留言紀錄，並把結果做成可追蹤的 thread（每 ID 一個 thread，像搜尋庫）。

### 核心設計（已定案）

**1. 入口與頻道設定**
- `config.json` 新增 `community_lookup_channel_id`
- 走既有 `/server_manager` 下拉選單設定（仿 `intro_channel_id` 同構），設定瞬間自動部署 panel
- 無獨立 slash command；所有互動走面板按鈕

**2. Panel（父頻道常駐）**
- 兩顆按鈕：🔍 查 PTT / 🎮 查巴哈
- 永續 View（`timeout=None`）；`setup_hook` 呼叫 `add_view(CommunityPanelView())`
- 每次查詢後 bump（刪舊發新，維持在父頻道最底）

**3. Modal**
| 欄位 | 查 PTT | 查巴哈 |
|---|---|---|
| 帳號輸入 | TextInput：PTT 帳號 | TextInput：ID 或名稱 |
| 範圍 | Select：`7/15/30(預設)/60/90/180` | 同左 |
| 比對模式 | — | Select：精確(預設，只查 ID) / 模糊(ID 或名稱 LIKE) |

- 巴哈模糊查多筆 → ephemeral 候選清單下拉讓使用者挑

**4. Thread 行為（重點）**
- 每個 `(guild_id, source, lookup_id)` **唯一一個 public thread**，重查複用（封存自動解封）
- 命名：`[PTT] JohnDoe` / `[巴哈] 小明 (ABC123)`
- Auto-archive：7 天（Discord 最大）
- **日期 hybrid 策略：**
  - 今天首次查 → append 建立「今日 section」
  - 今天再查 → edit 覆蓋「今日 section」（標頭更新「最新更新」時間）
  - 跨日首次查 → append 建立「新日期 section」
- Thread 內無「頂部查詢日誌」embed（section 標頭本身就是當日日誌）
- 控制訊息「[🔄 更新查詢結果]」每次更新後刪舊發新在 thread 最底

**5. Embed slot 機制（仿巴哈留言）**
- 每個 slot 一個 embed，`description` ≤ 4000 字（複用 `EMBED_DESC_LIMIT`）
- 滿了發下一個 slot，slot 間附「⬇️ 更多...」導航連結 + `thread.send(..., reference=prev_msg)` reply 串接
- 複用 `src/services/bahamut_monitor.py` 既有常數與函式
- **不做 edit 模式下的預建格**（因為歷史 section 不會被 edit，每個 section 的 slot 數由當次結果決定）

**6. 色條分區**
- 🟦 標頭 embed（藍色）
- 🟪 主文 embed（紫色）
- 🟩 留言 embed（綠色）
- ⬜ 控制訊息 embed（灰色）

**7. 主文連結策略**
- 查 `state_db.forum_thread_state` / `bahamut_post_state` 既有對應
- 有 → 🗨️ Discord 討論（jump URL）
- 無 → 🌐 原文（PTT / 巴哈原站）
- **留言不給跳轉連結**，直接印內容

**8. 查詢策略**
- 保底：留言 100 則 / 主文 20 篇
- 區間內不足保底時補撈區間外（UI 分段「區間內 X / 區間外補 Y」，含分隔線）
- Hard cap：1000 筆/來源，超過截斷並在標頭提示「結果過多，縮短天數重查」
- PTT：SQLite JSON1（`json_each` + `json_extract`）+ 兩個 index
- 巴哈：ORM 直接查 `author_id` / `LIKE author_name`

**9. 父頻道通知（公開）**
```
🔔 @Jason 更新了 [PTT] JohnDoe 的查詢紀錄
   📅 搜尋前 30 天 · 📊 主文 5 / 留言 127
   → 🔗 跳轉 thread
```
- 公開訊息（非 ephemeral），讓所有人看到「誰查了誰」
- 另外仍回 ephemeral 給查詢者方便直接點連結
- 發完後 bump panel

### 資料層變更

**新增表**（`src/services/state_db.py`）：
```sql
CREATE TABLE IF NOT EXISTS community_lookup_threads (
    guild_id              INTEGER NOT NULL,
    source                TEXT NOT NULL,              -- 'ptt' | 'bahamut'
    lookup_id             TEXT NOT NULL,              -- PTT 帳號 或 巴哈 user_id
    thread_id             INTEGER NOT NULL,
    last_updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_section_date     TEXT,                       -- 'YYYY-MM-DD'，判斷同日 edit / 跨日 append
    last_section_slots    TEXT,                       -- JSON: 記錄該 section 的 msg_ids（header, post_slots, comment_slots, control）
    last_query_range_days INTEGER,
    PRIMARY KEY (guild_id, source, lookup_id)
);
```

**PTT schema：** 不變動（`ix_ptt_posts_published_at` 已存在且足夠，`author` index 不需要 — Step 1 驗證結果）。

### 檔案分工

| 檔案 | 角色 |
|---|---|
| `src/commands/community_lookup_commands.py`（新增） | `CommunityPanelView`、兩個 Modal、更新按鈕控制訊息 |
| `src/services/community_lookup_service.py`（新增） | 查詢核心（JSON1 PTT + ORM 巴哈）、slot 切割、section append/edit、主文連結解析 |
| `src/services/state_db.py`（小動） | `community_lookup_threads` 表 + CRUD |
| `src/commands/management_commands.py`（小動） | `/server_manager` 加「社群查詢頻道」選項 + 5 個 panel 同構方法（仿 intro） |
| `src/discord_bot.py`（小動） | `setup_hook` 註冊 `add_view(CommunityPanelView())` |
| `settings/community_lookup_panel_runtime.json`（新增） | panel message_id（仿 intro runtime） |

### Phase 0 實作步驟

- [x] Step 1：JSON1 效能驗證 script（`src/scripts/bench_ptt_comment_lookup.py`）— 全部 p95 < 30ms，PTT index migration 確認不需要
- [x] Step 2：state_db 新表 `community_lookup_threads` + CRUD（COALESCE 部分更新、smoke test 通過）
- [x] Step 3：`services/community_lookup_service.py` 查詢核心（PTT JSON1 + 巴哈 ORM + 模糊候選；對真實 DB smoke test：lovez04wj06 30天查到 618 則留言、坂坂悠模糊候選排序正確）
- [x] Step 4：`commands/community_lookup_commands.py`（Panel View、Modal、ControlMessageView、Flow 含日期 hybrid/slot 切割/父頻道通知/bump，全部 smoke test 通過）
- [x] Step 5：`/server_manager` 加「社群查詢頻道」選項 + 設定完自動部署 panel、`discord_bot.py` 已掛入 `COMMAND_MODULES`
- [ ] Step 6：**端到端部署驗證（待使用者）** — 重啟 discord-bot 容器、`/server_manager` 設社群查詢頻道、測 PTT/巴哈 Modal、同日 edit / 跨日 append、保底補撈、父頻道公告、panel bump、封存 thread 重查自動解封

### 未定事項 / 風險

- Phase 0 Step 1 驗證結果：若 JSON1 query p95 > 500ms 需考慮 Phase X 做 `ptt_comments` 正規化 migration（目前判斷機率低）
- `last_section_slots` JSON 結構具體欄位在 Step 4 實作時最終拍板
- Phase 2+：預留「接入 `/askai` 的 `asker_profile` 成 `<asker_community_activity>` 區塊」可能性，目前不在 Phase 0 範圍

---

## 點歌機器人專區

<!-- @meta
id: music-bot
type: STATE
status: confirmed
depends_on: [project-architecture]
affects: []
last_confirmed: 2026-04-18
-->

> 核心 P0 + P1 主體已完成並上線運作。
> **完整架構 / 設計決策 / 已實作功能 / 音訊鏈路 / 已知限制 / Config 已歸檔至 `TODO-completed.md` 的「點歌機器人 Music Bot 完整實作（歸檔 2026-04-18）」。**

### 點歌機器人 TODO

<!-- @meta
id: music-bot-todo
type: TODO
status: confirmed
last_confirmed: 2026-04-18
-->

**P1（體驗優化）：**
- [ ] `/pause` 與 `/resume` 按鈕
- [ ] 多歌單管理（切換不同預設歌單）
- [ ] 快取空間管理（LRU 清理、磁碟用量監控）

**P2（進階功能）：**
- [ ] 歷史播放紀錄
- [ ] 使用者點歌統計
- [ ] DAVE 加速問題追蹤（等 discord.py 後續版本優化）

---

## 幽靈點名系統專區

<!-- @meta
id: rollcall-system
type: STATE
status: confirmed
depends_on: [project-architecture]
affects: []
last_confirmed: 2026-04-18
-->

> 核心 P0 已實作完成（除部署驗證外）。
> **完整架構 / 設計決策 / 管理面板 / 使用方式已歸檔至 `TODO-completed.md` 的「幽靈點名系統核心實作（歸檔 2026-04-18）」。**

### 幽靈點名 TODO

<!-- @meta
id: rollcall-todo
type: TODO
status: confirmed
last_confirmed: 2026-04-19
-->

**P0（核心）：**
- [ ] 部署驗證（其餘 P0 已完成，歸檔於 TODO-completed.md）

**P1（體驗優化）：**
- [ ] `/server_manager` 整合（透過下拉選單設定頻道與身份組）
- [ ] ~~踢除前 DM 最後警告~~ → 已併入下一項（「踢除時 DM 通知 + 邀請連結」）
- [ ] **踢除時 DM 通知 + 重新加入邀請連結（2026-04-19 設計完未動 code）**：
  - **背景：** 使用者要求「點名確認 -> 踢人後」寄 DM 告知 + 附邀請連結。Discord 限制：DM 必須在 `guild.kick()` **之前**送（踢後就沒共同伺服器，DM channel 開不起來）。
  - **改動位置：** [src/services/rollcall_service.py:385-438](src/services/rollcall_service.py#L385-L438) `check_expired()` 迴圈內 —— kick 前插入 `member.send(...)`，包 `try/except discord.Forbidden`（DM 關閉時記 log 但**不阻擋踢除**）。
  - **DM 文案草稿：**
    ```
    標題：👻 你已被移出伺服器
    內文：
    你因逾期 7 天未回覆幽靈點名，已被移出「{guild.name}」。

    如果需要加回請用以下連結重新申請：
    {invite_url}
    ```
  - **邀請連結方案：** 靜態連結（管理員手動設永久邀請），不採動態 `channel.create_invite()`（理由：被踢者本來就不活躍，動態邀請易過期）。
  - **卡在的兩個決策（待使用者確認）：**
    1. 邀請連結 key 放哪？使用者否決了 `config.json`（認為那邊是「function 可變更的」）。AI 提議 `.env` 的 `ROLLCALL_REJOIN_INVITE_URL`（和 `DISCORD_TOKEN` / `OWNER_ID` 同性質：部署專屬、半敏感、不進 git），**尚未最終確認**。
    2. 未設 URL 時行為？(A) 不附連結仍寄 DM  (B) 整個 DM 跳過 —— **使用者尚未回答**。

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
3. 巴哈 `moreCommend.php` XHR 留言端點有反爬偵測（403），已透過 `BaseScraperClient` + `curl_cffi` 修復（2026-04-12）

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

### 反爬基礎設施（BaseScraperClient）

<!-- @meta
id: scraper-anti-detect
type: STATE
status: confirmed
depends_on: [bahamut-risk-formal]
affects: [bahamut-todo]
last_confirmed: 2026-04-12
-->

**起因：** 巴哈 `moreCommend.php` XHR 留言端點回 403，根因為 TLS 指紋 + XHR headers 不完整被反爬偵測。

**新增元件：**
- `src/scraper/services/base_scraper_client.py` — 反爬 HTTP client 基底類別
  - `curl_cffi` Session 建立（TLS 指紋模擬 Chrome 127）
  - `_build_page_headers()` — 一般頁面請求（Sec-Fetch-Mode: navigate）
  - `_build_xhr_headers()` — AJAX 請求（Sec-Fetch-Mode: cors, Origin, Sec-CH-UA）
  - `_fetch_with_retry()` — 共用 GET + 指數退避 retry
  - 統一 User-Agent（與 impersonate 版本對齊）

**套件變更：**
- 移除 `cloudscraper`（已停止維護，Cloudflare 繞過失效）
- 新增 `curl_cffi`（TLS JA3/JA4 指紋模擬，API 與 requests 相容）
- 保留 `requests`（PTT scraper 尚未遷移）

**整合狀態：**
- [x] Phase 1：`BahamutScraperService` 繼承 `BaseScraperClient`，XHR headers 修復
- [x] Phase 2：`PTTScraperService` 接上 `BaseScraperClient`
- [x] Phase 3：`APIService`（鳴潮）接上 `BaseScraperClient`，`main.py` 改用 `curl_cffi`
- [x] 清理：移除 `requests`、`fake-useragent`、`cloudscraper` 依賴，scraper 容器統一只用 `curl_cffi`

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
last_confirmed: 2026-04-07
-->

> Telegram Relay 已完成（歸檔至 `TODO-completed.md`）。

### FB 貼文推送模式（2026-04-07 完成，待部署驗證）

<!-- @meta
id: fb-push-notify
type: STATE
status: confirmed
depends_on: [cross-source-integration]
affects: [project-architecture]
last_confirmed: 2026-04-07
-->

**起因：** post id=399「光耀灼痕——贊妮」DB 有 8 張圖，但 bot 收到 API 回傳 images 為空，Discord 貼文無圖。根因：輪詢模式下時間差 + FB CDN URL token 過期 + 無 URL 刷新機制。

**變更（4 檔案）：**
1. `src/scraper/main.py`：FB 抓完後呼叫 `_notify_discord_bot("fb")`
2. `src/services/notify_server.py`：新增 `"fb"` handler → `_process_fb` → 呼叫 `FBMonitor.check_and_send_fb_posts()`
3. `src/discord_bot.py`：移除 `_auto_start_fb_monitor` 輪詢（原每 600 秒）
4. `src/scraper/services/fb_scraper_service.py`：`_merge_fields_for_duplicate` 圖片合併改為 `>=` 時更新（刷新 CDN token，但不縮水）
5. `src/scraper/db/database.py`：`_update_fb_post` 圖片從「只新增」改為「全量替換」（URL 有變時刪舊插新）

**流程（改後）：**
> scraper 抓 FB → 寫 DB（URL 最新鮮） → POST /notify/fb → bot 從 API 拉資料 → 下載圖片 → 發送 Discord

**注意事項：**
- 舊貼文（不在 FB 首頁的）不會被重抓，其 CDN URL 過期後無法自動更新
- `start_fb_monitoring()` 仍保留於 `fb_monitor.py`，可供手動指令使用

### X.com / Twitter 影片嵌入研究（2026-04-22）

<!-- @meta
id: xcom-video-embed-research
type: STATE
status: draft
depends_on: [cross-source-integration]
affects: []
last_confirmed: 2026-04-22
-->

> **背景：** 使用者問 ermiana 類 Discord bot 為何能把 x.com 貼文影片直接轉成可播放 embed。結論記錄於此，若未來要在本專案加 x.com 來源可直接接手。

**核心原理：**
- Discord unfurler 會抓訊息裡 URL 的 `<meta>` 標籤（OpenGraph / Twitter Card）決定 embed 樣式
- x.com 本身**不回傳 `og:video` 直連**，只給縮圖，所以 Discord 播不了
- 第三方代理站 scrape 該 tweet 後重組一份含 `og:video` / `twitter:player:stream` 的 HTML，Discord 抓到就能直接播

**常用代理網域（把 `x.com` / `twitter.com` 整段替換）：**
- `fxtwitter.com`（最穩定、最主流）
- `fixupx.com`（FxTwitter 對應 x.com 的新網域）
- `vxtwitter.com`（另一派系）

**Bot 極簡實作模式（若要自己做）：**
1. `on_message` regex 抓 `x.com` / `twitter.com` URL
2. 替換 domain 後重發
3. `message.edit(suppress=True)` 或 webhook 模仿使用者身份，抑制原訊息 embed 避免雙重 embed

**影片直連 JSON API（想自己解析用）：**
- `GET https://api.fxtwitter.com/{user}/status/{id}` → 回 JSON
- `media.videos[].url` 即 `.mp4` 直連
- 免認證、免 API key

**能力邊界（重要）：**

| 功能 | 代理網域 | 說明 |
|---|---|---|
| 單篇貼文內容 | ✅ | 文字、作者、時間、媒體 |
| 影片直連 | ✅ | `.mp4` URL |
| 關鍵字 / hashtag / 使用者時間軸搜尋 | ❌ | 完全沒這能力，只吃「已知的 tweet URL」 |

**代理網域底層靠什麼跑：**
- Syndication API：`cdn.syndication.twimg.com/tweet-result?id={id}&token={derived}`
- 原用途是讓部落格 / 新聞網站嵌入推文，免登入、免 key、免費
- token 是前端用 tweet id 算出來的公式，任何人都能產
- X 不關掉 syndication 的理由：關了全世界新聞網站的 embed 都會爛，對 X 自己的 SEO 是自殺
- 舊的 `guest_token`（`/1.1/guest/activate.json`）**2023 年中被封殺**，Nitter / snscrape 就是那時死的，現在不可用

**付費 vs 免費路線比較：**

| 層面 | 官方 v2 API | Syndication（fxtwitter 等） |
|---|---|---|
| 要錢 | Basic $200/月 起 | 免費 |
| 註冊 | 需申請 API key | 不需 |
| 搜尋 / timeline | ✅ | ❌ |
| SLA / 文件 | ✅ | **完全沒有** |
| 隨時被關的風險 | 低 | 高（X 已有前例） |

**若未來要在本專案加 x.com 來源，決策樹：**
1. 「把 Discord 訊息裡的 x.com 連結轉成可播放影片」→ `on_message` domain replace，最省事，一小時可收工（見 [src/discord_bot.py](src/discord_bot.py)）
2. 監控特定帳號新貼文 → 沒有免費穩定方案，需評估付費 v2 或放棄
3. 關鍵字搜尋 → 代理網域做不到，只能走付費 v2 或改用其他社群（Threads / PTT / FB）
4. 若做商業/長期依賴 → 不建議依賴 syndication，**X 能隨時關掉**

**參考：**
- FxTwitter 專案：https://github.com/FixTweet/FxTwitter

---

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

2. **FB 走 Scraper 推送通知（與 Bahamut 同模式）**
   - Scraper 抓完 → POST `/notify/fb` → `notify_server._process_fb` → `FBMonitor.check_and_send_fb_posts()`
   - 不再輪詢（原 `start_fb_monitoring` 每 600 秒）

3. **PTT / Article 走來源資料存取層（SourceMessageRepository/Fetch）**
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
