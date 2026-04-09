class MusicBotError(Exception):
    """音樂機器人基礎錯誤"""

class YTDLError(MusicBotError):
    """yt-dlp 相關錯誤"""

class QueueEmptyError(MusicBotError):
    """queue 為空"""
