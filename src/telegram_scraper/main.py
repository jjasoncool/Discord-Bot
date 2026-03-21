import asyncio
from runner import run_telegram_scraper
from tg_config import load_config_from_env


async def main() -> None:
    """Telegram Scraper 入口：讀取設定後交給 runner 執行。"""
    config = load_config_from_env()
    await run_telegram_scraper(config)


if __name__ == "__main__":
    asyncio.run(main())
