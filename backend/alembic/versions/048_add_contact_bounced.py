"""add contact bounced flag

Revision ID: 048_add_contact_bounced
Revises: 047_sender_identity
Create Date: 2026-05-05
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = '048_add_contact_bounced'
down_revision = '047_sender_identity'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column(
        "contacts",
        sa.Column("bounced", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade():
    op.drop_column("contacts", "bounced")