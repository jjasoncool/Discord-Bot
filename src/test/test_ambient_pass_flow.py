"""守的底線：插話的單次評估（`_run_one_ambient_pass`）從閘門到送出的行為不因拆段而改變。

斷言使用者看得到的事：哪些情況不勞動模型、模型回了什麼就送到哪裡（reply 還是裸送）、送出後
冷卻與額度怎麼算、接續怎麼武裝、互動紀錄記了什麼。模型與 Discord 都是假的，只有 ambient_reply
本身是真的。
"""
import asyncio
import os
import sys
import time
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

import discord  # noqa: E402

from llm.ambient import ambient_insult, ambient_reply  # noqa: E402
from llm.ambient.ambient_hooks import HookDecision  # noqa: E402

BOT_ID = 1385591938438135848
BOT_USER = SimpleNamespace(id=BOT_ID, bot=True, display_name="琇紫", name="琇紫")
SPEAKER = 430244604688990212
EARLIER_AUTHOR = 537251366008127489
GUILD_ID = 1
CHANNEL_ID = 4242
NOW = datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc)


def _http_error(text="Unknown message"):
    return discord.HTTPException(SimpleNamespace(status=400, reason="Bad"), text)


def _hook(passed=True, explore=False, veto=None, signals=None):
    return HookDecision(passed=passed, score=1.0, prob=0.9 if passed else 0.1,
                        features={}, veto=veto, explore=explore, signals=signals)


class _Message(SimpleNamespace):
    """像 discord.Message 的假物件：reply／channel.send／add_reaction 都是可檢查的 AsyncMock。"""


def _message(content="今天抽卡又歪了啦", *, author_id=SPEAKER, mid=7001, attachments=(), reference=None):
    guild = SimpleNamespace(id=GUILD_ID, me=SimpleNamespace(id=BOT_ID, display_name="琇紫", name="琇紫"),
                            emojis=[])
    return _Message(
        content=content, id=mid, reference=reference, mentions=[], stickers=[], attachments=list(attachments),
        author=SimpleNamespace(id=author_id, bot=False, display_name="某人", name="某人"),
        guild=guild,
        channel=SimpleNamespace(id=CHANNEL_ID, send=mock.AsyncMock(return_value=SimpleNamespace(id=9001))),
        created_at=NOW,
        reply=mock.AsyncMock(return_value=SimpleNamespace(id=9002)),
        add_reaction=mock.AsyncMock(),
    )


