"""守的底線：插話的單次評估（`_run_one_ambient_pass`）從閘門到送出的行為不因拆段而改變。

斷言使用者看得到的事：哪些情況不勞動模型、模型回了什麼就送到哪裡（reply 還是裸送）、送出後
冷卻與額度怎麼算、接續怎麼武裝、互動紀錄記了什麼。模型與 Discord 都是假的，只有 ambient_reply
本身是真的。
另守：查詢工具有就交給模型（一輪、插話的提醒、不退回不帶工具的呼叫），沒有就跟原本一樣；今天的日期一起送；
被 @ 才有輸出上限；夾著工具呼叫原文的回答不送；回覆超過 Discord 上限只送第一段、回覆不 @ 任何人；
最新這則 @ 的人要傳進人物卡檢索與回憶對象（給模型看的文字已把 @ 換成名字，從那裡抓不到）。
一輪最多給模型 3 張圖（動圖算一張、最多 1 張，那張照樣帶全部的幀），收滿就不再抓：最新那則 → 被回覆那則 →
回覆鏈再往前（只追一小時內、最多 6 則，近的優先）→ 聊天紀錄裡被人回覆過的圖（近的優先；沒人回覆的不收）。
自己貼的圖沒抓到時，補上的舊圖要標明是更早的一則。
回覆鏈上是它自己的話：先附它當時對著講的那一則的圖（查互動紀錄；它的自動轉貼、別人的話不查）。
被回覆那則、最新那則的圖（附件、連結預覽）抓不到時，在那則後面標「（這張圖沒抓到）」，模型才不會自己編看不到的理由。
有附圖就給圖片清單：每張是誰、在哪一則貼的（發問的這則／聊天紀錄第幾行／更早的一則）、動圖是同一張的幾幀、
預覽與貼文的圖不說成群友貼的、聊天紀錄裡哪幾行的圖沒附；沒附圖就沒有清單。
被點名時才帶這個頻道最近被刪的訊息（查觸發那則所在的頻道；最新那句、被回覆那句、最近幾行聊天交去判斷有沒有人問），
自發插話不帶；近況交給改過訊息的附註。
"""
import asyncio
import os
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

import psycopg2  # noqa: E402

from llm.ambient import ambient_insult, ambient_reply, ambient_search, ambient_style_lines  # noqa: E402
from llm.storage import ai_interactions_store, deleted_and_edited  # noqa: E402
from llm.ambient.ambient_hooks import HookDecision  # noqa: E402
from llm.preprocess.vision_image import VisionFetch  # noqa: E402
from sys_settings import switches  # noqa: E402
from sys_settings.switches import Switches  # noqa: E402

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


def _att(mid, index=0, name=None):
    """一張貼上去的圖；網址記著是哪一則的第幾張，假的抓圖照它找 `self.images`。"""
    return SimpleNamespace(filename=name or f"{mid}.png", size=10, url=f"att://{mid}/{index}")


def _preview(picture, *, title="影片標題", url="https://example.com/v/1"):
    """Discord 幫連結抓到的預覽，帶一張縮圖。"""
    return SimpleNamespace(url=url, title=title, description=None, image=None,
                           thumbnail=SimpleNamespace(url=picture, proxy_url=None, width=None, height=None))


