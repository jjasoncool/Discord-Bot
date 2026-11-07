# 人格萃取與 Persona Agent

<!-- 給 AI：這份是歸檔檔，改之前先看完這段
結構：上半部（一頁看懂、時間線、定案與理由、踩過的坑）是整理過的重點；「## 原文」以下是當時的紀錄。
新增一段：
1. 原文放在「## 原文」目錄表下方的最前面，照現有各段的格式（## 標題、> 摘要與關鍵字、<details> 包正文，標籤前後各空一行）。
2. 目錄表加一列；dev/README.md 的「依日期」加一列。
3. 同一輪更新上半部，並把下面的「整理到」改成新段的日期。
不要改：原文正文、既有的段落標題（README 和其他檔用標題當錨點）。
找細節用搜尋，不必整份讀。改完跑 python3 dev/check.py。完整規則：AI_HANDOFF_AND_TODO.md「本檔維護規則」的「歸檔放哪」。
整理到：2026-10-13
-->

> 現況、待決與待做以交接檔為準：[Persona Agent：精簡版發布](../../AI_HANDOFF_AND_TODO.md#persona-agent精簡版發布)。
> 這裡是歷史。上半部是整理過的重點；「原文」是當時的紀錄，提到的檔名、函式、狀態可能已經改了。原文提到的 `TODO-completed.md` 是 2026-11-07 以前的單一歸檔檔，內容都拆到 `dev/` 了，從 [dev/README.md](../README.md) 找。

## 一頁看懂

這個主題管每晚 04:00 的人格萃取：AI 替每位群友寫一段個性描述，給插話與 /askai 參考。從固定流程換成會自己查資料的 persona agent，再每晚發布成精簡版。

- **08-18～08-25 影子模式**：把人格萃取改成會呼叫工具的 agent，寫獨立的表、不動線上流程。實測 tool calling 可用，定下五項（統一模型、序列接力、跑在 bot 行程內、補 `get_conversation`、thinking 分兩段）。M1、M2 做完，安靜群友的驗收 16 個證據全部真實。
- **09-28 精簡版上線（M7）**：agent 的完整描述只寫在 `persona_agent_versions`；每晚另外發布不經 LLM、照抄條目的精簡版到 `auto_personality`，插話與 /askai 只讀這份。
- **10-01～10-02 隱私與歸因**：描述裡有隱私，叫別人的暱稱被寫成口頭禪，群內流行語被算在個人身上。規則檔限制幾類不寫；發布時擋流行語與「把群友名字當口頭禪」的條目；名字表、`person_anchor`、`member_names` 統一名字；手動修正 4 條舊歸因。
- **10-13 備援退場**：精簡版連續 12 晚 failed=0，拆掉舊的人格萃取和兩個手動指令。04:00 維護搬到 `daily_maintenance.py`，變成四步：emoji 字典、招牌梗衰減、persona agent、發布精簡版。

**歸檔時（10-13）的狀態**

- [x] 精簡版每晚發布，連續 12 晚 failed=0（09-28 上線）
- [x] 隱私類別、名字表、擋流行語、共用錨點與名字模組（10-01）
- [x] 手動修正 4 條舊歸因（10-02）
- [x] 拆掉備援萃取與兩個手動指令（10-13）
- [ ] 失敗的 run 隔天重跑、證據反查失敗的那晚不寫入
- [ ] 資料庫安全網：`write_version` 失敗被當成功、只剩 drop 時寫出空描述
- [ ] 人工校正管道
- [ ] 刪掉舊萃取留下的兩份「無法分析」描述，要等使用者同意
- [ ] 名字表上線後 token 用量偏高，還在觀察

最新狀況看交接檔。

## 時間線

| 日期 | 發生什麼 | 結果 |
|---|---|---|
| 08-18 | 規劃影子模式：04:00 人格萃取改成 tool-calling agent，產出可稽核的 diff | 線上實測 tool calling、`role:"tool"` 往返、`json_schema` strict 都通；五項定案，M1～M6 節點 |
| 08-18 | 04:00 排程拆成 emoji、招牌梗、萃取三步 | `5b69042`；順帶修掉手動預覽會真的刪梗 |
| 08-18 | M1：補 `think` 缺口、四支唯讀工具；M2：`chat_with_tools`、agent 迴圈 | 安靜群友驗收：自己擴大到 90 天，16 個證據全部真實，互損文化判讀正確 |
| 08-18 | 前四次試跑全失敗 | 原因是用 `docker exec` 另開行程，禮讓沒觸發；證實 agent 不能做成獨立腳本 |
| 08-18 | 聊天表只有主鍵，手動建三個索引 | `get_messages` 752 → 38 ms、`get_conversation` 3,551 → 28 ms |
| 08-18 | 清掉 `auto_personality` 12 筆 `guild_id='0'` 的舊殘留 | 65 筆對 65 人 |
| 08-19 | 兩份 prompt 13 條核心規則重疊；加除錯指令 `/persona_agent_test` | 抽出共用 `persona_description_rules.txt`、三層疊加；指令只讀不寫 |
| 08-25 | 發現 agent 看不到 bot 自己的發言 | 記為已知盲點，刻意維持 |
| 09-28 | M7 精簡版發布上線 | 插話與 /askai 改讀精簡版（`2a0d0cf` 開 `publish_mode="on"`）；同時查出隱私、暱稱當口頭禪、群體用語等品質問題 |
| 10-01 | 唯讀盤點 66 筆精簡版，PA-Q1～Q12 定案並實作 | 規則檔限制類別、名字表、擋流行語、共用錨點與名字模組（`5aaf596`、`9b2c4d1`）；舊萃取先查跳過名單（PR-Q1） |
| 10-02 | 新程式第一晚驗收 | 寫入 63、失敗 0，擋 9 條與試算一致；舊萃取 38 人全跳過，幾秒結束 |
| 10-02 | 發現 agent 不會修舊的歸因錯誤（PA-Q13） | 使用者同意後手動修正 4 條，寫新版本並重新發布，先備份 |
| 10-02～10-13 | 精簡版每晚發布 | 連續 12 晚 failed=0 |
| 10-13 | 拆掉備援萃取（`7a369b6`） | 刪 `/personality_extract`、`/personality_extract_status`；維護搬出 `discord_bot.on_ready`，改成四步；手動入口不補 |

## 定案與理由

| 決定 | 為什麼 |
|---|---|
| 人格萃取改成 tool-calling agent，先走影子模式：寫獨立的表、不動線上排程 | 讓模型自己決定撈多少資料、追哪些線索，產出可稽核的 diff，不是整份覆蓋 |
| agent 跑在 bot 行程內、共用 `stream_exclusive`，每一步主動禮讓，不做成獨立腳本 | 獨立行程會讓總吞吐被平分（實測 33 → 7～11 tok/s，askai 慢 3 倍），禮讓機制也只在同一個行程內有效 |
| 補第四支工具 `get_conversation` | 人格訊號在互動不在句子，訊息平均 14 字；證據是孤句時，人工翻回去也驗不出對錯 |
| 收集資料時 thinking 關，最後產 diff 才開 | 選工具是機械決策；8 步全開約 12 分鐘一人，只開最後一步約 3 分鐘 |
| context 用 token 預算，不用則數 | 一則可能 5 字也可能 300 字 |
| 人格萃取的模型統一成同一顆，延到 M4 才改 | 兩顆會互踢、每次重載；agent 到 M4 才真的跑批次，提早改只會讓舊萃取先變慢 |
| 新建 `persona_agent_versions`（版本永不覆蓋）與 `persona_agent_runs`，不放進成員資料向量表 | 版本歷史會被語意召回撈出來當現況；不需要 embedding；需要 UNIQUE 約束 |
| 描述品質規則抽成共用檔 `persona_description_rules.txt`，prompt 三層疊加 | 兩份 prompt 13 條核心規則重疊，改一邊另一邊會靜默分岔 |
| prompt 不寫 golden-string 測試 | prompt 常手動微調，啟動 gate 會動不動就紅 |
| agent 看不到 bot 自己的發言，維持現狀 | 不會把 bot 的發言算成群友的，也不會形成「bot 影響氣氛 → 描述反映 bot → 又餵回 bot」的迴圈 |
| 描述不寫健康、性向、感情家庭、政治、具體行程；住哪裡、宗教、財務、職業不限制（PA-Q1、Q6） | 使用者：都是群裡公開講的；跟發布端不過濾一致，AI 重寫時也不會把這類內容慢慢刪掉 |
| 發布端不做隱私過濾（PA-Q2） | 使用者看到後備的寫法後改口：這些沒差，過濾太敏感；招牌梗的關鍵字掃精簡版 3 筆有 2 筆誤判 |
| 名字表列顯示名稱、伺服器暱稱、全域名稱，每晚從成員快取讀，不建資料庫（PA-Q8） | 改名時 Discord 會推送、快取自動更新，存資料庫反而要處理同步 |
| 名字表本人排第一並標「（本人）」，不放 user_id、不編號 | 模型原本不知道本人叫什麼；ID 會被抄成證據（以前擋下的假證據 37% 是別人的真訊息 ID），編號會跟條目的 ref 混 |
| 發布時只擋口頭禪類的「群內流行語」與「把別的群友名字寫成口頭禪」，排除暱稱與貼圖名 | 原本「同一詞 ≥2 人出現就全部不發」會誤殺 47 條，包括貼圖偏好和真實的人際關係 |
| 白天的主名字統一用 Discord 顯示名稱，其他叫法放【名字對照】（PA-Q11） | 成員在 Discord 上看到的就是它；同一資訊不放兩處，也不吃發布的預算 |
| 末四碼撞號時自動加長（PA-Q12 B） | 錨點是聊天行、人物卡、名字對照的共同鍵，撞號會把兩人的名字併在一起；抽成共用函式後成本低，今天的輸出不變 |
| 名字只用空白分段 | 照符號拆會拆出遊戲角色名，問角色時會被當成在講某位群友 |
| 4 條舊歸因錯誤手動修正：每人寫一個新版本，只改那一條，`model=manual`（PA-Q13） | agent「沒有反證就 keep」，舊條目不會自己被蓋掉；版本表只增不改，舊版本就是備份 |
| 備援萃取等精簡版連續 7 晚 failed=0、抽查沒有新類型嚴重問題才刪（PR-Q2 A） | 新規則上線後先觀察幾晚再拿掉備援 |
| 新成員接受空窗，等 agent 寫出條目（PR-Q3 A） | agent 的納入門檻比舊萃取寬，通常幾天內就有 |
| 兩個手動萃取指令都刪（PR-Q4 A） | 指令收斂計畫本來就要減少指令數；看單人用 `/persona_agent_test` |
| 手動入口不補、「精簡版」名稱不改 | 使用者：「不用手動入口」「維持精簡版就可以，確實是精簡後的資料」 |
| 刻意不做：revise 沿用舊證據；keep「今晚附的證據一律保留」 | 前者會灌高對話次數，後者會擠掉最新名額 |

## 踩過的坑

- **用 `docker exec` 另開行程跑 agent，禮讓從沒觸發**：`stream_exclusive()`、`stream_busy()` 只在同一個行程內有效。agent 和插話正面對撞，約 12k 就 context 超限，吞吐 33 → 7～11 tok/s。不是顯卡的問題；要在 bot 行程內跑（`/persona_agent_test`）。
- **可用的 context 會浮動**：KV 由多個 slot 共享，/askai 或插話同時在跑時，約 17k 的請求也會爆。估算擋不住，超限時把較早的 tool 內容換成佔位字串再試一次（不能刪訊息，`tool_call_id` 要一一對應）。
- **模型一步會丟好幾個工具呼叫**：實測一步六個 `get_conversation`，步末才檢查預算來不及，要每個呼叫前檢查。`get_conversation` 還會被叫到 9 次，prompt 限 5 次。
- **聊天表原本只有主鍵**：統計沒更新時規劃器估 456 筆、實際 265,118 筆。`::timestamptz` 轉型不能建索引，改成字串比較（ISO 字串的字典序就是時間序）。
- **`think` 參數在 Lemonade 分支被丟掉**：Ollama 換 Lemonade 時留下的斷點，管線本身是完整的。
- **tool calling 時空 content 是正常的**：只有 content 和 tool_calls 同時空才算 `empty_content`。
- **discord.py 的 `file` 預設是 `MISSING`，不是 `None`**：傳 `file=None` 會炸，剛好發生在沒有 diff 的失敗路徑。
- **回覆互動只有 15 分鐘**：agent 可能跑幾十分鐘，完整 diff 一律寫進 log。
- **模型把互損文化讀成攻擊性**：「你也太廢」被判成尖酸刻薄，prompt 要寫進這種文化。
- **暱稱被寫成口頭禪、群體用語被算成個人特徵**：agent 寫描述時沒讀自介和印象，不知道某個暱稱指的是誰。
- **agent 不會主動修舊條目**：名字表只附在旁邊，規則是「沒有反證就 keep」，常被提到的詞永遠搜得到佐證。
- **找人比對太寬**：問句候選詞用「開頭」比對 Discord 名字，3,408 則訊息有 54 則對到人，多半是常用詞誤中，bot 自己也在名單裡。改成看詞的邊界並排除 bot。
- **撞號加長的人，對方一離開就縮回 4 碼**：離開者的舊訊息還在，兩人又變成同一個錨點。改成加長過的不縮回。
- **同一秒改檔又還原、大小不變時，Python 會沿用改壞的 `.pyc`**：突變測試設 `PYTHONDONTWRITEBYTECODE=1` 並先清 `__pycache__`。
- **09-29 以前的 `discord_bot.log` 混有啟動測試的假紀錄**：之後測試一律寫 `/logs/test_run.log`。
- **名字表上線後 token 用量變多**：「預算用盡、停止收集」10-02 有 9 次、10-10～10-13 共 35 次。
- **agent 看不到 bot 自己的發言**：「群友說話 → bot 插話 → 群友回 bot」在 agent 眼裡像自言自語，插話頻繁的頻道比較容易誤判。

## 原文

新的在前。每段標題下面是摘要，正文在「展開原文」裡。

| 日期 | 段落 | 摘要 |
|---|---|---|
| 2026-10-13 | [Persona Agent M7（10-13 合併版）](#persona-agent-m7精簡版上線隱私與歸因定案備援萃取退場歸檔-2026-11-07原至-2026-10-13) | 精簡版連續 12 晚 failed=0，10-13 拆掉備援萃取與兩個手動指令；另列架構、取捨、待辦與坑。 |
| 2026-10-01 | [隱私、歸因與名字對照（10-02）](#persona-agent-m7隱私與歸因名字對照備援萃取退場第-1-階段歸檔-2026-10-13原-2026-09-2810-02) | 09-28 品質問題與 10-01 盤點；PA-Q1～Q13 定案與實作（隱私、名字表、流行語、錨點），10-02 驗收。 |
| 2026-08-18 | [影子模式規劃 M1～M6（08-18）](#persona-extraction-agent-影子模式規劃-m1m6歸檔-2026-09-28原-2026-08-18) | 人格萃取改成 tool-calling agent 的規劃：實測、五項定案、四支唯讀工具，M1、M2 完成；已被 M7 取代。 |

## Persona Agent M7：精簡版上線、隱私與歸因定案、備援萃取退場（歸檔 2026-11-07，原至 2026-10-13）

> 精簡版連續 12 晚 failed=0，10-13 拆掉備援萃取與兩個手動指令；另列架構、取捨、待辦與坑。
>
> 關鍵字：persona agent、精簡版、auto_personality、persona_agent_versions、publish、04:00 維護、隱私類別、名字表、備援萃取、隔離

<details>
<summary>展開原文（約 4,674 字）</summary>

> 從 `AI_HANDOFF_AND_TODO.md`「Persona Agent M7：精簡版發布（2026-09-28 已上線；精簡版連續 12 晚穩定，待刪備援萃取）」區塊（`persona-extraction-agent`）瘦身前的完整原文；交接檔只留現況、規則與坑、未定案、待做。

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

</details>

## Persona Agent M7：隱私與歸因、名字對照、備援萃取退場第 1 階段（歸檔 2026-10-13，原 2026-09-28～10-02）

> 09-28 品質問題與 10-01 盤點；PA-Q1～Q13 定案與實作（隱私、名字表、流行語、錨點），10-02 驗收。
>
> 關鍵字：PA-Q1～Q13、PR-Q1、群內流行語、名字表【群友的稱呼】、本人標記、person_anchor 撞號加長、member_names 只用空白分段、名字對照、詞的邊界、10-02 驗收、手動修正四條舊歸因 persona_manual_fix

<details>
<summary>展開原文（約 12,423 字）</summary>

> 從 `AI_HANDOFF_AND_TODO.md`「Persona Agent M7」區塊搬來的原文：09-28 的品質問題、10-01 唯讀盤點、PA-Q1～Q13 每一題的查證與定案、PA-Q11／Q12 實作與獨立複查、10-02 驗收、PA 第 1 輪實作、③ 退場第 2 輪的事實與 PR-Q1。交接檔留架構、狀態、定案摘要、PR-Q2～Q4、待辦與坑。

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

</details>

## Persona Extraction Agent 影子模式規劃 M1~M6（歸檔 2026-09-28，原 2026-08-18）

> 人格萃取改成 tool-calling agent 的規劃：實測、五項定案、四支唯讀工具，M1、M2 完成；已被 M7 取代。
>
> 關鍵字：已被 M7 取代、四支唯讀工具、五項定案、線上實測

<details>
<summary>展開原文（約 18,183 字）</summary>

> **歸檔原因**：已被 M7（精簡版發布，2026-09-28 上線）取代；現況見 `AI_HANDOFF_AND_TODO.md` 的「Persona Agent M7」區塊。
> 以下為原文，只拿掉開頭指向已刪除 HANDOFF 檔的過時說明，`status` 改成 deprecated。

### 原盤點紀錄

- 2026-08-18（人格萃取 Agent 影子模式，**規劃定案・未開工**；本輪只做查證與線上實測，未動任何 code／設定檔）：把每日 04:00 的固定人格萃取升級成 tool-calling agent，產出**可稽核的 diff** 而非整份覆蓋；影子模式並行、寫獨立表、**不動 production**。**線上實測（Lemonade 11.5.0 + Qwen3.8-27B-UD-Q4_K_XL / llamacpp b9747）**：tool calling ✅（`finish_reason=tool_calls`，4.4s / 33 tok/s）、`role:"tool"` 回合往返 ✅、`response_format: json_schema` strict ✅ → **不需自架 llama-server、不需 `--jinja`，M0 直接跳過**。**併發**：1 發 33 tok/s、2 發各 11~12、3 發各 7 → llama-server 多 slot 真並行但**總吞吐固定被平分**（故獨立進程方案會讓 askai 慢 3 倍）。**prompt cache**：冷 3417 tok/10.1s → 熱 18 tok/0.3s，且插入不同前綴後仍命中（多組 cache 並存）；插話 prompt 78%（10,823 字元）是靜態前綴，現有組裝順序已是最優。**資料面**：chat 表 273,780 筆 / 81 人 / `message_id` **100% 覆蓋**（evidence 機制成立）；訊息平均僅 11~38 字；14 天符合門檻 46 人、337,211 字。**五項定案**：①`personality_model` 統一改 27B（`max_models.llm=1` 會互踢）②04:00 觸發、production→agent **序列接力**（約 05:10 收工）③agent 跑在 bot process 內共用 `stream_exclusive`、**不可做成獨立腳本**、每 step 主動禮讓 ④**補第四支工具 `get_conversation`**（人格訊號在互動不在句子，不補會輸給現有 pipeline）+ context 改 token 預算 ⑤thinking 分兩段（收集關、產 diff 開，12 分/人 → 3 分/人）。**M1 第一項＝補 code 缺口**：`think` 覆寫管線完整存在，唯一斷點在 [_build_chat_extra_body](../../src/services/llm_service.py#L573-L588) 的 lemonade 分支把它丟掉。詳見 [Persona Agent 區塊](#persona-extraction-agent-影子模式規劃-m1m6歸檔-2026-09-28原-2026-08-18)。

<!-- @meta
id: persona-extraction-agent
type: DECISION
status: deprecated
last_confirmed: 2026-08-18
depends_on: personality_extractor, llm_service, lemonade_gate, member_profile_store, chat_persistence
affects: llm_service._build_chat_extra_body, discord_bot 排程, llm_runtime_config.json
-->

**目標**：把每日 04:00 的固定 pipeline 升級成 tool-calling agent，讓模型自己決定撈多少資料、追查哪些線索，產出**可稽核的 diff**（而非整份覆蓋）。**影子模式**：與現有 pipeline 並行、寫獨立表、**不動 production 排程**（[discord_bot.py:169-266](../../src/discord_bot.py#L169-L266) 含啟動補跑邏輯，整段不碰）。

### 本輪線上實測（2026-08-18，全部對真實服務打過）

後端＝Lemonade 11.5.0（`192.168.56.1:13305`）+ `Qwen3.8-27B-GGUF-UD-Q4_K_XL`，llamacpp recipe b9747、ctx 32768、雙卡 Vulkan0+1。

- **tool calling ✅**：`finish_reason == "tool_calls"`、結構化 `tool_calls` 正確，**4.4 秒 / 33 tok/s**（speculative decoding draft 接受率 32/33）
- **`role:"tool"` 回合往返 ✅**；**`response_format: json_schema` strict ✅**（輸出直接 `json.loads()` 過）
- → **不需自架 llama-server、不需煩惱 `--jinja`（Lemonade 已處理），M0 直接跳過**
- **併發**：1 發 33 tok/s、2 發各 11~12 tok/s、3 發各 7.0~7.5 tok/s，牆鐘皆未排隊 → llama-server **多 slot 真並行，但總吞吐固定（~22~33 tok/s）被平分**
- **prompt cache**：A 前綴冷 3,417 tok / 10.1s → 熱 18 tok / **0.3s**；中間插入不同前綴 B 之後 A 仍命中 → **多組 cache 並存**（各 slot 各自 KV）
- **大 context**：單發 11,954 tok prefill **35.2s @ 339 tok/s** 成功
- **插話 prompt 結構**：實際 13,874 字元中 **10,823（78%）是靜態 system 前綴**；[llm_service.py:463-469](../../src/services/llm_service.py#L463-L469) 已把 volatile 全放 user message、`asker_profile` 擺 system 末端 → **最長共同前綴已最大化，無需改動**
- **資料面（pgvector 實查）**：`data_discord_messages_index` 273,780 筆 / 81 人 / **`message_id` 100% 覆蓋**（Open Question「evidence 可否引用 msg_id」＝**是**）；訊息平均長度僅 **11~38 字**；7 天分層 A≥500:5人 / B100-499:13 / C30-99:12 / D10-29:10 / E<10:9人（5 人佔 57% 發言量）；14 天符合門檻 **46 人、337,211 字**

### 五項定案

**① `personality_model` 統一改 Qwen3.8-27B**
Lemonade `max_models.llm = 1`（embedding 有獨立 slot pool 不衝突）。現況 production 用 `Qwen3-14B-GGUF`、agent 要用 27B → 兩顆互踢，每次請求重載。統一後 04:00 不再驅逐 27B，**早上第一次插話省下 30-60s 重載（[llm_http_client.py:337](../../src/llm/llm_http_client.py#L337) 註解）+ ~30s prefill**。不換 quant（Q5/Q6）——tool calling 只在現有 Q4_K_XL checkpoint 上驗證過，換 quant＝換掉唯一已驗證的變數。

**② 04:00 觸發、production → agent 序列接力**
① production 萃取：16 批 × ~135s（prefill 15k tok ÷ 339 + decode 3k tok ÷ 33）≈ **40 分鐘** → 約 04:40 結束；② agent 影子：10 人 × 2~3 分 ≈ **30 分鐘** → 約 **05:10 全部收工**。agent 啟動前先看 `personality_extractor._extraction_running` 旗標（唯讀，不改 production）。**不用時鐘錯開**——既然定案「一次只做一件事」，用排隊即可。

**③ agent 跑在 bot process 內、共用 `stream_exclusive`**
一次只做一件事。**不可做成獨立腳本／獨立容器**——會繞過 [lemonade_gate.py](../../src/llm/lemonade_gate.py) 開頭記載的 connection reset 坑，且吞吐三分天下讓 askai 慢 3 倍（實測 33 → 7~11 tok/s）。每個 step 前主動禮讓（`stream_busy()` / `foreground_recently_active(90)` 就 sleep 再看）；agent **不得**呼叫 `note_foreground_activity()`（會壓制插話 90 秒，[llm_settings.py:378](../../src/sys_settings/llm_settings.py#L378)）。

**④ 補第四支工具 `get_conversation(channel_id, around_msg_id, before=15, after=15)`**
人格訊號在**互動**不在句子：實測訊息平均 14 字，「你開他」「剩我純心賞」單看零資訊。原 handoff 的三支工具只回單人碎片，模型只會**寫空話**或**腦補**——冒煙測試已示範：丟「你也太廢」→ 判「尖酸刻薄、帶有攻擊性」（實際是互損型社交）。**更關鍵：`evidence_msg_ids` 的稽核價值依賴上下文**，evidence 若是孤句，人工翻回去也驗不出對錯，防幻覺機制形同虛設。現有 pipeline 反而歪打正著（[personality_extractor.py:356](../../src/llm/personality_extractor.py#L356) 按時序交錯整批人訊息）→ **不補這支，agent 版會明確輸給現況**。
context 改用 **token 預算**（[tokenization.py](../../src/llm/tokenization.py) 估算，累計上限 24,000，留 8,000 給 thinking + 輸出），**不用「則數」**（一則可能 5 字也可能 300 字）。

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

覆寫管線**完整存在**——[`resolve_request_think()`](../../src/services/llm_service.py#L243) 有明確優先序（override > `backends.ollama.extra_body.think` > 舊欄位 > True），一路傳到 `generate_reply(think=)` → `chat_raw(think=)` → `_build_chat_extra_body(think=)`，且已有 caller 在用（[llm_commands.py:680](../../src/commands/llm_commands.py#L680)、[diary_reflection.py:201](../../src/llm/diary_reflection.py#L201)）。

**唯一斷點**在 [_build_chat_extra_body 的 lemonade 分支](../../src/services/llm_service.py#L573-L588)：非 ollama 後端直接把 `think` 丟進 `ignored` 只記 debug log；其 docstring 自承「非 ollama backend 此欄位無實際作用，仍保留以向後相容呼叫端」。**這是 Ollama → Lemonade 遷移時留下的斷點**，不是缺機制。

**修法**：lemonade 分支把 `think` 映射成 `chat_template_kwargs.enable_thinking`。**預設維持 config 值、只有明確傳入才覆寫** → askai／插話／production 萃取行為完全不變。已實測 Lemonade **吃這個 per-request 覆寫**（本輪每發冒煙測試都在 body 直送 `{"enable_thinking": false}`，全部生效）。單元測試必須涵蓋「不傳參數時 extra_body 與現況位元相同」。附帶修好 [diary_reflection.py](../../src/llm/diary_reflection.py#L201) 的同名旋鈕（目前預設 `None`，尚未壞）。

### agent 執行期間的影響面

| 功能 | 影響 | 機制 |
|---|---|---|
| /askai、被 @ / reply 的插話 | ⏳ 排隊，最多等一個 agent step | `asyncio.Lock` FIFO 公平，agent 一步一放鎖 |
| 自發插話 / 接續 / 記憶沉澱 | ❌ **整輪跳過**（不是延後） | [ambient_reply.py:1103](../../src/llm/ambient_reply.py#L1103)、[:1112](../../src/llm/ambient_reply.py#L1112)、[memory_service.py:89](../../src/services/memory_service.py#L89)、[ambient_memory.py:73](../../src/llm/ambient_memory.py#L73) 見 `stream_busy()` 即讓位 `return` |
| 訊息寫入 pgvector | ⏳ 排隊，不掉 | [chat_persistence.py:173](../../src/llm/chat_persistence.py#L173) 同持一把鎖 |

⚠️ `chat_raw` 的 timeout **在取得鎖之後才起算**（[ambient_reply.py:1267](../../src/llm/ambient_reply.py#L1267) 註解），等鎖無上限 → agent 必須維持「一步一放鎖」，絕不可跨 step 持鎖。

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

- **2026-08-25｜已知盲點：agent 看不到 bot 自己的發言**：`get_conversation` 還原現場時看不到插話內容——[discord_bot.py:446](../../src/discord_bot.py#L446) 的 `if not message.author.bot` 擋掉了 bot 訊息，實測最近 200 則插話**沒有任何一則**進 `data_discord_messages_index`。
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
- **2026-08-18｜清除 `auto_personality` 殭屍列**：12 筆 `guild_id='0'` 的舊格式殘留（`last_extracted_at` 為空、author_id 與正式版完全重複）已刪除，現為 65 筆／65 人完全對齊。原本無害（[context_retriever.py:771](../../src/llm/context_retriever.py#L771) 有 guild_id 過濾），刪除理由是避免新寫的 `get_current_persona` 漏帶 `guild_id` 時撈到舊基準產出錯誤 diff。**工具層仍強制帶 `guild_id`——正確性不靠資料剛好乾淨。**

</details>
