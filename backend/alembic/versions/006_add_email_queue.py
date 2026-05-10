"""add_email_queue

Revision ID: 006_add_email_queue
Revises: 005_add_smtp_settings
Create Date: 2025-10-21 04:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '006_add_email_queue'
down_revision = '005_add_smtp_settings'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create email_queue table
    op.create_table(
        'email_queue',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('workflow_id', sa.Integer(), nullable=True),
        sa.Column('execution_id', sa.Integer(), nullable=True),
        sa.Column('component_id', sa.Integer(), nullable=True),
        sa.Column('recipient_email', sa.String(), nullable=False),
        sa.Column('recipient_name', sa.String(), nullable=True),
        sa.Column('subject', sa.String(), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('cc', sa.JSON(), nullable=True),
        sa.Column('bcc', sa.JSON(), nullable=True),
        sa.Column('scheduled_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('status', sa.String(), nullable=True, server_default='pending'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('retry_count', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('max_retries', sa.Integer(), nullable=True, server_default='3'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['workflow_id'], ['workflows.id'], ),
        sa.ForeignKeyConstraint(['execution_id'], ['executions.id'], ),
        sa.ForeignKeyConstraint(['component_id'], ['components.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_email_queue_id'), 'email_queue', ['id'], unique=False)
    op.create_index('ix_email_queue_status', 'email_queue', ['status'], unique=False)
    op.create_index('ix_email_queue_scheduled_at', 'email_queue', ['scheduled_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_email_queue_scheduled_at', table_name='email_queue')
    op.drop_index('ix_email_queue_status', table_name='email_queue')
    op.drop_index(op.f('ix_email_queue_id'), table_name='email_queue')
    op.drop_table('email_queue')
