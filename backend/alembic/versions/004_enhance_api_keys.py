"""Enhance api_keys table with constraints and indexes

Revision ID: 004_enhance_api_keys
Revises: 003_add_universal_rules
Create Date: 2025-10-12 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '004_enhance_api_keys'
down_revision = '003_add_universal_rules'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Add constraints and indexes to api_keys table for:
    - Unique constraint on (user_id, service_name) to prevent duplicate keys
    - Index on (user_id, service_name, is_active) for fast lookups
    - Add updated_at column for tracking key updates
    - Add last_used_at column for tracking usage (optional)
    """

    # Add updated_at column
    op.add_column('api_keys', sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True))

    # Add last_used_at column for tracking when key was last used
    op.add_column('api_keys', sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True))

    # Create unique constraint on (user_id, service_name)
    # This ensures one user can only have one key per service
    op.create_unique_constraint(
        'uq_api_keys_user_service',
        'api_keys',
        ['user_id', 'service_name']
    )

    # Create composite index for fast lookups
    # This speeds up queries like: "Get active Fireflies key for user X"
    op.create_index(
        'ix_api_keys_user_service_active',
        'api_keys',
        ['user_id', 'service_name', 'is_active']
    )


def downgrade() -> None:
    """
    Remove the enhancements added in upgrade
    """

    # Drop index
    op.drop_index('ix_api_keys_user_service_active', table_name='api_keys')

    # Drop unique constraint
    op.drop_constraint('uq_api_keys_user_service', 'api_keys', type_='unique')

    # Drop columns
    op.drop_column('api_keys', 'last_used_at')
    op.drop_column('api_keys', 'updated_at')
