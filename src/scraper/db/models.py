from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime, timezone
from config import DATABASE_CONFIG

# 建立基礎模型類別
Base = declarative_base()

class ArticleMenu(Base):
    """文章選單主表 - API1 資料結構"""
    __tablename__ = 'article_menus'

    # 主鍵
    id = Column(Integer, primary_key=True, autoincrement=True)

    # API1 欄位對應
    article_id = Column(Integer, unique=True, nullable=False, index=True)  # articleId
    article_title = Column(String(500), nullable=False)  # articleTitle
    article_desc = Column(Text)  # articleDesc
    article_content = Column(Text)  # articleContent (簡短版本)
    article_type = Column(Integer)  # articleType

    # 時間欄位
    create_time = Column(DateTime, nullable=False, index=True)  # createTime
    start_time = Column(DateTime)   # startTime

    # 其他欄位
    sorting_mark = Column(Integer, default=0)  # sortingMark
    suggest_cover = Column(String(1000))       # suggestCover
    top = Column(Integer, default=0)           # top

    # 系統欄位
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # 關聯關係
    article_detail = relationship("ArticleDetail", back_populates="article_menu", uselist=False)

class ArticleDetail(Base):
    """文章詳細內容子表 - API2 資料結構"""
    __tablename__ = 'article_details'

    # 主鍵
    id = Column(Integer, primary_key=True, autoincrement=True)

    # 外鍵關聯到主表
    article_menu_id = Column(Integer, ForeignKey('article_menus.id'), nullable=False)

    # API2 欄位對應
    article_id = Column(Integer, unique=True, nullable=False, index=True)  # articleId
    article_title = Column(String(500), nullable=False)  # articleTitle
    article_content = Column(Text)  # articleContent (完整版本)
    article_cover = Column(String(1000))  # articleCover
    article_type = Column(Integer)  # articleType
    article_type_name = Column(String(100))  # articleTypeName
    content_cover = Column(String(1000))  # contentCover
    game_id = Column(String(50))  # gameId
    start_time = Column(DateTime)  # startTime

    # 系統欄位
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # 關聯關係
    article_menu = relationship("ArticleMenu", back_populates="article_detail")

    def __repr__(self):
        return f"<ArticleDetail(article_id={self.article_id}, title='{self.article_title}')>"

    def to_dict(self):
        """轉換為字典格式"""
        return {
            'id': self.id,
            'article_menu_id': self.article_menu_id,
            'article_id': self.article_id,
            'article_title': self.article_title,
            'article_content': self.article_content,
            'article_cover': self.article_cover,
            'article_type': self.article_type,
            'article_type_name': self.article_type_name,
            'content_cover': self.content_cover,
            'game_id': self.game_id,
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

class SystemState(Base):
    """系統狀態表 - 記錄最後抓取時間等資訊"""
    __tablename__ = 'system_states'

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(100), unique=True, nullable=False, index=True)  # 狀態鍵值
    value = Column(Text)  # 狀態值
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<SystemState(key='{self.key}', value='{self.value}')>"

class FBPost(Base):
    """Facebook 貼文主表"""
    __tablename__ = 'fb_posts'

    id = Column(Integer, primary_key=True, autoincrement=True)
    post_id = Column(String(100))  # fb_20241201_123456_1
    url = Column(String(1000))  # 貼文 URL (數字 ID 格式)
    pfbid_url = Column(String(1000))  # PFBID 格式 URL
    text = Column(Text)  # 純文字內容
    text_md = Column(Text)  # Discord Markdown 格式文字
    content_hash = Column(String(256), unique=True, nullable=False, index=True)  # 内容hash，用于判断文章内容，唯一，不可为空
    timestamp = Column(DateTime)  # 貼文時間戳
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # 關聯：一對多圖片
    images = relationship("FBImage", back_populates="post", cascade="all, delete-orphan")

    # 唯一約束：確保 url 和 pfbid_url 組合不重複
    __table_args__ = (
        UniqueConstraint('url', 'pfbid_url', name='unique_fb_urls'),
    )

    def __repr__(self):
        return f"<FBPost(post_id='{self.post_id}', url='{self.url}')>"

class FBImage(Base):
    """Facebook 貼文圖片子表"""
    __tablename__ = 'fb_images'

    id = Column(Integer, primary_key=True, autoincrement=True)
    fb_post_id = Column(Integer, ForeignKey('fb_posts.id'), nullable=False)  # 使用主表 id 作為外鍵
    image_url = Column(String(1000), nullable=False)  # 圖片 URL
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # 關聯
    post = relationship("FBPost", back_populates="images")

    # 複合唯一約束：同貼文不重複，同 URL 可重複但不同貼文
    __table_args__ = (
        UniqueConstraint('fb_post_id', 'image_url', name='unique_post_image'),
    )

    def __repr__(self):
        return f"<FBImage(fb_post_id={self.fb_post_id}, image_url='{self.image_url}')>"

# 建立資料庫引擎
engine = create_engine(DATABASE_CONFIG["url"], echo=False)

# 建立 Session
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db_session():
    """取得資料庫 session"""
    session = SessionLocal()
    try:
        return session
    except Exception:
        session.close()
        raise

def create_tables():
    """建立所有資料表"""
    Base.metadata.create_all(bind=engine)
