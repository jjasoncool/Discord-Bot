"""M7 精簡版：挑哪幾條、預算多少、怎麼寫進 auto_personality（hermetic，不碰 DB／LLM）。

守的幾件事：
  - 只挑證據跨 ≥2 次對話的條目（擋「一次當成習慣」），整條挑、不切半句
  - 基本個性（證據跨度長）先挑、最多一半預算；其餘條目依對話次數填滿，用不完的互讓
  - 預算扣掉標籤、自介與印象，發布當下插話那一行不超過上限——用 bot 讀取時的同一套函式驗
  - 寫入時標上來源與版本；寫入失敗算失敗，不能算成功
  - 發布開啟後，production 萃取（③／手動）跳過 ⑤ 要寫的人，③ 連 LLM 都不送；精簡版變空的人回到 ③ 手上
  - 群內流行語不當成個人特色：同一個詞在 ≥2 人的描述裡都被寫成口頭禪，那幾條都不發；
    講貼圖的條目不算；擋下的不佔預算
  - 把別的群友的名字寫成口頭禪的條目不發（本人的名字不算、單字不算）
  - 串接後不出現「。；」
  - 群友名字來自 Discord（顯示名稱、伺服器暱稱、全域名稱）、自介與印象

執行：
    cd src && python -m unittest test.test_persona_agent_publish -v
"""

import asyncio
import itertools
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

from llm.persona.agent import publish  # noqa: E402
from llm.persona.member_names import name_parts  # noqa: E402

NOW = datetime(2026, 9, 25, 12, tzinfo=timezone.utc)
_EPOCH_MS = 1420070400000


def sf(when: datetime) -> str:
    """造出某個時間點的 Discord snowflake id。"""
    return str((int(when.timestamp() * 1000) - _EPOCH_MS) << 22)


def ago(days: float = 0, hours: float = 0) -> datetime:
    return NOW - timedelta(days=days, hours=hours)


def item(text, *times, type_="keep"):
    return {"type": type_, "trait": "t", "text": text,
            "evidence_msg_ids": [sf(t) for t in times]}


