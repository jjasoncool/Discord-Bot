"""全程式共用一份的資源（utils.shared_resource.SharedResource）。

守的底線：
  1. 同時要的協程只開一次，拿到的是同一份。
  2. 停機 close 之後 get 丟 RuntimeError，不再開新的（停機時漏網的工作又開一份沒人關，行程退不出去）。
  3. 沒開過也能 close、重複 close 不出錯，關掉的動作只做一次。
  4. 開的時候出錯不留半份：下一次 get 重新開。
"""

import asyncio
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC_DIR = HERE.parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from utils.shared_resource import SharedResource  # noqa: E402


class SharedResourceTests(unittest.TestCase):

    def make(self, *, fail_first=False):
        log = {"opened": 0, "closed": []}

        async def open_():
            log["opened"] += 1
            await asyncio.sleep(0)  # 讓同時要的協程有機會插進來
            if fail_first and log["opened"] == 1:
                raise OSError("磁碟滿了")
            return object()

        async def close_(value):
            log["closed"].append(value)

        return SharedResource("測試資源", open_, close_), log

    def test_concurrent_gets_open_once(self):
        async def main():
            shared, log = self.make()
            values = await asyncio.gather(*(shared.get() for _ in range(5)))
            return values, log, shared.current

        values, log, current = asyncio.run(main())
        self.assertTrue(all(v is values[0] for v in values))
        self.assertIs(current, values[0])
        self.assertEqual(log["opened"], 1)

    def test_no_new_one_after_close(self):
        async def main():
            shared, log = self.make()
            first = await shared.get()
            await shared.close()
            with self.assertRaises(RuntimeError):
                await shared.get()
            return first, log, shared.current

        first, log, current = asyncio.run(main())
        self.assertEqual(log["opened"], 1)
        self.assertEqual(log["closed"], [first])
        self.assertIsNone(current)

    def test_close_without_open_and_twice(self):
        async def main():
            shared, log = self.make()
            await shared.close()
            await shared.close()
            return log

        self.assertEqual(asyncio.run(main())["closed"], [])

    def test_failed_open_is_retried(self):
        async def main():
            shared, log = self.make(fail_first=True)
            with self.assertRaises(OSError):
                await shared.get()
            value = await shared.get()
            return value, log

        value, log = asyncio.run(main())
        self.assertIsNotNone(value)
        self.assertEqual(log["opened"], 2)

    def test_reset_and_restore_for_tests(self):
        async def main():
            shared, _ = self.make()
            first = await shared.get()
            saved = shared.reset()
            other = await shared.get()
            shared.restore(saved)
            return first, other, shared.current

        first, other, current = asyncio.run(main())
        self.assertIsNot(first, other)
        self.assertIs(current, first)


if __name__ == "__main__":
    unittest.main()
