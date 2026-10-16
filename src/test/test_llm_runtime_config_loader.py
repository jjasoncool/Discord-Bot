"""LLM runtime 設定的載入（sys_settings.llm_settings.load_llm_runtime_config）。

守的底線：
  - 檔案沒變就不重讀重驗：十幾個地方每次用到都呼叫它，拿到的是同一份解析結果
  - 改檔即生效：改了模型名稱，下一次呼叫就是新的
  - 改壞了沿用上次的好內容，不讓 bot 失去模型名稱
  - 缺檔、或一開始就是壞的（從沒成功讀過）：拋錯，這些設定沒有合理的預設值
"""
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from sys_settings.llm_settings import load_llm_runtime_config  # noqa: E402
from utils import hot_files  # noqa: E402

GOOD = {"backend": "lemonade", "model": "main-model", "embed_model": "embed-model"}


class RuntimeConfigLoaderTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.path = Path(self.dir.name) / "llm_runtime_config.json"
        self.write(GOOD)

    def write(self, data, raw: str | None = None):
        self.path.write_text(raw if raw is not None else json.dumps(data), encoding="utf-8")
        # 修改時間往後撥，確保和上一版不同（檔案系統的時間解析度可能不夠）
        stamp = time.time() + 2
        os.utime(self.path, (stamp, stamp))
        hot_files.forget(self.path)

    def test_unchanged_file_is_parsed_once(self):
        first = load_llm_runtime_config(self.path)
        second = load_llm_runtime_config(str(self.path))
        self.assertEqual("main-model", first.model)
        self.assertIs(first, second, "檔案沒變就回同一份，不重讀重驗")

    def test_edit_takes_effect_on_next_call(self):
        load_llm_runtime_config(self.path)
        self.path.write_text(json.dumps({**GOOD, "model": "other-model"}), encoding="utf-8")
        stamp = time.time() + 4
        os.utime(self.path, (stamp, stamp))
        self.assertEqual("other-model", load_llm_runtime_config(self.path).model)

    def test_broken_edit_keeps_the_last_good_config(self):
        load_llm_runtime_config(self.path)
        self.path.write_text("{not json", encoding="utf-8")
        stamp = time.time() + 4
        os.utime(self.path, (stamp, stamp))
        with self.assertLogs(hot_files.logger, "WARNING"):
            self.assertEqual("main-model", load_llm_runtime_config(self.path).model)

    def test_missing_or_never_valid_file_raises(self):
        with self.assertLogs(hot_files.logger, "WARNING"), self.assertRaises(RuntimeError):
            load_llm_runtime_config(Path(self.dir.name) / "nope.json")
        self.write(None, raw="{not json")
        with self.assertLogs(hot_files.logger, "WARNING"), self.assertRaises(RuntimeError):
            load_llm_runtime_config(self.path)


if __name__ == "__main__":
    unittest.main()
