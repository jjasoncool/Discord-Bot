"""到期迴圈：睡到下一個該醒的時刻、醒來做事、出錯不中斷。

專案裡各個定時功能（週期提醒、點名、人格萃取、日記）原本各自手寫一份 sleep 迴圈，
各自處理「啟動時補跑」「醒得太早又空轉」「一次出錯整個排程停掉」。這裡只抽機制，
「什麼時候到期、到期做什麼」留給呼叫端的 tick。

    task = asyncio.create_task(run_due_loop("交易領收期限", service.run_receipt_deadlines,
                                            wait_ready=bot.wait_until_ready))

tick 收到「現在」，處理所有已到期的事，回傳下一個該醒的時刻（沒有就回 None）。
啟動後會先 tick 一次：bot 停機期間錯過的到期項目就在這一次補做，所以 tick 要冪等
（已做過的不要再做，例如靠 StateDB `sent_content` 去重，或狀態本身就記在 Discord 上）。

既有的四份迴圈還沒搬過來（TR-Q9 決定逐步搬）；`test_shared_conventions` 擋第六份。
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Awaitable, Callable, Optional

from sys_settings.time_settings import APP_TZ

logger = logging.getLogger(__name__)

Tick = Callable[[datetime], Awaitable[Optional[datetime]]]


def _now() -> datetime:
    return datetime.now(APP_TZ)


async def run_due_loop(
    name: str,
    tick: Tick,
    *,
    wait_ready: Optional[Callable[[], Awaitable[object]]] = None,
    max_sleep: float = 3600,
    retry_after: float = 300,
    now: Callable[[], datetime] = _now,
    sleep: Callable[[float], Awaitable[object]] = asyncio.sleep,
) -> None:
    """一直跑到被 cancel。

    - `max_sleep`：單次最多睡多久。tick 沒有下一個時刻、或時刻很遠時，至少這麼久醒來重算一次，
      讓途中新增的到期項目（例如剛有人按了按鈕）不會被漏掉太久。
    - `retry_after`：tick 拋例外後隔多久重試；例外只記 log，迴圈不停。
    """
    if wait_ready is not None:
        await wait_ready()
    while True:
        try:
            wake_at = await tick(now())
        except Exception:
            logger.error("%s：排程執行失敗，%s 秒後重試", name, retry_after, exc_info=True)
            await sleep(retry_after)
            continue
        delay = max_sleep
        if wake_at is not None:
            # +1 秒：避免醒得稍早、還沒到期又空轉一輪
            delay = min(max_sleep, (wake_at - now()).total_seconds() + 1)
        await sleep(max(delay, 1))
