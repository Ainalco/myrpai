"""add_invitations_audit_log

Revision ID: 021_add_invitations_audit_log
Revises: 020_add_organizations_accounts
Create Date: 2026-03-10
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '021_add_invitations_audit_log'
down_revision = '020_add_organizations_accounts'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create enum type for invitation status (idempotent)
    op.execute("DO $$ BEGIN CREATE TYPE invitation_status AS ENUM ('pending', 'accepted', 'expired', 'revoked'); EXCEPTION WHEN duplicate_object THEN NULL; END $$")

    # Create invitations table
    op.create_table('invitations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('org_id', sa.Integer(), nullable=False),
        sa.Column('invited_by', sa.Integer(), nullable=True),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('role', postgresql.ENUM('owner', 'admin', 'member', name='user_role', create_type=False), nullable=False),
        sa.Column('token', sa.String(255), nullable=False),
        sa.Column('status', postgresql.ENUM('pending', 'accepted', 'expired', 'revoked', name='invitation_status', create_type=False), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('accepted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['invited_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_invitations_id'), 'invitations', ['id'], unique=False)
    op.create_index(op.f('ix_invitations_token'), 'invitations', ['token'], unique=True)

    # Create audit_log table
    op.create_table('audit_log',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('org_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('action', sa.String(100), nullable=False),
        sa.Column('target_type', sa.String(50), nullable=True),
        sa.Column('target_id', sa.Integer(), nullable=True),
        sa.Column('details', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('ip_address', sa.String(45), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_audit_log_id'), 'audit_log', ['id'], unique=False)
    op.create_index(op.f('ix_audit_log_org_id'), 'audit_log', ['org_id'], unique=False)
    op.create_index(op.f('ix_audit_log_action'), 'audit_log', ['action'], unique=False)
    op.create_index(op.f('ix_audit_log_created_at'), 'audit_log', ['created_at'], unique=False)

    # Add acorn_allocation_mode to accounts
    op.add_column('accounts', sa.Column('acorn_allocation_mode', sa.String(20), server_default='shared', nullable=False))


def downgrade() -> None:
    op.drop_column('accounts', 'acorn_allocation_mode')

    op.drop_index(op.f('ix_audit_log_created_at'), table_name='audit_log')
    op.drop_index(op.f('ix_audit_log_action'), table_name='audit_log')
    op.drop_index(op.f('ix_audit_log_org_id'), table_name='audit_log')
    op.drop_index(op.f('ix_audit_log_id'), table_name='audit_log')
    op.drop_table('audit_log')

    op.drop_index(op.f('ix_invitations_token'), table_name='invitations')
    op.drop_index(op.f('ix_invitations_id'), table_name='invitations')
    op.drop_table('invitations')

    op.execute("DROP TYPE IF EXISTS invitation_status")
