"""Add rag_defer_count for pre-send decision defer tracking.

The pre-send gate in email_service._rag_presend_decision used to fail-open on
any Anthropic httpx error, which meant during an outage every stale deal in
the queue could ship the wrong email. We now defer instead: on timeout, 5xx,
or a malformed response we reschedule the email 5 minutes out and bump
rag_defer_count. After rag.presend_defer_max consecutive defers we fall back
to sending (with a conspicuous error log) so a sustained outage can't pin
messages in the queue forever.

Revision ID: 040_add_rag_defer_count
Revises: 039_add_batch_api_columns
"""
from alembic import op
import sqlalchemy as sa


revision = "040_add_rag_defer_count"
down_revision = "039_add_batch_api_columns"


def upgrade():
    op.add_column(
        "email_queue",
        sa.Column(
            "rag_defer_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )

    op.execute(
        """
        INSERT INTO system_config (key, value, description)
        VALUES
            ('rag.presend_defer_max', '5',
             'Max consecutive pre-send Sonnet defers before falling back to sending with a warning log'),
            ('rag.presend_defer_delay_seconds', '300',
             'Seconds to reschedule an email when the pre-send Sonnet call errors or emits a malformed response')
        ON CONFLICT (key) DO NOTHING
        """
    )


def downgrade():
    op.execute(
        """
        DELETE FROM system_config WHERE key IN (
            'rag.presend_defer_max',
            'rag.presend_defer_delay_seconds'
        )
        """
    )
    op.drop_column("email_queue", "rag_defer_count")
