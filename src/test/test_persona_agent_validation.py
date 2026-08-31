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


if __name__ == "__main__":
    unittest.main()