"""Persona agent 執行迴圈的單元測試（hermetic：假 LLM、假 DB）。

驗證迴圈在各種模型行為下都收斂到明確狀態——agent 是黑箱，這些狀態就是之後
（M3 寫進 runs 表後）唯一能拿來除錯與統計失敗率的東西：

  ok / max_steps / rejected_schema / error

以及三件錯了很難察覺的事：
  ① 工具結果要以 `role:"tool"` + 正確的 `tool_call_id` 回填，否則模型接不上
  ② 收集階段 thinking 必須關、產出階段必須開（差距 12 分鐘 vs 3 分鐘／人）
  ③ 任何例外都要收斂成 status，不能往外拋（批次執行時單人失敗不該波及其他人）

執行：
    cd src && python -m unittest test.test_persona_agent_loop -v
"""

import asyncio
import json
import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from llm.persona_agent import agent, tools  # noqa: E402
from services.llm_service import ChatMessageResult  # noqa: E402

ALICE = "1001"
VALID_DIFF = json.dumps({
    "user_id": ALICE,
    "changes": [{
        "type": "add", "trait": "吐槽擔當", "text": "習慣用反話虧隊友",
        "reason": "現場對方跟著笑", "evidence_msg_ids": ["m1"],
    }],
    "confidence": "high",
    "notes": "",
}, ensure_ascii=False)


def tool_call(name, arguments, call_id="call_1"):
    return {"id": call_id, "type": "function",
            "function": {"name": name, "arguments": arguments}}


def says(content="", tool_calls=None):
    return ChatMessageResult(
        content=content, tool_calls=tool_calls or [],
        finish_reason="tool_calls" if tool_calls else "stop", usage={},
    )


class FakeService:
    """依序吐出預先排好的回應，並記錄每次呼叫的參數。"""

    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    async def chat_with_tools(self, **kwargs):
        # messages 是傳參考、迴圈會持續 append，直接存會拿到最終狀態而非「當下送出的內容」
        self.calls.append({**kwargs, "messages": [dict(m) for m in kwargs["messages"]]})
        if not self.script:
            return says(VALID_DIFF)
        nxt = self.script.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt


def fake_ctx(payload='{"messages": []}'):
    return tools.ToolContext.build(
        guild_id=1, allowed_ids=[ALICE], fetch=lambda sql, params: []
    )


def run(service, **kwargs):
    kwargs.setdefault("user_id", ALICE)
    kwargs.setdefault("ctx", fake_ctx())
    kwargs.setdefault("model", "test-model")
    return asyncio.run(agent.run_for_user(llm_service=service, **kwargs))


