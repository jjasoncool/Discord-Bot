"""「自然插話」重構的單元測試（2026-08-09）。

覆蓋的新行為：
  1. chat_line 每行編號 + thread_map（模型要靠編號表態「我在接哪一條線」）
  2. `_parse_line_choice`：從模型輸出剝出 `#N` 錨點
  3. `_passes_content_gate`：內容閘改看整段 burst 的單則判定
  4. ambient_hooks 結構鉤子：懸空問句／獨白／冷場／對話正熱／聊完停頓
     （**人數不當判準**——那是語意問題，留給模型的第一關）
  5. 靜默期依對話節奏切換：慢節奏等人講完、熱聊只等一下就開講
  6. L4-b 接續（armed 用完即熄、window、chain 上限）

全部 hermetic：不碰 DB、不碰模型、不連網（k-NN 特徵在測試中被替換掉）。

執行：
    cd src && python -m unittest test.test_ambient_natural -v
"""

import asyncio
import os
import sys
import time
import unittest
from collections import deque
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from llm import ambient_hooks, ambient_reply
from llm.ambient_hooks import _structural_features, _text_features
from llm.ambient_reply import _parse_line_choice, _passes_content_gate
from llm import chat_line
from llm.chat_line import (
    fetch_recent_lines,
    resolve_user_mentions,
    semantic_message_text,
)

TZ8 = timezone(timedelta(hours=8))
BASE = datetime(2026, 8, 9, 12, 0, tzinfo=timezone.utc)


def _msg(content="", *, mid=1, author_name="老哥", author_id=123456789012341234,
         bot=False, created=None, ref_id=None, attachments=()):
    """造一個夠用的假 discord.Message（只放被測程式碼會碰到的欄位）。"""
    author = SimpleNamespace(display_name=author_name, name=author_name, id=author_id, bot=bot)
    reference = SimpleNamespace(message_id=ref_id, resolved=None) if ref_id else None
    return SimpleNamespace(
        content=content, author=author, created_at=created or BASE, stickers=[],
        id=mid, reference=reference,
        attachments=[SimpleNamespace(filename=f, size=1000) for f in attachments],
    )


class _FakeChannel:
    """假頻道：history() 回 async iterator（依 discord 慣例 newest-first 餵入）。"""

    def __init__(self, msgs_newest_first):
        self._msgs = msgs_newest_first

    def history(self, **kwargs):
        msgs = self._msgs[: kwargs.get("limit")]

        async def _gen():
            for m in msgs:
                yield m

        return _gen()


def _fetch(msgs_oldest_first, thread_map=None):
    """把「舊→新」的訊息餵進 fetch_recent_lines（內部吃 newest-first）。"""
    ch = _FakeChannel(list(reversed(msgs_oldest_first)))
    return asyncio.run(
        fetch_recent_lines(
            ch, tz=TZ8, limit=20, thread_replies=True, thread_map=thread_map
        )
    )


