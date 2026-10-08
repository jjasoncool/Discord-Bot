"""手動同步搜尋索引：`python -m services.search`（第一次建索引、或想立刻跟上 scraper 時用）。

搜尋時本來就會自動做增量同步；第一次建索引要掃十幾萬列，先手動跑一次，MCP 第一次搜尋才不會等很久。
"""
import logging
import time

from services.search import default_index
from utils.logger_config import configure_logging

logger = logging.getLogger(__name__)

if __name__ == "__main__":
    # 從 docker exec 手動執行：只印到畫面，不寫 bot 的輪替 log（兩個行程寫同一個檔會互相蓋掉）
    configure_logging(force=True, root_handlers=["console"])
    started = time.monotonic()
    report = default_index().sync(force=True)
    logger.info("搜尋索引同步完成：新增 %d、更新 %d、移除 %d%s，花了 %.1f 秒", report.added, report.updated,
                report.removed, "、整份重建" if report.rebuilt else "", time.monotonic() - started)
