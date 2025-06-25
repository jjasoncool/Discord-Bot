"""
爬蟲服務模組
核心業務邏輯處理
"""
from datetime import datetime
from typing import List, Optional
from utils.logger import get_logger

from config import API_URLS, OUTPUT_FILES, FEATURES
from db.database import DatabaseManager
from services.api_service import APIService
from services.file_service import FileService
from utils.datetime_utils import parse_datetime


class ScraperService:
    """爬蟲服務類別"""

    def __init__(self, db_manager: DatabaseManager, api_service: APIService, file_service: FileService):
        self.db_manager = db_manager
        self.api_service = api_service
        self.file_service = file_service
        self.logger = get_logger('scraper_service')

    def scrape_articles(self) -> bool:
        """
        執行完整的文章抓取流程

        Returns:
            執行是否成功
        """
        try:
            self.logger.info(f"[{datetime.now()}] 開始抓取文章資料...")

            # 1. 取得最後抓取時間
            last_scrape_time = self.db_manager.get_last_scrape_time()
            self.logger.info(f"[{datetime.now()}] 最後抓取時間: {last_scrape_time}")

            # 2. 抓取文章選單
            article_menus = self._scrape_article_menus(last_scrape_time)
            if not article_menus:
                self.logger.info(f"[{datetime.now()}] 沒有新文章需要處理")
                return True

            self.logger.info(f"[{datetime.now()}] 找到 {len(article_menus)} 篇新文章")

            # 3. 抓取文章詳細內容
            success_count = self._scrape_article_details(article_menus)

            # 4. 更新最後抓取時間
            if article_menus:
                latest_time = self._get_latest_create_time(article_menus)
                if latest_time:
                    self.db_manager.update_last_scrape_time(latest_time)
                    self.logger.info(f"[{datetime.now()}] 更新最後抓取時間: {latest_time}")

            self.logger.info(f"[{datetime.now()}] 文章抓取完成，成功處理 {success_count} 篇詳細內容")
            return True

        except Exception as e:
            self.logger.error(f"[{datetime.now()}] 爬蟲服務執行失敗: {str(e)}")
            return False

    def _scrape_article_menus(self, last_scrape_time: Optional[datetime]) -> List:
        """抓取文章選單"""
        # 抓取 API1 資料
        api1_data = self.api_service.fetch_data(API_URLS["api1"])
        if not api1_data:
            self.logger.error(f"[{datetime.now()}] 無法取得文章選單資料")
            return []

        # 儲存原始資料到 JSON（使用增量追加）
        if FEATURES.get("save_to_json", False):
            self.file_service.append_to_json(api1_data, OUTPUT_FILES["api1"])

        # 處理文章選單資料
        new_articles = []
        for article_data in api1_data:
            create_time = parse_datetime(article_data.get("createTime", ""))

            # 如果有最後抓取時間，只處理更新的文章
            if last_scrape_time and create_time and create_time <= last_scrape_time:
                continue

            # 儲存到資料庫
            if FEATURES.get("save_to_database", True):
                article_menu = self.db_manager.save_article_menu(article_data)
                if article_menu:
                    new_articles.append(article_menu)

        # 提交選單資料
        self.db_manager.commit()
        return new_articles

    def _scrape_article_details(self, article_menus: List) -> int:
        """抓取文章詳細內容"""
        success_count = 0
        detailed_articles = []

        for article_menu in article_menus:
            self.logger.info(f"[{datetime.now()}] 抓取文章詳細內容: {article_menu.article_id}")

            # 構建 API2 URL
            detail_url = f"{API_URLS['api2']}{article_menu.article_id}.json"
            detail_data = self.api_service.fetch_data(detail_url, delay=3)

            if detail_data:
                # 儲存到資料庫
                if FEATURES.get("save_to_database", True):
                    article_detail = self.db_manager.save_article_detail(article_menu, detail_data)
                    if article_detail:
                        success_count += 1

                # 收集資料用於 JSON 儲存
                if FEATURES.get("save_to_json", False):
                    detailed_articles.append(detail_data)

        # 提交詳細資料
        self.db_manager.commit()

        # 儲存詳細資料到 JSON（使用增量追加）
        if FEATURES.get("save_to_json", False) and detailed_articles:
            self.file_service.append_to_json(detailed_articles, OUTPUT_FILES["api2"])

        return success_count

    def _get_latest_create_time(self, article_menus: List) -> Optional[datetime]:
        """取得最新的建立時間"""
        latest_time = None
        for article_menu in article_menus:
            if article_menu.create_time:
                if not latest_time or article_menu.create_time > latest_time:
                    latest_time = article_menu.create_time
        return latest_time
