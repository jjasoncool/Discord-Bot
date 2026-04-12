import os
import json
import logging
import discord
from .models import Song
from .ytdl import YTDLSource

logger = logging.getLogger('discord_bot')

MUSIC_RUNTIME_PATH = "settings/music_runtime.json"


class MusicControlView(discord.ui.View):
    """音樂控制面板按鈕（persistent view，重啟後仍可互動）"""

    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog
        # 根據 shuffle 狀態設定按鈕顏色
        if cog.player and cog.player.queue.shuffle:
            self.toggle_shuffle.style = discord.ButtonStyle.success  # 綠色
        else:
            self.toggle_shuffle.style = discord.ButtonStyle.secondary  # 灰色

    # ─── 第一排：點歌 + 歌單 ───
    @discord.ui.button(label="點歌", style=discord.ButtonStyle.primary, custom_id="music_request", emoji="🎵", row=0)
    async def request_song(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(SongRequestModal(self.cog))

    @discord.ui.button(label="歌單", style=discord.ButtonStyle.secondary, custom_id="music_queue", emoji="📋", row=0)
    async def show_queue(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        queue = self.cog.player.queue

        lines = []
        if queue.current:
            lines.append(f"▶ **{queue.current.title}**")

        # 插播佇列
        for i, song in enumerate(queue.interrupt_queue):
            lines.append(f"⚡ {i+1}. {song.title}")

        # shuffle 開啟時只顯示下一首
        if queue.shuffle:
            next_song = queue.peek_next()
            if next_song:
                lines.append(f"🔀 下一首：{next_song.title}")
            else:
                lines.append("🔀 隨機播放中")
        else:
            # 主歌單（顯示前 10 首）
            main_list = list(queue.main_queue)[:10]
            for i, song in enumerate(main_list):
                lines.append(f"{i+1}. {song.title}")
            remaining = len(queue.main_queue) - len(main_list)
            if remaining > 0:
                lines.append(f"...還有 {remaining} 首")

        if not lines:
            await interaction.followup.send("📋 歌單是空的", ephemeral=True)
        else:
            await interaction.followup.send("\n".join(lines), ephemeral=True)

    # ─── 第二排：播放操作 ───
    @discord.ui.button(label="跳過", style=discord.ButtonStyle.secondary, custom_id="music_skip", emoji="⏭", row=1)
    async def skip_song(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        player = self.cog.player
        if player.voice_client and player.voice_client.is_playing():
            player.voice_client.stop()
            await interaction.followup.send("⏭️ 已跳過", ephemeral=True)
        else:
            await interaction.followup.send("目前沒有在播放", ephemeral=True)

    @discord.ui.button(label="停止", style=discord.ButtonStyle.danger, custom_id="music_stop", emoji="⏹", row=1)
    async def stop_music(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        self.cog.player.stop()
        await interaction.followup.send("⏹️ 音樂已停止", ephemeral=True)

    @discord.ui.button(label="重播", style=discord.ButtonStyle.secondary, custom_id="music_replay", emoji="🔄", row=1)
    async def replay_song(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        player = self.cog.player
        if not player.queue.current:
            await interaction.followup.send("目前沒有在播放", ephemeral=True)
            return

        song = player.queue.current
        video_id = YTDLSource._extract_video_id(song.webpage_url)
        if video_id:
            cache_path = YTDLSource.get_cache_path(video_id)
            if cache_path:
                try:
                    os.remove(cache_path)
                except OSError:
                    pass

        player._replay = True
        if player.voice_client and player.voice_client.is_playing():
            player.voice_client.stop()
        await interaction.followup.send(f"🔄 重新抓取並播放：**{song.title}**", ephemeral=True)

    @discord.ui.button(label="隨機", style=discord.ButtonStyle.secondary, custom_id="music_shuffle", emoji="🔀", row=1)
    async def toggle_shuffle(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        queue = self.cog.player.queue
        queue.shuffle = not queue.shuffle
        status = "開啟" if queue.shuffle else "關閉"
        await interaction.followup.send(f"🔀 隨機播放已 **{status}**", ephemeral=True)
        # 存檔（重啟後保持狀態）
        self.cog.player._save_shuffle_state(queue.shuffle)
        if self.cog.player.announcer and self.cog.player.announcer._panel_message:
            await self.cog.player.announcer.refresh_panel()


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
            song = await self.cog.player.request_song(query, interaction.user)
            queue_pos = len(self.cog.player.queue.interrupt_queue)
            await interaction.followup.send(
                f"<@{interaction.user.id}> 點了 **{song.title}**（排隊第 {queue_pos} 順位）"
            )
        except Exception as e:
            await interaction.followup.send(f"❌ 點歌失敗：{e}", ephemeral=True)


class Announcer:
    """負責在語音頻道內建聊天發送控制面板，換歌時自動 bump 到底部"""

    def __init__(self, bot: discord.Client, voice_channel_id: int, cog):
        self.bot = bot
        self.voice_channel_id = voice_channel_id
        self.cog = cog
        self._panel_message: discord.Message | None = None

    async def cleanup_old_panel(self):
        """啟動時清理上次殘留的面板訊息"""
        channel = self.bot.get_channel(self.voice_channel_id)
        if not channel:
            return
        old_id = self._load_panel_id()
        if old_id:
            try:
                old_msg = await channel.fetch_message(old_id)
                await old_msg.delete()
                logger.info(f"[Announcer] 已清理舊面板訊息: {old_id}")
            except (discord.NotFound, discord.HTTPException):
                pass
            self._save_panel_id(None)

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
        if song.requested_by_id:
            embed.add_field(
                name="點歌者",
                value=f"<@{song.requested_by_id}>",
                inline=True
            )

        # 發送新面板（含控制按鈕）
        view = MusicControlView(self.cog)
        self._panel_message = await channel.send(embed=embed, view=view)
        self._save_panel_id(self._panel_message.id)

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
        self._save_panel_id(self._panel_message.id)

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

    async def refresh_panel(self):
        """更新面板按鈕狀態（重新發送）"""
        if self._panel_message:
            try:
                view = MusicControlView(self.cog)
                await self._panel_message.edit(view=view)
            except (discord.NotFound, discord.HTTPException):
                pass

    async def _delete_panel(self):
        """安全刪除舊面板訊息"""
        if self._panel_message:
            try:
                await self._panel_message.delete()
            except (discord.NotFound, discord.HTTPException):
                pass
            self._panel_message = None
            self._save_panel_id(None)

    @staticmethod
    def _save_panel_id(message_id: int | None):
        """將面板訊息 ID 存入 music_runtime.json"""
        try:
            if os.path.exists(MUSIC_RUNTIME_PATH):
                with open(MUSIC_RUNTIME_PATH, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            else:
                data = {"music": {}}
            if message_id:
                data["music"]["panel_message_id"] = message_id
            else:
                data["music"].pop("panel_message_id", None)
            with open(MUSIC_RUNTIME_PATH, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"[Announcer] 儲存面板 ID 失敗: {e}")

    @staticmethod
    def _load_panel_id() -> int | None:
        """從 music_runtime.json 讀取面板訊息 ID"""
        try:
            if os.path.exists(MUSIC_RUNTIME_PATH):
                with open(MUSIC_RUNTIME_PATH, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return data.get("music", {}).get("panel_message_id")
        except Exception:
            pass
        return None
