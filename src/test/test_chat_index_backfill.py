"""從 raw 備份補寫聊天向量庫漏掉的訊息（llm/storage/chat_index_backfill.py，寫入交給 store_chat）。

守的底線：
  聊天向量庫是 /askai、插話回憶、人格萃取共用的資料；停機前還在記憶體裡的訊息沒寫進去，這些地方就永遠看不到。
  1. 即時寫入的文字長這樣：內文（自訂表情換描述）＋「[貼圖：…]」＋「[預覽：標題 - 描述前 100 字]」；補寫組出來的和它
     一模一樣，欄位也一樣：討論串裡的訊息記討論串本身、時間是 UTC 的 isoformat（資料庫回來的時區可能是 +08:00）。
  2. 組出來太短、即時寫入本來就不寫的不排；而且之後的查詢跳過它們，不會一直佔住每輪的名額。
  3. 排進聊天記憶 buffer 的前端（較舊的先寫）；已寫過、已在 buffer 裡的不重複排，也回報出來讓之後跳過；
     buffer 快滿時只用剩下的空間，不擠掉即時的訊息。
  4. 查詢範圍：往回 WINDOW_DAYS 天；這個行程啟動後建立的、最近 SETTLE_MINUTES 分鐘內的不查（可能還在緩衝裡），
     啟動前建立的不必等（停機前那幾分鐘，第一輪就補得到）。
  5. 開關：off 不查資料庫；dry_run 只記 log（會排幾則、跳過幾則、太短幾則）、不排；on 才排，排過、跳過的之後不再查。

不連資料庫：查詢函式換成假的；store_chat 的 buffer 每個測試前後清空、已寫入集合換成測試自己的。
真的資料庫上的查詢見 test/integration/it_chat_index_backfill.py（手動執行）。
"""

import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from llm.storage import chat_index_backfill as backfill  # noqa: E402
from llm.storage import store_chat  # noqa: E402
from sys_settings.switches import Switches  # noqa: E402

TAIPEI = timezone(timedelta(hours=8))
TENOR_URL = "https://tenor.com/view/dance-12345"
LONG_DESCRIPTION = "很長的描述" * 40


def raw_row(message_id="1", content="今天的深塔好難", *, stickers=None, tenor_gifs=None, thread_id=None,
            created_at=datetime(2026, 10, 15, 13, 5, 1, 802000, tzinfo=TAIPEI)):
    """raw 表一列（查詢會拿回來的欄位）。"""
    return {
        "message_id": message_id, "guild_id": "100", "channel_id": "10", "thread_id": thread_id,
        "author_id": "7", "content": content, "stickers": stickers, "tenor_gifs": tenor_gifs,
        "created_at": created_at, "candidates": 1,
    }


def live_message(content):
    return SimpleNamespace(
        content=content,
        stickers=[SimpleNamespace(id=55, name="貓咪")],
        embeds=[SimpleNamespace(title="跳舞", description=LONG_DESCRIPTION, url=TENOR_URL)],
    )


class StoreChatStateMixin:
    def setUp(self):
        store_chat._buffer.clear()
        store_chat._edit_buffer.clear()
        self.persisted: set[str] = set()
        patcher = mock.patch.object(store_chat, "_get_persisted_ids", lambda: self.persisted)
        patcher.start()
        self.addCleanup(patcher.stop)
        backfill._skip_ids.clear()
        self.addCleanup(backfill._skip_ids.clear)
        self.addCleanup(store_chat._buffer.clear)
        self.addCleanup(store_chat._edit_buffer.clear)


class BuildItemsTests(unittest.TestCase):
    def test_live_text_is_pinned(self):
        """兩條路徑共用同一個組字函式：只比兩邊一不一樣的話，共用的地方改壞了兩邊一起變，看不出來。"""
        with mock.patch.object(store_chat, "replace_custom_emoji_with_description",
                               side_effect=lambda text: text.replace("<:smile:1>", ":微笑:")):
            text = store_chat._build_persist_text(live_message("  好耶 <:smile:1> "))

        self.assertEqual(text, f"好耶 :微笑: [貼圖：貓咪] [預覽：跳舞 - {LONG_DESCRIPTION[:100]}]")

    def test_backfill_text_is_the_same_as_the_live_path(self):
        content = "  好耶 <:smile:123456789012345678> "
        row = raw_row(
            content=content,
            stickers=[{"id": "55", "name": "貓咪", "format_type": 1}],
            tenor_gifs=[{"url": TENOR_URL, "title": "跳舞", "description": LONG_DESCRIPTION[:200]}],
        )

        items, too_short = backfill.build_items([row])

        self.assertEqual(too_short, [])
        self.assertEqual(items[0]["text"], store_chat._build_persist_text(live_message(content)))

    def test_fields_match_the_live_path(self):
        items, _ = backfill.build_items([
            raw_row("1"),
            raw_row("2", thread_id="20"),
        ])

        plain, in_thread = items
        self.assertEqual(plain["channel_id"], "10")
        self.assertEqual(in_thread["channel_id"], "20", "討論串裡的訊息記討論串本身（即時寫入用 msg.channel.id）")
        self.assertEqual(plain["timestamp"], "2026-10-15T05:05:01.802000+00:00", "時間轉回 UTC")
        self.assertEqual({k: plain[k] for k in ("message_id", "author_id", "guild_id")},
                         {"message_id": "1", "author_id": "7", "guild_id": "100"})

    def test_text_too_short_is_not_queued_and_reported(self):
        items, too_short = backfill.build_items([raw_row("1", content=" 嗯 "), raw_row("2")])

        self.assertEqual([item["message_id"] for item in items], ["2"])
        self.assertEqual(too_short, ["1"])


