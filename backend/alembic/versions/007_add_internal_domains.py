"""add_internal_domains

Revision ID: 007_add_internal_domains
Revises: 006_add_email_queue
Create Date: 2025-10-21 09:15:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '007_add_internal_domains'
down_revision = '006_add_email_queue'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add internal_domains column to users table
    op.add_column('users', sa.Column('internal_domains', sa.Text(), nullable=True))


def downgrade() -> None:
    # Remove internal_domains column from users table
    op.drop_column('users', 'internal_domains')
