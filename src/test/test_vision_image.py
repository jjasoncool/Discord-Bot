"""vision 圖片前處理測試：動圖拆關鍵幀 + 格式降級備援 + 抓網路上的圖。

拆幀的重點不是「拆出幾張」，是**只留變化大的**——反應 gif 常常幾十幀都在原地抖，
等距抽樣會拿到一疊幾乎一樣的圖，白白吃掉 context 額度（總上限 9 張）。

抓圖守的底線：先抓 Discord 代理的縮小版、不行才抓原檔，兩邊上限都是 10 MB；代理的寬高照原圖比例、
簽章參數原樣留著；動圖給最多 4 張 PNG 關鍵幀（長邊 512），靜態圖給一張 JPEG（長邊 1280）；
兩邊都抓不到時什麼都不給、記一行 log、說得出是不是太大；解碼不在主流程上跑。

執行：
    cd src && python -m unittest test.test_vision_image -v
"""

import asyncio
import base64
import os
import sys
import threading
import unittest
from io import BytesIO
from types import SimpleNamespace
from unittest import mock
from urllib.parse import parse_qsl, urlsplit

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from llm.preprocess import vision_image
from llm.preprocess.vision_image import (
    MAX_FETCH_BYTES,
    RemoteImage,
    extract_key_frames,
    fetch_for_vision,
    fit_for_vision,
    is_universal_image,
    proxy_variant,
    remote_image,
    select_key_frames,
    to_png_first_frame,
)
from services.llm_service import _convert_messages_for_openai, _downgrade_images

try:
    from PIL import Image, ImageDraw
    HAS_PIL = True
except Exception:
    HAS_PIL = False


def _gif(colours, size=(64, 64)):
    """每幀一個純色（或 None＝白底畫個方塊）的動畫 gif。"""
    ims = []
    for c in colours:
        im = Image.new("RGB", size, "white")
        if c is not None:
            ImageDraw.Draw(im).rectangle([8, 8, size[0] - 8, size[1] - 8], fill=c)
        ims.append(im)
    buf = BytesIO()
    ims[0].save(buf, format="GIF", save_all=True, append_images=ims[1:], duration=100, loop=0)
    return buf.getvalue()


def _png(colour=(220, 30, 30)):
    buf = BytesIO()
    Image.new("RGB", (64, 64), colour).save(buf, format="PNG")
    return buf.getvalue()


@unittest.skipUnless(HAS_PIL, "需要 Pillow")
class KeyFrameTests(unittest.TestCase):
    """動圖拆幀。"""

    def test_static_image_returns_itself(self):
        data = _png()
        self.assertEqual(extract_key_frames(data, 4), [data])

    def test_changing_frames_are_kept_as_png(self):
        # 每幀顏色都不同 → 應該拆出多張，且每張都是 PNG
        data = _gif([(220, 20, 20), (20, 220, 20), (20, 20, 220), (220, 220, 20)])
        frames = extract_key_frames(data, 4)
        self.assertGreater(len(frames), 1)
        for f in frames:
            self.assertTrue(is_universal_image(f))

    def test_near_identical_frames_collapse(self):
        # 12 幀幾乎一樣 → 不該拆成 12 張（這正是等距抽樣會浪費額度的情況）
        frames = extract_key_frames(_gif([(200, 200, 200)] * 12), 9)
        self.assertLessEqual(len(frames), 2)

    def test_respects_max_frames(self):
        data = _gif([(i * 25, 255 - i * 25, 128) for i in range(10)])
        self.assertLessEqual(len(extract_key_frames(data, 3)), 3 + 1)  # +1：末幀補課

    def test_max_frames_one_returns_original(self):
        data = _gif([(220, 20, 20), (20, 220, 20)])
        self.assertEqual(extract_key_frames(data, 1), [data])

    def test_broken_bytes_return_original(self):
        junk = b"GIF89a-not-really-a-gif"
        self.assertEqual(extract_key_frames(junk, 4), [junk])


