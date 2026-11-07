# IT 新聞與 X 連結

<!-- 給 AI：這份是歸檔檔，改之前先看完這段
結構：上半部（一頁看懂、時間線、定案與理由、踩過的坑）是整理過的重點；「## 原文」以下是當時的紀錄。
新增一段：
1. 原文放在「## 原文」目錄表下方的最前面，照現有各段的格式（## 標題、> 摘要與關鍵字、<details> 包正文，標籤前後各空一行）。
2. 目錄表加一列；dev/README.md 的「依日期」加一列。
3. 同一輪更新上半部，並把下面的「整理到」改成新段的日期。
不要改：原文正文、既有的段落標題（README 和其他檔用標題當錨點）。
找細節用搜尋，不必整份讀。改完跑 python3 dev/check.py。完整規則：AI_HANDOFF_AND_TODO.md「本檔維護規則」的「歸檔放哪」。
整理到：2026-10-01
-->

> 交接檔已經沒有這個主題的區塊；現況以 [交接檔](../../AI_HANDOFF_AND_TODO.md) 與程式為準。
> 這裡是歷史。上半部是整理過的重點；「原文」是當時的紀錄，提到的檔名、函式、狀態可能已經改了。原文提到的 `TODO-completed.md` 是 2026-11-07 以前的單一歸檔檔，內容都拆到 `dev/` 了，從 [dev/README.md](../README.md) 找。

## 一頁看懂

這個主題管兩件轉發的事：IT 新聞（HKEPC）發出去的內文，以及群友貼的 X 影片連結怎麼換成 Discord 能預覽的網址。

- **04-22 研究**：Discord 靠網址的 `<meta>` 標籤決定預覽，x.com 不給 `og:video` 所以播不了；fxtwitter、fixupx 這類代理網域重組一份帶影片的 HTML 就能播。代理只吃已知的貼文網址，不能搜尋、不能監控帳號。
- **06-13 首版**：所有 x.com、twitter.com 貼文連結都轉 fixupx，並砍掉原訊息的預覽。
- **06-15**：改成只轉影片。查 X 的 syndication CDN 判斷貼文類型與存不存在；確定有影片、或查詢服務掛掉問不到才轉，確定是圖片或不存在就不轉。
- **09-30～10-01**：IT 快訊的內文跟全文不符、被截斷。HKEPC 內頁被擋（403）時資料庫只有列表摘要，bot 發完就標記已發，之後補到內文也不更新；9/22 起約三分之一的 IT 新聞只帶摘要發出。改成內文到了就把那則 embed 就地更新（`6f39e87`）。

**歸檔時（10-01）的狀態**

- [x] X 影片連結轉 fixupx，圖片貼文保留原生預覽（06-15）
- [x] IT 新聞內文補到後就地更新那則 embed（10-01，`6f39e87`）
- [ ] fixupx 的 6 項部署後驗證（原文沒記結果）
- [ ] 等下一次 HKEPC 通知，實際補上摘要訊息
- [ ] 爬蟲端減少 403，改跟「scraper 抓網頁機制」一起處理（SC-Q1～Q3）

最新狀況看交接檔。

## 時間線

| 日期 | 發生什麼 | 結果 |
|---|---|---|
| 04-22 | 研究別的 bot 怎麼把 x.com 影片轉成可播放的預覽 | 純研究，沒改程式 |
| 06-13 | X 連結首版 | 全部轉 fixupx、砍原訊息預覽 |
| 06-15 | 改成只轉影片，加存在性防呆 | `link_fix.select_video_links`；容器內整合測試通過，待部署驗證 |
| 09-30 | 使用者回報 IT 快訊內文被截斷 | 查出內頁 403 時只帶摘要發出；9/22 起 73 篇中 23 篇如此 |
| 10-01 | IT-Q1 選 B：先發摘要，內文到了就地更新 | 03:46 重啟上線、commit `6f39e87`；測試 12 項、9 種突變都紅 |

## 定案與理由

