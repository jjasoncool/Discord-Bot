from sqlalchemy import create_engine, event, Column, Integer, String, Text, DateTime, Boolean, ForeignKey, UniqueConstraint
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


class PTTPost(Base):
    """PTT 貼文主表（單看板/關鍵字抓取）"""
    __tablename__ = 'ptt_posts'

    id = Column(Integer, primary_key=True, autoincrement=True)
    board = Column(String(100), nullable=False, index=True)
    article_id = Column(String(100), nullable=False, index=True)
    title = Column(String(500), nullable=False)
    author = Column(String(100))
    url = Column(String(1000), nullable=False)
    content = Column(Text)
    comments_json = Column(Text)
    comments_count = Column(Integer, default=0)
    comments_hash = Column(String(256), index=True)
    last_comment_sync_at = Column(DateTime)
    matched_keywords = Column(String(500))
    published_at = Column(DateTime, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint('board', 'article_id', name='uq_ptt_board_article_id'),
        UniqueConstraint('url', name='uq_ptt_url'),
    )

    def __repr__(self):
        return f"<PTTPost(board='{self.board}', article_id='{self.article_id}', title='{self.title[:30]}...')>"


class BahamutPost(Base):
    """巴哈姆特文章表（主文 + 回文共用，以 position 區分）"""
    __tablename__ = 'bahamut_posts'

    id = Column(Integer, primary_key=True, autoincrement=True)
    board_id = Column(String(50), nullable=False, index=True)          # bsn (e.g. "74934")
    post_id = Column(String(50), nullable=False, index=True)           # snA，thread ID
    sn = Column(String(50), nullable=False)                            # 單篇文章 ID（主文或回文）
    position = Column(Integer, nullable=False, default=1)              # 1=主文, >1=回文
    title = Column(String(500))
    category = Column(String(100))
    author_name = Column(String(200))
    author_id = Column(String(100), index=True)
    url = Column(String(1000))
    ip = Column(String(50))
    area = Column(String(20))
    published_at = Column(DateTime, index=True)
    content = Column(Text)
    content_hash = Column(String(64), index=True)                      # SHA256，偵測內容異動
    content_images_json = Column(Text)                                 # JSON array of image URLs
    comments_count = Column(Integer, default=0)
    gp_count = Column(Integer, default=0)                              # 文章 GP（推）數
    bp_count = Column(Integer, default=0)                              # 文章 BP（噓）數
    replies_count = Column(Integer, default=0)                         # 只在主文（position=1）有意義
    prev_title = Column(String(500))                                   # 上一版標題
    prev_content = Column(Text)                                        # 上一版內容
    prev_content_hash = Column(String(64))                             # 上一版 content_hash
    prev_updated_at = Column(DateTime)                                 # 上一版更新時間
    update_blocked = Column(Boolean, default=False)                    # 是否因異常縮水被阻擋
    update_block_reason = Column(String(200))                          # 阻擋原因
    is_deleted = Column(Boolean, default=False, index=True)            # 巴哈端已刪除
    raw_json = Column(Text)                                            # 完整 JSON 備份
    last_seen_at = Column(DateTime)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # 關聯
    comments = relationship("BahamutPostComment", back_populates="post", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint('board_id', 'sn', name='uq_bahamut_board_sn'),
    )

    def __repr__(self):
        return f"<BahamutPost(board_id='{self.board_id}', post_id='{self.post_id}', sn='{self.sn}', position={self.position})>"


class BahamutPostComment(Base):
    """巴哈姆特文章留言表"""
    __tablename__ = 'bahamut_post_comments'

    id = Column(Integer, primary_key=True, autoincrement=True)
    bahamut_post_id = Column(Integer, ForeignKey('bahamut_posts.id'), nullable=False, index=True)
    parent_sn = Column(String(50), nullable=False)                     # 留言所屬文章 block 的 sn
    comment_id = Column(String(50), nullable=False)                    # 巴哈留言 ID
    floor = Column(String(20))                                         # B1, B2...
    position = Column(Integer)                                         # 排序序號
    user_id = Column(String(100), index=True)
    user_name = Column(String(200))
    content = Column(Text)
    is_hot = Column(Boolean, default=False)
    gp_count = Column(Integer, default=0)                              # 留言 GP（推）數
    bp_count = Column(Integer, default=0)                              # 留言 BP（噓）數
    published_at = Column(DateTime)
    raw_text = Column(Text)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # 關聯
    post = relationship("BahamutPost", back_populates="comments")

    __table_args__ = (
        UniqueConstraint('parent_sn', 'comment_id', name='uq_bahamut_comment'),
    )

    def __repr__(self):
        return f"<BahamutPostComment(parent_sn='{self.parent_sn}', comment_id='{self.comment_id}')>"


class HardwareNews(Base):
    """HKEPC 系統設備 / 硬體新知（IT快訊等 tag）。

    去重鍵 = hkepc_id（HKEPC 文章數字 id），同一篇跨多個 tag 只會有一筆。
    images_json 只存來源圖片 URL 清單（不存圖檔）；發送時由 bot 暫存下載成
    Discord 附件，交給 Discord CDN 重新 host。
    """
    __tablename__ = 'hardware_news'

    id = Column(Integer, primary_key=True, autoincrement=True)  # 代理主鍵
    hkepc_id = Column(Integer, unique=True, nullable=False, index=True)  # HKEPC 文章數字 id（去重鍵）
    title = Column(String(500), nullable=False)
    url = Column(String(1000), nullable=False)
    author = Column(String(100))
    introduction = Column(Text)        # 列表頁摘要
    content = Column(Text)             # 內頁全文（markdown）
    images_json = Column(Text)         # JSON 來源圖片 URL 清單（不存圖檔）
    reference_url = Column(String(1000))  # 內文的外部參考連結
    tags = Column(String(500))         # 文章 tag（多 tag 聯集，逗號分隔）
    comment_count = Column(Integer, default=0)
    published_at = Column(DateTime, index=True)  # 來源日期
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<HardwareNews(hkepc_id={self.hkepc_id}, title='{(self.title or '')[:20]}')>"


# 建立資料庫引擎
engine = create_engine(
    DATABASE_CONFIG["url"],
    echo=False,
    connect_args={"timeout": 30},
)


@event.listens_for(engine, "connect")
def _set_sqlite_wal(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()

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
