"""thread 的取得與解封。

**為什麼要先解封**：封存中的 thread 改不了、也刪不了訊息（Discord 回 50083），一天只進一兩則的 thread
一定會被自動封存。送訊息雖然會自動解封，但編輯舊訊息、刪舊面板不會，要自己先解封。

**為什麼取得要兩步**：`get_channel` 只看快取，封存的 thread 不在快取裡，要再 `fetch_channel`。
"""
from __future__ import annotations

import logging
from typing import Optional

import discord

logger = logging.getLogger(__name__)


async def fetch_thread(client: discord.Client, thread_id: Optional[int]) -> Optional[discord.Thread]:
    """id → thread（封存的也拿得到）；不存在、沒權限、不是 thread 都回 None。"""
    if not thread_id:
        return None
    channel = client.get_channel(int(thread_id))
    if channel is None:
        try:
            channel = await client.fetch_channel(int(thread_id))
        except (discord.NotFound, discord.Forbidden):
            return None
        except discord.HTTPException as exc:
            logger.warning("取得 thread 失敗 thread_id=%s：%s", thread_id, exc)
            return None
    # 只有 thread 有 archived（文字頻道、論壇沒有）；用屬性判斷，測試的假 thread 才用得了
    return channel if hasattr(channel, "archived") else None


async def reopen_thread(thread: discord.Thread) -> bool:
    """封存的 thread 先解封；回傳現在是不是可以編輯的狀態。"""
    if not getattr(thread, "archived", False):
        return True
    try:
        await thread.edit(archived=False)
        return True
    except discord.HTTPException as exc:
        logger.warning("解除 thread 封存失敗 thread_id=%s：%s", getattr(thread, "id", None), exc)
        return False
