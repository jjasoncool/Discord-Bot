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
- 2026-10-16 18:xx（/askai 想太久的修正，**已 commit `f45d029`（字典 `0ee90e6`），未推送；要重啟 discord-bot 才生效**；`doc/` 依使用者不進版控）：使用者「改」並問之前的上限是多少 → 之前沒有上限，只靠 300 秒逾時（逾時又重試 2 次，最壞一題 15 分鐘，10-12 評估時發生過）；10-09 起 /askai 38 次模型呼叫中位寫 229 token、P90 1,598、P95 2,344，撞到 4096 的只有今天這兩次，所以上限保留、改撞到後的處理。做了下面 17:4x 那筆的 ①～④（⑤ 思考預算另查）：`llm_service.py`——`chat_with_tools` 沒內容也沒工具呼叫且 finish_reason=length 時回 `kind="length"`（不當後端異常、不抓快照）；`_answer_with_tools` 第一次呼叫是 length 就照實往外丟、不再用同樣的思考不帶工具重跑；`generate_reply` 遇到 length：有給 `max_tokens`、而且這次開著思考，就關掉思考、不帶工具、用已經查到的 messages（工具輪的 progress）再答一次，仍沒答案才回 `THOUGHT_TOO_LONG_REPLY`「⚠️ 這題想太久，沒整理出答案。換個問法再問一次看看。」；length 不再觸發「圖退成 PNG 重跑」；`_chat_completion_checked` 撞到上限時把 `reasoning_content` 最後 1,500 字記進 llm_anomaly.log。沒給上限的呼叫端（插話、日記）行為不變。測試：`test_generate_reply_tools` 加 6 項（取代原本斷言「拆小」那項）、`test_llm_snapshot` 加 2 項；8 個突變全紅（第一版漏了「想太久也退成 PNG 重跑」，補了帶 GIF 的測試）；完整測試 1,639 項全過（容器內）。重啟前上線的仍是舊行為。使用者問上限要不要改 8192（中文字多）→ 說明 8192 在現行 300 秒逾時下到不了（約 20 token／秒，寫到約 5,000 token 就被逾時切斷，而逾時回「無法連線」、不走不思考重答），撞上限的原因是思考停不下來不是中文回答長 → 使用者「好吧」，維持 4096。使用者問「剛剛那是特例嗎」→ /askai 是（10-09 起 38 次呼叫只有這題撞到）；但「想太久」本身不罕見：插話（同一顆模型、沒有字數上限、每次 180 秒逾時）6 月底以來 14,763 次生成逾時 110 次（約 0.75%，平常約一天 1 次），今天 6 次（129 次裡；2 次在聊那串日文拼音），其中 3 次是被 @ 或被回覆、對方沒收到回覆；6 月底以來被 @ 卻逾時共 12 次（1,963 次裡）。**待決（新）**：被 @ 的插話要不要也比照——給一個字數上限、撞到就關掉思考重答，讓點名的人一定收到回覆（建議做，和插話上網查那批一起上；自發插話逾時照舊略過即可）。
- 2026-10-16 17:4x（/askai「回答太長寫不完」查因，**未動 code**）：群友 /askai「翻譯一下: super母洽估洽尼西TE阿GA他意」（日文發音用中文字拼寫，推測是「めちゃくちゃにしてあげたい」）回「⚠️ 這題回答太長寫不完」。log：17:31:23 開始；第 1 次（帶工具）prompt 10,830、cached 0、讀 48.7 秒，輸出 4,096 token 全是思考、沒有內容 → 撞到今天上線的 `answer_max_tokens`＝4096（/goal 第二輪 ⑦，思考也算在內）→ 被當成「帶工具的第一次呼叫失敗」→ 改用不帶工具再跑一次，同樣 4,096 全是思考 → 17:39:35 回錯誤，前後 8 分鐘、佔顯示卡兩整輪。同一句話 17:19 有人 @ 插話時也是 180 秒逾時沒講完。所以根因是模型對這類「拼音式外語」題會一直想下去（思考內容沒記進任何 log，看不到卡在哪），4096 上限把它變成沒有答案，退路又讓同樣的失敗多跑一次。**待決（選項＋建議）**：①撞到上限又沒內容時，不再走「不帶工具重跑」（同樣的思考、同樣的上限，必定再失敗）——建議做；②改成用「不思考」再答一次（多一次讀 prompt 約 45 秒＋短回答，給得出答案）——建議做；③錯誤訊息從「請拆小一點」改成「這題想太久沒想出答案」（短題被叫拆小會誤導）——建議做；④撞到上限時把思考的最後一段記進 debug 檔，才看得到卡在哪——建議做；⑤另外限制思考長度（後端是否支援每次請求的思考預算要先查）或調低思考強度（會影響所有回答深度）——建議先查支援度、不急。
- 2026-10-16 14:1x～15:4x（時事／新梗背景知識與 SearXNG 討論，**未動 code**；15:35 起在主機跑 24 小時的 SearXNG 穩定度測試，見 `mcp-search-tools` 待做 7）：使用者問①群裡聊新聞、新梗時能不能在背景更新知識、讓插話有參與感 ②SearXNG 不夠強、有沒有更好的開源或社群常用工具；之後貼另一個 AI 的建議，問有沒有讓 SearXNG 用上多數引擎的外掛或方法、`/stats/errors` 怎麼看。開兩組 workflow 唯讀盤點與調查（程式現況、插話 prompt 與快取、既有資料、交接檔定案；外部工具與來源；解封鎖做法）。15:04 使用者把 SearXNG 更新到 2026.10.16，Claude 前後對照實測。結論與待決 W6～W9 寫在 `mcp-search-tools` 待做 7「網路搜尋變弱的根因、SearXNG 更新與實測」。背景知識那題：盤點已完成（插話 prompt 只有 system 段吃快取，筆記該放 user 段新的不可信區塊；可照抄 emoji_autofill 與 ambient_memory 的背景流程；現有資料幾乎只有鳴潮、沒有新聞與梗的來源；插話 prompt 沒有日期），外部來源與做法的調查還在跑，下一輪再談。附帶：插話人設現名「琇紫」（文件裡的「柔喵」是舊稱）；現況摘要「待決定：插話被 @ 時要不要也查」已過時，改成 10-09 定案。過程中 Claude 一度說 `/stats/errors` 快照沒被實測影響，實際上實測 agent 14:26 已跑過一輪，已當場更正。
- 2026-10-16 05:xx～（/goal 第二輪：音樂重連修正、補寫兩個 bug、零散項、M6～M8、M7 工具鏈、M9 只寫設計；**不 commit、不開分支**，每塊做完封一張 git tree 快照，最後依序變成獨立 commit，做法寫在本機的 `doc/snapshot_commits.md`（使用者決定文件不進版控，只放本機）；快照清單與 commit 訊息草稿在 scratchpad `snapshots/manifest.txt`）：
  已封：00 補寫批次原樣（別人寫好、1,560 測試全過）；01 音樂重連（`player.py`：斷線後等 discord.py 自己重連最多 35 秒、等不到在同一條連線 `connect()`、連線從登記表消失才建新的；被打斷的歌記已播秒數、重連後 ffmpeg `-ss` 續播、不重複記入已播、連續 3 次放棄；刪無效的 `guild._voice_client = None`；新測試 `test_music_reconnect.py` 8 項、7 個突變全紅、完整 1,568 全過）；02 播放迴圈連不上語音時睡 5 秒再試（原本空轉吃滿 event loop）；03 測試模式的 log 只寫 test_run.log、不印到畫面（gate 的畫面就是 docker logs）；04 聊天向量庫一則一段（`store_chat` 改 `insert_nodes` 一個 TextNode，不經切段器；長訊息、變長的編輯不再因第二段撞唯一索引而漏掉）；05 raw 備份寫入遇連線層錯誤換一條連線重試一次（壞連線不放回池子）。06 LLM runtime 設定改走熱讀檔快取（`load_llm_runtime_config` 接 `hot_files`，11 處呼叫不再每次重讀重驗、壞檔沿用上次；LLMService 改呼叫它；AGENTS 表更新）；07 四份手寫排程迴圈搬到 `run_due_loop`／`periodic`（週期提醒 tick 回下一則時刻；點名 14:00 後一小時內做、錯過等明天；每日維護記「今天跑過」避免啟動補跑與排程重跑；日記排定時刻後 10 分鐘內寫一篇、不補寫不重寫；守衛例外清單清空）。08 爬蟲→bot 通知加共用密鑰（環境變數 `NOTIFY_SHARED_SECRET`，bot 驗 `X-Notify-Secret`、爬蟲帶 header；沒設維持現狀＋啟動警告一次；compose 給 scraper 帶變數、`.env.template` 加說明）；09 對話請求逾時不重試（連線錯誤與 5xx 照舊）＋ /askai 回答長度上限 `answer_max_tokens`＝4096，從 `generate_reply` 一路帶到每一輪模型呼叫。10 錯誤邊界守衛 `test_error_boundaries.py`：`llm/`、`services/` 技術與服務層接所有例外的地方以檔為單位記基準（21 檔 80 處），只准減不准增；真的是邊界在那一行註 `# 邊界：原因`；規則寫進 AGENTS。11 M6 縮小版（10-16 下午改版）：共用的頻道正規化與媒體時限只留一份在 `src/shared/telegram.py`（基礎層，只依賴標準庫），bot 直接 import；telegram-scraper 容器由 compose 把 `src/shared` 唯讀掛到 `/opt/pylib/shared`、`PYTHONPATH=/opt/pylib`，爬蟲只多看到這一小包；分層守衛的跨容器例外清空。**telegram-scraper 要 `docker compose up -d telegram-scraper` 才拿得到掛載；在那之前它若自己重啟會 import 不到 shared**。爬蟲端套件改名（scraper 的 services／utils 撞名）另一輪。12 M7：釘版本**不做**（使用者決定版本先不綁，三個容器都恢復原樣）；啟動 gate 改跑 `test/gate.py`（12 組守衛／import／設定載入，約 20 秒；完整測試交 `make test` 與 CI）、`pyproject.toml`（ruff 只開必錯規則、pyright basic）、`requirements-dev.txt`、`Makefile`（主機沒裝 make，指令可直接照抄）、`.gitlab-ci.yml` 草稿（沒跑過）。靠真實時間的 14 個測試改寫沒做；釘版本依使用者決定不做（原本 M7a 的一部分）。13 M9 只寫設計：本機 `doc/llm_worker_design.md`（不進版控；worker 容器、工作用 Postgres 交接、outbox 讓 bot 代貼、成員與表情快照、五步搬遷順序、四個待決）。
  **狀態（10-16 中午）**：13 張快照全部封好、每張都用容器 /tmp 的複本跑完整測試全過（最後一張 1617 項）；工作目錄＝最後一張快照＋排除的檔（兩個字典、交接檔、`doc/`、`it_comfyui_image.py`）。**13 張快照全部已 commit（使用者分批說 commit）：`ecf2bae` 00、`43f80c1` 01、`23e204b` 02、`f90d286` 03、`2942aa3` 04、`9275866` 05、`eb653a7` 06（loader 簡化併入）、`0511e40` 07、`9243309` 08（含使用者要求併入的守衛：爬蟲每個打 /notify 的 POST 都要帶密鑰 header，以及 .env.template 的註解）、`68713d1` 09（併入兩點修正：只有等回應的逾時不重試、撞到長度上限記 log＋結尾說明＋空內容回「請拆小」）、`ee6cc0d` 10、`64f6111` 11（**改成共用套件**：`src/shared/telegram.py` 一份，bot 經 src 掛載看得到，compose 把 `src/shared` 唯讀掛進 telegram-scraper 的 `/opt/pylib` 並設 PYTHONPATH；爬蟲的 tg_config、media_download 改 import 它；原本的兩份雙胞胎與守衛刪掉——使用者不要把整個 src 掛給爬蟲，所以不用「以 src 為根」）、`1822cab` 12（使用者決定**整個專案都不綁版本**：三份 requirements、dockerfile 恢復原樣、新 constraints 刪掉、CI 草稿不帶 constraints；bot 原有的 constraints.txt 只是紀錄，已更新成執行中容器的版本）；字典與開關 `4ff1efb`（10-16 14:17 使用者「切」，補寫開關 dry_run→on；14:14 dry_run 379 則、14:29 第一輪排進 20 則）、文件另外 commit。`.env` 已放一把隨機密鑰（使用者決定留著用）。沒重啟、沒推送**。
  **commit 步驟（使用者說 commit 後）**：跑 scratchpad `snapshots/snap_commit.sh`（依序 13 個 commit，訊息在各 `.msg`），再 `chore(settings)` 兩個字典、`docs` 交接檔＋`doc/`；`it_comfyui_image.py` 不進。快照是 git tree 物件（不是 commit、不是分支），各張的 patch 備份在同一個資料夾。
  **重啟兩批**：第一批 `docker compose up -d discord-bot`（compose 的 gate 指令改了，`restart` 不會吃到；避開 04:00～07:30）；生效：音樂重連、補寫（dry_run）、停機收尾、長訊息一則一段、raw 重試、設定熱讀、四份迴圈、/askai 逾時與長度上限、notify 密鑰（沒設就只警告）。第二批 `docker compose up -d scraper telegram-scraper`（scraper 帶 NOTIFY_SHARED_SECRET、telegram-scraper 掛 shared；順序先 scraper 再 discord-bot）；重建映像檔（`--build`）才會用到釘好的版本，不急。
  **照建議先做、請使用者最後確認的決定**：①音樂等 35 秒／同一條連線重連／斷點續播（連續 3 次放棄）；②長訊息一則一段（embedding 上下文 8192 放得下）；③raw 寫入連線錯誤重試一次；④`load_llm_runtime_config` 改熱讀檔、壞檔沿用上次；⑤點名只在 14:00 後一小時內做、日記排定時刻後 10 分鐘內寫（重啟錯過不補）；⑥notify 密鑰沒設不擋只警告；⑦對話逾時不重試＋/askai 上限 4096 token；⑧錯誤邊界只管 llm／services 的技術與服務層（功能層不管）；⑨M6 做縮小版（兩份雙胞胎＋守衛），爬蟲套件改名與三容器以 src 為根留到另一輪；⑩gate 只跑 12 組守衛，完整測試交 make test／CI；⑪yt-dlp 不釘版；⑫M9 只寫設計、M10 不做。
  **沒做、要另排**：爬蟲端套件改名（M6 完整版）、telegram-scraper 停機（runner.py／main.py／db.py＋compose stop_signal）、靠真實時間的 14 個測試改寫、ruff／pyright 本機沒跑過（主機與容器都沒裝）、CI 草稿沒推沒跑、runtime 檔依意義拆（會搬資料檔）。每塊都有新測試＋突變確認會紅，完整測試用快照在容器 /tmp 跑。要使用者決定的照建議先做，最後一併問。
- 2026-10-15 18:2x～19:xx（音樂 bot「一直自我斷線」查因，**未動 code**）：成因鏈、覆核結論與修法方向記在「點歌機器人專區 › 語音斷線後的自我重連競態」。四路獨立覆核（反證推論、盲測第二意見、discord.py 上游歷史、三週 log 統計）結論一致；修法四題待使用者定案後動手，改完要重啟。
- 2026-10-15 09:xx～16:xx（停機收尾＋聊天向量庫補寫；**停機收尾已 commit `6df0a78`（10-16，未推送、待重啟）**；**聊天向量庫補寫未 commit，10-16 使用者交給另一個 session 處理**——檔案留在工作目錄：`llm/storage/chat_index_backfill.py`、`store_chat.py`（compose_persist_text／preview_text／backfill_candidates／enqueue_backfill）、`switches.py`（chat_index_backfill_mode）、`discord_bot.py` 的補寫迴圈登記、`background_tasks.periodic` 的 first_after、`raw_message_store.py`／`sticker_cache.py` 的說明、`test_layering.py`、`test_chat_index_backfill.py`、`test_background_tasks.py` 的 first_after 測試、`test/integration/it_chat_index_backfill.py`；compose 的 `stop_signal: SIGINT` 與 Dockerfile 的 CMD 註解已併進 `10e0fd4`，13:06 重建生效）：
  ①使用者問 compose 的 `command` 和 Dockerfile 的 `CMD` 會不會衝突 → 不會（compose 蓋掉映像檔預設；映像檔沒有 ENTRYPOINT；search-mcp 共用映像檔、另有 command）。測試指令留在 compose：映像檔不含程式碼（src 是執行時才掛進去）、兩個服務共用映像檔、改了只要重建容器。
  ②查證時發現每次 docker stop 都等滿 10 秒被 SIGKILL：PID 1 的 python 沒接 SIGTERM（`/proc/1/status` 的 SigCgt 只有 SIGINT），kernel 直接丟掉 → compose 改送 SIGINT。13:16 第一次用 SIGINT 停：cog_unload 有跑，但卡在音樂斷語音（等一個永遠不會來的「已離開」回報），仍是 137。
  ③使用者「都做」（停機收尾＋緩衝遺失）。**已定案的做法**：
    - `MyBot.close`：寫 raw → 停 notify server、Telegram 轉發 → discord.py 的關閉 → `cancel_other_tasks` → 關共用 StateDB → 補寫 raw。前面幾步共用總期限 7 秒、每步各有上限，每步放進自己的 task（不用 wait_for：discord.py 斷語音會吞掉取消再等）；關 StateDB 另外保留 1 秒；第一次寫 raw 逾時就不寫第二次。停機開始後 on_ready 不再開 notify server／轉發。
    - 音樂：停機時離開語音放進自己的 task，2 秒到就 `voice.cleanup()` 取消登記（取消落在關語音 websocket 那段時，discord.py 的 finally 會再等 30 秒）；播放迴圈的取消被吞就再取消；`mark_closing` 之後不開新迴圈。
    - `close_shared_state_db`：關掉 aiosqlite 連線（非 daemon 執行緒不關，Python 退不出去），關掉後不再開新連線。
    - 週期提醒、點名的排程迴圈被取消時改成往外丟（原本每次停機記 3 行「背景迴圈自己結束了」）。
    - 停機時不寫聊天記憶的緩衝（要算 embedding，時間不夠）→ 新增 `llm/storage/chat_index_backfill.py`：每 15 分鐘（啟動後 5 分鐘第一次）查 raw 有、聊天向量庫沒有的（近 14 天、先補最新的、一次 20 則），組成和即時寫入一樣的文字排進 store_chat 的佇列；開關 `chat_index_backfill_mode` 預設 dry_run（只記 log，聊天向量庫是高風險資料，要使用者看過再切 on）。
  ④驗證：容器內完整測試 1,560 全過（新增 32 項）；突變 39 處全紅；整合測試 `test/integration/it_chat_index_backfill.py` 在正式資料上通過（近 14 天候選 384 則，最新那批正是 10-14 19:54～10-15 13:14 幾次重啟丟的）。用了三輪 workflow：停機路徑盤點、telegram-scraper 盤點、獨立複查（照它修了總時限、斷語音的硬上限、StateDB 重開、補寫細節、一個改壞時會卡死而不是變紅的測試）。盤點數字：近 7 天 raw 7,681 則有 297 則沒進聊天索引，集中在重啟前幾分鐘；10-09 後端卡住後那次重啟丟約 212 則。
  **待使用者**：(a) 重啟 discord-bot（避開 04:00～07:30）：這次停機跑的還是舊程式，照樣等 10 秒；再停一次才看得到新收尾——`docker events --filter container=discord-bot` 停止時沒有 kill 9、die 的 exitCode 是 0，log 有「停機收尾開始／完成」與「[MusicCog] cog_unload: 清理完成」。(b) 啟動 5 分鐘後看補寫的 dry_run log，再決定切 on：`settings/switches.json` 加 `"chat_index_backfill_mode": "on"`（使用者設定檔，說明列等使用者同意再加）。
  **未定案（選項＋建議）**：
    1. 長訊息寫不進聊天向量庫（既有）：內文加預覽超過約 940 個 token 會被預設切段器切成兩段，第二段撞到 message_id 唯一索引、整筆回滾，卻被當成「已存在」（800 字以上 29 則缺 23 則）；編輯後變長的，舊的先被刪、新的寫不進去。A 改成一則一段（先確認 embedding 輸入上限）／B 長訊息截斷／C 不動。建議 A；修好後 14 天以外的要不要補屬於寫高風險資料，另外問。
    2. raw 寫入失敗整批丟（既有；連線池給到已斷的連線，log 有 09-24、10-02 兩次）：停機收尾和補寫都靠 raw。A 遇到連線錯誤換新連線重試一次／B 失敗放回緩衝（設上限）／C 不動。建議 A。
    3. telegram-scraper 的停機（盤點完成，未動）：一樣每次被 SIGKILL；只改 compose 不夠——`db.close()` 會卡在一條沒歸還的 LISTEN 連線（runner.py:323）。要改 runner.py（歸還連線、先停補掃再斷 Telegram）、main.py（接 KeyboardInterrupt 正常結束）、db.py（pool.close 加時限），再加 `stop_signal: SIGINT`。session 不會壞（Telethon 每 60 秒存一次）、漏的訊息重啟後歷史掃描補得回。建議做，下一輪。
    4. 音樂播放迴圈在語音頻道找不到時會空轉（既有）：`_play_next` 立刻回來、`_play_loop` 不睡就重試，卡死整個 event loop（頻道被刪才會發生）。建議連不上時睡幾秒再試。
    5. 測試的 log 印到 docker logs：每次重啟約 30 行測試故意製造的 ERROR，使用者會誤以為 bot 出錯。改 `test/__init__.py` 只寫 test_run.log（unittest 自己的失敗報告不受影響）。建議做。
