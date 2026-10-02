"""X 貼文連結展開給模型看（llm/preprocess/tweet_context.py、utils/link_fix.py）。

真實案例：群友回覆 bot 轉發的 fixupx 影片說「肛塞？」，模型只看得到網址，回「你怎麼從我發的那個
連結，直接跳到肛塞了？」——其實是一支內文「Postmodern Cream Glazed Floor Vase」的花瓶影片。

守的底線：
- 認得 x.com／twitter.com，也認得 bot 自己發的 fixupx.com 等改寫網址；個人首頁不算
- 給模型看的說明有作者、內文（去掉 t.co 短網址）、影片秒數或圖片張數、敏感標記
- 影片只附縮圖、圖片每篇最多 2 張；同一篇一小時內不重查；查不到就什麼都不加
- 抽出共用查詢後，轉 fixupx 時判斷影片與否的結果跟以前一樣
- 插話與 /askai 都有接上（被回覆的訊息、最新訊息、/askai 問題）

執行：
    cd src && python -m unittest test.test_tweet_context -v
"""

import asyncio
import inspect
import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from llm.preprocess import tweet_context as tc  # noqa: E402
from utils import link_fix  # noqa: E402

VIDEO = {
    "id_str": "2105701577407205513",
    "text": "Postmodern Cream Glazed Floor Vase 😑 https://t.co/t1GESdYCPf",
    "user": {"screen_name": "BlotterMonkey", "name": "BlotterMonkey🐒"},
    "mediaDetails": [{"type": "video", "media_url_https": "https://pbs.twimg.com/thumb.jpg",
                      "video_info": {"duration_millis": 24034}}],
    "video": {"poster": "https://pbs.twimg.com/thumb.jpg"},
}
PHOTOS = {
    "id_str": "1", "text": "三張圖", "user": {"screen_name": "a", "name": "a"},
    "mediaDetails": [{"type": "photo", "media_url_https": f"https://pbs.twimg.com/p{i}.jpg"} for i in range(3)],
    "possibly_sensitive": True,
}


class _Resp:
    def __init__(self, status, data):
        self.status, self._data = status, data

    async def json(self, content_type=None):
        return self._data

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _Session:
    def __init__(self, status, data):
        self.status, self.data = status, data

    def get(self, url, timeout=None):
        return _Resp(self.status, self.data)


class LinkRecognitionTests(unittest.TestCase):
    def test_original_and_rewritten_links(self):
        text = ("https://x.com/a/status/11 https://fixupx.com/BlotterMonkey/status/2105701577407205513 "
                "https://twitter.com/b/status/11?s=20 https://x.com/a 主頁不算")
        self.assertEqual(link_fix.tweet_ids(text), ["11", "2105701577407205513"])


class ClassifyStillWorksTests(unittest.TestCase):
    """抽出 fetch_tweet 之後，轉 fixupx 的判斷不能變。"""

    def classify(self, status, data):
        return asyncio.run(link_fix._classify_tweet(_Session(status, data), "1"))

    def test_same_answers_as_before(self):
        self.assertEqual(self.classify(200, VIDEO), "video")
        only_media = {k: v for k, v in VIDEO.items() if k != "video"}   # 沒有頂層 video 欄位也要認得
        self.assertEqual(self.classify(200, only_media), "video")
        self.assertEqual(self.classify(200, PHOTOS), "non_video")
        self.assertEqual(self.classify(404, None), "not_found")
        self.assertEqual(self.classify(200, {}), "unknown")
        self.assertEqual(self.classify(503, None), "unknown")


class DescribeTests(unittest.TestCase):
    def test_video_gets_author_text_length_and_thumbnail(self):
        info = tc.parse_tweet("2105701577407205513", VIDEO)
        self.assertEqual(info.image_urls, ("https://pbs.twimg.com/thumb.jpg",))
        note = tc.describe(info, attached=1)
        self.assertIn("@BlotterMonkey", note)
        self.assertIn("Postmodern Cream Glazed Floor Vase", note)
        self.assertNotIn("t.co", note)
        self.assertIn("影片 24 秒，縮圖已附上", note)

    def test_photos_count_and_sensitive_flag(self):
        note = tc.describe(tc.parse_tweet("1", PHOTOS), attached=2)
        self.assertIn("3 張圖，附上 2 張", note)
        self.assertIn("被標為敏感內容", note)

    def test_text_only_post(self):
        note = tc.describe(tc.parse_tweet("2", {"text": "純文字", "user": {"screen_name": "c"}}), attached=0)
        self.assertEqual(note, "（X 貼文 @c：純文字）")


class ExpandTests(unittest.TestCase):
    def setUp(self):
        tc._cache.clear()
        self.addCleanup(tc._cache.clear)

    def expand(self, text, fetch_result=("ok", VIDEO)):
        fetch = mock.AsyncMock(return_value=fetch_result)
        download = mock.AsyncMock(side_effect=lambda session, urls: [f"img:{u}" for u in urls[:tc.MAX_IMAGES_PER_TWEET]])
        with mock.patch.object(tc, "fetch_tweet", fetch), mock.patch.object(tc, "_download_images", download):
            out = asyncio.run(tc.expand_tweets(text, session=object()))
        return out, fetch, download

    def test_reply_to_a_bot_repost_gets_the_post(self):
        (notes, images), _, _ = self.expand("https://fixupx.com/BlotterMonkey/status/2105701577407205513")
        self.assertEqual(len(notes), 1)
        self.assertIn("Floor Vase", notes[0])
        self.assertEqual(images, ["img:https://pbs.twimg.com/thumb.jpg"])

    def test_same_post_is_not_fetched_twice_within_the_hour(self):
        _, fetch, _ = self.expand("https://x.com/a/status/5")
        fetch2 = mock.AsyncMock(return_value=("ok", VIDEO))
        with mock.patch.object(tc, "fetch_tweet", fetch2):
            notes, _ = asyncio.run(tc.expand_tweets("https://x.com/a/status/5", session=object()))
        self.assertEqual(len(notes), 1)
        fetch2.assert_not_called()

    def test_failure_adds_nothing(self):
        (notes, images), _, _ = self.expand("https://x.com/a/status/6", fetch_result=("unknown", None))
        self.assertEqual((notes, images), ([], []))

    def test_no_link_never_touches_the_network(self):
        (notes, images), fetch, _ = self.expand("今天天氣不錯")
        self.assertEqual((notes, images), ([], []))
        fetch.assert_not_called()

    def test_photo_posts_attach_at_most_two(self):
        (_, images), _, _ = self.expand("https://x.com/a/status/7", fetch_result=("ok", PHOTOS))
        self.assertEqual(len(images), 2)


class WiredInTests(unittest.TestCase):
    """插話（被回覆的訊息、最新訊息）與 /askai 都有接上。"""

    def test_ambient_and_askai_use_it(self):
        from llm.ambient import ambient_reply
        self.assertIn("expand_tweets(content)", inspect.getsource(ambient_reply._media_context))
        src = inspect.getsource(ambient_reply._run_one_ambient_pass)
        self.assertIn("await _media_context(replied_msg)", src)
        self.assertIn("await _media_context(message)", src)
        with open(os.path.join(SRC_DIR, "commands", "llm_commands.py"), encoding="utf-8") as f:
            askai = f.read()
        self.assertIn("await expand_tweets(question)", askai)
        self.assertIn("prompt=llm_question,", askai)


if __name__ == "__main__":
    unittest.main()
