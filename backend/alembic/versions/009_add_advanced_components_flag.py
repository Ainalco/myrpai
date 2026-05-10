"""add_advanced_components_flag

Revision ID: 009_add_advanced_components_flag
Revises: 008_add_cascade_deletes
Create Date: 2025-11-08 16:15:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '009_add_advanced_components_flag'
down_revision = '008_add_cascade_deletes'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add enable_advanced_components column to users table
    # Default to False (restricted) - users must be explicitly granted access
    op.add_column('users', sa.Column('enable_advanced_components', sa.Boolean(), nullable=False, server_default='false'))


def downgrade() -> None:
    # Remove enable_advanced_components column from users table
    op.drop_column('users', 'enable_advanced_components')
