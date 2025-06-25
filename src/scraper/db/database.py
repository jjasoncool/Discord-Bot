"""
資料庫操作模組
處理所有與資料庫相關的 CRUD 操作
"""
from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from .models import ArticleMenu, ArticleDetail, SystemState
from utils.datetime_utils import parse_datetime
from utils.logger import get_logger


class DatabaseManager:
    """資料庫管理器"""

    def __init__(self, session: Session):
        self.session = session
        self.logger = get_logger('database')

    def get_last_scrape_time(self) -> Optional[datetime]:
        """取得最後抓取時間"""
        try:
            state = self.session.query(SystemState).filter(
                SystemState.key == "last_scrape_time"
            ).first()

            if state and state.value:
                return datetime.fromisoformat(state.value)
            return None

        except SQLAlchemyError as e:
            self.logger.error(f"資料庫查詢錯誤 (get_last_scrape_time): {str(e)}")
            return None
        except Exception as e:
            self.logger.error(f"取得最後抓取時間時發生錯誤: {str(e)}", exc_info=True)
            return None

    def update_last_scrape_time(self, last_time: datetime) -> bool:
        """更新最後抓取時間"""
        try:
            state = self.session.query(SystemState).filter(
                SystemState.key == "last_scrape_time"
            ).first()

            if state:
                state.value = last_time.isoformat()
                state.updated_at = datetime.utcnow()
            else:
                state = SystemState(
                    key="last_scrape_time",
                    value=last_time.isoformat()
                )
                self.session.add(state)

            self.session.commit()
            return True

        except SQLAlchemyError as e:
            self.logger.error(f"資料庫更新錯誤 (update_last_scrape_time): {str(e)}")
            self.session.rollback()
            return False
        except Exception as e:
            self.logger.error(f"更新最後抓取時間時發生錯誤: {str(e)}", exc_info=True)
            self.session.rollback()
            return False

    def save_article_menu(self, article_data: dict) -> Optional[ArticleMenu]:
        """儲存文章選單資料"""
        try:
            # 檢查是否已存在
            existing = self.session.query(ArticleMenu).filter(
                ArticleMenu.article_id == article_data["articleId"]
            ).first()

            if existing:
                # 更新現有資料
                self._update_article_menu(existing, article_data)
                return existing
            else:
                # 新增資料
                new_article = self._create_article_menu(article_data)
                self.session.add(new_article)
                return new_article

        except SQLAlchemyError as e:
            self.logger.error(f"資料庫操作錯誤 (save_article_menu): {str(e)}")
            return None
        except Exception as e:
            self.logger.error(f"儲存文章選單資料時發生錯誤: {str(e)}", exc_info=True)
            return None

    def save_article_detail(self, article_menu: ArticleMenu, detail_data: dict) -> Optional[ArticleDetail]:
        """儲存文章詳細資料"""
        try:
            # 檢查是否已存在
            existing = self.session.query(ArticleDetail).filter(
                ArticleDetail.article_id == detail_data["articleId"]
            ).first()

            if existing:
                # 更新現有資料
                self._update_article_detail(existing, detail_data)
                return existing
            else:
                # 新增資料
                new_detail = self._create_article_detail(article_menu, detail_data)
                self.session.add(new_detail)
                return new_detail

        except SQLAlchemyError as e:
            self.logger.error(f"資料庫操作錯誤 (save_article_detail): {str(e)}")
            return None
        except Exception as e:
            self.logger.error(f"儲存文章詳細資料時發生錯誤: {str(e)}", exc_info=True)
            return None

    def _update_article_menu(self, article: ArticleMenu, data: dict):
        """更新文章選單資料"""
        article.article_title = data.get("articleTitle", "")
        article.article_desc = data.get("articleDesc", "")
        article.article_content = data.get("articleContent", "")
        article.article_type = data.get("articleType")
        article.start_time = parse_datetime(data.get("startTime", ""))
        article.sorting_mark = data.get("sortingMark", 0)
        article.suggest_cover = data.get("suggestCover", "")
        article.top = data.get("top", 0)
        article.updated_at = datetime.utcnow()

    def _create_article_menu(self, data: dict) -> ArticleMenu:
        """建立新的文章選單資料"""
        return ArticleMenu(
            article_id=data["articleId"],
            article_title=data.get("articleTitle", ""),
            article_desc=data.get("articleDesc", ""),
            article_content=data.get("articleContent", ""),
            article_type=data.get("articleType"),
            create_time=parse_datetime(data.get("createTime", "")),
            start_time=parse_datetime(data.get("startTime", "")),
            sorting_mark=data.get("sortingMark", 0),
            suggest_cover=data.get("suggestCover", ""),
            top=data.get("top", 0)
        )

    def _update_article_detail(self, detail: ArticleDetail, data: dict):
        """更新文章詳細資料"""
        detail.article_title = data.get("articleTitle", "")
        detail.article_content = data.get("articleContent", "")
        detail.article_cover = data.get("articleCover", "")
        detail.article_type = data.get("articleType")
        detail.article_type_name = data.get("articleTypeName", "")
        detail.content_cover = data.get("contentCover", "")
        detail.game_id = data.get("gameId", "")
        detail.start_time = parse_datetime(data.get("startTime", ""))
        detail.updated_at = datetime.utcnow()

    def _create_article_detail(self, article_menu: ArticleMenu, data: dict) -> ArticleDetail:
        """建立新的文章詳細資料"""
        return ArticleDetail(
            article_menu_id=article_menu.id,
            article_id=data["articleId"],
            article_title=data.get("articleTitle", ""),
            article_content=data.get("articleContent", ""),
            article_cover=data.get("articleCover", ""),
            article_type=data.get("articleType"),
            article_type_name=data.get("articleTypeName", ""),
            content_cover=data.get("contentCover", ""),
            game_id=data.get("gameId", ""),
            start_time=parse_datetime(data.get("startTime", ""))
        )

    def commit(self) -> bool:
        """提交交易"""
        try:
            self.session.commit()
            return True
        except SQLAlchemyError as e:
            self.logger.error(f"資料庫提交錯誤: {str(e)}", exc_info=True)
            self.session.rollback()
            return False

    def rollback(self):
        """回滾交易"""
        try:
            self.session.rollback()
        except Exception as e:
            self.logger.error(f"回滾失敗: {str(e)}", exc_info=True)

    def close(self):
        """關閉 session"""
        try:
            self.session.close()
        except Exception as e:
            self.logger.error(f"關閉 session 失敗: {str(e)}", exc_info=True)
