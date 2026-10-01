"""群友的名字與 prompt 裡的「名字對照」（llm/persona/member_names.py 與白天的人物卡）。

真實案例：糯糯的伺服器暱稱「糯糯 弗糯糯」、全域名稱「一野shout死你」，群裡叫他一野；柔柔喵的
「阿喵」只在自介與印象裡有。名字只看一處，模型就對不到「一野」是誰。

守的底線：
- Discord 名字收顯示名稱、伺服器暱稱、全域名稱，不收帳號名（聊天畫面看不到）
- 主名字＝Discord 顯示名稱：人物卡標籤跟聊天行用同一個名字
- 名字對照只列這次出現、而且有其他叫法的人；其他叫法來自 Discord、自介、印象；查不到自介
  印象時仍列 Discord 的名字
- 問句裡的「一野」對得到糯糯（名字的一段或一段的開頭；不分大小寫），常見詞不會對到名字裡
  剛好含它的人
- /askai 與插話的找人查詢會帶上 Discord 名字對到的人

執行：
    cd src && python -m unittest test.test_member_names -v
"""

import contextlib
import logging
import os
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from llm.persona import member_names as mn  # noqa: E402

NUONUO = "100000000000001234"
MEOW = "200000000000004635"
SUPER = "300000000000000212"
NAMES = {
    NUONUO: ["糯糯 弗糯糯", "一野shout死你"],
    MEOW: ["❤️柔柔喵❤️-時渺"],
    SUPER: ["super"],
}


class FakeStore:
    def __init__(self, aliases=None, fail=False):
        self.aliases, self.fail = aliases or {}, fail

    def aliases_for_users(self, *, guild_id, user_ids):
        if self.fail:
            raise RuntimeError("db down")
        return {u: a for u, a in self.aliases.items() if u in user_ids}


class DiscordNamesTests(unittest.TestCase):
    def test_names_from_guild_skip_the_username(self):
        member = SimpleNamespace(id=int(NUONUO), display_name="糯糯 弗糯糯", nick="糯糯 弗糯糯",
                                 global_name="一野shout死你", name="one_shout321")
        plain = SimpleNamespace(id=int(SUPER), display_name="super", nick=None, global_name=None, name="super")
        bot = SimpleNamespace(id=9, display_name="漂泊者", nick=None, global_name=None, name="bot", bot=True)
        self.assertEqual(mn.member_names_from_guild(SimpleNamespace(members=[member, plain, bot])),
                         {NUONUO: ["糯糯 弗糯糯", "一野shout死你"], SUPER: ["super"]}, "bot 不收")

    def test_merge_splits_listed_nicknames(self):
        self.assertEqual(mn.merge_names(["❤️柔柔喵❤️-時渺"], ["柔喵, 阿喵", "阿喵", ""]),
                         ["❤️柔柔喵❤️-時渺", "柔喵", "阿喵"])

    def test_discord_names_are_never_split(self):
        """實測顯示名稱「Biboolater-只剩我沒6命愛彌斯/緋雪/心了」被拆出「緋雪」「心了」。"""
        name = "Biboolater-只剩我沒6命愛彌斯/緋雪/心了"
        self.assertEqual(mn.merge_names([name, "Biboolater"]), [name, "Biboolater"])


class MatchMembersTests(unittest.TestCase):
    def test_nickname_from_the_global_name_finds_the_person(self):
        self.assertEqual(mn.match_members(NAMES, ["一野", "最近", "幹嘛"]), [NUONUO])

    def test_case_does_not_matter(self):
        self.assertEqual(mn.match_members(NAMES, ["super"]), [SUPER])
        self.assertEqual(mn.match_members({SUPER: ["Super"]}, ["super"]), [SUPER])

    def test_decorated_names_match_by_start_but_not_by_symbol_pieces(self):
        """實測顯示名稱「Biboolater-只剩我沒6命愛彌斯/緋雪/心了」：照符號拆會拆出「緋雪」（遊戲角色），
        問「緋雪什麼時候復刻」就被當成在講他。「❤️柔柔喵❤️-時渺」去掉開頭表情才比得到「柔柔喵」。"""
        names = {"8": ["Biboolater-只剩我沒6命愛彌斯/緋雪/心了"], MEOW: ["❤️柔柔喵❤️-時渺"]}
        self.assertEqual(mn.match_members(names, ["緋雪", "復刻"]), [])
        self.assertEqual(mn.match_members(names, ["biboolater"]), ["8"])
        self.assertEqual(mn.match_members(names, ["柔柔喵"]), [MEOW])

    def test_prefix_counts_only_at_a_word_boundary(self):
        """獨立複查拿 3,408 則真實訊息試，沒看邊界時大多是誤中：「沒有」→「阿夢 - 沒有傘的孩子」、
        「丹瑾」（遊戲角色）→「丹瑾偶遇全息…」、「su」「mon」→ super、Just Monika。"""
        names = {"1": ["阿夢 - 沒有傘的孩子"], "2": ["丹瑾偶遇全息辛吉勒姆"], "3": ["super"], "4": ["Just Monika"]}
        self.assertEqual(mn.match_members(names, ["沒有", "丹瑾", "su", "mon", "mo"]), [])
        self.assertEqual(mn.match_members(names, ["monika"]), ["4"], "整段相等照算")

    def test_common_words_inside_a_name_do_not_match(self):
        """「我最近很忙」這種名字裡剛好有「最近」——問句切出來的詞很雜，不能任意子字串都算。"""
        self.assertEqual(mn.match_members({"9": ["我最近很忙"]}, ["最近"]), [])
        self.assertEqual(mn.match_members({"9": ["大佬"]}, ["這個大佬好強"]), [],
                         "問句候選詞比名字長（整句也是候選）時不算——不然名字是常見詞的人每句都被點到")


