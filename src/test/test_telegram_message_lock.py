"""telegram_scraper 單則訊息鎖（KeyedLock）單元測試（純 asyncio，不需 Telethon / DB）。

執行：
    cd src && python -m unittest test.test_telegram_message_lock -v
"""

import asyncio
import os
import sys
import unittest
from types import SimpleNamespace

# scraper 容器以 /app = src/telegram_scraper 執行、模組間用裸 import，這裡照樣把目錄加進路徑
HERE = os.path.dirname(os.path.abspath(__file__))
SCRAPER_DIR = os.path.join(os.path.dirname(HERE), "telegram_scraper")
if SCRAPER_DIR not in sys.path:
    sys.path.insert(0, SCRAPER_DIR)

from message_lock import KeyedLock, message_lock_key


class KeyedLockTests(unittest.IsolatedAsyncioTestCase):

    async def test_same_key_is_mutually_exclusive(self):
        # 即時事件與補掃撞到同一則訊息：不可同時處理
        locks = KeyedLock()
        active = 0
        max_active = 0

        async def worker():
            nonlocal active, max_active
            async with locks.hold((-100, 1)):
                active += 1
                max_active = max(max_active, active)
                await asyncio.sleep(0.01)
                active -= 1

        await asyncio.gather(*(worker() for _ in range(3)))
        self.assertEqual(max_active, 1)

    async def test_album_members_run_concurrently(self):
        # 相簿 8 張圖各自是一則訊息：必須能同時進入，否則會退回逐張排隊（漏圖的根因）。
        # 每個 worker 都等「8 個都進來了」才離開；若被序列化，第一個永遠等不到 → 逾時失敗。
        locks = KeyedLock()
        members = 8
        entered = 0
        all_in = asyncio.Event()

        async def worker(message_id: int):
            nonlocal entered
            async with locks.hold((-100, message_id)):
                entered += 1
                if entered == members:
                    all_in.set()
                await all_in.wait()

        await asyncio.wait_for(
            asyncio.gather(*(worker(3223 + i) for i in range(members))),
            timeout=1.0,
        )
        self.assertEqual(entered, members)

    async def test_lock_entries_are_reclaimed(self):
        locks = KeyedLock()

        async def worker(message_id: int):
            async with locks.hold((-100, message_id)):
                await asyncio.sleep(0)

        await asyncio.gather(*(worker(i % 3) for i in range(9)))
        self.assertEqual(len(locks), 0)

    async def test_lock_entry_reclaimed_after_exception(self):
        locks = KeyedLock()
        with self.assertRaises(RuntimeError):
            async with locks.hold((-100, 1)):
                raise RuntimeError("處理失敗")
        self.assertEqual(len(locks), 0)

        # 例外後同一則訊息仍可再次取得鎖
        async with locks.hold((-100, 1)):
            pass
        self.assertEqual(len(locks), 0)

    async def test_cancel_while_waiting_does_not_leak(self):
        locks = KeyedLock()
        release = asyncio.Event()
        holder_in = asyncio.Event()

        async def holder():
            async with locks.hold((-100, 1)):
                holder_in.set()
                await release.wait()

        async def waiter():
            async with locks.hold((-100, 1)):
                pass

        holder_task = asyncio.create_task(holder())
        await holder_in.wait()
        waiter_task = asyncio.create_task(waiter())
        await asyncio.sleep(0)
        waiter_task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await waiter_task

        release.set()
        await holder_task
        self.assertEqual(len(locks), 0)


class MessageLockKeyTests(unittest.TestCase):

    def test_same_message_from_different_paths_shares_key(self):
        # 即時事件的 event.message 與補掃的 iter_messages 結果是不同物件，key 必須相同
        live = SimpleNamespace(chat_id=-1002974889459, id=3223)
        catchup = SimpleNamespace(chat_id=-1002974889459, id=3223)
        self.assertEqual(message_lock_key(live), message_lock_key(catchup))

    def test_same_message_id_in_different_chats_does_not_collide(self):
        a = SimpleNamespace(chat_id=-1002974889459, id=100)
        b = SimpleNamespace(chat_id=-1002405953050, id=100)
        self.assertNotEqual(message_lock_key(a), message_lock_key(b))

    def test_missing_chat_id_falls_back_to_zero(self):
        self.assertEqual(message_lock_key(SimpleNamespace(chat_id=None, id=7)), (0, 7))


if __name__ == "__main__":
    unittest.main()
