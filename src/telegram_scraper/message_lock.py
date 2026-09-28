"""以「單則訊息」為單位的鎖：同一則訊息互斥，不同訊息各跑各的。"""

import asyncio
import contextlib
from typing import Any, AsyncIterator, Hashable


class KeyedLock:
    """每個 key 各自一把 asyncio.Lock。

    沒人持有、也沒人在等的 key 立刻回收，避免長時間運行後 dict 無限長大。
    """

    def __init__(self) -> None:
        self._locks: dict[Hashable, asyncio.Lock] = {}
        self._users: dict[Hashable, int] = {}

    @contextlib.asynccontextmanager
    async def hold(self, key: Hashable) -> AsyncIterator[None]:
        lock = self._locks.get(key)
        if lock is None:
            lock = self._locks[key] = asyncio.Lock()
        self._users[key] = self._users.get(key, 0) + 1
        try:
            async with lock:
                yield
        finally:
            # 等鎖途中被取消也會走到這裡，計數才不會漏減
            self._users[key] -= 1
            if self._users[key] == 0:
                del self._users[key]
                del self._locks[key]

    def __len__(self) -> int:
        return len(self._locks)


def message_lock_key(message: Any) -> tuple[int, int]:
    """鎖的 key：(chat_id, message_id)。

    即時事件、補掃、refetch 拿到的都是 Telethon Message，chat_id 皆為 marked id，
    三條路徑對同一則訊息算出的 key 一致；帶上 chat_id 避免多來源頻道 message_id 撞號。
    """
    return (int(getattr(message, "chat_id", 0) or 0), int(message.id))
