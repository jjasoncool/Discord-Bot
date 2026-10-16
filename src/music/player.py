"""音樂播放器：長期掛在固定語音頻道，依佇列下載、播放歌曲，並記住播放位置。

架構定位：介面層（`music/`，直接操作 Discord 語音連線）。
  - 上層（誰呼叫）：`music.cog.MusicCog`（建立播放器、啟動播放迴圈、cog_unload 時呼叫 `mark_closing`／`cleanup`）、
    `music.announcer` 的面板按鈕（跳過、重播、插播）。
  - 下層（呼叫誰）：discord.py 的語音連線、`music.ytdl`（下載與快取）、`music.queue`、`music.config`（狀態檔）。

介面（停機相關）：`mark_closing()`、`cleanup()`；其餘是播放控制（`start_background_loop`、`ensure_voice`、跳過、重播、插播）。

規則：
  - 停機時 `cleanup` 的每一步都有時限（CLOSE_LOOP_TIMEOUT、CLOSE_DISCONNECT_TIMEOUT），整個 bot 的停機收尾只有幾秒。
  - `mark_closing` 之後不再開新的播放迴圈。
  - 語音斷線後先等 discord.py 自己重連（RECONNECT_GRACE_SECONDS），等不到才在同一條連線上重連，連線從它的登記表消失
    才建新的；被斷線打斷的歌從斷掉的地方接著播（續播不重複記入已播、不重發面板）。

例外與決策：
  - 停機時離開語音不用 discord.py 的 disconnect 等到底：讀 Discord 事件的連線已經停了，「已離開」的回報永遠
    不會來（它會等 30 秒）；而且取消若落在關語音 websocket 那段，它的 finally 還會再等一次，包 wait_for 也擋不住。
    所以斷線放進自己的 task，時間到就直接從 discord.py 取消登記。
  - 斷線後不立刻換連線：discord.py 自己幾秒內就會接回；對它強制 disconnect 不會取消它進行中的重連，那份工作 30 秒後
    會送出「離開頻道」把新連線踢掉、再等 30 秒才放棄，一次網路抖動變成兩次掉線、丟兩首歌。
  - 斷線時 discord.py 可能把正在播的歌直接中止、也可能讓它接著播，取決於幾毫秒的時序；所以播完與被打斷用
    「結束那一刻連線還在不在」分辨，被打斷的記下已播秒數、重連後用 ffmpeg 跳回去續播。
"""
import os
import re
import asyncio
import logging
import time
import discord
from discord.ext import commands

logger = logging.getLogger(__name__)
from .queue import MusicQueue
from .ytdl import YTDLSource
from .config import MusicConfig, playlist_key, read_state, save_state
from .models import Song
from .exceptions import QueueEmptyError

# 停機時離開語音最多等幾秒（離開的要求在等回報之前就送出了）
CLOSE_DISCONNECT_TIMEOUT = 2.0
# 停機時等播放迴圈停下最多幾秒：迴圈若正在斷線／重連，discord.py 會吞掉取消、繼續往下走
CLOSE_LOOP_TIMEOUT = 1.0
# 語音斷線後先讓 discord.py 自己重連：它一次重連最多 30 秒，過了這段還沒接回才由播放器接手。
# 太早接手會砍掉它進行中的重連，又留下它的背景工作，30 秒後那份工作會把新連線踢出頻道
RECONNECT_GRACE_SECONDS = 35.0
# 等重連時多久看一次
RECONNECT_POLL_SECONDS = 0.5
# 同一首歌連續被斷線打斷幾次後放棄續播、換下一首
MAX_RESUMES_PER_SONG = 3
# 續播時倒退幾秒，接得自然一點
RESUME_REWIND_SECONDS = 1.0

