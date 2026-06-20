import os
import re
import json
import asyncio
import logging
from dataclasses import dataclass, field
from typing import Optional, Callable, Awaitable

logger = logging.getLogger('discord_bot')

# 頻道設定來源（與其他頻道設定一致）
CONFIG_JSON_PATH = "config.json"
# 歌單等音樂專屬設定
MUSIC_RUNTIME_PATH = "settings/music_runtime.json"


def playlist_key(url: str) -> str:
    """從 URL 取出穩定識別：優先用歌單 list id，其次影片 id，最後用 URL 本身（截斷）。

    這個 key 用於下拉選單 value 與「目前選取」的持久化，獨立於可能自動抓取/變動的顯示名稱。
    """
    m = re.search(r'[?&]list=([A-Za-z0-9_-]+)', url or '')
    if m:
        return m.group(1)
    m = re.search(r'(?:v=|/v/|youtu\.be/)([a-zA-Z0-9_-]{11})', url or '')
    if m:
        return m.group(1)
    return (url or '')[:100]


@dataclass
class Playlist:
    """單一歌單。

    key  ── 穩定識別（list id / video id / url），給下拉 value 與選取持久化用。
    url  ── YouTube 歌單或影片 URL。
    name ── 顯示名稱；None 代表未自訂，會在背景自動抓取 YouTube 歌單標題。
    """
    key: str
    url: str
    name: Optional[str] = None


@dataclass
class MusicConfig:
    voice_channel_id: int
    # 多歌單清單；舊格式（單一 default_playlist_url）載入時會自動轉成一筆
    playlists: list = field(default_factory=list)        # list[Playlist]
    # 目前選取的歌單 key（可複選），預設為全部
    active_keys: list = field(default_factory=list)      # list[str]
    audio_mode: str = 'opus'  # 'pcm' 或 'opus'，可在 music_runtime.json 切換
    shuffle: bool = False

    @property
    def default_playlist_url(self) -> str:
        """向後相容：第一個歌單的 URL（沒有歌單則回空字串）"""
        return self.playlists[0].url if self.playlists else ""

    @property
    def active_urls(self) -> list:
        """目前選取的歌單 URL 清單（依 playlists 原始順序，過濾出有選的 key）"""
        selected = set(self.active_keys)
        return [p.url for p in self.playlists if p.key in selected]

    @property
    def has_playlists(self) -> bool:
        return bool(self.playlists)