class PassFlowTests(unittest.TestCase):
    """單次評估：閘門 → 脈絡 → 模型 → 送出 → 記帳。"""

    def setUp(self):
        ambient_reply._PROC_STATE.clear()
        self.addCleanup(ambient_reply._PROC_STATE.clear)
        self.bot = SimpleNamespace(user=BOT_USER, ambient_tracker={})
        self.tracker = {"last_ts": 0.0, "hour_start": time.monotonic(), "hour_count": 0}
        self.bot.ambient_tracker[CHANNEL_ID] = self.tracker
        self.llm = SimpleNamespace(generate_reply=mock.AsyncMock(
            return_value=SimpleNamespace(reply="#1\n好喔", error_kind=None, prompt_record_log="PROMPT")))
        self.record_interaction = mock.AsyncMock()
        self.debug_writes = []
        self.skips = []
        self.stream_busy = False
        self.foreground_active = False
        self.hook = _hook()
        self.replied = None
        self.earlier = None
        self.media = {}            # id → (notes, imgs)
        self.images = {}           # id → base64 清單
        self.grudges = {}
        self.persona_cards = None
        self.memory_lines = None
        self.tag_lines = None

    def _model_says(self, reply, error_kind=None):
        self.llm.generate_reply.return_value = SimpleNamespace(
            reply=reply, error_kind=error_kind, prompt_record_log="PROMPT")

    def _run(self, message, *, directed=False, followup=False, burst=None):
        async def _fetch(msg, thread_map=None):
            if self.earlier is not None and thread_map is not None:
                thread_map[1] = self.earlier
            return (["#1 [12:00] 某人: 前一句"], [msg.author.id])

        async def _media(msg):
            return self.media.get(msg.id, ([], []))

        async def _images(msg):
            return self.images.get(msg.id)

        async def _grudges(guild_id):
            return dict(self.grudges)

        stubs = dict(
            stream_busy=lambda: self.stream_busy,
            foreground_recently_active=lambda *_a: self.foreground_active,
            _fetch_recent=mock.AsyncMock(side_effect=_fetch),
            evaluate_hook=mock.AsyncMock(return_value=self.hook),
            _load_ambient_prompt=lambda: "SYS",
            _resolve_replied_to=mock.AsyncMock(return_value=self.replied),
            _media_context=mock.AsyncMock(side_effect=_media),
            _prepare_images=mock.AsyncMock(side_effect=_images),
            _build_persona_context=mock.AsyncMock(return_value=self.persona_cards),
            recall_lines=mock.AsyncMock(return_value=self.memory_lines),
            recall_signature_tags=mock.AsyncMock(return_value=self.tag_lines),
            _build_chat_callback_context=mock.AsyncMock(return_value=None),
            _build_style_refs=mock.AsyncMock(return_value=None),
            _write_ambient_debug=lambda **k: self.debug_writes.append(k),
            _log_skip=lambda cid, reason: self.skips.append(reason),
            _record_ambient_interaction=self.record_interaction,
            _get_llm=lambda: self.llm,
        )
        self.evaluate_hook = stubs["evaluate_hook"]
        with mock.patch.multiple(ambient_reply, **stubs), \
                mock.patch.object(ambient_insult, "grudges", _grudges), \
                mock.patch.object(ambient_insult, "enabled", lambda: True):
            asyncio.run(ambient_reply._run_one_ambient_pass(
                self.bot, message, "m", directed, burst or [message], followup=followup))

    def _generate_kwargs(self):
        self.llm.generate_reply.assert_awaited_once()
        return self.llm.generate_reply.await_args.kwargs

    def _state(self):
        return ambient_reply._get_proc_state(CHANNEL_ID)

    # ── 閘門：不勞動模型 ──
    def test_burst_without_substance_is_skipped(self):
        msg = _message("笑死")
        self._run(msg, burst=[_message("XD"), msg])
        self.llm.generate_reply.assert_not_awaited()
        self.assertTrue(any("burst" in s for s in self.skips))

    def test_one_substantive_message_in_the_burst_lets_it_through(self):
        msg = _message("笑死")
        self._run(msg, burst=[_message("這版的新角色輸出真的高嗎"), msg])
        self.llm.generate_reply.assert_awaited_once()

    def test_cooldown_blocks_spontaneous_only(self):
        self.tracker["last_ts"] = time.monotonic()
        self._run(_message())
        self.llm.generate_reply.assert_not_awaited()
        self.assertTrue(any("冷卻" in s for s in self.skips))
        self._run(_message(), directed=True)
        self.llm.generate_reply.assert_awaited_once()

    def test_followup_ignores_cooldown_but_not_the_hourly_cap(self):
        self.tracker["last_ts"] = time.monotonic()
        self._run(_message(), directed=True, followup=True)
        self.llm.generate_reply.assert_awaited_once()
        self.tracker["hour_count"] = ambient_reply._SETTINGS.hourly_cap
        self._run(_message(), directed=True, followup=True)
        self.llm.generate_reply.assert_awaited_once()     # 第二次沒再叫模型

    def test_hourly_window_resets_after_an_hour(self):
        self.tracker.update(hour_start=time.monotonic() - 3700, hour_count=ambient_reply._SETTINGS.hourly_cap)
        self._run(_message())
        self.llm.generate_reply.assert_awaited_once()
        self.assertEqual(1, self.tracker["hour_count"])

    def test_foreground_activity_yields_for_spontaneous_and_followup_but_not_directed(self):
        self.foreground_active = True
        self._run(_message())
        self._run(_message(), directed=True, followup=True)
        self.llm.generate_reply.assert_not_awaited()
        self._run(_message(), directed=True)
        self.llm.generate_reply.assert_awaited_once()

    def test_backoff_words_in_the_window_silence_spontaneous_and_followup(self):
        self._run(_message("你很煩欸"))
        self._run(_message("對啊"), directed=True, followup=True)   # 觸發訊息沒有字眼，脈絡也沒有 → 通
        self.assertEqual(1, self.llm.generate_reply.await_count)
        self.assertTrue(any("降溫" in s for s in self.skips))

    def test_hook_veto_stops_spontaneous_and_hook_is_skipped_when_directed(self):
        self.hook = _hook(passed=False, veto="nobody")
        self._run(_message())
        self.llm.generate_reply.assert_not_awaited()
        self.evaluate_hook.assert_awaited_once()
        self.assertTrue(any("鉤子" in s and "nobody" in s for s in self.skips))
        self._run(_message(), directed=True)
        self.evaluate_hook.assert_not_awaited()           # 被點名不評鉤子
        self.llm.generate_reply.assert_awaited_once()

    def test_hook_sees_the_trigger_message_too(self):
        self.earlier = _message("前一句", author_id=EARLIER_AUTHOR, mid=6000)
        msg = _message()
        self._run(msg)
        seen = self.evaluate_hook.await_args.args[0]
        self.assertEqual([6000, 7001], [m.id for m in seen])

    def test_image_only_message_with_failed_download_has_nothing_to_say(self):
        msg = _message("", attachments=[SimpleNamespace(filename="a.png", size=10)])
        self._run(msg)
        self.llm.generate_reply.assert_not_awaited()
        self._run(msg, directed=True)                       # 被點名還是要回
        self.llm.generate_reply.assert_awaited_once()
        self.assertEqual("(對方只 @ 了我，沒有文字)", self._generate_kwargs()["prompt"])

    # ── 脈絡怎麼包 ──
    def test_directed_prompt_is_the_text_with_the_speaker_named(self):
        self._run(_message("琇紫你覺得呢"), directed=True)
        kw = self._generate_kwargs()
        self.assertEqual("琇紫你覺得呢", kw["prompt"])
        self.assertTrue(kw["asker_display_name"].startswith("某人#"))
        self.assertTrue(kw["bot_display_name"].startswith("琇紫#"))
        self.assertIsNone(kw["situation_signals"])
        self.assertEqual(["#1 [12:00] 某人: 前一句"], kw["chat_context"])

    def test_spontaneous_prompt_appends_the_trigger_as_a_numbered_line(self):
        self.earlier = _message("前一句", author_id=EARLIER_AUTHOR, mid=6000)
        self.hook = _hook(signals=["甲問了沒人回"])
        self._run(_message("這版的新角色輸出真的高嗎"))
        kw = self._generate_kwargs()
        self.assertIsNone(kw["asker_display_name"])
        self.assertIn("[PASS]", kw["prompt"])
        self.assertEqual(2, len(kw["chat_context"]))
        self.assertTrue(kw["chat_context"][1].startswith("#2 "))
        self.assertIn("這版的新角色輸出真的高嗎", kw["chat_context"][1])
        self.assertEqual(["甲問了沒人回"], kw["situation_signals"])

    def test_spontaneous_image_message_becomes_a_placeholder_line(self):
        msg = _message("", attachments=[SimpleNamespace(filename="a.png", size=10)])
        self.images[msg.id] = ["IMG1"]
        self._run(msg)
        kw = self._generate_kwargs()
        self.assertIn("(貼了一張圖)", kw["chat_context"][-1])
        self.assertEqual(["IMG1"], kw["images"])

    def test_replied_to_message_is_quoted_truncated_and_its_images_added(self):
        replied = _message("甲" * 300, author_id=EARLIER_AUTHOR, mid=6000,
                           attachments=[SimpleNamespace(filename="b.jpg", size=10)])
        self.replied = replied
        self.images[6000] = ["REF"]
        self.media[6000] = (["（X 貼文：內容）"], ["TW"])
        self.media[7001] = (["（表情 :x: 是一隻貓）"], [])
        self._run(_message("這個怎麼說"), directed=True)
        kw = self._generate_kwargs()
        self.assertTrue(kw["replied_to_from"].startswith("某人#"))
        self.assertTrue(kw["replied_to_text"].startswith("甲" * 200 + "…"))
        self.assertIn("（X 貼文：內容）", kw["replied_to_text"])
        self.assertEqual(["REF", "TW"], kw["images"])
        self.assertEqual("這個怎麼說\n（表情 :x: 是一隻貓）", kw["prompt"])

    def test_image_payload_is_capped(self):
        cap = ambient_reply._SETTINGS.image_max_count
        msg = _message("看這些", attachments=[SimpleNamespace(filename="a.png", size=10)])
        self.images[msg.id] = [f"I{i}" for i in range(cap)]
        self.media[msg.id] = ([], ["EXTRA"])
        self._run(msg, directed=True)
        self.assertEqual(cap, len(self._generate_kwargs()["images"]))

    def test_persona_memory_and_tags_are_one_persona_context(self):
        self.persona_cards, self.memory_lines, self.tag_lines = ["卡"], ["偏好"], ["招牌"]
        self._run(_message(), directed=True)
        self.assertEqual(["卡", "偏好", "招牌"], self._generate_kwargs()["persona_context"])

    def test_grudge_adds_the_mood_only_when_that_person_mentions_it(self):
        self.grudges = {SPEAKER: ambient_insult.Grudge(last_at=NOW, times=2)}
        self._run(_message(), directed=True)
        self.assertIn("【你的心情】", self._generate_kwargs()["system"])
        self.llm.generate_reply.reset_mock()
        self.grudges = {}
        self._run(_message(), directed=True)
        self.assertEqual("SYS", self._generate_kwargs()["system"])

    def test_generation_uses_the_ambient_model_and_timeout(self):
        self._run(_message(), directed=True)
        kw = self._generate_kwargs()
        self.assertEqual("m", kw["model"])
        self.assertEqual(int(ambient_reply._SETTINGS.pass_timeout_seconds), kw["timeout"])
        self.assertTrue(kw["trace_id"].startswith(f"amb-{CHANNEL_ID}-"))

    # ── 模型說了什麼 → 送到哪 ──
    def test_pass_sends_nothing_but_is_logged_for_debug(self):
        for reply in ("[PASS]", "[Pass]", "pass", ""):
            with self.subTest(reply=reply):
                self.debug_writes.clear()
                self._model_says(reply)
                msg = _message()
                self._run(msg, directed=True)
                msg.reply.assert_not_awaited()
                self.assertEqual("pass", self.debug_writes[-1]["outcome"])
        self.record_interaction.assert_not_awaited()

    def test_error_sends_nothing_and_records_the_kind(self):
        self._model_says("", error_kind="timeout")
        msg = _message()
        self._run(msg, directed=True)
        msg.reply.assert_not_awaited()
        self.assertEqual("error:timeout", self.debug_writes[-1]["outcome"])
        self.assertEqual(0.0, self.tracker["last_ts"])

    def test_directed_answer_replies_to_the_trigger_without_pinging(self):
        self._model_says("上個版本的。")
        msg = _message()
        self._run(msg, directed=True)
        msg.reply.assert_awaited_once_with("上個版本的。", mention_author=False)
        msg.channel.send.assert_not_awaited()
        self.assertEqual("reply", self.debug_writes[-1]["outcome"])
        self.assertEqual("上個版本的。", self.debug_writes[-1]["reply"])

    def test_directed_reply_falls_back_to_the_channel_when_the_trigger_is_gone(self):
        self._model_says("在。")
        msg = _message()
        msg.reply.side_effect = _http_error()
        with self.assertNoLogs("llm.ambient.ambient_reply", level="WARNING"):
            self._run(msg, directed=True)
        msg.channel.send.assert_awaited_once()
        self.assertEqual("在。", msg.channel.send.await_args.args[0])
        self.assertEqual("9001", self._state()["last_reply_message_id"])

    def test_spontaneous_answer_replies_to_the_line_the_model_chose(self):
        self.earlier = _message("前一句", author_id=EARLIER_AUTHOR, mid=6000)
        self._model_says("#1\n我也覺得")
        msg = _message()
        self._run(msg)
        self.earlier.reply.assert_awaited_once_with("我也覺得", mention_author=False)
        msg.channel.send.assert_not_awaited()
        self.assertEqual("#1\n我也覺得", self.debug_writes[-1]["reply"])   # debug 留原樣，看得出選了哪條
        self.assertEqual(EARLIER_AUTHOR, self._state()["last_anchor_author_id"])

    def test_spontaneous_answer_can_anchor_on_the_trigger_itself(self):
        # 觸發訊息也有編號（接在脈絡最大號之後）；模型選它就 reply 它
        self.earlier = _message("前一句", author_id=EARLIER_AUTHOR, mid=6000)
        self._model_says("#2\n我也覺得")
        msg = _message()
        self._run(msg)
        msg.reply.assert_awaited_once_with("我也覺得", mention_author=False)
        msg.channel.send.assert_not_awaited()

    def test_spontaneous_answer_without_a_number_is_sent_bare(self):
        self._model_says("我也覺得")
        msg = _message()
        self._run(msg)
        msg.reply.assert_not_awaited()
        msg.channel.send.assert_awaited_once()
        self.assertEqual("我也覺得", msg.channel.send.await_args.args[0])
        self.assertEqual(SPEAKER, self._state()["last_anchor_author_id"])

    def test_spontaneous_anchor_failure_falls_back_to_bare_send(self):
        self.earlier = _message("前一句", author_id=EARLIER_AUTHOR, mid=6000)
        self.earlier.reply.side_effect = _http_error()
        self._model_says("#1\n我也覺得")
        msg = _message()
        self._run(msg)
        msg.channel.send.assert_awaited_once()

    def test_send_failure_counts_nothing(self):
        self._model_says("我也覺得")
        msg = _message()
        msg.channel.send.side_effect = _http_error("boom")
        with self.assertLogs("llm.ambient.ambient_reply", level="WARNING"):
            self._run(msg)
        self.assertEqual(0, self.tracker["hour_count"])
        self.assertFalse(self._state().get("followup_armed"))
        self.record_interaction.assert_not_awaited()

    def test_reply_aimed_at_a_recent_insulter_is_dropped_before_sending(self):
        self.earlier = _message("前一句", author_id=EARLIER_AUTHOR, mid=6000)
        self.grudges = {EARLIER_AUTHOR: ambient_insult.Grudge(last_at=NOW, times=1)}
        self._model_says("#1\n我也覺得")
        msg = _message()
        self._run(msg)
        self.earlier.reply.assert_not_awaited()
        msg.channel.send.assert_not_awaited()
        self.record_interaction.assert_not_awaited()

    # ── 送出後的記帳 ──
    def test_only_spontaneous_replies_consume_cooldown_and_quota(self):
        self._model_says("嗯")
        self._run(_message(), directed=True)
        self.assertEqual((0.0, 0), (self.tracker["last_ts"], self.tracker["hour_count"]))
        self._run(_message(), directed=True, followup=True)
        self.assertEqual((0.0, 1), (self.tracker["last_ts"], self.tracker["hour_count"]))
        self.tracker["hour_count"] = 0
        self._run(_message())
        self.assertGreater(self.tracker["last_ts"], 0.0)
        self.assertEqual(1, self.tracker["hour_count"])

    def test_sending_arms_the_followup_and_resets_the_chain_unless_following_up(self):
        self._model_says("嗯")
        self._state()["followup_chain"] = 3
        self._run(_message(), directed=True, followup=True)
        state = self._state()
        self.assertTrue(state["followup_armed"])
        self.assertEqual("9002", state["last_reply_message_id"])
        self.assertEqual(3, state["followup_chain"])
        self._run(_message(), directed=True)
        self.assertEqual(0, self._state()["followup_chain"])

    def test_interaction_record_carries_kind_text_and_explore_flag(self):
        self.hook = _hook(explore=True)
        self._model_says("好喔")
        msg = _message("這版的新角色輸出真的高嗎")
        self._run(msg)
        kw = self.record_interaction.await_args.kwargs
        self.assertEqual((False, False, True), (kw["directed"], kw["followup"], kw["explore_sample"]))
        self.assertEqual("好喔", kw["reply"])
        self.assertEqual("這版的新角色輸出真的高嗎", kw["stripped"])
        self.assertEqual(9001, kw["sent_msg"].id)   # 沒給編號→裸送到頻道
        self.assertTrue(kw["trace_id"].startswith("amb-"))

    def test_followup_record_is_marked_as_followup(self):
        self._model_says("嗯")
        self._run(_message(), directed=True, followup=True)
        kw = self.record_interaction.await_args.kwargs
        self.assertEqual((True, True), (kw["directed"], kw["followup"]))


if __name__ == "__main__":
    unittest.main()
