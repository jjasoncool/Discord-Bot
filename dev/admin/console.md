# 指令整理、管理主控台與群主通知

<!-- 給 AI：這份是歸檔檔，改之前先看完這段
結構：上半部（一頁看懂、時間線、定案與理由、踩過的坑）是整理過的重點；「## 原文」以下是當時的紀錄。
新增一段：
1. 原文放在「## 原文」目錄表下方的最前面，照現有各段的格式（## 標題、> 摘要與關鍵字、<details> 包正文，標籤前後各空一行）。
2. 目錄表加一列；dev/README.md 的「依日期」加一列。
3. 同一輪更新上半部，並把下面的「整理到」改成新段的日期。
不要改：原文正文、既有的段落標題（README 和其他檔用標題當錨點）。
找細節用搜尋，不必整份讀。改完跑 python3 dev/check.py。完整規則：AI_HANDOFF_AND_TODO.md「本檔維護規則」的「歸檔放哪」。
整理到：2026-11-01
-->

> 現況、待決與待做以交接檔為準：[指令整理與管理入口](../../AI_HANDOFF_AND_TODO.md#指令整理與管理入口)、[群主通知、管理主控台與機器人狀態](../../AI_HANDOFF_AND_TODO.md#群主通知管理主控台與機器人狀態)。
> 這裡是歷史。上半部是整理過的重點；「原文」是當時的紀錄，提到的檔名、函式、狀態可能已經改了。原文提到的 `TODO-completed.md` 是 2026-11-07 以前的單一歸檔檔，內容都拆到 `dev/` 了，從 [dev/README.md](../README.md) 找。

## 一頁看懂

這個主題管兩件事：群主怎麼管理 bot（指令、主控台、頻道綁定），以及 bot 出事時怎麼讓群主知道、按一下就重新檢查。

- **3 月到 10 月初**：只有規劃。指令整理分三步（子指令 → 管理面板 → 網頁 dashboard），權限檢查收斂做過一次又全部還原。
- **10-29 起因**：向量模型掛掉，自癒試了 3 次就放棄。群主收到私訊，但修好 Lemonade 之後沒辦法告訴 bot「好了」。
- **10-30**：做成私訊主控台。出事時私訊群主，底下有「重新偵測」按鈕；另外有機器人狀態和頻道綁定面板。
- **10-31 關鍵轉折**：發現自癒從來沒真的重開過模型。Lemonade 對還活著的模型送 load 什麼都不做，卻回 200，bot 就以為修好了。改成先 unload 再 load、比對行程編號、真的算一次才算救回。
- **11-01**：主控台改成一則訊息、七組選單。05:36 第一次真的自癒成功，約 20 秒救回。

**歸檔時（11-01）的狀態**

- [x] 私訊通知＋「重新偵測」按鈕、機器人狀態、頻道綁定面板（10-30）
- [x] 自癒改成真的重開，驗證過才說救回（10-31）
- [x] 主控台改成一則訊息、七組選單（11-01）
- [ ] 第二批偵測：資料庫、別的容器沒消息、Discord 權限等
- [ ] 群主按「重新偵測」時兩顆模型各一行，還沒驗收
- [ ] 顯示卡掉裝置的原因，要等 Windows 端查證

最新狀況看交接檔。

## 時間線

| 日期 | 發生什麼 | 結果 |
|---|---|---|
| 03-31 | 規劃管理入口與指令整理 | 三個目標：入口整合、指令分層、子指令化 |
| 08-20 | AI／人格相關指令有 9 個、名字前綴不一 | 規劃收成 `/persona` 子指令群組，再做管理面板、網頁 dashboard |
| 09-04 | 權限檢查有五種寫法，收成一種 | 做完、測試全綠，但使用者要先專注 ComfyUI，全部還原，只留盤點 |
| 09-21 | 刪掉兩個權限包裝函式、點名按鈕改用共用檢查 | 上線（`7817bd4`、`3cbf28c`） |
| 10-02 | 兩份舊規劃合併成「指令整理與管理入口」 | 盤點斜線指令（當時 21 個） |
| 10-29 | 向量模型 DeviceLost，自癒 3 次後放棄 | 規劃「私訊＋重新偵測」；清查出 41 種要人介入的狀況 |
| 10-30 | 實作群主通知、機器人狀態、頻道綁定面板 | 私訊主控台；完整測試 1,949 條全綠 |
| 10-31 | 向量模型又壞，自癒 20 次全部空轉 | 查出 load 對活著的模型不做事；改成真的重開，並且驗證過才說救回 |
| 11-01 | 主控台第二版；05:36 第一次真的自癒 | 一則訊息七組選單；自癒約 20 秒救回 |

## 定案與理由

| 決定 | 為什麼 |
|---|---|
| 通知機制放基礎層 `utils/owner_alerts.py`，按鈕與私訊放一個新的指令模組 | 基礎層不能依賴模型服務；一個功能一個模組，之後別的偵測都接同一處 |
| Lemonade 直接呼叫 `owner_alerts.emit`，拿掉舊的通知接法 | 只留一條通知路，不要兩套並存 |
| 重新偵測要真的算一次，不能只看 health | 10-29 裝置掉了，health 照樣回 ready |
| 主控台放在跟 bot 的私訊裡，只由 `/server_manager` 叫出 | 通知本來就走私訊；不用開管理頻道，也不會因為頻道權限設錯外流；私訊對話留給之後的 AI 私聊 |
| 只有群主能操作 | 綁錯頻道會影響整個 bot；目前只有群主在管，要放寬只改三處 |
| 頻道清單由 bot 自己列 | Discord 原生的頻道選單在私訊裡列不出伺服器的頻道 |
| 加「解除綁定」 | 以前只能手改 `config.json` |
| 頻道類型只有文字、論壇、語音 | 使用者沒有公告頻道要綁 |
| 自癒改成 unload 再 load，比對行程編號、真的算一次才算救回 | 只送 load 對還活著的模型是空操作 |
| 自癒放棄後就停住，直到群主按重新偵測，或偵測到 Lemonade 被重啟 | 以前大約 50 分鐘後又自己開始重載，放棄訊息寫的「不再自動重載」不成立 |
| 兩顆模型都測、各自解除警報 | 以前一顆壞著，另一顆的警報也解除不了 |
| 「每個指令都要有權限檢查」的自動守衛先不加 | 守衛跑在啟動檢查裡，誤判會讓 bot 起不來 |

## 踩過的坑

- **Lemonade 的 load 不會重開還活著的模型**：選項相同就只回 200。要重開必須先 unload，而且要帶 `model_name`，不帶會把全部模型都卸掉。
- **health 正常不代表能算**：顯示卡掉裝置時 health 照樣正常，只有真的送一筆請求才知道。
- **顯示卡掉裝置比較像驅動層級的問題**：剛開的新行程也收到 device lost，約 18 秒後自己恢復。每次都發生在大模型大量計算、同時有向量請求打到同一張卡的時候。
- **原生頻道選單在私訊裡列不出伺服器的頻道**（discord-api-docs #5600）。
- **權限不足會回兩則訊息**：權限檢查自己回一句中文，全域的錯誤處理又補一句「執行命令時發生錯誤」，所以要用自訂的例外。
- **`persona_agent_test` 開始和結束各檢查一次權限，是刻意的**：回覆的時效有 15 分鐘，這段時間權限可能被撤銷，不能當成重複刪掉。
- **突變測試真的寫了正式資料庫**：測試沒把「補向量」換成替身，改壞的版本真的補了 12 筆。替身要放在 `setUp`。
- **偏好抽取沒有輸出上限**：一次生成 9,727 個字詞、跑了 294 秒，後面排隊的插話全被卡住。

## 原文

新的在前。每段標題下面是摘要，正文在「展開原文」裡。

| 日期 | 段落 | 摘要 |
|---|---|---|
| 2026-11-01 | [群主通知與管理主控台](#群主通知與管理主控台10-29-清查-41-條頻道綁定面板自癒空轉事故與第一次真的自癒歸檔-2026-11-07原至-2026-11-01) | 10-29 自癒放棄後規劃「私訊＋重新偵測」，清查出 41 種要人介入的狀況；10-30 做成私訊主控台與頻道綁定面板；10-31 查出自癒從沒真的重開，改成 unload 再 load 並驗證；11-01 第一次真的自癒。 |
| 2026-10-02 | [指令整理與管理入口（10-02 合併版）](#指令整理與管理入口三階段規劃與權限檢查收斂2026-0310歸檔-2026-11-07原至-2026-10-02) | 兩份舊規劃合併後的版本：斜線指令盤點、三步計畫（子指令 → 管理面板 → 網頁 dashboard），以及暫緩的權限檢查收斂。 |
| 2026-08-20 | [指令收斂與管理 Dashboard（08-20）](#指令收斂與管理-dashboard改寫前原文歸檔-2026-10-02原-2026-08-20) | AI／人格相關指令 9 個、名字前綴不一，規劃收成 `/persona` 子指令群組，再做管理面板與網頁 dashboard。 |
| 2026-03-31 | [管理入口與指令整理（03-31）](#discord-bot-管理入口與指令整理-todo改寫前原文歸檔-2026-10-02原-2026-03-31) | 最早的待辦：`/panel admin` 入口、指令分層、子指令化；含 09-04 權限檢查五種寫法的盤點，以及做完又還原的經過。 |

## 群主通知與管理主控台：10-29 清查 41 條、頻道綁定面板、自癒空轉事故與第一次真的自癒（歸檔 2026-11-07，原至 2026-11-01）

> 10-29 自癒放棄後規劃「私訊＋重新偵測」，清查出 41 種要人介入的狀況；10-30 做成私訊主控台與頻道綁定面板；10-31 查出自癒從沒真的重開，改成 unload 再 load 並驗證；11-01 第一次真的自癒。
>
> 關鍵字：owner_alerts、重新偵測、群主私訊、admin_console、admin_status、channel_panel、頻道綁定、ErrorDeviceLost、Lemonade 自癒、機器人狀態

<details>
<summary>展開原文（約 33,364 字）</summary>

> 從 `AI_HANDOFF_AND_TODO.md`「需要群主介入的狀況：私訊＋「重新偵測」按鈕＋管理面板（2026-10-29 規劃，未動工）」區塊（`owner-alerts`）瘦身前的完整原文；交接檔只留現況、規則與坑、未定案、待做。

**起因（10-29，log 核對 `discord_bot.log` 138664～138899）**：14:19:55 插話生成逾時後 embedding 模型回 500（vk ErrorDeviceLost）→ 自癒重載，14:21:12、14:24:55 再兩次，14:29:55 放棄；四次都有私訊群主。放棄後到 15:03 每 5 分鐘的聊天寫入都失敗、放回緩衝（最多積 17 則），`ai_interactions` 的向量存 NULL 6 筆，插話與 /askai 的人物卡／聊天向量檢索降級，這段只有 log。15:02 使用者重啟 Lemonade，15:03:17 bot 重推 reranker 的載入選項，15:04:56 聊天緩衝一次寫回 23 則，沒丟資料。放棄紀錄（`_GAVE_UP_AT`／`_HEAL_HISTORY`）留在記憶體一小時，Lemonade 重啟後 bot 不知道，一小時內再壞就不會救；也沒有任何入口告訴 bot「我修好了」。使用者要：① 放棄那則私訊底下有「重新偵測」按鈕；② 清查還有哪些要人介入的狀況，同樣私訊＋按鈕，或開管理面板看狀態、重測；③ 記入待辦。

**機制（一句話）**：下層用 `owner_alerts.emit(kind, key, text)` 把「要人介入」交上來；介面層把它變成一則私訊＋「重新偵測」按鈕（custom_id 帶 kind 與 key，重啟後還能按）；按下去呼叫那個 kind 登記的重測函式（清狀態 → 探測 → 回報），結果回寫同一則訊息；同一份登記表餵 `/admin_status` 面板。

**元件與放哪裡（建議 B，見 OA-Q1）**：
1. `utils/owner_alerts.py`（基礎層、不 import discord）：`emit(kind, key, text, *, severity)`（任何執行緒可叫）、`set_listener(fn)`、`register(kind, *, title, retest, status)`、`retest(kind, key) -> RetestResult`、`active()`（還沒解除的警報：kind、key、since、text）、`resolve(kind, key)`。同一 (kind, key) 一小時內只送一次（沿用 Lemonade「放棄只講一次」）。
2. `commands/owner_alert_commands.py`（介面層 cog，進 `COMMAND_MODULES`）：`cog_load` 接 listener（`loop.call_soon_threadsafe`＋`spawn`，從 `discord_bot._on_lemonade_heal` 搬過來）、`add_dynamic_items(RetestButton)`、登記各 kind 的重測；`_on_alert` → `dm_notifier.send_dm(owner, content, view)`，message id 記在記憶體給解除時回寫；`RetestButton(DynamicItem, template "owner:retest:(?P<kind>[a-z_]+):(?P<key>.+)")`：群主檢查 → defer → `owner_alerts.retest` → 編輯原訊息（成功：補一行「HH:MM 重新偵測：正常」、按鈕停用；失敗：補一行、按鈕留著）；`/admin_status`（owner_only、只有本人看得到）：各 kind 的 `status()` 行＋還沒解除的警報各一顆按鈕。先例：`telegram_quarantine_commands.QuarantineRestoreButton`、`forum_monitor.TradeButton`（discord.py 2.7.1）。
3. `dm_notifier.send_dm` 加 `view=`（和 `file` 一樣用 MISSING 哨兵）；`lemonade_heal_notice` 文案留著給 cog 用。
4. `discord_members.require_access` 加 `allow_dm=`：`owner_only` 在私訊放行（只比 `bot_owner_id()`）；`admin_only`／`permission`／`required_role` 照舊要在伺服器。repo 沒有私訊裡放按鈕的先例，`require_access` 現在一律擋私訊。
5. `lemonade_admin`：放棄與重載失敗改走 `owner_alerts.emit`（healed 照舊一行私訊、不掛按鈕、順便 `resolve`）；`set_heal_listener` 退場（見 OA-Q2）。
6. `LLMService.probe(model)`（新、公開）：`admin_get("/api/v1/health")` 看活著，再走一般路徑真的算一次（embedding 模型送一筆短字串、聊天模型 1 token），拿 GPU 閘門、不重試、短逾時；失敗讓 heal 再跑（紀錄剛清掉，會重載一次），再壞回報「還是壞」。接所有例外的那行註 `# 邊界`（錯誤邊界基準 78 只准減）。health 不能單獨當探測：10-29 16:08 查 health 全部 ready，但 14:30～15:02 每次算都 500（「ready 看的是行程不是裝置」）。
7. Lemonade 的重測＝`lemonade_admin.reset_cache()`（已有、正式程式沒人呼叫；清放棄紀錄、冷卻、載入快取，順便解 LM-Q2）→ `LLMService.probe(embed_model)`、`probe(chat_model)` → 回報；成功後 `ai_interactions_store.backfill_embeddings()`（不然 NULL 的向量要等重啟）、叫醒 Telegram 過濾的補判（`run_recheck`）；聊天緩衝 5 分鐘內本來就會重試，不必特別叫。
8. 守衛：`test_layering` 基礎層登記 `utils.owner_alerts`（不 import discord，不進 `DISCORD_HELPERS_IN_BASE`）；`test_shared_conventions` 加一條「通知群主要人介入只走 `owner_alerts.emit`；別處不自己 `bot_owner_id()`＋`send_dm`」；AGENTS 共用元件表加一列。
9. 測試：新 `test_owner_alerts.py`（emit 從別的執行緒 → listener 排回 loop；register／retest／active／resolve；同鍵一小時一次；私訊的 interaction 走到 callback；非群主按不動；原訊息被編輯；重啟後舊按鈕還能按＝DynamicItem 從 custom_id 還原）；`test_lemonade_heal.py` 的 `OwnerNoticeTests` 改接 emit；`require_access(allow_dm=True)`；`send_dm(view=)`；`LLMService.probe` 用假 client。每條新測試改壞一次確認會紅。

**清查結果（10-29）**：workflow 三個找尋角度（自己放棄／外部依賴斷了／ERROR 沒人知道）共 79 條、去重後 41 條；零件盤點另一個 agent；23 個複查 agent 因費用上限沒跑成，標「核對」的 10 條由主 agent 讀程式本體確認，其餘是找尋 agent 的判讀（讀過本體、附行號）。「實際發生」看 `discord_bot.log` 現行檔（2026-10-21 18:15 起）與 `persona_agent_runs`（唯讀查詢）。

| # | 狀況（哪裡） | 現在誰知道 | 怎麼解除 | 重測動作 | 實際發生 | 建議 |
|---|---|---|---|---|---|---|
| **A 模型後端（Lemonade／顯示卡／GPU 閘門）** | | | | | | |
| 1 | 自癒一小時 3 次後放棄、或重載本身失敗（`lemonade_admin.heal`） | 私訊（一小時一次） | 時間窗 1 小時；`reset_cache()` 沒人叫得到 | `reset_cache()` → `probe` | 1 次（10-29） | 第 1 批（核對） |
| 2 | Lemonade 整台連不上（`http_client.judge_failure` 不重載、不發事件；各呼叫端各自收尾） | 只有 log：/askai 回群友「無法連線」、插話 INFO 略過、聊天寫入 WARNING 放回 | 下一輪自動 | `probe`；要新加「連續連不上超過 10 分鐘」才發 | 10-29 15:02 一段（重啟期間） | 第 1 批（同 kind） |
| 3 | GPU 鎖檔被別的行程（search-mcp 批次、手動腳本）佔著：等 15 分鐘後硬闖 15 分鐘、循環（`gpu_gate._acquire_steps`） | ERROR | 對方放鎖 | 試拿鎖（LOCK_NB）＋列 `current_owner()`；是誰要看 search-mcp 的 ps | 0 次 | 第 1 批（核對） |
| 4 | Telegram 過濾模型 30 分鐘沒回應 → 未判放行、每 10 分鐘補判（`telegram_filter._ask`） | ERROR 一次 | 模型回來自動 | Lemonade 重測成功後 `run_recheck()` | — | 併入 1 |
| 5 | 04:00 維護整輪失敗當天不補：`_ran_on` 跑之前就設（`daily_maintenance._tick`） | ERROR | 隔天或重啟補跑 | `run_once(guild)`（長時間占 GPU，避開 04:00～07:30） | — | 第 2 批：面板按鈕（核對） |
| 6 | 插話互動紀錄的向量存 NULL 直到重啟（`ai_interactions_store.record_interaction`；回填只在 on_ready） | WARNING | 重啟 | `backfill_embeddings()` | 10-29 6 筆 | 併入 1 的重測成功後動作 |
| 7 | 自介／印象寫入失敗，群友仍看到成功（`member_profile_store.index_*`；`intro_profile_service` 不接錯） | ERROR | 當事人重填 | — | — | 另案（10-28 盤點已記「要不要提示重送」） |
| **B 資料庫（pgvector）** | | | | | | |
| 8 | pgvector 連不上：raw 備份整批丟、補不回（`raw_message_store.flush_raw_buffer`） | ERROR 每 60 秒 | 下一輪自動 | `pgvector_cursor` SELECT 1＋`flush_raw_buffer()` | 10-23、10-24 各一批（停機時） | 第 1 批：連續失敗 3 次就發（LM-Q4 已知） |
| 9 | 聊天緩衝超過 1000 則丟最舊；本行程排過補寫的不再撈（`store_chat._trim_oldest`、`chat_index_backfill._skip_ids`） | WARNING 一次 | 補寫 14 天內 | Lemonade 重測成功後 `flush_buffer()` | 0 次（今天最多 17 則） | 併入 1、8（核對） |
| 10 | 啟動時 Telegram 轉發起不來：缺 PGVECTOR_USER／PASSWORD、DB 當時連不上（`auto_start_telegram_relay`） | ERROR 一次 | 重啟（gateway 重連會再試） | `auto_start_telegram_relay(bot)`（有「已在跑就略過」） | — | 第 2 批：面板 |
| 11 | 啟動時建表失敗、之後不再試（`discord_bot._ensure_tables`；`member_profile_store` 第一次寫入才建表） | ERROR 一次 | 重啟 | `ensure_table()`（idempotent） | 只在新資料庫 | 第 2 批：面板 |
| **C 別的容器** | | | | | | |
| 12 | scraper 掛了：FB／IT／巴哈只靠推送、完全沒聲音；公告 30 分、PTT 10 分的輪詢每輪 ERROR（`base_monitor.fetch_content_from_api`） | silent／ERROR | 容器回來自動 | GET scraper `/health`；要新加「最後一次推送或成功輪詢超過 N 小時」 | API 逾時 3 次 | 第 1 批：新偵測 |
| 13 | telegram-scraper 掛了或 session 失效：bot 端沒有任何訊號（`_listen_loop`／`_poll_loop` 撈不到新 pk 是正常狀態） | silent | 容器回來自動 | 查 `telegram_messages` 最新一列的時間；session 狀態只有爬蟲知道 | — | 第 1 批：新偵測（最後一列超過 N 小時；N 看頻道平常節奏）（核對：沒有閒置偵測） |
| 14 | search-mcp 掛了：/askai 與插話每題 WARNING、不查（`intel/client.prepare_intel_session`） | WARNING 每題 | `restart: always` 多半自己回來 | `prepare_intel_session()` 回 None 就是連不上 | — | 第 2 批：面板 |
| 15 | search-mcp 的索引同步退避、每日補向量當天不重試（`services/search/background`，跑在那個容器） | 那邊的 log | — | 要在 MCP 加回報工具 | — | 另案 |
| 16 | SearXNG 掛了／引擎被擋暫避 30 分鐘（`searxng.fetch_web_results`／`_note_unresponsive`） | WARNING | 時間到自動 | `search_web("test")`；清暫避要新增 `reset_blocked()` | — | 第 2 批：面板顯示誰被擋 |
| **D Discord 權限／頻道綁定** | | | | | | |
| 17 | 轉發頻道綁了但送不出去（權限、頻道被刪）：每輪重抓、重失敗（article／fb／ptt／it／bahamut 的 send_*） | ERROR 每輪 | 修權限自動 | `permissions_for(guild.me)`＋重送 | 0 次 | 第 1 批：同一頻道一小時一次 |
| 18 | 推送來了頻道沒綁（`notify_server._process_relay`／`_process_bahamut`） | ERROR 每次 | 綁好自動；漏的 `/resend_article` | `get_configured_id` 列沒綁的 | 0 次（都已綁） | 第 2 批：面板 |
| 19 | bot 缺「管理活動」權限：活動建不起來，公告已標已送、不會回頭補（`event_scheduler._create_event` Forbidden） | ERROR | 補權限後只有新公告會建；漏的 `/resend_article type:article` | 檢查 `manage_events` | 0 次 | 第 1 批（核對） |
| 20 | 活動建好但指紋寫入失敗 → 重送會重複建（`event_scheduler`） | ERROR | 手動補列或刪重複 | — | 0 次 | 另案（小） |
| 21 | 點名踢人沒權限：每 6 小時對同一批人再私訊「已移出」再踢失敗（`rollcall_service.check_expired`） | ERROR | 補權限自動 | 檢查 `kick_members` 與身分組高低；不要真的跑 `check_expired`（會再私訊） | 0 次 | 第 1 批（先改成只私訊一次） |
| 22 | 隔離 thread 開不了（沒「建立公開討論串」權限）：那則不送、不再試（`telegram_quarantine.thread_for` → `_process_one` 仍標已處理） | ERROR | 修權限後只有新的 | 檢查權限；漏的 `/resend_article type:telegram` | 0 次 | 第 2 批 |
| 23 | Telegram 送 Discord 失敗（缺權限、頻道被刪）不重試、本行程不再送（`_process_one` 照樣 `_mark_processed`） | ERROR | 重啟補送 | — | — | 另案（和 c1 投遞單位一起） |
| 24 | 語音頻道連不上：每 5 秒重試、每次 ERROR（`music/player.ensure_voice`） | ERROR 每 5 秒 | 修頻道自動 | `ensure_voice()` | 0 次 | 第 2 批（先把重試間隔拉長） |
| 25 | 交易頻道沒綁（`trade_service`／`shop_service`） | 群友看到「請通知管理員」 | 綁好自動 | 列沒綁的 | 0 次 | 第 2 批：面板 |
| **E 設定／環境（多半啟動時一次，面板顯示即可）** | | | | | | |
| 26 | OWNER_ID 沒設：整條通知路無聲、`owner_only` 誰都過不了（`dm_notifier`／`bot_owner_id`） | silent | 重啟 | 啟動自檢＋面板 | — | 第 1 批（啟動時記 WARNING＋面板） |
| 27 | 群主關私訊／封鎖 bot：`send_dm` Forbidden 只 WARNING | WARNING | 群主開私訊 | — | 0 次 | 同 26 |
| 28 | DISCORD_TOKEN 錯：容器 Up 但 bot 不在線，每 60 秒 WARNING、不重試（`discord_bot.main`） | log | 重啟 | 無（bot 不在線） | — | 另案（改成重讀 .env 重試） |
| 29 | 指令模組載入失敗（`setup_hook`；例：`llm_context_safety_rules` 檔壞 → /askai 與管理 cog 都載不起來；ForumMonitor 沒載 → 商品上架停用） | ERROR 一次 | 重啟 | 面板列沒載入的 cog（`bot.cogs` 對 COMMAND_MODULES） | — | 第 2 批：面板 |
| 30 | 通知伺服器起不來（port 5000 被占）：推送路線全停（`auto_start_notify_server`） | ERROR 一次 | 重啟 | 面板顯示 | — | 第 2 批 |
| 31 | NOTIFY_SHARED_SECRET 兩邊不一致：每次推送 401（`notify_server._authorized`） | WARNING 每次 | 重啟兩邊 | 加 401 計數給面板 | 0 次 | 第 2 批 |
| 32 | HERMES_API_KEY 沒設：模型端點不掛（`notify_server`） | INFO | 重啟 | 面板顯示 | — | 第 2 批 |
| 33 | config.json 壞掉：每次讀都 ERROR、權限檢查全拒、Discord 設定寫入被拒（`ChannelConfig`／`check_role`） | ERROR 洗版 | 修檔即生效 | `load_config` 試讀 | 0 次 | 第 1 批（一小時一次） |
| 34 | settings/runtime 寫不進去（磁碟滿、唯讀）：設的東西都丟（`runtime_file` 呼叫端） | ERROR | 修掛載 | 試寫一個暫存欄位 | 0 次 | 第 2 批 |
| 35 | 活動排程 dry_run 預設 true／enabled false：一個活動都不建、沒聲音 | silent／INFO | 改 config 即生效 | 面板顯示現值 | 現在 false | 第 2 批：面板 |
| 36 | 插話模型或頻道沒設：插話（含被 @）整個靜默（`ambient_reply` 入口） | silent | 改即生效 | 面板顯示 | 現在有設 | 第 2 批：面板 |
| 37 | 週期提醒／日記／歡迎／點名頻道沒綁 | silent 或 WARNING | 綁好即生效 | 面板列出 | 現在都有 | 第 2 批：面板 |
| **F 自己放棄、要人解** | | | | | | |
| 38 | persona agent 隔離永遠解不開：`_is_failure` 把 `quarantined` 也算失敗，最近 5 筆永遠 ≥3（`agent/store.py`、`agent.py` `QUARANTINE_AFTER_FAILURES=3`） | WARNING 每晚 | 改資料庫 | 改 `_is_failure`（quarantined 不算）＋隔離 N 天自動再試；按鈕＝清失敗列跑一次 | 0 次（1,541 筆 run 沒有 quarantined；max_steps 80 筆沒連 3 次） | 第 1 批：先修 bug（核對） |
| 39 | yt-dlp 壞／要 cookies：每首抽取失敗都當「這首不能播」從歌單移除，整份歌單幾分鐘清空，沒有連續失敗判斷（`player._play_next`） | 頻道訊息 | 更新 yt-dlp 後面板重載歌單 | 連續 3 首失敗就停止移除、發私訊；重測 `extract_single` 一首 | 16 次都是版權／私人影片（正常） | 第 1 批（核對） |
| 40 | 隔離搬移要人收尾：log 附要手跑的 UPDATE SQL；補判判垃圾但原貼文已刪（`_record_after_deleted`／`run_recheck`） | ERROR | 手動跑 SQL／重跑 db# | 重跑 `move_to_quarantine(pk)` | — | 第 2 批：私訊一次附 db# |
| 41 | 背景迴圈每次起來就掛：`supervise` 每 5 分鐘重啟一次，沒上限、沒通知 | ERROR 每 5 分鐘 | 修根因自動 | `pending()` 對照清單；重啟次數要在 `_run` 裡計數 | 0 次 | 第 1 批：重啟超過 5 次發一次 |

找尋 agent 列了、我判為**不用人介入**的：SearXNG 單一引擎被擋（30 分鐘自動再試）、Telegram 過濾模型沒回應（補判自動）、pgvector 掛掉時 Telegram LISTEN 每 5 秒重連的 ERROR（自動接上，只是洗 log）、聊天緩衝放回（5 分鐘自動）。這些只在面板顯示。沒盤到的：`scraper/`、`telegram_scraper/` 內部（session 失效時爬蟲怎麼報）、`services/state_db.py` 的 SQLite 失敗、`intro_profile_service`／`impression_moderation_service` 的寫入失敗路徑、`llm/persona/agent/publish.py` 的失敗處理（找尋 agent 的 not_examined 原文在 scratchpad，換 session 會消失）。

**第一批（OA-Q3 建議）**：kind 清單與門檻（先用建議值、面板看得到再調）：`lemonade`（放棄、重載失敗；連續連不上超過 10 分鐘）、`gpu_lock`（等滿 15 分鐘那一刻）、`pgvector`（raw flush 連續失敗 3 次）、`scraper`／`telegram_scraper`（最後一次推送、成功輪詢或最新一列超過 N 小時）、`discord_perm`（頻道送不出、管理活動、踢人；一頻道一小時一次）、`config_json`（一小時一次）、`persona_quarantine`（先修 bug 再接）、`ytdlp`（連續 3 首）、`loop_crash`（同一迴圈重啟超過 5 次）、`owner_id`（啟動自檢只記 WARNING，沒人收得到私訊）。第二批：`/admin_status` 顯示 E 類設定與 C 類容器狀態、第 5／10／11／14 列的按鈕。

**未定案（選項＋建議）**：
- **OA-Q1 放哪裡**：A 擴充 `utils/dm_notifier`＋view 與重測邏輯放 `discord_bot.py`（最小改動；但基礎層不能 import `llm_service`／`lemonade_admin`，重測只能塞進 `discord_bot.py`，和「按鈕都在 cog」的慣例相反）／B 基礎層 `utils/owner_alerts.py`＋新 cog `commands/owner_alert_commands.py`（介面層能依賴所有層，和 rollcall、週期提醒「一個功能一個 cog＋cog_load 註冊 view」一致，之後別的來源同一處加）／C 掛進 `management_commands.py` 的 `/server_manager`（已 1,200 行、ephemeral 一次性訊息、私訊按鈕會被 `require_access` 擋）。**建議 B**。**10-30 定案 B**（使用者看完草稿「我覺得可以」）。
- **OA-Q2 Lemonade 的事件怎麼交上來**：A 保留 `set_heal_listener`，`discord_bot` 轉送給 cog／B `lemonade_admin` 直接 `owner_alerts.emit`（技術層可以 import 基礎層），listener 與 `_on_lemonade_heal` 退場。**建議 B**：只剩一條通知路；A 等於兩套接法並存。
- **OA-Q3 第一批接哪些**：見上段。**建議**先做 1～3、8、12、13、17、19、21、33、38、39、41（13 項），E 類只做啟動自檢；門檻先用建議值。
- **OA-Q4 Lemonade 重測做到哪**：A 只清紀錄＋打 health／B 清紀錄＋真的算一筆（拿閘門）／C B＋成功後回填 NULL 向量、叫醒過濾補判。**建議 C**：health 在裝置掉了時照樣 ready（10-29 實查），只有真的算一次才知道；回填與補判不做要等重啟或 10 分鐘。
- **OA-Q5 面板形式**：A `/admin_status` 回只有本人看得到的訊息／B 常駐面板訊息（像自介面板，要綁頻道）／C 併進指令整理第二步的 `/panel admin`。**建議 A**，第二步做的時候再併。 10-29 晚上畫了四種樣式的外觀草稿（沒有功能）給使用者挑：私訊＋按鈕（剛收到／重測後）、`/admin_status` 只有本人看得到、常駐面板置底、新版容器版面每列一顆按鈕；Design 畫布 `https://claude.ai/artifact/EuZa3Mvu6ZQdpvM7M37vyH`，來源檔在 scratchpad `owner_alerts_canvas/`（換 session 會消失，畫布本身留著）。使用者要改樣式：在畫布上直接改或留言、截圖、或用文字講區塊與按鈕。**10-30**：使用者「我覺得可以」，接著要把頻道綁定也做成管理員面板——推定選常駐面板（B／③ 或 ④），和綁定面板放同一個管理頻道；③ 或 ④ 沒明說：狀態面板 9 項兩種都放得下，綁定面板 16 項受新版版面 40 個元件的上限，只能用選單（見下方「頻道綁定面板」小節）。**10-30 實作成私訊主控台**（CB-Q1 選 C）：「機器人狀態」是管理選單的按鈕（私訊裡一般訊息、伺服器裡只有本人看得到），不做常駐面板。
- **OA-Q6 解除後要不要回寫舊訊息**（放棄那則補「15:03 已恢復」）：**建議要**，message id 記在記憶體就夠（重啟就忘，沒關係）。
- **OA-Q7 要不要自動偵測 Lemonade 被重啟**（放棄期間每分鐘看 `/api/v1/health` 的 pid，變了就清紀錄、探測、私訊「偵測到重啟，已重新偵測：正常」）：**建議第二步**；按鈕先做，明確、簡單。
- **OA-Q8 別的容器自己的事件**（telegram-scraper 的 session 失效、scraper 的 403）要不要經 `notify_server` 新端點 `POST /notify/alert`（共用密鑰）送進來：**建議等**第 12、13 列的「太久沒消息」偵測上線後看夠不夠。

**牽動點（第一批）**：新 `utils/owner_alerts.py`、新 `commands/owner_alert_commands.py`、`discord_bot.py`（COMMAND_MODULES；拿掉 `_on_lemonade_heal` 與 `set_heal_listener`；啟動自檢）、`utils/dm_notifier.py`（`send_dm(view=)`）、`utils/discord_members.py`（`allow_dm`）、`llm/client/lemonade_admin.py`（emit）、`services/llm_service.py`（`probe`）、`llm/client/gpu_gate.py`（等滿時 emit）、`llm/storage/raw_message_store.py`（連續失敗計數）、`services/relay/base_monitor.py`＋`notify_server.py`（最後成功時間）、`services/relay/telegram_relay_service.py`（最新一列時間）、`services/relay/*`／`services/events/event_scheduler.py`／`services/community/rollcall_service.py`（Forbidden 處 emit）、`utils/utils.py`（config.json 壞 emit）、`llm/persona/agent/store.py`（`_is_failure`）、`music/player.py`（連續失敗）、`utils/background_tasks.py`（重啟計數）、`test_layering.py`／`test_shared_conventions.py`／AGENTS 共用元件表、測試新 1 檔＋改 `test_lemonade_heal.py`。commit 規劃三個：① 元件＋Lemonade（含 send_dm、require_access、probe、守衛、測試）；② 新偵測（pgvector、容器沒消息、權限 Forbidden 去重、config.json、yt-dlp、迴圈重啟）；③ persona 隔離 bug。

### 頻道綁定面板（2026-10-30 使用者提出；同日已實作，見下方「實作紀錄」）

**使用者 10-30**：看完草稿「我覺得可以」；「頻道綁定的功能可不可以也弄成管理員面板」。答：可以，和自介、社群查詢、週期提醒面板同一套。

**現況**：綁頻道只有一條路：`/server_manager` → 「頻道設定」→ 選功能（`settings/channel_registry.py` 16 筆：15 筆選頻道＋Telegram 路由的表單）→ 自己拼的頻道清單選單（`utils.utils.create_paginated_view`，25 個一頁）→ 寫 `config.json`、跑那一筆的 `on_set`（自介、社群查詢、週期提醒、商品上架綁完自動發各自的面板）。全程是只有本人看得到的一次性訊息；看不到「現在各綁哪裡」、沒有解除綁定（只能手改 `config.json`）、沒有測試（盤點表早就記著「頻道綁定沒有測試」）。

**機制一句話**：一則常駐訊息（`PanelBumper` 置底、位置記 runtime 檔、persistent view），內容每次發送時從 `channel_registry.all_settings()` 現讀（新登記一個功能就多一列，不寫死），依 `channel_type` 分組（📌 論壇／📝 文字／🔊 語音／⚙️ 特殊，圖示沿用現在選頻道流程的那三個），組內照登記順序，每列「名稱、目前綁的頻道、說明」（`<#id>` 在 Discord 顯示成可點的頻道名；沒綁顯示「未綁定」；Telegram 路由列現有路由）。超過一頁（每頁 8 項，放 `sys_settings` 可調）就分頁：「◀ 上一頁」「下一頁 ▶」兩顆按鈕改同一則訊息的內容，頁碼帶在按鈕的 custom_id 裡（`DynamicItem`，重啟後照樣能按）；置底重發時回到第 1 頁。選單「改這一頁的哪一項」只列本頁的項目，選了回一則只有本人看得到的訊息放 Discord 原生的 `ChannelSelect`（依那一項的 `channel_type` 過濾、可打字搜尋），選完寫 `config.json`、跑 `on_set`、面板重發。Telegram 路由那一項照舊開表單。

**要收的重複**：「選頻道 → 寫檔 → `on_set`」現在只在 `management_commands.set_channel_cmd` 裡；面板接上時抽成一個函式，`/server_manager` 的舊入口與面板共用，自己拼的頻道清單改用 `ChannelSelect`（分頁那份留給身分組）。加守衛：不准第二份「選頻道寫 config」流程。

**Discord 限制（決定版面）**：一則訊息最多 5 列元件、選單佔一整列、字串選單最多 25 個選項；新版容器版面（每列一顆按鈕）整則最多 40 個元件，16 項各一顆按鈕（每項 3 個元件）放不下。所以綁定面板用「一個選單＋一列按鈕（上一頁、下一頁、解除、重新整理）」，選單只列本頁的項目，登記表再長也碰不到 25 的上限；狀態面板（9 項）才能用每列一顆按鈕的版面。

**草稿**：同一個 Design 畫布的 ⑤ 三張，內容用登記表的 16 筆資料產生（`Bindings.dc.html` 第 1 頁、`Bindings_page2.dc.html` 按了下一頁、`Bindings_pick.dc.html` 選了一項之後的選頻道訊息）。使用者 10-30 看完第一版：「似乎不錯」。

**待答（CB-Q1～Q5，每題附建議）**：
- **CB-Q1 面板放哪**：A 在 `channel_registry` 加一筆「機器人管理頻道」（`admin_panel_channel_id`），第一次用 `/server_manager` 綁，`on_set` 當場發出綁定面板與狀態面板（和自介頻道同一種做法；指令整理第二步的 `/panel admin`、人格管理面板之後也放這裡）／B 新指令 `/admin_panel` 在哪個頻道打就發在哪（多一個指令、位置另記 runtime 檔）／C **（10-30 使用者提）主控台放和 bot 的私訊**：通知本來就走私訊，通知、重測、綁定、狀態都在同一個對話；不用開管理頻道、不用置底（私訊裡只有你和它）、不會因頻道權限設錯外流；入口是私訊裡打 `/server_manager`（指令全域同步，私訊本來就打得到，只差 `require_access` 要放行私訊）或傳任何一句話 bot 就回主選單。代價：多位管理員各有各的私訊，一人改了別人的面板不會自己更新（要按重新整理，或 bot 記每個人的面板訊息逐一改）；私訊裡沒有 `interaction.guild`，伺服器用 `bot.guilds[0]`（bot 只在一個伺服器）；誰是管理員要回伺服器查成員（`resolve_member`），只有群主就比 id；原生 `ChannelSelect` 在私訊能不能列伺服器頻道要實測，列不出就退回 bot 自己列的清單（現在那份、25 個一頁，少了打字搜尋）；`on_message` 要在最前面加私訊分流（私訊不存聊天、不進插話；現在私訊有文字會在記 log 那行出錯，`DMChannel` 沒有 `name`）。**改建議 C**（現在所有管理操作都是群主限定、只有一個人在管）：面板內容與按鈕寫成一份、不綁發送位置，之後有別的管理員再加頻道版只是多一個發送目標與一條權限檢查。選 C 則 CB-Q3 不用答。待使用者確認：管理員除了群主還有誰。
- **CB-Q2 誰能按**：A 只有群主（`require_access(owner_only=True)`，和現在的「頻道設定」一樣；別人按到回只有本人看得到的拒絕）／B 管理員也可以（`admin_only`）。**建議 A**：綁錯頻道影響整個 bot；面板所在頻道本來就只給管理員看，之後要放寬只改一個參數。
- **CB-Q3 和狀態面板是一則還是兩則**：A 兩則訊息、各自一個 `PanelBumper`（custom_id 不同不會互刪；有人講話兩則都置底）／B 併成一則（兩張 embed；但 5 列元件要同時塞狀態的重測按鈕與綁定的選單，之後加東西就擠）。**建議 A**。
- **CB-Q4 舊入口留不留**：A 留 `/server_manager` → 頻道設定，兩條路共用同一個函式（綁管理頻道本身也要靠它；符合指令整理的「舊入口仍可用」）／B 面板上線就拿掉，`/server_manager` 只剩身分組。**建議 A**，用一陣子再收。
- **CB-Q6 自己開表單那組叫什麼**（現在只有 Telegram 路由）：A 不另立分組，直接叫「Telegram 路由」放最後／B 叫「表單設定」，之後同類的歸這組。**建議 A**：只有一項，分組名讓人多想。
- **CB-Q7 公告頻道要不要算文字頻道**：登記表文字類項目的頻道選單只列文字頻道，Discord 的「公告」頻道（發文方式和文字頻道一樣）選不到。A 維持只列文字／B 文字類項目同時列文字與公告（`channel_types=[text, news]`，寫入與發送流程不用改）。**建議看你有沒有公告頻道要拿來綁**：沒有就 A。**10-30 定案 A**（使用者：「那就文字論壇跟語音」），頻道類型只有文字、論壇、語音三種。
- **CB-Q5 要不要加「解除綁定」**：A 加（面板上紅色按鈕 → 選一項 → 刪掉那個 key；`get_configured_id` 本來就把缺 key 當沒綁；已發出去的面板訊息不刪）／B 不加，維持手改 `config.json`。**建議 A**：現在沒有任何不動檔案的方法解除。

**牽動點**：`settings/channel_registry.py`（新一筆「機器人管理頻道」；分組直接用 `channel_type`，不加欄位）、`sys_settings`（每頁幾項）、`commands/management_commands.py`（抽流程、`ChannelSelect`）、新面板 view＋`PanelBumper`＋runtime 檔（`settings/runtime/admin_panel.json`）、`discord_bot.py`（選頻道版：有人講話就置底，和自介面板同一個 `on_message` 鉤子；選私訊版：`on_message` 最前面加私訊分流，私訊不存聊天、不進插話、不算 echo）、測試（面板內容列出每一筆 registry 與目前綁定、登記表多一筆面板就多一列、超過每頁數量才出現第 2 頁、第 1 頁「上一頁」不能按、選單只列本頁、選了寫對 key、解除刪 key、非群主被拒、`on_set` 有跑）、`test_shared_conventions` 守衛（第二份選頻道流程）。

**順序**：排在群主通知第一批之後（它先把管理頻道、cog、persistent view 立起來，綁定面板直接掛上去）；使用者要一起做就併成同一批的第二個 commit。

### 實作紀錄（2026-10-30，第一批；已 commit、11-01 02:47 上線）

**第二版（2026-11-01，PM-Q1～Q3）**：使用者指出綁定面板樣式不照草稿、管理功能沒整合、私訊按角色管理被拒。改成：`/server_manager` 一則新版版面選單（七組）進全部管理操作、私訊只由這個指令觸發（拿掉「私訊任何一句話回選單」，私訊對話留給之後的 AI 私聊）；機器人狀態面板照草稿 ④＋③ 做成九項紅黃綠（`commands/admin_status`）；綁定面板改新版版面。判準、動到的檔、測試、沒做的都在最上面 11-01 09:1x～09:4x 那筆盤點紀錄；重啟後驗收步驟：①私訊打 `/server_manager` → 七組選單；②「機器人狀態」→ 九項、正常收成一行、「展開」逐項、每項右邊重測、「全部重測」結果寫在最上面；③「頻道設定」→ 新版版面（標題下頁碼統計、每項一行、「解除某一項」）；④「角色管理」在私訊裡能列、能設；⑤「文章轉發」→ 子選單四顆（重送一篇開表單）；⑥「幽靈點名」→ 面板私訊給你（公開頻道那張刪掉）、按鈕在私訊裡能按、身分組設定選單是 bot 自己列的分頁選單、面板上有「點名頻道」一欄；⑦「AI」→ 立即寫日記、人格測試表單；⑧私訊傳一句普通文字不會有任何回應；⑨伺服器裡 `/server_manager` 只有本人看得到；⑩「伺服器資訊」→「列出頻道」「列出身分組」在私訊裡列得出來（純文字、長了分幾則）。驗收進度：14:39 重啟後 ⑩ 列出頻道炸（embed 欄位 1024 字），已改純文字分段（最上面 11-01 14:3x 那筆），要再重啟。

**使用者 10-30**：「目前只有我」「可以保留擴充的餘裕」「請幫我先實做」「注意避免重複造輪子」。

**定案（照建議；使用者說先實做）**：OA-Q1 B；OA-Q2 B（`set_heal_listener` 退場，`lemonade_admin` 直接 `owner_alerts.emit`／`inform`）；OA-Q3 這一批只接 Lemonade（放棄＝error、重載失敗＝warning）與 OWNER_ID 自檢，其餘 12 條第二批；OA-Q4 C；OA-Q5 → 私訊主控台（CB-Q1 C）：「機器人狀態」是管理選單的按鈕，不做常駐面板；OA-Q6 要；OA-Q7、OA-Q8 未做。CB-Q1 C；CB-Q2 A（只有群主；要放寬只改 `channel_panel._ACCESS`、`owner_alert_commands._ACCESS`／`_is_console_user` 三處）；CB-Q3 不用答；CB-Q4 A（舊入口留著，按下去就是新面板；舊的「選功能 → 自己拼的頻道清單 → 寫檔」流程刪了，寫檔只剩 `channel_registry.apply`）；CB-Q5 A；CB-Q6 A（Telegram 路由不另立分組、排最後、`register_custom(describe=)` 顯示現況）；CB-Q7 A。

**動到的檔案**：
- 新：`src/utils/owner_alerts.py`（基礎層匯流排：emit／inform／register／retest／active／status_line）、`src/commands/owner_alert_commands.py`（cog：私訊＋`RetestButton`、`StatusRefreshButton`、機器人狀態、私訊入口 listener、Lemonade 重測）、`src/commands/channel_panel.py`（頻道綁定面板：`render`／`send_panel`／`PanelButton`／`PanelPickSelect`）、`src/sys_settings/admin_console_settings.py`（`bindings_page_size`＝8）、`src/test/test_owner_alerts.py`、`src/test/test_channel_panel.py`。
- 改：`llm/client/lemonade_admin.py`（emit／inform、`heal_notice`、`heal_summary`、`close`；載入改每個組合自己的鎖；聽眾機制刪除）、`utils/dm_notifier.py`（`send_dm(view=)`、改回傳訊息或 None；Lemonade 文案搬到 `lemonade_admin`）、`utils/discord_members.py`（`require_access(allow_dm=)`、`home_guild`）、`services/llm_service.py`（`ProbeResult`、`probe(embedding=, model=, timeout=)`、`_PROBE_GATE_GRACE`）、`settings/channel_registry.py`（`apply`／`unbind`／`display_order`／`bound_channel_id`／`telegram_routes`／`type_icon`／`type_name`、`register_custom(describe=)`、模組說明改標準格式；Telegram 路由改成「表單只輸入來源 → bot 自己列的文字頻道清單選目標」，私訊裡也能用，寫入改用 `telegram_routes` 正規化）、`llm/client/embedding_client.py`（`SafeLLMEmbedding.close()`）、`commands/management_commands.py`（頻道設定 → 面板；`manager_menu`；「機器人狀態」按鈕；/server_manager 私訊可用；`cog_load` 登記面板的 DynamicItem）、`discord_bot.py`（COMMAND_MODULES 加 `owner_alert_commands`；拿掉 `_on_lemonade_heal`；`on_message` 一開始擋私訊）、`services/relay/telegram_relay_service.py`（`wake_recheck`）、`test/test_lemonade_heal.py`（改接 owner_alerts；＋救回來順便解除、`heal_summary`）、`test/test_shared_conventions.py`（兩條新守衛：`notify_owner_*`、直接寫綁定 key）、AGENTS 共用元件表（Lemonade 列改寫、群主通知列、綁頻道列、權限列）。

**哪裡用到、哪裡刻意不用**：
- `owner_alerts.emit`：只有 `lemonade_admin.heal`（放棄、重載失敗）；`inform`：自癒成功。第二批的 12 條偵測還沒接。
- `require_access(allow_dm=True)`：主控台的按鈕與選單、/server_manager、機器人狀態。角色管理刻意不放（身分組要在伺服器裡查），私訊裡按「角色管理」會回「只能在伺服器中使用」。
- `send_dm(view=)`：只有警報私訊。其他呼叫端（關鍵字、收藏、點名、交易、/askai 附件）只看真假值，回傳改成訊息物件不影響；`notify_keyword_hit`／`notify_song_liked` 照舊回 bool。
- 頻道清單：bot 自己列（沿用 `create_paginated_view`，25 個一頁）。刻意不用 Discord 原生 `ChannelSelect`：它在私訊裡只列得出那個私訊本身（discord-api-docs issue #5600），私訊是主要入口。
- `PanelBumper`：刻意不用。私訊裡只有群主和 bot、沒有置底需求；伺服器裡的面板是只有本人看得到的訊息。
- 錯誤邊界：`LLMService.probe` 的 `except Exception` 有 `# 邊界` 註記，`services/llm_service.py` 基準 4 不變；`owner_alerts` 在基礎層（不在掃描範圍），兩處接所有例外都註了理由。
- 解除綁定＝刪 key：盤點 agent 逐一讀過 15 個 key 的所有讀取端（`get_configured_id`、`load_config().get`、`get_channel_id` 三種），缺 key 都當沒綁、不會炸（`get_channel_id` 那兩個——歡迎、自介——沒綁時每次會記一行 WARNING，原本就這樣）。

**測試**：`test_owner_alerts.py`（匯流排去重／補送／跨執行緒／key 消毒、cog 的私訊與回寫、只有群主、同一次重測解除的其他警報也回寫、機器人狀態、私訊入口、Lemonade 重測成功與失敗、`require_access(allow_dm)`、`home_guild`、`send_dm(view)`、`probe` 拿閘門／不重試／失敗回報／等不到）；`test_channel_panel.py`（分組與現況、登記表多一筆就多一列、分頁與夾頁碼、選單只列本頁、改綁寫對 key＋跑綁定後動作＋重畫、只有本人看得到的面板不主動重畫、表單類走自己的流程、解除綁定、本頁沒綁的、非群主三處都拒、私訊用唯一伺服器、多個伺服器請回伺服器、custom_id 來回、`apply` 拒表單類、`telegram_routes` 正規化）。故意改壞 6 處（去重、私訊放行、頻道型別過濾、解除沒刪 key、重測成功不解除、探測不拿閘門）與兩條守衛各 1 處都變紅。啟動 gate 綠（89 條）。完整套件：見下方「複查與完整測試」。

**重啟後驗收（使用者做，避開 04:00～07:30）**：
1. 私訊 bot 任何一句話 → 回「伺服器管理」選單（角色管理、頻道設定、機器人狀態）。
2. 「頻道設定」→ 面板：每一項綁哪裡、第 1／2 頁、「◀ 上一頁」灰掉；「下一頁 ▶」→ 第 2 頁。
3. 選一項（例：AI 日記頻道）→ 只有你看得到的頻道清單只列文字頻道 → 選一個 → 「✅ 已將…」且面板自己重畫（私訊裡不用按重新整理）。
4. 「解除綁定」→ 選單只列本頁已綁的 → 選了 → 面板那一列變「未綁定」。
5. 「機器人狀態」→ 兩列（模型後端、群主通知）綠燈＋「重測 模型後端」「重新整理」；按重測 → 同一則補一行「HH:MM 重新偵測：正常——向量模型 x 秒；聊天模型 y 秒；已開始回填…」（真的算一次、拿閘門，插話那段會等）。
6. 伺服器裡 `/server_manager` → 頻道設定 → 面板只有你看得到；改完要按「重新整理」。
7. 下次 Lemonade 放棄時私訊底下有「🔄 重新偵測」；按了同一則回寫。
8. log：啟動時「已載入指令模組: commands.owner_alert_commands」，沒有 ERROR；私訊 bot 不再出現 `DMChannel` 的 AttributeError。

**已知限制／要實測**：embed 裡的 `-# 說明` 小字是否照預期顯示（不顯示就改成一般行）；只有本人看得到的面板（伺服器裡）bot 不會主動重畫；「機器人狀態」上 Lemonade 那顆按鈕沒有警報時 key 是 `*`；警報私訊的訊息物件記在記憶體，重啟後舊私訊的按鈕還能按、但解除時不會回寫那則。

**下一步**：② 第二批偵測（pgvector 連續失敗、scraper／telegram-scraper 沒消息、Discord 權限 Forbidden 去重、config.json 壞、yt-dlp 連續失敗、迴圈重啟次數）各自 `owner_alerts.emit`＋登記重測；③ persona 隔離 bug（第 38 列）；OA-Q7 自動偵測 Lemonade 重啟。commit 等使用者說。

**複查與完整測試**：複查 workflow（2 個 lens：Discord 互動正確性、接線與慣例；12 條發現各由一個 agent 反證，沒有一條被駁回）：
1. **高**：`heal_summary()`／`reset_cache()` 在 event loop 上拿 `lemonade_admin._LOCK`，而 `ensure_loaded` 拿著同一把鎖做 30～180 秒的載入 HTTP → 群主按狀態或重測時可能卡住整個 bot。修：載入改成每個組合自己的鎖、`_LOCK` 只保護 dict；cog 端狀態與清紀錄都 `asyncio.to_thread`。測試：載入中呼叫狀態與清紀錄要在 1 秒內回來。
2. **中**：從「機器人狀態」按重測，整個 view 被換成單顆按鈕、embed 停在舊狀態、重新整理不見。修：按的那則有 embed 就當面板，結果寫在最上面、`status_message()` 整個重畫。
3. **中**：Telegram 路由的表單用 Discord 原生 `ChannelSelect`，私訊裡列不出伺服器頻道、表單送不出去。修：表單只輸入來源，送出後回 bot 自己列的文字頻道清單（和面板同一種），同一來源再設一次就多一個頻道。
4. 低：探測不重試、重載完不重送 → 第一次重測遇到壞掉的 5xx 必報「還是壞」卻同時私訊「已恢復」。修：帶後端壞掉訊號的失敗再探一次。
5. 低：同一把先「壞了」後「好了」兩則通知各自 spawn，可能交錯 → 舊警報標不成已恢復。修：通知一則一則送（`asyncio.Lock`）。
6. 低：重測失敗也把那則私訊忘掉 → 之後自癒成功回寫不到。修：失敗保留（連同最後寫上的文字）。
7. 低：重測函式出錯時按鈕停在「偵測中」。修：接住、補一行「重測出錯」、按鈕還回去。
8. 低：向量探測每次新建的 HTTP 連線池沒關；聊天探測借用正式 client 的 admin。修：`SafeLLMEmbedding.close()`／`LemonadeAdmin.close()`，探測用自己的 admin、用完都關。
9. 低：選頻道後先寫檔再回應，綁定後動作（建身分組、發面板）可能超過 Discord 的 3 秒。修：先回「寫入中」再寫，綁定後動作出錯也講、面板照樣重畫；解除綁定同樣。
10. 低：每頁幾項沒有上限，超過 25 一個選單放不下。修：`page_size()` 夾到 25、設定 `le=25`。
（第 3、6、9 條各有兩個 reviewer 從不同角度各報一次，合併計。）修完每條都有測試，故意改壞 6 處都變紅。容器內完整套件第一次 1,937 條全綠（165 秒）；修完複查後 gate 再跑一次抓到探測那段多了一個沒註記的 `except Exception`（基準 4 變 5），改成只接 `LlmAPIError` 後 gate 89 條全綠、完整套件 1,949 條全綠（2 條跳過，94 秒）。

### 線上事故：向量模型 ErrorDeviceLost 與自癒空轉（2026-10-31；已實作修正並 commit、未重啟）

**結論**：向量模型是真的壞，「重新偵測」判斷正確；壞的是自癒——它從來沒重開過任何行程，卻回報「已重載一次恢復」並解除警報。上面複查第 4 條「再探一次」的修法因此也救不回來：重載是空轉，再探必然還是 500。

**證據**
- 直接用 httpx 打 Lemonade `/v1/embeddings`（不經 bot 程式）：20:06 兩筆都 500 `decode() failed: vk::CommandBuffer::end: ErrorDeviceLost`，0.01～0.05 秒回。Lemonade 自己的 log（唯讀 websocket `/api/v1/logs/stream`，16:59～20:14 共 5,000 行）：embeddings 358 次 500、0 次 200；同期聊天模型 32 次 200。
- Lemonade 2026.43.3 原始碼：`server.cpp` `handle_load` → `router.cpp` `Router::load_model`（約 907～945 行），行程還活著、watchdog 沒觸發、解析後選項（bot 送的 `-sm none -mg 1` 會被補成 `-sm none -mg 1 --parallel 1`）和執行中相同時，只記 `Model already loaded, updating access time and pinned status` 就回 200；`save_options` 只管寫不寫 recipe_options.json。Lemonade log 對 bot 每次自癒都是這行，前後 1～2 毫秒。
- 20:08～20:48 每 15 秒讀 `/api/v1/health`：bot 在 20:35:10、20:37:36、20:39:09 各「自癒重載」一次，向量模型 pid 始終 22672。llama-server log 的行程時間推回這個行程是 10-29 16:33 起的，兩天多沒換過；`llm_anomaly.log` 今天的健康快照 pid 也全是 22672。
- 歷來自癒 0 次有效：10-29 三次都沒救回，15:02 重啟 Lemonade 才好；10-31 聊天模型 3 次、向量模型 17 次全部空轉。聊天模型 16:28 左右自己換了行程（pid 30296→30276），bot 端看不到原因（Lemonade 端可能是舊行程退出被 watchdog 重載，或有人在 Windows 端操作）。
- Lemonade 不會自己發現這種壞法：watchdog 只認行程結束、請求卡 90 秒且 health 連 3 次沒回、連線失敗、訊息含 "compute error"／"gpu hang"；llama-server 的 `/health` 不看 GPU 一律 ok；`/api/v1/health` 的 `backend_alive`、`watchdog_reset` 列出來的永遠是 true／false，看不出好壞。
- 真的重開單一模型只有：`POST /api/v1/unload {"model_name": …}`（evict、Windows 上 TerminateProcess；**body 不帶 model_name 會卸載全部**；沒載入回 404）→ 再 load，或讓下一個請求自動載回（自動載入用 recipe_options.json 存的選項，bot 之前 `save_options=True` 存過 ctx 4096、`-sm none -mg 1`）。重開能不能救回 DeviceLost 是推論：聊天模型同樣用到 Vulkan1，16:28 換行程後一直正常。
- 觸發（log 鑑識）：兩次都在一個雙卡 27B 插話請求進行中或剛結束（10-31 先是聊天 16:16:37 `waitSemaphores` DeviceLost，向量 16:18:23 跟著壞；10-29 是聊天請求 180 秒逾時後第一個向量請求就壞）。沒有產圖、Hermes、reranker、search-mcp 算向量；prompt 大小、帶圖都和平常一樣，插話逾時每天 10～20 次只有這 2 次接著 DeviceLost。比較像顯示卡或驅動層級掛住（Windows TDR），同卡上的向量行程跟著丟了 VkDevice。要確認得看 Windows 事件檢視器（系統記錄、顯示驅動停止回應並已復原，事件 4101）在 10-29 14:19、10-31 16:16 前後有沒有紀錄。
- 聊天緩衝：16:18 起每 5 分鐘寫入失敗放回，20:35 累積 304 則；只在記憶體，bot 重啟會清掉，但 raw 都有（唯讀查詢：近 14 天 raw 有、聊天向量庫沒有的 313 則全在 16:18:08 之後），補寫每 15 分鐘 20 則、約 3.8 小時補完；補不回的只有編輯（目前 0 則）與靠非 Tenor 連結預覽才夠長的訊息。所以先修 Lemonade、等緩衝寫回再重啟 bot。

**缺陷**（程式審查 10 條，每條由一個 agent 反駁驗證；9 條成立、1 條修正）
1. **高** `lemonade_admin.heal`（171 行）只送 `/api/v1/load`，對還活著的模型是空操作；模組說明「重載模型＝重開那顆後端行程」的前提不成立。
2. **高** `heal`（177～180 行）load 回 2xx 就 `inform`「已重載一次恢復」：不驗證、不比 pid；`inform` 先 `resolve` 警報、清掉一小時去重，`deliver` 收到 info 就把舊警報私訊補「✅ 已恢復」。
3. **高** `handle_retest`（216 行）用 before−after 差集標「已恢復」：重測的向量探測自己觸發 heal → inform 解除警報 → 同一則私訊先「❌ 還是壞」再「✅ 已恢復」（19:32 那則）。
4. 中 每小時 3 次是滑動視窗（144 行）：`_GAVE_UP_AT` 只壓通知、不擋重載，放棄後約 47～52 分鐘又開始重載，所以 18:33 那輪沒人按也有三次、三則都寫「第 3 次」；放棄訊息寫的「不再自動重載」不成立。（原報「重新偵測清紀錄造成多三次」被修正：清紀錄只讓計數從 1 重算、探測自己花掉一次，19:35、19:38 那兩次不清也會發生。）
5. 中 `retest_lemonade`（262 行）不看 key，`ok = embed.ok and chat.ok`：向量壞著時，按聊天模型那則也報「還是壞」，聊天那把（16:26 放棄、早就好了）一直解除不了。
6. 低 「機器人狀態」燈號只看同 kind 有沒有未解除警報、狀態文字看 `heal_summary`，兩者對不上：今天 16:26 後燈一直紅，但紅的是早就好了的聊天模型，壞掉的向量模型警報反而被自癒解除；`_GAVE_UP_AT` 重載成功不清，狀態寫「已放棄」時其實正在重載。
7. 低 探測失敗原因只剩「LlmAPIError: HTTP 500」（`llm_service.py` 420 行用 `str(exc)`，原文在 `exc.detail`），群主看不到 DeviceLost。
8. 低 探測的「已重載，再探一次」log（414 行）不看 heal 有沒有真的做；16:30:43 兩次重測同時跑，第二次落在冷卻期沒重載，log 照寫。
9. 低 search-mcp 行程也會自癒（`vectors.py`、`rerank.py` 經 `admin_for`），但那個行程沒接 listener，emit／inform 永遠留在 `_PENDING`；冷卻、上限、放棄各行程各算，群主按重新偵測只清 bot 的。這次事故 search-mcp 沒觸發。

**定案（10-31 21:0x 使用者「全部依照你的建議」）**：SH-Q0 A、SH-Q1 A、SH-Q2 A、SH-Q3 A、SH-Q4 A；缺陷 6～9 一起修。原選項：Q0 A Claude 卸載向量模型／B 使用者重啟 Lemonade／C 不動；Q1 A unload 再 load／B 只 unload 等自動載回／C 維持；Q2 A pid 換了＋真的算一次才說恢復／B 只比 pid／C 維持；Q3 A 放棄後停到重新偵測或偵測到重啟（OA-Q7）／B 維持滑動視窗改文案；Q4 A 兩顆都測各自解除／B 只測按的那顆。

**SH-Q0 執行（21:04:48）**：`POST /api/v1/unload {"model_name":"Qwen3-Embedding-0.6B-GGUF"}` → 200，pid 22672 結束，聊天模型與 reranker 不受影響；下一個請求自動載回成 pid 15000（`--ctx-size 8192 -sm none -mg 1`），21:11～21:13 第一輪寫入 28 則成功（120 秒閘門預算到就停，剩 339 則照節奏一輪輪寫）。重開確實救得回來——這次是行程壞、不是卡壞。

**實作紀錄（10-31 21:1x～23:0x；未 commit、未重啟——bot 跑的還是舊碼）**
- `llm/client/lemonade_admin.py`：`heal(model, reason, kind=)` 改成 `restart`（unload 帶 model_name，404 照載；再 load，save_options=False）→ health 比 pid（沒換算還是壞）→ `verify`（照 health 的 type，沒有就用呼叫端交的 kind，送最小請求；類型都不知道不算救回）→ 才 `inform`「已重開（行程 A→B）並確認能算」；還是壞 `emit` warning「重開了還是壞（第 N／3 次）」、重開失敗 `emit` warning（原因用 `backend_message`）；第 3 次還是壞或失敗、或用完之後又壞就 `_give_up`（error）。放棄持續（`_GAVE_UP` 記 pid），只有 `reset_cache`（群主按）或 `release`（自動重測確認好了）清。`_HEALING` 重開中不重入、冷卻從重開結束算；`_GENERATION` 讓 reset／release 之前開始的那次做完不寫回放棄與冷卻。`allow_heal()`：只有 bot 行程自癒（cog 載入時開），search-mcp、批次不開——各行程各自重開會互相換掉對方看到的行程。新 `replaced_since_give_up`（同一個新行程只報一次）、`check(model)`（單獨驗一顆，類型照 health 或上次自癒記下的）、`heal_summary` 改「重開」用語。
- `llm/client/http_client.py`：`backend_message(exc)`（取 Lemonade 錯誤 JSON 最裡層的 message；`judge_failure` 的 heal_reason 與探測原因都用它）；`_heal_kind(path)` 依端點把請求種類交給 heal；`BackendAdmin.heal` 與 `ollama_admin.heal` 簽名加 `kind`。
- `llm/client/gpu_gate.py`：新共用元件 `wait_at_most(gate, seconds)`（只限制等閘門，等不到丟 `GpuBusy`，進去後不限時）；`services/llm_proxy.py`、`llm/retrievers/context_retriever.py` 原本各寫一份 `AsyncExitStack＋asyncio.timeout`，改用它；`test_shared_conventions` 加守衛；AGENTS 共用元件表改了 GPU 閘門、Lemonade、群主通知三列。
- `services/llm_service.py`：`probe` 時限只管等閘門（等不到回 `ProbeResult.busy=True`，不算壞），拿到之後不整段限時（以前 150 秒到期會在重開做到一半時放掉閘門、關掉 admin 的連線池）；聊天探測的 admin 用 `heal_load_timeout=limit`；新 `probe_backend(model)`（經 admin.check，重新偵測測主模型以外的）、`replaced_backends()`；失敗原因帶後端原文。
- `commands/owner_alert_commands.py`：cog 載入開自癒、卸載關；每 60 秒 `check_backend_restarts`（supervise＋periodic）：放棄中的模型行程換了 → 探一輪（不 reset，別顆照舊放棄）→ 好了 `inform`、還是壞 `resolve` 後重新 `emit`（新的一輪不吃去重）、顯示卡忙下一分鐘再測。`retest_lemonade` 先 reset 再 `_probe_lemonade(extra=[key])`：兩顆主模型＋按的那顆（不是主模型就 `probe_backend`），各自解除、能算的 `release`、向量好了才回填、聊天好了才叫醒補判，回報照按的那顆。`_append_line`：私訊太長時保留最新那行。
- `utils/owner_alerts.py`：去重看最後一次真的送出的時刻與嚴重度，升高照送；`_PENDING` 只留 50 則。`llm/storage/store_chat.py` 的閘門預算註解改成自癒的最壞情況。
- 測試：`test_lemonade_heal.py` 重寫（重開、驗證、類型、放棄持續、重開中、冷卻、世代號、release、check、replaced、只有開了的行程自癒）、`test_owner_alerts.py` 補（升級去重、待送上限、各自判定、重開偵測三種結果、別顆單獨測、cog 開關自癒、保留最新那行、探測只限時等閘門、busy）。容器內完整套件 1,994 條全綠（2 條跳過）。突變 39 個（每條新規則改壞一次，三輪累計）全紅、還原全綠。
- 獨立審查兩輪（workflow）：第一輪 19 條（1 條被推翻）——必修 9 條已在上面改掉（health 查不到也說救回、冷卻從開始算、探測逾時放閘門、自動重測清全部、忙碌誤報壞、升級比錯對象、第 3 次失敗不放棄、跨行程互相誤判、reranker 沒測就解除），順手 3 條（訊息截斷、reset 競爭、store_chat 註解）也改了。第二輪 13 條全部成立（沒有被推翻的）——改了 5 條：探測的「再探一次」改在同一段閘門裡做、卡死信封（當連不上丟出）也再探，重測結果分得出「⏳ 這次沒測到」（`RetestResult.untested`，不寫成「還是壞」）；第 3 次 unload 成功、load 失敗時放棄記當下的行程（記舊的會被當成有人重開過）；世代號分兩層（`release` 只換放掉的那幾顆，別顆正在跑的第 3 次照樣放棄、通知）；`_probe_lemonade` 順便解除的警報私訊也補「已恢復」；同一把又送一則私訊時舊那則標「見下一則」、按鈕停用。沒有再跑第三輪審查：第三輪的改動都是針對第二輪發現的小修，各有測試與突變把關。

**事故（低嚴重度，已處理）**：第一輪突變測試「向量模型還壞也回填」那個改壞版本，測試沒有把 `backfill_embeddings` 換成替身，21:24:32 真的連上 pgvector，把 `ai_interactions` 12 筆 embedding 為 NULL 的列補上向量（只填空欄位、沒有覆寫或刪除；用的是剛修好的向量模型，和重新偵測成功後 bot 會做的事一樣）。唯讀查詢確認現在 NULL 向量 0 筆。防再發：`test_owner_alerts.CogTests.setUp` 對所有 cog 測試把回填換成替身，並補「向量壞時不回填」的斷言。

**記錄不修（都是低嚴重度，等使用者決定要不要排）**：①兩次重測同時跑時回填會重複跑（回填可重複執行、無害；要修就在 `backfill_embeddings` 加不可重入旗標）。②cog 第一次用到時在 event loop 上建 `LLMService`（同步讀設定檔，毫秒級，和 ambient、emoji_autofill 同一寫法）。③Hermes 非串流轉送的租約（330 秒）在自癒期間不續：請求跑了 200 多秒才壞、再加上重開時間超過租約時，watchdog 會取消持有者、放掉閘門，執行緒裡的重開照跑。④`owner_alerts.emit` 交給 listener 就算送過，私訊實際沒送出（Forbidden、resolve_user 回 None）也會吃掉一小時去重；放棄通知沒送到不會補送，警報仍在「機器人狀態」。⑤`telegram_filter` 用 `asyncio.wait_for` 包住整段 `chat_raw`（含拿閘門）：到期時閘門先放、執行緒裡的自癒還在重開。這是既有寫法，但自癒改成真的重開後風險變大；修法要讓 `chat_raw` 接受「等閘門上限」或拿掉外層 `wait_for`，不能直接套 `wait_at_most`。⑥按鈕重測沒有總時限，病態組合（每步都接近逾時又成功、等閘門都接近上限）可能超過 Discord 互動 token 的 15 分鐘，私訊停在「偵測中…」。

**待辦**：①~~重啟~~ 已上線：主機 11-01 02:46 重開，容器 02:47 起來，跑的是 commit 後的程式（`ce333ee`）。②驗收：「自癒真的重開」已在線上驗到一次（見下一小節）；群主按「重新偵測」兩顆各一行還沒驗。③Windows 端查證併進下一小節 DL-Q1。④~~commit~~ 11-01 已 commit、未 push。

### 第一次真的自癒（2026-11-01 05:36）與「顯示卡還是 llama.cpp」的判讀

**經過**（bot log＋Lemonade 自己的 log：唯讀 websocket `ws://<Lemonade>/logs/stream` 送 `{"type":"logs.subscribe"}`，回最近 5,000 行，這次涵蓋 04:39～06:34）：
- 05:36:25 聊天模型（27B，兩張卡分層）開始跑偏好抽取（9,417 字詞的 prompt）；同一秒向量模型算一筆 4 字詞的查詢，10 毫秒完成。
- 05:36:30 群主的 /askai 要算一筆向量（4 字詞、和上一筆一樣的內容）：卡了 8 秒，05:36:38 `ggml_vulkan: device fault on Vulkan1: Device lost detected`，回 500。
- 05:36:38 bot 自癒：unload（結束 PID 932）→ load，新行程 PID 24848 在初始化第 9 秒（05:36:49）**也**收到 `device lost on Vulkan1`。Lemonade 判定載入失敗，自己「卸載全部模型再重試」：reranker 被卸掉，27B 因為正在跑而延後（tombstoned，之後沒有真的卸）。05:36:56 重試開 PID 9640，1.5 秒載好、能算。bot 比對 pid（932→9640）、驗證通過，05:36:59 私訊群主「已重開並確認能算」，/askai 照常回答。
- 聊天模型同時也用 Vulkan1，但沒有 DeviceLost，只是 05:36:26～05:36:53 處理 prompt 的速度從每秒約 224 個字詞掉到約 96 個，之後恢復。
- 另外看到（和顯示卡無關）：那筆偏好抽取一次生成了 9,727 個字詞、跑了 294 秒（`preference_extractor` 呼叫 `chat_raw` 沒給 `max_tokens`），模型只能一次處理一個請求，後面排隊的插話與 persona agent 被卡到 05:44；bot 端 05:41:25 等到逾時（log 裡的「preference 抽取 LLM 失敗」）。

**判讀**：比較像顯示卡或驅動層級，不像 llama.cpp 行程自己的狀態或請求內容。理由：①剛開的新行程、不同 pid、什麼都還沒算，也在同一張卡上收到 device lost，表示壞的是那張卡當下的狀態，不是舊行程裡壞掉的東西；②約 18 秒後同樣的程式、同樣的參數又正常了，像 Windows 的 GPU 逾時重置（TDR）跑完恢復；③出錯的請求是 4 個字詞、5 秒前才成功過的同一句。歷次（10-08、10-29、10-31、11-01）都是 27B 正在大量計算、同時有向量請求打到 Vulkan1。從 Linux 這邊分不出是驅動處理兩個行程同時用一張卡出問題、1 號卡硬體不穩，還是某個 llama.cpp 的 Vulkan 計算把驅動弄掛；要再往下只能看 Windows 端。

**還沒定案的問題**
- DL-Q1 Windows 端查證（只有使用者能做）：事件檢視器的系統記錄找事件 4101（顯示驅動停止回應並已復原）與 WHEA-Logger（硬體錯誤），`C:\Windows\LiveKernelReports\WATCHDOG` 有沒有同時間的 dump；時間點 10-29 14:19、10-31 16:16、11-01 05:36:30～05:36:50。**建議：做**；有 4101 就是 TDR，有 WHEA 就懷疑硬體。
- DL-Q2 自癒重開前先等一下：A＝unload 後等約 20 秒再 load（這次第一次錯誤後至少 11 秒卡都還沒恢復，馬上載入只會再壞一次，還讓 Lemonade 卸載全部模型；20 秒是這一次的觀察，樣本只有一個）；B＝維持現狀。**建議 A**，成本是每次自癒向量模型多停 20 秒左右。
- DL-Q3 降低兩個行程同時用 Vulkan1：A＝向量模型改用 CPU（完全不共用顯示卡；聊天寫入、查詢的向量會變慢，search-mcp 批次算向量慢很多）；B＝向量模型改到 Vulkan0（`-mg 0`）當實驗，錯誤跟著搬到 Vulkan0 就是共用的問題、不是 1 號卡本身；C＝DL-Q1 查到 4101 就把 Windows 的 TdrDelay 調長（這次向量請求卡了 8 秒）；D＝先不動，靠自癒（這次整段約 20 秒、只壞一個請求）。**建議 D，等 DL-Q1**：查到 4101 走 C，查到 WHEA 先走 B 確認是不是那張卡。
- 另列（不同主題）：偏好抽取沒有輸出上限，要不要加 `max_tokens`。

</details>

## 指令整理與管理入口：三階段規劃與權限檢查收斂（2026-03～10）（歸檔 2026-11-07，原至 2026-10-02）

> 兩份舊規劃合併後的版本：斜線指令盤點、三步計畫（子指令 → 管理面板 → 網頁 dashboard），以及暫緩的權限檢查收斂。
>
> 關鍵字：指令收斂、/persona 子指令、管理面板、網頁 dashboard、test_commands、/anonymous、check_guild、require_permission、has_permissions、權限檢查

<details>
<summary>展開原文（約 3,817 字）</summary>

> 從 `AI_HANDOFF_AND_TODO.md`「指令整理與管理入口（規劃，未動工）」區塊（`command-consolidation-dashboard`）瘦身前的完整原文；交接檔只留現況、規則與坑、未定案、待做。

> 2026-10-02 由「指令收斂與管理 Dashboard」（2026-08-20）與「Discord Bot 管理入口與指令整理 TODO」（2026-03-31）合併，兩段原文已歸檔到 `TODO-completed.md`。

**現況（2026-10-02 盤點）**：19 個斜線指令（10-13 刪 2 個萃取指令後；原 21）＋2 個前綴指令。原本記的 `askai_prompt_debug`／`askai_prompt_trace`／`askai_response_trace` 已不存在；PR-Q4 已在 10-13 刪掉 `personality_extract`、`personality_extract_status`。

| 檔案 | 指令 |
|---|---|
| `commands/llm_commands.py` | `askai`、`ai_diary`、`persona_agent_test`、`personality_extract`、`personality_extract_status` |
| `commands/user_commands.py` | `forget_tag`、`list_item_price`、`watch_keywords` |
| `commands/article_commands.py` | `article_manager`、`get_baha_post`、`resend_article` |
| `commands/management_commands.py` | `server_manager`、`server_info` |
| `commands/rollcall_commands.py` | `rollcall_panel` |
| `commands/trade_commands.py` | `trade_info`、`select_item`、`set_item_prices` |
| `commands/test_commands.py`（正式環境也有載入） | `anonymous`、`echo`、`list_forum_posts`、`multi_select_demo`；前綴 `ping`、`helloworld` |

### 第一步：分層與子指令（低風險）

- [ ] `test_commands` 改成只在開發環境載入（現在正式環境也載入，其中 5 個斜線指令沒有任何權限檢查，見下方「權限檢查收斂」）
- [ ] 完成命令分類清單（使用者／管理者／開發）——上表是起點
- [ ] AI／人格這群收成一個 `/persona` 子指令群組：兩個萃取指令 10-13 已刪（PR-Q4），剩 `persona_agent_test` → `/persona test`、`forget_tag` → `/persona forget_tag`、`ai_diary` → `/persona diary`。`/askai` **保持獨立**（天天用，藏進子指令反而難找）
- [ ] 文章類提子指令設計稿：`/article start|stop|status|test`
- **時機**：兩個萃取指令 10-13 已刪、當時沒有順便做子指令（M4 的範圍只拆函式）；與「程式結構整理」的 P2（拆 `llm_commands.py`、`user_commands.py`）一起考慮

### 第二步：管理入口與面板

- [ ] 建立 `/panel admin` 空殼，把 `/article_manager` 掛進主控台（保留舊命令）
- [x] 頻道綁定面板（10-30 實作，未 commit）：`commands/channel_panel.py`；入口是私訊主控台與 `/server_manager` → 頻道設定（同一份面板，舊的選功能→頻道清單流程已刪）；設計與定案在[需要群主介入](#需要群主介入的狀況私訊重新偵測按鈕管理面板2026-10-29-規劃未動工)的「頻道綁定面板」與「實作紀錄」小節
- [ ] 管理入口：群主私訊 bot 任何一句話就拿到管理選單（10-30 已做）；人格管理面板、`/article_manager` 掛進主控台還沒做
- [ ] 人格管理面板，沿用 `intro_panel`／`community_panel`／點名的常駐訊息＋按鈕：上次萃取時間、成功筆數、失敗清單；按鈕：立即跑、跑 agent（選成員）、看最近一次 diff；agent 執行中顯示進度（步數／已用 token）。比子指令好在不用記指令名，而且看得到狀態

### 第三步：網頁 dashboard（真正的目標）

`notify_server.py` 已經是 bot 內的 aiohttp server（`/health`、`/notify/{source}`），加唯讀路由即可。資料源都已存在：

| 頁面 | 資料源 |
|---|---|
| 人格版本歷史／長期漂移 | `persona_agent_versions` |
| 執行紀錄、失敗率、幻覺率趨勢 | `persona_agent_runs` |
| 精簡版 vs agent 完整描述並排 | 兩張表＋`auto_personality` |

**安全性**：只綁 host-only 介面或加 token，絕不開在對外網段——內容是成員的完整發言證據。

### 追蹤指標

- [ ] 管理操作是否可由單一入口完成
- [ ] 指令數量是否下降或更清楚
- [ ] 正式環境是否已隔離開發命令
- [ ] 是否維持可回滾（舊入口仍可用）

### 權限檢查收斂（暫緩）


**現況（2026-10-02）**：9/21 已做掉一部分——`7817bd4` 刪掉兩個 `_check_guild_and_owner` 薄包裝、`3cbf28c` 點名按鈕改走共用的權限檢查（原本少了「在不在伺服器內」，私訊時會 `AttributeError`）。剩兩種寫法並存：5 個指令用 `@app_commands.checks.has_permissions(administrator=True)`（錯誤訊息是英文預設值），其餘在函式內呼叫 `utils/utils.py` 的 `check_guild(...)`（33 處）。9/04 的完整盤點已歸檔。

**9/04 做過、已還原的方案（可直接重做）**
1. `check_guild` 更名 `check_permission`——原名只描述四件事裡的第一件
2. `utils/utils.py` 新增 `require_permission(owner=/admin=/role=)` 裝飾器＋`PermissionDenied`（`app_commands.CheckFailure` 子類）；`check_permission` 自己會回中文訊息，而 `discord_bot.on_app_command_error` 會把非冷卻錯誤再回一句「執行命令時發生錯誤」，**不自訂例外就會連發兩則**
3. 指令改用裝飾器；按鈕／選單 callback 不是 app command，用不了裝飾器，改直呼 `check_permission`

**重做時的坑**
- `llm_commands` 的 `persona_agent_test` 是**入口出口各驗一次**（followup token 有 15 分鐘，期間權限可能被撤銷）——刻意的縱深防禦，不可以當成重複刪掉
- 裝飾器必須在 `@app_commands.command` 之下才會被註冊成 check

**尚未解決（一起盤到）**
- ⚠️ `/anonymous` **零權限檢查**：任何人可叫機器人匿名發訊息到他看得到的任何頻道；`test_commands` 另外幾個同樣零檢查。使用者 2026-09-04 決定「沒有特別要求就先不用」動
- owner 語意不一致：`check_role` 中 OWNER_ID 自動通過，`check_guild(admin_only=True)` 中不會
- `config.json` 的 `role_mapping.Moderator` 是空陣列，`check_role` 對未設定的角色 fail-closed——哪天有指令寫 `required_role="Moderator"`，除 owner 外全數被擋，訊息卻像權限不足

**待決：AST 守衛**：提案在 `test_shared_conventions.py` 加「每個 `@app_commands.command` 都必須有 `@require_permission`」，白名單用函式層級（`檔名.函式名`）。它跑在容器啟動 gate 裡，誤判會讓 bot 起不來，本專案一貫「寧可漏判不要誤判」；風險未評估完，**先不加**。

</details>

## 指令收斂與管理 Dashboard（改寫前原文，歸檔 2026-10-02，原 2026-08-20）

> AI／人格相關指令 9 個、名字前綴不一，規劃收成 `/persona` 子指令群組，再做管理面板與網頁 dashboard。
>
> 關鍵字：subcommand group、/persona、管理面板、notify_server dashboard、M3/M4 時機（已過時）

<details>
<summary>展開原文（約 1,770 字）</summary>

<!-- @meta
id: command-consolidation-dashboard
type: DECISION
status: draft
last_confirmed: 2026-08-20
depends_on: persona-extraction-agent
affects: commands/, notify_server
-->

**問題**：目前 28 個 slash command，其中 AI／人格這群就有 9 個，而且用了**三種前綴**：

| 前綴 | 指令 |
|---|---|
| `askai_` | `askai`、`askai_prompt_debug`、`askai_prompt_trace`、`askai_response_trace` |
| `ai_` | `ai_diary` |
| `personality_` | `personality_extract`、`personality_extract_status` |
| `persona_` | `persona_agent_test` |
| （無） | `forget_tag` |

同一個領域三種叫法，指令列表已經找不到東西。

### Phase 1：收斂成 subcommand group（低風險，可先做）

Discord 原生支援兩層子指令，一組最多 25 個 —— 9 個指令會收成選單裡的**一個**項目：

```
/persona extract          （原 personality_extract）
/persona status           （原 personality_extract_status）
/persona test             （原 persona_agent_test）
/persona forget_tag       （原 forget_tag）
/persona diary            （原 ai_diary）
/persona trace prompt|response   （原 askai_prompt_trace / askai_response_trace）
```

`/askai` **保持獨立** —— 使用者天天用，藏進子指令反而難找。

**時機**：M4 排程上線時會再加指令（樣本清單維護、手動觸發），**一起改比較划算**，不要現在改一次、M4 再改一次。

### Phase 2：管理面板（沿用既有 panel 機制）

專案已有 `intro_panel` / `community_panel` / rollcall 的 `_try_refresh_admin_panel` —— 常駐訊息 + 按鈕，狀態變動時刷新。人格面板可直接沿用同一套：

- 上次萃取時間 / 成功筆數 / 失敗清單
- 按鈕：立即萃取、跑 agent（選成員）、看最近一次 diff
- agent 執行中顯示進度（步數 / 已用 token）

**比子指令好在**：不用記指令名，而且**看得到狀態**。

### Phase 3：網頁 dashboard（真正的目標）

`notify_server.py` 已經是 bot 內的 aiohttp server（`/health`、`/notify/{source}`），加唯讀路由即可。

**資料源就是 M3 的兩張表**，所以這一階段**必須排在 M3 之後**：

| 頁面 | 資料源 |
|---|---|
| 人格版本歷史 / 長期漂移 | `persona_agent_versions` |
| 執行紀錄、失敗率、幻覺率趨勢 | `persona_agent_runs` |
| production vs agent 並排比對（M6 評測用） | 兩張表 + `auto_personality` |

**安全性**：只綁 host-only 介面或加 token，絕不開在對外網段 —— 內容是成員的完整發言證據。

### 順序建議

```
M3（建表）→ Phase 1（子指令，與 M4 一起改）→ Phase 2（面板）→ Phase 3（網頁）
```

Phase 3 的價值最高但依賴最多；Phase 1 隨時可做但要挑對時機（避免改兩次）。

</details>

## Discord Bot 管理入口與指令整理 TODO（改寫前原文，歸檔 2026-10-02，原 2026-03-31）

> 最早的待辦：`/panel admin` 入口、指令分層、子指令化；含 09-04 權限檢查五種寫法的盤點，以及做完又還原的經過。
>
> 關鍵字：/panel admin、test_commands dev-only、權限檢查五種寫法盤點、require_permission、9/04 已還原

<details>
<summary>展開原文（約 2,873 字）</summary>

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

### 目標 4：權限檢查收斂（**2026-09-04 盤點完成・改動已還原・暫緩**）

<!-- @meta
id: permission-consolidation
type: TODO
status: blocked
last_confirmed: 2026-09-04
-->

**暫緩原因**：使用者決定先專注 ComfyUI 串接，不想同時承擔這個改動的風險。實作過一次、
測試全綠（353），但**已 `git checkout` 全數還原**，本節保留盤點結果，重做時不必再查一遍。

**現況：同一件事有五種寫法**（23 個 slash 指令 + 21 個按鈕／選單 callback）

| 寫法 | 用在哪 | 問題 |
|---|---|---|
| `@app_commands.checks.has_permissions(administrator=True)` | 5 個指令 | 錯誤訊息是英文預設值 |
| `check_guild(interaction, owner_only=/admin_only=/required_role=)` | 函式體內，12 個指令 | 藏在第 4~6 行，盤點要逐一打開看 |
| `user_commands._check_guild_and_owner()` | 5 個 callback | **只透傳 `owner_only`**，`admin_only` / `required_role` 被丟掉 → 該檔永遠設不了管理員限制 |
| `management_commands._check_guild_and_owner()` | 8 個 callback | 同名但預設值相反（`owner_only=True`），兩個 cog 讀同一個名字得到不同行為 |
| `rollcall._check_admin()` | 8 個按鈕 | 自己重寫，**少了「在不在伺服器內」** → 私訊時 `interaction.user` 是 `User` 沒有 `guild_permissions`，會 `AttributeError` |

底層其實都通到 `utils/utils.py` 的 `check_guild()`；`check_role()` 是它的角色判斷零件，
另外被 `commands/forum_monitor.py` 獨立使用（吃 member 不吃 interaction，所以不能合併）。

**做過的方案（可直接重做）**
1. `check_guild` → 更名 `check_permission`（33 處）——原名只描述四件事裡的第一件
2. `utils/utils.py` 新增 `require_permission(owner=/admin=/role=)` 裝飾器 + `PermissionDenied`
   （`app_commands.CheckFailure` 子類）；`check_permission` 自己會回中文訊息，而
   `discord_bot.on_app_command_error` 會把非冷卻錯誤再回一句「執行命令時發生錯誤」，
   **不自訂例外就會連發兩則**
3. 17/23 指令改用裝飾器；三個薄包裝刪除，21 個 callback 改直呼 `check_permission`
   （callback 不是 app command，用不了裝飾器）
4. `test_commands` 6 個維持零檢查（見下）

**重做時已知的三個坑**
- `management_commands` 的 View 內是 `self.cog._check_guild_and_owner(...)`，跟其他寫法不同，
  整批取代會漏掉兩處
- `llm_commands` 的 `persona_agent_test` 是**入口出口各驗一次**（followup token 有 15 分鐘，
  期間權限可能被撤銷）——那是刻意的縱深防禦，不可以當成重複刪掉
- 裝飾器必須在 `@app_commands.command` 之下才會被註冊成 check

**尚未解決（與本次收斂無關，但一起盤到）**
- ⚠️ `/anonymous` **零權限檢查**：任何人可叫機器人匿名發訊息到他看得到的任何頻道。
  `test_commands` 另外 5 個（`echo` / `list_forum_posts` / `ping` / `hello_world` /
  `multi_select_demo`）同樣零檢查。使用者 2026-09-04 決定「沒有特別要求就先不用」動。
- owner 語意不一致：`check_role` 中 OWNER_ID **自動通過**，`check_guild(admin_only=True)`
  中**不會**——同一個 owner 走不同路徑結果不同
- `config.json` 的 `role_mapping.Moderator` 是空陣列。`check_role` 對未設定的角色 fail-closed，
  所以哪天有指令寫 `required_role="Moderator"`，除 owner 外全數被擋，而訊息會說「僅限具有
  Moderator 角色的使用者使用」——看起來像權限不足，實際是設定沒填

**待決：AST 守衛**
提案是在 `test_shared_conventions.py` 加一條「每個 `@app_commands.command` 都必須有
`@require_permission`」，白名單用**函式層級**（`檔名.函式名`）而非整檔豁免，新增指令忘記加就紅。
但**它跑在容器啟動 gate 裡，誤判會讓 bot 起不來**，而本專案的取捨一貫是「寧可漏判不要誤判」。
風險未評估完（指令宣告形式有幾種、AST 會不會漏、改名會怎樣），**先不加**。

</details>
