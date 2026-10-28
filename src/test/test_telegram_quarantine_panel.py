"""Telegram 隔離區的面板與放回（commands/telegram_quarantine_commands.py、轉發端 quarantine_items／restore）。

守的底線：
- 選單只列被隔離、還沒放回的；相簿算一項；依發文時間排；有文字顯示文字開頭，沒文字顯示「圖片 ×N」「影片」
- 日期新的在前、最多 25 天；標示「MM/DD（N 則）」
- 放回：照正常流程送回主頻道（相簿連同補圖合成一則、不重判、沒有判定那行）、寫主頻道的發送紀錄；
  隔離那則（含補圖）加上「已由 X 放回主頻道」；放回後不再出現在選單；同一則只會送一次（兩人同時按也是）
- 放回失敗（主頻道送不出去）：隔離那則不改、選單裡還選得到
- 放回過的相簿，之後晚到的圖跟著主頻道走
- 只有「管理訊息」權限的人能操作；沒權限按了只回「沒有權限」，什麼都不送
- 選了訊息不會馬上送：先跳只有自己看得到的確認（附隔離那則的連結），按「放回主頻道」才送；
  按下後先拿掉按鈕避免連按
- 選日期後面板重畫成沒選取（不然再選同一天 Discord 不會通知 bot）
- 有新的隔離訊息或放回時，面板置底（刪舊發新）並更新日期
- 面板、訊息選單、確認按鈕的 custom_id 重啟後解析得回原本的日期與訊息

執行：
    cd src && python -m unittest test.test_telegram_quarantine_panel -v
"""
import asyncio
import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

import discord

from commands import telegram_quarantine_commands as tqc
from services.relay.telegram_relay_service import QuarantineItem
from test.telegram_relay_fakes import CHANNEL, FakeBot, FakeFilter, make_worker, media_of
from utils import utils as bot_utils

TZ8 = timezone(timedelta(hours=8))


def at(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, day, hour, minute, tzinfo=TZ8)


class QuarantineTestBase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.filter = FakeFilter("on")
        self.bot = FakeBot()
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        self.runtime = str(Path(tmp) / "quarantine_runtime.json")
        self.worker, self.repo, self.routes, self.publisher = make_worker(
            content_filter=self.filter, quarantine=True, bot=self.bot, runtime_path=self.runtime,
        )
        self.worker._running = True
        # 測試資料用固定的十月日期（日期選單的標籤要比對），不能被「發文太久不送」擋掉
        self.worker._max_message_age = timedelta(days=36500)
        self.changes = []

        async def on_change(parent_id, thread):
            self.changes.append((parent_id, thread.id))
        self.worker._quarantine.on_change = on_change

    def thread(self):
        return self.bot.main.all_threads[-1]

    async def quarantine_single(self, pk, text="今日首水", *, date=None):
        self.repo.add_row(pk, 200 + pk, grouped_id=None, text=text, has_media=False, date=date)
        self.filter.quarantine(pk, "灌水", "每日打卡")
        await self.worker._process_one(pk)

    async def quarantine_album(self, pks, gid=77, text="說明", date=None):
        for n, pk in enumerate(pks):
            self.repo.add_ready(pk, 500 + pk, grouped_id=gid, text=text if n == 0 else "", date=date)
        self.filter.quarantine(pks[0], "無關圖片", "奶龍")
        await self.worker._process_one(pks[0])


class ListTests(QuarantineTestBase):
    async def test_lists_unrestored_units_with_media_counts(self):
        await self.quarantine_single(9, date=at(6, 12, 3))
        await self.quarantine_album([1, 2, 3], date=at(5, 9))
        self.repo.add_row(20, 220, grouped_id=None, text="", date=at(6, 15))
        self.repo.media[20] = [SimpleNamespace(file_rel_path="media/20.mp4", media_type="video",
                                               mime_type="video/mp4", is_spoiler=False)]
        self.filter.quarantine(20, "無關圖片", "別款遊戲")
        await self.worker._process_one(20)

        items = await self.worker.quarantine_items(CHANNEL)
        self.assertEqual([i.pk for i in items], [1, 9, 20], "依發文時間排，相簿算一項（代表是第一張）")
        album = items[0]
        self.assertEqual((album.text, album.image_count, album.video_count), ("說明", 3, 0))
        self.assertEqual((items[2].image_count, items[2].video_count), (0, 1))

    async def test_restored_ones_are_not_listed(self):
        await self.quarantine_single(9)
        await self.quarantine_single(10, "今天还水吗")
        await self.worker.restore(9, "小明")
        self.assertEqual([i.pk for i in await self.worker.quarantine_items(CHANNEL)], [10])


