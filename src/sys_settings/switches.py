"""功能開關：值放 `settings/switches.json`（使用者手改，改了下一次用到就生效、不用重啟），名稱、預設與允許的值定義在這裡。

**為什麼另開一個檔**：開關原本散在 config.json、sys_settings、環境變數、各種 runtime
檔，改了有的要重啟、有的要重建容器。開關集中一處、不做 Discord 指令，需要時直接改檔。不放進 config.json：那份
會被 Discord 存設定整份寫回，常切換的開關放進去容易被蓋掉。
- 細項參數（逾時、張數、門檻）仍在各自的 sys_settings 類別，重啟可接受。
- 之後改到哪個功能，就把它的開關搬進來（守衛擋新的開關放到別處）；還沒搬的列在 `test_shared_conventions` 的 `_LEGACY_SWITCH_FIELDS`。

**值寫錯時**：那一項記 warning 並用預設（其他項照用）；不認得的名稱也記 warning（多半是打錯字）；整份不是合法
JSON 時全部用預設並明講。檔案內以 `_` 開頭的 key 是說明文字，不會被當成開關：每個開關上面放一個
「_名稱 可以填」列出可填的值和意思（手改時不用回來翻程式），新增開關時一併加上。只在檔案修改後檢查一次、
檔案不見只記一次，不會每則訊息都洗 log。**任何寫錯都不會讓 bot 起不來**（啟動測試不驗這個檔）。
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from sys_settings.paths import SETTINGS_DIR
from typing import Literal

from pydantic import BaseModel, ConfigDict, TypeAdapter, ValidationError

logger = logging.getLogger(__name__)

#: 檔案不見的警告記過了沒（檔案回來就重置），避免每則訊息都記一次
_missing_warned = False

#: services/、sys_settings/ 都在 src/ 底下；開關檔跟 config.json 一樣是使用者會手改的設定
SWITCHES_PATH = SETTINGS_DIR / "switches.json"


class Switches(BaseModel):
    """每個開關一個欄位，預設值要選「關掉也安全」的那邊。"""

    model_config = ConfigDict(frozen=True)

    #: Telegram 轉發的 LLM 過濾（services.relay.telegram_filter）：off＝不判；dry_run＝判斷、寫 log、照常送主頻道；
    #: on＝判成垃圾的送進主頻道底下的「垃圾訊息」thread。開著（dry_run／on）時轉發一次只處理一則
    telegram_filter_mode: Literal["off", "dry_run", "on"] = "off"
    #: 插話頻道被點名、模型判斷是惡意辱罵（輸出 [INSULT]，llm.ambient.ambient_insult）：on＝按一個嘲諷表情、記下這個人，
    #: 之後幾天不主動接他的話；off＝不按、不記（標記照樣不送出去，等於不回）
    ambient_insult_mode: Literal["off", "on"] = "off"
    #: 情報搜尋（services.search，MCP 的 search 工具）加上向量（語意）搜尋：on＝關鍵字與向量的名次用 RRF 合併；
    #: off＝只用關鍵字。向量那邊壞掉時本來就會自動退回關鍵字；off 用在不想讓搜尋多打一次 embedding 的時候
    search_vector_mode: Literal["off", "on"] = "off"
    #: 情報搜尋的重新排序（reranker 把問題和每篇候選一起讀、重新打分）：on＝前幾十篇重排（llm_runtime_config.json
    #: 要設 rerank_model）；off＝不重排。reranker 壞掉、GPU 等太久時會自動照原本的順序
    search_rerank_mode: Literal["off", "on"] = "off"
    #: /askai 查遊戲情報（官網公告、官方 FB、PTT、巴哈；llm.retrievers.intel 連 search-mcp）：on＝讓模型自己決定要不要
    #: 先查、查什麼再回答；off＝跟原本一樣直接回答。search-mcp 沒開時本來就會自動不查
    askai_intel_search_mode: Literal["off", "on"] = "off"
    #: /askai 的網路搜尋（SearXNG，llm.retrievers.web）：keyword＝問題裡有時事類關鍵字就先查好、塞進 prompt（舊做法）；
    #: tool＝做成工具，由模型和遊戲情報一起決定查哪邊（兩邊不會同時塞資料）；off＝不查。預設照舊做法
    askai_web_search_mode: Literal["off", "keyword", "tool"] = "keyword"
    #: /askai 挑「相關」聊天訊息時的重排（和情報搜尋同一個 reranker）：on＝融合名次前 30 則連問題一起讀、重新打分，
    #: 每題多等一次 GPU（約 1～2 秒）；off＝照關鍵字＋向量融合的名次。reranker 壞掉、GPU 等太久時自動照原本的名次
    askai_rerank_mode: Literal["off", "on"] = "off"
    #: /askai 的聊天紀錄搜尋工具（llm.retrievers.chat_search）：on＝模型問到「誰說過／誰常說／之前有人提過」時自己決定查
    #: 全部頻道、所有時間的聊天紀錄（字面計數或語意），結果標頻道、名字、時間；off＝不給這個工具（只看頻道最近 100 則）
    askai_chat_search_mode: Literal["off", "on"] = "off"
    #: 聊天向量庫補寫（llm.storage.chat_index_backfill）：raw 備份有、聊天向量庫沒有的訊息（多半是停機前還在記憶體裡、
    #: 沒來得及寫的）定期補寫。off＝不查；dry_run＝查、記 log（幾則、會排幾則），不寫；on＝排進聊天記憶的寫入佇列。
    #: 預設 dry_run：只讀不寫，跟 off 一樣安全，又能先從 log 看到要補多少再決定切到 on
    chat_index_backfill_mode: Literal["off", "dry_run", "on"] = "dry_run"
    #: 插話上網查（llm.ambient.ambient_search）：琇紫判斷要不要插話的同一次生成裡，可以先查一次遊戲情報或網路。
    #: dry_run＝記錄模式：工具照宣告、名字檢查照做、額度照扣，但不出網、不給她結果，只記下她想查什麼（先確認沒把
    #: 群友名字送出去，再決定全開）；off＝不給工具，system 段跟原本一樣（user 段照樣帶今天日期）。全開（on）等記錄週
    #: 看過紀錄再加
    ambient_search_mode: Literal["off", "dry_run"] = "off"
    #: 聊天向量索引用哪種形狀（sys_settings.pgvector_settings.CHAT_INDEX_PROFILES；查詢的排序表達式要和資料庫裡的索引一致）：
    #: full＝整欄 1024 維、32 位元（索引約 2.2 GB）；halfvec512＝前 512 維、16 位元（約 0.5 GB，8 GB 主機才放得進快取）。
    #: 切之前先把對應的索引建好（建法在交接檔）；對不上只是退回全表掃描變慢，不會錯
    chat_vector_index: Literal["full", "halfvec512"] = "full"


def _parse(raw: str) -> Switches:
    try:
        data = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError as exc:
        logger.warning("功能開關檔不是合法的 JSON（%s），全部開關用預設（Telegram 過濾＝off）：%s", exc, SWITCHES_PATH)
        return Switches()
    if not isinstance(data, dict):
        logger.warning("功能開關檔最外層不是 JSON 物件，全部用預設：%s", SWITCHES_PATH)
        return Switches()
    fields = Switches.model_fields
    values = {}
    for key, value in data.items():
        if key.startswith("_"):
            continue
        if key not in fields:
            logger.warning("功能開關檔有不認得的名稱 %r（打錯字？），忽略：%s", key, SWITCHES_PATH)
            continue
        try:
            values[key] = TypeAdapter(fields[key].annotation).validate_python(value)
        except ValidationError:
            logger.warning("功能開關 %s 的值 %r 不合法，用預設 %r：%s", key, value, fields[key].default, SWITCHES_PATH)
    return Switches(**values)


def current() -> Switches:
    """目前的開關（檔案改了才重新解析）；沒有檔案或讀不到時全部用預設。"""
    global _missing_warned
    # 用到時才匯入：sys_settings 要能被 llm 底下的模組匯入（之後搬開關時），在模組層匯入 llm 會互相匯入
    from utils import hot_files

    value = hot_files.read_parsed(SWITCHES_PATH, parse=_parse, label="功能開關", missing_ok=True)
    if isinstance(value, Switches):
        _missing_warned = False
        return value
    if not _missing_warned:
        _missing_warned = True
        logger.warning("找不到功能開關檔（或讀不到），全部開關用預設（Telegram 過濾＝off）：%s", SWITCHES_PATH)
    return Switches()
