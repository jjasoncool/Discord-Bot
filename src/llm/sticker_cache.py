"""Discord 貼圖描述快取。

bot 啟動時預載所有 guild sticker 的 name + description，
供聊天 context 組裝與訊息持久化使用。
"""
from __future__ import annotations

import logging
from typing import Optional

import discord

logger = logging.getLogger("discord_bot")

# 模組級快取：sticker_id → "名稱｜描述"
_sticker_cache: dict[int, str] = {}


async def load_guild_stickers(bot: discord.Client) -> int:
    """預載所有 guild 的 sticker，回傳載入數量。"""
    loaded = 0
    for guild in bot.guilds:
        try:
            stickers = await guild.fetch_stickers()
            for sticker in stickers:
                desc = sticker.description or sticker.name
                _sticker_cache[sticker.id] = f"{sticker.name}｜{desc}"
                loaded += 1
        except Exception as exc:
            logger.warning("載入 guild %s 的貼圖失敗: %s", guild.id, exc)
    logger.info("已載入 %d 個貼圖描述", loaded)
    return loaded


def get_sticker_text(sticker: discord.StickerItem) -> Optional[str]:
    """查詢貼圖描述，回傳格式化文字或 None。"""
    cached = _sticker_cache.get(sticker.id)
    if cached:
        return f"[貼圖：{cached}]"
    # 非 guild sticker（標準貼圖），只用名稱
    return f"[貼圖：{sticker.name}]"
