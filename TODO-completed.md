# 已完成項目歸檔

## Index

> 依時間倒序排列，方便快速定位。搜尋關鍵字可直接跳到對應區塊。

| 日期 | 區塊 | 關鍵字 |
|---|---|---|
| 2026-04-19 | [askai bot 身份感注入](#askai-bot-身份感注入歸檔2026-04-19) | bot_display_name, bot_history name 屬性, safety_prompt 別稱推斷, persona 對內理解 vs 對外表達 |
| 2026-04-18 | [Context/Prompt 完整重構 + askai 身份感](#contextprompt-完整重構--askai-身份感歸檔2026-04-18) | askai, asker_profile, persona_card, 人格萃取, 撞名偵測, 429 治本, bahamut author_id |
| 2026-04-18 | [點歌機器人 Music Bot 完整實作](#點歌機器人-music-bot-完整實作歸檔2026-04-18) | music, yt-dlp, DAVE, 按鈕面板, 快取, 音訊鏈路 |
| 2026-04-18 | [幽靈點名系統核心實作](#幽靈點名系統核心實作歸檔2026-04-18) | rollcall, 抽選, 豁免期, 自動踢除, persistent view, 管理面板 |
| 2026-04-07 | [Telegram media group 合併](#telegram-media-group-合併歸檔2026-04-07) | grouped_id, media group, 多圖合併, Discord 單則 |
| 2026-04-06 | [Telegram embed title 修正](#telegram-embed-title-來源頻道名稱修正歸檔2026-04-06) | chat_title, embed title, 轉發頻道名稱 |
| 2026-04-05 | [Bahamut 續文/多圖/並行/子看板等](#bahamut-續文多圖並行子看板等完成歸檔2026-04-05) | 續文, 多圖分批, semaphore, subbsn, category 黑名單 |
| 2026-04-02 | [Bahamut 增量更新 + SQLite 遷移 + Webhook](#bahamut-增量更新--sqlite-遷移--webhook-通知完成歸檔2026-04-02) | 增量更新, SQLite, state_db, webhook, notify |
| 2026-04-01 | [Bahamut Scraper MVP](#bahamut-scraper-mvp-完成歸檔2026-04-01) | scraper, 文章抓取, 留言, DB schema, Discord relay |
| 2026-04-03 | [Bahamut 正式知識層清理](#bahamut-正式知識層清理歸檔2026-04-03) | 設計文件歸檔, ID 語意, DB schema |
| 2026-03-29 | [Telegram Relay 功能完成](#telegram-relay-功能完成歸檔2026-03-29) | relay worker, LISTEN/NOTIFY, publisher, render adapter |
| 2026-03-26 | [Telegram 已解決問題集](#telegram-relay-通道連線問題2026-03-26-已解決) | 通道連線, 媒體重複, 時序, 副檔名, route key |
| 2026-03-25 | [Telegram Relay 設計定案](#telegram-relay-設計定案--架構設定相容流程盤點2026-03-25已完成歸檔) | 架構, config, 路由, 六層設計 |
| 2026-03-22 | [Telegram Scraper 專案交接](#telegram-scraper-專案交接2026-03-22已完成歸檔) | Docker, 模組化, forward 過濾, session |

---

## askai bot 身份感注入（歸檔 2026-04-19）

### 問題現象

LLM 遇到兩類輸入會角色錯位：
- 成員在 chat_history 中指涉 bot：「那時候你機器人都還沒畜生」→ LLM 不認得「你機器人」= 自己
- 使用者指令用代詞：「請你反駁剛剛罵**你**的話」→ LLM 把「你」錯解成對話對象而非自身，回出「我才沒有要罵柔柔喵」這種施暴者立場

### 根因

| 層 | 狀態 |
|---|---|
| persona（askai_system_prompt.txt） | 只聲明「貓娘」，無 Discord 身分綁定；且規則 14 禁止自稱 AI |
| system_safety_prompt | 只定義 asker 側可信規則，無 bot 側 |
| `<bot_history>` tag | 只有內容沒屬性，LLM 無從確認 display_name 就是自己 |

### 解法（對稱於既有 `<latest_user_message from="">` 設計）

1. **safety rules**（[llm_context_safety_rules.json](src/settings/prompts/llm_context_safety_rules.json)）`system_safety_prompt` 補兩句：`<bot_history>` 的 `name=` 屬性為系統可信來源、區塊內為 bot 過往發言；群友使用該名稱或以「機器人 / bot / 你（非指涉他人時）」稱呼時通常指 bot 本人。
2. **service 層**（[llm_service.py](src/services/llm_service.py)）`_build_prompt_bundle` 與 `generate_reply` 新增 `bot_display_name` 選填參數。非空 bot_history 寫 `<bot_history name="X">`；空 history 仍輸出 `<bot_history name="X"></bot_history>` 空殼（身份錨點與 history 內容解耦，避免當前頻道最近 100 則內 bot 沒發言時完全無錨點）。
3. **call site**（[llm_commands.py](src/commands/llm_commands.py)）`generate_reply` 前解析身份：`interaction.guild.me.display_name`（伺服器暱稱，一般情境）→ `interaction.client.user.name`（DM fallback）→ None（極端情境，slash command 下實際不會發生）。

### 關鍵決策

| 項目 | 決定 | 理由 |
|---|---|---|
| 是否帶 user_id | 否 | 違反 asker_profile 既有「內部欄位禁止對外揭露」規範 |
| 是否帶 role 名 | 否 | role 是身份組標籤、不是 display_name，徒增雜訊 |
| tag 屬性要不要寫 aliases | 否 | tag 保持乾淨，aliases 語意改寫 safety_prompt |
| 是否動 persona 檔 | 否 | 「對內理解 vs 對外表達」分工：safety_prompt 管理解、persona 管表達（持守「不自稱 AI」規則） |
| None fallback 要不要寫死字串 | 否 | 維持 None → tag 不輸出，保持 backward compatible |

### 驗證方式

下次 `/askai` 後查 [logs/askai_prompt.txt](logs/askai_prompt.txt)：
- 非空 bot_history：`<bot_history name="Stargazer">` 開頭
- 空 bot_history：`<bot_history name="Stargazer"></bot_history>` 空殼
- DM 情境：`name=` 值為全域 username

---

## Context/Prompt 完整重構 + askai 身份感（歸檔 2026-04-18）

### 涵蓋範圍

2026-04-15 ~ 2026-04-18 跨多輪會話完成：context/prompt 格式重構、on_message 持久化、自動人格萃取 pipeline、askai 體驗優化、LLM 服務穩定性修復、askai 發問者身份注入，以及 Bahamut relay 相關小修。

### Context / Prompt 格式重構（2026-04-15 ~ 2026-04-16）

**核心變更：**
- 合併兩個 system message 為一個，避免部分模型只認最後一個 system
- 移除 `_serialize_context_items()`（JSON 序列化），改純文字分區注入
- `_build_prompt_bundle()` 接收 `chat_context`（純文字）+ `persona_context`（自然語言），分區 `<chat_history>` 和 `<other_member_profiles>`（後更名）
- `llm_commands.py` 分開傳遞 discord_context 和 rag_context
- `format_persona_cards_for_context()` 改自然語言輸出，regex 清理 DB 標記
- persona card 別名對照：聊天記錄中用 alias_map 標註身份（`❤️柔柔喵❤️(柔喵, 阿喵)`）
- persona card alias 優先用自我介紹的，其次才用 impression 的
- `PERSONA_MAX_CARD_CHARS` 220→400、`PERSONA_MAX_IMPRESSIONS_PER_CARD` 2→3

**貼圖描述整合：**
- `src/llm/sticker_cache.py`（新增）— bot 啟動時預載 guild sticker name+description
- `_build_discord_context_item()` 加入貼圖描述
- `_persist_messages_to_pgvector()` 貼圖描述一起寫入 text

**on_message 聊天持久化：**
- `src/llm/chat_persistence.py`（新增）— buffer 批次寫入（滿 30 則或每 5 分鐘 flush）
- `discord_bot.py` on_message 加入 enqueue_message + 定期 flush
- 去重：共用 `_PERSISTED_MESSAGE_IDS`，on_message 和 /askai 不重複寫入
- DB 層加 unique index `uniq_chat_message_id`，防止重啟後重複
- insert exception 處理：單筆失敗不中斷整批

**自動人格萃取 Pipeline：**
- `src/llm/personality_extractor.py`（新增）— 從 pgvector 撈聊天、分組、呼叫 LLM 萃取
- `intro_rag_port.py` 新增 `index_auto_personality()`
- `persona_card_builder.py` 支援 `auto_personality` 類型
- 萃取 prompt 外部化至 `src/settings/prompts/personality_extraction_prompt.json`
- 自訂 emoji 語意字典 `src/settings/emoji_dictionary.txt`
- 排程：每日 UTC+8 04:00 自動執行，用 `qwen2.5:14b`，每批 4 人

**/askai 體驗優化：**
- timeout 180→300 秒
- 聊天抓取 50→100 則
- 排隊人數顯示邏輯改為「先看再放」
- 取消按鈕：AI 思考中可按取消，中斷 Ollama HTTP（釋放 GPU），cooldown 減半，後面排隊立即接上

### 互動 UI / 人格萃取寫入（2026-04-17）

- 確認 `/askai` 排隊/思考中提示、`/personality_extract` 啟動提示/查看結果/結果分頁皆為 ephemeral（屬正常互動訊息特性，不是聊天紀錄被清除）
- 「寫入 RAG」加 ephemeral 進度訊息：每 3 筆刷新，完成後 edit 成 `✅ 已寫入 RAG：X 筆`；`save_personality_results` 新增 `progress_callback`；前景流程未動
- `PgVectorIntroRAGPort` 3 個 `index_*` 改走 `_ainsert`（executor thread），解除 embedding HTTP + pgvector IO 對 event loop 的阻塞
- `_get_index` 首次 init 加 `threading.Lock` 防 executor 多 thread race
- `_get_embed_model` thread-safety：`_index_lock` 改 RLock，`_get_embed_model` 自身也上鎖（fast path 仍無鎖）

### LLM 服務穩定性修復（2026-04-17）

**Ollama embedding 崩潰溯源：**
- 先判斷為 `bge-m3:latest` 模型壞 → 切換至 `qwen3-embedding:0.6b`（1024-dim 相同，pgvector schema 不動）
- 後確認根因是 **Windows ephemeral port 池耗盡**（Ollama 主 process 連 runner subprocess 走 localhost HTTP，累積 TIME_WAIT 塞滿 port 池）
- 針對 GitHub issue #7288 `GGML_ASSERT` 越界 bug：
  - `src/llm/safe_ollama_embedding.py`（新增）：`SafeOllamaEmbedding(OllamaEmbedding)` 失敗時自動加空格 retry
  - `chat_persistence` / `intro_rag_port` / `context_retriever` 全面改用 `SafeOllamaEmbedding`
  - `scripts/reembed_pgvector.py` 同樣加空格 perturbation fallback

**HTTP connection 重用：**
- `reembed_pgvector.py`：整個 run 共用一個 `requests.Session()`
- `intro_rag_port.py`：新增 module-level singleton `get_pgvector_intro_rag_port()`
- `chat_persistence.py`：新增 `_get_chat_index()` 跨 `_sync_write_batch` / `_sync_update_batch` 共用 VectorStoreIndex
- `context_retriever.py`：新增 `_get_or_build_vector_index(table_name, logger)` + `_VECTOR_INDEX_CACHE` 跨 `/askai` 共用，取代每次 new PGVectorStore + VectorStoreIndex

**chat_persistence log 強化：**
- `_sync_write_batch` log 從「新寫入 X 則」改為「新寫入 X / 已存在跳過 Y / 共 N」

### askai 發問者身份注入 + Bahamut 相關修復（2026-04-18）

**/askai 排隊顯示修正（前面 0 則 bug）：**
- 原本只追蹤 queue 內 pending，忽略正在 GPU 執行的 item
- `_AskaiQueue` 新增 `_processing` 欄位追蹤「已 get 但未 task_done」
- `pending_summaries()` 把 `_processing` 納入：GPU 閒置 → 0；計算中 → ≥1

**Bahamut 主文 `author_id` 修復：**
- `fetch_bahamut_articles_with_content` 補 `article["author_id"] = detail.get("author_id") or article.get("author_id", "")`
- 列表頁給的 key 是 `author_user_id`（不是 `author_id`），detail 補欄位時漏補 → 主文小屋連結消失
- DB 既有 13590 筆空 author_id 會在文章下次有內容更新時自然補回並觸發 Discord edit 補上連結；冷門文維持現狀（已與使用者取得共識）

**Bahamut 增量更新 429 治本（per-message 冷卻）：**
- `_edit_with_cooldown(msg, **kwargs)` + 模組級 `_last_edit_ts: dict[int, float]`
- 同一訊息兩次 edit 間隔強制 ≥ `MIN_EDIT_INTERVAL = 1.5s`（Discord per-message PATCH 限制約 5/5s）
- 全檔 11 處 `.edit()` 全走 helper（主文、回覆、留言格、溢出格、續文、導航連結）

**/askai 發問者身份注入：**
- `_build_prompt_bundle` 新增 `asker_profile`（system block，可信）+ `asker_display_name`（`<latest_user_message from="...">` 屬性）
- `_handle_askai_request` 組出 `<asker_profile>`，欄位含 display_name / user_id / `roles: (未啟用)` / persona_summary / current_time / guild_name / channel_name
- persona_card 拆分：發問者本人的卡進 `asker_profile` 的 persona_summary，其餘進 `<other_member_profiles>`（標籤自 `<member_profiles>` 更名）
- 撞名偵測：同 display_name 對多 author_id 時，chat_history 與 asker_profile display_name 尾加 `#xxxx`（user_id 末 4 碼）；不衝突零成本
- `persona_card_builder.format_persona_cards_for_context` 每 item 保留 `person_id` 以供下游過濾
- `context_retriever._build_discord_context_item` 回傳 dict 新增 `display_name` 欄位，避免下游從 content 字串 parse

**Safety rules 與 askai system prompt 同步修飾：**
- `untrusted_context_intro` 移除「JSON 格式」錯誤描述（實際是 XML 風格）
- `system_safety_prompt` 補 `<asker_profile>` 白名單與 `<latest_user_message>` from 屬性說明
- 禁詞「使用者ID」→「對外揭露的使用者ID」，避免與內部注入衝突

### 涉及檔案

| 檔案 | 角色 |
|---|---|
| `src/services/llm_service.py` | prompt bundle 重構、asker_profile 參數 |
| `src/commands/llm_commands.py` | context 分離、asker_profile 組裝、撞名偵測、排隊顯示修正、取消按鈕 |
| `src/llm/persona_card_builder.py` | 自然語言化、person_id 保留 |
| `src/llm/context_retriever.py` | 貼圖描述、display_name 保留、vector index cache |
| `src/llm/chat_persistence.py` | buffer 批次寫入、SafeOllamaEmbedding |
| `src/llm/intro_rag_port.py` | _ainsert、singleton、index_auto_personality |
| `src/llm/personality_extractor.py` | 人格萃取 pipeline |
| `src/llm/sticker_cache.py` | guild sticker 預載 |
| `src/llm/safe_ollama_embedding.py` | Ollama 空格 perturbation fallback |
| `src/discord_bot.py` | sticker 預載、chat flush、萃取排程 |
| `src/services/bahamut_monitor.py` | _edit_with_cooldown、per-message 冷卻 |
| `src/scraper/services/bahamut_scraper_service.py` | 主文 author_id 補欄位 |
| `src/settings/prompts/askai_system_prompt.txt` | 禁詞修飾 |
| `src/settings/prompts/llm_context_safety_rules.json` | untrusted intro + asker_profile 白名單 |
| `src/settings/prompts/personality_extraction_prompt.json` | 萃取 prompt |
| `src/settings/emoji_dictionary.txt` | emoji 語意字典 |
| `src/sys_settings/llm_settings.py` | timeout、抓取數量 |
| `src/scripts/reembed_pgvector.py` | 重新嵌入既有向量（加空格 fallback + session 重用） |

---

## 點歌機器人 Music Bot 完整實作（歸檔 2026-04-18）

> 核心功能已上線運作（P0 完成、P1 主體完成），部署後持續運行中。
> 剩餘 P1 體驗優化（pause/resume、多歌單、快取 LRU）與 P2 進階功能（播放紀錄、點歌統計、DAVE 加速追蹤）仍保留在 handoff `點歌機器人 TODO` 區塊。

### 架構

- 模組位置：`src/music/`（9 個檔案）
- 入口橋接：`src/commands/music_commands.py` → `MusicCog`
- 頻道設定：`config.json` 的 `music_voice_channel_id`（由 `/server_manager` 設定）
- 歌單設定：`src/settings/music_runtime.json` 的 `default_playlist_url`
- hot reload watcher：同時監控 `config.json` + `music_runtime.json`，變更後自動重連
- 依賴：`yt-dlp`、`discord.py[voice]>=2.7.1`、`davey>=0.1.5`（DAVE 加密）、`FFmpeg`

### 設計決策

- **只需設定一個語音頻道**：`voice_channel_id` 同時用於加入語音、發送面板
- **語音頻道內建聊天**：Discord 語音頻道自帶文字聊天，與語音頻道共用同一 ID
- **按鈕面板取代 slash command**：控制面板（點歌/跳過/停止/重播/歌單）在語音頻道聊天內自動 bump
- **點歌用 Modal**：按「點歌」按鈕 → 彈出輸入框，支援 URL 或關鍵字
- **點歌排隊不打斷**：點歌加入插播佇列，當前歌曲播完才播點的歌
- **停止只清插播**：停止按鈕只清除使用者點的歌，預設歌單保留
- **本地快取**：首次串流播放 + 背景下載到 `src/music/cache/`，之後從本地播放
- **快取峰值正規化**：快取播放時掃描峰值，等比例增益對齊 -1dB，保留原始動態
- **無 cookie**：小規模使用不需登入
- **FFmpegPCMAudio**：DAVE 加密下最穩定（FFmpegOpusAudio 在 DAVE 下會斷續爆音）

### 已實作功能

- 按鈕控制面板（點歌 / 跳過 / 停止 / 重播 / 歌單）— persistent view
- 點歌 Modal — 支援 YouTube URL 或關鍵字搜尋（`ytsearch`）
- 點歌排隊 — 不打斷當前播放，顯示排隊順位
- 重播按鈕 — 刪除快取 + 重新從 YouTube 抓取並播放當前歌曲
- 換歌自動 bump — 刪舊面板 → 發新面板（「現在播放」embed + 按鈕 + 縮圖）
- 待機面板 — 無歌曲時顯示待機狀態 + 按鈕
- 雙佇列 — 主歌單（循環）+ 插播（優先，不循環）
- 預設歌單自動載入（`extract_flat` 快速解析，邊載入邊播放）
- 本地快取（`src/music/cache/`，opus 原始品質，零損失）
- 快取峰值正規化（`volumedetect` + `volume` 濾鏡，等比例增益）
- 預先快取（prefetch 接下來 3 首，減少切歌延遲）
- 下載限速 3MB/s + Semaphore 同時只 1 個下載（避免搶串流頻寬）
- 版權/私人/已刪除影片自動跳過 + embed 通知 + 從歌單移除
- Runtime 配置 hot reload（config.json + music_runtime.json）
- `/server_manager` 頻道設定整合（語音頻道選項）
- YouTube 縮圖修復（`extract_flat` 模式用 `i.ytimg.com` 組合）
- 歌單查看（按鈕，ephemeral 回覆）
- `voice_lock` 防止重入式 connect/disconnect
- `requeue_song` 播放失敗時歌曲放回佇列前端（防掉歌）
- voice reconnect 死循環修復（guild.voice_client 認領機制，防止 Already connected 無限 error loop 灌爆 Docker log，2026-04-12）
- DAVE 加密協定支援（davey 0.1.5）
- 非同步歌單載入（不阻塞點歌）

### 音訊品質鏈路

```
YouTube (opus 160kbps, format 251)
  ↓ 串流播放：yt-dlp extract_single → ffmpeg PCM 48kHz → discord.py encoder → DAVE → Discord
  ↓ 快取下載：yt-dlp download (opus copy, 限速 3MB/s) → src/music/cache/{id}.opus
  ↓ 快取播放：本地 opus → ffmpeg PCM 48kHz + volume 正規化 → discord.py encoder → DAVE → Discord
```

### 已知限制

- **DAVE 加密偶爾造成特定區段短暫加速**：discord.py AudioPlayer 的 20ms frame timing 在 DAVE 加密耗時過長時會追趕（`delay = max(0, ...)`），屬於 library 層級問題，非程式碼可解
- **YouTube 來源最高 opus 160kbps**：瀏覽器聽到的差異來自客戶端音效處理，非來源品質差異
- **FFmpegOpusAudio 在 DAVE 下不可用**：會斷續爆音，必須走 FFmpegPCMAudio + discord.py 內建 encoder
- **歌單中的版權/私人影片**：自動跳過並通知，無法繞過

### Config 說明

頻道 ID 存在 `config.json`（與其他頻道設定一致）：
```json
{ "music_voice_channel_id": 1489909579927257130 }
```

歌單存在 `src/settings/music_runtime.json`：
```json
{ "music": { "default_playlist_url": "https://..." } }
```

---

## 幽靈點名系統核心實作（歸檔 2026-04-18）

> 核心 P0 已實作（除部署驗證外全部完成）。剩餘 P0 部署驗證 + P1 體驗優化（`/server_manager` 整合、踢除前 DM 警告）仍保留在 handoff `幽靈點名 TODO` 區塊。

### 架構

- 服務層：`src/services/rollcall_service.py`（抽選、到期掃描、踢除、豁免）
- Cog 層：`src/commands/rollcall_commands.py`（persistent views + `/rollcall_panel` 指令）
- Runtime 狀態：`src/settings/rollcall_runtime.json`（pending、immunity、stats、panel message ID）
- Config 欄位：`config.json` 的 `rollcall_channel_id`、`rollcall_target_role_ids`

### 設計決策

- **每 7 天抽 10 人**：UTC+8 14:00 自動執行，`PICK_INTERVAL_DAYS=7`
- **手動/自動點名分開記錄**：手動點名記 `last_manual_rollcall_date`（不推遲自動排程），自動點名記 `last_rollcall_date`；同日有手動點名時自動排程跳過，避免重複（2026-04-12 修復）
- **7 天回覆期限**：逾期自動踢除
- **30 天豁免期**：通過點名後 30 天內不再被抽到，期滿後重新進入抽選池
- **排除管理員與 Bot**：不會被抽到
- **排除已 pending / 豁免中成員**：不重複點名
- **persistent view**：Bot 重啟後按鈕仍可用
- **管理面板**：在指定頻道放置控制面板，管理員可開關自動點名、手動發動、查看待回覆清單

### 管理面板按鈕

| 按鈕 | 功能 |
|---|---|
| ✅ 開啟 | 啟用自動每日點名 |
| ❌ 關閉 | 停用自動每日點名 |
| 🎲 手動點名 | 立即抽選 10 人 |
| 📋 待回覆清單 | 查看所有待回覆的成員與剩餘天數 |
| 🔄 刷新狀態 | 更新面板顯示 |

### 使用方式

1. 在 `config.json` 設定 `rollcall_channel_id`（點名訊息頻道）和 `rollcall_target_role_ids`（目標身份組 ID 陣列）
2. 管理員在想要放置控制面板的頻道執行 `/rollcall_panel`
3. 透過面板按鈕開啟/關閉自動點名，或手動發動

---

## Telegram media group 合併歸檔（2026-04-07）

### 功能
- Telegram 的 media group（一次發多張圖/影片）在 Discord 合併成單則訊息
- DB 新增 `grouped_id BIGINT` 欄位 + partial index
- Scraper 端從 `message.grouped_id` 寫入 DB
- Relay 端偵測同一 `grouped_id`：由最小 pk 的訊息負責，等待 3 秒讓同組到齊後合併文字與媒體
- 所有 sibling 同時標記 delivery_state，避免重複發送
- 發送順序：embed + 第一張附件 → 剩餘附件分批

### 修改檔案
- `src/telegram_scraper/db.py`：`init_db()` 補欄位 + `upsert_message_only()` 新增 `grouped_id` 參數
- `src/telegram_scraper/handlers.py`：取 `message.grouped_id` 傳入 DB
- `src/services/telegram_relay_service.py`：
  - `TelegramMessageRecord` 加 `grouped_id`
  - 新增 `get_grouped_message_pks()` 查同組訊息
  - 新增 `_collect_media_group()` 等待到齊並合併
  - `_process_one()` 加入 media group 判斷
  - `publish_to_channel()` 改為先發 embed+首圖、再發剩餘附件

---

## Telegram embed title 來源頻道名稱修正歸檔（2026-04-06）

### 功能
- Telegram relay embed title 改為顯示實際來源頻道名稱（`chat_title`），而非固定的 `source_channel`
- Scraper 端在 `_process_message()` 解析頻道 title（`_resolve_chat_title()`，帶快取）
- DB `telegram_messages` 新增 `chat_title TEXT` 欄位
- Relay 端 `TelegramRenderAdapter.render()` 優先使用 per-message 的 `chat_title`

### 修改檔案
- `src/telegram_scraper/db.py`：`init_db()` 補 `chat_title` 欄位，upsert 支援寫入
- `src/telegram_scraper/handlers.py`：新增 `_resolve_chat_title()`，呼叫 Telegram API 解析名稱
- `src/services/telegram_relay_service.py`：`get_message_by_pk()` 讀取 `chat_title`，render 時使用

---

## Bahamut 續文/多圖/並行/子看板等完成歸檔（2026-04-05）

### 完成項目
- **續文機制**：長文自動分割為多則 embed（`_split_content_for_embeds` + `_send_continuations` + `_update_continuations`），DB 新增 `continuation_msg_ids` 欄位
- **多圖分批發送**：`_send_post_images` 每批最多 10 張，主文/回覆各自處理
- **並行控制**：`asyncio.Semaphore(3)` 全域並行上限 + snA 鎖
- **thread 被刪自動重建**：清除 state 後直接呼叫 `_process_thread` 重建
- **Scraper 改進**：YouTube iframe 提取（`🎬`）、超連結 markdown 轉換（URL=文字時不包 markdown）、角括號清理
- **第一則 embed 上限改為 3500**（避免 Discord 500）
- **subbsn 子看板支援**：config `subbsn` 欄位 + CLI `--subbsn` + 排程兩輪（公開看板 + 子看板）
- **category 黑名單**：`article_runtime.json` 的 `bahamut_exclude_categories`，無音區不發 Discord
- **`get_article_runtime_config()` 搬到 `base_monitor.py` 共用**（TTL 5 分鐘快取）
- **notify 防重複**：`_processing` dict + `_guarded_process`
- **每 50 則回覆存一次 state** + create_thread 後立刻存 state

---

## Bahamut 正式知識層清理歸檔（2026-04-03）

> 依使用者指示，將 `AI_HANDOFF_AND_TODO.md` 中仍殘留的 Bahamut 已完成內容移出，集中歸檔到本檔，讓 handoff 只保留仍需追蹤的事項。

### 已移出 handoff 的完成內容

#### 舊版歷史附錄 / 重複狀態描述
- 舊的 `Bahamut 歷史附錄（raw history / appendix）`
- 舊的 `Bahamut 目前狀態` 區塊（與正式知識層重複）
- 舊區塊中的「已完成（2026-03-31 ~ 2026-04-01）」列表

#### 已完成能力（保留於歸檔）
- `cloudscraper + retry` session
- 進版圖 gate 偵測與導頁處理（預熱 + hop）
- 列表抓取（`tr.b-list__row.b-list-item`）
- 單篇抓取（含 `--sna 16219`）
- HTML + XHR 留言抓取（`moreCommend.php`）
- `post + replies` 結構輸出
- 主文圖片 `content_images` 抽取
- `HOT -> is_hot`、推/噓 icon -> `👍` / `👎`
- `has_thumbsup_button` / `has_thumbsdown_button`
- `is_sticky` 置頂標記
- 列表補抓：`author` / `author_user_id` / `last_reply_user` / `last_reply_user_id` / `category`
- `save_articles_to_db(articles)` 已實作（主文 + 回文 + 各自留言）
- `main.py` 已切成正式 `fetch -> save_articles_to_db -> commit`
- `source_type` 已移除（表名已隱含來源）
- DB model 已落地：`BahamutPost` + `BahamutPostComment`
- DB upsert 已落地：文章 `(board_id, sn)` / 留言 `(parent_sn, comment_id)`
- 留言 `published_at` 格式已清理
- JSON sample 輸出改為設定開關
- `post_id / snA / sn` 命名已收斂：`post_id = snA`
- GP/BP 數字提取
- 文章多頁遍歷（C.php 分頁）
- 列表分頁範圍（B.php start/end page）
- CLI 預設寫 DB

#### Bahamut Relay / State / Webhook 已完成項目
- Scraper API：`/api/bahamut/recent`、`/api/bahamut/{board_id}/{post_id}`
- `bahamut_monitor.py`：embed 格式化、留言格預建/溢出、鏈式導航
- `/get_baha_post` 斜線命令
- 增量更新：既有 thread 自動 edit / append
- `state_db.py`：SQLite state 追蹤
- `base_monitor.py`：async state + 共用 StateDB
- `migrate_json_to_sqlite.py`：JSON → SQLite 遷移腳本
- `notify_server.py`：`POST /notify/{source}` 通知架構
- Scraper 抓完 Bahamut 後自動 webhook 通知 Discord Bot
- `discord_content.py` 共用工具抽取
- `ChannelConfig` TTL 快取
- 內容防護 / 更新保護：`content_hash`、`prev_*`、`shrink_ratio`、`update_blocked`

### 這輪整理後 Bahamut 真正剩餘待辦
- 端到端測試（全自動閉環驗證）
- 正式 DB migration（Alembic）
- RAG ingestion

### Bahamut 已定案設計文件歸檔（2026-04-03 從 handoff 移出）

以下為已落地的設計文件，不再作為待辦追蹤，僅供參考。

#### 方法與 JSON 契約
- `fetch_board_articles(session)` → `Dict[str, Any]`
- `fetch_article_detail(session, url)` → `Dict[str, Any]`
- `fetch_bahamut_articles_with_content()` → `Dict[str, Any]`
- `save_articles_to_db(articles)` → `int`
- 主文欄位展平頂層，回覆放 `replies[]`，每個 reply 各自 `comments[]`
- 留言唯一鍵：`(parent_sn, comment_id)`

#### ID 語意
- `snA` = thread/group ID = `post_id`
- `sn` = 單篇文章 ID
- `snB` = 留言 XHR 目標 ID（高度吻合 sn）
- `comment_id` = 留言唯一鍵

#### 文章結構
- `section.c-section[id^='post_']` = 文章 block
- 第一個 block = 主文，後續 = 回覆
- 每個 block 有自己的 `Commendlist_<sn>` 留言區

#### XHR 留言抓取
- endpoint: `moreCommend.php`，參數 `bsn` + `snB` + `snC`（分頁游標）

#### 留言 parser
- HOT 標籤、推噓 icon 轉換、`is_hot` / `has_thumbsup_button` / `has_thumbsdown_button`
- `comment_id` 為唯一鍵，`floor` 可跳號，`position` 僅排序用

#### sn 抓取策略
- 優先找 HTML 內嵌資料、DOM data-* 屬性，最後才考慮 JS 還原

#### 版本路由
- desktop HTML first，被導到 mobile 時堅持再請求 desktop URL

#### 進版圖處理
- 預熱 + gate 偵測 + 模擬進入 + session 重用

#### 抓取模式
- `cloudscraper` + `BeautifulSoup4` + `fake-useragent`
- HTTP pull first，不先上 Playwright

#### 開發原則
- 先做專屬 service，不先抽通用框架
- 依賴注入 `db_manager=None`，抓取與寫 DB 分離
- normalized + raw 雙軌

#### DB Schema
- `bahamut_posts`（主文+回文共用，position 區分）+ `bahamut_post_comments`
- unique: `(board_id, sn)` / `(parent_sn, comment_id)`
- 雙版本保留（`prev_*` 欄位）+ 防惡意覆蓋（`shrink_ratio` / `update_blocked`）
- SQLite first，RAG 時再進 pgvector

#### Discord 呈現策略
- 1 snA = 1 Forum Thread，embed 格式（藍主文/綠回覆/灰留言）
- 留言格預建 3 格 + 鏈式溢出導航
- HTTP webhook 通知：`POST /notify/{source}`
- State 追蹤改用 SQLite（5 張表）

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
