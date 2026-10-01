"""聊天訊息寫進 pgvector 時，後端連不上不能讓訊息消失。

守的底線：
  聊天表是 /askai RAG、插話回憶、04:00 人格萃取與 persona agent 共用的資料來源，
  漏寫的訊息這些地方全都看不到。
  1. embedding 後端（Lemonade）或 pgvector 連不上：沒寫成的訊息放回 buffer、維持原本順序，
     恢復後下一輪補寫；而且遇到第一則連不上就停，不逐則硬試（硬試會長時間佔住 GPU 閘門）。
  2. 跟連線無關的錯誤（某則訊息本身有問題）照舊略過，不能讓一則壞訊息永遠重試。
  3. buffer 有上限，超過丟最舊的、保留最新的，並記一行 log 說丟了幾則。
  4. 失敗後不會「每來一則新訊息就再開一次 flush」：同一時間只跑一個 flush，
     失敗後暫停滿門檻觸發，只靠定期 flush 重試；恢復後滿門檻觸發也跟著恢復。
  5. 編輯過的訊息：先刪舊向量後才連不上的，也要放回去補寫，不能從聊天表消失；
     flush 期間又被編輯的，以較新的文字為準。
"""

import asyncio
import os
import sys
import threading
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from sqlalchemy.exc import OperationalError

from llm.client.http_client import LlmAPIError, LlmConnectionError, LlmTimeoutError
from llm.storage import store_chat


def _msg(mid: int, text: str = "今天的深塔好難") -> SimpleNamespace:
    """最小的 discord.Message 替身：只帶 store_chat 會讀的欄位。"""
    return SimpleNamespace(
        id=mid,
        content=text,
        stickers=[],
        embeds=[],
        author=SimpleNamespace(bot=False, id=7),
        channel=SimpleNamespace(id=10),
        guild=SimpleNamespace(id=100),
        created_at=datetime(2026, 10, 1, tzinfo=timezone.utc) + timedelta(seconds=mid),
    )


class FakeIndex:
    """假的 VectorStoreIndex：記錄寫了哪些、依設定對特定訊息或全部丟錯。"""

    def __init__(self) -> None:
        self.inserted: list[tuple[str, str]] = []
        self.deleted: list[str] = []
        self.insert_calls = 0
        self.down: Exception | None = None       # 設了就每次 insert / delete 都丟這個
        self.fail: dict[str, Exception] = {}     # 只對特定 message_id 丟錯
        self.on_insert = None                    # 測試用掛勾：insert 開始時呼叫
        self.on_delete = None

    def insert(self, doc) -> None:
        self.insert_calls += 1
        if self.on_insert:
            self.on_insert(doc)
        if self.down:
            raise self.down
        if doc.doc_id in self.fail:
            raise self.fail[doc.doc_id]
        self.inserted.append((doc.doc_id, doc.text))

    def delete_ref_doc(self, mid: str) -> None:
        if self.on_delete:
            self.on_delete(mid)
        self.deleted.append(mid)

    def ids(self) -> list[str]:
        return [mid for mid, _ in self.inserted]


