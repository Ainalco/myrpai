"""Add sender identity fields to email_queue.

Revision ID: 047_sender_identity
Revises: 046_same_thread_fields
Create Date: 2026-04-26
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "047_sender_identity"
down_revision = "046_same_thread_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("email_queue", sa.Column("sender_provider", sa.String(), nullable=True))
    op.add_column("email_queue", sa.Column("sender_account_email", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("email_queue", "sender_account_email")
    op.drop_column("email_queue", "sender_provider")
