"""Add task column to ai_usage_log

Revision ID: 024_add_task_to_ai_usage_log
Revises: 023_add_cost_to_ai_usage_log
"""
from alembic import op
import sqlalchemy as sa

revision = "024_add_task_to_ai_usage_log"
down_revision = "023_add_cost_to_ai_usage_log"


def upgrade():
    op.add_column("ai_usage_log", sa.Column("task", sa.String, nullable=True))


def downgrade():
    op.drop_column("ai_usage_log", "task")
