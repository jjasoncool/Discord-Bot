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
   - runtime 狀態檔（例：`src/settings/*_runtime.json`、`src/services/sent_articles.db`；原本的 `sent_articles.json` 已遷移成 SQLite）
   - 使用者設定檔（例：`src/config.json`）
   - 快取、歷史紀錄、session、資料庫檔（例：`src/scraper/articles.db`、pgvector 資料、`/logs` 下的歷史紀錄、Telegram session）
3. 如需修改高風險資料檔，必須先說明風險與影響、提供備份／回復方案、取得使用者同意。
4. 若發生誤刪／誤覆寫，立即升級為高嚴重性事故：凍結 → 復原 → 記錄防再發。

## 資料與環境（硬規則）

- **Docker 只做唯讀查詢**：`ps`、`logs --since …`、`exec` 查詢、`inspect`。`compose up/down/restart/build`、`rm`、`rmi` 給指令讓使用者執行。
- **每天 04:00～約 07:30 是維護時段**（人格萃取、persona agent），這段時間請使用者不要重啟 discord-bot。
- **bot 會長時間不重啟**：會變的外部資料（官方公告、設定）每次用到時重讀，不在啟動時只讀一次。
- 讀 `articles.db` 用 `mode=ro`：它是 WAL 模式，`immutable=1` 會看不到還在 WAL 裡的新資料。

## 共用元件（動手前查這張表）

沒查就自己寫一份，是本專案最常見的錯誤。下表由 `src/test/test_shared_conventions.py` 守衛（啟動 gate 會跑，違反就起不來）；合法例外寫在該檔各條規則的 `allowed`。新增共用元件時，在該檔 `RULES` 加一條。

| 需要做什麼 | 用這個 |
|---|---|
| 寫 log | `logging.getLogger(__name__)`；去向、等級、分類改 `src/settings/logging.json`；類別 logger 用 `get_article_monitor_logger()`／`get_llm_anomaly_logger()` |
| 本機時區 | `sys_settings.time_settings.APP_TZ` |
| 遊戲公告的時間 | `services.event_time_parser.SERVER_TZ`（值同為 UTC+8，但語意不同，兩者不可合併） |
| 連 pgvector | `LLMServiceSettings().pgvector_connect()` |
| 實體表名 | `HYBRID_RETRIEVAL_SETTINGS.chat_table()`／`.source_table(key)`／`.physical_table(name)`（含 identifier 消毒） |
| 讀 prompt 檔 | `llm.prompt_files.read_text()`／`read_json()`（mtime 快取） |
| 清理聊天文字 | `personality_extractor._clean_text_for_extraction()` |
| 描述品質規則 | `persona_description_rules.txt`（各處讀同一個檔） |
| 人格素描的角色設定 | 疊在 `personality_extraction_prompt.json` 的 `system_prompt` 之上 |
| 發文到頻道 | `utils.discord_content.post_to_channel`（論壇／文字頻道自動分流、附件分批、失敗退純文字） |
| 面板置底 | `utils.panel_bump.PanelBumper`（`bump`／`bump_safe`；有人講話就置底用 `request_bump`） |
| 已發送去重 | StateDB `sent_content`（`is_content_sent`／`mark_content_as_sent`） |
| 版本更新時刻 | `services.event_scheduler.VersionDateResolver`（`refresh()`、`update_starts()`；只看時間，不看版本號） |
| GPU 獨佔（產圖時卸載 LLM） | `llm.lemonade_gate.gpu_exclusive(owner, lease_seconds)` |
| 綁頻道 | `settings/channel_registry.py` 的 `register_channel` |

## 程式碼

- 註解用繁體中文，寫「為什麼」；不寫具體模型名稱或規格（模型會一直換）。
- async 裡的同步 DB 或檔案 I/O 丟到執行緒（`asyncio.to_thread`；persona agent 用 `run_db`）。音樂、Discord 心跳、插話都在同一個 event loop 上。
- 新增欄位或改介面時，列出所有牽動點並逐一確認。
- 設定放 `sys_settings/` 的 pydantic settings（frozen）。

## 測試

- 單元測試放 `src/test/test_<功能>.py`，檔案開頭寫「守的底線」。斷言使用者看得到的約定（誰被 @、何時發、刪了哪則）；文案只比對關鍵資訊。
- 需要真實服務的放 `src/test/integration/it_*.py`，不進啟動 gate，手動執行。
- 測試會自動把 log 寫到 `/logs/test_run.log`，正式 log 不受影響。
- 突變測試複製到容器的 `/tmp` 做，只複製需要的目錄（`/app/telegram_scraper` 有 30 GB）。
