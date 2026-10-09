"""Discord 長訊息切段（`utils.discord_content.split_message`）：Telegram 轉發的長貼文、/askai 的長回答共用。

守的底線：
  - 放得下就不切；切了每段不超過上限，內容一個字都不丟（只去掉切點兩側的空白）
  - 優先在換行切，其次空白，都太靠前才硬切（不切出過短的碎段）
  - 暴雷標記 `||` 不會被切壞：跨切點的暴雷段，前段補收尾、下段補開頭
  - 守衛：別處自己寫切段函式會被擋

執行：
    cd src && python -m unittest test.test_split_message -v
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from test.test_shared_conventions import _find_message_splitters  # noqa: E402
from utils.discord_content import DISCORD_MESSAGE_LIMIT, split_message  # noqa: E402


def joined(chunks):
    return "".join(chunks).replace("\n", "").replace(" ", "")


class SplitMessageTests(unittest.TestCase):
    def test_short_text_is_left_alone(self):
        self.assertEqual(split_message("短短一句"), ["短短一句"])
        self.assertEqual(DISCORD_MESSAGE_LIMIT, 2000)

    def test_long_text_is_split_without_losing_anything(self):
        text = "\n".join(f"第{i}行：" + "內容" * 20 for i in range(40))
        chunks = split_message(text, 300)

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(c) <= 300 for c in chunks))
        self.assertEqual(joined(chunks), joined([text]))

    def test_prefers_line_breaks_then_spaces(self):
        by_line = split_message("甲" * 150 + "\n" + "乙" * 150, 200)
        self.assertEqual(by_line, ["甲" * 150, "乙" * 150])
        by_space = split_message("甲" * 150 + " " + "乙" * 150, 200)
        self.assertEqual(by_space, ["甲" * 150, "乙" * 150])
        hard = split_message("甲" * 450, 200)
        self.assertEqual([len(c) for c in hard], [200, 200, 50])

    def test_spoiler_marks_are_rebalanced_across_the_cut(self):
        chunks = split_message("前言\n||" + "雷" * 150 + "\n" + "雷" * 150 + "||", 200)

        self.assertEqual(len(chunks), 2)
        for chunk in chunks:
            self.assertEqual(chunk.count("||") % 2, 0, chunk)
        self.assertTrue(chunks[1].startswith("||"))


class GuardTests(unittest.TestCase):
    def test_handwritten_splitters_are_caught(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.py"
            path.write_text("def _split_text(t, n):\n    pass\n\ndef split_reply_message(t):\n    pass\n\n"
                            "def splitter():\n    pass\n", encoding="utf-8")
            self.assertEqual(_find_message_splitters(path), [1, 4])


if __name__ == "__main__":
    unittest.main()
