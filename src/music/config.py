import os
import json
import asyncio
import logging
from dataclasses import dataclass
from typing import Optional, Callable, Awaitable

logger = logging.getLogger('discord_bot')

# 頻道設定來源（與其他頻道設定一致）
CONFIG_JSON_PATH = "config.json"
# 歌單等音樂專屬設定
MUSIC_RUNTIME_PATH = "settings/music_runtime.json"

@dataclass
class MusicConfig:
    voice_channel_id: int
    default_playlist_url: str
    audio_mode: str = 'opus'  # 'pcm' 或 'opus'，可在 music_runtime.json 切換
    shuffle: bool = False

class RuntimeMusicConfig:
    _instance: Optional['RuntimeMusicConfig'] = None
    _config: MusicConfig | None = None
    _last_mtime_config: float = 0
    _last_mtime_runtime: float = 0
    _watch_task: asyncio.Task | None = None
    _on_change_callback: Callable[['MusicConfig'], Awaitable[None]] | None = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def get_config(cls) -> MusicConfig | None:
        """回傳配置，若未載入或載入失敗則回傳 None"""
        if cls._config is None:
            cls._load_config()
        return cls._config

    @classmethod
    def set_on_change(cls, callback: Callable[['MusicConfig'], Awaitable[None]]):
        """註冊配置變更 callback"""
        cls._on_change_callback = callback

    @classmethod
    def _load_config(cls) -> bool:
        """從 config.json 讀頻道、music_runtime.json 讀歌單，回傳是否成功"""
        # 讀取頻道 ID（from config.json）
        voice_channel_id = 0
        if os.path.exists(CONFIG_JSON_PATH):
            try:
                with open(CONFIG_JSON_PATH, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                voice_channel_id = int(data.get("music_voice_channel_id", 0))
            except Exception as e:
                logger.warning(f"[MusicConfig] 讀取 config.json 失敗: {e}")

        if not voice_channel_id:
            logger.warning("[MusicConfig] config.json 中未設定 music_voice_channel_id，音樂功能不啟用")
            cls._config = None
            return False

        # 讀取歌單、音訊模式、shuffle（from music_runtime.json）
        default_playlist_url = ""
        audio_mode = "pcm"
        shuffle = False
        if os.path.exists(MUSIC_RUNTIME_PATH):
            try:
                with open(MUSIC_RUNTIME_PATH, 'r', encoding='utf-8') as f:
                    runtime_data = json.load(f).get("music", {})
                default_playlist_url = runtime_data.get("default_playlist_url", "")
                audio_mode = runtime_data.get("audio_mode", "pcm")
                shuffle = runtime_data.get("shuffle", False)
            except Exception as e:
                logger.warning(f"[MusicConfig] 讀取 music_runtime.json 失敗: {e}")

        cls._config = MusicConfig(
            voice_channel_id=voice_channel_id,
            default_playlist_url=default_playlist_url,
            audio_mode=audio_mode if audio_mode in ('pcm', 'opus') else 'pcm',
            shuffle=bool(shuffle),
        )

        # 記錄兩個檔案的 mtime
        if os.path.exists(CONFIG_JSON_PATH):
            cls._last_mtime_config = os.path.getmtime(CONFIG_JSON_PATH)
        if os.path.exists(MUSIC_RUNTIME_PATH):
            cls._last_mtime_runtime = os.path.getmtime(MUSIC_RUNTIME_PATH)

        logger.info(f"🎵 [MusicConfig] 已載入配置 (voice: {voice_channel_id}, playlist: {'有' if default_playlist_url else '無'})")
        return True

    @classmethod
    async def start_watcher(cls):
        """背景 watcher：每 5 秒檢查兩個檔案是否變更"""
        if cls._watch_task and not cls._watch_task.done():
            return
        cls._watch_task = asyncio.create_task(cls._watch_loop())

    @classmethod
    async def stop_watcher(cls):
        """停止背景 watcher"""
        if cls._watch_task and not cls._watch_task.done():
            cls._watch_task.cancel()
            try:
                await cls._watch_task
            except asyncio.CancelledError:
                pass
        cls._watch_task = None
        cls._on_change_callback = None

    @classmethod
    async def _watch_loop(cls):
        while True:
            try:
                changed = False
                if os.path.exists(CONFIG_JSON_PATH):
                    mtime = os.path.getmtime(CONFIG_JSON_PATH)
                    if mtime > cls._last_mtime_config:
                        changed = True
                if os.path.exists(MUSIC_RUNTIME_PATH):
                    mtime = os.path.getmtime(MUSIC_RUNTIME_PATH)
                    if mtime > cls._last_mtime_runtime:
                        changed = True

                if changed:
                    logger.info("🔄 [MusicConfig] 偵測到配置變更 → 熱重載")
                    cls._load_config()
                    if cls._on_change_callback and cls._config:
                        try:
                            await cls._on_change_callback(cls._config)
                        except Exception as e:
                            logger.error(f"[MusicConfig] on_change callback 錯誤: {e}", exc_info=True)
            except Exception as e:
                logger.warning(f"[MusicConfig] watcher 錯誤: {e}")
            await asyncio.sleep(5)
