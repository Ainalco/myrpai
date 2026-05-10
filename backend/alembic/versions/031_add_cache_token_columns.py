"""Add prompt cache token tracking columns to ai_usage_log

Revision ID: 031_cache_tokens
Revises: 030_add_resources
"""
from alembic import op
import sqlalchemy as sa

revision = "031_cache_tokens"
down_revision = "030_add_resources"


def upgrade():
    op.add_column("ai_usage_log", sa.Column("cache_creation_input_tokens", sa.Integer(), server_default="0"))
    op.add_column("ai_usage_log", sa.Column("cache_read_input_tokens", sa.Integer(), server_default="0"))


def downgrade():
    op.drop_column("ai_usage_log", "cache_read_input_tokens")
    op.drop_column("ai_usage_log", "cache_creation_input_tokens")