class RuntimeMusicConfig:
    _instance: Optional['RuntimeMusicConfig'] = None
    _config: MusicConfig | None = None
    _last_mtime_config: float = 0
    _last_mtime_runtime: float = 0
    _watch_task: asyncio.Task | None = None
    _on_change_callback: Callable[['MusicConfig'], Awaitable[None]] | None = None
    # 只監控這些欄位的變化，忽略 last_video_id / panel_message_id
    _watched_keys: tuple = (
        'playlist_url', 'default_playlist_url', 'active_playlists', 'audio_mode', 'shuffle',
    )

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
    def force_reload(cls) -> MusicConfig | None:
        """立即從檔案重讀設定並回傳（供「重置歌單」按鈕等不想等 5 秒 watcher 的情境）"""
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
        runtime_data = {}
        audio_mode = "pcm"
        shuffle = False
        if os.path.exists(MUSIC_RUNTIME_PATH):
            try:
                with open(MUSIC_RUNTIME_PATH, 'r', encoding='utf-8') as f:
                    runtime_data = json.load(f).get("music", {})
                audio_mode = runtime_data.get("audio_mode", "pcm")
                shuffle = runtime_data.get("shuffle", False)
            except Exception as e:
                logger.warning(f"[MusicConfig] 讀取 music_runtime.json 失敗: {e}")

        playlists = cls._parse_playlists(runtime_data)
        active_keys = cls._resolve_active(runtime_data, playlists)

        cls._config = MusicConfig(
            voice_channel_id=voice_channel_id,
            playlists=playlists,
            active_keys=active_keys,
            audio_mode=audio_mode if audio_mode in ('pcm', 'opus') else 'pcm',
            shuffle=bool(shuffle),
        )

        # 記錄兩個檔案的 mtime
        if os.path.exists(CONFIG_JSON_PATH):
            cls._last_mtime_config = os.path.getmtime(CONFIG_JSON_PATH)
        if os.path.exists(MUSIC_RUNTIME_PATH):
            cls._last_mtime_runtime = os.path.getmtime(MUSIC_RUNTIME_PATH)

        logger.info(
            f"🎵 [MusicConfig] 已載入配置 (voice: {voice_channel_id}, "
            f"歌單: {len(playlists)} 個, 啟用: {len(active_keys)} 個)"
        )
        return True

    @staticmethod
    def _parse_playlists(runtime_data: dict) -> list:
        """解析 `playlist_url`（可為單一字串或物件/字串陣列），回傳 list[Playlist]。

        相容三種寫法：
          "playlist_url": "https://...&list=..."                       # 單一字串
          "playlist_url": ["url1", "url2"]                              # 字串陣列
          "playlist_url": [{"name": "華語", "url": "..."}, {"url": ...}] # 物件陣列（name 可省略＝自動抓）
        另相容舊 key `default_playlist_url`（字串）。name 省略時保留 None，之後背景自動抓 YouTube 標題。
        """
        raw = runtime_data.get("playlist_url")
        if raw is None:
            raw = runtime_data.get("default_playlist_url")  # 舊 key 相容

        # 正規化成 [{"url", "name"?}, ...]
        items: list[dict] = []
        if isinstance(raw, str):
            if raw.strip():
                items.append({"url": raw})
        elif isinstance(raw, list):
            for entry in raw:
                if isinstance(entry, str) and entry.strip():
                    items.append({"url": entry})
                elif isinstance(entry, dict):
                    items.append(entry)

        playlists: list[Playlist] = []
        seen_keys: set[str] = set()
        for item in items:
            url = str(item.get("url", "")).strip()
            if not url:
                continue
            name = str(item.get("name", "")).strip() or None
            key = playlist_key(url)
            # key 去重複（極少見，例如兩個同 list id），加後綴維持唯一
            base, n = key, 1
            while key in seen_keys:
                n += 1
                key = f"{base}-{n}"
            seen_keys.add(key)
            playlists.append(Playlist(key=key, url=url, name=name))
        return playlists

    @staticmethod
    def _resolve_active(runtime_data: dict, playlists: list) -> list:
        """決定目前選取的歌單 key 清單；無效/空值一律退回「全部」。

        `active_playlists` 可為 "all"、key 陣列，或（為了好讀）名稱陣列，三者都接受。
        """
        valid_keys = {p.key for p in playlists}
        name_to_key = {p.name: p.key for p in playlists if p.name}
        raw = runtime_data.get("active_playlists", "all")
        if raw == "all" or raw is None:
            return [p.key for p in playlists]

        entries = raw if isinstance(raw, list) else [raw]
        selected: list[str] = []
        for e in entries:
            if e in valid_keys:
                selected.append(e)
            elif e in name_to_key:
                selected.append(name_to_key[e])
        return selected if selected else [p.key for p in playlists]

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
    def _get_watched_snapshot(cls) -> dict:
        """取得需要監控的欄位快照"""
        snapshot = {}
        try:
            if os.path.exists(CONFIG_JSON_PATH):
                with open(CONFIG_JSON_PATH, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                snapshot['voice_channel_id'] = data.get('music_voice_channel_id', 0)
            if os.path.exists(MUSIC_RUNTIME_PATH):
                with open(MUSIC_RUNTIME_PATH, 'r', encoding='utf-8') as f:
                    runtime_data = json.load(f).get('music', {})
                for key in cls._watched_keys:
                    snapshot[key] = runtime_data.get(key)
        except Exception:
            pass
        return snapshot

    @classmethod
    async def _watch_loop(cls):
        last_snapshot = cls._get_watched_snapshot()
        while True:
            try:
                current_snapshot = cls._get_watched_snapshot()
                if current_snapshot != last_snapshot:
                    logger.info(f"🔄 [MusicConfig] 偵測到配置變更 → 熱重載")
                    last_snapshot = current_snapshot
                    cls._load_config()
                    if cls._on_change_callback and cls._config:
                        try:
                            await cls._on_change_callback(cls._config)
                        except Exception as e:
                            logger.error(f"[MusicConfig] on_change callback 錯誤: {e}", exc_info=True)
            except Exception as e:
                logger.warning(f"[MusicConfig] watcher 錯誤: {e}")
            await asyncio.sleep(5)
