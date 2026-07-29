"""活動公告時間解析（event_time_parser）單元測試。

測資為從 articles.db / fb_posts.json 抽出的「真實鳴潮公告」片段（嵌入式，CI 不依賴 DB）。
涵蓋：① 絕對起點單事件 ② 相對起點（版本號擷取）③ 缺年補年 ④ 雙詞交集閘門
⑤ 散文「活動時間」不誤觸 ⑥ 版本內容說明匯總帖多事件 ⑦ tz 變體 / 半形空白格式
⑧ HTML strip ⑨ 跨來源指紋（同活動同指紋核心、同名不同期不同指紋）。

執行：
    cd src && python -m unittest test.test_event_time_parser -v
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from datetime import datetime
from services.event_time_parser import (
    parse_events, passes_gate, strip_html, normalize_title,
    event_fingerprint, SERVER_TZ,
)

POST = datetime(2025, 6, 25, tzinfo=SERVER_TZ)


class GateTests(unittest.TestCase):
    """雙詞交集硬閘門。"""

    def test_both_keywords_pass(self):
        self.assertTrue(passes_gate("✦活動時間✦2025年6月26日04:00 ~ 2025年7月3日03:59（伺服器時間）"))

    def test_utc8_marker_also_passes(self):
        self.assertTrue(passes_gate("活動時間：2025年5月23日00:00 ~ 2025年6月11日03:59（UTC+8）"))

    def test_missing_server_time_fails(self):
        # 有活動時間、無伺服器時間/UTC+8（MyCard 聯動類）→ 閘掉
        self.assertFalse(passes_gate("活動時間：2025/6/19 11:00 - 2025/7/23 23:59"))

    def test_missing_activity_keyword_fails(self):
        # 有伺服器時間、無活動時間（維護預告類）→ 閘掉
        self.assertFalse(passes_gate("更新維護時間：2025年6月12日04:00 ~ 11:00（UTC+8）"))


class AbsoluteSingleEventTests(unittest.TestCase):
    """絕對起點單事件（最大宗、可放心建）。"""

    def test_fb_style_single(self):
        text = "[聲弦滌蕩]聲骸材料限時雙倍活動\n✦活動時間✦\n2025年6月26日04:00 ~ 2025年7月3日03:59（伺服器時間）"
        evs = parse_events(text, post_time=POST, is_html=False, fallback_title="[聲弦滌蕩]")
        self.assertEqual(len(evs), 1)
        self.assertEqual(evs[0].start, datetime(2025, 6, 26, 4, 0, tzinfo=SERVER_TZ))
        self.assertEqual(evs[0].end, datetime(2025, 7, 3, 3, 59, tzinfo=SERVER_TZ))
        self.assertIsNone(evs[0].start_relative_version)

    def test_no_space_around_sep(self):
        text = "活動時間：2025年5月29日04:00~2025年6月11日03:59（伺服器時間）"
        evs = parse_events(text, post_time=POST)
        self.assertEqual(len(evs), 1)
        self.assertEqual(evs[0].start.day, 29)
        self.assertEqual(evs[0].end.day, 11)

    def test_slash_format_with_space(self):
        # YYYY/M/D HH:MM（日與時之間有半形空格）
        text = "活動時間：2025/6/19 11:00 ~ 2025/7/23 23:59（伺服器時間）"
        evs = parse_events(text, post_time=POST)
        self.assertEqual(len(evs), 1)
        self.assertEqual(evs[0].start, datetime(2025, 6, 19, 11, 0, tzinfo=SERVER_TZ))
        self.assertEqual(evs[0].end, datetime(2025, 7, 23, 23, 59, tzinfo=SERVER_TZ))

    def test_inline_tz_after_start(self):
        # start 自帶 (UTC+8)，end 帶（伺服器時間）
        text = "活動時間：2025年5月23日00:00 (UTC+8) ~ 2025年6月11日03:59（伺服器時間）"
        evs = parse_events(text, post_time=POST)
        self.assertEqual(len(evs), 1)
        self.assertEqual(evs[0].start, datetime(2025, 5, 23, 0, 0, tzinfo=SERVER_TZ))


class RelativeStartTests(unittest.TestCase):
    """相對起點：擷取版本號、start 留 None 交上層回填。"""

    def test_version_extracted(self):
        text = "[浮聲沉兵]武器活動喚取\n✦活動時間✦2.4版本更新後 ~ 2025年7月3日09:59（伺服器時間）"
        evs = parse_events(text, post_time=POST, fallback_title="[浮聲沉兵]")
        self.assertEqual(len(evs), 1)
        self.assertIsNone(evs[0].start)
        self.assertTrue(evs[0].is_relative_start)
        self.assertEqual(evs[0].start_relative_version, "2.4")
        self.assertEqual(evs[0].end, datetime(2025, 7, 3, 9, 59, tzinfo=SERVER_TZ))


class ImmediateAndUnknownStartTests(unittest.TestCase):
    """即日起 / 無法判定的相對起點。"""

    def test_immediate_start_flagged(self):
        text = "活動時間：即日起 ~ 2025年7月3日03:59（伺服器時間）"
        evs = parse_events(text, post_time=POST)
        self.assertEqual(len(evs), 1)
        self.assertIsNone(evs[0].start)
        self.assertTrue(evs[0].is_immediate_start)
        self.assertFalse(evs[0].is_relative_start)

    def test_version_relative_not_immediate(self):
        text = "活動時間：2.4版本更新後 ~ 2025年7月3日09:59（伺服器時間）"
        evs = parse_events(text, post_time=POST)
        self.assertTrue(evs[0].is_relative_start)
        self.assertFalse(evs[0].is_immediate_start)


class MissingYearTests(unittest.TestCase):
    """缺年格式（1.x 早期帖）→ 用貼文年份補。"""

    def test_missing_year_filled_from_post(self):
        text = "活動時間：8月13日10:00 ~ 9月28日15:59（伺服器時間）"
        evs = parse_events(text, post_time=datetime(2024, 8, 13, tzinfo=SERVER_TZ))
        self.assertEqual(len(evs), 1)
        self.assertEqual(evs[0].start.year, 2024)
        self.assertEqual(evs[0].end, datetime(2024, 9, 28, 15, 59, tzinfo=SERVER_TZ))

    def test_cross_year_rolls_end_forward(self):
        # 12 月起、隔年 1 月結束，end 缺年 → 自動 +1 年
        text = "活動時間：2024年12月25日10:00 ~ 1月5日03:59（伺服器時間）"
        evs = parse_events(text, post_time=datetime(2024, 12, 25, tzinfo=SERVER_TZ))
        self.assertEqual(len(evs), 1)
        self.assertEqual(evs[0].end.year, 2025)


class ProseNotMatchedTests(unittest.TestCase):
    """散文用法的「活動時間」不可被當錨點。"""

    def test_prose_activity_time_ignored(self):
        # 只有散文「活動時間結束後」，另含一個正規活動 → 只抓正規那個
        text = ("活動結束後將關閉，還請漂泊者注意活動時間及時參與。"
                "✦活動時間✦2025年6月26日04:00 ~ 2025年7月3日03:59（伺服器時間）")
        evs = parse_events(text, post_time=POST)
        self.assertEqual(len(evs), 1)
        self.assertEqual(evs[0].start.day, 26)


class SummaryMultiEventTests(unittest.TestCase):
    """版本內容說明匯總帖：逐活動抽出多筆。"""

    def test_multiple_events_extracted(self):
        text = (
            "✦【角色活動喚取】活動時間：2025年5月22日10:00 ~ 2025年6月11日11:59（伺服器時間）\n"
            "✦【限時探索】活動時間：2025年5月29日04:00 ~ 2025年6月11日03:59（伺服器時間）\n"
            "✦【簽到活動】活動時間：2.3版本更新後 ~ 2025年6月11日03:59（伺服器時間）"
        )
        evs = parse_events(text, post_time=datetime(2025, 4, 29, tzinfo=SERVER_TZ),
                           fallback_title="2.3版本內容說明")
        self.assertEqual(len(evs), 3)
        # 第三筆為相對起點
        self.assertTrue(evs[2].is_relative_start)
        # 每筆活動名由括號抽出，而非整篇匯總標題
        self.assertIn("角色活動喚取", evs[0].title_hint)
        self.assertIn("限時探索", evs[1].title_hint)


class HtmlStripTests(unittest.TestCase):
    """article 內文是 HTML，需先 strip。"""

    def test_html_wrapped_parses(self):
        text = ('<p><span style="color: rgb(241,196,15);">✦活動時間✦</span><br>'
                '2025年6月18日10:00 ~ 2025年7月9日11:59（伺服器時間）</p>')
        evs = parse_events(text, post_time=POST, is_html=True)
        self.assertEqual(len(evs), 1)
        self.assertEqual(evs[0].start, datetime(2025, 6, 18, 10, 0, tzinfo=SERVER_TZ))

    def test_strip_unescapes_entities(self):
        self.assertNotIn("&hellip;", strip_html("劇情<br>探索&hellip;"))


class TitleHintTests(unittest.TestCase):
    """活動名擷取：章節標題行優先，別抓到 UP 池列舉句裡的 4 星名。

    真實事故（2026-07-29，article #5221）：抓到「燈燈」「悖論噴流」兩個 4 星名當活動名。
    """

    # article #5221 實際內文（節錄；兩個卡池各一段，標題行在列舉句上方）
    GACHA_POST = (
        "[飛星自春天啟航]角色活動喚取\n"
        "活動期間，5星角色「愛彌斯」、4星角色「白芷」、「莫特斐」、「燈燈」喚取機率限時提升！\n"
        "✦活動時間✦\n2026年7月30日10:00 ~ 2026年8月19日11:59（伺服器時間）\n"
        "※更多活動詳細說明，請前往遊戲內【喚取】介面查看。\n\n"
        "「永遠的啟明星」武器活動喚取\n"
        "活動期間，5星武器「永遠的啟明星」、4星武器「奇幻變奏」、「悖論噴流」喚取機率限時提升！\n"
        "✦活動時間✦\n2026年7月30日10:00 ~ 2026年8月19日11:59（伺服器時間）\n"
    )

    def test_heading_line_beats_gacha_pool_names(self):
        evs = parse_events(self.GACHA_POST, post_time=POST,
                           fallback_title="【3.5版本】[角色/武器活動喚取・第二期]")
        self.assertEqual(len(evs), 2)
        self.assertEqual(evs[0].title_hint, "[飛星自春天啟航]角色活動喚取")
        self.assertEqual(evs[1].title_hint, "「永遠的啟明星」武器活動喚取")

    def test_pool_four_star_names_never_become_titles(self):
        hints = [e.title_hint for e in parse_events(self.GACHA_POST, post_time=POST)]
        for bad in ("燈燈", "悖論噴流", "白芷", "奇幻變奏"):
            self.assertNotIn(bad, hints)

    def test_single_event_post_falls_back_to_post_title(self):
        # 單一活動帖內文沒有標題行 → 退用貼文標題，而非列舉句裡的 4 星名
        text = ("活動期間，5星角色「斟雨祝荷風」、4星角色「白芷」、「燈燈」喚取機率限時提升！\n"
                "✦活動時間✦2026年7月30日10:00 ~ 2026年8月19日11:59（伺服器時間）")
        evs = parse_events(text, post_time=POST, fallback_title="[斟雨祝荷風]角色活動喚取")
        self.assertEqual(len(evs), 1)
        self.assertEqual(evs[0].title_hint, "[斟雨祝荷風]角色活動喚取")

    def test_cross_source_fingerprint_matches_for_single_banner(self):
        # Article（無標題行、退貼文標題） vs FB（首行即標題）→ 指紋須一致，否則重複建活動
        s = datetime(2026, 7, 30, 10, 0, tzinfo=SERVER_TZ)
        e = datetime(2026, 8, 19, 11, 59, tzinfo=SERVER_TZ)
        art = ("活動期間，5星角色「斟雨祝荷風」、4星角色「燈燈」喚取機率限時提升！\n"
               "✦活動時間✦2026年7月30日10:00 ~ 2026年8月19日11:59（伺服器時間）")
        fb = ("[斟雨祝荷風]角色活動喚取\n"
              "✦活動時間：2026年7月30日10:00 ~ 2026年8月19日11:59（伺服器時間）")
        h_art = parse_events(art, post_time=POST,
                             fallback_title="[斟雨祝荷風]角色活動喚取")[0].title_hint
        h_fb = parse_events(fb, post_time=POST,
                            fallback_title="[斟雨祝荷風]角色活動喚取")[0].title_hint
        self.assertEqual(event_fingerprint(h_art, s, e), event_fingerprint(h_fb, s, e))

    def test_time_line_never_used_as_heading(self):
        text = ("[某某活動]限時挑戰活動\n"
                "開放時間：2026年7月1日04:00 ~ 2026年7月8日03:59\n"
                "✦活動時間✦2026年7月30日10:00 ~ 2026年8月19日11:59（伺服器時間）")
        evs = parse_events(text, post_time=POST)
        self.assertEqual(evs[0].title_hint, "[某某活動]限時挑戰活動")


class FingerprintTests(unittest.TestCase):
    """跨來源活動指紋：同活動同指紋、同名不同期不同指紋。"""

    def test_same_event_same_fingerprint(self):
        s = datetime(2025, 12, 11, 10, 0, tzinfo=SERVER_TZ)
        e = datetime(2025, 12, 24, 11, 59, tzinfo=SERVER_TZ)
        # Article 標題 vs FB 內文，括號核心名相同 → 指紋核心相同
        fp_article = event_fingerprint("[卻也在風潮後輕舞]角色活動喚取——「坎特蕾拉」機率UP", s, e)
        fp_fb = event_fingerprint("✦活動時間✦「坎特蕾拉」限時喚取", s, e)
        self.assertEqual(fp_article, fp_fb)

    def test_same_name_different_period_distinct(self):
        # 「聲弦滌蕩」同名不同期 → 指紋不同（必含 start/end）
        e1 = event_fingerprint("[聲弦滌蕩]限時雙倍活動",
                               datetime(2025, 6, 26, 4, 0, tzinfo=SERVER_TZ),
                               datetime(2025, 7, 3, 3, 59, tzinfo=SERVER_TZ))
        e2 = event_fingerprint("[聲弦滌蕩]限時雙倍活動",
                               datetime(2025, 5, 1, 4, 0, tzinfo=SERVER_TZ),
                               datetime(2025, 5, 8, 3, 59, tzinfo=SERVER_TZ))
        self.assertNotEqual(e1, e2)

    def test_normalize_strips_decoration(self):
        self.assertEqual(normalize_title("✦【聲弦滌蕩】✦ 活動"),
                         normalize_title("[聲弦滌蕩]活動"))


if __name__ == "__main__":
    unittest.main()
