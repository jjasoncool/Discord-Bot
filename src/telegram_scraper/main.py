import asyncio
import logging
import signal
import sys
from typing import Awaitable

from log_config import configure_logging
from runner import run_telegram_scraper
from tg_config import load_config_from_env

logger = logging.getLogger(__name__)


async def run_until_stopped(job: Awaitable[None]) -> None:
    """跑 `job` 直到它做完，或收到 SIGTERM／SIGINT 就取消它，讓收尾（Telethon 斷線、關 DB）跑完。

    容器裡 python 是 PID 1：沒有 handler 的訊號核心會直接丟掉，Docker 送 SIGTERM 等不到結束就 SIGKILL，
    `run_telegram_scraper` 的 finally 一行都沒跑。兩個訊號都接成「取消主要工作」，走正常的 CancelledError 路徑；
    不是訊號造成的取消照樣往外丟。
    """
    loop = asyncio.get_running_loop()
    task = asyncio.ensure_future(job)
    received: list[str] = []

    def request_stop(name: str) -> None:
        if not received:
            logger.info("收到 %s，開始停止", name)
        received.append(name)
        task.cancel()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, request_stop, sig.name)
    try:
        await task
    except asyncio.CancelledError:
        if not received:
            raise
        logger.info("Telegram scraper 已停止")
    finally:
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.remove_signal_handler(sig)


async def main() -> None:
    """Telegram Scraper 入口：讀取設定後交給 runner 執行。"""
    config = load_config_from_env()
    await run_until_stopped(run_telegram_scraper(config))


if __name__ == "__main__":
    configure_logging()
    try:
        asyncio.run(main())
    except Exception:
        # 容器會自動重啟、docker logs 重建容器就沒了；崩潰原因要留在 log 檔
        logger.exception("Telegram scraper 異常結束")
        sys.exit(1)
