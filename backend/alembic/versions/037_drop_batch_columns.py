"""Drop unused Anthropic Batch API columns from email_queue.

The Batch API routing was scaffolded in 035 but never wired into the request
path. Columns and indexes are removed here so the schema matches the code.

Uses IF EXISTS guards so the migration is a no-op on fresh DBs (where the
edited 035 never created the columns) and effective on existing DBs (where
the original 035 did).

Revision ID: 037_drop_batch_columns
Revises: 036_rag_retrieval_log
"""
from alembic import op
import sqlalchemy as sa

revision = "037_drop_batch_columns"
down_revision = "036_rag_retrieval_log"


def upgrade():
    # CONTRACT: These columns were added by 035 as Batch API scaffolding that
    # was never wired into the request path. 037 drops them so 039 can re-add
    # them with correct idempotency-key-based semantics. Before dropping, we
    # verify the columns (where they exist) are empty — any non-null row
    # indicates someone populated them on a fork or staging branch, and
    # dropping would silently destroy that data.
    #
    # On fresh DBs the edited 035 never created these columns, so `existing`
    # is empty and the pre-check is a single information_schema query.
    conn = op.get_bind()
    rows = conn.execute(sa.text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'email_queue' "
        "AND column_name IN "
        "('batch_id', 'batch_status', 'batch_submitted_at', 'batch_request_payload')"
    )).fetchall()
    existing = {r[0] for r in rows}

    populated = []
    for col in sorted(existing):
        # Column names come from our own hard-coded allow-list above, so the
        # f-string is injection-safe. Parametrized column references are not
        # supported by Postgres syntax.
        count = conn.execute(
            sa.text(f"SELECT COUNT(*) FROM email_queue WHERE {col} IS NOT NULL")
        ).scalar() or 0
        if count > 0:
            populated.append(f"{col}={count}")

    if populated:
        raise RuntimeError(
            "037_drop_batch_columns: refusing to drop populated batch scaffolding "
            "columns on email_queue. Non-null counts: "
            + ", ".join(populated)
            + ". These columns were meant to be empty everywhere (never wired "
            "into the request path); a non-zero count means a fork or staging "
            "environment populated them. Migrate or archive that data before "
            "re-running — do NOT drop the columns by hand."
        )

    op.execute("DROP INDEX IF EXISTS ix_email_queue_batch_id")
    op.execute("DROP INDEX IF EXISTS ix_email_queue_batch_status")
    op.execute("ALTER TABLE email_queue DROP COLUMN IF EXISTS batch_request_payload")
    op.execute("ALTER TABLE email_queue DROP COLUMN IF EXISTS batch_submitted_at")
    op.execute("ALTER TABLE email_queue DROP COLUMN IF EXISTS batch_status")
    op.execute("ALTER TABLE email_queue DROP COLUMN IF EXISTS batch_id")

    op.execute(
        "DELETE FROM system_config WHERE key IN ("
        "'rag.batch_poll_interval_seconds', 'rag.batch_submit_interval_seconds')"
    )


def downgrade():
    op.add_column("email_queue", sa.Column("batch_id", sa.String(length=255), nullable=True))
    op.add_column("email_queue", sa.Column("batch_status", sa.String(length=32), nullable=True))
    op.add_column("email_queue", sa.Column("batch_submitted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("email_queue", sa.Column("batch_request_payload", sa.JSON(), nullable=True))
    op.create_index("ix_email_queue_batch_status", "email_queue", ["batch_status"])
    op.create_index("ix_email_queue_batch_id", "email_queue", ["batch_id"])
