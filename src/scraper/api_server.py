"""
Discord Bot API 服務
提供文章查詢功能給 Discord Bot 使用
"""
from fastapi import FastAPI, HTTPException, Depends
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import List, Optional
from pydantic import BaseModel
import json
from sqlalchemy import case

from db.models import ArticleMenu, ArticleDetail, FBPost, FBImage, PTTPost, BahamutPost, BahamutPostComment, HardwareNews, get_db_session
from sqlalchemy.orm import joinedload, subqueryload
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


class PTTCommentResponse(BaseModel):
    tag: Optional[str]
    user: Optional[str]
    content: Optional[str]
    time: Optional[str]


class PTTPostResponse(BaseModel):
    """PTT 貼文回應模型"""
    id: int
    board: str
    article_id: str
    title: str
    author: Optional[str]
    url: str
    content: Optional[str]
    comments: List[PTTCommentResponse]
    comments_count: int
    comments_hash: Optional[str]
    matched_keywords: Optional[str]
    published_at: Optional[str]
    created_at: str

    class Config:
        from_attributes = True


class PTTPostsResponse(BaseModel):
    """PTT 貼文列表回應模型"""
    success: bool
    message: str
    posts: List[PTTPostResponse]
    total_count: int


class SinglePTTPostResponse(BaseModel):
    """單一 PTT 貼文查詢回應模型"""
    success: bool
    post: Optional[PTTPostResponse] = None
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


