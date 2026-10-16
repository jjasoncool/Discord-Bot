"""語音斷線後的重連（music/player.py 的 ensure_voice 與 _play_next）。

守的底線：
  - 語音連線還登記在 discord.py、只是斷了（它正在自己重連）：播放器不動手，等它接回來就沿用同一條連線，
    不對它 disconnect、也不另建連線（另建會留下舊連線的背景工作，30 秒後把新連線踢出頻道）
  - 過了寬限期（discord.py 自己一次重連的上限再加一點）還沒接回：在同一個連線物件上重連，不另建新連線
  - discord.py 自己放棄、把連線從登記表拿掉：不再白等，直接建新連線
  - 同一物件重連失敗（discord.py 會把它取消登記）：退回建新連線
  - 正在播的歌被斷線中止：重連後從斷掉的地方接著播同一首，不算播完、不跳下一首、不重複記入已播；
    同一首連續被打斷太多次才放棄
  - 歌正常播完（連線還在）：照常換下一首

不連 Discord：語音連線、頻道、伺服器、ffmpeg 音源都是假物件；時間用 test.fake_clock.FakeClock，不真的等。
"""
import asyncio
import os
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from music import player as music_player  # noqa: E402
from music.models import Song  # noqa: E402
from test.fake_clock import FakeClock  # noqa: E402


class FakeGuild:
    def __init__(self):
        self.voice_client = None


class FakeChannel:
    """音樂用的語音頻道；connect 像 discord.py 一樣建一條新連線並登記到 guild。"""

    def __init__(self, guild, channel_id=42):
        self.guild = guild
        self.id = channel_id
        self.name = "音樂"
        self.connects: list[float] = []

    async def connect(self, *, self_deaf=False, timeout=30.0):
        self.connects.append(timeout)
        voice = FakeVoiceClient(self.guild, self, connected=True)
        self.guild.voice_client = voice
        return voice


class FakeVoiceClient:
    """像 discord.py 的語音連線：is_connected 由測試控制；connect 成功就接回，失敗就像 discord.py 一樣先取消登記再丟逾時。"""

    def __init__(self, guild, channel, connected):
        self.guild = guild
        self.channel = channel
        self.connected = connected
        self.connect_calls: list[tuple] = []
        self.disconnects: list[bool] = []
        self.sources: list = []
        self.connect_outcome = "ok"
        self._after = None
        self._playing = False

    def is_connected(self):
        return self.connected

    def is_playing(self):
        return self._playing

    def stop(self):
        self._playing = False

    def cleanup(self):
        if self.guild.voice_client is self:
            self.guild.voice_client = None

    async def connect(self, *, reconnect, timeout, self_deaf=False, self_mute=False):
        self.connect_calls.append((reconnect, timeout))
        if self.connect_outcome != "ok":
            self.cleanup()
            raise asyncio.TimeoutError
        self.connected = True

    async def disconnect(self, *, force=False):
        self.disconnects.append(force)
        self.connected = False
        self.cleanup()

    def play(self, source, *, after=None, bitrate=None):
        self.sources.append(source)
        self._after = after
        self._playing = True

    def end_playback(self, *, connected):
        """播放執行緒結束：connected=False 就是被斷線中止（discord.py 不會給錯誤）。"""
        self.connected = connected
        self._playing = False
        after, self._after = self._after, None
        after(None)


class FakeSource:
    def __init__(self, path, *, before_options="", options=""):
        self.path = path
        self.before_options = before_options
        self.options = options


async def until(pred, *, tries=2000):
    for _ in range(tries):
        if pred():
            return
        await asyncio.sleep(0)
    raise AssertionError("等不到條件成立")


class VoiceReconnectTestCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.clock = FakeClock()
        self.enterContext(mock.patch.object(music_player, "_clock", self.clock.now))
        self.enterContext(mock.patch.object(music_player, "_sleep", self.clock.sleep))
        self.enterContext(mock.patch.object(music_player.discord, "VoiceChannel", FakeChannel))
        self.guild = FakeGuild()
        self.channel = FakeChannel(self.guild)
        bot = SimpleNamespace(get_channel=lambda channel_id: self.channel, loop=asyncio.get_running_loop())
        self.player = music_player.MusicPlayer(bot, SimpleNamespace(voice_channel_id=42, audio_mode="pcm"))

    def broken_voice(self):
        """手上的連線斷了、但還登記在 discord.py（它正在自己重連）。"""
        voice = FakeVoiceClient(self.guild, self.channel, connected=False)
        self.guild.voice_client = voice
        self.player.voice_client = voice
        return voice

    async def after(self, seconds, action):
        await self.clock.sleep(seconds)
        action()


