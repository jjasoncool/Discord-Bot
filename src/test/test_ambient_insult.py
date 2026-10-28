"""被點名罵時的應對（llm.ambient.ambient_insult，與 ambient_reply 的入口、單輪插話）。

守的底線（是不是在罵它由模型判斷，不用關鍵字）：
- 插話 prompt 告訴模型的標記，就是程式認得的那個（「被惡意辱罵就整則輸出 [INSULT]」）
- 被點名、模型輸出 [INSULT]、開關 on：不回文字、不寫互動紀錄，在那則訊息按嘲諷表情（本伺服器的設定表情，
  沒有就 🙄），記下是誰罵的；對方回覆的是它的哪則話，那則記成被罵
- [INSULT] 在任何情況都不會被當成文字送出去（含大小寫、各種括號）；開關 off、自發插話、接續時冒出來也不按表情、
  不記名單；標記夾在其他文字裡＝拿不定主意 → 不送，也不按表情、不記仇（保護機制門檻要高）
- 開關 off：記仇的效果全停（照常主動接話、點名不帶心情、讚照算）
- 被點名就用掉「接話」判定：對方用回覆罵完、下一句跟別人聊，不能被當成在接它的話
- 最近罵過它的人：最新一則是他的就不主動插話、模型選了他那則來接也不送；他點名照樣回
- 記仇中的人點名：system prompt 帶上【你的心情】（幾天前、幾次），不帶他罵的原話與名字（那是可信區）；
  別人點名不帶
- 群主罵它：表情照按，但不記仇——不進名單、不標被罵的那則（群主和它的關係不一樣）
- 罵它的人按的讚不算進「被讚的插話」；名單查不到時照常計入
- 被罵的插話在資料庫記成「沒人接」、之後不會被翻回「有人接」，也不當範例

全部 hermetic：不碰 DB、不碰模型、不連 Discord（規則檔讀的是 repo 裡那份）。

執行：
    cd src && python -m unittest test.test_ambient_insult -v
"""

import asyncio
import os
import re
import sys
import time
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

import discord  # noqa: E402

from llm.ambient import ambient_insult, ambient_reply  # noqa: E402
from llm.ambient.ambient_hooks import HookDecision  # noqa: E402
from llm.storage import ai_interactions_store  # noqa: E402
from sys_settings.switches import Switches  # noqa: E402

BOT_ID = 1385591938438135848
BOT_USER = SimpleNamespace(id=BOT_ID)
BOT_MSG = 1557095531455709285      # 它的那則話
INSULTER = 537251366008127489
OTHER = 430244604688990212
OWNER = 468158509297434635
GUILD_ID = 1
CHANNEL_ID = 4242


def _switch(test, mode):
    patcher = mock.patch.object(ambient_insult.switches, "current", lambda: Switches(ambient_insult_mode=mode))
    patcher.start()
    test.addCleanup(patcher.stop)


def _guild(*, emojis=True):
    emoji_list = [SimpleNamespace(name="sointeresting", available=True, id=77)] if emojis else []
    return SimpleNamespace(id=GUILD_ID, emojis=emoji_list, me=SimpleNamespace(id=BOT_ID))


class MarkerTests(unittest.TestCase):
    def test_marker_variants(self):
        for text in ("[INSULT]", "［INSULT］", "(insult)", "[ Insult ]", "【INSULT】", "INSULT", "[INSULT]。"):
            with self.subTest(text=text):
                self.assertTrue(ambient_insult.is_marker(text))
                self.assertTrue(ambient_insult.mentions_marker(text) or text == "INSULT")

    def test_marker_mixed_with_words_is_not_a_verdict(self):
        self.assertFalse(ambient_insult.is_marker("[INSULT]\n你自己查"))
        self.assertTrue(ambient_insult.mentions_marker("[INSULT]\n你自己查"))

    def test_talking_about_mockery_is_not_the_marker(self):
        for text in ("我覺得他在嘲諷你", "That was an insult lol", ""):
            self.assertFalse(ambient_insult.is_marker(text))
            self.assertFalse(ambient_insult.mentions_marker(text))

    def test_prompt_explains_the_mood_block_the_code_adds(self):
        with open(ambient_reply._SETTINGS.prompt_path, encoding="utf-8") as fh:
            prompt = fh.read()
        note = ambient_insult.mood_note(ambient_insult.Grudge(last_at=NOW, times=1), NOW)
        self.assertIn(note[:note.index("】") + 1], prompt[prompt.index("被 @ 或被回覆時"):])

    def test_prompt_tells_the_model_the_marker_the_code_reads(self):
        with open(ambient_reply._SETTINGS.prompt_path, encoding="utf-8") as fh:
            prompt = fh.read()
        directed_section = prompt[prompt.index("被 @ 或被回覆時"):]
        told = re.search(r"整則只輸出\s*(\S+?)[，,]", directed_section)
        self.assertIsNotNone(told)
        self.assertTrue(ambient_insult.is_marker(told.group(1)), told.group(1))


