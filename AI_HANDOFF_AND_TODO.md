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
- 2026-06-25（插話除錯）：**修「B 回覆 A 再 @ 機器人問意見 → 看不到 A 寫什麼就亂答」**。根因：Discord 原生 reply 的 `message.reference` 全程只被 [_is_directed](src/llm/ambient_reply.py) 拿來判「是不是回覆機器人」，**被回覆訊息的內容從未進 prompt**；模型只拿到 `<latest_user_message>`(B 的字) + `<chat_history>`(B 之前 20 則, `history_limit=20`)。A 那句要嘛已滾出視窗、要嘛在視窗內但**沒有連結標記**告訴模型「B 的問句是衝著這行來的」→「他/這個/這樣」無指涉 → 腦補亂答。**修法**（本輪定案：範圍 b 含自發、帶圖、不去重、不碰 /askai）：①[ambient_reply.py](src/llm/ambient_reply.py) 新增 `_resolve_replied_to()`（reference.resolved 三態 Message/Deleted/None；None 時 `fetch_message` 補抓一次，best-effort）；directed 與自發插話都在 `generate_reply` 前算 `replied_to_from/_text`，並把被回覆訊息的圖也併進 vision payload（trigger 自己的圖優先、整體受 `image_max_count=1`）。②[llm_service.py](src/services/llm_service.py) `_build_prompt_bundle`/`generate_reply` 加 `replied_to_from/replied_to_text` 兩參數，在 `<latest_user_message>` **正上方**輸出 `<reply_to from="A#XXXX">…</reply_to>` + 一行指引（把「他/這個/這樣」對準 reply_to，別跟 chat_history 其他話題搞混）。③debug 摘要加 `reply_to=` 計數。py_compile PASS、callers 全 kwargs 不受影響、**未 commit**。**下一步**：docker 重啟 → 實測「B reply A → @機器人問意見」「reply 帶圖」兩情境，看 `ambient_prompt.txt` 有 `<reply_to>` 區塊且回答對準 A。**未做（可選）**：/askai 同缺口（本輪不碰）。
- 2026-06-21（Telegram relay 除錯）：**長訊息 embed 撞 Discord 500、回放無限重試 — 已修截斷上限**。症狀：`message_pk=7616`（2026-05-21 舊訊息回放）每輪 `channel.send` 都 `500 Internal Server Error (error code 0)`、latency ~45s（discord.py 5xx 重試耗盡）。**實際查 DB 驗證**（telegram_data）：7616 文字 4091 字、無 media/控制字元/surrogate/壞 URL、title 15、timestamp 正常 → **payload 形式上合法**。對照本頻道 2138 筆成功訊息**最長僅 3012 字、超過 3500 字 0 筆成功** → 與成功訊息唯一差異就是長度。根因＝Discord 後端對接近 4096 上限的超長 embed description 回 500（非乾淨 400）；舊 code `content[:4000]` 剛好頂在地雷區；又因回放走 `force_replay` 跳過去重 → 同筆每輪重撞同一 500、卡死回放。**修法**：[TelegramRenderAdapter](src/services/telegram_relay_service.py#L579) 加 `_DESCRIPTION_MAX_CHARS=3000`（保守低於實測安全線 3012）當「每段」上限。**最終採分段而非截斷**（使用者要保留全文且看得出是連續文章）：新增 `_split_text()`（盡量在換行/空白邊界切、不切斷句子；**暴雷安全**：切點不落在 `||` 中間，切完平衡每段 `||`，暴雷跨段時前段補 `||` 收尾、下段補 `||` 開頭，標記不破、暴雷不外洩），`render()` 改成**每段產生一個 RenderOperation**（publisher 本就逐 operation 發送 → 自然多則）；續段標題加「（續）」、footer 加頁碼「i/n」，附件只掛第一段。實測 7616：4091 字 → 2 段（2790+1299，皆 ≤3000，段1 切在句末換行）。py_compile PASS、**未 commit**。**未做（未定案）**：回放「毒訊息」dead-letter（同筆連續失敗 N 次 → 略過，避免單筆永久堵塞補送）。**下一步**：部署後重跑回放，確認 7616 送成 2 則連續訊息、`telegram_relay_result` 由 `failed_or_skipped` 變 `published`、迴圈停止。**選配**：用 webhook 跑 `/tmp/discord_len_test.py` 長度掃描，坐實 500 門檻（目前未跑）。
- 2026-06-21（部署除錯）：**Lemonade 兩個地基問題排除（embeddings + 12B ctx），功能二 Phase C 完整實作**。①**embeddings 501**：Lemonade llamacpp 只有模型帶 `embeddings` 標籤才傳 `--embeddings`（[issue #1745](https://github.com/lemonade-sdk/lemonade/issues/1745)）；user-pull 的 `Qwen3-Embedding` 沒標籤 → 501。修法＝補標籤 / 我在 config 加 `llamacpp_args:"--embeddings"`。embeddings 通 → RAG 滿血 + Phase C 寫入可運作。②**12B ctx 卡 4096**：根因是 bot 的 `/api/v1/load` 送 **nested `recipe_options`**，但 Lemonade 文件要**平鋪參數**（[server_spec](https://github.com/Mintplex-Labs/lemonade-sdk/blob/main/docs/server/server_spec.md)；ctx_size bug [#1817](https://github.com/lemonade-sdk/lemonade/issues/1817) 只在 vLLM、llamacpp 正常）→ 改 [llm_http_client.py:_lemonade_load_model](src/llm/llm_http_client.py) 送**平鋪 ctx_size**（不帶 reserved 旗標、不帶 `save_options`，避免污染使用者 Lemonade 持久設定）→ **12B ctx=16384**。連帶把為 4096 加的精簡放寬回完整（history 12/persona 5/recall 6）。
  - **⚠️ 教訓（save_options 翻車）**：曾用 `llamacpp_args:"--embeddings"` + `save_options:true`，把 `--embeddings`（Lemonade reserved、由標籤管理）**baked 進持久 `recipe_options.json`** → 之後每次載入都 `model_load_error: --embeddings cannot be overridden`，embed model 整個掛掉、重啟還復發。**最終解**：`POST /api/v1/load {model_name, ctx_size, merge_args:false, save_options:true}` 一次覆寫掉持久的毒（`merge_args:false`＝不 merge 持久自訂 args）；或手動清 `%USERPROFILE%\.cache\lemonade\recipe_options.json` 的該筆。**結論：bot 絕不要送 reserved 旗標、也不要用 `save_options` 寫使用者的 Lemonade 設定。**③**Phase C 全鏈完成**（見功能二區塊，C-1~C-3 [x]）+ `MemoryService` 共享門面 + ambient debug 觀測（`/logs/ambient_prompt.txt`）+ reply 對已刪訊息 fallback 直接發頻道。**未 commit**。**下一步**：重啟 bot 套新設定 → 端到端測插話/記憶 → 之後做 C-4（consolidation/decay/觀測面板）。
- 2026-06-21（續）：**persona prompt 模組化 + 功能二 Phase B（認得人）+ 記憶設計定稿**。①**persona 重構**：把共用性格/語氣/色色分寸/§19§25 紅線/語言規則從 [askai_system_prompt.txt](src/settings/prompts/askai_system_prompt.txt) 搬進共用的 [persona_identity.txt](src/settings/prompts/persona_identity.txt)（/askai 留任務框架：回答風格/網路引用/人物對照）；ambient 與 /askai 從此**同一個琇紫**。內容等價、**順序微調 → 待 user 重測 /askai**。②**Phase B 認得人**：[ambient_reply.py](src/llm/ambient_reply.py) 接 `retrieve_rag_context_sync`（吃純 id，executor 跑，per-channel 60s 快取，embedding 走 Lemonade 獨立 port 不卸載 12B）→ persona card 進 `persona_context`。③**記憶設計定稿**（見功能二區塊 Phase C + 預設決策）：**只記本人中性偏好；敏感(健康/感情/家庭/財務)直接丟不存；他人/紅線丟；多次提到才升等(tentative→trusted≥2)；全自動零審核；治理＝AI 自我進化(抽取→升等→消化→淡忘)+選配監督面板**。靜態 py_compile PASS。**C（preference_fact 寫入管線）尚未實作**。
- 2026-06-21：**功能二「AI 偶爾插話」Phase A 實作完成（待 docker 驗證）**。新增 [ambient_reply.py](src/llm/ambient_reply.py)（硬過濾→冷卻/上限→foreground 讓位→**12B 判斷**，沉默 sentinel `[PASS]` 不發送；@/reply 必回）。**插不插由 12B 決定、不擲骰**——「偶爾」靠冷卻+上限；機率退為 `judge_sampling_rate` 純減壓閥（預設 1.0 不作用，太吵才抽樣降載）。配套：`ambient_model: Gemma-4-12B-it-GGUF` 進 [llm_runtime_config.json](src/sys_settings/llm_runtime_config.json)（+ctx 8192）、`LLMRuntimeConfig.ambient_model` + `LLMService.resolve_ambient_model()`、`AmbientChatSettings`、[channel_registry](src/settings/channel_registry.py) 加「AI 插話頻道」、[lemonade_gate](src/llm/lemonade_gate.py) 加 `stream_busy/note_foreground_activity/foreground_recently_active`（/askai 兩處標 foreground）、`bot.ambient_tracker`、`on_message` create_task、[ambient_reply_prompt.txt](src/settings/prompts/ambient_reply_prompt.txt)。**Phase A 範圍調整**：判斷+生成合一次 12B 呼叫（非獨立 judge）、react 檔次延後、persona card(檔1) 移到 Phase B（Phase A 記憶＝`channel.history` 短期脈絡）。**未做**：真正優先序佇列（目前靠 foreground 讓位 + `stream_exclusive` 序列化；directed@ 仍可能在 /askai 窗口觸發 swap）。靜態：py_compile/JSON/standalone gate 測試皆 PASS（完整載入須 docker）。**下一步**：docker 驗證手感 → 調機率/冷卻 → Phase B（`retrieve_discord_context` 泛化吃 channel + persona/RAG 召回）。
- 2026-06-20：**「AI 偶爾插話 / 閒聊」需求收斂 + 文件化（功能二）**。與使用者互動式確認後，把原本糾纏的需求**拆成兩個獨立功能**：①**功能一＝AI 的家**（專屬頻道、被叫必應、重度三層記憶）＝既有 [AI 私聊頻道 draft](#ai-私聊頻道--三層記憶機制規劃中)，**本輪暫放旁邊**；②**功能二＝AI 偶爾插話**（一般頻道白名單自發冒泡、@/reply 必回、全本地單流、輕量情境記憶）＝**新區塊** [AI 偶爾插話](#ai-偶爾插話--閒聊功能二規劃中)。**本輪定案共識（含模型分層）**：①**兩顆模型、同時只一顆常駐**（Lemonade 切模型會卸載另一顆）——新增背景常駐 **`Gemma-4-12B-it-GGUF`**（判斷＋插話＋傾聽＋記憶，跟既有 `moderation_model`/`personality_model` 同慣例），P0(`/askai`、功能一)才換 **`Gemma-4-26B-A4B-it-GGUF`**。②**優先序佇列 P0>P1>P2，只有 P0 觸發 swap，背景永不 ping-pong**（`/askai` keep_alive 窗口內插話/傾聽暫停）。③觸發＝免費硬過濾 + 冷卻(90s/6次) 前置 → **12B 即時判斷**（回/reaction/沉默），太熱才加機率減壓閥；@/reply 必回。④**記憶＝跨功能共享一層**，由 **12B「沒梗轉傾聽」順手寫入**（判斷=傾聽=記憶同一 pass）；v1 檔1（persona card）+ 檔2（`retrieve_discord_context` 情境召回），檔3（`preference_fact`）為 Phase C。**待使用者下指令才動 code**；Phase A→B→C。**前置技術債**：`retrieve_discord_context` 需從吃 `interaction` 泛化成吃 `channel`（檔2 前置）。
- 2026-06-20：**/askai 網路搜尋兩處修正（參考連結數 + 體育題觸發）**。① **參考連結 3→5**：抓取 `top_k=5`（[llm_settings.py:218](src/sys_settings/llm_settings.py#L218)）一直全部塞進 `<web_context>`，但 [llm_service.py:316](src/services/llm_service.py#L316) 文末引用 directive 寫死「最多 3 個」卡住輸出 → 改「最多 5 個」對齊（軟性上限，LLM 仍可能引用少於 5 條；`llm_commands.py:482` 的 `outcome.results[:3]` 只是 debug log、不影響、保留）。② **體育題不觸發搜尋**：「請告訴我這周的世界足球賽比賽簡報」trace 的 `web_context_meta` 為 `triggered=false/reason=default`（根本沒打 SearXNG，是模型用無即時資料的記憶回場面話）。Root cause [intent.py](src/llm/retrievers/web/intent.py) 無體育主題群、且 SOFT 寫死「這週」對不上異體字「這周」。修法：新增 `_TOPIC_SPORTS`（足球/世界盃/NBA/英超/賽程/比分… **刻意不收 bare「比賽」「賽」**）掛 HARD + `_ROUTE_RULES` 加 `news`/`week`；SOFT 的 `這週/上週/最近一週` 改 `這[週周]/…` 異體字容錯。新增 [src/test/test_web_intent.py](src/test/test_web_intent.py)（standalone importlib 跑 14 斷言全 PASS；本機無 `discord` 套件不能直跑 unittest，docker 內可）。**待部署驗證**：`docker compose restart discord-bot` 後重問足球題，`web_context_meta` 應為 `triggered=true/reason=hard/news/week` 且附參考連結。**未做（可選）**：`test_web_intent` 加進 docker-compose 啟動測試 gate（目前只跑 snapshot+spoiler）；體育詞表非窮舉（羽球/網球/瓊斯盃等未收）。

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
| AI 偶爾插話 / 閒聊（功能二） | **Phase A+B 已實作（2026-06-21）**，待 docker 驗證；C（記憶寫入）待做 | 50% | [AI 偶爾插話](#ai-偶爾插話--閒聊功能二規劃中) |
| AI 私聊頻道 + 三層記憶（功能一·姊妹案） | 規劃完成（含道德守門）；人設 prompt 已就位；**本輪暫放旁邊** | 10% | [AI 私聊頻道](#ai-私聊頻道--三層記憶機制規劃中) |
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
affects: [ai-chat-channel-memory]
last_confirmed: 2026-06-20
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
