import asyncio
import logging
import sys

from log_config import configure_logging
from runner import run_telegram_scraper
from tg_config import load_config_from_env

logger = logging.getLogger(__name__)


async def main() -> None:
    """Telegram Scraper 入口：讀取設定後交給 runner 執行。"""
    config = load_config_from_env()
    await run_telegram_scraper(config)


if __name__ == "__main__":
    configure_logging()
    try:
        asyncio.run(main())
    except Exception:
        # 容器會自動重啟、docker logs 重建容器就沒了；崩潰原因要留在 log 檔
        logger.exception("Telegram scraper 異常結束")
        sys.exit(1)