NOW = datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc)


class MoodNoteTests(unittest.TestCase):
    """記仇的心情：講幾天前、幾次；不講他罵的原話、不講名字。"""

    def _note(self, days_ago, times=1):
        return ambient_insult.mood_note(
            ambient_insult.Grudge(last_at=NOW - timedelta(days=days_ago), times=times), NOW)

    def test_how_long_ago(self):
        self.assertIn("今天", self._note(0))
        self.assertIn("昨天", self._note(1))
        self.assertIn("3 天前", self._note(3))

    def test_repeated_insults_are_counted(self):
        self.assertIn("一共 4 次", self._note(0, times=4))
        self.assertNotIn("一共", self._note(0, times=1))


def _entry_message(content, *, author_id=INSULTER, mid=9001, reply_to_bot=False):
    """入口用的假訊息；reply_to_bot＝用回覆功能回它的那則話。"""
    reference = None
    if reply_to_bot:
        resolved = mock.Mock(spec=discord.Message)
        resolved.id = BOT_MSG
        resolved.author = SimpleNamespace(id=BOT_ID)
        reference = SimpleNamespace(message_id=BOT_MSG, resolved=resolved)
    return SimpleNamespace(
        content=content, id=mid, reference=reference, mentions=[],
        author=SimpleNamespace(id=author_id, bot=False, display_name="NNN", name="NNN"),
        guild=_guild(), channel=SimpleNamespace(id=CHANNEL_ID), stickers=[], attachments=[],
    )


