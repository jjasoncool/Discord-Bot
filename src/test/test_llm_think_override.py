"""思考開關與強度只在設定檔頂層設，送出前依後端翻成那家的寫法（`LLMService._build_chat_extra_body`
＋ `llm.client.backend_admin.chat_style_for`；hermetic，不碰檔案或網路）。

守的底線：
  1. 線上設定送出的 extra_body 與改之前一字不差（/askai、插話、人格萃取、探測都走這條路）。
  2. 思考開關：呼叫端指定的優先，否則照頂層 think；Lemonade、vLLM 寫成 chat_template_kwargs.enable_thinking，
     Ollama 不思考寫成 reasoning_effort=none。
  3. 思考強度：呼叫端指定的優先，否則照頂層 reasoning_effort；都沒有就不送（用模型模板的預設）。
  4. extra_body 裡舊寫法的思考設定、那家收不到的欄位（Ollama 的 options）不會送出，記一次警告；設定檔的快取物件不會被改到。
  5. 那家收不到的參數不送（Lemonade 的 keep_alive、num_ctx；Ollama 的 num_ctx、repeat_penalty）。

執行：
    cd src && python -m unittest test.test_llm_think_override -v
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from services import llm_service as llm_service_module  # noqa: E402
from services.llm_service import LLMService  # noqa: E402
from sys_settings.llm_settings import BackendProfile, LLMRuntimeConfig  # noqa: E402

# 線上 llm_runtime_config.json 搬之前的寫法：思考開關還寫在各家的 extra_body
LEMONADE_EXTRA_OLD = {"chat_template_kwargs": {"enable_thinking": True}, "cache_prompt": True}
OLLAMA_EXTRA_OLD = {"think": True, "keep_alive": "10m", "options": {"num_ctx": 16384, "repeat_penalty": 1.15}}
# 搬之後：extra_body 只留那家獨有的
LEMONADE_EXTRA = {"cache_prompt": True}
OLLAMA_EXTRA = {"keep_alive": "10m"}


def service_with(backend, extra_body, *, think=True, effort=None):
    """繞過 __init__（會讀 prompt 檔），只裝上待測方法需要的狀態。"""
    svc = LLMService.__new__(LLMService)
    config = LLMRuntimeConfig(
        backend=backend,
        model="main-model",
        embed_model="embed-model",
        backends={backend: BackendProfile(extra_body=dict(extra_body))},
        think=think,
        reasoning_effort=effort,
    )
    svc._load_runtime_config_cached = lambda: config  # type: ignore[method-assign]
    return svc


def build(svc, **kwargs):
    for name in ("think", "repeat_penalty", "num_ctx", "keep_alive"):
        kwargs.setdefault(name, None)
    return svc._build_chat_extra_body(**kwargs)


class _Base(unittest.TestCase):
    def setUp(self):
        llm_service_module._stale_think_keys_warned.clear()


class LiveConfigTests(_Base):
    """現在線上是 Lemonade、頂層沒寫 think／reasoning_effort：各功能送出的內容不能變。"""

    def test_default_request_is_unchanged(self):
        self.assertEqual(build(service_with("lemonade", LEMONADE_EXTRA_OLD)), LEMONADE_EXTRA_OLD)

    def test_interjection_at_medium_is_unchanged(self):
        body = build(service_with("lemonade", LEMONADE_EXTRA_OLD), reasoning_effort="medium")
        self.assertEqual(body, {"chat_template_kwargs": {"enable_thinking": True, "reasoning_effort": "medium"},
                                "cache_prompt": True})

    def test_thinking_off_is_unchanged(self):
        body = build(service_with("lemonade", LEMONADE_EXTRA_OLD), think=False)
        self.assertEqual(body, {"chat_template_kwargs": {"enable_thinking": False}, "cache_prompt": True})

    def test_moving_the_switch_to_the_top_level_sends_the_same_body(self):
        before = build(service_with("lemonade", LEMONADE_EXTRA_OLD), reasoning_effort="medium")
        after = build(service_with("lemonade", LEMONADE_EXTRA), reasoning_effort="medium")
        self.assertEqual(before, after)


class ThinkTests(_Base):
    def test_top_level_think_decides_when_the_caller_says_nothing(self):
        body = build(service_with("lemonade", LEMONADE_EXTRA, think=False))
        self.assertIs(body["chat_template_kwargs"]["enable_thinking"], False)

    def test_the_caller_wins_over_the_top_level(self):
        body = build(service_with("lemonade", LEMONADE_EXTRA, think=False), think=True)
        self.assertIs(body["chat_template_kwargs"]["enable_thinking"], True)

    def test_vllm_uses_the_same_template_switch(self):
        # 以前 vLLM 收不到思考開關：關掉思考的功能（人格萃取的收集步驟、探測）在 vLLM 上照樣思考
        body = build(service_with("vllm", {}), think=False)
        self.assertEqual(body, {"chat_template_kwargs": {"enable_thinking": False}})

    def test_ollama_turns_thinking_off_with_reasoning_effort_none(self):
        body = build(service_with("ollama", OLLAMA_EXTRA), think=False)
        self.assertEqual(body["reasoning_effort"], "none")
        self.assertNotIn("think", body, "Ollama 的 OpenAI 相容端點沒有 think 欄位")
        self.assertNotIn("chat_template_kwargs", body)

    def test_ollama_thinking_on_sends_nothing(self):
        self.assertEqual(build(service_with("ollama", OLLAMA_EXTRA)), OLLAMA_EXTRA)

    def test_resolve_reads_only_the_top_level(self):
        svc = service_with("lemonade", {"chat_template_kwargs": {"enable_thinking": False}}, think=True)
        self.assertTrue(svc.resolve_request_think(), "各家 extra_body 裡的舊寫法不算數")
        self.assertFalse(svc.resolve_request_think(False))

    def test_without_a_config_it_thinks(self):
        svc = LLMService.__new__(LLMService)
        svc._load_runtime_config_cached = lambda: None  # type: ignore[method-assign]
        self.assertTrue(svc.resolve_request_think())
        self.assertIs(build(svc)["chat_template_kwargs"]["enable_thinking"], True)


class EffortTests(_Base):
    def test_top_level_effort_is_used_when_the_caller_says_nothing(self):
        body = build(service_with("lemonade", LEMONADE_EXTRA, effort="low"))
        self.assertEqual(body["chat_template_kwargs"]["reasoning_effort"], "low")

    def test_the_caller_wins_over_the_top_level(self):
        body = build(service_with("lemonade", LEMONADE_EXTRA, effort="low"), reasoning_effort="medium")
        self.assertEqual(body["chat_template_kwargs"]["reasoning_effort"], "medium")

    def test_no_effort_anywhere_sends_none(self):
        self.assertNotIn("reasoning_effort", build(service_with("lemonade", LEMONADE_EXTRA))["chat_template_kwargs"])

    def test_vllm_gets_it_in_the_template_kwargs(self):
        body = build(service_with("vllm", {}), reasoning_effort="medium")
        self.assertEqual(body["chat_template_kwargs"]["reasoning_effort"], "medium")

    def test_ollama_gets_it_at_the_top_level(self):
        body = build(service_with("ollama", OLLAMA_EXTRA), reasoning_effort="medium")
        self.assertEqual(body["reasoning_effort"], "medium")
        self.assertNotIn("chat_template_kwargs", body)

    def test_ollama_thinking_off_beats_the_effort(self):
        body = build(service_with("ollama", OLLAMA_EXTRA), think=False, reasoning_effort="medium")
        self.assertEqual(body["reasoning_effort"], "none")


class StaleProfileKeyTests(_Base):
    """extra_body 裡還寫著思考設定：不生效、記一次警告，不改到設定檔的快取物件。"""

    def test_an_effort_left_in_the_profile_is_not_sent(self):
        svc = service_with("lemonade", {"chat_template_kwargs": {"enable_thinking": True, "reasoning_effort": "low"}})
        with self.assertLogs(llm_service_module.logger, "WARNING") as logs:
            body = build(svc)
        self.assertNotIn("reasoning_effort", body["chat_template_kwargs"])
        self.assertIn("reasoning_effort", logs.output[0])

    def test_the_warning_is_logged_once(self):
        svc = service_with("ollama", OLLAMA_EXTRA_OLD)
        with self.assertLogs(llm_service_module.logger, "WARNING"):
            build(svc)
        with self.assertNoLogs(llm_service_module.logger, "WARNING"):
            build(svc)

    def test_the_ollama_think_field_is_dropped(self):
        body = build(service_with("ollama", OLLAMA_EXTRA_OLD), think=False)
        self.assertNotIn("think", body)
        self.assertEqual(body["reasoning_effort"], "none")

    def test_ollama_options_are_dropped_with_a_warning(self):
        # OpenAI 相容端點沒有 options：上下文長度寫在這裡以為生效、其實照 Modelfile 跑
        with self.assertLogs(llm_service_module.logger, "WARNING") as logs:
            body = build(service_with("ollama", OLLAMA_EXTRA_OLD))
        self.assertNotIn("options", body)
        self.assertEqual(body["keep_alive"], "10m", "那家認得的欄位照送")
        self.assertIn("options", logs.output[0])

    def test_a_clean_profile_logs_nothing(self):
        with self.assertNoLogs(llm_service_module.logger, "WARNING"):
            build(service_with("lemonade", LEMONADE_EXTRA), think=False, reasoning_effort="medium")

    def test_the_cached_config_is_not_changed(self):
        svc = service_with("lemonade", LEMONADE_EXTRA_OLD)
        build(svc, think=False, reasoning_effort="medium")
        self.assertEqual(svc._load_runtime_config_cached().backends["lemonade"].extra_body, LEMONADE_EXTRA_OLD)


class UnreachableKnobsTests(_Base):
    def test_lemonade_does_not_get_ollama_knobs(self):
        body = build(service_with("lemonade", LEMONADE_EXTRA), keep_alive="30m", num_ctx=32768, repeat_penalty=1.05)
        for name in ("keep_alive", "options", "num_ctx", "repeat_penalty"):
            self.assertNotIn(name, body)

    def test_ollama_gets_keep_alive_but_not_the_context_size(self):
        body = build(service_with("ollama", OLLAMA_EXTRA), keep_alive="1h", num_ctx=2048, repeat_penalty=1.05)
        self.assertEqual(body["keep_alive"], "1h")
        self.assertNotIn("options", body, "OpenAI 相容端點沒有 options，送了也收不到")


if __name__ == "__main__":
    unittest.main()
