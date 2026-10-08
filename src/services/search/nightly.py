"""每日維護：同步搜尋索引、補算新文章的向量。search-mcp 服務（`llm.mcp_server --http`）啟動時在背景開著。

為什麼要有：關鍵字索引在搜尋當下會自動跟上，向量卻要另外算（佔 GPU，不能等到搜尋時才算）；
原本要手動跑 `python -m services.search.embed`，沒跑的話新文章一直沒有向量，語意搜尋找不到它們。

  - 時刻：每天 `nightly_at`（03:00）；過了 `nightly_deadline`（04:00）還沒做就等明天——04:00～07:30 是維護時段
    （人格萃取、persona agent 用模型），不去搶 GPU。漏掉一天不會少算：每次都是把「還沒算的」全部補完
  - 重做無害：同步是增量的、沒變的段落不重算；所以只在記憶體記「今天做過了」，容器在時段內重開就再做一次
  - 向量開關（`search_vector_mode`）關著時只同步、不算向量
  - 排程走 `utils.due_loop.run_due_loop`，在自己的執行緒與 event loop 上跑，不佔 MCP 處理請求的那一個
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


def start_in_background(job: Callable[[], object] = run_once) -> threading.Thread:
    """開一條背景執行緒跑每日維護；daemon，主程式（MCP 服務）結束就跟著結束。"""
    nightly = NightlyJob(job)
    thread = threading.Thread(target=asyncio.run, args=(run_due_loop("搜尋索引每日維護", nightly.tick),),
                              name="search_nightly", daemon=True)
    thread.start()
    logger.info("搜尋索引每日維護已排程：每天 %s～%s 之間做一次", nightly.at.strftime("%H:%M"),
                nightly.deadline.strftime("%H:%M"))
    return thread
