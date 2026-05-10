"""
Integration tests for components API endpoints
Tests /components/* endpoints with database interactions
"""
import pytest
from httpx import AsyncClient
from unittest.mock import patch, AsyncMock

from tests.fixtures.factories import UserFactory, WorkflowFactory, ComponentFactory, ConnectionFactory, ExecutionFactory, ComponentExecutionFactory


@pytest.mark.asyncio
class TestGetComponentTypesEndpoint:
    """Test GET /components/types endpoint"""

    async def test_get_component_types_success(self, client: AsyncClient):
        """Test getting all component types"""
        # Act
        response = await client.get("/components/types")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
        assert "input_sources" in data
        assert "text_generation" in data
        assert "email" in data
        assert "conditional_logic" in data
        assert "ai_filter" in data
        assert "action" in data

    async def test_get_component_types_structure(self, client: AsyncClient):
        """Test component types have correct structure"""
        # Act
        response = await client.get("/components/types")

        # Assert
        assert response.status_code == 200
        data = response.json()

        for comp_type, metadata in data.items():
            assert "name" in metadata
            assert "description" in metadata
            assert "icon" in metadata
            assert "category" in metadata


@pytest.mark.asyncio
class TestListWorkflowComponentsEndpoint:
    """Test GET /components/{workflow_id}/components endpoint"""

    async def test_list_components_success(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test listing components for a workflow"""
        # Arrange
        workflow = WorkflowFactory.create(owner=test_user)
        comp1 = ComponentFactory.create(workflow=workflow, name="First", order=0)
        comp2 = ComponentFactory.create(workflow=workflow, name="Second", order=1)
        db_session.add_all([workflow, comp1, comp2])
        db_session.commit()

        # Act
        response = await authenticated_client.get(f"/components/{workflow.id}/components")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["name"] == "First"
        assert data[1]["name"] == "Second"

    async def test_list_components_ordered(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test components are returned in order"""
        # Arrange
        workflow = WorkflowFactory.create(owner=test_user)
        comp3 = ComponentFactory.create(workflow=workflow, name="Third", order=3)
        comp1 = ComponentFactory.create(workflow=workflow, name="First", order=1)
        comp2 = ComponentFactory.create(workflow=workflow, name="Second", order=2)
        db_session.add_all([workflow, comp3, comp1, comp2])
        db_session.commit()

        # Act
        response = await authenticated_client.get(f"/components/{workflow.id}/components")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3
        assert data[0]["order"] == 1
        assert data[1]["order"] == 2
        assert data[2]["order"] == 3

    async def test_list_components_empty(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test listing components for workflow with no components"""
        # Arrange
        workflow = WorkflowFactory.create(owner=test_user)
        db_session.add(workflow)
        db_session.commit()

        # Act
        response = await authenticated_client.get(f"/components/{workflow.id}/components")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 0

    async def test_list_components_workflow_not_found(self, authenticated_client: AsyncClient):
        """Test listing components for non-existent workflow"""
        # Act
        response = await authenticated_client.get("/components/99999/components")

        # Assert
        assert response.status_code == 404

    async def test_list_components_unauthorized(self, authenticated_client: AsyncClient, db_session):
        """Test listing components for workflow owned by another user"""
        # Arrange
        other_user = UserFactory.create(username="otheruser")
        workflow = WorkflowFactory.create(owner=other_user)
        db_session.add_all([other_user, workflow])
        db_session.commit()

        # Act
        response = await authenticated_client.get(f"/components/{workflow.id}/components")

        # Assert
        assert response.status_code == 404


@pytest.mark.asyncio
class TestCreateComponentEndpoint:
    """Test POST /components/{workflow_id}/components endpoint"""

    async def test_create_component_success(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test successful component creation"""
        # Arrange
        workflow = WorkflowFactory.create(owner=test_user)
        db_session.add(workflow)
        db_session.commit()

        component_data = {
            "type": "text_generation",
            "name": "Test Component",
            "description": "Test description",
            "configuration": {"test": "config"},
            "position_x": 100,
            "position_y": 200
        }

        # Act
        response = await authenticated_client.post(
            f"/components/{workflow.id}/components",
            json=component_data
        )

        # Assert
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Test Component"
        assert data["type"] == "text_generation"
        assert data["workflow_id"] == workflow.id
        assert "id" in data

    async def test_create_component_auto_assigns_order(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test that component order is auto-assigned"""
        # Arrange
        workflow = WorkflowFactory.create(owner=test_user)
        existing = ComponentFactory.create(workflow=workflow, order=0)
        db_session.add_all([workflow, existing])
        db_session.commit()

        component_data = {
            "type": "text_generation",
            "name": "Auto Order Component"
        }

        # Act
        response = await authenticated_client.post(
            f"/components/{workflow.id}/components",
            json=component_data
        )

        # Assert
        assert response.status_code == 201
        data = response.json()
        assert data["order"] == 1  # Should be auto-assigned next order

    async def test_create_component_invalid_type(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test creating component with invalid type"""
        # Arrange
        workflow = WorkflowFactory.create(owner=test_user)
        db_session.add(workflow)
        db_session.commit()

        component_data = {
            "type": "invalid_type",
            "name": "Invalid Component"
        }

        # Act
        response = await authenticated_client.post(
            f"/components/{workflow.id}/components",
            json=component_data
        )

        # Assert
        assert response.status_code == 400
        assert "invalid component type" in response.json()["detail"].lower()

    async def test_create_duplicate_input_source_fails(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test that only one input source is allowed per workflow"""
        # Arrange
        workflow = WorkflowFactory.create(owner=test_user)
        existing_input = ComponentFactory.create(workflow=workflow, type="input_sources", order=0)
        db_session.add_all([workflow, existing_input])
        db_session.commit()

        component_data = {
            "type": "input_sources",
            "name": "Duplicate Input Source"
        }

        # Act
        response = await authenticated_client.post(
            f"/components/{workflow.id}/components",
            json=component_data
        )

        # Assert
        assert response.status_code == 400
        assert "only one input source" in response.json()["detail"].lower()

    async def test_create_ai_filter_with_default_config(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test that ai_filter components get default configuration"""
        # Arrange
        workflow = WorkflowFactory.create(owner=test_user)
        db_session.add(workflow)
        db_session.commit()

        component_data = {
            "type": "ai_filter",
            "name": "AI Filter Component"
        }

        # Act
        response = await authenticated_client.post(
            f"/components/{workflow.id}/components",
            json=component_data
        )

        # Assert
        assert response.status_code == 201
        data = response.json()
        assert "configuration" in data
        assert "ai_prompt" in data["configuration"]
        assert "condition_operator" in data["configuration"]


@pytest.mark.asyncio
class TestUpdateComponentEndpoint:
    """Test PUT /components/{workflow_id}/components/{component_id} endpoint"""

    async def test_update_component_success(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test successful component update"""
        # Arrange
        workflow = WorkflowFactory.create(owner=test_user)
        component = ComponentFactory.create(workflow=workflow, name="Original")
        db_session.add_all([workflow, component])
        db_session.commit()

        update_data = {
            "name": "Updated Name",
            "description": "Updated description"
        }

        # Act
        response = await authenticated_client.put(
            f"/components/{workflow.id}/components/{component.id}",
            json=update_data
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Name"
        assert data["description"] == "Updated description"

    async def test_update_component_partial(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test partial component update"""
        # Arrange
        workflow = WorkflowFactory.create(owner=test_user)
        component = ComponentFactory.create(
            workflow=workflow,
            name="Original",
            description="Original desc"
        )
        db_session.add_all([workflow, component])
        db_session.commit()

        update_data = {"name": "Updated Only"}

        # Act
        response = await authenticated_client.put(
            f"/components/{workflow.id}/components/{component.id}",
            json=update_data
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Only"
        assert data["description"] == "Original desc"

    async def test_update_input_source_order_fails(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test that input source order cannot be changed from 0"""
        # Arrange
        workflow = WorkflowFactory.create(owner=test_user)
        component = ComponentFactory.create(workflow=workflow, type="input_sources", order=0)
        db_session.add_all([workflow, component])
        db_session.commit()

        update_data = {"order": 1}

        # Act
        response = await authenticated_client.put(
            f"/components/{workflow.id}/components/{component.id}",
            json=update_data
        )

        # Assert
        assert response.status_code == 400
        assert "must always be at order 0" in response.json()["detail"].lower()

    async def test_update_non_input_to_order_zero_fails(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test that non-input components cannot have order 0"""
        # Arrange
        workflow = WorkflowFactory.create(owner=test_user)
        component = ComponentFactory.create(workflow=workflow, type="text_generation", order=1)
        db_session.add_all([workflow, component])
        db_session.commit()

        update_data = {"order": 0}

        # Act
        response = await authenticated_client.put(
            f"/components/{workflow.id}/components/{component.id}",
            json=update_data
        )

        # Assert
        assert response.status_code == 400
        assert "only input source" in response.json()["detail"].lower()

    async def test_update_component_not_found(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test updating non-existent component"""
        # Arrange
        workflow = WorkflowFactory.create(owner=test_user)
        db_session.add(workflow)
        db_session.commit()

        # Act
        response = await authenticated_client.put(
            f"/components/{workflow.id}/components/99999",
            json={"name": "Updated"}
        )

        # Assert
        assert response.status_code == 404


@pytest.mark.asyncio
class TestDeleteComponentEndpoint:
    """Test DELETE /components/{workflow_id}/components/{component_id} endpoint"""

    async def test_delete_component_success(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test successful component deletion"""
        # Arrange
        workflow = WorkflowFactory.create(owner=test_user)
        component = ComponentFactory.create(workflow=workflow, type="text_generation")
        db_session.add_all([workflow, component])
        db_session.commit()
        component_id = component.id

        # Act
        response = await authenticated_client.delete(
            f"/components/{workflow.id}/components/{component_id}"
        )

        # Assert
        assert response.status_code == 200
        assert "deleted successfully" in response.json()["message"].lower()

    async def test_delete_input_source_fails(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test that input source components cannot be deleted"""
        # Arrange
        workflow = WorkflowFactory.create(owner=test_user)
        component = ComponentFactory.create(workflow=workflow, type="input_sources", order=0)
        db_session.add_all([workflow, component])
        db_session.commit()

        # Act
        response = await authenticated_client.delete(
            f"/components/{workflow.id}/components/{component.id}"
        )

        # Assert
        assert response.status_code == 400
        assert "cannot be deleted" in response.json()["detail"].lower()

    async def test_delete_component_not_found(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test deleting non-existent component"""
        # Arrange
        workflow = WorkflowFactory.create(owner=test_user)
        db_session.add(workflow)
        db_session.commit()

        # Act
        response = await authenticated_client.delete(
            f"/components/{workflow.id}/components/99999"
        )

        # Assert
        assert response.status_code == 404


@pytest.mark.asyncio
class TestUpdateComponentConfigEndpoint:
    """Test PUT /components/{component_id}/config endpoint"""

    async def test_update_config_success(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test successful config update"""
        # Arrange
        workflow = WorkflowFactory.create(owner=test_user)
        component = ComponentFactory.create(
            workflow=workflow,
            configuration={"old": "config"}
        )
        db_session.add_all([workflow, component])
        db_session.commit()

        config_data = {
            "configuration": {"new": "config", "updated": True}
        }

        # Act
        response = await authenticated_client.put(
            f"/components/{component.id}/config",
            json=config_data
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["configuration"]["new"] == "config"
        assert data["configuration"]["updated"] is True
        assert "old" not in data["configuration"]

    async def test_update_config_component_not_found(self, authenticated_client: AsyncClient):
        """Test updating config for non-existent component"""
        # Act
        response = await authenticated_client.put(
            "/components/99999/config",
            json={"configuration": {}}
        )

        # Assert
        assert response.status_code == 404

    async def test_update_email_config_rejects_future_thread_parent(self, authenticated_client: AsyncClient, db_session, test_user):
        """Thread parent must point to an earlier email component in the same workflow."""
        workflow = WorkflowFactory.create(owner=test_user)
        parent = ComponentFactory.create(workflow=workflow, type="email", order=3)
        child = ComponentFactory.create(workflow=workflow, type="email", order=2, configuration={})
        db_session.add_all([workflow, parent, child])
        db_session.commit()

        response = await authenticated_client.put(
            f"/components/{child.id}/config",
            json={
                "configuration": {
                    "send_as": "reply_to_component",
                    "thread_parent_component_id": parent.id,
                }
            }
        )

        assert response.status_code == 400
        assert "earlier email component" in response.json()["detail"]

    async def test_update_email_config_accepts_prior_thread_parent(self, authenticated_client: AsyncClient, db_session, test_user):
        """Valid threaded email config should be accepted."""
        workflow = WorkflowFactory.create(owner=test_user)
        parent = ComponentFactory.create(workflow=workflow, type="email", order=1)
        child = ComponentFactory.create(workflow=workflow, type="email", order=2, configuration={})
        db_session.add_all([workflow, parent, child])
        db_session.commit()

        response = await authenticated_client.put(
            f"/components/{child.id}/config",
            json={
                "configuration": {
                    "send_as": "reply_to_component",
                    "thread_parent_component_id": parent.id,
                }
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["configuration"]["send_as"] == "reply_to_component"
        assert data["configuration"]["thread_parent_component_id"] == parent.id


@pytest.mark.asyncio
class TestListConnectionsEndpoint:
    """Test GET /components/{workflow_id}/connections endpoint"""

    async def test_list_connections_success(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test listing connections for a workflow"""
        # Arrange
        workflow = WorkflowFactory.create(owner=test_user)
        comp1 = ComponentFactory.create(workflow=workflow)
        comp2 = ComponentFactory.create(workflow=workflow)
        connection = ConnectionFactory.create(
            workflow=workflow,
            from_component=comp1,
            to_component=comp2
        )
        db_session.add_all([workflow, comp1, comp2, connection])
        db_session.commit()

        # Act
        response = await authenticated_client.get(f"/components/{workflow.id}/connections")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["from_component_id"] == comp1.id
        assert data[0]["to_component_id"] == comp2.id

    async def test_list_connections_empty(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test listing connections for workflow with no connections"""
        # Arrange
        workflow = WorkflowFactory.create(owner=test_user)
        db_session.add(workflow)
        db_session.commit()

        # Act
        response = await authenticated_client.get(f"/components/{workflow.id}/connections")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 0

    async def test_list_connections_workflow_not_found(self, authenticated_client: AsyncClient):
        """Test listing connections for non-existent workflow"""
        # Act
        response = await authenticated_client.get("/components/99999/connections")

        # Assert
        assert response.status_code == 404


@pytest.mark.asyncio
class TestCreateConnectionEndpoint:
    """Test POST /components/{workflow_id}/connections endpoint"""

    async def test_create_connection_success(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test successful connection creation"""
        # Arrange
        workflow = WorkflowFactory.create(owner=test_user)
        comp1 = ComponentFactory.create(workflow=workflow)
        comp2 = ComponentFactory.create(workflow=workflow)
        db_session.add_all([workflow, comp1, comp2])
        db_session.commit()

        connection_data = {
            "from_component_id": comp1.id,
            "to_component_id": comp2.id,
            "condition": "success"
        }

        # Act
        response = await authenticated_client.post(
            f"/components/{workflow.id}/connections",
            json=connection_data
        )

        # Assert
        assert response.status_code == 201
        data = response.json()
        assert data["from_component_id"] == comp1.id
        assert data["to_component_id"] == comp2.id
        assert data["condition"] == "success"

    async def test_create_connection_without_condition(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test creating connection without condition"""
        # Arrange
        workflow = WorkflowFactory.create(owner=test_user)
        comp1 = ComponentFactory.create(workflow=workflow)
        comp2 = ComponentFactory.create(workflow=workflow)
        db_session.add_all([workflow, comp1, comp2])
        db_session.commit()

        connection_data = {
            "from_component_id": comp1.id,
            "to_component_id": comp2.id
        }

        # Act
        response = await authenticated_client.post(
            f"/components/{workflow.id}/connections",
            json=connection_data
        )

        # Assert
        assert response.status_code == 201
        data = response.json()
        assert data["condition"] is None

    async def test_create_connection_components_not_in_workflow(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test creating connection with components from different workflow"""
        # Arrange
        workflow1 = WorkflowFactory.create(owner=test_user)
        workflow2 = WorkflowFactory.create(owner=test_user)
        comp1 = ComponentFactory.create(workflow=workflow1)
        comp2 = ComponentFactory.create(workflow=workflow2)
        db_session.add_all([workflow1, workflow2, comp1, comp2])
        db_session.commit()

        connection_data = {
            "from_component_id": comp1.id,
            "to_component_id": comp2.id
        }

        # Act
        response = await authenticated_client.post(
            f"/components/{workflow1.id}/connections",
            json=connection_data
        )

        # Assert
        assert response.status_code == 400
        assert "must belong to" in response.json()["detail"].lower()


@pytest.mark.asyncio
class TestDeleteConnectionEndpoint:
    """Test DELETE /components/{workflow_id}/connections/{connection_id} endpoint"""

    async def test_delete_connection_success(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test successful connection deletion"""
        # Arrange
        workflow = WorkflowFactory.create(owner=test_user)
        comp1 = ComponentFactory.create(workflow=workflow)
        comp2 = ComponentFactory.create(workflow=workflow)
        connection = ConnectionFactory.create(
            workflow=workflow,
            from_component=comp1,
            to_component=comp2
        )
        db_session.add_all([workflow, comp1, comp2, connection])
        db_session.commit()
        connection_id = connection.id

        # Act
        response = await authenticated_client.delete(
            f"/components/{workflow.id}/connections/{connection_id}"
        )

        # Assert
        assert response.status_code == 200
        assert "deleted successfully" in response.json()["message"].lower()

    async def test_delete_connection_not_found(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test deleting non-existent connection"""
        # Arrange
        workflow = WorkflowFactory.create(owner=test_user)
        db_session.add(workflow)
        db_session.commit()

        # Act
        response = await authenticated_client.delete(
            f"/components/{workflow.id}/connections/99999"
        )

        # Assert
        assert response.status_code == 404


@pytest.mark.asyncio
class TestComponentTestEndpoint:
    """Test POST /components/{component_id}/test endpoint"""

    async def test_component_test_with_custom_data(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test component with custom test data"""
        # Arrange
        workflow = WorkflowFactory.create(owner=test_user)
        component = ComponentFactory.create(
            workflow=workflow,
            type="text_generation",
            configuration={"prompt": "Test prompt"}
        )
        db_session.add_all([workflow, component])
        db_session.commit()

        test_data = {
            "test_data": {"sample": "data", "test": True}
        }

        # Mock the component executor
        with patch("components.ComponentExecutor.execute_component", new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = {"status": "success", "output": "test output"}

            # Act
            response = await authenticated_client.post(
                f"/components/{component.id}/test",
                json=test_data
            )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["component_id"] == component.id
        assert "results" in data

    async def test_component_test_no_execution_data(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test component when no execution data is available"""
        # Arrange
        workflow = WorkflowFactory.create(owner=test_user)
        component = ComponentFactory.create(workflow=workflow, type="text_generation")
        db_session.add_all([workflow, component])
        db_session.commit()

        # Act (no test_data, no recent execution)
        response = await authenticated_client.post(f"/components/{component.id}/test")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "no workflow execution data" in data["error"].lower()

    async def test_component_test_not_found(self, authenticated_client: AsyncClient):
        """Test testing non-existent component"""
        # Act
        response = await authenticated_client.post("/components/99999/test")

        # Assert
        assert response.status_code == 404


@pytest.mark.asyncio
class TestPipedriveFieldsEndpoint:
    """Test GET /components/pipedrive/fields/{action_type} endpoint"""

    async def test_get_pipedrive_fields_success(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test getting Pipedrive fields"""
        # Mock the pipedrive service
        with patch("components.get_available_fields", new_callable=AsyncMock) as mock_fields:
            mock_fields.return_value = {
                "success": True,
                "fields": [
                    {"key": "title", "name": "Deal Title", "field_type": "varchar"}
                ]
            }

            # Act
            response = await authenticated_client.get("/components/pipedrive/fields/deal")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "fields" in data
        assert len(data["fields"]) == 1

    async def test_get_pipedrive_fields_error(self, authenticated_client: AsyncClient):
        """Test getting Pipedrive fields when service fails"""
        # Mock the pipedrive service to fail
        with patch("components.get_available_fields", new_callable=AsyncMock) as mock_fields:
            mock_fields.return_value = {
                "success": False,
                "error": "API key not found"
            }

            # Act
            response = await authenticated_client.get("/components/pipedrive/fields/deal")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "error" in data


@pytest.mark.asyncio
class TestClearPipedriveCacheEndpoint:
    """Test POST /components/pipedrive/cache/clear endpoint"""

    async def test_clear_pipedrive_cache_success(self, authenticated_client: AsyncClient):
        """Test clearing Pipedrive cache"""
        # Mock the cache service
        with patch("components.cache_clear_pattern") as mock_clear:
            mock_clear.return_value = 5

            # Act
            response = await authenticated_client.post("/components/pipedrive/cache/clear")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["cache_cleared"] is True


@pytest.mark.asyncio
class TestPipedriveStagesEndpoint:
    """Test GET /components/pipedrive/stages endpoint"""

    async def test_get_pipedrive_stages_success(self, authenticated_client: AsyncClient):
        """Test getting Pipedrive stages"""
        # Mock the pipedrive service
        with patch("components.get_deal_stages", new_callable=AsyncMock) as mock_stages:
            mock_stages.return_value = {
                "success": True,
                "stages": {1: "Lead", 2: "Qualified", 3: "Won"}
            }

            # Act
            response = await authenticated_client.get("/components/pipedrive/stages")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "stages" in data
        assert "Lead" in data["stages"]


@pytest.mark.asyncio
class TestPipedriveUsersEndpoint:
    """Test GET /components/pipedrive/users endpoint"""

    async def test_get_pipedrive_users_success(self, authenticated_client: AsyncClient):
        """Test getting Pipedrive users"""
        # Mock the pipedrive service
        with patch("components.get_pipedrive_users", new_callable=AsyncMock) as mock_users:
            mock_users.return_value = {
                "success": True,
                "users": [
                    {"id": 1, "name": "John Doe", "email": "john@company.com"}
                ]
            }

            # Act
            response = await authenticated_client.get("/components/pipedrive/users")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "users" in data


@pytest.mark.asyncio
class TestPipedriveCurrenciesEndpoint:
    """Test GET /components/pipedrive/currencies endpoint"""

    async def test_get_pipedrive_currencies_success(self, authenticated_client: AsyncClient):
        """Test getting Pipedrive currencies"""
        # Mock the pipedrive service
        with patch("components.get_pipedrive_currencies", new_callable=AsyncMock) as mock_currencies:
            mock_currencies.return_value = {
                "success": True,
                "currencies": [
                    {"code": "USD", "name": "US Dollar", "symbol": "$"}
                ]
            }

            # Act
            response = await authenticated_client.get("/components/pipedrive/currencies")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "currencies" in data


@pytest.mark.asyncio
class TestAvailableVariablesEndpoint:
    """Test GET /components/{component_id}/available-variables endpoint"""

    async def test_get_available_variables_success(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test getting available variables for a component"""
        # Arrange
        workflow = WorkflowFactory.create(owner=test_user)
        input_comp = ComponentFactory.create(
            workflow=workflow,
            type="input_sources",
            order=0
        )
        text_gen = ComponentFactory.create(
            workflow=workflow,
            type="text_generation",
            order=1,
            configuration={
                "extraction_points": [
                    {"name": "Client Name", "type": "string"},
                    {"name": "Deal Value", "type": "number"}
                ]
            }
        )
        target_comp = ComponentFactory.create(
            workflow=workflow,
            type="action",
            order=2
        )
        db_session.add_all([workflow, input_comp, text_gen, target_comp])
        db_session.commit()

        # Act
        response = await authenticated_client.get(
            f"/components/{target_comp.id}/available-variables"
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "available_variables" in data
        assert len(data["available_variables"]) > 0

        # Should have variables from both input source and text generation
        variable_values = [v["value"] for v in data["available_variables"]]
        assert "Client Name" in variable_values
        assert "Deal Value" in variable_values
        assert "transcript" in variable_values

    async def test_get_available_variables_no_previous_components(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test getting variables when component is first in workflow"""
        # Arrange
        workflow = WorkflowFactory.create(owner=test_user)
        component = ComponentFactory.create(workflow=workflow, order=0)
        db_session.add_all([workflow, component])
        db_session.commit()

        # Act
        response = await authenticated_client.get(
            f"/components/{component.id}/available-variables"
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "available_variables" in data
        assert len(data["available_variables"]) == 0

    async def test_get_available_variables_component_not_found(self, authenticated_client: AsyncClient):
        """Test getting variables for non-existent component"""
        # Act
        response = await authenticated_client.get(
            "/components/99999/available-variables"
        )

        # Assert
        assert response.status_code == 404
