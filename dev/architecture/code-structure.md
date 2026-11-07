# 程式結構整理

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

> 現況、待決與待做以交接檔為準：[程式結構整理](../../AI_HANDOFF_AND_TODO.md#程式結構整理)。
> 這裡是歷史。上半部是整理過的重點；「原文」是當時的紀錄，提到的檔名、函式、狀態可能已經改了。原文提到的 `TODO-completed.md` 是 2026-11-07 以前的單一歸檔檔，內容都拆到 `dev/` 了，從 [dev/README.md](../README.md) 找。

## 一頁看懂

這個主題管 `src/` 的資料夾怎麼分：哪些程式放 `llm/`、哪些放 `services/`，檔名要不要改，以及搬檔時會踩到什麼。

- **09-29 起因**：使用者覺得程式很亂。盤點 `src/` 約 5.66 萬行，痛點是一檔多功能、`discord_bot.py` 876 行什麼都塞、命名、`llm/` 分類。第一版草案另起 `core/`＋依領域分，被使用者否決，改成沿用現有架構、只修放錯和過大的地方。
- **09-29 定義**：`services/` 是服務，`llm_service.py` 留在那裡；`llm/` 是 LLM 相關技術（組裝、優化、橋接、RAG、MCP），插話、日記、人格萃取這些 AI 功能也在裡面。檔名只改會誤導的，討論過的三個最後都不改。
- **09-29 `llm/` 重組**：依角色分成 `client`、`preprocess`、`prompt`、`storage`、`retrievers`、`ambient`、`persona` 七個子資料夾，一次搬完；先加 import 守衛，prompt 組裝 49,152 組搬家前後逐字相同；15:28 重啟上線（`97d7595`）。
- **09-29～30 點名**：服務層在函式裡反過來 import 指令層拿按鈕，改成指令層把建立按鈕的函式交進去，循環消失（`9b0b916`）。
- **09-30 `services/` 分群**：分 `relay/`、`events/`、`community/`，`notify_server`、`state_db` 留頂層，`get_shared_state_db` 搬進 `state_db.py`；16:38 重啟上線。重建 image 時清查 52 個套件升級都不會弄壞，最後 dockerfile 不鎖版本、`constraints.txt` 只當紀錄。

**歸檔時（10-02）的狀態**

- [x] `llm/` 依角色分七個子資料夾，09-29 上線（`97d7595`）
- [x] 點名服務層不再 import 指令層（`9b0b916`）
- [x] `services/` 分三群、`get_shared_state_db` 搬進 `state_db.py`，09-30 上線（`5e10611`、`2b31828`）
- [x] 刪 FB／IT 輪詢死碼，加資料檔位置與 import 解析兩個守衛
- [ ] P2：把一檔多功能的指令檔拆開，還沒定案
- [ ] P3 `discord_bot.py` 瘦身暫停；N3 拆 `utils/utils.py` 延後
- [ ] N1 的命名慣例還沒寫進 `AGENTS.md`

最新狀況看交接檔。

## 時間線

| 日期 | 發生什麼 | 結果 |
|---|---|---|
| 09-29 | 使用者覺得程式很亂，唯讀盤點 | `src/` 約 5.66 萬行；列出一檔多功能、`discord_bot.py` 876 行、用程式檔位置找資料的搬檔地雷 |
| 09-29 | 架構草案 v1（另起 `core/`＋依領域分） | 使用者否決，改成 v2：沿用現有架構、最小修改 |
| 09-29 | v2 的 P1～P5 | P1（`llm_service` 搬進 `llm/`）否決；`llm/` 定義為 LLM 相關技術；P3 改成入口仍由 `discord_bot.py` 管 |
| 09-29 | 命名討論 N1～N4 | 只改會誤導的；`forum_monitor`、`test_commands`、`prompt_builder` 都不改；N3 延後 |
| 09-29 | `llm/` 子資料夾討論 L1～L4 | AI 功能留在 `llm/`；使用者推翻「不做 `llm/` 重組」，核可依角色分子資料夾、一次搬完 |
| 09-29 | 15:26 套用 `llm/` 重組、15:28 重啟 | 啟動 gate 637 項全過，重啟後沒有 ERROR |
| 09-29 | 刪死碼、加資料檔位置測試 | 刪 FB／IT 輪詢迴圈等 32 行；`test_data_file_paths.py` 釘住 6 個路徑；643 項全過 |
| 09-29 | 搜尋與 MCP 殼放哪（L4 重新討論） | 搜尋放 `services/search/`，MCP 殼放 `llm/mcp_server.py`，網頁搜尋留在 `llm/retrievers/web/` |
| 09-29 | 完整相依檢查 | 394 條專案 import 逐條執行成功；循環相依前後相同，沒有新增 |
| 09-29 | 第一個 commit、點名改寫 | `97d7595`（77 個檔）；點名改由指令層交按鈕，先補測試再改，648 項全過 |
| 09-30 | 02:10 重啟 | 點名新程式啟動；00:00 日記第一次在新路徑發布成功 |
| 09-30 | `services/` 分群討論與工作副本 | S5-1～S5-4 照建議；41 個檔的 patch，648 項全過 |
| 09-30 | 重建 image 的套件版本清查 | 52 個版本改變，隔離環境實測都不會弄壞，也不用改程式 |
| 09-30 | 13:09 用新 image 重建容器；16:17 套用 patch、16:38 重啟 | gate 652 項全過；commit `5e10611`、`2b31828`、`f7d4a14`、`f6e4830`；dockerfile 改回不鎖版本 |
| 10-02 | 盤點剩下的題目 | P2 未決、P3 暫停、N3 延後；N1 的命名慣例還沒寫進 `AGENTS.md` |

## 定案與理由

| 決定 | 為什麼 |
|---|---|
| 沿用現有架構，只修放錯和過大的地方；不另起 `core/`＋依領域分 | `llm/` 本來就是 AI 領域，草案把它拆成兩處；社群功能本來就是 Discord 服務，草案把它和 Discord 共用元件拆開 |
| `llm_service.py` 留在 `services/`（P1 否決） | `services/` 就是服務，`llm_service.py` 是 LLM 服務 |
| 插話、日記、人格萃取、persona agent 這些 AI 功能留在 `llm/`（L1） | 搬走牽動最大，也沒有更合適的地方 |
| `llm/` 依角色分子資料夾，一次搬完，搬前先加 import 守衛（L2a、L2b） | 使用者要依「LLM 會做的事」分；守衛會把漏改的延遲 import 擋在啟動 gate |
| 真正的 prompt 組裝搬到 `llm/prompt/prompt_builder.py`；`build_askai_prompt_log` 併進 `logger_factory.py`、不從 `llm/__init__` 轉出（L3） | 名實相符；從 `llm/__init__` 轉出會讓 import `llm` 多載入 `utils.logger_config`（載入就套用 log 設定），scripts 與 MCP 行程都會多這個副作用 |
| 檔名只改會誤導的＋既有正名表；不一致的只給新檔訂慣例（N1） | 延續「只改騙人的名字、不為好看搬家」 |
| `forum_monitor.py`、`test_commands.py`、`prompt_builder.py` 都不改名（N2） | `forum_monitor` 本來就是監控聊天室的 cog，交易是後來加的；`test_commands` 意思沒錯；`prompt_builder` 名字對、是內容放錯 |
| 正名表的四個在 `llm/` 搬家時一起改，`lemonade_gate` 先不改 | `lemonade_gate` 等它真的管 GPU 資源再改 |
| ComfyUI 另開 `src/imagegen/`，不塞進 `llm/` | 避免 `llm/` 變成「AI 相關雜物間」 |
| 搜尋放 `services/search/`，MCP 殼放 `llm/mcp_server.py`，網頁搜尋留在 `llm/retrievers/web/` | 搜尋也給不經 LLM 的指令用，不算 LLM 技術；MCP 是給 LLM 客戶端的協定，屬於橋接；網頁搜尋裡有 /askai 專用的判斷與格式化。不叫 `llm/mcp/` 是因為 `from llm.mcp import …` 跟 `from mcp import …` 容易混淆 |
| 刪掉 FB、IT 的輪詢迴圈，只靠 scraper 推送 | 沒有任何呼叫處；使用者核可不留輪詢備援 |
| 用程式檔位置找資料的 6 個檔不改寫法，只加測試釘住位置 | v2 架構下這 6 個檔不會搬；以後誰搬了，啟動 gate 會擋下，不會默默開空 DB 把舊文重發 |
| 點名按鈕由指令層交給服務層（`response_view_factory`），服務層不 import 指令層 | 服務層原本知道按鈕長什麼樣、放在哪個檔，違反「services 做事、commands 管 Discord 介面」；循環 import 也跟著消失 |
| `services/` 分 `relay/`、`events/`、`community/`；`notify_server`、`state_db` 留頂層；資料檔一律不搬 | 三群邊界清楚，轉發之後還會長；`notify_server` 是 bot 對外的 HTTP 入口，之後的網頁 dashboard 也要掛它；`state_db` 被多處共用、`sent_articles.db` 就在旁邊 |
| `get_shared_state_db` 搬到 `state_db.py`（S6-1） | 它是共用基礎，搬完 `events/`、`commands` 就不必為了拿資料庫去依賴轉發 |
| dockerfile 不鎖版本，`constraints.txt` 只留作對照紀錄（S6-2 最後定案） | 使用者認為通常升到最新就好；接受下次重建拿到沒測過的新版，第一道防線是啟動 gate（測試不過 bot 起不來、舊容器照跑） |
| `services/` 那批拆成五個 commit（S7-1） | 每個 commit 只做一件事，之後要退回某一項不會連帶退掉搬家 |
| `discord_bot.py` 瘦身（P3）先不動；入口仍由 `discord_bot.py` 管，不另拆排程程式 | 使用者說先別動；入口本來就該做入口的事 |
| 搬家與改寫由主 agent 一次做完，子 agent 只做唯讀複查 | 43 個檔互相牽連，拆給多個 agent 會改到同一批檔、做法也可能不一致；沒參與撰寫的比較容易看出漏掉的地方 |

## 踩過的坑

- **`state_db` 用程式檔位置找資料庫**：`Path(__file__).parent/"sent_articles.db"`，搬這個檔會悄悄開一個空的新 DB、大量重發。搬進子資料夾時路徑那行要改成 `parents[2]`，用 `test_data_file_paths.py` 確認位置沒變。
- **`./src` 是即時掛載，函式內的延遲 import 要跑到才壞**：檔案一搬、bot 還沒重啟，跑到 00:00 日記、04:00 維護就 ImportError。在獨立 worktree 改好，套用和重啟一起做。
- **套用到重啟之間的空窗**：還沒載入的模組（例：有人加入才載的 `member_welcome`）會 ImportError，歡迎訊息也不補發。image 不含程式碼，所以先重建 image，再套用 patch、立刻重建容器，空窗縮到幾秒。
- **資料檔跟程式碼混放**：`.gitignore` 依路徑排除，搬了沒更新會把使用者資料 commit 進去。
- **import 守衛跑在啟動 gate，誤判會讓 bot 起不來**：寧可少抓、不可誤判。`__file__`、`__name__` 這類模組內建屬性曾被當成不存在；要是完整測試沒抓到，下次重啟 gate 就會擋住 bot。
- **點名兩檔互相依賴**：服務層那邊只能寫成函式內延遲 import，有人把它移到檔頭就循環 import、啟動失敗（後來改由指令層交按鈕進去）。
- **`import llm` 會連帶載入 llama_index**：`llm/__init__.py` 預先載入，容器內約 1.5 秒、1,747 個模組；MCP 殼放 `llm/` 會多這段啟動時間。
- **重建 image 會把沒鎖的套件全部升級**：09-30 清查有 52 個版本改變（主版號 3 個）；實測不會弄壞，但 `websockets` 17.1 多了一條 DeprecationWarning，代表 18 版可能不相容。
- **`mcp` 2.x 把 `FastMCP` 改名為 `MCPServer`**：寫 MCP 時要用 `from mcp.server.mcpserver import MCPServer`。
- **整批 stage 時夾帶無關的檔**：`it_comfyui_image.py` 被一起 stage，commit 前用 `git restore --staged` 移出。
- **搬檔後 logger 名稱跟著變**：只影響 log 行裡的 `[模組]` 欄。執行期字串刻意不改（`caller="diary_reflection"`、`chat_persistence:` 前綴），改了會改到 log 內容。
- **「Telegram 啟動補償 373 筆」不是搬家造成的**：當天三次重啟的數字都一樣，是相簿晚到成員不寫發送紀錄的既有問題，結果都是略過，沒有重發。
- **AST 分層測試抓不到的寫法**：importlib 動態 import 或間接 import 指令層；頂層出現 `alias.attr = …` 之後，該別名的讀取不再檢查。

## 原文

新的在前。每段標題下面是摘要，正文在「展開原文」裡。

| 日期 | 段落 | 摘要 |
|---|---|---|
| 2026-10-02 | [結構整理收尾與未決（10-02 版）](#程式結構整理資料夾分群p2p3n3-討論與搬檔地雷歸檔-2026-11-07原至-2026-10-02) | 兩次分群與點名去反向依賴已上線；剩 P2 拆檔未決、P3 暫停、N3 延後，並記下搬檔地雷與 S6-2 不鎖版本。 |
| 2026-09-29 | [結構整理討論與實作（09-29～30）](#程式結構整理討論與實作紀錄歸檔-2026-10-02原-2026-09-29) | 否決另起架構、沿用現有分法；`llm/` 依角色分子資料夾、`services/` 分三群，驗證後上線。 |

## 程式結構整理：資料夾分群、P2／P3／N3 討論與搬檔地雷（歸檔 2026-11-07，原至 2026-10-02）

> 兩次分群與點名去反向依賴已上線；剩 P2 拆檔未決、P3 暫停、N3 延後，並記下搬檔地雷與 S6-2 不鎖版本。
>
> 關鍵字：程式結構整理、llm 子資料夾、services 分群、P2 拆檔、P3 discord_bot 瘦身、N3 拆 utils.py、N1 命名、state_db 路徑、S6-2 不鎖版本

<details>
<summary>展開原文（約 3,422 字）</summary>

> 從 `AI_HANDOFF_AND_TODO.md`「程式結構整理（2026-09-29 起；主要整理已完成，剩 P2／P3／N3）」區塊（`code-structure-reorg`）瘦身前的完整原文；交接檔只留現況、規則與坑、未定案、待做。

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

</details>

## 程式結構整理：討論與實作紀錄（歸檔 2026-10-02，原 2026-09-29）

> 否決另起架構、沿用現有分法；`llm/` 依角色分子資料夾、`services/` 分三群，驗證後上線。
>
> 關鍵字：llm 依角色分子資料夾、services 分 relay/events/community、test_import_resolution、test_data_file_paths、點名 response_view_factory、S6-2 constraints

<details>
<summary>展開原文（約 37,814 字）</summary>

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

</details>
