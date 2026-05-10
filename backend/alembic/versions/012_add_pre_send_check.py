"""add_pre_send_check

Revision ID: 012_add_pre_send_check
Revises: 011_add_email_queue_enhancements
Create Date: 2026-02-16

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '012_add_pre_send_check'
down_revision = '011_add_email_queue_enhancements'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('email_queue', sa.Column('pre_send_check_field', sa.String(), nullable=True))
    op.add_column('email_queue', sa.Column('pre_send_check_operator', sa.String(), nullable=True))
    op.add_column('email_queue', sa.Column('pre_send_check_value', sa.String(), nullable=True))
    op.add_column('email_queue', sa.Column('pre_send_check_context', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('email_queue', 'pre_send_check_context')
    op.drop_column('email_queue', 'pre_send_check_value')
    op.drop_column('email_queue', 'pre_send_check_operator')
    op.drop_column('email_queue', 'pre_send_check_field')
