"""插話的語氣參考句（llm.ambient.ambient_style_lines）。

守的底線：
- 學到的句子越多，預設句越少，但一直留至少一句（群友的反應分不出語氣，全換掉會一直模仿自己）
- 只有 learned_since 之後的句子才算學到；提到群友、含數字、AI 自我話題、性話題的不重用
- 最近用過的句子先避開；句庫讀不到回 None，學到的句子讀不到只用預設句
- repo 裡的預設句庫三種語氣都有、沒有老骨架與重複句
- 開關切換的接線（off 走舊的 style_refs、on 時句庫的說明跟著句子一起進 prompt）守在 test_ambient_pass_flow

執行：
    cd src && python -m unittest test.test_ambient_style_lines -v
"""
import asyncio
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from llm.ambient import ambient_reply, ambient_style_lines
from llm.storage import ai_interactions_store
from utils import hot_files

SEEDS = [
    {"tone": "冷", "context": "抽卡連歪", "line": "錢包有托夢嗎？"},
    {"tone": "冷", "context": "嘴硬", "line": "好喔。"},
    {"tone": "暖", "context": "很累", "line": "那就先不撐。"},
    {"tone": "暖", "context": "很煩", "line": "不煩。"},
    {"tone": "逗", "context": "被誇", "line": "今天？"},
    {"tone": "逗", "context": "被撩", "line": "排隊。"},
]


async def _no_names():
    return []


class PickTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.path = self.tmp / "seed.json"
        self.fetch = mock.Mock(return_value=[])
        self.now = 1000.0
        settings = ambient_style_lines._SETTINGS.model_copy(update={"seed_lines_path": str(self.path)})
        for patcher in (
            mock.patch.object(ambient_style_lines, "_SETTINGS", settings),
            mock.patch.object(ambient_style_lines, "fetch_learned_lines", self.fetch),
            mock.patch.object(ambient_style_lines, "_learned_cache", None),
            mock.patch.object(ambient_style_lines, "_clock", lambda: self.now),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        ambient_style_lines._recent.clear()
        self.addCleanup(ambient_style_lines._recent.clear)
        self._write(SEEDS)

    def _write(self, lines, since="2026-11-05T00:00:00+08:00"):
        self.path.write_text(json.dumps({"learned_since": since, "lines": lines}, ensure_ascii=False), encoding="utf-8")
        st = self.path.stat()
        os.utime(self.path, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000))
        hot_files.forget(self.path)

    @staticmethod
    def _pick(names=_no_names):
        return asyncio.run(ambient_style_lines.pick(names))

    @staticmethod
    def _learned(lines):
        return [x for x in lines if "你之前講過" in x]

    def test_no_learned_lines_gives_one_of_each_tone(self):
        lines = self._pick()
        self.assertEqual(3, len(lines))
        joined = "".join(lines)
        for tone in ("冷", "暖", "逗"):
            self.assertTrue(any(s["line"] in joined for s in SEEDS if s["tone"] == tone), tone)

    def test_too_few_learned_lines_are_not_used_yet(self):
        self.fetch.return_value = [f"學到的第{chr(0x4e00 + i)}句" for i in range(29)]
        self.assertEqual([], self._learned(self._pick()))

    def test_seeds_fade_as_learning_grows_but_never_to_zero(self):
        self.fetch.return_value = [f"學到的第{chr(0x4e00 + i)}句" for i in range(30)]
        self.assertEqual(1, len(self._learned(self._pick())))
        ambient_style_lines._learned_cache = None
        self.fetch.return_value = [f"學到的第{chr(0x4e00 + i)}句" for i in range(500)]
        for _ in range(5):
            lines = self._pick()
            self.assertEqual(3, len(lines))
            self.assertEqual(2, len(self._learned(lines)))

    def test_nothing_counts_as_learned_before_the_since_date_is_set(self):
        self._write(SEEDS, since=None)
        self.fetch.return_value = [f"學到的第{chr(0x4e00 + i)}句" for i in range(200)]
        self.assertEqual([], self._learned(self._pick()))
        self.fetch.assert_not_called()

    def test_lines_that_would_not_travel_are_not_reused(self):
        for bad in ("180 抽全沒了", "這個 AI 很煩", "奶很大", "看 https://x.com", "太" * 41):
            self.assertFalse(ambient_style_lines._reusable(bad), bad)
        self.assertTrue(ambient_style_lines._reusable("錢包有托夢嗎？"))

    def test_unusable_lines_never_reach_the_prompt_or_count_as_learned(self):
        # 數字、AI 自我話題、性話題的句子再多，也不算學到
        self.fetch.return_value = [f"{i} 抽全沒了" for i in range(200)] + [f"這個 AI 第{chr(0x4e00 + i)}次" for i in range(200)]
        lines = self._pick()
        self.assertEqual([], self._learned(lines))
        self.assertNotIn("抽全沒了", "".join(lines))

    def test_lines_naming_a_member_are_not_reused(self):
        self.fetch.return_value = [f"糯糯第{chr(0x4e00 + i)}次" for i in range(100)]

        async def names():
            return ["糯糯"]
        self.assertEqual([], self._learned(self._pick(names)))

    def test_the_same_line_many_times_counts_once(self):
        self.fetch.return_value = ["好喔。"] * 200
        self.assertEqual([], self._learned(self._pick()))

    def test_slots_follow_what_is_left_after_the_name_filter(self):
        # 濾到剩幾句時，不該每次都塞那幾句
        self.fetch.return_value = [f"糯糯第{chr(0x4e00 + i)}次" for i in range(120)] + ["沒提到人的那句"]

        async def names():
            return ["糯糯"]
        self.assertEqual([], self._learned(self._pick(names)))

    def test_recently_used_lines_are_avoided(self):
        first = {x.split("）")[1] for x in self._pick()}
        second = {x.split("）")[1] for x in self._pick()}
        self.assertEqual(set(), first & second)

    def test_learned_lines_are_cached_and_reread_after_the_ttl(self):
        self.fetch.return_value = []
        self._pick()
        self._pick()
        self.assertEqual(1, self.fetch.call_count)
        self.now += ambient_style_lines._SETTINGS.seed_lines_learned_ttl_seconds + 1
        self._pick()
        self.assertEqual(2, self.fetch.call_count)

    def test_missing_seed_file_is_no_lines(self):
        self.path.unlink()
        hot_files.forget(self.path)
        self.assertIsNone(self._pick())


