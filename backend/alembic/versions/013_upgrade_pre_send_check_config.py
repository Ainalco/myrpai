"""upgrade_pre_send_check_config

Revision ID: 013_pre_send_check_config
Revises: 012_add_pre_send_check
Create Date: 2026-02-21

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '013_pre_send_check_config'
down_revision = '012_add_pre_send_check'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('email_queue', sa.Column('pre_send_check_config', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('email_queue', 'pre_send_check_config')