class LineNumberingTests(unittest.TestCase):
    """每一行都要有編號——舊版只編「被回覆過」的，多數人不按 reply → 大半行無錨可指。"""

    def test_every_line_gets_sequential_number(self):
        msgs = [_msg("第一句", mid=1), _msg("第二句", mid=2), _msg("第三句", mid=3)]
        lines, _ = _fetch(msgs)
        self.assertEqual(len(lines), 3)
        for i, line in enumerate(lines, start=1):
            self.assertTrue(line.startswith(f"#{i} "), f"第 {i} 行沒有編號：{line}")

    def test_thread_map_maps_number_to_message(self):
        msgs = [_msg("A", mid=11), _msg("B", mid=22), _msg("C", mid=33)]
        tmap = {}
        _fetch(msgs, thread_map=tmap)
        self.assertEqual({1: 11, 2: 22, 3: 33}, {no: m.id for no, m in tmap.items()})

    def test_reply_marker_points_at_line_number(self):
        # 第 3 則回覆第 1 則 → 行尾應標 ↩#1
        msgs = [_msg("原句", mid=1), _msg("插話", mid=2), _msg("回你", mid=3, ref_id=1)]
        lines, _ = _fetch(msgs)
        self.assertTrue(lines[2].endswith(" ↩#1"), lines[2])

    def test_reply_to_outside_window_marked_earlier(self):
        msgs = [_msg("只有這則", mid=5, ref_id=999)]
        lines, _ = _fetch(msgs)
        self.assertTrue(lines[0].endswith(" ↩(較早)"), lines[0])

    def test_empty_message_skipped_and_does_not_consume_number(self):
        # 中間那則沒文字也沒人回覆它 → 整則跳過，編號不留洞
        msgs = [_msg("有內容", mid=1), _msg("", mid=2), _msg("也有內容", mid=3)]
        lines, _ = _fetch(msgs)
        self.assertEqual(2, len(lines))
        self.assertTrue(lines[0].startswith("#1 "))
        self.assertTrue(lines[1].startswith("#2 "))

    def test_replied_empty_message_becomes_a_line(self):
        # 純圖訊息被回覆 → 要成行顯示 (圖)，否則 ↩ 指不到
        msgs = [
            _msg("", mid=1, attachments=("cat.png",)),
            _msg("好可愛", mid=2, ref_id=1),
        ]
        lines, _ = _fetch(msgs)
        self.assertEqual(2, len(lines))
        self.assertIn("(圖)", lines[0])
        self.assertTrue(lines[1].endswith(" ↩#1"), lines[1])

    def test_self_marker_still_applied(self):
        # 既有行為不能退化：bot 自己的行仍標「(你自己)」
        msgs = [_msg("我說的", mid=1, author_id=777, bot=True)]
        ch = _FakeChannel(list(reversed(msgs)))
        lines, _ = asyncio.run(
            fetch_recent_lines(ch, tz=TZ8, limit=20, thread_replies=True, self_id=777)
        )
        self.assertIn("(你自己)", lines[0])


class MentionResolutionTests(unittest.TestCase):
    """裸 `<@id>` → `顯示名#XXXX`。對照靠錨點，名字查不到也要能對上。"""

    @staticmethod
    def _msg_with(content, *, mentions=(), guild_members=()):
        m = _msg(content)
        m.mentions = list(mentions)
        m.guild = SimpleNamespace(
            get_member=lambda uid, _d={u.id: u for u in guild_members}: _d.get(uid)
        )
        return m

    @staticmethod
    def _user(uid, name):
        return SimpleNamespace(id=uid, display_name=name, name=name, bot=False)

    def test_resolves_from_msg_mentions(self):
        u = self._user(436506192047636490, "克羅")
        out = resolve_user_mentions(
            "那是 <@436506192047636490>", self._msg_with("x", mentions=[u])
        )
        self.assertEqual("那是 克羅#6490", out)

    def test_falls_back_to_guild_cache(self):
        u = self._user(436506192047636490, "克羅")
        out = resolve_user_mentions(
            "<@436506192047636490> 你看", self._msg_with("x", guild_members=[u])
        )
        self.assertEqual("克羅#6490 你看", out)

    def test_unknown_user_still_keeps_the_anchor(self):
        # 名字查不到也必須留下 #XXXX——那才是模型對照同一個人的依據
        out = resolve_user_mentions("問問 <@436506192047636490>", self._msg_with("x"))
        self.assertEqual("問問 某人#6490", out)

    def test_nickname_style_mention(self):
        u = self._user(559683594360979464, "海苔")
        out = resolve_user_mentions("<@!559683594360979464>", self._msg_with("x", mentions=[u]))
        self.assertEqual("海苔#9464", out)

    def test_multiple_mentions_in_one_line(self):
        a = self._user(111122223333444455, "阿明")
        out = resolve_user_mentions(
            "<@111122223333444455> 跟 <@999988887777666655> 都在",
            self._msg_with("x", mentions=[a]),
        )
        self.assertEqual("阿明#4455 跟 某人#6655 都在", out)

    def test_text_without_mention_is_untouched(self):
        text = "今天天氣不錯 <:emoji:123> 沒有 at"
        self.assertEqual(text, resolve_user_mentions(text, self._msg_with("x")))

    def test_pipeline_applies_it(self):
        # semantic_message_text 這條共用管線要真的套用（chat_history/日記/askai 一起受益）
        u = self._user(436506192047636490, "克羅")
        m = self._msg_with("那是 <@436506192047636490>", mentions=[u])
        m.content = "那是 <@436506192047636490>"
        self.assertEqual("那是 克羅#6490", semantic_message_text(m))


