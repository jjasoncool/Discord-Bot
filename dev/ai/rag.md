# 聊天檢索（RAG）

<!-- 給 AI：這份是歸檔檔，改之前先看完這段
結構：上半部（一頁看懂、時間線、定案與理由、踩過的坑）是整理過的重點；「## 原文」以下是當時的紀錄。
新增一段：
1. 原文放在「## 原文」目錄表下方的最前面，照現有各段的格式（## 標題、> 摘要與關鍵字、<details> 包正文，標籤前後各空一行）。
2. 目錄表加一列；dev/README.md 的「依日期」加一列。
3. 同一輪更新上半部，並把下面的「整理到」改成新段的日期。
不要改：原文正文、既有的段落標題（README 和其他檔用標題當錨點）。
找細節用搜尋，不必整份讀。改完跑 python3 dev/check.py。完整規則：AI_HANDOFF_AND_TODO.md「本檔維護規則」的「歸檔放哪」。
整理到：2026-10-27
-->

> 現況、待決與待做以交接檔為準：[聊天檢索（RAG）：折疊、品質閘、重排、HNSW、聊天搜尋工具](../../AI_HANDOFF_AND_TODO.md#聊天檢索rag折疊品質閘重排hnsw聊天搜尋工具)。
> 這裡是歷史。上半部是整理過的重點；「原文」是當時的紀錄，提到的檔名、函式、狀態可能已經改了。原文提到的 `TODO-completed.md` 是 2026-11-07 以前的單一歸檔檔，內容都拆到 `dev/` 了，從 [dev/README.md](../README.md) 找。

## 一頁看懂

這個主題管 bot 怎麼從聊天紀錄裡找出相關的話：插話時的回憶、/askai 帶進 prompt 的相關訊息，以及讓模型自己查聊天紀錄的搜尋工具。

- **10-26 起因**：聊天表 344,808 列、沒有向量索引，插話回憶每次全表掃約 4 秒。同一人同一句的重複佔 17.5%，純表情、純貼圖也過得了舊的字數閘門。
- **10-26**：只改檢索端。同一人同一句折成一則，純表情、貼圖、連結不佔名額，/askai 的相關訊息加 reranker 重排。三位審查者複查後再修一輪，最重要的一條是兩條檢索路折疊不一致、同一句的分數被拆成兩半。
- **10-26 晚～10-27 上午**：重算整張表的向量，不再把 message_id、author_id 這些 metadata 一起算進去。先寫進影子欄，再在一個交易裡改名切換；HNSW 索引 06:38 建好（19 分鐘、2,211 MB），09:30 切換完成。
- **10-27**：索引 2.2 GB 放不進頁快取，加了索引 profile，可以改用前 512 維＋16 位元的小索引。另做給 /askai 的聊天搜尋工具（phrase 字面計數、topic 照意思找），字面比對建了 `pg_trgm` 索引。
- **10-27 晚**：embedding 後端回 5xx 長達 4 小時，639 則訊息被當成壞訊息略過。改成 5xx 也觸發自癒、寫入端遇到 5xx 就放回 buffer、自癒成功或放棄都私訊管理員。

**歸檔時（10-27）的狀態**

- [x] 重複折疊、品質閘、/askai 重排（10-26）
- [x] 重算向量、HNSW 建好並切換（10-27）
- [x] 聊天搜尋工具、`pg_trgm` 索引、embedding 5xx 自癒（10-27）
- [ ] 聊天搜尋工具要等重啟才生效
- [ ] 512 維＋16 位元索引的召回還在評估
- [ ] 舊向量欄 `embedding_v1` 留一個月當回滾，約 11-27 後 DROP 並 VACUUM FULL
- [ ] reranker 門檻 0.1 只測過 9 則；`LemonadeReranker` 要不要搬到 `llm/client/` 還沒定

最新狀況看交接檔。

## 時間線

| 日期 | 發生什麼 | 結果 |
|---|---|---|
| 10-26 | 唯讀實查聊天表 | 344,808 列、1024 維、沒向量索引；插話回憶全表掃 3.96～4.06 秒；重複 60,317 列、不到 8 字 146,851 列 |
| 10-26 | 檢索端：折疊、品質閘、/askai 相關名額、reranker 重排；從聊天紀錄抽 60 題評估集候選 | 新測試 `test_rag_collapse.py`；完整測試 1,753 個全綠 |
| 10-26 下午 | 三位審查者（正確性、設計與重用、重算計畫）複查，medium 以上再由反駁者驗證 | 折疊改在兩條路之前做一次、向量路查全部 id、重排進 bot 的 GPU 閘門；完整測試 1,763 個全綠 |
| 10-26 晚 | 重算向量計畫審查後改版；重算工作核准並做好 | `llm/storage/chat_reembed.py`；2,000 列試算：答案距離 0.285→0.261、雜訊距離 0.647→0.692 |
| 10-27 上午 | 06:38 HNSW 序列建圖；09:30 一個交易內改名切換；10:27 補尾巴 | 索引 19 分鐘、2,211 MB、有效；切換時的 UPDATE 掃表 15 分鐘；補尾巴 378 列 |
| 10-27 | 規劃器不走 HNSW；整句重複的向量叢集找不到 | 專用聊天表拿掉 `doc_type` 篩選；全庫搜尋 `hnsw.ef_search` 開到 1000 |
| 10-27 | 舊欄位處置；索引放不進頁快取 | `embedding_v1` 留一個月；加索引 profile 開關 `chat_vector_index`（全欄或前 512 維＋16 位元） |
| 10-27 | 「誰常說 X」排到 25 名外 → 聊天搜尋工具；評估集進版控 | `llm/retrievers/chat_search.py`、開關 `askai_chat_search_mode` 已開、待重啟；評估放 `src/llm/retrievers/eval/`，題目放 `private/` |
| 10-27 | 字面模式要不要索引；metadata 補 `guild_id`；「誰最常欺負某人」這類行為題 | 建 `pg_trgm` GIN 索引；`guild_id` 只寫新列、不回填；topic 撈到 100 則並附每人幾句、加 `contains` |
| 10-27 晚 | embedding 裝置掉了 4 小時，639 則被略過（靠 14 天內的補寫救回） | 5xx 帶後端壞掉的訊號也走自癒；寫入端遇 5xx 放回 buffer、只記一次 ERROR；自癒結果私訊管理員 |

## 定案與理由

| 決定 | 為什麼 |
|---|---|
| 折疊在 Python 做，不在 SQL | 正規化規則已經有一份（`tokenization`），SQL 再寫一份是二輪；排序成本在掃表不在回傳筆數；在 Python 折，測試不用資料庫 |
| 只折字面，不折語意（MMR、距離閘） | 重複的 86% 是一模一樣的表情、貼圖、4 字以內的反應詞，近似重複只多收 0.6 個百分點；MMR 在沒索引的表上要多掃幾倍 |
| /askai 相關名額跨作者去重，插話回憶保留不同作者的同一句 | 名額是給模型的脈絡，五個人的「笑死」不如五句不同的話；回憶裡幾個人都講過是訊號 |
| 折疊只做一次、放在兩條檢索路之前，向量路仍拿全部 id 去查 | 原本兩路投給不同的 id，RRF 把重複講過的句子分數拆成兩半；最新那則可能還在寫入緩衝、沒進向量庫 |
| 品質閘收進 `emoji_text_utils`，不開新檔 | 新檔要先問使用者；這個模組本來就裝著「整則只有表情」的判斷 |
| reranker 門檻 0.1 | 實測分數極度兩極（答得到的 ≥ 0.95、不相干的 ≤ 0.0001），0.1 只擋明顯不相干的 |
| 重排開關程式預設 off、`switches.json` 設 on | 預設要「關掉也安全」；使用者已定案要做 |
| 重排在 bot 的 async GPU 閘門裡做，`LemonadeReranker` 給空的 gate | 插話與產圖看得到持有者；它預設的同步鎖是給沒有 event loop 的行程用的 |
| 重算向量用影子欄＋改名，不原地覆寫 | 兩種膨脹一樣，但影子欄能瞬間回滾、能拿評估集做 A/B |
| 重算時送去算的字串就是 `text` 原樣，不加前綴 | 否則和新寫入的列在兩個向量空間 |
| 重算每批都拿 GPU 閘門，等不到就睡 30 秒再試，永遠不硬闖 | 和 bot 同時用顯示卡就是 10-08 斷線那種情況 |
| HNSW 序列建圖 | 平行建圖會把 1.6～1.8 GB 的圖塞進只有 64 MB 的 `/dev/shm`，直接失敗 |
| 切換在一個交易裡：先改名拿鎖，再補 NULL，再改名 | bot 每 5 分鐘或滿 30 則就 flush，先 UPDATE 再改名中間有空隙 |
| `embedding_v1` 留一個月當回滾，約 11-27 後 DROP 並 VACUUM FULL | DROP 只改 catalog、回收不到那 1.8 GB；真要回收得 VACUUM FULL，bot 停幾十分鐘 |
| 專用聊天表的查詢拿掉 `doc_type` 篩選 | JSON 表達式沒有統計，規劃器估 0.5% 選擇率，選了 105 秒的平行全表掃描 |
| 全庫搜尋 `hnsw.ef_search` 開到 1000 | 同一句重複幾十次的向量叢集，200 時找到 0／72 列、1000 時 70／72 列，熱快取多約 20 ms |
| 不走 DiskANN，改縮索引（16 位元、512 維、部分索引） | DiskANN 靠 NVMe 每秒十萬次的隨機讀；這台磁碟每秒只有幾百次，資料量也遠不到那個規模 |
| 「誰常說 X」做成給模型用的工具，分 phrase 和 topic 兩種模式；不靠引號觸發 | 整句算向量對到的是問句框架；每題都拿原句全庫比對的話，問法的字壓過內容，計數題也答不出；使用者不要打一堆東西 |
| 聊天評估集放新資料夾 `src/llm/retrievers/eval/`，題目放 `private/` | 考的是聊天向量庫、要在 discord-bot 容器跑；題目本身就是群友的聊天內容，repo 有公開鏡像 |
| 字面模式建 `pg_trgm` GIN 索引 | `ILIKE` 是全表掃描，冷快取幾秒到十幾秒；三個字以上的句子走索引變毫秒級 |
| `guild_id` 只寫進新列，舊列不回填 | 回填要重寫全表、7 個索引跟著長、要 VACUUM，當時沒有查詢用它 |
| 行為題用 topic 撈 100 則、回每人幾句的統計 | 原本只會數提到名字的次數，變成統計機器 |
| embedding 回 5xx 帶後端壞掉的訊號也觸發自癒；寫入端遇 5xx 放回 buffer | 639 則被當成單則錯誤略過；每則一行 WARNING，4 小時 639 行沒人看到 |

## 踩過的坑

- **向量裡混了 metadata**：94.6% 的向量是連同「message_id: … author_id: …」一起算的，短句被 id 稀釋，查詢端又沒有這串。重算後距離分布會整個改變，插話回憶的距離門檻要跟著重新校準。
- **兩條檢索路折疊不一致**：BM25 留最新那則、向量留最近那則，RRF 把同一句的分數拆成兩半。
- **純標點的 `dedup_key` 是空字串**：「????」「……」這類不能拿來折，三處都改成各自算一句。
- **`hnsw.ef_search` 超過 1000 不會報錯**：會被重設成 40，要自己夾在上限內。
- **HNSW 的 iterative_scan 不保證順序**：要撈距離回來、在 Python 端照距離排再折；它最多掃 `hnsw.max_scan_tuples`（20,000）就停，小頻道的候選可能變少。
- **`doc_type` 篩選讓規劃器不用 HNSW**：建好索引還得拿掉篩選才會走索引。
- **reranker 會回非有限分數**：後端漏掉的文件被填成 -inf、壞掉回 NaN，一律不保留。
- **平行建 HNSW 會塞爆 `/dev/shm`**：pgvector 容器只有 64 MB，會 `No space left on device`。
- **`psql -c "SET…; CREATE INDEX CONCURRENTLY…"` 會失敗**：一個 `-c` 會包成一個交易，要分開下。
- **llama-index 的 `embed_batch_size` 預設 10**：一批 64 其實是 7 次 HTTP，要設成和 batch 一樣。
- **`--column embedding` 少了 `--redo-copied` 會「做了 0 列」假裝成功**：程式端現在直接拒絕這個組合。
- **切換時補 NULL 的 UPDATE 掃了整張表 15 分鐘**：下次這類切換用主鍵範圍補。之後重做「沿用舊向量」的列時，比對兩個向量欄會解開 3.6 GB，所以重算工作加了 `--min-id`。
- **DROP COLUMN 回收不到空間**：TOAST 還被活的資料列引用，只有 VACUUM FULL 收得回來。
- **`to_tsvector('english')` 把中文整段當一個 token**：子字串對不到，要字面比對得另建 `pg_trgm` 索引。
- **5xx 被當成單則錯誤**：後端壞了 4 小時，639 則被略過，只有一則一行的 WARNING。
- **`test_import_resolution` 會把 `logging.getLogger("test.rag_collapse")` 的字串當成模組路徑**：測試裡改用 `__name__`。

## 原文

新的在前。每段標題下面是摘要，正文在「展開原文」裡。

| 日期 | 段落 | 摘要 |
|---|---|---|
| 2026-10-27 | [聊天檢索 RAG（10-26～10-27）](#聊天檢索-rag折疊與品質閘兩輪審查重算向量與-hnsw-遷移h512-索引聊天搜尋工具歸檔-2026-11-07原至-2026-10-27) | 10-26 折疊、品質閘與重排；10-27 重算向量切到 HNSW，加小索引 profile、聊天搜尋工具與 5xx 自癒。 |

## 聊天檢索 RAG：折疊與品質閘、兩輪審查、重算向量與 HNSW 遷移、h512 索引、聊天搜尋工具（歸檔 2026-11-07，原至 2026-10-27）

> 10-26 折疊、品質閘與重排；10-27 重算向量切到 HNSW，加小索引 profile、聊天搜尋工具與 5xx 自癒。
>
> 關鍵字：RAG、聊天向量、HNSW、halfvec、重算向量、chat_reembed、pg_trgm、chat_search、reranker、評估集

<details>
<summary>展開原文（約 25,186 字）</summary>

> 從 `AI_HANDOFF_AND_TODO.md`「聊天檢索（RAG）優化：重複折疊、品質閘、/askai 重排（2026-10-26 做好並 commit；重算向量、HNSW、切換 10-27 完成；聊天搜尋工具 10-27 做好、待重啟）」區塊（`rag-chat-retrieval`）瘦身前的完整原文；交接檔只留現況、規則與坑、未定案、待做。

> 說明文件（架構圖、三條檢索路徑的流程與例子、HNSW 原理、決定與優劣、待判斷清單）與 60 題評估集候選（第二個分頁，請勾 30 題）在 Claude Doc：https://claude.ai/artifact/PfrESK3SSsr7jCpoVQkVKr 。本區只留結論、待決與坑。

**現況數字（10-26 唯讀實查）**：聊天表 `data_discord_messages_index` 344,808 列、1024 維、無向量索引（heap 540 MB、向量收在 TOAST 1.8 GB）；插話回憶的全庫查詢（本頻道、LIMIT 25）全表掃 3.96～4.06 秒、讀 2.9M 頁；/askai 窗內查詢（`message_id = ANY`）走 btree 21 ms。同一人同一句的重複 60,317 列（17.5%）；不到 8 字 146,851 列（42.6%）；純表情描述 25,279 列（其中 1,732 列 ≥ 8 字、過得了舊閘門）、純貼圖 15,397 列（其中 14,612 列 ≥ 8 字、過得了舊閘門）。pgvector 0.8.2、PostgreSQL 18.6；maintenance_work_mem 64 MB、shared_buffers 128 MB；VM 7.9 GB、可用約 4.1 GB。

**做了什麼（都在檢索端；寫入端、資料庫一列都沒動）**
1. 折疊（RG-Q1）：`search_chat` 多撈 `_COLLAPSE_OVERFETCH`＝4 倍，再用 `tokenization.dedup_key`（正規化後只留字母數字與中日韓文字）把同一作者同一句折成距離最近的一則、帶 `repeat_count`（只數這批撈到的，不是全庫）；不同作者的同一句各自保留。BM25 在 100 則視窗裡同一人同一句只算最新那則。插話回憶的注入行尾標「（同一人說過 N 次）」。
2. 品質閘（RG-Q2）：`emoji_text_utils.is_emoji_or_symbol_only` 多認 `:描述:` 與 `[貼圖：…]`；插話的 `_is_link_only` 收成同模組的 `is_link_only`，插話內容閘、插話回憶、/askai 三處共用（守衛 `test_shared_conventions` 新規則「整則只有連結的判斷」擋手刻的 `startswith("http`，爬蟲容器例外）；插話回憶的 `callback_min_chars` 改成 SQL 的 `length(text) >= 8`，候選池不再被反應詞佔掉（以前 45% 在 Python 端才丟）。
3. /askai 相關名額：純表情／貼圖／連結不佔名額、不分作者同一句只留融合分最高的；保底的最近 25 則不經閘。stats log 多 `noise_skipped`、`repeat_skipped`、`reranked` 三個計數；`retrieval_debug` 多 `reranked`（message_id、分數、送去的文字）。
4. /askai 重排：融合名次前 `rerank_candidates`＝30 則，每則給 reranker 看「顯示名: 內容」，照分數取 25，低於 `rerank_min_score`＝0.1 的不進；reranker 壞掉、GPU 等太久、筆數不對都照融合名次。reranker 由指令層 `_askai_reranker()` 依開關 `askai_rerank_mode`（`switches.json` 已設 on；程式預設 off）建 `services.search.rerank.LemonadeReranker` 交進檢索層（檢索層是技術層，不 import `services.search`）。實測 9 則 0.6 秒，分數兩極：答得到的 ≥ 0.95、不相干的 ≤ 0.0001。
5. 評估集：60 題候選（A 誰說過什麼 20、B 某次討論的推論 15、C 口頭禪 15、D 近 14 天 10）從 `discord_messages_raw` 唯讀抽：A／D 取 15～60 字、有人按過反應、全庫唯一、非表情貼圖連結；B 多一個「所以／結論／最後」字面條件；C 是同一人同一句 ≥ 19 次。每題錨 message_id（C 類是那位作者說過這句的任一則）。跑分程式是新檔，等使用者勾完 30 題再問放哪。

**獨立審查後的修正（10-26 下午；三位審查者：正確性、設計與重用、重算計畫；每條 medium 以上再由反駁者驗證，結果見盤點紀錄）**
- 折疊只做一次、放在兩路之前：/askai 視窗先 `_collapse_window`（同一人同一句留最新，並回「每則 id → 代表 id」對照表），BM25 吃折好的清單；向量路仍拿**全部** id 去查（最新那則可能還在寫入緩衝、沒進向量庫，舊的才找得到），查到的換成代表、同一組只留最好的名次。原本 BM25 留最新、向量留最近，兩路投到不同的 id，RRF 把重複講過的句子分數拆成兩半（審查抓到的最重要一條，反駁驗證在容器重現確認為真，並補了「向量路要查全部 id」這個坑）。`search_chat` 的 `_collapse_repeats` 只給插話回憶的全庫搜尋用，代表改取最新那則、名次與距離取最近那筆。
- 純標點（「????」「……」顏文字）`dedup_key` 是空字串：三處都不折（各自算一句），而且 `is_emoji_or_symbol_only` 現在把沒有任何字詞字元的也當符號（插話內容閘也因此不會對「????????」出手，行為小變）。
- `is_link_only` 先去掉存檔格式的 `[預覽：…]`，純連結＋預覽也算純連結。
- /askai 重排改在 bot 的 async 閘門裡做（`gpu_exclusive("askai-rerank")`，插話與產圖看得到持有者；最多等 `rerank_gpu_wait_seconds`＝10、租約 `rerank_lease_seconds`＝30），`LemonadeReranker` 建立時給空的 gate、不再拿第二把鎖檔（它預設的 `gpu_exclusive_sync` 是給沒有 event loop 的行程用的）。
- reranker 回非有限分數（後端漏掉的文件客戶端填 -inf、壞掉回 NaN）一律不保留；一個有效分數都沒有就照融合名次並記 WARNING；`reranked_count` 只數有效的。
- `hnsw.ef_search` 夾在 pgvector 上限 1000 內（超過不是報錯而是被重設成 40），`services/search/vectors.py` 同步；`search_chat` 一律撈 dist、Python 端先照距離排再折（HNSW 的 iterative_scan 不保證順序）。
- 守衛規則改成只抓「整則只有連結」的形狀（`all(...)`／`any(...)` 裡的 `startswith("http…")`，單字串與 tuple 都抓；單純驗網址的 `url.startswith("https://")` 不抓），並有自己的 finder 測試。
- 插話回憶的最短字數只留 SQL 一份（Python 端的重複檢查與 debug 的 SHORT 標記拿掉）；`rerank_candidates` 簽章預設 None（＝和相關名額一樣多），數字只在設定與開關說明；`LemonadeReranker` 改頂層 import（啟動 gate 的 import 解析涵蓋得到），`services/search/__init__` 的說明改成「bot 只借 rerank 客戶端、不碰索引」。
- `emoji_text_utils` 模組說明改成專案格式。
- 審查建議但沒做、要你判斷：把 `LemonadeReranker` 搬到 `llm/client/`（技術層的模型客戶端，bot 就不必 import `services.search`）——是新檔與搬程式，等你點頭。

**定案與理由**
- 折疊在 Python、不在 SQL：正規化規則已經有一份（`tokenization`），SQL 再寫一份是二輪；排序成本在掃表不在回傳筆數；在 Python 折測試不用資料庫。
- 只折字面、不折語意（MMR、距離閘）：重複的 86% 是一模一樣的表情、貼圖、≤4 字反應詞，近似重複只多收 0.6 個百分點；MMR 要在沒索引的表上多掃幾倍，等 HNSW 再談。
- /askai 相關名額跨作者去重，插話回憶保留不同作者的同一句：名額是給模型的脈絡，五個人的「笑死」不如五句不同的話；幾個人都講過是訊號。
- 品質閘收進 `emoji_text_utils`、不開 `text_quality.py`：使用者要求新檔先問；該模組本來就裝著「整則只有表情」的判斷。
- reranker 門檻 0.1：實測分布極度兩極，0.1 只擋明顯不相干的；分布會記進 `askai_response_history`，不對就改。
- 開關程式預設 off、檔案 on：預設要「關掉也安全」；使用者已定案要做。

**重算向量計畫（RG-Q5 定案；10-26 晚獨立審查後改版；重算工作是新檔，等使用者核准）**
- 現況：向量是 LlamaIndex 預設 MetadataMode.EMBED 算的，送去算的文字是「message_id: …\nauthor_id: …\nchannel_id: …\ntimestamp: …\ndoc_type: discord_chat\n\n內文」（`_node_content.excluded_embed_metadata_keys` 為空）；查詢端只嵌純問句。實測吞吐（閒置時、經 GPU 閘門、平均 19 字）：batch 32／64／128 → 55／85／91 則/秒，全表約 68 分鐘純算向量；llama-index 的 `embed_batch_size` 預設 10，一批 64 其實是 7 次 HTTP，要設 `embed_batch_size = batch`。pgvector 容器 `/dev/shm` 只有 64 MB（compose 沒設 shm_size）、`lock_timeout = 0`、`max_parallel_maintenance_workers = 2`、統計過期（reltuples 273,890 對實際 345k）。
- 審查確認安全的部分：寫入端設 `excluded_embed_metadata_keys` 後 `get_content(EMBED)` 就是 `text` 本身、`_node_content` 序列化一致、`PGVectorStore.add` 只插明確欄位；影子欄＋RENAME 與 llama-index-vector-stores-postgres 0.9.0 相容（ORM 只選明確欄位、建表 checkfirst 不會 ALTER）；索引跟著欄位 RENAME 走。
- 步驟（改版）：
  ①寫入端：`store_chat._chat_node` 的 TextNode 設 `excluded_embed_metadata_keys`＝五個 metadata 鍵（backfill 同一條路）。**部署時機二選一**：跟切換一起（RENAME 後立刻重啟）→ 中間幾列的 NULL 由切換交易補；或先部署但基線要在重啟前先量完（否則現用欄位混兩種格式、基線被污染）。建議：跟切換一起。
  ②評估基線（切換前一定要有）：先用 v1（現狀）跑 30 題；`search_chat` 加只給評估用的 `embedding_column` 參數（只允許英數底線、預設 embedding），影子欄填好後同題對 v2 跑一次比對；試算的列依評估題牽涉的 message_id／頻道挑，不是「最新 2,000 則」。同時記兩個欄位 survivors 距離的 p10／p50／p90，給插話回憶重新校準 `callback_max_distance`（0.50）／`callback_target_max_distance`（0.70）——它們是對著帶 metadata 的窄帶距離調的，只嵌內文後距離分布會整個改變，地板要跟切換一起改，切換後幾天開著 `callback_debug` 看。
  ③影子欄：`SET lock_timeout = '3s'; ALTER TABLE data_discord_messages_index ADD COLUMN IF NOT EXISTS embedding_v2 vector(1024);`（不帶 DEFAULT，拿到鎖瞬間完成；拿不到就重試；避開 04:00～07:30 與每 5 分鐘的 flush）。
  ④重算工作（**已寫好** `llm/storage/chat_reembed.py`，影子欄由它第一次執行時 `ADD COLUMN IF NOT EXISTS`，所以③不必另外下）：`python -m llm.storage.chat_reembed [--limit N] [--batch 64] [--column embedding_v2] [--dry-run]` 在 discord-bot 容器跑；keyset 分頁 `WHERE id < %s AND {column} IS NULL ORDER BY id DESC`（走 pkey，新的先做）；每批 `gpu_exclusive_sync(max_wait_seconds=1800)`，`GpuBusy` 就睡 30 秒再試、**永遠不硬闖**（預設不給 max_wait 時等滿 15 分鐘會照常打模型，和 bot 同時用顯示卡＝10-08 斷線那種情況）；送去算的字串就是 `text` 原樣（不 strip、不正規化、不加 Instruct 前綴，否則和新寫入的列在兩個向量空間）；寫回 `execute_values(…, template="(%s, %s::vector)")` 的 `UPDATE … FROM (VALUES …)`，**每批 commit**；非 unreachable 的錯改逐筆重試，仍失敗的列記 log 並 `SET embedding_v2 = embedding`（沿用舊向量、保證不是 NULL）後繼續，keyset 無論成敗都前進；unreachable 才停。正式跑之前：挑一則最近的訊息分別用工作與 `_chat_node` 路徑各算一次，餘弦距離要是 0；在 bot 有人用的時候先量 5 分鐘吞吐再決定白天還是晚上跑；不在 04:00～07:30 跑。
  ⑤建索引（做完後、CONCURRENTLY，服務中可做；挑沒人用的時段、旁邊開 free -m）：同一條 psql 連線分開下 `SET maintenance_work_mem = '2500MB'; SET max_parallel_maintenance_workers = 0;` 再 `CREATE INDEX CONCURRENTLY discord_messages_idx_hnsw ON data_discord_messages_index USING hnsw (embedding_v2 vector_cosine_ops);`（**不能**用單一 `-c "SET…; CREATE INDEX CONCURRENTLY…"`：會包成一個交易而失敗；**序列建圖**才不經 DSM——平行建圖會把 1.6～1.8 GB 的圖塞進 /dev/shm，64 MB 直接 `No space left on device`；要平行就在 compose 給 pgvector 加 `shm_size: 3g` 並重建容器）。圖估 1.6～1.8 GB、主機可用約 4.1 GB、swap 已用 1.1 GB：超出 maintenance_work_mem 會退成磁碟建圖（小時級）、吃到 2.5～3 GB 有被 OOM 砍掉 backend 的風險（整個 cluster 重啟、CONCURRENTLY 失敗留 INVALID 索引要 `DROP INDEX CONCURRENTLY`）。省一半記憶體與磁碟的選項：halfvec 表達式索引 `USING hnsw ((embedding_v2::halfvec(1024)) halfvec_cosine_ops)`（建圖約 0.9 GB、索引約 0.8 GB），但 `search_chat` 的 ORDER BY 要改 `embedding::halfvec(1024) <=> %s::halfvec(1024)`。建完查 `pg_index.indisvalid`，並 `ANALYZE data_discord_messages_index`。　**10-27 06:38 已建好**（agent 經使用者授權執行；19 分鐘、2,211 MB、有效、已 ANALYZE）。　**索引 profile 之後的建法**：語法由 `CHAT_INDEX_PROFILES[profile].index_ddl(table)` 產生（`full` → `discord_messages_idx_hnsw`、`halfvec512` → `discord_messages_idx_hnsw_h512`）；換 profile 的順序固定是：建目標索引（並存）→ `indisvalid` 為 t、ANALYZE → 改 `switches.json` 的 `chat_vector_index` → EXPLAIN 或 60 題確認 → DROP 另一個；開關改早了只會退回全表掃描、不會錯；資料表全程不動、不重算。
  ⑥切換（一個交易，順序很重要）：`BEGIN; SET lock_timeout = '3s'; ALTER TABLE data_discord_messages_index RENAME COLUMN embedding TO embedding_v1;`（第一個 ALTER 先拿 ACCESS EXCLUSIVE，從這裡到 COMMIT 不會有 flush 插進來）→ `UPDATE data_discord_messages_index SET embedding_v2 = embedding_v1 WHERE embedding_v2 IS NULL;`（補尾巴擋不住最後幾分鐘的新列與永久失敗的列，這一步保證切換後沒有 NULL；幾十列、毫秒級、索引自動收進）→ `ALTER TABLE … RENAME COLUMN embedding_v2 TO embedding; COMMIT;` → 重啟 bot（寫入端）→ 用 `--column embedding --redo-copied` 再跑一次重算，把剛才沿用舊向量的幾列換成純文字格式（審查抓到：少了 `--redo-copied` 述詞恆假、會「做了 0 列」假裝成功，程式端現在會直接拒絕這個組合）。反駁驗證確認：bot 每 5 分鐘或滿 30 則 flush、編輯是 delete＋重插新 id，先 UPDATE 再 RENAME 中間還是有空隙，所以鎖要先拿。　補尾巴要帶 `--min-id <重算開始前最後一列的 id>`，不然 `embedding = embedding_v1` 會掃整張表（3.6 GB）。**10-27 09:30 已完成**（UPDATE 掃表 15 分鐘；下次這類切換用主鍵範圍補 NULL）。　補尾巴 10-27 10:27 完成（378 列）。
  ⑦切換後驗證：評估題再跑一次；對插話回憶（channel＋時間、target 模式再加 author）的查詢 `EXPLAIN (ANALYZE)` 看走哪個索引——HNSW 的 iterative_scan 最多掃 `hnsw.max_scan_tuples`（20,000）就停，小頻道或話少的人候選可能比今天的精確掃描少，不足就對那條路 `SET LOCAL hnsw.max_scan_tuples = 100000`。
  ⑧舊欄位：`DROP COLUMN embedding_v1` 只改 catalog，普通 VACUUM 回收不到那 1.8 GB（TOAST chunk 仍被活 tuple 引用）；真要回收只有 VACUUM FULL（整表 ACCESS EXCLUSIVE、重建含 HNSW 的全部索引、bot 停幾十分鐘）。**建議**：留著 embedding_v1 當回滾，磁碟還有 67 GB；或 DROP 後接受 1.8 GB 擱置。
- 膨脹預期（審查估）：UPDATE 不是 HOT（7 個索引、fillfactor 預設）→ heap 540 MB → 約 1.1 GB、索引 137 → 約 270 MB、TOAST 多 1.4 GB、WAL 約 2 GB、autovacuum 跑 4～5 次；可接受。原地覆寫 `embedding` 的膨脹完全一樣，只少掉 ADD／RENAME 與空間回收這題，但沒有瞬間回滾也不能 A/B——影子欄在真的會拿評估集比對時才值得（本計畫會）。
- 10-26 唯讀試算（2,000 列＋59 題答案）：答案距離 0.285→0.261、雜訊距離 0.647→0.692（差距 0.36→0.43）；小語料裡名次兩種格式都近乎第 1，名次收益要在全庫、改寫問句上才量得到。吞吐 98 則/秒。
- 規則式前文脈絡（v3）延後，等評估集再另開影子欄比較。寫資料庫的指令（ALTER、重算、CREATE INDEX、RENAME、DROP）都由使用者執行。

**待使用者判斷（RG-Q5～Q11，建議的先後；RG-Q5、Q6 已定案見上）**
- RG-Q5 要不要重算向量（metadata 不嵌＋規則式前文脈絡）：94.6% 的向量是「message_id: … author_id: … 內文」算的、短句被 id 稀釋、查詢端沒這串；另 5.4%（id < 19,424）是舊世代。重算一次兩件事一起消失，還能順便把「前一則誰說了什麼」用規則接在前面。成本：34 萬則 embedding、好幾天、佔 GPU；過渡期新舊混在一起檢索會變差。**建議**：先有評估集與基線，拿 2,000 則試算兩種格式比 Hit@k，有差才全量，維護時段分批。
- RG-Q6 HNSW 什麼時候建：現在每次插話回憶 4 秒、讀 23 GB buffer；建了降到幾十毫秒。索引約 1.5 GB、建 10～30 分鐘、要臨時 `SET maintenance_work_mem = '2GB'`。**建議**：先決定 RG-Q5，重算完再建（不然索引要跟著 34 萬次更新）；不重算就現在建：維護時段在 pgvector 容器 `CREATE INDEX CONCURRENTLY discord_messages_idx_hnsw ON data_discord_messages_index USING hnsw (embedding vector_cosine_ops)`；`search_chat` 要照 `services/search/vectors.py` 加 `SET LOCAL hnsw.ef_search`、`hnsw.iterative_scan = relaxed_order`（沒索引時設了無害，可先寫）。
- RG-Q7 從 doc 第二分頁勾 30 題；勾完再問跑分程式放哪（新檔）。兩條路分開量：全庫 `search_chat` 量 Hit@k；/askai 用 `askai_response_history` 的 100 則視窗重放。
- RG-Q8 reranker 門檻 0.1 留不留：只測了 9 則。不放心改 None（只重排不擋）；幾天後從 `retrieval_debug.reranked` 回報分布。
- RG-Q9 插話回憶候選池 25 → 50：折疊後最後會少於 25；放大在沒索引時不增加掃表成本，但排序與 debug log 多一倍。**建議**先不動，看幾天 debug log 的 survivors 數。
- RG-Q10 /askai 相關名額跨作者去重會讓「幾個人說 +1」這類計數題在視窗外少算。**建議**接受（保底 25 則全有）；不要就改成只折同作者，一行。
- RG-Q11 重啟：程式改動要重啟 discord-bot 才生效（避開 04:00～07:30）；開關檔已帶 `askai_rerank_mode`，舊版 bot 重啟前會記一次「不認得的開關」warning，其他開關不受影響。
- RG-Q12 **已核准並做好**（10-26 晚）：`llm/storage/chat_reembed.py`、`test/test_chat_reembed.py`；啟動：`docker exec -d discord-bot sh -c 'python -m llm.storage.chat_reembed --batch 64 > /logs/chat_reembed.log 2>&1'`，看進度 `docker exec discord-bot tail -3 /logs/chat_reembed.log`，剩幾列 `docker exec discord-bot python -m llm.storage.chat_reembed --dry-run`。
- RG-Q13 HNSW 建圖方式：序列建（不改 compose、約 10～30 分鐘）或在 compose 給 pgvector 加 `shm_size: 3g` 重建容器後平行建；要不要改用 halfvec 表達式索引（記憶體與磁碟減半、`search_chat` 的 ORDER BY 要跟著改）。建議：序列建、先不用 halfvec。　→ **10-27 已序列建好**（19 分鐘、2,211 MB）；建好後要讓規劃器用它還得拿掉 doc_type 篩選（見 06:1x 盤點）。
- RG-Q14 切換後 `embedding_v1` 留著當回滾還是 DROP（回收要 VACUUM FULL、bot 停幾十分鐘）。建議：留一個月再說。　→ **10-27 定案：留一個月，約 11-27 後 DROP 並 VACUUM FULL（bot 停幾十分鐘、避開 04:00～07:30）。**
- RG-Q15 `LemonadeReranker` 要不要搬到 `llm/client/`（技術層的模型客戶端；bot 就不必 import `services.search`，情報搜尋從那裡拿）。新檔與搬程式，等你點頭；不搬也能跑。
- RG-Q16 「誰常說 X」這類問題怎麼找（10-27 第二輪改版：使用者**不要引號觸發**，而且結果要看得出**是哪個頻道的誰**說的）。現象：整句問題算向量對到的是問句框架（「誰說的」「誰信」），X 平淡時目標句排到 25 名外（C 類 20→14；詞有特色的 14 題照樣第 1～6 名）。量過：只拿要找的那句話算向量 Hit@1 17/20、Hit@25 20/20；那句話 ILIKE 全庫按作者計數 Hit@1 18/20、Hit@3 20/20、0.3 秒/題、不用新索引。查證的現況：每一列的 author_id、channel_id、timestamp、message_id 都還在 `metadata_`，重算只是不再把它們混進向量；/askai 上下文每行是「名字#尾碼: 內容」（`context_retriever.py` 組行處）；`search_chat` 回傳有 author_id 但沒帶 channel_id（只拿來過濾，/askai 視窗本來就同一頻道）；折疊只折同一人同一句，不同人分開、幾個人都說過是訊號。/askai 今天只搜 100 則視窗、不搜全庫，所以這是新能力。選項（都不靠引號）：**A 工具（建議）**：給 /askai 一個「聊天紀錄搜尋」工具（參數：要找的句子、可選作者、可選頻道），模型自己從問句抽出要找的句子來呼叫；後端＝字面比對按（作者、頻道）計數＋最近幾則原文（頻道名、名字#尾碼、時間），字面 0 筆退到只嵌那句話的向量路；接法同 `WebSearchTools`：實作 `ToolRunner`、`run_with_intel(also=[…])`、`combine_runners`，開關一個。代價：多一輪模型呼叫（幾秒）、靠模型判斷何時查（情報搜尋的經驗：模型自己寫的查詢 Hit@5 71%、換字再查 79%）。**B 全庫混合檢索**：全庫多一條字面路再和向量路 `utils.rank_fusion` 合併。現有 GIN 是 `to_tsvector('english')`，中文整段當一個 token（「好了啦 又在裝」切成兩個 token、子字串對不到）；要子字串得加 pg_trgm 索引或兩字組 tsvector 欄位（DDL）；問句框架的字（誰、常說）也會對到，要靠 IDF／停用詞；工程最大、對所有問題都有一點幫助。**C 規則抽詞**：用「誰常說／口頭禪／誰說過」樣板剝掉框架。便宜但脆，和引號一樣是死規則，不建議。**D 查詢改寫**：檢索前先叫一次模型抽「要找的句子、人、頻道」。效果同 A 但每題都多一次呼叫，A 只在模型覺得需要時才查。不管選哪個都要補：`search_chat` 回傳加 channel_id、呈現加頻道名（指令層由 guild 對 id）。要定：選 A？放不放進這次？　**第三輪（使用者：「想要類似通用 AI、不想要 user 打一堆東西、有時只是印象搜尋或問題」，問是不是 B）**：A 與 B 使用者都只打一句自然語句，差別是誰決定去哪找、用什麼字找——A 由模型讀完問題自己決定要不要查、抽出要找的句子或主題（通用 AI 產品的搜尋就是這樣：模型改寫查詢再查，不是拿原句直接比對）；B 是每題都拿原句去全庫比對再塞進 prompt（傳統 RAG），弱點就是這次量到的：問法的字壓過內容、「誰常說」這種要計數的問題排名式檢索答不出來、中文字面路要建索引。印象搜尋（「之前好像有人說過…」）拿原句算向量本來就行（D 類 20/20、A 類 9/12），所以 A 的工具要有兩種模式：phrase（字面、按作者與頻道計數）與 topic（語意、回最近幾則含誰／哪個頻道／何時），模型自己挑；視窗內的 BM25＋向量照舊、不動。B-lite（每題順手跑一次全庫語意、塞幾行）等 HNSW 建好後若印象題仍漏再加，不是現在。建議仍為 A（兩種模式）。　**10-27 定案：A，工具兩種模式（phrase／topic）**。第四輪（使用者問「能不能在背後執行、使用者察覺不到」）→ 可以，而且不用另外做：/askai 的工具呼叫本來就在「🔄 AI 思考中」那則只有發問者看得到的訊息背後跑，公開回覆只有「問題／回答」兩段、沒有任何工具標記，情報與上網工具今天就是這樣；經過只記 log 與 `askai_response_history`。使用者能察覺的只有多等幾秒（建了 HNSW 後資料庫那段是毫秒，剩模型多一輪）。要補：工具規則加「回答裡不要說你查了紀錄」（模型有時會自己講「我查了一下」）；可選：第一輪模型呼叫時同步先跑一次 topic 搜尋當預取（省資料庫往返，不省模型那一輪，先不做）。**未答**：放進這次一起做，還是切換上線後再做。　→ **10-27 做好**：`llm/retrievers/chat_search.py`、開關 `askai_chat_search_mode` 已 on、待重啟（見盤點 15:0x～16:0x）。
- RG-Q18 索引放不進頁快取（使用者：「索引那麼吃記憶體嗎、VM 不可能給太多資源」）：2.2 GB 的大頭是索引裡每個節點都存一份完整向量（345k × 1024 維 × 4 bytes = 1.4 GB）加鄰居表與頁的填充，不是圖本身。縮小的路（可疊加）：①`halfvec` 表達式索引（16 位元浮點；`CREATE INDEX CONCURRENTLY … USING hnsw ((embedding::halfvec(1024)) halfvec_cosine_ops)`，`search_chat` 的 ORDER BY 改成同一個表達式；估 1.0～1.2 GB、召回幾乎不變、序列建約 20 分鐘、舊索引可並存再 DROP）；②降維：embedding 模型支援自訂輸出維度（截斷前 N 維再正規化），512 維＋halfvec 估 0.5～0.6 GB，表達式索引 `l2_normalize(subvector(embedding,1,512))::halfvec(512)`、查詢端同樣處理，**要先用 60 題評估集量召回**；③ef 參數化（插話 400）降冷讀量；④查 scraper 為什麼 CPU 89%、851 MB（它的檔案讀寫在擠快取）。**建議**：先 ①＋③（不用加記憶體、不改資料格式），② 另開評估再決定。不建議 shared_buffers 拉大（8 GB 會換頁）。　**11:2x 補**（使用者要記進文件：VM 沒資源、記憶體不大、在想辦法；參考說明「HNSW 須把向量與圖全放 RAM，業者改用 DiskANN 放 NVMe、RAM 只留快取、省 90%」）：說明文件新增一節「記憶體不夠時：HNSW 為什麼吃 RAM、DiskANN 是什麼、這台機器怎麼辦」。要點：HNSW 查詢是圖上隨機跳、每步讀一個節點的完整向量，RAM 幾微秒／磁碟幾毫秒差千倍，所以整張圖要常駐；DiskANN（Postgres 裡是 pgvectorscale 的 StreamingDiskANN）把圖建成每跳一步剛好讀一個 SSD 頁、RAM 只留壓縮向量導航，前提是 NVMe 的隨機讀（每秒十萬次），這台磁碟隨機讀只有每秒幾百次、資料 34.5 萬筆也遠不到那個規模，所以不走 DiskANN，改縮索引：halfvec（1.0～1.2 GB）→ 512 維＋halfvec（0.5～0.6 GB，評估跑中）→ 部分索引排除太短／純貼圖的列（再少 3～5 成；查詢要帶同一條件）→ 二元量化＋重排（0.1～0.15 GB，下一張牌）；ef 參數化降冷讀量。建議組合：512 維＋16 位元＋部分索引約 0.3～0.4 GB；召回掉太多就停在 1024 維＋16 位元＋部分索引。
- RG-Q20 聊天檢索的評估集（60 題）進版控（使用者 10-27：「之前也有題目，放一樣的地方跟格式可以嗎」）。現況：題目與跑分腳本只在 scratchpad（重開機就沒）、題目另抄在說明文件的表格。既有的情報搜尋評估在 `services/search/eval/`：`questions.json`（進 git，只有題目與答案 id）＋`private/questions_with_evidence.json`（不進 git）＋`evaluate.py`（search-mcp 容器跑）＋`reports/*.json`。**格式可以照抄**（qid／question／category／relevant，id 寫 `chat:<message_id>`；C 類多 `author` 與 `phrase` 兩個鍵，答案是「那個人說過含那句話的任一則」）。**位置建議不同資料夾**：① 它考的是聊天向量庫（`context_retriever.search_chat`），要在 discord-bot 容器跑，和情報搜尋的索引、容器都不同；② 題目本身就是群友的聊天內容與習慣（口頭禪、誰養貓、author id），repo 有公開鏡像，整份題目都該放 `private/`（gitignore），只有跑分程式進 git；情報搜尋那邊只有證據句是私密的，所以題目能進 git。建議：新資料夾 `src/llm/retrievers/eval/`＝`evaluate.py`（讀 `private/questions.json`、呼叫 `search_chat` top-25 不折疊、算 Hit@1／5／25 與中位名次、報告寫 `reports/<時間>-<名稱>.json`）＋`private/`（gitignore）＋`reports/`；另一個選項是塞進 `services/search/eval/` 共用 `evaluate.py` 加 `--target chat`，省一個資料夾但兩種評估的容器、索引、指標都不同、會把兩件事綁在一起，不建議。新檔要使用者點頭。　→ **10-27 使用者同意、已做**（見盤點 14:2x）。
- RG-Q21 聊天搜尋工具的字面模式要不要建 trigram 索引。現況：`text ILIKE '%句子%'` 是全表掃描（heap 約 660 MB），熱快取 0.3～0.5 秒、冷快取幾秒到十幾秒（已設 20 秒逾時，逾時回錯誤給模型）。選項：**A 建 `pg_trgm` GIN 索引（建議）**——`CREATE EXTENSION IF NOT EXISTS pg_trgm; CREATE INDEX CONCURRENTLY discord_messages_idx_text_trgm ON data_discord_messages_index USING gin (text gin_trgm_ops);`，擴充套件 pgvector 映像已內建；三個字以上的句子走索引變毫秒級，兩個字的（哇糙、全對）照樣掃描；估索引 100～200 MB、建幾分鐘、不停機，寫入時每則多一點索引成本。B 不建，看上線後的耗時再說（log 的 `askai 聊天搜尋` 有每次的毫秒數）。C 兩字句也要快：再加兩字組的 tsvector 欄，工程大、不建議。要定：A 還是 B？　→ **10-27 使用者「補」→ A，由 agent 建（CREATE EXTENSION pg_trgm＋CREATE INDEX CONCURRENTLY `discord_messages_idx_text_trgm`）；大小、耗時與 EXPLAIN 結果見盤點 16:xx～17:xx。**
- RG-Q22 聊天表的 metadata 要不要補 guild_id（使用者 10-27 問）。現況：`store_chat` 的 buffer 有 guild_id，`_make_node` 沒放進 metadata，全表 34.6 萬列（含今天新寫的）都沒有。選項：**A 只改寫入端（建議）**——`_make_node` 多放一個鍵、測試補一條，之後的新列帶 guild_id，舊列維持 NULL；多伺服器那天用 `guild_id = X OR guild_id IS NULL` 就分得開，不回填。B 現在回填——UPDATE 全表 jsonb，每列重寫、7 個索引跟著長新項目、要 VACUUM，估比早上那次 15 分鐘的 UPDATE 久，今天沒有任何查詢用它。C 不動。要定：A 或 C？　→ **10-27 使用者「做」→ A 已做**：`store_chat._make_node` 的 metadata 多放 `guild_id`（`item.get("guild_id") or ""`，`excluded_embed_metadata_keys` 本來就是整份 metadata，所以不進向量）；`test_chat_persist_retry` +1（帶 guild_id、沒給寫空白、不進向量），突變 1 刀紅；舊列不回填。
- RG-Q23 聊天搜尋工具要能回答「誰最常欺負／嘲笑／罵某人」這類行為題（使用者 10-27：現在只會數提到名字的次數，變成統計機器）。現象：「欺負」沒有字面關鍵字，模型用 phrase 查名字「阿喵」拿到 2,340 筆提到的次數再從例句挑；topic 只回最近 8 則、排不出誰最多。**建議**：①`topic_search` 多撈到 100 則、距離上限（例 0.5）、回傳每人幾句的統計＋例句（「在最像的句子裡誰出現最多」）；②規則檔：行為、態度、評價類用 topic 並把行為描述寫進 query（「嘲笑阿喵 阿喵好廢」），phrase 只找一字不差的句子，用 phrase 查名字要講明是提到的次數；③選配 `contains` 參數（`search_chat` 加 ILIKE 條件）限定句子含某個詞；④之後可加一層 reranker 判「這句是不是在欺負」（前 100 句約 5 秒）。限制：向量抓的是主題不是態度，含蓄的欺負會漏。要定：做 ①②③？　→ **10-27 使用者「做」→ ①②③ 已做**（見盤點 22:xx）；④ reranker 判態度等看過效果再說。
- RG-Q24 embedding 後端回 5xx 時聊天寫入該不該略過（10-27 事故：Lemonade 的 embedding 裝置掉了 4 小時，639 則被當「訊息本身有問題」略過，靠 14 天內的補寫救回）。現況：`store_chat` 只把「連不上、逾時」（`is_unreachable`）當後端問題而放回 buffer，HTTP 500 當單則錯誤略過。選項：**A（建議）** 同一輪 flush 連續幾則都是 5xx 就當後端壞了：剩下的放回 buffer、停這一輪（和連不上同一條路），並記 ERROR 一次（現在是每則一行 WARNING，4 小時刷了 639 行沒人看到）；B 再加自動修復：連續 5xx 時用 admin API 卸載再載入 embedding 模型一次（這次就是這樣修好的），還是壞就走 A；C 維持現狀，靠補寫。要定：A 還是 A＋B？　**第二輪（23:0x，查過現有自癒後重擬）**：現有的 `_try_heal_lemonade_backend` 只認「network_error 信封」。建議三件一起：**A′ 擴大自癒的觸發**——5xx 的 body 帶後端本身壞掉的訊號（`ErrorDeviceLost`、`decode() failed`、`vk::`、`CUDA error`）時也走同一個重載（沿用 60 秒冷卻、`save_options=False`），再加每個模型每小時最多 3 次的上限，超過就停、記 ERROR；不認得的 5xx 不重載（可能是請求本身的問題）。**B′ 寫入端**——同一輪 flush 裡遇到 5xx 就當後端問題：剩下的放回 buffer、停這輪，記一次 ERROR（不是每則一行 WARNING），補寫仍是保底。**C′ 看得見**——自癒成功、放棄時各私訊管理員一行（`utils.dm_notifier`），「一天到晚重啟」就看得到；常發生代表那張卡或驅動有問題，要從根本修，不是靠重載。不做：從 bot 重啟整個 Lemonade 行程（碰不到 Windows，也不需要——重載模型就是重開那顆後端行程）。安全邊界：只重載壞掉的那顆模型、有冷卻與上限、不覆寫 recipe options、主模型正在生成時不主動重載（wedge 代表它已經死了才算）。要定：A′＋B′＋C′？　→ **10-27 使用者「做」→ 已做**（見盤點 23:xx）。


**驗證**：新測試 `test/test_rag_collapse.py` 16 個（守的底線寫在檔頭）；突變 9 處（折疊、貼圖閘、min_chars、雜訊閘、BM25 折疊、重複標記、分數門檻、開關接線、重複跳過）全部變紅；守衛新規則故意加一段手刻判斷會紅。完整測試（容器）1,753 個：第三次全綠（OK，skipped=2）。前兩次各 1 紅，都是同一件事：`test_import_resolution` 把新測試裡 `logging.getLogger("test.rag_collapse")` 的字串當成模組路徑，改成 `__name__`。審查修正後：`test_rag_collapse` 23 個、突變再做 9 處（視窗折疊、代表取最新、非有限分數、ef_search 上限、連結＋預覽、純標點、照距離排、閘門、空鍵）全紅，完整測試第四次 1,762 個全綠（skipped=2）；補上「向量路查全部 id、換成代表」後突變 1 處紅、第五次 1,763 個全綠；再補「副本佔名額就多撈副本數」後 `test_rag_collapse` 25 個綠、完整測試第六次 1763 個：OK (skipped=2)。

**快照**（做法見本機 `doc/snapshot_commits.md`；scratchpad 會消失，id 記在這裡）：
- 05-hermes-proxy `ae6810ce35ff5b8b8cd72667f033cb9116da11ce`：Hermes 代理（notify_server 的 /v1、`services/llm_proxy.py`、`sys_settings/hermes_settings.py`、`http_client` 的 raw／stream、`ensure_model_loaded`、主模型 ctx 65536、`test_llm_proxy.py`、AGENTS 共用元件列）。訊息：`feat: let Hermes reach the GPU only through the bot's /v1 endpoint`；body：notify_server gains /v1/models and /v1/chat/completions behind a Bearer key (services.llm_proxy.LlmProxy)／proxy takes the GPU gate per request, clamps max_tokens, streams SSE with lease renewal, logs usage as feature=hermes／http_client gains chat_completion_raw/chat_completion_stream; llm_service exposes ensure_model_loaded／HermesSettings holds the key and proxy limits; the main model context grows to 65536 so Hermes accepts it／tests cover auth, allowlist, busy/unreachable mapping, streaming and the real gate owner。
- 06-rag-retrieval-quality `35c98daafd292154352633e791cd6b088d1d435c`（審查修正後重封四次；舊的 `547901e6…`、`30735c6b…`、`8bb9a92d…`、`7a238005…` 作廢；最後一次加的是重排包成獨立 task 與租約 240 秒）：本區「做了什麼」1～4 項＋審查後的修正＋HNSW 查詢設定＋守衛規則＋AGENTS 兩列。訊息：`feat(rag): collapse repeated lines, gate noise and rerank the /askai relevant picks`；body：/askai collapses the window to the latest copy per author and normalised text (tokenization.dedup_key) before BM25 and the vector route, so both routes vote for the same message; search_chat over-fetches and collapses the same way for the ambient recall, keeping the newest copy with a repeat_count, and filters min_chars in SQL／is_emoji_or_symbol_only also recognises the stored ":描述:" and "[貼圖：…]" forms and punctuation-only text; is_link_only moves next to it, ignores the stored "[預覽：…]" tail, and ambient reuses both／/askai hands the fused candidates to the intel-search LemonadeReranker behind the askai_rerank_mode switch inside the bot's async GPU gate, drops non-finite scores and scores under rerank_min_score, and falls back to the fused order on any failure／search_chat sets hnsw.ef_search (capped at 1000) and iterative_scan before each query and sorts by distance itself; ambient recall marks "同一人說過 N 次"／a shared-convention rule guards hand-rolled link-only checks; tests cover collapse, gates, reranking, the gate fallback and the HNSW settings。
- 07-chat-reembed `cba34391904ed29e8d01a835149f7ee85e5667ca`（第二輪審查修正後重封兩次；舊的 d5c6a8ea…、42092170… 作廢；含閘門「給了上限永不硬闖」的修正）：重算工作 `llm/storage/chat_reembed.py`＋`test/test_chat_reembed.py`、寫入端只嵌內文（`_chat_node` 的 excluded_embed_metadata_keys）、`search_chat` 評估用 `embedding_column`、分層登記。訊息：`feat(rag): add the chat re-embedding job and embed only the text of new rows`；body：llm.storage.chat_reembed recomputes every row's vector from the stored text into a shadow column, newest first, one committed batch at a time, resumable from the rows still NULL／each batch takes the cross-process GPU gate with a wait limit, sleeps when the GPU stays busy, pauses after releasing so the bot goes first, and waits out the 04:00-07:30 maintenance window／a row the backend cannot embed keeps its old vector and is logged; an unreachable backend stops the run; --self-check confirms the job embeds exactly what store_chat would／store_chat excludes metadata from the embedded text so new rows match the recomputed format; search_chat accepts an evaluation-only embedding_column／tests cover paging, commits, fallbacks, the busy gate, the maintenance window, dry-run and column validation。
- 08-hermes-proxy-fixes `43fdcdba36b343134f81a255b4075ef0b2b6d80d`：第二輪審查抓到的 Hermes 代理修正（信封、n_predict 繞過、非 ASCII 金鑰、SSE 空行、上游 401、本文上限只放大 /v1、租約、.env.template 的 LLM_TIMEOUT 300）。訊息：`fix(hermes): close the proxy gaps found in review`；body：chat_completion_raw unwraps Lemonade's "200 + error" envelope, heals a wedged backend once and reports it as unreachable so the proxy answers 503／the token cap also covers n_predict and max_completion_tokens, which llama.cpp would otherwise let override max_tokens／bearer and notify secrets are compared as bytes, so a non-ASCII header is a 401 instead of a 500／an upstream 401/403 becomes 502 upstream_auth, the lease is renewed once the model is loaded, and a mid-stream error always starts a new SSE event／only the /v1 endpoint accepts large bodies; /notify keeps aiohttp's default limit; LLM_TIMEOUT in the template is long enough for a cold 64k prompt。
- 09-hnsw-query-fixes `0bd35e6c1b3c286ada0ac19f67f51adbfc935bbf`（重封一次；第一版 `dcbc2f3f…` 只有 doc_type 那段，作廢）：`search_chat` 專用聊天表不帶 doc_type 篩選（規劃器才會走 HNSW）、設定層 `chat_table_is_shared()`、全庫搜尋 `hnsw.ef_search` 開到上限 1000（`_FULL_CORPUS_EF_SEARCH`，窗內重排維持原公式）、`test_rag_collapse` 加 4 個測試。訊息：`fix(rag): make the chat search actually use the HNSW index`；body：drop the doc_type filter on the dedicated chat table (the JSON expression has no statistics, so the planner assumed 0.5% selectivity and chose a 105 s parallel seq scan); keep the filter only when another source shares the table; open ef_search to 1000 for full-corpus searches because clusters of identical vectors (one line repeated dozens of times) are skipped at 200 (0 of 72 rows) and found at 1000 (70 of 72) for about 20 ms more when warm; window reranking keeps the message_id btree path.
- 10-reembed-min-id `1df27777269f4d58a4830a0c11638db34530bd1b`（累積：含 09）：`chat_reembed` 加 `--min-id`（count 與每批查詢帶 `id > %s`）、`test_chat_reembed` 加 2 個測試。訊息：`fix(rag): let the re-embedding job limit the copied-row redo to an id range`；body：the copied-row predicate compares both vector columns and detoasts 3.6 GB without an id floor; the rows copied at the switch are all newer than the original run, so an id floor walks the primary key and finishes in seconds.
- 11-chat-index-profile `3d99ff3bedab5a6c570c1a8738edfafe7b147c48`（累積：含 09、10；另含 `lemonade_gate` 的 GpuBusy 改 `raise … from None`，是 lint 修正）：`pgvector_settings` 的 `ChatIndexProfile`／`CHAT_INDEX_PROFILES`、開關 `chat_vector_index`（switches.py＋switches.json）、`search_chat` 照 profile 組 SQL、`test_rag_collapse` 加 2 個測試。訊息：`feat(rag): add index profiles so the chat search can run on a 512-dim halfvec HNSW index`。
- commit 順序：05 → 06 → 07 → 08（各 `git read-tree <tree>` + `git commit -F <msg>`），然後字典 `chore(settings)`、交接檔 `docs`。不進版控：`src/test/integration/it_comfyui_image.py`（未追蹤的整合測試，等使用者決定）。
- 字典（emoji、sticker）照慣例另一個 `chore(settings)` commit；交接檔與 AGENTS 的文件部分另一個 docs commit。

</details>