def _message(content="今天抽卡又歪了啦", *, author_id=SPEAKER, mid=7001, attachments=(), reference=None,
             created_at=NOW, embeds=()):
    attachments = [att if getattr(att, "url", None) else _att(mid, index, att.filename)
                   for index, att in enumerate(attachments)]
    guild = SimpleNamespace(id=GUILD_ID, me=SimpleNamespace(id=BOT_ID, display_name="琇紫", name="琇紫"),
                            emojis=[])
    return _Message(
        content=content, id=mid, reference=reference, mentions=[], stickers=[], attachments=list(attachments),
        embeds=list(embeds),
        author=SimpleNamespace(id=author_id, bot=False, display_name="某人", name="某人"),
        guild=guild,
        channel=SimpleNamespace(id=CHANNEL_ID, send=mock.AsyncMock(return_value=SimpleNamespace(id=9001))),
        created_at=created_at,
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
        self.chain = {}            # id → 那則用回覆功能回的訊息（被回覆那則再往前）
        self.looked_up = []        # 往回讀過哪些訊息的回覆對象
        self.earlier = None
        self.window = []           # 聊天紀錄視窗裡的訊息，照順序是 #1、#2…（給了就不看 earlier）
        self.chat_lines = ["#1 [12:00] 某人: 前一句"]   # 聊天紀錄那幾行的文字
        self.media = {}            # id → (notes, imgs)
        self.images = {}           # id → 那則每張附件抓到的圖（一張是字串，動圖是幾幀的清單）；沒列的就是沒抓到
        self.fetched = []          # 真的去抓了哪些網址
        self.preview_frames = {}   # 預覽縮圖的網址 → 抓到的圖
        self.said_about = {}       # 它的某句話（訊息 id）→ 當時觸發它的那則的 id（互動紀錄）
        self.asked_about = []      # 查過哪幾句話的互動紀錄
        self.by_id = {}            # 用 id 還讀得到的訊息
        self.grudges = {}
        self.persona_cards = None
        self.memory_lines = None
        self.tag_lines = None
        self.style_refs = mock.AsyncMock(return_value=None)
        self.style_lines = mock.AsyncMock(return_value=None)
        self.style_lines_on = False
        self.search_tools = None
        self.deleted = ["[11/11 20:57] 某人#0001【已刪，發出後 2 秒刪掉】: 打錯了"]
        self.deleted_calls = []

    def _model_says(self, reply, error_kind=None):
        self.llm.generate_reply.return_value = SimpleNamespace(
            reply=reply, error_kind=error_kind, prompt_record_log="PROMPT")

    def _run(self, message, *, directed=False, followup=False, burst=None):
        async def _fetch(msg, thread_map=None):
            if thread_map is not None:
                window = self.window or ([self.earlier] if self.earlier is not None else [])
                thread_map.update({number: earlier for number, earlier in enumerate(window, start=1)})
            return (list(self.chat_lines), [msg.author.id])

        async def _media(msg):
            return self.media.get(msg.id, ([], []))

        async def _fetch_picture(session, image, *, max_frames=4, **_kwargs):
            self.fetched.append(image.url)
            if not image.url.startswith("att://"):
                return VisionFetch(list(self.preview_frames.get(image.url) or [])[:max_frames])
            mid, index = image.url.removeprefix("att://").split("/")
            got = self.images.get(int(mid)) or []
            frames = got[int(index)] if int(index) < len(got) else []
            frames = [frames] if isinstance(frames, str) else list(frames)
            return VisionFetch(frames[:max_frames])

        async def _referenced(bot, msg):
            self.looked_up.append(msg.id)
            return self.replied if msg is message else self.chain.get(msg.id)

        def _trigger_of(reply_id):
            self.asked_about.append(int(reply_id))
            return self.said_about.get(int(reply_id))

        async def _grudges(guild_id):
            return dict(self.grudges)

        async def _deleted(guild, channel, *, tz, asked):
            self.deleted_calls.append(channel)
            self.deleted_asked = list(asked)
            return self.deleted

        stubs = dict(
            stream_busy=lambda: self.stream_busy,
            foreground_recently_active=lambda *_a: self.foreground_active,
            _fetch_recent=mock.AsyncMock(side_effect=_fetch),
            evaluate_hook=mock.AsyncMock(return_value=self.hook),
            _load_ambient_prompt=lambda: "SYS",
            _referenced_message=mock.AsyncMock(side_effect=_referenced),
            _media_context=mock.AsyncMock(side_effect=_media),
            fetch_for_vision=_fetch_picture,
            trigger_message_id=_trigger_of,
            _message_by_id=mock.AsyncMock(side_effect=lambda bot, channel, mid: self.by_id.get(mid)),
            _build_persona_context=mock.AsyncMock(return_value=self.persona_cards),
            recall_lines=mock.AsyncMock(return_value=self.memory_lines),
            recall_signature_tags=mock.AsyncMock(return_value=self.tag_lines),
            _build_chat_callback_context=mock.AsyncMock(return_value=None),
            _build_style_refs=self.style_refs,
            _build_style_lines=self.style_lines,
            _prepare_search_tools=mock.AsyncMock(side_effect=lambda *a, **k: self.search_tools),
            _write_ambient_debug=lambda **k: self.debug_writes.append(k),
            _log_skip=lambda cid, reason: self.skips.append(reason),
            _record_ambient_interaction=self.record_interaction,
            _get_llm=lambda: self.llm,
        )
        self.evaluate_hook = stubs["evaluate_hook"]
        self.persona_builder = stubs["_build_persona_context"]
        self.prepare_search = stubs["_prepare_search_tools"]
        with mock.patch.multiple(ambient_reply, **stubs), \
                mock.patch.object(ambient_style_lines, "enabled", lambda: self.style_lines_on), \
                mock.patch.object(ambient_insult, "grudges", _grudges), \
                mock.patch.object(ambient_insult, "enabled", lambda: True), \
                mock.patch.object(deleted_and_edited, "deleted_context", _deleted):
            asyncio.run(ambient_reply._run_one_ambient_pass(
                self.bot, message, "m", directed, burst or [message], followup=followup))

    def _generate_kwargs(self):
        self.llm.generate_reply.assert_awaited_once()
        return self.llm.generate_reply.await_args.kwargs

    def _state(self):
        return ambient_reply._get_proc_state(CHANNEL_ID)

    # ── 被刪的訊息：被點名才帶 ──
    def test_directed_replies_get_this_channels_deleted_messages(self):
        message = _message("剛剛誰刪了什麼")
        self._run(message, directed=True)
        self.assertEqual(self.deleted, self._generate_kwargs()["deleted_messages"])
        self.assertEqual([message.channel], self.deleted_calls)

    def test_whether_someone_asked_is_judged_from_the_trigger_the_replied_message_and_the_last_lines(self):
        # 問的人常常沒有 @ 她，是下一個人才叫她：最新那句、它回覆的那句、最近幾行聊天都要交去判斷
        self.replied = _message("他是不是偷刪了", author_id=EARLIER_AUTHOR, mid=6000)
        self._run(_message("你有看到嗎"), directed=True)
        self.assertEqual(["你有看到嗎", "他是不是偷刪了", "#1 [12:00] 某人: 前一句"], self.deleted_asked)

        self.chat_lines = [f"#{n} [12:0{n}] 某人: 第 {n} 行" for n in range(1, 8)]
        self._run(_message("你有看到嗎"), directed=True)
        self.assertEqual(self.chat_lines[-5:], self.deleted_asked[2:], "只看最近幾行，更早的話題不算")

    def test_spontaneous_replies_never_look_at_deleted_messages(self):
        self._run(_message("這波真的很誇張"))
        self.assertIsNone(self._generate_kwargs()["deleted_messages"])
        self.assertEqual([], self.deleted_calls, "沒人問就不翻")

    # ── 語氣參考：開關決定句子從哪來，說明跟著句子走 ──
    def test_style_lines_off_keeps_the_old_refs_and_their_note(self):
        self.style_refs.return_value = ["舊句"]
        self._run(_message("這波真的很誇張"))
        kwargs = self._generate_kwargs()
        self.assertEqual(["舊句"], kwargs["style_refs"])
        self.assertIsNone(kwargs["style_refs_note"])
        self.style_lines.assert_not_awaited()

    def test_style_lines_on_sends_the_lines_with_their_own_note(self):
        self.style_lines_on = True
        self.style_lines.return_value = ["・（情境）一句"]
        self._run(_message("這波真的很誇張"))
        kwargs = self._generate_kwargs()
        self.assertEqual(["・（情境）一句"], kwargs["style_refs"])
        self.assertEqual(ambient_style_lines.NOTE, kwargs["style_refs_note"])
        self.style_refs.assert_not_awaited()

    # ── 思考強度：只有插話照開關走 ──
    def _effort_sent_with(self, value):
        with mock.patch.object(switches, "current", lambda: Switches(ambient_reasoning_effort=value)):
            self._run(_message("這波真的很誇張"))
        return self._generate_kwargs()["reasoning_effort"]

    def test_the_default_effort_sends_nothing(self):
        self.assertIsNone(self._effort_sent_with("default"))

    def test_a_chosen_effort_is_sent(self):
        self.assertEqual("medium", self._effort_sent_with("medium"))

    # ── 閘門：不勞動模型 ──
    def test_burst_without_substance_is_skipped(self):
        msg = _message("笑死")
        self._run(msg, burst=[_message("XD"), msg])
        self.llm.generate_reply.assert_not_awaited()
        self.prepare_search.assert_not_awaited()          # 閘門擋下的不去準備查詢工具（不連 search-mcp）
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
        self.prepare_search.assert_not_awaited()          # 鉤子閘擋下的也不去準備查詢工具
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
        self.assertEqual("(對方只 @ 了我，沒有文字)\n（這張圖沒抓到）", self._generate_kwargs()["prompt"])

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
        self.assertTrue(kw["chat_context"][-1].endswith(": (圖)"), "跟聊天紀錄其他行同一個標記")
        self.assertEqual(["IMG1"], kw["images"])

    def test_a_bare_mention_is_not_said_to_carry_a_picture_that_someone_else_posted(self):
        picture = self._said("", 6000, 3, image=True)
        self.replied = picture
        self.images[6000] = ["THEIRS"]
        self._run(_message("", reference=SimpleNamespace(message_id=6000, resolved=None)), directed=True)
        kw = self._generate_kwargs()
        self.assertEqual(["THEIRS"], kw["images"])
        self.assertEqual("(對方只 @ 了我，沒有文字)", kw["prompt"], "圖是被回覆那則的，不是發問的人貼的")

        self.llm.generate_reply.reset_mock()
        own = _message("", attachments=[_att(7001)])
        self.images[7001] = ["MINE"]
        self._run(own, directed=True)
        self.assertEqual("(對方貼了一張圖)", self._generate_kwargs()["prompt"])

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

    def test_at_most_three_pictures_go_to_the_model(self):
        msg = _message("看這些", attachments=[_att(7001, i) for i in range(5)])
        self.images[msg.id] = [f"I{i}" for i in range(5)]
        self.media[msg.id] = ([], ["EXTRA"])
        self._run(msg, directed=True)
        kw = self._generate_kwargs()
        self.assertEqual(["I0", "I1", "I2"], kw["images"])
        self.assertEqual(["att://7001/0", "att://7001/1", "att://7001/2"], self.fetched, "收滿就不再抓")
        self.assertTrue(kw["image_note"].splitlines()[3].endswith("（那則貼了 5 張，這次只附 3 張）"), kw["image_note"])

    def test_what_the_latest_message_brought_comes_before_the_replied_messages_pictures(self):
        self.replied = self._said("", 6000, 3, image=True)
        self.images[6000] = ["REPLIED"]
        msg = _message("那這篇呢 https://example.com/v/1", embeds=[_preview("https://i.example/a.jpg")])
        self.media[msg.id] = (["（X 貼文：內容）"], ["TWEET"])
        self.preview_frames["https://i.example/a.jpg"] = ["THUMB"]
        self._run(msg, directed=True)
        self.assertEqual(["TWEET", "THUMB", "REPLIED"], self._generate_kwargs()["images"])

    def test_only_one_moving_picture_is_taken_and_it_keeps_its_frames(self):
        msg = _message("看這些", attachments=[_att(7001, 0, "a.gif"), _att(7001, 1, "b.gif"), _att(7001, 2, "c.png")])
        self.images[msg.id] = [["A1", "A2", "A3", "A4"], ["B1", "B2", "B3", "B4"], "STILL"]
        self._run(msg, directed=True)
        kw = self._generate_kwargs()
        self.assertEqual(["A1", "A2", "A3", "A4", "STILL"], kw["images"])
        self.assertNotIn("att://7001/1", self.fetched, "第二張動圖不收，也不去抓")
        self.assertIn("那則貼了 3 張，這次只附 2 張", kw["image_note"])

    def test_a_picture_that_turns_out_to_move_gives_one_frame_once_the_moving_slot_is_used(self):
        # 沒標成動圖、抓回來才知道會動的：動圖的名額用掉之後只拿一幀
        msg = _message("看這些", attachments=[_att(7001, 0, "a.gif"), _att(7001, 1, "b.png")])
        self.images[msg.id] = [["A1", "A2", "A3", "A4"], ["B1", "B2", "B3", "B4"]]
        self._run(msg, directed=True)
        self.assertEqual(["A1", "A2", "A3", "A4", "B1"], self._generate_kwargs()["images"])

    # ── 圖片清單：每張圖是誰、在哪一則貼的 ──
    def _list(self):
        return self._generate_kwargs()["image_note"].splitlines()

    def test_no_pictures_means_no_picture_list(self):
        self._run(_message("今天抽卡又歪了啦"), directed=True)
        self.assertIsNone(self._generate_kwargs()["image_note"])

    def test_the_askers_own_picture_is_listed_as_theirs(self):
        msg = _message("看這張", attachments=[_att(7001)])
        self.images[7001] = ["MINE"]
        self._run(msg, directed=True)
        lines = self._list()
        self.assertEqual("這次附了 1 張圖，照順序：", lines[0])
        self.assertTrue(lines[1].startswith("・第 1 張：發問的這則，某人#"), lines[1])
        self.assertTrue(lines[1].endswith("20:00 貼的"), lines[1])
        self.assertEqual("講圖裡的東西之前，先對一下那張是誰貼的。", lines[-1])

    def test_a_picture_people_replied_to_comes_along_with_the_latest_one(self):
        # 實例：甲貼梗圖、乙回覆它「我沒哭」、甲再貼一張哭臉。只給最新那張時，模型把哭臉當成乙回覆的那張、拿去虧乙
        meme = self._said("", 6000, 3, image=True)
        self.window = [meme, _message("我沒哭", mid=6001, reference=SimpleNamespace(message_id=6000, resolved=None))]
        self.images[6000] = ["MEME"]
        msg = _message("", author_id=EARLIER_AUTHOR, attachments=[_att(7001)])
        self.images[7001] = ["CRYING"]
        self._run(msg)
        kw = self._generate_kwargs()
        self.assertEqual(["CRYING", "MEME"], kw["images"], "最新那則的先，再來是被人回覆過的那張")
        lines = self._list()
        self.assertTrue(lines[1].startswith("・第 1 張：聊天紀錄 #3，某人#"), lines[1])
        self.assertTrue(lines[2].startswith("・第 2 張：聊天紀錄 #1，某人#"), lines[2])
        self.assertTrue(lines[2].endswith("19:57 貼的（#2 回覆的就是這張）"), lines[2])
        self.assertNotIn("沒附", kw["image_note"])

    def test_window_pictures_nobody_replied_to_are_left_out_and_named(self):
        self.window = [self._said("", 6000, 5, image=True), self._said("今天好冷", 6001, 4)]
        self.images[6000] = ["IGNORED"]
        msg = _message("", attachments=[_att(7001)])
        self.images[7001] = ["LATEST"]
        self._run(msg)
        kw = self._generate_kwargs()
        self.assertEqual(["LATEST"], kw["images"])
        self.assertNotIn("att://6000/0", self.fetched)
        lines = self._list()
        self.assertTrue(lines[1].startswith("・第 1 張：聊天紀錄 #3，某人#"), lines[1])
        self.assertEqual("聊天紀錄裡其他標 (圖) 的行（#1）這次沒附，那些圖你沒看到。", lines[2])

    def test_window_pictures_are_taken_nearest_first_until_full(self):
        for n in range(4):   # 四張圖，各有人回覆
            picture = self._said("", 6000 + 2 * n, 20 - 2 * n, image=True)
            self.images[picture.id] = [f"P{n}"]
            self.window += [picture, _message("笑死", mid=6001 + 2 * n,
                                              reference=SimpleNamespace(message_id=picture.id, resolved=None))]
        self._run(_message("你們在笑什麼"), directed=True)
        kw = self._generate_kwargs()
        self.assertEqual(["P3", "P2", "P1"], kw["images"])
        self.assertIn("其他標 (圖) 的行（#1）這次沒附", kw["image_note"])

    def test_the_replied_picture_says_who_posted_it_and_who_replied_to_it(self):
        picture = self._said("", 6000, 9, image=True)
        self.window = [picture]
        self.replied = picture
        self.images[6000] = ["PIC"]
        self._run(_message("這張是什麼", reference=SimpleNamespace(message_id=6000, resolved=None)), directed=True)
        self.assertEqual(["PIC"], self._generate_kwargs()["images"], "被回覆那則也在聊天紀錄裡，不重複收")
        line = self._list()[1]
        self.assertTrue(line.startswith("・第 1 張：聊天紀錄 #1，某人#"), line)
        self.assertIn("19:51 貼的", line)
        self.assertIn("發問的這則 回覆的就是這張", line)

    def test_a_moving_picture_is_listed_as_one_picture_in_several_frames(self):
        msg = _message("看這兩張", attachments=[_att(7001, 0, "a.gif"), _att(7001, 1, "b.png")])
        self.images[7001] = [["F1", "F2", "F3", "F4"], "STILL"]
        self._run(msg, directed=True)
        lines = self._list()
        self.assertEqual("這次附了 5 張圖，照順序：", lines[0])
        self.assertTrue(lines[1].startswith("・第 1～4 張：發問的這則"), lines[1])
        self.assertTrue(lines[1].endswith("貼的動圖，同一張圖照時間順序的 4 幀"), lines[1])
        self.assertTrue(lines[2].startswith("・第 5 張：發問的這則"), lines[2])

    def test_preview_and_post_pictures_are_not_listed_as_something_a_member_posted(self):
        msg = _message("你們看這個 https://example.com/v/1", embeds=[_preview("https://i.example/a.jpg")])
        self.preview_frames["https://i.example/a.jpg"] = ["THUMB"]
        self.media[7001] = (["（X 貼文：內容）"], ["TW"])
        self._run(msg, directed=True)
        lines = self._list()
        self.assertIn("那則裡 X 貼文或表情貼圖的圖", lines[1])
        self.assertIn("那則的連結預覽縮圖", lines[2])
        self.assertNotIn("貼的", lines[1] + lines[2])

    def test_a_message_with_more_pictures_than_were_attached_says_so(self):
        msg = _message("看這兩張", attachments=[_att(7001, 0), _att(7001, 1)])
        self.images[7001] = ["ONE"]          # 第二張沒抓到
        self._run(msg, directed=True)
        self.assertTrue(self._list()[1].endswith("（那則貼了 2 張，這次只附 1 張）"), self._list()[1])

    # ── 連結預覽上的圖 ──
    def test_a_moving_preview_brings_all_its_frames(self):
        msg = _message("你們看這個 https://example.com/v/1", embeds=[_preview("https://i.example/a.gif")])
        self.preview_frames["https://i.example/a.gif"] = ["F1", "F2", "F3", "F4"]
        self._run(msg, directed=True)
        kw = self._generate_kwargs()
        self.assertEqual(["F1", "F2", "F3", "F4"], kw["images"], "預覽的額度算個數，不把動圖的幀砍掉")
        self.assertIn("[預覽：影片標題]", kw["prompt"])

    def test_a_preview_picture_that_could_not_be_fetched_is_marked(self):
        msg = _message("你們看這個 https://example.com/v/1", embeds=[_preview("https://i.example/a.jpg")])
        self._run(msg, directed=True)
        kw = self._generate_kwargs()
        self.assertIsNone(kw["images"])
        self.assertTrue(kw["prompt"].endswith("[預覽：影片標題]（這張圖沒抓到）"), kw["prompt"])

    def test_the_replied_messages_preview_picture_is_marked_too(self):
        self.replied = _message("https://example.com/v/1", author_id=EARLIER_AUTHOR, mid=6001,
                                embeds=[_preview("https://i.example/a.jpg")])
        self._run(_message("這在講什麼"), directed=True)
        kw = self._generate_kwargs()
        self.assertTrue(kw["replied_to_text"].endswith("[預覽：影片標題]（這張圖沒抓到）"), kw["replied_to_text"])
        self.preview_frames["https://i.example/a.jpg"] = ["THUMB"]
        self.llm.generate_reply.reset_mock()
        self._run(_message("這在講什麼"), directed=True)
        kw = self._generate_kwargs()
        self.assertEqual(["THUMB"], kw["images"])
        self.assertNotIn("沒抓到", kw["replied_to_text"])

    # ── 回覆鏈再往前的圖：有名額就收，近的優先 ──
    def _said(self, text, mid, minutes_ago, *, image=False):
        attachments = [SimpleNamespace(filename=f"{mid}.png", size=10)] if image else []
        return _message(text, author_id=EARLIER_AUTHOR, mid=mid, attachments=attachments,
                        created_at=NOW - timedelta(minutes=minutes_ago))

    def _chain(self, *older):
        """觸發那則回 older[0]，older[0] 回 older[1]，依此類推。"""
        self.replied = older[0]
        for newer, earlier in zip(older, older[1:]):
            self.chain[newer.id] = earlier

    def test_a_followup_two_replies_from_the_picture_gets_it_again(self):
        self._chain(self._said("背景那台我看不太清楚", 6001, 6),
                    self._said("阿怎麼沒有聲優本人", 6000, 9, image=True))
        self.images[6000] = ["PIC"]
        self._run(_message("那背景機體的聲優是誰"), directed=True)
        kw = self._generate_kwargs()
        self.assertEqual(["PIC"], kw["images"])
        self.assertEqual("背景那台我看不太清楚", kw["replied_to_text"], "圖的說明在圖片清單，不接在被回覆那則後面")
        line = kw["image_note"].splitlines()[1]
        self.assertTrue(line.startswith("・第 1 張：更早的一則（不在上面的聊天紀錄裡）"), line)
        self.assertIn("19:51 貼的", line, "要講圖是幾點貼的（本機時區）")
        self.assertIn("某人#", line)
        self.assertIn("沿著這串回覆往前找到的", line)
        self.assertIn("那則寫「阿怎麼沒有聲優本人」", line)

    def test_spontaneous_followups_get_the_picture_too(self):
        self._chain(self._said("背景那台我看不太清楚", 6001, 6),
                    self._said("", 6000, 9, image=True))
        self.images[6000] = ["PIC"]
        self._run(_message("我也看不到背景"))
        self.assertEqual(["PIC"], self._generate_kwargs()["images"])

    def test_the_picture_can_be_six_messages_back_but_not_seven(self):
        older = [self._said(f"第{n}則", 6000 + n, n) for n in range(1, 8)]
        older[5].attachments = [_att(6006)]
        self.images[6006] = ["SIX"]
        self._chain(*older)
        self._run(_message("所以呢"), directed=True)
        self.assertEqual(["SIX"], self._generate_kwargs()["images"])

        self.llm.generate_reply.reset_mock()
        older[5].attachments = []
        older[6].attachments = [_att(6007)]
        self.images[6007] = ["SEVEN"]
        self.looked_up.clear()
        self._run(_message("所以呢"), directed=True)
        self.assertIsNone(self._generate_kwargs()["images"])
        self.assertNotIn(6006, self.looked_up, "第 6 則就停，不再往前讀")

    def test_a_picture_from_over_an_hour_ago_is_not_brought_back(self):
        self._chain(self._said("後來呢", 6002, 5), self._said("早就換話題了", 6001, 61),
                    self._said("", 6000, 62, image=True))
        self.images[6000] = ["OLD"]
        self._run(_message("然後咧"), directed=True)
        self.assertIsNone(self._generate_kwargs()["images"])
        self.assertNotIn(6001, self.looked_up, "碰到太舊的一則就停：再往前只會更舊")

    def test_a_picture_from_within_the_hour_is_brought_back(self):
        self._chain(self._said("後來呢", 6002, 5), self._said("", 6000, 59, image=True))
        self.images[6000] = ["PIC"]
        self._run(_message("然後咧"), directed=True)
        self.assertEqual(["PIC"], self._generate_kwargs()["images"])

    def test_chain_pictures_are_taken_nearest_first_until_full(self):
        self._chain(self._said("回你", 6005, 2), self._said("第一張", 6004, 3, image=True),
                    self._said("第二張", 6003, 4, image=True), self._said("第三張", 6002, 5, image=True),
                    self._said("第四張", 6001, 6, image=True))
        for mid, name in ((6004, "P1"), (6003, "P2"), (6002, "P3"), (6001, "P4")):
            self.images[mid] = [name]
        self._run(_message("哪張"), directed=True)
        self.assertEqual(["P1", "P2", "P3"], self._generate_kwargs()["images"])
        self.assertNotIn(6002, self.looked_up, "收滿就不再往回讀")

    def test_the_chain_is_followed_even_when_the_trigger_or_the_replied_message_has_a_picture(self):
        picture = self._said("", 6000, 9, image=True)
        self.images[6000] = ["CHAIN"]
        trigger = _message("那這張呢", attachments=[_att(7001)])
        self.images[trigger.id] = ["NEW"]
        self._chain(self._said("回你", 6001, 6), picture)
        self._run(trigger, directed=True)
        self.assertEqual(["NEW", "CHAIN"], self._generate_kwargs()["images"])
        lines = self._list()
        self.assertTrue(lines[1].startswith("・第 1 張：發問的這則，"), lines[1])
        self.assertIn("沿著這串回覆往前找到的", lines[2])

        self.llm.generate_reply.reset_mock()
        self._chain(self._said("", 6001, 6, image=True), picture)
        self.images[6001] = ["REPLIED"]
        self._run(_message("那這張呢"), directed=True)
        self.assertEqual(["REPLIED", "CHAIN"], self._generate_kwargs()["images"])

    def test_an_older_picture_is_not_passed_off_as_the_one_that_failed_to_download(self):
        self._chain(self._said("回你", 6001, 6), self._said("", 6000, 9, image=True))
        self.images[6000] = ["CHAIN"]
        self._run(_message("那這張呢", attachments=[_att(7001)]), directed=True)
        kw = self._generate_kwargs()
        self.assertEqual(["CHAIN"], kw["images"])
        self.assertIn("（這張圖沒抓到）", kw["prompt"], "自己貼的那張沒抓到要講")
        self.assertTrue(self._list()[1].startswith("・第 1 張：更早的一則"), "補上的舊圖要標明是更早的一則")
        self.assertNotIn("發問的這則，", kw["image_note"])

    def test_chain_pictures_come_after_what_the_replied_message_brought(self):
        self._chain(self._said("https://x.com/a/status/1", 6001, 6), self._said("", 6000, 9, image=True))
        self.images[6000] = ["CHAIN"]
        self.media[6001] = (["（X 貼文：內容）"], ["TW"])
        self._run(_message("這篇在講啥"), directed=True)
        self.assertEqual(["TW", "CHAIN"], self._generate_kwargs()["images"])

    def test_the_chain_picture_comes_even_when_the_replied_message_has_no_text(self):
        self._chain(self._said("", 6001, 6), self._said("", 6000, 9, image=True))
        self.images[6000] = ["CHAIN"]
        self._run(_message("然後咧"), directed=True)
        kw = self._generate_kwargs()
        self.assertEqual(["CHAIN"], kw["images"])
        self.assertIsNone(kw["replied_to_text"])
        self.assertIn("沿著這串回覆往前找到的", kw["image_note"], "圖是哪來的由圖片清單講")

    # ── 追問它的話：先附它當時對著講的那一則的圖 ──
    def _it_said(self, text, mid, minutes_ago, *, about=None):
        """它的一句插話；about 是當時觸發它的那則（互動紀錄記的），給了就讀得到。"""
        said = _message(text, author_id=BOT_ID, mid=mid, created_at=NOW - timedelta(minutes=minutes_ago))
        if about is not None:
            self.said_about[mid] = str(about.id)
            self.by_id[about.id] = about
        return said

    def test_asking_about_what_it_said_brings_back_the_picture_it_was_looking_at(self):
        # 實例：它看了甲後來貼的哭臉，用回覆指向的卻是乙那句「我沒哭」（那句回的是更早的梗圖）。乙回它
        # 「你看一下圖是誰發的」：只順著回覆走會附到梗圖，它手上就不是當初看的那張
        meme = self._said("", 6000, 9, image=True)
        crying = self._said("", 6002, 6, image=True)
        self._chain(self._it_said("淚都噴到麥克風上了欸，沒哭。", 6003, 4, about=crying),
                    self._said("我沒哭", 6001, 7), meme)
        self.images[6000], self.images[6002] = ["MEME"], ["CRYING"]
        self._run(_message("你看一下圖是誰發的好嗎"), directed=True)
        kw = self._generate_kwargs()
        self.assertEqual(["CRYING", "MEME"], kw["images"], "它當時看的那張排前面")
        lines = self._list()
        self.assertTrue(lines[1].endswith("19:54 貼的（你 19:56 那句就是看了這張講的）"), lines[1])
        self.assertIn("沿著這串回覆往前找到的", lines[2])

    def test_the_picture_it_looked_at_is_taken_once_when_it_also_replied_to_it(self):
        picture = self._said("這張好笑", 6000, 6, image=True)
        self._chain(self._it_said("確實", 6001, 4, about=picture), picture)
        self.images[6000] = ["PIC"]
        self._run(_message("哪裡好笑"), directed=True)
        self.assertEqual(["PIC"], self._generate_kwargs()["images"])
        self.assertIn("那句就是看了這張講的", self._list()[1])

    def test_only_its_own_talk_is_looked_up_in_the_interaction_records(self):
        repost = _message("https://fixupx.com/a/status/1", author_id=BOT_ID, mid=6002,
                          created_at=NOW - timedelta(minutes=3))
        repost.author.bot = True                                # 它的自動轉貼不是插話
        self._chain(self._said("回你", 6003, 2), repost, self._said("更早", 6001, 5))
        self._run(_message("所以呢"), directed=True)
        self.assertEqual([], self.asked_about)

    def test_what_it_looked_at_is_skipped_when_that_message_is_gone(self):
        gone = self._said("", 6000, 6, image=True)
        self._chain(self._it_said("確實", 6001, 4, about=gone))
        self.by_id.clear()                                      # 那則已刪，讀不到
        self._run(_message("哪裡好笑"), directed=True)
        self.assertEqual([6001], self.asked_about)
        self.assertIsNone(self._generate_kwargs()["images"])

    def test_a_failed_download_of_the_chain_picture_adds_nothing(self):
        self._chain(self._said("回你", 6001, 6), self._said("", 6000, 9, image=True))
        self._run(_message("那背景呢"), directed=True)
        kw = self._generate_kwargs()
        self.assertIsNone(kw["images"])
        self.assertIsNone(kw["image_note"], "沒附到圖就沒有圖片清單")
        self.assertEqual("回你", kw["replied_to_text"])

    def test_a_replied_picture_that_could_not_be_fetched_is_marked(self):
        self.replied = self._said("", 6001, 3, image=True)
        self._run(_message("這張圖是什麼"), directed=True)
        kw = self._generate_kwargs()
        self.assertIsNone(kw["images"])
        self.assertEqual("(一張圖)（這張圖沒抓到）", kw["replied_to_text"])

    def test_the_latest_picture_that_could_not_be_fetched_is_marked(self):
        self._run(_message("看這兩張", attachments=[SimpleNamespace(filename="a.png", size=10),
                                                  SimpleNamespace(filename="b.png", size=10)]), directed=True)
        kw = self._generate_kwargs()
        self.assertIsNone(kw["images"])
        self.assertIn("看這兩張", kw["prompt"])
        self.assertIn("（有 2 張圖沒抓到）", kw["prompt"])

    def test_pictures_that_arrived_are_not_marked(self):
        self.replied = self._said("", 6001, 3, image=True)
        self.images[6001] = ["PIC"]
        self._run(_message("這張圖是什麼"), directed=True)
        kw = self._generate_kwargs()
        self.assertEqual(["PIC"], kw["images"])
        self.assertEqual("(一張圖)", kw["replied_to_text"])

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
        args, kwargs = msg.reply.await_args
        self.assertEqual(("上個版本的。",), args)
        self.assertFalse(kwargs["mention_author"])
        self.assertFalse(kwargs["allowed_mentions"].everyone or kwargs["allowed_mentions"].users, "回覆不 @ 任何人")
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
        args, kwargs = self.earlier.reply.await_args
        self.assertEqual(("我也覺得",), args)
        self.assertFalse(kwargs["mention_author"])
        self.assertFalse(kwargs["allowed_mentions"].everyone or kwargs["allowed_mentions"].users)
        msg.channel.send.assert_not_awaited()
        self.assertEqual("#1\n我也覺得", self.debug_writes[-1]["reply"])   # debug 留原樣，看得出選了哪條
        self.assertEqual(EARLIER_AUTHOR, self._state()["last_anchor_author_id"])

    def test_spontaneous_answer_can_anchor_on_the_trigger_itself(self):
        # 觸發訊息也有編號（接在脈絡最大號之後）；模型選它就 reply 它
        self.earlier = _message("前一句", author_id=EARLIER_AUTHOR, mid=6000)
        self._model_says("#2\n我也覺得")
        msg = _message()
        self._run(msg)
        args, kwargs = msg.reply.await_args
        self.assertEqual((("我也覺得",), False), (args, kwargs["mention_author"]))
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

    # ── 查詢工具、日期、長度上限 ──
    def test_without_search_tools_the_model_gets_no_tool_runner(self):
        self._run(_message())
        kw = self._generate_kwargs()
        self.assertIsNone(kw["tool_runner"])
        self.assertIsNone(kw["max_tokens"], "自發插話不設輸出上限")

    def test_search_tools_are_handed_over_with_one_round_the_ambient_nudge_and_no_plain_fallback(self):
        self.search_tools = SimpleNamespace(mode="dry_run", tools=[{"function": {"name": "web_search"}}], instructions="規則")
        self._run(_message(), directed=True)
        kw = self._generate_kwargs()
        self.assertIs(self.search_tools, kw["tool_runner"])
        self.assertEqual(1, kw["max_tool_rounds"])
        self.assertEqual(ambient_search.NUDGE, kw["tool_nudge"])
        self.assertIs(False, kw["tools_plain_fallback"])

    def test_today_is_sent_with_the_prompt(self):
        self._run(_message(), directed=True)
        self.assertRegex(self._generate_kwargs()["today"], r"^\d{4}-\d{2}-\d{2}（星期.）$")

    def test_only_directed_replies_get_the_length_cap(self):
        self._run(_message(), directed=True)
        self.assertEqual(ambient_reply._SETTINGS.directed_max_tokens, self._generate_kwargs()["max_tokens"])

    def test_a_leaked_tool_call_is_never_sent(self):
        self._model_says('<tool_call>{"name": "web_search"}</tool_call>')
        msg = _message()
        self._run(msg, directed=True)
        msg.reply.assert_not_awaited()
        msg.channel.send.assert_not_awaited()
        self.assertEqual("pass", self.debug_writes[-1]["outcome"])

    def test_an_overlong_reply_is_cut_to_one_message(self):
        for label, text in (("純文字", "好長一句。" * 500), ("暴雷跨切點", "字" * 1995 + "||暴雷暴雷暴雷暴雷||" + "字" * 50)):
            with self.subTest(label):
                self._model_says(text)
                msg = _message()
                with self.assertLogs("llm.ambient.ambient_reply", level="WARNING"):
                    self._run(msg, directed=True)
                (sent,), _kwargs = msg.reply.await_args
                self.assertLessEqual(len(sent), 2000, "切段補的暴雷標記也不能超過上限")
                self.assertTrue(sent.startswith(text[:5]))

    def test_a_reply_cut_by_the_length_cap_is_not_sent(self):
        self._model_says("半句話\n" + ambient_reply.TRUNCATED_NOTE)
        msg = _message()
        self._run(msg, directed=True)
        msg.reply.assert_not_awaited()
        msg.channel.send.assert_not_awaited()
        self.assertEqual("pass", self.debug_writes[-1]["outcome"])

    def test_people_mentioned_are_on_the_name_check_list(self):
        msg = _message(f"<@{EARLIER_AUTHOR}> 生日幾號")
        with mock.patch.object(ambient_search, "prepare", mock.AsyncMock(return_value=None)) as prepare:
            asyncio.run(ambient_reply._prepare_search_tools(msg, "某人 生日幾號", [SPEAKER], "t"))
        names = prepare.await_args.kwargs["names"]          # functools.partial(name_parts_for, guild, people)
        self.assertEqual([SPEAKER, str(EARLIER_AUTHOR)], names.args[1], "近期發言的人加上被 @ 的人")

    def test_mentioned_people_are_looked_up_even_though_the_text_names_them(self):
        msg = _message(f"<@{EARLIER_AUTHOR}> <@{BOT_ID}> 你覺得呢")
        msg.mentions = [SimpleNamespace(id=EARLIER_AUTHOR, display_name="克羅", name="克羅"), BOT_USER]
        self._run(msg, directed=True)
        self.assertEqual([str(EARLIER_AUTHOR)], self.persona_builder.await_args.args[3], "被 @ 的人（去掉 bot）要傳進人物卡檢索")


class MentionLookupTests(unittest.TestCase):
    """被 @ 的人：人物卡檢索收到的是 id 清單，回憶對象也認得 @。"""

    def setUp(self):
        ambient_reply._PERSONA_CACHE.clear()
        self.addCleanup(ambient_reply._PERSONA_CACHE.clear)

    def test_persona_retrieval_is_told_who_was_mentioned(self):
        msg = _message(f"<@{EARLIER_AUTHOR}> 你覺得呢")
        seen = {}

        def fake_retrieve(question, guild_id, requester, participants, logger, top_k, **kwargs):
            seen.update(kwargs)
            return [], {}

        with mock.patch("llm.retrievers.context_retriever.retrieve_rag_context_sync", fake_retrieve), \
                mock.patch("llm.persona.member_names.member_names_from_guild", return_value={}), \
                mock.patch("llm.persona.member_names.name_map_lines", return_value=[]):
            asyncio.run(ambient_reply._build_persona_context(msg, "某人 你覺得呢", [SPEAKER], [str(EARLIER_AUTHOR)]))
        self.assertEqual([str(EARLIER_AUTHOR)], seen["mentioned_user_ids"])

    def test_recall_target_comes_from_the_original_message_not_the_renamed_text(self):
        msg = _message(f"<@{EARLIER_AUTHOR}> 上次說的那個")
        target = asyncio.run(ambient_reply._resolve_callback_target(msg, "某人#7489 上次說的那個"))
        self.assertEqual(str(EARLIER_AUTHOR), target)

    def test_the_bot_itself_is_not_a_mention(self):
        msg = _message(f"<@{BOT_ID}> 在嗎")
        self.assertEqual([], ambient_reply._mentioned_user_ids(msg))


class _Fetched(discord.Message):
    """讓 isinstance(…, discord.Message) 成立的假訊息（不呼叫 discord 的建構子）。"""

    def __init__(self, mid, ref=None, resolved=None):  # noqa: D107
        self.id = mid
        self.reference = SimpleNamespace(message_id=ref, resolved=resolved) if ref else None
        self.channel = SimpleNamespace(fetch_message=mock.AsyncMock(side_effect=lambda i: _Fetched(i)))


class ReferencedMessageTests(unittest.TestCase):
    """讀「這則回了哪一則」：Discord 一起送來的那份、bot 的訊息快取都沒有，才問 API。"""

    def _lookup(self, msg, *cached):
        return asyncio.run(ambient_reply._referenced_message(SimpleNamespace(cached_messages=list(cached)), msg))

    def test_the_copy_sent_with_the_message_is_used_first(self):
        earlier = _Fetched(1)
        msg = _Fetched(2, ref=1, resolved=earlier)
        self.assertIs(earlier, self._lookup(msg, _Fetched(1)))
        msg.channel.fetch_message.assert_not_awaited()

    def test_the_bot_cache_is_used_before_the_api(self):
        cached = _Fetched(1)
        msg = _Fetched(2, ref=1)
        self.assertIs(cached, self._lookup(msg, _Fetched(5), cached))
        msg.channel.fetch_message.assert_not_awaited()

    def test_the_api_is_asked_last_and_a_failure_is_none(self):
        msg = _Fetched(2, ref=1)
        self.assertEqual(1, self._lookup(msg).id)
        msg.channel.fetch_message.side_effect = discord.NotFound(SimpleNamespace(status=404, reason="x"), "gone")
        self.assertIsNone(self._lookup(msg))

    def test_a_message_that_replies_to_nothing_is_none(self):
        msg = _Fetched(2)
        self.assertIsNone(self._lookup(msg))
        msg.channel.fetch_message.assert_not_awaited()


class TriggerOfItsReplyTests(unittest.TestCase):
    """互動紀錄：它的某句話當時是被哪一則觸發的。查不到、資料庫出錯都回 None（照舊沿回覆鏈找圖）。"""

    def _conn(self, row):
        self.cur = mock.MagicMock()
        self.cur.__enter__.return_value = self.cur
        self.cur.fetchone.return_value = row
        conn = mock.MagicMock()
        conn.__enter__.return_value = conn
        conn.cursor.return_value = self.cur
        return conn

    def test_the_trigger_is_looked_up_by_the_id_of_what_it_said(self):
        with mock.patch.object(ai_interactions_store, "_get_conn", return_value=self._conn(("6002",))):
            self.assertEqual("6002", ai_interactions_store.trigger_message_id(6003))
        sql, params = self.cur.execute.call_args.args
        self.assertIn("WHERE reply_message_id = %s", sql)
        self.assertEqual(("6003",), params, "資料庫裡的 id 是字串")

    def test_not_one_of_its_interjections_is_none(self):
        for row in (None, (None,)):
            with mock.patch.object(ai_interactions_store, "_get_conn", return_value=self._conn(row)):
                self.assertIsNone(ai_interactions_store.trigger_message_id("6003"))

    def test_a_database_error_is_none_and_logged(self):
        with mock.patch.object(ai_interactions_store, "_get_conn", side_effect=psycopg2.OperationalError("連不上")), \
                self.assertLogs(ai_interactions_store.logger, "WARNING"):
            self.assertIsNone(ai_interactions_store.trigger_message_id("6003"))


if __name__ == "__main__":
    unittest.main()