class EnqueueBackfillTests(StoreChatStateMixin, unittest.TestCase):
    def _items(self, *ids):
        return [{"message_id": i, "text": f"訊息{i}", "author_id": "7", "channel_id": "10", "guild_id": "100",
                 "timestamp": "2026-10-15T05:05:01+00:00"} for i in ids]

    def test_goes_to_the_front_and_skips_what_is_written_or_queued(self):
        store_chat._buffer.extend(self._items("9"))   # 即時進來、還沒寫的
        self.persisted.add("2")                        # 已寫過的（或這個行程記成寫過的）

        queued, skipped = store_chat.enqueue_backfill(self._items("1", "2", "9", "3"))

        self.assertEqual(queued, ["1", "3"])
        self.assertEqual(sorted(skipped), ["2", "9"])
        self.assertEqual([item["message_id"] for item in store_chat._buffer], ["1", "3", "9"])

    def test_only_uses_the_room_left(self):
        store_chat._buffer.extend(self._items("9"))
        with mock.patch.object(store_chat, "MAX_BUFFER_SIZE", 2):
            queued, _ = store_chat.enqueue_backfill(self._items("1", "2"))

        self.assertEqual(queued, ["1"])
        self.assertEqual([item["message_id"] for item in store_chat._buffer], ["1", "9"], "即時的那則不能被擠掉")


class RunOnceTests(StoreChatStateMixin, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        self.fetch_calls: list[dict] = []
        self.rows = [raw_row("1", content="嗯"), raw_row("2"), raw_row("3")]

        def fake_fetch(since, until, limit, skip):
            self.fetch_calls.append({"since": since, "until": until, "limit": limit, "skip": list(skip)})
            return len(self.rows), [r for r in self.rows if r["message_id"] not in skip]

        patcher = mock.patch.object(backfill, "_fetch_missing", fake_fetch)
        patcher.start()
        self.addCleanup(patcher.stop)
        long_ago = mock.patch.object(backfill, "_STARTED_AT", datetime(2000, 1, 1, tzinfo=timezone.utc))
        long_ago.start()
        self.addCleanup(long_ago.stop)

    def _mode(self, mode):
        return mock.patch.object(backfill.switches, "current",
                                 return_value=Switches(chat_index_backfill_mode=mode))

    async def test_off_does_not_query(self):
        with self._mode("off"):
            self.assertEqual(await backfill.run_once(), 0)
        self.assertEqual(self.fetch_calls, [])
        self.assertEqual(store_chat._buffer, [])

    async def test_dry_run_only_logs_what_it_would_do(self):
        self.persisted.add("3")
        with self._mode("dry_run"), self.assertLogs(backfill.logger, level="INFO") as logs:
            self.assertEqual(await backfill.run_once(), 0)
        self.assertEqual(store_chat._buffer, [])
        self.assertIn("dry_run", logs.output[0])
        self.assertIn("會排 1、已在佇列或已記成寫過 1、太短 1", logs.output[0])

    async def test_on_queues_and_later_queries_skip_what_was_handled(self):
        self.persisted.add("3")   # 這個行程記成寫過、資料庫卻查到缺（例如長訊息沒寫成）：跳過，下一輪也不再查

        with self._mode("on"):
            first = await backfill.run_once()
            second = await backfill.run_once()

        self.assertEqual(first, 1)
        self.assertEqual(second, 0)
        self.assertEqual([item["message_id"] for item in store_chat._buffer], ["2"])
        self.assertEqual(sorted(self.fetch_calls[1]["skip"]), ["1", "2", "3"],
                         "排過的、跳過的、太短不寫的，下一輪都不再查")

    async def test_query_window(self):
        before = datetime.now(timezone.utc)
        with self._mode("on"):
            await backfill.run_once()
        after = datetime.now(timezone.utc)

        call = self.fetch_calls[0]
        settle = timedelta(minutes=backfill.SETTLE_MINUTES)
        window = timedelta(days=backfill.WINDOW_DAYS)
        self.assertTrue(before - settle <= call["until"] <= after - settle, "最近幾分鐘的可能還在緩衝裡")
        self.assertTrue(before - window <= call["since"] <= after - window)
        self.assertEqual(call["limit"], backfill.BATCH_LIMIT)
        self.assertLess(backfill.BATCH_LIMIT, store_chat.FLUSH_THRESHOLD, "一輪補寫不該自己就觸發一次提早寫入")

    async def test_messages_from_before_this_process_started_need_not_settle(self):
        started = datetime.now(timezone.utc) - timedelta(minutes=2)
        with mock.patch.object(backfill, "_STARTED_AT", started), self._mode("on"):
            await backfill.run_once()

        self.assertEqual(self.fetch_calls[0]["until"], started, "停機前那幾分鐘不在這個行程的緩衝裡，第一輪就要查得到")


if __name__ == "__main__":
    unittest.main()
