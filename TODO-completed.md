# 已完成項目歸檔

## Index

> 依時間倒序排列，方便快速定位。搜尋關鍵字可直接跳到對應區塊。

| 日期 | 區塊 | 關鍵字 |
|---|---|---|
| 2026-08-20 | [指令收斂與管理 Dashboard（改寫前原文）](#指令收斂與管理-dashboard改寫前原文歸檔-2026-10-02原-2026-08-20) | 從 handoff 歸檔, subcommand group, /persona, 管理面板, notify_server dashboard, M3/M4 時機（已過時） |
| 2026-03-31 | [Discord Bot 管理入口與指令整理 TODO（改寫前原文）](#discord-bot-管理入口與指令整理-todo改寫前原文歸檔-2026-10-02原-2026-03-31) | 從 handoff 歸檔, /panel admin, test_commands dev-only, 權限檢查五種寫法盤點, require_permission, 9/04 已還原 |
| 2026-04-18 | [Reaction 統計與社群互動玩法（改寫前原文）](#reaction-統計與社群互動玩法改寫前原文歸檔-2026-10-02原-2026-04-18) | 從 handoff 歸檔, message_reactions 表（不需要了）, 每週金句, 名人堂, /my_emoji, asker_recent_highlights |
| 2026-04-07 | [跨來源整合專區（改寫前原文）](#跨來源整合專區改寫前原文歸檔-2026-10-02原-2026-04-07) | 從 handoff 歸檔, SourceFetchPort, RenderPlan, DiscordMessagePublisher, 格式保留策略, 2026-03-25 共識 |
| 2026-03-31 | [產品能力 TODO（改寫前原文）](#產品能力-todo改寫前原文歸檔-2026-10-02原-2026-03-31) | 從 handoff 歸檔, askai 反饋, KPI, 梗庫, Prompt A/B, 模型路由, SFT |
| 2026-06-30 | [Ambient 互動紀錄 + 正向學習（自我蒸餾）](#ambient-互動紀錄--正向學習自我蒸餾--個性演化歸檔-2026-10-02) | 從 handoff 歸檔, ai_interactions, 反應＝隱式標籤, reaction_classifier, learned_style 自我蒸餾（被 style_refs 取代、不做） |
| 2026-09-29 | [ComfyUI 區塊已完成的待辦與正名](#comfyui-區塊已完成的待辦與正名歸檔-2026-10-02原-2026-09-022026-09-29) | 從 handoff 歸檔, ai_diary_channel_id, DIARY_TZ 別名繞過, 時區守衛改 AST, llm 檔名正名 |
| 2026-09-29 | [handoff 盤點紀錄歸檔](#handoff-盤點紀錄歸檔歸檔-2026-10-02) | 從 handoff 歸檔, handoff 盤點歸檔, llm 重組, services 分群, 週期提醒, 相簿漏圖, 自然插話 |
| 2026-09-29 | [共用元件索引（已搬到 AGENTS.md）](#共用元件索引已搬到-agentsmd歸檔-2026-10-02) | 從 handoff 歸檔, 共用元件索引, 合法例外, extract_fingerprint, _load_descriptions, _load_runtime_config_cached |
| 2026-09-29 | [程式結構整理：討論與實作紀錄](#程式結構整理討論與實作紀錄歸檔-2026-10-02原-2026-09-29) | 從 handoff 歸檔, llm 依角色分子資料夾, services 分 relay/events/community, test_import_resolution, test_data_file_paths, 點名 response_view_factory, S6-2 constraints |
| 2026-10-01 | [IT 新聞只帶摘要發出](#it-新聞只帶摘要發出歸檔-2026-10-02原-2026-10-01) | 從 handoff 歸檔, HKEPC 403, 只帶摘要, 就地 edit, IT-Q1 B, 6f39e87, test_it_article_refresh |
| 2026-10-01 | [scraper 抓網頁機制檢查](#scraper-抓網頁機制檢查歸檔-2026-10-02原-2026-10-01) | 從 handoff 歸檔, 瀏覽器指紋, Sec-CH-UA 矛盾, Cloudflare 擋 Chrome/Safari, 只用 Firefox, run_session, 巴哈每輪統計 |
| 2026-09-29 | [週期活動提醒：深塔海墟](#週期活動提醒深塔海墟歸檔-2026-10-02原-2026-09-29) | 從 handoff 歸檔, 深塔海墟, 錨點+28天, 矩陣版本日+7天, VersionDateResolver.update_starts, PanelBumper, 週期活動提醒身份組 |
| 2026-09-28 | [新成員歡迎訊息：接手 ProBot](#新成員歡迎訊息接手-probot歸檔-2026-10-02原-2026-09-28) | 從 handoff 歸檔, on_member_join, member_welcome, guild.rules_channel, ProBot, 4fd4170 |
| 2026-09-22 | [活動自動發布：連結指向錯誤 + 重複建活動](#活動自動發布連結指向錯誤--重複建活動歸檔-2026-10-02原-2026-09-22) | 從 handoff 歸檔, article_desc 全空, 截斷 1200, normalize_title 收 <>, 四軸升級, 墓碑, 指紋遷移, f7d4a14 |
| 2026-08-02 | [Telegram 漏收事件自動補掃與相簿漏圖](#telegram-漏收事件自動補掃與相簿漏圖歸檔-2026-10-02原-2026-08-02) | 從 handoff 歸檔, Telethon 漏派事件, CatchUp, 指針左移 300, process_lock 改單則鎖, 相簿補圖 12 小時, fbd2d3c, ea81a83 |
| 2026-03-31 | [專案 AI 架構總覽（Ollama 時代）](#專案-ai-架構總覽ollama-時代歸檔-2026-10-02原-2026-03-31) | 從 handoff 歸檔, 架構總覽, Ollama 時代, gemma4, 給外部 AI 的分析 prompt |
| 2026-04-19 | [Context / Prompt 優化專區](#context--prompt-優化專區歸檔-2026-10-02原-2026-04-19) | 從 handoff 歸檔, personality_extract 背景化, 智慧女性部署驗證, 萃取 pipeline 舊版, persona card alias 優先級 |
| 2026-08-09 | [AI 偶爾插話（功能二）與自然插話重構](#ai-偶爾插話功能二與自然插話重構歸檔-2026-10-02原-2026-06-212026-08-09) | 從 handoff 歸檔, 功能二 Phase A/B, 12B/26B 雙模型（已作廢）, preference_fact C-1~C-3, L1 鉤子閘, #N 選線 reply 錨定, L4-b 接續, debounce typing, got_reply, SearXNG 引擎體檢 |
| 2026-09-28 | [過時待辦清理](#過時待辦清理歸檔-2026-09-28) | ComfyUI 步驟 2, keep_alive 註解, 插話 Phase B 認得人, Ollama 時代觀察項 |
| 2026-08-18 | [Persona Extraction Agent 影子模式規劃 M1~M6](#persona-extraction-agent-影子模式規劃-m1m6歸檔-2026-09-28原-2026-08-18) | 從 handoff 歸檔, 已被 M7 取代, 四支唯讀工具, 五項定案, 線上實測 |
| 2026-08-18 | [Telegram 媒體 spoiler（防雷）](#telegram-媒體-spoiler防雷未帶到-discord歸檔-2026-09-28原-2026-08-18) | 從 handoff 歸檔, is_spoiler, media.spoiler, 已上線 |
| 2026-07-27 | [Telegram 多頻道來源 + 轉發去重](#telegram-多頻道來源--轉發去重歸檔-2026-08-18原-2026-07-27) | 從 handoff 歸檔, source_channels, 跨來源轉發去重 |
| 2026-07-25 | [Telegram Premium 自訂表情 → Discord App Emoji](#telegram-premium-自訂表情--discord-app-emoji歸檔-2026-08-18原-2026-07-25) | 從 handoff 歸檔, telegram_custom_emoji, App Emoji |
| 2026-07-01 | [活動公告 → 自動建立 Discord 伺服器活動](#活動公告--自動建立-discord-伺服器活動歸檔-2026-08-18原-2026-07-01) | 從 handoff 歸檔, event_time_parser, created_events |
| 2026-07-25 | [handoff 盤點紀錄歸檔（2026-08-18）](#handoff-盤點紀錄歸檔歸檔-2026-08-18) | handoff 盤點歸檔, 印象重填, 反附和, reply_to |
| 2026-06-29 | [變更紀錄：日記「開頭都一樣 + 只記得晚上」修正](#變更紀錄日記開頭都一樣--只記得晚上修正歸檔-2026-07-02原-2026-06-29) | 從 handoff 歸檔 |
| 2026-06-29 | [變更紀錄：插話人格「有時像屁孩噴人」修正](#變更紀錄插話人格有時像屁孩噴人修正歸檔-2026-07-02原-2026-06-29) | 從 handoff 歸檔 |
| 2026-06-30 | [變更紀錄：V2 風格召回（style_refs）+ 從反應數據學個性](#變更紀錄v2-風格召回style_refs-從反應數據學個性歸檔-2026-07-02原-2026-06-30) | 從 handoff 歸檔 |
| 2026-06-20 | [變更紀錄：多歌單下拉（可複選合併播放）](#變更紀錄多歌單下拉可複選合併播放歸檔-2026-07-02原-2026-06-20) | 從 handoff 歸檔 |
| 2026-06-25 | [待決議題：/askai 空泛新聞 query 搜不到](#待決議題askai-空泛新聞-query-搜不到歸檔-2026-07-02原-2026-06-25) | 從 handoff 歸檔 |
| 2026-06-21 | [handoff 盤點紀錄歸檔（歸檔 2026-07-02）](#handoff-盤點紀錄歸檔歸檔-2026-07-02) | handoff 盤點歸檔, 功能二 Phase A, persona 模組化, TG relay, Lemonade |
| 2026-06-15 | [fixupx 連結轉發：只轉影片 + 存在性防呆](#fixupx-連結轉發只轉影片--存在性防呆歸檔2026-06-15) | link_fix, select_video_links, cdn.syndication, get_token, react-tweet, fail-open, 影片才轉 |
| 2026-06-13 | [點歌者離開自動移除其點的歌](#點歌者離開自動移除其點的歌歸檔2026-06-20原2026-06-13) | music, drop_requests_by, on_voice_state_update, 寬限 5 秒 |
| 2026-06-13 | [音樂「停止」按鈕改重置歌單+重載線上歌單](#音樂停止按鈕改為重置歌單--重載線上歌單歸檔2026-06-20原2026-06-13) | music, reload_playlist, 先抓成功才換, 後改名編輯歌單 |
| 2026-06-12 | [幽靈點名按鈕越權 BUG 修正](#幽靈點名按鈕越權-bug-修正歸檔2026-06-20原2026-06-12) | rollcall, 按鈕綁定 message.id, persistent view target |
| 2026-05-18 | [LLM HTTP client 通用錯誤護網](#llm-http-client-通用錯誤護網歸檔2026-06-20原2026-05-18) | _unwrap_response_envelope, _require_json_key, KeyError 'data' |
| 2026-05-18 | [智慧女性風格重寫 + few-shot 範例檔](#智慧女性風格重寫--few-shot-範例檔歸檔2026-06-20原2026-05-18) | askai_system_prompt, persona_examples, Pekora mama, 三檔載入 |
| 2026-05-11 | [lemonade chat stream + 背景 embedding 併發失敗](#lemonade-對-chat-stream--背景-embedding-併發失敗no_choices-假象歸檔2026-06-20原2026-05-11) | lemonade_gate, stream_exclusive, no_choices 假象, network_error 200 |
| 2026-05-04 | [askai 失敗時 backend 狀態快照（Phase D）](#askai-失敗時-backend-狀態快照phase-d多-backend-通用歸檔2026-06-20原2026-05-04) | admin_get, _BACKEND_PROBES, snapshot, pre-deploy gate |
| 2026-04-29 | [askai log 觀測性補強（trace_id 串接）](#askai-log-觀測性補強phase-ab-trace_id-串接歸檔2026-06-20原2026-04-29) | trace_id, GenerateReplyResult, error_kind 分類 |
| 2026-04-29 | [Telegram Relay 文字 spoiler 還原](#telegram-relay-文字-spoiler-還原成-discord-歸檔2026-06-20原2026-04-29) | apply_spoiler_entities, entities JSONB, UTF-16-LE, surrogate |
| 2026-04-28 | [LLM client 重構：拋 openai SDK 改 httpx](#llm-client-重構拋-openai-sdk改自寫-httpx-wire-薄殼歸檔2026-06-20原2026-04-28) | llm_http_client, BaseEmbedding, backend profile, 綁協定不綁 SDK |
| 2026-04-07 | [FB 貼文推送模式](#fb-貼文推送模式歸檔2026-06-20原2026-04-07-完成) | notify/fb, CDN token 刷新, 全量替換, 移除輪詢 |
| 2026-04-27 | [Bahamut 專區整段歸檔](#bahamut-專區整段歸檔歸檔2026-04-27) | scraper 全流程 100%, 反爬基礎設施, 第三階段 RAG ingestion 未做 |
| 2026-04-27 | [幽靈點名系統剩餘 TODO 歸檔](#幽靈點名系統剩餘-todo-歸檔歸檔2026-04-27) | 部署驗證, /server_manager 整合 |
| 2026-04-27 | [askai 人物身份對照與 prompt 整合三輪重構](#askai-人物身份對照與-prompt-整合三輪重構歸檔2026-04-27) | #XXXX 錨點, mention boost, target_profile, profile 自我否定豁免, retire 退場, prompt 11→8 段精煉, persona 三路分流 |
| 2026-04-23 | [DM 通知模組抽出 + 音樂面板收藏按鈕](#dm-通知模組抽出--音樂面板收藏按鈕歸檔2026-04-23) | dm_notifier, resolve_user, send_dm, music favorite button, persistent custom_id |
| 2026-04-22 | [X.com / Twitter 影片嵌入研究](#xcom--twitter-影片嵌入研究歸檔2026-04-22) | fxtwitter, syndication API, og:video, Discord unfurler, domain replace |
| 2026-04-19 | [社群 ID 查詢 Phase 0 Step 1-5 實作完成](#社群-id-查詢-phase-0-step-1-5-實作完成歸檔2026-04-19) | community_lookup, PTT JSON1, 巴哈 ORM, panel modal, 日期 hybrid section, slot 切割 |
| 2026-04-19 | [Ollama 服務穩定化（chat_raw / keep_alive / 重試 / VRAM）](#ollama-服務穩定化chat_raw--keep_alive--重試--vram歸檔2026-04-19) | OllamaService.chat_raw, generate_reply, keep_alive 參數, 自動重試 OLLAMA_MAX_ATTEMPTS, SafeOllamaEmbedding num_ctx=8192 |
| 2026-04-19 | [askai bot 身份感注入](#askai-bot-身份感注入歸檔2026-04-19) | bot_display_name, bot_history name 屬性, safety_prompt 別稱推斷, persona 對內理解 vs 對外表達 |
| 2026-04-18 | [Context/Prompt 完整重構 + askai 身份感](#contextprompt-完整重構--askai-身份感歸檔2026-04-18) | askai, asker_profile, persona_card, 人格萃取, 撞名偵測, 429 治本, bahamut author_id |
| 2026-04-18 | [點歌機器人 Music Bot 完整實作](#點歌機器人-music-bot-完整實作歸檔2026-04-18) | music, yt-dlp, DAVE, 按鈕面板, 快取, 音訊鏈路 |
| 2026-04-18 | [幽靈點名系統核心實作](#幽靈點名系統核心實作歸檔2026-04-18) | rollcall, 抽選, 豁免期, 自動踢除, persistent view, 管理面板 |
| 2026-04-07 | [Telegram media group 合併](#telegram-media-group-合併歸檔2026-04-07) | grouped_id, media group, 多圖合併, Discord 單則 |
| 2026-04-06 | [Telegram embed title 修正](#telegram-embed-title-來源頻道名稱修正歸檔2026-04-06) | chat_title, embed title, 轉發頻道名稱 |
| 2026-04-05 | [Bahamut 續文/多圖/並行/子看板等](#bahamut-續文多圖並行子看板等完成歸檔2026-04-05) | 續文, 多圖分批, semaphore, subbsn, category 黑名單 |
| 2026-04-02 | [Bahamut 增量更新 + SQLite 遷移 + Webhook](#bahamut-增量更新--sqlite-遷移--webhook-通知完成歸檔2026-04-02) | 增量更新, SQLite, state_db, webhook, notify |
| 2026-04-01 | [Bahamut Scraper MVP](#bahamut-scraper-mvp-完成歸檔2026-04-01) | scraper, 文章抓取, 留言, DB schema, Discord relay |
| 2026-04-03 | [Bahamut 正式知識層清理](#bahamut-正式知識層清理歸檔2026-04-03) | 設計文件歸檔, ID 語意, DB schema |
| 2026-03-29 | [Telegram Relay 功能完成](#telegram-relay-功能完成歸檔2026-03-29) | relay worker, LISTEN/NOTIFY, publisher, render adapter |
| 2026-03-26 | [Telegram 已解決問題集](#telegram-relay-通道連線問題2026-03-26-已解決) | 通道連線, 媒體重複, 時序, 副檔名, route key |
| 2026-03-25 | [Telegram Relay 設計定案](#telegram-relay-設計定案--架構設定相容流程盤點2026-03-25已完成歸檔) | 架構, config, 路由, 六層設計 |
| 2026-03-22 | [Telegram Scraper 專案交接](#telegram-scraper-專案交接2026-03-22已完成歸檔) | Docker, 模組化, forward 過濾, session |

---

## 變更紀錄：日記「開頭都一樣 + 只記得晚上」修正（歸檔 2026-07-02，原 2026-06-29）

使用者回報兩個獨立問題，各有源頭，已修（待重啟生效）：

1. **只統整晚上、早上忘光光**（根因＝抓資料方式，非 prompt）。`diary_reflection._gather_day_transcript` 原本走 `fetch_recent_lines(after=now-24h, oldest_first=False, limit=120)`＝「24h 視窗裡抓**最新** 120 則」，活躍頻道從午夜往回數只到傍晚，早上中午被截光，`lookback_hours=24` 形同虛設。**改成分時段平均取樣**：把回顧視窗切成 `transcript_buckets`（預設 6）個等長時段（各 4h），每段各取最近 `max_messages//buckets`（180//6=30）則，再依時序串成一整天 → 早上中午一定有代表。新增 setting `transcript_buckets`，`max_messages` 120→180。會 log 每段取樣數（`日記逐字稿分時段取樣…`）方便觀察分佈。
   - 次要：結構化互動 `ai_interactions_store.fetch_recent` 也是 `ORDER BY ts DESC LIMIT 80` 尾段截斷，但 bot 一天插話遠少於 80，多半涵蓋整天，暫不動。
2. **日記開頭都從「夜深了」起手**（根因＝prompt 三處重複餵「深夜/安靜」+ 沒要求變化）。三處都改：`diary_reflection_prompt.txt`（去掉「現在夜深了，群裡安靜」開場、新增兩條規則：開頭別老是時間天氣起手要換切入點、回顧的是「一整天」看 `[HH:MM]` 別只盯深夜）、`diary_reflection.py` 的 `prompt_text` 與 fallback `_DEFAULT_DIARY_PROMPT` 同步去掉「深夜」字眼。

**部署**：重啟 bot 生效。可用 `/ai_diary`（admin）手動觸發驗證；看 debug log `/logs/diary_prompt.txt` 確認逐字稿是否從早到晚都有、開頭是否不再公式化。
**可微調**：`transcript_buckets` / `max_messages`（時段數與每段量）；傍晚細節若嫌薄可再加 `max_messages`。

---

## 變更紀錄：插話人格「有時像屁孩噴人」修正（歸檔 2026-07-02，原 2026-06-29）

使用者回報插話有時不像「從容和服熟女」、反而像屁孩噴人。看 `logs/ambient_prompt.txt` 對照實際回覆：**多數其實在人設上**（隔一層淡淡點評），走鐘集中在**一個情境——頻道在打遊戲互嗆對線時，它會跟著下場、借 gamer 嗆聲術語補刀**。典型：觸發「下路送爛」→ 回「既然都放棄治療了，那你們上中就當帶兩隻隊友打 5v3 吧」。

**根因**：
1. **結構破口（最關鍵）**：`persona_examples.txt`（「❌損友roast/同盟酸/毒舌 ✓智慧女性」對照範例）**只載入 /askai，沒載入插話**。`/askai` 組 prompt＝identity+guardrails+主prompt+examples（`llm_commands.py:115-117`）；插話 `_load_ambient_prompt` 只有 identity+guardrails+行為三份。最能教「別像損友補刀」的範例，缺席在最需要的模式。
2. **行為層 license 失衡**：`ambient_reply_prompt.txt` 第二關鼓勵「放開/愛玩/老朋友回扣招牌梗」好幾行，「刺是偶爾」只一行，且**沒有一條明講「群裡互嗆對線時你不下場跟著嗆」**。本地模型本就鏡像周遭語域 → 跟著對線。

**A（已做，待重啟）— 把範例載進插話**：
- **與 /askai 共用同一份 `persona_examples.txt`**（人設共通，不另維護避免 drift；使用者 2026-06-29 拍板合併，原先短暫建過的 `persona_examples_ambient.txt` 子集檔已刪）。唯一新增內容＝原檔尾端加 **範例 13「群裡打遊戲互嗆對線→旁觀者別下場補刀」**（正打使用者抱怨的情境，用範例教、非硬規則）。
- `AmbientChatSettings` 加 `use_examples=True` / `examples_path`(=persona_examples.txt)；`_load_ambient_prompt` 尾端疊 examples 層（順序＝identity+guardrails+行為+examples，與 askai 一致；mtime 快取自動納入）。
- 改檔：`persona_examples.txt`(加範例13)、`sys_settings/llm_settings.py`、`llm/ambient_reply.py`。py_compile 通過、組裝順序已驗。

**B（待你拍板，未做）— 第二關加硬規則「不下場對線」**：在 `ambient_reply_prompt.txt` 第二關加一條，明文「群裡互嗆/玩遊戲術語對線/口出穢語較勁時，你是看戲那個，不借同樣嗆聲口吻或遊戲對線術語（『放棄治療』『5v3』『有本事就…』就是下場了），刺永遠淡淡一句、隔一層、不補刀」。先做 A 觀察，B 視效果再決定（避免一次動太多人格條文難歸因）。

**部署/驗證**：重啟 bot 生效。看 `logs/ambient_prompt.txt` 確認 system prompt 尾端有範例層、且遊戲互嗆情境是否不再下場補刀。

---

## 變更紀錄：V2 風格召回（style_refs）+ 從反應數據學個性（歸檔 2026-07-02，原 2026-06-30）

**目標**：讓琇紫插話時，參考「**過去被群裡按過讚、且與當下情境語意相近**」的舊回覆當靈感 → 個性從群眾驗證過的數據長出來。**刻意不走「prose 蒸餾」**（弱 teacher 會把好句子蒸成笨句子，使用者擔心成立）→ 改「**召回真句子、不重寫**」，結構上免疫笨化。唯一 live 風險＝照抄跳針，用「抽樣輪替＋距離地板＋近期壓制＋只給情境→回覆配對＋prompt 明令別照抄」壓制。

**資料層**（`ai_interactions`）：
- 線上表已 `ALTER ADD COLUMN embedding vector(1024)` + hnsw cosine 索引（**純加欄、1281 列原資料未動**；`_EMBED_DDL` 也加進 `ensure_table`，獨立 try、缺 vector extension 不拖垮建表）。
- `record_interaction` 加 `embedding` 參數：寫入時 embed「情境」(trigger_text+context_snippet)，embed 不出來存 NULL（不影響寫入）。
- `backfill_embeddings()`：啟動時背景回填既有 1281 列（id 游標前進、idempotent、autocommit）；on_ready 在 `ensure_table` 後 `create_task(to_thread(...))`，有 `_ai_emb_backfill_started` flag 防重觸發。
- `fetch_similar_positive(situation, k, max_distance, min_positive)`：cosine `<=>`，撈 `positive_reactions>0 且 negative_reactions=0`、距離地板內的舊插話。
- embedding 走共用 `make_safe_llm_embedding`（與 RAG/印象卡同顆），公開 `get_text_embedding`；lazy singleton。

**注入層**：
- `llm_service._build_prompt_bundle` / `generate_reply` 加 `style_refs` 參數 → 渲染獨立 `<style_refs>` 區塊（框架：只學調子/招式、**嚴禁照抄字句**、不貼切就忽略）。
- `ambient_reply._build_style_refs(situation)`：召回→避開近期注入過的（`_RECENT_STYLE_REFS` deque）→抽樣 `inject_count` 條→debug log→（shadow 時只 log 不注入）。接在 callback 之後、傳進 generate_reply；debug 摘要加 `style=%d`。

**設定**（`AmbientChatSettings`，保守起步）：`style_refs_enabled=True`（False=純 shadow）、`style_refs_debug=True`、`top_k=8`、`max_distance=0.45`、`inject_count=2`、`min_positive=1`。

**部署/驗證**：**reboot container 上線**。reboot 後：(1) 看 `discord_bot.log` 的「embedding 背景回填」跑完（1281 筆，約數分鐘）；(2) 看 `ambient style_refs 召回=…抽樣=…` log 判斷**相關性 + 會不會老抓同幾句**；(3) 看 `ambient_prompt.txt` 確認 `<style_refs>` 有進 prompt、且回覆**沒有逐字照抄**。跳針/不相關 → 調 `max_distance`（收緊）或 `style_refs_enabled=False`（一鍵關）。

**待辦**：V3 心情（2 軸 transparent mood，JSON 存 `src/settings/ai_mood_state.json`、gitignore、tint-not-driver、寫進日記）尚未做；語意召回穩了再做。

---

## 變更紀錄：多歌單下拉（可複選合併播放）（歸檔 2026-07-02，原 2026-06-20）

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

## 待決議題：/askai 空泛新聞 query 搜不到（歸檔 2026-07-02，原 2026-06-25）

<!-- @meta
id: askai-vague-news-query
type: FEATURE
status: implemented_pending_verify
last_confirmed: 2026-06-25
-->

**現象：** 使用者問「幫我查詢最近重點新聞」，bot 回「我查不到什麼最新的即時新聞」，看似沒搜尋網頁。

**診斷（已定案）：** 其實有搜。`should_search()` 正確 HARD 觸發（命中 查詢/新聞 → `categories=news, time_range=week`），清理後 query=`最近重點新聞`，SearXNG 也打了 news 引擎，但 **回 0 筆**（log：`SearXNG ok: 0 results ... query=最近重點新聞`）。0 筆 → `web_context=None`（`llm_commands.py` 約 482）→ prompt 不放 `<web_context>` 區塊（`llm_service.py:296` `if web_context:` 為假）→ 模型照 system prompt「空就老實說查不到」規則回應。根因：query 無主題錨字 + news 引擎 + week，三者最差組合。

**「具體化」要先分兩種情況：** ① 真・無主題（只是要頭條）；② 有潛在主題但沒講明（本次 chat_history 整串在聊世界盃，故「最近重點新聞」很可能想問世界盃戰況）。

**三條路線：**
- A. 規則式改寫（零模型，改 `intent.py`）：偵測無錨字新聞 meta 請求，補時間/地區錨點。收益薄，regex 無法無中生有主題。
- B. 0 筆 fallback 換引擎（零模型，改 `llm_commands.py`）：news 回 0 → 改 general 引擎（`google,bing,duckduckgo,brave`）＋去 time_range 重試一次。依據：log 中 general 引擎幾乎都穩定回 5 筆。只在失敗時觸發、happy path 零延遲。**AI 建議底線方案。**
- C. LLM 改寫（真・具體化，新模組，可吃 chat_history 推斷潛在主題，例如本次可改成「世界盃足球 最新賽果」）：最強但多一趟模型（Lemonade 單流互斥，須共用已載入 gemma 避免換模型 ping-pong）、有幻覺主題風險、破壞 intent.py 零依賴哲學。**選配升級。**

**AI 建議：** 先做 B 當底線，C 當選配；A 不單獨做（頂多併進 B 的 fallback query）。

**已定案：採路線 B 並實作（2026-06-25）。**

**變更：** `src/commands/llm_commands.py`（回收 web_task 處，約 480 行）。
- 主搜回 0 筆、且 `outcome.meta.error is None`、且為窄路由（`intent.categories` 或 `intent.time_range` 非 None）時，自動再打一次 `fetch_web_results`：`engines=None`（→ `default_engines` general）、`categories=None`、`time_range=None`，language 沿用。
- 有結果才用 fallback outcome（含其 meta）；無結果維持原 0 筆。
- `web_meta["fallback"] = {attempted, result_count, error}` 供 debug。
- 不重撈的情況：① 有 error（timeout/http，SearXNG 本身異常）；② 主搜本就 general 無限時（`primary_narrow` 為 False），重撈無益。
- 未動 `intent.py`；intent 單元測試（隔離載入）全數通過。

**待驗證（部署後）：** ① 下「幫我查詢最近重點新聞」應看到 log `web fallback: 主搜 0 筆，改 general 引擎重試`，且第二次回非 0 → prompt 出現 `<web_context>`；② 有主題的新聞 query（如世界盃）主搜就命中、不應觸發 fallback；③ SearXNG timeout 時不應重撈（log 無 fallback 行）。

**未採用：** 路線 C（LLM/context-aware 改寫）保留為日後選配升級。

---

## handoff 盤點紀錄歸檔（歸檔 2026-07-02）

> 從 AI_HANDOFF 現況盤點列表移出的 2026-06-20 / 06-21 條目（完成或被後續工作取代），原文保留供追溯。

- 2026-06-21（Telegram relay 除錯）：**長訊息 embed 撞 Discord 500、回放無限重試 — 已修截斷上限**。症狀：`message_pk=7616`（2026-05-21 舊訊息回放）每輪 `channel.send` 都 `500 Internal Server Error (error code 0)`、latency ~45s（discord.py 5xx 重試耗盡）。**實際查 DB 驗證**（telegram_data）：7616 文字 4091 字、無 media/控制字元/surrogate/壞 URL、title 15、timestamp 正常 → **payload 形式上合法**。對照本頻道 2138 筆成功訊息**最長僅 3012 字、超過 3500 字 0 筆成功** → 與成功訊息唯一差異就是長度。根因＝Discord 後端對接近 4096 上限的超長 embed description 回 500（非乾淨 400）；舊 code `content[:4000]` 剛好頂在地雷區；又因回放走 `force_replay` 跳過去重 → 同筆每輪重撞同一 500、卡死回放。**修法**：[TelegramRenderAdapter](src/services/telegram_relay_service.py#L579) 加 `_DESCRIPTION_MAX_CHARS=3000`（保守低於實測安全線 3012）當「每段」上限。**最終採分段而非截斷**（使用者要保留全文且看得出是連續文章）：新增 `_split_text()`（盡量在換行/空白邊界切、不切斷句子；**暴雷安全**：切點不落在 `||` 中間，切完平衡每段 `||`，暴雷跨段時前段補 `||` 收尾、下段補 `||` 開頭，標記不破、暴雷不外洩），`render()` 改成**每段產生一個 RenderOperation**（publisher 本就逐 operation 發送 → 自然多則）；續段標題加「（續）」、footer 加頁碼「i/n」，附件只掛第一段。實測 7616：4091 字 → 2 段（2790+1299，皆 ≤3000，段1 切在句末換行）。py_compile PASS、**未 commit**。**未做（未定案）**：回放「毒訊息」dead-letter（同筆連續失敗 N 次 → 略過，避免單筆永久堵塞補送）。**下一步**：部署後重跑回放，確認 7616 送成 2 則連續訊息、`telegram_relay_result` 由 `failed_or_skipped` 變 `published`、迴圈停止。**選配**：用 webhook 跑 `/tmp/discord_len_test.py` 長度掃描，坐實 500 門檻（目前未跑）。
- 2026-06-21（部署除錯）：**Lemonade 兩個地基問題排除（embeddings + 12B ctx），功能二 Phase C 完整實作**。①**embeddings 501**：Lemonade llamacpp 只有模型帶 `embeddings` 標籤才傳 `--embeddings`（[issue #1745](https://github.com/lemonade-sdk/lemonade/issues/1745)）；user-pull 的 `Qwen3-Embedding` 沒標籤 → 501。修法＝補標籤 / 我在 config 加 `llamacpp_args:"--embeddings"`。embeddings 通 → RAG 滿血 + Phase C 寫入可運作。②**12B ctx 卡 4096**：根因是 bot 的 `/api/v1/load` 送 **nested `recipe_options`**，但 Lemonade 文件要**平鋪參數**（[server_spec](https://github.com/Mintplex-Labs/lemonade-sdk/blob/main/docs/server/server_spec.md)；ctx_size bug [#1817](https://github.com/lemonade-sdk/lemonade/issues/1817) 只在 vLLM、llamacpp 正常）→ 改 [llm_http_client.py:_lemonade_load_model](src/llm/llm_http_client.py) 送**平鋪 ctx_size**（不帶 reserved 旗標、不帶 `save_options`，避免污染使用者 Lemonade 持久設定）→ **12B ctx=16384**。連帶把為 4096 加的精簡放寬回完整（history 12/persona 5/recall 6）。
  - **⚠️ 教訓（save_options 翻車）**：曾用 `llamacpp_args:"--embeddings"` + `save_options:true`，把 `--embeddings`（Lemonade reserved、由標籤管理）**baked 進持久 `recipe_options.json`** → 之後每次載入都 `model_load_error: --embeddings cannot be overridden`，embed model 整個掛掉、重啟還復發。**最終解**：`POST /api/v1/load {model_name, ctx_size, merge_args:false, save_options:true}` 一次覆寫掉持久的毒（`merge_args:false`＝不 merge 持久自訂 args）；或手動清 `%USERPROFILE%\.cache\lemonade\recipe_options.json` 的該筆。**結論：bot 絕不要送 reserved 旗標、也不要用 `save_options` 寫使用者的 Lemonade 設定。**③**Phase C 全鏈完成**（見功能二區塊，C-1~C-3 [x]）+ `MemoryService` 共享門面 + ambient debug 觀測（`/logs/ambient_prompt.txt`）+ reply 對已刪訊息 fallback 直接發頻道。**未 commit**。**下一步**：重啟 bot 套新設定 → 端到端測插話/記憶 → 之後做 C-4（consolidation/decay/觀測面板）。
- 2026-06-21（續）：**persona prompt 模組化 + 功能二 Phase B（認得人）+ 記憶設計定稿**。①**persona 重構**：把共用性格/語氣/色色分寸/§19§25 紅線/語言規則從 [askai_system_prompt.txt](src/settings/prompts/askai_system_prompt.txt) 搬進共用的 [persona_identity.txt](src/settings/prompts/persona_identity.txt)（/askai 留任務框架：回答風格/網路引用/人物對照）；ambient 與 /askai 從此**同一個琇紫**。內容等價、**順序微調 → 待 user 重測 /askai**。②**Phase B 認得人**：[ambient_reply.py](src/llm/ambient_reply.py) 接 `retrieve_rag_context_sync`（吃純 id，executor 跑，per-channel 60s 快取，embedding 走 Lemonade 獨立 port 不卸載 12B）→ persona card 進 `persona_context`。③**記憶設計定稿**（見功能二區塊 Phase C + 預設決策）：**只記本人中性偏好；敏感(健康/感情/家庭/財務)直接丟不存；他人/紅線丟；多次提到才升等(tentative→trusted≥2)；全自動零審核；治理＝AI 自我進化(抽取→升等→消化→淡忘)+選配監督面板**。靜態 py_compile PASS。**C（preference_fact 寫入管線）尚未實作**。
- 2026-06-21：**功能二「AI 偶爾插話」Phase A 實作完成（待 docker 驗證）**。新增 [ambient_reply.py](src/llm/ambient_reply.py)（硬過濾→冷卻/上限→foreground 讓位→**12B 判斷**，沉默 sentinel `[PASS]` 不發送；@/reply 必回）。**插不插由 12B 決定、不擲骰**——「偶爾」靠冷卻+上限；機率退為 `judge_sampling_rate` 純減壓閥（預設 1.0 不作用，太吵才抽樣降載）。配套：`ambient_model: Gemma-4-12B-it-GGUF` 進 [llm_runtime_config.json](src/sys_settings/llm_runtime_config.json)（+ctx 8192）、`LLMRuntimeConfig.ambient_model` + `LLMService.resolve_ambient_model()`、`AmbientChatSettings`、[channel_registry](src/settings/channel_registry.py) 加「AI 插話頻道」、[lemonade_gate](src/llm/lemonade_gate.py) 加 `stream_busy/note_foreground_activity/foreground_recently_active`（/askai 兩處標 foreground）、`bot.ambient_tracker`、`on_message` create_task、[ambient_reply_prompt.txt](src/settings/prompts/ambient_reply_prompt.txt)。**Phase A 範圍調整**：判斷+生成合一次 12B 呼叫（非獨立 judge）、react 檔次延後、persona card(檔1) 移到 Phase B（Phase A 記憶＝`channel.history` 短期脈絡）。**未做**：真正優先序佇列（目前靠 foreground 讓位 + `stream_exclusive` 序列化；directed@ 仍可能在 /askai 窗口觸發 swap）。靜態：py_compile/JSON/standalone gate 測試皆 PASS（完整載入須 docker）。**下一步**：docker 驗證手感 → 調機率/冷卻 → Phase B（`retrieve_discord_context` 泛化吃 channel + persona/RAG 召回）。
- 2026-06-20：**「AI 偶爾插話 / 閒聊」需求收斂 + 文件化（功能二）**。與使用者互動式確認後，把原本糾纏的需求**拆成兩個獨立功能**：①**功能一＝AI 的家**（專屬頻道、被叫必應、重度三層記憶）＝既有 [AI 私聊頻道 draft](#ai-私聊頻道--三層記憶機制規劃中)，**本輪暫放旁邊**；②**功能二＝AI 偶爾插話**（一般頻道白名單自發冒泡、@/reply 必回、全本地單流、輕量情境記憶）＝**新區塊** [AI 偶爾插話](#ai-偶爾插話--閒聊功能二規劃中)。**本輪定案共識（含模型分層）**：①**兩顆模型、同時只一顆常駐**（Lemonade 切模型會卸載另一顆）——新增背景常駐 **`Gemma-4-12B-it-GGUF`**（判斷＋插話＋傾聽＋記憶，跟既有 `moderation_model`/`personality_model` 同慣例），P0(`/askai`、功能一)才換 **`Gemma-4-26B-A4B-it-GGUF`**。②**優先序佇列 P0>P1>P2，只有 P0 觸發 swap，背景永不 ping-pong**（`/askai` keep_alive 窗口內插話/傾聽暫停）。③觸發＝免費硬過濾 + 冷卻(90s/6次) 前置 → **12B 即時判斷**（回/reaction/沉默），太熱才加機率減壓閥；@/reply 必回。④**記憶＝跨功能共享一層**，由 **12B「沒梗轉傾聽」順手寫入**（判斷=傾聽=記憶同一 pass）；v1 檔1（persona card）+ 檔2（`retrieve_discord_context` 情境召回），檔3（`preference_fact`）為 Phase C。**待使用者下指令才動 code**；Phase A→B→C。**前置技術債**：`retrieve_discord_context` 需從吃 `interaction` 泛化成吃 `channel`（檔2 前置）。
- 2026-06-20：**/askai 網路搜尋兩處修正（參考連結數 + 體育題觸發）**。① **參考連結 3→5**：抓取 `top_k=5`（[llm_settings.py:218](src/sys_settings/llm_settings.py#L218)）一直全部塞進 `<web_context>`，但 [llm_service.py:316](src/services/llm_service.py#L316) 文末引用 directive 寫死「最多 3 個」卡住輸出 → 改「最多 5 個」對齊（軟性上限，LLM 仍可能引用少於 5 條；`llm_commands.py:482` 的 `outcome.results[:3]` 只是 debug log、不影響、保留）。② **體育題不觸發搜尋**：「請告訴我這周的世界足球賽比賽簡報」trace 的 `web_context_meta` 為 `triggered=false/reason=default`（根本沒打 SearXNG，是模型用無即時資料的記憶回場面話）。Root cause [intent.py](src/llm/retrievers/web/intent.py) 無體育主題群、且 SOFT 寫死「這週」對不上異體字「這周」。修法：新增 `_TOPIC_SPORTS`（足球/世界盃/NBA/英超/賽程/比分… **刻意不收 bare「比賽」「賽」**）掛 HARD + `_ROUTE_RULES` 加 `news`/`week`；SOFT 的 `這週/上週/最近一週` 改 `這[週周]/…` 異體字容錯。新增 [src/test/test_web_intent.py](src/test/test_web_intent.py)（standalone importlib 跑 14 斷言全 PASS；本機無 `discord` 套件不能直跑 unittest，docker 內可）。**待部署驗證**：`docker compose restart discord-bot` 後重問足球題，`web_context_meta` 應為 `triggered=true/reason=hard/news/week` 且附參考連結。**未做（可選）**：`test_web_intent` 加進 docker-compose 啟動測試 gate（目前只跑 snapshot+spoiler）；體育詞表非窮舉（羽球/網球/瓊斯盃等未收）。

---


## fixupx 連結轉發：只轉影片 + 存在性防呆（歸檔 2026-06-15）

<!-- @meta
id: twitter-link-fixupx
type: FEATURE
status: confirmed
last_confirmed: 2026-06-15
-->

**演進：** 2026-06-13 首版（所有 x.com / twitter.com 貼文連結都轉 fixupx + 砍預覽）→ 2026-06-15 改成**只轉影片**。動機：使用者回報圖片貼文的 fixupx 預覽跟 Discord 原生預覽沒差別，轉了多此一舉，還會把原生預覽卡一起砍掉。

**需求：** x.com **影片**貼到 Discord 不會載入預覽，bot 偵測後自動貼出可預覽的 fixupx 網址；**圖片貼文不轉**（保留 Discord 原生預覽）。

**關鍵限制：** 光看網址分不出影片/圖片；x.com 對本專案 server 也只回 JS 空殼（實測 `Discordbot` UA 抓回 5KB script、無 og 標籤，Discord 抓得到是因為它在 x.com 那邊有白名單待遇，我們複製不出來），所以必須查貼文 metadata 才能判斷類型與存在性。

**設計（`src/utils/link_fix.py`，無 discord 相依）：**
- `TWITTER_STATUS_RE`：只比對含 `/status/<id>` 的貼文連結（涵蓋 x.com / twitter.com、www./mobile. 子網域、/photo//video/ 尾段），抓出 `user`/`id` named group；避免轉到個人首頁、搜尋等無意義連結。**第 1 層格式防呆（本地、免網路）。**
- `get_token(id)`：移植 vercel/react-tweet 的 `getToken`，`((id/1e15)*π)` 轉 36 進位去 0 去點，供 syndication CDN 用（免金鑰、純計算）。實測 endpoint 只要 token「非空」就放行（亂打也回 200），仍照公式算正確值以防未來收緊。
- `async _classify_tweet(session, id)`：查 `cdn.syndication.twimg.com/tweet-result`（8s timeout）回 `video` / `non_video` / `not_found` / `unknown`。**第 2 層存在性 + 類型判斷。**
- `async select_video_links(content, session=None) -> str | None`：先跑 regex，**沒命中早退 None、不開 session、不連網**；命中才開 session（可注入，預設自開自關），逐一查類型，只在 `video` 或 `unknown` 時轉成 fixupx。
- `rewrite_twitter_links`（全轉版純函式）保留給測試與不需類型判斷的場合。
- `on_message`（`src/discord_bot.py`）：bot-self guard 後直接 `await select_video_links(message.content)`（格式擋掉/查詢/開 session 全收在函式內），有結果 → `channel.send(fixed_links)` + `message.edit(suppress=True)`，皆包 try/except 記 warning。

**決策表：**
| 查詢結果 | 動作 |
|---|---|
| 確定有影片（含 animated_gif） | ✅ 轉 fixupx + 砍預覽 |
| 確定非影片（圖片/純文字） | ❌ 不轉 |
| 404 / tombstone / 無貼文主體 | ❌ 不轉（防呆，服務的確定答案） |
| 逾時 / 5xx / 空 body 無法解析 | ✅ 轉 + 砍預覽（fail-open，查詢服務掛掉不停擺） |

一句話：**只在「確定有影片」或「服務掛掉問不到」時才轉；服務只要明確回答了（圖片 or 不存在），就尊重它。**

**為何用 syndication CDN 不用 api.fxtwitter.com：** 原生 CDN 除非 x.com 本身倒否則不會消失；第三方代理（fxtwitter）會掛。fixupx 本體無 JSON API、api.fixupx.com 連不上。查類型走原生 CDN、顯示走 fixupx.com，查與顯示分離。

**邊界：** `suppress=True` 是整則訊息一起砍，混合「影片連結+圖片連結」的訊息會連圖片原生預覽一起砍掉（罕見，已接受）；限流回 `{}` 會誤判成 not_found 不轉（罕見）。

**部署需求：** Bot 需 **Manage Messages 權限**才能壓別人的預覽；缺權限只記 warning、fixupx 新訊息仍正常發出。

**驗證（已完成）：** docker exec 在 discord-bot 容器（aiohttp 3.14.1）跑整合測試：影片→`video`→轉、jack/20 純文字→`non_video`→不轉、假 id→`not_found`→不轉、混合輸入只留影片那條、一般聊天/首頁連結早退 None、自開 session 路徑正常；token 算出 `5arc5735bxrdhz15s9vn29` 查得到正確 media；py_compile 兩檔通過。

**待部署驗證：** ① `docker compose restart discord-bot` ② 影片貼文回 fixupx 並可預覽、原訊息預覽卡被砍；③ **圖片貼文不轉、保留原生預覽**；④ 已刪/亂打 id 不轉；⑤ syndication CDN 暫掛時 fail-open 照轉；⑥ 缺 Manage Messages 權限時不會炸、僅略過壓制。

**參考：** [vercel/react-tweet getToken](https://github.com/vercel/react-tweet/blob/main/packages/react-tweet/src/api/fetch-tweet.ts)；早期研究見本檔 [X.com / Twitter 影片嵌入研究（歸檔 2026-04-22）](#xcom--twitter-影片嵌入研究歸檔2026-04-22)。

---

## Bahamut 專區整段歸檔（歸檔 2026-04-27）

### 已完成（持續運行中）

- Bahamut Scraper MVP（2026-04-01 歸檔）
- Bahamut 增量更新 + SQLite 遷移 + Webhook 通知（2026-04-02 歸檔）
- Bahamut 正式知識層清理（2026-04-03 歸檔）
- Bahamut 續文 / 多圖 / 並行 / 子看板（2026-04-05 歸檔）
- 反爬基礎設施 BaseScraperClient（2026-04-12，含 Phase 1-3 整合 + cloudscraper / fake-useragent / requests 清理；scraper 容器統一 curl_cffi）
- 端到端流程：scraper → DB → API → Discord 100% 完成並運行中

### 風險（仍需注意，未解決）

1. `snB == sn` 高度吻合但未 100% 證明
2. HTML 結構若再變，`section.c-section` / `Commendlist_*` selector 可能失效

### 未排入主線的未來工作（要做時從這邊撈）

**端到端測試 + Alembic migration**：
- 端到端測試：重啟兩容器 → 確認續文 + 多圖 + subbsn + 自動閉環
- 正式 DB migration（Alembic）

**第三階段：整合 AI / pgvector / RAG**
> 目標：Discord bot 可用巴哈資料做語意搜尋、摘要、審查輔助；讓結構化查詢與向量檢索並存

交付成果：
- Bahamut RAG ingestion pipeline
- pgvector embeddings 與 metadata 設計
- Discord bot 查人 / 查文 / 摘要 / 審查指令雛型
- SQL + Vector 雙軌查詢流程

完成標準：
- Discord bot 可回答巴哈相關問題
- 可對特定使用者或主題進行 RAG 搜尋與摘要
- 可結合 moderation 資料做文章審查輔助
- 可與既有 `discord_chat` / `member_profile` retrieval 共存

實作清單：
- 在 `retrieval_sources` 新增 `bahamut_forum` 資料來源設定
- 設計 chunk 策略：主文/留言/回文/回文留言
- 設計 pgvector metadata：`doc_type`, `post_id`, `comment_id`, `reply_id`, `user_id`, `category`, `published_at`, `moderation_status`
- 建立 embedding / ingestion pipeline
- 設計 SQL filter + Vector retrieval 混合查詢
- 設計 Discord bot 指令：查主題、查文章、查使用者、查高風險留言
- 建立摘要 prompt：單篇摘要、討論風向摘要、使用者發言摘要
- 建立觀測指標：索引筆數、查詢延遲、命中率、審查覆蓋率
- 驗證 Discord 問答是否可同時引用 Discord 聊天資料與巴哈論壇資料

建議執行順序：第三階段前先補端到端測試與 migration；第二階段穩定後再做第三階段 RAG；每階段保留 JSON 範例與測試案例。

---

## 幽靈點名系統剩餘 TODO 歸檔（歸檔 2026-04-27）

> 系統核心已歸檔於「幽靈點名系統核心實作（歸檔 2026-04-18，DM 通知 2026-04-27 補完）」。
> 以下是還沒做的項目，要做時從這邊撈：

- [ ] **部署驗證**（核心 P0 剩這個）
- [ ] **`/server_manager` 整合**（P1）：透過下拉選單設定頻道與身份組

---

## askai 人物身份對照與 prompt 整合三輪重構（歸檔 2026-04-27）

### 問題鏈

`/askai` 帶 `<@user_id>` 問「介紹某人」答錯——撈到語意接近的「一口氣上吧」而不是真正的 NNN（user_id 末 4 碼 7489）。三輪追根：

| 輪 | 發現 | 根因 |
|---|---|---|
| 1 | DB / SQL 撈卡用完整 user_id 精準對，但 prompt 呈現只給 LLM 名稱 | 名稱模糊匹配，相似 alias 會混 |
| 2 | 加 #XXXX 錨點後 prompt 仍走舊 SQL | `<@id>` resolve 後丟給 RAG，內部重抽 mention id 抽到空，+35 boost 從未生效 |
| 3 | mention boost 修好後 NNN 卡正確排第一，LLM 仍答「不知道」 | `<latest_user_message>` 沒帶 `#XXXX`，加上 NNN 自介有「無法用言語描述」自我否定，LLM 沒做跨段對照 |

### 解法（分四個維度）

**A. #XXXX 末 4 碼錨點全鏈路對齊**
- `persona_card_builder.format_persona_cards_for_context`：卡標題 `「alias」` → `「alias#XXXX」`
- `context_retriever._build_discord_context_item`：chat 行 `display_name:` → `display_name#XXXX:`
- `llm_commands.py`：移除舊撞名 `name_to_ids` 偵測（改成每行都有錨點，不只撞名才加）；asker_display_name 永遠加 `#XXXX`
- `<@id>` resolve 同步補末 4 碼：`<@537251366008127489>` → `二口氣上吧！ᕕ( ᐛ )ᕗ#7489`，跟卡標題 `「NNN#7489」` 用同一個錨點對齊
- DB 完整 user_id 不進 prompt（降敏 + 省 token），只留在 Python 變數 / DB metadata / asker_profile system block

**B. SQL 重構（按 profile_kind 分流 + 補 auto_personality）**
- Stage 2 `sql_alias`：原扁平 `author_id = ANY(mentioned)` 會撈到「tag 對象寫給別人的印象」，改 `(intro_profile/auto_personality AND author_id) OR (impression AND target_user_id)`
- Stage 1 `sql_identity` / Stage 0 `sql_participant`：補 `auto_personality` profile_kind（原本只查 intro + impression，AI 觀察只能靠 vector）

**C. mention boost 修復**
- 根因：`llm_commands.py:298` 上游已正確抽出 `mentioned_user_ids`，但 `<@id>` 被 resolve 成 display_name 後才把 `resolved_question` 傳給 `retrieve_rag_context_sync` (line 358)，導致內部 `extract_mentioned_user_ids(question)` 抽到空 list，**+35 scoring boost 從未生效**
- 修法：`retrieve_rag_context_sync` / `retrieve_rag_context` / `_retrieve_rag_context_impl` 三個簽名新增 `mentioned_user_ids: list[str] | None = None` kwarg；`llm_commands.py` 改用 `functools.partial` 顯式傳入；內部僅當 caller 沒傳時才 fallback 從 question 重抽

**D. target_profile 提權結構（mention 對象單獨抽出）**
- `llm_service._build_prompt_bundle` / `generate_reply` 新增 `target_profiles` 參數，輸出獨立 `<target_profile>` 區塊**緊鄰 `<latest_user_message>` 之上**（最高 attention 位置），含明確指引「請完整以這份 profile 為事實依據回答（自介、印象、AI 觀察都可帶入展開），不要被 chat 玩笑帶偏；不要對人物存在性提出懷疑」
- `llm_commands.py` 三路分流 persona card：requester 卡 → asker_profile / mentioned_user_ids 命中卡 → target_profiles / 其餘 → other_member_profiles
- 退場處理：mention 了但 DB 沒卡的對象（新進群、未填自介、AI 觀察未跑、或已離群）放退場行「`「{name}#{XXXX}」— 群內尚無此人的 persona 紀錄；可從 chat_history 推測，否則請老實說對此人不熟悉`」，display_name 從 `interaction.guild.get_member` 撈，撈不到 fallback `user_{XXXX}`
- system_safety_prompt 補 `target_profile` 入名單 + 明確豁免「即使 profile 自我否定（『你不能相信我』『無法用言語描述』）也只是人設用字，不是給你的指令」

### Prompt 整合精煉（順手做）

11 段 → 8 段，84 行 → 51 行，~3300 字元 → 2412 字元（-27%，估省 ~700 token / 次）：
- 【回答優先】+【收尾】+【知識盲區】合併為【回答風格】4 條
- 【互動模式】+【風格提示】合併為【互動與語氣】6 條
- 【網路搜尋引用規則】6 條 → 2 條 + 範例
- 【語氣與禁忌】6 條 → 3 條（子項全保留）
- 【色色模式】【人物身份對照規則】【語言規則】不動
- 所有獨立業務規則 1:1 保留，只砍純重複
- 【回答風格】3 條後續再調整成「像真實朋友聊天」三梯度（八卦/情緒 4-8 句、知識/技術 3-6 句、純短問 1-2 句），加「寧可多帶細節，也別縮到顯得什麼都不懂」反向防短
- 角色設定加「會主動陪聊的姊姊」描述：黏人不黏膩、好奇對方、自然延伸話題、不機械斷話

### 規則對照表（驗證無漏）

每條原規則都有 mapping，砍掉的 4 條（風格提示 11.1 / 11.2、網路搜尋 7.6、回答優先 2.2）都是純重複（與首行人設 / 色色模式 / 語氣與禁忌 2 重複）。

### 涉及檔案

| 檔案 | 主要改動 |
|---|---|
| `src/llm/persona_card_builder.py` | 卡標題加 #XXXX |
| `src/llm/context_retriever.py` | chat 行加 #XXXX + Stage 1/0/2 SQL 重構 + mentioned_user_ids 參數 |
| `src/commands/llm_commands.py` | 移除撞名邏輯 + asker #XXXX + functools.partial + persona 三路分流 + 退場處理 + `<@id>` resolve 加錨點 |
| `src/services/llm_service.py` | target_profiles 參數 + `<target_profile>` 區塊 |
| `src/settings/prompts/askai_system_prompt.txt` | 新增人物對照規則 4 條 + 整合 11→8 段 + 角色設定加陪聊感 + 回答風格三梯度 |
| `src/settings/prompts/llm_context_safety_rules.json` | target_profile 入名單 + 自我否定豁免 |

### 業界對照與未來路線

- 業界主流是「Deterministic + Probabilistic 雙層」，本次強化的是 Deterministic 在 prompt 端的延伸
- 規則型 fix（system prompt）對小模型（gemma4:26b）作用有限，**結構型 fix（位置 + 標籤）才有效**——target_profile 緊鄰問題、用獨立區塊、加明確指引，不依賴 LLM 跨段推理能力
- 升級路線（roadmap，未排入主線）：Structured XML context（用 `<person id="...">` / `<chat_message ref_person="...">` schema）→ tool calling-based persona lookup（換支援 tool use 的 model 後）

### 邊界（未動的部份）

| 項目 | 原因 |
|---|---|
| DB schema | 完整 ID 一直在 metadata，本來就夠 |
| 撈 DB SQL 用完整 ID 精準比對 | 已是現狀，方向正確 |
| persona card scoring 權重 | ID 比對加分（+50/+35/+25）已大於 alias 加分（+20），符合 ID-first |
| dedup 優先序 | sql_identity > sql_alias > vector，已正確 |
| `_clean_impression_text` regex | 保留，避免完整 18 位 ID 經由 impression text 漏進 prompt |
| NNN 等使用者自介內容 | 不修原始資料，靠結構保護模型不被自我否定文字帶偏 |

---

## DM 通知模組抽出 + 音樂面板收藏按鈕（歸檔 2026-04-23）

### 改動

①新增 `src/utils/dm_notifier.py`（系統模組層，與 `logger_config.py` 同層），提供四個函式：
- `resolve_user`（user_id → User/Member，`guild.fetch_member` → `bot.fetch_user` → `bot.get_user` → `guild.get_member`）
- `send_dm`（底層發送，吃掉所有例外，回 bool）
- `notify_keyword_hit`
- `notify_song_liked`

所有 discord DM 發送的共通 user resolution + 例外處理集中於此。

②`commands/user_commands.py` 的 keyword 監控命中段（原 ~60 行 user resolution + embed + try/except）縮到一行：
```python
await notify_keyword_hit(self.bot, user_id, message, found_keywords, guild=message.guild)
```

③`music/announcer.py` 的 `MusicControlView` 第一排加入 `⭐ 收藏` Secondary 按鈕（順序：點歌 → 歌單 → 收藏），按下後寄 DM 給按鈕觸發者（含歌名、長度、YT 連結、縮圖、語音頻道），`custom_id="music_favorite"` 可持久化；失敗給 ephemeral 提示「你的私訊已關閉」。

④純 DM 無記檔、無 de-dup（按幾次寄幾次，符合 MVP）。

### 附帶整理

`src/services/migrate_json_to_sqlite.py` 搬到 `src/scripts/`（用 `git mv` 保留歷史，與 `migrate_emoji_text_format.py` / `reembed_pgvector.py` 同性質），docstring 執行路徑同步更新。

---

## X.com / Twitter 影片嵌入研究（歸檔 2026-04-22）

### 背景

使用者問 ermiana 類 Discord bot 為何能把 x.com 貼文影片直接轉成可播放 embed。本次純研究記錄，無 code 異動。

### 核心原理

- Discord unfurler 會抓訊息裡 URL 的 `<meta>` 標籤（OpenGraph / Twitter Card）決定 embed 樣式
- x.com 本身**不回傳 `og:video` 直連**，只給縮圖，所以 Discord 播不了
- 第三方代理站 scrape 該 tweet 後重組一份含 `og:video` / `twitter:player:stream` 的 HTML，Discord 抓到就能直接播

### 常用代理網域

把 `x.com` / `twitter.com` 整段替換成：
- `fxtwitter.com`（最穩定、最主流）
- `fixupx.com`（FxTwitter 對應 x.com 的新網域）
- `vxtwitter.com`（另一派系）

### 實作模式（若要在本專案加 x.com 來源）

1. `on_message` regex 抓 `x.com` / `twitter.com` URL
2. 替換 domain 後重發
3. `message.edit(suppress=True)` 或 webhook 模仿使用者身份，抑制原訊息 embed

### 影片直連 JSON API

- `GET https://api.fxtwitter.com/{user}/status/{id}` → 回 JSON
- `media.videos[].url` 即 `.mp4` 直連
- 免認證、免 API key

### 能力邊界

| 功能 | 代理網域 | 說明 |
|---|---|---|
| 單篇貼文內容 | ✅ | 文字、作者、時間、媒體 |
| 影片直連 | ✅ | `.mp4` URL |
| 關鍵字 / hashtag / 使用者時間軸搜尋 | ❌ | 完全沒這能力，只吃「已知的 tweet URL」 |

### 代理底層

- Syndication API：`cdn.syndication.twimg.com/tweet-result?id={id}&token={derived}`
- 原用途是讓部落格 / 新聞網站嵌入推文，免登入、免 key、免費
- token 是前端用 tweet id 算出來的公式
- X 不關掉 syndication 是因為關了全世界新聞網站 embed 都會爛
- 舊的 `guest_token`（`/1.1/guest/activate.json`）**2023 年中被封殺**，Nitter / snscrape 死於此

### 付費 vs 免費

| 層面 | 官方 v2 API | Syndication（fxtwitter 等） |
|---|---|---|
| 要錢 | Basic $200/月 起 | 免費 |
| 註冊 | 需申請 API key | 不需 |
| 搜尋 / timeline | ✅ | ❌ |
| SLA / 文件 | ✅ | **完全沒有** |
| 隨時被關的風險 | 低 | 高（X 已有前例） |

### 決策樹

1. 把 Discord 訊息裡的 x.com 連結轉可播放影片 → `on_message` domain replace（一小時可收工）
2. 監控特定帳號新貼文 → 沒有免費穩定方案，需評估付費 v2 或放棄
3. 關鍵字搜尋 → 代理網域做不到
4. 商業/長期依賴 → 不建議依賴 syndication

### 參考

FxTwitter 專案：https://github.com/FixTweet/FxTwitter

---

## 社群 ID 查詢 Phase 0 Step 1-5 實作完成（歸檔 2026-04-19）

### 完成內容

| Step | 內容 |
|---|---|
| 1 | JSON1 效能驗證 script (`src/scripts/bench_ptt_comment_lookup.py`)。對現有 articles.db（810 篇 / 39,890 留言 / 367 MB）實測，全部 query p95 < 30ms（< 500ms 判準）。意外收穫：`ix_ptt_posts_published_at` 早已存在（scraper models.py 已加 `index=True`），EXPLAIN QUERY PLAN 顯示 SQLite 已先走時間 index 縮小範圍再做 `json_each`，所以 `idx_ptt_author` 完全不必加，原定 PTT index migration 取消 — scraper DB schema 零變更 |
| 2 | `state_db` 新表 `community_lookup_threads` + CRUD（COALESCE 部分更新、smoke test 通過）|
| 3 | `services/community_lookup_service.py` 查詢核心（PTT JSON1 + 巴哈 ORM + 模糊候選；對真實 DB smoke test：lovez04wj06 30 天查到 618 則留言、坂坂悠模糊候選排序正確）|
| 4 | `commands/community_lookup_commands.py`（Panel View、Modal、ControlMessageView、Flow 含日期 hybrid / slot 切割 / 父頻道通知 / bump，全部 smoke test 通過）|
| 5 | `/server_manager` 加「社群查詢頻道」選項 + 設定完自動部署 panel；`discord_bot.py` 已掛入 `COMMAND_MODULES` |

### 涉及檔案

**新增：**
- `src/services/community_lookup_service.py`
- `src/commands/community_lookup_commands.py`
- `src/scripts/bench_ptt_comment_lookup.py`

**改動：**
- `src/services/state_db.py`（新表 + CRUD）
- `src/commands/management_commands.py`（/server_manager 加選項）
- `src/discord_bot.py`（掛 cog）

未動 scraper DB schema。

### Step 6 部署驗證（已完成，2026-04-20）

DB `community_lookup_threads` 累積 13+ 筆查詢紀錄，PTT (xfa60118 等) 與巴哈 (eveway / omiyashota / david89037 / huang1011200 等) 雙來源都驗過；slot 拆分（header / post / comment）、日期 hybrid section、父頻道公告、panel bump 流程實際運作正常。

---

## Ollama 服務穩定化（chat_raw / keep_alive / 重試 / VRAM）（歸檔 2026-04-19）

### Stage 1：chat_raw 統一化

`OllamaService` 新增 `chat_raw()` 底層方法（純 HTTP + payload 組裝，raise `OllamaAPIError` / `aiohttp.ClientError`），`generate_reply()` 改為高階封裝（prompt bundle + context 注入 + 錯誤字串化）；`chat_raw` 新增 `timeout` 參數讓 caller 覆蓋預設。

`personality_extractor.extract_personalities` 從自寫 aiohttp 遷移到 `service.chat_raw(timeout=600, num_ctx=32768, temperature=0.3, top_p=0.8)`，消除唯一一處 /api/chat 重複實作。

附帶修掉「Ollama 呼叫發生未預期錯誤: （空字串）」log 診斷困難（加 `type(exc).__name__`，例：`TimeoutError: `）。

### keep_alive 參數

`chat_raw` / `generate_reply` 新增 `keep_alive` 參數，caller 按用途傳不同值：
- /askai：`"1h"`（連續互動期間 chat model 常駐）
- moderation：`"30m"`（間歇性任務）
- personality_extractor：`"30m"`（4am 排程跑完 30 分鐘後釋放）

策略：caller 明確傳值才加 `keep_alive` 欄位，否則沿用 server 端全域 `OLLAMA_KEEP_ALIVE`，不覆蓋。embed 模型目前還是走 server 全域設定（沒動 LlamaIndex 層），待後續需要時再做 Stage 2。

### 自動重試

`chat_raw` HTTP 區塊改 2-attempt 迴圈：
- 檔頭新增常數 `OLLAMA_MAX_ATTEMPTS=2` / `OLLAMA_RETRY_DELAY=3.0` / `OLLAMA_RETRY_STATUS_CODES={500,502,503,504}`
- 每次建立新 ClientSession + ClientTimeout 讓 timeout 自動重置
- 重試 500/502/503/504 + asyncio.TimeoutError + aiohttp.ClientError
- **不重試** 4xx 與回應格式異常

觸發背景：17:14 出現 `500 model runner has unexpectedly stopped`，使用者確認 VRAM 還剩 20GB 排除 OOM，判定為 Ollama runner 暫時性崩潰。

### VRAM 優化（embedding num_ctx）

`SafeOllamaEmbedding` 預設注入 `num_ctx=8192`：
- Ollama VRAM-based 預設 32768 讓 0.6B embedding 吃 5.7GB VRAM（KV cache ~3.5GB 預分配但用不到）
- 調成 8192 後 KV cache 降到 ~880MB，省 ~2.6GB
- 實作：檔頭常數 `_EMBED_NUM_CTX=8192` + `__init__` 覆寫把 `num_ctx` 塞進 `ollama_additional_kwargs`，caller 仍可覆寫
- 三個 call site（chat_persistence / intro_rag_port / context_retriever）一行都不用改

### embedding 長度稽核

所有 call site 最大輸入 ~4200 字元（Discord 訊息上限），用掉 8192 token 的 51%，有 2 倍 buffer；intro/impression/personality 都有 modal `max_length` 或程式常數硬限制；未來 Bahamut / Article 若需 embed 長文應先切 chunk，不是調大 num_ctx。

### 澄清

人格萃取排程本來就會自動寫 RAG（`run_personality_extraction` 預設 `write_rag=True`，排程 caller 沒傳 False），無需改動；現況語意 = 排程自動 / 手動人審。

---

## askai bot 身份感注入（歸檔 2026-04-19）

### 問題現象

LLM 遇到兩類輸入會角色錯位：
- 成員在 chat_history 中指涉 bot：「那時候你機器人都還沒畜生」→ LLM 不認得「你機器人」= 自己
- 使用者指令用代詞：「請你反駁剛剛罵**你**的話」→ LLM 把「你」錯解成對話對象而非自身，回出「我才沒有要罵柔柔喵」這種施暴者立場

### 根因

| 層 | 狀態 |
|---|---|
| persona（askai_system_prompt.txt） | 只聲明「貓娘」，無 Discord 身分綁定；且規則 14 禁止自稱 AI |
| system_safety_prompt | 只定義 asker 側可信規則，無 bot 側 |
| `<bot_history>` tag | 只有內容沒屬性，LLM 無從確認 display_name 就是自己 |

### 解法（對稱於既有 `<latest_user_message from="">` 設計）

1. **safety rules**（[llm_context_safety_rules.json](src/settings/prompts/llm_context_safety_rules.json)）`system_safety_prompt` 補兩句：`<bot_history>` 的 `name=` 屬性為系統可信來源、區塊內為 bot 過往發言；群友使用該名稱或以「機器人 / bot / 你（非指涉他人時）」稱呼時通常指 bot 本人。
2. **service 層**（[llm_service.py](src/services/llm_service.py)）`_build_prompt_bundle` 與 `generate_reply` 新增 `bot_display_name` 選填參數。非空 bot_history 寫 `<bot_history name="X">`；空 history 仍輸出 `<bot_history name="X"></bot_history>` 空殼（身份錨點與 history 內容解耦，避免當前頻道最近 100 則內 bot 沒發言時完全無錨點）。
3. **call site**（[llm_commands.py](src/commands/llm_commands.py)）`generate_reply` 前解析身份：`interaction.guild.me.display_name`（伺服器暱稱，一般情境）→ `interaction.client.user.name`（DM fallback）→ None（極端情境，slash command 下實際不會發生）。

### 關鍵決策

| 項目 | 決定 | 理由 |
|---|---|---|
| 是否帶 user_id | 否 | 違反 asker_profile 既有「內部欄位禁止對外揭露」規範 |
| 是否帶 role 名 | 否 | role 是身份組標籤、不是 display_name，徒增雜訊 |
| tag 屬性要不要寫 aliases | 否 | tag 保持乾淨，aliases 語意改寫 safety_prompt |
| 是否動 persona 檔 | 否 | 「對內理解 vs 對外表達」分工：safety_prompt 管理解、persona 管表達（持守「不自稱 AI」規則） |
| None fallback 要不要寫死字串 | 否 | 維持 None → tag 不輸出，保持 backward compatible |

### 驗證方式

下次 `/askai` 後查 [logs/askai_prompt.txt](logs/askai_prompt.txt)：
- 非空 bot_history：`<bot_history name="Stargazer">` 開頭
- 空 bot_history：`<bot_history name="Stargazer"></bot_history>` 空殼
- DM 情境：`name=` 值為全域 username

---

## Context/Prompt 完整重構 + askai 身份感（歸檔 2026-04-18）

### 涵蓋範圍

2026-04-15 ~ 2026-04-18 跨多輪會話完成：context/prompt 格式重構、on_message 持久化、自動人格萃取 pipeline、askai 體驗優化、LLM 服務穩定性修復、askai 發問者身份注入，以及 Bahamut relay 相關小修。

### Context / Prompt 格式重構（2026-04-15 ~ 2026-04-16）

**核心變更：**
- 合併兩個 system message 為一個，避免部分模型只認最後一個 system
- 移除 `_serialize_context_items()`（JSON 序列化），改純文字分區注入
- `_build_prompt_bundle()` 接收 `chat_context`（純文字）+ `persona_context`（自然語言），分區 `<chat_history>` 和 `<other_member_profiles>`（後更名）
- `llm_commands.py` 分開傳遞 discord_context 和 rag_context
- `format_persona_cards_for_context()` 改自然語言輸出，regex 清理 DB 標記
- persona card 別名對照：聊天記錄中用 alias_map 標註身份（`❤️柔柔喵❤️(柔喵, 阿喵)`）
- persona card alias 優先用自我介紹的，其次才用 impression 的
- `PERSONA_MAX_CARD_CHARS` 220→400、`PERSONA_MAX_IMPRESSIONS_PER_CARD` 2→3

**貼圖描述整合：**
- `src/llm/sticker_cache.py`（新增）— bot 啟動時預載 guild sticker name+description
- `_build_discord_context_item()` 加入貼圖描述
- `_persist_messages_to_pgvector()` 貼圖描述一起寫入 text

**on_message 聊天持久化：**
- `src/llm/chat_persistence.py`（新增）— buffer 批次寫入（滿 30 則或每 5 分鐘 flush）
- `discord_bot.py` on_message 加入 enqueue_message + 定期 flush
- 去重：共用 `_PERSISTED_MESSAGE_IDS`，on_message 和 /askai 不重複寫入
- DB 層加 unique index `uniq_chat_message_id`，防止重啟後重複
- insert exception 處理：單筆失敗不中斷整批

**自動人格萃取 Pipeline：**
- `src/llm/personality_extractor.py`（新增）— 從 pgvector 撈聊天、分組、呼叫 LLM 萃取
- `intro_rag_port.py` 新增 `index_auto_personality()`
- `persona_card_builder.py` 支援 `auto_personality` 類型
- 萃取 prompt 外部化至 `src/settings/prompts/personality_extraction_prompt.json`
- 自訂 emoji 語意字典 `src/settings/emoji_dictionary.txt`
- 排程：每日 UTC+8 04:00 自動執行，用 `qwen2.5:14b`，每批 4 人

**/askai 體驗優化：**
- timeout 180→300 秒
- 聊天抓取 50→100 則
- 排隊人數顯示邏輯改為「先看再放」
- 取消按鈕：AI 思考中可按取消，中斷 Ollama HTTP（釋放 GPU），cooldown 減半，後面排隊立即接上

### 互動 UI / 人格萃取寫入（2026-04-17）

- 確認 `/askai` 排隊/思考中提示、`/personality_extract` 啟動提示/查看結果/結果分頁皆為 ephemeral（屬正常互動訊息特性，不是聊天紀錄被清除）
- 「寫入 RAG」加 ephemeral 進度訊息：每 3 筆刷新，完成後 edit 成 `✅ 已寫入 RAG：X 筆`；`save_personality_results` 新增 `progress_callback`；前景流程未動
- `PgVectorIntroRAGPort` 3 個 `index_*` 改走 `_ainsert`（executor thread），解除 embedding HTTP + pgvector IO 對 event loop 的阻塞
- `_get_index` 首次 init 加 `threading.Lock` 防 executor 多 thread race
- `_get_embed_model` thread-safety：`_index_lock` 改 RLock，`_get_embed_model` 自身也上鎖（fast path 仍無鎖）

### LLM 服務穩定性修復（2026-04-17）

**Ollama embedding 崩潰溯源：**
- 先判斷為 `bge-m3:latest` 模型壞 → 切換至 `qwen3-embedding:0.6b`（1024-dim 相同，pgvector schema 不動）
- 後確認根因是 **Windows ephemeral port 池耗盡**（Ollama 主 process 連 runner subprocess 走 localhost HTTP，累積 TIME_WAIT 塞滿 port 池）
- 針對 GitHub issue #7288 `GGML_ASSERT` 越界 bug：
  - `src/llm/safe_ollama_embedding.py`（新增）：`SafeOllamaEmbedding(OllamaEmbedding)` 失敗時自動加空格 retry
  - `chat_persistence` / `intro_rag_port` / `context_retriever` 全面改用 `SafeOllamaEmbedding`
  - `scripts/reembed_pgvector.py` 同樣加空格 perturbation fallback

**HTTP connection 重用：**
- `reembed_pgvector.py`：整個 run 共用一個 `requests.Session()`
- `intro_rag_port.py`：新增 module-level singleton `get_pgvector_intro_rag_port()`
- `chat_persistence.py`：新增 `_get_chat_index()` 跨 `_sync_write_batch` / `_sync_update_batch` 共用 VectorStoreIndex
- `context_retriever.py`：新增 `_get_or_build_vector_index(table_name, logger)` + `_VECTOR_INDEX_CACHE` 跨 `/askai` 共用，取代每次 new PGVectorStore + VectorStoreIndex

**chat_persistence log 強化：**
- `_sync_write_batch` log 從「新寫入 X 則」改為「新寫入 X / 已存在跳過 Y / 共 N」

### askai 發問者身份注入 + Bahamut 相關修復（2026-04-18）

**/askai 排隊顯示修正（前面 0 則 bug）：**
- 原本只追蹤 queue 內 pending，忽略正在 GPU 執行的 item
- `_AskaiQueue` 新增 `_processing` 欄位追蹤「已 get 但未 task_done」
- `pending_summaries()` 把 `_processing` 納入：GPU 閒置 → 0；計算中 → ≥1

**Bahamut 主文 `author_id` 修復：**
- `fetch_bahamut_articles_with_content` 補 `article["author_id"] = detail.get("author_id") or article.get("author_id", "")`
- 列表頁給的 key 是 `author_user_id`（不是 `author_id`），detail 補欄位時漏補 → 主文小屋連結消失
- DB 既有 13590 筆空 author_id 會在文章下次有內容更新時自然補回並觸發 Discord edit 補上連結；冷門文維持現狀（已與使用者取得共識）

**Bahamut 增量更新 429 治本（per-message 冷卻）：**
- `_edit_with_cooldown(msg, **kwargs)` + 模組級 `_last_edit_ts: dict[int, float]`
- 同一訊息兩次 edit 間隔強制 ≥ `MIN_EDIT_INTERVAL = 1.5s`（Discord per-message PATCH 限制約 5/5s）
- 全檔 11 處 `.edit()` 全走 helper（主文、回覆、留言格、溢出格、續文、導航連結）

**/askai 發問者身份注入：**
- `_build_prompt_bundle` 新增 `asker_profile`（system block，可信）+ `asker_display_name`（`<latest_user_message from="...">` 屬性）
- `_handle_askai_request` 組出 `<asker_profile>`，欄位含 display_name / user_id / `roles: (未啟用)` / persona_summary / current_time / guild_name / channel_name
- persona_card 拆分：發問者本人的卡進 `asker_profile` 的 persona_summary，其餘進 `<other_member_profiles>`（標籤自 `<member_profiles>` 更名）
- 撞名偵測：同 display_name 對多 author_id 時，chat_history 與 asker_profile display_name 尾加 `#xxxx`（user_id 末 4 碼）；不衝突零成本
- `persona_card_builder.format_persona_cards_for_context` 每 item 保留 `person_id` 以供下游過濾
- `context_retriever._build_discord_context_item` 回傳 dict 新增 `display_name` 欄位，避免下游從 content 字串 parse

**Safety rules 與 askai system prompt 同步修飾：**
- `untrusted_context_intro` 移除「JSON 格式」錯誤描述（實際是 XML 風格）
- `system_safety_prompt` 補 `<asker_profile>` 白名單與 `<latest_user_message>` from 屬性說明
- 禁詞「使用者ID」→「對外揭露的使用者ID」，避免與內部注入衝突

### 涉及檔案

| 檔案 | 角色 |
|---|---|
| `src/services/llm_service.py` | prompt bundle 重構、asker_profile 參數 |
| `src/commands/llm_commands.py` | context 分離、asker_profile 組裝、撞名偵測、排隊顯示修正、取消按鈕 |
| `src/llm/persona_card_builder.py` | 自然語言化、person_id 保留 |
| `src/llm/context_retriever.py` | 貼圖描述、display_name 保留、vector index cache |
| `src/llm/chat_persistence.py` | buffer 批次寫入、SafeOllamaEmbedding |
| `src/llm/intro_rag_port.py` | _ainsert、singleton、index_auto_personality |
| `src/llm/personality_extractor.py` | 人格萃取 pipeline |
| `src/llm/sticker_cache.py` | guild sticker 預載 |
| `src/llm/safe_ollama_embedding.py` | Ollama 空格 perturbation fallback |
| `src/discord_bot.py` | sticker 預載、chat flush、萃取排程 |
| `src/services/bahamut_monitor.py` | _edit_with_cooldown、per-message 冷卻 |
| `src/scraper/services/bahamut_scraper_service.py` | 主文 author_id 補欄位 |
| `src/settings/prompts/askai_system_prompt.txt` | 禁詞修飾 |
| `src/settings/prompts/llm_context_safety_rules.json` | untrusted intro + asker_profile 白名單 |
| `src/settings/prompts/personality_extraction_prompt.json` | 萃取 prompt |
| `src/settings/emoji_dictionary.txt` | emoji 語意字典 |
| `src/sys_settings/llm_settings.py` | timeout、抓取數量 |
| `src/scripts/reembed_pgvector.py` | 重新嵌入既有向量（加空格 fallback + session 重用） |

---

## 點歌機器人 Music Bot 完整實作（歸檔 2026-04-18）

> 核心功能已上線運作（P0 完成、P1 主體完成），部署後持續運行中。
> 剩餘 P1 體驗優化（pause/resume、多歌單、快取 LRU）與 P2 進階功能（播放紀錄、點歌統計、DAVE 加速追蹤）仍保留在 handoff `點歌機器人 TODO` 區塊。

### 架構

- 模組位置：`src/music/`（9 個檔案）
- 入口橋接：`src/commands/music_commands.py` → `MusicCog`
- 頻道設定：`config.json` 的 `music_voice_channel_id`（由 `/server_manager` 設定）
- 歌單設定：`src/settings/music_runtime.json` 的 `default_playlist_url`
- hot reload watcher：同時監控 `config.json` + `music_runtime.json`，變更後自動重連
- 依賴：`yt-dlp`、`discord.py[voice]>=2.7.1`、`davey>=0.1.5`（DAVE 加密）、`FFmpeg`

### 設計決策

- **只需設定一個語音頻道**：`voice_channel_id` 同時用於加入語音、發送面板
- **語音頻道內建聊天**：Discord 語音頻道自帶文字聊天，與語音頻道共用同一 ID
- **按鈕面板取代 slash command**：控制面板（點歌/跳過/停止/重播/歌單）在語音頻道聊天內自動 bump
- **點歌用 Modal**：按「點歌」按鈕 → 彈出輸入框，支援 URL 或關鍵字
- **點歌排隊不打斷**：點歌加入插播佇列，當前歌曲播完才播點的歌
- **停止只清插播**：停止按鈕只清除使用者點的歌，預設歌單保留
- **本地快取**：首次串流播放 + 背景下載到 `src/music/cache/`，之後從本地播放
- **快取峰值正規化**：快取播放時掃描峰值，等比例增益對齊 -1dB，保留原始動態
- **無 cookie**：小規模使用不需登入
- **FFmpegPCMAudio**：DAVE 加密下最穩定（FFmpegOpusAudio 在 DAVE 下會斷續爆音）

### 已實作功能

- 按鈕控制面板（點歌 / 跳過 / 停止 / 重播 / 歌單）— persistent view
- 點歌 Modal — 支援 YouTube URL 或關鍵字搜尋（`ytsearch`）
- 點歌排隊 — 不打斷當前播放，顯示排隊順位
- 重播按鈕 — 刪除快取 + 重新從 YouTube 抓取並播放當前歌曲
- 換歌自動 bump — 刪舊面板 → 發新面板（「現在播放」embed + 按鈕 + 縮圖）
- 待機面板 — 無歌曲時顯示待機狀態 + 按鈕
- 雙佇列 — 主歌單（循環）+ 插播（優先，不循環）
- 預設歌單自動載入（`extract_flat` 快速解析，邊載入邊播放）
- 本地快取（`src/music/cache/`，opus 原始品質，零損失）
- 快取峰值正規化（`volumedetect` + `volume` 濾鏡，等比例增益）
- 預先快取（prefetch 接下來 3 首，減少切歌延遲）
- 下載限速 3MB/s + Semaphore 同時只 1 個下載（避免搶串流頻寬）
- 版權/私人/已刪除影片自動跳過 + embed 通知 + 從歌單移除
- Runtime 配置 hot reload（config.json + music_runtime.json）
- `/server_manager` 頻道設定整合（語音頻道選項）
- YouTube 縮圖修復（`extract_flat` 模式用 `i.ytimg.com` 組合）
- 歌單查看（按鈕，ephemeral 回覆）
- `voice_lock` 防止重入式 connect/disconnect
- `requeue_song` 播放失敗時歌曲放回佇列前端（防掉歌）
- voice reconnect 死循環修復（guild.voice_client 認領機制，防止 Already connected 無限 error loop 灌爆 Docker log，2026-04-12）
- DAVE 加密協定支援（davey 0.1.5）
- 非同步歌單載入（不阻塞點歌）

### 音訊品質鏈路

```
YouTube (opus 160kbps, format 251)
  ↓ 串流播放：yt-dlp extract_single → ffmpeg PCM 48kHz → discord.py encoder → DAVE → Discord
  ↓ 快取下載：yt-dlp download (opus copy, 限速 3MB/s) → src/music/cache/{id}.opus
  ↓ 快取播放：本地 opus → ffmpeg PCM 48kHz + volume 正規化 → discord.py encoder → DAVE → Discord
```

### 已知限制

- **DAVE 加密偶爾造成特定區段短暫加速**：discord.py AudioPlayer 的 20ms frame timing 在 DAVE 加密耗時過長時會追趕（`delay = max(0, ...)`），屬於 library 層級問題，非程式碼可解
- **YouTube 來源最高 opus 160kbps**：瀏覽器聽到的差異來自客戶端音效處理，非來源品質差異
- **FFmpegOpusAudio 在 DAVE 下不可用**：會斷續爆音，必須走 FFmpegPCMAudio + discord.py 內建 encoder
- **歌單中的版權/私人影片**：自動跳過並通知，無法繞過

### Config 說明

頻道 ID 存在 `config.json`（與其他頻道設定一致）：
```json
{ "music_voice_channel_id": 1489909579927257130 }
```

歌單存在 `src/settings/music_runtime.json`：
```json
{ "music": { "default_playlist_url": "https://..." } }
```

---

## 幽靈點名系統核心實作（歸檔 2026-04-18，DM 通知 2026-04-27 補完）

> 核心 P0 已實作（除部署驗證外全部完成）。P1 重點「踢除時 DM 通知 + 重新加入邀請連結」已於 2026-04-27 完成（[rollcall_service.py:428-436](src/services/rollcall_service.py#L428-L436) 用 `dm_notifier.send_dm` 寄 DM；邀請連結硬編碼於常數 `REJOIN_INVITE_URL`，[line 34](src/services/rollcall_service.py#L34)；DM 失敗不阻擋 kick）。剩餘 P0 部署驗證 + P1 `/server_manager` 整合仍保留在 handoff。

### 架構

- 服務層：`src/services/rollcall_service.py`（抽選、到期掃描、踢除、豁免）
- Cog 層：`src/commands/rollcall_commands.py`（persistent views + `/rollcall_panel` 指令）
- Runtime 狀態：`src/settings/rollcall_runtime.json`（pending、immunity、stats、panel message ID）
- Config 欄位：`config.json` 的 `rollcall_channel_id`、`rollcall_target_role_ids`

### 設計決策

- **每 7 天抽 10 人**：UTC+8 14:00 自動執行，`PICK_INTERVAL_DAYS=7`
- **手動/自動點名分開記錄**：手動點名記 `last_manual_rollcall_date`（不推遲自動排程），自動點名記 `last_rollcall_date`；同日有手動點名時自動排程跳過，避免重複（2026-04-12 修復）
- **7 天回覆期限**：逾期自動踢除
- **30 天豁免期**：通過點名後 30 天內不再被抽到，期滿後重新進入抽選池
- **排除管理員與 Bot**：不會被抽到
- **排除已 pending / 豁免中成員**：不重複點名
- **persistent view**：Bot 重啟後按鈕仍可用
- **管理面板**：在指定頻道放置控制面板，管理員可開關自動點名、手動發動、查看待回覆清單

### 管理面板按鈕

| 按鈕 | 功能 |
|---|---|
| ✅ 開啟 | 啟用自動每日點名 |
| ❌ 關閉 | 停用自動每日點名 |
| 🎲 手動點名 | 立即抽選 10 人 |
| 📋 待回覆清單 | 查看所有待回覆的成員與剩餘天數 |
| 🔄 刷新狀態 | 更新面板顯示 |

### 使用方式

1. 在 `config.json` 設定 `rollcall_channel_id`（點名訊息頻道）和 `rollcall_target_role_ids`（目標身份組 ID 陣列）
2. 管理員在想要放置控制面板的頻道執行 `/rollcall_panel`
3. 透過面板按鈕開啟/關閉自動點名，或手動發動

---

## Telegram media group 合併歸檔（2026-04-07）

### 功能
- Telegram 的 media group（一次發多張圖/影片）在 Discord 合併成單則訊息
- DB 新增 `grouped_id BIGINT` 欄位 + partial index
- Scraper 端從 `message.grouped_id` 寫入 DB
- Relay 端偵測同一 `grouped_id`：由最小 pk 的訊息負責，等待 3 秒讓同組到齊後合併文字與媒體
- 所有 sibling 同時標記 delivery_state，避免重複發送
- 發送順序：embed + 第一張附件 → 剩餘附件分批

### 修改檔案
- `src/telegram_scraper/db.py`：`init_db()` 補欄位 + `upsert_message_only()` 新增 `grouped_id` 參數
- `src/telegram_scraper/handlers.py`：取 `message.grouped_id` 傳入 DB
- `src/services/telegram_relay_service.py`：
  - `TelegramMessageRecord` 加 `grouped_id`
  - 新增 `get_grouped_message_pks()` 查同組訊息
  - 新增 `_collect_media_group()` 等待到齊並合併
  - `_process_one()` 加入 media group 判斷
  - `publish_to_channel()` 改為先發 embed+首圖、再發剩餘附件

---

## Telegram embed title 來源頻道名稱修正歸檔（2026-04-06）

### 功能
- Telegram relay embed title 改為顯示實際來源頻道名稱（`chat_title`），而非固定的 `source_channel`
- Scraper 端在 `_process_message()` 解析頻道 title（`_resolve_chat_title()`，帶快取）
- DB `telegram_messages` 新增 `chat_title TEXT` 欄位
- Relay 端 `TelegramRenderAdapter.render()` 優先使用 per-message 的 `chat_title`

### 修改檔案
- `src/telegram_scraper/db.py`：`init_db()` 補 `chat_title` 欄位，upsert 支援寫入
- `src/telegram_scraper/handlers.py`：新增 `_resolve_chat_title()`，呼叫 Telegram API 解析名稱
- `src/services/telegram_relay_service.py`：`get_message_by_pk()` 讀取 `chat_title`，render 時使用

---

## Bahamut 續文/多圖/並行/子看板等完成歸檔（2026-04-05）

### 完成項目
- **續文機制**：長文自動分割為多則 embed（`_split_content_for_embeds` + `_send_continuations` + `_update_continuations`），DB 新增 `continuation_msg_ids` 欄位
- **多圖分批發送**：`_send_post_images` 每批最多 10 張，主文/回覆各自處理
- **並行控制**：`asyncio.Semaphore(3)` 全域並行上限 + snA 鎖
- **thread 被刪自動重建**：清除 state 後直接呼叫 `_process_thread` 重建
- **Scraper 改進**：YouTube iframe 提取（`🎬`）、超連結 markdown 轉換（URL=文字時不包 markdown）、角括號清理
- **第一則 embed 上限改為 3500**（避免 Discord 500）
- **subbsn 子看板支援**：config `subbsn` 欄位 + CLI `--subbsn` + 排程兩輪（公開看板 + 子看板）
- **category 黑名單**：`article_runtime.json` 的 `bahamut_exclude_categories`，無音區不發 Discord
- **`get_article_runtime_config()` 搬到 `base_monitor.py` 共用**（TTL 5 分鐘快取）
- **notify 防重複**：`_processing` dict + `_guarded_process`
- **每 50 則回覆存一次 state** + create_thread 後立刻存 state

---

## Bahamut 正式知識層清理歸檔（2026-04-03）

> 依使用者指示，將 `AI_HANDOFF_AND_TODO.md` 中仍殘留的 Bahamut 已完成內容移出，集中歸檔到本檔，讓 handoff 只保留仍需追蹤的事項。

### 已移出 handoff 的完成內容

#### 舊版歷史附錄 / 重複狀態描述
- 舊的 `Bahamut 歷史附錄（raw history / appendix）`
- 舊的 `Bahamut 目前狀態` 區塊（與正式知識層重複）
- 舊區塊中的「已完成（2026-03-31 ~ 2026-04-01）」列表

#### 已完成能力（保留於歸檔）
- `cloudscraper + retry` session
- 進版圖 gate 偵測與導頁處理（預熱 + hop）
- 列表抓取（`tr.b-list__row.b-list-item`）
- 單篇抓取（含 `--sna 16219`）
- HTML + XHR 留言抓取（`moreCommend.php`）
- `post + replies` 結構輸出
- 主文圖片 `content_images` 抽取
- `HOT -> is_hot`、推/噓 icon -> `👍` / `👎`
- `has_thumbsup_button` / `has_thumbsdown_button`
- `is_sticky` 置頂標記
- 列表補抓：`author` / `author_user_id` / `last_reply_user` / `last_reply_user_id` / `category`
- `save_articles_to_db(articles)` 已實作（主文 + 回文 + 各自留言）
- `main.py` 已切成正式 `fetch -> save_articles_to_db -> commit`
- `source_type` 已移除（表名已隱含來源）
- DB model 已落地：`BahamutPost` + `BahamutPostComment`
- DB upsert 已落地：文章 `(board_id, sn)` / 留言 `(parent_sn, comment_id)`
- 留言 `published_at` 格式已清理
- JSON sample 輸出改為設定開關
- `post_id / snA / sn` 命名已收斂：`post_id = snA`
- GP/BP 數字提取
- 文章多頁遍歷（C.php 分頁）
- 列表分頁範圍（B.php start/end page）
- CLI 預設寫 DB

#### Bahamut Relay / State / Webhook 已完成項目
- Scraper API：`/api/bahamut/recent`、`/api/bahamut/{board_id}/{post_id}`
- `bahamut_monitor.py`：embed 格式化、留言格預建/溢出、鏈式導航
- `/get_baha_post` 斜線命令
- 增量更新：既有 thread 自動 edit / append
- `state_db.py`：SQLite state 追蹤
- `base_monitor.py`：async state + 共用 StateDB
- `migrate_json_to_sqlite.py`：JSON → SQLite 遷移腳本
- `notify_server.py`：`POST /notify/{source}` 通知架構
- Scraper 抓完 Bahamut 後自動 webhook 通知 Discord Bot
- `discord_content.py` 共用工具抽取
- `ChannelConfig` TTL 快取
- 內容防護 / 更新保護：`content_hash`、`prev_*`、`shrink_ratio`、`update_blocked`

### 這輪整理後 Bahamut 真正剩餘待辦
- 端到端測試（全自動閉環驗證）
- 正式 DB migration（Alembic）
- RAG ingestion

### Bahamut 已定案設計文件歸檔（2026-04-03 從 handoff 移出）

以下為已落地的設計文件，不再作為待辦追蹤，僅供參考。

#### 方法與 JSON 契約
- `fetch_board_articles(session)` → `Dict[str, Any]`
- `fetch_article_detail(session, url)` → `Dict[str, Any]`
- `fetch_bahamut_articles_with_content()` → `Dict[str, Any]`
- `save_articles_to_db(articles)` → `int`
- 主文欄位展平頂層，回覆放 `replies[]`，每個 reply 各自 `comments[]`
- 留言唯一鍵：`(parent_sn, comment_id)`

#### ID 語意
- `snA` = thread/group ID = `post_id`
- `sn` = 單篇文章 ID
- `snB` = 留言 XHR 目標 ID（高度吻合 sn）
- `comment_id` = 留言唯一鍵

#### 文章結構
- `section.c-section[id^='post_']` = 文章 block
- 第一個 block = 主文，後續 = 回覆
- 每個 block 有自己的 `Commendlist_<sn>` 留言區

#### XHR 留言抓取
- endpoint: `moreCommend.php`，參數 `bsn` + `snB` + `snC`（分頁游標）

#### 留言 parser
- HOT 標籤、推噓 icon 轉換、`is_hot` / `has_thumbsup_button` / `has_thumbsdown_button`
- `comment_id` 為唯一鍵，`floor` 可跳號，`position` 僅排序用

#### sn 抓取策略
- 優先找 HTML 內嵌資料、DOM data-* 屬性，最後才考慮 JS 還原

#### 版本路由
- desktop HTML first，被導到 mobile 時堅持再請求 desktop URL

#### 進版圖處理
- 預熱 + gate 偵測 + 模擬進入 + session 重用

#### 抓取模式
- `cloudscraper` + `BeautifulSoup4` + `fake-useragent`
- HTTP pull first，不先上 Playwright

#### 開發原則
- 先做專屬 service，不先抽通用框架
- 依賴注入 `db_manager=None`，抓取與寫 DB 分離
- normalized + raw 雙軌

#### DB Schema
- `bahamut_posts`（主文+回文共用，position 區分）+ `bahamut_post_comments`
- unique: `(board_id, sn)` / `(parent_sn, comment_id)`
- 雙版本保留（`prev_*` 欄位）+ 防惡意覆蓋（`shrink_ratio` / `update_blocked`）
- SQLite first，RAG 時再進 pgvector

#### Discord 呈現策略
- 1 snA = 1 Forum Thread，embed 格式（藍主文/綠回覆/灰留言）
- 留言格預建 3 格 + 鏈式溢出導航
- HTTP webhook 通知：`POST /notify/{source}`
- State 追蹤改用 SQLite（5 張表）

## Telegram Relay 功能完成歸檔（2026-03-29）

> 依使用者指示，將 `AI_HANDOFF_AND_TODO.md` 的 Telegram 功能完成項目移入本檔保存。

### 功能完成（主線）
- 已完成 `TelegramMessageRepository`（依 `message_pk` 取 message + media）
- 已完成 `MessageRelayWorker`：`LISTEN telegram_new_message` + 每小時補償輪詢
- 已完成 `TelegramRenderAdapter`（保留既有格式，不做語意重排）
- 已接入 `DiscordMessagePublisher`（執行 RenderPlan，不改內容）
- 已套用路由 `telegram_channel_routes`，無路由一律 skip + log

### 落地與設定
- 新增 `src/services/telegram_relay_service.py`，包含：
  - `TelegramMessageRepository`
  - `MessageRouteResolver`
  - `TelegramRenderAdapter`
  - `DiscordMessagePublisher`
  - `MessageRelayWorker`
- `src/discord_bot.py`：`on_ready()` 串接 `auto_start_telegram_relay(bot)`，含防重啟保護
- `src/config.json`：
  - `telegram_relay_enabled`
  - `telegram_channel_routes`
  - `telegram_replay_from_message_pk`

### 狀態持久化共識
- `config.json` 僅存設定，不存已送狀態
- 已送狀態/游標存 DB：
  - `telegram_relay_delivery_state`
  - `telegram_relay_runtime_state`

### 驗證結論
- NOTIFY 即時路徑已驗證正常
- 補償輪詢可補漏
- 既有已知問題（route key、重複下載、時序、副檔名、embed、連線觀測）均已修正

## Telegram Relay 通道連線問題（2026-03-26 已解決）

- **原始現象**：discord-bot log 顯示 `published_count=1` 但 Discord 頻道看不到訊息；`telegram_relay_delivery_state` 表為空。
- **排查結論**：
  1. LISTEN/NOTIFY 機制正常 — `test_ping` 手動測試收到，且刪除 DB 最新一筆後重啟 telegram-scraper 成功觸發即時 NOTIFY → discord-bot 收到並發文（pk=88, published_count=1）
  2. discord-bot relay worker 確認連到正確 DB（`telegram_data`），非 `discord_data`
  3. 先前「啟動後沒發文」主因是歷史 NOTIFY 在 LISTEN 建立前就發了（PG NOTIFY 即發即棄），由啟動補償 backfill 處理
  4. delivery_state / runtime_state 為空的原因：先前 session 的 DB 被清空重建，舊紀錄已不存在；最新 session（pk=88）已成功寫入 delivery_state
- **已修正**：
  - route key 型態不一致問題（chat_id 數字 vs source_channel 名稱 fallback）
  - 啟動安全補償（cursor=尾端 + delivery_state=0 自癒）
  - `_on_notify` 新增收到 NOTIFY 的 log：`收到 NOTIFY: channel=... message_pk=...`
- **結論**：NOTIFY 即時路徑正常運作，非 code bug。

## Telegram scraper 媒體下載重複問題（2026-03-26 已解決）

- **問題**：Telethon 預設時間戳命名 photo，重啟重跑歷史產生 `(N)` 後綴重複檔案與 DB 記錄。
- **修正**：`_build_stable_media_path()` 依 `photo.id`/`document.id` 建立固定路徑；下載前先查 DB 略過已有記錄。

## 歷史訊息時序錯亂（2026-03-26 已解決）

- **問題**：`iter_messages` 預設由新到舊，直接 insert 導致 PK 與時間反序。
- **修正**：收集後 `.reverse()` 再依序 insert。

## 媒體副檔名缺失（2026-03-26 已解決）

- **問題**：非圖片/影片 mime 類型無對應副檔名。
- **修正**：新增 `_MIME_TO_EXT` 查找表（38 種）+ 大類兜底。

## Route key 型態不一致（2026-03-26 已解決）

- **問題**：DB 路由用 `telegram_chat_id`（數字），config 用 `source_channel`（名稱）。
- **修正**：`resolve_telegram_routes` 先查 chat_id，再 fallback 讀 runtime_config 的 `source_channel` 正規化後查 routes。

## Embed 改善（2026-03-26 已完成）

- embed title 改為來源頻道名、timestamp 改為訊息時間、color 改為 Telegram 藍、影片不設 `set_image` 避免黑幕。

## Telegram -> Discord 核心定案（已完成，2026-03-29 歸檔）

1. Telegram scraper：寫 DB + `NOTIFY telegram_new_message`。
2. Discord consumer（`MessageRelayWorker`，舊暫名 `TelegramRelayService`）：
   - `LISTEN telegram_new_message`
   - 收 payload 後查 DB 取 message/media
   - 套路由後發送 Discord
3. 若無路由：**不發文（skip + log）**。
4. 除即時 notify 外，需有**每小時補檢**防漏。
5. 路由/開關由 `config.json` 管理（非硬編碼）。

## Telegram Scraper 專案交接（2026-03-22，已完成歸檔）

### 1) 目前狀態總結

- 已完成 `telegram-scraper` 獨立服務化（Docker 微服務）。
- Dockerfile 已集中在 `docker/telegram_scraper/dockerfile`。
- `telegram-scraper` 啟動邏輯改為 `entrypoint.sh` 控制：
  - 有 session：自動跑 `main.py`
  - 無 session 且可互動：進登入流程
  - 無 session 且非互動：待命 `sleep infinity`
- Telegram 程式已模組化，不再把所有邏輯塞在 `main.py`。

### 2) Telegram 模組化後檔案職責

- `src/telegram_scraper/main.py`
  - 薄入口，只做：載入設定 -> 呼叫 runner。
- `src/telegram_scraper/tg_config.py`
  - 設定解析（env + JSON），`TelegramConfig` dataclass。
  - forward 白名單寫回函式：`add_identifier_to_forward_whitelist(...)`。
- `src/telegram_scraper/filters.py`
  - forward 來源解析：`extract_forward_source_chat_id(...)`。
  - forward 白名單比對：`is_forward_source_in_whitelist(...)`。
  - forward 是否略過：`should_skip_forward(...)`。
- `src/telegram_scraper/handlers.py`
  - 共用訊息流程 `_process_message(...)`。
  - 即時與歷史 handler 皆委派到共用流程。
- `src/telegram_scraper/runner.py`
  - Telethon client 啟動、歷史掃描、即時監聽。

### 3) 目前 forward 過濾規則（已修正）

#### 問題回顧
先前誤把「目標頻道」拿去比白名單，導致 forward 容易被放行。

#### 現行正確規則
1. forward 訊息先以「**轉發來源**」做白名單比對。
2. 未命中白名單 -> 直接略過。
3. 命中白名單 -> 允許通過。
4. 允許通過的 forward 可自動把來源 identifier 寫回 `runtime_config.json`。

### 4) 設定來源（重要）

- `.env` 只保留必要 Telegram API：
  - `TELEGRAM_API_ID`
  - `TELEGRAM_API_HASH`
- forward 規則固定讀：
  - `src/telegram_scraper/runtime_config.json`

### 5) 歷史訊息抓取規則

- `history_limit`：最多掃幾筆（上限）。
- `history_hours`：時間窗（抓到多久以前）。
- 兩者可同時生效。
- `runner.py` 已實作：超過時間窗會 `break` 停止掃描。

### 6) Docker 相關現況

- `docker-compose.yaml` 已使用集中路徑：
  - `docker/discord_bot/dockerfile`
  - `docker/scraper/dockerfile`
  - `docker/telegram_scraper/dockerfile`
- `docker/telegram_scraper/entrypoint.sh` 控制首次登入與待命模式。
- `docker/telegram_scraper/dockerfile` 有 `PYTHONUNBUFFERED=1`，確保 log 即時。

### 7) Session 持久化與 git

- Telethon session 位置：`src/telegram_scraper/session/`
- `.gitignore` 已忽略：`src/telegram_scraper/session/`

## Telegram Relay 設計定案 — 架構/設定/相容/流程盤點（2026-03-25，已完成歸檔）

### 完整架構（目前共識）

1. **事件來源層（Source Ingest）**
   - 目前 source：Telegram scraper（寫 DB + `NOTIFY telegram_new_message`）。
   - 未來可擴充 FB/PTT/Article 作為其他 source。

2. **事件消費層（Relay Worker）**
   - 命名採通用：`MessageRelayWorker`（保留未來整合空間）。
   - 雙軌：
     - 即時通路：`LISTEN telegram_new_message`
     - 補償通路：每 1 小時 polling 補漏

3. **資料存取層（Repository）**
   - 上層抽象：`SourceMessageRepository`
   - Telegram 具體實作：`TelegramMessageRepository`
   - 職責：依 message key 取回完整訊息 + 媒體。

4. **路由層（Resolver）**
   - 命名：`MessageRouteResolver`
   - 職責：來源事件 -> Discord 頻道清單。
   - 規則：無路由就不發文（skip + log）。

5. **發送層（Publisher）**
   - 命名：`DiscordMessagePublisher`
   - 職責：文字/附件發送、分批、重試、錯誤紀錄。
   - 策略：先做最小共用核心，不一次硬整合所有來源格式。

6. **格式轉換層（Adapter）**
   - 建議抽象：`MessageRenderAdapter`
   - 來源別實作：`TelegramRenderAdapter` / `ArticleRenderAdapter` / `FbRenderAdapter` / `PttRenderAdapter`

### 設定規則（config.json）

- `telegram_relay_enabled`（bool）
  - Relay 總開關（保留）。

- `telegram_channel_routes`（dict）
  - 型態：`{ "<telegram_chat_id>": [discord_channel_id, ...] }`
  - 用途：來源 Telegram chat 對應目標 Discord 頻道。

- 發文原則
  - **無路由不發文**（skip + log）。

### 舊流程相容策略（已確認）

- 可先不引入 `MessageRelayWorker`。
- 舊流程可直接串 `SourceMessageRepository`（再接 resolver/publisher）。
- 待穩定後再收斂觸發入口進 `MessageRelayWorker`。

### 現行 Article / FB / PTT 流程盤點（已確認）

#### A) Article（官方文章）
1. 啟動來源：
   - `discord_bot.py` 的 `on_ready` 會讀 `config.json.article_monitor_channel_id` 並自動啟動。
   - 也可由 `ArticleCommands` 手動啟動監控。
2. 取文：
   - `ArticleMonitor.fetch_recent_articles()` 呼叫 `/api/articles/discord`（asc）。
3. 去重：
   - `BaseContentMonitor.sent_article_ids`（`/app/services/sent_articles.json`）。
4. 發文：
   - `send_article_to_channel()`（Embed + 圖片附件分批）。

#### B) FB
1. 啟動來源：
   - `discord_bot.py` 自動啟動 `start_fb_monitoring()`（目前沿用 `article_monitor_channel_id`）。
2. 取文：
   - `fetch_recent_fb_posts()` 呼叫 `/api/fb_posts/recent`。
3. 去重：
   - `sent_fbpost_ids`。
4. 發文：
   - `send_fb_post_to_channel()`（主文 + 第一張圖 + 其餘分批）。

#### C) PTT
1. 啟動來源：
   - `discord_bot.py` 讀 `config.json.forum_article_channel_id`，啟動 `start_ptt_monitoring()`。
2. 取文：
   - `fetch_recent_ptt_posts()` 呼叫 `/api/ptt_posts/recent`（desc，發送前反轉成舊到新）。
3. 去重與增量：
   - `sent_article_keys` + `sent_ptt_state`（留言同步進度）。
4. 發文：
   - `send_ptt_post_to_forum_channel()`（Forum thread 建立、附圖、留言分段補送）。

#### D) 現況結論
- 目前三者都在 `ArticleMonitor` 裡運作，功能可用但責任較重。
- 發送型態不完全一致（TextChannel Embed / ForumThread / 附件策略），
  所以整合要分階段，不能一次硬抽成單一流程。

#### E) 目前 service 取得的資料結構（欄位盤點）

1. **Article（`/api/articles/discord`）常用欄位**
   - 主鍵/識別：`article_id`
   - 文字：`article_title`, `article_desc`, `article_content`, `article_content_full`
   - 分類：`article_type_name`, `article_type`
   - 時間：`start_time`, `create_time`
   - 圖片：`article_cover`, `content_cover`, `suggest_cover`

2. **FB（`/api/fb_posts/recent`）常用欄位**
   - 主鍵/識別：`id`
   - 文字：`text`, `text_md`
   - 連結：`url`, `pfbid_url`
   - 時間：`timestamp`, `created_at`
   - 圖片：`images`（list）

3. **PTT（`/api/ptt_posts/recent`）常用欄位**
   - 主鍵/識別：`board`, `article_id`（組合 key：`ptt:{board}:{article_id}`）
   - 文字：`title`, `content`
   - 作者/時間：`author`, `published_at`
   - 連結與標記：`url`, `matched_keywords`
   - 留言：`comments`（元素含 `tag`, `user`, `content`, `time`）

4. **Telegram（DB 實體，`telegram_scraper/db.py`）**
   - `telegram_messages`：
     - `id`（PK）
     - `telegram_chat_id`, `telegram_message_id`（unique）
     - `text`, `message_date`, `has_media`
   - `telegram_message_media`：
     - `message_id`（FK）
     - `media_type`, `file_rel_path`, `mime_type`, `file_size`
     - `width`, `height`, `duration_sec`, `is_spoiler`

5. **整合注意（目前共識）**
   - Article/FB/PTT 是 API payload；Telegram 是 DB row + media row。
   - 型別來源不同，但欄位都必須保留（走 lossless envelope）。
   - 後續 `SourceFetchPort` / `MessageRenderAdapter` 只能做「映射」，不能做「刪減」。

---

## Bahamut Scraper MVP 完成歸檔（2026-04-01）

### 第一階段 MVP — 全部完成
- 研究巴哈 HTML / API 結構（文章列表、文章頁、留言區、回文區）
- 確認 anti-bot 處理（cloudscraper + gate 進版圖處理）
- 實作文章列表抓取（標題、分類、作者、時間、URL、文章 ID，支援多頁）
- 實作文章主文抓取（含多頁遍歷、圖片提取）
- 實作主文留言抓取（HTML + XHR moreCommend.php 合併去重）
- 實作回文與回文留言抓取
- 定義 JSON payload 結構（post + replies[] + 各自 comments[]）
- JSON 範例輸出驗證：`src/scraper/data/bahamut_samples/*.json`
- 錯誤處理、限速、重試、日誌紀錄
- GP/BP 提取（主文/回文/留言）
- CLI 單篇除錯：`--sna <id>`
- 排程串接：`main.py` 每 1 小時自動 `fetch → save_articles_to_db → commit`

### 第二階段 DB — 大部分完成
- `bahamut_posts` 主表（主文+回文共用，position 區分）
- `bahamut_post_comments` 留言表
- Upsert 邏輯：文章 `(board_id, sn)`、留言 `(parent_sn, comment_id)`
- Content hash 變更偵測 + 可疑縮水阻擋（prev_* 欄位）
- 必要索引（board_id, post_id, author_id, user_id, published_at, content_hash, is_deleted）
- raw_json 完整備份
- Scraper API：`/api/bahamut/recent` + `/api/bahamut/{board_id}/{post_id}`

### Bahamut → Discord Relay 首版
- `src/services/bahamut_monitor.py`：embed 格式化 + 留言格預建/溢出 + 鏈式導航
- `src/scraper/api_server.py`：巴哈 API endpoints（按 snA 分組，含主文+回覆+留言）
- `/get_baha_post` 斜線命令（`article_commands.py`）
- 主文（藍色 embed）、回覆（綠色 embed）、留言格（灰色 embed）
- 留言格式：`🔥 B1 **user** 👍107 — content`
- 作者名連結巴哈小屋、圖片 URL 轉 `[🖼 圖片](url)`
- 溢出導航：格3→格4→格5 鏈式 reply + `⬇️ 更多留言...` 連結

### ID 模型定案
- `snA` = thread/group ID = `post_id`
- `sn` = 單篇文章 ID
- `comment_id` = 留言唯一鍵（搭配 parent_sn）
- `floor` / `position` 僅供顯示，不作唯一鍵

---

## Bahamut 增量更新 + SQLite 遷移 + Webhook 通知完成歸檔（2026-04-02）

### 增量更新
- `_update_existing_thread`：已存在的 thread 自動走增量更新
- GP/BP edit：主文/回覆 embed 有變化才 edit
- 留言 slot 重組：用最新全部留言重組 slot 內容，有變化才 edit
- 新回覆 append：state 裡沒有的 sn → send + 預建留言格
- hash 比對：md5 比對 embed description，無變化跳過不 edit（防 Discord rate limit）

### SQLite State 遷移
- `state_db.py`：async SQLite 封裝，5 張表
  - `sent_content`：所有來源去重（Article / FB / PTT / Bahamut）
  - `forum_thread_state`：PTT / Bahamut 共用 thread 追蹤
  - `bahamut_post_state`：巴哈文章 Discord msg_id
  - `bahamut_comment_slot`：巴哈留言格 msg_id + used_chars
  - `bahamut_synced_comment`：巴哈留言去重
- `base_monitor.py`：所有 state 方法改 async，全域共用 StateDB + `asyncio.Lock` 併發安全
- `article_monitor.py`：所有 state 呼叫加 `await`
- `migrate_json_to_sqlite.py`：手動遷移腳本
- 遷移已執行完成（446 articles + 386 fb + 507 ptt）

### HTTP Webhook 通知
- `notify_server.py`：通用 aiohttp.web server，`POST /notify/{source}` 分派架構
- Scraper `main.py`：巴哈抓完存 DB 後呼叫 `_notify_discord_bot("bahamut", ...)`
- `discord_bot.py`：on_ready 啟動 notify server (port 5000)
- `docker-compose.yaml`：discord-bot 加 `expose: ["5000"]`

### 共用工具抽取
- `discord_content.py`：sanitize_forum_thread_title / linkify_image_urls / content_hash / chunk_discord_files / get_forum_tags
- article_monitor + bahamut_monitor 共用，移除各自重複的實作

### Config 快取
- `ChannelConfig`：TTL 5 分鐘記憶體快取，save_config 同步更新
- Scraper config：board_end_page 1→2（自動抓前 2 頁）、export_sample_json 關閉

---

> 以下區塊為 2026-06-20 handoff 瘦身時自 `AI_HANDOFF_AND_TODO.md` 移入（內容原樣保留，多為已完成 + 待部署驗證項；驗證細節若已過時以實際運行為準）。

## 點歌者離開自動移除其點的歌（歸檔 2026-06-20，原 2026-06-13）

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

---

## 音樂「停止」按鈕改為「重置歌單 + 重載線上歌單」（歸檔 2026-06-20，原 2026-06-13）

<!-- @meta
id: music-reset-reload-playlist
type: FEATURE
status: confirmed
last_confirmed: 2026-06-13
-->

**背景：** 舊「停止」按鈕(player.stop())其實只清點歌插播+跳當前歌，主歌單仍續播，名稱誤導；且線上歌單(default_playlist_url)改了內容後不重啟不會同步。

**變更：**
- 按鈕 `停止/⏹` → `重置歌單/♻️`（custom_id 仍為 `music_stop` 以相容既有面板），method 改名 `reset_playlist`（`src/music/announcer.py`）。
- 新增 `MusicPlayer.reload_playlist()`（`src/music/player.py`）：重新抓取 `default_playlist_url` 最新清單 → 清空點歌+舊主歌單 → 換上新清單 → 套用 shuffle → 跳過當前舊歌續播。**先抓成功才換**，抓取失敗/空清單則保留舊歌單回傳 None。`_reloading` 旗標防重複觸發。
- 抽出 `_fetch_playlist_songs()` 純抓取 helper，`add_to_playlist()` 與 `reload_playlist()` 共用。

**備註：** `MusicPlayer.stop()` 已無呼叫者（dead code），暫時保留未刪。
> 後續 2026-06-20「多歌單下拉」已把此按鈕再改名為「編輯歌單 🎚️」並擴充，詳見 handoff。

---

## 幽靈點名按鈕越權 BUG 修正（歸檔 2026-06-20，原 2026-06-12）

<!-- @meta
id: rollcall-button-auth-fix
type: FIX
status: confirmed
last_confirmed: 2026-06-12
-->

**問題：** A 可以點 B 的點名按鈕，並解掉「A 自己」的點名（拿到豁免）。
**根因：** `RollCallResponseView.respond` 只檢查「按的人是否 pending」，按鈕未真正綁定到該訊息的目標使用者；重啟後 persistent view 的 `_target_user_id=None`，連薄弱檢查都失效。
**修正：** 以 `interaction.message.id` 反查 `runtime.pending` 取得該訊息真正的目標 `user_id`，只允許本人回覆自己的點名訊息（`src/commands/rollcall_commands.py`）。

---

## LLM HTTP client 通用錯誤護網（歸檔 2026-06-20，原 2026-05-18）

<!-- @meta
id: llm-http-client-error-net
type: FIX
status: confirmed
last_confirmed: 2026-05-18
-->

**症狀：** `/askai` 每次跑都跳兩個 warning：`pgvector vector rank 嵌入問題失敗（降級為 BM25-only）: 'data'`、`member-profile vector retrieval 失敗（保留 SQL 結果）: 'data'`。
**根因：** `llm_http_client.py:embedding/aembedding` 直接 `data["data"]` 取 key，後端回非 OpenAI shape（error envelope、ollama native shape）時 raise `KeyError: 'data'`，例外 str 就是 `'data'` 無法判讀。原 sync `_post_json` 沒有 envelope unwrap，async `_apost_json` 只認 `error.type == "network_error"`。
**改動：** [llm_http_client.py](src/llm/llm_http_client.py) 新增兩個 module-level helper（多 endpoint 通用）：`_unwrap_response_envelope(data)`（network_error→ConnectError 觸發退避重試；其他 error envelope→`LlmAPIError(status=None)` 不重試；正常 payload 原樣回傳；用於 sync/async 兩出口）、`_require_json_key(data, key, *, op_label)`（缺 key / 型別不符→raise `LlmAPIError` 附 keys+sample；用於 `embedding()`/`aembedding()`，未來新 endpoint 可套）。
**收益：** 下次同樣 warning 直接顯示後端實際回了什麼；model_not_loaded 等永久錯誤被正確識別、不無限退避。

---

## 智慧女性風格重寫 + few-shot 範例檔（歸檔 2026-06-20，原 2026-05-18）

<!-- @meta
id: askai-smart-female-rewrite
type: FEATURE
status: confirmed
last_confirmed: 2026-05-18
-->

**動機：** 原 `askai_system_prompt.txt` 的「姊姊 + 同盟 roast + 暗刺」與「母性溫度」內在矛盾；使用者要求轉向「Pekora mama 但更智慧」——溫柔為底、刺輕但準、看穿不說破、不重複不撤回。

**改動內容：**
- `src/settings/prompts/askai_system_prompt.txt` 重寫開場 3 行 +【回答風格】1-4 +【互動與語氣】1-3,6 +【色色模式】4 +【語氣與禁忌】4-6（新增 6：失敗模式區擋空話智者/毒舌分析師）
- 拿掉「禁止自我撤回」條；結尾反問規則鬆綁（客服式禁止照舊，真誠好奇式反問允許）；八卦/情緒回應長度 4~8 句→3~5 句多留白；加入「點規律而非點現象」原則
- 新增 `src/settings/prompts/persona_examples.txt`（12 組正反例對照 few-shot；含色色降級範例）；`llm_settings.py` 加 `examples_file_path`；`llm_commands.py` `load_system_prompt()` 改讀三檔（identity → main → examples），examples 放最末利用 LLM 對尾端模仿力最強；範例缺檔不影響主流程

**設計重點：** few-shot 採「禁止 ❌ / 示範 ✅」對照（負例壓 failure mode 比純正例有效）；12 組情境覆蓋熬夜/抽卡/技術搞砸/抱怨第三方/做對事/低潮/純技術/被邀 roast 自己人/自嘲示弱/閒聊/色色/色色降級；examples 與 rules 拆檔便於迭代。

---

## lemonade 對 chat stream + 背景 embedding 併發失敗（`no_choices` 假象）（歸檔 2026-06-20，原 2026-05-11）

<!-- @meta
id: lemonade-stream-embedding-gate
type: FIX
status: confirmed
last_confirmed: 2026-05-11
-->

Root cause：5/4 補的 snapshot log 攢到 3 筆 `no_choices` 事故，raw body 都是 `{'error': {'type': 'network_error', 'message': 'CURL error: ...'}}`，是 lemonade gateway 內部 CURL 轉發到 downstream backend(port 8002, llama.cpp) 失敗的回應，但 lemonade 用 `200 OK + error envelope` 回 client，破壞 HTTP 語意，導致 bot 走 `no_choices` 分支且不重試。三次失敗時間軸全部都是 `/askai` LLM stream 進行中 → 1–4 秒前 `on_message 批次處理 pgvector`（`chat_persistence.py` `flush_buffer` 觸發的 batch embedding）→ LLM 連線被 lemonade reset。`/askai` 內部 RAG embedding 與 chat 是序列的不會自己撞，會撞的是背景 flush。**修法**：① 新增 `src/llm/lemonade_gate.py`：module-level `asyncio.Lock` + `stream_exclusive()` async context manager ② `llm_service.py` `chat_raw` 的 `chat_completion(...)` 那行外包 `async with stream_exclusive():`（snapshot 路徑留 gate 外）③ `chat_persistence.py` `flush_buffer` 的 executor 寫入包進 `stream_exclusive()`（buffer_lock 已先釋放）；對稱設計＝兩端互等 ④ **B1 兜底**：`llm_http_client.py` `_apost_json` 收到 200 後檢查 `data["error"]["type"]=="network_error"` → 主動 raise `httpx.ConnectError` 命中退避重試（2 次、1s/2s），用盡後 `LlmConnectionError` → 分類從假性 `no_choices` 改回真實 `connection`。**驗證**：AST parse 四檔全綠；未跑 unittest（純鎖、既有測試不覆蓋此路徑）。

---

## askai 失敗時 backend 狀態快照（Phase D，多 backend 通用）（歸檔 2026-06-20，原 2026-05-04）

<!-- @meta
id: askai-backend-snapshot
type: FEATURE
status: confirmed
last_confirmed: 2026-05-04
-->

動機：/askai 偶發失敗（`no_choices` + raw body 是 Lemonade 寫的「Network error: CURL error」），重啟 Lemonade 即恢復，但壞掉當下沒 backend 內部狀態可定位。**修法**：① `llm_http_client.py` 新增 `async admin_get(path, timeout=2.0) -> dict` best-effort helper（任何錯誤吞掉、回 dict；命名去 backend 化以利複用）② `llm_service.py` 加 module-level `_BACKEND_PROBES` registry：lemonade=(`/api/v1/health`,`/api/v1/system-info`)、ollama=(`/api/ps`,`/api/tags`)、vllm=(`/health`,`/v1/models`) ③ 新增 `_snapshot_backend_state(...)`：依 `runtime.backend` 查 probes、並行 gather、寫 anomaly log（全包 try/except，絕不蓋掉原始 raise）④ `chat_raw` 三個失敗點都接（含原本完全沒寫 anomaly 的 timeout/connection 分支）。**測試**：`src/test/test_llm_snapshot.py` 9 unittest 全綠。**順手**：`docker-compose.yaml` discord-bot 加 `command:` 啟動前先跑 `python -m unittest test.test_llm_snapshot test.test_telegram_spoiler`，紅了短路不啟動、綠了 `exec python discord_bot.py`（pre-deploy gate）。

---

## askai log 觀測性補強（Phase A+B：trace_id 串接）（歸檔 2026-06-20，原 2026-04-29）

<!-- @meta
id: askai-log-traceability
type: FEATURE
status: confirmed
last_confirmed: 2026-04-29
-->

動機：「LLM 回應格式異常」失敗跨 `discord_bot.log` / `askai_prompt.txt` / `askai_response_history.jsonl` 沒共同 ID，且 no_choices 路徑沒寫 anomaly、raw response 沒留。**修法**：① `llm_commands.py` 入口生成 `trace_id = ask-{user_id 末4碼}-{epoch_ms}` ② `llm_service.py` `chat_raw`/`generate_reply` 加 `trace_id` 參數 ③ no_choices 路徑補 anomaly log ④ `generate_reply` 改回傳 `GenerateReplyResult` dataclass（`__iter__` 維持 tuple unpacking 相容）⑤ `error_kind` 分類 no_choices/empty_content/http_error/timeout/connection/unknown ⑥ 各 log + `askai_prompt*.txt` + `askai_response_history.jsonl` 都帶 trace_id / messages_sent / error_kind。

---

## Telegram Relay 文字 spoiler 還原成 Discord `||...||`（歸檔 2026-06-20，原 2026-04-29）

<!-- @meta
id: telegram-spoiler-relay
type: FIX
status: confirmed
last_confirmed: 2026-04-29
-->

回報：頻道「內鬼情報」用了 Telegram spoiler，relay 到 Discord 沒包 `||`。根因：scraper `handlers.py` 只存 `raw_text`、丟掉 `message.entities`，relay 也沒還原。**範圍**：使用者指示「只針對文字、圖片不處理」。**修法**：① `db.py` 加 `entities JSONB` 欄；`upsert_message_only` UPDATE 用 `COALESCE` 不覆寫，歷史訊息走 history fetch 自動回填 ② `handlers.py` `_serialize_entities()` 轉 `[{type,offset,length}]` ③ `telegram_relay_service.py` 新 module-level `apply_spoiler_entities(text, entities)`：filter `MessageEntitySpoiler`、用 UTF-16-LE bytes 切片正確處理 emoji surrogate、從後往前插 `||`、先 wrap 再 truncate 4000。**測試**：`src/test/test_telegram_spoiler.py` 14 unittest 全綠。已實機從 #7267 強制重發驗證 `||...||` 渲染正確。**未做（未來議題）**：媒體 spoiler（`handlers.py:178` 用 `media_unread` 應改 `media.spoiler`）、relay embed 第一張圖邊界、`MessageEdited` 未監聽、force_replay 用 `message_pk` 而非 `telegram_message_id` 比較會誤觸後補歷史訊息。

---

## LLM client 重構：拋 openai SDK，改自寫 httpx wire 薄殼（歸檔 2026-06-20，原 2026-04-28）

<!-- @meta
id: llm-client-httpx-rewrite
type: FEATURE
status: confirmed
last_confirmed: 2026-04-28
-->

Root cause：commit `763d251`（chat 切 OpenAI SDK）順手把 LlamaIndex embedding 包從 `-ollama` 換 `-openai`，後者 `OpenAIEmbedding.__init__` 對 model 名做 enum 白名單驗證，自訂 model 名直接拋 `ValueError`，`SafeLLMEmbedding` 一直 fallback BM25 沒被注意。**修法**：① 新增 `src/llm/llm_http_client.py`（httpx 薄殼 ~200 行；chat/embedding/list_models + 指數退避）② `safe_llm_embedding.py` 改 subclass `llama_index.core.embeddings.BaseEmbedding`（核心介面穩定）③ `llm_service.py` 拋 `AsyncOpenAI` 改用 `LlmHttpClient` ④ `LLMRuntimeConfig` 加 `backend`+`backends` profile，per-call Ollama-only knobs 只在 `backend=="ollama"` 時生效 ⑤ `llm_runtime_config.json` 遷移新 schema（三後端 profile 備好）。Commit C1 `8642806`=code、C2 `02a937c`=deps cleanup。**設計準則**：綁協定不綁 SDK。

---

## FB 貼文推送模式（歸檔 2026-06-20，原 2026-04-07 完成）

<!-- @meta
id: fb-push-notify
type: FEATURE
status: confirmed
last_confirmed: 2026-04-07
-->

**起因：** post id=399 DB 有 8 張圖但 bot 收到 API images 為空、Discord 貼文無圖。根因：輪詢模式時間差 + FB CDN URL token 過期 + 無刷新機制。**變更**：① `src/scraper/main.py` FB 抓完呼叫 `_notify_discord_bot("fb")` ② `src/services/notify_server.py` 新增 `"fb"` handler → `_process_fb` → `FBMonitor.check_and_send_fb_posts()` ③ `src/discord_bot.py` 移除 `_auto_start_fb_monitor` 輪詢（原每 600 秒）④ `fb_scraper_service.py` `_merge_fields_for_duplicate` 圖片合併改 `>=` 時更新（刷新 CDN token 不縮水）⑤ `database.py` `_update_fb_post` 圖片從「只新增」改「全量替換」。**流程**：scraper 抓 FB → 寫 DB（URL 最新鮮）→ POST /notify/fb → bot 拉資料 → 下載圖 → 發送。**注意**：舊貼文（不在 FB 首頁）不會被重抓、CDN URL 過期無法自動更新；`start_fb_monitoring()` 保留供手動指令。

---

## 活動公告 → 自動建立 Discord 伺服器活動（歸檔 2026-08-18，原 2026-07-01）

**歸檔佐證**：已上線運作 — `a9b5101` 起共 5 次 commit（含 `7c3ec8c` 關掉 dry-run、`2c58d51` 刪除活動時清 created_events、`ae47f49` 封面圖、`198d68a` 標題取章節名），`sent_articles.db` 的 `created_events` 已累積 **17 筆**自動建立的活動。

<!-- @meta
id: event-announce-auto-schedule
type: DECISION
status: confirmed
last_confirmed: 2026-07-01
depends_on: post_to_channel, notify_server, state_db, article_monitor, fb_monitor
affects: scraper/main.py, notify_server, article_monitor, fb_monitor, discord_bot
-->

**目標**：把官方公告（FB／Article）裡同時含「活動時間」+「伺服器時間」的限時活動，解析出時間區間後**全自動**建成 Discord 伺服器活動（Guild Scheduled Event）。

### 來源與觸發（定案）
- 來源＝我們自己轉發的 **FB + Article**，兩者都發進 `article_monitor_channel_id`（FB 走 `notify_server._process_fb`、Article 改推送後同址；[notify_server.py:154](src/services/notify_server.py#L154) 已寫死此 key）。
- **不走 on_message**：bot 自己的訊息被 [on_message:356](src/discord_bot.py#L356) 擋掉；且攔在轉發點拿得到原始 dict（全文＋真發布時間），比反推 embed 乾淨。
- 偵測**寄生在轉發動作尾巴**（`send_*_to_channel` 成功後呼叫），不自建排程、不輪詢、不監聽 gateway。

### 同時做的基礎改造：Article 改推送 + 共用模組（完整版，使用者選定）
1. **Article 改準即時推送**（對稱 FB）：
   - [scraper/main.py](src/scraper/main.py#L40) `main_scrape_task()` 成功後加 `_notify_discord_bot("article", {...})`（仿 fb [:73](src/scraper/main.py#L73)）。
   - [notify_server](src/services/notify_server.py#L32) 派發表加 `"article"` 來源。
   - [discord_bot.py](src/discord_bot.py#L549) 退役 `_auto_start_official_article_monitor` 輪詢 → **降為 30 分 fallback safety net**；FB 也補同一條 fallback（目前 FB 無保險絲，webhook 漏了就不發）。
2. **共用模組（完整版）**：
   - **觸發層**：notify_server 用宣告式 `_RELAY_SOURCES` 註冊表（source → {config_key, monitor_factory, method}）把 `fb / article / it_article` 收斂成單一 `_process_relay`；**巴哈維持自有 handler**（單篇/批次＋forum slot 是真特例）。配 `src/test/test_notify_relay.py` 守現役 FB/IT 推送。
   - **偵測層**：`event_scheduler` 為唯一活動偵測模組，FB/Article 發送尾巴各呼叫一次，匯流同一 parser+scheduler。

### 解析（純 regex，不上 LLM）—— 已對 articles.db 全 490 篇對抗審查（2026-07-01）
- 理由：官方公告格式高度固定、幻覺日期在「自動建行事曆」不可逆；LLM 僅留逃生門。
- **雙詞交集硬閘門**：stripped text 同時含「活動時間」AND（含「伺服器時間」OR「（UTC+8）」）。實測交集=219/490，能分辨真活動 vs 宣傳/售票/維護預告（使用者觀察「交集伺服器時間 通常是活動」獲驗證）。
- **錨點認「詞」不認「符號」**：`活動時間[✦*：:\s　]*`——✦ 等裝飾不穩定，刻意忽略，只認「活動時間」四字。實證不會誤抓「✦開放條件✦／※…期間／活動時間結束後」散文。**加 negative lookahead** 排除「結束/及時/期間/內」散文字，讓 n 計的是「活動時間標籤」而非「活動時間詞」。
- **DATE**：`(\d{4})[/年](\d{1,2})[/月](\d{1,2})日?\s*(\d{1,2})[:：](\d{2})`（日與時之間**可選空白**，相容 `YYYY/M/D HH:MM`）+ **缺年分支** `(\d{1,2})月(\d{1,2})日…`（年份用貼文 start_time 補；跨年 end<start 則 +1 年）。範圍符 `[~～\-－—至到]`。
- **逐錨點抽出所有 range**（不再「恰好一個才建」）：一篇可含多個「活動時間」活動（含版本內容說明匯總帖），全部抽出，靠**指紋去重**決定建不建（見下）。
- **缺時間成分預設（皆 UTC+8）**：有日期無時刻 → start 00:00、end 23:59；缺結束（永久開放）→ 跳過。
- **相對起點（「X版本更新後」）**：**不可壓貼文日**（預告型貼文發文遠早於上線，方向性錯，實測偏差約 4 天）。改用**版本日回填**：解析同版本「內容說明」帖的「更新維護時間：YYYY年M月D日HH:00」；解析不到 → SKIP（寧可漏不可錯）。
- **全自動「寧可漏不可錯」**：抓不到/不確定一律不建。

### 去重（跨來源活動指紋，v1 強制）—— 對抗審查確認的最關鍵修正
- **問題**：FB+Article 都進 `article_monitor_channel_id`，**同活動雙來源雙報**（實證：坎特蕾拉喚取同時在 Article #3736 與 FB #93，range 一致）；FB 內部亦重複（#7==#9 同 post_id、content_hash 不同）。純 article_id/fb_id 去重**無法擋跨來源雙建**。
- **指紋** = `(normalize(title), start_utc8, end_utc8)`。normalize 剝 `[括號]`/✦裝飾/全形空白；**必含 start/end**（「聲弦滌蕩」13 篇、「回音盈域」10 篇為**同名不同期**循環活動，純標題會錯誤合併）。時間正規化到整分避免 1 分鐘差漏命中。
- **建立前查指紋**：命中既有 `created_events` 即跳過。FB 去重改用 `post_id`（非自增 id）。
- **匯總帖補建**：版本內容說明帖**逐活動 parse + 指紋去重**——有獨立貼文的被指紋擋掉（不重複）、只在匯總帖的補建（不漏，實證「唯你的長夏永不凋落」5/22~8/1 等只活在匯總帖）。降噪可只補非贈禮/簽到的玩法活動。
- **冪等對照表** `created_events(event_fingerprint, discord_event_id, source_id)`：可冪等、可在偵測刪文/改期時撤銷/更新。
- **首次上線 dry-run**：先輸出待建清單給人工核一輪，再開全自動（使用者已同意「錯了沒差再改」，dry-run 為首批保險）。

### 時區 / Discord 限制（定案）
- 伺服器時區 **UTC+8 固定**（壓 00:00、轉 UTC 都用它；台港服無 DST，等同 fixed +8）。
- Discord 規定 scheduled event **start 必須在未來** → `start = max(now+5min, 解析start)`；即日起原始 00:00 寫進 description；clamp 後若 start≥end 則整則跳過。
- `entity_type=external`，`location=`**「鳴潮」**（使用者選 b；多遊戲對應後續再抽），`description=` 原文摘要＋跳轉連結（FB `url`／文章連結）。
- bot 為 **admin** → Manage Events 無虞。guild 活動上限 100。

### 程式落點
- `src/services/event_time_parser.py`：純函式 `text + post_time → list[ParsedEvent]`（一篇可多事件），無 discord/db/io 依賴、可單測。含 strip HTML、GATE、ANCHOR、DATE（缺年/空白）、相對起點標記。
- `src/services/event_scheduler.py`：副作用層。閘門（`channel == config.article_monitor_channel_id`，即時讀）→ parse → 版本日回填（查 articles.db 版本說明帖，建 `{version→update_dt}` 快取）→ **指紋去重**（查 `created_events`）→ clamp → `guild.create_scheduled_event` → 寫指紋對照。全程 best-effort 不拋。dry-run 模式只輸出清單。
- 去重儲存：沿用 [StateDB](src/services/state_db.py) 加 `created_events(event_fingerprint TEXT PK, discord_event_id, source, source_id, ts)`。
- `src/test/test_event_time_parser.py`：用 [articles.db](src/scraper/articles.db) 真實樣本 + [fb_posts.json](src/scraper/data/fb_posts.json) 當測資（順補記憶「CI 要記起來」，接 docker 啟動測試 gate）。
- hook：[article_monitor.send_article_to_channel](src/services/article_monitor.py#L275)／[fb_monitor.send_fb_post_to_channel](src/services/fb_monitor.py#L163) 尾巴各加 ~3 行（包 try/except，絕不拖垮轉發；仿 [ai_interactions_store](src/llm/ai_interactions_store.py) best-effort）。
- **不碰 [post_to_channel](src/utils/discord_content.py#L64)**：守 additive 邊界。

### 欄位對照（已查證）
- article：`article_title` / `article_content_full`→`article_content`→`article_desc` / `start_time`→`create_time` / `article_id`。
- fb：（無標題，從內文首行取）/ `text_md`→`text` / `timestamp`→`created_at` / `id` / `url`→`pfbid_url`。

### 實作範圍（使用者 2026-07-01 定：v1+v2 全覆蓋一起上、容錯後修）
- 全覆蓋 = 絕對起點 CREATE + 相對起點版本日回填 + 匯總帖逐活動補建 + **跨來源指紋去重（強制）** + 格式修補（空白/缺年）+ 首批 dry-run。
- **基礎改造同步做**：article 改推送（scraper notify + notify_server article 來源 + 輪詢退役/30 分 fallback）+ 共用模組 `_process_relay`（收斂 fb/article/it，**巴哈維持自有 handler，零風險已驗證**）+ `test_notify_relay`。

### 事故修正：活動名抓到卡池 4 星名（2026-07-29，已修）
- **現象**：Discord 冒出兩個怪活動「燈燈」「悖論噴流」（來源 article #5221 =【3.5版本】[角色/武器活動喚取・第二期]）。
- **根因**：`_clean_title_hint` 取「錨點前 90 字內**最後一個**括號名」。喚取帖緊貼「活動時間」上方那句正是 UP 池列舉句
  「活動期間，5星角色「愛彌斯」、4星角色「白芷」、「莫特斐」、「燈燈」喚取機率限時提升！」→ 取到最後一個 **4 星名**，
  而真正的活動名在再上一行的標題行（`[飛星自春天啟航]角色活動喚取`）。
- **連帶災情（比錯名更嚴重）**：`title_hint` 同時是**指紋核心**，故
  ① 同期多卡池共用同一批 4 星 → 指紋互撞，`plan_events` 本地去重把**真活動吃掉**（#4160/#4492/#4594/#4699 實測 4~6 個事件只剩 2 個）；
  ② Article 與 FB 抓到不同名 → 跨來源去重失效 → **重複建活動**（#5221 該檔期建出 3 個，其中 2 個名字是廢的）。
- **修法**（[event_time_parser.py](src/services/event_time_parser.py)）：
  1. **標題行優先**：錨點往回 150 字、最多 5 個非空行，取第一個「像章節標題」的行——長度 2~40、無 `。！？，、；`、
     不含時間/日期/獎勵/`數字:數字`/`*數量`/`~`，且**以括號開頭**或**以 活動|喚取|說明|公告|挑戰 結尾**。視窗切半的殘句丟棄。
  2. **括號 fallback 只留給匯總帖**（多錨點）；單一活動帖抓不到標題行 → 回 `""` → 退用**貼文標題**（article_title／FB 首行），
     這正是 Article↔FB 兩邊都拿得到的同一個字串 → 跨來源指紋才對得上。
  3. 括號 fallback 另**跳過 UP 池列舉句**（`喚取機率|N星角色|N星武器`）與 `※`/`-` 說明條列。
- **驗證**：articles.db 全 510 篇 + fb_posts.json 全 709 篇重跑；匯總帖活動名由「4 星名」變回真名
  （`[非定義光譜]角色活動喚取`／`「溢彩熒輝」武器活動喚取`…），FB 側幾乎全部收斂成貼文首行；
  規則 3 全庫只動到 #4920 一篇（無標題行的純列舉帖 → 收斂成單一總表活動，且指紋與 FB 總表貼文對上）。

### 總表貼文處理（2026-07-29 使用者定案：「收斂成一則 + 總表在後 → 跳過」）
- **問題**：修好命名後，同一檔期各卡池各建一個（4 個），FB 另有一則整期總表貼文
  「【3.5版本】[角色/武器活動喚取・第二期]」→ 再多建第 5 個重複活動。
- **判定**：`is_umbrella_title()`（`N.N版本…角色…武器…喚取` 或 `角色/武器…喚取`）。
  全庫命中 6 篇 article + 7 篇 FB，單卡池公告（`[飛星自春天啟航]角色活動喚取`、`[週年角色活動喚取・第二期]`…）零誤判。
- **規則 A｜總表不拆各卡池**（`plan_events`）：總表帖一律用**貼文標題**當活動名與指紋基準，不用逐卡池標題行。
  #5221 內文有兩個卡池標題行，仍收斂成 1 則；同期卡池區間相同，本地指紋去重自然併掉。
  **不會漏不同檔期**——指紋含 start/end，區間不同就是不同活動（全庫 6 篇總表檢核：相異檔期數 ≤1，收斂後皆為 1 則）。
  這也讓 article 總表與 FB 總表**指紋一致**（`3.5版本角色武器活動喚取第二期|…`），跨來源去重擋得住。
- **規則 B（曾實作，2026-07-30 撤除）**：原本加了「同區間已有活動 → 跳過總表」（`StateDB.has_event_in_window`）。
  **前提是錯的，已連同該 DB method 一併移除。**
  - 錯在哪：當初以為「總表＝各卡池獨立公告的重複」。查證 3.2~3.5 全部檔期後推翻——官方實際做法是
    **一部分卡池發獨立公告、其餘包進總表**，兩者**互補而非重複**：
    3.5 第二期 → 總表 #5221 只寫「飛星自春天啟航／永遠的啟明星」，另外 #5226「斟雨祝荷風」、#5235「棲霞飲露」各自發文；
    3.3 第二期 → 總表 #4699 + 獨立 #4711/#4719；3.2、3.4 則整期只有總表。
  - 後果：規則 B 會因為 #5226/#5235 佔住同一區間，把 #5221 整篇跳掉 → **只存在總表裡的兩個卡池完全沒有活動**。
    使用者實測：刪掉舊活動後重送 #5221，log 出現「跳過總表公告（同區間已有活動）」，活動建不出來。
  - 為何不需要它：規則 A 已讓 article 總表與 FB 總表**指紋相同**，既有 `is_event_created` 就擋得住那唯一的真重複。
- **實測（#5221 重送，撤除規則 B 後）**：parse 2 個區間 → 收斂 1 則「【3.5版本】[角色/武器活動喚取・第二期]」→
  指紋不存在 → **建立**；#5226/#5235 重送 → 指紋已存在 → SKIP。該檔期共 3 個活動，無重複、無遺漏。
- **教訓**：活動去重只走**指紋**（含 start/end）。「同區間」不等於「同活動」——同一版本檔期本來就會有多個不同活動。

### 活動描述連結改指 Discord 訊息（2026-07-29）
- 描述末行由「原公告：官方原文 URL」改為「**公告出處：該則轉發訊息的 Discord jump link**」，點了直接跳到伺服器內的公告訊息，好追活動來自哪篇。
- 串接：`article_monitor` / `fb_monitor` 早已有 `sent_message`（`post_to_channel` 回傳值，論壇頻道則為 thread 首則）→
  以 `getattr(sent_message, "jump_url", None)` 傳給 `schedule_from_article/fb(message_url=...)` →
  `maybe_schedule_events(message_url=...)` → `url=(message_url or url)`。
- **退路**：拿不到訊息（發送失敗/舊呼叫端）時自動退回官方原文連結，描述不會變空。

### 來源標題取法差異（使用者提醒，2026-07-29 查證）
- article 用 DB 欄位 `article_title`；**FB 無標題欄位，取內文首行**——兩者機制本就不同。
- 查證：有連結可配對的 75 組，normalize 後 68 組相同、7 組不同；不同的都是**首行為情境文/問候語**的貼文
  （典藏車型、特別訂製、XBOX、短影片徵集…），這些**都過不了「活動時間＋伺服器時間」雙詞閘門**，不進活動路徑。
- 對「會建出活動」的 66 篇 FB 貼文逐篇檢查首行：**0 篇是情境文**（活動公告一律首行即標題）。
- 結論：現行取法對活動路徑安全；若日後 FB 改版把情境文放首行，需另做 FB 專屬標題擷取。

### 待辦 / 未決
- 多遊戲 `location` 對應（目前固定「鳴潮」）後續再抽。
- 既有 `created_events` 14 筆是**舊指紋**；同一篇公告若被重掃會以新指紋再建一次（article_monitor 只處理新文，實務風險低）。
- 公告事後改時間/刪文 → 用 `created_events` 對照表撤銷/更新（進階，可後補）。
- 版本日回填依賴版本說明帖有「更新維護時間」欄；v1.1 #995 缺此欄 → 該版相對起點活動 fallback SKIP。
- FB `content_hash` 對同 post_id 產生兩值（#7/#9）成因未明 → 指紋總閘可兜底，來源層待查。

---

## Telegram Premium 自訂表情 → Discord App Emoji（歸檔 2026-08-18，原 2026-07-25）

**歸檔佐證**：已上線運作 — `cfc99bc` 已 commit，`telegram_custom_emoji` 有 **10 筆**取得 `discord_emoji_id`（即實際上傳成 Discord App Emoji）。Phase 2（動態 tgs/webm → GIF）未做，如日後要續作再開新區塊。

<!-- @meta
id: telegram-custom-emoji-relay
type: DECISION
status: confirmed
depends_on: [telegram-relay]
affects: telegram_scraper/handlers.py, telegram_scraper/db.py, services/telegram_relay_service.py
last_confirmed: 2026-07-25
-->

**目標**：把 Telegram Premium 自訂表情（內嵌在文字裡的角色貼圖）relay 到 Discord 時還原成實際圖案，而非只剩 fallback 一般 emoji。

### 問題與根因（已對 msg #9676 實證，2026-07-25）
- 症狀：TG `MessageEntityCustomEmoji` 內嵌文字，每個佔一個 fallback unicode emoji 位置；relay 只保留 fallback → 使用者看到「看不懂的一般 emoji」。
- 實證：msg #9676「3.6主线登场角色↓」9 個角色自訂表情 → Discord 顯示成 `🐦‍🔥🐦🤔🐉💫🌫🥛😭🦊`（鳴潮 3.6 角色貼圖）。
- 根因：scraper [_serialize_entities](src/telegram_scraper/handlers.py#L182) 只存 `{type, offset, length}`，**`document_id` 被丟棄**（DB 查證：#9676 的 9 筆 CustomEmoji 皆無 document_id）；relay [apply_spoiler_entities](src/services/telegram_relay_service.py#L32) 只處理 spoiler，CustomEmoji 被無視。

### 定案（2026-07-25，使用者確認）
- 寄存模式 = **Discord App Emoji**（application 私有 emoji）：bot 專屬池上限 2000、**不佔伺服器 50 格**、**成員 emoji 選單隱形**、跨伺服器共用、程式自動建立/刪除、語法同 `<:name:id>`。
- **Phase 1 只做靜態**（webp → PNG）。動態 tgs / video webm → **不做**，維持 fallback emoji（不變差）。

### 三段改造
1. **Scraper**（[handlers.py](src/telegram_scraper/handlers.py) / [db.py](src/telegram_scraper/db.py)）：
   - `_serialize_entities` 對 `MessageEntityCustomEmoji` 多存 `document_id`。
   - 用 `GetCustomEmojiDocumentsRequest(document_id=[...])` 取 document → 下載表情檔到共用 media 目錄（重用現有跨容器穩定檔名機制）；靜態 mime = `image/webp`。
2. **對照表**（telegram_data DB，新表）：
   `telegram_custom_emoji_map(document_id BIGINT PK, discord_emoji_id BIGINT, discord_emoji_name TEXT, animated BOOL, status TEXT, file_rel_path TEXT, created_at, last_used_at)`；status = ok / failed / unsupported（動態）。
3. **Relay**（[telegram_relay_service.py](src/services/telegram_relay_service.py)）：
   - 新 `apply_custom_emoji_entities(text, entities)`：查表命中 → UTF-16 range 換 `<:name:id>`；未命中 → lazy 轉檔（webp→PNG，Pillow）+ `bot.create_application_emoji(name=f"tg_{document_id}", image=...)` → 寫對照表 → 換。動態/轉檔失敗 → 保留 fallback（best-effort，絕不拖垮發文）。
   - **與 spoiler 合併成同一次「由後往前」UTF-16 rewrite**，避免兩種 entity 並存時 offset 位移。
   - 命名 `tg_{document_id}`（deterministic、可反查）；custom emoji 在 embed description 內可正常 render（relay 用 embed 發文）。

### 測試入口 / 重抓 / 多頻道定位（2026-07-25 定案）
- **測試入口**：用既有 admin 指令 [`/resend_article`](src/commands/article_commands.py#L520) 加 `type: telegram` 分支（不新開指令）。
- **on-demand 重抓**：resend 讀 DB 不會自己抓 Telegram；改由 resend → `pg_notify('telegram_emoji_refetch', {chat_id,msg_id})` → scraper 用「既有常駐 client」抓該則、下載表情、回填 entities → resend poll DB 至就緒（~15s）→ 渲染+送。scraper 新增一個 pg LISTEN 任務（runner.py）。**不可雙開 session**（discord-bot 雖掛 ./src 看得到 session，但另開 client 會 SQLite 鎖衝突）。
- **多頻道定位**：premium emoji 是**全域 document_id**、不屬於頻道 → emoji 表維持全域 key（跨頻道自動共用去重）。真正要處理的是**訊息定位**：`telegram_message_id`（footer 的 #9676）每頻道各自編號、非全域唯一。
  - **對外**：footer 加 **DB id**（全域唯一，resend 用它）；footer = **A 方案**「`msg #9676 · db#12345`」（頻道名維持在 embed 標題、不進 footer）。
  - **對內**：resend 用 db id 查出 `(chat_id, telegram_message_id)`，重抓帶 chat_id，scraper `get_messages(chat_id, ids=...)` 抓對頻道。
- **replay 不動**：[`telegram_replay_from_message_id`](src/config.json#L14) 維持 telegram_message_id per-來源（已無歧義、且比 db id 耐清庫重掃）。
- **現況**：scraper 單頻道（source_channel=Seele_WW_leak）、relay 已 route 架構；今天不撞號，此設計讓未來加頻道零改動。

### 環境利多（已查證）
- discord.py **2.6.4**（[requirements.txt:1](docker/discord_bot/requirements.txt#L1)）支援 App Emoji API。
- relay 容器已有 **ffmpeg**（[dockerfile:6](docker/discord_bot/dockerfile#L6)）+ **Pillow**（[telegram_relay_service.py:887](src/services/telegram_relay_service.py#L887)）→ Phase 1 靜態零新依賴。

### 實作狀態（2026-07-25 已完成，待部署驗證）
**改動檔案：**
- [handlers.py](src/telegram_scraper/handlers.py)：`_serialize_entities` 補 `document_id`；新增 `_download_custom_emojis`（GetCustomEmojiDocumentsRequest→下載→寫表→回填 entities，History 掃描跳過）；`_process_message` 掛呼叫；新增 `handle_refetch_message`。
- [db.py](src/telegram_scraper/db.py)：`init_db` 建 `telegram_custom_emoji` 表；`get_known_emoji_ids` / `upsert_custom_emoji` / `update_message_entities`。
- [runner.py](src/telegram_scraper/runner.py)：新增 `EMOJI_REFETCH_CHANNEL="telegram_emoji_refetch"` pg LISTEN + `_handle_refetch_request`（用常駐 client `get_messages(chat_id, ids=)`）。**LISTEN 設在歷史掃描之前**（掃描可能很久，期間也要能收重抓通知）；重抓 task 用 set 持參照防 GC。**不需要歷史掃描做表情**（History 已 gate 掉）：新訊息即時抓、舊訊息靠 resend on-demand。
- [telegram_relay_service.py](src/services/telegram_relay_service.py)：`apply_message_entities`（spoiler+emoji 合併 UTF-16 改寫；舊 `apply_spoiler_entities` 已移除、無 production 呼叫者，測試改用之）；`CustomEmojiResolver`（webp→PNG Pillow→`create_application_emoji`→回填，名 `tg_{doc_id}`）；repo 加 `get/mark_custom_emoji_*`/`find_messages_by_id`/`send_pg_notify` + `ensure_relay_tables` 建表；worker `_resolve_custom_emojis`/`_wait_emoji_ready`/`resend_telegram_by_id`；`_process_one` 渲染前解析 emoji；footer 加 `db#{message_pk}`。
- [article_commands.py](src/commands/article_commands.py)：`/resend_article` 加 `type:telegram` + `_handle_resend_telegram`。
- [test_telegram_custom_emoji.py](src/test/test_telegram_custom_emoji.py)：9 個新測試（+ 既有 spoiler 14 測試仍過，全套 98 綠）。

**部署測試步驟：**
1. 使用者重啟 `telegram-scraper`（載入 LISTEN + 下載邏輯）+ `discord-bot`（載入 resolver/resend）。
2. Discord admin 打 `/resend_article id:9676 type:telegram` → 應在 relay 頻道重送 #9676，9 個角色表情顯示為實際圖案。
3. 觀察：scraper log `[Refetch] 完成`、`自訂表情已下載`；relay 回報「找到 9、轉出 N」。

### 待辦 / 未決
- **歷史訊息回填**：document_id 從未存 → #9676 等舊訊息無法從 DB 回填，需重掃（Telethon 重抓 entities）才有；新訊息修好 scraper 後自動帶。**決策：不做批次回填，改 on-demand（`/resend_article type:telegram` 觸發單則重抓）**。
- 2000 池策略：v1 不淘汰、逼近上限只 log；之後加 LRU（`last_used_at` + `delete_application_emoji`）。
- Discord emoji 建立有 rate limit：新表情包首次大量 lazy 上傳要退避重試。
- 名稱限制：Discord emoji name 2–32 字 `[A-Za-z0-9_]`，`tg_{document_id}` 需確認位數不超（document_id < 29 位）。
- Phase 2（未來）：動態 tgs→GIF（裝 rlottie/python-lottie）+ webm→GIF，順帶修「獨立動態貼圖變 .tgs 附件」。

---

## Telegram 多頻道來源 + 轉發去重（歸檔 2026-08-18，原 2026-07-27）

**歸檔佐證**：已上線運作 — `d0e0880` 已 commit，DB 內 Gamedataleak（`-1002974889459`）已累積 **205 筆**訊息。原「待決」的 `telegram_channel_routes` 補明確 chat_id route 仍未做，屬可選優化。

**需求**：新增 Gamedataleak（<https://t.me/Gamedataleak>）為主頻；避免兩個同性質頻道互轉造成重複（A 轉發 B、但 B 也是主頻時，A 的轉發無意義）。

**已確認決策（2026-07-27）**：
1. 加主頻方式＝**同容器多頻道**（`source_channel`→`source_channels` list，一個 session 同時監聽 Seele + Gamedataleak）。
2. Discord 路由＝Gamedataleak **發到 Seele 同一個頻道**（`1276423699851116544`）。
3. 去重＝**通用自動規則**：任何轉發若其原始來源本身也是我們的主頻，就在 scrape 階段丟掉；此排除**優先於** `forward_whitelist`（被排除者不進白名單、不 auto-add）。自我維護、雙向去重。

**關鍵事實（已查證）**：
- `telegram_messages` **不存轉發來源**（[db.py:87](src/telegram_scraper/db.py#L87)）→ 去重只能在 scrape 階段（[handlers._process_message](src/telegram_scraper/handlers.py#L318)，`fwd_from` 還在）。
- Seele chat_id = **-1002405953050**（DB 另有 `2057132858` 為早期殘留）。
- 帳號必須先加入 Gamedataleak 才收得到訊息、`get_entity` 才解析得到 username。

**實作落點（已完成）**：
- [tg_config.py](src/telegram_scraper/tg_config.py)：`TelegramConfig` 加 `source_channels: list[str]`；`load_config_from_env` 讀 runtime `source_channels`，缺則 fallback `[source_channel]`；`source_channel`＝清單 first（refetch + relay 端 `_get_source_channel_name` / route name-fallback BC）。
- [runner.py](src/telegram_scraper/runner.py)：`listen_channels = source_channels or [source_channel]`；`NewMessage(chats=listen_channels)`；歷史掃描 **for each channel** 各自 collect→reverse→insert（維持每頻道 PK 時序）。
- [filters.py](src/telegram_scraper/filters.py)：抽出 `_build_forward_source_candidates`（白名單與去重共用）；新增 `is_forward_source_a_primary(client, message, primary_sources)`。
- [handlers.py](src/telegram_scraper/handlers.py)：`_process_message` 在 `should_skip_forward` 前先擋，若 `is_forward` 且來源 ∈ 主頻集合 → 略過（log「略過主頻轉發（去重）」）。**不排除當前頻道**，保雙向去重。
- [runtime_config.json](src/telegram_scraper/runtime_config.json)：已加 `source_channels=["Seele_WW_leak","Gamedataleak"]`。
- [config.json](src/config.json)：**未改**。同頻道靠現有 name-fallback（未匹配 chat_id → seele route）自動導到同一 Discord 頻道；待取得 Gamedataleak chat_id 後可補明確 chat_id route。

**已驗證（本機純邏輯）**：config 解析出 `['Seele_WW_leak','Gamedataleak']`；去重函式對「Seele 轉 Gamedataleak / from_name 命中 / 非轉發 / 非主頻保留 / 白名單回歸」6 案全過。py_compile + JSON 均綠。

**部署步驟**：
1. 確認登入的 Telegram 帳號**已加入 Gamedataleak**（否則收不到、`get_entity` 解析不到 username → 去重失準）。使用者 2026-07-27 已確認加入。
2. 重啟 `telegram-scraper`（載入多頻道監聽 + 去重）。首次會回填 Gamedataleak 近 `history_hours`(=168=7 天) 歷史 → relay 灌進同一頻道（可能爆量，維持 7 天不限縮）。
3. 觀察 scraper log：`開始抓取來源頻道: Seele_WW_leak, Gamedataleak`、`Gamedataleak 歷史訊息抓取完成`；跨轉發出現時應有 `略過主頻轉發（去重）`。

**待決 / 後續**：
- 取得 Gamedataleak chat_id 後，在 `telegram_channel_routes` 補明確 chat_id route（去除對 name-fallback 的依賴）。
- 去重目前以 username 比對為主；若某來源 `get_entity` 常失敗，可再把各主頻 chat_id 也納入 primary set 強化。

---

## handoff 盤點紀錄歸檔（歸檔 2026-08-18）

> 從 AI_HANDOFF_AND_TODO.md 搬來的已完成盤點條目（2026-06-25 ~ 2026-07-25），皆已 commit 並上線。

- 2026-07-25（Telegram Premium 自訂表情 → Discord App Emoji，**已實作，待部署驗證**）：症狀＝TG premium custom emoji 內嵌文字，relay 只留 fallback 一般 emoji。**實證 msg #9676**「3.6主线登场角色↓」9 個角色貼圖在 Discord 只剩 `🐦‍🔥🐦🤔🐉💫🌫🥛😭🦊`。**根因（DB 查證）**：scraper [_serialize_entities](src/telegram_scraper/handlers.py#L182) 只存 `{type,offset,length}`，**`document_id` 被丟**（#9676 的 9 筆 CustomEmoji 皆無 document_id）→ relay 無從還原。**定案**：寄存用 **Discord App Emoji**（bot 私有池 2000、不佔伺服器 50 格、成員隱形、跨伺服器）；**Phase 1 只做靜態 webp→PNG，動態 tgs/GIF 不做**。完整規劃見 [Telegram 自訂表情 relay 區塊](#telegram-premium-自訂表情--discord-app-emoji規劃定案)。**已實作（py_compile + 98 測試全過）**：scraper 補 document_id + 下載（gate 掉 History）+ runner LISTEN 重抓；db 新表 `telegram_custom_emoji`；relay `apply_message_entities`（spoiler+emoji 合併）+ `CustomEmojiResolver`（上傳 App Emoji）+ footer 加 `db#id`；`/resend_article` 加 `type:telegram`（notify 重抓→poll→渲染→送）。**下一步**：使用者重啟 discord-bot + telegram-scraper，`/resend_article id:9676 type:telegram` 實測。
- 2026-07-03（他人印象被審核擋下 → 一鍵重填**已實作**，存檔即生效免重啟）：**現象排查**＝使用者填「對他人印象」後「什麼都沒跑出來」。查 [discord_bot.log](logs/discord_bot.log)：14:39:46 開 modal → 14:44:30 `intro_impression_moderation_blocked decision=reject reason=請勿使用迷因/定型文灌水 score_meme_spam=1.0 score_fake_story=1.0`，即**送出成功但被審核 reject**（[impression_moderation_service.py:186](src/services/impression_moderation_service.py#L186) meme_spam>0.6 硬擋）；被擋只回一則通用 ephemeral 警告（易被忽略、且不顯示真原因），原文全丟需重打。**需求**＝被擋時可重新複製/帶入表單（使用者反映判斷標準偏高）。**改法（僅改 code，未動門檻）**：[management_commands.py](src/commands/management_commands.py) ①`IntroImpressionModal.__init__` 加 `prefill_target/alias/habit/impression` kwargs → `UserSelect(default_values=[...])`(2.4+) + `TextInput(default=...)` 帶入上次全部欄位（含對象）；②新增 `ImpressionRetryView`（非持久化，timeout=600，一顆「✏️ 重新填寫（帶入剛剛內容）」按鈕，callback `send_modal` 帶 prefill）；③被擋分支改回覆＝顯示**實際 `moderation.reason`** + 原文（```code block``` 可複製）+ 掛 retry_view。py_compile PASS、discord.py>=2.6.4 支援全部用到的 API。**未 commit**。**下一步**：docker 重啟後實測「填梗被擋 → 看到原因+原文+按鈕 → 點按鈕帶入內容改寫再送」。**選配（未拍板）**：若仍覺門檻高，可再放寬 [impression_moderation_service.py](src/services/impression_moderation_service.py) 的 `score_meme_spam>0.6` / `score_fake_story>0.6` / `score_real_interaction<0.4` 閾值，或對特定情境放行。
- 2026-07-02（插話/askai 反附和 — prompt 微調**已實作**，存檔即生效免重啟）：使用者觀察「模型都在附和目前對話、不獨立思考」。**診斷（修正前一輪誤判）**：撈 `ai_interactions` 近兩則，其一觸發「英格蘭又讓人失望」+ 貼比分圖 → 回「這比分…徹底翻不了身」。原疑幻覺，**查 code 證實插話路徑會把圖 base64 送 vision 模型**（[ambient_reply.py:582/899-982](src/llm/ambient_reply.py#L899-L982) → [llm_service.py:62-83](src/services/llm_service.py#L62-L83) 轉 `image_url`），所以它**讀對了 0:1**、卻在「才 50 分鐘」時跟著把對方悲觀加碼 → **問題是反射性附和（模型 sycophancy 預設 + prompt 結構偏共鳴/留白強化），不是幻覺、也不是溫度**。**決策**：①**不動溫度**（`default_temperature=0.85`）——溫度管隨機/創意不管附和傾向，純聊天搞笑陪伴 bot 調低只會更平更像 yes-man；②**動 prompt 但窄**：把「有主見」當成人設本就有（機智/帶刺/見過世面不大驚小怪）卻被壓住的特質解放，條件觸發+點到為止。**改檔（僅 .txt，非資料檔）**：[persona_guardrails.txt](src/settings/prompts/persona_guardrails.txt) 於【不冒認】後新增【有自己的看法（不反射性附和）】4 點（對方 overshoot/與眼前事實對不上才淡淡唱反調、認真低潮不適用）；[persona_examples.txt](src/settings/prompts/persona_examples.txt) 新增範例 14（比分圖唱衰情境 ✗跟著加碼/✗說教/✓帶刺不說教）。兩檔 ambient([ambient_reply.py:105-109](src/llm/ambient_reply.py#L105-L109) identity→guardrails→ambient→examples) 與 /askai([llm_commands.py:105](src/commands/llm_commands.py#L105)) 皆載入；`./src` bind-mount + mtime 快取 → 免重啟。**未 commit**。**下一步**：觀察插話是否在情緒 overshoot 時淡淡點破而非附和、且不誤報/不說教/不變話癆。**選配**：baseline vs 新規則 A/B 實測（碰 Lemonade，挑閒時；使用者未拍板）。**能力備註**：此模型（ambient=Qwen3.6-35B-A3B Q4、askai=gemma-4-26B Q4、開 enable_thinking）感知 OK，「輕輕唱反調」在能力內；「跨多則偵測邏輯矛盾」的硬推理仍是天花板，別期待穩定。
- 2026-07-01（活動公告自動建活動 — 全覆蓋版**已實作**，待 docker 驗證）：需求＝官方公告（FB+Article，皆進 `article_monitor_channel_id`）含「活動時間」+「伺服器時間」交集 → regex 解析時間 → **全自動**建 Discord 伺服器活動。**先用 articles.db 全 490 篇跑 4 視角對抗審查**（workflow），抓到並修掉 4 個真缺陷：①跨來源（Article↔FB 同活動雙報，如坎特蕾拉 #3736+FB #93）→ **指紋去重(normalize(title)+start+end)** 為 v1 強制；②相對起點「X版本更新後」不可壓貼文日（方向錯）→ **版本日回填**（查版本內容說明帖「更新維護時間」，解不到 SKIP）；③版本內容說明匯總帖整篇丟棄會漏建「只在匯總帖」的活動 → **逐活動 parse + 指紋去重補建**；④缺年/空白格式 → DATE 補容錯。**新檔**：[event_time_parser.py](src/services/event_time_parser.py)(純函式、strip HTML、雙詞閘門、錨點認詞不認✦、缺年/即日起/版本相對起點)、[event_scheduler.py](src/services/event_scheduler.py)(閘門=channel==config、版本日回填、指紋去重、clamp start 未來、create_scheduled_event external/location=「鳴潮」、**首批預設 dry-run**)、[test_event_time_parser.py](src/test/test_event_time_parser.py)(20 測試)、[test_notify_relay.py](src/test/test_notify_relay.py)。**改檔**：[state_db.py](src/services/state_db.py) 加 `created_events` 指紋表；[article_monitor.py](src/services/article_monitor.py)/[fb_monitor.py](src/services/fb_monitor.py) send 尾巴各掛 hook(best-effort)；[notify_server.py](src/services/notify_server.py) 共用 `_process_relay`+`_RELAY_SOURCES`(收斂 fb/article/it，**巴哈維持自有 handler**)+新增 article 來源；[scraper/main.py](src/scraper/main.py) 加 `_notify_discord_bot("article")`(改推送)；[discord_bot.py](src/discord_bot.py) article 輪詢 180s→1800s fallback；docker-compose 啟動 gate 加兩測試。**驗證**：20 parser 測試 PASS、全檔 py_compile PASS、dry-run（article 239 + FB 41 = 280 唯一活動、跨來源指紋擋掉 105 重複、6+ 相對起點版本日解不到 SKIP）。**未 commit**。**下一步**：①docker 重啟（套 notify_server/monitor/scraper 改動 + 跑啟動 gate）②看 `[event][dry-run]` log 確認待建清單合理 ③滿意後在 config.json 設 `"event_schedule_dry_run": false` 開全自動。**殘留風險（已記文件）**：跨來源指紋對「同名不同期循環活動」靠 start/end 精確；版本日回填依賴版本說明帖有「更新維護時間」欄。
- 2026-06-25（插話除錯）：**修「B 回覆 A 再 @ 機器人問意見 → 看不到 A 寫什麼就亂答」**。根因：Discord 原生 reply 的 `message.reference` 全程只被 [_is_directed](src/llm/ambient_reply.py) 拿來判「是不是回覆機器人」，**被回覆訊息的內容從未進 prompt**；模型只拿到 `<latest_user_message>`(B 的字) + `<chat_history>`(B 之前 20 則, `history_limit=20`)。A 那句要嘛已滾出視窗、要嘛在視窗內但**沒有連結標記**告訴模型「B 的問句是衝著這行來的」→「他/這個/這樣」無指涉 → 腦補亂答。**修法**（本輪定案：範圍 b 含自發、帶圖、不去重、不碰 /askai）：①[ambient_reply.py](src/llm/ambient_reply.py) 新增 `_resolve_replied_to()`（reference.resolved 三態 Message/Deleted/None；None 時 `fetch_message` 補抓一次，best-effort）；directed 與自發插話都在 `generate_reply` 前算 `replied_to_from/_text`，並把被回覆訊息的圖也併進 vision payload（trigger 自己的圖優先、整體受 `image_max_count=1`）。②[llm_service.py](src/services/llm_service.py) `_build_prompt_bundle`/`generate_reply` 加 `replied_to_from/replied_to_text` 兩參數，在 `<latest_user_message>` **正上方**輸出 `<reply_to from="A#XXXX">…</reply_to>` + 一行指引（把「他/這個/這樣」對準 reply_to，別跟 chat_history 其他話題搞混）。③debug 摘要加 `reply_to=` 計數。py_compile PASS、callers 全 kwargs 不受影響、**未 commit**。**下一步**：docker 重啟 → 實測「B reply A → @機器人問意見」「reply 帶圖」兩情境，看 `ambient_prompt.txt` 有 `<reply_to>` 區塊且回答對準 A。**未做（可選）**：/askai 同缺口（本輪不碰）。


---

## Persona Extraction Agent 影子模式規劃 M1~M6（歸檔 2026-09-28，原 2026-08-18）

> **歸檔原因**：已被 M7（精簡版發布，2026-09-28 上線）取代；現況見 `AI_HANDOFF_AND_TODO.md` 的「Persona Agent M7」區塊。
> 以下為原文，只拿掉開頭指向已刪除 HANDOFF 檔的過時說明，`status` 改成 deprecated。

### 原盤點紀錄

- 2026-08-18（人格萃取 Agent 影子模式，**規劃定案・未開工**；本輪只做查證與線上實測，未動任何 code／設定檔）：把每日 04:00 的固定人格萃取升級成 tool-calling agent，產出**可稽核的 diff** 而非整份覆蓋；影子模式並行、寫獨立表、**不動 production**。**線上實測（Lemonade 11.5.0 + Qwen3.8-27B-UD-Q4_K_XL / llamacpp b9747）**：tool calling ✅（`finish_reason=tool_calls`，4.4s / 33 tok/s）、`role:"tool"` 回合往返 ✅、`response_format: json_schema` strict ✅ → **不需自架 llama-server、不需 `--jinja`，M0 直接跳過**。**併發**：1 發 33 tok/s、2 發各 11~12、3 發各 7 → llama-server 多 slot 真並行但**總吞吐固定被平分**（故獨立進程方案會讓 askai 慢 3 倍）。**prompt cache**：冷 3417 tok/10.1s → 熱 18 tok/0.3s，且插入不同前綴後仍命中（多組 cache 並存）；插話 prompt 78%（10,823 字元）是靜態前綴，現有組裝順序已是最優。**資料面**：chat 表 273,780 筆 / 81 人 / `message_id` **100% 覆蓋**（evidence 機制成立）；訊息平均僅 11~38 字；14 天符合門檻 46 人、337,211 字。**五項定案**：①`personality_model` 統一改 27B（`max_models.llm=1` 會互踢）②04:00 觸發、production→agent **序列接力**（約 05:10 收工）③agent 跑在 bot process 內共用 `stream_exclusive`、**不可做成獨立腳本**、每 step 主動禮讓 ④**補第四支工具 `get_conversation`**（人格訊號在互動不在句子，不補會輸給現有 pipeline）+ context 改 token 預算 ⑤thinking 分兩段（收集關、產 diff 開，12 分/人 → 3 分/人）。**M1 第一項＝補 code 缺口**：`think` 覆寫管線完整存在，唯一斷點在 [_build_chat_extra_body](src/services/llm_service.py#L573-L588) 的 lemonade 分支把它丟掉。詳見 [Persona Agent 區塊](#persona-extraction-agent-影子模式規劃-m1m6歸檔-2026-09-28原-2026-08-18)。

<!-- @meta
id: persona-extraction-agent
type: DECISION
status: deprecated
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

## Telegram 媒體 spoiler（防雷）未帶到 Discord（歸檔 2026-09-28，原 2026-08-18）

> **歸檔原因**：已上線（commit `77c812d`）。2026-09-28 查 DB：`telegram_message_media` 3,576 筆中有 100 筆 `is_spoiler=true`，
> 旗標已正確寫入。原文「未 commit」是當時的狀態。

### 原盤點紀錄

- 2026-08-18（Telegram 媒體 spoiler 未帶到 Discord，**已實作，待部署驗證**）：症狀＝TG 影片有防雷、Discord 沒打碼。**relay 端無辜**（`AttachmentSpec.is_spoiler` → `discord.File(spoiler=)` → discord.py 自動加 `SPOILER_` 前綴，圖片也已有「spoiler 首圖不進 embed」分支）；**DB `telegram_message_media` 2696 筆 `is_spoiler` 全 false**。**根因**＝[`_build_media_item`](src/telegram_scraper/handlers.py#L140) 讀 `message.media_unread`（語意是「媒體未檢視」，語音/圓形影片用），真正旗標在 media 物件上的 `MessageMediaPhoto/Document.spoiler`。**修法**：①改讀 `getattr(media, "spoiler", False)`；②`db.update_media_spoiler()`（`IS DISTINCT FROM` 過濾空寫）；③「媒體已存在略過下載」分支補呼叫回填——**沒這段舊資料永遠錯**，`/resend_article` 舊影片仍不打碼。**驗證**：scraper 5 案全過、`discord.File(spoiler=True)` 實測輸出 `SPOILER_clip.mp4`、回填 SQL 以 BEGIN/ROLLBACK 實測（值變 UPDATE 1、值同 UPDATE 0、回滾後 2696 筆未動）。**未 commit**。**下一步**：重啟 telegram-scraper，歷史掃描會校正近 7 天旗標。詳見 [Telegram 媒體 spoiler 區塊](#telegram-媒體-spoiler防雷未帶到-discord歸檔-2026-09-28原-2026-08-18)。

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

## 過時待辦清理（歸檔 2026-09-28）

從 `AI_HANDOFF_AND_TODO.md` 各區塊移出的單項待辦。

**ComfyUI 產圖**（已在 `e13343d`，2026-09-03 完成）
- 原「- [ ] 步驟 2~4 實作」中的**步驟 2**（租約鎖 + 卸載 helper）；步驟 3~4 仍留在 handoff。
- [x] 三處 `keep_alive` 的註解改成誠實描述（**參數保留**，只改註解；併入步驟 2）

**AI 偶爾插話 Phase B「認得人」**（已實作：`ambient_reply._build_persona_context` + `_PERSONA_CACHE`）
- [x] `ambient_reply` 接 `retrieve_rag_context_sync(question, guild_id, requester_user_id, participant_user_ids, …)`（吃純 id、**不需 interaction 重構**），把在場成員 persona card 轉成 `persona_context` 餵 `generate_reply`。
- [x] participant_user_ids ＝ 近期 `channel.history` 的發言者 + 當前作者；executor 跑（sync LlamaIndex）；best-effort（失敗→None）。
- [x] per-channel persona 短 TTL 快取（~60s），避免 armed 期間每則都打 pgvector。embedding 走 Lemonade 獨立 port（**不卸載 12B**，無 swap 風險）。

**Context 區塊的 Ollama 時代觀察項**（後端已換成 Lemonade，不再適用）
- [ ] Ollama 重試邏輯（觀察 `[WARNING] Ollama 第 1 次呼叫失敗` log）
- [ ] embedding `num_ctx=8192`（`curl http://192.168.56.1:11434/api/ps` 看 `qwen3-embedding:0.6b` 的 `size_vram` 從 ~5.7GB 降到 ~3.1GB）
- [ ] **Windows Ollama server 待調整**（使用者本機設定，AI 無法直接改）：`OLLAMA_KEEP_ALIVE=24h`（原 5m，每 5 分鐘反覆 unload/reload 是 Windows `wsarecv` / ephemeral port 耗盡主因）。`OLLAMA_MAX_LOADED_MODELS=2` 已設好、`OLLAMA_NUM_PARALLEL=1` 已設好。改完重啟 Ollama 後驗證 `server.log` 不再 5 分鐘一次的 `load request`。AMD 顯卡維持 `OLLAMA_VULKAN=true`。

---

## handoff 盤點紀錄歸檔（歸檔 2026-10-02）

- 2026-09-29（第 11 輪續）：點名修改的獨立複查確認行為不變；依複查補上點名端到端測試、修正守衛三處誤判與自測漏洞；9 種突變全紅、648 測試全過；第二個 commit。
- 2026-09-29（第 11 輪）：第一個 commit `97d7595`（`llm/` 重組）；點名改由 Cog 交按鈕建立函式給服務層，服務層不再 import 指令層（新測試 3 項、突變 3 種都紅）；修正 import 守衛把 `__file__` 等模組內建屬性誤判為不存在的問題；646 測試全過，等第二個 commit。
- 2026-09-29（第 10 輪，**未動 code**）：`it_comfyui_image.py` 移出暫存區；MCP R2-Q2 定案（`search`＋`fetch`，設計全部定案）；寫入點名「服務層依賴指令層」的細節與修法選項（建議先不改，改時先補測試再注入按鈕建立函式）。
- 2026-09-29（完整驗證 `llm/` 重組的相依與關連，**未動 code**）：六個角度（測試與運行、實際執行所有 import、相依圖比對與循環、分層、程式以外的引用、git 狀態）都沒有發現這次搬家造成的問題；循環相依前後完全相同。待處理：無關的 `it_comfyui_image.py` 被一起 stage、本檔最新修改未 stage。
- 2026-09-29（grill：MCP 第 3 輪，**未動 code**）：R2-Q3 定案關鍵字全文搜尋、R2-Q4 照建議；R2-Q2 使用者質疑「照來源命名會一直加工具」→ 查證 Anthropic 工具設計指引與 OpenAI MCP 文件後撤回原建議，改建議 `search`＋`fetch` 兩個工具、來源用參數選、來源清單由登記表自動產生，待確認。
- 2026-09-29（grill：L4 定案，**未動 code**）：使用者同意照建議——搜尋本體 `services/search/`（服務，不只給 LLM）、MCP 殼 `llm/mcp_server.py`（給 LLM 的橋接）、網頁搜尋留在 `llm/retrievers/web/`。MCP 區塊的啟動指令、log 分檔名稱、索引檔位置同步更新；R2-Q2～Q4 待答。
- 2026-09-29（第 1、3 項＋收尾，**已完成・643 測試全過・下次重啟生效・未 commit**）：刪 4 處死碼（FB／IT 輪詢迴圈、兩個沒用的 task 屬性、一個沒用的 import，共 32 行；FB／IT 只靠推送）；新增 `test_data_file_paths.py` 釘住 6 個資料檔位置（突變會紅）；刪除只剩快取的 `src/llm/persona_agent/`；S1～S4 結案。L4 使用者重新提出：搜尋獨立成服務、MCP 殼放 `llm/`，待 L4a／L4b 確認。
- 2026-09-29（`llm/` 依角色分子資料夾＋prompt 組裝搬家，**15:26 套用・15:28 重啟・驗證通過・未 commit**；L4 定案 MCP 外殼放 `services/`、名稱維持 `agent`、P3 暫停）：使用者核可 L2a／L2b／L3。在獨立 git worktree 改（bot 以 `./src` 即時掛載，延遲 import 會在重啟前壞），新增 import 守衛 `test_import_resolution.py`（七種突變都會紅、搬家前後都沒有誤判）與 prompt 組裝測試 `test_prompt_builder.py`；搬家前 627 項、最終版 637 項測試全過，逐模組獨立 import 全成功，prompt 組裝 49,152 組輸入逐字相同；兩位子 agent 獨立複查沒有找到執行期問題，指出的守衛誤判與漏抓已修。新舊路徑對照見 [程式結構整理區塊](#程式結構整理2026-09-29-構想grill-中)。L4、P3、第 1／3 項、N3 未動。
- 2026-09-29（grill：程式結構整理，**討論中・未動 code**）：使用者覺得程式很亂，想依功能分資料夾但要有整體規劃。新增 [程式結構整理區塊](#程式結構整理2026-09-29-構想grill-中)，寫入第 1 輪待決問題（痛點、整理方式、分法原則、跟 MCP 的關係）與盤點事實（一檔多功能的檔案、`discord_bot.py` 塞的東西、轉發應整組、`sent_articles.db` 路徑地雷、沒有測試的功能）。MCP 區塊的 R2-Q5 改為取決於這邊。使用者要先看架構怎麼切、以及不影響功能能先做什麼 → 寫入架構草案（`core/`＋依領域分：relay、schedule、ai、search、community、trade、music、misc）與「現在就能做」清單（資料檔路徑集中、私有 import 守衛、清死碼、更新文件、MCP 照新結構寫）。使用者否決草案 v1（拆了 `llm/` 與 Discord 服務），要求從現有架構出發、最小修改 → 改寫成架構建議 v2（P1～P5）；第 1 項縮小成只加測試釘住 6 個資料檔位置，第 3 項確認 4 處死碼（`chat_persistence` 延遲 import 不是死碼，移出）。使用者提出「檔案命名也是問題」→ 讀到 ComfyUI 區塊既有的「檔名正名」與「不做 llm/services 資料夾重組」決定並補進本區塊；寫入命名盤點與第 2 輪待決問題 N1～N4。使用者回覆：N1 同意、N2 三個都不改、N3 延後、P1 否決（services 就是服務）、P3 入口仍由 `discord_bot.py` 管；使用者定義 `llm/`＝LLM 相關的組裝、優化、橋接、RAG、MCP → 撤回搜尋獨立的修正，寫入 `llm/` 討論 L1～L4 與 P3 確認。使用者回覆 L1 同意、L2 要依 LLM 角色分子資料夾（重開不重組的決定）、L4 本地資料一律放 `localdata/` → 寫入第 4 輪：L2a 子資料夾草案、L2b 搬法（一次搬＋import 守衛）、L3 log 格式化移進 `logger_factory`、L4 MCP 殼放 `services/`。
- 2026-09-29（grill：MCP／搜尋工具化，**討論中・未動 code**）：新增 [MCP／搜尋工具化區塊](#mcp搜尋工具化2026-09-29-構想grill-中)，寫入第 1 輪待決問題（誰呼叫工具、結果給誰看、關鍵字過濾的痛點、要回答哪類問題），以及兩個子代理的查證事實（`/askai` 與網頁查詢流程、既有 tool calling、各來源資料量與儲存方式、「寫死日期區間」其實是轉發）。定案：社群稽查（依 ID 查人）不納入工具；用途＝查情報，排除 Telegram 內鬼；改由 LLM 決定何時查；先做 MCP server，工具本體共用。補上 Lemonade 實測速度與 bot 接工具的成本估算；寫入第 2 輪待決問題（MCP 客戶端與部署、工具切法、搜尋方式、論壇索引層級）。使用者追問「一定要另開 container 嗎」→ 在 R2-Q1 補上三種放法（塞進 bot 行程／同 container 另一個行程走 stdio／新 container）的利弊。使用者說不會有別的電腦連 → R2-Q1 定案：只有這台的 Claude Code，採放法 ②（stdio、`docker exec` 啟動，bot 重啟一次裝套件）。使用者問程式放哪 → 新增 R2-Q5（建議 `src/search/` 本體＋`src/mcp_server/` 殼；不可取名 `mcp/`；log 分檔）。使用者問「MCP server 不就取代 search？」→ R2-Q5 補上說明（MCP 只是協定殼，搜尋程式一定要有，差別只在放哪），以及 A 的變體。
- 2026-09-29（新增 repo 根目錄 `AGENTS.md`，**未 commit**）：每次工作都要遵守的規則（討論方式、使用者資料檔高嚴重性規則、Docker 限制、共用元件、程式碼與測試慣例）從本檔與本機記憶搬過去，讓所有 session、一般子代理、雲端都自動載入（Claude Code v2.1.277 以上；repo 裡不要放 `CLAUDE.md`／`CLAUDE.local.md`，否則改讀那個檔）。本檔開頭改成「本檔維護規則」，並寫明每段搬去哪。新規則：討論與 grill 的每一輪都回寫**待決問題（選項＋建議）**；問題每輪只談一個主題、約 3～5 題。依此補寫 Telegram 過濾、ComfyUI、Persona M7 三個暫停主題的待決問題與當時的建議。
- 2026-09-29（log 統一改成 `__name__` ＋ 設定檔，**已實作・595 測試全過・已 commit・已上線**；06:22 重啟後實測：3 小時 781 行、每行帶模組名稱、httpx 逐筆請求 0 行、測試紀錄只進 `test_run.log`、handler 沒有重複（唯一的重複行是 Telegram 啟動時的相簿補圖略過訊息，見 Telegram 過濾區塊）；之後加上 `discord.player` 壓到 WARNING（每播完一首歌一行 ffmpeg 結束訊息，約 250 行／天，下次重啟生效）與「json 裡的 logger 名稱都要對得到模組」的測試）：原本只有 `discord_bot` 這個 logger 掛了輸出，其他名稱的 logger 紀錄**既不顯示也不進 log 檔**（實證：09-29 00:29 建身份組那筆不在 log）。改為：① 新增 `settings/logging.json`（dictConfig）：root 輸出到畫面＋`discord_bot.log`；類別 logger `article_monitor`／`llm_anomaly` 各寫自己的檔、不往 root 傳；httpx／httpcore／urllib3／llama_index 等壓到 WARNING；每行多印模組名稱 `[時間] [等級] [模組] 訊息`。② `utils/logger_config.py` 改成只讀設定檔（import 即套用、冪等；`LOG_LEVEL` 可覆寫 root 等級）。③ 60 個模組從 `getLogger('discord_bot')` 改 `getLogger(__name__)`；`discord_bot.py` 主程式以 script 執行，明確命名 `discord_bot`；`bot.run(..., log_handler=None)` 避免 discord.py 重複輸出。④ 測試模式：`test/__init__.py` 設 `APP_TEST_LOG_FILE`，所有檔案輸出（含 `llm.logger_factory` 的 prompt 除錯檔）改寫到 `/logs/test_run.log`，實測跑完正式 log 位元組數不變。⑤ 守衛：模組 logger 一律 `__name__`（AST 判斷，類別 logger 與 `discord_bot.py` 例外）、不准 `print`；Rule 的 allowed 支援資料夾。突變驗證都會紅。**要拆分類時**：在 json 加一個 handler＋一個以模組前綴為名的 logger（例：`services.relay.telegram_relay_service`；2026-09-30 起 services 分群，模組名稱跟著變），重啟即可，不動程式碼。**下一批**：telegram-scraper 約 45 處 `print` 改 logger → 2026-10-01 已做（見當天 14:3x 紀錄）。
- 2026-09-29（週期活動提醒：深塔海墟，**已實作・586 測試全過・已 commit・待部署驗證**）：深塔／海墟各 28 天、週一 04:00 重置、錯開 14 天；重置前一天 20:00 正常 @、重置當下靜音 @ 自助訂閱身份組「深塔海墟提醒」；綁「週期提醒頻道」時自動建身份組＋發面板，每次提醒後面板刪舊發新置底。詳見 [週期活動提醒區塊](#週期活動提醒深塔海墟2026-09-29-已實作待部署驗證)。
- 2026-09-28（grill：Persona M7 後續／ComfyUI 產圖／Telegram LLM 過濾／深塔海墟提醒，**討論中・未動 code**）：新增 Telegram 過濾與週期提醒兩個草稿區塊並寫入查證事實；ComfyUI 區塊開頭補過時狀態修正（步驟 2 已完成、鎖有漏洞）；過時項目歸檔到 `TODO-completed.md`（Persona 影子模式規劃、Telegram 媒體防雷、ComfyUI 步驟 2 與 `keep_alive` 註解、插話 Phase B 三項、Ollama 時代觀察項），Persona 區塊改成 M7 現況。
- 2026-09-28（Telegram 相簿漏圖，**scraper＋relay 兩端已實作・545 測試全過・已 commit・已部署；今天缺的 87 張已於 15:58~16:07 補發完成**）：使用者回報 GameData #3223 相簿 8 張只發 1 張。**觸發點＝8/02 補掃 commit `fbd2d3c` 加的全域 `process_lock`**：本意是防「同一則」被三條路徑並行處理，卻把 Telethon 本來並行派發的相簿各張變成逐張排隊（組員寫入間隔 p90 0.03s → 2s），relay 0.5 秒到齊判斷等不到整組就先發、晚到的被丟棄。8/02 起 191 組相簿 77 組缺圖、共 237 張。**改法**：全域鎖 → 單則訊息鎖 `(chat_id, message_id)`（新 [message_lock.py](src/telegram_scraper/message_lock.py)）。**relay 端同輪修掉**（使用者拍板）：改成「哪個組員先到就收整組、等媒體到齊＋3 秒安靜才發、晚到的以（補圖）再發、補圖時效 12 小時」。**補今天缺圖**：先校正 delivery_state（補記實送沒標、撤記標了沒送）再重啟，由 reconcile 走正式路徑補發；唯讀預演＝23 則、87 張。詳見 [補掃區塊 2026-09-28 追加段](#telegram-漏收事件自動補掃2026-08-02-已實作2026-08-18-補上中段缺口盲區2026-09-28-全域鎖改單則訊息鎖修相簿漏圖待部署驗證)。
- 2026-09-27（Persona Agent **M7 精簡版發布，已實作・510 測試全過・未 commit**；bot 已隨 09-27 重開跑新程式，⑤ 首次 dry_run 在 09-28 04:00）：**09-28 已 commit 並上線**；現況、定案、待辦與坑已收進 [Persona Agent M7 區塊](#persona-agent-m7精簡版發布2026-09-28-已上線觀察中)（原 HANDOFF 檔已刪除；舊的影子模式規劃已歸檔到 `TODO-completed.md`）。
- 2026-09-22（活動自動發布「連結指向沒有該活動的訊息」+ 重複建活動，**已實作・397 測試全過・待部署驗證**）：使用者回報活動 `1539556072082112604`「[群聲共振模擬域]戰鬥活動」的「公告出處」點進去，那則訊息**一個字都沒提到這個活動**。**根因不在活動功能，在文章轉發**：活動偵測讀 `article_content_full`（該篇 8,454 字），轉發 embed 讀 `article_desc` —— 而 `article_desc` **全庫 532 篇皆為空字串**，於是「沒摘要就取前 300 字當預覽」那條 fallback 成了唯一路徑，8,454 字只發出 303 字；6 個活動名分別在第 1347~2010 字，全部被切掉。而 embed 連 `url=` 都沒設（FB 那邊有），訊息是條死路。**量化**：315 個 article 來源活動中 100 個（31.7%）的活動名在轉發訊息可見文字裡找不到。**同時修掉第二個 bug**：`normalize_title` 不認半形 `<>` → 「活動預告 \| <群聲共振模擬域>…」與「[群聲共振模擬域]戰鬥活動」指紋不同 → 同一活動建了兩個（線上 `…604` 與 `…681`）。**改法**：截斷 300→1200（全庫 p75 僅 565 字，85.2% 完整發出）+ 截斷時附官網連結 + embed 補 `url=`；活動描述嵌該活動的原文片段（匯總帖的 N 個活動各自可讀）；`normalize_title` 收 `<>`（**不收 `《》`**，472 個標題用它、其中 328 個包的是遊戲名「鳴潮」）；**後到的更好來源改為就地升級既有活動的封面與描述**（FB 832/834 有圖、article 三個封面欄位全庫皆空，且 FB 專屬貼文比匯總帖晚 7~28 天到）；同名+區間重疊視為官方改期而非新建（排除**本輪已配對的指紋**，否則 article 995 那種同名不同區間會被吃掉）；加建立/升級序列化鎖、指紋遷移、例外分離、補 log。**升級既有活動走四軸**（封面／描述／時間／名稱各自判斷）：中途曾用單一品質總分當唯一閘門，跑對抗性複查後確認那是錯的——422 筆規劃事件裡 294 筆同分，於是改期走不進換描述的分支（Discord 上時間改了、描述第一行的活動時間還是舊的）、專屬帖的短導言覆蓋匯總帖的長玩法說明（實測 370→118 字）、14.6% 的公告一個字都沒更新，故拆成四軸。**使用者從 Discord 刪掉的活動改立墓碑**（原本實體刪列，7~28 天後另一來源會把它原地復活），只有 `/resend_article` 解得開。**線上 DB 已先以指令套用欄位**（32 列不動，備份在 scratchpad），重啟後直接可用。詳見 [活動自動發布修正區塊](#活動自動發布連結指向錯誤--重複建活動2026-09-22-已實作待部署驗證)。
- 2026-09-02（ComfyUI 產圖 + GPU 資源仲裁，**規劃定案・未開工**；本輪只做線上實測與一則註解清理，未動任何功能 code）：需求＝每天 03:00 排程產圖（角色換衣，依心情／日期／節日），10 張以內。**硬數據**：兩張 RX 9060 XT 各 16GB，27B+ctx32768 本來就跨兩顆吃滿 → 卸載 LLM 是唯一解（釘單顆並行方案否決）。**線上實測（Lemonade 11.5.0 / ComfyUI 0.34.2）**：`POST /api/v1/unload {"model_name":...}` ✅；**卸載後打 chat 會自動重載（22s）→「主動載回」「背景預熱」整段不需要** ✅；`recipe_options`（ctx 32768 + sampling args）不會被洗掉 ✅；**ComfyUI 看不到 Lemonade 的 VRAM**（Vulkan vs HIP，27B 在與不在都回報 free 15.78 GiB）→ 不可用它判斷夠不夠 ✅。**設計定案**：鎖改**租約+心跳**（續租點掛在本來就要做的 ComfyUI 輪詢上，不開 checker task、不猜 timeout）；租約 120s 管卡死、deadline 03:50 管超時（04:00 有維護四步要用 GPU）；租約過期接管者要清 cache + log error。**換後端**：Ollama 可續用（`keep_alive:0` 就是原生卸載語意），vLLM 不可；三處 `keep_alive` **保留**（一度決定刪除，使用者否決且正確：它是可攜層該有的行為，且註解含 Ollama 時代實戰教訓），只把註解改誠實。**prompt v1 走規則零 LLM**：節日查表 + 重用 00:00 AI 日記當心情來源。**本輪 code 異動**：① 拿掉 `_try_heal_lemonade_backend` 那句無法查證的「裸 reload 會掉回 ctx 4096」註解；② `DIARY_TZ` → `APP_TZ`；③ 時區守衛從 regex 改走 AST + 補 5 項自我守衛測試（342 測試全過，未 commit）。詳見 [ComfyUI 產圖區塊](#comfyui-產圖--gpu-資源仲裁2026-09-02-規劃定案未開工)。
- 2026-08-18（Telegram 補掃補不到「中段缺口」，**已實作・未 commit・待部署驗證**）：使用者回報「重啟後又發一大堆早上 10-11 點的文章」，疑似重複。**查證＝不是重複、是首次補發**：`delivery_state` 全表無任何 `message_pk` 送超過 1 次，該批 8 則 `message_date` 10:31~11:03 但 `created_at` 全是 **17:24**（重啟才入庫）；早上 111 則中 34 則無 delivery 記錄者**全部**是 media group 成員（由首則代發），無法解釋的漏發 = 0。**根因**＝2026-08-02 版補掃的 `offset_id = max(message_id)` + `reverse=True` 只看得到比 max_id 更新的訊息，漏的若是**中段**（2742/2743/2746 漏但 2745/2747 已收 → max_id 早跳過去）永遠掃不到，只能等重啟全量掃描（本次卡 7 小時）。**修法＝指針左移**（使用者拍板改既有流程、不另開補洞路徑）：`offset_id = max_id - CATCHUP_GAP_WINDOW(300)`；配套 ①`limit` 加大成 `300+200`（limit 卡的是**撈回**幾則，沿用 200 會在 `window_start+200` 截斷）②新增 `db.get_existing_message_ids` 一次撈視窗內已有 id 成 set 過濾（否則 290 則已存在訊息各跑完整 `_process_message`）。**驗證**：容器內注入假 client/db 重現 8/18 真實缺口，洞全補回、新訊息照收、已存在 297 則零重跑；**反向驗證** limit 壓回 200 → 掃描截斷、洞與新訊息一則都收不到。**下一步**：`docker compose restart telegram-scraper`。詳見 [補掃區塊追加段](#telegram-漏收事件自動補掃2026-08-02-已實作2026-08-18-補上中段缺口盲區待部署驗證)。
- 2026-08-09（插話「談話自然」重構，**已實作・待部署驗證**；py_compile 全綠、146 測試全過、未 commit）：使用者提出兩個痛點——①一偵測到發言就馬上運算，沒等人講完；②聊天室常有多組人聊不同主題，機器人不知該加入哪個。**本輪量到基準**：自發插話「trace→送出」中位 **120.8s**（p90 165s、max 901s，n=3540）、PASS 率僅 15%、`ai_interactions` 5602 筆但負向反應只有 **13** 筆。**核心診斷**：問題不是它選錯主題，是**選的時候那條線還在、120 秒後講出來已經沒了**，而自發插話是裸 `channel.send` 無指向 → 必然像亂入；且節奏由冷卻計時器決定（每 5 分鐘準時報到）而非對話內容。**目標函數經使用者拍板＝自然/人性，GPU 節省降為副作用**。**四層方案**：L3 選線+reply 錨定（第一優先，讓「慢」變合理）、L4-b 接續自己的話、L2 debounce+typing 不搶話、L1 鉤子閘（**不用 LLM**＝結構演算法+少量 regex+k-NN，權重用 logistic regression 從 5602 筆學、標籤改用「插話後有沒有人接」而非 reaction）。順帶 `max_passes_per_burst` 3→1、`cooldown` 300→180。**使用者否決**：等鎖上限（GPU 本來就慢，放棄等於 /askai 忙時永遠不插話）、新鮮度丟棄（被接完也可以插，且丟棄＝白燒 120s 零產出）。**實作中修掉的缺陷**：L4-b 借用 directed 路徑會連 foreground 讓位/降溫硬閘/每小時上限一起繞過 → 加 `followup` 旗標分流閘門。**下一步**：`docker compose restart discord-bot` → 看 log 的「ambient 鉤子」分數分布調 `hook_threshold`、看「錨定=#N」確認模型有遵守選線契約。詳見 [自然插話重構區塊](#自然插話重構2026-08-09已實作待部署驗證)。
- 2026-08-02（Telegram 漏收事件自動補掃，**已實作，待部署驗證**）：症狀＝「最新的 telegram 沒有轉發」。**relay 端無辜**（delivery_state 3119 筆、`last_polled_pk`=`max(id)`=12494，DB 內全送完）；**斷點在 scraper**——Telegram 已有 `Seele_WW_leak/9824`，DB 最大卻停在 **9823**（08-01 22:29:48+08）。用 `telegram_emoji_refetch` NOTIFY 測活性，scraper **秒回且成功即時抓回 9823** → 連線正常、非卡死。**根因**＝Telethon 漏派 NewMessage 事件（handler 完全沒被呼叫），而 [runner.py](src/telegram_scraper/runner.py) **只在啟動時掃一次歷史**，之後純靠即時事件 → 漏掉就永久漏掉。**非偶發**：以 `created_at - message_date > 5min` 回推「靠重啟才補進來」的比例 7/25 **28/63**、7/26 **59/121**，過去都是剛好有重啟蓋掉問題。**實作**＝每 15 分鐘（`catchup_interval_min`，可熱調整、`<=0` 停用）以各頻道 DB 最大 message_id 為基準做 `iter_messages(reverse=True, offset_id=基準, limit=200)` 增量重掃（已讀 Telethon 1.43.2 原始碼確認 reverse 下 `offset_id` 內部 +1＝不含基準、回傳舊→新保 PK 時序）；即時/補掃/refetch 共用 `process_lock` 序列化；單輪上限由舊往新掃故不留永久空洞；單頻道拋錯不拖垮迴圈。**順修** History log 把 Gamedataleak 訊息全標成 `source_channel=Seele_WW_leak` 的誤導 bug。**驗證**：py_compile 全綠、容器內 stub 煙霧測試 15 項全過、`get_peer_id` 與 DB chat_id 一致、實 DB 基準 Seele=9823/Gamedataleak=2669。**已 commit（`fbd2d3c`）**，`runtime_config.json` 刻意未動（受保護檔，程式端預設已生效）。**下一步**：`docker compose restart telegram-scraper` → 立刻補回 9824 → 觀察 `[CatchUp]` log。詳見 [Telegram 漏收事件自動補掃區塊](#telegram-漏收事件自動補掃2026-08-02-已實作待部署驗證)。

---

## 共用元件索引（已搬到 AGENTS.md）（歸檔 2026-10-02）

<!-- @meta
id: shared-components-index
type: CONTRACT
status: deprecated
last_confirmed: 2026-09-29
affects: 全專案
-->

> 2026-09-29 起，共用元件表在 `AGENTS.md`「共用元件」，由 `src/test/test_shared_conventions.py` 守衛。這裡只留下各個合法例外的緣由，供追查時參考。

**合法的例外（形狀不同，硬收斂反而更糟，已寫進守衛的 allowlist）**
- `scraper/tools/extract_fingerprint.py` 的時區：scraper 是獨立容器（掛 `./src/scraper` → `/app`），根目錄看不到 `sys_settings`。兩邊都吃 compose 的 `TZ=Asia/Taipei`
- `emoji_text_utils._load_descriptions`：永久快取 + 明確 `reload_descriptions()`，因為字典是被 04:00 排程改寫後主動重載，不是靠 mtime 輪詢
- `ambient_reply._load_ambient_prompt`：多檔疊層且有自己的組裝順序
- `llm_service._load_runtime_config_cached`：讀 pydantic 設定物件，錯誤處理不同

---

## 程式結構整理：討論與實作紀錄（歸檔 2026-10-02，原 2026-09-29）

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

---

## IT 新聞只帶摘要發出（歸檔 2026-10-02，原 2026-10-01）

<!-- @meta
id: it-article-intro-only
type: RISK
status: confirmed
last_confirmed: 2026-10-01
affects: services/relay/it_article_monitor.py, scraper/services/hkepc_scraper_service.py
-->

**症狀（使用者 2026-09-30 回報）**：IT快訊〈前 EVGA 產品經理首度公開內幕…〉轉發的內文跟全文不符、被截斷。

**機制（一句話）**：HKEPC 內頁被擋（403）時資料庫只有列表頁的開頭摘要，bot 發文「有內文用內文、沒有就用摘要」，發完就標記已發送，之後 scraper 補到內文也不會再更新。

- **查證**：該篇 `hkepc_id=26838` 的 `content` 是空的，只有 `introduction`（467 字）；21:34、22:34 兩輪內頁都 403。同輪的 26837（Walmart）也一樣。有內文時上限 4000 字（`EMBED_DESC_MAX`），目前內文都在 2,000 字以內，不會被截。
- **scraper 會自己補**：每輪都替缺內文的文章重抓內頁（已有內文的才跳過，`hkepc_scraper_service.py` `existing_with_content`）；30 天來只有今天這 2 篇到現在還缺。
- **量化**：
  - 9/22 起主 log 有 73 篇 IT 發送，其中 **23 篇（約三分之一）是發送前 15 分鐘內剛被 403**，也就是只帶摘要發出。
  - 403 紀錄從 7/14 起共 155 篇；每篇被擋幾輪才抓到（輪數：篇數）＝ 1：101、2：34、3：13、4：6、5：1。等 3 輪涵蓋 95%，等 4 輪涵蓋 99%。
  - 不是這次整理或升級造成的：HKEPC 用自己的請求流程，403 從 7/14 就有。
- **現成的補救**：`/resend_article` 可以用 hkepc_id 重發 IT 文章；但要等內文補到才有意義。

**使用者決定（2026-10-01）**：IT-Q1 選 B「先發摘要，內文到了直接更新那則 embed」；IT-Q2 同一個機制補今天那 2 篇（免刪除）。
- **實作方式（未改使用者看到的行為，只換機制）**：不另存訊息 id，改成每次 HKEPC 通知時讀 IT 頻道最近 3 天的訊息（登記表限定文字頻道，1～2 次 API），用 embed 的原文網址（解碼後比對）對回文章；描述剛好等於「沒內文時的摘要版」、而現在有內文，就就地 `edit` 成完整內文，原本沒圖而內文帶圖時補第一張。好處：不必在 `sent_articles.db` 加表（高風險資料檔），已經發出去的舊訊息也會一起補上。排版對不上的訊息不動（寧可漏補，不誤改）。
- **狀態**：已上線（10/01 03:46 bot 重啟載入）並 commit（`6f39e87`）；複查後修正版 `test_it_article_refresh.py` 12 項、9 種突變都紅。等下一次 HKEPC 通知實際補上摘要訊息。

**第 1 輪的選項（已定案，留作紀錄）**
- **IT-Q1 修法**：A bot 端「內文到了才發」：沒有內文的先跳過、等下一輪；超過寬限仍沒有，就發摘要並註明「內文未取得，完整內容請點標題」／B 先發摘要，內文到了再就地編輯那則訊息（要另存訊息 id、多一套狀態）／C 只改 scraper，讓 403 少一點。建議 A：只改 `check_and_send_new` 的篩選，不需要新狀態；代價是約三分之一的 IT 新聞晚 1～3 小時發。
- **IT-Q2 寬限多久**：建議 3 小時（3 輪，涵蓋 95%）；4 小時涵蓋 99%，但晚得更多。
- **IT-Q3 已經發出的**：建議舊的 21 篇不處理（已是舊聞）；今天這 2 篇等內文補到後，你刪掉原訊息、用 `/resend_article` 重發。
- **IT-Q4 scraper 端要不要一起降低 403**：原建議先不做；查到抓網頁機制有明確的問題後，改為跟下面「scraper 抓網頁機制」一起處理（見 SC-Q1～Q3）。

---

## scraper 抓網頁機制檢查（歸檔 2026-10-02，原 2026-10-01）

<!-- @meta
id: scraper-fetch-fingerprint
type: RISK
status: confirmed
last_confirmed: 2026-10-01
depends_on: it-article-intro-only
affects: scraper/services/base_scraper_client.py, scraper/services/hkepc_scraper_service.py, scraper/services/bahamut_scraper_service.py
-->

**使用者問**：是不是被黑名單了？抓網頁的機制（瀏覽器指紋等）有沒有問題、有沒有隨機？

- **不是 IP 被封鎖**：同一台主機直接連，巴哈 0.23 秒、HKEPC 0.5 秒都回 200；scraper 容器內用 curl_cffi 0.16.3 連巴哈也是 0.2 秒、HTTP/2。兩站都在 Cloudflare 後面。HKEPC 的 403 是間歇的（被擋的 155 篇裡 101 篇下一小時就抓到），比較像防火牆逐筆評分，不是封鎖。
- **有隨機化**（`base_scraper_client.py`）：每個 session 從 10 個瀏覽器目標隨機選一個（Chrome 124／131／136、Edge 99／101、Firefox 133／135／144、Safari 17.0／18.0），另有 30% 機率用本地抓的 Firefox ESR 140 指紋；延遲也是隨機（巴哈每頁 2～5 秒、每篇 0.35～0.9 秒、留言 0.15～0.35 秒）。
- **查到的問題**（對 httpbin 實測送出的標頭）：
  1. **標頭自相矛盾**：`_build_page_headers`／`_build_xhr_headers` 對所有 Chromium 目標一律加 `Sec-CH-UA-Platform: "Linux"`，但 curl_cffi 的 Chrome 目標 UA 是 macOS、Edge 是 Windows；自己寫的 `Sec-CH-UA` 還蓋掉了 curl_cffi 內建的正確值（例：chrome131 內建送 `"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"`、平台 `"macOS"`，被換成 `"Chromium";v="131", "Not;A=Brand";v="24", …`、平台 `"Linux"`）。真的瀏覽器不會這樣，是防火牆很容易抓到的特徵。
  2. **HKEPC 每一頁都開新 session**（`hkepc_scraper_service.py` `_fetch_html`）：每頁隨機換一個瀏覽器、cookie 不延續，同一個 IP 幾秒內從 Mac Chrome 變 Windows Edge 變 Firefox。巴哈是一輪共用一個 session，沒有這個問題。
  3. **瀏覽器版本偏舊**：Edge 99／101 是 2022 年的版本，其他也是 2024～2025 年；2026 年的真實流量裡很少見。
  4. **403 當輪不重試**：`_fetch_with_retry` 只在連線例外時重試，拿到 403 直接交回，要等下一小時。
- **巴哈變慢另案**（見盤點紀錄 22:5x）：取樣 22:34 那輪執行緒 300 次，70% 在刻意的睡眠、21% 等網路、7% 跑 CPU，所以不是被擋或網路慢；請求一次只要 0.2 秒、每輪存的樓數也沒變，卻多花 4 倍時間（兩輪都是抓 74 分鐘＋寫 4 分鐘），原因還沒找到；每輪都比排程間隔長，每小時會有約 18 分鐘兩輪同時在抓。巴哈 logger 等級是 WARNING（`scraper/config.py`），逐筆請求不會寫 log，目前數不到每輪發了幾次請求。

**待決問題（第 1 輪，每題附建議）**
- **SC-Q1 標頭矛盾**：A 拿掉自己加的 `Sec-CH-UA`／`Sec-CH-UA-Platform`／`Sec-CH-UA-Mobile`，讓 curl_cffi 送內建、與 UA 一致的值；本地 Firefox 指紋本來就不送這些，不受影響／B 保留自訂但改成跟 UA 對應。建議 A：最小改動，而且以後 curl_cffi 新增目標也會自動正確。
- **SC-Q2 HKEPC 一輪共用一個 session**：建議做，跟巴哈一樣一輪只選一次瀏覽器、cookie 延續。
- **SC-Q3 瀏覽器池**：建議拿掉 Edge 99／101，改用 curl_cffi 0.16.3 支援的較新目標（實作前先列出它支援的清單再選）。
- **SC-Q4 巴哈變慢**：建議在「Bahamut 爬蟲任務完成」那行加上本輪的請求次數、睡眠總秒數、抓的頁數，下一輪就知道時間花在哪；不開逐筆 log（太多）。

**使用者決定（2026-10-01）**：SC-Q1～Q4 都照建議。

**第一版實作（worktree `wt3`；後來改成下方共用層版本）**
- `base_scraper_client.py`：拿掉自訂的 `Sec-CH-UA`／`Platform`／`Mobile`；池改成 Chrome 145／146／150、Firefox 144／147、Safari 26.0／26.0.1（Edge 拿掉）；池裡目前 curl_cffi 不認得的目標會被剔除並記警告，全都不認得時退回 `"chrome"` 別名（requirements 沒鎖版本，避免哪天重建後每個請求都失敗）。PTT 也用這個客戶端，一併受惠。
- `hkepc_scraper_service.py`：一輪只建一個 session，列表頁與內頁共用。
- `bahamut_scraper_service.py`＋`main.py`：每輪統計請求次數（含留言 XHR）、成功頁數、等待秒數、抓取耗時，另加寫入資料庫的秒數，寫在「Bahamut 爬蟲任務完成／未完成」那行。
- 測試：新增 `src/scraper/tests/`（scraper 容器內執行：`docker exec -w /app scraper python -m unittest discover -s tests -t . -p 'test_*.py'`；bot 容器沒有 curl_cffi，不進 bot 的啟動 gate），7 項，8 種突變都紅；測試期間關掉 logging，避免寫進正式 `/logs/scraper*.log`。
- 實測（httpbin 回顯）：新池 7 個目標的 UA 與平台標頭都一致（Chrome 報 macOS；Firefox／Safari 不送，符合真瀏覽器）。

**實測新發現（2026-10-01 00:2x，影響上線）：HKEPC 的 Cloudflare 看的是「模擬哪種瀏覽器」**
- 對 HKEPC 內頁與列表頁：Chrome 145／150、Safari 26 **一律被挑戰頁擋下**（403「Just a moment...」，跟我們加不加標頭無關）；Firefox 144／147、本機 Firefox ESR 指紋**全部 200**；主機用普通 curl 也是 200。巴哈不挑（Chrome、Firefox 都 200）。
- **這就是 403 時有時無的原因**：以前每頁隨機換瀏覽器，抽到 Firefox 的頁面過、抽到 Chrome／Safari／Edge 的被擋，所以同一篇下一小時常就成功；列表頁每天被擋 15～19 次、內頁 2～8 次，兩週來都這樣。
- **因此「HKEPC 一輪只用一個瀏覽器」單獨上線會更糟**：抽到 Chrome／Safari 的那一輪整輪都會被擋（估計約一半的輪次）。
- **SC-Q5 HKEPC 用哪些瀏覽器**：A HKEPC 只用 Firefox 系（curl_cffi 的 Firefox＋本機 Firefox ESR 指紋），一輪一個 session／B 一輪一個 session，遇到挑戰頁就換一個瀏覽器重抓那一頁／C 維持每頁隨機換（撤回 SC-Q2）。建議 A：實測 Firefox 全過；只影響 HKEPC（子類別覆寫 `IMPERSONATE_POOL`，基底類別已支援），巴哈、PTT 照舊。之後若 Firefox 也被擋，再加 B 的換瀏覽器重試。

**使用者（2026-10-01 00:4x）**：HKEPC 再測深入一點；UA 等特徵本來就有共用層，不容易被擋的做法應該大家一起共用。→ SC-Q5 改成在共用層處理。

**逐站實測矩陣（2026-10-01，13 種指紋 × 6 個實際網址，請求間隔 1.5～2.5 秒）**
- HKEPC 內頁與列表：**Chrome 124／136／146／150、Safari 18.0／26.0.1 全部被挑戰頁擋**；Firefox 133／144／147、本機 Firefox ESR、Tor 145、Edge 101 通過；不偽裝的 curl_cffi 內頁過、列表被擋。
- 巴哈看板與文章、PTT、官網 JSON：13 種全部通過。（第一次跑時 PTT 全標成被擋是誤判：Cloudflare 在正常頁面也嵌 `challenge-platform` 腳本；改成只認「403／503＋Just a moment」後 PTT 全部 200。）
- **每站一個 Firefox session 模擬正式一輪**：HKEPC 列表 3 頁＋內頁 5 篇（含一直被擋的 26838、26837）、巴哈 4、PTT 4、官網 4，全部 200；本機 Firefox ESR 跑 HKEPC 一輪也全部 200。
- **用新程式實跑 HKEPC 兩輪**（資料庫以假物件代替、不寫入；刻意抓全部 15 篇內頁）：curl_cffi Firefox 147 一輪、本機 Firefox ESR 一輪，都是 15 篇全有內文、0 錯誤。

**定案並實作（2026-10-01 03:46 上線；commit `648b80b` 抓網頁機制、`20acc0c` 巴哈統計）**
- 共用層預設池改成**只用 Firefox 系**（firefox144／147＋30% 本機 Firefox ESR）；備援別名改 `"firefox"`。理由：所有網站都通過的只有 Firefox 系；一個 IP 固定用同一種瀏覽器也比每次換一種像真人。Chrome／Safari 目標清單刪掉，要加回先逐站實測。
- 共用層新增 **`run_session()`**：區塊內 `_build_session()` 都回傳同一個 session（呼叫端的 `with` 不會關掉），離開區塊才關；巢狀沿用外層；區塊外照舊每次新建。HKEPC（`fetch_hkepc_articles`）、PTT（`fetch_ptt_articles_with_content`）、官網（`scrape_articles`）的一輪入口都包上；巴哈本來就一輪一個 session。先前 HKEPC 自己傳 session 的寫法撤回，改用共用機制。
- 測試：scraper 11 項（共用層標頭、Firefox 池、備援、`run_session` 語意、三個爬蟲一輪一個 session、巴哈統計、完成那行 log），13 種突變都紅；bot 659 項全過（含 IT 就地補內文 7 項）。
- 套用順序：先重啟 discord-bot（IT 補內文的程式要先上線），等啟動 gate 過、Notify Server 起來，再重啟 scraper（它一啟動就會跑 HKEPC，並通知 bot）。避開 04:00～07:30。

**獨立複查（子 agent，2026-10-01 01:0x）與修正（patch 改為 `scraper_it_v2.patch`）**：沒有會讓現在正式環境出錯的問題；照意見修正：
- **潛在啟動失敗**：curl_cffi 原始碼把 `BrowserType` 標成 1.x 移除，requirements 沒鎖版本 → 改成可選匯入，拿不到就不過濾（不鎖版本，照 S6-2 的決定）。測試會模擬它被拿掉並重新載入模組。
- IT 補內文：讀頻道改成**從最新的讀起**（有 `after` 時 discord.py 預設由舊到新，`limit` 會先吃掉最舊的）；改成**先發新文、再補舊訊息**；用**網址裡的文章編號**比對（站方改標題時 scraper 會更新 url）；**帶圖的編輯失敗時退回只換文字**；原本就有圖時改用 `attachment://` 引用原附件（讀回來的圖片網址帶簽章會過期），並明確列出舊附件（沒列的會被刪）。網址解碼拿掉（改用編號後用不到）。
- 巴哈：中途拋例外時統計留在 `last_stats`，`main.py` 記一行「Bahamut 爬蟲任務中斷」與做到哪；用語法樹檢查所有等待都經過 `_sleep`（複查把 3 處改回 `human_sleep`，舊測試沒紅）。
- 結果：bot 664 項全過（IT 補內文 12 項，9 種突變都紅）；scraper 16 項（19 種突變都紅）；最終版實抓一頁 HKEPC 列表成功（Firefox 144）。
- **未做、記為之後的選項（SC-Q6）**：一輪共用 session 後，若該輪指紋被擋會整輪失敗；以前逐頁各自重抽。只用 Firefox 的前提下風險低，建議先觀察，若 HKEPC 又出現 403 再加「遇到挑戰頁換一次 session 重抓」。

---

## 週期活動提醒：深塔海墟（歸檔 2026-10-02，原 2026-09-29）

<!-- @meta
id: periodic-event-reminder
type: STATE
status: confirmed
last_confirmed: 2026-09-29
depends_on: event-announce-link-and-dedup-fix
affects: 排程、身份組、config.json
-->

**需求（使用者 2026-09-28 提出）**
- 《鳴潮》的週期活動「深塔海墟」每四週重置一次，**重置時 @ 特定身份組**提醒。
- 這個身份組**成員可自由領取**（自助加入／退出）。
- 提醒要放**一般文字頻道還是論壇頻道**：使用者還在猶豫，要一起討論再決定。
- 要跟既有的「公告 → 自動建 Discord 伺服器活動」怎麼整合，待確認。

**查證事實（2026-09-28，唯讀調查）**
- **週期**：深塔（逆境深塔）與海墟（冥歌海墟）各自每 **28 天**、**週一 04:00（UTC+8，用 `SERVER_TZ`）**重置，**兩者錯開 14 天**（每兩週輪到一個）。
  - 海墟錨點 **2026-02-16 04:00**（唯一官方來源：FB 貼文 273）→ 下三次 10/26、11/23、12/21
  - 深塔錨點 **2026-03-02 04:00**（聊天紀錄與使用者在 🤖公告與建議專區「新功能」討論串的手記）→ 下三次 10/12、11/09、12/07
  - 11 個已知重置日全部落在 28 天格點上；官方從未公告週期 → 只能「錨點 + 28 天」。
  - 版本維護撞重置日的例子：3.4 = 2026-06-08 週一 04:00~11:00（那期要等維護結束才能打，但週期沒被推移）。
- **矩陣（終焉矩陣）跟版本走**，不是固定週期；但規則可由版本日推算（2026-09-29 查證）：
  - **週期**（S1「無盡危局」3.2～3.4、S2「險境強襲」3.5～3.8）底下，**每個版本一個階段**（S2-1、S2-2…），每階段新增三個挑戰任務。
  - **階段開放＝該版本更新維護開始日 +7 天的 04:00**；**階段結束＝下一版維護開始前**（例：S1 第二階段「2026年5月7日04:00 ~ 3.4版本維修前」）。證據：巴哈「終焉矩陣」看板各階段隊伍分享串主文的明確時程，7 次開放 6 次 +7 天（唯一例外是先行版第一次上線當天開放）。
  - **下一版更新日可以提早約 3 週推得**：每版最後一個卡池（「✦活動時間：… ~ YYYY年M月D日11:59」）都在「下一版更新前一天 11:59」結束，下一版隔天 04:00 開始維護（2.0～3.7 共 18 版全數 +16 小時）。下半卡池公告約在版本中段發出，比維護預告（約提前一週）早。
  - **3.7 之後的下一版在 11/12 04:00 更新**（使用者確認；版本號未定，可能是 3.8 或 4.0）。巴哈玩家轉述前瞻的「版本期間：2026/9/30 ～ 2026/11/11」，結束日是**最後一天**（＝最後卡池結束日），不是更新日。→ S2-3 預計 10/7 04:00 ～ 11/12 03:59。**推算一律用日期、不依賴版本號**。
  - 深塔／海墟起算日另以巴哈 44 期隊伍分享串驗證：43 期吻合，唯一例外是海墟第 1 期（2025-02-13 隨 2.1 上線）。社群期數：深塔第 33 期＝2026-03-02、海墟第 14 期＝2026-02-16。
- 既有「公告 → 伺服器活動」**從未**替深塔／海墟建過活動（閘門要求「活動時間」字樣）。現有 8 個 bot 建的活動，「有興趣」人數全部是 0。
- **伺服器**：Onboarding（原生「頻道與身分組」）關閉；bot 有 ADMINISTRATOR 且位置最高；24 個身份組全部 `mentionable=False`；程式裡沒有任何自助領身份組功能（`add_roles` 0 筆），persistent view 慣例成熟可沿用。
- **候選頻道**：🍼深塔海墟矩陣-代打（text `1480854656342294569`，主題是代打免責聲明，@everyone 可看）；📶活動情報（forum `1276560265533587591`，@everyone 唯讀、無活躍貼文）；🌸祕密花園（深塔／海墟討論 601 則裡有 561 則在這，但「鳴潮皇帝」看不到）。
- **論壇 @身份組 的通知行為未驗證**：據社群回報，超過 100 人的身份組在討論串裡可能被拒；bot 開新貼文時首則的身份組 ping 可能不通知；被加進串的人預設收到每則回覆的通知。
- **坑**：新身份組**不要**加進幽靈點名的排除清單（那份清單幾乎包含所有自訂身份組，加進去等於訂提醒就免點名）；bot 沒有全域 `allowed_mentions`，提醒訊息要明確指定 `AllowedMentions(roles=[該身份組])`。

**已定案（2026-09-28）**
- 發在**一般文字頻道 🍼深塔海墟矩陣-代打**，不用論壇（這個群不用論壇、論壇 @ 通知不可靠；討論留在原本的地方）。
- **一個身份組**涵蓋深塔與海墟（每兩週輪到誰就提醒誰）。
- **第一版只做深塔、海墟**；設定設計成「一個項目＝起算日＋週期」的清單，矩陣日後有可靠來源再加。
- **自助領取用按鈕**：面板上放「訂閱／取消訂閱」（persistent view），按下只回按的人看得到的訊息。
- **面板不釘選、改置底，而且立即置底**：發完提醒、或提醒頻道裡**有人講話**就立即「刪舊發新」（bot 自己的訊息不算，避免循環）；連發時合併，同一時間最多一次在跑、一次排隊。走共用的 `utils.panel_bump.PanelBumper`。提醒訊息本身不附按鈕。面板顯示各項目的下次重置日期。
- **提醒時間**：結束前提醒＝重置前一天 20:00，正常 @；重置提醒＝週一 04:00 準時，**靜音 @**（`silent=True`：有提及紅點、不推播）。
- **身份組「深塔海墟提醒」**：綁提醒頻道時由 bot 自動建立（`mentionable=False`、無權限），被刪會自動重建；不加進點名排除清單；提醒只 @ 這個身份組。
- **文案**：中性工具口吻，不用琇紫人設。
- **起算日與週期寫在程式的設定類別**（改了要重啟；`config.json` 屬使用者設定檔，AI 不自行改寫）；時間一律用 `SERVER_TZ`。
- **撞版本維護第一版不處理**（現有版本時間解析只記維護結束、只能用版本號查；約 20 期一次；重置提醒本來就靜音）。
- **補發**：bot 離線錯過時，結束前提醒補到重置前、重置提醒補到當天 12:00；去重用 StateDB `sent_content`。不建 Discord 活動、不加管理指令。
- **驗證**：單元測試以使用者手記為標準答案（海墟 8/3、8/31、9/28、10/26；深塔 8/17、9/14、10/12）；部署後依序：綁頻道看面板日期 → 按訂閱 → 整合腳本在正式頻道發真的「海墟已重置（到 10/26）」靜音 @ → 結束前提醒樣本發到只有管理員看得到的頻道測正常 @。
- 使用者決定**先做深塔提醒**；Persona 後續、Telegram 過濾、ComfyUI 暫停。

**矩陣接入的決定（2026-09-29）**
- 深塔、海墟、矩陣**共用一個身份組**，名稱改為「**週期活動提醒**」。
- 矩陣提醒**不寫階段編號**（S2-3 這種要靠版本號解析，版本號可能跳 4.0）。
- 版本延期時官方一定會公告：排程每次都依最新公告重算，面板與提醒日期跟著更新即可。
- 深塔／海墟期數：使用者覺得可有可無；可由「深塔第 33 期＝2026-03-02、海墟第 14 期＝2026-02-16、每 28 天 +1」直接推算。

**矩陣接入實作（2026-09-29，618 測試全過，未 commit）**
- `VersionDateResolver.update_starts()`（`services/events/event_scheduler.py`）：**不快取、每次重讀**官方公告，回傳所有版本更新維護的開始時刻；來源一＝「X.Y版本」標題＋「更新維護時間」的第一個日期，來源二＝標題含「喚取」「第二期」的下半卡池結束日隔天 04:00（前後 7 天內有官方時間就以官方為準）。版本號只用來認公告。實測：真實 DB 每次約 6 ms、不需要 index（`LIKE '%…%'` 本來就用不到 index）；卡池推算的 7 筆與官方時間全數一致。原本的 `_load()`／`update_time()` 不動。
- 設定：`VersionStageItem`（key=matrix、🧩、開放延遲 7 天）；`role_name` 改「週期活動提醒」，bot 啟動與每次取身份組時**依設定同步名稱**。
- 純邏輯：`Reminder.cycle` 改名 `item`；矩陣結束前提醒＝下一次更新前一天 20:00（正常 @），開放提醒＝更新 +7 天 04:00（靜音 @）；**不知道下一次更新就不發結束前提醒**（不用 +42 天硬猜）。
- 面板：「**時程**」下深塔／海墟之外多一行矩陣：空窗週「新階段 10/7（週三）04:00 開放」、已知結束「本階段開放中，9/30（週三）04:00 結束」、未知「本階段開放中，於版本末結束」。排程每輪比對面板標題＋內文（存在 runtime 的 `panel_content`），**一變就自動重發**。
- 讀 articles.db 走 `asyncio.to_thread`，不卡 event loop。
- 測試新增 19 項（開放日對上巴哈 S1-1～S2-2、結束前／開放提醒、空窗週、未知下一版、卡池推算、官方優先、身份組改名、面板變更才重發）；突變驗證：+7 改 +6、卡池少了隔天、未知時硬猜 +42，三種都會紅。
- **已修（2026-09-29，使用者要求：bot 會長時間不重啟）**：活動自動發布用的 `_version_resolver` 原本是模組層單例、只讀一次 DB，bot 啟動後才發的版本公告看不到，「X版本更新後」起算的活動會被略過。改為：① `refresh()` 每次排活動前在執行緒重讀，讀取失敗保留上次結果、版本有增減才寫 log；規劃過程中的 `update_time()` 只查記憶體。② 開 articles.db 改用一般唯讀 `mode=ro`，**不再用 `immutable=1`**：articles.db 是 WAL 模式（`-wal` 檔約 99 MB），immutable 會忽略還沒合併回主檔的 WAL，看不到剛寫入的公告，爬蟲合併時還可能讀到錯誤結果。新測試 `test_version_date_resolver.py`（啟動後才發的公告、update_time 不碰 DB、失敗保留、WAL 可見）；突變驗證改回 immutable、refresh 退化成只讀一次都會紅。

**實作（2026-09-29，已 commit）**
- `sys_settings/periodic_reminder_settings.py`：起算日、週期、提醒時刻、身份組名稱、runtime 路徑
- `services/events/periodic_reminder.py`：純邏輯（推算重置、到期／補發判斷、文案、面板內容）
- `commands/periodic_reminder_commands.py`：排程迴圈（最多睡 1 小時就重算）、訂閱按鈕（persistent view）、`ensure_role`（id → 同名既有身份組 → 建立）、`on_message` 有人講話就置底
- `settings/channel_registry.py`：登記「週期提醒頻道」，綁定時自動建身份組＋發面板；`discord_bot.py` 的 `COMMAND_MODULES` 加入；`.gitignore` 加 runtime 檔
- `test/test_periodic_reminder.py` 33 項（突變驗證過：靜音顛倒、提醒晚一小時、週期改 27 天、拿掉今天／明天判斷都會紅）；文案只比對關鍵資訊（誰、項目、日期、今天／明天），不逐字比對
- `test/integration/it_periodic_reminder.py`：手動發一則提醒實測（不寫 StateDB、不置底）

**面板置底收斂（2026-09-29，586 測試全過，已 commit）**
- 新增 `utils/panel_bump.py`：`PanelBumper` 只管「在哪、刪舊、發新、記住、同時只做一次」，面板長相由呼叫端的 `send` 決定。位置記在各自 runtime 檔的 `{key_prefix}channel_id / message_id`，寫入時保留其他欄位。**沒有完整紀錄時**才翻頻道最近 50 則，刪掉 bot 自己發、custom_id **精確**屬於該面板的殘留面板（社群查詢討論串的 `community_lookup:control:refresh` 不會被誤刪）。
- **社群查詢**改用它（runtime 格式本來就相同，資料不用搬）；查詢後的置底改成 `request_bump`（連發合併）。
- **自我介紹**改用它（`key_prefix="intro_panel_"`）：面板頻道 id 從 `config.json` 搬到 `settings/intro_panel_runtime.json`，**不再每次送出表單就重寫整份 `config.json`**。上線後第一次置底因為 runtime 只有訊息 id，會翻找刪掉現在的舊面板，之後就用紀錄。`config.json` 裡的 `intro_panel_channel_id` 已無人讀寫，使用者要刪可自行刪。
- **音樂面板暫不接入**（見點歌機器人待辦）。
- 動工前三份 runtime 檔已備份到 scratchpad（`runtime_backup_0929/`，主機重開會清空）。
- 突變驗證：不比對 custom_id、連發不合併、只有訊息 id 就當完整紀錄、寫檔蓋掉其他欄位，四種都會紅。

**部署與實測（使用者操作）**
- [x] `docker compose restart discord-bot`（09-29 00:28；當時 logger 用 `__name__`，INFO 沒輸出，已改成 `discord_bot`，下次重啟才看得到「週期提醒：接下來 →」）
- [x] `/server_manager` → 設定頻道 →「週期提醒頻道」選 🍼深塔海墟矩陣-代打（09-29 00:29；身份組 `1554168140441718885`、面板已發出）
- [x] 按「訂閱」（身份組成員數 1）
- [ ] 容器內 `python -m test.integration.it_periodic_reminder reset sea`：**已發送**（09-29）；待使用者確認手機沒跳通知、頻道有紅點
- [ ] 容器內 `python -m test.integration.it_periodic_reminder ending tower <只有管理員看得到的頻道id>`：確認手機有跳通知
- [ ] 10/11 20:00 第一則正式提醒：確認有發、面板被頂到最下面
- [ ] **再重啟一次**（置底收斂＋log 修正要重啟才生效）後確認：
  - 在提醒頻道講一句話 → 面板立即移到最下面
  - 送出一次自介 → 舊的自介面板被刪、新面板在最下面，而且 `settings/intro_panel_runtime.json` 多了 `intro_panel_channel_id`、`config.json` 沒被改動
  - 做一次社群查詢 → 查詢面板照常置底

---

## 新成員歡迎訊息：接手 ProBot（歸檔 2026-10-02，原 2026-09-28）

> 已上線：9/28 15:04 綁定「歡迎」頻道，10/01 07:59 首次實發；使用者 10-02 確認 ProBot 的歡迎功能早就關了，沒有剩下的待辦。

<!-- @meta
id: member-welcome-message
type: STATE
status: confirmed
last_confirmed: 2026-09-28
affects: settings/channel_registry.py, services/community/member_welcome.py（新）, discord_bot.py, test/test_member_welcome.py（新）
-->

**需求**：ProBot 的加入歡迎訊息疑似失效，改由自家 bot 在歡迎頻道發同樣內容（@新成員 + 伺服器名 + 引導去規範頻道）。

**機制一句話**：`on_member_join` 事件 → 讀 `welcome_channel_id` → 發一則純文字。

**改動清單（全部 additive，不動既有流程）**
1. `channel_registry.py`：`register_channel("歡迎頻道", text, "welcome_channel_id")`，沿用 `/server_manager` 綁頻道 UI，未設定＝功能靜默
2. 新檔 `services/community/member_welcome.py`：文案純函式 + 讀頻道發送；略過 bot 帳號
3. `discord_bot.py` 加 `@bot.event on_member_join`，只委派給上面的 service（沿用本專案「gateway 事件集中在 discord_bot.py、邏輯放 services」慣例；全專案原本無人監聽此事件，不會覆蓋）
4. 規範頻道連結優先用 Discord 內建 `guild.rules_channel`（社群伺服器設定），不另開 config key
5. 文案純函式補單元測試

**已排除**：掛在 `ManagementCommands` 當 Cog listener——功能可行，但該檔是指令集中地，放事件會亂了分工（使用者 2026-09-28 指正）。

**已知前提**：`intents.members = True` 已開（bot 能連上即代表開發者後台也已開）。

**已定案（使用者 2026-09-28 確認）**：規範頻道已設為伺服器「規則頻道」→ 用 `guild.rules_channel`；文案先照抄 ProBot；上線後關掉 ProBot 歡迎功能。

**實作細節**：只允許 @ 新成員本人（`AllowedMentions`）；bot 帳號、未綁頻道、頻道不在本伺服器、非文字頻道、發送失敗都靜默略過不拋例外。
測試 `test_member_welcome.py` 8 項，已併入啟動 gate（全套 526 項綠）。

**待驗證（使用者執行）**
- [ ] 重啟 discord-bot
- [ ] `/server_manager` → 設定頻道 → 「歡迎頻道」選目標頻道；確認 bot 在該頻道有「傳送訊息」權限
- [ ] 關掉 ProBot 歡迎（ProBot 後台 Welcome & Goodbye 關閉，或在歡迎頻道拒絕 ProBot 的「傳送訊息」權限）
- [ ] 找人（或小號）加入一次，確認文案、@ 與規範頻道連結正確

---

## 活動自動發布：連結指向錯誤 + 重複建活動（歸檔 2026-10-02，原 2026-09-22）

> **2026-10-02 結案**（使用者決定）：修正上線 10 天沒有問題，9/30 有就地升級既有活動的紀錄；9/22 對抗性複查剩的兩個面向（`article_monitor` 轉發 embed、`event_time_parser` 解析）不補做，之後出問題再查。「下一篇含活動的公告確認遷移摘要」不再追。結案時仍成立的殘留風險（已知、刻意不處理）：
>
> - 活動段落片段與轉發訊息內容來自兩套解析（`strip_html` vs `html2text`），文字可能略有差異
> - 超過 4,000 字的公告（全庫 23 篇）仍只轉發前 1,200 字，其餘靠官網連結
> - `created_events` 無清理機制，已結束的列會持續累積（線上 32 筆中 23 筆已是孤兒）
> - 使用者手動刪掉的活動不會被**自動來源**重建（墓碑）；`/resend_article` 是唯一解得開的入口
>   （人明確要求重抓才算數）。活動若還在伺服器上就解墓碑走升級，已被刪掉才整列丟掉重建
> - 官方改期到完全不重疊的新區間時不自動合併，只 log warning（理由見上）

<!-- @meta
id: event-announce-link-and-dedup-fix
type: STATE
status: confirmed
last_confirmed: 2026-09-30
depends_on: event-announce-auto-schedule
affects: services/events/event_scheduler.py, services/events/event_time_parser.py, services/relay/article_monitor.py, services/state_db.py
-->

> 原始功能區塊已於 2026-08-18 歸檔至 `TODO-completed.md`（id: `event-announce-auto-schedule`）。
> 本區塊是它重開的修正輪，只記這次改了什麼與為什麼。

### 症狀

活動 `1539556072082112604`「[群聲共振模擬域]戰鬥活動」描述裡的「公告出處」
指向訊息 `1539556070119440388`，點進去那則訊息**完全沒有提到這個活動**。

### 根因：錯在文章轉發，不在活動偵測

| 層 | 位置 | 問題 |
|---|---|---|
| ① 兩邊讀的不是同一份內容 | `article_monitor.py` | 活動偵測讀 `article_content_full`（article 5340＝8,454 字）；轉發 embed 讀 `article_desc` |
| ② fallback 變成唯一路徑 | 舊 `article_monitor.py:174` | `article_desc` **全庫 532 篇皆為空字串** → `parsed_content[:300]` 這條「沒摘要時的預覽」成為唯一路徑，8,454 字只發出 303 字。下方那行「限制 4000 字」的保護從上線到現在**一次都沒觸發過** |
| ③ 訊息是死路 | 舊 `article_monitor.py:197` | `discord.Embed(...)` 沒有 `url=`（`fb_monitor.py:145` 有），送出時也沒有 `content=`，點進去無法跳回官網全文 |

5340 的 6 個活動名分別在轉換後全文的第 1347 / 1524 / 1632 / 1755 / 1899 / 2010 字，**全部 > 300**。
全庫量化：315 個 article 來源活動中，**100 個（31.7%）**的活動名在轉發訊息可見文字裡找不到。

### 同時修掉：同一活動被建兩次

`normalize_title` 的核心名只認 `「」『』` 與 `【】[]`，不認半形 `<>`：

```
5340 匯總帖    → fp = 群聲共振模擬域|202608221000|202609291159
5351 專屬公告  → fp = 活動預告<群聲共振模擬域>戰鬥活動即將開啟|202608221000|202609291159
```

起訖相同、指紋不同 → 去重擋不住 → 線上 `…604` 與 `…681` 兩個活動同時存在。
全庫 14 篇「活動預告」型公告中，用 `「」` 的 3 篇擋得住、用 `<>` 的 11 篇全部會重複。

### 改了什麼

| 檔案 | 改動 |
|---|---|
| `article_monitor.py` | 截斷 300 → `EMBED_DESC_LIMIT = 1200`；截斷時附「閱讀完整公告」連結；`embed` 補 `url=`；移除「📝 內容預覽」欄位（條件是 `<=1000` 字，等於文章越長看到越少）；新增 `official_article_url()` 為官網網址的唯一來源 |
| `event_time_parser.py` | `normalize_title` 核心名加入半形 `<>`；新增 `_extract_body()` 抽活動段落片段；`ParsedEvent` 加 `body` |
| `event_scheduler.py` | 活動描述嵌片段 + 公告出處/官方原文雙連結（先保連結再給片段）；**升級既有活動**（封面＋描述）；同名+重疊視為改期；`_SCHEDULE_LOCK` 序列化；`_migrate_fingerprints_once` 指紋遷移；建立成功但寫 DB 失敗分開報；四種靜默丟棄補 log |
| `state_db.py` | `created_events` 加 `core_name` / `has_image` / `body` / `superseded_by` / `user_deleted` / `deleted_at` / `updated_at` + index；新增 `find_overlapping_event` / `find_same_name_events` / `list_created_events` / `update_created_event` / `mark_created_event_deleted` / `clear_event_tombstone` / `delete_created_event`；**移除 `is_event_created`**（已無呼叫者，留著會讓人繞過升級路徑）。**只留「有人讀」的欄位**——一度加過 `quality` 與 `message_url`，兩者寫了從來沒人讀，而存著一個「品質分」正是下一個人會拿來當閘門的誘餌（就是這次修掉的 bug），連同 `content_quality()` 與 `from_umbrella` 一起刪 |
| 測試 | 新增 `test_event_upgrade.py`（21，副作用層原本零覆蓋）、`test_article_embed.py`（8）；`test_shared_conventions.py` 加「官方公告原文網址」AST 守衛 |

### 支撐決策的實測數據（2026-09-22）

- `article_menus.article_desc`：**532 / 532 皆為空字串**
- FB 貼文 **832 / 834（99.8%）有圖**，平均 2.7 張；article 的 `article_cover` /
  `content_cover` / `suggest_cover` **全庫皆空**，只能從內文抓第一張 `<img>`（494/532 有）
- 公告字數：p50 = 400、p75 = 565、p90 = 2558、p99 = 9436。切 1200 有 **85.2%** 完整發出；
  拉到 2000 / 4000 只多 2.6% / 10.5%，卻會讓版本說明帖變成 40~50 行
- 括號用法：`<>` 出現在 38 個標題（內容都是活動名）；**`《》` 出現在 472 個標題，
  其中 328 個包的是遊戲名「鳴潮」** → 收進來會把 328 個公告壓成同一個核心名，故不收；
  `〈〉` 與全形 `＜＞` 在 1366 個標題中一次都沒出現
- 跨來源指紋對得上的有 **45 組**（升級路徑會實際被觸發）。最典型的就是被浪費掉的這 4 次：

  | 活動 | 先到（無圖） | 後到（有圖） | 相隔 |
  |---|---|---|---:|
  | 第二索拉・詭影迷蹤 | article 5340 匯總帖 8/19 | fb 774（2 張圖） | 7 天 |
  | 清弦紀流年 | article 5340 匯總帖 8/19 | fb 793（2 張圖） | 14 天 |
  | 若夢仍有回聲 | article 5340 匯總帖 8/19 | fb 810（1 張圖） | 21 天 |
  | 潮汐覓聞 | article 5340 匯總帖 8/19 | fb 822（1 張圖） | 28 天 |

- 「同名+重疊」全庫會合併 66 組，其中**只有 1 組**（article 995「往歲乘霄醒驚蟄」1.1版本內容說明，
  3 個活動標題都抽不出來而一起退用貼文標題）是同一則公告內部同名不同區間 →
  已用 `exclude_source` 排除，並補迴歸測試

### 指紋遷移（部署時會自動跑一次）

`normalize_title` 一改，既有指紋全部失配 → 去重表等同失效 → **線上活動會整批重建**。
故 `maybe_schedule_events` 在鎖內先跑 `_migrate_fingerprints_once`（冪等、程序內只一次；
失敗則本次不建任何活動並於下篇公告重試）。

用 `sent_articles.db` 的副本演練（未動原始檔）：

```
32 筆進、32 筆出（不掉筆）
指紋更新 6 筆（2 筆是 <> 修正，4 筆是 2026-07 舊 code 留下的錯誤指紋）
偵測到重複活動 1 組 → 記 ERROR、兩列都保留，不自動刪
core_name 全數回填；再跑一次完全冪等
```

### 升級既有活動：為什麼是四軸，而不是一個品質分

> **這段是防止「被簡化回去」的記錄。** 實作中途真的寫過「品質總分變高
> 就換描述與封面」的版本，對抗性複查後確認不可行，三個症狀都真實重現：
>
> | 用單一總分當閘門 | 實際後果 |
> |---|---|
> | 改期時品質分通常沒變 → 走不進換描述的分支 | Discord 上時間改了，描述第一行的「活動時間：…」還是舊的，**活動頁自相矛盾** |
> | 「非匯總帖 +1」當內容品質的代理指標 | 專屬帖開頭常是劇情導言、匯總帖寫的才是玩法與獎勵 → 描述反而**變短**（實測 370→118 字） |
> | 分數沒變高就整筆 return | 全庫 **14.6%** 的公告一個字都沒更新 |
>
> 根因是「封面／描述／時間／名稱」本來就是四件獨立的事，綁在同一個純量上必然出事。
> 那個分數連同 `content_quality()` 與 `from_umbrella` 都已刪除 —— 留著一個沒人讀的
> 「品質分」就是下一個人拿來當閘門的誘餌。log 直接印實際訊號（封面有無、片段字數）。

**四軸各自判斷，互不綁定**：

1. **時間**：起訖與 DB 不同 → 同步。**已開始的活動只改 `end_time`** —— `p.start` 是
   clamp 過的 `max(now+5min, logical_start)`，送出去會把進行中的活動推到 5 分鐘後開始；
   且 discord.py 把 start/end 併進同一個 PATCH，Discord 一拒絕連延長的 end 也一起失效。
2. **描述**：新片段 ≥ 既有 +40 字才換；**改期時一律重建**（時間就寫在第一行），
   但此時若新片段沒比較好就沿用既有片段，不為了修時間而讓描述變差。
3. **封面**：既有沒圖才補；既有已有圖不動（換圖對使用者沒價值，只會反覆重傳）。
   判定移到 `_fetch_event` 之後，不再白下載（實測單張 0.8~1.0 MB）。
0. **前置閘**：既有活動狀態是 `completed`／`canceled` 就**完全不碰**。Discord 會拒絕編輯
   已結束的活動，沒有這道閘，使用者手動提早結束一個活動之後，每來一篇同活動的新公告
   就白試一次編輯、白抓一次封面、白記一行 warning。閘門放在下載封面之前。
   （去重不受影響：那一列從未被刪，所以結束的活動不會被重建；而未來同名活動的新檔期
   因為指紋帶著時間區間、同名合併只認重疊，一樣照建 —— `聲弦滌蕩` 線上就有 3 檔共存。）
4. **名稱**：既有是預告型標題（`活動預告`／`即將開啟`…）而新來源不是 → 改名。
   收 `<>` 進核心名之後預告帖與正式公告會合併，不改名的話活動開跑一個月還寫「即將開啟」。

**另外五項保護**：

| 問題 | 做法 |
|---|---|
| 使用者從 Discord 刪掉活動 → 若 `on_scheduled_event_delete` **實體刪列**，7~28 天後另一來源會把它復活 | `mark_created_event_deleted` 改成**立墓碑**（`user_deleted` / `deleted_at`）；兩條比對路徑仍撈得到，撈到就什麼都不做 |
| `_fetch_event` 把所有例外當成「活動被刪」，一次 503 ＝ 該來源的封面／描述永久遺失（來源已 `mark_content_as_sent`） | 只有 `discord.NotFound` 回 None，其餘往外拋給每筆各自的 try |
| 重疊比對若排除「整則公告」→ `/resend_article` 重送改期公告時對不到自己那一列，建出第二個活動 | 改成排除「**本輪已配對的指紋**」(`exclude_fingerprints`)；同一則公告內部仍不互相吃掉 |
| 遷移碰撞列若留空 `core_name` → 對兩條查詢同時隱形，正本一出事就擋不住重複 | 碰撞列照樣回填 `core_name`，另標 `superseded_by` 指向正本；查詢排序正本優先 |
| 遷移單列失敗仍標記完成 | 有任何失敗就不標記、拋出，本次不建任何活動，下一篇公告重試 |

**刻意不做**：官方改期到**完全不重疊**的新區間時不自動合併 —— 不重疊也可能只是同一活動的
下一個檔期（`[聲弦滌蕩]` 每隔幾週一檔），自動併會把正常的循環活動吃掉，而歷史資料上
「改期」一次都沒出現過。改成**偵測到同名活動仍在進行／未開始就 log warning**。

**驗證**：397 測試全過（新增 40 條，含副作用層原本零覆蓋的部分）；以 `sent_articles.db`
副本演練遷移：32 列不掉、`core_name` 空列 0、分身正確標記、重疊查詢回正本、墓碑擋得住復活。

### 2026-09-30 追加：已處理過的重複不再每次報 ERROR（已上線・`f7d4a14`）

**機制（一句話）**：指紋遷移看到「這一列先前已經標成分身」就只計數、不再報 ERROR；第一次發現的分身若活動已結束，降成 INFO。

- **為什麼**：9/22 修正前留下的那一組「群聲共振模擬域」（`…604` 正本、`…681` 分身），9/22 之後每次重啟的遷移都再報一次 ERROR（累計 26 次）。它早就標好 `superseded_by`、擋得住重複，兩個活動也都在 9/29 11:59 結束——重複報只會把真正的錯誤淹沒。
- **改了什麼**（[event_scheduler.py](src/services/events/event_scheduler.py) `_migrate_fingerprints_once`）：
  - 分身列 `superseded_by` 已指向新指紋 → 算「先前已標記」，不寫 ERROR，也不重寫這一列（只在 `core_name` 不對時回填）。
  - 新發現的分身照樣標記；活動已結束（`end_utc8` 早於現在）→ INFO「只標記分身、不需處理」；還沒結束 → 照舊 ERROR 請人手動刪。
  - 摘要改成「新發現重複活動 N 組，先前已標記 M 組」。`now` 參數只給測試固定時間用。
- **測試**（[test_event_upgrade.py](src/test/test_event_upgrade.py)）：已知分身只在第一次報 ERROR、第二次不報也不重寫；已結束活動的新分身有標記但不報 ERROR；原本的相撞測試固定在活動結束前（仍報 ERROR）。三種故意改壞都會紅。
- **驗證時機**：遷移不在開機時跑，是第一篇含活動的公告進來、建立活動前才跑一次；預期 log「新發現重複活動 0 組，先前已標記 1 組」、沒有 ERROR。

### 待辦 / 下一步

- [ ] 對抗性複查還有 2 個面向（embed／parser）與驗證階段未跑完，結果出來要再過一次
- [x] `docker compose restart discord-bot`（9/22 之後已多次重啟）
- [x] 看 log 的「指紋遷移完成」與「⚠️ 指紋遷移發現重複活動」兩行（9/30 10:08 查：共 36 列、更新 0 列、重複 1 組、失敗 0 列；重複的就是修正前留下的那一組）
- [x] ~~人工刪掉重複活動~~ 不需要：`1539556072082112604` 與 `1539937681176272916` 都已在 9/29 11:59 結束，第二筆資料庫已標 `superseded_by`；遷移重複報 ERROR 的問題由上面的追加修正處理
- [x] 後到的來源就地升級、不另建（9/30 10:08 log：「♻️ 已升級既有活動：團團勇者大亂鬥」；9/22 之後遷移沒有發現新的重複）
- [ ] 下一篇含活動的公告進來時，確認遷移摘要是「新發現 0 組，先前已標記 1 組」、沒有 ERROR

### 殘留風險（已知未做）

- 活動段落片段與轉發訊息內容來自兩套解析（`strip_html` vs `html2text`），文字可能略有差異
- 超過 4,000 字的公告（全庫 23 篇）仍只轉發前 1,200 字，其餘靠官網連結
- `created_events` 無清理機制，已結束的列會持續累積（線上 32 筆中 23 筆已是孤兒）
- 使用者手動刪掉的活動不會被**自動來源**重建（墓碑）；`/resend_article` 是唯一解得開的入口
  （人明確要求重抓才算數）。活動若還在伺服器上就解墓碑走升級，已被刪掉才整列丟掉重建
- 官方改期到完全不重疊的新區間時不自動合併，只 log warning（理由見上）

---

## Telegram 漏收事件自動補掃與相簿漏圖（歸檔 2026-10-02，原 2026-08-02）

<!-- @meta
id: telegram-catchup-sweep
type: STATE
status: confirmed
depends_on: telegram-multi-source
affects: telegram-relay
last_confirmed: 2026-09-28
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
- **序列化鎖**：即時事件 / 補掃 / refetch 三條路徑共用一把 `process_lock`，避免同一則訊息並行處理造成重複下載媒體。**（2026-09-28 已改為單則訊息鎖，全域鎖造成相簿漏圖，見文末追加段）**
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

### 追加（2026-09-28）：全域 `process_lock` 讓相簿漏圖 → 改單則訊息鎖

**症狀**：使用者回報 GameData #3223 相簿「後面一堆圖片漏發」——8 張只發出 1 張；同時段 #3213 8 張發 1 張、#3231 7 張發 6 張。

**機制（一句話）**：全域鎖把「同時到的相簿各張」變成逐張排隊，relay 的 0.5 秒到齊判斷等不到整組就先發，晚到的組員走「交由首則處理」被丟掉。

**查證（非推測）**：
- **加鎖原因**（`fbd2d3c` commit 訊息）：補掃上線後，即時事件 / 補掃 / refetch 可能同時處理**同一則**訊息 → 加鎖防重複下載。但實作成**一把全域鎖**，連「不同訊息」也一起序列化。
- **Telethon 預設並行派發**：1.43.2 `sequential_updates=False`，每個 update 各開一個 task（容器內已讀 `telethon/client/updates.py:284` 原始碼）→ 相簿各張本來同時處理；唯一讓它排隊的就是這把鎖。
- **時間點吻合**：相簿組員寫入 DB 的間隔，7/31 以前 p90 **0.03 秒**（7/31 兩張間隔 0.001 秒）；commit 當天 8/02 11:01 之後第一組相簿（18:07）起即變成逐張，9 月中位數 **0.76 秒**、p90 **2 秒**、最大 12 秒。
- **影響量**（bot log `media group 合併 ... media_count=N` 對照 DB 該組實際媒體數）：7 月 70 組中 9 組不足（21 張）；**8/02 起 191 組中 77 組不足（237 張）**；9/28 單日 40 組中 21 組（82 張）。

**修法**：新增 [message_lock.py](src/telegram_scraper/message_lock.py)（`KeyedLock` + `message_lock_key`），[runner.py](src/telegram_scraper/runner.py) 三條路徑改用 `message_locks.hold((chat_id, message_id))`：**同一則訊息仍互斥（保留原本加鎖的目的），不同訊息恢復並行**。key 取 Telethon `Message.chat_id`（marked id，容器內實測 = DB `telegram_chat_id` 格式 `-100…`），三條路徑拿到的都是 Message 物件，key 一致。無人持有的 key 即回收，dict 不會長大。

**已驗證**：容器內 `unittest discover` **534 測試全過**（新增 [test_telegram_message_lock.py](src/test/test_telegram_message_lock.py) 8 條：同 key 互斥、相簿 8 張可同時進入、例外／取消後不漏回收、跨頻道同 id 不撞 key）；**反向驗證**：把 `hold` 換成全域鎖 → 相簿測試逾時失敗。`py_compile`（scraper 容器 py3.12）PASS。

**relay 端同輪一起修（使用者拍板「一起修正」）**——加鎖前 7 月仍約 1 成相簿缺圖，relay 自己有三個洞：只數訊息列不管媒體列寫入沒、晚到組員走「交由首則處理」直接丟棄（重啟 reconcile 也一樣跳過 → 永久漏發）、已發送標記用的是合併**前**的組員清單（實送了卻沒標、沒送卻標了都有）。
**機制（一句話）**：不再「只有首則能發」，改成**哪個組員先到就由它收整組**，等到齊才發；發完還有沒送的，以「（補圖）」再發一則。改動全在 [telegram_relay_service.py](src/services/relay/telegram_relay_service.py)：
- **到齊判斷** `_wait_group_settled`：每個組員都有媒體列（`get_group_member_states`，`has_media=false` 視為就緒）**且** 3 秒內沒有新組員／新就緒；湊滿 10 則（Telegram 相簿上限）且都就緒就不等；上限 60 秒，逾時先發已就緒的。
- **同組同時只有一個收集者** `_process_group_member`：收集中到的組員只登記 `_dirty_groups` 就返回（不佔處理槽空等），收集者發完回頭複查；「檢查 dirty → 移出 active」之間無 await，不會有組員卡在空檔。
- **各頻道只發還沒送的** `_group_pending_for_channel`：組內已有人送過 → 標題加「（補圖）」；**補圖時效 12 小時**（`_GROUP_FOLLOWUP_MAX_AGE`，以該組首次送出時間算）——重啟時 reconcile 會把全部沒 delivery 記錄的組員（現約 460 筆、158 組舊相簿）重新排入，沒有時效會把舊缺圖一口氣倒進頻道。發之前先快篩，沒有該發的（或全過時效）就不等安靜期。
- 只標記**實際合併送出**的組員；重送模式（replay）不看 delivery_state、以 processed 集合防同輪重送。
- `render()` 加 `title_suffix` 參數；`get_grouped_message_pks` 移除（改用 `get_group_member_states` + `get_delivered_at`）。

**已驗證（relay）**：新增 [test_telegram_relay_media_group.py](src/test/test_telegram_relay_media_group.py) 11 條（逐則寫入整組一次送、媒體未寫入要等、收集中到的組員不阻塞不重送、發送中到的以補圖送、發完才到的補圖不丟、逾時先發其餘補圖、過時效不發且不空等、全送過直接結束、重送模式只送一次、非首則觸發保留說明文字、單則訊息不變）；**反向驗證**：同樣的測試套舊版 relay → 關鍵 3 條全失敗。全套 **545 測試全過**。
**坑**：relay 測試的 logger 會寫進正式 `logs/discord_bot.log`——第一次跑時用了真實 grouped_id/pk，log 在 **15:50:39~41** 留下幾行假的「media group 合併 grouped_id=14324643361830837 …」（含一行 pks=[13916…13923] media_count=8，**不是真的送出**）。已改用假 id；日後用 log 還原送出狀態時要排除這幾行（校正腳本以「合併後 60 秒內有 delivery 記錄」過濾）。

**今天漏的圖補發（使用者拍板「補圖片」）**：
- **做法**：不另寫發送腳本，走新版 relay 的正式路徑——重啟時 reconcile 排入未送組員 → 以「（補圖）」送出。前提是先把今天相簿的 delivery_state 校正成「實際送出」：以 bot log 合併紀錄為準（pks 裡媒體寫入最早的 `media_count` 則＝實送），**補記** 實送沒標的（否則會被當晚到組員重送）、**撤記** 標了沒送的（否則永遠不補）。
- **校正腳本**：scratchpad `fix_album_delivery_state.py`（`docker exec -i telegram-scraper python - [--apply] < …`；bot 停機時也能跑）。09-28 15:55 dry-run：39 組、補記 57 筆、撤記 9 筆、待補發 **87 張**、無法判定 0。
- **唯讀預演**（新版 relay + 真 DB + 校正計畫套在記憶體、發送換成記錄器）：reconcile 排入 460 筆 → **23 則補圖、共 87 張**，其餘 0 則送出（舊相簿全被時效擋下）。
- **15:57 已套用**（備份 scratchpad `delivery_state_backup_20260928_155656.sql`，4108 列 → 4156 列＝+57−9；套用後複跑＝23 組、0 筆待校正、87 張待補發）。
- **順序必須是**：停 bot → 備份 `telegram_relay_delivery_state` → `--apply` → 啟動 bot。舊版 bot 在跑時每來一組相簿就再產生不一致的標記，所以不能先套用再重啟。**需在 09-28 22:15 前啟動**（最早一組缺圖相簿首次送出於 10:15:47，超過 12 小時時效就不補）。

**已知殘留（未處理）**：
1. 並行恢復後，兩則**不同**訊息若同時帶同一個尚未下載的自訂表情，會同時寫同一個 `emoji_{doc_id}` 檔——8/02 以前本來就如此，機率低，未加鎖。
2. History 啟動掃描本來就沒上鎖，維持原狀。
3. 8/02~9/27 的舊缺圖（約 155 張）不補——超過補圖時效，使用者只要求補今天。
4. 補圖訊息的說明文字：組員多半沒有文字，補圖只有標題「來源（補圖）」與 footer `msg #… · db#…` 指向原相簿。

**部署與補發結果（09-28）**：scraper 15:56 重啟、bot 15:58 啟動；reconcile 排入 460 筆 → **23 則補圖、87 張全數送出**（log `followup=True`；使用者確認「補圖沒問題」）。其中 GameData #3198、#3201 是 146MB 影片，two-pass 壓縮到 99.9MB 花約 8 分鐘，16:06/16:07 才送出——壓縮期間佔住處理槽，屬既有行為。另注意 bot 容器啟動時會跑單元測試，log 裡 `grouped_id=990000000000001` 的合併／逾時紀錄都是測試。

**已 commit。下一步**：重啟後尚無新相簿進來，下一組相簿確認 bot log `media_count` 等於組員數、DB 組員 `created_at` 間隔回到 0.0x 秒。

**仍可能缺圖的情境（非本次 bug，未處理）**：① 相簿已送一部分、缺的部分超過 12 小時才進 DB（例如 scraper 停機半天）→ 依設計不補；② scraper 下載失敗 → 媒體沒進 DB，沒人會發（有媒體卻無媒體列：6~9 月每月 1~7 則，幾乎不在相簿裡）；③ 影片壓縮後仍超過 Discord 上限 → 略過該檔但照樣標記已送（log 歷來共 5 次 `附件壓縮失敗或仍超限`）；④ Discord 發送失敗 → 不標記，要等下次 bot 重啟 reconcile 才重試。

---

## 專案 AI 架構總覽（Ollama 時代）（歸檔 2026-10-02，原 2026-03-31）

<!-- @meta
id: project-architecture
type: STATE
status: confirmed
last_confirmed: 2026-03-31
-->

- Bot 入口：`src/discord_bot.py`
- LLM 指令：`src/commands/llm_commands.py`（`/askai`）
- LLM 服務：`src/services/llm_service.py`（Ollama chat API 封裝）
- 檢索核心：`src/llm/retrievers/context_retriever.py`
- Persona 卡片：`src/llm/persona/persona_card_builder.py`
- Prompt 組裝：`src/llm/prompt/prompt_builder.py`；/askai 除錯 log 組裝：`src/llm/logger_factory.py`
- Profile/Impression 寫入 RAG：
  - 服務層：`src/services/community/intro_profile_service.py`
  - pgvector 介接層：`src/llm/storage/member_profile_store.py`（原 `intro_rag_port.py`，`b80c509` 改名）
- Impression 審核：`src/services/community/impression_moderation_service.py`
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

## Context / Prompt 優化專區（歸檔 2026-10-02，原 2026-04-19）

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
| `src/services/llm_service.py` | generate_reply（prompt bundle 組裝已移到 `src/llm/prompt/prompt_builder.py`） |
| `src/commands/llm_commands.py` | context 分離、asker_profile 組裝、撞名偵測 |
| `src/llm/persona/persona_card_builder.py` | 自然語言化、`person_id` 保留 |
| `src/llm/retrievers/context_retriever.py` | discord_context item（含 `display_name`）、vector index cache |
| `src/llm/storage/store_chat.py` | buffer 批次寫入、SafeOllamaEmbedding |
| `src/llm/persona/personality_extractor.py` | 人格萃取 pipeline |
| `src/llm/storage/member_profile_store.py`（原 `intro_rag_port.py`） | `index_auto_personality`、`_ainsert`、singleton |
| `src/settings/prompts/askai_system_prompt.txt` | 人設 prompt（規則）|
| `src/settings/prompts/persona_identity.txt` | 人設身份核心（琇紫） |
| `src/settings/prompts/persona_examples.txt` | few-shot 風格示範對照 |
| `src/settings/prompts/llm_context_safety_rules.json` | untrusted intro + asker_profile 白名單 |
| `src/sys_settings/llm_settings.py` | prompt 三檔路徑設定 |
| `src/commands/llm_commands.py:load_system_prompt` | 三檔拼接載入（identity → main → examples）|

---

## AI 偶爾插話（功能二）與自然插話重構（歸檔 2026-10-02，原 2026-06-21／2026-08-09）

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
- [x] 模型協調（取代「優先序佇列」的最小落地）：[lemonade_gate.py](src/llm/client/lemonade_gate.py) 加 `stream_busy()` + `note_foreground_activity()` / `foreground_recently_active(grace)`；/askai 在 `_handle_askai_request` 起點與 worker `finally` 兩處標 foreground → 背景插話於 grace 窗口內讓位。**注意：尚未做真正的優先序佇列**，只做「foreground 活躍時背景讓位 + 共用 `stream_exclusive` 序列化」；directed(@) 仍會在 /askai 窗口觸發 swap（罕見、可接受）。
- [x] 新檔 [src/llm/ambient/ambient_reply.py](src/llm/ambient/ambient_reply.py)：硬過濾 + 冷卻/上限 + foreground 讓位 + 機率 + @/reply 必回 + 12B 生成（`generate_reply(model=ambient_model)`，沉默 sentinel 不發送）。**Phase A 範圍調整**：(a) 判斷與生成**合為一次 12B 呼叫**（prompt 允許回 `[PASS]`＝沉默），未做獨立 judge；(b) **react 檔次延後**（Phase A 只有 回/沉默）；(c) **檔1 persona card 改到 Phase B**，Phase A 記憶＝近期 `channel.history` 短期脈絡（零 pgvector）。
- [x] [discord_bot.py](src/discord_bot.py) `on_message` 加 `asyncio.create_task(maybe_ambient_reply(bot, message))`。
- [x] 新 prompt [ambient_reply_prompt.txt](src/settings/prompts/ambient_reply_prompt.txt)（純「插話行為」規則、`[PASS]` 沉默）；**system 疊用共用身份 `persona_identity.txt`（琇紫）→ 插話與 /askai 同一角色**。注意：這是 bot 自己的「身份 prompt」；「認得別人是誰」的 per-user persona card 仍在 Phase B。
- **靜態檢查**：全檔 py_compile PASS；JSON valid；lemonade_gate 協調函式 standalone 測試 PASS（本機無 discord 套件，完整載入須在 docker）。
- **待 docker 驗證**：`docker compose restart discord-bot` → `/setch` 設「AI 插話頻道」→ 該頻道閒聊看是否偶爾插話、@ 必回、非白名單靜默、/askai 進行時讓位。
- **可調手感（config 起始值）**：base_probability、cooldown_seconds、hourly_cap、askai_grace_seconds。

#### B — 認得人（persona card 召回；檔1 提前到此）
- [x] 三項已實作（`ambient_reply._build_persona_context` 走 `retrieve_rag_context_sync`，`_PERSONA_CACHE` 依頻道短 TTL 快取）；原細項已歸檔（2026-09-28）。
- **驗收**：群裡有 persona card 的人講話，琇紫接話帶得出對方調性；沒卡的人也不會卡住（degrade 成只有對話脈絡）。
- **延後（非 v1 必要）**：`retrieve_discord_context` 泛化吃 channel 的 hybrid 長期對話召回——觸碰 /askai 核心、風險高，等 B 的 persona 召回不夠用再做。

#### C — 偏好事實 preference_fact（檔3：自我進化、全自動、自他分流）
> 政策（2026-06-21 定案）：**只記「本人講自己」的中性偏好；敏感(健康/感情/家庭/財務)一律自動丟、不存；他人評他人/紅線自動丟。多次提到才升等。全自動、零審核佇列。**

**共享接口（2026-06-21 建）**：[`MemoryService`](src/services/memory_service.py)（門面，單例）——任何功能只呼叫它、不碰底層：`recall / list_facts / extract / remember / observe / forget / format_recall`。底層委派 `intro_rag_port`(儲存) + `preference_extractor`(抽取/升等)。未來 /askai、功能一、/remember、管理面板都走這個。

- [x] **C-1 儲存層**：`PgVectorIntroRAGPort.index_preference_fact / list_preference_facts / delete_preference_fact`；`profile_kind="preference_fact"`，metadata：`{author_id, fact, fact_key, category, confidence, status, mention_count, first_seen, last_seen}`。doc_id 含 fact_key 雜湊 → 同事實 replace 不重複。**隔離已驗證**：persona 讀取器 SQL 白名單只撈 intro/auto/impression，preference_fact 不會混進 /askai/Phase B。
- [x] **C-2 抽取+守門**：[preference_extractor.py](src/llm/persona/preference_extractor.py) `extract_preferences`（12B、[守門 prompt](src/settings/prompts/preference_extractor_prompt.txt)：自他分流/敏感丟/紅線丟、輸出 JSON）+ `_parse_facts`（容錯）。
- [x] **C-2 corroboration**：`ingest_preferences`——confidence 濾（<0.6 丟）→ 批內去重 → 依作者讀既有 → 命中 `mention_count++`（≥2 升 trusted）否則新建 tentative。
- [x] **C-3 串接**：[ambient_memory.py](src/llm/ambient/ambient_memory.py)——`enqueue_for_memory`(插話頻道每則收緩衝) + `maybe_flush`(背景排程、**閒置才跑 12B**) + `recall_lines`(召回 trusted 注入 persona_context)；`ambient_reply` 與 `discord_bot` on_ready(每 180s 檢查) 已接。
- [ ] **C-4 自我進化迴圈**（閒置批次）：consolidation（合併重複、衝突取新記「以前X現在Y」）、decay（久未重提降權/封存）。**未做**。
- [ ] **C-4 隱私公告**：綁定插話頻道時自動置頂 + 改 channel topic。**未做**。
- [ ] **C-4 選配監督面板**（不擋流程）：查/改/刪/禁記；複用 `/personality_extract` UI 模式。**未做**（接口 `MemoryService.list_facts/forget` 已備好）。
- [ ] **觀測 / Debug 面板（使用者要求 2026-06-21，重要）**：使用者**不想用 CLI/log debug**，未來要一個 **Discord 面板** 能看：每次插話的**完整 prompt（含三層 context）**、決策狀態（reply/pass/error）、三層 context 數量（chat/persona/memory）、記憶 flush 狀態、某人記得的偏好。**取代** `ambient_prompt.txt` + grep。可與「記憶監督面板」合併成一個「AI 狀態/觀測面板」。**現況暫用**：`discord_bot.log` 的 `ambient 生成 …chat/persona/memory` 摘要 + [`/logs/ambient_prompt.txt`](src/llm/ambient/ambient_reply.py)（`AmbientChatSettings.debug_log`）；面板做好後轉成資料來源。
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
| `src/llm/ambient/ambient_reply.py`（新） | 硬過濾 + 12B 判斷 + 背景生成 | A |
| `src/discord_bot.py` | `on_message` 加 ambient 分支 | A |
| `src/settings/prompts/ambient_reply_prompt.txt`（新） | 輕量插話人設 | A |
| `src/llm/retrievers/context_retriever.py` | `retrieve_discord_context` 泛化吃 channel | B |
| `src/llm/persona/preference_extractor.py`（與功能一共用） | 12B 傾聽 → 偏好事實抽取（共享層） | C |

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
2. **120s 後裸送、無指向**（[ambient_reply.py:1032](src/llm/ambient/ambient_reply.py#L1032) `channel.send`）→ 多人多主題頻道必然像亂入。**這才是「不知道加入哪個主題」的真正成因**：它選的時候那條線還在，講出來時已經沒了。
3. 第一則就開跑 → 上下文半截；`max_passes_per_burst=3` → 一段 burst 最壞燒 6 分鐘。
4. **A↔B 對線**這種零成本可判的，現在花 120s 讓模型判（prompt 第一關 gate #3）。
5. **講完就跑**：除非被 @，否則不理會別人對它的回應 → 沒有來回感。
6. 等鎖排隊不計入 `pass_timeout_seconds`（[ambient_reply.py:988](src/llm/ambient/ambient_reply.py#L988) 註解已載明）→ 實測 max 901s。

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
- **k-NN（非 LLM 推理）**：`get_text_embedding(近 3 則)` → `ai_interactions` 最近鄰 20 筆 → 「過去語意相近情境下插話被接的比率」當一個特徵。基礎設施（embedding 欄位 + hnsw + [fetch_similar_positive](src/llm/storage/ai_interactions_store.py#L289)）已存在。
- **組合**：負鉤子否決 → `sigmoid(w·features) >= threshold`。**threshold 是唯一旋鈕**（調高＝話少）。
- **權重來源**：logistic regression，樣本＝5602 筆，特徵 <10 個。**係數可讀**＝看得出它為什麼開口，可定期重訓。

**學習標籤換掉**：不用 reaction（負向僅 13 筆，「什麼時候該閉嘴」學不出來），改用「**插話後 5 分鐘內有沒有人接話/回它**」——真人插話成功的定義本來就是話被接下去。此標籤可從 `ai_interactions`(`reply_message_id`+`channel_id`+`ts`) 配合 chat 歷史庫**回溯計算 5602 筆全量**，不必等新資料。

**已知統計限制**：5602 筆全是「已插話」樣本、無反例 → 學到的是「已想插話的情況下什麼形狀會被接」（ranking），不是「該不該插話」（causal）。可接受，但**門檻值必須上線後觀察調整，不能直接從迴歸結果讀出**。

#### 自循環 feedback 盤點（2026-08-09）

| 迴路 | 狀態 | 防護 |
|---|---|---|
| **回音迴圈**（回 bot／自己） | 既有，**不動** | 入口 `message.author.bot` 一律排除（[ambient_reply.py:644](src/llm/ambient/ambient_reply.py#L644)）；chat_history 裡自己的行標「(你自己)」 |
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
| `src/llm/ambient/ambient_reply.py` | debounce 迴圈、鉤子閘接入、`#N` 解析、reply 錨定送出、新鮮度檢查、L4-b |
| `src/llm/ambient/ambient_hooks.py`（新） | 結構鉤子 + regex + k-NN + 迴歸打分 |
| `src/llm/preprocess/chat_line.py` | `#N` 從「僅被回覆過的行」改為每行都給（[chat_line.py:107](src/llm/preprocess/chat_line.py#L107)） |
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
| `src/llm/ambient/ambient_hooks.py`（新） | 結構鉤子 + regex + k-NN + sigmoid 計分 + ε-greedy；失敗一律 fall-open（交給模型 `[PASS]` 把關，不讓鉤子壞掉就整個功能啞掉） |
| `src/llm/ambient/ambient_reply.py` | `note_typing` / `_wait_for_quiet` / `_is_followup_to_bot` / `_parse_line_choice` / `_passes_content_gate`；入口加靜默期與 followup 分派；pass 接鉤子閘、reply 錨定送出 |
| `src/llm/preprocess/chat_line.py` | `_thread_render` 每行給編號 + 回 `{編號: 訊息}`；`fetch_recent_lines` 加 `thread_map` out-param（不改回傳簽章＝不動既有 caller） |
| `src/llm/storage/ai_interactions_store.py` | 加三欄（見下）；`mark_got_reply()`；`fetch_reply_rate_stats()` k-NN |
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
- **資料**（動態、每次不同）→ 只能在 bundle 層：`llm.prompt.prompt_builder.build_prompt_bundle`（原 `llm_service._build_prompt_bundle`）新增
  `situation_signals` 參數與 `<situation_signals>` 區塊 + 一句中性 header。/askai 不傳就不出現
  （與 `style_refs` 同模式）。
- **使用規則**（靜態、要能熱改）→ 放 `ambient_reply_prompt.txt`。**理由是「誰在用」**：
  `recalled_context`/`style_refs` 是 askai+ambient 共用 → 說明放共用的 prompt 組裝（`llm/prompt/prompt_builder.py`）合理；
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
（[emoji_text_utils.py:8](src/llm/preprocess/emoji_text_utils.py#L8) 的註解早就寫明「不動 mention」，一直沒人補）。

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

## ComfyUI 區塊已完成的待辦與正名（歸檔 2026-10-02，原 2026-09-02／2026-09-29）

已完成的 TODO：

- [x] **（2026-09-02 定案）** 圖發到 `ai_diary_channel_id`，與日記同一頻道，不新增設定
- [x] **（2026-09-02 已修）** `discord_bot.py:339` 的 `DIARY_TZ = _tz(_td(hours=8))` 違反
      「全站時區只能用 `APP_TZ`」，因 `_tz`/`_td` 別名溜過 regex 守衛。**兩層都修了**：
      ① 改用 `APP_TZ`；② 該條規則從 regex 改走 **AST**（`_find_hardcoded_utc_offsets`），
      連 import 別名與 `datetime.timezone(...)` 模組屬性形式一起抓，並補 `TimezoneGuardTests`
      五項守住（含「`timedelta(hours=8)` 當時間長度是合法的、不可誤判」）。
      **驗證方式**：暫時還原成舊寫法 → 守衛確實紅在 `discord_bot.py:339` → 復原。
      全專案掃過，這是唯一一處別名繞過（`extract_fingerprint` / `event_time_parser` 是既有合法例外）

已完成的檔名正名（`lemonade_gate` 仍待定，留在交接文件）：

| 現在 | 改成 | import 點 |
|---|---|---|
| `llm/llm_http_client.py` | ✅ 已改為 `llm/client/http_client.py`（套件名複述兩次） | 3 |
| `llm/safe_llm_embedding.py` | ✅ 已改為 `llm/client/embedding_client.py`（"safe" 是形容詞不是分類） | 6 |
| `llm/chat_persistence.py` | ✅ 已改為 `llm/storage/store_chat.py`（它就是 store，卻跟另外 3 個 `*_store` 分家） | 12 |
| `llm/diary_reflection.py` | ✅ 已改為 `llm/ambient/ambient_diary.py`（它 import `ambient_reply`，是 ambient 家族） | 4 |

---

## Ambient 互動紀錄 + 正向學習（自我蒸餾 → 個性演化）（歸檔 2026-10-02）

> 歸檔理由（使用者 10-02 確認）：Part A（`ai_interactions`、反應捕捉）早已上線；Phase 2「LLM 蒸餾成 `learned_style.txt`」被 2026-06-30 style_refs「不走 prose 蒸餾、改召回真句子」的決定取代，程式裡沒有 learned_style，不做。


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

## 指令收斂與管理 Dashboard（改寫前原文，歸檔 2026-10-02，原 2026-08-20）


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

## Discord Bot 管理入口與指令整理 TODO（改寫前原文，歸檔 2026-10-02，原 2026-03-31）


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


---

## Reaction 統計與社群互動玩法（改寫前原文，歸檔 2026-10-02，原 2026-04-18）


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

## 跨來源整合專區（改寫前原文，歸檔 2026-10-02，原 2026-04-07）


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

## 產品能力 TODO（改寫前原文，歸檔 2026-10-02，原 2026-03-31）


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
