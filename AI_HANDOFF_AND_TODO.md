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
- 2026-08-18（Telegram 補掃補不到「中段缺口」，**已實作・未 commit・待部署驗證**）：使用者回報「重啟後又發一大堆早上 10-11 點的文章」，疑似重複。**查證＝不是重複、是首次補發**：`delivery_state` 全表無任何 `message_pk` 送超過 1 次，該批 8 則 `message_date` 10:31~11:03 但 `created_at` 全是 **17:24**（重啟才入庫）；早上 111 則中 34 則無 delivery 記錄者**全部**是 media group 成員（由首則代發），無法解釋的漏發 = 0。**根因**＝2026-08-02 版補掃的 `offset_id = max(message_id)` + `reverse=True` 只看得到比 max_id 更新的訊息，漏的若是**中段**（2742/2743/2746 漏但 2745/2747 已收 → max_id 早跳過去）永遠掃不到，只能等重啟全量掃描（本次卡 7 小時）。**修法＝指針左移**（使用者拍板改既有流程、不另開補洞路徑）：`offset_id = max_id - CATCHUP_GAP_WINDOW(300)`；配套 ①`limit` 加大成 `300+200`（limit 卡的是**撈回**幾則，沿用 200 會在 `window_start+200` 截斷）②新增 `db.get_existing_message_ids` 一次撈視窗內已有 id 成 set 過濾（否則 290 則已存在訊息各跑完整 `_process_message`）。**驗證**：容器內注入假 client/db 重現 8/18 真實缺口，洞全補回、新訊息照收、已存在 297 則零重跑；**反向驗證** limit 壓回 200 → 掃描截斷、洞與新訊息一則都收不到。**下一步**：`docker compose restart telegram-scraper`。詳見 [補掃區塊追加段](#telegram-漏收事件自動補掃2026-08-02-已實作2026-08-18-補上中段缺口盲區待部署驗證)。
- 2026-08-18（人格萃取 Agent 影子模式，**規劃定案・未開工**；本輪只做查證與線上實測，未動任何 code／設定檔）：把每日 04:00 的固定人格萃取升級成 tool-calling agent，產出**可稽核的 diff** 而非整份覆蓋；影子模式並行、寫獨立表、**不動 production**。**線上實測（Lemonade 11.5.0 + Qwen3.8-27B-UD-Q4_K_XL / llamacpp b9747）**：tool calling ✅（`finish_reason=tool_calls`，4.4s / 33 tok/s）、`role:"tool"` 回合往返 ✅、`response_format: json_schema` strict ✅ → **不需自架 llama-server、不需 `--jinja`，M0 直接跳過**。**併發**：1 發 33 tok/s、2 發各 11~12、3 發各 7 → llama-server 多 slot 真並行但**總吞吐固定被平分**（故獨立進程方案會讓 askai 慢 3 倍）。**prompt cache**：冷 3417 tok/10.1s → 熱 18 tok/0.3s，且插入不同前綴後仍命中（多組 cache 並存）；插話 prompt 78%（10,823 字元）是靜態前綴，現有組裝順序已是最優。**資料面**：chat 表 273,780 筆 / 81 人 / `message_id` **100% 覆蓋**（evidence 機制成立）；訊息平均僅 11~38 字；14 天符合門檻 46 人、337,211 字。**五項定案**：①`personality_model` 統一改 27B（`max_models.llm=1` 會互踢）②04:00 觸發、production→agent **序列接力**（約 05:10 收工）③agent 跑在 bot process 內共用 `stream_exclusive`、**不可做成獨立腳本**、每 step 主動禮讓 ④**補第四支工具 `get_conversation`**（人格訊號在互動不在句子，不補會輸給現有 pipeline）+ context 改 token 預算 ⑤thinking 分兩段（收集關、產 diff 開，12 分/人 → 3 分/人）。**M1 第一項＝補 code 缺口**：`think` 覆寫管線完整存在，唯一斷點在 [_build_chat_extra_body](src/services/llm_service.py#L573-L588) 的 lemonade 分支把它丟掉。詳見 [Persona Agent 區塊](#persona-extraction-agent影子模式規劃定案)。
- 2026-08-09（插話「談話自然」重構，**已實作・待部署驗證**；py_compile 全綠、146 測試全過、未 commit）：使用者提出兩個痛點——①一偵測到發言就馬上運算，沒等人講完；②聊天室常有多組人聊不同主題，機器人不知該加入哪個。**本輪量到基準**：自發插話「trace→送出」中位 **120.8s**（p90 165s、max 901s，n=3540）、PASS 率僅 15%、`ai_interactions` 5602 筆但負向反應只有 **13** 筆。**核心診斷**：問題不是它選錯主題，是**選的時候那條線還在、120 秒後講出來已經沒了**，而自發插話是裸 `channel.send` 無指向 → 必然像亂入；且節奏由冷卻計時器決定（每 5 分鐘準時報到）而非對話內容。**目標函數經使用者拍板＝自然/人性，GPU 節省降為副作用**。**四層方案**：L3 選線+reply 錨定（第一優先，讓「慢」變合理）、L4-b 接續自己的話、L2 debounce+typing 不搶話、L1 鉤子閘（**不用 LLM**＝結構演算法+少量 regex+k-NN，權重用 logistic regression 從 5602 筆學、標籤改用「插話後有沒有人接」而非 reaction）。順帶 `max_passes_per_burst` 3→1、`cooldown` 300→180。**使用者否決**：等鎖上限（GPU 本來就慢，放棄等於 /askai 忙時永遠不插話）、新鮮度丟棄（被接完也可以插，且丟棄＝白燒 120s 零產出）。**實作中修掉的缺陷**：L4-b 借用 directed 路徑會連 foreground 讓位/降溫硬閘/每小時上限一起繞過 → 加 `followup` 旗標分流閘門。**下一步**：`docker compose restart discord-bot` → 看 log 的「ambient 鉤子」分數分布調 `hook_threshold`、看「錨定=#N」確認模型有遵守選線契約。詳見 [自然插話重構區塊](#自然插話重構2026-08-09已實作待部署驗證)。
- 2026-08-18（Telegram 媒體 spoiler 未帶到 Discord，**已實作，待部署驗證**）：症狀＝TG 影片有防雷、Discord 沒打碼。**relay 端無辜**（`AttachmentSpec.is_spoiler` → `discord.File(spoiler=)` → discord.py 自動加 `SPOILER_` 前綴，圖片也已有「spoiler 首圖不進 embed」分支）；**DB `telegram_message_media` 2696 筆 `is_spoiler` 全 false**。**根因**＝[`_build_media_item`](src/telegram_scraper/handlers.py#L140) 讀 `message.media_unread`（語意是「媒體未檢視」，語音/圓形影片用），真正旗標在 media 物件上的 `MessageMediaPhoto/Document.spoiler`。**修法**：①改讀 `getattr(media, "spoiler", False)`；②`db.update_media_spoiler()`（`IS DISTINCT FROM` 過濾空寫）；③「媒體已存在略過下載」分支補呼叫回填——**沒這段舊資料永遠錯**，`/resend_article` 舊影片仍不打碼。**驗證**：scraper 5 案全過、`discord.File(spoiler=True)` 實測輸出 `SPOILER_clip.mp4`、回填 SQL 以 BEGIN/ROLLBACK 實測（值變 UPDATE 1、值同 UPDATE 0、回滾後 2696 筆未動）。**未 commit**。**下一步**：重啟 telegram-scraper，歷史掃描會校正近 7 天旗標。詳見 [Telegram 媒體 spoiler 區塊](#telegram-媒體-spoiler防雷未帶到-discord2026-08-18-已實作待部署驗證)。
- 2026-08-02（Telegram 漏收事件自動補掃，**已實作，待部署驗證**）：症狀＝「最新的 telegram 沒有轉發」。**relay 端無辜**（delivery_state 3119 筆、`last_polled_pk`=`max(id)`=12494，DB 內全送完）；**斷點在 scraper**——Telegram 已有 `Seele_WW_leak/9824`，DB 最大卻停在 **9823**（08-01 22:29:48+08）。用 `telegram_emoji_refetch` NOTIFY 測活性，scraper **秒回且成功即時抓回 9823** → 連線正常、非卡死。**根因**＝Telethon 漏派 NewMessage 事件（handler 完全沒被呼叫），而 [runner.py](src/telegram_scraper/runner.py) **只在啟動時掃一次歷史**，之後純靠即時事件 → 漏掉就永久漏掉。**非偶發**：以 `created_at - message_date > 5min` 回推「靠重啟才補進來」的比例 7/25 **28/63**、7/26 **59/121**，過去都是剛好有重啟蓋掉問題。**實作**＝每 15 分鐘（`catchup_interval_min`，可熱調整、`<=0` 停用）以各頻道 DB 最大 message_id 為基準做 `iter_messages(reverse=True, offset_id=基準, limit=200)` 增量重掃（已讀 Telethon 1.43.2 原始碼確認 reverse 下 `offset_id` 內部 +1＝不含基準、回傳舊→新保 PK 時序）；即時/補掃/refetch 共用 `process_lock` 序列化；單輪上限由舊往新掃故不留永久空洞；單頻道拋錯不拖垮迴圈。**順修** History log 把 Gamedataleak 訊息全標成 `source_channel=Seele_WW_leak` 的誤導 bug。**驗證**：py_compile 全綠、容器內 stub 煙霧測試 15 項全過、`get_peer_id` 與 DB chat_id 一致、實 DB 基準 Seele=9823/Gamedataleak=2669。**已 commit（`fbd2d3c`）**，`runtime_config.json` 刻意未動（受保護檔，程式端預設已生效）。**下一步**：`docker compose restart telegram-scraper` → 立刻補回 9824 → 觀察 `[CatchUp]` log。詳見 [Telegram 漏收事件自動補掃區塊](#telegram-漏收事件自動補掃2026-08-02-已實作待部署驗證)。

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

## 共用元件索引（動手前先查這張表）

<!-- @meta
id: shared-components-index
type: CONTRACT
status: confirmed
last_confirmed: 2026-08-19
affects: 全專案
-->

> **本專案大部分由 AI 協作，最常見的錯誤是「沒查就自己寫一份」。**
> 新增任何 helper 前先看這張表；表裡有的一律沿用，不要另立。
> 這些規則由 `src/test/test_shared_conventions.py` **自動守衛**（掃原始碼、進啟動 gate），
> 違反會讓容器起不來——文件會被略讀，紅掉的測試不會。

| 需要做什麼 | 用這個 | 不要自己寫 |
|---|---|---|
| 連 pgvector | `LLMServiceSettings().pgvector_connect()` | `psycopg2.connect(host=..., ...)` |
| 取實體表名 | `HYBRID_RETRIEVAL_SETTINGS.chat_table()` / `.source_table(key)` / `.physical_table(name)` | `f"data_{...}"`（**且會漏掉 identifier 消毒**） |
| 台北時區 | `sys_settings.time_settings.APP_TZ` | `timezone(timedelta(hours=8))`、或另立 `TAIPEI_TZ = APP_TZ` 別名 |
| 讀 prompt 檔（mtime 快取） | `llm.prompt_files.read_text()` / `read_json()` | 自己寫 `_PROMPT_CACHE` + `st_mtime_ns` |
| 清理聊天文字（表情轉語意／去 URL／mention） | `personality_extractor._clean_text_for_extraction()` | 自己 regex |
| 描述品質規則（嚴禁廢話那套） | `persona_description_rules.txt`，兩邊各自讀同一個檔 | 在新 prompt 裡重抄一份 |
| 人格素描的角色設定／繁中／表情規則 | 疊在 `personality_extraction_prompt.json` 的 `system_prompt` 之上 | 重寫一份 system prompt |

**合法的例外（形狀不同，硬收斂反而更糟，已寫進守衛的 allowlist）**
- `scraper/tools/extract_fingerprint.py` 的時區：scraper 是獨立容器（掛 `./src/scraper` → `/app`），根目錄看不到 `sys_settings`。兩邊都吃 compose 的 `TZ=Asia/Taipei`
- `emoji_text_utils._load_descriptions`：永久快取 + 明確 `reload_descriptions()`，因為字典是被 04:00 排程改寫後主動重載，不是靠 mtime 輪詢
- `ambient_reply._load_ambient_prompt`：多檔疊層且有自己的組裝順序
- `llm_service._load_runtime_config_cached`：讀 pydantic 設定物件，錯誤處理不同

**新增共用元件時**：在 `test_shared_conventions.py` 的 `RULES` 加一條，下一個人就不會重造。

---

## 現況摘要

> 本區只放指標與錨點。詳細內容請跳到對應區塊。
> 若某主題不再是當前主線，應從此區移除或降級，不應永久停留在現況摘要。

| 主軸 | 狀態 | 進度 | 詳見 |
|---|---|---:|---|
| Discord Bot / AI 對話能力 | 已有可用基礎能力 | 80% | [專案架構](#專案-ai-架構總覽) |
| Context / Prompt 優化 | 含 askai 身份感 + 人物對照三輪重構 + 人設深度重構（和風含蓄/30熟女/包容派）+ 智慧女性風格重寫（2026-05-18）+ few-shot 範例檔，待部署驗證 | 97% | [Context 優化](#context--prompt-優化專區) |
| AI 偶爾插話 / 閒聊（功能二） | **Phase A+B 已實作（2026-06-21）**，待 docker 驗證；C（記憶寫入）待做 | 50% | [AI 偶爾插話](#ai-偶爾插話--閒聊功能二規劃中) |
| 人格萃取 Agent（影子模式） | **規劃定案（2026-08-18）**；線上實測 tool calling／json_schema 全綠，M0 跳過 | 15% | [Persona Agent](#persona-extraction-agent影子模式規劃定案) |
| AI 私聊頻道 + 三層記憶（功能一·姊妹案） | 規劃完成（含道德守門）；人設 prompt 已就位；**本輪暫放旁邊** | 10% | [AI 私聊頻道](#ai-私聊頻道--三層記憶機制規劃中) |
| 使用者指令記憶 (/remember) | 規劃中（與 AI 私聊頻道互補） | 5% | [/remember 規劃](#使用者指令記憶-remember-未來工作) |
| Reaction 統計 / 社群互動玩法 | 規劃中 | 5% | [Reaction TODO](#reaction-統計與社群互動玩法) |
| 點歌機器人（Music Bot） | 已上線運作 | 85% | [點歌機器人](#點歌機器人專區) |
| Telegram relay 可靠性 | **補掃已實作（2026-08-02, `fbd2d3c`）+ 媒體 spoiler 已實作（2026-08-18, `77c812d`）**；兩者皆待重啟 telegram-scraper 驗證 | 90% | [漏收補掃](#telegram-漏收事件自動補掃2026-08-02-已實作待部署驗證) / [媒體 spoiler](#telegram-媒體-spoiler防雷未帶到-discord2026-08-18-已實作待部署驗證) |
| 跨來源整合（Article/FB/PTT/TG） | 有方向，尚未全面收斂 | 35% | [跨來源整合](#跨來源整合專區) |
| Discord Bot 管理入口 | 規劃中 | 10% | [管理 TODO](#discord-bot-管理入口與指令整理-todo) |

> 已完成 / 過往工作（Bahamut scraper + 反爬基礎設施、幽靈點名核心 + DM、社群 ID 查詢 Phase 0、Telegram Relay、Music Bot 完整實作等）詳見 `TODO-completed.md`。
>
> **2026-08-18 歸檔**：活動公告自動建活動（17 筆已建立）、Telegram 自訂表情 → Discord App Emoji（10 個已上傳）、Telegram 多頻道來源 + 轉發去重（Gamedataleak 205 筆），三者皆已上線運作，連同 2026-06-25 ~ 2026-07-25 的盤點紀錄一併移入 `TODO-completed.md`。

---

## Persona Extraction Agent（影子模式，規劃定案）

<!-- @meta
id: persona-extraction-agent
type: DECISION
status: confirmed
last_confirmed: 2026-08-18
depends_on: personality_extractor, llm_service, lemonade_gate, member_profile_store, chat_persistence
affects: llm_service._build_chat_extra_body, discord_bot 排程, llm_runtime_config.json
-->

**目標**：把每日 04:00 的固定 pipeline 升級成 tool-calling agent，讓模型自己決定撈多少資料、追查哪些線索，產出**可稽核的 diff**（而非整份覆蓋）。**影子模式**：與現有 pipeline 並行、寫獨立表、**不動 production 排程**（[discord_bot.py:169-266](src/discord_bot.py#L169-L266) 含啟動補跑邏輯，整段不碰）。

### 本輪線上實測（2026-08-18，全部對真實服務打過）

後端＝Lemonade 11.5.0（`192.168.56.1:13305`）+ `Qwen3.8-27B-GGUF-UD-Q4_K_XL`，llamacpp recipe b9747、ctx 32768、雙卡 Vulkan0+1。

- **tool calling ✅**：`finish_reason == "tool_calls"`、結構化 `tool_calls` 正確，**4.4 秒 / 33 tok/s**（speculative decoding draft 接受率 32/33）
- **`role:"tool"` 回合往返 ✅**；**`response_format: json_schema` strict ✅**（輸出直接 `json.loads()` 過）
- → **不需自架 llama-server、不需煩惱 `--jinja`（Lemonade 已處理），M0 直接跳過**
- **併發**：1 發 33 tok/s、2 發各 11~12 tok/s、3 發各 7.0~7.5 tok/s，牆鐘皆未排隊 → llama-server **多 slot 真並行，但總吞吐固定（~22~33 tok/s）被平分**
- **prompt cache**：A 前綴冷 3,417 tok / 10.1s → 熱 18 tok / **0.3s**；中間插入不同前綴 B 之後 A 仍命中 → **多組 cache 並存**（各 slot 各自 KV）
- **大 context**：單發 11,954 tok prefill **35.2s @ 339 tok/s** 成功
- **插話 prompt 結構**：實際 13,874 字元中 **10,823（78%）是靜態 system 前綴**；[llm_service.py:463-469](src/services/llm_service.py#L463-L469) 已把 volatile 全放 user message、`asker_profile` 擺 system 末端 → **最長共同前綴已最大化，無需改動**
- **資料面（pgvector 實查）**：`data_discord_messages_index` 273,780 筆 / 81 人 / **`message_id` 100% 覆蓋**（Open Question「evidence 可否引用 msg_id」＝**是**）；訊息平均長度僅 **11~38 字**；7 天分層 A≥500:5人 / B100-499:13 / C30-99:12 / D10-29:10 / E<10:9人（5 人佔 57% 發言量）；14 天符合門檻 **46 人、337,211 字**

### 五項定案

**① `personality_model` 統一改 Qwen3.8-27B**
Lemonade `max_models.llm = 1`（embedding 有獨立 slot pool 不衝突）。現況 production 用 `Qwen3-14B-GGUF`、agent 要用 27B → 兩顆互踢，每次請求重載。統一後 04:00 不再驅逐 27B，**早上第一次插話省下 30-60s 重載（[llm_http_client.py:337](src/llm/llm_http_client.py#L337) 註解）+ ~30s prefill**。不換 quant（Q5/Q6）——tool calling 只在現有 Q4_K_XL checkpoint 上驗證過，換 quant＝換掉唯一已驗證的變數。

**② 04:00 觸發、production → agent 序列接力**
① production 萃取：16 批 × ~135s（prefill 15k tok ÷ 339 + decode 3k tok ÷ 33）≈ **40 分鐘** → 約 04:40 結束；② agent 影子：10 人 × 2~3 分 ≈ **30 分鐘** → 約 **05:10 全部收工**。agent 啟動前先看 `personality_extractor._extraction_running` 旗標（唯讀，不改 production）。**不用時鐘錯開**——既然定案「一次只做一件事」，用排隊即可。

**③ agent 跑在 bot process 內、共用 `stream_exclusive`**
一次只做一件事。**不可做成獨立腳本／獨立容器**——會繞過 [lemonade_gate.py](src/llm/lemonade_gate.py) 開頭記載的 connection reset 坑，且吞吐三分天下讓 askai 慢 3 倍（實測 33 → 7~11 tok/s）。每個 step 前主動禮讓（`stream_busy()` / `foreground_recently_active(90)` 就 sleep 再看）；agent **不得**呼叫 `note_foreground_activity()`（會壓制插話 90 秒，[llm_settings.py:378](src/sys_settings/llm_settings.py#L378)）。

**④ 補第四支工具 `get_conversation(channel_id, around_msg_id, before=15, after=15)`**
人格訊號在**互動**不在句子：實測訊息平均 14 字，「你開他」「剩我純心賞」單看零資訊。原 handoff 的三支工具只回單人碎片，模型只會**寫空話**或**腦補**——冒煙測試已示範：丟「你也太廢」→ 判「尖酸刻薄、帶有攻擊性」（實際是互損型社交）。**更關鍵：`evidence_msg_ids` 的稽核價值依賴上下文**，evidence 若是孤句，人工翻回去也驗不出對錯，防幻覺機制形同虛設。現有 pipeline 反而歪打正著（[personality_extractor.py:356](src/llm/personality_extractor.py#L356) 按時序交錯整批人訊息）→ **不補這支，agent 版會明確輸給現況**。
context 改用 **token 預算**（[tokenization.py](src/llm/tokenization.py) 估算，累計上限 24,000，留 8,000 給 thinking + 輸出），**不用「則數」**（一則可能 5 字也可能 300 字）。

**⑤ thinking 分兩段**
「呼叫哪個工具」是機械決策（schema 已限死選項，實測 thinking 關閉時 4.4s / 42 tok 就正確產出）；「新增還是修正、證據夠不夠、跟舊描述矛盾嗎」才需要推理。8 步全開 ≈ 8 × 90s ≈ **12 分/人**（10 人 2 小時）；收集關閉、只有最後產 diff 開 ≈ **3 分/人**（10 人 30 分）。

### 整體流程（定案）

每日 04:00 由 `_run_daily_maintenance_once()` 序列觸發，**一次只做一件事**：

```
04:00  ① emoji 字典更新（已拆分 ✅）
       ② 招牌梗 sweep（已拆分 ✅）
       ③ production 人格萃取   約 40 分 → auto_personality（線上功能在吃）
       ④ persona agent 影子     約 30 分 → persona_agent_versions（只有維運在看）
05:10  收工
```

③④ 寫不同的表；persona card / /askai / 插話 完全不知道 ④ 存在（＝影子模式的定義）。

agent 單人流程：

```
for 每位樣本使用者：
  ├─ 組 messages（system=任務+工具契約 / user=這次分析誰）
  ├─ loop（max_steps=8）：
  │    ├─ 禮讓：stream_busy() / foreground_recently_active(90) → 等
  │    ├─ 呼叫 LLM（thinking=OFF）帶 tools
  │    ├─ 有 tool_calls → 執行工具 → append role:"tool" → 下一步
  │    └─ 無 tool_calls 或 token 預算（24k）用盡 → 跳出
  ├─ 最終步：thinking=ON + response_format=json_schema → 產 diff
  ├─ 驗證層（程式碼判斷，非 LLM）：
  │    ① JSON 合規？        否 → rejected_schema
  │    ② evidence 存在且屬於本人？ 否 → rejected_evidence
  │    ③ confidence=low / changes 空？ 是 → 標記資料不足、不寫版本
  │    └─ 通過 → 套用 diff 產生完整 persona_text
  └─ 寫 persona_agent_versions（新版本，永不覆蓋）+ persona_agent_runs（trace）
```

逐使用者獨立 try/except：**任一人失敗不影響其他人**。

### 四支唯讀工具

| 工具 | 用途 | 備註 |
|---|---|---|
| `get_current_persona(user_id)` | 讀現有描述當 diff 基準 | 第一次讀 production 的 `auto_personality`（**必帶 `guild_id`**），之後讀自己最新版 |
| `get_messages(user_id, days, channel, limit)` | 主要資料來源 | days ≤ 90、limit ≤ 200，程式端夾住並在回傳註明 |
| `search_messages(user_id, keyword, days, limit)` | 矛盾時找佐證 | limit ≤ 50 |
| `get_conversation(channel_id, around_msg_id, before, after)` | **還原現場** | 勝負手；window ≤ 30。會回傳他人發言（與現有 pipeline 餵交錯 chat_log 同等級，非新增暴露面） |

共同規則：唯讀、白名單強制檢查（`allowed_ids`）、回傳一律 JSON 字串、例外 catch 成 `{"error": ...}` 交給模型自行修正。

### 兩張新表（普通 SQL 表，不進向量表）

`persona_agent_versions`（成品，永久保存）
- 欄位：`guild_id / author_id / version / persona_text / changes(JSONB) / confidence / notes / model / based_on / created_at`，`UNIQUE(guild_id, author_id, version)`
- 功能：①M6 評比的對照組 ②稽核（reason + evidence 可翻回現場）③救援（現行 `auto_personality` 原地覆蓋、零歷史）④切換後成為正本 ⑤v2 漂移視覺化

`persona_agent_runs`（過程 log，可定期清）
- 欄位：`run_id / guild_id / author_id / status / steps / trace(JSONB) / duration_ms / error / created_at`
- `status`：`ok / rejected_schema / rejected_evidence / max_steps / error`
- 功能：①看 agent 決策路徑（黑箱除錯）②幻覺率＝`rejected_evidence` 比例（eval 直接取數）③失敗率（M4 驗收要求）④成本觀測決定樣本規模

**為什麼不放進 `data_discord_member_profiles_index`**：①版本歷史會被語意召回撈出來當現況、污染 RAG ②不需要 embedding ③需要 `UNIQUE` 關聯約束，jsonb metadata 撐不起來。先例＝`ai_interactions`（同 DB 的普通 SQL 表）。

### M1 第一項：`think` 參數的 code 缺口

覆寫管線**完整存在**——[`resolve_request_think()`](src/services/llm_service.py#L243) 有明確優先序（override > `backends.ollama.extra_body.think` > 舊欄位 > True），一路傳到 `generate_reply(think=)` → `chat_raw(think=)` → `_build_chat_extra_body(think=)`，且已有 caller 在用（[llm_commands.py:680](src/commands/llm_commands.py#L680)、[diary_reflection.py:201](src/llm/diary_reflection.py#L201)）。

**唯一斷點**在 [_build_chat_extra_body 的 lemonade 分支](src/services/llm_service.py#L573-L588)：非 ollama 後端直接把 `think` 丟進 `ignored` 只記 debug log；其 docstring 自承「非 ollama backend 此欄位無實際作用，仍保留以向後相容呼叫端」。**這是 Ollama → Lemonade 遷移時留下的斷點**，不是缺機制。

**修法**：lemonade 分支把 `think` 映射成 `chat_template_kwargs.enable_thinking`。**預設維持 config 值、只有明確傳入才覆寫** → askai／插話／production 萃取行為完全不變。已實測 Lemonade **吃這個 per-request 覆寫**（本輪每發冒煙測試都在 body 直送 `{"enable_thinking": false}`，全部生效）。單元測試必須涵蓋「不傳參數時 extra_body 與現況位元相同」。附帶修好 [diary_reflection.py](src/llm/diary_reflection.py#L201) 的同名旋鈕（目前預設 `None`，尚未壞）。

### agent 執行期間的影響面

| 功能 | 影響 | 機制 |
|---|---|---|
| /askai、被 @ / reply 的插話 | ⏳ 排隊，最多等一個 agent step | `asyncio.Lock` FIFO 公平，agent 一步一放鎖 |
| 自發插話 / 接續 / 記憶沉澱 | ❌ **整輪跳過**（不是延後） | [ambient_reply.py:1103](src/llm/ambient_reply.py#L1103)、[:1112](src/llm/ambient_reply.py#L1112)、[memory_service.py:89](src/services/memory_service.py#L89)、[ambient_memory.py:73](src/llm/ambient_memory.py#L73) 見 `stream_busy()` 即讓位 `return` |
| 訊息寫入 pgvector | ⏳ 排隊，不掉 | [chat_persistence.py:173](src/llm/chat_persistence.py#L173) 同持一把鎖 |

⚠️ `chat_raw` 的 timeout **在取得鎖之後才起算**（[ambient_reply.py:1267](src/llm/ambient_reply.py#L1267) 註解），等鎖無上限 → agent 必須維持「一步一放鎖」，絕不可跨 step 持鎖。

### 工程節點（M1→M6）

| 節點 | 內容 | 驗收標準 | 碰 production？ |
|---|---|---|---|
| **M1** | `think` 缺口 + 四支唯讀工具 + diff schema + 單元測試 | 容器內 `unittest discover` 全綠；夾取／白名單拒絕／`guild_id` 必帶／`think` 不傳時 extra_body 不變 四類皆有測 | ❌ 完全不碰（新模組無人呼叫，行為零改變） |
| **M2** | agent loop（手寫、`max_steps=8`、禮讓、token 預算、逐步 log） | 單人跑通：log 顯示至少一次多輪工具呼叫、產出可解析 JSON、耗時落在 2~3 分/人 | ❌ dry-run，不寫 DB |
| **M3** | 驗證層 + `store.py`（ensure_table／版本遞增／寫入） | **蓄意注入不存在的 msg_id → 該筆被攔，`status=rejected_evidence`** | ❌ 只寫新表 |
| **M4** | 樣本批次 + 接進 04:00 第 ④ 步 + `personality_model` 改 27B | 單人失敗不影響其他人；失敗率記錄在 `runs` 表 | ⚠️ 第一次動排程，需重啟 bot |
| **M5** | 與 production 平行跑一週 | 同一人的兩份輸出可並排比較 | 並行不互相影響 |
| **M6** | 人工評比（具體性／幻覺率／矛盾處理／空洞比例）+ 決策文件 | 結論可以是「pipeline 更好」——那也是有效產出 | — |

**節奏**：每個 M 完成後停下來給 Jason 檢視，不連續推進。M1~M3 完全不碰 production。

**時序注意**：`personality_model` 改 27B **延到 M4 才做**。統一 27B 的目的是避免 agent 與 production 互踢模型，但 agent 到 M4 才真的跑批次；提早改只會讓 production 先變慢（20→40 分）並多一個變數。

### 退場時程（若 M6 決定採用）

```
agent 產出後多呼叫一次現有的 index_auto_personality  → 下游（persona card / askai / 插話）零改動
        ↓ 觀察一週
停掉 production 萃取（emoji 字典與招牌梗 sweep 已於 2026-08-18 拆出，不受影響 ✅）
```

若不採用：agent 留著當實驗或直接移除，production 不受任何影響。

### 主要風險

| 風險 | 對應 |
|---|---|
| agent 版**輸給**現有 pipeline | 可接受的結論（M6 明文允許）。`get_conversation` 就是為了避免這個 |
| 模型把互損文化讀成攻擊性 | 冒煙測試已重現（「你也太廢」→「尖酸刻薄、帶有攻擊性」）。diff prompt 須寫入該文化，eval 獨立列一欄 |
| context 撐爆 32k | token 預算：累計 24k 上限、留 8k 給 thinking + 輸出；用 token 不用則數 |
| agent 拖慢白天對話 | 04:00 執行 + 每 step 禮讓 + 一次只做一件 |
| 8 步不夠用 | `runs.status='max_steps'` 比例會顯示；M2 即可觀察 |

### 未定案（待 Jason 拍板）

- **樣本使用者清單**（5~10 人）與代號對應表；建議組成：A 層×2、D/E 層×2（現行 `MIN_MESSAGES_PER_USER=10` 門檻下 E 層 9 人**從未被分析過**，是 agent 最可能贏的戰場）、C 層×2、曾抽壞案例×1。**M4 才需要**
- **diff prompt 的互損文化寫法**（M2 撰寫 prompt 時一併定）

### 已完成的前置工作

- **2026-08-25｜已知盲點：agent 看不到 bot 自己的發言**：`get_conversation` 還原現場時看不到插話內容——[discord_bot.py:446](src/discord_bot.py#L446) 的 `if not message.author.bot` 擋掉了 bot 訊息，實測最近 200 則插話**沒有任何一則**進 `data_discord_messages_index`。
  **好的一面（本來就該這樣）**：不會把 bot 的發言誤算成群友的，也不會形成「bot 影響氣氛 → 人格描述反映 bot 自己的貢獻 → 又餵回 bot」的自我強化迴圈。
  **盲點**：若某段對話是「A 說話 → bot 插話 → A 回應 bot」，agent 看到的是 A 兩句自言自語，中間那句不見了，可能誤判成自問自答或語意跳躍。目前幾次執行沒觀察到誤判（引用的證據都是真人對話），但**插話頻繁的頻道風險較高**。
  **對照**：插話／askai 的 prompt **有**帶 bot 自己的回覆（`llm_service` 的 `bot_history`，渲染成 `<bot_history name="...">`，用途是讓模型認出 chat_history 裡哪幾行是自己講的）。所以「bot 看得到自己、agent 看不到 bot」是兩條路徑的刻意差異，不是遺漏。
  **若日後要補**：`ai_interactions` 表存有插話的 `reply_message_id` 與 `reply_text`，可在 `get_conversation` 的時間視窗內併入，但要標明是 bot 發言、且要重新評估回饋迴圈風險。

- **2026-08-19｜prompt 改為三層疊加（修掉我自己造的重複輪子）**：使用者指正「新增功能前先看有沒有原本的輪子，一直加獨立的會崩潰」。比對後確認 `persona_agent_prompt.json` 與 `personality_extraction_prompt.json` **13 條核心規則全部重疊**（角色設定／只能繁中／不要編造／自訂表情 `:xxx:` 規則／嚴禁廢話清單／要寫出跟別人不一樣的地方／角色定位…）。問題不只冗餘——**日後調整其中一邊，另一邊會靜默分岔**，與「招牌梗 sweep 黏在萃取裡」同類。
  **改法（比照 `persona_examples.txt` 被 /askai 與插話共用的既有慣例，共用的是檔案、兩邊各自讀）**：
  ① 新增 `persona_description_rules.txt`＝描述品質規則（原本嵌在萃取的 `user_prompt_template` 裡）
  ② `personality_extraction_prompt.json` 該段換成 `{description_rules}` 佔位，`personality_extractor.load_description_rules()` 代入（讀檔失敗回空字串，不讓附加檔案缺失拖垮 04:00 排程）
  ③ `persona_agent_prompt.json` 砍到只留 `system_layer`＝**agent 專屬**（工具工作流、互損文化判讀、資料不足就說不足），896 字 → 691 字
  ④ `agent.load_prompts()` 三層疊加：萃取 system_prompt ＋ 共用描述規則 ＋ agent 層，雙檔 mtime 快取
  **測試**：新增 `PromptLayeringTests` 4 項，其中一項專門斷言「agent 層不該再抄一份共用規則」，避免下一輪漂回複製貼上；另一項守住萃取的 `{description_rules}` 有被代入（漏掉會把佔位符原樣送給模型）。**刻意不寫 golden-string 測試**——prompt 常手動微調，那會讓啟動 gate 動不動就紅。gate **267 測試全綠**。

- **2026-08-19｜`/persona_agent_test` admin 除錯指令（未 commit，需重啟 bot 才會註冊）**：補完 M2 驗收的必要工具——agent 必須跑在 **bot 自己的 process 內**才測得到真實行為（`stream_exclusive()` 是 process-local，用 `docker exec` 在旁邊跑會讓禮讓機制完全失效，實測導致 context 超限與吞吐 33→7 tok/s）。位置：`PersonalityCommands` cog（`llm_commands.py`），參數 `target`（成員）+ `model`（選填），`administrator=True`。**只讀不寫**：結果回 Discord + 完整寫 log，不碰任何資料表。設計細節：①先 defer 再回一則「已開始」，實際執行丟 `asyncio.create_task` + `_track_task`（agent 可能跑數十分鐘）②**完整 diff 一律進 log**——followup token 只有 15 分鐘，跑久了送不出去也不能讓結果消失③diff 以 `discord.File` 附件回傳，避免 2000 字限制④白名單只放 target 一人，工具層會擋掉其他查詢。**修掉一個只在失敗路徑才會觸發的 bug**：`discord.py` 的 `file` 預設是 `MISSING` 哨兵而非 `None`，`file=None` 會炸，而「沒有 diff」正好就是 error / context_exceeded 路徑 → 改成條件帶入 kwargs。指令由啟動時的 `tree.sync()` 自動註冊（全域指令，可能要等一下才出現在 Discord UI）。

- **2026-08-18｜M2 完成（安靜使用者驗收通過，未 commit）**：`persona_agent/agent.py`（手寫 loop）+ `TOOL_DEFINITIONS`／`dispatch()` + `settings/prompts/persona_agent_prompt.json`（system／user／final 三段，含**互損文化**教學）+ `test_persona_agent_loop.py`。gate **263 測試全綠**。
  **驗收案例＝安靜使用者 `275276661312847872`（7天 1 則／14天 5 則／90天 91 則）**——正是專案要解的痛點：
  - production（14 天視窗）只能寫出「低調觀察者，**僅出現兩次**提及伺服器差異…未展現強烈個人立場」
  - agent 判斷資料不足 → **自行擴大到 90 天** → 找到 91 則 → 產出 2 add／1 revise／2 keep，notes 明寫「90 天內有 91 則發言，足以推翻『僅出現兩次』的舊描述」
  - **evidence 16 個全部真實存在且屬於本人（16/16，零幻覺）**——M3 的過濾器提前驗過一次
  - **互損文化判讀正確**：notes 寫「粗口與貶義詞多為群內互損或針對外部人物，不等同對群內成員攻擊」，並把「對外部人物的批評」與「群內互損」分成兩個 trait（比 prompt 教的還細）。冒煙測試那個「你也太廢→尖酸刻薄、攻擊性」的失敗模式未再出現
  **限度**：n=1；agent 看 90 天 vs production 看 14 天不是控制變因（但「自己決定撈多久」正是設計優勢）；**活躍使用者尚未成功跑完**。
- **2026-08-18｜測試方法的坑（重要，已修正認知）**：前四次 dry-run 全失敗（context 超限／timeout／裁切produced 假陰性）。根因**不是顯卡或伺服器**（`backend_health=ready`、無 watchdog reset），而是**我用 `docker exec` 在另一個 process 跑 agent** → `stream_exclusive()`／`stream_busy()`／`foreground_recently_active()` 都是**模組層、process-local**，兩把鎖互不相干 → 禮讓機制**從未觸發**（四次 log 中「禮讓前景」出現 0 次），agent 與 bot 的插話**正面對撞**（同時段 bot 跑了 15 次 ambient/askai）。後果：共用 KV 池被瓜分 → ~12k 就 `Context size has been exceeded`（單獨跑 24k 都過）；吞吐 33 → 7~11 tok/s → 最終步連 600s timeout 都不夠。**這反而實測證實了「agent 不可做成獨立腳本」這條定案**。修正：裁切機制整段移除，改 `status="context_exceeded"`（不產出降級結果，明晚重跑）；預算計入每次重送的 `TOOL_DEFINITIONS`（832 token）；`get_messages` 預設 200→60、上限→120；prompt 限制 `get_conversation` 最多 5 次（實測模型會叫到 9 次撐爆預算）。
  **待辦**：活躍使用者必須在 **bot process 內**跑一次才算完整驗收 → 需要一個 admin 除錯指令（M4 也會用到）。
  **待定政策（無限重跑防護，M3 建 runs 表時實作）**：連續失敗 1 次→預算降 70%；2 次→降 50% 且 `get_conversation` 上限降 3；≥3 次→跳過並記 `quarantined` 列進維運報告。**重點不是省 GPU（一人一晚約 3 分鐘），是避免沉默失敗**。

- **2026-08-18｜M2 實作中的關鍵發現：可用 context 是浮動的共用資源**：第一次 dry-run 撞 `Context size has been exceeded`（HTTP 500）。探測後確認**不是硬上限問題**——單發 24,110 token 可過（`ctx_size=32768`），但同時段一個約 17k 的請求卻爆掉，因為 llama-server 的 KV 由多個 slot 共享，/askai 或插話同時在跑就會縮水。三道處置：
  ① **工具 payload 精簡**：`get_messages` / `search_messages` 拿掉恆定的 `author_id`、`channel`，時間戳砍成台北時間 `MM-DD HH:MM`（原本每則帶完整 ISO + 微秒）。200 則從 **35,103 → 15,812 字元**（估算 token 10,395 → 6,764）。`get_conversation` 保留 `author_id`（那裡作者會變，是判讀互動的關鍵）。
  ② **預算逐次檢查**：模型會在同一步丟出多個 `tool_calls`（實測一步六個 `get_conversation`），原本只在步末檢查預算完全來不及。改成每個 call 前檢查，超出後仍回覆每個 `tool_call_id`（協議要求）但換成佔位字串。`TOKEN_BUDGET` 24,000 → **9,000**。
  ③ **context 超限自動恢復**：`_call_model()` 偵測到 `Context size has been exceeded` 就把較早的 `role="tool"` 內容換成佔位字串（**不刪訊息**——`tool_call_id` 必須與 assistant 的 `tool_calls` 一一對應）後重試一次。估算擋不住浮動的共用資源，必須能從中恢復。

- **2026-08-18｜聊天表加索引（手動指令，刻意不寫進程式碼）**：`data_discord_messages_index` 原本**只有 pkey**，工具全表掃描。手動建三個表達式索引 + `ANALYZE`（統計沒更新時規劃器估 456 筆／實際 265,118 筆 → 走 Bitmap Scan 全撈再排序，是主要元兇）：
  ```sql
  CREATE INDEX CONCURRENTLY discord_messages_idx_author_ts  ON data_discord_messages_index ((metadata_->>'author_id'), (metadata_->>'timestamp'));
  CREATE INDEX CONCURRENTLY discord_messages_idx_channel_ts ON data_discord_messages_index ((metadata_->>'channel_id'), (metadata_->>'timestamp'));
  CREATE INDEX CONCURRENTLY discord_messages_idx_message_id ON data_discord_messages_index ((metadata_->>'message_id'));
  ANALYZE data_discord_messages_index;
  ```
  配套：`tools.py` 的時間比較從 `::timestamptz` 改**字串比較**（轉型是 STABLE 無法建索引；全表 `+00:00` ISO 字串的字典序 == 時間序，與 `personality_extractor.fetch_recent_messages` 寫法一致）。實測 `get_messages` 752→**38ms**、`get_conversation` 3,551→**28ms**、`get_current_persona` 154→**7.5ms**。順帶加速 `context_retriever` / production 萃取（同一張表）。
- **2026-08-18｜M2 管線缺口先行補上**：`chat_raw` 只回 content 字串、也不能送 `tools` / `response_format` → agent loop 無從取得 `tool_calls`。抽出共用的 `_chat_completion_checked()`（模型載入／vision 轉換／`stream_exclusive`／連線層 anomaly＋快照／`no_choices` 判讀），新增 `chat_with_tools()` 回傳 `ChatMessageResult(content, tool_calls, finish_reason, usage)`。**關鍵差異**：tool-calling 時空 content 是正常結果，故只在 content 與 tool_calls **同時為空**才判 `empty_content`（`chat_raw` 維持原本的空 content 即錯誤）。因共用同一條路徑，agent 自動遵守「一次只做一件事」。已用真實服務驗證 tool_calls 往返、`json_schema` strict 輸出、以及 `chat_raw` 無回歸。
- **2026-08-18｜M1 完成（未 commit）**：`llm/persona_agent/` 新套件（`tools.py` 四支唯讀工具、`schema.py` diff strict schema、`__init__.py` re-export）+ `llm_service` 的 `think` 缺口修補（`resolve_request_think` 改 backend-aware、`_build_chat_extra_body` 的 lemonade 分支把 `think` 轉成 `chat_template_kwargs.enable_thinking`，**僅在明確傳入時覆寫**故既有 caller 行為不變）+ 兩支測試（`test_persona_agent_tools.py` 16 項、`test_llm_think_override.py` 15 項）。容器內 gate **242 測試全綠**（原 211）。另對真實 DB 做過煙霧測試，四支工具皆通。**M1 完全不碰 production 執行路徑**。

- **2026-08-18｜04:00 排程三步驟拆分（commit `5b69042`）**：招牌梗 sweep 從 `_run_personality_extraction_impl` 移到 `signature_tag_extractor.run_signature_tag_sweep()`，`_run_personality_extraction_once` 更名 `_run_daily_maintenance_once` 並拆成 emoji／sweep／萃取三個各自 try/except 的步驟。**未來換掉萃取只需動一行**；順帶修掉「手動預覽（`write_rag=False`）會誤觸真實刪梗／降級」。容器內 211 測試全綠。
- **2026-08-18｜清除 `auto_personality` 殭屍列**：12 筆 `guild_id='0'` 的舊格式殘留（`last_extracted_at` 為空、author_id 與正式版完全重複）已刪除，現為 65 筆／65 人完全對齊。原本無害（[context_retriever.py:771](src/llm/context_retriever.py#L771) 有 guild_id 過濾），刪除理由是避免新寫的 `get_current_persona` 漏帶 `guild_id` 時撈到舊基準產出錯誤 diff。**工具層仍強制帶 `guild_id`——正確性不靠資料剛好乾淨。**

---

## Telegram 漏收事件自動補掃（2026-08-02 已實作；2026-08-18 補上「中段缺口」盲區，待部署驗證）

<!-- @meta
id: telegram-catchup-sweep
type: STATE
status: confirmed
depends_on: telegram-multi-source
affects: telegram-relay
last_confirmed: 2026-08-18
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
- **序列化鎖**：即時事件 / 補掃 / refetch 三條路徑共用一把 `process_lock`，避免同一則訊息並行處理造成重複下載媒體。
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

---

## Telegram 媒體 spoiler（防雷）未帶到 Discord（2026-08-18 已實作，待部署驗證）

<!-- @meta
id: telegram-media-spoiler
type: STATE
status: confirmed
depends_on: telegram-catchup-sweep
affects: telegram-relay
last_confirmed: 2026-08-18
-->

**症狀**：Telegram 影片有加 spoiler，轉到 Discord 沒有打碼。

**診斷**：DB `telegram_message_media` **2696 筆 `is_spoiler` 全為 false**，零筆 true。relay 端其實**早就接好了**（`TelegramMediaRecord` → `AttachmentSpec` → `discord.File(spoiler=...)`，discord.py 2.7.1 會自動加 `SPOILER_` 檔名前綴；圖片路徑也已有「首圖若為 spoiler 就不塞進 embed、改走附件」的分支）。唯一斷點在 scraper 寫入端。

**根因**：[handlers.py `_build_media_item`](src/telegram_scraper/handlers.py#L140) 讀 `message.media_unread`——那是「媒體尚未被檢視」（語音/圓形影片用），與防雷無關。真正的旗標在 **media 物件**上：`MessageMediaPhoto.spoiler` / `MessageMediaDocument.spoiler`（已用 Telethon 1.43.2 的 `inspect.signature` 確認欄位存在）。

**實作**：
- [handlers.py](src/telegram_scraper/handlers.py)：`is_spoiler` 改讀 `getattr(media, "spoiler", False)`。
- [db.py](src/telegram_scraper/db.py)：新增 `update_media_spoiler(message_pk, is_spoiler)`，`WHERE ... AND is_spoiler IS DISTINCT FROM $2` → 值沒變就不寫。
- [handlers.py](src/telegram_scraper/handlers.py)：「媒體已存在，略過下載」分支補呼叫回填。**沒有這段的話舊資料永遠錯**（該分支整段跳過 `upsert_media_items`），`/resend_article` 舊 spoiler 影片仍不會打碼。

**已驗證**：
- scraper 端 5 案全過（影片/圖片 × spoiler 真假 + 無媒體），並對照出舊寫法對 spoiler 影片確實回傳 False。
- `discord.File(..., spoiler=True)` 實測輸出檔名 `SPOILER_clip.mp4`。
- 回填 SQL 以 `BEGIN/ROLLBACK` 實測：值有變 → `UPDATE 1`、值相同 → `UPDATE 0`；回滾後全表 2696 筆未動。

**未 commit。下一步**：重啟 `telegram-scraper`，啟動歷史掃描（168h）會順手把近 7 天媒體的 spoiler 旗標校正（log 出現 `已校正 spoiler 旗標 message_pk=...`）；之後新的 spoiler 影片轉到 Discord 應顯示為需點擊的模糊附件。**注意**：Discord 已發出的舊訊息無法回頭補打碼，回填只影響 DB 正確性與日後 `/resend_article`。

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
- 檔案：`src/llm/ai_interactions_store.py`(新)、`ambient_reply.py`、`diary_reflection.py`、`discord_bot.py`(on_ready 建表 + 反應 hook)。

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
| `src/llm/ambient_reply.py` `_load_ambient_prompt` | 多組 learned_style 一層 |
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
- [x] 模型協調（取代「優先序佇列」的最小落地）：[lemonade_gate.py](src/llm/lemonade_gate.py) 加 `stream_busy()` + `note_foreground_activity()` / `foreground_recently_active(grace)`；/askai 在 `_handle_askai_request` 起點與 worker `finally` 兩處標 foreground → 背景插話於 grace 窗口內讓位。**注意：尚未做真正的優先序佇列**，只做「foreground 活躍時背景讓位 + 共用 `stream_exclusive` 序列化」；directed(@) 仍會在 /askai 窗口觸發 swap（罕見、可接受）。
- [x] 新檔 [src/llm/ambient_reply.py](src/llm/ambient_reply.py)：硬過濾 + 冷卻/上限 + foreground 讓位 + 機率 + @/reply 必回 + 12B 生成（`generate_reply(model=ambient_model)`，沉默 sentinel 不發送）。**Phase A 範圍調整**：(a) 判斷與生成**合為一次 12B 呼叫**（prompt 允許回 `[PASS]`＝沉默），未做獨立 judge；(b) **react 檔次延後**（Phase A 只有 回/沉默）；(c) **檔1 persona card 改到 Phase B**，Phase A 記憶＝近期 `channel.history` 短期脈絡（零 pgvector）。
- [x] [discord_bot.py](src/discord_bot.py) `on_message` 加 `asyncio.create_task(maybe_ambient_reply(bot, message))`。
- [x] 新 prompt [ambient_reply_prompt.txt](src/settings/prompts/ambient_reply_prompt.txt)（純「插話行為」規則、`[PASS]` 沉默）；**system 疊用共用身份 `persona_identity.txt`（琇紫）→ 插話與 /askai 同一角色**。注意：這是 bot 自己的「身份 prompt」；「認得別人是誰」的 per-user persona card 仍在 Phase B。
- **靜態檢查**：全檔 py_compile PASS；JSON valid；lemonade_gate 協調函式 standalone 測試 PASS（本機無 discord 套件，完整載入須在 docker）。
- **待 docker 驗證**：`docker compose restart discord-bot` → `/setch` 設「AI 插話頻道」→ 該頻道閒聊看是否偶爾插話、@ 必回、非白名單靜默、/askai 進行時讓位。
- **可調手感（config 起始值）**：base_probability、cooldown_seconds、hourly_cap、askai_grace_seconds。

#### B — 認得人（persona card 召回；檔1 提前到此）
- [ ] `ambient_reply` 接 `retrieve_rag_context_sync(question, guild_id, requester_user_id, participant_user_ids, …)`（吃純 id、**不需 interaction 重構**），把在場成員 persona card 轉成 `persona_context` 餵 `generate_reply`。
- [ ] participant_user_ids ＝ 近期 `channel.history` 的發言者 + 當前作者；executor 跑（sync LlamaIndex）；best-effort（失敗→None）。
- [ ] per-channel persona 短 TTL 快取（~60s），避免 armed 期間每則都打 pgvector。embedding 走 Lemonade 獨立 port（**不卸載 12B**，無 swap 風險）。
- **驗收**：群裡有 persona card 的人講話，琇紫接話帶得出對方調性；沒卡的人也不會卡住（degrade 成只有對話脈絡）。
- **延後（非 v1 必要）**：`retrieve_discord_context` 泛化吃 channel 的 hybrid 長期對話召回——觸碰 /askai 核心、風險高，等 B 的 persona 召回不夠用再做。

#### C — 偏好事實 preference_fact（檔3：自我進化、全自動、自他分流）
> 政策（2026-06-21 定案）：**只記「本人講自己」的中性偏好；敏感(健康/感情/家庭/財務)一律自動丟、不存；他人評他人/紅線自動丟。多次提到才升等。全自動、零審核佇列。**

**共享接口（2026-06-21 建）**：[`MemoryService`](src/services/memory_service.py)（門面，單例）——任何功能只呼叫它、不碰底層：`recall / list_facts / extract / remember / observe / forget / format_recall`。底層委派 `intro_rag_port`(儲存) + `preference_extractor`(抽取/升等)。未來 /askai、功能一、/remember、管理面板都走這個。

- [x] **C-1 儲存層**：`PgVectorIntroRAGPort.index_preference_fact / list_preference_facts / delete_preference_fact`；`profile_kind="preference_fact"`，metadata：`{author_id, fact, fact_key, category, confidence, status, mention_count, first_seen, last_seen}`。doc_id 含 fact_key 雜湊 → 同事實 replace 不重複。**隔離已驗證**：persona 讀取器 SQL 白名單只撈 intro/auto/impression，preference_fact 不會混進 /askai/Phase B。
- [x] **C-2 抽取+守門**：[preference_extractor.py](src/llm/preference_extractor.py) `extract_preferences`（12B、[守門 prompt](src/settings/prompts/preference_extractor_prompt.txt)：自他分流/敏感丟/紅線丟、輸出 JSON）+ `_parse_facts`（容錯）。
- [x] **C-2 corroboration**：`ingest_preferences`——confidence 濾（<0.6 丟）→ 批內去重 → 依作者讀既有 → 命中 `mention_count++`（≥2 升 trusted）否則新建 tentative。
- [x] **C-3 串接**：[ambient_memory.py](src/llm/ambient_memory.py)——`enqueue_for_memory`(插話頻道每則收緩衝) + `maybe_flush`(背景排程、**閒置才跑 12B**) + `recall_lines`(召回 trusted 注入 persona_context)；`ambient_reply` 與 `discord_bot` on_ready(每 180s 檢查) 已接。
- [ ] **C-4 自我進化迴圈**（閒置批次）：consolidation（合併重複、衝突取新記「以前X現在Y」）、decay（久未重提降權/封存）。**未做**。
- [ ] **C-4 隱私公告**：綁定插話頻道時自動置頂 + 改 channel topic。**未做**。
- [ ] **C-4 選配監督面板**（不擋流程）：查/改/刪/禁記；複用 `/personality_extract` UI 模式。**未做**（接口 `MemoryService.list_facts/forget` 已備好）。
- [ ] **觀測 / Debug 面板（使用者要求 2026-06-21，重要）**：使用者**不想用 CLI/log debug**，未來要一個 **Discord 面板** 能看：每次插話的**完整 prompt（含三層 context）**、決策狀態（reply/pass/error）、三層 context 數量（chat/persona/memory）、記憶 flush 狀態、某人記得的偏好。**取代** `ambient_prompt.txt` + grep。可與「記憶監督面板」合併成一個「AI 狀態/觀測面板」。**現況暫用**：`discord_bot.log` 的 `ambient 生成 …chat/persona/memory` 摘要 + [`/logs/ambient_prompt.txt`](src/llm/ambient_reply.py)（`AmbientChatSettings.debug_log`）；面板做好後轉成資料來源。
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
| `src/llm/ambient_reply.py`（新） | 硬過濾 + 12B 判斷 + 背景生成 | A |
| `src/discord_bot.py` | `on_message` 加 ambient 分支 | A |
| `src/settings/prompts/ambient_reply_prompt.txt`（新） | 輕量插話人設 | A |
| `src/llm/context_retriever.py` | `retrieve_discord_context` 泛化吃 channel | B |
| `src/llm/preference_extractor.py`（與功能一共用） | 12B 傾聽 → 偏好事實抽取（共享層） | C |

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
2. **120s 後裸送、無指向**（[ambient_reply.py:1032](src/llm/ambient_reply.py#L1032) `channel.send`）→ 多人多主題頻道必然像亂入。**這才是「不知道加入哪個主題」的真正成因**：它選的時候那條線還在，講出來時已經沒了。
3. 第一則就開跑 → 上下文半截；`max_passes_per_burst=3` → 一段 burst 最壞燒 6 分鐘。
4. **A↔B 對線**這種零成本可判的，現在花 120s 讓模型判（prompt 第一關 gate #3）。
5. **講完就跑**：除非被 @，否則不理會別人對它的回應 → 沒有來回感。
6. 等鎖排隊不計入 `pass_timeout_seconds`（[ambient_reply.py:988](src/llm/ambient_reply.py#L988) 註解已載明）→ 實測 max 901s。

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
- **k-NN（非 LLM 推理）**：`get_text_embedding(近 3 則)` → `ai_interactions` 最近鄰 20 筆 → 「過去語意相近情境下插話被接的比率」當一個特徵。基礎設施（embedding 欄位 + hnsw + [fetch_similar_positive](src/llm/ai_interactions_store.py#L289)）已存在。
- **組合**：負鉤子否決 → `sigmoid(w·features) >= threshold`。**threshold 是唯一旋鈕**（調高＝話少）。
- **權重來源**：logistic regression，樣本＝5602 筆，特徵 <10 個。**係數可讀**＝看得出它為什麼開口，可定期重訓。

**學習標籤換掉**：不用 reaction（負向僅 13 筆，「什麼時候該閉嘴」學不出來），改用「**插話後 5 分鐘內有沒有人接話/回它**」——真人插話成功的定義本來就是話被接下去。此標籤可從 `ai_interactions`(`reply_message_id`+`channel_id`+`ts`) 配合 chat 歷史庫**回溯計算 5602 筆全量**，不必等新資料。

**已知統計限制**：5602 筆全是「已插話」樣本、無反例 → 學到的是「已想插話的情況下什麼形狀會被接」（ranking），不是「該不該插話」（causal）。可接受，但**門檻值必須上線後觀察調整，不能直接從迴歸結果讀出**。

#### 自循環 feedback 盤點（2026-08-09）

| 迴路 | 狀態 | 防護 |
|---|---|---|
| **回音迴圈**（回 bot／自己） | 既有，**不動** | 入口 `message.author.bot` 一律排除（[ambient_reply.py:644](src/llm/ambient_reply.py#L644)）；chat_history 裡自己的行標「(你自己)」 |
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
| `src/llm/ambient_reply.py` | debounce 迴圈、鉤子閘接入、`#N` 解析、reply 錨定送出、新鮮度檢查、L4-b |
| `src/llm/ambient_hooks.py`（新） | 結構鉤子 + regex + k-NN + 迴歸打分 |
| `src/llm/chat_line.py` | `#N` 從「僅被回覆過的行」改為每行都給（[chat_line.py:107](src/llm/chat_line.py#L107)） |
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
| `src/llm/ambient_hooks.py`（新） | 結構鉤子 + regex + k-NN + sigmoid 計分 + ε-greedy；失敗一律 fall-open（交給模型 `[PASS]` 把關，不讓鉤子壞掉就整個功能啞掉） |
| `src/llm/ambient_reply.py` | `note_typing` / `_wait_for_quiet` / `_is_followup_to_bot` / `_parse_line_choice` / `_passes_content_gate`；入口加靜默期與 followup 分派；pass 接鉤子閘、reply 錨定送出 |
| `src/llm/chat_line.py` | `_thread_render` 每行給編號 + 回 `{編號: 訊息}`；`fetch_recent_lines` 加 `thread_map` out-param（不改回傳簽章＝不動既有 caller） |
| `src/llm/ai_interactions_store.py` | 加三欄（見下）；`mark_got_reply()`；`fetch_reply_rate_stats()` k-NN |
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
- **資料**（動態、每次不同）→ 只能在 bundle 層：`llm_service._build_prompt_bundle` 新增
  `situation_signals` 參數與 `<situation_signals>` 區塊 + 一句中性 header。/askai 不傳就不出現
  （與 `style_refs` 同模式）。
- **使用規則**（靜態、要能熱改）→ 放 `ambient_reply_prompt.txt`。**理由是「誰在用」**：
  `recalled_context`/`style_refs` 是 askai+ambient 共用 → 說明放共用的 llm_service 合理；
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
（[emoji_text_utils.py:8](src/llm/emoji_text_utils.py#L8) 的註解早就寫明「不動 mention」，一直沒人補）。

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
