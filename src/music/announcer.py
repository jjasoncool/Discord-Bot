import os
import json
import logging
import discord
from .models import Song
from .ytdl import YTDLSource
from utils.dm_notifier import notify_song_liked

logger = logging.getLogger('discord_bot')

MUSIC_RUNTIME_PATH = "settings/music_runtime.json"


def _is_in_music_channel(cog, user) -> bool:
    """檢查使用者是否正待在音樂語音頻道內（沒進來的人不准點歌）"""
    vc_id = cog.config.voice_channel_id if getattr(cog, "config", None) else None
    voice = getattr(user, "voice", None)
    return bool(vc_id and voice and voice.channel and voice.channel.id == vc_id)


class PlaylistSelect(discord.ui.Select):
    """歌單多選下拉：勾選一個只播該歌單，勾多個則合併播放（全勾＝全部合併）。

    放在「編輯歌單」按鈕彈出的 ephemeral 面板中，不常駐在主控制面板上。
    """

    def __init__(self, cog):
        self.cog = cog
        playlists = cog.config.playlists
        active = set(cog.config.active_keys)
        player = getattr(cog, "player", None)
        options = []
        for i, p in enumerate(playlists):
            # 顯示名稱：自訂 > 自動抓的 YouTube 標題 > 後備
            name = player.display_name(p) if player else (p.name or f"歌單{i + 1}")
            options.append(discord.SelectOption(
                label=name[:100],
                value=p.key[:100],
                default=(p.key in active),
                emoji="🎵",
            ))
        super().__init__(
            placeholder="選擇要播放的歌單（可複選，全選＝合併）",
            min_values=1,                 # 至少留一個，避免清空成沒歌可播
            max_values=max(1, len(options)),  # 可全選＝全部合併播放
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        keys = list(self.values)
        count = await self.cog.player.set_active_playlists(keys)
        # 顯示用名稱（從選單 option 的 label 反查，避免顯示醜醜的 key）
        label_map = {opt.value: opt.label for opt in self.options}
        label = "、".join(label_map.get(k, k) for k in keys)
        if count is None:
            await interaction.followup.send(
                f"⚠️ 已切換為「{label}」，但線上抓取失敗或為空，維持原本播放。",
                ephemeral=True,
            )
        else:
            await interaction.followup.send(
                f"🎶 已切換歌單為「{label}」，共 {count} 首。", ephemeral=True
            )


class PlaylistEditView(discord.ui.View):
    """「編輯歌單」彈出的多選面板（ephemeral，短時效，不需 persistent）"""

    def __init__(self, cog):
        super().__init__(timeout=180)
        self.add_item(PlaylistSelect(cog))


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

    # ─── 第一排：點歌 + 歌單 + 收藏 ───
    @discord.ui.button(label="點歌", style=discord.ButtonStyle.primary, custom_id="music_request", emoji="🎵", row=0)
    async def request_song(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not _is_in_music_channel(self.cog, interaction.user):
            await interaction.response.send_message(
                "🎧 請先加入音樂語音頻道才能點歌喔！", ephemeral=True
            )
            return
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

    @discord.ui.button(label="收藏", style=discord.ButtonStyle.secondary, custom_id="music_favorite", emoji="⭐", row=0)
    async def favorite_song(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        player = self.cog.player
        if not player.queue.current:
            await interaction.followup.send("目前沒有在播放", ephemeral=True)
            return

        song = player.queue.current
        voice_channel = player.voice_client.channel if player.voice_client else None
        ok = await notify_song_liked(interaction.user, song, voice_channel=voice_channel)
        if ok:
            await interaction.followup.send(f"⭐ 已將 **{song.title}** 寄到你的私訊", ephemeral=True)
        else:
            await interaction.followup.send("⚠️ 無法寄送，請檢查你的私訊是否已開啟", ephemeral=True)

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

    # custom_id 沿用舊的 music_stop 以相容既有面板；
    # 行為：重讀 music_runtime.json 歌單設定（套用新增/刪改的歌單，免重啟），
    #       2 個以上歌單→彈出多選清單讓使用者挑；只有 0~1 個→直接重載最新線上歌單。
    @discord.ui.button(label="編輯歌單", style=discord.ButtonStyle.secondary, custom_id="music_stop", emoji="🎚️", row=1)
    async def edit_playlist(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        # 先重讀設定 + 補抓歌單名稱，讓彈出的清單顯示最新歌單與正確名稱
        await self.cog.refresh_playlist_config()
        playlists = self.cog.config.playlists if self.cog.config else []

        if len(playlists) >= 2:
            await interaction.followup.send(
                "🎚️ 選擇要播放的歌單（可複選，全選＝合併播放）：",
                view=PlaylistEditView(self.cog),
                ephemeral=True,
            )
            return

        # 只有 0~1 個歌單，沒得選 → 直接重載套用（等同舊的重置：同步線上加/刪歌）
        count = await self.cog.player.reload_playlist() if self.cog.player else None
        if count is None:
            await interaction.followup.send(
                "⚠️ 目前沒有可用歌單，請先在設定檔 playlist_url 填入歌單連結。",
                ephemeral=True,
            )
        else:
            await interaction.followup.send(
                f"♻️ 已重載最新線上歌單（共 {count} 首）。", ephemeral=True
            )

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
        if not _is_in_music_channel(self.cog, interaction.user):
            await interaction.followup.send(
                "🎧 你已不在音樂語音頻道，已取消這次點歌。", ephemeral=True
            )
            return
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
