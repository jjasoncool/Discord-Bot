"""search-mcp 的背景工作：定期同步搜尋索引、每日補算新文章的向量。`llm.mcp_server --http` 啟動時開。

定期同步（每 `background_sync_seconds` 秒）：
  - 巴哈爬蟲每小時重存約 2 萬列（多半只是「最後看到時間」變了），同步要把它們讀出來比對內容。爬蟲剛寫完時
    這些資料還在記憶體快取裡，讀出來很快（查詢約 0.14 秒；上線後第一次在爬蟲寫完時跑的背景同步，含寫進索引
    共 7.0 秒，2026-10-09 實測）；拖到幾小時後才同步，可能要從硬碟到處讀，估計十幾秒以上（冷快取無法刻意
    重現，沒實測）。所以趁熱在背景先同步
  - 一直失敗時（例如索引是新版程式建的）：同樣的錯誤只完整記一次，間隔逐次拉長到最多一小時，恢復時記一行
  - 和搜尋共用同一個索引物件（`default_index`）：間隔比搜尋時的同步間隔短，搜尋那邊看到剛同步過就不再同步
  - 沒有變動時每次約 10 毫秒（爬蟲的表有 (updated_at, id) 索引，見 `sources.Source._changed_rows`）

每日維護：
  - 為什麼要有：關鍵字索引會跟上，向量卻要另外算（佔 GPU，不能等到搜尋時才算）；沒算的話新文章語意搜尋找不到
  - 時刻：每天 `nightly_at`（03:00）；過了 `nightly_deadline`（04:00）還沒做就等明天——04:00～07:30 是維護時段
    （人格萃取、persona agent 用模型），不去搶 GPU。漏掉一天不會少算：每次都是把「還沒算的」全部補完
  - 重做無害：同步是增量的、沒變的段落不重算；所以只在記憶體記「今天做過了」，容器在時段內重開就再做一次
  - 向量開關（`search_vector_mode`）關著時只同步、不算向量

兩件事都走 `utils.due_loop.run_due_loop`，在自己的執行緒與 event loop 上跑，不佔 MCP 處理請求的那一個。
"""
from __future__ import annotations

import asyncio
import logging
import threading
from datetime import date, datetime, time, timedelta
from typing import Callable, Optional

from sys_settings.search_settings import SEARCH_SETTINGS
from utils.due_loop import run_due_loop

logger = logging.getLogger(__name__)


class NightlyJob:
    """給 `run_due_loop` 的 tick：在時段內、而且今天還沒做過，就做一次；回傳下一次該醒的時刻。"""

    def __init__(self, job: Callable[[], object], *, at: time = SEARCH_SETTINGS.nightly_at,
                 deadline: time = SEARCH_SETTINGS.nightly_deadline):
        self.job, self.at, self.deadline = job, at, deadline
        self._done_on: Optional[date] = None

    async def tick(self, now: datetime) -> datetime:
        today = now.date()
        start = datetime.combine(today, self.at, tzinfo=now.tzinfo)
        deadline = datetime.combine(today, self.deadline, tzinfo=now.tzinfo)
        if start <= now < deadline and self._done_on != today:
            # 先記再做：做到一半出錯也不在同一個時段裡反覆重試、一直佔 GPU；明天會把今天的份一起補
            self._done_on = today
            await asyncio.to_thread(self.job)
        return start if now < start else start + timedelta(days=1)


class PeriodicSync:
    """給 `run_due_loop` 的 tick：同步一次，回傳下一次的時刻。同步本身是阻塞的 SQLite 讀寫，丟到執行緒做。

    失敗自己接住、不丟給 `run_due_loop`：那邊每次出錯都記完整 traceback、固定間隔重試，同步一直失敗
    （例如索引是新版程式建的，重開前不會好）時每 50 秒刷一次 ERROR。"""

    def __init__(self, sync: Callable[[], object], *,
                 every_seconds: float = SEARCH_SETTINGS.background_sync_seconds,
                 max_backoff_seconds: float = 3600.0):
        self.sync, self.every_seconds, self.max_backoff_seconds = sync, every_seconds, max_backoff_seconds
        self._failures = 0
        self._last_error: Optional[str] = None

    async def tick(self, now: datetime) -> datetime:
        try:
            await asyncio.to_thread(self.sync)
        except Exception as exc:
            self._failures += 1
            error = f"{type(exc).__name__}: {exc}"
            if error != self._last_error:
                logger.error("搜尋索引背景同步失敗：%s", error, exc_info=True)
                self._last_error = error
            else:
                logger.warning("搜尋索引背景同步仍然失敗（連續 %d 次）：%s", self._failures, error)
            delay = min(self.every_seconds * 2 ** self._failures, self.max_backoff_seconds)
            return now + timedelta(seconds=delay)
        if self._failures:
            logger.info("搜尋索引背景同步恢復正常（之前連續失敗 %d 次）", self._failures)
            self._failures, self._last_error = 0, None
        return now + timedelta(seconds=self.every_seconds)


def run_once() -> None:
    """同步索引；向量開關開著就把新文章的向量補完。"""
    from services.search.embed import embed_pending
    from services.search.index import default_index
    from sys_settings import switches

    index = default_index()
    if switches.current().search_vector_mode != "on" or index.vector_store is None:
        report = index.sync(force=True)
        logger.info("每日維護：向量開關關著，只同步索引（新增 %d、更新 %d、移除 %d）",
                    report.added, report.updated, report.removed)
        return
    logger.info("每日維護：同步索引、補算新文章的向量")
    embed_pending(index, index.vector_store)


def sync_index() -> None:
    """背景同步：一定做（不看最短間隔），搜尋那邊共用同一個索引物件，看得到剛同步過。"""
    from services.search.index import default_index

    default_index().sync(force=True)


def start_in_background(job: Callable[[], object] = run_once,
                        sync: Callable[[], object] = sync_index) -> threading.Thread:
    """開一條背景執行緒跑定期同步與每日維護；daemon，主程式（MCP 服務）結束就跟著結束。"""
    nightly = NightlyJob(job)
    periodic = PeriodicSync(sync)

    async def run_all() -> None:
        await asyncio.gather(
            run_due_loop("搜尋索引定期同步", periodic.tick, retry_after=periodic.every_seconds),
            run_due_loop("搜尋索引每日維護", nightly.tick),
        )

    thread = threading.Thread(target=asyncio.run, args=(run_all(),), name="search_background", daemon=True)
    thread.start()
    logger.info("搜尋索引背景工作已開始：每 %g 秒同步；每天 %s～%s 之間補算向量", periodic.every_seconds,
                nightly.at.strftime("%H:%M"), nightly.deadline.strftime("%H:%M"))
    return thread
