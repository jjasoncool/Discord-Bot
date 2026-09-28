"""Telegram relay media group（相簿）收集與補圖的單元測試（假 repository / publisher，不需 DB、Discord）。

背景：scraper 逐則寫入相簿組員（先寫訊息列、下載完才寫媒體列），舊版 relay 只要 0.5 秒
數量沒變就合併送出，晚到的組員被當成「交由首則處理」丟掉 → 相簿只發出前 1~2 張。

執行：
    cd src && python -m unittest test.test_telegram_relay_media_group -v
"""

import asyncio
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from services.telegram_relay_service import (
    MessageRelayWorker,
    TelegramMediaRecord,
    TelegramMessageRecord,
)

# 刻意用不存在的假 id：logger 會寫進正式 log，用真實 id 會和線上相簿的合併紀錄混在一起
CHAT = -1009990000001
GID = 990000000000001
CHANNEL = 990000000000002


class FakeRepository:
    """只實作 worker 會用到的查詢；模擬 scraper「先寫列、後寫媒體」的寫入順序。"""

    def __init__(self) -> None:
        self.rows: dict[int, dict] = {}
        self.media: dict[int, list[TelegramMediaRecord]] = {}
        self.delivered: dict[tuple[int, int], datetime] = {}
        self.replay_pk = None

    def add_row(self, pk: int, msg_id: int, *, grouped_id=GID, text: str = "", has_media: bool = True) -> None:
        self.rows[pk] = {
            "chat": CHAT, "msg_id": msg_id, "gid": grouped_id, "text": text, "has_media": has_media,
        }

    def add_media(self, pk: int) -> None:
        self.media[pk] = [TelegramMediaRecord(file_rel_path=f"media/{pk}.jpg", media_type="photo")]

    def add_ready(self, pk: int, msg_id: int, **kwargs) -> None:
        self.add_row(pk, msg_id, **kwargs)
        self.add_media(pk)

    def mark(self, pk: int, when: datetime | None = None) -> None:
        self.delivered[(pk, CHANNEL)] = when or datetime.now(timezone.utc)

    async def get_message_by_pk(self, pk):
        row = self.rows.get(pk)
        if row is None:
            return None
        return TelegramMessageRecord(
            message_pk=pk,
            telegram_chat_id=row["chat"],
            telegram_message_id=row["msg_id"],
            text=row["text"],
            message_date=None,
            has_media=row["has_media"],
            grouped_id=row["gid"],
            media_items=list(self.media.get(pk, [])),
        )

    async def get_group_member_states(self, grouped_id, chat_id):
        members = sorted(
            (row["msg_id"], pk) for pk, row in self.rows.items()
            if row["gid"] == grouped_id and row["chat"] == chat_id
        )
        return [(pk, (not self.rows[pk]["has_media"]) or pk in self.media) for _, pk in members]

    async def get_delivered_at(self, message_pks, discord_channel_id):
        return {
            pk: self.delivered[(pk, discord_channel_id)]
            for pk in message_pks if (pk, discord_channel_id) in self.delivered
        }

    async def mark_message_published(self, pk, discord_channel_id):
        self.delivered[(pk, discord_channel_id)] = datetime.now(timezone.utc)

    async def is_message_published(self, pk, discord_channel_id):
        return (pk, discord_channel_id) in self.delivered

    async def set_runtime_cursor_pk(self, pk):
        pass

    async def get_pk_by_telegram_message_id(self, telegram_message_id, telegram_chat_id=None):
        return self.replay_pk


class FakeRouteResolver:
    def __init__(self) -> None:
        self.replay_msg_id = None

    def resolve_telegram_routes(self, chat_id):
        return [CHANNEL]

    def resolve_replay_msg_id(self, chat_id):
        return self.replay_msg_id


class FakeRenderAdapter:
    app_root = "/tmp"

    def render(self, message, emoji_map=None, title_suffix=""):
        return {
            "pks": message.message_pk,
            "media": [m.file_rel_path for m in message.media_items],
            "title_suffix": title_suffix,
            "text": message.text,
        }


