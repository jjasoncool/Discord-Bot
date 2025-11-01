"""
Discord Bot API 服務
提供文章查詢功能給 Discord Bot 使用
"""
from fastapi import FastAPI, HTTPException, Depends
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import List, Optional
from pydantic import BaseModel

from db.models import ArticleMenu, ArticleDetail, FBPost, FBImage, get_db_session
from sqlalchemy.orm import joinedload
from utils.logger import get_logger

# 建立 FastAPI 實例
app = FastAPI(title="Discord Bot API", description="提供文章查詢功能給 Discord Bot")

# 建立 logger
logger = get_logger('api_server')

# Pydantic 模型
class ArticleResponse(BaseModel):
    """文章回應模型"""
    article_id: int
    article_title: str
    article_desc: Optional[str]
    article_content: Optional[str]  # 主表簡短版本
    article_content_full: Optional[str]  # 副表完整版本
    article_type: Optional[int]
    article_type_name: Optional[str]  # 副表的類型名稱
    create_time: str
    start_time: Optional[str]
    suggest_cover: Optional[str]
    article_cover: Optional[str]  # 副表的封面圖
    content_cover: Optional[str]  # 副表的內容封面
    game_id: Optional[str]  # 副表的遊戲 ID

    class Config:
        from_attributes = True

class NewArticlesResponse(BaseModel):
    """新文章查詢回應模型"""
    success: bool
    message: str
    articles: List[ArticleResponse]
    total_count: int

class SingleArticleResponse(BaseModel):
    """單一文章查詢回應模型"""
    success: bool
    article: Optional[ArticleResponse] = None
    message: Optional[str] = None

class FBPostResponse(BaseModel):
    """FB 貼文回應模型"""
    id: int
    post_id: str
    url: Optional[str]
    pfbid_url: Optional[str]
    text: Optional[str]
    text_md: Optional[str]
    timestamp: Optional[str]
    created_at: str
    images: List[str]

    class Config:
        from_attributes = True

class FBPostsResponse(BaseModel):
    """FB 貼文列表回應模型"""
    success: bool
    message: str
    posts: List[FBPostResponse]
    total_count: int

class SingleFBPostResponse(BaseModel):
    """單一 FB 貼文查詢回應模型"""
    success: bool
    post: Optional[FBPostResponse] = None
    message: Optional[str] = None

# 依賴注入：獲取資料庫 session
def get_db():
    """獲取資料庫 session"""
    db = get_db_session()
    try:
        yield db
    finally:
        db.close()

