"""
日期時間工具函式
"""
from datetime import datetime
from typing import Optional


def parse_datetime(date_string: str) -> Optional[datetime]:
    """
    解析日期時間字串

    Args:
        date_string: 日期時間字串，格式: "YYYY-MM-DD HH:MM:SS"

    Returns:
        datetime 物件或 None
    """
    try:
        if not date_string:
            return None
        return datetime.strptime(date_string, "%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return None


def format_datetime(dt: datetime) -> str:
    """
    格式化 datetime 物件為字串

    Args:
        dt: datetime 物件

    Returns:
        格式化的日期時間字串
    """
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def current_timestamp() -> str:
    """
    取得當前時間戳記

    Returns:
        當前時間的格式化字串
    """
    return format_datetime(datetime.now())
