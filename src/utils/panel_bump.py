"""面板置底：刪掉上一則面板、在頻道最底下發一則新的，並記住它在哪。

自介、社群查詢、週期提醒三個常駐面板共用（音樂面板的生命週期不同，暫未接入）。
面板長什麼樣由呼叫端的 `send` 決定，這裡只管「在哪、刪舊、發新、記住、同時只做一次」。

- 位置記在各自的 runtime 檔（不進版控）：`{key_prefix}channel_id`／`{key_prefix}message_id`，
  寫入時保留檔案裡的其他欄位。
- **沒有完整紀錄時**（第一次上線、runtime 檔被刪、舊版只記了訊息 id）才翻頻道最近的訊息，
  刪掉 bot 自己發、按鈕 custom_id 屬於這個面板的殘留面板。custom_id 用**精確比對**，
  不會誤刪同一功能的其他按鈕訊息。
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Awaitable, Callable, Iterable, Optional

import discord

logger = logging.getLogger(__name__)

SendPanel = Callable[[discord.abc.Messageable], Awaitable[discord.Message]]


def load_runtime(path: str) -> dict:
    """讀 runtime json；沒有檔案或壞掉都回空 dict。"""
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.warning("讀取 runtime 檔失敗 (%s): %s", path, e)
        return {}


def update_runtime(path: str, **fields) -> None:
    """把欄位合併寫回 runtime json（保留檔案裡的其他欄位）。"""
    data = load_runtime(path)
    data.update(fields)
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error("寫入 runtime 檔失敗 (%s): %s", path, e)


class PanelBumper:
    def __init__(self, runtime_path: str, send: SendPanel, *, custom_ids: Iterable[str],
                 key_prefix: str = "panel_", scan_limit: int = 50):
        self.runtime_path = runtime_path
        self._send = send
        self._custom_ids = frozenset(custom_ids)
        self._channel_key = f"{key_prefix}channel_id"
        self._message_key = f"{key_prefix}message_id"
        self._scan_limit = scan_limit
        self._lock = asyncio.Lock()
        self._pending: Optional[discord.abc.Messageable] = None
        self._drain_task: Optional[asyncio.Task] = None

    async def bump(self, channel) -> tuple[discord.Message, bool]:
        """刪舊發新，回傳 (新面板, 有沒有刪到舊的)。發送失敗會往上拋。"""
        async with self._lock:
            deleted_old = await self._delete_old(channel)
            message = await self._send(channel)
            update_runtime(self.runtime_path, **{self._channel_key: channel.id, self._message_key: message.id})
            return message, deleted_old

    async def bump_safe(self, channel) -> Optional[discord.Message]:
        """事件觸發用：失敗只記 log，不打斷呼叫端。"""
        try:
            message, _ = await self.bump(channel)
            return message
        except Exception as e:
            logger.error("面板置底失敗 (%s): %s", self.runtime_path, e, exc_info=True)
            return None

    def request_bump(self, channel) -> None:
        """立即置底，連發時合併：同時最多一次在跑、一次排隊（有人講話就置底用）。"""
        self._pending = channel
        if self._drain_task is None or self._drain_task.done():
            self._drain_task = asyncio.create_task(self._drain())

    async def _drain(self) -> None:
        while self._pending is not None:
            channel, self._pending = self._pending, None
            await self.bump_safe(channel)

    async def _delete_old(self, channel) -> bool:
        runtime = load_runtime(self.runtime_path)
        channel_id, message_id = runtime.get(self._channel_key), runtime.get(self._message_key)
        if not (channel_id and message_id):
            return await self._delete_strays(channel)
        old_channel = channel if int(channel_id) == channel.id else channel.guild.get_channel(int(channel_id))
        if old_channel is None:
            return False
        try:
            await old_channel.get_partial_message(int(message_id)).delete()
            return True
        except discord.NotFound:
            return False  # 已經被刪掉了
        except discord.HTTPException as e:
            logger.warning("刪除舊面板失敗 (%s): %s", self.runtime_path, e)
            return False

    async def _delete_strays(self, channel) -> bool:
        """沒有紀錄時：翻最近的訊息，刪掉 bot 自己發的同款面板。"""
        me = channel.guild.me
        deleted = False
        async for message in channel.history(limit=self._scan_limit):
            if message.author.id != me.id or not self._is_panel(message):
                continue
            try:
                await message.delete()
                deleted = True
                logger.info("已清掉沒有紀錄的殘留面板 message_id=%s (%s)", message.id, self.runtime_path)
            except discord.HTTPException as e:
                logger.warning("清除殘留面板失敗 message_id=%s: %s", message.id, e)
        return deleted

    def _is_panel(self, message: discord.Message) -> bool:
        for row in message.components:
            for child in getattr(row, "children", ()):
                if getattr(child, "custom_id", None) in self._custom_ids:
                    return True
        return False
