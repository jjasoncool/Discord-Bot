"""每個 LLM 請求記一行用量（功能、prompt 長度、命中快取、重算、讀 prompt 耗時）。

守的底線：
  - 成功的請求一定留一行，看得出是哪個功能（trace 前綴）、命中多少、重算多少——
    用來找「誰把誰的 prompt 快取洗掉」（KV cache 管理，2026-10-08）
  - 後端沒給 llama.cpp 的 `timings` 也不能壞，退回 OpenAI 格式的 `usage`
  - 只記數字，不記 prompt 內容（群友的聊天不該因為這行 log 多抄一份）

執行：
    cd src && python -m unittest test.test_llm_usage_log -v
"""

import asyncio
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from services import llm_service as llm_service_module  # noqa: E402
from test.test_llm_snapshot import _make_service  # noqa: E402

LEMONADE_COMPLETION = {
    "choices": [{"message": {"role": "assistant", "content": "回答"}}],
    "usage": {"completion_tokens": 2655, "prompt_tokens": 10805, "prompt_tokens_details": {"cached_tokens": 8139}},
    "timings": {"cache_n": 8139, "prompt_n": 2666, "prompt_ms": 10770.02, "predicted_n": 2655,
                "predicted_per_second": 28.52, "draft_n": 2631, "draft_n_accepted": 1777},
}


class LlmUsageLogTests(unittest.TestCase):
    def run_chat(self, completion, trace_id="ask-1234-1700000000000", content="群友的秘密聊天內容"):
        svc = _make_service("lemonade")
        svc._client.chat_completion.return_value = completion
        with self.assertLogs(llm_service_module.logger, level="INFO") as caught:
            asyncio.run(svc.chat_raw(model="m", messages=[{"role": "user", "content": content}], trace_id=trace_id))
        lines = [line for line in caught.output if "llm_usage" in line]
        self.assertEqual(len(lines), 1, caught.output)
        return lines[0]

    def test_records_feature_cache_hits_and_prompt_time(self):
        line = self.run_chat(LEMONADE_COMPLETION)

        for expected in ("feature=ask", "prompt=10805", "cached=8139", "computed=2666", "prompt_ms=10770",
                         "output=2655", "tok_s=28.5", "draft=1777/2631"):
            self.assertIn(expected, line)

    def test_falls_back_to_openai_usage_without_llama_cpp_timings(self):
        completion = {key: value for key, value in LEMONADE_COMPLETION.items() if key != "timings"}

        line = self.run_chat(completion, trace_id="amb-1-2")

        self.assertIn("feature=amb", line)
        self.assertIn("cached=8139", line)
        self.assertIn("computed=-", line)

    def test_never_logs_the_prompt_itself(self):
        line = self.run_chat(LEMONADE_COMPLETION, content="群友的秘密聊天內容")

        self.assertNotIn("群友的秘密聊天內容", line)


if __name__ == "__main__":
    unittest.main()
