# 新成員歡迎訊息

<!-- 給 AI：這份是歸檔檔，改之前先看完這段
結構：上半部（一頁看懂、時間線、定案與理由、踩過的坑）是整理過的重點；「## 原文」以下是當時的紀錄。
新增一段：
1. 原文放在「## 原文」目錄表下方的最前面，照現有各段的格式（## 標題、> 摘要與關鍵字、<details> 包正文，標籤前後各空一行）。
2. 目錄表加一列；dev/README.md 的「依日期」加一列。
3. 同一輪更新上半部，並把下面的「整理到」改成新段的日期。
不要改：原文正文、既有的段落標題（README 和其他檔用標題當錨點）。
找細節用搜尋，不必整份讀。改完跑 python3 dev/check.py。完整規則：AI_HANDOFF_AND_TODO.md「本檔維護規則」的「歸檔放哪」。
整理到：2026-09-28
-->

> 交接檔已經沒有這個主題的區塊；現況以 [交接檔](../../AI_HANDOFF_AND_TODO.md) 與程式為準。
> 這裡是歷史。上半部是整理過的重點；「原文」是當時的紀錄，提到的檔名、函式、狀態可能已經改了。原文提到的 `TODO-completed.md` 是 2026-11-07 以前的單一歸檔檔，內容都拆到 `dev/` 了，從 [dev/README.md](../README.md) 找。

## 一頁看懂

這個主題管新成員加入時的歡迎訊息：由自家 bot 在歡迎頻道發，接手 ProBot 原本做的事。

- **09-28 起因**：ProBot 的加入歡迎訊息疑似失效，改由自家 bot 在歡迎頻道發同樣的內容（@新成員、伺服器名、引導去規範頻道）。
- **09-28 做法**：`on_member_join` 事件 → 讀 `welcome_channel_id` → 發一則純文字。歡迎頻道用 `/server_manager` 綁，沒綁就不發；規範頻道連結用 Discord 內建的 `guild.rules_channel`；文案先照抄 ProBot。
- **09-28 上線準備**：`test_member_welcome.py` 8 項併入啟動 gate，全套 526 項全綠；15:04 綁定「歡迎」頻道。
- **10-01**：07:59 第一次真的發出歡迎訊息。
- **10-02**：使用者確認 ProBot 的歡迎功能早就關了，沒有剩下的待辦。

**歸檔時（10-02）的狀態**

- [x] bot 在歡迎頻道發新成員歡迎訊息，測試 8 項併入啟動 gate（09-28）
- [x] 綁定「歡迎」頻道（09-28），第一次實發（10-01）
- [x] 確認 ProBot 的歡迎功能早就關了，沒有剩下的待辦（10-02）

最新狀況看交接檔。

## 時間線

| 日期 | 發生什麼 | 結果 |
|---|---|---|
| 09-28 | ProBot 的歡迎訊息疑似失效，規劃由自家 bot 接手 | 定案：規範頻道用 `guild.rules_channel`、文案照抄 ProBot、上線後關掉 ProBot 的歡迎 |
| 09-28 | 實作 `services/community/member_welcome.py`，`discord_bot.py` 加 `on_member_join` | 測試 8 項併入啟動 gate，全套 526 項綠；15:04 綁定「歡迎」頻道 |
| 10-01 | 07:59 第一次實發 | 上線 |
| 10-02 | 使用者確認 ProBot 的歡迎功能早就關了 | 沒有待辦 |

## 定案與理由

| 決定 | 為什麼 |
|---|---|
| `on_member_join` 寫在 `discord_bot.py`，只交給 `services/community/member_welcome.py` 處理 | 沿用本專案「gateway 事件集中在 `discord_bot.py`、邏輯放 services」的慣例；全專案原本沒人監聽這個事件，不會蓋掉別的 |
| 不掛在 `ManagementCommands` 當 Cog listener | 功能可行，但那個檔是指令集中的地方，放事件會亂了分工 |
| 歡迎頻道用 `register_channel` 登記（`welcome_channel_id`） | 沿用 `/server_manager` 綁頻道的畫面；沒設定就靜默不發 |
| 規範頻道連結用 Discord 內建的 `guild.rules_channel`，不另開 config key | 規範頻道已經設成伺服器的「規則頻道」 |
| 文案先照抄 ProBot，上線後關掉 ProBot 的歡迎 | 需求就是由自家 bot 發同樣的內容 |

