"""add_cascade_deletes_for_workflows_and_components

Revision ID: 008_add_cascade_deletes
Revises: 007_add_internal_domains
Create Date: 2025-11-03 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '008_add_cascade_deletes'
down_revision = '007_add_internal_domains'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Add ON DELETE CASCADE to all foreign keys referencing workflows and components.
    This ensures that when a workflow or component is deleted, all related records are also deleted.
    """

    # Drop existing foreign key constraints and recreate with CASCADE

    # 1. Components table - workflow_id
    op.drop_constraint('components_workflow_id_fkey', 'components', type_='foreignkey')
    op.create_foreign_key(
        'components_workflow_id_fkey',
        'components', 'workflows',
        ['workflow_id'], ['id'],
        ondelete='CASCADE'
    )

    # 2. Connections table - from_component_id
    op.drop_constraint('connections_from_component_id_fkey', 'connections', type_='foreignkey')
    op.create_foreign_key(
        'connections_from_component_id_fkey',
        'connections', 'components',
        ['from_component_id'], ['id'],
        ondelete='CASCADE'
    )

    # 3. Connections table - to_component_id
    op.drop_constraint('connections_to_component_id_fkey', 'connections', type_='foreignkey')
    op.create_foreign_key(
        'connections_to_component_id_fkey',
        'connections', 'components',
        ['to_component_id'], ['id'],
        ondelete='CASCADE'
    )

    # 4. Executions table - workflow_id
    op.drop_constraint('executions_workflow_id_fkey', 'executions', type_='foreignkey')
    op.create_foreign_key(
        'executions_workflow_id_fkey',
        'executions', 'workflows',
        ['workflow_id'], ['id'],
        ondelete='CASCADE'
    )

    # 5. Component_executions table - execution_id
    op.drop_constraint('component_executions_execution_id_fkey', 'component_executions', type_='foreignkey')
    op.create_foreign_key(
        'component_executions_execution_id_fkey',
        'component_executions', 'executions',
        ['execution_id'], ['id'],
        ondelete='CASCADE'
    )

    # 6. Component_executions table - component_id
    op.drop_constraint('component_executions_component_id_fkey', 'component_executions', type_='foreignkey')
    op.create_foreign_key(
        'component_executions_component_id_fkey',
        'component_executions', 'components',
        ['component_id'], ['id'],
        ondelete='CASCADE'
    )

    # 7. Extracted_variables table - workflow_id
    op.drop_constraint('extracted_variables_workflow_id_fkey', 'extracted_variables', type_='foreignkey')
    op.create_foreign_key(
        'extracted_variables_workflow_id_fkey',
        'extracted_variables', 'workflows',
        ['workflow_id'], ['id'],
        ondelete='CASCADE'
    )

    # 8. Extracted_variables table - execution_id
    op.drop_constraint('extracted_variables_execution_id_fkey', 'extracted_variables', type_='foreignkey')
    op.create_foreign_key(
        'extracted_variables_execution_id_fkey',
        'extracted_variables', 'executions',
        ['execution_id'], ['id'],
        ondelete='CASCADE'
    )

    # 9. Webhooks table - workflow_id
    op.drop_constraint('webhooks_workflow_id_fkey', 'webhooks', type_='foreignkey')
    op.create_foreign_key(
        'webhooks_workflow_id_fkey',
        'webhooks', 'workflows',
        ['workflow_id'], ['id'],
        ondelete='CASCADE'
    )

    # 10. Webhooks table - component_id (THIS IS THE KEY FIX FOR YOUR ERROR)
    op.drop_constraint('webhooks_component_id_fkey', 'webhooks', type_='foreignkey')
    op.create_foreign_key(
        'webhooks_component_id_fkey',
        'webhooks', 'components',
        ['component_id'], ['id'],
        ondelete='CASCADE'
    )

    # 11. Email_queue table - workflow_id
    op.drop_constraint('email_queue_workflow_id_fkey', 'email_queue', type_='foreignkey')
    op.create_foreign_key(
        'email_queue_workflow_id_fkey',
        'email_queue', 'workflows',
        ['workflow_id'], ['id'],
        ondelete='CASCADE'
    )

    # 12. Email_queue table - execution_id
    op.drop_constraint('email_queue_execution_id_fkey', 'email_queue', type_='foreignkey')
    op.create_foreign_key(
        'email_queue_execution_id_fkey',
        'email_queue', 'executions',
        ['execution_id'], ['id'],
        ondelete='CASCADE'
    )

    # 13. Email_queue table - component_id
    op.drop_constraint('email_queue_component_id_fkey', 'email_queue', type_='foreignkey')
    op.create_foreign_key(
        'email_queue_component_id_fkey',
        'email_queue', 'components',
        ['component_id'], ['id'],
        ondelete='CASCADE'
    )


