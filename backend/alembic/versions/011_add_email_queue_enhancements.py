"""add_email_queue_enhancements

Revision ID: 011_add_email_queue_enhancements
Revises: 010_add_email_sequences
Create Date: 2025-01-07

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '011_add_email_queue_enhancements'
down_revision = '010_add_email_sequences'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create contacts table
    op.create_table(
        'contacts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=True),
        sa.Column('title', sa.String(), nullable=True),
        sa.Column('company', sa.String(), nullable=True),
        sa.Column('avatar_initials', sa.String(2), nullable=True),
        sa.Column('last_contacted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('contact_count', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_contacts_id'), 'contacts', ['id'], unique=False)
    op.create_index('ix_contacts_email', 'contacts', ['email'], unique=False)
    op.create_index('ix_contacts_user_id', 'contacts', ['user_id'], unique=False)

    # Create contact_activities table
    op.create_table(
        'contact_activities',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('contact_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('email_queue_id', sa.Integer(), nullable=True),
        sa.Column('activity_type', sa.String(), nullable=False),
        sa.Column('title', sa.String(), nullable=True),
        sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('is_new', sa.Boolean(), nullable=True, server_default='true'),
        sa.Column('extra_data', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['contact_id'], ['contacts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['email_queue_id'], ['email_queue.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_contact_activities_id'), 'contact_activities', ['id'], unique=False)
    op.create_index('ix_contact_activities_contact_id', 'contact_activities', ['contact_id'], unique=False)
    op.create_index('ix_contact_activities_occurred_at', 'contact_activities', ['occurred_at'], unique=False)

    # Add new columns to email_queue table
    # Contact linking
    op.add_column('email_queue', sa.Column('contact_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_email_queue_contact_id', 'email_queue', 'contacts', ['contact_id'], ['id'], ondelete='SET NULL')

    # Version tracking for edits
    op.add_column('email_queue', sa.Column('original_subject', sa.String(), nullable=True))
    op.add_column('email_queue', sa.Column('original_body', sa.Text(), nullable=True))
    op.add_column('email_queue', sa.Column('edit_source', sa.String(), nullable=True))
    op.add_column('email_queue', sa.Column('ai_edit_prompt', sa.Text(), nullable=True))

    # Approval workflow
    op.add_column('email_queue', sa.Column('approval_status', sa.String(), nullable=True, server_default='pending'))
    op.add_column('email_queue', sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True))

    # Sequence tracking
    op.add_column('email_queue', sa.Column('sequence_config_id', sa.Integer(), nullable=True))
    op.add_column('email_queue', sa.Column('sequence_email_id', sa.Integer(), nullable=True))
    op.add_column('email_queue', sa.Column('sequence_position', sa.Integer(), nullable=True))
    op.add_column('email_queue', sa.Column('sequence_total', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_email_queue_sequence_config_id', 'email_queue', 'email_sequence_configs', ['sequence_config_id'], ['id'], ondelete='SET NULL')
    op.create_foreign_key('fk_email_queue_sequence_email_id', 'email_queue', 'sequence_emails', ['sequence_email_id'], ['id'], ondelete='SET NULL')

    # Add indexes for common queries
    op.create_index('ix_email_queue_contact_id', 'email_queue', ['contact_id'], unique=False)
    op.create_index('ix_email_queue_approval_status', 'email_queue', ['approval_status'], unique=False)


def downgrade() -> None:
    # Drop indexes
    op.drop_index('ix_email_queue_approval_status', table_name='email_queue')
    op.drop_index('ix_email_queue_contact_id', table_name='email_queue')

    # Drop foreign keys
    op.drop_constraint('fk_email_queue_sequence_email_id', 'email_queue', type_='foreignkey')
    op.drop_constraint('fk_email_queue_sequence_config_id', 'email_queue', type_='foreignkey')
    op.drop_constraint('fk_email_queue_contact_id', 'email_queue', type_='foreignkey')

    # Drop columns from email_queue
    op.drop_column('email_queue', 'sequence_total')
    op.drop_column('email_queue', 'sequence_position')
    op.drop_column('email_queue', 'sequence_email_id')
    op.drop_column('email_queue', 'sequence_config_id')
    op.drop_column('email_queue', 'approved_at')
    op.drop_column('email_queue', 'approval_status')
    op.drop_column('email_queue', 'ai_edit_prompt')
    op.drop_column('email_queue', 'edit_source')
    op.drop_column('email_queue', 'original_body')
    op.drop_column('email_queue', 'original_subject')
    op.drop_column('email_queue', 'contact_id')

    # Drop contact_activities table
    op.drop_index('ix_contact_activities_occurred_at', table_name='contact_activities')
    op.drop_index('ix_contact_activities_contact_id', table_name='contact_activities')
    op.drop_index(op.f('ix_contact_activities_id'), table_name='contact_activities')
    op.drop_table('contact_activities')

    # Drop contacts table
    op.drop_index('ix_contacts_user_id', table_name='contacts')
    op.drop_index('ix_contacts_email', table_name='contacts')
    op.drop_index(op.f('ix_contacts_id'), table_name='contacts')
    op.drop_table('contacts')