class SelectLiteTests(unittest.TestCase):

    def test_single_conversation_is_not_eligible(self):
        """真實案例：「北側」全部發言只出現 1 次卻寫成「會用…」——一次當習慣不能給 bot。"""
        once = item("會用北側當地點代稱", ago(1), ago(1, hours=0.1))       # 同一段對話
        twice = item("常用低能貶稱", ago(1), ago(3))
        r = publish.select_lite([once, twice], 500, now=NOW)
        self.assertEqual([i.text for i in r.items], ["常用低能貶稱"])
        self.assertEqual(r.eligible, 1)

    def test_residue_markers_are_excluded_but_not_every_negation(self):
        """「（近期未見）」是改寫留下的標記；「不再是主力」這種句子還帶著現況，要留。"""
        residue = item("用「中風」形容被煩到（近期未見）", ago(1), ago(3))
        current = item("近期主玩魔獸世界，終末地不再是主力", ago(1), ago(3))
        r = publish.select_lite([residue, current], 500, now=NOW)
        self.assertEqual([i.text for i in r.items], ["近期主玩魔獸世界，終末地不再是主力"])

    def test_core_first_then_recent_by_last_seen(self):
        core = item("基本個性", ago(30), ago(10))            # 跨度 20 天
        recent_new = item("最近的", ago(0.5), ago(2))
        recent_old = item("稍早的", ago(5), ago(6))
        r = publish.select_lite([recent_old, core, recent_new], 500, now=NOW)
        self.assertEqual([i.text for i in r.items], ["基本個性", "最近的", "稍早的"])
        self.assertEqual([i.section for i in r.items], ["core", "recent", "recent"])
        self.assertEqual(r.text, "基本個性；最近的；稍早的")

    def test_recent_prefers_items_seen_in_more_conversations(self):
        """真實案例：9 次對話的特徵被一條晚幾分鐘、字數多的條目擠掉。次數多的先挑，次數
        相同才比時間；輸出也照這個順序——插話截斷時從尾巴切，先丟比較不重要的。"""
        frequent = item("常出現" + "字" * 20, ago(1.2), ago(1.4), ago(1.6), ago(1.8))  # 4 次
        newer = item("較新的" + "字" * 20, ago(1), ago(1.1))                            # 2 次
        only_one = publish.select_lite([newer, frequent], 30, now=NOW)
        self.assertEqual([i.text for i in only_one.items], [frequent["text"]])
        both = publish.select_lite([newer, frequent], 500, now=NOW)
        self.assertEqual([i.text for i in both.items], [frequent["text"], newer["text"]])

    def test_budget_is_respected_and_items_are_never_cut(self):
        items = [item("字" * n, ago(1), ago(3 + n)) for n in (40, 35, 30, 25)]
        r = publish.select_lite(items, 70, now=NOW)
        self.assertLessEqual(len(r.text), 70)
        originals = {c["text"] for c in items}
        for piece in r.text.split("；"):
            self.assertIn(piece, originals, "只能整條放，不能切半句")

    def test_core_is_capped_at_half_when_recent_competes(self):
        """第一輪基本個性最多一半預算。第二輪沒排進去的基本個性會跟近況一起依對話次數排——
        次數比近況多就可能超過一半（使用者 09-28 接受）；這裡次數相同，近況靠時間排進來。"""
        cores =[item(f"基本{i}" + "字" * 18, ago(40), ago(20 - i)) for i in range(4)]
        recent = item("最近" + "字" * 18, ago(0.5), ago(2))
        r = publish.select_lite([*cores, recent], 60, now=NOW)
        self.assertIn("recent", [i.section for i in r.items], "近況要留得到位置")
        core_len = sum(len(i.text) for i in r.items if i.section == "core")
        self.assertLessEqual(core_len, 30)

    def test_unused_space_flows_back_to_core(self):
        """沒有近況可放時，基本個性可以用滿整個預算，而且照樣排在基本個性那一段。"""
        cores = [item(f"基本{i}" + "字" * 18, ago(40), ago(20 - i)) for i in range(3)]
        r = publish.select_lite(cores, 70, now=NOW)
        self.assertEqual(len(r.items), 3)
        self.assertEqual({i.section for i in r.items}, {"core"})

    def test_nothing_eligible_means_empty(self):
        r = publish.select_lite([item("只講過一次", ago(1))], 500, now=NOW)
        self.assertEqual(r.text, "")
        self.assertEqual(r.items, [])

    def test_identical_text_is_used_once(self):
        """真實案例：舊版驗證沒擋住兩條 keep 指到同一項，版本裡留下兩條一字不差的條目。"""
        dup = [item("群裡的接梗吐槽擔當", ago(1), ago(3)), item("群裡的接梗吐槽擔當", ago(1), ago(3))]
        other = item("常用低能貶稱", ago(2), ago(4))
        r = publish.select_lite([*dup, other], 500, now=NOW)
        self.assertEqual(r.text, "群裡的接梗吐槽擔當；常用低能貶稱")
        self.assertEqual(r.eligible, 2, "相同文字算一條")

    def test_duplicate_keeps_the_better_ranked_copy(self):
        """兩份證據不同時，留排序在前的那份——不是版本裡先出現的那份。"""
        short = item("同一句", ago(1), ago(3))        # 跨度 2 天 → 近況
        long_ = item("同一句", ago(1), ago(30))       # 跨度 29 天 → 基本個性
        r = publish.select_lite([short, long_], 500, now=NOW)
        self.assertEqual([(i.text, i.section) for i in r.items], [("同一句", "core")])

    def test_drops_and_future_ids_do_not_count(self):
        dropped = item("被刪掉的", ago(1), ago(3), type_="drop")
        future = item("未來的證據", ago(1), NOW + timedelta(days=30))
        r = publish.select_lite([dropped, future], 500, now=NOW)
        self.assertEqual(r.text, "", "drop 不是描述；未來時間的 id 不算一次對話")


def intro_doc(pid, alias, bio):
    return {"metadata": {"profile_kind": "intro_profile", "author_id": pid, "alias": alias},
            "source": "sql_identity",
            "text": f"[Intro Profile]\nalias: {alias}\nwuwa_uid: -\nbio: {bio}\nmessage_to_all: -"}


def impression_doc(pid, text):
    return {"metadata": {"profile_kind": "impression", "target_user_id": pid, "target_alias": "某人"},
            "source": "sql_identity",
            "text": f"[Member Impression]\ntarget_user_id: {pid}\ntarget_alias: 某人\n"
                    f"target_habit: -\nimpression: {text}"}


