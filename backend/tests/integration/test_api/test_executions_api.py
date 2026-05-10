"""
Integration tests for executions API endpoints
Tests /executions/* endpoints with database interactions
"""
import pytest
from httpx import AsyncClient
from unittest.mock import patch, AsyncMock
from datetime import datetime

from tests.fixtures.factories import (
    UserFactory,
    WorkflowFactory,
    ComponentFactory,
    ExecutionFactory,
    ComponentExecutionFactory
)


@pytest.mark.asyncio
class TestListExecutionsEndpoint:
    """Test GET /executions/{workflow_id}/executions endpoint"""

    async def test_list_executions_success(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test listing executions for a workflow"""
        # Arrange
        workflow = WorkflowFactory.create(owner=test_user)
        exec1 = ExecutionFactory.create(workflow=workflow, status="completed")
        exec2 = ExecutionFactory.create(workflow=workflow, status="failed")
        db_session.add_all([workflow, exec1, exec2])
        db_session.commit()

        # Act
        response = await authenticated_client.get(f"/executions/{workflow.id}/executions")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert any(e["id"] == exec1.id for e in data)
        assert any(e["id"] == exec2.id for e in data)

    async def test_list_executions_with_component_executions(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test that executions include component execution details"""
        # Arrange
        workflow = WorkflowFactory.create(owner=test_user)
        component = ComponentFactory.create(workflow=workflow, name="Test Component")
        execution = ExecutionFactory.create(workflow=workflow)
        comp_exec = ComponentExecutionFactory.create(
            execution=execution,
            component=component,
            status="completed"
        )
        db_session.add_all([workflow, component, execution, comp_exec])
        db_session.commit()

        # Act
        response = await authenticated_client.get(f"/executions/{workflow.id}/executions")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert "component_executions" in data[0]
        assert len(data[0]["component_executions"]) == 1
        assert data[0]["component_executions"][0]["component_name"] == "Test Component"

    async def test_list_executions_ordered_by_recent(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test executions are returned in reverse chronological order"""
        # Arrange
        workflow = WorkflowFactory.create(owner=test_user)
        old_exec = ExecutionFactory.create(workflow=workflow)
        new_exec = ExecutionFactory.create(workflow=workflow)
        db_session.add_all([workflow, old_exec, new_exec])
        db_session.commit()

        # Act
        response = await authenticated_client.get(f"/executions/{workflow.id}/executions")

        # Assert
        assert response.status_code == 200
        data = response.json()
        # Most recent should be first
        assert data[0]["id"] == new_exec.id
        assert data[1]["id"] == old_exec.id

    async def test_list_executions_empty(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test listing executions when workflow has none"""
        # Arrange
        workflow = WorkflowFactory.create(owner=test_user)
        db_session.add(workflow)
        db_session.commit()

        # Act
        response = await authenticated_client.get(f"/executions/{workflow.id}/executions")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 0

    async def test_list_executions_workflow_not_found(self, authenticated_client: AsyncClient):
        """Test listing executions for non-existent workflow"""
        # Act
        response = await authenticated_client.get("/executions/99999/executions")

        # Assert
        assert response.status_code == 404

    async def test_list_executions_unauthorized(self, authenticated_client: AsyncClient, db_session):
        """Test listing executions for workflow owned by another user"""
        # Arrange
        other_user = UserFactory.create(username="otheruser")
        workflow = WorkflowFactory.create(owner=other_user)
        db_session.add_all([other_user, workflow])
        db_session.commit()

        # Act
        response = await authenticated_client.get(f"/executions/{workflow.id}/executions")

        # Assert
        assert response.status_code == 404


@pytest.mark.asyncio
class TestExecuteWorkflowEndpoint:
    """Test POST /executions/{workflow_id}/execute endpoint"""

    async def test_execute_workflow_success(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test successful workflow execution trigger"""
        # Arrange
        workflow = WorkflowFactory.create(owner=test_user)
        db_session.add(workflow)
        db_session.commit()

        execution_data = {
            "workflow_id": workflow.id,
            "test_mode": False
        }

        # Mock background execution
        with patch("executions.execute_workflow_background") as mock_bg:
            # Act
            response = await authenticated_client.post(
                f"/executions/{workflow.id}/execute",
                json=execution_data
            )

        # Assert
        assert response.status_code == 201
        data = response.json()
        assert data["workflow_id"] == workflow.id
        assert data["status"] == "running"
        assert "id" in data
        assert "started_at" in data

    async def test_execute_workflow_with_fireflies_transcript(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test workflow execution with Fireflies transcript"""
        # Arrange
        workflow = WorkflowFactory.create(owner=test_user)
        db_session.add(workflow)
        db_session.commit()

        execution_data = {
            "workflow_id": workflow.id,
            "fireflies_transcript_id": "trans_123",
            "test_mode": False
        }

        # Mock Fireflies service
        with patch("executions.fetch_transcript", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = {
                "transcript": "Sample transcript",
                "participants": ["John Doe"],
                "meeting_title": "Sales Call"
            }

            with patch("executions.execute_workflow_background"):
                # Act
                response = await authenticated_client.post(
                    f"/executions/{workflow.id}/execute",
                    json=execution_data
                )

        # Assert
        assert response.status_code == 201
        data = response.json()
        assert data["input_data"] is not None
        assert data["input_data"]["source"] == "fireflies_webhook"

    async def test_execute_workflow_test_mode(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test workflow execution in test mode"""
        # Arrange
        workflow = WorkflowFactory.create(owner=test_user)
        db_session.add(workflow)
        db_session.commit()

        execution_data = {
            "workflow_id": workflow.id,
            "test_mode": True
        }

        with patch("executions.execute_workflow_background"):
            # Act
            response = await authenticated_client.post(
                f"/executions/{workflow.id}/execute",
                json=execution_data
            )

        # Assert
        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "running"

    async def test_execute_workflow_not_found(self, authenticated_client: AsyncClient):
        """Test executing non-existent workflow"""
        # Arrange
        execution_data = {
            "workflow_id": 99999,
            "test_mode": False
        }

        # Act
        response = await authenticated_client.post(
            "/executions/99999/execute",
            json=execution_data
        )

        # Assert
        assert response.status_code == 404

    async def test_execute_workflow_unauthorized(self, authenticated_client: AsyncClient, db_session):
        """Test executing workflow owned by another user"""
        # Arrange
        other_user = UserFactory.create(username="otheruser")
        workflow = WorkflowFactory.create(owner=other_user)
        db_session.add_all([other_user, workflow])
        db_session.commit()

        execution_data = {
            "workflow_id": workflow.id,
            "test_mode": False
        }

        # Act
        response = await authenticated_client.post(
            f"/executions/{workflow.id}/execute",
            json=execution_data
        )

        # Assert
        assert response.status_code == 404


@pytest.mark.asyncio
class TestGetLatestExecutionEndpoint:
    """Test GET /executions/{workflow_id}/latest endpoint"""

    async def test_get_latest_execution_success(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test getting the most recent execution"""
        # Arrange
        workflow = WorkflowFactory.create(owner=test_user)
        old_exec = ExecutionFactory.create(workflow=workflow)
        latest_exec = ExecutionFactory.create(workflow=workflow)
        db_session.add_all([workflow, old_exec, latest_exec])
        db_session.commit()

        # Act
        response = await authenticated_client.get(f"/executions/{workflow.id}/latest")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == latest_exec.id

    async def test_get_latest_execution_with_components(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test latest execution includes component execution details"""
        # Arrange
        workflow = WorkflowFactory.create(owner=test_user)
        component = ComponentFactory.create(workflow=workflow, name="Component 1")
        execution = ExecutionFactory.create(workflow=workflow)
        comp_exec = ComponentExecutionFactory.create(
            execution=execution,
            component=component
        )
        db_session.add_all([workflow, component, execution, comp_exec])
        db_session.commit()

        # Act
        response = await authenticated_client.get(f"/executions/{workflow.id}/latest")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "component_executions" in data
        assert len(data["component_executions"]) == 1
        assert data["component_executions"][0]["component_name"] == "Component 1"

    async def test_get_latest_execution_not_found(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test getting latest execution when workflow has no executions"""
        # Arrange
        workflow = WorkflowFactory.create(owner=test_user)
        db_session.add(workflow)
        db_session.commit()

        # Act
        response = await authenticated_client.get(f"/executions/{workflow.id}/latest")

        # Assert
        assert response.status_code == 404
        assert "no executions" in response.json()["detail"].lower()

    async def test_get_latest_execution_workflow_not_found(self, authenticated_client: AsyncClient):
        """Test getting latest execution for non-existent workflow"""
        # Act
        response = await authenticated_client.get("/executions/99999/latest")

        # Assert
        assert response.status_code == 404


@pytest.mark.asyncio
class TestGetExecutionDetailsEndpoint:
    """Test GET /executions/{workflow_id}/executions/{execution_id} endpoint"""

    async def test_get_execution_details_success(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test getting specific execution details"""
        # Arrange
        workflow = WorkflowFactory.create(owner=test_user)
        execution = ExecutionFactory.create(
            workflow=workflow,
            status="completed",
            total_execution_time=1500
        )
        db_session.add_all([workflow, execution])
        db_session.commit()

        # Act
        response = await authenticated_client.get(
            f"/executions/{workflow.id}/executions/{execution.id}"
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == execution.id
        assert data["status"] == "completed"
        assert data["total_execution_time"] == 1500

    async def test_get_execution_details_with_components(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test execution details include component executions"""
        # Arrange
        workflow = WorkflowFactory.create(owner=test_user)
        comp1 = ComponentFactory.create(workflow=workflow, name="Comp 1")
        comp2 = ComponentFactory.create(workflow=workflow, name="Comp 2")
        execution = ExecutionFactory.create(workflow=workflow)
        comp_exec1 = ComponentExecutionFactory.create(
            execution=execution,
            component=comp1,
            status="completed"
        )
        comp_exec2 = ComponentExecutionFactory.create(
            execution=execution,
            component=comp2,
            status="completed"
        )
        db_session.add_all([workflow, comp1, comp2, execution, comp_exec1, comp_exec2])
        db_session.commit()

        # Act
        response = await authenticated_client.get(
            f"/executions/{workflow.id}/executions/{execution.id}"
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data["component_executions"]) == 2

    async def test_get_execution_details_with_error(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test getting execution details for failed execution"""
        # Arrange
        workflow = WorkflowFactory.create(owner=test_user)
        execution = ExecutionFactory.create(
            workflow=workflow,
            status="failed",
            error_message="Component X failed"
        )
        db_session.add_all([workflow, execution])
        db_session.commit()

        # Act
        response = await authenticated_client.get(
            f"/executions/{workflow.id}/executions/{execution.id}"
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "failed"
        assert data["error_message"] == "Component X failed"

    async def test_get_execution_details_not_found(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test getting non-existent execution"""
        # Arrange
        workflow = WorkflowFactory.create(owner=test_user)
        db_session.add(workflow)
        db_session.commit()

        # Act
        response = await authenticated_client.get(
            f"/executions/{workflow.id}/executions/99999"
        )

        # Assert
        assert response.status_code == 404

    async def test_get_execution_details_wrong_workflow(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test getting execution with mismatched workflow ID"""
        # Arrange
        workflow1 = WorkflowFactory.create(owner=test_user)
        workflow2 = WorkflowFactory.create(owner=test_user)
        execution = ExecutionFactory.create(workflow=workflow1)
        db_session.add_all([workflow1, workflow2, execution])
        db_session.commit()

        # Act - Try to access execution through wrong workflow
        response = await authenticated_client.get(
            f"/executions/{workflow2.id}/executions/{execution.id}"
        )

        # Assert
        assert response.status_code == 404

    async def test_get_execution_details_unauthorized(self, authenticated_client: AsyncClient, db_session):
        """Test getting execution for workflow owned by another user"""
        # Arrange
        other_user = UserFactory.create(username="otheruser")
        workflow = WorkflowFactory.create(owner=other_user)
        execution = ExecutionFactory.create(workflow=workflow)
        db_session.add_all([other_user, workflow, execution])
        db_session.commit()

        # Act
        response = await authenticated_client.get(
            f"/executions/{workflow.id}/executions/{execution.id}"
        )

        # Assert
        assert response.status_code == 404


@pytest.mark.asyncio
class TestExecutionStatsEndpoint:
    """Test GET /executions/{workflow_id}/executions/stats endpoint"""

    async def test_execution_stats_no_executions(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test stats when workflow has no executions"""
        # Arrange
        workflow = WorkflowFactory.create(owner=test_user)
        db_session.add(workflow)
        db_session.commit()

        # Act
        response = await authenticated_client.get(f"/executions/{workflow.id}/executions/stats")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["total_executions"] == 0
        assert data["successful_executions"] == 0
        assert data["failed_executions"] == 0
        assert data["running_executions"] == 0
        assert data["avg_execution_time"] is None

    async def test_execution_stats_with_executions(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test stats with various execution statuses"""
        # Arrange
        workflow = WorkflowFactory.create(owner=test_user)
        exec1 = ExecutionFactory.create(workflow=workflow, status="completed", total_execution_time=1000)
        exec2 = ExecutionFactory.create(workflow=workflow, status="completed", total_execution_time=2000)
        exec3 = ExecutionFactory.create(workflow=workflow, status="failed")
        exec4 = ExecutionFactory.create(workflow=workflow, status="running")
        db_session.add_all([workflow, exec1, exec2, exec3, exec4])
        db_session.commit()

        # Act
        response = await authenticated_client.get(f"/executions/{workflow.id}/executions/stats")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["total_executions"] == 4
        assert data["successful_executions"] == 2
        assert data["failed_executions"] == 1
        assert data["running_executions"] == 1
        assert data["avg_execution_time"] is not None
        assert 1000 <= data["avg_execution_time"] <= 2000

    async def test_execution_stats_avg_calculation(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test average execution time calculation"""
        # Arrange
        workflow = WorkflowFactory.create(owner=test_user)
        exec1 = ExecutionFactory.create(workflow=workflow, status="completed", total_execution_time=1000)
        exec2 = ExecutionFactory.create(workflow=workflow, status="completed", total_execution_time=3000)
        db_session.add_all([workflow, exec1, exec2])
        db_session.commit()

        # Act
        response = await authenticated_client.get(f"/executions/{workflow.id}/executions/stats")

        # Assert
        assert response.status_code == 200
        data = response.json()
        # Average of 1000 and 3000 should be 2000
        assert data["avg_execution_time"] == 2000.0

    async def test_execution_stats_workflow_not_found(self, authenticated_client: AsyncClient):
        """Test stats for non-existent workflow"""
        # Act
        response = await authenticated_client.get("/executions/99999/executions/stats")

        # Assert
        assert response.status_code == 404

    async def test_execution_stats_unauthorized(self, authenticated_client: AsyncClient, db_session):
        """Test stats for workflow owned by another user"""
        # Arrange
        other_user = UserFactory.create(username="otheruser")
        workflow = WorkflowFactory.create(owner=other_user)
        db_session.add_all([other_user, workflow])
        db_session.commit()

        # Act
        response = await authenticated_client.get(f"/executions/{workflow.id}/executions/stats")

        # Assert
        assert response.status_code == 404
