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
- 2026-10-27 23:xx（**RG-Q24 做好：A′＋B′＋C′**；使用者「做」）：①`http_client`：`is_backend_fault(exc)`＝連不上、逾時或 5xx（後端本身的問題）；`backend_looks_broken(exc)`＝5xx 且 body 帶 `ErrorDeviceLost`／`device lost`／`decode() failed`／`vk::`／`CUDA error`／`HIP error`；sync 與 async 的 `_post_json` 收到這種 5xx 就走既有的 `_try_heal_lemonade_backend(model, reason)` 重載那顆模型再重送（沿用 60 秒冷卻、`save_options=False`），看不懂的 5xx 照一般重試不重載；自癒加**每模型一小時最多 3 次**（`_LEMONADE_HEAL_HISTORY`），第 4 次放棄：記一次 ERROR、一小時內不再吵；事件（healed／failed／gave_up，帶 model、reason、heals）經 `set_heal_listener` 交出去，回呼出錯只記 WARNING 不影響請求。②`embedding_client` 四處 `is_unreachable` 改 `is_backend_fault`：5xx 不加空白重試、不逐筆。③`store_chat._is_backend_unreachable` 改看 `is_backend_fault`：5xx 放回 buffer、停這輪；中止的 log 依 `_fault_level` 分級（連不上 WARNING、5xx ERROR）。④`dm_notifier.lemonade_heal_notice`／`notify_owner_lemonade_heal(bot, event)`（`OWNER_ID` 沒設不送）；`discord_bot.setup_hook` 掛 `set_heal_listener(self._on_lemonade_heal)`，回呼用 `loop.call_soon_threadsafe` 排回 event loop 再 `spawn` 私訊。測試：新 `test_lemonade_heal`（訊號、sync／async 重載一次、看不懂的 5xx 不重載、冷卻、每小時上限與只吵一次、重載失敗事件、回呼出錯不炸、通知三種文案、OWNER_ID 沒設不送）10 個；`test_embedding_retry` +1、兩條「文字問題」改用 400 模擬；`test_chat_persist_retry` +1（5xx 放回、停、ERROR 一次）；突變 8 刀全紅；相關 180 個測試綠；ruff 過。AGENTS 共用元件表「判斷後端連不上」那列補上。**要重啟 discord-bot 才生效**。
- 2026-10-27 22:4x～23:0x（使用者「你下指令重啟 lemonade 看會不會又壞」＋「連續 500 可以嘗試送重啟指令，之前好像有做，討論怎麼做比較安全」）：bot 碰不到 Windows 主機的 Lemonade 行程，能做的「重啟」是 admin API 全部卸載再載入（後端 llama-server 行程重開）。腳本 scratchpad `rag/lemonade_cycle.py`，在 GPU 閘門裡做兩輪：三個模型卸載（主模型 2.6／0.6 秒）、照 bot 的 options 載回（主模型 12／10 秒、embedding 與 reranker 各 1.5 秒），每輪之後 embedding 兩次、rerank、chat 都正常（chat 24.6／20.6 tok/s）——**重啟沒有再壞**，今天的裝置掉是偶發。查證「之前好像有做」：**有**，`http_client._try_heal_lemonade_backend`——Lemonade 回「200＋error 信封 network_error」（admin 活著但它轉發的後端行程卡死）時重發 `/api/v1/load` 重生那顆後端，每個 (host, model) 60 秒冷卻、`save_options=False`，sync／async 兩條路都接，embedding 也走它。**今天沒觸發的原因**：後端有回應、回的是 HTTP 500 body `decode() failed: vk::Queue::submit: ErrorDeviceLost`，不是 wedge；500 照一般 5xx 重試兩次後丟 `LlmAPIError`，`store_chat` 當單則錯誤略過。討論內容與選項寫在 RG-Q24。
- 2026-10-27 22:xx（**RG-Q23 做好：topic 加統計、規則檔改行為類題用 topic、contains 範圍**；使用者「做」）：`chat_search.topic_search` 改撈 `topic_tally_limit`＝100 則（`search_chat` 折疊後）、距離超過 `topic_max_distance`＝0.5 的不算，回 `results`（最像的 8 則例句）＋`speakers`（每人幾句，同一句重複講的算次數、每人附 2 句）＋`counted`＋註明「只數最像的 N 句、不是全庫」；工具多一個 `contains` 參數，phrase 多一個 ILIKE 條件、topic 交給 `search_chat` 新的 `text_contains`；ILIKE 樣式抽成 `context_retriever.ilike_pattern`（兩處共用）。規則檔重寫第 1～4 條（行為、態度、評價類用 topic 並把那種話寫進 query、要鎖人就給 contains、講清楚次數是什麼的次數）。測試：`test_chat_search_tool` 11 個（統計、距離上限、contains 兩種模式）、`test_rag_collapse` +1（text_contains 進 SQL 且跳脫）；突變 6 刀全紅；ruff 過。**真資料煙霧**（名字表留空）：topic「嘲笑阿喵 阿喵好廢 阿喵又歪了」＋contains「阿喵」12.4 秒（含 embedding 模型剛重載）、統計 100 句、第一名 26 句（例句「阿喵已經栽贓我很久了」「阿喵 你好噁」）；沒給 contains 的「欺負阿喵」1.1 秒，會混進「欺負動物bad」「欺負我這些菜雞」→ 規則檔要模型對人的問題給 contains；「稱讚新角色很強」4.5 秒、86 句、例句都對題。100 句全在 0.5 以內，上限暫不收緊。**要重啟 discord-bot 才生效**（模組已載入；規則檔是熱讀、已生效）。
- 2026-10-27 18:29～22:4x（**事故：Lemonade 的 embedding 後端顯示卡裝置掉了，聊天向量 4 小時沒寫進去**；agent 修好）：使用者更新 Lemonade 後約 18:29 起，bot 每則訊息的 embedding 都回 HTTP 500，`store_chat` 當成「這則訊息本身有問題」略過，**共略過 639 則**（原始備份表有存；`chat_index_backfill_mode=on` 會每 15 分鐘補 20 則，約 8 小時補完，只補近 14 天的）。錯誤內容（直接打 `/api/v1/embeddings` 才看得到）：llama-server 回 `decode() failed: vk::Queue::submit: ErrorDeviceLost`——embedding 模型綁在 `-mg 1` 那張 Vulkan 裝置，裝置掉了但行程還活著，所以 Lemonade health 顯示 ready；主模型（`-mg 0`）與 reranker 都正常。處理：在 bot 的 GPU 閘門裡用 bot 自己的 admin 呼叫 `unload_lemonade_model` → `_lemonade_load_model`（同一組 options）重載 embedding 模型，8 秒後 embedding 正常（1024 維）、reranker 正常。**教訓**：health 的 ready 看的是行程不是裝置；要看 500 的 body。→ RG-Q24。
- 2026-10-27 16:3x（**使用者更新 Lemonade 到 2026.43.3，請 agent 測試**；腳本 scratchpad `rag/lemonade_check.py`，走 bot 的客戶端與 GPU 閘門）：chat、embedding、rerank 三個端點都正常；同一份 802 token 的 prompt 連打四次：①只有主模型 cached 0、15.8 tok/s（冷）→ 載入 embedding（1.9 秒）→ ②cached 798、18.7 tok/s → 載入 reranker（1.7 秒，分數 [1.0, 0.0] 正確）→ ③cached 798、18.9 tok/s → ④18.7 tok/s。**三個模型同時載著，主模型的快取沒被清、速度沒掉**；16:09 那題掉到 6～7 tok/s 的現象在新版重現不出來（那題 cached=0 更可能是 prompt 本身變了：聊天視窗不同），先當作舊版或當時負載的問題，繼續盯真實 /askai 的 `llm_usage`。使用者另提「回答偏互動、沒查到『欺負』、變成數字統計機器」→ 提了改法（topic 模式加計數、規則檔改行為類問題用 topic、選配 contains 範圍、之後可加 reranker 判態度），等使用者說做；見 RG-Q23。
- 2026-10-27 16:09～16:14（第二題「誰最常欺負阿喵」）：模型同一輪叫了兩次 `chat_search`——phrase「阿喵」（兩個字、全表掃描 7.6 秒、2,340 筆）與 phrase「6+5」（走索引 54 ms、230 筆）；回答把「提到阿喵最多的人」當成欺負排行（500／388／一百多次，附例句「阿喵又課金ㄌ?」）、還調侃一句，意思對得上但「次數」其實是提到名字的次數，模型有明講「光阿喵兩個字就說了 500 次」。**效能觀察（n=1，要再看）**：這題用到了 reranker（`reranked=30`，16:09:09 Lemonade 載入 Qwen3-Reranker-0.6B），接著主模型 prompt 全未快取（cached=0、34.7 秒）、生成只有 7.4／6.2 tok/s，整題 5.5 分鐘；第一題沒用 reranker（等 GPU 逾時照融合名次）是 27.2／19.5 tok/s。懷疑 reranker 載入後和主模型一起佔 VRAM、主模型被擠到慢路徑；重啟後只有這兩題可比。要盯：之後幾題 `llm_usage feature=ask` 的 tok_s 對照 `reranked=`；若一直這樣，選項 A 把 `askai_rerank_mode` 關掉（只差前 30 則的重排）、B 查 Lemonade 能不能用完就卸載 reranker。兩個字的 phrase 在負載下 7.6 秒也記一筆（索引幫不上）。
- 2026-10-27 16:0x（**聊天搜尋工具真模型驗收：通過**；使用者在 Discord 問 /askai「誰常常說嚇哭了」）：模型第 1 輪就呼叫 `chat_search`，自己把問法剝掉、query＝「嚇哭了」、mode＝phrase，316 ms、76 筆命中；回答點名最常說的人 47 次、全在同一個頻道、最近一次兩天前，第二名是發問者本人 8 次、第三名 5 次，還順口調侃發問者——對照資料庫 ILIKE 計數 47／8／5，第一名就是考卷 c05 的答案。耗時：第一次模型呼叫 prompt 11.9k token 全未快取（重啟後第一題）35 秒、工具 0.3 秒、第二次呼叫約 20 秒；同時出現「重排等 GPU 超過 10 秒，照融合名次」（顯示卡被第一次 prompt 佔著，是既有的退路）。回應紀錄的 `chat_search_meta` 有完整經過。使用者另問「誰最常罵你能不能找出來調侃」：目前只有插話的 `ambient_insult.grudges` 記 7 天內罵過它的人（給插話冷處理與心情註記用），/askai 看不到；`chat_search` 的 phrase 要有具體的字才能數、topic 只能找幾則例子，「最常罵」排名不可靠。選項：A 把 grudges 給 /askai（prompt 一段或小工具，只有 7 天）；B 讓 `ambient_insult` 長期累計次數（要存表）；C 不做。未定。
- 2026-10-27 15:49（**使用者重啟 discord-bot**）：啟動 gate 87 項 OK（26 秒）、同步 20 個全局斜線命令（多了 /ping）、15:49:03 連上 Gateway；重啟後沒有「不認得的開關」warning（`askai_chat_search_mode`、`chat_vector_index` 都認得了）；Telegram 啟動補償 3 筆照常。聊天搜尋工具的真模型驗收等使用者用 /askai 問一次再看 log「askai 聊天搜尋」。
- 2026-10-27 17:xx（使用者「把驚嘆號開頭的指令移除、都改用斜線」→ **已做**）：`test_commands` 的 `!ping`、`!helloworld` 拿掉，`/ping` 做成斜線（只有本人看得到的 Pong）；`discord_bot` 的 Bot 改 `command_prefix=commands.when_mentioned, help_command=None`（Bot 必填前綴，給一個只有 @bot 才觸發的；內建 `!help` 一起關），`on_message` 尾端的 `process_commands` 拿掉。新守衛 `test_shared_conventions`「指令一律用斜線」：擋 `@commands.command(`／`@bot.command(`，突變（加回一個前綴指令）會紅。守衛、import 解析、分層測試 40 個綠，ruff 過。重啟後生效。
- 2026-10-27 17:xx（使用者問「群友呼叫機器人指令不會被寫進向量吧」；查證、未動 code）：不會。斜線指令是 interaction、不是訊息，`on_message` 看不到；bot 公開貼的「問題＋回答」是 bot 的訊息，`store_chat.enqueue_message` 第一行就擋 `author.bot`。前綴 `!` 的指令只剩測試用的 `!ping`、`!helloworld`，群友打了會當一般訊息存（沒有前綴過濾），但全表 34.6 萬列裡 `!` 開頭只有 20 列、全是「!? 誰被鎖?」這類感嘆，不是指令；`/` 開頭 17 列。不加過濾。
- 2026-10-27 16:xx～17:0x（使用者：guild_id「做」、pg_trgm「補」→ **兩件都做完**）：①`store_chat._make_node` metadata 多放 guild_id（詳見 RG-Q22），`test_chat_persist_retry` +1、突變 1 刀紅。②由 agent 建索引：`CREATE EXTENSION pg_trgm` 0.6 秒、`CREATE INDEX CONCURRENTLY discord_messages_idx_text_trgm … gin (text gin_trgm_ops)` **6.5 秒、89 MB、有效**（估的 100～200 MB 與幾分鐘都偏高：訊息短、重複多）、ANALYZE 32 秒。EXPLAIN 工具的字面查詢「好了啦」：Bitmap Index Scan 讀 177 頁（全表掃描是 84,900 頁），執行 0.41 秒含冷讀；兩個字的「哇糙」照舊平行全表掃描 2.5 秒（冷）。透過工具量：「好了啦」0.0 秒、「哇糙」0.2 秒（熱）、「不要瞎掰好嗎」0.1 秒。寫入成本：每則新訊息多一個 GIN 項目，聊天寫入是批次、影響看不出來。索引清單現在：7 個 metadata／主鍵索引＋HNSW h512 371 MB＋trgm 89 MB。**完整測試 1,818 項：只 1 紅是 `test_telegram_scraper_media` 的 `@timing_sensitive` 補掃測試（靠真實時間，容器忙就會差幾十毫秒），單跑 41 個全綠、前兩次完整跑也綠，和這批無關。**
- 2026-10-27 16:xx（使用者問三題：guild_id 要不要現在塞、門檻數字的意義、pg_trgm 是什麼；討論、未動 code）：①查證 `store_chat`：buffer 有收 guild_id，但 `_make_node` 組 metadata 時沒放進去，所以**連今天新寫的 314 列也沒有**；回填 34.6 萬列＝改寫每一列的 jsonb，6 個 metadata 表達式索引與 HNSW 都要跟著長新項目（非 HOT 更新），比早上掃 15 分鐘的那次 UPDATE 更久、索引膨脹到 VACUUM 才回收，而現在只有一個伺服器、沒有任何查詢用它 → **建議不回填**；要做就只做寫入端一行（`_make_node` 把 guild_id 放進 metadata，之後多伺服器時舊列全是 NULL＝本伺服器，用 `guild_id = X OR guild_id IS NULL` 就分得開）→ RG-Q22。②門檻的意義：距離 0＝同一句、每則訊息最近鄰居約 0.2、前十名 0.25～0.36，0.50 等於「比最近鄰居遠一倍」的鬆標準、0.70 幾乎同頻道的話都過；舊向量讓同一人的句子多像 0.025 是因為名字與 id 也被算進向量；等效門檻 0.446 對 0.45 是雜訊，而且地板內不足 5 則本來就會補滿。③pg_trgm：連續三個字的切片做反向索引，`ILIKE '%句子%'` 先用切片找候選列再比對，不掃全表；兩個字的查詢沒有完整切片、照舊掃描；索引估 100～200 MB、CONCURRENTLY 建幾分鐘。
- 2026-10-27 15:0x～16:0x（**RG-Q16 聊天搜尋工具做好、開關已 on、待重啟與真模型驗收**）：新模組 `llm/retrievers/chat_search.py`（服務層，`test_layering` 已登記）＝`ChatSearchTools`（`ToolRunner`，宣告一個 `chat_search`：query 必填、mode＝phrase／topic、author、channel 選填；規則 `settings/prompts/askai_chat_search_rules.txt` 熱讀）。phrase＝ILIKE 子字串（% 與 _ 跳脫）、**一次掃描的 CTE 同時算「每人每頻道的計數＋最近幾則原文」**、`SET LOCAL statement_timeout` 20 秒（沒索引是全表掃描，逾時回錯誤給模型）、回每人（名字#尾碼）總數、前 3 個頻道的數字、最新日期、最近 2 則原文（`[本地時間 #頻道] 內容`）、最多 5 人、多的人數註明；一筆都沒有自動改走 topic 並註明「不是一字不差」。topic＝`search_chat(candidate_ids=None, collapse=True, min_chars=6, limit=16)` 再過品質閘（純表情、純連結、bot 自己的）裁到 8 則，每則 when／channel／name／text／repeats。author 用模型看到的名字對 `member_names_from_guild` 的名單（可含 #尾碼、可給 <@id>；對到多人回錯誤列候選、對不到回錯誤），channel 對指令層給的頻道＋thread 名單；人標 `person_anchor.label`、不在名單的標「已離開的成員#尾碼」、頻道不在名單標「未知頻道」（封存的 thread 不在快取）。指令層 `_askai_generate`：開關 `askai_chat_search_mode=on` 且在伺服器裡才建工具，`also=[網搜, 聊天搜尋]` 一起交給 `run_with_intel`；經過進 `inputs.chat_search_meta` → 回應紀錄 `chat_search_meta`、log「askai 聊天搜尋 trace= 呼叫=[(mode, query, ms, 筆數或錯誤)]」。細項 `AskAIChatSearchSettings`（phrase 5 人／3 頻道／2 則原文／掃最近 300 則命中、topic 8 則、每則 160 字、逾時 20 秒）；開關定義在 `Switches`、`switches.json` 已設 **on**（舊版 bot 重啟前會記一次「不認得的開關」warning，無害）。**途中改掉的錯誤**：第一版用 `metadata_->>'guild_id'` 限定本伺服器，煙霧測試對真資料回 0 筆才發現**聊天表的 metadata 沒有 guild_id**（34.6 萬列全空；`store_chat` 的 guild_id 只進原始備份表），之前盤點時把 `345993|345993|0` 看反了；拿掉 guild 篩選（bot 只在一個伺服器；多伺服器時要用頻道名單當白名單），`search_chat` 也不加 `guild_id` 參數。第一版兩次掃描在測試套件同時跑、冷快取下花 41 秒，改成一次掃描＋逾時。**真資料煙霧測試**（名字表留空，所以顯示「已離開的成員」）：phrase「好了啦」0.5 秒 174 筆、第一名 #4635 77 次（和考卷答案一致）；phrase「哇糙」0.3 秒 69 筆、#4635 66 次（一致）；topic「不喝水」0.2 秒 8 則，第 2 則就是「但我幾乎不喝水的」；亂打的句子 1.8 秒退到 topic（回的是 ZZZ 相關的句子，有註明不是一字不差）。測試：`test_chat_search_tool` 9 個、`test_askai_flow` +2（開關 on 時工具進工具輪、成員名單與 bot id 交進去、經過進回應紀錄；off 時不建）、`test_intel_search_client` 的原始碼斷言改成新的 `also=` 寫法；突變 9 刀全紅（bot 自己的也算、不跳脫萬用字元、對到多人拿第一個、topic 不過品質閘、退 topic 不註明、時間不換本地、指令層不交工具、經過不進紀錄…）。ruff 對改到的檔案全過（repo 原有的 107 條不在內）。**還沒做、要使用者決定**：①重啟 discord-bot 讓新程式生效（避開 04:00～07:30），重啟後用 /askai 問「誰常說好了啦」「之前有人說過自己不喝水嗎」看 log 的「askai 聊天搜尋」與回答有沒有標人與頻道；②RG-Q21 要不要建 pg_trgm 索引（見該條）；③60 題評估在工具上線後要改成「模型＋工具」的端到端評估才量得到 C 類的進步（現在的考卷量的是 `search_chat` 本身，工具不會改變那個數字）。
- 2026-10-27 14:2x～15:0x（使用者「都依照你的建議」→ **①距離門檻量完、不用改；③評估集進版控做好；RG-Q16 工具開做**）：**門檻**：抽 60 則近 30 天的訊息、h512 索引取 top-10，同一對訊息再算整欄新向量與舊向量 `embedding_v1` 的精確距離：同對距離中位 h512 0.254／整欄新向量 0.272／舊向量 0.216，h512−舊向量 p10/p50/p90 = −0.044/+0.025/+0.117（舊向量內文夾名字與 id，同一人的句子被拉近）；要放過和舊向量 0.45 門檻同樣多的候選，h512 得設 0.446 → **callback 的 0.50／0.70 維持不動**（style_refs 0.45 與 hook 0.50 用的是 `ai_interactions` 自己的向量欄與索引，沒受影響）。callback_debug 預設 True 但記在 DEBUG，正式 log 看不到候選距離；要調參時把 `llm.ambient.ambient_reply` 開到 DEBUG。量測腳本 scratchpad `rag/dist_shift2.py`（h512 對整欄）、`dist_shift3.py`（加舊向量）；第一版 `dist_shift.py` 對整欄做全表掃描、主機端逾時後容器裡殘留一小時（pid 3839，使用者殺掉）——教訓：沒索引的欄別拿來當對照組跑 40 題。**評估集（RG-Q20 做好）**：新資料夾 `src/llm/retrievers/eval/`＝`evaluate.py`（讀 `private/questions.json`、`search_chat` 全庫 top-25 不折疊、Hit@1／5／25 與名次中位、報告 `reports/<時間>-<名稱>.json`，結果走 logger 印到畫面）＋`private/questions.json`（60 題，A12／B8／C20／D20，從 scratchpad 搬來）＋`reports/`；`private/`、`reports/` 進 .gitignore；`test_layering` 登記 `llm.retrievers.eval` 為服務層。`search_chat` 加 `query_embedding=`（整份考卷先算完向量、只排一次 GPU 的隊）與回傳 `channel_id`（RG-Q16 工具要標頻道），問句算向量抽成 `embed_query`。跑法：`docker exec -w /app discord-bot python -m llm.retrievers.eval.evaluate --label 名稱 [--collapse] [--only C,D] [--column embedding_v2]`。**基準報告 `20261027-1429-h512基準線.json`：60 題 38／47／50（A 7/8/8、B 6/7/7、C 7/13/15、D 18/19/20）**，和切換後手刻腳本量的一樣；耗時中位 342 ms（同時在跑量測，之前量 120 ms）。測試：`test_chat_retrieval_eval` 7 個、`test_rag_collapse` +1（交進來的向量不再找模型、列帶 channel_id）；`test_chat_reembed` 與新測試原本讀到正式開關的 halfvec512 而紅，改成明指 full；突變 6 刀全紅（口頭禪不看作者、每題都折疊、Hit@k 用 <、回傳少 channel_id、不理會交進來的向量；Hit@k 那刀第一次沒抓到，補了名次剛好等於 k 的測試）。
- 2026-10-27 14:0x（使用者對「RAG 還剩什麼」五點的回覆；討論、未動 code）：①距離門檻重校「好」→ 量測中（第一支腳本對整欄做全表掃描太慢、主機端逾時，容器裡的行程殘留、agent 無權殺，等它自己跑完再跑便宜版：h512 取 top-10、同一對訊息再算整欄精確距離，比門檻 0.45／0.50／0.70 各放過幾則）；②使用者提醒「/askai 是什麼都可以問的，不是專門搜聊天」→ 確認 RG-Q16 的工具只是第三個工具（情報、網路之外），模型逐題決定要不要用，多數題目不會碰它，視窗內的 100 則照舊；工具的使用規則寫成「問群裡誰說過什麼、誰常說、之前有人提過」才用；③評估集進版控 → RG-Q20（格式照情報搜尋評估、位置另開、題目整份放 private）；④RG-Q14 定案（留一個月再 DROP）、RG-Q15 向使用者解釋「搬到技術層」的意思（reranker 只是打模型的 HTTP 客戶端、不碰索引，放在情報搜尋套件裡讓 /askai 為了它 import 整個搜尋套件；搬到 `llm/client/` 兩邊都從模型客戶端那層拿，行為不變），未定；⑤B-lite 目前**沒有**：/askai 只搜頻道最近 100 則視窗＋情報／網路工具，全庫聊天搜尋今天只有插話回憶在用；維持「工具做完再看要不要加」。舊的整欄 HNSW 索引使用者已 DROP，剩 `discord_messages_idx_hnsw_h512` 371 MB；表 4,316 MB（含 `embedding_v1` 約 1.4 GB）。
- 2026-10-27 13:0x（**60 題走 h512 索引的正式路徑**：`search_chat`、不折疊、top-25、ef 1000）：Hit@1／5／25 = 38／47／50（A 7/8/8、B 6/7/7、C 7/13/15、D 18/19/20），對精確掃描的 512 halfvec 38／48／51、整欄 38／49／50，差一題（「力大磚飛派」精確第 2～3、索引沒撈到）；**60 題共 7 秒、每題中位 120 ms、最大 0.4 秒**（371 MB 的索引整個在快取裡；之前整欄索引冷查 15～98 秒、全表掃熱 3～4 秒）。結論：換 512 維 halfvec 成立。下一步：使用者 `DROP INDEX CONCURRENTLY discord_messages_idx_hnsw`（釋放 2.2 GB、寫入少插一張圖）；之後插話回憶的距離門檻（0.50／0.70）要對 halfvec512 的距離重量。
- 2026-10-27 11:53～13:0x（**h512 索引建好、開關切換**）：使用者建 `discord_messages_idx_hnsw_h512`（`l2_normalize(subvector(embedding,1,512))::halfvec(512)`、halfvec_cosine_ops），11:53 有效、**371 MB**（原 2,217 MB 的 1/6）。`switches.json` 的 `chat_vector_index` 切成 `halfvec512`（agent 改，bot 熱讀到）。EXPLAIN：沒碰過的向量限定頻道 top-100 第 1 次 653 ms（8,945 頁都在 OS 快取，建完就熱）、第 2 次 13 ms，走 `discord_messages_idx_hnsw_h512`。60 題走正式路徑（`search_chat`、不折疊、top-25）評估跑中，結果見下一條；確認後由使用者 `DROP INDEX CONCURRENTLY discord_messages_idx_hnsw`。
- 2026-10-27 12:4x（**GitLab pipeline #2992383887 在 `8c85e80f` 失敗**；使用者貼通知）：`.gitlab-ci.yml` 開頭自己寫著「草稿、還沒推到 GitLab 跑過」，這是它第一次跑。lint 階段＝`ruff check src`（規則 F、E9、B006、B008、B904）；主機與容器都沒裝 ruff，在 scratchpad 開 venv 裝 ruff 0.17.3 重現：**全 repo 107 個錯**（F401 未用 import 56、F541 空 f-string 18、B904 raise 沒 from 13、B008 預設參數呼叫函式 12（全是 scraper/api_server.py 的 FastAPI `Depends()`，慣用寫法，該用 `[tool.ruff.lint.flake8-bugbear] extend-immutable-calls = ["fastapi.Depends"]` 放行）、F841 未用變數 6、**F821 未定義名稱 2**（`llm/mcp_server.py:136` 回傳型別字串 `"uvicorn.Config"` 但 uvicorn 只在函式內 import；`scraper/services/base_scraper_client.py:265` 用到 `curl_cffi` 但只 import 了 `curl_cffi.requests.Session`——這條可能是真的 NameError，待查）。這次六個 commit＋工作目錄改過的 26 個檔裡只有 9 個錯、其中 3 個是這次寫的（`lemonade_gate` GpuBusy 的 raise 沒 from、`test_chat_reembed` 未用的 timedelta 與 report）→ 已修（進快照 11／10），其餘 6 個是舊的。lint 擋住後 unit-tests 階段沒跑，那一階段有沒有別的問題（apt、timing_sensitive 測試）還不知道。**選項（RG-Q19，待定）**：A 清乾淨——`ruff --fix` 處理 72 個安全修正（未用 import、空 f-string）＋手修 B904／F841／F821＋B008 用設定放行，另成一個 chore commit（約一小時、純機械）；B `.gitlab-ci.yml` 的 lint 加 `allow_failure: true` 先看測試階段過不過；C 先不管。建議 A（順便看那兩個 F821 是不是真 bug），做之前先確認你要不要我動 scraper 那些檔。另：快照 tree 原本各自以 HEAD 為底、依序 commit 會互相蓋掉，已改成**累積**（10 含 09、11 含 09＋10），依序 `read-tree` 就是正確的三個 commit。
- 2026-10-27 12:0x～12:3x（**使用者定案換 512 維 halfvec、要能換回完整索引 → 索引 profile 做好**）：設定層 `sys_settings.pgvector_settings.ChatIndexProfile`／`CHAT_INDEX_PROFILES`（`full`、`halfvec512`：ORDER BY 表達式、查詢向量轉換（取前 N 維重新正規化）、建索引 DDL 只有一份）；開關 `chat_vector_index`（`switches.json`，預設 `full`，改檔即生效、不用重啟；對不上索引只會退回全表掃描變慢、不會錯）；`search_chat` 照 profile 組 dist 與 ORDER BY。測試 2 個（full 維持 `embedding <=> %s::vector`；halfvec512 的表達式、512 維正規化的字面、DDL 同一表達式），突變 2 種都紅；相關 5 檔 82 個綠、第十一次完整測試全綠（skipped 2）。AGENTS 共用元件表加一列（沒加守衛：`<=>` 在情報索引與 ai_interactions 也合法出現，規則難用 grep 表達）。快照 11 `3d99ff3bedab5a6c570c1a8738edfafe7b147c48`（累積含 09、10），訊息 `feat(rag): add index profiles so the chat search can run on a 512-dim halfvec HNSW index`；body：the table keeps the full 1024-dim vectors; a profile is an expression index computed at build time, so switching back only needs the other index and a switch flip; the halfvec512 profile measured 38/48/51 against 38/49/50 on the 60-question set while shrinking the index from 2.2 GB to about 0.5 GB; the ORDER BY expression, the query literal and the DDL come from one place so the planner always matches the index.　**下一步（使用者執行）**：建 h512 索引（在 pgvector 容器用 `psql -v ON_ERROR_STOP=1` 餵 stdin，逐句：`SET maintenance_work_mem = '2500MB'; SET max_parallel_maintenance_workers = 0; CREATE INDEX CONCURRENTLY discord_messages_idx_hnsw_h512 ON data_discord_messages_index USING hnsw ((l2_normalize(subvector(embedding, 1, 512))::halfvec(512)) halfvec_cosine_ops);` 建完查 `indisvalid`、`ANALYZE`）→ `switches.json` 把 `chat_vector_index` 改 `halfvec512` → 60 題走索引再量 → DROP `discord_messages_idx_hnsw`。
- 2026-10-27 11:5x（使用者問「原本的搜尋模式不好嗎、新的似乎很吃機器效能」；討論、未動 code）：回答的要點——舊模式（每次全表精確掃描）每題要讀整欄向量 1.8 GB＋算 34.5 萬次距離，熱 4 秒（且同樣要那 1.8 GB 留在快取）、冷 100～540 秒，兩顆 CPU 被占滿一題 4 秒，成本隨資料線性長；新模式每題只碰 1～3% 的頁，熱毫秒、冷幾秒，代價是索引要常駐（2.2 GB，可縮到 0.5 GB、再配部分索引 0.3～0.4 GB）與每則新訊息多一次圖插入（熱 ~10 ms）。今天感覺吃效能的是一次性的遷移工作（重算、建索引、切換的 UPDATE 掃表、補尾巴的掃表、我的評估掃描）加上 scraper 同時占 CPU，不是新模式的常態。舊向量的 metadata 稀釋問題和索引無關、本來就要修。結論：不是舊的不好，是它撐不到 34 萬筆；回滾可行（DROP 索引、欄位改回）但不建議。
- 2026-10-27 11:4x（**四種格式的召回評估結果**，60 題、精確掃描、top-25、不折疊）：1024 halfvec 全部 Hit@1／5／25 = 38／49／50（A 7/9/9、B 6/7/7、C 7/13/14、D 18/20/20）；512 halfvec 38／48／51（A 7/9/9、B 6/7/7、C 7/13/15、D 18/19/20）；256 halfvec 34／47／51（A 6/8/9、C 5/13/15、D 17/19/20）。昨晚同一把尺的現況精確基準是 39／49／50。**結論：16 位元不掉；512 維在誤差內（Hit@1 差 1 題、D 類一題 5→9、C 類多撈到一題）；256 維 Hit@1 掉 5 題、「養貓」2→10、「晚安阿喵」1→6，太多。**腳本的坑：第一版用 `SET enable_indexscan = off` 在交易裡、每題後 rollback 把它收回，所以「現況」那欄從第 2 題起其實走了 HNSW 且 ef_search 是預設 40 → 31／36／38，不是精確基準（意外量到：ef 40 會丟掉 50 題裡 12 題的 top-25，證明 ef 要開大）；已改 SET LOCAL 重跑精確基準（每題 2.4 秒、共 145 秒）：**38／49／50（A 7/9/9、B 6/7/7、C 7/13/14、D 18/20/20），和 1024 halfvec 一字不差、和 512 halfvec 只差一題的名次**；昨晚的 39 是補尾巴前的一題並列差。**定案建議（待使用者點頭）**：換 512 維＋halfvec 的表達式索引（`l2_normalize(subvector(embedding,1,512))::halfvec(512)`，查詢端同樣取前 512 維正規化），和現有索引並存建好、60 題走索引再量一次、再 DROP 舊的；部分索引（排除 `length(text) < callback_min_chars` 與純貼圖）可一起做。　使用者問「兩個格式都做嗎、未來資源多的機器能直接用完整索引嗎」→ 資料不變：表裡存的永遠是完整 1024 維 fp32，512 維 halfvec 只是表達式索引在建索引時現算；過渡期兩個索引並存，確認後 DROP 大的（留著只多 2.2 GB 磁碟與每則寫入兩次插圖，查詢用不到）；日後換機器只要再建完整索引（20 分鐘）＋把查詢表達式切回去，不用重算。建議把索引表達式做成設定檔的 profile（`full`／`halfvec512`），查詢端照 profile 組 ORDER BY，兩種索引的 DDL 寫在交接檔。耗時：halfvec 轉型的精確掃描每題 18 秒（期間 scraper 占 CPU）、512／256 每題 3 秒。
- 2026-10-27 11:0x（使用者：「開評估看看」「評估要改向量應該不用重算吧」→ 對，halfvec 是轉型、降維是取前 N 維再正規化，都用現有向量現場轉）：啟動四種格式的召回評估（scratchpad `rag/eval_formats.py`，容器內背景、只讀）：1024 fp32（現況）、1024 halfvec、512 halfvec、256 halfvec，60 題、精確掃描（關 indexscan／bitmapscan）、top-25、不折疊，和昨晚 60 題同一把尺；一種格式跑完 60 題再換。預估 25～30 分鐘，期間向量欄位的全表讀會把 HNSW 擠出快取、bot 查聊天會慢。結果見下一條。
- 2026-10-27 10:3x～10:5x（**冷快取的尾巴：索引放不進頁快取**，只讀量測、未動 code）：切換後限定頻道 top-100（ef 1000）同一題第 1 次 257 ms→第 2 次 15 ms；沒碰過的向量第 1 次 23 秒（讀 4,592 頁）→第 2 次 6.5 ms；ef 200 對照 1 秒（301 頁）。試著在 pgvector 容器裡順序讀索引 3 段（2.2 GB，20 秒、110 MB/s）與表檔（661 MB、4 秒）預熱，**沒效**：之後新向量仍讀 2,490／18,013 頁（15 秒／98 秒），重讀第一段 1 GB 仍要 11.6 秒。原因是頁快取總量只有約 3.3 GB（主機 8 GB、行程佔 4.7 GB、swap 已用 1.3 GB），索引 2.2 GB＋表 0.66 GB 剛好塞滿，scraper（851 MB、CPU 89%）等其他容器的檔案讀寫一直把它擠出去；容器與 docker 都沒設 cgroup 上限、PG 18 io_method=worker 沒繞過快取、shared_buffers 只有 128 MB。結論：熱的區域毫秒、沒碰過或被擠掉的區域要幾秒到幾十秒（ef 1000 讀的頁數是 ef 200 的 3～10 倍）；比切換前（熱 4 秒、冷幾分鐘）仍是進步，但不是穩定毫秒。選項（RG-Q18，待使用者定）：A 加記憶體（16 GB 就能整個放進快取，最有效）；B `search_chat` 的 ef_search 改成參數，插話回憶用 400、之後的聊天搜尋工具用 1000（冷讀量降 3 倍、口頭禪整團的召回交給工具的字面路）；C 把 shared_buffers 拉到 2.5 GB 讓 PG 自己鎖住索引（8 GB 主機會換頁，不建議）；D 接受暖機。另建議：`search_chat` 查詢超過 2 秒記一行 WARNING（含耗時與讀頁數看不到，只記耗時），才看得到實際情況。
- 2026-10-27 10:2x（**補尾巴完成、遷移結束**）：舊的補尾巴行程在 09:53 數完 378 列後一批批寫回（每批一到兩分鐘：每列都要插進 HNSW、索引頁冷），到 10:22 做了 331 列、開始掃老資料區找剩下的 58 列時由使用者停掉（`sh -c 'kill 61'`，容器沒有 kill 執行檔）；`--redo-copied --min-id 346799` 10:23:38 起跑、count 一秒、10:27:45 結束：做了 58 列、算出 58、沿用舊向量 0。核對：`id > 346799 AND embedding = embedding_v1` 0 列、`embedding IS NULL` 0 列。**遷移至此全部完成**：新向量只嵌內文、HNSW 在用、舊向量留在 `embedding_v1`。待做：插話回憶距離門檻重校（量新格式的 survivors 距離分布）、`search_chat` 回傳加 channel_id、聊天搜尋工具（RG-Q16）；待使用者定：快照 09／10 commit、六個 commit 推送。
- 2026-10-27 09:3x～09:5x（**補尾巴的比對會掃整張表 → 加 `--min-id`**）：使用者 09:33 `compose up` bot（gate 87 個通過、09:34 連上）並啟動 `--column embedding --redo-copied`；它第一步 `count(*) WHERE embedding = embedding_v1` 要把兩欄向量都從 TOAST 讀出來逐列比（3.6 GB），12 分鐘還沒數完，每批查詢與最後一批也都是同一個條件，這台磁碟上會跑一小時以上、還把索引頁擠出快取（切換後限定頻道 top-100 的 EXPLAIN 走索引但冷讀 59 秒）。agent 要停它被權限擋下（干擾工作負載），改請使用者停：`docker exec discord-bot kill 61`、`pg_cancel_backend(84806)`。修正：`chat_reembed` 加 `--min-id`（`_predicate` 回條件與參數、count 與每批查詢都帶 `id > %s`、走主鍵），抄過來的列都在最新那段：最新 3000 列裡只有 2 列的 `embedding_v1` 是 NULL（切換後新 bot 寫的），重算開始（10-26 21:56）前最後一列 id 346799、之後 391 列 → `--redo-copied --min-id 346799` 幾秒做完。測試 2 個（有 min_id 帶條件、沒有不帶）、突變紅；`test_chat_reembed`＋守衛 27 個綠。第十次完整測試 1,796 個全綠（skipped 2）。舊的補尾巴行程（pid 61）與它的 count 查詢（pid 84806，已 17 分鐘）等使用者停。快照 10 `1df27777269f4d58a4830a0c11638db34530bd1b`（chat_reembed＋測試；累積含 09），訊息 `fix(rag): let the re-embedding job limit the copied-row redo to an id range`；body：comparing both vector columns row by row detoasts 3.6 GB without an id floor; the copied rows are all newer than the original run, so --min-id walks the primary key instead.
- 2026-10-27 09:0x～09:3x（**切換完成**；使用者執行）：09:12 使用者先重啟 bot（已載入早上的修正）、09:14 自己把容器停掉；第一次貼切換 SQL 時貼進了互動式 psql 後面被 bash 吃掉（沒動到庫），改成 `docker exec -i … psql -v ON_ERROR_STOP=1 <<'SQL'` 一次餵進去；09:13 起跑，UPDATE 補 NULL 那步掃整張表找 `embedding_v2 IS NULL`（堆積檔 660 MB、磁碟冷讀 1.4 MB/s）約 15 分鐘，期間持有 ACCESS EXCLUSIVE（bot 已停、沒人等鎖）；09:30 COMMIT。核對：欄位 `embedding_v1`／`embedding`、HNSW 索引定義跟到 `embedding`、`embedding IS NULL` 0 列、無殘留交易。教訓：切換前先把要抄的列數壓到最少、或 UPDATE 用 `WHERE id > <重算結束時的最大 id>` 走主鍵，不要讓它掃全表。接下來：使用者 `docker compose up -d discord-bot` → `--column embedding --redo-copied`（378 列）→ 看 log 確認插話回憶走索引、量門檻。
- 2026-10-27 07:0x～07:4x（**HNSW 近似搜尋會繞過整團一模一樣的向量 → 全庫搜尋 ef_search 開到 1000**；agent 決定並做了，待使用者檢視）：用修正後的程式（走 HNSW、ef_search=200）重跑 20 題 C 類：Hit@1／5／25 = 7／12／13，比精確掃描（8／13／14）少「臥槽」一題；20 題冷快取 571 秒（每題 25 秒上下，磁碟隨機讀約 100 IOPS）。診斷：精確掃描前 100 名有 72 列是「臥槽」（距離 0.30），HNSW ef 200 一列都沒回（第 100 名距離 0.51）、400 回 2 列、1000 回 70 列；「嚇哭了」（55 份）三種 ef 都正常。原因是同一句話重複幾十次、向量一模一樣（pgvector 同一向量最多併 10 個 heap tid 成一個節點，78 份仍是 8 個節點），這團點彼此互連、外面進來的邊少，窄搜尋束會整團繞過。熱快取耗時（三題各三次中位）：ef 200 4～6 ms、400 7～16 ms、1000 15～29 ms；冷的首查 13～54 秒、和 ef 無關。**決定**：全庫搜尋（candidate_ids=None）一律 ef_search=1000（`_FULL_CORPUS_EF_SEARCH`，理由寫在常數旁），窗內重排維持 max(100, 2×撈取筆數)（走 message_id 索引用不到）；沒選：重建索引 m=32／ef_construction=200（約 1 小時、索引 1.5 倍、不保證連通）、寫入端對一模一樣的句子只索引一份（改寫入與切換計畫；RG-Q16 的字面路本來就會接住「誰常說」）。測試 2 個（全庫 1000、窗內 100），突變 2 種都紅；`test_rag_collapse` 等 4 檔 58 個綠。用 ef 1000 重跑 20 題 C 類：Hit@1／5／25 = 8／13／14，和精確掃描一樣（「臥槽」回到第 1）；20 題冷快取約 16 分鐘（每題要讀的索引頁比 ef 200 多，磁碟約 2 MB/s），熱的每題 15～29 ms。
- 2026-10-27 06:1x～07:2x（**HNSW 建好、發現規劃器不用它、已修**）：維護 06:16:51 結束（發布 67 人、失敗 0）→ 06:19:19 在 pgvector 容器用 `psql -f` 逐句執行（`maintenance_work_mem=2500MB`、`max_parallel_maintenance_workers=0`、`CREATE INDEX CONCURRENTLY discord_messages_idx_hnsw … hnsw (embedding_v2 vector_cosine_ops)`），06:38:20 完成：19 分鐘、2,211 MB、`indisvalid = t`，06:40 `ANALYZE`；建圖期間主機可用記憶體最低 2.3 GB。**坑**：建好後 EXPLAIN 全庫 top-100 仍是 Parallel Seq Scan＋排序（實測 105 秒，冷快取、磁碟只有 3 MB/s）；原因是 `search_chat` 的 `metadata_->>'doc_type' = 'discord_chat'` 沒有統計資料，規劃器估 0.5% 的列會過（rows=1725）、索引路徑成本 93,879 > 全表 87,872；拿掉篩選後索引路徑 9,085、走 HNSW。聊天表是專用表（TABLESAMPLE 2% 全是 discord_chat、寫入端只寫這種、成員資料另一張表）→ `search_chat` 改成只有 `HYBRID_RETRIEVAL_SETTINGS.chat_table_is_shared()`（新方法：別的啟用來源指到同一張表）時才篩 doc_type；測試 2 個（專用表不帶、共用表才帶），突變 2 種都紅；相關 5 檔 72 個測試綠，第九次完整測試 1,792 個全綠（skipped 2）。其他形狀確認：/askai 窗內重排（candidate_ids）走 message_id btree，不受影響；作者＋頻道：多話的人改走 HNSW（原本 bitmap 讀 1.2 萬列的 TOAST）、少話的人走作者索引。修正後實測：全庫 top-100 冷 11.3 秒（讀 1,437 頁）、熱 2.1 ms；限定頻道 top-25 熱 1.3 ms。快照 09（之後因 ef_search 再封一次，見下一條）；未 commit、bot 未重啟（改動隨切換後的重啟生效）。期間 bot 自己的插話回憶在舊欄冷掃跑了 13 分鐘以上、06:41 一次 LLM 逾時（建圖搶 CPU 的時段），建完就沒再發生。
- 2026-10-27 04:3x（使用者：「先作索引吧、現在應該在做排程、幫我監測、等排程做完之後幫我作 HNSW」→ **授權由 agent 在維護結束後建 HNSW**；RG-Q16 的工具排在索引與切換之後）：04:29 persona agent 批次 6/26（每人約 3～4 分鐘），估 05:30～06:00 做完、再跑 ④ 發布精簡版。監測方式：每分鐘看 discord_bot.log 有沒有「persona 精簡版發布結束／失敗」或「persona agent 批次失敗」。結束後照計畫 ⑤ 序列建：同一 psql 連線 `SET maintenance_work_mem='2500MB'`、`SET max_parallel_maintenance_workers=0`、`CREATE INDEX CONCURRENTLY discord_messages_idx_hnsw … USING hnsw (embedding_v2 vector_cosine_ops)`，用 `pg_stat_progress_create_index` 看進度（PG 18.6、pgvector 0.8.2、容器無記憶體上限、主機可用約 3.9 GB），建完查 `indisvalid`、`ANALYZE`、`EXPLAIN` 一次向量查詢。**切換交易與重啟仍由使用者執行**（重啟避開 04:00～07:30）。
- 2026-10-27 04:0x（使用者「好」→ RG-Q16 定案 A 兩種模式；再問「能不能在背後執行、使用者察覺不到」；討論、未動 code）：查過 `llm_commands.py`：發問者只看到私訊「🔄 AI 思考中」＋取消鈕，完成後改「✅ AI 已回覆」，公開回覆只有問題與回答；工具經過只進 log 與 `askai_response_history`。結論：新工具和情報／上網一樣天生看不到，只差幾秒；補一條「不要說查了紀錄」的規則。時機未答。
- 2026-10-27 03:5x（使用者問「想要類似通用 AI、不想 user 打一堆東西、有時只是印象搜尋，是不是 B」；討論、未動 code）：澄清 A 不用使用者多打字（參數是模型填的）；通用 AI 的搜尋是模型改寫查詢（A／D），不是原句直接比對（B）；印象搜尋原句算向量本來就行，計數題只有工具能答。RG-Q16 補第三輪：A 的工具分 phrase／topic 兩種模式，B-lite 列為之後的加強。
- 2026-10-27 03:4x（使用者問「為什麼問題有引號」「不想要引號」「要確定是哪個頻道的誰發的」；討論、未動 code）：解釋引號是我出題的寫法不是 /askai 的規則；整句算向量時問法（誰常說…）和內容（好了啦）混在同一個向量、內容平淡就被問法壓過；舊格式對是因為 id 字串把短句淹掉、字面重疊意外占上風。回答「分不出是誰說的」：metadata 都還在每一列、只是不進向量，/askai 每行已帶名字#尾碼，`search_chat` 沒回 channel_id 是要補的小洞；折疊不跨人。RG-Q16 改版：去掉引號觸發，新增「結果要帶頻道與作者」，四個選項（A 工具＝建議／B 全庫混合檢索／C 規則抽詞／D 查詢改寫）。
- 2026-10-27 02:5x～03:3x（**C 類折疊版複測與診斷**，只讀；腳本在 scratchpad `rag/compare_c_v2only.py`、`diag_c_miss.py`、`measure_c_routes.py`）：`embedding_v2`＋`collapse=True` 20 題 Hit@1／5／25 = 8／13／14，和不折疊一模一樣——折疊沒救回那 6 題，上一條「並列名次」的推測不成立。逐題印前 25 名：掉出去的 6 題（那是肯定、好了啦、喔喔==、靠你了、全對、怎麼了?）前 25 名全是對到**問句框架**的句子（「誰說的」「誰信」「在哪說過」「你常說」「誰在罵人」），目標句距離 0.41～0.49 排在後面；舊格式的 id 字串把短句稀釋成一團，字面吻合反而占上風（「那是肯定」舊欄 0.36 → 舊名次 2）。命中的 14 題都是詞本身有特色的（何意味、苦呀汐、哇糙、臥槽、晚安阿喵、GOAL…）。補救選項各量一次（同 20 題）：只拿引號內的詞算向量 Hit@1 17、Hit@5 20、Hit@25 20（每題 3 秒，無索引）；引號內的詞 ILIKE 全庫按作者計數 Hit@1 18、Hit@3 20、每題 0.3 秒、不用新索引、順便得到「誰說了幾次」。**但 /askai 不搜全庫**（`search_chat(candidate_ids=None)` 只有插話回憶在用，/askai 走 100 則視窗的窗內重排），C 類量的是 /askai 還沒有的能力 → 列 RG-Q16。對切換的結論不變：A 進步、B／D 持平、插話回憶要的是語意（距離分布變乾淨），建議照計畫序列建 HNSW → 切換；C 類的補救是查詢端的事，哪個欄位都一樣要做。說明文件已補：60 題表、C 類複測與選項表、六個 commit、重算執行結果、待判斷新增一項。
- 2026-10-27 00:1x～02:4x（**新舊欄位 60 題比對**，全庫、不折疊、top-25、只讀：`search_chat(embedding_column=…)`；問句向量先一次算好、一欄 60 題跑完再換另一欄——兩欄各 1.8 GB，交錯查會互相擠出頁快取，舊欄冷讀一題 319～542 秒、新欄熱讀每題 3～6 秒，整輪 49 分鐘）：60 題 Hit@1 39→39、Hit@5 48→49、Hit@25 56→50；A 12 題 6→7／8→9／9→9，B 8 題 6→6／7→7／7→7，C 20 題 9→8／13→13／**20→14**，D 20 題 18→18／20→20／20→20（各為 Hit@1／5／25 舊→新）。進步 8 題（「VIPER 滑鼠」13→1、「何意味」6→1、「都 01 換抽沒差」5→1…）、退步 11 題，其中 6 題是 C 類（口頭禪）從前 25 名掉出：這些句子同一人說過十幾次、別人也說，新格式去掉 id 字串後每一份向量一模一樣、距離並列，不折疊的 top-25 回哪幾份沒有保證（舊格式每份因 message_id 字串不同而略有差距，名次穩定）；正式路徑一律 `collapse=True`（同一人同一句只留一份、先多撈 4 倍再折），所以 C 類要用折疊版再量一次才算數；B／D 逐字引用不受影響、A 小進步。C 類折疊版（只量 `embedding_v2`、20 題）在容器內背景跑（`docker exec -d`，結果寫容器 `/tmp/compare_c_result.txt`，主機端行程死了也不中斷），結果見下一條。核對：總列 345,618、`embedding_v2` NULL 295（都是重算結束後新寫入的，切換交易會補）。HNSW 尚未建、切換未做、bot 未重啟。
- 2026-10-27 00:04（**重算向量完成**）：21:56 用舊程式啟動（做了約 11 萬列後，22:32 因審查修正換新程式接續），00:03:56 結束：第二輪 234,667 列全部算出、沿用舊向量 0 列；等 bot 讓位 9 次（都是 30 秒級的 warning，沒有硬闖）；平均 38～54 列/秒，bot 忙時慢。核對：總列 345,368、`embedding_v2` 已填 345,323、NULL 45（都是結束後新寫入的，切換交易會補）。接著跑 60 題新舊欄位比對（`search_chat(embedding_column=…)`，全庫、只讀），結果見下一條。下一步由使用者執行：序列建 HNSW → 切換交易 → 重啟 bot → `--column embedding --redo-copied`。
- 2026-10-26 22:1x～23:xx（使用者問「程式有沒有不正確、哪些可以 commit」→ 第二輪獨立審查工作流 `wf_1bf8ddcd-49e`：Hermes 代理、重算工作、commit 一致性三位審查者＋反駁驗證）：重算工作 8 條：**high** 閘門給了 1800 秒上限仍會在 900 秒硬闖（`_acquire_steps` 先判「等滿 15 分鐘照常打模型」）→ 改成給了 max_wait 的呼叫端只會丟 GpuBusy、也不吃放行窗，`test_gpu_gate` 加假時鐘案例；**medium** 交接檔切換後補做寫成 `--column embedding` 少了 `--redo-copied`（述詞恆假）→ 改文件、程式拒絕該組合；low：向量 nan／inf／維度與後端少回幾個 → 檢查後沿用舊向量或改逐筆；整批逾時先探一則再決定停不停；`SET lock_timeout` 改 `SET LOCAL`；讀完 rollback 不持交易（等鎖、睡覺時不擋切換的 ALTER）；沿用舊向量比例改看最近 20 批；docstring 與測試檔頭補規則。正式跑中的工作用的是舊程式（1800 秒上限那版），風險只在 bot 連續占 GPU 超過 15 分鐘；修好測過後把它停掉、用新程式接著跑（keyset 從還是 NULL 的列續）。Hermes 代理 8 條（都已修，另成一個 commit `fix(hermes)`，快照 08）：**medium** `chat_completion_raw` 沒拆 Lemonade 的「200＋error 信封」→ 拆信封、卡死就自癒一次再當連不上（代理回 503）；**medium** `n_predict`／`max_completion_tokens` 能繞過 `max_tokens` 上限（llama.cpp 以 n_predict 優先）→ 三個一起夾、只留 max_tokens；low：非 ASCII 的 Bearer 讓 `hmac.compare_digest` 丟 TypeError 變 500 → 用 bytes 比（notify 的密鑰同改）；串流中途錯誤塊可能黏進前一個 SSE event → 不是空行就先補一個；上游 401／403 原樣透傳會讓對方以為自己金鑰錯 → 改 502 `upstream_auth`；`client_max_size` 是整個 app 的（/notify 也收 32 MiB）→ app 維持預設、/v1 用 `request.clone(client_max_size=…)` 放大；租約在載入完成時續一次、`.env.template` 的 LLM_TIMEOUT 改 300（64k 冷讀約 200 秒）；「對方斷線就放閘門」沒有真連線的測試（審查者手動驗證三種斷線 1 秒內放鎖；未補自動測試）。新增測試 7 個（`test_llm_proxy` 31 個）。這批修正的突變 14 處全紅（H1 腳本沒套到、手動套一處確認紅）、第八次完整測試 1,788 個全綠。commit 一致性 5 條：**high（反駁驗證確認為真）** /askai 重排在工作者 task 裡直接進閘門，租約到期時看門狗取消的是工作者本身 → 發問者永遠等不到、排隊工作者結束（reranker 是同步 HTTP、執行緒裡續不了租，冷載入最多 180 秒必過期）→ 改成「拿閘門＋重排」包成獨立 task、`asyncio.wait` 後看 `cancelled()` 當失敗照融合名次，租約預設 240 秒；medium 兩條是快照落後磁碟、分批放錯（已按建議重建：06' 含重排修正、07' 含重算與閘門修正、08' 只有 Hermes 修正，各自的 diff 檔案清單核過）；low：探測那一則本身出錯會被當後端掛掉 → 探測另外包一層、只有連不上才停；06 把 `askai_rerank_mode` 設 on 要在訊息講明 → 已寫進 06 訊息。最終快照：06' `35c98daa…`、07' `cba34391…`、08' `43fdcdba…`（.msg 已更新）；兩處新修正的突變 2 處全紅（重排不包 task、探測例外直接穿出）；完整測試第九次 1790 個：OK (skipped=2)。**已 commit（2026-10-26 23:3x，未推送）**：`c96ecc6` feat Hermes 代理（05）→ `07b729f` feat(rag) 折疊／品質閘／重排（06'）→ `17e2aba` feat(rag) 重算工作（07'）→ `a2e0f3f` fix(hermes) 審查修正（08'）→ `d87ce07` chore(settings) 字典 → docs 交接檔（本次）。`src/test/integration/it_comfyui_image.py` 仍未追蹤，等使用者決定。
- 2026-10-26 21:56（使用者指示「現在開始全域轉檔、每分鐘監控」）：啟動 `python -m llm.storage.chat_reembed --batch 64`（log 在容器 `/logs/chat_reembed.log`），起跑時還剩 345,312 列；每分鐘看 log（錯誤、警告、維護暫停、GPU 等待立刻回報）。跑完的下一步：用 60 題候選對 `embedding`／`embedding_v2` 各跑一次 `search_chat` 比對（距離分布與名次）→ 序列建 HNSW → 切換交易。
- 2026-10-26 23:xx（使用者：「那現在開始重算 OK 嗎」「能不能讓 discord_bot 先抓住 key」「把新舊向量格式差異放到文件內」）：視為核准新檔。寫了 `llm/storage/chat_reembed.py`（含 `test/test_chat_reembed.py` 10 個、`search_chat` 評估用 `embedding_column`、寫入端 `_chat_node` 設 `excluded_embed_metadata_keys` 只嵌內文），自我檢查：寫入端會嵌的字串就是 text 原樣、兩個向量餘弦距離 0.000024（後端批次算有一點點非決定性，可忽略）；dry-run 在影子欄不存在時只報算不出剩幾列、不寫。bot 優先的做法：每批放鎖後讓 0.5 秒、等閘門最多 30 分鐘等不到就睡 30 秒再試、永遠不硬闖，bot 最多多等一批（約 1 秒）。文件加「新舊向量格式的差異」一節（送去算的字串對照表＋2,000 筆試算數字）。快照 07-chat-reembed `d5c6a8ea…`；突變 8 處全紅（keyset 那處一開始沒被抓到，補了「下一批從上一批最後的 id 往下」的斷言後紅）；第七次完整測試 1774 tests 全綠。啟動指令交給使用者（docker exec -d … > /logs/chat_reembed.log）。
- 2026-10-26 22:xx（使用者問「高風險是什麼、會不會麻煩、重算多久、要不要先跑 2,000 筆」）：白話解釋兩條高風險（/dev/shm 與 NULL 列）；**唯讀試算 2,000 筆**（主頻道隨機 2,000 列＋60 題候選的答案列，舊向量從庫裡讀、新向量只嵌內文現算，不寫庫）：embedding 2,059 則＋60 題問句 21 秒（約 98 則/秒）；答案距離中位 0.285→0.261（更近）、雜訊距離中位 0.647→0.692（更遠），答案與雜訊的差距 0.36→0.43；但在 2,000 列的小語料裡答案名次兩種格式都幾乎是第 1（Hit@10 59/59→57/59，6 題小退、1 題進步、52 題不變）——題目多半逐字引用原話，這種測法量不出名次差異，差異會在 34 萬列全庫與改寫過的問句上顯現。結論：重算的實益是距離分布變乾淨（插話回憶的地板不再被壓扁的雜訊塞滿）與寫入端、查詢端一致，名次收益要等 30 題在全庫比；仍建議做（約一小時機器時間）。隨機抽 2,000 列的 SELECT 花了 350 秒（ORDER BY random() 全表掃＋TOAST），重算工作用 keyset 不會這樣。
- 2026-10-26 20:1x～21:xx（**獨立審查工作流** `wf_7de29866-b48`：正確性、設計與重用、重算計畫三位審查者，medium 以上各取兩條由反駁者在容器重現驗證）：設計 8 條、正確性 6 條、計畫 12 條。反駁驗證：「BM25 與向量兩路留的不是同一則」兩位審查者都抓到、驗證者在容器重現**確認為真**並補「向量路要拿全部 id 去查（最新那則可能還在緩衝）」；「守衛規則太寬」判 **不成立**（驗證時工作樹已經改好，diff 快照落後）；其餘驗證結果：正確性那條同一發現在驗證時工作樹已改好、判「現行程式不成立」（並順帶指出副本會佔掉向量路 SQL LIMIT 的名額 → 已改成多撈副本數、裁到候選池組數）；計畫的「/dev/shm 64 MB 讓平行建圖失敗」**確認為真**（對照 pgvector 0.8.2 原始碼與容器實查）；「切換時 NULL 列永久消失」**確認為真**，並改成「第一個 RENAME 先拿鎖 → UPDATE 補 NULL → 第二個 RENAME」的交易順序。工作流 8 個 agent、39 分鐘、約 101 萬 token。最後一次小修（向量路多撈副本數）後完整測試第六次 1763 個：OK (skipped=2)；快照 06 最終 tree `35c98daafd292154352633e791cd6b088d1d435c`。全部採納的修正寫在 RAG 區塊「獨立審查後的修正」，重算計畫依 12 條改版（/dev/shm 64 MB 會讓平行建圖失敗 → 序列建；切換交易先把 NULL 補成舊向量；lock_timeout；壞列逐筆重試並沿用舊向量；每批 commit；embed_batch_size；永不硬闖閘門；字串一字不差；距離地板要重校；DROP COLUMN 回收不到空間；評估要能對影子欄跑），新增 RG-Q12～Q15。快照 06 重封為 `35c98daa…`；第五次完整測試 1,763 個全綠。
- 2026-10-26 13:xx～14:xx（**使用者對 RG-Q5～Q11 的回覆＋續做**）：①RG-Q5 **定案重算向量**；②RG-Q6 **依建議：重算完再建 HNSW**，`search_chat` 已先寫好查詢前 `SET LOCAL hnsw.ef_search`／`iterative_scan`（測試 17 個綠）；③評估集：A 類原本的題目「真人也不會記得」、C／D 好可快速驗證要多一點、沒名字對不了答案 → 改版：A 12 題改從成員資料表的高信心「偏好事實」挑（誰不喝水、誰愛吃酪梨…）再到 raw 找那人的原話當答案、B 8、C 20（≥12 次）、D 20，全部用 bot token 唯讀拉成員名單對上 Discord 顯示名稱（126 人）；④RG-Q8 使用者要實務建議 → 留 0.1 當雜訊地板、分數只用來排序、一週後用分布與評估集校準（理由在 doc 決定表）；⑤RG-Q10 使用者要討論 → 三個選項與建議（去重但標「另有 N 人說過」）寫在回覆，待拍板。另：實測重算向量吞吐 batch 64 → 85 則/秒（全表約 68 分鐘純算向量，不是原估的好幾天）；重算計畫寫在本區塊「重算向量計畫」，重算工作是新檔待核准。Hermes 代理複查：容器 Up、/v1/models 401/401/200、/health 200、工具組只開 memory/skills/todo＋MCP intel。獨立審查工作流（三位審查者＋反駁驗證）結果與修正補在本區塊「審查」。
- 2026-10-26 11:0x～13:xx（**RAG 優化實作**，/goal；code 已改、未 commit、discord-bot 未重啟）：做了 RG-Q1 折疊（`search_chat`／BM25／插話回憶的「同一人說過 N 次」）、RG-Q2 閘門（認得 `:描述:`、`[貼圖：…]`；`is_link_only` 收進 `emoji_text_utils`；`callback_min_chars` 進 SQL）、/askai 相關名額品質閘＋reranker（開關 `askai_rerank_mode`、門檻 0.1；沿用情報搜尋的 `LemonadeReranker`，由指令層交進檢索層）、60 題評估集候選（唯讀抽 raw，寫在 Claude Doc 第二分頁請使用者勾 30）；唯讀量了聊天表：全庫向量查詢全表掃約 4 秒、窗內 21 ms、純貼圖 14,612 列過得了舊閘門。寫了說明文件（架構圖、三條路徑流程與例子、HNSW 原理、決定與優劣、待判斷清單）：https://claude.ai/artifact/PfrESK3SSsr7jCpoVQkVKr 。快照 05（Hermes 代理，之前做好的）`ae6810ce…`、06（本輪，審查修正後重封）`35c98daa…`，commit 訊息與待決 RG-Q5～Q11（重算向量、HNSW 時機、選題、門檻、候選池、跨作者去重、重啟）都在新區塊「聊天檢索（RAG）優化」。新測試 16 個、突變 9 處全紅、守衛新規則會紅、完整測試 1,753 個全綠。守衛與 AGENTS 共用元件表各加品質閘與 `dedup_key`。
- 2026-10-26 10:3x（使用者對 RG／IN 的回覆，未動 code）：①「HNSW 我應該有做？」→ 有，但在另外兩張表：`ai_interactions`（兩個 hnsw，其中一個是 `got_reply IS NOT NULL AND NOT directed AND NOT followup` 的部分索引）與 `data_search_chunks`（`services/search/vectors.py:115`，查詢時 `SET LOCAL hnsw.ef_search = max(100, 2k)`、`hnsw.iterative_scan = relaxed_order`）；聊天表 `data_discord_messages_index`（27 萬+）與成員資料表都沒有。②**定案**：RG-Q1 折疊＋RG-Q2 閘門修正做；/askai 相關選取加品質閘＋rerank 做；評估集由 Claude 擬（使用者顧慮訊息與話題會變）→ 設計：題目錨定 message_id 與時間窗（凍結快照），分四類（誰說過什麼、某次討論的結論、某人的口頭禪或常貼的東西、最近 N 天內的事），後兩類每月從資料自動重抽候選（規則挑 15～60 字、非表情、唯一文字、有反應的訊息，用模型或範本改寫成問題，使用者挑 30 題確認），每題記出題日與有效期；兩條路分開量：全庫 `search_chat` 量 Hit@k，/askai 的混合重排用當時的 100 則視窗重放（`askai_response_history` 已有 `fused_ranked`）；先做候選產生器再請使用者挑。③「負例之前是不是做過」→ 部分有：`ai_interactions.insulted` 會把 `got_reply` 改成 FALSE，是插話鉤子（kNN）的反例，已上線；`positive_reactions`／`negative_reactions` 兩欄都有在記；但 style_refs 只用 `fetch_similar_positive`（≥`style_refs_min_positive` 讚）挑範本，沒有排除被罵過或負反應多的回覆——IN-Q3 的範圍縮成「style_refs 排除 insulted／negative>positive 的回覆」。④**IN-Q1 使用者決定維持按嘲諷表情，而且可以按多個**（照辦；之後實作成從嘲諷表情組挑 2～3 個）。IN-Q2 使用者要細節、不要動不動降溫 → 設計寫在 10-26 的回覆：只對「明確叫 bot 閉嘴」觸發（和 [INSULT] 同一次模型判斷、多一個 `[HUSH]` 標記；開玩笑的由模型照既有規則分）、動作是回一句就收＋該頻道 30 分鐘不主動插話（被 @ 照回）、冷卻內第二次延長到 2 小時且只回群主、到期自動解除、每次記 log；不觸發的：不同意、嫌它講錯、一般抱怨。**IN-Q2～Q4 都做但往後排；Hermes 開發優先**。
- 2026-10-26 10:1x（兩個討論題，未動 code）：①使用者要「業界解法與推薦方法的詳細說明，尤其 HNSW 與讓機器人更精準」→ 回覆分三層（召回／排序／雜訊與重複），逐項白話：HNSW 解決的是速度不是精準（近似最近鄰圖；pgvector 過濾是索引掃完才套、`ef_search` 預設 40、0.8 有 `iterative_scan`；34 萬筆 × 1024 維現在每次精確掃；建索引要 `CREATE INDEX CONCURRENTLY`、維護時段、記憶體），速度釋放後才有本錢把候選池從 25／30 放大到 100～200 再折疊、MMR、rerank；折疊（DISTINCT ON／window、ES collapse）；MMR（λ·相關 −(1−λ)·與已選最大相似）；near-dup（MinHash／SimHash）對聊天不必，exact＋正規化只差 0.6 個百分點；metadata 混進 embedding（短句距離被壓、查詢端格式不同）要重算 94.6%；Contextual Retrieval（嵌入前加前文脈絡，規則式不必用模型）；reranker（情報搜尋已有 Qwen3-Reranker，聊天沒用）；品質閘與 hubness；時間衰減；評估集。**推薦順序**：RG-Q1 折疊＋RG-Q2 閘門 → /askai 相關選取加品質閘＋rerank → 30 題聊天檢索考卷（沒量化不調參；基線 askai_response_history 的 fused_ranked）→ 量查詢時間後決定 HNSW → metadata 不嵌＋規則式前文脈絡一起重算一次（舊世代 5.4% 順便消失）。②「機器人偵測到一次仇恨言論，除了嘲諷還能有什麼反應」→ 查 10-24 19:24 那次：`ai_interactions` 顯示 bot 先說「那件婚紗大概是全群最貴的壽衣呢」、兩人叫它閉嘴、它回嗆「兩個人一起叫我閉嘴…只是說實話而已，別急」（insulted=true），對方才真的罵 → `[INSULT]`（按嘲諷表情、不回、7 天不主動接）。性質是「被罵」且 bot 自己有升溫，不是針對人或族群的仇恨言論。提出的選項（**IN-Q1～Q4 待決**）：IN-Q1 被罵時不按嘲諷表情（嘲諷本身是回應，會火上加油），改成不按或中性，建議改；IN-Q2 「叫閉嘴」就該降溫：回一句就收、該頻道插話冷卻 30 分鐘，不等到被罵（現在設計是「單純叫閉嘴照常回」），建議改；IN-Q3 把被罵前它自己那句標成負例（`ai_interactions.insulted` 已有欄位，style_refs 現在只取正例），建議做；IN-Q4 升級通知：同一人 7 天內第 2 次起 DM 群主一則摘要（頻道、時間、連結、它前面說了什麼；`dm_notifier` 現成），建議做。**真正的仇恨言論（針對群友／族群）**另一套：bot 的人格不介入執法，(a) 偵測→DM 管理員附連結（可用現有審核模型路線）建議；(b) 伺服器端開 Discord AutoMod 當第一層，建議；(c) bot 回應勸阻、刪文、禁言——不建議（誤判成本高、bot 替社群執法會引火）。
- 2026-10-26 09:1x～10:0x（**向量檢索的重複問題**，唯讀調查，未動 code；workflow `wf_a7df214b-bb9`：程式路徑、資料統計（只 SELECT）、業界做法三位＋一位交叉查證；原文在本 session scratchpad `rag_*.json`）：使用者問「同一個人重複講某句話，向量搜尋會不會把重複的擠進前幾名影響 RAG，目前有沒有處理」。**答案：沒有任何處理，而且會。** 寫入端（`store_chat.py:137-144,367-388`）一則一個 node、只擋 bot／已寫過的 id／不到 2 字，唯一鍵只有 message_id；檢索端 `search_chat`（`context_retriever.py:331-364`）就是 `ORDER BY embedding <=> q LIMIT k`，/askai 的 RRF（:594-631）以 message_id 計分逐筆填到 25，沒有文字去重、同作者上限、MMR；`grep mmr|dedup|per_author` 只命中人物卡的 `_dedup_profile_docs`。**資料（pgvector 實查，344,733 筆）**：同一人同一句的重複 60,092 筆（17.4%）、9,264 組、≥50 次 178 組／27,877 筆、最大一組 1,013 筆；不分作者 24% 的列在重複組。重複來源 86% 是表情描述 `:安可瘋狂:`（4,277）、`:吃瓜看戲:`（4,049）、貼圖 `[貼圖：…]`、「笑死」這類 ≤4 字的反應詞；真句子（>4 字、非表情貼圖、同作者 ≥5 次）只有 489 組／5,153 筆（1.5%），前幾名還是純 `<@id>` 點名和附件網址。≤10 字佔 58%（中位數 9 字）。同句的向量幾乎相同（同世代距離 ≤0.03），所以排名連號。**兩條路徑受害程度不同**：①/askai 只在「最近 100 則視窗」內重排（BM25＋向量 RRF，保底 25、相關 25、送 50），全庫重複碰不到它；686 次真實紀錄裡 top-25 平均 0.69 筆完全重複（38.8% 至少 1 筆、19 次 ≥5 筆），≤5 字短句平均佔 26%——傷害有限。②**插話的 callback（`ambient_reply._build_chat_callback_context` :499-640）是唯一的全庫向量查詢**：本頻道、2 小時前、候選 25 → 過濾（≥8 字、`is_emoji_or_symbol_only`、純連結、距離地板）→ 三因子排序 → 10 行。沒有去重；而且 `is_emoji_or_symbol_only` 只認 `<a?:name:id>`，**認不得庫裡存的 `:描述:` 與 `[貼圖：…]` 格式**（容器實測），單一表情靠 8 字門檻擋、貼圖描述完全擋不住。模擬：用 `:吃瓜看戲:` 或「笑死」的向量當查詢，全庫 top-30 只有 1 種文字；真實 callback log 12,595 次：候選名額約 45% 先被 <8 字的佔掉再丟、每次平均 2.87 筆完全重複、9.8% 的次數注入行裡有一模一樣的句子（共 3,991 行多餘）；用真實句子當查詢時影響小（20 句平均 top-30 有 27.1 種文字、2.9 筆重複）。**附帶發現**：(a) 節點 metadata（message_id、author_id、timestamp…）被一起算進 embedding（沒設 `excluded_embed_metadata_keys`，LlamaIndex 用 `MetadataMode.EMBED`），查詢端只嵌問句，格式不一致；短句被拉近（兩個表情句 0.64→0.38），長句影響小；(b) id<19,424（2026-04-21 07:46 UTC 前，18,676 筆、5.4%）是另一個向量世代，同句差約 0.25——交叉查證推翻「換模型」，最可能是 `reembed_pgvector.py` 只嵌原文、線上寫入嵌 metadata＋原文（早期同句跨作者距離恰為 0 可證；04-28 真正換後端沒造成新世代）；若之後改成只嵌原文，要重算的是其餘 94.6%；(c) embedding 欄**沒有 HNSW／IVFFlat 索引**，34 萬筆每次精確全表掃，callback 每則插話判斷查一次；(d) `discord_messages_raw.indexed_to_pgvector` 全 false、程式沒人用；(e) 人物卡那路不受影響（同 business key replace、每人一張卡）；但向量那一路 97% 是 preference_fact／signature_tag，`build_persona_cards` 只認三種 kind，top-15 多半被丟（影響未驗）。被交叉查證推翻、不要引用：「同句不同作者距離 0.13、向量三分之一在編碼誰說的」（混入早期世代的假象）；RRF 門檻數字漏乘權重（結論不變：幾乎不過濾）。**對策（待決 RG-Q1～Q4）**：RG-Q1 檢索層折疊：`search_chat` 先撈 limit×3、依 (author_id, 正規化文字) 折成一筆（留最新）帶 `repeat_count`，再取 limit；/askai 的 BM25 同樣折、RRF 後再文字去重；callback 走同一支自動受惠——建議**做**，改一處 facade 兩條路都修；RG-Q2 callback 的品質閘改認存庫格式（`:描述:`、`[貼圖：…]`）並在過濾後才補滿候選——建議做（小改）；RG-Q3 折疊後把次數交給模型（「這句他講過 37 次」當口頭禪訊號）——建議插話的回憶段做、/askai 的時間序不做；RG-Q4 寫入端乾脆不存純表情／純貼圖訊息（佔 11.8% 的列、54% 的重複量）——建議先不做（人格萃取可能要用，且 Q1 已擋），量過再說。另外三個獨立待辦：HNSW 索引（建索引期間吃 CPU／記憶體）、metadata 不嵌進 embedding（要重算 94.6%）、`indexed_to_pgvector` 欄位移除。驗證法：用 `askai_response_history.jsonl`（基線已算：平均 0.69 筆重複、短句 26%）與 callback debug log 離線重算前後對比。
- 2026-10-26 09:1x～09:4x（**Hermes 端到端打通**：bot 的 `/v1` 模型端點已實作上線、Hermes 容器起來、經 bot 用顯示卡回答、MCP 查情報也通；**未 commit**，使用者說先不管 commit）：使用者「幫我確認 hermes 的 container 已經可以起來了，並且透過 discord_bot 呼叫顯示卡端」。做的事（HM-Q1 甲、Q2 hermes-net、Q3 ctx 65536、Q5 轉發放 bot、Q7 關 background_review 都照建議；Q4 標籤、Q6 profile 沒動）：①`.env` 追加 `HERMES_API_KEY`（`openssl rand -hex 32`，只追加一行）；`docker compose pull hermes`（`stable` 現在是 **0.22.5**）。②**新模組 `services/llm_proxy.py`**（服務層，已登記 LAYERS）：`GET /v1/models`、`POST /v1/chat/completions`，只認 `Bearer HERMES_API_KEY`（hmac 比對）；模型名不是 `resolve_request_model()` 回 400 `model_not_found`；`max_tokens` 夾到 `proxy_max_tokens`（4096）、串流補 `stream_options.include_usage`；`imagegen_busy` 直接 503；用 `asyncio.timeout(proxy_max_wait_seconds=120)` 包 `gpu_exclusive("hermes", lease_seconds=LLM_TIMEOUT+30)` 的進入，等不到回 503＋Retry-After 30；進閘門後 `LLMService.ensure_model_loaded`（新公開方法）推 ctx；非串流走 `LlmHttpClient.chat_completion_raw`（新，不重試）、串流走 `chat_completion_stream`（新，asynccontextmanager，非 2xx 先讀完本文再丟 `LlmAPIError`）逐行原樣寫 `StreamResponse`、每行 `lease.renew()`、從帶 usage／timings 的塊取 `llm_usage`；後端非 2xx 原樣交回狀態碼與本文；連不上或逾時 503 `backend_unavailable`；200 送出後出錯在串流裡寫 `data: {"error":…}`；對方斷線直接收工。**新設定 `sys_settings/hermes_settings.py`**（`HermesSettings`，env_prefix HERMES_：`api_key`、`proxy_max_wait_seconds`、`proxy_retry_after_seconds`、`proxy_max_body_bytes` 32 MiB、`proxy_max_tokens`、`proxy_lease_extra_seconds`）。**`notify_server`**：`web.Application(client_max_size=…)`、`AppRunner(handler_cancellation=True)`、有金鑰才 `LlmProxy.add_routes`、啟動 log 加「模型端點=開／關」；模組說明補兩條端點。**測試 `test/test_llm_proxy.py`** 14 項（aiohttp 測試用本機伺服器＋假閘門、假後端、假 LLMService；含一項用真閘門驗 `current_owner()=="hermes"`、`stream_busy()`）：完整測試 1,737 項全過（138 秒）；守衛四組全過；**突變 7 個全紅**（不驗金鑰、不擋模型名、不續租、不夾 max_tokens、不記 usage、不補 include_usage、不開 handler_cancellation）。③`docker compose up -d discord-bot` 重建（env_file 有新變數要重建才拿得到；09:27:39 登入、09:27:49「模型端點=開」）；容器內驗 `/v1/models`：沒金鑰 401、錯金鑰 401、對的 200 只列主模型。④Hermes 一次性容器（`compose run --rm --no-deps hermes …`）會在 `data/hermes` 產生完整預設 `config.yaml`（129 KB、v51，備份為 `config.yaml.default-v51`）、`.env` 範本、`SOUL.md`、同步 58 個內建 skill；`hermes tools` 不是子指令（工具集名稱在 config 註解第 1518 行起）；`doctor` 只抱怨沒登入 Nous。**config.yaml 改的地方**（逐行精確替換，其餘預設）：`model.default`＝主模型名、`provider: custom`、`base_url: http://discord-bot:5000/v1`、`key_env: API_SERVER_KEY`、`context_length: 65536`；`agent.max_turns: 30`、`agent.disabled_toolsets: [terminal, file, browser, code_execution, delegation, web, search, image_gen, tts, cronjob, skills_hub]`；`platform_toolsets.api_server: [memory, skills, todo]`；檔尾加 `auxiliary.background_review.enabled: false`、`mcp_servers.intel.url: http://search-mcp:8765/mcp`。⑤第一次啟動用 `context_length: 32768` 試：Hermes 的 agent 在 `_enforce_minimum_context` 直接 ValueError「32,768 低於最低 64,000」（API server 回 502、沒去連 MCP、沒打到 bot）→ **HM-Q3 (a) 做了**：`src/sys_settings/llm_runtime_config.json` 第 45 行主模型 `ctx_size` 32768 → 65536（熱讀；下一次對話由 bot 推給 Lemonade），Hermes `context_length: 65536`、`restart hermes`。Lemonade 09:37:28 以 65536 重載成功（兩張 15.9 GB 卡，沒有 VRAM 問題；Hermes 警告「provider advertises 131,072; the pin wins」可忽略）。⑥**驗證**：`/v1/toolsets` 平台 api_server 只有 memory、skills、todo 啟用，terminal／file／browser／code_execution 都關；search-mcp log 有 172.19.0.3（hermes）的 GET／POST /mcp（工具探索）。閒聊題「鳴潮是什麼」66.9 秒、bot `llm_usage feature=hermes prompt=6813 cached=0 output=528 tok_s=24.4`，1 次呼叫。情報題「最近一篇官方公告」115 秒、**9 次呼叫**（第 2 次起快取接上：cached 6,788／6,824…、最後 prompt 15,141）、search-mcp 收到 4 次 `search`（版本 更新／維護預告／3.7 版本 活動／喚取 活動），回答正確（3.7 版第二期喚取、附官網連結）。另有兩次很短的呼叫（prompt≈270、output≈10）是 Hermes 的輔助工作（標題生成之類，`auxiliary.*.provider: auto` 落到主模型）。**觀察到的問題**：回答是**簡體中文**（SOUL.md 還是預設英文人設，沒要求繁體）→ 已寫 `data/hermes/SOUL.md`（觀星台圖書館員：繁體台灣用語、不夾日文、短答、先 search 再 fetch、官方與玩家分開講、每條附連結、查不到就說、只談鳴潮與社群），`restart hermes` 後重測「3.7 最近活動列三個」：182.5 秒、繁體、條列、每條附 FB／官網連結（內容是 9 月的活動加 10/20 的彙總連結，「最近」的解讀偏寬，之後看要不要在 SOUL 或 prompt 裡要求帶日期篩選）。使用者問「SOUL.md 是否應該版控」→ 應該（手寫、Hermes 只讀不寫；config.yaml 是 Hermes 產生並會升級搬遷的，留 data/）：建議搬到 `config/hermes/SOUL.md`，compose 以單一檔案唯讀 bind 蓋到 `/opt/data/SOUL.md`；之後自己寫的 skill 同法掛 `/opt/data/skills/<名稱>/`；`hermes doctor` 提到的 `/etc/hermes` managed scope 可能是「我們的 config 覆寫進版控」的正確機制，格式未查。**等使用者點頭再做**（新資料夾）。使用者問「Hermes 結合 bot 能提供什麼服務」→ 回覆列了之前的（日報、/配隊、補課交接檔、公告摘要／兌換碼；第二人格、ComfyUI 工具、clarify 之後）與新增的（論壇週報、版本前瞻整理表、週期提醒附這期配隊、/深查 長調查、本週大家在問），分工原則「要琇紫的臉或秒級回應進 bot；多步驟、跑幾分鐘、沒人在等進 Hermes」；Hermes 多出來的是跑得長、skill、記憶、排程；建議順序 日報 → 週報 → /配隊 → 補課交接檔，**等使用者選**。`platform_toolsets` 的 teams／google_chat 預設值在 0.22.5 是未知名稱（warning，無害）；Hermes 的 `usage` 是整輪加總（85,967 prompt tokens）。**還沒做**：SOUL.md；`gateway.api_server.max_concurrent_runs`（預設 10）沒設；讓位／優先序（Hermes 一題 9 次呼叫共 115 秒，期間插話會讓位、/askai 要排隊）；bot 端呼叫 Hermes 的客戶端與指令（日報、/配隊）；HM-Q4 釘版（stable 已悄悄變 0.22.5）與 Q6 拿掉 profile；`.env.template` 已有 HERMES_API_KEY；AGENTS 共用元件表要加「對外提供 LLM 端點 → `services.llm_proxy`」與「GPU 閘門持有中不可呼叫 Hermes」；commit（使用者先不管）。
- 2026-10-26 07:2x～07:4x（named volume 切換**已上線**、TS-Q3 新發現**已修並上線**、併進既有 commit；本檔與字典尚未 commit）：使用者「重啟時把無用的 named volume 清掉，動作前絕對確保安全」→ 07:27 還在維護時段，先做唯讀檢查：`discord_vector_data` 物件 device 指向已不存在的 `vector_data/`、`_data` 掛載點 0 個項目、沒有容器在用；資料在 `data/pgvector`（pgvector 當時掛 bind）；新 compose 解析 device＝`/home/jason/discord/data/pgvector`；記基準筆數。`data/backups/` 已被使用者清掉（10-22 的 dump 與 searxng 打包都不在）→ 重建目錄、線上 `pg_dumpall` 新備份 `data/backups/pg_dumpall-20261026-0728.sql.gz`（2.1 GB、14 張表、gzip 完整）→ 才 `docker volume rm discord_vector_data`。今天的每日維護 05:45 已跑完（下次 10-27 04:00），07:31 `docker compose --dry-run up -d` 確認只動 pgvector、discord-bot、search-mcp（dependents）後 `up -d`：07:31:39 新 `discord_vector_data` 建立（device＝data/pgvector）、pgvector 07:31:53「database system was shut down at 07:31:42」沒有 initdb、`data_directory=/var/lib/postgresql/18/docker`、四張表筆數與基準完全相同（raw 391,014）；bot 07:32:44 登入、07:33:07 通知伺服器起來；telegram-scraper 沒被 up 動到。**TS-Q3（新）**：`docker compose restart telegram-scraper` 07:32:30 走新流程 1.3 秒、exit 0，但接著量一次 `stop` 卻 10.3 秒、exit 137；`docker events` 與 log 對時：07:33:09 有「收到 SIGTERM，開始停止」、沒有「已停止」→ 收尾卡住，不是沒接到。根因：`runner.py` 啟動時 `db.pool.acquire()` 借一條連線掛 LISTEN（`telegram_emoji_refetch`）從不歸還，`db.close()` → asyncpg `pool.close()` 會等所有借出的連線歸還 → 永遠等 → 10 秒 SIGKILL；07:32:30 那次順利是因為 pgvector 剛重建、LISTEN 連線已斷，沒東西可等。修法：runner 的 finally 在 `db.close()` 前 `db.pool.release(refetch_listen_conn)`（release 會 UNLISTEN；`refetch_listen_conn = None` 移到 try 外面以免 `client.start()` 失敗時未定義）；`TelegramDatabase.close(timeout=5.0)` 用 `wait_for` 包 `pool.close()`、逾時 `pool.terminate()` 並記 WARNING（asyncpg 文件建議的做法）。測試加在 `test_telegram_scraper_stop.py`：跑完整 `run_telegram_scraper`（假 pool 記 acquire／release／close 順序）斷言 `["acquire","release","close"]`；`close()` 遇到永遠不回來的 pool 會 terminate、正常關閉不會 terminate。完整測試 1,723 項全過（87 秒）；突變 2 個全紅（不歸還 → 順序測試 failure；不 terminate → 逾時測試 failure）。以 `--fixup=amend:eea5db0` 併進 04 並改寫訊息（補 LISTEN 連線與 pool 關閉上限兩點）→ **04 現在是 `59a438b`**（docs `82770e6`、chore `17e353e` 跟著變）。部署驗證：`restart telegram-scraper`（停舊程式 10.4 秒）→ 新程式 `stop` **0.70 秒、exit 0**，log「收到 SIGTERM → 已停止」；search-mcp 新程式 `stop` **3.0 秒、exit 0**（Claude Code 的 MCP 客戶端連著也只等 2 秒上限；stdout 會多兩行 uvicorn 的 ERROR「Cancel 1 running task(s), timeout graceful shutdown exceeded」與「Exception in ASGI application」，就是那條被切掉的長連線，預期內）。重啟後 15 分鐘：bot 0 ERROR；telegram-scraper 的 traceback 全是 07:31 pgvector 重建期間 asyncpg 重連的（之後沒有）。**注意**：TS-Q3 的程式修正是我判斷後直接併進未推送的 04，沒有先問；使用者若要拆成獨立 commit 可以再拆。**留給使用者**：本檔與字典的 commit（建議 fixup 進 `82770e6`／`17e353e`）、推送（領先 17 個）、HM-Q1～Q7、pg_dumpall 要不要排程。
- 2026-10-25 續 2 → 10-26（compose 的 named volume 與註解精簡**已以 amend 型 fixup 併回 02**，hash 見下；本檔這段尚未 commit）：使用者追問「named 不會因 compose down／prune 被清、bind 會嗎」「named 看得見、bind 看不見，有比較好維護嗎」→ 實驗（暫存目錄建同型 `type none/bind` 的具名 volume、容器寫入、`docker volume rm`、再建回）：物件刪掉目錄資料都在，建回來內容照舊。事實表：`compose down` 兩種都不動；`down -v`、`volume prune -a` 會刪 named 的**物件**（這種 bind 型的資料留在目錄；Docker 自己管的那種才會連資料一起刪），bind 完全不受任何 Docker 指令影響；`data/pgvector` 唯一會消失的方式是主機上 `rm -rf`。可見性：named 在 `docker volume ls`／面板／`inspect` 看得到路徑，bind 只在容器的 Mounts 裡，這點對資料庫是實質優點。使用者看到面板裡的 `discord_vector_data` 以為舊資料還在那裡 → 證明它是空殼（device 指向已不存在的 `vector_data/`、沒有容器在用），資料 3.2 GB 在 `data/pgvector`、`discord_messages_raw` 387,158 → 390,874 筆持續寫入。named volume 的缺點整理：路徑存兩份（物件建立後寫死，改路徑、搬目錄、換機器都要先 `volume rm`）、名字綁專案名、`down -v`／`prune -a` 會讓物件消失再長回來、多一層掛載；Docker 自己管的那種另有 root-only、刪即丟資料、搬機器要 export。**真正保護資料的是備份**，目前只有 10-22 手動的一份 pg_dumpall，沒有排程。使用者要求用 fixup 改掉過去的 compose → `git commit --fixup=amend:2c3d10e`（`-F` 不能和 `--fixup` 並用，改用 `GIT_EDITOR=cp <檔>` 餵 amend! 訊息）＋ `GIT_SEQUENCE_EDITOR=true git rebase --autosquash 4c33ba0`；02 的訊息第 1、2、4 點改寫（named volume 相對路徑、頂層錨點、create_host_path 只講 bind）。**實際上線跑的順序是**：10-22 16:52 起 bind 版、之後才改回 named——歷史被改寫成一開始就是 named，這段差異只記在本檔。原「續 2」內容：使用者「可不可以先改好我看過再 commit；註解太多；資料庫我想獨立出來，bind 我只考慮共用的狀況，不然你分析我的 named volume 哪邊不好」→ 分析結論：兩種寫法功能相同，差距是偏好等級。具名 volume 的具體缺點只有「device 寫死在 Docker 物件裡，改路徑要先 `docker volume rm` 再 up、否則被問 Recreate」與名字綁專案名；優點是路徑不存在時天生失敗（不用 `create_host_path`）、`docker volume ls` 看得到、以後換儲存後端只改 driver_opts。使用者的分法「共用才 bind、獨立的用 named volume」有道理，**pgvector 改回 `vector_data` 具名 volume**，device 改成相對路徑 `./data/pgvector`（實測 Compose 5.6 從 `/` 執行也以 compose 檔目錄解析，`${PWD}` 的問題不存在）。註解：我加的全部精簡（57 → 37 行註解、285 → 267 行），只留「為什麼」；使用者原有的（啟動 gate、stop_signal、FORCE_OWNERSHIP、scraper init）沒動。`docker compose config` 比對：只有 pgvector 的 volumes 欄位變（bind → volume `vector_data`），其餘服務、networks 一字不差；解析後 device＝`/home/jason/discord/data/pgvector`。**部署**：舊物件 `discord_vector_data` 還指向舊路徑，`up` 前要先 `docker volume rm discord_vector_data`，compose 會以新 device 重建同名物件；`up -d` 會重建 pgvector 容器（DB 停約 10 秒），依賴它的服務可能一起被重建，等同整組重啟，避開 04:00～07:30；可先 `docker compose --dry-run up -d` 看 compose 打算動哪些。可以和套用 04 的重啟一起做。
- 2026-10-25（**已 commit**，未推送）：使用者「你先 commit」。定案：02＋03 合併（03 只是搬遷期間的過渡規則，使用者問過「是不是因為搬到 data 內所以移除」→ 是）；01 不合進 03 也不合進 04（feat 與 refactor／fix 分開，合進 04 還要手工拆 compose）；`.dockerignore` 拿掉（BuildKit 只傳 COPY 到的檔，10-23 14:19 的 rebuild 在 data/ 存在時成功，證明現在不需要；哪天 `COPY . .` 或關 BuildKit 才要，而且出錯是大聲的）。快照 03、04 重算成不含 `.dockerignore` 的 tree 後依序 commit：`8a8cfd2` chore: ignore the whole local doc folder（00）、`9c2ec1e` feat(compose): add the Hermes agent service draft behind a profile（01）、`5d90034` refactor(compose): group runtime data by lifecycle under data/, cache/, run/ and config/（02＋03；原 `6aa243e` → 10-25 續的 fixup 後 `2c3d10e` → 10-26 named volume 的 amend 後 `5d90034`）、`59a438b` fix: let telegram-scraper and search-mcp stop within Docker's grace period（04，原 `49e9be1` → `1e88c54` → `eea5db0` → 10-26 TS-Q3 併入後 `59a438b`）；之後 docs（本檔）與 chore(settings)（字典，bot 補的 37 行描述）各一個。commit 前驗過工作目錄（扣掉排除檔）的 tree 與 04' 相同、commit 後 HEAD 的 tree 與 04' 相同。**還沒做的部署**：`docker compose restart telegram-scraper search-mcp` 套用 04（在那之前它們跑的仍是舊程式）。**留給使用者**：`docker volume rm discord_vector_data`、匿名 volume `a5ea716…`、備份檔、推送；HM-Q1～Q7 等回覆。
- 2026-10-25 續（commit 後的三個追問，**未 commit** 的小改）：①使用者問為什麼 gpu_lock 的錨點不像 `x-main-build` 一樣放開頭定義、後面引用，行內定義可讀性差 → 同意（repo 已有這個慣例；兩個服務各 `- *gpu-lock-mount` 才對稱），具體理由：alias 必須指到文件裡前面已出現的 anchor，刪掉或搬動 discord-bot 那段、或把 search-mcp 排到前面，search-mcp 的 `*gpu-lock-mount` 就變解析錯誤；行內定義看起來像 search-mcp 在借 discord-bot 的設定；和 `x-main-build` 的既有慣例不一致；Compose 規格的 extension／fragments 就是給可重用片段的位置。**已改成頂層 `x-gpu-lock-mount`**，兩個服務各 `- *gpu-lock-mount`；`docker compose config --format json` 的 services／networks／volumes 三段和改前一字不差（只多了頂層的 x- 欄位本身）。使用者選 fixup 併回 02（還沒推送）。②問為什麼拿掉 `vector_data` 具名 volume → 解釋：它是「包了一層 volume 物件的 bind」，`${PWD}` 取下指令的目錄、device 建立後寫死（改了會被問 Recreate）、名字綁專案名；直接 bind 效果相同、沒有這三個坑。③問 `config/searxng/settings.yml` 為什麼進版控（原本過濾）→ 手改設定要有歷史、密鑰已換佔位字、其他五個 api_key／token 都是空值或佔位；代價是 2,780 行完整複本，W8 改精簡覆寫時一起處理；不想追蹤可 `git rm --cached` 加 ignore，建議維持。④使用者「不想內網防來防去一堆 key」→ **`SEARXNG_SECRET` 從待辦與 `.env.template` 拿掉**：它不是存取金鑰，是 SearXNG 簽 cookie 用的字串，bot 走 JSON API 用不到，內網實例用 compose 的預設值即可（搬遷前後一直如此）；compose 與 settings.yml 第 106 行的註解改成講清楚。`HERMES_API_KEY` 保留：那是 Hermes 軟體自己的要求（沒有 ≥8 字元金鑰 API server 不啟動），一把鑰匙兩個方向共用。補充：拿掉的具體理由是「這個實例裡它沒有功能」（image_proxy 關、limiter 沒開、只在內網聽），不是「內網不用 key」——`NOTIFY_SHARED_SECRET`（擋內網裡別的程式讓 bot 做事）與 `HERMES_API_KEY`（Hermes 自己的要求）照舊。以上連同錨點搬移以 `git commit --fixup` 併回 02，`GIT_SEQUENCE_EDITOR=true git rebase --autosquash 4c33ba0`（git 2.56）；交接檔的 hash 更正後再 fixup 進 docs commit。使用者 10-25 提醒：不要附和、要具體原因（記憶 `no-agreeing-without-reasons`）。
- 2026-10-23 下午～10-24 21:xx（TS-Q1、TS-Q2 **已實作、測試全綠、未部署、未 commit**；回答三個問題）：①`SEARXNG_SECRET` 為什麼要補 → 不急：`secret_key` 簽 cookie、圖片代理網址、防爬 token；compose 一直傳 `SEARXNG_SECRET`（預設值是公開 repo 裡那串 `change_me…`）且環境變數蓋掉檔案值，所以搬遷前後生效的都是那串公開字串，我沒改變行為；searxng 只在內網與 127.0.0.1:8888，影響小，補不補由使用者決定（不補就從待辦拿掉）。②`.dockerignore` → 對現在的 build 零影響（dockerfile 只 COPY requirements 與 entrypoint；BuildKit 會略過沒用到的檔），是對未來 `COPY . .`、關 BuildKit、CI 的保險（32 GB 媒體、root 擁有的 pgvector 檔會進 context 或讓 build 失敗）；三個 dockerfile 共用同一個 context，一份就夠；不要就從快照 02 拿掉。③HM-Q1～Q7 不是在資料目錄那次授權裡決定的，compose 只有草稿，完整利弊在 10-24 的回覆（未定案）。**TS-Q1 做法 (a)**：`telegram_scraper/main.py` 新增 `run_until_stopped(job)`：`loop.add_signal_handler` 接 SIGTERM／SIGINT → 取消主要工作（Telethon `run_until_disconnected` 的 finally 會斷線、runner 的 finally 關 DB）；不是訊號造成的取消照樣往外丟；結束後移除 handler；compose 不動（`docker stop` 預設的 SIGTERM 就對）。**TS-Q2 做法 (a)**：`llm/mcp_server.py` 新增 `uvicorn_config(app)`（`timeout_graceful_shutdown=SEARCH_SETTINGS.mcp_shutdown_grace_seconds`，新欄位預設 2.0），`main` 改成 `uvicorn.Server(uvicorn_config(server.streamable_http_app(**http_options()))).run()`，不再用 MCP 套件的 `server.run("streamable-http")`（它建 uvicorn 時沒設等待上限）。**踩到的坑**：改完後完整測試卡住 10 分鐘以上（行程在 ep_poll、不吃 CPU）：`test_search_mcp_server` 的 HTTP 模式測試原本把 `server.run` 換成假物件再呼叫 `main(["--http"])`，新 main 繞過它、真的 uvicorn 起來永遠不結束；改成 patch `uvicorn.Server`、斷言交給它的 Config 的 port／host／timeout；原本另開的 `test_mcp_server_http.py` 併進去後刪掉。另一個坑：`test_telegram_scraper_stop` 第一版用 `wait_for(timeout=5)` 當保險，但 handler 不取消時，wait_for 的逾時取消會被程式當成訊號造成的乾淨停止，突變抓不到 → 補「收到訊號後 1 秒內要停」（`call_later(1.0)` 設旗標；真實時間，掛 `@timing_sensitive`）。測試：新檔 `test/test_telegram_scraper_stop.py`（4 項：SIGTERM／SIGINT 取消並跑 cleanup、非訊號的取消不吞、結束後 handler 移除；用 fakes 的假 telethon、以獨立模組名載入 main.py）、`test_search_mcp_server` 守則補一句；完整測試 1,720 項全過（97 秒）；突變 4 個全紅（拿掉 timeout → 1 failure；永遠 raise → 2 errors；handler 不 cancel → 2 failures；不接 SIGTERM → 行程被 SIGTERM 殺掉 Terminated）。**部署（給使用者）**：`docker compose restart telegram-scraper search-mcp`（這次 restart 還是舊程式在收訊號，會等 10 秒；之後再 `time docker compose stop telegram-scraper`／`start` 驗證應在 1～2 秒內）；telegram-scraper 的 session 寫入要等它真的停才算，避開補掃剛開始的時候無妨。**快照 04** `6c8509eb3e787ff4bb51d3933ba1cc641f6f00bf` 04-graceful-stop：`fix: let telegram-scraper and search-mcp stop within Docker's grace period`（- telegram-scraper runs python as PID 1 without a SIGTERM handler, so docker stop waited 10 s and SIGKILLed it; cancel the main job on SIGTERM/SIGINT so Telethon disconnects and the DB closes / - search-mcp caught SIGTERM but uvicorn waited forever for the MCP client's open connection; build the uvicorn config ourselves with a 2 s graceful-shutdown limit / - the limit lives in SearchSettings next to the other MCP server settings / - tests cover both: the stop handlers cancel the job promptly and run its cleanup, and the uvicorn config carries the limit）。**scratchpad 第二次消失**：10-24 沒重開機、換了 session，`/tmp/claude-1000/<session>/scratchpad` 整個不在（session 結束就清），manifest 與 .msg 再次從本檔重建；記憶 `env-scratchpad-volatile` 已更正。
- 2026-10-23 14:3x（接續盤點，**未動 code**）：VM 今早 06:2x 重開過（uptime 8 小時），`/tmp` 清空，前一天快照的 manifest、commit 訊息、patch 全沒了，只剩 git 的 tree 物件；靠對話紀錄重建（記憶 `env-scratchpad-volatile`：以後 tree id 與訊息一律同步寫進本檔）。使用者 14:21 把 hermes 的 `restart: unless-stopped` 改成 `always`（和其他服務一致）並重啟了全部容器（14:21 起 Up，bot 12 小時內 0 ERROR）；這一行屬於 Hermes 草稿，已把 01～03 三張 tree 重建成含它的版本。**快照（依序 commit，`git read-tree <tree>` 再 `git commit -F`；patch 可用 `git diff HEAD <tree>` 重算；tree 沒有參照、兩週後可能被 gc，請早點 commit）**：
  - `a44d8a1c575e13b675a9e7aadfbafb46864340bc` 00-ignore-doc：`chore: ignore the whole local doc folder`（- doc/ holds local-only notes (interview prep, design drafts, the snapshot how-to) / - replaces the narrower doc/interview/ rule so new local documents stay out of the repo / - nothing under doc/ has ever been committed）
  - `d04f7119d46e21f6bc0819160a21ce807375e56a` 01-hermes-compose-draft：`feat(compose): add the Hermes agent service draft behind a profile`（- run the official image with only its OpenAI-compatible API server; the bot calls it and posts the results itself / - route model requests through the bot's /v1 endpoint on port 5000 so they share the GPU lock and model allowlist / - put hermes on an internal, isolated network so it can only reach discord-bot and search-mcp / - keep the service behind the "hermes" profile until its state directory and config exist / - make the API key optional at parse time so a missing value does not block the other services）
  - `13a2702f00825d6a15974554abca104c6fb9b7ee` 02-data-layout：`refactor(compose): group runtime data by lifecycle under data/, cache/, run/ and config/`（- move the pgvector cluster to data/pgvector as a plain bind mount; drop the named volume whose device depended on ${PWD} / - put the search index under cache/search-mcp and the GPU lock file under run/gpu_lock, shared by discord-bot and search-mcp through one anchored mount / - keep the SearXNG settings in config/searxng under version control with the secret replaced by the upstream placeholder; its cache becomes a named volume / - set create_host_path: false on data mounts so a missing directory fails loudly instead of starting on an empty cluster or a root-owned lock directory / - update init_volumes.sh, .env.template, .dockerignore, ruff excludes and the comments that named the old host paths; container paths are unchanged）
  - `ac6a0c96ac49d4d97c3d8f26960e76d703894b6c` 03-gitignore-cleanup：`chore: drop the ignore rules for the old data locations`（- vector_data, search_data and gpu_lock have been moved under data/, cache/ and run/, which are ignored as a whole / - the old searxng/ directory is gone too; its settings now live in config/searxng under version control / - anchor the new rules to the repo root so src/scraper/data keeps its own rule）
  - 之後另外：docs（本檔）、chore(settings)（兩個字典）；`it_comfyui_image.py` 不 commit。
  **留給使用者的項目狀態（14:30 查）**：`.env` 仍沒有 `SEARXNG_SECRET`、`HERMES_API_KEY`；`discord_vector_data` 與匿名 volume `a5ea716…` 仍在；hermes 映像還沒 pull；兩個備份檔仍在 `data/backups/`。