class LineBudgetTests(unittest.TestCase):
    """預算要讓插話那一行剛好不超過上限——用 bot 讀取時的同一套函式組出來驗。"""

    def _line(self, docs, alias, lite):
        from llm.persona.persona_card_builder import build_persona_cards, format_persona_cards_for_context
        cards = build_persona_cards(docs=[*docs, publish._auto_doc(alias, lite, {"author_id": "1"})],
                                    requester_user_id=None, participant_user_ids=[],
                                    intent="general", alias_hints=[], max_cards=1)
        return " ".join(format_persona_cards_for_context(cards)[1]["content"].split())

    def test_filling_the_budget_exactly_fits_the_line(self):
        for bio in ("", "短介紹", "很長的自我介紹" * 30):
            docs = [intro_doc("1", "米拉", bio)] if bio else []
            docs += [impression_doc("1", "印象" * 40)]
            budget = publish.line_budget(person_docs=docs, alias="米拉",
                                         auto_metadata={"author_id": "1"},
                                         line_max_chars=500, card_field_chars=600)
            if budget == 0:
                continue
            line = self._line(docs, "米拉", "字" * budget)
            self.assertLessEqual(len(line), 500, f"bio 長度 {len(bio)}")
            self.assertEqual(len(line), 500, "預算用滿時剛好碰到上限，不浪費也不超過")

    def test_long_intro_leaves_less_room(self):
        short = publish.line_budget(person_docs=[intro_doc("1", "米拉", "短")], alias="米拉",
                                    auto_metadata={"author_id": "1"}, line_max_chars=500,
                                    card_field_chars=600)
        long = publish.line_budget(person_docs=[intro_doc("1", "米拉", "長" * 300)], alias="米拉",
                                   auto_metadata={"author_id": "1"}, line_max_chars=500,
                                   card_field_chars=600)
        self.assertLess(long, short)

    def test_askai_field_limit_also_applies(self):
        """/askai 的卡片欄位上限比插話那一行緊時，以它為準——用滿剛好碰到欄位上限。"""
        budget = publish.line_budget(person_docs=[], alias="米拉", auto_metadata={"author_id": "1"},
                                     line_max_chars=5000, card_field_chars=100)
        doc = publish._auto_doc("米拉", "字" * budget, {"author_id": "1"})
        self.assertEqual(len(" ".join(doc["text"].split())), 100)

    def test_askai_card_keeps_the_whole_lite(self):
        """用真的欄位上限：預算內的最後一個字留得住，多一個字就被 /askai 的卡片切掉。"""
        from llm.persona.persona_card_builder import PERSONA_MAX_CARD_CHARS, build_persona_cards
        md = {"author_id": "1"}
        budget = publish.line_budget(person_docs=[], alias="米拉", auto_metadata=md,
                                     line_max_chars=5000, card_field_chars=PERSONA_MAX_CARD_CHARS)

        def summary(lite):
            cards = build_persona_cards(docs=[publish._auto_doc("米拉", lite, md)],
                                        requester_user_id=None, participant_user_ids=[],
                                        intent="general", alias_hints=[], max_cards=1)
            return cards[0]["auto_personality_summary"]

        fits = "字" * (budget - 1) + "尾"
        self.assertTrue(summary(fits).endswith("尾"))
        self.assertFalse(summary(fits + "多").endswith("多"))


