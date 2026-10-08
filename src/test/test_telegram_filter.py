"""Telegram 過濾的判斷（services/relay/telegram_filter.py）。

守的底線：
- 只有模型明確回「隔離」才隔離；回「放行」、看不懂、只寫了理由都放行（拿不準放行，使用者 10-05）
- 模型忙就排隊、不放行（使用者 10-08：「不能 90 秒沒回應就處理，應該排隊」）：產圖佔著 GPU 時等它做完才叫模型
  （不然會把 LLM 載回去搶 VRAM）；模型逾時、連不上就隔一陣子再排
- 排滿 30 分鐘還判不到才放行，並認定模型掛了：之後每則只問一次、失敗就放行（不再每則等滿）；問到一次就恢復排隊
- 判不了的放行、不擋轉發：模型回錯誤、讀不到 prompt
- 一定要看圖：該看的圖或影片有任何一個沒看到（檔案讀不到、抽幀失敗）就放行、不叫模型——只憑其他部分判
  會把「水」配角色設計稿那種情報錯關（13649）；附語音、壓縮檔（模型看不了）的也放行（語音爆料常常沒有文字）
- 回答不合格式就放行：只寫「隔離」沒有標籤、好幾行結論互相矛盾、思考區塊沒收尾
- 影片：只有一個關鍵畫格的短片也要抽得到畫面；最後一段要看得到；同一張不送兩次
- 透明背景的圖鋪白底（不能整張變黑）
- 每個發送單位最多給模型 `max_images` 張：前幾個媒體各一張，媒體不夠時剩下的名額給動圖多抽幾格；
  音訊、壓縮檔不看；圖縮到長邊上限並轉 JPEG；模型真的拿到圖、而且關掉思考
- 隔離時帶標籤（灌水、閒聊、罵人、無關圖片，模型寫別的記「其他」）與理由，給隔離那則最上面一行用

執行：
    cd src && python -m unittest test.test_telegram_filter -v
"""
import asyncio
import base64
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from PIL import Image, ImageDraw

from services.relay import telegram_filter as tf


def _png(size=(64, 64), colour=(220, 30, 30)) -> bytes:
    buf = BytesIO()
    Image.new("RGB", size, colour).save(buf, format="PNG")
    return buf.getvalue()


def _gif(colours, size=(64, 64)) -> bytes:
    ims = []
    for c in colours:
        im = Image.new("RGB", size, "white")
        ImageDraw.Draw(im).rectangle([8, 8, size[0] - 8, size[1] - 8], fill=c)
        ims.append(im)
    buf = BytesIO()
    ims[0].save(buf, format="GIF", save_all=True, append_images=ims[1:], duration=100, loop=0)
    return buf.getvalue()


FOUR_COLOURS = [(220, 20, 20), (20, 220, 20), (20, 20, 220), (220, 220, 20), (20, 220, 220), (220, 20, 220)]


class FakeLLM:
    def __init__(self, answer="看到一張圖。\n放行｜有角色", delay=0.0, error=None):
        self.answer, self.delay, self.error = answer, delay, error
        #: 依序先拋這些錯（例如模型逾時），拋完才照常回答
        self.errors: list[Exception] = []
        self.calls = []

    def resolve_request_model(self):
        return "main"

    async def chat_raw(self, **kwargs):
        self.calls.append(kwargs)
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.errors:
            raise self.errors.pop(0)
        if self.error:
            raise self.error
        return self.answer


