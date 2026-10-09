"""工具呼叫的訊息格式（`llm/client/tool_calls.py`）：人格萃取的 agent 與 /askai 的情報搜尋共用。

守的底線：
  - 模型要呼叫工具的那則 assistant 訊息原樣放回（含 tool_calls），工具結果用 `role: tool` 對上同一個 tool_call_id
  - 參數不是合法 JSON object 時丟 `ToolArgumentError`，訊息可以原文回給模型修正；有的後端直接給 dict 也收
  - 守衛：別處自己組 `role: tool` 或帶 tool_call_id 的 dict 會被擋

執行：
    cd src && python -m unittest test.test_tool_calls -v
"""

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


class GuardTests(unittest.TestCase):
    def test_handwritten_tool_messages_are_caught(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.py"
            path.write_text('a = {"role": "tool", "content": "x"}\nb = {"tool_call_id": "1"}\nc = {"role": "user"}\n',
                            encoding="utf-8")
            self.assertEqual(_find_tool_call_messages(path), [1, 2])


if __name__ == "__main__":
    unittest.main()
