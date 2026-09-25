"""驗證層：把 LLM 輸出當成不可信輸入（hermetic，不碰 DB）。

每條測試都對應一次真實觀察到的失敗：

  - 26 個證據裡有 1 個是編的，夾在兩個真的中間、格式完全合理、前 10 位數字都對
  - `confidence: high` 的那次執行，正是編造 ID 的那次
  - strict schema 完全放行 `text=""` + `evidence=[]` 的 add 項

執行：
    cd src && python -m unittest test.test_persona_agent_validation -v
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from llm.persona_agent import validation  # noqa: E402

ALICE = "1001"
REAL = ["m1", "m2", "m3"]


def fetch_only(known, texts=None):
    """假的證據反查：只認得 `known` 這些 id，回 (id, 原文) 兩欄。

    `texts` 給引號比對用；不指定就回空字串（等於「引號一定對不上」，
    但引號只計數不擋，所以既有測試的預期不受影響）。
    """
    texts = texts or {}
    def _fetch(sql, params):
        wanted = params[1]
        return [(i, texts.get(i, "")) for i in wanted if i in known]
    return _fetch


def change(**kw):
    base = {
        "type": "add", "trait": "吐槽擔當", "text": "習慣用反話虧隊友",
        "reason": "現場對方跟著笑", "evidence_msg_ids": ["m1"],
    }
    base.update(kw)
    return base


def diff(changes, *, confidence="high", user_id=ALICE):
    return {"user_id": user_id, "changes": changes,
            "confidence": confidence, "notes": ""}


class EvidenceTests(unittest.TestCase):
    def test_only_the_poisoned_item_is_rejected(self):
        """逐項處理——整筆丟棄等於為了一顆老鼠屎倒掉一鍋粥。"""
        good = change(trait="好的", evidence_msg_ids=["m1", "m2"])
        bad = change(trait="有假證據", evidence_msg_ids=["m3", "9999999999"])
        r = validation.validate_diff(
            diff([good, bad]), user_id=ALICE, fetch=fetch_only(REAL)
        )
        self.assertEqual([c["trait"] for c in r.accepted], ["好的"])
        self.assertEqual(len(r.rejected), 1)
        self.assertIn("9999999999", r.rejected[0]["why"])
        self.assertIsNone(r.skip_reason, "還有通過的項目就該寫入")

    def test_hallucination_rate_is_recorded(self):
        r = validation.validate_diff(
            diff([change(evidence_msg_ids=["m1", "m2", "nope"])]),
            user_id=ALICE, fetch=fetch_only(REAL),
        )
        self.assertEqual(r.evidence_claimed, 3)
        self.assertEqual(r.evidence_bogus, 1)
        self.assertAlmostEqual(r.hallucination_rate, 0.3333, places=3)

    def test_evidence_belonging_to_someone_else_is_rejected(self):
        """ID 存在但屬於別人，等於拿別人的話當這個人的證據。"""
        r = validation.validate_diff(
            diff([change(evidence_msg_ids=["m9"])]),
            user_id=ALICE, fetch=fetch_only(REAL),  # m9 不在該使用者名下
        )
        self.assertEqual(r.accepted, [])
        self.assertEqual(r.skip_reason, "沒有任何一項通過驗證")

    def test_lookup_failure_does_not_condemn_everything(self):
        """反查掛掉時寧可放行也不要冤枉——但要留 log。"""
        def boom(sql, params):
            raise RuntimeError("db down")
        r = validation.validate_diff(
            diff([change()]), user_id=ALICE, fetch=boom
        )
        self.assertEqual(len(r.accepted), 1)


class ShapeTests(unittest.TestCase):
    """strict schema 放行的語意空殼。"""

    def test_empty_text_rejected(self):
        r = validation.validate_diff(
            diff([change(text="")]), user_id=ALICE, fetch=fetch_only(REAL)
        )
        self.assertIn("text 為空", r.rejected[0]["why"])

    def test_empty_evidence_rejected(self):
        r = validation.validate_diff(
            diff([change(evidence_msg_ids=[])]), user_id=ALICE, fetch=fetch_only(REAL)
        )
        self.assertIn("evidence_msg_ids 為空", r.rejected[0]["why"])

    def test_bad_type_rejected(self):
        r = validation.validate_diff(
            diff([change(type="delete")]), user_id=ALICE, fetch=fetch_only(REAL)
        )
        self.assertIn("type 不合法", r.rejected[0]["why"])


class SkipTests(unittest.TestCase):
    def test_low_confidence_does_not_write_a_version(self):
        r = validation.validate_diff(
            diff([change()], confidence="low"), user_id=ALICE, fetch=fetch_only(REAL)
        )
        self.assertEqual(len(r.accepted), 1, "項目本身有效")
        self.assertIn("confidence=low", r.skip_reason, "但整筆不寫版本")

    def test_high_confidence_is_not_a_free_pass(self):
        """編造 ID 的那次執行，自己標的就是 high。"""
        r = validation.validate_diff(
            diff([change(evidence_msg_ids=["nope"])], confidence="high"),
            user_id=ALICE, fetch=fetch_only(REAL),
        )
        self.assertEqual(r.accepted, [])

    def test_wrong_user_id_aborts(self):
        """拿 A 的資料寫成 B 的人格，比幻覺更嚴重。"""
        r = validation.validate_diff(
            diff([change()], user_id="9999"), user_id=ALICE, fetch=fetch_only(REAL)
        )
        self.assertIn("user_id 不符", r.skip_reason)


class QuoteMatchTests(unittest.TestCase):
    """描述裡「」引號內的字串，要能在自己列的證據原文裡找到。

    **這是警示不是過濾器**——實測兩晚 118 個引號片段，裸比對有 27 個對不上，
    其中約半數是冤枉的。拿來退件會砍掉正確的描述，比放行錯誤的更糟，所以
    只計數進 runs 表，當人工複查的排序鍵。下面每條都對應一次真實觀察。
    """

    def _run(self, text, msg_text):
        r = validation.validate_diff(
            diff([change(text=text, evidence_msg_ids=["m1"])]),
            user_id=ALICE, fetch=fetch_only({"m1"}, {"m1": msg_text}),
        )
        return r

    def test_quote_found_in_evidence(self):
        r = self._run("常罵「垃圾索」", "反正PS 88 垃圾索")
        self.assertEqual(r.quote_unmatched, 0)

    def test_fabricated_quote_is_counted(self):
        r = self._run("自稱「肥矮醜就是我了」", "完全無關的一句話")
        self.assertEqual(r.quote_unmatched, 1)
        self.assertIn("肥矮醜就是我了", r.quote_misses)

    def test_counting_never_rejects(self):
        """對不上也照樣寫入——這條是本組的重點。"""
        r = self._run("自稱「完全編造的一句」", "無關內容")
        self.assertEqual(len(r.accepted), 1)
        self.assertEqual(len(r.rejected), 0)
        self.assertIsNone(r.skip_reason)

    def test_emoji_rendered_name_matches(self):
        """DB 存的是渲染後的 `:生氣:`，模型寫「生氣」就是子字串。"""
        self.assertEqual(self._run("愛用「生氣」", ":生氣:").quote_unmatched, 0)

    def test_slash_joined_variants_split(self):
        """模型愛用「／」合併兩種說法，任一命中就算數。"""
        self.assertEqual(
            self._run("常說「晚安阿喵／早安阿喵」", "晚安阿喵").quote_unmatched, 0)

    def test_split_actually_checks_each_part(self):
        """切分規則要真的比對每一段——用 >2 字的段落才驗得到。

        原本這條寫的是 `「拒絕/不要」` vs `:不要、拒絕:`，看起來像在驗「順序顛倒
        也能命中」，其實兩段都只有 2 字、被短詞規則整個跳過，刪掉切分規則照樣通過。
        **順序顛倒目前並沒有被處理**，那屬於 quote_unmatched 已知的雜訊。
        """
        # 「知道了」3 字，會實際比對；語料無關 → 要算一次沒命中
        self.assertEqual(self._run("用「知道了/無奈」", "完全無關").quote_unmatched, 1)
        # 同一個引號，語料含其中一段 → 不算沒命中
        self.assertEqual(self._run("用「知道了/無奈」", "他說知道了").quote_unmatched, 0)

    def test_lookup_failure_does_not_count_quotes(self):
        """反查失敗時語料拿不到，整個引號比對要跳過而不是算成「全部沒命中」。

        不跳過的話：evidence_bogus 因為放行而是 0、quote_unmatched 卻被灌到最大，
        資料上看起來就是「證據乾淨但引文全是編的」，剛好與事實相反，
        而且會排到人工複查佇列的最前面。
        """
        def boom(sql, params):
            raise RuntimeError("pgvector 連線中斷")

        r = validation.validate_diff(
            diff([change(text="常罵「垃圾索」跟「垃圾訂閱制」")]),
            user_id=ALICE, fetch=boom,
        )
        self.assertEqual(len(r.accepted), 1, "反查失敗仍要放行，不能冤枉")
        self.assertEqual(r.evidence_bogus, 0)
        self.assertIsNone(r.quote_unmatched, "沒算就要是 None，不是 0 也不是灌大的數字")

    def test_corpus_uses_the_text_the_model_saw(self):
        """比對基準是清理後的文字——工具回給模型的就是那份。

        DB 原文是 `<@123>`，模型看到的是 `@某人`；拿原文比，模型忠實照抄也會對不上。
        """
        r = self._run("常說「叫我大哥」", "<@123456789> 叫我大哥啦")
        self.assertEqual(r.quote_unmatched, 0)

    def test_quotes_do_not_span_two_messages(self):
        """兩則證據拼接處不能湊出原本不存在的字串。"""
        r = validation.validate_diff(
            diff([change(text="說過「前半後半」", evidence_msg_ids=["m1", "m2"])]),
            user_id=ALICE,
            fetch=fetch_only({"m1", "m2"}, {"m1": "...前半", "m2": "後半..."}),
        )
        self.assertEqual(r.quote_unmatched, 1, "跨訊息拼接不算命中")

    def test_short_quotes_are_skipped(self):
        """「肥」這種 2 字以下的必然命中，沒有鑑別力，不計入。"""
        self.assertEqual(self._run("「肥」是口頭禪", "無關內容").quote_unmatched, 0)

    def test_punctuation_differences_are_ignored(self):
        self.assertEqual(
            self._run("說「我不是不爽被嘲諷，是不爽被騙」", "我不是不爽被嘲諷 是不爽被騙")
            .quote_unmatched, 0)


class DropTests(unittest.TestCase):
    """drop：刪除既有項目。不描述任何人，所以 text 與證據可空，但一定要說為什麼刪。"""

    def _run(self, changes, base_refs=None):
        return validation.validate_diff(
            diff(changes), user_id=ALICE, fetch=fetch_only({"m1"}),
            base_refs=base_refs,
        )

    def test_drop_needs_no_text_or_evidence(self):
        r = self._run([{"type": "drop", "ref": 2, "trait": "", "text": "",
                        "reason": "跟第 1 項重複", "evidence_msg_ids": []}])
        self.assertEqual(len(r.accepted), 1)
        self.assertEqual(r.rejected, [])

    def test_drop_without_reason_is_rejected(self):
        """沒理由的刪除等於又回到無聲消失。"""
        r = self._run([{"type": "drop", "ref": 2, "trait": "", "text": "",
                        "reason": "", "evidence_msg_ids": []}])
        self.assertEqual(r.accepted, [])
        self.assertIn("reason", r.rejected[0]["why"])


class RefAccountingTests(unittest.TestCase):
    """上一版每個編號都要恰好交代一次——**只記錄不擋**。

    實測米拉 v7→v8 從 51 項只帶過來 31 項，20 項無聲消失；09-22 有一版兩個 keep
    指到同一項，那一項被複製了一次。
    """

    def _acc(self, changes, base):
        return validation.validate_diff(
            diff(changes), user_id=ALICE, fetch=fetch_only({"m1"}), base_refs=base,
        ).ref_accounting

    def _k(self, ref, typ="keep"):
        return change(type=typ, ref=ref)

    def test_all_accounted(self):
        acc = self._acc([self._k(1), self._k(2, "revise"),
                         {"type": "drop", "ref": 3, "trait": "", "text": "",
                          "reason": "r", "evidence_msg_ids": []}], [1, 2, 3])
        self.assertEqual(acc, {"unaccounted": [], "duplicated": [], "unknown": [],
                               "lost": [], "superseded": []})

    def test_rejected_revise_is_counted_as_lost(self):
        """有交代、但被退件＝那一項實際消失了。只看 unaccounted 會以為沒事。"""
        acc = self._acc([self._k(1), change(type="revise", ref=2, evidence_msg_ids=["假的"])],
                        [1, 2])
        self.assertEqual(acc["unaccounted"], [], "模型有交代第 2 項")
        self.assertEqual(acc["lost"], [2], "但它被退件，實際上不見了")

    def test_rejected_drop_is_counted_as_lost(self):
        """沒附理由的 drop 被退——項目一樣消失，而且沒留下刪除理由。"""
        acc = self._acc([self._k(2),
                         {"type": "drop", "ref": 1, "trait": "", "text": "",
                          "reason": "", "evidence_msg_ids": []}], [1, 2])
        self.assertEqual(acc["lost"], [1])

    def test_lost_ignores_refs_that_survived_elsewhere(self):
        """同一個編號有一個被退、另一個通過——那一項沒有消失。"""
        acc = self._acc([self._k(1), change(type="revise", ref=1, evidence_msg_ids=["假的"])],
                        [1])
        self.assertEqual(acc["lost"], [])
        self.assertEqual(acc["duplicated"], [1])

    def test_silent_vanish_is_recorded(self):
        """沒被提到的編號＝無聲消失。"""
        acc = self._acc([self._k(1)], [1, 2, 3])
        self.assertEqual(acc["unaccounted"], [2, 3])

    def test_duplicate_ref_is_recorded(self):
        """兩個 keep 指到同一項——那一項會被複製。"""
        acc = self._acc([self._k(1), self._k(1)], [1])
        self.assertEqual(acc["duplicated"], [1])

    def test_unknown_ref_is_recorded(self):
        acc = self._acc([self._k(9)], [1])
        self.assertEqual(acc["unknown"], [9])
        self.assertEqual(acc["unaccounted"], [1])

    def test_add_does_not_count(self):
        """add 不指涉既有項目，不算交代。"""
        acc = self._acc([change(type="add", ref=0)], [1])
        self.assertEqual(acc["unaccounted"], [1])

    def test_no_base_means_no_accounting(self):
        """第一次跑以 production 散文為基準，沒有編號可對。"""
        self.assertIsNone(self._acc([self._k(1)], None))

    def test_accounting_never_rejects(self):
        """沒交代的只記錄不擋——先看遵守率再決定要不要強制（重複交代另有處理，見
        OneChangePerRefTests）。"""
        r = validation.validate_diff(
            diff([self._k(1)]), user_id=ALICE, fetch=fetch_only({"m1"}),
            base_refs=[1, 2, 3])
        self.assertEqual(len(r.accepted), 1)
        self.assertIsNone(r.skip_reason)


class DropEvidenceTests(unittest.TestCase):
    def test_drop_ids_are_not_counted_as_claimed(self):
        """drop 的 id 不反查，算進宣稱數的話幻覺率的分母會多出一批沒檢查過的 id。"""
        drop = {"type": "drop", "ref": 1, "trait": "", "text": "", "reason": "重複",
                "evidence_msg_ids": ["x", "y"]}
        r = validation.validate_diff(
            diff([drop, change()]), user_id=ALICE, fetch=fetch_only({"m1"}), base_refs=[1])
        self.assertEqual(r.evidence_claimed, 1)
        self.assertEqual(r.evidence_bogus, 0)


class OneChangePerRefTests(unittest.TestCase):
    """上一版的每一項只採用一筆變更——兩筆都寫進去，新版本就有兩條幾乎一樣的描述。

    09-25 真實案例：同一人對第 6 項同時下了 keep 和 revise，兩筆都通過驗證。
    """

    KEEP6 = {"type": "keep", "ref": 6, "trait": "AI 接梗",
             "text": "會把 AI 工具往荒謬/低俗方向接梗自嘲", "reason": "維持", "evidence_msg_ids": []}
    REVISE6 = {"type": "revise", "ref": 6, "trait": "AI 接梗",
               "text": "會把 AI 工具或遊戲角色商品往荒謬/低俗方向接梗自嘲",
               "reason": "範圍變廣", "evidence_msg_ids": ["m1"]}

    def _run(self, changes, base=(6, 7)):
        return validation.validate_diff(
            diff(changes), user_id=ALICE, fetch=fetch_only({"m1"}), base_refs=list(base))

    def test_revise_wins_over_keep(self):
        r = self._run([self.KEEP6, self.REVISE6, change(type="keep", ref=7)])
        self.assertEqual([(c["type"], c["ref"]) for c in r.accepted],
                         [("revise", 6), ("keep", 7)])
        superseded = r.ref_accounting["superseded"]
        self.assertIn("重複交代", superseded[0]["why"])
        self.assertIn("沒有附證據", superseded[0]["why"], "沒東西可併就不能寫成「證據併入」")
        self.assertEqual(superseded[0]["change"]["type"], "keep")
        self.assertEqual(r.rejected, [], "沒有驗證失敗——退件數只算驗證失敗")

    def test_item_is_not_counted_as_lost(self):
        """被擋下的是重複的那筆，那一項本身還在——不能記成消失。"""
        r = self._run([self.KEEP6, self.REVISE6, change(type="keep", ref=7)])
        self.assertEqual(r.ref_accounting["lost"], [])
        self.assertEqual(r.ref_accounting["duplicated"], [6], "重複照樣記錄")

    def test_conflicts_keep_the_content(self):
        """衝突時寧可保留內容：keep 勝過 drop；同類型取第一筆。"""
        drop6 = {"type": "drop", "ref": 6, "trait": "", "text": "", "reason": "重複",
                 "evidence_msg_ids": []}
        r = self._run([drop6, self.KEEP6])
        self.assertEqual([c["type"] for c in r.accepted], ["keep"])
        r = self._run([self.REVISE6, dict(self.REVISE6, text="第二筆 revise")])
        self.assertEqual([c["text"] for c in r.accepted], [self.REVISE6["text"]])

    def test_revise_takes_tonights_evidence_from_the_losing_keep(self):
        """同一晚又 keep 又 revise＝模型認為原句還成立，revise 是在補充。

        真實案例（米拉 v10 第 25 項）：revise 的新句引用「黑料一堆低能台V」，revise 自己
        附的證據撐不住；撐它的那則附在同一晚的 keep 上——不併的話引號對不上自己的證據。
        """
        keep = dict(self.KEEP6, evidence_msg_ids=["m2"])
        revise = dict(self.REVISE6, text="慣用「低能」貶稱台V（「黑料一堆低能台V」）",
                      evidence_msg_ids=["m1"])
        r = validation.validate_diff(
            diff([keep, revise]), user_id=ALICE,
            fetch=fetch_only({"m1", "m2"}, {"m2": "黑料一堆低能台V"}), base_refs=[6])
        self.assertEqual([c["type"] for c in r.accepted], ["revise"])
        self.assertEqual(r.accepted[0]["evidence_msg_ids"], ["m1", "m2"])
        self.assertEqual(r.quote_misses, [], "併進來的證據撐得住引號")

    def test_duplicate_keeps_merge_their_evidence(self):
        """真實案例：第 9 項下了兩次 keep，第二筆附了 09-20 的新發言當補充證據。
        兩筆說的是同一句話——丟掉第二筆的話，那則新證據跟著不見、last_seen 停在舊日期。"""
        first = dict(self.KEEP6, evidence_msg_ids=["m1"])
        second = dict(self.KEEP6, reason="作為補充證據", evidence_msg_ids=["m2", "m1"])
        r = validation.validate_diff(
            diff([first, second]), user_id=ALICE, fetch=fetch_only({"m1", "m2"}),
            base_refs=[6])
        self.assertEqual(len(r.accepted), 1)
        self.assertEqual(r.accepted[0]["evidence_msg_ids"], ["m1", "m2"])
        self.assertEqual(r.rejected, [], "內容沒有少，不算退件")
        self.assertEqual(r.ref_accounting["duplicated"], [6], "重複照樣記錄")
        merged = r.ref_accounting["superseded"]
        self.assertEqual(merged[0]["change"]["reason"], "作為補充證據",
                         "併掉那筆的 reason 要查得到")

    def test_superseded_keep_keeps_its_stripped_ids_on_record(self):
        """併掉的那筆若有被剔除的假 id，稽核時要查得到是哪個。"""
        first = dict(self.KEEP6, evidence_msg_ids=["m1"])
        second = dict(self.KEEP6, evidence_msg_ids=["假的", "m2"])
        r = validation.validate_diff(
            diff([first, second]), user_id=ALICE, fetch=fetch_only({"m1", "m2"}),
            base_refs=[6])
        self.assertEqual(r.evidence_bogus, 1)
        self.assertEqual(r.ref_accounting["superseded"][0]["change"]["stripped_msg_ids"], ["假的"])

    def test_superseded_revise_quotes_are_not_counted(self):
        """落選的 revise 不會寫入，它的引號對不上也不該算進統計。"""
        second = dict(self.REVISE6, text="引用「根本沒講過的一句話」")
        r = self._run([self.REVISE6, second])
        self.assertEqual(r.quote_unmatched, 0)
        self.assertEqual(r.quote_misses, [])

    def test_adds_are_never_merged(self):
        """add 沒有指涉既有項目，兩筆 add 是兩個不同的新特徵。"""
        r = self._run([change(type="add", ref=0), change(type="add", ref=0, trait="另一個")])
        self.assertEqual(len(r.accepted), 2)


class AnchoredKeepTests(unittest.TestCase):
    """指到上一版真實項目的 keep：文字、trait、證據都由程式沿用，不再逼模型重附證據。

    舊規則逼模型二選一，兩條路都錯：老實留空 → 被退件、項目無聲消失；
    從本週訊息湊幾則沾邊的 → 過關，但證據撐不住描述，看起來像幻覺。
    下面的 reason 是 09-24 真實被退掉的 keep 原文。
    """

    HONEST = {
        "type": "keep", "ref": 1, "trait": "6+5口頭禪",
        "text": "「6+5」是口頭禪，且幾乎都用在「汐的隊友」身上",
        "reason": "本週發言未出現「6+5」口頭禪，無反證亦無正證，保守保留，信心降為 medium。",
        "evidence_msg_ids": [],
    }

    def _run(self, changes, base_refs=(1, 2), known=("m1",)):
        return validation.validate_diff(
            diff(changes), user_id=ALICE, fetch=fetch_only(set(known)),
            base_refs=list(base_refs) if base_refs is not None else None,
        )

    def test_honest_keep_without_evidence_survives(self):
        """真實案例：模型說「保守保留」卻因為沒附證據被退——這一項不該消失。"""
        r = self._run([self.HONEST])
        self.assertEqual(r.rejected, [])
        self.assertEqual(len(r.accepted), 1)
        self.assertEqual(r.ref_accounting["lost"], [])

    def test_keep_needs_no_reason_or_trait(self):
        """keep 只是在說「這項不動」——理由和 trait 空著也不能讓項目消失。"""
        r = self._run([{**self.HONEST, "reason": "", "trait": ""}])
        self.assertEqual(len(r.accepted), 1)

    def test_bogus_new_id_is_stripped_not_fatal(self):
        """keep 多附了一個抄錯的 id：剔掉那個 id，項目留著，假 id 照樣記進幻覺率。"""
        r = self._run([{**self.HONEST, "evidence_msg_ids": ["m1", "155000042933058"]}])
        self.assertEqual(r.rejected, [], "項目沒被退，不可以算進退件數")
        self.assertEqual(r.accepted[0]["evidence_msg_ids"], ["m1"])
        self.assertEqual(r.accepted[0]["stripped_msg_ids"], ["155000042933058"],
                         "剔掉的是哪個 id 要查得到，不能只剩一個數字")
        self.assertEqual(r.evidence_bogus, 1)
        self.assertEqual(r.evidence_claimed, 2)

    def test_clean_keep_has_no_stripped_field(self):
        r = self._run([{**self.HONEST, "evidence_msg_ids": ["m1"]}])
        self.assertNotIn("stripped_msg_ids", r.accepted[0])

    def test_unverifiable_new_ids_on_keep_are_not_kept(self):
        """反查失敗時其他項目 fail-open，但 keep 不收沒驗過的 id：沿用的證據會永遠留下去。"""
        def broken(sql, params):
            raise RuntimeError("db down")
        r = validation.validate_diff(
            diff([{**self.HONEST, "evidence_msg_ids": ["1" + "0" * 22]}]),
            user_id=ALICE, fetch=broken, base_refs=[1, 2])
        self.assertEqual(len(r.accepted), 1, "keep 照樣保留")
        self.assertEqual(r.accepted[0]["evidence_msg_ids"], [])

    def test_no_version_written_means_nothing_lost(self):
        """不寫新版本時上一版原封不動——lost 照算的話 confidence=low 那幾晚會高估。"""
        bad_revise = change(type="revise", ref=2, evidence_msg_ids=["假的"])
        low = validation.validate_diff(
            diff([self.HONEST, bad_revise], confidence="low"),
            user_id=ALICE, fetch=fetch_only({"m1"}), base_refs=[1, 2])
        self.assertIsNotNone(low.skip_reason)
        self.assertEqual(low.ref_accounting["lost"], [])
        none_passed = validation.validate_diff(
            diff([bad_revise]), user_id=ALICE, fetch=fetch_only({"m1"}), base_refs=[1, 2])
        self.assertIn("沒有任何一項", none_passed.skip_reason)
        self.assertEqual(none_passed.ref_accounting["lost"], [])
        written = validation.validate_diff(
            diff([self.HONEST, bad_revise]),
            user_id=ALICE, fetch=fetch_only({"m1"}), base_refs=[1, 2])
        self.assertEqual(written.ref_accounting["lost"], [2], "有寫新版本時才是真的消失")

    def test_keep_quotes_are_not_counted(self):
        """keep 的文字是沿用的原文、證據多半沒重附——拿空證據比對會把每個引號算成沒命中。"""
        r = self._run([self.HONEST])
        self.assertEqual(r.quote_unmatched, 0)

    def test_unanchored_keep_still_needs_evidence(self):
        """ref 對不上（第一次跑、基準是 production 的散文）：文字是模型寫的，照舊要證據。"""
        for base in (None, (5,)):
            r = self._run([self.HONEST], base_refs=base)
            self.assertEqual(r.accepted, [], f"base_refs={base!r}")
            self.assertIn("evidence_msg_ids 為空", r.rejected[0]["why"])

    def test_add_and_revise_still_need_evidence(self):
        """放寬只給 keep：新寫的文字沒有證據一樣不收。"""
        for typ, ref in (("add", 0), ("revise", 1)):
            r = self._run([change(type=typ, ref=ref, evidence_msg_ids=[])])
            self.assertEqual(r.accepted, [], typ)

    def test_add_with_bogus_id_is_still_rejected(self):
        """剔除假 id 只給 keep——新寫的描述引了假 id，整項照舊退掉。"""
        r = self._run([change(type="add", ref=0, evidence_msg_ids=["m1", "假的"])])
        self.assertEqual(r.accepted, [])
        self.assertIn("不存在或不屬於本人", r.rejected[0]["why"])


if __name__ == "__main__":
    unittest.main()