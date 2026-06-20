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
- 2026-06-20：**/askai 網路搜尋兩處修正（參考連結數 + 體育題觸發）**。① **參考連結 3→5**：抓取 `top_k=5`（[llm_settings.py:218](src/sys_settings/llm_settings.py#L218)）一直全部塞進 `<web_context>`，但 [llm_service.py:316](src/services/llm_service.py#L316) 文末引用 directive 寫死「最多 3 個」卡住輸出 → 改「最多 5 個」對齊（軟性上限，LLM 仍可能引用少於 5 條；`llm_commands.py:482` 的 `outcome.results[:3]` 只是 debug log、不影響、保留）。② **體育題不觸發搜尋**：「請告訴我這周的世界足球賽比賽簡報」trace 的 `web_context_meta` 為 `triggered=false/reason=default`（根本沒打 SearXNG，是模型用無即時資料的記憶回場面話）。Root cause [intent.py](src/llm/retrievers/web/intent.py) 無體育主題群、且 SOFT 寫死「這週」對不上異體字「這周」。修法：新增 `_TOPIC_SPORTS`（足球/世界盃/NBA/英超/賽程/比分… **刻意不收 bare「比賽」「賽」**）掛 HARD + `_ROUTE_RULES` 加 `news`/`week`；SOFT 的 `這週/上週/最近一週` 改 `這[週周]/…` 異體字容錯。新增 [src/test/test_web_intent.py](src/test/test_web_intent.py)（standalone importlib 跑 14 斷言全 PASS；本機無 `discord` 套件不能直跑 unittest，docker 內可）。**待部署驗證**：`docker compose restart discord-bot` 後重問足球題，`web_context_meta` 應為 `triggered=true/reason=hard/news/week` 且附參考連結。**未做（可選）**：`test_web_intent` 加進 docker-compose 啟動測試 gate（目前只跑 snapshot+spoiler）；體育詞表非窮舉（羽球/網球/瓊斯盃等未收）。
- 2026-06-15：**fixupx 轉發改「只轉影片」+ 存在性防呆，已實作完成並歸檔**。圖片貼文不再轉（原生預覽沒差別）；查類型走 Twitter 原生 syndication CDN（token 移植 react-tweet），顯示走 fixupx；影片/服務掛掉→轉，圖片/404→不轉。詳見 `TODO-completed.md` [fixupx 連結轉發：只轉影片 + 存在性防呆](TODO-completed.md)（含決策表、設計、驗證、待部署驗證清單）。
- 2026-05-11：**修 lemonade 對 chat stream + 背景 embedding 併發的失敗（`no_choices` 假象）**。Root cause：5/4 補的 snapshot log 攢到 3 筆 `no_choices` 事故，raw body 都是 `{'error': {'type': 'network_error', 'message': 'CURL error: ...'}}`，這是 lemonade gateway 內部 CURL 轉發到 downstream backend(port 8002, llama.cpp) 失敗時的回應，但 lemonade 用 `200 OK + error envelope` 回 client，破壞 HTTP 語意，導致 bot 走 `no_choices` 分支且不重試。比對 `discord_bot.log` 三次失敗的時間軸（21:48:14 / 21:49:40 / 22:03:31），全部都是 **`/askai` LLM stream 進行中 → 1–4 秒前 `on_message 批次處理 pgvector`（[chat_persistence.py:152](src/llm/chat_persistence.py#L152) `flush_buffer` 觸發的 batch embedding）** → LLM 連線被 lemonade reset。`/askai` 內部 RAG embedding 與 chat 是序列的不會自己撞，會撞的是背景 flush。**修法**：① 新增 [src/llm/lemonade_gate.py](src/llm/lemonade_gate.py)：module-level `asyncio.Lock` + `stream_exclusive()` async context manager（純鎖、無自家狀態，繁中註解解釋為何只 lemonade 需要、為何 RAG embedding 不掛 gate）② [llm_service.py](src/services/llm_service.py) `chat_raw` 的 `self._client.chat_completion(...)` 那行外包 `async with stream_exclusive():`，snapshot 路徑留在 gate 外（admin 端點不參戰，盡早釋放鎖）③ [chat_persistence.py](src/llm/chat_persistence.py) `flush_buffer` 的 `loop.run_in_executor(_sync_write_batch / _sync_update_batch)` 包進 `async with stream_exclusive():`，buffer_lock 已先釋放避免卡新訊息入 buffer；對稱設計＝兩端互等，bg flush 等 chat 結束才打 embedding，chat 也等 flush 完才開始（典型 batch 14 筆 ≈ 2–3 秒、threshold trigger 30 筆 ≈ 4–6 秒，slash command `defer()` 後使用者只看到 thinking 多轉幾秒）④ **B1 兜底**：[llm_http_client.py](src/llm/llm_http_client.py) `_apost_json` 收到 200 後檢查 `data["error"]["type"] == "network_error"` → 主動 raise `httpx.ConnectError`，命中既有 `RequestError` 退避重試分支（2 次、1s/2s），用盡後 raise `LlmConnectionError` → `chat_raw` 既有 except 抓住寫 anomaly + snapshot，分類從假性 `no_choices` 改回真實的 `connection`。**設計準則**：① 對稱 gate 而非 peek/skip — bg flush 本來就不急（5 分鐘 interval），晚個幾秒不影響任何體感、訊息進 pgvector 延遲反而更短（5 分鐘 → 幾秒）② B3+B1 並行：B3 治觸發條件、B1 兜底 lemonade 自己的偶發 hiccup（即使所有 bot 端 embedding 已序列化，lemonade 對 downstream 的 CURL 仍可能因 GPU/驅動短暫卡頓失敗）③ 不去 lemonade repo 改 source — 工夫不對等，且就算上游修「200 改成 5xx」，bot 端對網路類錯誤退避重試也是應有的健壯性。**驗證**：AST parse 四個檔案全綠（lemonade_gate / chat_persistence / llm_service / llm_http_client）；未跑 unittest 因為 chat_persistence 既有測試不覆蓋此路徑、新邏輯純鎖無需特殊測試。**未做（後續可考慮）**：① sync 路徑 `_post_json` 沒對稱加 error envelope 偵測（bg flush 走 sync embedding，目前靠 gate 預防、不需重試；若觀察到 sync path 仍會撞可再補）② 去 lemonade GitHub 提 issue 回報「`network_error` should return 5xx not 200」。**待部署驗證**：① `docker compose restart discord-bot` ② 觸發 chat_persistence buffer 滿 30 筆 或等 5 分鐘 interval，同時跑 `/askai` → 不應再見到 `no_choices`，flush 與 chat 應自然錯開（log 不會出現 `on_message 批次處理 pgvector` 緊接 `LLM 回應格式異常` 的 pattern）③ 若仍有 lemonade 自爆 → 應看到退避重試（log 應有兩次重試延遲），最終分類為 `kind=connection` 而非 `no_choices`。
- 2026-05-04：**askai log 觀測性補強（Phase D：失敗時 backend 狀態快照，多 backend 通用）**。動機：使用者回報 /askai 偶發失敗（`no_choices` + raw body 是 Lemonade 自家寫的「Network error: CURL error: Couldn't connect to server」），重啟 Lemonade 即恢復 — 但壞掉的當下沒有 backend 內部狀態（哪些 model 載著、有沒有 chat engine、VRAM 怎樣），事後無從定位是 swap 失敗 / vision projector 缺 / engine 子進程 zombie / VRAM 不足哪一條。診斷時釐清 raw body 的「Network error」字串是 **Lemonade gateway 內部 CURL 對它自己 chat engine subprocess 失敗** 的措辭，跟 bot ↔ Lemonade、跟物理網路無關；bot 端分類 `no_choices` 是正確的，缺的是 backend-side 證據。**修法**：① [llm_http_client.py](src/llm/llm_http_client.py) 新增 `async admin_get(path, timeout=2.0) -> dict` best-effort helper（任何錯誤吞掉、回 dict 描述；故障路徑用、不該進熱路徑；命名故意叫 `admin_get` 不叫 `lemonade_admin_get` 就是要通用）② [llm_service.py](src/services/llm_service.py) 加 module-level `_BACKEND_PROBES` registry（dict[backend → tuple of (label, path)]），目前覆蓋三個 backend：lemonade=(`/api/v1/health`, `/api/v1/system-info`)、ollama=(`/api/ps`, `/api/tags`)、vllm=(`/health`, `/v1/models`) — 加新 backend 只需在 registry 補一行 ③ 新增 `_snapshot_backend_state(trace_label, model, error_kind)`：依 `runtime.backend` 從 registry 查 probes，未註冊 backend 直接 return，並行 gather `admin_get(path)` 後寫 anomaly log（log 含 `backend=...` 標籤 + `probes={label: data}` dict，外層全包 try/except，admin probe 自爆只寫 warning，**絕不蓋掉原始 raise**）④ `chat_raw` 三個失敗點都接：`no_choices` / `empty_content` 分支 raise 前各加一行；`chat_completion()` 那行外包 try/except 捕 `LlmTimeoutError` / `LlmConnectionError` → 補 anomaly log（這條原本完全沒寫進 anomaly！）→ snapshot → re-raise。**測試**：[src/test/test_llm_snapshot.py](src/test/test_llm_snapshot.py) 9 unittest 全綠 — 四種失敗類型（no_choices / empty_content / connection / timeout）各觸發一次 snapshot；三個 backend 各自 dispatch 對的 probe path（lemonade / ollama / vllm）；未註冊 backend 跳過 snapshot 且不打 admin_get；admin probe 自爆時走 warning + 仍 raise 原本錯。docker exec import smoke 通過。既有 14 個 telegram_spoiler 測試也跑了確認沒誤傷。**設計準則**：故障路徑次要診斷不可影響主路徑；2s timeout 上限 + gather 並行控成本；用 registry 而非 if/elif 分支讓加 backend 變單行修改；命名 `admin_get` 跟 `_snapshot_backend_state` 都刻意去 backend 化以利後續複用（未來 watchdog / `/system_status` Discord 指令都可共用）。**順手做的 deploy-side gate**：[docker-compose.yaml](docker-compose.yaml) `discord-bot` 服務加 `command:` 覆蓋 dockerfile CMD：啟動前先 `python -m unittest test.test_llm_snapshot test.test_telegram_spoiler`，紅了 `&&` 短路、bot 不啟動（restart: always 會無限重啟、log 立刻可見）；綠了再 `exec python discord_bot.py`（`exec` 把 PID 1 給 python，讓 `docker compose stop` 的 SIGTERM 能直達 bot 而不被 bash 吃掉）。等同把 pre-commit hook 改成 pre-deploy gate — 比 hook 不版控、換機沒了的解法可靠，比手動跑測試不會忘。**待部署驗證**：① `docker compose restart discord-bot` 應該看到 `--- running startup tests ---` → 23 tests OK → `--- tests OK, starting bot ---` → bot 正常啟動 ② 重啟 Lemonade 中觸發一次 /askai → `llm_anomaly.log` 同 trace_id 應有 `connection trace=...` + `snapshot trace=... kind=connection backend=lemonade probes=...` 兩行 ③ 復原後正常 chat → 不應有 snapshot（只成功不寫 anomaly）。**未做（後續可考慮）**：依 raw body 含 `"Network error"` / `"CURL"` 把 `no_choices` reclassify 成新 kind（如 `backend_engine_unreachable`）讓 user 不用再被 Lemonade 措辭誤導；watchdog / Discord `/system_status` 指令共用 `admin_get` 的後續實作；目前先以 snapshot 提供 backend-side 證據已可定位。
- 2026-04-29：**askai log 觀測性補強（Phase A+B）**。動機：使用者回報「LLM 回應格式異常」這類失敗，跨 `discord_bot.log` / `askai_prompt.txt` / `askai_response_history.jsonl` 沒共同 ID 串接，且 line 494 `無 choices` 路徑沒寫 anomaly log，raw response 完全沒留 → 一次 4/29 17:32 的失敗事故無法事後分析。**修法**：① [llm_commands.py](src/commands/llm_commands.py) `_handle_askai_request` 入口生成 `trace_id = ask-{user_id 末4碼}-{epoch_ms}`，並在進入時 INFO log 記下 trace+user+question[:30] ② [llm_service.py](src/services/llm_service.py) `chat_raw` / `generate_reply` 都加 `trace_id` 參數 ③ `chat_raw` line 494（no_choices 路徑）補 anomaly log 寫入 raw completion，與 line 510（empty_content 路徑）對稱 ④ `generate_reply` 改回傳 `GenerateReplyResult` dataclass（`reply` / `prompt_record_log` / `messages_sent` / `error_kind`），透過 `__iter__` 維持前兩欄 tuple unpacking 向後相容（impression_moderation_service.py 的 caller 不用改）⑤ `error_kind` 五分類：`no_choices` / `empty_content` / `http_error` / `timeout` / `connection` / `unknown` ⑥ 所有 ERROR log 帶 `trace=...` ⑦ `askai_prompt.txt` / `askai_prompt_debug.txt` 區塊 title 加 `trace=...` ⑧ `askai_response_history.jsonl` 每筆條目補 `trace_id` / `messages_sent`（最終送 LLM 的訊息，可重放）/ `error_kind` 欄位。**驗證**：docker exec 跑 import smoke test 通過；GenerateReplyResult tuple unpacking 通過。**未做（Phase C 暫不做）**：依模組切分 discord_bot.log；寫 `scripts/askai_trace.py` 自動 join 多檔輸出 timeline。**順手清理**：`logs/ollama_anomaly.log` 對應的舊 logger 是 LLM 重構前殘留（現在不是 Ollama 而是 wire client），目前未刪除留作未來議題。**待部署驗證**：① `docker compose restart discord-bot` ② 隨意觸發一次 /askai 觀察 `discord_bot.log` 出現 `askai 開始 trace=ask-...`；查 `askai_response_history.jsonl` 該筆條目應有 trace_id / messages_sent / error_kind=null（成功時）③ 故意觸發失敗（例如再問會被 safety filter 擋的 prompt）→ 應有 anomaly log + error_kind=no_choices。
- 2026-04-29：**Telegram Relay 補丁：文字 spoiler 還原成 Discord `||...||`（已驗證完成）**。回報問題：頻道訊息「內鬼情報」類使用了 Telegram spoiler，relay 到 Discord 後沒包 `||`。查 DB 發現 `telegram_messages` 沒 entities 欄位，scraper [src/telegram_scraper/handlers.py](src/telegram_scraper/handlers.py) 只存 `raw_text` 把 `message.entities` 整個丟掉，relay [src/services/telegram_relay_service.py](src/services/telegram_relay_service.py) 的 `description = content[:4000]` 也沒做任何 entity 還原 → 屬實。**範圍**：使用者明確指示「圖片不處理 只針對文字」（`media_unread` 媒體 spoiler bug 與 relay embed 邊界 bug 暫不修）。**修法**：① [db.py](src/telegram_scraper/db.py) 加 `ALTER TABLE telegram_messages ADD COLUMN IF NOT EXISTS entities JSONB`；`upsert_message_only` 加 `entities` 參數，INSERT/UPDATE 都帶上（UPDATE 用 `COALESCE(entities, $7::jsonb)` 不覆寫舊值，所以歷史訊息走 history fetch UPDATE 路徑時會自動回填）② [handlers.py](src/telegram_scraper/handlers.py) 新增 `_serialize_entities()`：把 Telethon 的 `message.entities` 轉成 `[{type, offset, length}]`（保留全部 type，未來可擴 bold/italic）③ [telegram_relay_service.py](src/services/telegram_relay_service.py) `TelegramMessageRecord` 加 `entities`，repo query 加 `entities` 並用 `json.loads` 容錯讀回（asyncpg JSONB 可能回 str/list 都接）④ 新 module-level `apply_spoiler_entities(text, entities)`：filter `MessageEntitySpoiler` → 用 UTF-16-LE bytes 切片正確處理 BMP 外字元（emoji surrogate pair）→ 從後往前插 `||`；render 中先 wrap 再 truncate 4000，避免切到 markdown 中間。**測試**：[src/test/test_telegram_spoiler.py](src/test/test_telegram_spoiler.py) 14 個 unittest 全綠（ASCII / 中文 / emoji surrogate / 多 spoiler / 越界 / 邊界 / 混合 entity）。**部署驗證**：使用者透過既有 `telegram_replay_from_message_id` 機制（[config.json:13](src/config.json#L13)）從 #7267 強制重發 → DB 確認 #7268~#7272 都有 `MessageEntitySpoiler offset=17, length=N`（整段 spoiler，end_pos 對齊 text 尾端不越界），Discord 端確認 `||...||` 渲染正確。**未做（與本輪範圍無關，列為未來議題）**：媒體 spoiler bug（`handlers.py:178` 用 `media_unread` 應改 `media.spoiler`）、relay embed 第一張圖邊界 bug（`telegram_relay_service.py:831`）、`MessageEdited` 事件未監聽（已編輯訊息會跟 DB 偏移）、scraper NewMessage event 偶發漏接（如 #7244 漏抓 22 小時靠 history fetch 補上）。**新發現的副議題**：`telegram_relay_service.py:1294-1298` 的 force_replay 用 `message_pk` 而非 `telegram_message_id` 比較，後補的歷史訊息（pk 大於 replay 起點對應的 pk，但 telegram_message_id 小於 replay_msg_id）會被誤觸發強制重發 — 這次測試時 #7244 (msg_id=7244, pk=5813) 在設 `replay_from=7267` (pk=5620) 時被誤算進範圍重發了一次。
- 2026-04-28：**LLM client 重構：拋掉 `openai` SDK 與 `llama-index-embeddings-openai`，改自寫 `httpx` wire 薄殼**。Root cause 是 commit `763d251`（chat 路徑切 OpenAI SDK）順手把 LlamaIndex embedding 包從 `-ollama` 換成 `-openai`，後者的 `OpenAIEmbedding.__init__` 在 init 階段對 model 名做 enum 白名單驗證，自訂 model 名（`Qwen3-Embedding-0.6B-GGUF`）直接拋 `ValueError`，`SafeLLMEmbedding` 一直 fallback 到 BM25 但沒被注意到。**修法**：① 新增 `src/llm/llm_http_client.py`（httpx 薄殼，~200 行；chat / embedding / list_models + 指數退避 retry）② `safe_llm_embedding.py` 改 subclass `llama_index.core.embeddings.BaseEmbedding`（核心介面穩定，避免 provider 子套件雷）③ `llm_service.py` 拋掉 `AsyncOpenAI` 改用 `LlmHttpClient`④ `LLMRuntimeConfig` 加 `backend` + `backends` profile 欄位，`extra_body` 來源由 config 決定，per-call Ollama-only knobs 只在 `backend=="ollama"` 時生效（vLLM 嚴格模式不會 4xx）⑤ `llm_runtime_config.json` 遷移到新 schema，三個後端 profile 都備好。Commit C1 (`8642806`) = code，C2 (`02a937c`) = deps cleanup。**設計準則**：綁協定（OpenAI dialect wire 自 2023 年沒動）不綁 SDK；wire 規格穩、SDK / 周邊套件不穩，長期成本最低。**待辦**：① 容器需 `docker compose restart discord-bot` 重抓 .env（`LLM_BASE_URL=13305`）並裝新 deps（C2 拔了 openai）② 重啟後驗 askai / moderation / 人格萃取三條路徑 + 觀察 `on_message` 寫 pgvector 不再 BM25 fallback ③ 啟動自我測試（`list_models()` 比對 4 個 model id）這次未做，可作為下次優化。
- 2026-04-27：askai 人設深度重構（和風含蓄酸派 + 30 熟女貴氣母愛 + 摸摸頭包容 + 外貌設定）已落 prompt；同時規劃 [AI 私聊頻道 + 三層記憶機制](#ai-私聊頻道--三層記憶機制規劃中)（preference_fact / ai_self_memory / 視覺輸入 / 道德守門），跟既有 [/remember 規劃](#使用者指令記憶-remember-未來工作) 互補不取代。
- 2026-04-27：handoff 大清理。三個已完成主線（Bahamut scraper + 反爬基礎設施、幽靈點名系統、社群 ID 查詢 Phase 0）整段移至 `TODO-completed.md`。Bahamut 第三階段 RAG ingestion 與幽靈點名剩餘 P1（部署驗證 + `/server_manager` 整合）併入歸檔當「未來工作 reference」，要做時從 archive 撈回。
- 2026-04-27：askai 人物身份對照與 prompt 整合三輪重構完成並歸檔。①#XXXX 末 4 碼錨點全鏈路對齊 ②SQL 按 profile_kind 分流 + 補 auto_personality ③mention boost 修復 ④target_profile 提權結構 + 退場處理 + 自我否定豁免 ⑤askai_system_prompt 整合精煉（11 → 8 段、~700 tok/次）+ 角色設定加陪聊感 + 回答風格三梯度 + 客服反射禁令 + 撩的拿捏。詳見 `TODO-completed.md`。未來路線：`/remember`、Structured XML context、tool calling-based persona lookup。
- 2026-04-23：DM 通知模組抽出 + 音樂面板收藏按鈕完成並歸檔。
- 2026-04-22：X.com / Twitter 影片嵌入研究歸檔（純研究、無 code 異動）。
- 2026-04-19：Ollama 服務穩定化三連（chat_raw 統一化 + keep_alive 參數 + 自動重試 + VRAM 優化）已歸檔。

---

## 協作流程契約（強制，優先於全文其他段落）

<!-- @meta
id: collaboration-rules
type: CONTRACT
status: confirmed
last_confirmed: 2026-03-31
-->

### 使用者指定的討論流程

1. 每次討論先給**完整架構**，不能只回片段。
2. 清楚標示「本輪改了哪些共識」。
3. 最後做「整體確認」：已定案 / 未定案 / 下一步。
4. 盡量避免反覆單題選單式問答，改用完整方案溝通。

### 文件閉環規範

每一輪原則上遵循：`讀取需要區塊 -> 沿用共識 -> 討論/執行 -> 必要時回寫 -> 下輪再讀`

補充：
- 不要求每輪都全文重讀。
- 應優先讀取與當前任務直接相關的區塊；只有在需要交叉確認依賴、主線變更、或資訊不足時，才擴大閱讀範圍。
- 只有在本輪有實作異動、共識更新、TODO 狀態變更、或使用者明確要求時，才需要回寫本檔。

### TODO 更新規則

1. 完成項目要打勾。
2. 完成且無未完成關聯時，應自待辦移除。
3. 若仍有依賴未完成項目，保留並註記依賴。
4. 僅在本輪有實作異動、共識更新、TODO 狀態變更、或使用者明確要求時，才需要回寫本檔進度。
5. 若主線已切換，必須同步更新：
   - 現況摘要
   - 管理級總覽
   - 原主線區塊 status
   - 必要時將舊主線移入 `TODO-completed.md`

### 禁止未經確認刪除/覆寫使用者資料檔（高嚴重性）

1. **禁止**在未取得使用者明確同意前，執行任何可能刪除、清空、覆寫資料檔的操作。
2. 針對以下類型檔案，一律視為「高風險資料」：
   - runtime 狀態檔（例如：`src/services/sent_articles.json`）
   - 使用者設定檔、快取、歷史紀錄、session、資料庫檔
3. 如需修改高風險資料檔，必須先說明風險與影響、提供備份/回復方案、取得使用者同意。
4. 若發生誤刪/誤覆寫，需立即升級為高嚴重性事故（凍結 -> 復原 -> 紀錄防再發）。

### 注意事項

- AI 禁止執行會變更環境狀態的 Docker 指令（`docker compose up/down/build/restart`、`docker rm`、`docker rmi` 等）。
- 允許 AI 執行唯讀/除錯類 Docker 指令（`docker ps`、`docker logs`、`docker exec` 查詢、`docker inspect`）。
- 若需要變更環境，AI 只能提供建議指令，由使用者自行在終端執行。
- 碼風慣例：4 空白縮排、繁體中文註解。
- 非同步開發：`asyncio` / `Telethon` / `asyncpg`。

---

## 現況摘要

> 本區只放指標與錨點。詳細內容請跳到對應區塊。
> 若某主題不再是當前主線，應從此區移除或降級，不應永久停留在現況摘要。

| 主軸 | 狀態 | 進度 | 詳見 |
|---|---|---:|---|
| Discord Bot / AI 對話能力 | 已有可用基礎能力 | 80% | [專案架構](#專案-ai-架構總覽) |
| Context / Prompt 優化 | 含 askai 身份感 + 人物對照三輪重構 + 人設深度重構（和風含蓄/30熟女/包容派）+ 智慧女性風格重寫（2026-05-18）+ few-shot 範例檔，待部署驗證 | 97% | [Context 優化](#context--prompt-優化專區) |
| AI 私聊頻道 + 三層記憶 | 規劃完成（含道德守門）；人設 prompt 已就位 | 10% | [AI 私聊頻道](#ai-私聊頻道--三層記憶機制規劃中) |
| 使用者指令記憶 (/remember) | 規劃中（與 AI 私聊頻道互補） | 5% | [/remember 規劃](#使用者指令記憶-remember-未來工作) |
| Reaction 統計 / 社群互動玩法 | 規劃中 | 5% | [Reaction TODO](#reaction-統計與社群互動玩法) |
| 點歌機器人（Music Bot） | 已上線運作 | 85% | [點歌機器人](#點歌機器人專區) |
| 跨來源整合（Article/FB/PTT/TG） | 有方向，尚未全面收斂 | 35% | [跨來源整合](#跨來源整合專區) |
| Discord Bot 管理入口 | 規劃中 | 10% | [管理 TODO](#discord-bot-管理入口與指令整理-todo) |

> 已完成 / 過往工作（Bahamut scraper + 反爬基礎設施、幽靈點名核心 + DM、社群 ID 查詢 Phase 0、Telegram Relay、Music Bot 完整實作等）詳見 `TODO-completed.md`。

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
- 檢索核心：`src/llm/context_retriever.py`
- Persona 卡片：`src/llm/persona_card_builder.py`
- Prompt 與 log 組裝：`src/llm/prompt_builder.py`
- Profile/Impression 寫入 RAG：
  - 服務層：`src/services/intro_profile_service.py`
  - pgvector 介接層：`src/llm/intro_rag_port.py`
- Impression 審核：`src/services/impression_moderation_service.py`
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

### 已完成（2026-04-15 ~ 2026-04-18）

> 詳細項目已歸檔至 `TODO-completed.md` 的「Context/Prompt 完整重構 + askai 身份感（歸檔 2026-04-18）」。
> 摘要：context/prompt 格式重構、貼圖描述、on_message 持久化、自動人格萃取 pipeline、/askai 體驗優化（timeout / 抓取量 / 取消 / 排隊顯示）、LLM 服務穩定性修復（SafeOllamaEmbedding + HTTP 連線重用 + thread-safety）、/askai 發問者身份注入（`<asker_profile>` + `<latest_user_message from=...>` + persona 拆分 + 撞名偵測 `#xxxx` + safety rules 修飾）。

### 已完成（2026-05-18：LLM HTTP client 通用錯誤護網）

**症狀：** `/askai` 每次跑都跳兩個 warning：
- `pgvector vector rank 嵌入問題失敗（降級為 BM25-only）: 'data'`
- `member-profile vector retrieval 失敗（保留 SQL 結果）: 'data'`

**根因：** `llm_http_client.py:embedding/aembedding` 直接 `data["data"]` 取 key，當後端（Lemonade / Ollama compat 層）回傳非 OpenAI shape（如 error envelope、ollama native shape）時 raise `KeyError: 'data'`，例外 str 出來就是 `'data'` 兩個字，無法判讀。原 sync `_post_json` 完全沒有 envelope unwrap，async `_apost_json` 也只認 `error.type == "network_error"`，其他 error type（如 model_not_loaded）會漏到下游撞牆。

**改動：** [llm_http_client.py](src/llm/llm_http_client.py) 新增兩個 module-level helper，多 endpoint 通用：

| Helper | 行為 | 應用 |
|---|---|---|
| `_unwrap_response_envelope(data)` | `error.type==network_error` → `ConnectError`（觸發退避重試）；其他 error envelope → `LlmAPIError(status=None)` 不重試；正常 payload 原樣回傳 | sync `_post_json` + async `_apost_json` 出口，所有 POST 端點自動受惠 |
| `_require_json_key(data, key, *, op_label)` | 缺 key / 型別不符 → raise `LlmAPIError` 附 `keys=[...]` + sample；錯誤訊息含 op_label 區分入口 | `embedding()` / `aembedding()`；未來新 endpoint（rerank / classification 等）直接套 |

**收益：** 下次同樣 warning 會直接顯示後端實際回了什麼（envelope error type / native shape / 空陣列），不必去 server log 對拍。Lemonade KEEP_ALIVE 跑掉導致的 model_not_loaded 等永久錯誤也會被正確識別、不無限退避。

---

### 已完成（2026-05-18：智慧女性風格重寫 + few-shot 範例檔）

**動機：** 原 `askai_system_prompt.txt` 的「姊姊 + 同盟 roast + 暗刺」與「母性溫度」內在矛盾；使用者要求轉向「Pekora mama 但更智慧」——溫柔為底、刺輕但準、看穿不說破、不重複不撤回。

**改動內容：**
- `src/settings/prompts/askai_system_prompt.txt` 重寫開場 3 行 + 【回答風格】1-4 + 【互動與語氣】1-3, 6 + 【色色模式】4 + 【語氣與禁忌】4-6（新增 6：失敗模式區擋空話智者 / 毒舌分析師）
- 拿掉「禁止自我撤回」條（智慧女性的刺輕，不需要這條防線撐第二句）
- 結尾反問規則鬆綁：客服式禁止照舊，**真誠好奇式反問允許**（觀察者語言）
- 八卦/情緒回應長度從 4~8 句 → 3~5 句多留白
- 加入「點規律而非點現象」原則
- 新增 `src/settings/prompts/persona_examples.txt`（12 組正反例對照 few-shot；含色色降級範例）
- `src/sys_settings/llm_settings.py` 加 `examples_file_path` 欄位
- `src/commands/llm_commands.py` `load_system_prompt()` 改成讀三檔（identity → main → examples），examples 放最末利用 LLM 對尾端模仿力最強的特性；範例缺檔不影響主流程

**設計重點：**
- few-shot 採「禁止 ❌ / 示範 ✅」對照法（負例對壓制 failure mode 比純正例有效，token 多花 ~30% 值得）
- 12 組情境覆蓋：熬夜、抽卡爆、技術搞砸、抱怨第三方、做對事、低潮、純技術求答、被邀 roast 自己人、自嘲示弱、閒聊、色色情境、色色降級
- examples 跟 rules 拆檔 → 未來迭代範例不必動主規則

### 待處理

**體驗 / 觀測：**
- [ ] `/personality_extract` 的「寫入 RAG」改為背景 task：按鈕按下後先立即回應，避免 interaction 長時間停在 loading（目前仍前景等完，已加進度訊息降低體感不安）
- [ ] 若背景寫入超時或 followup 失敗，規劃 fallback（DM 或至少補 log / 狀態查詢入口）
- [ ] 為 `save_personality_results()` / `index_auto_personality()` 補逐筆或批次成功 log 與耗時統計，判斷卡點在 embedding、delete、還是 pgvector insert
- [ ] `asker_profile.roles` 欄位目前為 `(未啟用)`，未來可填 Discord 身份組名稱 + 權限層級（admin/moderator/member）

**部署驗證（待重啟 + 跑一輪確認）：**
- [ ] 2026-05-18 智慧女性風格 + few-shot 範例效果（觀察：回應是否變短/留白變多、是否真的「點規律不點現象」、空話智者 / 毒舌分析師 failure mode 是否被擋掉、色色降級觸發是否更敏感）
- [ ] 2026-04-27 三輪 askai 重構完整效果（#XXXX 對齊、target_profile 區塊、prompt 整合後回答長度與陪聊感、自我否定卡片是否仍能被 LLM 正常引用）
- [ ] Ollama 重試邏輯（觀察 `[WARNING] Ollama 第 1 次呼叫失敗` log）
- [ ] embedding `num_ctx=8192`（`curl http://192.168.56.1:11434/api/ps` 看 `qwen3-embedding:0.6b` 的 `size_vram` 從 ~5.7GB 降到 ~3.1GB）

**外部環境：**
- [ ] **Windows Ollama server 待調整**（使用者本機設定，AI 無法直接改）：`OLLAMA_KEEP_ALIVE=24h`（原 5m，每 5 分鐘反覆 unload/reload 是 Windows `wsarecv` / ephemeral port 耗盡主因）。`OLLAMA_MAX_LOADED_MODELS=2` 已設好、`OLLAMA_NUM_PARALLEL=1` 已設好。改完重啟 Ollama 後驗證 `server.log` 不再 5 分鐘一次的 `load request`。AMD 顯卡維持 `OLLAMA_VULKAN=true`。

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
| `src/services/llm_service.py` | prompt bundle、`asker_profile` 參數、generate_reply |
| `src/commands/llm_commands.py` | context 分離、asker_profile 組裝、撞名偵測 |
| `src/llm/persona_card_builder.py` | 自然語言化、`person_id` 保留 |
| `src/llm/context_retriever.py` | discord_context item（含 `display_name`）、vector index cache |
| `src/llm/chat_persistence.py` | buffer 批次寫入、SafeOllamaEmbedding |
| `src/llm/personality_extractor.py` | 人格萃取 pipeline |
| `src/llm/intro_rag_port.py` | `index_auto_personality`、`_ainsert`、singleton |
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
| `src/llm/personality_extractor.py` | Phase 3：萃取時加權 reaction 訊號 |

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
affects: [user-directive-memory]
last_confirmed: 2026-04-27
-->

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

- [ ] 新檔 `src/llm/preference_extractor.py`：批次掃 AI 私聊訊息（含圖片描述）抽原子事實
- [ ] 抽取 prompt（`src/settings/prompts/preference_extractor_prompt.json`）內嵌**道德分類**規則（紅線丟 / 中風險標 sensitivity / 低風險正常記）
- [ ] pgvector 新 `profile_kind = "preference_fact"`，metadata：`{author_id, fact_text, category, source_msg_id, confidence, captured_at, source_kind, sensitivity, ephemeral}`
- [ ] confidence < 0.6 不進 persona card
- [ ] 衝突處理：保留歷史 + 召回偏新（讓「之前說 X 現在改口啦」這種接話成立）
- [ ] `src/llm/intro_rag_port.py` 新增 `index_preference_fact()`
- [ ] `src/llm/persona_card_builder.py` 新增「我（柔喵）記得的偏好」段
- [ ] `src/llm/context_retriever.py` SQL 多撈 `profile_kind='preference_fact'`，召回 top-K = 3
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
| `src/llm/preference_extractor.py`（新） | 偏好事實抽取 | P4 |
| `src/llm/self_memory_summarizer.py`（新） | AI 自我記憶 summarizer | P5 |
| `src/llm/intro_rag_port.py` | 新增 `index_preference_fact()`、`index_ai_self_memory()` | P4, P5 |
| `src/llm/persona_card_builder.py` | 新增「偏好」+「柔喵記憶」段 | P4, P5 |
| `src/llm/context_retriever.py` | SQL 多撈兩種 profile_kind + sensitivity 過濾 | P4, P5, P6 |
| `src/services/llm_service.py` | 整合 reply_gate + vision describer 到主流程 | P2, P3 |
| `src/sys_settings/llm_settings.py` | 新增 gating model + vision model 設定 | P2, P3 |

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
- [x] 多歌單管理（多歌單下拉，可複選合併播放）— 2026-06-20，詳見下方變更紀錄
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

### FB 貼文推送模式（2026-04-07 完成，待部署驗證）

<!-- @meta
id: fb-push-notify
type: STATE
status: confirmed
depends_on: [cross-source-integration]
affects: [project-architecture]
last_confirmed: 2026-04-07
-->

**起因：** post id=399「光耀灼痕——贊妮」DB 有 8 張圖，但 bot 收到 API 回傳 images 為空，Discord 貼文無圖。根因：輪詢模式下時間差 + FB CDN URL token 過期 + 無 URL 刷新機制。

**變更（4 檔案）：**
1. `src/scraper/main.py`：FB 抓完後呼叫 `_notify_discord_bot("fb")`
2. `src/services/notify_server.py`：新增 `"fb"` handler → `_process_fb` → 呼叫 `FBMonitor.check_and_send_fb_posts()`
3. `src/discord_bot.py`：移除 `_auto_start_fb_monitor` 輪詢（原每 600 秒）
4. `src/scraper/services/fb_scraper_service.py`：`_merge_fields_for_duplicate` 圖片合併改為 `>=` 時更新（刷新 CDN token，但不縮水）
5. `src/scraper/db/database.py`：`_update_fb_post` 圖片從「只新增」改為「全量替換」（URL 有變時刪舊插新）

**流程（改後）：**
> scraper 抓 FB → 寫 DB（URL 最新鮮） → POST /notify/fb → bot 從 API 拉資料 → 下載圖片 → 發送 Discord

**注意事項：**
- 舊貼文（不在 FB 首頁的）不會被重抓，其 CDN URL 過期後無法自動更新
- `start_fb_monitoring()` 仍保留於 `fb_monitor.py`，可供手動指令使用

### X.com / Twitter 影片嵌入研究（2026-04-22）

<!-- @meta
id: xcom-video-embed-research
type: STATE
status: draft
depends_on: [cross-source-integration]
affects: []
last_confirmed: 2026-04-22
-->

> **背景：** 使用者問 ermiana 類 Discord bot 為何能把 x.com 貼文影片直接轉成可播放 embed。結論記錄於此，若未來要在本專案加 x.com 來源可直接接手。

**核心原理：**
- Discord unfurler 會抓訊息裡 URL 的 `<meta>` 標籤（OpenGraph / Twitter Card）決定 embed 樣式
- x.com 本身**不回傳 `og:video` 直連**，只給縮圖，所以 Discord 播不了
- 第三方代理站 scrape 該 tweet 後重組一份含 `og:video` / `twitter:player:stream` 的 HTML，Discord 抓到就能直接播

**常用代理網域（把 `x.com` / `twitter.com` 整段替換）：**
- `fxtwitter.com`（最穩定、最主流）
- `fixupx.com`（FxTwitter 對應 x.com 的新網域）
- `vxtwitter.com`（另一派系）

**Bot 極簡實作模式（若要自己做）：**
1. `on_message` regex 抓 `x.com` / `twitter.com` URL
2. 替換 domain 後重發
3. `message.edit(suppress=True)` 或 webhook 模仿使用者身份，抑制原訊息 embed 避免雙重 embed

**影片直連 JSON API（想自己解析用）：**
- `GET https://api.fxtwitter.com/{user}/status/{id}` → 回 JSON
- `media.videos[].url` 即 `.mp4` 直連
- 免認證、免 API key

**能力邊界（重要）：**

| 功能 | 代理網域 | 說明 |
|---|---|---|
| 單篇貼文內容 | ✅ | 文字、作者、時間、媒體 |
| 影片直連 | ✅ | `.mp4` URL |
| 關鍵字 / hashtag / 使用者時間軸搜尋 | ❌ | 完全沒這能力，只吃「已知的 tweet URL」 |

**代理網域底層靠什麼跑：**
- Syndication API：`cdn.syndication.twimg.com/tweet-result?id={id}&token={derived}`
- 原用途是讓部落格 / 新聞網站嵌入推文，免登入、免 key、免費
- token 是前端用 tweet id 算出來的公式，任何人都能產
- X 不關掉 syndication 的理由：關了全世界新聞網站的 embed 都會爛，對 X 自己的 SEO 是自殺
- 舊的 `guest_token`（`/1.1/guest/activate.json`）**2023 年中被封殺**，Nitter / snscrape 就是那時死的，現在不可用

**付費 vs 免費路線比較：**

| 層面 | 官方 v2 API | Syndication（fxtwitter 等） |
|---|---|---|
| 要錢 | Basic $200/月 起 | 免費 |
| 註冊 | 需申請 API key | 不需 |
| 搜尋 / timeline | ✅ | ❌ |
| SLA / 文件 | ✅ | **完全沒有** |
| 隨時被關的風險 | 低 | 高（X 已有前例） |

**若未來要在本專案加 x.com 來源，決策樹：**
1. 「把 Discord 訊息裡的 x.com 連結轉成可播放影片」→ `on_message` domain replace，最省事，一小時可收工（見 [src/discord_bot.py](src/discord_bot.py)）
2. 監控特定帳號新貼文 → 沒有免費穩定方案，需評估付費 v2 或放棄
3. 關鍵字搜尋 → 代理網域做不到，只能走付費 v2 或改用其他社群（Threads / PTT / FB）
4. 若做商業/長期依賴 → 不建議依賴 syndication，**X 能隨時關掉**

**參考：**
- FxTwitter 專案：https://github.com/FixTweet/FxTwitter

---

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

---

## 修正紀錄：幽靈點名按鈕越權 BUG（2026-06-12）

<!-- @meta
id: rollcall-button-auth-fix
type: FIX
status: confirmed
last_confirmed: 2026-06-12
-->

**問題：** A 可以點 B 的點名按鈕，並解掉「A 自己」的點名（拿到豁免）。
**根因：** `RollCallResponseView.respond` 只檢查「按的人是否 pending」，按鈕未真正綁定到該訊息的目標使用者；重啟後 persistent view 的 `_target_user_id=None`，連薄弱檢查都失效。
**修正：** 以 `interaction.message.id` 反查 `runtime.pending` 取得該訊息真正的目標 `user_id`，只允許本人回覆自己的點名訊息（`src/commands/rollcall_commands.py`）。
**待驗證：** 部署後實測「他人按按鈕被擋下、本人按可正常通過、重啟後仍正確綁定」。

---

## 變更紀錄：音樂「停止」按鈕改為「重置歌單 + 重載線上歌單」（2026-06-13）

<!-- @meta
id: music-reset-reload-playlist
type: FEATURE
status: confirmed
last_confirmed: 2026-06-13
-->

**背景：** 舊「停止」按鈕(player.stop())其實只清點歌插播+跳當前歌，主歌單仍續播，名稱誤導；且線上歌單(default_playlist_url)改了內容後不重啟不會同步。

**變更：**
- 按鈕 `停止/⏹` → `重置歌單/♻️`（custom_id 仍為 `music_stop` 以相容既有面板），method 改名 `reset_playlist`（`src/music/announcer.py`）。
- 新增 `MusicPlayer.reload_playlist()`（`src/music/player.py`）：重新抓取 `default_playlist_url` 最新清單 → 清空點歌+舊主歌單 → 換上新清單 → 套用 shuffle → 跳過當前舊歌續播。**先抓成功才換**，抓取失敗/空清單則保留舊歌單回傳 None，避免清空後沒歌可播。`_reloading` 旗標防重複觸發。
- 抽出 `_fetch_playlist_songs()` 純抓取 helper，`add_to_playlist()` 與 `reload_playlist()` 共用。

**待驗證：** 部署後實測 ① 線上歌單加/刪歌後按鈕能同步；② 抓取失敗時不會清空舊歌單；③ 點歌會被清空。

**備註：** `MusicPlayer.stop()` 已無呼叫者（dead code），暫時保留未刪。

---

## 變更紀錄：多歌單下拉（可複選合併播放）（2026-06-20）

<!-- @meta
id: music-multi-playlist-select
type: FEATURE
status: implemented_pending_verify
last_confirmed: 2026-06-20
-->

**需求：** 控制面板加一個 Discord 多選下拉（multi-select），可勾選一個歌單只播該歌單、勾多個則合併播放、全勾＝全部合併；預設全部合併。需相容現況的單一歌單設定，且歌單名稱可自動抓 YouTube 標題（不用手打）。

**設定檔（`src/settings/music_runtime.json`）— key 為 `playlist_url`，多型：**
- 字串：`"playlist_url": "https://...&list=..."`
- 字串陣列：`"playlist_url": ["url1", "url2"]`
- 物件陣列：`"playlist_url": [{"name": "華語", "url": "..."}, {"url": "..."}]`（`name` 可省略＝自動抓 YouTube 歌單標題）
- `active_playlists`（選用）：`"all"` 或 key/名稱陣列；記住使用者下拉選擇、重啟後沿用，預設全部。machine 寫入用 key。
- **向後相容**：沒有 `playlist_url` 時自動讀舊 key `default_playlist_url`（字串）。

**識別與命名設計：**
- 每個歌單算一個穩定 `key`（`list=` id ＞ video id ＞ url 截斷），下拉 value 與 `active_playlists` 持久化都用 key，與「可能自動抓/變動的名稱」解耦。
- 顯示名稱：自訂 name ＞ 自動抓的 YouTube 標題 ＞ 後備。自動標題在背景抓取（`YTDLSource.extract_playlist_title()` 用 `playlistend=1` 快速；載入歌單時也順手快取），抓到後 `refresh_panel()`。

**變更：**
- `src/music/config.py`：新增 `playlist_key()` 與 `Playlist(key,url,name=None)`；`MusicConfig` 用 `playlists`/`active_keys`，property `default_playlist_url`/`active_urls`/`has_playlists`。`_parse_playlists()` 解析多型 `playlist_url`（＋舊 key 相容），`_resolve_active()` 回 key（接受 key 或名稱）。watcher 監看 `playlist_url`/`default_playlist_url`/`active_playlists`。
- `src/music/ytdl.py`：`_extract_playlist_sync()` 改回傳 `(title, entries)`；新增 `extract_playlist_title()`。
- `src/music/player.py`：`_playlist_titles` 標題快取；`_fetch_playlist_songs()` 順手快取標題；新增 `load_active_playlists()`/`_rebuild_main_from_urls()`（多歌單合併、先抓成功才換）/`set_active_playlists(keys)`（切換＋持久化）/`resolve_playlist_titles()`/`display_name()`。`reload_playlist()` 重載「目前選取集合」。
- `src/music/announcer.py`：`PlaylistSelect`（value=key, label=顯示名稱）放進 **ephemeral 彈出面板** `PlaylistEditView`，不常駐主面板。主面板「重置歌單 ♻️」按鈕改名 **「編輯歌單 🎚️」**（custom_id 仍 `music_stop` 相容既有面板）。
- `src/music/cog.py`：啟動載入改 `load_active_playlists()`，gate 改 `has_playlists`；新增背景 `_prewarm_playlist_titles()`（預抓名稱）；新增 `refresh_playlist_config()`（force_reload + 抓名稱，不動佇列）。
- **「編輯歌單 🎚️」按鈕流程**：按下 → `refresh_playlist_config()` 立即重讀 `music_runtime.json`（不等 5 秒 watcher）+ 補抓歌單名稱 → 若 **≥2 個歌單**則彈出 ephemeral 多選清單讓使用者挑（選好由 `PlaylistSelect.callback` → `set_active_playlists()` 重建並持久化）；若 **0~1 個**則直接 `reload_playlist()` 重載最新線上歌單。使用者編輯 `playlist_url`（新增/刪改歌單）後按一下即套用，**免重啟**。

**待驗證（部署後）：** ① 單一歌單／舊 `default_playlist_url`：按「編輯歌單」直接重載、不彈清單；② 填多個歌單：按「編輯歌單」彈出 ephemeral 多選清單，預設全勾合併；③ 清單勾單一個只播該歌單、勾多個合併；④ 沒填 name 時清單顯示 YouTube 歌單標題；⑤ 抓取失敗保留舊歌單；⑥ 重啟後沿用上次選擇；⑦ 編輯設定檔新增歌單後，按「編輯歌單」即出現新歌單（免重啟）。

**待 user 提供：** 把第二條（含以後更多）歌單連結填進 `playlist_url`（名稱可不填）。

---

## 新功能：點歌者離開自動移除其點的歌（2026-06-13）

<!-- @meta
id: music-drop-requests-on-leave
type: FEATURE
status: confirmed
last_confirmed: 2026-06-13
-->

**需求：** 有人進音樂頻道點歌就跑走，偵測其離開後自動砍掉他點的歌——未播放的移除、正在播放的等同跳過停止。

**設計（資料已就緒：`song.requested_by_id` 點歌時已記錄）：**
- `MusicQueue.remove_interrupts_by(user_id)`（`src/music/queue.py`）：移除某人尚未播放的插播歌。
- `MusicPlayer.drop_requests_by(user_id)`（`src/music/player.py`）：未播放的移除 + 正在播的若是他點的則 `voice_client.stop()` 跳過。主歌單歌 `requested_by_id=None` 不會誤砍。
- `MusicCog.on_voice_state_update` + `_handle_requester_left`（`src/music/cog.py`）：偵測離開音樂頻道（完全離開或切頻道都算）→ **寬限 5 秒**，若仍未回來才移除 → 在頻道發**簡短公告**。

**行為共識：** 寬限 5 秒（避免閃斷誤砍）、移除後頻道簡短公告。

**待驗證：** ① 點歌後離開 5 秒內回來不砍；② 超過 5 秒砍掉且公告；③ 正在播他的歌會直接跳過；④ 主歌單歌不受影響。
