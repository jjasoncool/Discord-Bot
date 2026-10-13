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

最後盤點紀錄（只保留近期；過往詳見 `TODO-completed.md` 各歸檔 entry）：
- 2026-10-13 11:xx～12:xx（M2 收尾＋交接檔歸檔，**未動 code**；之前 09:0x～11:2x 的 M2a `63be5a4`、字典 `65354a9`／`60c4744`、交接檔 `732eb9d`、tag `checkpoint-20261013-m2a`，11:20 使用者重啟 discord-bot 與 search-mcp 後 gate 1,426 全過、上線正常）：使用者質疑 M2b（`llm_service` 搬進 `llm/`）與 09-29 定案相反 → 退回（還原 19 檔）、M2c 取消；分層改成寫到子資料夾的五層，守衛 `test/test_layering.py`（M2d，1,432 項全過、6 個突變全紅，併進 M3 的 commit）。使用者「整理 AI_HANDOFF_AND_TODO.md、已完成的打包到 TODO-completed.md，然後繼續做 M3」→ 本次歸檔：巴哈編輯限速整塊、Telegram 過濾 285 行濃縮成現況＋定案摘要＋待辦、交易改版 150 行濃縮、Persona M7 的 PA／PR 討論、插話 AM-Q1／Q4～Q8 與 RB、/askai 接線的實作與審查（情報搜尋待做 7）、架構審視 M1／M2 過程、9/30～10/09 盤點紀錄；順手核對（唯讀）：週期提醒 10/7 04:00 矩陣提醒已發（log `matrix:2026-10-07:reset`）、⑤ 精簡版 10-02～10-13 連續 12 晚 failed=0（PR-Q2 刪 ③ 的門檻已達到，等使用者）、交易與商品 10-04～05 的修改都已 commit（至 `5809120`）、13 個 commit 未推送。接著做 M3：第 1 步（守衛「技術層與服務層不可 import discord」、`sticker_cache` 與 `context_retriever` 改掉 discord import、10 個突變全紅、完整 1,437 全過）做完等使用者看；第 2 步搬不搬 `llm/ambient`、`llm/storage` 先問（建議不搬，見架構審視區塊）。
- 2026-10-12（文件整理與唯讀查證，**未動 code**）：①使用者要圖解頁「改成從 askai RAG 串接做了哪些事、技術解釋、改善了什麼」→ 同一個網址改成整個串接的紀錄（十段：改善了什麼、現在怎麼跑、做了哪些事、搜尋、工具輪、快取、快了多少、排隊、文章對照、面試複習）。②使用者問「有沒有排隊機制」（朋友 10-08 建議改用 MQ）→ 對著程式確認有，而且不只一層：/askai 的 `ASKAI_QUEUE`＋單一工作者（先進先出）、顯示卡閘門 `gpu_exclusive`（行程內鎖＋跨容器鎖檔）、Telegram 轉發自己的佇列、Lemonade `--parallel 1`。**結論（建議，使用者未表態）**：現在不需要外部 MQ；朋友說對的是「加顯示卡不會變快」（工作者一位、閘門一次放一個、後端一個處理槽，且主模型一張 16 GB 的卡放不下），要加快先改這三處或做 `--parallel` 實驗，多行程／多台機器或工作要撐過重啟時才換 MQ。已知弱點：佇列在記憶體（重啟就沒了）、閘門每次模型呼叫拿一次、跨容器鎖檔不是嚴格先到先得、沒有優先順序。③使用者要對照 Ilya Rice 的冠軍 RAG 文章 → 差別與面試題寫進圖解頁第 9、10 段與 `doc/interview/` 準備檔第 2.6、9、10 節。另外 10-11 使用者同意後刪了 `doc/interview/` 的兩個舊版準備檔。④使用者問「評估需要改善嗎」→ 建議檢索評估不用再動、面試前只補 Agent 評估一個實驗 → **使用者「好 你幫我作」→ 07:45～09:18 跑完（未 commit）：42 題全部有查、閒聊 6 題都沒亂查；模型自己寫的查詢 Hit@5 71%（外部 agent 81%，差距不顯著），算上換字再查 79%；回答初判對 31／42；沒有自己編的連結。過程中第 42 題的一次回答因「逾時後自動重試」佔了顯示卡 15 分鐘，Claude 中止評估行程後接著跑完——逾時重試與回答沒有長度上限是線上 /askai 也有的問題，待使用者決定。數字、原因分析、未定案三題（放寬輪數、工具說明、逾時重試）都在搜尋區塊待做第 9 項**；⑤使用者「搬」→ 兩支評估程式搬進 `services/search/eval/`（和考卷、報告同一個資料夾，指令改成 `python -m services.search.eval.evaluate`；執行中的行程沒人 import，不用重啟；完整 1,404 項全過）；⑫使用者「其他的問題都要修正，滾動修正、commit 前先停讓我看」→ 計畫 M1～M10 與 Q1～Q5 寫在 `architecture-review-2026-10` 區塊，等回覆；`/anonymous`、test_commands 依使用者跳過。面試主檔加第 2.10 節「自己認的架構弱點」。⑪使用者「認真從嚴格的角度審視目前專案的架構」→ 靜態掃描＋讀模組說明，11 項發現、優先順序、限制寫成新區塊 `architecture-review-2026-10`（全部未定案、沒動 code）。⑨字典：使用者同意留在版控、每次 commit 時另做 `chore(settings)`（AM-Q8，`248565e`、`53c14b6`）。⑩使用者問「現在如果要面試，值得提的功能和實作方法都寫清楚了嗎」→ 盤點後補 `doc/interview/` 主檔（不進 git）：功能地圖、Persona agent 完整版、看圖的原因、AI 插話的閘門、記憶四層、訊息傳遞、故事 15／16、五題追問；圖解頁加第 12 段。內容都是從各模組的說明與設定值整理的，沒有動程式。⑧使用者「commit」→ 照先後拆成 `a918ff4` refactor(search)（評估程式搬進 `eval/`）、`f9364c8` feat(search)（Agent 評估、測試、三份報告）、本 docs；前兩個各自把暫存區的版本疊到容器 `/tmp` 的副本跑完整測試全過（1,383、1,404 項），都未推送。沒帶：bot 自己寫的表情與貼圖字典、`it_comfyui_image.py`。⑦`.gitignore` 照使用者改好的內容 commit（`f48605a`，未推送）；**查證：到 `0a809a6` 為止都已推送到 GitLab**（commit 前本機與 `dcbot/master` 一致），下面各則寫的「未推送」是當時的狀態，現況摘要與搜尋區塊的字樣已改。使用者問能不能把歷史裡舊版 `.gitignore` 也蓋掉 → 說明要改寫 26 個 commit 並強制推送、同樣的說明還寫在 `questions.json` 等檔，建議不做，使用者「好」。⑥使用者「已完成就該搬到 completed」→ 第 9 項已完成的部分（設計、執行經過、事故時間線、搬家）歸檔到 `TODO-completed.md`，交接檔只留結果、限制、未定案，歸檔裡的舊路徑也一起改；④的原建議內容：42 題加幾題閒聊，用正式模型跑完整工具輪，記「該查的有沒有查、模型自己寫的查詢 Hit@5／MRR（和 81% 並排）、抽 10 題人工看回答與引用連結」；只加評估腳本、不動正式程式。擴到 100 題、LLM 自動評分、聊天紀錄的考卷都排在面試之後。
- 2026-10-11 08:xx（文件同步，**未動 code**）：使用者問交付文件「是不是太舊了」→ Claude Docs 交付文件已更新成現況（總覽、架構圖的工具輪、設計決定、端到端數字、開關表、「留給你決定的事」重排成還沒決定／已定案、面試概念、優化表）。快取圖解頁（使用者私人頁面）補上現在的架構、前後比較、四題實測、線上第一題的時間分解、面試名詞表。`doc/interview/` 的準備檔故事 9 補上結局。**還沒決定的事（選項＋建議）現在以交付文件「留給你決定的事」為準**：openmeteo 加 `timeout: 4.0`（建議加）、台股類型（有人常問再做）、關鍵字模式要不要刪（觀察一週後刪）、新聞一週限制（先留）、輪數與全文長度（累積一週再調）、要不要縮短回答時的思考（先用考卷確認品質）、推 GitHub＋英文 README（面試前推）、備份分支（推送後刪）、爬蟲 `updated_at`（有需要再議）。
- 2026-10-11 04:3x（拿掉 /askai 的決策輪，**已 commit・未推送**；06:43 使用者重啟後已上線）：使用者「你幫我改」。工具輪每一輪都照原本的思考設定、帶同一份工具清單，不查的題目只呼叫模型一次；`decide_max_tokens`、`chat_with_tools(max_tokens=)` 一起拿掉。原因與證據見 `llm-inference-kv` 待做 4。完整 1,383 項全過、5 個突變全紅。06:35 persona agent 批次結束後使用者重啟；06:46 跑 `it_askai_intel` 四題：快取接上、閒聊沒亂查（數字見 `llm-inference-kv` 待做 4）。線上整題秒數待真實使用後補。
- 2026-10-11（合併繞路的 commit，**未推送**）：使用者問「有沒有改了 A 最後又修 B 的」→ 列出 6 組 → 使用者「合併」。從串接 MCP 起，把「先改 A、後來又修」併回原本的 commit；審查找到什麼、怎麼修，仍記在各區塊。**新編號（舊→新）**：`10a57ce` 工具輪（原 c68782a＋71c1803）→ `a107a66` 有篩選時走小索引（原 dd5795b）→ `8010ee0` MCP 客戶端＋/askai 接線（原 4cbba04＋7b2f582＋e4b4d14：從一開始就是每次呼叫短連線、情報規則獨立檔）→ `378c59b`／`9a9e863`／`c004b2c`／`a102763` 內容不變（原 32c7987／a50cd8e／3a48f20／b506880）→ `3fef43e` 被擋引擎暫避（原 582aa18＋09cf190 的被擋判斷、殘缺結果不快取）→ `41878bb` 直接答案（原 f05a3c4＋09cf190 的答案、天氣、外掛部分；不含維基）→ `96f92a3` 網路搜尋工具（原 661014d＋405c657＋其餘修正：從一開始就是模型選 kind）→ 本 docs（原 4 個 docs commit）。**驗證**：新的 MCP 客戶端 commit 與內容不變的 4 個 commit，樹和原 commit 一字不差；最後的程式樹和合併前一字不差（只差交接檔的編號）；5 個全新的中間版本在容器快照跑完整測試全過（1,305／1,305／1,344／1,356／1,364 項）。只用暫存索引組新 commit，工作目錄沒切換過（bot 即時掛載 src/）。改寫前的歷史留在本機分支 `backup/before-mcp-squash`（沒問題就可刪）；`99afecb`／`8ba0eb0`／`a14b9ed`／`826b994`／`c677a01`／`b59e392` 與更早的沒動。交接檔裡的舊編號已全部換成新的。

---

## 本檔維護規則（強制）

<!-- @meta
id: collaboration-rules
type: CONTRACT
status: confirmed
last_confirmed: 2026-09-29
-->

> **每次工作都要遵守的規則**，2026-09-29 起搬到 repo 根目錄的 `AGENTS.md`（所有 session、子代理、雲端都會自動載入）。原本這裡的段落對應如下：
> - 「使用者指定的討論流程」→ `AGENTS.md`「與使用者溝通」
> - 「禁止未經確認刪除/覆寫使用者資料檔（高嚴重性）」→ `AGENTS.md` 同名段落（四條照原文，例子更新為現有檔案）
> - 「注意事項」（Docker 限制、碼風）→ `AGENTS.md`「資料與環境（硬規則）」「程式碼」
> - 「共用元件索引」→ `AGENTS.md`「共用元件」
>
> 這裡只留維護本檔的規則。

### 文件閉環

每一輪原則上遵循：`讀取需要區塊 -> 沿用共識 -> 討論/執行 -> 回寫 -> 下輪再讀`

- 不要求每輪都全文重讀；優先讀與當前任務直接相關的區塊，需要交叉確認依賴、主線變更或資訊不足時才擴大範圍。
- 本輪有實作異動、共識更新、**待決問題新增或變動**（題目、選項、建議）、TODO 狀態變更，或使用者明確要求時，就要回寫本檔。討論與 grill 的每一輪都算。

### TODO 更新規則

1. 完成項目要打勾。
2. 完成且無未完成關聯時，應自待辦移除。
3. 若仍有依賴未完成項目，保留並註記依賴。
4. 若主線已切換，必須同步更新：
   - 現況摘要
   - 管理級總覽
   - 原主線區塊 status
   - 必要時將舊主線移入 `TODO-completed.md`

---

## 指令整理與管理入口（規劃，未動工）

<!-- @meta
id: command-consolidation-dashboard
type: DECISION
status: draft
last_confirmed: 2026-10-02
depends_on: persona-extraction-agent
affects: commands/, notify_server
-->

> 2026-10-02 由「指令收斂與管理 Dashboard」（2026-08-20）與「Discord Bot 管理入口與指令整理 TODO」（2026-03-31）合併，兩段原文已歸檔到 `TODO-completed.md`。

**現況（2026-10-02 盤點）**：21 個斜線指令＋2 個前綴指令。原本記的 `askai_prompt_debug`／`askai_prompt_trace`／`askai_response_trace` 已不存在；PR-Q4 會在刪 ③ 時再刪 `personality_extract`、`personality_extract_status`。

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
- [ ] AI／人格這群收成一個 `/persona` 子指令群組：PR-Q4 刪掉兩個萃取指令後剩 `persona_agent_test` → `/persona test`、`forget_tag` → `/persona forget_tag`、`ai_diary` → `/persona diary`。`/askai` **保持獨立**（天天用，藏進子指令反而難找）
- [ ] 文章類提子指令設計稿：`/article start|stop|status|test`
- **時機**：PR-Q4 刪 ③ 的兩個指令時一起改，避免改兩次（原本寫的「M4 排程上線時一起改」已過時）；與「程式結構整理」的 P2（拆 `llm_commands.py`、`user_commands.py`）一起考慮

### 第二步：管理入口與面板

- [ ] 建立 `/panel admin` 空殼，把 `/article_manager` 掛進主控台（保留舊命令）
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

<!-- @meta
id: permission-consolidation
type: TODO
status: blocked
last_confirmed: 2026-10-02
-->

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
---

## 現況摘要

> 本區只放指標與錨點。詳細內容請跳到對應區塊。
> 若某主題不再是當前主線，應從此區移除或降級，不應永久停留在現況摘要。

