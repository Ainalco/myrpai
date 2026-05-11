"""add whatsapp queue fields

Revision ID: 050_add_whatsapp_queue_fields
Revises: 049_add_sms_fields
Create Date: 2026-05-11
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = '050_add_whatsapp_queue_fields'
down_revision = '049_add_sms_fields'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("email_queue", sa.Column("whatsapp_message_id", sa.String(length=100), nullable=True))
    op.add_column("email_queue", sa.Column("whatsapp_template_name", sa.String(length=100), nullable=True))
    op.add_column(
        "email_queue",
        sa.Column("is_template_message", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "email_queue",
        sa.Column("conversation_window_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_email_queue_whatsapp_message_id",
        "email_queue",
        ["whatsapp_message_id"],
        unique=False,
    )


def downgrade():
    op.drop_index("ix_email_queue_whatsapp_message_id", table_name="email_queue")
    op.drop_column("email_queue", "conversation_window_expires_at")
    op.drop_column("email_queue", "is_template_message")
    op.drop_column("email_queue", "whatsapp_template_name")
    op.drop_column("email_queue", "whatsapp_message_id")