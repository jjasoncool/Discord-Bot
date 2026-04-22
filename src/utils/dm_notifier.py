"""
DM 通知共用模組：封裝向指定使用者發送私訊的共通邏輯。

- 底層：resolve_user + send_dm
- 高階情境封裝：notify_keyword_hit, notify_song_liked
"""
import logging
import discord

logger = logging.getLogger('discord_bot')


async def resolve_user(bot, user_id: int, *, guild: discord.Guild = None):
    """解析 user_id 為 User/Member。順序：guild.fetch_member → bot.fetch_user → bot.get_user → guild.get_member"""
    user = None
    if guild is not None:
        try:
            user = await guild.fetch_member(user_id)
        except discord.NotFound:
            logger.warning(f"fetch_member 找不到使用者，ID: {user_id}")
        except discord.Forbidden:
            logger.warning(f"fetch_member 權限不足，ID: {user_id}")
        except Exception as e:
            logger.warning(f"fetch_member 錯誤，ID: {user_id}，{type(e).__name__}: {e}")

    if user is None:
        try:
            user = await bot.fetch_user(user_id)
        except (discord.NotFound, discord.Forbidden):
            pass
        except Exception as e:
            logger.warning(f"fetch_user 錯誤，ID: {user_id}，{type(e).__name__}: {e}")

    if user is None:
        user = bot.get_user(user_id)
    if user is None and guild is not None:
        user = guild.get_member(user_id)

    if user is None:
        logger.warning(f"所有方法均無法取得使用者，ID: {user_id}")
    return user


async def send_dm(user, *, embed=None, content=None) -> bool:
    """對已解析的 User/Member 發送 DM。True = 送達；False = 失敗（已 log），永不 raise。"""
    if user is None:
        return False
    try:
        await user.send(content=content, embed=embed)
        logger.info(f"已發送 DM 給 {user.name}（ID: {user.id}）")
        return True
    except discord.Forbidden:
        logger.warning(f"無法發送 DM 給 {user.name}（ID: {user.id}），可能已關閉私人訊息")
        return False
    except Exception as e:
        logger.error(f"發送 DM 錯誤：{type(e).__name__}: {e}")
        return False


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
    return await send_dm(user, embed=embed)


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

    return await send_dm(user, embed=embed)
