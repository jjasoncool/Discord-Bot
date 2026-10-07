"""把已經貼在主頻道的 Telegram 轉發移進隔離區（轉發端 relay_posts／move_to_quarantine）。

守的底線（使用者 10-07：「判垃圾搬到 thread、原本頻道的貼文刪除」，搬過去的要能用面板放回）：
- 搬＝在隔離 thread 照正常流程重貼一份（最上面「判定：標籤｜理由」）＋刪主頻道原貼文；一則的所有部分都刪
  （相簿分批的圖、補圖），別的貼文、群友的訊息不動
- 發送紀錄只改頻道（主頻道 → thread），送出時間不動；相簿每張都改
- 搬過去的：面板列得出來、放回後跟新判的一樣；轉發重啟後不會再貼回主頻道
- 原貼文一則都沒刪掉（刪不掉、資料庫一開始就失敗）：紀錄不改、thread 那份收回，跟沒搬一樣
- 刪了一部分才失敗：thread 那份留著（不能讓內容兩邊都沒有），紀錄不改；本文那則最後刪，重跑認得出來、補得完
- 全部刪完才失敗（寫入資料庫時）：再試一次改紀錄；還是失敗就在 log 留要手動執行的 SQL（重跑已找不到原貼文）
- 不搬、不貼：主頻道找不到原貼文、認不出本文那則（07-25 以前的舊格式沒有 db#）、已經在隔離區的、
  放回過的（管理員看過）、第一次送出未滿 12 小時的相簿（晚到的圖還可能被線上 bot 補進主頻道）
- 預覽（apply=False）做同樣的檢查，什麼都不動
- 搬之前的判斷：相簿整本一起判、不看開關（開關是給新訊息的）；圖還沒到齊的不判、放行

執行：
    cd src && python -m unittest test.test_telegram_quarantine_move -v
"""
import importlib.util
import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

import discord

from services.relay.telegram_filter import Verdict
from services.relay.telegram_relay_service import relay_post_pks
from test.telegram_relay_fakes import CHANNEL, FakeBot, FakeFilter, FakeMessage, make_worker, media_of

SPAM = Verdict(True, label="灌水", reason="每日打卡")


class MoveTestBase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.bot = FakeBot()
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        self.runtime = str(Path(tmp) / "quarantine_runtime.json")
        # 不接過濾：先照舊貼進主頻道，再搬
        self.worker, self.repo, self.routes, self.publisher = make_worker(
            quarantine=True, bot=self.bot, runtime_path=self.runtime,
        )
        self.worker._running = True
        self.publisher.split_media = True

    def main_messages(self):
        return list(self.bot.main.messages)

    def thread(self):
        return self.bot.main.all_threads[-1]

    async def post_single(self, pk, text="今日首水"):
        self.repo.add_row(pk, 200 + pk, grouped_id=None, text=text, has_media=False)
        await self.worker._process_one(pk)

    async def post_album(self, pks, gid=77, text="說明"):
        for n, pk in enumerate(pks):
            self.repo.add_ready(pk, 500 + pk, grouped_id=gid, text=text if n == 0 else "")
        await self.worker._process_one(pks[0])

    def age(self, *pks, hours=13):
        """把這幾則的主頻道發送時間往前推：相簿過了補圖時效才搬得動。"""
        for pk in pks:
            self.repo.delivered[(pk, CHANNEL)] = datetime.now(timezone.utc) - timedelta(hours=hours)

    async def move(self, pk, verdict=SPAM, **kwargs):
        return await self.worker.move_to_quarantine(pk, verdict, await self.worker.relay_posts(self.bot.main), **kwargs)


