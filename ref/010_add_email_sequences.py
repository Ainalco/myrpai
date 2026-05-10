"""add_email_sequences

Revision ID: 010_add_email_sequences
Revises: 009_extracted_variables
Create Date: 2025-12-27

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '010_add_email_sequences'
down_revision = '009_extracted_variables'  # Update this to your last migration
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create email_sequence_configs table
    op.create_table(
        'email_sequence_configs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('workflow_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False, server_default='Follow-up Sequence'),
        sa.Column('is_enabled', sa.Boolean(), nullable=True, server_default='true'),
        sa.Column('ai_optimize_timing', sa.Boolean(), nullable=True, server_default='false'),
        sa.Column('ai_optimization_prompt', sa.Text(), nullable=True),
        sa.Column('send_method', sa.String(), nullable=True, server_default='smtp'),
        sa.Column('timezone', sa.String(), nullable=True, server_default='America/New_York'),
        sa.Column('business_hours_only', sa.Boolean(), nullable=True, server_default='true'),
        sa.Column('business_hours_start', sa.String(), nullable=True, server_default='09:00'),
        sa.Column('business_hours_end', sa.String(), nullable=True, server_default='17:00'),
        sa.Column('business_days', sa.JSON(), nullable=True),
        sa.Column('skip_conditions', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['workflow_id'], ['workflows.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('workflow_id')
    )
    op.create_index(op.f('ix_email_sequence_configs_id'), 'email_sequence_configs', ['id'], unique=False)
    op.create_index('ix_email_sequence_configs_workflow_id', 'email_sequence_configs', ['workflow_id'], unique=True)

    # Create sequence_emails table
    op.create_table(
        'sequence_emails',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('sequence_config_id', sa.Integer(), nullable=False),
        sa.Column('order', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('name', sa.String(), nullable=True, server_default='Email'),
        sa.Column('subject', sa.String(), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('timing_mode', sa.String(), nullable=True, server_default='relative'),
        sa.Column('delay_value', sa.Integer(), nullable=True, server_default='1'),
        sa.Column('delay_unit', sa.String(), nullable=True, server_default='days'),
        sa.Column('specific_day', sa.String(), nullable=True),
        sa.Column('specific_time', sa.String(), nullable=True),
        sa.Column('ai_decides_timing', sa.Boolean(), nullable=True, server_default='false'),
        sa.Column('ai_timing_context', sa.Text(), nullable=True),
        sa.Column('is_enabled', sa.Boolean(), nullable=True, server_default='true'),
        sa.Column('generation_prompt', sa.Text(), nullable=True),
        sa.Column('use_variables', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['sequence_config_id'], ['email_sequence_configs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_sequence_emails_id'), 'sequence_emails', ['id'], unique=False)
    op.create_index('ix_sequence_emails_config_id', 'sequence_emails', ['sequence_config_id'], unique=False)
    op.create_index('ix_sequence_emails_order', 'sequence_emails', ['order'], unique=False)

    # Create scheduled_sequence_emails table
    op.create_table(
        'scheduled_sequence_emails',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('sequence_config_id', sa.Integer(), nullable=True),
        sa.Column('sequence_email_id', sa.Integer(), nullable=True),
        sa.Column('execution_id', sa.Integer(), nullable=True),
        sa.Column('email_queue_id', sa.Integer(), nullable=True),
        sa.Column('recipient_email', sa.String(), nullable=False),
        sa.Column('recipient_name', sa.String(), nullable=True),
        sa.Column('status', sa.String(), nullable=True, server_default='scheduled'),
        sa.Column('skip_reason', sa.Text(), nullable=True),
        sa.Column('scheduled_for', sa.DateTime(timezone=True), nullable=True),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('ai_decided_timing', sa.Boolean(), nullable=True, server_default='false'),
        sa.Column('ai_timing_reasoning', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['sequence_config_id'], ['email_sequence_configs.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['sequence_email_id'], ['sequence_emails.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['execution_id'], ['executions.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['email_queue_id'], ['email_queue.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_scheduled_sequence_emails_id'), 'scheduled_sequence_emails', ['id'], unique=False)
    op.create_index('ix_scheduled_sequence_emails_status', 'scheduled_sequence_emails', ['status'], unique=False)
    op.create_index('ix_scheduled_sequence_emails_scheduled_for', 'scheduled_sequence_emails', ['scheduled_for'], unique=False)


def downgrade() -> None:
    # Drop tables in reverse order
    op.drop_index('ix_scheduled_sequence_emails_scheduled_for', table_name='scheduled_sequence_emails')
    op.drop_index('ix_scheduled_sequence_emails_status', table_name='scheduled_sequence_emails')
    op.drop_index(op.f('ix_scheduled_sequence_emails_id'), table_name='scheduled_sequence_emails')
    op.drop_table('scheduled_sequence_emails')

    op.drop_index('ix_sequence_emails_order', table_name='sequence_emails')
    op.drop_index('ix_sequence_emails_config_id', table_name='sequence_emails')
    op.drop_index(op.f('ix_sequence_emails_id'), table_name='sequence_emails')
    op.drop_table('sequence_emails')

    op.drop_index('ix_email_sequence_configs_workflow_id', table_name='email_sequence_configs')
    op.drop_index(op.f('ix_email_sequence_configs_id'), table_name='email_sequence_configs')
    op.drop_table('email_sequence_configs')
