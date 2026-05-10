"""Migrate content_embeddings.embedding to an HNSW index, non-blocking.

Why:
  * IVFFlat takes ACCESS EXCLUSIVE during CREATE INDEX. On a prod-sized
    content_embeddings table the original 035 drop-then-rebuild locked writes
    for minutes inside a single Alembic transaction.
  * IVFFlat uses k-means over existing vectors to build centroid lists. Built
    on an empty (or tiny) table — as 033 did — clustering is degenerate and
    recall collapses. HNSW has no training step and stays healthy as rows
    accumulate.
  * Consumers should also bump hnsw.ef_search per-query for recall@10; this
    migration seeds the tuning knob (rag_service.retrieve_context reads it).

How:
  * autocommit_block() disables Alembic's surrounding transaction so
    CREATE/DROP INDEX CONCURRENTLY is legal.
  * Both DROP and CREATE use IF [NOT] EXISTS so the migration is idempotent on:
      - fresh DBs where edited 033 already created the HNSW index
      - prod DBs where 033 + 035 built IVFFlat (same index name; gets dropped)
      - re-runs or partial failures

Revision ID: 038_hnsw_vector_index
Revises: 037_drop_batch_columns
"""
from alembic import op


revision = "038_hnsw_vector_index"
down_revision = "037_drop_batch_columns"


def upgrade():
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_content_embeddings_vector")
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_content_embeddings_vector "
            "ON content_embeddings USING hnsw (embedding vector_cosine_ops)"
        )

    op.execute(
        """
        INSERT INTO system_config (key, value, description)
        VALUES (
            'rag.hnsw_ef_search',
            '100',
            'HNSW search-list size issued as SET LOCAL before each similarity query. '
            'Default 40 is too low for recall@10 >= 0.9; 100 gives a safe margin. '
            'Increase for higher recall, decrease to cut latency.'
        )
        ON CONFLICT (key) DO NOTHING
        """
    )


def downgrade():
    op.execute("DELETE FROM system_config WHERE key = 'rag.hnsw_ef_search'")

    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_content_embeddings_vector")
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_content_embeddings_vector "
            "ON content_embeddings USING ivfflat (embedding vector_cosine_ops) "
            "WITH (lists = 500)"
        )
