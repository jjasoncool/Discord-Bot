import re
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
        self._replay = False  # 重播當前歌曲（不跳下一首）

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
            self._reset_voice_client()
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

            # 重播模式：沿用 current，不從佇列取下一首
            if self._replay and self.queue.current:
                song = self.queue.current
                is_interrupt_song = False
                self._replay = False
                logger.info(f"[MusicPlayer] 重播: {song.title}")
            else:
                is_interrupt_song = self.queue.is_interrupt_active()
                song = self.queue.get_next()
                self.queue.current = song

            # 檢查本地快取
            video_id = YTDLSource._extract_video_id(song.webpage_url)
            cache_path = YTDLSource.get_cache_path(video_id) if video_id else None
            need_download = False

            # FFmpegPCMAudio + 強制 48kHz PCM（DAVE 下最穩定）
            PCM_OPTS = '-vn -ar 48000 -ac 2 -f s16le'
            # thread_queue_size：ffmpeg 內部讀取緩衝，吸收 CPU/IO 微小延遲
            BUFFER_OPTS = '-thread_queue_size 4096'

            if cache_path:
                # 有快取：峰值正規化（等比例增益，保留動態）
                logger.info(f"[MusicPlayer] 使用快取播放: {song.title}")
                peak_db = await self._get_peak_db(cache_path)
                if peak_db is not None and peak_db != 0:
                    gain = -1.0 - peak_db
                    options = f'{PCM_OPTS} -af volume={gain:.1f}dB'
                    logger.info(f"[MusicPlayer] 峰值正規化: peak={peak_db:.1f}dB, gain={gain:.1f}dB")
                else:
                    options = PCM_OPTS
                audio_source = discord.FFmpegPCMAudio(
                    cache_path,
                    before_options=BUFFER_OPTS,
                    options=options,
                )
            else:
                # 無快取，串流播放（不做音量處理）
                try:
                    info = await YTDLSource.extract_single(song.webpage_url)
                except Exception as e:
                    error_msg = str(e)
                    if 'copyright' in error_msg.lower() or 'blocked' in error_msg.lower():
                        reason = "版權限制，已被權利方封鎖"
                    elif 'private' in error_msg.lower():
                        reason = "私人影片，無法存取"
                    elif 'unavailable' in error_msg.lower() or 'not available' in error_msg.lower():
                        reason = "影片已不存在或被移除"
                    else:
                        reason = "無法取得串流資訊"
                    logger.warning(f"[MusicPlayer] 跳過無法播放的歌曲: {song.title} ({reason})")
                    self.queue.remove_song(song)
                    self.queue.current = None
                    if self.announcer:
                        await self.announcer.send_skipped_notice(song, reason)
                    return

                audio_source = discord.FFmpegPCMAudio(
                    info['url'],
                    before_options=f'-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 {BUFFER_OPTS}',
                    options=PCM_OPTS,
                )
                need_download = True

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

            # 背景下載當前歌曲 + 預先快取接下來 3 首
            if need_download and song.webpage_url:
                asyncio.create_task(YTDLSource.download_to_cache(song.webpage_url))
            asyncio.create_task(self._prefetch_upcoming(3))

            await play_done.wait()
            if not self._replay:
                self.queue.current = None
            await asyncio.sleep(0.5)

    async def add_to_playlist(self, url: str):
        """將歌單 URL 逐批加入主佇列（邊解析邊播，不等全部完成）"""
        loop = asyncio.get_event_loop()
        try:
            entries = await loop.run_in_executor(
                None, lambda: YTDLSource._extract_playlist_sync(url)
            )
        except Exception as e:
            logger.error(f"[MusicPlayer] 歌單解析失敗: {e}")
            return

        batch = []
        for entry in entries:
            if not entry:
                continue
            song_url = entry.get('url') or entry.get('webpage_url', '')
            if not song_url:
                continue
            video_id = entry.get('id', '')
            thumbnail = entry.get('thumbnail') or (
                f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg" if video_id else None
            )
            song = Song(
                title=entry.get('title', 'Unknown'),
                url=song_url,
                webpage_url=f"https://www.youtube.com/watch?v={video_id}" if video_id else song_url,
                duration=int(entry.get('duration', 0) or 0),
                thumbnail=thumbnail,
            )
            batch.append(song)

            # 每 5 首加入一批
            if len(batch) >= 5:
                self.queue.add_to_main(batch)
                logger.info(f"[MusicPlayer] 歌單載入中... 已加入 {len(self.queue.main_queue)} 首")
                batch = []
                await asyncio.sleep(0)

        if batch:
            self.queue.add_to_main(batch)
        logger.info(f"[MusicPlayer] 歌單載入完成，共 {len(self.queue.main_queue)} 首")

    @staticmethod
    async def _get_peak_db(file_path: str) -> float | None:
        """用 ffmpeg 掃描檔案的最大峰值（dB）"""
        try:
            proc = await asyncio.create_subprocess_exec(
                'ffmpeg', '-i', file_path, '-af', 'volumedetect', '-f', 'null', '-',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
            match = re.search(r'max_volume:\s*([-\d.]+)\s*dB', stderr.decode())
            if match:
                return float(match.group(1))
        except Exception as e:
            logger.warning(f"[MusicPlayer] 峰值掃描失敗: {e}")
        return None

    async def _prefetch_upcoming(self, count: int = 3):
        """背景預先下載接下來的歌曲到快取"""
        upcoming = list(self.queue.interrupt_queue)[:count]
        if len(upcoming) < count:
            upcoming += list(self.queue.main_queue)[:count - len(upcoming)]

        for song in upcoming:
            if not song.webpage_url:
                continue
            video_id = YTDLSource._extract_video_id(song.webpage_url)
            if video_id and not YTDLSource.get_cache_path(video_id):
                try:
                    await YTDLSource.download_to_cache(song.webpage_url)
                except Exception:
                    pass

    async def request_song(self, query: str) -> Song:
        """點歌：加入插播佇列排隊，不打斷當前歌曲"""
        song = await YTDLSource.create_song(query)
        self.queue.add_interrupt(song)
        return song

    def stop(self):
        """停止播放，只清除插播佇列，保留預設歌單"""
        self.queue.clear_interrupts()
        if self.voice_client and self.voice_client.is_playing():
            self.voice_client.stop()