def downgrade() -> None:
    """
    Remove CASCADE deletes and restore original foreign key constraints without CASCADE.
    """

    # Reverse all the changes - remove CASCADE

    # 1. Components table - workflow_id
    op.drop_constraint('components_workflow_id_fkey', 'components', type_='foreignkey')
    op.create_foreign_key(
        'components_workflow_id_fkey',
        'components', 'workflows',
        ['workflow_id'], ['id']
    )

    # 2. Connections table - from_component_id
    op.drop_constraint('connections_from_component_id_fkey', 'connections', type_='foreignkey')
    op.create_foreign_key(
        'connections_from_component_id_fkey',
        'connections', 'components',
        ['from_component_id'], ['id']
    )

    # 3. Connections table - to_component_id
    op.drop_constraint('connections_to_component_id_fkey', 'connections', type_='foreignkey')
    op.create_foreign_key(
        'connections_to_component_id_fkey',
        'connections', 'components',
        ['to_component_id'], ['id']
    )

    # 4. Executions table - workflow_id
    op.drop_constraint('executions_workflow_id_fkey', 'executions', type_='foreignkey')
    op.create_foreign_key(
        'executions_workflow_id_fkey',
        'executions', 'workflows',
        ['workflow_id'], ['id']
    )

    # 5. Component_executions table - execution_id
    op.drop_constraint('component_executions_execution_id_fkey', 'component_executions', type_='foreignkey')
    op.create_foreign_key(
        'component_executions_execution_id_fkey',
        'component_executions', 'executions',
        ['execution_id'], ['id']
    )

    # 6. Component_executions table - component_id
    op.drop_constraint('component_executions_component_id_fkey', 'component_executions', type_='foreignkey')
    op.create_foreign_key(
        'component_executions_component_id_fkey',
        'component_executions', 'components',
        ['component_id'], ['id']
    )

    # 7. Extracted_variables table - workflow_id
    op.drop_constraint('extracted_variables_workflow_id_fkey', 'extracted_variables', type_='foreignkey')
    op.create_foreign_key(
        'extracted_variables_workflow_id_fkey',
        'extracted_variables', 'workflows',
        ['workflow_id'], ['id']
    )

    # 8. Extracted_variables table - execution_id
    op.drop_constraint('extracted_variables_execution_id_fkey', 'extracted_variables', type_='foreignkey')
    op.create_foreign_key(
        'extracted_variables_execution_id_fkey',
        'extracted_variables', 'executions',
        ['execution_id'], ['id']
    )

    # 9. Webhooks table - workflow_id
    op.drop_constraint('webhooks_workflow_id_fkey', 'webhooks', type_='foreignkey')
    op.create_foreign_key(
        'webhooks_workflow_id_fkey',
        'webhooks', 'workflows',
        ['workflow_id'], ['id']
    )

    # 10. Webhooks table - component_id
    op.drop_constraint('webhooks_component_id_fkey', 'webhooks', type_='foreignkey')
    op.create_foreign_key(
        'webhooks_component_id_fkey',
        'webhooks', 'components',
        ['component_id'], ['id']
    )

    # 11. Email_queue table - workflow_id
    op.drop_constraint('email_queue_workflow_id_fkey', 'email_queue', type_='foreignkey')
    op.create_foreign_key(
        'email_queue_workflow_id_fkey',
        'email_queue', 'workflows',
        ['workflow_id'], ['id']
    )

    # 12. Email_queue table - execution_id
    op.drop_constraint('email_queue_execution_id_fkey', 'email_queue', type_='foreignkey')
    op.create_foreign_key(
        'email_queue_execution_id_fkey',
        'email_queue', 'executions',
        ['execution_id'], ['id']
    )

    # 13. Email_queue table - component_id
    op.drop_constraint('email_queue_component_id_fkey', 'email_queue', type_='foreignkey')
    op.create_foreign_key(
        'email_queue_component_id_fkey',
        'email_queue', 'components',
        ['component_id'], ['id']
    )
