"""RAG tuning.

- Seeds SystemConfig keys for previously hardcoded RAG tuning constants.

Note: an earlier revision of this migration also dropped and rebuilt the
pgvector IVFFlat index with lists=500. That step took ACCESS EXCLUSIVE on
content_embeddings for minutes on prod-sized data. The index switch is now
handled by migration 038 (HNSW, built CONCURRENTLY). Removed from this file
so fresh DBs skip the locking rebuild; existing DBs already ran the old
version and are migrated forward by 038.

Revision ID: 035_rag_tuning_batch
Revises: 034_rag_phase4
"""
from alembic import op

revision = "035_rag_tuning_batch"
down_revision = "034_rag_phase4"


def upgrade():
    # --- Seed RAG tuning constants (previously module-level in rag_service.py) ---
    op.execute(
        """
        INSERT INTO system_config (key, value, description)
        VALUES
            ('rag.chunk_size', '300', 'Words per chunk when embedding long text'),
            ('rag.chunk_overlap', '50', 'Overlap in words between adjacent chunks'),
            ('rag.similarity_threshold', '0.70', 'Minimum cosine similarity to include a chunk in results'),
            ('rag.structured_preference', '0.78', 'When structured and raw chunks score close, prefer structured above this score'),
            ('rag.max_retrieval_results', '5', 'Default top-k per retrieval block'),
            ('rag.dedup_jaccard_threshold', '0.6', 'Drop a chunk as duplicate when word Jaccard overlap exceeds this value')
        ON CONFLICT (key) DO NOTHING
        """
    )


def downgrade():
    op.execute(
        """
        DELETE FROM system_config WHERE key IN (
            'rag.chunk_size', 'rag.chunk_overlap', 'rag.similarity_threshold',
            'rag.structured_preference', 'rag.max_retrieval_results',
            'rag.dedup_jaccard_threshold'
        )
        """
    )
