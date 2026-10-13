"""會被手改的檔案的讀取器（`utils/hot_files.py`）：prompt、字典、開關、config.json、LLM runtime 設定共用這一份。

守的底線：
  - 檔案修改時間沒變就不重新解析（parse 只跑一次）
  - 檔案改了（修改時間變了）下一次讀就拿到新內容，不用重啟
  - 缺檔回 None；`missing_ok` 時不記警告，否則記
  - 檔案壞掉（解析失敗）沿用上次讀到的好內容並記 WARNING；從來沒讀成功過才回 None
  - 給了 `on_error` 就由呼叫端記 log，這裡不記
  - `forget` 之後下一次一定重讀
  - `read_text` 缺檔回空字串、`read_json` 不是物件回 None（舊介面不變）

執行：
    cd src && python -m unittest test.test_hot_files -v
"""

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

from utils import hot_files  # noqa: E402

LOGGER = "utils.hot_files"


class HotFilesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "thing.json"
        self.parses = 0

    def tearDown(self):
        hot_files.forget(self.path)
        self.tmp.cleanup()

    def write(self, text, mtime_ns):
        self.path.write_text(text, encoding="utf-8")
        os.utime(self.path, ns=(mtime_ns, mtime_ns))

    def parse(self, raw):
        self.parses += 1
        return json.loads(raw)

    def read(self, **kw):
        return hot_files.read_parsed(self.path, parse=self.parse, label="測試檔", **kw)

    def test_same_mtime_is_parsed_once(self):
        self.write('{"a": 1}', 1_000)
        self.assertEqual(self.read(), {"a": 1})
        self.assertEqual(self.read(), {"a": 1})
        self.assertEqual(self.parses, 1)

    def test_changed_file_is_read_right_away(self):
        self.write('{"a": 1}', 1_000)
        self.read()
        self.write('{"a": 2}', 2_000)
        self.assertEqual(self.read(), {"a": 2})
        self.assertEqual(self.parses, 2)

    def test_missing_file(self):
        with self.assertLogs(LOGGER, "WARNING"):
            self.assertIsNone(self.read())
        with self.assertNoLogs(LOGGER, "WARNING"):
            self.assertIsNone(self.read(missing_ok=True))

    def test_broken_file_keeps_the_last_good_content(self):
        self.write('{"a": 1}', 1_000)
        self.read()
        self.write('{"a": 1,,}', 2_000)
        with self.assertLogs(LOGGER, "WARNING") as logs:
            self.assertEqual(self.read(), {"a": 1})
        self.assertIn("沿用上次", logs.output[0])
        # 修好之後又讀新的
        self.write('{"a": 3}', 3_000)
        self.assertEqual(self.read(), {"a": 3})

    def test_broken_file_with_nothing_good_before_is_none(self):
        self.write('{"a": 1,,}', 1_000)
        with self.assertLogs(LOGGER, "WARNING"):
            self.assertIsNone(self.read())

    def test_on_error_lets_the_caller_log_instead(self):
        self.write('{"a": 1,,}', 1_000)
        seen = []
        with self.assertNoLogs(LOGGER, "WARNING"):
            self.assertIsNone(self.read(on_error=seen.append))
        self.assertEqual(len(seen), 1)
        self.assertIsInstance(seen[0], json.JSONDecodeError)

    def test_forget_forces_a_reload(self):
        self.write('{"a": 1}', 1_000)
        self.read()
        hot_files.forget(self.path)
        self.read()
        self.assertEqual(self.parses, 2)

    def test_old_helpers_keep_their_contract(self):
        self.assertEqual(hot_files.read_text(Path(self.tmp.name) / "nope.txt", label="x"), "")
        self.assertIsNone(hot_files.read_json(Path(self.tmp.name) / "nope.json", label="x"))
        self.write("[1, 2]", 1_000)
        self.assertIsNone(hot_files.read_json(self.path, label="x"))     # 不是物件


if __name__ == "__main__":
    unittest.main()
