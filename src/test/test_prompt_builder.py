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
  7. 給了今天的日期，它是 user 段的第一行、在開場說明之前（system 段一變整份快取都可能重讀）；沒給就沒有這行。
  8. system 段的人設各層只有一個函式疊（`persona_system`）：身分 → 守則 → 場合規則 → 範例卡，沒給、讀不到、
     空的層略過；檔案改了下一次就生效。/askai、插話、日記都交給它。
  9. 四層一個字都沒讀到就回空字串：插話與日記因此退回各自的預設 prompt。

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

import tempfile  # noqa: E402
from pathlib import Path  # noqa: E402
from unittest import mock  # noqa: E402

from llm.prompt.prompt_builder import build_prompt_bundle, persona_system  # noqa: E402
from utils import hot_files  # noqa: E402

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
    def test_style_refs_note_replaces_the_default_when_given(self):
        # 語氣參考句來自句庫時，不能還寫「你過去講過、群裡反應不錯」；沒給就維持原本那段
        self.assertIn("反應不錯", build(**EVERYTHING).messages[1]["content"])
        replaced = build(style_refs_note="（換一段說明）", **EVERYTHING).messages[1]["content"]
        self.assertIn("（換一段說明）", replaced)
        self.assertNotIn("反應不錯", replaced)

    def test_deleted_messages_come_with_their_rules_only_when_given(self):
        user = build(deleted_messages=["[11/11 20:57] 甲#1111【已刪，發出後 2 秒刪掉】: 打錯了"]).messages[1]["content"]
        block = user.split("<deleted_messages>\n", 1)[1].split("</deleted_messages>", 1)[0]
        for rule in ("沒人問", "看前後文判斷", "不要假裝沒看到"):
            self.assertIn(rule, block)
        self.assertIn("【已刪，發出後 2 秒刪掉】: 打錯了", block)
        self.assertTrue(user.startswith(RULES.untrusted_context_intro), "只有這段時也要先講 context 不可信")
        self.assertNotIn("<deleted_messages>", build().messages[1]["content"])

    def test_today_opens_the_user_message_only_when_given(self):
        with_date = build(today="2026-10-17（星期五）", **EVERYTHING)
        user = with_date.messages[1]["content"]
        self.assertTrue(user.startswith("（今天是 2026-10-17（星期五））\n\n" + RULES.untrusted_context_intro), user[:80])
        self.assertIn("（今天是 2026-10-17（星期五））", with_date.prompt_record_log)

        without = build(**EVERYTHING)
        self.assertTrue(without.messages[1]["content"].startswith(RULES.untrusted_context_intro))


    def test_web_directive_lets_looked_up_facts_through_when_there_are_tools(self):
        """有工具（/askai 查遊戲情報）時，網路搜尋的「本規則優先」不能把查到的官方資料擋掉。"""
        plain = build(**EVERYTHING).messages[1]["content"]
        with_tools = build(**EVERYTHING, has_tools=True).messages[1]["content"]

        self.assertIn("只能用<web_context>給的 URL", plain)
        self.assertIn("只能用<web_context> 或你查到的資料給的 URL", with_tools)
        self.assertIn("不可編造<web_context> 或你查到的資料以外的數字", with_tools)

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

    def test_a_callers_own_picture_note_replaces_the_shared_instruction(self):
        content = build(images=["aGVsbG8="], image_note="第 1 張：甲貼的\x00").messages[1]["content"]
        self.assertIn("<image_instruction>\n第 1 張：甲貼的\n</image_instruction>", content)
        self.assertNotIn("【看圖說明】", content)
        self.assertNotIn("<image_instruction>", build(image_note="第 1 張：甲貼的").messages[1]["content"],
                         "沒附圖就沒有這一段")

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



