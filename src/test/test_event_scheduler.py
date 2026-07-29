"""活動排程規劃層（event_scheduler.plan_events / is_umbrella_title）單元測試。

只測純邏輯：總表公告收斂、指紋基準、描述連結。不碰 discord / db
（event_scheduler 的 discord 相依只在 maybe_schedule_events 內 lazy import）。

執行：
    cd src && python -m unittest test.test_event_scheduler -v
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from datetime import datetime, timezone

from services.event_time_parser import parse_events, SERVER_TZ
from services.event_scheduler import plan_events, is_umbrella_title

NOW = datetime(2026, 7, 29, 3, 0, tzinfo=timezone.utc)
POST = datetime(2026, 7, 29, 11, 10, tzinfo=SERVER_TZ)

UMBRELLA_TITLE = "【3.5版本】[角色/武器活動喚取・第二期]"

# article #5221 實際內文（節錄）：一則包整期兩個卡池，各自有標題行
UMBRELLA_ARTICLE = (
    "[飛星自春天啟航]角色活動喚取\n"
    "活動期間，5星角色「愛彌斯」、4星角色「白芷」、「莫特斐」、「燈燈」喚取機率限時提升！\n"
    "✦活動時間✦\n2026年7月30日10:00 ~ 2026年8月19日11:59（伺服器時間）\n"
    "※更多活動詳細說明，請前往遊戲內【喚取】介面查看。\n\n"
    "「永遠的啟明星」武器活動喚取\n"
    "活動期間，5星武器「永遠的啟明星」、4星武器「奇幻變奏」、「悖論噴流」喚取機率限時提升！\n"
    "✦活動時間✦\n2026年7月30日10:00 ~ 2026年8月19日11:59（伺服器時間）\n"
)

# FB 同一期的總表貼文（首行即標題，只有一個活動時間）
UMBRELLA_FB = (
    "【3.5版本】[角色/武器活動喚取・第二期]\n"
    "「斟雨祝荷風」、「飛星自春天啟航」角色活動喚取，"
    "「棲霞飲露」、「永遠的啟明星」武器活動喚取限時開啟！\n"
    "✦活動時間：2026年7月30日10:00 ~ 2026年8月19日11:59（伺服器時間）\n"
)


def _plan(text, title, *, is_html=False, url=None):
    evs = parse_events(text, post_time=POST, is_html=is_html, fallback_title=title)
    return plan_events(evs, title=title, source="article", source_id="5221", url=url,
                       version_resolver=None, now=NOW, post_time=POST)


class UmbrellaTitleTests(unittest.TestCase):
    """總表公告判定：只認整期卡池匯總帖，不可誤傷單卡池公告。"""

    def test_detects_version_phase_posts(self):
        for t in ("【3.5版本】[角色/武器活動喚取・第二期]",
                  "【3.1版本】[角色/武器活動喚取・第一期]"):
            self.assertTrue(is_umbrella_title(t), t)

    def test_ignores_single_banner_posts(self):
        for t in ("[飛星自春天啟航]角色活動喚取",
                  "「永遠的啟明星」武器活動喚取",
                  "[浮聲沉兵]武器活動喚取——「不屈命定之冠」機率UP",
                  "[週年角色活動喚取・第二期]",
                  "[聲弦滌蕩]聲骸材料限時雙倍活動"):
            self.assertFalse(is_umbrella_title(t), t)

    def test_empty_is_not_umbrella(self):
        self.assertFalse(is_umbrella_title(""))
        self.assertFalse(is_umbrella_title(None))


class UmbrellaCollapseTests(unittest.TestCase):
    """總表公告不拆各卡池：收斂成一則、名字用貼文標題。"""

    def test_umbrella_article_collapses_to_one_event(self):
        # 內文雖有兩個卡池標題行，總表帖仍收斂成一則（各卡池另有獨立公告會自己建）
        planned = _plan(UMBRELLA_ARTICLE, UMBRELLA_TITLE)
        self.assertEqual(len(planned), 1)
        self.assertEqual(planned[0].name, UMBRELLA_TITLE)

    def test_umbrella_article_and_fb_share_fingerprint(self):
        # article（兩個時段區塊）與 FB（單一區塊）指紋須一致 → 跨來源去重擋得住
        a = _plan(UMBRELLA_ARTICLE, UMBRELLA_TITLE)
        f = _plan(UMBRELLA_FB, UMBRELLA_TITLE)
        self.assertEqual(len(f), 1)
        self.assertEqual(a[0].fingerprint, f[0].fingerprint)

    def test_non_umbrella_summary_post_still_splits(self):
        # 版本內容說明匯總帖不是總表卡池帖 → 仍逐活動拆開，不可被收斂掉
        text = (
            "[七丘氣象前沿]限時跑酷收集活動\n"
            "✦活動時間✦2026年7月30日10:00 ~ 2026年8月19日11:59（伺服器時間）\n"
            "[黎明贈禮]七日簽到活動\n"
            "✦活動時間✦2026年8月1日04:00 ~ 2026年8月20日03:59（伺服器時間）\n"
        )
        planned = _plan(text, "「暗潮將映的黎明」2.7版本內容說明")
        self.assertEqual(len(planned), 2)
        self.assertEqual(planned[0].name, "[七丘氣象前沿]限時跑酷收集活動")
        self.assertEqual(planned[1].name, "[黎明贈禮]七日簽到活動")

    def test_single_banner_post_keeps_its_own_name(self):
        text = ("活動期間，5星角色「斟雨祝荷風」、4星角色「燈燈」喚取機率限時提升！\n"
                "✦活動時間✦2026年7月30日10:00 ~ 2026年8月19日11:59（伺服器時間）")
        planned = _plan(text, "[斟雨祝荷風]角色活動喚取")
        self.assertEqual(len(planned), 1)
        self.assertEqual(planned[0].name, "[斟雨祝荷風]角色活動喚取")
        # 卡池 4 星名不可外洩到活動名/指紋
        self.assertNotIn("燈燈", planned[0].name)
        self.assertNotIn("燈燈", planned[0].fingerprint)


class DescriptionLinkTests(unittest.TestCase):
    """活動描述的「公告出處」連結。"""

    def test_uses_given_link(self):
        link = "https://discord.com/channels/1/2/3"
        planned = _plan(UMBRELLA_ARTICLE, UMBRELLA_TITLE, url=link)
        self.assertIn(f"公告出處：{link}", planned[0].description)

    def test_no_link_line_when_missing(self):
        planned = _plan(UMBRELLA_ARTICLE, UMBRELLA_TITLE, url=None)
        self.assertNotIn("公告出處", planned[0].description)
        self.assertIn("活動時間：", planned[0].description)


if __name__ == "__main__":
    unittest.main()
