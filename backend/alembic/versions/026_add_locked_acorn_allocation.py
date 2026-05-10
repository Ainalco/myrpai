"""Add locked_acorn_allocation to users for per-cycle budget tracking

Revision ID: 026_add_locked_acorn_allocation
Revises: 025_fix_user_org_fk_cascade
"""
from alembic import op
import sqlalchemy as sa

revision = "026_add_locked_acorn_allocation"
down_revision = "025_fix_user_org_fk_cascade"


def upgrade():
    op.add_column("users", sa.Column("locked_acorn_allocation", sa.Float, nullable=True))
    # Backfill: set allocation = current balance for any user that already has a locked balance
    op.execute("""
        UPDATE users
        SET locked_acorn_allocation = locked_acorn_balance
        WHERE locked_acorn_balance IS NOT NULL
    """)


def downgrade():
    op.drop_column("users", "locked_acorn_allocation")
