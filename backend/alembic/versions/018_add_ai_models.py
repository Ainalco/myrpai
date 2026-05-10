"""add_ai_models

Revision ID: 018_add_ai_models
Revises: 017_ai_usage_log
Create Date: 2026-03-03

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '018_add_ai_models'
down_revision = '017_ai_usage_log'
branch_labels = None
depends_on = None


def upgrade() -> None:
    ai_models_table = op.create_table(
        'ai_models',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('model_id', sa.String(), nullable=False),
        sa.Column('display_name', sa.String(), nullable=False),
        sa.Column('input_cost_per_million', sa.Float(), nullable=False),
        sa.Column('output_cost_per_million', sa.Float(), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint('model_id', name='uq_ai_models_model_id'),
    )

    op.bulk_insert(ai_models_table, [
        {
            'model_id': 'claude-sonnet-4-5-20250929',
            'display_name': 'Claude Sonnet 4.5',
            'input_cost_per_million': 3.0,
            'output_cost_per_million': 15.0,
            'is_active': True,
        }
    ])


def downgrade() -> None:
    op.drop_table('ai_models')