class PlanForTests(unittest.TestCase):

    ROW = {"version": 13, "changes": [item("常用低能貶稱", ago(1), ago(3))]}

    AUTO = {"metadata": {"profile_kind": "auto_personality", "author_id": "1", "alias": "舊名字"},
            "source": "sql_identity", "text": "[Auto Personality]\nalias: 舊名字\npersonality: 舊的"}

    def test_current_display_name_wins(self):
        """發布開啟後 ③ 不再寫這個人，別名要跟著顯示名稱更新，不能沿用文件裡的舊別名。"""
        plan = publish.plan_for("1", self.ROW, {"auto_personality": [self.AUTO]},
                                line_max_chars=500, card_field_chars=600, display_name="米拉",
                                now=NOW)
        self.assertEqual(plan.alias, "米拉")
        self.assertEqual(plan.version, 13)
        self.assertEqual(plan.lite.text, "常用低能貶稱")

    def test_without_display_name_keeps_stored_alias(self):
        """不在成員快取裡（例如已離開伺服器）時沿用舊別名。"""
        plan = publish.plan_for("1", self.ROW, {"auto_personality": [self.AUTO]},
                                line_max_chars=500, card_field_chars=600, now=NOW)
        self.assertEqual(plan.alias, "舊名字")

    @staticmethod
    def _impression(text, alias, habit="-"):
        return {"metadata": {"profile_kind": "impression", "target_user_id": "1",
                             "target_alias": alias},
                "source": "sql_identity",
                "text": f"[Member Impression]\ntarget_user_id: 1\ntarget_alias: {alias}\n"
                        f"target_habit: {habit}\nimpression: {text}"}

    def _worst_line(self, plan, impressions, intros=()):
        """bot 撈到 0～3 則印象（自介有撈到、沒撈到都算）、任何順序時，把預算用滿的那一行
        最長有多長。

        用滿的是**扣掉 BUDGET_MARGIN 之前**的預算：那份餘裕是留給列舉不到的情況的，
        這裡列舉得到的組合與順序要靠計算算準，不能靠它蓋過去。
        """
        from llm.persona.persona_card_builder import build_persona_cards, format_persona_cards_for_context
        fill = "字" * (plan.budget + publish.BUDGET_MARGIN)
        # 真的寫入時 metadata 帶著別名（`index_auto_personality`），標籤會把它算進去
        auto = publish._auto_doc(plan.alias, fill, {"author_id": "1", "alias": plan.alias})
        combos = [(*i, *c) for i in ([()] + ([tuple(intros)] if intros else []))
                  for k in range(min(3, len(impressions)) + 1)
                  for c in itertools.permutations(impressions, k)]
        longest = 0
        for combo in combos:
            cards = build_persona_cards(docs=[*combo, auto], requester_user_id=None,
                                        participant_user_ids=[], intent="general", alias_hints=[],
                                        max_cards=1)
            line = format_persona_cards_for_context(cards)[1]["content"]
            longest = max(longest, len(" ".join(line.split())))
        return longest

    def test_every_impression_order_fits(self):
        """順序會影響長度：清理印象時只有第一則的「target_habit:」會被拿掉，換個順序就差幾個字
        （這個例子差 2 字，亂數搜出來的）。差得不多、BUDGET_MARGIN 蓋得過去，但列舉就是要算準，
        不能靠餘裕。別名都一樣、標籤固定，所以用滿時應該剛好碰到上限。"""
        imps = [self._impression("字" * 84, "阿"),
                self._impression("字" * 55, "阿", habit="習" * 37),
                self._impression("字" * 73, "阿"),
                self._impression("字" * 124, "阿")]
        plan = publish.plan_for("1", self.ROW, {"impression": imps}, line_max_chars=500,
                                card_field_chars=600, display_name="米拉", now=NOW)
        self.assertGreater(plan.budget, 0)
        self.assertEqual(self._worst_line(plan, imps), 500, "最壞的順序剛好碰到上限")

    def test_fewer_impressions_can_mean_a_longer_label(self):
        """沒有自介時卡片標籤取所有別名裡排最前的那個：三則都撈到時是「a」，少撈了那則
        就換成 40 字的別名——撈得少，那一行反而更長。"""
        imps = [self._impression("嗨", "a"),
                self._impression("字" * 150, "b" * 40),
                self._impression("字" * 150, "c" * 40)]
        plan = publish.plan_for("1", self.ROW, {"impression": imps}, line_max_chars=500,
                                card_field_chars=600, display_name="米拉", now=NOW)
        self.assertLessEqual(self._worst_line(plan, imps), 500)

    def test_missing_intro_switches_the_label(self):
        """自介是最舊的文件，bot 的 SQL 依新到舊撈、有筆數上限，最先被擠掉的就是它。沒撈到
        自介時標籤從自介的別名（「喵」）換成顯示名稱或印象的別名，可能長很多。"""
        intros = [intro_doc("1", "喵", "嗨")]
        imps = [self._impression("評" * 60, "a" * 50)]
        for person_imps in ([], imps):
            plan = publish.plan_for("1", self.ROW, {"intro_profile": intros, "impression": person_imps},
                                    line_max_chars=500, card_field_chars=600,
                                    display_name="顯" * 32, now=NOW)
            self.assertLessEqual(self._worst_line(plan, person_imps, intros), 500,
                                 f"印象 {len(person_imps)} 則")

    def test_label_from_an_impression_outside_the_pool(self):
        """第 7 則印象不在列舉範圍內，但它的別名排最前、撈到它時就成了標籤。"""
        pool = [self._impression("評" * 60, "b") for _ in range(6)]
        outside = self._impression("評" * 55, "a" * 50)
        plan = publish.plan_for("1", self.ROW, {"impression": [*pool, outside]}, line_max_chars=500,
                                card_field_chars=600, display_name="米拉", now=NOW)
        self.assertLessEqual(self._worst_line(plan, [outside, *pool[:2]]), 500)

    def test_old_long_impressions_are_counted(self):
        """語意檢索可能撈到很舊的印象：最新 6 則都很短時，舊的長印象照樣要算進預算。"""
        imps = ([self._impression("短" * 10, "阿") for _ in range(6)]             # 新
                + [self._impression("長" * 150, "阿") for _ in range(2)])        # 舊
        plan = publish.plan_for("1", self.ROW, {"impression": imps}, line_max_chars=500,
                                card_field_chars=600, display_name="米拉", now=NOW)
        self.assertLessEqual(self._worst_line(plan, imps[:1] + imps[6:]), 500)

    def test_pool_ranks_by_what_the_card_shows(self):
        """原始文字含 target_alias，清理時會被拿掉：別名很長的印象原始文字長、卡片上卻短。
        照原始長度挑的話，卡片上最長的那則會被擠出列舉範圍。"""
        long_alias = [self._impression("短" * 100, "名" * 50) for _ in range(6)]
        wide = self._impression("長" * 140, "阿")
        imps = [*long_alias, wide]
        plan = publish.plan_for("1", self.ROW, {"impression": imps}, line_max_chars=500,
                                card_field_chars=600, display_name="米拉", now=NOW)
        self.assertLessEqual(self._worst_line(plan, [wide, *long_alias[:2]]), 500)


