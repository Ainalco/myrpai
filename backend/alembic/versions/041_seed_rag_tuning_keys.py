"""Seed remaining RAG/batch tuning keys into SystemConfig.

Moves the last batch of hardcoded tunables into system_config so operators
can A/B them without a deploy:

  - rag.structured_preference_boost: the additive similarity bump applied to
    structured (text_gen_output / resource) chunks that already score above
    rag.structured_preference. Previously +0.05, hardcoded in smart_retrieve.
  - rag.batch_max_batch_size: max rows submitted in one Anthropic batch call.
  - rag.batch_max_poll_failures: consecutive poll errors on the same batch id
    before the worker fails the rows out to the sync-Sonnet fallback.

Revision ID: 041_seed_rag_tuning_keys
Revises: 040_add_rag_defer_count
"""
from alembic import op


revision = "041_seed_rag_tuning_keys"
down_revision = "040_add_rag_defer_count"


def upgrade():
    op.execute(
        """
        INSERT INTO system_config (key, value, description)
        VALUES
            ('rag.structured_preference_boost', '0.05',
             'Additive similarity boost applied to structured chunks scoring above rag.structured_preference. Range 0..0.2.'),
            ('rag.batch_max_batch_size', '100',
             'Max rows submitted per Anthropic Batch API create_batch call.'),
            ('rag.batch_max_poll_failures', '5',
             'Consecutive poll errors on the same batch id before its rows are failed to the sync Sonnet fallback.')
        ON CONFLICT (key) DO NOTHING
        """
    )


def downgrade():
    op.execute(
        """
        DELETE FROM system_config WHERE key IN (
            'rag.structured_preference_boost',
            'rag.batch_max_batch_size',
            'rag.batch_max_poll_failures'
        )
        """
    )
