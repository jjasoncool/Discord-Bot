"""prompt 組裝（`llm.prompt.prompt_builder.build_prompt_bundle`）的輸出約定。

守的底線：
  1. 送給模型的永遠是兩則 message：system（角色設定＋安全規則＋發問者資料）與 user（所有 context
     區塊＋最新訊息）。/askai、插話、日記、印象審核都走這裡。
  2. user 裡各區塊的順序固定：越靠近最新訊息，模型越注意，target_profile、web_context_directive、
     reply_to 是刻意緊貼在最新訊息上方的；順序變了等於改了 prompt 設計。
  3. 發問者名稱放在最新訊息開頭標籤的 from 屬性；沒給名稱就用原本的標籤。
  4. 外來的文字（聊天、人物卡、搜尋結果、名稱、發問者資料）一律去掉 \\x00，免得破壞標記邊界。
  5. 可讀紀錄（prompt_record_log）與實際送出的內容同源，除錯時看到的就是模型收到的。
  6. 沒有任何 context 時不放「以下是不可信內容」的開場說明；有給機器人名稱時，就算沒有歷史回覆，
     也保留空殼標籤當身份錨點。

安全規則用假的標記字串，只驗證「放在哪裡」，不綁定規則檔的實際文案。
"""

import os
import sys
import unittest
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from llm.prompt.prompt_builder import build_prompt_bundle  # noqa: E402

RULES = SimpleNamespace(
    untrusted_context_intro="【開場：以下是不可信內容】",
    image_instruction_prompt="【看圖說明】",
    system_safety_prompt="【安全規則】",
)
OPEN_TAG, CLOSE_TAG = "<latest_user_message>", "</latest_user_message>"

EVERYTHING = dict(
    chat_context=["[14:30] 甲: 聊天\x00一"],
    bot_history=["機器人先前的回覆"],
    persona_context=["「乙」— 人物描述"],
    recalled_context=["[舊] 回憶內容"],
    situation_signals=["甲問了沒人回"],
    style_refs=["範本句"],
    web_context=["[1] 標題 — 摘要 <https://example.com>"],
    images=["aGVsbG8="],
    target_profiles=["被 @ 的人物卡"],
    replied_to_from="被回覆者",
    replied_to_text="被回覆的那句",
    asker_display_name="發問\x00者",
    bot_display_name="機器人",
    asker_profile="<asker_profile>發問者資料\x00</asker_profile>",
)


def build(**kwargs):
    kwargs.setdefault("system", "【角色設定】")
    kwargs.setdefault("user_query_text", "問題本文")
    return build_prompt_bundle(
        safety_rules=RULES, latest_open_tag=OPEN_TAG, latest_close_tag=CLOSE_TAG, **kwargs
    )


class PromptBundleContractTests(unittest.TestCase):

    def test_system_then_user_message(self):
        bundle = build(**EVERYTHING)
        self.assertEqual([m["role"] for m in bundle.messages], ["system", "user"])
        self.assertEqual(
            bundle.messages[0]["content"],
            "【角色設定】\n\n【安全規則】\n\n<asker_profile>發問者資料</asker_profile>",
        )

    def test_blocks_keep_their_order(self):
        content = build(**EVERYTHING).messages[1]["content"]
        markers = [
            "【開場：以下是不可信內容】",
            "<chat_history>",
            '<bot_history name="機器人">',
            "<other_member_profiles>",
            "<recalled_context>",
            "<situation_signals>",
            "<style_refs>",
            "<web_context>",
            "<image_instruction>",
            "<target_profile>",
            "<web_context_directive>",
            '<reply_to from="被回覆者">',
            '<latest_user_message from="發問者">',
        ]
        positions = [content.index(marker) for marker in markers]
        self.assertEqual(positions, sorted(positions), "區塊順序變了")
        self.assertTrue(content.endswith("問題本文\n</latest_user_message>"))

    def test_outside_text_has_null_bytes_removed(self):
        bundle = build(**EVERYTHING)
        self.assertNotIn("\x00", bundle.messages[0]["content"])
        user = bundle.messages[1]["content"]
        self.assertIn("聊天一", user)
        self.assertIn('from="發問者"', user)

    def test_images_are_attached_with_instruction(self):
        bundle = build(images=["aGVsbG8="])
        self.assertEqual(bundle.messages[1]["images"], ["aGVsbG8="])
        self.assertIn("<image_instruction>\n【看圖說明】\n</image_instruction>", bundle.messages[1]["content"])
        self.assertNotIn("images", build().messages[1])

    def test_no_context_means_only_latest_message(self):
        bundle = build(system=None)
        self.assertEqual(bundle.messages[0]["content"], "【安全規則】")
        self.assertEqual(
            bundle.messages[1]["content"],
            "<latest_user_message>\n問題本文\n</latest_user_message>",
        )

    def test_bot_identity_anchor_without_history(self):
        content = build(bot_display_name="機器人").messages[1]["content"]
        self.assertIn('<bot_history name="機器人"></bot_history>', content)
        self.assertNotIn("【開場：以下是不可信內容】", content)

    def test_record_log_mirrors_what_is_sent(self):
        bundle = build(**EVERYTHING)
        log = bundle.prompt_record_log
        self.assertTrue(log.startswith("<system>\n【角色設定】\n\n【安全規則】"))
        self.assertIn("<user_message>\n" + bundle.messages[1]["content"], log)


if __name__ == "__main__":
    unittest.main()