class HappyPathTests(unittest.TestCase):
    def test_collects_then_produces_diff(self):
        svc = FakeService([
            says(tool_calls=[tool_call("get_current_persona", '{"user_id": "1001"}')]),
            says(tool_calls=[tool_call("get_messages", '{"user_id": "1001", "days": 7}')]),
            says("看夠了"),          # 不再呼叫工具 → 跳出收集
            says(VALID_DIFF),        # 產出階段
        ])
        result = run(svc)
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.diff["changes"][0]["trait"], "吐槽擔當")
        self.assertEqual([t.tool for t in result.trace],
                         ["get_current_persona", "get_messages"])

    def test_tool_results_are_fed_back_with_call_id(self):
        svc = FakeService([
            says(tool_calls=[tool_call("get_messages", '{"user_id": "1001"}', "abc123")]),
            says("夠了"),
            says(VALID_DIFF),
        ])
        run(svc)
        # 第二次呼叫模型時，messages 必須已包含 assistant(tool_calls) + tool(結果)
        messages = svc.calls[1]["messages"]
        assistant = messages[-2]
        tool_msg = messages[-1]
        self.assertEqual(assistant["role"], "assistant")
        self.assertEqual(assistant["tool_calls"][0]["id"], "abc123")
        self.assertEqual(tool_msg["role"], "tool")
        self.assertEqual(tool_msg["tool_call_id"], "abc123")
        self.assertEqual(tool_msg["name"], "get_messages")

    def test_final_step_gets_a_longer_timeout(self):
        """產出步驟開 thinking 會吐數千推理 token，300 秒預設不夠。"""
        svc = FakeService([says("夠了"), says(VALID_DIFF)])
        run(svc)
        self.assertEqual(svc.calls[-1]["timeout"], agent.FINAL_TIMEOUT_SECONDS)
        self.assertNotIn("timeout", svc.calls[0])

    def test_collecting_never_thinks_and_producing_follows_the_switch(self):
        """收集階段一律關 thinking；產出階段跟著 `FINAL_STEP_THINKING`。

        產出階段預設也是關的——mock benchmark（四陷阱各兩次）顯示開關對品質沒有可測
        差異，開啟那組反而出現一次自相矛盾，代價卻是慢 4.5 倍；真實資料上更是三戰三敗
        （推理把 32k context 用光）。開關保留，日後想比較隨時能開。
        """
        svc = FakeService([
            says(tool_calls=[tool_call("get_messages", '{"user_id": "1001"}')]),
            says("夠了"),
            says(VALID_DIFF),
        ])
        run(svc)
        self.assertTrue(all(c["think"] is False for c in svc.calls[:-1]),
                        "收集階段必須關閉 thinking")
        self.assertIs(svc.calls[-1]["think"], agent.FINAL_STEP_THINKING,
                      "產出階段要跟著開關，不是寫死")
        self.assertIn("response_format", svc.calls[-1])
        self.assertNotIn("response_format", svc.calls[0])
        self.assertIn("tools", svc.calls[0])


class GuardrailTests(unittest.TestCase):
    def test_max_steps_still_produces_diff_but_flags_status(self):
        svc = FakeService(
            [says(tool_calls=[tool_call("get_messages", '{"user_id": "1001"}')])] * 3
            + [says(VALID_DIFF)]
        )
        result = run(svc, max_steps=3)
        self.assertEqual(result.status, "max_steps")
        self.assertIsNotNone(result.diff)
        self.assertEqual(result.steps, 3)

    def test_token_budget_stops_collection_early(self):
        big = '{"messages": [' + '"x"' * 4000 + ']}'
        svc = FakeService([
            says(tool_calls=[tool_call("get_messages", '{"user_id": "1001"}')]),
            says(VALID_DIFF),
        ])
        ctx = tools.ToolContext.build(
            guild_id=1, allowed_ids=[ALICE],
            fetch=lambda sql, params: [("m1", "c1", "2026-08-01T00:00:00+00:00", ALICE, big)],
        )
        result = run(svc, ctx=ctx, token_budget=100)
        self.assertEqual(result.steps, 1, "預算用盡後不該再收集")
        self.assertIsNotNone(result.diff)
        # 產出階段的提示要告知模型不能再撈資料
        self.assertIn("已達上限", svc.calls[-1]["messages"][-1]["content"])

    def test_unparsable_final_output_is_rejected(self):
        svc = FakeService([says("夠了"), says("這不是 JSON")])
        result = run(svc)
        self.assertEqual(result.status, "rejected_schema")
        self.assertIsNone(result.diff)
        self.assertIn("JSON", result.error)

    def test_llm_failure_becomes_status_not_exception(self):
        svc = FakeService([RuntimeError("backend wedged")])
        result = run(svc)
        self.assertEqual(result.status, "error")
        self.assertIn("RuntimeError", result.error)
        self.assertGreaterEqual(result.duration_ms, 0)