class RunPublishTests(unittest.TestCase):

    VERSIONS = {
        "1": {"version": 13, "changes": [item("常用低能貶稱", ago(1), ago(3))]},
        "2": {"version": 4, "changes": [item("只講過一次", ago(1))]},
    }
    PERSONS = {"1": {"auto_personality": [{
        "metadata": {"profile_kind": "auto_personality", "author_id": "1", "alias": "米拉"},
        "source": "sql_identity", "text": "[Auto Personality]\nalias: 米拉\npersonality: 舊的"}]}}

    def _run(self, mode, write=None, names=None):
        store = mock.MagicMock()
        store.index_auto_personality = write or mock.AsyncMock(return_value=True)
        with mock.patch.object(publish, "load_guild_state", return_value=(self.VERSIONS, self.PERSONS)):
            stats = asyncio.run(publish.run_publish(guild_id=9, mode=mode, display_names=names,
                                                    profile_store=store))
        return stats, store

    def test_off_does_nothing(self):
        stats, store = self._run("off")
        self.assertEqual(stats, {"skipped": 1})
        store.index_auto_personality.assert_not_called()

    def test_dry_run_never_writes(self):
        stats, store = self._run("dry_run")
        store.index_auto_personality.assert_not_called()
        self.assertEqual(stats["dry_run"], 1)
        self.assertEqual(stats["empty"], 1, "精簡版是空的人照樣算得出來、只是不寫")

    def test_on_writes_with_source_and_version(self):
        stats, store = self._run("on")
        self.assertEqual(stats["written"], 1)
        self.assertEqual(stats["failed"], 0)
        kw = store.index_auto_personality.call_args.kwargs
        self.assertEqual(kw["author_id"], 1)
        self.assertEqual(kw["alias"], "米拉")
        self.assertEqual(kw["personality"], "常用低能貶稱")
        self.assertEqual(kw["extra_metadata"], {"written_by": "persona_agent", "agent_version": "13"})

    def test_display_name_is_written_as_alias(self):
        _, store = self._run("on", names={"1": "新名字"})
        self.assertEqual(store.index_auto_personality.call_args.kwargs["alias"], "新名字")

    def test_failed_write_is_not_counted_as_written(self):
        """寫入函式自己吞例外、回傳 False；丟例外也一樣——兩種都算失敗。"""
        for write in (mock.AsyncMock(return_value=False), mock.AsyncMock(side_effect=RuntimeError("x"))):
            stats, _ = self._run("on", write)
            self.assertEqual((stats["written"], stats["failed"]), (0, 1))

    def test_empty_lite_is_not_written(self):
        """第 2 人沒有任何條目過門檻——不寫，交給 ③。"""
        _, store = self._run("on")
        written_for = [c.kwargs["author_id"] for c in store.index_auto_personality.call_args_list]
        self.assertNotIn(2, written_for)


class ProductionSkipListTests(unittest.TestCase):
    """③ 與手動萃取要跳過誰：只有 ⑤ 這一晚真的會寫精簡版的人。"""

    VERSIONS = {
        "1": {"version": 13, "changes": [item("常用低能貶稱", ago(1), ago(3))]},
        # 之前發布過（文件標著 written_by），但現在精簡版是空的
        "2": {"version": 5, "changes": [item("只講過一次", ago(1))]},
    }
    PERSONS = {"2": {"auto_personality": [{
        "metadata": {"profile_kind": "auto_personality", "author_id": "2", "alias": "克羅",
                     "written_by": "persona_agent", "agent_version": "4"},
        "source": "sql_identity", "text": "[Auto Personality]\nalias: 克羅\npersonality: 舊的精簡版"}]}}

    def _skip(self, publish_mode="on", enabled=True):
        settings = SimpleNamespace(publish_mode=publish_mode, enabled=enabled)
        with mock.patch("sys_settings.llm_settings.PersonaAgentSettings", return_value=settings), \
             mock.patch.object(publish, "load_guild_state",
                               return_value=(self.VERSIONS, self.PERSONS)) as load:
            return asyncio.run(publish.production_skip_list(9)), load

    def test_only_people_with_a_lite_are_skipped(self):
        skip, _ = self._skip()
        self.assertEqual(skip, {"1"})

    def test_published_person_whose_lite_became_empty_goes_back_to_production(self):
        """審查時的重現：看「誰被發布過」的話，第 2 人 ③ 永遠跳過、⑤ 又不寫——兩邊都不更新。"""
        skip, _ = self._skip()
        self.assertNotIn("2", skip)

    def test_nothing_is_skipped_unless_publishing_is_on(self):
        for mode, enabled in (("off", True), ("dry_run", True), ("on", False)):
            skip, load = self._skip(mode, enabled)
            self.assertEqual(skip, set(), f"{mode=} {enabled=}")
            load.assert_not_called()

    def test_agent_disabled_turns_publishing_off(self):
        """④ 關掉就沒有新版本：⑤ 只會一直寫同一份舊的精簡版、③ 又跳過——兩邊都不更新。"""
        settings = SimpleNamespace(publish_mode="on", enabled=False)
        with mock.patch("sys_settings.llm_settings.PersonaAgentSettings", return_value=settings):
            self.assertEqual(publish.effective_publish_mode(), "off")


class SplitUncoveredTests(unittest.TestCase):
    def test_covered_people_are_skipped_and_listed(self):
        results = {"1": {"alias": "米拉", "personality": "p"}, "2": {"alias": "克羅", "personality": "p"}}
        kept, skipped = publish.split_uncovered(results, {"1"})
        self.assertEqual(list(kept), ["2"])
        self.assertEqual(skipped, ["米拉"])


