"""add content_hash to fb_posts and make it unique"""

from alembic import op
import sqlalchemy as sa

revision = '4f89a1b2'
down_revision = '3d2f47875bdf'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('fb_posts', schema=None, recreate='always') as batch_op:
        # 删除post_id的unique index
        batch_op.drop_index('ix_fb_posts_post_id')
        # 修改post_id为可null
        batch_op.alter_column('post_id', nullable=True)
        # 添加content_hash欄位 (先可null以避開重建表問題)
        batch_op.add_column(sa.Column('content_hash', sa.String(length=256), nullable=True))
        # 创建content_hash的unique index
        batch_op.create_index('ix_fb_posts_content_hash', ['content_hash'], unique=True)


def downgrade() -> None:
    with op.batch_alter_table('fb_posts', schema=None, recreate='always') as batch_op:
        # 删除content_hash的unique index
        batch_op.drop_index('ix_fb_posts_content_hash')
        # 删除content_hash欄位
        batch_op.drop_column('content_hash')
        # 修改post_id为不可null
        batch_op.alter_column('post_id', nullable=False)
        # 恢复post_id的unique index
        batch_op.create_index('ix_fb_posts_post_id', ['post_id'], unique=True)