class MoveTests(MoveTestBase):
    async def test_move_single(self):
        await self.post_single(9)
        [original] = self.main_messages()
        sent_at = self.repo.delivered[(9, CHANNEL)]

        ok, note = await self.move(9)

        self.assertTrue(ok, note)
        self.assertTrue(original.deleted)
        self.assertEqual(self.main_messages(), [])
        thread = self.thread()
        [copy] = thread.messages
        self.assertTrue(copy.content.startswith("判定：灌水｜每日打卡"))
        self.assertEqual(relay_post_pks(copy), {9}, "thread 那份帶 db#，放回時才找得到")
        self.assertEqual(self.repo.channels_of(9), {thread.id})
        self.assertEqual(self.repo.delivered[(9, thread.id)], sent_at, "送出時間不動")
        self.assertEqual([i.pk for i in await self.worker.quarantine_items(CHANNEL)], [9])

    async def test_album_every_part_moves_and_nothing_else(self):
        await self.post_album([1, 2, 3])
        self.repo.add_ready(4, 504, grouped_id=77)   # 晚到的圖以補圖貼進主頻道
        await self.worker._process_one(4)
        await self.post_single(9, "別則情報")
        human = FakeMessage(self.bot.main, self.bot.next_id(), "db#1", attachments=["tg_1_9.jpg"], author_id=42)
        self.bot.main.messages.append(human)
        self.age(1, 2, 3, 4)
        album_posts = [m for m in self.main_messages() if m is not human and relay_post_pks(m) & {1, 2, 3, 4}]
        self.assertEqual(len(album_posts), 3, "embed＋第 2 張起另一則＋補圖")

        ok, note = await self.move(1)

        self.assertTrue(ok, note)
        self.assertTrue(all(m.deleted for m in album_posts))
        self.assertEqual([relay_post_pks(m) for m in self.main_messages() if m is not human], [{9}])
        self.assertIn(human, self.main_messages(), "群友的訊息不動")
        thread = self.thread()
        self.assertEqual({pk: self.repo.channels_of(pk) for pk in (1, 2, 3, 4)},
                         {pk: {thread.id} for pk in (1, 2, 3, 4)}, "相簿每張都改")
        self.assertEqual(self.repo.channels_of(9), {CHANNEL})
        [plan] = self.publisher.to(thread.id)
        self.assertEqual(plan["media"], media_of(1, 2, 3, 4), "整本連同補圖合成一則")

    async def test_restore_after_move(self):
        await self.post_single(9)
        await self.move(9)
        thread = self.thread()

        ok, message = await self.worker.restore(9, "小明")

        self.assertTrue(ok, message)
        self.assertEqual(len(self.publisher.to(CHANNEL)), 2, "原本那則＋放回的")
        self.assertIn("已由 小明 放回主頻道", thread.messages[0].content)
        self.assertEqual(self.repo.channels_of(9), {CHANNEL, thread.id})
        self.assertEqual(await self.worker.quarantine_items(CHANNEL), [])

    async def test_not_reposted_after_restart(self):
        await self.post_single(9)
        await self.move(9)
        worker, _, _, publisher = make_worker(quarantine=True, bot=self.bot, repo=self.repo, runtime_path=self.runtime)
        await worker._process_one(9)
        self.assertEqual(publisher.sent, [], "紀錄在 thread，就是送過了")

    async def test_original_already_gone_still_moves(self):
        await self.post_single(9)
        posts = await self.worker.relay_posts(self.bot.main)
        await self.main_messages()[0].delete()   # 掃完之後有人先刪了
        ok, note = await self.worker.move_to_quarantine(9, SPAM, posts)
        self.assertTrue(ok, note)
        self.assertEqual(self.repo.channels_of(9), {self.thread().id})


