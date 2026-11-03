# AGENTS.md

<!-- 維護者注意：每個 Claude Code session（v2.1.277 以上）都會自動載入本檔，其他 AI 工具也會讀。
     repo 裡一旦出現 CLAUDE.md 或 CLAUDE.local.md，Claude Code 就改讀那個檔、不再讀本檔；
     需要 Claude 專用設定時，用內容只有 `@AGENTS.md` 的 CLAUDE.md 匯入本檔。
     目標 200 行以內；現況、決定、待辦寫在 AI_HANDOFF_AND_TODO.md，不寫在這裡。 -->

鳴潮社群「漂泊者觀星台」的 Discord bot：官網／FB／PTT／巴哈／Telegram 轉發、AI 插話與 /askai、人格萃取、週期活動提醒、點歌。
Python / asyncio / discord.py / Telethon / asyncpg；程式在 `src/`，跑在 docker：`discord-bot`、`telegram-scraper`、`scraper`、`pgvector`。

## 開工

1. 讀 `AI_HANDOFF_AND_TODO.md` 的「現況摘要」與這次任務相關的區塊（用標題或 `@meta id` 找，不必整份讀）。
2. `git status`：有不是你改的檔案，代表另一個 agent 正在做，先避開那些檔案；需要動到時先告訴使用者。
3. 要寫的東西先對照下方「共用元件」，並 grep 同類做法的**所有**實作。已經有兩份以上，就先抽成共用元件（放 `src/utils/`，只抽機制、長相留給呼叫端），再接新功能。現有程式裡找到的重複（同一套流程寫兩份、同一條規則散在幾處）也一樣要收，排進順序做；「沿用現有架構、最小修改」管的是收的時候不另起一套分層，不是不收的理由。

## 收工（三項都做到才算完成）

- 容器內完整測試全綠（主機沒有 discord 套件）：
  `docker exec -w /app discord-bot python -m unittest discover -s test -t . -p 'test_*.py'`
  （同 `make test`；啟動 gate 只跑 `src/test/gate.py` 列的守衛、import 解析與設定載入，新的守衛要加進那張清單；lint 與型別檢查 `make lint`、`make typecheck`，工具在 `requirements-dev.txt`）
  新增的測試要故意改壞一次程式，確認它會紅。
- 回寫 `AI_HANDOFF_AND_TODO.md`：已定案的決定與理由、**還沒定案的問題（選項＋建議）**、狀態、盤點紀錄。討論或 grill 的**每一輪**都回寫，不只定案時。寫法規則在該檔開頭。
- 等使用者明說才 commit。訊息用英文 conventional commits，body 3～5 點 `- ` 條列，不加 Co-Authored-By。

追查過去的決定、找已完成或過時的項目：`TODO-completed.md`（開頭有依日期的索引）。

## 與使用者溝通

- 所有給使用者看的文字（含工具說明）用繁體中文，不夾日文；commit 訊息例外。
- 解釋方案時，先一句話講機制本質，再列要改哪幾處；流程圖、坑、成本等使用者問了再展開。
- 討論時給完整架構、標明本輪改了哪些共識，最後整體確認（已定案／未定案／下一步）。
- 問題一次提出一整組、每題附上建議，但每輪控制在人能專注讀完的量：只談一個主題、約 3～5 題，其餘排到下一輪。

## 禁止未經確認刪除/覆寫使用者資料檔（高嚴重性）

1. **禁止**在未取得使用者明確同意前，執行任何可能刪除、清空、覆寫資料檔的操作。
2. 以下一律視為「高風險資料」：
   - bot 執行時寫的檔（`src/settings/runtime/*.json`：透過 Discord 設的值與它自己的紀錄——面板、點名、音樂、價格表、關鍵字監控；`src/services/sent_articles.db`）
   - 使用者設定檔（例：`src/config.json`）
   - 快取、歷史紀錄、session、資料庫檔（例：`src/scraper/articles.db`、pgvector 資料 `data/pgvector/`、Hermes 的設定與記憶 `data/hermes/`、`/logs` 下的歷史紀錄與備份、Telegram session）
3. 如需修改高風險資料檔，必須先說明風險與影響、提供備份／回復方案、取得使用者同意。
4. 若發生誤刪／誤覆寫，立即升級為高嚴重性事故：凍結 → 復原 → 記錄防再發。

## 資料與環境（硬規則）

- **Docker 只做唯讀查詢**：`ps`、`logs --since …`、`exec` 查詢、`inspect`。`compose up/down/restart/build`、`rm`、`rmi` 給指令讓使用者執行。例外：在 `search-mcp` 容器裡（`docker exec search-mcp …`）的情報搜尋指令可以直接執行——stdio 備用的 MCP server（`python -m llm.mcp_server`）、手動同步索引（`python -m services.search`）、搜尋評估（`python -m services.search.eval.evaluate`）與批次算向量（`python -m services.search.embed`），它們只寫自己的索引檔（容器內 `/search_data`，主機端 repo 根目錄 `cache/search-mcp/`）、評估報告 `services/search/eval/reports/` 與 pgvector 的 `data_search_chunks` 表（不碰其他表）。discord-bot 容器沒掛 `/search_data`，在那裡跑會失敗。聊天檢索的評估（`docker exec -w /app discord-bot python -m llm.retrievers.eval.evaluate --label 名稱`）也可以直接跑：只讀資料庫、只寫同資料夾的 `reports/`（不進版控），考卷在 `private/`。
- **每天 04:00～約 07:30 是維護時段**（人格萃取、persona agent），這段時間請使用者不要重啟 discord-bot。
- **bot 會長時間不重啟**：會變的外部資料（官方公告、設定）每次用到時重讀，不在啟動時只讀一次。
- 讀 `articles.db` 用 `mode=ro`：它是 WAL 模式，`immutable=1` 會看不到還在 WAL 裡的新資料。

