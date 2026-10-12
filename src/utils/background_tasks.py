"""背景任務的統一入口：建任務、留著參照、結束時看得到結果，該一直跑的掛了就重啟。

為什麼要有這個：`asyncio.create_task(coro)` 不留參照會發生兩件事——任務物件可能被回收（Python 文件明講
event loop 只留弱參照），以及任務裡沒接住的例外只會在被回收時印一行「Task exception was never retrieved」，
沒有人知道哪個功能停了。2026-10-12 盤點全專案有 16 處這樣寫（on_message 的記憶寫入、插話、字典補、
通知處理、巴哈同步…），另外十幾個「該一直跑」的迴圈各自留參照、各自決定出錯要不要繼續。

    spawn(flush_buffer(), name="聊天記憶寫入")                 # 做一件事就結束：留參照到做完、失敗記 ERROR
    supervise(lambda: relay.listen_loop(), name="Telegram 監聽")  # 該一直跑：掛了記 ERROR、等一下重啟

  - `spawn`：被取消不算失敗（關機、逾時中止都是正常路徑）。
  - `supervise`：`factory` 每次重啟都重新呼叫（coroutine 用過一次就不能再 await）。第一次在 `supervise()` 裡
    當場呼叫——和原本 `create_task(coro)` 的時機一樣，參數寫錯會立刻在呼叫端炸，不會躲進背景每 5 秒重試一次。
    重啟間隔從 `restart_after` 起每次加倍、到 `max_restart_after` 為止；跑滿 `healthy_after` 秒才掛掉的，
    視為新的一次故障、間隔重算。迴圈自己正常結束記 WARNING、不重啟（正常的迴圈不該結束，多半是忘了 `while True`）。
  - 這裡只管「建、留、記、重啟」。工作本身的節流、去重、等 GPU 都留給呼叫端；`run_due_loop` 管的是
    「什麼時候醒來」，兩者是搭配不是取代。

守衛（`test_shared_conventions`）擋「結果被丟掉的 `create_task`」：要 fire-and-forget 就走 `spawn`。
"""
from __future__ import annotations

import asyncio
import inspect
import logging
import time
from typing import Awaitable, Callable, Coroutine, Optional

logger = logging.getLogger(__name__)

#: 還沒做完的任務；留著參照，event loop 才不會把它們回收
_tasks: set[asyncio.Task] = set()


def spawn(coro: Coroutine, *, name: str) -> asyncio.Task:
    """建一個背景任務：做完自動放掉參照；拋例外記 ERROR（含名稱與堆疊）；被取消不記。"""
    task = asyncio.get_running_loop().create_task(coro, name=name)
    _tasks.add(task)
    task.add_done_callback(_on_done)
    return task


def _on_done(task: asyncio.Task) -> None:
    _tasks.discard(task)
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.error("背景任務「%s」失敗：%s: %s", task.get_name(), type(exc).__name__, exc, exc_info=exc)


def supervise(
    factory: Callable[[], Awaitable[None]],
    *,
    name: str,
    restart_after: float = 5.0,
    max_restart_after: float = 300.0,
    healthy_after: float = 60.0,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> asyncio.Task:
    """讓一個該一直跑的迴圈真的一直跑：掛了記 ERROR、等一下重新呼叫 `factory`；被取消才停。回傳的 task 可以 cancel。"""
    first = factory()   # 現在就建第一個 coroutine：factory 本身寫錯（參數不對）在這裡就炸，不會躲進背景重試

    async def _run(current) -> None:
        delay = restart_after
        while True:
            started = clock()
            try:
                await current
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if clock() - started >= healthy_after:
                    delay = restart_after
                logger.error("背景迴圈「%s」掛了：%s: %s；%g 秒後重新啟動", name, type(exc).__name__, exc, delay,
                             exc_info=exc)
                await sleep(delay)
                delay = min(delay * 2, max_restart_after)
                current = factory()
                continue
            logger.warning("背景迴圈「%s」自己結束了（正常的迴圈不該結束），不再重啟", name)
            return

    task = spawn(_run(first), name=name)
    # 任務還沒輪到執行就被取消時，第一個 coroutine 不會被 await 到；關掉它，不然 Python 會抱怨「never awaited」
    task.add_done_callback(lambda _t: first.close() if inspect.getcoroutinestate(first) == inspect.CORO_CREATED else None)
    return task


def pending() -> list[str]:
    """還在跑的背景任務名稱（給診斷、測試看）。"""
    return sorted(task.get_name() for task in _tasks if not task.done())


def cancel_all() -> int:
    """取消所有還在跑的背景任務（關機、測試收尾用）；回傳取消了幾個。"""
    live = [task for task in _tasks if not task.done()]
    for task in live:
        task.cancel()
    return len(live)


async def wait_all(timeout: Optional[float] = None) -> None:
    """等所有背景任務結束（測試用；正式程式關機時搭配 `cancel_all`）。"""
    live = [task for task in _tasks if not task.done()]
    if live:
        await asyncio.wait(live, timeout=timeout)