class MoveFailureTests(MoveTestBase):
    async def assert_not_moved(self, pk, original):
        self.assertFalse(original.deleted)
        self.assertEqual(self.repo.channels_of(pk), {CHANNEL})
        self.assertEqual([m for m in self.thread().messages if relay_post_pks(m) & {pk}], [], "thread 那份要收回")
        self.assertEqual(await self.worker.quarantine_items(CHANNEL), [])

    async def test_original_cannot_be_deleted(self):
        await self.post_single(9)
        [original] = self.main_messages()
        original.delete_error = discord.Forbidden(SimpleNamespace(status=403, reason="Forbidden"), "沒有權限")
        ok, _ = await self.move(9)
        self.assertFalse(ok)
        await self.assert_not_moved(9, original)

    async def test_database_down_before_deleting(self):
        await self.post_single(9)
        [original] = self.main_messages()
        self.repo.fail_move = "start"
        ok, _ = await self.move(9)
        self.assertFalse(ok)
        await self.assert_not_moved(9, original)

    async def test_all_deleted_then_write_fails_once_is_retried(self):
        await self.post_single(9)
        self.repo.fail_move, self.repo.fail_move_once = "commit", True
        ok, note = await self.move(9)
        self.assertTrue(ok, note)
        self.assertEqual(self.repo.channels_of(9), {self.thread().id}, "原貼文已全刪，改紀錄已經安全，再試一次")
        self.assertEqual([i.pk for i in await self.worker.quarantine_items(CHANNEL)], [9])

    async def test_all_deleted_but_record_never_written_logs_sql(self):
        await self.post_single(9)
        self.repo.fail_move = "commit"
        with self.assertLogs("services.relay.telegram_relay_service", "ERROR") as logs:
            ok, note = await self.move(9)
        self.assertFalse(ok)
        self.assertIn("手動", note)
        self.assertTrue(any("UPDATE telegram_relay_delivery_state SET discord_channel_id" in line
                            and "{9}" in line for line in logs.output))
        self.assertEqual(self.main_messages(), [])
        self.assertEqual(len(self.thread().messages), 1, "主頻道已經沒了，thread 那份是唯一一份")
        self.assertEqual(self.repo.channels_of(9), {CHANNEL}, "紀錄沒改")

    async def test_partly_deleted_keeps_thread_copy_and_rerun_completes(self):
        await self.post_album([1, 2])
        self.age(1, 2)
        body, more_images = self.main_messages()
        body.delete_error = discord.HTTPException(SimpleNamespace(status=500, reason="Server Error"), "掛了")
        ok, note = await self.move(1)
        self.assertFalse(ok)
        self.assertIn("1/2", note)
        self.assertTrue(more_images.deleted, "後面的先刪")
        self.assertFalse(body.deleted, "本文那則最後刪，還在")
        self.assertEqual(len(self.publisher.to(self.thread().id)), 1, "thread 那份留著")
        self.assertEqual(self.repo.channels_of(1), {CHANNEL})

        body.delete_error = None
        ok, note = await self.move(1)
        self.assertTrue(ok, note)
        self.assertEqual(self.main_messages(), [])
        self.assertEqual(self.repo.channels_of(1), {self.thread().id})

    async def test_new_album_is_not_moved(self):
        await self.post_album([1, 2])
        ok, note = await self.move(1)
        self.assertFalse(ok)
        self.assertIn("12 小時", note)
        self.assertEqual(self.bot.main.all_threads, [])
        self.assertEqual(len(self.main_messages()), 2)

    async def test_old_format_without_db_tag_is_not_moved(self):
        # 07-25 以前：本文那則 footer 只有「msg #…」，只認得出後面那則影片
        self.repo.add_row(9, 209, grouped_id=None, text="水", has_media=True)
        self.repo.mark(9)
        body = await self.bot.main.send(footer="msg #209")
        video = await self.bot.main.send(attachments=["tg_9_1.mp4"])
        ok, note = await self.move(9)
        self.assertFalse(ok)
        self.assertIn("認不出", note)
        self.assertEqual(self.main_messages(), [body, video], "一則都不刪")
        self.assertEqual(self.bot.main.all_threads, [])
        self.assertEqual(self.repo.channels_of(9), {CHANNEL})

    async def test_preview_changes_nothing(self):
        await self.post_album([1, 2])
        self.age(1, 2)
        ok, note = await self.move(1, apply=False)
        self.assertTrue(ok, note)
        self.assertIn("會刪主頻道 2 則", note)
        self.assertEqual(len(self.main_messages()), 2)
        self.assertEqual(self.bot.main.all_threads, [])
        self.assertEqual(self.repo.channels_of(1), {CHANNEL})

    async def test_no_original_found(self):
        await self.post_single(9)
        ok, note = await self.worker.move_to_quarantine(9, SPAM, {})
        self.assertFalse(ok)
        self.assertIn("找不到原貼文", note)
        self.assertEqual(self.bot.main.all_threads, [], "沒找到就什麼都不做")
        self.assertEqual(self.repo.channels_of(9), {CHANNEL})

    async def test_already_in_quarantine(self):
        await self.post_single(9)
        await self.move(9)
        ok, _ = await self.move(9)
        self.assertFalse(ok)
        self.assertEqual(len(self.thread().messages), 1)

    async def test_restored_one_is_not_moved_again(self):
        # 管理員放回＝看過、覺得不是垃圾；整批重跑時又被判成垃圾也不能再搬走
        await self.post_single(9)
        await self.move(9)
        await self.worker.restore(9, "小明")
        ok, note = await self.move(9)
        self.assertFalse(ok)
        self.assertIn("已經在隔離區", note)
        self.assertEqual(len(self.publisher.to(self.thread().id)), 1, "連貼都不貼")
        self.assertEqual(len(self.main_messages()), 1)


