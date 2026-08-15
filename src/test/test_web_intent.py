"""web 意圖偵測（should_search / classify_route）單元測試。

涵蓋：① 體育賽事報導主題群（HARD 觸發 + news/week 路由）
② 體育即時數據（賽程 / 賽果 / 比分 / 場次 → general/day，回歸實際 bug）
③ 戰績留 news/week（生涯/累計語意）、場次只進路由不進 HARD（避免誤觸）
④ 周/週 異體字容錯（SOFT 觸發）；並含既有行為回歸測試。

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

from llm.retrievers.web.intent import (
    _ROUTE_RULES,
    classify_route,
    focus_news_query,
    should_search,
)


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

    def test_sports_report_route_is_news_week(self):
        # 純「報導 / 花絮」類（無賽程 / 比分等即時數據字）仍走 news + 一週。
        self.assertEqual(classify_route("世界盃足球賽事報導"), ("news", "week", None))

    def test_bare_competition_word_does_not_trigger(self):
        # 「比賽」太泛刻意不收，避免遊戲機制類問句誤觸搜尋。
        result = should_search("這個遊戲的比賽機制怎麼設計比較好玩")
        self.assertFalse(result.triggered)


class SportsLiveDataTests(unittest.TestCase):
    """體育即時數據（賽程 / 賽果 / 比分 / 場次）→ general + 當日。

    回歸實際 bug：「查詢今天世足賽最新場次」原本被「世足」帶去 news + 一週，
    news engines 撈不到比分站 / 賽程頁，只回花絮特稿（隊醫最忙、最幸福的球迷⋯），
    答非所問。改為偵測即時數據字、優先走 general 引擎 + 當日。

    刻意排除：① 戰績——多指生涯 / 累計戰績，留 news + 一週（見 NonLiveSportsTests）；
    ② 場次只進路由不進 HARD——避免「現場 / 停車場 / 工作場 + 次X」誤觸（見
    SessionWordTriggerTests）。
    """

    def test_reported_bug_today_world_cup_schedule(self):
        # 完整重現回報 query：應 hard 觸發、走 general（categories=None）+ day。
        result = should_search("查詢今天世足賽最新場次")
        self.assertTrue(result.triggered)
        self.assertEqual(result.reason, "hard")
        self.assertIsNone(result.categories)  # → default_engines（general），非 news
        self.assertEqual(result.time_range, "day")
        # 「查詢」前綴應被剝除，主題字（含場次）保留
        self.assertIn("場次", result.cleaned_query)
        self.assertNotIn("查詢", result.cleaned_query)

    def test_live_data_words_route_general_day(self):
        # 即時數據字（不論是否帶體育主題字）一律 general + 當日。
        for q in [
            "世足賽程",        # 主題字 + 即時數據字並存：須先比中 live 規則
            "今天NBA比分",
            "英超賽果",
            "世界盃今天場次",  # 場次靠「今天 / 世界盃」觸發，再由本路由接走
        ]:
            with self.subTest(q=q):
                cat, tr, _lang = classify_route(q)
                self.assertIsNone(cat, f"{q} 不該走 news 分類")
                self.assertEqual(tr, "day", f"{q} 應限當日")

    def test_live_hard_words_still_trigger_search(self):
        # 賽程 / 賽果 / 比分 為 domain-specific live 字，仍須 HARD 觸發。
        for q in ["世足賽程", "今天比分", "世界盃賽果"]:
            with self.subTest(q=q):
                self.assertTrue(should_search(q).triggered)


class NonLiveSportsTests(unittest.TestCase):
    """戰績留在報導群（news + 一週）：中文多指生涯 / 累計戰績，非當日比分。"""

    def test_career_record_routes_news_week_not_day(self):
        # 「球員生涯戰績」「選舉戰績」是累計型，壓成單日視窗會答壞 → 維持 news/week。
        for q in ["球員生涯戰績", "選舉戰績", "中職戰績"]:
            with self.subTest(q=q):
                self.assertEqual(classify_route(q), ("news", "week", None))

    def test_record_word_still_triggers(self):
        # 路由改了但 HARD 觸發不變（戰績仍在 _TOPIC_SPORTS）。
        self.assertTrue(should_search("NBA季後賽戰績").triggered)


class SessionWordTriggerTests(unittest.TestCase):
    """場次只進路由、不進 HARD：避免跨詞界 / 一般量詞誤觸網搜。"""

    def test_bare_session_word_does_not_hard_trigger(self):
        # 中文無詞界：現場+次 / 停車場+次 / 工作場次 等不該觸發網搜。
        for q in [
            "他現場次次都遲到",
            "停車場次數用完了",
            "我的工作場次安排",
            "這場次要排哪裡比較好",
            "市場次貸危機",
        ]:
            with self.subTest(q=q):
                self.assertFalse(should_search(q).triggered, f"{q} 不該觸發網搜")

    def test_session_word_routes_general_day_when_co_triggered(self):
        # 帶其他 HARD 字（今天）時才觸發，並由 live 路由收成 general + 當日。
        result = should_search("今天電影場次")
        self.assertTrue(result.triggered)
        self.assertIsNone(result.categories)
        self.assertEqual(result.time_range, "day")


class NewsTimeRangeTests(unittest.TestCase):
    """新聞時序錨字一律 news/week——**news 路由不得使用 day**（2026-08-15 修）。

    原本「今天 / 今日 / 本日」另走 day，看起來合理但實測直接回 0 筆：
    bing news 在 day 濾鏡下拿到空 body（lxml ParserError），duckduckgo news 的
    duckduckgo_extra engine 沒宣告 time_range_support、被 SearXNG 整個跳過。
    """

    def test_today_news_routes_week_not_day(self):
        # 回歸釘樁：「今天」不能再落到 day，否則 news 引擎全滅。
        for q in ["今天新聞", "今日頭條", "本日重點新聞"]:
            with self.subTest(q=q):
                self.assertEqual(classify_route(q), ("news", "week", None))

    def test_today_plus_news_word_routes_week(self):
        self.assertEqual(classify_route("今天有什麼新聞"), ("news", "week", None))

    def test_recent_words_stay_week(self):
        # 新聞 / 最新 / 昨天 / 昨日 維持 news + 一週。
        for q in ["最新消息", "昨天的新聞", "昨日頭條", "有什麼新聞"]:
            with self.subTest(q=q):
                self.assertEqual(classify_route(q), ("news", "week", None))

    def test_today_words_still_trigger(self):
        for q in ["今天新聞", "今日頭條"]:
            with self.subTest(q=q):
                self.assertTrue(should_search(q).triggered)


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

    def test_finance_routes_news_week(self):
        # 原本斷言 day，實測 台股 day=0 / week=10、美股 day=1 / week=10 → 改 week。
        cat, tr, _lang = classify_route("台積電今天股價")
        self.assertEqual((cat, tr), ("news", "week"))

    def test_never_chitchat_not_triggered(self):
        result = should_search("早安你今天好嗎")
        self.assertFalse(result.triggered)
        self.assertEqual(result.reason, "never")

    def test_time_word_without_action_verb_not_triggered(self):
        # 「剛才」在 SOFT 但需配動作詞；翻譯請求不應觸發搜尋。
        self.assertFalse(should_search("幫我把剛才那段話翻成英文").triggered)


class NewsRouteNeverUsesDayTests(unittest.TestCase):
    """結構性釘樁：**任何** news 路由都不得帶 time_range="day"。

    逐條測「今天新聞」「台股」只擋得住已知的三條；這條掃整張路由表，
    以後新增 news 規則時手滑寫 day 也會被擋下來。day 為什麼會死見 intent.py 的 ⚠ 註解。
    """

    def test_no_news_rule_uses_day(self):
        offenders = [
            (pattern.pattern[:40], tr)
            for pattern, cat, tr, _lang in _ROUTE_RULES
            if cat == "news" and tr == "day"
        ]
        self.assertEqual(
            offenders, [],
            "news 路由不能用 time_range=day（會讓 bing news / duckduckgo news 全滅）",
        )

    def test_general_routes_may_still_use_day(self):
        # general 引擎支援 day（實測 10 筆），天氣 / 體育即時那幾條照留，不該被一起改掉。
        self.assertEqual(classify_route("今天天氣如何"), (None, "day", None))
        self.assertEqual(classify_route("今天世足賽場次"), (None, "day", None))


class NewsQueryFocusTests(unittest.TestCase):
    """新聞問句 → 關鍵字。

    news 引擎比對的是標題字面，餵整句問句不是回 0 筆就是回一堆不相關的填充頭條。
    實測（前 5 筆有幾筆真的提到主題）：剝後 7 勝 3 平 0 敗。
    """

    def test_topicless_question_falls_back_to_anchor(self):
        # 剝完沒剩主題 → 廣義錨字，否則連 general 引擎都只回得出新聞網站首頁。
        for q in [
            "今天有什麼新聞",
            "最近有什麼新聞",
            "今天的新聞",
            "有什麼新聞嗎",
            "請幫我找一下今天有什麼新聞",  # 回歸實例：實際只撈到 1 筆的那句
        ]:
            with self.subTest(q=q):
                self.assertEqual(should_search(q).cleaned_query, "台灣 新聞")

    def test_question_is_stripped_down_to_topic(self):
        # 有主題就剝成主題字本身（實測 台積電 0→5 筆相關、長榮 0→4）。
        for q, expected in [
            ("台積電最新新聞", "台積電"),
            ("美股現在如何", "美股"),
            ("鴻海最新消息", "鴻海"),
            ("台股", "台股"),
        ]:
            with self.subTest(q=q):
                self.assertEqual(should_search(q).cleaned_query, expected)

    def test_topic_survives_even_with_leftover_particles(self):
        # 殘渣可以留，主題不能掉——這是「有講到長榮」那類句子的回歸。
        cleaned = should_search("昨天的新聞有講到長榮嗎").cleaned_query
        self.assertIn("長榮", cleaned)
        self.assertNotEqual(cleaned, "台灣 新聞")

    def test_non_news_route_is_untouched(self):
        # 只對 news 路由生效；通用路由（遊戲改版）走 general 引擎，吃得下長句。
        self.assertEqual(
            should_search("鳴潮什麼時候改版").cleaned_query, "鳴潮什麼時候改版"
        )

    def test_helper_is_news_only(self):
        self.assertEqual(focus_news_query("今天有什麼新聞", None), "今天有什麼新聞")
        self.assertEqual(focus_news_query("今天有什麼新聞", "news"), "台灣 新聞")
        self.assertEqual(focus_news_query("台積電最新新聞", "news"), "台積電")


if __name__ == "__main__":
    unittest.main()
