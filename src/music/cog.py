import logging
import asyncio
import discord
from discord.ext import commands
from .config import RuntimeMusicConfig, MusicConfig
from .player import MusicPlayer
from .announcer import Announcer, MusicControlView

logger = logging.getLogger('discord_bot')


class MusicCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config = RuntimeMusicConfig.get_config()
        self.player = None
        self.announcer = None
        self._starting = False
        self._view_registered = False

    async def cog_load(self):
        """Cog 載入（由 add_cog 自動呼叫，只做輕量初始化）"""
        RuntimeMusicConfig.set_on_change(self._on_config_change)
        await RuntimeMusicConfig.start_watcher()

        if not self.config or not self.config.voice_channel_id:
            logger.warning("[MusicCog] 音樂功能未設定，等待配置變更")
            return

        self._init_components()
        logger.info("[MusicCog] cog_load 完成，等待 on_ready 再連線")

    def _init_components(self):
        """初始化 announcer 和 player（已存在就複用，避免丟失面板參照）"""
        if self.announcer is None:
            self.announcer = Announcer(self.bot, self.config.voice_channel_id, cog=self)
        else:
            self.announcer.voice_channel_id = self.config.voice_channel_id
        if self.player is None:
            self.player = MusicPlayer(self.bot, self.config)
        else:
            self.player.config = self.config
        self.player.announcer = self.announcer

        # persistent view 只註冊一次
        if not self._view_registered:
            self.bot.add_view(MusicControlView(self))
            self._view_registered = True

    @commands.Cog.listener()
    async def on_ready(self):
        """Bot ready / reconnect 後嘗試連線語音"""
        logger.info("[MusicCog] on_ready 觸發")

        if not self.player:
            return

        # 已經連線中就跳過
        if self.player.voice_client and self.player.voice_client.is_connected():
            logger.info("[MusicCog] 已在語音頻道中，跳過")
            return

        # 延遲讓 voice gateway 穩定
        await asyncio.sleep(5)
        await self._start_if_ready()

    async def _start_if_ready(self):
        """連線語音並啟動播放"""
        if not self.player:
            return

        if self._starting:
            logger.info("[MusicCog] 啟動中，跳過重複呼叫")
            return

        if self.player.voice_client and self.player.voice_client.is_connected():
            return

        self._starting = True
        try:
            logger.info(f"[MusicCog] 嘗試加入語音頻道 {self.config.voice_channel_id}")
            connected = await self.player.ensure_voice()
            if not connected:
                logger.warning("[MusicCog] 無法加入語音頻道")
                return

            # 清理上次殘留的面板
            await self.announcer.cleanup_old_panel()

            # 先啟動播放迴圈和面板，歌單背景載入（不阻塞點歌）
            await self.player.start_background_loop()
            await self.announcer.send_idle_panel()

            if self.config.default_playlist_url:
                asyncio.create_task(self._load_playlist_background())
        finally:
            self._starting = False

    async def _load_playlist_background(self):
        """背景載入預設歌單，不阻塞其他操作"""
        try:
            logger.info("[MusicCog] 開始背景載入預設歌單...")
            await self.player.add_to_playlist(self.config.default_playlist_url)
            count = len(self.player.queue.main_queue)
            logger.info(f"[MusicCog] 預設歌單已載入（{count} 首可播放）")

            # 跳到上次播放位置
            last_vid = MusicPlayer.get_last_position()
            if last_vid:
                self.player.skip_to_video_id(last_vid)
        except Exception as e:
            logger.error(f"[MusicCog] 載入歌單失敗: {e}", exc_info=True)

    async def _on_config_change(self, new_config: MusicConfig):
        """配置變更時處理"""
        old_voice_id = self.config.voice_channel_id if self.config else 0
        self.config = new_config

        if not new_config.voice_channel_id:
            logger.warning("[MusicCog] voice_channel_id 為 0，音樂功能停用")
            return

        # 頻道沒變，只更新 config
        if old_voice_id == new_config.voice_channel_id:
            logger.info(f"[MusicCog] 配置已更新（頻道未變: {new_config.voice_channel_id}）")
            self._init_components()
            return

        # 頻道有變，斷開舊連接再重連
        logger.info(f"[MusicCog] 語音頻道變更 {old_voice_id} → {new_config.voice_channel_id}，重新連接")
        if self.player and self.player.voice_client and self.player.voice_client.is_connected():
            await self.player.voice_client.disconnect(force=True)
            self.player.voice_client = None
            await asyncio.sleep(3)

        self.player = None
        self.announcer = None  # 頻道變了，重建 announcer
        self._init_components()
        await self._start_if_ready()


async def setup(bot: commands.Bot):
    cog = MusicCog(bot)
    await bot.add_cog(cog)