class ContextExceededTests(unittest.TestCase):
    """context 不足時直接放棄，不產出降級結果。

    第一版會裁掉舊的工具結果再重試，實測模型只剩空殼、卻回報一個格式正確、理由充分、
    confidence 標 low 的「資料不足」——假陰性，不看 trace 分不出來。批次任務明晚會重跑，
    沒有理由接受被削過的輸入。
    """

    class ContextError(Exception):
        detail = '{"error": {"message": "Context size has been exceeded."}}'

    def test_context_error_becomes_its_own_status(self):
        svc = FakeService([says("夠了"), self.ContextError("HTTP 500")])
        result = run(svc)
        self.assertEqual(result.status, "context_exceeded")
        self.assertIsNone(result.diff, "不得產出降級結果")

    def test_context_error_is_not_retried(self):
        svc = FakeService([self.ContextError("HTTP 500"), says(VALID_DIFF)])
        result = run(svc)
        self.assertEqual(result.status, "context_exceeded")
        self.assertEqual(len(svc.calls), 1, "不重試——重試等於送出被削過的輸入")

    def test_other_errors_still_map_to_error(self):
        svc = FakeService([RuntimeError("something else")])
        self.assertEqual(run(svc).status, "error")

    def test_fixed_overhead_counted_in_budget(self):
        """工具宣告每次呼叫都重送，不計入會系統性低估約 1,500 token。"""
        svc = FakeService([says("夠了"), says(VALID_DIFF)])
        result = run(svc)
        self.assertGreater(result.estimated_tokens, 800,
                           "起始預算至少要含 system prompt + 工具宣告")


class PromptLayeringTests(unittest.TestCase):
    """prompt 是三層疊加，不是自己複製一份。

    原本 agent 的 prompt 把角色設定、繁中限制、不編造、表情規則、描述品質規則全部
    重寫一遍，13 條核心規則與 production 萃取完全重疊——日後調整其中一邊會靜默分岔。
    這些測試守住「共用的是檔案」這個結構。
    """

    def test_system_prompt_contains_all_three_layers(self):
        sp = agent.load_prompts()["system_prompt"]
        self.assertIn("社群觀察專家", sp, "① 沿用萃取的角色設定")
        self.assertIn(":xxx:", sp, "① 沿用萃取的自訂表情規則")
        self.assertIn("嚴禁出現", sp, "② 沿用共用的描述品質規則")
        self.assertIn("互損型", sp, "③ agent 專屬的互損文化判讀")
        self.assertIn("get_conversation", sp, "③ agent 專屬的工具工作流")

    def test_agent_layer_does_not_duplicate_shared_rules(self):
        """agent 自己的檔案不該再抄一份共用規則。"""
        import json as _json
        from pathlib import Path

        own = _json.loads(
            Path("/app/settings/prompts/persona_agent_prompt.json").read_text(
                encoding="utf-8"
            )
        )
        layer = own["system_layer"]
        for duplicated in ("常用貼圖表達情感", ":xxx:", "只能使用繁體中文"):
            self.assertNotIn(
                duplicated, layer,
                f"「{duplicated}」屬於共用層，agent 層不該再抄一份",
            )

    def test_extraction_placeholder_is_substituted(self):
        """萃取那邊的 {description_rules} 必須代入——漏掉會把佔位符原樣送給模型。"""
        from llm.personality_extractor import (
            MAX_PERSONALITY_CHARS,
            _load_extract_prompts,
            load_description_rules,
        )

        rendered = (
            _load_extract_prompts()["user_prompt_template"]
            .replace("{description_rules}", load_description_rules())
            .replace("{max_chars}", str(MAX_PERSONALITY_CHARS))
        )
        self.assertNotIn("{description_rules}", rendered)
        self.assertIn("嚴禁出現", rendered)
        self.assertIn(f"不超過 {MAX_PERSONALITY_CHARS} 字", rendered)

    def test_description_rules_file_is_not_empty(self):
        from llm.personality_extractor import load_description_rules

        self.assertGreater(len(load_description_rules()), 50)


