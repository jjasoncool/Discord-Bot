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
3. 要寫的東西先對照下方「共用元件」，並 grep 同類做法的**所有**實作。已經有兩份以上，就先抽成共用元件（放 `src/utils/`，只抽機制、長相留給呼叫端），再接新功能。

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
   - 快取、歷史紀錄、session、資料庫檔（例：`src/scraper/articles.db`、pgvector 資料、`/logs` 下的歷史紀錄、Telegram session）
3. 如需修改高風險資料檔，必須先說明風險與影響、提供備份／回復方案、取得使用者同意。
4. 若發生誤刪／誤覆寫，立即升級為高嚴重性事故：凍結 → 復原 → 記錄防再發。

## 資料與環境（硬規則）

- **Docker 只做唯讀查詢**：`ps`、`logs --since …`、`exec` 查詢、`inspect`。`compose up/down/restart/build`、`rm`、`rmi` 給指令讓使用者執行。例外：在 `search-mcp` 容器裡（`docker exec search-mcp …`）的情報搜尋指令可以直接執行——stdio 備用的 MCP server（`python -m llm.mcp_server`）、手動同步索引（`python -m services.search`）、搜尋評估（`python -m services.search.eval.evaluate`）與批次算向量（`python -m services.search.embed`），它們只寫自己的索引檔（repo 根目錄 `search_data/`）、評估報告 `services/search/eval/reports/` 與 pgvector 的 `data_search_chunks` 表（不碰其他表）。discord-bot 容器沒掛 `search_data/`，在那裡跑會失敗。
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
| 連 pgvector | `LLMServiceSettings().pgvector_connect()` |
| 實體表名 | `HYBRID_RETRIEVAL_SETTINGS.chat_table()`／`.source_table(key)`／`.physical_table(name)`（含 identifier 消毒） |
| 讀會被手改、改了就要生效的檔案（prompt、字典、開關、config.json、LLM runtime 設定） | 機制只有一份：`utils.hot_files.read_text()`／`read_json()`／`read_parsed(path, parse=…)`（mtime 快取、壞檔沿用上次）。各檔的解析、驗證、寫入在呼叫端：config.json 走 `ChannelConfig.load_config`／`update_config`、開關走 `switches.current()`、LLM runtime 設定走 `sys_settings.llm_settings.load_llm_runtime_config`（已接熱讀檔，LLMService 也用它）、字典走 `emoji_dictionary`／`sticker_dictionary`；不要在 `hot_files` 加認得特定檔案的函式 |
| 清理聊天文字 | `llm.persona.personality_extractor._clean_text_for_extraction()` |
| 描述品質規則 | `persona_description_rules.txt`（各處讀同一個檔） |
| 人格素描的角色設定 | 疊在 `personality_extraction_prompt.json` 的 `system_prompt` 之上 |
| 發文到頻道 | `utils.discord_content.post_to_channel`（論壇／文字頻道自動分流、附件分批、失敗退純文字） |
| 把長文切成 Discord 放得下的多段 | `utils.discord_content.split_message`（不丟內容、優先換行與空白切、不切壞暴雷 `||`；上限常數 `DISCORD_MESSAGE_LIMIT`） |
| 面板置底 | `utils.panel_bump.PanelBumper`（`bump`／`bump_safe`；有人講話就置底用 `request_bump`） |
| 已發送去重 | StateDB `sent_content`（`is_content_sent`／`mark_content_as_sent`） |
| 版本更新時刻 | `services.events.event_scheduler.VersionDateResolver`（`refresh()`、`update_starts()`；只看時間，不看版本號） |
| GPU 獨佔（產圖時卸載 LLM） | `llm.client.lemonade_gate.gpu_exclusive(owner, lease_seconds)`（另開的行程、search-mcp 容器也一起排隊：跨行程鎖檔，跨容器靠 compose 掛同一個 `gpu_lock/` 並設 `LEMONADE_GPU_LOCK_PATH`）；沒有 event loop 的同步程式（情報搜尋的批次算向量、MCP）用 `gpu_exclusive_sync()`；拿著閘門算 embedding 一律 `make_safe_llm_embedding(holding_gpu_gate=True)`（短逾時、不重試、排隊有上限，後端卡住時早點放鎖） |
| 判斷 LLM 後端連不上或逾時（該停手、晚點再試，不是請求本身的問題） | `llm.client.http_client.is_unreachable` |
| 讓模型先用工具查、再回答（每輪都照原本的思考設定、帶同一份工具清單，不查就只呼叫一次；查滿輪數保證有文字） | `LLMService.generate_reply(tool_runner=…)`（工具介面 `llm.client.tool_calls.ToolRunner`；/askai 查情報用它，不要再寫一份迴圈） |
| 工具呼叫的訊息格式（模型要呼叫工具的 assistant 訊息、`role: tool` 回覆、取工具名稱與解析參數） | `llm.client.tool_calls`（`assistant_message`／`tool_message`／`call_name_and_arguments`／`parse_arguments`；迴圈、預算、工具怎麼跑留給呼叫端。人格萃取 agent 與 /askai 情報搜尋共用） |
| 幾組工具一起交給同一個工具輪（例：遊戲情報＋網路搜尋） | `llm.client.tool_calls.combine_runners`（宣告照順序接、使用規則依序接、呼叫依名稱交給宣告它的那組；沒工具的連規則一起略過） |
| 按鈕、指令的操作權限 | `utils.utils.check_guild`（`owner_only`／`admin_only`／`required_role`／`permission="manage_messages"` 這類 Discord 權限；不通過時自己回只有本人看得到的訊息） |
| 功能開關（開／關、off／dry_run／on） | 值寫在 `settings/switches.json`（手改、下一次用到就生效）；名稱、預設、允許的值定義在 `sys_settings.switches.Switches`，讀用 `switches.current()`；新開關只能放這裡（守衛擋，舊的改到再搬） |
| 專案裡檔案的位置（settings、settings/runtime、prompts、scraper 資料庫、static、config.json、log 與備份） | `sys_settings.paths`（`APP_ROOT`、`LOGS_DIR`、`SETTINGS_DIR`＝你手改、`RUNTIME_DIR`＝bot 寫、`PROMPTS_DIR`、`SCRAPER_DIR`、`STATIC_DIR`、`settings_file()`、`runtime_path()`、`prompt_file()`；config.json 用 `utils.utils.CONFIG_FILE`）；不寫死 `"/app/..."`、`"/logs/..."`、不用 `Path(__file__).parents[n]` 往上數、不用相對路徑（守衛擋；爬蟲容器例外） |
| bot 執行時寫的 JSON（`settings/runtime/*.json`：透過 Discord 設的值與它自己的紀錄——面板、點名、音樂、自介投稿、隔離 thread、關鍵字監控；整個資料夾不進版控） | `utils.runtime_file.load`／`save`／`update`（讀走熱讀檔、寫走安全寫入加備份；面板位置用 `panel_bump` 的 `load_runtime`／`update_runtime`）；不自己 `open`／`json.load`（守衛擋） |
| 賣家物品價格（`settings/runtime/item_prices.json`） | `services.community.item_prices`（`all_prices`／`user_prices`／`set_user_prices`） |
| 寫 `config.json` | `ChannelConfig.update_config(apply)`（重讀最新內容、只改這次的 key、安全寫入加備份）；讀 `load_config` 回複本、改檔即生效 |
| 綁頻道 | `settings/channel_registry.py` 的 `register_channel` |
| 取得 thread（封存的也拿得到）、解除封存 | `utils.discord_threads.fetch_thread`／`reopen_thread`（封存的 thread 改不了、刪不了訊息） |
| 讀綁定的頻道 id（可能沒綁） | `ChannelConfig.get_configured_id(key)`（沒綁回 None，不必自己比 `DEFAULT_ID`） |
| 搜尋公告、官方 FB、PTT、巴哈的內容；讀全文（附推文、留言） | `services.search`（`SearchIndex.search`／`fetch`；索引從 `articles.db` 唯讀增量同步；用語、評估數字見 `AI_HANDOFF_AND_TODO.md` 的 `mcp-search-tools` 區塊）；MCP 殼是 `llm.mcp_server`，常駐在 compose 的 `search-mcp` 服務（背景同步與每日維護 `services.search.background`）；bot 端（discord-bot 沒掛索引）一律當 MCP 客戶端用 `llm.retrievers.intel`（`run_with_intel` 依開關準備工具、交給回答流程並記經過，`also=` 帶其他一起給模型的工具；`prepare_intel_session`；每次工具呼叫各開短連線，見模組說明） |
| 網路搜尋（SearXNG；哪類題目用哪組引擎、窄路由結果太少換通用引擎補查） | `llm.retrievers.web.search_web`（路由用 `intent.classify_route`；直接呼叫 `fetch_web_results` 守衛擋）；給模型當工具用 `WebSearchTools`（/askai 開關 `askai_web_search_mode`：keyword 先查好塞進 prompt、tool 由模型和遊戲情報一起決定；工具模式的題目類型由模型選 `kind`，每種類型的引擎寫在 `tools._KINDS`）；SearXNG 的直接答案（匯率、天氣）在 `WebRetrievalOutcome.answers`；被擋的引擎自動暫避 |
| 官方公告、巴哈單一樓層的原文網址 | `services.source_urls`（`official_article_url`、`bahamut_floor_url`） |
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
- 靠時間的邏輯（租約到期、排隊上限、相簿安靜期）看時間、睡覺要經過可換的名字（`lemonade_gate._clock`／`_async_sleep`、轉發 worker 的 `_clock`／`_sleep`），測試換成 `test.fake_clock.FakeClock`，不要真的 sleep。流程裡夾著真的執行緒 IO（aiosqlite、to_thread）換不成假時鐘的，掛 `@timing_sensitive`（`test/__init__.py`）：啟動 gate 設了 `APP_STARTUP_GATE=1` 會跳過、手動與 CI 照跑。容器啟動時負載高，靠真實時間的測試會把幾十毫秒的誤差判成失敗，bot 就多等一輪 gate。
- 突變測試複製到容器的 `/tmp` 做，只複製需要的目錄（`/app/telegram_scraper` 有 30 GB）；設 `PYTHONDONTWRITEBYTECODE=1` 並先清 `__pycache__`——同一秒內改壞又還原、檔案大小不變時，Python 會沿用改壞的 `.pyc`，結果不可信。
