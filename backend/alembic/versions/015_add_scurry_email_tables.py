"""add_scurry_email_tables

Revision ID: 015_scurry_email_tables
Revises: 014_reason_token_tracking
Create Date: 2026-03-02

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '015_scurry_email_tables'
down_revision = '014_reason_token_tracking'
branch_labels = None
depends_on = None


def upgrade():
    # Scurry Users (mapped from auth system)
    op.create_table('scurry_users',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('external_user_id', sa.Integer(), nullable=False, unique=True),
        sa.Column('username', sa.String(255), nullable=True),
        sa.Column('email', sa.String(255), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.TIMESTAMP(), nullable=True),
    )
    op.create_index('ix_scurry_users_external_user_id', 'scurry_users', ['external_user_id'])

    # OAuth State Tokens (CSRF protection during OAuth flow)
    op.create_table('scurry_oauth_states',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('state_token', sa.String(64), nullable=False, unique=True),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('expires_at', sa.TIMESTAMP(), nullable=False),
    )
    op.create_index('ix_scurry_oauth_states_state_token', 'scurry_oauth_states', ['state_token'])
    op.create_index('ix_scurry_oauth_states_expires_at', 'scurry_oauth_states', ['expires_at'])

    # Gmail Email Accounts
    op.create_table('scurry_email_accounts',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('provider', sa.String(50), nullable=False, server_default='gmail'),
        sa.Column('email_address', sa.String(255), nullable=False),
        sa.Column('display_name', sa.String(255), nullable=True),
        sa.Column('access_token', sa.Text(), nullable=False),
        sa.Column('refresh_token', sa.Text(), nullable=True),
        sa.Column('token_expires_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('scopes', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='true'),
        sa.Column('last_sync_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('sync_error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.TIMESTAMP(), nullable=True),
        sa.UniqueConstraint('user_id', 'email_address', name='uq_scurry_email_accounts_user_email'),
    )
    op.create_index('ix_scurry_email_accounts_user_id', 'scurry_email_accounts', ['user_id'])
    op.create_index('ix_scurry_email_accounts_email', 'scurry_email_accounts', ['email_address'])
    op.create_index('ix_scurry_email_accounts_active', 'scurry_email_accounts', ['is_active'])

    # Gmail Sent Emails
    op.create_table('scurry_sent_emails',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.Column('recipient_email', sa.String(255), nullable=False),
        sa.Column('recipient_name', sa.String(255), nullable=True),
        sa.Column('cc', sa.JSON(), nullable=True),
        sa.Column('bcc', sa.JSON(), nullable=True),
        sa.Column('subject', sa.String(1000), nullable=False),
        sa.Column('body_html', sa.Text(), nullable=False),
        sa.Column('body_text', sa.Text(), nullable=True),
        sa.Column('gmail_message_id', sa.String(255), nullable=True),
        sa.Column('gmail_thread_id', sa.String(255), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('opens', sa.Integer(), server_default='0'),
        sa.Column('clicks', sa.Integer(), server_default='0'),
        sa.Column('first_opened_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('last_opened_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('first_clicked_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('last_clicked_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('sent_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.CheckConstraint("status IN ('pending', 'sent', 'failed')", name='ck_scurry_sent_emails_status'),
    )
    op.create_index('ix_scurry_sent_emails_user_id', 'scurry_sent_emails', ['user_id'])
    op.create_index('ix_scurry_sent_emails_account_id', 'scurry_sent_emails', ['account_id'])
    op.create_index('ix_scurry_sent_emails_status', 'scurry_sent_emails', ['status'])
    op.create_index('ix_scurry_sent_emails_recipient', 'scurry_sent_emails', ['recipient_email'])
    op.create_index('ix_scurry_sent_emails_sent_at', 'scurry_sent_emails', ['sent_at'])

    # Gmail Email Tracking Events
    op.create_table('scurry_email_tracking',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('email_id', sa.Integer(), sa.ForeignKey('scurry_sent_emails.id', ondelete='CASCADE'), nullable=False),
        sa.Column('event_type', sa.String(20), nullable=False),
        sa.Column('url', sa.Text(), nullable=True),
        sa.Column('ip_address', sa.String(45), nullable=True),
        sa.Column('user_agent', sa.Text(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.CheckConstraint("event_type IN ('open', 'click')", name='ck_scurry_email_tracking_type'),
    )
    op.create_index('ix_scurry_email_tracking_email_id', 'scurry_email_tracking', ['email_id'])
    op.create_index('ix_scurry_email_tracking_type', 'scurry_email_tracking', ['event_type'])

    # Outlook Accounts
    op.create_table('scurry_outlook_accounts',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('email_address', sa.String(255), nullable=False),
        sa.Column('display_name', sa.String(255), nullable=True),
        sa.Column('microsoft_user_id', sa.String(255), nullable=True),
        sa.Column('access_token', sa.Text(), nullable=False),
        sa.Column('refresh_token', sa.Text(), nullable=True),
        sa.Column('token_expires_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='true'),
        sa.Column('created_at', sa.TIMESTAMP(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.TIMESTAMP(), nullable=True),
        sa.UniqueConstraint('user_id', 'email_address', name='uq_scurry_outlook_accounts_user_email'),
    )
    op.create_index('ix_scurry_outlook_accounts_user_id', 'scurry_outlook_accounts', ['user_id'])
    op.create_index('ix_scurry_outlook_accounts_email', 'scurry_outlook_accounts', ['email_address'])

    # Outlook Sent Emails
    op.create_table('scurry_outlook_sent_emails',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.Column('recipient_email', sa.String(255), nullable=False),
        sa.Column('recipient_name', sa.String(255), nullable=True),
        sa.Column('cc', sa.JSON(), nullable=True),
        sa.Column('bcc', sa.JSON(), nullable=True),
        sa.Column('subject', sa.String(1000), nullable=False),
        sa.Column('body_html', sa.Text(), nullable=False),
        sa.Column('body_text', sa.Text(), nullable=True),
        sa.Column('outlook_message_id', sa.String(255), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('opens', sa.Integer(), server_default='0'),
        sa.Column('clicks', sa.Integer(), server_default='0'),
        sa.Column('first_opened_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('last_opened_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('first_clicked_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('last_clicked_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('sent_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.CheckConstraint("status IN ('pending', 'sent', 'failed')", name='ck_scurry_outlook_sent_status'),
    )
    op.create_index('ix_scurry_outlook_sent_user_id', 'scurry_outlook_sent_emails', ['user_id'])
    op.create_index('ix_scurry_outlook_sent_account_id', 'scurry_outlook_sent_emails', ['account_id'])
    op.create_index('ix_scurry_outlook_sent_status', 'scurry_outlook_sent_emails', ['status'])

    # Outlook Tracking Events
    op.create_table('scurry_outlook_tracking',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('email_id', sa.Integer(), sa.ForeignKey('scurry_outlook_sent_emails.id', ondelete='CASCADE'), nullable=False),
        sa.Column('event_type', sa.String(20), nullable=False),
        sa.Column('url', sa.Text(), nullable=True),
        sa.Column('ip_address', sa.String(45), nullable=True),
        sa.Column('user_agent', sa.Text(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.CheckConstraint("event_type IN ('open', 'click')", name='ck_scurry_outlook_tracking_type'),
    )
    op.create_index('ix_scurry_outlook_tracking_email_id', 'scurry_outlook_tracking', ['email_id'])
    op.create_index('ix_scurry_outlook_tracking_type', 'scurry_outlook_tracking', ['event_type'])


def downgrade():
    op.drop_table('scurry_outlook_tracking')
    op.drop_table('scurry_outlook_sent_emails')
    op.drop_table('scurry_outlook_accounts')
    op.drop_table('scurry_email_tracking')
    op.drop_table('scurry_sent_emails')
    op.drop_table('scurry_email_accounts')
    op.drop_table('scurry_oauth_states')
    op.drop_table('scurry_users')
