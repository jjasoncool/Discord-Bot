"""
資料庫操作模組
處理所有與資料庫相關的 CRUD 操作
"""
from datetime import datetime
from typing import Optional, List, Dict
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from .models import ArticleMenu, ArticleDetail, SystemState, FBPost, FBImage
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

    # ---------------- FB Post 區段（以 content_hash 為唯一） ----------------
    def get_fb_post_by_content_hash(self, content_hash: str) -> Optional[FBPost]:
        """根據 content_hash 查詢 FB 貼文"""
        try:
            return self.session.query(FBPost).filter(FBPost.content_hash == content_hash).first()
        except Exception as e:
            self.logger.error(f"查詢 FB 貼文失敗: {str(e)}")
            return None

    def get_fb_post_by_url(self, url: str) -> Optional[FBPost]:
        """根據 URL 查詢 FB 貼文（保留舊方法，僅供相容）"""
        try:
            return self.session.query(FBPost).filter(FBPost.url == url).first()
        except Exception as e:
            self.logger.error(f"查詢 FB 貼文失敗: {str(e)}")
            return None

    def save_fb_post(self, post_data: dict, check_duplicate: bool = True) -> Optional[FBPost]:
        """
        儲存單篇 FB 貼文（舊流程；相容用）
        建議改用：sync_fb_posts_ops
        """
        try:
            if check_duplicate and post_data.get("content_hash"):
                existing_post = self.get_fb_post_by_content_hash(post_data["content_hash"])
                if existing_post:
                    return self._update_fb_post(existing_post, post_data)

            new_post = FBPost(
                post_id=post_data.get("post_id"),
                url=post_data.get("url") or None,
                pfbid_url=post_data.get("pfbid_url") or None,
                text=post_data.get("text", ""),
                text_md=post_data.get("text_md", ""),
                content_hash=post_data.get("content_hash"),
                timestamp=parse_datetime(post_data.get("timestamp")),
            )
            self.session.add(new_post)
            self.session.flush()

            if post_data.get("images"):
                for img_url in post_data["images"]:
                    self.session.add(FBImage(fb_post_id=new_post.id, image_url=img_url))

            return new_post

        except Exception as e:
            self.logger.error(f"儲存 FB 貼文失敗: {str(e)}")
            return None

    def _update_fb_post(self, existing_post: FBPost, post_data: dict) -> Optional[FBPost]:
        """
        更新現有 FB 貼文（遵循 JSON 的合併邏輯）
        - 僅補空白的 url/pfbid_url
        - text/text_md 取較長
        - 圖片合併新增
        - timestamp 若未知則補
        """
        try:
            updated = False

            # URL 欄位：僅補空白
            if (not existing_post.url) and post_data.get("url"):
                existing_post.url = post_data["url"]
                updated = True
            if (not existing_post.pfbid_url) and post_data.get("pfbid_url"):
                existing_post.pfbid_url = post_data["pfbid_url"]
                updated = True

            # 文本：取較長
            if post_data.get("text") and len(post_data["text"]) > len(existing_post.text or ""):
                existing_post.text = post_data["text"]
                updated = True

            if post_data.get("text_md") and len(post_data["text_md"]) > len(existing_post.text_md or ""):
                existing_post.text_md = post_data["text_md"]
                updated = True

            # 圖片：合併
            if post_data.get("images"):
                current_images = {img.image_url for img in existing_post.images}
                new_images = [u for u in post_data["images"] if u not in current_images]
                for img_url in new_images:
                    self.session.add(FBImage(fb_post_id=existing_post.id, image_url=img_url))
                if new_images:
                    updated = True

            # timestamp：若未知則補
            if post_data.get("timestamp") and not existing_post.timestamp:
                existing_post.timestamp = parse_datetime(post_data["timestamp"])
                updated = True

            if updated:
                existing_post.updated_at = datetime.utcnow()

            return existing_post

        except Exception as e:
            self.logger.error(f"更新 FB 貼文失敗: {str(e)}")
            return None

    # === 新增：依 JSON 決策同步（ops 驅動；不重複判斷） ===
    def sync_fb_posts_ops(self, ops: List[Dict]) -> None:
        """
        僅依據 JSON 的 ops 清單同步 DB：
        - op = {"action": "insert"|"update", "post": {...}}
        - 用 post["content_hash"] 當唯一定位值
        """
        try:
            for op in ops:
                action = op.get("action")
                p = op.get("post") or {}
                ch = p.get("content_hash")
                if not ch:
                    self.logger.warning("略過：缺少 content_hash 的 op")
                    continue

                if action == "insert":
                    # 已存在則略過（理論上 JSON 已決定 insert，這裡保守再查一次）
                    existing = self.get_fb_post_by_content_hash(ch)
                    if existing:
                        continue
                    new_post = FBPost(
                        post_id=p.get("post_id"),
                        url=(p.get("url") or None),
                        pfbid_url=(p.get("pfbid_url") or None),
                        text=p.get("text", ""),
                        text_md=p.get("text_md", ""),
                        content_hash=ch,
                        timestamp=parse_datetime(p.get("timestamp")),
                    )
                    self.session.add(new_post)
                    self.session.flush()
                    seen_images = set()
                    for img_url in (p.get("images") or []):
                        if not img_url or img_url in seen_images:
                            continue
                        seen_images.add(img_url)
                        self.session.add(FBImage(fb_post_id=new_post.id, image_url=img_url))

                elif action == "update":
                    existing = self.get_fb_post_by_content_hash(ch)
                    if not existing:
                        # 若找不到，退化為 insert（但原則上不會發生）
                        new_post = FBPost(
                            post_id=p.get("post_id"),
                            url=(p.get("url") or None),
                            pfbid_url=(p.get("pfbid_url") or None),
                            text=p.get("text", ""),
                            text_md=p.get("text_md", ""),
                            content_hash=ch,
                            timestamp=parse_datetime(p.get("timestamp")),
                        )
                        self.session.add(new_post)
                        self.session.flush()
                        for img_url in (p.get("images") or []):
                            self.session.add(FBImage(fb_post_id=new_post.id, image_url=img_url))
                        continue

                    # 按 JSON 合併規則更新
                    existing.images  # 觸發 lazy load，避免重複插入同圖造成 UNIQUE constraint
                    self._update_fb_post(existing, p)

                else:
                    # noop 不處理
                    continue

        except Exception as e:
            self.logger.error(f"同步 FB 貼文（ops）失敗: {str(e)}")
            self.session.rollback()
            raise

    # --- 舊流程的 _update_fb_post_with_json_logic / sync_fb_posts_from_json 可保留或移除 ---
    # 這裡保留一版簡化相容（若其他模組仍呼叫），但建議改用 sync_fb_posts_ops。
    def sync_fb_posts_from_json(self, posts_list: List[dict]):
        """相容方法：逐篇以 content_hash upsert（不含 ops 概念）"""
        try:
            for post_data in posts_list:
                ch = post_data.get("content_hash")
                if not ch:
                    continue
                existing = self.get_fb_post_by_content_hash(ch)
                if existing:
                    self._update_fb_post(existing, post_data)
                else:
                    self.save_fb_post(post_data, check_duplicate=False)
            self.session.commit()
        except Exception as e:
            self.logger.error(f"同步 FB 貼文失敗: {str(e)}")
            self.session.rollback()

    def close(self):
        """關閉 session"""
        try:
            self.session.close()
        except Exception as e:
            self.logger.error(f"關閉 session 失敗: {str(e)}", exc_info=True)
