"""插話上網查：琇紫判斷要不要插話的同一次生成裡，可以先查一次遊戲情報或網路，再決定要不要開口、講什麼。

架構定位：功能層（`llm/ambient`）。上層：`ambient_reply._gather_inputs`（準備工具）、`_generate`（交給模型）。
下層：`llm.retrievers.intel`（遊戲情報工具，連 search-mcp）、`llm.retrievers.web`（網路搜尋工具）、
`llm.persona.member_names`（名字檢查）、`llm.storage.member_profile_store`（自介與印象裡的暱稱）、
`utils.daily_quota`、`utils.hot_files`、`sys_settings.switches`。

介面：
- `mode()`：開關的值（off／dry_run）。
- `prepare(question, *, now, names, trace_id)`：開關開著、今天還有額度，就準備這次插話的那組工具（情報的 search＋
  web_search）；否則回 None（照原本的方式生成）。`names` 是取群友名字片段的 async 函式，第一次要檢查查詢字時才呼叫。
- `AmbientSearchTools`：交給 `LLMService.generate_reply(tool_runner=…)` 的那組工具；`records` 是這次查了什麼。
- `name_parts_for(guild, participant_ids)`：全伺服器成員的 Discord 名字加在場的人自介、印象裡的暱稱，切成比對片段。
- `NUDGE`、`RECORD_MODE_NOTE`：查滿時提醒模型的話、記錄模式回給模型的話。

規則：
- 自發、被 @、接續三種插話給一字不差的同一份宣告與規則，提示詞快取才只在上線與改規則時失效一次；額度用完
  當天整天不宣告（提示詞一天只變一次），不是宣告了再回錯誤（那樣照樣多跑一輪）。
- 同一次插話只執行第一個工具呼叫（共用迴圈會把同一輪的呼叫全執行，這裡擋）；情報只宣告 search、不宣告 fetch。
- web_search 的查詢字先過名字與識別碼檢查，擋下的不出網、記下原因；情報查詢只到本機的 search-mcp，不檢查。
- 記錄模式（dry_run）：檢查都做、額度照扣、每次呼叫記一行 log，但不呼叫內層工具、回模型固定的說明。
- 規則檔每次用 hot_files 讀、掛在這組工具上：掛在情報那組的話，search-mcp 一掉線規則就跟著消失。
- 例外只在這一層接：工具失敗回 `{"error": …}` 給模型，不讓整次插話中斷。

例外與決策：記錄模式完全不上網（不是「查了但不給結果」）——查詢字一送出就收不回來，而名字檢查實測會漏掉名字
黏著別的字的寫法（79 個名字片段漏 8 個），群裡私下叫的綽號也不在名單裡；先看過一週的紀錄確認沒把群友名字
送出去，再決定全開。查到的東西存起來、下次直接帶上（不再查）放第二版，用記錄週的真實查詢決定存法。
"""
from __future__ import annotations

import asyncio
import functools
import json
import logging
import time
from datetime import datetime
from typing import Any, Awaitable, Callable, Iterable, Optional

from llm.client.tool_calls import ToolArgumentError, parse_arguments
from llm.persona.member_names import member_names_from_guild, merge_names, name_parts, query_names_member
from llm.retrievers.intel import prepare_intel_session
from llm.retrievers.web import WebSearchTools
from llm.retrievers.web.tools import WEB_SEARCH_TOOL
from sys_settings import switches
from sys_settings.llm_settings import AmbientSearchSettings, AskAIIntelSettings, AskAIWebSettings
from utils import hot_files
from utils.daily_quota import DailyQuota

logger = logging.getLogger(__name__)

_SETTINGS = AmbientSearchSettings()
_WEB_SETTINGS = AskAIWebSettings()
#: 今天有查的插話次數（換日歸零；只在行程記憶體）
_QUOTA = DailyQuota(_SETTINGS.daily_limit)
_WEB_TOOL = WEB_SEARCH_TOOL["function"]["name"]
_INTEL_SEARCH = "search"

#: 查滿輪數還想查時提醒模型的話：系統口吻（自發插話看的是旁觀的對話，用 user 口吻說會被當成有人在跟它講話），
#: 並明講可以 [PASS]——/askai 那句「直接回答原本的問題」會把本該閉嘴的插話推向開口
NUDGE = ("（系統：這次不能再查了。請就手上的資料直接決定：自發插話沒把握就只輸出 [PASS]；"
         "被 @ 時用手上的資料簡短回，不熟就說不熟。）")
#: 記錄模式回給模型的話
RECORD_MODE_NOTE = ("這次不提供查詢結果。照你原本知道的判斷：自發插話沒把握就只輸出 [PASS]；"
                    "被 @ 就用手上的資料簡短回，不熟就說不熟。")

NamesProvider = Callable[[], Awaitable[Iterable[str]]]


def mode() -> str:
    return switches.current().ambient_search_mode


def max_tool_rounds() -> int:
    return _SETTINGS.max_tool_rounds


def _tool_name(tool: dict[str, Any]) -> str:
    return str((tool.get("function") or {}).get("name") or "")