## 共用元件（動手前查這張表）

沒查就自己寫一份，是本專案最常見的錯誤。下表由 `src/test/test_shared_conventions.py` 守衛（啟動 gate 會跑，違反就起不來）；合法例外寫在該檔各條規則的 `allowed`。新增共用元件時，在該檔 `RULES` 加一條。

| 需要做什麼 | 用這個 |
|---|---|
| 寫 log | `logging.getLogger(__name__)`；去向、等級、分類改 `src/settings/logging.json`；類別 logger 用 `get_article_monitor_logger()`／`get_llm_anomaly_logger()`；同容器另開的行程用 `configure_logging(force=True, root_handlers=[…])` 寫自己的檔（兩個行程寫同一個輪替檔會互相蓋掉） |
| 本機時區 | `sys_settings.time_settings.APP_TZ` |
| 遊戲公告的時間 | `services.events.event_time_parser.SERVER_TZ`（值同為 UTC+8，但語意不同，兩者不可合併） |
| 連 pgvector；LlamaIndex 向量庫 | `LLMServiceSettings().pgvector_connect()`／`pgvector_cursor()`；向量庫（聊天、成員資料、檢索）用 `pgvector_vector_store(table_name=…, embed_dim=…)`（借出連線前先確認活著，守衛擋直接 `from_params`） |
| 交易裡逐筆寫一批、壞的那筆只撤回那筆（保存點） | `sys_settings.llm_settings.pg_savepoint(cur, name)`（失敗只撤回這一段、例外照樣往外丟，略過或整批放棄由呼叫端決定；失敗後也 RELEASE；`rowcount` 要在區段裡讀；raw 備份的逐筆寫入、插話反應計數的名單查詢用它；守衛擋自己寫 SAVEPOINT） |
| 轉發來源同一篇內容的送出鎖（推送與輪詢、手動指令與排程撞在一起只送一份） | `services.relay.base_monitor.content_send_lock(content_type, content_id)`（鎖內再查一次已送紀錄才送；巴哈、公告、FB、IT 都用它） |
| 實體表名 | `HYBRID_RETRIEVAL_SETTINGS.chat_table()`／`.source_table(key)`／`.physical_table(name)`（含 identifier 消毒） |
| 讀會被手改、改了就要生效的檔案（prompt、字典、開關、config.json、LLM runtime 設定） | 機制只有一份：`utils.hot_files.read_text()`／`read_json()`／`read_parsed(path, parse=…)`（mtime 快取、壞檔沿用上次）。各檔的解析、驗證、寫入在呼叫端：config.json 走 `ChannelConfig.load_config`／`update_config`、開關走 `switches.current()`、LLM runtime 設定走 `sys_settings.llm_settings.load_llm_runtime_config`（已接熱讀檔，LLMService 也用它）、字典走 `emoji_dictionary`／`sticker_dictionary`；不要在 `hot_files` 加認得特定檔案的函式 |
| 清理聊天文字 | `llm.persona.personality_extractor._clean_text_for_extraction()` |
| 描述品質規則 | `persona_description_rules.txt`（各處讀同一個檔） |
| 人格素描的角色設定 | 疊在 `personality_extraction_prompt.json` 的 `system_prompt` 之上 |
| 發文到頻道 | `utils.discord_content.post_to_channel`（論壇／文字頻道自動分流、附件分批、失敗退純文字） |
| 把長文切成 Discord 放得下的多段 | `utils.discord_content.split_message`（不丟內容、優先換行與空白切、不切壞暴雷 `||`；上限常數 `DISCORD_MESSAGE_LIMIT`） |
| 回互動一段長度跟資料量走的純文字（一次性的長文字回覆） | `utils.utils.safe_send_interaction_text(interaction, text, ephemeral=)`（切段、第一則回應、其餘接續；embed 欄位 1024 字放不下清單，守衛擋自己寫 `for … in split_message(` 的送出迴圈）；主控台裡的清單（頻道、身分組、狀態詳細）不用它，改成分頁畫面一頁一頁翻（見「群主的管理操作放哪」） |
| 面板或主控台上換畫面（改互動所在的那一則訊息） | `utils.discord_content.edit_screen(interaction, view=…)`（還沒回應用回應改、回應過或 defer 了就改原訊息；新版版面只給 view，content／embed 明確清掉，舊 embed 訊息才換得過去；embed 版面板給 `embed=`；從按鈕或選單開的表單送出時也能這樣改原訊息；守衛擋自己寫 `edit_message(content=None, embed=None, view=`） |
| 面板上一次操作的錯誤邊界（做壞了要把畫面從「處理中」救回來） | `utils.discord_content.guarded_screen(interaction, label, run, rescue=, log=logger)`（做壞了記 ERROR、用 `rescue(notice)` 把畫面換回來並標「❌ 操作失敗（例外名）」；救援也改不了（訊息被刪）只記一行 WARNING；`log` 給呼叫端自己的 logger；守衛擋自己寫那段救援） |
| 清單分頁（頁碼寫在按鈕的 custom_id、選項每次照現況重列） | `utils.utils.paginate(items, page, per_page)` 回 (這一頁的項目, 夾回合法範圍的頁碼, 總頁數)；空清單算 1 頁；超過一頁才放上一頁／下一頁（只有一頁時兩顆的 custom_id 會撞） |
| 「一個設定對應幾個身分組」的畫面與寫法（點名的目標／排除、角色管理的 Trader／Moderator） | `utils.discord_members` 的 `role_name`／`roles_by_position`／`addable_role_ids`／`role_select_options`／`role_ids_changed`／`role_ids_after`（名稱、照高低排、還沒設定的、選單選項、送出時真的會變的、加進或拿掉之後的清單）；寫到哪個 key 由呼叫端決定 |
| 一則訊息上有哪些按鈕與選單的 custom_id（找殘留面板、舊主控台） | `utils.discord_content.message_custom_ids(message)`（新版版面的容器、區段、區段右邊的按鈕都走進去；`panel_bump` 與主控台清舊訊息都用它） |
| 把模型寫的文字送到 Discord（/askai 回答、插話、日記） | `utils.discord_content.send_model_text(send, text, mention_users=…)`（切段、一律不 @everyone／身分組／任何人，要 @ 的人由呼叫端指定、只放第一段；`send` 給 `channel.send`／`message.reply`／`interaction.followup.send`）；Bot 建構時的全域預設已擋 @everyone 與身分組，@ 人照舊放行，要 @ 身分組的地方自己明確指定 |
| 面板置底 | `utils.panel_bump.PanelBumper`（`bump`／`bump_safe`；有人講話就置底用 `request_bump`） |
| 已發送去重 | StateDB `sent_content`（`is_content_sent`／`mark_content_as_sent`） |
| 版本更新時刻 | `services.events.event_scheduler.VersionDateResolver`（`refresh()`、`update_starts()`；只看時間，不看版本號） |
| GPU 獨佔（產圖時卸載 LLM） | `llm.client.gpu_gate.gpu_exclusive(owner, lease_seconds)`（另開的行程、search-mcp 容器也一起排隊：跨行程鎖檔，跨容器靠 compose 把同一個主機目錄 `run/gpu_lock/` 掛成 `/gpu_lock` 並設 `LEMONADE_GPU_LOCK_PATH`）；沒有 event loop 的同步程式（情報搜尋的批次算向量、MCP）用 `gpu_exclusive_sync()`；等閘門要有上限的（探測、Hermes 轉送、/askai 重排）用 `wait_at_most(gate, seconds)`（只限制等、等不到丟 `GpuBusy`，拿到之後不整段限時，守衛擋自己寫 `enter_async_context(gate(...))`）；拿著閘門算 embedding 一律 `make_safe_llm_embedding(holding_gpu_gate=True)`（短逾時、不重試、排隊有上限，後端卡住時早點放鎖） |
| 判斷 LLM 後端連不上或逾時（該停手、晚點再試，不是請求本身的問題） | `llm.client.http_client.is_unreachable`；連同「後端有回應但回 5xx」一起算後端問題用 `is_backend_fault`（聊天寫入放回 buffer、embedding 不逐筆重試都看它）。送出失敗怎麼辦只有 `http_client.judge_failure` 一份；重載是後端專屬的事：`LlmHttpClient(admin=…)` 掛的 `BackendAdmin` 負責拆信封與重載，建 client 時用 `llm.client.backend_admin.admin_for(backend, host)` 決定（介面照能力定、實作照廠商各一個 class：Lemonade＝`lemonade_admin.LemonadeAdmin`、Ollama＝`ollama_admin.OllamaAdmin` 只有卸載、vLLM 回 None；`LLMService.release_model` 只看有沒有 admin，沒有廠商分支）。Lemonade 的管理 API（載入、卸載）與自癒都在 `LemonadeAdmin`（5xx 帶顯示卡裝置掉了的訊號就重開那顆模型＝unload 再 load——只送 load 對還活著、選項相同的模型是空操作；重開後看 health 的行程換了、再送最小請求真的算一次，都過了才算救回；每模型 60 秒冷卻、一小時最多 3 次，用完或第 3 次重開還是壞就放棄，放棄後不再自動重開；不看還剩幾次重試，不重試的呼叫端重開完不重送、照原錯誤丟出；拿著閘門的 embedding 重開逾時縮成 `gated_embed_timeout`）；重開失敗、重開了還是壞、放棄走 `utils.owner_alerts.emit`（私訊群主＋「重新偵測」按鈕，見下一列）、救回 `inform` 一行；錯誤裡後端自己講的那句話用 `http_client.backend_message`；群主按「重新偵測」＝`lemonade_admin.reset_cache()`＋`LLMService.probe(embedding=…)`（真的算一次、拿閘門、不重試；只看 health 不夠，裝置掉了 health 照樣 ready），兩顆模型各自照結果解除；放棄期間介面層每分鐘問 `LLMService.replaced_backends()`，行程換了（重啟 Lemonade）就自動重新偵測 |
| 要群主介入的狀況（私訊＋「重新偵測」按鈕、「機器人狀態」面板） | `utils.owner_alerts.emit(kind, key, text)`（任何執行緒可叫；同一把一小時只送一次、嚴重度升高（警告→要人介入）照送、解除後再壞再送）／`inform(kind, key, text)`（一行通知、順便解除）；每種狀況的重測與狀態用 `owner_alerts.register(kind, title=, retest=, status=)` 登記（狀態函式回字串＝綠、回 `Status(level, text)` 可標黃；只讀現況、不打網路，會連線的探測只在重測做）：模型後端在 `commands.owner_alert_commands` 的 `cog_load`，其餘八項（Discord 權限、scraper、網路搜尋、顯示卡閘門、資料庫、telegram-scraper、情報搜尋、設定）在 `commands.admin_status.register_kinds`；私訊上的按鈕是 `RetestButton`、面板是 `admin_status`（九項紅黃綠、每項重測、全部重測、看詳細、補跑 04:00 維護；新版版面）；私訊裡的文字不回（主控台只由 `/server_manager` 進，私訊對話留給之後的 AI 私聊；`discord_bot.on_message` 一開始就擋掉私訊）；守衛擋別處再寫 `notify_owner_*` |
| 群主的管理操作放哪（新的管理功能要有入口） | `commands.admin_console`：主控台是「一則訊息、幾個畫面」——`ACTIONS` 加一組（畫面代號、名稱、說明、按鈕文字）＋ `_SCREENS` 加一個畫面函式（收 interaction、guild、action、page，用 `edit_screen` 把主控台那一則換成你的畫面），主選單就多一列；畫面用 `screen_box(title, notice=, colour=)`＋`screen_view(box, *按鈕列)` 組、每個畫面都放 `back_button()`（回主控台）或回上一層、操作結果寫在標題下那一行（`notice=`）、要等幾秒的先切「處理中」（`busy=True` 按鈕全灰）再做；一次互動走 `guarded_screen`，做壞了換回主選單並標錯誤；按鈕是 `ConsoleButton(screen, action, page)`（DynamicItem，custom_id `console:<畫面>[:<動作>[:<頁碼>]]`，重啟後照樣能按）；入口只有 `/server_manager`（`/server_info` 直接開在伺服器資訊；伺服器裡只有本人看得到、私訊裡一般訊息並刪掉上一則主控台，只放群主）；功能本體留在各自的 cog，主控台用 `interaction.client.get_cog` 叫它們、要它們回「結果一句」（`resend_result`、`baha_sync_result`、`write_diary_now`、`start_persona_test`、`deliver_admin_panel`）不自己回訊息，不互相 import；別的模組畫的畫面（機器人狀態 `admin_status.render_status`、頻道綁定 `channel_panel.render`、角色管理 `management_commands.render_roles_home`）import 主控台拿 `back_button`／`screen_view`，主控台要畫它們時才載入；要輸入東西用 Modal（2.7.1 支援 `Label`＋`Select`），送出的互動照樣 `edit_screen` 改回主控台那一則；私訊裡需要伺服器用 `home_guild`；幽靈點名是另一則常駐面板（群主私訊，`RollCallCommands.deliver_admin_panel` 刪舊面板、記位置、回連結，主控台只在自己畫面上回那句；它的畫面是 embed＋按鈕，寫法同上：`render_*`／`_show`／`_guarded`） |
| 新版版面（LayoutView：Container、Section 帶按鈕、TextDisplay、Separator、ActionRow）的訊息 | 面板與主控台都用它；送出時只給 `view=`、不帶 content／embed（Discord 會拒）；改訊息一律 `utils.discord_content.edit_screen`（它會把 content／embed 明確清掉，舊的 embed 訊息才換得過去）；同一則訊息的 custom_id 不能重複（Discord 整則退件、錯誤看不出哪兩顆撞；`admin_console.screen_view` 組畫面時就擋，翻頁按鈕只在超過一頁時放）；整則最多 40 個元件、文字總長 4000；按鈕一律 `DynamicItem`（`is_persistent()` 只看頂層，內層忘了 custom_id 擋不到）；一列只能放一個選單；拿上面的文字（log、測試）用 `utils.discord_content.layout_text(view)` |
| 對外提供 OpenAI 相容的模型端點（Hermes 經 bot 用顯示卡） | `services.llm_proxy.LlmProxy`（掛在通知伺服器的 `/v1`，驗 `HERMES_API_KEY`、只放行 bot 正在用的模型、拿 GPU 閘門後原樣轉給 Lemonade；原樣送出用 `LlmHttpClient.chat_completion_raw`／`chat_completion_stream`，不重試）。**bot 呼叫 Hermes 時不可拿著 GPU 閘門**：Hermes 會回頭打這個端點要同一把鎖 |
| 讓模型先用工具查、再回答（每輪都照原本的思考設定、帶同一份工具清單，不查就只呼叫一次；查滿輪數的提醒文字與「要不要改用不帶工具的呼叫」由呼叫端決定） | `LLMService.generate_reply(tool_runner=…, tool_nudge=…, tools_plain_fallback=…)`（工具介面 `llm.client.tool_calls.ToolRunner`；/askai 查情報、插話的查詢都用它，不要再寫一份迴圈）；要給模型今天日期用 `today=`（放 user 段，不動 system 段的快取） |
| 工具呼叫的訊息格式（模型要呼叫工具的 assistant 訊息、`role: tool` 回覆、取工具名稱與解析參數） | `llm.client.tool_calls`（`assistant_message`／`tool_message`／`call_name_and_arguments`／`parse_arguments`；迴圈、預算、工具怎麼跑留給呼叫端。人格萃取 agent 與 /askai 情報搜尋共用） |
| 幾組工具一起交給同一個工具輪（例：遊戲情報＋網路搜尋） | `llm.client.tool_calls.combine_runners`（宣告照順序接、使用規則依序接、呼叫依名稱交給宣告它的那組；沒工具的連規則一起略過） |
| 新的 bot 指令 | 一律斜線 `@app_commands.command`；不用 `!` 前綴的 `@commands.command`（守衛擋：前綴指令是一般訊息，會被當聊天存進向量庫；Bot 的 `command_prefix` 只是必填參數，`process_commands` 已不呼叫）。對某則訊息操作的用右鍵選單 `app_commands.ContextMenu`（cog 裡不能用裝飾器：`cog_load` 建好掛上 `bot.tree`、`cog_unload` 拿掉；範例 `commands.telegram_quarantine_commands`）。bot 啟動只同步全域指令，手動註冊到單一伺服器的指令不會自動清掉，用完要自己刪 |
| 這個人能不能在這裡做這個操作（按鈕、指令）；誰是群主；私訊裡指的是哪個伺服器 | `utils.discord_members.require_access`（不行就自己回只有本人看得到的訊息、回 False，呼叫端直接 return；不帶參數＝要在伺服器裡；`allow_dm=True`＝私訊裡也放行、但只放群主（不管原本要求的是群主、管理員或哪個權限），管理主控台的指令與按鈕用）／`home_guild(interaction)`（私訊裡用 bot 唯一的伺服器；回 None 就回 `NO_HOME_GUILD` 那句）／`check_role`（只回是否）／`bot_owner_id`（`owner_only`／`admin_only`／`required_role`／`permission="manage_messages"` 這類 Discord 權限；不通過時自己回只有本人看得到的訊息；不用 `@app_commands.checks.has_permissions`，守衛擋：它擋下時回英文錯誤還記一筆 ERROR） |
| 選項可能超過 25 個的選單（分頁；單選或多選） | 私訊裡要列伺服器的頻道或身分組一律由 bot 自己列（Discord 原生頻道／身分組選單在私訊裡列不出東西）。面板與主控台上的選單是 DynamicItem、頁碼寫在 custom_id、選項每次照現況重列、切片用 `utils.utils.paginate`（每頁 `ITEMS_PER_PAGE`＝選單上限 25；頻道綁定面板的項目每頁 `ADMIN_CONSOLE_SETTINGS.bindings_page_size`）：點名面板的 `RollCallPickSelect`、頻道綁定的 `ChannelSelect`、角色管理的 `RoleSelect` 都這樣寫。`utils.utils.create_paginated_view(options, …, max_values=)` 靠閉包記住選項與頁碼，bot 重啟就失效，只給一次性的追問訊息（使用者指令那邊還在用） |
| 功能開關（開／關、off／dry_run／on） | 值寫在 `settings/switches.json`（手改、下一次用到就生效）；名稱、預設、允許的值定義在 `sys_settings.switches.Switches`，讀用 `switches.current()`；新開關只能放這裡（守衛擋，舊的改到再搬） |
| 專案裡檔案的位置（settings、settings/runtime、prompts、scraper 資料庫、static、config.json、log 與備份） | `sys_settings.paths`（`APP_ROOT`、`LOGS_DIR`、`SETTINGS_DIR`＝你手改、`RUNTIME_DIR`＝bot 寫、`PROMPTS_DIR`、`SCRAPER_DIR`、`STATIC_DIR`、`settings_file()`、`runtime_path()`、`prompt_file()`；config.json 用 `utils.utils.CONFIG_FILE`；SQLite 唯讀開用 `sqlite_readonly_uri(path)`，`articles.db` 的路徑用 `ARTICLES_DB`，守衛擋自己拼路徑或 `mode=ro`／`immutable`）；不寫死 `"/app/..."`、`"/logs/..."`、不用 `Path(__file__).parents[n]` 往上數、不用相對路徑（守衛擋；爬蟲容器例外） |
| bot 執行時寫的 JSON（`settings/runtime/*.json`：透過 Discord 設的值與它自己的紀錄——面板、點名、音樂、自介投稿、隔離 thread、關鍵字監控；整個資料夾不進版控） | `utils.runtime_file.load`／`save`／`update`（讀走熱讀檔、寫走安全寫入加備份；面板位置用 `panel_bump` 的 `load_runtime`／`update_runtime`）；不自己 `open`／`json.load`（守衛擋） |
| 賣家物品價格（`settings/runtime/item_prices.json`） | `services.community.item_prices`（`all_prices`／`user_prices`／`set_user_prices`） |
| 寫 `config.json` | `ChannelConfig.update_config(apply)`（重讀最新內容、只改這次的 key、安全寫入加備份）；讀 `load_config` 回複本、改檔即生效 |
| 綁頻道：登記一個功能、寫 config.json、綁定後動作、解除；頻道綁定面板 | 登記用 `settings/channel_registry.py` 的 `register_channel`；要先輸入一段文字再選頻道的（Telegram 路由）用 `register_custom(describe=, input=InputSpec(label, placeholder, pick_type, max_length, normalize))` 裝飾寫入函式 `apply(text, channel_id) -> 結果一句`；寫入只走 `channel_registry.apply(setting, bot=, guild=, channel=)`／`unbind(setting)`／表單類的 `apply_input`（守衛擋別處直接寫 `*_channel_id`）；目前綁哪裡 `bound_channel_id`／`telegram_routes`；畫面是 `commands.channel_panel.render(guild, page, notice=, busy=)`（主控台的「頻道設定」畫在主控台那一則上；新版版面：標題下一行頁碼與統計、依頻道型別分組、每項一行「名稱　頻道　說明」、每頁 `ADMIN_CONSOLE_SETTINGS.bindings_page_size` 項、選單只列本頁、「解除某一項」、回主控台）；選了一項換成選頻道的畫面（`render_channel_pick`：bot 自己列、超過 25 個分頁、回上一層）、解除換成 `render_unbind`、表單類先開 `InputModal` 再換成選頻道（輸入正規化後帶在 custom_id）；選了先切「處理中」再寫檔，結果寫在面板標題下那一行 |
| 取得 thread（封存的也拿得到）、解除封存 | `utils.discord_threads.fetch_thread(client, id, raise_errors=…)`／`reopen_thread`（封存的 thread 改不了、刪不了訊息；「找不到就清紀錄重建」的呼叫端用 `raise_errors=True`，只有真的不存在才回 None、5xx 往外丟；守衛擋自己 `fetch_channel`） |
| 取伺服器成員（快取偶爾漏人，要再問 API）；找能私訊的對象 | `utils.discord_members.resolve_member(guild, user_id)`／`resolve_user(bot, user_id, guild=)`（先查快取、沒有再 fetch；不在、沒權限、5xx 都回 None；守衛擋自己 `guild.fetch_member`，點名刻意只用 API 是例外） |
| 讀綁定的頻道 id（可能沒綁） | `ChannelConfig.get_configured_id(key)`（沒綁回 None，不必自己比 `DEFAULT_ID`） |
| 搜尋公告、官方 FB、PTT、巴哈的內容；讀全文（附推文、留言） | `services.search`（`SearchIndex.search`／`fetch`；索引從 `articles.db` 唯讀增量同步；用語、評估數字見 `AI_HANDOFF_AND_TODO.md` 的 `mcp-search-tools` 區塊）；MCP 殼是 `llm.mcp_server`，常駐在 compose 的 `search-mcp` 服務（背景同步與每日維護 `services.search.background`）；bot 端（discord-bot 沒掛索引）一律當 MCP 客戶端用 `llm.retrievers.intel`；/askai 重排相關聊天訊息只借 `services.search.rerank.HttpReranker`（打模型的客戶端，不碰索引；在 bot 行程裡要給它空的 gate、由 `context_retriever` 用 async 閘門排隊）（`run_with_intel` 依開關準備工具、交給回答流程並記經過，`also=` 帶其他一起給模型的工具；`prepare_intel_session`；每次工具呼叫各開短連線，見模組說明） |
| 搜這個伺服器的聊天紀錄給模型當工具（誰說過／誰常說某句話、之前有人提過嗎、誰最常欺負／稱讚某人；phrase 字面計數、topic 照意思找並附「最像的句子裡誰說了幾句」的統計、`contains` 鎖在含某個詞的句子；結果標頻道、名字#尾碼、時間） | `llm.retrievers.chat_search.ChatSearchTools`（/askai 開關 `askai_chat_search_mode`，細項 `AskAIChatSearchSettings`，規則 `settings/prompts/askai_chat_search_rules.txt`；成員名字、頻道名稱由指令層交進去，語意路走 `search_chat`）；聊天向量庫的語意搜尋本身只有 `context_retriever.search_chat`（`channel_id`／`author_id`／`text_contains` 篩選、`query_embedding=` 交進算好的向量、回傳帶 `channel_id`）；`text ILIKE` 的子字串樣式用 `context_retriever.ilike_pattern` |
| 插話判斷時先查一次（遊戲情報＋網路、每次 1 次、每天上限、名字檢查、記錄模式） | `llm.ambient.ambient_search`（`prepare` 回那組工具或 None、`AmbientSearchTools`；開關 `ambient_search_mode`、細項 `AmbientSearchSettings`；規則 `settings/prompts/ambient_search_rules.txt`） |
| 要送出網的查詢字是不是在指群友（名字、#尾碼、長數字、email） | `llm.persona.member_names.query_names_member(query, parts)`（名字片段用 `name_parts`；插話用 `ambient_search.name_parts_for` 拿全伺服器的） |
| 一則訊息有沒有可聊、可當回憶的文字（純表情、純貼圖、純連結） | `llm.preprocess.emoji_text_utils.is_emoji_or_symbol_only`／`is_link_only`（Discord 原文 `<:name:id>` 與向量庫存的 `:描述:`、`[貼圖：…]` 都認；插話的內容閘、插話回憶、/askai 相關名額都用它，守衛擋自己判斷「整則只有連結」的 `all(... .startswith("http...") ...)`） |
| 同一句話的折疊鍵（聊天檢索把同一人同一句折成一則） | `llm.preprocess.tokenization.dedup_key`（正規化後只留字母數字與中日韓文字；`search_chat`、BM25、/askai 相關名額共用，只認字面不判語意） |
| 每天最多做幾次的計數（換日歸零） | `utils.daily_quota.DailyQuota`（看圖補字典、插話查詢都用它；守衛擋自己用 `["", 0]` 記） |
| 網路搜尋（SearXNG；哪類題目用哪組引擎、窄路由結果太少換通用引擎補查） | `llm.retrievers.web.search_web`（路由用 `intent.classify_route`；直接呼叫 `fetch_web_results` 守衛擋）；給模型當工具用 `WebSearchTools`（/askai 開關 `askai_web_search_mode`：keyword 先查好塞進 prompt、tool 由模型和遊戲情報一起決定；工具模式的題目類型由模型選 `kind`，每種類型的引擎寫在 `tools._KINDS`）；SearXNG 的直接答案（匯率、天氣）在 `WebRetrievalOutcome.answers`；被擋的引擎自動暫避 |
| 官方公告、巴哈單一樓層的原文網址 | `services.source_urls`（`official_article_url`、`bahamut_floor_url`） |
| 聊天向量索引的形狀（查詢的距離表達式、查詢向量怎麼轉、建索引語法；整欄或前 512 維＋16 位元） | `sys_settings.pgvector_settings.CHAT_INDEX_PROFILES`（`expression`／`param_cast`／`query_literal`／`index_ddl`；用哪個由開關 `chat_vector_index` 決定，`search_chat` 照它組 SQL；三者要一字不差規劃器才會用索引，不要在別處自己拼 `<=>`） |
| 合併多份排名（關鍵字＋向量的混合檢索） | `utils.rank_fusion`（`rrf_score`／`fuse_rankings`；只看名次、不看各自的分數） |
| prompt 裡認人的錨點（名字#尾碼） | `llm.preprocess.person_anchor.label()`／`suffix()`（撞號自動加長；`refresh()` 由 `discord_bot` 在啟動與成員進出時呼叫） |
| 群友的名字（Discord 顯示名稱、伺服器暱稱、全域名稱＋自介／印象暱稱） | `llm.persona.member_names`（`member_names_from_guild`、`merge_names`、`names_member`、`name_map_lines`） |
| 查 X 貼文／給 AI 看貼文內容與縮圖 | `utils.link_fix.fetch_tweet`（syndication CDN）；給模型看用 `llm.preprocess.tweet_context.expand_tweets` |
| 讀寫自訂表情字典（`settings/emoji_dictionary.txt`） | `llm.preprocess.emoji_dictionary.entries()`；AI 補描述用 `fill()`（不覆寫人寫的描述） |
| 讀寫別的伺服器的貼圖描述（`settings/sticker_dictionary.txt`） | `llm.preprocess.sticker_dictionary.lookup()`／`add()`；本伺服器的貼圖描述在 Discord 上，走 `sticker_cache` |
| 沒描述的表情／貼圖讓 AI 看圖補字典 | `llm.preprocess.emoji_autofill.observe`（`on_message` 呼叫；設定 `EmojiAutofillSettings`） |
| 別的伺服器的表情／貼圖給 AI 看圖 | `llm.preprocess.external_emoji.external_emoji_context` |
| 被點名罵時的應對（模型判斷、按嘲諷表情）；最近罵過它的人 | `llm.ambient.ambient_insult`（模型在插話 prompt 裡輸出 `[INSULT]`；`is_marker`、`respond`、`grudges`；開關 `ambient_insult_mode`） |
| bot 與 telegram-scraper 都要用的定義（頻道識別正規化、媒體補圖時限） | `shared.telegram`（`src/shared/` 由 compose 唯讀掛進爬蟲容器；只能依賴標準庫） |
| Telegram 爬蟲下載媒體 | `telegram_scraper.media_download.download_with_stall_guard`（太久沒進度就取消；時限常數：補掃重試與補發通知 `MEDIA_RETRY_WINDOW`、新訊息圖沒到先不通知 `MEDIA_HOLD_NOTIFY`） |
| 下載網址上的圖給 vision 模型 | `llm.preprocess.vision_image.download_images`（失敗跳過、限張數與大小） |
| 本機的圖與影片給 vision 模型（縮圖、動圖與影片挑幀） | `llm.preprocess.vision_image.fit_for_vision`（縮到長邊上限、轉 JPEG）、`extract_key_frames`（動圖）、`video_key_frames`（影片）；挑幀規則只有 `select_key_frames` 一份 |
| 跑 ffmpeg 這類子行程 | `utils.media_probe.run_media_tool(cmd, timeout=…)`（逾時砍掉行程、回 `ToolResult`；守衛擋自己 `create_subprocess_exec`） |
| 讀影片長度 | `utils.media_probe.probe_duration`（ffprobe；失敗、逾時回 0） |
| 取模型回答的最後一行結論 | `llm.prompt.answer_line.final_line`（去思考區塊與「第二行：」這類照抄格式的前綴；prompt 讓模型先寫理由、最後一行才寫結論） |
| 改寫使用者也會手改的文字檔 | `utils.safe_write.replace_text`（暫存檔換名、每天第一次改寫前備份） |
| 解析使用者在視窗打的日期／時間（Discord 沒有日期選擇器） | `utils.user_dates.parse_user_date`／`parse_user_datetime`（全形、`/` `-` `.`、年月日都收；讀不懂回 None，訊息與規則留給呼叫端） |
| 背景任務（做完就結束的 fire-and-forget、該一直跑的迴圈、固定間隔做一件事） | `utils.background_tasks.spawn`（留參照、失敗記 ERROR、取消不算失敗）／`supervise`（掛了記 ERROR、間隔加倍重啟、取消才停）／`periodic(seconds, job, name=)`（定期寫入這類固定間隔的工作，失敗記 WARNING 繼續；要算下一個時刻的用 `run_due_loop`）；結果被丟掉的 `create_task` 守衛擋 |
| 定時排程（睡到下一個時刻、啟動時補做、出錯不中斷） | `utils.due_loop.run_due_loop`（tick 處理到期的事、回傳下一個時刻；到期項目途中變了就設 `wake` 讓它提早重算；週期提醒、點名、人格萃取、日記四份舊迴圈待搬） |
| 開交易 thread、領收、取消、封存（自由市場接單、商品購買） | `services.community.trade_service.TradeService`（`open_trade` 等；流程見根目錄 `TRADE_FLOW.md`） |
| 讀交易 thread（開單身分、有效的領收通知、交易按鈕、bot 的訊息） | `TradeService.read` → `TradeThreadLog`（一律讀完整串；交易與商品模組不自己翻歷史，守衛擋） |
| 新增一種交易來源（完成、取消時對來源的處理不同，例：商品貼文） | 實作 `trade_service.SourceKind`，用 `TradeService.add_source_kind` 登記（參考 `shop_service.ListingSource`） |

