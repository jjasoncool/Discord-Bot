"""`think` per-call 覆寫在各後端的轉接（hermetic，不碰檔案或網路）。

背景：`think` 的覆寫管線本來就完整（`resolve_request_think` → `generate_reply` →
`chat_raw` → `_build_chat_extra_body`），但從 Ollama 遷到 Lemonade 之後，最後一步把
它丟進 `ignored` → 形成「參數傳得到、卻不生效」的斷點。persona agent 需要在同一次
執行裡切換思考模式（收集步驟關、產 diff 開），因此補上轉接。

本測試的重點是**不要誤傷既有 caller**：`think=None` 時 extra_body 必須與修改前
完全相同（/askai、插話、人格萃取都走這條路）。

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

from services.llm_service import LLMService  # noqa: E402
from sys_settings.llm_settings import BackendProfile, LLMRuntimeConfig  # noqa: E402

# 線上 llm_runtime_config.json 的等價設定（2026-08-18）
LEMONADE_EXTRA = {
    "chat_template_kwargs": {"enable_thinking": True},
    "cache_prompt": True,
}
OLLAMA_EXTRA = {
    "think": True,
    "keep_alive": "10m",
    "options": {"num_ctx": 16384, "repeat_penalty": 1.15},
}


def service_with(backend, profiles, legacy_think=True):
    """繞過 __init__（會讀 prompt 檔），只裝上待測方法需要的狀態。"""
    svc = LLMService.__new__(LLMService)
    config = LLMRuntimeConfig(
        backend=backend,
        model="Qwen3.8-27B-GGUF-UD-Q4_K_XL",
        embed_model="Qwen3-Embedding-0.6B-GGUF",
        backends=profiles,
        think=legacy_think,
    )
    svc._load_runtime_config_cached = lambda: config  # type: ignore[method-assign]
    return svc


def lemonade_service():
    return service_with("lemonade", {
        "ollama": BackendProfile(extra_body=dict(OLLAMA_EXTRA)),
        "lemonade": BackendProfile(extra_body=dict(LEMONADE_EXTRA)),
    })


def build(svc, **kwargs):
    kwargs.setdefault("think", None)
    kwargs.setdefault("repeat_penalty", None)
    kwargs.setdefault("num_ctx", None)
    kwargs.setdefault("keep_alive", None)
    return svc._build_chat_extra_body(**kwargs)


class NoRegressionTests(unittest.TestCase):
    """think=None（既有 caller 的情境）→ extra_body 必須原封不動。"""

    def test_lemonade_untouched_when_think_is_none(self):
        self.assertEqual(build(lemonade_service()), LEMONADE_EXTRA)

    def test_profile_dict_is_not_mutated(self):
        """覆寫必須是複製後再改，否則會污染 runtime config 的快取物件。"""
        svc = lemonade_service()
        build(svc, think=False)
        self.assertTrue(
            svc._load_runtime_config_cached()
            .backends["lemonade"].extra_body["chat_template_kwargs"]["enable_thinking"]
        )

    def test_ollama_path_unchanged(self):
        svc = service_with("ollama", {"ollama": BackendProfile(extra_body=dict(OLLAMA_EXTRA))})
        self.assertIs(build(svc, think=False)["think"], False)
        self.assertNotIn("chat_template_kwargs", build(svc, think=False))


class LemonadeMappingTests(unittest.TestCase):
    """think → chat_template_kwargs.enable_thinking 的語意轉接。"""

    def test_think_false_disables_thinking(self):
        body = build(lemonade_service(), think=False)
        self.assertIs(body["chat_template_kwargs"]["enable_thinking"], False)
        # 同一個 dict 裡的其他鍵不能被覆寫掉
        self.assertTrue(body["cache_prompt"])

    def test_think_true_enables_thinking(self):
        body = build(lemonade_service(), think=True)
        self.assertIs(body["chat_template_kwargs"]["enable_thinking"], True)

    def test_ollama_only_knobs_still_dropped(self):
        body = build(lemonade_service(), think=False, keep_alive="30m", num_ctx=32768)
        self.assertNotIn("keep_alive", body)
        self.assertNotIn("options", body)

    def test_other_backends_still_ignore_think(self):
        svc = service_with("vllm", {"vllm": BackendProfile(extra_body={})})
        self.assertEqual(build(svc, think=False), {})


class ResolveThinkTests(unittest.TestCase):
    """優先序：override > 當前 backend profile > 舊欄位 > True。"""

    def test_override_wins(self):
        self.assertFalse(lemonade_service().resolve_request_think(False))

    def test_reads_lemonade_profile_not_ollama(self):
        svc = service_with("lemonade", {
            "ollama": BackendProfile(extra_body={"think": True}),
            "lemonade": BackendProfile(
                extra_body={"chat_template_kwargs": {"enable_thinking": False}}
            ),
        })
        self.assertFalse(svc.resolve_request_think())

    def test_reads_ollama_profile_when_backend_is_ollama(self):
        svc = service_with("ollama", {"ollama": BackendProfile(extra_body={"think": False})})
        self.assertFalse(svc.resolve_request_think())

    def test_falls_back_to_legacy_field(self):
        svc = service_with("lemonade", {"lemonade": BackendProfile(extra_body={})},
                           legacy_think=False)
        self.assertFalse(svc.resolve_request_think())

    def test_live_config_shape_still_resolves_true(self):
        """線上設定（兩邊都是 true）→ 結果不變，確認本次改動不影響 production。"""
        self.assertTrue(lemonade_service().resolve_request_think())


if __name__ == "__main__":
    unittest.main()
