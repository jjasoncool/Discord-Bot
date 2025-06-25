"""
主爬蟲程式
負責定時任務調度和程式入口
"""
import schedule
import time
from datetime import datetime
from dotenv import load_dotenv

from container import ServiceContainer
from utils.logger import get_logger, log_startup_info

# 載入環境變數
load_dotenv()

# 建立 logger
logger = get_logger('main')


def main_scrape_task():
    """主要爬蟲任務"""
    container = ServiceContainer()

    try:
        # 建立資料庫表格
        container.create_database_tables()

        # 建立爬蟲服務並執行
        scraper_service = container.create_scraper_service()
        success = scraper_service.scrape_articles()

        if success:
            logger.info("爬蟲任務執行成功")
        else:
            logger.warning("爬蟲任務執行失敗")

    except Exception as e:
        logger.error(f"爬蟲任務發生未預期錯誤: {str(e)}", exc_info=True)
    finally:
        # 確保資源清理
        if 'scraper_service' in locals():
            scraper_service.db_manager.close()


def main():
    """主程式入口"""
    # 記錄啟動資訊
    log_startup_info()

    # 載入環境變數
    load_dotenv()

    # 設定定時任務
    schedule.every(15).minutes.do(main_scrape_task)

    # 立即執行一次
    logger.info("執行初始爬蟲任務")
    main_scrape_task()

    # 啟動定時任務循環
    logger.info("定時任務已啟動，每小時執行一次")
    while True:
        try:
            schedule.run_pending()
            time.sleep(60)  # 每分鐘檢查一次
        except KeyboardInterrupt:
            logger.info("程式被用戶中斷")
            break
        except Exception as e:
            logger.error(f"定時任務循環發生錯誤: {str(e)}", exc_info=True)
            time.sleep(60)


if __name__ == "__main__":
    main()