class ChatPersistRetryTests(unittest.IsolatedAsyncioTestCase):

    def setUp(self) -> None:
        store_chat._buffer.clear()
        store_chat._edit_buffer.clear()
        store_chat._flush_running = False
        store_chat._threshold_paused_until = 0.0
        store_chat._dropped_overflow = 0
        self.persisted: set[str] = set()
        self.index = FakeIndex()
        for target, value in (
            ("_check_flush_deps", lambda: True),
            ("_get_chat_index", lambda: self.index),
            ("_get_persisted_ids", lambda: self.persisted),
            ("_buffer_lock", asyncio.Lock()),
        ):
            p = patch.object(store_chat, target, value)
            p.start()
            self.addCleanup(p.stop)

    def tearDown(self) -> None:
        store_chat._buffer.clear()
        store_chat._edit_buffer.clear()

    @staticmethod
    def buffer_ids() -> list[str]:
        return [item["message_id"] for item in store_chat._buffer]

    # ---- 1. 連不上：放回、維持順序、恢復後補寫 ----

    async def test_unreachable_backend_keeps_messages_until_it_recovers(self):
        for exc in (
            LlmConnectionError("connection refused"),
            LlmTimeoutError("timed out"),
            OperationalError("INSERT", {}, Exception("pgvector down")),
        ):
            with self.subTest(error=type(exc).__name__):
                self.setUp()
                for mid in range(1, 6):
                    store_chat.enqueue_message(_msg(mid))
                self.index.fail = {"3": exc}

                with self.assertLogs(store_chat.logger, "WARNING"):
                    written = await store_chat.flush_buffer()

                self.assertEqual(written, 2)
                self.assertEqual(self.index.ids(), ["1", "2"])
                self.assertEqual(self.buffer_ids(), ["3", "4", "5"])
                # 停在第一則連不上的，沒有繼續硬試後面幾則
                self.assertEqual(self.index.insert_calls, 3)

                # 斷線期間的新訊息排在放回的後面；恢復後全部依序補上
                store_chat.enqueue_message(_msg(6))
                self.index.fail = {}
                await store_chat.flush_buffer()
                self.assertEqual(self.index.ids(), ["1", "2", "3", "4", "5", "6"])
                self.assertEqual(store_chat._buffer, [])

    async def test_index_unavailable_requeues_whole_batch(self):
        for mid in (1, 2):
            store_chat.enqueue_message(_msg(mid))

        def broken():
            raise OperationalError("connect", {}, Exception("pgvector down"))

        with patch.object(store_chat, "_get_chat_index", broken):
            with self.assertLogs(store_chat.logger, "WARNING"):
                await store_chat.flush_buffer()
        self.assertEqual(self.buffer_ids(), ["1", "2"])

    # ---- 2. 壞訊息不永遠重試 ----

    async def test_message_specific_error_is_skipped_not_retried(self):
        for mid in (1, 2, 3):
            store_chat.enqueue_message(_msg(mid))
        self.index.fail = {"2": LlmAPIError("HTTP 400", status=400)}

        with self.assertLogs(store_chat.logger, "WARNING"):
            await store_chat.flush_buffer()

        self.assertEqual(self.index.ids(), ["1", "3"])
        self.assertEqual(store_chat._buffer, [])
        self.assertEqual(store_chat._threshold_paused_until, 0.0)

    # ---- 3. 上限：丟最舊、留最新、記 log ----

    async def test_buffer_cap_drops_oldest_and_reports_it(self):
        with patch.object(store_chat, "MAX_BUFFER_SIZE", 5):
            for mid in range(1, 9):
                store_chat.enqueue_message(_msg(mid))
            self.assertEqual(self.buffer_ids(), ["4", "5", "6", "7", "8"])

            with self.assertLogs(store_chat.logger, "WARNING") as logs:
                await store_chat.flush_buffer()
            self.assertTrue(any("丟棄最舊的 3 則" in line for line in logs.output))

    async def test_requeue_respects_cap_and_keeps_newest(self):
        with patch.object(store_chat, "MAX_BUFFER_SIZE", 5):
            for mid in range(1, 6):
                store_chat.enqueue_message(_msg(mid))
            self.index.down = LlmConnectionError("connection refused")

            # flush 進行中又來了 3 則新訊息
            def arrive(_doc):
                if self.index.insert_calls == 1:
                    for mid in (6, 7, 8):
                        store_chat.enqueue_message(_msg(mid))
            self.index.on_insert = arrive

            with self.assertLogs(store_chat.logger, "WARNING"):
                await store_chat.flush_buffer()
            self.assertEqual(self.buffer_ids(), ["4", "5", "6", "7", "8"])

    # ---- 4. 不會變成 flush 風暴 ----

    async def test_failure_pauses_threshold_trigger_but_not_periodic_flush(self):
        for mid in range(1, store_chat.FLUSH_THRESHOLD + 1):
            store_chat.enqueue_message(_msg(mid))
        self.assertTrue(store_chat.should_flush_now())

        self.index.down = LlmConnectionError("connection refused")
        with self.assertLogs(store_chat.logger, "WARNING"):
            await store_chat.flush_buffer()
        store_chat.enqueue_message(_msg(999))
        self.assertGreater(len(store_chat._buffer), store_chat.FLUSH_THRESHOLD)
        self.assertFalse(store_chat.should_flush_now())

        # 定期 flush 仍照常重試；成功後滿門檻觸發恢復
        self.index.down = None
        await store_chat.flush_buffer()
        self.assertEqual(len(self.index.inserted), store_chat.FLUSH_THRESHOLD + 1)
        for mid in range(1001, 1001 + store_chat.FLUSH_THRESHOLD):
            store_chat.enqueue_message(_msg(mid))
        self.assertTrue(store_chat.should_flush_now())

    async def test_only_one_flush_runs_at_a_time(self):
        store_chat.enqueue_message(_msg(1))
        entered, release = threading.Event(), threading.Event()

        def block(_doc):
            entered.set()
            release.wait(5)
        self.index.on_insert = block

        first = asyncio.create_task(store_chat.flush_buffer())
        await asyncio.to_thread(entered.wait, 5)

        store_chat.enqueue_message(_msg(2))
        with patch.object(store_chat, "FLUSH_THRESHOLD", 1):
            self.assertFalse(store_chat.should_flush_now())
        self.assertEqual(await store_chat.flush_buffer(), 0)
        self.assertEqual(self.buffer_ids(), ["2"])   # 第二個 flush 沒有把它拿走

        release.set()
        await first
        self.index.on_insert = None
        await store_chat.flush_buffer()
        self.assertEqual(self.index.ids(), ["1", "2"])

    # ---- 5. 編輯 ----

    async def test_edit_deleted_then_unreachable_is_rewritten_later(self):
        self.persisted.update({"1", "2"})
        store_chat.enqueue_message_edit(_msg(1, "改過的第一則"))
        store_chat.enqueue_message_edit(_msg(2, "改過的第二則"))
        self.index.down = LlmConnectionError("connection refused")

        with self.assertLogs(store_chat.logger, "WARNING"):
            await store_chat.flush_buffer()
        # 舊向量已經刪了，但這則要留著等補寫
        self.assertEqual(self.index.deleted, ["1"])
        self.assertEqual([i["message_id"] for i in store_chat._edit_buffer], ["1", "2"])

        self.index.down = None
        await store_chat.flush_buffer()
        self.assertEqual(self.index.inserted, [("1", "改過的第一則"), ("2", "改過的第二則")])
        self.assertEqual(store_chat._edit_buffer, [])

    async def test_edit_during_failed_flush_keeps_newer_text(self):
        self.persisted.add("1")
        store_chat.enqueue_message_edit(_msg(1, "第一版"))

        def edited_again(_mid):
            store_chat.enqueue_message_edit(_msg(1, "第二版"))
            raise LlmConnectionError("connection refused")
        self.index.on_delete = edited_again

        with self.assertLogs(store_chat.logger, "WARNING"):
            await store_chat.flush_buffer()
        self.assertEqual([i["text"] for i in store_chat._edit_buffer], ["第二版"])

    async def test_insert_failure_skips_edit_attempt(self):
        self.persisted.add("9")
        store_chat.enqueue_message(_msg(1))
        store_chat.enqueue_message_edit(_msg(9, "改過"))
        self.index.down = LlmConnectionError("connection refused")

        with self.assertLogs(store_chat.logger, "WARNING"):
            await store_chat.flush_buffer()
        self.assertEqual(self.index.deleted, [])     # 沒有去刪舊向量
        self.assertEqual(self.buffer_ids(), ["1"])
        self.assertEqual([i["message_id"] for i in store_chat._edit_buffer], ["9"])


if __name__ == "__main__":
    unittest.main()
