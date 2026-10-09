"""工具呼叫（tool calling）的訊息格式：模型要求呼叫工具時那則 assistant 訊息、工具跑完回給模型的
`role: tool` 訊息、以及從模型給的 tool_call 取出名稱與參數。

OpenAI 相容 API 的協議：模型回 `tool_calls` 後，下一輪的 messages 要先放回那則 assistant 訊息（含
tool_calls），再對**每個** tool_call_id 各回一則 `role: tool`——少一則或 id 對不上，後端會拒絕或模型會亂掉。
這份格式只寫一次：人格萃取的 agent 與 /askai 的情報搜尋都用這裡；迴圈怎麼跑、預算怎麼算、工具怎麼執行，
留給各自的呼叫端。
"""
from __future__ import annotations

import json
from typing import Any, Protocol


class ToolRunner(Protocol):
    """給模型用的一組工具：宣告（OpenAI 格式）、怎麼用的規則（接在系統提示詞後面，可以是空字串）、執行。
    執行失敗也要回字串（例如 `{"error": ...}`），不往外丟。"""

    instructions: str

    @property
    def tools(self) -> list[dict[str, Any]]:
        ...

    async def execute(self, name: str, arguments: Any) -> str:
        ...


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
