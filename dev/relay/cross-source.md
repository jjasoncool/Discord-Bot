# 跨來源整合

<!-- 給 AI：這份是歸檔檔，改之前先看完這段
結構：上半部（一頁看懂、時間線、定案與理由、踩過的坑）是整理過的重點；「## 原文」以下是當時的紀錄。
新增一段：
1. 原文放在「## 原文」目錄表下方的最前面，照現有各段的格式（## 標題、> 摘要與關鍵字、<details> 包正文，標籤前後各空一行）。
2. 目錄表加一列；dev/README.md 的「依日期」加一列。
3. 同一輪更新上半部，並把下面的「整理到」改成新段的日期。
不要改：原文正文、既有的段落標題（README 和其他檔用標題當錨點）。
找細節用搜尋，不必整份讀。改完跑 python3 dev/check.py。完整規則：AI_HANDOFF_AND_TODO.md「本檔維護規則」的「歸檔放哪」。
整理到：2026-10-28
-->

> 現況、待決與待做以交接檔為準：[跨來源整合](../../AI_HANDOFF_AND_TODO.md#跨來源整合)。
> 這裡是歷史。上半部是整理過的重點；「原文」是當時的紀錄，提到的檔名、函式、狀態可能已經改了。原文提到的 `TODO-completed.md` 是 2026-11-07 以前的單一歸檔檔，內容都拆到 `dev/` 了，從 [dev/README.md](../README.md) 找。

## 一頁看懂

這個主題管各個轉發來源（官方文章、FB、PTT、Telegram）能共用哪些流程：讀資料、事件模型、路由、發文、設定讀寫。

- **03-25 共識**：先整合讀資料，再整合 render 與路由，發文端放最後。Article、FB、PTT 取文與去重很像，先抽風險低；發文端差異大。
- **04-07 規劃**：六步計畫（`SourceFetchPort`、無損事件模型、`MessageRouteResolver`、`DiscordMessagePublisher`、`MessageRelayWorker`、設定統一）。格式保留的原則是發文端只照 `RenderPlan` 執行，內容與版型留在各來源的 Adapter。FB 改成爬蟲推送、不再輪詢。
- **到 10-02 實際做到的**：Telegram 自成一套分層；Article、FB、PTT、IT 與活動發文共用 `post_to_channel`；Telegram 路由可在 `/server_manager` 設定。3 月規劃剩下的，照 09-29 起「沿用現有架構、最小修改」的原則，要做之前重新評估值不值得。
- **10-28**：提議 Telegram 的 Discord 端設定改成「以服務為單位」：Discord 端只記 Telegram 送到哪個頻道，要聽哪些 Telegram 頻道是爬蟲自己的設定，兩個容器只透過資料庫溝通。TG-Q1～Q5 已答，TG-Q6～Q7 待答。

**歸檔時（10-28）的狀態**

- [x] Telegram 轉發的分層（Repository、RouteResolver、RenderAdapter、Publisher、Worker）
- [x] Article、FB、PTT、IT 與活動發文共用 `utils.discord_content.post_to_channel`
- [x] FB 改成爬蟲推送模式
- [ ] 讀資料整合、統一事件模型、其他來源的路由與 worker（3 月規劃剩下的）
- [ ] 設定讀寫統一到 `ChannelConfig`：10-02 盤點還有 7 處直接 `open(config.json)`
- [ ] Telegram 設定改以服務為單位：TG-Q6（開關切 off 時暫停或跳過）、TG-Q7（整段重送放哪）待答，還沒實作

最新狀況看交接檔。

## 時間線

| 日期 | 發生什麼 | 結果 |
|---|---|---|
| 03-25 | 跨來源整合的順序 | 共識：先讀資料 → 再 render／路由 → 發文端最後 |
| 04-07 | 跨來源整合專區規劃 | 六步計畫、格式保留策略、`RenderPlan` 結構；Telegram 轉發已完成 |
| 09-29 | 原則改成「沿用現有架構、先指出不合理處再最小修改」 | 3 月規劃剩下的項目要重新評估 |
| 10-02 | 改寫交接檔區塊並盤點 | 還有 7 處直接 `open(config.json)` |
| 10-28 | 提議 Telegram 設定改以服務為單位，出 TG-Q1～Q7 | Q1～Q5 已答；Q6、Q7 待答 |

## 定案與理由

| 決定 | 為什麼 |
|---|---|
| 整合順序：先讀資料，再 render 與路由，發文端最後（03-25） | Article、FB、PTT 的取文與去重流程高度相似，先抽讀資料風險低；發文端差異（文字頻道、論壇串、留言增量、圖片策略）大，適合後置 |
| 發文端只執行 `RenderPlan`，內容與版型留在各來源的 Adapter | 避免格式被洗平：PTT、FB、Article 各自保持原本的發文順序與版型，發文端只做可靠執行 |
| Adapter 無損封裝，來源特有欄位一律留在 `source_payload_raw` | 發文端只依賴 `normalized_payload`，不碰來源細節 |
| 3 月規劃剩下的項目，動手前照新原則重新評估（09-29） | 原則是「沿用現有架構、先指出不合理處再最小修改，不另起一套分層」 |
| Telegram 改成一般綁頻道，一個 `telegram_relay_channel_id`（TG-Q1 選 A） | 和其他轉發一致，現在也只有一個目的頻道 |
| 總開關 `telegram_relay_enabled` 搬到 `switches.json`（TG-Q2 選 B；當時建議是 A 拿掉） | 原文沒記使用者的理由 |
| 保留重送功能（TG-Q3；當時建議是拿掉） | 原文沒記使用者的理由 |
| 拿掉爬蟲設定的 `source_channel`，只留 `source_channels`（TG-Q4） | Discord 端不再讀爬蟲的設定，兩個容器只透過資料庫溝通 |
| 其他轉發的 key 命名不一致先不管（TG-Q5） | 排到下一輪再談 |

## 踩過的坑

- **Telegram 路由寫入和讀取的 key 不一致**：用來源名稱當 key 寫入，但只有 chat_id 當 key 查得到（記在「Telegram 訊息 LLM 過濾」區塊）。
- **路由表的 key 看起來是單一來源專用，其實三個來源都靠它**：先用 chat_id 查，查不到就拿爬蟲 `runtime_config.json` 的名稱查；bot 為此直接讀爬蟲容器的設定檔。
- **`config.json` 的整段重送值沒清掉，每次重啟都會再送一次**：而且用名稱當 key 時，同一個訊息編號會套到每個來源各自的頻道。
- **`telegram_relay_enabled` 只在 worker 啟動時讀**：`is_telegram_relay_enabled` 沒有人呼叫。
- **改 `config.json` 的 key 要先加新的、重啟、再刪舊的**：舊程式每則訊息都讀路由，先刪會斷。
- **開關切 off 若做成「跳過」要另外記紀錄**：不然重啟時的啟動補償會把跳過的訊息又送出去（TG-Q6 選項 B 的代價）。
- **有些 Telegram 訊息沒有頻道標題**：資料庫裡兩個來源共 115 則，只有重送時看得到；提議沒標題時寫「Telegram」。

## 原文

新的在前。每段標題下面是摘要，正文在「展開原文」裡。

| 日期 | 段落 | 摘要 |
|---|---|---|
| 2026-10-28 | [規劃剩餘項目與 Telegram 設定](#跨來源整合3-月規劃剩餘項目與-telegram-設定改以服務為單位的討論2026-03-2510-28歸檔-2026-11-07原至-2026-10-02) | 發文已共用 post_to_channel，其餘要重新評估；10-28 提議 Telegram 設定以服務為單位。 |
| 2026-04-07 | [跨來源整合原規劃（04-07）](#跨來源整合專區改寫前原文歸檔-2026-10-02原-2026-04-07) | 03-25 共識的整合順序與六步計畫、RenderPlan 格式保留策略、各來源入口分流與 P0～P2 待辦。 |

## 跨來源整合：3 月規劃剩餘項目與 Telegram 設定改以服務為單位的討論（2026-03-25～10-28）（歸檔 2026-11-07，原至 2026-10-02）

> 發文已共用 post_to_channel，其餘要重新評估；10-28 提議 Telegram 設定以服務為單位。
>
> 關鍵字：SourceFetchPort、MessageRouteResolver、MessageRelayWorker、post_to_channel、telegram_channel_routes、telegram_relay_channel_id、telegram_replay_from_message_id、source_channel、TG-Q1～Q7、ChannelConfig

<details>
<summary>展開原文（約 3,518 字）</summary>

> 從 `AI_HANDOFF_AND_TODO.md`「跨來源整合專區（規劃；發文已共用）」區塊（`cross-source-integration`）瘦身前的完整原文；交接檔只留現況、規則與坑、未定案、待做。

> **已完成的部分**：Telegram 轉發自成一套分層（`TelegramMessageRepository`、`MessageRouteResolver`、`TelegramRenderAdapter`、`DiscordMessagePublisher`、`MessageRelayWorker`，都在 `services/relay/telegram_relay_service.py`）；Article、FB、PTT、IT 與活動發文已共用 `utils.discord_content.post_to_channel`（論壇／文字頻道分流、附件分批、失敗退純文字）；FB 改推送模式；Telegram 路由可在 `/server_manager` 設定。原規劃全文（2026-03-25 共識、RenderPlan 結構、遷移原則）已歸檔。
>
> **動手前先對照**：2026-09-29 起的原則是「沿用現有架構、先指出不合理處再最小修改，不另起一套分層」。下面這些是 3 月規劃裡還沒做的，要做之前照這條重新評估值不值得。

### 還沒做

- [ ] 讀資料整合：`SourceFetchPort`＋各來源實作、`SourceFetchOrchestrator`（各來源原本的去重邏輯不動）
- [ ] 統一事件模型：無損封裝（`normalized_payload`／`source_payload_raw`／`source_meta`），目前只有 Telegram 有自己的 RenderAdapter
- [ ] Route 規則從流程碼抽離、其他來源納入（目前只有 Telegram 有 `MessageRouteResolver`）
- [ ] 視穩定度把其他來源的事件觸發收斂進 `MessageRelayWorker`
- [ ] 設定讀寫統一到 `ChannelConfig`：還有 7 處直接 `open(config.json)`（10-02 盤點）
- Telegram 路由設定的既有 bug（用來源名稱當 key 寫入，只有 chat_id 當 key 查得到）記在「Telegram 訊息 LLM 過濾」區塊的「順便發現的既有問題」
- **Telegram 的 Discord 端設定改成「以服務為單位」（2026-10-28 提出；TG-Q1～Q5 已答，TG-Q6～Q7 待答）**
  - 使用者回答（10-28 09:3x）：TG-Q1＝A，改成一般綁頻道（現在的 `telegram_channel_routes` 可以手改、也可以用綁頻道面板的「Telegram 路由設定」自訂視窗寫，`seele_ww_leak` 這個小寫 key 是視窗寫的格式）；TG-Q2＝B，總開關搬到 `switches.json`；TG-Q3＝要保留重送；TG-Q4＝拿掉 `source_channel`；TG-Q5＝先不管。
  - 已有的單則重送：`/resend_article type:telegram id:<db id 或 msg id>`（不合併相簿、不過濾、不寫發送紀錄）。`config.json` 的重送是「從某則開始全部重送」：啟動時把游標倒回去、每則照正常流程（合併、過濾、發送紀錄）強制送；要重啟才生效，**值沒清掉的話之後每次重啟都會再送一次**。
  - TG-Q6 開關切到 off 時：A 暫停，不送、不推游標，切回 on 從停下的地方接著送（＝現在 `telegram_relay_enabled=false` 再打開的效果；建議）／B 跳過，切回 on 只送之後的新訊息（要另外寫「頻道 0」紀錄，否則重啟的啟動補償會把跳過的又送出去）。
  - TG-Q7 整段重送放哪：A 做成指令，`/resend_article type:telegram` 加「這則之後全部」選項，照正常流程排進 worker、不用重啟、做完就結束（建議；`config.json` 只留綁定）／B 留在 `config.json`，改成一個 db id（不分來源），照舊要重啟、用完要清掉。
  - 動 `config.json`、`switches.json` 前要使用者同意。
  - 現況：`config.json` 有三個 key——`telegram_relay_enabled`（只在 worker 啟動時讀；`is_telegram_relay_enabled` 沒人呼叫）、`telegram_channel_routes`（`{"seele_ww_leak": [頻道]}`，key 看起來是 Seele 專用，實際上三個來源都靠它：先用 chat_id 查、查不到就拿爬蟲 `runtime_config.json` 的 `source_channel` 名稱查）、`telegram_replay_from_message_id`（`{"seele_ww_leak": null}`，null＝沒作用；用名稱當 key 時同一個訊息編號會套到每個來源各自的頻道）。bot 為了這個名稱退回與 embed 標題的備用名稱，直接讀爬蟲容器的 `runtime_config.json`。其他轉發（官方文章、IT 快訊、論壇文章）都是一個 `<用途>_channel_id`、走一般綁頻道；只有 Telegram 有自己的表與自訂輸入視窗。
  - 提議（機制一句話：Discord 端只記「Telegram 這個服務送到哪個頻道」，要聽哪些頻道是爬蟲自己的設定，兩個容器只透過資料庫溝通）：`config.json` 三個 key 換成 `telegram_relay_channel_id`；`MessageRouteResolver` 改讀 `ChannelConfig.get_configured_id`，拿掉名稱退回、讀爬蟲設定、`is_telegram_relay_enabled`；`TelegramRenderAdapter` 沒頻道標題時寫「Telegram」（DB 裡 Seele 有 89 則、chat 2057132858 有 26 則沒標題，只有重送時看得到）；`channel_registry` 的 `_TelegramRouteInputModal` 換成一般 `register_channel`；爬蟲 `tg_config.py` 拿掉 `source_channel` 與 `TELEGRAM_SOURCE_CHANNEL`（compose、.env 都沒設），重抓的備用取清單第一個。改 `config.json` 的順序：先加新 key → 重啟 discord-bot → 再刪舊 key（舊程式每則讀路由，先刪會斷）。
  - TG-Q1 Discord 端形狀：A 一個 `telegram_relay_channel_id`、一般綁頻道（建議：和其他轉發一致，現在也只有一個目的頻道）／B 保留每來源一張表、key 只收 chat_id（真要分頻道才需要）／C 所有轉發收成一個 `relays` 區塊（範圍是全部轉發，另一輪）。
  - TG-Q2 總開關 `telegram_relay_enabled`：A 拿掉，沒綁頻道＝不轉發（建議，同其他轉發）／B 搬到 `switches.json`。
  - TG-Q3 重送：A 拿掉，要重送時再寫一次性腳本、用 DB 的 message_pk 指定（建議：6 月加了之後一直是 null）／B 留著但 key 只收 chat_id／C 不動。
  - TG-Q4 爬蟲 `runtime_config.json` 的 `source_channel`：拿掉、只留 `source_channels`（建議）。
  - TG-Q5 其他轉發的 key 命名不一致（`article_monitor_channel_id`、`forum_article_channel_id`、`hardware_news_channel_id`）要不要一起改名：建議下一輪再談；`forward_whitelist` 名稱與自動補的 chat_id 混在一起、主來源列在裡面是多餘的，也排下一輪。

</details>

## 跨來源整合專區（改寫前原文，歸檔 2026-10-02，原 2026-04-07）

> 03-25 共識的整合順序與六步計畫、RenderPlan 格式保留策略、各來源入口分流與 P0～P2 待辦。
>
> 關鍵字：SourceFetchPort、RenderPlan、DiscordMessagePublisher、格式保留策略、2026-03-25 共識

<details>
<summary>展開原文（約 3,505 字）</summary>

<!-- @meta
id: cross-source-integration
type: STATE
status: confirmed
depends_on: []
affects: [project-architecture]
last_confirmed: 2026-04-07
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

</details>
