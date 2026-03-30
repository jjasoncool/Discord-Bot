"""
依賴注入容器
管理所有服務的建立和配置
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from config import DATABASE_CONFIG
from db.models import Base
from db.database import DatabaseManager
from services.api_service import APIService
from services.bahamut_scraper_service import BahamutScraperService
from services.file_service import FileService
from services.ptt_scraper_service import PTTScraperService
from services.scraper_service import ScraperService


class ServiceContainer:
    """服務容器"""

    def __init__(self):
        self._engine = None
        self._session_factory = None
        self._api_service = None
        self._file_service = None

    def get_database_engine(self):
        """取得資料庫引擎"""
        if self._engine is None:
            self._engine = create_engine(DATABASE_CONFIG["url"], echo=False)
        return self._engine

    def get_session_factory(self):
        """取得 Session 工廠"""
        if self._session_factory is None:
            engine = self.get_database_engine()
            self._session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        return self._session_factory

    def create_database_session(self):
        """建立資料庫 Session"""
        session_factory = self.get_session_factory()
        return session_factory()

    def get_api_service(self) -> APIService:
        """取得 API 服務"""
        if self._api_service is None:
            self._api_service = APIService(timeout=30, default_delay=2)
        return self._api_service

    def get_file_service(self) -> FileService:
        """取得檔案服務"""
        if self._file_service is None:
            output_dir = os.getenv("OUTPUT_DIR", "data")
            self._file_service = FileService(output_dir)
        return self._file_service

    def create_database_manager(self) -> DatabaseManager:
        """建立資料庫管理器"""
        session = self.create_database_session()
        return DatabaseManager(session)

    def create_scraper_service(self) -> ScraperService:
        """建立爬蟲服務"""
        db_manager = self.create_database_manager()
        api_service = self.get_api_service()
        file_service = self.get_file_service()

        return ScraperService(db_manager, api_service, file_service)

    def create_ptt_scraper_service(self):
        """建立 PTT 爬蟲服務"""
        db_manager = self.create_database_manager()
        return PTTScraperService(db_manager=db_manager)

    def create_bahamut_scraper_service(self):
        """建立 Bahamut 爬蟲服務"""
        db_manager = self.create_database_manager()
        return BahamutScraperService(db_manager=db_manager)

    def create_database_tables(self):
        """建立資料庫表格"""
        engine = self.get_database_engine()
        Base.metadata.create_all(bind=engine)
