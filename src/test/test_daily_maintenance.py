"""每日 04:00 維護的編排（`llm/persona/daily_maintenance.py`）：四步順序、失敗隔離、不重疊、補跑判斷。

守的底線：
  - ① emoji 字典 → ② 招牌梗衰減 → ③ persona agent → ④ 發布精簡版，照這個順序跑
  - 每一步失敗都不拖累後面；agent 關掉時 ③ 不跑、④ 照跑
  - 同一時間只跑一輪：已經在跑時再呼叫只記 INFO、不重跑
  - 補跑判斷：沒有寫入紀錄、或上次寫入早於上一個該跑的 04:00 → 補跑；否則跳過
  - 上一個／下一個 04:00 的計算跨日正確
  - 沒有 guild 時什麼都不做

hermetic：各步驟都換成會記錯順序的假函式，不碰資料庫與模型。

執行：
    cd src && python -m unittest test.test_daily_maintenance -v
"""

import asyncio
import contextlib
import os
import sys
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

import llm.persona.agent.batch as agent_batch  # noqa: E402
import llm.persona.agent.publish as agent_publish  # noqa: E402
import llm.persona.member_names as member_names  # noqa: E402
import llm.persona.personality_extractor as extractor  # noqa: E402
import llm.persona.signature_tag_extractor as signature  # noqa: E402
import sys_settings.llm_settings as llm_settings  # noqa: E402
from llm.persona import daily_maintenance as dm  # noqa: E402
from sys_settings.time_settings import APP_TZ  # noqa: E402

LOGGER = "llm.persona.daily_maintenance"
GUILD = SimpleNamespace(id=9, emojis=[])


class _Steps:
    """把四個步驟換成假函式，記下呼叫順序與參數；`fail` 指定哪幾步要炸；`gate` 讓 ③ 卡住等放行。"""

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []
        self.fail: set[str] = set()
        self.agent_enabled = True
        self.gate: asyncio.Event | None = None

    def _record(self, name, kwargs):
        self.calls.append((name, kwargs))
        if name in self.fail:
            raise RuntimeError(f"{name} 壞了")

    def patches(self):
        steps = self

        def emoji(guild):
            steps._record("①", {"guild": guild})

        async def sweep(guild):
            steps._record("②", {"guild": guild})

        async def batch(**kwargs):
            steps._record("③", kwargs)
            if steps.gate is not None:
                await steps.gate.wait()

        async def publish(**kwargs):
            steps._record("④", kwargs)

        return [
            mock.patch.object(extractor, "refresh_emoji_dictionary", emoji),
            mock.patch.object(signature, "run_signature_tag_sweep", sweep),
            mock.patch.object(agent_batch, "run_batch", batch),
            mock.patch.object(agent_publish, "run_publish", publish),
            mock.patch.object(agent_publish, "effective_publish_mode", lambda: "on"),
            mock.patch.object(member_names, "member_names_from_guild", lambda guild: {"1": ["甲"]}),
            mock.patch.object(llm_settings, "PersonaAgentSettings", lambda: SimpleNamespace(enabled=steps.agent_enabled)),
            mock.patch.object(dm, "load_llm_runtime_config", lambda path: SimpleNamespace(personality_model=None, model="主模型")),
        ]

    def names(self):
        return [name for name, _ in self.calls]

    def kwargs_of(self, name):
        return next(kwargs for n, kwargs in self.calls if n == name)


class RunOnceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.steps = _Steps()
        stack = contextlib.ExitStack()
        for patch in self.steps.patches():
            stack.enter_context(patch)
        self.addCleanup(stack.close)

    async def test_runs_four_steps_in_order(self):
        await dm.run_once(GUILD)
        self.assertEqual(self.steps.names(), ["①", "②", "③", "④"])
        batch = self.steps.kwargs_of("③")
        self.assertEqual((batch["guild_id"], batch["model"], batch["member_names"]), (9, "主模型", {"1": ["甲"]}))
        publish = self.steps.kwargs_of("④")
        self.assertEqual((publish["guild_id"], publish["mode"], publish["member_names"]), (9, "on", {"1": ["甲"]}))

    async def test_each_failure_is_logged_and_the_rest_still_runs(self):
        self.steps.fail = {"①", "②", "③"}
        with self.assertLogs(LOGGER, level="WARNING") as logs:
            await dm.run_once(GUILD)
        self.assertEqual(self.steps.names(), ["①", "②", "③", "④"])
        self.assertEqual(len([line for line in logs.output if "失敗" in line]), 3)

    async def test_agent_disabled_skips_the_batch_only(self):
        self.steps.agent_enabled = False
        await dm.run_once(GUILD)
        self.assertEqual(self.steps.names(), ["①", "②", "④"])

    async def test_publish_failure_is_logged_not_raised(self):
        self.steps.fail = {"④"}
        with self.assertLogs(LOGGER, level="ERROR"):
            await dm.run_once(GUILD)                  # 最後一步失敗也不能往外丟：排程那層會當成整輪失敗
        self.assertEqual(self.steps.names(), ["①", "②", "③", "④"])

    async def test_a_second_round_does_not_overlap_a_running_one(self):
        self.steps.gate = asyncio.Event()
        first = asyncio.ensure_future(dm.run_once(GUILD))
        for _ in range(3):
            await asyncio.sleep(0)                    # 第一輪跑到 ③、卡在 gate
        second = None
        try:
            with self.assertLogs(LOGGER, level="INFO") as logs:
                second = asyncio.ensure_future(dm.run_once(GUILD))
                for _ in range(5):
                    await asyncio.sleep(0)
                self.assertTrue(second.done(), "第二輪要直接退出，不能跟著跑、也不能等第一輪")
            self.assertTrue(any("略過" in line for line in logs.output))
            self.assertEqual(self.steps.names(), ["①", "②", "③"], "第二輪沒有多跑任何一步")
        finally:
            self.steps.gate.set()
            if second is not None and not second.done():
                second.cancel()
        await first
        self.assertEqual(self.steps.names(), ["①", "②", "③", "④"])
        await dm.run_once(GUILD)                      # 跑完之後要能再跑
        self.assertEqual(self.steps.names()[-4:], ["①", "②", "③", "④"])

    async def test_no_guild_does_nothing(self):
        with self.assertLogs(LOGGER, level="WARNING"):
            await dm.run_once(None)
        self.assertEqual(self.steps.calls, [])


class ScheduleMathTests(unittest.TestCase):
    def test_last_and_next_run_across_the_day_boundary(self):
        before = datetime(2026, 10, 13, 3, 59, tzinfo=APP_TZ)
        at = datetime(2026, 10, 13, 4, 0, tzinfo=APP_TZ)
        after = datetime(2026, 10, 13, 4, 1, tzinfo=APP_TZ)
        self.assertEqual(dm.last_scheduled_run(before), datetime(2026, 10, 12, 4, 0, tzinfo=APP_TZ))
        self.assertEqual(dm.last_scheduled_run(at), datetime(2026, 10, 13, 4, 0, tzinfo=APP_TZ))
        self.assertEqual(dm.last_scheduled_run(after), datetime(2026, 10, 13, 4, 0, tzinfo=APP_TZ))
        self.assertEqual(dm.next_run(before), datetime(2026, 10, 13, 4, 0, tzinfo=APP_TZ))
        self.assertEqual(dm.next_run(at), datetime(2026, 10, 14, 4, 0, tzinfo=APP_TZ))
        self.assertEqual(dm.next_run(after), datetime(2026, 10, 14, 4, 0, tzinfo=APP_TZ))


class CatchUpTests(unittest.IsolatedAsyncioTestCase):
    NOW = datetime(2026, 10, 13, 11, 20, tzinfo=APP_TZ)   # 上一個該跑的是 10-13 04:00

    def setUp(self):
        self.ran = []

        async def fake_run_once(guild):
            self.ran.append(guild)

        patcher = mock.patch.object(dm, "run_once", fake_run_once)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.bot = SimpleNamespace(guilds=[GUILD])

    async def _catch_up(self, last_utc):
        with mock.patch.object(extractor, "get_last_extraction_time", lambda guild_id: last_utc):
            return await dm.catch_up_if_missed(self.bot, now=self.NOW)

    async def test_no_record_catches_up(self):
        self.assertTrue(await self._catch_up(None))
        self.assertEqual(self.ran, [GUILD])

    async def test_older_than_last_scheduled_run_catches_up(self):
        yesterday_0545_utc = datetime(2026, 10, 11, 21, 45, tzinfo=timezone.utc)   # 本機時間 10-12 05:45 < 10-13 04:00
        self.assertTrue(await self._catch_up(yesterday_0545_utc))
        self.assertEqual(self.ran, [GUILD])

    async def test_already_ran_after_last_scheduled_run_skips(self):
        today_0545_utc = datetime(2026, 10, 12, 21, 45, tzinfo=timezone.utc)   # 本機時間 10-13 05:45 ≥ 10-13 04:00
        self.assertFalse(await self._catch_up(today_0545_utc))
        self.assertEqual(self.ran, [])

    async def test_without_guild_nothing_runs(self):
        self.bot.guilds = []
        self.assertFalse(await dm.catch_up_if_missed(self.bot, now=self.NOW))
        self.assertEqual(self.ran, [])


if __name__ == "__main__":
    unittest.main()
