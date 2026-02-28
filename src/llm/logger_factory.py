"""LLM/askai 專用 logger factory。"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from pathlib import Path
from typing import Literal

def get_or_create_file_logger(
    *,
    name: str,
    log_path: Path,
    mode: Literal["size", "time"],
    level: int = logging.INFO,
    max_bytes: int = 0,
    backup_count: int = 0,
    when: str = "midnight",
    interval: int = 1,
) -> logging.Logger:
    """依 rotation 模式建立/回傳 file logger（避免重複 handler）。"""
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = False

    if not logger.handlers:
        if mode == "time":
            file_handler = TimedRotatingFileHandler(
                log_path,
                when=when,
                interval=interval,
                backupCount=backup_count,
                encoding="utf-8",
            )
        else:
            file_handler = RotatingFileHandler(
                log_path,
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding="utf-8",
            )

        file_handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(file_handler)

    return logger