class ThinkingBudgetTests(unittest.TestCase):
    """thinking 需要 context 才想得完，而 prompt 與生成是共用同一個 32k。

    實測一次：prompt 22,379 + 推理 10,387 ＝ 32,766，`finish_reason=length`、
    `content` 全空——不是失敗，是「想太久，還沒開始寫答案就沒紙了」。
    純估算擋不住（當時估 14,501、實際 22,379），所以預算改以伺服器回報的
    `usage.prompt_tokens` 為準。
    """

    def test_budget_follows_server_reported_tokens(self):
        """伺服器回報的實際值要覆蓋估算，否則低估 1.5 倍還不自知。

        估算說「才幾十個 token」，伺服器說「已經 13,900」——以伺服器為準才會停手。
        """
        svc = FakeService([
            ChatMessageResult(
                content="", tool_calls=[tool_call("get_messages", '{"user_id": "1001"}')],
                finish_reason="tool_calls", usage={"prompt_tokens": 14200},
            ),
            says(VALID_DIFF),  # 預算用盡後直接進產出階段
        ])
        ctx = tools.ToolContext.build(
            guild_id=1, allowed_ids=[ALICE],
            fetch=lambda sql, params: [
                ("m1", "c1", "2026-08-01T00:00:00+00:00", ALICE, "字" * 100)
            ],
        )
        result = run(svc, ctx=ctx, token_budget=14000)
        # 伺服器說已 14,200（超過 14,000 預算）→ 批量工具被擋、本步無執行 → 停止收集
        self.assertEqual(result.steps, 1)
        self.assertIsNotNone(result.diff)
        self.assertIn("已達上限", svc.calls[-1]["messages"][-1]["content"])

    def test_falls_back_to_no_thinking_when_context_runs_out(self):
        """thinking 開著時才需要這條保底：輸入完全沒動，只是少了深思。

        與「裁掉資料再問」是兩回事——那個會產出假陰性，這個只是品質降一級且有旗標。
        """
        from services.llm_service import LLMAPIError

        svc = FakeService([
            says("夠了"),
            LLMAPIError("空 content 且無 tool_calls", kind="empty_content"),
            says(VALID_DIFF),
        ])
        with mock.patch.object(agent, "FINAL_STEP_THINKING", True):
            result = run(svc)
        self.assertEqual(result.status, "ok")
        self.assertTrue(result.thinking_exhausted, "必須標記，評測時要分開看")
        self.assertIsNotNone(result.diff)
        self.assertIs(svc.calls[-1]["think"], False, "重試要關掉 thinking")
        self.assertIs(svc.calls[-2]["think"], True, "第一次仍要開 thinking")

    def test_empty_content_is_a_real_error_when_thinking_is_off(self):
        """thinking 本來就關著還空 content → 是真的異常，不該吞掉當成「想太久」。"""
        from services.llm_service import LLMAPIError

        svc = FakeService([
            says("夠了"),
            LLMAPIError("空 content 且無 tool_calls", kind="empty_content"),
        ])
        result = run(svc)
        self.assertEqual(result.status, "error")
        self.assertFalse(result.thinking_exhausted)

    def test_other_api_errors_are_not_retried(self):
        from services.llm_service import LLMAPIError

        svc = FakeService([says("夠了"), LLMAPIError("無 choices", kind="no_choices")])
        result = run(svc)
        self.assertEqual(result.status, "error")
        self.assertFalse(result.thinking_exhausted)


