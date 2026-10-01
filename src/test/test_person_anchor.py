"""prompt 裡認人的錨點「名字#尾碼」（llm/preprocess/person_anchor.py）。

守的底線：
- 沒撞號的人一律 4 碼；撞號的人自動加長到分得開為止，其他人不受影響
- 撞號的人有一人離開後，留下的人不縮回 4 碼（離開者的舊訊息還在聊天歷史裡）
- 聊天行、人物卡、招牌梗用的是同一個錨點——撞號加長時三處一起變，模型才對得上是同一個人

執行：
    cd src && python -m unittest test.test_person_anchor -v
"""

import os
import sys
import unittest
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from llm.preprocess import person_anchor  # noqa: E402

NORMAL = "380711801760907274"
A = "111111111111110001"
B = "222222222222220001"   # 跟 A 末四碼相同、末五碼不同
C = "333333333333310001"   # 跟 A、B 末五碼也相同（…10001 vs …20001 vs …10001）


class AnchorTestBase(unittest.TestCase):
    def setUp(self):
        # 加長過的人不縮回，refresh([]) 清不掉——直接換成空的一份
        self.addCleanup(setattr, person_anchor, "_extended", {})


class AnchorTests(AnchorTestBase):
    def test_default_is_four_digits(self):
        self.assertEqual(person_anchor.label("米拉", NORMAL), "米拉#7274")
        self.assertEqual(person_anchor.label("某人", "12"), "某人", "id 太短就不掛錨點")

    def test_only_colliding_people_get_longer(self):
        person_anchor.refresh([NORMAL, A, B])
        self.assertEqual(person_anchor.suffix(A), "10001")
        self.assertEqual(person_anchor.suffix(B), "20001")
        self.assertEqual(person_anchor.suffix(NORMAL), "7274", "沒撞號的人不受影響")

    def test_longer_until_everyone_is_distinct(self):
        person_anchor.refresh([A, B, C])
        tails = {person_anchor.suffix(x) for x in (A, B, C)}
        self.assertEqual(len(tails), 3)
        self.assertEqual(person_anchor.suffix(A), "110001", "A 與 C 末五碼相同，要加到六碼")

    def test_stays_longer_after_the_other_one_leaves(self):
        """複查指出：B 離開後 A 縮回 4 碼，B 還在聊天歷史裡的舊訊息也是 4 碼——兩人又變成同一個錨點。"""
        person_anchor.refresh([A, B])
        person_anchor.refresh([A])
        self.assertEqual((person_anchor.suffix(A), person_anchor.suffix(B)), ("10001", "20001"))


class SameAnchorEverywhereTests(AnchorTestBase):
    """撞號加長後，聊天行、人物卡、招牌梗那行都要一起變——只改一處，模型就對不上是同一個人。"""

    def test_chat_line_card_and_tag_line_agree(self):
        from llm.preprocess.chat_line import name_with_anchor
        from llm.persona.persona_card_builder import persona_card_label

        person_anchor.refresh([A, B])
        author = SimpleNamespace(display_name="糯糯", name="x", id=int(A))
        self.assertEqual(name_with_anchor(author), "糯糯#10001")
        self.assertEqual(persona_card_label({"alias": "糯糯", "person_id": A}), "糯糯#10001")
        self.assertEqual(person_anchor.label("", A), "#10001", "招牌梗那行只掛錨點")


if __name__ == "__main__":
    unittest.main()
