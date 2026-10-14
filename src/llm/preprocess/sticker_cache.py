"""貼圖描述快取：貼圖 id → 「名稱｜描述」，給聊天行、訊息備份、看圖補字典查「這張貼圖是什麼、是不是本伺服器的」。

架構定位：技術層（`llm/preprocess`），只是一份記憶體快取，不認 Discord——向 Discord 要貼圖清單、
接 `on_guild_stickers_update` 事件都是介面層（`discord_bot`）的事，它拿到清單後交進來。
  - 上層（誰呼叫）：`discord_bot`（啟動時 `remember`、貼圖變動時 `update_guild`）、
    `llm.preprocess.chat_line`／`llm.storage.store_chat`／`llm.storage.raw_message_store`（`get_sticker_text`）、
    `llm.preprocess.emoji_autofill`／`external_emoji`（`is_known`）。
  - 下層（呼叫誰）：`llm.preprocess.sticker_dictionary`（別的伺服器的貼圖，AI 看圖補的描述）。

介面：
  - `remember(stickers)`：把一批貼圖（任何有 `id`、`name`、`description` 的物件）記進快取，回傳幾張。
  - `update_guild(before, after)`：伺服器貼圖增刪改時，拿掉舊的、記新的。
  - `get_sticker_text(sticker)`：給 prompt 用的「[貼圖：名稱｜描述]」；查不到描述只剩名稱。
  - `is_known(sticker_id, guild=None)`：是不是本伺服器的貼圖；快取還沒載完時可給訊息所屬伺服器的清單再查一次。

規則：
  - 本伺服器貼圖的描述存在 Discord 上（伺服器設定），這裡只是鏡像；別的伺服器的查 `sticker_dictionary`。
  - 參數都是鴨子型別：測試用 `SimpleNamespace` 就能餵，不必建 discord 物件。

例外與決策：
  - 2026-10-03：重啟後連上 Discord 到快取載完的 3 秒內，本伺服器的貼圖被當成別的伺服器的寫進字典
    → `is_known` 多收 `guild`，快取沒有就看它自己的清單（連上就有，不用等預載）。
  - 2026-10-13（技術層與服務層退出 discord）：原本的 `load_guild_stickers(bot)` 自己向每個伺服器 `fetch_stickers`，
    拆成介面層抓、這裡 `remember`；技術層不 import discord（守衛 `test_layering`）。
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Iterable, Optional

from llm.preprocess import sticker_dictionary

if TYPE_CHECKING:  # 只給型別註解；執行時不依賴 discord
    import discord

logger = logging.getLogger(__name__)

# 模組級快取：sticker_id → "名稱｜描述"
_sticker_cache: dict[int, str] = {}


def _remember(sticker) -> None:
    desc = sticker.description or sticker.name
    _sticker_cache[sticker.id] = f"{sticker.name}｜{desc}"


def remember(stickers: Iterable) -> int:
    """記住一批貼圖（有 `id`、`name`、`description` 的物件），回傳記了幾張。"""
    count = 0
    for sticker in stickers:
        _remember(sticker)
        count += 1
    return count


def get_sticker_text(sticker: "discord.StickerItem") -> Optional[str]:
    """查詢貼圖描述，回傳格式化文字或 None。"""
    cached = _sticker_cache.get(sticker.id) or sticker_dictionary.lookup(sticker.id)
    if cached:
        return f"[貼圖：{cached}]"
    # 別的伺服器還沒補描述的、Discord 標準貼圖：只用名稱
    return f"[貼圖：{sticker.name}]"


def is_known(sticker_id: int, guild=None) -> bool:
    """這張貼圖是不是本伺服器的。別的伺服器的貼圖不在快取裡。

    給了 `guild`（訊息所屬伺服器）時，快取沒有就再看它自己的貼圖清單——那是連上 Discord 時就有的，
    預載快取要等 `on_ready` 才載完。2026-10-03 實例：重啟後連上（03:31:49）到快取載完（03:31:52）之間
    有人貼了本伺服器的 IDEA，被當成別的伺服器的寫進貼圖字典。
    """
    if sticker_id in _sticker_cache:
        return True
    return any(getattr(s, "id", None) == sticker_id for s in (getattr(guild, "stickers", None) or ()))


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
