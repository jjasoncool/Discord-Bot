# 已完成項目歸檔

## Telegram Relay 功能完成歸檔（2026-03-29）

> 依使用者指示，將 `AI_HANDOFF_AND_TODO.md` 的 Telegram 功能完成項目移入本檔保存。

### 功能完成（主線）
- 已完成 `TelegramMessageRepository`（依 `message_pk` 取 message + media）
- 已完成 `MessageRelayWorker`：`LISTEN telegram_new_message` + 每小時補償輪詢
- 已完成 `TelegramRenderAdapter`（保留既有格式，不做語意重排）
- 已接入 `DiscordMessagePublisher`（執行 RenderPlan，不改內容）
- 已套用路由 `telegram_channel_routes`，無路由一律 skip + log

### 落地與設定
- 新增 `src/services/telegram_relay_service.py`，包含：
  - `TelegramMessageRepository`
  - `MessageRouteResolver`
  - `TelegramRenderAdapter`
  - `DiscordMessagePublisher`
  - `MessageRelayWorker`
- `src/discord_bot.py`：`on_ready()` 串接 `auto_start_telegram_relay(bot)`，含防重啟保護
- `src/config.json`：
  - `telegram_relay_enabled`
  - `telegram_channel_routes`
  - `telegram_replay_from_message_pk`

### 狀態持久化共識
- `config.json` 僅存設定，不存已送狀態
- 已送狀態/游標存 DB：
  - `telegram_relay_delivery_state`
  - `telegram_relay_runtime_state`

### 驗證結論
- NOTIFY 即時路徑已驗證正常
- 補償輪詢可補漏
- 既有已知問題（route key、重複下載、時序、副檔名、embed、連線觀測）均已修正

## Telegram Relay 通道連線問題（2026-03-26 已解決）

- **原始現象**：discord-bot log 顯示 `published_count=1` 但 Discord 頻道看不到訊息；`telegram_relay_delivery_state` 表為空。
- **排查結論**：
  1. LISTEN/NOTIFY 機制正常 — `test_ping` 手動測試收到，且刪除 DB 最新一筆後重啟 telegram-scraper 成功觸發即時 NOTIFY → discord-bot 收到並發文（pk=88, published_count=1）
  2. discord-bot relay worker 確認連到正確 DB（`telegram_data`），非 `discord_data`
  3. 先前「啟動後沒發文」主因是歷史 NOTIFY 在 LISTEN 建立前就發了（PG NOTIFY 即發即棄），由啟動補償 backfill 處理
  4. delivery_state / runtime_state 為空的原因：先前 session 的 DB 被清空重建，舊紀錄已不存在；最新 session（pk=88）已成功寫入 delivery_state
- **已修正**：
  - route key 型態不一致問題（chat_id 數字 vs source_channel 名稱 fallback）
  - 啟動安全補償（cursor=尾端 + delivery_state=0 自癒）
  - `_on_notify` 新增收到 NOTIFY 的 log：`收到 NOTIFY: channel=... message_pk=...`
- **結論**：NOTIFY 即時路徑正常運作，非 code bug。

## Telegram scraper 媒體下載重複問題（2026-03-26 已解決）

- **問題**：Telethon 預設時間戳命名 photo，重啟重跑歷史產生 `(N)` 後綴重複檔案與 DB 記錄。
- **修正**：`_build_stable_media_path()` 依 `photo.id`/`document.id` 建立固定路徑；下載前先查 DB 略過已有記錄。

## 歷史訊息時序錯亂（2026-03-26 已解決）

- **問題**：`iter_messages` 預設由新到舊，直接 insert 導致 PK 與時間反序。
- **修正**：收集後 `.reverse()` 再依序 insert。

## 媒體副檔名缺失（2026-03-26 已解決）

- **問題**：非圖片/影片 mime 類型無對應副檔名。
- **修正**：新增 `_MIME_TO_EXT` 查找表（38 種）+ 大類兜底。

## Route key 型態不一致（2026-03-26 已解決）

- **問題**：DB 路由用 `telegram_chat_id`（數字），config 用 `source_channel`（名稱）。
- **修正**：`resolve_telegram_routes` 先查 chat_id，再 fallback 讀 runtime_config 的 `source_channel` 正規化後查 routes。

## Embed 改善（2026-03-26 已完成）

