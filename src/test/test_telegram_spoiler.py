"""apply_spoiler_entities 單元測試（純函式，不需 DB）。

執行：
    cd src && python -m pytest test/test_telegram_spoiler.py -v
或：
    cd src && python -m unittest test.test_telegram_spoiler -v
"""

import os
import sys
import unittest

# 讓 import 路徑指到 src/
HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from services.telegram_relay_service import apply_spoiler_entities


class ApplySpoilerEntitiesTests(unittest.TestCase):

    def test_returns_text_when_no_entities(self):
        self.assertEqual(apply_spoiler_entities("hello", None), "hello")
        self.assertEqual(apply_spoiler_entities("hello", []), "hello")

    def test_returns_text_when_no_spoiler_entities(self):
        entities = [{"type": "MessageEntityBold", "offset": 0, "length": 5}]
        self.assertEqual(apply_spoiler_entities("hello", entities), "hello")

    def test_single_spoiler_ascii(self):
        entities = [{"type": "MessageEntitySpoiler", "offset": 6, "length": 5}]
        result = apply_spoiler_entities("hello world!", entities)
        self.assertEqual(result, "hello ||world||!")

    def test_single_spoiler_chinese(self):
        # 中文每字佔 1 個 UTF-16 code unit（皆在 BMP 內）
        text = "明天會下雨"
        entities = [{"type": "MessageEntitySpoiler", "offset": 0, "length": 5}]
        self.assertEqual(apply_spoiler_entities(text, entities), "||明天會下雨||")

    def test_partial_chinese_spoiler(self):
        # "內鬼情報：兇手是管家" → 把「兇手是管家」（offset=5, length=5）打 spoiler
        text = "內鬼情報：兇手是管家"
        entities = [{"type": "MessageEntitySpoiler", "offset": 5, "length": 5}]
        self.assertEqual(
            apply_spoiler_entities(text, entities),
            "內鬼情報：||兇手是管家||",
        )

    def test_multiple_spoilers_disjoint(self):
        text = "AAA BBB CCC"
        entities = [
            {"type": "MessageEntitySpoiler", "offset": 0, "length": 3},
            {"type": "MessageEntitySpoiler", "offset": 8, "length": 3},
        ]
        self.assertEqual(
            apply_spoiler_entities(text, entities),
            "||AAA|| BBB ||CCC||",
        )

    def test_multiple_spoilers_unsorted_input(self):
        # 給的 entities 順序刻意亂 → 結果應跟排序後一致
        text = "AAA BBB CCC"
        entities = [
            {"type": "MessageEntitySpoiler", "offset": 8, "length": 3},
            {"type": "MessageEntitySpoiler", "offset": 0, "length": 3},
        ]
        self.assertEqual(
            apply_spoiler_entities(text, entities),
            "||AAA|| BBB ||CCC||",
        )

    def test_spoiler_with_emoji_surrogate_pair(self):
        # 😀 (U+1F600) 在 UTF-16 是 surrogate pair (length=2)
        # 文字："a😀b"  → 對 😀 設 spoiler 應 wrap 整個 surrogate pair
        text = "a😀b"
        entities = [{"type": "MessageEntitySpoiler", "offset": 1, "length": 2}]
        self.assertEqual(apply_spoiler_entities(text, entities), "a||😀||b")

    def test_mixed_entities_only_spoiler_applied(self):
        # 同時有 bold 和 spoiler，只處理 spoiler
        text = "hello world"
        entities = [
            {"type": "MessageEntityBold", "offset": 0, "length": 5},
            {"type": "MessageEntitySpoiler", "offset": 6, "length": 5},
        ]
        self.assertEqual(
            apply_spoiler_entities(text, entities),
            "hello ||world||",
        )

    def test_zero_length_spoiler_skipped(self):
        text = "hello"
        entities = [{"type": "MessageEntitySpoiler", "offset": 0, "length": 0}]
        self.assertEqual(apply_spoiler_entities(text, entities), "hello")

    def test_out_of_range_spoiler_skipped(self):
        text = "hi"
        entities = [{"type": "MessageEntitySpoiler", "offset": 0, "length": 999}]
        # 範圍超出文字 → 略過該 entity 而不是丟例外
        self.assertEqual(apply_spoiler_entities(text, entities), "hi")

    def test_malformed_entity_skipped(self):
        # 缺欄位的 entity 不應炸掉
        text = "hello"
        entities = [{"type": "MessageEntitySpoiler"}]  # 沒 offset/length
        result = apply_spoiler_entities(text, entities)
        self.assertEqual(result, "hello")

    def test_empty_text_returns_empty(self):
        entities = [{"type": "MessageEntitySpoiler", "offset": 0, "length": 0}]
        self.assertEqual(apply_spoiler_entities("", entities), "")

    def test_adjacent_spoilers(self):
        # 兩個相鄰 spoiler，中間沒空格
        text = "ABCDEF"
        entities = [
            {"type": "MessageEntitySpoiler", "offset": 0, "length": 3},
            {"type": "MessageEntitySpoiler", "offset": 3, "length": 3},
        ]
        self.assertEqual(
            apply_spoiler_entities(text, entities),
            "||ABC||||DEF||",
        )


if __name__ == "__main__":
    unittest.main()