class AutoPersonalityMetadataTests(unittest.TestCase):
    """寫入函式：extra_metadata 蓋在預設值上；回傳是否真的寫進去。"""

    def _write(self, extra, *, ready=True, fail=False):
        from llm.storage.member_profile_store import PgVectorMemberProfileStore
        store = object.__new__(PgVectorMemberProfileStore)
        captured = {}

        async def fake_ainsert(*, doc_id, text, metadata):
            if fail:
                raise RuntimeError("embedding down")
            captured.update(doc_id=doc_id, text=text, metadata=metadata)

        store._dependencies_ready = lambda: ready
        store._ainsert = fake_ainsert
        ok = asyncio.run(store.index_auto_personality(
            guild_id=9, author_id=1, alias="米拉", personality="常用低能貶稱", extra_metadata=extra))
        return ok, captured

    def test_production_write_is_unchanged(self):
        ok, captured = self._write(None)
        self.assertTrue(ok)
        self.assertIn("last_extracted_at", captured["metadata"])
        self.assertNotIn("written_by", captured["metadata"])

    def test_agent_write_is_tagged_and_timestamped(self):
        """萃取時間記當下——啟動補跑看它，發布後沿用舊時間會讓每次重啟都補跑。"""
        _, captured = self._write({"written_by": "persona_agent", "agent_version": "13"})
        md = captured["metadata"]
        self.assertEqual((md["written_by"], md["agent_version"]), ("persona_agent", "13"))
        self.assertIn("last_extracted_at", md)

    def test_reports_failure(self):
        self.assertFalse(self._write(None, fail=True)[0])
        self.assertFalse(self._write(None, ready=False)[0])


class ProductionExtractionTests(unittest.TestCase):
    """③／手動萃取這一側：跳過 ⑤ 要寫的人、只把真的寫進去的算成功。"""

    def test_excluded_people_are_not_sent_to_the_llm(self):
        """實測 9/30、10/01：③ 對 37／34 人跑了約 12 分鐘 LLM，全部被跳過、寫入 0——要在送 LLM 前就拿掉。"""
        from llm.persona import personality_extractor as pe
        guild = mock.MagicMock()
        guild.id = 9

        async def extract(**kw):
            return {uid: {"alias": "a", "personality": "p"} for uid in kw["user_groups"]}

        save = mock.AsyncMock(return_value=1)
        extract_mock = mock.AsyncMock(side_effect=extract)
        with mock.patch.object(pe, "fetch_recent_messages", return_value=[{"m": 1}]), \
             mock.patch.object(pe, "group_by_user", return_value={"1": [], "2": []}), \
             mock.patch.object(pe, "_fetch_aliases_from_db", return_value={}), \
             mock.patch.object(pe, "extract_personalities", extract_mock), \
             mock.patch.object(pe, "save_personality_results", save):
            out = asyncio.run(pe._run_personality_extraction_impl(
                guild=guild, days=14, model="m", exclude_author_ids={"1"}))
        self.assertEqual(list(extract_mock.call_args.kwargs["user_groups"]), ["2"])
        self.assertEqual(list(out), ["2"])
        self.assertEqual(list(save.call_args.kwargs["results"]), ["2"])

    def test_everyone_excluded_means_no_llm_call(self):
        from llm.persona import personality_extractor as pe
        extract_mock = mock.AsyncMock()
        with mock.patch.object(pe, "fetch_recent_messages", return_value=[{"m": 1}]), \
             mock.patch.object(pe, "group_by_user", return_value={"1": []}), \
             mock.patch.object(pe, "extract_personalities", extract_mock):
            out = asyncio.run(pe._run_personality_extraction_impl(
                guild=mock.MagicMock(), days=14, model="m", exclude_author_ids={"1"}))
        self.assertEqual(out, {})
        extract_mock.assert_not_called()

    def test_only_successful_writes_are_counted(self):
        from llm.persona import personality_extractor as pe
        store = mock.MagicMock()
        store.index_auto_personality = mock.AsyncMock(side_effect=[True, False, RuntimeError("x")])
        results = {str(i): {"alias": "a", "personality": "p"} for i in (1, 2, 3)}
        with mock.patch("llm.storage.member_profile_store.get_member_profile_store", return_value=store):
            written = asyncio.run(pe.save_personality_results(guild_id=9, results=results))
        self.assertEqual(written, 1)