class EstimateCalibrationTests(unittest.TestCase):
    """估算的自我校正。

    **這組測試存在的原因**：校正那段程式碼曾經引用一個沒被定義的常數，
    `py_compile` 抓不到（Python 執行期才解析名字）、300 個測試也全過——因為
    校正分支的條件（上一輪有 pending、伺服器回報有成長）在假資料裡從沒成立。
    真正執行時才 `NameError`。**沒被執行過的分支等於沒測。**
    """

    def _svc(self, usages):
        return FakeService([
            ChatMessageResult(
                content="",
                tool_calls=[tool_call("get_messages", '{"user_id": "1001"}')],
                finish_reason="tool_calls", usage={"prompt_tokens": u},
            )
            for u in usages
        ] + [says(VALID_DIFF)])

    def _ctx(self, chars):
        return tools.ToolContext.build(
            guild_id=1, allowed_ids=[ALICE],
            fetch=lambda sql, params: [
                ("m1", "c1", "2026-08-01T00:00:00+00:00", ALICE, "字" * chars)
            ],
        )

    def test_calibration_branch_actually_runs(self):
        """最基本的一條：走得到那段程式碼，不會 NameError。"""
        result = run(self._svc([1000, 3000]), ctx=self._ctx(200), token_budget=99999)
        self.assertIn(result.status, ("ok", "max_steps"))
        self.assertIsNotNone(result.diff)

    def test_scale_is_computed_from_the_observed_growth(self):
        """伺服器說長了 2,000、我們只估了幾百 → 係數應該被放大到上限。

        直接驗係數本身，不去推測步數——步數受預算、search 保留額度、假資料長度
        多個門檻交互影響，斷言步數只會測到我自己的算術。
        """
        with self.assertLogs("discord_bot", level="INFO") as logs:
            run(self._svc([1000, 3000]), ctx=self._ctx(200), token_budget=99999)
        calib = [m for m in logs.output if "估算校正" in m]
        self.assertTrue(calib, "校正分支必須真的被執行到")
        lo, hi = agent.ESTIMATE_SCALE_RANGE
        self.assertIn(f"係數 {hi:.2f}", calib[0],
                      "低估近 10 倍 → 係數應被夾在上限")

    def test_scale_is_clamped(self):
        """單次異常不該把係數帶到離譜的值。"""
        lo, hi = agent.ESTIMATE_SCALE_RANGE
        self.assertGreaterEqual(lo, 1.0)
        self.assertLessEqual(hi, 10.0)


class SearchReserveTests(unittest.TestCase):
    """預算用盡後仍要放行 search_messages。

    實測：模型在最後一步搜「PY」「米拉」「機械」——問題問得完全正確，卻正好撞上預算
    用盡，三個都回佔位字串，只好寫「無法確認」。但那些詞在 14 天內都還在（PY 出現
    14 次）。search 回傳小、是查證用的，不該跟批量撈資料搶同一份額度。
    """

    def _svc(self, tool_name):
        return FakeService([
            ChatMessageResult(
                content="", tool_calls=[tool_call(tool_name, '{"user_id": "1001", "keyword": "PY"}')],
                finish_reason="tool_calls", usage={"prompt_tokens": 12500},
            ),
            says(VALID_DIFF),
        ])

    def _ctx(self):
        return tools.ToolContext.build(
            guild_id=1, allowed_ids=[ALICE],
            fetch=lambda sql, params: [
                ("m1", "c1", "2026-08-01T00:00:00+00:00", ALICE, "PY")
            ],
        )

    def test_search_runs_past_the_budget(self):
        svc = self._svc("search_messages")
        result = run(svc, ctx=self._ctx(), token_budget=12000)
        payload = result.trace[0].result_preview
        self.assertNotIn("已達本次資料上限", payload, "search 應該走保留額度被放行")

    def test_bulk_tools_still_blocked(self):
        svc = self._svc("get_messages")
        result = run(svc, ctx=self._ctx(), token_budget=12000)
        self.assertIn("已達本次資料上限", result.trace[0].result_preview,
                      "批量工具沒有保留額度，照樣要擋")


class FailureCountingTests(unittest.TestCase):
    """連續失敗計數不該把「資料不足」算成失敗。

    話少的人本來就會 `confidence=low`。把它算成失敗，預算會一路降 70% → 50% →
    第三次隔離——而他們正是最需要多撈資料的族群，方向剛好相反。
    """

    def test_low_confidence_is_not_a_failure(self):
        from llm.persona_agent.store import _is_failure

        self.assertFalse(_is_failure("ok", None))
        self.assertFalse(
            _is_failure("ok", "confidence=low（模型自認資料不足，不寫入新版本）"),
            "資料不足是合法結果，不是失敗",
        )

    def test_real_problems_still_count(self):
        from llm.persona_agent.store import _is_failure

        self.assertTrue(_is_failure("ok", "沒有任何一項通過驗證"))
        self.assertTrue(_is_failure("error", None))
        self.assertTrue(_is_failure("context_exceeded", None))
        self.assertTrue(_is_failure("max_steps", None))


