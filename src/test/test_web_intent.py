"""web 意圖偵測（should_search / classify_route）單元測試。

涵蓋本輪新增：① 體育賽事主題群（HARD 觸發 + news/week 路由）
② 周/週 異體字容錯（SOFT 觸發）；並含既有行為回歸測試。

執行：
    cd src && python -m pytest test/test_web_intent.py -v
或：
    cd src && python -m unittest test.test_web_intent -v
"""

import os
import sys
import unittest

# 讓 import 路徑指到 src/
HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from llm.retrievers.web.intent import classify_route, should_search


class SportsTriggerTests(unittest.TestCase):
    """新增的體育賽事主題群：HARD 觸發 + news/week 路由。"""

    def test_world_cup_football_briefing_triggers(self):
        # 回歸實際 bug：此題原本 triggered=False / reason=default（沒去搜尋），
        # 加了體育主題群後應 hard 觸發並走 news + week。
        result = should_search("請告訴我這周的世界足球賽比賽簡報")
        self.assertTrue(result.triggered)
        self.assertEqual(result.reason, "hard")
        self.assertEqual(result.categories, "news")
        self.assertEqual(result.time_range, "week")

    def test_various_sports_keywords_trigger(self):
        for q in [
            "世界盃賽程",
            "NBA季後賽戰績",
            "英超這輪比分",
            "中職總冠軍賽結果如何",
        ]:
            with self.subTest(q=q):
                self.assertTrue(should_search(q).triggered)

    def test_sports_route_is_news_week(self):
        self.assertEqual(classify_route("世界盃足球賽程"), ("news", "week", None))

    def test_bare_competition_word_does_not_trigger(self):
        # 「比賽」太泛刻意不收，避免遊戲機制類問句誤觸搜尋。
        result = should_search("這個遊戲的比賽機制怎麼設計比較好玩")
        self.assertFalse(result.triggered)


class WeekVariantTests(unittest.TestCase):
    """周/週 異體字容錯（SOFT 觸發）。"""

    def test_soft_trigger_with_variant_zhou(self):
        # 「周」(異體) + 動作詞，修正前對不上 SOFT 的「這週」，修正後應觸發。
        self.assertTrue(should_search("這周發生了什麼新的大事").triggered)

    def test_soft_trigger_with_standard_zhou(self):
        self.assertTrue(should_search("這週發生了什麼新的大事").triggered)

    def test_last_week_variant_zhou(self):
        # 「上周」(異體) + 動作詞「漲」，純走 SOFT（無 HARD 關鍵字）。
        result = should_search("上周房價漲了好多")
        self.assertTrue(result.triggered)
        self.assertEqual(result.reason, "soft")


class RegressionTests(unittest.TestCase):
    """既有行為不受本輪改動影響。"""

    def test_finance_still_routes_news_day(self):
        cat, tr, _lang = classify_route("台積電今天股價")
        self.assertEqual((cat, tr), ("news", "day"))

    def test_never_chitchat_not_triggered(self):
        result = should_search("早安你今天好嗎")
        self.assertFalse(result.triggered)
        self.assertEqual(result.reason, "never")

    def test_time_word_without_action_verb_not_triggered(self):
        # 「剛才」在 SOFT 但需配動作詞；翻譯請求不應觸發搜尋。
        self.assertFalse(should_search("幫我把剛才那段話翻成英文").triggered)


if __name__ == "__main__":
    unittest.main()
