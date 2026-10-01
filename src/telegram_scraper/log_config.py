"""telegram-scraper 容器的 log 設定：console＋`/logs/telegram_scraper.log`。

**為什麼不用 bot 的 `settings/logging.json`**：這個容器只掛 `./src/telegram_scraper` 與 `./logs`，
看不到 `src/settings`、`src/utils`；要共用得改 compose 掛載並重建容器。格式與 bot 相同，
兩邊的 log 可以對著時間一起看。

**只由入口 `main.py` 呼叫**：bot 也會 import 本目錄的 `tg_config`，import 時改全域 logging
會把 bot 的設定洗掉。各模組一律 `logging.getLogger(__name__)`，不自己掛 handler。
"""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler

LOG_FILE_ENV = "TELEGRAM_SCRAPER_LOG_FILE"
DEFAULT_LOG_FILE = "/logs/telegram_scraper.log"
LOG_FORMAT = "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
MAX_BYTES = 10 * 1024 * 1024
BACKUP_COUNT = 5

#: 第三方套件的等級。Telethon 的 INFO 有斷線重連、FloodWait、補抓漏收更新，查漏訊息時用得到，
#: 保留；只有「每個檔案開始下載」這類逐檔訊息關掉。
LOGGER_LEVELS = {
    "telethon.client.downloads": logging.WARNING,
    "asyncpg": logging.WARNING,
}


def configure_logging(log_file: str | None = None) -> None:
    """把 root logger 設成 console＋輪替檔案；log 檔開不了時只留 console，不讓 scraper 起不來。"""
    path = log_file or os.getenv(LOG_FILE_ENV, DEFAULT_LOG_FILE)
    formatter = logging.Formatter(LOG_FORMAT, DATE_FORMAT)
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    file_error = None
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        handlers.append(
            RotatingFileHandler(path, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8")
        )
    except OSError as exc:
        file_error = exc

    for handler in handlers:
        handler.setFormatter(formatter)
    root = logging.getLogger()
    root.handlers[:] = handlers
    root.setLevel(logging.INFO)
    for name, level in LOGGER_LEVELS.items():
        logging.getLogger(name).setLevel(level)

    if file_error is not None:
        logging.getLogger(__name__).warning("無法寫入 log 檔 %s，只輸出到 console：%s", path, file_error)
