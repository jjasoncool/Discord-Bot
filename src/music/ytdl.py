import yt_dlp
import asyncio
from .exceptions import YTDLError
from .models import Song

class YTDLSource:
    YTDL_OPTIONS = {
        'format': 'bestaudio/best',
        'noplaylist': False,           # 允許歌單
        'quiet': True,
        'no_warnings': True,
        'ignoreerrors': True,          # 跳過無法播放的影片（版權、地區限制等）
        'extractor_args': {'youtube': {'player_client': ['android', 'web']}},
        'sleep_interval': 2,           # 防 rate-limit
        'max_sleep_interval': 5,
    }

    # 單首歌播放時用（不展開歌單）
    SINGLE_OPTIONS = {
        'format': 'bestaudio/best',
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
        'extractor_args': {'youtube': {'player_client': ['android', 'web']}},
    }

    SEARCH_OPTIONS = {
        'format': 'bestaudio/best',
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
        'default_search': 'ytsearch',  # 非 URL 時自動 YouTube 搜尋
        'extractor_args': {'youtube': {'player_client': ['android', 'web']}},
    }

    @staticmethod
    def _is_url(query: str) -> bool:
        return query.startswith(('http://', 'https://'))

    @staticmethod
    async def extract_info(url: str) -> list[dict]:
        """提取 URL 的音訊資訊（支援歌單）"""
        loop = asyncio.get_event_loop()
        try:
            info = await loop.run_in_executor(
                None,
                lambda: yt_dlp.YoutubeDL(YTDLSource.YTDL_OPTIONS).extract_info(url, download=False)
            )
            if 'entries' in info:
                return [e for e in info['entries'] if e]
            return [info]
        except Exception as e:
            raise YTDLError(f"yt-dlp 提取失敗: {e}") from e

    @staticmethod
    async def extract_single(url: str) -> dict:
        """取得單首歌的串流資訊（不展開歌單，用於播放時重新取得新鮮 URL）"""
        loop = asyncio.get_event_loop()
        try:
            info = await loop.run_in_executor(
                None,
                lambda: yt_dlp.YoutubeDL(YTDLSource.SINGLE_OPTIONS).extract_info(url, download=False)
            )
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
            info = await loop.run_in_executor(
                None,
                lambda: yt_dlp.YoutubeDL(YTDLSource.SEARCH_OPTIONS).extract_info(query, download=False)
            )
            # ytsearch 回傳 entries
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