## 程式碼

- 註解用繁體中文，只寫「為什麼」；不寫具體模型名稱或規格（模型會一直換）。**不寫誰決定、哪天決定**（「使用者 10-03」只有當時在場的人懂）、**不寫里程碑或題號代碼**（M5、TR-Q40）、**不拿「見交接檔」代替理由**（讀程式的人看不到交接檔）：理由寫得下就寫在原地，寫不下就不寫；只在文件裡維護的數字、樣本，可以寫「記在哪個區塊」。commit 訊息同樣不寫代碼與出處，只寫改了什麼。
- 模組開頭的說明照這個格式（2026-10-13 起；新寫、搬動的模組一定照做，舊的碰到再改）：
  1. 一句話：這個模組做什麼。
  2. 架構定位：在哪一層、能依賴什麼；上層（誰呼叫，寫種類與例子）；下層（呼叫誰）。
  3. 介面：對外的函式各一行。
  4. 規則：呼叫端要遵守的約定、不做的事。
  5. 例外與決策：不收斂的例外、決策與一兩句理由寫在這裡；不要只寫「見交接檔」。經過與長篇討論寫交接檔，程式這邊要有結論。
  範例：`src/utils/hot_files.py`。歷史敘述（「原本是…後來…」）不寫在程式裡。