| 決定 | 為什麼 |
|---|---|
| X 連結只轉影片，圖片貼文不轉 | 圖片貼文的 fixupx 預覽跟 Discord 原生預覽沒差，轉了多此一舉，還會把原生預覽卡一起砍掉 |
| 只比對含 `/status/<id>` 的貼文連結 | 避免轉到個人首頁、搜尋這類沒意義的連結 |
| 查類型走 X 的 syndication CDN，不用 `api.fxtwitter.com`；顯示用 fixupx | 原生 CDN 除非 x.com 本身倒了才會消失，第三方代理會掛；fixupx 沒有 JSON API |
| token 照公式算正確值 | 實測只要非空就放行，照算是防之後收緊 |
| 查詢逾時、5xx、空回應時照轉（fail-open） | 查詢服務掛掉不能讓功能停擺；服務明確回答了（圖片或不存在）就尊重它 |
| 混合影片與圖片連結的訊息會連圖片預覽一起砍（接受） | 罕見 |
| IT 新聞先發摘要，內文到了就地更新那則 embed（IT-Q1 選 B） | 原文沒記使用者的理由（當時建議的 A「內文到了才發」會讓約三分之一 IT 新聞晚 1～3 小時發） |
| 不另存訊息 id，每次 HKEPC 通知時讀 IT 頻道最近 3 天的訊息，用原文網址對回文章 | 不必在高風險資料檔 `sent_articles.db` 加表；已經發出去的舊訊息也會一起補上 |
| 排版對不上的訊息不動 | 寧可漏補，不誤改 |
| 當天那 2 篇用同一個機制補（IT-Q2） | 免刪除重發 |

## 踩過的坑

- **x.com 對我們的 server 只回 JS 空殼**：用 `Discordbot` UA 也只抓回 5KB script、沒有 og 標籤；Discord 抓得到是 x.com 給它的白名單待遇，我們複製不出來。光看網址也分不出影片或圖片，只能查貼文 metadata。
- **syndication 限流時回 `{}`，會被誤判成貼文不存在**：結果不轉（罕見）。
- **`suppress=True` 是整則訊息一起砍預覽**。
- **壓別人的預覽要 Manage Messages 權限**：缺權限只記 warning，fixupx 新訊息照常發出。
- **IT 新聞發完就標記已發送**：之後爬蟲補到內文也不會更新。HKEPC 內頁 403 從 7/14 就有、共 155 篇；等 3 輪涵蓋 95%，等 4 輪涵蓋 99%。
- **免費查推文的路隨時可能被關**：舊的 `guest_token` 2023 年中被封，Nitter、snscrape 因此停擺；syndication 沒有 SLA、沒有文件。

## 原文

新的在前。每段標題下面是摘要，正文在「展開原文」裡。

| 日期 | 段落 | 摘要 |
|---|---|---|
| 2026-10-01 | [IT 新聞只帶摘要發出](#it-新聞只帶摘要發出歸檔-2026-10-02原-2026-10-01) | HKEPC 內頁 403 時只帶摘要發出且之後不更新；改成內文到了就地更新那則 embed，已上線。 |
| 2026-06-15 | [fixupx 只轉影片與防呆](#fixupx-連結轉發只轉影片--存在性防呆歸檔-2026-06-15) | X 連結從全部轉改成只轉影片；查 syndication CDN 判斷類型與存在，問不到時照轉。 |
| 2026-04-22 | [X 影片嵌入的原理研究](#xcom--twitter-影片嵌入研究歸檔-2026-04-22) | 代理網域為什麼能讓 Discord 播 X 影片、syndication API 的原理與限制，純研究沒改程式。 |

## IT 新聞只帶摘要發出（歸檔 2026-10-02，原 2026-10-01）

> HKEPC 內頁 403 時只帶摘要發出且之後不更新；改成內文到了就地更新那則 embed，已上線。
>
> 關鍵字：HKEPC 403、只帶摘要、就地 edit、IT-Q1 B、6f39e87、test_it_article_refresh

<details>
<summary>展開原文（約 1,808 字）</summary>

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

</details>

## fixupx 連結轉發：只轉影片 + 存在性防呆（歸檔 2026-06-15）

> X 連結從全部轉改成只轉影片；查 syndication CDN 判斷類型與存在，問不到時照轉。
>
> 關鍵字：link_fix、select_video_links、cdn.syndication、get_token、react-tweet、fail-open、影片才轉

<details>
<summary>展開原文（約 2,703 字）</summary>

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

**參考：** [vercel/react-tweet getToken](https://github.com/vercel/react-tweet/blob/main/packages/react-tweet/src/api/fetch-tweet.ts)；早期研究見本檔 [X.com / Twitter 影片嵌入研究（歸檔 2026-04-22）](#xcom--twitter-影片嵌入研究歸檔-2026-04-22)。

</details>

## X.com / Twitter 影片嵌入研究（歸檔 2026-04-22）

> 代理網域為什麼能讓 Discord 播 X 影片、syndication API 的原理與限制，純研究沒改程式。
>
> 關鍵字：fxtwitter、syndication API、og:video、Discord unfurler、domain replace

<details>
<summary>展開原文（約 1,566 字）</summary>

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

</details>