class EnsureVoiceTests(VoiceReconnectTestCase):
    async def test_waits_for_discord_py_to_reconnect_and_keeps_the_same_client(self):
        voice = self.broken_voice()
        asyncio.create_task(self.after(3, lambda: setattr(voice, "connected", True)))

        ok = await self.player.ensure_voice()

        self.assertTrue(ok)
        self.assertIs(self.player.voice_client, voice)
        self.assertEqual([], voice.disconnects, "discord.py 正在重連時不能動它")
        self.assertEqual([], voice.connect_calls)
        self.assertEqual([], self.channel.connects, "不能另建連線")
        self.assertGreaterEqual(self.clock.now(), 3)
        self.assertLess(self.clock.now(), music_player.RECONNECT_GRACE_SECONDS)

    async def test_reconnects_on_the_same_client_after_the_grace_period(self):
        voice = self.broken_voice()

        ok = await self.player.ensure_voice()

        self.assertTrue(ok)
        self.assertIs(self.player.voice_client, voice)
        self.assertGreaterEqual(self.clock.now(), music_player.RECONNECT_GRACE_SECONDS)
        self.assertEqual([(True, 30)], voice.connect_calls, "寬限期過了才在同一條連線上重連")
        self.assertEqual([], voice.disconnects)
        self.assertEqual([], self.channel.connects, "同一條連線接回來就不另建")

    async def test_builds_a_new_client_when_discord_py_gave_up(self):
        voice = self.broken_voice()
        asyncio.create_task(self.after(5, voice.cleanup))   # discord.py 放棄：從登記表拿掉

        ok = await self.player.ensure_voice()

        self.assertTrue(ok)
        self.assertEqual(1, len(self.channel.connects))
        self.assertIs(self.player.voice_client, self.guild.voice_client)
        self.assertIsNot(self.player.voice_client, voice)
        self.assertEqual([], voice.connect_calls, "已取消登記的連線收不到語音事件，重連它沒有用")
        self.assertLess(self.clock.now(), music_player.RECONNECT_GRACE_SECONDS, "它放棄了就不該等滿寬限期")

    async def test_falls_back_to_a_new_client_when_the_same_client_cannot_reconnect(self):
        voice = self.broken_voice()
        voice.connect_outcome = "timeout"

        ok = await self.player.ensure_voice()

        self.assertTrue(ok)
        self.assertEqual([(True, 30)], voice.connect_calls)
        self.assertEqual(1, len(self.channel.connects))
        self.assertIs(self.player.voice_client, self.guild.voice_client)
        self.assertIsNot(self.player.voice_client, voice)

    async def test_connected_client_is_reused_without_waiting(self):
        voice = FakeVoiceClient(self.guild, self.channel, connected=True)
        self.guild.voice_client = voice
        self.player.voice_client = voice

        self.assertTrue(await self.player.ensure_voice())
        self.assertEqual(0, self.clock.now())
        self.assertEqual([], self.channel.connects)


class ResumeAfterDisconnectTests(VoiceReconnectTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.voice = FakeVoiceClient(self.guild, self.channel, connected=True)
        self.guild.voice_client = self.voice
        self.player.voice_client = self.voice
        self.song1 = Song(title="一", url="u1", webpage_url="https://youtu.be/vid1", duration=300)
        self.song2 = Song(title="二", url="u2", webpage_url="https://youtu.be/vid2", duration=200)
        self.player.queue.add_to_main([self.song1, self.song2])
        self.enterContext(mock.patch.object(music_player.discord, "FFmpegPCMAudio", FakeSource))
        self.enterContext(mock.patch.object(music_player.YTDLSource, "_extract_video_id",
                                            staticmethod(lambda url: url.rsplit("/", 1)[-1])))
        self.enterContext(mock.patch.object(music_player.YTDLSource, "get_cache_path",
                                            staticmethod(lambda video_id: f"/cache/{video_id}.pcm")))
        self.enterContext(mock.patch.object(music_player.MusicPlayer, "_get_peak_db",
                                            staticmethod(mock.AsyncMock(return_value=None))))
        self.enterContext(mock.patch.object(music_player.MusicPlayer, "_save_last_position", staticmethod(lambda vid: None)))
        self.enterContext(mock.patch.object(music_player.MusicPlayer, "_prefetch_next", mock.AsyncMock()))
        self.marked: list[str] = []
        real_mark = self.player.queue.mark_played

        def spy_mark(song, is_interrupt):
            self.marked.append(song.title)
            return real_mark(song, is_interrupt)

        self.player.queue.mark_played = spy_mark

    async def play_one_round(self):
        task = asyncio.create_task(self.player._play_next())
        await until(lambda: self.voice.sources and self.voice._after is not None)
        return task

    async def test_interrupted_song_resumes_from_where_it_stopped(self):
        task = await self.play_one_round()
        self.assertEqual("/cache/vid1.pcm", self.voice.sources[0].path)
        await self.clock.sleep(20)                       # 播了 20 秒
        self.voice.end_playback(connected=False)         # 斷線把播放執行緒中止
        await task
        asyncio.create_task(self.after(2, lambda: setattr(self.voice, "connected", True)))  # discord.py 自己接回

        task = await self.play_one_round()

        resumed = self.voice.sources[1]
        self.assertEqual("/cache/vid1.pcm", resumed.path, "接著播同一首，不是下一首")
        self.assertIn("-ss 19.0", resumed.before_options, "從斷掉的地方（倒退一秒）接著播")
        self.assertEqual(["一"], self.marked, "續播不重複記入已播")
        self.assertIs(self.player.queue.current, self.song1)
        self.voice.end_playback(connected=True)
        await task

        task = await self.play_one_round()
        self.assertEqual("/cache/vid2.pcm", self.voice.sources[2].path, "播完才換下一首")
        self.assertNotIn("-ss", self.voice.sources[2].before_options)
        self.voice.end_playback(connected=True)
        await task

    async def test_song_that_ends_normally_moves_on(self):
        task = await self.play_one_round()
        await self.clock.sleep(300)
        self.voice.end_playback(connected=True)
        await task

        task = await self.play_one_round()
        self.assertEqual("/cache/vid2.pcm", self.voice.sources[1].path)
        self.assertEqual(["一", "二"], self.marked)
        self.voice.end_playback(connected=True)
        await task

    async def test_gives_up_resuming_after_too_many_interruptions(self):
        for _ in range(music_player.MAX_RESUMES_PER_SONG + 1):
            task = await self.play_one_round()
            await self.clock.sleep(5)
            self.voice.end_playback(connected=False)
            await task
            self.voice.connected = True

        task = await self.play_one_round()
        self.assertEqual("/cache/vid2.pcm", self.voice.sources[-1].path, "連續被打斷太多次就換下一首")
        self.voice.end_playback(connected=True)
        await task


if __name__ == "__main__":
    unittest.main()