class RestoreTests(QuarantineTestBase):
    async def test_restore_single(self):
        await self.quarantine_single(9)
        thread = self.thread()
        ok, message = await self.worker.restore(9, "小明")
        self.assertTrue(ok, message)

        [plan] = self.publisher.to(CHANNEL)
        self.assertEqual((plan.header, plan["title_suffix"]), ("", ""), "放回主頻道的不帶判定、也不是補圖")
        self.assertEqual(len(self.filter.calls), 1, "放回不重判")
        self.assertEqual(self.repo.channels_of(9), {CHANNEL, thread.id})
        [quarantined] = thread.messages[:1]
        self.assertIn("判定：灌水｜每日打卡", quarantined.content)
        self.assertIn("已由 小明 放回主頻道", quarantined.content)

        again, _ = await self.worker.restore(9, "小華")
        self.assertFalse(again)
        self.assertEqual(len(self.publisher.to(CHANNEL)), 1, "同一則只送一次")

    async def test_restore_album_with_followup_as_one_post(self):
        await self.quarantine_album([1, 2])
        thread = self.thread()
        self.repo.add_ready(3, 503, grouped_id=77)   # 晚到的組員以補圖進隔離區
        await self.worker._process_one(3)
        self.assertEqual(len(self.publisher.to(thread.id)), 2)

        ok, _ = await self.worker.restore(1, "小明")
        self.assertTrue(ok)
        [plan] = self.publisher.to(CHANNEL)
        self.assertEqual(plan["media"], media_of(1, 2, 3), "相簿連同補圖合成一則")
        marked = [m for m in thread.messages if m.content and "已由 小明 放回主頻道" in m.content]
        self.assertEqual(len(marked), 2, "第一次送出與補圖兩則都標上")

    async def test_late_image_after_restore_goes_to_main(self):
        await self.quarantine_album([1, 2])
        thread = self.thread()
        await self.worker.restore(1, "小明")
        self.repo.add_ready(3, 503, grouped_id=77)
        await self.worker._process_one(3)
        plans = self.publisher.to(CHANNEL)
        self.assertEqual([p["media"] for p in plans], [media_of(1, 2), media_of(3)])
        self.assertEqual(plans[1]["title_suffix"], "（補圖）")
        self.assertEqual(len(self.publisher.to(thread.id)), 1, "放回後的補圖不再進隔離區")

    async def test_failed_restore_leaves_it_in_quarantine(self):
        await self.quarantine_single(9)
        thread = self.thread()
        self.publisher.fail_channels.add(CHANNEL)
        ok, _ = await self.worker.restore(9, "小明")
        self.assertFalse(ok)
        self.assertNotIn("已由", thread.messages[0].content)
        self.assertEqual([i.pk for i in await self.worker.quarantine_items(CHANNEL)], [9], "選單裡還選得到")

    async def test_two_admins_at_once_send_once(self):
        await self.quarantine_single(9)
        self.publisher.delay = 0.05
        results = await asyncio.gather(self.worker.restore(9, "小明"), self.worker.restore(9, "小華"))
        self.assertEqual(sorted(ok for ok, _ in results), [False, True])
        self.assertEqual(len(self.publisher.to(CHANNEL)), 1)

    async def test_album_being_collected_is_not_restored(self):
        await self.quarantine_album([1, 2])
        self.worker._active_groups.add((self.repo.rows[1]["chat"], 77))
        ok, message = await self.worker.restore(1, "小明")
        self.assertFalse(ok)
        self.assertIn("處理中", message)
        self.assertEqual(self.publisher.to(CHANNEL), [])

    async def test_image_arriving_during_restore_goes_to_main(self):
        await self.quarantine_album([1, 2])
        thread = self.thread()
        # 時序做緊：晚到那張的收集不等安靜期，放回卻還在送（主頻道紀錄還沒寫）
        self.worker._GROUP_QUIET_SEC = 0
        self.publisher.delay = 0.3

        def late_member_arrives():
            if len(self.publisher.to(CHANNEL)) == 1 and 3 not in self.repo.rows:
                self.repo.add_ready(3, 503, grouped_id=77)
                asyncio.get_running_loop().create_task(self.worker._process_one(3))
        self.publisher.on_publish = late_member_arrives
        ok, _ = await self.worker.restore(1, "小明")
        self.assertTrue(ok)
        await asyncio.sleep(1.0)
        plans = self.publisher.to(CHANNEL)
        self.assertEqual([p["media"] for p in plans], [media_of(1, 2), media_of(3)], "放回途中晚到的圖送主頻道")
        self.assertEqual(len(self.publisher.to(thread.id)), 1, "不能送進隔離區、讓這本卡在選單裡")
        self.assertEqual(await self.worker.quarantine_items(CHANNEL), [])

    async def test_marking_failure_still_reports_restored(self):
        await self.quarantine_single(9)
        with mock.patch.object(self.worker, "find_quarantine_messages", side_effect=RuntimeError("Discord 掛了")):
            ok, message = await self.worker.restore(9, "小明")
        self.assertTrue(ok, "主頻道已經送出，不能讓操作者以為沒放回")
        self.assertEqual(len(self.publisher.to(CHANNEL)), 1)

    async def test_sent_but_not_recorded_is_not_reported_as_failure(self):
        await self.quarantine_single(9)
        thread = self.thread()
        original = self.repo.mark_message_published

        async def broken(pk, channel_id, **kwargs):
            if channel_id == CHANNEL:
                raise RuntimeError("資料庫斷線")
            await original(pk, channel_id, **kwargs)
        self.repo.mark_message_published = broken
        ok, message = await self.worker.restore(9, "小明")
        self.assertTrue(ok, "主頻道已經送出，回報失敗的話操作者會再按一次、貼兩則")
        self.assertIn("不要再按", message)
        self.assertIn("已由 小明 放回主頻道", thread.messages[0].content)

    async def test_archived_thread_is_reopened_to_mark(self):
        await self.quarantine_single(9)
        thread = self.thread()
        thread.archived = True
        await self.worker.restore(9, "小明")
        self.assertIn("已由 小明 放回主頻道", thread.messages[0].content)

    async def test_panel_is_told_about_changes(self):
        await self.quarantine_single(9)
        await asyncio.sleep(0)
        thread = self.thread()
        self.assertEqual(self.changes, [(CHANNEL, thread.id)], "多一則隔離訊息")
        await self.worker.restore(9, "小明")
        await asyncio.sleep(0)
        self.assertEqual(self.changes[-1], (CHANNEL, thread.id), "放回一則")
        self.assertEqual(len(self.changes), 2)