class AnchorCollisionTests(unittest.TestCase):
    """兩個人的 user_id 後四碼相同 → #XXXX 指向兩人，必須出警報而不是無聲認錯人。"""

    def setUp(self):
        chat_line._WARNED_ANCHOR_COLLISIONS.clear()

    def test_collision_warns(self):
        msgs = [_msg("a", author_id=111111111111116490),
                _msg("b", author_id=999999999999996490)]
        with self.assertLogs("discord_bot", level="WARNING") as cm:
            chat_line._check_anchor_collision(msgs)
        self.assertIn("6490", "".join(cm.output))

    def test_same_person_twice_is_not_a_collision(self):
        msgs = [_msg("a", author_id=111111111111116490),
                _msg("b", author_id=111111111111116490)]
        chat_line._check_anchor_collision(msgs)   # 不該拋、不該警告
        self.assertEqual(set(), chat_line._WARNED_ANCHOR_COLLISIONS)

    def test_warns_only_once_per_pair(self):
        msgs = [_msg("a", author_id=111111111111116490),
                _msg("b", author_id=999999999999996490)]
        with self.assertLogs("discord_bot", level="WARNING"):
            chat_line._check_anchor_collision(msgs)
        self.assertEqual(1, len(chat_line._WARNED_ANCHOR_COLLISIONS))
        chat_line._check_anchor_collision(msgs)   # 第二次不再洗 log
        self.assertEqual(1, len(chat_line._WARNED_ANCHOR_COLLISIONS))


class ParseLineChoiceTests(unittest.TestCase):
    """模型第一行宣告接哪一則 → 剝成 (編號, 內容)。"""

    def test_number_on_own_line(self):
        self.assertEqual((12, "這王判定看心情吧"), _parse_line_choice("#12\n這王判定看心情吧"))

    def test_number_same_line(self):
        self.assertEqual((7, "淡淡接一句"), _parse_line_choice("#7 淡淡接一句"))

    def test_number_only(self):
        self.assertEqual((3, ""), _parse_line_choice("#3"))

    def test_pass_sentinel_untouched(self):
        self.assertEqual((None, "[PASS]"), _parse_line_choice("[PASS]"))

    def test_missing_number_keeps_full_text(self):
        # 模型忘了給編號 → 不丟棄整則，退回裸送
        self.assertEqual((None, "忘記編號的回覆"), _parse_line_choice("忘記編號的回覆"))

    def test_hash_inside_text_not_treated_as_choice(self):
        self.assertEqual((None, "這款遊戲 #1 好玩"), _parse_line_choice("這款遊戲 #1 好玩"))


class ContentGateTests(unittest.TestCase):
    """單則的「有沒有可聊的內容」；burst 版是對整段做 any()。"""

    def test_normal_text_passes(self):
        self.assertTrue(_passes_content_gate(_msg("今天這場打得有夠慘")))

    def test_command_rejected(self):
        self.assertFalse(_passes_content_gate(_msg("!play 某首歌")))
        self.assertFalse(_passes_content_gate(_msg("/askai 幫我查")))

    def test_link_only_rejected(self):
        self.assertFalse(_passes_content_gate(_msg("https://example.com/a")))

    def test_too_short_rejected(self):
        self.assertFalse(_passes_content_gate(_msg("哦")))

    def test_image_passes_even_without_text(self):
        self.assertTrue(_passes_content_gate(_msg("", attachments=("shot.png",))))

    def test_burst_any_semantics(self):
        # 整段裡只要有一則有料就該放行——收尾剛好是貼圖不該把整段刷掉
        burst = [_msg("這王判定根本看心情"), _msg("哦"), _msg("", attachments=())]
        self.assertTrue(any(_passes_content_gate(m) for m in burst))


