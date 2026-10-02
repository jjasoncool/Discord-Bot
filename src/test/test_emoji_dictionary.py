"""自訂表情字典（llm/preprocess/emoji_dictionary.py）與表情轉文字、反應分類。

守的底線：
- 使用者手改字典，**不用重啟**就生效（以前只有 04:00 偵測到新表情時才重載）
- 三個讀取者（表情轉文字、反應分類、新表情偵測）讀的是同一份解析；類別不合法時整段當描述
- 本伺服器的表情：有描述換成描述；字典有登錄但還沒填描述的照舊拿掉（管理員維護）
- 別的伺服器的表情（字典沒登錄）：保留 `:名稱:`，不然模型不知道對方回了什麼

執行：
    cd src && python -m unittest test.test_emoji_dictionary -v
"""

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from llm.preprocess import emoji_dictionary as ed  # noqa: E402
from llm.preprocess import emoji_text_utils  # noqa: E402

DICT = """# 註解
frog_angry = 生氣 | negative
LULW = 爆笑
pending =
weird = 描述 | 不是類別
"""


class DictionaryFileTestBase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name, "emoji_dictionary.txt")
        self.path.write_text(DICT, encoding="utf-8")
        patcher = mock.patch.object(ed, "EMOJI_DICT_PATH", str(self.path))
        patcher.start()
        self.addCleanup(patcher.stop)
        ed.reload()
        self.addCleanup(ed.reload)


class ParseTests(DictionaryFileTestBase):
    def test_lines(self):
        e = ed.entries()
        self.assertEqual((e["frog_angry"].description, e["frog_angry"].category), ("生氣", "negative"))
        self.assertEqual((e["LULW"].description, e["LULW"].category), ("爆笑", None))
        self.assertEqual(e["pending"].description, "", "待填的佔位也要列出（新表情偵測靠它）")
        self.assertEqual(e["weird"].description, "描述 | 不是類別", "類別不合法就整段當描述")

    def test_hand_edits_take_effect_without_restart(self):
        self.assertEqual(ed.entries()["LULW"].description, "爆笑")
        time.sleep(0.01)
        self.path.write_text(DICT.replace("LULW = 爆笑", "LULW = 笑到翻過去"), encoding="utf-8")
        os.utime(self.path, (time.time() + 5, time.time() + 5))   # 確保修改時間有變
        self.assertEqual(ed.entries()["LULW"].description, "笑到翻過去")


class EmojiTextTests(DictionaryFileTestBase):
    def test_this_server_and_other_servers(self):
        text = emoji_text_utils.replace_custom_emoji_with_description(
            "<:frog_angry:1> <:pending:2> <a:other_server:3> 好")
        self.assertEqual(text, ":生氣: :other_server: 好",
                         "有描述換描述；本伺服器待填的拿掉；別的伺服器的留名稱")

    def test_reaction_categories_follow_the_same_file(self):
        from llm.persona import reaction_classifier as rc
        cats = rc._load_custom_emoji_categories()
        self.assertEqual(cats["frog_angry"], "negative")
        self.assertIn("LULW", cats)
        self.assertNotIn("pending", cats, "還沒填描述的不分類")

    def test_new_emoji_detection_sees_placeholders(self):
        from llm.persona import personality_extractor as pe
        self.assertEqual(pe._load_all_emoji_names_from_file(), {"frog_angry", "LULW", "pending", "weird"})


if __name__ == "__main__":
    unittest.main()
