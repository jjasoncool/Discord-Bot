"""官方公告轉發 embed：內文長度與原文連結。

守的是 2026-09-22 修掉的那個洞：`article_desc` 全庫 532 篇皆為空字串，
於是「沒有摘要時取前 300 字當預覽」的 fallback 變成唯一路徑 —— 一篇 8000 字的
版本說明帖只發出前 300 字，導致自動建的活動連回來時，訊息裡一個字都沒提到那個活動。

執行：
    cd src && python -m unittest test.test_article_embed -v
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from services.article_monitor import ArticleMonitor, EMBED_DESC_LIMIT, official_article_url

LONG_BODY = "鳴潮公告內文測試段落。" * 400        # 遠超過上限
SHORT_BODY = "本次維護於 04:00 開始。"


def _article(content, article_id=5340, title="「蜃雲燈影，凡塵劍心」3.6版本內容說明"):
    return {
        "article_id": article_id,
        "article_title": title,
        "article_content": f"<div><p>{content}</p></div>",
        "article_desc": "",          # 官方實際上永遠給空字串
        "start_time": "2026-08-19 16:43:52",
    }


class ArticleEmbedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.monitor = ArticleMonitor(bot=None)

    def _embed(self, *args, **kwargs):
        return self.monitor.format_article_embed(_article(*args, **kwargs))

    # ── 長度 ──

    def test_long_article_is_not_cut_to_300(self):
        """迴歸：舊行為是無條件切 300 字，活動段落（多在第 1300 字之後）整段消失。"""
        desc = self._embed(LONG_BODY).description
        self.assertGreater(len(desc), 1000, "長公告不該再被切成 300 字")

    def test_long_article_is_capped(self):
        desc = self._embed(LONG_BODY).description
        # 內文切在上限，後面才接「閱讀完整公告」連結；總長仍遠低於 Discord 的 4096
        self.assertLess(len(desc), EMBED_DESC_LIMIT + 200)
        self.assertLess(len(desc), 4096)

    def test_truncated_article_gets_full_text_link(self):
        desc = self._embed(LONG_BODY).description
        self.assertIn("…", desc)
        self.assertIn("[閱讀完整公告 →](https://wutheringwaves.kurogames.com"
                      "/zh-tw/main/news/detail/5340)", desc)

    def test_short_article_is_intact_without_extra_link(self):
        desc = self._embed(SHORT_BODY).description
        self.assertIn(SHORT_BODY, desc)
        self.assertNotIn("閱讀完整公告", desc, "沒被截斷就不該多一行連結")

    # ── 連結出口 ──

    def test_embed_title_links_to_official_article(self):
        """對齊 fb_monitor 的 embed url=；原本只有 article 這邊漏掉，訊息變成死路。"""
        self.assertEqual(self._embed(SHORT_BODY).url,
                         "https://wutheringwaves.kurogames.com/zh-tw/main/news/detail/5340")

    def test_missing_article_id_does_not_crash(self):
        embed = self.monitor.format_article_embed(
            {"article_title": "無 id 的公告", "article_content": f"<p>{SHORT_BODY}</p>"}
        )
        self.assertIsNone(embed.url)

    def test_official_article_url_guards_empty_ids(self):
        for bad in (None, "", "unknown"):
            self.assertIsNone(official_article_url(bad))

    # ── 已移除的反向欄位 ──

    def test_no_content_preview_field(self):
        """舊的「📝 內容預覽」條件是 <=1000 字，等於文章越長看到越少，方向是反的。"""
        for body in (SHORT_BODY, LONG_BODY):
            names = [f.name for f in self._embed(body).fields]
            self.assertNotIn("📝 內容預覽", names)


if __name__ == "__main__":
    unittest.main()