class LabelTests(unittest.TestCase):
    def test_item_labels(self):
        text = tqc.item_option(QuarantineItem(9, at(6, 12, 3), "今日首水"))
        self.assertEqual((text.label, text.value, text.description), ("12:03 今日首水", "9", None))
        album = tqc.item_option(QuarantineItem(1, at(6, 9), "", image_count=3))
        self.assertEqual(album.label, "09:00 圖片 ×3")
        both = tqc.item_option(QuarantineItem(2, at(6, 9), "說明\n第二行", image_count=1, video_count=2))
        self.assertEqual((both.label, both.description), ("09:00 說明 第二行", "附圖片、影片 ×2"))
        long = tqc.item_option(QuarantineItem(3, at(6, 9), "字" * 300))
        self.assertLessEqual(len(long.label), 100)

    def test_dates_newest_first_with_counts_max_25(self):
        items = [QuarantineItem(1, at(5, 9), "a"), QuarantineItem(2, at(6, 9), "b"), QuarantineItem(3, at(6, 23), "c")]
        options = tqc.date_options(items)
        self.assertEqual([(o.label, o.value) for o in options], [("10/06（2 則）", "20261006"), ("10/05（1 則）", "20261005")])
        many = [QuarantineItem(n, datetime(2026, 1, 1, tzinfo=TZ8) + timedelta(days=n), "x") for n in range(40)]
        self.assertEqual(len(tqc.date_options(many)), 25)

    def test_custom_ids_round_trip(self):
        pick = tqc.QuarantinePickSelect(CHANNEL, "20261006")
        restore = tqc.QuarantineRestoreButton(9)
        self.assertRegex(pick.item.custom_id, tqc.PICK_TEMPLATE)
        m = tqc.QuarantinePickSelect.__discord_ui_compiled_template__.fullmatch(pick.item.custom_id)
        self.assertEqual((int(m["parent"]), m["day"]), (CHANNEL, "20261006"))
        m = tqc.QuarantineRestoreButton.__discord_ui_compiled_template__.fullmatch(restore.item.custom_id)
        self.assertEqual(int(m["pk"]), 9)
        self.assertEqual(tqc.QuarantinePanelView(None).children[0].custom_id, tqc.DATE_SELECT_ID)


