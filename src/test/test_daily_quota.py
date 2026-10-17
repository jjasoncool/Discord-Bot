"""每天最多做幾次的計數（`utils.daily_quota.DailyQuota`）。

守的底線：
  - 先扣再做：拿得到就算一次，用完回 False 且不再扣
  - 換日（呼叫端給的時間）就歸零；同一天內不歸零
  - 上限可以每次呼叫另給，沒給就用建立時的
  - `reset()` 回到沒用過

執行：
    cd src && python -m unittest test.test_daily_quota -v
"""

import os
import sys
import unittest
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from utils.daily_quota import DailyQuota  # noqa: E402

NOON = datetime(2026, 10, 17, 12, 0)


class DailyQuotaTests(unittest.TestCase):
    def test_takes_until_the_limit_then_refuses(self):
        quota = DailyQuota(2)
        self.assertEqual([quota.take(NOON), quota.take(NOON), quota.take(NOON)], [True, True, False])
        self.assertEqual(quota.used(NOON), 2)
        self.assertEqual(quota.remaining(NOON), 0)

    def test_a_new_day_starts_over(self):
        quota = DailyQuota(1)
        self.assertTrue(quota.take(NOON))
        self.assertFalse(quota.take(NOON + timedelta(hours=11)))          # 同一天
        self.assertTrue(quota.take(NOON + timedelta(hours=13)))           # 隔天
        self.assertEqual(quota.used(NOON + timedelta(hours=13)), 1)

    def test_limit_given_per_call_wins(self):
        quota = DailyQuota(1)
        self.assertTrue(quota.take(NOON, limit=3))
        self.assertTrue(quota.take(NOON, limit=3))
        self.assertFalse(quota.take(NOON))                                 # 沒給就是建立時的 1
        self.assertEqual(quota.remaining(NOON, limit=3), 1)

    def test_reset_forgets_today(self):
        quota = DailyQuota(1)
        quota.take(NOON)
        quota.reset()
        self.assertTrue(quota.take(NOON))


if __name__ == "__main__":
    unittest.main()
