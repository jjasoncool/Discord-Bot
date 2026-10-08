"""切段（`services/search/chunking.py`）：文件怎麼切成送去算向量的段落。

守的底線：
  - 每段都帶標題（巴哈回覆樓層、公告中後段常沒提主題，靠標題補上）
  - 短文（巴哈一樓多半如此）就是一段；長文照段落切，每段不超過上限太多
  - 相鄰兩段有重疊，跨在切點上的句子至少在一段裡是完整的；內文一個字都不能漏
  - 段落編號與內容 hash 固定，內容沒變就不必重算向量

執行：
    cd src && python -m unittest test.test_search_chunking -v
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from services.search.chunking import chunk_document, split_text  # noqa: E402


class ChunkingTests(unittest.TestCase):
    def test_short_floor_is_one_chunk_with_its_title(self):
        chunks = chunk_document("bahamut:1", "【攻略】深囚者攻略（2 樓）", "後面可以再打兩次", max_chars=500, overlap=80)

        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].chunk_id, "bahamut:1#0")
        self.assertEqual(chunks[0].text, "【攻略】深囚者攻略（2 樓）\n後面可以再打兩次")

    def test_long_article_splits_on_paragraphs_and_keeps_every_paragraph(self):
        paragraphs = [f"第{i}段：" + "內容" * 40 for i in range(12)]   # 每段約 85 字
        pieces = split_text("3.7 版本說明", "\n".join(paragraphs), max_chars=300, overlap=40)

        self.assertGreater(len(pieces), 2)
        for piece in pieces:
            self.assertTrue(piece.startswith("3.7 版本說明\n"))
            self.assertLessEqual(len(piece), 300 + 40 + len("3.7 版本說明\n") + 1)
        for para in paragraphs:
            self.assertTrue(any(para in piece for piece in pieces), para[:6])

    def test_neighbouring_chunks_overlap(self):
        # 每個字都不一樣，重疊才看得出來（全用同一個字的話，沒重疊也會「剛好比對得到」）
        paragraphs = ["".join(chr(0x4E00 + i * 100 + j) for j in range(90)) for i in range(6)]
        pieces = split_text("標題", "\n".join(paragraphs), max_chars=200, overlap=30)

        self.assertGreater(len(pieces), 2)
        for left, right in zip(pieces, pieces[1:]):
            tail = left.split("\n", 1)[1][-30:]
            self.assertTrue(right.split("\n", 1)[1].startswith(tail))

    def test_one_huge_paragraph_uses_a_sliding_window(self):
        body = "".join(chr(0x4E00 + i) for i in range(1000))   # 一千個不同的字、不換行
        pieces = split_text("標題", body, max_chars=300, overlap=50)

        self.assertGreater(len(pieces), 3)
        bodies = [p.split("\n", 1)[1] for p in pieces]
        joined = "".join(bodies)
        for ch in body:
            self.assertIn(ch, joined)
        for left, right in zip(bodies, bodies[1:]):
            self.assertEqual(left[-50:], right[:50])   # 視窗之間重疊 50 字

    def test_hash_changes_only_when_text_changes(self):
        a = chunk_document("ptt:1", "標題", "內容甲", max_chars=500, overlap=80)[0]
        b = chunk_document("ptt:1", "標題", "內容甲", max_chars=500, overlap=80)[0]
        c = chunk_document("ptt:1", "標題", "內容乙", max_chars=500, overlap=80)[0]

        self.assertEqual(a.text_hash, b.text_hash)
        self.assertNotEqual(a.text_hash, c.text_hash)

    def test_title_only_document_still_gets_one_chunk(self):
        self.assertEqual(split_text("只有標題", "", max_chars=500, overlap=80), ["只有標題"])


if __name__ == "__main__":
    unittest.main()
