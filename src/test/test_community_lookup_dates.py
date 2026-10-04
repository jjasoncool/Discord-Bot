"""社群稽查（社群 ID 查詢）填的起訖日期（commands.community_lookup_commands._validate_date_range）。

守的底線：
  1. 日期寫法跟商品的預購截止一樣寬鬆（共用 utils.user_dates）：`2026-04-20`、`2026/04/20`、全形都收。
  2. 讀不懂就說是哪一欄、附範例；起始日在未來就擋。
  3. 結束日超過今天自動改成今天；起訖顛倒自動互換；區間最多 180 天。
"""

import os
import sys
import unittest
from datetime import datetime, timezone, timedelta
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from commands import community_lookup_commands as lookup  # noqa: E402

TODAY = datetime(2026, 10, 4, 12, 0, tzinfo=timezone(timedelta(hours=8)))


class DateRangeTests(unittest.TestCase):

    def setUp(self):
        patcher = mock.patch.object(lookup, "_now_local", return_value=TODAY)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_spellings(self):
        for start, end in (("2026-09-01", "2026-09-30"), ("2026/09/01", "2026/09/30"), ("２０２６／０９／０１", "2026/9/30")):
            with self.subTest(start=start, end=end):
                self.assertEqual(lookup._validate_date_range(start, end), ("2026-09-01", "2026-09-30", None))

    def test_unreadable_says_which_field(self):
        self.assertIn("起始日", lookup._validate_date_range("9/1", "2026-09-30")[2])
        self.assertIn("結束日", lookup._validate_date_range("2026-09-01", "2026/02/30")[2])

    def test_rules(self):
        self.assertIn("未來", lookup._validate_date_range("2026-10-05", "2026-10-06")[2])
        self.assertEqual(lookup._validate_date_range("2026-09-01", "2026-12-31")[:2], ("2026-09-01", "2026-10-04"))
        self.assertEqual(lookup._validate_date_range("2026-09-30", "2026-09-01")[:2], ("2026-09-01", "2026-09-30"))
        self.assertIn("180", lookup._validate_date_range("2026-01-01", "2026-10-01")[2])


if __name__ == "__main__":
    unittest.main()
