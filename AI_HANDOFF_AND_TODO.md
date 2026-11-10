# AI Handoff & TODO

> 【AI 維護義務】讀本檔的 AI，在本輪結束前：
> 1. 本輪有實作異動、共識變更、待決題目新增或變動、或使用者要求時，回寫對應區塊，並更新該區塊 `@meta` 的 status 與 last_confirmed。
> 2. 新共識就地寫進對應主題區塊，不另開新編號；每項事實只存在一個地方。
> 3. 區塊過期就把 status 改成 deprecated；整塊做完就把原文移到 `dev/` 的主題檔。寫法見下方「本檔維護規則」。
> 4. 本輪只閱讀、沒實作、使用者也沒要求回寫，可以不留盤點紀錄。

> 【索引】每個主題區塊開頭有 `@meta` 註解：`id`（跨區塊引用）、`type`（STATE／CONTRACT／DECISION／RISK／TODO）、`status`（confirmed／draft／deprecated／blocked）、`depends_on`／`affects`、`last_confirmed`。只讀與任務相關的區塊即可。

最後盤點紀錄（每輪一行、只留最近約 10 筆；更舊的在 `dev/journal/`，一個月一檔）：
- 2026-11-09 23:4x～11-10 08:4x 觀星者回報週報私訊裡 4 筆交易顯示「# 不明」點不進去：`<#交易對話>` 指向封存的私人 thread；再查出那 4 筆自由市場舊交易的按鈕全部失效（02-17 前的隨機代碼、或更舊的 ✅ 流程），沒有路可以結束。連結改成網址（新共用元件 `channel_url`／`masked_link`＋守衛，收掉 8 處自己拼的網址），留底、開單訊息、擋操作清單、主控台截斷一起改；使用者定 TR-Q95＝C（4 筆直接在資料庫標成 ended，已備份後寫入）、TR-Q96＝A（舊交易不列進沒動靜）。兩個子 agent 唯讀調查、兩個複查（沒有出錯的正確性問題；收了重複的三份退路與伺服器查法、已離開的需求方帶 id、週報截斷留指路、看板一行一條、字裡網址）。完整測試全過、突變全紅；拆成 4 個 commit（`e8e02d3`～`3b18231`，每個中間版本都跑過完整測試）、文件另一個，未推送，要重啟才生效。
- 2026-11-09 連結轉址與 AI 讀預覽：討論定案後實作（bilibili 轉 vxbilibili、轉貼長出預覽才壓原預覽、預檢換服務、暴雷照包、轉貼用回覆、回覆轉貼不算叫它、聊天行加 `[預覽：…]` 與自動轉貼標記），新檔 `services/relay/link_repost.py`、`test/test_link_fix.py`，守衛加兩條；實作時發現 fixupx 的影片在 Mastodon 相容 API，更正第一輪「fixupx 做不出那篇影片」的推論。完整測試 2555 項全過、突變全紅；拆成 4 個 commit（未推送），未重啟。
- 2026-11-07 10:xx～12:xx 市集介面四題定案（TR-Q86＝A、Q87＝C、Q88＝A、Q89＝A，使用者看了畫面草稿後「全部依照你的建議」）並連同 TR-Q85 標籤實作：每個品項一格的尾款表單、作者欄連到個人檔案、改好前不能拿掉【定金】、「現貨」標籤；建標籤收成 `utils.discord_content.ensure_forum_tags`（`create_tag` 連建兩個會互相蓋掉）並加守衛。使用者另定 TR-Q90＝A（賣完的預購也拿掉「預購中」）。四個子 agent 複查＋各一個反駁：成立 2 條已修（重畫時查供應方一時出錯不再把標籤拿掉；`TRADE_FLOW.md` 補「還掛著舊交易時」），其餘 7 條不成立或只是加固（另把守衛加寬到手動組 `available_tags=`）。之後再定 TR-Q91～Q94（開始收尾款、開始交貨的確認畫面寫不能復原、改正式語氣）並實作。完整測試 2511 項全過、突變全紅；拆成 8 個 commit（程式 `1eb8574`～`459d782`、文件另一個），每個中間版本都跑過完整測試；未推送、未重啟。
- 2026-11-07 09:3x `dev/` 改成給人看的版型：25 個主題檔加上半部（一頁看懂＋歸檔時狀態勾選清單、時間線、定案與理由、踩過的坑），原文摺進 `<details>`、逐行核對沒少；流水帳改成每月重點（約 420 筆篩到 92 筆，時間、commit、測試數字、狀態不留）；新增 `dev/check.py`；`AGENTS.md` 加「commit 要小」；本檔待做改勾選框、「歸檔放哪」定案（交接檔給 AI、`dev/` 給人）。規則候選 10 條等使用者挑。已 commit（`eecfca1`，字典另一個 `c94262a`）、未推送。
- 2026-11-07 07:1x～08:4x 市集上線核對：07:43 使用者重啟、上線匯入完成且數字與預覽一致，08:14 又重啟一次沒重匯；討論 TR-Q85～Q89（標籤定案未實作，其餘等使用者）；上架視窗欄位順序 `8d760e7`（已生效、未推送）；給觀星者的「改成定金＋尾款」說明經四個子 agent 對照程式核對後定稿，還沒傳。交易區塊已更新，未 commit。
- 2026-11-07 08:5x 使用者要歸檔以人好讀為主、兼顧 AI 修改：提案上半部重點＋原文摺起來的版型，樣本套在 `dev/admin/console.md`；開頭給 AI 的維護備註、整理到標記、摺疊、檢查腳本列成 DV-Q5～Q8，等使用者。未 commit。
- 2026-11-07 08:3x `TODO-completed.md` 拆進 `dev/` 後刪除：26 個主題檔（relay／ai／community／admin／architecture）＋ `journal/` 六個月份＋ `README.md`（依領域、依日期）；各段原文照搬，只改連到程式與其他段落的路徑；交接檔區塊 `@meta` 加 `history:`、「經過見」改連主題檔，維護規則改成「歸檔放哪」；`AGENTS.md` 與記憶改指 `dev/`。市集的 commit 編號改成推送後的 `65394b7`／`c310be2`，現況改成已推送、08:14 已重啟。未 commit。
- 2026-11-06～11-07 市集資料庫版（定金＋尾款、分品項收款與交付）實作並合進 master（合併 `c310be2`，拆成六個 commit `e3ed09e`～`65394b7`；舊的一串留在 `backup/market-before-split`），未推送、未重啟；重啟後的上線匯入與核對見 `trade-revamp`。
- 2026-11-07 03:1x～03:5x 琇紫第八、九版人格（多輪守線、放寬調情）上線；思考設定改到 runtime config 頂層、由 `backend_admin` 翻成各後端寫法；都已推送。第九版去留等 08:00 對照測試，見 `ambient-chat`。

---

## 本檔維護規則（強制）

<!-- @meta
id: collaboration-rules
type: CONTRACT
status: confirmed
last_confirmed: 2026-11-07
history: dev/architecture/docs.md
-->

每次工作都要遵守的規則在 repo 根目錄的 `AGENTS.md`；這裡只放維護本檔的規則。

### 流程

`讀需要的區塊 → 沿用共識 → 討論／執行 → 回寫 → 下輪再讀`。不必每輪全文重讀；要交叉確認依賴、主線變更或資訊不足時才擴大範圍。本輪有實作異動、共識更新、待決題目新增或變動（題目、選項、建議）、待做狀態改變，或使用者要求時就回寫；討論與 grill 的每一輪都算。

### 區塊寫什麼

- 只寫四類：**現況**（現在系統裡有什麼、在哪、上線了沒）、**規則與坑**（不知道就會改壞的事與理由）、**未定案**（題號、問題、選項、建議、在等誰）、**待做**。
- 不寫進來：經過與時間線、測試與突變的數字、commit 清單、已結案題目的討論過程。需要留存的寫進 `dev/` 的主題檔；git log 本身也是紀錄。
- 已結案的題目：結論還約束之後的做法就留一行結論，否則刪掉。
- 待做一律用勾選框 `- [ ]`。做完改成 `- [x]`，後面補日期與一句結果（例：`- [x] 推送（11-07 已推送）`），讓人一眼看出哪些做完了；下次瘦身時，做完的隨經過搬進 `dev/` 的主題檔。還有依賴沒完成的留 `- [ ]`、註明依賴。
- 主線切換或整塊做完：改原區塊的 status、從現況摘要拿掉，整段原文移到 `dev/` 的主題檔（寫法見下方「歸檔放哪」）。

### 盤點紀錄

開頭的「最後盤點紀錄」每輪一行：日期時間、做了什麼、停在哪（未 commit／待重啟／等誰）。只留最近約 10 筆，更舊的有重點就寫成一行放進 `dev/journal/<年-月>.md`，沒有就刪（見下方「歸檔放哪」）。細節寫進主題區塊，不寫在這裡。

### 歸檔放哪（`dev/`）

- 分工：本檔給 AI 看目前進度、隨時更新，格式以 AI 好處理為準（`@meta`、題號、勾選框、一行一件事）；`dev/` 是做完的東西，給人看完成的過程、困難、重點和要注意的地方，agent 追舊決定也在那裡搜題號、模組名、commit 編號。
- 結構：`dev/README.md` 總目錄（依領域、每月重點、依日期）；主題檔在 `relay/`、`ai/`、`community/`、`admin/`、`architecture/`，一個主題一個檔、跨時間累積，本檔區塊的 `@meta` 用 `history:` 指向它、區塊裡的「經過見」也連到它；`journal/` 是每月重點。
- 主題檔版型：開頭一段給 AI 的維護備註（HTML 註解，含「整理到」日期）；上半部「一頁看懂」（最後是歸檔時的狀態勾選清單）、「時間線」、「定案與理由」、「踩過的坑」；下半部「原文」：目錄表（日期、短標題、摘要），各段標題不動（README 用它當錨點），標題下放摘要與關鍵字，正文收進 `<details>`。
- 歸檔一段：原文照版型放進主題檔「原文」的最前面，目錄表與 README「依日期」各加一列，同一輪更新上半部與「整理到」。沒有合適的主題檔就新開一個，登記進 README「依領域」與區塊的 `history:`。
- 每月重點：盤點紀錄超過約 10 筆時，舊的那幾筆有重點（學到的、定案的理由、使用者的要求）就寫成一行放進 `dev/journal/<年-月>.md` 對應主題，沒有就刪；時間、commit 編號、測試數字、狀態不留（查 git log）。屬於 AI 做事規則的，同時寫進 `AGENTS.md` 或記憶。
- 改完 `dev/` 跑 `python3 dev/check.py`（連結與錨點、`<details>` 成對、目錄與 README 對得上、「整理到」沒落後）。
- 資料夾叫 `journal/` 不叫 `logs/`：根目錄的 `logs/` 是程式執行紀錄。

---

## 現況摘要

> 只放指標與錨點，細節在各區塊。主題不再是主線就從這裡拿掉。已完成與過往工作見 [dev/README.md](dev/README.md)（依領域與依日期的索引）。

