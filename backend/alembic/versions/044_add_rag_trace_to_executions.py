"""Add rag_trace JSONB column to executions for RAG visibility (#73).

Persists a filtered trace of RAG-only events captured during workflow runs so
the Execution Details modal can render the same data the component-test
modal already gets via the in-flight trace buffer. JSONB so we can query
into reasons / counts later without another schema bump. Nullable because
older executions don't have this data and runs that never call rag_service
should leave the column null rather than store an empty array.

Revision ID: 044_add_rag_trace_to_executions
Revises: 043_dnc_status_and_fresh_check
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "044_add_rag_trace_to_executions"
down_revision = "043_dnc_status_and_fresh_check"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "executions",
        sa.Column("rag_trace", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade():
    op.drop_column("executions", "rag_trace")
