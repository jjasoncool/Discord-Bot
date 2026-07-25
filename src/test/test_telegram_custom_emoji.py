"""apply_message_entities 自訂表情替換單元測試（純函式，不需 DB / Discord 連線）。

執行：
    cd src && python -m unittest test.test_telegram_custom_emoji -v
"""

import os
import sys
import unittest

# 讓 import 路徑指到 src/
HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from services.telegram_relay_service import apply_message_entities


def _fixed_resolver(mapping):
    """回傳一個依 document_id 對照表回傳 Discord 標記的 resolver。"""
    return lambda doc_id: mapping.get(int(doc_id))


class ApplyMessageEntitiesCustomEmojiTests(unittest.TestCase):

    def test_custom_emoji_replaced_with_markup(self):
        # "AB😀CD"：😀 在 UTF-16 offset 2、length 2
        text = "AB😀CD"
        entities = [{"type": "MessageEntityCustomEmoji", "offset": 2, "length": 2, "document_id": 1}]
        out = apply_message_entities(text, entities, resolve_emoji=_fixed_resolver({1: "<:tg_1:100>"}))
        self.assertEqual(out, "AB<:tg_1:100>CD")

    def test_surrogate_pair_emoji_offset(self):
        # 🐉 (U+1F409) 為 surrogate pair，佔 2 個 UTF-16 unit，在 offset 0
        text = "🐉X"
        entities = [{"type": "MessageEntityCustomEmoji", "offset": 0, "length": 2, "document_id": 5}]
        out = apply_message_entities(text, entities, resolve_emoji=_fixed_resolver({5: "<:d:9>"}))
        self.assertEqual(out, "<:d:9>X")

    def test_resolver_returns_none_keeps_fallback(self):
        text = "AB😀CD"
        entities = [{"type": "MessageEntityCustomEmoji", "offset": 2, "length": 2, "document_id": 1}]
        out = apply_message_entities(text, entities, resolve_emoji=_fixed_resolver({}))
        self.assertEqual(out, "AB😀CD")

    def test_missing_document_id_keeps_fallback(self):
        text = "AB😀CD"
        entities = [{"type": "MessageEntityCustomEmoji", "offset": 2, "length": 2}]
        out = apply_message_entities(text, entities, resolve_emoji=_fixed_resolver({1: "<:tg_1:100>"}))
        self.assertEqual(out, "AB😀CD")

    def test_no_resolver_keeps_fallback(self):
        text = "AB😀CD"
        entities = [{"type": "MessageEntityCustomEmoji", "offset": 2, "length": 2, "document_id": 1}]
        # resolve_emoji=None → 不替換自訂表情
        self.assertEqual(apply_message_entities(text, entities), "AB😀CD")

    def test_spoiler_and_custom_emoji_combined(self):
        # spoiler 蓋 "AB"(offset 0,len 2)、自訂表情在 😀(offset 2,len 2)，兩者 disjoint
        text = "AB😀CD"
        entities = [
            {"type": "MessageEntitySpoiler", "offset": 0, "length": 2},
            {"type": "MessageEntityCustomEmoji", "offset": 2, "length": 2, "document_id": 1},
        ]
        out = apply_message_entities(text, entities, resolve_emoji=_fixed_resolver({1: "<:tg_1:100>"}))
        self.assertEqual(out, "||AB||<:tg_1:100>CD")

    def test_multiple_custom_emoji_unsorted(self):
        # 兩個自訂表情：😀(offset 2)、😭(offset 5)；輸入順序刻意顛倒
        text = "AB😀C😭D"
        entities = [
            {"type": "MessageEntityCustomEmoji", "offset": 5, "length": 2, "document_id": 2},
            {"type": "MessageEntityCustomEmoji", "offset": 2, "length": 2, "document_id": 1},
        ]
        out = apply_message_entities(
            text, entities, resolve_emoji=_fixed_resolver({1: "<:a:1>", 2: "<:b:2>"})
        )
        self.assertEqual(out, "AB<:a:1>C<:b:2>D")

    def test_out_of_range_entity_skipped(self):
        text = "AB😀CD"
        entities = [{"type": "MessageEntityCustomEmoji", "offset": 99, "length": 2, "document_id": 1}]
        out = apply_message_entities(text, entities, resolve_emoji=_fixed_resolver({1: "<:tg_1:100>"}))
        self.assertEqual(out, "AB😀CD")

if __name__ == "__main__":
    unittest.main()
