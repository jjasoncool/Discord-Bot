"""音樂播放器：長期掛在固定語音頻道，依佇列下載、播放歌曲，並記住播放位置。

架構定位：介面層（`music/`，直接操作 Discord 語音連線）。
  - 上層（誰呼叫）：`music.cog.MusicCog`（建立播放器、啟動播放迴圈、cog_unload 時呼叫 `mark_closing`／`cleanup`）、
    `music.announcer` 的面板按鈕（跳過、重播、插播）。
  - 下層（呼叫誰）：discord.py 的語音連線、`music.ytdl`（下載與快取）、`music.queue`、`music.config`（狀態檔）。

介面（停機相關）：`mark_closing()`、`cleanup()`；其餘是播放控制（`start_background_loop`、`ensure_voice`、跳過、重播、插播）。

規則：
  - 停機時 `cleanup` 的每一步都有時限（CLOSE_LOOP_TIMEOUT、CLOSE_DISCONNECT_TIMEOUT），整個 bot 的停機收尾只有幾秒。
  - `mark_closing` 之後不再開新的播放迴圈。

例外與決策：停機時離開語音不用 discord.py 的 disconnect 等到底：讀 Discord 事件的連線已經停了，「已離開」的回報永遠
  不會來（它會等 30 秒）；而且取消若落在關語音 websocket 那段，它的 finally 還會再等一次，包 wait_for 也擋不住。
  所以斷線放進自己的 task，時間到就直接從 discord.py 取消登記。
"""
import os
import re
import asyncio
import logging
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
        """強制斷開並清理 guild 上的殘留 voice_client，含 disconnect 的硬 timeout"""
        self._reset_voice_client()
        existing = guild.voice_client
        if existing is not None:
            try:
                # discord.py 的 disconnect 在 voice gateway 已死時也可能 hang，硬性限時
                await asyncio.wait_for(existing.disconnect(force=True), timeout=5)
            except (asyncio.TimeoutError, Exception):
                pass
        try:
            guild._voice_client = None
        except Exception:
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
        if self.voice_client is not None:
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
            logger.info("[MusicPlayer] 清理 guild 殘留語音連線")
            await self._force_cleanup_guild_voice(guild)
            await asyncio.sleep(3)

        # 第一次嘗試
        if await self._try_connect(channel):
            return True

        # 失敗則強制清理 guild 狀態後再試一次（不等 _play_loop 5 秒）
        logger.info("[MusicPlayer] 第一次連線失敗，強制清理後立即重試")
        await self._force_cleanup_guild_voice(guild)
        await asyncio.sleep(2)
        if await self._try_connect(channel):
            return True

        logger.error("[MusicPlayer] 加入語音頻道失敗（兩次嘗試皆失敗）")
        return False

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

            # 音訊模式：pcm 或 opus（在歌單檔 music_playlists.json 的 audio_mode 切換）
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

            # 防呆：voice 仍在播時直接呼叫 play() 會丟 ClientException: Already playing audio
            # （通常是上一輪 _play_next 因 announcer 503 等例外提早跳出，play_done 未等待）
            if self.voice_client.is_playing():
                logger.warning("[MusicPlayer] voice_client 仍在播放，將歌曲排回稍後重試")
                self.queue.requeue_song(song, is_interrupt_song)
                self.queue.current = None
                await asyncio.sleep(2)
                return

            try:
                self.voice_client.play(audio_source, after=after_callback, bitrate=192)
            except discord.ClientException as e:
                logger.warning(f"[MusicPlayer] play() 時 voice 已失效，歌曲將回佇列重試: {e}")
                self._reset_voice_client()
                self.queue.requeue_song(song, is_interrupt_song)
                self.queue.current = None
                return

            # play() 已成功送出，loop 模式將歌曲循環回主歌單尾端
            self.queue.mark_played(song, is_interrupt_song)

            # 通知「現在播放」面板（Discord HTTP 暫時性錯誤不應炸到播放迴圈）
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
            if not self._replay:
                self.queue.current = None
            await asyncio.sleep(0.5)

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
