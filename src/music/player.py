import os
import re
import json
import asyncio
import logging
import discord
from discord.ext import commands

logger = logging.getLogger('discord_bot')
from .queue import MusicQueue
from .ytdl import YTDLSource
from .config import MusicConfig, MUSIC_RUNTIME_PATH
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
        self._bg_tasks: set[asyncio.Task] = set()  # 追蹤背景下載 tasks
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

        guild = channel.guild

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

        # guild 層級已有連線（gateway reconnect / voice server migration 後常見）
        # 直接認領，不要嘗試重新 connect
        existing_vc = guild.voice_client
        if existing_vc is not None:
            if existing_vc.is_connected() and getattr(existing_vc.channel, 'id', None) == channel.id:
                logger.info("[MusicPlayer] 認領 guild 殘留語音連線（同頻道）")
                self.voice_client = existing_vc
                return True
            # 不同頻道或已斷線，強制清理
            logger.info("[MusicPlayer] 清理 guild 殘留語音連線")
            try:
                await existing_vc.disconnect(force=True)
            except Exception:
                pass
            # 確保 discord.py 內部狀態也清乾淨
            try:
                guild._voice_client = None
            except Exception:
                pass
            await asyncio.sleep(3)

        try:
            self.voice_client = await channel.connect(self_deaf=True, timeout=60)
            logger.info(f"[MusicPlayer] 已加入語音頻道: {channel.name}")
            return True
        except discord.ClientException:
            # connect 仍失敗（內部狀態殘留），最後嘗試認領
            if guild.voice_client and guild.voice_client.is_connected():
                logger.warning("[MusicPlayer] connect 失敗但 guild 有活躍連線，強制認領")
                self.voice_client = guild.voice_client
                return True
            self._reset_voice_client()
            logger.error("[MusicPlayer] 加入語音頻道失敗: Already connected 且無法認領")
            return False
        except Exception as e:
            self._reset_voice_client()
            logger.error(f"[MusicPlayer] 加入語音頻道失敗: {e}", exc_info=True)
            return False

    def _track_task(self, coro) -> asyncio.Task:
        """建立背景 task 並自動追蹤，完成後從 set 移除"""
        task = asyncio.create_task(coro)
        self._bg_tasks.add(task)
        task.add_done_callback(self._bg_tasks.discard)
        return task

    async def cleanup(self):
        """停止播放、取消所有背景 tasks、斷開語音"""
        # 取消播放主迴圈
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        # 取消所有背景下載/prefetch tasks
        for task in list(self._bg_tasks):
            task.cancel()
        self._bg_tasks.clear()

        # 停止目前播放並斷開語音
        if self.voice_client:
            if self.voice_client.is_playing():
                self.voice_client.stop()
            if self.voice_client.is_connected():
                await self.voice_client.disconnect(force=True)
            self._reset_voice_client()

        self.queue.current = None

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

            # 記錄當前播放位置（主歌單的歌才記錄，插播不記錄）
            if not is_interrupt_song:
                video_id_for_save = YTDLSource._extract_video_id(song.webpage_url)
                if video_id_for_save:
                    self._save_last_position(video_id_for_save)

            # 檢查本地快取
            video_id = YTDLSource._extract_video_id(song.webpage_url)
            cache_path = YTDLSource.get_cache_path(video_id) if video_id else None
            need_download = False

            # 音訊模式：pcm 或 opus（可在 music_runtime.json 的 audio_mode 切換）
            use_opus = self.config.audio_mode == 'opus'
            BUFFER_OPTS = '-thread_queue_size 4096 -fflags +genpts'
            # Discord voice 固定 48kHz stereo；opus frame_duration 20ms 最穩定
            OPUS_ENCODE = '-c:a libopus -b:a 192k -ar 48000 -ac 2 -frame_duration 20 -application audio'

            if cache_path:
                logger.info(f"[MusicPlayer] 使用快取播放 ({self.config.audio_mode}): {song.title}")
                peak_db = await self._get_peak_db(cache_path)
                volume_filter = ''
                if peak_db is not None and peak_db != 0:
                    gain = -1.0 - peak_db
                    volume_filter = f'-af volume={gain:.1f}dB'
                    logger.info(f"[MusicPlayer] 峰值正規化: peak={peak_db:.1f}dB, gain={gain:.1f}dB")

                if use_opus:
                    # 統一走解碼→filter→重新編碼，避免 codec copy 與 volume filter 衝突
                    opus_opts = f'-vn {volume_filter} {OPUS_ENCODE} -flush_packets 0 -f opus'.strip()
                    audio_source = discord.FFmpegOpusAudio(
                        cache_path,
                        before_options=BUFFER_OPTS,
                        options=opus_opts,
                        codec='copy',  # 告訴 discord.py 資料已是 opus，直接送出不再轉碼
                    )
                else:
                    pcm_opts = f'-vn -ar 48000 -ac 2 -f s16le {volume_filter}'.strip()
                    audio_source = discord.FFmpegPCMAudio(
                        cache_path,
                        before_options=BUFFER_OPTS,
                        options=pcm_opts,
                    )
            else:
                # 無快取，串流播放
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

                stream_url = info['url']
                del info  # 釋放 yt-dlp 的大型 metadata dict

                stream_before = f'-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -re {BUFFER_OPTS}'
                if use_opus:
                    audio_source = discord.FFmpegOpusAudio(
                        stream_url,
                        before_options=stream_before,
                        options=f'-vn {OPUS_ENCODE} -f opus',
                        codec='copy',
                    )
                else:
                    audio_source = discord.FFmpegPCMAudio(
                        stream_url,
                        before_options=stream_before,
                        options='-vn -ar 48000 -ac 2 -f s16le',
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
                self.voice_client.play(audio_source, after=after_callback, bitrate=192)
            except discord.ClientException as e:
                logger.warning(f"[MusicPlayer] play() 時 voice 已失效，歌曲將回佇列重試: {e}")
                self._reset_voice_client()
                self.queue.requeue_song(song, is_interrupt_song)
                self.queue.current = None
                return

            # 通知「現在播放」面板
            if self.announcer:
                await self.announcer.send_now_playing(song)

            # 背景下載當前歌曲 + 預先快取下一首
            if need_download and song.webpage_url:
                self._track_task(YTDLSource.download_to_cache(song.webpage_url))
            self._track_task(self._prefetch_next())

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

    async def _prefetch_next(self):
        """背景預先下載下一首要播的歌"""
        song = self.queue.peek_next()
        if not song or not song.webpage_url:
            return
        video_id = YTDLSource._extract_video_id(song.webpage_url)
        if video_id and not YTDLSource.get_cache_path(video_id):
            try:
                await YTDLSource.download_to_cache(song.webpage_url)
            except Exception:
                pass

    @staticmethod
    def _save_to_runtime(key: str, value):
        """寫入 music_runtime.json 的指定欄位"""
        try:
            if os.path.exists(MUSIC_RUNTIME_PATH):
                with open(MUSIC_RUNTIME_PATH, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            else:
                data = {"music": {}}
            data["music"][key] = value
            with open(MUSIC_RUNTIME_PATH, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"[MusicPlayer] 儲存 {key} 失敗: {e}")

    @staticmethod
    def _save_last_position(video_id: str):
        MusicPlayer._save_to_runtime("last_video_id", video_id)

    @staticmethod
    def _save_shuffle_state(shuffle: bool):
        MusicPlayer._save_to_runtime("shuffle", shuffle)

    @staticmethod
    def get_last_position() -> str | None:
        """讀取上次播放的 video ID"""
        try:
            if os.path.exists(MUSIC_RUNTIME_PATH):
                with open(MUSIC_RUNTIME_PATH, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return data.get("music", {}).get("last_video_id")
        except Exception:
            pass
        return None

    def skip_to_video_id(self, target_video_id: str) -> bool:
        """跳轉主歌單到指定 video ID 的位置"""
        for i, song in enumerate(self.queue.main_queue):
            vid = YTDLSource._extract_video_id(song.webpage_url)
            if vid == target_video_id:
                # 旋轉 deque，讓目標歌曲排到最前面
                self.queue.main_queue.rotate(-i)
                # shuffle 模式下 get_next() 讀 _next_shuffle 而非 deque 順序，
                # 必須覆寫才不會被先前 setter 隨機挑的那首蓋過
                if self.queue.shuffle:
                    self.queue._next_shuffle = song
                logger.info(f"[MusicPlayer] 跳轉到上次播放位置: {song.title} (index {i})")
                return True
        logger.warning(f"[MusicPlayer] 找不到上次播放的歌曲: {target_video_id}")
        return False

    async def request_song(self, query: str, user: discord.User | discord.Member = None) -> Song:
        """點歌：加入插播佇列排隊，不打斷當前歌曲"""
        song = await YTDLSource.create_song(query)
        if user:
            song.requested_by = user.display_name
            song.requested_by_id = user.id
        self.queue.add_interrupt(song)
        return song

    def stop(self):
        """停止播放，只清除插播佇列，保留預設歌單"""
        self.queue.clear_interrupts()
        if self.voice_client and self.voice_client.is_playing():
            self.voice_client.stop()