class GroupSlangTests(unittest.TestCase):
    """真實案例：「484」在 3 個人的描述裡都被寫成他的口頭禪，「何意味」2 人——那是群裡大家都在講的詞。"""

    @staticmethod
    def changes(*texts):
        return [item(t, ago(1), ago(3)) for t in texts]

    def test_word_claimed_by_two_people_is_group_slang(self):
        slang = publish.find_group_slang({
            "1": self.changes("口頭禪「484」，常帶懷疑語氣"),
            "2": self.changes("句尾極愛掛「484」當萬能語氣詞"),
            "3": self.changes("口頭禪「何意味」"),
        }, nicknames=[])
        self.assertEqual(slang, {"484"}, "只有一個人被這樣寫的是他自己的口頭禪")

    def test_member_nicknames_are_not_slang(self):
        """「阿喵」被兩個人寫成口頭禪，其實是在叫群友——那是歸因錯誤（另一條規則擋），不是流行語。"""
        slang = publish.find_group_slang({
            "1": self.changes("「阿喵」是他的固定口頭禪"),
            "2": self.changes("口頭禪是「阿喵」"),
        }, nicknames=["阿喵", "柔喵"])
        self.assertEqual(slang, frozenset())

    def test_sticker_and_plain_mentions_do_not_count(self):
        """「安可瘋狂」是貼圖名稱，12 個人都用；只是提到一個詞、沒說是口頭禪的也不算。"""
        slang = publish.find_group_slang({
            "1": self.changes("興奮時連發「安可瘋狂」貼圖，像口頭禪一樣", "跟「一野」同一陣營"),
            "2": self.changes("「安可瘋狂」表情是他的口頭禪", "對「一野」有固定損法"),
        }, nicknames=[])
        self.assertEqual(slang, frozenset())

    def test_slang_items_are_withheld_without_using_budget(self):
        claim = item("口頭禪「484」，常帶懷疑語氣", ago(1), ago(3), ago(5))   # 次數最多、排第一
        mention = item("會拿「484」接別人的梗", ago(1), ago(3))
        other = item("吐槽擔當", ago(2), ago(4))
        budget = len(mention["text"]) + 1 + len(other["text"])
        r = publish.select_lite([claim, mention, other], budget, now=NOW, group_slang=frozenset({"484"}))
        self.assertEqual(r.withheld, [(publish.WITHHELD_SLANG, claim["text"])])
        self.assertEqual(sorted(i.text for i in r.items), sorted([mention["text"], other["text"]]),
                         "擋下的不佔預算；只是提到這個詞、沒說是口頭禪的照發")


class PunctuationTests(unittest.TestCase):
    def test_trailing_period_does_not_double_up(self):
        """真實案例：10 個人的精簡版裡有「。；」——條目自帶句號，串接又加分號。"""
        r = publish.select_lite([item("吐槽擔當。", ago(1), ago(3)), item("常用低能貶稱。", ago(2), ago(4))],
                                500, now=NOW)
        self.assertEqual(r.text, "吐槽擔當；常用低能貶稱")


def nickname_docs(pid, intro_alias=None, impression_aliases=(), auto_alias=None):
    docs = {"intro_profile": [], "impression": [], "auto_personality": []}
    if intro_alias is not None:
        docs["intro_profile"].append({"metadata": {"profile_kind": "intro_profile", "author_id": pid,
                                                   "alias": intro_alias}, "text": ""})
    for a in impression_aliases:
        docs["impression"].append({"metadata": {"profile_kind": "impression", "target_user_id": pid,
                                                "target_alias": a}, "text": ""})
    if auto_alias is not None:
        docs["auto_personality"].append({"metadata": {"profile_kind": "auto_personality", "author_id": pid,
                                                      "alias": auto_alias}, "text": ""})
    return docs


class MemberNicknamesTests(unittest.TestCase):
    """群裡叫的名字散在三處：Discord（糯糯的全域名稱是「一野shout死你」，群裡叫他一野）、
    自介「別人常常叫我什麼」、印象「你平常怎麼稱呼他」（「阿喵」只在這裡有）。"""

    def test_intro_and_impression_nicknames_are_merged(self):
        persons = {"1": nickname_docs("1", intro_alias="柔喵, 阿喵", impression_aliases=["阿喵", "喵董"],
                                      auto_alias="❤️柔柔喵❤️-時渺")}
        self.assertEqual(publish.member_nicknames(persons), {"1": ("❤️柔柔喵❤️-時渺", ["柔喵", "阿喵", "喵董"])})

    def test_discord_names_join_and_label_the_table(self):
        persons = {"1": nickname_docs("1", intro_alias="米拉、拉拉", auto_alias="舊名字")}
        names = {"1": ["米拉"], "9": ["糯糯 弗糯糯", "一野shout死你"]}
        self.assertEqual(publish.member_nicknames(persons, names, people=["9"]),
                         {"1": ("米拉", ["拉拉"]), "9": ("糯糯 弗糯糯", ["一野shout死你"])},
                         "顯示名稱以 Discord 當下的為準；沒有自介的人（people）也列")
        slash = "Biboolater-只剩我沒6命愛彌斯/緋雪/心了"
        self.assertEqual(publish.member_nicknames({}, {"8": [slash, "Biboolater"]}, people=["8"]),
                         {"8": (slash, ["Biboolater"])}, "Discord 名字裡的「/」不能拆")

    def test_everyone_with_a_name_is_listed(self):
        """只有一個名字的人也要列：模型才認得訊息裡的「克羅」是群友。"""
        persons = {"1": nickname_docs("1", auto_alias="克羅"),
                   "2": nickname_docs("2", impression_aliases=["阿狗"])}
        self.assertEqual(publish.member_nicknames(persons), {"1": ("克羅", []), "2": ("阿狗", [])})


