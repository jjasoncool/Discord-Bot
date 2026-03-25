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

## 3) Telegram -> Discord 目前核心定案（摘要）

1. Telegram scraper：寫 DB + `NOTIFY telegram_new_message`。
2. Discord consumer（`MessageRelayWorker`，舊暫名 `TelegramRelayService`）：
   - `LISTEN telegram_new_message`
   - 收 payload 後查 DB 取 message/media
   - 套路由後發送 Discord
3. 若無路由：**不發文（skip + log）**。
4. 除即時 notify 外，需有**每小時補檢**防漏。
5. 路由/開關由 `config.json` 管理（非硬編碼）。

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

# Telegram Scraper 專案交接（2026-03-22 最新）

> 本段是給下一個 Session 直接接手 Telegram -> Discord 轉發鏈路使用。

## 1) 目前狀態總結

- 已完成 `telegram-scraper` 獨立服務化（Docker 微服務）。
- Dockerfile 已集中在 `docker/telegram_scraper/dockerfile`。
- `telegram-scraper` 啟動邏輯改為 `entrypoint.sh` 控制：
  - 有 session：自動跑 `main.py`
  - 無 session 且可互動：進登入流程
  - 無 session 且非互動：待命 `sleep infinity`
- Telegram 程式已模組化，不再把所有邏輯塞在 `main.py`。

## 2) Telegram 模組化後檔案職責

- `src/telegram_scraper/main.py`
  - 薄入口，只做：載入設定 -> 呼叫 runner。
- `src/telegram_scraper/tg_config.py`
  - 設定解析（env + JSON），`TelegramConfig` dataclass。
  - forward 白名單寫回函式：`add_identifier_to_forward_whitelist(...)`。
- `src/telegram_scraper/filters.py`
  - forward 來源解析：`extract_forward_source_chat_id(...)`。
  - forward 白名單比對：`is_forward_source_in_whitelist(...)`。
  - forward 是否略過：`should_skip_forward(...)`。
- `src/telegram_scraper/handlers.py`
  - 共用訊息流程 `_process_message(...)`。
  - 即時與歷史 handler 皆委派到共用流程。
- `src/telegram_scraper/runner.py`
  - Telethon client 啟動、歷史掃描、即時監聽。

## 3) 目前 forward 過濾規則（已修正）

### 問題回顧
先前誤把「目標頻道」拿去比白名單，導致 forward 容易被放行。

### 現行正確規則
1. forward 訊息先以「**轉發來源**」做白名單比對。
2. 未命中白名單 -> 直接略過。
3. 命中白名單 -> 允許通過。
4. 允許通過的 forward 可自動把來源 identifier 寫回 `runtime_config.json`。

## 4) 設定來源（重要）

- `.env` 只保留必要 Telegram API：
  - `TELEGRAM_API_ID`
  - `TELEGRAM_API_HASH`
- forward 規則固定讀：
  - `src/telegram_scraper/runtime_config.json`

目前範例（實際內容已被使用者調整）：

```json
{
    "history_hours": 24,
    "skip_forwards": true,
    "forward_whitelist": [
        "Team_Gemberry78",
        "Sleep_Leaks",
        "Seele_WW_leak"
    ]
}
```

## 5) 歷史訊息抓取規則

- `history_limit`：最多掃幾筆（上限）。
- `history_hours`：時間窗（抓到多久以前）。
- 兩者可同時生效。
- `runner.py` 已實作：超過時間窗會 `break` 停止掃描。

## 6) Docker 相關現況

- `docker-compose.yaml` 已使用集中路徑：
  - `docker/discord_bot/dockerfile`
  - `docker/scraper/dockerfile`
  - `docker/telegram_scraper/dockerfile`
- `docker/telegram_scraper/entrypoint.sh` 控制首次登入與待命模式。
- `docker/telegram_scraper/dockerfile` 有 `PYTHONUNBUFFERED=1`，確保 log 即時。

## 7) Session 持久化與 git

- Telethon session 位置：`src/telegram_scraper/session/`
- `.gitignore` 已忽略：`src/telegram_scraper/session/`

## 8) Telegram Relay 最新設計（2026-03-25 定案版）

> 本段取代舊方案。若與後文舊內容衝突，以本段為準。

### 8.1 完整架構（目前共識）

1. **事件來源層（Source Ingest）**
   - 目前 source：Telegram scraper（寫 DB + `NOTIFY telegram_new_message`）。
   - 未來可擴充 FB/PTT/Article 作為其他 source。