class StructuralHookTests(unittest.TestCase):
    """結構鉤子只看 metadata，不理解內容。"""

    @staticmethod
    def _at(sec):
        return BASE + timedelta(seconds=sec)

    def _now(self, sec):
        return self._at(sec).timestamp()

    def test_participant_count_is_never_a_gate(self):
        # 迴歸：曾有一條「兩人 + 間隔短 → 直接否決」的負鉤子，實測小頻道 12 分鐘內 6/7 次判定
        # 全被擋、幾乎全時間靜音。人數不是判準——prompt 第一關的判準是「話題封不封閉」，那是
        # 語意問題，結構規則模仿不來。這裡驗證：不管幾個人、多密集，鉤子都不否決。
        for label, authors, gap in (
            ("兩人密集", (1, 2), 10),
            ("兩人慢聊", (1, 2), 35),
            ("三人", (1, 2, 3), 10),
        ):
            with self.subTest(label):
                msgs = [
                    _msg(f"{label}{i}", mid=i, author_id=authors[i % len(authors)],
                         created=self._at(i * gap))
                    for i in range(6)
                ]
                _feats, veto = _structural_features(msgs, self._now(6 * gap + 5))
                self.assertIsNone(veto, f"{label} 不該被否決")

    def test_dangling_question(self):
        # 有人問了、沒人回、已過 30 秒 → 最強的正鉤子
        msgs = [
            _msg("大家在幹嘛", mid=1, author_id=1, created=self._at(0)),
            _msg("這副本要幾人才能打啊？", mid=2, author_id=2, created=self._at(10)),
        ]
        feats, veto = _structural_features(msgs, self._now(120))
        self.assertIsNone(veto)
        self.assertEqual(1.0, feats["dangling_question"])

    def test_answered_question_is_not_dangling(self):
        msgs = [
            _msg("這副本要幾人？", mid=1, author_id=1, created=self._at(0)),
            _msg("三人就夠了", mid=2, author_id=2, created=self._at(20)),
        ]
        feats, _veto = _structural_features(msgs, self._now(120))
        self.assertEqual(0.0, feats["dangling_question"])

    def test_fresh_question_not_yet_dangling(self):
        # 才剛問 2 秒（短於靜默期）→ 還不算懸空；等多久由 quiet_seconds 決定
        msgs = [_msg("有人知道嗎？", mid=1, author_id=1, created=self._at(0))]
        feats, _veto = _structural_features(msgs, self._now(2))
        self.assertEqual(0.0, feats["dangling_question"])

    def test_time_gates_track_quiet_seconds(self):
        # 迴歸：這兩個門檻曾寫死 30s/60s，而靜默期只等 ~15s 就評估 → 熱聊後停頓永遠不命中。
        # 門檻必須跟著 quiet_seconds 走，否則鉤子接在 debounce 後面時形同虛設。
        msgs = [
            _msg(f"熱聊{i}？", mid=i, author_id=(i % 3) + 1, created=self._at(i * 10))
            for i in range(1, 8)
        ]
        now = self._now(7 * 10 + 20)  # 最後一則後 20 秒：大於預設 quiet(15)、小於舊的 60
        feats, _veto = _structural_features(msgs, now)
        self.assertEqual(1.0, feats["lull_after_burst"])

        orig = ambient_hooks._SETTINGS
        try:  # 靜默期拉長 → 同一個時間點就還不算「停下來」
            ambient_hooks._SETTINGS = orig.model_copy(update={"quiet_seconds": 120.0})
            feats2, _v2 = _structural_features(msgs, now)
            self.assertEqual(0.0, feats2["lull_after_burst"])
        finally:
            ambient_hooks._SETTINGS = orig

    def test_monologue(self):
        msgs = [
            _msg("我剛剛試了一下", mid=1, author_id=9, created=self._at(0)),
            _msg("結果還是不行", mid=2, author_id=9, created=self._at(10)),
            _msg("這什麼鬼設計", mid=3, author_id=9, created=self._at(20)),
        ]
        feats, _veto = _structural_features(msgs, self._now(30))
        self.assertEqual(1.0, feats["monologue"])

    def test_long_silence_then_one_message_is_not_a_hook(self):
        # 迴歸：曾有 cold_start＝「冷場 10 分鐘後有人開口就接」，語意上正是「沒人聊天也硬回」。
        # 死寂之後冒一句，不該構成任何開口理由——除非那句本身有訊號（問句/叫名字/徵詢）。
        msgs = [
            _msg("昨天的事", mid=1, author_id=1, created=self._at(0)),
            _msg("欸話說回來", mid=2, author_id=2, created=self._at(1200)),  # 隔 20 分鐘
        ]
        feats, veto = _structural_features(msgs, self._now(1210))
        self.assertIsNone(veto)
        self.assertEqual(0.0, sum(feats.values()), f"不該有任何鉤子命中：{feats}")

    def test_active_chat_while_conversation_is_hot(self):
        # 快節奏熱聊也要能參與：其他鉤子全是「找空檔」導向，熱聊時一個都不命中 →
        # 加上 debounce 在熱聊時等不到靜默，只能靠 max_wait 兜底，會變成必然靜音。
        msgs = [
            _msg(f"熱聊{i}", mid=i, author_id=(i % 3) + 1, created=self._at(i * 15))
            for i in range(1, 9)
        ]
        feats, veto = _structural_features(msgs, self._now(8 * 15 + 3))  # 才停 3 秒＝仍在熱聊
        self.assertIsNone(veto)
        self.assertEqual(1.0, feats["active_chat"])
        self.assertEqual(0.0, feats["lull_after_burst"], "才停 3 秒不該算停頓")

    def test_sparse_chat_is_not_active(self):
        # 零星對話（每 2 分鐘一則）不算熱 → 沒有這條鉤子，交給其他訊號決定
        msgs = [
            _msg(f"零星{i}", mid=i, author_id=(i % 3) + 1, created=self._at(i * 120))
            for i in range(1, 9)
        ]
        feats, _veto = _structural_features(msgs, self._now(8 * 120 + 30))
        self.assertEqual(0.0, feats["active_chat"])

    def test_lull_after_burst(self):
        # 近 10 則擠在 2 分鐘內（熱），但最後一則已過 90 秒（停）→ 話題告一段落
        msgs = [
            _msg(f"熱聊{i}", mid=i, author_id=(i % 3) + 1, created=self._at(i * 12))
            for i in range(1, 11)
        ]
        feats, _veto = _structural_features(msgs, self._now(10 * 12 + 90))
        self.assertEqual(1.0, feats["lull_after_burst"])

    def test_empty_input_vetoed(self):
        _feats, veto = _structural_features([], self._now(0))
        self.assertEqual("no_messages", veto)


