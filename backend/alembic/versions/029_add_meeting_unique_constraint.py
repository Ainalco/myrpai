"""Add unique constraint on (contact_id, external_meeting_id) for MeetingHistory idempotency

Revision ID: 029_meeting_unique
Revises: 028_add_crm_synced_at
"""
from alembic import op

revision = "029_meeting_unique"
down_revision = "028_add_crm_synced_at"


def upgrade():
    op.create_unique_constraint(
        "uq_meeting_contact_external",
        "meeting_history",
        ["contact_id", "external_meeting_id"],
    )


def downgrade():
    op.drop_constraint("uq_meeting_contact_external", "meeting_history", type_="unique")