class AmbientSearchTools:
    """一次插話的那組工具（`llm.client.tool_calls.ToolRunner`）。"""

    def __init__(self, *, mode: str, intel: Any, web: Any, names: NamesProvider, now: Callable[[], datetime],
                 settings: AmbientSearchSettings = _SETTINGS, trace_id: str = "-"):
        self.mode = mode
        self._intel = intel
        self._web = web
        self._names = names
        self._now = now
        self._settings = settings
        self._trace = trace_id
        self._parts: Optional[list[str]] = None
        self._calls = 0
        #: 這次插話每個工具呼叫的紀錄（工具、查詢字、判定、耗時）
        self.records: list[dict[str, Any]] = []

    @property
    def instructions(self) -> str:
        return hot_files.read_text(self._settings.rules_path, label="插話查詢規則")

    @property
    def tools(self) -> list[dict[str, Any]]:
        intel_tools = [t for t in (self._intel.tools if self._intel is not None else []) if _tool_name(t) == _INTEL_SEARCH]
        return [*intel_tools, *self._web.tools]

    async def execute(self, name: str, arguments: Any) -> str:
        started = time.perf_counter()
        self._calls += 1
        record: dict[str, Any] = {"tool": name, "arguments": str(arguments)[:300], "mode": self.mode, "query": ""}
        try:
            payload = await self._execute(name, arguments, record)
        except Exception as exc:  # 邊界：每個工具呼叫；失敗回給模型，不讓整次插話中斷
            logger.warning("ambient 查詢工具失敗 trace=%s tool=%s：%s: %s", self._trace, name, type(exc).__name__, exc)
            record["verdict"] = "failed"
            payload = {"error": f"這次查不到（{type(exc).__name__}），照你原本知道的判斷"}
        record["elapsed_ms"] = int((time.perf_counter() - started) * 1000)
        self.records.append(record)
        logger.info("ambient 查詢 trace=%s mode=%s tool=%s query=%r 判定=%s 耗時=%dms", self._trace, self.mode, name,
                    record["query"], record.get("verdict", "ok"), record["elapsed_ms"])
        return json.dumps(payload, ensure_ascii=False)

    async def _execute(self, name: str, arguments: Any, record: dict[str, Any]) -> dict[str, Any]:
        names = [_tool_name(t) for t in self.tools]
        if name not in names:
            record["verdict"] = "unknown_tool"
            return {"error": f"沒有名為 {name} 的工具；可用的是：{', '.join(names)}"}
        try:
            args = parse_arguments(arguments)
        except ToolArgumentError as exc:
            record["verdict"] = "bad_arguments"
            return {"error": str(exc)}
        query = str(args.get("query") or args.get("question") or "")
        record["query"] = query[:200]     # 只有 log 與紀錄截短；名字檢查看整段，不然後段的名字會漏
        if self._calls > 1:
            record["verdict"] = "second_call"
            return {"error": "這次插話只能查一次，請就手上的資料直接決定"}
        if not _QUOTA.take(self._now(), self._settings.daily_limit):
            record["verdict"] = "quota"
            return {"error": "今天的查詢額度用完了，請就手上的資料直接決定"}
        if name == _WEB_TOOL:
            reason = await self._names_in(query)
            if reason:
                record["verdict"] = f"blocked:{reason}"
                return {"error": f"查詢字裡有群友的名字或帳號（{reason}），這類不上網查；請就手上的資料直接決定"}
        if self.mode == "dry_run":
            record["verdict"] = "recorded"
            return {"results": [], "note": RECORD_MODE_NOTE}
        runner = self._web if name == _WEB_TOOL else self._intel
        payload = json.loads(await runner.execute(name, arguments))
        record["verdict"] = "error" if "error" in payload else "ok"
        return payload

    async def _names_in(self, query: str) -> Optional[str]:
        if self._parts is None:
            self._parts = list(await self._names())
        return query_names_member(query, self._parts)


async def prepare(question: str, *, now: Callable[[], datetime], names: NamesProvider, trace_id: str = "-",
                  settings: AmbientSearchSettings = _SETTINGS, intel_settings: Optional[AskAIIntelSettings] = None,
                  server: Any = None) -> Optional[AmbientSearchTools]:
    """開關開著、今天還有額度 → 這次插話的那組工具；否則 None。`question` 是觸發那則的原文（情報搜尋的重排要讀問句）。
    `server` 給單元測試用（同一個行程裡的 MCPServer）。"""
    current = mode()
    if current == "off":
        return None
    if _QUOTA.remaining(now(), settings.daily_limit) <= 0:
        logger.info("ambient 查詢：今天的 %d 次用完，這次不宣告工具 trace=%s", settings.daily_limit, trace_id)
        return None
    intel = None
    try:
        intel = await asyncio.wait_for(
            prepare_intel_session(question=question, settings=intel_settings, server=server),
            timeout=settings.intel_prepare_seconds,
        )
    except asyncio.TimeoutError:
        logger.warning("ambient 查詢：準備情報工具超過 %.0f 秒，這次只給網路搜尋 trace=%s",
                       settings.intel_prepare_seconds, trace_id)
    web = WebSearchTools(settings=_WEB_SETTINGS, instructions="")
    return AmbientSearchTools(mode=current, intel=intel, web=web, names=names, now=now, settings=settings,
                              trace_id=trace_id)


async def name_parts_for(guild: Any, participant_ids: Iterable[int]) -> frozenset[str]:
    """名字檢查用的片段：全伺服器成員的 Discord 名字，加上在場的人自介、印象裡的暱稱（查資料庫，丟執行緒）。"""
    discord_names = member_names_from_guild(guild)
    ids = [str(uid) for uid in participant_ids if uid]
    aliases: dict[str, list[str]] = {}
    if ids:
        from llm.storage.member_profile_store import get_member_profile_store
        try:
            aliases = await asyncio.get_running_loop().run_in_executor(
                None, functools.partial(get_member_profile_store().aliases_for_users,
                                        guild_id=getattr(guild, "id", None), user_ids=ids),
            )
        except Exception as exc:  # 邊界：查不到暱稱就只用 Discord 名字，不擋這次查詢
            logger.debug("ambient 查詢：讀自介、印象暱稱失敗：%s", exc)
    names = [n for uid, ns in discord_names.items() for n in merge_names(ns, (aliases or {}).get(uid, []))]
    return name_parts(names)