2. **事件消費層（Relay Worker）**
   - 命名採通用：`MessageRelayWorker`（保留未來整合空間）。
   - 雙軌：
     - 即時通路：`LISTEN telegram_new_message`
     - 補償通路：每 1 小時 polling 補漏

3. **資料存取層（Repository）**
   - 上層抽象：`SourceMessageRepository`
   - Telegram 具體實作：`TelegramMessageRepository`
   - 職責：依 message key 取回完整訊息 + 媒體。

4. **路由層（Resolver）**
   - 命名：`MessageRouteResolver`
   - 職責：來源事件 -> Discord 頻道清單。
   - 規則：無路由就不發文（skip + log）。

5. **發送層（Publisher）**
   - 命名：`DiscordMessagePublisher`
   - 職責：文字/附件發送、分批、重試、錯誤紀錄。
   - 策略：先做最小共用核心，不一次硬整合所有來源格式。

6. **格式轉換層（Adapter）**
   - 建議抽象：`MessageRenderAdapter`
   - 來源別實作：`TelegramRenderAdapter` / `ArticleRenderAdapter` / `FbRenderAdapter` / `PttRenderAdapter`

### 8.2 設定規則（config.json）

- `telegram_relay_enabled`（bool）
  - Relay 總開關（保留）。

- `telegram_channel_routes`（dict）
  - 型態：`{ "<telegram_chat_id>": [discord_channel_id, ...] }`
  - 用途：來源 Telegram chat 對應目標 Discord 頻道。

- 發文原則
  - **無路由不發文**（skip + log）。

### 8.3 舊流程相容策略（已確認）

- 可先不引入 `MessageRelayWorker`。
- 舊流程可直接串 `SourceMessageRepository`（再接 resolver/publisher）。
- 待穩定後再收斂觸發入口進 `MessageRelayWorker`。

### 8.4 現行 Article / FB / PTT 流程盤點（已確認）

> 目的：先把既有流程講清楚，避免整合時誤拆。

#### A) Article（官方文章）
1. 啟動來源：
   - `discord_bot.py` 的 `on_ready` 會讀 `config.json.article_monitor_channel_id` 並自動啟動。
   - 也可由 `ArticleCommands` 手動啟動監控。
2. 取文：
   - `ArticleMonitor.fetch_recent_articles()` 呼叫 `/api/articles/discord`（asc）。
3. 去重：
   - `BaseContentMonitor.sent_article_ids`（`/app/services/sent_articles.json`）。
4. 發文：
   - `send_article_to_channel()`（Embed + 圖片附件分批）。

#### B) FB
1. 啟動來源：
   - `discord_bot.py` 自動啟動 `start_fb_monitoring()`（目前沿用 `article_monitor_channel_id`）。
2. 取文：
   - `fetch_recent_fb_posts()` 呼叫 `/api/fb_posts/recent`。
3. 去重：
   - `sent_fbpost_ids`。
4. 發文：
   - `send_fb_post_to_channel()`（主文 + 第一張圖 + 其餘分批）。

#### C) PTT
1. 啟動來源：
   - `discord_bot.py` 讀 `config.json.forum_article_channel_id`，啟動 `start_ptt_monitoring()`。
2. 取文：
   - `fetch_recent_ptt_posts()` 呼叫 `/api/ptt_posts/recent`（desc，發送前反轉成舊到新）。
3. 去重與增量：
   - `sent_article_keys` + `sent_ptt_state`（留言同步進度）。
4. 發文：
   - `send_ptt_post_to_forum_channel()`（Forum thread 建立、附圖、留言分段補送）。

#### D) 現況結論
- 目前三者都在 `ArticleMonitor` 裡運作，功能可用但責任較重。
- 發送型態不完全一致（TextChannel Embed / ForumThread / 附件策略），
  所以整合要分階段，不能一次硬抽成單一流程。

#### E) 目前 service 取得的資料結構（欄位盤點）

> 目的：先掌握「現況 payload 長相」，後續整合時才不會誤砍欄位。

1. **Article（`/api/articles/discord`）常用欄位**
   - 主鍵/識別：`article_id`
   - 文字：`article_title`, `article_desc`, `article_content`, `article_content_full`
   - 分類：`article_type_name`, `article_type`
   - 時間：`start_time`, `create_time`
   - 圖片：`article_cover`, `content_cover`, `suggest_cover`

