"""別的伺服器的表情與貼圖給模型看圖（llm/preprocess/external_emoji.py）與共用圖片下載。

守的底線：
- 只處理別的伺服器的：表情名稱不在字典、貼圖不在本伺服器快取；本伺服器的不下載（描述由管理員維護）
- Lottie 動態貼圖沒有圖檔，跳過；每則最多 2 張
- 下載失敗或沒有對象時什麼都不加，不擋回覆；沒有對象時完全不連網
- 插話（最新那則、被回覆的那則）與 /askai 都有接上

執行：
    cd src && python -m unittest test.test_external_emoji -v
"""

import asyncio
import base64
import inspect
import os
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from llm.preprocess import emoji_dictionary as ed  # noqa: E402
from llm.preprocess import external_emoji as xe  # noqa: E402
from llm.preprocess import vision_image  # noqa: E402

KNOWN = {"frog_angry": ed.EmojiEntry("frog_angry", "生氣", "negative"),
         "pending": ed.EmojiEntry("pending", "", None)}


def sticker(sid, name, fmt="png"):
    return SimpleNamespace(id=sid, name=name, format=SimpleNamespace(name=fmt),
                           url=f"https://media.discordapp.net/stickers/{sid}.{fmt}")


class TargetTests(unittest.TestCase):
    def targets(self, text, stickers=(), known_stickers=()):
        with mock.patch.object(ed, "entries", return_value=KNOWN), \
             mock.patch.object(xe.sticker_cache, "is_known", side_effect=lambda sid: sid in known_stickers):
            return xe._targets(text, stickers)

    def test_only_other_servers(self):
        got = self.targets("<:frog_angry:1> <:pending:2> <a:worryWDYM:3>",
                           [sticker(10, "NanaSussy"), sticker(11, "貓咪哭哭")], known_stickers={11})
        self.assertEqual(got, [("表情 :worryWDYM:", "https://cdn.discordapp.com/emojis/3.gif"),
                               ("貼圖「NanaSussy」", "https://media.discordapp.net/stickers/10.png")])

    def test_lottie_stickers_have_no_picture(self):
        self.assertEqual(self.targets("", [sticker(12, "動態", fmt="lottie")]), [])


class ContextTests(unittest.TestCase):
    def run_context(self, text, stickers=(), download=None):
        download = download or mock.AsyncMock(side_effect=lambda session, urls, limit: [f"img:{urls[0]}"])
        with mock.patch.object(ed, "entries", return_value=KNOWN), \
             mock.patch.object(xe.sticker_cache, "is_known", return_value=False), \
             mock.patch.object(xe, "download_images", download):
            return asyncio.run(xe.external_emoji_context(text, stickers, session=object())), download

    def test_note_and_images(self):
        (notes, images), _ = self.run_context("<:worryWDYM:3>", [sticker(10, "NanaSussy")])
        self.assertEqual(notes, ["（附圖：別的伺服器的表情 :worryWDYM:、貼圖「NanaSussy」）"])
        self.assertEqual(len(images), 2)

    def test_at_most_two(self):
        (_, images), _ = self.run_context("<:a1:1> <:a2:2> <:a3:3>")
        self.assertEqual(len(images), xe.MAX_IMAGES)

    def test_failed_download_adds_nothing(self):
        (out, _) = self.run_context("<:worryWDYM:3>", download=mock.AsyncMock(return_value=[]))
        self.assertEqual(out, ([], []))

    def test_nothing_to_show_never_touches_the_network(self):
        (out, download) = self.run_context("<:frog_angry:1> 普通的話")
        self.assertEqual(out, ([], []))
        download.assert_not_called()
        # 呼叫端沒給連線時（/askai、插話都是）：連線都不該開
        import aiohttp
        with mock.patch.object(ed, "entries", return_value=KNOWN), \
             mock.patch.object(aiohttp, "ClientSession") as opened:
            asyncio.run(xe.external_emoji_context("<:frog_angry:1> 普通的話"))
        opened.assert_not_called()


class _Resp:
    def __init__(self, status, body):
        self.status, self.body = status, body

    async def read(self):
        return self.body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class DownloadTests(unittest.TestCase):
    def test_skips_failures_and_respects_limit(self):
        pages = {"ok1": _Resp(200, b"a"), "bad": _Resp(404, b""), "big": _Resp(200, b"x" * 20), "ok2": _Resp(200, b"b"),
                 "ok3": _Resp(200, b"c")}
        session = SimpleNamespace(get=lambda url, timeout=None: pages[url])
        got = asyncio.run(vision_image.download_images(session, ["ok1", "bad", "big", "ok2", "ok3"],
                                                       limit=2, max_bytes=10))
        self.assertEqual(got, [base64.b64encode(b"a").decode(), base64.b64encode(b"b").decode()],
                         "失敗、太大的跳過，最多 limit 張")


class WiredInTests(unittest.TestCase):
    def test_ambient_and_askai_use_it(self):
        from llm.ambient import ambient_reply
        media = inspect.getsource(ambient_reply._media_context)
        self.assertIn("expand_tweets(content)", media)
        self.assertIn("external_emoji_context(content", media)
        main = inspect.getsource(ambient_reply._run_one_ambient_pass)
        self.assertIn("await _media_context(replied_msg)", main)
        self.assertIn("await _media_context(message)", main)
        with open(os.path.join(SRC_DIR, "commands", "llm_commands.py"), encoding="utf-8") as f:
            askai = f.read()
        self.assertIn("await external_emoji_context(question)", askai)


if __name__ == "__main__":
    unittest.main()
