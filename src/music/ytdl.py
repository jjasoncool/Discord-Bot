import os
import re
import glob
import logging
import yt_dlp
import asyncio
from .exceptions import YTDLError
from .models import Song

logger = logging.getLogger('discord_bot')

CACHE_DIR = os.path.join(os.path.dirname(__file__), 'cache')


class YTDLSource:
    # 同時只允許 1 個下載任務，避免多個 yt-dlp 同時搶頻寬/CPU
    _download_semaphore = asyncio.Semaphore(1)

    YTDL_OPTIONS = {
        'format': '251/bestaudio/best',
        'noplaylist': False,
        'quiet': True,
        'no_warnings': True,
        'ignoreerrors': True,
        'extractor_args': {'youtube': {'player_client': ['android', 'web']}},
        'sleep_interval': 2,
        'max_sleep_interval': 5,
    }

    # 單首歌播放時用（優先 opus，避免即時轉碼 AAC 的 CPU 開銷）
    SINGLE_OPTIONS = {
        'format': '251/bestaudio/best',
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
        'extractor_args': {'youtube': {'player_client': ['android', 'web']}},
    }

    # 下載到本地快取用（統一轉為 opus，限速避免搶頻寬）
    DOWNLOAD_OPTIONS = {
        'format': '251/bestaudio/best',
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
        'extractor_args': {'youtube': {'player_client': ['android', 'web']}},
        'outtmpl': os.path.join(CACHE_DIR, '%(id)s.%(ext)s'),
        'ratelimit': 3145728,  # 限速 3MB/s，保留頻寬給串流播放
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'opus',
            'preferredquality': '0',  # 0 = 來源是 opus 時 codec copy，非 opus 時用最高品質轉檔
        }],
    }

    SEARCH_OPTIONS = {
        'format': '251/bestaudio/best',
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
        'default_search': 'ytsearch',
        'extractor_args': {'youtube': {'player_client': ['android', 'web']}},
    }

    @staticmethod
    def _is_url(query: str) -> bool:
        return query.startswith(('http://', 'https://'))

    @staticmethod
    def _extract_video_id(url: str) -> str | None:
        """從 YouTube URL 提取 video ID"""
        patterns = [
            r'(?:v=|/v/|youtu\.be/)([a-zA-Z0-9_-]{11})',
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None

    @staticmethod
    def get_cache_path(video_id: str) -> str | None:
        """檢查快取是否存在，回傳檔案路徑（支援任何副檔名）"""
        matches = glob.glob(os.path.join(CACHE_DIR, f"{video_id}.*"))
        for path in matches:
            if os.path.getsize(path) > 0:
                return path
        return None

    @staticmethod
    async def download_to_cache(url: str):
        """背景下載音訊到本地快取，Semaphore 確保同時只有一個下載"""
        video_id = YTDLSource._extract_video_id(url)
        if not video_id:
            return
        if YTDLSource.get_cache_path(video_id):
            return

        os.makedirs(CACHE_DIR, exist_ok=True)
        loop = asyncio.get_event_loop()

        async with YTDLSource._download_semaphore:
            # 等待期間可能已被其他任務下載完
            if YTDLSource.get_cache_path(video_id):
                return
            try:
                def _download():
                    with yt_dlp.YoutubeDL(YTDLSource.DOWNLOAD_OPTIONS) as ydl:
                        ydl.download([url])
                await loop.run_in_executor(None, _download)
                logger.info(f"[MusicCache] 已快取: {video_id}")
            except Exception as e:
                logger.warning(f"[MusicCache] 下載快取失敗 {video_id}: {e}")

    @staticmethod
    async def extract_info(url: str) -> list[dict]:
        """提取 URL 的音訊資訊（支援歌單，一次性回傳）"""
        loop = asyncio.get_event_loop()
        try:
            def _extract():
                with yt_dlp.YoutubeDL(YTDLSource.YTDL_OPTIONS) as ydl:
                    return ydl.extract_info(url, download=False)
            info = await loop.run_in_executor(None, _extract)
            if 'entries' in info:
                return [e for e in info['entries'] if e]
            return [info]
        except Exception as e:
            raise YTDLError(f"yt-dlp 提取失敗: {e}") from e

    @staticmethod
    def _extract_playlist_sync(url: str):
        """同步提取歌單，使用 lazy extraction 逐首產出。回傳 (playlist_title, entries)。"""
        ydl_opts = YTDLSource.YTDL_OPTIONS.copy()
        ydl_opts['extract_flat'] = 'in_playlist'
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                return (None, [])
            title = info.get('title')
            if 'entries' not in info:
                return (title, [info])
            return (title, [e for e in info['entries'] if e])

    @staticmethod
    async def extract_playlist_title(url: str) -> str | None:
        """只抓歌單標題（playlistend=1，不展開整份歌單，快速），供自動命名用"""
        loop = asyncio.get_event_loop()

        def _extract():
            opts = YTDLSource.YTDL_OPTIONS.copy()
            opts['extract_flat'] = 'in_playlist'
            opts['playlistend'] = 1  # 只需第一筆即可拿到歌單標題
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
                return info.get('title') if info else None

        try:
            return await loop.run_in_executor(None, _extract)
        except Exception as e:
            logger.warning(f"[YTDLSource] 抓取歌單標題失敗: {e}")
            return None

    @staticmethod
    async def extract_single(url: str) -> dict:
        """取得單首歌的串流資訊（不展開歌單）"""
        loop = asyncio.get_event_loop()
        try:
            def _extract():
                with yt_dlp.YoutubeDL(YTDLSource.SINGLE_OPTIONS) as ydl:
                    return ydl.extract_info(url, download=False)
            info = await loop.run_in_executor(None, _extract)
            if 'entries' in info:
                entries = [e for e in info['entries'] if e]
                if entries:
                    return entries[0]
            return info
        except Exception as e:
            raise YTDLError(f"yt-dlp 單曲提取失敗: {e}") from e

    @staticmethod
    async def search(query: str) -> Song:
        """關鍵字搜尋，回傳第一筆結果"""
        loop = asyncio.get_event_loop()
        try:
            def _search():
                with yt_dlp.YoutubeDL(YTDLSource.SEARCH_OPTIONS) as ydl:
                    return ydl.extract_info(query, download=False)
            info = await loop.run_in_executor(None, _search)
            if 'entries' in info:
                entries = [e for e in info['entries'] if e]
                if not entries:
                    raise YTDLError(f"找不到結果：{query}")
                return Song.from_info(entries[0])
            return Song.from_info(info)
        except YTDLError:
            raise
        except Exception as e:
            raise YTDLError(f"搜尋失敗: {e}") from e

    @staticmethod
    async def create_song(query: str) -> Song:
        """統一入口：URL 走 extract_single（只取一首），關鍵字走 search"""
        if YTDLSource._is_url(query):
            info = await YTDLSource.extract_single(query)
            return Song.from_info(info)
        return await YTDLSource.search(query)
