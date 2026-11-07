# 產品能力規劃

<!-- 給 AI：這份是歸檔檔，改之前先看完這段
結構：上半部（一頁看懂、時間線、定案與理由、踩過的坑）是整理過的重點；「## 原文」以下是當時的紀錄。
新增一段：
1. 原文放在「## 原文」目錄表下方的最前面，照現有各段的格式（## 標題、> 摘要與關鍵字、<details> 包正文，標籤前後各空一行）。
2. 目錄表加一列；dev/README.md 的「依日期」加一列。
3. 同一輪更新上半部，並把下面的「整理到」改成新段的日期。
不要改：原文正文、既有的段落標題（README 和其他檔用標題當錨點）。
找細節用搜尋，不必整份讀。改完跑 python3 dev/check.py。完整規則：AI_HANDOFF_AND_TODO.md「本檔維護規則」的「歸檔放哪」。
整理到：2026-10-02
-->

> 現況、待決與待做以交接檔為準：[產品能力 TODO](../../AI_HANDOFF_AND_TODO.md#產品能力-todo)。
> 這裡是歷史。上半部是整理過的重點；「原文」是當時的紀錄，提到的檔名、函式、狀態可能已經改了。原文提到的 `TODO-completed.md` 是 2026-11-07 以前的單一歸檔檔，內容都拆到 `dev/` 了，從 [dev/README.md](../README.md) 找。

## 一頁看懂

這個主題管功能之外的產品規劃：怎麼拿到使用數據、讓 bot 更好玩、提升回覆品質，以及什麼時候才值得做 SFT。另外收了一個已經做完的「社群 ID 查詢」。

- **03-31 規劃**：分四階段。Phase 0 先拿數據（/askai 👍／👎、回饋日誌、每日 KPI）；Phase 1 提升好玩度（每日話題、印象小卡、梗庫金句、輕量遊戲化）；Phase 2 品質（Prompt A/B、模型路由、RAG 召回評估集）；Phase 3 資料成熟後再做 SFT，先拿小模型做 DPO／ORPO 實驗。
- **04-19～04-20**：社群 ID 查詢的 Step 1～6 做完並部署驗證：在面板輸入 PTT 或巴哈的帳號，查他近期的發言。PTT 留言用 SQLite JSON1 查，實測 p95 < 30ms，爬蟲資料表不用改。
- **10-02 盤點**：3 月的四階段規劃都還沒做。後來的相關進展：插話已經用 `ai_interactions` 記反應，/askai 還沒有；招牌梗（`signature_tag`）已在累積各人的梗；GPU 一次只放得下一顆大模型，所以全部共用同一顆。SFT 決策門檻從架構總覽搬到這裡。

**歸檔時（10-02）的狀態**

- [x] 社群 ID 查詢：查詢核心、面板、部署驗證（04-20）
- [ ] Phase 0：/askai 快速回饋、回饋日誌、每日 KPI
- [ ] Phase 1：每日話題、印象小卡、梗庫金句、輕量遊戲化
- [ ] Phase 2：Prompt A/B、模型路由、RAG 召回評估集
- [ ] Phase 3：蒐集 3k～10k 則高品質多輪對話後的 DPO／SFT

最新狀況看交接檔。

## 時間線

| 日期 | 發生什麼 | 結果 |
|---|---|---|
| 03-31 | 產品能力 TODO 四階段規劃 | Phase 0～3，預估 Phase 0 一週、Phase 1 一到兩週、Phase 2 兩週 |
| 04-19 | 社群 ID 查詢 Step 1～5 | JSON1 查詢 p95 < 30ms，原定的 PTT 索引 migration 取消；新表 `community_lookup_threads`；`/server_manager` 加「社群查詢頻道」 |
| 04-20 | 社群 ID 查詢 Step 6 部署驗證 | 累積 13 筆以上查詢，PTT 與巴哈兩個來源都驗過 |
| 10-02 | 盤點產品 TODO | 3 月的規劃都還沒做；SFT 決策門檻從架構總覽搬來 |

## 定案與理由

| 決定 | 為什麼 |
|---|---|
| 取消原定的 PTT 作者索引 migration，爬蟲資料表零變更 | 時間索引 `ix_ptt_posts_published_at` 早已存在，SQLite 先走它縮小範圍再做 `json_each`；實測 p95 < 30ms，判準是 < 500ms |
| SFT 三個條件都滿足才投入，否則先做產品迭代＋資料閉環 | 原文只列條件：有足量高品質資料（不是噪音對話）、有清楚的評估集與 KPI、prompt／RAG／模型路由都優化過仍卡住 |

## 踩過的坑

- **原本以為要加 PTT 作者索引，其實不用**：爬蟲的 `models.py` 早已替發文時間加了索引，`EXPLAIN QUERY PLAN` 顯示查詢先走它。動資料表之前先實測、看查詢計畫。

## 原文

新的在前。每段標題下面是摘要，正文在「展開原文」裡。

| 日期 | 段落 | 摘要 |
|---|---|---|
| 2026-10-02 | [產品能力 TODO（10-02 盤點）](#產品能力-todo2026-03-規劃phase-03歸檔-2026-11-07原至-2026-10-02) | 3 月的 Phase 0～3 到 10-02 都還沒做，標上後來的相關進展，並收進 SFT 決策門檻。 |
| 2026-04-19 | [社群 ID 查詢實作完成](#社群-id-查詢-phase-0-step-1-5-實作完成歸檔-2026-04-19) | 用 PTT、巴哈帳號查近期發言：JSON1 效能驗證、新表、查詢核心、面板；04-20 部署驗證通過。 |
| 2026-03-31 | [產品能力 TODO（03-31 原文）](#產品能力-todo改寫前原文歸檔-2026-10-02原-2026-03-31) | 最早的四階段規劃：先拿數據、提升好玩度、品質優化、資料成熟後再做 SFT，附時程估計。 |

## 產品能力 TODO：2026-03 規劃（Phase 0～3）（歸檔 2026-11-07，原至 2026-10-02）

> 3 月的 Phase 0～3 到 10-02 都還沒做，標上後來的相關進展，並收進 SFT 決策門檻。
>
> 關鍵字：產品 TODO、回饋、KPI、每日話題、梗庫、遊戲化、Prompt A/B、模型路由、RAG 評估集、SFT、DPO

<details>
<summary>展開原文（約 841 字）</summary>

> 從 `AI_HANDOFF_AND_TODO.md`「產品能力 TODO」區塊（`product-todo`）瘦身前的完整原文；交接檔只留現況、規則與坑、未定案、待做。

> 2026-03 的規劃，到 2026-10-02 都還沒做（盤點過）。原文已歸檔；這裡標上後來的相關進展。

### Phase 0：先拿數據
- [ ] `/askai` 回覆後加快速反饋（👍／👎 或按鈕）——插話已經有 `ai_interactions` 記反應，/askai 還沒有
- [ ] 寫入回饋日誌（問題、回覆、model、context meta、feedback）
- [ ] 每日 KPI 彙總（互動量、滿意率、平均回覆長度、失敗率）

### Phase 1：提升好玩度
- [ ] 「每日話題／今日任務」指令
- [ ] 「群友印象小卡」展示指令
- [ ] 「梗庫／金句」功能——招牌梗（`signature_tag`）已在內部累積各人的梗，可以拿它當資料來源；金句可跟「Reaction 統計」的每週金句合併
- [ ] 輕量遊戲化：連續互動天數、活躍徽章

### Phase 2：品質優化
- [ ] Prompt A/B 實驗（至少 2 組 system prompt）
- [ ] 模型路由（閒聊／技術問答／審核分流）——目前 GPU 一次只放得下一顆大模型（見 ComfyUI 區塊），全部共用同一顆
- [ ] RAG 召回評估集（固定 50～100 題做離線比較）

### Phase 3：資料成熟後再做 SFT
- [ ] 蒐集 3k～10k 高品質多輪對話（含偏好標註）
- [ ] 先做偏好對齊（DPO／ORPO）小模型實驗
- [ ] 若明顯優於 prompt-only，再擴大 SFT

**SFT 決策門檻**（從架構總覽搬來）：有足量高品質資料（非噪音對話）、有清楚的評估集與 KPI、已做過 prompt／RAG／模型路由優化仍卡住——三者都滿足才投入 SFT，否則先做產品迭代＋資料閉環。

</details>

## 社群 ID 查詢 Phase 0 Step 1-5 實作完成（歸檔 2026-04-19）

> 用 PTT、巴哈帳號查近期發言：JSON1 效能驗證、新表、查詢核心、面板；04-20 部署驗證通過。
>
> 關鍵字：community_lookup、PTT JSON1、巴哈 ORM、panel modal、日期 hybrid section、slot 切割

<details>
<summary>展開原文（約 1,370 字）</summary>

### 完成內容

| Step | 內容 |
|---|---|
| 1 | JSON1 效能驗證 script (`src/scripts/bench_ptt_comment_lookup.py`)。對現有 articles.db（810 篇 / 39,890 留言 / 367 MB）實測，全部 query p95 < 30ms（< 500ms 判準）。意外收穫：`ix_ptt_posts_published_at` 早已存在（scraper models.py 已加 `index=True`），EXPLAIN QUERY PLAN 顯示 SQLite 已先走時間 index 縮小範圍再做 `json_each`，所以 `idx_ptt_author` 完全不必加，原定 PTT index migration 取消 — scraper DB schema 零變更 |
| 2 | `state_db` 新表 `community_lookup_threads` + CRUD（COALESCE 部分更新、smoke test 通過）|
| 3 | `services/community_lookup_service.py` 查詢核心（PTT JSON1 + 巴哈 ORM + 模糊候選；對真實 DB smoke test：lovez04wj06 30 天查到 618 則留言、坂坂悠模糊候選排序正確）|
| 4 | `commands/community_lookup_commands.py`（Panel View、Modal、ControlMessageView、Flow 含日期 hybrid / slot 切割 / 父頻道通知 / bump，全部 smoke test 通過）|
| 5 | `/server_manager` 加「社群查詢頻道」選項 + 設定完自動部署 panel；`discord_bot.py` 已掛入 `COMMAND_MODULES` |

### 涉及檔案

**新增：**
- `src/services/community_lookup_service.py`
- `src/commands/community_lookup_commands.py`
- `src/scripts/bench_ptt_comment_lookup.py`

**改動：**
- `src/services/state_db.py`（新表 + CRUD）
- `src/commands/management_commands.py`（/server_manager 加選項）
- `src/discord_bot.py`（掛 cog）

未動 scraper DB schema。

### Step 6 部署驗證（已完成，2026-04-20）

DB `community_lookup_threads` 累積 13+ 筆查詢紀錄，PTT (xfa60118 等) 與巴哈 (eveway / omiyashota / david89037 / huang1011200 等) 雙來源都驗過；slot 拆分（header / post / comment）、日期 hybrid section、父頻道公告、panel bump 流程實際運作正常。

</details>

## 產品能力 TODO（改寫前原文，歸檔 2026-10-02，原 2026-03-31）

> 最早的四階段規劃：先拿數據、提升好玩度、品質優化、資料成熟後再做 SFT，附時程估計。
>
> 關鍵字：askai 反饋、KPI、梗庫、Prompt A/B、模型路由、SFT

<details>
<summary>展開原文（約 574 字）</summary>

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

</details>
