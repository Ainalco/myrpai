"""Add pgvector extension and content_embeddings table for RAG

Creates the content_embeddings table used by the RAG system to store
chunked + embedded text from resources, text generation outputs,
and transcript chunks.

Revision ID: 033_content_embeddings
Revises: 032_billable_cost
"""
from alembic import op
import sqlalchemy as sa

revision = "033_content_embeddings"
down_revision = "032_billable_cost"


def upgrade():
    # Enable pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "content_embeddings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_type", sa.String(50), nullable=False),  # resource, text_gen_output, transcript_chunk, activity, generated_email
        sa.Column("source_id", sa.String(255), nullable=False),  # e.g. resource:42, execution:99, etc.
        sa.Column("contact_id", sa.Integer(), sa.ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("org_id", sa.Integer(), sa.ForeignKey("contact_organizations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("chunk_text", sa.Text(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("source_type", "source_id", "chunk_index", name="uq_embedding_source_chunk"),
    )

    # Add the vector column via raw SQL (pgvector type not natively supported by alembic)
    op.execute("ALTER TABLE content_embeddings ADD COLUMN embedding vector(1536)")

    # Indexes for common query patterns
    op.create_index("ix_content_embeddings_account_id", "content_embeddings", ["account_id"])
    op.create_index("ix_content_embeddings_contact_id", "content_embeddings", ["contact_id"])
    op.create_index("ix_content_embeddings_org_id", "content_embeddings", ["org_id"])
    op.create_index("ix_content_embeddings_source", "content_embeddings", ["source_type", "source_id"])
    op.create_index("ix_content_embeddings_created_at", "content_embeddings", ["created_at"])

    # HNSW vector index for cosine similarity search.
    # HNSW avoids IVFFlat's two prod hazards: (1) ACCESS EXCLUSIVE on rebuild,
    # (2) degenerate k-means centroids when the index is built before backfill.
    #
    # Built with CREATE INDEX CONCURRENTLY inside an autocommit_block so that
    # re-applying this migration on a populated table (rebuild / alembic stamp
    # recovery / staging rerun after a partial backfill) cannot take ACCESS
    # EXCLUSIVE and block the hot-path embedding writers in rag_service.
    # IF NOT EXISTS makes the statement idempotent on re-runs and harmless
    # when migration 038 has already rebuilt the same-named index.
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_content_embeddings_vector "
            "ON content_embeddings USING hnsw (embedding vector_cosine_ops)"
        )


def downgrade():
    # Drop the HNSW index non-blocking for symmetry with upgrade — a rollback
    # against a populated table must not lock writes either.
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_content_embeddings_vector")
    op.drop_index("ix_content_embeddings_created_at", table_name="content_embeddings")
    op.drop_index("ix_content_embeddings_source", table_name="content_embeddings")
    op.drop_index("ix_content_embeddings_org_id", table_name="content_embeddings")
    op.drop_index("ix_content_embeddings_contact_id", table_name="content_embeddings")
    op.drop_index("ix_content_embeddings_account_id", table_name="content_embeddings")
    op.drop_table("content_embeddings")
    # Intentionally do NOT drop the `vector` extension. Other tables (current
    # or future) may depend on it, and DROP EXTENSION cascades to dependent
    # objects — silently breaking unrelated features on an `alembic downgrade`.
    # A harmless installed extension is strictly safer than a destructive drop.
