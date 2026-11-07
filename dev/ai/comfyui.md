# ComfyUI 產圖與 GPU 仲裁

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

> 現況、待決與待做以交接檔為準：[ComfyUI 產圖與 GPU 仲裁](../../AI_HANDOFF_AND_TODO.md#comfyui-產圖與-gpu-仲裁)。
> 這裡是歷史。上半部是整理過的重點；「原文」是當時的紀錄，提到的檔名、函式、狀態可能已經改了。原文提到的 `TODO-completed.md` 是 2026-11-07 以前的單一歸檔檔，內容都拆到 `dev/` 了，從 [dev/README.md](../README.md) 找。

## 一頁看懂

這個主題管每天 03:00 用 ComfyUI 產圖（AI 角色依心情、日期、節日換衣服），以及產圖時怎麼讓 LLM 讓出顯示卡（GPU 仲裁）。

- **09-02 實測**：兩張卡各 16GB，主模型跨兩張吃滿，產圖一定要先卸載 LLM。Lemonade 卸載後，下一次聊天會自動載回（22 秒），ctx 設定也不會被洗掉，所以出錯最壞只是下一次 /askai 慢 22 秒。
- **09-02 設計定案**：GPU 獨佔用「租約＋心跳」：租約 120 秒，每輪詢 ComfyUI 成功一次就續租；另設 03:50 整批截止，讓位給 04:00 維護。prompt 第一版走規則、不呼叫 LLM；圖發到日記頻道，不新增設定。同一天也修好一處用別名繞過時區守衛的寫法。
- **09-03**：租約鎖與卸載 helper 完成（`e13343d`）。
- **09-28 查證**：鎖有漏洞，聊天在排隊等鎖之前就先送 load，產圖期間會把主模型載回；ComfyUI 連不上。討論暫停，留下六個待決問題。
- **09-29～10-01**：`llm/` 依角色分子資料夾，四個檔名正名完成；Lemonade 升到 2026.40.0，重啟後設定保留。

**歸檔時（10-01）的狀態**

- [x] Lemonade 卸載與自動載回實測（09-02）
- [x] 租約鎖＋卸載 helper（09-03，`e13343d`）
- [x] `llm/` 四個檔名正名（09-29）
- [ ] 修鎖漏洞，把載入移進鎖內（產圖接進 bot 前必修）
- [ ] ComfyUI client、接 03:00 排程與發圖
- [ ] 六個待決問題：每天幾張誰挑、尺度、長相一致性、心情從哪來、產圖期間被 @ 怎麼回、ComfyUI 是否常駐與用哪張卡
- [ ] Lemonade 新版的「卸載後自動重載」與 `POST /free` 重測

最新狀況看交接檔。

## 時間線

| 日期 | 發生什麼 | 結果 |
|---|---|---|
| 09-02 | 線上實測 Lemonade 卸載與 ComfyUI | 卸載後打 chat 自動重載 22 秒；ctx 設定沒被洗掉；ComfyUI 看不到 Lemonade 佔的 VRAM |
| 09-02 | 產圖與 GPU 仲裁規劃定案 | 租約＋心跳、規則產 prompt、發到日記頻道；未開工 |
| 09-02 | `DIARY_TZ` 用別名繞過時區守衛 | 改用 `APP_TZ`；守衛從 regex 改成 AST，補 5 項測試 |
| 09-03 | 租約鎖＋卸載 helper | 完成（`e13343d`） |
| 09-28 | 查證狀態 | 發現鎖漏洞；ComfyUI 連不上（TCP 通、HTTP 被 reset）；討論暫停 |
| 09-29 | `llm/` 依角色分子資料夾 | 四個檔名正名完成；GPU 獨佔寫進 `AGENTS.md` 共用元件 |
| 10-01 | Lemonade 升到 2026.40.0 | 重啟後設定保留、收到請求自動載入；卸載後自動重載與 `POST /free` 還沒重測 |

## 定案與理由

| 決定 | 為什麼 |
|---|---|
| 產圖前一定卸載 LLM | 兩張卡各 16GB，主模型跨兩張吃滿，加上產圖塞不下；單張 16GB 放不下主模型，所以「LLM 釘一張、ComfyUI 用另一張」否決 |
| 不做「主動載回」和「背景預熱」 | 實測卸載後打 chat 會自動重載（22 秒） |
| GPU 獨佔用租約＋心跳，不用固定 timeout | timeout 分不出「跑很久」和「卡死」；輪詢 ComfyUI 本來就要做，輪詢成功就是心跳，租約長度跟產圖要跑多久無關 |
| 不另做 checker task | 多一個會自己掛掉的元件，而且最後還是得問 ComfyUI |
| 租約過期接管時要清載入快取，並記顯眼的 error | 不可靜默；清快取冪等，重複清沒有副作用 |
| 整批截止時間 03:50 | 04:00 有每日維護，產圖不能占著不放 |
| 不用 ComfyUI 的 `vram_free` 判斷夠不夠 | ComfyUI 看不到 Lemonade 佔的 VRAM，會寫出看似合理但永遠答錯的檢查 |
| 仲裁層與 `release_llm()` 介面不隨後端變，只有卸載的 adapter 每家一份 | 換後端可續用：Ollama 用 `keep_alive: 0`；vLLM 一個行程一個模型，做不到 |
| `keep_alive` 三處保留，只改註解（09-02 一度決定刪除，被使用者否決） | 它表達的是意圖，各後端能做多少是後端的事，刪了就沒有可攜性；註解裡有 Ollama 時代避開 Windows ephemeral port 與 runner crash 的教訓 |
| prompt 第一版走規則，不呼叫 LLM | ComfyUI 的 prompt 是 tag 語言，LLM 產的自由文字難控制、難重現；要用 LLM 就得排在卸載前、同在鎖內 |
| 圖發到日記頻道，不新增設定 | 該頻道成為「AI 的一天」的完整紀錄：00:00 寫日記 → 03:00 讀它決定心情 → 產圖發回同一處 |
| 心情來源要從新往回掃，找當天由 bot 發、有文字、沒附件的訊息 | 只讀最後一則，在當天日記沒發或有人留言時會抓錯 |
| ComfyUI 另開 `src/imagegen/`，不塞進 `llm/` | 塞了 `llm/` 就變成「AI 相關雜物間」 |
| `lemonade_gate` 等它真的管到 GPU 資源再改名 | 不然名字更騙人 |

## 踩過的坑

- **鎖有漏洞**：`_chat_completion_checked` 先 `_ensure_model_loaded` 才進 `stream_exclusive()`，產圖期間任何聊天都會在排隊前送 load，把主模型載回 VRAM。要把載入移進鎖內。
- **ComfyUI 看不到 Lemonade 佔的 VRAM**：Lemonade 走 Vulkan、ComfyUI 走 HIP，主模型在不在，`/system_stats` 都回報 free 15.78 GiB。
- **會自動載回，所以更怕漏網的請求**：一個背景插話就會把主模型拉回 VRAM 跟 ComfyUI 搶，實作時要確認沒有路徑繞過鎖直接打 LLM。
- **別名繞過 regex 守衛**：`DIARY_TZ = _tz(_td(hours=8))` 用 import 別名溜過；改成 AST 時也要注意 `timedelta(hours=8)` 當時間長度是合法的，不能誤判。
- **bot 在 Linux 容器裡拿不到 Windows 上的輸出資料夾**：只能走 HTTP 的 `GET /view` 取圖。
- **讀日記頻道最後一則會抓錯**：當天日記沒發會讀到前一天的圖，有人留言也會錯；往回掃也可能把「附件上傳失敗、退成純文字」的訊息誤認成日記。
- **測試檔說明跟現況矛盾**：`it_comfyui_image.py` 寫「與 Lemonade 綁不同 GPU」，和主模型跨兩張吃滿對不上，待使用者確認。

## 原文

新的在前。每段標題下面是摘要，正文在「展開原文」裡。

| 日期 | 段落 | 摘要 |
|---|---|---|
| 2026-09-29 | [已完成的待辦與檔名正名](#comfyui-區塊已完成的待辦與正名歸檔-2026-10-02原-2026-09-022026-09-29) | 圖發到日記頻道、修好別名繞過時區守衛（守衛改 AST），以及 llm/ 四個檔名正名。 |
| 2026-10-01 | [產圖與 GPU 仲裁設計](#comfyui-產圖與-gpu-仲裁09-02-實測租約加心跳設計keep_alive-取捨與-09-28-待決歸檔-2026-11-07原至-2026-09-02) | 09-02 實測卸載會自動載回、定案租約加心跳與規則產 prompt；09-28 查出鎖漏洞，六題待決。 |

## ComfyUI 區塊已完成的待辦與正名（歸檔 2026-10-02，原 2026-09-02／2026-09-29）

> 圖發到日記頻道、修好別名繞過時區守衛（守衛改 AST），以及 llm/ 四個檔名正名。
>
> 關鍵字：ai_diary_channel_id、DIARY_TZ 別名繞過、時區守衛改 AST、llm 檔名正名

<details>
<summary>展開原文（約 1,014 字）</summary>

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

</details>

## ComfyUI 產圖與 GPU 仲裁：09-02 實測、租約加心跳設計、keep_alive 取捨與 09-28 待決（歸檔 2026-11-07，原至 2026-09-02）

> 09-02 實測卸載會自動載回、定案租約加心跳與規則產 prompt；09-28 查出鎖漏洞，六題待決。
>
> 關鍵字：ComfyUI、產圖、gpu_gate、租約、心跳、release_model、unload、keep_alive、日記頻道、imagegen

<details>
<summary>展開原文（約 7,614 字）</summary>

> 從 `AI_HANDOFF_AND_TODO.md`「ComfyUI 產圖 + GPU 資源仲裁（2026-09-02 規劃定案，未開工）」區塊（`comfyui-gpu-arbitration`）瘦身前的完整原文；交接檔只留現況、規則與坑、未定案、待做。

> **2026-09-28 查證（本區塊部分狀態已過時）**
> - 實作順序的步驟 2（租約鎖 + 卸載 helper）**已完成**：`e13343d`（2026-09-03）。
> - ⚠️ **鎖有漏洞**：`services/llm_service.py` 的 `_chat_completion_checked` 先呼叫 `_ensure_model_loaded(model)`（:792），**之後**才 `async with stream_exclusive()`（:800）。產圖期間任何 chat 都會在排隊等鎖**之前**打 `POST /api/v1/load`，把 27B 載回 VRAM。產圖接進 bot 前必修。
> - ComfyUI 09-28 連不上（TCP 通、HTTP 被 reset），checkpoint／LoRA 清單未知。
> - Lemonade 已升到 **2026.40.0**（2026-10-01 約 10:3x）。升級重啟後 recipe 保留 ✅（27B `ctx_size 32768`、embedding `4096` 與各自 `llamacpp_args` 都在）、重啟後收到請求會自動載入 ✅；**unload 後自動重載**仍只在 11.5.0 測過，需要重測；`POST /free`（ComfyUI 放 VRAM）從未實測。
> - 04:00 維護現在是**五步**，收工約 05:46；Persona ⑤ 的 `publish_mode` 已是 `on`。
> - `src/test/integration/it_comfyui_image.py` 未 commit；它的 docstring 寫「與 Lemonade 綁不同 GPU」，與下方「27B 跨兩顆吃滿」矛盾，待使用者確認。
> - 落地前的待決問題見下方「待決問題（grill 暫停中）」。

**待決問題（grill 暫停中，2026-09-28；每題附當時的建議）**
- **頻道裡每天出現幾張、誰挑**：建議先跑兩週「產完放進只有管理員看得到的暫存區，按按鈕挑哪幾張發到日記頻道」，之後再考慮全自動。暫存區的「按鈕放行」跟 Telegram 隔離區的「放回主頻道」是同一種機制，做一次共用。
- **尺度**：建議嚴格全年齡——prompt 不放身材相關 tag、負面 prompt 放 nsfw 類、加全年齡 rating tag。身材設定只留在文字人設。
- **角色長相一致性**：建議先只靠 tag 上線，從產出挑一張「定裝照」，之後拿來當 IPAdapter 參考圖或練 LoRA 的素材。
- **心情從哪來**（會推翻「03:00 往回掃日記頻道」的定案）：建議 00:00 寫完日記後（LLM 還載著）多做一次分類，把心情歸到固定幾類存起來；03:00 仍然完全不用 LLM。理由：日記是含蓄散文，規則抽不準；往回掃也可能把「附件上傳失敗、退成純文字」的訊息誤認成日記。
- **產圖期間有人 @ 琇紫**：建議立刻回一句固定台詞（不經 LLM），例：「正在換衣服，等一下再聊」。目前的行為是一直等到產圖結束（最久 50 分鐘）才回。
- **只有使用者知道的事實**：ComfyUI 平常是否常駐（09-28 連不上）；ComfyUI 用哪張卡（測試檔 docstring 寫「與 Lemonade 綁不同 GPU」，與本區「27B 跨兩顆吃滿」矛盾）。

**不反對就照做的預設**：修鎖漏洞（任何會讓 Lemonade 載入模型的呼叫都要先拿鎖，把 `_ensure_model_loaded` 移進 `stream_exclusive`）；先確認 ComfyUI 活著且佇列是空的才拿租約、卸載 LLM，否則當天跳過；10 張拆成 10 個任務，每張 360 秒逾時，任一張逾時就中止整批並 `/interrupt`，已完成的照常處理；收工一律先 `POST /free` 讓 ComfyUI 釋放 VRAM 再放鎖（要跟 Lemonade 11.9.0 的三項實測一起驗證）；錯過 03:00 不補跑；節日表第一版手填未來兩年；embedding 小模型不卸載；`lemonade_gate` 改名 `gpu_gate`；圖檔名加日期並保留存檔。

**需求**：每天 **03:00** 排程產圖（特定角色換衣服，依心情／日期／節日決定），單次 10 張以內。
**不是 on-request**，使用者不會按著等。

**為什麼一定要卸載 LLM**（實測數字，不是推估）：兩張 RX 9060 XT **各 16GB**
（`vram_total 17,095,983,104`）；27B UD-Q4_K_XL + ctx 32768 本來就 `llamacpp_device: "Vulkan0,Vulkan1"`
跨兩顆吃滿。加上產圖，32GB 總量塞不下 → **卸載是唯一解**，不是保守選擇。
（曾考慮「把 LLM 釘單顆、ComfyUI 用另一顆並行」→ 單顆 16GB 放不下 27B，否決。）

### 線上實測結論（2026-09-02，對 `192.168.56.1:13305` Lemonade 11.5.0 / `:8188` ComfyUI 0.34.2）

| 測項 | 結果 |
|---|---|
| unload API | `POST /api/v1/unload {"model_name":"..."}` → `200 {"status":"success"}`，與 `/api/v1/load` 對稱 |
| 卸載生效 | health 的 `all_models_loaded` 中該 model 整個消失 |
| **卸載後打 chat 會自動重載** | **會**，22 秒（含冷載入）回 200 → **「主動載回」與「背景預熱」整段不需要** |
| recipe_options 是否被洗掉 | **沒有**。`ctx_size: 32768` 與全部 sampling args 原封不動（Lemonade 自己持久化在 `recipe_options.json`） |
| 二次呼叫 | 1.8 秒 / 36.7 tok/s → 確認常駐熱狀態 |
| ComfyUI 看不看得到 Lemonade 的 VRAM | **看不到**。27B 在與不在，`/system_stats` 都回報 free 15.78 GiB（Lemonade 走 Vulkan、ComfyUI 走 HIP，跨 process 查不到對方） |

**衍生結論**
1. `reset_lemonade_load_cache()` 從「必要」降級成「衛生」——Lemonade 自己記得 ctx_size，不清也不會錯；仍要清（模型卸載後「本 process 已推過 load options」的假設不成立），但**不再是單點故障**。
2. **整體風險很低**：租約過期／bot crash／鎖沒放好，最壞只是下一次 /askai 慢 22 秒，**沒有永久損壞路徑**。
3. **反過來**：正因為會自動載，「產圖期間絕不能有 LLM 請求漏進來」更要緊——一個漏網的背景插話就會把 27B 拉回 VRAM 跟 ComfyUI 搶。實作時要確認沒有任何路徑繞過鎖直接打 LLM。
4. **不可**用 ComfyUI 的 `vram_free` 判斷「現在夠不夠」——這條路提早封掉，否則會寫出看似合理但永遠答錯的檢查。

### 設計：租約 + 心跳（不是 timeout，也不是 checker task）

**核心：timeout 是猜的，心跳是量的。** 純 timeout 分不出「跑很久」與「卡死」——設太短誤殺正常長工作，設太長讓 bot 死著。

持有者拿**短期租約**（120s），每次證明還活著就續租。**續租點不用新造**：ComfyUI 的
`/queue`、`/history/{prompt_id}` 本來就要輪詢才知道圖好了沒，**輪詢成功即心跳**。

```python
async with gpu_exclusive("imagegen", lease=120) as lease:
    await unload_llm(chat_model)
    reset_lemonade_load_cache()
    while not done:
        await asyncio.sleep(5)
        status = await comfy.poll(prompt_id)   # 這一步成功 = 心跳
        lease.renew()
# 鎖釋放 → 下一個 LLM 請求進來，Lemonade 自動載回（22s）
```

- 正常跑 40 分鐘 → 續租 ~480 次，永不誤殺
- ComfyUI 卡死 → 輪詢失敗 → 120s 後租約到期 → 鎖自動釋放
- **租約長度與「產圖要跑多久」完全解耦**，只要比輪詢間隔長即可 → 不用猜任何時間
- 不做 checker task：多一個會自己掛掉的元件，而且它要判斷「還在跑嗎」最後還是得問 ComfyUI

**租約過期接管者不能只放鎖**：要順手 `reset_lemonade_load_cache()` + log 顯眼 error（不可靜默）。cache reset 冪等，重複清無副作用。

**兩種時限要分清楚**（不同東西，都要有）：

| | 管什麼 | 值 |
|---|---|---|
| 租約 | 卡死（liveness） | 120s，靠輪詢續 |
| 整批 deadline | 跑太久（budget） | **03:50**，護欄而非預算；正常 10 張幾分鐘就收工 |

deadline 存在的理由：**04:00 有每日維護四步**（emoji → 招牌梗 sweep → 人格萃取 → persona agent，跑到約 05:10），產圖不能占著不放。

### 換後端可續用（Ollama 可，vLLM 不可）

分三層，只有最薄一層要換：

| 層 | 內容 | 換後端要動嗎 |
|---|---|---|
| 仲裁層 | 租約／心跳／deadline／誰在佔用 | ❌ 完全不動（管的是 GPU 這個資源） |
| 意圖層 | `release_llm()` | ❌ 介面不動 |
| 後端 adapter | 怎麼實現該意圖 | ✅ 每後端一份，都很小 |

| 後端 | 卸載 | 載回 |
|---|---|---|
| Lemonade | `POST /api/v1/unload {"model_name":...}` | 不用做，下次 chat 自動載（22s） |
| Ollama | 一次 `{"keep_alive": 0}` 的請求（**原生卸載語意**） | 不用做，收到請求就載 |
| vLLM | ❌ 做不到（一 process 一模型、無 swap 概念） | — |

**`keep_alive` 三處保留，只改註解**（`llm_commands` "1h"、`impression_moderation_service` "30m"、
`personality_extractor` "30m"）。2026-09-02 曾一度決定刪除，**使用者否決且是對的**：它們確實在
Lemonade 下被 `_build_chat_extra_body` 丟進 ignored，但**那正是可攜層該有的行為**——`keep_alive`
表達的是意圖（「閒置多久可以放」），各後端能做到多少是後端的事；刪掉等於刪掉可攜性，和本節
「換後端可續用」的目標自相矛盾。而且 `llm_commands` 那則註解裡藏著 Ollama 時代的實戰教訓
（「避開反覆 unload/reload 觸發的 Windows ephemeral port 與 runner crash」），刪了下次換回 Ollama 會再踩一次。

要改的是**註解**，把「保證會發生」的口氣改成誠實描述。兩個機制互補、不是替代：

| | 語意 | 性質 | Lemonade | Ollama |
|---|---|---|---|---|
| `keep_alive` | 「閒置 N 分鐘後可以放」 | **軟提示**，後端能做就做 | 無 TTL 概念 → 忽略（已有 debug log） | ✅ 原生生效 |
| `release_llm()` | 「**現在馬上**放」 | **硬動作**，每後端一份 adapter | `POST /api/v1/unload` | `keep_alive: 0` |

### prompt 產生：v1 走規則，零 LLM 呼叫

素材三個來源都是現成的：

- **日期、節日** → `settings/` 一份 JSON 查表
- **心情** → **重用 00:00 的 AI 日記**。03:00 剛好在它之後，讀日記頻道最後一則即當天心情；
  頻道 id 也不用新設，`DiaryReflectionSettings.diary_channel_config_key` 已在 channel config 裡

不用 LLM 的理由不只是省事：① ComfyUI prompt 是 **tag 語言不是自然語言**，LLM 產的自由文字難控難重現；
② 一旦要 LLM，就得排在 unload 之前且同在鎖內，流程多一整段。
**v2 想換成 LLM 生 tag 時介面完全不用改**——差別只是「誰產出那串 tag」。

**發圖頻道＝日記頻道**（2026-09-02 使用者拍板）：沿用 `ai_diary_channel_id`
（`= DiaryReflectionSettings.diary_channel_config_key`，值 `1495609627361017867`），
**不新增任何設定**。該頻道因此成為「AI 的一天」的完整紀錄：00:00 寫日記 → 03:00 讀它決定心情 → 產圖發回同一處。

⚠️ **心情來源的定位規則不可以寫成「讀最後一則」**。正常時序雖然對（00:00 日記 → 03:00 圖，
03:00 當下最後一則就是當天日記），但兩種情況會抓錯：① 當天日記失敗沒發 → 讀到**前一天的圖**（無文字）；
② 有人在該頻道留言。正確規則：**從新往回掃，找「當天（`APP_TZ`）由 bot 發出、`content` 非空、
且無附件」的訊息**；找不到＝當天沒日記 → 心情來源缺席，退回純節日／日期規則。

（順帶：`diary_reflection` 目前是 `diary_channel.send(diary)` 直接發，沒走 `post_to_channel`。
產圖端仍走 `post_to_channel`；兩條路進同一個頻道是既有的小不一致，本案不處理，記在此備查。）

### 實作順序

1. ~~驗 `/api/v1/unload` 行為~~ ✅ 已完成（見上表）
2. `unload_llm()` adapter + gate 租約化（lease / renew / owner / busy 查詢 / 過期接管）
3. ComfyUI client：`POST /prompt` → 輪詢 `/history/{id}` → `GET /view` 取圖
   （bot 在 Linux container，**拿不到** Windows 的 `D:\AI\ComfyUI\...\output`，只能走 HTTP）
4. 接 03:00 排程 + 發圖
5. **最後**做檔名正名（見下）

**刻意重用既有輪子，不新造**
- workflow JSON 用 `llm.prompt.prompt_files.read_json()`（已有 mtime 快取，與 `settings/prompts/` 慣例一致）
- 發圖走 `utils.discord_content.post_to_channel`，不自己組 `channel.send`
- ~~實作完成後在「共用元件索引」補一行~~：GPU 獨佔（`lemonade_gate.gpu_exclusive`）已寫進 `AGENTS.md`「共用元件」（2026-09-29）

### TODO

- [ ] 步驟 3~4 實作（步驟 2 已在 `e13343d` 完成，已歸檔）
- [ ] **prompt 精修（使用者指定，後續要做）**：心情 ↔ 服裝的搭配表、節日表。v1 先能跑，映射規則之後細調

### 檔名正名（2026-09-29 隨 `llm/` 依角色分子資料夾完成四項；`lemonade_gate` 仍待定）

| 現在 | 改成 | import 點 |
|---|---|---|
| `llm/lemonade_gate.py`（現在位於 `llm/client/`） | 待定（`gpu_gate` / `resource_gate`）——**等它真的管到 GPU 資源再改**，否則名字更騙人 | 10 |

**已決定不做**：`llm/`、`services/` 的資料夾重組（成本 ~160 個 import 點，效益只有排序好看）。**2026-09-29 更新**：`llm/` 部分已由使用者推翻，改依角色分子資料夾（見[程式結構整理](#程式結構整理2026-09-29-起主要整理已完成剩-p2p3n3)）；`services/` 也在 2026-09-30 分成 relay／events／community。
子資料夾的判準是「≥6 檔／有封裝邊界／可預期會長」滿足其一——`persona_agent/`、`retrievers/web/`
是對的示範，其餘各群目前都不達標。**ComfyUI 另開 `src/imagegen/`，不塞進 `llm/`**（塞了 `llm/`
就變成「AI 相關雜物間」，重蹈 `services/` 覆轍）。

</details>