class FilterTestBase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        prompt = self.tmp / "prompt.txt"
        prompt.write_text("判斷有沒有鳴潮的資訊。", encoding="utf-8")
        self.settings = tf._SETTINGS.model_copy(update={
            "prompt_path": str(prompt), "retry_initial_seconds": 0.01, "retry_max_seconds": 0.5,
            "busy_poll_seconds": 0.01, "give_up_seconds": 10,
        })
        self.llm = FakeLLM()
        for target, value in (("_SETTINGS", self.settings), ("_LLM", self.llm)):
            patcher = mock.patch.object(tf, target, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        busy = mock.patch.object(tf.lemonade_gate, "imagegen_busy", return_value=False)
        self.imagegen_busy = busy.start()
        self.addCleanup(busy.stop)
        down = mock.patch.object(tf, "_model_down", False)
        down.start()
        self.addCleanup(down.stop)

    def file(self, name: str, data: bytes, kind: str) -> tf.MediaFile:
        path = self.tmp / name
        path.write_bytes(data)
        return tf.MediaFile(path, kind)

    async def judge(self, text="", media=()):
        return await tf.judge(text, list(media), trace_id="test")

    def sent_images(self) -> list[bytes]:
        user = self.llm.calls[-1]["messages"][-1]
        return [base64.b64decode(b) for b in user.get("images", [])]


class VerdictTests(FilterTestBase):
    async def test_quarantine_only_when_model_says_so(self):
        self.llm.answer = "文字是「今日首水」，沒有圖。\n隔離｜灌水｜每日打卡灌水"
        v = await self.judge("今日首水")
        self.assertTrue(v.quarantine)
        self.assertEqual((v.label, v.reason), ("灌水", "每日打卡灌水"))
        self.assertTrue(v.by_model)

    async def test_pass_answer_passes(self):
        self.llm.answer = "文字是「已开服」。\n放行｜開服消息"
        v = await self.judge("已开服")
        self.assertFalse(v.quarantine)
        self.assertTrue(v.by_model)

    async def test_unreadable_answer_passes(self):
        for answer in ["看起來是梗圖", "", "我覺得應該隔離", "隔離吧？不確定"]:
            self.llm.answer = answer
            v = await self.judge("水")
            self.assertFalse(v.quarantine, answer)
            self.assertFalse(v.by_model, answer)

    def test_parse_handles_copied_prefix_and_bars(self):
        self.assertEqual(tf.parse_verdict("圖是奶龍。\n第二行：隔離｜無關圖片｜奶龍梗圖"), (True, "無關圖片", "奶龍梗圖"))
        self.assertEqual(tf.parse_verdict("<think>嗯</think>\n隔離 | 罵人 | 互嗆"), (True, "罵人", "互嗆"))
        self.assertEqual(tf.parse_verdict("隔離｜廣告｜賣東西"), (True, "其他", "廣告｜賣東西"))
        self.assertEqual(tf.parse_verdict("放行"), (False, "", ""))
        self.assertIsNone(tf.parse_verdict("看到梗圖。\n隔離"), "只寫隔離沒有標籤＝不合格式")
        self.assertIsNone(tf.parse_verdict("放行｜有角色\n例：\n隔離｜灌水｜每日打卡"), "答完又照抄範例，結論互相矛盾")
        self.assertIsNone(tf.parse_verdict("看到圖。\n<think>應該是\n隔離｜灌水｜x"), "思考區塊沒收尾")
        # 結論寫在思考區塊裡不算（沒有真的回答）
        self.assertIsNone(tf.parse_verdict("<think>先想想\n隔離｜灌水｜打卡</think>"))


class ModelUnavailableTests(FilterTestBase):
    async def test_waits_for_imagegen_then_judges(self):
        self.llm.answer = "文字是「今日首水」。\n隔離｜灌水｜每日打卡"
        calls_while_busy = []
        busy = iter([True, True, True, False])

        def imagegen_busy():
            calls_while_busy.append(len(self.llm.calls))
            return next(busy, False)
        self.imagegen_busy.side_effect = imagegen_busy
        v = await self.judge("今日首水")
        self.assertTrue(v.quarantine, "等產圖做完再判，不放行")
        self.assertTrue(v.by_model)
        self.assertEqual(calls_while_busy[:3], [0, 0, 0], "產圖中叫模型會把 LLM 載回去搶 VRAM")

    async def test_slow_model_is_waited_for(self):
        # 原本 90 秒就放行：插話一次佔模型好幾分鐘時，垃圾就漏進主頻道（14106）
        self.llm.answer = "文字是「今日首水」。\n隔離｜灌水｜每日打卡"
        self.llm.delay = 0.3
        v = await self.judge("今日首水")
        self.assertTrue(v.quarantine)
        self.assertTrue(v.by_model)

    async def test_model_timeout_is_retried_until_answered(self):
        self.llm.answer = "文字是「今日首水」。\n隔離｜灌水｜每日打卡"
        self.llm.errors = [tf.LlmTimeoutError("逾時"), tf.LlmConnectionError("連不上")]
        with self.assertLogs("services.relay.telegram_filter", "WARNING") as logs:
            v = await self.judge("今日首水")
        self.assertTrue(v.quarantine, "逾時、連不上是模型忙，再排一次，不放行")
        self.assertEqual(len(self.llm.calls), 3)
        self.assertEqual(len(logs.output), 2)

    async def test_gives_up_after_the_limit(self):
        self.llm.delay = 2
        with mock.patch.object(tf, "_SETTINGS", self.settings.model_copy(update={"give_up_seconds": 0.2})):
            with self.assertLogs("services.relay.telegram_filter", "ERROR"):
                v = await self.judge("今日首水")
        self.assertEqual((v.quarantine, v.by_model), (False, False))
        self.assertIn("沒回應", v.reason)
        self.assertLess(v.seconds, 1.5, "排滿時限就放行，不等模型回完")
        self.assertTrue(tf._model_down)

    async def test_while_model_is_down_each_message_is_asked_once(self):
        tf._model_down = True
        self.llm.errors = [tf.LlmTimeoutError("逾時"), tf.LlmTimeoutError("逾時")]
        v = await self.judge("今日首水")
        self.assertEqual((v.quarantine, v.by_model), (False, False))
        self.assertIn("還沒恢復", v.reason)
        self.assertEqual(len(self.llm.calls), 1, "掛了就不再每則排滿 30 分鐘，不然一次一則會卡好幾小時")
        self.assertTrue(tf._model_down)

    async def test_answer_brings_back_queueing(self):
        tf._model_down = True
        self.llm.answer = "文字是「今日首水」。\n隔離｜灌水｜每日打卡"
        with self.assertLogs("services.relay.telegram_filter", "WARNING"):
            v = await self.judge("今日首水")
        self.assertTrue(v.quarantine)
        self.assertFalse(tf._model_down)
        self.llm.errors = [tf.LlmTimeoutError("逾時")]
        with self.assertLogs("services.relay.telegram_filter", "WARNING"):
            v = await self.judge("今日首水")
        self.assertTrue(v.quarantine, "恢復後又照常排隊、重問")
        self.assertEqual(len(self.llm.calls), 3)

    async def test_which_passes_are_rechecked_later(self):
        # 使用者 10-08 UC-Q2：模型沒判到（沒回應、出錯、看不懂）之後補判；看不了的檔案、有圖沒看到再判也一樣
        self.llm.answer = "看起來是梗圖"
        self.assertTrue((await self.judge("水")).recheck, "回答看不懂")
        self.llm.error = RuntimeError("連不上")
        with self.assertLogs("services.relay.telegram_filter", "WARNING"):
            self.assertTrue((await self.judge("水")).recheck, "出錯")
        self.llm.error = None
        tf._model_down = True
        self.llm.errors = [tf.LlmTimeoutError("逾時")]
        self.assertTrue((await self.judge("水")).recheck, "等不到模型")
        voice = self.file("a.ogg", b"OggS", "other")
        missing = tf.MediaFile(self.tmp / "gone.jpg", "image")
        for media in ([voice], [missing]):
            self.assertFalse((await self.judge("", media)).recheck, media)
        self.llm.answer = "看到圖。\n放行｜有角色"
        self.assertFalse((await self.judge("水")).recheck, "模型判過了")

    async def test_model_error_passes(self):
        self.llm.error = RuntimeError("連不上")
        with self.assertLogs("services.relay.telegram_filter", "WARNING"):
            v = await self.judge("今日首水")
        self.assertFalse(v.quarantine)
        self.assertFalse(v.by_model)

    async def test_missing_prompt_passes(self):
        Path(self.settings.prompt_path).unlink()
        with self.assertLogs("services.relay.telegram_filter", "WARNING"):
            v = await self.judge("今日首水")
        self.assertFalse(v.quarantine)
        self.assertEqual(self.llm.calls, [])


class ImageTests(FilterTestBase):
    async def test_model_gets_the_image_without_thinking(self):
        self.llm.answer = "隔離｜無關圖片｜奶龍"
        await self.judge("", [self.file("a.png", _png(), "image")])
        call = self.llm.calls[-1]
        self.assertIs(call["think"], False, "不關思考慢好幾倍，還可能把思考寫進回答")
        self.assertEqual(len(self.sent_images()), 1)

    async def test_visual_media_seen_none_passes_without_model(self):
        broken = self.file("broken.jpg", b"not an image", "image")
        missing = tf.MediaFile(self.tmp / "gone.jpg", "image")
        for media in ([broken], [missing]):
            self.llm.calls.clear()
            v = await self.judge("水", media)
            self.assertFalse(v.quarantine)
            self.assertFalse(v.by_model)
            self.assertEqual(self.llm.calls, [], "沒看到圖就只憑文字判，會把設計稿那種情報錯關")

    async def test_album_shows_first_four_in_order(self):
        media = [self.file(f"{n}.png", _png(colour=c), "image") for n, c in enumerate(FOUR_COLOURS)]
        await self.judge("", media)
        got = [Image.open(BytesIO(b)).convert("RGB").getpixel((5, 5)) for b in self.sent_images()]
        self.assertEqual(len(got), 4)
        for pixel, colour in zip(got, FOUR_COLOURS[:4]):
            self.assertTrue(all(abs(a - b) < 20 for a, b in zip(pixel, colour)), (pixel, colour))

    async def test_spare_slots_go_to_animation(self):
        gif = self.file("a.gif", _gif(FOUR_COLOURS), "image")
        photo = self.file("b.png", _png(), "image")
        await self.judge("", [gif, photo])
        self.assertEqual(len(self.sent_images()), 4, "GIF 拿剩下的名額多抽幾格，照片一張")
        self.assertEqual(len(await tf.collect_images([gif])), 4)

    async def test_unviewable_attachments_pass_without_model(self):
        audio = self.file("a.wav", b"RIFF....", "other")
        for text in ("", "新角色語音"):
            v = await self.judge(text, [audio])
            self.assertFalse(v.quarantine, text)
            self.assertFalse(v.by_model, text)
        self.assertEqual(self.llm.calls, [], "語音、壓縮檔模型看不了，沒文字的語音爆料會被當成空訊息錯關")

    async def test_one_unseen_image_in_album_passes(self):
        good = self.file("a.png", _png(), "image")
        broken = self.file("b.jpg", b"not an image", "image")
        v = await self.judge("水", [good, broken])
        self.assertFalse(v.by_model)
        self.assertEqual(self.llm.calls, [], "只看到一部分就判，可能漏掉在沒看到的那張裡的情報")

    async def test_images_beyond_the_limit_are_not_counted_as_unseen(self):
        media = [self.file(f"{n}.png", _png(colour=FOUR_COLOURS[n % 6]), "image") for n in range(5)]
        media.append(self.file("broken.jpg", b"not an image", "image"))   # 第 6 張本來就不看
        v = await self.judge("", media)
        self.assertTrue(v.by_model)

    async def test_two_animations_share_four_slots(self):
        a = self.file("a.gif", _gif(FOUR_COLOURS), "image")
        b = self.file("b.gif", _gif(list(reversed(FOUR_COLOURS))), "image")
        await self.judge("", [a, b])
        self.assertLessEqual(len(self.sent_images()), 4)
        self.assertGreaterEqual(len(self.sent_images()), 2)

    async def test_transparent_background_is_white(self):
        im = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        ImageDraw.Draw(im).rectangle([20, 20, 44, 44], fill=(0, 0, 0, 255))
        buf = BytesIO()
        im.save(buf, format="PNG")
        await self.judge("", [self.file("t.png", buf.getvalue(), "image")])
        corner = Image.open(BytesIO(self.sent_images()[0])).convert("RGB").getpixel((2, 2))
        self.assertGreater(min(corner), 200, "透明的地方要是白的，不能變黑")

    async def test_images_are_downscaled_jpeg(self):
        await self.judge("", [self.file("big.png", _png(size=(4000, 2000)), "image")])
        img = Image.open(BytesIO(self.sent_images()[0]))
        self.assertEqual(img.format, "JPEG")
        self.assertLessEqual(max(img.size), self.settings.image_max_side)

    async def test_oversized_file_is_not_read(self):
        small_limit = self.settings.model_copy(update={"image_max_bytes": 10})
        with mock.patch.object(tf, "_SETTINGS", small_limit):
            v = await self.judge("水", [self.file("a.png", _png(), "image")])
        self.assertFalse(v.by_model)

    def test_media_kind(self):
        cases = [
            (("photo", "image/jpeg", "a.jpg"), "image"),
            (("image", "image/webp", "a.webp"), "image"),
            (("unknown", None, "a.jpg"), "image"),
            (("video", "video/mp4", "a.mp4"), "video"),
            (("video", "video/webm", "a.webm"), "video"),
            (("audio", "audio/wav", "a.wav"), "other"),
            (("document", "application/zip", "a.zip"), "other"),
        ]
        for args, expected in cases:
            self.assertEqual(tf.media_kind(*args), expected, args)


class RelayFilterModeTests(unittest.TestCase):
    def test_mode_comes_from_the_switches_file(self):
        """開關在 settings/switches.json（改了就生效、不用重啟）。"""
        from sys_settings import switches
        for mode in ("off", "dry_run", "on"):
            with mock.patch.object(switches, "current", return_value=switches.Switches(telegram_filter_mode=mode)):
                self.assertEqual(tf.RelayFilter().mode, mode)


@unittest.skipUnless(shutil.which("ffmpeg"), "需要 ffmpeg")
class VideoTests(FilterTestBase):
    # 灰階差很多的顏色（紅綠的灰階幾乎一樣，挑幀分不出來）
    GREYS = ("black", "white", "0x606060", "0xb0b0b0")

    def video(self, colours=GREYS, gop=25) -> tf.MediaFile:
        path = self.tmp / f"clip_{gop}.mp4"
        parts = "".join(f"color=c={c}:s=320x240:d=1,format=yuv420p[v{n}];" for n, c in enumerate(colours))
        joined = "".join(f"[v{n}]" for n in range(len(colours)))
        subprocess.run(
            ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", f"{parts}{joined}concat=n={len(colours)}:v=1:a=0",
             "-g", str(gop), "-sc_threshold", "0", "-y", str(path)],
            check=True,
        )
        return tf.MediaFile(path, "video")

    def shades(self) -> list[int]:
        return [Image.open(BytesIO(b)).convert("L").getpixel((5, 5)) for b in self.sent_images()]

    async def test_video_frames_are_shown_including_the_end(self):
        await self.judge("", [self.video()])
        shades = self.shades()
        self.assertGreaterEqual(len(shades), 3, "影片要抽出好幾格，不是只看第一格")
        self.assertLessEqual(len(shades), 4)
        self.assertTrue(all(Image.open(BytesIO(b)).format == "JPEG" for b in self.sent_images()))
        self.assertTrue(any(abs(v - 0xb0) < 25 for v in shades), f"最後一段要看得到：{shades}")
        self.assertEqual(len(shades), len({v // 20 for v in shades}), f"同一張不能送兩次：{shades}")

    async def test_single_keyframe_video_still_shows_a_frame(self):
        # Telegram 的 GIF 轉 mp4、幾秒的短片常常只有一個關鍵畫格
        await self.judge("", [self.video(gop=1000)])
        self.assertEqual(len(self.sent_images()), 1)
        self.assertEqual(len(self.llm.calls), 1, "要真的叫模型看，不是抽不到就放行")

    async def test_broken_video_passes(self):
        bad = self.file("bad.mp4", b"not a video", "video")
        v = await self.judge("水", [bad])
        self.assertFalse(v.by_model)
        self.assertEqual(self.llm.calls, [])


if __name__ == "__main__":
    unittest.main()