class JudgeExistingTests(MoveTestBase):
    async def test_album_is_judged_as_one_regardless_of_switch(self):
        await self.post_album([1, 2, 3])
        self.worker._filter = FakeFilter("off")
        self.worker._filter.quarantine(1, "無關圖片", "奶龍")

        verdict = await self.worker.judge_existing(1)

        self.assertEqual((verdict.quarantine, verdict.label), (True, "無關圖片"))
        [call] = self.worker._filter.calls
        self.assertEqual((call["text"], call["media"]), ("說明", ["1.jpg", "2.jpg", "3.jpg"]))

    async def test_incomplete_unit_is_not_judged(self):
        self.repo.add_ready(1, 501, grouped_id=77, text="說明")
        self.repo.add_row(2, 502, grouped_id=77)          # 第 2 張一直沒下載到
        self.repo.add_row(9, 209, grouped_id=None, text="水", has_media=True)
        self.worker._filter = FakeFilter("on")
        for pk in (1, 9):
            verdict = await self.worker.judge_existing(pk)
            self.assertEqual((verdict.quarantine, verdict.by_model), (False, False))
        self.assertEqual(self.worker._filter.calls, [], "只看到一部分不判")

    async def test_without_filter_or_message(self):
        await self.post_single(9)
        self.assertIsNone(await self.worker.judge_existing(9))
        self.worker._filter = FakeFilter("on")
        self.assertIsNone(await self.worker.judge_existing(404))


class ScriptListFileTests(unittest.TestCase):
    def test_list_file_with_and_without_verdicts(self):
        # 使用者看過的清單照清單搬、不重判（模型每次判的不一定一樣）；只寫 pk 的才用模型判
        cwd = os.getcwd()
        self.addCleanup(os.chdir, cwd)   # 腳本 import 時會切到 src
        spec = importlib.util.spec_from_file_location(
            "telegram_move_script", Path(SRC_DIR) / "scripts" / "telegram_move_to_quarantine.py")
        script = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(script)
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        path = Path(tmp) / "move.txt"
        path.write_text("14093 罵人 設定 拉黑規則  # 看過了\n14095\n\n# 註解\n", encoding="utf-8")

        targets = script._read_targets(SimpleNamespace(pks=[13342], file=str(path)))

        self.assertEqual(set(targets), {13342, 14093, 14095})
        self.assertIsNone(targets[13342])
        self.assertIsNone(targets[14095])
        self.assertEqual((targets[14093].quarantine, targets[14093].label, targets[14093].reason),
                         (True, "罵人", "設定 拉黑規則"))


class RelayPostPksTests(unittest.TestCase):
    def message(self, *, footer=None, files=()):
        return SimpleNamespace(
            embeds=[SimpleNamespace(footer=SimpleNamespace(text=footer))] if footer else [],
            attachments=[SimpleNamespace(filename=name) for name in files],
        )

    def test_footer_and_file_names(self):
        self.assertEqual(relay_post_pks(self.message(footer="msg #10822 · db#14095")), {14095})
        self.assertEqual(relay_post_pks(self.message(footer="msg #5 · db#7 · 2/3")), {7})
        self.assertEqual(relay_post_pks(self.message(files=["tg_14077_11.jpg", "tg_14077_12.mp4"])), {14077})
        self.assertEqual(relay_post_pks(self.message(files=["SPOILER_tg_14078_1.jpg"])), {14078}, "有雷的圖")

    def test_other_messages(self):
        self.assertEqual(relay_post_pks(self.message(files=["photo_tg_1_1.jpg", "tg_x_1.jpg"])), set())
        self.assertEqual(relay_post_pks(SimpleNamespace()), set())


if __name__ == "__main__":
    unittest.main()
