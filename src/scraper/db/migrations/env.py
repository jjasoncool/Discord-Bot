"""
Alembic 環境設定檔 - 資料庫遷移系統的核心配置

這個檔案是 Alembic 的「大腦」，負責：
1. 連接我們的資料庫模型 (db.models.Base)
2. 提供兩種執行模式：離線（生成SQL）和線上（直接執行）
3. 協調模型定義與實際資料庫之間的同步

常用指令：
- alembic revision --autogenerate -m "描述" : 自動生成遷移檔案
- alembic upgrade head                      : 執行所有待執行的遷移
- alembic upgrade head --sql               : 只生成SQL不執行
- alembic history                          : 查看遷移歷史
- alembic downgrade -1                     : 回退到上一版本
"""
import os
import logging.config
from sqlalchemy import engine_from_config
from sqlalchemy import pool
from alembic import context

# 從 alembic.ini 讀取設定
config = context.config

# 動態設定資料庫連線 URL
# 優先使用環境變數，若無則使用預設的 SQLite
database_url = os.getenv(
    "DATABASE_URL",
    "sqlite:///./articles.db"  # 預設值
)
config.set_main_option("sqlalchemy.url", database_url)

# 設定日誌系統（如果 alembic.ini 中有 logging 設定）
if config.config_file_name is not None:
    logging.config.fileConfig(config.config_file_name, disable_existing_loggers=False)

# 設定 Alembic 的目標 metadata
# 這裡導入我們的資料庫模型，告訴 Alembic 要管理哪些表格
# target_metadata 包含了所有模型的定義：ArticleMenu, ArticleDetail, SystemState
from db.models import Base
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """離線模式執行遷移

    不連接到實際的資料庫，而是生成純文字的 SQL 腳本

    使用場景：
    - 預覽變更：想先看看會執行什麼 SQL (alembic upgrade head --sql)
    - 企業部署：生成 SQL 腳本交給 DBA 審查後手動執行
    - 無資料庫權限：在 CI/CD 中生成腳本，後續手動執行
    - 安全考量：不會意外修改資料庫

    執行方式：alembic upgrade head --sql > migration.sql
    """
    # 從 alembic.ini 讀取資料庫連接字串 (sqlite:///./articles.db)
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,                    # 資料庫 URL（但不實際連接）
        target_metadata=target_metadata,  # 我們的模型定義
        literal_binds=True,         # 重要！將 SQL 參數直接寫入，避免 ? 佔位符
        dialect_opts={"paramstyle": "named"},  # SQLite 的 SQL 方言設定
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """線上模式執行遷移

    直接連接到實際的資料庫並執行變更

    使用場景：
    - 開發環境：快速同步資料庫結構 (alembic upgrade head)
    - 自動化部署：CI/CD 流程中自動更新資料庫
    - 即時變更：立即將模型變更應用到資料庫

    風險：會直接修改資料庫，建議先在測試環境驗證
    執行方式：alembic upgrade head
    """
    # 從 alembic.ini 建立資料庫引擎
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,  # 不使用連接池，適合短期執行的遷移
    )

    # 建立實際的資料庫連接並執行遷移
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata  # 我們的模型定義
        )

        with context.begin_transaction():
            context.run_migrations()


# 根據執行模式選擇對應的函式
# - Offline：生成 SQL 腳本（安全，可預覽）
# - Online：直接執行變更（快速，有風險）
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