- 2026-10-13 11:xx～12:xx（M2 收尾＋交接檔歸檔，**未動 code**；之前 09:0x～11:2x 的 M2a `63be5a4`、字典 `65354a9`／`60c4744`、交接檔 `2d6523d`、tag `checkpoint-20261013-m2a`，11:20 使用者重啟 discord-bot 與 search-mcp 後 gate 1,426 全過、上線正常）：使用者質疑 M2b（`llm_service` 搬進 `llm/`）與 09-29 定案相反 → 退回（還原 19 檔）、M2c 取消；分層改成寫到子資料夾的五層，守衛 `test/test_layering.py`（M2d，1,432 項全過、6 個突變全紅，併進 M3 的 commit）。使用者「整理 AI_HANDOFF_AND_TODO.md、已完成的打包到 TODO-completed.md，然後繼續做 M3」→ 本次歸檔：巴哈編輯限速整塊、Telegram 過濾 285 行濃縮成現況＋定案摘要＋待辦、交易改版 150 行濃縮、Persona M7 的 PA／PR 討論、插話 AM-Q1／Q4～Q8 與 RB、/askai 接線的實作與審查（情報搜尋待做 7）、架構審視 M1／M2 過程、9/30～10/09 盤點紀錄；順手核對（唯讀）：週期提醒 10/7 04:00 矩陣提醒已發（log `matrix:2026-10-07:reset`）、⑤ 精簡版 10-02～10-13 連續 12 晚 failed=0（PR-Q2 刪 ③ 的門檻已達到，等使用者）、交易與商品 10-04～05 的修改都已 commit（至 `5809120`）、13 個 commit 未推送。接著做 M3：第 1 步（守衛「技術層與服務層不可 import discord」、`sticker_cache` 與 `context_retriever` 改掉 discord import、10 個突變全紅、完整 1,437 全過）做完等使用者看；第 2 步搬不搬 `llm/ambient`、`llm/storage` 先問 → 使用者看過對照表後「不搬」，M3 完成（程式待 commit）。交接檔歸檔已 commit `c078f0f`、字典 `5ace57b`。使用者問 `if TYPE_CHECKING: import discord` 是什麼、拿掉為何不會錯 → 說明那是給編輯器看的型別註記用 import，執行時是 False、註記因 `from __future__ import annotations` 只是字串；建議留著（和 `chat_line` 同寫法），使用者沒要求拿掉。13:5x 使用者「commit」→ M3 程式 `d2d9dc8`；問「test 裡面會不會太多東西需要瘦身」→ 逐模組計時與數字、四個選項見架構審視區塊（建議 M7b 提前、不刪測試），等回。 使用者「M4 可以開始進行」→ M4a 做完等看：`on_ready` 只剩登記（`discord_bot.py` 929 → 718 行、新模組 `llm/persona/daily_maintenance.py`）；使用者問模組底下多出的 `flush_loop` → 改成共用 `background_tasks.periodic`；使用者「③ 跑一段時間了可拆掉嗎」→ 抽 5 筆精簡版沒問題、使用者「一起改吧」→ 拆掉備援萃取 ③ 與兩個手動指令併進 M4a（`personality_extractor.py` 669 → 174、`llm_commands.py` 1,554 → 1,119）；完整 1,440 全過、13 個突變全紅 → 使用者看過圖解頁後「不用手動入口、維持精簡版、commit」→ `7a369b6`。接著 M4b：`_handle_askai_request` 拆四段，先寫 11 項特徵測試再拆，完整 1,451 全過、13 個突變全紅 → 使用者換到另一台電腦接手（同一主機、同一 session），確認測試 OK 後「commit」→ `693eaf1`、字典 `7aeadf9`。
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
| AI 偶爾插話 / 閒聊（功能二） | **已上線**（含 2026-08-09 自然插話重構）；10-02 看得懂貼圖、X 貼文、別的伺服器的表情（`673a965`）、AI 看圖補表情／貼圖字典（`cd0baf7`）、10-07 被罵的應對（`0f71b6d`）都已上線並 commit；待決 AM-Q2（放寬 style_refs 門檻）、AM-Q3（接話算正向）、AM-Q6h（偏掉的描述）、RB-Q9（道歉消氣）、AL-Q1～Q5（自主學習，暫停）、KN 插話判斷時自己上網查（10-16 討論中：KN-Q1～Q7 已定，KN-Q5b、KN-Q8～Q11 待決）；待做 C-4 整併／淡忘、觀測面板、鉤子權重迴歸 | 85% | [AI 偶爾插話](#ai-偶爾插話--閒聊功能二已上線c-4-待做) |
| Persona Agent M7（精簡版發布） | **已上線**；10-01 隱私歸因與名字對照上線、10-02 手動修正四條舊錯誤；精簡版 10-02～10-13 連續 12 晚 failed=0；**備援 ③ 與兩個手動萃取指令 10-13 已拆（`7a369b6`，重啟後生效）**，04:00 維護變四步；不補手動入口、「精簡版」名稱維持 | 92% | [Persona Agent M7](#persona-agent-m7精簡版發布2026-09-28-已上線精簡版連續-12-晚穩定待刪備援萃取) |
| ComfyUI 產圖 + GPU 資源仲裁 | **規劃定案（2026-09-02）**；租約鎖與卸載 helper 已完成（`e13343d`），鎖有漏洞待修；落地細節討論中 | 25% | [ComfyUI 產圖](#comfyui-產圖--gpu-資源仲裁2026-09-02-規劃定案未開工) |
| AI 私聊頻道 + 三層記憶（功能一·姊妹案） | 規劃完成（含道德守門）；人設 prompt 已就位；**本輪暫放旁邊** | 10% | [AI 私聊頻道](#ai-私聊頻道--三層記憶機制規劃中) |
| 使用者指令記憶 (/remember) | 規劃中（與 AI 私聊頻道互補） | 5% | [/remember 規劃](#使用者指令記憶-remember-未來工作) |
| Reaction 統計 / 社群互動玩法 | 資料收集已完成（`raw_message_store`）；玩法、/askai 整合、人格加權都還沒做 | 15% | [Reaction 統計](#reaction-統計與社群互動玩法規劃資料收集已完成) |
| 點歌機器人（Music Bot） | 已上線運作；10-15 查出語音斷線後的自我重連競態，**10-16 修正已 commit（`43f80c1`、`23e204b`）並上線**（discord-bot 10-16 14:08 重啟）；四題的做法在 /goal 第二輪照建議先做、待使用者最後確認 | 85% | [點歌機器人](#點歌機器人專區) |
| Telegram relay 可靠性 | 補掃、媒體防雷、相簿漏圖修正都已上線並驗證（9/29 起合併與補圖符合設計） | 98% | [Telegram 補掃](#telegram-漏收補掃與相簿漏圖已上線) |
| 程式結構整理 | **主要整理已完成並上線**（`llm/` 與 `services/` 分群、點名去除反向依賴）；剩 P2 拆檔（未決）、P3 `discord_bot.py` 瘦身（暫停）、N3（延後）、命名慣例未寫進 AGENTS.md | 90% | [程式結構整理](#程式結構整理2026-09-29-起主要整理已完成剩-p2p3n3) |
| 架構審視與滾動修正（/goal） | 11 項發現；**M1～M5 上線**；**第二輪（10-16）13 張快照已 commit、已重啟上線（discord-bot、scraper、telegram-scraper 10-16 14:0x 重啟；已推送到 `e2662c2`）**：音樂重連、補寫批次與兩個既有 bug、設定熱讀、四份排程迴圈搬 `run_due_loop`、notify 密鑰、/askai 逾時不重試＋長度上限、M8 錯誤邊界守衛（21 檔 80 處基準）、M6 縮小版（bot 不再 import 爬蟲）、M7 釘版本／gate 瘦身／ruff・pyright 設定／Makefile／CI 草稿、M9 設計寫在本機的 `doc/llm_worker_design.md`（不進版控）；M10 不做。做法寫在本機的 `doc/snapshot_commits.md`（使用者決定文件不進版控，只放本機），待確認的 12 個決定與重啟兩批列在最後盤點紀錄 10-16 那筆 | 85% | [架構審視](#架構審視與滾動修正2026-10-12-起goal-進行中進度見區塊內進度) |
| 情報搜尋（MCP）：公告、FB、PTT、巴哈 | **P1～P4 已 commit（10-08，已推送）**：全文索引＋向量（RRF）＋reranker、42 題評估（原句 Hit@5 21%→67%、關鍵字 60%→81%）；**10-12 Agent 評估（已 commit，未推送）**：正式模型自己寫的查詢 71%、算上換字再查 79%、回答初判 31／42，三題未定案見區塊待做第 9 項；**R12 已上線並 commit（10-08，已推送）**：常駐服務 `search-mcp`、索引移到 `search_data/`、每日補向量、重排讀原句並已開啟；**延遲改進與 /askai 接線已 commit（10-09，已推送、已上線）**：背景同步、冷快取讀取量 52 MB → 4.5 MB、/askai 由模型決定查不查；插話上網查改由 ambient-chat 區塊 KN 系列處理（10-09「被 @ 時不查」已被 10-16 KN-Q4 取代）；**10-16 SearXNG 更新到 2026.10.16 並實測**：yahoo 恢復且最準、duckduckgo 部分恢復、bing 變得不穩（只查第一個字、亂回），bot 預設引擎待換（W6～W9，見區塊待做第 7 項） | 95% | [情報搜尋（MCP）](#情報搜尋mcp官網公告官方-fbptt巴哈p1p4-已完成常駐服務已上線) |
| LLM 推論：KV cache 與 GPU | 查證完成、`llm_usage` 已上線；待調 prompt 順序、`--parallel` 實驗 | 30% | [LLM 推論](#llm-推論kv-cacheprompt-快取與-gpu2026-10-08-查證) |
| Telegram 訊息 LLM 過濾 + 隔離區 | **2026-10-07 已上線**（模型看文字＋圖判有沒有遊戲資訊、隔離 thread、放回面板、舊訊息搬移腳本），10-08 排隊到 30 分鐘＋`needs_recheck` 補判上線，全部已 commit；開關 `telegram_filter_mode=on`；剩轉發端那批（有文字的單則先送文字後補到的圖送不出去）與幾個小項 | 90% | [Telegram 過濾](#telegram-訊息-llm-過濾--隔離區2026-10-07-已上線10-08-補判上線) |
| 週期活動提醒（深塔海墟矩陣） | **已上線**：9/29 20:00 矩陣結束前提醒、10/7 04:00 矩陣開放靜音提醒都已實發（log 核對）、手機通知確認正常；待自介面板置底驗證 | 97% | [週期活動提醒](#週期活動提醒深塔海墟矩陣已上線) |
| scraper 抓網頁機制＋IT 就地補內文 | **已上線**：IT 補內文已驗證（10/01 補 11 則）；HKEPC 10/01 03:46 後 0 次 403；巴哈每輪仍約 80 分鐘待查；SC-Q6 觀察 | 95% | [scraper 抓網頁機制](#scraper-抓網頁機制檢查2026-10-01-已上線) |
| 跨來源整合（Article/FB/PTT/TG） | 發文已共用 `post_to_channel`、Telegram 自成分層；讀資料與事件模型整合沒做（動手前先照「沿用現有架構」重新評估） | 40% | [跨來源整合](#跨來源整合專區規劃發文已共用) |
| 指令整理與管理入口 | 規劃：test 指令隔離、`/persona` 子指令（PR-Q4 的兩個指令 10-13 已刪，剩 3 個可收）、管理面板、網頁 dashboard；權限檢查收斂暫緩 | 10% | [指令整理](#指令整理與管理入口規劃未動工) |
| 交易功能改版（自發貼文接單、販賣者上架商品） | **已上線並 commit**（10-03 A＋B `84a8ba3`、商品上架至 `46e84a6`；10-04～05 實測回饋 13 個 commit 至 `5809120`）；流程見根目錄 `TRADE_FLOW.md`；剩措辭 A／B／D 幾句、TR-Q33 上架說明附圖（等使用者截圖）、舊留底含對話要不要改、價格 0 的意思；之後：沒人收尾的交易（TR-Q5）、刪 Legacy view（`commands/forum_monitor.py` 的 `LegacyTransactionView`，10-16 查仍在；四份舊迴圈搬 `run_due_loop` 已在 10-16 `0511e40` 完成）、價目表併入商品目錄 | 90% | [交易功能改版](#交易功能改版與商品上架2026-10-0305-已上線並-commit剩措辭與價目表待決) |

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
last_confirmed: 2026-10-16
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
   - **留給使用者**：(1) ~~插話被 @ 時要不要也能查~~ → **已定案：不查**（10-09 使用者「@先不要查 因為/askai 就是特定查詢目的」）**；10-16 被 KN-Q4 取代：插話判斷時可以查，被 @ 也可以，見 ambient-chat 區塊**。(2) 最多 2 輪、全文 2,500 字是估的，建議上線一週後看 `askai_response_history.jsonl` 的 `intel_meta` 與 `web_context_meta.calls` 再調（輪數是情報與網路共用；放寬輪數的選項見第 9 項）。(3) `searxng/settings.yml` 的 openmeteo 那段建議加 `timeout: 4.0`（地點查座標＋拿預報常超過預設 2 秒；不能超過 `max_request_timeout: 4.0`），改完 `docker compose restart searxng`；`searxng/` 是使用者的檔，我沒動。
   - **未定案：天氣題查不到預報**（關鍵字模式走同一條路由與引擎，不是這次改動造成）。選項：(a) 先觀察，看群友多常問天氣；(b) 加一個天氣工具接中央氣象署開放資料 API（要申請免費授權碼，回答有實際數字）；(c) 調路由，天氣題加站內限定（例：`site:cwa.gov.tw`）。建議 (a)，有人常問再做 (b)；(c) 引擎對 site 語法支援不一，要先量。
   - **未定案：股價查不穩**。選項：(a) 加「台股」類型直接查證交所即時報價（`mis.twse.com.tw` getStockInfo，不用 key、0.07 秒、與看盤網站一致；網頁背後沒公開文件的介面、可能改版或限流，要股名→代號表，休市日回前一交易日要標資料時間）；(b) 等 duckduckgo 解封、不改程式；(c) Tavily 等免費方案要註冊 key，不符合「純免費」先排除。建議 (a)。
   - **留給使用者（新）**：(W5) 關鍵字模式（`askai_web_search_mode=keyword`，`intent.should_search` 與 `_ROUTE_RULES`）要不要整個刪掉——建議工具模式跑一週沒問題再刪，現在留著當退回開關；(W6) 新聞類型要不要拿掉一週限制（讓 duckduckgo news 回來，會混舊文）——建議等網路搜尋評估集。
   - **網路搜尋變弱的根因、SearXNG 更新與實測（10-16，未動 code）**：使用者問 SearXNG 不夠強、有沒有更好的開源或社群常用工具；貼了另一個 AI 的建議（降頻、快取、退避、正式 API 當備援、看 `/stats/errors`），問有沒有別人做的外掛或方法讓 SearXNG 用上多數引擎。15:04 使用者自己把 SearXNG 從 2026.8.14 更新到 2026.10.16（`settings.yml` 沒動），Claude 前後對照實測（結果在 scratchpad `after_upgrade/`）。
     - **根因（更新前查證）**：被擋主因是舊版送出的連線特徵不像瀏覽器（httpx＋`shuffle_ciphers` 打亂加密套件、標頭順序），不是查詢量、也不是封 IP：7 天內搜尋引擎 403 為 0；停用很久的 brave、startpage、baidu 第一次請求就被擋；duckduckgo 一週十幾次照樣 100% 驗證（10-09 20:33 起 25 次全擋，SearXNG 對它的暫停寫死 0 秒）。上游 #6596（DDG 看標頭順序與 TLS 指紋）、#6570（Google 檢查 TLS）、#6819（Brave 429，修正 PR #6836 未合併）；#6620（09-04 合併）網路層改 curl_cffi 模擬 Chrome、#6671（09-11 合併）修 bing「只用查詢第一個詞」，兩個都在 GitHub 頁面確認已合併。那份建議裡的快取、單一工作者、被擋暫避、停用壞引擎 bot 都已經有；正式 API 違反純免費。`docker compose up -d` 不會自己 pull，compose 寫 latest 不等於最新。
     - **更新後實測**（同一套 18 引擎 × 2 題，加 bot 實際流程 8 題、補測 13 次）：yahoo 從「連線被斷」恢復，兩題全對題，新梗「何意味 梗」前 5 筆是知乎、百度百科、B 站梗百科、頭條、萌娘百科，「鳴潮 新角色」是巴哈、wuthering.gg、維基——目前最準；duckduckgo 驗證率 100% → 40%；sogou 一題可用（簡中）；yandex、360search 照舊可用（yandex 繁中相關度高，部分標題變成網址）；**bing 更不穩**：「颱風 停班停課」第一次回 10 筆成人內容（有送安全搜尋）、第二次正常，「台積電 股價」正常，「鳴潮 新角色」「何意味 梗」只查第一個字（回辭典的「鳴」「何」），不帶語系時「鳴潮 新角色」回 Lidl 超市——bing 回垃圾時 SearXNG 不算錯誤，會直接混進結果；google、google news 改成 403；brave 照舊 429；startpage「Anubis difficulty too high」；baidu 驗證；reuters 401；yahoo news 0 筆；openmeteo 照舊逾時。bot 實際流程（bing＋duckduckgo）：股價題變好；「鳴潮 新角色」「何意味 梗」只拿到辭典單字頁；新聞「鳴潮 改版」整串無關（一週限制把 duckduckgo news 擋掉，它不限時間時 11 筆對題、全附日期，但混 2024 舊文）；天氣逾時。新版因舊 `settings.yml` 每次啟動噴 15 行 Cannot load engine（presearch、karmasearch、aol 等新版已刪），不影響運作。
     - **別人的「解封鎖」做法對這台的評估**：IPv6 輪換（duckduckgo、startpage、mojeek 沒有 IPv6，Google 整段擋，要改主機與 Docker 網路，不對症）；Cloudflare WARP（第一次啟動自動註冊裝置帳號，違反「不註冊」，條款灰色）；Tor（出口多在國外，bing 依出口地區給結果，Google 必擋，慢）；多代理輪流（免費代理不安全、付費違反純免費，驗證頁是 200 不會觸發換代理）；家用瀏覽器手動解驗證（只對按 IP 封的引擎有效，DDG 不按 IP 封）。第三方外掛、fork 的盤點與社群做法調查還在跑，回來再補。
     - **留給使用者**：(W7) bot 一般搜尋的引擎 `AskAIWebSettings.default_engines` 從 `bing,duckduckgo` 換成 `yahoo,duckduckgo,yandex`、拿掉 bing——建議換（bing 回垃圾時不報錯、會混進結果，還出現過成人內容；duckduckgo 常被擋時另外兩家互補），要改程式與測試、重啟 discord-bot；(W6) **已定案（10-16，使用者問「會不會拿到舊聞而非新聞」，聽完說明後「如果可以依照搜尋結果排序日期那我當然不需要限制」）**：新聞不限時間查、結果照日期新到舊排；bing news 不給日期、排不了，保留它自己支援的一週條件、排在有日期的後面；沒日期的不當最新（規則檔第 5 條已有）；要改 `tools._KINDS` 的 news 與合併後依 publishedDate 排序，程式待動；(W8，10-16 使用者「想知道作了之後會有什麼改變再評估」：Claude 做草稿並用 SearXNG 自己的設定載入程式算出換上前後的實際差異，評估後再定) `searxng/settings.yml` 改成 `use_default_settings: true` 只留覆寫值（停用清單、`request_timeout` 回上游預設 3.0、openmeteo `timeout: 4.0`），清掉新版已刪的引擎、拿到 duckduckgo web、google cse 等新引擎——建議改，Claude 先在 scratchpad 做對照草稿，使用者同意後 sudo 換上、先備份，改完再測新引擎；(W9) **已定案（10-16，使用者「不算，讓他開可以，但我覺得用預設值也可以」）**：新版自動解 JS 挑戰（duckduckgo web）與工作量證明（startpage 的 Anubis、mojeek 的 ALTCHA）不算破解真人驗證，可以開；但照官方預設（duckduckgo web 預設關、startpage 與 mojeek 預設不載入），W8 草稿不另外覆寫這三個，bot 的預設引擎也先不加。從 10-09「純免費、不註冊」推得：WARP、付費代理、要 key 的 API 不採用。舊題的建議同步調整：W5（刪關鍵字模式）——工具模式上線一週，但網路搜尋 0 次、等於沒驗到，建議 W7 改完、真的有人用過再刪；股價——新版 yahoo、bing 已查得到股價頁，建議先不做台股類型；讀網頁全文（第四批 12）——建議併進「背景補時事／新梗知識」那題一起談。
     - **社群常用工具與替代方案（10-16 外部調查，回答使用者「有沒有開源更好的、社群常用來爬網路資料的」）**：沒有「開源、自架、免 key 又嚴格勝過 SearXNG」的通用搜尋——有自有索引的（YaCy、Mwmbl、Marginalia、Open Web Index）中文時事太弱或要註冊、Stract 已封存；其他元搜尋（4get、Degoog、LibreY、Websurfx、OpenSERP、ddgs）爬的是同一批上游；Whoogle 2026-07 宣告結束；Vane（原 Perplexica）底層就是 SearXNG。開源 LLM 應用的免 key 預設幾乎都是自架 SearXNG（Vane、Khoj、local-deep-research、Morphic 的 Docker 版）；要 key 的預設以 Tavily 最常見；Bing Search API 2025-08-11 退役、Google Custom Search JSON API 不收新客戶（2027-01-01 停）、Brave 2026-02 起要信用卡。字面上免 key、但有條款或存續風險的新選項：keenable 公開端點（每 IP 每小時 1,000 次；條款寫「僅限個人使用」並禁止把輸出單獨轉給第三方）、You.com 免 key（每天 100 次，官方定位評估用）、Firecrawl 免 key（每 IP 每日上限未公布）、SearXNG 的 google cse（借第三方公開 cx，「搜尋整個網路」只到 2027-01-01）——建議先不採用，等 W7 測試結果，yahoo 撐不住再評估。「爬網路資料」那類工具解決的是讀全文不是找得到：輕量做法 curl_cffi 下載＋trafilatura 抽正文（實測 10 個台灣頁面含 Big5 都抽得到、每頁 3～160 毫秒、峰值約 52 MB）；Crawl4AI、Firecrawl 自架、Jina 自架對這台 VM 太重；Scrapling 的 solve_cloudflare、FlareSolverr、newspaper4k 的 cloudscraper 是過 Cloudflare 驗證，不用。Google 新聞 RSS 的 robots.txt 禁止 /rss 並點名 AI 爬蟲，排除。
     - **W8 前後差異評估（10-16 16:4x，草稿與模擬都在 scratchpad `w8/`，沒動使用者的檔）**：用 SearXNG 自己的載入程式（`init_settings`＋`load_engines`，擋掉寫檔與連網）模擬；同一套模擬跑現在的檔和執行中 `/config` 的 232 個引擎八個欄位 0 處不一致，可信。使用者的檔是上游 2026-04-17 範本（8579974f5）的原樣複本，使用者自己改的只有：default_lang zh-TW、formats 加 json、request_timeout 2.0、max_request_timeout 4.0、打開 bing 與 reddit、08-15 停用 8 個。草稿 `settings.proposed.yml` 約 60 行。換上後**會變**：一般逾時 2→3 秒（唯一影響 bot 的一項；bot 用的引擎 p90 約 1.8 秒）；openmeteo 4 秒（天氣才有機會查到）；啟動錯誤約 230 行（19 個 Cannot load engine）→ 只剩 ahmia、torch 兩行（官方預設本來就有）；載入引擎 232→261（多 39：預設開 7 個含 google cse、可指定 32 個含 duckduckgo web；少 10：startpage、mojeek×3、yahoo news 等官方改成不載入，bot 都沒用）；搜尋框建議字從關變成送 DuckDuckGo；瀏覽器表單 POST→GET（搜尋字會進網址與紀錄）。**不變**：formats 含 json、安全搜尋、語系、max_request_timeout 4.0（openmeteo 4.0 與官方長逾時都靠它截住，不能拿掉）、外掛、限流；bot 指定的引擎與 W7 候選全部載得到。**W8 小題（待使用者）**：W8a 換不換——建議換，10-17 15:35 測試結束後；W8b 一般逾時跟官方 3 秒或留 2 秒——建議 3 秒；W8c 草稿裡 9 筆「維持現況」的圖片引擎（1x、artic、devicons、flickr、lucide、openverse、google images、qwant images、qwant videos，舊範本的值、官方因結果差／逾時／限流關掉）留或刪——建議刪（瀏覽器圖片分頁 14→6），常用 SearXNG 搜圖才留；W8d google cse（新版預設開、進瀏覽器一般分頁；借 blackle.com 的公開元件 ID、不用 key，「搜尋整個網路」2027-01-01 停，借用 ID 屬條款灰色）照官方開著或關掉——建議照官方（W9「用預設值也可以」），bot 不用它；W8e 實際生效的 secret 是 docker-compose.yaml 寫死的預設字串（compose 進版控、公開鏡像看得到；.env 沒有 SEARXNG_SECRET），只有本機與 docker 內網連得到——建議另外在 .env 加隨機 SEARXNG_SECRET 再 `docker compose up -d searxng`（restart 不吃新環境變數），不急。bing 那行（瀏覽器一般分頁查 bing）跟 W7 一起定。套用 7 步（備份、awk 搬原 secret 行、`check_final.sh` 換上前唯讀檢查、cp、restart、看 log、確認 `/config` 印出 `261 4.0 True False 'duckduckgo'`）與還原步驟寫在 workflow 結果裡，使用者決定後再給。
     - **外掛與解封鎖方法的調查結論（10-16，第二組 workflow，九個 agent 含四個反查）**：沒有能讓多數引擎不被擋的第三方外掛——SearXNG 外掛只有 pre_search、on_result、post_search 三個掛鉤，改不了請求方式；第三方能用的都是 sidecar 或自訂引擎（4get-hijacked 15 星、07-04 後沒更新；4get 與 Degoog 的 Google 都要真瀏覽器加螢幕；Trawl 會解 reCAPTCHA／hCaptcha／Turnstile，違反規則）；上游 09-08 刪掉「查別的實例」的引擎，維護者稱拿公開實例當備援 very selfish。官方 09-04 的 curl_cffi 改版就是最有效的方法（已更新）。升級後仍擋：google／google news 403（上游 #6835 家用網路同樣 403、沒人回）、brave 429（#6836 未合併）、startpage「Anubis difficulty too high」（解題上限寫死 4）、baidu 驗證、sogou 與 quark 解析錯、reuters 401。可以試的小點：duckduckgo（html）引擎用 Chrome 的連線特徵卻自稱 Firefox（本機回聲測試確認同時送出 Chrome 的 sec-ch-ua 與 Firefox UA），可能是它還有約四成被擋的原因之一；settings.yml 的引擎項目可以覆寫模組變數（`_HTTP_User_Agent`），不改程式就能試，但依賴內部變數名、未實測。另有一批轉賣 Google／Brave 結果的新引擎（startpagina、s1search、resulthunter、tusksearch 等）上游多為 inactive、沒有台灣實測。
     - **穩定度測試（10-16 15:35 起跑 24 小時，10-17 15:35 自己停）**：使用者問「不知道怎麼樣才是穩定的」。定義（每個引擎各自算）：查得到率（沒被擋、沒逾時、有結果）≥90%、有用率（查得到時前 5 筆至少 3 筆對題）≥80%、不當內容 0 次＝可當主力；查得到與有用都 ≥60%、沒有不當內容＝只能當備援；其他＝不穩；另看同一題重複查時前 5 筆網址的重疊度（忽好忽壞的引擎會偏低）。做法：主機上跑 `/tmp/claude-1000/-home-jason-discord/5c5c87ce-c09d-4572-80a9-fcf990d36ac7/scratchpad/stability/monitor.py`（只讀 127.0.0.1:8888，不碰 bot），每 20 分鐘一輪：yahoo／duckduckgo／yandex／bing 查同一題（10 題輪流）、duckduckgo news（不限時間）與 bing news（限一週，同 bot 現況）各查一題、每 3 輪合查 yahoo,duckduckgo,yandex（W7 提議的組合），每輪另存 `/stats/errors`；每輪 7～8 次請求。資料在同資料夾 `run1/rounds.jsonl`，摘要用 `summarize.py <rounds.jsonl> [--detail]`；提早停：`kill $(cat run1/pid)` 或建 `run1/STOP`。資料在 /tmp，主機重開機會消失。第一輪 7 次全查得到、全對題（bing 這次「鳴潮 新角色」5/5 對，一小時前同一題回辭典的「鳴」）。結果用來決定 W7。
     - 小事：`llm_settings.py:276-277` 的註解說 SearXNG 最長等 4 秒，實際只等 2 秒（整體等待＝min(所選引擎 timeout 最大值, max_request_timeout)）；compose 的 `UWSGI_*` 在新版（granian）沒有作用；wikidata 在舊版啟動時 403、資訊框整個不能用（新版待確認）。
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

## 架構審視與滾動修正（2026-10-12 起，/goal 進行中；進度見區塊內「進度」）

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
  - ✅ M3 Discord 退出技術層與服務層（第 2 項，10-13 完成、待 commit）：守衛「技術層與服務層不可 import discord」＋`sticker_cache`、`context_retriever` 改掉 discord import；`llm/ambient`、`llm/storage` 的功能層模組留在原地（使用者 10-13 定案不搬，見下方「M3 第 2 步」）。
  - ▶ M4 超大函式（第 5 項，10-13 進行中）：✅ M4a `on_ready` 剩登記（`7a369b6`，連拆備援萃取）→ ✅ M4b `_handle_askai_request` 拆四段（`693eaf1`）→ ✅ M4c `_run_one_ambient_pass` 拆六段 → ✅ M4d `_retrieve_rag_context_impl` 拆四段（兩個合一個 commit `95c7449`，字典 `ee6c19d`）；先補測試再拆，行為不變。**M4 完成**（重啟後生效）。
  - ✅ M5 設定與狀態（第 6 項，10-14 完成，`f3798bf`）：Q1 `sys_settings/paths.py`（寫死 `/app`、`__file__` 往上數、相對路徑三種寫法全收）；Q2 `item_prices` 單一存取點；Q3 定案 (a) 只統一讀寫機制 `utils/runtime_file`，不匯 StateDB、檔案不動。
  - M6 套件撞名（第 7 項）：共用的 `tg_config.normalize_channel_identifier`、`media_download` 的時限常數抽到 shared 套件；scraper 內部 `services`／`utils` 改名；要重啟 scraper、telegram-scraper。
  - M7 測試與工具鏈（第 8 項）：M7a 三個 requirements 釘版本（從執行中的容器 `pip freeze` 取）、加 ruff＋pyright basic 設定與 `make check`；M7b 啟動 gate 只跑守衛＋import 解析＋設定載入，完整測試改成手動／CI；M7c CI 依 Q4。
  - M8 錯誤邊界（第 9 項）：守衛擋 llm／services 內層的裸 except，現有 624 處列 allowlist 當 ratchet，只准減不准增；逐步清。
  - M9 LLM 背景工作拆 worker 行程（第 3 項）：先寫設計（哪些工作搬、怎麼拿 Discord 權限、排程誰管）再討論，最後做。
  - M10（原第 11 項）文件拆「現況／紀錄」：最後、可不做。
- **圖解頁**：`架構修正計畫`（使用者私人 artifact，連結在 `doc/interview/README.md`）：分層與「Discord 接入」、CI 的用意與架構、里程碑進度表；之後每個里程碑完成就更新。
- **待重新決定的清單（10-13 列給使用者；/goal 期間照「建議」做，標 ★ 的不碰）**：
  - 架構：Q3 Discord 接入 → 建議 (a) 搬 `llm/ambient`、`llm/storage` 的 Discord 接入到 services，llm 禁 discord＋守衛。Q4 CI → 建議 GitLab 共用 runner，先寫 `.gitlab-ci.yml` 與本機 `make check`，**不推送**。M5 runtime JSON → **已定案 (a) 只統一讀寫機制（`utils/runtime_file`），不匯 StateDB、檔案不動**；`/app/` 路徑已改成 `sys_settings/paths`。M6 套件撞名 → 建議「統一以 `src` 為根」：scraper、telegram-scraper 容器也掛 `./src:/app`、以套件路徑啟動與 import，共用的（`tg_config.normalize_channel_identifier`、媒體時限常數）放 `utils/`；代價：改 compose、重啟三個容器、相對路徑（media、session）要確認。M7b gate 瘦身 → 只跑守衛＋import 解析＋設定載入，完整測試由 `make check` 與 CI 跑。M9、M10 → 最後、先討論設計。★ `/anonymous`、test_commands → 使用者說先不管。
  - /askai 與搜尋（產品行為，★ /goal 不動，最後再決定）：openmeteo `timeout: 4.0`（建議加；`searxng/` 是使用者的檔）、天氣查不到預報（先觀察）、股價（建議加台股類型）、W5 關鍵字模式（跑一週再刪）、W6 新聞一週限制（等評估集）、輪數與全文長度（累積一週）、縮短思考（先用考卷確認）、向量那路改用原句與閒置後第一次搜尋慢（先量）、Agent 評估三題：放寬輪數（第 3 輪只准 fetch，面試後用新題目驗收）、工具說明加「不用加遊戲名稱」、**對話逾時不重試＋回答長度上限（建議併進 /goal，穩定性不是調分數）**、回答判讀 31／42 待抽看（q05、q31、q36、q41）。
  - 其他：推 GitHub＋英文 README（面試前推；9 個 commit 未推送）、備份分支 4 條（推送後刪）、爬蟲 `updated_at`、`.gitignore` 的 `staged_diff.txt`（可刪）與 `monitored_channels.json`（先留）、字典 4 筆可疑描述、`it_comfyui_image.py` 說明矛盾、AGENTS 收工加「字典另外 commit」（建議加）。交易／商品舊的 TR-Q14、TR-Q24、價格 0、BH-Q6、隔離區 grill 兩輪不在範圍。
- **/goal 運作規則（10-13 提給使用者）**：①醒著時每個 commit 前停、休息時不停；每個 commit 獨立、訊息照規則；②里程碑結束列「要重啟的容器＋指令」，使用者有空就重啟（避開 00:00、04:00～07:30；最後一批 10/17 前）；③不刪不覆寫任何資料檔、不碰 `searxng/`、不推送；④要使用者才知道的事先做能做的、最後一併問；⑤★ 的產品行為不在 /goal 內動（逾時不重試那條待使用者點頭）。
- **寫檔注意（10-13 00:4x）**：這段 00:1x 寫過一次、程式也印了成功，之後檔案卻回到 17:51 的內容（mtime 沒變），同一時間使用者在 IDE 開著這個檔——疑似編輯器用舊緩衝蓋回去。之後寫完要重讀驗證；使用者開著的檔，改完提醒他重新載入。
- **進度（10-13）**：M1、M2a 已上線（10-13 11:20 重啟，gate 1,426 全過、上線後無 ERROR）；M2b 退回、M2c 取消；M2d 完成、等併進 M3 的 commit；節點 tag `checkpoint-20261013-m2a`（M1＋M2a）；M3 完成（10-13，等 commit；要重啟才生效的只有 `sticker_cache` 的拆法，和下一批一起）。下一個：M4 超大函式（先補測試再拆）。每個 commit 的內容、突變、使用者問答等過程紀錄在 `TODO-completed.md`「架構審視：M1、M2 的過程紀錄（歸檔 2026-10-13）」。
- **分層定案（10-13，使用者確認方向）**：09-29 的資料夾定義不變——`services/`＝服務、`llm_service.py` 留在 `services/`；`llm/`＝LLM 相關技術（組裝、優化、橋接、RAG），AI 功能也在裡面；MCP 殼放 `llm/`（橋接）。要守的方向寫到**子資料夾／模組**，不是頂層資料夾：基礎（utils、sys_settings、settings、constants，層內可互 import）← 技術 ← 服務 ← 功能 ← 介面（commands、discord_bot、music），import 只能同層或往下（函式內的也算、`if TYPE_CHECKING:` 不算）；表在 `test/test_layering.py` 的 `LAYERS`，規則在 AGENTS「程式碼」。用這把尺掃 148 個模組：0 條往上、3 條跨容器（`telegram_scraper`，M6 清）。「服務」兩義：部署單位（Lemonade、search-mcp）與程式裡的一層（`LLMService`：把一種能力包成入口給功能用），兩者同時成立。llm 要叫搜尋不必 import services——下層定義介面（`ToolRunner`、`run_due_loop(tick)`、persona 工具可注入的 `fetch`），上層注入實作。M2b 的錯：提案時沒先對照 09-29 定案、把頂層資料夾當成層。
- **M3 第 1 步做完、等使用者看（10-13 12:5x；未 commit）**：先做兩種做法都要的部分。①守衛 `test_layering` 加一條：**技術層與服務層不可 import discord**（`if TYPE_CHECKING:` 裡的不算），基礎層只有 `DISCORD_HELPERS_IN_BASE` 列的 6 個 Discord 工具（`utils.utils`、`discord_content`、`discord_threads`、`dm_notifier`、`panel_bump`、`channel_registry`）可以、每個寫理由，不再 import 的要拿掉（殭屍檢查）；功能層與介面層是 Discord 應用本身，不限制。掃出來只有兩處違規，都已修：②`llm/preprocess/sticker_cache`（技術層）——原本自己向每個伺服器 `fetch_stickers`，拆成 `discord_bot` 的 `on_ready` 抓清單、快取只 `remember(stickers)`（鴨子型別），型別註解進 `TYPE_CHECKING`，模組說明改成新格式；③`llm/retrievers/context_retriever`（服務層）——`import discord` 只剩型別註解，`isinstance(channel, (TextChannel, Thread))` 改看能力（有 `guild` 且有 `history`）。行為差異只有一個：語音頻道的文字聊天以前拿不到脈絡、現在拿得到；私訊、分類、論壇照舊不抓。測試：`test_layering` +1、`test_emoji_autofill` +1、新 `test_context_retriever_channel` 3 項；完整 1,437 項全過（容器副本）；10 個突變全紅（G1 技術層檔頭 import、G2 服務層函式內 import、G3 基礎層非工具 import、G4 例外殭屍、G5 TYPE_CHECKING 當真、S1／S2 remember 不記／數錯、C1 不看 guild、C2 不看 history——第一版只看回傳是空的沒抓到，因為讀失敗被 except 接住也會回空，改成「不能有 WARNING」才紅、C3 把 import 放回去）。M2d 的 `test_layering.py` 與 AGENTS 分層段一起進這個 commit。線上不用急著重啟（新舊程式都能跑；`sticker_cache` 的拆法要重啟才生效，和 M3 其餘一批）。**突變腳本的坑**：第一版 `docker cp` 整個工作目錄的 `src`（含 30 GB 的 Telegram 媒體）進容器、卡了 16 分鐘；改成和 `snap_test.sh` 一樣先把工作目錄寫成暫時的 git tree（只有追蹤的檔）、`git archive` 再疊到副本，一個突變約 4 秒。
- **M3 第 2 步要使用者決定（10-13 提出；M2b 之後才看清楚，所以搬檔前先問）**：Q3 原建議 (a) 把 `llm/ambient/*`、`llm/storage/store_chat`、`raw_message_store` 搬到 `services/`，讓 `llm/` 一行都不 import discord。但 09-29 的定義明說「AI 功能本身（插話、日記、人格萃取、agent）也在 llm」，M2d 的五層表也把它們標成 llm 裡的功能層，而功能層本來就是 Discord 應用、守衛不擋它們 import discord。第 1 步的守衛已經保證「技術層與服務層不認 discord」——第 2 項發現要的「LLM 技術能離開 Discord 測試、重用」已經成立。選項：(a) 照原建議搬：7 個檔、約 20 處 import、測試的 mock 字串、AGENTS 表、記憶都要改，要重啟；收益只剩 `llm/` 資料夾字面上零 discord，而且和 09-29 定義相反／(a′) **不搬**：功能層模組留在 `llm/ambient`、`llm/storage`，照守衛允許 import discord，M3 到第 1 步就算完成／(b) 留原地、改收純資料物件：`ambient_reply` 1,479 行幾乎重寫，面試前不做。**建議 (a′)**：和 09-29 定義一致、不動 7 個檔、守衛已達到第 2 項的目的。使用者沒回之前不動這 7 個檔。 **定案（使用者 10-13 13:0x「不搬」，先看過兩種做法各改哪裡、之後維護差在哪的對照表才選）**：(a′)。M3 到此完成：守衛保證技術層與服務層不認 Discord；功能層放在 `llm/` 還是 `services/` 是抽屜問題，照 09-29 定義留在 `llm/`。M3 的程式與 M2d 的守衛合成一個 commit，等使用者同意。
- **M3 已 commit（10-13 13:5x 使用者「commit」）：`d2d9dc8`**（守衛 `test_layering.py`、AGENTS 分層段、`sticker_cache`、`context_retriever`、`discord_bot`、`test_emoji_autofill`、新的 `test_context_retriever_channel`）。下一個 M4。
- **M4a 已 commit（10-13 16:3x 使用者「commit」）：`7a369b6`——`on_ready` 只剩登記＋拆掉備援萃取 ③＋定期迴圈共用**。使用者同時定案：不補手動萃取入口（看單人用 `/persona_agent_test`）、「精簡版」名稱維持（「確實是精簡後的資料」）；解釋這套機制時用「兩張表＋一個動作」講才通（A 表草稿紙、B 表答案卷、發布只抄證據跨 2 次對話的條目），已寫進回饋記憶。圖解頁 https://claude.ai/artifact/WxdETmZ8B9yHYut1g7gr5c 。使用者「M4 可以開始進行」→ 先做 on_ready；看到三個模組底下各多一份 `flush_loop` 問「為什麼」→ 三份幾乎一樣、違反共用元件規則，改成 `utils.background_tasks.periodic(seconds, job, name=)`（固定間隔做一件事、失敗記 WARNING 繼續），三個模組不再有迴圈；使用者「③ 已經跑一段時間了可以拆掉了嗎」→ PR-Q2 門檻已達到（精簡版 10-02～10-13 連續 12 晚 failed=0），唯讀抽 5 筆已發布的精簡版看過（68 筆 auto_personality、64 筆是精簡版；抽到的都是口頭禪、表情偏好、互動方式，沒有規則擋的類別），使用者「一起改吧」→ 併進這個 commit。改了什麼：①`discord_bot.py` 929 → 718 行，`on_ready` 332 → 20 行，只剩順序、每步一行；維護編排搬成 `llm/persona/daily_maintenance.py`（功能層：`run_once` 四步、`schedule_loop`、`catch_up_if_missed`、`last_scheduled_run`／`next_run`；自己有「同一時間只跑一輪」的旗標，接替原本 ③ 兼任的鎖）；日記排程搬成 `ambient_diary.schedule_loop`；三個定期寫入由 on_ready 用 `periodic` 掛；`_start_once` 統一 reconnect 不重掛（屬性名不變）。②拆 ③：`personality_extractor.py` 669 → 174 行（刪 `run_personality_extraction`、`_run_personality_extraction_impl`、`extract_personalities`、`save_personality_results`、鎖與常數；留 `refresh_emoji_dictionary`、`get_last_extraction_time`、`load_description_rules`、`_load_extract_prompts`、`_get_db_conn`、`_clean_text_for_extraction`；檔名沿用、說明改新格式）；`llm_commands.py` 1,554 → 1,119 行（刪 `/personality_extract`、`/personality_extract_status`、結果分頁與狀態畫面、`register_scheduled_result`；留 `/persona_agent_test`、`/ai_diary`）；`publish.py` 刪 `production_skip_list`、`split_uncovered`，說明裡的 ③ 改掉；`llm_settings.py` 兩段說明改掉。③四個模組說明改新格式；`LAYERS` 登記 `llm.persona.daily_maintenance` 為功能層；「定時排程」規則例外從 `discord_bot.py` 換成 `daily_maintenance.py`、`ambient_diary.py`；AGENTS 背景任務列加 `periodic`。**行為差異**：(a) 04:00 維護變四步（emoji 字典 → 招牌梗衰減 → persona agent → 發布精簡版），精簡版是空的 4 人停在最後一版描述、新成員等 agent 寫出條目才有描述（PR-Q3）；(b) 兩個手動萃取指令消失（PR-Q4），重啟時同步指令清單才會從 Discord 拿掉；(c) 日記排程改成和另外四個迴圈一起掛、在建表之前（先睡 90 秒，順序不影響）；(d) 補跑檢查不變（看 `last_extracted_at` 最大值，發布每晚寫）。**要重啟才生效**（on_ready 與 04:00 那條路都在啟動時載入），避開 04:00～07:30；還沒重啟前舊程式照舊跑五步、不會壞。測試：新 `test_daily_maintenance` 11 項（四步順序、每步失敗不擋後面、④ 失敗不往外丟、agent 關掉只跳 ③、兩輪不重疊且跑完能再跑、沒 guild 不做、04:00 跨日、補跑三種）、`test_background_tasks` +1（periodic）；刪 ③ 的測試 3 個類別與 1 個 prompt 佔位符測試；完整 1,440 項全過（容器副本）；13 個突變全紅（D1 ③④對調、D2 ①不接例外、D3 agent 開關失效、D4 不記正在跑、D5 跑完不放開、D6／D7 04:00 邊界、D8 沒紀錄不補跑、D9 ④失敗往外丟、P1 periodic 不接例外、P2 睡錯長度、G1 新模組沒登記層級、G2 守衛例外少列；D4、D9 第一版沒乾淨地抓到——D4 的第二輪會卡在 gate 上等到 timeout、D9 沒有測 ④ 失敗，補了測試才紅）。`on_ready` 本身沒有單元測試（`discord_bot.py` import 時就建 bot、讀 token），靠啟動時實際跑。下一步：使用者同意 → commit → M4b `_handle_askai_request`。
- **M4b 已 commit（10-13 18:5x 使用者「commit」）：`693eaf1`——`_handle_askai_request` 468 行拆成四段**（字典 `7aeadf9`）。使用者看到 `_AskaiInputs` 問是什麼 → 說明是第 1 段的產出、三類欄位；`model`／`think`／`interaction` 三個「後面才填回」的欄位使用者沒要求改。先寫特徵測試再拆：新 `test/test_askai_flow.py` 11 項，用假的互動、檢索、網搜、情報、模型服務把整段跑一遍，守的是給模型的東西怎麼組（<@id> 換名字錨點、聊天紀錄逐行、bot 回覆另一段、人物卡三路分流、名字對照接尾、被 @ 沒卡的提示）、有圖時縮上下文與附圖網址、圖不合格不叫模型、keyword 先查塞 web_context／tool 把工具交給工具輪、三種取消（叫模型前、生成途中、底層連帶）、三份記錄、送出與「已回覆」——先對舊程式跑全綠，拆完照樣全綠。拆法（同一個檔，不開新模組；拆檔是 P2 的題目）：`_handle_askai_request` 43 行只排順序 → 第 1 段 `_askai_gather`（120 行，收集上下文，回 `_AskaiInputs` 資料類）→ 第 2 段 `_askai_generate`（101 行，工具輪與取消處理）→ 第 3 段 `_askai_record`（70 行，三份紀錄）→ 第 4 段 `_askai_send`（24 行）；純函式另拆出 `_context_limits`、`_resolve_mentions`、`_start_web_search`、`_collect_web`、`_participant_ids`、`_split_persona`、`_mention_hints`、`_asker_profile_text`。既有三個「讀原始碼比字串」的測試（`test_intel_search_client`、`test_tweet_context`、`test_external_emoji`）的字串都保留原寫法，沒改測試。行為不變；唯一順序差異是 system prompt 改在送出「思考中」之後才讀（讀的是檔案，沒影響）。`llm_commands.py` 1,119 → 1,222 行（多的是說明與資料類）。測試：完整 1,451 項全過（容器副本）；13 個突變全紅（A1 被 @ 的卡當成其餘、A2 有圖不縮、A3 參與者順序、A4 不檢查取消、A5 名字對照沒接、A6 沒卡沒提示、A7 不附圖網址、A8 錯誤類型記錯、A9 取消後照走——第一版沒抓到：取消後會走到「底層連帶取消」那條路，使用者會看到「這次沒有順利回答」又記一筆 ERROR，測試改成取消不准有 ERROR log 與失敗訊息才紅、A10 keyword 查到也不給、A11 tool 不交工具、A12 連帶取消沒接住、A13 發問者的卡跑進其餘）。突變腳本第一版用 shell 字串拼 Python、沒套上就跑測試、13 個全「綠」——改成清單檔套不上就算失敗、不算綠。
- **M4c 做完等使用者看（10-13 19:xx，未 commit）：`_run_one_ambient_pass` 354 行拆六段**。先寫特徵測試再拆：新 `test/test_ambient_pass_flow.py` 32 項（假的模型、Discord、召回；只有 `ambient_reply` 是真的），守的是：哪些情況不勞動模型（整段 burst 沒料、冷卻只擋自發、接續不吃冷卻但吃每小時上限、滾動一小時歸零、前景活躍時自發與接續讓位但被點名照回、降溫字眼、鉤子否決只在自發、鉤子看得到觸發訊息、純圖下載失敗沒東西可接但被點名仍回）、給模型的東西怎麼包（被點名帶發話者名字錨點與原文；自發把觸發訊息編號接在脈絡末尾、帶中性提示與鉤子訊號；純圖變佔位行；被回覆訊息截 200 字並補 X 貼文描述與圖、圖總數受上限；人物卡＋偏好＋招牌梗是同一段；記仇中的人點名才疊心情；模型與逾時）、模型說了什麼送到哪（[PASS] 各種寫法不送但記 debug、錯誤記類型且不計額度、被點名 reply 不 @ 人、原訊息刪了退回頻道且沒有 WARNING、自發 reply 模型選的那一則／選觸發訊息本身／沒編號裸送／錨點失效裸送、送出失敗什麼都不記、錨點是記仇中的人整則不送）、送出後的記帳（只有自發吃冷卻與額度、接續只吃額度、武裝接續與 chain 歸零規則、互動紀錄的種類與探索旗標）——先對舊程式跑全綠，拆完照樣全綠。拆法（同一個檔）：`_run_one_ambient_pass` 44 行只排順序 → `_pass_gates`（43 行，零成本閘門，回 `_Gate`：計數器、記仇名單）→ `_gather_inputs`（108 行，回 `_Inputs` 資料類；途中的降溫、鉤子、「沒東西可接」擋下回 None；最新一則怎麼包另拆 `_frame_latest` 40 行）→ `_generate`（60 行，叫模型、判讀 outcome、寫 debug 檔）→ `_react_to_insult`（9 行）或 `_deliver`（41 行，回送出的訊息與錨點；錨點是記仇中的人不送）→ `_bookkeep`（36 行，冷卻額度、武裝接續、log）→ 原有 `_record_ambient_interaction`。每小時窗口歸零原本寫兩遍，抽成 `_roll_hour`。行為不變；`ambient_reply.py` 1,480 → 1,560 行（多的是說明與資料類），模組說明改新格式。兩個「讀原始碼比字串」的測試（`test_tweet_context`、`test_external_emoji`）原本看 `_run_one_ambient_pass` 有沒有呼叫 `_media_context`，改成看 `_gather_inputs`；`test_ambient_natural` 看主流程有沒有 `stripped = _message_text(message)` 的那條沒改（還在主流程）。測試：完整 1,482 項全過（容器副本）；26 個突變全紅（C1 冷卻失效、C2 接續不看每小時上限、C3 窗口不歸零、C4 記仇中的人的話照接、C5 降溫失效、C6 鉤子否決失效、C7 鉤子看不到觸發訊息、C8 沒東西也叫模型、C9 被回覆不截、C10 圖不設上限、C11 不疊心情、C12 被點名不帶發話者、C13 觸發訊息沒登記編號、C14 [INSULT] 當文字送、C15 錨點是記仇中的人照送、C16 原訊息刪了不退回頻道、C17 自發不吃額度、C18 接續吃冷卻、C19 接續 chain 歸零、C20 探索旗標丟掉、C21 接續時也按表情記仇、C22 debug 結果記錯、C23 錯誤記成 pass、C24 錨點作者記錯、C25 pass／error 也送、C26 接續不讓位）。第一版新加的「模型選觸發訊息本身」測試在正確程式上也紅（假的 `_fetch_recent` 沒把第一則放進 thread_map，編號對不上）→ 修測試後 C13 才算抓到；其餘 25 個原本就各有另一個測試抓到。使用者 10-14 問「M5 什麼時候才能作」「M4d 跟 M4c 一起 commit 不行嗎」→ 說明與每個 commit 一件事的原則有牴觸，折衷：M4d 先做、兩個一起停下來看、分兩個 commit 連著打；使用者「先作」。
- **M4d 做完等使用者看（10-14 03:xx，未 commit）：`_retrieve_rag_context_impl` 320 行拆四段**（`llm/retrievers/context_retriever.py`，人物卡的檢索）。先寫特徵測試再拆：新 `test/test_rag_profile_flow.py` 18 項（假的 DB 連線依 SQL 分三路回資料並記參數、假的向量索引、卡片產生器是真的），守的是：空問句或沒 guild 不查、來源關掉時 meta 標 enabled=False、本人那一路要有發問者才查且參數是三個同 id、在場者那一路去重／去 0／最多 5 人、別名那一路有片段或有提到的人才查且沒對到 id 時用 0、<@id> 由呼叫端給或自己重抽、Discord 名字對到的人進別名查詢、三路照本人→在場→別名的順序並各自計數、一路壞了其他照常且記 WARNING、SQL 的 metadata 是 JSON 字串也能讀、語意檢索撈 max(top_k×2, 候選池÷2) 且只收本伺服器、ref_doc_id 從 node 拿、向量壞了保留 SQL、同一份文件兩路都撈到留精度高的、排序本人→別名→語意再新的在前、三種對到誰的計數、卡片數受 top_k 與上限 3、多於額度裁到最後幾張（安全網）、沒撈到回空——先對舊程式跑全綠（三處是我預期寫錯，程式是基準），拆完照樣全綠。拆法（同一個檔）：`_retrieve_rag_context_impl` 68 行只排順序與 log → `_parse_profile_question`（19 行，回 `_ProfileQuestion`：誰在問、提到誰、在場誰）→ `_collect_profile_candidates`（55 行，三路 SQL 共用 `_sql_profile_route`＋`_rows_to_docs`，原本三段幾乎相同的連線、轉列、接例外各寫一遍；語意那一路 `_vector_profile_route` 32 行）→ `_dedup_profile_docs`（19 行，優先表抽成模組常數）→ `_count_profile_matches`（12 行）→ `_profile_cards_context`（25 行）。行為不變；模組說明改新格式（原本只有一行）。**順手發現、沒改**：去重後的排序表沒有 `sql_participant`，在場者那一路的文件排在語意檢索之後（卡片產生器自己會依來源加分，所以卡片順序沒受影響，只是交給它的候選順序怪）；裁切那段在現況走不到（卡片產生器已限量），留著當安全網。兩者都寫進測試註解與模組說明的「例外與決策」，要不要改等 /goal 結束一起決定。測試：完整 1,500 項（容器副本；第一輪 `test_import_resolution` 紅——測試 logger 取名 `test.rag` 被當成模組路徑，改名後綠）；22 個突變全紅（R1 空問句照查、R2 來源關掉不標、R3 沒發問者也查本人、R4 在場者不限 5 人、R5 只有別名片段不查、R6 Discord 名字對到的人沒進查詢、R7 無視呼叫端給的 <@id>、R8 一路壞了往外丟、R9 不解 JSON 字串、R10 不過濾伺服器、R11 ref_doc_id 不從 node 拿、R12 向量壞了往外丟、R13 去重留錯來源、R14 不去重、R15 舊的在前、R16 不算寫給本人的、R17 卡片不設上限 3、R18 不裁——第一版沒抓到，因為正常走不到，補了直接餵超量卡片的測試才紅、R19 在場者不計數、R20 語意檢索池不放寬、R21 來源標錯、R22 在場人數不記）。使用者 10-14 04:xx「可不可以先測試然後解釋修改邏輯」→ 正式容器 1,501 全過，用「一條流程切成幾段、主函式只排順序」解釋；「所以功能不變只是重構嗎」→ 是；「那一起 commit 不就好了」→ 依使用者決定合成一個 commit `95c7449`（字典 `ee6c19d`）。下一步：M5。
- **M5 第 1 輪（10-14 04:xx，盤點＋提問，未動 code）**。盤點（唯讀）：寫死 `/app/…` 的路徑 38 處（`sys_settings/llm_settings.py` 等 pydantic 預設 20 處、模組常數 10 處、指令層 5 處、scripts 2 處、`fb_scraper_service` 用 `/.dockerenv` 判斷）；`item_prices.json` 在 `user_commands.py` 兩處與 `trade_commands.py` 一處各自開檔讀寫，680 bytes；runtime JSON 9 個都在 `settings/`，最大 1.9 KB——其中 `article_runtime.json`（暴雷關鍵字、排除分類）與 `sys_settings/llm_runtime_config.json`（模型選擇）是「人手改的設定」，其餘 7 個（面板訊息 id ×4、music、rollcall、intro_submission、quarantine threads）是「程式寫的狀態」；讀寫方式各自一套（`base_monitor` 自己 5 分鐘 TTL 快取、`rollcall_service` 自己 json.load/dump、`management_commands` 相對路徑 `settings/...`）。StateDB（`services/state_db.py`，aiosqlite，`sent_articles.db`）已有 7 張表與 `migrate_from_json`。提問三題（附建議）：Q1 base path——建議加 `sys_settings/paths.py`：`APP_ROOT`（環境變數 `APP_ROOT`，預設 `/app`）與 `SETTINGS_DIR`、`PROMPTS_DIR`、`SCRAPER_DIR`，38 處改引用，守衛擋新的 `"/app/` 字面。Q2 item_prices——建議抽 `services/community/item_prices.py`（`get_user_prices`／`set_user_prices`，讀走 `hot_files.read_json`、寫走 `safe_write`），三處改呼叫；檔案不搬不刪。Q3 runtime JSON——選項 (a) 只統一讀寫機制：7 個狀態檔都改走同一個小工具（讀 `hot_files`、寫 `safe_write` 加備份），檔案與格式不動，不需要資料遷移與同意流程；(b) 7 個狀態檔逐個匯入 StateDB 新表 `runtime_state(name, json)`，只匯入不刪舊檔；(c) 不做。**建議 (a)**：檔案都不到 2 KB、各自一份是機制重複的問題不是容量問題，(a) 零資料風險就把機制收成一份；(b) 多一次遷移與 7 次同意、收益是少 7 個檔。兩個設定檔（article、llm_runtime）維持熱讀檔不動。等使用者回。使用者「可不可以畫圖比較前後、容器這樣用有什麼問題，還是問題在寫死」→ 回答：容器沒問題（`./src:/app` 掛載、`/app/...` 找得到），問題是同一個位置三種寫法（寫死、`__file__` 往上數、相對路徑）散在 38 處，相對路徑那 3 處換啟動目錄就錯；嚴重度是剩下里程碑裡最低的。圖解（現況、Q1／Q2 改前改後、Q3 三選項）原本另開一頁，使用者要求併進架構修正計畫頁第 4 段、刪掉多的那頁（已刪）。使用者「那請進行修正」→ 三題照建議做，Q1 進行中。
- **M5 三題做完等使用者看（10-14 06:xx，未 commit）**。途中使用者要求：commit 訊息不寫 M1／Q3 這類代碼（已寫進記憶 `commit-no-milestone-codes`），並改掉之前 7 個帶代碼的訊息 → 用 filter-branch 改寫未推送的 25 個 commit 中 7 個訊息（含 `c2b63a4` body 的「PR-Q2 to Q4」）、13 個 hash 跟著變，交接檔與歸檔裡 24 處 hash 已換新（`2020185`）。**Q1 路徑**：新 `sys_settings/paths.py`（`APP_ROOT` 讀環境變數、預設 `/app`；`SETTINGS_DIR`／`PROMPTS_DIR`／`SYS_SETTINGS_DIR`／`SCRAPER_DIR`／`TELEGRAM_SCRAPER_DIR`／`STATIC_DIR`；`settings_file()`／`prompt_file()`），33 處寫死 `/app/…` 改引用（pydantic 預設 20 處、模組常數、指令層；`TelegramRenderAdapter` 預設 `APP_ROOT`）；順手把同類的另兩種寫法也收掉——`Path(__file__).parents[n]` 往上數 8 處（switches、logger_config、base_monitor、event_scheduler、rollcall、quarantine ×2、shop_service）、相對路徑 9 處（面板檔 ×3、music ×2、periodic_reminder 預設、monitored_channels、config.json ×3→`utils.utils.CONFIG_FILE`）。守衛：`test_shared_conventions` 新規則「專案根目錄的路徑」走 AST finder（字串在 regex 比對前會被遮掉，第一版用 pattern 寫、突變沒抓到才發現）；allowed：`paths.py`、爬蟲兩個容器、`scripts/`、`test/`。新 `test_paths` 3 項。**Q2 價格檔**：新 `services/community/item_prices.py`（`all_prices`／`user_prices`／`set_user_prices`，讀走熱讀檔、寫走 `runtime_file.save`、只換那位賣家），`user_commands` 兩處讀與 `trade_commands` 讀＋寫改呼叫它；寫失敗現在會告知使用者「價格沒有存成功」（原本直接覆寫、失敗沒處理）。新 `test_item_prices` 6 項。**Q3 狀態檔 (a)**：發現 `utils/panel_bump.py` 早有 `load_runtime`／`update_runtime`、7 個檔中 4 個已走它 → 抽成正式共用元件 `utils/runtime_file.py`（`load`／`save`／`update`；讀 `hot_files.read_parsed`、寫 `safe_write.replace_text` 加每日備份到 `/logs/runtime_backup`，環境變數 `RUNTIME_BACKUP_DIR` 可換），`panel_bump` 的兩個函式改成轉呼叫（寫失敗照舊吞掉記 log）；接上剩下三個：自介投稿（`management_commands` 的 load/save）、點名（`rollcall_service` 的 `_load`／`save`，`_get_config` 改走 `ChannelConfig.load_config`）、音樂（`announcer`／`config`／`player` 五處直接 open）。守衛新規則「狀態 JSON 的讀寫」：open／read_text／write_text 的對象文字帶 runtime 或 PRICES 就擋（變數叫 `path` 這種繞得過，是 tripwire 不是證明）；allowed：`runtime_file.py`、`base_monitor`／`ptt_monitor`（人手改的 article_runtime 走自己的 5 分鐘快取）、爬蟲、scripts、test。新 `test_runtime_file` 6 項。**測試副作用修正**：第一輪跑測試時 `panel_bump` 測試用暫存路徑寫檔、備份卻進了正式 `/logs/runtime_backup/`（3 個小檔：`runtime_2026-10-14.json`、`panel_runtime_2026-10-14.json`、`x_2026-10-14.json`，都是測試資料）→ 比照 GPU 鎖檔，`test/__init__.py` 在 unittest 模式把 `RUNTIME_BACKUP_DIR` 指到暫存目錄；那 3 個檔在 /logs 下、依規則等使用者同意再刪（指令：`rm /home/jason/discord/logs/runtime_backup/{runtime,panel_runtime,x}_2026-10-14.json`）。**行為差異**：容器裡路徑值完全相同；狀態檔寫入從直接覆寫變成暫存檔換名＋每日備份；價格寫失敗會回訊息。要重啟才生效（和 M3、M4 一批）。AGENTS 共用元件表加三列。
  測試：完整 1,517 項全過（容器副本 `APP_ROOT=/tmp/snap` 與正式容器各跑一次）。`test_data_file_paths` 原本用「測試檔所在位置」當基準、在副本裡會紅 → 改成以 `APP_ROOT` 為基準（它守的是「資料檔位置不隨程式檔搬動而變」，現在位置由 APP_ROOT 決定，前提換了），`state_db.DEFAULT_DB_PATH` 與 `music/ytdl.CACHE_DIR` 也從 `__file__` 改成 APP_ROOT 推；`services/search/eval/evaluate.py` 的 `EVAL_DIR`（報告放自己旁邊）是唯一留下的 `__file__` 用法。13 個突變：12 紅、1 等價（S3 `_parse` 的 dict 檢查和 `load` 重複 → 拿掉重複的那份）；S4 備份目錄不看環境變數、S5 寫失敗留暫存檔，第一版沒抓到，補了兩個測試才紅（S1 回傳不是複本、S2 update 蓋掉其他欄位、P1 設價蓋掉別的賣家、P2 讀不到某賣家、P3 價格表不是複本、A1 APP_ROOT 不看環境變數、A2 prompts 目錄算錯、G1 panel_bump 自己讀檔、G2 守衛漏抓 open 狀態檔、G3 守衛漏抓寫死 /app）。第一版「專案根目錄」守衛用 regex pattern 寫、突變全綠才發現字串在比對前就被遮掉，改成 AST finder。改動 36 個檔。下一步：使用者看過 → 一個 commit（功能描述、不寫代碼）→ M6。
- **註解裡的代碼清掉（10-14 07:xx，未 commit）**。使用者看 `rollcall_service.save` 問「有沒有考慮編碼」→ 寫 `ensure_ascii=False`＋`encoding=utf-8`、讀 `utf-8`、備份是位元組複製，實際寫一筆含中文與 emoji 讀回確認是明碼；接著使用者「註解不要寫 M5 沒人懂，commit 與程式內都一樣，永久記住、不限此專案」→ 記憶 `no-milestone-codes-anywhere`（原 commit 那條擴大）＋新建全域 `~/.claude/CLAUDE.md` 一條規則（所有專案都載入）。掃 `src/` 所有 `.py`：里程碑（M1～M7、M2a、M4d）與題號（TR-Q、SW-Q、TF-Q、UC-Q、RB-Q、PR-Q）共 83 處、44 個檔，全部換成功能描述或只留日期（例：「（使用者 2026-10-04，TR-Q40）」→「（使用者 2026-10-04）」、「M7 精簡版」→「精簡版」、「M3 的驗證層」→「寫入前的驗證層」、「見交接檔架構審視區塊 M5」→「見交接檔 `architecture-review-2026-10`（設定與狀態）」）；`scripts/bench_ptt_comment_lookup.py` 的 Q1～Q5 是查詢編號不是題號，沒動。交接檔與歸檔仍用代碼（追蹤文件本身）。正式容器完整測試 1,517 全過。這批和 M5 的程式一起等使用者看；commit 時分開：M5 一個、註解清理一個（都只寫功能，不寫代碼）。
- **出處標記與「見交接檔」也清掉（10-14 07:xx，未 commit）**。使用者看 `paths.py` 的「例外與決策：見交接檔 `architecture-review-2026-10`」→「交接檔也看不到啊，要嘛有地方寫、要嘛這邊寫清楚、要嘛不寫」；再看 `shop_commands.py` 的「（使用者 2026-10-03）」→「這也很沒意義」。原則收成一句：**註解只寫理由；誰決定、哪天決定、代碼、「見交接檔」都不寫；理由寫得下就寫原地，寫不下就不寫；只在文件裡維護的數字、樣本可以寫「記在哪」**。寫進 AGENTS「程式碼」段與模組說明第 5 條（原本寫「決策理由與日期寫交接檔、這裡只留區塊 id」，整個反過來）、記憶 `no-milestone-codes-anywhere` 與 `feedback-module-docstring-format`、全域 `~/.claude/CLAUDE.md`。程式：約 90 處「（使用者 日期）」出處——有引述理由的換成理由本身（「使用者 10-08：『每個訊息應該都要被檢查過』」→「每則訊息都要被檢查過」），只有日期的刪掉；20 處「見交接檔」指標——新格式模組說明的「例外與決策」改成在原地寫結論與理由（`paths`：為什麼用環境變數加預設而不是從程式檔位置推；`runtime_file`：為什麼留 JSON 不搬 SQLite、備份為什麼放 /logs；`item_prices`：寫失敗為什麼往外丟；`context_retriever`：排序怪為什麼刻意沒改；`store_chat`：放回緩衝與上限 1,000 的取捨；`daily_maintenance`：為什麼從 on_ready 搬出來、精簡版空的人為什麼寧可空著；`ambient_memory`：只記本人中性偏好的原因），其餘純指標刪掉；留下 3 處是「評估數字／樣本記在哪個區塊」的事實陳述（`search/__init__`、`eval/evaluate`、`it_telegram_filter`）。`agent/__init__` 順手改掉過時的「與 personality_extractor 並行」。正式容器完整測試 1,517 全過。暫存區裡有 18 個已暫存的檔，我當成過時快照 `git reset` 掉了——**那是使用者邊看邊暫存的紀錄**，不該動；工作目錄沒受影響。
- **設定與狀態收攏＋註解清理已 commit（10-14 10:4x）**：使用者「git staged 的都是我看過的，你也覺得沒問題就 commit」。先查 git 物件的寫入時間確認暫存區狀態：我 `git reset` 的是使用者 09:04～09:25 暫存的 18 個檔；使用者 09:56～10:25 又從頭把 91 個檔逐一看過並暫存（每個檔一個物件、依路徑順序、內容都等於工作目錄），所以我 reset 掉的那一輪他已自己重做，暫存區是完整的。已向使用者說明。使用者同時問一次性腳本的 `TelegramRenderAdapter(app_root=str(SRC_DIR))` 還要不要傳參數 → 不用（預設就是 `APP_ROOT`），拿掉；順手掃到還有 8 處 `"config.json"` 相對路徑（轉發服務 `MessageRouteResolver` 的預設、`discord_bot` 自動啟動的檢查、指令層四處傳 `config_file=`、腳本一處）與轉發服務的 `telegram_scraper/runtime_config.json` 預設，全部改成問 `paths`／`CONFIG_FILE`；這幾個檔是使用者看過之後又改的，commit 前列給他。正式容器 1,517 全過。依檔案分兩個 commit：有動到程式的 41 個檔 `f3798bf`（路徑、狀態檔、價格表、守衛、測試）、只動註解的 48 個檔 `14c92d4`（AST 去掉 docstring 後前後相同）；AGENTS 與交接檔另一個 commit。**要重啟才生效**（M3、M4、M5 一批；避開 04:00～07:30）。下一步：M6 套件撞名。
- **M5 收尾盤點（10-14 10:5x，使用者「先確認這次重構還有沒有漏掉的」，唯讀）**。Q2／Q3 沒漏：七個狀態檔的每一處讀寫都走 `runtime_file`（面板四個經 `panel_bump`），價格表只剩 `item_prices` 一個入口。Q1 漏掉同類型的另一個掛載點：`/logs` 在 bot 程式裡寫死 10 處（`logger_config.LOG_DIR`、`utils.ChannelConfig.BACKUP_DIR`、`runtime_file.DEFAULT_BACKUP_DIR`、`llm_settings` 的 6 個 prompt／回應 log 與字典備份路徑、`discord_bot` 啟動時列目錄）；兩個一次性腳本 `sys.path.insert(0, "/app")`（守衛放行 scripts/，但第三個腳本已用 `Path(__file__)` 推，寫法不一致）。順帶發現三處繞過「手改檔走 `hot_files`」規則的讀法（不是 M5 新造成、是 M2a 沒掃到）：`MessageRouteResolver` 自己 `json.loads` 讀 config.json（該走 `ChannelConfig.load_config`）；`base_monitor` 對 `article_runtime.json` 自己做 5 分鐘 TTL 快取、`ptt_monitor` 再讀一次（該走 `hot_files.read_json`，改了就生效）；`MessageRouteResolver`／`TelegramRenderAdapter` 每次呼叫都重讀 `telegram_scraper/runtime_config.json`。建議：(1) `paths` 加 `LOGS_DIR`（環境變數 `LOGS_DIR`，預設 `/logs`），10 處改引用、守衛連 `/logs` 一起擋；(2) 兩個腳本改 `Path(__file__)`；(3) 三處讀法改走 `hot_files`／`ChannelConfig`，`base_monitor` 的 TTL 快取拿掉；(4) `test_data_file_paths` 補釘 `switches.json`、`item_prices.json`。都小，合起來約 20 處；等使用者點頭再做（他剛看完 91 個檔）。
- **Q1 收尾做完等使用者看（10-14 11:xx，未 commit；使用者「先改 Q1 讓我看」）**：`paths` 加 `LOGS_DIR`（環境變數 `LOGS_DIR`，預設 `/logs`；是另一個掛載點，不跟著 `APP_ROOT` 走）；10 處 `/logs` 改引用（`logger_config.LOG_DIR`、`ChannelConfig.BACKUP_DIR`、`runtime_file.DEFAULT_BACKUP_DIR`、`llm_settings` 的 6 個路徑、`discord_bot` 啟動 log 兩行）；兩個腳本的 `sys.path.insert(0, "/app")` 改成從自己的位置往上一層推；守衛「容器掛載點的路徑」連 `/logs` 一起擋、`scripts/` 不再放行（突變：塞一行 `/logs/x.log` 守衛紅）；`test_paths` 加 LOGS_DIR 預設與環境變數兩條。爬蟲容器自己的 `/logs` 不動（M6）。完整測試 1,517 全過。沒做的三處讀法（config.json、article_runtime、telegram runtime_config 繞過 `hot_files`）與資料檔位置測試補釘，等使用者看完 Q1 再說。
  **踩到一個坑**：註解清理那個 commit（`14c92d4`）我用 `git commit -- src` 整個資料夾當 pathspec，把 bot 正在寫的 `src/settings/music_runtime.json`（`.gitignore` 有列、但很早就被追蹤進 git，所以 ignore 不生效）一起掃進去了：多了 `last_video_id`、`panel_message_id` 兩行變動。沒有資料風險（檔案本身沒動、歷史裡本來就有它的舊版本），只是不該進 commit。建議：下一個 commit 順手 `git rm --cached src/settings/music_runtime.json` 停止追蹤（`.gitignore` 的意圖本來就是不追蹤；`article_runtime.json` 是人手改的設定、保持追蹤）；要不要回頭改寫 `14c92d4` 把它拿掉由使用者決定（還沒推送、可以改）。已記進記憶：commit 一律列明確檔名。
  → 使用者（11:1x）：「我要追蹤的是歌單清單跟 URL，即時的變更不想追蹤」，自己跑了 `git rm --cached src/settings/music_runtime.json`，要我把之前的 commit 也清掉這個檔並說明指令。做法：在暫時的 worktree 跑 `git filter-branch --index-filter 'git reset -q f3798bf -- src/settings/music_runtime.json' -- f3798bf..master`（把那個檔在兩個未推送 commit 裡的版本設回前一版，等於那兩個 commit 沒動它；工作目錄一碼未動，bot 照常寫），`14c92d4`（原 6f65787）、`e152e28`（原 1a9fcdf）；接著把使用者暫存的刪除單獨 commit 成 `chore(settings): stop tracking the music runtime state file`。四月的兩個 commit（`af665a4`、`c86868a`）也動過它，但已推送到 dcbot 與 GitHub 鏡像，沒改——改了要 force push、重寫半年的 hash；內容只有歌單網址與訊息 id，沒有敏感資料。**後續（待使用者點頭）**：歌單清單目前變成沒人追蹤——拆檔：`music_runtime.json` 只留 `playlist_url`／`audio_mode`（人手改、重新追蹤），`last_video_id`／`panel_message_id`／`shuffle`／`active_playlists` 搬到新的狀態檔（gitignore、走 `runtime_file`）；新程式先讀新檔、沒有就退回讀舊欄位，寫只寫新檔；重啟後舊欄位變死資料，由使用者刪或同意我刪再 commit 乾淨的歌單檔。
- **Q1 已 commit（`1dd58a1` 程式、`7c6d6d2` 文件；使用者「Q1 我看完了 commit 接續做後面」）。後面三件做完等使用者看（10-14 11:4x，未 commit）**：
  ① 三處繞過共用讀檔機制的讀法：`MessageRouteResolver._load_config` 改走 `ChannelConfig.load_config(config_path, caller="telegram_relay")`；`_load_telegram_runtime_config` 與 `TelegramRenderAdapter._get_source_channel_name` 改走 `hot_files.read_json`（改了就生效、壞檔沿用上次）；`base_monitor.get_article_runtime_config` 的 5 分鐘 TTL 快取與三個全域變數拿掉、改 `hot_files.read_json`，`ptt_monitor` 的初始化讀取同樣改走它（仍是啟動時讀一次，行為不變）；`music/config.py` 兩處自己讀 config.json 改走 `ChannelConfig.load_config`。守衛「狀態 JSON 的讀寫」不再放行 base_monitor／ptt_monitor。
  ② 資料檔位置測試補釘 `switches.json`、`item_prices.json`、音樂的歌單檔與狀態檔。
  ③ 音樂拆檔：`music_runtime.json` 只當歌單檔（`playlist_url`、`audio_mode`，人手改；`.gitignore` 先維持不追蹤——我一度拿掉那行、使用者看到它跑進 git 清單質疑，立刻加回。要不要追蹤、何時追蹤由使用者在重啟並清掉四個舊欄位後自己決定）；新狀態檔 `settings/music_state_runtime.json`（`.gitignore` 加入）放 `last_video_id`、`panel_message_id`、`shuffle`、`active_playlists`，走 `runtime_file`。`music/config.py` 加 `STATE_KEYS`、`read_state()`（狀態檔有的優先、含明確寫 null 的；沒有的退回讀歌單檔裡的舊欄位；只收 STATE_KEYS，歌單永遠不從狀態檔來）、`save_state(key, value)`（只寫狀態檔）；`_load_config` 歌單與音訊模式讀歌單檔、隨機與啟用的歌單讀狀態；watcher 快照合併兩邊、監看的欄位不變（面板切隨機／歌單仍會觸發重載，和拆檔前一樣）；`announcer._save_panel_id(None)` 改成明確寫 null（拿掉欄位會退回讀到歌單檔裡過期的 id）、`_load_panel_id` 讀狀態；`player._save_to_runtime` 與 `get_last_position` 改走狀態。歌單檔程式一碼不寫。**過渡**：重啟前舊程式照舊寫歌單檔；重啟後新程式從狀態檔沒有的欄位退回讀舊值、寫只寫狀態檔，歌單檔裡那四個欄位從此是死資料——**由使用者刪（或同意我刪）後 `git add src/settings/music_runtime.json` 重新追蹤**；之後才會有乾淨的歌單 commit。
  測試：新 `test/test_music_state.py` 6 項（拆檔前狀態從歌單檔來、寫只動狀態檔且歌單檔一碼不動、狀態蓋過舊值、清掉的面板 id 不退回舊值、歌單永遠不從狀態檔來、`_load_config` 歌單與啟用分別來自兩個檔、announcer 清面板寫 null）；完整 1,525 全過（容器副本與正式容器）。8 個突變全紅（U1 不退回舊欄位、U2 寫回歌單檔、U3 null 被當成沒有、U4 狀態檔的歌單欄位也收、U5 啟用歌單讀錯檔、U6 隨機讀錯檔、U7 announcer 清面板時不寫、G1 base_monitor 又自己 read_text）——U7 第一版沒抓到，補 announcer 的測試；G1 沒抓到是守衛的 bug：`X.read_text(encoding=…)` 沒有位置參數，finder 的 `not node.args` 把它跳過了，修掉後多抓到 `llm_settings.load_llm_runtime_config` 的嚴格讀取（人手改的 LLM 設定、缺檔要炸，列 allowed）。**順帶發現**：`load_llm_runtime_config` 有 12 個呼叫點各自每次重讀 `llm_runtime_config.json`（`store_chat`、`context_retriever`、`member_profile_store`、`daily_maintenance`、搜尋的 vectors／rerank…），繞過 `LLMService` 的快取——是同一題（設定散落）的下一個候選，等使用者決定。
- **歌單檔改名、狀態搬家（10-14 11:5x，容器停著做）**。使用者：「先停容器、你改好我再啟動是不是比較好」→ 是，而且停著就能把狀態**搬**過去而不是靠退回舊欄位：備份 `logs/runtime_backup/music_runtime_2026-10-14-114551.json` 後，四個欄位原值寫進 `settings/music_state_runtime.json`、從歌單檔拿掉。使用者再問「這樣還能叫 runtime 嗎，它只是歌單檔」→ 改名 `settings/music_playlists.json`（`music/config.py` 的 `MUSIC_PLAYLISTS_PATH`，讀走 `hot_files.read_json`；`read_playlists_file()`），`.gitignore` 拿掉舊檔名那行（新檔名沒有列，要不要追蹤由使用者 `git add` 決定）；過渡用的「退回讀歌單檔舊欄位」拿掉——狀態已經搬好，留著只是死碼；歌單檔裡殘留的狀態欄位一律不當狀態讀（測試有守）。測試在 search-mcp 容器跑（discord-bot 停著，同一個映像檔、同樣掛 ./src）。狀態檔格式：`{"last_video_id", "panel_message_id", "shuffle", "active_playlists"}` 平鋪，不再包 `music`。
- **重啟與事故（10-14 11:5x）**：使用者啟動 discord-bot。gate 第一次紅——`test_telegram_relay_media_group.test_members_written_one_by_one_are_sent_together`（0.03 秒間隔的時間差測試），同一時間我在 search-mcp 跑突變副本搶 CPU，容器依 restart 設定重跑第二次全過（1,526）、11:55 起來。教訓：gate 跑的時候別在同一台機器並行跑測試副本。音樂：`MusicConfig` 載入 2 個歌單、啟用 2 個，從狀態檔讀到舊面板 id 並照啟動流程清掉重發，241 首載入 → 拆檔與搬家正確。**真的事故**：`commands.user_commands` 載入失敗 `NameError: settings_file`——Q1 收尾時我把 `monitored_channels_file = settings_file(...)` 放在模組層，而該檔的 import 區在這行之後（原本就有一半 import 寫在模組中段），`settings_file` 用到時還沒 import；`/list_item_price`、關鍵字監控等整組指令消失，其他功能照常，log 只有一行 ERROR。單元測試沒抓到是因為沒有任何測試 import 這個模組（`test_import_resolution` 只靜態檢查名字存在）。修法：import 全部搬到模組層賦值之前；新守衛 `test/test_cog_modules_import.py`——把 `commands/*` 與 `music/*` 每個模組實際 import 一遍（突變：把 import 搬回去，紅）。完整 1,527 全過。**要再重啟一次**才會載到 user_commands。這次的 commit（f3798bf）已經帶著這個壞掉的順序上去了，修正跟著這批一起 commit。
  → 使用者 12:03 再重啟：`commands.user_commands` 載入成功（監控設定讀到、persistent view 註冊），音樂 2 歌單／2 啟用／241 首，沒有 ERROR。M3～M5 全部生效。
- **狀態檔搬家到 `src/state/`（10-14 12:1x，程式改好等停容器搬檔；使用者「好啊 搬家」，並要求追蹤 `music_playlists.json`→ 已 `git add`）**。原則：`settings/`＝你手改、進版控；`state/`＝bot 寫、整個資料夾不進版控（`.gitignore` 十行變一行 `src/state/`）。`paths` 加 `STATE_DIR`、`state_file()`；10 個檔改位置、檔名拿掉 `_runtime`：intro_panel、intro_submissions、community_panel、telegram_quarantine_panel、telegram_quarantine、periodic_reminder、rollcall、music、monitored_channels、item_prices。順帶：關鍵字監控 `monitored_channels.json` 原本 `open()` 直接讀寫（沒 encoding、守衛沒抓到因為檔名沒有 runtime）→ 改走 `runtime_file`；守衛關鍵字加 STATE／state_file／monitored_channels。轉發設定 `article_runtime.json` 改名 `article_relay.json`（它是人手改的設定，留在 settings/、繼續追蹤）。新增 `test_data_file_paths.test_every_state_file_lives_in_the_state_folder` 釘住 7 個狀態檔都在 state/。完整 1,528 全過。**搬檔步驤**（腳本 scratchpad `move_state_files.py`，容器停著才跑）：整批備份到 `logs/runtime_backup/state_move_<時間>/` → 逐檔 `mv` 到 `src/state/` 並改名 → `git mv article_runtime.json article_relay.json`。搬完使用者啟動，gate 過了再確認面板、點名、關鍵字監控、價格都讀得到。AGENTS 的高風險清單與共用元件表已改成 state/。
  → 15:39 搬到 `src/state/`、15:48 啟動確認全部讀到（監控設定、點名排程、週期提醒、音樂 2／2／241）。使用者看 `periodic_reminder.json` 內容：「裡面有頻道設定跟文字，我認知上那是設定」——對：這些檔混著「透過 Discord 設的值」（身分組、面板頻道與文字、點名開關、監控關鍵字、價格、隨機與啟用歌單）和「bot 自己的紀錄」（訊息 id、thread id、放到哪首、pending 與統計），叫 state 是把「誰寫檔」和「誰決定值」混在一起；三種東西的分類表與兩條路（a 只改名 runtime／b 照意義拆、把 Discord 設的值併進 config.json 那類）寫在對話，**(b) 列進結束時的待決清單**（以前「面板位置不寫 config.json」是怕整份覆寫，現在 `update_config` 是安全讀改寫，理由已不成立）。使用者選 (a)。我提議啟動時自動把舊資料夾改名免再停容器 → 使用者「不要，我要乾淨的」，自己停容器。第一次改成 `src/runtime/` 平行於 settings/——**位置弄錯**：使用者從一開始就說 `settings/state`，我只問了名字沒確認位置；他啟動後指出，再停一次，改成 **`src/settings/runtime/`**（`RUNTIME_DIR = SETTINGS_DIR / "runtime"`、`runtime_path()`，`.gitignore` 一行 `src/settings/runtime/`）。兩次搬資料夾各留備份 `logs/runtime_backup/runtime_rename_*`、`runtime_rename2_*`。16:09 啟動確認全部從 `settings/runtime/` 讀到，沒有 ERROR。**gate 偶發紅已連三次**（每次首輪紅、自動重跑過）：相簿 0.03 秒時間差、GPU 閘門等待 0.4 秒門檻、GPU 租約續租 `test_renew_keeps_long_job_alive`（CancelledError）——都是 `test_gpu_gate`／媒體群組這類靠真實時間的測試在啟動時負載下翻車，每次多花 100 秒；這是 M7b（gate 只跑守衛、時間測試注入時鐘）的直接證據，先記著。
- **關聯總檢（10-14 16:2x，使用者 /goal「僅限這次把錯誤都修好、重新檢視 config 檔案關聯、授予 docker restart」）**。做法：在容器裡把每個設定、狀態、prompt、資源檔的路徑從程式實際算出來（`paths`、所有 `sys_settings` 類別裡 `/app/` 開頭的欄位、各模組常數）→ 43 個路徑全部存在；全 repo 掃舊檔名與舊位置（`article_runtime`、`music_runtime.json`、`*_runtime.json`、`settings/item_prices`、`src/state/`）→ 程式只剩名字裡帶 runtime 的函式與變數、沒有指向不存在的檔；修掉的殘留：`TRADE_FLOW.md` 的價格檔路徑、點名服務兩行 log 文字、`runtime_file` 說明、`test_rollcall_service` 說明、`test_data_file_paths` 兩個方法名、交接檔三處現況描述（隔離 thread、自介面板、音樂待辦）。git：`settings/` 追蹤的正是 7 個人手改的檔＋prompts；`settings/runtime/` 整個 ignore；`config.json`、`llm_runtime_config.json` 照舊追蹤。compose 沒有針對 settings 的掛載；兩個爬蟲容器不讀 `settings/`。權限：容器以 uid 1000 執行＝主機 jason，啟動後已成功寫 `settings/runtime/music.json`。完整測試 1,528 全過。**沒用到 restart 權限**：最後一次啟動（16:09）之後只改了 log 文字、說明與測試名稱，沒有功能差異。**順帶**：search-mcp 跑的是 29 小時前的程式（paths 等重構之前），它讀的檔都沒搬所以沒事，但兩個容器程式版本不同，下次方便時重啟 search-mcp 讓它跟上。待處理不變：三個測試垃圾備份檔等同意刪、這批程式等 commit。
  → Stop hook 指出「連三次首輪 gate 紅」還沒修 → 修三個靠真實時間的測試，判斷改靠倍數差而不是幾十毫秒：`test_gpu_gate.test_long_wait_is_logged_and_capped` 第二次呼叫的上限改 2 秒、門檻 1 秒（原 0.5／0.4，和讓位的 0.2 秒只差一點）；`test_renew_keeps_long_job_alive` 租約 0.5 秒改 2 秒、續租 0.1 秒 ×25（間隔只有租約的 1/20）；相簿 `test_members_written_one_by_one_are_sent_together` 安靜期 0.1 改 0.5 秒（餵料間隔 0.06 秒）、最長等 3 秒。驗證：search-mcp 跑全套當負載、同時這兩個模組在 discord-bot 連跑 5 次全過；16:25 用授權 `docker restart discord-bot`，**gate 首輪 1,528 全過**、啟動乾淨（監控設定、點名、週期提醒、音樂 2／2／241）。這不是把時間敏感測試從 gate 拿掉的根本解（M7b），只是把門檻放到負載下也不會翻的程度。
  → 再加強驗證：兩個容器同時跑全套、連兩輪，四次全過（1,528）。使用者回兩題：三個測試垃圾備份檔（`runtime_backup/runtime_2026-10-14.json`、`panel_runtime_2026-10-14.json`、`x_2026-10-14.json`，內容是 500／111 這類假 id 與 `{broken`）→ 刪，已刪；search-mcp 跑舊程式 → 使用者自己重啟（`docker compose restart search-mcp`），我不碰。這次 /goal 結束：設定關聯 43 個路徑全對、首輪 gate 偶發紅已修、沒有待處理的錯誤；程式 30 個檔＋2 個新測試檔等使用者 commit。 補驗：再三輪兩容器同時跑全套（六次全過，累計修後 10 次全套＋重啟首輪 gate 全過、零紅）；search-mcp 近 2 小時 0 錯誤、索引同步正常、MCP 搜尋可用——它跑舊程式不是錯誤，是版本不一致，使用者決定自己重啟。
  → 再往根本解推一步（M7b 的一部分提前）：`test/__init__.py` 加 `timing_sensitive = unittest.skipIf(APP_STARTUP_GATE == "1", …)`，三個靠真實時間的測試掛上；compose 的 gate 指令改成 `APP_STARTUP_GATE=1 python -m unittest …`。驗證：帶環境變數跑這兩個模組 skipped=3，不帶照跑全過；完整 1,528 全過。**compose 改了要 `docker compose up -d discord-bot` 重建才生效**（`docker restart` 不會吃到新的 command），這一步要使用者做；在那之前 gate 跑的是放寬門檻後的版本，負載下 10 次全套零紅。
  → 使用者加授權兩項：17:48 `docker compose restart search-mcp`（MCP server 與背景同步重新啟動，0 錯誤）、`docker compose up -d discord-bot` 重建（新 command 帶 `APP_STARTUP_GATE=1`，gate 首輪 1,528 全過、skipped=5＝原本 2＋時間敏感 3）。兩個容器現在都跑同一版程式。這次 /goal 的錯誤與後續風險都收掉；程式等使用者 commit。
  → 使用者看過六組清單後：「現在 commit，依六組分開」（`f13f996` 讀法收攏、`60b1275` 音樂拆檔、`d582150` runtime 資料夾、`ac0c009` user_commands 修正＋守衛、`bc74dd9` 時間測試＋gate 跳過、`70b520a` 貼圖字典）；注入時鐘「現在就做」（我先用白話解釋：程式問時間、睡覺改問一個可換的東西，測試用假時鐘瞬間跑完）。**注入時鐘（已做）**：`lemonade_gate` 加 `_clock = time.monotonic`、`_async_sleep = asyncio.sleep`，11 處 `time.monotonic()` 與 watchdog、跨行程輪詢的 `asyncio.sleep` 改走它們（同步版 `time.sleep` 不動）；轉發 worker 加 `self._clock`／`self._sleep`，相簿到齊判斷改用。新 `test/fake_clock.py`：`FakeClock.sleep` 登記醒來時刻、等事件迴圈跑完兩輪 call_soon 再撥時間叫醒最早的那個，多任務依時刻先後叫醒、被 cancel 的略過。四個測試改用假時鐘（續租、放棄後不再從頭等、到期後可重用、相簿逐則到齊），不再靠真實時間，兩個模組從 10 秒變 5 秒；`timing_sensitive` 與 compose 的 `APP_STARTUP_GATE=1` 沒人用了，拿掉；AGENTS 測試段改成「靠時間的邏輯走可換的時鐘，測試用 FakeClock」。驗證：5 個突變全紅（續租失效、放棄後又等、watchdog 不取消、安靜期失效、組員變動不重算）；負載下兩模組連 10 次全過、全套 1,528 全過；19:57 重建 discord-bot：首輪又紅一個**不同**的真實時間測試（`test_bahamut_edit_pacing.test_threads_do_not_wait_for_each_other`，跨 thread 限速，斷言 < 2 個間隔），自動重跑後正常。
  → 盤點整個測試套件靠真實時間的地方（小數秒 sleep、量牆鐘時間）：約 16 個測試。巴哈限速那組流程裡夾著 aiosqlite（真的執行緒 IO），假時鐘沒辦法知道該什麼時候撥時間（會在別的任務還在等 DB 時就把時間撥過去、順序和真實不同），所以**換不成假時鐘**；同類的還有爬蟲媒體下載的卡住判斷、相簿「等晚到的組員」、寫入預算到時停手、搜尋引擎冷卻、跨行程排隊。做法：假時鐘用在純 event loop 的流程（閘門續租／放棄／到期、相簿逐則到齊，已做）；其餘 14 個掛回 `@timing_sensitive`（`test/__init__.py` 加回、compose 的 gate 加回 `APP_STARTUP_GATE=1`）：啟動 gate 跳過、手動與 CI 照跑；限速測試的 SLACK_INTERVAL 0.5 → 1.0（對的流程等 1 個間隔、錯的等 3 個，差距更開）。gate 模式全套 1,528 全過（skipped=18＝原 2＋標記 16）；手動模式和另一個容器同時跑時 `test_takes_turns_with_another_process`（跨行程輪替、已標記）偶發一次——證明分類對、也說明手動／CI 跑它仍可能偶發，之後 M7 再看要不要改寫。20:10 再重建 discord-bot：新 command 帶 `APP_STARTUP_GATE=1`，gate 首輪 skipped=18 全過、啟動乾淨。AGENTS 測試段寫清楚兩條：能用假時鐘就用；夾真實 IO 的掛 timing_sensitive。這批（注入時鐘＋標記＋compose）等使用者看、commit。
  → 手動模式偶發的 `test_takes_turns_with_another_process` 也加固：放鎖後的讓位窗口在測試裡拉到 1 秒（外部行程每 0.02 秒輪詢，機器忙時 0.2 秒的窗口會錯過），負載下連 5 次過、全套 1,528 全過。使用者「我先看，等我說」→ 這批未 commit，等指令。
  → 10-15 使用者看過假時鐘圖解後「commit」：程式、交接檔、表情字典各一個 commit。使用者再要求把 `docker/discord_bot/dockerfile` 的一行註解（CMD 只在直接 docker run 時用到、compose 的 command 會蓋掉它）併進程式那個 commit：`git commit --fixup` 加 `git rebase --autosquash` 完成，內容與改寫前逐位元相同，三個 commit 換成新 hash：程式 `10e0fd4`、交接檔 `a1c9d19`、字典 `63a33cb`（都未推送）。同時回答：search-mcp 和 discord-bot 是同一份 dockerfile 建的兩個映像（只差 compose 自動加的服務標籤，12 層全部共用、pip freeze 完全相同），兩個獨立 container；dockerfile 的 CMD 不需要改（兩個服務在 compose 都覆寫了 command，映像本身沒有程式碼，拿掉 CMD 會繼承基底映像的 python3 直譯器）。提醒：requirements 51 行只有 5 行釘版本，改 requirements 時要 `docker compose build discord-bot search-mcp` 兩個一起建，否則套件版本會一新一舊。
- **測試要不要瘦身（10-13 使用者問「test 裡面會不會太多東西需要瘦身」，討論中）**：數字——84 個測試檔、22,854 行（程式 47,197 行，不含兩個爬蟲；比例 48%）、1,437 項；完整跑約 100 秒，啟動 gate 每次重啟都整套跑。最慢 15 個模組佔 85 秒：`test_search_index` 15.8 秒（真的建 SQLite 索引）、`test_bahamut_edit_pacing` 14.1（用 0.5 秒間隔真的等）、`test_ambient_insult` 8.6、`test_shared_conventions` 8.4（30 條規則掃全專案）、`test_gpu_gate` 5.6（真的等鎖）、`test_search_rerank` 4.8、`test_intel_search_client` 4.7、`test_chat_persist_retry` 4.7、`test_layering` 4.1（7 個測試各自重新 parse 148 個檔）。42 處測試真的睡（非 0 的 sleep，機器忙時會誤紅，10-12 就偶發過 1 項）；自造假物件 32 個 `Fake` 類別、184 處 `SimpleNamespace`，共用的只有 `telegram_relay_fakes.py`。判斷：行數不算多（測試對程式 48%，每條都做過突變），問題是「每次重啟都跑 100 秒」和「等真實時間的測試」。選項：(a) 刪測試——不建議，少掉的是保護；(b) **M7b 提前**：啟動 gate 只跑守衛類（`shared_conventions`、`layering`、`import_resolution`、`data_file_paths`，約 15 秒），完整測試改成 commit 前 `make check`＋CI 跑；(c) 等真實時間的測試改成注入時鐘與 sleep（`bahamut_edit_pacing` 14 秒 → 1 秒以內、`gpu_gate`、`chat_persist_retry`；`background_tasks` 已經是這種寫法），兩個守衛的 AST parse 快取一次給所有規則用（`shared_conventions` 8.4、`layering` 4.1 秒可降一半以上）；(d) 共用假物件抽成 `test/fakes/`（Discord 訊息、頻道、伺服器、互動），碰到哪個測試檔就順手改，M4 會動到 /askai 與插話的測試。**建議：(b) 現在排進來當下一個小里程碑（它本來就是 M7b，改的只有啟動腳本與 Makefile），(c) 挑最慢三個做，(d) 隨 M4 順手；不做 (a)。**等使用者回。
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
- 程式：`services/relay/telegram_filter.py`（`judge`、看圖範圍、排隊）、`services/relay/telegram_quarantine.py`（`QuarantineThreads`，runtime 檔 `settings/runtime/telegram_quarantine.json`）、`commands/telegram_quarantine_commands.py`（面板）、轉發端 `_send_unit`／`move_to_quarantine`／`restore`、一次性腳本 `scripts/telegram_move_to_quarantine.py`（預覽／`--apply`／`--file` 照清單搬）、離線樣本 `test/integration/it_telegram_filter.py`（90 則、`--days N`）；prompt `settings/prompts/telegram_filter_prompt.txt`（手改即生效）。commit：10-07 03:3x 整批 13 個（`8e8e4bc`…`23292a2`）、搬移 `0b1f7f6`／`bd2cfc2`／`0600476`、面板修正 `722768b`、排隊與補判 `c110c6d`／`aa812fe`。
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
- [ ] 有人送自介時：舊的自介面板被刪、新面板在最下面，`settings/runtime/intro_panel.json` 多了 `intro_panel_channel_id`、`config.json` 沒被改動（7/3 之後沒人送過自介，未證實）。

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

**架構（2026-09-28 定案；2026-10-13 起四步）**：04:00 維護（`llm/persona/daily_maintenance.py`，10-13 從 `discord_bot.on_ready` 搬出）
① emoji 字典 → ② 招牌梗衰減 → ③ persona agent（每晚主力；完整描述寫 `persona_agent_versions`，bot 讀不到；只重跑上次跑完後有新發言的人）
→ ④ 發布精簡版（`llm/persona/agent/publish.py`；**不經 LLM、整條原文照抄**，寫進 `auto_personality`；插話與 /askai 只讀這裡）。
原本的第 ③ 步「production 人格萃取」（過渡期備援）10-13 拆掉，見下方「③ 退場」；下面各段提到的 ③④⑤ 是拆之前的編號。

**狀態（2026-10-13）**
- commit：`c544036`、`b3dad1c`、`aafdc85`、`948ab96`、`2a0d0cf`（`publish_mode="on"`）；10-01 隱私、歸因與名字對照：`5aaf596`（③ 送 LLM 前跳過）、`9b2c4d1`（名字與錨點整合）＋docs；10-02 手動修正四條舊歸因錯誤（資料，見下方 PA-Q13）。
- ⑤ 每晚 05:45～06:35 寫入：10-02～10-13 **連續 12 晚 failed=0**（people 64～66、written 63～64、empty 2＝兩位還沒有過門檻條目的人）。log 關鍵字「persona 精簡版發布結束」。
- 備援 ③ 已拆（10-13，`7a369b6`，重啟後生效）：拆前每晚只替精簡版是空的 1 人跑、約 15 秒；PR-Q2 的門檻（10/05 後連續 7 晚 failed=0＋抽查）已達到，抽查 5 筆見架構審視區塊 M4a。精簡版是空的 4 人（68 筆 auto_personality 中 64 筆是精簡版）停在最後一版描述。圖解頁（前後決定、之前與之後的流程、拆了什麼、為什麼能拆、安全評估、命名）：https://claude.ai/artifact/WxdETmZ8B9yHYut1g7gr5c
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

**③ 退場（PR-Q2～Q4 10-13 已執行，隨 M4a 一起）**
- 已執行：刪 ③ 主體、`/personality_extract` 與 `/personality_extract_status`、`production_skip_list`；維護自己有「只跑一輪」旗標接替 ③ 兼任的鎖；補跑檢查不用改（發布每晚寫 `last_extracted_at`）；新成員接受空窗。原定案與選項保留供追溯：
- **定案（10-13 使用者：「不用手動入口」「維持精簡版就可以，確實是精簡後的資料」）**：手動入口不補、名稱不改；原選項保留供追溯——(1) 手動入口——1 補 `/persona_maintenance` 立刻跑一輪四步（agent 批次佔 GPU 一到三小時，有「只跑一輪」保護）／2 同一個指令加「只發布」選項，配 `/persona_agent_test save` 幾秒就把某人的人物卡換新／3 不補。**建議 1＋2 做成同一個指令**（約 30 行加測試，可併進 M4a 的 commit）。(2) 命名——「精簡版」是相對 agent 的「完整描述」（寫在 `persona_agent_versions`）而不是相對 ③，但聽起來像次級品：A 維持／B 改「人物卡版」（只改給人看的文字與 log，程式變數 `lite` 不動）／C 改「正式版」（和完整版對照會被讀成草稿與定稿）。**建議 B**，約 30 處字串。等使用者回。
- **PR-Q2 什麼時候整個刪 → 定案 A**：10/05 後，⑤ 連續 7 晚 failed=0 且抽查沒有新類型嚴重問題才刪。原標準「⑤ 連續 7 晚 failed=0，且抽查沒有新類型的嚴重問題」，目前 3 晚。A 照原標準，最快 10/05 後／B 現在就刪／C 做完 PR-Q1 就不刪，③ 留作備援。建議 A：今晚起 ④⑤ 換上暱稱表與流行語過濾，先觀察幾晚再拿掉備援。
- **PR-Q3 新成員的第一版描述 → 定案 A 接受空窗**（刪 ③ 時生效）：刪掉 ③ 後，新成員要等 ④ 寫出跨 2 次對話的條目，⑤ 才有東西發；在那之前插話與 /askai 只看得到自介與印象。A 接受這段空窗（④ 的納入門檻比 ③ 寬，通常幾天內就有）／B ⑤ 對還沒發布過的人放寬成 1 次對話也收／C 保留 ③ 只寫新成員。建議 A。
- **PR-Q4 手動萃取指令 → 定案 A 兩個都刪**（隨刪 ③ 一起做）：`/personality_extract`（手動跑 ③、預覽後按「寫入 RAG」）與 `/personality_extract_status`。A 兩個都刪（要看單人用既有的 `/persona_agent_test`）／B 改成手動跑全體 ④＋⑤／C 保留。建議 A（指令收斂計畫本來就要減少指令數）。

**不反對就照做的預設**：已做——⑤ 修掉「。；」雙標點、④ prompt 的「每條都要能單獨讀懂，不寫跟舊版比較的句子」。還沒做——同一人意思相近的條目在 ⑤ 用 embedding 相似度去重（⑤ 要多打 embedding）；兩位「DDLC」撞名時標籤加區分碼（動到插話／askai 讀取端）；回滾步驟寫成文件。⚠️ **需使用者明確同意才做**：刪除 ③ 留下的 Banana、Rie 兩份「無法分析」描述（先備份）。

**M7 之後待辦**：~~拿掉 ③~~（10-13 已做）；失敗的 run 隔天重跑；
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
last_confirmed: 2026-10-16
-->

> **目標：** 在白名單的一般聊天頻道裡，AI（柔喵）**沒人叫也會偶爾冒一句**，讓群聊更活；被 **@ 或 reply 時一定回**。定位是「彩蛋式偶爾插話」，**不是**功能一那種「專屬頻道全程參與」。寧可少講講得巧，也不要每句都插變噪音。
> Phase A、B、C-1～C-3 都已上線，2026-08-09 的自然插話重構也已上線並實測。原本「兩顆模型、12B 常駐」的架構已作廢（ambient、主模型、人格萃取現在是同一顆）。完整規劃、各 Phase 實作與自然插話重構的推演已歸檔到 `TODO-completed.md`「AI 偶爾插話（功能二）與自然插話重構（歸檔 2026-10-02，原 2026-06-21／2026-08-09）」。 10-02～10-07 的改進（看懂貼圖與 X 貼文、別的伺服器的表情、AI 看圖補字典、被罵的應對）已上線並 commit，紀錄歸檔到 `TODO-completed.md`「AI 偶爾插話：10 月的改進（歸檔 2026-10-13）」。

**待做**
- [ ] **C-4 自我進化迴圈**（閒置批次）：consolidation（合併重複、衝突取新記「以前X現在Y」）、decay（久未重提降權/封存）。**未做**。
- [ ] **C-4 隱私公告**：綁定插話頻道時自動置頂 + 改 channel topic。**未做**。
- [ ] **C-4 選配監督面板**（不擋流程）：查/改/刪/禁記；複用 `/personality_extract` UI 模式。**未做**（接口 `MemoryService.list_facts/forget` 已備好）。
- [ ] **觀測 / Debug 面板（使用者要求 2026-06-21，重要）**：使用者**不想用 CLI/log debug**，未來要一個 **Discord 面板** 能看：每次插話的**完整 prompt（含三層 context）**、決策狀態（reply/pass/error）、三層 context 數量（chat/persona/memory）、記憶 flush 狀態、某人記得的偏好。**取代** `ambient_prompt.txt` + grep。可與「記憶監督面板」合併成一個「AI 狀態/觀測面板」。**現況暫用**：`discord_bot.log` 的 `ambient 生成 …chat/persona/memory` 摘要 + [`/logs/ambient_prompt.txt`](src/llm/ambient/ambient_reply.py)（`AmbientChatSettings.debug_log`）；面板做好後轉成資料來源。
- **延後（非 v1 必要）**：`retrieve_discord_context` 泛化吃 channel 的 hybrid 長期對話召回——觸碰 /askai 核心、風險高，等 B 的 persona 召回不夠用再做。

**背景補時事／新梗知識（10-16 討論中，未動 code）**：使用者問「群裡開始聊新聞、新梗時模型一定沒有相關資料，有沒有辦法在背景更新知識、讓模型有參與感」，要求一起討論並說明業界最常用的做法。插話人設現名「琇紫」（本區舊段落的「柔喵」是舊稱）。
- **盤點（唯讀）**：插話完全不查（10-09 定案只管「被 @ 時當場查」，沒涵蓋背景預先整理，但精神是「查資料歸 /askai」）；`ambient_reply_prompt.txt` 第 36 行「不懂就別硬接 → [PASS]」（06-22 `c709f64`，之前沒記）讓新梗時沉默。快取：插話只有 system 段（約 8.2k token）被重用，user 段每次整段重讀（10-08～10-16 的 867 次 llm_usage）——筆記放 user 段新的不可信區塊只多付自己的 token（250 token 約 1.3 秒）；放 system 段每變一次多約 35 秒，也違反「群友與網路內容不進可信區」。插話 prompt 沒有「今天」的日期（聊天行只有時:分；`<recalled_context>` 的舊發言每行帶完整日期，但沒有今天可以對照）。現有資料幾乎只有鳴潮（官網、FB、PTT C_Chat 標題含鳴潮、巴哈鳴潮板、Telegram 內鬼），沒有一般新聞、梗百科、熱門話題來源；招牌梗沒有「意思」欄位；近 90 天群裡問梗、解釋梗的訊息各約 100 則。可照抄：emoji_autofill（觀察→佇列→一次一個→每日上限→維護時段不跑→dry_run→不覆寫人寫的）、ambient_memory（插話頻道緩衝→閒置批次→生成前召回；招牌梗的半衰期淡出公式）、[INSULT] 標記。SearXNG 更新後 yahoo、yandex 查新梗會給萌娘百科、百度百科、知乎、PTT、B 站梗百科。
- **業界常見做法**：①當下查——搜尋工具由模型決定叫不叫（ChatGPT、Claude、Gemini、Perplexity、Grok；本專案 /askai）；②關鍵字觸發的設定集（lorebook／World Info：SillyTavern、NovelAI）——每條有觸發詞，最近幾則聊天出現觸發詞才把那條放進 prompt，有條數與 token 上限，不分誰在說話；③閒置時整理記憶——Letta 的 sleep-time agent、mem0（抽出事實後新增／更新／刪除）、ChatGPT 記憶、Zep（事實帶有效期間，被新事實取代就失效）。會參與聊天的角色 bot 常見組合是②＋③，①留給明確提問。偵測「不懂的詞」：聊天產品最常見的是讓模型自己決定查（弱點正是新梗：模型常把沒看過的梗硬套成舊意思）；熱搜、社群監測用統計爆量詞／新詞；研究上有「生成時信心低才查」（FLARE、Self-RAG），要逐字信心值，這裡的後端不好用。
- **提議架構**：程式找候選詞（最近新冒出、多人在講、筆記裡沒有）→ 模型挑值得查的 → 遊戲相關先查本機情報索引、其他經 SearXNG → 模型寫一兩句筆記（附日期、來源；查不到或不確定就不寫）→ 存筆記 → 插話時聊天裡出現那個詞（含別名）才放進 user 段新區塊，區塊說明寫今天日期與「可能過時或有誤、以群友說的為準、不要解說或附網址」→ 依類型淡出（新聞短、梗長）。要改：新背景工作（放 `llm/ambient/`，照 emoji_autofill 節流，抽到第二份時先抽共用）、筆記檔、`prompt_builder` 新區塊與安全規則的不可信清單（要重啟 bot）、第 36 行加筆記用法、新開關（off／dry_run／on）。
- **第二輪（10-16 16:0x）使用者改方向**：「閒置的時候查，我希望不是等人問 /askai，而是群友聊天的時候，就讓模型在判斷要不要插話的那個環節同時決定要不要上網搜尋」。**本輪改的共識**：KN-Q2 定案＝模型在插話判斷時自己決定查不查（業界最常見的工具呼叫做法；上一輪建議的「程式統計候選詞」改當之後的輔助）；KN-Q1 由此推得 B（只查群裡正在聊的、不主動抓新聞）；10-09「插話被 @ 時先不要查」將被取代，範圍待 KN-Q4 確認。可行性（工具輪與 [PASS]／#N／[INSULT] 輸出契約、快取、時間、隱私、存法）交給 workflow 唯讀核對中，結果回來再補下面的題目與建議。
- **第三輪（10-16 16:1x）使用者「KN-Q3～Q7 都依照你的建議」→ 全部定案**：KN-Q6 當場查、當場用（有查的那次插話晚多少見第四輪的實算；當時說的「約一分鐘」偏高）；KN-Q4 被 @、被回覆時也可以查（**取代 10-09「插話被 @ 時先不要查」**）；KN-Q7 本機遊戲情報＋網路一起給、由模型挑（同 /askai 的 combine_runners）；KN-Q3 查到的存起來，放 `settings/runtime/` 的 JSON（使用者同意開這個新檔），下次聊天出現同一個詞直接帶上、不再查；KN-Q5 每次插話最多查 1 次、每天最多 30 次，第一週「記錄模式」（照樣查、記下查了什麼，但不把結果交給模型），使用者看過紀錄（沒亂查、沒送出群友名字）再全開。必備防護：查詢字送出前程式檢查群友名字、結果當不可信資料、W7 拿掉 bing。實作等可行性核對（workflow）回來後動手，和 W6、W7 一起上線、只重啟一次。
- **外部調查補充（10-16 16:3x）**：①研究（RetrievalQA 的 TA-ARE，Findings ACL 2024）在指令放今天日期加「要查／不用查」各兩個示範，模型判斷要不要找新資料的正確率平均高 14.9 個百分點（數字來自雲端模型，本機要自己驗）→ 當場查要一起做：user 段開頭放今天日期，插話規則加幾個示範。②零連網的現成線索：群友貼連結時 Discord 已經抓好的預覽（標題、描述）沒放進插話的聊天行（`semantic_message_text` 只取文字、表情、@、貼圖；預覽只寫進聊天向量庫），近 30 天 32,388 則裡有 1,110 則帶預覽（YouTube、B 站、GIF 梗名、遊戲 PV）→ KN-Q8。③遊戲新詞最即時的定義來源是鳴潮 BWIKI 的 MediaWiki API（免 key，改版當天就有新條目，簡體要轉繁），可當之後的補充來源。④業界做法的佐證：RAG 勝過微調學新知識（Ovadia、Gekhman，EMNLP 2024）；SillyTavern World Info 的關鍵字觸發（scan depth、token 預算）；開源群聊 bot MaiBot 會自學群內黑話（不上網、GPL 不能抄）；Open-LLM-VTuber、AstrBot 等主流做法都是查詢當下的工具呼叫。⑤調查的挑錯者提醒：當場查要先離線重播近期插話 prompt 驗證模型遇到新梗會不會真的叫工具（研究顯示模型常把新梗硬套成舊意思）——排進實作的驗收。
- **KN-Q8（新）群友貼連結時，把 Discord 已經抓好的預覽標題與描述放進插話看到的那一行？** 建議做：不連網、不花查詢額度，群友貼新聞、影片、梗圖時模型就知道是什麼；每則限長度，避免 prompt 變長太多。
- **第四輪（10-16 17:0x）可行性核對（workflow：程式可行性、防護與儲存兩組唯讀盤點＋一個審查者核對；結果在 scratchpad `feas_readable.txt`）**：
  - **做得到、不另寫迴圈**：插話已經呼叫 `LLMService.generate_reply`，只是沒給 tool_runner；給插話自己那組工具＋`max_tool_rounds=1` 就走 /askai 的 `_answer_with_tools`。共用迴圈加兩個選用參數、預設維持 /askai 行為：查滿時的提醒文字（現在寫死「直接回答原本的問題」，會把插話推向開口；插話改系統口吻、明講可以 [PASS]，被 @ 時用手上資料簡短回）；「不改用不帶工具的呼叫」（第一次失敗照實回錯、提醒後還要工具就回空字串＝[PASS]；否則 empty_content 每天約 1 次會多跑一整次、整段重讀）。牽動：/askai、印象審核、日記都用預設值不變。
  - **代價（實算，更正第三輪的「約一分鐘」）**：插話中位 75.4 秒、P90 139 秒（869 次）；有查的那次多 9～41 秒（中估 20 秒，第 1 輪叫工具前只寫幾百 token），再加工具時間（網路 0.2～2 秒；遊戲情報中位 12.8 秒、P90 32 秒）。每天 30 次全用完約多 5～20 分鐘模型時間（現在插話每天約 130 分鐘）。最壞：加旗標後每次插話最多 3 次模型呼叫、各 180 秒逾時。
  - **快取**：模板把工具宣告放在思考那句之後、我們的 system 之前；自發、被 @、接續給同一份宣告與規則，只有上線（與之後改工具說明或規則）時整段重讀一次約 50 秒。llama.cpp 的 RAM 快取同時留得住好幾份開頭（log：插話前一個呼叫是別的功能時照樣命中 8k），偶爾不宣告工具（額度用完、帶圖被拒、search-mcp 掉線）代價只是切換時重讀一次。system 段任何位置一變都可能從 0 重讀，所以日期不放 system 段。
  - **技術決定（Claude 照審查定，不另問）**：每次插話只執行第一個工具呼叫（共用迴圈會把同一輪的呼叫全執行，要在插話那組工具的 execute 擋）；情報只宣告 search、不宣告 fetch；插話規則由插話那組工具每次用 hot_files 讀（掛在情報那組，search-mcp 掉線規則就跟著消失）；今天日期放 user 段最前面（只有插話傳）；輸出含 `<tool_call>` 原文一律當 [PASS] 不送；名字檢查放 `llm.persona.member_names`（全伺服器成員的三種名字＋自介與印象暱稱，`allow_longer`，純英數短於 3 字不算；識別碼用 regex：#尾碼、`<@…>`、8 位以上數字、email），試算 127 句正常查詢誤擋 0、空白隔開的名字 79/79 抓到、黏字漏 8/79；第 36 行改成「有查詢工具時可以先查一次，查完仍沒把握才 [PASS]」、第 87 行「如果最後有【你的心情】」改「如果有」（工具規則會接在心情之後）；每日計數抽到 utils（看圖補字典一起改用），不另設維護時段（插話在那段本來就讓位，近 10 天只生成 8/1,055 次）；情報 search 的 question 帶觸發那則原文；log 依 trace 加總。
  - **上線前驗收（真模型重播近期插話 prompt）**：含新梗會叫工具、一般閒聊不叫、帶圖＋工具後端接受（插話 17% 帶圖，/askai 有工具以來沒有一題帶圖；不接受就帶圖那次不宣告工具）、查完仍守 [PASS]／#N、回覆沒有網址。
  - **第一版範圍（審查建議）**：記錄模式＋共用迴圈兩個參數＋名字檢查＋規則檔＋日期＋防呆，和 W6、W7 同一次重啟；存筆記、全開、成人內容過濾放第二版（看 KN-Q10）。/askai 接名字檢查另談。
  - **KN-Q5b（補問已定案的 KN-Q5，有新證據）**：第一週記錄模式原定「照樣上網查、只是不給琇紫結果」，但查詢字會在使用者看紀錄前就送到 Yahoo、DuckDuckGo、Yandex；名字檢查黏字漏 8/79、群裡私下的綽號不在名單。A 照原定（名字檢查同時上）／B 第一週完全不上網，只記琇紫想查什麼與名字檢查判定，週末 Claude 用 127.0.0.1:8888 與 search-mcp 重查（先剔掉有名字的）、整理品質——建議 B（兩種做法琇紫都拿不到結果，「多常想查、查什麼」量出來一樣）。
  - **KN-Q9 查到的東西琇紫怎麼講**：A 像本來就知道／B 語氣保留、自然帶出處（「好像是…的梗」「新聞說…」），不說查過、不附網址／C 同 B，被 @ 問事情時可附一個網址——建議 B（同 /askai「自然帶出處、不提工具」）。
  - **KN-Q10 KN-Q3「查到的存起來」什麼時候做**：A 跟第一週一起（只重啟一次，但存法只能先猜、第一週也用不到）／B 第一週看完、全開時再做（用真實查詢定存法；全開那次再重啟；第一次上線不必動「寫壞 bot 就起不來」的安全規則檔）——建議 B。
  - **KN-Q11 新檔**：① `llm/ambient/ambient_search.py`（插話那組工具：每次 1 次、每天 30 次、名字檢查、記錄模式）② `settings/prompts/ambient_search_rules.txt`（插話查詢規則，含要查／不用查各兩個示範）③ `utils/daily_quota.py`＋測試（看圖補字典一起改用）④ `test/test_ambient_search.py` ⑤ `test/integration/it_ambient_search.py`（上線前真模型驗收）；另在 `settings/switches.json` 加 `ambient_search_mode` 與說明、先設記錄模式——建議全部可以。
- **待決（選項＋建議，第一輪原文；KN-Q1～Q7 已在第二、三輪定案，留作紀錄）**：KN-Q1 學哪些：A 只學遊戲（只查本機索引、不出網）／B 遊戲＋網路梗＋群裡正在聊的時事／C 再加主動抓新聞（RSS、熱搜）——建議 B，只查群裡正在聊的，不主動抓（主動抓多半用不到，模型還會想拿出來講；08-15 也否決過 RSS）。KN-Q2 怎麼發現不懂的詞：A 模型在插話時輸出標記說要查／B 程式統計新冒出、多人在講的詞，模型再挑／C 兩者都做——建議先 B（符合 08-09「量測歸程式、判斷歸模型」，先 dry_run 看候選準不準），A 當第二版。KN-Q3 筆記放哪：A `settings/runtime/` 的 JSON（不進版控、手改即生效，像 lorebook；新檔要使用者同意）／B pgvector 新表／C `settings/` 的文字字典（會進公開鏡像，群聊衍生內容不適合）——建議 A。KN-Q4 被 @ 時帶不帶筆記：A 帶（讀事先整理好的，不是當場查）／B 只有自發插話帶——建議 A。KN-Q5 每天查幾個詞：建議先 dry_run 一週只記候選詞、不查不寫，看每天冒出多少再定；上線起始每天 20 個、04:00～07:30 不跑、前景忙時讓位（每個詞約 10～20 秒 GPU，20 個約 5 分鐘）。

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
- [ ] 音樂面板改用共用置底元件 `utils.panel_bump.PanelBumper`（2026-09-29 決定**暫緩**：面板訊息存記憶體、按鈕狀態就地 edit、啟動時有清理流程、面板 id 在 `settings/runtime/music.json`、歌單在 `settings/music_playlists.json`（10-14 已拆開）；要搬得先把面板 id 移到別的檔，上線那次會留一則舊面板要手動刪）
- [x] 多歌單管理（多歌單下拉，可複選合併播放）— 2026-06-20，詳見 `TODO-completed.md` 歸檔
- [ ] 快取空間管理（LRU 清理、磁碟用量監控）

**P2（進階功能）：**
- [ ] 歷史播放紀錄
- [ ] 使用者點歌統計
- [ ] DAVE 加速問題追蹤（等 discord.py 後續版本優化）

### 語音斷線後的自我重連競態（2026-10-15 查因；修法待定案）

<!-- @meta
id: music-voice-reconnect-race
type: RISK
status: draft
depends_on: [music-bot]
affects: [music-bot-todo]
last_confirmed: 2026-10-15
-->

**現象**：使用者回報音樂 bot「一直自我斷線」。log 統計（09-29 起 discord logger 才進檔，統計腳本在 scratchpad 的 `voice_stats.py`）：語音 websocket 被切 62 次（1006 ×47、1001 ×5、30 秒沒訊息 ×10），每天 0～7 次、沒有趨勢。其中 45 次 discord.py 1～6 秒自己接回、歌照播（Discord 上仍看得到 bot 閃退重進一次）；8 次播放器在 1～3 秒內介入、9 次在 30～34 秒介入。10-08 起 6 次快速介入全部變成「掉兩次、無聲 63～65 秒、連丟兩首」（10-08、10-09、10-14、10-15 ×3）。10-14 的 11 次加入有 9 次是部署重啟；10-15 的 10 次有 3 次重啟、7 次介入。

**成因鏈（已定案，四路獨立覆核一致）**：
1. 外部：語音連線被切（多為 1006），與主 gateway 的 RESUMED 只有 12/62 同時，是語音連線單獨掉、不是整機網路，也不是程式造成（event loop 卡頓的紀錄都不在斷線附近）。
2. discord.py 2.7.1 自己重連時，`VoiceConnectionState.disconnect(cleanup=False)` 的 finally 會把 `_connected` set 再 clear（喚醒等待者；自 2.4.0 起如此）。播放執行緒每 20 ms 檢查一次連線，若恰好在 state 變成 disconnected 之後、flip 之前進入 `wait_until_connected`，會被叫醒、`is_connected()` 仍 False → 放棄播放（DEBUG，log 看不到）→ `after(None)` → 這首歌被當成播完。命中率約 8/50。
3. `_play_next` 半秒後重入 → `ensure_voice` 看到未連線 →「偵測到失效的 voice_client」→ `_force_cleanup_guild_voice` 對舊連線 `disconnect(force=True)` 再 `channel.connect()` 建新連線。`disconnect` 不會取消舊連線的 `_poll_voice_ws` task（只有 `connect()`／`soft_disconnect()` 會），它卡在 `_connect` 的 30 秒 wait_for 裡變殭屍。這是第一次「自我斷線」（約 5 秒無聲）。
4. 30 秒後殭屍逾時 → 對已關閉的 ws poll 到 close code 1000 → `_expecting_disconnect` 早被重設 → 走完整 `disconnect()`：送 channel=None 把新連線踢出頻道（新連線收 4014），並以 guild id 為鍵 `cleanup()`，拔掉的是**新連線**的登記 → 新連線再收不到任何語音事件，`_potential_reconnect` 必等滿 30 秒 →「Reconnect was unsuccessful」→ stop() → 播放器第二次介入。這是第二次「自我斷線」（約 33 秒無聲）。
5. 另一型：discord.py 重連本身卡住（gateway 事件 30 秒沒到，常伴 RESUME 或 endpoint=null），或 poller 被未接住的例外殺死（10-15 03:55 是 `ClientConnectorDNSError`；2.7.1 只接 ConnectionClosed／TimeoutError）。播放執行緒 30 秒逾時後介入，這時介入是對的、沒有殭屍。

**覆核結論**：機制全是舊的——播放器重連碼自 05-11 未改；discord.py 2.7.1 是 PyPI 最新版，master 的語音三檔與 2.7.1 相同，升版無解；沒有對應的 upstream issue（第三方專案 discord-radio 10-06 踩到同類問題，修法是「每個 guild 只允許一個重連、先給 discord.py 幾秒自己接回」）。10-08 第一次「被踢」發生在當天映像重建之前，套件變動假說推翻；10-08 前的快速介入沒被踢是因為當時 gateway 或新連線剛好也卡住，差別只在亞秒級時序。另外 `player.py` 的 `guild._voice_client = None` 是空操作（Guild 有 `__slots__`，`voice_client` 是讀登記表的 property）。

**修法（10-16 已實作、未 commit，見最後盤點紀錄的快照 01；三題照建議：35 秒、同一條連線重連、斷點續播）**：斷線後先讓 discord.py 自己接回，播放器只在它真的接不回來時才介入；介入時在同一個連線物件上 `connect()`（它會先取消舊 task，不留殭屍），失敗才建新連線；被打斷的歌接回去播而不是跳過；等待期間只記 INFO，真的介入才 WARNING。測試用假連線物件守四條底線（時限內接回就不動手、逾時才同物件重連、再失敗才建新連線、被打斷的歌不被跳過），等待走可換時鐘接 `test/fake_clock.py`。

**未定案（選項＋建議）**：
1. 等多久才介入：建議 35 秒（discord.py 自己的連線逾時 30 秒＋緩衝）；短於 30 秒會和它打架。
2. 介入方式：建議同一物件 `connect()`、失敗才建新連線。另一選項是硬清理時另取消私有的 `_runner`，版本一換就壞，不建議。
3. 被打斷的歌：A 從斷點續播（記已播秒數，ffmpeg `-ss`）／B 從頭重播／C 照現在跳下一首。建議 A。
4. 檔案衝突：`player.py`、`cog.py` 有另一批未提交的停機收尾改動。A 等那批先 commit 再改／B 只改重連函式、兩批一起等下次重啟。建議 A。

順帶可做：`settings/logging.json` 把 `discord.player` 暫設 DEBUG，修好後可直接看到「Aborting playback」有沒有再發生；刪掉無效的 `guild._voice_client = None`。

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
