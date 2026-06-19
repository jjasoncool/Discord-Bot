"""add hardware_news table (HKEPC IT快訊 / 系統設備新知)

Revision ID: hkepc_hardware_news_20260619
Revises: add_ptt_comments_20260308
Create Date: 2026-06-19 00:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = 'hkepc_hardware_news_20260619'
down_revision = 'add_ptt_comments_20260308'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'hardware_news',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('hkepc_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=500), nullable=False),
        sa.Column('url', sa.String(length=1000), nullable=False),
        sa.Column('author', sa.String(length=100), nullable=True),
        sa.Column('introduction', sa.Text(), nullable=True),
        sa.Column('content', sa.Text(), nullable=True),
        sa.Column('images_json', sa.Text(), nullable=True),
        sa.Column('reference_url', sa.String(length=1000), nullable=True),
        sa.Column('tags', sa.String(length=500), nullable=True),
        sa.Column('comment_count', sa.Integer(), nullable=True),
        sa.Column('published_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('hkepc_id', name='uq_hardware_news_hkepc_id'),
    )
    op.create_index('ix_hardware_news_hkepc_id', 'hardware_news', ['hkepc_id'], unique=True)
    op.create_index('ix_hardware_news_published_at', 'hardware_news', ['published_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_hardware_news_published_at', table_name='hardware_news')
    op.drop_index('ix_hardware_news_hkepc_id', table_name='hardware_news')
    op.drop_table('hardware_news')
