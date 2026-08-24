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


def fetch_only(known):
    """假的證據反查：只認得 `known` 這些 id。"""
    def _fetch(sql, params):
        wanted = params[1]
        return [(i,) for i in wanted if i in known]
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


if __name__ == "__main__":
    unittest.main()
