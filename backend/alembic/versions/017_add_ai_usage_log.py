"""add_ai_usage_log

Revision ID: 017_ai_usage_log
Revises: 016_add_is_admin
Create Date: 2026-03-02

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '017_ai_usage_log'
down_revision = '016_add_is_admin'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'ai_usage_log',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False, index=True),
        sa.Column('source', sa.String(), nullable=False, index=True),
        sa.Column('execution_id', sa.Integer(), sa.ForeignKey('executions.id'), nullable=True),
        sa.Column('component_id', sa.Integer(), sa.ForeignKey('components.id'), nullable=True),
        sa.Column('prompt_tokens', sa.Integer(), server_default='0'),
        sa.Column('completion_tokens', sa.Integer(), server_default='0'),
        sa.Column('total_tokens', sa.Integer(), server_default='0'),
        sa.Column('ai_model', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table('ai_usage_log')