- embed title 改為來源頻道名、timestamp 改為訊息時間、color 改為 Telegram 藍、影片不設 `set_image` 避免黑幕。

## Telegram -> Discord 核心定案（已完成，2026-03-29 歸檔）

1. Telegram scraper：寫 DB + `NOTIFY telegram_new_message`。
2. Discord consumer（`MessageRelayWorker`，舊暫名 `TelegramRelayService`）：
   - `LISTEN telegram_new_message`
   - 收 payload 後查 DB 取 message/media
   - 套路由後發送 Discord
3. 若無路由：**不發文（skip + log）**。
4. 除即時 notify 外，需有**每小時補檢**防漏。
5. 路由/開關由 `config.json` 管理（非硬編碼）。

## Telegram Scraper 專案交接（2026-03-22，已完成歸檔）

### 1) 目前狀態總結

- 已完成 `telegram-scraper` 獨立服務化（Docker 微服務）。
- Dockerfile 已集中在 `docker/telegram_scraper/dockerfile`。
- `telegram-scraper` 啟動邏輯改為 `entrypoint.sh` 控制：
  - 有 session：自動跑 `main.py`
  - 無 session 且可互動：進登入流程
  - 無 session 且非互動：待命 `sleep infinity`
- Telegram 程式已模組化，不再把所有邏輯塞在 `main.py`。

### 2) Telegram 模組化後檔案職責

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

### 3) 目前 forward 過濾規則（已修正）

#### 問題回顧
先前誤把「目標頻道」拿去比白名單，導致 forward 容易被放行。

#### 現行正確規則
1. forward 訊息先以「**轉發來源**」做白名單比對。
2. 未命中白名單 -> 直接略過。
3. 命中白名單 -> 允許通過。
4. 允許通過的 forward 可自動把來源 identifier 寫回 `runtime_config.json`。

### 4) 設定來源（重要）

- `.env` 只保留必要 Telegram API：
  - `TELEGRAM_API_ID`
  - `TELEGRAM_API_HASH`
- forward 規則固定讀：
  - `src/telegram_scraper/runtime_config.json`

### 5) 歷史訊息抓取規則

- `history_limit`：最多掃幾筆（上限）。
- `history_hours`：時間窗（抓到多久以前）。
- 兩者可同時生效。
- `runner.py` 已實作：超過時間窗會 `break` 停止掃描。

### 6) Docker 相關現況

- `docker-compose.yaml` 已使用集中路徑：
  - `docker/discord_bot/dockerfile`
  - `docker/scraper/dockerfile`
  - `docker/telegram_scraper/dockerfile`
- `docker/telegram_scraper/entrypoint.sh` 控制首次登入與待命模式。
- `docker/telegram_scraper/dockerfile` 有 `PYTHONUNBUFFERED=1`，確保 log 即時。

### 7) Session 持久化與 git

- Telethon session 位置：`src/telegram_scraper/session/`
- `.gitignore` 已忽略：`src/telegram_scraper/session/`

## Telegram Relay 設計定案 — 架構/設定/相容/流程盤點（2026-03-25，已完成歸檔）

### 完整架構（目前共識）

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

### 設定規則（config.json）

- `telegram_relay_enabled`（bool）
  - Relay 總開關（保留）。

- `telegram_channel_routes`（dict）
  - 型態：`{ "<telegram_chat_id>": [discord_channel_id, ...] }`
  - 用途：來源 Telegram chat 對應目標 Discord 頻道。

- 發文原則
  - **無路由不發文**（skip + log）。

### 舊流程相容策略（已確認）

- 可先不引入 `MessageRelayWorker`。
- 舊流程可直接串 `SourceMessageRepository`（再接 resolver/publisher）。
- 待穩定後再收斂觸發入口進 `MessageRelayWorker`。

### 現行 Article / FB / PTT 流程盤點（已確認）

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

---

## Bahamut Scraper MVP 完成歸檔（2026-04-01）