- 2026-10-23 上午（兩個問題，**未動 code**；只改本筆）：①使用者問「現在可以把 hermes 建起來嗎、還沒要用、目前的 compose 可以先建起來開始實作程式嗎」→ 現況：映像還沒 pull（`docker images` 空）、`.env` 沒有 `HERMES_API_KEY`、`data/hermes` 空；bot 端程式（notify_server 的 `/v1` 轉發、Hermes 客戶端）不需要 Hermes 在跑就能寫和單測（假後端），Hermes 只在整合測試時才需要，而它要真的回答得先有三件事：主模型 ctx 65536（HM-Q3）、bot 的 `/v1`（HM-Q5）、`data/hermes/config.yaml`。先建起來的用處是用真的 CLI 看工具名與設定鍵（之前都是從文件猜的）。建議順序：(1) 使用者 `.env` 加 `HERMES_API_KEY`、`docker compose pull hermes`、`docker compose run --rm --no-deps hermes --help`／`tools`（一次性容器，不留狀態）；(2) 寫 `/v1` 轉發與測試；(3) 改 ctx 65536（要同意、挑沒人用時）；(4) 寫 config.yaml、`docker compose up -d --no-deps hermes`；(5) 整合測試。Hermes 在 hermes-net 上沒有外網，`hermes setup` 的線上功能（登入、skill 市集）用不到，config.yaml 預計手寫（範本位置 `config/hermes/` 待問）。②使用者 rebuild 時發現 telegram-scraper 也要等 10 秒才被砍，問是不是和 discord-bot 同一個原因 → **是**：entrypoint `exec python /app/main.py`，PID 1 是 python，`main.py` 只有 `asyncio.run`、沒裝 SIGTERM handler；容器內 `/proc/1/status` 的 SigCgt 實測：discord-bot 與 telegram-scraper 都只接 SIGINT、不接 SIGTERM（PID 1 沒有 handler 的訊號會被核心丟掉），Docker 送 SIGTERM 沒反應、10 秒後 SIGKILL、exit 137（16:51 停機時看到）。**search-mcp 也是 137，但原因不同**：uvicorn 有裝 SIGTERM handler（SigCgt 有），graceful shutdown 會等開著的連線關掉，而 Claude Code 的 MCP 客戶端一直連著（現在 `/proc/net/tcp` 就有一條來自 172.18.0.1 的 ESTABLISHED），MCP 套件 2.x 建 `uvicorn.Config(app, host, port, log_level)` 沒設 `timeout_graceful_shutdown`（預設無限等）→ 10 秒被砍。影響：telegram-scraper 的 `finally`（取消補掃、`db.close()`）沒跑；search-mcp 是 stateless、索引是 SQLite WAL，被砍通常無害，但若正在寫索引會留 WAL 等下次恢復。**TS-Q1 telegram-scraper 修法**：(a) `main.py` 用 `loop.add_signal_handler(SIGTERM, task.cancel)` 走正常取消路徑、compose 不動（標準容器做法，`docker stop` 也對） (b) compose `stop_signal: SIGINT` 加 `main.py` 接 `KeyboardInterrupt`（和 bot 一樣）；建議 (a)。**TS-Q2 search-mcp 修法**：(a) `llm/mcp_server.py` 自己建 `uvicorn.Server(Config(server.streamable_http_app(), …, timeout_graceful_shutdown=2))`，不走 `server.run()`（要確認 2.x 有 `streamable_http_app()` 這類取 app 的方法） (b) 接受 137（無狀態）；建議 (a)。兩題等使用者點頭再改。
- 2026-10-22 16:4x～16:5x（資料目錄整理**已執行並上線**，未 commit；使用者 /goal「都依建議、要停就說、先做完、需決議的先做後報告、快照 commit」，16:5x 授權停機與啟動後離開）：**決定（DL-Q1～Q5 全照 14:0x 那筆的建議）**：第一層 config／data／cache／run／logs、第二層依服務；`search_data`→`cache/search-mcp`；`gpu_lock`→`run/gpu_lock`（仍是 bind，compose 用 YAML 錨點讓 bot 與 search-mcp 引用同一個定義）；`searxng/settings.yml`→`config/searxng/settings.yml` 進版控（第 106 行 `secret_key` 換成上游佔位字 `ultrasecretkey`，實際值由 compose 的 `SEARXNG_SECRET` 傳入；檔裡其他 api_key／token 都是空值或佔位）、映像另宣告的 `/var/cache/searxng` 改具名 volume `searxng_cache`（原本每次重建都多一個匿名 volume）；`vector_data`→`data/pgvector` 直接 bind 掛 `/var/lib/postgresql`、刪掉頂層 `volumes.vector_data`、拿掉 `${PWD}`；hermes→`data/hermes`；資料掛載都加 `bind.create_host_path: false`。**另自行決定**：新增 `.dockerignore`（.git、data、cache、run、logs、vector_data、search_data、Telegram media 與 session、music cache、articles db；三個 dockerfile 只 COPY requirements 與 entrypoint）；`data/backups/` 放 pg_dumpall；`.env.template` 補 `SEARXNG_SECRET`、`HERMES_API_KEY`；`scripts/init_volumes.sh` 改建五個目錄；pyproject 的 ruff 排除改 data／cache／run；五處程式註解與 AGENTS.md 三處改新路徑。**Hermes 的 profile 與 `stable` 標籤這輪沒動**（HM-Q4／Q6 要等 config.yaml 準備好：現在拿掉 profile，整批 up 會帶起沒設定的 hermes）。**執行**：16:45 線上 `docker exec pgvector pg_dumpall | gzip -1` → `data/backups/pg_dumpall-20261022-1645.sql.gz`（2.2 GB、3 分鐘、14 張表、`gzip -t` 通過）；容器內完整測試 1,716 項全過（183 秒）；封快照 02 後 16:51:21 `compose stop discord-bot search-mcp telegram-scraper pgvector searxng` → 16:51:37 三個 `mv` 完成（同一個 xfs、擁有者與 SELinux 標籤 container_var_lib_t 保留）→ 16:52:05 `compose up -d`，16:52:22 全部 Up（pgvector healthy 後才起依賴）；bot 16:53:13 登入、16:53:45 通知伺服器起來；**停機約 2 分鐘**。**驗證**：pgvector log「database system was shut down at 16:51:35」、沒有 initdb、`data_directory=/var/lib/postgresql/18/docker`，10 張表筆數＝或＞基準（`discord_messages_raw` 387,158→387,175，停機前 bot 仍在寫；基準檔在本 session scratchpad `pg_baseline_before.txt`）；search-mcp 索引檔 inode 主機＝容器、背景同步照常（新增 4）、容器內搜「兌換碼」3 筆；鎖檔 inode 主機＝bot＝search-mcp；searxng HTTP 200、15 筆結果；telegram-scraper 恢復監聽；bot 與 search-mcp 啟動後 5 分鐘 0 個 ERROR；hermes-net 建立成功、`isolated` 生效（`network inspect` 沒有閘道位址、主機沒有對應的 br- 介面）。**快照**（本 session scratchpad `snapshots/`：`manifest.txt`＋各 `.msg`＋`.patch`）：00-ignore-doc（使用者 10-19 手改的 .gitignore）、01-hermes-compose-draft、02-data-layout（13 檔，含 `config/searxng/settings.yml` 2,780 行）、03-gitignore-cleanup；快照腳本拿掉 `:!doc/`（doc/ 已整個被忽略，點名會讓 `git add` 報錯），`doc/snapshot_commits.md` 已改。**留給使用者**：①`.env` 加 `SEARXNG_SECRET=`（`openssl rand -hex 32`）再 `docker compose up -d searxng`——現在生效的是 compose 寫在公開檔裡的預設字串，搬遷前就是這樣；②~~`sudo rm -r searxng/`~~ **18:0x 已清掉**（使用者「安全的清法、不要影響 production」：先打包到 `data/backups/searxng-old-20261022.tar.gz`（48 KB，含 `.bak`、`.new`），再用一次性 root 容器 `docker run --rm --network none --entrypoint /bin/sh -v …/searxng:/old pgvector/pgvector:pg18-trixie -c 'chown -R 1000:1000 /old'` 改擁有者、主機上一般身分 `rm -r`；searxng 容器全程不受影響（HTTP 200、掛載仍是 config/searxng）；`.gitignore` 的 `/searxng/` 暫時規則已拿掉、快照 03 重封）；③`docker volume rm discord_vector_data`（已閒置、device 路徑已不存在，依 moby 原始碼不會碰到資料）；④沒人用的匿名 volume `a5ea716…` 要不要 `docker volume rm`；⑤commit：照 manifest 順序 00→03 各一個（`git read-tree <tree>` 再 `git commit -F <msg>`），再 docs（本檔）與 chore(settings)（兩個字典）；⑥2.2 GB 的備份檔留著還是刪、之後要不要排 pg_dumpall 定期備份（目前沒有任何自動備份）。**順帶發現**：searxng 啟動 log 有 `Cannot load engine "adobe_stock"`（settings.yml 是舊版的完整複本，列了新映像已移除的引擎；搬遷前就有，容器重建後才看得到，不影響搜尋）→ 改成 `use_default_settings: true` 的精簡覆寫檔時一起處理（W8）；compose 的 `UWSGI_*` 兩行已無作用（映像改用 Granian）。**還沒做**：src/ 底下的資料（articles.db、sent_articles.db、settings/runtime、Telegram session／media、music/cache、scraper/data；由 `test_data_file_paths.py` 釘住）另開一輪；logs/ 裡的 runtime_backup、dictionary_backup、config_backup 要不要搬到 data/backups；Hermes config.yaml 範本放 `config/hermes/`（新檔待問）；compose 第 102 行 Hermes 註解裡的 `--profile hermes` 等 HM-Q6 定案時一起改。
- 2026-10-22 14:0x（資料目錄整理第一輪討論，**未動 code、未搬任何資料、未改 compose**；只改本筆）：使用者「data 分散四處，想把 vector_data/18/docker、search_data 放到 /home/jason/discord/data，不確定 gpu_lock、searxng 要不要放，或放 data/configs；程式、compose、dockerfile 與相關設定都要完整 migrate；請參考業界最推薦的做法，維持維護性與遷移性」→ 兩個 workflow 唯讀盤點（`wf_3804c8ea-509` 字串掃描 61 處＋程式追蹤 52 處、互相對照；`wf_278be0d4-cc5` 主機事實＋業界做法；全程沒啟動、沒停任何容器，`.env` 只列了鍵名、沒讀值）。**事實**：pgvector 3.2 GB（discord_data 3106 MB、telegram_data 13 MB），具名 volume `discord_vector_data`（device=/home/jason/discord/vector_data、帶 compose config-hash 標籤），頂層 999:999 1777、`18/` root 755、`18/docker` 999 700、SELinux container_var_lib_t；search_data 294 MB（jason，重建約 204 秒～3.5 分鐘）；gpu_lock 0 B（flock 鎖檔，程式每次 `O_CREAT` 重開）；searxng 208 KB、977:977（舊版 entrypoint chown 留下的，jason 不能 mv 也刪不掉，要 sudo）、settings.yml 2780 行完整複本、含非預設 secret_key、從未進版控；SearXNG 映像另宣告 `/var/cache/searxng`（現為匿名 volume，空的；另有沒人用的匿名 volume `a5ea716…`）；`data/hermes` 已建（空）。全在同一個 xfs（mv 只是改名、保留擁有者與標籤）；Docker 沒開 SELinux 隔離（容器是 spc_t），不用 `:z`。**目前沒有任何自動備份**（crontab 空、repo 沒有 pg_dump）。**風險查證**：①`${PWD}` 取的是下指令時的目錄（實測從 /tmp 跑會變 /tmp/vector_data），雜湊不同 compose 會問「Recreate (data will be lost)?」，答 Yes 且新路徑是空目錄時 postgres 會靜靜 initdb 空叢集；②local volume 建立後不能改選項，改 device 就會被問重建；改成直接 bind 後舊 volume 閒置、不影響；`docker volume rm` 依 moby 原始碼不會刪 device 內容（先 unmount、只刪空的 `_data`），未實測；③bind 來源不存在時 Docker 會自動建（root），pgvector 會在空目錄 initdb，gpu_lock 會變 root 的、appuser 開不了鎖檔只記 warning、兩容器各排各的隊 → 資料目錄的 bind 要加 `bind: create_host_path: false`；④PG18 映像 VOLUME 是 `/var/lib/postgresql`、PGDATA 是 `18/docker`（為了 pg_upgrade --link），要整包掛上層、不能只搬 `18/docker`；檔案層級搬移要停機；⑤`.gitignore` 現在沒有忽略 `data/`（`git check-ignore` 實測），`vector_data/*` 只比對根目錄，搬進 data 就不算被忽略，repo 有公開鏡像 → 搬任何東西、Hermes 寫入前先加 `/data/`（要錨定，不然會連 `src/scraper/data/` 一起忽略）。**業界做法（附來源，記在本 session 的 facts_industry）**：第一層依生命週期分 config／data／cache／logs／run（FHS、systemd 的五種目錄、XDG；GitLab Docker 用 config／logs／data），第二層依服務分（Immich、SearXNG 官方 compose）；單機要整包搬家用 bind mount＋相對路徑；手寫設定不含密鑰才進版控、密鑰走環境變數（12-factor）；可重建的快取和不可重建的資料分層（FHS `/var/cache`），放 data 底下就放 `CACHEDIR.TAG`；資料留在 repo 底下（gitignore）是 Immich、Mastodon、Supabase、SearXNG 範例的做法。**牽動點（容器內路徑全部不變、程式只改註解）**：compose（bot gpu_lock 38-41、search-mcp search_data 74-77 與 gpu_lock 78-80、hermes 104-105／115-117／120、pgvector 205 與頂層 volumes 261-267、searxng 228-231 與註解 234-239）；`.gitignore` 2-4、27-30；`pyproject.toml:8`（ruff extend-exclude 寫死 search_data、searxng）；`scripts/init_volumes.sh:7-10、18`（建目錄，沒有文件提到它）；註解 `search_settings.py:19-21`、`services/search/index.py:4`、`services/search/__init__.py:7-8`、`llm/retrievers/intel/client.py:4`、`lemonade_gate.py:82-84`；`AGENTS.md:41`（高風險資料清單補新路徑與 data/hermes）、`:47`（search-mcp 例外寫的是 search_data/）、`:73`；本檔描述現況的段落 321、330、336、338、339、352、402、421、429、527、607、627、1488（歷史紀錄不改）；`doc/llm_worker_design.md:33`。不用改：三個 dockerfile 與 entrypoint、Makefile、CI、`.mcp.json`、`.env.template`、`.vscode`、`.claude`、守衛與測試（都用暫存路徑；`test_shared_conventions` 只擋寫死 /app、/logs）。程式只認容器路徑（`search_settings.py:22` 的 `/search_data/search_index.db`、`lemonade_gate.py:85` 讀 `LEMONADE_GPU_LOCK_PATH`）。**待決（DL-Q1～Q5）**：DL-Q1 第一層怎麼分：(a) config／data／cache／run／logs（data＝一定要備份、不能重建）(b) 全部放 data 底下（data/configs…）(c) 只依服務分；建議 (a)。DL-Q2 search_data：(a) `cache/search-mcp` (b) `data/search-mcp`＋CACHEDIR.TAG；建議 (a)。DL-Q3 gpu_lock：(a) `run/gpu_lock` bind（機制和現在一樣、已驗證，`run/` 不備份）(b) tmpfs 具名 volume `o: uid=1000,gid=999,mode=0770`（語意最乾淨，跨容器共用依 moby 原始碼推論、未實測，會推翻 402 的 10-08 決定）(c) 不動；建議 (a)，和 402「不改 named volume」一致。DL-Q4 searxng：(a) `config/searxng` 並進版控（先刪 settings.yml 的 secret_key 行、在 .env 設 SEARXNG_SECRET）(b) `config/searxng` 但先不進版控 (c) `data/configs/searxng`；建議 (a)，手寫設定放 data 就沒有版本紀錄；搬法是 cp（新檔歸 jason，FORCE_OWNERSHIP=false 照樣讀得到），舊目錄由使用者 sudo 刪；快取 `/var/cache/searxng` 改具名 volume 或維持匿名，可以晚點決定。DL-Q5 pgvector：(a) 改成直接 bind `./data/pgvector`→`/var/lib/postgresql`、加 `create_host_path: false`、刪頂層 volumes (b) 保留具名 volume、device 改相對路徑（要答 Yes 重建 volume）；建議 (a)，和其他服務同一種寫法、不綁專案名、拿掉 `${PWD}`；搬前先 `pg_dumpall`。hermes 直接改 `./data/hermes`（已建），範本若要放就放 `config/hermes/`（新檔待問）。**搬法草案（指令給使用者跑，避開 03:00～07:30）**：先改 `.gitignore`（加 `/data/`、`/cache/`、`/run/`）→ `pg_dumpall` 備份 → 停 bot、search-mcp、telegram-scraper、pgvector → `mv vector_data data/pgvector`、`mv search_data cache/search-mcp`、`mv gpu_lock run/gpu_lock`、cp searxng → 改 compose、`docker compose config --quiet` → up → 驗證（PG 筆數、search-mcp 搜得到、兩容器鎖檔 `stat -c %d:%i` 相同、searxng 有回應）→ 確認後 `docker volume rm discord_vector_data`（mv 後 device 已不在，刪不到資料）、刪 `.gitignore` 舊行。bot 這次重建會順便套上 Hermes 草稿的 hermes-net（無害）。**範圍外、同樣是資料散在各處（要改程式，建議另開一輪）**：src/ 底下的 articles.db（524 MB＋WAL 100 MB，scraper 寫、bot 與 search-mcp 讀）、sent_articles.db（32 MB）、settings/runtime（44 KB）、Telegram session（登入憑證，644、bot 與 search-mcp 容器也看得到）、Telegram media（32 GB，相對路徑寫進 PG 3,827 列）、music/cache（1.3 GB）、scraper/data（fb_posts.json 是去重的狀態）；這些由 `test_data_file_paths.py` 釘住（相對 APP_ROOT）。logs/ 裡混了 runtime_backup、dictionary_backup、config_backup 三種備份。**順帶發現**：.env 沒有 `SEARXNG_SECRET`，實際生效的是 compose:241 寫在公開檔案裡的預設字串，而且它會蓋掉 settings.yml 的 secret_key；compose:242-243 的 `UWSGI_*` 已無作用（映像改用 Granian）；整個 repo 沒有 `.dockerignore`（BuildKit 只傳用到的檔，目前不影響，新檔待問）。
- 2026-10-22 09:2x（Hermes 串接第四輪，**未動 code**；只改 `docker-compose.yaml` 的註解與本筆，未 commit）：使用者要求這次新增的 compose 註解「改專業一點」→ 改用精確術語（端點、驗證、宿主機、預設路由、變數插值），一行一件事，端點與網路用途改成條列，拿掉口語說法；內容與理由不變，設定一行未動，`docker compose config --quiet` 通過。接著問「profile 的意義是什麼、不用就整段註解掉不就好、用 profile 比較好嗎」→ 討論，**未改檔**。事實（Compose 文件 profiles 頁）：不點名的 `up` 跳過有 profile 的服務；點名服務時 profile 自動開啟、連同它的 depends_on 一起啟動（所以註解裡 `docker compose --profile hermes up -d hermes`、`--profile hermes run … setup` 的 `--profile hermes` 是多的）；不帶 profile 的 `down` 只停沒有 profile 的服務，hermes 會繼續跑；容器一旦啟動就照 `restart: unless-stopped` 運作，開關是 `docker compose stop／start hermes`（**更正**：當時說「三種寫法都一樣」不對：一般服務被 stop 後，不點名的 `docker compose up -d` 會把它重新啟動，只有 profile 能讓「關著」維持住）。**HM-Q6 hermes 用 profile、整段註解、還是一般服務**：整段註解的坑是 compose 不檢查被註解的設定（放久了壞掉沒人知道）、開關要改進版控的檔、Hermes 還在跑時註解掉會變孤兒容器（每次 up 警告、`--remove-orphans` 會刪）；profile 的坑是多一個觀念、不帶 profile 的 `down` 會漏掉它；一般服務的坑是不點名的 `up -d` 會帶起它。profile 只防「不點名的 `up -d` 把還沒準備好的 Hermes 帶起來」（`hermes_home` 沒建會啟動失敗；bot 的 `/v1` 沒寫時它跑起來沒模型可用、還佔記憶體上限 2 GB）。建議：試用這一週用 profile，穩定、要長期開著後拿掉 profiles 改成一般服務；另建議順手把註解裡多餘的 `--profile hermes` 拿掉（等 HM-Q6 定了一起改）。使用者接著說「一起起來也沒關係吧，沒有 call 或程式去打，hermes 也會一併做動嗎」→ 查 Hermes 官方文件：①沒人呼叫時不會打模型：gateway 每 60 秒檢查一次排程，只跑使用者建立的工作（存在 `cron/jobs.json`，文件沒提到內建工作）；Curator（整理 Hermes 自己寫的 skill）預設開、每 168 小時且閒置 2 小時才跑，搬移 stale／archive 不用模型，用模型合併的 `curator.consolidate` 預設關，沒有它自己寫的 skill 時模型那段整個跳過，新安裝第一次要等滿一個週期；②**被呼叫過之後會自己多打模型**：`auxiliary.background_review.enabled` 預設 true，每輪回答後在背景重讀這段對話、決定要不要更新記憶或 skill，預設用主模型，輸入上限預設是模型 context 的 75%（上限 60 萬、讀不到時 12 萬）；`defer: auto`、`defer_max_age_s: 1800`（文件說延後執行是在它自管的本機 runtime 上）。這次呼叫不是 bot 發起的，一樣經 bot 的 `/v1` 排 GPU 鎖，會和插話、/askai 搶顯示卡、洗掉快取。當時順著使用者改建議成「拿掉 profiles」，使用者指正「你幫我分析利弊，不應該只是叫我拿掉」→ 重新比較（不帶 profile 時 `docker compose config --services` 列不出 hermes，不點名的 up／pull／down 都不碰它）：**profile 的好處**：stop 之後整批 up 不會帶回來（關得穩）；只有 `docker compose pull hermes` 才換版（HM-Q4 選 stable 的理由要靠它才成立，Hermes 每週改版、可能改設定格式）；準備期間不會被誤啟動。**壞處**：多一個觀念、操作都要點名；不點名的 down 漏掉它，hermes-net 也因還有容器接著刪不掉；之後若常駐，點名只是多打字。**一般服務的好處**：最直覺、整批指令一次到位。**壞處**：stop 不穩（整批 up 會帶回來，要真的關只能註解或刪）；整批 pull 會順便升級；準備期間整批 up 會報錯或讓它一直重啟（只洗 log，閒置記憶體要跑起來才知道，上限 2 GB）。**HM-Q6 建議維持保留 profile**（試用期一定要；之後也偏向保留，第 7 天依「常駐還是選用」再決定），決定後順手拿掉註解裡多餘的 `--profile hermes`。使用者再問「down、up 都不影響它、還要特別指定，那用一個獨立的 compose 不就好，幹嘛放同一個」，接著說明「放在一起就代表這些服務是一起關聯的，還要在關聯的 container 之中分開，會不會很怪」→ 同意這個原則：profile 是給平常不跑、偶爾才開的工具用（官方文件的例子是除錯用的 phpmyadmin）；Hermes 由 bot 呼叫、用 bot 的模型端點、共用 hermes-net 與 HERMES_API_KEY，是同一套系統的一部分，該放同一份 compose、當一般服務一起起停。**HM-Q6 建議改為一般服務（拿掉 profiles）**，連帶 **HM-Q4 改建議釘 `v0.22.2`**（沒有 profile 時不點名的 pull 會順便換掉 stable，釘版本才讓升級變成改 compose 的刻意動作；草案待決 3 原本也建議釘 tag）；長期不要它時就從 compose 拿掉（stop 後不點名的 up 會帶回來）；第一次不點名的 up 前先建好 `hermes_home` 與 config.yaml。拆成獨立 compose 以 workflow 查證（`wf_bbc2e6fb-597`，一位對照 Compose 文件與 v5.6.0／compose-go v2.16.1 原始碼並在 scratchpad 用 `docker compose config` 實驗，一位替拆開辯護；未啟動任何容器、未讀 .env），**結論不變：不拆**。查證的事實：①同目錄的第二份檔沒寫頂層 `name:` 就是同一個專案 discord，兩邊互把對方的容器當孤兒，從 hermes 檔下 `--remove-orphans` 會刪掉整組 bot；`.env` 的 `COMPOSE_PROJECT_NAME` 會蓋過 `name:`；②拆開要 `external: true` 加寫死的網路名稱（現在會是 `discord_hermes-net`，或主檔替網路設固定 `name:`），網路不存在時 hermes 在建任何容器前就失敗；跨專案不能寫 depends_on（`required: false` 也報錯）；子目錄的 compose 讀不到根目錄 `.env`（`${HERMES_API_KEY:-}` 會靜默變空）；只帶 `-p hermes` 不帶 `-f` 會用主檔另建一整套；③拆開後「要特別指定」不會消失，只是從點名服務變成每個指令帶 `-f`；拆開真正多得的只有「hermes 區塊寫壞不擋 bot 的指令」（同一份檔不用 `:?`、給指令前先跑 `config --quiet` 也擋得住）；`include:` 等於同一份檔（同專案、錯誤不隔離）；④profile 的細節：點名時自動啟用並連同 depends_on 收斂（`up -d hermes` 會收斂 search-mcp→pgvector，設定分岔就重建；`run … setup` 也一樣，要加 `--no-deps`）；`docker compose ps` 看得到 profile 服務、`logs` 看不到；v5.6.0 的 `--remove-orphans` 不會刪 profile 停用的服務（v2.23.2 起修正）；不帶 profile 的 down 只印「Resource is still in use」警告、退出碼 0；⑤**新發現（依原始碼推論、未實測）**：hermes 還接在 hermes-net 上時改了這張網路的定義，不含 hermes 的整批 up 會先停掉 bot、search-mcp、再刪網路失敗、整個計畫中止，兩個服務可能停在已停止狀態（手動停止不受 restart: always 救回）；一般服務會把三個放進同一個計畫處理。isolated 還沒實測，試用期可能要改網路，這點支持拿掉 profile。**建議（待使用者確認後改 compose）**：同一份檔、拿掉 profiles 當一般服務；HM-Q4 釘 `v0.22.2`；註解拿掉 `--profile hermes`、setup 改成 `docker compose run --rm --no-deps -it hermes setup`、寫明第一次整批 up 前先建 `hermes_home` 與 config.yaml；保留 `depends_on: search-mcp`（它是真的依賴），只動 hermes 時用 `docker compose up -d --no-deps hermes`。反方的建議是試用期保留 profile、只點名服務、常駐後再拿掉；沒採用，理由是使用者的原則（同一份 compose＝一起起停）與第⑤點。另：`vector_data` 用 `${PWD}`，從 repo 以外的目錄跑 compose 會讓 pgvector 的 volume 設定不符、compose 會問要不要重建（預設否），和 Hermes 無關、既有問題，指令都在 ~/discord 執行就沒事。使用者問「config.yaml 是幹嘛的」→ 解釋：Hermes 自己的設定檔（`hermes_home/config.yaml`，容器內 `/opt/data/config.yaml`），管它用哪個模型、能用哪些工具、連哪些 MCP、記憶與背景工作；compose 的 environment 只管容器層（API server 開關、位址、金鑰、uid）。只在啟動時讀，改了要 `docker compose restart hermes`（官方 web dashboard 與 multi-profile 文件、GitHub issue #13146）；沒寫時會不會自己產生預設檔，文件沒寫。要寫的內容：`model`（custom、`base_url: http://discord-bot:5000/v1`、模型名、`key_env: API_SERVER_KEY`、`context_length`）、`mcp_servers.intel`、`agent.disabled_toolsets`、`auxiliary.background_review.enabled`、`gateway.api_server.max_concurrent_runs: 1`。**新的待決（寫轉發程式時定）**：模型名會在 `llm_runtime_config.json` 與 config.yaml 各一份，bot 換模型時 Hermes 會被白名單擋（400）；選項 (a) bot 的 `/v1` 一律換成自己正在用的模型、Hermes 填固定代號，(b) 兩邊各寫一份、換模型時一起改；建議 (a)（Hermes 選不了模型，比白名單更嚴，也少一處要同步）。**新檔待問**：`hermes_home` 不進版控，config.yaml 丟了就沒了；要不要在 repo 放一份範本（位置待定）。**HM-Q7（新）試用期要不要關 `auxiliary.background_review`**：(a) 關，記憶只在對話中由它自己用記憶工具寫 (b) 開，第 4／6 天量 GPU 時把這些背景呼叫算進去；建議 (a)，和草案待決 6「Hermes 記憶」第 7 天一起重新決定。
- 2026-10-21 13:xx（Hermes 串接第三輪，**未動 code、未改 compose**；只改本筆與 11:xx 那筆的 HM-Q2）：使用者問「有必要多一個 hermes-net 嗎」，又問第二輪那段「internal 擋不住 VM 本機、isolated、連不到通知伺服器不對」是什麼意思 → 白話解釋：discord-net 在 VM 上是一塊虛擬網卡（`br-5e0c48c3c2f4`，172.18.0.1），容器出去都經它由 VM 轉送；internal 只關掉轉送，閘道位址本身是 VM 自己的位址，VM 上聽 0.0.0.0 的 sshd、Cockpit 照樣連得到；isolated 讓那塊網卡不配位址；bot 為了叫 Hermes 也接 hermes-net，所以 Hermes 連得到 bot:5000，擋它的是通知密鑰。HM-Q2 補上選項 (b)「直接接 discord-net」與兩邊碰得到什麼的比較，記在 11:xx 那筆。接著問「那 hermes 怎麼存取 lemonade 的算力」→ 解釋：經 bot 的 `/v1` 轉發，bot 兩張網路都接但不轉送封包，在 hermes-net 收下請求、驗金鑰與模型名、排同一把 GPU 鎖，再自己從 discord-net 打 Lemonade、串流傳回；Hermes 碰不到載入卸載這類管理功能。再問「已經 internal 了，isolated 的意義是什麼」→ 用兩次連線解釋：連 Lemonade 要 VM 轉出去，internal 擋得住；連 VM 自己在 hermes-net 上的位址（例如 172.19.0.1:22）不用轉送，internal 不擋，isolated 讓 VM 在這張網路上不拿位址才擋得住。沒有新決定。
- 2026-10-21 11:xx（Hermes 串接第二輪：模型轉發放哪裡，**未動 code**；只改 `docker-compose.yaml`、本筆與 04:0x 那筆，未 commit、未啟動任何容器）：使用者質疑「同樣的 container 一直創幹嘛、llm-proxy 不就跟 discord_bot 一樣、為什麼不用 discord_bot 當主要轉發中心、架構應該要簡單」→ workflow 唯讀評估（bot 現有零件、維運事實、設計 bot 當轉發、反方找破綻，共 4 個 agent；原文在本 session scratchpad 的 mapBot／mapOps／advocate／skeptic）→ **建議：模型轉發做在 bot 的通知伺服器上（5000 加 `/v1/chat/completions`、`/v1/models`），不另開 llm-proxy**，compose 已照這個改，等使用者確認（HM-Q5）。**放 bot 才有的好處**：①bot 本來就要接 hermes-net 叫 Hermes，Hermes 一樣連得到 bot:5000，另開容器在網路上沒有多隔離什麼；②讓位現成：`lemonade_gate.stream_busy()`／`foreground_recently_active()` 只看本行程，插話、persona agent、記憶抽取已經用它們讓位，Hermes 拿著閘門時會自動讓；另開容器要新做跨行程旗標檔（草案待決 1 的讓位旗標因此不必做）；③`llm_usage` 留在同一個 `discord_bot.log`、同一個時間順序（另開的行程不能寫同一個輪替檔）；④另開容器要補 PG 帳密：`services/llm_service.py` import 時就建 `LLMServiceSettings()`，缺 `PGVECTOR_USER`／`PASSWORD` 會 ValidationError（容器內實測）；放 `llm/` 也會被分到技術層，import `log_llm_usage` 是往上引用，分層守衛會擋；⑤少一個映像（推論：掛 profile 的 build 服務在不帶 profile 的 build 不會重建，套件會分岔）與約 60～80 MB 記憶體（VM 可用約 2.5 GiB、swap 已用 1.7 GiB）。search-mcp 當初獨立的五個理由（建索引搶 event loop、改程式要重啟 bot、開 port 的行程不該握 token、MCP SDK 是 ASGI、索引只能一個寫入者）套到轉發只剩「改程式要重啟 bot」。**代價與擋法**：①改轉發程式要重啟 bot（實測平常約 49 秒、VM 開機負載約 2 分 20 秒；斷語音、/askai 佇列清空；09-29～10-18 登入 65 次）：串接第 3～5 天本來就要改 bot，改動累積一次重啟；②Hermes 的正常流量進到握有 token 的行程：`/v1` 只認 `Authorization: Bearer <HERMES_API_KEY>`、`/notify` 照舊只認 X-Notify-Secret，兩把不互通，HERMES_API_KEY 沒設就不掛 `/v1`；限本文大小（aiohttp 預設 `client_max_size` 1 MiB 也要調大）與同時數；真正擋住風險的是關掉 Hermes 的 terminal／file／code／browser／委派工具，兩案都要做；③互鎖：行程內的 asyncio.Lock 沒有等待上限，bot 若拿著 GPU 鎖去叫 Hermes，Hermes 回頭要同一把，bot 的 AI 會停到 HTTP 逾時或 Hermes 放棄（反方照 Hermes 文件預設估 30 分～2 小時以上；跨行程鎖檔則 15 分鐘放行）；擋法：閘門用 ContextVar 記「這個 task 拿著鎖」，Hermes 客戶端第一行斷言沒拿著，加測試；代理等鎖最多 120 秒回 503；④行程內先來先拿：Hermes 同時送多個請求會全排在 /askai 前面；擋法：代理只在閘門沒人拿、也沒人排時才進，Hermes 設 `max_concurrent_runs: 1`；⑤和 M9（`doc/llm_worker_design.md`：bot 只做 Discord I/O 與排隊）不衝突，轉發只做排隊與搬位元組；M9 的 llm-worker 上線時再評估要不要併過去，模組說明寫明。**沒選的**：放 search-mcp（不握 token、重啟約 15 秒、已接兩張網路、MCP SDK 2.3.0 有 `custom_route`），但和 bot 是兩個行程（讓位要另做旗標、llm_usage 分兩個檔）、搜尋服務變成模型入口，自訂路由也不受 MCP 的 Host 白名單保護；另開 llm-proxy 要多寫約 120 行（自己的 main／log／設定、跨行程讓位旗標）。**更正第一輪**：①64k 不是去 Windows 改：主模型的 `ctx_size: 32768` 在 `src/sys_settings/llm_runtime_config.json`（進版控）的 `backends.lemonade.model_load_options`，`LLMService._ensure_model_loaded` 每次對話前推給 Lemonade（`_lemonade_load_model` 的 `save_options` 預設 True）；改成 65536 就是改這個檔，要使用者同意；下一次對話會重載模型（約 22～60 秒），重載不經過 GPU 閘門，要挑沒人在用的時候。②internal 網路的橋接介面預設有位址，容器連得到 VM 主機上聽 0.0.0.0 的服務（`ss -ltn`：22、9090、27500、5355；Docker 文件 port publishing 頁），要加 `com.docker.network.bridge.gateway_mode_ipv4: isolated`（文件：只能和 internal 一起用；本機 Docker 29.9.1，還沒實際建網路驗證）；bot 接上 hermes-net 後 Hermes 連得到 bot:5000，靠密鑰擋（10-16、10-18 啟動後都沒有「沒設共用密鑰」警告，表示有設）。第一輪 compose 註解寫的「連不到 bot 的通知伺服器、就算被誘導也沒有路」不成立，已改。**compose 這輪改了**：刪 `llm-proxy`；discord-bot 加接 hermes-net、5000 的註解改成兩組入口各驗各的金鑰；hermes 的 depends_on 只留 search-mcp、刻意不寫 discord-bot（compose 帶起一個服務時預設重建設定有變的依賴，寫了 `up -d hermes` 可能重建 bot、斷語音、不看維護時段）；hermes-net 加 isolated；hermes 說明改成模型走 `http://discord-bot:5000/v1`。`docker compose config --quiet` 有無 profile、有無金鑰都通過。**部署注意（指令給使用者跑）**：discord-bot 多了網路，下一次不帶服務名的 `docker compose up -d` 或 `up -d discord-bot` 就會重建 bot；bot 端的程式寫好、`make test` 全綠之前不要跑不帶服務名的 up。程式好了之後：先 `docker compose --dry-run up -d` 確認只動 discord-bot 與 search-mcp，再 `docker compose up -d discord-bot search-mcp`（避開 03:00～07:30）→ `mkdir hermes_home` → setup → `docker compose --profile hermes up -d hermes`。驗證：`docker exec discord-bot cat /proc/net/route` 預設路由仍走 discord-net；hermes 打 `/notify/fb` 回 401；hermes-net 的橋接介面沒有 IPv4 位址。**寫 bot 端時不能漏（兩案都一樣）**：Hermes 的回覆發到頻道一律帶 `AllowedMentions.none()`（`post_to_channel` 只在呼叫端有給時才帶，`discord_bot.py` 也沒設全域預設，內容有 @everyone 會真的通知；/askai 有帶）；兩端都要真的串流（`http_client.chat_completion` 寫死 `stream: False`，bot 沒用過串流；Hermes 文件預設串流 180 秒沒內容就砍，排隊加冷讀 64k prompt 約 200 秒，要調大它的停滯逾時）；`handler_cancellation` 要開（aiohttp 預設 False，Hermes 斷線後舊 handler 還會拿鎖跑完）；Hermes 設 `max_concurrent_runs: 1`、調低重試（文件預設重試 3 次再恢復 5 輪，加上 http_client 的 2 次會相乘）；bot 重啟時 Hermes 進行中的 run 沒人收（兩案一樣），之後由 bot 把 run id 記在 runtime_file、啟動時對沒收完的 stop。估程式約 400 行、測試約 430 行；預計新檔 `services/llm_proxy.py`（服務層）、`test/test_llm_proxy.py`、`test/test_llm_http_stream.py`、`test/integration/it_llm_proxy.py`，動手前要問。**待決（第二輪起以本筆為準）**：HM-Q1 掛件形態（甲：沒有 Discord 帳號、bot 叫它；乙：自己的帳號），建議甲，本輪的轉發設計建在甲上；HM-Q2 要不要另開 hermes-net（13:xx 使用者問「有必要多一個 hermes-net 嗎」）：它不是為了 bot 和 Hermes 互通（同在 discord-net 也通），只用來限制 Hermes 連得到哪裡。(a) 另開 internal＋isolated 的 hermes-net：Hermes 只碰得到 discord-bot:5000（要金鑰）與 search-mcp:8765；(b) Hermes 直接接 discord-net：碰得到外網、Windows 上的 Lemonade（`http_client` 送的是 `Bearer no-auth`，Lemonade 沒有驗證，能直接對話、載入與卸載模型，繞過 GPU 鎖與模型白名單）、VM 本機的 sshd 22、Cockpit 9090 與 passimd 27500（`ss -ltn`；passim 是 Fedora 內建、在區網分享韌體檔案的服務，不用密碼）、scraper:8000（只有唯讀的公開文章 API，沒驗證）、searxng、pgvector（要密碼）；telegram-scraper 沒開對外 port。選 (b) 時「不直連 Lemonade」只剩兩個約定：Hermes 不知道位址（和 bot 的一樣，猜得到）、它的工具關乾淨（API server 平台文件寫預設給完整工具含終端機、工具名隨版本變、它讀的論壇內容任何人都能寫）。建議 (a)，代價：compose 多約 8 行、bot 與 search-mcp 各多接一張網路（各重建一次，bot 本來就要為轉發程式重啟）、Hermes 沒有外網（內建網路工具、skill 市集、更新檢查不能用；`hermes setup` 連不到外網，config.yaml 可能要手寫），之後要網路搜尋就把 searxng 接上 hermes-net；HM-Q3 64k：(a) 主模型 `ctx_size` 改 65536（KV 約 2→4 GiB，可併進已定案的 131k 實驗）(b) Hermes 謊報 `context_length`（超過 32k 就失敗、壓縮門檻也錯），建議 (a)；HM-Q4 映像 `stable`（手動 pull 才換）或 `v0.22.2`，建議 `stable`（草案待決 3 原本建議釘 tag）；HM-Q5 模型轉發放 bot／search-mcp／另開容器，建議 bot。**之後再談（實作細節）**：新檔或塞進 notify_server（建議新檔）；金鑰兩個方向共用 HERMES_API_KEY（建議共用）；Hermes 呼叫的 max_tokens 上限 4096 或 8192（建議 4096）；優先序先做「Hermes 避開 /askai 結束後 90 秒」（沿用 `foreground_recently_active`）；`gpu_exclusive` 重入改成直接丟錯（建議要）。另：反方提到日報與 /配隊 用 bot 現有的工具輪（`generate_reply(tool_runner=…)`、`combine_runners`）也做得到，不需要 Hermes、不必調 64k；Hermes 的價值在 skill、記憶、多步驟長任務。只記下，未討論。**還沒做的牽動點**：`.gitignore` 加 `hermes_home/`（現有 10-19 使用者手改、未 commit 的那行，沒碰）、`.env.template` 加 `HERMES_API_KEY`（兩個方向共用）、Hermes 的 `config.yaml` 範本（model 指 `http://discord-bot:5000/v1`、`key_env: API_SERVER_KEY`、`context_length` 釘住、`mcp_servers.intel` 指 `http://search-mcp:8765/mcp`、`max_concurrent_runs: 1`、關工具）、草案原文還沒進 repo（第一輪問過要不要先放進本檔，未答）。
- 2026-10-21 04:0x（Hermes 串接第一輪討論，**未動 code**；只改 `docker-compose.yaml` 與本筆，未 commit、未啟動任何容器）：使用者貼「Hermes 串接：一週實作交接」草案（10-20 22:10 版，**還沒進 repo**，原計畫第 7 天併進本檔 `hermes-integration` 區塊），要求先討論、先改 compose 給他看、問有沒有現成 Docker、說「希望 Hermes 是 discord-bot 的掛件」。**查到的事實**：①官方映像 `nousresearch/hermes-agent`（Docker Hub），`stable`／`latest`＝v0.22.2（10-15），另有 `rc.1-v0.22.3`（10-20）與開發版 `main`，壓縮後約 1.1 GB（含 Node、Playwright＋Chromium），不必自己 build；狀態目錄是 `/opt/data`（草案寫的 `HERMES_HOME: /hermes` 不對），入口已是 hermes、指令寫 `gateway run`；預設 uid 10000，`HERMES_UID`／`HERMES_GID` 可對齊主機帳號；建議記憶體 2～4 GB。②Hermes 有 OpenAI 相容的 API server（`API_SERVER_ENABLED`、`API_SERVER_HOST`、`API_SERVER_PORT` 預設 8642、`API_SERVER_KEY` 一律必填）：`/v1/chat/completions`（無狀態）、`/v1/responses`（伺服器端存狀態）、`/v1/runs`（長任務、事件串流、可中止）、`/api/jobs`（排程）；`X-Hermes-Session-Id` 接續 session；客戶端的 system 訊息疊在它自己的 system prompt 上；`gateway.api_server.max_concurrent_runs` 預設 10。③**Hermes 要求模型 context 至少 64k，小於就在啟動時拒絕**；Lemonade 主模型現在 ctx 32,768（`llm-inference-kv`），草案第 4 天「放不下就砍工具、不要調 ctx」行不通。④草案 compose 的 `<<: *main-build` 應為 `build: *main-build`。**compose 改了**：新網路 `hermes-net`（`internal: true`，沒有對外路由）；新服務 `llm-proxy`（bot 映像、`python -m llm.proxy_server --port 8080`、掛 src／logs／gpu_lock、接 discord-net＋hermes-net、模型白名單照草案待決 2 的建議讀 `llm_runtime_config.json` 所以沒有 `PROXY_MODEL_ALLOWLIST`）與 `hermes`（官方映像 `stable`、`./hermes_home:/opt/data`、只開 API server、`API_SERVER_KEY=${HERMES_API_KEY:-}`、`mem_limit: 2g`、只接 hermes-net）；兩者掛 profile `hermes`，一般的 `docker compose up -d` 不會帶起；search-mcp 加接 hermes-net（下次 up 會重建它）；discord-bot 沒動。`docker compose config` 在有無 profile、.env 有無金鑰時都通過。踩到的坑：`${HERMES_API_KEY:?…}` 必填寫法連沒啟用的 profile 也檢查，.env 沒這個值時所有服務都起不來，改成可空（空白時 Hermes 自己拒絕開 API server）。**本輪提議改的共識（待使用者確認）**：「掛件」照字面解成 Hermes 沒有自己的 Discord 帳號，只有 bot 帶金鑰經 API server 叫它、結果由琇紫發（草案原本是自己的身分「觀星台圖書館員」）；連帶改動：硬規則 1（bot 會多一個 HTTP 客戶端與指令，不 import Hermes）、5／6（allowlist 不用，工具收斂改套在 API server 平台）、第 3 天（不建 Discord application，改 bot 端接一個只有擁有者能用的測試指令，要重啟 bot、bot 要加接 hermes-net）、第 4 天（日報排程放 bot 的 `run_due_loop`，Hermes 只執行）、第 5 天（`/配隊` 斜線指令註冊在 bot）、第 6 天（兩隻 bot 互回的核對不需要）、契約三條收成一條（bot → Hermes），`notify_server` 不加代貼、補課交接檔的端點（結果在回應裡帶回來）；新規則：bot 呼叫 Hermes 時不能拿著 GPU 鎖（Hermes 經代理拿同一把，會互鎖）。**本輪提出待決 HM-Q1～Q4**（掛件形態、internal 網路、64k、映像標籤）；題目、更正與還沒做的牽動點從第二輪起記在 10-21 11:xx 那筆，以那裡為準（本輪對 internal 網路與改 ctx 位置的說法有誤，那筆有更正）。
- 2026-10-19 11:xx（版控整理，**未動 code**；只改 `.gitignore` 與本筆，未 commit）：使用者問還有沒有沒 commit 的東西、`doc/` 兩份說明要不要進版控、沒必要的都 ignore → 兩份說明照 10-16 的決定不進版控（`snapshot_commits.md` 是本機的拆 commit 作法；`llm_worker_design.md` 是 M9 設計稿，它的四個待決只寫在那份檔）；`.gitignore` 把 `doc/interview/` 改成整個 `doc/`（11:58 使用者手改成只留這一行，`it_comfyui_image.py` 沒加進 ignore，仍是未追蹤檔，照舊不 commit）。doc/ 的兩份和 `it_comfyui_image.py` 都沒進過歷史；已追蹤的檔裡沒有執行期資料（db、session、runtime、log）。還沒 commit：`.gitignore`、兩個字典（bot 補的表情 3 行、貼圖 1 行，照慣例另做 `chore(settings)`）、本筆交接檔。**本機領先 `dcbot/master`（`bff1eb9`，10-16）11 個 commit（`2e59d49`…`4c33ba0`，10-18），還沒推送**；GitHub 公開鏡像 10-08 查證時和 GitLab 一致，所以應該也還看不到這 11 個。根目錄仍沒有 README。另外，面試資料盤點時的反方驗證查到音樂斷點續播卡住的新 bug，記在「點歌機器人專區 › 語音斷線後的自我重連競態」最後一點。
- 2026-10-17 16:xx（第三輪架構審視的討論與反查，**未動 code**；改了交接檔與記憶）：使用者貼另一個 session 10-16 21:27 產出的架構審視 HTML（同一件事寫好幾份、介面太寬：十張候選＋六個 bug），「先與我討論，再一次」→ workflow 五組唯讀反查（Telegram 轉發、prompt 組裝、儲存、介面與測試、翻歷史）＋整理，主 agent 再抽查關鍵幾條（巴哈開串與記狀態的先後、10-17 11:09 公告兩次進入發送、三份 `PGVectorStore.from_params` 都沒有借出前檢查、插話沒傳被 @ 的 id、啟動補償每次 2 筆、Telegram 送失敗照樣推游標）。結果、收斂順序、AR3-Q1～Q5 寫在 `architecture-review-2026-10` 的「第三輪反查結果」；Telegram 過濾區塊「判決持久化」更正頻道 0 與啟動補償的說法，「還沒做」補兩項。過程中 Claude 說「照最小修改的原則，十張只挑一兩張」，被使用者糾正：「沿用現有架構、最小修改的原則沒有錯，但有重複輪子、分散各處的程式碼就要收成一個模組，我一直有講」→ 記憶 `feedback-minimal-change-architecture`、`reuse-first` 補上（最小修改管怎麼收，不管收不收），順序改成全部排進來；AGENTS.md 要不要補一句列為 AR3-Q5。SearXNG 穩定度測試已跑完（10-16 15:35 起，最後一輪 10-17 15:15），結果下一輪報、再定 W7。16:5x 使用者「AR3-Q1～Q5 全部修；先前幾輪不是都已經講過作法了，你列出來給我看」→ 五題照建議定案（AGENTS 開工第 3 條已補一句）；Claude 卻把先前幾輪的題目整張又當「等你答」問了一次，還把已 commit 上線的 /goal 12 項和 10-13 已結案的零星項也列進去 → 使用者「我明明就答過你還全部重新問一次、已經結案的為什麼也問」。原因：接續摘要後用交接檔的舊清單重建待決，沒把使用者「建議都很好、都依照你的建議」「commit」當成已答。更正：KN-Q5b、Q8～Q11、W7、W8a～e、W5、股價、天氣、讀全文、被 @ 長度上限全部記成定案（照講過的作法），/goal 12 項與 10-13 清單記成結案；X2 照建議做（刪除事件同步刪、既有 779 則備份後刪，刪之前仍要經使用者同意，因為是高風險資料）。記憶 `no-reasking` 補上這個模式。
- 2026-10-17 17:xx～18:xx（AR3-Q1 的三個小修，**已 commit `2e59d49`、`f982315`、`a0bd76c`（10-18）**；沒開新檔）：①巴哈 `_process_thread` 開串後馬上 `save_bahamut_thread`（state 含主文 msg_id、建立當下的 content_hash、空的續文清單），之後續文／補圖／留言格出錯，下一輪走增量更新不再開串；主文補圖改成失敗只記 WARNING（增量更新本來就不補圖，圖太大不該擋留言格與回覆）。②送出鎖收成 `services/relay/base_monitor.content_send_lock(content_type, content_id)`（模組層 dict、跨監看物件共用；巴哈原本的 `_thread_locks`／`_get_thread_lock` 刪掉改用它，key 不變）；公告、FB、IT 的輪詢函式在鎖內再查一次已送紀錄才送，`discord_bot` 那段「去重靠 StateDB，不會重送」的說明改正。③`LLMServiceSettings.pgvector_vector_store(table_name=, embed_dim=, hybrid_search=True)`：`PGVectorStore.from_params` 只剩這一份，帶 `create_engine_kwargs={"pool_pre_ping": True}`（容器內 SQLAlchemy 2.0.54 同步與非同步引擎都接受）；`context_retriever`、`member_profile_store`、`store_chat` 改呼叫它；守衛 `test_shared_conventions` 加規則「PGVectorStore.from_params 只准在 llm_settings」；AGENTS 共用元件表加兩列。測試：`test_bahamut_edit_pacing` 加 2 項（底線第 7 條）、`test_notify_relay` 加 1 項（推送與輪詢同時只送一份）、`test_chat_persist_retry` 加 1 項（帶借出前檢查）；6 個突變全紅（拿掉提早記下、補圖失敗照丟、鎖內不再查、沒有鎖、不帶 pool_pre_ping、有人又自己 from_params）；完整測試 1,643 項全過（容器內，96 秒）。獨立複查（workflow 三個角度＋反駁式驗證）：送出鎖與向量庫兩個角度沒有問題；巴哈那段抓到兩個真問題（都用假物件實跑證實）——①開串後留言格那步出錯，下一輪增量更新不會替主文補建留言格（第 3 步只在已有格時才開新格），留言還被記成已同步、從此靜默遺失；②主文超過 3,500 字時提早記下的空續文清單會讓下一輪把續文整串重發、舊的變孤兒。修法：續文發完先再存一次（帶 id 與連結後的 hash）；增量更新遇到「主文沒有任何留言格」就呼叫 `_send_post_comments` 補建（只補主文：正式 StateDB 唯讀查到 post 9099 一篇有 567 則回覆沒格、主文 0 篇沒格，替回覆補格會往舊串灌幾百則訊息）；`_send_continuations` 送到一半出錯改成先回已送出的 id（缺的下一輪補在串尾）。測試補強：主文帶留言與長內文，斷言第二輪有格、續文沒重發；新增「續文送到一半下一輪補齊」。commit 訊息草稿三份在 scratchpad `commit_q1.txt`，等使用者說 commit。
- 2026-10-17 17:3x～18:5x（插話那批，**已 commit `eebf984`…`17c7ef0`（10-18，共 6 個）**；新檔照 KN-Q11：`llm/ambient/ambient_search.py`、`settings/prompts/ambient_search_rules.txt`、`utils/daily_quota.py`＋`test/test_daily_quota.py`、`test/test_ambient_search.py`、`test/integration/it_ambient_search.py`；`settings/switches.json` 加 `ambient_search_mode` 說明與值 `dry_run`）：
  - **W6**：`search._search_news`——有日期的引擎（`news_engines`＝duckduckgo news）不限時間、結果照日期新到舊排、沒日期的接在後面；沒日期的引擎（`news_undated_engines`＝bing news）另一次請求帶自己的一週條件（`news_undated_time_range`），排在有日期的後面；一邊出錯不算整次失敗（meta.error 只在兩邊都錯時保留）。`tools._KINDS` 的 news 不帶 time_range；工具說明與 `askai_web_rules.txt` 第 3 條改成「照日期新到舊排」；工具說明加「網路流行語、梗的意思」。reuters 拿掉（升級後 401）。
  - **W7**：`AskAIWebSettings.default_engines`＝`yahoo,duckduckgo`（測試釘住「沒有 bing」）。
  - **共用迴圈**：`generate_reply` 加 `tool_nudge`（查滿的提醒文字，預設 `TOOL_ROUNDS_NUDGE`＝/askai 那句）、`tools_plain_fallback`（False＝第一次失敗照實回報、提醒後仍要工具就回空字串）、`today`（放 user 段最前面「（今天是 YYYY-MM-DD（星期X））」，system 段不動）；/askai、日記、印象審核都用預設、行為不變。說明拿掉「/askai 專用」。
  - **每日額度**：`utils.daily_quota.DailyQuota`（換日歸零、先扣再做、上限可每次再給）；看圖補字典改用；守衛 `_find_hand_rolled_daily_quotas` 擋 `_quota = ["", 0]` 這種寫法。
  - **名字檢查**：`member_names.query_names_member(query, parts)`：識別碼（`#4 碼以上`、`<@…>`／`<#…>`、8 位以上數字、email）回「識別碼」；名字用 `names_member(allow_longer=True)`，純英數短於 3 字的片段不算。
  - **插話上網查第一版（記錄模式）**：`ambient_search.prepare(question, now=, names=, trace_id=)`——開關 off 或今天額度用完回 None；否則連 search-mcp 列工具（最多等 `intel_prepare_seconds`＝5 秒，逾時只剩網路）＋`WebSearchTools(instructions="")`，組成 `AmbientSearchTools`：宣告＝情報的 search（不宣告 fetch）＋web_search，規則每次 `hot_files` 讀 `ambient_search_rules.txt`；`execute` 依序：不認得的工具／參數錯 → 錯誤；同一次插話第二個呼叫 → 「只能查一次」；額度 `_QUOTA.take` 不到 → 「額度用完」；web_search 的查詢字過名字檢查（名單 `name_parts_for(guild, participant_ids)`＝全伺服器 Discord 名字＋在場的人自介、印象暱稱，第一次要用才查）→ 擋下回錯誤；dry_run → 不呼叫內層、回 `{"results": [], "note": RECORD_MODE_NOTE}`；每次呼叫記一行 `ambient 查詢 trace= mode= tool= query= 判定= 耗時=`。`NUDGE` 是系統口吻、明講可以 [PASS]。開關 `ambient_search_mode: Literal["off","dry_run"]`（`on` 第二版才加）；設定 `AmbientSearchSettings`（daily_limit 30、max_tool_rounds 1、rules_path、intel_prepare_seconds 5）。
  - **接線**（`ambient_reply`）：`_gather_inputs` 最後 `_prepare_search_tools`（測試可換）；`_Inputs` 加 `search_tools`、`today`；`_generate` 傳 `today`、`tool_runner`、`max_tool_rounds=1`、`tool_nudge=NUDGE`、`tools_plain_fallback=False`、`max_tokens=directed_max_tokens（3000）if directed`；輸出含 `<tool_call>` 當 pass；「ambient 生成」摘要加 `search= tools=`。prompt 第 36 行改「有查詢工具時可以先查一次，查完仍沒把握才 [PASS]」、第 87 行「如果最後有」→「如果有」。
  - **被 @ 長度上限**：`AmbientChatSettings.directed_max_tokens=3000`——180 秒逾時約能寫 3,400 token，上限要比它低才有機會關掉思考重答（重答約多 25 秒）；撞到仍沒答案時 `generate_reply` 回 `error_kind="length"`，插話照 error 略過（「想太久」那句不會貼進群）。自發不設上限。
  - **B2**：`_mentioned_user_ids(message)`（原文 `<@id>`＋`message.mentions`，去掉 bot）傳進 `_build_persona_context`→`retrieve_rag_context_sync(mentioned_user_ids=…)`（快取 key 改成（頻道, 被 @ 的人））與 `_resolve_callback_target`（不再從換過名字的 query 抽）。
  - **B6**：`_deliver` 超過 2000 字只送 `split_message` 的第一段並記 WARNING；`reply` 兩條路都帶 `allowed_mentions=none`；原訊息被刪（50035）與其他送出失敗分開記。
  - 測試：`test_web_search` +4、`test_web_tools` 改 1、`test_generate_reply_tools` +4、`test_prompt_builder` +1、`test_daily_quota` 新 4、`test_emoji_autofill` 改 2、`test_member_names` +4、`test_ambient_search` 新 13、`test_ambient_pass_flow` +10（含 `MentionLookupTests`）、`test_switches` +1、`test_bahamut_edit_pacing` 補強 2；28 個突變全紅（scratchpad `mut_batch2.sh`）；完整測試 1,696 項全過（容器內，152 秒）。**真模型驗收（`it_ambient_search`，19:xx 在正式容器跑、記錄模式不出網）4 個情境 0 個問題**：新梗（「這波是標準的何意味」）→ 叫 web_search「何意味 梗 意思」，拿到記錄模式的說明後輸出 [PASS]（191 秒，含上線第一次整段重讀）；閒聊（抽卡歪了）→ 不查，#4 接一句（98 秒）；被 @ 問「3.7 版本的新角色」→ 叫情報 search「3.7 版本 新角色」，回「手上還沒看到確切的公告，不好憑空猜」（13 秒）；帶圖＋工具 → 後端接受、沒叫工具、照圖回（27 秒）。四個都沒有網址、沒有工具呼叫漏成文字、自發開口有寫 #N。
  - **獨立複查（workflow 三個角度＋反駁式驗證，14 個 agent）**：隱私角度確認記錄模式沒有任何路徑把查詢字送出主機（只對本機 search-mcp 列工具）、額度不會重複扣、log 只記查詢字不記 prompt。確認為真並已修的 4 條：①被 @ 時答案才開頭就被 3000 上限切到（思考用掉大半）——`chat_raw` 會接 /askai 用的「（回答到長度上限被截斷）」註記，半句話加註記會貼進群（估每次被 @ 約 0.2～0.5%，數週一次）→ `generate_reply` 收到結尾帶 `TRUNCATED_NOTE` 的回答且思考開著、有上限時，關掉思考再答一次（和「什麼都沒寫出來」同一個 `without_thinking`）；帶工具的路徑也在 finish_reason=length 時接註記（原本只有不帶工具的會接）；插話收到仍帶註記的回答當 pass、不送。②名字檢查只看查詢字前 200 字，內層工具卻拿整段 → 檢查改看整段，200 字只用在 log 與紀錄。③名單只有近期發言的人的自介、印象暱稱，被 @ 但沒發言的人（人物卡會把他的暱稱送進 prompt，最容易被拿去查）不在 → 名單併入被 @ 的人。④新聞「照日期排」是在 SearXNG 相關度前 5 筆裡排（主機實測 duckduckgo news「鳴潮 改版」最新兩筆排第 7、8，模型拿到的 5 筆有 3 筆是 2024 年的）→ 有日期的那次抓 `top_k × 4` 再排再截；meta 另記 `dated` 的錯誤與筆數。小修：切段用 `DISCORD_MESSAGE_LIMIT - 10` 留餘裕（暴雷跨切點時補 `||` 會到 2002 字、整則被拒）；開關 off 的說明改成「提示詞只多了 user 段開頭的今天日期」；閘門測試補斷言「擋下的不去準備查詢工具」；工具的 kind 說明「近期新聞時事」→「新聞時事」。判定不算問題、不改的：識別碼規則會擋無分隔的 8 位日期與「#年份」（寧可多擋）；名字是常見詞的人會擋整類查詢、log 沒記對到哪一段（第二版再看）；新聞一邊逾時的不完整結果會進 5 分鐘快取（實際 456 次請求 0 次 HTTP 層失敗，影響有界）。修正後對應測試 +7（截斷重答 4、名字檢查整段 1、名單含被 @ 1、新聞多抓再排 1）、7 個突變全紅（切段留餘裕那個第一次沒抓到：測試素材的暴雷沒有跨過第 2000 字，改成跨切點後會紅）；**完整測試 1,716 項全過（容器內，119 秒）**。整批到 18:5x 收工；**10-18 03:4x 使用者「commit」→ 11 個 commit（`2e59d49`～`1394523`：三個小修 3 個、W6＋W7、共用迴圈、每日額度、名字檢查、插話查詢、被 @ 修正、字典 chore、docs），同檔分屬兩個 commit 的用中間版本直接放進 index、工作目錄沒動；未推送**。**10-18 02:5x 主機意外重啟，六個容器全部自己起來，這批未 commit 的程式因此上線了**（src 是即時掛載；啟動 gate 85 項全過、bot 02:55 登入、Telegram 啟動補償照舊 2 筆、通知伺服器與各監看正常、插話查詢開關是 dry_run）。telegram-scraper 多重啟兩次是 pgvector 還在做當機復原（WAL redo）、連線被拒，第三次才起來，沒有資料問題；pgvector 復原正常。02:59:52 系統套件更新把 docker 服務也重啟（systemd「marked units」），六個容器 03:00 再起一次，bot 03:02 回來、音樂 03:02:33 重新加入語音並續播（使用者看到的「音樂沒啟動」是這兩分半的空窗）。**上線後第一次核對（03:3x）**：插話的「ambient 生成」摘要有 `search=dry_run tools=2`（情報 search＋web_search 都宣告到、search-mcp 連得上），prompt 檔有「（今天是 2026-10-18（星期日））」與【插話時的查詢規則】；還沒有任何 `ambient 查詢`（模型還沒想查）；03:21 那次自發插話逾時 180 秒（上線後第一次要整段重讀約 12k token，加上想太久；屬「插話逾時變多」那條待查，不是這批的錯誤）；其他功能沒有 ERROR。整批上線後要盯的：一週後看 `ambient 查詢`；插話逾時比例。commit 訊息草稿（第 4～9 個）在 scratchpad `commit_q1.txt`。