class FakePublisher:
    def __init__(self) -> None:
        self.plans: list[dict] = []
        self.delay = 0.0
        self.on_publish = None

    async def publish_to_channel(self, channel, plan):
        self.plans.append(plan)
        if self.on_publish is not None:
            self.on_publish()
        if self.delay:
            await asyncio.sleep(self.delay)
        return 1


class FakeChannel:
    name = "leak"
    guild = None

    async def send(self, *args, **kwargs):
        pass


class FakeBot:
    def get_channel(self, channel_id):
        return FakeChannel()


def make_worker():
    repo = FakeRepository()
    routes = FakeRouteResolver()
    publisher = FakePublisher()
    worker = MessageRelayWorker(
        bot=FakeBot(),
        repository=repo,
        route_resolver=routes,
        render_adapter=FakeRenderAdapter(),
        publisher=publisher,
        dsn="",
    )
    # 測試用縮短等待；比例與正式值一致（輪詢 < 安靜期 < 上限）
    worker._GROUP_QUIET_SEC = 0.1
    worker._GROUP_POLL_INTERVAL = 0.01
    worker._GROUP_MAX_WAIT_SEC = 1.0
    return worker, repo, routes, publisher


def media_of(*pks):
    return [f"media/{pk}.jpg" for pk in pks]


