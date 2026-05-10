"""add_dnc_org_fields

Revision ID: 045_add_dnc_org_fields
Revises: 044_add_rag_trace_to_executions
Create Date: 2026-04-29

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = '045_add_dnc_org_fields'
down_revision = '044_add_rag_trace_to_executions'
branch_labels = None
depends_on = None

def upgrade() -> None:

    # 1️⃣ Add dnc column
    op.add_column('contact_organizations', sa.Column('dnc', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('contact_organizations', sa.Column('dnc_set_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('contact_organizations', sa.Column('dnc_set_by', sa.Integer(), nullable=True))
    op.add_column('contact_organizations', sa.Column('dnc_propagation_status', sa.String(), nullable=True))

    # 3️⃣ Create index for channel
    op.create_index(
        'ix_contact_org_dnc',
        'contact_organizations',
        ['dnc'],
        unique=False
    )


def downgrade() -> None:

    # Drop index
    op.drop_index('ix_contact_org_dnc', table_name='contact_organizations')

    # Drop columns (reverse order is safer)
    op.drop_column('contact_organizations', 'dnc_propagation_status')
    op.drop_column('contact_organizations', 'dnc_set_by')
    op.drop_column('contact_organizations', 'dnc_set_at')
    op.drop_column('contact_organizations', 'dnc')