- 2026-10-16 18:xx（/askai 想太久的修正，**已 commit `f45d029`（字典 `0ee90e6`）、已推送（10-17 查遠端 `dcbot/master` 到 `bff1eb9`）；要重啟 discord-bot 才生效**；`doc/` 依使用者不進版控）：使用者「改」並問之前的上限是多少 → 之前沒有上限，只靠 300 秒逾時（逾時又重試 2 次，最壞一題 15 分鐘，10-12 評估時發生過）；10-09 起 /askai 38 次模型呼叫中位寫 229 token、P90 1,598、P95 2,344，撞到 4096 的只有今天這兩次，所以上限保留、改撞到後的處理。做了下面 17:4x 那筆的 ①～④（⑤ 思考預算另查）：`llm_service.py`——`chat_with_tools` 沒內容也沒工具呼叫且 finish_reason=length 時回 `kind="length"`（不當後端異常、不抓快照）；`_answer_with_tools` 第一次呼叫是 length 就照實往外丟、不再用同樣的思考不帶工具重跑；`generate_reply` 遇到 length：有給 `max_tokens`、而且這次開著思考，就關掉思考、不帶工具、用已經查到的 messages（工具輪的 progress）再答一次，仍沒答案才回 `THOUGHT_TOO_LONG_REPLY`「⚠️ 這題想太久，沒整理出答案。換個問法再問一次看看。」；length 不再觸發「圖退成 PNG 重跑」；`_chat_completion_checked` 撞到上限時把 `reasoning_content` 最後 1,500 字記進 llm_anomaly.log。沒給上限的呼叫端（插話、日記）行為不變。測試：`test_generate_reply_tools` 加 6 項（取代原本斷言「拆小」那項）、`test_llm_snapshot` 加 2 項；8 個突變全紅（第一版漏了「想太久也退成 PNG 重跑」，補了帶 GIF 的測試）；完整測試 1,639 項全過（容器內）。重啟前上線的仍是舊行為。使用者問上限要不要改 8192（中文字多）→ 說明 8192 在現行 300 秒逾時下到不了（約 20 token／秒，寫到約 5,000 token 就被逾時切斷，而逾時回「無法連線」、不走不思考重答），撞上限的原因是思考停不下來不是中文回答長 → 使用者「好吧」，維持 4096。使用者問「剛剛那是特例嗎」→ /askai 是（10-09 起 38 次呼叫只有這題撞到）；但「想太久」本身不罕見：插話（同一顆模型、沒有字數上限、每次 180 秒逾時）6 月底以來 14,763 次生成逾時 110 次（約 0.75%，平常約一天 1 次），今天 6 次（129 次裡；2 次在聊那串日文拼音），其中 3 次是被 @ 或被回覆、對方沒收到回覆；6 月底以來被 @ 卻逾時共 12 次（1,963 次裡）。**定案（10-17 使用者：先前講過的作法照做）**：被 @ 的插話也比照——給一個字數上限、撞到就關掉思考重答，讓點名的人一定收到回覆，和插話上網查那批一起上；自發插話逾時照舊略過。
- 2026-10-16 17:4x（/askai「回答太長寫不完」查因，**未動 code**）：群友 /askai「翻譯一下: super母洽估洽尼西TE阿GA他意」（日文發音用中文字拼寫，推測是「めちゃくちゃにしてあげたい」）回「⚠️ 這題回答太長寫不完」。log：17:31:23 開始；第 1 次（帶工具）prompt 10,830、cached 0、讀 48.7 秒，輸出 4,096 token 全是思考、沒有內容 → 撞到今天上線的 `answer_max_tokens`＝4096（/goal 第二輪 ⑦，思考也算在內）→ 被當成「帶工具的第一次呼叫失敗」→ 改用不帶工具再跑一次，同樣 4,096 全是思考 → 17:39:35 回錯誤，前後 8 分鐘、佔顯示卡兩整輪。同一句話 17:19 有人 @ 插話時也是 180 秒逾時沒講完。所以根因是模型對這類「拼音式外語」題會一直想下去（思考內容沒記進任何 log，看不到卡在哪），4096 上限把它變成沒有答案，退路又讓同樣的失敗多跑一次。**待決（選項＋建議）**：①撞到上限又沒內容時，不再走「不帶工具重跑」（同樣的思考、同樣的上限，必定再失敗）——建議做；②改成用「不思考」再答一次（多一次讀 prompt 約 45 秒＋短回答，給得出答案）——建議做；③錯誤訊息從「請拆小一點」改成「這題想太久沒想出答案」（短題被叫拆小會誤導）——建議做；④撞到上限時把思考的最後一段記進 debug 檔，才看得到卡在哪——建議做；⑤另外限制思考長度（後端是否支援每次請求的思考預算要先查）或調低思考強度（會影響所有回答深度）——建議先查支援度、不急。
- 2026-10-16 14:1x～15:4x（時事／新梗背景知識與 SearXNG 討論，**未動 code**；15:35 起在主機跑 24 小時的 SearXNG 穩定度測試，見 `mcp-search-tools` 待做 7）：使用者問①群裡聊新聞、新梗時能不能在背景更新知識、讓插話有參與感 ②SearXNG 不夠強、有沒有更好的開源或社群常用工具；之後貼另一個 AI 的建議，問有沒有讓 SearXNG 用上多數引擎的外掛或方法、`/stats/errors` 怎麼看。開兩組 workflow 唯讀盤點與調查（程式現況、插話 prompt 與快取、既有資料、交接檔定案；外部工具與來源；解封鎖做法）。15:04 使用者把 SearXNG 更新到 2026.10.16，Claude 前後對照實測。結論與待決 W6～W9 寫在 `mcp-search-tools` 待做 7「網路搜尋變弱的根因、SearXNG 更新與實測」。背景知識那題：盤點已完成（插話 prompt 只有 system 段吃快取，筆記該放 user 段新的不可信區塊；可照抄 emoji_autofill 與 ambient_memory 的背景流程；現有資料幾乎只有鳴潮、沒有新聞與梗的來源；插話 prompt 沒有日期），外部來源與做法的調查還在跑，下一輪再談。附帶：插話人設現名「琇紫」（文件裡的「柔喵」是舊稱）；現況摘要「待決定：插話被 @ 時要不要也查」已過時，改成 10-09 定案。過程中 Claude 一度說 `/stats/errors` 快照沒被實測影響，實際上實測 agent 14:26 已跑過一輪，已當場更正。
- 2026-10-16 05:xx～（/goal 第二輪：音樂重連修正、補寫兩個 bug、零散項、M6～M8、M7 工具鏈、M9 只寫設計；**不 commit、不開分支**，每塊做完封一張 git tree 快照，最後依序變成獨立 commit，做法寫在本機的 `doc/snapshot_commits.md`（使用者決定文件不進版控，只放本機）；快照清單與 commit 訊息草稿在 scratchpad `snapshots/manifest.txt`）：
  已封：00 補寫批次原樣（別人寫好、1,560 測試全過）；01 音樂重連（`player.py`：斷線後等 discord.py 自己重連最多 35 秒、等不到在同一條連線 `connect()`、連線從登記表消失才建新的；被打斷的歌記已播秒數、重連後 ffmpeg `-ss` 續播、不重複記入已播、連續 3 次放棄；刪無效的 `guild._voice_client = None`；新測試 `test_music_reconnect.py` 8 項、7 個突變全紅、完整 1,568 全過）；02 播放迴圈連不上語音時睡 5 秒再試（原本空轉吃滿 event loop）；03 測試模式的 log 只寫 test_run.log、不印到畫面（gate 的畫面就是 docker logs）；04 聊天向量庫一則一段（`store_chat` 改 `insert_nodes` 一個 TextNode，不經切段器；長訊息、變長的編輯不再因第二段撞唯一索引而漏掉）；05 raw 備份寫入遇連線層錯誤換一條連線重試一次（壞連線不放回池子）。06 LLM runtime 設定改走熱讀檔快取（`load_llm_runtime_config` 接 `hot_files`，11 處呼叫不再每次重讀重驗、壞檔沿用上次；LLMService 改呼叫它；AGENTS 表更新）；07 四份手寫排程迴圈搬到 `run_due_loop`／`periodic`（週期提醒 tick 回下一則時刻；點名 14:00 後一小時內做、錯過等明天；每日維護記「今天跑過」避免啟動補跑與排程重跑；日記排定時刻後 10 分鐘內寫一篇、不補寫不重寫；守衛例外清單清空）。08 爬蟲→bot 通知加共用密鑰（環境變數 `NOTIFY_SHARED_SECRET`，bot 驗 `X-Notify-Secret`、爬蟲帶 header；沒設維持現狀＋啟動警告一次；compose 給 scraper 帶變數、`.env.template` 加說明）；09 對話請求逾時不重試（連線錯誤與 5xx 照舊）＋ /askai 回答長度上限 `answer_max_tokens`＝4096，從 `generate_reply` 一路帶到每一輪模型呼叫。10 錯誤邊界守衛 `test_error_boundaries.py`：`llm/`、`services/` 技術與服務層接所有例外的地方以檔為單位記基準（21 檔 80 處），只准減不准增；真的是邊界在那一行註 `# 邊界：原因`；規則寫進 AGENTS。11 M6 縮小版（10-16 下午改版）：共用的頻道正規化與媒體時限只留一份在 `src/shared/telegram.py`（基礎層，只依賴標準庫），bot 直接 import；telegram-scraper 容器由 compose 把 `src/shared` 唯讀掛到 `/opt/pylib/shared`、`PYTHONPATH=/opt/pylib`，爬蟲只多看到這一小包；分層守衛的跨容器例外清空。**telegram-scraper 要 `docker compose up -d telegram-scraper` 才拿得到掛載；在那之前它若自己重啟會 import 不到 shared**。爬蟲端套件改名（scraper 的 services／utils 撞名）另一輪。12 M7：釘版本**不做**（使用者決定版本先不綁，三個容器都恢復原樣）；啟動 gate 改跑 `test/gate.py`（12 組守衛／import／設定載入，約 20 秒；完整測試交 `make test` 與 CI）、`pyproject.toml`（ruff 只開必錯規則、pyright basic）、`requirements-dev.txt`、`Makefile`（主機沒裝 make，指令可直接照抄）、`.gitlab-ci.yml` 草稿（沒跑過）。靠真實時間的 14 個測試改寫沒做；釘版本依使用者決定不做（原本 M7a 的一部分）。13 M9 只寫設計：本機 `doc/llm_worker_design.md`（不進版控；worker 容器、工作用 Postgres 交接、outbox 讓 bot 代貼、成員與表情快照、五步搬遷順序、四個待決）。
  **狀態（10-16 中午）**：13 張快照全部封好、每張都用容器 /tmp 的複本跑完整測試全過（最後一張 1617 項）；工作目錄＝最後一張快照＋排除的檔（兩個字典、交接檔、`doc/`、`it_comfyui_image.py`）。**13 張快照全部已 commit（使用者分批說 commit）：`ecf2bae` 00、`43f80c1` 01、`23e204b` 02、`f90d286` 03、`2942aa3` 04、`9275866` 05、`eb653a7` 06（loader 簡化併入）、`0511e40` 07、`9243309` 08（含使用者要求併入的守衛：爬蟲每個打 /notify 的 POST 都要帶密鑰 header，以及 .env.template 的註解）、`68713d1` 09（併入兩點修正：只有等回應的逾時不重試、撞到長度上限記 log＋結尾說明＋空內容回「請拆小」）、`ee6cc0d` 10、`64f6111` 11（**改成共用套件**：`src/shared/telegram.py` 一份，bot 經 src 掛載看得到，compose 把 `src/shared` 唯讀掛進 telegram-scraper 的 `/opt/pylib` 並設 PYTHONPATH；爬蟲的 tg_config、media_download 改 import 它；原本的兩份雙胞胎與守衛刪掉——使用者不要把整個 src 掛給爬蟲，所以不用「以 src 為根」）、`1822cab` 12（使用者決定**整個專案都不綁版本**：三份 requirements、dockerfile 恢復原樣、新 constraints 刪掉、CI 草稿不帶 constraints；bot 原有的 constraints.txt 只是紀錄，已更新成執行中容器的版本）；字典與開關 `4ff1efb`（10-16 14:17 使用者「切」，補寫開關 dry_run→on；14:14 dry_run 379 則、14:29 第一輪排進 20 則）、文件另外 commit。`.env` 已放一把隨機密鑰（使用者決定留著用）。沒重啟、沒推送**。
  **commit 步驟（使用者說 commit 後）**：跑 scratchpad `snapshots/snap_commit.sh`（依序 13 個 commit，訊息在各 `.msg`），再 `chore(settings)` 兩個字典、`docs` 交接檔＋`doc/`；`it_comfyui_image.py` 不進。快照是 git tree 物件（不是 commit、不是分支），各張的 patch 備份在同一個資料夾。
  **重啟兩批**：第一批 `docker compose up -d discord-bot`（compose 的 gate 指令改了，`restart` 不會吃到；避開 04:00～07:30）；生效：音樂重連、補寫（dry_run）、停機收尾、長訊息一則一段、raw 重試、設定熱讀、四份迴圈、/askai 逾時與長度上限、notify 密鑰（沒設就只警告）。第二批 `docker compose up -d scraper telegram-scraper`（scraper 帶 NOTIFY_SHARED_SECRET、telegram-scraper 掛 shared；順序先 scraper 再 discord-bot）；重建映像檔（`--build`）才會用到釘好的版本，不急。
  **照建議先做的決定（使用者 10-16 分批說 commit 就是確認；10-17 已結案，不再問）**：①音樂等 35 秒／同一條連線重連／斷點續播（連續 3 次放棄）；②長訊息一則一段（embedding 上下文 8192 放得下）；③raw 寫入連線錯誤重試一次；④`load_llm_runtime_config` 改熱讀檔、壞檔沿用上次；⑤點名只在 14:00 後一小時內做、日記排定時刻後 10 分鐘內寫（重啟錯過不補）；⑥notify 密鑰沒設不擋只警告；⑦對話逾時不重試＋/askai 上限 4096 token；⑧錯誤邊界只管 llm／services 的技術與服務層（功能層不管）；⑨M6 做縮小版（兩份雙胞胎＋守衛），爬蟲套件改名與三容器以 src 為根留到另一輪；⑩gate 只跑 12 組守衛，完整測試交 make test／CI；⑪yt-dlp 不釘版；⑫M9 只寫設計、M10 不做。
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
| AI 偶爾插話 / 閒聊（功能二） | **已上線**（含 2026-08-09 自然插話重構）；10-02 看得懂貼圖、X 貼文、別的伺服器的表情（`673a965`）、AI 看圖補表情／貼圖字典（`cd0baf7`）、10-07 被罵的應對（`0f71b6d`）都已上線並 commit；待決 AM-Q2（放寬 style_refs 門檻）、AM-Q3（接話算正向）、AM-Q6h（偏掉的描述）、RB-Q9（道歉消氣）、AL-Q1～Q5（自主學習，暫停）、KN 插話判斷時自己上網查（KN-Q1～Q11 全部定案；**第一版記錄模式 10-17 做好、10-18 02:5x 隨主機重啟上線、已 commit `bfec06f`**，開關是 dry_run、跑一週看紀錄再決定全開；同批：被 @ 的輸出上限＋關思考重答、B2 被 @ 的人進人物卡檢索、B6 長回覆只送第一段與不 @ 人）；待做 C-4 整併／淡忘、觀測面板、鉤子權重迴歸 | 85% | [AI 偶爾插話](#ai-偶爾插話--閒聊功能二已上線c-4-待做) |
| Persona Agent M7（精簡版發布） | **已上線**；10-01 隱私歸因與名字對照上線、10-02 手動修正四條舊錯誤；精簡版 10-02～10-13 連續 12 晚 failed=0；**備援 ③ 與兩個手動萃取指令 10-13 已拆（`7a369b6`，重啟後生效）**，04:00 維護變四步；不補手動入口、「精簡版」名稱維持 | 92% | [Persona Agent M7](#persona-agent-m7精簡版發布2026-09-28-已上線精簡版連續-12-晚穩定待刪備援萃取) |
| ComfyUI 產圖 + GPU 資源仲裁 | **規劃定案（2026-09-02）**；租約鎖與卸載 helper 已完成（`e13343d`），鎖有漏洞待修；落地細節討論中 | 25% | [ComfyUI 產圖](#comfyui-產圖--gpu-資源仲裁2026-09-02-規劃定案未開工) |
| AI 私聊頻道 + 三層記憶（功能一·姊妹案） | 規劃完成（含道德守門）；人設 prompt 已就位；**本輪暫放旁邊** | 10% | [AI 私聊頻道](#ai-私聊頻道--三層記憶機制規劃中) |
| 使用者指令記憶 (/remember) | 規劃中（與 AI 私聊頻道互補） | 5% | [/remember 規劃](#使用者指令記憶-remember-未來工作) |
| Reaction 統計 / 社群互動玩法 | 資料收集已完成（`raw_message_store`）；玩法、/askai 整合、人格加權都還沒做 | 15% | [Reaction 統計](#reaction-統計與社群互動玩法規劃資料收集已完成) |
| 點歌機器人（Music Bot） | 已上線運作；10-15 查出語音斷線後的自我重連競態，**10-16 修正已 commit（`43f80c1`、`23e204b`）並上線**（discord-bot 10-16 14:08 重啟）；四題的做法在 /goal 第二輪照建議先做、待使用者最後確認；**10-19 發現斷點續播會卡住重試（10-16～10-18 卡了約 35 小時），未修**，見區塊內 | 85% | [點歌機器人](#點歌機器人專區) |
| Telegram relay 可靠性 | 補掃、媒體防雷、相簿漏圖修正都已上線並驗證（9/29 起合併與補圖符合設計） | 98% | [Telegram 補掃](#telegram-漏收補掃與相簿漏圖已上線) |
| 程式結構整理 | **主要整理已完成並上線**（`llm/` 與 `services/` 分群、點名去除反向依賴）；剩 P2 拆檔（未決）、P3 `discord_bot.py` 瘦身（暫停）、N3（延後）、命名慣例未寫進 AGENTS.md | 90% | [程式結構整理](#程式結構整理2026-09-29-起主要整理已完成剩-p2p3n3) |
| 架構審視與滾動修正（/goal） | 11 項發現；**M1～M5 上線**；**第二輪（10-16）13 張快照已 commit、已重啟上線（discord-bot、scraper、telegram-scraper 10-16 14:0x 重啟；已推送到 `e2662c2`）**：音樂重連、補寫批次與兩個既有 bug、設定熱讀、四份排程迴圈搬 `run_due_loop`、notify 密鑰、/askai 逾時不重試＋長度上限、M8 錯誤邊界守衛（21 檔 80 處基準）、M6 縮小版（bot 不再 import 爬蟲）、M7 釘版本／gate 瘦身／ruff・pyright 設定／Makefile／CI 草稿、M9 設計寫在本機的 `doc/llm_worker_design.md`（不進版控）；M10 不做。做法寫在本機的 `doc/snapshot_commits.md`（使用者決定文件不進版控，只放本機），待確認的 12 個決定與重啟兩批列在最後盤點紀錄 10-16 那筆；**第三輪（10-17，同一件事寫好幾份的收斂）反查完成**：真的出過事的是巴哈重開串、公告推送與輪詢撞車重貼、連線失效疊上先刪再寫丟偏好；收斂順序與 AR3-Q1～Q5 待答（見區塊「第三輪反查結果」） | 85% | [架構審視](#架構審視與滾動修正2026-10-12-起goal-進行中進度見區塊內進度) |
| 情報搜尋（MCP）：公告、FB、PTT、巴哈 | **P1～P4 已 commit（10-08，已推送）**：全文索引＋向量（RRF）＋reranker、42 題評估（原句 Hit@5 21%→67%、關鍵字 60%→81%）；**10-12 Agent 評估（已 commit，未推送）**：正式模型自己寫的查詢 71%、算上換字再查 79%、回答初判 31／42，三題未定案見區塊待做第 9 項；**R12 已上線並 commit（10-08，已推送）**：常駐服務 `search-mcp`、索引移到 `search_data/`（10-22 再搬到 `cache/search-mcp/`）、每日補向量、重排讀原句並已開啟；**延遲改進與 /askai 接線已 commit（10-09，已推送、已上線）**：背景同步、冷快取讀取量 52 MB → 4.5 MB、/askai 由模型決定查不查；插話上網查改由 ambient-chat 區塊 KN 系列處理（10-09「被 @ 時不查」已被 10-16 KN-Q4 取代）；**10-16 SearXNG 更新到 2026.10.16 並實測**：yahoo 恢復且最準、duckduckgo 部分恢復、bing 變得不穩（只查第一個字、亂回），bot 預設引擎待換（W6～W9，見區塊待做第 7 項） | 95% | [情報搜尋（MCP）](#情報搜尋mcp官網公告官方-fbptt巴哈p1p4-已完成常駐服務已上線) |
| 聊天檢索（RAG）品質：折疊、品質閘、/askai 重排、重算向量、HNSW | **10-26 已 commit（`c96ecc6`～`8c85e80` 六個，未推送）、待重啟**；重算向量 10-27 00:04 完成（影子欄 `embedding_v2`）；**HNSW 10-27 06:38 建好**（序列 19 分鐘、2,211 MB、有效；全庫 top-100 熱 2 ms／冷 11 秒，之前全表掃熱 4 秒／冷 100～540 秒）；建好後發現 `search_chat` 的 doc_type 篩選讓規劃器不走索引 → 已修（快照 09 `dcbc2f3f`，未 commit）；60 題比對 A 進步、B／D 持平、C 整句問法 20→14（查詢端的事，RG-Q16 定案 A：聊天搜尋工具兩種模式，排在切換後）。**切換 10-27 09:30 完成**（`embedding`＝新向量＋HNSW、`embedding_v1`＝舊向量留回滾）；bot 09:33 重啟、補尾巴 10:27 完成（378 列、`--min-id` 快照 10）、**遷移結束**；索引放不進 8 GB 的快取 → **換 512 維 halfvec 表達式索引**（profile 開關 `chat_vector_index`，快照 11；371 MB、60 題每題 120 ms、Hit 38/47/50 對精確 38/48/51）；待做：插話回憶距離門檻重校、`search_chat` 回傳加 channel_id；待決：跨作者去重（RG-Q11）、搬 `LemonadeReranker`（RG-Q15）、勾 30 題（RG-Q7）；說明文件在 Claude Doc | 85% | [聊天檢索優化](#聊天檢索rag優化重複折疊品質閘askai-重排2026-10-26-做好並-commit重算向量hnsw切換-10-27-完成聊天搜尋工具待做)；**10-27 下午：插話距離門檻量完不改、評估集進版控（`llm/retrievers/eval`）、/askai 聊天搜尋工具做好（開關已 on、待重啟與真模型驗收）；pg_trgm 索引待決（RG-Q21）** |
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
affects: services/search、llm/mcp_server.py、.mcp.json、docker-compose（search-mcp、run/gpu_lock）、cache/search-mcp/、pgvector data_search_chunks、Lemonade（embedding、reranker）、/askai（llm/retrievers/intel、LLMService.generate_reply 的工具輪）、scraper/db/models.py（四個 updated_at 索引）
-->

> 2026-09-29～10-08 每一輪的討論與查證（R2～R12）原文在 `TODO-completed.md`「MCP／搜尋工具化：討論與實作紀錄」。本區只放現況、定案、數字與待辦；評估紀錄（原 `eval/RESULTS.md`）與用語（原根目錄 `CONTEXT.md`）也併在這裡。

**現況（2026-10-09）**
- 用途：讓 LLM 自己決定要不要查、查什麼；來源是官網公告、官方 FB、PTT、巴哈（Telegram 內鬼頻道、依 ID 查人不納入）。MCP server 給這台的 Claude Code 與 bot 共用；bot 當 MCP 客戶端（`llm.retrievers.intel`）連 search-mcp，不直接 import `services.search`（10-09 改定案，理由見待做第 7 項）。
- **/askai 已接上（10-09，已 commit、已推送、10-09 重啟後已上線）**：開關 `askai_intel_search_mode`（`switches.json` 已設 `on`）；架構、定案、實測、留給使用者的題目見待做第 7 項。交付文件（架構圖、設計決定、數字、上線步驟、面試概念、優化排序）：https://claude.ai/code/artifact/11a03b1e-558a-4ac5-8253-71c35e8b9d57
- 已 commit、已推送：`dd89c58` refactor（共用網址、RRF、同步 GPU 閘門、側行程 log）、`c842b9b` feat(search)、`9b4ec88` feat(llm)（逐筆 LLM 用量 log）。完整測試 1,248 項全過，新測試都做過突變驗證。
- **R12 已部署（10-08 18:50）、已 commit（`c96cc80`、`ca5b837`，已推送）**：MCP 是常駐的 compose 服務 `search-mcp`（HTTP，`127.0.0.1:8765`）、索引在 repo 根目錄 `search_data/`（舊位置已刪；10-22 搬到 `cache/search-mcp/`，容器內仍是 `/search_data`）、每天 03:00 補算新文章向量、重排讀原句。完整測試 1,263 項全過、19 個突變全抓到。
- 運作中：`settings/switches.json` 的 `search_vector_mode: on`、`search_rerank_mode: on`（10-08 使用者同意打開）。
- 索引：11.2 萬份文件（公告 543、FB 874、PTT 5.5k、巴哈 10.5 萬樓）；向量：2026 年起的 1.8 萬段（巴哈只做攻略、心得、情報、問題四類討論串）。

**架構**
- `llm/mcp_server.py`：MCP 協定層，只有 `search(query, sources?, since, until, limit, question?)` 與 `fetch(id, page)` 兩個工具；參數錯把原因原文回給模型（`ToolError`）。`--http` 是常駐模式（stateless Streamable HTTP、聽 0.0.0.0:8765、Host 白名單 `127.0.0.1`／`localhost`／`search-mcp`，別的 Host 回 421），並在背景開每日維護；不帶參數是 stdio（備用）。
- compose 服務 `search-mcp`：沿用 bot 的 build（兩邊引用同一個錨點 `x-main-build`，不改 Dockerfile）、`restart: always`、不跑啟動測試（discord-bot 已經跑同一份程式的）；只帶 `LLM_BASE_URL`、`LLM_TIMEOUT`、`PGVECTOR_*`、`LOG_LEVEL`、`TZ`、`LEMONADE_GPU_LOCK_PATH`（沒有 Discord token、Telegram 憑證）；掛 `./src`、`./logs`、`./cache/search-mcp`→`/search_data`、`./run/gpu_lock`→`/gpu_lock`；`ports: 127.0.0.1:8765:8765`＋`expose: 8765`。`.mcp.json` 改成 `{"type": "http", "url": "http://127.0.0.1:8765/mcp"}`。
- `services/search/background.py`（10-09 由 `nightly.py` 改名）：每 50 秒背景同步一次（失敗退避、同樣錯誤只完整記一次）；每天 03:00～04:00 之間做一次「同步索引＋補算向量」（`embed.embed_pending`，向量開關關著只同步）；04:00 之後才啟動不補做、等明天；同一天不重做、出錯也不在同一時段重試；排程走 `utils.due_loop.run_due_loop`，在自己的執行緒與 event loop 上跑。
- GPU 鎖檔跨容器：各容器的 `/tmp` 是分開的，所以 discord-bot 與 search-mcp 都掛 `./run/gpu_lock`（compose 用錨點共用同一個定義）並設 `LEMONADE_GPU_LOCK_PATH=/gpu_lock/lemonade_gpu.lock`；單元測試由 `test/__init__.py` 強制換成暫存檔（不能 `setdefault`，容器的環境變數已經有值）。
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

**常用指令**（`docker exec search-mcp …`；`AGENTS.md` 的 Docker 例外允許 agent 直接執行。discord-bot 沒掛 `/search_data`，在那裡跑會失敗）
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
- compose 的 bind 掛載不改 named volume（10-08 使用者問）：`./src`（即時改程式）、`./logs`（主機要看）、`cache/search-mcp`（原 `search_data`；主機要能刪除重建）都需要主機路徑；`run/gpu_lock`（原 `gpu_lock`）改 named volume 的話資料夾歸 root、容器裡的 appuser 建不了鎖檔，只會記警告然後各排各的隊。重複只有三個掛載，YAML 合併不了清單，只把 `build:` 抽成 `x-main-build` 錨點（兩個服務的映像檔不能分岔）。
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
   - **留給使用者**：(1) ~~插話被 @ 時要不要也能查~~ → **已定案：不查**（10-09 使用者「@先不要查 因為/askai 就是特定查詢目的」）**；10-16 被 KN-Q4 取代：插話判斷時可以查，被 @ 也可以，見 ambient-chat 區塊**。(2) 最多 2 輪、全文 2,500 字是估的，建議上線一週後看 `askai_response_history.jsonl` 的 `intel_meta` 與 `web_context_meta.calls` 再調（輪數是情報與網路共用；放寬輪數的選項見第 9 項）。(3) `config/searxng/settings.yml`（原 `searxng/`）的 openmeteo 那段建議加 `timeout: 4.0`（地點查座標＋拿預報常超過預設 2 秒；不能超過 `max_request_timeout: 4.0`），改完 `docker compose restart searxng`；設定檔是使用者的檔，我沒動。
   - **未定案：天氣題查不到預報**（關鍵字模式走同一條路由與引擎，不是這次改動造成）。選項：(a) 先觀察，看群友多常問天氣；(b) 加一個天氣工具接中央氣象署開放資料 API（要申請免費授權碼，回答有實際數字）；(c) 調路由，天氣題加站內限定（例：`site:cwa.gov.tw`）。建議 (a)，有人常問再做 (b)；(c) 引擎對 site 語法支援不一，要先量。
   - **未定案：股價查不穩**。選項：(a) 加「台股」類型直接查證交所即時報價（`mis.twse.com.tw` getStockInfo，不用 key、0.07 秒、與看盤網站一致；網頁背後沒公開文件的介面、可能改版或限流，要股名→代號表，休市日回前一交易日要標資料時間）；(b) 等 duckduckgo 解封、不改程式；(c) Tavily 等免費方案要註冊 key，不符合「純免費」先排除。建議 (a)。
   - **留給使用者（新）**：(W5) 關鍵字模式（`askai_web_search_mode=keyword`，`intent.should_search` 與 `_ROUTE_RULES`）要不要整個刪掉——建議工具模式跑一週沒問題再刪，現在留著當退回開關；(W6) 新聞類型要不要拿掉一週限制（讓 duckduckgo news 回來，會混舊文）——建議等網路搜尋評估集。
   - **網路搜尋變弱的根因、SearXNG 更新與實測（10-16，未動 code）**：使用者問 SearXNG 不夠強、有沒有更好的開源或社群常用工具；貼了另一個 AI 的建議（降頻、快取、退避、正式 API 當備援、看 `/stats/errors`），問有沒有別人做的外掛或方法讓 SearXNG 用上多數引擎。15:04 使用者自己把 SearXNG 從 2026.8.14 更新到 2026.10.16（`settings.yml` 沒動），Claude 前後對照實測（結果在 scratchpad `after_upgrade/`）。
     - **根因（更新前查證）**：被擋主因是舊版送出的連線特徵不像瀏覽器（httpx＋`shuffle_ciphers` 打亂加密套件、標頭順序），不是查詢量、也不是封 IP：7 天內搜尋引擎 403 為 0；停用很久的 brave、startpage、baidu 第一次請求就被擋；duckduckgo 一週十幾次照樣 100% 驗證（10-09 20:33 起 25 次全擋，SearXNG 對它的暫停寫死 0 秒）。上游 #6596（DDG 看標頭順序與 TLS 指紋）、#6570（Google 檢查 TLS）、#6819（Brave 429，修正 PR #6836 未合併）；#6620（09-04 合併）網路層改 curl_cffi 模擬 Chrome、#6671（09-11 合併）修 bing「只用查詢第一個詞」，兩個都在 GitHub 頁面確認已合併。那份建議裡的快取、單一工作者、被擋暫避、停用壞引擎 bot 都已經有；正式 API 違反純免費。`docker compose up -d` 不會自己 pull，compose 寫 latest 不等於最新。
     - **更新後實測**（同一套 18 引擎 × 2 題，加 bot 實際流程 8 題、補測 13 次）：yahoo 從「連線被斷」恢復，兩題全對題，新梗「何意味 梗」前 5 筆是知乎、百度百科、B 站梗百科、頭條、萌娘百科，「鳴潮 新角色」是巴哈、wuthering.gg、維基——目前最準；duckduckgo 驗證率 100% → 40%；sogou 一題可用（簡中）；yandex、360search 照舊可用（yandex 繁中相關度高，部分標題變成網址）；**bing 更不穩**：「颱風 停班停課」第一次回 10 筆成人內容（有送安全搜尋）、第二次正常，「台積電 股價」正常，「鳴潮 新角色」「何意味 梗」只查第一個字（回辭典的「鳴」「何」），不帶語系時「鳴潮 新角色」回 Lidl 超市——bing 回垃圾時 SearXNG 不算錯誤，會直接混進結果；google、google news 改成 403；brave 照舊 429；startpage「Anubis difficulty too high」；baidu 驗證；reuters 401；yahoo news 0 筆；openmeteo 照舊逾時。bot 實際流程（bing＋duckduckgo）：股價題變好；「鳴潮 新角色」「何意味 梗」只拿到辭典單字頁；新聞「鳴潮 改版」整串無關（一週限制把 duckduckgo news 擋掉，它不限時間時 11 筆對題、全附日期，但混 2024 舊文）；天氣逾時。新版因舊 `settings.yml` 每次啟動噴 15 行 Cannot load engine（presearch、karmasearch、aol 等新版已刪），不影響運作。
     - **別人的「解封鎖」做法對這台的評估**：IPv6 輪換（duckduckgo、startpage、mojeek 沒有 IPv6，Google 整段擋，要改主機與 Docker 網路，不對症）；Cloudflare WARP（第一次啟動自動註冊裝置帳號，違反「不註冊」，條款灰色）；Tor（出口多在國外，bing 依出口地區給結果，Google 必擋，慢）；多代理輪流（免費代理不安全、付費違反純免費，驗證頁是 200 不會觸發換代理）；家用瀏覽器手動解驗證（只對按 IP 封的引擎有效，DDG 不按 IP 封）。第三方外掛、fork 的盤點與社群做法調查還在跑，回來再補。
     - **留給使用者**：(W7) bot 一般搜尋的引擎 `AskAIWebSettings.default_engines` 從 `bing,duckduckgo` 換成 `yahoo,duckduckgo,yandex`、拿掉 bing——建議換（bing 回垃圾時不報錯、會混進結果，還出現過成人內容；duckduckgo 常被擋時另外兩家互補），**10-17 定案 `yahoo,duckduckgo`、已改好（commit `eebf984`，已上線）**；(W6) **已定案（10-16，使用者問「會不會拿到舊聞而非新聞」，聽完說明後「如果可以依照搜尋結果排序日期那我當然不需要限制」）**：新聞不限時間查、結果照日期新到舊排；bing news 不給日期、排不了，保留它自己支援的一週條件、排在有日期的後面；沒日期的不當最新（規則檔第 5 條已有）；**10-17 已改好（`search._search_news`，commit `eebf984`，已上線）**；(W8，10-16 使用者「想知道作了之後會有什麼改變再評估」：Claude 做草稿並用 SearXNG 自己的設定載入程式算出換上前後的實際差異，評估後再定) `config/searxng/settings.yml` 改成 `use_default_settings: true` 只留覆寫值（停用清單、`request_timeout` 回上游預設 3.0、openmeteo `timeout: 4.0`），清掉新版已刪的引擎、拿到 duckduckgo web、google cse 等新引擎——建議改，Claude 先在 scratchpad 做對照草稿，使用者同意後 sudo 換上、先備份，改完再測新引擎；(W9) **已定案（10-16，使用者「不算，讓他開可以，但我覺得用預設值也可以」）**：新版自動解 JS 挑戰（duckduckgo web）與工作量證明（startpage 的 Anubis、mojeek 的 ALTCHA）不算破解真人驗證，可以開；但照官方預設（duckduckgo web 預設關、startpage 與 mojeek 預設不載入），W8 草稿不另外覆寫這三個，bot 的預設引擎也先不加。從 10-09「純免費、不註冊」推得：WARP、付費代理、要 key 的 API 不採用。舊題的建議同步調整：W5（刪關鍵字模式）——工具模式上線一週，但網路搜尋 0 次、等於沒驗到，建議 W7 改完、真的有人用過再刪；股價——新版 yahoo、bing 已查得到股價頁，建議先不做台股類型；讀網頁全文（第四批 12）——建議併進「背景補時事／新梗知識」那題一起談。
     - **社群常用工具與替代方案（10-16 外部調查，回答使用者「有沒有開源更好的、社群常用來爬網路資料的」）**：沒有「開源、自架、免 key 又嚴格勝過 SearXNG」的通用搜尋——有自有索引的（YaCy、Mwmbl、Marginalia、Open Web Index）中文時事太弱或要註冊、Stract 已封存；其他元搜尋（4get、Degoog、LibreY、Websurfx、OpenSERP、ddgs）爬的是同一批上游；Whoogle 2026-07 宣告結束；Vane（原 Perplexica）底層就是 SearXNG。開源 LLM 應用的免 key 預設幾乎都是自架 SearXNG（Vane、Khoj、local-deep-research、Morphic 的 Docker 版）；要 key 的預設以 Tavily 最常見；Bing Search API 2025-08-11 退役、Google Custom Search JSON API 不收新客戶（2027-01-01 停）、Brave 2026-02 起要信用卡。字面上免 key、但有條款或存續風險的新選項：keenable 公開端點（每 IP 每小時 1,000 次；條款寫「僅限個人使用」並禁止把輸出單獨轉給第三方）、You.com 免 key（每天 100 次，官方定位評估用）、Firecrawl 免 key（每 IP 每日上限未公布）、SearXNG 的 google cse（借第三方公開 cx，「搜尋整個網路」只到 2027-01-01）——建議先不採用，等 W7 測試結果，yahoo 撐不住再評估。「爬網路資料」那類工具解決的是讀全文不是找得到：輕量做法 curl_cffi 下載＋trafilatura 抽正文（實測 10 個台灣頁面含 Big5 都抽得到、每頁 3～160 毫秒、峰值約 52 MB）；Crawl4AI、Firecrawl 自架、Jina 自架對這台 VM 太重；Scrapling 的 solve_cloudflare、FlareSolverr、newspaper4k 的 cloudscraper 是過 Cloudflare 驗證，不用。Google 新聞 RSS 的 robots.txt 禁止 /rss 並點名 AI 爬蟲，排除。
     - **W8 前後差異評估（10-16 16:4x，草稿與模擬都在 scratchpad `w8/`，沒動使用者的檔）**：用 SearXNG 自己的載入程式（`init_settings`＋`load_engines`，擋掉寫檔與連網）模擬；同一套模擬跑現在的檔和執行中 `/config` 的 232 個引擎八個欄位 0 處不一致，可信。使用者的檔是上游 2026-04-17 範本（8579974f5）的原樣複本，使用者自己改的只有：default_lang zh-TW、formats 加 json、request_timeout 2.0、max_request_timeout 4.0、打開 bing 與 reddit、08-15 停用 8 個。草稿 `settings.proposed.yml` 約 60 行。換上後**會變**：一般逾時 2→3 秒（唯一影響 bot 的一項；bot 用的引擎 p90 約 1.8 秒）；openmeteo 4 秒（天氣才有機會查到）；啟動錯誤約 230 行（19 個 Cannot load engine）→ 只剩 ahmia、torch 兩行（官方預設本來就有）；載入引擎 232→261（多 39：預設開 7 個含 google cse、可指定 32 個含 duckduckgo web；少 10：startpage、mojeek×3、yahoo news 等官方改成不載入，bot 都沒用）；搜尋框建議字從關變成送 DuckDuckGo；瀏覽器表單 POST→GET（搜尋字會進網址與紀錄）。**不變**：formats 含 json、安全搜尋、語系、max_request_timeout 4.0（openmeteo 4.0 與官方長逾時都靠它截住，不能拿掉）、外掛、限流；bot 指定的引擎與 W7 候選全部載得到。**W8 小題（10-17 定案，全照建議：a 換、b 3 秒、c 刪、d 照官方、e 加密鑰不急；W5 等 W7 改完真的有人用過再刪、股價不做台股類型、天氣先觀察、讀全文併插話上網查第二版，同樣定案不再問）**：W8a 換不換——建議換，10-17 15:35 測試結束後；W8b 一般逾時跟官方 3 秒或留 2 秒——建議 3 秒；W8c 草稿裡 9 筆「維持現況」的圖片引擎（1x、artic、devicons、flickr、lucide、openverse、google images、qwant images、qwant videos，舊範本的值、官方因結果差／逾時／限流關掉）留或刪——建議刪（瀏覽器圖片分頁 14→6），常用 SearXNG 搜圖才留；W8d google cse（新版預設開、進瀏覽器一般分頁；借 blackle.com 的公開元件 ID、不用 key，「搜尋整個網路」2027-01-01 停，借用 ID 屬條款灰色）照官方開著或關掉——建議照官方（W9「用預設值也可以」），bot 不用它；W8e 實際生效的 secret 是 docker-compose.yaml 寫死的預設字串（compose 進版控、公開鏡像看得到；.env 沒有 SEARXNG_SECRET），只有本機與 docker 內網連得到——建議另外在 .env 加隨機 SEARXNG_SECRET 再 `docker compose up -d searxng`（restart 不吃新環境變數），不急。bing 那行（瀏覽器一般分頁查 bing）跟 W7 一起定。套用 7 步（備份、awk 搬原 secret 行、`check_final.sh` 換上前唯讀檢查、cp、restart、看 log、確認 `/config` 印出 `261 4.0 True False 'duckduckgo'`）與還原步驟寫在 workflow 結果裡，使用者決定後再給。
     - **外掛與解封鎖方法的調查結論（10-16，第二組 workflow，九個 agent 含四個反查）**：沒有能讓多數引擎不被擋的第三方外掛——SearXNG 外掛只有 pre_search、on_result、post_search 三個掛鉤，改不了請求方式；第三方能用的都是 sidecar 或自訂引擎（4get-hijacked 15 星、07-04 後沒更新；4get 與 Degoog 的 Google 都要真瀏覽器加螢幕；Trawl 會解 reCAPTCHA／hCaptcha／Turnstile，違反規則）；上游 09-08 刪掉「查別的實例」的引擎，維護者稱拿公開實例當備援 very selfish。官方 09-04 的 curl_cffi 改版就是最有效的方法（已更新）。升級後仍擋：google／google news 403（上游 #6835 家用網路同樣 403、沒人回）、brave 429（#6836 未合併）、startpage「Anubis difficulty too high」（解題上限寫死 4）、baidu 驗證、sogou 與 quark 解析錯、reuters 401。可以試的小點：duckduckgo（html）引擎用 Chrome 的連線特徵卻自稱 Firefox（本機回聲測試確認同時送出 Chrome 的 sec-ch-ua 與 Firefox UA），可能是它還有約四成被擋的原因之一；settings.yml 的引擎項目可以覆寫模組變數（`_HTTP_User_Agent`），不改程式就能試，但依賴內部變數名、未實測。另有一批轉賣 Google／Brave 結果的新引擎（startpagina、s1search、resulthunter、tusksearch 等）上游多為 inactive、沒有台灣實測。
     - **穩定度測試（10-16 15:35 起跑 24 小時，10-17 15:35 自己停）**：使用者問「不知道怎麼樣才是穩定的」。定義（每個引擎各自算）：查得到率（沒被擋、沒逾時、有結果）≥90%、有用率（查得到時前 5 筆至少 3 筆對題）≥80%、不當內容 0 次＝可當主力；查得到與有用都 ≥60%、沒有不當內容＝只能當備援；其他＝不穩；另看同一題重複查時前 5 筆網址的重疊度（忽好忽壞的引擎會偏低）。做法：主機上跑 `/tmp/claude-1000/-home-jason-discord/5c5c87ce-c09d-4572-80a9-fcf990d36ac7/scratchpad/stability/monitor.py`（只讀 127.0.0.1:8888，不碰 bot），每 20 分鐘一輪：yahoo／duckduckgo／yandex／bing 查同一題（10 題輪流）、duckduckgo news（不限時間）與 bing news（限一週，同 bot 現況）各查一題、每 3 輪合查 yahoo,duckduckgo,yandex（W7 提議的組合），每輪另存 `/stats/errors`；每輪 7～8 次請求。資料在同資料夾 `run1/rounds.jsonl`，摘要用 `summarize.py <rounds.jsonl> [--detail]`；提早停：`kill $(cat run1/pid)` 或建 `run1/STOP`。資料在 /tmp，主機重開機會消失。第一輪 7 次全查得到、全對題（bing 這次「鳴潮 新角色」5/5 對，一小時前同一題回辭典的「鳴」）。結果用來決定 W7。**結果（72 輪、456 次請求，10-16 15:35～10-17 15:15）**：yahoo 72 次 100% 查得到、100% 對題、0 不當、重複查同一題前 5 筆重疊 0.84（最穩）；duckduckgo 97%／100%／0（真人驗證 2 次）、重疊 0.77；yandex 100%／100% 但「鳴潮 3.7 版本」回了一筆成人網站（有送安全搜尋）→ 依定義算不穩；bing 90% 查得到（0 筆 7 次）、對題只 71%、20～24 時只有 75% → 只能當備援；三家合查 24 次 100%／100%／0。新聞：duckduckgo news 不限時間 72 次 100%／100%、前 5 筆全附日期、72% 是 7 天內、80% 是 30 天內（W6 的做法可行）；bing news 97%／80%、完全不附日期（逾時 2 次）。**W7 定案 `yahoo,duckduckgo`（10-17；使用者 10-16「建議都很好」＋10-17「照講過的作法做」）**（拿掉 bing；yandex 不進預設，出過成人內容）；新聞照 W6 定案：duckduckgo news 不限時間、照日期排，bing news 保留一週條件、排在有日期的後面。
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
last_confirmed: 2026-10-17
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

**第三輪（deep module 角度；另一個 session 10-16 21:27 產出的 HTML 報告 `architecture-review-20261016-2127.html`，沒進 repo 也沒記交接檔；使用者 10-17 貼來「先與我討論」）**：找「同一件事在好幾處各寫一份、對外介面太寬」的地方，建議收成一個對外用法簡單的模組。十張候選：c1 Telegram 投遞單位（首選）、c2 人物進 prompt（/askai 與插話共用）、c3 綁定頻道解析交給 channel_registry、c4 公告／FB／IT／PTT 的發文與記錄只留一份、c5 聊天向量庫有一個主人、c6 成員記憶自己管生命週期、c7 LLMService 依角色呼叫、c8 訊息轉模型輸入只做一次、c9 Postgres 連線與交易一個入口、c10 共用一份 Discord 測試替身；其餘（常駐面板、自介投稿、關鍵字監看、巴哈訊息鏈、StateDB、點名）。順帶確認的 bug：B1 Telegram 送失敗不重試（多路由一成一敗時敗的那條永遠不補）、B2 插話的人物卡檢索沒帶被 @ 的 id、B3 公告／FB／IT 第一則貼出後後面失敗會整則重發＋附件太大退純文字又送同一批附件、B4 raw 批次沒有 SAVEPOINT（一筆壞掉整批回滾）、B5 反應熱度斷線時 rollback 再拋例外、壞連線放回池子、B6 插話回覆超過 2000 字整則丟掉。**10-17 反查完成**，每條的真偽、影響、收斂順序與本輪題目見下一段。**原則更正（10-17 使用者）**：Claude 一度說「照最小修改的原則，十張只挑一兩張」→ 使用者：「沿用現有架構、最小修改的原則沒有錯，但有重複輪子、分散各處的程式碼就要收成一個模組，我一直有講。」（AGENTS 開工第 3 條、記憶 reuse-first 本來就有記，是 Claude 用錯。）所以核對確認是重複的候選都要收，討論的是先後順序、怎麼收、和插話上網查怎麼錯開，不是挑幾張做；最小修改管的是收的時候沿用現有分層、不另起一套架構。

**第三輪反查結果（10-17 16:xx；workflow 五組唯讀核對 log、唯讀 SQL、程式與歷史，主 agent 再抽查關鍵幾條）**：報告的行號與數字大多對，但它沒查 log，分不出哪些真的發生過；漏了三件真的出過事的，B3～B6 實際都是 0 次。
- **真的出過事、程式現在還是這樣**（報告不是漏掉就是沒列成 bug）：
  - **X1 巴哈開新討論串後中途失敗，下一輪再開一串**：`bahamut_monitor._process_thread` 開串（`create_thread`）後，續文、主文附圖、留言都送完才 `save_bahamut_thread`（它同時寫已送紀錄），中間一出錯就沒記。那段註解「立刻寫入 state（即使後續回覆失敗，也不會重複建 thread）」只對回覆成立。04-30～09-30 有 8 篇被開了 250 個不完整的串（18385 一篇 106 串、08-07～08-11 每小時一串；17392 40 串、17201 39 串；最近是 09-30 的 19054，5 串），起因是 Discord 500（245 次）、413（5 次）。那 250 串後來有沒有手動刪掉，log 查不到。
  - **c4a 公告推送與 30 分鐘保險輪詢沒有共用鎖，同一篇連圖貼兩次**：`notify_server` 每次推送都新建一個監看物件，輪詢用的是另一個，去重只靠送完才寫的已送紀錄；`discord_bot._auto_start_official_article_monitor` 說明裡的「去重靠 StateDB，不會重送」不成立。07-26 #5197、10-17 11:09 #5631「共鳴者展示｜鎖暝」（11:09:29 推送、11:09:31 輪詢，各進一次 `send_article_to_channel`）。巴哈已經有每篇一把的模組級鎖（`_get_thread_lock`）。
  - **c9 連線借出前沒檢查還活不活著**：`context_retriever`、`member_profile_store`、`store_chat` 各自 `PGVectorStore.from_params(...)`（同樣的參數三份），都沒傳 `create_engine_kwargs`，所以沒有 `pool_pre_ping`；資料庫關掉閒置連線後，每個池子第一次使用必失敗（06-20、09-17、09-24、10-02）。09-17 09:59、09-24 22:17 兩筆偏好寫入撞到，疊上 c6 的「先刪再寫」，兩筆偏好永久丟失、累積次數歸零。c6 另外的損失：06-03 49 張人格卡消失約一天、5 月 12 個晚上約 660 次寫入失敗。交接檔原本把「先刪再寫」列為已知取捨，但只講到人格卡（隔晚會重寫）；偏好和招牌梗丟了不會回來。
- **每天在發生的品質問題**：
  - **B2 對，但歸因錯**：不是「4 月只修到 /askai」（插話 06-21 才上線），是 10-02 `673a965` 把插話改讀換過名字的文字後，`ambient_reply` 呼叫 `retrieve_rag_context_sync` 沒傳 `mentioned_user_ids`，檢索端從文字重抽抽不到；「依稀記得」的對象判斷也從換過名字的文字抽 @，同樣抽不到（報告沒提）。約每天 3 次：50 次被 @ 觸發裡判成「問別人」0 次，追得到的 16 個被 @ 的人只有 5 人拿到人物卡。`test_ambient_natural.py` 有一條直接比對造成 B2 那行原始碼的測試。
  - **X3（報告沒列）找暱稱的候選詞依字碼排序後只取前 8 個**（`persona_card_builder` 取 `tokenization` 排序後的前 8），不是照句子裡出現的順序：「米拉你今天怎麼了」認不出米拉，插話檢索 71% 撞到 8 個上限；/askai 與插話都受影響。改了會改變檢索結果，要先離線對照。
  - **X2（報告沒列）群友刪掉的訊息還留在聊天向量庫**：raw 標成已刪的 1,241 則（04-21～10-17）有 779 則還在，插話回憶與 persona agent 撈得到；刪除事件只在 raw 標記，向量庫沒有刪除的路徑，交接檔也沒有這項決定。要不要刪是產品與隱私的決定；刪既有的要先備份、經使用者同意。
- **從沒發生過，或報告說錯的**：B1 近 30 天 0 次（全期 42 次失敗都是 5～6 月同一則 pk 7616）；「只在重啟時補」是 10-07 有註解、有測試的寫法，真正的缺口是 10-05 定案的每小時重試沒做（記在 Telegram 過濾區塊「還沒做」）；「多路由一成一敗」目前只有一個路由，不會發生。B3 公告／FB／IT 04-12 起 0 次。B4 04-12 起 0 次；批次裡有刪除時是變 ERROR、統計 0，不是「統計顯示有寫入」。B5 rollback 再拋屬實，「壞連線放回池子」錯（psycopg2 2.9.13 的池會丟掉已關閉的連線），唯一的呼叫端接住當成空的，功能照樣降級，只差 log 看不到。B6 上線以來 0 次（8,776 則插話最長 248 字），有 WARNING 與 prompt 全文，缺的是互動紀錄與冷卻記帳；同一段用回覆送出的兩條路沒擋 @everyone 與 @人（0 次）。
- **十張候選列的重複都屬實**（數字小差異）：c1 相簿與單則同一串步驟寫兩份、「這個單位送到哪」組法 5 處、12 小時規則 3 處各用不同起算點、測試 64 處直接呼叫私有的 `_process_one`（方法 48 個，不是約 58）；c2「這份資料屬於誰」6 處（4 處是 SQL 字串）、@ 轉 id 4 份、id 換名字兩套；c3 讀綁定頻道 6 種找法、16 檔 20 處，`get_configured_id` 只有 2 處在用，2 處直接讀 config.json（`rollcall_commands.py` 用相對路徑，守衛沒擋到），「沒綁」有五種寫法，點名的 `runtime.channel_id` 是只寫不讀的死欄位；c4 FB 送出流程 57 行裡 32 行和公告逐字相同、「每 10 張一批」5 份、發文用的圖片下載 3 份（base_monitor 沒人用的只有 2 個方法）；c5 直接用 SQL 讀聊天向量庫欄位的有 5 個模組、4 個索引是手動建的（時間用字串比大小是刻意的效能設計）；c6 偏好與招牌梗的「讀 → +1 → 升級 → 寫」兩份、衰減公式兩份逐行相同、/forget_tag 的擁有者檢查只在指令層；c7 `generate_reply` 28 個參數（17 個只有一個呼叫端在用）、`_get_llm` 手寫 6 份；c8 /askai 與插話的訊息轉換各一份（列的差異實際都是 0 次，「/askai 不處理貼圖」不成立）、3 個比對原始碼字串的測試；c9 三處各自拼帳密、`ai_interactions_store` 10 份同樣的連線樣板、discord_data 實際在用的連法 5 種（「with 不關連線」實際影響 0）；c10 兩份 Discord 假世界、11 份 Interaction 替身，兩份對「封存的 thread 拿不拿得到」行為相反（交易測試測不到正式環境靠的退路），10-13 起還在變多。其餘 r1～r6（綁定時部署面板、自介投稿、關鍵字監看、巴哈訊息鏈、StateDB、點名）屬實、用量低；自介投稿與關鍵字監看沒有測試。
- 報告 HTML 沒進 repo、本機也沒有（使用者貼在對話裡），之後要查原文只能請使用者再給。
- **建議的收斂順序（確認是重複的全部排進來，只排先後；Claude 提出，待使用者確認）**：
  1. 插話那批之前，不碰插話的檔、各自一個 commit：X1 開串後馬上記下這串和主文（之後失敗只記 log，下一輪走既有的增量更新）；c4a 公告／FB／IT 的推送與輪詢共用鎖——把巴哈那份每篇一把的鎖搬到三個監看共用的地方再用，不寫第二份；c9 第一步：三份 `PGVectorStore.from_params` 收成一個共用的建構函式、加上借出前檢查，放在 `pgvector_connect` 旁邊（「憑證的擁有者提供連線方式」的既有慣例）。
  2. 插話那批（同一次重啟）：W6、W7、插話上網查第一版（記錄模式）、被 @ 長度上限＋關思考重答，加 B2（從原訊息取一次被 @ 的 id，人物卡檢索與回憶對象共用，用現有的 `extract_mentioned_user_ids`）、B6（送出前用 `split_message`、回覆不 @ 任何人）。給插話新加的參數先收成一份插話專用設定。ambient_reply 讀綁定頻道那段不動，等 c3。
  3. 重啟後的下一小批（防丟資料）：c6 的「先算好向量再刪舊的」、B4 每筆設保存點（`ai_interactions_store` 已有同樣寫法）。
  4. 插話上網查第一版上線後、第二版（全開＋存筆記＋淡出）之前，依序、不交錯：c10 第一步（共用 Discord 測試替身，要開新資料夾）→ c2＋c8（含 X3，改之前離線對照）→ c6＋c9 整張（含 B5、10 份連線樣板、衰減公式收成一份給第二版用）→ c7（插話專用設定整包搬進用途入口、`_get_llm` 收成一份）。
  5. 不碰插話檔、可以穿插：c4＋B3（公告／FB／IT／PTT 的發文與記錄一份；主文貼出就記已送、退純文字時跳過太大的檔）→ c1＋B1（Telegram 投遞單位；補 10-05 定案的每小時重試、頻道 0 自動寫入、有文字的單則補圖）。
  6. 最後：c3＋N3（綁定頻道一個入口、拆 utils.py、點名的相對路徑與死欄位）、c5＋X2（聊天向量庫的主人，和 M9 第 1 步一起定）、c10 收尾、r1～r6。
- **本輪題目（10-17 16:xx 提出；使用者 16:5x「AR3-Q1～Q5 全部修」→ 五題全照建議定案：Q1 X1、c4a 現在修、和插話那批同一次重啟；Q2 B2、B6 併進插話那批；Q3 c9 第一步跟 Q1 一起、先算向量再刪排重啟後下一批；Q4 c7 排在插話上網查第一版後、第二版前；Q5 AGENTS 開工第 3 條已補、和下一批一起 commit）**：
  - AR3-Q1 X1、c4a 這兩個「同一篇貼兩次」的 bug 現在修、和插話那批同一次重啟（插話那批拖過一兩天就先單獨重啟）？A 現在做／B 插話之後的下一次重啟／C 等 c4 一起。**建議 A**：唯二真的讓群友看到重複貼文的，修法小、不碰插話的檔。
  - AR3-Q2 B2、B6 併進插話那批？A 兩個都併／B 只併 B2／C 另排。**建議 A**：同一個檔，突變測試與重啟各只做一次；插話被 @ 時也會上網查，認對人更重要。
  - AR3-Q3 成員記憶丟資料：A 先修兩小步（c9 第一步跟 Q1 一起上；先算向量再刪排重啟後下一批），整張照順序／B 等 c6＋c9 整張／C 維持已知取捨。**建議 A**：唯一真的丟過資料的，兩步擋掉已發生過的兩種起因。
  - AR3-Q4 c7 的時機：A 插話上網查第一版先做、新參數先收成一份插話專用設定，c7 排在第二版前／B c7 先做（插話上網查延後幾天）／C 兩版都做完再做。**建議 A**。
  - AR3-Q5 AGENTS.md 開工第 3 條補一句「現有程式裡找到的重複也要收、排進順序做；沿用現有架構、最小修改管的是收的時候不另起一套分層，不是不收的理由」？**建議補**，和下一批一起 commit。
  - 排到下一輪：收斂順序的細節與開 `test/fakes/`（c10）；X2 那 779 則要不要從向量庫刪；插話逾時變多的原因（10-16 生成 150 次逾時 10 次、10-17 到 15 時 49 次裡 5 次，之前約 0.75%；10-16 17:22 那次的快照是主模型正忙、向量模型也載著；聊天索引補寫 10-16 14:36 打開，日期對得上，還沒核對是不是它）。

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
- **10-13 列給使用者的清單（10-17 起不再當待決清單：裡面要做的事已歸到各區塊的待做，其餘結案；不再拿來問）**：
  - 架構：Q3 Discord 接入 → 建議 (a) 搬 `llm/ambient`、`llm/storage` 的 Discord 接入到 services，llm 禁 discord＋守衛。Q4 CI → 建議 GitLab 共用 runner，先寫 `.gitlab-ci.yml` 與本機 `make check`，**不推送**。M5 runtime JSON → **已定案 (a) 只統一讀寫機制（`utils/runtime_file`），不匯 StateDB、檔案不動**；`/app/` 路徑已改成 `sys_settings/paths`。M6 套件撞名 → 建議「統一以 `src` 為根」：scraper、telegram-scraper 容器也掛 `./src:/app`、以套件路徑啟動與 import，共用的（`tg_config.normalize_channel_identifier`、媒體時限常數）放 `utils/`；代價：改 compose、重啟三個容器、相對路徑（media、session）要確認。M7b gate 瘦身 → 只跑守衛＋import 解析＋設定載入，完整測試由 `make check` 與 CI 跑。M9、M10 → 最後、先討論設計。★ `/anonymous`、test_commands → 使用者說先不管。
  - /askai 與搜尋（產品行為，★ /goal 不動，最後再決定）：openmeteo `timeout: 4.0`（建議加；`config/searxng/` 是使用者的檔）、天氣查不到預報（先觀察）、股價（建議加台股類型）、W5 關鍵字模式（跑一週再刪）、W6 新聞一週限制（等評估集）、輪數與全文長度（累積一週）、縮短思考（先用考卷確認）、向量那路改用原句與閒置後第一次搜尋慢（先量）、Agent 評估三題：放寬輪數（第 3 輪只准 fetch，面試後用新題目驗收）、工具說明加「不用加遊戲名稱」、**對話逾時不重試＋回答長度上限（建議併進 /goal，穩定性不是調分數）**、回答判讀 31／42 待抽看（q05、q31、q36、q41）。
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
- 判決持久化：發送紀錄 `telegram_relay_delivery_state` 記三種去向——主頻道、隔離 thread、頻道 0（＝停止主動追蹤；設計上不擋真的晚到的圖）；`needs_recheck` 欄＝沒經模型判就放行的，模型恢復後補判（每 10 分鐘也掃一次），判成垃圾就用搬移功能移走。不建新表。10-05 已把舊的 373 則標成頻道 0（備份 `~/backups/telegram_delivery_backup_2026-10-05.sql`）。**更正（10-17 反查）**：①頻道 0 只影響重啟時的啟動補償（`list_undelivered_message_pks` 只撈完全沒有發送紀錄的）；每小時輪詢只從游標往後撈新訊息，不看發送紀錄。②程式不會自動寫頻道 0：唯一寫發送紀錄的 `_send_unit` 只記實際送到的頻道；10-05 設計的四種情況（相簿晚到超過 12 小時、Telegram 系統通知、有圖標示滿 12 小時沒下載到、合併後沒內容）沒做，見下方「還沒做」。③所以啟動補償不是 0：近期每次重啟都偵測到 2 筆（10-11～10-16 每次都是 2，反查認為是 2 則系統通知）。
- 等模型：排隊（插話、產圖、別的行程後面都等；跨行程鎖檔在 `run/gpu_lock/`）；模型逾時或連不上隔 30 秒～5 分鐘再排，排滿 30 分鐘（`give_up_seconds`）才放行並標補判。各模組逾時供參考：插話生成 180 秒、/askai 300 秒、persona agent 讓前景 600 秒、看圖補字典 120 秒、跨行程鎖等別的行程 15 分鐘、過濾單次問模型 60 秒。
- 準確度：90 則離線樣本誤關 0、漏放 1；30 天 414 個單位模型判出 75 個會隔離（閒聊 30、無關圖 24、灌水 15、罵人 6）；10-07 上線第一天 9 個單位搬 4 個。

**已定案（摘要；每題的選項、理由與數據見歸檔「Telegram 訊息 LLM 過濾 + 隔離區：討論、實作與上線紀錄」）**
- 判斷標準：只問「有沒有遊戲資訊」；拿不準就放行；一定看圖（純圖不能一律放行，反例 13649 文字只有「水」、圖是角色設計稿）；文字或任一張圖有資訊就放行；看不了的檔案（語音、壓縮檔）或選來看的圖有一張沒看到就放行；角色手辦、周邊、聯名、展場照算有；看得出是別的動漫或影視的截圖不算。
- 介面與流程：TF-Q1 面板＝thread 置底雙層選單（使用者自訂）；TF-Q2 誰能按＝有「管理訊息」權限；TF-Q3 反方向這次不做；TF-Q4 隔離那則最上面寫判定；TF-Q5 先縮圖、不合併多則一次問；TF-Q6 一次一則；TF-Q7 原本等 90 秒放行 → 10-08 改成排隊到 30 分鐘；TF-Q8 離線樣本 → dry_run → on；TF-Q9 不附前幾則當上下文；TF-Q10／SW-Q1 開關放 `switches.json`、不做開關指令；SW-Q2 這次只搬 Telegram 過濾；SW-Q4 `config.json` 安全寫入（`ChannelConfig.update_config`）。
- 搬舊垃圾（MV-Q1～Q5）：近 30 天、使用者看過清單再搬、刪原貼文、只改那列的 `discord_channel_id`、不備份（Telegram 可重抓；log 逐筆記 `db#` 與列 `id` 供復原）。
- 補判（UC-Q1～Q3）：發送紀錄加 `needs_recheck` 欄（使用者自己執行 ALTER）；模型沒回應或回答看不懂才補；一恢復就補＋每 10 分鐘掃一次。
- 爬蟲端（S1～S4、SQ1＝A）：啟動讀對話清單修相簿缺開頭（Telethon 沒有 pts 起點就丟掉比它早的更新）；下載加 `download_with_stall_guard`（180 秒沒進度就取消）；補掃每 15 分鐘重試到發文＋12 小時（`MEDIA_RETRY_WINDOW`，要等於轉發端 `_GROUP_FOLLOWUP_MAX_AGE`，有守衛）；新訊息第一次下載失敗先壓 30 分鐘不通知（`MEDIA_HOLD_NOTIFY`），補到圖再通知；Telethon 不釘版本。

**還沒做（之後或轉發端那批）**
- 有文字的單則滿 30 分鐘先送文字後，補到的圖送不出去（10-05 定案要以（補圖）補上）。
- 送失敗每小時重試沒做（10-05 定案 T10-Q2：每小時重試，進來超過 12 小時改回只在重啟時重試、不放棄）：現在單則與相簿送失敗都照樣記成處理過、推游標，只有重啟時的啟動補償撈得回完全沒紀錄的。近 30 天 0 次（全期 42 次失敗都是 5～6 月 pk 7616，一個月後才送出）。排在架構審視第三輪 c1＋B1 一起做。
- 頻道 0 自動寫入沒做（上面「更正」②的四種情況）；做了之後重啟的啟動補償才會歸 0。同樣排在 c1。
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

## 聊天檢索（RAG）優化：重複折疊、品質閘、/askai 重排（2026-10-26 做好並 commit；重算向量、HNSW、切換 10-27 完成；聊天搜尋工具 10-27 做好、待重啟）

<!-- @meta
id: rag-chat-retrieval
type: STATE
status: draft
last_confirmed: 2026-10-27
depends_on: [mcp-search-tools, context-prompt-optimization]
affects: llm/retrievers/context_retriever、llm/preprocess/tokenization、llm/preprocess/emoji_text_utils、llm/ambient/ambient_reply、commands/llm_commands、sys_settings/llm_settings、sys_settings/switches、settings/switches.json、test/test_rag_collapse、test/test_shared_conventions、AGENTS.md
-->

> 說明文件（架構圖、三條檢索路徑的流程與例子、HNSW 原理、決定與優劣、待判斷清單）與 60 題評估集候選（第二個分頁，請勾 30 題）在 Claude Doc：https://claude.ai/artifact/PfrESK3SSsr7jCpoVQkVKr 。本區只留結論、待決與坑。

**現況數字（10-26 唯讀實查）**：聊天表 `data_discord_messages_index` 344,808 列、1024 維、無向量索引（heap 540 MB、向量收在 TOAST 1.8 GB）；插話回憶的全庫查詢（本頻道、LIMIT 25）全表掃 3.96～4.06 秒、讀 2.9M 頁；/askai 窗內查詢（`message_id = ANY`）走 btree 21 ms。同一人同一句的重複 60,317 列（17.5%）；不到 8 字 146,851 列（42.6%）；純表情描述 25,279 列（其中 1,732 列 ≥ 8 字、過得了舊閘門）、純貼圖 15,397 列（其中 14,612 列 ≥ 8 字、過得了舊閘門）。pgvector 0.8.2、PostgreSQL 18.6；maintenance_work_mem 64 MB、shared_buffers 128 MB；VM 7.9 GB、可用約 4.1 GB。

**做了什麼（都在檢索端；寫入端、資料庫一列都沒動）**
1. 折疊（RG-Q1）：`search_chat` 多撈 `_COLLAPSE_OVERFETCH`＝4 倍，再用 `tokenization.dedup_key`（正規化後只留字母數字與中日韓文字）把同一作者同一句折成距離最近的一則、帶 `repeat_count`（只數這批撈到的，不是全庫）；不同作者的同一句各自保留。BM25 在 100 則視窗裡同一人同一句只算最新那則。插話回憶的注入行尾標「（同一人說過 N 次）」。
2. 品質閘（RG-Q2）：`emoji_text_utils.is_emoji_or_symbol_only` 多認 `:描述:` 與 `[貼圖：…]`；插話的 `_is_link_only` 收成同模組的 `is_link_only`，插話內容閘、插話回憶、/askai 三處共用（守衛 `test_shared_conventions` 新規則「整則只有連結的判斷」擋手刻的 `startswith("http`，爬蟲容器例外）；插話回憶的 `callback_min_chars` 改成 SQL 的 `length(text) >= 8`，候選池不再被反應詞佔掉（以前 45% 在 Python 端才丟）。
3. /askai 相關名額：純表情／貼圖／連結不佔名額、不分作者同一句只留融合分最高的；保底的最近 25 則不經閘。stats log 多 `noise_skipped`、`repeat_skipped`、`reranked` 三個計數；`retrieval_debug` 多 `reranked`（message_id、分數、送去的文字）。
4. /askai 重排：融合名次前 `rerank_candidates`＝30 則，每則給 reranker 看「顯示名: 內容」，照分數取 25，低於 `rerank_min_score`＝0.1 的不進；reranker 壞掉、GPU 等太久、筆數不對都照融合名次。reranker 由指令層 `_askai_reranker()` 依開關 `askai_rerank_mode`（`switches.json` 已設 on；程式預設 off）建 `services.search.rerank.LemonadeReranker` 交進檢索層（檢索層是技術層，不 import `services.search`）。實測 9 則 0.6 秒，分數兩極：答得到的 ≥ 0.95、不相干的 ≤ 0.0001。
5. 評估集：60 題候選（A 誰說過什麼 20、B 某次討論的推論 15、C 口頭禪 15、D 近 14 天 10）從 `discord_messages_raw` 唯讀抽：A／D 取 15～60 字、有人按過反應、全庫唯一、非表情貼圖連結；B 多一個「所以／結論／最後」字面條件；C 是同一人同一句 ≥ 19 次。每題錨 message_id（C 類是那位作者說過這句的任一則）。跑分程式是新檔，等使用者勾完 30 題再問放哪。

**獨立審查後的修正（10-26 下午；三位審查者：正確性、設計與重用、重算計畫；每條 medium 以上再由反駁者驗證，結果見盤點紀錄）**
- 折疊只做一次、放在兩路之前：/askai 視窗先 `_collapse_window`（同一人同一句留最新，並回「每則 id → 代表 id」對照表），BM25 吃折好的清單；向量路仍拿**全部** id 去查（最新那則可能還在寫入緩衝、沒進向量庫，舊的才找得到），查到的換成代表、同一組只留最好的名次。原本 BM25 留最新、向量留最近，兩路投到不同的 id，RRF 把重複講過的句子分數拆成兩半（審查抓到的最重要一條，反駁驗證在容器重現確認為真，並補了「向量路要查全部 id」這個坑）。`search_chat` 的 `_collapse_repeats` 只給插話回憶的全庫搜尋用，代表改取最新那則、名次與距離取最近那筆。
- 純標點（「????」「……」顏文字）`dedup_key` 是空字串：三處都不折（各自算一句），而且 `is_emoji_or_symbol_only` 現在把沒有任何字詞字元的也當符號（插話內容閘也因此不會對「????????」出手，行為小變）。
- `is_link_only` 先去掉存檔格式的 `[預覽：…]`，純連結＋預覽也算純連結。
- /askai 重排改在 bot 的 async 閘門裡做（`gpu_exclusive("askai-rerank")`，插話與產圖看得到持有者；最多等 `rerank_gpu_wait_seconds`＝10、租約 `rerank_lease_seconds`＝30），`LemonadeReranker` 建立時給空的 gate、不再拿第二把鎖檔（它預設的 `gpu_exclusive_sync` 是給沒有 event loop 的行程用的）。
- reranker 回非有限分數（後端漏掉的文件客戶端填 -inf、壞掉回 NaN）一律不保留；一個有效分數都沒有就照融合名次並記 WARNING；`reranked_count` 只數有效的。
- `hnsw.ef_search` 夾在 pgvector 上限 1000 內（超過不是報錯而是被重設成 40），`services/search/vectors.py` 同步；`search_chat` 一律撈 dist、Python 端先照距離排再折（HNSW 的 iterative_scan 不保證順序）。
- 守衛規則改成只抓「整則只有連結」的形狀（`all(...)`／`any(...)` 裡的 `startswith("http…")`，單字串與 tuple 都抓；單純驗網址的 `url.startswith("https://")` 不抓），並有自己的 finder 測試。
- 插話回憶的最短字數只留 SQL 一份（Python 端的重複檢查與 debug 的 SHORT 標記拿掉）；`rerank_candidates` 簽章預設 None（＝和相關名額一樣多），數字只在設定與開關說明；`LemonadeReranker` 改頂層 import（啟動 gate 的 import 解析涵蓋得到），`services/search/__init__` 的說明改成「bot 只借 rerank 客戶端、不碰索引」。
- `emoji_text_utils` 模組說明改成專案格式。
- 審查建議但沒做、要你判斷：把 `LemonadeReranker` 搬到 `llm/client/`（技術層的模型客戶端，bot 就不必 import `services.search`）——是新檔與搬程式，等你點頭。

**定案與理由**
- 折疊在 Python、不在 SQL：正規化規則已經有一份（`tokenization`），SQL 再寫一份是二輪；排序成本在掃表不在回傳筆數；在 Python 折測試不用資料庫。
- 只折字面、不折語意（MMR、距離閘）：重複的 86% 是一模一樣的表情、貼圖、≤4 字反應詞，近似重複只多收 0.6 個百分點；MMR 要在沒索引的表上多掃幾倍，等 HNSW 再談。
- /askai 相關名額跨作者去重，插話回憶保留不同作者的同一句：名額是給模型的脈絡，五個人的「笑死」不如五句不同的話；幾個人都講過是訊號。
- 品質閘收進 `emoji_text_utils`、不開 `text_quality.py`：使用者要求新檔先問；該模組本來就裝著「整則只有表情」的判斷。
- reranker 門檻 0.1：實測分布極度兩極，0.1 只擋明顯不相干的；分布會記進 `askai_response_history`，不對就改。
- 開關程式預設 off、檔案 on：預設要「關掉也安全」；使用者已定案要做。

**重算向量計畫（RG-Q5 定案；10-26 晚獨立審查後改版；重算工作是新檔，等使用者核准）**
- 現況：向量是 LlamaIndex 預設 MetadataMode.EMBED 算的，送去算的文字是「message_id: …\nauthor_id: …\nchannel_id: …\ntimestamp: …\ndoc_type: discord_chat\n\n內文」（`_node_content.excluded_embed_metadata_keys` 為空）；查詢端只嵌純問句。實測吞吐（閒置時、經 GPU 閘門、平均 19 字）：batch 32／64／128 → 55／85／91 則/秒，全表約 68 分鐘純算向量；llama-index 的 `embed_batch_size` 預設 10，一批 64 其實是 7 次 HTTP，要設 `embed_batch_size = batch`。pgvector 容器 `/dev/shm` 只有 64 MB（compose 沒設 shm_size）、`lock_timeout = 0`、`max_parallel_maintenance_workers = 2`、統計過期（reltuples 273,890 對實際 345k）。
- 審查確認安全的部分：寫入端設 `excluded_embed_metadata_keys` 後 `get_content(EMBED)` 就是 `text` 本身、`_node_content` 序列化一致、`PGVectorStore.add` 只插明確欄位；影子欄＋RENAME 與 llama-index-vector-stores-postgres 0.9.0 相容（ORM 只選明確欄位、建表 checkfirst 不會 ALTER）；索引跟著欄位 RENAME 走。
- 步驟（改版）：
  ①寫入端：`store_chat._chat_node` 的 TextNode 設 `excluded_embed_metadata_keys`＝五個 metadata 鍵（backfill 同一條路）。**部署時機二選一**：跟切換一起（RENAME 後立刻重啟）→ 中間幾列的 NULL 由切換交易補；或先部署但基線要在重啟前先量完（否則現用欄位混兩種格式、基線被污染）。建議：跟切換一起。
  ②評估基線（切換前一定要有）：先用 v1（現狀）跑 30 題；`search_chat` 加只給評估用的 `embedding_column` 參數（只允許英數底線、預設 embedding），影子欄填好後同題對 v2 跑一次比對；試算的列依評估題牽涉的 message_id／頻道挑，不是「最新 2,000 則」。同時記兩個欄位 survivors 距離的 p10／p50／p90，給插話回憶重新校準 `callback_max_distance`（0.50）／`callback_target_max_distance`（0.70）——它們是對著帶 metadata 的窄帶距離調的，只嵌內文後距離分布會整個改變，地板要跟切換一起改，切換後幾天開著 `callback_debug` 看。
  ③影子欄：`SET lock_timeout = '3s'; ALTER TABLE data_discord_messages_index ADD COLUMN IF NOT EXISTS embedding_v2 vector(1024);`（不帶 DEFAULT，拿到鎖瞬間完成；拿不到就重試；避開 04:00～07:30 與每 5 分鐘的 flush）。
  ④重算工作（**已寫好** `llm/storage/chat_reembed.py`，影子欄由它第一次執行時 `ADD COLUMN IF NOT EXISTS`，所以③不必另外下）：`python -m llm.storage.chat_reembed [--limit N] [--batch 64] [--column embedding_v2] [--dry-run]` 在 discord-bot 容器跑；keyset 分頁 `WHERE id < %s AND {column} IS NULL ORDER BY id DESC`（走 pkey，新的先做）；每批 `gpu_exclusive_sync(max_wait_seconds=1800)`，`GpuBusy` 就睡 30 秒再試、**永遠不硬闖**（預設不給 max_wait 時等滿 15 分鐘會照常打模型，和 bot 同時用顯示卡＝10-08 斷線那種情況）；送去算的字串就是 `text` 原樣（不 strip、不正規化、不加 Instruct 前綴，否則和新寫入的列在兩個向量空間）；寫回 `execute_values(…, template="(%s, %s::vector)")` 的 `UPDATE … FROM (VALUES …)`，**每批 commit**；非 unreachable 的錯改逐筆重試，仍失敗的列記 log 並 `SET embedding_v2 = embedding`（沿用舊向量、保證不是 NULL）後繼續，keyset 無論成敗都前進；unreachable 才停。正式跑之前：挑一則最近的訊息分別用工作與 `_chat_node` 路徑各算一次，餘弦距離要是 0；在 bot 有人用的時候先量 5 分鐘吞吐再決定白天還是晚上跑；不在 04:00～07:30 跑。
  ⑤建索引（做完後、CONCURRENTLY，服務中可做；挑沒人用的時段、旁邊開 free -m）：同一條 psql 連線分開下 `SET maintenance_work_mem = '2500MB'; SET max_parallel_maintenance_workers = 0;` 再 `CREATE INDEX CONCURRENTLY discord_messages_idx_hnsw ON data_discord_messages_index USING hnsw (embedding_v2 vector_cosine_ops);`（**不能**用單一 `-c "SET…; CREATE INDEX CONCURRENTLY…"`：會包成一個交易而失敗；**序列建圖**才不經 DSM——平行建圖會把 1.6～1.8 GB 的圖塞進 /dev/shm，64 MB 直接 `No space left on device`；要平行就在 compose 給 pgvector 加 `shm_size: 3g` 並重建容器）。圖估 1.6～1.8 GB、主機可用約 4.1 GB、swap 已用 1.1 GB：超出 maintenance_work_mem 會退成磁碟建圖（小時級）、吃到 2.5～3 GB 有被 OOM 砍掉 backend 的風險（整個 cluster 重啟、CONCURRENTLY 失敗留 INVALID 索引要 `DROP INDEX CONCURRENTLY`）。省一半記憶體與磁碟的選項：halfvec 表達式索引 `USING hnsw ((embedding_v2::halfvec(1024)) halfvec_cosine_ops)`（建圖約 0.9 GB、索引約 0.8 GB），但 `search_chat` 的 ORDER BY 要改 `embedding::halfvec(1024) <=> %s::halfvec(1024)`。建完查 `pg_index.indisvalid`，並 `ANALYZE data_discord_messages_index`。　**10-27 06:38 已建好**（agent 經使用者授權執行；19 分鐘、2,211 MB、有效、已 ANALYZE）。　**索引 profile 之後的建法**：語法由 `CHAT_INDEX_PROFILES[profile].index_ddl(table)` 產生（`full` → `discord_messages_idx_hnsw`、`halfvec512` → `discord_messages_idx_hnsw_h512`）；換 profile 的順序固定是：建目標索引（並存）→ `indisvalid` 為 t、ANALYZE → 改 `switches.json` 的 `chat_vector_index` → EXPLAIN 或 60 題確認 → DROP 另一個；開關改早了只會退回全表掃描、不會錯；資料表全程不動、不重算。
  ⑥切換（一個交易，順序很重要）：`BEGIN; SET lock_timeout = '3s'; ALTER TABLE data_discord_messages_index RENAME COLUMN embedding TO embedding_v1;`（第一個 ALTER 先拿 ACCESS EXCLUSIVE，從這裡到 COMMIT 不會有 flush 插進來）→ `UPDATE data_discord_messages_index SET embedding_v2 = embedding_v1 WHERE embedding_v2 IS NULL;`（補尾巴擋不住最後幾分鐘的新列與永久失敗的列，這一步保證切換後沒有 NULL；幾十列、毫秒級、索引自動收進）→ `ALTER TABLE … RENAME COLUMN embedding_v2 TO embedding; COMMIT;` → 重啟 bot（寫入端）→ 用 `--column embedding --redo-copied` 再跑一次重算，把剛才沿用舊向量的幾列換成純文字格式（審查抓到：少了 `--redo-copied` 述詞恆假、會「做了 0 列」假裝成功，程式端現在會直接拒絕這個組合）。反駁驗證確認：bot 每 5 分鐘或滿 30 則 flush、編輯是 delete＋重插新 id，先 UPDATE 再 RENAME 中間還是有空隙，所以鎖要先拿。　補尾巴要帶 `--min-id <重算開始前最後一列的 id>`，不然 `embedding = embedding_v1` 會掃整張表（3.6 GB）。**10-27 09:30 已完成**（UPDATE 掃表 15 分鐘；下次這類切換用主鍵範圍補 NULL）。　補尾巴 10-27 10:27 完成（378 列）。
  ⑦切換後驗證：評估題再跑一次；對插話回憶（channel＋時間、target 模式再加 author）的查詢 `EXPLAIN (ANALYZE)` 看走哪個索引——HNSW 的 iterative_scan 最多掃 `hnsw.max_scan_tuples`（20,000）就停，小頻道或話少的人候選可能比今天的精確掃描少，不足就對那條路 `SET LOCAL hnsw.max_scan_tuples = 100000`。
  ⑧舊欄位：`DROP COLUMN embedding_v1` 只改 catalog，普通 VACUUM 回收不到那 1.8 GB（TOAST chunk 仍被活 tuple 引用）；真要回收只有 VACUUM FULL（整表 ACCESS EXCLUSIVE、重建含 HNSW 的全部索引、bot 停幾十分鐘）。**建議**：留著 embedding_v1 當回滾，磁碟還有 67 GB；或 DROP 後接受 1.8 GB 擱置。
- 膨脹預期（審查估）：UPDATE 不是 HOT（7 個索引、fillfactor 預設）→ heap 540 MB → 約 1.1 GB、索引 137 → 約 270 MB、TOAST 多 1.4 GB、WAL 約 2 GB、autovacuum 跑 4～5 次；可接受。原地覆寫 `embedding` 的膨脹完全一樣，只少掉 ADD／RENAME 與空間回收這題，但沒有瞬間回滾也不能 A/B——影子欄在真的會拿評估集比對時才值得（本計畫會）。
- 10-26 唯讀試算（2,000 列＋59 題答案）：答案距離 0.285→0.261、雜訊距離 0.647→0.692（差距 0.36→0.43）；小語料裡名次兩種格式都近乎第 1，名次收益要在全庫、改寫問句上才量得到。吞吐 98 則/秒。
- 規則式前文脈絡（v3）延後，等評估集再另開影子欄比較。寫資料庫的指令（ALTER、重算、CREATE INDEX、RENAME、DROP）都由使用者執行。

**待使用者判斷（RG-Q5～Q11，建議的先後；RG-Q5、Q6 已定案見上）**
- RG-Q5 要不要重算向量（metadata 不嵌＋規則式前文脈絡）：94.6% 的向量是「message_id: … author_id: … 內文」算的、短句被 id 稀釋、查詢端沒這串；另 5.4%（id < 19,424）是舊世代。重算一次兩件事一起消失，還能順便把「前一則誰說了什麼」用規則接在前面。成本：34 萬則 embedding、好幾天、佔 GPU；過渡期新舊混在一起檢索會變差。**建議**：先有評估集與基線，拿 2,000 則試算兩種格式比 Hit@k，有差才全量，維護時段分批。
- RG-Q6 HNSW 什麼時候建：現在每次插話回憶 4 秒、讀 23 GB buffer；建了降到幾十毫秒。索引約 1.5 GB、建 10～30 分鐘、要臨時 `SET maintenance_work_mem = '2GB'`。**建議**：先決定 RG-Q5，重算完再建（不然索引要跟著 34 萬次更新）；不重算就現在建：維護時段在 pgvector 容器 `CREATE INDEX CONCURRENTLY discord_messages_idx_hnsw ON data_discord_messages_index USING hnsw (embedding vector_cosine_ops)`；`search_chat` 要照 `services/search/vectors.py` 加 `SET LOCAL hnsw.ef_search`、`hnsw.iterative_scan = relaxed_order`（沒索引時設了無害，可先寫）。
- RG-Q7 從 doc 第二分頁勾 30 題；勾完再問跑分程式放哪（新檔）。兩條路分開量：全庫 `search_chat` 量 Hit@k；/askai 用 `askai_response_history` 的 100 則視窗重放。
- RG-Q8 reranker 門檻 0.1 留不留：只測了 9 則。不放心改 None（只重排不擋）；幾天後從 `retrieval_debug.reranked` 回報分布。
- RG-Q9 插話回憶候選池 25 → 50：折疊後最後會少於 25；放大在沒索引時不增加掃表成本，但排序與 debug log 多一倍。**建議**先不動，看幾天 debug log 的 survivors 數。
- RG-Q10 /askai 相關名額跨作者去重會讓「幾個人說 +1」這類計數題在視窗外少算。**建議**接受（保底 25 則全有）；不要就改成只折同作者，一行。
- RG-Q11 重啟：程式改動要重啟 discord-bot 才生效（避開 04:00～07:30）；開關檔已帶 `askai_rerank_mode`，舊版 bot 重啟前會記一次「不認得的開關」warning，其他開關不受影響。
- RG-Q12 **已核准並做好**（10-26 晚）：`llm/storage/chat_reembed.py`、`test/test_chat_reembed.py`；啟動：`docker exec -d discord-bot sh -c 'python -m llm.storage.chat_reembed --batch 64 > /logs/chat_reembed.log 2>&1'`，看進度 `docker exec discord-bot tail -3 /logs/chat_reembed.log`，剩幾列 `docker exec discord-bot python -m llm.storage.chat_reembed --dry-run`。
- RG-Q13 HNSW 建圖方式：序列建（不改 compose、約 10～30 分鐘）或在 compose 給 pgvector 加 `shm_size: 3g` 重建容器後平行建；要不要改用 halfvec 表達式索引（記憶體與磁碟減半、`search_chat` 的 ORDER BY 要跟著改）。建議：序列建、先不用 halfvec。　→ **10-27 已序列建好**（19 分鐘、2,211 MB）；建好後要讓規劃器用它還得拿掉 doc_type 篩選（見 06:1x 盤點）。
- RG-Q14 切換後 `embedding_v1` 留著當回滾還是 DROP（回收要 VACUUM FULL、bot 停幾十分鐘）。建議：留一個月再說。　→ **10-27 定案：留一個月，約 11-27 後 DROP 並 VACUUM FULL（bot 停幾十分鐘、避開 04:00～07:30）。**
- RG-Q15 `LemonadeReranker` 要不要搬到 `llm/client/`（技術層的模型客戶端；bot 就不必 import `services.search`，情報搜尋從那裡拿）。新檔與搬程式，等你點頭；不搬也能跑。
- RG-Q16 「誰常說 X」這類問題怎麼找（10-27 第二輪改版：使用者**不要引號觸發**，而且結果要看得出**是哪個頻道的誰**說的）。現象：整句問題算向量對到的是問句框架（「誰說的」「誰信」），X 平淡時目標句排到 25 名外（C 類 20→14；詞有特色的 14 題照樣第 1～6 名）。量過：只拿要找的那句話算向量 Hit@1 17/20、Hit@25 20/20；那句話 ILIKE 全庫按作者計數 Hit@1 18/20、Hit@3 20/20、0.3 秒/題、不用新索引。查證的現況：每一列的 author_id、channel_id、timestamp、message_id 都還在 `metadata_`，重算只是不再把它們混進向量；/askai 上下文每行是「名字#尾碼: 內容」（`context_retriever.py` 組行處）；`search_chat` 回傳有 author_id 但沒帶 channel_id（只拿來過濾，/askai 視窗本來就同一頻道）；折疊只折同一人同一句，不同人分開、幾個人都說過是訊號。/askai 今天只搜 100 則視窗、不搜全庫，所以這是新能力。選項（都不靠引號）：**A 工具（建議）**：給 /askai 一個「聊天紀錄搜尋」工具（參數：要找的句子、可選作者、可選頻道），模型自己從問句抽出要找的句子來呼叫；後端＝字面比對按（作者、頻道）計數＋最近幾則原文（頻道名、名字#尾碼、時間），字面 0 筆退到只嵌那句話的向量路；接法同 `WebSearchTools`：實作 `ToolRunner`、`run_with_intel(also=[…])`、`combine_runners`，開關一個。代價：多一輪模型呼叫（幾秒）、靠模型判斷何時查（情報搜尋的經驗：模型自己寫的查詢 Hit@5 71%、換字再查 79%）。**B 全庫混合檢索**：全庫多一條字面路再和向量路 `utils.rank_fusion` 合併。現有 GIN 是 `to_tsvector('english')`，中文整段當一個 token（「好了啦 又在裝」切成兩個 token、子字串對不到）；要子字串得加 pg_trgm 索引或兩字組 tsvector 欄位（DDL）；問句框架的字（誰、常說）也會對到，要靠 IDF／停用詞；工程最大、對所有問題都有一點幫助。**C 規則抽詞**：用「誰常說／口頭禪／誰說過」樣板剝掉框架。便宜但脆，和引號一樣是死規則，不建議。**D 查詢改寫**：檢索前先叫一次模型抽「要找的句子、人、頻道」。效果同 A 但每題都多一次呼叫，A 只在模型覺得需要時才查。不管選哪個都要補：`search_chat` 回傳加 channel_id、呈現加頻道名（指令層由 guild 對 id）。要定：選 A？放不放進這次？　**第三輪（使用者：「想要類似通用 AI、不想要 user 打一堆東西、有時只是印象搜尋或問題」，問是不是 B）**：A 與 B 使用者都只打一句自然語句，差別是誰決定去哪找、用什麼字找——A 由模型讀完問題自己決定要不要查、抽出要找的句子或主題（通用 AI 產品的搜尋就是這樣：模型改寫查詢再查，不是拿原句直接比對）；B 是每題都拿原句去全庫比對再塞進 prompt（傳統 RAG），弱點就是這次量到的：問法的字壓過內容、「誰常說」這種要計數的問題排名式檢索答不出來、中文字面路要建索引。印象搜尋（「之前好像有人說過…」）拿原句算向量本來就行（D 類 20/20、A 類 9/12），所以 A 的工具要有兩種模式：phrase（字面、按作者與頻道計數）與 topic（語意、回最近幾則含誰／哪個頻道／何時），模型自己挑；視窗內的 BM25＋向量照舊、不動。B-lite（每題順手跑一次全庫語意、塞幾行）等 HNSW 建好後若印象題仍漏再加，不是現在。建議仍為 A（兩種模式）。　**10-27 定案：A，工具兩種模式（phrase／topic）**。第四輪（使用者問「能不能在背後執行、使用者察覺不到」）→ 可以，而且不用另外做：/askai 的工具呼叫本來就在「🔄 AI 思考中」那則只有發問者看得到的訊息背後跑，公開回覆只有「問題／回答」兩段、沒有任何工具標記，情報與上網工具今天就是這樣；經過只記 log 與 `askai_response_history`。使用者能察覺的只有多等幾秒（建了 HNSW 後資料庫那段是毫秒，剩模型多一輪）。要補：工具規則加「回答裡不要說你查了紀錄」（模型有時會自己講「我查了一下」）；可選：第一輪模型呼叫時同步先跑一次 topic 搜尋當預取（省資料庫往返，不省模型那一輪，先不做）。**未答**：放進這次一起做，還是切換上線後再做。　→ **10-27 做好**：`llm/retrievers/chat_search.py`、開關 `askai_chat_search_mode` 已 on、待重啟（見盤點 15:0x～16:0x）。
- RG-Q18 索引放不進頁快取（使用者：「索引那麼吃記憶體嗎、VM 不可能給太多資源」）：2.2 GB 的大頭是索引裡每個節點都存一份完整向量（345k × 1024 維 × 4 bytes = 1.4 GB）加鄰居表與頁的填充，不是圖本身。縮小的路（可疊加）：①`halfvec` 表達式索引（16 位元浮點；`CREATE INDEX CONCURRENTLY … USING hnsw ((embedding::halfvec(1024)) halfvec_cosine_ops)`，`search_chat` 的 ORDER BY 改成同一個表達式；估 1.0～1.2 GB、召回幾乎不變、序列建約 20 分鐘、舊索引可並存再 DROP）；②降維：embedding 模型支援自訂輸出維度（截斷前 N 維再正規化），512 維＋halfvec 估 0.5～0.6 GB，表達式索引 `l2_normalize(subvector(embedding,1,512))::halfvec(512)`、查詢端同樣處理，**要先用 60 題評估集量召回**；③ef 參數化（插話 400）降冷讀量；④查 scraper 為什麼 CPU 89%、851 MB（它的檔案讀寫在擠快取）。**建議**：先 ①＋③（不用加記憶體、不改資料格式），② 另開評估再決定。不建議 shared_buffers 拉大（8 GB 會換頁）。　**11:2x 補**（使用者要記進文件：VM 沒資源、記憶體不大、在想辦法；參考說明「HNSW 須把向量與圖全放 RAM，業者改用 DiskANN 放 NVMe、RAM 只留快取、省 90%」）：說明文件新增一節「記憶體不夠時：HNSW 為什麼吃 RAM、DiskANN 是什麼、這台機器怎麼辦」。要點：HNSW 查詢是圖上隨機跳、每步讀一個節點的完整向量，RAM 幾微秒／磁碟幾毫秒差千倍，所以整張圖要常駐；DiskANN（Postgres 裡是 pgvectorscale 的 StreamingDiskANN）把圖建成每跳一步剛好讀一個 SSD 頁、RAM 只留壓縮向量導航，前提是 NVMe 的隨機讀（每秒十萬次），這台磁碟隨機讀只有每秒幾百次、資料 34.5 萬筆也遠不到那個規模，所以不走 DiskANN，改縮索引：halfvec（1.0～1.2 GB）→ 512 維＋halfvec（0.5～0.6 GB，評估跑中）→ 部分索引排除太短／純貼圖的列（再少 3～5 成；查詢要帶同一條件）→ 二元量化＋重排（0.1～0.15 GB，下一張牌）；ef 參數化降冷讀量。建議組合：512 維＋16 位元＋部分索引約 0.3～0.4 GB；召回掉太多就停在 1024 維＋16 位元＋部分索引。
- RG-Q20 聊天檢索的評估集（60 題）進版控（使用者 10-27：「之前也有題目，放一樣的地方跟格式可以嗎」）。現況：題目與跑分腳本只在 scratchpad（重開機就沒）、題目另抄在說明文件的表格。既有的情報搜尋評估在 `services/search/eval/`：`questions.json`（進 git，只有題目與答案 id）＋`private/questions_with_evidence.json`（不進 git）＋`evaluate.py`（search-mcp 容器跑）＋`reports/*.json`。**格式可以照抄**（qid／question／category／relevant，id 寫 `chat:<message_id>`；C 類多 `author` 與 `phrase` 兩個鍵，答案是「那個人說過含那句話的任一則」）。**位置建議不同資料夾**：① 它考的是聊天向量庫（`context_retriever.search_chat`），要在 discord-bot 容器跑，和情報搜尋的索引、容器都不同；② 題目本身就是群友的聊天內容與習慣（口頭禪、誰養貓、author id），repo 有公開鏡像，整份題目都該放 `private/`（gitignore），只有跑分程式進 git；情報搜尋那邊只有證據句是私密的，所以題目能進 git。建議：新資料夾 `src/llm/retrievers/eval/`＝`evaluate.py`（讀 `private/questions.json`、呼叫 `search_chat` top-25 不折疊、算 Hit@1／5／25 與中位名次、報告寫 `reports/<時間>-<名稱>.json`）＋`private/`（gitignore）＋`reports/`；另一個選項是塞進 `services/search/eval/` 共用 `evaluate.py` 加 `--target chat`，省一個資料夾但兩種評估的容器、索引、指標都不同、會把兩件事綁在一起，不建議。新檔要使用者點頭。　→ **10-27 使用者同意、已做**（見盤點 14:2x）。
- RG-Q21 聊天搜尋工具的字面模式要不要建 trigram 索引。現況：`text ILIKE '%句子%'` 是全表掃描（heap 約 660 MB），熱快取 0.3～0.5 秒、冷快取幾秒到十幾秒（已設 20 秒逾時，逾時回錯誤給模型）。選項：**A 建 `pg_trgm` GIN 索引（建議）**——`CREATE EXTENSION IF NOT EXISTS pg_trgm; CREATE INDEX CONCURRENTLY discord_messages_idx_text_trgm ON data_discord_messages_index USING gin (text gin_trgm_ops);`，擴充套件 pgvector 映像已內建；三個字以上的句子走索引變毫秒級，兩個字的（哇糙、全對）照樣掃描；估索引 100～200 MB、建幾分鐘、不停機，寫入時每則多一點索引成本。B 不建，看上線後的耗時再說（log 的 `askai 聊天搜尋` 有每次的毫秒數）。C 兩字句也要快：再加兩字組的 tsvector 欄，工程大、不建議。要定：A 還是 B？　→ **10-27 使用者「補」→ A，由 agent 建（CREATE EXTENSION pg_trgm＋CREATE INDEX CONCURRENTLY `discord_messages_idx_text_trgm`）；大小、耗時與 EXPLAIN 結果見盤點 16:xx～17:xx。**
- RG-Q22 聊天表的 metadata 要不要補 guild_id（使用者 10-27 問）。現況：`store_chat` 的 buffer 有 guild_id，`_make_node` 沒放進 metadata，全表 34.6 萬列（含今天新寫的）都沒有。選項：**A 只改寫入端（建議）**——`_make_node` 多放一個鍵、測試補一條，之後的新列帶 guild_id，舊列維持 NULL；多伺服器那天用 `guild_id = X OR guild_id IS NULL` 就分得開，不回填。B 現在回填——UPDATE 全表 jsonb，每列重寫、7 個索引跟著長新項目、要 VACUUM，估比早上那次 15 分鐘的 UPDATE 久，今天沒有任何查詢用它。C 不動。要定：A 或 C？　→ **10-27 使用者「做」→ A 已做**：`store_chat._make_node` 的 metadata 多放 `guild_id`（`item.get("guild_id") or ""`，`excluded_embed_metadata_keys` 本來就是整份 metadata，所以不進向量）；`test_chat_persist_retry` +1（帶 guild_id、沒給寫空白、不進向量），突變 1 刀紅；舊列不回填。
- RG-Q23 聊天搜尋工具要能回答「誰最常欺負／嘲笑／罵某人」這類行為題（使用者 10-27：現在只會數提到名字的次數，變成統計機器）。現象：「欺負」沒有字面關鍵字，模型用 phrase 查名字「阿喵」拿到 2,340 筆提到的次數再從例句挑；topic 只回最近 8 則、排不出誰最多。**建議**：①`topic_search` 多撈到 100 則、距離上限（例 0.5）、回傳每人幾句的統計＋例句（「在最像的句子裡誰出現最多」）；②規則檔：行為、態度、評價類用 topic 並把行為描述寫進 query（「嘲笑阿喵 阿喵好廢」），phrase 只找一字不差的句子，用 phrase 查名字要講明是提到的次數；③選配 `contains` 參數（`search_chat` 加 ILIKE 條件）限定句子含某個詞；④之後可加一層 reranker 判「這句是不是在欺負」（前 100 句約 5 秒）。限制：向量抓的是主題不是態度，含蓄的欺負會漏。要定：做 ①②③？　→ **10-27 使用者「做」→ ①②③ 已做**（見盤點 22:xx）；④ reranker 判態度等看過效果再說。
- RG-Q24 embedding 後端回 5xx 時聊天寫入該不該略過（10-27 事故：Lemonade 的 embedding 裝置掉了 4 小時，639 則被當「訊息本身有問題」略過，靠 14 天內的補寫救回）。現況：`store_chat` 只把「連不上、逾時」（`is_unreachable`）當後端問題而放回 buffer，HTTP 500 當單則錯誤略過。選項：**A（建議）** 同一輪 flush 連續幾則都是 5xx 就當後端壞了：剩下的放回 buffer、停這一輪（和連不上同一條路），並記 ERROR 一次（現在是每則一行 WARNING，4 小時刷了 639 行沒人看到）；B 再加自動修復：連續 5xx 時用 admin API 卸載再載入 embedding 模型一次（這次就是這樣修好的），還是壞就走 A；C 維持現狀，靠補寫。要定：A 還是 A＋B？　**第二輪（23:0x，查過現有自癒後重擬）**：現有的 `_try_heal_lemonade_backend` 只認「network_error 信封」。建議三件一起：**A′ 擴大自癒的觸發**——5xx 的 body 帶後端本身壞掉的訊號（`ErrorDeviceLost`、`decode() failed`、`vk::`、`CUDA error`）時也走同一個重載（沿用 60 秒冷卻、`save_options=False`），再加每個模型每小時最多 3 次的上限，超過就停、記 ERROR；不認得的 5xx 不重載（可能是請求本身的問題）。**B′ 寫入端**——同一輪 flush 裡遇到 5xx 就當後端問題：剩下的放回 buffer、停這輪，記一次 ERROR（不是每則一行 WARNING），補寫仍是保底。**C′ 看得見**——自癒成功、放棄時各私訊管理員一行（`utils.dm_notifier`），「一天到晚重啟」就看得到；常發生代表那張卡或驅動有問題，要從根本修，不是靠重載。不做：從 bot 重啟整個 Lemonade 行程（碰不到 Windows，也不需要——重載模型就是重開那顆後端行程）。安全邊界：只重載壞掉的那顆模型、有冷卻與上限、不覆寫 recipe options、主模型正在生成時不主動重載（wedge 代表它已經死了才算）。要定：A′＋B′＋C′？　→ **10-27 使用者「做」→ 已做**（見盤點 23:xx）。


**驗證**：新測試 `test/test_rag_collapse.py` 16 個（守的底線寫在檔頭）；突變 9 處（折疊、貼圖閘、min_chars、雜訊閘、BM25 折疊、重複標記、分數門檻、開關接線、重複跳過）全部變紅；守衛新規則故意加一段手刻判斷會紅。完整測試（容器）1,753 個：第三次全綠（OK，skipped=2）。前兩次各 1 紅，都是同一件事：`test_import_resolution` 把新測試裡 `logging.getLogger("test.rag_collapse")` 的字串當成模組路徑，改成 `__name__`。審查修正後：`test_rag_collapse` 23 個、突變再做 9 處（視窗折疊、代表取最新、非有限分數、ef_search 上限、連結＋預覽、純標點、照距離排、閘門、空鍵）全紅，完整測試第四次 1,762 個全綠（skipped=2）；補上「向量路查全部 id、換成代表」後突變 1 處紅、第五次 1,763 個全綠；再補「副本佔名額就多撈副本數」後 `test_rag_collapse` 25 個綠、完整測試第六次 1763 個：OK (skipped=2)。

**快照**（做法見本機 `doc/snapshot_commits.md`；scratchpad 會消失，id 記在這裡）：
- 05-hermes-proxy `ae6810ce35ff5b8b8cd72667f033cb9116da11ce`：Hermes 代理（notify_server 的 /v1、`services/llm_proxy.py`、`sys_settings/hermes_settings.py`、`http_client` 的 raw／stream、`ensure_model_loaded`、主模型 ctx 65536、`test_llm_proxy.py`、AGENTS 共用元件列）。訊息：`feat: let Hermes reach the GPU only through the bot's /v1 endpoint`；body：notify_server gains /v1/models and /v1/chat/completions behind a Bearer key (services.llm_proxy.LlmProxy)／proxy takes the GPU gate per request, clamps max_tokens, streams SSE with lease renewal, logs usage as feature=hermes／http_client gains chat_completion_raw/chat_completion_stream; llm_service exposes ensure_model_loaded／HermesSettings holds the key and proxy limits; the main model context grows to 65536 so Hermes accepts it／tests cover auth, allowlist, busy/unreachable mapping, streaming and the real gate owner。
- 06-rag-retrieval-quality `35c98daafd292154352633e791cd6b088d1d435c`（審查修正後重封四次；舊的 `547901e6…`、`30735c6b…`、`8bb9a92d…`、`7a238005…` 作廢；最後一次加的是重排包成獨立 task 與租約 240 秒）：本區「做了什麼」1～4 項＋審查後的修正＋HNSW 查詢設定＋守衛規則＋AGENTS 兩列。訊息：`feat(rag): collapse repeated lines, gate noise and rerank the /askai relevant picks`；body：/askai collapses the window to the latest copy per author and normalised text (tokenization.dedup_key) before BM25 and the vector route, so both routes vote for the same message; search_chat over-fetches and collapses the same way for the ambient recall, keeping the newest copy with a repeat_count, and filters min_chars in SQL／is_emoji_or_symbol_only also recognises the stored ":描述:" and "[貼圖：…]" forms and punctuation-only text; is_link_only moves next to it, ignores the stored "[預覽：…]" tail, and ambient reuses both／/askai hands the fused candidates to the intel-search LemonadeReranker behind the askai_rerank_mode switch inside the bot's async GPU gate, drops non-finite scores and scores under rerank_min_score, and falls back to the fused order on any failure／search_chat sets hnsw.ef_search (capped at 1000) and iterative_scan before each query and sorts by distance itself; ambient recall marks "同一人說過 N 次"／a shared-convention rule guards hand-rolled link-only checks; tests cover collapse, gates, reranking, the gate fallback and the HNSW settings。
- 07-chat-reembed `cba34391904ed29e8d01a835149f7ee85e5667ca`（第二輪審查修正後重封兩次；舊的 d5c6a8ea…、42092170… 作廢；含閘門「給了上限永不硬闖」的修正）：重算工作 `llm/storage/chat_reembed.py`＋`test/test_chat_reembed.py`、寫入端只嵌內文（`_chat_node` 的 excluded_embed_metadata_keys）、`search_chat` 評估用 `embedding_column`、分層登記。訊息：`feat(rag): add the chat re-embedding job and embed only the text of new rows`；body：llm.storage.chat_reembed recomputes every row's vector from the stored text into a shadow column, newest first, one committed batch at a time, resumable from the rows still NULL／each batch takes the cross-process GPU gate with a wait limit, sleeps when the GPU stays busy, pauses after releasing so the bot goes first, and waits out the 04:00-07:30 maintenance window／a row the backend cannot embed keeps its old vector and is logged; an unreachable backend stops the run; --self-check confirms the job embeds exactly what store_chat would／store_chat excludes metadata from the embedded text so new rows match the recomputed format; search_chat accepts an evaluation-only embedding_column／tests cover paging, commits, fallbacks, the busy gate, the maintenance window, dry-run and column validation。
- 08-hermes-proxy-fixes `43fdcdba36b343134f81a255b4075ef0b2b6d80d`：第二輪審查抓到的 Hermes 代理修正（信封、n_predict 繞過、非 ASCII 金鑰、SSE 空行、上游 401、本文上限只放大 /v1、租約、.env.template 的 LLM_TIMEOUT 300）。訊息：`fix(hermes): close the proxy gaps found in review`；body：chat_completion_raw unwraps Lemonade's "200 + error" envelope, heals a wedged backend once and reports it as unreachable so the proxy answers 503／the token cap also covers n_predict and max_completion_tokens, which llama.cpp would otherwise let override max_tokens／bearer and notify secrets are compared as bytes, so a non-ASCII header is a 401 instead of a 500／an upstream 401/403 becomes 502 upstream_auth, the lease is renewed once the model is loaded, and a mid-stream error always starts a new SSE event／only the /v1 endpoint accepts large bodies; /notify keeps aiohttp's default limit; LLM_TIMEOUT in the template is long enough for a cold 64k prompt。
- 09-hnsw-query-fixes `0bd35e6c1b3c286ada0ac19f67f51adbfc935bbf`（重封一次；第一版 `dcbc2f3f…` 只有 doc_type 那段，作廢）：`search_chat` 專用聊天表不帶 doc_type 篩選（規劃器才會走 HNSW）、設定層 `chat_table_is_shared()`、全庫搜尋 `hnsw.ef_search` 開到上限 1000（`_FULL_CORPUS_EF_SEARCH`，窗內重排維持原公式）、`test_rag_collapse` 加 4 個測試。訊息：`fix(rag): make the chat search actually use the HNSW index`；body：drop the doc_type filter on the dedicated chat table (the JSON expression has no statistics, so the planner assumed 0.5% selectivity and chose a 105 s parallel seq scan); keep the filter only when another source shares the table; open ef_search to 1000 for full-corpus searches because clusters of identical vectors (one line repeated dozens of times) are skipped at 200 (0 of 72 rows) and found at 1000 (70 of 72) for about 20 ms more when warm; window reranking keeps the message_id btree path.
- 10-reembed-min-id `1df27777269f4d58a4830a0c11638db34530bd1b`（累積：含 09）：`chat_reembed` 加 `--min-id`（count 與每批查詢帶 `id > %s`）、`test_chat_reembed` 加 2 個測試。訊息：`fix(rag): let the re-embedding job limit the copied-row redo to an id range`；body：the copied-row predicate compares both vector columns and detoasts 3.6 GB without an id floor; the rows copied at the switch are all newer than the original run, so an id floor walks the primary key and finishes in seconds.
- 11-chat-index-profile `3d99ff3bedab5a6c570c1a8738edfafe7b147c48`（累積：含 09、10；另含 `lemonade_gate` 的 GpuBusy 改 `raise … from None`，是 lint 修正）：`pgvector_settings` 的 `ChatIndexProfile`／`CHAT_INDEX_PROFILES`、開關 `chat_vector_index`（switches.py＋switches.json）、`search_chat` 照 profile 組 SQL、`test_rag_collapse` 加 2 個測試。訊息：`feat(rag): add index profiles so the chat search can run on a 512-dim halfvec HNSW index`。
- commit 順序：05 → 06 → 07 → 08（各 `git read-tree <tree>` + `git commit -F <msg>`），然後字典 `chore(settings)`、交接檔 `docs`。不進版控：`src/test/integration/it_comfyui_image.py`（未追蹤的整合測試，等使用者決定）。
- 字典（emoji、sticker）照慣例另一個 `chore(settings)` commit；交接檔與 AGENTS 的文件部分另一個 docs commit。

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
  - **第五輪（10-17 16:5x）全部定案（使用者：「先前幾輪不是都已經講過作法了」，照講過的作法做、不再問）**：KN-Q5b＝B（第一週完全不上網，只記想查什麼與名字檢查判定，週末 Claude 離線重查看品質）；KN-Q8 做（排在 c2＋c8 之後）；KN-Q9＝B；KN-Q10＝B；KN-Q11 五個新檔與開關全部開。
  - **第一版已做好（10-17，等 commit 與重啟；實作細節在最後盤點紀錄 10-17 18:xx 那筆）。記錄週怎麼看**：`grep 'ambient 查詢' logs/discord_bot.log`——每行 `trace= mode=dry_run tool=search|web_search query='…' 判定=recorded|blocked:群友名字|blocked:識別碼|second_call|quota|… 耗時=`；同一個 trace 的插話結果看 `ambient 生成`（有 `search=dry_run tools=N`）與之後的 pass／reply 行。週末要算：每天想查幾次、查了什麼（recorded 的查詢字拿去 127.0.0.1:8888 與 `docker exec search-mcp` 離線重查看品質、有沒有不當內容）、名字檢查擋了幾次與擋對不對、[PASS] 比例有沒有變、有查的那次多幾秒（同 trace 的 llm_usage 加總）。看完才決定全開＝第二版：開關加 `on`、查到的存筆記（KN-Q3／KN-Q10）、淡出、成人內容過濾；/askai 要不要接名字檢查另談。
  - **記錄週結果（10-18 上線～10-27 看，10 天）**：`ambient 查詢` 68 行、66 次插話判斷想查（每天 1～12 次，離每天 30 次上限很遠）；工具 search 39／web_search 29；判定 recorded 64、blocked:群友名字 1（「穗穗 一野 梗」）、blocked:識別碼 1（PTT 文章代號）、second_call 2（模型想連查兩次，第二次被「只能查一次」擋下）。查的東西：遊戲名詞、配隊、公告（「鳴潮 歐洲區 停登 維修」「殘星會 海德拉 新角色」）、電競與新聞時事（颱風停班、台積電協力廠商）、網路梗（「朋友費」「覽鳥公家拉」）；沒有不當內容。漏網：3 次把群友貼的 YouTube 影片 id 拿去查（`14Ja2o5Exrc youtube` 這類，公開連結、隱私沒事，但查 id 多半查不到東西）、1 次「immuking YouTube 頻道」可能是群友的頻道名。拿到記錄模式說明後：66 次裡 19 次仍開口（1 次是被 @）、2 次模型逾時、其餘 45 次沒有開口紀錄（[PASS] 不記 INFO）。**結論：記錄週看完，沒有擋全開的問題；第二版（開關加 `on`、查到的存筆記、淡出、成人內容過濾、識別碼規則加 YouTube id）排在 RAG 收尾之後，等使用者排優先序。**
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

- **新聞檢索（SearXNG）**：google 系、yahoo、brave、qwant、startpage 已停用（`config/searxng/settings.yml` `disabled: true`）；news 路由用 week、不用 day；明確指定 engines 會繞過 disabled，`default_engines` 要同步改。

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
- **2026-10-19 新發現（未修、未查因）**：修正上線後重連那半有效（10-16 14:09 之後 10 次斷線都在 0.6～2.2 秒內由 discord.py 自己接回），斷點續播卻會卡住：10-16 15:43 第一次斷線後，播放器把歌記成被打斷、要從第 122 秒續播，但 `voice_client` 一直回報還在播，於是每約 2.5 秒「voice_client 仍在播放，將歌曲排回稍後重試」一次，卡到 10-18 02:40 停機（約 35 小時、`discord_bot.log.1` 30,609 行加 `discord_bot.log` 16,735 行 WARNING），期間沒播別首。10-18 重啟後沒再出現（10-19 中午正常在播），`player.py` 之後沒改過，下次語音斷線很可能再卡。排在面試之後查。

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
