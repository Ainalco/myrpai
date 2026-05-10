"""add_reason_and_token_tracking_columns

Revision ID: 014_reason_token_tracking
Revises: 013_pre_send_check_config
Create Date: 2026-02-24

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '014_reason_token_tracking'
down_revision = '013_pre_send_check_config'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # EmailQueue: AI reasoning columns
    op.add_column('email_queue', sa.Column('timing_reason', sa.Text(), nullable=True))
    op.add_column('email_queue', sa.Column('generation_reason', sa.Text(), nullable=True))

    # Execution: generation reason + token tracking
    op.add_column('executions', sa.Column('generation_reason', sa.Text(), nullable=True))
    op.add_column('executions', sa.Column('total_prompt_tokens', sa.Integer(), nullable=True))
    op.add_column('executions', sa.Column('total_completion_tokens', sa.Integer(), nullable=True))
    op.add_column('executions', sa.Column('total_tokens', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('executions', 'total_tokens')
    op.drop_column('executions', 'total_completion_tokens')
    op.drop_column('executions', 'total_prompt_tokens')
    op.drop_column('executions', 'generation_reason')
    op.drop_column('email_queue', 'generation_reason')
    op.drop_column('email_queue', 'timing_reason')