# 看時間、睡覺都走這兩個名字，測試換成假時鐘
_clock = time.monotonic
_sleep = asyncio.sleep


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
        self._resume: tuple[Song, float, bool] | None = None  # 被斷線打斷的歌：(歌, 從第幾秒接著播, 是不是插播)
        self._resume_song_key: str | None = None  # 連續被打斷的是哪一首
        self._resume_count = 0
        self._reloading = False  # 重載歌單中，避免重複觸發
        self._closing = False  # 停機中：不再開新的播放迴圈
        self._playlist_titles: dict[str, str] = {}  # 歌單 key → YouTube 標題（自動命名快取）

    def _has_active_voice(self) -> bool:
        return self.voice_client is not None and self.voice_client.is_connected()

    def _reset_voice_client(self):
        self.voice_client = None

    async def ensure_voice(self) -> bool:
        """自動加入固定語音頻道（長期掛機）"""
        async with self._voice_lock:
            return await self._ensure_voice_inner()

    async def _force_cleanup_guild_voice(self, guild):
        """強制斷開並清理 guild 上的殘留 voice_client，含 disconnect 的硬 timeout。

        只在那條連線已經沒有 discord.py 自己的重連在跑時用（等過寬限期、或同一條連線重連失敗之後）：
        重連進行中就強制 disconnect 的話，它的重連工作不會被取消，30 秒後會把後來建的新連線踢出頻道。
        取消登記由 disconnect 裡的 cleanup 做，guild.voice_client 是從登記表讀的，不能直接改。
        """
        self._reset_voice_client()
        existing = guild.voice_client
        if existing is not None:
            try:
                # discord.py 的 disconnect 在 voice gateway 已死時也可能 hang，硬性限時
                await asyncio.wait_for(existing.disconnect(force=True), timeout=5)
            except (asyncio.TimeoutError, Exception):
                pass

    async def _try_connect(self, channel) -> bool:
        """單次嘗試連線。用外層 wait_for 強制中斷 discord.py 不可靠的 timeout。

        實測 discord.py 2.7.1 的 channel.connect(timeout=60) 在 voice gateway hang 時
        會等 ~3 分鐘才超時（issue #10376 相關），用外層 wait_for=35s 強制保底。
        """
        try:
            self.voice_client = await asyncio.wait_for(
                channel.connect(self_deaf=True, timeout=30),
                timeout=35,
            )
            logger.info(f"[MusicPlayer] 已加入語音頻道: {channel.name}")
            return True
        except asyncio.TimeoutError:
            logger.warning("[MusicPlayer] connect() 超過 35 秒未回應，強制中斷")
            self._reset_voice_client()
            return False
        except discord.ClientException:
            if channel.guild.voice_client and channel.guild.voice_client.is_connected():
                logger.warning("[MusicPlayer] connect 失敗但 guild 有活躍連線，強制認領")
                self.voice_client = channel.guild.voice_client
                return True
            self._reset_voice_client()
            logger.warning("[MusicPlayer] connect 失敗: Already connected 且無法認領")
            return False
        except Exception as e:
            self._reset_voice_client()
            logger.warning(f"[MusicPlayer] connect 失敗: {e}")
            return False

    async def _ensure_voice_inner(self) -> bool:
        channel = self.bot.get_channel(self.config.voice_channel_id)
        if channel is None:
            logger.warning(f"[MusicPlayer] 找不到語音頻道 {self.config.voice_channel_id}，請確認頻道是否存在")
            return False
        if not isinstance(channel, discord.VoiceChannel):
            logger.warning(f"[MusicPlayer] 頻道 {self.config.voice_channel_id} 不是語音頻道")
            return False

        guild = channel.guild

        # bot 固定在同一頻道，已連線就直接複用
        if self._has_active_voice():
            return True

        # discord.py 登記表上的連線（通常就是我們手上這條）。連著就認領；斷了多半是它正在自己重連，先等它、
        # 等不到再在同一條連線上重連。只有登記表上沒有連線了，才建新的
        existing = guild.voice_client
        if existing is not None:
            if existing.is_connected():
                if getattr(existing.channel, 'id', None) == channel.id:
                    logger.info("[MusicPlayer] 認領 guild 殘留語音連線（同頻道）")
                    self.voice_client = existing
                    return True
            elif await self._wait_for_reconnect(existing, guild):
                self.voice_client = existing
                return True
            elif guild.voice_client is existing and await self._reconnect_same_client(existing):
                self.voice_client = existing
                return True

        self._reset_voice_client()
        if guild.voice_client is not None:
            logger.info("[MusicPlayer] 清理 guild 殘留語音連線")
            await self._force_cleanup_guild_voice(guild)
            await _sleep(3)

        # 第一次嘗試
        if await self._try_connect(channel):
            return True

        # 失敗則強制清理 guild 狀態後再試一次（不等 _play_loop 5 秒）
        logger.info("[MusicPlayer] 第一次連線失敗，強制清理後立即重試")
        await self._force_cleanup_guild_voice(guild)
        await _sleep(2)
        if await self._try_connect(channel):
            return True

        logger.error("[MusicPlayer] 加入語音頻道失敗（兩次嘗試皆失敗）")
        return False

    async def _wait_for_reconnect(self, voice, guild) -> bool:
        """語音斷了但連線還在登記表上：discord.py 會自己重連，給它 RECONNECT_GRACE_SECONDS。

        接回來回 True。它放棄的話會把連線從登記表拿掉，這時提早回 False，不白等。
        """
        started = _clock()
        logger.info("[MusicPlayer] 語音連線斷了，等 discord.py 自己重連（最多 %d 秒）", RECONNECT_GRACE_SECONDS)
        while True:
            if voice.is_connected():
                logger.info("[MusicPlayer] 語音已重連（等了 %.1f 秒）", _clock() - started)
                return True
            if guild.voice_client is not voice:
                logger.warning("[MusicPlayer] discord.py 放棄重連（等了 %.1f 秒），改建新連線", _clock() - started)
                return False
            if _clock() - started >= RECONNECT_GRACE_SECONDS:
                logger.warning("[MusicPlayer] 等了 %d 秒還沒接回，由播放器接手重連", RECONNECT_GRACE_SECONDS)
                return False
            await _sleep(RECONNECT_POLL_SECONDS)

    async def _reconnect_same_client(self, voice) -> bool:
        """在同一條連線上重連。

        discord.py 的 connect 會先取消這條連線自己的重連工作再重新握手，不會留下殭屍；失敗時它會自己 disconnect
        並取消登記，呼叫端接著建新連線就好。已取消登記的連線收不到語音事件，對它重連沒有用，所以呼叫端要先確認它還在登記表上。
        """
        try:
            await asyncio.wait_for(voice.connect(reconnect=True, timeout=30, self_deaf=True),
                                   timeout=RECONNECT_GRACE_SECONDS)
        except asyncio.TimeoutError:
            logger.warning("[MusicPlayer] 同一條連線重連逾時")
            return False
        except Exception as e:
            logger.warning(f"[MusicPlayer] 同一條連線重連失敗: {e}")
            return False
        if voice.is_connected():
            logger.info("[MusicPlayer] 同一條連線重連成功")
            return True
        logger.warning("[MusicPlayer] 同一條連線重連回來了但沒接上")
        return False

    def _may_resume(self, song: Song) -> bool:
        """同一首連續被斷線打斷太多次就放棄續播，換下一首（避免某一首永遠播不完、一直重來）。"""
        key = song.webpage_url or song.title
        if self._resume_song_key != key:
            self._resume_song_key, self._resume_count = key, 0
        self._resume_count += 1
        if self._resume_count > MAX_RESUMES_PER_SONG:
            logger.warning(f"[MusicPlayer] 同一首連續被打斷超過 {MAX_RESUMES_PER_SONG} 次，放棄續播換下一首: {song.title}")
            return False
        return True

    def _track_task(self, coro) -> asyncio.Task:
        """建立背景 task 並自動追蹤，完成後從 set 移除"""
        task = asyncio.create_task(coro)
        self._bg_tasks.add(task)
        task.add_done_callback(self._bg_tasks.discard)
        return task

    def mark_closing(self) -> None:
        """停機開始：之後不再開新的播放迴圈（歌單載入被取消時的 finally 也會想開一個）。"""
        self._closing = True

    async def cleanup(self):
        """停止播放、取消所有背景 tasks、斷開語音；停機時由 cog_unload 呼叫，每一步都有時限。"""
        self.mark_closing()
        await self._stop_play_loop()

        # 取消所有背景下載/prefetch tasks
        for task in list(self._bg_tasks):
            task.cancel()
        self._bg_tasks.clear()

        # 停止目前播放並離開語音。不看 is_connected：語音正在重連時它是 False，但連線物件還登記在 discord.py，
        # 留著的話關 Discord 連線時會再斷一次、再等一次回報
        if self.voice_client and self.voice_client.is_playing():
            self.voice_client.stop()
        guild = self._voice_guild()
        if guild is not None:
            await self._leave_voice_on_close(guild)
        self._reset_voice_client()

        self.queue.current = None

    async def _leave_voice_on_close(self, guild) -> None:
        """停機時離開語音：最多等 CLOSE_DISCONNECT_TIMEOUT 秒，時間到就直接從 discord.py 取消登記（原因見模組說明）。"""
        voice = guild.voice_client
        if voice is None:
            return
        leaving = asyncio.ensure_future(voice.disconnect(force=True))
        done, _ = await asyncio.wait({leaving}, timeout=CLOSE_DISCONNECT_TIMEOUT)
        if done:
            if not leaving.cancelled() and leaving.exception() is not None:
                logger.warning("[MusicPlayer] 停機時離開語音失敗：%s", leaving.exception())
            return
        leaving.cancel()   # 讓它在背景收尾；停機的下一步會再取消一次
        leaving.add_done_callback(lambda t: t.cancelled() or t.exception())   # 之後才結束的結果沒人取，先接住
        try:
            voice.cleanup()
        except Exception as exc:
            logger.warning("[MusicPlayer] 停機時取消語音登記失敗：%s", exc)

    def _voice_guild(self):
        """音樂用的語音頻道所在的伺服器；還沒連過語音時從設定的頻道找。"""
        if self.voice_client is not None:
            return self.voice_client.guild
        channel = self.bot.get_channel(self.config.voice_channel_id) if self.config else None
        return getattr(channel, "guild", None)

    async def _stop_play_loop(self) -> None:
        """取消播放主迴圈，最多等 CLOSE_LOOP_TIMEOUT 秒；沒停下就再取消一次（取消可能被 discord.py 吞掉）。"""
        task, self._task = self._task, None
        if task is None or task.done():
            return
        loop = asyncio.get_running_loop()
        deadline = loop.time() + CLOSE_LOOP_TIMEOUT
        while not task.done():
            task.cancel()   # 放棄前也先送出這一次：迴圈下次醒來就會停
            remaining = deadline - loop.time()
            if remaining <= 0:
                logger.warning("[MusicPlayer] 播放迴圈 %g 秒內沒停下，不再等", CLOSE_LOOP_TIMEOUT)
                return
            await asyncio.wait({task}, timeout=min(remaining, CLOSE_LOOP_TIMEOUT / 4))

    async def start_background_loop(self):
        """背景播放主迴圈"""
        if self._closing:
            return
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

            resume, self._resume = self._resume, None
            resume_offset = 0.0
            if resume is not None:
                # 上一輪被斷線打斷：同一首從斷掉的地方接著播，不從佇列取、不算播完
                song, resume_offset, is_interrupt_song = resume
                self.queue.current = song
                logger.info(f"[MusicPlayer] 從第 {resume_offset:.0f} 秒接著播: {song.title}")
            elif self._replay and self.queue.current:
                # 重播模式：沿用 current，不從佇列取下一首
                song = self.queue.current
                is_interrupt_song = False
                self._replay = False
                logger.info(f"[MusicPlayer] 重播: {song.title}")
            else:
                is_interrupt_song = self.queue.is_interrupt_active()
                song = self.queue.get_next()
                self.queue.current = song

            # 記錄當前播放位置（主歌單的歌才記錄，插播不記錄；續播的上一輪已記過）
            if resume is None and not is_interrupt_song:
                video_id_for_save = YTDLSource._extract_video_id(song.webpage_url)
                if video_id_for_save:
                    self._save_last_position(video_id_for_save)

            # 檢查本地快取
            video_id = YTDLSource._extract_video_id(song.webpage_url)
            cache_path = YTDLSource.get_cache_path(video_id) if video_id else None
            need_download = False

            # 音訊模式：pcm 或 opus（在歌單檔 music_playlists.json 的 audio_mode 切換）
            use_opus = self.config.audio_mode == 'opus'
            BUFFER_OPTS = '-thread_queue_size 4096 -fflags +genpts'
            # 續播：ffmpeg 讀來源前先跳到斷掉的地方（-ss 放在 -i 之前，快取檔和串流都適用）
            seek_opts = f'-ss {resume_offset:.1f} ' if resume_offset > 0 else ''
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
                        before_options=seek_opts + BUFFER_OPTS,
                        options=opus_opts,
                        codec='copy',  # 告訴 discord.py 資料已是 opus，直接送出不再轉碼
                    )
                else:
                    pcm_opts = f'-vn -ar 48000 -ac 2 -f s16le {volume_filter}'.strip()
                    audio_source = discord.FFmpegPCMAudio(
                        cache_path,
                        before_options=seek_opts + BUFFER_OPTS,
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
                        before_options=seek_opts + stream_before,
                        options=f'-vn {OPUS_ENCODE} -f opus',
                        codec='copy',
                    )
                else:
                    audio_source = discord.FFmpegPCMAudio(
                        stream_url,
                        before_options=seek_opts + stream_before,
                        options='-vn -ar 48000 -ac 2 -f s16le',
                    )
                need_download = True

            # 播放並等待結束
            play_done = asyncio.Event()
            voice = self.voice_client
            outcome = {"connected": True}

            def after_callback(error):
                if error:
                    logger.error(f"[MusicPlayer] 播放錯誤: {error}")
                # 斷線把播放執行緒中止時 discord.py 不給錯誤，只能從「結束那一刻連線還在不在」分辨是播完還是被打斷
                outcome["connected"] = voice.is_connected()
                self.bot.loop.call_soon_threadsafe(play_done.set)

            def put_back():
                """沒播出去：續播的留到下一輪接著播，其他的排回佇列"""
                if resume is not None:
                    self._resume = resume
                else:
                    self.queue.requeue_song(song, is_interrupt_song)
                    self.queue.current = None

            if not self._has_active_voice():
                logger.warning("[MusicPlayer] 播放前偵測到 voice 已失效，重新排回歌曲並重連")
                self._reset_voice_client()
                put_back()
                return

            # 防呆：voice 仍在播時直接呼叫 play() 會丟 ClientException: Already playing audio
            # （通常是上一輪 _play_next 因 announcer 503 等例外提早跳出，play_done 未等待）
            if self.voice_client.is_playing():
                logger.warning("[MusicPlayer] voice_client 仍在播放，將歌曲排回稍後重試")
                put_back()
                await _sleep(2)
                return

            started_at = _clock()
            try:
                self.voice_client.play(audio_source, after=after_callback, bitrate=192)
            except discord.ClientException as e:
                logger.warning(f"[MusicPlayer] play() 時 voice 已失效，歌曲將回佇列重試: {e}")
                self._reset_voice_client()
                put_back()
                return

            if resume is None:
                # play() 已成功送出，loop 模式將歌曲循環回主歌單尾端（續播的上一輪已經記過）
                self.queue.mark_played(song, is_interrupt_song)

                # 通知「現在播放」面板（Discord HTTP 暫時性錯誤不應炸到播放迴圈）；續播不重發，面板上還是這一首
                if self.announcer:
                    try:
                        await self.announcer.send_now_playing(song)
                    except Exception as e:
                        logger.warning(f"[MusicPlayer] 發送現在播放面板失敗（不影響播放）: {e}")

                # 背景下載當前歌曲 + 預先快取下一首
                if need_download and song.webpage_url:
                    self._track_task(YTDLSource.download_to_cache(song.webpage_url))
                self._track_task(self._prefetch_next())

            await play_done.wait()
            if not outcome["connected"] and self._may_resume(song):
                position = max(0.0, resume_offset + (_clock() - started_at) - RESUME_REWIND_SECONDS)
                self._resume = (song, position, is_interrupt_song)
                logger.warning(f"[MusicPlayer] 播放被語音斷線打斷，重連後從第 {position:.0f} 秒接著播: {song.title}")
            elif not self._replay:
                self.queue.current = None
            await _sleep(0.5)

    async def _fetch_playlist_songs(self, url: str) -> list[Song]:
        """解析歌單 URL，回傳 Song 清單（純抓取，不動佇列）。順便快取歌單標題供自動命名。"""
        loop = asyncio.get_event_loop()
        try:
            title, entries = await loop.run_in_executor(
                None, lambda: YTDLSource._extract_playlist_sync(url)
            )
        except Exception as e:
            logger.error(f"[MusicPlayer] 歌單解析失敗: {e}")
            return []

        if title:
            self._playlist_titles[playlist_key(url)] = title

        songs = []
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
            songs.append(Song(
                title=entry.get('title', 'Unknown'),
                url=song_url,
                webpage_url=f"https://www.youtube.com/watch?v={video_id}" if video_id else song_url,
                duration=int(entry.get('duration', 0) or 0),
                thumbnail=thumbnail,
            ))
        return songs

    async def add_to_playlist(self, url: str):
        """將單一歌單 URL 逐批加入主佇列（邊解析邊播，不等全部完成）"""
        songs = await self._fetch_playlist_songs(url)
        for i in range(0, len(songs), 5):
            self.queue.add_to_main(songs[i:i + 5])
            logger.info(f"[MusicPlayer] 歌單載入中... 已加入 {len(self.queue.main_queue)} 首")
            await asyncio.sleep(0)
        logger.info(f"[MusicPlayer] 單一歌單載入完成，共 {len(self.queue.main_queue)} 首")

    async def load_active_playlists(self):
        """啟動時依目前選取的歌單集合載入（逐個歌單邊抓邊加，不清空舊佇列）"""
        urls = self.config.active_urls
        if not urls:
            logger.info("[MusicPlayer] 沒有選取任何歌單，略過載入")
            return
        for url in urls:
            await self.add_to_playlist(url)
        logger.info(
            f"[MusicPlayer] 啟動歌單載入完成，共 {len(self.queue.main_queue)} 首"
            f"（{len(urls)} 個歌單）"
        )

    async def _rebuild_main_from_urls(self, urls: list[str]) -> int | None:
        """先抓成功才換：抓取（可多個）歌單合併 → 清空點歌與舊主歌單 → 換上新清單。

        回傳新歌單歌曲數；若無歌單或抓取結果全為空則不動舊歌單，回傳 None。
        """
        if not urls or self._reloading:
            return None

        self._reloading = True
        try:
            # 先抓新清單，成功才動佇列，避免抓失敗把歌單清空導致沒歌可播
            all_songs: list[Song] = []
            for url in urls:
                all_songs.extend(await self._fetch_playlist_songs(url))
            if not all_songs:
                logger.warning("[MusicPlayer] 重建主歌單：抓取結果為空，保留舊歌單")
                return None

            self.queue.clear_all()  # 清掉點歌插播 + 舊主歌單
            for i in range(0, len(all_songs), 5):
                self.queue.add_to_main(all_songs[i:i + 5])
                await asyncio.sleep(0)
            self.queue.shuffle = self.config.shuffle  # 重新套用隨機狀態並決定下一首

            # 跳過正在播的（舊）歌，讓播放迴圈從新歌單抓下一首
            if self.voice_client and self.voice_client.is_playing():
                self.voice_client.stop()

            count = len(self.queue.main_queue)
            logger.info(f"[MusicPlayer] 主歌單已重建，共 {count} 首（{len(urls)} 個歌單）")
            return count
        finally:
            self._reloading = False

    async def reload_playlist(self) -> int | None:
        """重置按鈕：重新抓取「目前選取的歌單集合」最新線上清單。"""
        return await self._rebuild_main_from_urls(self.config.active_urls)

    async def set_active_playlists(self, keys: list[str]) -> int | None:
        """切換選取的歌單集合（以 key 指定）並持久化（重啟後保持），重建主歌單。

        回傳新歌單歌曲數；抓取失敗/為空則保留舊歌單回傳 None（但仍記住使用者選擇）。
        """
        self.config.active_keys = list(keys)
        count = await self._rebuild_main_from_urls(self.config.active_urls)
        # 不論抓取結果如何都記住使用者的選擇，重啟後沿用
        self._save_to_runtime("active_playlists", list(keys))
        return count

    async def resolve_playlist_titles(self) -> bool:
        """為未自訂名稱、且尚未抓過標題的歌單抓取 YouTube 標題填入快取。

        回傳是否有任何更新（供呼叫端決定要不要刷新面板）。
        """
        updated = False
        for p in self.config.playlists:
            if p.name:  # 使用者已自訂名稱 → 不用抓
                continue
            if p.key in self._playlist_titles:  # 載入歌單時已順便抓到
                continue
            title = await YTDLSource.extract_playlist_title(p.url)
            if title:
                self._playlist_titles[p.key] = title
                updated = True
        return updated

    def display_name(self, playlist) -> str:
        """歌單顯示名稱：自訂名稱 > 自動抓的 YouTube 標題 > 後備（歌單 key）"""
        return playlist.name or self._playlist_titles.get(playlist.key) or f"歌單 {playlist.key}"

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
        """寫入狀態檔的指定欄位（歌單檔是人手改的，程式不碰）"""
        try:
            save_state(key, value)
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
        return read_state().get("last_video_id")

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

    async def drop_requests_by(self, user_id: int) -> int:
        """移除某使用者點的歌：未播放的從插播佇列移除；
        正在播放的若是他點的，立即停止（效果等同跳過）。回傳處理的歌曲總數。
        （主歌單歌曲 requested_by_id 為 None，不會被誤砍。）"""
        dropped = self.queue.remove_interrupts_by(user_id)

        cur = self.queue.current
        if cur and cur.requested_by_id == user_id:
            # 停止當前歌曲，after callback 會讓播放迴圈抓下一首
            if self.voice_client and self.voice_client.is_playing():
                self.voice_client.stop()
            dropped += 1

        if dropped:
            logger.info(f"[MusicPlayer] 已移除使用者 {user_id} 點的 {dropped} 首歌")
        return dropped
