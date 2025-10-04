"""
統一的日誌配置模組
提供集中化的日誌器配置和管理
"""
import os
import logging
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv

# 載入環境變數
load_dotenv()
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO').upper()

# 全域日誌配置
LOG_DIR = '/logs'
DEFAULT_MAX_BYTES = 20 * 1024 * 1024  # 20MB
DEFAULT_BACKUP_COUNT = 20

# 解析日誌級別
def get_log_level():
    """取得日誌級別"""
    return getattr(logging, LOG_LEVEL, logging.INFO)

def create_console_handler(log_level=None):
    """創建控制台處理器"""
    if log_level is None:
        log_level = get_log_level()

    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_format = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s', '%Y-%m-%d %H:%M:%S')
    console_handler.setFormatter(console_format)
    return console_handler

def create_file_handler(filename, log_level=None, max_bytes=None, backup_count=None):
    """創建文件處理器"""
    if log_level is None:
        log_level = get_log_level()
    if max_bytes is None:
        max_bytes = DEFAULT_MAX_BYTES
    if backup_count is None:
        backup_count = DEFAULT_BACKUP_COUNT

    filepath = os.path.join(LOG_DIR, filename)
    file_handler = RotatingFileHandler(
        filepath,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding='utf-8'
    )
    file_handler.setLevel(log_level)
    file_format = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s', '%Y-%m-%d %H:%M:%S')
    file_handler.setFormatter(file_format)
    return file_handler

def setup_logger(name, filename, include_console=True, log_level=None, max_bytes=None, backup_count=None):
    """
    設定日誌器

    Args:
        name: 日誌器名稱
        filename: 日誌檔案名稱
        include_console: 是否包含控制台輸出
        log_level: 日誌級別
        max_bytes: 檔案最大大小
        backup_count: 備份檔案數量

    Returns:
        配置好的日誌器實例
    """
    logger = logging.getLogger(name)

    # 如果已經有處理器，跳過設定
    if logger.handlers:
        return logger

    if log_level is None:
        log_level = get_log_level()

    logger.setLevel(log_level)

    # 添加文件處理器
    file_handler = create_file_handler(filename, log_level, max_bytes, backup_count)
    logger.addHandler(file_handler)

    # 添加控制台處理器（可選）
    if include_console:
        console_handler = create_console_handler(log_level)
        logger.addHandler(console_handler)

    return logger

# 預定義的日誌器實例
def get_discord_bot_logger():
    """取得 Discord Bot 主日誌器"""
    return setup_logger(
        'discord_bot',
        'discord_bot.log',
        include_console=True,
        max_bytes=20*1024*1024,  # 20MB
        backup_count=50
    )

def get_article_monitor_logger():
    """取得文章監控日誌器"""
    return setup_logger(
        'article_monitor',
        'article_monitor.log',
        include_console=True,
        max_bytes=20*1024*1024,  # 20MB
        backup_count=20
    )

def get_scraper_logger():
    """取得爬蟲日誌器"""
    return setup_logger(
        'scraper',
        'scraper.log',
        include_console=True
    )

def get_api_logger():
    """取得 API 日誌器"""
    return setup_logger(
        'api',
        'api.log',
        include_console=True
    )

# 初始化主要日誌器
discord_bot_logger = get_discord_bot_logger()
article_monitor_logger = get_article_monitor_logger()