2. **FB（`/api/fb_posts/recent`）常用欄位**
   - 主鍵/識別：`id`
   - 文字：`text`, `text_md`
   - 連結：`url`, `pfbid_url`
   - 時間：`timestamp`, `created_at`
   - 圖片：`images`（list）

3. **PTT（`/api/ptt_posts/recent`）常用欄位**
   - 主鍵/識別：`board`, `article_id`（組合 key：`ptt:{board}:{article_id}`）
   - 文字：`title`, `content`
   - 作者/時間：`author`, `published_at`
   - 連結與標記：`url`, `matched_keywords`
   - 留言：`comments`（元素含 `tag`, `user`, `content`, `time`）

4. **Telegram（DB 實體，`telegram_scraper/db.py`）**
   - `telegram_messages`：
     - `id`（PK）
     - `telegram_chat_id`, `telegram_message_id`（unique）
     - `text`, `message_date`, `has_media`
   - `telegram_message_media`：
     - `message_id`（FK）
     - `media_type`, `file_rel_path`, `mime_type`, `file_size`
     - `width`, `height`, `duration_sec`, `is_spoiler`

5. **整合注意（目前共識）**
   - Article/FB/PTT 是 API payload；Telegram 是 DB row + media row。
   - 型別來源不同，但欄位都必須保留（走 lossless envelope）。
   - 後續 `SourceFetchPort` / `MessageRenderAdapter` 只能做「映射」，不能做「刪減」。

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

## 10) TODO（Telegram Relay 實作追蹤）

### 10.0 Telegram 先行實作（本輪追加，優先最高）

> 使用者決議：先做 Telegram。以下細節為必記錄項，避免後續返工。

- [x] 實作 `TelegramMessageRepository` 查詢介面（依 message_pk 取 message + media）
- [x] 實作 `MessageRelayWorker`：LISTEN `telegram_new_message` + 每小時補償輪詢
- [x] 實作 `TelegramRenderAdapter`（保留目前格式，不做語意重排）
- [x] 接入 `DiscordMessagePublisher`（僅執行 RenderPlan，不改內容）
- [x] 路由套用 `telegram_channel_routes`，無路由一律 skip + log

#### Telegram 先行實作落地紀錄（2026-03-25）

- 新增檔案：`src/services/telegram_relay_service.py`
  - `TelegramMessageRepository`
  - `MessageRouteResolver`
  - `TelegramRenderAdapter`
  - `DiscordMessagePublisher`
  - `MessageRelayWorker`
- 串接啟動：`src/discord_bot.py`
  - `on_ready()` 新增 `auto_start_telegram_relay(bot)`
  - 支援重複 on_ready 防重啟（worker 已運行則略過）
- 設定補齊：`src/config.json`
  - 新增 `telegram_relay_enabled`（預設 false）
  - 新增 `telegram_channel_routes`（預設 `{}`）
  - 新增 `telegram_replay_from_message_pk`（預設 `null`，可指定從某筆後重送）

#### Telegram 狀態持久化共識（2026-03-25 補充）

- `config.json` **只放設定**，不放「已送過哪些資料」。
- 已送狀態與游標改存 DB：
  - `telegram_relay_delivery_state`：記錄 `(message_pk, discord_channel_id)` 是否已送
  - `telegram_relay_runtime_state`：記錄 `last_polled_pk`
- 可選重送設定：
  - `telegram_replay_from_message_pk`（例如設 `12345` 表示從 `message_pk >= 12345` 強制重送）
  - 重送完成後建議手動改回 `null`，恢復一般去重流程

> 注意：目前為「最小可用版」；已具備 LISTEN + 補償 + route + publish。
> 下一輪可補強 retry/backoff 細節與更多可觀測欄位聚合。

#### 2026-03-26 已解決問題（詳見 TODO-completed.md）

> 以下問題均已解決並歸檔至 `TODO-completed.md`：
> - route key 型態不一致（chat_id 數字 vs source_channel 名稱）
> - Telegram scraper 媒體下載重複（`(N)` 後綴問題）
> - 歷史訊息時序錯亂（PK 與時間反序）
> - 媒體副檔名缺失（非圖片/影片 mime 類型）
> - Embed 改善（頻道名、timestamp、Telegram 藍）
> - Telegram relay 通道連線問題（NOTIFY 即時路徑已驗證正常）

#### Telegram relay NOTIFY 即時路徑驗證結果（2026-03-26）