@app.get("/api/ptt_posts/recent", response_model=PTTPostsResponse)
async def get_recent_ptt_posts(
    days: int = 3,
    limit: int = 50,
    board: Optional[str] = None,
    order: str = "desc",
    db: Session = Depends(get_db)
):
    """獲取最近的 PTT 貼文"""
    try:
        start_date = datetime.now() - timedelta(days=days)

        query = db.query(PTTPost).filter(
            (PTTPost.published_at >= start_date) | (PTTPost.created_at >= start_date)
        )
        if board:
            query = query.filter(PTTPost.board == board)

        published_sort = case(
            (PTTPost.published_at.is_(None), PTTPost.created_at),
            else_=PTTPost.published_at,
        )

        if order.lower() == "asc":
            query = query.order_by(published_sort.asc(), PTTPost.created_at.asc())
        else:
            query = query.order_by(published_sort.desc(), PTTPost.created_at.desc())

        posts = query.limit(limit).all()

        post_responses = [
            PTTPostResponse(
                id=post.id,
                board=post.board,
                article_id=post.article_id,
                title=post.title,
                author=post.author,
                url=post.url,
                content=post.content,
                comments=[PTTCommentResponse(**item) for item in json.loads(post.comments_json or "[]")],
                comments_count=post.comments_count or 0,
                comments_hash=post.comments_hash,
                matched_keywords=post.matched_keywords,
                published_at=post.published_at.isoformat() if post.published_at else None,
                created_at=post.created_at.isoformat() if post.created_at else "",
            )
            for post in posts
        ]

        return PTTPostsResponse(
            success=True,
            message=f"成功獲取 {len(post_responses)} 篇 PTT 貼文",
            posts=post_responses,
            total_count=len(post_responses),
        )

    except Exception as e:
        logger.error(f"查詢 PTT 貼文時發生錯誤: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"查詢 PTT 貼文失敗: {str(e)}")


@app.get("/api/ptt_posts/{post_id}", response_model=SinglePTTPostResponse)
async def get_ptt_post_by_id(
    post_id: int,
    db: Session = Depends(get_db)
):
    """根據資料庫 ID 取得單篇 PTT 貼文"""
    try:
        post = db.query(PTTPost).filter(PTTPost.id == post_id).first()

        if not post:
            return SinglePTTPostResponse(success=False, message=f"找不到 ID 為 {post_id} 的 PTT 貼文")

        response_data = PTTPostResponse(
            id=post.id,
            board=post.board,
            article_id=post.article_id,
            title=post.title,
            author=post.author,
            url=post.url,
            content=post.content,
            comments=[PTTCommentResponse(**item) for item in json.loads(post.comments_json or "[]")],
            comments_count=post.comments_count or 0,
            comments_hash=post.comments_hash,
            matched_keywords=post.matched_keywords,
            published_at=post.published_at.isoformat() if post.published_at else None,
            created_at=post.created_at.isoformat() if post.created_at else "",
        )

        return SinglePTTPostResponse(success=True, post=response_data)

    except Exception as e:
        logger.error(f"查詢 PTT 貼文 {post_id} 時發生錯誤: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"查詢 PTT 貼文失敗: {str(e)}")

# === Bahamut API ===

class BahamutCommentResponse(BaseModel):
    comment_id: str
    floor: Optional[str]
    position: Optional[int]
    user_id: Optional[str]
    user_name: Optional[str]
    content: Optional[str]
    is_hot: bool = False
    gp_count: int = 0
    bp_count: int = 0
    published_at: Optional[str]

    class Config:
        from_attributes = True


class BahamutPostResponse(BaseModel):
    """單篇巴哈文章（主文或回覆）"""
    id: int
    board_id: str
    post_id: str                          # snA
    sn: str
    position: int
    title: Optional[str]
    category: Optional[str]
    author_name: Optional[str]
    author_id: Optional[str]
    url: Optional[str]
    gp_count: int = 0
    bp_count: int = 0
    content: Optional[str]
    content_images: List[str] = []
    comments_count: int = 0
    replies_count: int = 0
    published_at: Optional[str]
    created_at: str
    comments: List[BahamutCommentResponse] = []

    class Config:
        from_attributes = True


class BahamutThreadResponse(BaseModel):
    """一個完整討論串（主文 + 回覆，以 snA 分組）"""
    post_id: str                          # snA
    board_id: str
    main_post: BahamutPostResponse
    replies: List[BahamutPostResponse] = []


class BahamutThreadsResponse(BaseModel):
    success: bool
    message: str
    threads: List[BahamutThreadResponse]
    total_count: int


class SingleBahamutThreadResponse(BaseModel):
    success: bool
    thread: Optional[BahamutThreadResponse] = None
    message: Optional[str] = None


def _build_bahamut_post_response(post: BahamutPost) -> BahamutPostResponse:
    """將 BahamutPost ORM 物件轉為 API response。"""
    content_images = []
    if post.content_images_json:
        try:
            content_images = json.loads(post.content_images_json)
        except (json.JSONDecodeError, TypeError):
            pass

    comments = [
        BahamutCommentResponse(
            comment_id=c.comment_id,
            floor=c.floor,
            position=c.position,
            user_id=c.user_id,
            user_name=c.user_name,
            content=c.content,
            is_hot=c.is_hot or False,
            gp_count=c.gp_count or 0,
            bp_count=c.bp_count or 0,
            published_at=c.published_at.isoformat() if c.published_at else None,
        )
        for c in sorted(post.comments, key=lambda x: x.position or 0)
    ]

    return BahamutPostResponse(
        id=post.id,
        board_id=post.board_id,
        post_id=post.post_id,
        sn=post.sn,
        position=post.position,
        title=post.title,
        category=post.category,
        author_name=post.author_name,
        author_id=post.author_id,
        url=post.url,
        gp_count=post.gp_count or 0,
        bp_count=post.bp_count or 0,
        content=post.content,
        content_images=content_images,
        comments_count=post.comments_count or 0,
        replies_count=post.replies_count or 0,
        published_at=post.published_at.isoformat() if post.published_at else None,
        created_at=post.created_at.isoformat() if post.created_at else "",
        comments=comments,
    )


def _group_posts_into_threads(posts: List[BahamutPost]) -> List[BahamutThreadResponse]:
    """將 BahamutPost 列表按 (board_id, post_id/snA) 分組成討論串。"""
    from collections import OrderedDict
    threads_map: OrderedDict[str, dict] = OrderedDict()

    for post in posts:
        key = f"{post.board_id}:{post.post_id}"
        if key not in threads_map:
            threads_map[key] = {"board_id": post.board_id, "post_id": post.post_id, "main": None, "replies": []}
        resp = _build_bahamut_post_response(post)
        if post.position == 1:
            threads_map[key]["main"] = resp
        else:
            threads_map[key]["replies"].append(resp)

    result = []
    for key, group in threads_map.items():
        if group["main"] is None:
            continue
        group["replies"].sort(key=lambda r: r.position)
        result.append(BahamutThreadResponse(
            post_id=group["post_id"],
            board_id=group["board_id"],
            main_post=group["main"],
            replies=group["replies"],
        ))
    return result


@app.get("/api/bahamut/recent", response_model=BahamutThreadsResponse)
async def get_recent_bahamut_threads(
    days: int = 3,
    hours: Optional[int] = None,
    limit: int = 50,
    board_id: Optional[str] = None,
    order: str = "desc",
    db: Session = Depends(get_db)
):
    """取得最近的巴哈討論串（含主文、回覆、留言）。hours 優先於 days。"""
    try:
        if hours is not None:
            start_date = datetime.now() - timedelta(hours=hours)
        else:
            start_date = datetime.now() - timedelta(days=days)

        # 找出活躍的 snA：只要該 snA 底下任一 post 或 comment 的 published_at 在時間範圍內
        from sqlalchemy import func, or_
        latest_activity = func.max(
            case(
                (BahamutPostComment.published_at.isnot(None), BahamutPostComment.published_at),
                else_=BahamutPost.published_at,
            )
        ).label("latest_activity")

        active_sna_query = (
            db.query(
                BahamutPost.post_id,
                BahamutPost.board_id,
                latest_activity,
            )
            .outerjoin(BahamutPostComment, BahamutPostComment.bahamut_post_id == BahamutPost.id)
            .filter(BahamutPost.is_deleted.in_([False, None]))
            .group_by(BahamutPost.board_id, BahamutPost.post_id)
            .having(or_(
                func.max(BahamutPost.published_at) >= start_date,
                func.max(BahamutPostComment.published_at) >= start_date,
            ))
        )
        if board_id:
            active_sna_query = active_sna_query.filter(BahamutPost.board_id == board_id)

        if order.lower() == "asc":
            active_sna_query = active_sna_query.order_by(latest_activity.asc())
        else:
            active_sna_query = active_sna_query.order_by(latest_activity.desc())

        active_sna_query = active_sna_query.limit(limit)
        thread_keys = active_sna_query.all()

        if not thread_keys:
            return BahamutThreadsResponse(success=True, message="沒有符合條件的巴哈討論串", threads=[], total_count=0)

        # 一次查所有相關 posts + comments
        target_post_ids = [row.post_id for row in thread_keys]
        from sqlalchemy import tuple_
        all_posts = (
            db.query(BahamutPost)
            .options(subqueryload(BahamutPost.comments))
            .filter(
                BahamutPost.post_id.in_(target_post_ids),
                BahamutPost.is_deleted.in_([False, None]),
            )
            .all()
        )

        threads = _group_posts_into_threads(all_posts)

        return BahamutThreadsResponse(
            success=True,
            message=f"成功獲取 {len(threads)} 個巴哈討論串",
            threads=threads,
            total_count=len(threads),
        )

    except Exception as e:
        logger.error(f"查詢巴哈討論串時發生錯誤: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"查詢巴哈討論串失敗: {str(e)}")


@app.get("/api/bahamut/{board_id}/{post_id}", response_model=SingleBahamutThreadResponse)
async def get_bahamut_thread(
    board_id: str,
    post_id: str,
    db: Session = Depends(get_db)
):
    """根據 board_id + post_id(snA) 取得單一巴哈討論串"""
    try:
        posts = (
            db.query(BahamutPost)
            .options(subqueryload(BahamutPost.comments))
            .filter(
                BahamutPost.board_id == board_id,
                BahamutPost.post_id == post_id,
                BahamutPost.is_deleted.in_([False, None]),
            )
            .all()
        )

        if not posts:
            return SingleBahamutThreadResponse(
                success=False,
                message=f"找不到 board_id={board_id}, post_id={post_id} 的巴哈討論串",
            )

        threads = _group_posts_into_threads(posts)
        if not threads:
            return SingleBahamutThreadResponse(
                success=False,
                message=f"找不到主文：board_id={board_id}, post_id={post_id}",
            )

        return SingleBahamutThreadResponse(success=True, thread=threads[0])

    except Exception as e:
        logger.error(f"查詢巴哈討論串 {board_id}/{post_id} 時發生錯誤: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"查詢巴哈討論串失敗: {str(e)}")


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
        ptt_post_count = db.query(PTTPost).count()

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
                "ptt_posts": ptt_post_count,
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

# === IT 文章（系統設備 / 硬體新知）API — 主題層 it_articles，來源目前為 HKEPC ===

class HardwareNewsResponse(BaseModel):
    """HKEPC 硬體新知回應模型"""
    id: int
    hkepc_id: int
    title: str
    url: str
    author: Optional[str]
    introduction: Optional[str]
    content: Optional[str]
    images: List[str]              # 來源圖片 URL 清單（由 images_json 解析）
    reference_url: Optional[str]
    tags: Optional[str]
    comment_count: int
    published_at: Optional[str]
    created_at: str


class HardwareNewsListResponse(BaseModel):
    """HKEPC 列表回應模型"""
    success: bool
    message: str
    items: List[HardwareNewsResponse]
    total_count: int


class SingleHardwareNewsResponse(BaseModel):
    """單篇 HKEPC 查詢回應模型"""
    success: bool
    item: Optional[HardwareNewsResponse] = None
    message: Optional[str] = None


def _hardware_news_to_response(row: HardwareNews) -> HardwareNewsResponse:
    return HardwareNewsResponse(
        id=row.id,
        hkepc_id=row.hkepc_id,
        title=row.title,
        url=row.url,
        author=row.author,
        introduction=row.introduction,
        content=row.content,
        images=json.loads(row.images_json) if row.images_json else [],
        reference_url=row.reference_url,
        tags=row.tags,
        comment_count=row.comment_count or 0,
        published_at=row.published_at.isoformat() if row.published_at else None,
        created_at=row.created_at.isoformat() if row.created_at else "",
    )


@app.get("/api/it_articles/recent", response_model=HardwareNewsListResponse)
async def get_recent_it_articles(
    days: int = 3,
    limit: int = 50,
    tag: Optional[str] = None,   # 依 tag 過濾（為將來不同 tag 發不同頻道鋪路）
    order: str = "asc",          # asc=舊到新（適合依序發送），desc=新到舊
    db: Session = Depends(get_db),
):
    """獲取最近的 HKEPC 硬體新知。"""
    try:
        start_date = datetime.now() - timedelta(days=days)
        query = db.query(HardwareNews).filter(
            (HardwareNews.published_at >= start_date) | (HardwareNews.created_at >= start_date)
        )
        if tag:
            query = query.filter(HardwareNews.tags.like(f"%{tag}%"))

        sort_col = HardwareNews.published_at
        query = query.order_by(sort_col.asc() if order == "asc" else sort_col.desc())
        rows = query.limit(limit).all()

        items = [_hardware_news_to_response(r) for r in rows]
        return HardwareNewsListResponse(
            success=True,
            message=f"成功獲取 {len(items)} 篇硬體新知",
            items=items,
            total_count=len(items),
        )
    except Exception as e:
        logger.error(f"查詢 HKEPC 硬體新知時發生錯誤: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"查詢 HKEPC 失敗: {str(e)}")


@app.get("/api/it_articles/{hkepc_id}", response_model=SingleHardwareNewsResponse)
async def get_it_article_by_id(
    hkepc_id: int,
    db: Session = Depends(get_db),
):
    """根據 HKEPC 文章 id 取得單篇。"""
    try:
        row = db.query(HardwareNews).filter(HardwareNews.hkepc_id == hkepc_id).first()
        if not row:
            return SingleHardwareNewsResponse(success=False, message=f"找不到 hkepc_id={hkepc_id} 的文章")
        return SingleHardwareNewsResponse(success=True, item=_hardware_news_to_response(row))
    except Exception as e:
        logger.error(f"查詢 HKEPC 文章 {hkepc_id} 時發生錯誤: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"查詢 HKEPC 文章失敗: {str(e)}")


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
