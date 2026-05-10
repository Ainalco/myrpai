"""Add resources table for account-level link and PDF library

Revision ID: 030_add_resources
Revises: 029_meeting_unique
"""
from alembic import op
import sqlalchemy as sa

revision = "030_add_resources"
down_revision = "029_meeting_unique"


def upgrade():
    op.create_table(
        "resources",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("account_id", sa.Integer, sa.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", sa.String(10), nullable=False),  # 'link' or 'file'
        sa.Column("label", sa.String(50), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("url", sa.Text, nullable=True),  # for links
        sa.Column("file_path", sa.Text, nullable=True),  # for files (internal storage path)
        sa.Column("file_size_bytes", sa.Integer, nullable=True),
        sa.Column("file_original_name", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("account_id", "type", "label", name="uq_resource_account_type_label"),
        sa.CheckConstraint("type IN ('link', 'file')", name="ck_resource_type"),
    )
    op.create_index("ix_resources_account_id", "resources", ["account_id"])


def downgrade():
    op.drop_index("ix_resources_account_id", "resources")
    op.drop_table("resources")
