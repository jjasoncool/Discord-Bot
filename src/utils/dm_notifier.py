"""
DM 通知共用模組：封裝向指定使用者發送私訊的共通邏輯。

- 底層：send_dm（找對象用 `utils.discord_members.resolve_user`）
- 高階情境封裝：notify_keyword_hit, notify_song_liked, notify_owner_lemonade_heal（模型後端自癒事件私訊群主）
"""
import logging
import discord

from utils.discord_members import resolve_user

logger = logging.getLogger(__name__)


async def send_dm(user, *, embed=None, content=None, file=None) -> bool:
    """對已解析的 User/Member 發送 DM。True = 送達；False = 失敗（已 log），永不 raise。

    `file`：附件（例如太長塞不進訊息的 JSON 結果）。discord.py 的 `send` 對
    `file` 用 MISSING 哨兵而非 None，傳 None 會炸 → 這裡條件帶入。
    """
    if user is None:
        return False
    try:
        kwargs = {"content": content, "embed": embed}
        if file is not None:
            kwargs["file"] = file
        await user.send(**kwargs)
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


def lemonade_heal_notice(event: dict) -> str:
    """自癒事件（`llm.client.lemonade_admin.set_heal_listener` 送來的）→ 給群主看的一行。管理員訊息可以帶技術原因。"""
    model = str(event.get("model") or "?")
    reason = str(event.get("reason") or "").strip() or "沒有錯誤內容"
    heals = event.get("heals")
    outcome = event.get("outcome")
    if outcome == "healed":
        return f"🔧 Lemonade 自癒：{model} 回錯（{reason}），已重載一次恢復；這一小時第 {heals} 次。常發生代表那張卡或驅動有問題。"
    if outcome == "failed":
        return f"⚠️ Lemonade 自癒失敗：{model} 重載沒成功（{reason}），bot 會晚點再試；請看看 Lemonade。"
    if outcome == "gave_up":
        return f"🛑 Lemonade 自癒放棄：{model} 一小時內已重載 {heals} 次還是壞（{reason}），不再自動重載，請檢查那張顯示卡或驅動。"
    return f"Lemonade 自癒事件：{outcome} {model}（{reason}）"


async def notify_owner_lemonade_heal(bot, event: dict) -> bool:
    """模型後端自癒（重載、失敗、放棄）時私訊群主一行；`OWNER_ID` 沒設就不送。True＝送達。"""
    from utils.utils import bot_owner_id

    owner_id = bot_owner_id()
    if not owner_id:
        return False
    user = await resolve_user(bot, owner_id)
    return await send_dm(user, content=lemonade_heal_notice(event)[:1900])
