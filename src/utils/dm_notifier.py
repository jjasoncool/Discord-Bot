"""私訊：對一個人發私訊，以及幾種固定情境的私訊內容（關鍵字命中、收藏歌曲）。

架構定位：基礎層（utils）裡的 Discord 工具（登記在 `test_layering.DISCORD_HELPERS_IN_BASE`），只依賴 discord.py 與
  `utils.discord_members`（找人、群主 id）。
  上層：關鍵字監看、音樂面板、點名、交易、/askai 的結果附件、群主通知（`commands.owner_alert_commands`）。
  下層：discord.py 的 `User.send`。

介面：
- `send_dm(user, *, embed=, content=, file=, view=)`：對已解析的 User／Member 發私訊，回送出的訊息；失敗回 None（已記 log），永不 raise。
- `notify_keyword_hit(bot, user_id, message, found_keywords, *, guild=)`／`notify_song_liked(user, song, *, voice_channel=)`。

規則：
- 要群主介入的狀況不在這裡拼：走 `utils.owner_alerts.emit`，由介面層變成私訊＋「重新偵測」按鈕。
"""
import logging
from typing import Optional

import discord

from utils.discord_members import resolve_user

logger = logging.getLogger(__name__)


async def send_dm(user, *, embed=None, content=None, file=None, view=None) -> Optional[discord.Message]:
    """對已解析的 User/Member 發送 DM。回送出的訊息（呼叫端要回寫時用）；失敗回 None（已 log），永不 raise。

    `file`、`view`：discord.py 的 `send` 對它們用 MISSING 哨兵而非 None，傳 None 會炸 → 有給才帶。
    """
    if user is None:
        return None
    try:
        kwargs = {"content": content, "embed": embed}
        if file is not None:
            kwargs["file"] = file
        if view is not None:
            kwargs["view"] = view
        message = await user.send(**kwargs)
        logger.info(f"已發送 DM 給 {user.name}（ID: {user.id}）")
        return message
    except discord.Forbidden:
        logger.warning(f"無法發送 DM 給 {user.name}（ID: {user.id}），可能已關閉私人訊息")
        return None
    except Exception as e:
        logger.error(f"發送 DM 錯誤：{type(e).__name__}: {e}")
        return None


async def notify_keyword_hit(bot, user_id: int, message: discord.Message, found_keywords, *, guild: discord.Guild = None) -> bool:
    """keyword 監控命中通知。"""
    user = await resolve_user(bot, user_id, guild=guild or message.guild)
    if user is None:
        return False

    parent_channel_id = None
    if hasattr(message.channel, 'parent') and message.channel.parent:
        parent_channel_id = message.channel.parent.id
    elif hasattr(message.channel, 'parent_id') and message.channel.parent_id:
        parent_channel_id = message.channel.parent_id

    channel_name = message.channel.parent.name if parent_channel_id else message.channel.name
    thread_name = f"貼文: {message.channel.name}" if parent_channel_id else ""

    embed = discord.Embed(
        title="🔔 關鍵字偵測通知",
        description=f"在頻道 **{channel_name}** {thread_name} 中偵測到您監控的關鍵字！",
        color=discord.Color.gold(),
        timestamp=message.created_at,
    )
    embed.add_field(
        name="偵測到的關鍵字",
        value=", ".join(f"`{kw}`" for kw in found_keywords),
        inline=False,
    )
    embed.add_field(
        name="訊息內容",
        value=message.content[:1024],
        inline=False,
    )
    embed.add_field(
        name="訊息連結",
        value=f"[點擊前往查看]({message.jump_url})",
        inline=False,
    )
    embed.set_author(
        name=message.author.display_name,
        icon_url=message.author.display_avatar.url,
    )
    return await send_dm(user, embed=embed) is not None


async def notify_song_liked(user, song, *, voice_channel: discord.VoiceChannel = None) -> bool:
    """音樂收藏通知：使用者按下播放面板的收藏按鈕時呼叫。"""
    if user is None:
        return False

    embed = discord.Embed(
        title="⭐ 收藏了一首歌",
        description=f"**{song.title}**",
        color=0xFFD700,
        timestamp=discord.utils.utcnow(),
    )
    if song.thumbnail:
        embed.set_thumbnail(url=song.thumbnail)
    if song.duration > 0:
        embed.add_field(
            name="長度",
            value=f"{song.duration // 60}:{song.duration % 60:02d}",
            inline=True,
        )
    embed.add_field(
        name="來源",
        value=f"[YouTube]({song.webpage_url})",
        inline=True,
    )
    if voice_channel is not None:
        embed.add_field(name="語音頻道", value=voice_channel.name, inline=True)

    return await send_dm(user, embed=embed) is not None
