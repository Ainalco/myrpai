"""Add billable_cost column to ai_usage_log

Stores the baseline USD cost we charge users (as if no Anthropic prompt caching),
separate from `cost` which holds the actual cost to us after cache tier pricing.

Revision ID: 032_billable_cost
Revises: 031_cache_tokens
"""
from alembic import op
import sqlalchemy as sa

revision = "032_billable_cost"
down_revision = "031_cache_tokens"


def upgrade():
    op.add_column("ai_usage_log", sa.Column("billable_cost", sa.Float(), server_default="0"))


def downgrade():
    op.drop_column("ai_usage_log", "billable_cost")
