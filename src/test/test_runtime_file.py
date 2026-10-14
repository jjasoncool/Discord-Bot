"""守的底線：狀態 JSON 只有一套讀寫——缺檔與壞檔不炸、改檔即生效、更新只動自己的欄位、寫入先備份且不留半成品。"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from utils import runtime_file  # noqa: E402


class RuntimeFileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "x_runtime.json"
        self.backup = Path(self.tmp.name) / "backup"

    def _write(self, text):
        self.path.write_text(text, encoding="utf-8")
        os.utime(self.path, ns=(os.stat(self.path).st_mtime_ns + 1_000_000,) * 2)

    def test_missing_or_broken_file_reads_empty(self):
        self.assertEqual({}, runtime_file.load(self.path))
        self._write("{broken")
        self.assertEqual({}, runtime_file.load(self.path))
        self._write("[1, 2]")
        self.assertEqual({}, runtime_file.load(self.path))

    def test_edits_to_the_file_are_seen(self):
        self._write('{"a": 1}')
        self.assertEqual({"a": 1}, runtime_file.load(self.path))
        self._write('{"a": 2}')
        self.assertEqual({"a": 2}, runtime_file.load(self.path))

    def test_update_merges_top_level_fields_and_keeps_the_rest(self):
        self._write('{"a": 1, "nested": {"k": "v"}}')
        runtime_file.update(self.path, b=2, backup_dir=self.backup)
        self.assertEqual({"a": 1, "nested": {"k": "v"}, "b": 2}, json.loads(self.path.read_text(encoding="utf-8")))
        self.assertTrue(any(self.backup.glob("x_runtime_*.json")), "改寫前要備份一份")

    def test_save_replaces_everything_and_creates_the_folder(self):
        path = Path(self.tmp.name) / "deeper" / "y_runtime.json"
        runtime_file.save(path, {"only": True}, backup_dir=self.backup)
        self.assertEqual({"only": True}, runtime_file.load(path))

    def test_returned_dict_is_a_copy(self):
        self._write('{"a": {"b": 1}}')
        runtime_file.load(self.path)["a"]["b"] = 9
        self.assertEqual({"a": {"b": 1}}, runtime_file.load(self.path))

    def test_failed_write_leaves_the_old_file_intact(self):
        self._write('{"a": 1}')
        with mock.patch("utils.safe_write.os.replace", side_effect=OSError("disk")):
            with self.assertRaises(OSError):
                runtime_file.update(self.path, a=2, backup_dir=self.backup)
        self.assertEqual({"a": 1}, json.loads(self.path.read_text(encoding="utf-8")))
        self.assertEqual([self.path.name], [p.name for p in Path(self.tmp.name).iterdir() if p.is_file()], "不留暫存檔")

    def test_backup_folder_follows_the_environment_variable(self):
        """測試套件把它指到暫存目錄；沒這條，跑測試會把假資料的備份寫進正式的 /logs。"""
        self._write('{"a": 1}')
        with mock.patch.dict(os.environ, {"RUNTIME_BACKUP_DIR": str(self.backup)}):
            self.assertEqual(str(self.backup), runtime_file.default_backup_dir())
            runtime_file.update(self.path, b=2)
        self.assertTrue(any(self.backup.glob("x_runtime_*.json")))
        with mock.patch.dict(os.environ, {"RUNTIME_BACKUP_DIR": ""}):
            self.assertEqual(runtime_file.DEFAULT_BACKUP_DIR, runtime_file.default_backup_dir())


if __name__ == "__main__":
    unittest.main()