### 第一階段 MVP — 全部完成
- 研究巴哈 HTML / API 結構（文章列表、文章頁、留言區、回文區）
- 確認 anti-bot 處理（cloudscraper + gate 進版圖處理）
- 實作文章列表抓取（標題、分類、作者、時間、URL、文章 ID，支援多頁）
- 實作文章主文抓取（含多頁遍歷、圖片提取）
- 實作主文留言抓取（HTML + XHR moreCommend.php 合併去重）
- 實作回文與回文留言抓取
- 定義 JSON payload 結構（post + replies[] + 各自 comments[]）
- JSON 範例輸出驗證：`src/scraper/data/bahamut_samples/*.json`
- 錯誤處理、限速、重試、日誌紀錄
- GP/BP 提取（主文/回文/留言）
- CLI 單篇除錯：`--sna <id>`
- 排程串接：`main.py` 每 1 小時自動 `fetch → save_articles_to_db → commit`

### 第二階段 DB — 大部分完成
- `bahamut_posts` 主表（主文+回文共用，position 區分）
- `bahamut_post_comments` 留言表
- Upsert 邏輯：文章 `(board_id, sn)`、留言 `(parent_sn, comment_id)`
- Content hash 變更偵測 + 可疑縮水阻擋（prev_* 欄位）
- 必要索引（board_id, post_id, author_id, user_id, published_at, content_hash, is_deleted）
- raw_json 完整備份
- Scraper API：`/api/bahamut/recent` + `/api/bahamut/{board_id}/{post_id}`

### Bahamut → Discord Relay 首版
- `src/services/bahamut_monitor.py`：embed 格式化 + 留言格預建/溢出 + 鏈式導航
- `src/scraper/api_server.py`：巴哈 API endpoints（按 snA 分組，含主文+回覆+留言）
- `/get_baha_post` 斜線命令（`article_commands.py`）
- 主文（藍色 embed）、回覆（綠色 embed）、留言格（灰色 embed）
- 留言格式：`🔥 B1 **user** 👍107 — content`
- 作者名連結巴哈小屋、圖片 URL 轉 `[🖼 圖片](url)`
- 溢出導航：格3→格4→格5 鏈式 reply + `⬇️ 更多留言...` 連結

### ID 模型定案
- `snA` = thread/group ID = `post_id`
- `sn` = 單篇文章 ID
- `comment_id` = 留言唯一鍵（搭配 parent_sn）
- `floor` / `position` 僅供顯示，不作唯一鍵

---

## Bahamut 增量更新 + SQLite 遷移 + Webhook 通知完成歸檔（2026-04-02）

### 增量更新
- `_update_existing_thread`：已存在的 thread 自動走增量更新
- GP/BP edit：主文/回覆 embed 有變化才 edit
- 留言 slot 重組：用最新全部留言重組 slot 內容，有變化才 edit
- 新回覆 append：state 裡沒有的 sn → send + 預建留言格
- hash 比對：md5 比對 embed description，無變化跳過不 edit（防 Discord rate limit）

### SQLite State 遷移
- `state_db.py`：async SQLite 封裝，5 張表
  - `sent_content`：所有來源去重（Article / FB / PTT / Bahamut）
  - `forum_thread_state`：PTT / Bahamut 共用 thread 追蹤
  - `bahamut_post_state`：巴哈文章 Discord msg_id
  - `bahamut_comment_slot`：巴哈留言格 msg_id + used_chars
  - `bahamut_synced_comment`：巴哈留言去重
- `base_monitor.py`：所有 state 方法改 async，全域共用 StateDB + `asyncio.Lock` 併發安全
- `article_monitor.py`：所有 state 呼叫加 `await`
- `migrate_json_to_sqlite.py`：手動遷移腳本
- 遷移已執行完成（446 articles + 386 fb + 507 ptt）

### HTTP Webhook 通知
- `notify_server.py`：通用 aiohttp.web server，`POST /notify/{source}` 分派架構
- Scraper `main.py`：巴哈抓完存 DB 後呼叫 `_notify_discord_bot("bahamut", ...)`
- `discord_bot.py`：on_ready 啟動 notify server (port 5000)
- `docker-compose.yaml`：discord-bot 加 `expose: ["5000"]`

### 共用工具抽取
- `discord_content.py`：sanitize_forum_thread_title / linkify_image_urls / content_hash / chunk_discord_files / get_forum_tags
- article_monitor + bahamut_monitor 共用，移除各自重複的實作

### Config 快取
- `ChannelConfig`：TTL 5 分鐘記憶體快取，save_config 同步更新
- Scraper config：board_end_page 1→2（自動抓前 2 頁）、export_sample_json 關閉
