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
- 2026-09-30 16:4x（`services/` 分群＋S6-1＋重複活動雜訊修正 **已套用・已重啟・驗證通過・已 commit**）：16:17:41 套用 `services_reorg_v2.patch`（43 檔，與工作副本逐位元組相同），使用者 16:38 重啟；啟動 gate 652 項全過，11 個指令模組、21 個斜線指令、各排程、轉發、Telegram worker、Notify Server 都從新路徑啟動；重啟後沒有任何 ERROR，套用到重啟之間也沒有。指紋遷移在第一篇含活動的公告進來時才跑，新摘要（預期「新發現 0 組，先前已標記 1 組」、不再報 ERROR）要等那時才看得到。S6-2 改定案：使用者認為 dockerfile 的鎖版本沒必要 → dockerfile 還原成只裝 `requirements.txt`；`constraints.txt` 留作紀錄（與容器內 `pip freeze` 102 項逐一相同），檔頭改成「建置不讀、用來對照與暫時退回」。文件路徑更新腳本已跑（交接文件 16 處、記憶 1 處；剩下的舊路徑都在「程式結構整理」的新舊對照裡）。S7-1 使用者選 A 拆五個：`5e10611` 搬家（648 項）、`2b31828` S6-1（650 項）、`f7d4a14` 重複活動只報一次（652 項＝上線版）、`f6e4830` 加 mcp＋版本紀錄、交接文件另一個 `docs` commit；中間兩個狀態都先在容器 `/tmp` 跑過完整測試才 commit，`it_comfyui_image.py` 沒進。
- 2026-09-30 16:0x（新 image 上線、重複活動查證，**未動 code**）：使用者 13:09 用新 image 重建容器（**`services/` 搬家 patch 尚未套用**，程式仍是 `9b0b916`）；啟動 gate 648 項全過，套件版本與 constraints 一致（mcp 2.2.0、yt-dlp 2026.8.19、numpy 2.5.3、pgvector 0.5.0、llama-index-core 0.14.25、davey 0.1.6、websockets 17.1）；15:56、16:02 正常播歌（語音加密新版 OK）；13:09 後唯一的 ERROR 是 15:56 語音斷線重連（Discord 端切換，升級前也有）。
  - 重複的「群聲共振模擬域」活動查證：兩筆都建於 8/19、8/20（9/22 修正前，當時 `normalize_title` 不認半形 `<>`）；第二筆 `1539937681176272916` 在資料庫已標 `superseded_by` 指向正本 `1539556072082112604`；兩者都在 9/29 11:59 結束。9/22 修正後的每次指紋遷移都只報這同一組、沒有新增重複 → **去重（有重複就更新）正常**。但遷移每跑一次就再報一次 ERROR（累計 26 次），已處理過又已結束的重複變成雜訊。待決：要不要讓遷移略過已標 `superseded_by`／已結束的組合（見活動區塊）。