class EntryTests(unittest.TestCase):
    """入口（maybe_ambient_reply）：被點名就用掉接話判定；罵它的那則照樣交給模型判斷。"""

    def setUp(self):
        ambient_reply._PROC_STATE.clear()
        self.addCleanup(ambient_reply._PROC_STATE.clear)
        self.bot = SimpleNamespace(user=BOT_USER, ambient_tracker={})
        self.pass_mock = mock.AsyncMock()
        self.mark_got_reply = mock.Mock()
        llm = SimpleNamespace(resolve_ambient_model=lambda: "m")
        for attr, value in (
            ("_get_llm", lambda: llm),
            ("_resolve_target_channel_id", lambda: CHANNEL_ID),
            ("enqueue_for_memory", lambda m: None),
            ("_wait_for_quiet", mock.AsyncMock()),
            ("_run_one_ambient_pass", self.pass_mock),
            ("mark_got_reply", self.mark_got_reply),
        ):
            patcher = mock.patch.object(ambient_reply, attr, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def _send(self, *messages):
        async def _run():
            for m in messages:
                await ambient_reply.maybe_ambient_reply(self.bot, m)
            await asyncio.sleep(0.05)   # 讓背景的 to_thread（接話標記）跑完
        asyncio.run(_run())

    def _armed_after_interjecting_on(self, author_id):
        state = ambient_reply._get_proc_state(CHANNEL_ID)
        state.update(followup_armed=True, last_reply_mono=time.monotonic(),
                     last_reply_message_id=str(BOT_MSG), last_anchor_author_id=author_id)

    def test_insult_is_handed_to_the_model_as_a_directed_message(self):
        msg = _entry_message("閉嘴拉 腦殘AI", reply_to_bot=True)
        self._send(msg)
        self.assertIs(msg, self.pass_mock.await_args.args[1])
        self.assertTrue(self.pass_mock.await_args.args[3])

    def test_talking_to_others_after_insulting_it_is_not_taking_up_its_words(self):
        # 10-06 09:30 實例：它接了 NNN 的話 → NNN 用回覆罵它 → NNN 接著跟別人聊「416婚紗」
        self._armed_after_interjecting_on(INSULTER)
        self._send(_entry_message("媽的 腦殘AI 閉嘴拉", reply_to_bot=True, mid=1),
                   _entry_message("416婚紗", mid=2))
        self.mark_got_reply.assert_not_called()
        self.assertFalse(self.pass_mock.await_args.kwargs.get("followup"))

    def test_taking_up_its_words_still_counts(self):
        # 對照組：沒有被點名夾在中間時，同一個人緊接著講話仍算接它的話
        self._armed_after_interjecting_on(INSULTER)
        self._send(_entry_message("對啊 我也這樣覺得", mid=2))
        self.mark_got_reply.assert_called_once_with(str(BOT_MSG))
        self.assertTrue(self.pass_mock.await_args.kwargs.get("followup"))


class PassTests(unittest.TestCase):
    """單輪插話：模型的 [INSULT] 標記、最近罵過它的人。"""

    def setUp(self):
        self.record_insult = mock.Mock()
        self.mark_insulted = mock.Mock()
        for attr, value in (("record_insult", self.record_insult), ("mark_insulted", self.mark_insulted)):
            patcher = mock.patch.object(ambient_insult, attr, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        _switch(self, "on")

    @staticmethod
    def _message(content, *, author_id, guild=None):
        return SimpleNamespace(
            content=content, id=7001, reference=None, stickers=[], attachments=[],
            author=SimpleNamespace(id=author_id, bot=False, display_name="x", name="x"),
            guild=guild or _guild(),
            channel=SimpleNamespace(id=CHANNEL_ID, send=mock.AsyncMock(return_value=SimpleNamespace(id=1))),
            created_at=datetime(2026, 10, 7, tzinfo=timezone.utc),
            reply=mock.AsyncMock(return_value=SimpleNamespace(id=2)),
            add_reaction=mock.AsyncMock(),
        )

    def _run(self, message, *, directed, followup=False, cold=(), reply="#1\n好喔", earlier=None, replied=None):
        """跑一次 `_run_one_ambient_pass`，模型回 reply。

        earlier＝脈絡裡第 1 則（自發時模型可能選它來接）；replied＝這則用回覆功能回的那則訊息。
        """
        self.llm = SimpleNamespace(generate_reply=mock.AsyncMock(
            return_value=SimpleNamespace(reply=reply, error_kind=None, prompt_record_log="")))
        self.record_interaction = mock.AsyncMock()

        async def _fetch(msg, thread_map=None):
            if earlier is not None and thread_map is not None:
                thread_map[1] = earlier
            return (["#1 [12:00] 某人: 前一句"], [message.author.id])

        stubs = dict(
            _get_tracker=lambda bot, cid: {"last_ts": 0.0, "hour_start": time.monotonic(), "hour_count": 0},
            stream_busy=lambda: False,
            foreground_recently_active=lambda *_a: False,
            _fetch_recent=mock.AsyncMock(side_effect=_fetch),
            evaluate_hook=mock.AsyncMock(return_value=HookDecision(
                passed=True, score=1.0, prob=0.9, features={}, veto=None, explore=False)),
            _load_ambient_prompt=lambda: "sys",
            _resolve_replied_to=mock.AsyncMock(return_value=replied),
            _media_context=mock.AsyncMock(return_value=([], [])),
            _build_persona_context=mock.AsyncMock(return_value=None),
            recall_lines=mock.AsyncMock(return_value=None),
            recall_signature_tags=mock.AsyncMock(return_value=None),
            _build_chat_callback_context=mock.AsyncMock(return_value=None),
            _build_style_refs=mock.AsyncMock(return_value=None),
            _write_ambient_debug=lambda **_k: None,
            _record_ambient_interaction=self.record_interaction,
            _get_llm=lambda: self.llm,
            name_with_anchor=lambda m: "name#0000",
            format_chat_line=lambda *a, **k: "#2 [12:01] 某人: 最新",
            _message_text=lambda m: m.content,
            semantic_message_text=lambda m: m.content,
        )
        bot = SimpleNamespace(user=BOT_USER, ambient_tracker={})
        # 資料庫的 author_id 是字串；只換掉查詢，記仇名單的開關與轉型走真的 grudges()
        rows = {str(uid): (NOW, 2) for uid in cold}
        with mock.patch.multiple(ambient_reply, **stubs), \
                mock.patch.object(ambient_insult, "recent_insults", lambda guild, days: rows):
            asyncio.run(ambient_reply._run_one_ambient_pass(
                bot, message, "m", directed, [message], followup=followup))

    @staticmethod
    def _its_message():
        return SimpleNamespace(id=BOT_MSG, author=SimpleNamespace(id=BOT_ID, bot=True),
                               content="前一句", attachments=[])

    # ── 模型判定被惡意辱罵 ──
    def test_insult_gets_an_emoji_not_a_reply(self):
        msg = self._message("閉嘴拉 腦殘AI", author_id=INSULTER)
        self._run(msg, directed=True, reply="[INSULT]", replied=self._its_message())
        msg.reply.assert_not_awaited()
        msg.channel.send.assert_not_awaited()
        self.record_interaction.assert_not_awaited()            # 不灌回話紀錄
        msg.add_reaction.assert_awaited_once()
        self.assertEqual("sointeresting", msg.add_reaction.await_args.args[0].name)
        kwargs = self.record_insult.call_args.kwargs
        self.assertEqual((str(INSULTER), str(BOT_MSG)), (kwargs["author_id"], kwargs["replied_to_message_id"]))
        self.mark_insulted.assert_called_once_with(str(BOT_MSG))

    def test_rolling_eyes_when_the_server_emoji_is_missing(self):
        msg = self._message("吵死了", author_id=INSULTER, guild=_guild(emojis=False))
        self._run(msg, directed=True, reply="［INSULT］")
        msg.add_reaction.assert_awaited_once_with("🙄")

    def test_mention_without_reply_records_who_but_marks_no_message(self):
        msg = self._message("<@1385591938438135848> 滾啦", author_id=INSULTER)
        self._run(msg, directed=True, reply="[INSULT]", replied=None)
        self.record_insult.assert_called_once()
        self.mark_insulted.assert_not_called()

    def test_mentioning_it_while_replying_to_someone_else_marks_no_message(self):
        someone = SimpleNamespace(id=31337, author=SimpleNamespace(id=OTHER, bot=False),
                                  content="我要去北海道", attachments=[])
        msg = self._message("<@1385591938438135848> 你也閉嘴", author_id=INSULTER)
        self._run(msg, directed=True, reply="[INSULT]", replied=someone)
        self.mark_insulted.assert_not_called()
        self.assertIsNone(self.record_insult.call_args.kwargs["replied_to_message_id"])

    def test_marker_mixed_with_words_sends_nothing_and_holds_no_grudge(self):
        msg = self._message("你很煩欸", author_id=OTHER)
        self._run(msg, directed=True, reply="[INSULT]\n你自己查", replied=self._its_message())
        msg.reply.assert_not_awaited()
        msg.add_reaction.assert_not_awaited()
        self.record_insult.assert_not_called()

    def test_lowercase_marker_is_still_the_marker(self):
        msg = self._message("吵死了", author_id=INSULTER)
        self._run(msg, directed=True, reply="[insult]")
        msg.reply.assert_not_awaited()
        msg.add_reaction.assert_awaited_once()

    def test_the_marker_is_never_sent_as_text(self):
        # 開關 off 的點名、自發插話、接續：都不送文字，也不按表情、不記名單
        for mode, directed, followup in (("off", True, False), ("on", False, False), ("on", True, True)):
            with self.subTest(mode=mode, directed=directed, followup=followup):
                _switch(self, mode)
                self.record_insult.reset_mock()
                msg = self._message("今天抽卡又歪了啦", author_id=OTHER)
                self._run(msg, directed=directed, followup=followup, reply="#2\n[INSULT]")
                msg.reply.assert_not_awaited()
                msg.channel.send.assert_not_awaited()
                msg.add_reaction.assert_not_awaited()
                self.record_insult.assert_not_called()

    def test_normal_answer_is_sent_as_before(self):
        msg = self._message("閉嘴拉 腦殘AI 你剛剛講的是哪個版本", author_id=INSULTER)
        self._run(msg, directed=True, reply="上個版本的，3.1。")
        msg.reply.assert_awaited_once()
        msg.add_reaction.assert_not_awaited()

    # ── 最近罵過它的人 ──
    def test_latest_message_from_a_recent_insulter_is_not_taken_up(self):
        msg = self._message("今天抽卡又歪了啦", author_id=INSULTER)
        self._run(msg, directed=False, cold={INSULTER})
        self.llm.generate_reply.assert_not_awaited()
        msg.channel.send.assert_not_awaited()

    def test_reply_aimed_at_a_recent_insulter_is_dropped(self):
        earlier = self._message("我要去北海道", author_id=INSULTER)
        msg = self._message("出國真好欸", author_id=OTHER)
        self._run(msg, directed=False, cold={INSULTER}, earlier=earlier)
        earlier.reply.assert_not_awaited()
        msg.channel.send.assert_not_awaited()

    def test_followup_from_a_recent_insulter_is_not_taken_up(self):
        msg = self._message("對啊", author_id=INSULTER)
        self._run(msg, directed=True, followup=True, cold={INSULTER}, reply="嗯")
        self.llm.generate_reply.assert_not_awaited()
        msg.reply.assert_not_awaited()

    def test_switch_off_holds_no_grudge(self):
        _switch(self, "off")
        msg = self._message("今天抽卡又歪了啦", author_id=INSULTER)
        self._run(msg, directed=False, cold={INSULTER})
        self.llm.generate_reply.assert_awaited_once()
        called = self._message("琇紫 這張圖是什麼", author_id=INSULTER)
        self._run(called, directed=True, cold={INSULTER}, reply="新角色的立繪。")
        self.assertNotIn("【你的心情】", self.llm.generate_reply.await_args.kwargs["system"])

    def test_owner_is_never_on_the_list(self):
        # 群主的紀錄就算出現在表裡（例如手動回補），也不冷落、點名不帶心情
        msg = self._message("琇紫 這張圖是什麼", author_id=OWNER)
        with mock.patch.object(ambient_insult, "bot_owner_id", lambda: OWNER):
            self._run(msg, directed=True, cold={OWNER}, reply="新角色的立繪。")
        self.assertNotIn("【你的心情】", self.llm.generate_reply.await_args.kwargs["system"])

    def test_others_still_get_spontaneous_replies(self):
        earlier = self._message("我要去北海道", author_id=INSULTER)
        msg = self._message("出國真好欸", author_id=OTHER)
        self._run(msg, directed=False, cold=set(), earlier=earlier)
        earlier.reply.assert_awaited_once()

    def test_a_recent_insulter_calling_it_still_gets_an_answer_with_a_mood(self):
        msg = self._message("琇紫 這張圖是什麼", author_id=INSULTER)
        self._run(msg, directed=True, cold={INSULTER}, reply="新角色的立繪。")
        msg.reply.assert_awaited_once()
        system = self.llm.generate_reply.await_args.kwargs["system"]
        self.assertIn("【你的心情】", system)
        self.assertIn("一共 2 次", system)

    def test_others_calling_it_get_no_mood(self):
        msg = self._message("琇紫 這張圖是什麼", author_id=OTHER)
        self._run(msg, directed=True, cold={INSULTER}, reply="新角色的立繪。")
        self.assertNotIn("【你的心情】", self.llm.generate_reply.await_args.kwargs["system"])

    def test_owner_gets_the_emoji_but_no_grudge(self):
        msg = self._message("閉嘴", author_id=OWNER)
        with mock.patch.object(ambient_insult, "bot_owner_id", lambda: OWNER):
            self._run(msg, directed=True, reply="[INSULT]", replied=self._its_message())
        msg.add_reaction.assert_awaited_once()
        self.record_insult.assert_not_called()
        self.mark_insulted.assert_not_called()


class _FakeCursor:
    """記下每句 SQL 與參數；SELECT 的結果由 fetchone_result 決定。"""

    def __init__(self, log, fetchone_result, fail_select=False):
        self.log, self.fetchone_result, self.rowcount = log, fetchone_result, 1
        self.fail_select = fail_select

    def execute(self, sql, params=None):
        if self.fail_select and sql.lstrip().startswith("SELECT"):
            raise RuntimeError('relation "ai_insults" does not exist')
        self.log.append((" ".join(sql.split()), params))

    def fetchone(self):
        return self.fetchone_result

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _FakeConn:
    def __init__(self, log, fetchone_result, fail_select=False):
        self._cur = _FakeCursor(log, fetchone_result, fail_select)

    def cursor(self):
        return self._cur

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class ReactionTests(unittest.TestCase):
    def setUp(self):
        _switch(self, "on")

    def _positive_delta(self, *, insulter_found, action="add", fail_select=False):
        log = []
        with mock.patch.object(ai_interactions_store, "_get_conn",
                               lambda: _FakeConn(log, (1,) if insulter_found else None, fail_select)):
            ai_interactions_store.note_reaction("555", "😂", None, action, INSULTER)
        update = next(params for sql, params in log if sql.startswith("UPDATE"))
        return update[1]   # (delta, pos, neg, message_id)

    def test_insulters_likes_do_not_count(self):
        self.assertEqual(0, self._positive_delta(insulter_found=True))
        self.assertEqual(0, self._positive_delta(insulter_found=True, action="remove"))

    def test_others_likes_count(self):
        self.assertEqual(1, self._positive_delta(insulter_found=False))
        self.assertEqual(-1, self._positive_delta(insulter_found=False, action="remove"))

    def test_switch_off_counts_everyone(self):
        _switch(self, "off")
        self.assertEqual(1, self._positive_delta(insulter_found=True))

    def test_list_lookup_failure_still_counts_the_like(self):
        self.assertEqual(1, self._positive_delta(insulter_found=True, fail_select=True))

    def test_list_lookup_failure_rolls_back_to_the_savepoint_before_counting(self):
        """查名單那句失敗後要先撤回到保存點：真的資料庫裡交易已經進入失敗狀態，不撤回的話下面的 UPDATE 會被拒。"""
        log = []
        with mock.patch.object(ai_interactions_store, "_get_conn", lambda: _FakeConn(log, None, True)), \
                self.assertLogs(ai_interactions_store.logger, "WARNING"):
            ai_interactions_store.note_reaction("555", "😂", None, "add", INSULTER)
        sqls = [sql for sql, _ in log]
        update_at = next(i for i, sql in enumerate(sqls) if sql.startswith("UPDATE"))
        self.assertLess(sqls.index("ROLLBACK TO SAVEPOINT insulter_check"), update_at)
        self.assertLess(sqls.index("RELEASE SAVEPOINT insulter_check"), update_at, "失敗後也收掉保存點")


class InsultedInteractionSqlTests(unittest.TestCase):
    """被罵的插話在資料庫的樣子（SQL 本身的正確性另見 integration/it_ai_insults_sql.py，用暫存表實跑）。"""

    def _sql(self, call):
        log = []
        with mock.patch.object(ai_interactions_store, "_get_conn", lambda: _FakeConn(log, None)):
            call()
        return " ".join(sql for sql, _ in log)

    def test_insulted_interjection_becomes_unwelcome(self):
        sql = self._sql(lambda: ai_interactions_store.mark_insulted("555", attempts=1))
        self.assertIn("insulted = TRUE", sql)
        self.assertIn("ELSE FALSE", sql)

    def test_it_is_never_flipped_back_to_got_reply(self):
        self.assertIn("NOT insulted", self._sql(lambda: ai_interactions_store.mark_got_reply("555", attempts=1)))

    def test_it_is_never_an_example(self):
        with mock.patch.object(ai_interactions_store, "_embed_text", lambda t: [0.1, 0.2]):
            sql = self._sql(lambda: ai_interactions_store.fetch_similar_positive("情境"))
        self.assertIn("NOT insulted", sql)

    def test_startup_creates_the_column_and_the_table(self):
        self.assertIn("ADD COLUMN IF NOT EXISTS insulted", ai_interactions_store._DDL)
        self.assertIn("CREATE TABLE IF NOT EXISTS ai_insults", ai_interactions_store._DDL)


if __name__ == "__main__":
    unittest.main()
