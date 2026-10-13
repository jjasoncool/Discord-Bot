"""`LLMService._load_runtime_config_cached`：LLM runtime 設定（哪個後端、哪個模型）改檔即生效，壞檔不會讓 bot 失去模型名稱。

守的底線：
  - 檔案改了，下一次請求就用新的模型名稱（不用重啟）
  - 模型名稱空白＝沒有設定，回 None（呼叫端退回預設），不會拿空字串去打後端
  - 檔案壞掉時沿用上次讀到的設定；缺檔回 None

執行：
    cd src && python -m unittest test.test_llm_runtime_config_cache -v
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from services.llm_service import LLMService  # noqa: E402
from utils import hot_files  # noqa: E402

BASE = {"backend": "lemonade", "model": "main-model", "embed_model": "embed-model"}


class RuntimeConfigCacheTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "llm_runtime_config.json"
        self.svc = LLMService.__new__(LLMService)
        self.svc.settings = SimpleNamespace(llm_runtime_model_path=str(self.path))

    def tearDown(self):
        hot_files.forget(self.path)
        self.tmp.cleanup()

    def write(self, data, mtime_ns):
        self.path.write_text(json.dumps(data) if isinstance(data, dict) else data, encoding="utf-8")
        os.utime(self.path, ns=(mtime_ns, mtime_ns))

    def test_edit_takes_effect_on_the_next_read(self):
        self.write(BASE, 1_000)
        self.assertEqual(self.svc._load_runtime_config_cached().model, "main-model")
        self.write({**BASE, "model": "other-model"}, 2_000)
        self.assertEqual(self.svc._load_runtime_config_cached().model, "other-model")

    def test_blank_model_name_means_not_configured(self):
        self.write({**BASE, "model": "   "}, 1_000)
        self.assertIsNone(self.svc._load_runtime_config_cached())

    def test_broken_file_keeps_the_last_good_config_and_missing_is_none(self):
        self.write(BASE, 1_000)
        self.svc._load_runtime_config_cached()
        self.write("{not json", 2_000)
        with self.assertLogs("utils.hot_files", "WARNING"):
            self.assertEqual(self.svc._load_runtime_config_cached().model, "main-model")
        self.path.unlink()
        self.assertIsNone(self.svc._load_runtime_config_cached())


if __name__ == "__main__":
    unittest.main()