class SituationSignalTests(unittest.TestCase):
    """鉤子量到的事實 → 給模型看的中性描述（只陳述、不下結論、不含分數）。"""

    @staticmethod
    def _at(sec):
        return BASE + timedelta(seconds=sec)

    def _now(self, sec):
        return self._at(sec).timestamp()

    def _obs(self, msgs, now_sec):
        obs = {}
        _structural_features(msgs, self._now(now_sec), obs)
        return obs

    def test_dangling_question_signal(self):
        msgs = [_msg("這副本要幾人？", mid=1, author_id=1234, author_name="米拉",
                     created=self._at(0))]
        lines = ambient_hooks.describe_signals(self._obs(msgs, 300))
        self.assertEqual(1, len(lines))
        self.assertIn("米拉", lines[0])
        self.assertIn("5 分鐘前", lines[0])
        self.assertIn("沒有人回應", lines[0])

    def test_monologue_signal_counts_the_streak(self):
        msgs = [
            _msg(f"自言自語{i}", mid=i, author_id=777, author_name="老哥",
                 created=self._at(i * 30))
            for i in range(4)
        ]
        lines = ambient_hooks.describe_signals(self._obs(msgs, 3 * 30 + 20))
        self.assertTrue(any("連續講了 4 則" in ln for ln in lines), lines)

    def test_two_person_is_stated_as_fact_not_a_veto(self):
        # 人數不再否決，但「誰跟誰在來回」這個事實仍量測下來交給模型判斷
        msgs = [
            _msg(f"來回{i}", mid=i, author_id=(i % 2) + 1,
                 author_name=("阿明" if i % 2 else "阿華"), created=self._at(i * 10))
            for i in range(6)
        ]
        obs = self._obs(msgs, 6 * 10 + 5)
        lines = ambient_hooks.describe_signals(obs)
        self.assertTrue(any("兩個人在來回" in ln for ln in lines), lines)

    def test_signals_never_leak_scores_or_advice(self):
        # 契約：只陳述事實。出現分數或「建議你…」會讓模型變橡皮圖章
        msgs = [_msg("有人在嗎？", mid=1, author_id=1, created=self._at(0))]
        for ln in ambient_hooks.describe_signals(self._obs(msgs, 300)):
            for banned in ("建議", "應該", "p=", "score", "分數", "權重"):
                self.assertNotIn(banned, ln, f"訊號不該含「{banned}」：{ln}")

    def test_no_observation_means_no_signal(self):
        lines = ambient_hooks.describe_signals({})
        self.assertEqual([], lines)


