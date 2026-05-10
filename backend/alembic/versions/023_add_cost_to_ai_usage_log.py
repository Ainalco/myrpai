"""Add cost column to ai_usage_log

Revision ID: 023_add_cost_to_ai_usage_log
Revises: 022_rename_sapling_to_seedling
"""
from alembic import op
import sqlalchemy as sa

revision = "023_add_cost_to_ai_usage_log"
down_revision = "022_rename_sapling_to_seedling"


def upgrade():
    op.add_column("ai_usage_log", sa.Column("cost", sa.Float, server_default="0", nullable=True))


def downgrade():
    op.drop_column("ai_usage_log", "cost")