| 主軸 | 狀態 | 進度 | 詳見 |
|---|---|---:|---|
| Discord Bot / AI 對話能力 | 已有可用基礎能力；架構總覽停在 Ollama 時代，待重寫 | 80% | [專案架構](#專案-ai-架構總覽已過時待重寫) |
| Context / Prompt 優化 | 主要重構都已上線；剩 asker roles、/askai 指定 thread、/remember 等小待辦 | 97% | [Context 優化](#context--prompt-優化專區) |
| AI 偶爾插話 / 閒聊（功能二） | **已上線**（含 2026-08-09 自然插話重構）；10-02 看得懂貼圖、X 貼文、別的伺服器的表情（`673a965`）、AI 看圖補表情／貼圖字典（`cd0baf7`）、10-07 被罵的應對（`0f71b6d`）都已上線並 commit；待決 AM-Q2（放寬 style_refs 門檻）、AM-Q3（接話算正向）、AM-Q6h（偏掉的描述）、RB-Q9（道歉消氣）、AL-Q1～Q5（自主學習，暫停）；待做 C-4 整併／淡忘、觀測面板、鉤子權重迴歸 | 85% | [AI 偶爾插話](#ai-偶爾插話--閒聊功能二已上線c-4-待做) |
| Persona Agent M7（精簡版發布） | **已上線**；10-01 隱私歸因與名字對照上線、10-02 手動修正四條舊錯誤；⑤ 10-02～10-13 連續 12 晚 failed=0，**PR-Q2 刪 ③ 的門檻已達到，等使用者決定**（PR-Q3／Q4 隨之生效） | 90% | [Persona Agent M7](#persona-agent-m7精簡版發布2026-09-28-已上線精簡版連續-12-晚穩定待刪備援萃取) |
| ComfyUI 產圖 + GPU 資源仲裁 | **規劃定案（2026-09-02）**；租約鎖與卸載 helper 已完成（`e13343d`），鎖有漏洞待修；落地細節討論中 | 25% | [ComfyUI 產圖](#comfyui-產圖--gpu-資源仲裁2026-09-02-規劃定案未開工) |
| AI 私聊頻道 + 三層記憶（功能一·姊妹案） | 規劃完成（含道德守門）；人設 prompt 已就位；**本輪暫放旁邊** | 10% | [AI 私聊頻道](#ai-私聊頻道--三層記憶機制規劃中) |
| 使用者指令記憶 (/remember) | 規劃中（與 AI 私聊頻道互補） | 5% | [/remember 規劃](#使用者指令記憶-remember-未來工作) |
| Reaction 統計 / 社群互動玩法 | 資料收集已完成（`raw_message_store`）；玩法、/askai 整合、人格加權都還沒做 | 15% | [Reaction 統計](#reaction-統計與社群互動玩法規劃資料收集已完成) |
| 點歌機器人（Music Bot） | 已上線運作 | 85% | [點歌機器人](#點歌機器人專區) |
| Telegram relay 可靠性 | 補掃、媒體防雷、相簿漏圖修正都已上線並驗證（9/29 起合併與補圖符合設計） | 98% | [Telegram 補掃](#telegram-漏收補掃與相簿漏圖已上線) |
| 程式結構整理 | **主要整理已完成並上線**（`llm/` 與 `services/` 分群、點名去除反向依賴）；剩 P2 拆檔（未決）、P3 `discord_bot.py` 瘦身（暫停）、N3（延後）、命名慣例未寫進 AGENTS.md | 90% | [程式結構整理](#程式結構整理2026-09-29-起主要整理已完成剩-p2p3n3) |
| 架構審視與滾動修正（/goal） | 11 項發現；M1 背景任務 supervisor、M2a 熱讀檔器併一份 **已上線（10-13 11:20 重啟）**；M2b 退回、M2c 取消；M2d 分層守衛 `test_layering.py` 完成（併 M3 commit）；**M3 第 1 步（守衛「技術層與服務層不可 import discord」＋兩處修正）等看，第 2 步搬不搬 `llm/ambient`、`llm/storage` 待使用者（建議不搬）**；之後 M4～M10；結束時把「待重新決定的清單」整份給使用者 | 20% | [架構審視](#架構審視與滾動修正2026-10-12-起m1m2a-已上線m2d-守衛完成m3-進行中) |
| 情報搜尋（MCP）：公告、FB、PTT、巴哈 | **P1～P4 已 commit（10-08，已推送）**：全文索引＋向量（RRF）＋reranker、42 題評估（原句 Hit@5 21%→67%、關鍵字 60%→81%）；**10-12 Agent 評估（已 commit，未推送）**：正式模型自己寫的查詢 71%、算上換字再查 79%、回答初判 31／42，三題未定案見區塊待做第 9 項；**R12 已上線並 commit（10-08，已推送）**：常駐服務 `search-mcp`、索引移到 `search_data/`、每日補向量、重排讀原句並已開啟；**延遲改進與 /askai 接線已 commit（10-09，已推送、已上線）**：背景同步、冷快取讀取量 52 MB → 4.5 MB、/askai 由模型決定查不查；待決定：插話被 @ 時要不要也查（見區塊待做第 7 項） | 95% | [情報搜尋（MCP）](#情報搜尋mcp官網公告官方-fbptt巴哈p1p4-已完成常駐服務已上線) |
| LLM 推論：KV cache 與 GPU | 查證完成、`llm_usage` 已上線；待調 prompt 順序、`--parallel` 實驗 | 30% | [LLM 推論](#llm-推論kv-cacheprompt-快取與-gpu2026-10-08-查證) |
| Telegram 訊息 LLM 過濾 + 隔離區 | **2026-10-07 已上線**（模型看文字＋圖判有沒有遊戲資訊、隔離 thread、放回面板、舊訊息搬移腳本），10-08 排隊到 30 分鐘＋`needs_recheck` 補判上線，全部已 commit；開關 `telegram_filter_mode=on`；剩轉發端那批（有文字的單則先送文字後補到的圖送不出去）與幾個小項 | 90% | [Telegram 過濾](#telegram-訊息-llm-過濾--隔離區2026-10-07-已上線10-08-補判上線) |
| 週期活動提醒（深塔海墟矩陣） | **已上線**：9/29 20:00 矩陣結束前提醒、10/7 04:00 矩陣開放靜音提醒都已實發（log 核對）、手機通知確認正常；待自介面板置底驗證 | 97% | [週期活動提醒](#週期活動提醒深塔海墟矩陣已上線) |
| scraper 抓網頁機制＋IT 就地補內文 | **已上線**：IT 補內文已驗證（10/01 補 11 則）；HKEPC 10/01 03:46 後 0 次 403；巴哈每輪仍約 80 分鐘待查；SC-Q6 觀察 | 95% | [scraper 抓網頁機制](#scraper-抓網頁機制檢查2026-10-01-已上線) |
| 跨來源整合（Article/FB/PTT/TG） | 發文已共用 `post_to_channel`、Telegram 自成分層；讀資料與事件模型整合沒做（動手前先照「沿用現有架構」重新評估） | 40% | [跨來源整合](#跨來源整合專區規劃發文已共用) |
| 指令整理與管理入口 | 規劃：test 指令隔離、`/persona` 子指令（與 PR-Q4 一起）、管理面板、網頁 dashboard；權限檢查收斂暫緩 | 10% | [指令整理](#指令整理與管理入口規劃未動工) |
| 交易功能改版（自發貼文接單、販賣者上架商品） | **已上線並 commit**（10-03 A＋B `84a8ba3`、商品上架至 `46e84a6`；10-04～05 實測回饋 13 個 commit 至 `5809120`）；流程見根目錄 `TRADE_FLOW.md`；剩措辭 A／B／D 幾句、TR-Q33 上架說明附圖（等使用者截圖）、舊留底含對話要不要改、價格 0 的意思；之後：沒人收尾的交易（TR-Q5）、四份舊迴圈搬 `run_due_loop`、刪 Legacy view、價目表併入商品目錄 | 90% | [交易功能改版](#交易功能改版與商品上架2026-10-0305-已上線並-commit剩措辭與價目表待決) |

> 已完成 / 過往工作（Bahamut scraper + 反爬基礎設施、幽靈點名核心 + DM、社群 ID 查詢 Phase 0、Telegram Relay、Music Bot 完整實作等）詳見 `TODO-completed.md`。
>
> **2026-08-18 歸檔**：活動公告自動建活動（17 筆已建立）、Telegram 自訂表情 → Discord App Emoji（10 個已上傳）、Telegram 多頻道來源 + 轉發去重（Gamedataleak 205 筆），三者皆已上線運作，連同 2026-06-25 ~ 2026-07-25 的盤點紀錄一併移入 `TODO-completed.md`。
>
> **2026-10-02 歸檔**：程式結構整理的討論紀錄、IT 新聞只帶摘要、scraper 指紋查證、週期提醒／新成員歡迎／活動自動發布／Telegram 補掃的實作紀錄、Ollama 時代的架構總覽、Context 優化與 AI 插話（含自然插話重構）的已完成部分、共用元件索引、9/29 以前的盤點紀錄，原文移到 `TODO-completed.md`；交接文件只留仍有效的待辦、待決與坑。
>
> **2026-10-13 歸檔**：巴哈轉發編輯限速（整塊）、Telegram LLM 過濾的討論與上線紀錄、交易改版與商品上架的定案過程、Persona M7 隱私歸因與名字對照的實作、AI 插話 10 月的改進與被罵的應對、/askai 接情報搜尋與網路搜尋工具化的實作與審查、架構審視 M1／M2 的過程、9/30～10/09 的盤點紀錄，原文移到 `TODO-completed.md`；各區塊只留現況、定案摘要、待決與坑。

---

## 交易功能改版與商品上架（2026-10-03～05 已上線並 commit；剩措辭與價目表待決）

<!-- @meta
id: trade-revamp
type: TODO
status: confirmed
last_confirmed: 2026-10-13
depends_on: TRADE_FLOW.md（現況）
affects: commands/trade_commands.py、commands/forum_monitor.py、自由市場、購物車、封存頻道、新的商品論壇
-->

**需求（使用者 2026-10-03）**：① 自由市場裡使用者自己發的貼文，被供應方按表情後也能走交易流程；② 供應方（Trader，伺服器上叫觀星者）在新的論壇頻道上架商品（頻道綁 `config.json`），一個商品多個品項、分預購與立即購買，購買共用自由市場的開單，預購截止時在交易對話 @ 雙方提醒。

**現況（2026-10-05 起全部已上線並 commit）**：10-03 A＋B 交易模組與自發貼文接單（`84a8ba3`）、商品上架（至 `46e84a6`）；10-04～05 實測回饋 13 個 commit（至 `5809120`：措辭、附圖、停用選單、總計按鈕、下架警語、`TradeThreadLog`、私聊不進留底）。程式碼清單、流程圖、資料存在哪、名詞表（品項＝`Variant`）、已知缺口見根目錄 `TRADE_FLOW.md`。TR-Q1～Q45 每一題的選項、理由與實測回饋原文已歸檔到 `TODO-completed.md`「交易功能改版與商品上架：定案、實作與實測回饋（歸檔 2026-10-13，原 2026-10-03～05）」。

**已定案（摘要）**
- 架構：做 A（「誰是需求方」只寫一處）＋B（開單、領收、取消、封存都經 `services/community/trade_service.TradeService`，按鈕由指令層交進來；讀交易對話一律經 `TradeService.read` → `TradeThreadLog`）；Discord 當紀錄、不加資料庫（TR-Q1）：身分放按鈕 custom_id、狀態看對話鎖定與標題前綴【交易中】【已完成】【已取消】【已結束】。定時排程抽成 `utils.due_loop.run_due_loop`（TR-Q9；`wake` 讓截止時間改了提早醒）。
- 角色與流程：需求方（貼文者）／供應方（按表情的 Trader）；所有自發貼文都能接單、只有對貼文本身按的表情算（TR-Q2）；每位供應方各開一個私人對話；供應方按「通知需求方領收」，需求方按「已領收」或「還沒領收」（暫停倒數並 @ 供應方；到期前 6 小時提醒一次，TR-Q18）；只有供應方能取消（TR-Q4）；一位完成後同篇其他對話結束並刪需求貼文（TR-Q8）；「請群主協助」把伺服器擁有者拉進對話（TR-Q19）；結束時立刻鎖定封存並私訊雙方 embed（TR-Q29）；名字一律伺服器暱稱（快取→API）。
- 商品上架：按鈕跳 modal、bot 代發貼文（TR-Q6）；入口在置頂「上架說明」貼文、不加指令（TR-Q13）；同一系列放同一篇，一篇多個品項、批次新增一行一項「名稱｜價格｜數量｜預購截止」、時間寫年份（TR-Q14／Q22）；價格只填數字、幣別設一次、金額千分位（TR-Q23／Q26）；下單就預留、取消還回（TR-Q16）；填完數量先看明細再「確認下單」（TR-Q20）；只放一顆「⚙️ 管理商品（上架者）」灰色按鈕、非上架者按了被拒（TR-Q21／Q24）；一篇可賣多人、每位買家一個對話、加購沿用，加購時作廢原領收通知（TR-Q12／Q25）；預購截止提醒從商品側找，靠論壇標籤「預購中」（TR-Q17）；編輯時數量是「剩餘數量」（TR-Q27）；完成時在封存頻道另發「【市集】…」留底（TR-Q28），10-05 起留底只留每筆下單與交易對話連結、不附對話內容（TR-Q44＝B；私人對話本身就是備份，TR-Q45＝A；封存頻道維持所有觀星者看得到）；不能買的品項加刪除線＋灰底標籤、全部不能買時停用選單（TR-Q38）；下架＝停止接單、不可恢復、保留紀錄，暫停販售改剩餘 0（TR-Q39）；總計寫在訂單按鈕上（TR-Q40）；上架說明附橫幅圖 `src/static/ListingGuidelines.jpg`（換圖＝換檔＋重綁）。
- 措辭（TR-Q34 原則，使用者提出）：群友看到的訊息只講發生了什麼、下一步，不講 thread／鎖定／封存／預留這些做法；thread 叫「交易對話」；只有管理員看得到的訊息保留技術原因。已照改：thread→對話、開不了交易、幣別說明、封存結果只在要人處理時才說（TR-Q37）、`/select_item` 找不到論壇的那句。日期輸入共用 `utils.user_dates`（TR-Q41／Q42：全形、`/` `-` `.` 都收；預購只寫日期＝23:59；選立即購買卻填截止就擋）。
- 價目表（TR-Q7＝C）：設計上合併、分兩階段——商品目錄按「價目表也是一種商品」設計；上架穩定後再把 `item_prices.json` 搬進去（先備份、取得同意）並停用 `/set_item_prices`、`/list_item_price`。

**仍待決**
- TR-Q35／Q36 剩下的句子：A（1～6 交易流程）、B（7～10 市集）、D（18～21）待使用者挑要改哪些；開單訊息要不要加一句給需求方（「供應方交付並按通知後，這裡會出現『已領收』按鈕」）併在 TR-Q35。
- TR-Q33 上架說明要不要附操作截圖（建議 A：介面穩定後由使用者在正式論壇截圖，放進 repo）。
- 10-03～10-05 已發出去的市集留底仍含完整對話，要不要改舊貼文（動資料，要先同意）。
- 價格 0 是否代表不賣（TR-Q7 遷移前要使用者說明）。
- 可考慮的守衛：給人看的文字裡提到的斜線指令都要存在（全專案掃描，要先排除註解、網址路徑）。

**之後的待辦**
- 沒人收尾的交易（TR-Q5），和預購到期提醒一起用 `run_due_loop` 做。
- 週期提醒、點名、人格萃取、日記四份舊迴圈搬到 `run_due_loop`（搬一份就從守衛例外拿掉一份；人格萃取和日記要避開維護時段重啟）。
- 舊交易 thread 都結束後刪 `LegacyTransactionView` 與 `legacy_ref_from_text`。
- `item_prices.json` 三處各自讀寫 → 單一存取點（架構審視 M5）後併入商品目錄。
- `/select_item` 流程沒有測試。

---

## 程式結構整理（2026-09-29 起；主要整理已完成，剩 P2／P3／N3）

<!-- @meta
id: code-structure-reorg
type: TODO
status: draft
last_confirmed: 2026-10-02
affects: src/ 全部資料夾、mcp-search-tools（R2-Q5 程式放哪）、test_shared_conventions、settings/logging.json
-->

> 已完成並上線：`llm/` 依角色分子資料夾（`97d7595`）、點名去除反向依賴（`9b0b916`）、`services/` 分 relay／events／community（`5e10611`）、共用 StateDB 連線搬到 `state_db.py`（`2b31828`）、刪 FB／IT 輪詢死碼、資料檔路徑測試（`test_data_file_paths.py`）與 import 守衛（`test_import_resolution.py`）。各輪討論（L／N／P／R2／S）與新舊路徑對照已歸檔到 `TODO-completed.md`「程式結構整理：討論與實作紀錄（歸檔 2026-10-02，原 2026-09-29）」。

**還沒定案**
- **P2 一檔多功能，拆檔但留在同一個資料夾**：`commands/llm_commands.py` 拆成 /askai 與人格相關（萃取、agent 測試、日記）兩個檔；`management_commands.py` 拆出自介面板；`user_commands.py` 的 `/forget_tag` 併到人格指令、物價併到 `trade_commands.py`。cog class 名稱不變，`get_cog` 不受影響；`COMMAND_MODULES` 要加項。
- **P3 `discord_bot.py` 瘦身**：04:00 維護編排搬進 `llm/`、00:00 日記排程搬進 `llm/ambient/ambient_diary.py`、Telegram 組裝搬進 `telegram_relay_service`、公告／PTT 自動啟動搬回 `article_commands` 的 `cog_load`。碰到每晚的維護排程，要單獨排、先補測試。
- **P3 修正**：同意 `discord_bot.py` 太胖，但入口本來就該做入口的事；不另拆一個排程程式，入口仍由 `discord_bot.py` 管。我的理解（待確認）：`discord_bot.py` 保留「什麼時候跑什麼、步驟順序、啟動順序、事件接線」，每個步驟裡面的實作細節（例：04:00 第 ③ 步讀略過名單、把結果塞進 cog）搬到各自的模組，入口只剩一行呼叫。
- **P3 確認**：上面對 `discord_bot.py` 的理解對嗎？另外，cog 自己啟動的迴圈（週期提醒、點名、/askai 排隊）要不要也改由 `discord_bot.py` 登記？建議不要：那些是功能內部的計時器；由入口統一編排的只限跨功能的排程（04:00 維護、00:00 日記、轉發啟動）。
- **N3 延後**：`utils/utils.py` 拆成 `permissions.py`（`check_guild`／`check_role`）、`channel_config.py`（`ChannelConfig`＋頻道 getter）、`interaction.py`（安全回覆、分頁），約 18 個 import 點；`settings/channel_registry.py` 搬到 `utils/`（它是共用元件，照 AGENTS.md 應放 `utils/`），名稱不變；`user_commands`、`llm_commands`、`management_commands` 在 P2 拆檔時一起取新名。建議都做，但排在純改名之後。
- **N1 已定案（A：只改會誤導的＋正名表），但命名慣例還沒寫進 `AGENTS.md`**（10-02 盤點確認）。
- 可選、不急：轉發相關 7 個檔集中到 `services/` 底下一個子資料夾（會碰到 `state_db` 路徑地雷與 `notify_server` 的模組字串）；`settings/channel_registry.py` 是程式碼放在資料夾裡；`utils/utils.py` 裡各功能專屬的頻道 getter。

**仍有效的事實與坑**
- **`discord_bot.py` 876 行**：`on_ready` 約 320 行，塞了 04:00 維護（①～⑤ 全部編排，171～344 行）、00:00 日記排程、3 個 flush loop、公告／PTT 自動啟動（直接改 cog 內部屬性）、Telegram 物件組裝、echo 跟風、fixupx、活動墓碑、reaction 統計 hook。背景迴圈有的在 `on_ready` 啟動，有的在 `cog_load` 啟動，不一致。
- **搬檔最大的地雷**：`services/state_db.py` 用 `Path(__file__).parent/"sent_articles.db"` 找資料庫，**搬這個檔會悄悄開一個空的新 DB，導致大量重發**。其他依 `__file__` 找資料的：`base_monitor`、`rollcall_service`、`event_scheduler`（`../scraper/articles.db`）、`logger_config`、`music/ytdl`。約 20 處用相對工作目錄讀 `config.json`，約 15 處寫死 `/app/settings/prompts/*`。**資料檔跟程式碼混放**（`services/sent_articles.db`、`settings/*_runtime.json`），`.gitignore` 依路徑排除，搬了沒更新會把使用者資料 commit 進去。
- **沒有測試的功能**：點名、社群 ID 查詢、點歌、自介／印象、交易、關鍵字監看、PTT、巴哈、FB（只有 embed）、日記、人格萃取、記憶、聊天紀錄寫入、頻道綁定。**搬這些功能時沒有測試保護**。
- 子資料夾判準：「≥6 檔／有封裝邊界／可預期會長」滿足其一。**ComfyUI 另開 `src/imagegen/`，不塞進 `llm/`**，避免 `llm/` 變成「AI 相關雜物間」。
- 實測：`import llm` 在容器內約 1.5 秒、載入 1,747 個模組（`llm/__init__.py` 會預先載入 llama_index 等）；對照 `import services.base_monitor` 0.39 秒。MCP 殼放 `llm/` 會多這 1.5 秒啟動時間，每個 Claude Code session 只啟動一次，可以接受；太慢再把 `llm/__init__.py` 改成用到才載入。
- 已知但不處理（改動前就有、目前沒有這種寫法）：頂層出現 `alias.attr = …` 時，該別名後面的讀取不再檢查（刻意保守，避免誤判）；用 importlib 動態 import 或間接 import 指令層，AST 分層測試抓不到。
- **S6-2 改定案（使用者 2026-09-30）**：使用者認為 dockerfile 改成鎖版本沒必要（通常升到最新就好）→ **dockerfile 還原成原版**（只 `pip install -r requirements.txt`，每次重建都拿當下最新版）；**`constraints.txt` 留作紀錄**：內容與容器內 `pip freeze` 102 項逐一相同，檔頭改成「建置不讀這個檔」，用途是之後重建出問題時對照哪個套件變了，必要時用 `pip install --user -c constraints.txt -r requirements.txt` 暫時裝回；映像重建後就不代表現況，要更新請重新 `pip freeze`。`requirements.txt` 保留 `mcp>=2.2,<3` 與兩行註解路徑更新。接受的取捨：下次重建會拿到沒測過的新版，第一道防線是啟動 gate（測試不過 bot 起不來、舊容器照跑）。

---

## 情報搜尋（MCP）：官網公告、官方 FB、PTT、巴哈（P1～P4 已完成，常駐服務已上線）

<!-- @meta
id: mcp-search-tools
type: STATE
status: confirmed
last_confirmed: 2026-10-12
affects: services/search、llm/mcp_server.py、.mcp.json、docker-compose（search-mcp、gpu_lock）、search_data/、pgvector data_search_chunks、Lemonade（embedding、reranker）、/askai（llm/retrievers/intel、LLMService.generate_reply 的工具輪）、scraper/db/models.py（四個 updated_at 索引）
-->

> 2026-09-29～10-08 每一輪的討論與查證（R2～R12）原文在 `TODO-completed.md`「MCP／搜尋工具化：討論與實作紀錄」。本區只放現況、定案、數字與待辦；評估紀錄（原 `eval/RESULTS.md`）與用語（原根目錄 `CONTEXT.md`）也併在這裡。

**現況（2026-10-09）**
- 用途：讓 LLM 自己決定要不要查、查什麼；來源是官網公告、官方 FB、PTT、巴哈（Telegram 內鬼頻道、依 ID 查人不納入）。MCP server 給這台的 Claude Code 與 bot 共用；bot 當 MCP 客戶端（`llm.retrievers.intel`）連 search-mcp，不直接 import `services.search`（10-09 改定案，理由見待做第 7 項）。
- **/askai 已接上（10-09，已 commit、已推送、10-09 重啟後已上線）**：開關 `askai_intel_search_mode`（`switches.json` 已設 `on`）；架構、定案、實測、留給使用者的題目見待做第 7 項。交付文件（架構圖、設計決定、數字、上線步驟、面試概念、優化排序）：https://claude.ai/code/artifact/11a03b1e-558a-4ac5-8253-71c35e8b9d57
- 已 commit、已推送：`dd89c58` refactor（共用網址、RRF、同步 GPU 閘門、側行程 log）、`c842b9b` feat(search)、`9b4ec88` feat(llm)（逐筆 LLM 用量 log）。完整測試 1,248 項全過，新測試都做過突變驗證。
- **R12 已部署（10-08 18:50）、已 commit（`c96cc80`、`ca5b837`，已推送）**：MCP 是常駐的 compose 服務 `search-mcp`（HTTP，`127.0.0.1:8765`）、索引在 repo 根目錄 `search_data/`（舊位置已刪）、每天 03:00 補算新文章向量、重排讀原句。完整測試 1,263 項全過、19 個突變全抓到。
- 運作中：`settings/switches.json` 的 `search_vector_mode: on`、`search_rerank_mode: on`（10-08 使用者同意打開）。
- 索引：11.2 萬份文件（公告 543、FB 874、PTT 5.5k、巴哈 10.5 萬樓）；向量：2026 年起的 1.8 萬段（巴哈只做攻略、心得、情報、問題四類討論串）。

**架構**
- `llm/mcp_server.py`：MCP 協定層，只有 `search(query, sources?, since, until, limit, question?)` 與 `fetch(id, page)` 兩個工具；參數錯把原因原文回給模型（`ToolError`）。`--http` 是常駐模式（stateless Streamable HTTP、聽 0.0.0.0:8765、Host 白名單 `127.0.0.1`／`localhost`／`search-mcp`，別的 Host 回 421），並在背景開每日維護；不帶參數是 stdio（備用）。
- compose 服務 `search-mcp`：沿用 bot 的 build（兩邊引用同一個錨點 `x-main-build`，不改 Dockerfile）、`restart: always`、不跑啟動測試（discord-bot 已經跑同一份程式的）；只帶 `LLM_BASE_URL`、`LLM_TIMEOUT`、`PGVECTOR_*`、`LOG_LEVEL`、`TZ`、`LEMONADE_GPU_LOCK_PATH`（沒有 Discord token、Telegram 憑證）；掛 `./src`、`./logs`、`./search_data`、`./gpu_lock`；`ports: 127.0.0.1:8765:8765`＋`expose: 8765`。`.mcp.json` 改成 `{"type": "http", "url": "http://127.0.0.1:8765/mcp"}`。
- `services/search/background.py`（10-09 由 `nightly.py` 改名）：每 50 秒背景同步一次（失敗退避、同樣錯誤只完整記一次）；每天 03:00～04:00 之間做一次「同步索引＋補算向量」（`embed.embed_pending`，向量開關關著只同步）；04:00 之後才啟動不補做、等明天；同一天不重做、出錯也不在同一時段重試；排程走 `utils.due_loop.run_due_loop`，在自己的執行緒與 event loop 上跑。
- GPU 鎖檔跨容器：各容器的 `/tmp` 是分開的，所以 discord-bot 與 search-mcp 都掛 `./gpu_lock` 並設 `LEMONADE_GPU_LOCK_PATH=/gpu_lock/lemonade_gpu.lock`；單元測試由 `test/__init__.py` 強制換成暫存檔（不能 `setdefault`，容器的環境變數已經有值）。
- `services/search/`：`index.py`（索引同步、召回、排序、RRF 合併、重排、讀全文）、`sources.py`（來源登記表；加來源＝寫一個 `Source`）、`text.py`（HTML 轉文字、NFKC＋簡轉繁、兩字組切詞）、`chunking.py`、`vectors.py`（pgvector＋HNSW、問句向量）、`embed.py`（批次算向量）、`rerank.py`、`evaluate.py`；`background.py`（背景同步與每日維護）；`eval/`（`questions.json` 考卷、`keyword_queries.json`、`reports/*.json`、`private/` 證據句不進 git）。索引 `search_data/search_index.db`（repo 根目錄，只掛給 search-mcp 的 `/search_data`；SQLite＋WAL，不進 git，可刪掉重建約 3.5 分鐘；沒掛的容器用到會直接失敗，不會悄悄另建一份）。
- 設定 `sys_settings/search_settings.py`；開關 `settings/switches.json`；模型 `sys_settings/llm_runtime_config.json` 的 `embed_model`、`rerank_model` 與 `model_load_options`（reranker：`-sm none -mg 0 -ub 1024 -b 1024`）。
- 依賴單向：MCP 層 → 搜尋本體 → 共用元件（`services.source_urls`、`utils.rank_fusion`、`lemonade_gate.gpu_exclusive_sync`）。搜尋本體不 import discord 與 mcp；bot 程式沒有 import 搜尋。
- 搜尋流程：全詞（FTS5 trigram，每個長關鍵字整段出現）＋兩字組 BM25（FTS5 contentless，整句也能用）＋一個字的詞走 LIKE → 依「含幾個關鍵字 → 兩字組 BM25 名次 → 新舊」排 → 向量（餘弦距離 ≤ 0.35）與關鍵字名次 RRF（k=60）合併 →（開關開時）前 30 篇 reranker 重排（有 `question` 就讀原句；每篇挑哪一段仍看查詢字）→ 每種來源最多 5 筆、總共最多 20 筆。
- 同步：游標 (updated_at, 列 id)＋內容 hash（巴哈每天約兩萬列只是「最後看到時間」變了）；索引版本只升不降（舊行程遇到新索引丟 `IndexTooNew`，不會把它砍回舊版）；`articles.db` 一律 `mode=ro`。
- GPU：所有 embedding、rerank 都走 `gpu_exclusive_sync`，和 bot 排同一個隊；問句向量與重排最多等 10 秒（`query_gpu_wait_seconds`），等不到這次跳過那一步；批次一直等。向量或重排壞掉都退回關鍵字結果，搜尋本身不會失敗。

**用語**
- **來源**：官網公告、官方 FB（官方）；PTT、巴哈（玩家說法）。
- **文件**：搜尋結果與評分的單位，可以直接給人連結的一篇：公告一篇、FB 一則、PTT 一篇、**巴哈一個樓層**（不是整串，最大的串有 11,234 樓）。id：`article:<article_id>`、`fb:<fb_posts.id>`、`ptt:<article_id>`、`bahamut:<sn>`（`post_id#position` 有重複，不能當 id）。
- **段落**：文件切出來算向量的片段（約 500 字、重疊 80 字，每段帶標題）；命中任一段就算命中那份文件。
- **評估集（考卷）**、**正確答案**（讀了就能回答；一題可有好幾篇）、**只答一半**（預設不算對）。

**常用指令**（`docker exec search-mcp …`；`AGENTS.md` 的 Docker 例外允許 agent 直接執行。discord-bot 沒掛 `search_data/`，在那裡跑會失敗）
- `python -m services.search`：手動同步索引。
- `docker logs search-mcp`：啟動、每日維護的結果（也寫 `logs/mcp_server.log`）。
- `python -m services.search.embed [--dry-run] [--limit N] [--since YYYY-MM-DD]`：補算向量（增量、排 GPU 隊）。
- `python -m services.search.eval.evaluate --label 名稱 [--vector on|off] [--rerank on|off] [--split 全部|A|B] [--vector-weight W] [--max-distance X|inf] [--diagnose-vectors]`：報告寫到 `eval/reports/<時間>-<名稱>.json`。

**評估方法**
- 考卷 `eval/questions.json`：42 題（情報 30：公告、活動、兌換碼；攻略 12：配隊、倍率、聲骸各 4），使用者逐題確認過。正確答案直接查資料庫找，沒用受測的搜尋；證據句與標題是論壇原文，放 `eval/private/`（不進 git）。
- 原句模式＝群友原句直接搜（沒人幫忙改寫的最差情況）；關鍵字模式＝由沒看過答案的子 agent 改寫成關鍵字再搜（模擬 LLM 客戶端），存 `keyword_queries.json`。
- 指標：Hit@k（前 k 名有正確答案的題目比例）、MRR@10（第一篇正確答案名次倒數的平均，前 10 名外算 0）、Recall@10（前 10 名找回幾成正確答案）、nDCG@10（所有正確答案依名次打折加總，除以理想值）。排名看搜尋實際回傳的那一串（含來源上限）。
- 調參防過度擬合：考卷依分類交錯固定拆 A、B 兩半；事先定好規則，在 A 選設定、選定後才看 B；兩半方向一致才採用。

**評估結果**（數字以這裡為準，每次評估加一列；報告在 `eval/reports/`）

| 版本 | 改了什麼 | 模式 | Hit@1 | Hit@5 | Hit@10 | MRR@10 | Recall@10 | nDCG@10 | 情報 Hit@5 | 攻略 Hit@5 | 報告 |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| P1 | 三字組全文索引＋2 字詞 LIKE＋簡轉繁 | 原句 | 14% | 21% | 36% | 0.195 | — | — | 30% | 0% | `1203-P1-FTS5基準線` |
| P1 | 同上（事後補量，見下） | 關鍵字 | 33% | 60% | 62% | 0.439 | — | — | 70% | 33% | `1238-P1-補量` |
| P1.5 | 加兩字組索引做 BM25；只有一個字才走 LIKE | 原句 | 29% | 38% | 52% | 0.336 | — | — | 53% | 0% | `1236-P1.5-兩字組` |
| P1.5 | 同上 | 關鍵字 | 43% | 71% | 74% | 0.530 | — | — | 80% | 50% | `1236-P1.5-兩字組` |
| P3 | 加向量（2026 年起 1.8 萬段）與 RRF；門檻 0.35 | 原句 | 36% | 55% | 67% | 0.446 | 38% | 0.336 | 63% | 33% | `1554-P3-不重排-新指標` |
| P3 | 同上 | 關鍵字 | 45% | 74% | 79% | 0.559 | 55% | 0.476 | 77% | 67% | `1554-P3-不重排-新指標` |
| P4 | 合併後前 30 篇 reranker 重排 | 原句 | 48% | 67% | 71% | 0.555 | 46% | 0.433 | 73% | 50% | `1609-P4-重排前30篇` |
| P4 | 同上 | 關鍵字 | 31% | 74% | 76% | 0.483 | 46% | 0.389 | 77% | 67% | `1609-P4-重排前30篇` |
| P4 原句重排 | 重排改讀原句（`question`），挑段落仍看查詢字 | 原句 | 48% | 67% | 71% | 0.555 | 46% | 0.433 | 73% | 50% | `1705-P4-重排用原句` |
| P4 原句重排 | 同上 | 關鍵字 | 48% | 81% | 81% | 0.596 | 54% | 0.482 | 83% | 75% | `1705-P4-重排用原句` |
| 10-12 對照 | 程式沒變，同一份外部 agent 查詢在 10-12 的索引重跑 | 關鍵字 | 48% | 81% | 81% | 0.596 | 54% | 0.482 | 83% | 75% | `20261012-0918-對照-外部agent改寫` |
| 10-12 Agent 重放 | 查詢字換成**正式模型在 /askai 工具輪裡第一次 search 自己寫的**（同一把尺：前 20 筆、重排讀原句） | 關鍵字 | 40% | 71% | 76% | 0.533 | 49% | 0.429 | 73% | 67% | `20261012-0917-Agent-模型自己寫的查詢` |
| 10-12 Agent 實際 | 模型實際看到的結果（每次前 6 筆）：第一次 search／任一次 search 裡最好的 | 模型自己寫 | 38%／52% | 71%／79% | — | 0.515／0.628 | — | — | 73%／80% | 67%／75% | `20261012-0745-Agent評估-正式模型` |

（沒寫日期的報告檔名前面都是 `20261008-`；10-12 三列見待做第 9 項。P1、P1.5 當時還沒有 Recall／nDCG。P3 與 `1341-P3-門檻0.35` 的數字完全相同，後者是第一次跑的。）

- **P1 → P1.5**：兩字組讓原句 +17、關鍵字 +11 個百分點（搜尋端）；關鍵字改寫 +33～39 個百分點（客戶端，影響更大）。代價：原句模式平均 23 → 87 ms、索引 242 → 299 MB、整份重建 55 → 204 秒。「P1 關鍵字」是事後補量：在容器暫存區把程式還原成 P1 另建暫時索引，同一份程式量原句得到 21%／0.195，和當初的基準線完全一致。
- **P3 門檻怎麼選**：第一次挑候選門檻用了全部 42 題的距離分布（B 半參與了選擇，程式碼審查抓到），照規則重做——只用 A 半的分布，候選＝正確答案距離的中位數與第 90 百分位（0.35、0.43），A 半選出 0.35（MRR 平均 0.403，只用關鍵字 0.391，差距可能是雜訊），**B 半驗收 0.476 → 0.602**，兩半一致才採用。調參報告在 `reports/調參過程/`。
- **P3 的觀察**：向量幫最多的是原句模式與攻略題（攻略題原句 0% → 33%）；正確答案有向量的 22 題原句 Hit@5 77%、沒有向量的（2025 年以前）30%——舊資料補向量是最直接的改進。只有 1,000 份有向量的預覽版整體反而變差（原句 38 → 29%）：向量那一路涵蓋不全時，會把不相關的新文章與關鍵字找對的結果平分名次；混合檢索的兩路要涵蓋同一批資料、向量要有門檻。
- **P4 的觀察**：只比一種設定、沒有挑參數。原句模式明顯變好（MRR 0.446 → 0.555；A 半 0.335 → 0.561、B 半 0.557 → 0.549）；**關鍵字模式變差**（0.559 → 0.483；A 半 0.471 → 0.487、B 半 0.647 → 0.478）。推測 reranker 是用自然語言問句訓練的，「卜靈 身分」這種斷片判不準 → 改用原始問句（見下一點）。第一次 P4 評估約三分之一請求失敗（llama.cpp 的物理批次預設 512 token，段落＋問題到 530～569 token），已作廢（`調參過程/*P4-重排前30篇-作廢-批次上限`），加 `-ub 1024 -b 1024` 後重跑零失敗。
- **P4 原句重排（10-08 17:05）**：只改一處、沒挑參數。關鍵字模式 MRR 0.483 → **0.596**（也高過不重排的 0.559），Hit@1 31 → 48%、Hit@5 74 → 81%；A 半 0.487 → 0.563、B 半 0.478 → 0.629（和不重排比：A 0.471 → 0.563、B 0.647 → 0.629，B 的差距不到一題的量）。原句模式與上一次一字不差（這個模式下原句就是查詢字），等於重現了舊結果。推測成立：reranker 要讀自然語言問句。還沒過的 8 題多是暱稱（家主、汐汐、水母）與答案只在舊資料（沒向量）。
- 速度：向量化約 4,600 字／秒（今年 1.8 萬段 16 分鐘，含讓路 4 分鐘）；reranker 30 篇約 1.6 秒（第一次載入 24 秒）。

**已定案的設計決定**（理由）
- 只開 `search`、`fetch` 兩個工具：工具少模型選得準；來源由登記表產生，加來源不加工具。
- 每種來源最多 5 筆、每筆標來源與是否官方：論壇的量不能淹掉官方；回答分開講官方與玩家說法。
- 三字組＋兩字組兩份全文索引、不用斷詞詞典：角色名與暱稱一直增加；BM25 自動壓低常見詞。
- 巴哈以樓層為文件單位（R6-Q1）；切段約 500 字、重疊 80 字、每段帶標題（contextual chunk header）；聊天紀錄一則一段不切。
- pgvector＋HNSW（不另架向量資料庫）：已有 Postgres、量在十萬級；有篩選時開 `iterative_scan`，結果先照距離排序再去重。
- 查詢加任務說明、文件不加（這類 embedding 模型的用法）；RRF 只看名次不看分數。
- 向量門檻 0.35（A／B 拆半選出）；重排前 30 篇、在來源上限之前做、段落＝標題＋和問題重疊最多的那段。
- 先做 2026 年起的向量（比例原則，使用者 R10-Q2），舊資料之後補；巴哈只做四類討論串。
- 開關放 `switches.json`（預設關）；考卷留在 git（只有問題與文件 id），論壇原文不進 git（R5-Q3）。
- 不讓爬蟲直接寫搜尋索引（雙寫）、維持 search-mcp 從 `articles.db` 拉（10-09 使用者問「為什麼不讓巴哈 PTT 寫入時額外寫 MCP 資料庫」）：索引本來就要能從 `articles.db` 重建（改正規化、改切詞、壞掉），拉的路一定要有，雙寫只是多一條；爬蟲寫索引失敗（重建中、鎖住、容器停）會漏，還是要靠同步補；衍生資料不該拖累爬蟲；爬蟲是另一個容器與套件，文字整理程式會變兩份、版本一分岔索引就不一致；四個爬蟲都要改。雙寫唯一的好處（知道內容真的有沒有變）可以改由「爬蟲只更新最後看到時間時不動 `updated_at`」取得（L 組選項 3，之後再議）。要更即時時，可讓爬蟲寫完通知 search-mcp 立刻同步（爬蟲已有通知 bot 的機制），資料仍是單一寫入者；目前每 50 秒同步一次只要約 10 毫秒，不需要。面試用語：雙寫 vs 從唯一資料來源做 CDC（游標 (updated_at, id) 是簡化版 CDC）。使用者追問「以後換資料庫能不能用 trigger 寫 MCP 資料庫」：不建議 trigger 直接寫索引（和爬蟲寫入同一筆交易、會拖累爬蟲；trigger 裡做不了文字整理；重建的路照樣要有）；建議 trigger 只寫同庫的變更紀錄表（內容真的變才記，順便濾掉只更新最後看到時間的假變動）或發通知（換 Postgres 後用 LISTEN/NOTIFY，專案已有前例：Telegram 爬蟲的 `telegram_new_message`），search-mcp 收到再自己讀、自己寫索引——Outbox 模式。現在是 SQLite 沒有通知，變更紀錄表要改 `articles.db` 結構，之後再議。
- compose 的 bind 掛載不改 named volume（10-08 使用者問）：`./src`（即時改程式）、`./logs`（主機要看）、`search_data`（主機要備份、刪除）都需要主機路徑；`gpu_lock` 改 named volume 的話資料夾歸 root、容器裡的 appuser 建不了鎖檔，只會記警告然後各排各的隊。重複只有三個掛載，YAML 合併不了清單，只把 `build:` 抽成 `x-main-build` 錨點（兩個服務的映像檔不能分岔）。
- search-mcp 共用 bot 的映像檔、不另做精簡版（10-08 使用者問）：實測一次完整搜尋只載入 mcp、opencc、llama-index-core（embedding 用戶端和 bot 的聊天記憶共用）、psycopg2、bs4／lxml 等，discord.py、yt-dlp、Telethon 都沒載入——沒用到的套件不佔記憶體（search-mcp 約 190 MB）；兩個映像檔 12 層全部共用，不多佔硬碟。另做一份反而要多維護一份 requirements，共用的程式（`sys_settings`、`llm.client`、`utils`）加了 bot 專用套件的 import 時精簡版會在執行時才壞，opencc 版本分岔還會讓索引的正規化方式不一致。之後搜尋要搬到別台機器或單獨發布時再拆。
- R12（10-08）：MCP 常駐成獨立的 compose 服務（不放進 bot 行程：建索引會搶 event loop、改程式要重啟 bot、開 port 的行程不該握有 Discord token）；stateless HTTP（容器重開客戶端不用重連）；容器聽 0.0.0.0、主機只綁 127.0.0.1、Host 白名單防 DNS rebinding；索引移出 `src/`（幾百 MB 衍生資料不跟程式碼混）；每日維護避開 04:00～07:30、不補做（漏一天下次一起補）；`question` 只給重排用（reranker 用自然語言問句訓練；關鍵字適合找、挑段落）。
- 2026-10-08 程式碼審查（5 個面向的 agent 找、每個發現再由懷疑者反駁，29 個成立 13 個）修掉：批次向量沒走 GPU 閘門、新舊行程輪流重建索引、評估挑門檻用到 B 半、只刪結尾時舊段沒刪、`relaxed_order` 沒排序就去重、`until=9999-12-31` 溢位、共用元件表漏列。

**待做**
1. **R12 收尾**：已部署、驗收、commit；Claude Code 重連後 `search`、`fetch` 實測可用（10-08 19:22）。
   - **未定案：閒置後第一次搜尋很慢**。實測：部署後第一次 37 秒（同步 20 秒＋載入模型）；另一次 48 秒，Lemonade log 顯示空檔落在「問句向量算完」到「送出重排」之間，也就是讀 pgvector 或搜尋索引；同一句再跑 1.2 秒。原因：VM 記憶體 7.7 GB（快取約 3.7 GB，和 bot、pgvector、其他服務共用）、虛擬硬碟，閒置後索引頁面被擠出快取。選項：(a) 先接受（目前只有 Claude Code 偶爾用）；(b) 搜尋各階段計時寫進 log（總時間超過幾秒才記），先分清楚是 pgvector 還是 SQLite 慢；(c) 定時暖快取（會跟其他服務搶記憶體，不建議）；(d) 縮小讀取量（例：兩字組 BM25 對很常見的字組設上限）。建議：先做 (b)，有數據再決定 (d)。
   - 未定案：向量那一路要不要也改用原句（embedding 的查詢說明本來就寫「問題」；關鍵字斷片的向量可能比較差）。建議：照重排的做法加進評估量一次再決定。
2. 舊資料（2025 年以前）補向量；之後再量一次。
3. 暱稱對照表（查詢擴展；家主＝坎特蕾拉、汐汐＝今汐、水母＝坎特蕾拉、里哥／要哥＝相里要…），前後都要量。
4. 向量的模型指紋（分支事項，使用者「先記起來」）：向量表沒記是哪個模型算的、hash 只看文字，換 embedding 模型會新舊座標系混用且不報錯；要補時一個模型一張表、用考卷比較後切換。pgvector 的維數是欄位型別的一部分不能直接改；HNSW 上限 2,000 維（更大用 `halfvec`）。
5. 考卷擴充到 100 題以上，分調參用與驗收用。
6. 選配：微調 reranker 或 embedding（考卷不能拿來訓練；用 LLM 從段落合成問題、搜尋結果裡的錯誤答案當難負例；AMD＋Windows 訓練環境麻煩，可能要租雲端 GPU，訓練完轉 GGUF）。
7. **/askai 接情報搜尋（10-09 上線）與網路搜尋工具化（10-10 上線）：已完成、已 commit、已推送**。commit 清單、最終審查（19 個 agent）、SearXNG 工具化的三輪審查與真模型實測、網路搜尋免費優化的根因、L 組（搜尋延遲：`updated_at` 索引、背景同步、等待額度、計時、無篩選捷徑）的討論與實作全文已歸檔到 `TODO-completed.md`「/askai 接情報搜尋與網路搜尋工具化：實作、審查與延遲改進（歸檔 2026-10-13）」。這裡只留架構、定案與還沒定案的事。
   - **架構**：/askai → `run_with_intel`（開關開著才向 `http://search-mcp:8765/mcp` 讀工具清單；每次工具呼叫各開短連線，都在 llm_task 裡，按取消一起中斷；連不上就照原本回答）→ `LLMService.generate_reply(tool_runner=IntelSearchSession)` → `_answer_with_tools`：每一輪都照 /askai 原本的思考設定、帶同一份工具清單，模型直接回答或叫工具（最多 2 輪）→ 工具在兩次模型呼叫之間執行（不拿 GPU 鎖；search-mcp 算向量、重排排同一把鎖）→ 查滿還想查先提醒一次、再不行改用不帶工具的 `chat_raw`；第一次呼叫就失敗也改用 `chat_raw`。**每一輪的設定都一樣**：思考開關、工具宣告都會改到 prompt 前段，一變動後面整段提示詞快取就失效。（原本第 1 輪是不開思考、限 200 token 的決策輪，10-11 拿掉，見 `llm-inference-kv` 待做 4）
   - **定案與理由**：①bot 當 MCP 客戶端（discord-bot 沒掛索引、索引只該一個行程寫；10-08 建議 (b)）；②模型自己決定查不查（R2-Q3 已定案，關鍵字觸發會漏攻略題）；③~~只有第一輪是決策輪~~ → 10-11 改成沒有決策輪：每輪設定相同，不查的題目只呼叫一次、查一次的題目 2 次（決策輪實測省不到幾秒，卻讓下一輪快取接不上，見 `llm-inference-kv` 待做 4）；④工具只開 search／fetch（R2-Q2）；⑤模型漏帶原句時客戶端補上（重排要讀原句）；⑥結果只給回答用得到的欄位、全文截到 2,500 字；⑦安全規則把 web_context 與工具回傳的內容列為不可信（論壇文章與留言任何人都能寫）；⑧網址上限兩處統一成 3 個（原本 3 與 5 矛盾）；⑨長回答依 Discord 2,000 字切多則（5 月出過錯）；⑩共用元件先抽再用：工具訊息格式（人格萃取已有一份）、切段（Telegram 已有一份）。人格萃取的迴圈本身沒合併：它綁 token 預算、估算校正、禮讓前景，/askai 不需要；兩邊共用的是訊息格式與參數解析（AGENTS「只抽機制、長相留給呼叫端」）。
   - **網路搜尋也是工具（10-09 使用者「改 我怕打架」；已上線）**：SearXNG 包成 `web_search`，和情報的 search／fetch 合成同一組交給同一個工具輪（`tool_calls.combine_runners`），模型一次決定查哪邊；工具模式不走關鍵字觸發。題目類型由模型選 `kind`（general／news／weather／currency），每種類型的引擎、時間範圍、語系寫在 `llm/retrievers/web/tools._KINDS`（使用者 10-09：「關鍵字過濾還是不太好」→ 不交給關鍵字分類）；天氣走 `openmeteo`、匯率走 `currency`，SearXNG 的直接答案放 `WebRetrievalOutcome.answers`；被擋的引擎（真人驗證、限流、拒絕存取）暫避 30 分鐘；同查詢 5 分鐘快取。純免費（使用者 10-09「我要當純免費仔」：不註冊、不要 key；不破解真人驗證）。查到的引擎事實：bing 一般搜尋與 duckduckgo news 不支援 time_range；duckduckgo 一般搜尋 10-09 起常被真人驗證擋（SearXNG 對它的停用秒數寫死 0），一般搜尋只剩 bing、品質不穩。
   - **搜尋端索引定案（10-09 使用者「加索引我沒意見」「直接加 不要用遷移的方式」）**：直接在 `articles.db` 建四個 `(updated_at, id)` 索引（`ix_<表>_updated_at_id`），不走 Alembic；`src/scraper/db/models.py` 照樣宣告（autogenerate 比對時一致）；搜尋端 `_changed_rows` 用 `(updated_at, id) > (?, ?)`。已建（10-09 14:3x）。L 組其餘（背景同步 50 秒、一次搜尋共用 10 秒 GPU 等待額度、超過 3 秒記 WARNING、沒篩選時只在全文索引排名）已寫在上方「架構」。Lemonade 閒置後卸載 embedding／reranker 是預設行為，接受（使用者 10-09）。
   - **留給使用者**：(1) ~~插話被 @ 時要不要也能查~~ → **已定案：不查**（10-09 使用者「@先不要查 因為/askai 就是特定查詢目的」）。(2) 最多 2 輪、全文 2,500 字是估的，建議上線一週後看 `askai_response_history.jsonl` 的 `intel_meta` 與 `web_context_meta.calls` 再調（輪數是情報與網路共用；放寬輪數的選項見第 9 項）。(3) `searxng/settings.yml` 的 openmeteo 那段建議加 `timeout: 4.0`（地點查座標＋拿預報常超過預設 2 秒；不能超過 `max_request_timeout: 4.0`），改完 `docker compose restart searxng`；`searxng/` 是使用者的檔，我沒動。
   - **未定案：天氣題查不到預報**（關鍵字模式走同一條路由與引擎，不是這次改動造成）。選項：(a) 先觀察，看群友多常問天氣；(b) 加一個天氣工具接中央氣象署開放資料 API（要申請免費授權碼，回答有實際數字）；(c) 調路由，天氣題加站內限定（例：`site:cwa.gov.tw`）。建議 (a)，有人常問再做 (b)；(c) 引擎對 site 語法支援不一，要先量。
   - **未定案：股價查不穩**。選項：(a) 加「台股」類型直接查證交所即時報價（`mis.twse.com.tw` getStockInfo，不用 key、0.07 秒、與看盤網站一致；網頁背後沒公開文件的介面、可能改版或限流，要股名→代號表，休市日回前一交易日要標資料時間）；(b) 等 duckduckgo 解封、不改程式；(c) Tavily 等免費方案要註冊 key，不符合「純免費」先排除。建議 (a)。
   - **留給使用者（新）**：(W5) 關鍵字模式（`askai_web_search_mode=keyword`，`intent.should_search` 與 `_ROUTE_RULES`）要不要整個刪掉——建議工具模式跑一週沒問題再刪，現在留著當退回開關；(W6) 新聞類型要不要拿掉一週限制（讓 duckduckgo news 回來，會混舊文）——建議等網路搜尋評估集。
9. **Agent 評估（10-12 跑完；已 commit、未推送：`a918ff4` 評估程式搬進 `eval/`、`f9364c8` Agent 評估與三份報告）**。怎麼設計、怎麼跑、途中的事故、評估程式搬進 `eval/` 的經過，已歸檔到 `TODO-completed.md`「Agent 評估：實作、第一次執行與評估程式搬家」；這裡只留結果、限制與還沒定案的事。
   - **程式在哪、怎麼重跑**：算分 `services/search/eval/agent_eval.py`，跑題目 `test/integration/it_askai_agent_eval.py`。`docker exec -w /app discord-bot python -m test.integration.it_askai_agent_eval --label <名稱>`（約 1.5 小時、避開維護時段；每題上限 10 分鐘；`--resume`／`--score-only` 帶 `eval/private/` 的經過檔）。和 81% 用同一把尺比：把報告檔當 `--keywords` 交給 `python -m services.search.eval.evaluate --mode 關鍵字 --rerank on`。
   - **結果（42 題考卷＋6 題閒聊，沒有出錯的題目）**：
     - 該查的有沒有查：42 題全部查了遊戲情報（沒有只查網路、沒有完全不查）；閒聊 6 題全部沒叫工具。查 1 輪 6 題、查 2 輪 36 題；search 共 60 次，其中 58 次模型自己有帶原句。
     - 模型自己寫的查詢（和 81% 同一把尺的重放）：**Hit@5 71%、MRR 0.533**；同一天重跑外部 agent 那份仍是 81%／0.596（索引新增沒影響）。逐題：模型比外部 agent 差 6 題（q08、q20、q21、q25、q26、q39）、好 2 題（q24、q27），符號檢定 p≈0.29，**差距不顯著**。
     - 模型實際用起來（它每次只看到前 6 筆）：第一次 search Hit@5 71%，算上換字再查 **79%**——重試把差距補回大半。
     - 回答對不對（Claude 對照證據句初判，**使用者還沒確認**；判讀在 `eval/private/20261012-0745-Agent評估-正式模型-回答判讀.json`）：**對 31、只對一半 2、錯 3、說查不到 6**（74% 答對）。有找到正確文章的 33 題裡答對 30 題（91%）；沒找到的 9 題只答對 1 題，其中 3 題答錯、4 題老實說查不到、1 題只對一半。
     - 連結：41 題有附、32 題附到正確答案那篇、**0 題附了工具結果裡沒有的連結**；22 題用 fetch 讀到正確答案。
     - 時間：每題中位數 71 秒、第 90 百分位 166 秒、最久 411 秒；超過 2 分鐘的有 11 題。
   - **沒答對的 11 題的原因**：search 沒找到 8 題（q08、q11、q15、q20、q21、q26、q32、q42——用字不同、暱稱「水母」被當成守岸人、「4C」被當成配隊）；找到了但沒輪數讀全文 2 題（q25、q39）；找到了但讀了別篇 1 題（q12）。
   - **限制（報告數字時要一起講）**：每題只跑一次（模型有隨機性）；沒有聊天紀錄，線上的 prompt 比較長；考卷還是 42 題；回答對不對是 Claude 初判、使用者還沒確認。
   - **未定案：要不要放寬「最多查 2 輪」（10-12 使用者問「這需要修正嗎，還是會越修越 overfit」）**。評估發現：42 題裡 13 題查滿 2 輪還想再查（被提醒後才回答），其中 4 題本來就答對、9 題沒答對；確定被輪數卡住的是 2 題（q25、q39：第 1 次 search 沒中、第 2 次已把正確文章排第 1，沒有輪數叫 fetch），其餘 7 題是搜尋本身沒找到，多一輪不一定有用。選項：(a) 上限改 3；(b) 第 3 輪只准 fetch（只在已經找到文章時多花一輪）；(c) 不改。**建議：面試前不改**（正式程式凍結；單跑一次差 2 題在模型隨機性內，量不出來），面試後先試 (b)。**不算 overfit 的條件**：理由是機制（「沒中→換字再搜→讀全文」要 3 輪，和哪一題無關）、改的是通用能力不是針對題目、效果用沒看過的題目量，而且正確率和每題秒數一起報（約三成題目會多一輪）。**這份考卷的用途變了**：這次把 42 題的失敗原因全看過，之後它只能拿來找問題，不能再拿來驗收由它找出來的修法；驗收要用新題目（待做第 5 項）。
   - **未定案：模型寫查詢的毛病（可以改工具說明）**：7 題的第一次查詢加了「鳴潮」兩個字（整個索引都是鳴潮，等於雜訊），q08 多加「角色」就從第 1 名掉到第 19 名。建議：工具說明加一句「不用加遊戲名稱、只放最關鍵的兩三個詞」，改之前之後各跑一次；同樣要用沒看過的題目驗收。
   - **未定案：對話請求逾時後自動重試，會把一次寫不停的回答拖到 15 分鐘（線上 /askai 同一條路）**。評估時第 42 題發生：300 秒逾時有生效，但 `LlmHttpClient` 預設重試 2 次、逾時也重試，對話請求又沒有長度上限（`max_tokens`），三次嘗試各寫了 6,000～8,600 token 沒寫完，整段拿著顯示卡鎖，bot 的另一個工作等了 12 分半（時間線見歸檔）。**選項**：(a) 對話請求逾時不重試（逾時代表模型還在寫，不是連線問題）；(b) 給 /askai 的回答一個長度上限；(c) 兩個都做。**建議 (c)**，這不是調分數，是會讓 bot 的 AI 卡 15 分鐘的問題；要不要在面試前動由使用者決定。
   - **待查：完整測試偶發 1 項失敗**。10-12 09:2x 連跑五次 1,404 項，四次全過、一次有 1 項失敗沒抓到是哪一項，之後（含搬檔後）沒再重現；懷疑是某個和時間有關的測試。再遇到時把輸出存檔。
8. 小毛病：FB 的標題是內文第一行（摘要重複）；巴哈討論串標題改了舊樓層不更新；長期更新的整理串日期停在建立日（日期篩選要考慮 `updated_at`）；3.1 版本內容說明爬蟲漏抓；有些官網公告內文只在圖片裡（之後可用 VLM 抽字）。

## 架構審視與滾動修正（2026-10-12 起；M1、M2a 已上線，M2d 守衛完成，M3 進行中）

<!-- @meta
id: architecture-review-2026-10
type: TODO
status: draft
depends_on: mcp-search-tools
affects: 全專案的分層、背景任務、設定與持久化、測試 gate
last_confirmed: 2026-10-13
-->

> 靜態掃描（190 個程式檔 58,436 行、92 個測試檔 24,002 行）＋讀模組說明得出的判斷，沒有逐一讀邏輯；數字是當天掃的。結論：功能面與工程紀律（守衛、突變、開關、遙測、驗證層）紮實，結構面有幾個累積的問題。10-12 起依下方「滾動修正計畫」逐項修，進度見「進度」。

| # | 發現（證據） | 建議 | 大小 |
|---|---|---|---|
| 1 | **分層方向沒定義**：`llm`↔`services` 檔案開頭互相 import 21 條（llm→services 7、services→llm 14），函式裡再 12 條明顯是繞循環；`services.llm_service` 用的全是 `llm.client.*`、`llm.prompt.*`，卻放在 services，而 `llm.ambient`、`llm.persona` 又反過來 import 它；`sys_settings.switches → llm.prompt`（設定層依賴功能層） | 定義方向（client／infra → llm 核心 → 功能 → commands），`llm_service` 搬進 `llm`，`switches` 不碰 prompt；用守衛固定方向（`test_import_resolution` 可擴） | 中 |
| 2 | **Discord 滲到下層**：services／llm／utils／settings 共 26 個檔 import discord，`llm` 層 8 個（ambient 4、storage 2、retrievers、preprocess）。服務層實際是 Discord 應用層，離開 Discord 不能測、不能重用 | 至少 `llm` 層不認 discord：訊息轉成純 dataclass 再進去；services 的 relay／community 可以慢慢來 | 中～大 |
| 3 | **單一行程、單一 event loop 扛所有東西**：心跳、音樂、插話、/askai、Telegram 轉發與過濾、記憶寫入、人格萃取、日記、字典補、通知伺服器；`on_ready` 326 行、起 6 個背景任務；`discord_bot.py` 921 行、41 個函式內 import；全部 LLM 工作排同一把閘門，一個卡住全停（10-09 事故、10-12 評估佔 15 分鐘） | 把 LLM 背景工作（萃取、日記、記憶寫入、字典補）拆成一個 worker 行程（像 search-mcp），bot 只做 Discord I/O 與排隊；做不到就先做下一項 | 大 |
| 4 | **背景任務沒有人管**：12 處 `create_task` 沒留參照、沒 done callback（discord_bot 5、notify_server 2、relay 2…）；任務死掉無聲 | 一個 supervisor 建所有背景任務：記 log、例外重啟、退避；`on_ready` 只剩登記 | 小 |
| 5 | **超大函式與檔案**：`_handle_askai_request` 468 行（31 if、6 try）、`_run_one_ambient_pass` 354、`on_ready` 326、`_retrieve_rag_context_impl` 320；檔案 telegram_relay_service 2,748、fb_scraper 2,354、llm_commands 1,552；commands 層 8,898 行＝UI 層塞業務邏輯 | /askai 流程拆成 pipeline（上下文 → 檢索 → 生成 → 送出 → 記錄），commands 只剩互動；插話的單次評估拆成關卡物件 | 中 |
| 6 | **設定與狀態來源太多**：pydantic 14 class／308 欄位、config.json 23 key、switches 13、環境變數 28 個名稱、llm_runtime_config.json、16 個 prompt 檔、11 個 runtime JSON、34 處寫死 `/app/`；16 處各自 json.load／dump（`item_prices.json` 三處各自讀寫）。持久化 4 種：articles.db、search_index.db、StateDB（7 表）、Postgres（pgvector＋十幾張普通表）＋ runtime JSON | runtime JSON 全收進 StateDB（同類）；`/app/` 改一個 base path 設定；item_prices 單一存取點；規則 AGENTS 已寫，是歷史包袱沒收完 | 中 |
| 7 | **容器邊界上的套件撞名**：scraper 容器把 `src/scraper` 掛成 `/app`，裡面的 `services`、`utils` 和 bot 的同名；同一 repo 兩套 `services`／`utils`，依容器而異（這次掃描第一輪就因此誤判）；bot 又直接 import `telegram_scraper.tg_config`、`telegram_scraper.media_download`（另一個容器的程式） | 真正共用的（normalize、媒體時限常數）抽到明確的 shared 套件；scraper 內部套件改名或改相對匯入 | 中 |
| 8 | **測試覆蓋不均、gate 太重、沒有 CI／lint／型別檢查**：34 個模組 11,245 行（20%）沒有任何測試提到（scraper 幾乎全部、commands 的 article／user／trade／test_commands、music、ptt_monitor、channel_registry、raw_message_store、memory_service）；啟動 gate 跑 1,383 項約 90～100 秒，每次重啟都付；守衛 30 條規則是亮點；75% 函式有回傳型別但沒有 mypy／pyright；requirements 只釘 5／51（靠 constraints 102 行），scraper／telegram_scraper 的 requirements 完全沒釘 | gate 只跑守衛＋import 解析＋設定載入（幾秒），完整測試交給 GitLab CI；加 ruff＋pyright basic；三個 requirements 都釘版本 | 中 |
| 9 | **錯誤邊界沒集中設計**：624 處接所有例外（fb_scraper 99、telegram_relay 29、discord_bot 28、llm_commands 18）；多數是「不讓一個失敗拖垮全部」的合理用法，但每個呼叫點自己決定吞不吞 | 裸 except 只允許在邊界（排程 tick、每則訊息、每個工具呼叫）；守衛擋 llm／services 內層 | 中 |
| 10 | **安全與營運邊角**：`commands.test_commands` 在正式環境無條件載入，`/anonymous` 讓任何人用 bot 身分匿名發文、沒有權限檢查（違反 AGENTS 的 check_guild 規則）；notify_server 綁 0.0.0.0 無驗證（只在 docker 網路內，scraper 被攻破就能打）；單管理員、無備援、推論在另一台 Windows 主機 | `/anonymous` 拔掉或 owner_only、test_commands 用環境變數決定載入；notify 加 shared secret；其餘面試照實講 | 小 |
| 11 | **文件很重**：AI_HANDOFF 2,147 行、TODO-completed 4,614 行；最近 60 個 commit 有 13 個 docs。對單人＋AI 協作有效，新人看不完 | 「現況」和「紀錄」拆兩個檔；歸檔照現在的節奏 | 小 |

**好的地方（嚴格審也要寫）**：共用元件守衛（違反就起不來）、每個新測試做突變、off／dry_run／on 三段開關、逐筆 `llm_usage` 遙測、MCP 獨立容器＋只綁本機＋Host 白名單、GPU 閘門有租約與等待上限、把模型輸出當不可信輸入的驗證層、評估有 A／B 拆半與顯著性、每個模組說明寫「為什麼」。

**滾動修正計畫（10-12 使用者：「/anonymous 與 test_commands 好玩的可以先不管；其他都要修正；滾動修正、每個 commit 之前先停讓我看、同意就繼續；每個 commit 要能獨立、看得出重點」）**

- **流程**：一個里程碑＝一到幾個 commit。每個 commit：改完 → 容器暫存副本跑完整測試（新測試做突變）→ 停下來給使用者看（改了什麼、為什麼、測試結果、要不要重啟）→ 使用者同意才 commit → 下一個。需要重啟的 commit 集中在一批的最後，請使用者避開 00:00 與 04:00～07:30 重啟。
- **里程碑（草案，順序照風險由低到高；第 10 項依使用者決定跳過）**：
  - ✅ M1 背景任務 supervisor（第 4 項）：`utils/background_tasks.py` 的 `spawn`／`supervise`；16 個長跑迴圈與 11 處丟掉結果的 `create_task` 都改走它；守衛擋裸 `create_task`。`49d288e`、`8a1d3ba`，10-13 11:20 重啟後生效。
  - M2 依賴方向（第 1 項）：✅ M2a `llm/prompt/prompt_files.py` → `utils/hot_files.py`（`sys_settings.switches` 不再 import `llm.prompt`；三份 mtime 快取併一份、壞檔沿用上次；`63be5a4`，已上線）；❌ M2b `llm_service` 搬進 `llm/` **退回**（與 09-29 定案相反，見下方「分層定案」）；❌ M2c 取消（MCP 殼留 `llm/`）；✅ M2d 守衛 `test/test_layering.py`（五層寫到子資料夾、只能同層或往下、跨容器一律列例外；1,432 項全過、6 個突變全紅；併進 M3 的 commit）。
  - ▶ M3 Discord 退出技術層與服務層（第 2 項，10-13 進行中）：第 1 步（守衛「技術層與服務層不可 import discord」＋`sticker_cache`、`context_retriever` 改掉 discord import）做完等使用者看；第 2 步「`llm/ambient`、`llm/storage` 的功能層模組要不要搬到 `services/`」等使用者決定（建議不搬，見下方「M3 第 2 步要使用者決定」）。
  - M4 超大函式（第 5 項）：`_handle_askai_request` 拆 pipeline、`_run_one_ambient_pass` 拆關卡、`on_ready` 剩登記、`_retrieve_rag_context_impl` 拆段；先補測試再拆，行為不變。
  - M5 設定與狀態（第 6 項）：`/app/` 改 base path 設定；`item_prices.json` 單一存取點；runtime JSON 逐個收進 StateDB（高風險資料：每個都先備份、使用者同意）。
  - M6 套件撞名（第 7 項）：共用的 `tg_config.normalize_channel_identifier`、`media_download` 的時限常數抽到 shared 套件；scraper 內部 `services`／`utils` 改名；要重啟 scraper、telegram-scraper。
  - M7 測試與工具鏈（第 8 項）：M7a 三個 requirements 釘版本（從執行中的容器 `pip freeze` 取）、加 ruff＋pyright basic 設定與 `make check`；M7b 啟動 gate 只跑守衛＋import 解析＋設定載入，完整測試改成手動／CI；M7c CI 依 Q4。
  - M8 錯誤邊界（第 9 項）：守衛擋 llm／services 內層的裸 except，現有 624 處列 allowlist 當 ratchet，只准減不准增；逐步清。
  - M9 LLM 背景工作拆 worker 行程（第 3 項）：先寫設計（哪些工作搬、怎麼拿 Discord 權限、排程誰管）再討論，最後做。
  - M10（原第 11 項）文件拆「現況／紀錄」：最後、可不做。
- **圖解頁**：`架構修正計畫`（使用者私人 artifact，連結在 `doc/interview/README.md`）：分層與「Discord 接入」、CI 的用意與架構、里程碑進度表；之後每個里程碑完成就更新。
- **待重新決定的清單（10-13 列給使用者；/goal 期間照「建議」做，標 ★ 的不碰）**：
  - 架構：Q3 Discord 接入 → 建議 (a) 搬 `llm/ambient`、`llm/storage` 的 Discord 接入到 services，llm 禁 discord＋守衛。Q4 CI → 建議 GitLab 共用 runner，先寫 `.gitlab-ci.yml` 與本機 `make check`，**不推送**。M5 runtime JSON → StateDB → 建議「只匯入、不刪不覆寫舊 JSON」（舊檔由使用者刪）；`/app/` 路徑改 base path 設定。M6 套件撞名 → 建議「統一以 `src` 為根」：scraper、telegram-scraper 容器也掛 `./src:/app`、以套件路徑啟動與 import，共用的（`tg_config.normalize_channel_identifier`、媒體時限常數）放 `utils/`；代價：改 compose、重啟三個容器、相對路徑（media、session）要確認。M7b gate 瘦身 → 只跑守衛＋import 解析＋設定載入，完整測試由 `make check` 與 CI 跑。M9、M10 → 最後、先討論設計。★ `/anonymous`、test_commands → 使用者說先不管。
  - /askai 與搜尋（產品行為，★ /goal 不動，最後再決定）：openmeteo `timeout: 4.0`（建議加；`searxng/` 是使用者的檔）、天氣查不到預報（先觀察）、股價（建議加台股類型）、W5 關鍵字模式（跑一週再刪）、W6 新聞一週限制（等評估集）、輪數與全文長度（累積一週）、縮短思考（先用考卷確認）、向量那路改用原句與閒置後第一次搜尋慢（先量）、Agent 評估三題：放寬輪數（第 3 輪只准 fetch，面試後用新題目驗收）、工具說明加「不用加遊戲名稱」、**對話逾時不重試＋回答長度上限（建議併進 /goal，穩定性不是調分數）**、回答判讀 31／42 待抽看（q05、q31、q36、q41）。
  - 其他：推 GitHub＋英文 README（面試前推；9 個 commit 未推送）、備份分支 4 條（推送後刪）、爬蟲 `updated_at`、`.gitignore` 的 `staged_diff.txt`（可刪）與 `monitored_channels.json`（先留）、字典 4 筆可疑描述、`it_comfyui_image.py` 說明矛盾、AGENTS 收工加「字典另外 commit」（建議加）。交易／商品舊的 TR-Q14、TR-Q24、價格 0、BH-Q6、隔離區 grill 兩輪不在範圍。
- **/goal 運作規則（10-13 提給使用者）**：①醒著時每個 commit 前停、休息時不停；每個 commit 獨立、訊息照規則；②里程碑結束列「要重啟的容器＋指令」，使用者有空就重啟（避開 00:00、04:00～07:30；最後一批 10/17 前）；③不刪不覆寫任何資料檔、不碰 `searxng/`、不推送；④要使用者才知道的事先做能做的、最後一併問；⑤★ 的產品行為不在 /goal 內動（逾時不重試那條待使用者點頭）。
- **寫檔注意（10-13 00:4x）**：這段 00:1x 寫過一次、程式也印了成功，之後檔案卻回到 17:51 的內容（mtime 沒變），同一時間使用者在 IDE 開著這個檔——疑似編輯器用舊緩衝蓋回去。之後寫完要重讀驗證；使用者開著的檔，改完提醒他重新載入。
- **進度（10-13）**：M1、M2a 已上線（10-13 11:20 重啟，gate 1,426 全過、上線後無 ERROR）；M2b 退回、M2c 取消；M2d 完成、等併進 M3 的 commit；節點 tag `checkpoint-20261013-m2a`（M1＋M2a）；M3 進行中。每個 commit 的內容、突變、使用者問答等過程紀錄在 `TODO-completed.md`「架構審視：M1、M2 的過程紀錄（歸檔 2026-10-13）」。
- **分層定案（10-13，使用者確認方向）**：09-29 的資料夾定義不變——`services/`＝服務、`llm_service.py` 留在 `services/`；`llm/`＝LLM 相關技術（組裝、優化、橋接、RAG），AI 功能也在裡面；MCP 殼放 `llm/`（橋接）。要守的方向寫到**子資料夾／模組**，不是頂層資料夾：基礎（utils、sys_settings、settings、constants，層內可互 import）← 技術 ← 服務 ← 功能 ← 介面（commands、discord_bot、music），import 只能同層或往下（函式內的也算、`if TYPE_CHECKING:` 不算）；表在 `test/test_layering.py` 的 `LAYERS`，規則在 AGENTS「程式碼」。用這把尺掃 148 個模組：0 條往上、3 條跨容器（`telegram_scraper`，M6 清）。「服務」兩義：部署單位（Lemonade、search-mcp）與程式裡的一層（`LLMService`：把一種能力包成入口給功能用），兩者同時成立。llm 要叫搜尋不必 import services——下層定義介面（`ToolRunner`、`run_due_loop(tick)`、persona 工具可注入的 `fetch`），上層注入實作。M2b 的錯：提案時沒先對照 09-29 定案、把頂層資料夾當成層。
- **M3 第 1 步做完、等使用者看（10-13 12:5x；未 commit）**：先做兩種做法都要的部分。①守衛 `test_layering` 加一條：**技術層與服務層不可 import discord**（`if TYPE_CHECKING:` 裡的不算），基礎層只有 `DISCORD_HELPERS_IN_BASE` 列的 6 個 Discord 工具（`utils.utils`、`discord_content`、`discord_threads`、`dm_notifier`、`panel_bump`、`channel_registry`）可以、每個寫理由，不再 import 的要拿掉（殭屍檢查）；功能層與介面層是 Discord 應用本身，不限制。掃出來只有兩處違規，都已修：②`llm/preprocess/sticker_cache`（技術層）——原本自己向每個伺服器 `fetch_stickers`，拆成 `discord_bot` 的 `on_ready` 抓清單、快取只 `remember(stickers)`（鴨子型別），型別註解進 `TYPE_CHECKING`，模組說明改成新格式；③`llm/retrievers/context_retriever`（服務層）——`import discord` 只剩型別註解，`isinstance(channel, (TextChannel, Thread))` 改看能力（有 `guild` 且有 `history`）。行為差異只有一個：語音頻道的文字聊天以前拿不到脈絡、現在拿得到；私訊、分類、論壇照舊不抓。測試：`test_layering` +1、`test_emoji_autofill` +1、新 `test_context_retriever_channel` 3 項；完整 1,437 項全過（容器副本）；10 個突變全紅（G1 技術層檔頭 import、G2 服務層函式內 import、G3 基礎層非工具 import、G4 例外殭屍、G5 TYPE_CHECKING 當真、S1／S2 remember 不記／數錯、C1 不看 guild、C2 不看 history——第一版只看回傳是空的沒抓到，因為讀失敗被 except 接住也會回空，改成「不能有 WARNING」才紅、C3 把 import 放回去）。M2d 的 `test_layering.py` 與 AGENTS 分層段一起進這個 commit。線上不用急著重啟（新舊程式都能跑；`sticker_cache` 的拆法要重啟才生效，和 M3 其餘一批）。**突變腳本的坑**：第一版 `docker cp` 整個工作目錄的 `src`（含 30 GB 的 Telegram 媒體）進容器、卡了 16 分鐘；改成和 `snap_test.sh` 一樣先把工作目錄寫成暫時的 git tree（只有追蹤的檔）、`git archive` 再疊到副本，一個突變約 4 秒。
- **M3 第 2 步要使用者決定（10-13 提出；M2b 之後才看清楚，所以搬檔前先問）**：Q3 原建議 (a) 把 `llm/ambient/*`、`llm/storage/store_chat`、`raw_message_store` 搬到 `services/`，讓 `llm/` 一行都不 import discord。但 09-29 的定義明說「AI 功能本身（插話、日記、人格萃取、agent）也在 llm」，M2d 的五層表也把它們標成 llm 裡的功能層，而功能層本來就是 Discord 應用、守衛不擋它們 import discord。第 1 步的守衛已經保證「技術層與服務層不認 discord」——第 2 項發現要的「LLM 技術能離開 Discord 測試、重用」已經成立。選項：(a) 照原建議搬：7 個檔、約 20 處 import、測試的 mock 字串、AGENTS 表、記憶都要改，要重啟；收益只剩 `llm/` 資料夾字面上零 discord，而且和 09-29 定義相反／(a′) **不搬**：功能層模組留在 `llm/ambient`、`llm/storage`，照守衛允許 import discord，M3 到第 1 步就算完成／(b) 留原地、改收純資料物件：`ambient_reply` 1,479 行幾乎重寫，面試前不做。**建議 (a′)**：和 09-29 定義一致、不動 7 個檔、守衛已達到第 2 項的目的。使用者沒回之前不動這 7 個檔。
**掃描的限制**：「沒測試提到」是用模組名比對，用別名測到的會漏；except 計數含合理的邊界；async 內同步 I/O 粗掃到 12 處但多半是讀 prompt 檔的 mtime 快取（有意為之）；沒有量 event loop 實際阻塞時間。

## LLM 推論：KV cache、prompt 快取與 GPU（2026-10-08 查證）

<!-- @meta
id: llm-inference-kv
type: STATE
status: draft
last_confirmed: 2026-10-11
affects: Lemonade（Windows 主機）、services/llm_service.py（llm_usage log）、插話與 /askai 的 prompt 順序
-->

> 討論過程（R7、R8）原文在 `TODO-completed.md`「MCP／搜尋工具化：討論與實作紀錄」。

**現況**
- 硬體：Windows 主機、2 張 AMD Radeon RX 9060 XT（各 16 GB）、Ryzen 7 5800X、128 GB RAM、沒有 NPU。這台 Linux 是跑在同一台上的 VM（7.7 GB）。Lemonade 用 llama.cpp（Vulkan）：主模型 `--device Vulkan0,Vulkan1`、ctx 32,768、`--spec-type draft-mtp`、`--parallel 1`（Lemonade 自動補的預設，可從 `llamacpp_args` 改；不是保留旗標）。
- 主模型是混合注意力：64 層裡 16 層完整注意力、48 層線性注意力。KV cache 每 token 64 KiB（F16）→ 32k 約 2 GiB、131k 約 8 GiB、262k 約 16 GiB；線性注意力層每槽另有固定大小的狀態（估約 150 MB）。
- 速度：讀 prompt 約 330 tok/s，產生 22～35 tok/s（單張卡頻寬約 320 GB/s、權重 17.5 GB，接力跑的理論上限約 18 tok/s，超過的部分靠 MTP 推測解碼）。
- prompt 快取：Lemonade 累計命中約 60%，平均每個請求約 10 秒花在重算。bot 每個 LLM 請求記一行 `llm_usage`（功能、prompt、命中、重算、讀 prompt 毫秒、tok/s、MTP 猜中），插話 prompt 約 1.04～1.14 萬 tokens、前 8,139 每次命中、重算 2,200～3,300。llama.cpp 把被擠掉的快取存到系統 RAM（`--cache-ram` 預設 8 GiB，每份約 0.9～1.1 GB）：工作管理員 7.7 GB 的那個 llama-server 就是它。
- `--parallel N`：權重只有一份；context 會被各槽均分（除非 `--kv-unified` 共用一塊）；檢查點每槽各自存在 RAM。
- 物理批次（`-ub`）：embedding 與 reranker 的「整段輸入」要放進同一個物理批次（預設 512 token），超過整次請求失敗；產生文字時長 prompt 可以分批讀，不受限。
- 顯示卡：使用者截圖一張卡 11.8 GB、另一張 0 GB，說「一直如此、運作正常」；但 17.56 GB 權重放不進一張卡，原因未明，做 `--parallel` 實驗時順便量。系統 RAM 72%（約 92 GB）中，處理程序清單只加得到約 16 GB，其餘未查。
- **顯示卡斷線事件（10-08）**：Lemonade log 出現 `vk::Queue::submit: ErrorDeviceLost`——10:24 一次（embedding 大量寫入與一個長回答同時在跑）、10:39～10:56 主模型每個請求都失敗（bot 6 次插話失敗、群友看不到），11:01 重新載入後恢復。原因未定（Windows GPU 逾時重置、兩個 llama-server 同時用同一張卡、驅動）。之後的批次向量化都走 GPU 閘門。
- 讀 Lemonade log 的方法：主 port 13305 的 `/logs/stream` 接受 websocket，送 `{"type":"logs.subscribe"}` 會先回最近 5,000 行；llama-server 啟動時的配置行被過濾、看不到。看得到進來的是對話／embedding／重排、產生到第幾個 token（`n_gen`，約每 3 秒一行）、做完的統計、被取消（`cancel task`、`aborted due to client disconnect`）；看不到是誰送的與內容，要對 bot 這邊 `llm_usage` 的功能名稱與編號。每個模型現在忙不忙看 `/api/v1/health`（10-12 用它還原了「逾時後自動重試」的時間線）。

**已定案（R7、R8）**：先顧「回應快」（常用的長 prompt 不被洗掉）；KV 維持 F16；要測 131k 的極限；順序＝先量現況（`llm_usage` 已上線）→ 調 prompt 順序（不變的放前面）→ 固定槽放進實驗量 → RAM 快取上限等 RAM 調查後再定；實驗腳本在 VM 經 Lemonade 跑、使用者看工作管理員記 VRAM／RAM。

**待做**
1. 用 `llm_usage` 找出誰洗掉誰，調插話與 `/askai` 的 prompt 順序。
2. `--parallel` 實驗六組：①現況 1 槽 32k ②4 槽均分 ③4 槽 `--kv-unified` ④1 槽 131k ⑤KV q8_0 ⑥2 槽、兩種長 prompt 輪流送、比較帶不帶 `id_slot` 的第一個字出來前等多久；①～③各測同時 1／2／4 個請求，量第一個字的等待時間、單一與總 tok/s、命中、兩張卡 VRAM、RAM。動正式載入參數前先問使用者，避開維護時段。
3. 主模型的 `-ub` 也影響讀 prompt 的速度，可以放進同一個實驗。
4. **/askai 決策輪→正式輪快取沒接上（10-11 已定案並實作：拿掉決策輪；重啟後待線上驗證）**：`_answer_with_tools` 每輪帶同一份工具清單、只換思考開關（`chat_template_kwargs.enable_thinking`），設計上第 2 輪應接上第 1 輪整段。10-09 線上 6 題的 `llm_usage`：4 題第 1 輪 cached=6,858、第 2 輪 cached=6,894；2 題兩輪都 cached=0；第 2 輪多重讀約 3,300～10,500 token（約 15～48 秒）；第 3 輪起都正常接上。
   - 線索：決策輪沒叫工具的那題（23:39），第 2 輪 messages 與第 1 輪相同，prompt 多 36 token（11,257→11,293）、cached 也正好多 36（6,858→6,894）、重讀一樣是 4,399。
   - **原因（10-11 讀模板查到）**：主模型官方模板（Hugging Face 上的 `chat_template.jinja`，unsloth 版同）在思考開、`reasoning_effort` 為預設 xhigh 時，把一句英文「Reasoning effort is set to xhigh. Please think carefully …」塞在 `<|im_start|>system\n` 後面（工具清單、我們的系統提示詞之前）；思考關沒有這句。結尾另差 `<think>\n` 與 `<think>\n\n</think>\n\n`。用 Lemonade 的 `/api/v1/tokenize` 算：前段 +37、結尾 −2，淨 +35（log 是 36；這個端點不管 `model` 參數都用同一套切詞，差 1 屬正常）。所以思考開關兩份文字從第 3 個 token 起就不同；第 2 輪的 6,894 是接上之前其他「思考開」請求的快取。bot 這端沒問題：同一題兩輪的 messages 一字不差；四題系統訊息互相比對，22:5x 那三題第一個不同的字在 `current_time`（系統訊息 9,980 字的第 9,849 字，接近結尾），23:39 那題因為當晚改了網路搜尋規則，在規則中段就不同。
   - 還沒解：22:5x 三題真正分歧在 `current_time`（照字數估約第七千多個 token），快取卻都停在 6,858，可能是混合架構只能退回檢查點；cached=0 的 2 題也沒查。
   - 驗證法（建議使用者自己跑，面試準備）：同一份 messages、`max_tokens=1`，依序送思考關→思考開→思考開，比三次的 cached；再加一組「思考開＋`chat_template_kwargs.reasoning_effort: medium`」。
   - **決策輪值不值得留（10-11 使用者問「決策輪重要嗎、換別的模型還需要嗎」→ 建議拿掉 → 使用者「你幫我改」）**：10-09 的 6 題全部都有查。決策輪有叫工具的 4 題（輸出 45～91 token）；沒叫的 2 題（22:27 撞 200 上限、23:39）正式輪自己叫了 search，決策輪整輪白跑（約 58 秒、23 秒）。6 題都有「思考開的輪自己叫工具」（search 或 fetch），叫工具前只輸出 56～252 token（約 2～11 秒），所以決策輪頂多省幾秒的思考輸出，卻換來每題 15～48 秒的快取重讀。換模型時：一般的工具迴圈（帶工具清單、模型自己決定叫工具或回答）任何支援工具的模型都能用；決策輪多了兩個跟模型有關的假設（有思考開關、切換開關不會改到 prompt 開頭），這個模型就不符合第二個，沒有思考模式的模型則是整輪重複。沒資料的部分：6 題都是使用者自己問、都是查資料題；拿掉後要用原本的整合測試（含閒聊題）確認模型不會亂查。
   - **採用 (a) 拿掉決策輪（10-11 實作）**：`_answer_with_tools` 每輪 `think` 都照呼叫端的設定、不再限長度；`generate_reply` 的 `decide_max_tokens`、`AskAIIntelSettings.decide_max_tokens`、`chat_with_tools` 的 `max_tokens`（只有決策輪在用）一起拿掉。保留的行為：第一次呼叫就失敗（後端拒絕工具、什麼都沒產出）改用不帶工具的呼叫；模型回過話之後才失敗照實報錯。測試 `test_generate_reply_tools.py` 12 項，突變 5 個全紅（第一輪關思考、第一次失敗不退回、查過後失敗卻退回、又帶限長度、不查時多問一次）。**重啟後實測（10-11 06:46，`it_askai_intel` 四題，新程式）**：第 2 輪快取都接上（兌換碼 cached 7,736／重讀 1,411、6.6 秒；配隊 7,731／1,276、6.0 秒；天氣 7,730／78、0.7 秒），改之前線上 7 題的第 2 輪要讀 16～61 秒；閒聊題沒有查、只呼叫 1 次（31.7 秒）；該查的照樣查（兌換碼 search、配隊 search＋fetch×2、天氣 web_search）。同題在 10-09 用舊程式跑的模型呼叫次數：兌換碼 4→2、配隊 4→3、閒聊 2→1。第 1 輪開思考、叫工具前只寫 93～120 token（3.7～4.6 秒）。整題 70.3／91.6／20.6／31.7 秒，但測試題沒有聊天紀錄、不能直接和線上比。**線上第一題（10-11 07:47，新流程）**：117 秒、模型呼叫 2 次；第 1 輪 prompt 11,206（cached 7,224、讀 20.4 秒、寫 8.2 秒）→ search 7.5 秒 → 第 2 輪 prompt 12,634（cached 11,202、重讀 1,432、讀 6.9 秒、寫 1,412 token 71.7 秒）。第 2 輪快取在線上也接上了；現在最花時間的是寫回答（含思考，佔六成）。同一天 05:53 舊流程那題的第 2 輪是 cached=0、讀 61.4 秒。線上只有這一題是新流程，「整題省幾秒」仍是估算。天氣題第一次 web_search 被 openmeteo 逾時（2.7 秒），模型自己重查一次才拿到——`searxng/settings.yml` 的 openmeteo 加 `timeout: 4.0` 仍待使用者決定。**預估效果（10-11，把新流程套到 10-09 六題的 `llm_usage` 算的，不是實測）**：模型時間（各輪讀 prompt＋寫字，不含查資料與排隊）每題省約 10～58 秒，六題合計 735 → 約 581 秒（少 21%）；決策輪白跑的 2 題省整輪（58、23 秒），決策輪有查的 4 題省第 2 輪的重讀（扣掉第 1 輪改開思考多寫的字，估 6 秒）後約 10～42 秒。假設模型做的決定和當時一樣；六題都是查資料題。圖解頁（使用者私人頁面）第 7 段有圖。沒採用的選項：(b) 正式輪帶 `reasoning_effort: medium`（模板在 medium 時不加那句；會改變回答深度）(c) 兩輪同一種思考設定但保留決策輪。

---

## Telegram 訊息 LLM 過濾 + 隔離區（2026-10-07 已上線，10-08 補判上線）

<!-- @meta
id: telegram-llm-filter-quarantine
type: TODO
status: confirmed
last_confirmed: 2026-10-13
depends_on: telegram-catchup-sweep
affects: Telegram relay、settings/switches.json、telegram_relay_delivery_state（頻道 0、needs_recheck）、telegram_scraper（S1～S4）
-->

**現況（2026-10-07 上線、10-08 補判上線；全部已 commit）**
- 機制一句話：Telegram 訊息轉進 Discord 前，主模型（關思考）看文字＋最多 4 張圖判「對看頻道的人有沒有遊戲資訊」；沒有就送進內鬼頻道底下的「垃圾訊息」thread（最上面一行「判定：標籤｜理由」），thread 置底面板（日期選單 → 訊息選單 → 確認）可放回主頻道，有「管理訊息」權限的人才能按。
- 程式：`services/relay/telegram_filter.py`（`judge`、看圖範圍、排隊）、`services/relay/telegram_quarantine.py`（`QuarantineThreads`，runtime 檔 `settings/telegram_quarantine_runtime.json`）、`commands/telegram_quarantine_commands.py`（面板）、轉發端 `_send_unit`／`move_to_quarantine`／`restore`、一次性腳本 `scripts/telegram_move_to_quarantine.py`（預覽／`--apply`／`--file` 照清單搬）、離線樣本 `test/integration/it_telegram_filter.py`（90 則、`--days N`）；prompt `settings/prompts/telegram_filter_prompt.txt`（手改即生效）。commit：10-07 03:3x 整批 13 個（`8e8e4bc`…`23292a2`）、搬移 `0b1f7f6`／`bd2cfc2`／`0600476`、面板修正 `722768b`、排隊與補判 `c110c6d`／`aa812fe`。
- 開關：`settings/switches.json` 的 `telegram_filter_mode`（off／dry_run／on，每則重讀；現在 `on`）。開過濾時一次只處理一則。
- 判決持久化：發送紀錄 `telegram_relay_delivery_state` 記三種去向——主頻道、隔離 thread、頻道 0（＝停止主動追蹤：相簿晚到超過 12 小時、Telegram 系統通知、有圖標示滿 12 小時沒下載到、合併後沒內容；只影響重啟與每小時補償，不擋真的晚到的圖）；`needs_recheck` 欄＝沒經模型判就放行的，模型恢復後補判（每 10 分鐘也掃一次），判成垃圾就用搬移功能移走。不建新表。10-05 已把舊的 373 則標成頻道 0（備份 `~/backups/telegram_delivery_backup_2026-10-05.sql`）；「啟動補償：偵測到 N 筆」之後應維持 0。
- 等模型：排隊（插話、產圖、別的行程後面都等；跨行程鎖檔在 `gpu_lock/`）；模型逾時或連不上隔 30 秒～5 分鐘再排，排滿 30 分鐘（`give_up_seconds`）才放行並標補判。各模組逾時供參考：插話生成 180 秒、/askai 300 秒、persona agent 讓前景 600 秒、看圖補字典 120 秒、跨行程鎖等別的行程 15 分鐘、過濾單次問模型 60 秒。
- 準確度：90 則離線樣本誤關 0、漏放 1；30 天 414 個單位模型判出 75 個會隔離（閒聊 30、無關圖 24、灌水 15、罵人 6）；10-07 上線第一天 9 個單位搬 4 個。

**已定案（摘要；每題的選項、理由與數據見歸檔「Telegram 訊息 LLM 過濾 + 隔離區：討論、實作與上線紀錄」）**
- 判斷標準：只問「有沒有遊戲資訊」；拿不準就放行；一定看圖（純圖不能一律放行，反例 13649 文字只有「水」、圖是角色設計稿）；文字或任一張圖有資訊就放行；看不了的檔案（語音、壓縮檔）或選來看的圖有一張沒看到就放行；角色手辦、周邊、聯名、展場照算有；看得出是別的動漫或影視的截圖不算。
- 介面與流程：TF-Q1 面板＝thread 置底雙層選單（使用者自訂）；TF-Q2 誰能按＝有「管理訊息」權限；TF-Q3 反方向這次不做；TF-Q4 隔離那則最上面寫判定；TF-Q5 先縮圖、不合併多則一次問；TF-Q6 一次一則；TF-Q7 原本等 90 秒放行 → 10-08 改成排隊到 30 分鐘；TF-Q8 離線樣本 → dry_run → on；TF-Q9 不附前幾則當上下文；TF-Q10／SW-Q1 開關放 `switches.json`、不做開關指令；SW-Q2 這次只搬 Telegram 過濾；SW-Q4 `config.json` 安全寫入（`ChannelConfig.update_config`）。
- 搬舊垃圾（MV-Q1～Q5）：近 30 天、使用者看過清單再搬、刪原貼文、只改那列的 `discord_channel_id`、不備份（Telegram 可重抓；log 逐筆記 `db#` 與列 `id` 供復原）。
- 補判（UC-Q1～Q3）：發送紀錄加 `needs_recheck` 欄（使用者自己執行 ALTER）；模型沒回應或回答看不懂才補；一恢復就補＋每 10 分鐘掃一次。
- 爬蟲端（S1～S4、SQ1＝A）：啟動讀對話清單修相簿缺開頭（Telethon 沒有 pts 起點就丟掉比它早的更新）；下載加 `download_with_stall_guard`（180 秒沒進度就取消）；補掃每 15 分鐘重試到發文＋12 小時（`MEDIA_RETRY_WINDOW`，要等於轉發端 `_GROUP_FOLLOWUP_MAX_AGE`，有守衛）；新訊息第一次下載失敗先壓 30 分鐘不通知（`MEDIA_HOLD_NOTIFY`），補到圖再通知；Telethon 不釘版本。

**還沒做（之後或轉發端那批）**
- 有文字的單則滿 30 分鐘先送文字後，補到的圖送不出去（10-05 定案要以（補圖）補上）。
- 多路由放回會重複標示（目前只有一個路由）；面板置底先刪後發（查詢失敗會暫時沒面板）；移除角色權限寫入失敗時記憶體與檔案不同步；config 寫入鎖只在 bot 行程內；執行緒池被佔滿時可能超過 3 秒；runtime 檔遺失後選日期面板變停用；`/resend_article` 不過濾、不寫紀錄、沒有測試。
- SW-Q3：環境變數裡的功能開關（`ASKAI_WEB_ENABLED`、`PERIODIC_REMINDER_ENABLED`、`TRADE_*`）與 sys_settings 現有開關，改到那個功能時再搬進 `switches.json`。
- 待觀察：搬移腳本判斷時最多等 600 秒、佔著模型時 bot 的插話與新訊息過濾都要排隊，整批搬要避開熱鬧時段；補判搬走時群友會看到「出現又消失」。
- 使用者之後的想法：讓群友回報垃圾訊息的面板（TF-Q3）；F3 密集發文（尖峰一分鐘最多 7 則，排隊跟得上，先不做合併）。

**仍有效的事實**：來源是兩個 Telegram 廣播頻道（`Seele_WW_leak`、`Gamedataleak`），垃圾是頻道管理員自己發的；目的頻道只有 #🌘角色內鬼情報；媒體檔在 `/app/telegram_scraper/media/`（`file_rel_path`）；判斷用主模型關思考（Lemonade 一次只放一個大模型，不另用審核模型）；被拒絕或中斷的 `docker exec` 行程在容器裡還會跑、會佔著模型（10-07 事故，見記憶）。

---

## 巴哈轉發：編輯被限速＋續文／留言格顯示錯誤（2026-10-02 已上線）

<!-- @meta
id: bahamut-edit-pacing
type: RISK
status: confirmed
last_confirmed: 2026-10-13
affects: services/relay/bahamut_monitor.py, test/test_bahamut_edit_pacing.py
-->

> 2026-10-02 已上線並驗證（commit `b11df27`）：同一討論串所有編輯間隔 6 秒排隊、續文每輪逐則比對只編有變的並保留導航連結、本文底部連到第一則續文、建立當下就記 hash、封存串等新回覆再解封補上、新回覆編號修正；上線第一輪 429 由 104 → 0；BH-Q5 的 31 格舊錯誤顯示已用一次性腳本修好。症狀、查證、BH-Q1～Q9 的定案與原選項、測試、複查、上線驗證全文已歸檔到 `TODO-completed.md`「巴哈轉發：編輯被限速＋續文／留言格顯示錯誤（歸檔 2026-10-13，原 2026-10-02）」。
>
> 仍有效：刪文偵測沒做（`is_deleted` 從沒被設成 true），Discord 保留原文、不標示，等遇到實際刪文案例再做（記憶「Bahamut 刪文偵測待辦」）；之後觀察每天 429 是否維持 0、熱門串單輪耗時（最多約 117 次編輯 ≈ 12 分鐘）是否影響下一輪。

---

## scraper 抓網頁機制檢查（2026-10-01 已上線）

<!-- @meta
id: scraper-fetch-fingerprint
type: RISK
status: confirmed
last_confirmed: 2026-10-01
depends_on: it-article-intro-only
affects: scraper/services/base_scraper_client.py, scraper/services/hkepc_scraper_service.py, scraper/services/bahamut_scraper_service.py
-->

> Firefox 系瀏覽器池與一輪一個 session（`run_session`）已上線（`648b80b`、`20acc0c`）；HKEPC 最後一次 403 是 10/01 00:34，03:46 換程式後 0 次。完整的查證（指紋矛盾、逐站實測）已歸檔到 `TODO-completed.md`「scraper 抓網頁機制檢查（歸檔 2026-10-02，原 2026-10-01）」。

- **巴哈變慢另案**（見 `TODO-completed.md` 盤點紀錄歸檔 2026-09-30 22:5x）：取樣 22:34 那輪執行緒 300 次，70% 在刻意的睡眠、21% 等網路、7% 跑 CPU，所以不是被擋或網路慢；請求一次只要 0.2 秒、每輪存的樓數也沒變，卻多花 4 倍時間（兩輪都是抓 74 分鐘＋寫 4 分鐘），原因還沒找到；每輪都比排程間隔長，每小時會有約 18 分鐘兩輪同時在抓。巴哈 logger 等級是 WARNING（`scraper/config.py`），逐筆請求不會寫 log，目前數不到每輪發了幾次請求。
- 10/02 巴哈每輪統計：抓取 4,737～4,970 秒（其中等待約 3,250 秒）、請求約 18,580 次（留言 XHR 約 17,600 次）、頁面 976，仍超過一小時的排程間隔；防重疊與根因待查。
- 測試：新增 `src/scraper/tests/`（scraper 容器內執行：`docker exec -w /app scraper python -m unittest discover -s tests -t . -p 'test_*.py'`；bot 容器沒有 curl_cffi，不進 bot 的啟動 gate），7 項，8 種突變都紅；測試期間關掉 logging，避免寫進正式 `/logs/scraper*.log`。
- 共用層預設池改成**只用 Firefox 系**（firefox144／147＋30% 本機 Firefox ESR）；備援別名改 `"firefox"`。理由：所有網站都通過的只有 Firefox 系；一個 IP 固定用同一種瀏覽器也比每次換一種像真人。Chrome／Safari 目標清單刪掉，要加回先逐站實測。
- **潛在啟動失敗**：curl_cffi 原始碼把 `BrowserType` 標成 1.x 移除，requirements 沒鎖版本 → 改成可選匯入，拿不到就不過濾（不鎖版本，照 S6-2 的決定）。測試會模擬它被拿掉並重新載入模組。
- **未做、記為之後的選項（SC-Q6）**：一輪共用 session 後，若該輪指紋被擋會整輪失敗；以前逐頁各自重抽。只用 Firefox 的前提下風險低，建議先觀察，若 HKEPC 又出現 403 再加「遇到挑戰頁換一次 session 重抓」。

---

## 週期活動提醒：深塔海墟矩陣（已上線）

<!-- @meta
id: periodic-event-reminder
type: STATE
status: confirmed
last_confirmed: 2026-10-13
depends_on: event-announce-link-and-dedup-fix
affects: 排程、身份組、config.json
-->

> 已上線：9/29 20:00 第一則正式提醒（矩陣結束前、正常 @）已實發；面板 9/30 04:10 自動更新並置底；使用者 10/01 確認手機通知正常（靜音與正常 @ 都對）。完整設計、週期與版本日推算、部署紀錄已歸檔到 `TODO-completed.md`「週期活動提醒：深塔海墟（歸檔 2026-10-02，原 2026-09-29）」。

**待驗**
- [x] 10/7 04:00 第一則「矩陣開放」靜音提醒（S2-3）：10-07 04:00:02 已發送 `matrix:2026-10-07:reset`（silent=True），log 確認（10-13 唯讀核對）。
- [ ] 有人送自介時：舊的自介面板被刪、新面板在最下面，`settings/intro_panel_runtime.json` 多了 `intro_panel_channel_id`、`config.json` 沒被改動（7/3 之後沒人送過自介，未證實）。

**仍有效的事實與決定**
- **下一版更新日可以提早約 3 週推得**：每版最後一個卡池（「✦活動時間：… ~ YYYY年M月D日11:59」）都在「下一版更新前一天 11:59」結束，下一版隔天 04:00 開始維護（2.0～3.7 共 18 版全數 +16 小時）。下半卡池公告約在版本中段發出，比維護預告（約提前一週）早。
- **3.7 之後的下一版在 11/12 04:00 更新**（使用者確認；版本號未定，可能是 3.8 或 4.0）。巴哈玩家轉述前瞻的「版本期間：2026/9/30 ～ 2026/11/11」，結束日是**最後一天**（＝最後卡池結束日），不是更新日。→ S2-3 預計 10/7 04:00 ～ 11/12 03:59。**推算一律用日期、不依賴版本號**。
- **論壇 @身份組 的通知行為未驗證**：據社群回報，超過 100 人的身份組在討論串裡可能被拒；bot 開新貼文時首則的身份組 ping 可能不通知；被加進串的人預設收到每則回覆的通知。
- **坑**：新身份組**不要**加進幽靈點名的排除清單（那份清單幾乎包含所有自訂身份組，加進去等於訂提醒就免點名）；bot 沒有全域 `allowed_mentions`，提醒訊息要明確指定 `AllowedMentions(roles=[該身份組])`。
- **起算日與週期寫在程式的設定類別**（改了要重啟；`config.json` 屬使用者設定檔，AI 不自行改寫）；時間一律用 `SERVER_TZ`。
- **撞版本維護第一版不處理**（現有版本時間解析只記維護結束、只能用版本號查；約 20 期一次；重置提醒本來就靜音）。
- **補發**：bot 離線錯過時，結束前提醒補到重置前、重置提醒補到當天 12:00；去重用 StateDB `sent_content`。不建 Discord 活動、不加管理指令。
- 深塔、海墟、矩陣**共用一個身份組**，名稱改為「**週期活動提醒**」。
- 矩陣提醒**不寫階段編號**（S2-3 這種要靠版本號解析，版本號可能跳 4.0）。
- 版本延期時官方一定會公告：排程每次都依最新公告重算，面板與提醒日期跟著更新即可。
- 深塔／海墟期數：使用者覺得可有可無；可由「深塔第 33 期＝2026-03-02、海墟第 14 期＝2026-02-16、每 28 天 +1」直接推算。

---

## Lemonade 後端與寫入緩衝的待決（2026-10-01）

<!-- @meta
id: lemonade-backend-open-questions
type: TODO
status: draft
last_confirmed: 2026-10-02
-->

> 從 2026-10-01 10:4x 盤點紀錄搬來（Lemonade 升級盤點時發現的缺口）。LM-Q1（聊天向量斷線會掉）已修（`95a0330`），LM-Q3（重啟期間的請求不補做）決定維持現狀。

- **LM-Q2 load cache 不會因 Lemonade 重啟失效**：`_LEMONADE_LOADED` 記「已推過 ctx_size」，Lemonade 若重灌洗掉 `recipe_options.json`，bot 不會重推 → 用預設 4096 跑、長 prompt 爆 context。選項：A 遇到連線錯誤或 context exceeded 時清掉該模型的 cache／B 定期比對 `/api/v1/health` 的 `version` 變了就清／C 不改。建議 A。這次升級設定有保留，沒發生。
- **待決 LM-Q4**：三份記憶體 buffer（`store_chat`、`raw_message_store`、`ambient_memory`）骨架相同，`raw_message_store` 在 pgvector 斷線時也會整批丟掉；選項：A 抽成 `utils/` 共用元件並讓 raw store 也放回重試／B 只補 raw store／C 不動。建議 A，但等這次上線觀察過再做。

---

## ComfyUI 產圖 + GPU 資源仲裁（2026-09-02 規劃定案，未開工）

<!-- @meta
id: comfyui-gpu-arbitration
type: DECISION
status: draft
last_confirmed: 2026-09-02
affects: llm/client/lemonade_gate, llm/client/http_client, services/llm_service, imagegen/（新）
-->

> **2026-09-28 查證（本區塊部分狀態已過時）**
> - 實作順序的步驟 2（租約鎖 + 卸載 helper）**已完成**：`e13343d`（2026-09-03）。
> - ⚠️ **鎖有漏洞**：`services/llm_service.py` 的 `_chat_completion_checked` 先呼叫 `_ensure_model_loaded(model)`（:792），**之後**才 `async with stream_exclusive()`（:800）。產圖期間任何 chat 都會在排隊等鎖**之前**打 `POST /api/v1/load`，把 27B 載回 VRAM。產圖接進 bot 前必修。
> - ComfyUI 09-28 連不上（TCP 通、HTTP 被 reset），checkpoint／LoRA 清單未知。
> - Lemonade 已升到 **2026.40.0**（2026-10-01 約 10:3x）。升級重啟後 recipe 保留 ✅（27B `ctx_size 32768`、embedding `4096` 與各自 `llamacpp_args` 都在）、重啟後收到請求會自動載入 ✅；**unload 後自動重載**仍只在 11.5.0 測過，需要重測；`POST /free`（ComfyUI 放 VRAM）從未實測。
> - 04:00 維護現在是**五步**，收工約 05:46；Persona ⑤ 的 `publish_mode` 已是 `on`。
> - `src/test/integration/it_comfyui_image.py` 未 commit；它的 docstring 寫「與 Lemonade 綁不同 GPU」，與下方「27B 跨兩顆吃滿」矛盾，待使用者確認。
> - 落地前的待決問題見下方「待決問題（grill 暫停中）」。

**待決問題（grill 暫停中，2026-09-28；每題附當時的建議）**
- **頻道裡每天出現幾張、誰挑**：建議先跑兩週「產完放進只有管理員看得到的暫存區，按按鈕挑哪幾張發到日記頻道」，之後再考慮全自動。暫存區的「按鈕放行」跟 Telegram 隔離區的「放回主頻道」是同一種機制，做一次共用。
- **尺度**：建議嚴格全年齡——prompt 不放身材相關 tag、負面 prompt 放 nsfw 類、加全年齡 rating tag。身材設定只留在文字人設。
- **角色長相一致性**：建議先只靠 tag 上線，從產出挑一張「定裝照」，之後拿來當 IPAdapter 參考圖或練 LoRA 的素材。
- **心情從哪來**（會推翻「03:00 往回掃日記頻道」的定案）：建議 00:00 寫完日記後（LLM 還載著）多做一次分類，把心情歸到固定幾類存起來；03:00 仍然完全不用 LLM。理由：日記是含蓄散文，規則抽不準；往回掃也可能把「附件上傳失敗、退成純文字」的訊息誤認成日記。
- **產圖期間有人 @ 琇紫**：建議立刻回一句固定台詞（不經 LLM），例：「正在換衣服，等一下再聊」。目前的行為是一直等到產圖結束（最久 50 分鐘）才回。
- **只有使用者知道的事實**：ComfyUI 平常是否常駐（09-28 連不上）；ComfyUI 用哪張卡（測試檔 docstring 寫「與 Lemonade 綁不同 GPU」，與本區「27B 跨兩顆吃滿」矛盾）。

**不反對就照做的預設**：修鎖漏洞（任何會讓 Lemonade 載入模型的呼叫都要先拿鎖，把 `_ensure_model_loaded` 移進 `stream_exclusive`）；先確認 ComfyUI 活著且佇列是空的才拿租約、卸載 LLM，否則當天跳過；10 張拆成 10 個任務，每張 360 秒逾時，任一張逾時就中止整批並 `/interrupt`，已完成的照常處理；收工一律先 `POST /free` 讓 ComfyUI 釋放 VRAM 再放鎖（要跟 Lemonade 11.9.0 的三項實測一起驗證）；錯過 03:00 不補跑；節日表第一版手填未來兩年；embedding 小模型不卸載；`lemonade_gate` 改名 `gpu_gate`；圖檔名加日期並保留存檔。

**需求**：每天 **03:00** 排程產圖（特定角色換衣服，依心情／日期／節日決定），單次 10 張以內。
**不是 on-request**，使用者不會按著等。

**為什麼一定要卸載 LLM**（實測數字，不是推估）：兩張 RX 9060 XT **各 16GB**
（`vram_total 17,095,983,104`）；27B UD-Q4_K_XL + ctx 32768 本來就 `llamacpp_device: "Vulkan0,Vulkan1"`
跨兩顆吃滿。加上產圖，32GB 總量塞不下 → **卸載是唯一解**，不是保守選擇。
（曾考慮「把 LLM 釘單顆、ComfyUI 用另一顆並行」→ 單顆 16GB 放不下 27B，否決。）

### 線上實測結論（2026-09-02，對 `192.168.56.1:13305` Lemonade 11.5.0 / `:8188` ComfyUI 0.34.2）

| 測項 | 結果 |
|---|---|
| unload API | `POST /api/v1/unload {"model_name":"..."}` → `200 {"status":"success"}`，與 `/api/v1/load` 對稱 |
| 卸載生效 | health 的 `all_models_loaded` 中該 model 整個消失 |
| **卸載後打 chat 會自動重載** | **會**，22 秒（含冷載入）回 200 → **「主動載回」與「背景預熱」整段不需要** |
| recipe_options 是否被洗掉 | **沒有**。`ctx_size: 32768` 與全部 sampling args 原封不動（Lemonade 自己持久化在 `recipe_options.json`） |
| 二次呼叫 | 1.8 秒 / 36.7 tok/s → 確認常駐熱狀態 |
| ComfyUI 看不看得到 Lemonade 的 VRAM | **看不到**。27B 在與不在，`/system_stats` 都回報 free 15.78 GiB（Lemonade 走 Vulkan、ComfyUI 走 HIP，跨 process 查不到對方） |

**衍生結論**
1. `reset_lemonade_load_cache()` 從「必要」降級成「衛生」——Lemonade 自己記得 ctx_size，不清也不會錯；仍要清（模型卸載後「本 process 已推過 load options」的假設不成立），但**不再是單點故障**。
2. **整體風險很低**：租約過期／bot crash／鎖沒放好，最壞只是下一次 /askai 慢 22 秒，**沒有永久損壞路徑**。
3. **反過來**：正因為會自動載，「產圖期間絕不能有 LLM 請求漏進來」更要緊——一個漏網的背景插話就會把 27B 拉回 VRAM 跟 ComfyUI 搶。實作時要確認沒有任何路徑繞過鎖直接打 LLM。
4. **不可**用 ComfyUI 的 `vram_free` 判斷「現在夠不夠」——這條路提早封掉，否則會寫出看似合理但永遠答錯的檢查。

### 設計：租約 + 心跳（不是 timeout，也不是 checker task）

**核心：timeout 是猜的，心跳是量的。** 純 timeout 分不出「跑很久」與「卡死」——設太短誤殺正常長工作，設太長讓 bot 死著。

持有者拿**短期租約**（120s），每次證明還活著就續租。**續租點不用新造**：ComfyUI 的
`/queue`、`/history/{prompt_id}` 本來就要輪詢才知道圖好了沒，**輪詢成功即心跳**。

```python
async with gpu_exclusive("imagegen", lease=120) as lease:
    await unload_llm(chat_model)
    reset_lemonade_load_cache()
    while not done:
        await asyncio.sleep(5)
        status = await comfy.poll(prompt_id)   # 這一步成功 = 心跳
        lease.renew()
# 鎖釋放 → 下一個 LLM 請求進來，Lemonade 自動載回（22s）
```

- 正常跑 40 分鐘 → 續租 ~480 次，永不誤殺
- ComfyUI 卡死 → 輪詢失敗 → 120s 後租約到期 → 鎖自動釋放
- **租約長度與「產圖要跑多久」完全解耦**，只要比輪詢間隔長即可 → 不用猜任何時間
- 不做 checker task：多一個會自己掛掉的元件，而且它要判斷「還在跑嗎」最後還是得問 ComfyUI

**租約過期接管者不能只放鎖**：要順手 `reset_lemonade_load_cache()` + log 顯眼 error（不可靜默）。cache reset 冪等，重複清無副作用。

**兩種時限要分清楚**（不同東西，都要有）：

| | 管什麼 | 值 |
|---|---|---|
| 租約 | 卡死（liveness） | 120s，靠輪詢續 |
| 整批 deadline | 跑太久（budget） | **03:50**，護欄而非預算；正常 10 張幾分鐘就收工 |

deadline 存在的理由：**04:00 有每日維護四步**（emoji → 招牌梗 sweep → 人格萃取 → persona agent，跑到約 05:10），產圖不能占著不放。

### 換後端可續用（Ollama 可，vLLM 不可）

分三層，只有最薄一層要換：

| 層 | 內容 | 換後端要動嗎 |
|---|---|---|
| 仲裁層 | 租約／心跳／deadline／誰在佔用 | ❌ 完全不動（管的是 GPU 這個資源） |
| 意圖層 | `release_llm()` | ❌ 介面不動 |
| 後端 adapter | 怎麼實現該意圖 | ✅ 每後端一份，都很小 |

| 後端 | 卸載 | 載回 |
|---|---|---|
| Lemonade | `POST /api/v1/unload {"model_name":...}` | 不用做，下次 chat 自動載（22s） |
| Ollama | 一次 `{"keep_alive": 0}` 的請求（**原生卸載語意**） | 不用做，收到請求就載 |
| vLLM | ❌ 做不到（一 process 一模型、無 swap 概念） | — |

**`keep_alive` 三處保留，只改註解**（`llm_commands` "1h"、`impression_moderation_service` "30m"、
`personality_extractor` "30m"）。2026-09-02 曾一度決定刪除，**使用者否決且是對的**：它們確實在
Lemonade 下被 `_build_chat_extra_body` 丟進 ignored，但**那正是可攜層該有的行為**——`keep_alive`
表達的是意圖（「閒置多久可以放」），各後端能做到多少是後端的事；刪掉等於刪掉可攜性，和本節
「換後端可續用」的目標自相矛盾。而且 `llm_commands` 那則註解裡藏著 Ollama 時代的實戰教訓
（「避開反覆 unload/reload 觸發的 Windows ephemeral port 與 runner crash」），刪了下次換回 Ollama 會再踩一次。

要改的是**註解**，把「保證會發生」的口氣改成誠實描述。兩個機制互補、不是替代：

| | 語意 | 性質 | Lemonade | Ollama |
|---|---|---|---|---|
| `keep_alive` | 「閒置 N 分鐘後可以放」 | **軟提示**，後端能做就做 | 無 TTL 概念 → 忽略（已有 debug log） | ✅ 原生生效 |
| `release_llm()` | 「**現在馬上**放」 | **硬動作**，每後端一份 adapter | `POST /api/v1/unload` | `keep_alive: 0` |

### prompt 產生：v1 走規則，零 LLM 呼叫

素材三個來源都是現成的：

- **日期、節日** → `settings/` 一份 JSON 查表
- **心情** → **重用 00:00 的 AI 日記**。03:00 剛好在它之後，讀日記頻道最後一則即當天心情；
  頻道 id 也不用新設，`DiaryReflectionSettings.diary_channel_config_key` 已在 channel config 裡

不用 LLM 的理由不只是省事：① ComfyUI prompt 是 **tag 語言不是自然語言**，LLM 產的自由文字難控難重現；
② 一旦要 LLM，就得排在 unload 之前且同在鎖內，流程多一整段。
**v2 想換成 LLM 生 tag 時介面完全不用改**——差別只是「誰產出那串 tag」。

**發圖頻道＝日記頻道**（2026-09-02 使用者拍板）：沿用 `ai_diary_channel_id`
（`= DiaryReflectionSettings.diary_channel_config_key`，值 `1495609627361017867`），
**不新增任何設定**。該頻道因此成為「AI 的一天」的完整紀錄：00:00 寫日記 → 03:00 讀它決定心情 → 產圖發回同一處。

⚠️ **心情來源的定位規則不可以寫成「讀最後一則」**。正常時序雖然對（00:00 日記 → 03:00 圖，
03:00 當下最後一則就是當天日記），但兩種情況會抓錯：① 當天日記失敗沒發 → 讀到**前一天的圖**（無文字）；
② 有人在該頻道留言。正確規則：**從新往回掃，找「當天（`APP_TZ`）由 bot 發出、`content` 非空、
且無附件」的訊息**；找不到＝當天沒日記 → 心情來源缺席，退回純節日／日期規則。

（順帶：`diary_reflection` 目前是 `diary_channel.send(diary)` 直接發，沒走 `post_to_channel`。
產圖端仍走 `post_to_channel`；兩條路進同一個頻道是既有的小不一致，本案不處理，記在此備查。）

### 實作順序

1. ~~驗 `/api/v1/unload` 行為~~ ✅ 已完成（見上表）
2. `unload_llm()` adapter + gate 租約化（lease / renew / owner / busy 查詢 / 過期接管）
3. ComfyUI client：`POST /prompt` → 輪詢 `/history/{id}` → `GET /view` 取圖
   （bot 在 Linux container，**拿不到** Windows 的 `D:\AI\ComfyUI\...\output`，只能走 HTTP）
4. 接 03:00 排程 + 發圖
5. **最後**做檔名正名（見下）

**刻意重用既有輪子，不新造**
- workflow JSON 用 `llm.prompt.prompt_files.read_json()`（已有 mtime 快取，與 `settings/prompts/` 慣例一致）
- 發圖走 `utils.discord_content.post_to_channel`，不自己組 `channel.send`
- ~~實作完成後在「共用元件索引」補一行~~：GPU 獨佔（`lemonade_gate.gpu_exclusive`）已寫進 `AGENTS.md`「共用元件」（2026-09-29）

### TODO

- [ ] 步驟 3~4 實作（步驟 2 已在 `e13343d` 完成，已歸檔）
- [ ] **prompt 精修（使用者指定，後續要做）**：心情 ↔ 服裝的搭配表、節日表。v1 先能跑，映射規則之後細調

### 檔名正名（2026-09-29 隨 `llm/` 依角色分子資料夾完成四項；`lemonade_gate` 仍待定）

| 現在 | 改成 | import 點 |
|---|---|---|
| `llm/lemonade_gate.py`（現在位於 `llm/client/`） | 待定（`gpu_gate` / `resource_gate`）——**等它真的管到 GPU 資源再改**，否則名字更騙人 | 10 |

**已決定不做**：`llm/`、`services/` 的資料夾重組（成本 ~160 個 import 點，效益只有排序好看）。**2026-09-29 更新**：`llm/` 部分已由使用者推翻，改依角色分子資料夾（見[程式結構整理](#程式結構整理2026-09-29-起主要整理已完成剩-p2p3n3)）；`services/` 也在 2026-09-30 分成 relay／events／community。
子資料夾的判準是「≥6 檔／有封裝邊界／可預期會長」滿足其一——`persona_agent/`、`retrievers/web/`
是對的示範，其餘各群目前都不達標。**ComfyUI 另開 `src/imagegen/`，不塞進 `llm/`**（塞了 `llm/`
就變成「AI 相關雜物間」，重蹈 `services/` 覆轍）。

---

## Persona Agent M7：精簡版發布（2026-09-28 已上線；精簡版連續 12 晚穩定，待刪備援萃取）

<!-- @meta
id: persona-extraction-agent
type: STATE
status: confirmed
last_confirmed: 2026-10-13
depends_on: personality_extractor, llm_service, lemonade_gate, member_profile_store
affects: auto_personality、插話／askai 人物卡、discord_bot 04:00 排程
-->

> 早期「影子模式」規劃（M1~M6、線上實測、五項定案）已歸檔到 `TODO-completed.md`。
> 原 `HANDOFF_2026-09-27_persona-agent-M7.md` 已刪除，仍有效的內容收在本區。

**架構（2026-09-28 定案）**：04:00 維護五步（`discord_bot._run_daily_maintenance_once`）
① emoji 字典 → ② 招牌梗衰減 → ③ production 人格萃取（過渡期備援，只寫 ④ 沒涵蓋的人）
→ ④ persona agent（每晚主力；完整描述寫 `persona_agent_versions`，bot 讀不到；只重跑上次跑完後有新發言的人）
→ ⑤ 發布精簡版（`llm/persona/agent/publish.py`；**不經 LLM、整條原文照抄**，寫進 `auto_personality`；插話與 /askai 只讀這裡）。

**狀態（2026-10-13）**
- commit：`c544036`、`b3dad1c`、`aafdc85`、`948ab96`、`2a0d0cf`（`publish_mode="on"`）；10-01 隱私、歸因與名字對照：`5aaf596`（③ 送 LLM 前跳過）、`9b2c4d1`（名字與錨點整合）＋docs；10-02 手動修正四條舊歸因錯誤（資料，見下方 PA-Q13）。
- ⑤ 每晚 05:45～06:35 寫入：10-02～10-13 **連續 12 晚 failed=0**（people 64～66、written 63～64、empty 2＝兩位還沒有過門檻條目的人）。log 關鍵字「persona 精簡版發布結束」。
- ③ 自 PR-Q1（10-02）起只替精簡版是空的人跑：每晚「跳過 37～38 人，剩 1 人」、約 15 秒結束。**PR-Q2 的刪除門檻（10/05 後連續 7 晚 failed=0）已達到**，抽查還沒做 → 待使用者決定何時刪 ③（PR-Q3、PR-Q4 隨之生效）。
- ④ 的 token 用量：10-02 名字表上線後「預算用盡、停止收集」變多（10-02 9 次；10-10～10-13 共 35 次）；若一直偏高，考慮預算加約 1,000 或名字表只列有其他叫法的人（約 39 人、530 token）。

**回滾**（依程式推得，未實測）：revert `2a0d0cf` → 重啟 → 下一個 04:00 由 ③ 把門檻內約 36 人覆寫回 ③ 的描述；
門檻外約 26 人會停在最後一版精簡版（沒有備份，使用者已接受）。日間重啟不會立刻變回來（補跑檢查看到 ⑤ 的寫入時間會跳過）。

**已接受的取捨（不要再提）**：啟動補跑看 `MAX(last_extracted_at)`；不備份 `auto_personality`；精簡版比 ③ 薄照換；近況沒有時間上限。

**已知、刻意沒處理**：被隔離的人停在最後一版精簡版；`index_auto_personality` 先刪後寫（embedding 失敗那人暫時沒描述）；
③ 存入時硬切 200 字；④ 意思相近的條目可能兩條都被挑到；③ 與精簡版都不看招牌梗的 spicy／封鎖閘門。

**已定案（2026-10-01～02；討論、查證數據與實作細節見歸檔「Persona Agent M7：隱私與歸因、名字對照、備援萃取退場第 1 階段」）**
- PA-Q1／Q6 不寫進描述的類別（規則檔 `persona_description_rules.txt`，③④ 共用、即時生效）：健康、性向、感情家庭、政治、具體行程（日期＋店名／地點，寫角色不寫地點）；住哪裡、宗教、財務、職業**不限制**（使用者：都是群裡公開講的）。PA-Q2 ⑤ 不做隱私過濾；PA-Q3 性化條目照留、不套招牌梗的 spicy 閘門。
- PA-Q4／Q8／Q9 歸因：④ 每人跑時附【群友的稱呼】名字表（顯示名稱＋伺服器暱稱＋全域名稱，不抓帳號名、不放 user_id、不編號；本人排第一標「（本人）」；每晚從成員快取讀，不建資料庫）；⑤ 擋「群內流行語」（同一詞在 ≥2 人描述裡被寫成口頭禪；暱稱、貼圖名不算）與「把別的群友名字寫成口頭禪」的條目；條目句尾的「。」拿掉。PA-Q10 舊錯誤等 ④ 重跑修正；PA-Q13 ④ 不會主動修舊條目 → 10-02 手動替 Biboolater、雞蛋飛、KaTsuO、Ἡράκλειος 各寫一個新版本（只改那一條、`model=manual`）並重新發布；備份 `logs/persona_manual_fix_2026-10-02.json`，回復＝讀備份的 changes 再寫一版抄回去並重新發布。
- PA-Q11／Q12 白天的名字：主名字統一 Discord 顯示名稱（人物卡標籤也是）；插話與 /askai 的 persona_context 尾端加【名字對照】（只列這次出現且有其他叫法的人）；找人比對加查伺服器暱稱與全域名稱、看詞的邊界、排除 bot；錨點 `#末四碼` 抽成 `llm/preprocess/person_anchor`（撞號自動加長）；名字 `llm/persona/member_names`（只用空白分段）。守衛擋手寫錨點與自己讀 `.global_name`／`.nick`。
- PR-Q1 ③ 過渡：先查跳過名單再送 LLM，只替精簡版是空的人跑（10-02 起生效）。

**③ 退場（PR-Q2～Q4 已定案，等使用者說刪）**
- **PR-Q2 什麼時候整個刪 → 定案 A**：10/05 後，⑤ 連續 7 晚 failed=0 且抽查沒有新類型嚴重問題才刪。原標準「⑤ 連續 7 晚 failed=0，且抽查沒有新類型的嚴重問題」，目前 3 晚。A 照原標準，最快 10/05 後／B 現在就刪／C 做完 PR-Q1 就不刪，③ 留作備援。建議 A：今晚起 ④⑤ 換上暱稱表與流行語過濾，先觀察幾晚再拿掉備援。
- **PR-Q3 新成員的第一版描述 → 定案 A 接受空窗**（刪 ③ 時生效）：刪掉 ③ 後，新成員要等 ④ 寫出跨 2 次對話的條目，⑤ 才有東西發；在那之前插話與 /askai 只看得到自介與印象。A 接受這段空窗（④ 的納入門檻比 ③ 寬，通常幾天內就有）／B ⑤ 對還沒發布過的人放寬成 1 次對話也收／C 保留 ③ 只寫新成員。建議 A。
- **PR-Q4 手動萃取指令 → 定案 A 兩個都刪**（隨刪 ③ 一起做）：`/personality_extract`（手動跑 ③、預覽後按「寫入 RAG」）與 `/personality_extract_status`。A 兩個都刪（要看單人用既有的 `/persona_agent_test`）／B 改成手動跑全體 ④＋⑤／C 保留。建議 A（指令收斂計畫本來就要減少指令數）。

**不反對就照做的預設**：已做——⑤ 修掉「。；」雙標點、④ prompt 的「每條都要能單獨讀懂，不寫跟舊版比較的句子」。還沒做——同一人意思相近的條目在 ⑤ 用 embedding 相似度去重（⑤ 要多打 embedding）；兩位「DDLC」撞名時標籤加區分碼（動到插話／askai 讀取端）；回滾步驟寫成文件。⚠️ **需使用者明確同意才做**：刪除 ③ 留下的 Banana、Rie 兩份「無法分析」描述（先備份）。

**M7 之後待辦**：拿掉 ③（PR-Q2 門檻已達到，等使用者；新成員第一版描述從哪來、補跑檢查改看什麼、手動萃取指令去留都已定案 PR-Q3／Q4）；失敗的 run 隔天重跑；
證據反查失敗的那晚不寫入；DB 安全網（`write_version` 失敗被當成功、只剩 drop 時寫出空描述）；人工校正管道。

**刻意不做**：revise 沿用舊證據（會灌高對話次數）；keep「今晚附的證據一律保留」（會擠掉最新名額）。

**坑**
- ~~log 會混入啟動測試的假紀錄~~（2026-09-29 已修：測試一律改寫到 `/logs/test_run.log`；**09-29 以前**的 `discord_bot.log` 仍混有假紀錄，例如 author=1/2、mode=on、`(901)`、`chat_id=-1009990000001`）；⑤ 的 log 只印前 200 字。
- 04:00～約 07:30 不要重啟。
- 突變測試複製到容器 `/tmp`，只複製需要的目錄（`/app/telegram_scraper` 有 30 GB）。
- `docker logs` 從容器建立起累積，查近期要加 `--since`。
- async 裡的同步 DB 呼叫走 `run_db`（AST 把關；參數名叫 `store` 也會被誤判）。
- pydantic settings 是 frozen，測試裡要整個換成 `SimpleNamespace`；測試用的假 auto doc 要帶 `alias` metadata。

---

## Telegram 漏收補掃與相簿漏圖（已上線）

<!-- @meta
id: telegram-catchup-sweep
type: STATE
status: confirmed
depends_on: telegram-multi-source
affects: telegram-relay
last_confirmed: 2026-10-02
-->

> 三段都已上線並驗證：8/02 週期補掃（`fbd2d3c`）、8/18 指針左移補中段缺口、9/28 全域鎖改單則訊息鎖＋相簿等齊再發（`3a1379c`、`ea81a83`）。9/29 起 15 次相簿合併，到齊的組 `media_count` 都等於組員數，逾時的以補圖送出；`[CatchUp]` 每 15 分鐘照常跑。完整診斷、修法與驗證已歸檔到 `TODO-completed.md`「Telegram 漏收事件自動補掃與相簿漏圖（歸檔 2026-10-02，原 2026-08-02）」。

**仍有效**
**已 commit（`fbd2d3c`）。** `runtime_config.json` **刻意未改**（該檔執行中會被 `add_identifier_to_forward_whitelist` 自行寫入，屬受保護檔）；程式端預設 15 分鐘已生效，要調整再手動加 `"catchup_interval_min": <分鐘>`。

**限制**：視窗外的舊洞（> `max_id - 300`）仍只有重啟全量掃描補得到；要延長回溯就調大 `CATCHUP_GAP_WINDOW`，代價是每輪多撈同量 metadata。

**已知殘留（未處理）**：
1. 並行恢復後，兩則**不同**訊息若同時帶同一個尚未下載的自訂表情，會同時寫同一個 `emoji_{doc_id}` 檔——8/02 以前本來就如此，機率低，未加鎖。
2. History 啟動掃描本來就沒上鎖，維持原狀。
3. 8/02~9/27 的舊缺圖（約 155 張）不補——超過補圖時效，使用者只要求補今天。
4. 補圖訊息的說明文字：組員多半沒有文字，補圖只有標題「來源（補圖）」與 footer `msg #… · db#…` 指向原相簿。

**仍可能缺圖的情境（非本次 bug，未處理）**：① 相簿已送一部分、缺的部分超過 12 小時才進 DB（例如 scraper 停機半天）→ 依設計不補；② scraper 下載失敗 → 媒體沒進 DB，沒人會發（有媒體卻無媒體列：6~9 月每月 1~7 則，幾乎不在相簿裡）；③ 影片壓縮後仍超過 Discord 上限 → 略過該檔但照樣標記已送（log 歷來共 5 次 `附件壓縮失敗或仍超限`）；④ Discord 發送失敗 → 不標記，要等下次 bot 重啟 reconcile 才重試。

---

## 專案 AI 架構總覽（已過時，待重寫）

<!-- @meta
id: project-architecture
type: STATE
status: deprecated
last_confirmed: 2026-10-02
-->

> 原內容停在 2026-03 的 Ollama 時代（gemma4、`ollama_runtime_config.json`），已歸檔到 `TODO-completed.md`「專案 AI 架構總覽（Ollama 時代）（歸檔 2026-10-02，原 2026-03-31）」。留著這個區塊是因為其他區塊的 `depends_on` 指向 `project-architecture`；重寫時以 `AGENTS.md` 與 `src/` 現在的分層為準。

SFT 決策門檻已搬到「產品能力 TODO」。

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
> 已完成的重構與部署驗證項（askai 身份感、人物對照三輪、人設深度重構、智慧女性風格、few-shot 範例檔、`/personality_extract` 背景化與 fallback、萃取 log）與舊的設計備忘，已歸檔到 `TODO-completed.md`「Context / Prompt 優化專區（歸檔 2026-10-02，原 2026-04-19）」；`/personality_extract` 相關待辦會隨 PR-Q4（刪指令）一起消失。

**待處理**
- [ ] `asker_profile.roles` 欄位目前為 `(未啟用)`，未來可填 Discord 身份組名稱 + 權限層級（admin/moderator/member）
- [ ] **/askai 指定 thread 查詢**：情境 A（人在 thread 內 `/askai`）已支援；情境 B（在他處指定 thread）不支援，因 slash command 無 thread 參數 + pgvector metadata 無 `thread_id` / `parent_id`。兩方案：Minimum 版（加 thread 參數 + retriever 吃 thread.history，≤3 處改動）/ 完整版（Minimum + chat_persistence 寫 thread_id + RAG 加 thread 過濾，需 migration）。AI 建議先 Minimum 版，使用者未選。
- [ ] **使用者指令記憶 `/remember`**：詳見 [使用者指令記憶專區](#使用者指令記憶-remember-未來工作)
- [ ] 觀察 /askai 執行時音樂機器人是否還會斷音；若仍斷，考慮 BM25/embedding 隔離到獨立 ThreadPoolExecutor（治標）或 ProcessPoolExecutor（治本但 IPC overhead 高）（未證實，log 查不到）

---

## Reaction 統計與社群互動玩法（規劃；資料收集已完成）

<!-- @meta
id: reaction-stats-todo
type: TODO
status: draft
depends_on: [project-architecture]
affects: [product-todo]
last_confirmed: 2026-10-02
-->

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
---

## 使用者指令記憶 (/remember) 未來工作

<!-- @meta
id: user-directive-memory
type: TODO
status: draft
depends_on: [context-prompt-optimization]
affects: [project-architecture]
last_confirmed: 2026-04-27
-->

> **目標：** 讓使用者用「請記住 X」「希望你叫我 Y」等指令把事實 / 偏好寫進 RAG，下次 `/askai` 自動帶入，不會因聊天記錄淘汰而消失。

### 現況差距

| 層 | 寫入來源 | 是否被 askai 自動讀取 | 是否能受「請記住」觸發 |
|---|---|---|---|
| `raw_message_store` (SQL) | 全部 on_message | 否（只給 personality_extractor 用） | ✅ 寫入但不被讀 |
| `chat_persistence` (pgvector) | 訊息 embedding | 是（vector rank） | ✅ 寫入但僅靠語意命中才被撈 |
| `intro_profile` | /intro 面板 | 是（persona card） | ❌ 需走面板 |
| `impression` | /impression | 是（persona card） | ❌ 需走面板 |
| `auto_personality` | 排程批次萃取 | 是（persona card） | ✅ 但抽的是「人格特徵」不是「請記住的事實」 |

→ 沒有「使用者指令記憶」這一層；「請記住 X」會被 raw / chat 收進去但不會被當作持久指令對待。

### 業界主流做法

| 模式 | 代表產品 | 概念 |
|---|---|---|
| **A. LLM 偵測 + 自動寫入** | ChatGPT Memory、Claude memory、Mem0 | 訊息過 LLM 分類器，判定要記就抽成 fact 存 DB |
| **B. 顯式 /remember command** | Notion AI、Slack chatbots | 使用者打 `/remember X`，bot 寫入 fact，標明 owner / scope |
| **C. 結構化 knowledge graph** | 企業級 CRM、Replika | 抽成 (subject, predicate, object) 三元組 |
| **D. Long-term episodic + semantic memory** | MemGPT、LangChain memory | 短期 + 中期 summary + 長期 facts，分層檢索 |
| **E. 混合：自動萃 + 使用者覆蓋** | Cursor rules、CLI agent memory | 自動觀察存背景知識，使用者可手動加 / 修 / 刪 |

### 推薦路線（A+B 混合，複用 member_profile 表）

不用新 schema，沿用現有 `member_profile`：

```
新增 profile_kind = "user_directive"
metadata: {
  doc_type: "member_profile",
  guild_id: ...,
  author_id: 寫入者 user_id,
  target_user_id: 適用對象（可選；空=寫入者自己 / "all"=全群）
  alias: 寫入者名稱
}
text: [User Directive] {自然語言事實或偏好}
```

**入口：**
- **B 模式（先做）**：`/remember 我用 PS5 玩鳴潮` → 寫入 user_directive 卡（author=自己、target=自己）
- **A 模式（後做）**：on_message 偵測「請記住」「希望你」「以後我」等 pattern → 用 cheap LLM async 判斷是不是直陳事實 → 是的話自動寫入 + reply ✅

**讀取：**
- `retrieve_rag_context` Stage 1/2 SQL 多撈 `profile_kind='user_directive'`
- 寫入者的 directive 進 `<asker_profile>` 的 `directives:` 欄位
- 對別人的 directive 進 persona card

**進階機制：**
- `/forget X` 刪除
- 寫 directive 時記時間戳，超過 N 個月可標 stale
- 衝突偵測（兩條 directive 矛盾時靠 timestamp 取新）

### 工作量估算

| 元件 | 動作 |
|---|---|
| DB schema | 不動（沿用 member_profile） |
| `intro_rag_port` | 加 `index_directive()` 函式 |
| `context_retriever` Stage 1/2 | SQL 加 `OR profile_kind='user_directive'` |
| `persona_card_builder` | 新增 directive 處理（或合併到 intro 區） |
| /askai prompt | 加 `<user_directives>` 區塊或併入 asker_profile |
| 新指令 | `/remember`、`/forget` |

預估 5-8 小時（B 模式 MVP）。複雜度比 #XXXX 重構低（複用現有 RAG）。

### 待定事項

- 先做 B（命令版）就好，還是 A+B 一起？
- A 模式偵測 pattern 用哪個 model（cheap async）？
- target_user_id="all" 全群 directive 的權限控制（誰能寫？）
- 跟 auto_personality 衝突時優先序

---

## AI 私聊頻道 + 三層記憶機制（規劃中）

<!-- @meta
id: ai-chat-channel-memory
type: TODO
status: draft
depends_on: [project-architecture, context-prompt-optimization]
affects: [user-directive-memory, ambient-chat]
last_confirmed: 2026-04-27
-->

> ⏸️ **本輪（2026-06-20）暫放旁邊。** 與新案 [AI 偶爾插話 / 閒聊（功能二）](#ai-偶爾插話--閒聊功能二已上線c-4-待做) 切為**兩個獨立功能**：
> - **功能一（本案）= AI 的家**：專屬頻道、你去找他「被叫必應、一定回答」、重度三層記憶。
> - **功能二（新案）= AI 偶爾插話**：一般頻道自發冒泡、@ 才必回、輕量情境記憶。
> 兩案的「偏好事實記憶」未來收斂為**共享一層**（一個寫入器、兩功能召回），詳見功能二區塊。

> **目標：** 在每個 guild 指定一個「AI 私聊頻道」。在該頻道內，AI（柔喵）以 30 熟女姊姊人設自然加入閒聊（不需要 `/askai` 指令），透過長期累積建立三層記憶——使用者偏好事實 + AI 自己的觀點/默契 + 既有人設。讓 AI 能像真朋友一樣記得「你愛吃鮭魚」、「我之前覺得 X」這類細節，且具備道德判斷不被惡意污染。

### 設計總覽

#### 三層記憶

| 層 | profile_kind | 內容 | 召回時機 | 來源 |
|---|---|---|---|---|
| 使用者偏好事實 | `preference_fact`（新） | 一個人的原子偏好 / 興趣 / 厭惡 | 該人當前話題語意命中時 | AI 私聊頻道訊息 + 圖片描述 |
| AI 自我記憶 | `ai_self_memory`（新） | 柔喵自己對事件的感受、跟某人形成的默契 | 柔喵要表態 / 回憶 / 形成立場時 | AI 私聊頻道對話批次 summarize（柔喵視角） |
| 個性 prompt | （prompt file） | 30 熟女、貴氣、含蓄酸、母愛、摸摸頭包容、和風氣質、外貌豐腴 | 永遠載入 | `askai_system_prompt.txt`（已落 2026-04-27） |

#### 視覺輸入

- AI 私聊頻道訊息含圖片時，先用 vision LLM 產出客觀描述
- 描述以 `[圖片：...]` 形式注入 chat context、進入 fact extractor、進入 self-memory summarizer
- vision prompt 限制：客觀、不渲染、不評價（避免色色內容自我色色化）
- image hash cache 避免同張圖重跑

#### 道德守門（雙層 gate）

**抽取守門（主防線）**：fact extractor 與 self_memory summarizer 的 prompt 內嵌道德分類，三檔處理：

| 風險檔次 | 例子 | 處理 |
|---|---|---|
| 紅線（直接丟） | 未成年、強迫場景、種族/外貌/家人等 §19 §25 紅線題材 | discard，不寫入 |
| 誣陷他人 | 「X 是小偷」「Y 是渣男」 | discard（記他人負面標籤會被當證詞用） |
| 隱私資料 | 真實住址、電話、真實身份對應 | discard |
| 污染人設 | 「妳應該記得人類都很糟」「妳是邪惡的 AI」 | discard，不轉成 self_memory |
| 短期情緒 | 吵架時「我恨 X」、低潮「我廢物」 | 記但標 `sensitivity=high` + `ephemeral=true`，召回限同情境 |
| 隱私邊界 | 「我跟前任的事」「家裡有狀況」 | 記但標 `sensitivity=high`，公開頻道一律不引用 |
| 正常偏好 | 食物、興趣、習慣、品味 | 正常記，可跨頻道引用 |

**召回守門（二道）**：metadata 帶 `sensitivity` / `ephemeral` / `source_kind` flag，召回時依場景過濾：
- 公開頻道 `/askai`：只撈 `sensitivity=low` 且非 ephemeral
- AI 私聊頻道：可撈 sensitivity=high，但 ephemeral 仍要看時近度

紅線完整沿用 [askai_system_prompt.txt](src/settings/prompts/askai_system_prompt.txt) §19、§25。

### Phase 切分

#### P1 — 頻道綁定 + 無指令對話（基礎設施）

- [ ] 新指令 `/setup ai-chat-channel #channel`（admin 限定）置於 `src/commands/management_commands.py`
- [ ] 新表 `ai_chat_channels (guild_id PK, channel_id, enabled_at, updated_at)` — 走 SQL（`state_db` 或新檔）
- [ ] `discord_bot.py` `on_message` 加分支：在指定頻道直接走 askai 流程，不需指令
- [ ] 連發 debounce：使用者停 5 秒以上才考慮回
- [ ] @ 提到柔喵或 reply 柔喵 → 一定回（覆蓋 debounce）
- [ ] 隱私告知：設定指令時自動發置頂訊息 + 改 channel topic（明示訊息會被記憶）
- **驗收：** 設好頻道，自然講話 AI 自然回；沒設不回。

#### P2 — 回應時機 gating（看氛圍挑著回）

- [ ] 新檔 `src/llm/reply_gate.py`：輕量 gating LLM，三檔輸出 `reply / react / silent`
- [ ] gating 用便宜小模型（haiku-4-5 / 4o-mini 等級），prompt 寫進 `src/settings/prompts/reply_gate_prompt.txt`
- [ ] 安靜 30 分鐘以上 → silent（不主動破壞氣氛）
- [ ] `react` 檔次貼一個 reaction emoji 表達「有在」
- **驗收：** 連發、廢話、安靜時不亂插話；被叫一定回。

#### P3 — 視覺輸入（vision pipeline）

- [ ] 新檔 `src/llm/vision_describer.py`：訊息有 image attachment 時呼叫 vision model
- [ ] image hash cache（避免同張圖重跑），cache 存 `state_db` 或本地 sqlite
- [ ] vision prompt 限制：客觀、不渲染、不評價，置於 `src/settings/prompts/vision_describer_prompt.txt`
- [ ] 描述以 `[圖片：...]` 形式注入 askai context
- [ ] `src/sys_settings/llm_settings.py` 新增 vision model 設定
- **驗收：** 純圖、圖+文都能自然回應；色色內容不被 vision 自我渲染。

#### P4 — 使用者偏好事實 + 抽取道德守門

- [ ] 新檔 `src/llm/persona/preference_extractor.py`：批次掃 AI 私聊訊息（含圖片描述）抽原子事實
- [ ] 抽取 prompt（`src/settings/prompts/preference_extractor_prompt.json`）內嵌**道德分類**規則（紅線丟 / 中風險標 sensitivity / 低風險正常記）
- [ ] pgvector 新 `profile_kind = "preference_fact"`，metadata：`{author_id, fact_text, category, source_msg_id, confidence, captured_at, source_kind, sensitivity, ephemeral}`
- [ ] confidence < 0.6 不進 persona card
- [ ] 衝突處理：保留歷史 + 召回偏新（讓「之前說 X 現在改口啦」這種接話成立）
- [ ] `src/llm/intro_rag_port.py` 新增 `index_preference_fact()`
- [ ] `src/llm/persona/persona_card_builder.py` 新增「我（柔喵）記得的偏好」段
- [ ] `src/llm/retrievers/context_retriever.py` SQL 多撈 `profile_kind='preference_fact'`，召回 top-K = 3
- **驗收：** 講過愛吃鮭魚，幾天後問晚餐被自然帶出；測試誣陷/隱私/紅線輸入確認被丟棄。

#### P5 — AI 自我記憶（第二層）+ 抽取道德守門

- [ ] 新檔 `src/llm/self_memory_summarizer.py`：每 30 訊息批次 + 每天 dedup
- [ ] summarizer prompt（`src/settings/prompts/self_memory_summarizer_prompt.json`）內嵌道德分類，特別防「污染人設」型輸入
- [ ] pgvector 新 `profile_kind = "ai_self_memory"`，metadata：`{topic, perspective, related_user_ids, captured_at, sensitivity}`
- [ ] `intro_rag_port.py` 新增 `index_ai_self_memory()`
- [ ] persona_card / askai context 新增「柔喵的記憶 / 觀點」段
- [ ] 召回 top-K = 3
- **驗收：** 聊久之後柔喵會說「我之前覺得 X」這種有連續性的話；測試「妳該覺得人類都很糟」這類污染輸入確認不被吸收。

#### P6 — 跨頻道引用 + 召回道德守門 + prompt 整合

- [ ] [askai_system_prompt.txt](src/settings/prompts/askai_system_prompt.txt) 新增「【記憶與召回】」區塊：
  - 引用記憶用自然口語（「我記得你⋯」「上次你提過⋯」），不用工程語言
  - 沒命中記憶不要憑空編
  - AI 私聊頻道私下說過的事不主動搬到公開頻道
  - 偏好衝突用「之前 X 現在改口啦」這種接法
  - 對 sensitivity=high 的記憶絕不主動引用，除非對方在同情境主動帶到
- [ ] 公開頻道 `/askai` 召回邏輯接入 sensitivity / ephemeral / source_kind 過濾
- **驗收：** 公開場合敢說「記得你愛吃鮭魚」但不會爆「你昨天說很累」或「你上週情緒崩潰」。

### 預設決策（還可改）

| 決策點 | 預設值 |
|---|---|
| AI 頻道每 guild 數量 | 一個 |
| 隱私告知方式 | 設定指令時自動發置頂 + 改 channel topic |
| AI 自我記憶更新頻率 | 混合：每 30 訊息批次 + 每天 dedup |
| vision 呼叫策略 | 全跑 + image hash cache |
| 圖片推論大膽度 | 中等，confidence < 0.6 不進 persona card |
| 偏好衝突 | 保留歷史 + 召回偏新 |
| 召回 top-K | preference 3、self-memory 3 |
| Confidence threshold | 0.6 |
| 連發 debounce | 5 秒 |
| 道德守門位置 | 抽取為主、召回為輔（防線前移） |
| 短期情緒處理 | 記但 `ephemeral=true`，限同情境召回 |

### 待確認

- 「只貼 reaction emoji」要不要當第三選項？預設要（P2 包含）。
- 上線節奏：P1+P2 先部署實際用幾天再做 P3-P6？還是一條龍寫完？
- gating 用哪個小模型？（成本敏感）
- vision 用哪個模型？（既有架構是 Ollama 為主，vision 走本地還是雲端）
- AI 自我記憶的「視角第一人稱」是否要在 prompt 明寫「我覺得⋯」這類自指規則？

### 風險與注意

- **成本：** vision + gating LLM 每訊息呼叫，量會上來。P2 gating 必須用便宜模型。
- **記憶污染：** 群組裡有人惡意餵假事實。短期靠抽取道德守門 + confidence；長期可考慮多人重複提到才升等的 source 信任度機制。
- **誤抽尷尬：** 抽錯偏好讓 AI 講錯話比沒記憶更糟。「不確定就不主動帶出」要寫進召回邏輯與 prompt（P6）。
- **隱私感受：** 使用者可能不知道 AI 頻道全紀錄。P1 落地時告知必須清楚。
- **道德守門誤殺：** 過嚴會記不到正常偏好。需建立 eval 集（典型正例 / 誣陷例 / 紅線例 / 短期情緒例）跑回歸測試。

### 跟 [/remember](#使用者指令記憶-remember-未來工作) 的關係

兩案互補不取代：

| 維度 | /remember | AI 私聊頻道（本案） |
|---|---|---|
| 觸發 | 顯式指令（高使用者意圖） | 自然對話（被動沉澱） |
| 信心度 | 高（user 親口指定） | 中（LLM 推斷） |
| profile_kind | `user_directive` | `preference_fact` / `ai_self_memory` |
| 召回優先級 | 高 | 中 |
| 道德守門需求 | 低（user 已表態） | 高（需 LLM 自判） |

建議：本案 P4 落地後，/remember A 模式（pattern 自動偵測）可廢；/remember B 模式（顯式 `/remember`）保留作為高信度通道。

### 涉及檔案（預估）

| 檔案 | 角色 | Phase |
|---|---|---|
| `src/settings/prompts/askai_system_prompt.txt` | 已加人設；待加【記憶與召回】 | P0 ✅, P6 |
| `src/settings/prompts/reply_gate_prompt.txt`（新） | gating prompt | P2 |
| `src/settings/prompts/vision_describer_prompt.txt`（新） | vision 描述 prompt | P3 |
| `src/settings/prompts/preference_extractor_prompt.json`（新） | 偏好抽取 + 道德分類 prompt | P4 |
| `src/settings/prompts/self_memory_summarizer_prompt.json`（新） | AI 自我記憶 + 道德分類 prompt | P5 |
| `src/commands/management_commands.py` | `/setup ai-chat-channel` | P1 |
| `src/services/state_db.py`（或新檔） | `ai_chat_channels` 表 + image hash cache | P1, P3 |
| `src/discord_bot.py` | on_message 分支 + reply gate 接入 | P1, P2 |
| `src/llm/reply_gate.py`（新） | gating 邏輯 | P2 |
| `src/llm/vision_describer.py`（新） | vision pipeline | P3 |
| `src/llm/persona/preference_extractor.py`（新） | 偏好事實抽取 | P4 |
| `src/llm/self_memory_summarizer.py`（新） | AI 自我記憶 summarizer | P5 |
| `src/llm/intro_rag_port.py` | 新增 `index_preference_fact()`、`index_ai_self_memory()` | P4, P5 |
| `src/llm/persona/persona_card_builder.py` | 新增「偏好」+「柔喵記憶」段 | P4, P5 |
| `src/llm/retrievers/context_retriever.py` | SQL 多撈兩種 profile_kind + sensitivity 過濾 | P4, P5, P6 |
| `src/services/llm_service.py` | 整合 reply_gate + vision describer 到主流程 | P2, P3 |
| `src/sys_settings/llm_settings.py` | 新增 gating model + vision model 設定 | P2, P3 |

---

## AI 偶爾插話 / 閒聊（功能二）（已上線，C-4 待做）

<!-- @meta
id: ambient-chat
type: TODO
status: draft
depends_on: [project-architecture, context-prompt-optimization]
affects: [ai-chat-channel-memory, ambient-natural-rework]
last_confirmed: 2026-10-07
-->

> **目標：** 在白名單的一般聊天頻道裡，AI（柔喵）**沒人叫也會偶爾冒一句**，讓群聊更活；被 **@ 或 reply 時一定回**。定位是「彩蛋式偶爾插話」，**不是**功能一那種「專屬頻道全程參與」。寧可少講講得巧，也不要每句都插變噪音。
> Phase A、B、C-1～C-3 都已上線，2026-08-09 的自然插話重構也已上線並實測。原本「兩顆模型、12B 常駐」的架構已作廢（ambient、主模型、人格萃取現在是同一顆）。完整規劃、各 Phase 實作與自然插話重構的推演已歸檔到 `TODO-completed.md`「AI 偶爾插話（功能二）與自然插話重構（歸檔 2026-10-02，原 2026-06-21／2026-08-09）」。 10-02～10-07 的改進（看懂貼圖與 X 貼文、別的伺服器的表情、AI 看圖補字典、被罵的應對）已上線並 commit，紀錄歸檔到 `TODO-completed.md`「AI 偶爾插話：10 月的改進（歸檔 2026-10-13）」。

**待做**
- [ ] **C-4 自我進化迴圈**（閒置批次）：consolidation（合併重複、衝突取新記「以前X現在Y」）、decay（久未重提降權/封存）。**未做**。
- [ ] **C-4 隱私公告**：綁定插話頻道時自動置頂 + 改 channel topic。**未做**。
- [ ] **C-4 選配監督面板**（不擋流程）：查/改/刪/禁記；複用 `/personality_extract` UI 模式。**未做**（接口 `MemoryService.list_facts/forget` 已備好）。
- [ ] **觀測 / Debug 面板（使用者要求 2026-06-21，重要）**：使用者**不想用 CLI/log debug**，未來要一個 **Discord 面板** 能看：每次插話的**完整 prompt（含三層 context）**、決策狀態（reply/pass/error）、三層 context 數量（chat/persona/memory）、記憶 flush 狀態、某人記得的偏好。**取代** `ambient_prompt.txt` + grep。可與「記憶監督面板」合併成一個「AI 狀態/觀測面板」。**現況暫用**：`discord_bot.log` 的 `ambient 生成 …chat/persona/memory` 摘要 + [`/logs/ambient_prompt.txt`](src/llm/ambient/ambient_reply.py)（`AmbientChatSettings.debug_log`）；面板做好後轉成資料來源。
- **延後（非 v1 必要）**：`retrieve_discord_context` 泛化吃 channel 的 hybrid 長期對話召回——觸碰 /askai 核心、風險高，等 B 的 persona 召回不夠用再做。

**10 月已上線的改進（2026-10-02～10-07；定案理由、查證數據、實作與突變細節見歸檔「AI 偶爾插話：10 月的改進（看懂貼圖與 X 貼文、看圖補字典、被罵的應對）」）**
- AM-Q4（`673a965`）：插話讀最新訊息改用 `semantic_message_text`（只回貼圖不再被當成空 @）；回覆對象或最新訊息含 X 貼文連結時用 `utils.link_fix.fetch_tweet`（syndication CDN，免金鑰）附內文、作者，縮圖給模型看（`llm.preprocess.tweet_context.expand_tweets`），/askai 一併。
- AM-Q5c～e（`673a965`）：字典沒登錄的表情（＝別的伺服器的）留 ` :名稱: ` 並下載給模型看（`external_emoji_context`，每則最多 2 張）；字典唯一讀取點 `llm.preprocess.emoji_dictionary.entries()`（手改即生效）。本伺服器的表情描述由使用者維護、不改；別的伺服器的貼圖不多查 API。
- AM-Q6（`cd0baf7`、`e61f6a3`、`5f34b28`）：bot 看到真人訊息裡字典沒描述（或只有類別字）的表情、不在本伺服器的貼圖時，背景讓模型看圖寫描述，寫回 `settings/emoji_dictionary.txt`（別的伺服器的放檔尾專區）與新的 `settings/sticker_dictionary.txt`（貼圖 ID 當鍵）；每個只看一次、一次一張、每天 30 張、維護時段不跑；人寫的描述不覆寫；寫入前備份到 `/logs/dictionary_backup/`；`EmojiAutofillSettings.mode` 已是 `on`。只有類別字的行解讀成「類別、描述待填」（AM-Q7b）。10-03 重啟後 3 秒內把本伺服器貼圖 IDEA 誤記成別的伺服器 → 快取沒有時看訊息所屬伺服器的 `guild.stickers`／`guild.emojis`。效能：一天約 1～2 分鐘 GPU，不需改。
- AM-Q8（10-12）：表情與貼圖字典留在版控、不 ignore；每次使用者說 commit 就順手看一眼字典變動、另做 `chore(settings)` commit（AGENTS 收工、記憶）。
- AM-Q1（被按讚句子當固定參考檔）已被下方「AI 自主學習」取代，撤回。

**AM-Q2 style_refs 抽 2 還是 3 → 維持 2（使用者 10-02 問）**：996 次插話（7/28～10/2）通過距離門檻的候選：1 筆 61%、2 筆 16%、≥3 筆 22%——78% 時候抽 2 已經全拿，改 3 只有 22% 會多一條。**瓶頸是距離門檻 0.45**：多數時候只有 1 筆候選，同一句被重複用、沒得輪替。**待決**：要不要放寬門檻——先唯讀試算近期觸發訊息在 0.45／0.50／0.55 各有幾筆候選、多出來的句子像不像，再決定。

**待決 AM-Q6h 偏掉的描述怎麼辦**（使用者未回，照 A 的現況實作）：A 接受，使用者看到再改（git diff 看得到 AI 寫了什麼）／B 寫入時加註「AI」讓使用者好挑出來改（要改格式）。建議 A——檔尾專區本身就標明是 AI 補的；本伺服器那 16 行只有就地補，git diff 一眼看得到。

**AM-Q3「有人接話」也算 style_refs 的正向（使用者 10-02：「這個不錯」），候選已列出、程式未改**
- 候選檔：repo 根目錄 `style_refs_candidates.md`（**未追蹤、內容含群友發言，不要 commit**；使用者要在 git status 看得到、自由刪改）。條件：沒有負評，且至少一種正向訊號——👍 被讚、💬 有人接話、↩ 被群友用 Discord 回覆功能直接回覆。共 1,530 句：兩種以上訊號 170、只有讚 240、只有接話 325、只有被直接回覆 795。一行一句，`#編號`＝`ai_interactions.id`。
- **發現：用 Discord 回覆功能或 @ 回 bot 不會被標成「有人接話」**——那會走 `_is_directed` 路徑，`mark_got_reply` 只在 `_is_followup_to_bot`（同一人緊接著講、沒用回覆功能）時呼叫。最直接的接話反而沒算：958 則插話被群友直接回覆過，其中 795 則讚與接話都沒算到（原始聊天紀錄 `discord_messages_raw.reply_to_id` 可回補，資料從 4/21 起）。這同時影響插話**鉤子學習**的正標籤（`got_reply` 也是鉤子 k-NN 的樣本）。直接回覆不一定是好評（可能是「你在講什麼」），候選檔附了第一則回覆內容。
- 「有人接話」的現行定義（`ambient_reply._is_followup_to_bot`）：bot 插話後的**第一則**真人訊息、在時限內、而且是 bot 剛才回應的那個人說的——準確度高、但少算。
- 待決：① 直接回覆要不要算正向、算的話要不要先過濾負面回覆；② style_refs 的查詢條件改成「讚或接話（或直接回覆）且無負評」；③ `got_reply` 要不要補標直接回覆（含歷史回補）。使用者看過候選檔再決定。

**AI 自主學習插話風格（2026-10-02 討論；取代 AM-Q1）→ 暫停，使用者決定先維持現狀（style_refs 只看讚）**。現狀評估：被讚的 382 筆有 84% 來自 6～7 月新鮮期（每月 160／161 筆，9 月只剩 17 筆），參考池等於凍結在新鮮期；沒用上「有人接話」與冷場訊號；61% 的插話只有 1 筆候選；沒有過濾過時事實、黃腔、AI 自我話題；也沒有評估 style_refs 有沒有讓插話變好。重啟時從下面 AL-Q1～Q5 接著談。
- **使用者定調**：要 AI 自主學習，**不靠人工挑選**（「要人工就意義下降了，更何況現在模型越來越強」）→ AM-Q1 的 B（列給使用者挑）撤回。
- **機制本質**：模型當「評審」不當「改寫者」——從真實句子裡挑好的、淘汰差的，不重寫；再用之後的實際反應驗證，學壞了自動退回上一版。
- **訊號查證（`ai_interactions`，依月）**：正向率 6 月 11.3% → 7 月 4.8% → 8 月 2.1% → 9 月 1.5%（新鮮感退了，讚越來越少；高讚句子多是 6～7 月談「自己是 AI」的回答）；「有人接話」（`got_reply`）8/09 起才記，9 月 163 次，是讚（17）的 10 倍；自發插話後沒反應也沒人接：9 月 778／1,156 次。→ 讚數不能單獨當標準，「有人接話」是主要的正向訊號，「冷場」量很大、可以當反面教材。
- **待決 AL-Q1 學什麼**：A 例句池（模型從真句子挑、不改寫；style_refs 改從這個池子召回）／B 例句池＋原則（模型對比「有人接、被讚」與「冷場」，寫 ≤6 條原則附例句佐證，即原本的自我蒸餾）／C 只做原則。建議 B 分兩階段：先 A 跑兩週，確認自動評估本身可靠，再開原則（原則錯了會影響每一次插話）。
- **待決 AL-Q2 好壞怎麼判**：好＝有人接話或被讚（讚數用「當週相對值」修正新鮮期偏差）；壞＝自發插話後沒反應也沒人接；有負評直接淘汰。`got_reply` 只看下一則的保守偏差先接受。建議照此。
- **待決 AL-Q3 評審要排除什麼**：建議排除談自己是 AI／bot 的回答（新鮮期特例）、寫到特定成員事實的（會過時，例：#1638）、只適用一次性事件的、露骨的黃腔（放進例句等於鼓勵它主動開黃腔；守則只允許對方先開才接）。
- **待決 AL-Q4 自動評估與回滾**：每版例句池／原則記版本；上線滿一週且樣本夠才比較；「被接話率」與「正向率」都比上一版差（超過雜訊範圍）就自動退回，不需人工；結果寫進 log，AI 日記順便講「這週學到什麼」，讓人看得到但不用動手。建議照此。
- **待決 AL-Q5 週期**：每週一次，接在 04:00 維護之後（⑤ 約 05:50 結束）；候選數百則分批評審，估 10～20 分鐘 GPU。建議照此。

**被罵的應對 RB（2026-10-07 已上線：`40737ea`、`0f71b6d`，開關 `ambient_insult_mode=on`；RB-Q1～Q8 全部定案，盤點、四輪討論與審查見歸檔）**
- 機制：被點名時模型在那次生成裡判斷，只是在罵它（羞辱它、髒話衝著它、明顯真的不爽；叫它閉嘴、嫌吵、帶笑的虧、指出它哪裡錯的都照常回；拿不準照常回）就整則輸出 `[INSULT]`（英文標記不會漂成簡體；夾在文字裡＝不送、不按、不記）→ 不回文字、不寫互動紀錄，按嘲諷表情（`AmbientChatSettings.insult_reaction_emoji`＝`sointeresting`，找不到用 🙄）、記進 `ai_insults`；對方回覆的那則插話標 `insulted`、`got_reply` 改 FALSE。
- 記仇：罵過它的人 7 天內不主動接他的話（再罵重算）；點名照回，但 system prompt 疊【你的心情】（只寫幾天前、幾次，不放原話與名字——那些是群友打的字），語氣冷淡、最多酸一句；道歉或示好可消氣（只影響那一則）。群主罵它：表情照按、不記仇（`bot_owner_id()`，使用者：關係不一樣；管理員沒有豁免）。不在 Discord 上處罰（RB-Q3）；學習資料（style_refs、按讚）排除被罵的互動（RB-Q4）；人格描述可以寫對機器人的態度（RB-Q5，使用者：「希望機器人也像人有情緒」）；RB-Q7 不回補歷史，從重啟後開始記。
- 程式：`llm/ambient/ambient_insult.py`（`is_marker`、`mentions_marker`、`grudges`、`mood_note`、`respond`）；表 `ai_insults`、欄 `ai_interactions.insulted` 由 `ensure_table` 建；規則寫在 `ambient_reply_prompt.txt`「被 @ 或被回覆時」（prompt 規則不跟開關，要整個拿掉就改 prompt）。
- 待決 RB-Q9 道歉消氣：現在道歉只讓那一則語氣回暖，名單仍到期才解除；可讓模型在對方道歉時輸出標記、程式清掉記仇。

**偏好事實（C）的政策與接口（仍有效）**
> 政策（2026-06-21 定案）：**只記「本人講自己」的中性偏好；敏感(健康/感情/家庭/財務)一律自動丟、不存；他人評他人/紅線自動丟。多次提到才升等。全自動、零審核佇列。**

**共享接口（2026-06-21 建）**：[`MemoryService`](src/services/memory_service.py)（門面，單例）——任何功能只呼叫它、不碰底層：`recall / list_facts / extract / remember / observe / forget / format_recall`。底層委派 `intro_rag_port`(儲存) + `preference_extractor`(抽取/升等)。未來 /askai、功能一、/remember、管理面板都走這個。

- **驗收**：本人講過愛吃鮭魚且被提 ≥2 次 → 之後相關話題自然帶出；敏感/他人/紅線輸入確認不入庫；衝突取新；久未提的淡出。
- **回音迴圈**：一律排除 bot 訊息（含 `message.author.bot`），不只排除自己。

### 自然插話重構（2026-08-09 已上線）

<!-- @meta
id: ambient-natural-rework
type: DECISION
status: confirmed
depends_on: [ambient-chat]
last_confirmed: 2026-10-02
-->

**起點**：使用者觀察「一偵測到發言就馬上運算」+「聊天室常有多組人聊不同主題，機器人不知該加入哪個」。
**目標函數（使用者拍板）**：**談話自然、適當插話、有人性**；GPU 節省只是副作用，不是目標。

**調話量**（依序試，每次只動一項才看得出效果）
- 想更多話：`hook_threshold` 0.4→0.35 ／ `cooldown_seconds` 180→150（**下限約 120**＝一次生成的時間， 低於它隊列只會越排越長）／ `hourly_cap` 20→30 ／ `hook_explore_rate` →0.2。
- 嫌太多：`hook_explore_rate` 0.15→0.1 → `hook_threshold` 0.4→0.45 → `cooldown_seconds` 180→240。
- **要降載請調 `hook_threshold`，別再加機率閥。**

**釐清出的分工原則（重要，之後所有取捨都照這條）**：

| | 鉤子（code） | 模型（prompt） |
|---|---|---|
| 做什麼 | **可觀察的行為痕跡**（量測） | **意圖與分寸**（判斷） |
| 例 | 有問句、30s 沒人回；某人連講 3 則沒人接 | 他是想要回應還是不想被打擾？這時插話得體嗎？ |
| 會不會錯 | 不會——它不判斷，只量測 | 會 |
| 成本 | 零 | ~120s |

判斷一件事該放哪層，就問「**這件事有沒有『判斷錯』的可能**」——有，是意圖，歸模型；
沒有，只是數數字，歸 code。`two_person_volley` 的教訓正是 code 越界去猜意圖。
反過來全給 prompt 也不行：每則訊息都要 120s 生成才知道要不要講，物理上做不到。

→ **通則：換模型時，prompt 裡所有「沒寫界線的允許」都會被重新詮釋一次。**

**單一來源原則（使用者當場糾正，已定案）**：初版在其餘三處都加「——見 guardrails【動作描述】」，
太冗長。**規則只寫 guardrails 一份，其他檔案只把原本的「鼓勵」拿掉，不重述也不指路**——
guardrails 本來就跟它們組在同一個 system prompt 裡，指路等於對著同一份文件說「請見同一份文件」。

**待觀察（上線後才調得準）**
1. `hook_threshold`：看 `discord_bot.log` 的「ambient 鉤子」行（`hook_debug=True`）分數分布，
   話太少就調低、太吵調高。這是話多話少的**主旋鈕**。
2. 模型遵不遵守 `#N` 輸出契約：看 `ambient_prompt.txt` 的 reply 段（記的是模型原樣輸出）與
   `已插話 … 錨定=#N` log。不遵守就退回裸送，不會壞，但錨定效果會失效。
3. `got_reply` 樣本累積：滿約 50 筆後 k-NN 特徵才會真的生效（`_knn_feature` 樣本 <5 回中性）。
4. 之後才做：用 (特徵, got_reply) 跑 logistic regression 取代手設權重 `ambient_hooks._W`。
5. **`got_reply` 有已知的保守偏差**：只認「它發言後的第一則」訊息（`followup_armed` 用完即熄），
   所以「有人先聊別的、第二則才回它」不會被標記 → 系統性低估被接率。當初這樣設是為了 L4-b
   不要亂接話；要放寬的話得把兩個用途拆開（L4-b 維持保守、標籤改成 window 內有人 reply/提到它），
   但該多寬要等真實資料才知道，現在拆是憑空猜。

**已作廢的中間結論（避免重複討論）**
- 「debounce 純 5 秒」→ 打字不是講話，改為**靜默 + typing 雙條件**。
- 「以省 GPU 排優先序」→ 使用者拍板目標是自然，該排序作廢。
- 「(A) trigger 往回找 vs (B) 內容閘看整段 burst」→ 有了選線機制後 trigger 是哪則不再關鍵，**(B) 定案**。
- 「用 reaction 當學習標籤」→ 負向樣本僅 13 筆，改用「有沒有被接話」。

- **新聞檢索（SearXNG）**：google 系、yahoo、brave、qwant、startpage 已停用（`searxng/settings.yml` `disabled: true`）；news 路由用 week、不用 day；明確指定 engines 會繞過 disabled，`default_engines` 要同步改。

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
- [ ] 音樂面板改用共用置底元件 `utils.panel_bump.PanelBumper`（2026-09-29 決定**暫緩**：面板訊息存記憶體、按鈕狀態就地 edit、啟動時有清理流程、面板 id 與被設定熱重載監看的 `music_runtime.json` 同檔；要搬得先把面板 id 移到別的檔，上線那次會留一則舊面板要手動刪）
- [x] 多歌單管理（多歌單下拉，可複選合併播放）— 2026-06-20，詳見 `TODO-completed.md` 歸檔
- [ ] 快取空間管理（LRU 清理、磁碟用量監控）

**P2（進階功能）：**
- [ ] 歷史播放紀錄
- [ ] 使用者點歌統計
- [ ] DAVE 加速問題追蹤（等 discord.py 後續版本優化）

---

## 跨來源整合專區（規劃；發文已共用）

<!-- @meta
id: cross-source-integration
type: TODO
status: draft
depends_on: []
affects: [project-architecture]
last_confirmed: 2026-10-02
-->

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
---

## 產品能力 TODO

<!-- @meta
id: product-todo
type: TODO
status: draft
last_confirmed: 2026-10-02
-->

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
