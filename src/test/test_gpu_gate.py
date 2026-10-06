"""GPU 互斥閘的租約機制 + `release_model()` 的後端分派（hermetic，不碰網路）。

這組測試守兩件事：

1. **既有 10 個 `stream_exclusive()` caller 不能被改壞。** 閘門從「一把裸鎖」擴成
   「租約閘」時，短工作路徑必須一字不差地維持原行為（不開 watchdog、永不到期）。

2. **租約真的會在卡死時放手。** 這是整個設計存在的理由：ComfyUI 卡住時若閘門
   不放，/askai、插話、日記、人格萃取會全部靜默死掉。所以「到期會取消持有者並
   釋放閘門」必須有測試釘住，不能只靠註解。

執行：
    cd src && python -m unittest test.test_gpu_gate -v
"""

import asyncio
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from llm.client import lemonade_gate as gate  # noqa: E402
from services.llm_service import LLMService  # noqa: E402
from sys_settings.llm_settings import LLMRuntimeConfig  # noqa: E402


class _GateTestCase(unittest.IsolatedAsyncioTestCase):
    """每個測試換一把新鎖。

    `asyncio.Lock` 在**有競爭**時才會綁定當下的 event loop，而且綁了就不解綁；
    沿用同一把會讓下一個測試的 loop 撞 "bound to a different event loop"。
    重建成本是零，比在測試之間玩解綁安全。
    """

    def setUp(self) -> None:
        gate._GPU_LOCK = asyncio.Lock()
        gate._holder = None
        gate._last_release = 0.0
        gate._skip_until = 0.0
        # 每個測試用自己的鎖檔：不跟同一個容器裡執行中的 bot 搶，也不互相影響
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        patcher = mock.patch.object(gate, "CROSS_PROCESS_LOCK_PATH", os.path.join(tmp, "gpu.lock"))
        patcher.start()
        self.addCleanup(patcher.stop)


