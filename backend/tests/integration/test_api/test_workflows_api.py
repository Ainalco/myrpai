"""
Integration tests for workflows API endpoints
Tests /workflows/* endpoints with database interactions
"""
import pytest
from httpx import AsyncClient

import models
from tests.fixtures.factories import UserFactory, WorkflowFactory, ComponentFactory, ConnectionFactory, ExecutionFactory


@pytest.mark.asyncio
class TestListWorkflowsEndpoint:
    """Test GET /workflows/ endpoint"""

    async def test_list_workflows_success(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test listing workflows for authenticated user"""
        # Arrange
        workflow1 = WorkflowFactory.create(owner=test_user, name="First Workflow")
        workflow2 = WorkflowFactory.create(owner=test_user, name="Second Workflow")
        db_session.add_all([workflow1, workflow2])
        db_session.commit()

        # Act
        response = await authenticated_client.get("/workflows/")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["name"] in ["First Workflow", "Second Workflow"]
        assert data[1]["name"] in ["First Workflow", "Second Workflow"]

    async def test_list_workflows_empty(self, authenticated_client: AsyncClient):
        """Test listing workflows when user has no workflows"""
        # Act
        response = await authenticated_client.get("/workflows/")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 0
        assert isinstance(data, list)

    async def test_list_workflows_unauthenticated(self, client: AsyncClient):
        """Test listing workflows without authentication fails"""
        # Act
        response = await client.get("/workflows/")

        # Assert
        assert response.status_code == 401

    async def test_list_workflows_only_returns_user_workflows(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test that list only returns workflows owned by the authenticated user"""
        # Arrange
        other_user = UserFactory.create(username="otheruser")
        db_session.add(other_user)
        db_session.commit()

        user_workflow = WorkflowFactory.create(owner=test_user, name="My Workflow")
        other_workflow = WorkflowFactory.create(owner=other_user, name="Other Workflow")
        db_session.add_all([user_workflow, other_workflow])
        db_session.commit()

        # Act
        response = await authenticated_client.get("/workflows/")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "My Workflow"

    async def test_list_workflows_includes_components(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test that listed workflows include their components"""
        # Arrange
        workflow = WorkflowFactory.create(owner=test_user)
        component = ComponentFactory.create(workflow=workflow, name="Test Component")
        db_session.add_all([workflow, component])
        db_session.commit()

        # Act
        response = await authenticated_client.get("/workflows/")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert "components" in data[0]
        assert len(data[0]["components"]) == 1
        assert data[0]["components"][0]["name"] == "Test Component"


@pytest.mark.asyncio
class TestCreateWorkflowEndpoint:
    """Test POST /workflows/ endpoint"""

    async def test_create_workflow_success(self, authenticated_client: AsyncClient, db_session):
        """Test successful workflow creation"""
        # Arrange
        workflow_data = {
            "name": "New Workflow",
            "description": "Test workflow description",
            "universal_rules": "Always be professional"
        }

        # Act
        response = await authenticated_client.post("/workflows/", json=workflow_data)

        # Assert
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "New Workflow"
        assert data["description"] == "Test workflow description"
        assert data["universal_rules"] == "Always be professional"
        assert data["is_active"] is True
        assert "id" in data
        assert "created_at" in data

    async def test_create_workflow_auto_creates_input_component(self, authenticated_client: AsyncClient, db_session):
        """Test that creating workflow automatically creates input source component"""
        # Arrange
        workflow_data = {
            "name": "Workflow with Input",
            "description": "Test"
        }

        # Act
        response = await authenticated_client.post("/workflows/", json=workflow_data)

        # Assert
        assert response.status_code == 201
        data = response.json()
        assert "components" in data
        assert len(data["components"]) == 1

        input_component = data["components"][0]
        assert input_component["type"] == "input_sources"
        assert input_component["name"] == "Input Source"
        assert input_component["order"] == 0

    async def test_create_workflow_minimal_data(self, authenticated_client: AsyncClient):
        """Test creating workflow with only required fields"""
        # Arrange
        workflow_data = {
            "name": "Minimal Workflow"
        }

        # Act
        response = await authenticated_client.post("/workflows/", json=workflow_data)

        # Assert
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Minimal Workflow"
        assert data["description"] is None
        assert data["universal_rules"] is None

    async def test_create_workflow_missing_name(self, authenticated_client: AsyncClient):
        """Test creating workflow without name fails"""
        # Arrange
        workflow_data = {
            "description": "Missing name"
        }

        # Act
        response = await authenticated_client.post("/workflows/", json=workflow_data)

        # Assert
        assert response.status_code == 422

    async def test_create_workflow_unauthenticated(self, client: AsyncClient):
        """Test creating workflow without authentication fails"""
        # Arrange
        workflow_data = {"name": "Unauthorized Workflow"}

        # Act
        response = await client.post("/workflows/", json=workflow_data)

        # Assert
        assert response.status_code == 401


@pytest.mark.asyncio
class TestGetWorkflowEndpoint:
    """Test GET /workflows/{workflow_id} endpoint"""

    async def test_get_workflow_success(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test getting a specific workflow"""
        # Arrange
        workflow = WorkflowFactory.create(owner=test_user, name="Test Workflow")
        component = ComponentFactory.create(workflow=workflow, name="Test Component")
        db_session.add_all([workflow, component])
        db_session.commit()

        # Act
        response = await authenticated_client.get(f"/workflows/{workflow.id}")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == workflow.id
        assert data["name"] == "Test Workflow"
        assert len(data["components"]) == 1
        assert data["components"][0]["name"] == "Test Component"

    async def test_get_workflow_not_found(self, authenticated_client: AsyncClient):
        """Test getting non-existent workflow"""
        # Act
        response = await authenticated_client.get("/workflows/99999")

        # Assert
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    async def test_get_workflow_unauthorized(self, authenticated_client: AsyncClient, db_session):
        """Test getting workflow owned by another user fails"""
        # Arrange
        other_user = UserFactory.create(username="otheruser")
        workflow = WorkflowFactory.create(owner=other_user, name="Other's Workflow")
        db_session.add_all([other_user, workflow])
        db_session.commit()

        # Act
        response = await authenticated_client.get(f"/workflows/{workflow.id}")

        # Assert
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    async def test_get_workflow_unauthenticated(self, client: AsyncClient, db_session, test_user):
        """Test getting workflow without authentication fails"""
        # Arrange
        workflow = WorkflowFactory.create(owner=test_user)
        db_session.add(workflow)
        db_session.commit()

        # Act
        response = await client.get(f"/workflows/{workflow.id}")

        # Assert
        assert response.status_code == 401


@pytest.mark.asyncio
class TestUpdateWorkflowEndpoint:
    """Test PUT /workflows/{workflow_id} endpoint"""

    async def test_update_workflow_all_fields(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test updating all workflow fields"""
        # Arrange
        workflow = WorkflowFactory.create(
            owner=test_user,
            name="Original Name",
            description="Original description",
            universal_rules="Original rules",
            is_active=True
        )
        db_session.add(workflow)
        db_session.commit()

        update_data = {
            "name": "Updated Name",
            "description": "Updated description",
            "universal_rules": "Updated rules",
            "is_active": False
        }

        # Act
        response = await authenticated_client.put(f"/workflows/{workflow.id}", json=update_data)

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Name"
        assert data["description"] == "Updated description"
        assert data["universal_rules"] == "Updated rules"
        assert data["is_active"] is False

    async def test_update_workflow_partial(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test partial update of workflow"""
        # Arrange
        workflow = WorkflowFactory.create(
            owner=test_user,
            name="Original Name",
            description="Original description"
        )
        db_session.add(workflow)
        db_session.commit()

        update_data = {
            "name": "Updated Name Only"
        }

        # Act
        response = await authenticated_client.put(f"/workflows/{workflow.id}", json=update_data)

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Name Only"
        assert data["description"] == "Original description"  # Unchanged

    async def test_update_workflow_toggle_active(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test toggling workflow active status"""
        # Arrange
        workflow = WorkflowFactory.create(owner=test_user, is_active=True)
        db_session.add(workflow)
        db_session.commit()

        # Act
        response = await authenticated_client.put(
            f"/workflows/{workflow.id}",
            json={"is_active": False}
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["is_active"] is False

    async def test_update_workflow_not_found(self, authenticated_client: AsyncClient):
        """Test updating non-existent workflow"""
        # Act
        response = await authenticated_client.put(
            "/workflows/99999",
            json={"name": "Updated"}
        )

        # Assert
        assert response.status_code == 404

    async def test_update_workflow_unauthorized(self, authenticated_client: AsyncClient, db_session):
        """Test updating workflow owned by another user fails"""
        # Arrange
        other_user = UserFactory.create(username="otheruser")
        workflow = WorkflowFactory.create(owner=other_user)
        db_session.add_all([other_user, workflow])
        db_session.commit()

        # Act
        response = await authenticated_client.put(
            f"/workflows/{workflow.id}",
            json={"name": "Hacked"}
        )

        # Assert
        assert response.status_code == 404

    async def test_update_workflow_unauthenticated(self, client: AsyncClient, db_session, test_user):
        """Test updating workflow without authentication fails"""
        # Arrange
        workflow = WorkflowFactory.create(owner=test_user)
        db_session.add(workflow)
        db_session.commit()

        # Act
        response = await client.put(
            f"/workflows/{workflow.id}",
            json={"name": "Updated"}
        )

        # Assert
        assert response.status_code == 401

    async def test_update_workflow_rag_settings_persists_to_db(
        self, authenticated_client: AsyncClient, db_session, test_user
    ):
        """Regression: toggling a RAG setting must issue an UPDATE, not just
        mutate the in-session dict.

        workflows.rag_settings is Column(JSON) without MutableDict.as_mutable,
        so an in-place existing.update(incoming) does NOT flag the attribute
        as dirty and the UPDATE is silently skipped. The endpoint returns 200
        but the row on disk is unchanged — exactly what a user sees as
        "toggled a setting, refreshed, reverted."

        Forcing expire_all() before re-reading is load-bearing: without it the
        identity map would serve the in-memory (possibly non-persisted) dict
        and the test would pass even with the bug present.
        """
        workflow = WorkflowFactory.create(
            owner=test_user,
            name="RAG Workflow",
            rag_settings={
                "smart_context_diversity": False,
                "thin_transcript_prompt": False,
            },
        )
        db_session.add(workflow)
        db_session.commit()
        workflow_id = workflow.id

        response = await authenticated_client.put(
            f"/workflows/{workflow_id}",
            json={"rag_settings": {
                "smart_context_diversity": True,
                "thin_transcript_prompt": False,
            }},
        )

        assert response.status_code == 200
        assert response.json()["rag_settings"] == {
            "smart_context_diversity": True,
            "thin_transcript_prompt": False,
        }

        # Drop cached attributes so the next access hits the database. This is
        # what distinguishes a real persisted update from a fake in-memory one.
        db_session.expire_all()
        reloaded = db_session.query(models.Workflow).filter(
            models.Workflow.id == workflow_id
        ).first()
        assert reloaded is not None
        assert reloaded.rag_settings == {
            "smart_context_diversity": True,
            "thin_transcript_prompt": False,
        }


@pytest.mark.asyncio
class TestDeleteWorkflowEndpoint:
    """Test DELETE /workflows/{workflow_id} endpoint"""

    async def test_delete_workflow_success(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test successful workflow deletion"""
        # Arrange
        workflow = WorkflowFactory.create(owner=test_user, name="To Delete")
        db_session.add(workflow)
        db_session.commit()
        workflow_id = workflow.id

        # Act
        response = await authenticated_client.delete(f"/workflows/{workflow_id}")

        # Assert
        assert response.status_code == 200
        assert "deleted successfully" in response.json()["message"].lower()

        # Verify workflow is deleted
        verify_response = await authenticated_client.get(f"/workflows/{workflow_id}")
        assert verify_response.status_code == 404

    async def test_delete_workflow_with_components(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test deleting workflow cascades to components"""
        # Arrange
        workflow = WorkflowFactory.create(owner=test_user)
        component = ComponentFactory.create(workflow=workflow)
        db_session.add_all([workflow, component])
        db_session.commit()
        workflow_id = workflow.id
        component_id = component.id

        # Act
        response = await authenticated_client.delete(f"/workflows/{workflow_id}")

        # Assert
        assert response.status_code == 200

        # Verify component was also deleted
        from models import Component
        deleted_component = db_session.query(Component).filter(Component.id == component_id).first()
        assert deleted_component is None

    async def test_delete_workflow_not_found(self, authenticated_client: AsyncClient):
        """Test deleting non-existent workflow"""
        # Act
        response = await authenticated_client.delete("/workflows/99999")

        # Assert
        assert response.status_code == 404

    async def test_delete_workflow_unauthorized(self, authenticated_client: AsyncClient, db_session):
        """Test deleting workflow owned by another user fails"""
        # Arrange
        other_user = UserFactory.create(username="otheruser")
        workflow = WorkflowFactory.create(owner=other_user)
        db_session.add_all([other_user, workflow])
        db_session.commit()

        # Act
        response = await authenticated_client.delete(f"/workflows/{workflow.id}")

        # Assert
        assert response.status_code == 404

    async def test_delete_workflow_unauthenticated(self, client: AsyncClient, db_session, test_user):
        """Test deleting workflow without authentication fails"""
        # Arrange
        workflow = WorkflowFactory.create(owner=test_user)
        db_session.add(workflow)
        db_session.commit()

        # Act
        response = await client.delete(f"/workflows/{workflow.id}")

        # Assert
        assert response.status_code == 401

    async def test_delete_workflow_cascades_to_executions(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test deleting workflow cascades to executions"""
        from tests.fixtures.factories import ExecutionFactory
        from models import Execution

        # Arrange
        workflow = WorkflowFactory.create(owner=test_user)
        execution1 = ExecutionFactory.create(workflow=workflow, status="completed")
        execution2 = ExecutionFactory.create(workflow=workflow, status="failed")
        db_session.add_all([workflow, execution1, execution2])
        db_session.commit()
        workflow_id = workflow.id
        execution1_id = execution1.id
        execution2_id = execution2.id

        # Act
        response = await authenticated_client.delete(f"/workflows/{workflow_id}")

        # Assert
        assert response.status_code == 200

        # Verify executions were deleted
        deleted_exec1 = db_session.query(Execution).filter(Execution.id == execution1_id).first()
        deleted_exec2 = db_session.query(Execution).filter(Execution.id == execution2_id).first()
        assert deleted_exec1 is None
        assert deleted_exec2 is None

    async def test_delete_workflow_cascades_to_webhooks(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test deleting workflow cascades to webhooks (fixes the original bug)"""
        from tests.fixtures.factories import WebhookFactory
        from models import Webhook

        # Arrange
        workflow = WorkflowFactory.create(owner=test_user)
        component = ComponentFactory.create(workflow=workflow)
        webhook = WebhookFactory.create(workflow=workflow, component=component, name="Test Webhook")
        db_session.add_all([workflow, component, webhook])
        db_session.commit()
        workflow_id = workflow.id
        webhook_id = webhook.id

        # Act - This would have failed before the cascade delete fix
        response = await authenticated_client.delete(f"/workflows/{workflow_id}")

        # Assert
        assert response.status_code == 200

        # Verify webhook was deleted
        deleted_webhook = db_session.query(Webhook).filter(Webhook.id == webhook_id).first()
        assert deleted_webhook is None

    async def test_delete_workflow_cascades_to_extracted_variables(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test deleting workflow cascades to extracted variables"""
        from tests.fixtures.factories import ExecutionFactory, ExtractedVariableFactory
        from models import ExtractedVariable

        # Arrange
        workflow = WorkflowFactory.create(owner=test_user)
        execution = ExecutionFactory.create(workflow=workflow)
        variable1 = ExtractedVariableFactory.create(workflow=workflow, execution=execution, variable_name="Participant")
        variable2 = ExtractedVariableFactory.create(workflow=workflow, execution=execution, variable_name="Budget")
        db_session.add_all([workflow, execution, variable1, variable2])
        db_session.commit()
        workflow_id = workflow.id
        variable1_id = variable1.id
        variable2_id = variable2.id

        # Act
        response = await authenticated_client.delete(f"/workflows/{workflow_id}")

        # Assert
        assert response.status_code == 200

        # Verify variables were deleted
        deleted_var1 = db_session.query(ExtractedVariable).filter(ExtractedVariable.id == variable1_id).first()
        deleted_var2 = db_session.query(ExtractedVariable).filter(ExtractedVariable.id == variable2_id).first()
        assert deleted_var1 is None
        assert deleted_var2 is None

    async def test_delete_workflow_cascades_to_email_queue(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test deleting workflow cascades to email queue"""
        from tests.fixtures.factories import EmailQueueFactory, ExecutionFactory
        from models import EmailQueue

        # Arrange
        workflow = WorkflowFactory.create(owner=test_user)
        execution = ExecutionFactory.create(workflow=workflow)
        component = ComponentFactory.create(workflow=workflow)
        email1 = EmailQueueFactory.create(
            user=test_user,
            workflow=workflow,
            execution=execution,
            component=component,
            status="pending"
        )
        email2 = EmailQueueFactory.create(
            user=test_user,
            workflow=workflow,
            execution=execution,
            component=component,
            status="sent"
        )
        db_session.add_all([workflow, execution, component, email1, email2])
        db_session.commit()
        workflow_id = workflow.id
        email1_id = email1.id
        email2_id = email2.id

        # Act
        response = await authenticated_client.delete(f"/workflows/{workflow_id}")

        # Assert
        assert response.status_code == 200

        # Verify emails were deleted
        deleted_email1 = db_session.query(EmailQueue).filter(EmailQueue.id == email1_id).first()
        deleted_email2 = db_session.query(EmailQueue).filter(EmailQueue.id == email2_id).first()
        assert deleted_email1 is None
        assert deleted_email2 is None

    async def test_delete_workflow_cascades_to_connections(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test deleting workflow cascades to connections between components"""
        from tests.fixtures.factories import ConnectionFactory
        from models import Connection

        # Arrange
        workflow = WorkflowFactory.create(owner=test_user)
        component1 = ComponentFactory.create(workflow=workflow, name="Input")
        component2 = ComponentFactory.create(workflow=workflow, name="Output")
        connection = ConnectionFactory.create(
            workflow=workflow,
            from_component=component1,
            to_component=component2
        )
        db_session.add_all([workflow, component1, component2, connection])
        db_session.commit()
        workflow_id = workflow.id
        connection_id = connection.id

        # Act
        response = await authenticated_client.delete(f"/workflows/{workflow_id}")

        # Assert
        assert response.status_code == 200

        # Verify connection was deleted
        deleted_connection = db_session.query(Connection).filter(Connection.id == connection_id).first()
        assert deleted_connection is None

    async def test_delete_workflow_cascades_to_component_executions(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test deleting workflow cascades to component executions"""
        from tests.fixtures.factories import ExecutionFactory, ComponentExecutionFactory
        from models import ComponentExecution

        # Arrange
        workflow = WorkflowFactory.create(owner=test_user)
        component = ComponentFactory.create(workflow=workflow)
        execution = ExecutionFactory.create(workflow=workflow)
        comp_exec = ComponentExecutionFactory.create(
            execution=execution,
            component=component,
            status="completed"
        )
        db_session.add_all([workflow, component, execution, comp_exec])
        db_session.commit()
        workflow_id = workflow.id
        comp_exec_id = comp_exec.id

        # Act
        response = await authenticated_client.delete(f"/workflows/{workflow_id}")

        # Assert
        assert response.status_code == 200

        # Verify component execution was deleted
        deleted_comp_exec = db_session.query(ComponentExecution).filter(ComponentExecution.id == comp_exec_id).first()
        assert deleted_comp_exec is None

    async def test_delete_workflow_full_cascade_integration(self, authenticated_client: AsyncClient, db_session, test_user):
        """
        Integration test: Delete workflow with all related entities and verify complete cascade.
        This tests the entire fix for the original bug where webhooks blocked deletion.
        """
        from tests.fixtures.factories import (
            ExecutionFactory, ComponentExecutionFactory, WebhookFactory,
            ExtractedVariableFactory, EmailQueueFactory, ConnectionFactory
        )
        from models import (
            Workflow, Component, Connection, Execution, ComponentExecution,
            Webhook, ExtractedVariable, EmailQueue
        )

        # Arrange - Create a workflow with ALL related entities
        workflow = WorkflowFactory.create(owner=test_user, name="Full Cascade Test")

        # Components
        component1 = ComponentFactory.create(workflow=workflow, name="Input")
        component2 = ComponentFactory.create(workflow=workflow, name="Processor")

        # Connections
        connection = ConnectionFactory.create(workflow=workflow, from_component=component1, to_component=component2)

        # Executions
        execution = ExecutionFactory.create(workflow=workflow, status="completed")

        # Component Executions
        comp_exec1 = ComponentExecutionFactory.create(execution=execution, component=component1)
        comp_exec2 = ComponentExecutionFactory.create(execution=execution, component=component2)

        # Webhooks (the original problem!)
        webhook = WebhookFactory.create(workflow=workflow, component=component1, name="Trigger Webhook")

        # Extracted Variables
        variable = ExtractedVariableFactory.create(workflow=workflow, execution=execution)

        # Email Queue
        email = EmailQueueFactory.create(
            user=test_user,
            workflow=workflow,
            execution=execution,
            component=component2
        )

        db_session.add_all([
            workflow, component1, component2, connection, execution,
            comp_exec1, comp_exec2, webhook, variable, email
        ])
        db_session.commit()

        # Store IDs for verification
        workflow_id = workflow.id
        component1_id = component1.id
        component2_id = component2.id
        connection_id = connection.id
        execution_id = execution.id
        comp_exec1_id = comp_exec1.id
        comp_exec2_id = comp_exec2.id
        webhook_id = webhook.id
        variable_id = variable.id
        email_id = email.id

        # Act - Delete the workflow (this would have failed before the fix)
        response = await authenticated_client.delete(f"/workflows/{workflow_id}")

        # Assert
        assert response.status_code == 200
        assert "deleted successfully" in response.json()["message"].lower()

        # Verify ALL related entities were deleted
        assert db_session.query(Workflow).filter(Workflow.id == workflow_id).first() is None
        assert db_session.query(Component).filter(Component.id == component1_id).first() is None
        assert db_session.query(Component).filter(Component.id == component2_id).first() is None
        assert db_session.query(Connection).filter(Connection.id == connection_id).first() is None
        assert db_session.query(Execution).filter(Execution.id == execution_id).first() is None
        assert db_session.query(ComponentExecution).filter(ComponentExecution.id == comp_exec1_id).first() is None
        assert db_session.query(ComponentExecution).filter(ComponentExecution.id == comp_exec2_id).first() is None
        assert db_session.query(Webhook).filter(Webhook.id == webhook_id).first() is None
        assert db_session.query(ExtractedVariable).filter(ExtractedVariable.id == variable_id).first() is None
        assert db_session.query(EmailQueue).filter(EmailQueue.id == email_id).first() is None


@pytest.mark.asyncio
class TestDashboardStatsEndpoint:
    """Test GET /workflows/stats/dashboard endpoint"""

    async def test_dashboard_stats_no_workflows(self, authenticated_client: AsyncClient):
        """Test dashboard stats when user has no workflows"""
        # Act
        response = await authenticated_client.get("/workflows/stats/dashboard")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["total_workflows"] == 0
        assert data["active_workflows"] == 0
        assert data["total_executions"] == 0
        assert data["successful_executions"] == 0
        assert data["failed_executions"] == 0
        assert data["avg_execution_time"] is None

    async def test_dashboard_stats_with_workflows(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test dashboard stats with multiple workflows"""
        # Arrange
        workflow1 = WorkflowFactory.create(owner=test_user, is_active=True)
        workflow2 = WorkflowFactory.create(owner=test_user, is_active=True)
        workflow3 = WorkflowFactory.create(owner=test_user, is_active=False)
        db_session.add_all([workflow1, workflow2, workflow3])
        db_session.commit()

        # Act
        response = await authenticated_client.get("/workflows/stats/dashboard")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["total_workflows"] == 3
        assert data["active_workflows"] == 2

    async def test_dashboard_stats_with_executions(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test dashboard stats with execution data"""
        # Arrange
        workflow = WorkflowFactory.create(owner=test_user)
        db_session.add(workflow)
        db_session.commit()

        exec1 = ExecutionFactory.create(workflow=workflow, status="completed", total_execution_time=10.5)
        exec2 = ExecutionFactory.create(workflow=workflow, status="completed", total_execution_time=20.5)
        exec3 = ExecutionFactory.create(workflow=workflow, status="failed", total_execution_time=5.0)
        db_session.add_all([exec1, exec2, exec3])
        db_session.commit()

        # Act
        response = await authenticated_client.get("/workflows/stats/dashboard")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["total_executions"] == 3
        assert data["successful_executions"] == 2
        assert data["failed_executions"] == 1
        assert data["avg_execution_time"] is not None
        assert 10 < data["avg_execution_time"] < 15  # Average should be around 12

    async def test_dashboard_stats_only_user_data(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test dashboard stats only includes current user's data"""
        # Arrange
        other_user = UserFactory.create(username="otheruser")
        db_session.add(other_user)
        db_session.commit()

        user_workflow = WorkflowFactory.create(owner=test_user)
        other_workflow = WorkflowFactory.create(owner=other_user)
        db_session.add_all([user_workflow, other_workflow])
        db_session.commit()

        # Act
        response = await authenticated_client.get("/workflows/stats/dashboard")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["total_workflows"] == 1

    async def test_dashboard_stats_unauthenticated(self, client: AsyncClient):
        """Test dashboard stats without authentication fails"""
        # Act
        response = await client.get("/workflows/stats/dashboard")

        # Assert
        assert response.status_code == 401


@pytest.mark.asyncio
class TestExportWorkflowEndpoint:
    """Test GET /workflows/{workflow_id}/export endpoint"""

    async def test_export_workflow_success(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test successful workflow export"""
        # Arrange
        workflow = WorkflowFactory.create(
            owner=test_user,
            name="Export Workflow",
            description="Test export",
            universal_rules="Be nice"
        )
        component1 = ComponentFactory.create(workflow=workflow, name="Component 1", order=0)
        component2 = ComponentFactory.create(workflow=workflow, name="Component 2", order=1)
        db_session.add_all([workflow, component1, component2])
        db_session.commit()

        connection = ConnectionFactory.create(
            workflow=workflow,
            from_component=component1,
            to_component=component2,
            condition="success"
        )
        db_session.add(connection)
        db_session.commit()

        # Act
        response = await authenticated_client.get(f"/workflows/{workflow.id}/export")

        # Assert
        assert response.status_code == 200
        data = response.json()

        # Check workflow data
        assert "workflow" in data
        assert data["workflow"]["name"] == "Export Workflow"
        assert data["workflow"]["description"] == "Test export"
        assert data["workflow"]["universal_rules"] == "Be nice"

        # Check components
        assert "components" in data
        assert len(data["components"]) == 2
        assert any(c["name"] == "Component 1" for c in data["components"])
        assert any(c["name"] == "Component 2" for c in data["components"])
        assert all("original_id" in c for c in data["components"])

        # Check connections
        assert "connections" in data
        assert len(data["connections"]) == 1
        assert data["connections"][0]["condition"] == "success"

    async def test_export_workflow_not_found(self, authenticated_client: AsyncClient):
        """Test exporting non-existent workflow"""
        # Act
        response = await authenticated_client.get("/workflows/99999/export")

        # Assert
        assert response.status_code == 404

    async def test_export_workflow_unauthorized(self, authenticated_client: AsyncClient, db_session):
        """Test exporting workflow owned by another user fails"""
        # Arrange
        other_user = UserFactory.create(username="otheruser")
        workflow = WorkflowFactory.create(owner=other_user)
        db_session.add_all([other_user, workflow])
        db_session.commit()

        # Act
        response = await authenticated_client.get(f"/workflows/{workflow.id}/export")

        # Assert
        assert response.status_code == 404

    async def test_export_workflow_empty(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test exporting workflow with no components or connections"""
        # Arrange
        workflow = WorkflowFactory.create(owner=test_user)
        db_session.add(workflow)
        db_session.commit()

        # Act
        response = await authenticated_client.get(f"/workflows/{workflow.id}/export")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["components"] == []
        assert data["connections"] == []


@pytest.mark.asyncio
class TestImportWorkflowEndpoint:
    """Test POST /workflows/{workflow_id}/import endpoint"""

    async def test_import_workflow_success(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test successful workflow import"""
        # Arrange
        workflow = WorkflowFactory.create(owner=test_user)
        db_session.add(workflow)
        db_session.commit()

        import_data = {
            "workflow": {
                "name": "Imported Workflow",
                "description": "Imported description",
                "universal_rules": "Imported rules"
            },
            "components": [
                {
                    "type": "input_sources",
                    "name": "Input",
                    "description": "Input component",
                    "configuration": {"test": "config"},
                    "position_x": 100,
                    "position_y": 200,
                    "order": 0,
                    "original_id": 1
                },
                {
                    "type": "text_generation",
                    "name": "Generator",
                    "description": "Generate text",
                    "configuration": {},
                    "position_x": 300,
                    "position_y": 200,
                    "order": 1,
                    "original_id": 2
                }
            ],
            "connections": [
                {
                    "from_component_original_id": 1,
                    "to_component_original_id": 2,
                    "condition": "always"
                }
            ]
        }

        # Act
        response = await authenticated_client.post(f"/workflows/{workflow.id}/import", json=import_data)

        # Assert
        assert response.status_code == 200
        assert "imported successfully" in response.json()["message"].lower()

        # Verify the workflow was updated
        verify_response = await authenticated_client.get(f"/workflows/{workflow.id}")
        verify_data = verify_response.json()
        assert verify_data["name"] == "Imported Workflow"
        assert verify_data["description"] == "Imported description"
        assert len(verify_data["components"]) == 2

    async def test_import_workflow_replaces_existing(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test that import replaces existing components and connections"""
        # Arrange
        workflow = WorkflowFactory.create(owner=test_user)
        old_component = ComponentFactory.create(workflow=workflow, name="Old Component")
        db_session.add_all([workflow, old_component])
        db_session.commit()

        import_data = {
            "workflow": {"name": "Replaced"},
            "components": [
                {
                    "type": "input_sources",
                    "name": "New Component",
                    "configuration": {},
                    "position_x": 0,
                    "position_y": 0,
                    "order": 0,
                    "original_id": 1
                }
            ],
            "connections": []
        }

        # Act
        response = await authenticated_client.post(f"/workflows/{workflow.id}/import", json=import_data)

        # Assert
        assert response.status_code == 200

        # Verify old components are gone
        verify_response = await authenticated_client.get(f"/workflows/{workflow.id}")
        verify_data = verify_response.json()
        assert len(verify_data["components"]) == 1
        assert verify_data["components"][0]["name"] == "New Component"

    async def test_import_workflow_not_found(self, authenticated_client: AsyncClient):
        """Test importing to non-existent workflow"""
        # Arrange
        import_data = {
            "workflow": {"name": "Test"},
            "components": [],
            "connections": []
        }

        # Act
        response = await authenticated_client.post("/workflows/99999/import", json=import_data)

        # Assert
        assert response.status_code == 404

    async def test_import_workflow_unauthorized(self, authenticated_client: AsyncClient, db_session):
        """Test importing to workflow owned by another user fails"""
        # Arrange
        other_user = UserFactory.create(username="otheruser")
        workflow = WorkflowFactory.create(owner=other_user)
        db_session.add_all([other_user, workflow])
        db_session.commit()

        import_data = {
            "workflow": {"name": "Hacked"},
            "components": [],
            "connections": []
        }

        # Act
        response = await authenticated_client.post(f"/workflows/{workflow.id}/import", json=import_data)

        # Assert
        assert response.status_code == 404

    async def test_import_workflow_invalid_data(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test importing with invalid data structure"""
        # Arrange
        workflow = WorkflowFactory.create(owner=test_user)
        db_session.add(workflow)
        db_session.commit()

        invalid_data = {
            "workflow": {"name": "Test"},
            "components": "invalid",  # Should be array
            "connections": []
        }

        # Act
        response = await authenticated_client.post(f"/workflows/{workflow.id}/import", json=invalid_data)

        # Assert
        assert response.status_code == 422

    async def test_import_workflow_remaps_thread_parent_component_id(
        self, authenticated_client: AsyncClient, db_session, test_user
    ):
        """Threaded email config must preserve parent linkage after import by remapping ids."""
        workflow = WorkflowFactory.create(owner=test_user)
        db_session.add(workflow)
        db_session.commit()

        import_data = {
            "workflow": {
                "name": "Threaded Import",
                "description": "Preserve threading",
            },
            "components": [
                {
                    "type": "input_sources",
                    "name": "Input",
                    "configuration": {},
                    "position_x": 0,
                    "position_y": 0,
                    "order": 0,
                    "original_id": 100,
                },
                {
                    "type": "email",
                    "name": "Email A",
                    "configuration": {"send_as": "new_thread"},
                    "position_x": 100,
                    "position_y": 0,
                    "order": 1,
                    "original_id": 101,
                },
                {
                    "type": "email",
                    "name": "Email B",
                    "configuration": {
                        "send_as": "reply_to_component",
                        "thread_parent_component_id": 101,
                    },
                    "position_x": 200,
                    "position_y": 0,
                    "order": 2,
                    "original_id": 102,
                },
            ],
            "connections": [],
        }

        response = await authenticated_client.post(
            f"/workflows/{workflow.id}/import",
            json=import_data,
        )
        assert response.status_code == 200

        verify_response = await authenticated_client.get(f"/workflows/{workflow.id}")
        assert verify_response.status_code == 200
        components = verify_response.json()["components"]

        parent = next(c for c in components if c["name"] == "Email A")
        child = next(c for c in components if c["name"] == "Email B")

        assert child["configuration"]["send_as"] == "reply_to_component"
        assert child["configuration"]["thread_parent_component_id"] == parent["id"]

    async def test_import_workflow_accepts_legacy_connection_keys(
        self, authenticated_client: AsyncClient, db_session, test_user
    ):
        """Import should accept legacy connection keys for backward compatibility."""
        workflow = WorkflowFactory.create(owner=test_user)
        db_session.add(workflow)
        db_session.commit()

        import_data = {
            "workflow": {
                "name": "Legacy Connection Import",
            },
            "components": [
                {
                    "type": "input_sources",
                    "name": "Input",
                    "configuration": {},
                    "position_x": 0,
                    "position_y": 0,
                    "order": 0,
                    "original_id": 10,
                },
                {
                    "type": "text_generation",
                    "name": "Generator",
                    "configuration": {},
                    "position_x": 100,
                    "position_y": 0,
                    "order": 1,
                    "original_id": 11,
                },
            ],
            "connections": [
                {
                    "from_component_id": 10,
                    "to_component_id": 11,
                    "condition": "always",
                }
            ],
        }

        response = await authenticated_client.post(
            f"/workflows/{workflow.id}/import",
            json=import_data,
        )
        assert response.status_code == 200

        imported_components = db_session.query(models.Component).filter(
            models.Component.workflow_id == workflow.id
        ).all()
        imported_component_ids = [component.id for component in imported_components]

        imported_connections = db_session.query(models.Connection).filter(
            models.Connection.from_component_id.in_(imported_component_ids),
            models.Connection.to_component_id.in_(imported_component_ids),
        ).all()
        assert len(imported_connections) == 1


@pytest.mark.asyncio
class TestValidateWorkflowEndpoint:
    async def test_validate_workflow_returns_valid_for_prior_email_reference(
        self, authenticated_client: AsyncClient, db_session, test_user
    ):
        workflow = WorkflowFactory.create(owner=test_user)
        input_component = ComponentFactory.create(workflow=workflow, type="input_sources", order=0)
        parent = ComponentFactory.create(workflow=workflow, type="email", order=1, configuration={"send_as": "new_thread"})
        child = ComponentFactory.create(
            workflow=workflow,
            type="email",
            order=2,
            configuration={
                "send_as": "reply_to_component",
                "thread_parent_component_id": parent.id,
            },
        )
        db_session.add_all([workflow, input_component, parent, child])
        db_session.commit()

        response = await authenticated_client.post(f"/workflows/{workflow.id}/validate")

        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
        assert data["errors"] == []

    async def test_validate_workflow_returns_error_for_future_email_reference(
        self, authenticated_client: AsyncClient, db_session, test_user
    ):
        workflow = WorkflowFactory.create(owner=test_user)
        input_component = ComponentFactory.create(workflow=workflow, type="input_sources", order=0)
        child = ComponentFactory.create(
            workflow=workflow,
            type="email",
            order=1,
            configuration={
                "send_as": "reply_to_component",
            },
        )
        parent = ComponentFactory.create(workflow=workflow, type="email", order=2, configuration={"send_as": "new_thread"})
        child.configuration["thread_parent_component_id"] = parent.id
        db_session.add_all([workflow, input_component, child, parent])
        db_session.commit()

        response = await authenticated_client.post(f"/workflows/{workflow.id}/validate")

        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert len(data["errors"]) == 1
        assert data["errors"][0]["component_id"] == child.id
        assert "earlier email component" in data["errors"][0]["message"]
