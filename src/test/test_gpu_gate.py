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
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from llm import lemonade_gate as gate  # noqa: E402
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