class MediaGroupCollectTests(unittest.IsolatedAsyncioTestCase):

    async def test_members_written_one_by_one_are_sent_together(self):
        # 重現 GameData #3223：8 張逐則進來，每張「列先到、媒體後到」，間隔短於安靜期
        worker, repo, _, publisher = make_worker()
        pks = list(range(901, 909))
        repo.add_ready(pks[0], 5001, text="相簿說明")

        async def scraper():
            for i, pk in enumerate(pks[1:], start=1):
                await asyncio.sleep(0.03)
                repo.add_row(pk, 5001 + i)
                await asyncio.sleep(0.03)
                repo.add_media(pk)

        feeder = asyncio.create_task(scraper())
        await worker._process_one(pks[0])
        await feeder

        self.assertEqual(len(publisher.plans), 1)
        self.assertEqual(publisher.plans[0]["media"], media_of(*pks))
        self.assertEqual(publisher.plans[0]["title_suffix"], "")
        self.assertTrue(all((pk, CHANNEL) in repo.delivered for pk in pks))

    async def test_waits_for_member_whose_media_is_not_written_yet(self):
        # 組員數早就不變，但最後一則的媒體還在下載：不能先發
        worker, repo, _, publisher = make_worker()
        repo.add_ready(1, 100)
        repo.add_row(2, 101)

        async def finish_download():
            await asyncio.sleep(0.3)  # 超過安靜期好幾倍
            repo.add_media(2)

        feeder = asyncio.create_task(finish_download())
        await worker._process_one(1)
        await feeder

        self.assertEqual(len(publisher.plans), 1)
        self.assertEqual(publisher.plans[0]["media"], media_of(1, 2))

    async def test_member_arriving_during_collection_does_not_block_or_duplicate(self):
        worker, repo, _, publisher = make_worker()
        repo.add_ready(1, 100)
        repo.add_ready(2, 101)

        collector = asyncio.create_task(worker._process_one(1))
        await asyncio.sleep(0.02)
        # 組員 2 的 NOTIFY 在收集中到達：應立即返回，不等收集者
        await asyncio.wait_for(worker._process_one(2), timeout=0.05)
        await collector

        self.assertEqual(len(publisher.plans), 1)
        self.assertEqual(publisher.plans[0]["media"], media_of(1, 2))

    async def test_member_arriving_while_sending_is_sent_as_followup(self):
        worker, repo, _, publisher = make_worker()
        repo.add_ready(1, 100)
        repo.add_ready(2, 101)
        publisher.delay = 0.05

        def late_member_arrives():
            # 首批送出途中，第 3 張才寫進 DB 並 NOTIFY
            if len(publisher.plans) == 1:
                repo.add_ready(3, 102)
                asyncio.get_running_loop().create_task(worker._process_one(3))

        publisher.on_publish = late_member_arrives
        await worker._process_one(1)

        self.assertEqual([p["media"] for p in publisher.plans], [media_of(1, 2), media_of(3)])
        self.assertEqual(publisher.plans[1]["title_suffix"], "（補圖）")
        self.assertIn((3, CHANNEL), repo.delivered)

    async def test_late_member_after_group_sent_is_followup_not_dropped(self):
        # 舊版在這裡走「交由首則處理」直接丟棄
        worker, repo, _, publisher = make_worker()
        repo.add_ready(1, 100)
        repo.add_ready(2, 101)
        repo.mark(1)
        repo.mark(2)
        repo.add_ready(3, 102)

        await worker._process_one(3)

        self.assertEqual(len(publisher.plans), 1)
        self.assertEqual(publisher.plans[0]["media"], media_of(3))
        self.assertEqual(publisher.plans[0]["title_suffix"], "（補圖）")

    async def test_timeout_sends_ready_members_and_leaves_rest_for_followup(self):
        worker, repo, _, publisher = make_worker()
        worker._GROUP_MAX_WAIT_SEC = 0.2
        repo.add_ready(1, 100)
        repo.add_row(2, 101)  # 下載一直沒完成

        await worker._process_one(1)
        self.assertEqual(publisher.plans[0]["media"], media_of(1))
        self.assertNotIn((2, CHANNEL), repo.delivered)

        # 之後下載完成、NOTIFY 到達 → 以補圖送出
        repo.add_media(2)
        await worker._process_one(2)
        self.assertEqual(publisher.plans[1]["media"], media_of(2))
        self.assertEqual(publisher.plans[1]["title_suffix"], "（補圖）")

    async def test_stale_followup_is_skipped_without_waiting(self):
        # 重啟時 reconcile 會排入舊相簿沒標記的組員：過了補圖時效就不發，也不空等安靜期
        worker, repo, _, publisher = make_worker()
        worker._GROUP_QUIET_SEC = 5.0
        repo.add_ready(1, 100)
        repo.add_ready(2, 101)
        repo.mark(1, datetime.now(timezone.utc) - timedelta(hours=13))

        await asyncio.wait_for(worker._process_one(2), timeout=0.5)

        self.assertEqual(publisher.plans, [])
        self.assertNotIn((2, CHANNEL), repo.delivered)

    async def test_fully_delivered_group_exits_without_waiting(self):
        worker, repo, _, publisher = make_worker()
        worker._GROUP_QUIET_SEC = 5.0
        repo.add_ready(1, 100)
        repo.add_ready(2, 101)
        repo.mark(1)
        repo.mark(2)

        await asyncio.wait_for(worker._process_one(2), timeout=0.5)
        self.assertEqual(publisher.plans, [])

    async def test_force_replay_sends_group_once(self):
        worker, repo, routes, publisher = make_worker()
        routes.replay_msg_id = 100
        repo.replay_pk = 1
        repo.add_ready(1, 100)
        repo.add_ready(2, 101)
        repo.mark(1)
        repo.mark(2)

        await worker._process_one(1)
        await worker._process_one(2)  # 重送模式會把每個組員都排入，第二則不可再送一次

        self.assertEqual(len(publisher.plans), 1)
        self.assertEqual(publisher.plans[0]["media"], media_of(1, 2))

    async def test_caption_is_kept_when_first_member_has_text(self):
        worker, repo, _, publisher = make_worker()
        repo.add_ready(1, 100, text="公告")
        repo.add_ready(2, 101)

        await worker._process_one(2)  # 由非首則觸發也一樣整組送出

        self.assertEqual(publisher.plans[0]["text"], "公告")
        self.assertEqual(publisher.plans[0]["media"], media_of(1, 2))


class SingleMessageTests(unittest.IsolatedAsyncioTestCase):

    async def test_single_message_sent_once(self):
        worker, repo, _, publisher = make_worker()
        repo.add_ready(9, 200, grouped_id=None, text="hi")

        await worker._process_one(9)
        worker._processed_set.clear()
        await worker._process_one(9)  # 已有 delivery 記錄 → 不重送

        self.assertEqual(len(publisher.plans), 1)
        self.assertIn((9, CHANNEL), repo.delivered)


if __name__ == "__main__":
    unittest.main()
