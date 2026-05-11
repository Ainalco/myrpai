"""add_sms_fields_to_email_queue

Revision ID: 049_add_sms_fields
Revises: 048_add_contact_bounced
Create Date: 2026-05-11
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = '049_add_sms_fields'
down_revision = '048_add_contact_bounced'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column(
        "email_queue",
        sa.Column("channel", sa.String(length=20), nullable=False, server_default="email"),
    )
    op.add_column("email_queue", sa.Column("recipient_phone", sa.String(length=20), nullable=True))
    op.add_column("email_queue", sa.Column("character_count", sa.Integer(), nullable=True))
    op.add_column("email_queue", sa.Column("sms_segments", sa.Integer(), nullable=True))
    op.add_column("email_queue", sa.Column("twilio_message_sid", sa.String(length=100), nullable=True))
    op.add_column("email_queue", sa.Column("delivery_status", sa.String(length=20), nullable=True))

    op.create_index("idx_email_queue_channel", "email_queue", ["channel"])
    op.create_index("idx_email_queue_twilio_message_sid", "email_queue", ["twilio_message_sid"])


def downgrade():
    op.drop_index("idx_email_queue_twilio_message_sid", table_name="email_queue")
    op.drop_index("idx_email_queue_channel", table_name="email_queue")

    op.drop_column("email_queue", "delivery_status")
    op.drop_column("email_queue", "twilio_message_sid")
    op.drop_column("email_queue", "sms_segments")
    op.drop_column("email_queue", "character_count")
    op.drop_column("email_queue", "recipient_phone")
    op.drop_column("email_queue", "channel")