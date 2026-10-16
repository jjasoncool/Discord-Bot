"""`LLMService.generate_reply` 的工具輪（/askai 查情報）：模型自己決定要不要先查，再回答。

守的底線：
  - 不用查的問題只呼叫模型一次，設定和沒有工具時一樣（原本的思考設定、不限長度）
  - 要查：工具在兩次模型呼叫之間執行，結果用 `role: tool` 對上同一個 tool_call_id
  - 每一輪的思考設定、工具清單都一樣（切換思考開關或拿掉工具，提示詞快取就接不上）
  - 最多查 `max_tool_rounds` 輪；查滿還想查（就算順手寫了一句「讓我再查一下」）先提醒一次，再不行改用不帶工具的
    呼叫，保證有文字——那句開場白不能被當成回答送出
  - 第一次呼叫就被後端拒絕（例如不支援工具）或什麼都沒產出：改用不帶工具的呼叫，照原本的方式回答
  - 查過之後才失敗：照實回報錯誤（不改用沒查的回答），錯誤紀錄裡看得到已經查了什麼
  - 工具的使用規則只在有工具時接在系統提示詞後面；網路搜尋的指示知道這次有工具
  - 沒給工具、或工具清單是空的：跟原本一樣一問一答
  - 模型呼叫失敗：一樣回友善錯誤訊息（和沒有工具的路徑共用）
  - askai_prompt.txt 記到的內容包含工具呼叫與結果

執行：
    cd src && python -m unittest test.test_generate_reply_tools -v
"""

import os
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from llm.client.http_client import LlmTimeoutError  # noqa: E402
from services.llm_service import LLMAPIError  # noqa: E402
from llm.prompt.prompt_builder import PromptBundle  # noqa: E402
from services.llm_service import ChatMessageResult, LLMService  # noqa: E402

BUNDLE = PromptBundle(messages=[{"role": "system", "content": "你是 bot"}, {"role": "user", "content": "深塔多久重置？"}],
                      prompt_record_log="PROMPT")
TOOLS = [{"type": "function", "function": {"name": "search", "description": "搜", "parameters": {}}}]


def call(call_id, name="search", arguments='{"query": "深塔 重置"}'):
    return {"id": call_id, "type": "function", "function": {"name": name, "arguments": arguments}}


def wants(*calls):
    return ChatMessageResult(content="", tool_calls=list(calls), finish_reason="tool_calls", usage={})


def says(text, finish="stop"):
    return ChatMessageResult(content=text, tool_calls=[], finish_reason=finish, usage={})


class FakeRunner:
    def __init__(self, tools=TOOLS, instructions="【查詢規則】先查再答"):
        self.tools = tools
        self.instructions = instructions
        self.executed = []

    async def execute(self, name, arguments):
        self.executed.append((name, arguments))
        return '{"results": [{"id": "article:1", "title": "深塔兩週重置"}]}'


class GenerateReplyToolTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        svc = LLMService.__new__(LLMService)
        svc.context_safety_rules = None
        svc.settings = SimpleNamespace(latest_open_tag="<l>", latest_close_tag="</l>")
        svc._resolve_runtime_model = lambda model: "main-model"
        svc.resolve_request_think = lambda think=None: True
        self.model_calls = []
        self.replies = []

        async def chat_with_tools(**kwargs):
            self.model_calls.append({**kwargs, "messages": list(kwargs["messages"])})
            return self.replies.pop(0)

        svc.chat_with_tools = chat_with_tools
        svc.chat_raw = mock.AsyncMock(return_value="一般回答")
        self.svc = svc
        patcher = mock.patch("services.llm_service.build_prompt_bundle", return_value=BUNDLE)
        self.build = patcher.start()
        self.addCleanup(patcher.stop)

    async def ask(self, runner, **kwargs):
        return await self.svc.generate_reply(prompt="深塔多久重置？", system="你是 bot", tool_runner=runner, **kwargs)

    async def test_no_search_needed_is_a_single_call_with_the_normal_settings(self):
        self.replies = [says("正式回答")]
        runner = FakeRunner()

        result = await self.ask(runner)

        self.assertEqual(result.reply, "正式回答")
        (only,) = self.model_calls                                     # 不查就只問一次
        self.assertEqual(only["think"], True)
        self.assertIsNone(only.get("max_tokens"), "沒給上限就不限長度")
        self.assertEqual(only["messages"], BUNDLE.messages)
        self.assertEqual(runner.executed, [])
        self.assertEqual(result.prompt_record_log, "PROMPT")

    async def test_search_then_answer(self):
        self.replies = [wants(call("c1")), says("深塔每兩週重置。\n\n<https://example.com>")]
        runner = FakeRunner()

        result = await self.ask(runner)

        self.assertEqual(result.reply, "深塔每兩週重置。\n\n<https://example.com>")
        self.assertEqual(runner.executed, [("search", '{"query": "深塔 重置"}')])
        final = self.model_calls[-1]
        self.assertEqual(final["think"], True)
        self.assertEqual(final["messages"][-2]["tool_calls"][0]["id"], "c1")
        self.assertEqual(final["messages"][-1]["role"], "tool")
        self.assertEqual(final["messages"][-1]["tool_call_id"], "c1")
        self.assertIn("article:1", final["messages"][-1]["content"])
        self.assertEqual(result.messages_sent, final["messages"])
        self.assertIn("<tool_rounds>", result.prompt_record_log)
        self.assertIn("search", result.prompt_record_log)

    async def test_every_round_carries_the_same_tools_and_think_setting(self):
        self.replies = [wants(call("c1")), wants(call("c2", "fetch", '{"id": "article:1"}')), says("答")]

        await self.ask(FakeRunner())

        self.assertEqual(len(self.model_calls), 3)
        self.assertTrue(all(c["tools"] == TOOLS for c in self.model_calls))
        self.assertEqual([c["think"] for c in self.model_calls], [True, True, True])

    async def test_rounds_are_capped_then_nudged_then_answered_without_tools(self):
        self.replies = [wants(call("c1")), wants(call("c2")), wants(call("c3")), wants(call("c4"))]
        runner = FakeRunner()

        result = await self.ask(runner, max_tool_rounds=2)

        self.assertEqual(len(runner.executed), 2)                    # 只查 2 輪
        self.assertIn("不能再查了", self.model_calls[-1]["messages"][-1]["content"])
        self.assertEqual(result.reply, "一般回答")                   # 還是只想查 → 不帶工具的呼叫
        self.assertEqual(self.svc.chat_raw.await_args.kwargs["think"], True)

    async def test_a_preamble_with_more_tool_calls_is_not_sent_as_the_answer(self):
        self.replies = [wants(call("c1")), wants(call("c2")),
                        ChatMessageResult(content="讓我再查一下 3.2 的卡池。", tool_calls=[call("c3")],
                                          finish_reason="tool_calls", usage={}),
                        says("查到的整理")]

        result = await self.ask(FakeRunner(), max_tool_rounds=2)

        self.assertEqual(result.reply, "查到的整理")
        self.assertIn("不能再查了", self.model_calls[-1]["messages"][-1]["content"])

    async def test_blank_text_is_not_an_answer(self):
        self.replies = [wants(call("c1")), says("\n\n"), says("真的回答")]

        result = await self.ask(FakeRunner(), max_tool_rounds=1)

        self.assertEqual(result.reply, "真的回答")

    async def test_first_call_failing_falls_back_to_the_plain_answer(self):
        failures = {
            "後端拒絕": LLMAPIError("HTTP 500", status=500),
            "什麼都沒產出": LLMAPIError("回應格式異常: 空 content 且無 tool_calls", kind="empty_content"),
        }
        for label, failure in failures.items():
            with self.subTest(label):
                self.svc.chat_raw.reset_mock()

                async def chat_with_tools(failure=failure, **kwargs):
                    raise failure

                self.svc.chat_with_tools = chat_with_tools
                with self.assertLogs("services.llm_service", level="WARNING"):
                    result = await self.ask(FakeRunner())

                self.assertEqual(result.reply, "一般回答")
                self.assertIsNone(result.error_kind)
                plain = self.svc.chat_raw.await_args.kwargs
                self.assertEqual(plain["think"], True)
                self.assertNotIn("tools", plain)

    async def test_failure_after_searching_keeps_the_rounds_in_the_record(self):
        calls = {"n": 0}

        async def chat_with_tools(**kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                return wants(call("c1"))
            raise LlmTimeoutError("逾時")

        self.svc.chat_with_tools = chat_with_tools
        with self.assertLogs("services.llm_service", level="ERROR"):
            result = await self.ask(FakeRunner())

        self.assertEqual(result.error_kind, "timeout")
        self.assertEqual(result.messages_sent[-1]["role"], "tool")
        self.assertIn("<tool_rounds>", result.prompt_record_log)

    async def test_backend_error_after_searching_is_reported_not_answered_without_tools(self):
        calls = {"n": 0}

        async def chat_with_tools(**kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                return wants(call("c1"))
            raise LLMAPIError("HTTP 500", status=500)

        self.svc.chat_with_tools = chat_with_tools
        with self.assertLogs("services.llm_service", level="ERROR"):
            result = await self.ask(FakeRunner())

        self.assertEqual(result.error_kind, "http_error")              # 查到的資料不能被悄悄丟掉、改用沒查的回答
        self.svc.chat_raw.assert_not_awaited()
        self.assertEqual(result.messages_sent[-1]["role"], "tool")

    async def test_usage_rules_are_added_only_when_there_are_tools(self):
        self.replies = [says("答")]
        await self.ask(FakeRunner())
        with_tools = self.build.call_args.kwargs
        await self.ask(None)
        without = self.build.call_args.kwargs

        self.assertIn("【查詢規則】先查再答", with_tools["system"])
        self.assertTrue(with_tools["has_tools"])
        self.assertEqual(without["system"], "你是 bot")
        self.assertFalse(without["has_tools"])

    async def test_without_tools_it_is_a_single_plain_call(self):
        for runner in (None, FakeRunner(tools=[])):
            with self.subTest(runner=runner):
                self.model_calls.clear()
                result = await self.ask(runner)
                self.assertEqual(result.reply, "一般回答")
                self.assertEqual(self.model_calls, [])

    async def test_model_failures_become_the_usual_friendly_message(self):
        async def boom(**kwargs):
            raise LlmTimeoutError("逾時")

        self.svc.chat_with_tools = boom
        with self.assertLogs("services.llm_service", level="ERROR"):
            result = await self.ask(FakeRunner())

        self.assertEqual(result.error_kind, "timeout")
        self.assertTrue(result.reply.startswith("⚠️"))


class AnswerLengthCapTests(GenerateReplyToolTests):
    """回答長度上限（max_tokens）要一路帶到每一次模型呼叫：帶工具的每一輪、改用一般呼叫時都一樣；沒給就不送。"""

    async def test_max_tokens_reaches_every_model_call(self):
        runner = FakeRunner()
        self.replies = [wants(call("c1")), says("查完了：兩週重置")]
        with mock.patch("services.llm_service.build_prompt_bundle", return_value=BUNDLE):
            await self.svc.generate_reply(prompt="深塔多久重置？", tool_runner=runner, max_tokens=4096)
        self.assertEqual([4096, 4096], [c["max_tokens"] for c in self.model_calls])

    async def test_plain_answer_carries_the_cap_and_no_cap_means_unlimited(self):
        with mock.patch("services.llm_service.build_prompt_bundle", return_value=BUNDLE):
            await self.svc.generate_reply(prompt="深塔多久重置？", max_tokens=4096)
            self.assertEqual(4096, self.svc.chat_raw.await_args.kwargs["max_tokens"])
            await self.svc.generate_reply(prompt="深塔多久重置？")
            self.assertIsNone(self.svc.chat_raw.await_args.kwargs["max_tokens"])


class LengthErrorMessageTests(GenerateReplyToolTests):
    async def test_length_error_becomes_a_message_about_splitting_the_question(self):
        self.svc.chat_raw = mock.AsyncMock(side_effect=LLMAPIError("回答超過長度上限，沒有產出內容", kind="length"))
        result = await self.svc.generate_reply(prompt="深塔多久重置？", max_tokens=100)
        self.assertEqual("length", result.error_kind)
        self.assertIn("拆小", result.reply)


if __name__ == "__main__":
    unittest.main()
