"""使用者在視窗打的日期與時間（utils.user_dates）。

守的底線：
  1. 寫法寬鬆：`/` `-` `.`、年月日、八碼數字、全形字、一位數的月日時都讀得懂（使用者 2026-10-04，TR-Q41）。
  2. 年份一定要四位數；不存在的日期（2/30）與時間（25:00）讀不懂。
  3. 只要日期的欄位多寫了時間算讀不懂；日期＋時間的欄位只寫日期時，用呼叫端給的預設時間，沒給就讀不懂。
"""

import os
import sys
import unittest
from datetime import date, datetime, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from utils.user_dates import parse_user_date, parse_user_datetime  # noqa: E402

DAY = date(2026, 10, 20)


class ParseUserDateTests(unittest.TestCase):

    def test_accepted_spellings(self):
        for text in ("2026-10-20", "2026/10/20", "2026.10.20", "2026年10月20日", "20261020",
                     " 2026/10/20 ", "２０２６／１０／２０", "2026 / 10 / 20"):
            with self.subTest(text):
                self.assertEqual(parse_user_date(text), DAY)
        self.assertEqual(parse_user_date("2026/1/5"), date(2026, 1, 5))

    def test_rejected(self):
        for text in ("", "10/20", "26/10/20", "2026/02/30", "2026/13/01", "明天", "2026/10/20 23:59", None):
            with self.subTest(text):
                self.assertIsNone(parse_user_date(text))


class ParseUserDatetimeTests(unittest.TestCase):

    def test_date_and_time(self):
        expected = datetime(2026, 10, 20, 23, 59)
        for text in ("2026/10/20 23:59", "2026-10-20 23:59", "２０２６／１０／２０　２３：５９", "2026年10月20日 23:59"):
            with self.subTest(text):
                self.assertEqual(parse_user_datetime(text), expected)
        self.assertEqual(parse_user_datetime("2026/10/20 9:05"), datetime(2026, 10, 20, 9, 5))

    def test_date_only_uses_the_default_time(self):
        self.assertEqual(parse_user_datetime("2026/10/20", default_time=time(23, 59)), datetime(2026, 10, 20, 23, 59))
        self.assertIsNone(parse_user_datetime("2026/10/20"))  # 沒給預設就一定要寫時間

    def test_rejected(self):
        for text in ("2026/10/20 25:00", "2026/10/20 23:60", "2026/02/30 12:00", "10/20 23:59", "2026/10/2023:59"):
            with self.subTest(text):
                self.assertIsNone(parse_user_datetime(text, default_time=time(23, 59)))


if __name__ == "__main__":
    unittest.main()
