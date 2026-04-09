import asyncio
import logging
import discord
from discord.ext import commands

logger = logging.getLogger('discord_bot')
from .queue import MusicQueue
from .ytdl import YTDLSource
from .config import MusicConfig
from .models import Song
from .exceptions import QueueEmptyError


class MusicPlayer:
    def __init__(self, bot: commands.Bot, config: MusicConfig):
        self.bot = bot
        self.config = config
        self.queue = MusicQueue()
        self.voice_client: discord.VoiceClient | None = None
        self.announcer = None  # 由 cog 注入（避免循環引用）
        self._play_lock = asyncio.Lock()
        self._voice_lock = asyncio.Lock()  # 防止重入式 connect/disconnect
        self._task: asyncio.Task | None = None

    def _has_active_voice(self) -> bool:
        return self.voice_client is not None and self.voice_client.is_connected()

    def _reset_voice_client(self):
        self.voice_client = None

    async def ensure_voice(self) -> bool:
        """自動加入固定語音頻道（長期掛機）"""
        async with self._voice_lock:
            return await self._ensure_voice_inner()

    async def _ensure_voice_inner(self) -> bool:
        channel = self.bot.get_channel(self.config.voice_channel_id)
        if channel is None:
            logger.warning(f"[MusicPlayer] 找不到語音頻道 {self.config.voice_channel_id}，請確認頻道是否存在")
            return False
        if not isinstance(channel, discord.VoiceChannel):
            logger.warning(f"[MusicPlayer] 頻道 {self.config.voice_channel_id} 不是語音頻道")
            return False

        # 已連線到同一頻道，直接複用
        if self._has_active_voice():
            if self.voice_client.channel and self.voice_client.channel.id == channel.id:
                return True
            # 連到不同頻道，先斷開
            logger.info(f"[MusicPlayer] 從 {self.voice_client.channel} 移到 {channel.name}")
            await self.voice_client.disconnect(force=True)
            self._reset_voice_client()
            await asyncio.sleep(3)
        elif self.voice_client is not None:
            logger.warning("[MusicPlayer] 偵測到失效的 voice_client，將重新建立連線")
            self._reset_voice_client()

        # guild 有殘留的 voice client（非我們的），清理
        guild = channel.guild
        if guild.voice_client and guild.voice_client.is_connected() and guild.voice_client != self.voice_client:
            logger.info("[MusicPlayer] 清理 guild 殘留語音連線")
            try:
                await guild.voice_client.disconnect(force=True)
            except Exception:
                pass
            await asyncio.sleep(3)

        try:
            self.voice_client = await channel.connect(self_deaf=True, timeout=60)
            logger.info(f"[MusicPlayer] 已加入語音頻道: {channel.name}")
            return True
        except Exception as e:
            self._reset_voice_client()  # 清理半失敗狀態
            logger.error(f"[MusicPlayer] 加入語音頻道失敗: {e}", exc_info=True)
            return False

    async def start_background_loop(self):
        """背景播放主迴圈"""
        if self._task and not self._task.done():
            return
        self._task = asyncio.create_task(self._play_loop())

    async def _play_loop(self):
        while True:
            try:
                await self._play_next()
            except QueueEmptyError:
                await asyncio.sleep(5)
            except Exception as e:
                logger.error(f"[MusicPlayer] 播放迴圈錯誤: {e}", exc_info=True)
                await asyncio.sleep(5)

    async def _play_next(self):
        async with self._play_lock:
            if not await self.ensure_voice():
                return

            is_interrupt_song = self.queue.is_interrupt_active()
            song = self.queue.get_next()
            self.queue.current = song

            # 提取音源（每次播放時重新取得新鮮串流 URL，不展開歌單）
            try:
                info = await YTDLSource.extract_single(song.webpage_url)
            except Exception as e:
                error_msg = str(e)
                # 判斷錯誤類型，產生友善的原因訊息
                if 'copyright' in error_msg.lower() or 'blocked' in error_msg.lower():
                    reason = "版權限制，已被權利方封鎖"
                elif 'private' in error_msg.lower():
                    reason = "私人影片，無法存取"
                elif 'unavailable' in error_msg.lower() or 'not available' in error_msg.lower():
                    reason = "影片已不存在或被移除"
                else:
                    reason = "無法取得串流資訊"
                logger.warning(f"[MusicPlayer] 跳過無法播放的歌曲: {song.title} ({reason})")
                # 從主歌單中移除（不放回佇列）
                self.queue.remove_song(song)
                self.queue.current = None
                if self.announcer:
                    await self.announcer.send_skipped_notice(song, reason)
                return

            audio_source = discord.FFmpegPCMAudio(
                info['url'],
                before_options='-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
                options='-vn'
            )

            # 播放並等待結束
            play_done = asyncio.Event()

            def after_callback(error):
                if error:
                    logger.error(f"[MusicPlayer] 播放錯誤: {error}")
                self.bot.loop.call_soon_threadsafe(play_done.set)

            if not self._has_active_voice():
                logger.warning("[MusicPlayer] 播放前偵測到 voice 已失效，重新排回歌曲並重連")
                self._reset_voice_client()
                self.queue.requeue_song(song, is_interrupt_song)
                self.queue.current = None
                return

            try:
                self.voice_client.play(audio_source, after=after_callback)
            except discord.ClientException as e:
                logger.warning(f"[MusicPlayer] play() 時 voice 已失效，歌曲將回佇列重試: {e}")
                self._reset_voice_client()
                self.queue.requeue_song(song, is_interrupt_song)
                self.queue.current = None
                return

            # 通知「現在播放」面板
            if self.announcer:
                await self.announcer.send_now_playing(song)

            await play_done.wait()
            self.queue.current = None
            await asyncio.sleep(0.5)

    async def add_to_playlist(self, url: str):
        """將 URL（歌單或單曲）加入主佇列"""
        songs_info = await YTDLSource.extract_info(url)
        song_list = [Song.from_info(s) for s in songs_info]
        self.queue.add_to_main(song_list)

    async def interrupt_play(self, query: str):
        """插播：URL 或關鍵字皆可"""
        song = await YTDLSource.create_song(query)
        self.queue.add_interrupt(song)
        # 如果正在播放，立即停止並切下一首
        if self.voice_client and self.voice_client.is_playing():
            self.voice_client.stop()

    def stop(self):
        """停止播放，只清除插播佇列，保留預設歌單"""
        self.queue.clear_interrupts()
        if self.voice_client and self.voice_client.is_playing():
            self.voice_client.stop()
