"""面板置底共用元件（utils/panel_bump.py）。

守的底線：
- 有紀錄：只刪紀錄那一則（一次 API），發新面板後把頻道＋訊息 id 寫回 runtime 檔
- 寫 runtime 檔時不動檔案裡的其他欄位（週期提醒的 role_id 跟面板位置放同一個檔）
- 沒有完整紀錄：翻最近訊息，只刪「bot 自己發、custom_id 精確屬於這個面板」的殘留面板
- 連發合併：一口氣來很多次置底請求，最多只會一次在跑、一次排隊

執行：
    cd src && python -m unittest test.test_panel_bump -v
"""

import asyncio
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

import discord

from utils.panel_bump import PanelBumper, load_runtime, update_runtime

BOT_ID = 1
PANEL_IDS = ("panel:a", "panel:b")


def _history_message(message_id, *, author_id=BOT_ID, custom_ids=()):
    message = MagicMock()
    message.id = message_id
    message.author.id = author_id
    row = MagicMock()
    row.children = [MagicMock(custom_id=cid) for cid in custom_ids]
    message.components = [row] if custom_ids else []
    message.delete = AsyncMock()
    return message


def _channel(channel_id=500, history=()):
    channel = MagicMock(spec=discord.TextChannel)
    channel.id = channel_id
    channel.guild.me.id = BOT_ID
    channel.send = AsyncMock(side_effect=lambda **_: MagicMock(id=900 + channel.send.await_count))
    old_message = MagicMock()
    old_message.delete = AsyncMock()
    channel.get_partial_message.return_value = old_message

    async def _history(limit):
        for message in list(history)[:limit]:
            yield message
    channel.history = MagicMock(side_effect=_history)
    return channel


class BumperTestBase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "runtime.json")

    def tearDown(self):
        self.tmp.cleanup()

    def bumper(self, **kwargs):
        async def send(channel):
            return await channel.send(content="panel")
        return PanelBumper(self.path, send, custom_ids=PANEL_IDS, **kwargs)


class BumpWithRecordTests(BumperTestBase):
    async def test_deletes_recorded_panel_and_saves_new_location(self):
        update_runtime(self.path, panel_channel_id=500, panel_message_id=111)
        channel = _channel()

        message, deleted_old = await self.bumper().bump(channel)

        self.assertTrue(deleted_old)
        channel.get_partial_message.assert_called_once_with(111)
        channel.history.assert_not_called()  # 有紀錄就不翻訊息
        self.assertEqual(load_runtime(self.path), {"panel_channel_id": 500, "panel_message_id": message.id})

    async def test_old_panel_in_another_channel(self):
        update_runtime(self.path, panel_channel_id=400, panel_message_id=111)
        old_channel = _channel(400)
        channel = _channel(500)
        channel.guild.get_channel.return_value = old_channel

        _, deleted_old = await self.bumper().bump(channel)

        self.assertTrue(deleted_old)
        channel.guild.get_channel.assert_called_once_with(400)
        old_channel.get_partial_message.assert_called_once_with(111)

    async def test_already_deleted_panel_is_fine(self):
        update_runtime(self.path, panel_channel_id=500, panel_message_id=111)
        channel = _channel()
        channel.get_partial_message.return_value.delete.side_effect = discord.NotFound(MagicMock(status=404), "gone")

        message, deleted_old = await self.bumper().bump(channel)

        self.assertFalse(deleted_old)
        self.assertEqual(load_runtime(self.path)["panel_message_id"], message.id)

    async def test_keeps_other_fields_and_key_prefix(self):
        update_runtime(self.path, role_id=42, intro_panel_channel_id=500, intro_panel_message_id=111)
        await self.bumper(key_prefix="intro_panel_").bump(_channel())
        data = load_runtime(self.path)
        self.assertEqual(data["role_id"], 42)
        self.assertNotIn("panel_message_id", data)
        self.assertNotEqual(data["intro_panel_message_id"], 111)


class BumpWithoutRecordTests(BumperTestBase):
    async def test_scans_and_deletes_only_this_panel(self):
        stray = _history_message(10, custom_ids=("panel:a",))
        other_button = _history_message(11, custom_ids=("panel:control",))  # 同功能的其他按鈕
        human = _history_message(12, author_id=99, custom_ids=("panel:a",))  # 不是 bot 發的
        plain = _history_message(13)
        channel = _channel(history=[stray, other_button, human, plain])

        _, deleted_old = await self.bumper().bump(channel)

        self.assertTrue(deleted_old)
        stray.delete.assert_awaited_once()
        other_button.delete.assert_not_awaited()
        human.delete.assert_not_awaited()
        plain.delete.assert_not_awaited()
        channel.history.assert_called_once_with(limit=50)

    async def test_message_id_only_record_scans(self):
        # 舊版自介只記了訊息 id、沒記頻道 id：當成沒有完整紀錄
        update_runtime(self.path, intro_panel_message_id=111)
        stray = _history_message(111, custom_ids=("panel:b",))
        channel = _channel(history=[stray])

        await self.bumper(key_prefix="intro_panel_").bump(channel)

        stray.delete.assert_awaited_once()
        self.assertEqual(load_runtime(self.path)["intro_panel_channel_id"], 500)


class RequestBumpTests(BumperTestBase):
    async def test_burst_is_merged(self):
        bumper = self.bumper()
        gate = asyncio.Event()
        calls = []
        running = {"now": 0, "max": 0}

        async def slow_bump(channel):
            calls.append(channel)
            running["now"] += 1
            running["max"] = max(running["max"], running["now"])
            await gate.wait()
            running["now"] -= 1
        bumper.bump_safe = slow_bump
        channel = _channel()

        for _ in range(10):
            bumper.request_bump(channel)
        await asyncio.sleep(0)  # 第一次開始跑
        for _ in range(10):
            bumper.request_bump(channel)  # 跑的期間又來 10 次
        gate.set()
        await bumper._drain_task

        self.assertEqual(len(calls), 2)  # 一次在跑、一次排隊
        self.assertEqual(running["max"], 1)  # 同一時間只跑一次


class RuntimeFileTests(unittest.TestCase):
    def test_missing_or_broken_file_reads_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "x.json")
            self.assertEqual(load_runtime(path), {})
            with open(path, "w", encoding="utf-8") as f:
                f.write("{broken")
            self.assertEqual(load_runtime(path), {})
            update_runtime(path, a=1)
            with open(path, encoding="utf-8") as f:
                self.assertEqual(json.load(f), {"a": 1})


if __name__ == "__main__":
    unittest.main()
