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
| 點歌機器人（Music Bot） | 已上線運作 | 85% | [點歌機器人](#點歌機器人專區) |
| 跨來源整合（Article/FB/PTT/TG） | 有方向，尚未全面收斂 | 35% | [跨來源整合](#跨來源整合專區) |
| Bahamut RAG / AI 整合 | 尚未開始 | 5% | [RAG TODO](#第三階段整合-ai--pgvector--rag) |
| 幽靈點名系統（Roll Call） | 已實作，待部署驗證 | 80% | [幽靈點名](#幽靈點名系統專區) |
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

## 點歌機器人專區

<!-- @meta
id: music-bot
type: STATE
status: confirmed
depends_on: [project-architecture]
affects: []
last_confirmed: 2026-04-10
-->

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

- [x] 按鈕控制面板（點歌 / 跳過 / 停止 / 重播 / 歌單）— persistent view
- [x] 點歌 Modal — 支援 YouTube URL 或關鍵字搜尋（`ytsearch`）
- [x] 點歌排隊 — 不打斷當前播放，顯示排隊順位
- [x] 重播按鈕 — 刪除快取 + 重新從 YouTube 抓取並播放當前歌曲
- [x] 換歌自動 bump — 刪舊面板 → 發新面板（「現在播放」embed + 按鈕 + 縮圖）
- [x] 待機面板 — 無歌曲時顯示待機狀態 + 按鈕
- [x] 雙佇列 — 主歌單（循環）+ 插播（優先，不循環）
- [x] 預設歌單自動載入（`extract_flat` 快速解析，邊載入邊播放）
- [x] 本地快取（`src/music/cache/`，opus 原始品質，零損失）
- [x] 快取峰值正規化（`volumedetect` + `volume` 濾鏡，等比例增益）
- [x] 預先快取（prefetch 接下來 3 首，減少切歌延遲）
- [x] 下載限速 3MB/s + Semaphore 同時只 1 個下載（避免搶串流頻寬）
- [x] 版權/私人/已刪除影片自動跳過 + embed 通知 + 從歌單移除
- [x] Runtime 配置 hot reload（config.json + music_runtime.json）
- [x] `/server_manager` 頻道設定整合（語音頻道選項）
- [x] YouTube 縮圖修復（`extract_flat` 模式用 `i.ytimg.com` 組合）
- [x] 歌單查看（按鈕，ephemeral 回覆）
- [x] `voice_lock` 防止重入式 connect/disconnect
- [x] `requeue_song` 播放失敗時歌曲放回佇列前端（防掉歌）
- [x] voice reconnect 死循環修復（guild.voice_client 認領機制，防止 Already connected 無限 error loop 灌爆 Docker log，2026-04-12）
- [x] DAVE 加密協定支援（davey 0.1.5）
- [x] 非同步歌單載入（不阻塞點歌）

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

### 點歌機器人 TODO

<!-- @meta
id: music-bot-todo
type: TODO
status: confirmed
last_confirmed: 2026-04-10
-->

**P0（已完成）：**
- [x] 透過 `/server_manager` 設定語音頻道
- [x] 部署驗證：bot 可加入語音頻道並播放
- [x] Docker 容器有 FFmpeg、yt-dlp、davey

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
last_confirmed: 2026-04-12
-->

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

### 幽靈點名 TODO

<!-- @meta
id: rollcall-todo
type: TODO
status: confirmed
last_confirmed: 2026-04-11
-->

**P0（核心）：**
- [x] 每日自動抽選 + 點名訊息發送
- [x] 「我是活人」按鈕回覆處理
- [x] 7 天逾期自動踢除
- [x] 30 天豁免期管理
- [x] 管理員控制面板（開/關/手動/查看）
- [x] persistent view（重啟後按鈕仍可用）
- [ ] 部署驗證

**P1（體驗優化）：**
- [ ] `/server_manager` 整合（透過下拉選單設定頻道與身份組）
- [ ] 踢除前 DM 最後警告

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