@app.get("/health")
async def health_check():
    """健康檢查端點"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "service": "discord-bot-api"
    }

@app.get("/api/articles/recent", response_model=NewArticlesResponse)
async def get_recent_articles(
    days: int = 3,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """
    獲取最近的文章

    Args:
        days: 查詢天數，預設3天
        limit: 回傳數量限制，預設50筆
        db: 資料庫 session

    Returns:
        NewArticlesResponse: 包含文章列表的回應
    """
    try:
        # 計算查詢的開始時間（3天前）
        start_date = datetime.now() - timedelta(days=days)

        logger.info(f"查詢 {days} 天內的文章，從 {start_date} 開始")

        # 查詢最近的文章，LEFT JOIN 副表獲取完整內容
        query = db.query(ArticleMenu).outerjoin(
            ArticleDetail, ArticleMenu.article_id == ArticleDetail.article_id
        ).filter(
            ArticleMenu.start_time >= start_date
        ).order_by(
            ArticleMenu.start_time.desc()
        ).limit(limit)

        results = query.all()

        # 轉換為回應格式
        article_responses = []
        for article in results:
            # 獲取關聯的詳細資料
            detail = article.article_detail if hasattr(article, 'article_detail') else None

            article_responses.append(ArticleResponse(
                article_id=article.article_id,
                article_title=article.article_title,
                article_desc=article.article_desc,
                article_content=article.article_content,  # 主表簡短版本
                article_content_full=detail.article_content if detail else None,  # 副表完整版本
                article_type=article.article_type,
                article_type_name=detail.article_type_name if detail else None,
                create_time=article.create_time.isoformat() if article.create_time else "",
                start_time=article.start_time.isoformat() if article.start_time else None,
                suggest_cover=article.suggest_cover,
                article_cover=detail.article_cover if detail else None,
                content_cover=detail.content_cover if detail else None,
                game_id=detail.game_id if detail else None
            ))

        logger.info(f"找到 {len(article_responses)} 篇文章")

        return NewArticlesResponse(
            success=True,
            message=f"成功獲取 {len(article_responses)} 篇文章",
            articles=article_responses,
            total_count=len(article_responses)
        )

    except Exception as e:
        logger.error(f"查詢文章時發生錯誤: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"查詢文章失敗: {str(e)}")

@app.get("/api/articles/discord", response_model=NewArticlesResponse)
async def get_articles_for_discord(
    days: int = 3,
    limit: int = 50,
    order: str = "asc",  # 新增排序參數：asc=舊到新，desc=新到舊
    db: Session = Depends(get_db)
):
    """
    專為 Discord Bot 設計的文章查詢 API
    優先返回有完整內容的文章

    Args:
        days: 查詢天數，預設3天
        limit: 回傳數量限制，預設50筆
        order: 排序方式，預設 asc（舊到新），可選 desc（新到舊）
        db: 資料庫 session

    Returns:
        NewArticlesResponse: 包含文章列表的回應
    """
    try:
        # 計算查詢的開始時間
        start_date = datetime.now() - timedelta(days=days)

        logger.info(f"Discord Bot 查詢 {days} 天內的文章，從 {start_date} 開始，排序: {order}")

        # 查詢有完整內容的文章，JOIN 副表
        query = db.query(ArticleMenu).join(
            ArticleDetail, ArticleMenu.article_id == ArticleDetail.article_id
        ).filter(
            ArticleMenu.start_time >= start_date
        )

        # 根據排序參數決定排序方式
        if order.lower() == "desc":
            query = query.order_by(ArticleMenu.start_time.desc())
        else:  # 預設為 asc，舊到新
            query = query.order_by(ArticleMenu.start_time.asc())

        query = query.limit(limit)

        results = query.all()

        # 轉換為回應格式
        article_responses = []
        for article in results:
            detail = article.article_detail

            article_responses.append(ArticleResponse(
                article_id=article.article_id,
                article_title=article.article_title,
                article_desc=article.article_desc,
                article_content=article.article_content,  # 主表簡短版本
                article_content_full=detail.article_content if detail else None,  # 副表完整版本
                article_type=article.article_type,
                article_type_name=detail.article_type_name if detail else None,
                create_time=article.create_time.isoformat() if article.create_time else "",
                start_time=article.start_time.isoformat() if article.start_time else None,
                suggest_cover=article.suggest_cover,
                article_cover=detail.article_cover if detail else None,
                content_cover=detail.content_cover if detail else None,
                game_id=detail.game_id if detail else None
            ))

        logger.info(f"Discord Bot 找到 {len(article_responses)} 篇有完整內容的文章")

        return NewArticlesResponse(
            success=True,
            message=f"成功獲取 {len(article_responses)} 篇文章",
            articles=article_responses,
            total_count=len(article_responses)
        )

    except Exception as e:
        logger.error(f"Discord Bot 查詢文章時發生錯誤: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"查詢文章失敗: {str(e)}")

@app.get("/api/articles/{article_id}", response_model=SingleArticleResponse)
async def get_article_by_id(
    article_id: int,
    db: Session = Depends(get_db)
):
    """
    根據文章 ID 獲取特定文章

    Args:
        article_id: 文章 ID
        db: 資料庫 session

    Returns:
        SingleArticleResponse: 包含單一文章資料或錯誤訊息的回應
    """
    try:
        article = db.query(ArticleMenu).outerjoin(
            ArticleDetail, ArticleMenu.article_id == ArticleDetail.article_id
        ).filter(
            ArticleMenu.article_id == article_id
        ).first()

        if not article:
            logger.warning(f"API 查詢：找不到 ID 為 {article_id} 的文章")
            return SingleArticleResponse(success=False, message=f"找不到 ID 為 {article_id} 的文章")

        # 獲取關聯的詳細資料
        detail = article.article_detail if hasattr(article, 'article_detail') else None

        response_data = ArticleResponse(
            article_id=article.article_id,
            article_title=article.article_title,
            article_desc=article.article_desc,
            article_content=article.article_content,
            article_content_full=detail.article_content if detail else None,
            article_type=article.article_type,
            article_type_name=detail.article_type_name if detail else None,
            create_time=article.create_time.isoformat() if article.create_time else "",
            start_time=article.start_time.isoformat() if article.start_time else None,
            suggest_cover=article.suggest_cover,
            article_cover=detail.article_cover if detail else None,
            content_cover=detail.content_cover if detail else None,
            game_id=detail.game_id if detail else None
        )

        return SingleArticleResponse(success=True, article=response_data)

    except Exception as e:
        logger.error(f"查詢文章 {article_id} 時發生錯誤: {str(e)}", exc_info=True)
        # 保持 HTTP 500 錯誤，因為這是伺服器內部錯誤
        raise HTTPException(status_code=500, detail=f"查詢文章失敗: {str(e)}")

@app.get("/api/fb_posts/recent", response_model=FBPostsResponse)
async def get_recent_fb_posts(
    days: int = 7,
    limit: int = 20,
    db: Session = Depends(get_db)
):
    """
    獲取最近的 FB 貼文

    Args:
        days: 查詢天數，預設7天
        limit: 回傳數量限制，預設20筆
        db: 資料庫 session

    Returns:
        FBPostsResponse: 包含 FB 貼文列表的回應
    """
    try:
        # 計算查詢的開始時間
        start_date = datetime.now() - timedelta(days=days)

        logger.info(f"查詢 {days} 天內的 FB 貼文，從 {start_date} 開始")

        # 查詢最近的 FB 貼文，按 created_at 降序排列，並載入關聯圖片
        posts = db.query(FBPost).options(joinedload(FBPost.images)).filter(
            FBPost.created_at >= start_date
        ).order_by(FBPost.created_at.desc()).limit(limit).all()

        # 轉換為回應格式
        post_responses = []
        for post in posts:
            # 獲取關聯的圖片
            images = [img.image_url for img in post.images] if hasattr(post, 'images') else []

            post_responses.append(FBPostResponse(
                id=post.id,
                post_id=post.post_id,
                url=post.url,
                pfbid_url=post.pfbid_url,
                text=post.text,
                text_md=post.text_md,
                timestamp=post.timestamp.isoformat() if post.timestamp else None,
                created_at=post.created_at.isoformat(),
                images=images
            ))

        logger.info(f"找到 {len(post_responses)} 篇 FB 貼文")

        return FBPostsResponse(
            success=True,
            message=f"成功獲取 {len(post_responses)} 篇 FB 貼文",
            posts=post_responses,
            total_count=len(post_responses)
        )

    except Exception as e:
        logger.error(f"查詢 FB 貼文時發生錯誤: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"查詢 FB 貼文失敗: {str(e)}")

@app.get("/api/fb_posts/{post_id}", response_model=SingleFBPostResponse)
async def get_fb_post_by_id(
    post_id: str,
    db: Session = Depends(get_db)
):
    """
    根據 FB 貼文 ID 或資料庫 ID 獲取特定貼文
    智能判斷：如果是純數字，視為資料庫 ID；否則視為 post_id

    Args:
        post_id: FB 貼文 ID 或資料庫 ID
        db: 資料庫 session

    Returns:
        SingleFBPostResponse: 包含單一 FB 貼文資料或錯誤訊息的回應
    """
    try:
        # 智能判斷：嘗試將輸入解析為數字（資料庫 ID）
        try:
            db_id = int(post_id)
            # 如果是數字，用資料庫 ID 查詢，並載入關聯圖片
            post = db.query(FBPost).options(joinedload(FBPost.images)).filter(FBPost.id == db_id).first()
            query_type = f"資料庫 ID {db_id}"
        except ValueError:
            # 如果不是數字，用 post_id 查詢，並載入關聯圖片
            post = db.query(FBPost).options(joinedload(FBPost.images)).filter(FBPost.post_id == post_id).first()
            query_type = f"post_id {post_id}"

        if not post:
            logger.warning(f"API 查詢：找不到 {query_type} 的 FB 貼文")
            return SingleFBPostResponse(success=False, message=f"找不到 {query_type} 的 FB 貼文")

        # 獲取關聯的圖片
        images = [img.image_url for img in post.images] if hasattr(post, 'images') else []

        response_data = FBPostResponse(
            id=post.id,
            post_id=post.post_id,
            url=post.url,
            pfbid_url=post.pfbid_url,
            text=post.text,
            text_md=post.text_md,
            timestamp=post.timestamp.isoformat() if post.timestamp else None,
            created_at=post.created_at.isoformat(),
            images=images
        )

        return SingleFBPostResponse(success=True, post=response_data)

    except Exception as e:
        logger.error(f"查詢 FB 貼文 {post_id} 時發生錯誤: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"查詢 FB 貼文失敗: {str(e)}")

@app.get("/api/debug/tables")
async def debug_table_structure(db: Session = Depends(get_db)):
    """
    調試用端點：檢查表格結構和資料
    """
    try:
        # 檢查主表資料
        main_count = db.query(ArticleMenu).count()
        detail_count = db.query(ArticleDetail).count()
        fb_post_count = db.query(FBPost).count()
        fb_image_count = db.query(FBImage).count()

        # 檢查有關聯的資料數量
        joined_count = db.query(ArticleMenu).join(
            ArticleDetail, ArticleMenu.article_id == ArticleDetail.article_id
        ).count()

        # 取得最新的一筆資料來檢查結構
        latest_main = db.query(ArticleMenu).order_by(ArticleMenu.created_at.desc()).first()
        latest_detail = db.query(ArticleDetail).order_by(ArticleDetail.created_at.desc()).first()
        latest_fb_post = db.query(FBPost).order_by(FBPost.created_at.desc()).first()

        result = {
            "table_counts": {
                "article_menus": main_count,
                "article_details": detail_count,
                "fb_posts": fb_post_count,
                "fb_images": fb_image_count,
                "joined_records": joined_count
            },
            "latest_main_article": {
                "id": latest_main.article_id if latest_main else None,
                "title": latest_main.article_title if latest_main else None,
                "has_content": bool(latest_main.article_content) if latest_main else False,
                "start_time": latest_main.start_time.isoformat() if latest_main and latest_main.start_time else None
            } if latest_main else None,
            "latest_detail_article": {
                "id": latest_detail.article_id if latest_detail else None,
                "title": latest_detail.article_title if latest_detail else None,
                "has_content": bool(latest_detail.article_content) if latest_detail else False,
                "type_name": latest_detail.article_type_name if latest_detail else None
            } if latest_detail else None,
            "latest_fb_post": {
                "id": latest_fb_post.id if latest_fb_post else None,
                "post_id": latest_fb_post.post_id if latest_fb_post else None,
                "url": latest_fb_post.url if latest_fb_post else None,
                "created_at": latest_fb_post.created_at.isoformat() if latest_fb_post else None
            } if latest_fb_post else None
        }

        return result

    except Exception as e:
        logger.error(f"調試查詢失敗: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"調試查詢失敗: {str(e)}")

if __name__ == "__main__":
    import uvicorn

    logger.info("啟動 Discord Bot API 服務...")

    # 啟動 API 服務
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )
