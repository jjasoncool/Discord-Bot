# 巴哈／PTT 轉發

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

> 現況、待決與待做以交接檔為準：[巴哈／PTT 轉發：刪文與亂改的防禦](../../AI_HANDOFF_AND_TODO.md#巴哈ptt-轉發刪文與亂改的防禦)。
> 這裡是歷史。上半部是整理過的重點；「原文」是當時的紀錄，提到的檔名、函式、狀態可能已經改了。原文提到的 `TODO-completed.md` 是 2026-11-07 以前的單一歸檔檔，內容都拆到 `dev/` 了，從 [dev/README.md](../README.md) 找。

## 一頁看懂

這個主題管巴哈姆特論壇的爬蟲，以及把文章轉發成 Discord 論壇討論串（本文、回覆、留言格、續文、之後的增量更新）。

- **04-01～04-05**：爬蟲 MVP 與首版轉發。一個 `snA` 一個討論串，主文藍、回覆綠、留言格灰；接著做了增量更新（hash 有變才編）、bot 端 state 搬到 SQLite、爬蟲抓完用 webhook 通知 bot，以及長文續文、多圖分批、子看板、分類黑名單。
- **04-27**：整段歸檔。爬蟲 → 資料庫 → API → Discord 全程在跑；端到端測試、Alembic migration、RAG 第三階段沒排進主線。
- **10-02 起因**：9/29 統一 log 後看到大量 429，全是編輯巴哈討論串裡的舊訊息，10/01 一天 849 次。Discord 對編輯舊訊息有沒公開的限速，同一個討論串約 5 秒只能編一則，舊程式只按「同一則訊息」冷卻 1.5 秒。
- **10-02 修正**：同一個討論串的所有編輯改成間隔 6 秒排隊；順帶修好續文導航連結被洗掉、新留言格沒記 hash 導致新留言不出現等顯示錯誤。上線第一輪 429 從 104 次降到 0（`b11df27`），31 格舊的錯誤顯示用一次性腳本修好。
- **10-13**：上線後觀察結案，交接檔只留摘要與觀察項。

**歸檔時（10-13）的狀態**

- [x] 爬蟲 → 資料庫 → API → Discord 全程在跑（04-27）
- [x] 同一討論串的編輯 6 秒排隊，上線第一輪 429 由 104 次降到 0（10-02）
- [x] 續文導航連結、新留言不出現等顯示錯誤修好，31 格舊錯誤一次性修復（10-02）
- [ ] 刪文偵測：`is_deleted` 從沒被設成 true，Discord 保留原文、不標示
- [ ] 觀察每天 429 是否維持 0、熱門串單輪耗時（最多約 117 次編輯、約 12 分鐘）會不會影響下一輪
- [ ] 端到端測試、Alembic migration、RAG 第三階段（04-27 列為未來工作）

最新狀況看交接檔。

## 時間線

| 日期 | 發生什麼 | 結果 |
|---|---|---|
| 04-01 | 爬蟲 MVP：列表、主文、留言（HTML＋XHR）、回文抓取，寫進資料庫；首版轉發與 `/get_baha_post` | 每 1 小時排程抓取存檔；一個 `snA` 一個論壇討論串 |
| 04-02 | 增量更新、bot 端 state 從 JSON 搬到 SQLite、webhook 通知 | 遷移完成（articles 446、fb 386、ptt 507 筆）；爬蟲抓完呼叫 `POST /notify/{source}` |
| 04-03 | 已完成內容與設計文件從交接檔移出 | 剩端到端測試、Alembic migration、RAG ingestion |
| 04-05 | 續文、多圖分批、並行上限、子看板、分類黑名單 | 第一則 embed 上限改 3500；無音區不發 Discord |
| 04-12 | 反爬基礎設施 `BaseScraperClient` | 爬蟲容器統一用 curl_cffi |
| 04-27 | 巴哈專區整段歸檔 | 端到端流程在跑；RAG 第三階段列為未來工作 |
| 10-02 | 查 429 限速與續文／留言格顯示錯誤，BH-Q1～Q9 分三輪定案 | 同串編輯 6 秒排隊；上線第一輪 429 由 104 → 0；31 格舊錯誤顯示修好（`b11df27`） |
| 10-13 | 上線後觀察結案，從交接檔歸檔 | 刪文偵測仍沒做，等遇到實際案例 |

## 定案與理由

| 決定 | 為什麼 |
|---|---|
| 第一則 embed 上限 3500 字 | 避免 Discord 回 500 |
| 增量更新用 md5 比對 embed 描述，沒變就不編 | 防 Discord 限速 |
| 留言唯一鍵用 `(parent_sn, comment_id)`；`floor`、`position` 只供顯示 | `floor` 會跳號 |
| 同一個討論串的所有編輯間隔 6 秒，不分新舊訊息（BH-Q1） | Discord 對編輯舊訊息的限速是每個討論串約 5 秒一則；不把 Discord 沒公開的「1 小時」寫死 |
| 間隔從真正編完起算；被拒絕的編輯退回登記、不佔名額 | discord.py 吃到 429 會自己等完重試，那段不能算進去；封存串每則失敗都白等 6 秒，9/26～27 曾一天約 300 次 |
| 推噓數照舊有變就同步（BH-Q2） | 排隊後不會再撞限速，不為此讓推噓數落後 |
| 續文每輪逐則比對、只編有變的，有變時保留導航連結（BH-Q3） | 以前本文 hash 一變就把續文全部重編而且不帶連結；hash 只涵蓋第一則 embed，後段改了續文永遠不更新 |
| 舊的錯誤顯示跑一次性修復，只修 log 圈出的回覆留言格（BH-Q5 選 B） | 修最明顯的症狀（留言沒出現、還寫「等待更新中」），成本小；推數差一兩個的影響小，也會隨時間離開轉發範圍 |
| 本文或回覆被切斷時，底部一律加「⬇️ 更多內文」連到第一則續文，hash 用含連結的版本算（BH-Q6 選 B） | 每個被切斷的區塊都有往下的連結，修改變長或變短再變長都讀得到全文；連結目標是第一則續文 id、建立後不變，hash 不會每輪判定不同 |
| 封存的討論串沒有新回覆就整輪跳過，有新回覆才解封、一起補上累積的變動（BH-Q7 選 B） | 發文本來就會解除封存，未上鎖時只需要發言權限 |
| 新回覆編號改成 `len(existing_sns)`（BH-Q8 選 A） | 主文是 #1，已經算在既有清單裡 |
| 刪文與被擋下的大幅刪減，Discord 保留原文、不標示（BH-Q9 選 A） | 目前 0 篇偵測到刪除，被擋下的有史以來 1 篇；等遇到實際刪文案例再做偵測 |
| 續文預留 110 字給導航連結（`CONTINUATION_NAV_RESERVE`），留言格的 `LAST_SLOT_NAV_RESERVE` 不動 | ID 最長 20 位數時連結 107 字；改留言格會讓所有第三格重新分配、大量重編 |

## 踩過的坑

- **Discord 對編輯舊訊息的限速比公開的嚴**：同一個討論串約 5 秒只能編一則（429 要求等待中位數 4.1 秒、最長 5.04 秒）。被擋的訊息都發出超過 1.7 小時，剛發的從沒被擋；3 篇並行時各串各自被限速。要以討論串為單位排隊。
- **用 REST 比對 Discord 實際內容也會被限速**：前兩次每秒讀 4 則被擋，讀到空內容，誤判成「32/94 本文、100/276 留言格不一致」，數字作廢。要照 `X-RateLimit-Remaining`／`X-RateLimit-Reset-After` 等、429 與 5xx 重試，而且挑兩輪更新之間比對（bot 約每小時 :12 開始），不然會把時間差當成錯誤。
- **續文導航連結被洗掉**：本文 hash 一變就把續文無條件重編，重編內容不帶「⬇️ 更多內文」。有 2 則以上續文的 12 篇中 9 篇連結已消失。
- **續文切到滿時連結塞不下**：預留 100 字，連結實際 104 字（ID 19 位數），sn=111119 從建立起就沒有連結。
- **新建的格子沒記 hash，新留言就不出現**：下一輪走「首次寫入只存不編」，新留言要等之後再有變動才一起出現，沒再變動就永遠不出現；三天內有 35 則回覆的留言格一直是舊的。建立當下就要記 hash。
- **舊程式補導航時會蓋掉本文**：續文從 0 則變 1 則時，用只有描述的 embed 去編本文，本文的標題與圖片會不見。
- **Discord 會修掉頭尾空白**：逐則比對續文時要忽略頭尾空白，不然每輪都判定不同。
- **刪文其實沒有偵測**：`is_deleted` 欄位存在但沒有程式設它，被刪的文章 API 照樣回傳資料庫裡的版本，Discord 一直保留原樣。新內文是空字串時大幅刪減的檢查不生效（`new_len > 0`），會直接覆蓋。
- **計時測試在機器忙時會誤紅**：斷言「不超過多久」的兩項用 0.5 秒間隔，留約 0.45 秒餘裕。
- **兩個沒解決的風險（04-27 記）**：`snB == sn` 高度吻合但沒有百分之百證明；巴哈 HTML 結構再變，`section.c-section`、`Commendlist_*` 選擇器可能失效。

## 原文

新的在前。每段標題下面是摘要，正文在「展開原文」裡。

| 日期 | 段落 | 摘要 |
|---|---|---|
| 2026-10-13 | [編輯限速修正結案（10-13）](#巴哈轉發編輯限速與續文留言格顯示修正上線後觀察結案歸檔-2026-11-07原至-2026-10-13) | 交接檔瘦身前的摘要：10-02 修正已上線、429 由 104 降到 0；仍待觀察 429 與熱門串耗時，刪文偵測沒做。 |
| 2026-10-02 | [編輯被限速與顯示錯誤（10-02）](#巴哈轉發編輯被限速續文留言格顯示錯誤歸檔-2026-10-13原-2026-10-02) | 查出同串約 5 秒只能編一則，改成同串 6 秒排隊；修續文連結被洗掉與新留言不顯示，BH-Q1～Q9 定案。 |
| 2026-04-27 | [巴哈專區整段歸檔（04-27）](#bahamut-專區整段歸檔歸檔-2026-04-27) | 端到端流程已在跑；記下兩個未解風險，以及端到端測試、Alembic、RAG 第三階段等未排入主線的工作。 |
| 2026-04-05 | [續文、多圖、並行與子看板](#bahamut-續文多圖並行子看板等完成歸檔2026-04-05) | 長文續文、多圖每批 10 張、並行上限 3、子看板、分類黑名單、thread 被刪自動重建等完成項目。 |
| 2026-04-03 | [知識層清理與設計文件](#bahamut-正式知識層清理歸檔2026-04-03) | 從交接檔移出的已完成能力清單與已定案設計：ID 語意、文章結構、留言抓取、資料表與 Discord 呈現方式。 |
| 2026-04-02 | [增量更新與 SQLite 遷移](#bahamut-增量更新--sqlite-遷移--webhook-通知完成歸檔2026-04-02) | 既有討論串改走增量更新（hash 有變才編），state 搬到 SQLite，爬蟲抓完用 webhook 通知 bot。 |
| 2026-04-01 | [爬蟲 MVP 與首版轉發](#bahamut-scraper-mvp-完成歸檔2026-04-01) | 第一階段抓取全部完成、資料表大部分完成，首版轉發做出主文、回覆、留言格與溢出導航，並定下 ID 模型。 |

## 巴哈轉發：編輯限速與續文／留言格顯示修正（上線後觀察結案）（歸檔 2026-11-07，原至 2026-10-13）

> 交接檔瘦身前的摘要：10-02 修正已上線、429 由 104 降到 0；仍待觀察 429 與熱門串耗時，刪文偵測沒做。
>
> 關鍵字：bahamut_monitor、編輯限速、429、續文導航、留言格、_edit_with_cooldown、BH-Q1～Q9、is_deleted、DF-Q1～Q3

<details>
<summary>展開原文（約 543 字）</summary>

> 從 `AI_HANDOFF_AND_TODO.md`「巴哈轉發：編輯被限速＋續文／留言格顯示錯誤（2026-10-02 已上線）」區塊（`bahamut-edit-pacing`）瘦身前的完整原文；交接檔只留現況、規則與坑、未定案、待做。

> 2026-10-02 已上線並驗證（commit `b11df27`）：同一討論串所有編輯間隔 6 秒排隊、續文每輪逐則比對只編有變的並保留導航連結、本文底部連到第一則續文、建立當下就記 hash、封存串等新回覆再解封補上、新回覆編號修正；上線第一輪 429 由 104 → 0；BH-Q5 的 31 格舊錯誤顯示已用一次性腳本修好。症狀、查證、BH-Q1～Q9 的定案與原選項、測試、複查、上線驗證全文已歸檔到 `TODO-completed.md`「巴哈轉發：編輯被限速＋續文／留言格顯示錯誤（歸檔 2026-10-13，原 2026-10-02）」。
>
> 仍有效：刪文偵測沒做（`is_deleted` 從沒被設成 true），Discord 保留原文、不標示，等遇到實際刪文案例再做（記憶「Bahamut 刪文偵測待辦」）；之後觀察每天 429 是否維持 0、熱門串單輪耗時（最多約 117 次編輯 ≈ 12 分鐘）是否影響下一輪。

</details>

## 巴哈轉發：編輯被限速＋續文／留言格顯示錯誤（歸檔 2026-10-13，原 2026-10-02）

> 查出同串約 5 秒只能編一則，改成同串 6 秒排隊；修續文連結被洗掉與新留言不顯示，BH-Q1～Q9 定案。
>
> 關鍵字：discord.http 429、同串 6 秒排隊、BH-Q1～Q9、續文導航連結被洗掉、hash 記帳、封存串解封、新回覆編號、repair_stuck_slots 31 格、b11df27、刪文偵測沒做

<details>
<summary>展開原文（約 7,033 字）</summary>

> 從 `AI_HANDOFF_AND_TODO.md` 同名區塊搬來的原文：症狀、查證、BH-Q1～Q9 的定案與原選項、改了什麼、測試、獨立複查、一次性修復、上線驗證。交接檔只留一段摘要與觀察項。

**症狀**：9/29 log 統一後看得到的 `discord.http` 429，全是 `PATCH channels/{巴哈討論串}/messages/{id}`：9/29 55 次、9/30 212、10/01 849、10/02 到 08:13 已 201。

**機制（一句話）**：Discord 對編輯舊訊息有未公開的較嚴限速（同一個討論串約 5 秒只能編一則；429 要求等待中位數 4.1 秒、最長 5.04 秒），我們只按「同一則訊息」冷卻 1.5 秒，同串不同則約 1 秒編一則，熱門串每則都先吃 429 再等。

**查證（唯讀）**
- **不是「每輪把全部重編」**：用 API 當下資料重算「3.7 劇情討論串」94 則的 hash，只有 1 則跟 StateDB 不同；一天被限速 16 次的那格，每次都對得上新留言或熱門留言 B1 的 GP 在漲。10/01 的 1,613 次編輯：本文（推噓數為主）872、留言格 741（其中 178 次只是留言 GP／熱門變動）、續文 18。
- 被限速的 1,317 次（9/29～10/02）：留言格 755、本文 540、溢出格 15、續文 0；訊息全都發出超過 1.7 小時，剛發的訊息編輯從沒被擋。3 篇並行時各串各自被限速（交錯出現），所以是「每個討論串」的限制。
- discord.py 會自己等完重試，沒有因限速漏掉的編輯（兩天內真正失敗的 9 次是 Discord 503 與討論串已封存）。429 算進 Discord 無效請求上限（10 分鐘 1 萬次），我們最多約 100 次，離很遠。實際影響：log 雜訊＋每輪多等幾分鐘。
- 越來越多：3.7 版本 9/30 開始，熱門串留言與 GP 暴增。
- **坑（比對 Discord 實際內容時）**：以 bot 身分用 REST 讀訊息要照 `X-RateLimit-Remaining`／`X-RateLimit-Reset-After` 等、429 等完重試、5xx 重試；前兩次沒照做（每秒 4 則）被限速，讀到空內容誤判成「32/94 本文、100/276 留言格不一致」，數字作廢。比對還要挑兩輪更新之間（bot 約每小時 :12 開始，3.7 劇情串約 3 分鐘處理完），否則會把時間差當成錯誤。

**順帶查到並確認的顯示錯誤**
- **續文導航連結被洗掉**：本文 hash 一變就把該篇所有續文無條件重編，重編內容不帶「⬇️ 更多內文」。以 bot 身分唯讀抓 Discord：有 2 則以上續文的 12 篇中 **9 篇連結已消失**。
- **續文切到滿時連結塞不下**：預留 100 字，連結實際 104 字（ID 19 位數）；sn=111119 從建立起就沒有連結。
- **新建留言格／更新時新增的回覆／更新時新開的溢出格沒存 hash**：下一輪走「首次寫入 hash 只存不編」，這期間的新留言或推數變動不會顯示，要等之後再有變動才一起出現；之後都沒變動就永遠不出現。log 證實：sn=144598 20:20 有 13 則新留言但留言格沒更新，21:32 再來一則才一起出現；sn=144713 01:16 的 2 則新留言 03:15 才出現。
- **hash 只涵蓋第一則 embed**：內文後段改了，續文永遠不會更新。

**定案（使用者 2026-10-02：BH-Q1～Q4 全照建議）**
- BH-Q1：同一個討論串的**所有**編輯間隔 6 秒（不分新舊訊息，不把 Discord 沒公開的「1 小時」寫死）。
- BH-Q2：推噓數照舊有變就同步（排隊後不會再撞限速，不為此讓推噓數落後）。
- BH-Q3：續文一起修——沒變不編，有變時保留導航連結。
- BH-Q4：測試從公開入口 `send_bahamut_thread_to_forum` 測（暫存檔上的真 StateDB＋假 Discord thread／訊息＋縮短間隔）。

**改了什麼（2026-10-02 10:48 套用、10:53 重啟上線；commit `b11df27`）**
- `_edit_with_cooldown`：以討論串（`msg.channel.id`）排隊、間隔 `THREAD_EDIT_INTERVAL = 6.0`；先登記下一個可用時間再等，同串並行也會錯開。取代 `MIN_EDIT_INTERVAL`／`_last_edit_ts`。複查後補兩點：編完再從「真正編完」重設一次間隔（discord.py 吃到 429 會自己等完重試，那段不能算進去）；被拒絕的編輯（例如討論串已封存 50083）退回登記、不佔名額（不然封存串每則失敗都白等 6 秒，9/26～27 曾一天約 300 次）。
- `_update_continuations` 改寫：不夠的追加、多出的改佔位，再逐則比對「應有內容（含導航連結）」跟 Discord 上的訊息（忽略頭尾空白——Discord 會修掉；巴哈內文 0 篇含 `\r`、0 篇有頭尾空白），一樣就不編。**每輪都比對**（以前只在本文 hash 變時）：後段內文改了、導航連結掉了都會補。成本：每則續文每輪多一次讀取，只發生在有續文的貼文（全部 40,651 篇中 91 篇）。
- 續文上限：新增 `CONTINUATION_NAV_RESERVE = 110`（ID 最長 20 位數時連結 107 字），`CONTINUATION_CONTENT_LIMIT` 3996→3986；留言格的 `LAST_SLOT_NAV_RESERVE` 不動（改了會讓所有第三格重新分配、大量重編）。本文第一則的切法不受影響，所以本文 hash 不會因此全部變動。
- `_send_continuations`：導航連結用切好的文字＋共用的 `_continuation_nav()` 組，不再回頭讀訊息、不再因長度略過。
- hash 記帳：建立留言格、溢出格、更新時新增的回覆、溢出格補導航後的前一格，都在當下記 hash。
- log 文字：「已更新主文／回覆 embed + 續文」改成「已更新主文／回覆 embed」，續文另記「已更新續文 msg=…」。
- **行為變更（BH-Q6，尚待使用者確認）**：續文從 0 則變成 1 則時，舊程式會去編本文訊息加導航，而且用只有描述的 embed 蓋掉，本文的標題與圖片會不見（本文 hash 也不含導航，推數一變又會消失）；新程式不編本文，新續文以 reply 指向本文。

**測試**：`test/test_bahamut_edit_pacing.py` 18 項（同串排隊、間隔從編完起算、被拒不佔名額、跨串不互等、只編有變的／有變的一定編、更新時新增的回覆、溢出格（更新時開的、建串時就有的）、續文推數變不編／後段改了只編那一則／主文續文／導航補回／切到滿也塞得下／變多／變少再變多）；容器 /tmp 完整測試 738 項全過；巴哈測試連跑 5 次都綠；18 種突變全紅。斷言「不超過多久」的兩項用 0.5 秒間隔（餘裕約 0.45 秒），避免啟動 gate 在機器忙時誤紅。

**獨立複查（2026-10-02，子 agent，唯讀）**：沒有必須修的問題。模擬 Discord 修頭尾空白跑 8 種續文情境（1→3、3→1、3→1→4、0→2、2→0、追加途中失敗、結尾換行），同資料再跑一輪都是 0 次編輯。每輪多讀的續文：目前活躍 50 串只有 7 篇、9 則。上限改 3986 只讓 5 篇切點移動（則數不變、都不在活躍串，之後活躍時合計 ≤16 次編輯）；活躍串裡導航補回約 2 次編輯。單串單輪最多 117 次編輯（5698，10/01 16:12）→ 新版約 12 分鐘。複查指出的測試缺口（續文增減、溢出格 hash）與兩個排程低風險點都已補上。另記：開新溢出格那一輪，前一格會先不帶導航編一次、再帶導航編一次（既有，現在多 6 秒，之後再優化）；手動指令單篇模式會等整串處理完，極熱門串可能超過互動回覆 15 分鐘時效（既有）。

**套用後會發生的一次性變化**
- 3 天內還在 API 範圍的討論串，有續文的貼文會在下一輪被比對：導航連結被洗掉的會補回；切點因上限改成 3986 而移動的會重編一次（少數可能追加一則續文，排在討論串最後）。
- 舊的「首次寫入只存不編」留下的錯誤顯示不會自動修好（hash 已記成新內容）→ BH-Q5。

**舊的錯誤顯示有多少（09:16～09:23 兩輪更新之間的乾淨比對，遵守額度）**
- 「3.7 劇情討論串」本文 96 則中 2 則、留言格 282 格中 5 格跟目前資料不符，7 則全對得上「新回覆建立後第一輪就有變化 → 只記 hash 不編」：sn=144278 推數從 9/30 起沒顯示；sn=144744／144745 02:15 來的留言到現在仍顯示「預留留言區（等待更新中...）」。
- 用 log 圈全部討論串：三天內新增回覆 1,053 則，其中 244 則建立後才第一次有留言進來；209 則後來又有變動、被順帶修好；**35 則的留言格到現在仍是舊的**。圈不到的：整串新建時的回覆（建立 log 沒有 sn）、第一輪只有推數變動的本文（不寫 log）。
- 全面讀一遍不划算：最近 50 串（含長年大串）共 66,908 則訊息；只讀三天內新增的回覆＋新建串也要 2,000～4,000 則，照額度約每秒 1 則。

**待決**
- **BH-Q5 舊的錯誤顯示要不要另外修**：A 不修（新的不會再發生；舊的等之後有變動自然修好，沒再變動的就一直是舊的）／B 套用後跑一次性修復，只處理 log 圈出的 35 則回覆的留言格（讀約 40 則、只編不一致的，幾分鐘；以 bot 身分照額度、同串 6 秒排隊；hash 已是新內容，不寫資料庫）／C 一次性讀三天內新增回覆與新建串的本文＋留言格全部比對（30～60 分鐘以上，涵蓋推數漏顯示）。建議 B：修的是最明顯的症狀（留言沒出現、還寫「等待更新中」），成本小；推數差一兩個的安靜回覆影響小，也會隨時間離開轉發範圍。B、C 都會編 Discord 上的訊息，要使用者同意。
- ~~BH-Q6~~ **已定案 B**（第 3 輪）：**本文要不要有往下的連結**（使用者追問「原文刪除或大幅修改時怎麼辦」，第 2 版）：見下方「刪除與大幅修改的現況」。選項：A 維持（本文不加連結，新續文以 reply 指回本文；讀者從本文找不到串尾追加的後半段）／B 本文與回覆被切斷時，底部一律加「⬇️ 更多內文」連到第一則續文，hash 用含連結的版本算（穩定，不會每輪重編）；代價：建立長文時多一次編輯、套用後活躍串裡有續文的約 7 篇本文重編一次。建議 B：每個被切斷的區塊都有往下的連結，修改變長（有史以來 8 篇）或變短再變長時都讀得到全文。
- ~~BH-Q9~~ **已定案 A**（第 3 輪，不改程式）：**刪文／被擋下的大幅刪減，Discord 上要不要標示**：A 維持現狀，保留原文、不標示／B 保留原文並標示「原文已刪除」「作者已大幅刪減，此處保留原版」／C 跟著刪。B、C 都要先改 scraper：刪文偵測沒做（`is_deleted` 從沒被設成 true，0 篇），API 也沒回傳 `update_blocked`／`is_deleted`。建議 A：目前 0 篇偵測到刪除、被擋下的有史以來 1 篇，照先前決定等遇到實際刪文案例再做偵測（見記憶「Bahamut 刪文偵測待辦」）。

**刪除與大幅修改的現況（2026-10-02 查證，唯讀）**
- 刪除：scraper 沒有偵測（`is_deleted` 欄位存在但沒有程式設定它，0 篇）；API 只回傳未刪除的，但因為從沒標記，等於刪掉的文章照樣回傳資料庫裡的版本 → Discord 一直保留原樣（等於存檔）。整串在巴哈被刪，scraper 不再抓到、過幾天離開轉發範圍，Discord 上留著。
- 大幅刪減：原文 ≥500 字、新版縮到一半以下 → scraper 擋下、保留舊版（`update_blocked`，有史以來 1 篇）→ Discord 保留舊版、不標示。新內文是空字串時這道檢查不生效（`new_len > 0`），會直接覆蓋；19 篇被改成空白的都是原本就 0～74 字的短回覆（像只貼圖），不是刪文。
- 一般修改：2,433 篇有修改紀錄，近 30 天 200 篇（±10% 108、變長 76、縮 10～50% 13、縮一半以下 2）。Discord 跟著更新：本文首段＋續文逐則更新，多出的續文改「（此段已更新移除）」，不夠的追加在串尾（reply 前一則）。

**定案（使用者 2026-10-02 第 3 輪）**：BH-Q6 選 B、BH-Q9 選 A。使用者擔心「連結算進 hash 會不會每輪都判定不同」→ 說明：hash 比的是我們上次寫的與這次該寫的，連結目標是存在 state 的第一則續文 id、建立後不變，所以只在內文／推數變動、第一則續文出現或全部清空時才不同；已用測試守住（同資料兩輪 0 次編輯）。
- BH-Q6 實作：`_add_continuation_link()`（有續文切塊且有續文 id 時，本文描述尾端加 `_continuation_nav(第一則續文)`）；增量更新改成**先** `_update_continuations` 再算本文描述與 hash；建立時 `_link_post_to_continuations()` 在續文發出後回頭補連結，回傳 Discord 上實際的描述記 hash（補失敗記沒連結的版本，下一輪補）。主文、回覆、更新時新增的回覆三處都接上。舊的 hash 為空（從沒被更新過的舊資料）仍走「只記不編」，那些本文不會補連結（少數，接受）。
- 測試：再加 5 項（同資料兩輪 0 次編輯並指向第一則續文、變長追加在串尾也連得到／改回短的拿掉連結且穩定、建立時補連結失敗下一輪補、套用前的長文只補一次）＋既有續文增減測試改成「從本文開始順著連結讀」；共 24 項，完整 744 項全過、連跑 5 次都綠、26 種突變全紅。
- BH-Q5 修復腳本：`scratchpad/repair_stuck_slots.py`（session 暫存，內容見本段描述）；10:48 試跑（只讀）：log 圈出 31 則回覆，31 格全部不一致（其中 20 格仍顯示「等待更新中」），62 格已一致不動。**11:00～11:02 執行完成**：已修 31 格、期間 bot 0 次 429；11:03 只讀重跑：0 格不一致、93 格全對。

**定案（使用者 2026-10-02 第 2 輪）**：BH-Q5 選 B、BH-Q7 選 B、BH-Q8 選 A。
- BH-Q7 實作：增量更新開頭若討論串已封存，且沒有新回覆 → 整輪跳過（不編、不存 state，hash 留舊值，變動累積）；有新回覆 → 先 `thread.edit(archived=False)`（發文本來就會解除封存；未上鎖時只需要發言權限），再照常處理，累積的變動一起補上。
- BH-Q8 實作：`new_reply_idx = len(existing_sns)`（主文是 #1，已含在內）。既有的錯編號要等該則推數變動、本文重編時才會改正（hash 不含標題）。
- 測試：新增封存串、編號各 1 項，共 20 項；完整 740 項全過；21 種突變全紅。
- BH-Q5 一次性修復：套用＋重啟後、新程式跑完第一輪再執行（重算當下 log 圈出的清單）。

**上線驗證（2026-10-02 11:16 那輪，新程式第一輪）**
- 429：舊程式 10:16 那輪 104 次 → 新程式 **0 次**；整輪沒有 WARNING／ERROR。
- 排隊：3.7 劇情串這輪編 31 次，相鄰間隔全是 6～7 秒（最短 6），11:16:28 開始、11:20:18 完成。
- 編輯種類：回覆本文 44、留言格 29、主文 14、新增回覆 6、溢出格 3、續文 2。
- 連結：活躍串裡有續文的 7 篇全部「本文有連結→第一則續文、續文導航完整」（含早上確認被洗掉的 9099/107821、14859/109620）。
- 50 串中 49 串完成；沒完成的 19071 是「無音區」分類，在 `bahamut_exclude_categories` 裡，本來就不轉發。

**下一步**：~~commit~~（`b11df27`）。之後觀察：每天 429 是否維持 0、熱門串單輪耗時（最多約 117 次編輯 ≈ 12 分鐘）是否影響到下一輪。

</details>

## Bahamut 專區整段歸檔（歸檔 2026-04-27）

> 端到端流程已在跑；記下兩個未解風險，以及端到端測試、Alembic、RAG 第三階段等未排入主線的工作。
>
> 關鍵字：scraper 全流程 100%、反爬基礎設施、第三階段 RAG ingestion 未做

<details>
<summary>展開原文（約 1,414 字）</summary>

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

</details>

## Bahamut 續文/多圖/並行/子看板等完成歸檔（2026-04-05）

> 長文續文、多圖每批 10 張、並行上限 3、子看板、分類黑名單、thread 被刪自動重建等完成項目。
>
> 關鍵字：續文、多圖分批、semaphore、subbsn、category 黑名單

<details>
<summary>展開原文（約 759 字）</summary>

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

</details>

## Bahamut 正式知識層清理歸檔（2026-04-03）

> 從交接檔移出的已完成能力清單與已定案設計：ID 語意、文章結構、留言抓取、資料表與 Discord 呈現方式。
>
> 關鍵字：設計文件歸檔、ID 語意、DB schema

<details>
<summary>展開原文（約 3,252 字）</summary>

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

</details>

## Bahamut 增量更新 + SQLite 遷移 + Webhook 通知完成歸檔（2026-04-02）

> 既有討論串改走增量更新（hash 有變才編），state 搬到 SQLite，爬蟲抓完用 webhook 通知 bot。
>
> 關鍵字：增量更新、SQLite、state_db、webhook、notify

<details>
<summary>展開原文（約 1,409 字）</summary>

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

</details>

## Bahamut Scraper MVP 完成歸檔（2026-04-01）

> 第一階段抓取全部完成、資料表大部分完成，首版轉發做出主文、回覆、留言格與溢出導航，並定下 ID 模型。
>
> 關鍵字：scraper、文章抓取、留言、DB schema、Discord relay

<details>
<summary>展開原文（約 1,302 字）</summary>

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

</details>