class NameMapTests(unittest.TestCase):
    def test_lists_people_with_other_names_under_their_display_name(self):
        store = FakeStore({MEOW: ["柔喵, 阿喵"], NUONUO: ["我們之間沒有愛"]})
        lines = mn.name_map_lines(9, [NUONUO, MEOW, SUPER], NAMES, profile_store=store)
        self.assertEqual(lines[0], mn.NAME_MAP_HEADER)
        self.assertEqual(lines[1:], [
            "- 糯糯 弗糯糯#1234 也叫：一野shout死你、我們之間沒有愛",
            "- ❤️柔柔喵❤️-時渺#4635 也叫：柔喵、阿喵",
        ], "super 沒有別的叫法，不列")

    def test_discord_names_still_listed_when_profiles_fail(self):
        lines = mn.name_map_lines(9, [NUONUO], NAMES, profile_store=FakeStore(fail=True))
        self.assertEqual(lines[1:], ["- 糯糯 弗糯糯#1234 也叫：一野shout死你"])

    def test_nobody_with_other_names_means_no_section(self):
        self.assertEqual(mn.name_map_lines(9, [SUPER, None], NAMES, profile_store=FakeStore()), [])


class CardLabelTests(unittest.TestCase):
    """人物卡標籤跟聊天行用同一個名字：以前標籤是自介別名（「柔喵, 阿喵#4635」），聊天行是顯示名稱。"""

    @staticmethod
    def cards(display_names=None, hints=()):
        from llm.persona.persona_card_builder import build_persona_cards
        intro = {"metadata": {"profile_kind": "intro_profile", "author_id": MEOW, "alias": "柔喵, 阿喵"},
                 "source": "vector", "text": "[Intro Profile]\nalias: 柔喵, 阿喵\nbio: 喜歡鳴潮"}
        return build_persona_cards(docs=[intro], requester_user_id=None, participant_user_ids=[],
                                   intent="general", alias_hints=list(hints), max_cards=3,
                                   display_names=display_names)

    def test_display_name_is_the_label(self):
        self.assertEqual(self.cards({MEOW: "❤️柔柔喵❤️-時渺"})[0]["alias"], "❤️柔柔喵❤️-時渺")
        self.assertEqual(self.cards()[0]["alias"], "柔喵, 阿喵", "沒有 Discord 名字時用自介別名")

    def test_asking_by_intro_nickname_still_ranks_the_card(self):
        """標籤換成顯示名稱後，問「阿喵」的加分不能掉。"""
        with_hint = self.cards({MEOW: "❤️柔柔喵❤️-時渺"}, hints=["阿喵"])[0]["score"]
        without = self.cards({MEOW: "❤️柔柔喵❤️-時渺"})[0]["score"]
        self.assertEqual(with_hint - without, 20)


class _RecordingCursor:
    def __init__(self, log):
        self.log = log

    def execute(self, sql, params=None):
        self.log.append((sql, params))

    def fetchall(self):
        return []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class RetrievalLookupTests(unittest.TestCase):
    """/askai 與插話撈人物卡：問句講「一野」時，糯糯的卡要被撈出來。"""

    def test_discord_name_match_joins_the_alias_query(self):
        from llm.retrievers import context_retriever as cr
        if cr.psycopg2 is None:
            self.skipTest("需要 psycopg2")
        log = []

        @contextlib.contextmanager
        def connect():
            yield SimpleNamespace(cursor=lambda: _RecordingCursor(log))

        settings = SimpleNamespace(get_source=lambda name: SimpleNamespace(table_name="member_profiles"),
                                   physical_table=lambda table: f"data_{table}", hybrid_candidate_pool=10)
        with mock.patch.object(cr, "HYBRID_RETRIEVAL_SETTINGS", settings), \
             mock.patch.object(cr, "_pgvector_connect", connect), \
             mock.patch.object(cr, "_get_or_build_vector_index", lambda *a: None):
            cr.retrieve_rag_context_sync("一野最近在幹嘛", 9, None, [], logging.getLogger("test"), 5,
                                         member_names=NAMES)
        alias_params = [p for sql, p in log if "ILIKE ANY" in sql]
        self.assertTrue(alias_params, "別名那一路要有查")
        self.assertIn([NUONUO], alias_params[0], "Discord 名字對到的人要進找人查詢")


if __name__ == "__main__":
    unittest.main()
