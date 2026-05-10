"""Re-add Anthropic Batch API columns with idempotency guarantees.

Reintroduces the batch columns dropped by 037 plus three new columns that
make submission idempotent against worker crashes:

  * batch_stage        — AI-pipeline state machine (null / pending_submit /
                         submitting / submitted / completed / failed). Kept
                         separate from email_queue.status, which remains the
                         SMTP-send state machine (pending / sent / failed /
                         cancelled). The two stages are orthogonal: when
                         batch_stage reaches "completed" the worker writes
                         body/subject and flips status to "pending" so the
                         SMTP worker picks it up.
  * idempotency_key    — sha256 hex of (row.id, row.prompt_hash). UNIQUE, so
                         a concurrent or crash-and-retry submit is forced to
                         hit the DB before Anthropic — a duplicate attempt
                         errors at the INSERT/UPDATE, and the worker treats
                         that as "reconcile then decide" rather than resubmit.
  * prompt_hash        — sha256 hex of the prompt body; stable across runs so
                         idempotency_key is stable across restarts.
  * custom_id          — echoed by Anthropic on every result; the
                         authoritative reconciliation key (format
                         "email_queue:{row.id}:{prompt_hash[:8]}").

See docs/superpowers/plans/2026-04-21-batch-api-idempotency.md for the full
design and failure-mode reasoning.

Revision ID: 039_add_batch_api_columns
Revises: 038_hnsw_vector_index
"""
from alembic import op
import sqlalchemy as sa


revision = "039_add_batch_api_columns"
down_revision = "038_hnsw_vector_index"


def upgrade():
    op.add_column("email_queue", sa.Column("batch_id", sa.String(length=255), nullable=True))
    op.add_column("email_queue", sa.Column("batch_status", sa.String(length=32), nullable=True))
    op.add_column("email_queue", sa.Column("batch_submitted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("email_queue", sa.Column("batch_request_payload", sa.JSON(), nullable=True))
    op.add_column("email_queue", sa.Column("batch_stage", sa.String(length=32), nullable=True))
    op.add_column("email_queue", sa.Column("idempotency_key", sa.String(length=64), nullable=True))
    op.add_column("email_queue", sa.Column("prompt_hash", sa.String(length=64), nullable=True))
    op.add_column("email_queue", sa.Column("custom_id", sa.String(length=128), nullable=True))

    op.create_index("ix_email_queue_batch_id", "email_queue", ["batch_id"])
    op.create_index("ix_email_queue_batch_status", "email_queue", ["batch_status"])
    op.create_index("ix_email_queue_batch_stage", "email_queue", ["batch_stage"])
    op.create_index("ix_email_queue_custom_id", "email_queue", ["custom_id"])
    op.create_unique_constraint(
        "uq_email_queue_idempotency_key", "email_queue", ["idempotency_key"]
    )

    op.execute(
        """
        INSERT INTO system_config (key, value, description)
        VALUES
            ('rag.batch_submit_interval_seconds', '60',
             'How often the batch worker polls for pending_submit rows'),
            ('rag.batch_poll_interval_seconds', '120',
             'How often the batch worker polls Anthropic for completed batches'),
            ('rag.batch_reconcile_lookback_hours', '24',
             'Reconciliation window: max age of Anthropic batches to scan for '
             'orphaned custom_ids on worker startup')
        ON CONFLICT (key) DO NOTHING
        """
    )


def downgrade():
    op.execute(
        """
        DELETE FROM system_config WHERE key IN (
            'rag.batch_submit_interval_seconds',
            'rag.batch_poll_interval_seconds',
            'rag.batch_reconcile_lookback_hours'
        )
        """
    )

    op.drop_constraint("uq_email_queue_idempotency_key", "email_queue", type_="unique")
    op.drop_index("ix_email_queue_custom_id", table_name="email_queue")
    op.drop_index("ix_email_queue_batch_stage", table_name="email_queue")
    op.drop_index("ix_email_queue_batch_status", table_name="email_queue")
    op.drop_index("ix_email_queue_batch_id", table_name="email_queue")

    op.drop_column("email_queue", "custom_id")
    op.drop_column("email_queue", "prompt_hash")
    op.drop_column("email_queue", "idempotency_key")
    op.drop_column("email_queue", "batch_stage")
    op.drop_column("email_queue", "batch_request_payload")
    op.drop_column("email_queue", "batch_submitted_at")
    op.drop_column("email_queue", "batch_status")
    op.drop_column("email_queue", "batch_id")