class BlockingCallTests(unittest.TestCase):
    """`run_and_persist` 是 async，裡面的同步 DB 呼叫必須走 executor。

    `store` 與 `validation` 走同步 psycopg2；直接在 async 裡呼叫會卡住整個 event loop
    （音樂、Discord 心跳、插話全停）。M4 批次跑 10 人就是 60 次阻塞。
    掃 AST 而不是靠人記得——這種錯誤不會報錯，只會讓 bot 間歇性卡頓。
    """

    def test_no_bare_store_or_validation_call_in_async(self):
        import ast
        import inspect

        src = inspect.getsource(agent.run_and_persist)
        tree = ast.parse(src.lstrip())
        offenders = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            if (
                isinstance(fn, ast.Attribute)
                and isinstance(fn.value, ast.Name)
                and fn.value.id in ("store", "validation")
            ):
                offenders.append(f"{fn.value.id}.{fn.attr} (line {node.lineno})")
        self.assertEqual(
            offenders, [],
            f"這些同步 DB 呼叫沒有走 executor，會卡住 event loop：{offenders}",
        )


class DispatchTests(unittest.TestCase):
    """模型填錯東西時，要回錯誤 JSON 讓它自行修正，而不是中斷 loop。"""

    def test_unknown_tool(self):
        payload = json.loads(tools.dispatch(fake_ctx(), name="get_everything", arguments="{}"))
        self.assertIn("error", payload)
        self.assertIn("get_messages", payload["error"])

    def test_malformed_arguments_json(self):
        payload = json.loads(
            tools.dispatch(fake_ctx(), name="get_messages", arguments="{user_id: 1001")
        )
        self.assertIn("error", payload)

    def test_unexpected_keyword(self):
        payload = json.loads(tools.dispatch(
            fake_ctx(), name="get_messages",
            arguments='{"user_id": "1001", "sort_by": "vibes"}',
        ))
        self.assertIn("error", payload)
        self.assertIn("參數不符", payload["error"])

    def test_routes_to_the_right_tool(self):
        payload = json.loads(tools.dispatch(
            fake_ctx(), name="get_messages", arguments='{"user_id": "1001", "days": 3}'
        ))
        self.assertEqual(payload["days"], 3)


class ToolDefinitionTests(unittest.TestCase):
    def test_all_four_tools_declared_and_dispatchable(self):
        names = [t["function"]["name"] for t in tools.TOOL_DEFINITIONS]
        self.assertEqual(sorted(names), [
            "get_conversation", "get_current_persona", "get_messages", "search_messages",
        ])
        for name in names:
            self.assertIn(name, tools._TOOL_FUNCS, f"{name} 有宣告卻無法派發")

    def test_conversation_description_explains_why_it_matters(self):
        """描述是寫給模型看的：不強調「碎片讀不出語氣」，它會懶得呼叫這支。"""
        desc = next(
            t["function"]["description"] for t in tools.TOOL_DEFINITIONS
            if t["function"]["name"] == "get_conversation"
        )
        self.assertIn("語氣", desc)


if __name__ == "__main__":
    unittest.main()


class PromptFileLoaderTests(unittest.TestCase):
    """共用的 prompt 載入器（收斂掉三份一字不差的 mtime 快取實作）。"""

    def test_missing_file_is_not_fatal_for_text(self):
        from llm import prompt_files

        self.assertEqual(prompt_files.read_text("/nope/missing.txt"), "")

    def test_missing_file_returns_none_for_json(self):
        from llm import prompt_files

        self.assertIsNone(prompt_files.read_json("/nope/missing.json"))

    def test_cache_returns_same_object_until_mtime_changes(self):
        import os
        import tempfile

        from llm import prompt_files

        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False,
                                         encoding="utf-8") as fh:
            fh.write("第一版")
            path = fh.name
        try:
            self.assertEqual(prompt_files.read_text(path), "第一版")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("第二版")
            # mtime 解析度可能不足以區分連續兩次寫入 → 明確往前推
            stat = os.stat(path)
            os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
            self.assertEqual(prompt_files.read_text(path), "第二版", "改檔要即時生效")
        finally:
            os.unlink(path)
