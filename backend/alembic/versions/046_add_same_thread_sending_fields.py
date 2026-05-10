"""Add same-thread sending fields to email_queue.

Revision ID: 046_same_thread_fields
Revises: 045_add_dnc_org_fields
Create Date: 2026-04-30
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "046_same_thread_fields"
down_revision = "045_add_dnc_org_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("email_queue", sa.Column("message_id_header", sa.String(), nullable=True))
    op.add_column("email_queue", sa.Column("thread_parent_component_id", sa.Integer(), nullable=True))
    op.add_column("email_queue", sa.Column("thread_parent_queue_id", sa.Integer(), nullable=True))
    op.add_column("email_queue", sa.Column("thread_fallback_reason", sa.String(), nullable=True))

    op.create_foreign_key(
        "fk_email_queue_thread_parent_component_id",
        "email_queue",
        "components",
        ["thread_parent_component_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_email_queue_thread_parent_queue_id",
        "email_queue",
        "email_queue",
        ["thread_parent_queue_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_email_queue_thread_parent_queue_id", "email_queue", type_="foreignkey")
    op.drop_constraint("fk_email_queue_thread_parent_component_id", "email_queue", type_="foreignkey")
    op.drop_column("email_queue", "thread_fallback_reason")
    op.drop_column("email_queue", "thread_parent_queue_id")
    op.drop_column("email_queue", "thread_parent_component_id")
    op.drop_column("email_queue", "message_id_header")
