# LLM 後端、client 與推論

<!-- 給 AI：這份是歸檔檔，改之前先看完這段
結構：上半部（一頁看懂、時間線、定案與理由、踩過的坑）是整理過的重點；「## 原文」以下是當時的紀錄。
新增一段：
1. 原文放在「## 原文」目錄表下方的最前面，照現有各段的格式（## 標題、> 摘要與關鍵字、<details> 包正文，標籤前後各空一行）。
2. 目錄表加一列；dev/README.md 的「依日期」加一列。
3. 同一輪更新上半部，並把下面的「整理到」改成新段的日期。
不要改：原文正文、既有的段落標題（README 和其他檔用標題當錨點）。
找細節用搜尋，不必整份讀。改完跑 python3 dev/check.py。完整規則：AI_HANDOFF_AND_TODO.md「本檔維護規則」的「歸檔放哪」。
整理到：2026-11-04
-->

> 現況、待決與待做以交接檔為準：[LLM 推論：KV cache、prompt 快取與 GPU](../../AI_HANDOFF_AND_TODO.md#llm-推論kv-cacheprompt-快取與-gpu)、[Lemonade 後端與寫入緩衝的待決](../../AI_HANDOFF_AND_TODO.md#lemonade-後端與寫入緩衝的待決)。
> 這裡是歷史。上半部是整理過的重點；「原文」是當時的紀錄，提到的檔名、函式、狀態可能已經改了。原文提到的 `TODO-completed.md` 是 2026-11-07 以前的單一歸檔檔，內容都拆到 `dev/` 了，從 [dev/README.md](../README.md) 找。

## 一頁看懂

這個主題管 bot 怎麼呼叫 LLM 後端（從 Ollama、自寫的 HTTP client 到 Lemonade）、後端出錯時怎麼判斷與重試，以及推論速度與 prompt 快取。

- **04-19 Ollama 時期**：底層呼叫統一成 `chat_raw`，`keep_alive` 依用途傳，500/502/503/504 與逾時自動重試 2 次，embedding 的 `num_ctx` 調成 8192，省約 2.6 GB VRAM。
- **04-28**：拿掉 openai SDK，自寫 httpx 薄殼 `llm_http_client.py`。起因是換了 embedding 套件後，自訂模型名被白名單擋下，embedding 一直退回 BM25 沒人發現。準則是綁協定不綁 SDK。
- **05-11～05-18**：Lemonade 失敗時回 `200 OK` 加錯誤信封，bot 誤判成 `no_choices`。加一把鎖讓聊天串流與背景 embedding 互等，收到 `network_error` 信封改當連線錯誤重試；之後再加通用的信封拆解與缺 key 檢查。
- **10-08～10-11 關鍵轉折**：每個請求記一行 `llm_usage` 量快取。查出 /askai 的決策輪讓第 2 輪快取接不上：模板在思考開時會在 system 最前面塞一句英文，思考開關兩份 prompt 從第 3 個 token 就不同。拿掉決策輪後第 2 輪快取接上。
- **11-04**：量了 5,254 次呼叫。插話快取沒命中只有 3.4%；user 段重排沒用，不做；定出「system 只放不變的、動態內容放 user 段」等規則。

**歸檔時（11-04）的狀態**

- [x] 自寫 httpx client，Lemonade 的錯誤信封改判成連線錯誤並重試（04-28～05-18）
- [x] 每個 LLM 請求記一行 `llm_usage`（10-08）
- [x] 拿掉 /askai 決策輪，第 2 輪快取接上（10-11）
- [x] 量出插話的快取命中情形，定出 system／user 段的規則（11-04）
- [ ] `--parallel` 六組實驗（`-ub` 一起量）
- [ ] 顯示卡斷線 `ErrorDeviceLost` 的原因
- [ ] 三份寫入緩衝要不要抽成共用元件（LM-Q4）
- [ ] 自動偵測 Lemonade 重啟並清載入快取（LM-Q2，10-29 只有手動版）

最新狀況看交接檔。

## 時間線

| 日期 | 發生什麼 | 結果 |
|---|---|---|
| 04-19 | Ollama 服務穩定化 | `chat_raw` 統一、`keep_alive` 依用途、自動重試 2 次、embedding `num_ctx=8192` |
| 04-28 | 拿掉 openai SDK，改自寫 httpx 薄殼 | `8642806`（程式）、`02a937c`（套件清理）；設定檔加後端 profile |
| 05-11 | 3 筆 `no_choices` 事故，查出是 Lemonade 回 200 加錯誤信封 | 加 `lemonade_gate.stream_exclusive()`；`network_error` 改當連線錯誤重試 |
| 05-18 | `/askai` 每次跳兩個只寫 `'data'` 的警告 | 加 `_unwrap_response_envelope`、`_require_json_key`，錯誤會顯示後端實際回了什麼 |
| 10-01 | Lemonade 升級盤點出缺口 | LM-Q1（聊天向量斷線會掉）已修 `95a0330`；LM-Q3 維持現狀；LM-Q2、LM-Q4 待決 |
| 10-08 | 查 KV cache 與 prompt 快取；顯示卡 `ErrorDeviceLost` | `llm_usage` 上線；主模型 10:39～10:56 每個請求都失敗，11:01 重新載入後恢復；批次向量化改走 GPU 閘門 |
| 10-09 | /askai 線上 6 題，第 2 輪快取沒接上 | 第 2 輪多重讀約 3,300～10,500 token（約 15～48 秒） |
| 10-11 | 讀模板查出原因，拿掉決策輪 | 重啟後第 2 輪快取接上；線上第一題 117 秒，最花時間的變成寫回答 |
| 10-29 | 「重新偵測」按鈕呼叫 `reset_cache()`，一起清載入快取 | 等於 LM-Q2 選項 A 的手動版 |
| 11-04 | 量 10-20～11-04 的 5,254 次呼叫 | 插話沒命中 3.4%；user 段重排不做；定出 system／user 段的規則 |

## 定案與理由

| 決定 | 為什麼 |
|---|---|
| `keep_alive` 依用途傳：/askai `1h`、moderation 與人格萃取 `30m`；沒傳就沿用 server 全域設定 | /askai 連續互動期間讓模型常駐；moderation 是間歇性任務；人格萃取 4am 跑完 30 分鐘後釋放 |
| 重試 500/502/503/504、逾時與連線錯誤，不重試 4xx 與回應格式異常 | 17:14 出現 `500 model runner has unexpectedly stopped`，VRAM 還剩 20GB，判定是 runner 暫時性崩潰 |
| embedding 預設 `num_ctx=8192` | 預設 32768 讓 embedding 吃 5.7GB VRAM；改後 KV cache 約 880MB；最大輸入約 4,200 字元，只用掉 51% |
| 綁協定不綁 SDK，自寫 httpx 薄殼 | openai 套件的 embedding 對模型名做白名單驗證，自訂模型名直接丟 `ValueError` |
| 聊天串流與背景 embedding 寫入用同一把鎖互等 | 三次失敗都是 /askai 串流進行中、1～4 秒前背景 flush 送了批次 embedding，連線被 Lemonade reset |
| 先顧「回應快」（常用的長 prompt 不被洗掉）、KV 維持 F16、要測 131k 的極限（R7、R8） | 原文沒記理由，只記順序：先量現況 → 調 prompt 順序 → 固定槽放進實驗量 → RAM 快取上限等 RAM 調查後再定 |
| 拿掉 /askai 決策輪，每輪照呼叫端的思考設定 | 決策輪頂多省幾秒的思考輸出，卻換來每題 15～48 秒的快取重讀；決策輪假設切換思考不會改到 prompt 開頭，這個模型不符合 |
| 不做 user 段重排 | 共同前綴平均只從 26 字變 244 字（約 0.5 秒），人物卡和上一筆完全相同的只有 20/476 |
| 動態內容（日期、心情、人物卡、撈回的舊話、輪換的範例）放 user 段，system 只放不變的 | system 任何一處變了，該模式下一次要重讀那處之後的全部（最多約 35 秒） |
| 自發、被 @、接續共用同一份 system | 拆成兩份就有兩個前綴，少用的那份容易被擠掉 |

## 踩過的坑

- **Lemonade 失敗時回 `200 OK` 加錯誤信封**：破壞 HTTP 語意，bot 走 `no_choices` 分支而且不重試。要檢查 `error.type == "network_error"`，改丟連線錯誤。
- **錯誤訊息只剩 `'data'`**：直接 `data["data"]` 取值，後端回錯誤信封或別的格式時丟 `KeyError: 'data'`，看不出後端回了什麼。
- **embedding 默默退回 BM25**：commit `763d251` 順手換了 embedding 套件，新套件拒絕自訂模型名，`SafeLLMEmbedding` 一直 fallback，沒人注意到。
- **例外訊息是空字串**：log 只印「Ollama 呼叫發生未預期錯誤: 」，要加 `type(exc).__name__` 才看得出是 `TimeoutError`。
- **切換思考開關會改到 prompt 開頭**：模板在思考開、`reasoning_effort` 為預設 xhigh 時，在 system 開頭塞一句英文；思考關沒有這句，兩份從第 3 個 token 起就不同，快取接不上。
- **不同模式之間共用不到快取**：模板把思考那句與工具宣告放在我們的 system 之前，插話、/askai、日記的工具不同，前綴一開始就分開（日記 16/16 整段重讀），「共用的人格放最前面」省不到。
- **embedding 與 reranker 的整段輸入要放進同一個物理批次**：預設 512 token，超過整次請求失敗；產生文字時長 prompt 可以分批讀，不受限。
- **顯示卡斷線 `ErrorDeviceLost`**：10-08 主模型約 17 分鐘每個請求都失敗，bot 6 次插話失敗、群友看不到。原因未定（Windows GPU 逾時重置、兩個 llama-server 同時用同一張卡、驅動）。
- **載入快取不會因 Lemonade 重啟失效**：Lemonade 重灌洗掉 `recipe_options.json` 時，bot 不會重推 ctx_size，會用預設 4096 跑、長 prompt 爆 context。
- **`raw_message_store` 在 pgvector 斷線時整批丟掉**：三份寫入緩衝骨架相同，只有它沒放回重試（LM-Q4）。
- **Lemonade log 看不到是誰送的**：從主 port 的 `/logs/stream` 訂閱可以拿最近 5,000 行，但 llama-server 啟動配置行被過濾、也看不到請求內容，要對 bot 這邊 `llm_usage` 的功能名稱與編號。

## 原文

新的在前。每段標題下面是摘要，正文在「展開原文」裡。

| 日期 | 段落 | 摘要 |
|---|---|---|
| 2026-11-04 | [KV cache 與 prompt 快取](#llm-推論kv-cache-查證askai-決策輪拿掉prompt-快取量測歸檔-2026-11-07原至-2026-10-11) | 硬體與快取現況、顯示卡斷線事件；查出決策輪讓快取接不上而拿掉；11-04 量測定出 system／user 段規則。 |
| 2026-10-02 | [載入快取與寫入緩衝的缺口](#lemonade-升級盤點的缺口載入快取與寫入緩衝歸檔-2026-11-07原至-2026-10-02) | LM-Q2 載入快取不會因 Lemonade 重啟失效（10-29 有手動清除）；LM-Q4 寫入緩衝要不要收成一份。 |
| 2026-05-18 | [HTTP client 錯誤護網](#llm-http-client-通用錯誤護網歸檔-2026-06-20原-2026-05-18) | embedding 缺 key 只報 'data'，加信封拆解與缺 key 檢查，之後錯誤會顯示後端實際回了什麼。 |
| 2026-05-11 | [串流與 embedding 併發失敗](#lemonade-對-chat-stream--背景-embedding-併發失敗no_choices-假象歸檔-2026-06-20原-2026-05-11) | Lemonade 回 200 加錯誤信封造成假 no_choices；加鎖讓串流與 embedding 互等。 |
| 2026-04-28 | [改自寫 httpx client](#llm-client-重構拋-openai-sdk改自寫-httpx-wire-薄殼歸檔-2026-06-20原-2026-04-28) | 換套件後 embedding 一直退回 BM25，改自寫 httpx 薄殼並加後端 profile，綁協定不綁 SDK。 |
| 2026-04-19 | [Ollama 服務穩定化](#ollama-服務穩定化chat_raw--keep_alive--重試--vram歸檔-2026-04-19) | 統一 chat_raw、keep_alive 依用途、5xx 與逾時重試、embedding num_ctx 8192。 |

## LLM 推論：KV cache 查證、/askai 決策輪拿掉、prompt 快取量測（歸檔 2026-11-07，原至 2026-10-11）

> 硬體與快取現況、顯示卡斷線事件；查出決策輪讓快取接不上而拿掉；11-04 量測定出 system／user 段規則。
>
> 關鍵字：KV cache、prompt 快取、llm_usage、決策輪、reasoning_effort、--parallel、Lemonade、MTP、ErrorDeviceLost

<details>
<summary>展開原文（約 6,345 字）</summary>

> 從 `AI_HANDOFF_AND_TODO.md`「LLM 推論：KV cache、prompt 快取與 GPU（2026-10-08 查證）」區塊（`llm-inference-kv`）瘦身前的完整原文；交接檔只留現況、規則與坑、未定案、待做。

> 討論過程（R7、R8）原文在 `TODO-completed.md`「MCP／搜尋工具化：討論與實作紀錄」。

**現況**
- 硬體：Windows 主機、2 張 AMD Radeon RX 9060 XT（各 16 GB）、Ryzen 7 5800X、128 GB RAM、沒有 NPU。這台 Linux 是跑在同一台上的 VM（7.7 GB）。Lemonade 用 llama.cpp（Vulkan）：主模型 `--device Vulkan0,Vulkan1`、ctx 32,768、`--spec-type draft-mtp`、`--parallel 1`（Lemonade 自動補的預設，可從 `llamacpp_args` 改；不是保留旗標）。
- 主模型是混合注意力：64 層裡 16 層完整注意力、48 層線性注意力。KV cache 每 token 64 KiB（F16）→ 32k 約 2 GiB、131k 約 8 GiB、262k 約 16 GiB；線性注意力層每槽另有固定大小的狀態（估約 150 MB）。
- 速度：讀 prompt 約 330 tok/s，產生 22～35 tok/s（單張卡頻寬約 320 GB/s、權重 17.5 GB，接力跑的理論上限約 18 tok/s，超過的部分靠 MTP 推測解碼）。
- prompt 快取：Lemonade 累計命中約 60%，平均每個請求約 10 秒花在重算。bot 每個 LLM 請求記一行 `llm_usage`（功能、prompt、命中、重算、讀 prompt 毫秒、tok/s、MTP 猜中），插話 prompt 約 1.04～1.14 萬 tokens、前 8,139 每次命中、重算 2,200～3,300。llama.cpp 把被擠掉的快取存到系統 RAM（`--cache-ram` 預設 8 GiB，每份約 0.9～1.1 GB）：工作管理員 7.7 GB 的那個 llama-server 就是它。
- `--parallel N`：權重只有一份；context 會被各槽均分（除非 `--kv-unified` 共用一塊）；檢查點每槽各自存在 RAM。
- 物理批次（`-ub`）：embedding 與 reranker 的「整段輸入」要放進同一個物理批次（預設 512 token），超過整次請求失敗；產生文字時長 prompt 可以分批讀，不受限。
- 顯示卡：使用者截圖一張卡 11.8 GB、另一張 0 GB，說「一直如此、運作正常」；但 17.56 GB 權重放不進一張卡，原因未明，做 `--parallel` 實驗時順便量。系統 RAM 72%（約 92 GB）中，處理程序清單只加得到約 16 GB，其餘未查。
- **顯示卡斷線事件（10-08）**：Lemonade log 出現 `vk::Queue::submit: ErrorDeviceLost`——10:24 一次（embedding 大量寫入與一個長回答同時在跑）、10:39～10:56 主模型每個請求都失敗（bot 6 次插話失敗、群友看不到），11:01 重新載入後恢復。原因未定（Windows GPU 逾時重置、兩個 llama-server 同時用同一張卡、驅動）。之後的批次向量化都走 GPU 閘門。
- 讀 Lemonade log 的方法：主 port 13305 的 `/logs/stream` 接受 websocket，送 `{"type":"logs.subscribe"}` 會先回最近 5,000 行；llama-server 啟動時的配置行被過濾、看不到。看得到進來的是對話／embedding／重排、產生到第幾個 token（`n_gen`，約每 3 秒一行）、做完的統計、被取消（`cancel task`、`aborted due to client disconnect`）；看不到是誰送的與內容，要對 bot 這邊 `llm_usage` 的功能名稱與編號。每個模型現在忙不忙看 `/api/v1/health`（10-12 用它還原了「逾時後自動重試」的時間線）。

**已定案（R7、R8）**：先顧「回應快」（常用的長 prompt 不被洗掉）；KV 維持 F16；要測 131k 的極限；順序＝先量現況（`llm_usage` 已上線）→ 調 prompt 順序（不變的放前面）→ 固定槽放進實驗量 → RAM 快取上限等 RAM 調查後再定；實驗腳本在 VM 經 Lemonade 跑、使用者看工作管理員記 VRAM／RAM。

**待做**
1. 用 `llm_usage` 找出誰洗掉誰，調插話與 `/askai` 的 prompt 順序。**11-04 量過（10-20～11-04，5,254 次呼叫；使用者要 prompt 架構改動一併考慮快取）**：
   - 插話 1,334 次，1,173 次剛好命中 9,516（工具宣告＋整段 system），沒命中 46 次（3.4%）；新算中位 2,673（約等於整個 user 段）、約 10 秒；整段重讀約 12,000 token、約 35 秒。帶圖不影響命中（137 對 1）。
   - 誰洗掉誰：前一筆是 batch（維護時段）的 10 次有 8 次要重讀；前一筆是 tgfilter、autofill、diary、`-` 的幾乎都還命中，RAM 快取留得住，互相洗掉不是問題。
   - 不跨模式共用：模板把思考那句與工具宣告放在我們的 system 之前，插話、/askai、日記的工具不同，前綴一開始就分開（日記 16/16 整段重讀），所以「共用的人格放最前面」省不到跨模式的快取。
   - user 段重排沒有用：連續兩筆第一個不同落在 chat_history 470/476；就算把穩定區塊排前面，共同前綴平均只從 26 字變 244 字（約 0.5 秒），因為人物卡和上一筆完全相同只有 20/476。不要做。
   - system 段各部分（`/api/v1/tokenize` 算的再按實際命中換算，約 0.915，近似值）：身分 174、守則 1,987、插話行為 3,879、範例 1,856、查詢規則 409、安全 301、工具宣告與模板約 910。
   - 架構規則：①動態內容（日期、心情、人物卡、撈回的舊話、會輪換的範例）一律放 user 段，system 只放不變的；②自發、被 @、接續共用同一份 system，不要拆成兩份（兩個前綴，少用的那份容易被擠掉）；只有被 @ 才用的規則若要移出 system，放 user 段，只多那幾次的讀取時間；③改 system 任何一處，該模式下一次要重讀該處之後的全部（最多約 35 秒、只一次），調整時一次改完再存；④切 `ambient_search_mode` 成 `on` 不動宣告，不會讓快取失效。
2. `--parallel` 實驗六組：①現況 1 槽 32k ②4 槽均分 ③4 槽 `--kv-unified` ④1 槽 131k ⑤KV q8_0 ⑥2 槽、兩種長 prompt 輪流送、比較帶不帶 `id_slot` 的第一個字出來前等多久；①～③各測同時 1／2／4 個請求，量第一個字的等待時間、單一與總 tok/s、命中、兩張卡 VRAM、RAM。動正式載入參數前先問使用者，避開維護時段。
3. 主模型的 `-ub` 也影響讀 prompt 的速度，可以放進同一個實驗。
4. **/askai 決策輪→正式輪快取沒接上（10-11 已定案並實作：拿掉決策輪；重啟後待線上驗證）**：`_answer_with_tools` 每輪帶同一份工具清單、只換思考開關（`chat_template_kwargs.enable_thinking`），設計上第 2 輪應接上第 1 輪整段。10-09 線上 6 題的 `llm_usage`：4 題第 1 輪 cached=6,858、第 2 輪 cached=6,894；2 題兩輪都 cached=0；第 2 輪多重讀約 3,300～10,500 token（約 15～48 秒）；第 3 輪起都正常接上。
   - 線索：決策輪沒叫工具的那題（23:39），第 2 輪 messages 與第 1 輪相同，prompt 多 36 token（11,257→11,293）、cached 也正好多 36（6,858→6,894）、重讀一樣是 4,399。
   - **原因（10-11 讀模板查到）**：主模型官方模板（Hugging Face 上的 `chat_template.jinja`，unsloth 版同）在思考開、`reasoning_effort` 為預設 xhigh 時，把一句英文「Reasoning effort is set to xhigh. Please think carefully …」塞在 `<|im_start|>system\n` 後面（工具清單、我們的系統提示詞之前）；思考關沒有這句。結尾另差 `<think>\n` 與 `<think>\n\n</think>\n\n`。用 Lemonade 的 `/api/v1/tokenize` 算：前段 +37、結尾 −2，淨 +35（log 是 36；這個端點不管 `model` 參數都用同一套切詞，差 1 屬正常）。所以思考開關兩份文字從第 3 個 token 起就不同；第 2 輪的 6,894 是接上之前其他「思考開」請求的快取。bot 這端沒問題：同一題兩輪的 messages 一字不差；四題系統訊息互相比對，22:5x 那三題第一個不同的字在 `current_time`（系統訊息 9,980 字的第 9,849 字，接近結尾），23:39 那題因為當晚改了網路搜尋規則，在規則中段就不同。
   - 還沒解：22:5x 三題真正分歧在 `current_time`（照字數估約第七千多個 token），快取卻都停在 6,858，可能是混合架構只能退回檢查點；cached=0 的 2 題也沒查。
   - 驗證法（建議使用者自己跑，面試準備）：同一份 messages、`max_tokens=1`，依序送思考關→思考開→思考開，比三次的 cached；再加一組「思考開＋`chat_template_kwargs.reasoning_effort: medium`」。
   - **決策輪值不值得留（10-11 使用者問「決策輪重要嗎、換別的模型還需要嗎」→ 建議拿掉 → 使用者「你幫我改」）**：10-09 的 6 題全部都有查。決策輪有叫工具的 4 題（輸出 45～91 token）；沒叫的 2 題（22:27 撞 200 上限、23:39）正式輪自己叫了 search，決策輪整輪白跑（約 58 秒、23 秒）。6 題都有「思考開的輪自己叫工具」（search 或 fetch），叫工具前只輸出 56～252 token（約 2～11 秒），所以決策輪頂多省幾秒的思考輸出，卻換來每題 15～48 秒的快取重讀。換模型時：一般的工具迴圈（帶工具清單、模型自己決定叫工具或回答）任何支援工具的模型都能用；決策輪多了兩個跟模型有關的假設（有思考開關、切換開關不會改到 prompt 開頭），這個模型就不符合第二個，沒有思考模式的模型則是整輪重複。沒資料的部分：6 題都是使用者自己問、都是查資料題；拿掉後要用原本的整合測試（含閒聊題）確認模型不會亂查。
   - **採用 (a) 拿掉決策輪（10-11 實作）**：`_answer_with_tools` 每輪 `think` 都照呼叫端的設定、不再限長度；`generate_reply` 的 `decide_max_tokens`、`AskAIIntelSettings.decide_max_tokens`、`chat_with_tools` 的 `max_tokens`（只有決策輪在用）一起拿掉。保留的行為：第一次呼叫就失敗（後端拒絕工具、什麼都沒產出）改用不帶工具的呼叫；模型回過話之後才失敗照實報錯。測試 `test_generate_reply_tools.py` 12 項，突變 5 個全紅（第一輪關思考、第一次失敗不退回、查過後失敗卻退回、又帶限長度、不查時多問一次）。**重啟後實測（10-11 06:46，`it_askai_intel` 四題，新程式）**：第 2 輪快取都接上（兌換碼 cached 7,736／重讀 1,411、6.6 秒；配隊 7,731／1,276、6.0 秒；天氣 7,730／78、0.7 秒），改之前線上 7 題的第 2 輪要讀 16～61 秒；閒聊題沒有查、只呼叫 1 次（31.7 秒）；該查的照樣查（兌換碼 search、配隊 search＋fetch×2、天氣 web_search）。同題在 10-09 用舊程式跑的模型呼叫次數：兌換碼 4→2、配隊 4→3、閒聊 2→1。第 1 輪開思考、叫工具前只寫 93～120 token（3.7～4.6 秒）。整題 70.3／91.6／20.6／31.7 秒，但測試題沒有聊天紀錄、不能直接和線上比。**線上第一題（10-11 07:47，新流程）**：117 秒、模型呼叫 2 次；第 1 輪 prompt 11,206（cached 7,224、讀 20.4 秒、寫 8.2 秒）→ search 7.5 秒 → 第 2 輪 prompt 12,634（cached 11,202、重讀 1,432、讀 6.9 秒、寫 1,412 token 71.7 秒）。第 2 輪快取在線上也接上了；現在最花時間的是寫回答（含思考，佔六成）。同一天 05:53 舊流程那題的第 2 輪是 cached=0、讀 61.4 秒。線上只有這一題是新流程，「整題省幾秒」仍是估算。天氣題第一次 web_search 被 openmeteo 逾時（2.7 秒），模型自己重查一次才拿到——`searxng/settings.yml` 的 openmeteo 加 `timeout: 4.0` 仍待使用者決定。**預估效果（10-11，把新流程套到 10-09 六題的 `llm_usage` 算的，不是實測）**：模型時間（各輪讀 prompt＋寫字，不含查資料與排隊）每題省約 10～58 秒，六題合計 735 → 約 581 秒（少 21%）；決策輪白跑的 2 題省整輪（58、23 秒），決策輪有查的 4 題省第 2 輪的重讀（扣掉第 1 輪改開思考多寫的字，估 6 秒）後約 10～42 秒。假設模型做的決定和當時一樣；六題都是查資料題。圖解頁（使用者私人頁面）第 7 段有圖。沒採用的選項：(b) 正式輪帶 `reasoning_effort: medium`（模板在 medium 時不加那句；會改變回答深度）(c) 兩輪同一種思考設定但保留決策輪。

</details>

## Lemonade 升級盤點的缺口：載入快取與寫入緩衝（歸檔 2026-11-07，原至 2026-10-02）

> LM-Q2 載入快取不會因 Lemonade 重啟失效（10-29 有手動清除）；LM-Q4 寫入緩衝要不要收成一份。
>
> 關鍵字：Lemonade、recipe_options、ctx_size、載入快取、reset_cache、raw_message_store、store_chat、ambient_memory、寫入緩衝

<details>
<summary>展開原文（約 780 字）</summary>

> 從 `AI_HANDOFF_AND_TODO.md`「Lemonade 後端與寫入緩衝的待決（2026-10-01）」區塊（`lemonade-backend-open-questions`）瘦身前的完整原文；交接檔只留現況、規則與坑、未定案、待做。

> 從 2026-10-01 10:4x 盤點紀錄搬來（Lemonade 升級盤點時發現的缺口）。LM-Q1（聊天向量斷線會掉）已修（`95a0330`），LM-Q3（重啟期間的請求不補做）決定維持現狀。

- **LM-Q2 load cache 不會因 Lemonade 重啟失效**：`_LEMONADE_LOADED` 記「已推過 ctx_size」，Lemonade 若重灌洗掉 `recipe_options.json`，bot 不會重推 → 用預設 4096 跑、長 prompt 爆 context。選項：A 遇到連線錯誤或 context exceeded 時清掉該模型的 cache／B 定期比對 `/api/v1/health` 的 `version` 變了就清／C 不改。建議 A。這次升級設定有保留，沒發生。 **10-29**：「重新偵測」按鈕呼叫 `reset_cache()` 會一起清載入快取，等於選項 A 的手動版；自動偵測 Lemonade 重啟（OA-Q7）排第二步。
- **待決 LM-Q4**：三份記憶體 buffer（`store_chat`、`raw_message_store`、`ambient_memory`）骨架相同，`raw_message_store` 在 pgvector 斷線時也會整批丟掉；選項：A 抽成 `utils/` 共用元件並讓 raw store 也放回重試／B 只補 raw store／C 不動。建議 A，但等這次上線觀察過再做。

</details>

## LLM HTTP client 通用錯誤護網（歸檔 2026-06-20，原 2026-05-18）

> embedding 缺 key 只報 'data'，加信封拆解與缺 key 檢查，之後錯誤會顯示後端實際回了什麼。
>
> 關鍵字：_unwrap_response_envelope、_require_json_key、KeyError 'data'

<details>
<summary>展開原文（約 971 字）</summary>

<!-- @meta
id: llm-http-client-error-net
type: FIX
status: confirmed
last_confirmed: 2026-05-18
-->

**症狀：** `/askai` 每次跑都跳兩個 warning：`pgvector vector rank 嵌入問題失敗（降級為 BM25-only）: 'data'`、`member-profile vector retrieval 失敗（保留 SQL 結果）: 'data'`。
**根因：** `llm_http_client.py:embedding/aembedding` 直接 `data["data"]` 取 key，後端回非 OpenAI shape（error envelope、ollama native shape）時 raise `KeyError: 'data'`，例外 str 就是 `'data'` 無法判讀。原 sync `_post_json` 沒有 envelope unwrap，async `_apost_json` 只認 `error.type == "network_error"`。
**改動：** [llm_http_client.py](../../src/llm/llm_http_client.py) 新增兩個 module-level helper（多 endpoint 通用）：`_unwrap_response_envelope(data)`（network_error→ConnectError 觸發退避重試；其他 error envelope→`LlmAPIError(status=None)` 不重試；正常 payload 原樣回傳；用於 sync/async 兩出口）、`_require_json_key(data, key, *, op_label)`（缺 key / 型別不符→raise `LlmAPIError` 附 keys+sample；用於 `embedding()`/`aembedding()`，未來新 endpoint 可套）。
**收益：** 下次同樣 warning 直接顯示後端實際回了什麼；model_not_loaded 等永久錯誤被正確識別、不無限退避。

</details>

## lemonade 對 chat stream + 背景 embedding 併發失敗（`no_choices` 假象）（歸檔 2026-06-20，原 2026-05-11）

> Lemonade 回 200 加錯誤信封造成假 no_choices；加鎖讓串流與 embedding 互等。
>
> 關鍵字：lemonade_gate、stream_exclusive、no_choices 假象、network_error 200

<details>
<summary>展開原文（約 1,201 字）</summary>

<!-- @meta
id: lemonade-stream-embedding-gate
type: FIX
status: confirmed
last_confirmed: 2026-05-11
-->

Root cause：5/4 補的 snapshot log 攢到 3 筆 `no_choices` 事故，raw body 都是 `{'error': {'type': 'network_error', 'message': 'CURL error: ...'}}`，是 lemonade gateway 內部 CURL 轉發到 downstream backend(port 8002, llama.cpp) 失敗的回應，但 lemonade 用 `200 OK + error envelope` 回 client，破壞 HTTP 語意，導致 bot 走 `no_choices` 分支且不重試。三次失敗時間軸全部都是 `/askai` LLM stream 進行中 → 1–4 秒前 `on_message 批次處理 pgvector`（`chat_persistence.py` `flush_buffer` 觸發的 batch embedding）→ LLM 連線被 lemonade reset。`/askai` 內部 RAG embedding 與 chat 是序列的不會自己撞，會撞的是背景 flush。**修法**：① 新增 `src/llm/lemonade_gate.py`：module-level `asyncio.Lock` + `stream_exclusive()` async context manager ② `llm_service.py` `chat_raw` 的 `chat_completion(...)` 那行外包 `async with stream_exclusive():`（snapshot 路徑留 gate 外）③ `chat_persistence.py` `flush_buffer` 的 executor 寫入包進 `stream_exclusive()`（buffer_lock 已先釋放）；對稱設計＝兩端互等 ④ **B1 兜底**：`llm_http_client.py` `_apost_json` 收到 200 後檢查 `data["error"]["type"]=="network_error"` → 主動 raise `httpx.ConnectError` 命中退避重試（2 次、1s/2s），用盡後 `LlmConnectionError` → 分類從假性 `no_choices` 改回真實 `connection`。**驗證**：AST parse 四檔全綠；未跑 unittest（純鎖、既有測試不覆蓋此路徑）。

</details>

## LLM client 重構：拋 openai SDK，改自寫 httpx wire 薄殼（歸檔 2026-06-20，原 2026-04-28）

> 換套件後 embedding 一直退回 BM25，改自寫 httpx 薄殼並加後端 profile，綁協定不綁 SDK。
>
> 關鍵字：llm_http_client、BaseEmbedding、backend profile、綁協定不綁 SDK

<details>
<summary>展開原文（約 777 字）</summary>

<!-- @meta
id: llm-client-httpx-rewrite
type: FEATURE
status: confirmed
last_confirmed: 2026-04-28
-->

Root cause：commit `763d251`（chat 切 OpenAI SDK）順手把 LlamaIndex embedding 包從 `-ollama` 換 `-openai`，後者 `OpenAIEmbedding.__init__` 對 model 名做 enum 白名單驗證，自訂 model 名直接拋 `ValueError`，`SafeLLMEmbedding` 一直 fallback BM25 沒被注意。**修法**：① 新增 `src/llm/llm_http_client.py`（httpx 薄殼 ~200 行；chat/embedding/list_models + 指數退避）② `safe_llm_embedding.py` 改 subclass `llama_index.core.embeddings.BaseEmbedding`（核心介面穩定）③ `llm_service.py` 拋 `AsyncOpenAI` 改用 `LlmHttpClient` ④ `LLMRuntimeConfig` 加 `backend`+`backends` profile，per-call Ollama-only knobs 只在 `backend=="ollama"` 時生效 ⑤ `llm_runtime_config.json` 遷移新 schema（三後端 profile 備好）。Commit C1 `8642806`=code、C2 `02a937c`=deps cleanup。**設計準則**：綁協定不綁 SDK。

</details>

## Ollama 服務穩定化（chat_raw / keep_alive / 重試 / VRAM）（歸檔 2026-04-19）

> 統一 chat_raw、keep_alive 依用途、5xx 與逾時重試、embedding num_ctx 8192。
>
> 關鍵字：OllamaService.chat_raw、generate_reply、keep_alive 參數、自動重試 OLLAMA_MAX_ATTEMPTS、SafeOllamaEmbedding num_ctx=8192

<details>
<summary>展開原文（約 1,886 字）</summary>

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

</details>
