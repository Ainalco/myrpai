"""add_is_admin_to_users

Revision ID: 016_add_is_admin
Revises: 015_scurry_email_tables
Create Date: 2026-03-02

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '016_add_is_admin'
down_revision = '015_scurry_email_tables'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('is_admin', sa.Boolean(), nullable=True, server_default=sa.text('false')))


def downgrade() -> None:
    op.drop_column('users', 'is_admin')
