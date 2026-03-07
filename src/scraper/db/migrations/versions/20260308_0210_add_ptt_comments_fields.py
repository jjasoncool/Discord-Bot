"""add comments fields to ptt_posts

Revision ID: add_ptt_comments_20260308
Revises: 4f89a1b2
Create Date: 2026-03-08 02:10:00
"""

from alembic import op
import sqlalchemy as sa


revision = 'add_ptt_comments_20260308'
down_revision = '4f89a1b2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('ptt_posts', schema=None) as batch_op:
        batch_op.add_column(sa.Column('comments_json', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('comments_count', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('comments_hash', sa.String(length=256), nullable=True))
        batch_op.add_column(sa.Column('last_comment_sync_at', sa.DateTime(), nullable=True))
        batch_op.create_index('ix_ptt_posts_comments_hash', ['comments_hash'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('ptt_posts', schema=None) as batch_op:
        batch_op.drop_index('ix_ptt_posts_comments_hash')
        batch_op.drop_column('last_comment_sync_at')
        batch_op.drop_column('comments_hash')
        batch_op.drop_column('comments_count')
        batch_op.drop_column('comments_json')
