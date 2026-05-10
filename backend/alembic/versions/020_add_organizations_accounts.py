"""add_organizations_accounts

Revision ID: 020_add_organizations_accounts
Revises: 019_add_email_signature
Create Date: 2026-03-10

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '020_add_organizations_accounts'
down_revision = '019_add_email_signature'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create enum types (idempotent — safe to re-run after partial failures)
    op.execute("DO $$ BEGIN CREATE TYPE plan_tier AS ENUM ('trialing', 'sapling', 'oak', 'redwood', 'ancient_forest'); EXCEPTION WHEN duplicate_object THEN NULL; END $$")
    op.execute("DO $$ BEGIN CREATE TYPE account_status AS ENUM ('trialing', 'active', 'past_due', 'suspended', 'cancelled'); EXCEPTION WHEN duplicate_object THEN NULL; END $$")
    op.execute("DO $$ BEGIN CREATE TYPE user_role AS ENUM ('owner', 'admin', 'member'); EXCEPTION WHEN duplicate_object THEN NULL; END $$")
    op.execute("DO $$ BEGIN CREATE TYPE acorn_transaction_type AS ENUM ('trial_credit', 'subscription_credit', 'purchase', 'usage', 'adjustment', 'refund'); EXCEPTION WHEN duplicate_object THEN NULL; END $$")

    # Create organizations table
    op.create_table('organizations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('slug', sa.String(255), nullable=False),
        sa.Column('domain', sa.String(255), nullable=True),
        sa.Column('logo_url', sa.String(500), nullable=True),
        sa.Column('settings', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_organizations_id'), 'organizations', ['id'], unique=False)
    op.create_index(op.f('ix_organizations_slug'), 'organizations', ['slug'], unique=True)

    # Create accounts table
    op.create_table('accounts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('org_id', sa.Integer(), nullable=False),
        sa.Column('paddle_customer_id', sa.String(255), nullable=True),
        sa.Column('paddle_subscription_id', sa.String(255), nullable=True),
        sa.Column('plan_tier', postgresql.ENUM('trialing', 'sapling', 'oak', 'redwood', 'ancient_forest', name='plan_tier', create_type=False), nullable=True),
        sa.Column('billing_cycle', sa.String(50), nullable=True),
        sa.Column('acorn_balance', sa.Float(), server_default='0', nullable=False),
        sa.Column('status', postgresql.ENUM('trialing', 'active', 'past_due', 'suspended', 'cancelled', name='account_status', create_type=False), nullable=True),
        sa.Column('trial_ends_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('current_period_ends_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('org_id')
    )
    op.create_index(op.f('ix_accounts_id'), 'accounts', ['id'], unique=False)

    # Create acorn_transactions table
    op.create_table('acorn_transactions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('type', postgresql.ENUM('trial_credit', 'subscription_credit', 'purchase', 'usage', 'adjustment', 'refund', name='acorn_transaction_type', create_type=False), nullable=False),
        sa.Column('amount', sa.Float(), nullable=False),
        sa.Column('balance_after', sa.Float(), nullable=False),
        sa.Column('description', sa.String(500), nullable=False),
        sa.Column('paddle_transaction_id', sa.String(255), nullable=True),
        sa.Column('metadata_json', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_acorn_transactions_id'), 'acorn_transactions', ['id'], unique=False)

    # Create system_config table
    op.create_table('system_config',
        sa.Column('key', sa.String(100), nullable=False),
        sa.Column('value', sa.Text(), nullable=False),
        sa.Column('description', sa.String(500), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('key')
    )

    # Create paddle_webhook_events table (idempotency tracking)
    op.create_table('paddle_webhook_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('event_id', sa.String(255), nullable=False),
        sa.Column('event_type', sa.String(100), nullable=False),
        sa.Column('raw_payload', sa.Text(), nullable=True),
        sa.Column('processed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_paddle_webhook_events_id'), 'paddle_webhook_events', ['id'], unique=False)
    op.create_index(op.f('ix_paddle_webhook_events_event_id'), 'paddle_webhook_events', ['event_id'], unique=True)

    # Add new columns to users table
    op.add_column('users', sa.Column('org_id', sa.Integer(), nullable=True))
    op.add_column('users', sa.Column('role', postgresql.ENUM('owner', 'admin', 'member', name='user_role', create_type=False), server_default='owner', nullable=False))
    op.add_column('users', sa.Column('is_superadmin', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('users', sa.Column('locked_acorn_balance', sa.Float(), nullable=True))
    op.add_column('users', sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key('fk_users_org_id', 'users', 'organizations', ['org_id'], ['id'], ondelete='CASCADE')

    # Data migration: For each existing user, create an Organization and Account, then set user.org_id
    # Also copy is_admin to is_superadmin
    op.execute("""
        DO $$
        DECLARE
            u RECORD;
            new_org_id INTEGER;
            org_name TEXT;
        BEGIN
            FOR u IN SELECT id, email, is_admin FROM users LOOP
                -- Derive org name from email domain
                org_name := split_part(u.email, '@', 2);

                -- Create organization
                INSERT INTO organizations (name, slug, created_at)
                VALUES (org_name, 'org-' || u.id, now())
                RETURNING id INTO new_org_id;

                -- Create account for the organization
                INSERT INTO accounts (org_id, plan_tier, acorn_balance, status, created_at)
                VALUES (new_org_id, 'sapling', 0, 'active', now());

                -- Update user with org_id
                UPDATE users SET org_id = new_org_id WHERE id = u.id;

                -- Copy is_admin to is_superadmin
                IF u.is_admin IS TRUE THEN
                    UPDATE users SET is_superadmin = true WHERE id = u.id;
                END IF;
            END LOOP;
        END $$;
    """)

    # Drop old columns from users
    op.drop_index(op.f('ix_users_username'), table_name='users')
    op.drop_column('users', 'username')
    op.drop_column('users', 'is_admin')

    # Seed system_config with default values
    op.execute("""
        INSERT INTO system_config (key, value, description) VALUES
        ('acorn_cost_rate_usd', '0.01', 'USD cost per acorn'),
        ('trial_acorns', '250', 'Number of acorns granted on trial signup'),
        ('trial_duration_days', '14', 'Duration of trial period in days'),
        ('min_acorn_reserve', '1', 'Minimum acorn balance required to run workflows'),
        ('plan_acorns_sapling', '500', 'Monthly acorn allocation for Sapling plan'),
        ('plan_acorns_oak', '1750', 'Monthly acorn allocation for Oak plan'),
        ('plan_acorns_redwood', '4000', 'Monthly acorn allocation for Redwood plan'),
        ('payment_grace_days', '7', 'Grace period in days after payment failure'),
        ('suspension_days', '90', 'Days before suspended account data is purged'),
        ('data_export_days', '30', 'Days allowed for data export after cancellation');
    """)


def downgrade() -> None:
    # Remove system_config seeds (table will be dropped)

    # Re-add dropped columns to users
    op.add_column('users', sa.Column('is_admin', sa.Boolean(), server_default=sa.text('false'), nullable=True))
    op.add_column('users', sa.Column('username', sa.String(), nullable=True))

    # Copy is_superadmin back to is_admin
    op.execute("UPDATE users SET is_admin = is_superadmin")

    # Set username from email (before the @ part) for existing users
    op.execute("UPDATE users SET username = split_part(email, '@', 1)")

    # Make username not null and add index back
    op.alter_column('users', 'username', nullable=False)
    op.create_index(op.f('ix_users_username'), 'users', ['username'], unique=True)

    # Drop foreign key and new columns from users
    op.drop_constraint('fk_users_org_id', 'users', type_='foreignkey')
    op.drop_column('users', 'last_login_at')
    op.drop_column('users', 'locked_acorn_balance')
    op.drop_column('users', 'is_superadmin')
    op.drop_column('users', 'role')
    op.drop_column('users', 'org_id')

    # Drop tables in reverse dependency order
    op.drop_index(op.f('ix_paddle_webhook_events_event_id'), table_name='paddle_webhook_events')
    op.drop_index(op.f('ix_paddle_webhook_events_id'), table_name='paddle_webhook_events')
    op.drop_table('paddle_webhook_events')
    op.drop_table('system_config')
    op.drop_index(op.f('ix_acorn_transactions_id'), table_name='acorn_transactions')
    op.drop_table('acorn_transactions')
    op.drop_index(op.f('ix_accounts_id'), table_name='accounts')
    op.drop_table('accounts')
    op.drop_index(op.f('ix_organizations_slug'), table_name='organizations')
    op.drop_index(op.f('ix_organizations_id'), table_name='organizations')
    op.drop_table('organizations')

    # Drop enum types
    op.execute("DROP TYPE IF EXISTS acorn_transaction_type")
    op.execute("DROP TYPE IF EXISTS user_role")
    op.execute("DROP TYPE IF EXISTS account_status")
    op.execute("DROP TYPE IF EXISTS plan_tier")
