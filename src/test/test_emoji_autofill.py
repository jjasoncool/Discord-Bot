"""看到沒描述的表情或貼圖時讓模型看圖補字典（llm/preprocess/emoji_autofill.py）。

守的底線：
- **使用者寫過的描述一律不動**：只寫空白、只有類別字的行，或檔裡沒有的（別的伺服器的）；
  就地補時保留使用者選的類別，其他行一個字都不變
- 別的伺服器的表情集中寫在檔尾 AI 專區；別的伺服器的貼圖寫 `sticker_dictionary.txt`（用 ID 當鍵）
- 每個只看一次：寫進字典就不再是對象；看不出來、失敗、試跑看過的，隔一段時間才再看；同一個表情連發只看一次
- 試跑（dry_run）只寫 log、不寫檔；每天有上限；04:00 維護時段不跑；任何錯誤都不往外丟（不能打斷 on_message）
- 每天第一次改寫字典前備份；寫進去的描述馬上被讀到（不用重啟）
- 本伺服器的貼圖有增刪改時，描述快取跟著更新；別的伺服器的貼圖查得到 AI 補的描述

執行：
    cd src && python -m unittest test.test_emoji_autofill -v
"""

import asyncio
import inspect
import os
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from llm.preprocess import emoji_autofill as af  # noqa: E402
from llm.preprocess import emoji_dictionary as ed  # noqa: E402
from llm.preprocess import sticker_cache  # noqa: E402
from llm.preprocess import sticker_dictionary as sd  # noqa: E402
from llm.prompt import prompt_files  # noqa: E402
from sys_settings.llm_settings import EmojiAutofillSettings  # noqa: E402
from sys_settings.time_settings import APP_TZ  # noqa: E402

DICT = """# 註解
frog_angry = 生氣 | negative
let_me_see_see = think
pending =

# === 自動偵測 2026-08-15（待填寫） ===
Dorothy_cry = negative
"""

NOON = datetime(2026, 10, 2, 12, 0, tzinfo=APP_TZ)


def sticker(sid, name, fmt="png"):
    return SimpleNamespace(id=sid, name=name, format=SimpleNamespace(name=fmt),
                           url=f"https://media.discordapp.net/stickers/{sid}.{fmt}")


def msg(content="", stickers=(), bot=False):
    return SimpleNamespace(content=content, stickers=list(stickers), author=SimpleNamespace(bot=bot),
                           mentions=[], guild=None, reference=None)