class TextHookTests(unittest.TestCase):
    def test_named_without_mention(self):
        self.assertEqual(1.0, _text_features([_msg("琇紫你覺得呢")])["named"])

    def test_solicit(self):
        self.assertEqual(1.0, _text_features([_msg("有沒有人知道這隻怎麼打")])["solicit"])

    def test_plain_chat_hits_nothing(self):
        feats = _text_features([_msg("今天天氣不錯")])
        self.assertEqual(0.0, feats["named"])
        self.assertEqual(0.0, feats["solicit"])


class EvaluateTests(unittest.TestCase):
    """整體計分：否決 → 不過；強鉤子 → 過；ε-greedy → 分數沒過也可能放行。"""

    def setUp(self):
        # k-NN 是唯一會碰 DB/embedding 的部分 → 測試中換成沒有訊號的樁
        async def _no_knn(_situation):
            return (0.0, 0)

        self._orig_knn = ambient_hooks._knn_feature
        self._orig_settings = ambient_hooks._SETTINGS
        self._orig_struct = ambient_hooks._structural_features
        ambient_hooks._knn_feature = _no_knn

    def tearDown(self):
        ambient_hooks._knn_feature = self._orig_knn
        ambient_hooks._SETTINGS = self._orig_settings
        ambient_hooks._structural_features = self._orig_struct

    @staticmethod
    def _override(**kw):
        """設定物件是 frozen（pydantic）→ 用 model_copy 換一個新的進去，tearDown 還原。"""
        ambient_hooks._SETTINGS = ambient_hooks._SETTINGS.model_copy(update=kw)

    @staticmethod
    def _run(msgs, **kw):
        return asyncio.run(ambient_hooks.evaluate(msgs, **kw))

    def test_veto_blocks_even_explore(self):
        # veto 優先於一切——連 ε-greedy 強制放行都擋得住（explore_rate 開到 1.0 也一樣）
        self._override(hook_explore_rate=1.0)
        decision = self._run([])          # 沒有任何可判讀的訊息
        self.assertFalse(decision.passed)
        self.assertFalse(decision.explore)
        self.assertEqual("no_messages", decision.veto)

    def test_strong_hook_passes(self):
        # 叫名字 + 徵詢 + 獨白 → 分數應該明顯過門檻
        base = datetime.now(timezone.utc) - timedelta(seconds=120)
        msgs = [
            _msg("琇紫在嗎", mid=1, author_id=5, created=base),
            _msg("有沒有人知道這個怎麼弄", mid=2, author_id=5, created=base + timedelta(seconds=10)),
            _msg("我卡在這一步好久了", mid=3, author_id=5, created=base + timedelta(seconds=20)),
        ]
        decision = self._run(msgs)
        self.assertTrue(decision.passed)
        self.assertFalse(decision.explore)

    def test_explore_requires_the_channel_to_have_people(self):
        # 迴歸：探索原本不管有沒有人在，於是死寂的頻道也會被硬放行——實測「無任何特徵卻被
        # 探索放行」正是「沒人聊天也硬回」的來源。沒人在時探索也學不到東西（標籤必然沒人接）。
        self._override(hook_explore_rate=1.0)   # 探索開到必中，仍不該放行
        base = datetime.now(timezone.utc)
        msgs = [   # 5 則橫跨 5 小時＝零星，不算有人在
            _msg("零星", mid=i, author_id=i, created=base - timedelta(hours=5 - i))
            for i in range(5)
        ]
        decision = self._run(msgs)
        self.assertFalse(decision.passed)
        self.assertFalse(decision.explore)

    def test_explore_forces_pass(self):
        # 平淡到不該開口（沒有任何鉤子命中），但頻道有人在 → explore_rate=1.0 強制放行
        # 6 則、每 60 秒一則：不夠熱（active_chat 要 3 分鐘內），最後一則才剛講完（不算停頓），
        # 但落在 15 分鐘的活躍窗內 → 算「有人在」。
        base = datetime.now(timezone.utc)
        msgs = [
            _msg(f"閒聊{i}", mid=i, author_id=(i % 3) + 1,
                 created=base - timedelta(seconds=(5 - i) * 60 + 2))
            for i in range(6)
        ]
        self._override(hook_explore_rate=1.0)
        decision = self._run(msgs)
        self.assertTrue(decision.passed)
        self.assertTrue(decision.explore)

    def test_hook_failure_falls_open(self):
        # 鉤子壞掉不該讓整個功能啞掉 → 放行，交給模型的 [PASS] 把關
        def _boom(*_a, **_kw):
            raise RuntimeError("鉤子內部炸了")

        ambient_hooks._structural_features = _boom
        decision = self._run([_msg("隨便一句")])
        self.assertTrue(decision.passed)