class CrossProcessQueueTests(_GateTestCase):
    """同一個容器裡另開的行程（手動抽查腳本、MCP server）也要跟 bot 一起排隊，不能直接搶模型。"""

    def hold_in_other_process(self) -> subprocess.Popen:
        proc = subprocess.Popen(
            [sys.executable, "-c",
             "import fcntl, sys, time\n"
             f"f = open({gate.CROSS_PROCESS_LOCK_PATH!r}, 'a')\n"
             # 最多等 5 秒：鎖沒被放掉時讓測試直接失敗，不要卡住啟動檢查
             "deadline = time.monotonic() + 5\n"
             "while True:\n"
             "    try:\n"
             "        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB); break\n"
             "    except BlockingIOError:\n"
             "        if time.monotonic() > deadline: print('busy', flush=True); sys.exit(1)\n"
             "        time.sleep(0.05)\n"
             "print('locked', flush=True)\n"
             "sys.stdin.readline()\n"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
        )
        if proc.stdout.readline().strip() != "locked":
            proc.kill()
            self.fail("鎖一直沒被放掉，別的行程拿不到")
        return proc

    async def test_waits_while_another_process_holds_the_gpu(self):
        other = self.hold_in_other_process()
        entered = asyncio.Event()

        async def job():
            async with gate.stream_exclusive():
                entered.set()

        task = asyncio.create_task(job())
        await asyncio.sleep(0.3)
        self.assertFalse(entered.is_set(), "別的行程在用，要排隊")
        other.communicate("\n")          # 對方用完
        await asyncio.wait_for(task, 2)
        self.assertTrue(entered.is_set())

    async def test_lock_is_released_after_use_and_after_cancel(self):
        async with gate.stream_exclusive():
            pass
        other = self.hold_in_other_process()   # 用完有放，別的行程拿得到
        waiting = asyncio.create_task(gate.stream_exclusive().__aenter__())
        await asyncio.sleep(0.15)
        waiting.cancel()                        # 等的途中被取消（例如逾時放行）
        await asyncio.gather(waiting, return_exceptions=True)
        other.communicate("\n")
        self.hold_in_other_process().communicate("\n")   # 取消的不會留著鎖

    async def test_takes_turns_with_another_process(self):
        """本行程有一串工作時，別的行程也要插得進來（輪流用，不是等整串做完）。"""
        order = []
        poller = subprocess.Popen(
            [sys.executable, "-c",
             "import fcntl, sys, time\n"
             f"f = open({gate.CROSS_PROCESS_LOCK_PATH!r}, 'a')\n"
             "deadline = time.monotonic() + 5\n"
             "print('polling', flush=True)\n"
             "while time.monotonic() < deadline:\n"
             "    try:\n"
             "        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB); print('got', flush=True); sys.exit(0)\n"
             "    except BlockingIOError:\n"
             # 輪詢間隔要遠小於放鎖後讓位的時間，機器忙時才不會剛好錯過
             "        time.sleep(0.02)\n"
             "print('never', flush=True)\n"],
            stdout=subprocess.PIPE, text=True,
        )

        async def job(tag, hold):
            async with gate.stream_exclusive():
                order.append(tag)
                await asyncio.sleep(hold)

        async with gate.stream_exclusive():
            # 本行程先佔著，等外部行程真的開始輪詢才放（機器忙時另開行程要好一陣子才跑起來）
            self.assertEqual((await asyncio.to_thread(poller.stdout.readline)).strip(), "polling")
            await asyncio.sleep(0.1)
            follow = asyncio.create_task(job("b", 0.3))   # 緊接著還有下一件
        line = await asyncio.to_thread(poller.stdout.readline)
        order.append(line.strip())
        await follow
        poller.wait()
        self.assertEqual(order[0], "got", f"外部行程要在下一件之前插進來：{order}")

    async def test_long_wait_is_logged_and_capped(self):
        other = self.hold_in_other_process()
        try:
            with mock.patch.object(gate, "_CROSS_PROCESS_WARN_S", 0.2), \
                 mock.patch.object(gate, "_CROSS_PROCESS_MAX_WAIT_S", 0.5):
                with self.assertLogs("llm.client.lemonade_gate", "WARNING") as logs:
                    async with gate.stream_exclusive():
                        pass
            self.assertTrue(any("已等" in line for line in logs.output), logs.output)
            self.assertTrue(any("不等了" in line for line in logs.output), "別的行程卡住時不能讓 bot 的 AI 整個停住")
            # 等滿上限放行後，下一個呼叫不能又從頭等（排在後面的會等 N 倍）
            started = asyncio.get_running_loop().time()
            with mock.patch.object(gate, "_CROSS_PROCESS_MAX_WAIT_S", 0.5):
                async with gate.stream_exclusive():
                    pass
            self.assertLess(asyncio.get_running_loop().time() - started, 0.4)
        finally:
            other.communicate("\n")

    async def test_unopenable_lock_file_still_queues_in_process(self):
        with mock.patch.object(gate, "CROSS_PROCESS_LOCK_PATH", "/proc/nope/gpu.lock"):
            with self.assertLogs("llm.client.lemonade_gate", "WARNING"):
                async with gate.stream_exclusive():
                    self.assertTrue(gate.stream_busy())


class StreamExclusiveRegressionTests(_GateTestCase):
    """短工作路徑（chat / batch embedding）行為不變。"""

    async def test_is_mutually_exclusive(self):
        order = []

        async def worker(tag: str, hold: float):
            async with gate.stream_exclusive():
                order.append(f"{tag}-in")
                await asyncio.sleep(hold)
                order.append(f"{tag}-out")

        first = asyncio.create_task(worker("a", 0.1))
        await asyncio.sleep(0.01)          # 確保 a 先進去
        second = asyncio.create_task(worker("b", 0.0))
        await asyncio.gather(first, second)

        # b 必須整段等在門外，不可以插進 a 的區段中間
        self.assertEqual(order, ["a-in", "a-out", "b-in", "b-out"])

    async def test_busy_flag_and_owner(self):
        self.assertFalse(gate.stream_busy())
        self.assertIsNone(gate.current_owner())

        async with gate.stream_exclusive():
            self.assertTrue(gate.stream_busy())
            self.assertEqual(gate.current_owner(), "llm")
            # 短工作不是產圖：/askai 不該因此被告知「正在產圖」
            self.assertFalse(gate.imagegen_busy())

        self.assertFalse(gate.stream_busy())
        self.assertIsNone(gate.current_owner())

    async def test_no_lease_never_expires(self):
        """`lease_seconds=None` ＝ 不開 watchdog，持有多久都不會被取消。"""
        async with gate.gpu_exclusive("llm") as lease:
            self.assertIsNone(lease.lease_seconds)
            self.assertFalse(lease.expired)
            await asyncio.sleep(0.3)
            self.assertTrue(gate.stream_busy())
        self.assertFalse(gate.stream_busy())


class LeaseTests(_GateTestCase):
    """長工作路徑（產圖）：心跳續租、卡死自我了斷。"""

    async def test_imagegen_owner_is_distinguishable(self):
        async with gate.gpu_exclusive("imagegen", lease_seconds=5):
            self.assertTrue(gate.stream_busy())
            self.assertTrue(gate.imagegen_busy())
            self.assertEqual(gate.current_owner(), "imagegen")
        self.assertFalse(gate.imagegen_busy())

    async def test_expiry_cancels_holder_and_releases_gate(self):
        """不續租 → watchdog 取消持有者 → finally 把閘門放掉。

        這一條是整個租約設計的存在理由；拿掉它，ComfyUI 卡死時 bot 會靜默全死。
        """
        entered = asyncio.Event()

        async def stuck_holder():
            async with gate.gpu_exclusive("imagegen", lease_seconds=0.3):
                entered.set()
                await asyncio.sleep(30)     # 假裝 ComfyUI 卡死，永遠不 renew

        task = asyncio.create_task(stuck_holder())
        await entered.wait()
        self.assertTrue(gate.imagegen_busy())

        with self.assertRaises(asyncio.CancelledError):
            await task

        self.assertFalse(gate.stream_busy(), "租約到期後閘門必須放掉")
        self.assertIsNone(gate.current_owner())

    async def test_renew_keeps_long_job_alive(self):
        """持續心跳的長工作不可以被誤殺——租約長度與工作總長解耦。"""
        finished = False

        async def polling_holder():
            nonlocal finished
            async with gate.gpu_exclusive("imagegen", lease_seconds=0.5) as lease:
                for _ in range(6):          # 總長 0.6s > 單次租約 0.5s
                    await asyncio.sleep(0.1)
                    lease.renew()           # 模擬 ComfyUI 輪詢成功
                finished = True

        await asyncio.wait_for(asyncio.create_task(polling_holder()), timeout=5)
        self.assertTrue(finished)
        self.assertFalse(gate.stream_busy())

    async def test_gate_is_reusable_after_expiry(self):
        """被 watchdog 收掉之後，下一個工作要能正常進場（不留殘留狀態）。"""
        async def stuck_holder():
            async with gate.gpu_exclusive("imagegen", lease_seconds=0.2):
                await asyncio.sleep(30)

        task = asyncio.create_task(stuck_holder())
        await asyncio.sleep(0.05)
        with self.assertRaises(asyncio.CancelledError):
            await task

        async with gate.stream_exclusive():
            self.assertEqual(gate.current_owner(), "llm")


class _FakeClient:
    """只記錄呼叫，不打網路。"""

    def __init__(self) -> None:
        self.unloaded: list[str] = []
        self.chats: list[tuple[str, dict | None]] = []

    def unload_lemonade_model(self, *, model: str, **_kw) -> None:
        self.unloaded.append(model)

    async def chat_completion(self, *, model: str, messages, extra_body=None, **_kw):
        self.chats.append((model, extra_body))
        return {"choices": [{"message": {"content": ""}}]}


def _service(backend: str) -> tuple[LLMService, _FakeClient]:
    """繞過 __init__（會讀 prompt 檔），只裝上 release_model 需要的狀態。"""
    svc = LLMService.__new__(LLMService)
    config = LLMRuntimeConfig(
        backend=backend,
        model="Qwen3.8-27B-GGUF-UD-Q4_K_XL",
        embed_model="Qwen3-Embedding-0.6B-GGUF",
    )
    svc._load_runtime_config_cached = lambda: config  # type: ignore[method-assign]
    client = _FakeClient()
    svc._client = client
    return svc, client


class ReleaseModelTests(_GateTestCase):
    """「讓出 VRAM」這個意圖在各後端的實作分派。"""

    async def test_lemonade_calls_unload(self):
        svc, client = _service("lemonade")
        self.assertTrue(await svc.release_model("m1"))
        self.assertEqual(client.unloaded, ["m1"])
        self.assertEqual(client.chats, [], "Lemonade 不該走 chat 路徑")

    async def test_ollama_sends_keep_alive_zero(self):
        svc, client = _service("ollama")
        self.assertTrue(await svc.release_model("m1"))
        self.assertEqual(client.unloaded, [], "Ollama 沒有 unload admin API")
        self.assertEqual(len(client.chats), 1)
        model, extra_body = client.chats[0]
        self.assertEqual(model, "m1")
        self.assertEqual(extra_body.get("keep_alive"), 0)

    async def test_vllm_is_a_noop(self):
        """一 process 一 model、沒有 swap 概念——做不到就誠實回 False，不要假裝。"""
        svc, client = _service("vllm")
        self.assertFalse(await svc.release_model("m1"))
        self.assertEqual(client.unloaded, [])
        self.assertEqual(client.chats, [])

    async def test_does_not_reacquire_the_gate(self):
        """呼叫端已持有閘門時 `release_model()` 必須能跑完。

        它若走 `chat_raw`（會再 acquire 一次 `stream_exclusive()`）就會死鎖，
        而死鎖的症狀是「bot 靜默不動」，非常難查——所以直接用測試釘住。
        """
        svc, client = _service("ollama")
        async with gate.gpu_exclusive("imagegen", lease_seconds=5):
            await asyncio.wait_for(svc.release_model("m1"), timeout=2)
        self.assertEqual(len(client.chats), 1)


if __name__ == "__main__":
    unittest.main()
