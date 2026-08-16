"""vision 圖片前處理測試：動圖拆關鍵幀 + 格式降級備援。

拆幀的重點不是「拆出幾張」，是**只留變化大的**——反應 gif 常常幾十幀都在原地抖，
等距抽樣會拿到一疊幾乎一樣的圖，白白吃掉 context 額度（總上限 9 張）。

執行：
    cd src && python -m unittest test.test_vision_image -v
"""

import base64
import os
import sys
import unittest
from io import BytesIO

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from llm.vision_image import extract_key_frames, is_universal_image, to_png_first_frame
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


if __name__ == "__main__":
    unittest.main()
