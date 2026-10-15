"""音樂的停機收尾（music/player.py 的 cleanup、music/cog.py 的 cog_unload）。

守的底線：
  - 停機時離開語音不會一直等：discord.py 斷線後要等 Discord 回報「已離開」，停機時讀事件的連線已經停了、回報永遠不會來
    （不設限會等滿 30 秒，超過 Docker 給的時間）；cleanup 要在時限內回來，而且連線要從 discord.py 取消登記
  - 取消落在關語音 websocket 那段（語音連線半死）時，discord.py 的 finally 還會再長等一次：一樣要在時限內回來
  - 語音正在重連（is_connected 是 False、player 已放掉參照）時，還登記在 discord.py 的連線也要斷：
    留著的話關 Discord 連線時會再等一次回報
  - 播放迴圈正在斷線／重連時，discord.py 會吞掉取消；cleanup 要再取消一次讓它停下，而且不會一直等
  - 停機開始後不再開新的播放迴圈：cog_unload 取消歌單載入時，那個 task 的 finally 會想開一個，要在取消前就擋下

不連 Discord：語音連線、伺服器、頻道都是假物件；時限調成幾十毫秒。
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

from music import cog as music_cog  # noqa: E402
from music import player as music_player  # noqa: E402


class FakeGuild:
    def __init__(self):
        self.voice_client = None


class FakeVoiceClient:
    """像 discord.py 的語音連線：disconnect 送出離開後等回報、回報永遠不會來；被取消時把取消吞掉，照樣收尾取消登記。"""

    def __init__(self, guild, connected=True):
        self.guild = guild
        self._connected = connected
        self.disconnects: list[bool] = []
        self.stopped = False

    def is_connected(self):
        return self._connected

    def is_playing(self):
        return True

    def stop(self):
        self.stopped = True

    def cleanup(self):
        """從 discord.py 的登記表拿掉（重複呼叫沒事）。"""
        self.guild.voice_client = None

    async def disconnect(self, *, force=False):
        self.disconnects.append(force)
        try:
            await asyncio.Event().wait()   # 等「已離開」的回報：停機時永遠等不到
        except asyncio.CancelledError:
            pass
        self.cleanup()


class HalfDeadVoiceClient(FakeVoiceClient):
    """語音 websocket 半死時的 discord.py：關 websocket 那段把取消往外丟，finally 裡再長等回報（吞掉取消）才收尾。"""

    async def disconnect(self, *, force=False):
        self.disconnects.append(force)
        try:
            await asyncio.Event().wait()   # 關語音 websocket：對方不回關閉框
        finally:
            try:
                await asyncio.Event().wait()   # 等「已離開」的回報
            except asyncio.CancelledError:
                pass
            self.cleanup()


def make_player(guild, voice_client=None):
    channel = SimpleNamespace(guild=guild)
    bot = SimpleNamespace(get_channel=lambda channel_id: channel)
    player = music_player.MusicPlayer(bot, SimpleNamespace(voice_channel_id=42))
    player.voice_client = voice_client
    return player


class PlayerCleanupTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        for name in ("CLOSE_DISCONNECT_TIMEOUT", "CLOSE_LOOP_TIMEOUT"):
            patcher = mock.patch.object(music_player, name, 0.05)
            patcher.start()
            self.addCleanup(patcher.stop)

    async def test_leaving_voice_does_not_wait_for_a_reply_that_never_comes(self):
        guild = FakeGuild()
        voice = FakeVoiceClient(guild)
        guild.voice_client = voice
        player = make_player(guild, voice)
        loop = asyncio.get_running_loop()
        started = loop.time()

        # 外層的 wait_for 時間到時，會被 disconnect 吞掉取消、照樣「正常回來」，所以要看花了多久，不能只看有沒有回來
        await asyncio.wait_for(player.cleanup(), timeout=3)

        self.assertLess(loop.time() - started, 2, "斷語音要在時限（這裡調成 0.05 秒）到時就放手，不是等到被外面取消")
        self.assertEqual(voice.disconnects, [True])
        self.assertTrue(voice.stopped)
        self.assertIsNone(player.voice_client)
        self.assertIsNone(guild.voice_client, "要從 discord.py 取消登記，關 Discord 連線時才不會再斷一次")

    async def test_half_dead_voice_connection_does_not_hold_it_up_either(self):
        guild = FakeGuild()
        voice = HalfDeadVoiceClient(guild)
        guild.voice_client = voice
        player = make_player(guild, voice)
        loop = asyncio.get_running_loop()
        started = loop.time()

        await asyncio.wait_for(player.cleanup(), timeout=3)

        self.assertLess(loop.time() - started, 2, "取消落在關 websocket 那段時，wait_for 擋不住 finally 裡的長等")
        self.assertIsNone(guild.voice_client, "時間到要直接取消登記，關 Discord 連線時才不會又斷一次、再等一次")

    async def test_voice_that_is_reconnecting_is_still_disconnected(self):
        guild = FakeGuild()
        voice = FakeVoiceClient(guild, connected=False)
        guild.voice_client = voice
        player = make_player(guild, voice_client=None)   # 重連中：player 已放掉參照，連線還登記在 discord.py

        await asyncio.wait_for(player.cleanup(), timeout=5)

        self.assertEqual(voice.disconnects, [True])
        self.assertIsNone(guild.voice_client)

    async def test_play_loop_that_swallows_the_cancel_is_cancelled_again(self):
        player = make_player(FakeGuild())

        async def loop_in_the_middle_of_reconnecting():
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                pass   # 斷線中：discord.py 把這次取消吞掉
            await asyncio.sleep(3600)   # 接著照迴圈平常的做法，睡幾秒再重連

        loop_task = asyncio.create_task(loop_in_the_middle_of_reconnecting())
        player._task = loop_task
        await asyncio.sleep(0)

        await asyncio.wait_for(player.cleanup(), timeout=5)
        await asyncio.wait({loop_task}, timeout=1)   # 最後一次取消可能在時限到時才送出，給它醒來一下

        self.assertTrue(loop_task.cancelled(), "第一次取消被吞掉後要再取消一次，迴圈才不會繼續重連")
        self.assertIsNone(player._task)

    async def test_no_new_play_loop_once_closing(self):
        player = make_player(FakeGuild())
        player.mark_closing()

        await player.start_background_loop()
        started = player._task
        if started is not None:
            started.cancel()   # 還沒輪到它跑就收掉：假的伺服器連不上語音，真讓它跑會一直空轉

        self.assertIsNone(started)


class CogUnloadTests(unittest.IsolatedAsyncioTestCase):
    async def test_cancelled_playlist_load_cannot_start_a_play_loop(self):
        with mock.patch.object(music_cog.RuntimeMusicConfig, "get_config", return_value=None):
            cog = music_cog.MusicCog(SimpleNamespace())
        cog.config = SimpleNamespace(active_keys=[], shuffle=False)
        cog.player = make_player(FakeGuild())
        cog.player.cleanup = mock.AsyncMock()
        closing_when_restarted: list[bool] = []

        async def start_background_loop():
            closing_when_restarted.append(cog.player._closing)

        cog.player.start_background_loop = start_background_loop
        loading = asyncio.Event()

        async def load_active_playlists():
            loading.set()
            await asyncio.sleep(3600)

        cog.player.load_active_playlists = load_active_playlists
        cog._playlist_task = asyncio.create_task(cog._load_playlist_background())
        await loading.wait()

        async def stop_watcher():
            await asyncio.sleep(0)   # 真的 stop_watcher 會讓出 event loop，被取消的歌單 task 這時跑 finally

        with mock.patch.object(music_cog.RuntimeMusicConfig, "stop_watcher", new=stop_watcher):
            await cog.cog_unload()

        self.assertEqual(closing_when_restarted, [True], "歌單 task 的 finally 跑的時候，播放器要已經在停機狀態")


if __name__ == "__main__":
    unittest.main()
