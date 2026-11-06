"""全程式共用一份的資源（例：資料庫連線）：第一次要用時才開，同時要的只開一次；停機關掉之後不再開。

架構定位：基礎層（`utils/`），只依賴標準庫。
  - 上層（誰呼叫）：服務層的資料庫模組，各自包一個 `SharedResource`，對外照舊給 `get_shared_*`／`close_shared_*`
    （例：`services.state_db` 的轉發狀態資料庫、`services.market_db` 的市集資料庫）。
  - 下層（呼叫誰）：asyncio。

介面：
  - `SharedResource(name, open, close)`：`open()` 建好並回傳一份資源、`close(資源)` 把它關掉，都由呼叫端給。
  - `await get()`：取得那一份；還沒開就呼叫 `open()`，同時要的協程只開一次。關掉之後丟 RuntimeError。
  - `await close()`：停機時關掉；沒開過也能關、重複呼叫不出錯。之後 `get()` 不再開新的。
  - `current`：目前那一份，沒開或已關是 None。
  - `reset()`／`restore(state)`：只給測試：回到「沒開、沒關」，用完放回原本的狀態。

規則：
  - 資源怎麼開、怎麼關由呼叫端決定；這裡只管「只開一次、關了就不再開」。
  - 一個資源一個 `SharedResource`，放在提供那個資源的模組裡（模組層級），別處不另外存一份。

例外與決策：
  - 關掉之後不再開：停機時漏網的工作（撐過取消、或收尾途中才跑的）又來拿，新開的那份沒人關；
    aiosqlite 每條連線背後有一條非 daemon 執行緒，沒關的話行程退不出去。
"""
from __future__ import annotations

import asyncio
from typing import Awaitable, Callable, Generic, Optional, TypeVar

T = TypeVar("T")


class SharedResource(Generic[T]):
    """全程式共用的一份資源。"""

    def __init__(self, name: str, open: Callable[[], Awaitable[T]], close: Callable[[T], Awaitable[None]]):
        self.name = name
        self._open = open
        self._close = close
        self._lock = asyncio.Lock()
        self._value: Optional[T] = None
        self._closed = False

    @property
    def current(self) -> Optional[T]:
        return self._value

    async def get(self) -> T:
        async with self._lock:
            if self._value is None:
                if self._closed:
                    raise RuntimeError(f"停機中：共用的{self.name}已關閉，不再開新的")
                self._value = await self._open()
            return self._value

    async def close(self) -> None:
        async with self._lock:
            value, self._value = self._value, None
            self._closed = True
        if value is not None:
            await self._close(value)

    def reset(self) -> tuple[Optional[T], bool]:
        """測試用：回到沒開、沒關的狀態，回傳原本的狀態給 `restore`。"""
        state = (self._value, self._closed)
        self._value, self._closed = None, False
        return state

    def restore(self, state: tuple[Optional[T], bool]) -> None:
        self._value, self._closed = state
