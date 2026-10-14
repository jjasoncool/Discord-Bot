"""守的底線：賣家價格表只有一個讀寫點；改檔即生效、換一位賣家的價格不動到別人、壞檔不炸。"""
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

from services.community import item_prices  # noqa: E402


class ItemPricesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "item_prices.json"
        self.backup = Path(self.tmp.name) / "backup"

    def _write(self, data):
        self.path.write_text(json.dumps(data), encoding="utf-8")
        os.utime(self.path, ns=(os.stat(self.path).st_mtime_ns + 1_000_000,) * 2)   # 確保 mtime 會變

    def test_missing_file_means_no_prices(self):
        self.assertEqual({}, item_prices.all_prices(self.path))
        self.assertEqual({}, item_prices.user_prices(1, self.path))

    def test_reads_one_seller_and_reflects_edits_to_the_file(self):
        self._write({"1": {"gold": 100}, "2": {"gold": 90}})
        self.assertEqual({"gold": 100}, item_prices.user_prices(1, self.path))
        self._write({"1": {"gold": 120}, "2": {"gold": 90}})
        self.assertEqual({"gold": 120}, item_prices.user_prices("1", self.path))

    def test_setting_one_seller_keeps_the_others(self):
        self._write({"1": {"gold": 100}, "2": {"gold": 90}})
        item_prices.set_user_prices(2, {"gold": 80, "silver": 5}, self.path, backup_dir=self.backup)
        self.assertEqual({"1": {"gold": 100}, "2": {"gold": 80, "silver": 5}},
                         json.loads(self.path.read_text(encoding="utf-8")))
        self.assertEqual({"gold": 80, "silver": 5}, item_prices.user_prices(2, self.path))
        self.assertTrue(self.backup.exists(), "改寫前要備份")

    def test_setting_into_a_missing_file_creates_it(self):
        item_prices.set_user_prices(7, {"gold": 1}, self.path, backup_dir=self.backup)
        self.assertEqual({"7": {"gold": 1}}, item_prices.all_prices(self.path))

    def test_returned_dict_is_a_copy(self):
        self._write({"1": {"gold": 100}})
        item_prices.all_prices(self.path)["1"]["gold"] = 1
        self.assertEqual({"gold": 100}, item_prices.user_prices(1, self.path))

    def test_broken_file_is_not_fatal(self):
        self.path.write_text("{not json", encoding="utf-8")
        self.assertEqual({}, item_prices.all_prices(self.path))


if __name__ == "__main__":
    unittest.main()
