import os
import discord
from .models import Song
from .ytdl import YTDLSource


class MusicControlView(discord.ui.View):
    """音樂控制面板按鈕（persistent view，重啟後仍可互動）"""

    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="點歌", style=discord.ButtonStyle.primary, custom_id="music_request", emoji="🎵")
    async def request_song(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(SongRequestModal(self.cog))

    @discord.ui.button(label="跳過", style=discord.ButtonStyle.secondary, custom_id="music_skip", emoji="⏭")
    async def skip_song(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        player = self.cog.player
        if player.voice_client and player.voice_client.is_playing():
            player.voice_client.stop()
            await interaction.followup.send("⏭️ 已跳過", ephemeral=True)
        else:
            await interaction.followup.send("目前沒有在播放", ephemeral=True)

    @discord.ui.button(label="停止", style=discord.ButtonStyle.danger, custom_id="music_stop", emoji="⏹")
    async def stop_music(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        self.cog.player.stop()
        await interaction.followup.send("⏹️ 音樂已停止", ephemeral=True)

    @discord.ui.button(label="重播", style=discord.ButtonStyle.secondary, custom_id="music_replay", emoji="🔄")
    async def replay_song(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        player = self.cog.player
        if not player.queue.current:
            await interaction.followup.send("目前沒有在播放", ephemeral=True)
            return

        song = player.queue.current
        # 刪除該首歌的快取
        video_id = YTDLSource._extract_video_id(song.webpage_url)
        if video_id:
            cache_path = YTDLSource.get_cache_path(video_id)
            if cache_path:
                try:
                    os.remove(cache_path)
                except OSError:
                    pass

        # 設定重播 flag，停止當前播放 → 播放迴圈會重播同一首
        player._replay = True
        if player.voice_client and player.voice_client.is_playing():
            player.voice_client.stop()
        await interaction.followup.send(f"🔄 重新抓取並播放：**{song.title}**", ephemeral=True)

    @discord.ui.button(label="歌單", style=discord.ButtonStyle.secondary, custom_id="music_queue", emoji="📋")
    async def show_queue(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        queue = self.cog.player.queue
        if not queue.current and not queue.main_queue and not queue.interrupt_queue:
            await interaction.followup.send("📋 歌單是空的", ephemeral=True)
            return

        lines = []
        if queue.current:
            lines.append(f"▶ **{queue.current.title}**")

        # 插播佇列
        for i, song in enumerate(queue.interrupt_queue):
            lines.append(f"⚡ {i+1}. {song.title}")

        # 主歌單（只顯示前 10 首）
        main_list = list(queue.main_queue)[:10]
        for i, song in enumerate(main_list):
            lines.append(f"{i+1}. {song.title}")
        remaining = len(queue.main_queue) - len(main_list)
        if remaining > 0:
            lines.append(f"...還有 {remaining} 首")

        await interaction.followup.send("\n".join(lines), ephemeral=True)


class SongRequestModal(discord.ui.Modal):
    """點歌輸入框：支援 URL 或關鍵字"""

    def __init__(self, cog):
        super().__init__(title="點歌", timeout=120)
        self.cog = cog
        self.query = discord.ui.TextInput(
            label="歌名或 YouTube 連結",
            placeholder="例如：稻香、https://youtube.com/watch?v=...",
            max_length=200,
            required=True,
        )
        self.add_item(self.query)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        query = self.query.value.strip()
        try:
            await self.cog.player.interrupt_play(query)
            await interaction.followup.send(f"✅ 已加入插播：{query}", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ 點歌失敗：{e}", ephemeral=True)


class Announcer:
    """負責在語音頻道內建聊天發送控制面板，換歌時自動 bump 到底部"""

    def __init__(self, bot: discord.Client, voice_channel_id: int, cog):
        self.bot = bot
        self.voice_channel_id = voice_channel_id
        self.cog = cog
        self._panel_message: discord.Message | None = None

    async def send_now_playing(self, song: Song):
        """換歌時：刪除舊面板 → 發新面板（auto bump）"""
        channel = self.bot.get_channel(self.voice_channel_id)
        if channel is None:
            return

        # 刪除舊面板
        await self._delete_panel()

        # 建立新 embed
        embed = discord.Embed(
            title="🎵 現在播放",
            description=f"**{song.title}**",
            color=0x1DB954
        )
        if song.thumbnail:
            embed.set_thumbnail(url=song.thumbnail)
        if song.duration > 0:
            embed.add_field(
                name="長度",
                value=f"{song.duration // 60}:{song.duration % 60:02d}",
                inline=True
            )
        embed.add_field(
            name="來源",
            value=f"[YouTube]({song.webpage_url})",
            inline=True
        )

        # 發送新面板（含控制按鈕）
        view = MusicControlView(self.cog)
        self._panel_message = await channel.send(embed=embed, view=view)

    async def send_idle_panel(self):
        """閒置時顯示待機面板"""
        channel = self.bot.get_channel(self.voice_channel_id)
        if channel is None:
            return

        await self._delete_panel()

        embed = discord.Embed(
            title="🎵 音樂機器人",
            description="目前沒有播放中的歌曲\n點擊下方按鈕來點歌！",
            color=0x808080
        )
        view = MusicControlView(self.cog)
        self._panel_message = await channel.send(embed=embed, view=view)

    async def send_skipped_notice(self, song: Song, reason: str):
        """顯示跳過通知（版權、無法播放等），不影響控制面板"""
        channel = self.bot.get_channel(self.voice_channel_id)
        if channel is None:
            return

        embed = discord.Embed(
            title="⚠️ 無法播放，已跳過",
            description=f"**{song.title}**",
            color=0xFF4444
        )
        embed.add_field(name="原因", value=reason, inline=False)
        if song.webpage_url:
            embed.add_field(name="連結", value=f"[YouTube]({song.webpage_url})", inline=False)
        embed.set_footer(text="此歌曲已從歌單中移除")

        # 獨立訊息，5 秒後自動刪除
        try:
            msg = await channel.send(embed=embed, delete_after=15)
        except Exception:
            pass

    async def _delete_panel(self):
        """安全刪除舊面板訊息"""
        if self._panel_message:
            try:
                await self._panel_message.delete()
            except (discord.NotFound, discord.HTTPException):
                pass
            self._panel_message = None