## 踩過的坑

（這幾段沒有記下坑）

## 原文

新的在前。每段標題下面是摘要，正文在「展開原文」裡。

| 日期 | 段落 | 摘要 |
|---|---|---|
| 2026-09-28 | [接手 ProBot 的歡迎訊息](#新成員歡迎訊息接手-probot歸檔-2026-10-02原-2026-09-28) | bot 接手 ProBot 發新成員歡迎訊息；09-28 實作、10-01 首次實發、10-02 確認沒有待辦。 |

## 新成員歡迎訊息：接手 ProBot（歸檔 2026-10-02，原 2026-09-28）

> bot 接手 ProBot 發新成員歡迎訊息；09-28 實作、10-01 首次實發、10-02 確認沒有待辦。
>
> 關鍵字：on_member_join、member_welcome、guild.rules_channel、ProBot、4fd4170

<details>
<summary>展開原文（約 1,454 字）</summary>

> 已上線：9/28 15:04 綁定「歡迎」頻道，10/01 07:59 首次實發；使用者 10-02 確認 ProBot 的歡迎功能早就關了，沒有剩下的待辦。

<!-- @meta
id: member-welcome-message
type: STATE
status: confirmed
last_confirmed: 2026-09-28
affects: settings/channel_registry.py, services/community/member_welcome.py（新）, discord_bot.py, test/test_member_welcome.py（新）
-->

**需求**：ProBot 的加入歡迎訊息疑似失效，改由自家 bot 在歡迎頻道發同樣內容（@新成員 + 伺服器名 + 引導去規範頻道）。

**機制一句話**：`on_member_join` 事件 → 讀 `welcome_channel_id` → 發一則純文字。

**改動清單（全部 additive，不動既有流程）**
1. `channel_registry.py`：`register_channel("歡迎頻道", text, "welcome_channel_id")`，沿用 `/server_manager` 綁頻道 UI，未設定＝功能靜默
2. 新檔 `services/community/member_welcome.py`：文案純函式 + 讀頻道發送；略過 bot 帳號
3. `discord_bot.py` 加 `@bot.event on_member_join`，只委派給上面的 service（沿用本專案「gateway 事件集中在 discord_bot.py、邏輯放 services」慣例；全專案原本無人監聽此事件，不會覆蓋）
4. 規範頻道連結優先用 Discord 內建 `guild.rules_channel`（社群伺服器設定），不另開 config key
5. 文案純函式補單元測試

**已排除**：掛在 `ManagementCommands` 當 Cog listener——功能可行，但該檔是指令集中地，放事件會亂了分工（使用者 2026-09-28 指正）。

**已知前提**：`intents.members = True` 已開（bot 能連上即代表開發者後台也已開）。

**已定案（使用者 2026-09-28 確認）**：規範頻道已設為伺服器「規則頻道」→ 用 `guild.rules_channel`；文案先照抄 ProBot；上線後關掉 ProBot 歡迎功能。

**實作細節**：只允許 @ 新成員本人（`AllowedMentions`）；bot 帳號、未綁頻道、頻道不在本伺服器、非文字頻道、發送失敗都靜默略過不拋例外。
測試 `test_member_welcome.py` 8 項，已併入啟動 gate（全套 526 項綠）。

**待驗證（使用者執行）**
- [ ] 重啟 discord-bot
- [ ] `/server_manager` → 設定頻道 → 「歡迎頻道」選目標頻道；確認 bot 在該頻道有「傳送訊息」權限
- [ ] 關掉 ProBot 歡迎（ProBot 後台 Welcome & Goodbye 關閉，或在歡迎頻道拒絕 ProBot 的「傳送訊息」權限）
- [ ] 找人（或小號）加入一次，確認文案、@ 與規範頻道連結正確

</details>
