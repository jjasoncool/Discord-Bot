"""
主爬蟲程式
負責定時任務調度和程式入口
同時啟動 API 服務供 Discord Bot 使用
"""
import schedule
import time
import threading
from datetime import datetime
from dotenv import load_dotenv
import uvicorn

from container import ServiceContainer
from services.fb_scraper_service import FBScraperService
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


def fb_scrape_task():
    """Facebook 爬蟲任務"""
    try:
        logger.info("開始執行 Facebook 爬蟲任務")
        fb_service = FBScraperService()
        results = fb_service.scrape_facebook_posts()

        if results:
            logger.info(f"Facebook 爬蟲任務完成，抓取到 {len(results)} 篇貼文")
        else:
            logger.warning("Facebook 爬蟲任務完成，但未抓取到貼文")

    except Exception as e:
        logger.error(f"Facebook 爬蟲任務發生未預期錯誤: {str(e)}", exc_info=True)


def ptt_scrape_task():
    """PTT 爬蟲任務（抓搜尋第一頁文章列表）"""
    container = ServiceContainer()
    try:
        logger.info("開始執行 PTT 爬蟲任務")

        # 保險建立資料表
        container.create_database_tables()

        ptt_service = container.create_ptt_scraper_service()
        result = ptt_service.fetch_ptt_articles_with_content()

        saved_count = ptt_service.save_articles_to_db(result.get("articles", []))
        ptt_service.db_manager.commit()

        if result.get("ok"):
            logger.info(
                "PTT 爬蟲任務完成: status=%s, article_count=%s, detailed_count=%s, saved_count=%s, title=%s",
                result.get("status_code"),
                result.get("article_count"),
                result.get("detailed_count", 0),
                saved_count,
                result.get("title"),
            )
        else:
            logger.warning("PTT 爬蟲任務完成，但頁面驗證未通過")

    except Exception as e:
        logger.error(f"PTT 爬蟲任務發生未預期錯誤: {str(e)}", exc_info=True)
    finally:
        if 'ptt_service' in locals() and getattr(ptt_service, 'db_manager', None):
            ptt_service.db_manager.close()


def start_api_server():
    """啟動 API 服務器"""
    from api_server import app
    logger.info("啟動 API 服務器於 port 8000")
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )


def main():
    """主程式入口"""
    # 記錄啟動資訊
    log_startup_info()

    # 載入環境變數
    load_dotenv()

    # 在背景執行緒中啟動 API 服務器
    api_thread = threading.Thread(target=start_api_server, daemon=True)
    api_thread.start()
    logger.info("API 服務器已在背景啟動")

    # 設定定時任務
    schedule.every(15).minutes.do(main_scrape_task)
    schedule.every(1).hours.do(fb_scrape_task)
    schedule.every(1).hours.do(ptt_scrape_task)

    # 立即執行一次 Facebook 爬蟲
    logger.info("執行初始 Facebook 爬蟲任務")
    fb_scrape_task()

    # 立即執行一次主要爬蟲
    logger.info("執行初始爬蟲任務")
    main_scrape_task()

    # 立即執行一次 PTT 爬蟲
    logger.info("執行初始 PTT 爬蟲任務")
    ptt_scrape_task()

    # 啟動定時任務循環
    logger.info("定時任務已啟動：每15分鐘執行文章爬蟲，每1小時執行 Facebook 爬蟲，每1小時執行 PTT 爬蟲")
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
