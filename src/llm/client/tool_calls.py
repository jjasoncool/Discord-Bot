"""工具呼叫（tool calling）的訊息格式：模型要求呼叫工具時那則 assistant 訊息、工具跑完回給模型的
`role: tool` 訊息、以及從模型給的 tool_call 取出名稱與參數。

OpenAI 相容 API 的協議：模型回 `tool_calls` 後，下一輪的 messages 要先放回那則 assistant 訊息（含
tool_calls），再對**每個** tool_call_id 各回一則 `role: tool`——少一則或 id 對不上，後端會拒絕或模型會亂掉。
這份格式只寫一次：人格萃取的 agent 與 /askai 的情報搜尋都用這裡；迴圈怎麼跑、預算怎麼算、工具怎麼執行，
留給各自的呼叫端。幾組工具要一起交給同一個工具輪時用 `combine_runners`（/askai 的遊戲情報＋網路搜尋）。
"""
from __future__ import annotations

import json
from typing import Any, Optional, Protocol


class ToolRunner(Protocol):
    """給模型用的一組工具：宣告（OpenAI 格式）、怎麼用的規則（接在系統提示詞後面，可以是空字串）、執行。
    執行失敗也要回字串（例如 `{"error": ...}`），不往外丟。"""

    instructions: str

    @property
    def tools(self) -> list[dict[str, Any]]:
        ...

    async def execute(self, name: str, arguments: Any) -> str:
        ...


class _CombinedTools:
    """幾組工具合成一組（見 `combine_runners`）。"""

    def __init__(self, runners: list[ToolRunner]):
        self._runners = runners
        self._owners: dict[str, ToolRunner] = {}
        for runner in runners:
            for tool in runner.tools:
                name = str((tool.get("function") or {}).get("name") or "")
                if name in self._owners:
                    raise ValueError(f"兩組工具都有名為 {name} 的工具，模型呼叫時分不出要交給誰")
                self._owners[name] = runner
        self.instructions = "\n\n".join(
            runner.instructions.strip() for runner in runners if (runner.instructions or "").strip()
        )

    @property
    def tools(self) -> list[dict[str, Any]]:
        return [tool for runner in self._runners for tool in runner.tools]

    async def execute(self, name: str, arguments: Any) -> str:
        runner = self._owners.get(name)
        if runner is None:
            return json.dumps({"error": f"沒有名為 {name} 的工具；可用的是：{', '.join(self._owners)}"},
                              ensure_ascii=False)
        return await runner.execute(name, arguments)


def combine_runners(*runners: Optional[ToolRunner]) -> Optional[ToolRunner]:
    """把幾組工具（例如遊戲情報與網路搜尋）合成一組，交給同一個工具輪：模型一次看到全部工具、自己決定查哪邊。

    宣告照傳入的順序接起來（每輪都是同一份，提示詞快取才吃得到）；使用規則依序接、空的略過；呼叫依名稱交給
    宣告它的那一組。None 與沒有工具的略過（沒有工具時規則也不給，免得模型被要求去查卻沒有工具）；
    都沒有回 None（照原本的方式回答），只剩一組就回它本身。名稱重複是寫程式的錯，直接丟 ValueError。
    """
    present = [runner for runner in runners if runner is not None and runner.tools]
    if not present:
        return None
    if len(present) == 1:
        return present[0]
    return _CombinedTools(present)


class ToolArgumentError(ValueError):
    """模型給的參數不是 JSON object。訊息是寫給模型看的，呼叫端照原文放進 `{"error": ...}` 回給它修正。"""


def assistant_message(content: str, tool_calls: list[dict[str, Any]]) -> dict[str, object]:
    """模型這一步要呼叫工具：原樣放回 messages，下一輪它才看得到自己要了什麼。"""
    return {"role": "assistant", "content": content, "tool_calls": tool_calls}


def call_name_and_arguments(call: dict[str, Any]) -> tuple[str, Any]:
    """一個 tool_call 的工具名稱與原始參數（通常是 JSON 字串；有的後端直接給 dict）。"""
    fn = call.get("function") or {}
    return str(fn.get("name") or ""), fn.get("arguments") or "{}"


def parse_arguments(arguments: Any) -> dict[str, Any]:
    """把模型給的參數轉成 dict；不是合法 JSON object 就丟 `ToolArgumentError`（不讓整個迴圈中斷）。"""
    if isinstance(arguments, str):
        try:
            parsed = json.loads(arguments or "{}")
        except json.JSONDecodeError as exc:
            raise ToolArgumentError(f"arguments 不是合法 JSON：{exc}") from exc
    else:
        parsed = arguments or {}
    if not isinstance(parsed, dict):
        raise ToolArgumentError("arguments 必須是 JSON object")
    return parsed


def tool_message(call: dict[str, Any], content: str) -> dict[str, object]:
    """工具的執行結果（或錯誤、佔位字串），對應回模型發出的那一個 tool_call。"""
    name, _ = call_name_and_arguments(call)
    return {"role": "tool", "tool_call_id": call.get("id"), "name": name, "content": content}
