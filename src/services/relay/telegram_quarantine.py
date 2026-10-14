"""Telegram 過濾的隔離區：每個轉發主頻道底下一個「垃圾訊息」thread。

- 判成垃圾的訊息送進這裡，發送紀錄記這個 thread 的 id（不建新表）。
- **記住歷來所有隔離 thread**（runtime 檔）：認「這筆紀錄是不是隔離」要看 id 是不是在這份清單裡，不能用
  「不在路由裡、也不是 0」——主頻道一改綁，幾千筆舊的主頻道紀錄會全被當成隔離。thread 被刪重建後 id 會變，
  舊紀錄仍認得出來，晚到的圖改送到現在的 thread。
- thread 找不到就依名稱找（bot 自己開的、名稱相符，封存的也找），再找不到就重建；封存的先解封。
- 開 thread 時指定 7 天才自動封存（主頻道預設 24 小時，一天只進一兩則，幾乎都會是封存狀態）。
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Awaitable, Callable, Optional

import discord

from utils.discord_threads import fetch_thread, reopen_thread
from utils.panel_bump import load_runtime, update_runtime
from sys_settings.paths import runtime_path
from utils.background_tasks import spawn

logger = logging.getLogger(__name__)

THREAD_NAME = "垃圾訊息"
#: 隔離 thread 與面板位置（bot 自己寫的狀態，不進版控）
RUNTIME_PATH = runtime_path("telegram_quarantine.json")  # services/relay/ 往上兩層是 src/
#: 一週沒人講話才封存（Discord 允許的最長值）
_AUTO_ARCHIVE_MINUTES = 10080


class QuarantineThreads:
    """主頻道 → 它底下的隔離 thread。runtime 檔記 `threads`（主頻道 → 現在的 thread）與
    `thread_parents`（歷來每個隔離 thread → 主頻道）。"""

    def __init__(self, bot: discord.Client, runtime_path: str,
                 on_change: Optional[Callable[[int, discord.Thread], Awaitable[None]]] = None) -> None:
        self.bot = bot
        self.runtime_path = runtime_path
        #: 隔離區有變動（多一則、放回一則）時通知面板置底重畫：(主頻道 id, thread)
        self.on_change = on_change
        self._state: Optional[dict] = None
        self._lock = asyncio.Lock()
        #: 問過 Discord、確定不是隔離 thread 的頻道（例如別的路由的主頻道），不再重問
        self._not_quarantine: set[str] = set()

    async def _load(self) -> dict:
        if self._state is None:
            data = await asyncio.to_thread(load_runtime, self.runtime_path)
            # 讀檔途中可能有別人先讀完、還記了新的 thread：只採用第一個讀完的，不然會用舊內容蓋掉
            if self._state is None:
                self._state = {
                    "threads": dict(data.get("threads") or {}),
                    "thread_parents": dict(data.get("thread_parents") or {}),
                }
        return self._state

    async def parent_of(self, channel_id: int) -> Optional[int]:
        """這個頻道是隔離 thread 的話，回它的主頻道；不是回 None。

        runtime 檔裡沒有時（檔案被刪、寫入失敗）問 Discord：是 bot 自己開的「垃圾訊息」thread 就補記回去。
        認不出來的話，被隔離相簿晚到的圖會讓整本被當成新相簿重判、可能整本貼進主頻道。
        """
        state = await self._load()
        key = str(int(channel_id))
        parent = state["thread_parents"].get(key)
        if parent is not None:
            return int(parent)
        if key in self._not_quarantine:
            return None
        thread = await fetch_thread(self.bot, int(channel_id))
        me = getattr(getattr(self.bot, "user", None), "id", None)
        if (thread is not None and getattr(thread, "name", None) == THREAD_NAME
                and getattr(thread, "owner_id", me) == me and getattr(thread, "parent_id", None)):
            logger.warning("runtime 檔沒記到隔離 thread %s，依 Discord 補記（主頻道 %s）", channel_id, thread.parent_id)
            await self._remember_parent(int(thread.parent_id), int(channel_id))
            return int(thread.parent_id)
        self._not_quarantine.add(key)
        return None

    async def thread_ids_of(self, parent_id: int) -> list[int]:
        """這個主頻道歷來的隔離 thread（含被刪重建前的舊 thread）。"""
        state = await self._load()
        return [int(t) for t, p in state["thread_parents"].items() if int(p) == int(parent_id)]

    async def current_thread(self, parent_id: int) -> Optional[discord.Thread]:
        """主頻道現在的隔離 thread；不存在就回 None（不會新開）。"""
        state = await self._load()
        return await fetch_thread(self.bot, state["threads"].get(str(int(parent_id))))

    def changed(self, parent_id: int, thread: discord.Thread) -> None:
        """隔離區有變動：背景通知面板，不擋呼叫端，失敗只記 log。"""
        if self.on_change is None:
            return

        async def run() -> None:
            try:
                await self.on_change(parent_id, thread)
            except Exception as exc:
                logger.warning("通知隔離區面板失敗 parent=%s：%s", parent_id, exc)

        spawn(run(), name="隔離區面板通知")

    async def thread_for(self, parent: discord.abc.Messageable) -> Optional[discord.Thread]:
        """主頻道底下的隔離 thread（找不到就開一個，封存的先解封）；開不了回 None。"""
        async with self._lock:
            state = await self._load()
            parent_id = int(parent.id)
            thread = await fetch_thread(self.bot, state["threads"].get(str(parent_id)))
            if thread is None:
                thread = await self._find_by_name(parent)
            if thread is None:
                try:
                    thread = await parent.create_thread(
                        name=THREAD_NAME,
                        type=discord.ChannelType.public_thread,
                        auto_archive_duration=_AUTO_ARCHIVE_MINUTES,
                        reason="Telegram 過濾：放判成垃圾的訊息",
                    )
                except (discord.HTTPException, AttributeError) as exc:
                    logger.error("開隔離 thread 失敗 parent=%s：%s", parent_id, exc)
                    return None
                logger.info("已開隔離 thread：parent=%s thread=%s", parent_id, thread.id)
            await reopen_thread(thread)
            await self._remember(parent_id, int(thread.id))
            return thread

    async def _find_by_name(self, parent) -> Optional[discord.Thread]:
        """id 遺失時的後備：bot 自己開、名稱相符的 thread（先找活躍的，再找封存的）。"""
        me = getattr(getattr(self.bot, "user", None), "id", None)

        def mine(t) -> bool:
            return getattr(t, "name", None) == THREAD_NAME and getattr(t, "owner_id", me) == me

        for t in getattr(parent, "threads", None) or []:
            if mine(t):
                return t
        if not getattr(parent, "threads", None):
            # 快取是空的（只走 HTTP 的一次性腳本沒有快取；或真的沒有活躍 thread）：問 Discord 活躍中的。
            # 不問的話腳本看不到 bot 開著的那個，會再開一個
            try:
                for t in await parent.guild.active_threads():
                    if getattr(t, "parent_id", None) == parent.id and mine(t):
                        return t
            except (discord.HTTPException, AttributeError) as exc:
                logger.info("查活躍的 thread 失敗 parent=%s：%s", getattr(parent, "id", None), exc)
        try:
            async for t in parent.archived_threads(limit=None):
                if mine(t):
                    return t
        except (discord.HTTPException, AttributeError) as exc:
            logger.info("翻封存的 thread 失敗 parent=%s：%s", getattr(parent, "id", None), exc)
        return None

    async def _remember(self, parent_id: int, thread_id: int) -> None:
        state = self._state
        if (state["threads"].get(str(parent_id)) == thread_id
                and state["thread_parents"].get(str(thread_id)) == parent_id):
            return
        state["threads"][str(parent_id)] = thread_id
        await self._remember_parent(parent_id, thread_id)

    async def _remember_parent(self, parent_id: int, thread_id: int) -> None:
        """記住這個 thread 是哪個主頻道的隔離區（歷來的都留著）。"""
        state = await self._load()
        state["thread_parents"][str(thread_id)] = parent_id
        current = state["threads"].get(str(parent_id))
        await asyncio.to_thread(self._write, parent_id, thread_id, current)

    def _write(self, parent_id: int, thread_id: int, current: Optional[int]) -> None:
        """只把這次的變動合併進檔案：先重讀檔案、只改這個主頻道與這個 thread。一次性搬移腳本跟 bot 是兩個
        行程、各有一份記憶體；拿記憶體整份寫回，會把對方剛記的 thread 蓋回舊的。"""
        data = load_runtime(self.runtime_path)
        threads = dict(data.get("threads") or {})
        parents = dict(data.get("thread_parents") or {})
        parents[str(thread_id)] = parent_id
        if current == thread_id:
            threads[str(parent_id)] = thread_id
        update_runtime(self.runtime_path, threads=threads, thread_parents=parents)