class QuietPeriodTests(unittest.TestCase):
    """靜默期：距最後一則夠久 **且** 沒人在打字才放行。用很短的秒數跑，避免拖慢 gate。"""

    def setUp(self):
        self._orig = ambient_reply._SETTINGS
        ambient_reply._SETTINGS = ambient_reply._SETTINGS.model_copy(
            update={"quiet_seconds": 0.1, "typing_grace_seconds": 0.2,
                    "quiet_max_wait_seconds": 5.0, "quiet_directed_seconds": 0.0}
        )

    def tearDown(self):
        ambient_reply._SETTINGS = self._orig

    @staticmethod
    def _elapsed(state):
        started = time.monotonic()
        asyncio.run(ambient_reply._wait_for_quiet(state))
        return time.monotonic() - started

    def test_returns_immediately_when_already_quiet(self):
        state = {"directed": None, "last_msg_mono": time.monotonic() - 5, "typing_at": {}}
        self.assertLess(self._elapsed(state), 0.3)

    def test_waits_while_someone_is_typing(self):
        # 距最後一則已久（時間條件早就滿足），但有人正在打字 → 仍要等
        state = {
            "directed": None,
            "last_msg_mono": time.monotonic() - 5,
            "typing_at": {42: time.monotonic()},
        }
        self.assertGreater(self._elapsed(state), 0.3)

    def test_directed_does_not_wait(self):
        # 被 @／接續：對方在跟它講話，不等
        state = {"directed": object(), "last_msg_mono": time.monotonic(), "typing_at": {}}
        self.assertLess(self._elapsed(state), 0.3)

    def test_hot_conversation_uses_short_wait_and_ignores_typing(self):
        # 熱聊：只等 hot_quiet_seconds，且忽略 typing——熱聊時永遠等不到靜默，用慢節奏那套
        # 只會被 max_wait 硬拖，而且熱聊插話本來就不需要空檔。
        ambient_reply._SETTINGS = ambient_reply._SETTINGS.model_copy(
            update={"quiet_seconds": 30.0, "hot_quiet_seconds": 0.1,
                    "hot_min_messages": 5, "hot_window_seconds": 120.0}
        )
        now = time.monotonic()
        state = {
            "directed": None,
            "last_msg_mono": now - 1,                       # 才過 1 秒，遠不到 quiet(30)
            "typing_at": {42: now},                         # 而且有人正在打字
            "msg_times": deque([now - i * 5 for i in range(5, 0, -1)]),  # 5 則在 25 秒內＝熱
        }
        self.assertLess(self._elapsed(state), 0.6)

    def test_slow_conversation_still_waits_for_typing(self):
        # 慢節奏：維持「等人講完」——有人在打字就繼續等，不能因為熱聊通道而漏掉
        now = time.monotonic()
        state = {
            "directed": None,
            "last_msg_mono": now - 5,
            "typing_at": {42: now},
            "msg_times": deque([now - i * 60 for i in range(5, 0, -1)]),  # 5 則橫跨 5 分鐘＝不熱
        }
        self.assertGreater(self._elapsed(state), 0.3)

    def test_max_wait_caps_the_wait(self):
        # 靜默條件永遠達不到（quiet 拉到 999）→ 總上限兜底，不會無限等
        ambient_reply._SETTINGS = ambient_reply._SETTINGS.model_copy(
            update={"quiet_seconds": 999.0, "quiet_max_wait_seconds": 0.2}
        )
        state = {"directed": None, "last_msg_mono": time.monotonic(), "typing_at": {}}
        self.assertLess(self._elapsed(state), 2.0)


