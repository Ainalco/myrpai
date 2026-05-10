"""Add RAG phase 4-8 schema: rag_settings on workflows, used_chunk_ids + org_warning on email_queue, seed SystemConfig.

Revision ID: 034_rag_phase4
Revises: 033_content_embeddings
"""
from alembic import op
import sqlalchemy as sa

revision = "034_rag_phase4"
down_revision = "033_content_embeddings"


def upgrade():
    # Per-workflow RAG toggles (smart_context_diversity, thin_transcript_prompt, etc.)
    op.add_column("workflows", sa.Column("rag_settings", sa.JSON(), nullable=True))

    # Track RAG chunks used within a sequence_run for diversity penalty
    op.add_column("email_queue", sa.Column("used_chunk_ids", sa.JSON(), nullable=True))

    # Org-level pre-send warning (shown in UI, never auto-cancels)
    op.add_column("email_queue", sa.Column("org_warning", sa.Text(), nullable=True))

    # Seed SystemConfig defaults used by RAG
    op.execute(
        """
        INSERT INTO system_config (key, value, description)
        VALUES
            ('rag.diversity_penalty', '0.5', 'Multiplier applied to similarity score for chunks already used within a sequence_run'),
            ('rag.haiku_model', 'claude-haiku-4-5-20251001', 'Haiku model used for AI Filters and context sufficiency gating'),
            ('rag.sonnet_model', 'claude-sonnet-4-6', 'Sonnet model used for email generation and pre-send STOP/CONTINUE decisions'),
            ('rag.batch_api_threshold_hours', '24', 'If an email is scheduled more than this many hours in the future, route through Anthropic Batch API'),
            ('rag.thin_transcript_tier1_threshold', '2', 'If this many or more Tier 1 fields are missing, flag transcript as thin')
        ON CONFLICT (key) DO NOTHING
        """
    )


def downgrade():
    op.execute(
        "DELETE FROM system_config WHERE key IN ("
        "'rag.diversity_penalty', 'rag.haiku_model', 'rag.sonnet_model', "
        "'rag.batch_api_threshold_hours', 'rag.thin_transcript_tier1_threshold')"
    )
    op.drop_column("email_queue", "org_warning")
    op.drop_column("email_queue", "used_chunk_ids")
    op.drop_column("workflows", "rag_settings")