- **錯誤邊界**（`src/test/test_error_boundaries.py` 守衛）：技術層與服務層（`llm/`、`services/` 裡不是功能的模組）不接所有例外（`except Exception`、裸 `except`、含它們的 tuple），讓例外往外走到邊界處理；真的是邊界（排程的一次 tick、每則訊息、每個工具呼叫、對外的一次請求）才接，而且在那一行註明 `# 邊界：原因`（有註明的不計）。既有的 80 處記在該檔 `BASELINE`，只准減不准增；清掉一處就把基準往下調。
- async 裡的同步 DB 或檔案 I/O 丟到執行緒（`asyncio.to_thread`；persona agent 用 `run_db`）。音樂、Discord 心跳、插話都在同一個 event loop 上。
- 新增欄位或改介面時，列出所有牽動點並逐一確認。
- 細項設定放 `sys_settings/` 的 pydantic settings（frozen）；功能開關放 `settings/switches.json`（見共用元件表）。
- **分層方向**（`src/test/test_layering.py` 守衛，啟動 gate 會跑）：基礎（`utils/`、`sys_settings/`、`settings/`、`constants`）← 技術 ← 服務 ← 功能 ← 介面（`commands/`、`discord_bot.py`、`music/`），import 只能指向同層或更下層，函式內的延遲 import 也算。`llm/` 與 `services/` 各自橫跨三層（`services/`＝服務，但 `relay`／`events`／`community`／`notify_server` 是功能；`llm/`＝LLM 技術，但 `ambient`、`persona/agent`、`emoji_autofill`、`store_chat` 是功能，`member_profile_store`、`context_retriever`、`llm_service` 的零件是服務），所以分類寫在那個測試的 `LAYERS` 表，到子資料夾／模組。新資料夾要先登記層級；下層需要上層的東西，由上層交進來（介面、callback），不往上 import。跨容器（`scraper/`、`telegram_scraper/`）的 import 一律不准，現有例外列在 `CROSS_CONTAINER_ALLOWED` 並寫理由。**技術層與服務層不可 import discord**（`if TYPE_CHECKING:` 裡的型別註解不算）：要 Discord 物件就由功能層或介面層傳進來，向 Discord 要資料的那段寫在呼叫端；功能層與介面層是 Discord 應用本身，可以；基礎層只有列在 `DISCORD_HELPERS_IN_BASE` 的 Discord 工具（`utils.utils`、`discord_content`、`discord_threads`、`dm_notifier`、`panel_bump`、`channel_registry`）可以。

