"""Add composite index on content_embeddings (account_id, created_at DESC)

Common query filter is `account_id = ? AND created_at >= ?` (pre-send
snapshots, admin observability, contact/org activity windows). The standalone
ix_content_embeddings_account_id and ix_content_embeddings_created_at
indexes force either a bitmap-and or a seq scan — a composite index with
created_at DESC serves those range filters directly.

The older single-column indexes are kept because other call sites still
filter by created_at alone (global observability) or account_id alone
(account-scoped maintenance), and dropping them here would regress those
planners.

Revision ID: 042_content_embeddings_acct_idx
Revises: 041_seed_rag_tuning_keys
"""
from alembic import op


revision = "042_content_embeddings_acct_idx"
down_revision = "041_seed_rag_tuning_keys"


def upgrade():
    # Raw SQL so we can specify DESC on created_at — op.create_index does not
    # expose per-column sort order.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_content_embeddings_account_id_created_at "
        "ON content_embeddings (account_id, created_at DESC)"
    )


def downgrade():
    op.execute(
        "DROP INDEX IF EXISTS ix_content_embeddings_account_id_created_at"
    )
