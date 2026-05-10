"""Add contact system tables and columns

Revision ID: 027_add_contact_system
Revises: 026_add_locked_acorn_allocation
"""
from alembic import op
import sqlalchemy as sa

revision = "027_add_contact_system"
down_revision = "026_add_locked_acorn_allocation"
branch_labels = None
depends_on = None


def upgrade():
    # -------------------------------------------------------------------------
    # 1. contact_organizations
    # -------------------------------------------------------------------------
    op.create_table(
        'contact_organizations',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('domain', sa.String(), nullable=True),
        sa.Column('external_org_id', sa.String(), nullable=True),
        sa.Column('crm_provider', sa.String(), nullable=True),
        sa.Column('do_not_contact_propagation', sa.Boolean(), nullable=True, server_default='true'),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_contact_organizations_user_id', 'contact_organizations', ['user_id'])
    op.create_index('ix_contact_organizations_domain', 'contact_organizations', ['domain'])

    # -------------------------------------------------------------------------
    # 2. Add columns to contacts
    # -------------------------------------------------------------------------
    op.add_column('contacts', sa.Column('primary_email', sa.String(), nullable=True))
    op.add_column('contacts', sa.Column('contact_organization_id', sa.Integer(), nullable=True))
    op.add_column('contacts', sa.Column('external_person_id', sa.String(), nullable=True))
    op.add_column('contacts', sa.Column('crm_provider', sa.String(), nullable=True))
    op.add_column('contacts', sa.Column('status', sa.String(), nullable=True, server_default='active'))
    op.add_column('contacts', sa.Column('last_activity_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('contacts', sa.Column('last_activity_type', sa.String(), nullable=True))
    op.add_column('contacts', sa.Column('last_activity_direction', sa.String(), nullable=True))
    op.add_column('contacts', sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True))

    op.create_foreign_key(
        'fk_contacts_contact_organization_id',
        'contacts', 'contact_organizations',
        ['contact_organization_id'], ['id'],
        ondelete='SET NULL'
    )
    op.create_index('ix_contacts_status', 'contacts', ['status'])
    op.create_index('ix_contacts_contact_organization_id', 'contacts', ['contact_organization_id'])

    # Backfill primary_email from email
    op.execute("UPDATE contacts SET primary_email = email WHERE primary_email IS NULL")

    # -------------------------------------------------------------------------
    # 3. contact_emails
    # -------------------------------------------------------------------------
    op.create_table(
        'contact_emails',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('contact_id', sa.Integer(), sa.ForeignKey('contacts.id', ondelete='CASCADE'), nullable=False),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('is_primary', sa.Boolean(), nullable=True, server_default='false'),
        sa.Column('verified', sa.Boolean(), nullable=True, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('now()')),
    )
    op.create_index('ix_contact_emails_email', 'contact_emails', ['email'])
    op.create_index('ix_contact_emails_contact_id', 'contact_emails', ['contact_id'])

    # Backfill from existing contacts
    op.execute(
        "INSERT INTO contact_emails (contact_id, email, is_primary) "
        "SELECT id, email, true FROM contacts WHERE email IS NOT NULL"
    )

    # -------------------------------------------------------------------------
    # 4. contact_deals
    # -------------------------------------------------------------------------
    op.create_table(
        'contact_deals',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('contact_id', sa.Integer(), sa.ForeignKey('contacts.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('contact_organization_id', sa.Integer(), sa.ForeignKey('contact_organizations.id', ondelete='SET NULL'), nullable=True),
        sa.Column('external_deal_id', sa.String(), nullable=True),
        sa.Column('crm_provider', sa.String(), nullable=True),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=True, server_default='open'),
        sa.Column('stage_name', sa.String(), nullable=True),
        sa.Column('value', sa.Float(), nullable=True),
        sa.Column('expected_close_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('currency', sa.String(), nullable=True, server_default='USD'),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_contact_deals_contact_id', 'contact_deals', ['contact_id'])

    # -------------------------------------------------------------------------
    # 5. contact_stats
    # -------------------------------------------------------------------------
    op.create_table(
        'contact_stats',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('contact_id', sa.Integer(), sa.ForeignKey('contacts.id', ondelete='CASCADE'), nullable=False, unique=True),
        sa.Column('emails_sent', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('emails_received', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('reply_rate', sa.Float(), nullable=True, server_default='0'),
        sa.Column('meetings_count', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('active_sequences', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('open_deals', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('total_deal_value', sa.Float(), nullable=True, server_default='0'),
        sa.Column('last_computed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )

    # Backfill contact_stats for existing contacts
    op.execute(
        "INSERT INTO contact_stats (contact_id) "
        "SELECT id FROM contacts"
    )

    # -------------------------------------------------------------------------
    # 6. contact_pulse
    # -------------------------------------------------------------------------
    op.create_table(
        'contact_pulse',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('contact_id', sa.Integer(), sa.ForeignKey('contacts.id', ondelete='CASCADE'), nullable=False, unique=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('sentiment', sa.String(), nullable=True),
        sa.Column('engagement_level', sa.String(), nullable=True),
        sa.Column('intent', sa.String(), nullable=True),
        sa.Column('recommended_action', sa.String(), nullable=True),
        sa.Column('key_topics', sa.JSON(), nullable=True),
        sa.Column('key_objections', sa.JSON(), nullable=True),
        sa.Column('last_meeting_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('generated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )

    # -------------------------------------------------------------------------
    # 7. thread_digests
    # -------------------------------------------------------------------------
    op.create_table(
        'thread_digests',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('contact_id', sa.Integer(), sa.ForeignKey('contacts.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('thread_id', sa.String(), nullable=False),
        sa.Column('subject', sa.String(), nullable=True),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('sentiment', sa.String(), nullable=True),
        sa.Column('thread_status', sa.String(), nullable=True),
        sa.Column('message_count', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('last_message_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('participants', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_thread_digests_contact_id', 'thread_digests', ['contact_id'])
    op.create_index('ix_thread_digests_thread_id', 'thread_digests', ['thread_id'])

    # -------------------------------------------------------------------------
    # 8. meeting_history
    # -------------------------------------------------------------------------
    op.create_table(
        'meeting_history',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('contact_id', sa.Integer(), sa.ForeignKey('contacts.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('external_meeting_id', sa.String(), nullable=True),
        sa.Column('source', sa.String(), nullable=True),
        sa.Column('meeting_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('key_points', sa.JSON(), nullable=True),
        sa.Column('objections', sa.JSON(), nullable=True),
        sa.Column('buying_signals', sa.JSON(), nullable=True),
        sa.Column('deal_stage_at_time', sa.String(), nullable=True),
        sa.Column('duration_minutes', sa.Integer(), nullable=True),
        sa.Column('participants', sa.JSON(), nullable=True),
        sa.Column('raw_transcript_url', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_meeting_history_contact_id', 'meeting_history', ['contact_id'])

    # -------------------------------------------------------------------------
    # 9. sequence_runs
    # -------------------------------------------------------------------------
    op.create_table(
        'sequence_runs',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('contact_id', sa.Integer(), sa.ForeignKey('contacts.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('sequence_config_id', sa.Integer(), sa.ForeignKey('email_sequence_configs.id', ondelete='SET NULL'), nullable=True),
        sa.Column('status', sa.String(), nullable=True, server_default='active'),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('current_step', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('total_steps', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_sequence_runs_contact_id', 'sequence_runs', ['contact_id'])

    # -------------------------------------------------------------------------
    # 10. Add columns to contact_activities
    # -------------------------------------------------------------------------
    op.add_column('contact_activities', sa.Column('contact_organization_id', sa.Integer(), nullable=True))
    op.add_column('contact_activities', sa.Column('deal_id', sa.Integer(), nullable=True))
    op.add_column('contact_activities', sa.Column('direction', sa.String(), nullable=True))
    op.add_column('contact_activities', sa.Column('source_type', sa.String(), nullable=True))
    op.add_column('contact_activities', sa.Column('source_id', sa.String(), nullable=True))
    op.add_column('contact_activities', sa.Column('thread_id', sa.String(), nullable=True))
    op.add_column('contact_activities', sa.Column('subject', sa.String(), nullable=True))
    op.add_column('contact_activities', sa.Column('summary', sa.Text(), nullable=True))
    op.add_column('contact_activities', sa.Column('raw_content', sa.Text(), nullable=True))
    op.add_column('contact_activities', sa.Column('metadata_json', sa.JSON(), nullable=True))
    op.add_column('contact_activities', sa.Column('activity_at', sa.DateTime(timezone=True), nullable=True))

    op.create_foreign_key(
        'fk_contact_activities_contact_organization_id',
        'contact_activities', 'contact_organizations',
        ['contact_organization_id'], ['id'],
        ondelete='SET NULL'
    )
    op.create_foreign_key(
        'fk_contact_activities_deal_id',
        'contact_activities', 'contact_deals',
        ['deal_id'], ['id'],
        ondelete='SET NULL'
    )

    # Partial unique index on (user_id, source_type, source_id) WHERE source_id IS NOT NULL
    op.execute(
        "CREATE UNIQUE INDEX uq_activity_source "
        "ON contact_activities (user_id, source_type, source_id) "
        "WHERE source_id IS NOT NULL"
    )

    # Backfill activity_at from occurred_at
    op.execute("UPDATE contact_activities SET activity_at = occurred_at WHERE activity_at IS NULL")

    # -------------------------------------------------------------------------
    # 11. Add columns to email_queue
    # -------------------------------------------------------------------------
    op.add_column('email_queue', sa.Column('thread_id', sa.String(), nullable=True))
    op.add_column('email_queue', sa.Column('deal_id', sa.Integer(), nullable=True))
    op.add_column('email_queue', sa.Column('sequence_run_id', sa.Integer(), nullable=True))

    op.create_foreign_key(
        'fk_email_queue_deal_id',
        'email_queue', 'contact_deals',
        ['deal_id'], ['id'],
        ondelete='SET NULL'
    )
    op.create_foreign_key(
        'fk_email_queue_sequence_run_id',
        'email_queue', 'sequence_runs',
        ['sequence_run_id'], ['id'],
        ondelete='SET NULL'
    )


def downgrade():
    # -------------------------------------------------------------------------
    # Reverse step 11: email_queue columns
    # -------------------------------------------------------------------------
    op.drop_constraint('fk_email_queue_sequence_run_id', 'email_queue', type_='foreignkey')
    op.drop_constraint('fk_email_queue_deal_id', 'email_queue', type_='foreignkey')
    op.drop_column('email_queue', 'sequence_run_id')
    op.drop_column('email_queue', 'deal_id')
    op.drop_column('email_queue', 'thread_id')

    # -------------------------------------------------------------------------
    # Reverse step 10: contact_activities columns
    # -------------------------------------------------------------------------
    op.execute("DROP INDEX IF EXISTS uq_activity_source")
    op.drop_constraint('fk_contact_activities_deal_id', 'contact_activities', type_='foreignkey')
    op.drop_constraint('fk_contact_activities_contact_organization_id', 'contact_activities', type_='foreignkey')
    op.drop_column('contact_activities', 'activity_at')
    op.drop_column('contact_activities', 'metadata_json')
    op.drop_column('contact_activities', 'raw_content')
    op.drop_column('contact_activities', 'summary')
    op.drop_column('contact_activities', 'subject')
    op.drop_column('contact_activities', 'thread_id')
    op.drop_column('contact_activities', 'source_id')
    op.drop_column('contact_activities', 'source_type')
    op.drop_column('contact_activities', 'direction')
    op.drop_column('contact_activities', 'deal_id')
    op.drop_column('contact_activities', 'contact_organization_id')

    # -------------------------------------------------------------------------
    # Reverse step 9: sequence_runs
    # -------------------------------------------------------------------------
    op.drop_index('ix_sequence_runs_contact_id', table_name='sequence_runs')
    op.drop_table('sequence_runs')

    # -------------------------------------------------------------------------
    # Reverse step 8: meeting_history
    # -------------------------------------------------------------------------
    op.drop_index('ix_meeting_history_contact_id', table_name='meeting_history')
    op.drop_table('meeting_history')

    # -------------------------------------------------------------------------
    # Reverse step 7: thread_digests
    # -------------------------------------------------------------------------
    op.drop_index('ix_thread_digests_thread_id', table_name='thread_digests')
    op.drop_index('ix_thread_digests_contact_id', table_name='thread_digests')
    op.drop_table('thread_digests')

    # -------------------------------------------------------------------------
    # Reverse step 6: contact_pulse
    # -------------------------------------------------------------------------
    op.drop_table('contact_pulse')

    # -------------------------------------------------------------------------
    # Reverse step 5: contact_stats
    # -------------------------------------------------------------------------
    op.drop_table('contact_stats')

    # -------------------------------------------------------------------------
    # Reverse step 4: contact_deals
    # -------------------------------------------------------------------------
    op.drop_index('ix_contact_deals_contact_id', table_name='contact_deals')
    op.drop_table('contact_deals')

    # -------------------------------------------------------------------------
    # Reverse step 3: contact_emails
    # -------------------------------------------------------------------------
    op.drop_index('ix_contact_emails_contact_id', table_name='contact_emails')
    op.drop_index('ix_contact_emails_email', table_name='contact_emails')
    op.drop_table('contact_emails')

    # -------------------------------------------------------------------------
    # Reverse step 2: contacts columns
    # -------------------------------------------------------------------------
    op.drop_index('ix_contacts_contact_organization_id', table_name='contacts')
    op.drop_index('ix_contacts_status', table_name='contacts')
    op.drop_constraint('fk_contacts_contact_organization_id', 'contacts', type_='foreignkey')
    op.drop_column('contacts', 'deleted_at')
    op.drop_column('contacts', 'last_activity_direction')
    op.drop_column('contacts', 'last_activity_type')
    op.drop_column('contacts', 'last_activity_at')
    op.drop_column('contacts', 'status')
    op.drop_column('contacts', 'crm_provider')
    op.drop_column('contacts', 'external_person_id')
    op.drop_column('contacts', 'contact_organization_id')
    op.drop_column('contacts', 'primary_email')

    # -------------------------------------------------------------------------
    # Reverse step 1: contact_organizations
    # -------------------------------------------------------------------------
    op.drop_index('ix_contact_organizations_domain', table_name='contact_organizations')
    op.drop_index('ix_contact_organizations_user_id', table_name='contact_organizations')
    op.drop_table('contact_organizations')