- 2026-09-30 12:2x（重建完成，準備套用）：使用者 11:39 建好新 image（依 constraints 安裝，含 mcp）。**04:00 維護第一次在新路徑下完整跑完**：③ 人格萃取 37/37、④ persona agent 26 人、⑤ 精簡版發布 64 人（寫入 63、空 1、失敗 0）。04:00 後 6 行錯誤都與整理無關：語音斷線 2 次（都在 2 秒內重連到新的語音伺服器，屬 Discord 端切換）、活動指紋遷移提醒 Discord 上有一組重複的「群聲共振模擬域」活動（event_id=1539937681176272916，需手動刪一個，既有資料狀況）、插話模型回空內容 1 次（已略過）。`services_reorg.patch` 仍可乾淨套用。
- 2026-09-30（S6-2 升級影響研究完成，**未動 code**）：52 個升級都不影響我們、不需改程式（隔離 venv 實測 648 測試全過、SQL 與影像輸出相同）；S6-2 建議改為「升到最新＋用 constraints 鎖住測過的版本」。04:00 維護第一次在新路徑下跑：③ 完成、④ 進行中、無錯誤。
- 2026-09-30（`services/` 分類複查）：兩個角度都確認 patch 正確；調整套用流程為「先重建 image → 套用 patch 後立刻重新建立容器」，避免歡迎訊息在空窗期出錯；備好文件路徑更新腳本。
- 2026-09-30（S6-2 套件升級影響清查，**未動 code**）：從零重建會改 52 個套件版本（主版號 3：deprecated、setuptools、websockets），新增 18 個；breaking changes 研究與隔離環境實測進行中。
- 2026-09-30（`services/` 分類，**已在工作副本完成・648 測試全過・未套用・未 commit**）：分成 relay／events／community，共用留頂層；相依圖前後相同、資料路徑不變；獨立複查進行中。待決：`get_shared_state_db` 搬到 `state_db.py`（S6-1）、重建 image 時用 constraints 鎖版本（S6-2）、套用時機（S6-3）。
- 2026-09-30（grill：`services/` 分類，**未動 code**）：盤點 19 檔分成轉發／遊戲時程／社群管理／共用四群，寫入搬檔會碰到的地方與待決問題 S5-1～S5-4。
- 2026-09-30（重啟驗證，**未動 code**）：使用者 02:10 重啟；啟動 gate 648 項全過、點名新程式上線；00:00 日記在新路徑成功發布；唯一 ERROR 是既有的模型逾時。背景 agent 狀態：只有 9/29 第一個驗證流程因 session 重啟停下（其未完成部分已由主 agent 補做），之後的流程 9/9 完成。待辦：07:30 後確認 04:00 維護。
- 2026-09-29（第 11 輪續）：點名修改的獨立複查確認行為不變；依複查補上點名端到端測試、修正守衛三處誤判與自測漏洞；9 種突變全紅、648 測試全過；第二個 commit。
- 2026-09-29（第 11 輪）：第一個 commit `97d7595`（`llm/` 重組）；點名改由 Cog 交按鈕建立函式給服務層，服務層不再 import 指令層（新測試 3 項、突變 3 種都紅）；修正 import 守衛把 `__file__` 等模組內建屬性誤判為不存在的問題；646 測試全過，等第二個 commit。
- 2026-09-29（第 10 輪，**未動 code**）：`it_comfyui_image.py` 移出暫存區；MCP R2-Q2 定案（`search`＋`fetch`，設計全部定案）；寫入點名「服務層依賴指令層」的細節與修法選項（建議先不改，改時先補測試再注入按鈕建立函式）。
- 2026-09-29（完整驗證 `llm/` 重組的相依與關連，**未動 code**）：六個角度（測試與運行、實際執行所有 import、相依圖比對與循環、分層、程式以外的引用、git 狀態）都沒有發現這次搬家造成的問題；循環相依前後完全相同。待處理：無關的 `it_comfyui_image.py` 被一起 stage、本檔最新修改未 stage。
- 2026-09-29（grill：MCP 第 3 輪，**未動 code**）：R2-Q3 定案關鍵字全文搜尋、R2-Q4 照建議；R2-Q2 使用者質疑「照來源命名會一直加工具」→ 查證 Anthropic 工具設計指引與 OpenAI MCP 文件後撤回原建議，改建議 `search`＋`fetch` 兩個工具、來源用參數選、來源清單由登記表自動產生，待確認。
- 2026-09-29（grill：L4 定案，**未動 code**）：使用者同意照建議——搜尋本體 `services/search/`（服務，不只給 LLM）、MCP 殼 `llm/mcp_server.py`（給 LLM 的橋接）、網頁搜尋留在 `llm/retrievers/web/`。MCP 區塊的啟動指令、log 分檔名稱、索引檔位置同步更新；R2-Q2～Q4 待答。
- 2026-09-29（第 1、3 項＋收尾，**已完成・643 測試全過・下次重啟生效・未 commit**）：刪 4 處死碼（FB／IT 輪詢迴圈、兩個沒用的 task 屬性、一個沒用的 import，共 32 行；FB／IT 只靠推送）；新增 `test_data_file_paths.py` 釘住 6 個資料檔位置（突變會紅）；刪除只剩快取的 `src/llm/persona_agent/`；S1～S4 結案。L4 使用者重新提出：搜尋獨立成服務、MCP 殼放 `llm/`，待 L4a／L4b 確認。
- 2026-09-29（`llm/` 依角色分子資料夾＋prompt 組裝搬家，**15:26 套用・15:28 重啟・驗證通過・未 commit**；L4 定案 MCP 外殼放 `services/`、名稱維持 `agent`、P3 暫停）：使用者核可 L2a／L2b／L3。在獨立 git worktree 改（bot 以 `./src` 即時掛載，延遲 import 會在重啟前壞），新增 import 守衛 `test_import_resolution.py`（七種突變都會紅、搬家前後都沒有誤判）與 prompt 組裝測試 `test_prompt_builder.py`；搬家前 627 項、最終版 637 項測試全過，逐模組獨立 import 全成功，prompt 組裝 49,152 組輸入逐字相同；兩位子 agent 獨立複查沒有找到執行期問題，指出的守衛誤判與漏抓已修。新舊路徑對照見 [程式結構整理區塊](#程式結構整理2026-09-29-構想grill-中)。L4、P3、第 1／3 項、N3 未動。
- 2026-09-29（grill：程式結構整理，**討論中・未動 code**）：使用者覺得程式很亂，想依功能分資料夾但要有整體規劃。新增 [程式結構整理區塊](#程式結構整理2026-09-29-構想grill-中)，寫入第 1 輪待決問題（痛點、整理方式、分法原則、跟 MCP 的關係）與盤點事實（一檔多功能的檔案、`discord_bot.py` 塞的東西、轉發應整組、`sent_articles.db` 路徑地雷、沒有測試的功能）。MCP 區塊的 R2-Q5 改為取決於這邊。使用者要先看架構怎麼切、以及不影響功能能先做什麼 → 寫入架構草案（`core/`＋依領域分：relay、schedule、ai、search、community、trade、music、misc）與「現在就能做」清單（資料檔路徑集中、私有 import 守衛、清死碼、更新文件、MCP 照新結構寫）。使用者否決草案 v1（拆了 `llm/` 與 Discord 服務），要求從現有架構出發、最小修改 → 改寫成架構建議 v2（P1～P5）；第 1 項縮小成只加測試釘住 6 個資料檔位置，第 3 項確認 4 處死碼（`chat_persistence` 延遲 import 不是死碼，移出）。使用者提出「檔案命名也是問題」→ 讀到 ComfyUI 區塊既有的「檔名正名」與「不做 llm/services 資料夾重組」決定並補進本區塊；寫入命名盤點與第 2 輪待決問題 N1～N4。使用者回覆：N1 同意、N2 三個都不改、N3 延後、P1 否決（services 就是服務）、P3 入口仍由 `discord_bot.py` 管；使用者定義 `llm/`＝LLM 相關的組裝、優化、橋接、RAG、MCP → 撤回搜尋獨立的修正，寫入 `llm/` 討論 L1～L4 與 P3 確認。使用者回覆 L1 同意、L2 要依 LLM 角色分子資料夾（重開不重組的決定）、L4 本地資料一律放 `localdata/` → 寫入第 4 輪：L2a 子資料夾草案、L2b 搬法（一次搬＋import 守衛）、L3 log 格式化移進 `logger_factory`、L4 MCP 殼放 `services/`。
- 2026-09-29（grill：MCP／搜尋工具化，**討論中・未動 code**）：新增 [MCP／搜尋工具化區塊](#mcp搜尋工具化2026-09-29-構想grill-中)，寫入第 1 輪待決問題（誰呼叫工具、結果給誰看、關鍵字過濾的痛點、要回答哪類問題），以及兩個子代理的查證事實（`/askai` 與網頁查詢流程、既有 tool calling、各來源資料量與儲存方式、「寫死日期區間」其實是轉發）。定案：社群稽查（依 ID 查人）不納入工具；用途＝查情報，排除 Telegram 內鬼；改由 LLM 決定何時查；先做 MCP server，工具本體共用。補上 Lemonade 實測速度與 bot 接工具的成本估算；寫入第 2 輪待決問題（MCP 客戶端與部署、工具切法、搜尋方式、論壇索引層級）。使用者追問「一定要另開 container 嗎」→ 在 R2-Q1 補上三種放法（塞進 bot 行程／同 container 另一個行程走 stdio／新 container）的利弊。使用者說不會有別的電腦連 → R2-Q1 定案：只有這台的 Claude Code，採放法 ②（stdio、`docker exec` 啟動，bot 重啟一次裝套件）。使用者問程式放哪 → 新增 R2-Q5（建議 `src/search/` 本體＋`src/mcp_server/` 殼；不可取名 `mcp/`；log 分檔）。使用者問「MCP server 不就取代 search？」→ R2-Q5 補上說明（MCP 只是協定殼，搜尋程式一定要有，差別只在放哪），以及 A 的變體。
- 2026-09-29（新增 repo 根目錄 `AGENTS.md`，**未 commit**）：每次工作都要遵守的規則（討論方式、使用者資料檔高嚴重性規則、Docker 限制、共用元件、程式碼與測試慣例）從本檔與本機記憶搬過去，讓所有 session、一般子代理、雲端都自動載入（Claude Code v2.1.277 以上；repo 裡不要放 `CLAUDE.md`／`CLAUDE.local.md`，否則改讀那個檔）。本檔開頭改成「本檔維護規則」，並寫明每段搬去哪。新規則：討論與 grill 的每一輪都回寫**待決問題（選項＋建議）**；問題每輪只談一個主題、約 3～5 題。依此補寫 Telegram 過濾、ComfyUI、Persona M7 三個暫停主題的待決問題與當時的建議。
- 2026-09-29（log 統一改成 `__name__` ＋ 設定檔，**已實作・595 測試全過・已 commit・已上線**；06:22 重啟後實測：3 小時 781 行、每行帶模組名稱、httpx 逐筆請求 0 行、測試紀錄只進 `test_run.log`、handler 沒有重複（唯一的重複行是 Telegram 啟動時的相簿補圖略過訊息，見 Telegram 過濾區塊）；之後加上 `discord.player` 壓到 WARNING（每播完一首歌一行 ffmpeg 結束訊息，約 250 行／天，下次重啟生效）與「json 裡的 logger 名稱都要對得到模組」的測試）：原本只有 `discord_bot` 這個 logger 掛了輸出，其他名稱的 logger 紀錄**既不顯示也不進 log 檔**（實證：09-29 00:29 建身份組那筆不在 log）。改為：① 新增 `settings/logging.json`（dictConfig）：root 輸出到畫面＋`discord_bot.log`；類別 logger `article_monitor`／`llm_anomaly` 各寫自己的檔、不往 root 傳；httpx／httpcore／urllib3／llama_index 等壓到 WARNING；每行多印模組名稱 `[時間] [等級] [模組] 訊息`。② `utils/logger_config.py` 改成只讀設定檔（import 即套用、冪等；`LOG_LEVEL` 可覆寫 root 等級）。③ 60 個模組從 `getLogger('discord_bot')` 改 `getLogger(__name__)`；`discord_bot.py` 主程式以 script 執行，明確命名 `discord_bot`；`bot.run(..., log_handler=None)` 避免 discord.py 重複輸出。④ 測試模式：`test/__init__.py` 設 `APP_TEST_LOG_FILE`，所有檔案輸出（含 `llm.logger_factory` 的 prompt 除錯檔）改寫到 `/logs/test_run.log`，實測跑完正式 log 位元組數不變。⑤ 守衛：模組 logger 一律 `__name__`（AST 判斷，類別 logger 與 `discord_bot.py` 例外）、不准 `print`；Rule 的 allowed 支援資料夾。突變驗證都會紅。**要拆分類時**：在 json 加一個 handler＋一個以模組前綴為名的 logger（例：`services.relay.telegram_relay_service`；2026-09-30 起 services 分群，模組名稱跟著變），重啟即可，不動程式碼。**下一批**：telegram-scraper 約 45 處 `print` 改 logger；該容器只掛 `./src/telegram_scraper`，要共用 `settings/logging.json` 得改 compose 掛載（需使用者重建容器）。
- 2026-09-29（週期活動提醒：深塔海墟，**已實作・586 測試全過・已 commit・待部署驗證**）：深塔／海墟各 28 天、週一 04:00 重置、錯開 14 天；重置前一天 20:00 正常 @、重置當下靜音 @ 自助訂閱身份組「深塔海墟提醒」；綁「週期提醒頻道」時自動建身份組＋發面板，每次提醒後面板刪舊發新置底。詳見 [週期活動提醒區塊](#週期活動提醒深塔海墟2026-09-29-已實作待部署驗證)。
- 2026-09-28（grill：Persona M7 後續／ComfyUI 產圖／Telegram LLM 過濾／深塔海墟提醒，**討論中・未動 code**）：新增 Telegram 過濾與週期提醒兩個草稿區塊並寫入查證事實；ComfyUI 區塊開頭補過時狀態修正（步驟 2 已完成、鎖有漏洞）；過時項目歸檔到 `TODO-completed.md`（Persona 影子模式規劃、Telegram 媒體防雷、ComfyUI 步驟 2 與 `keep_alive` 註解、插話 Phase B 三項、Ollama 時代觀察項），Persona 區塊改成 M7 現況。
- 2026-09-28（Telegram 相簿漏圖，**scraper＋relay 兩端已實作・545 測試全過・已 commit・已部署；今天缺的 87 張已於 15:58~16:07 補發完成**）：使用者回報 GameData #3223 相簿 8 張只發 1 張。**觸發點＝8/02 補掃 commit `fbd2d3c` 加的全域 `process_lock`**：本意是防「同一則」被三條路徑並行處理，卻把 Telethon 本來並行派發的相簿各張變成逐張排隊（組員寫入間隔 p90 0.03s → 2s），relay 0.5 秒到齊判斷等不到整組就先發、晚到的被丟棄。8/02 起 191 組相簿 77 組缺圖、共 237 張。**改法**：全域鎖 → 單則訊息鎖 `(chat_id, message_id)`（新 [message_lock.py](src/telegram_scraper/message_lock.py)）。**relay 端同輪修掉**（使用者拍板）：改成「哪個組員先到就收整組、等媒體到齊＋3 秒安靜才發、晚到的以（補圖）再發、補圖時效 12 小時」。**補今天缺圖**：先校正 delivery_state（補記實送沒標、撤記標了沒送）再重啟，由 reconcile 走正式路徑補發；唯讀預演＝23 則、87 張。詳見 [補掃區塊 2026-09-28 追加段](#telegram-漏收事件自動補掃2026-08-02-已實作2026-08-18-補上中段缺口盲區2026-09-28-全域鎖改單則訊息鎖修相簿漏圖待部署驗證)。
- 2026-09-27（Persona Agent **M7 精簡版發布，已實作・510 測試全過・未 commit**；bot 已隨 09-27 重開跑新程式，⑤ 首次 dry_run 在 09-28 04:00）：**09-28 已 commit 並上線**；現況、定案、待辦與坑已收進 [Persona Agent M7 區塊](#persona-agent-m7精簡版發布2026-09-28-已上線觀察中)（原 HANDOFF 檔已刪除；舊的影子模式規劃已歸檔到 `TODO-completed.md`）。
- 2026-09-22（活動自動發布「連結指向沒有該活動的訊息」+ 重複建活動，**已實作・397 測試全過・待部署驗證**）：使用者回報活動 `1539556072082112604`「[群聲共振模擬域]戰鬥活動」的「公告出處」點進去，那則訊息**一個字都沒提到這個活動**。**根因不在活動功能，在文章轉發**：活動偵測讀 `article_content_full`（該篇 8,454 字），轉發 embed 讀 `article_desc` —— 而 `article_desc` **全庫 532 篇皆為空字串**，於是「沒摘要就取前 300 字當預覽」那條 fallback 成了唯一路徑，8,454 字只發出 303 字；6 個活動名分別在第 1347~2010 字，全部被切掉。而 embed 連 `url=` 都沒設（FB 那邊有），訊息是條死路。**量化**：315 個 article 來源活動中 100 個（31.7%）的活動名在轉發訊息可見文字裡找不到。**同時修掉第二個 bug**：`normalize_title` 不認半形 `<>` → 「活動預告 \| <群聲共振模擬域>…」與「[群聲共振模擬域]戰鬥活動」指紋不同 → 同一活動建了兩個（線上 `…604` 與 `…681`）。**改法**：截斷 300→1200（全庫 p75 僅 565 字，85.2% 完整發出）+ 截斷時附官網連結 + embed 補 `url=`；活動描述嵌該活動的原文片段（匯總帖的 N 個活動各自可讀）；`normalize_title` 收 `<>`（**不收 `《》`**，472 個標題用它、其中 328 個包的是遊戲名「鳴潮」）；**後到的更好來源改為就地升級既有活動的封面與描述**（FB 832/834 有圖、article 三個封面欄位全庫皆空，且 FB 專屬貼文比匯總帖晚 7~28 天到）；同名+區間重疊視為官方改期而非新建（排除**本輪已配對的指紋**，否則 article 995 那種同名不同區間會被吃掉）；加建立/升級序列化鎖、指紋遷移、例外分離、補 log。**升級既有活動走四軸**（封面／描述／時間／名稱各自判斷）：中途曾用單一品質總分當唯一閘門，跑對抗性複查後確認那是錯的——422 筆規劃事件裡 294 筆同分，於是改期走不進換描述的分支（Discord 上時間改了、描述第一行的活動時間還是舊的）、專屬帖的短導言覆蓋匯總帖的長玩法說明（實測 370→118 字）、14.6% 的公告一個字都沒更新，故拆成四軸。**使用者從 Discord 刪掉的活動改立墓碑**（原本實體刪列，7~28 天後另一來源會把它原地復活），只有 `/resend_article` 解得開。**線上 DB 已先以指令套用欄位**（32 列不動，備份在 scratchpad），重啟後直接可用。詳見 [活動自動發布修正區塊](#活動自動發布連結指向錯誤--重複建活動2026-09-22-已實作待部署驗證)。
- 2026-09-02（ComfyUI 產圖 + GPU 資源仲裁，**規劃定案・未開工**；本輪只做線上實測與一則註解清理，未動任何功能 code）：需求＝每天 03:00 排程產圖（角色換衣，依心情／日期／節日），10 張以內。**硬數據**：兩張 RX 9060 XT 各 16GB，27B+ctx32768 本來就跨兩顆吃滿 → 卸載 LLM 是唯一解（釘單顆並行方案否決）。**線上實測（Lemonade 11.5.0 / ComfyUI 0.34.2）**：`POST /api/v1/unload {"model_name":...}` ✅；**卸載後打 chat 會自動重載（22s）→「主動載回」「背景預熱」整段不需要** ✅；`recipe_options`（ctx 32768 + sampling args）不會被洗掉 ✅；**ComfyUI 看不到 Lemonade 的 VRAM**（Vulkan vs HIP，27B 在與不在都回報 free 15.78 GiB）→ 不可用它判斷夠不夠 ✅。**設計定案**：鎖改**租約+心跳**（續租點掛在本來就要做的 ComfyUI 輪詢上，不開 checker task、不猜 timeout）；租約 120s 管卡死、deadline 03:50 管超時（04:00 有維護四步要用 GPU）；租約過期接管者要清 cache + log error。**換後端**：Ollama 可續用（`keep_alive:0` 就是原生卸載語意），vLLM 不可；三處 `keep_alive` **保留**（一度決定刪除，使用者否決且正確：它是可攜層該有的行為，且註解含 Ollama 時代實戰教訓），只把註解改誠實。**prompt v1 走規則零 LLM**：節日查表 + 重用 00:00 AI 日記當心情來源。**本輪 code 異動**：① 拿掉 `_try_heal_lemonade_backend` 那句無法查證的「裸 reload 會掉回 ctx 4096」註解；② `DIARY_TZ` → `APP_TZ`；③ 時區守衛從 regex 改走 AST + 補 5 項自我守衛測試（342 測試全過，未 commit）。詳見 [ComfyUI 產圖區塊](#comfyui-產圖--gpu-資源仲裁2026-09-02-規劃定案未開工)。
- 2026-08-18（Telegram 補掃補不到「中段缺口」，**已實作・未 commit・待部署驗證**）：使用者回報「重啟後又發一大堆早上 10-11 點的文章」，疑似重複。**查證＝不是重複、是首次補發**：`delivery_state` 全表無任何 `message_pk` 送超過 1 次，該批 8 則 `message_date` 10:31~11:03 但 `created_at` 全是 **17:24**（重啟才入庫）；早上 111 則中 34 則無 delivery 記錄者**全部**是 media group 成員（由首則代發），無法解釋的漏發 = 0。**根因**＝2026-08-02 版補掃的 `offset_id = max(message_id)` + `reverse=True` 只看得到比 max_id 更新的訊息，漏的若是**中段**（2742/2743/2746 漏但 2745/2747 已收 → max_id 早跳過去）永遠掃不到，只能等重啟全量掃描（本次卡 7 小時）。**修法＝指針左移**（使用者拍板改既有流程、不另開補洞路徑）：`offset_id = max_id - CATCHUP_GAP_WINDOW(300)`；配套 ①`limit` 加大成 `300+200`（limit 卡的是**撈回**幾則，沿用 200 會在 `window_start+200` 截斷）②新增 `db.get_existing_message_ids` 一次撈視窗內已有 id 成 set 過濾（否則 290 則已存在訊息各跑完整 `_process_message`）。**驗證**：容器內注入假 client/db 重現 8/18 真實缺口，洞全補回、新訊息照收、已存在 297 則零重跑；**反向驗證** limit 壓回 200 → 掃描截斷、洞與新訊息一則都收不到。**下一步**：`docker compose restart telegram-scraper`。詳見 [補掃區塊追加段](#telegram-漏收事件自動補掃2026-08-02-已實作2026-08-18-補上中段缺口盲區待部署驗證)。
- 2026-08-09（插話「談話自然」重構，**已實作・待部署驗證**；py_compile 全綠、146 測試全過、未 commit）：使用者提出兩個痛點——①一偵測到發言就馬上運算，沒等人講完；②聊天室常有多組人聊不同主題，機器人不知該加入哪個。**本輪量到基準**：自發插話「trace→送出」中位 **120.8s**（p90 165s、max 901s，n=3540）、PASS 率僅 15%、`ai_interactions` 5602 筆但負向反應只有 **13** 筆。**核心診斷**：問題不是它選錯主題，是**選的時候那條線還在、120 秒後講出來已經沒了**，而自發插話是裸 `channel.send` 無指向 → 必然像亂入；且節奏由冷卻計時器決定（每 5 分鐘準時報到）而非對話內容。**目標函數經使用者拍板＝自然/人性，GPU 節省降為副作用**。**四層方案**：L3 選線+reply 錨定（第一優先，讓「慢」變合理）、L4-b 接續自己的話、L2 debounce+typing 不搶話、L1 鉤子閘（**不用 LLM**＝結構演算法+少量 regex+k-NN，權重用 logistic regression 從 5602 筆學、標籤改用「插話後有沒有人接」而非 reaction）。順帶 `max_passes_per_burst` 3→1、`cooldown` 300→180。**使用者否決**：等鎖上限（GPU 本來就慢，放棄等於 /askai 忙時永遠不插話）、新鮮度丟棄（被接完也可以插，且丟棄＝白燒 120s 零產出）。**實作中修掉的缺陷**：L4-b 借用 directed 路徑會連 foreground 讓位/降溫硬閘/每小時上限一起繞過 → 加 `followup` 旗標分流閘門。**下一步**：`docker compose restart discord-bot` → 看 log 的「ambient 鉤子」分數分布調 `hook_threshold`、看「錨定=#N」確認模型有遵守選線契約。詳見 [自然插話重構區塊](#自然插話重構2026-08-09已實作待部署驗證)。
- 2026-08-02（Telegram 漏收事件自動補掃，**已實作，待部署驗證**）：症狀＝「最新的 telegram 沒有轉發」。**relay 端無辜**（delivery_state 3119 筆、`last_polled_pk`=`max(id)`=12494，DB 內全送完）；**斷點在 scraper**——Telegram 已有 `Seele_WW_leak/9824`，DB 最大卻停在 **9823**（08-01 22:29:48+08）。用 `telegram_emoji_refetch` NOTIFY 測活性，scraper **秒回且成功即時抓回 9823** → 連線正常、非卡死。**根因**＝Telethon 漏派 NewMessage 事件（handler 完全沒被呼叫），而 [runner.py](src/telegram_scraper/runner.py) **只在啟動時掃一次歷史**，之後純靠即時事件 → 漏掉就永久漏掉。**非偶發**：以 `created_at - message_date > 5min` 回推「靠重啟才補進來」的比例 7/25 **28/63**、7/26 **59/121**，過去都是剛好有重啟蓋掉問題。**實作**＝每 15 分鐘（`catchup_interval_min`，可熱調整、`<=0` 停用）以各頻道 DB 最大 message_id 為基準做 `iter_messages(reverse=True, offset_id=基準, limit=200)` 增量重掃（已讀 Telethon 1.43.2 原始碼確認 reverse 下 `offset_id` 內部 +1＝不含基準、回傳舊→新保 PK 時序）；即時/補掃/refetch 共用 `process_lock` 序列化；單輪上限由舊往新掃故不留永久空洞；單頻道拋錯不拖垮迴圈。**順修** History log 把 Gamedataleak 訊息全標成 `source_channel=Seele_WW_leak` 的誤導 bug。**驗證**：py_compile 全綠、容器內 stub 煙霧測試 15 項全過、`get_peer_id` 與 DB chat_id 一致、實 DB 基準 Seele=9823/Gamedataleak=2669。**已 commit（`fbd2d3c`）**，`runtime_config.json` 刻意未動（受保護檔，程式端預設已生效）。**下一步**：`docker compose restart telegram-scraper` → 立刻補回 9824 → 觀察 `[CatchUp]` log。詳見 [Telegram 漏收事件自動補掃區塊](#telegram-漏收事件自動補掃2026-08-02-已實作待部署驗證)。

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

## 指令收斂與管理 Dashboard（規劃，未動工）

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

---

## 共用元件索引（已搬到 `AGENTS.md`）

<!-- @meta
id: shared-components-index
type: CONTRACT
status: deprecated
last_confirmed: 2026-09-29
affects: 全專案
-->

> 2026-09-29 起，共用元件表在 `AGENTS.md`「共用元件」，由 `src/test/test_shared_conventions.py` 守衛。這裡只留下各個合法例外的緣由，供追查時參考。

**合法的例外（形狀不同，硬收斂反而更糟，已寫進守衛的 allowlist）**
- `scraper/tools/extract_fingerprint.py` 的時區：scraper 是獨立容器（掛 `./src/scraper` → `/app`），根目錄看不到 `sys_settings`。兩邊都吃 compose 的 `TZ=Asia/Taipei`
- `emoji_text_utils._load_descriptions`：永久快取 + 明確 `reload_descriptions()`，因為字典是被 04:00 排程改寫後主動重載，不是靠 mtime 輪詢
- `ambient_reply._load_ambient_prompt`：多檔疊層且有自己的組裝順序
- `llm_service._load_runtime_config_cached`：讀 pydantic 設定物件，錯誤處理不同

---

## 現況摘要

> 本區只放指標與錨點。詳細內容請跳到對應區塊。
> 若某主題不再是當前主線，應從此區移除或降級，不應永久停留在現況摘要。

| 主軸 | 狀態 | 進度 | 詳見 |
|---|---|---:|---|
| Discord Bot / AI 對話能力 | 已有可用基礎能力 | 80% | [專案架構](#專案-ai-架構總覽) |
| Context / Prompt 優化 | 含 askai 身份感 + 人物對照三輪重構 + 人設深度重構（和風含蓄/30熟女/包容派）+ 智慧女性風格重寫（2026-05-18）+ few-shot 範例檔，待部署驗證 | 97% | [Context 優化](#context--prompt-優化專區) |
| AI 偶爾插話 / 閒聊（功能二） | **Phase A+B 已實作（2026-06-21）**，待 docker 驗證；C（記憶寫入）待做 | 50% | [AI 偶爾插話](#ai-偶爾插話--閒聊功能二規劃中) |
| Persona Agent M7（精簡版發布） | **已上線（2026-09-28）**，觀察一週後決定拿掉 ③；精簡版品質問題討論中 | 85% | [Persona Agent M7](#persona-agent-m7精簡版發布2026-09-28-已上線觀察中) |
| ComfyUI 產圖 + GPU 資源仲裁 | **規劃定案（2026-09-02）**；租約鎖與卸載 helper 已完成（`e13343d`），鎖有漏洞待修；落地細節討論中 | 25% | [ComfyUI 產圖](#comfyui-產圖--gpu-資源仲裁2026-09-02-規劃定案未開工) |
| AI 私聊頻道 + 三層記憶（功能一·姊妹案） | 規劃完成（含道德守門）；人設 prompt 已就位；**本輪暫放旁邊** | 10% | [AI 私聊頻道](#ai-私聊頻道--三層記憶機制規劃中) |
| 使用者指令記憶 (/remember) | 規劃中（與 AI 私聊頻道互補） | 5% | [/remember 規劃](#使用者指令記憶-remember-未來工作) |
| Reaction 統計 / 社群互動玩法 | 規劃中 | 5% | [Reaction TODO](#reaction-統計與社群互動玩法) |
| 點歌機器人（Music Bot） | 已上線運作 | 85% | [點歌機器人](#點歌機器人專區) |
| Telegram relay 可靠性 | 補掃（`fbd2d3c`）與媒體防雷（`77c812d`，已上線、已歸檔）；**2026-09-28 相簿漏圖修正已部署** | 95% | [漏收補掃](#telegram-漏收事件自動補掃2026-08-02-已實作2026-08-18-補上中段缺口盲區2026-09-28-全域鎖改單則訊息鎖修相簿漏圖待部署驗證) |
| 活動自動發布（公告 → Discord 伺服器活動） | **連結指向修正 + 重複活動修正已上線**（9/22 後沒有新的重複、後到的來源會就地升級既有活動）；2026-09-30 遷移不再重複報已處理的重複（`f7d4a14`） | 95% | [活動自動發布修正](#活動自動發布連結指向錯誤--重複建活動2026-09-22-已實作待部署驗證) |
| 程式結構整理（沿用現有架構；`llm/` 依角色分子資料夾） | **`llm/` 重組（`97d7595`）與點名去除反向依賴（`9b0b916`）已 commit 並上線**；**`services/` 分成 relay／events／community（`5e10611`）＋共用 StateDB 連線搬到 `state_db.py`（`2b31828`），9/30 16:38 重啟上線**；P2 未決、P3 暫停、N3 延後 | 90% | [程式結構整理](#程式結構整理2026-09-29-構想grill-中) |
| MCP／搜尋工具化（網頁、公告、論壇） | **構想（2026-09-29）**，grill 第 2 輪；已定先做 MCP、LLM 決定何時查、位置（`services/search/`＋`llm/mcp_server.py`）、關鍵字全文搜尋、論壇索引範圍、`search`＋`fetch` 兩個工具；**設計已全部定案**，待實作 | 15% | [MCP／搜尋工具化](#mcp搜尋工具化2026-09-29-構想grill-中) |
| Telegram 訊息 LLM 過濾 + 隔離區 | **構想（2026-09-28）**，討論中 | 0% | [Telegram 過濾](#telegram-訊息-llm-過濾--隔離區2026-09-28-構想討論中) |
| 週期活動提醒（深塔海墟） | **已實作並 commit（2026-09-29）**，頻道已綁定、身份組已建；待重啟驗證置底收斂 | 90% | [週期活動提醒](#週期活動提醒深塔海墟2026-09-29-已實作待部署驗證) |
| 新成員歡迎訊息（接手 ProBot） | **已實作（2026-09-28）**，待重啟 discord-bot + 綁頻道驗證 | 90% | [新成員歡迎訊息](#新成員歡迎訊息接手-probot2026-09-28-已實作待部署驗證) |
| 跨來源整合（Article/FB/PTT/TG） | 有方向，尚未全面收斂 | 35% | [跨來源整合](#跨來源整合專區) |
| Discord Bot 管理入口 | 規劃中 | 10% | [管理 TODO](#discord-bot-管理入口與指令整理-todo) |

> 已完成 / 過往工作（Bahamut scraper + 反爬基礎設施、幽靈點名核心 + DM、社群 ID 查詢 Phase 0、Telegram Relay、Music Bot 完整實作等）詳見 `TODO-completed.md`。
>
> **2026-08-18 歸檔**：活動公告自動建活動（17 筆已建立）、Telegram 自訂表情 → Discord App Emoji（10 個已上傳）、Telegram 多頻道來源 + 轉發去重（Gamedataleak 205 筆），三者皆已上線運作，連同 2026-06-25 ~ 2026-07-25 的盤點紀錄一併移入 `TODO-completed.md`。

---

## 程式結構整理（2026-09-29 構想，grill 中）

<!-- @meta
id: code-structure-reorg
type: TODO
status: draft
last_confirmed: 2026-09-30
affects: src/ 全部資料夾、mcp-search-tools（R2-Q5 程式放哪）、test_shared_conventions、settings/logging.json
-->

**需求（使用者 2026-09-29 提出，從 MCP 討論延伸）**
- 覺得程式很亂，想知道從哪裡開始整理。
- 傾向「依功能分資料夾」（改一個功能只看受影響的程式），但也要有整體架構規劃，否則程式分散各處很難維護。

**機制本質**：依功能分（每個功能一個資料夾，擁有自己的指令、服務、設定、prompt）與依層分（現況：`commands/`、`services/`、`llm/`、`settings/`、`sys_settings/`）不是二選一；常見做法是「功能資料夾＋一個共用核心」，並用規則限制誰可以 import 誰。

**查證事實（2026-09-29，唯讀盤點）**
- **規模**：`src/` 約 5.66 萬行 Python（含另外兩個 container 的 `scraper/` 8.7k、`telegram_scraper/` 1.9k）。bot 端依層分：`commands/` 11 檔 8.4k 行、`services/` 19 檔 10.1k、`llm/` 38 檔 12.7k、`utils/` 1.1k、`sys_settings/` 0.9k、`test/` 8.9k（29 個測試檔平放）。
- **已經是功能資料夾、可當範本**：`music/`（9 檔，只依賴外面的 `utils.dm_notifier`）、`llm/persona_agent/`（8 檔）。
- **一檔多功能**：
  - `commands/llm_commands.py` 1,533 行，含 4 個功能：/askai、人格萃取、persona_agent_test、AI 日記。
  - `commands/management_commands.py` 1,179 行：伺服器管理、自介面板、印象審核。
  - `commands/user_commands.py`：關鍵字監看、/forget_tag、物價查詢。
  - `commands/article_commands.py`：六個轉發來源的手動指令。
  - `services/llm_service.py`：核心 LLM 客戶端，混著 /askai 的 prompt 組裝（`generate_reply` 約 25 個參數，給四個功能用）。
  - `sys_settings/llm_settings.py`：7 個 settings class，屬於不同功能。
  - `utils/utils.py`：雜物袋。
  - `settings/channel_registry.py`：程式碼放在資料夾裡，還含三個功能的 hook。
- **`discord_bot.py` 876 行**：`on_ready` 約 320 行，塞了 04:00 維護（①～⑤ 全部編排，171～344 行）、00:00 日記排程、3 個 flush loop、公告／PTT 自動啟動（直接改 cog 內部屬性）、Telegram 物件組裝、echo 跟風、fixupx、活動墓碑、reaction 統計 hook。背景迴圈有的在 `on_ready` 啟動，有的在 `cog_load` 啟動，不一致。
- **功能散佈**：公告轉發 11 檔、/askai 約 20 檔、插話約 18 檔（`discord_bot.py` 裡有 6 處）、persona agent 15 檔、人格萃取 10 檔、日記 8 檔（跨 4 個資料夾）。聚在一起的只有點歌、網頁查詢、Telegram（但全塞在一個 2,099 行的檔）。
- **轉發（公告／FB／PTT／巴哈／IT／Telegram）共用一條管線**（`base_monitor`、StateDB、`notify_server`、`post_to_channel`），適合整組放一個「轉發」資料夾＋轉發共用層，不適合每個來源各自獨立；也跟既有的「跨來源整合」規劃（`cross-source-integration`，P0 未動）方向一致。
- **import 熱點**：被最多模組 import 的是 `sys_settings.llm_settings`（29）、`utils.utils`（18）、`services.llm_service`（13）。兩個真的循環 import（`article_monitor`↔`event_scheduler`、`rollcall_commands`↔`rollcall_service`，都靠延遲 import 繞過）。跨功能拿私有函式：日記→`ambient_reply._get_llm`、persona agent→`personality_extractor` 三個私有函式、巴哈轉發直接對 StateDB 下 SQL。`llm/` 與 `services/` 互相 import（層次兩個方向都有）。
- **搬檔最大的地雷**：`services/state_db.py` 用 `Path(__file__).parent/"sent_articles.db"` 找資料庫，**搬這個檔會悄悄開一個空的新 DB，導致大量重發**。其他依 `__file__` 找資料的：`base_monitor`、`rollcall_service`、`event_scheduler`（`../scraper/articles.db`）、`logger_config`、`music/ytdl`。約 20 處用相對工作目錄讀 `config.json`，約 15 處寫死 `/app/settings/prompts/*`。**資料檔跟程式碼混放**（`services/sent_articles.db`、`settings/*_runtime.json`），`.gitignore` 依路徑排除，搬了沒更新會把使用者資料 commit 進去。
- **其他會跟著搬檔變動的**：`discord_bot.py` 的 `COMMAND_MODULES` 字串、`notify_server._RELAY_SOURCES` 的模組字串、7 個 `mock.patch` 字串、`test_shared_conventions` 的 `allowed` 路徑、AGENTS.md 共用元件表約 13 個路徑、本檔約 160 處路徑。**不受影響**：持久化按鈕的 `custom_id`（不含模組路徑）、`get_cog` 用的是 class 名稱。啟動 gate 與測試 log 導向都假設測試在 `test/` 底下。
- **沒有測試的功能**：點名、社群 ID 查詢、點歌、自介／印象、交易、關鍵字監看、PTT、巴哈、FB（只有 embed）、日記、人格萃取、記憶、聊天紀錄寫入、頻道綁定。**搬這些功能時沒有測試保護**。
- **完整盤點補充**：① bot 程式跨 container import `telegram_scraper.tg_config`（`telegram_relay_service.py`、`channel_registry.py`），功能邊界要處理這條線；② `llm/__init__.py` 會預先載入 `context_retriever`、`persona_card_builder`、`retrievers.web`，import 任何 `llm.*` 都會連帶載入這些；③ `test_shared_conventions` 掃描時跳過 `test/`，如果測試改放進功能資料夾，守衛規則會開始掃到測試檔；④「專案 AI 架構總覽」區塊是依層寫的檔案清單，而且已過時（還寫 Ollama），結構定案後要重寫。
- **既有規劃**：「指令收斂與 Dashboard」的 `/persona` 子指令群，正好對應一個 persona 功能資料夾（萃取＋agent＋日記＋forget_tag）；該區塊寫 28 個指令已過時，實際是 21 個斜線指令＋2 個前綴指令。「管理入口 TODO」的權限檢查統一（5 種寫法，曾寫過又撤回）屬於核心。

**待決問題（grill 第 1 輪，2026-09-29；每題附建議）**
- **S1 「亂」的痛點**（可複選）：a 找不到某功能的程式在哪／b 改一個功能要動好幾個資料夾／c 單一檔案太大、一檔塞多個功能／d 重複的輪子／e `discord_bot.py` 什麼都塞／f 不敢改，怕牽動別的功能。建議（推測）：b＋c＋e。這題決定從哪裡下手。
- **S2 整理方式**：A 一次大搬家／B 漸進：先畫目標地圖，新功能直接照新結構，舊功能下次要改時順便搬／C 漸進但主動排程：每次挑一個功能搬。建議 B＋C：先畫地圖、以 MCP 搜尋當第一個試點，之後每次主動搬一個最痛的功能。不一次大搬的理由：搬檔會牽動 `settings/logging.json` 的 logger 名稱、`test_shared_conventions` 的 `allowed` 路徑、交接文件裡的連結，一次全搬很難檢查，出錯也難定位。
- **S3 分法原則**：A 純依功能／B 維持依層（現況）／C 混合：功能資料夾＋共用核心（LLM 客戶端、GPU 鎖、pgvector、StateDB、`post_to_channel`、面板置底、頻道綁定、log、時區）。建議 C，並加兩條規則：功能之間不直接 import 對方內部，只透過核心或對方公開的入口；核心不 import 任何功能。這兩條寫進 `test_shared_conventions` 守衛。
- **S4 跟 MCP 的關係**：A MCP 先暫停，等結構定完再做／B MCP 搜尋照新結構當第一個試點（R2-Q2～Q4 照常討論，R2-Q5「程式放哪」等這邊定）。建議 B。

**架構草案 v1（已被使用者否決，2026-09-29）**：另起一套 `core/`＋依領域分（relay、schedule、ai、community…）。否決理由（使用者）：`llm/` 本來就是 AI 領域，草案把它拆成 `core/llm` 和 `ai/`；社群功能本來就是 Discord 服務，草案把它和 Discord 共用元件拆開。**應該從現有架構出發，指出不合理或可精簡的地方，用最小修改處理。**

**架構建議 v2：沿用現有架構，只修放錯與過大的地方（待確認）**
- 我理解的現有架構：`llm/`＝AI 領域（所有 AI 相關）；`commands/`＝Discord 指令、`services/`＝Discord 服務的業務邏輯（轉發、活動、點名、社群…）；`music/`＝點歌（獨立）；`utils/`＝共用工具；`sys_settings/`＝設定程式、`settings/`＝資料與 prompt；`scraper/`、`telegram_scraper/`＝其他 container；`discord_bot.py`＝入口。
- 不合理或可精簡的地方（每項都是最小修改，依價值排序）：
  - **P1 AI 的程式放在 `services/`**：`services/llm_service.py`（LLM 客戶端）、`services/memory_service.py`（AI 記憶）搬進 `llm/`。順便解掉 `llm/` 與 `services/` 互相 import。牽動約 13 個 import。
  - **P2 一檔多功能，拆檔但留在同一個資料夾**：`commands/llm_commands.py` 拆成 /askai 與人格相關（萃取、agent 測試、日記）兩個檔；`management_commands.py` 拆出自介面板；`user_commands.py` 的 `/forget_tag` 併到人格指令、物價併到 `trade_commands.py`。cog class 名稱不變，`get_cog` 不受影響；`COMMAND_MODULES` 要加項。
  - **P3 `discord_bot.py` 瘦身**：04:00 維護編排搬進 `llm/`、00:00 日記排程搬進 `llm/ambient/ambient_diary.py`、Telegram 組裝搬進 `telegram_relay_service`、公告／PTT 自動啟動搬回 `article_commands` 的 `cog_load`。碰到每晚的維護排程，要單獨排、先補測試。
  - **P4 `telegram_relay_service.py`（2,099 行）拆成 `services/relay/telegram_relay/` 子資料夾**：等做「Telegram LLM 過濾」時順便拆，那個功能本來就要改這個檔。
  - **P5 新功能照現有架構放**：公告／論壇搜尋放 `llm/retrievers/`（網頁查詢已經在 `llm/retrievers/web/`，同層加 `official/`、`forum/`）；MCP 殼放頂層 `mcp_server/`（跟 `discord_bot.py` 一樣是入口）。這也回答了 MCP 區塊的 R2-Q5。
  - **使用者回覆（2026-09-29）**：
  - **P1 否決**：`services/` 就是「服務」，`llm_service.py` 是 LLM 服務，留在 `services/`。
  - **`llm/` 的定義（使用者）**：處理 RAG、MCP 等 LLM 相關技術，也就是跟 LLM 相關的任何組裝、優化、橋接；裡面可以有子資料夾。子資料夾怎麼分要討論（見下方 L1～L4）。
  - **P3 修正**：同意 `discord_bot.py` 太胖，但入口本來就該做入口的事；不另拆一個排程程式，入口仍由 `discord_bot.py` 管。我的理解（待確認）：`discord_bot.py` 保留「什麼時候跑什麼、步驟順序、啟動順序、事件接線」，每個步驟裡面的實作細節（例：04:00 第 ③ 步讀略過名單、把結果塞進 cog）搬到各自的模組，入口只剩一行呼叫。
  - P5 原本打算改成獨立 `src/search/`；**照使用者對 `llm/` 的定義（RAG、MCP 屬於 `llm/`），撤回這個修正**，搜尋留在 `llm/retrievers/`。
- 可選、不急：轉發相關 7 個檔集中到 `services/` 底下一個子資料夾（會碰到 `state_db` 路徑地雷與 `notify_server` 的模組字串）；`settings/channel_registry.py` 是程式碼放在資料夾裡；`utils/utils.py` 裡各功能專屬的頻道 getter。

**既有決定（本輪才讀到，v2 必須遵守；原文在 ComfyUI 區塊「檔名正名」）**
- 已同意的檔名正名（原約定等 ComfyUI 步驟 2～4 完成後一起改）：`llm_http_client` → `http_client`、`safe_llm_embedding` → `embedding_client`、`chat_persistence` → `store_chat`、`diary_reflection` → `ambient_diary`；`lemonade_gate` 待定（等它真的管 GPU 資源再改）。
- **已決定不做 `llm/`、`services/` 的資料夾重組**（約 160 個 import 點，效益只有排序好看）。子資料夾判準：「≥6 檔／有封裝邊界／可預期會長」滿足其一（`persona_agent/`、`retrievers/web/` 是範例）。**ComfyUI 另開 `src/imagegen/`，不塞進 `llm/`**，避免 `llm/` 變成「AI 相關雜物間」。
- 對 v2 的影響：P1 只搬一個放錯的檔，不算重組，可以；P4 Telegram 子資料夾符合判準（有封裝邊界、2,099 行）；**P5 搜尋放 `llm/retrievers/` 要重新考慮**：搜尋也給 MCP 用、不只給 AI 用，照 imagegen 的原則可能該獨立成 `src/search/`（下一輪問）。

**命名問題（使用者 2026-09-29 提出「檔案命名也是問題」；grill 中）**
- 盤點（唯讀）：
  - **名字說 A、內容是 B（會誤導）**：`commands/forum_monitor.py` 實際是交易確認（論壇貼文按表情開交易 thread，`TransactionView`）；`commands/test_commands.py` 是開發用測試指令，跟 `test/` 撞名；`llm/prompt_builder.py` 只有 `build_askai_prompt_log`，組的是 /askai 的 log，不是 prompt（真正組 prompt 的在 `llm_service._build_prompt_bundle`）。
  - **同一個詞三種意思**：「monitor」同時指轉發（`*_monitor.py`）、交易確認（`forum_monitor`）、關鍵字監看（`user_commands` 的 `StopAllMonitoringView`、`monitored_channels.json`）。
  - **名字太籠統，看不出內容**：`utils/utils.py`（權限檢查、`ChannelConfig`、安全回覆、分頁、各功能的頻道 getter）、`commands/user_commands.py`（關鍵字監看＋`/forget_tag`＋物價）、`commands/llm_commands.py`、`commands/management_commands.py`。
  - **不一致但不誤導**：`settings/`（資料檔）與 `sys_settings/`（設定程式）名字分不出誰是誰，且 `settings/channel_registry.py` 是程式碼放在資料夾；`personality_*` 與 `persona_*` 混用；`services/` 有的檔帶 `_service` 字尾、有的沒有。
  - 改名的代價：import 點、`COMMAND_MODULES` 字串、`mock.patch` 字串、log 裡的模組名稱（查舊 log 要用舊名）、`AGENTS.md` 與本檔的路徑。**不受影響**：cog class 名稱（`get_cog`）、按鈕 `custom_id`。
- 待決問題（grill 第 2 輪，每題附建議）：
  - **N1 改名原則**：A 只改會誤導的＋既有正名表；不一致的不改舊檔，只在 `AGENTS.md` 訂命名慣例給新檔／B 全面統一／C 都不改。建議 A，延續「只改騙人的名字、不為好看搬家」的既有決定。
  - **N2 會誤導的三個**：`forum_monitor.py` → `trade_confirm_commands.py`（不併進 845 行的 `trade_commands.py`，免得又變大檔）；`test_commands.py` → `dev_commands.py`；`prompt_builder.py` → `askai_log.py`。建議都改；純改名、行為不變。
  - **N3 籠統的名字**：`utils/utils.py` 拆成 `permissions.py`（`check_guild`／`check_role`）、`channel_config.py`（`ChannelConfig`＋頻道 getter）、`interaction.py`（安全回覆、分頁），約 18 個 import 點；`settings/channel_registry.py` 搬到 `utils/`（它是共用元件，照 AGENTS.md 應放 `utils/`），名稱不變；`user_commands`、`llm_commands`、`management_commands` 在 P2 拆檔時一起取新名。建議都做，但排在純改名之後。
  - **N4 什麼時候改**：A 純改名（N2＋正名表）獨立一批，跟第 1、3 項一起做；拆檔（N3、P2）另一批／B 全部等 P2 一起。建議 A。正名表原約定等 ComfyUI，但除了 `lemonade_gate` 其餘四個跟 ComfyUI 無關，建議提前；你想維持原約定也可以。
- **使用者回覆（2026-09-29）**：
  - N1：同意 A（只改會誤導的＋正名表；不一致的只訂慣例給新檔）。
  - N2：**三個都不改**。`forum_monitor.py` 本來就是監控聊天室的 cog，交易是後來加的用途；`test_commands.py` 意思沒錯（啟動 gate 只掃 `test/`，技術上也不衝突）；`prompt_builder.py` 見下方 L3：名字沒錯，是內容放錯（真正的 prompt 組裝在 `services/llm_service.py`）。
  - N3：延後，這次要改的已經夠多。
  - N4：N2 不改後只剩正名表，**維持原約定**（等 ComfyUI 步驟 2～4）。

**`llm/` 資料夾討論（grill 第 3 輪，2026-09-29；每題附建議）**
- 現況依角色分（照使用者的定義歸類，26 個平放檔＋`persona_agent/`、`retrievers/web/`）：
  - 橋接（接 LLM 後端）：`llm_http_client`、`safe_llm_embedding`、`lemonade_gate`、`vision_image`、`logger_factory`
  - 組裝（把資料組成 prompt）：`prompt_builder`（目前只組 /askai 的 log）、`prompt_files`、`chat_line`、`persona_card_builder`
  - RAG（存與找）：`context_retriever`、`tokenization`、`retrievers/web/`、`chat_persistence`、`raw_message_store`、`member_profile_store`、`ai_interactions_store`、`sticker_cache`、`emoji_text_utils`
  - AI 功能：`ambient_reply`、`ambient_hooks`、`ambient_memory`、`diary_reflection`、`personality_extractor`、`preference_extractor`、`signature_tag_extractor`、`reaction_classifier`、`persona_agent/`
- **L1 AI 功能本身（插話、日記、人格萃取、persona agent）也留在 `llm/` 嗎**：A 留（現況，符合「llm 就是跟 AI 相關」）／B 搬到別處。建議 A：搬走牽動最大，也沒有更合適的地方。
- **L2 子資料夾分到什麼程度**：A 維持平放，只有新東西開子資料夾（搜尋、MCP）／B 依上面四個角色全部收進子資料夾／C 平放為主，某一群符合既有判準（≥6 檔、有封裝邊界、會長大）時，下次改到它才收成子資料夾（例：插話 `ambient_*` 加日記）。建議 A＋C：既有決定是不做 `llm/` 重組（約 160 個 import 點）。
- **L3 真正的 prompt 組裝搬進 `llm/prompt_builder.py`**：`services/llm_service.py` 的 `_build_prompt_bundle`（約 220 行，/askai、插話、日記、印象審核共用）是「組裝」，照你的定義屬於 `llm/`。A 搬進 `prompt_builder.py`（名字剛好對，現在那個檔只組 log，一起放）；`llm_service` 留在 `services/`，只做服務（連線、載模型、呼叫、重試）／B 不動。建議 A。這也是 `prompt_builder.py`「名字沒錯、內容放錯」的解法。
- **L4 MCP 與搜尋放哪**：搜尋放 `llm/retrievers/official/`、`llm/retrievers/forum/`（跟 `web/` 同層）；MCP 殼放 `llm/mcp/`，用 `python -m llm.mcp` 啟動（子套件不會蓋掉安裝的 `mcp` 套件，只有頂層的 `src/mcp/` 會）。**坑**：`llm/__init__.py` 會預先載入 `context_retriever` 等模組（連帶 llama_index），MCP 一啟動就全部載入，慢又吃記憶體；解法是把 `llm/__init__.py` 改成用到才載入（對外的 `from llm import …` 寫法不變）。建議照這樣做。
- **使用者回覆（2026-09-29）**：
  - L1：同意，AI 功能留在 `llm/`。
  - L2：**要依「LLM 會做的事」分子資料夾**（例：還有資料整理的部分、`persona_card_builder.py` 還放在外面）。等於**重開**「不做 `llm/` 重組」的既有決定，由使用者拍板。
  - L3：使用者問：`prompt_builder.py` 組的是 log，為什麼不放進 `logger_factory.py`？（不確定該不該，只覺得名稱讓人誤會）
  - L4：撈本地資料庫的一律放 `localdata/`（不照來源分 official／forum）；問 MCP server 該放 `services/` 還是 `llm/`。
- 查證：`logger_factory.py`（54 行）只有 `get_or_create_file_logger`，負責 prompt 除錯檔（askai、插話、日記）寫到哪、怎麼輪替；`build_askai_prompt_log` 只有 `commands/llm_commands.py:766` 一處使用（經 `llm/__init__.py` 轉出）。`llm` 相關 import 共 162 行、分布在 43 個檔（其中 76 行在 `llm/` 內部），`mock.patch` 字串 1 個；**`llm/` 裡沒有用檔案位置找資料的地雷**（6 個都在 `llm/` 外）。風險在函式內的延遲 import：漏改不會在啟動時報錯，要等跑到那段程式（例：04:00 維護）才壞。

**`llm/` 資料夾討論（grill 第 4 輪，2026-09-29；每題附建議）**
- **L2a 依角色分的子資料夾草案**：
  - `client/` 橋接後端：`llm_http_client`、`safe_llm_embedding`、`lemonade_gate`
  - `preprocess/` 資料整理：`chat_line`、`emoji_text_utils`、`sticker_cache`、`vision_image`、`tokenization`（之後抽出的共用文字清理也放這）
  - `prompt/` 組裝：`prompt_builder`（真正的 prompt 組裝，見 L3）、`prompt_files`
  - `storage/` 存：`chat_persistence`、`raw_message_store`、`member_profile_store`、`ai_interactions_store`
  - `retrievers/` 找：`context_retriever`、`web/`、`localdata/`（新）
  - `ambient/` 插話：`ambient_reply`、`ambient_hooks`、`ambient_memory`、`diary_reflection`
  - `persona/` 人格：`personality_extractor`、`preference_extractor`、`signature_tag_extractor`、`reaction_classifier`、`persona_card_builder`、`agent/`（原 `persona_agent/`）
  - `logger_factory.py` 留在 `llm/` 頂層（prompt 除錯 log）
  - 既有正名表在搬家時一起做（例：`client/http_client.py`、`client/embedding_client.py`、`storage/store_chat.py`、`ambient/ambient_diary.py`），import 路徑只改一次；`lemonade_gate` 照原約定暫不改名。
  - 建議照這份，資料夾名稱可以再改。`persona_card_builder` 放 `persona/`：它也被 /askai、插話的 prompt 組裝使用，但內容是人格卡。
- **L2b 怎麼搬**：A 一次搬完（純搬家＋改 import，行為不變）／B 分批，每次一個子資料夾。建議 A，但先加一個守衛測試：掃所有 import（含函式內的延遲 import），每一個都要找得到模組，漏改就在啟動 gate 擋下。搬完跑完整測試，挑維護時段以外重啟。時機：在第 1、3 項之後、寫 MCP 之前（MCP 直接寫在新位置）。
- **L3 兩件事分開放**：`build_askai_prompt_log`（組 /askai 的除錯 log 內容）移進 `logger_factory.py`，讓它成為「prompt 除錯 log」的專屬檔（寫到哪＋寫什麼）；`prompt_builder.py` 改放真正的 prompt 組裝（`services/llm_service.py` 的 `_build_prompt_bundle`），名實相符。建議兩件都做。
- **L4 MCP server 放 `services/`**：伺服器外殼是「服務」，跟 `services/notify_server.py`（對 scraper 提供 HTTP 介面）同類；查本地資料的工具本體是 RAG，放 `llm/retrievers/localdata/`。剛好符合「`services/` 是服務、`llm/` 是 LLM 技術」兩個定義。建議 `services/mcp_server.py`，用 `python -m services.mcp_server` 啟動。不論放哪，`llm/__init__.py` 都要改成用到才載入（MCP 會 import `llm.retrievers.localdata`，會觸發它）。
- **P3 確認**：上面對 `discord_bot.py` 的理解對嗎？另外，cog 自己啟動的迴圈（週期提醒、點名、/askai 排隊）要不要也改由 `discord_bot.py` 登記？建議不要：那些是功能內部的計時器；由入口統一編排的只限跨功能的排程（04:00 維護、00:00 日記、轉發啟動）。

**使用者回覆（2026-09-29，第 4 輪）**
- **L2a、L2b、L3 核可**；「先改核可的地方，還沒確認的先不動」→ L4、P3、第 1／3 項（含刪 FB／IT 輪詢）、N3 都不動。
- 子 agent 要不要分派交給 Claude 判斷，**最重要的是正確性**。本輪分工：搬家與改寫由主 agent 一次做完（43 個檔案互相牽連，拆給多個 agent 會改到同一批檔案、做法也可能不一致）；子 agent 只做唯讀的獨立複查（沒參與撰寫，比較容易看出漏掉的地方）。
- 使用者表示沒看過 S1～S4（題目在 session 重啟前發出，可能沒顯示），本輪重新列出。

**`llm/` 重組＋L3 實作（2026-09-29；15:26 套用、15:28 重啟、已驗證，未 commit）**
- **做法：先在獨立的 git worktree 改，不動 bot 正在讀的 `./src`**。理由：bot 以 `./src` 即時掛載執行，函式內的延遲 import 要到執行那段才讀檔；檔案一搬、bot 還沒重啟，跑到那段（例：00:00 日記、04:00 維護）就 ImportError。所以「套用到 `./src`」和「重啟」要一起做。
- **新舊路徑對照（舊 → 新，都在 `src/llm/` 底下）**：
  - `llm_http_client.py` → `client/http_client.py`；`safe_llm_embedding.py` → `client/embedding_client.py`；`lemonade_gate.py` → `client/lemonade_gate.py`
  - `chat_line.py`、`emoji_text_utils.py`、`sticker_cache.py`、`vision_image.py`、`tokenization.py` → `preprocess/` 同名
  - `prompt_files.py` → `prompt/prompt_files.py`；（新）`prompt/prompt_builder.py`＝真正的 prompt 組裝
  - `chat_persistence.py` → `storage/store_chat.py`；`raw_message_store.py`、`member_profile_store.py`、`ai_interactions_store.py` → `storage/` 同名
  - `context_retriever.py` → `retrievers/context_retriever.py`（`retrievers/web/` 不動）
  - `ambient_reply.py`、`ambient_hooks.py`、`ambient_memory.py` → `ambient/` 同名；`diary_reflection.py` → `ambient/ambient_diary.py`
  - `personality_extractor.py`、`preference_extractor.py`、`signature_tag_extractor.py`、`reaction_classifier.py`、`persona_card_builder.py` → `persona/` 同名；`persona_agent/` → `persona/agent/`
  - 舊 `prompt_builder.py`（只組 /askai 除錯 log）→ 內容併入 `logger_factory.py`，檔案刪除
  - 正名表中的 `llm_http_client`、`safe_llm_embedding`、`chat_persistence`、`diary_reflection` 四項在這次一起完成；`lemonade_gate` 照原約定不改名。
- **L3**：
  - `build_askai_prompt_log` 移進 `llm/logger_factory.py`，**不再從 `llm/__init__.py` 轉出**，唯一呼叫端 `commands/llm_commands.py` 改成直接 import。原因：若改由 `llm/__init__` 轉出，import `llm` 會多載入 `utils.logger_config`（載入就套用 log 設定），scripts 與之後的 MCP 行程都會多這個副作用；實測搬家前 import `llm` 不會載入它。
  - `_build_prompt_bundle`、`PromptBundle`、`_sanitize_text` 搬到 `llm/prompt/prompt_builder.py`，成為 `build_prompt_bundle(safety_rules=…, latest_open_tag=…, latest_close_tag=…, 其餘參數不變)`；`LLMService.generate_reply` 傳入原本的 `self.context_safety_rules` 與 `self.settings.latest_*_tag`。
- **新增守衛 `src/test/test_import_resolution.py`**：只讀原始碼（AST），不實際 import。檢查四件事：所有專案 import（含函式內的延遲 import、相對 import）都找得到模組；`from X import 名稱` 的名稱存在（只寫在 `if TYPE_CHECKING:` 裡的不算）；模組字串（`mock.patch` 目標、`notify_server` 的模組字串、`COMMAND_MODULES`）指向存在的模組與第一層名稱；模組頂層別名的屬性讀取（含多層，如 `llm.retrievers.web.x`）存在。**它跑在啟動 gate，誤判會讓 bot 起不來，所以寧可少抓、不可誤判**：同名變數被重新賦值的範圍內不檢查、結尾是常見副檔名的字串不檢查、只剩 `__pycache__` 的資料夾不算套件；真的不是模組的字串加進 `_NOT_MODULE_STRINGS`（目前 1 筆：`test_logger_config` 刻意虛構的 logger 名稱）。自測 11 項，另有「確實掃到核心檔案」的斷言。已知抓不到（目前程式裡都沒有）：函式內 import 的別名屬性、`import_module` 的相對寫法、f-string 組出的路徑、`notify_server` 裡 `cls`／`method` 欄位。
- **新增 `src/test/test_prompt_builder.py`**：釘住 prompt 組裝的輸出約定（兩則 message、區塊順序、`from` 屬性、去 `\x00`、紀錄與送出同源、沒 context 不放開場、身份錨點）。突變驗證：開合標籤對調、不去 `\x00`、兩個區塊對調 → 都會紅。
- **其他同步**：`test_shared_conventions` 的 canonical 與 allowed 路徑；`AGENTS.md` 共用元件表 3 列；`persona_agent_prompt.json` 的 `_comment`（程式只讀特定欄位，不影響行為）；21 處註解／docstring 裡的舊模組名；`llm_service.py` 搬走方法後多出的空行。**`docker/discord_bot/requirements.txt` 刻意不改**：它有 2 行註解提到舊路徑，但套件大多沒鎖版本，檔案一改，下次 build 就會重抓最新版；等之後因為加 `mcp` 套件而必須改它時，再一起更新註解。**刻意不改**：`ambient_diary.py` 的 `caller="diary_reflection"` 標籤、`store_chat.py` 的 log 訊息前綴 `chat_persistence:`（執行期字串，改了會改到 log 內容）。
- **驗證**（都在容器 `/tmp` 的副本跑，不影響正在跑的 bot）：
  - 搬家前基準：627 項測試全過；89 個模組各自在全新行程 import 全部成功；守衛通過。
  - 守衛突變：函式內延遲 import 打錯字、`mock.patch` 字串指錯、`llm/__init__` 少轉出名稱、`notify_server` 模組字串打錯 → 四種都變紅，還原後恢復通過。
  - 搬家後：627 項測試全過；95 個模組（多出 6 個子資料夾的 `__init__`）各自 import 全部成功，舊的 89 個全都對得到新位置；守衛通過。
  - prompt 組裝差異比對：14 個選填參數的全部組合 × chat_context 三種狀態＝49,152 組，經 `generate_reply` 實際走一遍（模型呼叫換成假物件），比對送出的 messages 與 log 文字，**搬家前後逐字相同**；故意把開合標籤對調後 49,152 組全部不同，證明比對有效。
  - 子 agent 獨立複查（兩位，重點不同，都是唯讀）：**沒有會在執行期出錯的殘留，搬家與 L3 沒有行為差異、沒有新的循環 import**。AST 比對 59 個改動檔，54 個除路徑外完全相同，其餘 5 個的差異正好是預期的修改；程式外的資料（config、runtime json、prompt、StateDB）沒有存模組路徑；logger 名稱會變，但只影響 log 行裡的 `[模組]` 欄，沒有程式或工具依它過濾。複查指出後已修正：守衛的四類誤判與四類漏抓（見上）、prompt 組裝缺常駐測試、9 處註解、`AGENTS.md` 一列、`requirements.txt` 還原、多餘空行。
  - 修正後（最終版）重跑：**637 項測試全過**（多出的 10 項是守衛自測與 prompt 組裝測試）；95 個模組獨立 import 全成功；prompt 組裝 49,152 組仍逐字相同；守衛 7 種突變都會紅，搬家前與搬家後的程式都沒有誤判。
  - patch 已產生並確認可乾淨套用：71 個檔案（新增 9、刪除 1、修改 30、搬移 31）。
- **套用步驟**（時間由使用者決定，避開 00:00 日記與 04:00～07:30 維護）：① 套用工作副本產生的 patch（scratchpad `llm_reorg.patch`）到 `./src`；② 刪除舊的 `src/llm/persona_agent/`（套用後只剩 `__pycache__`，不是使用者資料；留著會變成一個空的套件）；③ 立刻在容器跑正式測試指令；④ 使用者執行 `docker compose restart discord-bot`（啟動 gate 會再跑一次全部測試）；⑤ 執行文件更新腳本（scratchpad `apply_doc_paths.py`），把本檔其他區塊與記憶裡現行說明的舊路徑換成新路徑（開頭盤點紀錄與本區塊不動）。③ 紅就用 `git apply -R` 還原。套用後 `git status` 會出現搬移的檔案，commit 等使用者指示。

**第 1、3 項（2026-09-29 查證；第 7 輪使用者核可「做」，已完成，見第 7 輪紀錄）**
- **第 1 項縮小成「只加測試、不改程式」**：在 v2 架構下這 6 個檔都不會搬，改路徑是多餘的變動。改成加一個測試，釘住 6 個資料檔的實際位置：`services/state_db.py:22`（`sent_articles.db`）、`services/base_monitor.py:31`（`article_runtime.json`）、`services/rollcall_service.py:21`（`rollcall_runtime.json`）、`services/event_scheduler.py:69`（`scraper/articles.db`）、`utils/logger_config.py:22`（`logging.json`）、`music/ytdl.py:12`（`music/cache`）。以後誰搬了這些檔，啟動 gate 就擋下來（bot 起不來），而不是默默開空 DB、把舊文重發一遍。
- **第 3 項確認是死碼的 4 處**（已 grep 全 repo，含字串用法）：
  - `services/fb_monitor.py:288` `start_fb_monitoring`：FB 輪詢迴圈，沒有任何呼叫處（FB 已改由 scraper 推送，`notify_server` 以字串呼叫的是 `check_and_send_fb_posts`，保留）。
  - `services/it_article_monitor.py:216` `start_monitoring`：IT 輪詢迴圈，沒有呼叫處（`notify_server` 用的是 `check_and_send_new`、`ensure_seeded`，保留）。
  - `commands/article_commands.py:108、110`：`fb_monitoring_task`、`it_article_monitoring_task` 只有設成 `None`，沒有任何地方讀（`discord_bot.py` 以字串讀的是 `monitoring_task`、`ptt_monitoring_task`，保留）。
  - `commands/forum_monitor.py:322`：`from commands.user_commands import UserCommands` 匯入後沒用到（下一行用 `get_cog('UserCommands')`）。
  - 原本列的 `chat_persistence` 延遲 import **不是死碼**（還在用），移出清單。
  - 要確認：刪掉 FB／IT 的輪詢迴圈，等於確定只走推送、不留輪詢當備援。

**使用者回覆（2026-09-29，第 5 輪）**：現在就套用（15:26 已套用）；**P3 先別動**；問「不是要改名成 agents？」→ 說明 `persona_agent/` 已搬成 `llm/persona/agent/`（L2a 核可的單數 `agent`），舊位置只剩 `__pycache__`；問「L4 不是討論過了？」→ 已定的是「撈本地資料庫的放 `llm/retrievers/localdata/`」與「`llm/` 處理 RAG、MCP 等 LLM 技術」，MCP server 外殼放 `services/` 還是 `llm/` 是使用者問我、我建議 `services/`，尚待使用者選。

**使用者回覆（2026-09-29，第 6 輪）**：已重啟；**名稱維持 `agent`**；~~L4 定案：MCP server 外殼放 `services/`~~（第 7 輪使用者重新提出，改為討論中，見下方）。使用者問「MCP 只限定給 LLM 用嗎？」→ 協定本身是為 LLM 應用設計的（客戶端是 Claude Code 這類 AI 工具，讓模型發現並呼叫工具）；一般程式技術上也能呼叫，但那種需求用普通 HTTP API 更簡單。

**重啟後驗證（15:28～15:30）**：啟動 gate 637 項全過；12 個指令模組全部載入、21 個斜線指令同步、各排程（04:00 人格萃取、00:00 日記、flush 迴圈）都已啟動；15:26 之後 `discord_bot.log` 沒有任何 ERROR 或 import 錯誤（套用到重啟的 2 分鐘空窗也沒有）。「Telegram 啟動補償 373 筆」與今天 06:22、09:58、10:34 三次重啟的數字相同，是既有問題（相簿晚到成員不寫發送紀錄，見 Telegram 過濾區塊），處理結果全是「已過時效，略過」或「略過空訊息」，**沒有重發**。文件路徑更新腳本已執行（本檔其他區塊與記憶的現行說明改成新路徑）；工作副本與容器 `/tmp` 暫存已清除。舊的 `src/llm/persona_agent/` 只剩 `__pycache__`，要不要刪等使用者決定（留著無害，守衛也不把它當套件）。

**使用者回覆與實作（2026-09-29，第 7 輪）**
- **舊資料夾 `src/llm/persona_agent/` 已刪除**（使用者核可；裡面只有 16 個 `__pycache__` 快取檔）。
- **S1～S4 結案**（使用者同意）：S1 痛點＝一檔多功能、`discord_bot.py` 太胖、命名、`llm/` 分類；S2 `llm/` 一次搬完，其他部分等要改到時再用最小修改處理；S3 沿用使用者的架構（`services/` 放服務、`llm/` 放 LLM 技術）；S4 MCP 直接寫在新結構。
- **第 3 項完成（刪死碼，共 32 行）**：`services/fb_monitor.py` 的 `start_fb_monitoring`、`services/it_article_monitor.py` 的 `start_monitoring`（FB／IT 從此只靠 scraper 推送，使用者核可不留輪詢備援）、`commands/article_commands.py` 兩個沒人讀的 task 屬性、`commands/forum_monitor.py` 沒用到的 `UserCommands` import。`asyncio`、`List` 在兩檔仍有其他用處，import 保留；`notify_server` 以字串呼叫的 `check_and_send_fb_posts`、`check_and_send_new`、`ensure_seeded` 都還在。
- **第 1 項完成（只加測試）**：新增 `src/test/test_data_file_paths.py`，釘住 6 個依程式檔位置算出的資料檔路徑（`sent_articles.db`、`article_runtime.json`、`rollcall_runtime.json`、`scraper/articles.db`、`logging.json`、`music/cache`）；只比對位置、不要求檔案存在。突變驗證：改 `state_db` 或 `music/ytdl` 的路徑 → 對應測試變紅。bot 端（不含 scraper、telegram_scraper、手動 scripts）用這種寫法的就是這 6 處，已 grep 確認。
- 正式測試 **643 項全過**。這些改動下次重啟才生效，不需要立刻重啟（刪的是沒人呼叫的程式）。
- **L4 使用者重新提出**：「搜尋應該獨立一個資料夾？搜尋像是一種 service，不只給 LLM；MCP 的殼才放 `llm/`。」分析：同意。搜尋的使用者有三種——MCP（給 LLM）、之後 /askai 的工具呼叫（給 LLM）、給人看的搜尋指令（R2-Q2 的 B，不經 LLM）——所以搜尋本身不是 LLM 技術；MCP 是給 LLM 客戶端用的協定，屬於「橋接 LLM」，照使用者對 `llm/` 的定義放 `llm/`。給模型看的工具說明（名稱、描述、參數格式）也屬於 LLM 這一側，之後 /askai 的工具呼叫可以共用。
  - 實測：`import llm` 在容器內約 1.5 秒、載入 1,747 個模組（`llm/__init__.py` 會預先載入 llama_index 等）；對照 `import services.base_monitor` 0.39 秒。MCP 殼放 `llm/` 會多這 1.5 秒啟動時間，每個 Claude Code session 只啟動一次，可以接受；太慢再把 `llm/__init__.py` 改成用到才載入。

**待決問題（第 7 輪，L4 重新討論；每題附建議）**
- **L4a 搜尋放哪**：A `services/search/`（搜尋是一種服務；符合子資料夾判準：有封裝邊界、會長大）／B 頂層 `src/search/`（像 `music/` 自成一包）。建議 A：它是給指令、/askai、MCP 共用的服務，不是一個自帶指令的完整功能。撈本地資料庫的程式放在裡面（使用者先前說的 `localdata`，檔案怎麼切等 R2-Q2 定）。
- **L4b MCP 殼放哪**：`llm/mcp_server.py`（單一檔案，變大再改成資料夾；用 `python -m llm.mcp_server` 啟動）。建議叫 `mcp_server` 而不是 `llm/mcp/`：雖然放在 `llm/` 底下不會蓋掉安裝的 `mcp` 套件，但 `from llm.mcp import …` 跟 `from mcp import …` 讀起來容易混淆。
- 順帶：網頁搜尋（`llm/retrievers/web/`）**建議留在原處**。它除了呼叫 SearXNG，還有「/askai 要不要查」的判斷和「整理成 prompt 區塊」的格式化，這兩部分是 LLM 專用的；等之後真的有非 LLM 的地方要用網頁搜尋，再把純搜尋那段抽到 `services/search/`。

**使用者回覆（2026-09-29，第 8 輪）**：L4a、L4b 都照建議——**搜尋放 `services/search/`、MCP 殼放 `llm/mcp_server.py`、網頁搜尋留在 `llm/retrievers/web/`**。MCP 區塊的 R2-Q5 同步定案。

**完整驗證（2026-09-29 第 9 輪，使用者要求「完整測試各套件之間的相依與關連性」）**
- 做法：多 agent 流程從六個角度獨立檢查，每個發現再派懷疑者重現或推翻。流程在 16:11 左右因 Claude Code session 重啟中斷；「分層檢查」「循環比對」兩個 agent 寫分析腳本時被權限擋下，「舊引用」沒跑完。這三項由主 agent 改用不落檔的方式直接補做。
- **測試與實際運行**：完整測試 643 項全過；15:28 重啟的啟動 gate 637 項通過（差的 6 項是 15:36 才加的 `test_data_file_paths.py`）；15:26 之後 `discord_bot.log` 612 行沒有任何 ERROR／Traceback／import 錯誤；指令模組 **11 個**（清單本來就是 11 個，先前回報的 12 是筆誤）、21 個斜線指令同步；raw flush、chat flush、插話（經新的 `build_prompt_bundle`）、反應事件、notify 轉發都已用新模組跑過。
- **實際執行所有 import**：97 個模組各自在全新行程 import 全成功；138 個 bot 端檔案共 394 條專案 import（含 162 條寫在函式、類別、try、if、with 裡）逐條實際執行全成功；`COMMAND_MODULES` 11 個、`_RELAY_SOURCES` 3 組（module、cls、method、seed）、9 個 `mock.patch` 字串全部解析得到。
- **相依圖比對**：依對照表換名後，搬家前 327 條、搬家後 335 條邊，差異只有預期的 2 條移除與 10 條新增（新測試、`llm_service` → `prompt_builder`、`prompt_builder` 的 TYPE_CHECKING 邊）。**循環相依前後完全相同**（原本就有的兩組：`music` 套件內部、`llm/__init__` 預先載入形成的一組），沒有新增。
- **分層檢查**：違反定義的只有 `services.rollcall_service` → `commands.rollcall_commands`（延遲 import，搬家前就有）；`llm/client`、`llm/preprocess` 沒有依賴上層功能；跨模組私有名稱 import 全部是既有的，沒有新增。放置上只有 `reaction_classifier` 可討論（`storage` 與 `persona` 都用它，也可以算資料整理），不算錯誤。
- **程式以外的引用**：`AGENTS.md` 共用元件表 8 個名稱全部解析得到；`test_shared_conventions` 的例外路徑全部存在；`logging.json` 只有類別與第三方 logger；舊路徑命中都屬歷史紀錄、刻意保留或刻意延後。本檔有 22 個 `src/` 路徑不存在，都與這次搬家無關（規劃中還沒寫的檔案，或本來就過時的 `intro_rag_port.py`、`ollama_runtime_config.json`）；**規劃中的新檔之後要照新結構放**（例：`reply_gate.py` 應放 `llm/ambient/`）。
- **git 狀態**：31 組搬移的內容相似度都在 0.947 以上；只用暫存區版本檢查 import 也是 0 個問題。**要處理**：① 使用者 15:39 整批 stage 時，把**無關的 `src/test/integration/it_comfyui_image.py` 也 stage 了**，commit 前要移出；② 本檔最新的修改還沒 stage。
- 其他：`src/llm/__pycache__` 還有舊檔名的 `.pyc`，Python 在沒有原始碼時不會載入它們，無害。

**使用者回覆（2026-09-29，第 10 輪）**：`it_comfyui_image.py` 移出暫存區（已執行 `git restore --staged`，檔案本身未動，回到未追蹤狀態）；本檔最新修改 commit 時一起加入；要求說明點名那條分層違規的細節（見下）。

**點名：服務層反過來依賴指令層（搬家前就有，未改）**
- 位置：`services/rollcall_service.py` 的 `_send_rollcall_message`（約 327～351 行）發點名訊息時要附「✋ 我是活人」按鈕；按鈕類別 `RollCallResponseView` 定義在 `commands/rollcall_commands.py`（約 29 行），所以服務層在函式裡 `from commands.rollcall_commands import RollCallResponseView`（約 344 行）。同一段的註解寫「View 由 Cog 層提供」，實作卻是服務層自己去指令層拿。
- 反方向：`commands/rollcall_commands.py` 頂層 import 服務層的 `RollCallService`、`RESPONSE_DEADLINE_DAYS`、`IMMUNITY_DAYS`、`_now_utc8`；「預覽範圍」按鈕還呼叫服務層的私有方法 `_get_target_role_ids`、`_get_exclude_role_ids`、`_collect_candidates_from_list`（同一功能內，不在跨功能的 7 處名單）。
- 為什麼現在能跑：兩檔互相依賴，只能把服務層那一邊寫成函式內延遲 import；有人把第 344 行移到檔案頂端，就會因循環 import 而啟動失敗（`RollCallService` 還沒定義就被指令層要求）。
- 影響：服務層知道 Discord 按鈕長什麼樣、放在哪個檔案，違反「services 做事、commands 管 Discord 介面」的分法；點名沒有單元測試，單測服務層會連帶載入指令層。目前功能正常，不急。
- **已定案：A**（使用者 2026-09-29 第 11 輪；實作見下方第 11 輪紀錄）。當時的選項：A 由指令層把「建立按鈕」的函式交給服務層（建立 `RollCallService` 時傳入），服務層只呼叫它、不 import 指令層；改 3 處（服務層建構子、發訊息處、指令層建立服務處），行為不變，順便消除延遲 import／B 把按鈕類別搬到服務層（違反 commands 管 Discord 介面的定義，不建議）／C 先不改，等下次改點名功能時再做。建議 C＋A：點名沒有測試，要改就先補一個「發點名訊息會附按鈕、按下會呼叫服務層」的測試，再用 A；目前沒有其他理由去動它。

**使用者回覆與實作（2026-09-29，第 11 輪）**
- 使用者：這次整理先 commit，點名照 A 改，**分兩次 commit**。
- **第一個 commit 已完成**：`97d7595 refactor(llm): group llm modules into role subpackages`（77 個檔案；搬家、prompt 組裝搬移、刪死碼、三個守衛測試、文件路徑）。無關的 `it_comfyui_image.py` 沒有包含在內，維持未追蹤。
- **點名改用 A（已實作，等第二個 commit）**：`RollCallService` 建構子多一個必填參數 `response_view_factory`；`_send_rollcall_message` 改呼叫它產生按鈕，拿掉對 `commands.rollcall_commands` 的延遲 import；`RollCallCommands` 建立服務時傳入 `RollCallResponseView`（它的參數正好是服務與被點名者 id）。服務層從此不 import 指令層，循環消失。
- **先補測試再改**：新增 `src/test/test_rollcall_service.py`（點名訊息 @ 本人並附上建立函式產生的按鈕、服務層不 import 指令層、Cog 有把按鈕類別交進去；執行期狀態檔以假物件取代）。改之前三項都紅；三種突變（服務層又 import 指令層、不用交進來的按鈕、Cog 沒交按鈕）都會紅。
- **順便修了守衛的一個誤判**：新測試讀 `rollcall_service.__file__`，守衛把 `__file__` 這類模組天生就有的屬性當成不存在而報錯——若沒被完整測試抓到，下次重啟時啟動 gate 會擋住 bot。改為接受 `__file__`、`__name__`、`__spec__` 等模組內建屬性，並加自測；拿掉這條件自測就會紅。
- 完整測試 **646 項全過**。這次改動下次重啟才生效（沒有搬檔，重啟前沒有風險）。
- **commit 前的獨立複查**（三個角度，每個發現再由另一個 agent 重現）：執行期行為與 `97d7595` 完全相同（新舊兩版在容器裡用同一支程式跑，點名訊息、按鈕、按下後三條路徑的輸出逐字相同）。確認並已修正的：
  - 守衛的內建屬性豁免沒套用到沒有 `__init__.py` 的資料夾（`commands.__path__` 會被誤判）→ 豁免移到資料夾判斷之前。
  - （改動前就有）頂層 `type X = ...`、`match` 分支、`:=` 綁定的名稱被當成不存在 → 補上。
  - 守衛自測沒鎖住豁免範圍、新加的 `mod.__name__` 其實沒被檢查到 → 另立正反例（清單外的 `__version__`、`__nope__` 仍要報錯）。
  - 點名兩層從沒接起來測過（按鈕建構子簽名改掉、按下不呼叫服務，測試照樣綠）→ 新增端到端測試：真的 Cog＋真的按鈕，本人按下交給服務層、別人按只收到提示。
  - 交接文件狀態行過時 → 已更新。
  - 突變驗證 9 種（點名 4、守衛 5）全部變紅；完整測試 **648 項全過**。
  - 已知但不處理（改動前就有、目前沒有這種寫法）：頂層出現 `alias.attr = …` 時，該別名後面的讀取不再檢查（刻意保守，避免誤判）；用 importlib 動態 import 或間接 import 指令層，AST 分層測試抓不到。

**還沒定案（下一輪）**：P3 暫停（使用者說先別動）；N3 延後。本主題其餘都已定案。

**`services/` 要不要也分類（2026-09-30 第 12 輪，使用者提出；grill 中）**
- 背景：ComfyUI 區塊的舊決定是「`llm/`、`services/` 都不做資料夾重組」，`llm/` 部分已推翻，`services/` 還維持原決定；這輪等於重新檢討。
- 盤點（19 檔、約 1 萬行，依「這個服務在做什麼」自然分成四群）：
  - 轉發（8 檔、約 5,100 行）：`article_monitor`、`fb_monitor`、`ptt_monitor`、`bahamut_monitor`、`it_article_monitor`、`telegram_relay_service`、`base_monitor`（轉發共用，被 7 檔引用）、`notify_server`（接 scraper 通知的 HTTP 入口，用字串指定 3 個轉發模組）。
  - 遊戲時程（3 檔、約 1,500 行）：`event_scheduler`、`event_time_parser`（被 9 檔引用）、`periodic_reminder`。
  - 社群管理（5 檔、約 1,500 行）：`rollcall_service`、`community_lookup_service`、`member_welcome`、`intro_profile_service`、`impression_moderation_service`。
  - 共用（3 檔、約 1,700 行）：`llm_service`（被 13 檔引用）、`memory_service`、`state_db`（被 5 檔引用）。
- 搬檔會碰到的地方：
  - **用程式檔位置找資料的 4 個**：`state_db`（`sent_articles.db` 就放在 `services/` 裡）、`base_monitor`（`settings/article_runtime.json`）、`event_scheduler`（`scraper/articles.db`）、`rollcall_service`（`settings/rollcall_runtime.json`）。搬到子資料夾後「上一層」會變，路徑那一行要跟著改；`test_data_file_paths.py` 會確認改完的實際位置跟現在完全一樣。
  - 字串路徑：`notify_server` 的 3 個轉發模組、`test_event_upgrade` 的 1 個 `mock.patch`；`AGENTS.md` 共用元件表 2 列（`event_time_parser.SERVER_TZ`、`event_scheduler.VersionDateResolver`）；`test_shared_conventions` 的例外路徑 2 個。import 守衛會擋下漏改的。
  - bot 即時掛載 `./src`：跟 `llm/` 一樣要在工作副本改好、驗證完，套用和重啟一起做。
- 待決問題（每題附建議）：
  - **S5-1 分到什麼程度**：A 依四群全分——`relay/`、`events/`、`community/`，共用的留在 `services/` 頂層／B 只收最明顯的轉發 `relay/`，其他平放／C 維持平放。建議 A：三群都有清楚的邊界（符合既有子資料夾判準），分完 `services/` 頂層只剩共用的東西與之後的 `search/`，要改哪一塊就只看那個資料夾；轉發那群之後還會長（Telegram 過濾、跨來源整合都在這裡）。
  - **S5-2 `notify_server` 放哪**：A 放 `relay/`（它目前只轉發通知）／B 留頂層。建議 B：它是 bot 對外的 HTTP 入口，「管理入口 TODO」規劃的網頁 dashboard 也要掛在它上面，不只給轉發用。
  - **S5-3 `state_db` 放哪**：建議留頂層、不搬：它被轉發、活動、社群 ID 查詢、週期提醒共用，而且 `sent_articles.db` 就在它旁邊，不搬就不必動資料路徑。**資料檔一律不搬。**
  - **S5-4 時機**：A 現在做（MCP 之前）／B MCP 之後。建議 A，並把「套用搬家」和 MCP 需要的「重建 image（加 `mcp` 套件）」排在同一次重啟，只重啟一次；搜尋服務 `services/search/` 也直接寫進整理好的結構。
- 不另外問、照慣例的預設：檔名不改（照 N1，`*_monitor` 不算誤導）；子資料夾名稱 `relay`、`events`、`community` 可以再換；做法同 `llm/`（工作副本、守衛、一次搬完、逐檔比對、獨立複查）。

**`services/` 分類：使用者核可與實作（2026-09-30 第 13 輪）**
- 使用者：S5-1～S5-4 都照建議（分 `relay/`、`events/`、`community/`；`notify_server`、`state_db` 留頂層；現在做、跟 MCP 重建 image 排同一次重啟）。
- **已在工作副本完成**（scratchpad `wt2`，patch `services_reorg.patch`，41 個檔案：搬移 15、新增 3 個 `__init__`、修改 23）：
  - `relay/`：`article_monitor`、`fb_monitor`、`ptt_monitor`、`bahamut_monitor`、`it_article_monitor`、`telegram_relay_service`、`base_monitor`
  - `events/`：`event_scheduler`、`event_time_parser`、`periodic_reminder`
  - `community/`：`rollcall_service`、`community_lookup_service`、`member_welcome`、`intro_profile_service`、`impression_moderation_service`
  - 頂層不動：`llm_service`、`memory_service`、`state_db`（`sent_articles.db` 在它旁邊）、`notify_server`
  - 改寫 62 處引用（含 `notify_server` 的模組字串、測試的 `mock.patch` 字串、`AGENTS.md` 表格 2 列、`test_shared_conventions` 例外路徑）；3 個資料路徑改成 `parents[2]`（搬進子資料夾多一層）。`src/scraper/` 自己的 `services` 套件沒動。
- 驗證（容器 `/tmp` 副本）：完整測試 648 項全過；import 守衛與資料檔位置測試通過（3 個路徑算出的實際位置與搬家前相同）；98 個模組各自單獨 import 全成功；依對照表換名後相依圖前後都是 336 條、完全相同，沒有循環。
- **獨立複查完成（兩個角度，發現都由另一個 agent 重現）**：patch 本身沒有問題——bot 端 141 檔共 396 條專案 import（函式內 160 條）逐條實際執行全成功，15 個舊名稱都已 import 不到；`notify_server` 三組轉發來源（模組、類別、方法、seed）動態解析正確；9 個 `mock.patch` 目標都解析得到；3 個資料路徑與 HEAD 相對位置完全相同（改成 `parents[1]` 則測試變紅）；15 個搬移檔除了 import 路徑與那 3 行外內容相同；`services/` 維持命名空間套件、子資料夾是一般套件，import 正常；scraper 與 telegram_scraper 沒被動到；4 種故意改壞都會被啟動 gate 擋下。確認的兩點：
  - **套用到重啟之間的空窗**：執行中的 bot 還沒載入 `services.member_welcome`（有人加入才載），套用後、重啟前若有新成員加入，歡迎訊息會 ImportError 而且不補發。→ 套用與重啟要接著做；**image 不含程式碼（`./src` 是掛載的），所以先重建 image（bot 照常運作），重建完再「套用 patch → 立刻重新建立容器」**，空窗縮到幾秒。
  - **交接文件與記憶裡仍在指引後續工作的舊路徑**（例：拆 log 分類的範例 `services.telegram_relay_service`，照做會被 log 設定測試擋在啟動 gate）→ 已備好套用時執行的 `apply_doc_paths_services.py`（試跑：交接文件 16 處、記憶 `project_telegram_relay.md` 1 處；開頭盤點紀錄與「程式結構整理」區塊不動）。
- **分群後浮現的放錯位置**：`get_shared_state_db`（取得全域共用 StateDB 連線）寫在轉發的 `relay/base_monitor.py`，但 `events/event_scheduler`、`commands/community_lookup_commands`、`commands/periodic_reminder_commands`、`discord_bot.py` 都用它 → 分群後這些都要去依賴 `relay/`。沒有動，待決。
- **重建 image 的版本風險（查證）**：`requirements.txt` 除 pydantic 等少數外都沒鎖版本，dockerfile 是 `pip install -r requirements.txt`，重建會把 discord.py、llama-index、yt-dlp 等全部升到最新。容器內模擬：把目前 84 個套件鎖在現有版本再加 `mcp==2.2.0`，可以解析，不動任何既有套件，只新增 MCP 自己的依賴（starlette、uvicorn、jsonschema 等）。
- **待決問題（第 13 輪，每題附建議）**：
  - **S6-1 `get_shared_state_db` 搬到 `state_db.py`**：A 搬（它和它的全域變數、鎖一起搬；4 個呼叫端＋1 個 `mock.patch` 改成 `services.state_db`；`base_monitor` 自己也改從那裡拿）／B 不搬。建議 A：它是共用基礎，搬完 `events/`、`commands` 就不必為了拿資料庫去依賴轉發。
  - **S6-2 重建時的套件版本**：A 新增 `docker/discord_bot/constraints.txt`（容器內目前版本的完整清單），dockerfile 改成 `pip install -c constraints.txt -r requirements.txt`，`requirements.txt` 加 `mcp==2.2.0`（順便更新那兩行舊路徑註解）／B 直接在 `requirements.txt` 逐一釘版本／C 接受全部升到最新。建議 A：重建結果跟現在一模一樣、只多 MCP；以後要升級某個套件，改 constraints 那一行就好。
  - **使用者追問 S6-2（2026-09-30）**：通常認為升到最新版 OK，要先清查「目前版本 vs 最新版本、有沒有 breaking changes、哪些行為會變」。
    - 清查（容器內模擬從零重建的實際解析結果，不是各套件各自的最新版）：重建後安裝 102 個；**版本改變 52 個**（主版號 3、次版號 37、修補 12）、新增 18 個（MCP 與其依賴）、移除 0 個。`discord.py` 2.7.1 已是最新、不會變。
    - 主版號：`deprecated` 1.3.1→3.0.0、`setuptools` 82.0.1→84.0.0、`websockets` 16.0→17.1。
    - 次版號中較需注意：`llama-index-vector-stores-postgres` 0.8.1→0.9.0（碰 pgvector 資料表）、`pgvector` 0.4.2→0.5.0、`numpy` 2.4.6→2.5.3、`pydantic-settings` 2.14.1→2.15.0、`pillow` 12.2.0→12.3.0、`yt-dlp` 2026.6.9→2026.8.19、`llama-index-workflows`、`llama-index-instrumentation`、`tiktoken`、`nltk`、`anyio`、`urllib3`、`multidict`（解析結果是 6.9.1，不是 7.0）。
    - 各套件自己的最新版與實際解析結果不同的例子：`marshmallow` 最新 4.x 但被上游限制在 3.x、`SQLAlchemy` 最新 2.1 但解析為 2.0.54、`PyNaCl` 維持 1.5.0。
    - 研究進行中：四組 agent 讀官方更新紀錄並對照我們的程式用法，一個 agent 在容器 `/tmp` 的獨立 venv 裝最新版、跑完整測試與逐模組 import；標為「會影響我們」的再由另一個 agent 複查。
  - **升級影響研究完成（2026-09-30，四組 agent 讀官方更新紀錄並對照程式，外加隔離 venv 實測；標「會影響」的再複查）**：**52 個升級都不會弄壞我們，也不需要改程式。**
    - 實測：容器 `/tmp` 的獨立 venv 從零安裝（requirements＋`mcp==2.2.0`），`pip check` 無衝突、版本與清查表逐一相符；完整測試 648 項全過（與現行環境跑的結果去掉時間後完全相同，沒有新警告）；95 個模組各自 import 成功；額外煙霧測試：`PGVectorStore` 以我們的參數建構成功、建表與查詢的 SQL 逐字相同；語音（opus、PyNaCl、davey）正常；yt-dlp 用我們 4 組選項建立成功；Pillow 動圖拆幀與 JPEG 壓縮的輸出像素雜湊相同；`deprecated` 3.0 行為正常；`setuptools` 84 對我們沒差（`pkg_resources` 在舊版就已經沒有）。
    - 有行為改變、但碰不到我們的：
      - `pgvector` 0.5：SQLAlchemy 讀回的向量從 numpy 陣列改成 list、維度檢查改由資料庫做（錯誤類型會變）；我們沒從 SQLAlchemy 讀向量、沒用 MMR，自己的 SQL 用 `%s::vector` 字串。
      - `llama-index-core` 0.14.25：instrumentation 事件內容變少（我們沒掛）；切段器極端情況的例外類型改變（碰不到）。`llama-index-vector-stores-postgres` 0.9.0 程式碼與 0.8.1 逐位元組相同。
      - `nltk` 3.10：超過 1024 token 的新訊息，若英文句號後緊接彎引號或 « »，切段邊界會和舊版略有不同；舊資料不受影響。它新增必要相依 `defusedxml`（`cloudpickle` 則是 `joblib` 1.6 要的，兩者都不是 mcp 帶的）。
      - `pydantic-settings` 2.15：用關鍵字參數建構設定時欄位名改成不分大小寫；我們正式程式建構時不帶參數。
      - `yt-dlp`：預設 YouTube client 改了；我們在 `music/ytdl.py` 明確指定 `android`、`web`，新版仍有。
      - `websockets` 17.1：只有 yt-dlp 在 ws:// 網址才用；新增一條 DeprecationWarning，代表 18 版可能不相容（將來的風險）。
      - `davey` 0.1.6：語音加密（DAVE）的修正，API 不變；建議重建後點一首歌確認能出聲、log 沒有 4017 或 encryption failed。
    - **給之後寫 MCP 的提醒**：`mcp` 2.x 把 `FastMCP` 改名為 `MCPServer`（`from mcp.server.mcpserver import MCPServer`）；它帶進來的 `httpx2` 不會蓋掉我們用的 `httpx` 0.28.1。
    - **S6-2 建議改成「升到最新＋鎖住測過的版本」**：這次直接升到最新（上面已實測）；同時把這次解析出來、測過的 102 個版本寫進 `docker/discord_bot/constraints.txt`，dockerfile 改成 `-c constraints.txt`，以後重建結果跟這次完全相同，想升級時再刻意更新 constraints 並重跑這套檢查。比「鎖在舊版」好，因為 yt-dlp 這類套件本來就要跟著更新；比「每次重建都升到最新」穩，因為每次重建都可能拿到沒測過的新版。
  - **S6-2 已準備（2026-09-30，使用者要重建指令，照建議 A「升到最新＋鎖住測過的版本」）**：新增 `docker/discord_bot/constraints.txt`（102 個版本，就是隔離環境實測過的那一組）；`requirements.txt` 加 `mcp>=2.2,<3`，兩行舊路徑註解改成 `src/llm/client/…`；dockerfile 改為一起複製 constraints 並用 `pip install -c constraints.txt -r requirements.txt`。容器內用新設定模擬從零安裝：pip 結束碼 0，裝出的 102 個與鎖定檔逐一相同，沒有漏鎖。重建只產生新 image，不影響執行中的 bot；不要加 `--no-cache`／`--pull`，作業系統那幾層（apt、ffmpeg）才會沿用快取、維持不變。
  - **S6-3 套用時機**：07:30 維護結束之後、你方便時（9/30 05:03 查：③ 人格萃取在新路徑下 37/37 完成，④ persona agent 進行中 14/26，04:00 起沒有任何錯誤）。流程：我套用 patch（搬家＋S6-1＋S6-2）→ 跑正式測試 → 你執行 `docker compose build discord-bot && docker compose up -d discord-bot`（重建 image 並重新建立容器）→ 我看啟動 gate 與 log → 跑文件路徑更新腳本 → 第三個 commit。

**`services/` 分類：套用與上線（2026-09-30 第 14 輪）**
- 實際順序：使用者先用新 image 重建容器（13:09，程式仍是 `9b0b916`）→ S6-1 使用者核可、併進 patch → 重複活動雜訊修正（A，見[活動自動發布修正區塊](#活動自動發布連結指向錯誤--重複建活動2026-09-22-已實作待部署驗證)）也併進 patch → 使用者要我代為套用，避免手動失誤。
- **S6-1 已做**：`get_shared_state_db`（連同全域變數與鎖）從 `relay/base_monitor.py` 搬到 `services/state_db.py` 檔尾；4 個呼叫端（`discord_bot.py`、`events/event_scheduler.py`、`commands/community_lookup_commands.py`、`commands/periodic_reminder_commands.py`）與 1 個 `mock.patch` 字串改成 `services.state_db`；`base_monitor` 自己也改從那裡拿。新增 `test_shared_state_db.py`：同時呼叫 5 次拿到同一個實例、只連線一次；這個函式只定義在 `services/state_db.py`（在別處另寫一份就會變成兩個連線）。兩種故意改壞都會紅。
- **套用**：16:17:41 套用 `services_reorg_v2.patch`（43 檔＝原本 41 檔＋`state_db.py`＋`test_shared_state_db.py`），套用後與工作副本逐位元組相同；套用前在新 image 容器 `/tmp` 副本跑過：652 項全過、98 個模組各自 import 成功。
- **上線驗證（使用者 16:38 重啟）**：啟動 gate 652 項全過；11 個指令模組、21 個斜線指令、人格萃取與日記排程、官網與 PTT 轉發、Telegram relay worker、Notify Server 全部從新路徑啟動（log 的模組名稱已是 `services.relay.*`、`services.community.*`）；重啟後沒有任何 ERROR；16:17～16:38 空窗期也沒有 ERROR，沒有新成員加入造成歡迎訊息失敗。
- **S6-2 改定案（使用者 2026-09-30）**：使用者認為 dockerfile 改成鎖版本沒必要（通常升到最新就好）→ **dockerfile 還原成原版**（只 `pip install -r requirements.txt`，每次重建都拿當下最新版）；**`constraints.txt` 留作紀錄**：內容與容器內 `pip freeze` 102 項逐一相同，檔頭改成「建置不讀這個檔」，用途是之後重建出問題時對照哪個套件變了，必要時用 `pip install --user -c constraints.txt -r requirements.txt` 暫時裝回；映像重建後就不代表現況，要更新請重新 `pip freeze`。`requirements.txt` 保留 `mcp>=2.2,<3` 與兩行註解路徑更新。接受的取捨：下次重建會拿到沒測過的新版，第一道防線是啟動 gate（測試不過 bot 起不來、舊容器照跑）。
- **文件路徑已更新**：`apply_doc_paths_services.py` 已執行，交接文件 16 處（明確替換 2 處＋通用規則 14 處）、記憶 `project_telegram_relay.md` 1 處；剩下的舊路徑都在本區塊的新舊對照裡（刻意保留）。
- **S7-1 commit 怎麼拆（已定案：A）**（`it_comfyui_image.py` 一律不進）：
  - 結果：`5e10611` `refactor(services)`（v1 patch 41 檔，容器 `/tmp` 648 項全過）→ `2b31828` `refactor(state-db)`（8 檔；`event_scheduler` 與 `test_event_upgrade` 只放 S6-1 那一行，650 項全過）→ `f7d4a14` `fix(events)`（2 檔，commit 後 `src/` 與上線程式相同，啟動 gate 652 項）→ `f6e4830` `build(discord-bot)`（`requirements.txt`＋`constraints.txt`）→ 交接文件 `docs` commit。
  - 當時的選項：
    - A 拆五個：① `refactor(services)` 分成 relay／events／community（就是 v1 patch 那 41 檔＋`AGENTS.md` 兩列路徑，已測過 648 項）② `refactor(state-db)` S6-1 ③ `fix(events)` 已處理過的重複活動只報一次 ④ `build(discord-bot)` 加 mcp、留版本紀錄 ⑤ `docs` 交接文件。
    - B 拆三個：搬家含 S6-1／A 修正／套件＋交接文件。
    - C 一個 commit。
    - 建議 A：v1 與 v2 的差別剛好只在 S6-1 與 A 牽動的 8 個檔，可以乾淨切開；每個 commit 只做一件事，之後要退回某一項（例如 A）不會連帶退掉搬家。中間兩個狀態（只有搬家、搬家＋S6-1）我會先在容器 `/tmp` 各跑一次完整測試再 commit。
- 收尾：scratchpad 的 worktree `wt2` 在 commit 後移除（`git worktree remove --force`＋`git worktree prune`）。

**重啟驗證（2026-09-30 02:10 使用者重啟）**：啟動 gate 648 項全過；11 個指令模組載入、21 個斜線指令同步、各排程啟動；點名服務用新程式啟動（下次檢查 09-30 14:00）。**00:00 日記第一次在新路徑（`llm.ambient.ambient_diary`）執行，成功發布**（446 字、來源 173 則）。9/29 15:28～9/30 02:10 舊行程期間唯一的 ERROR 是 00:21 插話呼叫模型逾時（隨後 embedding 回 HTTP 500、改逐筆重試成功）；這類逾時 9/16 起約每天一次，與搬家無關。其餘是 Discord 429 限流、PTT 附件分批、Telegram 大檔壓縮等既有訊息。

**狀態**：`llm/` 重組（`97d7595`）與點名去除反向依賴（`9b0b916`）**都已 commit 並上線**；9/30 04:00 維護在新路徑下完整跑完。**`services/` 分群（`5e10611`）＋S6-1（`2b31828`）已 commit、9/30 16:38 重啟上線**。P2 未決、P3 暫停、N3 延後。

---

## MCP／搜尋工具化（2026-09-29 構想，grill 中）

<!-- @meta
id: mcp-search-tools
type: TODO
status: draft
last_confirmed: 2026-09-29
affects: /askai、網頁查詢、官網公告、論壇（PTT／巴哈）
-->

**需求（使用者 2026-09-29 提出）**
- 想把現有服務改成 MCP server。例子：① 網頁查詢（現在要先過固定字詞過濾，才會在 /askai 底下查）；② 官方公告搜尋（現在沒有搜尋功能）；③ 論壇搜尋（現在是寫死日期區間給 Discord，希望機器人也能自己搜）。

**機制本質**：MCP 是把工具包成標準介面、讓任何 LLM 客戶端都能找到並呼叫的協定。三個例子的共同點是「讓 bot 的 LLM 自己決定要不要查、查什麼」，也就是 tool calling。MCP 值不值得做，要看 bot 以外有沒有第二個客戶端。

**查證事實（2026-09-29，唯讀調查）**
- **`/askai` 流程**：`commands/llm_commands.py` `askai_cmd`（約 291 行）→ 全域排隊、單一 worker → `_handle_askai_request` 組 prompt（固定兩則 message：system＋一則帶標籤區塊的 user，沒有多輪）→ `LLMService.generate_reply` → 自寫的 httpx 客戶端打 OpenAI 相容 API（`/v1/chat/completions`，不串流）。用主模型、開思考。每人冷卻 180 秒（管理員例外），排隊沒有上限。
- **網頁查詢**：自架 SearXNG（compose 的 `searxng`，bing＋duckduckgo），**只用搜尋結果摘要，不抓內文**。觸發是 `llm/retrievers/web/intent.py` `should_search()` 的純 regex：先排除（短句、招呼語），再看硬關鍵字（金融、天氣、版本／更新、公告、體育、今天／最新、幫我查…），最後看軟規則（「最近…發生／新／更」）。命中後依類別決定搜新聞或一般、時間範圍、語言；結果少於 3 筆就放寬再搜一次，最多 5 筆，塞進 `<web_context>`。只有 `/askai` 用，插話、日記、persona agent 都不用。
- **tool calling 已經有一份實作**：persona agent（04:00 維護步驟 ④）用 `LLMService.chat_with_tools` 跑自寫的多輪迴圈（最多 8 步、token 預算、工具錯誤轉成 `{"error":…}` 回給模型、最後一步用嚴格 `json_schema` 輸出）；4 個唯讀 SQL 工具（`llm/persona/agent/tools.py`）。在 Lemonade 11.5.0＋27B 實測過 tool call、`role:"tool"` 往返與 json_schema；**Lemonade 已升到 11.9.0，沒有重測**。persona agent 是關思考跑的，**開思考＋tool calling 沒驗證過**。`chat_with_tools` 不支援 `tool_choice`，也不回傳思考內容。
- **GPU 鎖只在單一行程內有效**（`lemonade_gate` 是 `asyncio.Lock`）。獨立的 MCP 行程如果要呼叫 LLM，就不受這把鎖管；純搜尋工具（SQL、SearXNG）不碰 GPU，不受影響。
- **吞吐量**：總共約 22～33 tok/s，並行時均分（1 個請求 33、2 個各約 11～12）。tool calling 每多一輪，就是多一次完整的 LLM 呼叫。
- **scraper 容器已經有唯讀 HTTP API**（FastAPI，內網 8000）：`/api/{articles,fb_posts,ptt_posts,bahamut,it_articles}/recent`、依 id 查詢；只能用 `days`、`limit` 篩選，**沒有關鍵字搜尋**。bot 也會直接唯讀開 `/app/scraper/articles.db`（`services/community/community_lookup_service.py`）。
- **bot 內已有 aiohttp 伺服器**（`services/notify_server.py`，內網 5000：`/health`、`/notify/{source}`）。
- **repo 裡沒有任何 MCP 相關程式或套件**；requirements 也沒有 openai SDK。
- **資料都已經在 `articles.db`，而且是全文、永久保留**（scraper 沒有任何清除程式；巴哈刪文是軟刪除、改文保留舊版）。都沒有做搜尋索引：
  - 官網公告：540 篇（公告 503、新聞 37，2024-01 起）；`article_details.article_content` 是**完整內文，但存的是 HTML**（平均約 4,160 字），要先轉純文字才能搜。沒有網址欄位，網址用 id 組（`services/relay/article_monitor.py` `OFFICIAL_ARTICLE_URL`）。
  - FB：847 篇，`fb_posts.text` 是純文字全文（2025-11 起）。
  - PTT：5,182 篇，**只有 C_Chat 板、用「鳴潮」搜到的文章**（2025-01 起），有全文和全部推文。
  - 巴哈：主文 15,989 篇（含回覆共 102,958 列）、留言 693,917 則，2022-06 起，有全文。
- **「寫死日期區間給 DC」指的是轉發**，不是 `/askai`：巴哈、PTT、公告的轉發都只看最近 3 天（FB 看 7 天），以 StateDB 去重。所以論壇搜尋是**另外新增的能力**，轉發本身不用改。
- **現有查詢只有**：scraper API 的「最近 N 天」、社群 ID 查詢面板的「依作者查」（`services/community/community_lookup_service.py`，已有 bot 直接唯讀查 `articles.db`、p95 < 30ms 的前例），以及 `VersionDateResolver` 寫死的 `LIKE`。**沒有任何關鍵字或主題搜尋**。
- **搜尋基礎設施現況**：SQLite 沒有 FTS 表；Postgres 只裝了 `vector`，沒有 pg_trgm 或中文斷詞；pgvector 只存 Discord 聊天（31 萬筆）和成員檔案，**公告、FB、論壇都沒有做 embedding**；embedding 欄位沒有向量索引（全表掃描）。可以沿用的：`llm/preprocess/tokenization.py` 自製的中文 BM25 斷詞（CJK 2-gram／3-gram）。
- **舊規劃**：`TODO-completed.md`「Bahamut 專區」第三階段規劃過巴哈 RAG（分段、metadata、混合搜尋），沒做；`askai-vague-news-query` 決定過「新聞搜不到就放寬」，「用 LLM 依聊天紀錄改寫查詢」留作之後的升級。
- **順便發現**：① `/askai` 回覆沒有處理 Discord 2000 字上限（沒切段，長回答可能送出失敗，未實測）；② 引用網址上限不一致：`askai_system_prompt.txt` 寫最多 3 個，`<web_context_directive>` 寫 5 個。

- **效能實測（2026-09-29，唯讀查 Lemonade `/api/v1/stats`）**：最近一次請求讀入 3,924 tokens、沒命中 prompt cache，第一個字出來前等了 11.7 秒（讀 prompt 約 335 tok/s）；產生速度 33 tok/s。累計 prompt cache 命中約 55%。
- **容器環境**：discord-bot 的 SQLite 是 3.46.1，支援 FTS5 trigram 全文索引；沒有安裝 `mcp` 套件。

**已定案（2026-09-29）**
- **社群稽查（依巴哈／PTT ID 查人）不納入工具**（使用者：「其實也能不要，主要希望查情報用」）。理由：技術上很容易包（`community_lookup_service.py` 本來就是乾淨的查詢函式），但工具一旦交給 LLM，任何成員都能在 `/askai` 叫它查某個人的發言紀錄；用途是管理稽查，繼續留在管理面板。
- **用途＝查情報；Telegram 內鬼頻道排除**（使用者拍板）。來源：官方公告、論壇（PTT、巴哈）、網頁。每筆結果都標來源類型，回答時分開講「官方」與「玩家說法」。
- **改由 LLM 決定要不要查、查什麼**（Q3，使用者確認痛點是「該查沒查」＋「要記觸發字」，而且關鍵字沒辦法從語意上穩定判斷）。
- **先做 MCP server**（Q2，使用者選）。搜尋函式（工具本體）只寫一份；MCP server、bot 的 tool calling、斜線指令都是外面的殼，殊途同歸。先做 MCP 的好處：用外部的強模型當客戶端先驗證搜尋品質，不必重啟 discord-bot，也不碰 GPU。bot 之後直接 import 工具本體，不當 MCP 客戶端（同一份程式碼，多一層網路只是多一個會壞的地方）。
- **MCP 客戶端只有這台 Linux 上的 Claude Code，採放法 ②**（R2-Q1，使用者 2026-09-29：「不會有別的電腦連接」）：MCP server 是 discord-bot container 裡的另一個行程，走 stdio，由 Claude Code 用 `docker exec -i discord-bot python -m llm.mcp_server` 啟動；不開 port、不用 token。理由：放進 bot 行程要常重啟 bot、建索引會搶 bot 的 event loop；新 container 的好處（網路常駐連線）用不到。代價：`mcp` 套件寫進 requirements、重建 image，**discord-bot 要重啟一次**（避開 04:00～07:30）；之後改 MCP 程式都不用重啟 bot。

**bot 接工具的成本估算**（回答使用者 Q1「會不會拖效能」；等到 bot 階段再定案）
- 搜尋本身不是瓶頸：查 SQLite 是毫秒級，SearXNG 最多 4 秒。慢的是 LLM 多跑一輪：第 1 輪決定查什麼，第 2 輪看結果回答。
- 估算：第 1 輪如果**關掉思考**，只產生幾十個 token 的工具呼叫（約 1～2 秒）；第 2 輪前面的 prompt 命中 cache，只需多讀搜尋結果（約 1,500 tokens，約 5 秒）。每次搜尋大約多 5～10 秒。現在開思考的回答常常要 30～100 秒。
- 風險：第 1 輪如果開著思考，會多 10～45 秒；兩輪中間有別的請求插隊，cache 會被洗掉，要整份重讀（多 12～15 秒）。建議：決策輪關思考、最多 2 輪搜尋，只有最後回答那一輪開思考。「開思考＋tool calling」與 Lemonade 11.9.0 都還沒實測。

**待決問題（grill 第 2 輪，2026-09-29；每題附建議）**
- **R2-Q1 MCP 客戶端是誰、跑在哪**（已回答，見已定案）：A 只有這台 Linux 上的 Claude Code／B 再加上 Windows 那台（Lemonade 所在的 192.168.56.1）的 Claude Desktop／C 連 claude.ai 網頁、手機都要能用（得對外網公開 HTTPS）。建議 A＋B：新開一個 compose 服務，走 HTTP 傳輸、資料唯讀掛載，只綁本機與內部網段、加 token；不對外網公開；部署時不必重啟 discord-bot。
  - **使用者追問（2026-09-29）：一定要另開 container 嗎？** 關鍵是「跟 bot 同不同一個行程」，不是同不同一個 container。三種放法：
    - ① **塞進 bot 行程**（開 HTTP port）：不多一個服務、可直接用 bot 的設定與斷詞。缺點：MCP 程式每改一次就要重啟 bot；建索引（十幾萬篇 HTML 轉文字）的 CPU 工作會跟音樂、Discord 心跳搶同一個 event loop 與 GIL；對網路開 port 的行程握有 Discord token；MCP SDK 是 ASGI（uvicorn），bot 現有的是 aiohttp，要在 bot 裡再塞一套網頁框架。
    - ② **同一個 container、另一個行程**（stdio，由 Claude Code 用 `docker exec -i discord-bot python -m llm.mcp_server` 啟動）：不開 port、不用 token、不多服務；獨立行程，不搶 bot 的 event loop；改 MCP 程式不用重啟 bot。缺點：只有能跑 `docker exec` 的地方連得到（Windows 的 Claude Desktop 要透過 ssh 遠端執行同一行指令）；裝 `mcp` 套件要重建 image，**bot 至少要重啟一次**才會用到新 image；沒有常駐行程，索引同步要在每次啟動或每次搜尋時做增量。
    - ③ **新 container**（HTTP）：可沿用 discord-bot 的 image，只換啟動指令、唯讀掛載 `./src`，不用新寫 Dockerfile；完全不動 bot；常駐，可以定時同步索引；網路 port 開在沒有 Discord token 的 container 上。缺點：compose 多一個服務要維護；要處理 port 與 token。
    - 建議：①不採用。只有這台的 Claude Code 用（或 Windows 願意走 ssh）→ ②最省事；要讓其他機器透過網路常態連線 → ③。
- **R2-Q2 工具怎麼切、回傳什麼**：A 一個 `search` 工具，用參數選來源／B 依來源分：`search_official`（公告＋FB）、`search_forum`（PTT＋巴哈），再加一個 `read_document(id)` 讀全文。建議 B：工具範圍窄，本機模型比較選得準；搜尋只回標題、日期、來源類型、網址、約 200 字摘要，要全文再呼叫 `read_document`（分頁），讓 prompt 保持短（每多 1,000 tokens 約多 3 秒）。網頁搜尋不放進 MCP（Claude Code／Desktop 自己就會上網查），只做成 bot 用的工具（沿用 SearXNG）。
- **R2-Q3 搜尋方式**：A 關鍵字全文搜尋（SQLite FTS5 trigram，另開索引檔，從 `articles.db` 唯讀同步）／B 向量搜尋（算 embedding 存 pgvector）／C 兩者混合。建議第一版 A：角色名、活動名都是固定字串，查詢字交給 LLM 寫，搜不到它可以換詞再搜。坑：trigram 查不到少於 3 個字的詞（例如兩個字的角色名）→ 短詞改用 `LIKE`（巴哈 10 萬列要實測速度）。向量之後再加：十幾萬篇要先全部算一遍 embedding，會佔 GPU 好幾個小時。
- **R2-Q4 論壇要搜到哪一層**：巴哈有主文、回覆樓層（共 10 萬列）、留言（69 萬則）；PTT 有內文、推文。建議索引巴哈主文＋回覆樓層、PTT 內文；推文與巴哈留言第一版不索引（短、雜、量大），但 `read_document` 會一起顯示。

- **R2-Q5 程式放哪**（使用者 2026-09-29 提出：不想跟其他程式混在一起）：A 一個資料夾 `src/search_mcp/` 全放／B 分兩個：`src/search/`（搜尋本體：索引同步、各來源搜尋、讀全文；索引檔放 `src/search/data/`）＋ `src/mcp_server/`（只有 MCP 這層殼：登記工具、`python -m mcp_server` 啟動）。建議 B：之後 bot 要 import 的是搜尋本體，放在叫 mcp 的資料夾裡名稱會誤導；殼保持很薄，以後要開放別的工具也是往 `mcp_server/` 加。
  - **定案（2026-09-29 第 8 輪，取代上面 A／B 兩案）**：搜尋本體放 `services/search/`（搜尋是給指令、/askai、MCP 共用的服務，不只給 LLM；索引檔放 `services/search/data/`）；MCP 殼放 `llm/mcp_server.py`（給 LLM 客戶端的橋接，`python -m llm.mcp_server` 啟動；不取名 `llm/mcp/` 以免跟 `mcp` 套件混淆）；網頁搜尋留在 `llm/retrievers/web/`（含 /askai 專用的觸發判斷與 prompt 格式化）。討論經過見 [程式結構整理](#程式結構整理2026-09-29-構想grill-中) 的 L4a／L4b。
  - **使用者追問：MCP server 不就取代 search 了？** 不會。MCP server 只負責協定（告訴客戶端有哪些工具、把呼叫轉進來、把結果包回去），真正查 SQLite、同步索引、HTML 轉文字的程式一定要有；問題只是放在哪個資料夾。對照專案現有分工：`commands/`（斜線指令＝殼）呼叫 `services/`（做事）。分開的理由是 bot 之後直接 import 搜尋程式、不走 MCP；如果全放在 `mcp_server/`，功能一樣能用，只是名稱誤導，而且要注意搜尋程式不能 import `mcp` 套件（不然 bot 也被拖著載入）。A 的變體：`src/mcp_server/` 裡放一個不依賴 MCP 套件的 `search/` 子資料夾，也可接受。
  - **不能取名 `src/mcp/`**：容器工作目錄是 `/app`，會蓋掉安裝的 `mcp` 套件，`import mcp` 會載到自己的資料夾。
  - **照專案規則仍放在外面的**：測試放 `src/test/test_search_*.py`（啟動 gate 只掃 `test/`）；設定放 `sys_settings/search_settings.py`（AGENTS.md 規定）；`.mcp.json` 放 repo 根目錄（Claude Code 從那裡讀）。
  - **log 要分檔**：`settings/logging.json` 加 `llm.mcp_server`、`services.search` 前綴的 logger 寫自己的檔、不往 root 傳。原因：兩個行程寫同一個輪替 log 檔，輪替時會互相蓋掉；也符合「不混在一起」。已確認 console handler 預設輸出到 stderr，不會弄壞走 stdout 的 MCP 協定。

**使用者回覆（2026-09-29，第 3 輪）**
- **R2-Q3 定案：A 關鍵字全文搜尋**（SQLite FTS5 trigram，索引檔在 `services/search/data/`，從 `articles.db` 唯讀同步；少於 3 個字的詞改用 `LIKE`；向量之後再加）。
- **R2-Q4 定案：照建議**（索引巴哈主文＋回覆樓層、PTT 內文；PTT 推文與巴哈留言第一版不索引，讀全文時一起顯示）。
- **R2-Q2 使用者質疑**：「照來源命名，之後每加一個來源都要加一堆工具名稱？這樣可行、符合業界用法嗎？」→ 查證後**撤回原建議 B**：
  - Anthropic〈Writing effective tools for agents〉：工具要把相關操作合併成少數幾個（例：用 `schedule_event` 取代 `list_users`＋`list_events`＋`create_event`），減少模型選錯；依服務加前綴（`asana_search`、`jira_search`）是用在工具很多、且來自不同系統時。我們的來源查同一個索引、參數與回傳格式都一樣，應該合併。
  - OpenAI MCP 文件：`search`（一個查詢字串 → 帶 id、標題、網址的結果）＋`fetch`（id → 全文、網址、metadata）是標準的一組，ChatGPT 深度研究要求 MCP server 提供這兩個工具。
- **R2-Q2 定案（使用者 2026-09-29 第 10 輪確認「不是同意了嗎」）**：只開兩個工具——`search(query, sources=可選, since, until, limit)` 與 `fetch(id, page)`。`sources` 是可選的來源清單（官網公告、官方 FB、PTT、巴哈），不給就全部搜，每種來源各取前幾筆，避免論壇的量把官方公告淹掉；每筆結果標明來源。**來源清單由 `services/search/` 的登記表自動產生**：之後加來源＝寫一個來源模組並登記，工具名稱與介面都不變。在 Claude Code 裡工具會自動加上 server 名稱當前綴（例：`mcp__<server>__search`），不會跟內建的網頁工具撞名。之後 /askai 的工具呼叫也用同一組，工具少，本機模型也比較不會選錯。

**不反對就照做的預設**：MCP 設定放 repo 的 `.mcp.json`（在這個 repo 開的 Claude Code 都能用這些工具）；索引檔放 `services/search/data/` 並加進 `.gitignore`，**標明是可重建的衍生資料、不算使用者資料**；R2-Q3 若選 A，索引在 MCP 啟動時與每次搜尋前做增量同步（沒有常駐行程；之後 bot 搜尋也走同一個同步函式），兩個行程同時同步時用 SQLite 寫入鎖排隊；實作時在 `AGENTS.md`「Docker 只做唯讀查詢」加註這個例外（這個 MCP server 由 `docker exec` 啟動、只寫自己的索引檔）；官方 FB 粉專算「官方」來源；所有工具唯讀；結果預設依日期新到舊，可以篩日期範圍；公告 HTML 在建索引時轉純文字；索引檔由搜尋模組自己擁有，不改 `articles.db`。

**之後（bot 階段）再問**：`/askai` 決策輪要不要關思考、最多幾輪；舊的關鍵字觸發要不要留著當保底；插話能不能用搜尋；搜尋與 `/askai` 排隊、GPU 鎖怎麼配合；要不要抓網頁內文（現在只用摘要）。

**狀態**：設計已全部定案（R2-Q1～Q5），未動 code；下一步是實作（先加 `mcp` 套件 → 重建 image → 重啟一次 bot）。`llm/` 重組已上線，MCP 直接寫在新位置。

---

## Telegram 訊息 LLM 過濾 + 隔離區（2026-09-28 構想，討論中）

<!-- @meta
id: telegram-llm-filter-quarantine
type: TODO
status: draft
last_confirmed: 2026-09-28
depends_on: telegram-catchup-sweep
affects: Telegram relay、config.json
-->

**需求（使用者 2026-09-28 提出）**
- Telegram 訊息轉進 Discord 前先用 LLM 判斷是不是垃圾發言：灌水（「最近有什麼水啊」「又水一次」這類）、情緒性罵人。
- 垃圾發言不進主頻道，改發到**隔離區**：config 指定一個頻道（例如內鬼頻道），在裡面開一個 thread 專放垃圾發言。
- 隔離區裡被誤判的訊息，要能手動（按鈕或其他方式）**放回主頻道**。

**查證事實（2026-09-28，唯讀調查）**
- **來源是兩個 Telegram 廣播頻道**（`Seele_WW_leak` 8.4 萬訂閱、`Gamedataleak` 1.2 萬），沒有網友留言 → 「垃圾發言」是**頻道管理員自己發的**（Seele 管理員 09-09 起的「今日首水」習慣、跟人互嗆）。目的頻道只有 #🌘角色內鬼情報（`1276423699851116544`）；GD 沒有自己的路由，靠「查不到就用第一個來源的路由」送到同一處。
- **量**：近 14 天有文字的只有 120 則（約 8.6 則／天，尖峰 22 則／小時）；灌水約 5%、罵人約 3%，連同閒聊約一成。純媒體佔發送單位的一半。
- **關鍵字不可行**：含「水」的 85 則裡只有約 10 則是灌水（水匣、汽水、山水…）；≤5 字多是有情報的圖說（「亚服」「预下载已开启」「V2来了」）；emoji 可能是角色代號（13653「🦊😭🥛…」對照 13664 是在爆主線角色）。
- **插入點**：discord-bot 的 `services/relay/telegram_relay_service.py` `_process_one`，相簿合併（`_collect_media_group`）之後、`resolve_telegram_routes` 之前（約 1773~1775 行）。scraper 容器沒有 LLM 設定也沒有 http 套件。
- **判決必須持久化**：現在被「略過」的訊息不寫 `delivery_state`，每次重啟都會被 reconcile 重排重跑；不存判決就會每次重啟重判、重貼隔離區。
- **放回主頻道**要走 relay 原本的發送流程；`resend_telegram_by_id`（`/resend_article`）不合併相簿、也不寫 `delivery_state`。
- **順便發現的既有問題**：① 相簿晚到的成員不寫 `delivery_state`（DB 有 460 則），每次重啟空跑一次（09-29 起可見：每次重啟約 65 個舊相簿各印兩行「相簿補圖已過時效，略過」）；② 發送失敗也推進游標，要等重啟才重試；③ `/server_manager` 的 Telegram 路由用來源**名稱**當 key 寫入，但只有 chat_id 當 key 才查得到（第一個來源除外）。
- **離線測試樣本**（`telegram_messages.id`）
  - 應隔離（灌水／閒聊）：13371、13404、13430、13431、13447、13451、13474、13643、13646、13649、13478、13650、13651、13661、13681、13766、13510
  - 應隔離（罵人）：7378、7379、9028、9179、9842、1474、1475、6941、6953、13076、13362、13433、13449、13487、13638、13678
  - 應放行（看起來像垃圾但有情報）：1、13025、9382、11368、12750、13685、13391、13392、12492、11584、6937、13299、11205、11557、4253、12190、9153、13189、13181、13182、12458、13475、9531、12285、13393、10025、13381、13387、13461、13481（13480 自寫假劇情的免責聲明，要看前文）、13682、13653、12071

**待決問題（grill 暫停中，2026-09-28；每題附當時的建議）**
- **判錯時偏哪邊**：建議「拿不準就放行」。頻道價值在爆料、短訊息多半是情報；錯放一則水代價小，錯關一則情報代價大。
- **LLM 不能用時**：建議直接放行。打 LLM 前先看 GPU 租約（產圖期間完全不碰 LLM，避免觸發 27B 重載搶 VRAM）；被 /askai 等短暫佔用時最多等 60 秒。
- **垃圾的定義**：建議只用一個標準——「對看頻道的人有沒有遊戲資訊」。灌水、罵人、閒聊（「追月节快乐」）都隔離；帶髒話但有資訊的放行（「我操 老库牛逼，又开服这么早」）。標籤（灌水／罵人／閒聊／正常）存進 DB 供統計。
- **反方向（主頻道 → 隔離區）**：建議第一版不做；每次「放回」都記錄下來，當作判錯樣本調 prompt。
- **隔離 thread 開在哪**：建議開在 #🌘角色內鬼情報 底下的公開 thread；母頻道做成 /server_manager 可改的設定。
- **誰能按「放回主頻道」**：建議管理員（同點名管理按鈕）。注意 `role_mapping` 的 Moderator 目前是空的，用它等於只有 owner 能按。
- **判斷單位**：相簿整組判、整組隔離；只有圖片沒文字的一律放行；只有一張 Telegram 貼圖的用規則直接隔離；判斷時附同頻道前幾則當上下文（例：13481 是 13480 自寫假劇情的免責聲明）。
- **順序 vs 速度**：建議改成一次只處理一則，保證 Discord 上的順序（量小，尖峰一小時 22 則）。
- **上線方式**：建議先用上方的歷史樣本離線測，「有情報卻被隔離」為 0 才上線，不跑影子模式。
- **順便發現的既有問題**：建議「相簿晚到成員不寫 delivery_state」這次一起修（同一段程式）；其餘兩項記待辦。

**不反對就照做的預設**：判斷用主模型並關閉思考（不用 7B 審核模型，Lemonade 一次只放一個大模型，會互相擠出）；判決存新表（判決、標籤、理由、隔離訊息 id、放回者、放回時間），隔離那則也寫 delivery_state；放回走 relay 原本的發送流程（不走 `resend_telegram_by_id`，它不合併相簿、不寫紀錄）；放回後隔離區那則改成「已由 X 放回」並停用按鈕；按鈕用固定 custom_id＋用訊息 id 查 DB；`/resend_article` 不過濾、補掃與重播要過濾、不回頭判歷史訊息；thread 被刪或封存時自動重建／解封。

**開工前注意**：另一個工作階段 09-28 改過 `telegram_relay_service.py` 的相簿處理（已 commit `3a1379c`、`ea81a83`），動工前先確認現況。

**狀態**：設計討論中（grill 暫停）；以上建議都還沒經使用者確認。

---

## 週期活動提醒：深塔海墟（2026-09-29 已實作，待部署驗證）

<!-- @meta
id: periodic-event-reminder
type: STATE
status: confirmed
last_confirmed: 2026-09-29
depends_on: event-announce-link-and-dedup-fix
affects: 排程、身份組、config.json
-->

**需求（使用者 2026-09-28 提出）**
- 《鳴潮》的週期活動「深塔海墟」每四週重置一次，**重置時 @ 特定身份組**提醒。
- 這個身份組**成員可自由領取**（自助加入／退出）。
- 提醒要放**一般文字頻道還是論壇頻道**：使用者還在猶豫，要一起討論再決定。
- 要跟既有的「公告 → 自動建 Discord 伺服器活動」怎麼整合，待確認。

**查證事實（2026-09-28，唯讀調查）**
- **週期**：深塔（逆境深塔）與海墟（冥歌海墟）各自每 **28 天**、**週一 04:00（UTC+8，用 `SERVER_TZ`）**重置，**兩者錯開 14 天**（每兩週輪到一個）。
  - 海墟錨點 **2026-02-16 04:00**（唯一官方來源：FB 貼文 273）→ 下三次 10/26、11/23、12/21
  - 深塔錨點 **2026-03-02 04:00**（聊天紀錄與使用者在 🤖公告與建議專區「新功能」討論串的手記）→ 下三次 10/12、11/09、12/07
  - 11 個已知重置日全部落在 28 天格點上；官方從未公告週期 → 只能「錨點 + 28 天」。
  - 版本維護撞重置日的例子：3.4 = 2026-06-08 週一 04:00~11:00（那期要等維護結束才能打，但週期沒被推移）。
- **矩陣（終焉矩陣）跟版本走**，不是固定週期；但規則可由版本日推算（2026-09-29 查證）：
  - **週期**（S1「無盡危局」3.2～3.4、S2「險境強襲」3.5～3.8）底下，**每個版本一個階段**（S2-1、S2-2…），每階段新增三個挑戰任務。
  - **階段開放＝該版本更新維護開始日 +7 天的 04:00**；**階段結束＝下一版維護開始前**（例：S1 第二階段「2026年5月7日04:00 ~ 3.4版本維修前」）。證據：巴哈「終焉矩陣」看板各階段隊伍分享串主文的明確時程，7 次開放 6 次 +7 天（唯一例外是先行版第一次上線當天開放）。
  - **下一版更新日可以提早約 3 週推得**：每版最後一個卡池（「✦活動時間：… ~ YYYY年M月D日11:59」）都在「下一版更新前一天 11:59」結束，下一版隔天 04:00 開始維護（2.0～3.7 共 18 版全數 +16 小時）。下半卡池公告約在版本中段發出，比維護預告（約提前一週）早。
  - **3.7 之後的下一版在 11/12 04:00 更新**（使用者確認；版本號未定，可能是 3.8 或 4.0）。巴哈玩家轉述前瞻的「版本期間：2026/9/30 ～ 2026/11/11」，結束日是**最後一天**（＝最後卡池結束日），不是更新日。→ S2-3 預計 10/7 04:00 ～ 11/12 03:59。**推算一律用日期、不依賴版本號**。
  - 深塔／海墟起算日另以巴哈 44 期隊伍分享串驗證：43 期吻合，唯一例外是海墟第 1 期（2025-02-13 隨 2.1 上線）。社群期數：深塔第 33 期＝2026-03-02、海墟第 14 期＝2026-02-16。
- 既有「公告 → 伺服器活動」**從未**替深塔／海墟建過活動（閘門要求「活動時間」字樣）。現有 8 個 bot 建的活動，「有興趣」人數全部是 0。
- **伺服器**：Onboarding（原生「頻道與身分組」）關閉；bot 有 ADMINISTRATOR 且位置最高；24 個身份組全部 `mentionable=False`；程式裡沒有任何自助領身份組功能（`add_roles` 0 筆），persistent view 慣例成熟可沿用。
- **候選頻道**：🍼深塔海墟矩陣-代打（text `1480854656342294569`，主題是代打免責聲明，@everyone 可看）；📶活動情報（forum `1276560265533587591`，@everyone 唯讀、無活躍貼文）；🌸祕密花園（深塔／海墟討論 601 則裡有 561 則在這，但「鳴潮皇帝」看不到）。
- **論壇 @身份組 的通知行為未驗證**：據社群回報，超過 100 人的身份組在討論串裡可能被拒；bot 開新貼文時首則的身份組 ping 可能不通知；被加進串的人預設收到每則回覆的通知。
- **坑**：新身份組**不要**加進幽靈點名的排除清單（那份清單幾乎包含所有自訂身份組，加進去等於訂提醒就免點名）；bot 沒有全域 `allowed_mentions`，提醒訊息要明確指定 `AllowedMentions(roles=[該身份組])`。

**已定案（2026-09-28）**
- 發在**一般文字頻道 🍼深塔海墟矩陣-代打**，不用論壇（這個群不用論壇、論壇 @ 通知不可靠；討論留在原本的地方）。
- **一個身份組**涵蓋深塔與海墟（每兩週輪到誰就提醒誰）。
- **第一版只做深塔、海墟**；設定設計成「一個項目＝起算日＋週期」的清單，矩陣日後有可靠來源再加。
- **自助領取用按鈕**：面板上放「訂閱／取消訂閱」（persistent view），按下只回按的人看得到的訊息。
- **面板不釘選、改置底，而且立即置底**：發完提醒、或提醒頻道裡**有人講話**就立即「刪舊發新」（bot 自己的訊息不算，避免循環）；連發時合併，同一時間最多一次在跑、一次排隊。走共用的 `utils.panel_bump.PanelBumper`。提醒訊息本身不附按鈕。面板顯示各項目的下次重置日期。
- **提醒時間**：結束前提醒＝重置前一天 20:00，正常 @；重置提醒＝週一 04:00 準時，**靜音 @**（`silent=True`：有提及紅點、不推播）。
- **身份組「深塔海墟提醒」**：綁提醒頻道時由 bot 自動建立（`mentionable=False`、無權限），被刪會自動重建；不加進點名排除清單；提醒只 @ 這個身份組。
- **文案**：中性工具口吻，不用琇紫人設。
- **起算日與週期寫在程式的設定類別**（改了要重啟；`config.json` 屬使用者設定檔，AI 不自行改寫）；時間一律用 `SERVER_TZ`。
- **撞版本維護第一版不處理**（現有版本時間解析只記維護結束、只能用版本號查；約 20 期一次；重置提醒本來就靜音）。
- **補發**：bot 離線錯過時，結束前提醒補到重置前、重置提醒補到當天 12:00；去重用 StateDB `sent_content`。不建 Discord 活動、不加管理指令。
- **驗證**：單元測試以使用者手記為標準答案（海墟 8/3、8/31、9/28、10/26；深塔 8/17、9/14、10/12）；部署後依序：綁頻道看面板日期 → 按訂閱 → 整合腳本在正式頻道發真的「海墟已重置（到 10/26）」靜音 @ → 結束前提醒樣本發到只有管理員看得到的頻道測正常 @。
- 使用者決定**先做深塔提醒**；Persona 後續、Telegram 過濾、ComfyUI 暫停。

**矩陣接入的決定（2026-09-29）**
- 深塔、海墟、矩陣**共用一個身份組**，名稱改為「**週期活動提醒**」。
- 矩陣提醒**不寫階段編號**（S2-3 這種要靠版本號解析，版本號可能跳 4.0）。
- 版本延期時官方一定會公告：排程每次都依最新公告重算，面板與提醒日期跟著更新即可。
- 深塔／海墟期數：使用者覺得可有可無；可由「深塔第 33 期＝2026-03-02、海墟第 14 期＝2026-02-16、每 28 天 +1」直接推算。

**矩陣接入實作（2026-09-29，618 測試全過，未 commit）**
- `VersionDateResolver.update_starts()`（`services/events/event_scheduler.py`）：**不快取、每次重讀**官方公告，回傳所有版本更新維護的開始時刻；來源一＝「X.Y版本」標題＋「更新維護時間」的第一個日期，來源二＝標題含「喚取」「第二期」的下半卡池結束日隔天 04:00（前後 7 天內有官方時間就以官方為準）。版本號只用來認公告。實測：真實 DB 每次約 6 ms、不需要 index（`LIKE '%…%'` 本來就用不到 index）；卡池推算的 7 筆與官方時間全數一致。原本的 `_load()`／`update_time()` 不動。
- 設定：`VersionStageItem`（key=matrix、🧩、開放延遲 7 天）；`role_name` 改「週期活動提醒」，bot 啟動與每次取身份組時**依設定同步名稱**。
- 純邏輯：`Reminder.cycle` 改名 `item`；矩陣結束前提醒＝下一次更新前一天 20:00（正常 @），開放提醒＝更新 +7 天 04:00（靜音 @）；**不知道下一次更新就不發結束前提醒**（不用 +42 天硬猜）。
- 面板：「**時程**」下深塔／海墟之外多一行矩陣：空窗週「新階段 10/7（週三）04:00 開放」、已知結束「本階段開放中，9/30（週三）04:00 結束」、未知「本階段開放中，於版本末結束」。排程每輪比對面板標題＋內文（存在 runtime 的 `panel_content`），**一變就自動重發**。
- 讀 articles.db 走 `asyncio.to_thread`，不卡 event loop。
- 測試新增 19 項（開放日對上巴哈 S1-1～S2-2、結束前／開放提醒、空窗週、未知下一版、卡池推算、官方優先、身份組改名、面板變更才重發）；突變驗證：+7 改 +6、卡池少了隔天、未知時硬猜 +42，三種都會紅。
- **已修（2026-09-29，使用者要求：bot 會長時間不重啟）**：活動自動發布用的 `_version_resolver` 原本是模組層單例、只讀一次 DB，bot 啟動後才發的版本公告看不到，「X版本更新後」起算的活動會被略過。改為：① `refresh()` 每次排活動前在執行緒重讀，讀取失敗保留上次結果、版本有增減才寫 log；規劃過程中的 `update_time()` 只查記憶體。② 開 articles.db 改用一般唯讀 `mode=ro`，**不再用 `immutable=1`**：articles.db 是 WAL 模式（`-wal` 檔約 99 MB），immutable 會忽略還沒合併回主檔的 WAL，看不到剛寫入的公告，爬蟲合併時還可能讀到錯誤結果。新測試 `test_version_date_resolver.py`（啟動後才發的公告、update_time 不碰 DB、失敗保留、WAL 可見）；突變驗證改回 immutable、refresh 退化成只讀一次都會紅。

**實作（2026-09-29，已 commit）**
- `sys_settings/periodic_reminder_settings.py`：起算日、週期、提醒時刻、身份組名稱、runtime 路徑
- `services/events/periodic_reminder.py`：純邏輯（推算重置、到期／補發判斷、文案、面板內容）
- `commands/periodic_reminder_commands.py`：排程迴圈（最多睡 1 小時就重算）、訂閱按鈕（persistent view）、`ensure_role`（id → 同名既有身份組 → 建立）、`on_message` 有人講話就置底
- `settings/channel_registry.py`：登記「週期提醒頻道」，綁定時自動建身份組＋發面板；`discord_bot.py` 的 `COMMAND_MODULES` 加入；`.gitignore` 加 runtime 檔
- `test/test_periodic_reminder.py` 33 項（突變驗證過：靜音顛倒、提醒晚一小時、週期改 27 天、拿掉今天／明天判斷都會紅）；文案只比對關鍵資訊（誰、項目、日期、今天／明天），不逐字比對
- `test/integration/it_periodic_reminder.py`：手動發一則提醒實測（不寫 StateDB、不置底）

**面板置底收斂（2026-09-29，586 測試全過，已 commit）**
- 新增 `utils/panel_bump.py`：`PanelBumper` 只管「在哪、刪舊、發新、記住、同時只做一次」，面板長相由呼叫端的 `send` 決定。位置記在各自 runtime 檔的 `{key_prefix}channel_id / message_id`，寫入時保留其他欄位。**沒有完整紀錄時**才翻頻道最近 50 則，刪掉 bot 自己發、custom_id **精確**屬於該面板的殘留面板（社群查詢討論串的 `community_lookup:control:refresh` 不會被誤刪）。
- **社群查詢**改用它（runtime 格式本來就相同，資料不用搬）；查詢後的置底改成 `request_bump`（連發合併）。
- **自我介紹**改用它（`key_prefix="intro_panel_"`）：面板頻道 id 從 `config.json` 搬到 `settings/intro_panel_runtime.json`，**不再每次送出表單就重寫整份 `config.json`**。上線後第一次置底因為 runtime 只有訊息 id，會翻找刪掉現在的舊面板，之後就用紀錄。`config.json` 裡的 `intro_panel_channel_id` 已無人讀寫，使用者要刪可自行刪。
- **音樂面板暫不接入**（見點歌機器人待辦）。
- 動工前三份 runtime 檔已備份到 scratchpad（`runtime_backup_0929/`，主機重開會清空）。
- 突變驗證：不比對 custom_id、連發不合併、只有訊息 id 就當完整紀錄、寫檔蓋掉其他欄位，四種都會紅。

**部署與實測（使用者操作）**
- [x] `docker compose restart discord-bot`（09-29 00:28；當時 logger 用 `__name__`，INFO 沒輸出，已改成 `discord_bot`，下次重啟才看得到「週期提醒：接下來 →」）
- [x] `/server_manager` → 設定頻道 →「週期提醒頻道」選 🍼深塔海墟矩陣-代打（09-29 00:29；身份組 `1554168140441718885`、面板已發出）
- [x] 按「訂閱」（身份組成員數 1）
- [ ] 容器內 `python -m test.integration.it_periodic_reminder reset sea`：**已發送**（09-29）；待使用者確認手機沒跳通知、頻道有紅點
- [ ] 容器內 `python -m test.integration.it_periodic_reminder ending tower <只有管理員看得到的頻道id>`：確認手機有跳通知
- [ ] 10/11 20:00 第一則正式提醒：確認有發、面板被頂到最下面
- [ ] **再重啟一次**（置底收斂＋log 修正要重啟才生效）後確認：
  - 在提醒頻道講一句話 → 面板立即移到最下面
  - 送出一次自介 → 舊的自介面板被刪、新面板在最下面，而且 `settings/intro_panel_runtime.json` 多了 `intro_panel_channel_id`、`config.json` 沒被改動
  - 做一次社群查詢 → 查詢面板照常置底

---

## 新成員歡迎訊息：接手 ProBot（2026-09-28 已實作，待部署驗證）

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

---

## 活動自動發布：連結指向錯誤 + 重複建活動（2026-09-22 已實作，待部署驗證）

<!-- @meta
id: event-announce-link-and-dedup-fix
type: STATE
status: confirmed
last_confirmed: 2026-09-30
depends_on: event-announce-auto-schedule
affects: services/events/event_scheduler.py, services/events/event_time_parser.py, services/relay/article_monitor.py, services/state_db.py
-->

> 原始功能區塊已於 2026-08-18 歸檔至 `TODO-completed.md`（id: `event-announce-auto-schedule`）。
> 本區塊是它重開的修正輪，只記這次改了什麼與為什麼。

### 症狀

活動 `1539556072082112604`「[群聲共振模擬域]戰鬥活動」描述裡的「公告出處」
指向訊息 `1539556070119440388`，點進去那則訊息**完全沒有提到這個活動**。

### 根因：錯在文章轉發，不在活動偵測

| 層 | 位置 | 問題 |
|---|---|---|
| ① 兩邊讀的不是同一份內容 | `article_monitor.py` | 活動偵測讀 `article_content_full`（article 5340＝8,454 字）；轉發 embed 讀 `article_desc` |
| ② fallback 變成唯一路徑 | 舊 `article_monitor.py:174` | `article_desc` **全庫 532 篇皆為空字串** → `parsed_content[:300]` 這條「沒摘要時的預覽」成為唯一路徑，8,454 字只發出 303 字。下方那行「限制 4000 字」的保護從上線到現在**一次都沒觸發過** |
| ③ 訊息是死路 | 舊 `article_monitor.py:197` | `discord.Embed(...)` 沒有 `url=`（`fb_monitor.py:145` 有），送出時也沒有 `content=`，點進去無法跳回官網全文 |

5340 的 6 個活動名分別在轉換後全文的第 1347 / 1524 / 1632 / 1755 / 1899 / 2010 字，**全部 > 300**。
全庫量化：315 個 article 來源活動中，**100 個（31.7%）**的活動名在轉發訊息可見文字裡找不到。

### 同時修掉：同一活動被建兩次

`normalize_title` 的核心名只認 `「」『』` 與 `【】[]`，不認半形 `<>`：

```
5340 匯總帖    → fp = 群聲共振模擬域|202608221000|202609291159
5351 專屬公告  → fp = 活動預告<群聲共振模擬域>戰鬥活動即將開啟|202608221000|202609291159
```

起訖相同、指紋不同 → 去重擋不住 → 線上 `…604` 與 `…681` 兩個活動同時存在。
全庫 14 篇「活動預告」型公告中，用 `「」` 的 3 篇擋得住、用 `<>` 的 11 篇全部會重複。

### 改了什麼

| 檔案 | 改動 |
|---|---|
| `article_monitor.py` | 截斷 300 → `EMBED_DESC_LIMIT = 1200`；截斷時附「閱讀完整公告」連結；`embed` 補 `url=`；移除「📝 內容預覽」欄位（條件是 `<=1000` 字，等於文章越長看到越少）；新增 `official_article_url()` 為官網網址的唯一來源 |
| `event_time_parser.py` | `normalize_title` 核心名加入半形 `<>`；新增 `_extract_body()` 抽活動段落片段；`ParsedEvent` 加 `body` |
| `event_scheduler.py` | 活動描述嵌片段 + 公告出處/官方原文雙連結（先保連結再給片段）；**升級既有活動**（封面＋描述）；同名+重疊視為改期；`_SCHEDULE_LOCK` 序列化；`_migrate_fingerprints_once` 指紋遷移；建立成功但寫 DB 失敗分開報；四種靜默丟棄補 log |
| `state_db.py` | `created_events` 加 `core_name` / `has_image` / `body` / `superseded_by` / `user_deleted` / `deleted_at` / `updated_at` + index；新增 `find_overlapping_event` / `find_same_name_events` / `list_created_events` / `update_created_event` / `mark_created_event_deleted` / `clear_event_tombstone` / `delete_created_event`；**移除 `is_event_created`**（已無呼叫者，留著會讓人繞過升級路徑）。**只留「有人讀」的欄位**——一度加過 `quality` 與 `message_url`，兩者寫了從來沒人讀，而存著一個「品質分」正是下一個人會拿來當閘門的誘餌（就是這次修掉的 bug），連同 `content_quality()` 與 `from_umbrella` 一起刪 |
| 測試 | 新增 `test_event_upgrade.py`（21，副作用層原本零覆蓋）、`test_article_embed.py`（8）；`test_shared_conventions.py` 加「官方公告原文網址」AST 守衛 |

### 支撐決策的實測數據（2026-09-22）

- `article_menus.article_desc`：**532 / 532 皆為空字串**
- FB 貼文 **832 / 834（99.8%）有圖**，平均 2.7 張；article 的 `article_cover` /
  `content_cover` / `suggest_cover` **全庫皆空**，只能從內文抓第一張 `<img>`（494/532 有）
- 公告字數：p50 = 400、p75 = 565、p90 = 2558、p99 = 9436。切 1200 有 **85.2%** 完整發出；
  拉到 2000 / 4000 只多 2.6% / 10.5%，卻會讓版本說明帖變成 40~50 行
- 括號用法：`<>` 出現在 38 個標題（內容都是活動名）；**`《》` 出現在 472 個標題，
  其中 328 個包的是遊戲名「鳴潮」** → 收進來會把 328 個公告壓成同一個核心名，故不收；
  `〈〉` 與全形 `＜＞` 在 1366 個標題中一次都沒出現
- 跨來源指紋對得上的有 **45 組**（升級路徑會實際被觸發）。最典型的就是被浪費掉的這 4 次：

  | 活動 | 先到（無圖） | 後到（有圖） | 相隔 |
  |---|---|---|---:|
  | 第二索拉・詭影迷蹤 | article 5340 匯總帖 8/19 | fb 774（2 張圖） | 7 天 |
  | 清弦紀流年 | article 5340 匯總帖 8/19 | fb 793（2 張圖） | 14 天 |
  | 若夢仍有回聲 | article 5340 匯總帖 8/19 | fb 810（1 張圖） | 21 天 |
  | 潮汐覓聞 | article 5340 匯總帖 8/19 | fb 822（1 張圖） | 28 天 |

- 「同名+重疊」全庫會合併 66 組，其中**只有 1 組**（article 995「往歲乘霄醒驚蟄」1.1版本內容說明，
  3 個活動標題都抽不出來而一起退用貼文標題）是同一則公告內部同名不同區間 →
  已用 `exclude_source` 排除，並補迴歸測試

### 指紋遷移（部署時會自動跑一次）

`normalize_title` 一改，既有指紋全部失配 → 去重表等同失效 → **線上活動會整批重建**。
故 `maybe_schedule_events` 在鎖內先跑 `_migrate_fingerprints_once`（冪等、程序內只一次；
失敗則本次不建任何活動並於下篇公告重試）。

用 `sent_articles.db` 的副本演練（未動原始檔）：

```
32 筆進、32 筆出（不掉筆）
指紋更新 6 筆（2 筆是 <> 修正，4 筆是 2026-07 舊 code 留下的錯誤指紋）
偵測到重複活動 1 組 → 記 ERROR、兩列都保留，不自動刪
core_name 全數回填；再跑一次完全冪等
```

### 升級既有活動：為什麼是四軸，而不是一個品質分

> **這段是防止「被簡化回去」的記錄。** 實作中途真的寫過「品質總分變高
> 就換描述與封面」的版本，對抗性複查後確認不可行，三個症狀都真實重現：
>
> | 用單一總分當閘門 | 實際後果 |
> |---|---|
> | 改期時品質分通常沒變 → 走不進換描述的分支 | Discord 上時間改了，描述第一行的「活動時間：…」還是舊的，**活動頁自相矛盾** |
> | 「非匯總帖 +1」當內容品質的代理指標 | 專屬帖開頭常是劇情導言、匯總帖寫的才是玩法與獎勵 → 描述反而**變短**（實測 370→118 字） |
> | 分數沒變高就整筆 return | 全庫 **14.6%** 的公告一個字都沒更新 |
>
> 根因是「封面／描述／時間／名稱」本來就是四件獨立的事，綁在同一個純量上必然出事。
> 那個分數連同 `content_quality()` 與 `from_umbrella` 都已刪除 —— 留著一個沒人讀的
> 「品質分」就是下一個人拿來當閘門的誘餌。log 直接印實際訊號（封面有無、片段字數）。

**四軸各自判斷，互不綁定**：

1. **時間**：起訖與 DB 不同 → 同步。**已開始的活動只改 `end_time`** —— `p.start` 是
   clamp 過的 `max(now+5min, logical_start)`，送出去會把進行中的活動推到 5 分鐘後開始；
   且 discord.py 把 start/end 併進同一個 PATCH，Discord 一拒絕連延長的 end 也一起失效。
2. **描述**：新片段 ≥ 既有 +40 字才換；**改期時一律重建**（時間就寫在第一行），
   但此時若新片段沒比較好就沿用既有片段，不為了修時間而讓描述變差。
3. **封面**：既有沒圖才補；既有已有圖不動（換圖對使用者沒價值，只會反覆重傳）。
   判定移到 `_fetch_event` 之後，不再白下載（實測單張 0.8~1.0 MB）。
0. **前置閘**：既有活動狀態是 `completed`／`canceled` 就**完全不碰**。Discord 會拒絕編輯
   已結束的活動，沒有這道閘，使用者手動提早結束一個活動之後，每來一篇同活動的新公告
   就白試一次編輯、白抓一次封面、白記一行 warning。閘門放在下載封面之前。
   （去重不受影響：那一列從未被刪，所以結束的活動不會被重建；而未來同名活動的新檔期
   因為指紋帶著時間區間、同名合併只認重疊，一樣照建 —— `聲弦滌蕩` 線上就有 3 檔共存。）
4. **名稱**：既有是預告型標題（`活動預告`／`即將開啟`…）而新來源不是 → 改名。
   收 `<>` 進核心名之後預告帖與正式公告會合併，不改名的話活動開跑一個月還寫「即將開啟」。

**另外五項保護**：

| 問題 | 做法 |
|---|---|
| 使用者從 Discord 刪掉活動 → 若 `on_scheduled_event_delete` **實體刪列**，7~28 天後另一來源會把它復活 | `mark_created_event_deleted` 改成**立墓碑**（`user_deleted` / `deleted_at`）；兩條比對路徑仍撈得到，撈到就什麼都不做 |
| `_fetch_event` 把所有例外當成「活動被刪」，一次 503 ＝ 該來源的封面／描述永久遺失（來源已 `mark_content_as_sent`） | 只有 `discord.NotFound` 回 None，其餘往外拋給每筆各自的 try |
| 重疊比對若排除「整則公告」→ `/resend_article` 重送改期公告時對不到自己那一列，建出第二個活動 | 改成排除「**本輪已配對的指紋**」(`exclude_fingerprints`)；同一則公告內部仍不互相吃掉 |
| 遷移碰撞列若留空 `core_name` → 對兩條查詢同時隱形，正本一出事就擋不住重複 | 碰撞列照樣回填 `core_name`，另標 `superseded_by` 指向正本；查詢排序正本優先 |
| 遷移單列失敗仍標記完成 | 有任何失敗就不標記、拋出，本次不建任何活動，下一篇公告重試 |

**刻意不做**：官方改期到**完全不重疊**的新區間時不自動合併 —— 不重疊也可能只是同一活動的
下一個檔期（`[聲弦滌蕩]` 每隔幾週一檔），自動併會把正常的循環活動吃掉，而歷史資料上
「改期」一次都沒出現過。改成**偵測到同名活動仍在進行／未開始就 log warning**。

**驗證**：397 測試全過（新增 40 條，含副作用層原本零覆蓋的部分）；以 `sent_articles.db`
副本演練遷移：32 列不掉、`core_name` 空列 0、分身正確標記、重疊查詢回正本、墓碑擋得住復活。

### 2026-09-30 追加：已處理過的重複不再每次報 ERROR（已上線・`f7d4a14`）

**機制（一句話）**：指紋遷移看到「這一列先前已經標成分身」就只計數、不再報 ERROR；第一次發現的分身若活動已結束，降成 INFO。

- **為什麼**：9/22 修正前留下的那一組「群聲共振模擬域」（`…604` 正本、`…681` 分身），9/22 之後每次重啟的遷移都再報一次 ERROR（累計 26 次）。它早就標好 `superseded_by`、擋得住重複，兩個活動也都在 9/29 11:59 結束——重複報只會把真正的錯誤淹沒。
- **改了什麼**（[event_scheduler.py](src/services/events/event_scheduler.py) `_migrate_fingerprints_once`）：
  - 分身列 `superseded_by` 已指向新指紋 → 算「先前已標記」，不寫 ERROR，也不重寫這一列（只在 `core_name` 不對時回填）。
  - 新發現的分身照樣標記；活動已結束（`end_utc8` 早於現在）→ INFO「只標記分身、不需處理」；還沒結束 → 照舊 ERROR 請人手動刪。
  - 摘要改成「新發現重複活動 N 組，先前已標記 M 組」。`now` 參數只給測試固定時間用。
- **測試**（[test_event_upgrade.py](src/test/test_event_upgrade.py)）：已知分身只在第一次報 ERROR、第二次不報也不重寫；已結束活動的新分身有標記但不報 ERROR；原本的相撞測試固定在活動結束前（仍報 ERROR）。三種故意改壞都會紅。
- **驗證時機**：遷移不在開機時跑，是第一篇含活動的公告進來、建立活動前才跑一次；預期 log「新發現重複活動 0 組，先前已標記 1 組」、沒有 ERROR。

### 待辦 / 下一步

- [ ] 對抗性複查還有 2 個面向（embed／parser）與驗證階段未跑完，結果出來要再過一次
- [x] `docker compose restart discord-bot`（9/22 之後已多次重啟）
- [x] 看 log 的「指紋遷移完成」與「⚠️ 指紋遷移發現重複活動」兩行（9/30 10:08 查：共 36 列、更新 0 列、重複 1 組、失敗 0 列；重複的就是修正前留下的那一組）
- [x] ~~人工刪掉重複活動~~ 不需要：`1539556072082112604` 與 `1539937681176272916` 都已在 9/29 11:59 結束，第二筆資料庫已標 `superseded_by`；遷移重複報 ERROR 的問題由上面的追加修正處理
- [x] 後到的來源就地升級、不另建（9/30 10:08 log：「♻️ 已升級既有活動：團團勇者大亂鬥」；9/22 之後遷移沒有發現新的重複）
- [ ] 下一篇含活動的公告進來時，確認遷移摘要是「新發現 0 組，先前已標記 1 組」、沒有 ERROR

### 殘留風險（已知未做）

- 活動段落片段與轉發訊息內容來自兩套解析（`strip_html` vs `html2text`），文字可能略有差異
- 超過 4,000 字的公告（全庫 23 篇）仍只轉發前 1,200 字，其餘靠官網連結
- `created_events` 無清理機制，已結束的列會持續累積（線上 32 筆中 23 筆已是孤兒）
- 使用者手動刪掉的活動不會被**自動來源**重建（墓碑）；`/resend_article` 是唯一解得開的入口
  （人明確要求重抓才算數）。活動若還在伺服器上就解墓碑走升級，已被刪掉才整列丟掉重建
- 官方改期到完全不重疊的新區間時不自動合併，只 log warning（理由見上）

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
> - Lemonade 已升到 **11.9.0**，下方 09-02 的三項實測（unload／自動重載／recipe 保留）是在 11.5.0 上做的，需要重測；`POST /free`（ComfyUI 放 VRAM）從未實測。
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
- [x] **（2026-09-02 定案）** 圖發到 `ai_diary_channel_id`，與日記同一頻道，不新增設定
- [x] **（2026-09-02 已修）** `discord_bot.py:339` 的 `DIARY_TZ = _tz(_td(hours=8))` 違反
      「全站時區只能用 `APP_TZ`」，因 `_tz`/`_td` 別名溜過 regex 守衛。**兩層都修了**：
      ① 改用 `APP_TZ`；② 該條規則從 regex 改走 **AST**（`_find_hardcoded_utc_offsets`），
      連 import 別名與 `datetime.timezone(...)` 模組屬性形式一起抓，並補 `TimezoneGuardTests`
      五項守住（含「`timedelta(hours=8)` 當時間長度是合法的、不可誤判」）。
      **驗證方式**：暫時還原成舊寫法 → 守衛確實紅在 `discord_bot.py:339` → 復原。
      全專案掃過，這是唯一一處別名繞過（`extract_fingerprint` / `event_time_parser` 是既有合法例外）

### 檔名正名（2026-09-29 隨 `llm/` 依角色分子資料夾完成四項；`lemonade_gate` 仍待定）

| 現在 | 改成 | import 點 |
|---|---|---|
| `llm/llm_http_client.py` | ✅ 已改為 `llm/client/http_client.py`（套件名複述兩次） | 3 |
| `llm/safe_llm_embedding.py` | ✅ 已改為 `llm/client/embedding_client.py`（"safe" 是形容詞不是分類） | 6 |
| `llm/chat_persistence.py` | ✅ 已改為 `llm/storage/store_chat.py`（它就是 store，卻跟另外 3 個 `*_store` 分家） | 12 |
| `llm/diary_reflection.py` | ✅ 已改為 `llm/ambient/ambient_diary.py`（它 import `ambient_reply`，是 ambient 家族） | 4 |
| `llm/lemonade_gate.py`（現在位於 `llm/client/`） | 待定（`gpu_gate` / `resource_gate`）——**等它真的管到 GPU 資源再改**，否則名字更騙人 | 10 |

**已決定不做**：`llm/`、`services/` 的資料夾重組（成本 ~160 個 import 點，效益只有排序好看）。**2026-09-29 更新**：`llm/` 部分已由使用者推翻，改依角色分子資料夾（見[程式結構整理](#程式結構整理2026-09-29-構想grill-中)）；`services/` 仍不重組。
子資料夾的判準是「≥6 檔／有封裝邊界／可預期會長」滿足其一——`persona_agent/`、`retrievers/web/`
是對的示範，其餘各群目前都不達標。**ComfyUI 另開 `src/imagegen/`，不塞進 `llm/`**（塞了 `llm/`
就變成「AI 相關雜物間」，重蹈 `services/` 覆轍）。

---

## Persona Agent M7：精簡版發布（2026-09-28 已上線，觀察中）

<!-- @meta
id: persona-extraction-agent
type: STATE
status: confirmed
last_confirmed: 2026-09-28
depends_on: personality_extractor, llm_service, lemonade_gate, member_profile_store
affects: auto_personality、插話／askai 人物卡、discord_bot 04:00 排程
-->

> 早期「影子模式」規劃（M1~M6、線上實測、五項定案）已歸檔到 `TODO-completed.md`。
> 原 `HANDOFF_2026-09-27_persona-agent-M7.md` 已刪除，仍有效的內容收在本區。

**架構（2026-09-28 定案）**：04:00 維護五步（`discord_bot._run_daily_maintenance_once`）
① emoji 字典 → ② 招牌梗衰減 → ③ production 人格萃取（過渡期備援，只寫 ④ 沒涵蓋的人）
→ ④ persona agent（每晚主力；完整描述寫 `persona_agent_versions`，bot 讀不到；只重跑上次跑完後有新發言的人）
→ ⑤ 發布精簡版（`llm/persona/agent/publish.py`；**不經 LLM、整條原文照抄**，寫進 `auto_personality`；插話與 /askai 只讀這裡）。

**狀態**
- commit：`c544036`、`b3dad1c`、`aafdc85`、`948ab96`、`2a0d0cf`（`publish_mode="on"`）。
- 09-28 14:01 手動跑 ⑤（on）寫入 62 人；09-29 04:00 起由排程寫入。約 05:45 跑到 ⑤。
- ③ 仍對門檻內約 36 人跑 LLM（約 12 分鐘），但這些人都有精簡版，實際寫入 0 人；觀察約一週後決定拿掉 ③。

**回滾**（依程式推得，未實測）：revert `2a0d0cf` → 重啟 → 下一個 04:00 由 ③ 把門檻內約 36 人覆寫回 ③ 的描述；
門檻外約 26 人會停在最後一版精簡版（沒有備份，使用者已接受）。日間重啟不會立刻變回來（補跑檢查看到 ⑤ 的寫入時間會跳過）。

**已接受的取捨（不要再提）**：啟動補跑看 `MAX(last_extracted_at)`；不備份 `auto_personality`；精簡版比 ③ 薄照換；近況沒有時間上限。

**已知、刻意沒處理**：被隔離的人停在最後一版精簡版；`index_auto_personality` 先刪後寫（embedding 失敗那人暫時沒描述）；
③ 存入時硬切 200 字；④ 意思相近的條目可能兩條都被挑到；③ 與精簡版都不看招牌梗的 spicy／封鎖閘門。

**09-28 發現的品質問題（討論中）**
- 隱私內容進了 prompt：62 筆中至少 5 筆含居住地、職業、宗教、持股；另有一筆寫了聚餐日期、店名、樓層。
- 暱稱被當成口頭禪（KaTsuO 的「喵」其實是在叫柔柔喵；雞蛋飛 的「糯糯」其實是成員名）。
- 群體用語被當成個人特徵（「484」寫在 3 個人身上、「何意味」2 人）。
- 改版留下的比較句（「並非／而非／不只」）、「。；」雙標點、同一人意思重複的條目（至少 8 人）。
- 兩位成員顯示名稱都是「DDLC」；③ 遺留的 Banana、Rie 描述內容是「無法分析」。

**待決問題（grill 暫停中，2026-09-28；每題附當時的建議）**
- **隱私**：建議不發布職業、居住地、宗教、財務（持股、薪資）、政治立場、健康、具體行程（日期＋地點）。做法：④ 的 prompt 加規則不記錄這些類別，⑤ 再用關鍵字當後備（④ 只重跑有新發言的人，舊版本裡的條目要靠 ⑤ 擋）。另建議把招牌梗的 spicy 閘門也套到精簡版（之前列為刻意沒處理，但性化引用已經進到 prompt）。
- **歸因錯誤**：建議兩個都做——④ 執行時附成員別名表，並加「別人的暱稱不算口頭禪」；⑤ 發布前跨人比對，同一個加引號的詞出現在 2 個人以上的描述裡，就當群體用語、全部不發（純規則，不經 LLM）。
- **③ 怎麼退場**（會改變既有定案的做法）：建議現在就把「跳過名單」移到送 LLM 之前（③ 今晚實際寫 0 人卻對 36 人跑約 12 分鐘 LLM；改完只替精簡版是空的人寫）。整個刪除的標準建議訂為「⑤ 連續 7 晚 failed=0，且抽查沒有新類型的嚴重問題」。刪之前要先決定三件事：新成員第一版描述從哪來、啟動補跑檢查改看什麼、手動萃取指令留不留。
- **人工校正**：建議做一個 JSON 設定檔，列「全域不發布的詞」和「某人不發布的詞」，⑤ 發布時跳過含這些詞的條目（`read_json` 會熱載入）；「改完立刻重發」的指令先不做，急的時候手動跑 ⑤。

**不反對就照做的預設**：⑤ 串接時修掉「。；」雙標點；④ prompt 加「每條都要能單獨讀懂，不寫跟舊版比較的句子」；同一人意思重複的條目在 ⑤ 用 embedding 相似度去重（之前列為刻意沒處理，但至少 8 人有這個問題）；兩位「DDLC」撞名時標籤加區分碼；回滾步驟寫成文件。⚠️ **需使用者明確同意才做**：刪除 ③ 留下的 Banana、Rie 兩份「無法分析」描述（先備份）。

**M7 之後待辦**：拿掉 ③（新成員第一版描述從哪來、補跑檢查改看什麼、手動萃取指令去留）；失敗的 run 隔天重跑；
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

## Telegram 漏收事件自動補掃（2026-08-02 已實作；2026-08-18 補上「中段缺口」盲區；2026-09-28 全域鎖改單則訊息鎖修相簿漏圖，待部署驗證）

<!-- @meta
id: telegram-catchup-sweep
type: STATE
status: confirmed
depends_on: telegram-multi-source
affects: telegram-relay
last_confirmed: 2026-09-28
-->

**症狀**：使用者回報「最新的 telegram 沒有轉發」。

**診斷（已查證，非推測）**：
1. **relay 端無問題** — `telegram_relay_delivery_state` 3119 筆、`last_polled_pk`=12494＝`max(telegram_messages.id)`，DB 內該送的全送掉了。
2. **斷點在 scraper** — Telegram 上已有 `Seele_WW_leak/9824`，但 DB 最大只到 **9823**（`2026-08-01 22:29:48+08`），之後 12 小時沒有任何新資料。
3. **不是斷線/卡死** — 對 `telegram_emoji_refetch` 發 NOTIFY 測試，scraper 秒回並成功即時抓回 9823；TCP 對 `91.108.56.199:443` 為 ESTABLISHED，session `update_state` 時間戳持續推進。
4. **根因＝Telethon 漏派 NewMessage 事件**（handler 完全沒被呼叫，連「略過轉發訊息」都沒印），而 [runner.py](src/telegram_scraper/runner.py) **只在啟動時掃一次歷史**，跑起來後 100% 只靠即時事件 → **漏掉就永久漏掉，除非重啟容器**。
5. **不是偶發** — 以 `created_at - message_date > 5min` 回推「靠重啟歷史掃描才補進來」的比例：7/25 **28/63**、7/26 **59/121**、7/20 4/9、7/22 4/17、7/24 3/13。過去都是剛好有重啟才把洞補起來。

**實作（本輪）**：
- [db.py](src/telegram_scraper/db.py)：新增 `get_max_message_id(telegram_chat_id)`，走既有 UNIQUE(chat_id, message_id) 索引取增量基準。
- [runner.py](src/telegram_scraper/runner.py)：新增 `_catch_up_channel` / `_catch_up_loop` / `_resolve_catchup_chat_id`（chat_id 快取）。以 `iter_messages(channel, reverse=True, offset_id=<DB 最大 message_id>, limit=200)` 增量重掃——已讀 Telethon 1.43.2 原始碼確認 reverse 模式下 `offset_id` 會 `+1`，即**從基準之後開始、不含基準本身**，且回傳為舊→新（PK 與時序一致）。
- **序列化鎖**：即時事件 / 補掃 / refetch 三條路徑共用一把 `process_lock`，避免同一則訊息並行處理造成重複下載媒體。**（2026-09-28 已改為單則訊息鎖，全域鎖造成相簿漏圖，見文末追加段）**
- **單輪上限 200 筆/頻道**：由舊往新掃，超出部分下一輪接著補，**不會留下永久空洞**；達上限會明確 log。
- **容錯**：單頻道拋錯（FloodWait 等）只 log 並續跑其他頻道，不拖垮迴圈；`run_until_disconnected` 結束時 cancel 補掃 task。
- [tg_config.py](src/telegram_scraper/tg_config.py)：`catchup_interval_min`（預設 **15** 分鐘）進 `TelegramConfig` 與 runtime snapshot，可從 `runtime_config.json` 熱調整；`<= 0` 為停用（迴圈保留，改回正值免重啟即恢復）。
- [handlers.py](src/telegram_scraper/handlers.py)：新增 `handle_catchup_message`（`log_prefix="CatchUp"`，**不**跳過自訂表情下載——補掃到的等同新訊息，表情要能對到 Discord App Emoji）；`_process_message` 加 `source_label`，**順修** History log 把 Gamedataleak 的訊息全標成 `source_channel=Seele_WW_leak` 的誤導性 bug（原本印 `config.source_channel`＝多來源清單第一個）。

**已驗證**：
- 4 檔 `py_compile` PASS。
- 容器內 stub 煙霧測試 **15 項全過**：offset_id/reverse/limit 參數正確、以 marked chat_id 查基準、每則都進 handler 且處理期間持有 lock、`source_label` 為實際頻道、無基準時**不**整頻道重掃、單頻道拋錯後迴圈續跑。
- `get_peer_id(Channel(id=2405953050))` == `-1002405953050`，與 DB `telegram_chat_id` 一致。
- 實 DB 驗證補掃基準：Seele=**9823**、Gamedataleak=**2669**（即重啟後首輪會補回 9824）。

**已 commit（`fbd2d3c`）。** `runtime_config.json` **刻意未改**（該檔執行中會被 `add_identifier_to_forward_whitelist` 自行寫入，屬受保護檔）；程式端預設 15 分鐘已生效，要調整再手動加 `"catchup_interval_min": <分鐘>`。

**下一步**：
1. `docker compose restart telegram-scraper`（bind-mount `./src/telegram_scraper` → `/app`，重啟即載入新 code；同時啟動歷史掃描會立刻補回 9824 → NOTIFY → relay 轉發）。
2. 觀察 log：`週期性補掃已啟動（每 15 分鐘增量重掃）`；日後漏事件時應出現 `[CatchUp] <頻道> 補回漏收訊息：基準 message_id=... 之後撈到 N 筆`。
3. 觀察一兩天，若 `[CatchUp]` 頻繁觸發，代表即時事件漏失率高，可考慮縮短間隔或深入追 Telethon 更新迴圈。

### 追加（2026-08-18）：補掃補不到「中段缺口」→ 指針左移

**症狀**：使用者回報「重啟服務之後又發一大堆早上 10-11 點的文章」，懷疑重複轉發。

**查證結論＝不是重複，是首次補發**：
- `telegram_relay_delivery_state` 全表**沒有任何 `message_pk` 出現 >1 次**；`telegram_messages` 有 UNIQUE(chat_id, message_id)，同一則不可能存成兩個 pk。
- 該批 8 則（Seele 10057~10060、GameData 2742/2743/2746/2756）`message_date` 為 **10:31~11:03**、`created_at` 全是 **17:24**（重啟當下才入庫）、`delivered_at` 17:25、送出次數皆 1。
- 早上 09:00~12:00 共 111 則，34 則無 delivery 記錄但**全部**帶 `grouped_id`（media group 成員由首則代發），「無法解釋的漏發」= 0。
- 附帶現象：pk 12798（msgid 2744）10:32 就入庫卻同樣 17:25 才發 —— 它是 media group 成員，**首則 2742 漏收導致整組卡住**，首則補回才一起放行。

**根因（2026-08-02 版補掃的設計盲區）**：`offset_id = max(message_id)` + `reverse=True` 只看得到**比 DB 最大 id 更新**的訊息。當漏的是中段（2742/2743/2746 漏、但 2745/2747 正常收到 → max_id 早已跳過去），那些洞永遠不在掃描範圍內，只能等**重啟時的全量歷史掃描**。本次即卡了 7 小時。

**修法＝把指針左移，其餘兩項是配套**（使用者拍板：改善既有流程，不另開補洞路徑）：
1. **指針左移**：`offset_id = max(last_id - CATCHUP_GAP_WINDOW, 0)`，`CATCHUP_GAP_WINDOW = 300`。中段的洞與 max_id 之後的新訊息在**同一次掃描**涵蓋，不需要第二條路徑。
2. **limit 跟著加大**：`limit = CATCHUP_GAP_WINDOW + CATCHUP_MAX_PER_CYCLE`（500）。`limit` 卡的是**撈回幾則**（`fetched`）而非收下幾則，額度會被視窗內已存在的訊息吃光 —— 沿用 200 的話掃描在 `window_start+200` 就截斷。
3. **id 過濾**：新增 [`db.get_existing_message_ids(chat_id, lo, hi)`](src/telegram_scraper/db.py)，掃描前**一次**撈出視窗內已入庫的 id 成 set，迴圈裡 `if msg.id in known_ids: continue`。不過濾的話視窗內約 290 則已存在訊息會各跑完整個 `_process_message`（含 forward 白名單判斷、可能打 `client.get_entity`）才在 upsert 時發現重複。刻意「一次撈 set」而非逐則查 DB：一輪 1 次查詢即可。

**成本**（實測缺號率：GameData 3.2%、Seele 10.9%，視窗內缺號 17~26 個）：Telegram API 8 → 24 次/小時（視窗 300 則 ÷ 每 request 100 則 = 3 次/輪/頻道）；DB 每輪每頻道多 1 次區間查詢（走 UNIQUE 索引）；媒體不重複下載（已存在者連 `_process_message` 都進不去）。

**已驗證**（容器內注入假 client/db，唯讀不碰 DB 與 Telegram，重現 8/18 早上真實缺口 2742/2743/2746）：
- `offset_id`=2455（左移 300）、`known_ids` 查詢區間 (2455, 2755)、`limit`=500 ✅
- 中段的洞 [2742, 2743, 2746] 全數補回 ✅；max_id 之後的新訊息 [2756~2760] 照收 ✅；已存在的 297 則一則都沒重跑 ✅
- **反向驗證**：把 limit 壓回 200 → 掃描在 2655 截斷，洞與新訊息**一則都收不到**（處理數 0）→ 證明 limit 加大是必要配套而非優化。
- `py_compile` PASS（runner.py / db.py）。

**限制**：視窗外的舊洞（> `max_id - 300`）仍只有重啟全量掃描補得到；要延長回溯就調大 `CATCHUP_GAP_WINDOW`，代價是每輪多撈同量 metadata。

**未 commit。下一步**：`docker compose restart telegram-scraper` → 觀察 `[CatchUp] <頻道> 補回漏收訊息：視窗 X~Y 撈到 N 筆、已存在略過 M 筆、收下 K 筆`。

### 追加（2026-09-28）：全域 `process_lock` 讓相簿漏圖 → 改單則訊息鎖

**症狀**：使用者回報 GameData #3223 相簿「後面一堆圖片漏發」——8 張只發出 1 張；同時段 #3213 8 張發 1 張、#3231 7 張發 6 張。

**機制（一句話）**：全域鎖把「同時到的相簿各張」變成逐張排隊，relay 的 0.5 秒到齊判斷等不到整組就先發，晚到的組員走「交由首則處理」被丟掉。

**查證（非推測）**：
- **加鎖原因**（`fbd2d3c` commit 訊息）：補掃上線後，即時事件 / 補掃 / refetch 可能同時處理**同一則**訊息 → 加鎖防重複下載。但實作成**一把全域鎖**，連「不同訊息」也一起序列化。
- **Telethon 預設並行派發**：1.43.2 `sequential_updates=False`，每個 update 各開一個 task（容器內已讀 `telethon/client/updates.py:284` 原始碼）→ 相簿各張本來同時處理；唯一讓它排隊的就是這把鎖。
- **時間點吻合**：相簿組員寫入 DB 的間隔，7/31 以前 p90 **0.03 秒**（7/31 兩張間隔 0.001 秒）；commit 當天 8/02 11:01 之後第一組相簿（18:07）起即變成逐張，9 月中位數 **0.76 秒**、p90 **2 秒**、最大 12 秒。
- **影響量**（bot log `media group 合併 ... media_count=N` 對照 DB 該組實際媒體數）：7 月 70 組中 9 組不足（21 張）；**8/02 起 191 組中 77 組不足（237 張）**；9/28 單日 40 組中 21 組（82 張）。

**修法**：新增 [message_lock.py](src/telegram_scraper/message_lock.py)（`KeyedLock` + `message_lock_key`），[runner.py](src/telegram_scraper/runner.py) 三條路徑改用 `message_locks.hold((chat_id, message_id))`：**同一則訊息仍互斥（保留原本加鎖的目的），不同訊息恢復並行**。key 取 Telethon `Message.chat_id`（marked id，容器內實測 = DB `telegram_chat_id` 格式 `-100…`），三條路徑拿到的都是 Message 物件，key 一致。無人持有的 key 即回收，dict 不會長大。

**已驗證**：容器內 `unittest discover` **534 測試全過**（新增 [test_telegram_message_lock.py](src/test/test_telegram_message_lock.py) 8 條：同 key 互斥、相簿 8 張可同時進入、例外／取消後不漏回收、跨頻道同 id 不撞 key）；**反向驗證**：把 `hold` 換成全域鎖 → 相簿測試逾時失敗。`py_compile`（scraper 容器 py3.12）PASS。

**relay 端同輪一起修（使用者拍板「一起修正」）**——加鎖前 7 月仍約 1 成相簿缺圖，relay 自己有三個洞：只數訊息列不管媒體列寫入沒、晚到組員走「交由首則處理」直接丟棄（重啟 reconcile 也一樣跳過 → 永久漏發）、已發送標記用的是合併**前**的組員清單（實送了卻沒標、沒送卻標了都有）。
**機制（一句話）**：不再「只有首則能發」，改成**哪個組員先到就由它收整組**，等到齊才發；發完還有沒送的，以「（補圖）」再發一則。改動全在 [telegram_relay_service.py](src/services/relay/telegram_relay_service.py)：
- **到齊判斷** `_wait_group_settled`：每個組員都有媒體列（`get_group_member_states`，`has_media=false` 視為就緒）**且** 3 秒內沒有新組員／新就緒；湊滿 10 則（Telegram 相簿上限）且都就緒就不等；上限 60 秒，逾時先發已就緒的。
- **同組同時只有一個收集者** `_process_group_member`：收集中到的組員只登記 `_dirty_groups` 就返回（不佔處理槽空等），收集者發完回頭複查；「檢查 dirty → 移出 active」之間無 await，不會有組員卡在空檔。
- **各頻道只發還沒送的** `_group_pending_for_channel`：組內已有人送過 → 標題加「（補圖）」；**補圖時效 12 小時**（`_GROUP_FOLLOWUP_MAX_AGE`，以該組首次送出時間算）——重啟時 reconcile 會把全部沒 delivery 記錄的組員（現約 460 筆、158 組舊相簿）重新排入，沒有時效會把舊缺圖一口氣倒進頻道。發之前先快篩，沒有該發的（或全過時效）就不等安靜期。
- 只標記**實際合併送出**的組員；重送模式（replay）不看 delivery_state、以 processed 集合防同輪重送。
- `render()` 加 `title_suffix` 參數；`get_grouped_message_pks` 移除（改用 `get_group_member_states` + `get_delivered_at`）。

**已驗證（relay）**：新增 [test_telegram_relay_media_group.py](src/test/test_telegram_relay_media_group.py) 11 條（逐則寫入整組一次送、媒體未寫入要等、收集中到的組員不阻塞不重送、發送中到的以補圖送、發完才到的補圖不丟、逾時先發其餘補圖、過時效不發且不空等、全送過直接結束、重送模式只送一次、非首則觸發保留說明文字、單則訊息不變）；**反向驗證**：同樣的測試套舊版 relay → 關鍵 3 條全失敗。全套 **545 測試全過**。
**坑**：relay 測試的 logger 會寫進正式 `logs/discord_bot.log`——第一次跑時用了真實 grouped_id/pk，log 在 **15:50:39~41** 留下幾行假的「media group 合併 grouped_id=14324643361830837 …」（含一行 pks=[13916…13923] media_count=8，**不是真的送出**）。已改用假 id；日後用 log 還原送出狀態時要排除這幾行（校正腳本以「合併後 60 秒內有 delivery 記錄」過濾）。

**今天漏的圖補發（使用者拍板「補圖片」）**：
- **做法**：不另寫發送腳本，走新版 relay 的正式路徑——重啟時 reconcile 排入未送組員 → 以「（補圖）」送出。前提是先把今天相簿的 delivery_state 校正成「實際送出」：以 bot log 合併紀錄為準（pks 裡媒體寫入最早的 `media_count` 則＝實送），**補記** 實送沒標的（否則會被當晚到組員重送）、**撤記** 標了沒送的（否則永遠不補）。
- **校正腳本**：scratchpad `fix_album_delivery_state.py`（`docker exec -i telegram-scraper python - [--apply] < …`；bot 停機時也能跑）。09-28 15:55 dry-run：39 組、補記 57 筆、撤記 9 筆、待補發 **87 張**、無法判定 0。
- **唯讀預演**（新版 relay + 真 DB + 校正計畫套在記憶體、發送換成記錄器）：reconcile 排入 460 筆 → **23 則補圖、共 87 張**，其餘 0 則送出（舊相簿全被時效擋下）。
- **15:57 已套用**（備份 scratchpad `delivery_state_backup_20260928_155656.sql`，4108 列 → 4156 列＝+57−9；套用後複跑＝23 組、0 筆待校正、87 張待補發）。
- **順序必須是**：停 bot → 備份 `telegram_relay_delivery_state` → `--apply` → 啟動 bot。舊版 bot 在跑時每來一組相簿就再產生不一致的標記，所以不能先套用再重啟。**需在 09-28 22:15 前啟動**（最早一組缺圖相簿首次送出於 10:15:47，超過 12 小時時效就不補）。

**已知殘留（未處理）**：
1. 並行恢復後，兩則**不同**訊息若同時帶同一個尚未下載的自訂表情，會同時寫同一個 `emoji_{doc_id}` 檔——8/02 以前本來就如此，機率低，未加鎖。
2. History 啟動掃描本來就沒上鎖，維持原狀。
3. 8/02~9/27 的舊缺圖（約 155 張）不補——超過補圖時效，使用者只要求補今天。
4. 補圖訊息的說明文字：組員多半沒有文字，補圖只有標題「來源（補圖）」與 footer `msg #… · db#…` 指向原相簿。

**部署與補發結果（09-28）**：scraper 15:56 重啟、bot 15:58 啟動；reconcile 排入 460 筆 → **23 則補圖、87 張全數送出**（log `followup=True`；使用者確認「補圖沒問題」）。其中 GameData #3198、#3201 是 146MB 影片，two-pass 壓縮到 99.9MB 花約 8 分鐘，16:06/16:07 才送出——壓縮期間佔住處理槽，屬既有行為。另注意 bot 容器啟動時會跑單元測試，log 裡 `grouped_id=990000000000001` 的合併／逾時紀錄都是測試。

**已 commit。下一步**：重啟後尚無新相簿進來，下一組相簿確認 bot log `media_count` 等於組員數、DB 組員 `created_at` 間隔回到 0.0x 秒。

**仍可能缺圖的情境（非本次 bug，未處理）**：① 相簿已送一部分、缺的部分超過 12 小時才進 DB（例如 scraper 停機半天）→ 依設計不補；② scraper 下載失敗 → 媒體沒進 DB，沒人會發（有媒體卻無媒體列：6~9 月每月 1~7 則，幾乎不在相簿裡）；③ 影片壓縮後仍超過 Discord 上限 → 略過該檔但照樣標記已送（log 歷來共 5 次 `附件壓縮失敗或仍超限`）；④ Discord 發送失敗 → 不標記，要等下次 bot 重啟 reconcile 才重試。

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
- 檢索核心：`src/llm/retrievers/context_retriever.py`
- Persona 卡片：`src/llm/persona/persona_card_builder.py`
- Prompt 組裝：`src/llm/prompt/prompt_builder.py`；/askai 除錯 log 組裝：`src/llm/logger_factory.py`
- Profile/Impression 寫入 RAG：
  - 服務層：`src/services/community/intro_profile_service.py`
  - pgvector 介接層：`src/llm/storage/member_profile_store.py`（原 `intro_rag_port.py`，`b80c509` 改名）
- Impression 審核：`src/services/community/impression_moderation_service.py`
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
- generation: `gemma4:31b`（2026-04-15 切換）
- embedding: `bge-m3:latest`
- moderation: `qwen2.5:7b`
- 特性：runtime 可熱更新
- timeout: 300 秒（2026-04-15 從 180 秒調高，因 gemma4:31b 帶 context 回應較慢）

**注意事項：**
- `gemma4:31b` 支援 `think: true/false`，API 傳遞方式與 CLI `--think` 一致
- 圖片支援 jpg/png/webp，**不支援 GIF**（Ollama 回傳 `image: unknown format`）
- 已合併兩個 system message 為一個（2026-04-15），避免部分模型只認最後一個 system message

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

### 待處理

**體驗 / 觀測：**
- [ ] `/personality_extract` 的「寫入 RAG」改為背景 task：按鈕按下後先立即回應，避免 interaction 長時間停在 loading（目前仍前景等完，已加進度訊息降低體感不安）
- [ ] 若背景寫入超時或 followup 失敗，規劃 fallback（DM 或至少補 log / 狀態查詢入口）
- [ ] 為 `save_personality_results()` / `index_auto_personality()` 補逐筆或批次成功 log 與耗時統計，判斷卡點在 embedding、delete、還是 pgvector insert
- [ ] `asker_profile.roles` 欄位目前為 `(未啟用)`，未來可填 Discord 身份組名稱 + 權限層級（admin/moderator/member）

**部署驗證（待重啟 + 跑一輪確認）：**
- [ ] 2026-05-18 智慧女性風格 + few-shot 範例效果（觀察：回應是否變短/留白變多、是否真的「點規律不點現象」、空話智者 / 毒舌分析師 failure mode 是否被擋掉、色色降級觸發是否更敏感）
- [ ] 2026-04-27 三輪 askai 重構完整效果（#XXXX 對齊、target_profile 區塊、prompt 整合後回答長度與陪聊感、自我否定卡片是否仍能被 LLM 正常引用）

**新議題（未開工）：**
- [ ] **/askai 指定 thread 查詢**：情境 A（人在 thread 內 `/askai`）已支援；情境 B（在他處指定 thread）不支援，因 slash command 無 thread 參數 + pgvector metadata 無 `thread_id` / `parent_id`。兩方案：Minimum 版（加 thread 參數 + retriever 吃 thread.history，≤3 處改動）/ 完整版（Minimum + chat_persistence 寫 thread_id + RAG 加 thread 過濾，需 migration）。AI 建議先 Minimum 版，使用者未選。
- [ ] **使用者指令記憶 `/remember`**：詳見 [使用者指令記憶專區](#使用者指令記憶-remember-未來工作)
- [ ] 觀察 /askai 執行時音樂機器人是否還會斷音；若仍斷，考慮 BM25/embedding 隔離到獨立 ThreadPoolExecutor（治標）或 ProcessPoolExecutor（治本但 IPC overhead 高）

### 設計決策備忘

**Persona Card 資料來源與合併：**

| profile_kind | 來源 | 更新方式 |
|---|---|---|
| `intro_profile` | 使用者 `/intro` | 手動 |
| `impression` | 群友 `/impression` | 手動 |
| `auto_personality` | LLM 批次萃取 | 每日自動覆蓋 |

卡片標題 alias 優先級：intro_profile > impression > auto_personality
卡片內容顯示：自介 → 印象 → AI觀察

**萃取 Pipeline 架構：**
```
每日 04:00 UTC+8
    ↓ pgvector SQL 撈最近 14 天聊天
    ↓ 按 author_id 分組（≥10 則才分析）
    ↓ 反查 display_name（guild member 優先 → DB alias fallback）
    ↓ 清理噪音（emoji 字典替換、移除 URL/mention）
    ↓ 每批 4 人送 qwen2.5:14b
    ↓ 寫入 auto_personality:{guild_id}:{user_id}（覆蓋式）
```

**手動人格萃取 UI / 寫入流程現況（2026-04-17 確認）：**
- `/personality_extract` 啟動訊息與「查看結果」按鈕為 ephemeral；結果分頁與「寫入 RAG / 捨棄」按鈕也為 ephemeral。
- 「寫入 RAG」按下後目前會先把原 ephemeral 訊息改成 `⏳ 正在寫入 RAG...`，再同步執行整個寫入流程；完成後才 followup 一則 `✅ 已寫入 RAG：X 筆`。
- 若改成背景 task，使用者偏好方案是：**額外發一筆新的 ephemeral** 當作「已開始寫入 / 完成通知」，而不是只 edit 原本那筆。
- 風險提醒：新的 ephemeral followup 仍受 interaction token / webhook 時效限制，不適合無上限超長任務；若要更穩，後續仍需保留 fallback 機制。

**涉及檔案（設計參考）：**

完整檔案清單見 `TODO-completed.md` 對應歸檔。重要入口：

| 檔案 | 角色 |
|---|---|
| `src/services/llm_service.py` | generate_reply（prompt bundle 組裝已移到 `src/llm/prompt/prompt_builder.py`） |
| `src/commands/llm_commands.py` | context 分離、asker_profile 組裝、撞名偵測 |
| `src/llm/persona/persona_card_builder.py` | 自然語言化、`person_id` 保留 |
| `src/llm/retrievers/context_retriever.py` | discord_context item（含 `display_name`）、vector index cache |
| `src/llm/storage/store_chat.py` | buffer 批次寫入、SafeOllamaEmbedding |
| `src/llm/persona/personality_extractor.py` | 人格萃取 pipeline |
| `src/llm/storage/member_profile_store.py`（原 `intro_rag_port.py`） | `index_auto_personality`、`_ainsert`、singleton |
| `src/settings/prompts/askai_system_prompt.txt` | 人設 prompt（規則）|
| `src/settings/prompts/persona_identity.txt` | 人設身份核心（琇紫） |
| `src/settings/prompts/persona_examples.txt` | few-shot 風格示範對照 |
| `src/settings/prompts/llm_context_safety_rules.json` | untrusted intro + asker_profile 白名單 |
| `src/sys_settings/llm_settings.py` | prompt 三檔路徑設定 |
| `src/commands/llm_commands.py:load_system_prompt` | 三檔拼接載入（identity → main → examples）|

---

## Reaction 統計與社群互動玩法

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

---

## Ambient 互動紀錄 + 正向學習（自我蒸餾 → 個性演化）

<!-- 2026-06-22 -->

### 目標
讓琇紫從「群眾對它插話的反應」學習，逐步長出**被這個群塑形的個性**——但 **prompt 不能無限增長**：靠「蒸餾成固定大小的風格、覆寫」，不是「堆 few-shot」。

### 已實作（Part A，已驗證；**反應捕捉待重啟生效**）
- **`ai_interactions` 表**（pgvector 那個 Postgres，普通 SQL、軟連結、無硬 FK）。每次「真的開口」的插話寫一筆：
  `directed / trigger_kind / trigger_author_id / trigger_message_id / trigger_text / context_snippet / reply_text / reply_message_id / trace_id`
  + 反應證據欄 `reaction_count / positive_reactions / negative_reactions`。
- **寫入**：`ambient_reply._record_ambient_interaction`（送出後 `asyncio.to_thread` 寫，best-effort）。
- **反應＝群眾的隱式標籤**：`on_raw_reaction_add/remove` → 若被按的是 bot 插話（`ai_interactions_store.is_tracked_reply` 記憶體集合命中）→ `note_reaction` 用既有 `reaction_classifier`（讀 `emoji_dictionary.txt`，認得自訂 emoji）分類：agree/laugh=正向、negative=負向 → 更新該筆。
- **日記讀**：`diary_reflection` 撈當天 `ai_interactions` 結構化餵入（自發/被問各幾次、當時在聊什麼、回了什麼、哪句有正向反應）。
- 檔案：`src/llm/storage/ai_interactions_store.py`(新)、`ambient_reply.py`、`ambient_diary.py`、`discord_bot.py`(on_ready 建表 + 反應 hook)。

### Phase 2 — 自我蒸餾學習（**計畫，未實作**）
核心：**蒸餾不堆疊**。定期把累積的正/負向插話歸納成一小段固定大小的「學到的風格」，**覆寫**不追加。
- **資料來源/標記**：`ai_interactions`；正向＝`positive_reactions>0 且 negative_reactions=0`、負向＝`negative_reactions>0` 或事後有人說「尬聊」。（之後可加更強訊號：被回話 / 被 echo。）
- **蒸餾 job**（複用排程範本，每 3~7 天一次）：撈近期正/負向插話 → LLM「歸納 3~6 條：你在這群講話最對味/最冷場的樣子（切入點、句式、梗的類型）」→ **與現有 learned_style 合併精煉**（累積、不重練）。
- **輸出**：寫進新檔 `settings/prompts/learned_style.txt`（**長度上限 ~500 字 / ≤6 條，覆寫**）；`_load_ambient_prompt` 多組這一層（identity + guardrails + **learned_style** + 插話行為）；mtime 自動生效。
- **不爆 prompt**：原始例子永不進 prompt，只有蒸餾後的原則進；固定大小覆寫。
- **長出個性**：profile 隨更多正向資料演化 → 風格偏向這群會獎勵的樣子（仍在 base 人格框架內）。
- **護欄**：learned_style 從屬於 guardrails/identity（只影響「怎麼講」、不碰安全紅線）；人類可讀可手改；某習慣不再得反應 → 下次蒸餾自然淡出（自我修正）。
- **對稱**：等同把現有 `personality_extractor`（蒸餾成員個性）指向 bot 自己。

### 節奏（已與 user 確認 2026-06-22）
1. **表情/反應蒐集先建立、先上線**（Part A ✅，待重啟）。
2. **先收集 1~2 週**，用日記觀察「這群到底會不會按反應」；若他們愛回話多過按讚 → 把「被回/被 echo」也納入標記。
3. **有訊號再建 Phase 2 蒸餾**（先有資料再學，別蒸餾空氣）。

### 涉及檔案（Phase 2 預估）
| 檔案 | 角色 |
|---|---|
| `src/settings/prompts/learned_style.txt`（新） | 蒸餾出的固定大小「學到的風格」 |
| `src/llm/self_distill.py`（新，暫名） | 撈 `ai_interactions` 正/負向 → LLM 蒸餾 → 覆寫 learned_style |
| `src/llm/ambient/ambient_reply.py` `_load_ambient_prompt` | 多組 learned_style 一層 |
| `src/discord_bot.py` | 蒸餾排程（每 3~7 天） |

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

> ⏸️ **本輪（2026-06-20）暫放旁邊。** 與新案 [AI 偶爾插話 / 閒聊（功能二）](#ai-偶爾插話--閒聊功能二規劃中) 切為**兩個獨立功能**：
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

## AI 偶爾插話 / 閒聊（功能二）（規劃中）

<!-- @meta
id: ambient-chat
type: TODO
status: draft
depends_on: [project-architecture, context-prompt-optimization]
affects: [ai-chat-channel-memory, ambient-natural-rework]
last_confirmed: 2026-08-09
-->

> **目標：** 在白名單的一般聊天頻道裡，AI（柔喵）**沒人叫也會偶爾冒一句**，讓群聊更活；被 **@ 或 reply 時一定回**。定位是「彩蛋式偶爾插話」，**不是**功能一那種「專屬頻道全程參與」。寧可少講講得巧，也不要每句都插變噪音。

### 與功能一（AI 的家）的分界

| | 功能一：AI 的家 | 功能二：偶爾插話（本案） |
|---|---|---|
| 概念 | 你「去找他聊天」的地方 | 他在群裡「偶爾冒泡」 |
| 觸發 | 進去講話**一定回** | 自發低機率 + **@/reply 必回** |
| 場景 | 一個專屬頻道 | 一般頻道（白名單，可多個） |
| 記憶 | 重度三層 + 道德守門 | 輕量情境記憶（檔1+檔2） |
| 狀態 | 暫放旁邊 | **本輪主線** |

### 模型與排隊（2026-06-20 定案的核心架構）

**兩顆模型、同時只一顆常駐**（Lemonade「切模型會卸載另一顆」是硬約束，使用者確認）：

| 角色 | 模型 | 服務 |
|---|---|---|
| 前景大模型（P0） | `Gemma-4-26B-A4B-it-GGUF`（既有，MoE 僅 ~4B 活躍） | `/askai`、功能一（AI 的家） |
| **背景小模型（常駐底，P1/P2）** | **`Gemma-4-12B-it-GGUF`（新增）** | 插話判斷＋生成、傾聽＋記憶 |

> 與既有 `moderation_model`(Qwen2.5-7B) / `personality_model`(Qwen3-14B) 同一個「角色專屬模型」慣例，加 `ambient_model` 即可（[llm_runtime_config.json](src/sys_settings/llm_runtime_config.json)）。選 12B dense 的理由是**佔 VRAM 小、load 快、適合常駐背景**（非運算更省——A4B 的 26B 反而活躍參數更少）。

**優先序佇列（擴充現有 `stream_exclusive` / askai queue）**：

| 序 | 工作 | 模型 | 能否觸發 swap |
|---|---|---|---|
| P0 | `/askai`、功能一 | 26B | ✅（前景值得） |
| P1 | 插話判斷＋生成 | 12B | ❌ 只用當下常駐者；P0 一來就讓位 |
| P2 | 傾聽＋記憶批次 | 12B | ❌ 閒置時才跑 |

**鐵則：只有 P0 觸發換模型。** 12B 為預設常駐背景腦（靠插話/記憶活動保溫）；`/askai` 來 → swap 26B 並守 keep_alive，**這段期間插話/傾聽暫停**（不為背景又 swap 回去）；`/askai` 閒置夠久 → 落回 12B。swap 一輩子只由 P0 驅動，不 ping-pong。

### 觸發設計（硬過濾前置 + 12B 判斷，零 swap）

因 12B 本來就常駐，由它即時判斷每則訊息**零 swap**（前面我擔心的「判斷害大模型反覆卸載」在此政策下不成立）：

1. **免費硬性過濾**：bot/自己、非白名單頻道、指令開頭、純連結、純附件、太短(<4字)或太長(>300字) → 連 12B 都不勞動。
2. **冷卻 + 上限**：距上次插話 < 90 秒、本小時已插 ≥ 6 次 → 跳過（維持「偶爾」手感）。
3. **12B 判斷**：過濾後交 12B 決定 **插話 / 只貼 reaction / 沉默(轉傾聽)**。
4. **@/reply 覆蓋**：被 @ 它或 reply 它 → **必回**，跳過冷卻（預設只在白名單頻道）。
5. **（備案減壓閥）** 頻道太熱、12B 每則判斷負載過高 → 在第 3 步前加機率抽樣，不每則都問。
6. 過關 → `asyncio.create_task` 背景生成，不阻塞 `on_message`。

### 生成（複用現有零件）

- 插話由**常駐的 12B** 生成（`LLMService.generate_reply()`，傳 `model=ambient_model`）。
- **system prompt = 共用人設身份（`persona_identity.txt`，琇紫，與 /askai 同一份）＋ 插話行為規則（`ambient_reply_prompt.txt`）**：插話與問答是同一個角色，只是換成「插話模式」（簡短、口語、允許 `[PASS]` 沉默）。可用 `AmbientChatSettings.use_shared_identity` 關閉疊加。**不含** askai 主規則與 few-shot 範例（保持輕量、避免問答框架）。
- `allowed_mentions=none` 不 ping 人；不回 bot 訊息（防回音迴圈）。

### 記憶（v1 = 檔1 + 檔2「情境記憶」；偏好事實走共享層）

**核心決策：記憶是跨功能共享的一層**——同一個 pgvector 記憶池，一個寫入器負責沉澱，兩功能都召回。**寫入由常駐的 12B 在「沒梗轉傾聽」時順手做**（判斷=傾聽=記憶寫入，同一顆模型同一條 pass）。

| 檔次 | 它會「記得」什麼 | 靠什麼 | v1 |
|---|---|---|---|
| 檔1 認得人 | 在跟誰講話、這人什麼調性 | `persona card`（已存在，直接讀） | ✅ |
| 檔2 記得聊過什麼 | 最近/相關講過的話，接得上舊話題 | `retrieve_discord_context` 召回 | ✅ |
| 檔3 記得人物偏好 | 「你愛吃鮭魚」這種原子事實 | 12B 傾聽 pass 抽 `preference_fact`（共享寫入器）→ 召回時讀 | ⏭️ Phase C |

### Phase 切分

#### A — 插話骨架（**已實作 2026-06-21，待 docker 驗證**）
- [x] [llm_runtime_config.json](src/sys_settings/llm_runtime_config.json) 加 `ambient_model: "Gemma-4-12B-it-GGUF"` + `model_load_options` ctx_size 8192；`LLMRuntimeConfig` 加 `ambient_model` 欄位 + `LLMService.resolve_ambient_model()`。
- [x] `channel_registry` 加 `register_channel("AI 插話頻道", text, "ambient_chat_channel_id", …)`（magenta）。
- [x] `llm_settings.py` 新增 `AmbientChatSettings`（min/max 字數、cooldown 90s、hourly_cap 6、askai_grace 90s、silence_sentinel `[PASS]`、history_limit 12、`judge_sampling_rate=1.0` 減壓閥預設關閉）。**插不插由 12B 判斷，不用機率**；「偶爾」感靠冷卻+上限（冷卻期內連判斷都不跑）。
- [x] `bot.ambient_tracker = {}`（[discord_bot.py](src/discord_bot.py)）。
- [x] 模型協調（取代「優先序佇列」的最小落地）：[lemonade_gate.py](src/llm/client/lemonade_gate.py) 加 `stream_busy()` + `note_foreground_activity()` / `foreground_recently_active(grace)`；/askai 在 `_handle_askai_request` 起點與 worker `finally` 兩處標 foreground → 背景插話於 grace 窗口內讓位。**注意：尚未做真正的優先序佇列**，只做「foreground 活躍時背景讓位 + 共用 `stream_exclusive` 序列化」；directed(@) 仍會在 /askai 窗口觸發 swap（罕見、可接受）。
- [x] 新檔 [src/llm/ambient/ambient_reply.py](src/llm/ambient/ambient_reply.py)：硬過濾 + 冷卻/上限 + foreground 讓位 + 機率 + @/reply 必回 + 12B 生成（`generate_reply(model=ambient_model)`，沉默 sentinel 不發送）。**Phase A 範圍調整**：(a) 判斷與生成**合為一次 12B 呼叫**（prompt 允許回 `[PASS]`＝沉默），未做獨立 judge；(b) **react 檔次延後**（Phase A 只有 回/沉默）；(c) **檔1 persona card 改到 Phase B**，Phase A 記憶＝近期 `channel.history` 短期脈絡（零 pgvector）。
- [x] [discord_bot.py](src/discord_bot.py) `on_message` 加 `asyncio.create_task(maybe_ambient_reply(bot, message))`。
- [x] 新 prompt [ambient_reply_prompt.txt](src/settings/prompts/ambient_reply_prompt.txt)（純「插話行為」規則、`[PASS]` 沉默）；**system 疊用共用身份 `persona_identity.txt`（琇紫）→ 插話與 /askai 同一角色**。注意：這是 bot 自己的「身份 prompt」；「認得別人是誰」的 per-user persona card 仍在 Phase B。
- **靜態檢查**：全檔 py_compile PASS；JSON valid；lemonade_gate 協調函式 standalone 測試 PASS（本機無 discord 套件，完整載入須在 docker）。
- **待 docker 驗證**：`docker compose restart discord-bot` → `/setch` 設「AI 插話頻道」→ 該頻道閒聊看是否偶爾插話、@ 必回、非白名單靜默、/askai 進行時讓位。
- **可調手感（config 起始值）**：base_probability、cooldown_seconds、hourly_cap、askai_grace_seconds。

#### B — 認得人（persona card 召回；檔1 提前到此）
- [x] 三項已實作（`ambient_reply._build_persona_context` 走 `retrieve_rag_context_sync`，`_PERSONA_CACHE` 依頻道短 TTL 快取）；原細項已歸檔（2026-09-28）。
- **驗收**：群裡有 persona card 的人講話，琇紫接話帶得出對方調性；沒卡的人也不會卡住（degrade 成只有對話脈絡）。
- **延後（非 v1 必要）**：`retrieve_discord_context` 泛化吃 channel 的 hybrid 長期對話召回——觸碰 /askai 核心、風險高，等 B 的 persona 召回不夠用再做。

#### C — 偏好事實 preference_fact（檔3：自我進化、全自動、自他分流）
> 政策（2026-06-21 定案）：**只記「本人講自己」的中性偏好；敏感(健康/感情/家庭/財務)一律自動丟、不存；他人評他人/紅線自動丟。多次提到才升等。全自動、零審核佇列。**

**共享接口（2026-06-21 建）**：[`MemoryService`](src/services/memory_service.py)（門面，單例）——任何功能只呼叫它、不碰底層：`recall / list_facts / extract / remember / observe / forget / format_recall`。底層委派 `intro_rag_port`(儲存) + `preference_extractor`(抽取/升等)。未來 /askai、功能一、/remember、管理面板都走這個。

- [x] **C-1 儲存層**：`PgVectorIntroRAGPort.index_preference_fact / list_preference_facts / delete_preference_fact`；`profile_kind="preference_fact"`，metadata：`{author_id, fact, fact_key, category, confidence, status, mention_count, first_seen, last_seen}`。doc_id 含 fact_key 雜湊 → 同事實 replace 不重複。**隔離已驗證**：persona 讀取器 SQL 白名單只撈 intro/auto/impression，preference_fact 不會混進 /askai/Phase B。
- [x] **C-2 抽取+守門**：[preference_extractor.py](src/llm/persona/preference_extractor.py) `extract_preferences`（12B、[守門 prompt](src/settings/prompts/preference_extractor_prompt.txt)：自他分流/敏感丟/紅線丟、輸出 JSON）+ `_parse_facts`（容錯）。
- [x] **C-2 corroboration**：`ingest_preferences`——confidence 濾（<0.6 丟）→ 批內去重 → 依作者讀既有 → 命中 `mention_count++`（≥2 升 trusted）否則新建 tentative。
- [x] **C-3 串接**：[ambient_memory.py](src/llm/ambient/ambient_memory.py)——`enqueue_for_memory`(插話頻道每則收緩衝) + `maybe_flush`(背景排程、**閒置才跑 12B**) + `recall_lines`(召回 trusted 注入 persona_context)；`ambient_reply` 與 `discord_bot` on_ready(每 180s 檢查) 已接。
- [ ] **C-4 自我進化迴圈**（閒置批次）：consolidation（合併重複、衝突取新記「以前X現在Y」）、decay（久未重提降權/封存）。**未做**。
- [ ] **C-4 隱私公告**：綁定插話頻道時自動置頂 + 改 channel topic。**未做**。
- [ ] **C-4 選配監督面板**（不擋流程）：查/改/刪/禁記；複用 `/personality_extract` UI 模式。**未做**（接口 `MemoryService.list_facts/forget` 已備好）。
- [ ] **觀測 / Debug 面板（使用者要求 2026-06-21，重要）**：使用者**不想用 CLI/log debug**，未來要一個 **Discord 面板** 能看：每次插話的**完整 prompt（含三層 context）**、決策狀態（reply/pass/error）、三層 context 數量（chat/persona/memory）、記憶 flush 狀態、某人記得的偏好。**取代** `ambient_prompt.txt` + grep。可與「記憶監督面板」合併成一個「AI 狀態/觀測面板」。**現況暫用**：`discord_bot.log` 的 `ambient 生成 …chat/persona/memory` 摘要 + [`/logs/ambient_prompt.txt`](src/llm/ambient/ambient_reply.py)（`AmbientChatSettings.debug_log`）；面板做好後轉成資料來源。
- **驗收**：本人講過愛吃鮭魚且被提 ≥2 次 → 之後相關話題自然帶出；敏感/他人/紅線輸入確認不入庫；衝突取新；久未提的淡出。

### 預設決策（還可改）

| 決策點 | 預設值 |
|---|---|
| 觸發場景 | 一般頻道白名單（可多個） |
| 模型 | 背景 `Gemma-4-12B-it-GGUF`（常駐底，判斷+插話+傾聽）；P0 才換 `Gemma-4-26B-A4B-it-GGUF` |
| 排隊 | 優先序佇列 P0>P1>P2；只有 P0 觸發 swap，背景永不 ping-pong |
| 插話判斷 | 12B 即時判（回/reaction/沉默）；前置硬過濾 + 冷卻；太熱才加機率減壓閥 |
| 冷卻 / 每小時上限 | 90 秒 / 6 次（起始值，待調手感） |
| @/reply 處理 | 必回，覆蓋冷卻；預設只在白名單頻道 |
| v1 記憶深度 | B＝認得人（persona card 召回）；C＝偏好事實 preference_fact（與 B 一起做） |
| 記憶範圍（防污染第一刀） | **只記「本人講自己」的中性偏好**；他人評他人/紅線自動丟 |
| 敏感自我揭露 | **直接丟、不存**（健康/感情/家庭/財務）；當下仍可由 channel.history 體貼回應，事後不留檔 |
| 升等（corroboration） | 首見 `tentative`不公開引用；不同時間 ≥2 次升 `trusted` 才召回；`/remember` 直接 trusted |
| 治理 | AI 自我進化（抽取→升等→消化→淡忘，全自動）；人類監督面板為**選配**、不擋流程 |
| 衝突 / 淡忘 | 衝突自動取新（記「以前X現在Y」）；久未重提降權/封存 |
| 連發/沉默 | prompt 允許回空＝沉默；冷卻避免洗版 |

### 風險與注意
- **回音迴圈**：一律排除 bot 訊息（含 `message.author.bot`），不只排除自己。
- **swap ping-pong**：背景(P1/P2)絕不為自己換模型；只有 P0 驅動 swap，且 `/askai` keep_alive 窗口內插話/傾聽暫停。若實測 12B 常駐底跟 `/askai` 使用頻率打架，退路是插話也改跑 26B（少一顆但回 swap）。
- **12B 連續判斷負載**：熱門頻道每則都過 12B 可能吃資源 → 用第 5 步機率減壓閥抽樣。
- **記憶污染**（檔3）：抽取道德守門 + confidence；功能二只讀，污染風險集中在共享寫入器治理。

### 涉及檔案（預估）

| 檔案 | 角色 | Phase |
|---|---|---|
| `src/sys_settings/llm_runtime_config.json` | 加 `ambient_model` + load options | A |
| `src/sys_settings/llm_settings.py` | `LLMRuntimeConfig` 加 `ambient_model` 欄位 + `AmbientChatSettings` | A |
| `src/settings/channel_registry.py` | 加「AI 插話頻道」綁定 | A |
| `src/services/llm_service.py` | 優先序佇列 + 背景不 swap 規則 + ambient_model 解析 | A |
| `src/llm/ambient/ambient_reply.py`（新） | 硬過濾 + 12B 判斷 + 背景生成 | A |
| `src/discord_bot.py` | `on_message` 加 ambient 分支 | A |
| `src/settings/prompts/ambient_reply_prompt.txt`（新） | 輕量插話人設 | A |
| `src/llm/retrievers/context_retriever.py` | `retrieve_discord_context` 泛化吃 channel | B |
| `src/llm/persona/preference_extractor.py`（與功能一共用） | 12B 傾聽 → 偏好事實抽取（共享層） | C |

---

### 自然插話重構（2026-08-09，**已實作・待部署驗證**）

<!-- @meta
id: ambient-natural-rework
type: DECISION
status: confirmed
depends_on: [ambient-chat]
last_confirmed: 2026-08-09
-->

**起點**：使用者觀察「一偵測到發言就馬上運算」+「聊天室常有多組人聊不同主題，機器人不知該加入哪個」。
**目標函數（使用者拍板）**：**談話自然、適當插話、有人性**；GPU 節省只是副作用，不是目標。

#### 實測基準（本輪從 log / DB 量到，後續調整以此為準）

| 指標 | 值 | 來源 |
|---|---|---|
| 自發插話「trace 建立 → 送出」中位 | **120.8s**（p10 95.2 / p90 164.7 / max 901.3） | `discord_bot.log` n=3540 |
| 被 @ 同上中位 | 111.3s | n=367 |
| PASS 率 | **15%**（146 reply / 26 pass） | `ambient_prompt.txt.1` |
| `ai_interactions` 總筆數 | 5602（directed 894） | pgvector |
| 有正向反應 / 負向反應 | 343（6.1%） / **13（0.2%）** | 同上 |

#### 診斷（六個「不自然」的來源）

1. **節奏由計時器決定，不由對話內容決定**：冷卻 300s 一到期，下一則就喚起生成，而 PASS 率僅 15% → 等於「每 5 分鐘準時報到講一句」。
2. **120s 後裸送、無指向**（[ambient_reply.py:1032](src/llm/ambient/ambient_reply.py#L1032) `channel.send`）→ 多人多主題頻道必然像亂入。**這才是「不知道加入哪個主題」的真正成因**：它選的時候那條線還在，講出來時已經沒了。
3. 第一則就開跑 → 上下文半截；`max_passes_per_burst=3` → 一段 burst 最壞燒 6 分鐘。
4. **A↔B 對線**這種零成本可判的，現在花 120s 讓模型判（prompt 第一關 gate #3）。
5. **講完就跑**：除非被 @，否則不理會別人對它的回應 → 沒有來回感。
6. 等鎖排隊不計入 `pass_timeout_seconds`（[ambient_reply.py:988](src/llm/ambient/ambient_reply.py#L988) 註解已載明）→ 實測 max 901s。

#### 四層方案（優先序＝對「自然」的貢獻，非改動大小）

| 層 | 內容 | 關鍵決策 |
|---|---|---|
| **L3 選線 + reply 錨定**（第一優先） | chat_context 每行給 `#N`；prompt 輸出契約第一行 `#N`＝我在接第幾則；自發送出改 `message.reply(#N)` | **不走 code 端聚類**（embedding 分群易錯）；讓模型自己選線。120s 延遲下這是唯一能讓「慢」變合理的東西——引用著回話的人，晚兩分鐘正常 |
| **L4-b 接續自己的話** | 它剛講完、下一則在接它的話 → 視為半 directed，允許馬上接續 | 現在完全沒有；最能製造「有在對話」的感覺 |
| **L2 不搶話** | debounce 靜默 10~15s **且** 無人 typing（`on_typing`）；directed 不等 | `Intents.default()` 已含 typing，**不必改 intents**。typing 是加分訊號，收不到就退化成純時間 debounce。**不做** typing indicator 顯示（2 分鐘太假） |
| **L1 鉤子閘** | 決定「值不值得花那 120s」 | 見下節。鉤子只管喚不喚醒模型，**開不開口仍由模型 `[PASS]` 決定** |

順帶必做（理由是自然，不是省 GPU）：`max_passes_per_burst` **3 → 1**（第二輪要再等 2 分鐘，講出來跟現場脫節）。

**使用者否決、不做（2026-08-09）**：
- ~~等鎖上限 120s 超過放棄~~ → **不做**。GPU 本來就慢，放棄等於 `/askai` 忙的時段插話永遠不會發生；寧可晚講也不要不講。
- ~~L4-a 新鮮度檢查（那條線被別人接完就丟棄）~~ → **不做**。使用者判斷「被接完也可以插話，沒差」；真人也常在別人答完後補一句自己的看法，且有 reply 錨定後遲到的傷害已經很小，丟棄反而是白燒 120s 卻零產出。L4 只保留 **b（接續自己的話）**。

**完整保留、本次不動的既有機制**（曾在 to-be 流程圖被省略，非刪除）：foreground 讓位（`stream_busy` / `foreground_recently_active`，防 model swap ping-pong）、每小時上限、`judge_sampling_rate` 減壓閥、降溫硬閘 `_has_chime_backoff_signal`（尬聊/閉嘴 → 收手）、三層 context 組裝（persona / memory / signature tags / callback / style_refs / 圖片 / replied_to）、`[PASS]` 判斷、`_write_ambient_debug`、`record_interaction`、directed 優先答與 pending 吸收、reply 失敗 fallback `channel.send`。

#### L1 鉤子的判斷方法（**不用 LLM**）

寫死結構演算法（主）+ 極少量 regex + k-NN 檢索（軟），權重由歷史資料迴歸學出來。

- **結構鉤子（零 I/O，只看 `author_id`/`created_at`/`reference_id`）**：正＝懸空問句（有人問、30s+ 沒人回）、獨白（最近 3 則同一人）、冷場後新起頭（隔 >10 分鐘）、熱聊後停頓（近 10 則跨度 <5min 且最後一則已過 60s）；**負＝A↔B 對線（近 6 則只有 2 人且平均間隔 <45s）→ 直接否決**。
- **regex**：只放最高把握兩三條（沒 @ 但叫名字、明確徵詢）。刻意克制，避免膨脹成關鍵詞地獄。
- **k-NN（非 LLM 推理）**：`get_text_embedding(近 3 則)` → `ai_interactions` 最近鄰 20 筆 → 「過去語意相近情境下插話被接的比率」當一個特徵。基礎設施（embedding 欄位 + hnsw + [fetch_similar_positive](src/llm/storage/ai_interactions_store.py#L289)）已存在。
- **組合**：負鉤子否決 → `sigmoid(w·features) >= threshold`。**threshold 是唯一旋鈕**（調高＝話少）。
- **權重來源**：logistic regression，樣本＝5602 筆，特徵 <10 個。**係數可讀**＝看得出它為什麼開口，可定期重訓。

**學習標籤換掉**：不用 reaction（負向僅 13 筆，「什麼時候該閉嘴」學不出來），改用「**插話後 5 分鐘內有沒有人接話/回它**」——真人插話成功的定義本來就是話被接下去。此標籤可從 `ai_interactions`(`reply_message_id`+`channel_id`+`ts`) 配合 chat 歷史庫**回溯計算 5602 筆全量**，不必等新資料。

**已知統計限制**：5602 筆全是「已插話」樣本、無反例 → 學到的是「已想插話的情況下什麼形狀會被接」（ranking），不是「該不該插話」（causal）。可接受，但**門檻值必須上線後觀察調整，不能直接從迴歸結果讀出**。

#### 自循環 feedback 盤點（2026-08-09）

| 迴路 | 狀態 | 防護 |
|---|---|---|
| **回音迴圈**（回 bot／自己） | 既有，**不動** | 入口 `message.author.bot` 一律排除（[ambient_reply.py:644](src/llm/ambient/ambient_reply.py#L644)）；chat_history 裡自己的行標「(你自己)」 |
| **style_refs 風格自我模仿**（插話→reaction→embedding→召回當靈感） | 既有，**不動** | 已有距離地板 + 抽樣 + `_RECENT_STYLE_REFS` 近期壓制；決策是「召回真句子不重寫」以免蒸笨 |
| **AI 日記** | 既有，不構成迴路 | v1 定位「純表達、不改行為」 |
| **★鉤子權重學習迴路**（本輪新引入，**最需注意**） | 新增 | 見下 |
| **★L4-b 接續迴路**（本輪新引入） | 新增 | 見下 |

**鉤子權重學習迴路的風險**：鉤子用「插話後有沒有人接」訓練 → 鉤子決定何時插話 → **只有鉤子放行的時機才會產生新樣本** → 新樣本再訓練鉤子。等於 exposure bias 自我強化：一旦鉤子偏好「懸空問句」，其他時機永遠沒機會被驗證，策略窄化成單調的一種開口方式。這也是前述 selection bias 的升級版——上線後 bias 會自己滾大。

**防護＝ε-greedy 探索**：保留一小比例（`hook_explore_rate`，起步 ~10%）**無視鉤子分數強制放行**，專門收集「鉤子不看好的時機」樣本。這批探索樣本正是迴歸訓練缺的反例，讓模型有機會發現新的好時機。探索樣本在 `ai_interactions` 標記（加欄位或記在 `trace_id`），訓練時可分層。

**L4-b 接續迴路的風險**：它講 → 有人回 → 它接 → 對方再回 → 它再接……理論上無限。**防護**：同一串接續次數上限（`followup_max_chain`，建議 2）、接續一樣吃每小時上限、且接續對象必須是**非 bot 的真人訊息**。

#### 新增設定（`AmbientChatSettings`）

`quiet_seconds`(10~15) / `typing_grace_seconds`(12) / `quiet_max_wait_seconds`(60) / `quiet_directed_seconds`(0) / `hook_threshold`(上線調) / `hook_knn_*` / `hook_explore_rate`(~0.1) / `followup_window_seconds`(L4-b) / `followup_max_chain`(2) / `max_passes_per_burst`(3→**1**) / `cooldown_seconds`(300→**180**)

**冷卻 300 → 180s（使用者拍板 2026-08-09）**：撤掉等鎖上限與新鮮度丟棄後，節奏完全由冷卻決定，而 300s 會把鉤子閘架空（冷卻期內連鉤子都不看）。**物理下限約 120s**——生成一次 120s、一小時最多 30 次，冷卻低於生成時間會讓隊列越排越長。取 180s＝鉤子有發揮空間、又留安全邊際。**話多話少的主旋鈕改為 `hook_threshold`**，冷卻退為防洗版的安全網。

#### 涉及檔案（本重構）

| 檔案 | 改動 |
|---|---|
| `src/llm/ambient/ambient_reply.py` | debounce 迴圈、鉤子閘接入、`#N` 解析、reply 錨定送出、新鮮度檢查、L4-b |
| `src/llm/ambient/ambient_hooks.py`（新） | 結構鉤子 + regex + k-NN + 迴歸打分 |
| `src/llm/preprocess/chat_line.py` | `#N` 從「僅被回覆過的行」改為每行都給（[chat_line.py:107](src/llm/preprocess/chat_line.py#L107)） |
| `src/settings/prompts/ambient_reply_prompt.txt` | 輸出契約加 `#N` 選線；「分不清接誰 → PASS」 |
| `src/discord_bot.py` | 新增 `on_typing` handler |
| `src/sys_settings/llm_settings.py` | 上表設定項 |
| 離線分析腳本（新） | 回溯標記 5602 筆 + 交叉比對形狀 + 訓迴歸 |

#### 實作紀錄（2026-08-09，使用者「全部實做」）

**六項改動全部落地**（未 commit）：debounce＋typing、鉤子閘、每行 `#N`、選線＋reply 錨定、
L4-b 接續、`max_passes` 3→1（另 `cooldown` 300→180）。

前幾輪的未定案一併用建議值定案（都是可熱調的設定，上線後照實際狀況調）：
`#N` **每行都給**（編號只算實際成行的訊息、跳過的空訊息不佔號，所以不會跳號）、
`quiet_seconds=15`、`hook_threshold=0.5`、`hook_explore_rate=0.1`。

**實作中發現並修掉的缺陷**：L4-b 借用 directed 路徑會**連 foreground 讓位、降溫硬閘、每小時
上限一起繞過**——被 @ 有 must-reply 的免死金牌是因為使用者主動找它，但接續是它自己起的頭，
不該享有同等待遇（會破壞防 model swap ping-pong 的保護，也會在群裡已喊停時還一路接下去）。
修法：`_run_one_ambient_pass` 多收 `followup` 旗標，三種來源走不同閘門組合；`_note_sent`
加 `cooldown=False` 讓接續計入每小時額度但不吃冷卻。

**改動檔案**：
| 檔案 | 內容 |
|---|---|
| `src/llm/ambient/ambient_hooks.py`（新） | 結構鉤子 + regex + k-NN + sigmoid 計分 + ε-greedy；失敗一律 fall-open（交給模型 `[PASS]` 把關，不讓鉤子壞掉就整個功能啞掉） |
| `src/llm/ambient/ambient_reply.py` | `note_typing` / `_wait_for_quiet` / `_is_followup_to_bot` / `_parse_line_choice` / `_passes_content_gate`；入口加靜默期與 followup 分派；pass 接鉤子閘、reply 錨定送出 |
| `src/llm/preprocess/chat_line.py` | `_thread_render` 每行給編號 + 回 `{編號: 訊息}`；`fetch_recent_lines` 加 `thread_map` out-param（不改回傳簽章＝不動既有 caller） |
| `src/llm/storage/ai_interactions_store.py` | 加三欄（見下）；`mark_got_reply()`；`fetch_reply_rate_stats()` k-NN |
| `src/settings/prompts/ambient_reply_prompt.txt` | 編號說明改「每行都有」；輸出契約加「第一行寫 `#N`」＋範例 |
| `src/discord_bot.py` | `on_typing` handler |
| `src/sys_settings/llm_settings.py` | 上節設定項 |
| `src/test/test_ambient_natural.py`（新） | 35 個 hermetic 測試 |

**驗證**：py_compile 全綠；容器內 `unittest discover` **146 測試全過**（既有 111 + 新 35）。
新測試涵蓋每行編號/thread_map/↩指向/空訊息不佔號、`#N` 解析四種寫法、內容閘 burst 語意、
五種結構鉤子 + A↔B 否決、ε-greedy、鉤子 fall-open。
注意：`AmbientChatSettings` 是 pydantic **frozen**，測試要覆寫設定得用 `model_copy(update=...)`
換掉 module 的 `_SETTINGS`，不能直接賦值。

#### 資料庫異動（`ai_interactions` 一張表，只加欄不改既有資料）

| 欄位 | 型別 | 語意 |
|---|---|---|
| `got_reply` | `BOOLEAN` **nullable** | 它這句話有沒有換到別人接話。NULL＝未觀測（上線前的 5602 筆、以及被 @ 的）／FALSE＝已觀測沒人接／TRUE＝有人接 |
| `explore_sample` | `BOOLEAN NOT NULL DEFAULT FALSE` | ε-greedy 探索放行的樣本（鉤子分數沒過但硬放行）→ 訓練分層用 |
| `followup` | `BOOLEAN NOT NULL DEFAULT FALSE` | 這筆是「有人接它 → 它再回」 |

**命名的坑（2026-08-09 改名）**：原本叫 `followed_up`／`explore`。
`followed_up` 字面像「這筆已被跟進處理」，而且跟 code 裡的 `followup`（**它**接續自己的話）
主詞相反、必踩；`explore` 太抽象。改成 `got_reply`／`explore_sample`。
另補 `followup` 欄——接續在 code 裡借用 directed 路徑，不獨立記一欄的話 **DB 分不出「被 @」
和「接續」**。三種來源現在是：`directed=T`（被 @）／`followup=T`（接續）／兩者皆 F（自發）。

`got_reply` 刻意 nullable：若給 `DEFAULT FALSE`，舊資料會被當成「全部都沒人接」毒化 k-NN 統計；
順帶讓 `mark_got_reply` 的 `WHERE ... AND got_reply IS NOT NULL` 天然碰不到舊資料。
k-NN 只吃**純自發**（`directed = FALSE AND followup = FALSE`）——被 @ 與接續的情境「被接」機率
天生偏高，混進去會灌高分數。

**沒有**新索引 / 改型別 / UPDATE 既有列；其他表未動。

**改名的實際執行（2026-08-09）**：討論期間 bot 曾重啟過，已用舊名 `followed_up`／`explore`
建好欄位並寫入少量真實資料 → 改名改用 **`ALTER TABLE ... RENAME COLUMN`** 就地改（metadata
操作、不搬列、資料完整保留），而非「建新欄 + UPDATE 搬 + DROP 舊欄」。已執行完成，驗證
`total=5631 / got_reply 已觀測 4 筆（TRUE 2）/ explore_sample 1 筆` 全數帶過來。
`followup` 欄同時以 `ADD COLUMN IF NOT EXISTS` 補上。重啟時 `ensure_table` 的三行 ALTER
會因為欄位已存在而全部跳過（idempotent）。

**注意（一次性）**：rename 之後、重啟之前，記憶體裡跑的舊 code 其 INSERT 仍用舊欄名 →
`record_interaction` 會寫入失敗（best-effort，只記 warning，插話本身照常送出）。空窗期損失
僅為「幾筆插話紀錄」，重啟即恢復。

**部署**：`docker compose restart discord-bot`。`ensure_table()` 在 on_ready 跑 idempotent ALTER
自動補這三欄，不必手動改 DB。prompt 檔走 mtime 快取，但 code 改動要重啟。

#### 提高發話頻率（2026-08-09，使用者要求「發話頻率高一點」）

**真正的根因不是門檻設太高，是鉤子的時間門檻跟 debounce 打架**：`dangling_question` 要求
「問句後 > 30s」、`lull_after_burst` 要求「最後一則後 > 60s」，但靜默期只等 `quiet_seconds`
(15s) 就評估 → **熱聊後停頓永遠不可能命中**。實測 log 全是 `feats={}` `p=0.23` 就是這個。
把鉤子接到 debounce 後面時漏掉了疊加效應；「等一下、對方可能還在打字」本來就已經由 typing
偵測負責，鉤子不需要再等一次。

**改法**：兩個門檻改成跟 `quiet_seconds` 連動（`quiet = max(5.0, _SETTINGS.quiet_seconds)`），
另把 `hook_threshold` 0.5→**0.4**、`hook_explore_rate` 0.1→**0.15**。
0.4 的意義：讓「冷場後新起頭」「熱聊後停頓」（分數 0.45）單獨命中就能開口，完全沒鉤子的
平淡對話仍然閉嘴（0.23）。已加迴歸測試 `test_time_gates_track_quiet_seconds` 防止門檻再被寫死。

**還想更多話的階梯**（依序試，每次只動一項才看得出效果）：
`hook_threshold` 0.4→0.35 ／ `cooldown_seconds` 180→150（**下限約 120**＝一次生成的時間，
低於它隊列只會越排越長）／ `hourly_cap` 20→30 ／ `hook_explore_rate` →0.2。

#### 上線後實測發現（2026-08-09 重啟，台北 11:28）

**功能全數驗證通過**：`thr=0.40` 生效；`PASS p=0.45 [lull_after_burst]` ← 修好的鉤子第一次
命中（改門檻前永遠不可能）；`VETO:two_person_volley` 實際擋掉對線；`EXPLORE` 放行；
`kind=spontaneous 錨定=#21` ← 模型遵守 `#N` 契約、reply 錨定生效；`kind=followup` +
`接續 chain=1/2` ← L4-b 整條鏈通；DB 三欄寫入正確（`directed=f, followup=t` 分得開）。

**實測抓到的 bug（已修）—— `mark_got_reply` 的 race**：`id 5666` 在 11:36:40 插話、11:36:41
就被接話，但 `got_reply` 仍是 `f`；對照 `id 5667`（間隔 13 秒）就正確標成 `t`。原因是送出後
`await _record_ambient_interaction()` 要先算 embedding 才 INSERT，而 `mark_got_reply` 1 秒後
就跑 → UPDATE 影響 0 列。**rowcount=0 不是例外，靜默丟失、連 log 都沒有**。修法：加重試
（4 次 × 2.5s，跑在 to_thread 裡不阻塞 loop）+ 檢查 rowcount + 全數失敗時 log.info。

**實測抓到的設計失誤（已修）—— 人數不該當判準**：重建容器後 12 分鐘內 7 次判定，
**6 次是 `VETO:two_person_volley`**（兩人 + 間隔 <45s → 直接否決）。小頻道常態就是兩三人在聊，
等於全時間閉嘴。根因：把 prompt 第一關 gate #3 降級成純結構規則時，**把它的放行例外一起丟掉了**
——原文是「判準是**話題封不封閉**，不是有沒有兩個人」，那是語意問題，結構規則模仿不來，
硬擋只會把「兩人在聊一件全場都看得到的事」一起殺掉；而且它是硬否決、繞過模型判斷。

**使用者拍板：「不需要限定幾個人聊」→ 整條負鉤子拿掉**（連降級成扣分的折衷版也不留）。
現在 `_W` **全部是正權重、沒有任何負鉤子**，唯一的 veto 只剩 `no_messages`。
分工變成：**鉤子只管「時機」（值不值得花那 ~120s 去想），「該不該插進這段對話」是語意問題，
完整留給模型的第一關。** 加迴歸測試 `test_participant_count_is_never_a_gate`（兩人密集／兩人慢聊／
三人 三種都必須不否決）。

順帶把 `lull_after_burst` 的「有在聊」跨度 **300s → 600s**——原本的 5 分鐘是連珠炮節奏，
小頻道每分鐘一兩則、10 則就超過 5 分鐘，等於這鉤子只服務最吵的頻道。

**再一個盲點（已修）—— 鉤子全是「找空檔」導向，快節奏熱聊反而靜音**：使用者指出「快節奏對話
也希望機器人能參與」。原本五個正鉤子（懸空問句／獨白／冷場／停頓）**全在找對話空隙**，熱聊
進行中一個都不命中；而且 debounce 在熱聊時等不到「靜默 15s 且沒人打字」，只能靠
`quiet_max_wait_seconds`(60s) 兜底放行，那時「已停下來」也不成立 → **熱聊必然 SKIP**。
真人剛好相反，熱聊時插話才最自然。**新增 `active_chat`**（近 8 則擠在 3 分鐘內）權重 **1.2**。
與 `lull_after_burst` 不衝突：那條看「已停下來」、這條看「節奏快」，同時成立＝剛熱聊完的空檔，
疊加加分（0.73）是對的。測試 `test_active_chat_while_conversation_is_hot` / `test_sparse_chat_is_not_active`。

**現行鉤子分數對照**（threshold 0.4，任一鉤子命中即可開口）：

| 鉤子 | 權重 | 單獨命中分數 |
|---|---|---|
| 叫名字（沒 @） | 2.5 | 0.79 |
| 懸空問句 | 2.2 | 0.73 |
| 明確徵詢 | 1.3 | 0.52 |
| 獨白 / **對話正熱** | 1.2 | 0.50 |
| 冷場後起頭 / 聊完停頓 | 1.0 | 0.45 |
| （什麼都沒命中） | — | 0.23 ✗ |

**靜默期依對話節奏切換（使用者定調：「慢的時候等人講完才說話，熱絡的時候只看前面的就可以講」）**：
原本 debounce 對兩種節奏用同一套規則，熱聊時「靜默 15s 且沒人打字」根本等不到，只能被
`max_wait` 硬拖 60 秒，而那時對話又前進了一段。何況熱聊插話本來就不需要空檔——真人也是直接接話。

| 節奏 | 判定 | 等法 |
|---|---|---|
| 慢 | 最近 5 則跨度 ≥ `hot_window_seconds`(120s) | 等 `quiet_seconds`(15s) **且**沒人在打字 |
| 熱 | 最近 5 則落在 120s 內 | 只等 `hot_quiet_seconds`(3s)，**忽略 typing** |

熱聊忽略 typing 是刻意的：熱聊時本來就一直有人在打字，等它等於不等。留 3 秒只是避免切在
某人連發的中間。實作＝`_is_hot_conversation()` 讀 `state["msg_times"]`（deque(12)，每則訊息
記一個 monotonic 時刻）。熱聊總延遲從「60s + 生成」降到「3s + 生成」≈ 2 分鐘。
測試 `test_hot_conversation_uses_short_wait_and_ignores_typing` /
`test_slow_conversation_still_waits_for_typing`。

**`docker compose restart` 不套用 compose 變更（既有問題，非本次造成）**：啟動 gate 的 log 印的是
`--- running startup tests ---`，但 docker-compose.yaml 寫的是 `--- running startup tests (auto-discover) ---`
→ 容器跑的是**建立當時的舊 command**（手動測試列表，23 個）。從 2026-07-09 至今每次啟動都是
`Ran 23 tests`，期間新增過測試檔（7/25、8/9）數字卻沒動。**程式碼本身是 bind mount 所以一直
是最新的**，只有 gate 沒生效。要修：`docker compose up -d discord-bot`（重建容器）而非 restart。

#### 清理與資料庫維護（2026-08-09，全實作後掃描）

**移除 `judge_sampling_rate`（純機率減壓閥）**：`random.random() > rate` 就跳過評估——**隨機丟棄
會丟掉好時機、留下爛時機**，它對「這一刻值不值得插話」一無所知。鉤子閘做同一件事但有判斷依據，
完全取代之；兩者並存還會讓調校時分不清是哪個閥在作用（而且 `hook_explore_rate` 也是隨機、
方向相反）。預設 1.0 本來就不作用 → 移除零風險。**要降載請調 `hook_threshold`，別再加機率閥。**

**資料庫維護（已執行）**：
1. `UPDATE ai_interactions SET got_reply=TRUE WHERE id=5666` —— 補回被上述 race 吃掉的標籤。
2. 新增 **partial index**：
   ```sql
   CREATE INDEX idx_ai_interactions_embedding_observed
     ON ai_interactions USING hnsw (embedding vector_cosine_ops)
     WHERE got_reply IS NOT NULL AND directed = FALSE AND followup = FALSE;
   ```
   原因：`fetch_reply_rate_stats` 的 WHERE 只符合個位數列，但既有 hnsw 索引涵蓋全部 5600+ 列。
   hnsw 是**近似**搜尋，掃描時把不符條件的 post-filter 掉 → 很可能掃到 `ef_search` 上限仍湊不滿
   LIMIT，症狀是「明明有語意相近的樣本卻撈不到」。partial index 只索引真正會被查的列。
   現在建成本最低（資料少），且隨 `got_reply` 累積越來越有價值。

**掃描結論**：無孤兒 code（所有函式都有呼叫點）；DB 完整性正常（embedding 100% 覆蓋、
`reply_message_id` 無空值、無 directed/got_reply 矛盾）。`HookDecision.score` 原本只寫不讀 →
改印進 debug log（`s=+0.00 p=0.50`，調權重時 raw score 比 sigmoid 後直觀）。

**Log rotate 不需另做**：`hook_debug` / `callback_debug` / `style_refs_debug` 都走
`logging.getLogger("discord_bot")` → `discord_bot.log`，已吃到 [logger_config.py](src/utils/logger_config.py#L45)
的 `RotatingFileHandler`（**20MB × 20 份**）；`_write_ambient_debug` 走
[logger_factory.py](src/llm/logger_factory.py#L38)（5MB × 3）。**沒有重複造輪子的必要。**

#### 「幾乎每個人的話都在回」（2026-08-09 實測回報）→ 修 L4-b 判準

**先量再改**：一小時內 15 次插話，來源分布 **followup 9 / spontaneous 5 / directed 1**。
鉤子閘那側其實正常（PASS 5、EXPLORE 3、SKIP 2、VETO 1）——**主因是接續，不是鉤子**。
接續不經鉤子閘、不吃冷卻，chain 上限 2 → 每次自發插話後還能再連兩次。

**根因是判準太寬**：原本只要「它發言後的第一則真人訊息 + window 內」就算接續，但**那則訊息
未必是在回它**——它插完話、群裡繼續聊自己的，第一則就被當成「有人接我」，於是又講一句。

**修法（三道判準，缺一不可）**：
1. `followup_armed`——只認發言後第一則，用完即熄（原有）。
2. window：`followup_window_seconds` **180 → 45 → 90**（45 實測太緊：修正後 51 分鐘內 5 次
   自發插話、接續一次都沒觸發。真人看到回覆要讀、要決定回不回、還要打字，何況它講的是兩分鐘前
   的話題。**收斂該靠下面第 3 條的對象判準，不是靠把時間壓短**）。
3. **★發話者必須是它剛才回的那個人**（新增，最關鍵）。送出時記
   `state["last_anchor_author_id"]`：自發＝它 reply 錨定那則的作者、被 @/接續＝跟它說話的人。
   `followup_max_chain` 順帶 **2 → 1**（一來一回就好，別纏著同一個人連講三輪）。

迴歸測試 `test_someone_else_talking_is_not_a_followup`。

**如果還是嫌多，下一格**（一次只動一項才看得出效果）：`hook_explore_rate` 0.15→0.1 →
`hook_threshold` 0.4→0.45 → `cooldown_seconds` 180→240。

#### 「沒人聊天時不用硬回」（2026-08-09 使用者回報）

**先量再改**（132 次真實評估，用「同一秒多筆＝測試」濾掉 63 筆測試污染的 log）：

| 判定 | 次數 | | 鉤子命中 | 次數 |
|---|---|---|---|---|
| SKIP | 48 | | 無任何特徵 | 96 |
| VETO | 43（舊版 two_person，已移除） | | `lull_after_burst` | 16 |
| PASS | 35 | | `active_chat` | 11 |
| EXPLORE | 6 | | `monologue` | 9 |
| | | | `dangling_question` | 6 |
| | | | **`cold_start`** | **1** |

**順帶澄清一個假警報**：先前兩次看到 explore 比例 38%/60%（設定 15%）疑似有 bug，
濾掉測試 log 後真實比例是 **11.1%**（6/54）——正常。**統計 log 時必須排除測試產生的行**
（`test_strong_hook_passes` 會同時命中 dangling/monologue/named/solicit 四個，
`test_explore_forces_pass` 會產生一筆無特徵 EXPLORE）。

**兩個修正**：
1. **移除 `cold_start`**（「冷場 >10 分鐘後有人開口就接」）——語意上正是「沒人聊天時硬回」，
   而且 132 次評估只命中 1 次，移除無痛。測試改成
   `test_long_silence_then_one_message_is_not_a_hook`（死寂後冒一句，**不該有任何鉤子命中**）。
2. **ε-greedy 探索加活躍度前提**（`_channel_has_life`）：近 `explore_min_messages`(5) 則要落在
   `explore_activity_window_seconds`(900s) 內才探索。原本探索完全不管有沒有人在，
   「無特徵卻被探索放行」正是使用者感受到的來源；何況沒人在時探索也**學不到東西**
   （標籤必然是「沒人接」）。測試 `test_explore_requires_the_channel_to_have_people`。

修正後，安靜頻道基本上只在 **有人問了沒人回 / 有人叫它 / 明確徵詢** 時才開口。

#### C：把鉤子量到的事實注入 prompt（2026-08-09 實作）

**問題**：使用者問「這（判斷有沒有人想要回應）應該用 prompt 做嗎？模型有時候會誤判」。

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

**真正的誤判解方**：鉤子已經算好的事實**完全沒告訴模型**，模型得自己從一堆 `[HH:MM]`
裡推導誰回了誰、隔多久——**那正是它最容易算錯的地方**。所以把事實卸給它。

**模組化切法（使用者要求維持模組化，三選一後拍板）**：
- **資料**（動態、每次不同）→ 只能在 bundle 層：`llm.prompt.prompt_builder.build_prompt_bundle`（原 `llm_service._build_prompt_bundle`）新增
  `situation_signals` 參數與 `<situation_signals>` 區塊 + 一句中性 header。/askai 不傳就不出現
  （與 `style_refs` 同模式）。
- **使用規則**（靜態、要能熱改）→ 放 `ambient_reply_prompt.txt`。**理由是「誰在用」**：
  `recalled_context`/`style_refs` 是 askai+ambient 共用 → 說明放共用的 prompt 組裝（`llm/prompt/prompt_builder.py`）合理；
  `situation_signals` **只有插話用** → 放插話專屬的行為檔才符合模組邊界。不另開新檔（粒度太細）。

**訊號契約**：自然語言、**只陳述事實、不下結論、絕不含分數**。給分數或「建議你接話」
會把模型變成橡皮圖章，判斷力就廢了。實際輸出長這樣：
```
・米拉#1111 連續講了 3 則都沒有人接話（最後一則：剛剛）。
・阿華#3333 問了一句（3 分鐘前），到現在沒有人回應。
・最近幾則是 阿明#1001 和 阿華#1000 兩個人在來回，節奏很快。
```
第三條是**負面事實**——當初 `two_person_volley` 的翻案：錯的是 code 拿它硬擋，
陳述事實交給模型判斷「封不封閉」則完全正確，還省下它自己數作者/算間隔。

**實作**：`_structural_features` 加 `obs` out-param（收集誰/多久/幾則，不改回傳簽章）；
`describe_signals(obs)` 產生描述；`HookDecision.signals` 帶出；`ambient_reply` 傳給
`generate_reply`；prompt 檔新增 `★ <situation_signals> 怎麼用` 四條（明示「不是叫你開口的指示」、
獨白可能是想找人聊也可能是自言自語不想被打擾、要看內容再決定）。
測試 5 個，含 **`test_signals_never_leak_scores_or_advice`** 釘住「不得出現建議/分數」的契約。

#### prompt 內人名對照：裸 mention 修補 + 錨點撞號警報（2026-08-09）

**使用者的問題**：「prompt 內可不可以對照？因為人物也都有可能改名。」

**釐清出的核心**：**對照依據是 `#XXXX`（user_id 後四碼），不是名字。** 改名不會動到它，
所以各區塊的名字**允許不同**——實測 persona card 用自填別名 `「柔喵, 阿喵#4635」`、
chat_history 用 Discord 顯示名 `❤️柔柔喵❤️-時渺#4635`，靠同一個 `#4635` 就串得起來。
`name_with_anchor` 當初的設計是對的。

**討論掉的替代方案**：使用者提議「prompt 直接用 ID + 每天維護一張對照表」。不採用，因為
①12B 比對 19 位數字容易看錯，4 碼好認得多 ②token 成本高（每行都帶）③要「看到 ID→查表→
得名字」兩跳，小模型易掉 ④`guild.get_member()` 已經是**即時**的對照表（`intents.members=True`，
member cache 常駐），改名當下就更新，比每天同步的表更即時、且零維護。

**唯一被證實的破口＝裸 mention**：`<@436506192047636490>` 沒有任何錨點，模型只看到一串數字。
實測 **chat_history 53%（10/19）、recalled_context 29%（5/17）** 的區塊含有它
（[emoji_text_utils.py:8](src/llm/preprocess/emoji_text_utils.py#L8) 的註解早就寫明「不動 mention」，一直沒人補）。

**修法**（`chat_line.resolve_user_mentions`，接在 `semantic_message_text` 管線裡 →
chat_history / recalled_context / 日記 / askai **一次全部受益**）：
`msg.mentions`（discord.py 已解析，含已離開伺服器的 User）→ guild member cache → 純錨點。
全程零 API、零 DB，`"<@" not in text` 有 fast path。
**名字查不到也保留錨點**（`某人#6490`）——因為錨點才是對照依據，模型看到別行的 `克羅#6490`
一樣對得上。實例：`那是 <@436506192047636490>` → `那是 克羅#6490`。

**錨點撞號警報**（`_check_anchor_collision`）：兩人 user_id 後四碼相同時 `#XXXX` 會指向兩個人，
而且無聲無息。實測 **78 位發言者目前 0 撞號**，但機率隨群成長上升（約 100 人 39%、150 人 67%
會出現至少一組）→ 加 log warning，同一組只警告一次。
**真撞到才處理**：加長到 5 碼會讓 persona card 文字裡已存的 4 碼對不上，要一併重建。

測試 10 個（mention 解析 7、撞號 3），總數 178。

#### 動作描述氾濫 + 色色尺度放寬（2026-08-15）

**動作氾濫**：`ambient_model` 換 `Qwen3.8-27B` 後幾乎每則都用 `*尾尖輕輕一掃*` 起手
（實測 08-09~14 舊模型 2/319，08-15 新模型 4/11 且連四則，連「介紹一下鳴潮」也加）。
**根因不是模型壞掉**：prompt 有四處寫「可以用動作」、零處寫「什麼時候不該用」。舊模型指令
跟得鬆等於沒看見，新模型跟得緊就把「允許」讀成「預設」。
→ **通則：換模型時，prompt 裡所有「沒寫界線的允許」都會被重新詮釋一次。**

**改法**：規則進 `persona_guardrails.txt`【動作描述】（預設不寫 → 只有「對方先做指向你的肢體
互動／挑逗」或「對方低潮需要無聲陪伴」可用 → 一則一個、上則用過這則不用）；examples 補範例 15。

**單一來源原則（使用者當場糾正，已定案）**：初版在其餘三處都加「——見 guardrails【動作描述】」，
太冗長。**規則只寫 guardrails 一份，其他檔案只把原本的「鼓勵」拿掉，不重述也不指路**——
guardrails 本來就跟它們組在同一個 system prompt 裡，指路等於對著同一份文件說「請見同一份文件」。

**色色尺度**：原本「露骨的器官、體液、性行為過程」整包在【紅線】。使用者拍板放寬器官 → 移出
紅線、另立【色色尺度（分寸，不是紅線）】：器官可直接講／指名，但不寫成色情敘事（性行為過程
逐步描寫、體液細節仍不寫）。**紅線原封不動**（未成年、非合意、真實公眾人物、不主動把在場成員
當性對象、降級觸發）。ambient / askai 兩份 prompt 同步改口徑，避免互相打架。

#### 新聞檢索修復（2026-08-15，已實作）

**現象**：問「今天有什麼新聞」只回 1 則。模型沒問題，是檢索層。

**真因①：我們自己送的 `time_range=day` 讓 news 引擎回 0 筆**（q=台積電）：

| 引擎 | 不設 | week | day |
| --- | --- | --- | --- |
| bing news | 10 | 10 | **0** |
| duckduckgo news | 30 | **0** | **0** |

機制（已讀 SearXNG 2026.8.14 原始碼）：bing news 宣告支援 day，但 Bing 對 `qft=interval="4"`
回**空 body** → `bing_news.py:85` 拋 lxml ParserError；duckduckgo news 用的 `duckduckgo_extra`
**整份沒宣告 `time_range_support`**（預設 False）→ `processors/abstract.py:264` 把它**整個跳過**。
受害的是三條 news+day 路由（今日新聞 / 台股 / 美股+加密幣）。general+day 不受影響，照留。

**真因②：news 引擎比對標題字面，餵問句會回 0 筆或「填充垃圾」**（「比特幣現在多少」回 4 筆
慈濟／日本豪雨／韓國女孩）。剝成關鍵字再搜，10 題以「前 5 筆有幾筆真的提到主題」計分：
**剝後 7 勝 3 平 0 敗**（台積電 0→5、美股 0→5、長榮 0→4）。剝完沒主題就換錨字「台灣 新聞」。
（使用者判讀「n=1 也沒比較差」正確 → 評分標準從**筆數**改成**相關筆數**。）

**真因③：既有 general fallback 門檻是 `not results`**，救不到「只吐 1 筆」——這是看到 1 則的直接原因。

**已實作**：① 三條 news 路由 day→week（`_ROUTE_RULES` 上方留 ⚠ 註解）② `focus_news_query()`
③ `fallback_min_results=3`，fallback 改成**合併**不取代 ④ news 路由只送 engines 不送 categories
（同送取聯集會把壞引擎叫來陪跑；實測 0.68s→0.16s、結果一樣）。

**驗收**：四句端到端各 5 筆相關（改前 1／0／0／4 筆全錯）。測試 185 全綠，含結構釘樁
`test_no_news_rule_uses_day` 掃整張路由表。

**已知殘留**：
- **引擎總體檢**（2026-08-15，每個引擎中文查 3 次，全 0 再補測英文 3 次；結果完全一致無 flaky）：

  | 引擎 | 中文×3 | 英文×3 | 判定 |
  | --- | --- | --- | --- |
  | duckduckgo / duckduckgo news | 10 / 30 | — | ✅（news 版帶 time_range 會被跳過） |
  | bing / bing news | 7 / 10 | — | ✅ 主力 |
  | reuters | 0 | 20 | ✅ 英文站，**不是壞掉**（先前誤判） |
  | wikinews | 5 | — | ⚠️ 有回但只有簡中舊文 |
  | google / google news / startpage / startpage news | 0 | 0 | ❌ CAPTCHA（google 通用版是靜默 0 筆） |
  | brave / brave.news | 0 | 0 | ❌ 429 限流 |
  | yahoo news | 0 | 0 | ❌ ALPN（見下），無解 |
  | qwant news | 0 | 0 | ❌ SearXNG parser bug `qwant.py:222` |

  處置：① `searxng/settings.yml` 那 8 個加 `disabled: true`（該檔 uid 977 所有，須使用者自行套用 +
  重啟 searxng）② **`default_engines` / `news_engines` 也要同步砍**——因為明確指定 `engines=` 會
  **繞過** disabled（`webadapter.parse_generic` 只有 category 路徑才過濾），只改 settings.yml 沒用。
  現值：`default_engines="bing,duckduckgo"`、`news_engines="bing news,duckduckgo news,reuters"`。

- **google / google news 的真正死因（都不是被封 IP，也不是 CAPTCHA）**：我們的出口是 HiNet 高雄
  浮動住宅 IP，用 curl／httpx 直接打 `google.com/search` 與 `news.google.com` **都是 HTTP 200**。
  - **google（通用）**：Google 回 200 但內容是 **JS 重導向殼**（頁面只有 3 個 `<a>`、0 個 `data-ved`，
    正文是「如果系統沒有在數秒鐘後將您重新導向…」）。SearXNG 的 xpath 命中 0，而它的 CAPTCHA 判定
    要求「<2000 bytes 且含 /sorry/」，這頁 92KB 又不含 → 不算錯誤 → **安靜回 0 筆**。
  - **google news**：`engine_traits.json` **根本沒有 zh-TW 的 ceid 條目**（只有 zh-HK / zh-CN），
    fallback 後算出 `hl=zh-Hant-HK` 這種無效值 → Google News 回 **302 導去 CONSENT 對話框**
    （SearXNG 官方文件自己就警告 hl 沒設對會被導到 CONSENT）→ 而 `detect_google_sorry` 有一條
    `if resp.status_code == 302: raise CaptchaException` → **誤判成 CAPTCHA**、停權 3600 秒。
    實測 `hl=zh-Hant-TW / zh-Hant-HK / zh-Hans-CN` 全 302，`hl=zh-TW / en-US` 都 200 →
    **所有中文語系都中招，只有 en 能用**。（parser 那個 issue #5852 已於 2026-03 由 PR #5984 修掉，
    我們這版有修好的 xpath，不是同一件事。）
  - 結論：不改 SearXNG 原始碼就救不回中文的 Google 系。業界通例也是放棄 Google 改用還能用的引擎。

  因為 news 路由用 `time_range=week`，duckduckgo news 每次都被跳過 → **實際只有 bing news 在跑**。
  想要兩引擎備援就得拿掉 time_range（35 筆 vs 10 筆，代價是可能混進較舊的新聞）。

- **yahoo news 為什麼救不回來**（容器內同一支 Python 交錯測 6 輪，穩定重現）：
  不送 ALPN → 6/6 成功 200；ALPN=`[h2, http/1.1]` → 6/6 BadStatusLine（＝SearXNG log 的
  「server has disconnected」）；ALPN=`[http/1.1]` → 6/6 HTTP 500。
  而 httpx **一定會送 ALPN**（`http2=True` 送 h2+1.1、`False` 送 1.1），所以
  **`enable_http2: false` 也救不了**。排除項：不是 IP（容器與 host 出口 IP 同為一個）、
  不是 UA（六種 SearXNG UA 用 curl 都 200）、不是 header、不是 parser（xpath 對得上現行 HTML）。
  唯一解是改 SearXNG 原始碼建立不帶 ALPN 的 SSLContext → 要自建 image
  （`/usr/local/searxng/searx` 不是掛載的，只有 `/etc/searxng` 是）→ 不划算，建議停用。
- `focus_news_query` 的單字雜訊（有／到／說／講）會誤傷專名（「有線電視」→「線電視」）；不收
  則殘渣毒化查詢（相關數 4→0）。權衡後收下，踩到再拆例外。
- **停權（Suspended）是 SearXNG 本地計時器，重啟只把它歸零、對方的封鎖沒變 → 重啟不是修復**。
  要分辨「本地停權」還是「真的壞掉」，讀 `unresponsive_engines` 前綴就夠：`Suspended: X` ＝
  這次沒發請求；`X` ＝ 發了、對方回錯。**不需要重啟**。
- RSS 方案已否決：查詢改寫就拿得到當日頭條，不必新增依賴。
- **「本地新聞也改走英文來源 + 模型翻譯」已否決（2026-08-15，使用者拍板）**：起點是想救 google news，
  但實測 ① google news 就算語系正確也是 0 筆——Google 又改版把 `<a target="_blank">` 往下包一層，
  SearXNG 用的是直接子節點 `./a[...]`（改成 `.//a` 應可修，可回報上游）② 更關鍵的是，英文來源回的是
  「外媒視角的台灣」（預算案／印尼海軍演習／AI 經濟預測），不是群友問「今天有什麼新聞」想聽的
  （雨彈／貓咪博覽會／總統開嗆）。**這是覆蓋角度差異，翻譯補不了。**
  結論：國際題材（`_TOPIC_FINANCE_INTL`）維持 lang=en + 模型翻譯（本來就在跑，靠 bing news + reuters）；
  本地題材維持中文來源。google 系維持停用。

#### 待觀察（上線後才調得準）

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

#### 已作廢的中間結論（避免重複討論）

- 「debounce 純 5 秒」→ 打字不是講話，改為**靜默 + typing 雙條件**。
- 「以省 GPU 排優先序」→ 使用者拍板目標是自然，該排序作廢。
- 「(A) trigger 往回找 vs (B) 內容閘看整段 burst」→ 有了選線機制後 trigger 是哪則不再關鍵，**(B) 定案**。
- 「用 reaction 當學習標籤」→ 負向樣本僅 13 筆，改用「有沒有被接話」。

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
