# 文件與待辦整理

<!-- 給 AI：這份是歸檔檔，改之前先看完這段
結構：上半部（一頁看懂、時間線、定案與理由、踩過的坑）是整理過的重點；「## 原文」以下是當時的紀錄。
新增一段：
1. 原文放在「## 原文」目錄表下方的最前面，照現有各段的格式（## 標題、> 摘要與關鍵字、<details> 包正文，標籤前後各空一行）。
2. 目錄表加一列；dev/README.md 的「依日期」加一列。
3. 同一輪更新上半部，並把下面的「整理到」改成新段的日期。
不要改：原文正文、既有的段落標題（README 和其他檔用標題當錨點）。
找細節用搜尋，不必整份讀。改完跑 python3 dev/check.py。完整規則：AI_HANDOFF_AND_TODO.md「本檔維護規則」的「歸檔放哪」。
整理到：2026-09-29
-->

> 現況、待決與待做以交接檔為準：[本檔維護規則（強制）](../../AI_HANDOFF_AND_TODO.md#本檔維護規則強制)。
> 這裡是歷史。上半部是整理過的重點；「原文」是當時的紀錄，提到的檔名、函式、狀態可能已經改了。原文提到的 `TODO-completed.md` 是 2026-11-07 以前的單一歸檔檔，內容都拆到 `dev/` 了，從 [dev/README.md](../README.md) 找。

## 一頁看懂

這個檔記交接檔的兩次整理：清掉已經做完或不再適用的待辦，以及共用元件索引搬到 `AGENTS.md` 後留下的合法例外。

- **09-28 清待辦**：從 `AI_HANDOFF_AND_TODO.md` 各區塊移出三類單項待辦。ComfyUI 產圖的步驟 2（租約鎖＋卸載 helper）09-03 已在 `e13343d` 完成；插話 Phase B「認得人」已實作；Ollama 時代的觀察項因為後端換成 Lemonade，不再適用。
- **09-29 共用元件表搬家**：共用元件表改放 `AGENTS.md`「共用元件」，由 `src/test/test_shared_conventions.py` 守衛；交接檔的舊索引只留合法例外的緣由。
- **四個合法例外**：形狀不同、硬收斂反而更糟，寫進守衛的 allowlist——scraper 的時區（`extract_fingerprint.py`）、`emoji_text_utils._load_descriptions`、`ambient_reply._load_ambient_prompt`、`llm_service._load_runtime_config_cached`。

**歸檔時（09-29）的狀態**

- [x] 交接檔裡已做完或不再適用的單項待辦移出（09-28）
- [x] 共用元件表搬到 `AGENTS.md`，由 `test_shared_conventions.py` 守衛（09-29）
- [x] 四個合法例外寫進守衛的 allowlist，緣由留在這裡
- [ ] ComfyUI 產圖的步驟 3～4，當時還留在交接檔

最新狀況看交接檔。

## 時間線

| 日期 | 發生什麼 | 結果 |
|---|---|---|
| 09-03 | ComfyUI 產圖步驟 2（租約鎖＋卸載 helper），一併把三處 `keep_alive` 的註解改成如實描述 | 完成（`e13343d`）；`keep_alive` 參數保留，只改註解 |
| 09-28 | 清理交接檔裡過時的單項待辦 | 移出 ComfyUI 步驟 2、插話 Phase B「認得人」、Ollama 時代的觀察項；ComfyUI 步驟 3～4 留在交接檔 |
| 09-29 | 共用元件表搬到 `AGENTS.md`「共用元件」 | 由 `test_shared_conventions.py` 守衛；舊索引只留四個合法例外的緣由 |

## 定案與理由

| 決定 | 為什麼 |
|---|---|
| 共用元件表改放 `AGENTS.md`，由 `src/test/test_shared_conventions.py` 守衛 | （原文沒寫理由） |
| `scraper/tools/extract_fingerprint.py` 的時區寫法列為合法例外 | scraper 是獨立容器（掛 `./src/scraper` → `/app`），看不到根目錄的 `sys_settings`；兩邊都吃 compose 的 `TZ=Asia/Taipei` |
| `emoji_text_utils._load_descriptions` 用永久快取＋明確的 `reload_descriptions()`，列為合法例外 | 字典是 04:00 排程改寫後主動重載，不是靠 mtime 輪詢 |
| `ambient_reply._load_ambient_prompt` 列為合法例外 | 多檔疊層，有自己的組裝順序 |
| `llm_service._load_runtime_config_cached` 列為合法例外 | 讀的是 pydantic 設定物件，錯誤處理不同 |
| 插話認得人：`ambient_reply` 接 `retrieve_rag_context_sync`，只傳 id | 吃純 id，不需要重構 interaction |
| 在場成員的 persona 每個頻道短快取（約 60 秒） | 避免 armed 期間每則訊息都打 pgvector |
| embedding 走 Lemonade 的獨立 port | 不卸載 12B，沒有 swap 風險 |

## 踩過的坑

- **Ollama 時代：`OLLAMA_KEEP_ALIVE=5m` 讓模型每 5 分鐘反覆卸載、載入**：原文認為這是 Windows `wsarecv`／ephemeral port 耗盡的主因，待辦是改成 24h，重啟 Ollama 後確認 `server.log` 不再每 5 分鐘一次 `load request`。這項當時沒打勾；後端換成 Lemonade 後不再適用。
- **三處 `keep_alive` 的註解原本寫得不實**：09-03 隨 ComfyUI 步驟 2 改成如實描述，參數保留、只改註解。

## 原文

新的在前。每段標題下面是摘要，正文在「展開原文」裡。

| 日期 | 段落 | 摘要 |
|---|---|---|
| 2026-09-29 | [共用元件索引搬到 AGENTS.md](#共用元件索引已搬到-agentsmd歸檔-2026-10-02) | 09-29 起共用元件表在 `AGENTS.md`、由守衛把關；這裡只留四個寫進 allowlist 的合法例外與緣由。 |
| 2026-09-28 | [交接檔過時待辦清理（09-28）](#過時待辦清理歸檔-2026-09-28) | 從交接檔移出已做完或不再適用的待辦：ComfyUI 步驟 2、插話認得人、Ollama 時代的觀察項。 |

## 共用元件索引（已搬到 AGENTS.md）（歸檔 2026-10-02）

> 09-29 起共用元件表在 `AGENTS.md`、由守衛把關；這裡只留四個寫進 allowlist 的合法例外與緣由。
>
> 關鍵字：共用元件索引、合法例外、extract_fingerprint、_load_descriptions、_load_runtime_config_cached

<details>
<summary>展開原文（約 622 字）</summary>

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

</details>

## 過時待辦清理（歸檔 2026-09-28）

> 從交接檔移出已做完或不再適用的待辦：ComfyUI 步驟 2、插話認得人、Ollama 時代的觀察項。
>
> 關鍵字：ComfyUI 步驟 2、keep_alive 註解、插話 Phase B 認得人、Ollama 時代觀察項

<details>
<summary>展開原文（約 1,247 字）</summary>

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

</details>