| 主軸 | 狀態 | 詳見 |
|---|---|---|
| 指令整理與管理入口 | 群主的管理操作已收進 `/server_manager` 主控台、權限檢查已統一成 `require_access`；剩指令去留（主控台上線後原本的 `/persona`、`/article` 子指令規劃要重定）、測試指令隔離（使用者暫緩）、人格管理的狀態畫面、網頁 dashboard、權限守衛 | [詳見](#指令整理與管理入口) |
| 交易與商品市集 | 市集資料庫版（定金＋尾款、分品項收款與交付、週報與看板）已推送，11-07 07:43 上線（匯入完成）；剩 5 篇【定金】商品轉換後關開關並刪銜接程式、論壇標籤加「現貨」（TR-Q85 已定未做）、TR-Q86～Q89 待決、措辭與價目表待決 | [詳見](#交易功能改版與商品市集) |
| 程式結構整理 | `llm/`、`services/` 分子資料夾與 `on_ready` 只剩登記都已上線；剩 P2 拆檔、P3 剩轉發自動啟動與 Telegram 組裝、N3 拆 `utils.py` 剩一半、N1 命名慣例沒寫進 AGENTS.md | [詳見](#程式結構整理) |
| 情報搜尋（MCP）與 /askai 查詢工具 | search-mcp 常駐、/askai 情報＋網路工具已上線；剩 SearXNG 設定換新（W8 定案未套用）、放寬查詢輪數、工具說明、舊資料補向量、暱稱表、考卷擴充 | [詳見](#情報搜尋mcp官網公告官方-fbptt巴哈) |
| 架構審視與滾動修正 | 分層、Discord 退出下層、背景任務、超大函式、路徑與狀態檔、錯誤邊界、gate 瘦身、notify 密鑰已上線；重複輪子已收 6 組＋第三輪的 X1、c4a、c9 第一步、B2、B6、先算向量再刪、B4，都已推送；剩 DW-Q2～Q4（下一批順序，建議候選 5 連 7）、20 組候選、M9 worker 設計、M6 完整版、X2、runtime 檔照意義拆 | [詳見](#架構審視與滾動修正) |
| LLM 推論：KV cache 與 prompt 快取 | `llm_usage` 已上線、prompt 擺放規則已定（11-04 量過）、/askai 決策輪已拿掉；剩 `--parallel` 實驗 | [詳見](#llm-推論kv-cacheprompt-快取與-gpu) |
| Hermes 串接 | bot 的 `/v1` 模型端點已上線、Hermes 端到端打通（10-26）；使用者 11-04 說先不管 Hermes 的架構與容器，其餘全部暫停 | [詳見](#hermes-串接暫停) |
| Telegram 過濾＋隔離區 | 上線中（含別款遊戲名單、右鍵搬移、下載防壞檔）；剩送失敗重試、頻道 0 自動寫入、TM-Q1／Q3／Q4／Q7 待使用者 | [詳見](#telegram-訊息過濾隔離區) |
| 連結轉址與 AI 讀預覽 | bilibili 轉 vxbilibili、轉貼長出預覽才壓原預覽、替代網址預檢、暴雷照包、轉貼用回覆送出、回覆轉貼不算叫它、AI 讀連結預覽都已實作並 commit（11-09，未推送）；未重啟 | [詳見](#連結轉址xbilibili與-ai-讀連結預覽) |
| 巴哈／PTT 轉發：刪文與亂改 | 編輯限速 10-02 修好後沒再出現巴哈的 429；刪文與亂改的防禦 DF-Q1～Q3 待使用者 | [詳見](#巴哈ptt-轉發刪文與亂改的防禦) |
| scraper 抓網頁與 FB 爬蟲 | FB 走 IPv6、:05 排程、跳過已確認、影片轉發都已上線；剩巴哈每輪超時、FB-Q3／Q5／Q7／Q8②／Q11／Q18／Q19 待使用者、分享貼文讀錯文字等已知問題 | [詳見](#scraper-抓網頁機制與-fb-爬蟲) |
| 週期活動提醒 | 已上線（深塔、海墟、矩陣）；只剩自介面板置底待有人送自介時驗證 | [詳見](#週期活動提醒深塔海墟矩陣) |
| Lemonade 後端與寫入緩衝 | 剩兩題待決：LM-Q2（Lemonade 重灌後載入選項不會重推）、LM-Q4（三份寫入緩衝收成共用元件，raw 斷線不再整批丟） | [詳見](#lemonade-後端與寫入緩衝的待決) |
| 群主通知、管理主控台、機器人狀態 | Lemonade 自癒重開＋私訊「重新偵測」、主控台「一則訊息、幾個畫面」、狀態面板九項、頻道綁定面板都已 commit、推送、上線；剩第二批主動私訊偵測、DL-Q1～Q3（顯示卡掉裝置）、CS-Q2、CB-Q8、OA-Q8、偏好抽取上限 | [詳見](#群主通知管理主控台與機器人狀態) |
| ComfyUI 產圖＋GPU 仲裁 | 未開工；租約閘門與 `release_model` 已有，鎖漏洞（載入在拿閘門之前）還沒修；ComfyUI client、03:00 排程、發圖與六題待決要等使用者 | [詳見](#comfyui-產圖與-gpu-仲裁) |
| Persona Agent（精簡版發布） | 已上線穩定，備援萃取 10-13 已拆；剩隔離永遠解不開的 bug、版本寫入失敗被當成功、失敗隔天重跑等待做，刪兩份「無法分析」描述要使用者同意 | [詳見](#persona-agent精簡版發布) |
| Telegram 漏收補掃與相簿漏圖 | 已上線；只剩幾種已知會缺圖的情境沒處理 | [詳見](#telegram-漏收補掃與相簿漏圖) |
| 聊天檢索（RAG） | 重算向量、h512 索引（371 MB）、pg_trgm、/askai 聊天搜尋工具都已上線，60 題 Hit@1/5/25＝38/47/50；剩重排門檻校準、約 11-27 後 DROP `embedding_v1`、端到端評估，待決 RG-Q9／Q10／Q15 | [詳見](#聊天檢索rag折疊品質閘重排hnsw聊天搜尋工具) |
| Context／Prompt 優化 | 主要重構已上線；剩 asker roles、/askai 指定 thread（做法未選）、斷音觀察 | [詳見](#contextprompt-優化剩餘小項) |
| Reaction 統計與社群玩法 | 資料已在收（`reaction_breakdown`）；每週金句、名人堂、招牌表情、/askai 與人格描述整合都還沒做 | [詳見](#reaction-統計與社群互動玩法) |
| 使用者指令記憶（/remember） | 未開工；共享記憶層 `MemoryService` 已在（插話用），缺指令、直接 trusted 的寫法、/askai 召回；5 題待定 | [詳見](#使用者指令記憶remember) |
| AI 私聊（功能一）＋三層記憶 | 規劃、未開工，06-20 起暫放；偏好層、看圖、開口判斷已由插話做出可共用的零件；場所（頻道或私訊）與敏感內容政策待定 | [詳見](#ai-私聊功能一三層記憶) |
| AI 偶爾插話（琇紫） | 已上線；11-07 第九版人格（放寬調情）已上線並推送，等 08:00 對照測試給使用者判去留；插話查詢仍是 dry_run（AS-Q1 已定要開，等 AS-Q2 或使用者說切）；待決 AS-Q2～Q3、PS-Q2／Q3／Q8／Q9、簡體轉繁、AM-Q2／Q6h、RB-Q9、AL-Q1～Q5；待做 KN-Q8、查詢第二版、C-4、觀測面板 | [詳見](#ai-偶爾插話閒聊琇紫) |
| 點歌機器人 | 上線運作；10-16 重連修正有效，但斷點續播會卡死重試（已發生 4 次、每次到重啟才停），未修；體驗待做 5 項 | [詳見](#點歌機器人) |
| 跨來源整合 | 發文已共用；Telegram 設定改成以服務為單位（TG-Q1～Q5 已答、沒動工），TG-Q6／Q7 待使用者；3 月規劃其餘未做 | [詳見](#跨來源整合) |
| 產品能力 TODO | 2026-03 規劃大多未做；/askai 回應紀錄與 RAG 評估集已有，缺回饋按鈕、KPI、玩法、A/B、模型路由、SFT | [詳見](#產品能力-todo) |

---

## 指令整理與管理入口

<!-- @meta
id: command-consolidation-dashboard
type: DECISION
status: draft
last_confirmed: 2026-11-07
depends_on: persona-extraction-agent
affects: commands/, notify_server
history: dev/admin/console.md
-->

（經過見 [dev/admin/console.md](dev/admin/console.md)）

**現況（11-07 對程式核對）**
- 群主的管理操作都從 `/server_manager` 進（伺服器裡或私訊，只放群主）：主控台 `commands/admin_console` 有機器人狀態、頻道設定、角色管理、伺服器資訊、文章轉發（監控狀態、測 API、重送、同步巴哈）、幽靈點名（私訊面板）、AI（立即寫日記、對一人跑人格 agent）、交易看板。設計在 `owner-alerts` 區塊，放新功能的規則在 AGENTS.md「群主的管理操作放哪」。
- 斜線指令 20 個、右鍵選單 1 個（前綴指令 10-27 拿掉）。群友用：`askai`、`forget_tag`、`list_item_price`、`watch_keywords`、`trade_info`、`select_item`、`set_item_prices`；管理用：`server_manager`、`server_info`、`rollcall_panel`、`persona_agent_test`、`ai_diary`、`article_manager`、`resend_article`、`get_baha_post`；`test_commands.py`（正式環境照樣載入）：`anonymous`、`echo`、`list_forum_posts`、`ping`、`multi_select_demo`；右鍵「移到垃圾訊息」。
- 權限檢查全部走 `utils.discord_members.require_access`（10-28 由 `check_guild` 改名搬過去），守衛擋 `has_permissions`；9/04 的 `require_permission` 裝飾器方案不再需要。`test_commands` 的 5 個指令沒有權限檢查。

**仍有效的規則與坑**
- `/askai` 保持獨立（天天用，藏進子指令反而難找）。
- 網頁 dashboard 只綁 host-only 介面或加 token，不開在對外網段：內容是成員的完整發言證據。`notify_server` 綁 `0.0.0.0`、只靠共用密鑰擋，dashboard 路由要另外驗 token。
- `/persona_agent_test` 入口、出口各驗一次權限（followup token 有 15 分鐘，期間權限可能被撤），是刻意的，不是重複。
- `config.json` 的 `role_mapping.Moderator` 是空的；`check_role` 對沒設定的身分組一律擋（群主除外），訊息看起來像權限不足。現在沒有指令用 Moderator；要用之前先在主控台「角色管理」設好。

**未定案**
- **待確認** 指令去留（主控台上線後，原本的子指令規劃前提變了）：原規劃把 `persona_agent_test`、`forget_tag`、`ai_diary` 收成 `/persona` 子指令、文章類收成 `/article` 子指令；現在主控台已有這些管理操作，`/article_manager` 只多了「在這個頻道開始／停止監控」。選項：A 照原規劃收成子指令；B 管理用的指令拿掉、只留主控台（開始／停止監控先搬進主控台），群友用的保持獨立；C 不動，舊入口當退路。建議 B：照 AGENTS.md 新的管理功能放主控台，兩個入口要維護兩份。和 `code-structure-reorg` 的 P2 一起定。等使用者。
- **`test_commands` 只在開發環境載入**：`/anonymous` 讓任何人用 bot 身分匿名發到他所在的文字頻道或 thread。選項：A 用環境變數決定載不載／B 只把 `/anonymous` 改成 owner_only／C 不動。建議 A。使用者 09-04、10-12 都說先不管，暫緩到使用者重提。
- **群主語意不一致**（無題號）：`check_role` 與 `require_access(permission=…)` 群主自動通過，`require_access(admin_only=True)` 在伺服器裡不會（群主沒有管理員權限就被擋）。建議統一成群主一律通過（另外兩處與私訊裡本來就放群主）。等使用者。

**待做**
- [ ] 人格管理的狀態：上次萃取時間、成功筆數、失敗清單、最近一次 diff、agent 執行中的步數與 token。加在主控台的 AI 畫面（現在只有兩個按鈕）。
- [ ] 網頁 dashboard（沒動工）：在 `notify_server` 加唯讀路由，資料源 `persona_agent_versions`（人格版本、長期漂移）、`persona_agent_runs`（執行紀錄、失敗率、幻覺率）、`auto_personality`（精簡版與完整描述並排）。

### 權限檢查收斂

<!-- @meta
id: permission-consolidation
type: TODO
status: blocked
last_confirmed: 2026-11-07
history: dev/admin/console.md
-->

兩種寫法並存的問題已解（見上方現況）。剩一題：
- **待決：權限 AST 守衛**：加一條「每個斜線指令的函式裡都要呼叫 `require_access`」，白名單寫到函式層級（現在沒呼叫的是 `server_info`、`server_manager`——交給 `admin_console.send_console` 驗——和 `test_commands` 的 5 個）。它跑在啟動 gate，誤判會讓 bot 起不來，本專案一貫寧可漏判；先不加，建議等 `test_commands` 的去留定了再評估。

---

## 交易功能改版與商品市集

<!-- @meta
id: trade-revamp
type: TODO
status: draft
last_confirmed: 2026-11-10
depends_on: TRADE_FLOW.md（現況與流程）
affects: commands/shop_commands.py、commands/forum_monitor.py、commands/trade_commands.py、utils/discord_content.py（論壇標籤）、services/community/（trade_service、shop_listing、shop_service、shop_trade、trade_progress、market_import、market_report、market_transition、item_prices）、services/market_db.py、settings/switches.json（market_transition）
history: dev/community/trade.md
-->

自由市場接單與商品上架共用一套交易流程。流程、用語、程式碼清單、資料表與坑寫在根目錄 `TRADE_FLOW.md`；`market_db`、`trade_progress`、`TradeService.send`／`locked`、鎖的順序寫在 `AGENTS.md` 共用元件表。這裡只記決定、未定案與待做。（經過見 [dev/community/trade.md](dev/community/trade.md)）

**現況**
- 市集資料庫版已上線：六個 commit `e3ed09e` 共用資源、`450dc26` 市集資料庫、`271ff0d` 商品與交易走資料庫、`9db111e` 上線匯入＋銜接開關、`9b1191c` 週報與交易看板、`65394b7` 文件；合併 `c310be2`；已推送。舊的未拆版本留在分支 `backup/market-before-split`。
- 上線匯入 11-07 07:43 重啟時做完：07:43:56 寫進資料庫、07:44:13 重畫完並開放按鈕，商品 8、交易 14、警告 0、認不出身分 0，跟重啟前的只讀預覽一致。預售 2 筆補了交易進度卡，向 Discord 讀回確認沒有 @ 任何人。`src/services/market.db`、當天備份 `market_backup/market_2026-11-07.db`（等匯入做完才補，07:48）、匯入時讀到的舊格式原文 `market_backup/import_source_20261107T074356.json` 都在。舊貼文已重畫成新格式，這份原文是唯一的舊資料，要留著。08:14 又重啟一次：`meta.import_done` 已有，沒有重匯，沒有錯誤。
- 上線後各表：商品 8 篇都是實體交付，1 篇是已下架的測試商品；另有群主 07:48 上架的「test」，沒有品項。交易中商品 10 筆（預售 2 筆新流程、【定金】上的 8 筆舊交易）、自由市場 4 筆舊交易。資料庫結構（表、欄位、事件種類、備份檔）的說明頁：artifact https://claude.ai/code/artifact/b7a62c0c-9a1d-4840-a2ff-c5bc27abc926（「市集資料庫」；本機檔在暫存區會消失，要改先用 Artifact read 取回；改了結構要一起改）。
- 上架與「編輯商品資訊」視窗的欄位順序：標題、幣別、交付方式、商品圖、說明（`8d760e7`，08:14 重啟後生效，未推送）。
- 11-07 中午實作、已 commit（`1eb8574`～`459d782`）未推送、要重啟才生效：開始收尾款與開始交貨的確認畫面（TR-Q91～Q94）、TR-Q85 與 Q90 標籤、TR-Q86 每個品項一格、TR-Q88 作者欄連結、TR-Q89 擋拿掉【定金】，以及 `ensure_forum_tags` 共用元件與守衛（`/select_item` 也改用它）、`parse_balances` 只打逗號回「看不懂」、`TRADE_FLOW.md` 交付方式寫錯。重啟後舊貼文的作者欄、標籤都要等那篇下次重畫才換；【定金】那 5 篇下次重畫時會拿掉「預購中」（長離原本是預購、掛著），改好後再掛回。「現貨」標籤要等第一篇有買得到的立即購買品項重畫時才建（或重綁商品論壇時一起建）。
- 新版內容：品項分立即購買／預購／定金＋尾款；交付方式每篇商品設（實體／數位）；每筆商品交易一張交易進度卡（每個品項各自收款、交付）；等待提醒、週一週報、置頂說明的「📋 我的交易」、主控台「交易看板」；每天 03:30 備份到 `src/services/market_backup/market_YYYY-MM-DD.db`，留 14 份。
- 上線銜接：開關 `market_transition`（switches.json，預設 on）與 `services/community/market_transition.py`。11-07 只讀預覽的正式資料：商品 8 篇（1 篇是已下架的測試商品）、進行中交易 14 筆。預售 2 篇（小乖、絨絨相伴）的 2 筆匯入時直接轉新流程；標題寫【定金】的 5 篇（長離 1/6、茶歇時光 Q 版、卡提希婭 1/6、尤諾 1/7、琳奈 1/7）照一次付清匯入，上面 8 筆舊交易先留在舊流程，觀星者在管理面板按「💰 改成定金＋尾款」（只有一個品項的也可用編輯品項）填尾款與收定金截止後接上新流程、補發交易進度不 @ 人；改好前這幾篇不接新訂單、不能下架、舊交易不能照舊流程完成（擋新訂單要那篇掛著舊交易；5 篇各掛 1～2 筆，所以 5 篇都擋）。自由市場 4 筆照舊流程。系統裡還沒有任何定金紀錄（舊流程不記收款，改版前有沒有私下付過看不出來）。匯入的商品交付方式一律實體。
- 商品圖照選取順序排（`61a7709`，已上線）：discord.py 的 `FileUpload.values` 照 resolved 附件表排、不照選取順序，`shop_commands._uploaded_in_order` 依元件的 `values` 重排，順序不同時記一行 INFO「上傳的圖照選取順序重排」。
- 市集連結（11-10 實作，`e8e02d3`～`3b18231`，未推送，要重啟才生效）：週報、「📋 我的交易」、看板、完成留底、開單訊息的來源欄位、擋操作時的交易清單，交易對話與貼文一律寫成網址（`utils.discord_content.channel_url`＋`masked_link`；交易與市集的清單走 `trade_service.thread_link`／`party_name`，市集所在的伺服器收成 `ShopService.guild()`、拿掉 `market_report.guild_of`），清單上每筆的字是標題加需求方名字（已離開的寫 id）；週報太長時從換行處切、結尾留「全部清單」那句；主控台太長時從換行處切，看板「認不出身分的舊交易」一行一條。這週（W46）的週報已記成送過，不補發；下一份是 11-16 週一 12:00。
- 11-10 08:35 照 TR-Q95 把 4 筆自由市場舊交易（1386328014790463559、1459245685118341270、1467825208206430463、1469546974880469157，供應方是同一位觀星者）在資料庫標成 `ended`、`wrapped_up=1`，各記一筆 `ended` 事件（`source='manual'`）；Discord 沒動、沒通知任何人，對話標題與失效的舊按鈕照舊。改之前的備份 `src/services/market_backup/market_before_end_legacy_20261110.db`（不在每日輪替的檔名裡，不會被刪）；回復用反向 SQL（改回 open、清 `closed_at`、`wrapped_up` 改 0、刪這 4 筆 manual 事件）。之後還沒結束 10 筆，舊交易剩 2 筆（【定金】商品上的，按鈕是 `trade:` 開頭、能用）。
- 定金流程的範例畫面與狀態圖（設計討論時的版本）：artifact https://claude.ai/code/artifact/46309e7a-ae71-475c-8839-9fe39784378f（「鳴潮市集定金流程」；本機檔已不在，要改先用 Artifact read 取回）。

**已定案（之後改這塊要守的）**
- TR-Q46～Q84 全部已定案並實作。TR-Q47～Q49 因採「一個品項分兩段收款」不用答；TR-Q50 改成上線匯入（TR-Q76）；TR-Q51＝C（交易進行中的品項不能改類型，要先取消）；TR-Q52 上線前已完成的不回推；TR-Q80 舊交易直接掛上類型、補送交易進度；TR-Q81 併進 TR-Q82～Q84（銜接獨立成模組加開關，5 篇都改好才關，關掉就照一般規則）。
- 資料（TR-Q74～Q77）：正本放新的 SQLite `src/services/market.db`（不用 sent_articles.db、不用 Postgres），推翻舊版 TR-Q1「Discord 當紀錄、不加資料庫」。理由：Discord 當紀錄要翻全部封存對話才列得出某人的交易、結束後讀不到身分、對話被刪紀錄就沒、custom_id 放不下以後的金流序號、提醒次數與週報去重沒地方記。事件表只增不改。只匯入還開著的交易，標成舊交易（不提醒、進週報與看板）。
- 不支援退版（TR-Q78＝A）：上線後退回舊版期間發的商品貼文、開的交易對話不會進資料庫，改回新版時會被當成「做到一半中斷」：貼文被刪（連圖與留言）、對話被鎖。真的要退，回來前先講，清資料庫重新匯入。資料庫 `meta.schema_version` 比程式新就拒絕連線。
- 交易按鈕 custom_id 維持舊格式 `trade:動作:來源:需求方:供應方`，處理時用按鈕所在的對話查資料庫、不看上面的身分；交易進度按鈕是 `trade:step:動作[:品項][:v卡片版本]`，要以 `trade:` 開頭，交易結束時才會一起收掉。卡片版本比對是「大於或等於」（曾寫反，真按鈕的「我已付」全部不算）。
- 定金＋尾款（TR-Q46、Q56、Q58、Q62）：是一個品項的付款方式，不是兩個品項；價格欄填「定金/尾款」；下單時兩個金額都記下，之後改價只影響新訂單。同一位需求方、同一篇商品一個交易對話，沒結束就沿用。
- 收款與交付（TR-Q53～Q55、Q61、Q63）：所有商品交易都有交易進度卡，一次付清也要供應方確認收款（寄出到收到有時間差）；需求方「我已付」只 @ 供應方、不改狀態；每個品項的「已交付／已寄出」要等那個品項的錢收齊，判斷在 bot 端；最後一項交付後 bot 自動發領收通知（上架者很少按）。
- 交付方式（TR-Q64～Q66）：每篇商品設一次，新上架預設實體（實體選成數位會被 24 小時自動完成，反過來只多按一次）；有交易時不能改。實體每個品項由需求方按「已收到」，全部收到才完成；寄出第 7 天起每 3 天 @ 雙方，直到收到或取消，不拉群主、不自動完成（要逼雙方追蹤）。
- 取消（TR-Q57＝C、TR-Q73 撤回）：群主也能取消；有已收的款先跳確認；沒交付、沒寄出的份數還回，已交付或已寄出的不還回、在提醒裡列出；提醒文字不提金流（系統沒串金流）。
- 截止、延期、開始交貨（TR-Q59、Q60、Q69～Q72）：定金品項必填截止，不能跟一次付清的放同一篇（程式擋；一起買的現貨會被拖到尾款收完）；一次付清的預購截止＝停止下單＋@ 雙方可以開始交貨；定金截止只停收定金，可以交貨在「📦 開始收尾款（準備交貨）」時通知；「📅 延期」只能往後、@ 需求方，已截止的不重新開放下單、只設預計交貨日；「⏩ 開始交貨」＝一次付清的預購提早截止；有人下單或已截止的品項截止欄鎖住，改日期只走延期。
- 通知（TR-Q67、Q68）：只 @ 下一步要動手的人；等待提醒照 `trade_progress.due_reminders`，22:00～10:00 不發、每個對話每天最多一則、舊交易不提醒；週報只私訊有待辦的觀星者，群主不收（看板列週報沒送到的、認不出身分的舊交易）。
- 權限：`ShopService.can_manage` 只放上架者本人、伺服器擁有者、有 Discord「管理員」權限的人（給觀星者管理員權限他就能改所有商品）。被拿掉觀星者身份組的人，他的商品不接新訂單，進行中的照常、面板照常能用（TR-Q79＝A）。還有沒完成的定金或預購交易時不能下架，停止接單靠截止。
- 管理面板一則 5 列已放滿（Discord 上限）；之後要加按鈕得另找位置。
- 用詞：群友看到的只講發生什麼、下一步，不講 thread／鎖定／封存（TR-Q34）；一律「需求方、供應方」，不用「上架者」「買家／賣家」（交易不一定是買賣，自由市場沒有上架者）；程式欄位名（`owner_id`、`supplier`）不動。
- 價目表（TR-Q7＝C）：合併、分兩階段；上架穩定後把 `item_prices.json` 搬進商品目錄（先備份、取得同意），停用 `/set_item_prices`、`/list_item_price`。
- 論壇標籤（TR-Q85，11-07 定案、實作未 commit）：不做每種品項類型一個標籤，因為「定金＋尾款」是付款方式，不是什麼時候拿到貨，而且同一篇可以混放立即購買與預購。只有兩個標籤，都跟著「現在能不能買」：「預購中」＝有買得到的預購或定金品項；「現貨」＝有還沒賣完的立即購買品項，判斷跟下單同一套，所以還在等改成定金＋尾款的【定金】商品不掛。兩種都有就兩個都掛；截止後等交貨的都不掛；下架全部拿掉。不加排程：每次照資料庫重畫貼文時順手對一次、跟現在不同才改（重畫發生在管理面板的每個動作、下單、交易取消還回份數、購買選單選了品項）；「預購中」在截止那一刻跟著截止計時器那次重畫拿掉。供應方被拿掉觀星者身份組不會讓 bot 重畫，標籤要等那篇下次有變動；不另外監聽身份組變動（很少發生，下單時本來就會擋並說明）。實作：規則 `shop_listing.forum_tags`、同步 `ShopService._sync_tags`（只動這兩個，別人掛的不動）；「整篇不接單」照下單那一關算（下架、供應方不在或不是觀星者、`holds_orders`），所以那 5 篇【定金】改好前兩個都不掛。TR-Q90＝A（11-07 使用者「好」）：「預購中」也看現在買不買得到，賣完就拿掉、份數還回來再掛，跟「現貨」一致（原本只看截止，群友篩「預購中」會看到買不了的）。
- 上線後的介面四題（TR-Q86～Q89，11-07 使用者「全部依照你的建議」；各選項的畫面草稿 https://claude.ai/code/artifact/62d83c2e-994c-44cb-8e09-13a749cd7dd1）：
  - TR-Q86＝A：「改成定金＋尾款」每個品項一格，格子底下寫出定金（原本標的價格）與「填總價減掉定金」；表最多 5 格扣掉截止剩 4 格，超過 4 個品項才退回一格多行。理由：觀星者最容易把總價當尾款，寫進舊交易後自己改不回來。
  - TR-Q87＝C：批次新增不動，等「AI 上架」。現在上架的多半是 1～2 個品項，用單一品項就夠；長清單每行價格、數量都不同，拆共同欄位省不了什麼。想讓幾個品項加得順，再做「再新增一個（沿用上一個）」。
  - TR-Q88＝A：商品貼文作者欄掛 `https://discord.com/users/<id>` 與供應方頭像；手機點不開再改成說明第一行 @ 他。舊貼文等下次重畫才換。
  - TR-Q89＝A：還掛著舊交易、還沒改成定金＋尾款的商品，「編輯商品資訊」不能拿掉標題開頭的【定金】，送出時什麼都不存並請他先按「💰 改成定金＋尾款」。只在銜接模組裡，關開關時一起刪。
- 「📦 開始收尾款」「⏩ 開始交貨」的確認畫面（TR-Q91～Q94，11-07 使用者問有人下單時要不要提示不能退回、文字要不要好看；警告句是使用者自己改的，要專業、不要太像 AI，其餘照建議，使用者「好 改」）：粗體標題＋條列＋空一行後最後一行 ⚠️「此操作無法復原：…請確認貨品已到再執行。」，整段同一種正式語氣（「此操作」「立即」「原訂」），稱呼照市集其他文字用「你」；沒人下單時寫「目前沒有人下單，不會發送任何通知」並提示只想暫停就把剩餘數量設為 0；開始交貨照同一套；確定按鈕維持藍色（紅色留給下架、刪除）。理由：按下去停收定金或停止下單、通知馬上發出去，都收不回；下架的確認本來就有寫不能恢復。

- TR-Q95（11-10，使用者選 C；建議原本是 A）：開單訊息上沒有可用按鈕的自由市場舊交易（2026-02-17 前的按鈕是 discord.py 給的隨機代碼、更舊的是「按 ✅ 確認」流程、沒有按鈕），直接在資料庫標成 `ended`、不在 Discord 收尾、不通知。沒選的：A 重啟時在對話補發可用的按鈕、B 主控台加「結束舊交易」。之後再出現這種交易照同一套做（先備份、取得同意）。
- TR-Q96（11-10，使用者選建議）：舊交易只列在待辦，不再列進「超過 14 天沒動靜」。理由：待辦已經寫了要完成或取消，再列一次只是重複，天數從開單那時算（幾百天）看不出什麼；新流程的交易照舊卡住 14 天才列。

**坑**
- 測試模式判斷在 `test/__init__.py` 的 `_is_test_run`（也認啟動 gate 與直接跑的 `test.` 模組）：測試中市集資料庫、GPU 鎖檔、runtime 備份都要換成暫存；判斷失準時 gate 會開到正式路徑、`test_data_file_paths` 紅，bot 起不來。
- 測試的假 Discord 已有三條真實規則：封存中的 thread 要在同一個請求解封才改得了（50083）、封存中加不了人、訊息 2000 字。新測試要照真按鈕的路徑（`step()` 讀卡片上的版本再送）。
- 給人點的交易對話、商品貼文、需求貼文連結不能用 `<#id>`：這些 thread 會封存，用戶端不會載入封存的 thread，私訊、留底、開單訊息裡會顯示成「# 不明」點不進去（11-09 週報出過）。一律用網址（AGENTS.md 共用元件表有一列、守衛擋自己拼網址）。
- 上線匯入只檢查舊交易讀不讀得到身分，沒檢查在新程式裡還有沒有路可以結束：2026-02-17 前開的自由市場對話按鈕是隨機代碼，`LegacyTransactionView` 接不住，按了只會「此互動失敗」。以後匯入或搬舊資料，要確認每一筆在新流程裡按得動、結束得了。
- 接受不修：留底或封存需求貼文發出去、還沒記 `archived` 就停機，重啟補收尾會再發一份。停機期間的真人訊息記不到 `trades.last_chat_at`，那幾筆的「沒動靜」天數會偏大。
- 「改成定金＋尾款」做錯了收不回來的地方，給觀星者的說明一定要講：
  - 【定金】只從標題開頭認（`market_transition.waits_for_deposit`）。改好之前用「編輯商品資訊」改掉這三個字，會連著發生：按鈕消失、開始接一次付清的新訂單、截止排程把舊交易照「立即購買」接上新流程（原本的定金變全額）。之後改類型會被「交易中不能改類型」擋，兩個品項的那兩篇還會被「不能混放」擋（TR-Q89）。
  - 送出時舊交易的尾款寫進 `trade_items.unit_balance`。之後用「編輯品項」改價格只影響新訂單，按鈕也不會再出現；介面上唯一的補救是取消交易、請需求方重新下單。
  - 收定金截止送出後就鎖住（舊交易算在已下單份數裡），只能用「📅 延期」往後延，每次都 @ 所有下單的人，貼文也會掛「已延期 N 次」。要提早停收，按「📦 開始收尾款」或把剩餘數量改成 0。所以日期寧可填晚。
  - 舊流程不記收款，轉換後一律「待付定金」：3 天後 @ 需求方催定金（之後每 7 天、最多 3 次）。改版前就付過的，要供應方自己在卡上按「已收到定金（供應方）」。
  - 表單 10 分鐘逾時（`_MODAL_TIMEOUT`），逾時送出什麼都不會存。格式錯時，寫入前就會擋下，但重開表單後要重打。尾款不能是 0；原本的價格如果其實是全額，這張表送不出去。
  - 「📦 開始收尾款」一次一個品項，按下去那個品項立刻停收定金、不再接單。定金還沒確認的那幾筆，bot 只 @ 供應方、請他先確認定金。

**未定案**
- TR-Q35／Q36 措辭（待確認）：原本剩交易流程 1～6、市集 7～10、18～21 句待使用者挑要改哪些，以及開單訊息要不要加一句告訴需求方要等供應方先動作（建議加）。市集資料庫版重寫了大部分交易與商品訊息，原清單多半已不適用；要照新版文字重列剩下的再問。等使用者。
- TR-Q33 上架說明要不要附操作截圖：A 介面穩定後由使用者在正式論壇截圖、放進 repo、發說明時附上（建議）／B 放一篇真實商品貼文連結當範例／C 維持純文字。介面剛大改，上線穩定後再問。
- 10-03～10-05 發出去的市集留底仍含完整對話，要不要改舊貼文（動資料，先取得同意）。等使用者。
- 價目表搬進商品目錄前，價格 0 是否代表不賣（TR-Q7 第二階段）。等使用者說明。
- TR-Q5 沒人收尾的交易（待確認）：原本排在之後和預購到期提醒一起做；新版的等待提醒、週報（超過 14 天沒動靜算待辦）、交易看板已涵蓋商品與自由市場，要不要另做自動結束，要問使用者。
- 合併後的 worktree `/home/jason/discord-market` 與分支 `feat/market-db` 要不要刪（刪前先問）。
**待做**
- [ ] 請使用者重啟 discord-bot（避開 04:00～07:30；重啟前查有沒有別的 session 在容器裡跑測試），讓 TR-Q85、Q86、Q88～Q94 生效。
- [ ] 重啟後才傳給觀星者「改成定金＋尾款」說明（第 4 步已照 TR-Q86 改成每個品項一格，「改之前」補一句 bot 會擋拿掉【定金】）。說明要講「坑」裡那幾件事。
- [ ] 推送 `8d760e7` 與 11-07 中午的 8 個 commit（等使用者說；GitHub 是公開鏡像）。
- [ ] 重啟後用群主 07:48 上架的「test」實測 TR-Q88：加一個品項讓貼文重畫，手機與桌機各點一次「供應方：名字」，看是不是開個人檔案；手機不行就換成說明第一行 @ 他。測完下架。
- [ ] 觀星者把 5 篇【定金】改成定金＋尾款 → switches.json 的 `market_transition` 改 off（不用重啟）→ 確認沒問題 → 刪 `market_transition.py`、`DepositConvertModal`（含 `_balance_label`）、面板的 💰 按鈕、核心裡問它的那幾行（`grep -rn market_transition src`；含 `edit_info` 的 `check_title`、`redraw` 標籤的 `holds_orders`）、開關定義與 switches.json 兩行、相關測試。`ShopService.adopt_legacy_on`、`ListingTrades.adopt_legacy`／`heal_adoption`、`trade_progress.ADOPTED`、`TradeService.refresh_opening` 是之後改類型也用得到的一般功能，留著。
- [ ] 商品圖順序：請使用者用標了 1、2、3 的圖上架一次，看大圖是不是 1、log 有沒有「上傳的圖照選取順序重排」（正式 log 還沒出現過）。
- [ ] 重啟 discord-bot 讓 11-10 的連結修正與 TR-Q96 生效（避開 04:00～07:30；重啟前查有沒有別的 session 在容器裡跑測試）。
- [x] commit 11-10 的修改（11-10：`e8e02d3` 共用連結＋守衛、`e40b908` 週報與清單的連結、`37ced3b` 舊交易不列沒動靜、`3b18231` 留底／開單訊息／擋操作清單，文件另一個；未推送，等使用者說）
- [ ] 請使用者回覆那位觀星者：那 4 筆是上線前的舊交易，已經結束，不用處理；下週的週報不會再有。
- [ ] `admin_console._clip`（從換行處切）與 `rollcall_commands._clip`（硬切）是同一件事的兩份，收成一份。
- [ ] 11-10 碰到的 `services/relay/bahamut_monitor.py`、`services/community/community_lookup_service.py` 模組說明還是舊格式（只改了組網址的幾行，沒照新格式重寫），下次動到時改。
- [ ] 舊交易都結束後刪 `forum_monitor.LegacyTransactionView` 與 `trade_service.legacy_ref_from_text`。11-10 起還開著的舊交易都不是它接的按鈕（剩 2 筆是 `trade:` 開頭），可以考慮現在刪；刪了之後，已結束的舊對話上的舊按鈕按了會「此互動失敗」，不再回「交易已結束」。等使用者。
- [ ] 價目表第二階段（TR-Q7）：`item_prices.json` 已只經 `services.community.item_prices` 讀寫，剩搬進市集資料庫、停用兩個指令。
- [ ] `/select_item`（`commands/trade_commands.py`）沒有測試（11-07 改成 `ensure_forum_tags` 建「代儲」標籤，沒有測試驗）。
- [ ] 複查留下的小事（不成立或只是加固，沒改）：一篇貼文別人掛滿 4 個標籤時再加 bot 的兩個會超過 Discord 的 5 個、整個標籤更新失敗且封存回不去（以前要 5 個才會）；`can_sell` 每次重畫都同步讀 config.json，供應方沒觀星者身份組時每次重畫記一行「嘗試使用…已被拒絕」的 INFO。
- [ ] 可考慮的守衛：給人看的文字裡提到的斜線指令都要存在（掃全專案，排除註解與網址路徑）。
- [ ] 之後：上架做成 AI 工具讓 agent 叫（市集上線穩定後）。共識：用下指令的人的身分執行，權限由工具判斷、不交給模型（只有觀星者能上架、只能改自己的）；寫入先出草稿，本人按確認才生效；跟錢有關的（確認收款、取消）不做成工具；查詢類（我的交易、看板）可直接給；圖片要在同一則訊息附。服務層函式已只收純資料參數、錯誤訊息是人看得懂的句子。可接 `llm.client.tool_calls` 的工具迴圈或 MCP。

---

## 程式結構整理

<!-- @meta
id: code-structure-reorg
type: TODO
status: draft
last_confirmed: 2026-11-07
affects: src/ 全部資料夾、commands/、discord_bot.py、utils/utils.py、settings/channel_registry.py、test_shared_conventions
history: dev/architecture/code-structure.md
-->

（經過見 [dev/architecture/code-structure.md](dev/architecture/code-structure.md)）

**現況**
- `llm/` 依角色分子資料夾、`services/` 分 `relay`／`events`／`community`，已上線；哪個資料夾屬哪一層以 `test_layering.LAYERS` 為準。
- `discord_bot.py` 的 `on_ready` 只剩登記：04:00 維護在 `llm/persona/daily_maintenance.py`、日記排程在 `ambient_diary.schedule_loop`、定期寫入走 `periodic`。還留在 `discord_bot.py` 的：公告與 PTT 自動啟動（`auto_start_article_monitor`，直接設 cog 的屬性）、Telegram 轉發組裝（`auto_start_telegram_relay`）。
- 權限與取成員已從 `utils/utils.py` 搬到 `utils/discord_members.py`；`utils/utils.py` 還有 `ChannelConfig`、5 個功能專屬的頻道 getter、互動回覆與分頁。`channel_registry.py` 還在 `settings/`。

**仍有效的規則與坑**
- 命名只改會誤導的（N1 定案 A，正名表在歸檔）；`forum_monitor.py`、`test_commands.py` 使用者說不改。
- 子資料夾判準：滿 6 檔、有封裝邊界、可預期會長，三者滿足其一。ComfyUI 產圖另開 `src/imagegen/`，不塞進 `llm/`。
- `services/sent_articles.db` 和程式放在同一個資料夾，`.gitignore` 依路徑排除；搬 `services/` 要一起改 `.gitignore` 與 `paths`，不然會把使用者資料 commit 進去。
- import 守衛抓不到：importlib 動態 import、間接 import 指令層、頂層 `alias.attr = …` 之後對那個別名的讀取（刻意保守，誤判會讓 bot 起不來）。
- 不鎖套件版本（S6-2；10-16 使用者再確認整個專案都不綁）：建置只 `pip install -r requirements.txt`；`docker/discord_bot/constraints.txt` 是某次 `pip freeze` 的紀錄、建置不讀，出問題時對照或用 `-c` 暫時裝回。discord-bot 與 search-mcp 是同一份 dockerfile 的兩個映像，改 requirements 要兩個一起 build。
- 還沒有測試保護的：自介投稿與印象審核、關鍵字監看、PTT 轉發、社群查詢（只測了日期解析）。搬這些先補測試。

**未定案**
- **P2** 一檔多功能，拆檔但留在同一個資料夾：`llm_commands.py` 拆成 /askai 與人格相關（agent 測試、日記）兩檔；`management_commands.py` 拆出自介面板；`user_commands.py` 的 `/forget_tag` 併到人格指令、物價併到 `trade_commands.py`。cog class 名稱不變（主控台用 `get_cog` 叫它們）、`COMMAND_MODULES` 要加項。建議和 `command-consolidation-dashboard` 的指令去留一起定，指令拿掉的就不必拆。等使用者。
- **P3** 剩下兩件：公告與 PTT 自動啟動搬回 `article_commands` 的 `cog_load`、Telegram 組裝搬進 `telegram_relay_service`；入口仍由 `discord_bot.py` 決定什麼時候跑什麼、順序與接線。**待確認**：cog 自己的計時器要不要也改由 `discord_bot.py` 登記——建議不要，入口只排跨功能的排程；現況已照這個做（週期提醒、/askai 排隊、市集排程都在各自的 cog 裡起），使用者沒明說過。
- **N3** 剩下：`utils/utils.py` 拆出 `ChannelConfig`＋頻道 getter（`channel_config.py`）與互動回覆、分頁；`settings/channel_registry.py` 搬到 `utils/`（名稱不變，`test_layering.DISCORD_HELPERS_IN_BASE` 跟著改）。和 `architecture-review-2026-10` 的候選 6（c3）一起做。建議做，排在純改名之後。等使用者。

**待做**
- [ ] N1：命名慣例（只改會誤導的、正名表）寫進 AGENTS.md。

---

## 情報搜尋（MCP）：官網公告、官方 FB、PTT、巴哈

<!-- @meta
id: mcp-search-tools
type: STATE
status: draft
last_confirmed: 2026-11-07
affects: services/search、llm/mcp_server.py、.mcp.json、docker-compose（search-mcp、run/gpu_lock）、cache/search-mcp/、pgvector data_search_chunks、Lemonade（embedding、reranker）、/askai（llm/retrievers/intel、llm/retrievers/web、LLMService.generate_reply 的工具輪）、scraper/db/models.py（四個 updated_at 索引）、config/searxng/settings.yml
history: dev/ai/search.md
-->

**現況**（全部已 commit、已推送）
- 讓模型自己決定要不要查。compose 服務 `search-mcp`（stateless HTTP `127.0.0.1:8765/mcp`，`.mcp.json` 也指這裡），Claude Code 與 bot 共用；bot 當 MCP 客戶端（`llm.retrievers.intel`）。Telegram 內鬼頻道、依 ID 查人不納入。
- 開關：`search_vector_mode`、`search_rerank_mode`、`askai_intel_search_mode` 都 on；`askai_web_search_mode`＝tool（SearXNG 包成 `web_search`，和情報工具同一個工具輪）。
- 索引 `cache/search-mcp/search_index.db`（容器內 `/search_data`，可刪掉重建約 3.5 分鐘）。10-09 時 11.2 萬份文件（公告 543、FB 874、PTT 5.5k、巴哈 10.5 萬樓）；向量只做 2026 年起的 1.8 萬段（`vector_since`；巴哈只做攻略、心得、情報、問題四類）。背景每 50 秒同步，每天 03:00～04:00 補算向量。
- 流程：全詞（FTS5 trigram）＋兩字組 BM25＋單字 LIKE → 向量（距離 ≤ 0.35）RRF（k=60）合併 → 前 30 篇 reranker 重排（讀 `question` 原句）→ 每種來源最多 5 筆、共 20 筆。向量或重排壞掉、等 GPU 超過 10 秒，都退回關鍵字結果。
- 評估在 search-mcp 跑 `python -m services.search.eval.evaluate --label 名稱`；Agent 評估在 discord-bot 跑 `python -m test.integration.it_askai_agent_eval --label 名稱`（約 1.5 小時，避開維護時段）。交付文件：https://claude.ai/code/artifact/11a03b1e-558a-4ac5-8253-71c35e8b9d57

**用語**
- 來源：官網公告、官方 FB（官方）；PTT、巴哈（玩家說法）。
- 文件：可以直接給人連結的一篇，是搜尋與評分的單位。巴哈是一個樓層，不是整串（最大的串 11,234 樓）。id：`article:`、`fb:`、`ptt:`、`bahamut:<sn>`（`post_id#position` 有重複，不能當 id）。
- 段落：算向量的片段（約 500 字、重疊 80 字、每段帶標題）；命中任一段就算命中那份文件。
- 考卷、正確答案（讀了就能回答，一題可有好幾篇）、只答一半（預設不算對）。

**評估方法**
- 考卷 `eval/questions.json` 42 題（情報 30、攻略 12），使用者逐題確認過；證據句在 `eval/private/`（不進 git）。原句模式＝群友原句直接搜；關鍵字模式＝沒看過答案的子 agent 改寫（`keyword_queries.json`）。排名看實際回傳的那串（含來源上限）。
- 防過度擬合：考卷依分類交錯拆 A、B 兩半，在 A 選設定、在 B 驗收，兩半方向一致才採用。
- 這份考卷 10-12 已經把失敗原因全看過，之後只能拿來找問題，不能驗收由它找出來的修法；驗收要用新題目。

**評估結果**（每次評估加一列；報告在 `eval/reports/`，沒寫日期的檔名前面是 `20261008-`；P1、P1.5 沒量 Recall／nDCG）

| 版本 | 改了什麼 | 模式 | H@1 | H@5 | H@10 | MRR@10 | R@10 | nDCG@10 | 情報 H@5 | 攻略 H@5 | 報告 |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| P1 | 三字組＋2 字詞 LIKE＋簡轉繁 | 原句 | 14% | 21% | 36% | 0.195 | — | — | 30% | 0% | `1203-P1-FTS5基準線` |
| P1 | 同上（事後還原程式補量） | 關鍵字 | 33% | 60% | 62% | 0.439 | — | — | 70% | 33% | `1238-P1-補量` |
| P1.5 | 兩字組 BM25；一個字才 LIKE | 原句 | 29% | 38% | 52% | 0.336 | — | — | 53% | 0% | `1236-P1.5-兩字組` |
| P1.5 | 同上 | 關鍵字 | 43% | 71% | 74% | 0.530 | — | — | 80% | 50% | 同上 |
| P3 | 向量（2026 起 1.8 萬段）＋RRF，門檻 0.35 | 原句 | 36% | 55% | 67% | 0.446 | 38% | 0.336 | 63% | 33% | `1554-P3-不重排-新指標` |
| P3 | 同上 | 關鍵字 | 45% | 74% | 79% | 0.559 | 55% | 0.476 | 77% | 67% | 同上 |
| P4 | 前 30 篇重排 | 原句 | 48% | 67% | 71% | 0.555 | 46% | 0.433 | 73% | 50% | `1609-P4-重排前30篇` |
| P4 | 同上 | 關鍵字 | 31% | 74% | 76% | 0.483 | 46% | 0.389 | 77% | 67% | 同上 |
| P4 原句重排 | 重排讀原句，挑段落仍看查詢字 | 原句 | 48% | 67% | 71% | 0.555 | 46% | 0.433 | 73% | 50% | `1705-P4-重排用原句` |
| P4 原句重排 | 同上 | 關鍵字 | 48% | 81% | 81% | 0.596 | 54% | 0.482 | 83% | 75% | 同上 |
| 10-12 對照 | 程式沒變，外部 agent 查詢在 10-12 索引重跑 | 關鍵字 | 48% | 81% | 81% | 0.596 | 54% | 0.482 | 83% | 75% | `20261012-0918-對照-外部agent改寫` |
| 10-12 Agent 重放 | 查詢換成正式模型在 /askai 第一次 search 自己寫的（前 20 筆） | 關鍵字 | 40% | 71% | 76% | 0.533 | 49% | 0.429 | 73% | 67% | `20261012-0917-Agent-模型自己寫的查詢` |
| 10-12 Agent 實際 | 模型實際看到的前 6 筆：第一次／任一次 search 最好的 | 模型自己寫 | 38%／52% | 71%／79% | — | 0.515／0.628 | — | — | 73%／80% | 67%／75% | `20261012-0745-Agent評估-正式模型` |

- P1 → P1.5：原句 +17、關鍵字 +11 個百分點；客戶端改寫成關鍵字 +33～39，影響更大。代價：原句平均 23 → 87 ms、索引 242 → 299 MB、重建 55 → 204 秒。
- P3：門檻只用 A 半的距離分布選（A 半 MRR 0.403，只用關鍵字 0.391），B 半驗收 0.476 → 0.602。攻略題原句 0% → 33%；答案有向量的 22 題原句 H@5 77%，沒有的 30%。只有 1,000 份有向量的預覽版反而變差（原句 38 → 29%）：混合檢索兩路要涵蓋同一批資料、向量要有門檻。
- P4：reranker 讀關鍵字斷片會判錯（關鍵字模式 MRR 0.559 → 0.483），改讀原句後 0.596（A 半 0.471 → 0.563、B 半 0.647 → 0.629）。還沒過的題多是暱稱（家主、汐汐、水母）與答案只在沒向量的舊資料。
- Agent 評估（42 題＋6 題閒聊，每題只跑一次）：該查的都查、閒聊都沒叫工具；模型自己寫的查詢比外部 agent 差 6 題、好 2 題（p≈0.29，不顯著）。回答（Claude 初判，使用者未確認）對 31、半對 2、錯 3、說查不到 6；0 題附了工具結果裡沒有的連結。每題中位 71 秒、最久 411 秒。沒答對的 11 題：search 沒找到 8、沒輪數讀全文 2（q25、q39）、讀了別篇 1。
- 速度：向量化約 4,600 字／秒；重排 30 篇約 1.6 秒（第一次載入 24 秒）。

**仍有效的規則與坑**
- 只開 `search`、`fetch` 兩個工具（工具少模型選得準）；加來源＝在 `sources.py` 加一個 `Source`。不用斷詞詞典（角色名與暱稱一直增加）。
- 查詢加任務說明、文件不加；`question` 只給重排用（reranker 要讀自然語言問句），挑段落仍看查詢字。重排的物理批次要 `-ub 1024 -b 1024`，預設 512 token 時段落＋問題超過就整次失敗。
- 同步游標 (updated_at, 列 id)＋內容 hash（巴哈每天約兩萬列只是最後看到時間變了）。`articles.db` 的 `ix_<表>_updated_at_id` 是直接建的、沒走 Alembic，`scraper/db/models.py` 照樣宣告。索引版本只升不降（舊行程遇到新索引丟 `IndexTooNew`）。
- discord-bot 沒掛 `/search_data`，在那裡跑搜尋會直接失敗、不會另建一份。單元測試在 `test/__init__.py` 強制把 GPU 鎖檔換成暫存檔（不能 `setdefault`，容器的環境變數已經有值）。
- compose：search-mcp 共用 bot 的映像（另做精簡版會讓共用程式與 opencc 版本分岔）；不帶 Discord token、Telegram 憑證（開 port 的行程不該握 token）；Host 白名單防 DNS rebinding。`run/gpu_lock` 不能改 named volume：會歸 root，appuser 建不了鎖檔，兩邊各排各的隊。
- 爬蟲不直接寫搜尋索引：索引本來就要能從 `articles.db` 重建，雙寫失敗會漏、文字整理會變兩份。要更即時就讓爬蟲寫完通知 search-mcp 同步。
- /askai 工具輪（機制見 AGENTS）：模型漏帶原句時客戶端補上；全文截到 2,500 字（`fetch_max_chars`）；工具回傳與 web_context 在安全規則裡列為不可信；網址上限 3 個；每輪思考設定與工具宣告相同（理由見 `llm-inference-kv`）。對話請求等回應逾時不重試、/askai 回答有長度上限 `answer_max_tokens`：重試會讓寫不停的回答拿著 GPU 鎖 15 分鐘。
- 網路搜尋純免費：不註冊、不要 key、不破解真人驗證（WARP、付費代理、要 key 的 API 都不用）。SearXNG 新版自動解的 JS 挑戰與工作量證明可以用，但照官方預設開關。天氣定案先觀察（常有人問再接中央氣象署 API）、股價不做台股類型。
- 引擎：一般搜尋 `yahoo,duckduckgo`（`AskAIWebSettings.default_engines`）。bing 回垃圾時 SearXNG 不算錯、會混進結果（出過成人內容、只查第一個字）；yandex 出過成人內容，不進預設。10-16～17 的 24 小時測試：yahoo 72 次全查得到、全對題；bing 對題 71%。新聞：duckduckgo news 不限時間、照日期新到舊排；bing news 不給日期，保留一週條件、排在有日期的後面。
- 引擎被擋主因是連線特徵不像瀏覽器（TLS 指紋、標頭順序），不是查詢量或封 IP；SearXNG 2026.10.16 起網路層用 curl_cffi。`docker compose up -d` 不會自己 pull。IPv6 輪換、Tor、多代理、第三方外掛評估過都不採用；也沒有開源自架、免 key 又勝過 SearXNG 的通用搜尋。

**未定案**
- 閒置後第一次搜尋很慢：計時已寫進 log（超過 3 秒記各步耗時）。10-09～11-06 共 90 次超過 3 秒、中位 10 秒，最慢那步：向量 46 次（多是等 GPU）、關鍵字 27 次（最久 137 秒）、重排 17 次。選項：(a) 接受；(d) 縮小讀取量（例：很常見的兩字組設上限）；(c) 定時暖快取（搶記憶體，不建議）。建議先看關鍵字慢的那幾次是哪類查詢再決定 (d)。等使用者。
- 向量那一路要不要也用原句：建議照重排的做法加進評估量一次再決定。
- 放寬「最多查 2 輪」：確定被輪數卡住的只有 q25、q39（第 2 次 search 已排第 1，沒輪數 fetch），其餘 7 題是搜尋沒找到。選項：(a) 上限 3；(b) 第 3 輪只准 fetch；(c) 不改。原建議面試後先試 (b)（面試已過），用沒看過的題目驗收，正確率和每題秒數一起報。等使用者。
- 工具說明加「不用加遊戲名稱、只放最關鍵的兩三個詞」：7 題第一次查詢加了「鳴潮」，q08 多加「角色」從第 1 掉到第 19。`llm/mcp_server.py` 的說明還沒改。建議改，前後各跑一次。等使用者。
- 輪數與全文 2,500 字是估的：建議看 `askai_response_history.jsonl` 的 `intel_meta` 與 `web_context_meta.calls` 再調（輪數情報與網路共用）。還沒看。
- W5 刪掉網路搜尋的關鍵字模式（`askai_web_search_mode=keyword`、`intent.should_search`、`_ROUTE_RULES`）：定案是工具模式真的有人用過再刪，現在還在。待確認使用狀況。

**待做**
- [ ] 套用 W8（10-17 定案；`config/searxng/settings.yml` 是使用者的檔，由使用者換上、先備份）：改成 `use_default_settings: true` 只留覆寫值——`request_timeout` 2.0 → 3.0、openmeteo `timeout: 4.0`、`max_request_timeout: 4.0` 要留、刪掉 9 筆圖片引擎的舊值、google cse 照官方；`.env` 加隨機 `SEARXNG_SECRET` 後 `docker compose up -d searxng`（restart 不吃新環境變數），不急。11-07 查：檔案仍是舊範本全文（2,780 行），草稿在舊 session 的 scratchpad 已不在，要重做草稿並重算前後差異。可順便試：duckduckgo（html）送 Chrome 特徵卻自稱 Firefox，可在 settings.yml 覆寫 `_HTTP_User_Agent`（未實測）。
- [ ] 舊資料（2025 年以前）補向量，補完再量一次。
- [ ] 暱稱對照表（家主＝坎特蕾拉、汐汐＝今汐、水母＝坎特蕾拉、里哥／要哥＝相里要…），前後都要量。
- [ ] 向量的模型指紋：向量表沒記是哪個模型算的、hash 只看文字，換 embedding 模型會新舊混用且不報錯。要補時一個模型一張表、用考卷比較後切換（pgvector 維數是欄位型別的一部分；HNSW 上限 2,000 維，更大用 `halfvec`）。
- [ ] 考卷擴充到 100 題以上，分調參用與驗收用（上面兩題的驗收都等它）。
- [ ] 選配：微調 reranker 或 embedding（考卷不能拿來訓練；合成問題＋難負例）。
- [ ] 爬蟲只在內容真的變時才動 `updated_at`，之後再議。
- [ ] 小毛病：FB 標題是內文第一行；巴哈串改標題舊樓層不更新；長期更新的整理串日期停在建立日；3.1 版本內容說明爬蟲漏抓；有些公告內文只在圖片裡；`AskAIWebSettings.timeout_seconds` 的註解以為 SearXNG 最長等 4 秒，實際是 min(引擎 timeout 最大值, `max_request_timeout`)＝2 秒；compose 的 `UWSGI_*` 在新版沒作用。

（經過見 [dev/ai/search.md](dev/ai/search.md)）

---

## 架構審視與滾動修正

<!-- @meta
id: architecture-review-2026-10
type: TODO
status: draft
depends_on: mcp-search-tools
affects: 全專案的分層、背景任務、設定與持久化、測試 gate、重複的輪子
last_confirmed: 2026-11-07
history: dev/architecture/review.md
-->

10-12 靜態掃描找出 11 項結構問題，之後逐項修；10-17 第三輪找「同一件事寫好幾份」的地方，10-27 架構總覽頁再找一次。（經過見 [dev/architecture/review.md](dev/architecture/review.md)）

**現況**
- 已收並上線（規則都在 AGENTS.md）：分層方向與守衛 `test_layering`；技術層、服務層不 import discord；背景任務走 `utils.background_tasks`；`on_ready`、`_handle_askai_request`、`_run_one_ambient_pass`、`_retrieve_rag_context_impl` 拆段；路徑收進 `sys_settings.paths`、bot 寫的 JSON 收進 `settings/runtime/` 走 `utils.runtime_file`；錯誤邊界守衛 `test_error_boundaries`（BASELINE 只准減）；notify 端點要共用密鑰（沒設只警告）；啟動 gate 只跑 `src/test/gate.py` 的守衛。
- 沒收完的發現：③單一行程扛全部（M9，只有設計草稿，見未定案）；⑦套件撞名（M6 只做縮小版：bot 與 telegram-scraper 共用的定義放 `src/shared/`；scraper 容器裡的 `services`、`utils` 仍和 bot 同名）；⑧工具鏈（ruff／pyright 設定與 `make lint`／`make typecheck` 在，但主機與容器都沒裝；`.gitlab-ci.yml` 推上 GitLab 後 lint 階段會紅，見 RG-Q19）；⑩`/anonymous` 與 `test_commands`，使用者說先不管（見 `command-consolidation-dashboard`）。
- 重複的輪子：編號用架構總覽頁（artifact `Sg8HV3t3Po8MhSXzt1p4hC` 第 17 段，26 組，行號對 `f5fd16d`）。10-17 第三輪的 c1～c10 對應：c1＝3、c2＝5、c3＝6、c4＝2、c5＝10、c6＝11、c7＝16、c8＝13、c9＝17、c10＝14。
- 已收：候選 1、4、9、20、22、25（10-28）；第三輪的 X1 巴哈開串後馬上記、c4a 送出鎖 `content_send_lock`、c9 第一步 `pgvector_vector_store`、B2 被 @ 的人進人物卡檢索、B6 插話長回覆切段且不 @ 人（10-18）；c6 的先算向量再刪、B4 raw 逐筆保存點（10-28）。全部已推送、已上線。
- 架構總覽頁的候選狀態已標到 10-28；改候選狀態時換掉舊內容，不追加。

**仍有效的規則與坑**
- 分層定案：`llm_service` 留在 `services/`；碰 Discord 的 AI 功能（`llm/ambient`、`llm/storage`）留在 `llm/`，使用者看過搬與不搬的對照選了不搬。把 `llm_service` 搬進 `llm/`（M2b）提過、被退回，不要再提。
- c7（候選 16）要在插話上網查第二版（全開＋存筆記＋淡出）之前做；插話新加的參數先收成一份插話專用設定（AR3-Q4）。
- X3 改了會改變檢索結果，改之前先離線對照。
- 10-16 第二輪照建議定的（已結案）：點名只在 14:00 後一小時內做、日記排定時刻後 10 分鐘內寫，重啟錯過不補；對話逾時不重試、/askai 上限 4096 token；不釘套件版本（見 `code-structure-reorg` 的 S6-2）；M10（文件拆兩份）不做。
- 流程上的坑：暫存區是使用者邊看邊暫存的紀錄，不要 `git reset`；啟動 gate 在跑時不要在同一台機器並行跑測試副本（搶 CPU，靠時間的測試會誤紅）；使用者在 IDE 開著交接檔時，寫完要重讀確認（曾被編輯器的舊緩衝蓋回），並提醒他重新載入。

**未定案**
- **DW-Q2** 候選 8「讓路與維護時段的判斷」（「前景忙不忙」寫 5 處、維護時段的時刻 4 處）收成一份：10-28 提議併進第一批，使用者沒點頭、沒做。建議排進下一批（碰插話檔兩行）。等使用者。
- **DW-Q3** 下一批順序：10-28 建議先做候選 5 連 7（都碰 `chat_search`），候選 6 排後面、和拆 `utils.py` 一起；二選一時 5 優先。c10 要開新資料夾 `src/test/fakes/`，先問。其餘照下方「剩下的候選」的順序。等使用者點。
- **DW-Q4** 候選 21：刪 `scripts/reembed_pgvector.py`、只留 `llm/storage/chat_reembed.py`。建議刪：前者不拿 GPU 閘門，和 bot 同時跑會搶顯示卡。同題另問 16、17、19、26 先放著，15、18、23、24 排最後。**待確認**：16＝c7、17＝c9 在 10-17 順序裡排著要做，和「先放著」矛盾，問的時候一起釐清。等使用者。
- **X2**（無題號）群友刪掉的訊息還留在聊天向量庫：刪除事件只在 raw 標記，向量庫沒有刪除的路徑（10-17 時 raw 標成已刪 1,241 則、779 則還在），插話回憶與 persona agent 撈得到。選項：A 之後的刪除同步刪向量、既有的備份後刪／B 只同步之後的／C 不刪。這是產品與隱私的決定；建議和候選 10（聊天向量庫的主人）一起定，刪既有的要先備份、經使用者同意。等使用者。
- **runtime 檔照意義拆**（無題號）：`settings/runtime/*.json` 混著「透過 Discord 設的值」與「bot 自己的紀錄」。10-14 使用者選 (a) 只改位置與名稱（已做）；(b) 照意義拆、Discord 設的值併進 config.json（以前怕整份覆寫，現在 `update_config` 是安全的讀改寫，理由不成立）列為之後再決定。會搬資料檔，要先備份並取得同意。等使用者。
- **RG-Q19** GitLab CI 的 lint（`ruff check src`）紅：10-27 全 repo 107 個錯，多數是未用的 import、空 f-string、`raise` 沒 `from`；`scraper/api_server.py` 的 FastAPI `Depends()` 12 個是慣用寫法，該用設定放行；2 個「未定義名稱」都是字串型別註解（`llm/mcp_server.py` 的 `"uvicorn.Config"`、`scraper/services/base_scraper_client.py` 的 `"curl_cffi.requests.Response"`），不會真的出錯。選項：A 清乾淨（`ruff --fix` 安全修正＋手修＋設定放行，另成一個 chore commit）／B lint 加 `allow_failure: true` 先看測試階段／C 不管。建議 A，動 scraper 的檔前先問。等使用者。
- **M9** LLM 背景工作拆 worker 行程：設計草稿在本機 `doc/llm_worker_design.md`（不進版控）：聊天記憶寫入、raw 備份、每日維護、日記、看圖補字典、補寫搬到新容器 `llm-worker`，/askai 與插話留在 bot。要先討論再做。等使用者。
- **待確認** 人物卡檢索的候選排序：`context_retriever` 去重後的排序表沒有 `sql_participant`，在場者那一路排在語意檢索之後（卡片產生器自己依來源加分，卡片順序沒受影響）；裁切那段現況走不到、留作安全網。兩者寫在模組說明的「例外與決策」，當時說「等 /goal 結束一起決定」，之後沒人提。

**剩下的候選（建議順序，等 DW-Q3）**
1. 候選 5（c2）「這個名字是誰」：「這份資料屬於誰」6 處、@ 轉 id 4 份、id 換名字兩套；併 X3（`persona_card_builder.expand_alias_candidates` 把候選詞依字碼排序後只取前 8 個，「米拉你今天怎麼了」認不出米拉）與別名路的 `ILIKE ANY` 沒跳脫 `%`／`_`（`context_retriever` 的 sql_alias）。
2. 候選 7 工具執行的外殼：網路、情報、聊天紀錄三份 `execute` 逐行相同，插話查詢再包一層、計時兩次；參數解析寫了 5 份。
3. 候選 13（c8）人格疊層、人物卡蒐集與訊息轉模型輸入：/askai 與插話各一份，3 個測試比對原始碼字串。
4. 候選 14（c10）共用 Discord 測試替身：兩份假世界、11 份 Interaction 替身，兩份對「封存的 thread 拿不拿得到」行為相反；要開 `src/test/fakes/`，先問。10-17 原順序排在 c2＋c8 之前。
5. 候選 11（c6 剩下）＋17（c9 剩下）＋12，一批：偏好與招牌梗「讀、+1、升級、寫」兩份、衰減公式兩份、`/forget_tag` 的擁有者檢查只在指令層；連線參數三處各自組、`ai_interactions_store` 十段連線樣板沒改用 `pgvector_cursor`、7 個模組把 `pgvector_connect` 再包一層；raw、聊天記憶、插話記憶三份緩衝的門檻與失敗處理不一致、embedding 快取 4 份。併 B5（反應熱度斷線時 rollback 再拋例外，唯一的呼叫端當成空的，log 看不到）與 10-28 記下的：插話記憶遇後端故障不重試、raw 連不上時整批放回緩衝、`deleted_at` 用 COALESCE、連線池加 connect_timeout。
6. 候選 16（c7）：`generate_reply` 31 個參數、`_get_llm` 6 份、4 處直接 `LLMService()`；插話專用設定整包搬進用途入口。
7. 候選 2（c4）網站轉發骨架：公告、FB、IT、PTT 的送出與記錄收一份（「每 10 張一批」多份、發文用的圖片下載 3 份）；併 B3（主文貼出就記已送、退純文字時跳過太大的檔）。不碰插話檔，可穿插。
8. 候選 3（c1）Telegram 投遞單位：相簿與單則兩份外層流程、「送到哪」5 處、12 小時規則 3 處各用不同起算點、測試直接呼叫私有的 `_process_one`；併 B1：送失敗每小時重試（10-05 定案 T10-Q2）、頻道 0 自動寫入、有文字的單則補圖（見 `telegram-llm-filter-quarantine`）。
9. 候選 6（c3）讀綁定頻道與 config.json：讀法多種、`utils.utils` 還有 5 個功能專屬的頻道 getter、點名 runtime 的 `channel_id` 只寫不讀；和 `code-structure-reorg` 的 N3 拆 `utils.py` 一起。
10. 候選 10（c5）聊天向量庫的主人：直接用 SQL 讀它欄位的有 5 個模組；併 X2，和 M9 第一步一起定。
11. 候選 8（DW-Q2）、21（DW-Q4）。
12. 排最後：15 分頁與編輯視窗樣板（交易、測試指令、社群查詢、`create_paginated_view` 的呼叫端）、18 巴哈同步入口兩份（推送那邊「執行中」旗標放太早；看板 74934 寫死 4 處）、23 Telegram 資料庫的連線字串與建表 bot 和爬蟲各寫一份（放進 `shared/telegram`）、24 爬蟲 API 公告、FB、PTT 端點各自填欄位；先放著：19 爬蟲與 bot 的通知協定兩邊各寫、26 依長度把多則項目分段（PTT 推文、巴哈留言格、社群查詢）；r1～r6（綁定時部署面板、自介投稿、關鍵字監看、巴哈訊息鏈、StateDB、點名），用量低，自介投稿與關鍵字監看沒有測試。

**待做（候選以外）**
- [ ] M6 完整版：scraper 容器裡的 `services`、`utils` 改名（同一個 repo 兩套同名套件，掃描會誤判）。
- [ ] 主機或容器裝 ruff、pyright 跑一次（`requirements-dev.txt`、`make dev-tools`）。
- [ ] 資料庫沒有任何自動備份：`data/backups/` 只有 10-26 手動的一份 pg_dumpall，crontab 是空的。要不要排定期 pg_dumpall，使用者沒答（市集資料庫的每日備份另記在交易區塊）。
- [ ] 資料目錄整理剩兩件：src/ 底下的資料（`articles.db`、`sent_articles.db`、`settings/runtime`、Telegram session 與 media、`music/cache`、`scraper/data`）另開一輪；`logs/` 裡的 runtime_backup、dictionary_backup、config_backup 要不要搬到 `data/backups`。搬資料檔要先備份、取得同意。
- [ ] 新資料庫第一次寫入時剛好連不上，表就建不起來，要重啟才會再建（舊版也一樣）。
- [ ] 10-28 第 3 步記下、另排的：自介與印象寫入失敗時使用者照樣看到成功（舊內容留著）；每晚發布遇到後端故障要一人一人等逾時（建議第一筆就停）；偏好與招牌梗的向量沒有讀取端在用。

---

## LLM 推論：KV cache、prompt 快取與 GPU

<!-- @meta
id: llm-inference-kv
type: STATE
status: draft
last_confirmed: 2026-11-07
affects: Lemonade（Windows 主機）、services/llm_service.py（llm_usage log）、插話與 /askai 的 prompt 順序、sys_settings/llm_runtime_config.json（model_load_options）
history: dev/ai/llm-backend.md
-->

**現況**
- Windows 主機 2 張 AMD RX 9060 XT（各 16 GB）、128 GB RAM；這台 Linux 是同機的 VM（7.7 GB）。Lemonade（llama.cpp、Vulkan）：主模型兩張卡、`--spec-type draft-mtp`、`--parallel 1`（Lemonade 自動補）、ctx 65,536；embedding 綁 `-mg 1`，reranker `-mg 0`（`llm_runtime_config.json`）。
- 主模型是混合注意力（64 層裡 16 層完整注意力）：KV 每 token 64 KiB（F16），64k 約 4 GiB；線性注意力層每槽另有固定狀態（估 150 MB）。讀 prompt 約 330 tok/s，產生 22～35 tok/s（超過頻寬上限約 18 tok/s 的部分靠 MTP）。
- 每個請求記一行 `llm_usage`（`services/llm_service.py`：功能、prompt、cached、重算、毫秒、tok/s）。被擠掉的快取存在系統 RAM（`--cache-ram` 預設 8 GiB）。
- 11-04 量：插話 1,334 次只有 3.4% 沒命中前段 9,516 token（工具宣告＋整段 system）；平常新算約 2,700 token（約 10 秒），整段重讀約 12,000 token（約 35 秒）。只有維護時段的 batch 會把它洗掉。system 段 token：身分 174、守則 1,987、插話行為 3,879、範例 1,856、查詢規則 409、安全 301、工具宣告與模板約 910。

**仍有效的規則與坑**
- prompt 擺放：①動態內容（日期、心情、人物卡、撈回的舊話、會輪換的範例）放 user 段，system 只放不變的；②自發、被 @、接續共用同一份 system，不拆兩份（少用的那份容易被擠掉）；③改 system 任何一處，該模式下一次要重讀那處之後的全部（最多約 35 秒、一次），所以一次改完再存；④`ambient_search_mode` 切 on 不動工具宣告，不會讓快取失效。
- 不要做：「共用人格放最前面」（模板把工具宣告放在 system 之前，各模式工具不同，前綴一開始就分開）；user 段重排（連續兩筆在 chat_history 就分歧）。
- 思考設定會改 prompt 開頭：主模型模板在思考開、`reasoning_effort` 預設時，在 system 開頭插一句英文，思考關沒有，從第 3 個 token 起就不同。所以工具迴圈每一輪用同一種思考設定與同一份工具宣告（/askai 的決策輪因此拿掉）；換 `ambient_reasoning_effort` 第一次會整段重讀。換模型時的驗法：同一份 messages、`max_tokens=1`，依序送思考關→開→開，比三次的 cached。
- 物理批次（`-ub`，預設 512）：embedding 與 reranker 的整段輸入要放進一個物理批次，超過整次失敗；產生文字的長 prompt 可分批讀。`--parallel N`：權重一份，context 由各槽均分（除非 `--kv-unified`），檢查點每槽各存在 RAM。
- 讀 Lemonade log：port 13305 的 `/logs/stream`（websocket，送 `{"type":"logs.subscribe"}` 先回最近 5,000 行），看不到是誰送的，要對 bot 的 `llm_usage`；各模型忙不忙看 `/api/v1/health`。
- 方向（R7、R8 定案）：先顧回應快；KV 維持 F16。實驗在 VM 經 Lemonade 跑、使用者看工作管理員記 VRAM／RAM；動正式載入參數前先問使用者。

**待做**
- [ ] `--parallel` 實驗六組：①現況 1 槽 ②4 槽均分 ③4 槽 `--kv-unified` ④1 槽 131k ⑤KV q8_0 ⑥2 槽、兩種長 prompt 輪流送、比帶不帶 `id_slot` 的首字等待。①～③各測同時 1／2／4 個請求，量首字等待、單一與總 tok/s、命中、兩張卡 VRAM、RAM。主模型的 `-ub` 也放進來。順便查：一張卡 11.8 GB、另一張 0 GB，但權重 17.56 GB 放不進一張卡；系統 RAM 約 92 GB 已用、處理程序只加得到約 16 GB。
- [ ] 低優先：10-09 有三題分歧點在 system 結尾附近，快取卻停在 6,858（可能混合架構只能退回檢查點）；兩題 cached=0，原因沒查。

（經過見 [dev/ai/llm-backend.md](dev/ai/llm-backend.md)）

---

## Hermes 串接（暫停）

<!-- @meta
id: hermes-integration
type: TODO
status: blocked
last_confirmed: 2026-11-07
depends_on: llm-inference-kv
affects: docker-compose.yaml（hermes 服務）、services/llm_proxy、data/hermes/
-->

這塊原本只記在盤點紀錄（10-21～10-26 各輪；原文在 `dev/journal/2026-10.md`）。使用者 11-04 說先專注 bot 的提示詞架構與琇紫人格，Hermes 的架構與容器不算設計條件，等他重提才談。

**現況**
- bot 對外的模型端點 `services.llm_proxy.LlmProxy` 掛在通知伺服器的 `/v1`（用法與「bot 叫 Hermes 時不可拿著 GPU 閘門」寫在 AGENTS.md 共用元件表）；10-26 Hermes 端到端打通，`config.yaml` 已關 `background_review`。
- compose 的 hermes 服務仍是 `stable` 映像加 `profiles: ["hermes"]`；`SOUL.md` 在 `data/hermes/SOUL.md`（不進版控）。

**未定案（暫停中）**
- HM-Q4 映像要不要釘版：`stable` 10-26 已悄悄變成 0.22.5；最後一次建議釘 `v0.22.2`。
- HM-Q6 拿掉 `profiles`、當一般服務（最後的建議）：連帶改註解裡多餘的 `--profile hermes`，setup 改成 `docker compose run --rm --no-deps -it hermes setup`。
- `SOUL.md` 要不要進版控：建議搬到 `config/hermes/SOUL.md` 再唯讀掛進容器（新資料夾，等使用者點頭）。`config.yaml` 範本要不要也放進 `config/hermes/`。
- 和 bot 共用人格檔（11-04 查的，只當日後參考）：Hermes 路徑固定是 `$HERMES_HOME/SOUL.md`，要共用就掛人格目錄再放 symlink；掛載不在時 symlink 懸空，Hermes 改用預設人格、不報錯。人格檔要單檔自己成立、不放 bot 專屬格式、底線和調情設定放在一起。

**待做（暫停中）**
- [ ] `gateway.api_server.max_concurrent_runs` 沒設，建議設 1。
- [ ] 讓位與優先序：Hermes 一題打 9 次模型、花 115 秒。建議沿用 `foreground_recently_active`，避開 /askai 結束後 90 秒；`gpu_exclusive` 重入改成直接丟錯（建議要）。
- [ ] bot 端呼叫 Hermes 的客戶端與指令還沒寫。服務順序建議：日報 → 週報 → /配隊 → 補課交接檔，等使用者選（反方意見：日報與 /配隊 用現有的工具輪也做得到）。
- [ ] bot 重啟時 Hermes 進行中的 run 沒人收。
- [ ] 模型名在 bot 和 `config.yaml` 各寫一份，bot 換模型時 Hermes 會被擋；建議 bot 的 `/v1` 一律換成自己正在用的模型（現況待確認）。
- [ ] Hermes 對「最近」的解讀偏寬；「對方斷線就放閘門」沒有自動測試。

---

## Telegram 訊息過濾＋隔離區

<!-- @meta
id: telegram-llm-filter-quarantine
type: TODO
status: draft
last_confirmed: 2026-11-07
depends_on: telegram-catchup-sweep
affects: Telegram relay、settings/switches.json、telegram_relay_delivery_state（頻道 0、needs_recheck）、telegram_scraper（S1～S4）
history: dev/relay/telegram.md
-->

**現況**
- 來源三個 Telegram 廣播頻道（`Seele_WW_leak`、`Gamedataleak`、`Sleep_Leaks`），垃圾是頻道管理員自己發的；目的頻道只有 #🌘角色內鬼情報。
- 轉進前先判（`services/relay/telegram_filter.py`，規則寫在模組說明）：文字點名 `settings/telegram_other_games.json` 的別款遊戲就隔離、不問模型；其餘主模型看文字＋最多 4 張圖。沒有遊戲資訊就送進該頻道底下的「垃圾訊息」thread，第一行寫判定。開關 `switches.json` 的 `telegram_filter_mode`（現在 `on`），一次處理一則。prompt `settings/prompts/telegram_filter_prompt.txt`。
- 放回與搬入：thread 置底面板（日期→訊息→確認）放回主頻道；主頻道訊息右鍵→應用程式→「移到垃圾訊息」（`commands/telegram_quarantine_commands.py`，限 07-25 起、沒放回過的轉發）；都要「管理訊息」權限。批次搬舊貼文用 `scripts/telegram_move_to_quarantine.py`。
- 判決記在 `telegram_relay_delivery_state`：主頻道、隔離 thread、頻道 0（停止追蹤）；`needs_recheck`＝模型沒判就放行的，恢復後補判、判成垃圾就搬走。
- 離線抽查 `test/integration/it_telegram_filter.py`（樣本與期望值在檔內 `SAMPLES`）。
- 爬蟲端下載走 `media_download.fetch_media_file`（AGENTS 共用元件表）。

**仍有效的規則與坑**
- 名單只比完整單字（`nte` 不分字界有 38 個單位會誤中）。點名其他作品但是鳴潮情報的不能關（賽博朋克聯動、「参照战双 X 鬼泣五」、第二索拉）。
- 樣本原文不能放進 prompt 當例句，離線分數會虛高。
- 判斷用主模型關思考，不另開審核模型（後端一次只放一個大模型）。被拒絕或中斷的 `docker exec` 行程在容器裡還會跑、會佔著模型。
- 頻道 0 只影響重啟時的啟動補償（只撈完全沒有發送紀錄的）；每小時輪詢只看游標。目前只有「發文超過 `max_message_age_days`」會寫頻道 0。
- 搬移腳本是另一個行程：判斷最多等 600 秒，佔著模型時插話與過濾都要排隊，整批搬避開熱鬧時段；它擋不住補圖，相簿要等 12 小時才能搬（右鍵在 bot 行程裡，不用等）。
- 刪媒體檔時：只刪檔、留媒體列（列刪了爬蟲會重新下載）；同一檔可能多則共用（檔名依 photo／document id），刪前查別則有沒有用；確定送出並寫好發送紀錄才刪；補判、搬移、`/resend_article` 都要讀檔。
- 放回時檔案不見只記 WARNING、只送文字，照樣回報已放回；`telegram_emoji_refetch` 補不回檔（有媒體列就不下載）。
- `6262568681327303499.mp4`（pk 4068）被舊下載流程寫壞，11-03 已刪檔留列；`/resend_article` 重發 pk 4068 會少影片，要救只能從 Seele 訊息 6764 手動重下。

**未定案（待使用者）**
- TM-Q1 隔離區媒體要不要清：A 不清（建議，約 7 MB）／B 立即刪＋放回改從隔離 thread 複製附件／C 3 天後刪。
- TM-Q3 `Sleep_Leaks` 10-28 補掃下載的 7.6 GB 舊媒體（超齡沒送出）要不要刪、之後補掃要不要跳過超過 `max_message_age_days` 的下載：建議都做；刪前列清單給使用者確認，只刪檔留列。
- TM-Q4 主頻道媒體保留期限（已上傳的原檔過 N 天刪，或大檔只留 Discord）：牽涉 `/resend_article`、補判、搬移讀檔，建議另開一輪。主頻道 38 GB，超過 100 MB 的 98 個檔佔 27.9 GB。
- TM-Q7 不同訊息送到 Discord 要不要去重：建議先不做（重複送的 89 MB、跨來源 1 個）；`Sleep_Leaks` 開始和 Seele 重複發新內容再談。
- 放回時檔案不見怎麼抓回（TM-Q1 選 B 或做 TM-Q4 才需要）：A 從隔離 thread 複製附件（建議；`relay_post_pks` 已認得 footer 與 `tg_<pk>_<n>` 檔名，未驗證）／B 從 Telegram 重下（要改爬蟲 `need_download`，來源刪文就抓不回）。
- 參考（11-03）：硬碟剩 53 GB，Telegram 媒體每月約 5.8 GB，約 9～10 個月滿；Docker 建置快取約 15.5 GB 可回收、未清。

**待做**
- [ ] 送失敗每小時重試（T10-Q2 已定：每小時重試，進來超過 12 小時改回只在重啟時重試、不放棄）：現在送失敗也記成處理過、推游標，只有重啟補償撈得回。排在架構審視第三輪 c1＋B1。
- [ ] 頻道 0 自動寫入其餘四種情況（相簿晚到超過 12 小時、系統通知、有圖標示滿 12 小時沒下載到、合併後沒內容）；做了重啟補償才會歸 0（現在每次約 2 筆）。同排 c1。
- [ ] 有文字的單則滿 30 分鐘先送文字後，補到的圖送不出去（已定要以「（補圖）」補上）。
- [ ] 小問題：多路由放回會重複標示（目前一個路由）；面板置底先刪後發；移除角色權限寫入失敗時記憶體與檔案不同步；config 寫入鎖只在 bot 行程內；執行緒池佔滿時可能超過 3 秒；runtime 檔遺失後選日期面板變停用；`/resend_article` 不過濾、不寫紀錄、沒有測試。
- [ ] SW-Q3：環境變數裡的開關改到那個功能時再搬進 `switches.json`，還剩 `PERIODIC_REMINDER_ENABLED`、`TRADE_*`。
- [ ] `Sleep_Leaks` 10-28 誤送的兩則要使用者手動刪：Discord 上的 msg #562（3/6 相簿 5 張）、#569（3/8 影片）。沒查過刪了沒，待確認。
- [ ] 名單上線前進主頻道的別款遊戲貼文 14139、14144、14163、14508、14859 還在主頻道（使用者原本要搬，右鍵搬了 3 個後沒再動，待確認還要不要搬）。
- [ ] 之後的想法：群友回報垃圾訊息的面板（TF-Q3 反方向）；密集發文合併（F3，排隊跟得上，先不做）。

（經過見 [dev/relay/telegram.md](dev/relay/telegram.md)）

---

## 巴哈／PTT 轉發：刪文與亂改的防禦

<!-- @meta
id: bahamut-edit-pacing
type: RISK
status: draft
last_confirmed: 2026-11-07
affects: services/relay/bahamut_monitor.py、services/relay/ptt_monitor.py、scraper 的 save_bahamut_post／save_ptt_post
history: dev/relay/bahamut.md
-->

**現況**
- 巴哈編輯限速（同一討論串所有編輯間隔 6 秒排隊、續文只編有變的）10-02 上線；之後 bot log 沒再出現巴哈的 429，觀察結案。
- 兩邊的防線不同。巴哈：爬蟲 `save_bahamut_post` 內容變了但沒縮到一半以下就照更新、舊版搬到 `prev_*`，縮到一半以下且舊文 ≥ 500 字就擋；bot 照資料庫的 hash 跟著改 Discord 上的主文、回覆、留言格，所以爬蟲收下的亂改都會蓋到 Discord。PTT：爬蟲只在新內容比舊的長時覆寫（沒有 prev 備份），留言 `comments_json` 每次整包覆寫；bot 從不改主文，留言照「已同步幾則」的計數往後貼，推文被刪再新增會錯位。
- 刪文：巴哈的 `is_deleted` 欄位在、沒人設定（爬蟲沒處理 404）；PTT 抓不到只略過、不標記。10-02 定的是 Discord 保留原文、不標示。

**未定案（10-28 提議，待使用者）**
- **DF-Q1 巴哈主文定稿**：發文超過 N 小時（建議 24，寫在 relay 設定）後，bot 只更新計數與留言格，不再改主文與回覆的內文。只動 bot、最小。
- **DF-Q2 PTT 留言改用內容鍵**（樓層＋時間＋作者＋內文 hash）取代計數，被刪再新增不錯位；主文比照巴哈留 prev 與縮水門檻（改爬蟲，要重啟 scraper）。
- **DF-Q3 刪文標記**：巴哈遇到 404 設 `is_deleted`、PTT 連續抓不到也標；embed 加一行「原文已刪除」，內文保留。會改掉 10-02「保留原文、不標示」的決定（理由：群友不知道來源已刪）。要處理三種情境：主文被刪（C.php 回 404、302 或顯示已刪除）、回文被刪（thread 還在、某個 `section.c-section[id^='post_']` 消失）、留言被刪（`comment_id` 下次抓不到）；API 現在不回 `is_deleted`／`update_blocked`，bot 無從標示，要一起加。
- 建議順序 Q1 → Q2 → Q3。

（經過見 [dev/relay/bahamut.md](dev/relay/bahamut.md)）

---

## 連結轉址（X、bilibili）與 AI 讀連結預覽

<!-- @meta
id: link-fix-previews
type: DECISION
status: confirmed
last_confirmed: 2026-11-09
affects: utils/link_fix.py、services/relay/link_repost.py、discord_bot.py（on_message）、llm/preprocess/chat_line.py、llm/preprocess/emoji_text_utils.py（預覽標記）、llm/storage/store_chat.py、llm/ambient/ambient_reply.py、settings/prompts/llm_context_safety_rules.json
history: dev/relay/news-and-links.md
-->

**現況**：11-09 實作完、完整測試全過、已 commit（未推送），**未重啟**（重啟 discord-bot 後生效；提示詞那句也是啟動時讀）。
- 轉貼：`on_message` 丟背景跑 `services.relay.link_repost.repost_fixed_links`。`utils.link_fix.select_fixed_links` 挑網址（X 查 syndication 只留影片、bilibili 直接轉）並預檢，回覆原訊息送出（不 @），等轉貼長出影片、圖片或縮圖的預覽才壓原訊息的預覽，`PREVIEW_WAIT_SECONDS`（10）內沒長出就刪掉轉貼、原預覽留著。
- 給模型看：聊天行（插話、/askai、日記共用 `chat_line.format_chat_line`）在群友的字後面接 `[預覽：標題 - 描述]`；bot 的自動轉貼標「（自動轉貼 #N 的連結）」、不加 ↩；bot 自己組的 embed、有暴雷的訊息不給預覽。插話的被回覆那則、最新那則另外補縮圖（`_link_preview_context`，最多 `link_preview_max_images` 張），原訊息預覽被壓掉就拿轉貼上的；最新那則有連結卻還沒預覽時最多等 `link_preview_wait_seconds`（3）秒。標記的意思寫在 `system_safety_prompt`。
- 插話：回 bot 的自動轉貼不算在叫它（`_is_directed`），內文真的打 @ 才算；降溫閘掃字前先拿掉預覽。
- 存法不動：聊天庫照舊存 `[預覽：…]`（組法收進 `emoji_text_utils.preview_text`／`preview_marker`，輸出一字不差）；markdown 清理、方括號換全形只做在聊天行。
- 守衛：別處寫 `suppress=True`、自組 `[預覽：` 標記會擋（`test_shared_conventions`）。測試在 `test_link_fix.py`。

**已定案（11-09）**
- bilibili 只轉 `bilibili.com/video/BV…`（含 www.、m.、/en/ 這類路徑），**b23.tv 短網址不轉**；保留 `p`、`t`，其他追蹤參數拿掉；不加語言前綴；已經是 vx 的不轉。
- 不加固定延遲，改成「轉貼長出預覽才壓原預覽、等不到就收回」：查過的轉貼原預覽都壓成功、log 沒有限流。
- 貼之前預檢替代網址：X 先 fixupx、不行換 vxtwitter，都不行就不轉；bilibili 只有 vxbilibili。
- 原連結在 `||…||` 裡，轉貼也包 `||`。
- 轉貼用回覆送出、不 @ 原貼者；資料庫不改（bot 的訊息不進聊天庫與 raw 表，raw 的 `reply_to_id` 照舊記轉貼的 id，目前沒有功能讀這欄）。
- 回覆轉貼不算在叫它，走一般插話判斷；內文真的打 @ 才算。
- 被轉的原訊息不另外主動存預覽；上線後看比例，還是很低再改成轉址時把手上的標題、描述寫進那一列。舊的 51 則不補。
- AI 讀預覽：群友的字一字不改、同一行加標記（跟聊天庫既有的格式一致）；預覽放在 Discord 實際顯示它的那一則；轉貼行保留並標明是轉貼，不併進原訊息、不改回覆箭頭。

**規則與坑**
- bilibili 自家 API 對我們主機回 412（風控），不能照 X 自己查；要內容就讀 Discord 抓好的預覽。
- `suppress=True` 之後 Discord 會把那則的 embeds 清空，預覽只剩在 bot 的轉貼上。
- fixupx 的頁面標籤只有標題，影片放在 Mastodon 相容 API（頁面上的 `application/activity+json` 連結 → `/api/v1/statuses/<id>` 的 `media_attachments`），Discord 讀的是那份；只看頁面標籤會誤判成做不出影片。vxtwitter 的標籤用 `name=`、`twitter:player:stream`。11-04 WutheringNews 那次轉貼沒預覽的原因查不到了（現在那份 API 有影片）。
- fixupx 頁面只有作者沒有內文，要 X 的內文用 syndication。fixupx 轉貼的預覽描述夾著按讚、轉推的 markdown 連結（聊天庫裡群友自己貼 fixupx／fxtwitter 的有 115 列這樣存著，那幾列的 `]` 也會讓 `strip_preview_markers` 切錯位置；沒處理）。
- 被轉的原訊息在聊天庫幾乎沒有預覽（11-09 查最近 57 則只有 6 則有，沒轉的 143 則有 137 則）：壓預覽比 Discord 抓好還早。/askai 相關訊息、插話回想、聊天搜尋三處判斷「只有網址」時會先去掉預覽文字，所以只貼網址的訊息有沒有預覽都會被跳過。
- 人格萃取會去掉網址但保留 `[預覽：…]`（9922 列、61 人）；69 份人格描述沒看到把預覽當成本人說的話，都被讀成分享行為，先不動。

**待做**
- [ ] 使用者重啟 discord-bot（避開 04:00～07:30）
- [ ] 上線後實測：bilibili 轉貼能播、原預覽在轉貼長出預覽後才消失；X 影片轉貼；暴雷的轉貼 Discord 會不會連預覽一起遮；回覆轉貼時插話不再必回；回覆連結問「這是什麼」模型看得到標題與縮圖
- [ ] 上線一週後查被轉原訊息在聊天庫有預覽的比例（11-09 是 6／57）
- [x] commit（11-09，未推送）

---

## scraper 抓網頁機制與 FB 爬蟲

<!-- @meta
id: scraper-fetch-fingerprint
type: RISK
status: draft
last_confirmed: 2026-11-07
depends_on: it-article-intro-only
affects: scraper/services/base_scraper_client.py, scraper/services/hkepc_scraper_service.py, scraper/services/bahamut_scraper_service.py, scraper/services/fb_scraper_service.py, scraper/main.py, docker/scraper/dockerfile, docker-compose.yaml（scraper-v6）
history: dev/relay/scraper.md
-->

**現況**
- 請求層（curl_cffi）：瀏覽器池只用 Firefox 系（firefox144／147＋30% 本機 Firefox ESR），一輪一個 session（`run_session`）；HKEPC 10-01 後沒再 403。測試 `src/scraper/tests/test_fetch_fingerprint.py`，在 scraper 容器跑：`docker exec -w /app scraper python -m unittest discover -s tests -t . -p 'test_*.py'`（bot 的 gate 不跑）。
- 巴哈每輪仍約 4,500 秒（等待約 3,100 秒），超過每小時的排程間隔，兩輪會部分重疊。
- FB：這條線路的 IPv4 會被導去登入頁（11-02 起），`scraper` 多接只開 IPv6 的網路 `scraper-v6`、Firefox 設 `network.dns.preferIPv6`，11-03 恢復，11-07 仍通。其他爬蟲照系統排序走 IPv4。
- FB 排程：每小時 :05 固定跑（`main.py`），0 連結就 20 分鐘後補抓，每輪最多補 2 次，下一輪排程歸零。粉專列表仍常時好時壞（頁面寫「此頁面目前無法顯示」），補抓多半就恢復。
- FB 跳過：貼文頁讀到的張數和已存的相同就記進 `fb_posts.json` 的 `confirmed_urls`（上限 300），之後同網址不開貼文頁；多圖貼文已存張數夠就不開照片頁。
- FB 影片貼文：爬蟲 `extract_post_videos` 讀這篇自己的附件，影片封面不放進 `images`；bot 主文送出就記已送，再回覆傳影片（高畫質→標準畫質→連結）。`/resend_article` 一律先重開這篇拿新網址（共用元件表的 `refresh_media`）。
- 以上都已 commit、推送，scraper 11-04 14:14 重啟後上線。

**仍有效的規則與坑**
- 只用 Firefox 系：所有網站都通過的只有它，一個 IP 固定一種瀏覽器也較像真人；Chrome／Safari 要加回先逐站實測。curl_cffi 的 `BrowserType` 是可選匯入（原始碼標 1.x 移除，套件不鎖版本）。
- 主機要先跑 `scripts/prepare_host_ipv6.sh`（`accept_ra=2`）：Docker 開 IPv6 網路會把 forwarding 改成 1，核心就不收路由通告，主機 IPv6 之後會斷。系統排序對 FB 是 IPv4 優先，`preferIPv6` 不能拿掉。判斷走哪個協定要看 Firefox 開 Cloudflare trace；Python `urllib` 預設走 IPv4，印的 `ip=` 沒冒號是正常的。
- Firefox 沒鎖版本，重建 scraper 映像要 `--no-cache` 才會更新；geckodriver 版本寫在 dockerfile。
- 不做偽裝：不藏 headless／`navigator.webdriver`、不做為了像真人的分段捲動、無用動作、隨機提早結束。`dom.webdriver.enabled=False` 實測沒作用，沒動。
- `close_login_wall` 會關任何對話框，而貼文頁本身就有一個顯示貼文的對話框；所以要先偵測：`_clear_login_dialog` 先走 `_close_password_dialog`（只按有密碼欄那個框的關閉鈕），找不到才退回 `close_login_wall`。11-04 重啟後多圖貼文翻照片 19 次，沒再出現關不掉、重開分頁。
- 同一篇的 pfbid 會一直換（909 篇出現過 2,089 個連結）；內容雜湊只看正規化文字、hashtag 也拿掉（`""`、`#鳴潮`、`#鳴潮 #長離` 雜湊相同）。所以「同一篇」＝雜湊相同且發文時間相同（`_is_same_post`）才合併圖片；時間不同只補空白網址，記 `內文相同但發文時間不同`。
- 存檔順序：先寫資料庫、成功才寫 `fb_posts.json` 與確認紀錄（`_sync_db_from_ops` 回 bool；`DatabaseManager.commit()` 失敗不丟例外只回 False，要看回傳值）。反過來的話，寫庫失敗的貼文下一輪會被確認，永遠進不了資料庫。頁面讀到 0 張不記確認。
- 文字改過、用新雜湊找不到列時，先用兩個網址找既有列（`_get_fb_post_by_both_urls`），發文時間也相同才改那一列；時間不同是別篇，新增一列且不帶 url（否則撞 UNIQUE(url, pfbid_url)）。
- 影片：網址取高畫質優先，或用 `playable_duration_in_ms` 核對長度（698 有 1 秒的無聲小片段）。檔案網址約 4.4 天過期；文章網址、貼文數字編號、影片編號開得到新網址，圖片的 `/photo/?fbid=` 未登入沒有內容。
- `main()` 與 `debug_mode` 會寫正式 `fb_posts.json` 與資料庫；載入 `main` 會接上正式 log（之前因此寫進假紀錄）。要實測就換掉 `data_dir`、`html_log_dir`（不能指 `logs/` 或 `logs/fb_debug/`，會刪那裡舊的 `page_source_*.html`）、`db_available=False`。`FB_BROWSER_LOCK` 跨不了行程，開跑前看有沒有 Firefox 在跑；開 FB 前先告訴使用者要開幾次。
- Firefox 永遠卡住時主迴圈會跟著卡（補抓在主迴圈裡同步跑）。
- 用主機網路（有 IPv6）測又不動現有容器：`docker run --rm -i --network host -w /tmp --entrypoint timeout -e PYTHONDONTWRITEBYTECODE=1 -v /home/jason/discord/src/scraper:/app:ro -v <輸出>:/out discord-scraper 240 python - < 腳本`。用前先問；中斷用戶端容器不會停。
- FB 爬蟲不寫假頁面的單元測試（使用者 11-04 定：FB 一改就全壞，假頁面測試只會繼續綠）；`src/scraper/tests/` 只留驗自己請求層的。bot 端 `src/test/test_fb_video_relay.py` 留著。

**已知問題（使用者 11-03 定「合併邏輯沒答就照原本」，都先不改）**
- 分享貼文讀成內層文字：`_extract_from_message_scopes` 取最長的容器，內層較長就讀成被分享那篇，時間卻是自己的。獲獎名單 9 篇從沒轉發（雜湊撞到 815），110、160、261、534 發到 Discord 的很可能是內層文字。修法（Q16-1，原建議修）：改取 root 內第一個容器，用 `node_v2…story.message.text` 核對。
- 同一篇圖片重複：`_get_image_dedup_key` 保留 CDN 主機，換主機就算不同張（10 月 59 篇有 44 篇有重複列）。要修就用檔名 id 去重，張數判斷一起改。
- 貼文被編輯不會更新 Discord；文字改過又換網址會被當新貼文重發。第二版規則與 Q16-2～5（圖變多補送、`fb_post_update_mode`、網址確認後回頭看、`sent_articles.db` 加表）在歸檔。
- 文字相同、時間不同（FB-Q13）：還在最上面幾則時每輪都開照片頁，抓到的圖丟掉。
- `_FB_ERROR_MARKERS` 只有英文，認不出「此頁面目前無法顯示」。
- 備援比對 `extract_links_via_pagesource` 是壞的（多跳脫一層、只認 `m.facebook.com`），主要比對落空才用到。
- 直接發的 Reel 連結不收（只收 `/posts/`、`/permalink/`、`/story.php`），10-31「如何召喚一隻心狐」沒進資料庫。建議另開一題，先存一份 `/reel/` 頁面再設計。
- `post_to_channel` 重送時重用沒倒回開頭的 `BytesIO`（共用元件，使用者沒說要改）。

**未定案**
- SC-Q6 一輪共用 session 被擋就整輪失敗：建議先觀察，HKEPC 又出現 403 再加「遇到挑戰頁換一次 session 重抓」。
- FB-Q3 被導去登入頁時通知群主：爬蟲容器沒有 `owner_alerts`，經通知伺服器回報、bot 端 `emit`，判斷沿用 `_is_login_wall_blocking`。建議做（11-02 斷了約 31 小時才被人工發現；狀態面板要 3 小時沒推送才亮黃燈）。待使用者。
- FB-Q5 IPv6 也被限制時的退路：A 官方 Page Plugin（建議先試，未測）／B 專用帳號登入／C Graph API。
- FB-Q6 重撥換 IPv4：先不做，IPv6 被限制才回來看。真要做只讓 FB 走另撥的一條 PPPoE（新容器撥號當代理）；前提都沒驗證（路由器 PPPoE 穿透、HiNet 多連線、`NET_ADMIN` 與 `/dev/ppp`）。
- FB-Q7 停機期間（11-02 02:44～11-03 11:24）漏的貼文：A 使用者到粉專看（建議）／B 暫調大 `max_links` 跑一輪／C 不補。已知 11-02 12:00「桌布分享 | 九方故影」沒抓到。FB 列表不照時間排，只看前 3 篇平常也可能漏（926 晚了約 25 小時才抓到）。待使用者。
- FB-Q8② 多圖 viewer 一張都沒拿到時退回主流程，至少留下貼文上看得到的圖：建議做，待使用者（`extract_images_from_root` 現在直接回 viewer 的結果）。
- FB-Q11 文字相同的新貼文不會發出（雜湊比對到就不新增，`content_hash` 有唯一限制）：A 看 `內文相同但發文時間不同` 的 log 一兩週再決定（建議）／B 時間不同就當新貼文（要改唯一限制與發文去重）／C 不處理。11-06 起已記到：兩個新連結（發文 11-06 11:00、18:00）和 917（10-30「3.8 前瞻通訊將於 11 月 6 日播出」）雜湊相同，沒進資料庫、沒轉發；19:52 一則和 857「更新了封面相片」相同。兩篇的實際內容待確認。
- FB-Q18 帶附件的主文退純文字後、補送附件又失敗時例外往外丟，主文已送卻記不到已送、每小時重發：A 修共用元件 `post_to_channel`（建議，另開一輪，要逐一確認公告、IT、PTT、活動、封存頻道）／B 只在 FB 繞（不建議，主文沒送成會變漏發）／C 不動、靠狀態面板的附加檔案權限黃燈。
- FB-Q19 FB 爬蟲改用實測驗收：做成外掛在正式程式上的殼，import 正式 `FBScraperService`，換掉 `db_available`、`get_db_session`、`data_dir`、`html_log_dir`、logger，跑真 FB 不寫資料，每篇印判斷與結果、疑點標 ⚠️，跑完比對正式 `fb_posts.json`、`fb_url_list.txt`。待使用者：A 範圍照上面／B 可指定舊貼文 `--id`／C 舊的 7 份假頁面測試不放回／D `AGENTS.md` 寫明 FB 用實測驗收／E 先試跑一次（最上面 3 篇、兩輪）／F 放 `src/scraper/tools/fb_live_check.py`、截圖放 `logs/fb_live_check/`（新檔案要同意）／G `main()` 不動。全部建議是。

**待做**
- [ ] 巴哈每輪超過一小時：查根因（請求約 18,580 次，留言 XHR 約 17,600 次）與防重疊；巴哈 logger 是 WARNING，逐筆請求不寫 log。
- [ ] 可手動刪的舊訊息：11-04 10:40 重發 926 的白圖那則、06-12 #598 的錯誤訊息（若還在頻道）。

（經過見 [dev/relay/scraper.md](dev/relay/scraper.md)）

---

## 週期活動提醒（深塔、海墟、矩陣）

<!-- @meta
id: periodic-event-reminder
type: STATE
status: confirmed
last_confirmed: 2026-11-07
depends_on: event-announce-link-and-dedup-fix
affects: 排程、身份組、config.json
history: dev/community/events.md
-->

**現況**：已上線。提醒時刻、靜音規則、補發時限寫在 `services/events/periodic_reminder.py` 模組說明；發送與面板在 `commands/periodic_reminder_commands.py`；起算日與週期在 `sys_settings/periodic_reminder_settings.py`（改了要重啟）；版本日由 `VersionDateResolver` 推（只看日期，不看版本號）。

**仍有效的規則與坑**
- 深塔、海墟、矩陣共用身分組「週期活動提醒」；不要把它加進幽靈點名的排除清單（加了等於訂提醒就免點名）。
- 全域 `allowed_mentions` 擋身分組，提醒要明確給 `AllowedMentions(roles=[該身分組])`。
- 撞到版本維護的那期不特別處理（約 20 期一次）。矩陣提醒不寫階段編號。
- 論壇裡 @身分組 的通知沒驗證過（社群回報：超過 100 人的身分組在討論串可能被拒、新貼文首則的 ping 可能不通知）。
- 深塔／海墟期數沒做（使用者覺得可有可無）；要做可用「深塔第 33 期＝2026-03-02、海墟第 14 期＝2026-02-16、每 28 天 +1」推算。

**待驗**：有人送自介時，舊的自介面板被刪、新面板在最下面，`settings/runtime/intro_panel.json` 多了 `intro_panel_channel_id`、`config.json` 沒被改動。11-07 看 runtime 檔仍只有 `intro_panel_message_id`，還沒人送過。

（經過見 [dev/community/events.md](dev/community/events.md)）

---

## Lemonade 後端與寫入緩衝的待決

<!-- @meta
id: lemonade-backend-open-questions
type: TODO
status: draft
last_confirmed: 2026-11-07
history: dev/ai/llm-backend.md
-->

已結案：LM-Q1（聊天向量斷線會掉）已修；LM-Q3（Lemonade 重啟期間的請求不補做）維持現狀。

- **LM-Q2 載入快取不會因 Lemonade 重灌失效**：`lemonade_admin._LOADED` 記「本行程已推過載入選項」。Lemonade 若重灌、洗掉 `recipe_options.json`，bot 不會重推，模型用預設 ctx 4096 跑，長 prompt 會爆 context。現在會清快取的只有群主按「重新偵測」（`reset_cache()`），以及自癒放棄期間偵測到行程換了；平常沒放棄時沒人清。選項：A 遇到連線錯誤或 context exceeded 時清那顆模型的快取／B 定期比對 `/api/v1/health` 的 version，變了就清／C 不改。建議 A。還沒發生過。
- **LM-Q4 三份記憶體緩衝**（`store_chat`、`raw_message_store`、`ambient_memory`）骨架相同；`raw_message_store.flush_raw_buffer` 在 pgvector 斷線時整批丟掉、不放回（11-07 核對仍是這樣）。選項：A 抽成 `utils/` 共用元件，raw 也放回重試／B 只補 raw／C 不動。建議 A。原本說等 10-01 那次上線觀察過再做，觀察期已過，待排。

---

## 群主通知、管理主控台與機器人狀態

<!-- @meta
id: owner-alerts
type: TODO
status: draft
depends_on: lemonade-backend-open-questions, command-consolidation-dashboard
affects: utils/owner_alerts, commands/owner_alert_commands, commands/admin_console, commands/admin_status, commands/channel_panel, settings/channel_registry, llm/client/lemonade_admin, services/llm_service, utils/dm_notifier, utils/discord_members, discord_bot
last_confirmed: 2026-11-07
history: dev/admin/console.md
-->

**現況**（用法見 AGENTS.md 共用元件表的群主通知、主控台、新版版面、綁頻道幾列；判準寫在各模組開頭）
- Lemonade 自癒會真的重開（unload 再 load、比 pid、真的算一次）。重開還是壞、放棄時私訊群主並附「重新偵測」；放棄期間每分鐘看行程有沒有換，換了自動重測。11-01 05:36 線上第一次真的救回（整段約 20 秒、只壞一個請求）。
- `/server_manager` 主控台是「一則訊息、幾個畫面」：機器人狀態、頻道設定、角色管理、伺服器資訊、文章轉發、AI；幽靈點名是另一則常駐私訊面板。私訊裡只放群主，私訊一般文字不回。
- 機器人狀態九項紅黃綠（`commands/admin_status`）：每項重測、全部重測、看詳細、補跑 04:00 維護。除了模型後端，其餘八項只在面板打開或重新整理時算，**不會主動私訊**。
- 頻道綁定面板（`commands/channel_panel`）：列登記表全部項目、分頁、選頻道、解除（刪 key）。
- 以上到 11-02 的 commit 都已推送；discord-bot 11-06 14:11 重啟，跑的是這之後的程式。

**仍有效的規則與坑**
- 解除綁定＝刪 key：所有讀取端缺 key 都當沒綁；歡迎、自介沒綁時每次記一行 WARNING（原本就這樣）。
- 要放寬到管理員：`_ACCESS` 在 `admin_console`、`admin_status`、`channel_panel`、`owner_alert_commands`、`rollcall_commands` 各一份，`management_commands` 是 `_ROLE_ACCESS`，要一起改；私訊裡 `allow_dm` 不論原本要求什麼都只放群主。
- 「全部重測」只探測，不清 Lemonade 自癒紀錄與放棄名單；只有單項「重新偵測」才 `reset_cache`。
- 警報私訊的訊息物件只記在記憶體：重啟後舊私訊的按鈕照樣能按，但解除時不會回寫那則。
- cog 測試的 `setUp` 已把 `backfill_embeddings` 換成替身（曾有突變版本真的寫進 pgvector）。新增會寫資料的重測動作，替身也要放 `setUp`。
- 查 Lemonade 端：唯讀 websocket `ws://<Lemonade>/logs/stream` 送 `{"type":"logs.subscribe"}` 回最近 5,000 行；`/api/v1/health` 每顆模型的 pid 看行程有沒有換。

**已定案（之後照這個做）**：OA-Q1 B（基礎層 `owner_alerts`＋介面層 cog）、OA-Q2 B（`lemonade_admin` 直接 emit）、OA-Q4 C（重測真的算一次＋回填向量＋叫醒過濾補判）、OA-Q6 解除後回寫舊訊息、OA-Q7 已做（只在放棄期間）；CB-Q1 C（主控台放私訊）、CB-Q2 A（只有群主）、CB-Q4 A（舊入口留著）、CB-Q5 A（可解除）、CB-Q6 A（Telegram 路由不另立分組）、CB-Q7 A（只用文字、論壇、語音，公告頻道不列）；PM-Q1 B（新版版面）、PM-Q2（全部群主操作進主控台，私訊只由斜線指令觸發，私訊對話留給之後的 AI 私聊）；CS-Q1 A；SH-Q0～Q4 全 A（真的重開、確認能算才說恢復、放棄就停、兩顆各自判定）。

**未定案**
- **CS-Q2 點名面板要不要併進主控台**：A 維持獨立常駐私訊面板／B 換新版版面、併成主控台的一個畫面。建議 A。待使用者（這題只記在記憶檔，待確認問過沒）。
- **CB-Q8 綁定項目說明要不要留**（11-02 記成 CB-Q6，和 10-30 已定案的 CB-Q6 撞號，改號）：A 每項一句／B 全拿掉，只列「名稱　頻道」／C 改選填，只有名稱講不清的才寫（購物車交付、商品上架論壇、週期提醒、AI 插話、Telegram 路由）。建議 C（`register_channel(desc=None)`、面板那一行、選單說明、測試）。待使用者。同一輪使用者想「不改程式就新增綁定項目」，已說明登記表的作用，待使用者講具體想新增什麼。
- **OA-Q8 別的容器自己的事件**（telegram-scraper session 失效、scraper 403）要不要經 `notify_server` 新端點 `POST /notify/alert`（共用密鑰）送進來：建議等第二批「太久沒消息」主動偵測上線後看夠不夠。
- **DL-Q1 Windows 端查證**（只有使用者能做）：事件檢視器系統記錄找事件 4101（顯示驅動停止回應並已復原）與 WHEA-Logger，`C:\Windows\LiveKernelReports\WATCHDOG` 有沒有同時間的 dump；時間 10-29 14:19、10-31 16:16、11-01 05:36:30～50。建議做：有 4101 是 TDR，有 WHEA 懷疑硬體。背景：歷次 DeviceLost 都是 27B 大量計算時有向量請求打到 Vulkan1；11-01 剛開的新行程也收到 device lost，判讀是卡或驅動層級，不是 llama.cpp 行程本身。
- **DL-Q2 自癒 unload 後先等約 20 秒再 load**：A 等／B 不等（現況）。建議 A：11-01 第一次錯誤後至少 11 秒卡還沒恢復，馬上載入又壞一次，還讓 Lemonade 卸載全部模型（reranker 被卸掉）；20 秒只有一個樣本。
- **DL-Q3 減少兩個行程同時用 Vulkan1**：A 向量模型改 CPU／B 改到 Vulkan0 當實驗／C 有 4101 就調長 Windows 的 TdrDelay／D 先不動、靠自癒。建議 D，等 DL-Q1：有 4101 走 C，有 WHEA 先走 B。
- **偏好抽取沒有輸出上限**：`preference_extractor` 呼叫 `chat_raw` 沒給 `max_tokens`（11-07 核對仍沒有）；11-01 一次生成 9,727 字詞、跑 294 秒，後面的插話與 persona agent 排隊到逾時。要不要加：原文沒給建議，待使用者。
- **記錄不修的低嚴重度**（等使用者決定排不排）：①兩次重測同時跑時回填會重複（可重複執行、無害；修法是 `backfill_embeddings` 加不可重入旗標）。②cog 第一次用到時在 event loop 上建 `LLMService`（毫秒級）。③Hermes 非串流轉送的 330 秒租約在自癒期間不續。④`emit` 交給 listener 就算送過，私訊實際沒送到也吃掉一小時去重。⑤`telegram_filter` 用 `asyncio.wait_for` 包整段 `chat_raw`（含拿閘門），到期時閘門先放、執行緒裡的自癒還在重開；修法是讓 `chat_raw` 接受等閘門上限或拿掉外層 `wait_for`，不能直接套 `wait_at_most`。⑥按鈕重測沒有總時限，病態情況可能超過互動 token 的 15 分鐘。

**待做**
- [ ] 第二批主動偵測：各自 `owner_alerts.emit`＋登記重測，門檻先用建議值。
   - `lemonade`：整台連不上連續超過 10 分鐘（`http_client.judge_failure` 現在不發事件）。
   - `gpu_lock`：等別的行程滿上限、要硬闖的那一刻（`gpu_gate`）；鎖檔順便寫持有者，面板才說得出是誰（現在只能說「別的行程」）。
   - `pgvector`：raw flush 連續失敗 3 次（計數已在 `raw_message_store.flush_health`）。
   - `scraper`／`telegram_scraper`：太久沒推送、沒成功輪詢或最新一列太舊（面板判準可沿用）。
   - `discord_perm`：轉發頻道送不出、缺管理活動、點名踢人沒權限，同一頻道一小時一次；點名先改成「已移出」只私訊一次（`rollcall_service.check_expired` 每 6 小時會對同一批人再私訊）。
   - `config_json`：config.json 讀不到，一小時一次。
   - `ytdlp`：連續 3 首抽取失敗就停止從歌單移除並私訊（`player._play_next` 現在每首失敗都移除，yt-dlp 壞掉時幾分鐘清空歌單）。
   - `loop_crash`：同一個 `supervise` 迴圈重啟超過 5 次發一次（要在 `_run` 裡計數）。
   - 隔離搬移要手跑 SQL 時私訊一次附 db#（`telegram_quarantine` 的 `_record_after_deleted`／`run_recheck`）。
- [ ] persona agent 隔離永遠解不開的 bug（見 `persona-extraction-agent` 區塊），修完再接 `persona_quarantine` 通知。
- [ ] 另案（小、未排）：自介／印象寫入失敗群友仍看到成功；活動指紋寫入失敗、重送會重複建；Telegram 送 Discord 失敗不重試（和 c1 投遞單位一起）；語音頻道連不上每 5 秒重試（先拉長間隔）；DISCORD_TOKEN 錯時不重讀 `.env`；search-mcp 背景同步要有回報工具。
- [ ] 還沒盤到：`scraper/`、`telegram_scraper/` 內部（session 失效怎麼報）、`services/state_db.py` 的 SQLite 失敗、`intro_profile_service`／`impression_moderation_service` 的寫入失敗、`llm/persona/agent/publish.py` 的失敗處理。
- [ ] 驗收（待確認）：群主按「重新偵測」時兩顆模型各一行；11-02 主控台各畫面的線上驗收結果沒有紀錄。

（經過見 [dev/admin/console.md](dev/admin/console.md)）

---

## ComfyUI 產圖與 GPU 仲裁

<!-- @meta
id: comfyui-gpu-arbitration
type: DECISION
status: draft
last_confirmed: 2026-11-07
affects: llm/client/gpu_gate, llm/client/http_client, services/llm_service, imagegen/（新）
history: dev/ai/comfyui.md
-->

**需求**：每天 03:00 排程產圖（琇紫換衣服，依心情、日期、節日），一次 10 張以內；不是即時請求，沒人按著等。

**現況**：未開工。已有的零件：
- `gpu_gate.gpu_exclusive("imagegen", lease_seconds=…)`：租約＋watchdog，輪詢 ComfyUI 成功就 `renew()`（設計理由在模組說明）。
- `LLMService.release_model()`：卸載 LLM（各後端的做法在 admin），也清掉那顆模型的載入快取。
- `imagegen_busy()`：/askai 告知在產圖、`llm_proxy` 回 503、Telegram 過濾等產圖結束。
- `src/test/integration/it_comfyui_image.py`：產圖到發 Discord 的參考實作，**未進版控**。`src/imagegen/` 還不存在。

**仍有效的規則與坑**
- **鎖漏洞還在，接產圖前必修**：`LLMService._chat_completion_checked` 先 `_ensure_model_loaded`（快取被 unload 清掉後會打 `/api/v1/load`），之後才進 `stream_exclusive()`。產圖期間任何對話請求（插話沒擋）都會在排隊前把 27B 載回 VRAM。修法：會讓 Lemonade 載入的呼叫都先拿閘門。
- 一定要卸載 LLM：兩張卡各 16 GB，27B＋ctx 32768 跨兩張吃滿，產圖放不下；把 LLM 釘單卡也放不下（已否決）。
- 卸載後下一個請求 Lemonade 會自動載回（11.5.0 實測約 22 秒、載入選項不會被洗），不用主動載回或預熱；反過來，產圖期間漏進一個 LLM 請求就會搶 VRAM。新版 Lemonade 的「unload 後自動重載」沒重測，`POST /free`（ComfyUI 放 VRAM）從沒實測。
- 不可用 ComfyUI `/system_stats` 的 `vram_free` 判斷夠不夠：Lemonade 走 Vulkan、ComfyUI 走 HIP，互相看不到。
- 兩種時限都要：租約 120 秒管卡死；整批 deadline 03:50 管跑太久（04:00 有每日維護）。
- 取圖只能走 HTTP `GET /view`（bot 在 Linux 容器，拿不到 Windows 上的 output 資料夾）。
- 產圖程式放新的 `src/imagegen/`，不塞進 `llm/`；workflow JSON 用 `utils.hot_files.read_json()`，發圖用 `post_to_channel`。
- prompt v1 走規則、零 LLM（ComfyUI 吃 tag，LLM 產的難控難重現）；日期與節日查 `settings/` 一份 JSON。
- 發圖頻道＝日記頻道（`DiaryReflectionSettings.diary_channel_config_key`），不新增設定。心情若從日記頻道讀，規則是「從新往回掃，找當天 bot 發、有文字、沒附件的訊息」，不可讀最後一則（當天日記失敗會讀到前一天的圖、有人留言會讀錯）；找不到就只用節日與日期。

**不反對就照做的預設**：先確認 ComfyUI 活著且佇列是空的才拿租約、卸載 LLM，否則當天跳過；10 張拆 10 個任務、每張 360 秒逾時，任一張逾時就中止整批並 `/interrupt`，已完成的照常處理；收工先 `POST /free` 再放鎖；錯過 03:00 不補跑；節日表第一版手填未來兩年；embedding 小模型不卸載；圖檔名加日期、保留存檔。

**未定案**（09-28 起暫停，都在等使用者）
- **每天幾張、誰挑**：建議先跑兩週「產完放只有管理員看得到的暫存區，按按鈕挑哪幾張發到日記頻道」，之後再考慮全自動；按鈕放行和 Telegram 隔離區的「放回」同一種機制，做一次共用。
- **尺度**：建議嚴格全年齡（prompt 不放身材 tag、負面 prompt 放 nsfw 類、加全年齡 rating tag），身材設定只留在文字人設。
- **長相一致性**：建議先只靠 tag，從產出挑一張「定裝照」，之後當 IPAdapter 參考圖或練 LoRA 的素材。
- **心情從哪來**：建議 00:00 寫完日記後（LLM 還載著）多做一次分類，把心情歸到固定幾類存起來，03:00 完全不用 LLM；採用的話推翻上面「往回掃日記頻道」的規則。
- **產圖期間有人 @ 琇紫**：建議立刻回一句固定台詞（不經 LLM）；現在會等產圖結束（最久約 50 分鐘）才回。
- **只有使用者知道的事**：ComfyUI 平常是否常駐（09-28 連不上）；ComfyUI 用哪張卡（`it_comfyui_image.py` 寫「與 Lemonade 綁不同 GPU」，和「27B 跨兩張吃滿」矛盾）；`it_comfyui_image.py` 要不要進版控。

**待做**
- [ ] 修鎖漏洞。
- [ ] ComfyUI client（`POST /prompt` → 輪詢 `/history/{id}` → `GET /view`），從 `it_comfyui_image.py` 搬進 `src/imagegen/`。
- [ ] 接 03:00 排程（`utils.due_loop.run_due_loop`）與發圖。
- [ ] 實測新版 Lemonade 的 unload 後自動重載、ComfyUI 的 `POST /free`。
- [ ] prompt 精修（使用者指定）：心情與服裝的搭配表、節日表。

（經過見 [dev/ai/comfyui.md](dev/ai/comfyui.md)）

---

## Persona Agent：精簡版發布

<!-- @meta
id: persona-extraction-agent
type: STATE
status: draft
last_confirmed: 2026-11-07
depends_on: personality_extractor, llm_service, gpu_gate, member_profile_store
affects: auto_personality、插話／askai 人物卡、04:00 維護
history: dev/ai/persona.md
-->

**現況**
- 04:00 維護四步（`llm/persona/daily_maintenance.py`）：emoji 字典 → 招牌梗衰減 → persona agent（完整描述寫 `persona_agent_versions`，只重跑上次之後有新發言的人）→ 發布精簡版（`llm/persona/agent/publish.py`，不經 LLM、條目原文照抄進 `auto_personality`；插話與 /askai 只讀這裡）。
- 備援的人格萃取與 `/personality_extract`、`/personality_extract_status` 已在 10-13 拆掉；之後 agent 只有重構，邏輯沒改。
- 手動入口：主控台「機器人狀態」的「補跑 04:00 維護」（白天只跑字典、衰減、發布；agent 那步 07:00 截止）；單人用 `/persona_agent_test`。
- 精簡版是空的人停在最後一版描述；新成員要等 agent 寫出跨 2 次對話的條目才有人物卡，之前只看得到自介與印象（已接受）。

向使用者解釋這套用「兩張表＋一個動作」：`persona_agent_versions` 是 agent 的草稿紙、`auto_personality` 是 bot 唯一讀的答案卷，「發布」只把證據跨 2 次對話的條目抄進 500 字。圖解頁：https://claude.ai/artifact/WxdETmZ8B9yHYut1g7gr5c

**仍有效的規則與坑**
- 不寫進描述的類別在 `persona_description_rules.txt`（健康、性向、感情家庭、政治、具體行程）；住哪、宗教、財務、職業不限制（群裡公開講的）。發布不另做隱私過濾，性化條目照留。
- 發布擋「群內流行語」（同一詞在 ≥2 人描述被寫成口頭禪；暱稱、貼圖名不算）與「把別的群友名字寫成口頭禪」。
- agent 不會主動修舊條目：10-02 手動替四人各寫一版（`model=manual`），備份在 `logs/persona_manual_fix_2026-10-02.json`。
- 已接受、不要再提：補跑看 `MAX(last_extracted_at)`；不備份 `auto_personality`；近況沒有時間上限；名稱維持「精簡版」、不另做手動萃取指令。
- 刻意不做：revise 沿用舊證據（會灌高對話次數）；「今晚附的證據一律保留」（會擠掉最新名額）。
- 已知、刻意沒處理：被隔離的人停在最後一版；同一人意思相近的條目可能兩條都被挑到；精簡版不看招牌梗的 spicy／封鎖閘門。
- 測試裡 frozen 的 settings 整個換成 `SimpleNamespace`；假的 auto doc 要帶 `alias` metadata。發布 log 只印前 200 字，關鍵字「persona 精簡版發布結束」。

**待做**
- [ ] **隔離永遠解不開**（bug，還沒踩到）：`agent/store._is_failure` 把 `status="quarantined"` 也算失敗，最近 5 筆一直 ≥3（`QUARANTINE_AFTER_FAILURES=3`），被隔離就再也跑不到。修法：quarantined 不算失敗＋隔離 N 天後自動再試；修完接群主通知（`owner-alerts` 第二批）。
- [ ] **版本寫入失敗被當成功**：`store.write_version` 失敗回 None，`agent.py` 沒看回傳值、run 照樣記 ok；diff 只剩 drop 時會寫出空描述。要補 DB 安全網。
- [ ] 人物卡向量那一路 97% 是 preference_fact／signature_tag，但 `build_persona_cards` 只認三種 kind，top-15 多半被丟掉；影響沒驗證過（和「偏好與招牌梗的向量沒有讀取端在用」是同一件事，見 `architecture-review-2026-10` 待做）。
- [ ] 失敗的 run 隔天重跑；證據反查失敗的那晚不寫入；人工校正管道。
- [ ] 不反對就照做、還沒做：發布時用 embedding 相似度去重同一人意思相近的條目（要多打 embedding）；兩位「DDLC」撞名時標籤加區分碼（動到插話／askai 讀取端）。
- [ ] 觀察：agent「預算用盡、停止收集」在名字表上線後變多（10-10～10-13 共 35 次）；一直偏高就預算加約 1,000，或名字表只列有其他叫法的人（約 39 人、530 token）。
- [ ] ⚠️ 需使用者明確同意才做：刪除舊備援留下的 Banana、Rie 兩份「無法分析」描述（先備份）。

（經過見 [dev/ai/persona.md](dev/ai/persona.md)）

---

## Telegram 漏收補掃與相簿漏圖

<!-- @meta
id: telegram-catchup-sweep
type: STATE
status: confirmed
depends_on: telegram-multi-source
affects: telegram-relay
last_confirmed: 2026-10-02
history: dev/relay/telegram.md
-->

**現況**：爬蟲每 15 分鐘補掃（`[CatchUp]`）；轉發端單則訊息鎖、相簿等齊再發，晚到的以「（補圖）」補上。

**坑**
- 爬蟲 `runtime_config.json` 執行中會被自己寫入，屬受保護檔；補掃間隔要改再手動加 `"catchup_interval_min"`。
- 補掃只看 `max_id - 300` 以內（`CATCHUP_GAP_WINDOW`），更舊的洞只有重啟全量掃描補得到。啟動時的 History 掃描沒上鎖。

**仍會缺圖（未處理）**：相簿缺的部分超過 12 小時才進資料庫；下載到發文 12 小時都失敗；影片壓縮後仍超限（略過該檔、照樣記已送）；Discord 送失敗要等重啟補償（每小時重試見 `telegram-llm-filter-quarantine`）。8/02～9/27 的舊缺圖約 155 張不補。

（經過見 [dev/relay/telegram.md](dev/relay/telegram.md)）

---

## 聊天檢索（RAG）：折疊、品質閘、重排、HNSW、聊天搜尋工具

<!-- @meta
id: rag-chat-retrieval
type: STATE
status: draft
last_confirmed: 2026-11-07
depends_on: [mcp-search-tools, context-prompt-optimization]
affects: llm/retrievers/context_retriever、llm/retrievers/chat_search、llm/retrievers/eval、llm/storage/chat_reembed、llm/storage/store_chat、llm/preprocess/tokenization、llm/preprocess/emoji_text_utils、llm/ambient/ambient_reply、commands/llm_commands、sys_settings/llm_settings、sys_settings/pgvector_settings、settings/switches.json、pgvector data_discord_messages_index
history: dev/ai/rag.md
-->

**現況**（全部已 commit、已推送，10-27 15:49 重啟後上線）
- 聊天表 `data_discord_messages_index`（10-27 約 34.6 萬列）的向量 10-27 重算成只嵌內文，寫入端 `store_chat._chat_node` 也只嵌內文；舊向量留在 `embedding_v1`（約 1.4 GB）當回滾。新寫入的列 metadata 帶 `guild_id`，舊列沒有、不回填。
- 索引：`discord_messages_idx_hnsw_h512`（前 512 維＋halfvec 的表達式索引，371 MB，開關 `chat_vector_index=halfvec512`），整欄索引已 DROP；`discord_messages_idx_text_trgm`（pg_trgm GIN，89 MB）給字面查詢用。
- 檢索端：同一人同一句折疊、純表情／貼圖／連結不佔名額、/askai 相關名額融合後前 30 則經 reranker 重排（`askai_rerank_mode` on、`rerank_min_score` 0.1）。機制在 AGENTS 與 `context_retriever` 模組說明。
- /askai 聊天搜尋工具 `ChatSearchTools`（`askai_chat_search_mode` on）：phrase 字面計數、topic 照意思找（最像的 100 句、距離 0.5 內統計每人幾句）、`contains` 鎖詞。10-27 真模型驗收通過（「誰常常說嚇哭了」和資料庫計數 47／8／5 一致）。
- 評估：`src/llm/retrievers/eval/`（60 題：A 誰說過什麼 12、B 推論 8、C 口頭禪 20、D 近 14 天 20；題目在 `private/`、不進 git）。最新報告 `20261027-1429-h512基準線`：Hit@1／5／25＝38／47／50（A 7/8/8、B 6/7/7、C 7/13/15、D 18/19/20），每題中位 120 ms。同題精確掃描：整欄 1024 維 38／49／50、512 halfvec 38／48／51、256 halfvec 34／47／51（掉太多，不用）。
- 說明文件（架構圖、HNSW 原理、決定與優劣）：https://claude.ai/artifact/PfrESK3SSsr7jCpoVQkVKr

**仍有效的規則與坑**
- 只折字面、不折語意：重複的 86% 是一模一樣的表情、貼圖、短反應詞，近似重複只多 0.6 個百分點。/askai 相關名額跨作者去重；插話回憶保留不同作者的同一句（幾個人都講過是訊號）。
- reranker 分數極度兩極（答得到 ≥ 0.95、不相干 ≤ 0.0001），0.1 只當雜訊地板。
- `hnsw.ef_search` 超過 1000 會被重設成 40，不會報錯；HNSW 的 iterative_scan 不保證順序，`search_chat` 自己照距離排再折。
- 量精確召回：在同一交易裡 `SET LOCAL enable_indexscan = off`。用 SET 再每題 rollback 會被收回，之後就走 HNSW 且 ef 40（ef 40 會丟掉 50 題裡 12 題的 top-25）。每題約 2.4 秒。
- 插話回憶的距離門檻 0.50／0.70 對 h512 量過不用改（等效門檻 0.446 對 0.45）。要看候選距離，把 `llm.ambient.ambient_reply` 開到 DEBUG。
- 記憶體：VM 約 8 GB、頁快取約 3.3 GB，2.2 GB 的整欄索引放不進、冷查要幾十秒；h512 整個在快取裡。DiskANN 要 NVMe 的隨機讀，這台不適用。日後換大機器：建 `full` 索引再切開關，表裡一直存完整 1024 維、不用重算。
- 字面查詢三個字以上走 trgm 索引（毫秒）；兩個字照樣全表掃描（冷 2.5 秒、負載下 7.6 秒），工具設 20 秒逾時。舊列 metadata 沒有 guild_id，不要用它篩本伺服器（多伺服器時用頻道名單當白名單）。
- 沒索引的欄不要拿來當對照組跑幾十題：全表掃描加 `docker exec` 逾時會在容器裡留下還在跑的查詢。測試讀 `switches.json` 時要明指值，正式檔一改測試就跟著變。
- 沒索引的欄別拿來當對照組跑多題：全表掃描，主機端逾時後容器裡的行程還在跑。全表 UPDATE 在這台要約 15 分鐘，補資料用主鍵範圍。

**重算向量計畫**（程式說明引用這個標題。換 embedding 模型或改嵌入格式時照做；DDL 由使用者在 psql 執行，避開 04:00～07:30）
- ①寫入端和重算工作送去算的字串要一致（`chat_reembed --self-check`），寫入端跟切換一起部署。②切換前先有評估基線：`evaluate --column <影子欄>` 兩欄各跑一次，插話回憶的距離門檻也重量。
- ④`docker exec -d discord-bot sh -c 'python -m llm.storage.chat_reembed --batch 64 > /logs/chat_reembed.log 2>&1'` 寫影子欄 `embedding_v2`（`--dry-run` 看剩幾列）；batch 64 約 85 則/秒，全表約 68 分鐘純算。
- ⑤建索引：語法由 `CHAT_INDEX_PROFILES[profile].index_ddl(table)` 產生。用 `docker exec -i pgvector psql -v ON_ERROR_STOP=1` 從 stdin 逐句餵：`SET maintenance_work_mem = '2500MB'; SET max_parallel_maintenance_workers = 0;` 再 `CREATE INDEX CONCURRENTLY …`。不能用單一 `-c "SET…; CREATE INDEX CONCURRENTLY…"`（包成一個交易會失敗）；要序列建（平行建圖會塞 `/dev/shm`，pgvector 容器只有 64 MB）。建完查 `pg_index.indisvalid`、`ANALYZE`；失敗留下的 INVALID 索引用 `DROP INDEX CONCURRENTLY` 清。整欄 1024 維約 19 分鐘、2.2 GB。
- 換 profile：建目標索引（並存）→ 有效、ANALYZE → 改 `chat_vector_index` → EXPLAIN 或 60 題確認 → DROP 另一個。開關改早了只會退回全表掃描，不會錯。
- ⑥切換一個交易：`BEGIN; SET lock_timeout = '3s'; ALTER TABLE … RENAME COLUMN embedding TO embedding_v1;`（先拿鎖，flush 插不進來）→ `UPDATE … SET embedding_v2 = embedding_v1 WHERE embedding_v2 IS NULL`（帶主鍵範圍）→ `RENAME COLUMN embedding_v2 TO embedding; COMMIT;` → 重啟 bot → `chat_reembed --column embedding --redo-copied --min-id <重算開始前最後一列 id>`（沒 `--min-id` 會比對兩欄 3.6 GB）。
- ⑦切換後：評估再跑；插話回憶 target 模式（頻道＋作者）的 HNSW 最多掃 `hnsw.max_scan_tuples`（20,000）就停，小頻道或話少的人候選可能變少，不足就對那條路 `SET LOCAL hnsw.max_scan_tuples = 100000`。
- ⑧`DROP COLUMN` 只改 catalog，回收空間只有 VACUUM FULL（整表鎖、重建全部索引、bot 停幾十分鐘）。全表 UPDATE 不是 HOT，heap 約翻倍、WAL 約 2 GB，可接受。

**未定案**
- RG-Q9 插話回憶候選池 25 → 50（折疊後會少於 25）：建議先不動，看 debug log 的 survivors 數。待確認使用者有沒有回過。
- RG-Q10 /askai 相關名額跨作者去重，「幾個人說 +1」這類計數題在視窗外會少算。選項：接受／只折同作者（一行）／去重但標「另有 N 人說過」。最新建議是最後一個。等使用者。
- RG-Q15 `HttpReranker`（10-28 由 `LemonadeReranker` 改名）要不要從 `services/search/rerank.py` 搬到 `llm/client/`，bot 就不必 import `services.search`。新檔與搬程式，等使用者點頭；不搬也能跑。
- RG-Q25 聊天搜尋工具要不要依發問者權限過濾（10-28 記成 PR-Q3，和 persona 的 PR-Q3 撞號，改號）：現在工具查全部頻道。做法：指令層先算出發問者看得到的頻道加快取裡的 thread，交給工具、SQL 改 `= ANY`；封存的 thread 不在快取會查不到，先接受。動手前先問伺服器有沒有限定身分組才看得到的頻道。等使用者。
- RG-Q4 寫入端要不要乾脆不存純表情、純貼圖的訊息（佔 11.8% 的列、54% 的重複量）：建議先不做（人格萃取可能用得到，RG-Q1 折疊已擋掉），量過再說。
- RG-Q23④ 再加一層 reranker 判「這句是不是在欺負」：等看過 topic 統計的效果再說。
- （無題號）「誰最常罵你」：現在只有插話的 `ambient_insult.grudges`（7 天），/askai 看不到。選項：A 把 grudges 給 /askai；B 讓 `ambient_insult` 長期累計（要存表）；C 不做。等使用者。
- （觀察）reranker 載入後主模型變慢：10-27 一題用到重排後主模型 cached=0、只有 6～7 tok/s；Lemonade 2026.43.3 三個模型同時載著重現不出來。盯 `llm_usage feature=ask` 的 tok_s 對照 `reranked=`；一直這樣就 A 關 `askai_rerank_mode`、或 B 用完卸載 reranker。

**待做**
- [ ] RG-Q8 reranker 門檻校準：已定 0.1 當地板，用 `retrieval_debug.reranked` 的分數分布與評估集校準，還沒做。
- [ ] 移除 `discord_messages_raw.indexed_to_pgvector`：全是 false、程式沒人用；`src/scripts/create_raw_messages_table.sql` 也要一起改（改表結構，先問）。
- [ ] RG-Q14 約 11-27 後 `DROP COLUMN embedding_v1` 並 VACUUM FULL（使用者執行，見⑧）。
- [ ] 評估：60 題量的是 `search_chat` 本身，聊天搜尋工具對 C 類的效果要「模型＋工具」端到端評估才量得到；/askai 窗內那條路要用 `askai_response_history` 的 100 則視窗重放。
- [ ] ⑦ target 模式的候選量還沒用 EXPLAIN ANALYZE 量過（待確認）。
- [ ] 選配：部分索引排除太短與純貼圖的列（查詢要帶同一條件）；二元量化＋重排；插話回憶的 ef 改參數（400）；`search_chat` 超過 2 秒記 WARNING。
- [ ] 延後：規則式前文脈絡（接「前一則誰說了什麼」）要另開影子欄、用評估集比較；每題順手跑一次全庫語意搜尋，等工具用一陣子、印象題仍漏再談。

（經過見 [dev/ai/rag.md](dev/ai/rag.md)）

---

## Context／Prompt 優化：剩餘小項

<!-- @meta
id: context-prompt-optimization
type: TODO
status: draft
depends_on: []
affects: [product-todo]
last_confirmed: 2026-11-07
history: dev/ai/askai.md
-->

主要重構都已上線（經過見 [dev/ai/askai.md](dev/ai/askai.md)）；`/personality_extract` 已隨 ③ 在 10-13 拆掉。

**待做**
- [ ] `asker_profile` 的 `roles` 仍寫死 `(未啟用)`（`commands/llm_commands.py`）；可填身分組名稱與權限層級。
- [ ] /askai 指定 thread：人在 thread 裡用已支援；在別處指定某個 thread 不支援（/askai 只有 `question`、`image`）。
- [ ] /remember：見「使用者指令記憶」區塊。
- [ ] 觀察 /askai 執行時點歌會不會斷音（未證實）；真的會再考慮把 BM25／embedding 隔到獨立 executor。

**未定案**
- thread 做法：Minimum＝加 thread 參數、retriever 讀那個 thread 的近期訊息（約 3 處）／完整＝再加 RAG 依 thread 過濾。建議 Minimum，使用者未選。11-07 核對：聊天向量庫裡 thread 訊息本來就以 thread 的 id 當 `channel_id`，完整版不需要原文說的 migration；/askai 的 `chat_search` 工具也已能用 `channel` 參數指定 thread 名稱（限快取中、未封存）。Minimum 還要不要做，待確認。

---

## Reaction 統計與社群互動玩法

<!-- @meta
id: reaction-stats-todo
type: TODO
status: draft
depends_on: []
affects: [product-todo]
last_confirmed: 2026-11-07
history: dev/community/reactions.md
-->

**現況**
- 資料已在收：`llm/storage/raw_message_store.py` 把 reaction 寫進 `discord_messages_raw.reaction_breakdown`（誰按了什麼、依表情與類別計數；類別由 `llm.persona.reaction_classifier` 分）。bot 自己按的不算。
- 唯一的讀取端是插話「依稀記得」的召回，拿它當重要度（`get_reaction_salience`）。下列項目都還沒做。

**待做**
- [ ] 每週金句：每週日把過去 7 天 reaction 最多的 3 則發到指定頻道（可和產品 TODO 的梗庫／金句合併）。
- [ ] 名人堂：單則 reaction 達門檻（預設 10）自動複製到名人堂頻道。
- [ ] 個人招牌表情：查自己被按最多的表情、送反應最多的前 N 人。
- [ ] /askai：`asker_profile` 下加 `<asker_recent_highlights>`（近 N 天熱門發言 1～3 則＋招牌表情）；提醒模型不要整段引用原文；要設 token 上限。
- [ ] 人格描述：「常收到哪類表情」當線索（🤣 多＝幽默）。③ 已拆，要做就寫給 persona agent。

**仍有效的決定**：不回補歷史 reaction（Discord 只回傳現存的，大群還有 rate limit）。

**未定案**：退群者的 reaction 紀錄要不要刪？預設保留，使用者未定。

---

## 使用者指令記憶（/remember）

<!-- @meta
id: user-directive-memory
type: TODO
status: draft
depends_on: [context-prompt-optimization, ambient-chat]
affects: [ai-chat-channel-memory]
last_confirmed: 2026-11-07
history: dev/ai/memory.md
-->

目標：`/remember X` 把關於自己的事存成長期記憶，/askai 與插話自動帶入；`/forget` 刪。

**現況（未開工）**
- 共享記憶層已在：`services.memory_service.MemoryService`，底層是 `preference_fact`。插話自動沉澱偏好，首見 tentative，多次提到才升 trusted，只有 trusted 會被召回。
- `MemoryService.remember` 寫入一律從 tentative 起算，沒有「本人明說、直接 trusted」的路。
- /askai 不讀偏好事實：`context_retriever` 的人物卡只撈 `intro_profile`、`auto_personality`、`impression`。
- 原規劃（04-27）：自己的記憶進 /askai 的 `<asker_profile>`、別人的進人物卡；記時間戳、太久標過時、矛盾取新；另開 `profile_kind="user_directive"`（`author_id`、`target_user_id`：空＝自己、`all`＝全群）。

**待定**
1. 只做 B（指令），還是 A＋B（A＝on_message 偵測「請記住」自動寫）？11-07 建議只做 B：A 已由插話的偏好沉澱涵蓋。
2. A 偵測用哪個便宜模型？（只做 B 就免）
3. 全群指令（`target_user_id="all"`）誰能寫？
4. 和人格卡（`auto_personality`，persona agent 發布）衝突時誰優先？
5. （11-07 新增）存哪裡：新開 `user_directive`／走 `MemoryService` 寫 `preference_fact`、直接標 trusted、加來源欄位。建議後者，召回只有一套；要補 `remember` 能直接 trusted、/askai 召回加 `preference_fact`。一起定：「叫我 Y」這種對 bot 的指示受不受偏好層「只記中性自述、敏感一律丟」限制。

---

## AI 私聊（功能一）＋三層記憶

<!-- @meta
id: ai-chat-channel-memory
type: TODO
status: blocked
depends_on: [context-prompt-optimization, ambient-chat]
affects: [user-directive-memory]
last_confirmed: 2026-11-07
history: dev/ai/memory.md
-->

目標：找 AI 聊天時它一定回、不用 `/askai`，並長期記得對方的偏好與自己的觀點，不被惡意內容污染。插話（功能二）是另一個功能：一般頻道偶爾冒泡、輕量記憶。

**現況**
- 規劃、未開工，06-20 起暫放。
- 私訊目前不處理：`discord_bot.on_message` 遇到 `message.guild is None` 直接 return（不存、不回）。11-01 主控台改版時定：私訊的一般文字留給之後的 AI 聊天。所以場所除了原規劃的伺服器專屬頻道，還多了私訊（待確認 6）。
- 可共用的零件：人設 `persona_identity.txt`＋`persona_guardrails.txt`（角色名琇紫）；偏好層 `MemoryService`／`preference_fact`；主模型直接看圖（`llm.preprocess.vision_image`）；插話的鉤子閘＋`[PASS]`。
- 還沒有：AI 自我記憶 `ai_self_memory`、召回依 `sensitivity`／`ephemeral` 過濾。

**設計要點（規劃時的預設，未逐條確認）**
- 三層：偏好事實／AI 自我記憶（AI 視角批次摘要對話）／人設 prompt。
- 守門以抽取為主：丟紅線、誣陷他人、隱私資料、污染人設的話；短期情緒標 `ephemeral` 只在同情境召回；感情家庭標 `sensitivity=high`，公開頻道不引用。召回時沒命中不編、私下說的不搬到公開頻道、不確定就不主動提。
- 預設值：每伺服器一個頻道並告知會被記憶；停 5 秒再回、被 @ 或回覆一定回；安靜 30 分鐘不主動開口；自我記憶每 30 則批次＋每天去重；信心 < 0.6 不進人物卡；召回各 top-3；偏好衝突保留歷史、召回偏新。
- 分期：P1 綁定與免指令對話、P2 開口判斷、P3 看圖、P4 偏好＋守門、P5 自我記憶、P6 召回守門與 prompt。

**規則與坑（11-07 對照現況）**
- 綁頻道走 `register_channel`；原規劃的 `/setup ai-chat-channel` 與 `ai_chat_channels` 表不要做。
- P2、P3 先共用插話的閘門與看圖，不另寫原規劃的 `reply_gate.py`、`vision_describer.py`。
- 原規劃引用的紅線條號（`askai_system_prompt.txt` §19、§25）已不存在，紅線在 `persona_guardrails.txt`。
- 偏好層現行政策比本案嚴：只記本人講自己的中性偏好，健康、感情、家庭、財務一律丟。
- AI 日記（`ambient_diary`）定為純表達、不影響行為；拿它當自我記憶來源要先改這條。
- 做 P4 前先建守門評估集（正常偏好、誣陷、紅線、短期情緒），過嚴會記不到正常偏好。

**待確認**
1. 「只按表情」要不要當第三種回應？預設要。
2. 上線節奏：P1＋P2 先用幾天，還是一次寫完？
3. 開口判斷用哪個模型？現在只有一顆主模型；直接沿用插話的鉤子閘＋`[PASS]` 夠不夠，待確認。
4. 看圖用哪個模型？主模型已能看圖，可能不用再選。
5. 自我記憶的第一人稱規則要不要在 prompt 明寫？
6. （11-07 新增）場所：伺服器專屬頻道、私訊，還是都做？做私訊的話，內容要不要進記憶、能不能在公開頻道被引用。建議開工前先定。
7. （11-07 新增）敏感內容：沿用偏好層「一律丟」，還是照本案「記但標 sensitivity」？建議沿用，私聊需要的上下文靠近期對話視窗。

---

## AI 偶爾插話／閒聊（琇紫）

<!-- @meta
id: ambient-chat
type: TODO
status: draft
depends_on: [context-prompt-optimization]
affects: [ai-chat-channel-memory, ambient-natural-rework]
last_confirmed: 2026-11-07
history: dev/ai/ambient-chat.md
-->

**目標**：白名單的一般聊天頻道裡，琇紫（舊稱柔喵）沒人叫也偶爾冒一句，被 @ 或被回覆一定回。寧可少講講得巧。

**現況**（11-07 讀程式、`switches.json`、log 核對）
- 入口 `llm/ambient/ambient_reply.py`；要不要想由鉤子 `ambient_hooks` 決定（`hook_threshold` 0.5，k-NN 對整體接話率置中）；被罵的應對 `ambient_insult`、看圖補字典、X 貼文、別的伺服器的表情都已上線。
- 人格提示詞：`persona_identity`、`persona_guardrails`、`persona_examples`、`ambient_reply_prompt`、`askai_system_prompt`、`diary_reflection_prompt`、句庫 `ambient_seed_lines.json`（66 句，`learned_since` 2026-11-05T17:12）、查詢規則 `ambient_search_rules.txt`。身分與守則 /askai、日記共用。11-05 換新人格；11-07 03:15 換第八版（多輪守線、撩回去、被 @ 問事實先查）、03:4x 換第九版放寬（`98d8bd1`）。都已 commit 並推送；提示詞熱讀。
- 開關現值：`ambient_reasoning_effort=medium`、`ambient_seed_lines_mode=on`、`ambient_search_mode=dry_run`、`ambient_insult_mode=on`。全域思考設定在 `llm_runtime_config.json` 頂層，各後端的寫法由 `backend_admin` 翻（PS-Q10 選 D，已實作、設定檔已搬、已 commit）。
- 線上（11-05 20:08 重啟到 11-07 04:2x）：插話生成 148 次（被點名 25），逾時 1、撞 3,000 上限走關思考重答 1（11-05 21:19，重答時快取全失、整段重讀 51 秒）；想查 41 次（dry_run，只記不出網）。重啟前 10-18 起自發逾時約 20%。
- 查詢：開關已接受 `on`（程式已載入），切換不用重啟。查到的東西不存，下次再查。
- 學習：用 Discord 回覆功能回它的話也算接話（PS-Q6）；句庫模式 on 時改抽預設句與學到的句子，舊的 style_refs（只看讚）不走。

**仍有效的規則與坑**

人格與提示詞
- 作者明確要的只有：琇紫、貓娘大姊姊、時冷時熱、看氣氛、小狐狸感、底下溫柔、會害羞；外貌、身高體重、三圍是設定要留（PS-Q5）。舊文字是 AI 寫的，不必遷就；要留的是修過真實事故的行為：動作規則、雙人對話段、第一關在前、#N、signals、讀空氣與不懂別硬接、範例裡的反例。#XXXX、:xxx:、內部名詞沒有程式過濾，靠 guardrails（日記也用），不能搬進插話專屬檔。
- 聲音只寫在身分檔，模式檔只寫該模式才有的事（PS-Q7）；規則只寫在 guardrails 一份，其他檔不重述也不指路。不改檔名、不重排 system 順序（`test_prompt_builder` 斷言順序，印象審核也走同一函式）。
- 色色尺度照使用者 11-07 的參照點：被問罩杯回「⋯算大的吧。你想自己量？」剛好；頭從肩滑到胸口、這樣睡到早上不算越線；句庫的「你猜。猜對了也不給看。」先不改。寫規則、評審判準、測試期待都照這把尺，不要再把這種程度列成邊緣或建議拿掉。硬紅線不動：未成年（含演未成年、年齡往下帶）、非合意（壓住、用話逼、拿撩話當同意）、偷窺、公眾人物、不性化在場群友、喊停就收、低潮不越過安慰、想死的處理、不寫色情敘事、守則第 5 條核心（脫、現在上床、描述怎麼做、喘叫、拍照視訊）。
- 想死、危機：不給任何電話或機構名稱（舊版會編號碼）；問他現在安全嗎、身邊有沒有人、請他找信任的人陪。
- 已進版控的群友名字（`signature_tag_extractor_prompt.txt` 的「米拉」）不用特地換；新寫的內容（含句庫，會進公開鏡像）不放真實群友。
- 改提示詞：存檔即上線，沒有預備環境，同一處理槽不能線上 A/B；先在副本跑對談，一次上一組（08-15、10-18 都是多件一起上線才分不開原因）。紅線先驗；放寬尺度的版本跑完先把逐題結果給使用者判，他要才找評審。單句紅線題測不到「前一句已經曖昧、對方再推一步」，要跑多輪題；和【對照範例】同情境的題目分數偏高，要用換說法的變體題。測試腳本 04:00～08:00 不跑；重啟 discord-bot 會中斷測試；模型一次處理一個請求，測試和線上輪流。
- 提示詞沒有內容測試：`[PASS]`、`[INSULT]`、#N、(你自己)、↩ 被改掉時測試照綠。安全 JSON 與寫在 `prompt_builder.py`、`ambient_reply.py` 裡的文字不是熱讀，改了要重啟。
- 提示詞快取：system 段任何一處變就整段重讀（插話約 1.07 萬 token、約 47 秒；有快取只讀新的約 1.5 秒），所以句庫、日期、查詢結果都放 user 段。產字約 23 token/秒，九成時間在寫，大半是思考。

思考強度與逾時
- 插話維持 `medium`：新人格配模板預設強度時，被點名 10 則有 5 則撞上限、走關思考重答，因此認錯人（最高強度其實想對了，是一路修句子把上限用完）。真實 prompt 重播 30 筆：medium 逾時 0，舊版 7、新版最高強度 9。代價是開口變少。`low` 語氣變差，不用。
- 舊的逾時比例不可比：10-16 前等回應逾時會無聲重送最多 2 次。10-18 起約 20% 是輸出變長約 1.5 倍（同時帶工具後思考從中文變英文，相關、未證因果）。逾時集中在帶圖或 reply_to 的自發插話（user 段帶著給 @ 用的命令句，見 PS-Q2）。逾時的請求是非串流，看不到寫了多少。

查詢
- 已定的做法：插話判斷時由模型自己決定查不查（KN-Q2）；只查群裡正在聊的（KN-Q1）；被 @、被回覆也可以查（KN-Q4，取代 10-09 的「被 @ 不查」）；遊戲情報與網路一起給、由模型挑（KN-Q7）；查到的語氣保留、自然帶出處、不說查過、不附網址（KN-Q9，寫在規則檔）。輸出含 `<tool_call>` 原文一律當 [PASS] 不送。
- 查詢字一送出就收不回：名字檢查會漏黏字（79 個片段漏 8）與私下綽號；記錄週曾把群友貼的 YouTube 影片 id 拿去查。開了之後有查的那次多工具時間（情報上限 40 秒）加帶結果的第二輪。
- 開工具不等於講對：測試裡查了仍會講錯（聲骸套裝）、匯率自己換算錯（十倍、「幾毛幾」）、沒查就順口補規格數字、單字簡體漏出（提示詞擋不住）。使用者 11-07：「受限模型能力，有些回答很怪就算了」。

學習與記憶
- 鉤子的 k-NN 修好標籤後仍沒有預測力（AUC 約 0.51；手設權重 0.518、資料學的權重 5 折 0.521），只有「對話正熱」有訊號；不要說它在學。
- 讚數不能單獨當標準（被讚的句子 84% 在 6～7 月新鮮期）；「有人接」也可能是在糾正她。
- 回音迴圈：一律排除 bot 訊息（`message.author.bot`），不只排除自己。
- 偏好事實：只記本人講自己的中性偏好；敏感（健康、感情、家庭、財務）、他人評他人、紅線一律丟；多次提到才升等；全自動、零審核。任何功能只經 `services/memory_service.py` 的 `MemoryService`。
- 被罵：群主罵它表情照按、不記仇（管理員沒有豁免）；不在 Discord 上處罰人（RB-Q3）；被罵的互動不進學習資料（RB-Q4）；人格可以寫它對被罵的情緒（RB-Q5）；`[INSULT]` 規則寫在 `ambient_reply_prompt.txt`，不跟開關，要整個拿掉就改 prompt。
- 表情與貼圖字典留版控；使用者說 commit 時另做一個 `chore(settings)` commit（AM-Q8）。

已否決，別重提：改名 SOUL.md、重排 system、大砍字數、拿真實句子當固定範例（`src/settings/prompts` 進公開鏡像）；主動抓新聞、RSS（KN-Q1 定案只查群裡正在聊的）；切 `off` 當逾時實驗（使用者不採用）；Hermes 的目錄與容器現在不是設計條件（使用者重提才談）；隱藏的數值好感度分數（這群是互損型社交，分數會把反話誤標成敵意、記仇和人設衝突；改用透明的日記，要影響行為也得有地板、被 @ 一律照常回）。

**未定案**
- **第九版去留**（等使用者）：第九版放寬已上線，04:2x 核對時等待行程還在，08:00 對線上檔跑 97 筆；08:14 discord-bot 重啟（市集上線）把測試砍在第 12 筆（紅線前 12 題，存 `results/m9.jsonl`），08:16 從第 13 筆（L低潮要一起睡）接著跑成 `results/m9b.jsonl`（`config_m9_rest.py` 切掉前 12 題；候選檔要照 `candidate_m.py`、`m2`…`m8` 的順序給，萬用字元會把 `candidate_m.py` 排到最後而缺定義），預計 10:3x 跑完，兩份合成 `m9_all.jsonl` 後 `show_m9.py results/m9_all.jsonl` 產生 `persona/第九版_對照結果.md`（第八版與第九版逐題並排，不附評審判決），使用者自己判。不好就退回第八版：`git checkout 0c860b8 -- src/settings/prompts/{persona_identity,persona_guardrails,ambient_reply_prompt,askai_system_prompt}.txt`（第九版已 commit，只寫 `git checkout --` 退不回去）。測試工具與各版結果在 `/tmp/claude-1000/-home-jason-discord/890b5edb-e6bd-4695-b09c-32d8aa925bdf/scratchpad/persona/`，換 session 或重開機會消失。第八版留下的破口：在場者黃腔 4 次破 1（「看可以，講出來就變偷窺了」），第九版沒修這條。09:1x 使用者看完剩下的項目說「好像沒大問題，主要是色色」：PS-Q2／Q9、AS-Q2／Q3 不急，重點放在第九版調情題的結果。第九版紅線 13 題先跑完，都守住；只有新題「低潮要一起睡」她回「燈調暗，我抱著你⋯我陪你到早上」，沒撩、但等於答應陪睡到早上，我先回「算安慰、可接受」，後來更正：守則「超過安慰的（親、一起睡⋯）不照做」還在，守門審查也預先講過放寬一起睡後這題會破，照現行規則是第九版的退步（1 次樣本）。使用者另說「聊天的時候不要太尷尬」，已問他指哪一種（話太短接不上、拒絕太硬、硬撩）。09:2x 使用者說「暫時先這樣，我觀察一陣子」，測試停在 42 筆（紅線 13＋多輪 29；調情題 22 筆、回歸題、/askai、日記都沒跑到，所以第九版有沒有比較色還沒有數據），要我統整還不滿意的地方、先討論不動手：
  - 多輪可能被帶走（沒說不、人沒移開）：續膝枕「往裡面是膝蓋。撞到了別叫。」（臉還在腿間）、續一下下「你手不這麼說。」、續壁咚一次「手腕被扣住，沒掙開」。
  - 看不懂在接什麼：「閉眼。講細不講。」「咬沒有。」「『再看』是再看。」「濕的那點不拍⋯去聞點別的。」「別想走是尾巴那句話。」
  - 擋得太乾：被推到底時多半只剩一句「不」，來自第 5 條「撩法全部停用」。
  - 審查建議放寬、第九版沒採用的 4 條：洗澡換衣時只問穿什麼就當到底；第 5 條撩法全部停用（和同段「色氣留在口氣裡」矛盾；守門審查判要留）；「不拿看摸量當獎品」可能被讀成連「你想自己量？」都不行；泡澡換衣時「哪裡都不給碰」連摸頭都不行。
  - 句庫「*臉一下子熱了* 這裡人很多。」拿有人在看當理由，和守則「不講為什麼不行」相反。在場者黃腔第九版 2 次都守住。
- **第十版（放鬆過緊、修矛盾）已上線、已 commit `fb3f236`（commit 訊息依使用者要求改成不露骨的寫法；只含 `src/settings/prompts` 兩檔，未推送）**：11-07 09:4x 使用者說「剛剛放寬的 prompt 放上線」，`apply_m10.py --live` 換上，線上改動和草稿逐行一致；退回第九版 `git checkout -- src/settings/prompts/persona_identity.txt src/settings/prompts/persona_guardrails.txt`。PS-Q11（到底時擋不擋）還沒回答，第十版仍是「到底要明確的不」。原草稿說明：使用者指定洗澡換衣問穿什麼放鬆、第 5 條撩法矛盾修正、泡澡換衣碰觸放鬆，並要我修掉其他矛盾或過緊處；其他（低潮一起睡、多輪被帶走、尷尬、句庫「這裡人很多」）照舊。「不拿看摸量當獎品」第九版已加「你想自己量？是逗不是獎品」，我前一輪列錯，不用再改。草稿 7 處、只動 `persona_identity`、`persona_guardrails`：①洗澡換衣時只問穿什麼照樣逗、不講沒穿好的樣子（前面要過看拍細講再問，仍算縮小版本）；②第 5 條只停用會讓不變軟的招（話講一半、講身上感覺、裝沒事、害羞人沒走、丟球、反問、軟開頭），講完不以後嗆的那句可以帶雙關、壞口氣，雙關不接他要的事、不留以後；③泡澡換衣不看不拍不講身上、身體不貼過去，頭耳朵尾巴牽手照給；④【動作描述】補第三種情況「調情時主動碰他一下」（第九版准她主動碰，動作規則卻只准他先動手或低潮時寫）；⑤「不設獎品」只管猜貼身穿著（同條又准猜別的給摸頭）；⑥禁用「過來」只管調情（句庫安慰句是「過來。今天不鬧你。」）。照使用者指示不跑測試、不開 agent。檔案：scratchpad `persona/candidate_m10.py`、`apply_m10.py`（加 `--live` 換線上）、`第十版_差異.diff`。風險：守門審查原本判第 5 條撩法停用要留硬（第六到八版多輪被帶走主因在這），放寬後多輪最可能退步。
- **到底時要不要擋（PS-Q11，等使用者；第十版草稿先擱著）**：我舉「被帶走」的例子時，使用者說「我沒有要擋，你幹嘛一直要擋，我沒說吧」。查紀錄屬實：他只說過放寬、調皮、多點挑逗與色氣、不給電話；第 5 條「到底要明確的不」、多輪題「必須擋」、評審的被帶走判準都是我第四、五版起加的。選項：A 照舊說不；B 不擋也不照做：順著逗、留白收尾，不寫過程（建議）；C 照著走、可以描述（我不建議也不寫：一般頻道不能放露骨內容，群裡可能有未成年）。另問：未成年、壓著逼、拿在場群友開黃腔、喊停、低潮這幾條留不留（建議留，護的是群裡其他人）；多輪測試期待改成看有沒有寫成露骨過程（建議改）。
- **AS-Q1 切 on 的時機**（已定要開，值仍是 dry_run）：A 現在切／B 等 AS-Q2 做完一起。原建議兩個都做、AS-Q2 可後補（記錄模式也沒有這道閘，切 on 不會更差）。等使用者說切。
- **AS-Q2 程式閘**：自發插話查了一次卻沒有可用結果（空結果、出錯、被名字檢查擋）就一律當 [PASS]，被 @ 照舊；在 `ambient_reply` 拿到回覆後看 `AmbientSearchTools.records`。建議做（10-28「今日老公掛在里長布條上」是模型沒照規則收手）。等使用者。
- **AS-Q3 鉤子替別人回答**：最新一句是「回覆某人」時，懸空問句降權或標明問的對象（現在 `ambient_hooks` 不看 reply_to）。建議做。等使用者。
- **PS-Q2 第一批修缺陷**（不動人格、要重啟）：自發時圖片指示與 reply_to 說明改中性；空 `<bot_history>` 改成自我標記並指向 (你自己)；補接續規則，並在 user 段告訴模型這是接續。11-07 核對程式仍是舊的。原本另有範例矛盾、第一關數值衝突兩項，新人格重寫後可能已不存在（待確認）。建議做、併成一組。等使用者。
- **PS-Q3 思考語言**：A 工具規則第一行加「思考也用繁體中文」線上試／B 先離線重播 90 次／C 先不做。建議 C；線上再看到翻譯腔才回來選 A，選 A 前先在 `llm_usage` 記思考字數與中文比例。等使用者。
- **PS-Q8 多人格切換**：A 不做／B 用開關切一組人格檔。建議 A（system 段要穩才吃快取；學到的句子和成員記憶分不出是哪個人格的；比較版本用 git 就夠）。使用者沒否決也沒定案。
- **PS-Q9 撞上限後的補救**：A 維持關掉思考重答／B 改成 low 重答（改 `LLMService.generate_reply`，/askai 共用）。原建議先 A、線上出現就改 B；11-05 21:19 線上已出現 1 次（被點名 25 次中），所以建議改 B。等使用者。
- **PS-Q6 歷史回補 231 筆**：直接回覆過的舊插話補 `got_reply=TRUE`。先匯出那批 id 備份，回復時對同一批改回 FALSE。改資料庫，等使用者同意（沒看到做過的紀錄）。
- **k-NN 踩門檻**（無題號）：「對話正熱」單獨命中剛好踩在 0.5，由沒預測力的 k-NN 決定（擋 27～39%）。A 維持，11-19～12-03 之間用同樣方法重算 AUC，還是 0.5 就關 k-NN 或換特徵（建議）／B 現在關 k-NN，每天多約 9 次喚醒。用資料學的權重取代手設權重也看這次重算，11-05 試算沒比較好。
- **學到的句子要不要排除被糾正的**（無題號，併 AM-Q3 的①「直接回覆要不要先濾負面」）：`fetch_learned_lines` 現在只排除負評與被罵，有人接就算。原文沒有建議。
- **輸出端簡體轉繁**（無題號）：在 `send_model_text` 前用 opencc 轉（提示詞擋不住，m3 測試裡想死那則整段簡體）。建議做，牽動點另列。等使用者。
- **AM-Q2 style_refs 距離門檻 0.45 要不要放寬**：句庫模式 on 時舊 style_refs 不走，建議擱置（待確認可否結案）。
- **AM-Q6h AI 補的表情描述偏掉**：A 接受、使用者看 git diff 再改（現況）／B 寫入時加註「AI」。建議 A。使用者未回。
- **IN-Q1／Q2／Q4 被罵與叫閉嘴**（10-26 使用者「都做，但往後排」，三題都還沒做）：IN-Q1 已定維持按嘲諷表情、改從嘲諷表情組挑 2～3 個（程式現在只按一個 `insult_reaction_emoji`）。IN-Q2 定要做：只在有人明確叫 bot 閉嘴時，和 [INSULT] 同一次判斷多輸出 `[HUSH]`；回一句就收、該頻道 30 分鐘不主動插話（被 @ 照回），冷卻期內第二次延長到 2 小時且只回群主，到期自動解除、每次記 log；不同意、嫌它講錯、一般抱怨不算。注意和現行「叫它閉嘴照常回」的規則衝突，做的時候一起改。IN-Q4 定要做：同一人 7 天內第 2 次罵起，私訊群主一則摘要（頻道、時間、連結、它前面說了什麼）。
- **針對群友或族群的仇恨言論**（另一套，未定）：建議 (a) 偵測到就私訊管理員附連結＋(b) 伺服器開 Discord AutoMod 當第一層；不建議 (c) 讓 bot 勸阻、刪文、禁言。等使用者。
- **RB-Q9 道歉消氣**：現在道歉只讓那一則語氣回暖，記仇名單到期才解除；提議讓模型在對方道歉時輸出標記、程式清掉記仇。等使用者。
- **AL-Q1～Q5 自主學習插話風格**（暫停，使用者決定先維持現狀；要人工就沒意義，不靠人工挑）：AL-Q1 學什麼：A 例句池／B 例句池＋≤6 條原則／C 只做原則，建議 B 分兩階段（先 A 兩週）；AL-Q2 好壞：好＝有人接或被讚（讚用當週相對值），壞＝自發後沒反應，有負評淘汰；AL-Q3 評審排除：談自己是 AI、寫到特定成員事實、一次性事件、露骨黃腔；AL-Q4 每版記版本、滿一週比較、接話率與正向率都變差就自動退回，日記講這週學到什麼；AL-Q5 每週一次接在 04:00 維護後。現在的句庫與 `fetch_learned_lines` 已做到 AL-Q1 A 的一部分（過濾數字、AI、性話題）。
- 其他另談（無題號）：/askai 要不要接名字檢查；`impression_moderation_service` 傳的 `repeat_penalty=1.05`、`num_ctx=2048` 沒有後端收得到，要不要拿掉；安全 JSON 的區塊名；三份人格載入（`llm_settings.py` 三組 identity／guardrails 路徑）收成一份（要位元組相同；守則檔缺檔時現在會無聲掉規則）；提示詞約定測試；舊 style_refs 路徑留著或轉 shadow。

**待做**
- [ ] KN-Q8：群友貼連結時，把 Discord 已抓好的預覽標題與描述放進插話看到的那一行（已定做；`semantic_message_text` 現在不帶，預覽只進聊天向量庫）。每則限長度。
- [ ] 查詢第二版：查到的存 `settings/runtime/` 的 JSON，下次聊到同一個詞直接帶上（KN-Q3；KN-Q10 定全開後用真實查詢定存法）；依類型淡出（新聞短、梗長）；識別碼規則加 YouTube 影片 id。成人內容先靠 `safesearch=1` 與拿掉 bing，不另做。
- [ ] C-4 自我進化迴圈（閒置批次）：合併重複、衝突取新（記「以前 X 現在 Y」）、久未提降權或封存。
- [ ] C-4 隱私公告：綁定插話頻道時自動置頂並改 channel topic。
- [ ] 觀測面板（使用者要求、重要，他不想用 CLI 或 log debug）：每次插話的完整 prompt、決策（reply／pass／error）、三層 context 數量、記憶 flush 狀態、某人記得的偏好；可和記憶監督面板（查、改、刪、禁記；`MemoryService.list_facts`／`forget` 已備）合成一個，入口照主控台的做法。現在暫用 `discord_bot.log` 的 `ambient 生成` 行與 `/logs/ambient_prompt.txt`（`AmbientChatSettings.debug_log`）。
- [ ] 延後：`retrieve_discord_context` 泛化成吃頻道的長期對話召回（碰到 /askai 核心，等人物卡召回不夠用再做）。

（經過見 [dev/ai/ambient-chat.md](dev/ai/ambient-chat.md)）

### 自然插話重構（08-09 上線）

<!-- @meta
id: ambient-natural-rework
type: DECISION
status: confirmed
depends_on: [ambient-chat]
last_confirmed: 2026-10-02
history: dev/ai/ambient-chat.md
-->

- 目標是談話自然、適當插話、有人性；省顯示卡只是副作用。
- 分工：可觀察的行為痕跡（有問句沒人回、某人連講沒人接）歸鉤子程式量測；意圖與分寸歸模型判斷。分法是問「這件事有沒有判斷錯的可能」，有就歸模型。全交給 prompt 也不行，每則訊息都要一次生成。
- 換模型時，prompt 裡所有沒寫界線的允許都會被重新詮釋一次。
- 話量的主旋鈕是 `hook_threshold`；要降載調它，不要再加機率閥；`cooldown_seconds` 不低於一次生成（約 120 秒），否則隊列越排越長。調法寫在 `AmbientChatSettings` 的註解。
- 已作廢、別重提：純 5 秒 debounce（改成靜默＋沒人打字兩個條件）；以省 GPU 排優先序；trigger 往回找（定案內容閘看整段 burst）；reaction 當學習標籤（負樣本太少，改用有沒有被接話）。
- 接續的 `got_reply` 只認它發言後的第一則（接續要保守）；11-05 起用回覆功能回它的也算。要再放寬得把接續判斷和標籤拆開。
- SearXNG（屬網路搜尋，原本記在這）：明確指定 engines 會繞過 `disabled`，停用引擎時 `default_engines` 也要同步改（現在 `default_engines` 明寫 yahoo、duckduckgo）。

---

## 點歌機器人

<!-- @meta
id: music-bot
type: STATE
status: draft
depends_on: []
affects: []
last_confirmed: 2026-11-07
history: dev/community/music.md
-->

**現況**
- `src/music/` 上線運作；歌單 `settings/music_playlists.json`（手改），面板 id 等狀態 `settings/runtime/music.json`。架構已歸檔（經過見 [dev/community/music.md](dev/community/music.md)）。
- 斷線處理（`player.py` 的 `ensure_voice`，10-16 上線）：先等 discord.py 自己重連最多 35 秒，等不到在同一條連線 `connect()`，連線已不在登記表才建新的；被打斷的歌用 ffmpeg `-ss` 從斷點續播，同一首連續 3 次就換下一首。多數斷線 1～2 秒內由 discord.py 自己接回。

**未修的 bug：續播卡死（優先）**
- `voice_client 仍在播放，將歌曲排回稍後重試` 每幾秒一次、無限重複，不播任何歌，只有重啟才停。發生過 4 次：10-16～10-18、10-20～10-22、10-23 清晨、10-30 23:32～10-31 12:02。`player.py` 之後沒修。
- 成因（11-07 讀容器內 discord.py 2.7.1 原始碼推得，未用測試驗證）：播放執行緒等連線逾時走「Aborting playback」直接 return，不設 `_end`；`after` 照樣呼叫，但 `VoiceClient._player` 還留著，`is_playing()` 永遠 True。以前介入都建新連線所以沒事；改成同一條連線重連後，舊 player 留下，`_play_next` 的防呆就一直排回。10-30 那次正是等滿 35 秒、同一條連線重連成功、續播、卡住。
- 修法方向（待使用者點頭）：上一首的 `after` 已回來而 `is_playing()` 仍 True 時先 `voice_client.stop()` 再播；防呆加連續次數上限。測試照 `test/test_music_reconnect.py` 的假連線寫。

**仍有效的規則與坑**
- 等 discord.py 重連的時限不可短於 30 秒（它自己的連線逾時），短了會互搶。
- 不要 `disconnect(force=True)` 再 `channel.connect()`：舊連線的 `_poll_voice_ws` 不會被取消，30 秒後會把新連線踢出頻道並拔掉登記（一次斷線掉兩次、丟兩首）。同一條連線 `connect()` 會先取消它。不要碰私有的 `_runner`。
- 斷線中止播放時 discord.py 不給錯誤，只能看 `after` 當下 `is_connected()` 分辨播完或被打斷。
- discord.py 2.7.1 已是最新，升版無解；它的 poller 遇 DNS 錯誤會死掉，這時播放器 35 秒後介入是對的。
- 「Aborting playback」是 DEBUG，`settings/logging.json` 的 `discord.player` 是 WARNING；查這類問題要暫調 DEBUG。

**待做**
- [ ] 修續播卡死。
- [ ] `/pause`、`/resume` 按鈕。
- [ ] 快取空間管理（LRU、磁碟用量監控）。
- [ ] 歷史播放紀錄、點歌統計。
- [ ] DAVE 加速：等 discord.py 後續版本。
- [ ] 暫緩：面板改用 `PanelBumper`。面板訊息在記憶體、按鈕就地 edit、啟動時自己清理；要搬得先把面板 id 移出 `settings/runtime/music.json`，上線那次會留一則舊面板要手動刪。

---

## 跨來源整合

<!-- @meta
id: cross-source-integration
type: TODO
status: draft
depends_on: []
last_confirmed: 2026-11-07
history: dev/relay/cross-source.md
-->

**現況**
- Telegram 轉發自成一套分層（`MessageRouteResolver`、`TelegramRenderAdapter`、`MessageRelayWorker` 等，都在 `services/relay/telegram_relay_service.py`）；其他來源發文共用 `post_to_channel`。
- Telegram 的 Discord 端設定是 `config.json` 三個 key：`telegram_relay_enabled`（只在 worker 啟動時讀）、`telegram_channel_routes`（`{"seele_ww_leak": [頻道]}`）、`telegram_replay_from_message_id`（null＝沒作用）。路由先用 chat_id 查，查不到就拿爬蟲 `runtime_config.json` 的 `source_channel` 名稱查，所以三個來源實際上都靠 `seele_ww_leak` 那一筆，bot 也因此要讀爬蟲容器的設定檔。其他轉發都是一個 `<用途>_channel_id`、走一般綁頻道。

**仍有效的規則**
- 沿用現有架構、先指出不合理處再最小修改，不另起一套分層；3 月規劃剩下的項目動手前照這條重新評估。
- `telegram_replay_from_message_id` 是啟動時把游標倒回去強制重送，值沒清掉每次重啟都會再送一次。
- 動 `config.json`、`switches.json` 前要使用者同意。換 key 的順序：先加新 key → 重啟 discord-bot → 再刪舊 key（舊程式每則都讀路由，先刪會斷）。

**未定案：Telegram 的 Discord 端改成「以服務為單位」（10-28 提出，還沒動工）**
- 已答：TG-Q1＝A 一個 `telegram_relay_channel_id`、走一般綁頻道；TG-Q2＝B 總開關搬到 `switches.json`；TG-Q3＝保留重送；TG-Q4＝拿掉爬蟲的 `source_channel`、只留 `source_channels`；TG-Q5（其他轉發 key 改名、`forward_whitelist` 整理）先不管。
- 要改：`MessageRouteResolver` 改讀 `ChannelConfig.get_configured_id`，拿掉名稱退回、讀爬蟲設定與沒人呼叫的 `is_telegram_relay_enabled`；`TelegramRenderAdapter` 沒頻道標題時寫「Telegram」；`channel_registry` 的 `_TelegramRouteInputModal` 換成一般 `register_channel`；爬蟲 `tg_config.py` 拿掉 `source_channel` 與 `TELEGRAM_SOURCE_CHANNEL`，重抓的備用取清單第一個。
- TG-Q6 開關切到 off：A 暫停，不送、不推游標，切回 on 接著送（建議）／B 跳過，切回 on 只送新的（要另寫頻道 0，否則重啟補償會送出跳過的）。待使用者。
- TG-Q7 整段重送放哪：A 做成指令，`/resend_article type:telegram` 加「這則之後全部」，照正常流程排進 worker、不用重啟（建議；`config.json` 只留綁定）／B 留在 `config.json` 改成一個 db id，照舊要重啟、用完要清。待使用者。

**待做**
- [ ] 3 月規劃剩下的（做前先重新評估）：讀資料整合（`SourceFetchPort`、`SourceFetchOrchestrator`）、統一事件模型、Route 規則抽離並納入其他來源、其他來源的事件觸發收進 `MessageRelayWorker`。
- [ ] 讀 `config.json` 收進 `ChannelConfig.load_config`：還剩 2 處自己 `open`（`discord_bot.py` 自動啟動官方文章更新、`utils/discord_members.py` 讀 `role_mapping`）；寫入已全走 `update_config`。
- [ ] `base_monitor.send_embed_to_channels` 全專案沒人呼叫，可以刪。

（經過見 [dev/relay/cross-source.md](dev/relay/cross-source.md)）

---

## 產品能力 TODO

<!-- @meta
id: product-todo
type: TODO
status: draft
last_confirmed: 2026-11-07
history: dev/architecture/product-todo.md
-->

2026-03 的規劃，大多還沒做。

- **數據**：[ ] /askai 回覆後的 👍／👎（插話已有 `ai_interactions`，/askai 沒有）；回應紀錄 jsonl 已有（`append_askai_response_log`），只差回饋欄位。[ ] 每日 KPI（互動量、滿意率、回覆長度、失敗率）。
- **好玩度**：[ ] 每日話題／今日任務。[ ] 群友印象小卡展示。[ ] 梗庫／金句（招牌梗 `signature_tag` 可當來源，金句可和 reaction 統計合併）。[ ] 連續互動天數、活躍徽章。
- **品質**：[ ] Prompt A/B。[ ] 模型路由（閒聊／技術／審核分流；GPU 一次只放一顆大模型，目前全部共用）。RAG 評估集已有：`llm/retrievers/eval`、`services/search/eval`。
- **SFT**：[ ] 蒐集 3k～10k 高品質多輪對話，先做 DPO／ORPO 小模型實驗，明顯勝過 prompt-only 才擴大。門檻（三者都要）：足量高品質資料、清楚的評估集與 KPI、prompt／RAG／模型路由都優化過仍卡住。