class PanelFlowTests(QuarantineTestBase):
    def setUp(self):
        super().setUp()
        self.cog = tqc.TelegramQuarantineCommands(self.bot)
        self.cog.worker = self.worker
        panel_tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, panel_tmp, ignore_errors=True)
        panel_runtime = str(Path(panel_tmp) / "panel_runtime.json")
        patcher = mock.patch.object(tqc, "PANEL_RUNTIME_PATH", panel_runtime)
        patcher.start()
        self.addCleanup(patcher.stop)

    def interaction(self, *, can_manage=True, user_id=42):
        return SimpleNamespace(
            guild=SimpleNamespace(id=1), channel=self.thread(), data={},
            user=SimpleNamespace(id=user_id, display_name="小明"),
            permissions=SimpleNamespace(manage_messages=can_manage),
            response=SimpleNamespace(edit_message=mock.AsyncMock(), defer=mock.AsyncMock(),
                                     send_message=mock.AsyncMock(), is_done=lambda: False),
            followup=SimpleNamespace(send=mock.AsyncMock()),
            edit_original_response=mock.AsyncMock(),
        )

    async def test_whole_flow(self):
        await self.quarantine_single(9, date=at(6, 12, 3))
        day = tqc.day_key((await self.worker.quarantine_items(CHANNEL))[0])

        pick = self.interaction()
        await self.cog.handle_date(pick, day)
        reset = pick.response.edit_message.await_args.kwargs["view"]
        self.assertEqual(reset.children[0].values if hasattr(reset.children[0], "values") else [], [])
        sent = pick.followup.send.await_args
        self.assertTrue(sent.kwargs["ephemeral"])
        [select] = sent.kwargs["view"].children
        self.assertEqual([o.value for o in select.item.options], ["9"])

        confirm = self.interaction()
        await self.cog.handle_pick(confirm, 9)
        kwargs = confirm.edit_original_response.await_args.kwargs
        self.assertIn(self.thread().messages[0].jump_url, kwargs["content"], "確認時附隔離那則的連結")
        self.assertEqual(self.publisher.to(CHANNEL), [], "選了還沒確認，不能送")
        self.assertEqual(kwargs["view"].children[0].item.custom_id, "tgq:restore:9")

        press = self.interaction()
        await self.cog.handle_restore(press, 9)
        self.assertEqual(press.response.edit_message.await_args.kwargs, {"content": "放回中……", "view": None})
        self.assertIn("已放回主頻道", press.edit_original_response.await_args.kwargs["content"])
        self.assertEqual(len(self.publisher.to(CHANNEL)), 1)

    async def test_restore_error_is_reported_not_stuck(self):
        await self.quarantine_single(9)
        press = self.interaction()
        with mock.patch.object(self.worker, "restore", side_effect=RuntimeError("轉發端出錯")):
            await self.cog.handle_restore(press, 9)
        self.assertIn("出錯", press.edit_original_response.await_args.kwargs["content"], "不能一直停在「放回中……」")

    async def test_without_permission_nothing_happens(self):
        await self.quarantine_single(9)
        with mock.patch.dict(os.environ, {"OWNER_ID": "1"}):
            denied = self.interaction(can_manage=False)
            await self.cog.handle_restore(denied, 9)
            denied.response.edit_message.assert_not_awaited()
            await self.cog.handle_date(denied, "20261006")
        self.assertEqual(self.publisher.to(CHANNEL), [])
        denied.followup.send.assert_not_awaited()
        replies = [c.kwargs.get("content", "") for c in denied.response.send_message.await_args_list]
        self.assertTrue(replies and all("管理訊息" in r for r in replies), replies)

    async def test_panel_is_reset_even_when_refused(self):
        """沒權限、轉發還沒啟動時也要把面板重畫成沒選取，不然之後再選同一天不會有反應。"""
        await self.quarantine_single(9)
        with mock.patch.dict(os.environ, {"OWNER_ID": "1"}):
            denied = self.interaction(can_manage=False)
            await self.cog.handle_date(denied, "20261006")
        denied.response.edit_message.assert_awaited_once()
        self.cog.worker = None
        stopped = self.interaction()
        await self.cog.handle_date(stopped, "20261006")
        stopped.response.edit_message.assert_awaited_once()

    async def test_archived_thread_is_reopened_before_redrawing(self):
        await self.quarantine_single(9, date=at(6, 12))
        thread = self.thread()
        thread.archived = True
        await self.cog.handle_date(self.interaction(), "20261006")
        self.assertIn({"archived": False}, thread.edits, "封存中的 thread 改不了面板，要先解封")

    async def test_lost_runtime_file_still_lists_items(self):
        await self.quarantine_single(9, date=at(6, 12))
        Path(self.runtime).unlink()                         # 記錄 thread 的檔案不見了
        self.worker, _, self.routes, self.publisher = make_worker(
            content_filter=self.filter, quarantine=True, bot=self.bot, repo=self.repo, runtime_path=self.runtime)
        self.worker._running = True
        self.cog.worker = self.worker
        pick = self.interaction()
        await self.cog.handle_date(pick, "20261006")
        [select] = pick.followup.send.await_args.kwargs["view"].children
        self.assertEqual([o.value for o in select.item.options], ["9"], "在 thread 裡操作時要把它補記回去")

    async def test_owner_can_operate_without_the_permission(self):
        await self.quarantine_single(9)
        with mock.patch.dict(os.environ, {"OWNER_ID": "42"}):
            await self.cog.handle_restore(self.interaction(can_manage=False, user_id=42), 9)
        self.assertEqual(len(self.publisher.to(CHANNEL)), 1)

    async def test_panel_is_bumped_with_current_dates(self):
        await self.quarantine_single(9, date=at(6, 12))
        thread = self.thread()
        await self.cog.on_quarantine_change(CHANNEL, thread)
        await asyncio.sleep(0.05)
        panels = [m for m in thread.messages if m.view is not None]
        self.assertEqual(len(panels), 1)
        self.assertEqual([o.value for o in panels[0].view.children[0].options], ["20261006"])

        await self.quarantine_single(10, "今天还水吗", date=at(7, 8))
        await self.cog.on_quarantine_change(CHANNEL, thread)
        await asyncio.sleep(0.05)
        panels = [m for m in thread.messages if m.view is not None]
        self.assertEqual(len(panels), 1, "刪舊發新，只留一個面板")
        self.assertIs(thread.messages[-1], panels[0], "面板在最底下")
        self.assertEqual([o.value for o in panels[0].view.children[0].options], ["20261007", "20261006"])

    async def test_archived_thread_panel_still_moves_to_bottom(self):
        await self.quarantine_single(9, date=at(6, 12))
        thread = self.thread()
        await self.cog.on_quarantine_change(CHANNEL, thread)
        await asyncio.sleep(0.05)
        thread.archived = True          # 一週沒人講話自動封存；有人放回時要先解封，舊面板才刪得掉
        await self.cog.on_quarantine_change(CHANNEL, thread)
        await asyncio.sleep(0.05)
        self.assertEqual(len([m for m in thread.messages if m.view is not None]), 1)

    async def test_empty_panel_is_disabled(self):
        view = tqc.QuarantinePanelView(self.cog, [])
        self.assertTrue(view.children[0].disabled)


if __name__ == "__main__":
    unittest.main()
