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
- 2026-10-02 11:3x（巴哈轉發，**已 commit**）：使用者同意後 `b11df27` fix(relay)（`bahamut_monitor.py`＋`test_bahamut_edit_pacing.py`）＋交接文件 `docs` commit；另一個 session 的 Persona 紀錄（PA-Q13 等）沒放進這兩個 commit，留在工作目錄。worktree 已移除。
- 2026-10-02 11:2x（巴哈轉發上線驗證，**未 commit**）：11:16 那輪 429 從舊程式的 104 次降到 0、3.7 劇情串 31 次編輯間隔全是 6～7 秒、活躍串 7 篇長文本文連結與續文導航全部到位；待使用者說 commit。
- 2026-10-02 11:0x（巴哈轉發上線，**未 commit**）：使用者 10:53 重啟，啟動 gate 744 項全過；BH-Q5 一次性修復 11:00～11:02 改好 31 格（只讀重驗 0 格不一致）；等 11:12 那輪驗證新程式。
- 2026-10-02 10:5x（巴哈轉發第 3 輪，**已套用到 ./src・待重啟・未 commit**）：使用者 BH-Q6 選 B（擔心 hash 每輪不符 → 說明並以測試守住）、BH-Q9 選 A；本文底部連到第一則續文實作完成，24 項新測試、正式容器完整 744 項全過、26 種突變全紅；BH-Q5 修復腳本試跑：31 格全部不一致、待重啟後執行。
- 2026-10-02 10:xx（巴哈轉發第 2 輪，**worktree・未套用・未 commit**）：使用者 BH-Q5 B、Q7 B、Q8 A；Q7 封存串跳過編輯、有新回覆先解除封存，Q8 編號修正，20 項新測試、完整 740 項全過、21 種突變全紅。使用者追問 BH-Q6「原文刪除或大幅修改怎麼辦」→ 查證：刪文從沒偵測（0 篇）、大幅刪減被擋 1 篇、API 不回傳這些狀態；BH-Q6 改成問「本文要不要往下的連結」（建議加），新增 BH-Q9 刪文要不要標示（建議維持）。
- 2026-10-02 09:5x（巴哈轉發限速：複查與補強，**worktree・未套用・未 commit**）：兩輪更新之間的乾淨比對確認舊錯誤顯示的規模（3.7 劇情串 7 則；全部串 log 圈出 35 則回覆留言沒顯示）→ BH-Q5；子 agent 獨立複查無必修問題，照意見補續文增減與溢出格測試、排程改成從編完起算、被拒的編輯不佔名額；新增待決 BH-Q6～Q8。18 項新測試、完整 738 項全過、18 種突變全紅。
- 2026-10-02 09:2x（巴哈轉發限速，**worktree 完成・未套用・未 commit**）：查證不是「每輪全部重編」，是 Discord 對編輯舊訊息的未公開限速（同串約 5 秒一則）；另確認 9/12 篇續文導航連結被洗掉、建立當下沒記 hash 讓第一輪新留言不顯示等 4 個顯示錯誤。使用者 BH-Q1～Q4 全照建議；TDD 11 項新測試、完整 731 項全過、11 種突變全紅。待：獨立複查、BH-Q5（舊錯誤顯示要不要修）、套用＋重啟。詳見[巴哈轉發編輯](#巴哈轉發編輯被限速續文留言格顯示錯誤2026-10-02-已上線)。
- 2026-10-02 12:xx（交接文件歸檔，**未動 code**）：使用者要求整理沒用的東西。子 agent 唯讀盤點（查 log 與 git 佐證）後，整段或已完成部分的**原文**搬到 `TODO-completed.md`（13 個歸檔區塊，Index 已加列），交接文件從 3,154 行減到約 1,710 行，只留仍有效的待辦、待決與坑；核對過：舊檔每一行都還在新交接文件或歸檔檔裡（只有 4 行是刻意改寫）；內部連結全部對得上。另把 LM-Q2／LM-Q4 從盤點紀錄搬成「Lemonade 後端與寫入緩衝的待決」區塊、mcp 2.x 改名提醒搬到 MCP 區塊、現況摘要依現況改寫。巴哈轉發區塊（另一個 session 的）沒動。**待使用者決定**：① Ambient「自我蒸餾 learned_style」是否確定不做（已被 style_refs 取代？）→ 是就歸檔；② ProBot 歡迎功能關了嗎；③ 活動自動發布 9/22 對抗性複查剩的 embed／parser 兩面向還要做嗎；④ 半年沒動的「產品能力 TODO」「跨來源整合」「Reaction 統計」要保留、歸檔或改寫；⑤「指令收斂 Dashboard」與「管理入口與指令整理 TODO」兩段重疊要不要合併。Persona M7 內部精簡排在 10/05 刪 ③ 時一起做。（`TODO-completed.md` Index 有 23 列舊連結本來就對不到：舊標題日期前有空格、連結少了連字號，這次沒動。）
- 2026-10-02 09:0x（PA-Q13 手動修正，**動了資料庫：使用者明確同意**）：四條舊歸因錯誤各寫一個新版本改寫、只替這四人重新發布精簡版；備份在 `logs/persona_manual_fix_2026-10-02.json`。
- 2026-10-02 08:5x（驗收，**未動 code**）：③⑤ 與白天名字對照都照預期；發現 ④ 不會主動修正舊的歸因錯誤（Biboolater「被暱稱一野」已發布）→ PA-Q13；④ token 用量同人中位數 +3,100、預算停止收集 9 次 → 觀察；另發現巴哈轉發每小時重新編輯已轉發的回覆，被 Discord 限速（見下行）。
- 2026-10-02 08:5x（新發現，**未動 code**）：9/29 log 統一後才看得到的 `discord.http` 限速警告——全是 `PATCH channels/{討論串}/messages/{id}`（編輯訊息），9/29 55 次、9/30 212、10/01 849、10/02 到 08:34 已 201，每次都緊接在 `POST /notify/bahamut` 之後，頻道是論壇裡的巴哈討論串（「【討論】3.7版本 劇情討論串」等），同一則訊息每小時被重新編輯一次。推測巴哈轉發每輪把已轉發的回覆全部重編。**10-02 使用者交給另一個 session 查**，這邊不碰巴哈轉發的程式。
- 2026-10-01 18:xx（**已 commit**）：使用者同意後分三個——`5aaf596` perf(persona) ③ 送 LLM 前跳過（中間版本在容器 /tmp 跑完整測試 696 項全過）、`9b2c4d1` feat(persona) 名字與錨點整合（720 項全過）、交接文件與 AGENTS.md 另一個 `docs` commit。原本說四個，但 ④⑤ 名字表與白天名字對照共用新模組、`discord_bot.py`／`llm_commands.py`／測試裡兩邊的改動交錯，拆開的中間版本跑不起來，合成一個。`it_comfyui_image.py` 沒進。**待使用者 04:00 前重啟 discord-bot**；明早驗收見 Persona 區塊。
- 2026-10-01 18:xx（獨立複查與修正，**720 測試全過・未 commit・要重啟**）：複查無高、中問題；修掉找人與 ⑤ 擋名字太寬（加詞邊界、排除 bot）、撞號加長後不縮回；試算誤中從 54 則降到 24 則且全是真的叫名字。
- 2026-10-01 17:xx（PA-Q11／Q12 實作，**718 測試全過・未 commit・要重啟**）：使用者決定當天做；共用錨點（撞號自動加長）、共用名字模組、白天人物卡改顯示名稱＋名字對照＋找人加 Discord 名字；實測發現並修掉 Discord 名字被符號拆開的問題。
- 2026-10-01 16:4x：使用者同意 PA-Q11 a/b/c 與 PA-Q12 B，排在 10/02 早上確認 ④⑤ 後動工。
- 2026-10-01 16:3x（grill：PA-Q11 第 2 版設計，**未動 code**）：查證人物卡標籤用自介別名、插話 prompt 發言者中位 6 人但人物卡最多 3 張；Q11 改成主名字統一顯示名稱＋一段名字對照＋別名查詢加 Discord 名稱；Q12 建議改 B。
- 2026-10-01 16:2x（grill：末四碼撞號，**未動 code**）：唯讀實測 128 人 0 組撞號、錨點不存檔；寫入 PA-Q12。
- 2026-10-01 16:0x（PA-Q8～Q10 實作，**701 測試全過・未 commit・要重啟**）：抓 Discord 名稱（不建 DB）、⑤ 擋把群友名字寫成口頭禪（試算 3 條全是真錯誤）、名字表標本人；使用者問白天 prompt 的 #末四碼 識別 → 寫入 PA-Q11。
- 2026-10-01 16:1x（grill：暱稱來源，**未動 code**）：使用者指正一野＝糯糯、提議通抓伺服器暱稱與全域暱稱；唯讀查 Discord 成員清單證實糯糯全域名稱是「一野shout死你」；提出 PA-Q8～Q10。
- 2026-10-01 15:4x（重啟驗證，**未動 code**）：使用者 15:40:48 重啟 discord-bot 與 telegram-scraper（scraper 15:35 另重啟過一次）。bot 啟動測試 696 項全過；15:42:10 補跑檢查看到 ⑤ 05:49 的寫入而跳過；正式 log 唯一 WARNING 是每次重啟都一樣的「Telegram 啟動補償 373 筆」（既有問題，見 Telegram 過濾區塊）。scraper 的 `logs/telegram_scraper.log` 開始寫入，兩次啟動都完成歷史掃描並開始監聽、每行帶等級與模組名。PR-Q1（③ 送 LLM 前跳過）今晚 04:00 第一次生效，明早看「跳過由 persona agent 精簡版負責的 N 人，剩 M 人」那行。
- 2026-10-01 16:0x（③ 退場第 2 輪定案，**PR-Q1 已實作・696 測試全過・未 commit・要重啟才生效**）：使用者 PR-Q1～Q4 全照建議；③ 改成送 LLM 前就跳過精簡版負責的人；整個刪 ③（含新成員空窗、兩個手動指令）排在 10/05 後。
- 2026-10-01 15:4x（grill：③ 退場第 2 輪，**未動 code**）：PA 改動分三個 commit（`8098f6d` scraper log、`255a2f7` persona、`3043c62` 交接文件）；查 log：⑤ 三晚 63 人 0 失敗、③ 兩晚寫 0 人卻各跑 12 分鐘 LLM；提出 PR-Q1～Q4。
- 2026-10-01 15:3x：PA-Q6 使用者選 B → 規則檔放寬成只擋健康、性向、感情家庭、政治、具體行程；`publish.py` 說明同步；persona 測試全過。
- 2026-10-01 15:2x（Persona M7 隱私與歸因，**已實作・695 測試全過・未 commit**）：PA-Q2、PA-Q4 使用者回「都做」，實作中使用者看到 ⑤ 的隱私關鍵字（地名、持股、宮廟）說「沒差、太敏感」→ ⑤ 不做隱私過濾，只靠規則檔；④ 附群友暱稱表（16 人）、⑤ 擋群內流行語（試算 6 條）、拿掉「。；」。新增待決 PA-Q6（規則檔要不要跟著放寬），規則檔即時生效，要在今晚 04:00 前決定。詳見 Persona 區塊。
- 2026-10-01 15:0x（grill：Persona M7 第 1 輪回覆，**未動 code**）：PA-Q1 原則同意、PA-Q3 選 C（性化內容不動）定案；PA-Q5 使用者指出自介區已有暱稱 → 查證自介 18 人、印象 8 人有暱稱，但 ④ 寫描述時沒讀它們 → 改成暱稱表從自介＋印象組、不另做 JSON；PA-Q2、PA-Q4 用例子重新說明，待答。
- 2026-10-01 14:4x（grill：Persona M7 隱私與歸因第 1 輪，**未動 code**）：唯讀盤點目前 66 筆精簡版，寫進 Persona 區塊；重點是原建議「同一個引號詞 ≥2 人就全部不發」會誤殺 47 條（多數是群內暱稱與貼圖名稱，不是群體用語），改建議只比對口頭禪類條目並排除暱稱與貼圖名；提出 PA-Q1～Q5（擋哪些類別、擋法、性化內容、歸因、人工校正檔），③ 退場排到下一輪。
- 2026-10-01 14:3x（telegram-scraper 的 `print` 全改 logger，**已實作・679 測試全過・未重啟・未 commit**）：使用者排定先做這項與 Persona M7 隱私歸因。45 處（runner 25、handlers 16、db 2、tg_config 2）改成各模組 `logging.getLogger(__name__)`，訊息原文與 `[History]`／`[CatchUp]`／`[Refetch]`／`[Telegram]` 標籤都保留（除錯時照舊 grep）；等級：失敗與重試用 WARNING，`Refetch 處理訊息失敗`、`處理自訂表情時發生例外` 這兩個接住所有例外的地方改 `exception`（附 traceback），其餘 INFO。新增 `telegram_scraper/log_config.py`：console＋`/logs/telegram_scraper.log`（10MB×5 輪替、格式同 bot）；**只由 `main.py` 呼叫**（bot 也 import `tg_config`，import 時改全域 logging 會洗掉 bot 的設定）；log 檔開不了時只留 console、不讓 scraper 起不來；Telethon 的 INFO（斷線重連、FloodWait、補抓漏收更新）保留進檔、逐檔下載訊息關掉；`main.py` 崩潰時把 traceback 寫進檔（容器重建後 docker logs 就沒了）。**為什麼不共用 `settings/logging.json`**：容器只掛 `./src/telegram_scraper` 與 `./logs`，共用要改 compose 掛載並重建容器，這次不做。守衛拿掉 `telegram_scraper/` 的兩條例外（不准 print、logger 一律 `__name__`）。新增 `test_telegram_scraper_logging.py` 5 項，6 種突變都紅；scraper 容器內 import runner／handlers／main 正常、`/logs` 可寫。**生效要重啟 telegram-scraper**（只掛自己的目錄，不受 bot 維護時段限制，但重啟會跑一次歷史掃描）。
- 2026-10-01 10:4x（Lemonade 升級 11.9.0 → 2026.40.0＋bot 斷線自癒盤點，**未動 code**）：release notes 的 breaking change 逐條對照，bot 都沒用到（版本號格式、`registry_source`、`/docs`、upscale 標籤、ROCm 後端、`system-info` GPU 名稱只進故障快照 log、`user_models.json` 改完要重啟 lemond）；`auto_evict` 預設 false。舊的 `user.` 模型名稱在新版仍可解析。升級當下 bot 沒有任何連線錯誤（`llm_anomaly.log` 今天為空），10:32～10:35 插話處理器卡約 3 分鐘：推測是新版第一次載入 embedding（10:35:51 那批 19 則才寫進 pgvector，期間持有 GPU 閘門），之後 10:37:13 directed 插話成功（首字 29 秒／9,870 tokens 無 cache、24.6 tok/s，09-29 是 33 tok/s，只一筆樣本，待觀察）。**bot 現有的自癒**：每個請求獨立，Lemonade 回來後下一個請求就恢復，不必重啟 bot；連不上時重試 2 次（約 3 秒）後放棄；後端卡死（`network_error`）會自動重發 `/api/v1/load`；ctx 設定由 Lemonade 自己存著。**缺口與待決**：
  - **LM-Q1 聊天向量斷線會掉**：`store_chat` flush 前就清空 buffer，embedding 失敗時 log 寫「將重試」但沒放回 buffer → 那批訊息永遠沒有向量（原始訊息仍在 raw store）。影響不只 RAG：這張聊天表也是 04:00 人格萃取（`personality_extractor` 從這裡撈最近 N 天文字）與 persona agent SQL 工具的資料來源，漏寫的訊息這些地方也看不到。選項：A 失敗的放回 buffer 下輪重試（設上限）／B 定期補寫缺向量的訊息／C 不改、只把 log 改誠實。建議 A。今天沒發生。
    - 10:5x 使用者問「能修嗎、現在有防無限累積嗎」。查證：`_buffer` **沒有任何上限**，現在不會累積只是因為「失敗就丟」；觸發條件是滿 30 則（每則新訊息都檢查、各開一個 flush task）或每 5 分鐘。**另一個問題**：斷線時 flush 仍逐則硬試，每則 3 個變體 × 3 次嘗試，連線被拒約 9 秒／則（30 則約 4.5 分鐘），封包被丟時每次嘗試最多等 `LLM_TIMEOUT` 300 秒；全程持有 GPU 閘門，`/askai` 與插話都要等。B 不採用的理由：raw store 沒存連結預覽，重建出的文字與原本不同。
    - **11:0x 已實作（未重啟・未 commit）**：使用者說「能修正了嗎」，三個待決照建議（上限 1,000、丟最舊、編輯一起改）。改 `store_chat.py`（`_is_backend_unreachable`：`LlmConnectionError`／`LlmTimeoutError`／SQLAlchemy `OperationalError`／`InterfaceError`，pgvector 斷線也算；`should_flush_now()`；`_trim_oldest`；兩個 `_sync_*` 改回傳「寫入數＋要放回的」；刪掉沒人用的 `buffer_size()`）與 `discord_bot.py` on_message 改呼叫 `should_flush_now()`。新增 `test_chat_persist_retry.py` 10 項，15 種突變全紅，完整測試 674 項全過。執行中的 bot 仍是舊程式（模組已載入），下次重啟生效。**已知限制**：後端回 4xx／5xx 仍視為那則訊息的問題而略過（與以前相同；改成重試會讓一則壞訊息卡住整個 buffer）；斷線時每輪定期 flush 仍會在第一則上等到逾時（3 種寫法 × 3 次嘗試，連線被拒約 9 秒，封包被丟可能十幾分鐘），期間佔著 GPU 閘門——此時 LLM 本來就連不上，影響有限；要再縮短可讓共用 embedding client 遇到連線錯誤時不做 perturbation 重試（會影響 RAG，另議）。（待決 LM-Q4 已移到「Lemonade 後端與寫入緩衝的待決」區塊。）
    - 修法（原提案）：① 遇到連線錯誤或逾時就停下整批、全部放回 buffer 前端；其他錯誤照舊跳過該則（避免一則壞訊息永遠重試）；② buffer 上限，超過丟最舊並 log；③ 上一輪失敗後，到下一個 5 分鐘週期前不再因為滿 30 則開 flush，同一時間只跑一個 flush；④ 編輯 buffer 同樣處理。待決：上限值（建議 1,000 則，以熱絡時段每 5 分鐘 10～20 則估，約撐 4～5 小時）、超過時丟最舊（建議）還是丟最新、編輯 buffer 要不要一起改（建議一起）。bot 重啟會丟掉還沒寫的 buffer（最多 5 分鐘）是既有問題，不在本次範圍。
  - **LM-Q2** 已移到「Lemonade 後端與寫入緩衝的待決」區塊。
  - **LM-Q3 重啟期間的請求不補做**：`/askai` 回「無法連線」、插話放棄該輪。建議維持現狀（Lemonade 重啟要數分鐘，拉長重試只會讓使用者等更久）。
- 2026-10-01 04:0x（**已 commit**）：拆成四個——`648b80b` fix(scraper) 一致的 Firefox 指紋＋一輪一個 session、`20acc0c` feat(scraper) 巴哈每輪統計、`6f39e87` feat(relay) IT 就地補內文、交接文件 `docs` commit；中間兩個狀態都在容器 /tmp 跑過（scraper 10／16 項、bot 652 項），最終版正式容器 bot 664 項、scraper 16 項全過；`it_comfyui_image.py` 沒進。待驗：約 04:46 HKEPC 通知時補 11 則摘要訊息、巴哈本輪完成那行的統計。
- 2026-10-01 03:5x（`scraper_it_v2.patch` **03:45:51 套用**）：使用者 03:45:44 重啟 discord-bot、03:46:41 重啟 scraper。bot 的啟動測試比套用早開始，只跑了舊的 652 項（新 12 項已在 /tmp 驗過，下次重啟會進 gate）；但 IT 模組 03:46:03 才載入，跑的是新程式。scraper 03:46:45 第一輪 HKEPC 沒有錯誤（候選都已有內文）。**IT 訊息還沒補**：scraper 一啟動就通知 bot，bot 回頭拿資料時 scraper 的 API 還沒起來（`Cannot connect to host scraper:8000`，scraper 開機時任務與 API 同時啟動的既有時序問題），這次沒跑到補內文；下一次 HKEPC 通知（約 04:46）會補。9/28 起只帶摘要的有 11 則（26811、26813、26818、26820、26821、26825、26828、26833、26837、26838、26840），內文都已到；9/28 那 2 則可能落在 API 3 天範圍外。巴哈第一輪新統計等本輪完成才會出現。
- 2026-10-01 00:3x（IT 就地補內文＋scraper 抓網頁機制＋巴哈統計，**worktree 完成・未套用・未 commit**）：使用者定案 IT-Q1 B、SC-Q1～Q4 照建議。bot 658 項、scraper 新測試 7 項全過，13 種突變都紅。IT 改用「掃頻道比對網址」就地更新，不動 `sent_articles.db`。實測發現 HKEPC 的 Cloudflare 只擋 Chrome／Safari 模擬、Firefox 全過（403 時有時無的真正原因），「一輪一個瀏覽器」單獨上線會更糟 → 新增待決 SC-Q5 → 使用者要求逐站深入實測、並在共用層讓大家一起用 → 共用層改成只用 Firefox 系＋一輪一個 session（`run_session`），四個爬蟲都接上；實測 HKEPC 兩輪 15/15 有內文。獨立複查完成並照意見修正（v2：BrowserType 可選匯入、IT 從最新讀起／先發新文／編號比對／帶圖失敗退回文字、巴哈中斷也記統計），bot 664、scraper 16 項全過，突變 28 種都紅；待使用者同意後套用＋依序重啟。
- 2026-09-30 23:4x（IT 新聞被截斷查證，**未動 code**）：使用者回報 EVGA 那篇只發出一段；查證是 HKEPC 內頁 403 時只剩列表頁摘要，bot 照發並標記已發送。9/22 起 73 篇中 23 篇是這樣發出的，從 7/14 就有、與整理無關。新增 IT 新聞只帶摘要區塊（已歸檔到 TODO-completed.md） 與待決 IT-Q1～Q4。
- 2026-09-30 22:5x（全功能狀態檢查，**未動 code**）：虛擬機 18:15～21:32 停機（使用者 host 端作業，預期內），21:35 bot 起來後啟動 gate 652 項全過、沒有 ERROR；官網 5581、FB 859～861、PTT 停機期間 13 篇都補發，逐一確認開機前沒發過（沒有重發舊文）；Telegram 補掃、插話、`/askai`、點歌、點名與週期提醒排程都正常。IT 新聞 6 篇因 21:34 通知時 bot 還沒起來而延後，22:34 下一輪 HKEPC 通知時全數補發。**巴哈（23:30 更正）**：不是卡死，是**每輪變慢約 4 倍**。以執行緒建立時間辨認，兩輪都已證實：21:34 那輪 78 分鐘（22:52 結束、轉發 2 篇）、22:34 那輪 78 分鐘（23:48 才開始寫資料庫、23:52 結束、轉發 5 篇；當時 23:34 那輪的執行緒還在，22:34 的已結束）；log 沒有「第幾輪」的標記，某輪超過一小時就會和下一輪的完成紀錄錯配，所以早先誤判成「22:34 那輪 17 分鐘完成」。時間花在抓網頁（正常 18 分鐘→74 分鐘），寫資料庫正常（2～4 分鐘），今天沒有任何請求失敗。**從 13:09 開始**：那時 scraper 映像也一起重建（telegram-scraper 是 12:25），它的 `requirements.txt` 完全沒鎖版本，全部升到最新（curl_cffi 0.16.3、beautifulsoup4 4.15.0、SQLAlchemy 2.1.1、selenium 4.49.0 等）；13:09 之前每輪都約 20 分鐘。影響：巴哈轉發最多延遲約 2 小時；每輪都超過一小時，會和下一輪重疊（排程沒有防重疊），同時兩輪打同一個站。舊映像可能還在（懸空映像 `e06661dbd647`，6/13，1.5GB），可用來比對升級前的版本。待決：找出是哪個套件變慢（建議先比對新舊版本，嫌疑最大的是 curl_cffi）、要不要只鎖那一個套件、要不要幫巴哈任務加防重疊（scraper 端程式，這次整理沒動到）。既有、未變多：插話模型回空內容（今天 5 次，9/25 4 次）、HKEPC 內頁 403（累計 236 次）。
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

## 現況摘要

> 本區只放指標與錨點。詳細內容請跳到對應區塊。
> 若某主題不再是當前主線，應從此區移除或降級，不應永久停留在現況摘要。

| 主軸 | 狀態 | 進度 | 詳見 |
|---|---|---:|---|
| Discord Bot / AI 對話能力 | 已有可用基礎能力；架構總覽停在 Ollama 時代，待重寫 | 80% | [專案架構](#專案-ai-架構總覽已過時待重寫) |
| Context / Prompt 優化 | 主要重構都已上線；剩 asker roles、/askai 指定 thread、/remember 等小待辦 | 97% | [Context 優化](#context--prompt-優化專區) |
| AI 偶爾插話 / 閒聊（功能二） | **已上線**（含 2026-08-09 自然插話重構）；待做 C-4 整併／淡忘、觀測面板、鉤子權重迴歸 | 85% | [AI 偶爾插話](#ai-偶爾插話--閒聊功能二已上線c-4-待做) |
| Persona Agent M7（精簡版發布） | **已上線**；10-01 隱私歸因與名字對照上線、10-02 手動修正四條舊錯誤；10/05 後符合標準刪 ③ | 90% | [Persona Agent M7](#persona-agent-m7精簡版發布2026-09-28-已上線觀察中) |
| ComfyUI 產圖 + GPU 資源仲裁 | **規劃定案（2026-09-02）**；租約鎖與卸載 helper 已完成（`e13343d`），鎖有漏洞待修；落地細節討論中 | 25% | [ComfyUI 產圖](#comfyui-產圖--gpu-資源仲裁2026-09-02-規劃定案未開工) |
| AI 私聊頻道 + 三層記憶（功能一·姊妹案） | 規劃完成（含道德守門）；人設 prompt 已就位；**本輪暫放旁邊** | 10% | [AI 私聊頻道](#ai-私聊頻道--三層記憶機制規劃中) |
| 使用者指令記憶 (/remember) | 規劃中（與 AI 私聊頻道互補） | 5% | [/remember 規劃](#使用者指令記憶-remember-未來工作) |
| Reaction 統計 / 社群互動玩法 | 規劃中 | 5% | [Reaction TODO](#reaction-統計與社群互動玩法) |
| 點歌機器人（Music Bot） | 已上線運作 | 85% | [點歌機器人](#點歌機器人專區) |
| Telegram relay 可靠性 | 補掃、媒體防雷、相簿漏圖修正都已上線並驗證（9/29 起合併與補圖符合設計） | 98% | [Telegram 補掃](#telegram-漏收補掃與相簿漏圖已上線) |
| 活動自動發布（公告 → Discord 伺服器活動） | **已上線**（連結修正、重複活動修正、就地升級）；待下一篇含活動的公告確認遷移摘要 | 95% | [活動自動發布](#活動自動發布連結指向錯誤--重複建活動已上線) |
| 程式結構整理 | **主要整理已完成並上線**（`llm/` 與 `services/` 分群、點名去除反向依賴）；剩 P2 拆檔（未決）、P3 `discord_bot.py` 瘦身（暫停）、N3（延後）、命名慣例未寫進 AGENTS.md | 90% | [程式結構整理](#程式結構整理2026-09-29-起主要整理已完成剩-p2p3n3) |
| MCP／搜尋工具化（網頁、公告、論壇） | **構想（2026-09-29）**，grill 第 2 輪；已定先做 MCP、LLM 決定何時查、位置（`services/search/`＋`llm/mcp_server.py`）、關鍵字全文搜尋、論壇索引範圍、`search`＋`fetch` 兩個工具；**設計已全部定案**，待實作 | 15% | [MCP／搜尋工具化](#mcp搜尋工具化2026-09-29-構想grill-中) |
| Telegram 訊息 LLM 過濾 + 隔離區 | **構想（2026-09-28）**，討論中 | 0% | [Telegram 過濾](#telegram-訊息-llm-過濾--隔離區2026-09-28-構想討論中) |
| 週期活動提醒（深塔海墟矩陣） | **已上線**：9/29 20:00 矩陣結束前提醒實發、手機通知確認正常；待 10/7 矩陣開放與自介面板置底驗證 | 95% | [週期活動提醒](#週期活動提醒深塔海墟矩陣已上線) |
| 新成員歡迎訊息（接手 ProBot） | **已上線**（10/01 07:59 首次實發）；ProBot 歡迎功能是否已關待確認 | 95% | [新成員歡迎訊息](#新成員歡迎訊息接手-probot已上線) |
| scraper 抓網頁機制＋IT 就地補內文 | **已上線**：IT 補內文已驗證（10/01 補 11 則）；HKEPC 10/01 03:46 後 0 次 403；巴哈每輪仍約 80 分鐘待查；SC-Q6 觀察 | 95% | [scraper 抓網頁機制](#scraper-抓網頁機制檢查2026-10-01-已上線) |
| 巴哈轉發編輯限速＋續文／留言格顯示錯誤 | **2026-10-02 已上線並驗證**：同串編輯排隊 6 秒、續文逐則比對並補回導航連結、建立當下記 hash；封存串等新回覆再補、新回覆編號修正、本文底部連到第一則續文；24 項新測試、完整 744 項全過；**11:16 上線驗證：429 由 104→0、同串間隔 6 秒、連結全部到位**；BH-Q5 已修 31 格；commit `b11df27`；之後觀察每天 429 與熱門串單輪耗時 | 100% | [巴哈轉發編輯](#巴哈轉發編輯被限速續文留言格顯示錯誤2026-10-02-已上線) |
| 跨來源整合（Article/FB/PTT/TG） | 有方向，尚未全面收斂 | 35% | [跨來源整合](#跨來源整合專區) |
| Discord Bot 管理入口 | 規劃中 | 10% | [管理 TODO](#discord-bot-管理入口與指令整理-todo) |

> 已完成 / 過往工作（Bahamut scraper + 反爬基礎設施、幽靈點名核心 + DM、社群 ID 查詢 Phase 0、Telegram Relay、Music Bot 完整實作等）詳見 `TODO-completed.md`。
>
> **2026-08-18 歸檔**：活動公告自動建活動（17 筆已建立）、Telegram 自訂表情 → Discord App Emoji（10 個已上傳）、Telegram 多頻道來源 + 轉發去重（Gamedataleak 205 筆），三者皆已上線運作，連同 2026-06-25 ~ 2026-07-25 的盤點紀錄一併移入 `TODO-completed.md`。
>
> **2026-10-02 歸檔**：程式結構整理的討論紀錄、IT 新聞只帶摘要、scraper 指紋查證、週期提醒／新成員歡迎／活動自動發布／Telegram 補掃的實作紀錄、Ollama 時代的架構總覽、Context 優化與 AI 插話（含自然插話重構）的已完成部分、共用元件索引、9/29 以前的盤點紀錄，原文移到 `TODO-completed.md`；交接文件只留仍有效的待辦、待決與坑。

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
  - **定案（2026-09-29 第 8 輪，取代上面 A／B 兩案）**：搜尋本體放 `services/search/`（搜尋是給指令、/askai、MCP 共用的服務，不只給 LLM；索引檔放 `services/search/data/`）；MCP 殼放 `llm/mcp_server.py`（給 LLM 客戶端的橋接，`python -m llm.mcp_server` 啟動；不取名 `llm/mcp/` 以免跟 `mcp` 套件混淆）；網頁搜尋留在 `llm/retrievers/web/`（含 /askai 專用的觸發判斷與 prompt 格式化）。討論經過見 [程式結構整理](#程式結構整理2026-09-29-起主要整理已完成剩-p2p3n3) 的 L4a／L4b。
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

- **給之後寫 MCP 的提醒**：`mcp` 2.x 把 `FastMCP` 改名為 `MCPServer`（`from mcp.server.mcpserver import MCPServer`）；它帶進來的 `httpx2` 不會蓋掉我們用的 `httpx` 0.28.1。
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

## 巴哈轉發：編輯被限速＋續文／留言格顯示錯誤（2026-10-02 已上線）

<!-- @meta
id: bahamut-edit-pacing
type: RISK
status: confirmed
last_confirmed: 2026-10-02
affects: services/relay/bahamut_monitor.py, test/test_bahamut_edit_pacing.py
-->

**症狀**：9/29 log 統一後看得到的 `discord.http` 429，全是 `PATCH channels/{巴哈討論串}/messages/{id}`：9/29 55 次、9/30 212、10/01 849、10/02 到 08:13 已 201。

**機制（一句話）**：Discord 對編輯舊訊息有未公開的較嚴限速（同一個討論串約 5 秒只能編一則；429 要求等待中位數 4.1 秒、最長 5.04 秒），我們只按「同一則訊息」冷卻 1.5 秒，同串不同則約 1 秒編一則，熱門串每則都先吃 429 再等。

**查證（唯讀）**
- **不是「每輪把全部重編」**：用 API 當下資料重算「3.7 劇情討論串」94 則的 hash，只有 1 則跟 StateDB 不同；一天被限速 16 次的那格，每次都對得上新留言或熱門留言 B1 的 GP 在漲。10/01 的 1,613 次編輯：本文（推噓數為主）872、留言格 741（其中 178 次只是留言 GP／熱門變動）、續文 18。
- 被限速的 1,317 次（9/29～10/02）：留言格 755、本文 540、溢出格 15、續文 0；訊息全都發出超過 1.7 小時，剛發的訊息編輯從沒被擋。3 篇並行時各串各自被限速（交錯出現），所以是「每個討論串」的限制。
- discord.py 會自己等完重試，沒有因限速漏掉的編輯（兩天內真正失敗的 9 次是 Discord 503 與討論串已封存）。429 算進 Discord 無效請求上限（10 分鐘 1 萬次），我們最多約 100 次，離很遠。實際影響：log 雜訊＋每輪多等幾分鐘。
- 越來越多：3.7 版本 9/30 開始，熱門串留言與 GP 暴增。
- **坑（比對 Discord 實際內容時）**：以 bot 身分用 REST 讀訊息要照 `X-RateLimit-Remaining`／`X-RateLimit-Reset-After` 等、429 等完重試、5xx 重試；前兩次沒照做（每秒 4 則）被限速，讀到空內容誤判成「32/94 本文、100/276 留言格不一致」，數字作廢。比對還要挑兩輪更新之間（bot 約每小時 :12 開始，3.7 劇情串約 3 分鐘處理完），否則會把時間差當成錯誤。

**順帶查到並確認的顯示錯誤**
- **續文導航連結被洗掉**：本文 hash 一變就把該篇所有續文無條件重編，重編內容不帶「⬇️ 更多內文」。以 bot 身分唯讀抓 Discord：有 2 則以上續文的 12 篇中 **9 篇連結已消失**。
- **續文切到滿時連結塞不下**：預留 100 字，連結實際 104 字（ID 19 位數）；sn=111119 從建立起就沒有連結。
- **新建留言格／更新時新增的回覆／更新時新開的溢出格沒存 hash**：下一輪走「首次寫入 hash 只存不編」，這期間的新留言或推數變動不會顯示，要等之後再有變動才一起出現；之後都沒變動就永遠不出現。log 證實：sn=144598 20:20 有 13 則新留言但留言格沒更新，21:32 再來一則才一起出現；sn=144713 01:16 的 2 則新留言 03:15 才出現。
- **hash 只涵蓋第一則 embed**：內文後段改了，續文永遠不會更新。

**定案（使用者 2026-10-02：BH-Q1～Q4 全照建議）**
- BH-Q1：同一個討論串的**所有**編輯間隔 6 秒（不分新舊訊息，不把 Discord 沒公開的「1 小時」寫死）。
- BH-Q2：推噓數照舊有變就同步（排隊後不會再撞限速，不為此讓推噓數落後）。
- BH-Q3：續文一起修——沒變不編，有變時保留導航連結。
- BH-Q4：測試從公開入口 `send_bahamut_thread_to_forum` 測（暫存檔上的真 StateDB＋假 Discord thread／訊息＋縮短間隔）。

**改了什麼（2026-10-02 10:48 套用、10:53 重啟上線；commit `b11df27`）**
- `_edit_with_cooldown`：以討論串（`msg.channel.id`）排隊、間隔 `THREAD_EDIT_INTERVAL = 6.0`；先登記下一個可用時間再等，同串並行也會錯開。取代 `MIN_EDIT_INTERVAL`／`_last_edit_ts`。複查後補兩點：編完再從「真正編完」重設一次間隔（discord.py 吃到 429 會自己等完重試，那段不能算進去）；被拒絕的編輯（例如討論串已封存 50083）退回登記、不佔名額（不然封存串每則失敗都白等 6 秒，9/26～27 曾一天約 300 次）。
- `_update_continuations` 改寫：不夠的追加、多出的改佔位，再逐則比對「應有內容（含導航連結）」跟 Discord 上的訊息（忽略頭尾空白——Discord 會修掉；巴哈內文 0 篇含 `\r`、0 篇有頭尾空白），一樣就不編。**每輪都比對**（以前只在本文 hash 變時）：後段內文改了、導航連結掉了都會補。成本：每則續文每輪多一次讀取，只發生在有續文的貼文（全部 40,651 篇中 91 篇）。
- 續文上限：新增 `CONTINUATION_NAV_RESERVE = 110`（ID 最長 20 位數時連結 107 字），`CONTINUATION_CONTENT_LIMIT` 3996→3986；留言格的 `LAST_SLOT_NAV_RESERVE` 不動（改了會讓所有第三格重新分配、大量重編）。本文第一則的切法不受影響，所以本文 hash 不會因此全部變動。
- `_send_continuations`：導航連結用切好的文字＋共用的 `_continuation_nav()` 組，不再回頭讀訊息、不再因長度略過。
- hash 記帳：建立留言格、溢出格、更新時新增的回覆、溢出格補導航後的前一格，都在當下記 hash。
- log 文字：「已更新主文／回覆 embed + 續文」改成「已更新主文／回覆 embed」，續文另記「已更新續文 msg=…」。
- **行為變更（BH-Q6，尚待使用者確認）**：續文從 0 則變成 1 則時，舊程式會去編本文訊息加導航，而且用只有描述的 embed 蓋掉，本文的標題與圖片會不見（本文 hash 也不含導航，推數一變又會消失）；新程式不編本文，新續文以 reply 指向本文。

**測試**：`test/test_bahamut_edit_pacing.py` 18 項（同串排隊、間隔從編完起算、被拒不佔名額、跨串不互等、只編有變的／有變的一定編、更新時新增的回覆、溢出格（更新時開的、建串時就有的）、續文推數變不編／後段改了只編那一則／主文續文／導航補回／切到滿也塞得下／變多／變少再變多）；容器 /tmp 完整測試 738 項全過；巴哈測試連跑 5 次都綠；18 種突變全紅。斷言「不超過多久」的兩項用 0.5 秒間隔（餘裕約 0.45 秒），避免啟動 gate 在機器忙時誤紅。

**獨立複查（2026-10-02，子 agent，唯讀）**：沒有必須修的問題。模擬 Discord 修頭尾空白跑 8 種續文情境（1→3、3→1、3→1→4、0→2、2→0、追加途中失敗、結尾換行），同資料再跑一輪都是 0 次編輯。每輪多讀的續文：目前活躍 50 串只有 7 篇、9 則。上限改 3986 只讓 5 篇切點移動（則數不變、都不在活躍串，之後活躍時合計 ≤16 次編輯）；活躍串裡導航補回約 2 次編輯。單串單輪最多 117 次編輯（5698，10/01 16:12）→ 新版約 12 分鐘。複查指出的測試缺口（續文增減、溢出格 hash）與兩個排程低風險點都已補上。另記：開新溢出格那一輪，前一格會先不帶導航編一次、再帶導航編一次（既有，現在多 6 秒，之後再優化）；手動指令單篇模式會等整串處理完，極熱門串可能超過互動回覆 15 分鐘時效（既有）。

**套用後會發生的一次性變化**
- 3 天內還在 API 範圍的討論串，有續文的貼文會在下一輪被比對：導航連結被洗掉的會補回；切點因上限改成 3986 而移動的會重編一次（少數可能追加一則續文，排在討論串最後）。
- 舊的「首次寫入只存不編」留下的錯誤顯示不會自動修好（hash 已記成新內容）→ BH-Q5。

**舊的錯誤顯示有多少（09:16～09:23 兩輪更新之間的乾淨比對，遵守額度）**
- 「3.7 劇情討論串」本文 96 則中 2 則、留言格 282 格中 5 格跟目前資料不符，7 則全對得上「新回覆建立後第一輪就有變化 → 只記 hash 不編」：sn=144278 推數從 9/30 起沒顯示；sn=144744／144745 02:15 來的留言到現在仍顯示「預留留言區（等待更新中...）」。
- 用 log 圈全部討論串：三天內新增回覆 1,053 則，其中 244 則建立後才第一次有留言進來；209 則後來又有變動、被順帶修好；**35 則的留言格到現在仍是舊的**。圈不到的：整串新建時的回覆（建立 log 沒有 sn）、第一輪只有推數變動的本文（不寫 log）。
- 全面讀一遍不划算：最近 50 串（含長年大串）共 66,908 則訊息；只讀三天內新增的回覆＋新建串也要 2,000～4,000 則，照額度約每秒 1 則。

**待決**
- **BH-Q5 舊的錯誤顯示要不要另外修**：A 不修（新的不會再發生；舊的等之後有變動自然修好，沒再變動的就一直是舊的）／B 套用後跑一次性修復，只處理 log 圈出的 35 則回覆的留言格（讀約 40 則、只編不一致的，幾分鐘；以 bot 身分照額度、同串 6 秒排隊；hash 已是新內容，不寫資料庫）／C 一次性讀三天內新增回覆與新建串的本文＋留言格全部比對（30～60 分鐘以上，涵蓋推數漏顯示）。建議 B：修的是最明顯的症狀（留言沒出現、還寫「等待更新中」），成本小；推數差一兩個的安靜回覆影響小，也會隨時間離開轉發範圍。B、C 都會編 Discord 上的訊息，要使用者同意。
- ~~BH-Q6~~ **已定案 B**（第 3 輪）：**本文要不要有往下的連結**（使用者追問「原文刪除或大幅修改時怎麼辦」，第 2 版）：見下方「刪除與大幅修改的現況」。選項：A 維持（本文不加連結，新續文以 reply 指回本文；讀者從本文找不到串尾追加的後半段）／B 本文與回覆被切斷時，底部一律加「⬇️ 更多內文」連到第一則續文，hash 用含連結的版本算（穩定，不會每輪重編）；代價：建立長文時多一次編輯、套用後活躍串裡有續文的約 7 篇本文重編一次。建議 B：每個被切斷的區塊都有往下的連結，修改變長（有史以來 8 篇）或變短再變長時都讀得到全文。
- ~~BH-Q9~~ **已定案 A**（第 3 輪，不改程式）：**刪文／被擋下的大幅刪減，Discord 上要不要標示**：A 維持現狀，保留原文、不標示／B 保留原文並標示「原文已刪除」「作者已大幅刪減，此處保留原版」／C 跟著刪。B、C 都要先改 scraper：刪文偵測沒做（`is_deleted` 從沒被設成 true，0 篇），API 也沒回傳 `update_blocked`／`is_deleted`。建議 A：目前 0 篇偵測到刪除、被擋下的有史以來 1 篇，照先前決定等遇到實際刪文案例再做偵測（見記憶「Bahamut 刪文偵測待辦」）。

**刪除與大幅修改的現況（2026-10-02 查證，唯讀）**
- 刪除：scraper 沒有偵測（`is_deleted` 欄位存在但沒有程式設定它，0 篇）；API 只回傳未刪除的，但因為從沒標記，等於刪掉的文章照樣回傳資料庫裡的版本 → Discord 一直保留原樣（等於存檔）。整串在巴哈被刪，scraper 不再抓到、過幾天離開轉發範圍，Discord 上留著。
- 大幅刪減：原文 ≥500 字、新版縮到一半以下 → scraper 擋下、保留舊版（`update_blocked`，有史以來 1 篇）→ Discord 保留舊版、不標示。新內文是空字串時這道檢查不生效（`new_len > 0`），會直接覆蓋；19 篇被改成空白的都是原本就 0～74 字的短回覆（像只貼圖），不是刪文。
- 一般修改：2,433 篇有修改紀錄，近 30 天 200 篇（±10% 108、變長 76、縮 10～50% 13、縮一半以下 2）。Discord 跟著更新：本文首段＋續文逐則更新，多出的續文改「（此段已更新移除）」，不夠的追加在串尾（reply 前一則）。

**定案（使用者 2026-10-02 第 3 輪）**：BH-Q6 選 B、BH-Q9 選 A。使用者擔心「連結算進 hash 會不會每輪都判定不同」→ 說明：hash 比的是我們上次寫的與這次該寫的，連結目標是存在 state 的第一則續文 id、建立後不變，所以只在內文／推數變動、第一則續文出現或全部清空時才不同；已用測試守住（同資料兩輪 0 次編輯）。
- BH-Q6 實作：`_add_continuation_link()`（有續文切塊且有續文 id 時，本文描述尾端加 `_continuation_nav(第一則續文)`）；增量更新改成**先** `_update_continuations` 再算本文描述與 hash；建立時 `_link_post_to_continuations()` 在續文發出後回頭補連結，回傳 Discord 上實際的描述記 hash（補失敗記沒連結的版本，下一輪補）。主文、回覆、更新時新增的回覆三處都接上。舊的 hash 為空（從沒被更新過的舊資料）仍走「只記不編」，那些本文不會補連結（少數，接受）。
- 測試：再加 5 項（同資料兩輪 0 次編輯並指向第一則續文、變長追加在串尾也連得到／改回短的拿掉連結且穩定、建立時補連結失敗下一輪補、套用前的長文只補一次）＋既有續文增減測試改成「從本文開始順著連結讀」；共 24 項，完整 744 項全過、連跑 5 次都綠、26 種突變全紅。
- BH-Q5 修復腳本：`scratchpad/repair_stuck_slots.py`（session 暫存，內容見本段描述）；10:48 試跑（只讀）：log 圈出 31 則回覆，31 格全部不一致（其中 20 格仍顯示「等待更新中」），62 格已一致不動。**11:00～11:02 執行完成**：已修 31 格、期間 bot 0 次 429；11:03 只讀重跑：0 格不一致、93 格全對。

**定案（使用者 2026-10-02 第 2 輪）**：BH-Q5 選 B、BH-Q7 選 B、BH-Q8 選 A。
- BH-Q7 實作：增量更新開頭若討論串已封存，且沒有新回覆 → 整輪跳過（不編、不存 state，hash 留舊值，變動累積）；有新回覆 → 先 `thread.edit(archived=False)`（發文本來就會解除封存；未上鎖時只需要發言權限），再照常處理，累積的變動一起補上。
- BH-Q8 實作：`new_reply_idx = len(existing_sns)`（主文是 #1，已含在內）。既有的錯編號要等該則推數變動、本文重編時才會改正（hash 不含標題）。
- 測試：新增封存串、編號各 1 項，共 20 項；完整 740 項全過；21 種突變全紅。
- BH-Q5 一次性修復：套用＋重啟後、新程式跑完第一輪再執行（重算當下 log 圈出的清單）。

**上線驗證（2026-10-02 11:16 那輪，新程式第一輪）**
- 429：舊程式 10:16 那輪 104 次 → 新程式 **0 次**；整輪沒有 WARNING／ERROR。
- 排隊：3.7 劇情串這輪編 31 次，相鄰間隔全是 6～7 秒（最短 6），11:16:28 開始、11:20:18 完成。
- 編輯種類：回覆本文 44、留言格 29、主文 14、新增回覆 6、溢出格 3、續文 2。
- 連結：活躍串裡有續文的 7 篇全部「本文有連結→第一則續文、續文導航完整」（含早上確認被洗掉的 9099/107821、14859/109620）。
- 50 串中 49 串完成；沒完成的 19071 是「無音區」分類，在 `bahamut_exclude_categories` 裡，本來就不轉發。

**下一步**：~~commit~~（`b11df27`）。之後觀察：每天 429 是否維持 0、熱門串單輪耗時（最多約 117 次編輯 ≈ 12 分鐘）是否影響到下一輪。

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

- **巴哈變慢另案**（見盤點紀錄 22:5x）：取樣 22:34 那輪執行緒 300 次，70% 在刻意的睡眠、21% 等網路、7% 跑 CPU，所以不是被擋或網路慢；請求一次只要 0.2 秒、每輪存的樓數也沒變，卻多花 4 倍時間（兩輪都是抓 74 分鐘＋寫 4 分鐘），原因還沒找到；每輪都比排程間隔長，每小時會有約 18 分鐘兩輪同時在抓。巴哈 logger 等級是 WARNING（`scraper/config.py`），逐筆請求不會寫 log，目前數不到每輪發了幾次請求。
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
last_confirmed: 2026-10-02
depends_on: event-announce-link-and-dedup-fix
affects: 排程、身份組、config.json
-->

> 已上線：9/29 20:00 第一則正式提醒（矩陣結束前、正常 @）已實發；面板 9/30 04:10 自動更新並置底；使用者 10/01 確認手機通知正常（靜音與正常 @ 都對）。完整設計、週期與版本日推算、部署紀錄已歸檔到 `TODO-completed.md`「週期活動提醒：深塔海墟（歸檔 2026-10-02，原 2026-09-29）」。

**待驗**
- [ ] 10/7 04:00 第一則「矩陣開放」靜音提醒（S2-3）。
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

## 新成員歡迎訊息：接手 ProBot（已上線）

<!-- @meta
id: member-welcome-message
type: STATE
status: confirmed
last_confirmed: 2026-10-02
affects: settings/channel_registry.py, services/community/member_welcome.py（新）, discord_bot.py, test/test_member_welcome.py（新）
-->

> 已上線：9/28 15:04 綁定「歡迎」頻道，10/01 07:59 首次實發歡迎訊息。設計與實作紀錄已歸檔到 `TODO-completed.md`「新成員歡迎訊息：接手 ProBot（歸檔 2026-10-02，原 2026-09-28）」。

- [ ] ProBot 的歡迎功能關了嗎？（log 查不到，待使用者確認；沒關的話新成員會收到兩則歡迎）

---

## 活動自動發布：連結指向錯誤 + 重複建活動（已上線）

<!-- @meta
id: event-announce-link-and-dedup-fix
type: STATE
status: confirmed
last_confirmed: 2026-10-02
depends_on: event-announce-auto-schedule
affects: services/events/event_scheduler.py, services/events/event_time_parser.py, services/relay/article_monitor.py, services/state_db.py
-->

> 原始功能區塊已於 2026-08-18 歸檔至 `TODO-completed.md`（id: `event-announce-auto-schedule`）。
> 本區塊是它重開的修正輪，只記這次改了什麼與為什麼。
> 修正已上線（9/30 有升級既有活動的紀錄）；四軸升級的理由寫在 `event_scheduler.py` 的 docstring，墓碑也有程式註解。完整的症狀、根因、實測數據與設計推演已歸檔到 `TODO-completed.md`「活動自動發布：連結指向錯誤 + 重複建活動（歸檔 2026-10-02，原 2026-09-22）」。

**待辦**
- [ ] 對抗性複查還有 2 個面向（embed／parser）與驗證階段未跑完，結果出來要再過一次
- [ ] 下一篇含活動的公告進來時，確認遷移摘要是「新發現 0 組，先前已標記 1 組」、沒有 ERROR（9/30 16:38 之後還沒有新的指紋遷移）

### 殘留風險（已知未做）

- 活動段落片段與轉發訊息內容來自兩套解析（`strip_html` vs `html2text`），文字可能略有差異
- 超過 4,000 字的公告（全庫 23 篇）仍只轉發前 1,200 字，其餘靠官網連結
- `created_events` 無清理機制，已結束的列會持續累積（線上 32 筆中 23 筆已是孤兒）
- 使用者手動刪掉的活動不會被**自動來源**重建（墓碑）；`/resend_article` 是唯一解得開的入口
  （人明確要求重抓才算數）。活動若還在伺服器上就解墓碑走升級，已被刪掉才整列丟掉重建
- 官方改期到完全不重疊的新區間時不自動合併，只 log warning（理由見上）

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

## Persona Agent M7：精簡版發布（2026-09-28 已上線，觀察中）

<!-- @meta
id: persona-extraction-agent
type: STATE
status: confirmed
last_confirmed: 2026-10-01
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

**2026-10-01 唯讀盤點（66 筆精簡版，`data_discord_member_profiles_index` 的 `auto_personality`）**
- 隱私（人工看過上下文，排除誤判後）：居住地 5 人（嘉義 3、桃園 1、海外 1）、具體行程 1（日期＋店名＋時間＋人數）、宗教 1（個人宮廟經歷）、財務 1（持股）；職業、健康、政治 0。關鍵字掃到的另外 4 筆是誤判（「教會」是路邊觀察、「米拉教」是群內角色扮演、「月薪」「投資」是在講別人的梗）。
- 性化：約 6 人的描述直接引用露骨原句。守則（`persona_guardrails.txt` 第 27 條）允許「本人先開黃腔才接梗」，描述寫進去等於長期許可。
- 歸因：同一個引號詞出現在 2 人以上的有 10 個，但多數不是群體用語——「阿喵」「阿狗」「一野」是**群內暱稱**（不是顯示名稱，從顯示名稱自動建的別名表抓不到）、「安可瘋狂」「今汐」是**貼圖名稱**；真正的群體用語是「484」（3 人）、「何意味」（2 人）。KaTsuO 的「喵」語尾（實為叫柔柔喵）仍在。
- **原建議「≥2 人出現就全部不發」會誤殺 47 條**（含 12 條「安可瘋狂」貼圖偏好、克羅「板務搭檔是阿喵」這類真實關係）→ 本輪改建議只比對「口頭禪／語尾／慣用語」類條目，並排除成員暱稱與貼圖名稱。
- 格式：比較句（並非／而非／不只是）11 人、「。；」雙標點 10 人、「DDLC」撞名、Banana／Rie「無法分析」仍在。
- 可重用：招牌梗的 `_SENSITIVE_KEYWORDS`（`llm/persona/signature_tag_extractor.py`，私有常數，已涵蓋疾病、性向、感情家庭、財務、宗教、政治；沒有地名、行程、持股）；`persona_description_rules.txt`（③④ 都讀）。

**待決問題第 1 輪：發布內容的隱私與歸因（2026-10-01 提出）**
- **PA-Q1 擋哪些類別 → 定案（使用者 10-01 原則同意）**：不發布居住地（含國家）、具體行程（日期＋地點／店名）、宗教、財務、職業、健康、政治、性向、感情家庭；寫角色、不寫地點（「線下聚會的發起者」可以，「嘉義」「9/26 某店 13:15」不行）。
- **PA-Q3 性化內容 → 定案 C 不動**（使用者 10-01）：精簡版照舊保留性化條目，也不把招牌梗的 spicy 閘門套過來。
- **PA-Q5 人工校正檔 → 使用者指出自介區已有暱稱**：查證屬實——自介表單有「別人常常叫我什麼（暱稱/綽號）」（18 人填，例：柔柔喵填「柔喵, 阿喵」），他人印象有「你平常怎麼稱呼他？」（9 筆、8 人，例：阿喵、喵董、阿狗）。但 **④ 寫描述時完全沒讀自介與印象**（只有 ⑤ 拿來算版面與標籤），所以 AI 不知道「阿喵」是誰。改建議：暱稱表直接從「顯示名稱＋自介暱稱＋印象稱呼」組出來，**不另做 JSON**；「不發布的詞」也先不做，等規則上線後真的有漏網再說。限制：66 人中只有 18 人填自介，沒填的人（例：被叫「一野」的 Biboolater）抓不到。
- **PA-Q2 擋法 → 定案：只靠 ③④ 的規則，⑤ 不做隱私過濾**（使用者 10-01）：先同意 A（規則＋⑤ 關鍵字後備），實作中看到後備的寫法後改口「住哪裡、持股、宮廟這些沒差，不用過濾，太敏感了」（理由：都是群裡公開講的）→ ⑤ 的隱私關鍵字整段拿掉（含日期＋時間），舊條目照留。校準時的數據留作參考：招牌梗的 `_SENSITIVE_KEYWORDS` 拿來掃精簡版 3 筆有 2 筆誤判（「小三」是玩笑、「信仰」是米拉教角色扮演），這也是當初沒打算直接共用它的原因。
- **PA-Q4 歸因 → 定案：兩個都做，已實作**（使用者 10-01「都做」）。
- **PA-Q6 規則檔要不要跟著放寬 → 定案 B**（使用者 10-01）：規則檔只留健康、性向、感情家庭、政治與具體行程（日期＋店名／地點）不寫；住哪裡、宗教、財務、職業不限制（跟 ⑤ 不過濾一致，AI 重寫時也不會把「住桃園」這類內容慢慢刪掉）。PA-Q1 的類別清單以此為準。

- **PA-Q7 表上沒有的人 → 改由 PA-Q8～Q10 處理**（使用者 10-01 指正：「一野」是糯糯，不是 Biboolater；並提議通抓伺服器暱稱與全域暱稱）：暱稱表原本只收自介或印象有登記的人（64 人中 14 人）。**唯讀查證（Discord API 讀成員清單）**：64 人都還在伺服器；伺服器暱稱與全域名稱不同的有 34 人；糯糯的伺服器暱稱「糯糯 弗糯糯」、**全域名稱「一野shout死你」**、帳號 one_shout321——有抓全域名稱，模型就知道一野是誰。列伺服器暱稱＋全域名稱約 890 字（④ 預算 20,000 token 的約 4%），再加帳號名約 1,540 字。同時發現 ④ 描述裡的歸因錯誤：雞蛋飛「『糯糯』是他的口頭禪」、雲~「口頭禪『肥糯糯』」（糯糯是群友）、Biboolater「群內被暱稱『一野』」（一野是糯糯）。
- **PA-Q8 → 定案 A**（使用者 10-01「好」）：抓顯示名稱＋伺服器暱稱＋全域名稱（不抓帳號名），每晚從 bot 的成員快取讀（`publish.member_names_from_guild`），**不建資料庫**——改名時 Discord 會推送、快取自動更新，存 DB 反而要處理同步。
- **PA-Q9 → 定案、已實作**：⑤ 擋「把別的群友名字寫成口頭禪」的條目（引號詞等於名字的一段、是某段的一部分、或含有某段；單字不算；本人的名字不算）。正式資料唯讀試算擋 3 條，全是真的歸因錯誤：雞蛋飛「『糯糯』是他的口頭禪」、KaTsuO「『喵』語尾…『伺候阿喵吃肉』」、Ἡράκλειος「『阿狗』是他的固定口頭禪」；沒有誤擋。（雲~「肥糯糯」那條沒過門檻，本來就不會發。）
- **PA-Q10 → 定案 A**：Biboolater「被暱稱一野」等 ④ 下次重跑他時修正。
- **加做：名字表標出本人**（使用者問「prompt 裡的 ID／編號識別會不會有問題」時查到的缺口）：指示只給 user_id、`get_current_persona` 對已有版本的人也不回名字，模型不知道本人叫什麼——別人喊「一野」時分不出是叫本人還是叫別人（Biboolater 那條就是這樣錯的）。現在每個人跑時，自己那行排第一並標「（本人）」，規則檔加一句說明。**表上不放 user_id、不編號**：使用者 ID 跟訊息 ID 一樣是長串數字，會被抄成證據（以前擋下的假證據 37% 是別人的真訊息 ID）；編號會跟條目的 ref 混。④ 裡旁人是「他人1」，表不需要也不應該對上代號。試算：名字表 68 人、約 1,050 字（④ 預算 20,000 token 的約 5%）。
- **PA-Q11 白天的名字關聯（插話、/askai）→ 定案 a、b、c 全照建議，10-01 當天已實作（見下方 PA-Q11／Q12 實作）**（使用者問：三種名字要不要統一顯示一種、其他用對照）。
  - 查證：①「顯示名稱」本身就是伺服器暱稱（沒設才是全域名稱），所以實際是「顯示名稱＋另一個 Discord 名稱＋群內暱稱（自介、印象）」；② **人物卡標籤現在用的是自介別名，不是顯示名稱**——同一人在聊天行是「❤️柔柔喵❤️-時渺#4635」、在人物卡是「柔喵, 阿喵#4635」，只靠 #4635 對上；③ 插話 prompt 最近 40 段：聊天發言者中位 6 人、最多 10 人，人物卡最多 3 張——對照只放卡上會漏掉一半以上在場的人。
  - Q11a **主名字統一用 Discord 顯示名稱**：聊天行本來就是；人物卡標籤改成顯示名稱（拿不到才用自介別名）。建議是（成員在 Discord 上看到的就是它）。
  - Q11b **其他名字放一段「名字對照」**：只列這次 prompt 裡出現、且有其他名字的人（聊天發言者＋人物卡的人），例：「糯糯 弗糯糯#1234 也叫：一野shout死你」。估每段多 100～250 字。人物卡標籤不再塞別名（同一資訊不放兩處，也不吃 ⑤ 的預算）。建議是。
  - Q11c **「在講誰」的別名查詢加查成員快取的伺服器暱稱與全域名稱**（部分比對，「一野」對得到「一野shout死你」）。建議是。
  - 要改：散在 7 處的末四碼寫法抽成一個共用錨點函式（聊天行、人物卡、對照段都要用同一個）；插話與 /askai 的 prompt 組裝加對照段；人物卡標籤；別名查詢；⑤ 算預算的標籤長度跟著改（同一套函式）。建議等明早確認今晚的 ④⑤ 結果再做。
- **PA-Q12 末四碼撞號 → 定案 B 自動加長，10-01 已實作**：唯讀實測全伺服器 128 人、活躍 68 人都 0 組撞號（理論機率 4 碼 56%／20%）；錨點每次組 prompt 時現算、不存檔（聊天向量表 31 萬則只有 3 則含這種寫法，都是有人貼的除錯文字）。Q11 之後錨點是聊天行、人物卡、名字對照三處的共同鍵，撞號會把兩人的名字併在一起。**做了 Q11 的共用錨點函式後 B 變便宜**：函式內存一份撞號名單（啟動時與成員加入／離開時從成員快取重算），沒撞號的維持 4 碼、撞號的自動加長——呼叫端不用傳任何東西，今天的輸出完全不變。A 維持 4 碼＋撞號時 WARNING／B 自動加長／C 全部 5 碼。建議改為 B（隨 Q11 一起做）。

**PA-Q11／Q12 實作（2026-10-01 17:xx，使用者「我覺得問題應該不大」→ 當天做，未 commit，要重啟 discord-bot）**
- 共用錨點 `llm/preprocess/person_anchor.py`：`label(name, uid)`／`suffix(uid)`；`refresh(member_ids)` 由 `discord_bot` 在 on_ready、on_member_join、新增的 on_member_remove 呼叫。沒撞號一律 4 碼、撞號的人加長到分得開為止（今天 0 組撞號，輸出完全不變）。原本 7 處 8 個手寫的 `[-4:]` 錨點全換掉；`chat_line._check_anchor_collision` 保留，改成只抓「加長後仍撞」（多半是已離開伺服器的人）。
- 查證錨點有沒有存檔：人物資料各類 0 筆、④ 版本 787 筆 0 筆；`ai_interactions.context_snippet` 有 7,957 筆含錨點，但只在插話的「當時情境」與日記引用前 60 字當背景，不拿來對人，加長不影響。`chat_line` 舊註解說「persona card 文字存了 4 碼」是過時的，已改。
- 共用名字 `llm/persona/member_names.py`：`member_names_from_guild`（從 publish 搬來）、`merge_names(discord_names, listed)`、`name_parts`、`names_member`、`match_members`、`name_map_lines`；儲存層加 `member_profile_store.aliases_for_users`（Null 版回空）。**名字只用空白分段**：照符號拆會把「Biboolater-只剩我沒6命愛彌斯/緋雪/心了」拆出「緋雪」（遊戲角色），問「緋雪什麼時候復刻」會被當成在講他；Discord 名字整個保留、只有自介／印象欄位用逗號等拆。比對規則：等於名字的一段或是某段的開頭（「一野」→「一野shout死你」）；⑤ 另外允許詞比名字長（「肥糯糯」含「糯糯」），問句不允許（整句也是候選詞）。
- 白天 prompt：人物卡標籤改成 Discord 顯示名稱（沒有才用自介別名；問句講自介別名的加分照舊）；插話與 /askai 在 persona_context（`<other_member_profiles>`）尾端加「【名字對照】」，列這次出現且有其他叫法的人；/askai 拿掉舊的逐行別名加註（只有拿到卡的人才有）。找人：插話的 `_resolve_callback_target` 與取卡的別名 SQL 都加上 Discord 名字對到的人。
- 實測（唯讀，最近一次插話的 7 位發言者）：名字對照 5 人、223 字，例「糯糯 弗糯糯#9398 也叫：一野shout死你、我們之間沒有愛」。「一野」同時對到糯糯與另一位顯示名稱「一野的狗」的人——真的有歧義，插話找人時不猜、/askai 兩張卡都撈。⑤ 試算結果不變（9 條：6 條流行語、3 條把群友名字寫成口頭禪），④ 名字表 68 人、1,019 字。
- 守衛新增兩條：手寫錨點（AST：`f"#{x[-4:]}"` 或先切尾巴再 `f"{name}#{short}"`；改前的檔案 8 處全抓到）、自己讀 `.global_name`／`.nick`。AGENTS.md 共用元件表加兩列。
- 測試：新增 `test_person_anchor.py`、`test_member_names.py`，改 `test_persona_agent_publish`；突變 Q 系列 11 種（1 種等價：問句候選詞本來就小寫）、R 系列 7 種、守衛 2 種都紅；完整 718 項全過。突變時發現：同一秒內改檔又還原且檔案大小不變時，Python 會沿用改壞的 .pyc——之後突變一律 `PYTHONDONTWRITEBYTECODE=1` 並清 `__pycache__`。
- **獨立複查（子 agent，唯讀）**：沒有會拋例外、卡 event loop、SQL 參數不符的問題；⑤ 預算用實際資料模擬白天以顯示名稱當標籤，最長 480 字（上限 500）；04:00 新舊模組混用目前安全（前提：重啟前沒人用 `/persona_agent_test` 或手動萃取的「寫入 RAG」）。5 個低嚴重度問題：
  1. **找人比對太寬（已修）**：問句候選詞對 Discord 名字用「開頭」比對，3,408 則真實訊息有 54 則對到人、大多誤中（「沒有」→「阿夢 - 沒有傘的孩子」、「丹瑾」→「丹瑾偶遇全息…」、「su」「mon」→ super、Just Monika），bot 自己也在名單裡。改成**看詞的邊界**：開頭比對要在邊界結束（下一個字換了一類文字或是符號——「一野shout死你」算、「沒有傘的孩子」不算），並排除 bot。重跑同一份模擬：24 則、全是真的叫名字（super、糯糯、DDLC、雞蛋飛…）；附帶「一野」不再對到「一野的狗」（那是「一野的狗」，不是一野）。
  2. **⑤ 擋名字同樣太寬（已修）**：自介別名「棒槌 or 不是棒槌」切出「or」，「sorry」會被當名字；「我們之間沒有愛」讓「我們」被當名字。同一套邊界規則；⑤ 允許詞比名字長時，中文名字在詞裡任何位置都算（「肥糯糯」含「糯糯」）、英文要整個字。實際資料仍擋同樣 9 條。
  3. **撞號的人有一人離開就縮回 4 碼（已修）**：離開者的舊訊息還在聊天歷史，兩人又同錨點 → 加長過的人不縮回（重啟後才會忘，由 `chat_line` 撞號警告兜底）。
  4. 插話的人物卡快取（短 TTL）帶的是當時的錨點與顯示名稱，TTL 內剛好有人改名或撞號名單變動時，聊天行與卡片會不一致——機率極低，不處理。
  5. 人物卡標籤改用即時顯示名稱：白天有人改成比 04:00 長 20 字以上的名字（超過 `BUDGET_MARGIN`），那一行會被丟掉最後一條（不切半句），到下一晚 ⑤ 重算——接受。
  另記：④ 名字表從只列有暱稱的 14 人變成列全部 68 人（不含 Discord 名字時 832 字、約 525 token），已計入 agent 的 token 預算。修正後測試 720 項全過，邊界相關突變 6 種都紅。

**10-02 驗收（使用者 10-01 22:42 重啟，04:00 維護第一次跑新程式）**
- 啟動 gate 720 項全過；22:44 補跑檢查正確跳過。
- ③：「跳過由 persona agent 精簡版負責的 38 人，剩 0 人」，04:00:01 結束（以前約 12 分鐘）✅
- ⑤：寫入 63、失敗 0；擋下 9 條，跟試算完全一致（6 條流行語、3 條把群友名字寫成口頭禪）；已發布的 66 筆精簡版 0 筆含「。；」、0 筆含被擋條目 ✅
- 白天：重啟後 40 段插話 prompt 全部有「【名字對照】」，人物卡標籤是顯示名稱（例「一口氣上吧！ᕕ( ᐛ )ᕗ#9124 也叫：Bentou、阿狗」）✅；重啟後沒人用 /askai，那邊還沒實際看到。
- ④：26 人、ok 23、max_steps 3（9/27 也 3、9/30 也 3，正常範圍；max_steps 照樣寫入，written 26）。
- **發現 A：④ 不會主動修正舊條目**。Biboolater（04:35 重跑）仍有「群內被暱稱『一野』」、雞蛋飛（05:48 重跑、還搜了「糯糯」）仍有「『糯糯』是他的口頭禪」——名字表只是附在旁邊，final_prompt 規定「沒有反證就 keep」，模型沒拿表去回頭檢查。雞蛋飛那條被 ⑤ 擋住；**Biboolater 那條不是口頭禪寫法，⑤ 擋不到，已發布**。→ 待決 PA-Q13。
- **發現 B：④ 的 token 用量變多**：同一批 18 人兩晚對照，中位數 +3,101（名字表本身估約 640 token）；平均 19,633（預算 20,000）；「預算用盡、停止收集」9/30 3 次、10/01 4 次、10/02 9 次；search_messages 225 次（前幾晚 185～192），其中搜群友名字 21 次（前一晚 14 次）；接受的變更平均 22.5 條（前幾晚約 19）。推測是新規則第一晚在回頭改舊條目、多查證——再看兩三晚，若「停止收集」一直偏高，再考慮把預算加約 1,000 或名字表只列有其他叫法的人（39 人、約 530 token）。
- **PA-Q13 ④ 不修舊的歸因錯誤 → 已手動修正（使用者 10-02 明確同意，09:0x 執行）**。查證：舊條目不會自己被蓋掉——④「沒有反證就 keep」，只有 30 天沒新佐證且搜不到近期例子才刪，Biboolater 常喊「一野」所以永遠搜得到。已知 4 條舊錯誤（都是 keep、證據 2～7 次對話）：Biboolater v19 第 2 項「群內被暱稱『一野』…」（已發布）、雞蛋飛 v19 第 7 項「『糯糯』是他的口頭禪…」、KaTsuO v9 第 1 項「『喵』語尾…」、Ἡράκλειος v12 第 7 項「『阿狗』是他的固定口頭禪…」（後三條被 ⑤ 擋住未發布）。**做法**：版本表只增不改——每人寫一個新版本，其他條目照抄，只把那條改成 revise（換文字、證據不動），notes 註明手動修正、model=manual；舊版本留在表裡就是備份，另把四人目前最新版本匯出到 `logs/persona_manual_fix_2026-10-02.json`；回復＝再寫一版抄回舊內容。改寫建議：①「常拿『一野』稱呼糯糯來吐槽（…）」②「常拿群友糯糯的名字玩梗，還會變化用法（…）」③「常拿阿喵（柔柔喵）開帶色玩笑（…），接到含『喵』的梗會順手延伸成色色暗示」④「常拿群友阿狗當吐槽對象（…）」——都不含口頭禪字眼，⑤ 會發布。待決：改寫或刪除（建議改寫，保留互動資訊）、立刻只替這 4 人重新發布或等今晚 ⑤（建議立刻，Biboolater 那條正掛在插話與 /askai 上）、A（final_prompt 加規則）先不做，看之後有沒有新錯誤。
  - 執行結果：備份 `logs/persona_manual_fix_2026-10-02.json`（四人修正前的最新版本整列＋已發布精簡版）；寫入新版本 Biboolater v19→v20、雞蛋飛 v19→v20、KaTsuO v9→v10、Ἡράκλειος v12→v13（只改那一條，type=revise、證據不動、reason 留原文；model=manual）；用 ⑤ 同一套 `build_plans`＋`index_auto_personality` 只替這四人重新發布，四人舊錯誤都已不在精簡版；改寫後的條目 Biboolater、KaTsuO、Ἡράκλειος 有排進精簡版，雞蛋飛那條（2 次對話）排序在後、沒進。回復方式：讀備份檔的 changes，再寫一版抄回去並重新發布。今晚 ④ 若重跑這四人，會以手動版為基準。A（final_prompt 加規則）先不做，觀察有沒有新錯誤。

**PA 第 1 輪實作（2026-10-01，未 commit；④⑤ 不用重啟、今晚 04:00 生效）**
- 規則檔 `persona_description_rules.txt`（③④ 共用、即時生效）加「不要寫進描述的」：健康、性向、感情家庭、政治（PA-Q6 放寬後）、具體行程寫角色不寫日期店名、叫別人的暱稱不是口頭禪（有附【群友的稱呼】時以它為準）。
- ④ 暱稱表：`publish.member_nicknames`（自介「別人常常叫我什麼」＋印象「你平常怎麼稱呼他」，顯示名稱當標籤）→ `agent.nickname_note` 排成【群友的稱呼】→ `batch.load_nickname_note` 整批讀一次、經 `ToolContext.nickname_note` 附在給模型的指示後面；讀不到就不附、不擋整批。手動 `/persona_agent_test` 也附同一份（這處要重啟才生效）。實際資料：16 人、323 字；沒填自介的人抓不到（例：被叫「一野」的 Biboolater）。
- ⑤ 群內流行語：`publish.find_group_slang` 看每人最新版本的全部條目，同一個詞在 ≥2 人的描述裡被寫成口頭禪（口頭禪／語尾／口癖／慣用語／固定用語／語氣詞）就是流行語，那些條目不發、不佔預算；群友暱稱與顯示名稱不算、講貼圖的條目不算。擋下的每條寫進 log「persona 精簡版擋下群內流行語」。唯讀試算：擋 6 條（「484」3 人、「何意味」2 人、「全對」1 人——另一人被寫成口頭禪的那條沒過門檻，但同樣算進人數）。
- ⑤ 條目句尾的「。」拿掉，不再出現「。；」（試算 0 筆）。
- 不反對就照做的預設：「每條要能單獨讀懂、不寫比較句」④ 的 `final_prompt` 本來就有（現存 11 人的比較句是舊條目）；**DDLC 撞名、意思重複的條目用 embedding 去重這次沒做**（前者動到插話／askai 讀取端的標籤，後者 ⑤ 要多打 embedding），排到之後。刪 Banana、Rie 仍待使用者同意。
- 測試：`test_persona_agent_publish`（流行語、暱稱、句號、build_plans 全路徑）、`test_persona_agent_loop`（暱稱表附在指示後、規則檔與表頭同名）、`test_persona_agent_batch`（整批一份、讀不到不擋）共 16 項新測試；12 種突變都紅；完整測試 695 項全過。
- **名字擴充（PA-Q8～Q10，10-01 16:0x，未 commit）**：`publish.member_names_from_guild`／`member_nicknames(persons, member_names, people)`／`name_parts`／`withhold_reason`；`build_plans`／`production_skip_list`／`run_publish` 多收 `member_names`（③ 的跳過名單與 ⑤ 用同一份名字才會一致）；`batch.load_member_nicknames` 整批讀一次、每人 `nickname_note(..., target_id=)` 標本人；`discord_bot.py` 的 `_display_names()` 換成 `_member_names()`；手動萃取與 `/persona_agent_test` 也傳同一份。測試新增 9 項、改 5 項，10 種突變都紅，完整 701 項全過。**要重啟 discord-bot 才拿得到全域名稱**；不重啟的話今晚舊的主程式只傳顯示名稱，新 ④⑤ 照樣能跑（名字表少了全域名稱、⑤ 的名字規則只比對顯示名稱與自介印象）。
- **為什麼不重啟也會生效**：bot 11:22 啟動後沒跑過 persona agent（log 查證），`publish`／`batch`／`agent`／`tools` 都還沒載入，04:00 才延遲 import，會一起載入新版；`store` 已載入但沒改。重啟也可以（避開 04:00～07:30）。

**待決問題第 2 輪：③ 怎麼退場（2026-10-01 提出）**
- 事實（log 查證）：⑤ 9/29、9/30、10/01 三晚都寫入 63 人、失敗 0（另 1 人精簡版是空的）；③ 9/30、10/01 各對 37／34 人跑 LLM 約 12 分鐘，**寫入都是 0**（全部被跳過名單擋下）；那 1 個空精簡版的人不在 ③ 的門檻（14 天 10 則）內，③ 也沒替他寫。
- 牽動點（刪 ③ 時一起處理，不用另外決定）：③ 兼任維護的「執行中」鎖（遇鎖整個維護返回、④⑤ 不跑）→ 改成維護自己的鎖；啟動補跑檢查看 `auto_personality` 的 `last_extracted_at` 最大值，⑤ 每晚也會寫，不用改；`register_scheduled_result` 只給 `/personality_extract_status` 看結果，隨指令處理；④ 對新成員原本拿 ③ 的描述當第一次的基準，刪掉後從零開始寫。
- **PR-Q1 過渡 → 定案、已實作（10-01，未 commit，要重啟 discord-bot 才生效）**：③ 先查跳過名單再送 LLM，只替精簡版是空的人跑。改完 ③ 通常 0 人、幾秒結束，④ 提早約 12 分鐘開始。建議做。
- **PR-Q2 什麼時候整個刪 → 定案 A**：10/05 後，⑤ 連續 7 晚 failed=0 且抽查沒有新類型嚴重問題才刪。原標準「⑤ 連續 7 晚 failed=0，且抽查沒有新類型的嚴重問題」，目前 3 晚。A 照原標準，最快 10/05 後／B 現在就刪／C 做完 PR-Q1 就不刪，③ 留作備援。建議 A：今晚起 ④⑤ 換上暱稱表與流行語過濾，先觀察幾晚再拿掉備援。
- **PR-Q3 新成員的第一版描述 → 定案 A 接受空窗**（刪 ③ 時生效）：刪掉 ③ 後，新成員要等 ④ 寫出跨 2 次對話的條目，⑤ 才有東西發；在那之前插話與 /askai 只看得到自介與印象。A 接受這段空窗（④ 的納入門檻比 ③ 寬，通常幾天內就有）／B ⑤ 對還沒發布過的人放寬成 1 次對話也收／C 保留 ③ 只寫新成員。建議 A。
- **PR-Q4 手動萃取指令 → 定案 A 兩個都刪**（隨刪 ③ 一起做）：`/personality_extract`（手動跑 ③、預覽後按「寫入 RAG」）與 `/personality_extract_status`。A 兩個都刪（要看單人用既有的 `/persona_agent_test`）／B 改成手動跑全體 ④＋⑤／C 保留。建議 A（指令收斂計畫本來就要減少指令數）。
- PR-Q1 實作：`personality_extractor._run_personality_extraction_impl` 在分組後就拿掉跳過名單的人（每批只看批內成員的訊息，不影響其他人的上下文），全部被跳過時不打 LLM；回傳不再含被跳過的人（`register_scheduled_result` 與「萃取 N 位」log 會變 0）；手動 `/personality_extract` 沒傳名單，行為不變。測試改成「不送 LLM」並加「全被跳過不呼叫」，突變會紅，完整 696 項全過。**生效要重啟 discord-bot**：`personality_extractor` 已被啟動補跑檢查載入；重啟時補跑檢查會看到 ⑤ 今天 05:49 的寫入而跳過。

**不反對就照做的預設**（隨第 1 輪一起做）：⑤ 串接時修掉「。；」雙標點；④ prompt 加「每條都要能單獨讀懂，不寫跟舊版比較的句子」；同一人意思重複的條目在 ⑤ 用 embedding 相似度去重（之前列為刻意沒處理，但至少 8 人有這個問題）；兩位「DDLC」撞名時標籤加區分碼；回滾步驟寫成文件。⚠️ **需使用者明確同意才做**：刪除 ③ 留下的 Banana、Rie 兩份「無法分析」描述（先備份）。

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
> 已完成的重構與部署驗證項（askai 身份感、人物對照三輪、人設深度重構、智慧女性風格、few-shot 範例檔、`/personality_extract` 背景化與 fallback、萃取 log）與舊的設計備忘，已歸檔到 `TODO-completed.md`「Context / Prompt 優化專區（歸檔 2026-10-02，原 2026-04-19）」；`/personality_extract` 相關待辦會隨 PR-Q4（刪指令）一起消失。

**待處理**
- [ ] `asker_profile.roles` 欄位目前為 `(未啟用)`，未來可填 Discord 身份組名稱 + 權限層級（admin/moderator/member）
- [ ] **/askai 指定 thread 查詢**：情境 A（人在 thread 內 `/askai`）已支援；情境 B（在他處指定 thread）不支援，因 slash command 無 thread 參數 + pgvector metadata 無 `thread_id` / `parent_id`。兩方案：Minimum 版（加 thread 參數 + retriever 吃 thread.history，≤3 處改動）/ 完整版（Minimum + chat_persistence 寫 thread_id + RAG 加 thread 過濾，需 migration）。AI 建議先 Minimum 版，使用者未選。
- [ ] **使用者指令記憶 `/remember`**：詳見 [使用者指令記憶專區](#使用者指令記憶-remember-未來工作)
- [ ] 觀察 /askai 執行時音樂機器人是否還會斷音；若仍斷，考慮 BM25/embedding 隔離到獨立 ThreadPoolExecutor（治標）或 ProcessPoolExecutor（治本但 IPC overhead 高）（未證實，log 查不到）

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
last_confirmed: 2026-10-02
-->

> **目標：** 在白名單的一般聊天頻道裡，AI（柔喵）**沒人叫也會偶爾冒一句**，讓群聊更活；被 **@ 或 reply 時一定回**。定位是「彩蛋式偶爾插話」，**不是**功能一那種「專屬頻道全程參與」。寧可少講講得巧，也不要每句都插變噪音。
> Phase A、B、C-1～C-3 都已上線，2026-08-09 的自然插話重構也已上線並實測。原本「兩顆模型、12B 常駐」的架構已作廢（ambient、主模型、人格萃取現在是同一顆）。完整規劃、各 Phase 實作與自然插話重構的推演已歸檔到 `TODO-completed.md`「AI 偶爾插話（功能二）與自然插話重構（歸檔 2026-10-02，原 2026-06-21／2026-08-09）」。

**待做**
- [ ] **C-4 自我進化迴圈**（閒置批次）：consolidation（合併重複、衝突取新記「以前X現在Y」）、decay（久未重提降權/封存）。**未做**。
- [ ] **C-4 隱私公告**：綁定插話頻道時自動置頂 + 改 channel topic。**未做**。
- [ ] **C-4 選配監督面板**（不擋流程）：查/改/刪/禁記；複用 `/personality_extract` UI 模式。**未做**（接口 `MemoryService.list_facts/forget` 已備好）。
- [ ] **觀測 / Debug 面板（使用者要求 2026-06-21，重要）**：使用者**不想用 CLI/log debug**，未來要一個 **Discord 面板** 能看：每次插話的**完整 prompt（含三層 context）**、決策狀態（reply/pass/error）、三層 context 數量（chat/persona/memory）、記憶 flush 狀態、某人記得的偏好。**取代** `ambient_prompt.txt` + grep。可與「記憶監督面板」合併成一個「AI 狀態/觀測面板」。**現況暫用**：`discord_bot.log` 的 `ambient 生成 …chat/persona/memory` 摘要 + [`/logs/ambient_prompt.txt`](src/llm/ambient/ambient_reply.py)（`AmbientChatSettings.debug_log`）；面板做好後轉成資料來源。
- **延後（非 v1 必要）**：`retrieve_discord_context` 泛化吃 channel 的 hybrid 長期對話召回——觸碰 /askai 核心、風險高，等 B 的 persona 召回不夠用再做。

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
