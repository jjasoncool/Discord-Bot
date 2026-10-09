"""工具呼叫的訊息格式（`llm/client/tool_calls.py`）：人格萃取的 agent 與 /askai 的情報搜尋共用。

守的底線：
  - 模型要呼叫工具的那則 assistant 訊息原樣放回（含 tool_calls），工具結果用 `role: tool` 對上同一個 tool_call_id
  - 參數不是合法 JSON object 時丟 `ToolArgumentError`，訊息可以原文回給模型修正；有的後端直接給 dict 也收
  - 幾組工具合成一組（`combine_runners`）：宣告照順序接、規則依序接（空的略過）、呼叫交給宣告它的那一組；
    沒有工具的那組連規則一起略過；都沒有回 None、只剩一組回它本身；名稱重複直接報錯
  - 守衛：別處自己組 `role: tool` 或帶 tool_call_id 的 dict 會被擋

執行：
    cd src && python -m unittest test.test_tool_calls -v
"""

import asyncio
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from llm.client.tool_calls import (  # noqa: E402
    ToolArgumentError,
    assistant_message,
    call_name_and_arguments,
    combine_runners,
    parse_arguments,
    tool_message,
)
from test.test_shared_conventions import _find_tool_call_messages  # noqa: E402

CALL = {"id": "call_1", "type": "function", "function": {"name": "search", "arguments": '{"query": "深塔"}'}}


class ToolCallMessageTests(unittest.TestCase):
    def test_round_trip_keeps_the_call_id(self):
        self.assertEqual(assistant_message("", [CALL]), {"role": "assistant", "content": "", "tool_calls": [CALL]})
        self.assertEqual(tool_message(CALL, '{"results": []}'),
                         {"role": "tool", "tool_call_id": "call_1", "name": "search", "content": '{"results": []}'})

    def test_name_and_arguments(self):
        self.assertEqual(call_name_and_arguments(CALL), ("search", '{"query": "深塔"}'))
        self.assertEqual(call_name_and_arguments({"id": "x"}), ("", "{}"))

    def test_arguments_are_parsed_or_rejected_with_a_readable_reason(self):
        self.assertEqual(parse_arguments('{"query": "深塔"}'), {"query": "深塔"})
        self.assertEqual(parse_arguments({"query": "深塔"}), {"query": "深塔"})   # 有的後端直接給 dict
        self.assertEqual(parse_arguments(""), {})
        for bad, reason in (("{壞掉", "不是合法 JSON"), ("[1, 2]", "JSON object")):
            with self.subTest(bad=bad), self.assertRaises(ToolArgumentError) as ctx:
                parse_arguments(bad)
            self.assertIn(reason, str(ctx.exception))


def declare(name):
    return {"type": "function", "function": {"name": name, "description": name, "parameters": {}}}


class FakeTools:
    def __init__(self, names, instructions=""):
        self.tools = [declare(n) for n in names]
        self.instructions = instructions
        self.executed = []

    async def execute(self, name, arguments):
        self.executed.append((name, arguments))
        return f"{name} 的結果"


class CombineRunnersTests(unittest.TestCase):
    def test_tools_rules_and_calls_go_to_the_right_set(self):
        intel = FakeTools(["search", "fetch"], "【情報規則】")
        web = FakeTools(["web_search"], "【網路規則】")

        combined = combine_runners(intel, web)

        self.assertEqual([t["function"]["name"] for t in combined.tools], ["search", "fetch", "web_search"])
        self.assertEqual(combined.tools, combined.tools)                    # 每輪同一份
        self.assertEqual(combined.instructions, "【情報規則】\n\n【網路規則】")
        self.assertEqual(asyncio.run(combined.execute("web_search", '{"query": "颱風"}')), "web_search 的結果")
        self.assertEqual(asyncio.run(combined.execute("fetch", "{}")), "fetch 的結果")
        self.assertEqual(web.executed, [("web_search", '{"query": "颱風"}')])
        self.assertEqual(intel.executed, [("fetch", "{}")])

    def test_unknown_tool_is_an_error_for_the_model(self):
        combined = combine_runners(FakeTools(["search"]), FakeTools(["web_search"]))

        reply = json.loads(asyncio.run(combined.execute("weather", "{}")))

        self.assertIn("weather", reply["error"])
        self.assertIn("web_search", reply["error"])

    def test_missing_or_empty_sets_are_skipped_with_their_rules(self):
        web = FakeTools(["web_search"], "【網路規則】")

        self.assertIsNone(combine_runners())
        self.assertIsNone(combine_runners(None, FakeTools([], "【沒工具的規則】")))
        self.assertIs(combine_runners(None, web), web)
        combined = combine_runners(FakeTools(["search"], "  "), FakeTools([], "【沒工具的規則】"), web)
        self.assertEqual(combined.instructions, "【網路規則】")

    def test_duplicate_names_are_a_programming_error(self):
        with self.assertRaises(ValueError):
            combine_runners(FakeTools(["search"]), FakeTools(["search"]))


class GuardTests(unittest.TestCase):
    def test_handwritten_tool_messages_are_caught(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.py"
            path.write_text('a = {"role": "tool", "content": "x"}\nb = {"tool_call_id": "1"}\nc = {"role": "user"}\n',
                            encoding="utf-8")
            self.assertEqual(_find_tool_call_messages(path), [1, 2])


if __name__ == "__main__":
    unittest.main()
