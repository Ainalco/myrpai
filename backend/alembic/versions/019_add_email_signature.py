"""add_email_signature

Revision ID: 019_add_email_signature
Revises: 018_add_ai_models
Create Date: 2026-03-06

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '019_add_email_signature'
down_revision = '018_add_ai_models'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('email_signature', sa.Text(), nullable=True))
    op.add_column('users', sa.Column('email_signature_enabled', sa.Boolean(), server_default='true', nullable=False))


def downgrade() -> None:
    op.drop_column('users', 'email_signature_enabled')
    op.drop_column('users', 'email_signature')
