"""
主爬蟲程式
負責定時任務調度和程式入口
同時啟動 API 服務供 Discord Bot 使用
"""
import schedule
import time
import threading
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv
import uvicorn

from container import ServiceContainer
from services.fb_scraper_service import FBScraperService
from utils.logger import get_logger, log_startup_info

# 載入環境變數
load_dotenv()

# 建立 logger
logger = get_logger('main')


FB_EMPTY_URL_RETRY_DELAY_MINUTES = 15
fb_retry_scheduled_at = None
fb_task_running = False


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
    global fb_retry_scheduled_at, fb_task_running

    if fb_task_running:
        logger.warning("Facebook 爬蟲任務已在執行中，略過本次重複觸發")
        return

    fb_task_running = True
    try:
        logger.info("開始執行 Facebook 爬蟲任務")
        fb_service = FBScraperService()
        results = fb_service.scrape_facebook_posts()
        empty_link_failure = bool(getattr(fb_service, "last_empty_link_failure", False))

        if results:
            logger.info(f"Facebook 爬蟲任務完成，抓取到 {len(results)} 篇貼文")
            fb_retry_scheduled_at = None
        elif empty_link_failure:
            if fb_retry_scheduled_at is None:
                fb_retry_scheduled_at = datetime.now() + timedelta(minutes=FB_EMPTY_URL_RETRY_DELAY_MINUTES)
                logger.warning(
                    "Facebook 本輪為 0 URL，已排入 %s 分鐘後補抓：scheduled_at=%s",
                    FB_EMPTY_URL_RETRY_DELAY_MINUTES,
                    fb_retry_scheduled_at.isoformat(),
                )
            else:
                logger.warning(
                    "Facebook 本輪為 0 URL，但已有待執行補抓，不重複排入：scheduled_at=%s",
                    fb_retry_scheduled_at.isoformat(),
                )
        else:
            logger.warning("Facebook 爬蟲任務完成，但未抓取到貼文")

    except Exception as e:
        logger.error(f"Facebook 爬蟲任務發生未預期錯誤: {str(e)}", exc_info=True)
    finally:
        fb_task_running = False


def run_pending_fb_retry_if_needed():
    """若先前 FB 首頁 0 URL，於指定時間補抓一次；僅由單一主迴圈呼叫。"""
    global fb_retry_scheduled_at, fb_task_running

    if fb_retry_scheduled_at is None:
        return
    if fb_task_running:
        return

    now = datetime.now()
    if now < fb_retry_scheduled_at:
        return

    scheduled_at = fb_retry_scheduled_at
    fb_retry_scheduled_at = None
    logger.info(
        "開始執行 Facebook 0 URL 延後補抓任務：scheduled_at=%s now=%s",
        scheduled_at.isoformat(),
        now.isoformat(),
    )
    fb_scrape_task()


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


DISCORD_BOT_NOTIFY_URL = "http://discord-bot:5000"


def _notify_discord_bot(source: str, payload: dict = None):
    """通知 Discord Bot 有新資料可處理。失敗只 log，不阻斷排程。"""
    try:
        url = f"{DISCORD_BOT_NOTIFY_URL}/notify/{source}"
        resp = requests.post(url, json=payload or {}, timeout=10)
        logger.info("已通知 Discord Bot: %s status=%s", url, resp.status_code)
    except Exception as e:
        logger.warning("通知 Discord Bot 失敗（不影響排程）: %s", e)


def bahamut_scrape_task():
    """Bahamut 爬蟲任務：抓取 → 寫入 DB → 輸出 sample JSON"""
    container = ServiceContainer()
    try:
        logger.info("開始執行 Bahamut 爬蟲任務")

        # 確保資料表存在
        container.create_database_tables()

        bahamut_service = container.create_bahamut_scraper_service()
        result = bahamut_service.fetch_bahamut_articles_with_content()

        if result.get("ok"):
            # 寫入資料庫
            saved_count = bahamut_service.save_articles_to_db(result.get("articles", []))
            bahamut_service.db_manager.commit()

            # 依設定決定是否輸出 sample JSON
            from config import BAHAMUT_CONFIG
            output_path = None
            if BAHAMUT_CONFIG.get("export_sample_json", False):
                output_path = bahamut_service.export_sample_json(result)

            logger.info(
                "Bahamut 爬蟲任務完成: article_count=%s, detailed_count=%s, saved_count=%s, output=%s",
                result.get("article_count", 0),
                result.get("detailed_count", 0),
                saved_count,
                output_path,
            )

            # 通知 Discord Bot 有新資料
            _notify_discord_bot("bahamut", {"board_id": "74934", "count": saved_count})
        else:
            logger.warning(
                "Bahamut 爬蟲任務未完成: error=%s gate=%s",
                result.get("error"),
                result.get("gate", {}),
            )

    except Exception as e:
        logger.error(f"Bahamut 爬蟲任務發生未預期錯誤: {str(e)}", exc_info=True)
    finally:
        if 'bahamut_service' in locals() and getattr(bahamut_service, 'db_manager', None):
            bahamut_service.db_manager.close()


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
    schedule.every(1).hours.do(bahamut_scrape_task)

    # 立即執行一次 Facebook 爬蟲
    logger.info("執行初始 Facebook 爬蟲任務")
    fb_scrape_task()

    # 立即執行一次主要爬蟲
    logger.info("執行初始爬蟲任務")
    main_scrape_task()

    # 立即執行一次 PTT 爬蟲
    logger.info("執行初始 PTT 爬蟲任務")
    ptt_scrape_task()

    # 立即執行一次 Bahamut 爬蟲
    logger.info("執行初始 Bahamut 爬蟲任務")
    bahamut_scrape_task()

    # 啟動定時任務循環
    logger.info("定時任務已啟動：每15分鐘執行文章爬蟲，每1小時執行 Facebook/PTT/Bahamut 爬蟲")
    while True:
        try:
            schedule.run_pending()
            run_pending_fb_retry_if_needed()
            time.sleep(60)  # 每分鐘檢查一次
        except KeyboardInterrupt:
            logger.info("程式被用戶中斷")
            break
        except Exception as e:
            logger.error(f"定時任務循環發生錯誤: {str(e)}", exc_info=True)
            time.sleep(60)


if __name__ == "__main__":
    main()