class PerImageMessageTests(unittest.TestCase):
    """多張圖必須拆成多則訊息。

    實測後端解析「單一 message 內多個 image_url」時每隔一張丟一張（prompt_tokens 只認
    ⌈n/2⌉ 張：2 張＝1 張、3 張＝2 張、6 張＝3 張）；一圖一則就完全線性。
    這是中間層的解析 bug，不是模型限制——同一個模型在多則訊息下讀得出連續幀的變化。
    """

    def test_each_image_gets_its_own_message(self):
        out = _convert_messages_for_openai(
            [{"role": "user", "content": "看這個", "images": ["A", "B", "C"]}]
        )
        image_msgs = [m for m in out if m["content"][0]["type"] == "image_url"]
        self.assertEqual(len(image_msgs), 3)
        for m in image_msgs:
            self.assertEqual(len(m["content"]), 1)   # 一則只放一張，不可合併

    def test_text_follows_the_images(self):
        out = _convert_messages_for_openai(
            [{"role": "user", "content": "看這個", "images": ["A"]}]
        )
        self.assertEqual([m["content"][0]["type"] for m in out], ["image_url", "text"])
        self.assertEqual(out[-1]["content"][0]["text"], "看這個")

    def test_message_without_images_is_untouched(self):
        msg = {"role": "user", "content": "純文字"}
        self.assertEqual(_convert_messages_for_openai([msg]), [msg])

    def test_images_without_text_produce_only_image_messages(self):
        out = _convert_messages_for_openai([{"role": "user", "content": "", "images": ["A", "B"]}])
        self.assertEqual(len(out), 2)
        self.assertTrue(all(m["content"][0]["type"] == "image_url" for m in out))


class UniversalDetectionTests(unittest.TestCase):
    """用 magic bytes 判格式，不看副檔名——到那一層副檔名已經沒了。"""

    def test_empty_is_not_universal(self):
        self.assertFalse(is_universal_image(b""))

    def test_gif_is_not_universal(self):
        self.assertFalse(is_universal_image(b"GIF89a" + b"\x00" * 10))

    @unittest.skipUnless(HAS_PIL, "需要 Pillow")
    def test_png_is_universal(self):
        self.assertTrue(is_universal_image(_png()))


class DowngradeTests(unittest.TestCase):
    """降級備援：只有「真的有非 jpeg/png 的圖」才回退，其餘回 None（呼叫端就不重試）。"""

    def test_no_images_returns_none(self):
        self.assertIsNone(_downgrade_images([{"role": "user", "content": "沒圖"}]))

    @unittest.skipUnless(HAS_PIL, "需要 Pillow")
    def test_png_only_returns_none(self):
        b64 = base64.b64encode(_png()).decode()
        self.assertIsNone(_downgrade_images([{"role": "user", "images": [b64]}]))

    @unittest.skipUnless(HAS_PIL, "需要 Pillow")
    def test_gif_is_downgraded_without_mutating_input(self):
        msgs = [{"role": "user", "content": "看圖",
                 "images": [base64.b64encode(_gif([(220, 20, 20)])).decode()]}]
        out = _downgrade_images(msgs)
        self.assertIsNotNone(out)
        self.assertTrue(is_universal_image(base64.b64decode(out[0]["images"][0])))
        self.assertEqual(out[0]["content"], "看圖")
        self.assertFalse(is_universal_image(base64.b64decode(msgs[0]["images"][0])))

    def test_unconvertible_bytes_are_left_alone(self):
        junk = b"GIF89a-not-really-a-gif"
        self.assertEqual(to_png_first_frame(junk), junk)
        self.assertIsNone(
            _downgrade_images([{"role": "user", "images": [base64.b64encode(junk).decode()]}])
        )




@unittest.skipUnless(HAS_PIL, "需要 Pillow")
class FitForVisionTests(unittest.TestCase):
    """給 vision 模型前縮圖：長邊不超過上限、一律 JPEG，打不開回 None。"""

    def test_large_image_is_downscaled_to_jpeg(self):
        buf = BytesIO()
        Image.new("RGB", (4100, 2000), (10, 200, 10)).save(buf, format="PNG")
        out = fit_for_vision(buf.getvalue(), max_side=1280)
        with Image.open(BytesIO(out)) as im:
            self.assertEqual(im.format, "JPEG")
            self.assertEqual(max(im.size), 1280)

    def test_small_image_keeps_its_size(self):
        with Image.open(BytesIO(fit_for_vision(_png(), max_side=1280))) as im:
            self.assertEqual(im.size, (64, 64))

    def test_garbage_returns_none(self):
        self.assertIsNone(fit_for_vision(b"not an image"))
        self.assertIsNone(fit_for_vision(b""))


