"""
日誌工具模組
提供統一的日誌記錄功能
"""
import os
import sys
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
from typing import Optional


class MaxLevelFilter(logging.Filter):
    """僅允許小於等於指定等級的 log 通過。"""

    def __init__(self, max_level: int):
        super().__init__()
        self.max_level = max_level

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno <= self.max_level


class LoggerConfig:
    """日誌配置類別"""

    def __init__(self):
        self.log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
        self.log_file = os.getenv('LOG_FILE', '/logs/scraper.log')
        self.info_log_file = os.getenv('LOG_INFO_FILE', '/logs/scraper_info.log')
        self.error_log_file = os.getenv('LOG_ERROR_FILE', '/logs/scraper_error.log')
        self.log_max_bytes = int(os.getenv('LOG_MAX_BYTES', str(10 * 1024 * 1024)))  # 10MB
        self.log_backup_count = int(os.getenv('LOG_BACKUP_COUNT', '5'))
        self.log_format = '[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s'
        self.log_date_format = '%Y-%m-%d %H:%M:%S'


def setup_logger(name: str, config: Optional[LoggerConfig] = None) -> logging.Logger:
    """
    設定日誌記錄器

    Args:
        name: logger 名稱
        config: 日誌配置，如果為 None 則使用預設配置

    Returns:
        配置好的 logger 實例
    """
    if config is None:
        config = LoggerConfig()

    # 取得或建立 logger
    logger = logging.getLogger(name)

    # 避免重複設定
    if logger.handlers:
        return logger

    # 設定日誌級別（支援個別 logger 覆蓋，優先順序：config.py LOGGER_LEVELS > 預設 LOG_LEVEL）
    log_level = None
    try:
        from config import LOGGER_LEVELS
        override = LOGGER_LEVELS.get(name, "").upper()
        if override:
            log_level = getattr(logging, override, None)
    except ImportError:
        pass
    if log_level is None:
        log_level = getattr(logging, config.log_level, logging.INFO)
    logger.setLevel(log_level)

    # 建立格式器
    formatter = logging.Formatter(config.log_format, config.log_date_format)

    # 控制台處理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 檔案處理器（帶輪替）
    try:
        log_files = {config.log_file, config.info_log_file, config.error_log_file}
        for log_file in log_files:
            log_dir = os.path.dirname(log_file)
            if log_dir and not os.path.exists(log_dir):
                os.makedirs(log_dir, exist_ok=True)

        # 完整檔：保留所有符合 LOG_LEVEL 的訊息
        file_handler = RotatingFileHandler(
            config.log_file,
            maxBytes=config.log_max_bytes,
            backupCount=config.log_backup_count,
            encoding='utf-8'
        )
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        # info/debug 檔：只保留 INFO 以下（含 DEBUG、INFO）
        info_file_handler = RotatingFileHandler(
            config.info_log_file,
            maxBytes=config.log_max_bytes,
            backupCount=config.log_backup_count,
            encoding='utf-8'
        )
        info_file_handler.setLevel(logging.DEBUG)
        info_file_handler.addFilter(MaxLevelFilter(logging.INFO))
        info_file_handler.setFormatter(formatter)
        logger.addHandler(info_file_handler)

        # warning/error 檔：保留 WARNING 以上
        error_file_handler = RotatingFileHandler(
            config.error_log_file,
            maxBytes=config.log_max_bytes,
            backupCount=config.log_backup_count,
            encoding='utf-8'
        )
        error_file_handler.setLevel(logging.WARNING)
        error_file_handler.setFormatter(formatter)
        logger.addHandler(error_file_handler)

    except Exception as e:
        # 如果無法建立檔案處理器，至少要有控制台輸出
        logger.warning(f"無法建立日誌檔案處理器: {str(e)}")

    return logger


def get_logger(name: str = 'scraper') -> logging.Logger:
    """
    取得日誌記錄器的便利函數

    Args:
        name: logger 名稱，預設為 'scraper'

    Returns:
        logger 實例
    """
    return setup_logger(name)


# 建立預設的 scraper logger
scraper_logger = get_logger('scraper')


class LoggerMixin:
    """
    日誌混入類別
    為其他類別提供日誌記錄功能
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.logger = get_logger(self.__class__.__name__)

    def log_info(self, message: str):
        """記錄資訊日誌"""
        self.logger.info(message)

    def log_warning(self, message: str):
        """記錄警告日誌"""
        self.logger.warning(message)

    def log_error(self, message: str, exc_info: bool = False):
        """記錄錯誤日誌"""
        self.logger.error(message, exc_info=exc_info)

    def log_debug(self, message: str):
        """記錄除錯日誌"""
        self.logger.debug(message)


def log_function_call(func):
    """
    裝飾器：記錄函數呼叫
    """
    def wrapper(*args, **kwargs):
        logger = get_logger('function_call')
        logger.debug(f"呼叫函數: {func.__name__}")
        try:
            result = func(*args, **kwargs)
            logger.debug(f"函數 {func.__name__} 執行成功")
            return result
        except Exception as e:
            logger.error(f"函數 {func.__name__} 執行失敗: {str(e)}", exc_info=True)
            raise
    return wrapper


def log_startup_info():
    """記錄啟動資訊"""
    logger = get_logger('startup')
    logger.info(f"爬蟲程式啟動於 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"Python 版本: {sys.version}")
    logger.info(f"工作目錄: {os.getcwd()}")
    logger.info(f"日誌級別: {os.getenv('LOG_LEVEL', 'INFO')}")
    logger.info(f"日誌檔案: {os.getenv('LOG_FILE', '/logs/scraper.log')}")
    logger.info(f"資訊日誌檔案: {os.getenv('LOG_INFO_FILE', '/logs/scraper_info.log')}")
    logger.info(f"警告錯誤日誌檔案: {os.getenv('LOG_ERROR_FILE', '/logs/scraper_error.log')}")


if __name__ == "__main__":
    # 測試日誌功能
    test_logger = get_logger('test')
    test_logger.info("這是一條測試訊息")
    test_logger.warning("這是一條警告訊息")
    test_logger.error("這是一條錯誤訊息")
