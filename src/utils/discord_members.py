"""取 Discord 的人：伺服器成員（快取沒有再問 API），以及任何能收訊息的對象（不是成員就找使用者）。

架構定位：基礎層（utils）裡的 Discord 工具（登記在 `test_layering.DISCORD_HELPERS_IN_BASE`），只依賴 discord.py。
  上層：交易（顯示暱稱）、關鍵字清單、賣家清單、論壇貼文擁有者、私訊通知（`dm_notifier`）。
  下層：discord.py 的快取與 REST。

介面：
- `resolve_member(guild, user_id)`：先查成員快取、沒有再 `fetch_member`；不在伺服器（已離開）、沒權限、其他 HTTP 錯誤都回 None。
- `resolve_user(bot, user_id, guild=)`：先當成員找（上面那支），不是成員再查 bot 的使用者快取、最後 `fetch_user`；都沒有回 None。

規則：
- 全專案取成員只走這裡（守衛擋自己 `guild.fetch_member`）：快取偶爾拿不到人（接單曾因此失敗），快取沒有不等於不在伺服器，
  一定要再問一次 API。點名刻意只用 API（快取漏人會把還在的人誤判成離開而踢掉），是合理例外。

例外與決策：
- 快取優先而不是 API 優先：bot 開著 members intent，成員改暱稱、離開都會經 gateway 事件更新快取，資料不會舊；
  快取命中就省兩次 API，沒命中走的 API 和 API 優先一樣。
"""
from __future__ import annotations

import logging

import discord

logger = logging.getLogger(__name__)


async def resolve_member(guild, user_id) -> discord.Member | None:
    """伺服器成員：先查快取、沒有再向 API 查；不在、沒權限、出錯都回 None。"""
    if guild is None or not user_id:
        return None
    member = guild.get_member(int(user_id))
    if member is not None:
        return member
    try:
        return await guild.fetch_member(int(user_id))
    except discord.NotFound:
        logger.warning("成員 %s 不在伺服器（可能已離開）", user_id)
    except discord.Forbidden:
        logger.warning("沒有權限查成員 %s", user_id)
    except discord.HTTPException as exc:
        logger.warning("向 API 查成員 %s 失敗：%s", user_id, exc)
    return None


async def resolve_user(bot, user_id: int, *, guild: discord.Guild = None):
    """任何能收訊息的對象（Member 或 User）：先當伺服器成員找，不是成員才退到 bot 的使用者快取與 API。"""
    user = await resolve_member(guild, user_id)
    if user is None:
        user = bot.get_user(user_id)
    if user is None:
        try:
            user = await bot.fetch_user(user_id)
        except (discord.NotFound, discord.Forbidden):
            pass
        except discord.HTTPException as exc:
            logger.warning("fetch_user 錯誤，ID: %s：%s", user_id, exc)

    if user is None:
        logger.warning("所有方法均無法取得使用者，ID: %s", user_id)
    return user