@unittest.skipUnless(HAS_PIL, "需要 Pillow")
class SelectKeyFramesTests(unittest.TestCase):
    """挑幀規則吃一串 PIL 幀（影片解出來的畫格走這裡），跟動圖拆幀是同一套。"""

    def test_same_choice_as_gif(self):
        # 每幀都不同：第一幀一定收、隔兩幀才收下一張、末幀補課 → [0, 2, 3]，跟同樣內容的 GIF 拆幀一致
        colours = [(220, 20, 20), (20, 220, 20), (20, 20, 220), (220, 220, 20)]
        frames = [Image.new("RGB", (64, 64), c) for c in colours]
        _, indices = select_key_frames(iter(frames), 4)
        self.assertEqual(indices, [0, 2, 3])
        self.assertEqual(len(extract_key_frames(_gif(colours), 4)), len(indices))

    def test_identical_last_frame_is_not_added_again(self):
        # 影片只有一個關鍵畫格時，解出來的每一格都一樣：末幀補課不能再補一張一樣的
        frames = [Image.new("RGB", (64, 64), (40, 40, 40)) for _ in range(5)]
        _, indices = select_key_frames(iter(frames), 4)
        self.assertEqual(indices, [0])

    def test_single_slot_keeps_only_the_first_frame(self):
        frames = [Image.new("RGB", (64, 64), c) for c in [(220, 20, 20), (20, 220, 20), (20, 20, 220)]]
        kept, indices = select_key_frames(iter(frames), 1)
        self.assertEqual(indices, [0])
        self.assertEqual(select_key_frames(iter(frames), 0), ([], []))

    def test_stops_reading_when_full(self):
        consumed = []

        def frames():
            for n in range(40):
                consumed.append(n)
                yield Image.new("RGB", (64, 64), ((n * 60) % 256, (n * 110) % 256, (n * 170) % 256))
        kept, _ = select_key_frames(frames(), 3)
        self.assertEqual(len(kept), 3)
        self.assertLess(len(consumed), 40, "名額滿了就不再往下解")


# ── 抓網路上的圖：先代理的縮小版、不行才抓原檔 ──

PROXY = "https://media.discordapp.net/attachments/1/2/a.gif?ex=1&is=2&hm=3&"
ORIGINAL = "https://cdn.discordapp.com/attachments/1/2/a.gif?ex=1&is=2&hm=3&"


def _image(**changes):
    fields = dict(proxy_url=PROXY, url=ORIGINAL, width=None, height=None, animated=False)
    fields.update(changes)
    return RemoteImage(**fields)


def _params(url):
    return dict(parse_qsl(urlsplit(url).query))


class ProxyVariantTests(unittest.TestCase):
    """向代理要的縮小版網址。"""

    def test_animated_asks_for_moving_webp_512_on_the_long_side(self):
        url = proxy_variant(_image(width=1024, height=760, animated=True))
        p = _params(url)
        self.assertEqual((p["format"], p["animated"], p["width"], p["height"]), ("webp", "true", "512", "380"))
        self.assertTrue(url.startswith(PROXY), "簽章參數要原樣留著，代理才認")

    def test_static_asks_for_1280_on_the_long_side_and_keeps_its_format(self):
        p = _params(proxy_variant(_image(width=2160, height=2880)))
        self.assertEqual((p["width"], p["height"]), ("960", "1280"))
        self.assertNotIn("format", p)

    def test_small_pictures_are_not_enlarged(self):
        p = _params(proxy_variant(_image(width=300, height=200, animated=True)))
        self.assertEqual((p["width"], p["height"]), ("300", "200"))

    def test_unknown_size_never_asks_for_a_size(self):
        # 寬高比例不對代理會把圖拉變形；不知道原圖寬高就只要格式，靜態圖連格式都不用要
        p = _params(proxy_variant(_image(animated=True)))
        self.assertNotIn("width", p)
        self.assertNotIn("height", p)
        self.assertEqual(p["format"], "webp")
        self.assertEqual(proxy_variant(_image()), PROXY)

    def test_no_proxy_no_variant(self):
        self.assertIsNone(proxy_variant(_image(proxy_url=None)))


class RemoteImageTests(unittest.TestCase):
    """附件與預覽縮圖都照屬性讀成同一種東西。"""

    def test_attachment_or_preview_media_is_read_by_attribute(self):
        media = SimpleNamespace(proxy_url="p", url="u", width=570, height=570, flags=SimpleNamespace(animated=True))
        self.assertEqual(remote_image(media), RemoteImage("p", "u", 570, 570, True))

    def test_gifs_count_as_animated_even_without_the_flag(self):
        self.assertTrue(remote_image(SimpleNamespace(proxy_url="p", url="https://cdn/a.GIF?ex=1")).animated)
        self.assertTrue(remote_image(SimpleNamespace(proxy_url="p", url="u", filename="a.gif")).animated)
        self.assertTrue(remote_image(SimpleNamespace(proxy_url="p", url="u", content_type="image/gif")).animated)
        self.assertFalse(remote_image(SimpleNamespace(proxy_url="p", url="https://cdn/a.jpg", flags=None)).animated)

    def test_nothing_to_fetch_is_none(self):
        self.assertIsNone(remote_image(SimpleNamespace(proxy_url=None, url=None)))
        self.assertIsNone(remote_image(None))


class _Resp:
    def __init__(self, status=200, body=b"", content_length=None, error=None):
        self.status, self.body, self.content_length, self.error = status, body, content_length, error

    async def read(self):
        return self.body

    async def __aenter__(self):
        if self.error is not None:
            raise self.error
        return self

    async def __aexit__(self, *exc):
        return False


