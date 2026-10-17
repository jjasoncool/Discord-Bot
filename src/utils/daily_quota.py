"""每天最多做幾次的計數：換日歸零、先扣再做。

架構定位：基礎層（`utils/`），只依賴標準庫。上層：看圖補字典（`llm.preprocess.emoji_autofill`）、插話的查詢
（`llm.ambient.ambient_search`）。下層：無。

介面：
- `DailyQuota(limit)`：`take(now, limit=None) -> bool`（先扣再做，用完回 False）、`used(now)`、
  `remaining(now, limit=None)`、`reset()`。

規則：
- `now` 由呼叫端給（用 `APP_TZ` 的現在時間），這裡不看時鐘，測試才換得掉。
- 只存在行程記憶體：重啟歸零。bot 很少重啟，額度本來就是粗略的節流，不值得落地。
- 上限可以每次呼叫再給：設定被換掉（測試、熱讀）時不用重建計數器。

例外與決策：不管維護時段——插話在那段時間本來就讓位，看圖補字典自己判斷時段；計數器只做計數。
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional


class DailyQuota:
    def __init__(self, limit: int) -> None:
        self.limit = int(limit)
        self._day = ""
        self._used = 0

    def _roll(self, now: datetime) -> None:
        day = now.strftime("%Y-%m-%d")
        if day != self._day:
            self._day, self._used = day, 0

    def used(self, now: datetime) -> int:
        self._roll(now)
        return self._used

    def remaining(self, now: datetime, limit: Optional[int] = None) -> int:
        self._roll(now)
        return max(0, (self.limit if limit is None else int(limit)) - self._used)

    def take(self, now: datetime, limit: Optional[int] = None) -> bool:
        """扣一次；今天已經用完就回 False、不扣。"""
        if self.remaining(now, limit) <= 0:
            return False
        self._used += 1
        return True

    def reset(self) -> None:
        self._day, self._used = "", 0