class MemberNameClaimTests(unittest.TestCase):
    """真實案例：雞蛋飛被寫成「『糯糯』是他的口頭禪」、Ἡράκλειος「『阿狗』是他的固定口頭禪」——
    那是在叫群友。④ 只重跑有新發言的人，舊條目要靠發布這關擋。"""

    PARTS = name_parts(["糯糯 弗糯糯", "一野shout死你", "❤️柔柔喵❤️-時渺", "阿喵", "喵董",
                        "Biboolater-只剩我沒6命愛彌斯/緋雪/心了", "棒槌 or 不是棒槌", "我們之間沒有愛"])

    def withheld(self, text):
        return publish.withhold_reason(text, member_parts=self.PARTS)

    def test_member_names_written_as_catchphrases_are_withheld(self):
        for text in ("「糯糯」是他的口頭禪", "口頭禪「肥糯糯」，用來自嘲",      # 名字的一段、含名字
                     "「一野」是他的口頭禪", "常把「伺候阿喵吃肉」掛嘴邊當口頭禪"):  # 名字的一部分、句子裡有名字
            self.assertEqual(self.withheld(text), publish.WITHHELD_MEMBER_NAME, text)

    def test_single_characters_and_plain_mentions_are_kept(self):
        """「喵」這種單字到處都是；沒說是口頭禪、只是寫跟誰互動的照發。"""
        self.assertIsNone(self.withheld("「喵」語尾是他的習慣，像口頭禪"))
        self.assertIsNone(self.withheld("常跟「糯糯」互損，替他出頭"))
        self.assertIsNone(self.withheld("「緋雪」是他的口頭禪"), "名字裡用符號隔開的一段（遊戲角色）不算名字")

    def test_partial_words_are_not_names(self):
        """複查指出：自介別名「棒槌 or 不是棒槌」切出「or」，「sorry」就被當成名字；
        「我們之間沒有愛」讓「我們」被當成名字。英文要整個字、開頭要到詞的邊界才算。"""
        self.assertIsNone(self.withheld("口頭禪「sorry」，道歉也像在敷衍"))
        self.assertIsNone(self.withheld("「我們」是他的口頭禪"))
        self.assertEqual(self.withheld("口頭禪「or not」"), publish.WITHHELD_MEMBER_NAME, "整個字照算")

    def test_own_name_is_not_withheld(self):
        """自稱不是誤認：糯糯自封「肥糯糯」照發，別人把「糯糯」當口頭禪才擋。"""
        versions = {
            "9": {"version": 2, "changes": [item("自封「肥糯糯」，當口頭禪自嘲", ago(1), ago(3))]},
            "1": {"version": 2, "changes": [item("「糯糯」是他的口頭禪", ago(1), ago(3)), item("吐槽擔當", ago(1), ago(3))]},
        }
        names = {"9": ["糯糯 弗糯糯", "一野shout死你"], "1": ["雞蛋飛"]}
        with mock.patch.object(publish, "load_guild_state", return_value=(versions, {})):
            plans, _ = publish.build_plans(9, member_names=names, now=NOW)
        self.assertEqual(plans["9"].lite.text, "自封「肥糯糯」，當口頭禪自嘲")
        self.assertEqual(plans["1"].lite.text, "吐槽擔當")
        self.assertEqual(plans["1"].lite.withheld, [(publish.WITHHELD_MEMBER_NAME, "「糯糯」是他的口頭禪")])
        self.assertEqual(plans["9"].alias, "糯糯 弗糯糯", "顯示名稱取 member_names 的第一個")


class BuildPlansGroupSlangTests(unittest.TestCase):
    """⑤ 實際跑的路徑：流行語跨所有人算一次，暱稱從自介與印象排除。"""

    def test_slang_and_member_names_are_withheld_for_different_reasons(self):
        versions = {
            "1": {"version": 3, "changes": [item("口頭禪「484」", ago(1), ago(3)), item("吐槽擔當", ago(1), ago(3))]},
            "2": {"version": 5, "changes": [item("口頭禪「484」", ago(2), ago(4))]},
            "3": {"version": 2, "changes": [item("「阿喵」是他的固定口頭禪", ago(1), ago(3))]},
            "4": {"version": 2, "changes": [item("口頭禪是「阿喵」", ago(1), ago(3))]},
        }
        persons = {"5": nickname_docs("5", intro_alias="柔喵, 阿喵")}
        with mock.patch.object(publish, "load_guild_state", return_value=(versions, persons)):
            plans, failed = publish.build_plans(9, now=NOW)
        self.assertEqual(failed, {})
        self.assertEqual(plans["1"].lite.text, "吐槽擔當")
        self.assertEqual(plans["2"].lite.text, "")
        self.assertEqual(plans["3"].lite.withheld, [(publish.WITHHELD_MEMBER_NAME, "「阿喵」是他的固定口頭禪")],
                         "阿喵是群友（自介登記的暱稱）：不算流行語，算把名字寫成口頭禪")


if __name__ == "__main__":
    unittest.main()
