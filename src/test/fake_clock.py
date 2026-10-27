"""測試用的假時鐘：程式問時間、睡覺都問它，測試不用真的等，機器再忙結果也一樣。

用法：被測模組把「看時間」與「睡覺」做成可換的名字（例：`gpu_gate._clock`／`_async_sleep`、
轉發 worker 的 `_clock`／`_sleep`），測試裡換成 `clock.now`／`clock.sleep`。

機制：`sleep(秒)` 登記一個醒來時刻、等一個 future。等事件迴圈把手上能跑的都跑完（兩輪 `call_soon`），
再把時間撥到最早的醒來時刻、只叫醒那一個；被叫醒的任務跑到下一次睡覺再登記。幾個任務同時睡，
依醒來時刻先後叫醒，順序和真實時間一樣，但一秒都不用等。被取消的睡覺（任務被 cancel）直接略過。
"""
from __future__ import annotations

import asyncio
import heapq


class FakeClock:
    def __init__(self, start: float = 0.0) -> None:
        self._now = start
        self._waiters: list[tuple[float, int, asyncio.Future]] = []
        self._seq = 0
        self._tick_pending = False

    def now(self) -> float:
        return self._now

    async def sleep(self, seconds: float) -> None:
        loop = asyncio.get_running_loop()
        fut: asyncio.Future = loop.create_future()
        heapq.heappush(self._waiters, (self._now + max(0.0, float(seconds)), self._seq, fut))
        self._seq += 1
        self._arm(loop)
        await fut

    def _arm(self, loop: asyncio.AbstractEventLoop) -> None:
        if not self._tick_pending:
            self._tick_pending = True
            # 兩輪 call_soon：讓剛被叫醒、剛開始的任務有機會登記自己的睡覺，再決定誰最早
            loop.call_soon(lambda: loop.call_soon(self._tick))

    def _tick(self) -> None:
        self._tick_pending = False
        while self._waiters and self._waiters[0][2].done():
            heapq.heappop(self._waiters)          # 被 cancel 的任務：它的 future 已經結束，跳過
        if not self._waiters:
            return
        wake, _, fut = heapq.heappop(self._waiters)
        self._now = max(self._now, wake)
        fut.set_result(None)
        if self._waiters:
            self._arm(asyncio.get_running_loop())
