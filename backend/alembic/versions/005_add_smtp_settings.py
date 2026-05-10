"""add_smtp_settings

Revision ID: 720fb4a5f043
Revises: 004_enhance_api_keys
Create Date: 2025-10-21 00:22:21.009196

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '005_add_smtp_settings'
down_revision = '004_enhance_api_keys'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add SMTP configuration columns to users table
    op.add_column('users', sa.Column('smtp_host', sa.String(), nullable=True))
    op.add_column('users', sa.Column('smtp_port', sa.Integer(), nullable=True))
    op.add_column('users', sa.Column('smtp_username', sa.String(), nullable=True))
    op.add_column('users', sa.Column('smtp_password', sa.Text(), nullable=True))
    op.add_column('users', sa.Column('smtp_use_tls', sa.Boolean(), nullable=True, server_default='true'))
    op.add_column('users', sa.Column('smtp_from_email', sa.String(), nullable=True))
    op.add_column('users', sa.Column('smtp_from_name', sa.String(), nullable=True))


def downgrade() -> None:
    # Remove SMTP configuration columns from users table
    op.drop_column('users', 'smtp_from_name')
    op.drop_column('users', 'smtp_from_email')
    op.drop_column('users', 'smtp_use_tls')
    op.drop_column('users', 'smtp_password')
    op.drop_column('users', 'smtp_username')
    op.drop_column('users', 'smtp_port')
    op.drop_column('users', 'smtp_host')