class FilesTestBase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.emoji_path = self.dir / "emoji_dictionary.txt"
        self.emoji_path.write_text(DICT, encoding="utf-8")
        self.sticker_path = self.dir / "sticker_dictionary.txt"
        self.backup_dir = self.dir / "backup"
        for target, attr, value in [(ed, "EMOJI_DICT_PATH", str(self.emoji_path)),
                                    (sd, "STICKER_DICT_PATH", str(self.sticker_path))]:
            patcher = mock.patch.object(target, attr, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        prompt_files.forget(self.emoji_path)
        prompt_files.forget(self.sticker_path)

    def lines(self):
        return self.emoji_path.read_text(encoding="utf-8").split("\n")


class TargetTests(FilesTestBase):
    def test_what_needs_a_picture(self):
        m = msg("<:frog_angry:1> <:let_me_see_see:2> <:pending:3> <a:worryWDYM:4> <:worryWDYM:4>",
                [sticker(10, "本伺服器"), sticker(11, "已補過"), sticker(12, "動態", "lottie"), sticker(13, "NanaSussy")])
        sd_entries = {11: "已補過｜描述"}
        with mock.patch.object(sticker_cache, "is_known", side_effect=lambda sid: sid == 10), \
             mock.patch.object(sd, "entries", return_value=sd_entries):
            got = [(t.key, t.url) for t in af.targets(m)]
        self.assertEqual(got, [
            ("emoji:let_me_see_see", "https://cdn.discordapp.com/emojis/2.png"),   # 只有類別字
            ("emoji:pending", "https://cdn.discordapp.com/emojis/3.png"),          # 空白待填
            ("emoji:worryWDYM", "https://cdn.discordapp.com/emojis/4.gif"),        # 別的伺服器，連發兩次只算一個
            ("sticker:13", "https://media.discordapp.net/stickers/13.png"),        # 別的伺服器、還沒補
        ], "人寫過描述的表情、本伺服器的貼圖、已補過的、Lottie 都不是對象")


class ParseAnswerTests(unittest.TestCase):
    def parse(self, text):
        return af.parse_answer(text, max_chars=15)

    def test_good_answers(self):
        self.assertEqual(self.parse("哭哭難過 | negative"), ("哭哭難過", "negative"))
        self.assertEqual(self.parse("<think>嗯</think>\n`偷看 | think`"), ("偷看", "think"))
        self.assertEqual(self.parse("「嘿嘿偷笑」"), ("嘿嘿偷笑", None))
        # 先寫看到什麼、再寫字典那行：取最後一行
        self.assertEqual(self.parse("一隻青蛙雙手合十，不知道在拜託什麼。\n祈禱、拜託 | neutral"), ("祈禱、拜託", "neutral"))
        self.assertIsNone(self.parse("看不清楚。\n不知道"))

    def test_rather_write_nothing(self):
        for bad in ["不知道", "", "think", "描述 | 不是類別", "這是一個非常非常非常非常長的描述字串", "a = b | laugh"]:
            self.assertIsNone(self.parse(bad), bad)


class FillTests(FilesTestBase):
    def fill(self, name, desc, cat):
        return ed.fill(name, desc, cat, backup_dir=str(self.backup_dir))

    def test_category_only_line_keeps_the_users_category(self):
        before = self.lines()
        self.assertTrue(self.fill("let_me_see_see", "歪頭打量", "laugh"))
        after = self.lines()
        changed = [(a, b) for a, b in zip(before, after) if a != b]
        self.assertEqual(changed, [("let_me_see_see = think", "let_me_see_see = 歪頭打量 | think")],
                         "只改那一行；使用者選的類別保留")
        self.assertEqual(len(before), len(after))

    def test_blank_line_takes_the_ai_category(self):
        self.assertTrue(self.fill("pending", "帶帶我", "agree"))
        self.assertIn("pending = 帶帶我 | agree", self.lines())

    def test_never_overwrites_a_written_description(self):
        raw = self.emoji_path.read_bytes()
        self.assertFalse(self.fill("frog_angry", "別的說法", "laugh"))
        self.assertEqual(self.emoji_path.read_bytes(), raw)

    def test_other_servers_go_to_one_section_at_the_end(self):
        self.assertTrue(self.fill("worryWDYM", "擔心困惑", "think"))
        self.assertTrue(self.fill("FR16", "得意", None))
        lines = self.lines()
        self.assertEqual(lines.count(ed.AI_SECTION_HEADER), 1)
        start = lines.index(ed.AI_SECTION_HEADER)
        self.assertEqual(lines[start + 1:start + 3], ["worryWDYM = 擔心困惑 | think", "FR16 = 得意"])
        self.assertTrue(DICT.rstrip("\n") in "\n".join(lines), "原本的內容原樣保留")

    def test_written_description_is_read_back_immediately(self):
        self.fill("worryWDYM", "擔心困惑", "think")
        self.assertEqual(ed.entries()["worryWDYM"].description, "擔心困惑")
        self.assertFalse(ed.entries()["worryWDYM"].needs_description)

    def test_backs_up_once_a_day_before_writing(self):
        self.fill("pending", "帶帶我", "agree")
        self.fill("worryWDYM", "擔心困惑", "think")
        backups = list(self.backup_dir.iterdir())
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(encoding="utf-8"), DICT, "備份的是第一次改寫前的原檔")