## 測試

- 單元測試放 `src/test/test_<功能>.py`，檔案開頭寫「守的底線」。斷言使用者看得到的約定（誰被 @、何時發、刪了哪則）；文案只比對關鍵資訊。
- 需要真實服務的放 `src/test/integration/it_*.py`，不進啟動 gate，手動執行。
- 測試會自動把 log 寫到 `/logs/test_run.log`，正式 log 不受影響。
- 靠時間的邏輯（租約到期、排隊上限、相簿安靜期）看時間、睡覺要經過可換的名字（`gpu_gate._clock`／`_async_sleep`、轉發 worker 的 `_clock`／`_sleep`），測試換成 `test.fake_clock.FakeClock`，不要真的 sleep。流程裡夾著真的執行緒 IO（aiosqlite、to_thread）換不成假時鐘的，掛 `@timing_sensitive`（`test/__init__.py`）：啟動 gate 設了 `APP_STARTUP_GATE=1` 會跳過、手動與 CI 照跑。容器啟動時負載高，靠真實時間的測試會把幾十毫秒的誤差判成失敗，bot 就多等一輪 gate。
- 突變測試複製到容器的 `/tmp` 做，只複製需要的目錄（`/app/telegram_scraper` 有 30 GB）；設 `PYTHONDONTWRITEBYTECODE=1` 並先清 `__pycache__`——同一秒內改壞又還原、檔案大小不變時，Python 會沿用改壞的 `.pyc`，結果不可信。