class PersonaSystemTests(unittest.TestCase):
    """system 段的人設各層：層次只有一份。"""

    def setUp(self):
        self.dir = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.addCleanup(hot_files._cache.clear)

    def _file(self, name, text):
        path = self.dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def _layers(self):
        return dict(identity=self._file("identity.txt", "【身分】\n"), guardrails=self._file("guardrails.txt", "\n【守則】"),
                    rules=self._file("rules.txt", "【場合規則】"), examples=self._file("examples.txt", "【範例卡】\n\n"))

    def test_layers_are_stacked_in_one_fixed_order(self):
        self.assertEqual("【身分】\n\n【守則】\n\n【場合規則】\n\n【範例卡】", persona_system(**self._layers()))

    def test_a_layer_that_is_not_given_missing_or_empty_is_skipped(self):
        layers = self._layers()
        layers["guardrails"] = self.dir / "沒有這個檔.txt"
        layers["examples"] = None
        self._file("rules.txt", "   \n")
        self.assertEqual("【身分】", persona_system(**layers))
        self.assertEqual("", persona_system(rules=self.dir / "沒有這個檔.txt"), "全部讀不到是空字串，預設由呼叫端決定")

    def test_editing_a_layer_takes_effect_on_the_next_call(self):
        layers = self._layers()
        self.assertIn("【場合規則】", persona_system(**layers))
        path = self._file("rules.txt", "【改過的場合規則】")
        os.utime(path, ns=(path.stat().st_atime_ns, path.stat().st_mtime_ns + 1_000_000_000))
        self.assertIn("【改過的場合規則】", persona_system(**layers))


class SurfacesUseTheSharedLayersTests(unittest.TestCase):
    """/askai、插話、日記都交給同一個函式疊。"""

    def setUp(self):
        self.calls = []

        def fake(**kwargs):
            self.calls.append(kwargs)
            return "疊好的 system"

        self.fake = fake

    def test_ambient_gives_its_four_layers(self):
        from llm.ambient import ambient_reply
        with mock.patch.object(ambient_reply, "persona_system", self.fake):
            self.assertEqual("疊好的 system", ambient_reply._load_ambient_prompt())
        settings = ambient_reply._SETTINGS
        self.assertEqual(dict(identity=settings.identity_path, guardrails=settings.guardrails_path, rules=settings.prompt_path,
                              examples=settings.examples_path), self.calls[0])

    def test_the_diary_gives_no_examples(self):
        from llm.ambient import ambient_diary
        with mock.patch.object(ambient_diary, "persona_system", self.fake):
            self.assertEqual("疊好的 system", ambient_diary._load_diary_prompt())
        settings = ambient_diary._SETTINGS
        self.assertEqual(dict(identity=settings.identity_path, guardrails=settings.guardrails_path, rules=settings.prompt_path),
                         self.calls[0])

    def test_askai_gives_its_four_layers(self):
        from commands import llm_commands
        with mock.patch.object(llm_commands, "persona_system", self.fake):
            self.assertEqual("疊好的 system", llm_commands.load_system_prompt())
        self.assertEqual(dict(identity=llm_commands.IDENTITY_FILE_PATH, guardrails=llm_commands.GUARDRAILS_FILE_PATH,
                              rules=llm_commands.PROMPT_FILE_PATH, examples=llm_commands.EXAMPLES_FILE_PATH),
                         self.calls[0])

    def test_askai_uses_its_default_prompt_when_identity_and_rules_are_both_unreadable(self):
        from commands import llm_commands
        with mock.patch.object(llm_commands.hot_files, "read_text", lambda path, **_k: ""), \
                mock.patch.object(llm_commands, "persona_system", self.fake):
            self.assertEqual(llm_commands.ASKAI_SETTINGS.default_system_prompt, llm_commands.load_system_prompt())
        self.assertEqual([], self.calls)

    def test_ambient_and_diary_use_their_own_defaults_when_no_persona_file_is_readable(self):
        from llm.ambient import ambient_diary, ambient_reply
        folder = Path(self.enterContext(tempfile.TemporaryDirectory()))
        nowhere = SimpleNamespace(use_shared_identity=True, identity_path=str(folder / "沒有身分.txt"),
                                  guardrails_path=str(folder / "沒有守則.txt"), prompt_path=str(folder / "沒有規則.txt"),
                                  use_examples=True, examples_path=str(folder / "沒有範例.txt"))
        self.addCleanup(hot_files._cache.clear)
        with mock.patch.object(ambient_reply, "_SETTINGS", nowhere), mock.patch.object(ambient_diary, "_SETTINGS", nowhere):
            self.assertEqual(ambient_reply._DEFAULT_AMBIENT_PROMPT, ambient_reply._load_ambient_prompt())
            self.assertEqual(ambient_diary._DEFAULT_DIARY_PROMPT, ambient_diary._load_diary_prompt())


if __name__ == "__main__":
    unittest.main()
