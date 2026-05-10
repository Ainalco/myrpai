"""
Integration tests for variables API endpoints
Tests /workflows/{workflow_id}/variables/* endpoints with database interactions
"""
import pytest
from httpx import AsyncClient

from tests.fixtures.factories import (
    UserFactory,
    WorkflowFactory,
    ExecutionFactory,
    ExtractedVariableFactory
)


@pytest.mark.asyncio
class TestGetWorkflowVariablesEndpoint:
    """Test GET /workflows/{workflow_id}/variables endpoint"""

    async def test_get_variables_success(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test getting extracted variables for a workflow"""
        # Arrange
        workflow = WorkflowFactory.create(owner=test_user)
        execution = ExecutionFactory.create(workflow=workflow)
        var1 = ExtractedVariableFactory.create(
            workflow=workflow,
            execution=execution,
            variable_name="Client Name",
            variable_value="Acme Corp"
        )
        var2 = ExtractedVariableFactory.create(
            workflow=workflow,
            execution=execution,
            variable_name="Deal Value",
            variable_value=50000
        )
        db_session.add_all([workflow, execution, var1, var2])
        db_session.commit()

        # Act
        response = await authenticated_client.get(f"/workflows/{workflow.id}/variables")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        var_names = [v["variable_name"] for v in data]
        assert "Client Name" in var_names
        assert "Deal Value" in var_names

    async def test_get_variables_returns_latest_only(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test that only the most recent variable for each name is returned"""
        # Arrange
        workflow = WorkflowFactory.create(owner=test_user)
        old_exec = ExecutionFactory.create(workflow=workflow)
        new_exec = ExecutionFactory.create(workflow=workflow)

        # Create old and new variables with same name
        old_var = ExtractedVariableFactory.create(
            workflow=workflow,
            execution=old_exec,
            variable_name="Client Name",
            variable_value="Old Client"
        )
        new_var = ExtractedVariableFactory.create(
            workflow=workflow,
            execution=new_exec,
            variable_name="Client Name",
            variable_value="New Client"
        )
        db_session.add_all([workflow, old_exec, new_exec, old_var, new_var])
        db_session.commit()

        # Act
        response = await authenticated_client.get(f"/workflows/{workflow.id}/variables")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1  # Only one unique variable name
        assert data[0]["variable_value"] == "New Client"

    async def test_get_variables_empty(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test getting variables when workflow has none"""
        # Arrange
        workflow = WorkflowFactory.create(owner=test_user)
        db_session.add(workflow)
        db_session.commit()

        # Act
        response = await authenticated_client.get(f"/workflows/{workflow.id}/variables")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 0

    async def test_get_variables_different_data_types(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test getting variables with different data types"""
        # Arrange
        workflow = WorkflowFactory.create(owner=test_user)
        execution = ExecutionFactory.create(workflow=workflow)

        string_var = ExtractedVariableFactory.create(
            workflow=workflow,
            execution=execution,
            variable_name="Name",
            variable_value="John Doe",
            data_type="string"
        )
        number_var = ExtractedVariableFactory.create(
            workflow=workflow,
            execution=execution,
            variable_name="Age",
            variable_value=30,
            data_type="number"
        )
        bool_var = ExtractedVariableFactory.create(
            workflow=workflow,
            execution=execution,
            variable_name="Active",
            variable_value=True,
            data_type="boolean"
        )
        array_var = ExtractedVariableFactory.create(
            workflow=workflow,
            execution=execution,
            variable_name="Tags",
            variable_value=["urgent", "vip"],
            data_type="array"
        )
        db_session.add_all([workflow, execution, string_var, number_var, bool_var, array_var])
        db_session.commit()

        # Act
        response = await authenticated_client.get(f"/workflows/{workflow.id}/variables")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 4

        data_types = {v["variable_name"]: v["data_type"] for v in data}
        assert data_types["Name"] == "string"
        assert data_types["Age"] == "number"
        assert data_types["Active"] == "boolean"
        assert data_types["Tags"] == "array"

    async def test_get_variables_workflow_not_found(self, authenticated_client: AsyncClient):
        """Test getting variables for non-existent workflow"""
        # Act
        response = await authenticated_client.get("/workflows/99999/variables")

        # Assert
        assert response.status_code == 404

    async def test_get_variables_unauthorized(self, authenticated_client: AsyncClient, db_session):
        """Test getting variables for workflow owned by another user"""
        # Arrange
        other_user = UserFactory.create(username="otheruser")
        workflow = WorkflowFactory.create(owner=other_user)
        db_session.add_all([other_user, workflow])
        db_session.commit()

        # Act
        response = await authenticated_client.get(f"/workflows/{workflow.id}/variables")

        # Assert
        assert response.status_code == 404


@pytest.mark.asyncio
class TestSubstituteVariablesEndpoint:
    """Test POST /workflows/{workflow_id}/variables/substitute endpoint"""

    async def test_substitute_variables_success(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test successful variable substitution"""
        # Arrange
        workflow = WorkflowFactory.create(owner=test_user)
        execution = ExecutionFactory.create(workflow=workflow)
        var1 = ExtractedVariableFactory.create(
            workflow=workflow,
            execution=execution,
            variable_name="Client Name",
            variable_value="Acme Corp"
        )
        var2 = ExtractedVariableFactory.create(
            workflow=workflow,
            execution=execution,
            variable_name="Deal Value",
            variable_value=50000
        )
        db_session.add_all([workflow, execution, var1, var2])
        db_session.commit()

        substitution_data = {
            "text": "Hello {{Client Name}}, your deal is worth ${{Deal Value}}."
        }

        # Act
        response = await authenticated_client.post(
            f"/workflows/{workflow.id}/variables/substitute",
            json=substitution_data
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["processed_text"] == "Hello Acme Corp, your deal is worth $50000."
        assert data["substitutions_made"] == 2
        assert "Client Name" in data["variables_used"]
        assert "Deal Value" in data["variables_used"]

    async def test_substitute_variables_case_insensitive(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test that variable substitution is case insensitive"""
        # Arrange
        workflow = WorkflowFactory.create(owner=test_user)
        execution = ExecutionFactory.create(workflow=workflow)
        var = ExtractedVariableFactory.create(
            workflow=workflow,
            execution=execution,
            variable_name="Client Name",
            variable_value="Test Client"
        )
        db_session.add_all([workflow, execution, var])
        db_session.commit()

        substitution_data = {
            "text": "Hello {{client name}} and {{CLIENT NAME}}!"
        }

        # Act
        response = await authenticated_client.post(
            f"/workflows/{workflow.id}/variables/substitute",
            json=substitution_data
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["processed_text"] == "Hello Test Client and Test Client!"
        assert data["substitutions_made"] == 2

    async def test_substitute_variables_with_spaces_and_underscores(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test variable substitution handles spaces and underscores flexibly"""
        # Arrange
        workflow = WorkflowFactory.create(owner=test_user)
        execution = ExecutionFactory.create(workflow=workflow)
        var = ExtractedVariableFactory.create(
            workflow=workflow,
            execution=execution,
            variable_name="Client Name",
            variable_value="Test Client"
        )
        db_session.add_all([workflow, execution, var])
        db_session.commit()

        substitution_data = {
            "text": "Using {{client_name}} and {{ClientName}}"
        }

        # Act
        response = await authenticated_client.post(
            f"/workflows/{workflow.id}/variables/substitute",
            json=substitution_data
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "Test Client" in data["processed_text"]

    async def test_substitute_variables_with_array(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test substitution of array variables (joined with comma)"""
        # Arrange
        workflow = WorkflowFactory.create(owner=test_user)
        execution = ExecutionFactory.create(workflow=workflow)
        var = ExtractedVariableFactory.create(
            workflow=workflow,
            execution=execution,
            variable_name="Tags",
            variable_value=["urgent", "vip", "enterprise"],
            data_type="array"
        )
        db_session.add_all([workflow, execution, var])
        db_session.commit()

        substitution_data = {
            "text": "Tags: {{Tags}}"
        }

        # Act
        response = await authenticated_client.post(
            f"/workflows/{workflow.id}/variables/substitute",
            json=substitution_data
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["processed_text"] == "Tags: urgent, vip, enterprise"

    async def test_substitute_variables_with_boolean(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test substitution of boolean variables (Yes/No)"""
        # Arrange
        workflow = WorkflowFactory.create(owner=test_user)
        execution = ExecutionFactory.create(workflow=workflow)
        var = ExtractedVariableFactory.create(
            workflow=workflow,
            execution=execution,
            variable_name="Is Active",
            variable_value=True,
            data_type="boolean"
        )
        db_session.add_all([workflow, execution, var])
        db_session.commit()

        substitution_data = {
            "text": "Active: {{Is Active}}"
        }

        # Act
        response = await authenticated_client.post(
            f"/workflows/{workflow.id}/variables/substitute",
            json=substitution_data
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["processed_text"] == "Active: Yes"

    async def test_substitute_variables_not_found(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test that unknown variables are left as-is"""
        # Arrange
        workflow = WorkflowFactory.create(owner=test_user)
        db_session.add(workflow)
        db_session.commit()

        substitution_data = {
            "text": "Hello {{Unknown Variable}}!"
        }

        # Act
        response = await authenticated_client.post(
            f"/workflows/{workflow.id}/variables/substitute",
            json=substitution_data
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["processed_text"] == "Hello {{Unknown Variable}}!"
        assert data["substitutions_made"] == 0
        assert len(data["variables_used"]) == 0

    async def test_substitute_variables_no_placeholders(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test substitution with text containing no placeholders"""
        # Arrange
        workflow = WorkflowFactory.create(owner=test_user)
        db_session.add(workflow)
        db_session.commit()

        substitution_data = {
            "text": "Plain text with no variables."
        }

        # Act
        response = await authenticated_client.post(
            f"/workflows/{workflow.id}/variables/substitute",
            json=substitution_data
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["processed_text"] == "Plain text with no variables."
        assert data["substitutions_made"] == 0

    async def test_substitute_variables_null_value(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test substitution of variable with null value"""
        # Arrange
        workflow = WorkflowFactory.create(owner=test_user)
        execution = ExecutionFactory.create(workflow=workflow)
        var = ExtractedVariableFactory.create(
            workflow=workflow,
            execution=execution,
            variable_name="Optional Field",
            variable_value=None
        )
        db_session.add_all([workflow, execution, var])
        db_session.commit()

        substitution_data = {
            "text": "Value: {{Optional Field}}"
        }

        # Act
        response = await authenticated_client.post(
            f"/workflows/{workflow.id}/variables/substitute",
            json=substitution_data
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["processed_text"] == "Value: [Not Available]"

    async def test_substitute_variables_workflow_not_found(self, authenticated_client: AsyncClient):
        """Test substitution for non-existent workflow"""
        # Arrange
        substitution_data = {
            "text": "Hello {{Name}}!"
        }

        # Act
        response = await authenticated_client.post(
            "/workflows/99999/variables/substitute",
            json=substitution_data
        )

        # Assert
        assert response.status_code == 404

    async def test_substitute_variables_unauthorized(self, authenticated_client: AsyncClient, db_session):
        """Test substitution for workflow owned by another user"""
        # Arrange
        other_user = UserFactory.create(username="otheruser")
        workflow = WorkflowFactory.create(owner=other_user)
        db_session.add_all([other_user, workflow])
        db_session.commit()

        substitution_data = {
            "text": "Hello {{Name}}!"
        }

        # Act
        response = await authenticated_client.post(
            f"/workflows/{workflow.id}/variables/substitute",
            json=substitution_data
        )

        # Assert
        assert response.status_code == 404
