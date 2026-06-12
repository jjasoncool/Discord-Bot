import logging
import asyncio
import discord
from discord.ext import commands
from .config import RuntimeMusicConfig, MusicConfig
from .player import MusicPlayer
from .announcer import Announcer, MusicControlView

logger = logging.getLogger('discord_bot')

# 點歌者離開音樂頻道後，砍歌前的寬限秒數（避免短暫閃斷/重連誤砍）
LEAVE_GRACE_SECONDS = 5


class MusicCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config = RuntimeMusicConfig.get_config()
        self.player = None
        self.announcer = None
        self._starting = False
        self._view_registered = False
        self._playlist_task: asyncio.Task | None = None
        self._leave_tasks: set[asyncio.Task] = set()  # 追蹤點歌者離開的延遲處理 task，避免被 GC

    async def cog_load(self):
        """Cog 載入（由 add_cog 自動呼叫，只做輕量初始化）"""
        RuntimeMusicConfig.set_on_change(self._on_config_change)
        await RuntimeMusicConfig.start_watcher()

        if not self.config or not self.config.voice_channel_id:
            logger.warning("[MusicCog] 音樂功能未設定，等待配置變更")
            return

        self._init_components()
        logger.info("[MusicCog] cog_load 完成，等待 on_ready 再連線")

    async def cog_unload(self):
        """Cog 卸載時清理所有資源"""
        logger.info("[MusicCog] cog_unload: 開始清理資源")

        # 取消歌單載入 task
        if self._playlist_task and not self._playlist_task.done():
            self._playlist_task.cancel()
            self._playlist_task = None

        # 取消尚未完成的「離開砍歌」延遲 task
        for task in list(self._leave_tasks):
            task.cancel()
        self._leave_tasks.clear()

        # 停止 config watcher
        await RuntimeMusicConfig.stop_watcher()

        # 清理 player（背景 tasks、語音連線等）
        if self.player:
            await self.player.cleanup()

        # 清理面板訊息引用
        if self.announcer:
            self.announcer._panel_message = None

        logger.info("[MusicCog] cog_unload: 清理完成")

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

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        """點歌者離開音樂語音頻道時，自動移除他點的歌（寬限 5 秒）"""
        if member.bot or not self.player or not self.config:
            return
        channel_id = self.config.voice_channel_id
        if not channel_id:
            return

        # 從音樂頻道離開（完全離開或切到別的頻道都算）
        left_music_channel = (
            before.channel is not None and before.channel.id == channel_id
            and (after.channel is None or after.channel.id != channel_id)
        )
        if left_music_channel:
            logger.info(
                f"[MusicCog] 偵測到 {member.display_name}({member.id}) 離開音樂頻道，"
                f"{LEAVE_GRACE_SECONDS} 秒後檢查其點歌"
            )
            # 必須保留 task 參照，否則可能在 sleep 期間被 GC 回收而不執行完
            task = asyncio.create_task(self._handle_requester_left(member))
            self._leave_tasks.add(task)
            task.add_done_callback(self._leave_tasks.discard)

    async def _handle_requester_left(self, member):
        """寬限數秒後，若點歌者仍未回到音樂頻道，移除他點的歌並公告"""
        try:
            await asyncio.sleep(LEAVE_GRACE_SECONDS)

            channel = self.bot.get_channel(self.config.voice_channel_id)
            # 又回到音樂頻道就不處理（避免短暫閃斷/重連誤砍）
            if channel and any(
                m.id == member.id for m in getattr(channel, "members", [])
            ):
                logger.info(f"[MusicCog] {member.display_name} 已回到音樂頻道，保留其點的歌")
                return

            dropped = await self.player.drop_requests_by(member.id)
            logger.info(f"[MusicCog] {member.display_name} 離開後移除 {dropped} 首點歌")
            if dropped and channel:
                try:
                    await channel.send(
                        embed=discord.Embed(
                            description=f"👋 **{member.display_name}** 已離開，已移除其點的 {dropped} 首歌。",
                            color=discord.Color.greyple(),
                        )
                    )
                except Exception as e:
                    logger.warning(f"[MusicCog] 發送離開移除公告失敗: {e}")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"[MusicCog] 處理點歌者離開失敗: {e}", exc_info=True)

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
            await self.announcer.send_idle_panel()

            if self.config.default_playlist_url:
                # 歌單載完、shuffle 設好、跳到上次位置後才啟動播放迴圈，
                # 避免迴圈搶先從半載的佇列抓到錯誤的第一首
                self._playlist_task = asyncio.create_task(self._load_playlist_background())
            else:
                await self.player.start_background_loop()
        finally:
            self._starting = False

    async def _load_playlist_background(self):
        """背景載入預設歌單 → 設定 shuffle / 跳轉 → 啟動播放迴圈"""
        try:
            logger.info("[MusicCog] 開始背景載入預設歌單...")
            await self.player.add_to_playlist(self.config.default_playlist_url)
            count = len(self.player.queue.main_queue)
            logger.info(f"[MusicCog] 預設歌單已載入（{count} 首可播放）")

            # 恢復 shuffle 狀態
            self.player.queue.shuffle = self.config.shuffle
            logger.info(f"[MusicCog] shuffle: {'開啟' if self.config.shuffle else '關閉'}")

            # 跳到上次播放位置
            last_vid = MusicPlayer.get_last_position()
            if last_vid:
                self.player.skip_to_video_id(last_vid)
        except Exception as e:
            logger.error(f"[MusicCog] 載入歌單失敗: {e}", exc_info=True)
        finally:
            # 不論成功失敗都啟動播放迴圈，避免永遠不播
            await self.player.start_background_loop()

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