class _Session:
    """代理的網址回 `proxy` 那一頁、其他回 `original`；記下問過哪些網址。"""

    def __init__(self, proxy=None, original=None):
        self.pages = {"proxy": proxy or _Resp(404), "original": original or _Resp(404)}
        self.asked = []

    def get(self, url, timeout=None):
        self.asked.append(url)
        return self.pages["proxy" if url.startswith("https://media.") else "original"]


def _fetch(session, image, **kwargs):
    return asyncio.run(fetch_for_vision(session, image, **kwargs))


def _decoded(b64):
    return Image.open(BytesIO(base64.b64decode(b64)))


def _png_of(size):
    buf = BytesIO()
    Image.new("RGB", size, (30, 120, 200)).save(buf, format="PNG")
    return buf.getvalue()


@unittest.skipUnless(HAS_PIL, "需要 Pillow")
class FetchForVisionTests(unittest.TestCase):
    def test_the_proxy_comes_first_and_the_original_is_left_alone(self):
        session = _Session(proxy=_Resp(body=_png()), original=_Resp(body=_png()))
        got = _fetch(session, _image(width=64, height=64))
        self.assertEqual(len(got.frames), 1)
        self.assertEqual(len(session.asked), 1)
        self.assertTrue(session.asked[0].startswith(PROXY))

    def test_falls_back_to_the_original_when_the_proxy_does_not_work(self):
        cases = {
            "404": _Resp(404),
            "逾時": _Resp(error=asyncio.TimeoutError()),
            "下載下來太大": _Resp(body=b"x" * (MAX_FETCH_BYTES + 1)),
            "宣告的大小太大": _Resp(content_length=MAX_FETCH_BYTES + 1, body=_png()),
            "解不開": _Resp(body=b"not an image"),
        }
        for name, proxy in cases.items():
            with self.subTest(name):
                session = _Session(proxy=proxy, original=_Resp(body=_png()))
                got = _fetch(session, _image())
                self.assertEqual(len(got.frames), 1)
                self.assertEqual(session.asked[-1], ORIGINAL)

    def test_the_limit_is_10mb_for_both(self):
        self.assertEqual(MAX_FETCH_BYTES, 10 * 1024 * 1024)
        got = _fetch(_Session(proxy=_Resp(content_length=6 * 1024 * 1024, body=_png())), _image())
        self.assertEqual(len(got.frames), 1, "原本 5 MB 的上限會擋掉這張")

    def test_nothing_when_both_fail_with_a_log_line_and_whether_it_was_too_big(self):
        session = _Session(proxy=_Resp(404), original=_Resp(content_length=11 * 1024 * 1024))
        with self.assertLogs(vision_image.logger, "INFO") as logs:
            got = _fetch(session, _image())
        self.assertEqual(got.frames, [])
        self.assertTrue(got.too_big)
        self.assertIn("404", "\n".join(logs.output))
        got = _fetch(_Session(proxy=_Resp(404), original=_Resp(500)), _image())
        self.assertEqual((got.frames, got.too_big), ([], False))

    def test_animated_becomes_up_to_four_png_frames_512_on_the_long_side(self):
        colours = [(220, 20, 20), (20, 220, 20), (20, 20, 220), (220, 220, 20), (20, 220, 220), (220, 20, 220)]
        session = _Session(proxy=_Resp(body=_gif(colours, size=(800, 600))))
        got = _fetch(session, _image(animated=True))
        self.assertTrue(2 <= len(got.frames) <= 4, len(got.frames))
        for frame in got.frames:
            with _decoded(frame) as im:
                self.assertEqual((im.format, im.size), ("PNG", (512, 384)))
        self.assertLessEqual(len(_fetch(session, _image(animated=True), max_frames=2).frames), 2)

    def test_static_becomes_one_jpeg_1280_on_the_long_side(self):
        got = _fetch(_Session(proxy=_Resp(body=_png_of((2000, 3000)))), _image())
        self.assertEqual(len(got.frames), 1)
        with _decoded(got.frames[0]) as im:
            self.assertEqual((im.format, im.size), ("JPEG", (853, 1280)))

    def test_decoding_runs_off_the_event_loop(self):
        threads = []
        real = vision_image.vision_frames

        def spy(*args, **kwargs):
            threads.append(threading.current_thread() is threading.main_thread())
            return real(*args, **kwargs)

        with mock.patch.object(vision_image, "vision_frames", spy):
            got = _fetch(_Session(proxy=_Resp(body=_png())), _image())
        self.assertEqual(len(got.frames), 1)
        self.assertEqual(threads, [False], "拆幀、轉檔要丟到執行緒，不卡音樂與 Discord 連線")

if __name__ == "__main__":
    unittest.main()