class StickerDictionaryTests(FilesTestBase):
    def test_add_and_read(self):
        self.assertTrue(sd.add(13, "Nana Sussy", "懷疑", backup_dir=str(self.backup_dir)))
        self.assertFalse(sd.add(13, "Nana Sussy", "別的", backup_dir=str(self.backup_dir)), "已經有了就不動")
        self.assertEqual(sd.lookup(13), "Nana Sussy｜懷疑")
        self.assertIn("# 別的伺服器的貼圖描述", self.sticker_path.read_text(encoding="utf-8"))

    def test_sticker_text_uses_it(self):
        sd.add(13, "NanaSussy", "懷疑", backup_dir=str(self.backup_dir))
        self.assertEqual(sticker_cache.get_sticker_text(sticker(13, "NanaSussy")), "[貼圖：NanaSussy｜懷疑]")
        self.assertEqual(sticker_cache.get_sticker_text(sticker(99, "沒補過")), "[貼圖：沒補過]")


class StickerCacheUpdateTests(unittest.TestCase):
    def test_follows_server_changes(self):
        def gs(sid, name, desc):
            return SimpleNamespace(id=sid, name=name, description=desc)
        sticker_cache.update_guild([], [gs(501, "舊", "舊描述"), gs(502, "要刪", "")])
        sticker_cache.update_guild([gs(501, "舊", "舊描述"), gs(502, "要刪", "")],
                                   [gs(501, "舊", "改過的描述"), gs(503, "新增", "新描述")])
        self.addCleanup(sticker_cache.update_guild, [gs(501, "", ""), gs(503, "", "")], [])
        self.assertEqual(sticker_cache.get_sticker_text(sticker(501, "舊")), "[貼圖：舊｜改過的描述]")
        self.assertTrue(sticker_cache.is_known(503))
        self.assertFalse(sticker_cache.is_known(502))


