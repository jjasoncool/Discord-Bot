"""統一的日誌配置：所有 log 的去向都寫在 `settings/logging.json`（Python 標準 dictConfig 格式）。

- 一般模組一律 `logger = logging.getLogger(__name__)`：名稱就是模組路徑（例：`llm.ambient_reply`），
  設定檔可以依前綴分類——要把某一類拆到獨立檔、調等級、靜音，改 json 重啟即可，不動程式碼。
- 刻意獨立的「類別」logger（`article_monitor`、`llm_anomaly`）也定義在設定檔裡。
- 測試模式（`test/__init__.py` 設 `APP_TEST_LOG_FILE`）：所有檔案 handler 改寫到同一個測試 log，
  不把假紀錄混進正式 log。
- import 本模組就會套用設定（重複呼叫不會重複加 handler），任何入口都不會漏掉。
"""
import copy
import json
import logging
import logging.config
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

LOG_DIR = "/logs"
CONFIG_PATH = Path(__file__).resolve().parent.parent / "settings" / "logging.json"

#: 測試執行時（由 `test/__init__.py` 設定）所有 log 檔改寫到這一個檔，不把假紀錄混進正式 log
TEST_LOG_ENV = "APP_TEST_LOG_FILE"

#: 刻意獨立的類別 logger（去向定義在 settings/logging.json）
ARTICLE_MONITOR_LOGGER = "article_monitor"
LLM_ANOMALY_LOGGER = "llm_anomaly"

_configured = False


def redirected_log_name():
    """測試模式下要改寫到的檔名；正式執行回 None。"""
    return os.getenv(TEST_LOG_ENV) or None


def build_config(raw: dict, *, log_dir: str = LOG_DIR, test_log_name=None, level=None) -> dict:
    """把設定檔內容轉成可直接交給 dictConfig 的 dict（不碰全域狀態，方便測試）。"""
    config = copy.deepcopy(raw)
    for handler in config.get("handlers", {}).values():
        if "filename" in handler:
            handler["filename"] = os.path.join(log_dir, test_log_name or handler["filename"])
    if level:
        config.setdefault("root", {})["level"] = level
    return config


def configure_logging(force: bool = False) -> None:
    """套用 settings/logging.json；環境變數 LOG_LEVEL 可覆寫 root 等級。"""
    global _configured
    if _configured and not force:
        return
    raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    level = os.getenv("LOG_LEVEL", "").upper() or None
    logging.config.dictConfig(build_config(raw, test_log_name=redirected_log_name(), level=level))
    _configured = True


def get_article_monitor_logger() -> logging.Logger:
    """文章／爬蟲監控類別 logger（獨立寫 article_monitor.log，也輸出到畫面）。"""
    return logging.getLogger(ARTICLE_MONITOR_LOGGER)


def get_llm_anomaly_logger() -> logging.Logger:
    """LLM 異常回應的完整 raw dump（獨立寫 llm_anomaly.log，不輸出到畫面、不混進主 log）。"""
    return logging.getLogger(LLM_ANOMALY_LOGGER)


configure_logging()
