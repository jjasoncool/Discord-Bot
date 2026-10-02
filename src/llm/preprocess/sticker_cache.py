"""Discord 貼圖描述快取。

bot 啟動時預載所有 guild sticker 的 name + description，伺服器的貼圖有增刪改時
（`on_guild_stickers_update`）跟著更新，供聊天 context 組裝與訊息持久化使用。
別的伺服器的貼圖查 `sticker_dictionary`（AI 看圖補的）。
"""
from __future__ import annotations

import logging
from typing import Optional

import discord

from llm.preprocess import sticker_dictionary

logger = logging.getLogger(__name__)

# 模組級快取：sticker_id → "名稱｜描述"
_sticker_cache: dict[int, str] = {}


def _remember(sticker) -> None:
    desc = sticker.description or sticker.name
    _sticker_cache[sticker.id] = f"{sticker.name}｜{desc}"


async def load_guild_stickers(bot: discord.Client) -> int:
    """預載所有 guild 的 sticker，回傳載入數量。"""
    loaded = 0
    for guild in bot.guilds:
        try:
            stickers = await guild.fetch_stickers()
            for sticker in stickers:
                _remember(sticker)
                loaded += 1
        except Exception as exc:
            logger.warning("載入 guild %s 的貼圖失敗: %s", guild.id, exc)
    logger.info("已載入 %d 個貼圖描述", loaded)
    return loaded


def get_sticker_text(sticker: discord.StickerItem) -> Optional[str]:
    """查詢貼圖描述，回傳格式化文字或 None。"""
    cached = _sticker_cache.get(sticker.id) or sticker_dictionary.lookup(sticker.id)
    if cached:
        return f"[貼圖：{cached}]"
    # 別的伺服器還沒補描述的、Discord 標準貼圖：只用名稱
    return f"[貼圖：{sticker.name}]"


def is_known(sticker_id: int) -> bool:
    """這張貼圖是不是本伺服器的（啟動時預載過描述）。別的伺服器的貼圖不在快取裡。"""
    return sticker_id in _sticker_cache


def update_guild(before, after) -> None:
    """伺服器貼圖有增刪改（`on_guild_stickers_update`）時更新快取。

    **為什麼**：bot 會長時間不重啟；以前只在啟動時載入，新增的貼圖或改過的描述要等重啟才看得到，
    新增的本伺服器貼圖還會被當成別的伺服器的去下載圖。事件本身就帶著改完的完整清單，不必再查 API。
    """
    for sticker in before or ():
        _sticker_cache.pop(sticker.id, None)
    for sticker in after or ():
        _remember(sticker)
    logger.info("伺服器貼圖有變動，已更新描述快取（現有 %d 張）", len(after or ()))