class _Session:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class ObserveTests(FilesTestBase):
    def setUp(self):
        super().setUp()
        af._in_flight.clear()
        af._retry_after.clear()
        af._quota[:] = ["", 0]
        self.addCleanup(af._retry_after.clear)
        self.answer = "擔心困惑 | think"
        self.ask = mock.AsyncMock(side_effect=lambda *a, **k: self.answer)
        self.now = NOON
        self.settings = EmojiAutofillSettings(mode="on", backup_dir=str(self.backup_dir), daily_limit=3)
        for attr, value in [("_ask_model", self.ask), ("_SETTINGS", self.settings),
                            ("download_images", self.fake_download),
                            ("_session", lambda: _Session()), ("_now", lambda: self.now),
                            ("_context_lines", lambda m: ["ctx"])]:
            patcher = mock.patch.object(af, attr, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    @staticmethod
    async def fake_download(*args, **kwargs):
        await asyncio.sleep(0)   # 真的下載會讓出 event loop，別的訊息這時才進得來
        return ["img"]

    def run_observe(self, *messages):
        async def go():
            await asyncio.gather(*(af.observe(m) for m in messages))
        asyncio.run(go())

    def test_writes_and_then_never_looks_again(self):
        self.run_observe(msg("<:worryWDYM:4>"))
        self.assertEqual(ed.entries()["worryWDYM"].description, "擔心困惑")
        af._retry_after.clear()
        self.run_observe(msg("<:worryWDYM:4>"))
        self.assertEqual(self.ask.await_count, 1, "寫進字典後就不再是對象")

    def test_dry_run_only_logs_and_waits_before_looking_again(self):
        af._SETTINGS = self.settings.model_copy(update={"mode": "dry_run"})
        raw = self.emoji_path.read_bytes()
        with self.assertLogs("llm.preprocess.emoji_autofill", "INFO") as logs:
            self.run_observe(msg("<:worryWDYM:4>"))
        self.assertEqual(self.emoji_path.read_bytes(), raw, "試跑不寫檔")
        self.assertTrue(any("試跑" in line and "擔心困惑" in line for line in logs.output))
        self.run_observe(msg("<:worryWDYM:4>"))
        self.assertEqual(self.ask.await_count, 1, "試跑看過的也要隔一段時間才再看")

    def test_unrecognisable_waits_before_retry(self):
        self.answer = "不知道"
        self.run_observe(msg("<:worryWDYM:4>"))
        self.run_observe(msg("<:worryWDYM:4>"))
        self.assertEqual(self.ask.await_count, 1)
        self.assertNotIn("worryWDYM", ed.entries())

    def test_same_emoji_in_a_burst_is_looked_at_once(self):
        # 用「看不出來」：寫入成功的話第一則一寫完就不再是對象，擋不住的是看不出來、失敗的重複看
        self.answer = "不知道"
        self.run_observe(msg("<:worryWDYM:4>"), msg("<:worryWDYM:4>"), msg("<:worryWDYM:4>"))
        self.assertEqual(self.ask.await_count, 1)
        # 前一個表情還在看的時候，同一個新表情連來兩則：排隊的只能算一次
        af._retry_after.clear()
        af._quota[:] = ["", 0]   # 別讓每日上限替去重擋掉第三次
        self.ask.reset_mock()
        self.run_observe(msg("<:FR16:5>"), msg("<:moon2:6>"), msg("<:moon2:6>"))
        self.assertEqual(self.ask.await_count, 2)

    def test_daily_limit(self):
        self.run_observe(msg("<:a1:1> <:a2:2> <:a3:3> <:a4:4>"))
        self.assertEqual(self.ask.await_count, 3)

    def test_quiet_during_maintenance(self):
        self.now = datetime(2026, 10, 2, 5, 0, tzinfo=APP_TZ)
        self.run_observe(msg("<:worryWDYM:4>"))
        self.ask.assert_not_awaited()
        self.now = NOON
        self.run_observe(msg("<:worryWDYM:4>"))
        self.assertEqual(self.ask.await_count, 1, "維護時段錯過的，下次被看到再補")

    def test_off_and_bots_do_nothing(self):
        self.run_observe(msg("<:worryWDYM:4>", bot=True))
        af._SETTINGS = self.settings.model_copy(update={"mode": "off"})
        self.run_observe(msg("<:worryWDYM:4>"))
        self.ask.assert_not_awaited()

    def test_errors_never_escape(self):
        self.ask.side_effect = RuntimeError("模型掛了")
        self.run_observe(msg("<:worryWDYM:4>"))   # 不拋例外就算過
        self.assertNotIn("worryWDYM", ed.entries())

    def test_human_written_description_wins(self):
        """使用者手動補了描述（不用重啟）→ 不看、不寫。"""
        self.emoji_path.write_text(DICT.replace("pending =", "pending = 使用者寫的"), encoding="utf-8")
        os.utime(self.emoji_path, (NOON.timestamp() + 99, NOON.timestamp() + 99))
        self.run_observe(msg("<:pending:3>"))
        self.ask.assert_not_awaited()
        self.assertEqual(ed.entries()["pending"].description, "使用者寫的")

    def test_sticker_goes_to_sticker_dictionary(self):
        self.answer = "懷疑 | think"
        with mock.patch.object(sticker_cache, "is_known", return_value=False):
            self.run_observe(msg("", [sticker(13, "NanaSussy")]))
        self.assertEqual(sd.lookup(13), "NanaSussy｜懷疑")


class WiredInTests(unittest.TestCase):
    def test_discord_bot_hooks(self):
        with open(os.path.join(SRC_DIR, "discord_bot.py"), encoding="utf-8") as f:
            src = f.read()
        self.assertIn("asyncio.create_task(observe_emoji(message))", src)
        self.assertIn("async def on_guild_stickers_update(guild, before, after):", src)
        self.assertIn("update_guild(before, after)", src)

    def test_model_sees_the_picture(self):
        src = inspect.getsource(af._ask_model)
        self.assertIn('"images": [image]', src)


if __name__ == "__main__":
    unittest.main()
