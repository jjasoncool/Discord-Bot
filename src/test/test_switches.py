"""功能開關（sys_settings/switches.py 與 settings/switches.json）。

守的底線（使用者 10-06 SW-Q1～Q2）：
- 值從 switches.json 讀，改了下一次用到就生效、不用重啟
- 沒有檔案、讀不到時全部用預設（預設是關掉也安全的那邊）
- 某一項的值寫錯：那一項用預設並記 warning，其他項照用；不認得的名稱記 warning；`_` 開頭的說明不算開關
- 檔案不見或整份 JSON 寫壞：全部用預設、只記一次 warning，不會讓 bot 起不來（啟動測試刻意不驗線上手改的那份檔）

執行：
    cd src && python -m unittest test.test_switches -v
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from llm.prompt import prompt_files
from sys_settings import switches


class SwitchesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.path = self.tmp / "switches.json"
        patcher = mock.patch.object(switches, "SWITCHES_PATH", self.path)
        patcher.start()
        self.addCleanup(patcher.stop)

    def write(self, data):
        self.path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        st = self.path.stat()
        os.utime(self.path, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000))   # 確保修改時間不同
        prompt_files.forget(self.path)

    def test_missing_file_uses_defaults_and_warns_once(self):
        with mock.patch.object(switches, "_missing_warned", False):
            with self.assertLogs("sys_settings.switches", "WARNING") as logs:
                for _ in range(3):
                    self.assertEqual(switches.current().telegram_filter_mode, "off")
        self.assertEqual(len(logs.output), 1, "每則訊息都會讀，不能每次都記")

    def test_broken_json_uses_defaults_and_warns_once(self):
        self.path.write_text('{"telegram_filter_mode": "on",,}', encoding="utf-8")
        prompt_files.forget(self.path)
        with self.assertLogs("sys_settings.switches", "WARNING") as logs:
            for _ in range(3):
                self.assertEqual(switches.current().telegram_filter_mode, "off")
        self.assertEqual(len(logs.output), 1)
        self.assertIn("不是合法的 JSON", logs.output[0], "要講清楚是寫壞了、全部用預設，不是說找不到")

    def test_edit_takes_effect_without_restart(self):
        self.write({"telegram_filter_mode": "dry_run"})
        self.assertEqual(switches.current().telegram_filter_mode, "dry_run")
        self.write({"telegram_filter_mode": "on"})
        self.assertEqual(switches.current().telegram_filter_mode, "on")

    def test_bad_value_falls_back_to_default(self):
        with self.assertLogs("sys_settings.switches", "WARNING") as logs:
            self.write({"telegram_filter_mode": "onn"})
            self.assertEqual(switches.current().telegram_filter_mode, "off")
        self.assertTrue(any("telegram_filter_mode" in line for line in logs.output))

    def test_unknown_key_warns_and_comments_are_ignored(self):
        with self.assertLogs("sys_settings.switches", "WARNING") as logs:
            self.write({"_說明": "這是說明", "telegram_filter_mod": "on", "telegram_filter_mode": "dry_run"})
            self.assertEqual(switches.current().telegram_filter_mode, "dry_run")
        self.assertTrue(any("telegram_filter_mod'" in line for line in logs.output))
        self.assertFalse(any("_說明" in line for line in logs.output))

    def test_defaults_are_safe(self):
        self.assertEqual(switches.Switches().telegram_filter_mode, "off")


if __name__ == "__main__":
    unittest.main()
