"""${message}

資料庫遷移檔案 - 自動生成
專案：爬蟲系統
作者：系統自動生成

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

此檔案包含：
- upgrade(): 升級資料庫結構的操作
- downgrade(): 回滾到上一版本的操作

注意：請勿手動修改版本識別資訊
"""
from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

# revision identifiers, used by Alembic.
revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade() -> None:
    """升級資料庫結構

    此函式包含將資料庫從上一版本升級到當前版本的所有操作
    如：建立表格、新增欄位、建立索引等
    """
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    """回滾資料庫結構

    此函式包含將資料庫從當前版本回滾到上一版本的所有操作
    如：刪除表格、移除欄位、刪除索引等
    注意：回滾操作可能會導致資料遺失
    """
    ${downgrades if downgrades else "pass"}
