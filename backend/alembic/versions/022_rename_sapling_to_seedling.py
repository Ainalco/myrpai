"""Rename sapling plan tier to seedling

Revision ID: 022
Revises: 021
"""
from alembic import op

revision = "022_rename_sapling_to_seedling"
down_revision = "021_add_invitations_audit_log"


def upgrade():
    # ADD VALUE cannot be used in a transaction block alongside DML,
    # so we commit first, then update rows separately.
    op.execute("COMMIT")
    op.execute("ALTER TYPE plan_tier ADD VALUE IF NOT EXISTS 'seedling'")
    # Now update existing accounts
    op.execute("UPDATE accounts SET plan_tier = 'seedling' WHERE plan_tier = 'sapling'")


def downgrade():
    op.execute("UPDATE accounts SET plan_tier = 'sapling' WHERE plan_tier = 'seedling'")
