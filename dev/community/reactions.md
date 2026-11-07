# Reaction 統計與社群互動玩法

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

> 現況、待決與待做以交接檔為準：[Reaction 統計與社群互動玩法](../../AI_HANDOFF_AND_TODO.md#reaction-統計與社群互動玩法)。
> 這裡是歷史。上半部是整理過的重點；「原文」是當時的紀錄，提到的檔名、函式、狀態可能已經改了。原文提到的 `TODO-completed.md` 是 2026-11-07 以前的單一歸檔檔，內容都拆到 `dev/` 了，從 [dev/README.md](../README.md) 找。

## 一頁看懂

這個主題管 Discord reaction 的統計：把群裡的互動量化，做成公開玩法，並餵回 /askai 與人格描述。

- **04-18 規劃**：分三階段。Phase 1 收集資料＋三個玩法（每週金句、神級發言名人堂、個人招牌 emoji），Phase 2 讓 /askai 帶出發問者近期的熱門發言，Phase 3 人格萃取依收到的 emoji 加權。當時只有論壇管理在聽 reaction，沒有任何累積統計，打算新建 `message_reactions` 表。
- **到 10-02 的資料收集**：已經做好，但不是新表，而是由 `raw_message_store` 寫進 `discord_messages_raw.reaction_breakdown`（每則訊息誰按了哪個表情、依表情與類別計數）。bot 自己按的不算，自訂與 unicode 表情的比對鍵已統一；插話的「依稀記得」召回已經拿它當重要度。
- **10-02 的待做**：三個玩法、/askai 整合、人格描述加權都還沒做。人格加權原本寫給人格萃取（③），它預定 10/05 後刪除，要做就改寫給 persona agent（④）。

**歸檔時（10-02）的狀態**

- [x] reaction 收集：寫進 `reaction_breakdown`，排除 bot 自己按的，表情比對鍵統一
- [x] 插話「依稀記得」的召回用它當重要度
- [ ] 每週金句、名人堂、`/my_emoji` 三個玩法
- [ ] /askai 帶出發問者近期熱門發言（`<asker_recent_highlights>`）
- [ ] 人格描述依收到的 emoji 加權（要改寫給 persona agent）

最新狀況看交接檔。

## 時間線

| 日期 | 發生什麼 | 結果 |
|---|---|---|
| 04-18 | 規劃 reaction 統計與三階段玩法 | 當時沒有累積統計；計畫新建 `message_reactions` 表 |
| 10-02 | 改寫交接檔區塊 | 收集已完成（`reaction_breakdown`），新表不需要；玩法與整合都還沒做 |

## 定案與理由

| 決定 | 為什麼 |
|---|---|
| 不建 `message_reactions` 表 | 資料已經寫進 `discord_messages_raw.reaction_breakdown` |
| bot 自己按的 reaction 不算 | 避免污染統計 |
| 歷史回補（掃 `channel.history()` 抓既有 reaction）先不做 | Discord 只回傳目前還存在的 reaction，大群還有 rate limit |
| 人格描述加權要做就改寫給 persona agent | 原本的人格萃取（③）預定 10/05 後刪除 |

## 踩過的坑

- **Discord 只回傳目前還存在的 reaction**：被撤回的回補不到；04-18 的做法是先跑一段時間累積自然資料，有需要再回補。
- **大群掃 `channel.history` 會撞 rate limit**：真要回補得分批加退避。
- **/askai 整合會增加 context token**：原文提醒實作時要設上限，也不要整段引述原文以免尷尬。

## 原文

新的在前。每段標題下面是摘要，正文在「展開原文」裡。

| 日期 | 段落 | 摘要 |
|---|---|---|
| 2026-10-02 | [原規劃與資料收集（10-02）](#reaction-統計與社群互動玩法原規劃與資料收集歸檔-2026-11-07原至-2026-10-02) | 收集已寫進 reaction_breakdown、新表不需要；三個玩法、/askai 整合、人格加權都還沒做。 |
| 2026-04-18 | [reaction 原規劃（04-18）](#reaction-統計與社群互動玩法改寫前原文歸檔-2026-10-02原-2026-04-18) | 最早的三階段規劃：新建 message_reactions 表與三個玩法、/askai 整合、人格萃取加權。 |

## Reaction 統計與社群互動玩法：原規劃與資料收集（歸檔 2026-11-07，原至 2026-10-02）

> 收集已寫進 reaction_breakdown、新表不需要；三個玩法、/askai 整合、人格加權都還沒做。
>
> 關鍵字：reaction、reaction_breakdown、raw_message_store、reaction_classifier、每週金句、名人堂、招牌 emoji、asker_recent_highlights、人格加權

<details>
<summary>展開原文（約 1,143 字）</summary>

> 從 `AI_HANDOFF_AND_TODO.md`「Reaction 統計與社群互動玩法（規劃；資料收集已完成）」區塊（`reaction-stats-todo`）瘦身前的完整原文；交接檔只留現況、規則與坑、未定案、待做。

> **目標：** 用 Discord reaction 統計把群內互動量化，餵回 `/askai` 與人格描述，讓 bot 更有「社群感」。

**資料已經有了（原 Phase 1 的收集部分）**：`discord_bot.py` 的 `on_raw_reaction_add`／`remove` → `llm/storage/raw_message_store.py` 寫進 `discord_messages_raw.reaction_breakdown`（每則訊息：誰按了哪個表情、依表情與類別計數）；bot 自己按的不算、自訂與 unicode 表情已統一比對鍵；插話「依稀記得」的召回已經拿它當重要度。原規劃要新建的 `message_reactions` 表不需要了。原規劃全文已歸檔。

### 還沒做

**玩法（都用上面的資料）**
- [ ] **每週金句頒獎**：排程每週日發佈過去 7 天 reaction 最多的 3 則訊息到指定頻道
- [ ] **神級發言名人堂**：訊息 reaction 數達門檻（預設 10）自動複製到 `#hall-of-fame` 頻道
- [ ] **個人招牌 emoji**：`/my_emoji` 查自己被按最多的 emoji、送反應最多的前 N 人

**/askai 整合**
- [ ] 查發問者近 N 天的 reaction 熱點（熱門發言 1～3 則＋招牌 emoji），在 `asker_profile` 下方加 `<asker_recent_highlights>` 區塊
- [ ] 讓模型能自然帶出「你上週那句大家反應很好」；safety rules 標為可信，提醒不要整段引述原文以免尷尬

**人格描述加權**（原本寫給 ③；③ 預定 10/05 後刪，要做就改寫給 ④ persona agent）
- [ ] 把「這個人常收到哪類 emoji」當線索（收到 🤣 多 → 幽默感、😢 多 → 共感），跟 `emoji_dictionary.txt` 聯動轉成自然語言特徵

### 設計備忘

- 歷史回補（掃 `channel.history()` 抓既有 reaction）先不做：Discord 只回傳目前還存在的 reaction，大群還有 rate limit
- 使用者退群後的 reaction 紀錄保留政策待定（預設保留）
- /askai 整合會增加 context token，實作時要設上限

</details>

## Reaction 統計與社群互動玩法（改寫前原文，歸檔 2026-10-02，原 2026-04-18）

> 最早的三階段規劃：新建 message_reactions 表與三個玩法、/askai 整合、人格萃取加權。
>
> 關鍵字：message_reactions 表（不需要了）、每週金句、名人堂、/my_emoji、asker_recent_highlights

<details>
<summary>展開原文（約 2,289 字）</summary>

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
| `src/llm/persona/personality_extractor.py` | Phase 3：萃取時加權 reaction 訊號 |

</details>