class RepoSeedFileTests(unittest.TestCase):
    """進版控的那份句庫：換人格那天才填 learned_since，填了就開始把新句子算進來。"""

    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(Path(ambient_style_lines._SETTINGS.seed_lines_path).read_text(encoding="utf-8"))
        cls.lines = [r["line"] for r in cls.data["lines"]]

    def test_every_tone_has_lines(self):
        for tone in ambient_style_lines.TONES:
            self.assertGreaterEqual(sum(r["tone"] == tone for r in self.data["lines"]), 10, tone)
        self.assertEqual(set(ambient_style_lines.TONES), {r["tone"] for r in self.data["lines"]})

    def test_no_duplicates(self):
        self.assertEqual(len(self.lines), len(set(self.lines)))

    def test_no_worn_out_shapes(self):
        # 這些骨架是實際輸出裡的罐頭，放進範例等於再教一次
        worn = re.compile(r"不叫|都.{1,6}了，|連.{1,6}都|比.{1,8}還|——|了呢")
        self.assertEqual([], [x for x in self.lines if worn.search(x)])


class LearnedLinesStoreTests(unittest.TestCase):
    def _conn(self, rows):
        self.cur = mock.MagicMock()
        self.cur.__enter__.return_value = self.cur
        self.cur.fetchall.return_value = rows
        conn = mock.MagicMock()
        conn.__enter__.return_value = conn
        conn.cursor.return_value = self.cur
        return conn

    def test_only_spontaneous_lines_that_got_a_response_and_no_complaint(self):
        with mock.patch.object(ai_interactions_store, "_get_conn", return_value=self._conn([("好喔。",)])):
            self.assertEqual(["好喔。"], ai_interactions_store.fetch_learned_lines("2026-11-05"))
        sql = self.cur.execute.call_args.args[0]
        for condition in ("directed = FALSE", "followup = FALSE", "NOT insulted", "negative_reactions = 0",
                          "positive_reactions > 0 OR got_reply", "ts >="):
            self.assertIn(condition, sql)

    def test_a_failure_comes_back_empty(self):
        with mock.patch.object(ai_interactions_store, "_get_conn", side_effect=RuntimeError("連不上")):
            with self.assertLogs("llm.storage.ai_interactions_store", "WARNING"):
                self.assertEqual([], ai_interactions_store.fetch_learned_lines("2026-11-05"))


class WiringTests(unittest.TestCase):
    def test_a_broken_pick_only_drops_the_lines(self):
        message = SimpleNamespace(guild=None, mentions=[], reference=None)
        with mock.patch.object(ambient_style_lines, "pick", mock.AsyncMock(side_effect=RuntimeError("壞了"))), \
                mock.patch.object(ambient_reply, "_mentioned_user_ids", lambda m: []):
            with self.assertLogs("llm.ambient.ambient_reply", "WARNING"):
                self.assertIsNone(asyncio.run(ambient_reply._build_style_lines(message, [1])))


if __name__ == "__main__":
    unittest.main()