class FollowupTests(unittest.TestCase):
    """L4-b：只認「它剛才回的那個人、在 window 內、發言後的第一則」，且有 chain 上限。"""

    TALKED_TO = 5150  # 它剛才回的那個人

    @staticmethod
    def _state(**kw):
        base = {"followup_armed": True, "last_reply_mono": time.monotonic(),
                "followup_chain": 0, "last_anchor_author_id": FollowupTests.TALKED_TO}
        base.update(kw)
        return base

    def _from(self, author_id):
        return _msg("接一句", author_id=author_id)

    def test_the_person_it_replied_to_counts(self):
        self.assertTrue(
            ambient_reply._is_followup_to_bot(self._state(), self._from(self.TALKED_TO))
        )

    def test_someone_else_talking_is_not_a_followup(self):
        # 迴歸：這是「幾乎每個人的話都在回」的成因——它插完話、群裡繼續聊自己的，
        # 第一則訊息就被當成「有人在接我」。實測 15 次插話裡 9 次是這樣來的。
        self.assertFalse(
            ambient_reply._is_followup_to_bot(self._state(), self._from(99999))
        )

    def test_armed_is_consumed_after_one_shot(self):
        state = self._state()
        self.assertTrue(ambient_reply._is_followup_to_bot(state, self._from(self.TALKED_TO)))
        self.assertFalse(ambient_reply._is_followup_to_bot(state, self._from(self.TALKED_TO)))

    def test_outside_window_rejected(self):
        stale = self._state(last_reply_mono=time.monotonic() - 10_000)
        self.assertFalse(ambient_reply._is_followup_to_bot(stale, self._from(self.TALKED_TO)))

    def test_chain_limit_stops_infinite_loop(self):
        maxed = self._state(followup_chain=ambient_reply._SETTINGS.followup_max_chain)
        self.assertFalse(ambient_reply._is_followup_to_bot(maxed, self._from(self.TALKED_TO)))

    def test_never_replied_yet(self):
        self.assertFalse(
            ambient_reply._is_followup_to_bot(
                self._state(last_reply_mono=0.0), self._from(self.TALKED_TO)
            )
        )

    def test_no_anchor_recorded(self):
        # 沒記到「剛才在跟誰講話」→ 不猜，直接不算接續
        self.assertFalse(
            ambient_reply._is_followup_to_bot(
                self._state(last_anchor_author_id=None), self._from(self.TALKED_TO)
            )
        )

    def test_disabled_flag_short_circuits(self):
        orig = ambient_reply._SETTINGS
        try:
            ambient_reply._SETTINGS = orig.model_copy(update={"followup_enabled": False})
            state = self._state()
            self.assertFalse(
                ambient_reply._is_followup_to_bot(state, self._from(self.TALKED_TO))
            )
            # 關閉時不該偷偷消耗 armed（開回來還要能用）
            self.assertTrue(state["followup_armed"])
        finally:
            ambient_reply._SETTINGS = orig


if __name__ == "__main__":
    unittest.main()
