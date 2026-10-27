"""跑媒體子行程只有一份：utils.media_probe.run_media_tool（有逾時、逾時收掉行程）。

守的底線：
  1. 逾時就砍掉行程、回 timed_out=True，不丟例外；做完回 returncode 與 stdout／stderr，ok 只在 rc=0 時為真。
  2. probe_duration 照舊：讀到數字回秒數、逾時或讀不到回 0。
  3. Telegram 影片壓縮、影片抽幀、點歌音量量測都走 run_media_tool（守衛擋自己 create_subprocess_exec）。

不真的開行程：把建行程與等待換成假的。
"""

import asyncio
import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from utils import media_probe  # noqa: E402

SRC = os.path.dirname(HERE)


class _Proc:
    def __init__(self, rc=0, stdout=b"", stderr=b""):
        self.returncode = None
        self._rc, self._out, self._err = rc, stdout, stderr
        self.killed = False

    async def communicate(self):
        self.returncode = self._rc
        return self._out, self._err

    def kill(self):
        self.killed = True

    async def wait(self):
        self.returncode = -9


class RunMediaToolTests(unittest.TestCase):
    def _run(self, proc, *, times_out=False, timeout=5):
        async def create(*args, **kwargs):
            self.spawned = (args, kwargs)
            return proc

        async def wait_for(coro, timeout_):
            if times_out:
                coro.close()
                raise asyncio.TimeoutError
            return await coro

        with mock.patch.object(media_probe, "_create_subprocess", create), \
             mock.patch.object(media_probe, "_wait_for", wait_for):
            return asyncio.run(media_probe.run_media_tool(["ffmpeg", "-i", "a.mp4"], timeout=timeout))

    def test_finished_tool_returns_its_output(self):
        result = self._run(_Proc(0, b"12.5\n", b"warn"))
        self.assertTrue(result.ok)
        self.assertEqual((0, b"12.5\n", b"warn", False), (result.returncode, result.stdout, result.stderr, result.timed_out))
        self.assertEqual(("ffmpeg", "-i", "a.mp4"), self.spawned[0])
        self.assertEqual(asyncio.subprocess.DEVNULL, self.spawned[1]["stdin"], "工具不會停下來等輸入")

    def test_failed_tool_is_not_ok(self):
        result = self._run(_Proc(1, b"", b"boom"))
        self.assertFalse(result.ok)
        self.assertEqual(1, result.returncode)

    def test_timeout_kills_the_process_and_reports_it(self):
        proc = _Proc(0, b"never", b"")
        with self.assertLogs("utils.media_probe", level="WARNING"):
            result = self._run(proc, times_out=True)
        self.assertTrue(result.timed_out)
        self.assertFalse(result.ok)
        self.assertTrue(proc.killed, "逾時要砍掉行程")


class ProbeDurationTests(unittest.TestCase):
    def _probe(self, result):
        with mock.patch.object(media_probe, "run_media_tool", mock.AsyncMock(return_value=result)):
            return asyncio.run(media_probe.probe_duration("a.mp4"))

    def test_duration_is_parsed(self):
        self.assertEqual(12.5, self._probe(media_probe.ToolResult(0, b"12.5\n", b"")))

    def test_timeout_or_garbage_means_zero(self):
        self.assertEqual(0.0, self._probe(media_probe.ToolResult(None, b"", b"", timed_out=True)))
        self.assertEqual(0.0, self._probe(media_probe.ToolResult(0, b"not a number", b"")))


class CallersTests(unittest.TestCase):
    def test_every_media_subprocess_goes_through_run_media_tool(self):
        for rel in ("services/relay/telegram_relay_service.py", "llm/preprocess/vision_image.py", "music/player.py"):
            with open(os.path.join(SRC, rel), encoding="utf-8") as fh:
                self.assertIn("run_media_tool(", fh.read(), rel)


if __name__ == "__main__":
    unittest.main()
