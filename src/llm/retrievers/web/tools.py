"""網路搜尋（SearXNG）做成給模型用的工具：/askai 由模型自己決定要不要查、查什麼（開關 `askai_web_search_mode=tool`）。

為什麼改成工具：關鍵字模式會先把網路結果塞進 prompt，模型自己查的遊戲情報又是另一份，
兩邊說法不同時模型不知道該信誰。改成工具後，遊戲情報與網路搜尋在同一個工具輪裡（`combine_runners`）由模型挑，
先後與出處的規則寫在 `settings/prompts/askai_web_rules.txt`，只在有這個工具時才給模型。

  - 題目類型由模型選（`kind`：一般／新聞／天氣／匯率），不用關鍵字分類（關鍵字分不準：
    「台北今天幾度」被「今天」帶去新聞、「明天台北會下雨嗎」什麼都沒命中）。每種類型用哪些引擎、要不要限時間
    寫在 `_KINDS`：那是實測出來的引擎特性（例：新聞不限時間、照日期排，限一週會把最準的新聞引擎擋掉），不交給模型
  - 天氣、匯率走 SearXNG 內建的專用引擎，答案在 `answers`。查詢字先整理成引擎認得的樣子（天氣只留英文地名、
    匯率整理成「1 USD to TWD」）；引擎有跑卻沒答案才回寫法提示，引擎這次沒回應就照實說，不叫模型改寫
  - 查詢字只去掉「幫我查」這類贅字：模型寫的已經是關鍵字，不套用關鍵字模式給使用者原句用的新聞剝字（會切壞專有名詞）
  - 查詢與「窄路由結果太少換通用引擎補查」走 `search_web`，和關鍵字模式同一份
  - 任何失敗（參數錯、SearXNG 掛了、逾時）都轉成 `{"error": ...}` 回給模型，不讓整個回答中斷
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Optional

from llm.client.tool_calls import ToolArgumentError, parse_arguments
from utils import hot_files

from .intent import clean_query
from .search import search_web

logger = logging.getLogger(__name__)

#: 模型選的題目類型 → 怎麼查。新聞不限時間、結果照日期新到舊排（怎麼查、怎麼排在 `search._search_news`）；
#: 一般搜尋不限時間；天氣、匯率指定 SearXNG 的專用引擎（引擎名稱在 AskAIWebSettings）
_KINDS: dict[str, dict[str, Any]] = {
    "general": {},
    "news": {"categories": "news"},
    "weather": {"engines": "weather_engines", "language": "en", "label": "天氣",
                "hint": "天氣引擎沒找到這個地點：query 只寫英文地名（例：Taipei、Kaohsiung），不要加其他字"},
    "currency": {"engines": "currency_engines", "label": "匯率",
                 "hint": "匯率引擎沒看懂：query 寫成「1 USD to TWD」這種格式（金額不加逗號＋國際幣別代碼）"},
}
_CJK = re.compile(r"[\u3400-\u9fff]")
#: 天氣查詢裡不是地名的英文字（模型常順手寫 Taipei tomorrow weather）；地名查座標只認純地名
_NOT_PLACE = {"today", "tomorrow", "tonight", "now", "weather", "forecast", "this", "next", "week", "weekend",
              "rain", "temperature", "in", "the"}
_CURRENCY = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*([A-Za-z]{3})\s*(?:to|in|=|->)\s*([A-Za-z]{3})", re.IGNORECASE)


def _engine_query(kind: str, query: str) -> str:
    """把模型寫的查詢整理成專用引擎認得的樣子；其他類型原樣。整理不出來就原樣，讓引擎回沒答案、模型照提示改寫。"""
    if kind == "weather":
        words = [w for w in re.findall(r"[A-Za-z][A-Za-z.'-]*", query) if w.lower() not in _NOT_PLACE]
        return " ".join(words) or query
    if kind == "currency":
        match = _CURRENCY.search(query)
        if match:
            amount, source, target = match.groups()
            return f"{amount.replace(',', '')} {source.upper()} to {target.upper()}"
    return query

#: 宣告給模型的工具（名稱與說明是模型決定要不要查的依據）
WEB_SEARCH_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "web_search",
        # 不寫死「《鳴潮》以外」：情報工具不在時（開關關著、search-mcp 連不上）只剩這個工具，遊戲問題也要能查
        "description": (
            "一般網路搜尋。查需要即時或外部資訊的事：新聞時事、天氣、股價匯率、體育賽程比分、其他遊戲或軟體的消息、"
            "網路流行語或梗的意思。《鳴潮》的問題有 search（遊戲情報）時先用 search，沒有時也用這個查。"
            "回傳 answers（直接答案：天氣預報、匯率，有的話）與 results（標題、網址、摘要、日期）。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "空白分隔的主題關鍵字。weather 只寫英文地名（例：Taipei），不寫時間；"
                                   "currency 寫成「1 USD to TWD」；news 不用寫時間詞（結果照日期新到舊排）",
                },
                "kind": {
                    "type": "string",
                    "enum": list(_KINDS),
                    "description": "題目類型：news＝新聞時事；weather＝天氣預報；currency＝匯率換算；"
                                   "其他（股價、比分、其他遊戲或軟體、一般資訊）用 general。沒給就是 general",
                },
            },
            "required": ["query"],
        },
    },
}


class WebSearchTools:
    """一次 /askai 請求的網路搜尋工具（`llm.client.tool_calls.ToolRunner`）。"""

    def __init__(self, *, settings: Any, instructions: Optional[str] = None):
        # settings 是 AskAIWebSettings（以 Any 標記，和 searxng.py 一樣避免 circular import）
        self.settings = settings
        #: 怎麼用這個工具（接在系統提示詞後面，見 `LLMService.generate_reply`）
        self.instructions = (
            instructions if instructions is not None
            else hot_files.read_text(settings.rules_path, label="網路搜尋規則")
        )
        #: 這次請求呼叫過的工具與結果摘要（寫進 /askai 的回應紀錄）
        self.calls: list[dict[str, Any]] = []

    @property
    def tools(self) -> list[dict[str, Any]]:
        return [WEB_SEARCH_TOOL]

    async def execute(self, name: str, arguments: Any) -> str:
        """執行一個工具呼叫，回傳給模型的 JSON 字串；失敗也回 `{"error": ...}`，不往外丟。"""
        started = time.perf_counter()
        record: dict[str, Any] = {"tool": name, "arguments": str(arguments)[:300]}
        try:
            payload = await self._execute(name, arguments, record)
        except Exception as exc:
            logger.warning("網路搜尋工具失敗 tool=%s：%s: %s", name, type(exc).__name__, exc)
            payload = {"error": f"這次查不到（{type(exc).__name__}），請就手上的資料回答"}
        record["elapsed_ms"] = int((time.perf_counter() - started) * 1000)
        if "error" in payload:
            record["error"] = str(payload["error"])[:200]
        self.calls.append(record)
        return json.dumps(payload, ensure_ascii=False)

    async def _execute(self, name: str, arguments: Any, record: dict[str, Any]) -> dict[str, Any]:
        if name != WEB_SEARCH_TOOL["function"]["name"]:
            return {"error": f"沒有名為 {name} 的工具；可用的是：web_search"}
        try:
            args = parse_arguments(arguments)
        except ToolArgumentError as exc:
            return {"error": str(exc)}
        raw_query = str(args.get("query") or "").strip()
        if not raw_query:
            return {"error": "query 不能是空的：請給要查的關鍵字"}
        kind = str(args.get("kind") or "general").strip().lower()
        if kind not in _KINDS:
            return {"error": f"kind 只能是 {'／'.join(_KINDS)}"}
        route = _KINDS[kind]
        categories, time_range = route.get("categories"), route.get("time_range")
        engines = getattr(self.settings, route["engines"]) if "engines" in route else None
        query = _engine_query(kind, clean_query(raw_query))
        # 語系：天氣引擎只認英文地名；其他類型看查詢字有沒有中文——模型寫英文多半是國際題材，英文來源比較快、比較全
        language = route.get("language") or (None if _CJK.search(query) else "en")
        record.update(query=query, kind=kind,
                      route={"categories": categories, "time_range": time_range, "language": language, "engines": engines})

        outcome = await search_web(query, settings=self.settings, categories=categories, time_range=time_range,
                                   language=language, engines=engines, logger_override=logger)
        results = [
            {key: value for key, value in (
                ("title", hit.title), ("url", hit.url), ("snippet", hit.snippet),
                ("published_date", (hit.published_date or "")[:10]),
            ) if value}
            for hit in outcome.results
        ]
        record["result_count"] = len(results)
        record["result_urls"] = [hit.url for hit in outcome.results[:3]]
        record["answer_count"] = len(outcome.answers)
        if outcome.meta.get("fallback"):
            record["fallback"] = outcome.meta["fallback"]
        error = outcome.meta.get("error")
        if error and not results and not outcome.answers:
            return {"error": f"網路搜尋這次失敗（{error}），請就手上的資料回答"}
        if "hint" in route and not outcome.answers:
            # 引擎這次沒回應（逾時、被暫停）時寫法可能是對的，照實講，別叫模型改寫浪費一輪
            silent = [reason for name, reason in outcome.meta.get("unresponsive_engines") or []
                      if name in (engines or "").split(",")]
            if silent:
                return {"error": f"{route['label']}服務這次沒回應（{silent[0]}），請就手上的資料回答"}
            return {"answers": [], "results": results, "note": route["hint"]}
        # 直接答案（匯率、天氣、維基摘要）排在前面：數字型問題先看它，比網頁摘要準
        return {"answers": list(outcome.answers), "results": results} if outcome.answers else {"results": results}
