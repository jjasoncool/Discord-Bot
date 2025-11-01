"""add pfbid_url"""

from alembic import op
import sqlalchemy as sa

revision = '3d2f47875bdf'
down_revision = '015d8cb32801'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('fb_posts', schema=None, recreate='always') as batch_op:
        # 新增欄位
        batch_op.add_column(sa.Column('pfbid_url', sa.String(length=1000), nullable=True))
        # url 改 nullable
        batch_op.alter_column('url', nullable=True)
        # 刪除舊的 unique index (ix_fb_posts_url)
        batch_op.drop_index('ix_fb_posts_url')
        # 建立新 unique constraint
        batch_op.create_unique_constraint('unique_fb_urls', ['url', 'pfbid_url'])


def downgrade() -> None:
    with op.batch_alter_table('fb_posts', schema=None, recreate='always') as batch_op:
        # 刪除新 constraint
        batch_op.drop_constraint('unique_fb_urls', type_='unique')
        # 刪除欄位
        batch_op.drop_column('pfbid_url')
        # url 恢復 NOT NULL
        batch_op.alter_column('url', nullable=False)
        # 恢復舊 unique index
        batch_op.create_index('ix_fb_posts_url', ['url'], unique=True)
