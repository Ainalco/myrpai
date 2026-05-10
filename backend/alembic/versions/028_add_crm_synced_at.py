"""Add crm_synced_at to contacts for tracking Pipedrive sync freshness

Revision ID: 028_add_crm_synced_at
Revises: 027_add_contact_system
"""
from alembic import op
import sqlalchemy as sa

revision = "028_add_crm_synced_at"
down_revision = "027_add_contact_system"


def upgrade():
    op.add_column("contacts", sa.Column("crm_synced_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_contacts_crm_synced_at", "contacts", ["crm_synced_at"])


def downgrade():
    op.drop_index("ix_contacts_crm_synced_at", "contacts")
    op.drop_column("contacts", "crm_synced_at")
