"""Add rag_retrieval_log table for retrieval latency observability.

Revision ID: 036_rag_retrieval_log
Revises: 035_rag_tuning_batch
"""
from alembic import op
import sqlalchemy as sa

revision = "036_rag_retrieval_log"
down_revision = "035_rag_tuning_batch"


def upgrade():
    op.create_table(
        "rag_retrieval_log",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "account_id",
            sa.Integer(),
            sa.ForeignKey("accounts.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("result_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_rag_retrieval_log_account_id", "rag_retrieval_log", ["account_id"])
    op.create_index("ix_rag_retrieval_log_created_at", "rag_retrieval_log", ["created_at"])


def downgrade():
    op.drop_index("ix_rag_retrieval_log_created_at", table_name="rag_retrieval_log")
    op.drop_index("ix_rag_retrieval_log_account_id", table_name="rag_retrieval_log")
    op.drop_table("rag_retrieval_log")