- **驗證方式**：刪除 DB 最新一筆 → 重啟 telegram-scraper → telegram-scraper 重新 INSERT + NOTIFY → discord-bot 即時收到並發文
- **結果**：`telegram_relay_result message_pk=88 ... published_count=1 result=published` ✅
- **結論**：NOTIFY 即時路徑正常運作
- **已新增 log**：`_on_notify` 收到有效 NOTIFY 時記錄 `收到 NOTIFY: channel=... message_pk=...`（方便追蹤即時路徑）
- **觀察 log 關鍵字**：
  - `收到 NOTIFY: channel=... message_pk=...`（即時收到通知）
  - `Telegram Relay 啟動補償已排入 X 筆歷史訊息`（啟動補償）
  - `telegram_relay_result ... published_count=... result=...`（處理結果）
  - `Telegram relay 無路由，略過 ...`（路由問題）

#### Telegram scraper 歷史掃描安全性確認（2026-03-26）

- `history_hours: 168`（7 天）設定安全，原因：
  - `iter_messages` 本身流量小（只列出訊息 metadata）
  - 已存在的訊息：`upsert_message_only` ON CONFLICT DO NOTHING
  - 已存在的媒體：`has_media_records()` 檢查後略過下載
  - 已存在的訊息不發 NOTIFY（只有 `inserted_new=True` 才通知）
  - Telethon 內建 `FloodWaitError` 自動等待，不會被封鎖帳號
- 初始化完成後建議將 `history_hours` 調回 `24`~`48`

#### Telegram 必記錄細節（設計約束）

1. **去重鍵**
   - DB unique：`(telegram_chat_id, telegram_message_id)`
   - Relay 端二次保險：以 `message_pk` 做已處理去重（避免重複 notify / 重啟重送）

2. **事件 payload 規格**
   - `NOTIFY telegram_new_message` payload 固定為 `message_pk`（字串）
   - consumer 收到後必做型別驗證；無效 payload 直接記錯誤並略過

3. **順序與一致性**
   - 不強保證全域順序，只保證「單一訊息不重複發送」
   - 補償輪詢需以 cursor（`last_processed_pk` 或 `last_processed_time`）前進

4. **媒體檔案路徑**
   - `file_rel_path` 必須能在 discord-bot 容器解析到實際檔案
   - 啟動時先做 path health-check，失敗要明確告警

5. **Spoiler 與媒體策略**
   - `is_spoiler=true` 時，優先走 Discord 可識別的 spoiler 發送策略
   - 不可在 publisher 端臨時改文案，規則寫在 `TelegramRenderAdapter`

6. **錯誤與重試**
   - 發送失敗採有限次 retry（含 backoff）
   - 超過上限要落錯誤日誌並保留可補送資訊（message_pk / route / err）

7. **可觀測性（最少欄位）**
   - 每次處理記錄：`message_pk`, `telegram_chat_id`, `telegram_message_id`, `route_count`, `published_count`, `latency_ms`, `result`

8. **設定驗證**
   - 啟動即驗證 `telegram_relay_enabled` / `telegram_channel_routes` 型別
   - route 的 channel id 若不存在或不可發送，啟動時告警 + 執行時 skip

### P0（本期必做）
- [ ] 建立 `SourceFetchPort` 與來源實作（Article/FB/PTT/Telegram）
- [ ] 建立 `SourceFetchOrchestrator`（strategy/case 分派）
- [x] 建立 `SourceMessageRepository` 介面與 `TelegramMessageRepository` 實作
- [x] 實作 Telegram 即時流程：`LISTEN telegram_new_message` 取文（已驗證 NOTIFY 即時路徑正常）
- [x] 實作 Telegram 補償流程：每小時 polling 補漏
- [x] 套用規則：無路由不發文（skip + log）

### P1（穩定化）
- [x] 建立 `MessageRouteResolver`（先接 `telegram_channel_routes`，含 chat_id + source_channel fallback）
- [ ] 建立 `MessageRenderAdapter` 無損封裝模型
- [ ] 統一 config 讀寫方式，減少直接 `open(config.json)` 的分散寫法
- [x] 補齊 fetch/route/retry/skip 的可觀測 log（NOTIFY 收到 log、發送目標 log、relay result log）

### P2（整合擴充）
- [ ] 導入/整合 `DiscordMessagePublisher`（後置）
- [ ] 保留外部 API 不變，逐步內部改接 publisher
- [ ] 規劃/新增管理命令：telegram route 查詢與設定
