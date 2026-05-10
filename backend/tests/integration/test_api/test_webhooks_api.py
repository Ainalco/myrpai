"""
Integration tests for webhooks API endpoints
Tests /webhooks/* endpoints with database interactions
"""
import pytest
from httpx import AsyncClient
from unittest.mock import patch, AsyncMock

from tests.fixtures.factories import (
    UserFactory,
    WorkflowFactory,
    ComponentFactory,
    WebhookFactory
)


@pytest.mark.asyncio
class TestCreateWebhookEndpoint:
    """Test POST /webhooks/create endpoint"""

    async def test_create_webhook_success(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test successful webhook creation"""
        # Arrange
        workflow = WorkflowFactory.create(owner=test_user)
        component = ComponentFactory.create(
            workflow=workflow,
            type="input_sources"
        )
        db_session.add_all([workflow, component])
        db_session.commit()

        webhook_data = {
            "workflow_id": workflow.id,
            "component_id": component.id,
            "name": "Fireflies Webhook",
            "description": "Webhook for Fireflies transcripts"
        }

        # Act
        response = await authenticated_client.post(
            "/webhooks/create",
            json=webhook_data
        )

        # Assert
        assert response.status_code == 201
        data = response.json()
        assert data["workflow_id"] == workflow.id
        assert data["component_id"] == component.id
        assert data["name"] == "Fireflies Webhook"
        assert "webhook_url" in data
        assert "webhook_token" in data
        assert len(data["webhook_token"]) > 0

    async def test_create_webhook_updates_existing(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test that creating webhook for same component updates existing one"""
        # Arrange
        workflow = WorkflowFactory.create(owner=test_user)
        component = ComponentFactory.create(workflow=workflow, type="input_sources")
        existing_webhook = WebhookFactory.create(
            workflow=workflow,
            component=component,
            name="Old Name"
        )
        db_session.add_all([workflow, component, existing_webhook])
        db_session.commit()
        original_id = existing_webhook.id

        webhook_data = {
            "workflow_id": workflow.id,
            "component_id": component.id,
            "name": "New Name",
            "description": "Updated description"
        }

        # Act
        response = await authenticated_client.post(
            "/webhooks/create",
            json=webhook_data
        )

        # Assert
        assert response.status_code == 201
        data = response.json()
        assert data["id"] == original_id  # Same webhook updated
        assert data["name"] == "New Name"
        assert data["description"] == "Updated description"

    async def test_create_webhook_workflow_not_found(self, authenticated_client: AsyncClient):
        """Test creating webhook for non-existent workflow"""
        # Arrange
        webhook_data = {
            "workflow_id": 99999,
            "component_id": 1,
            "name": "Test Webhook"
        }

        # Act
        response = await authenticated_client.post(
            "/webhooks/create",
            json=webhook_data
        )

        # Assert
        assert response.status_code == 404
        assert "workflow not found" in response.json()["detail"].lower()

    async def test_create_webhook_component_not_found(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test creating webhook for non-existent component"""
        # Arrange
        workflow = WorkflowFactory.create(owner=test_user)
        db_session.add(workflow)
        db_session.commit()

        webhook_data = {
            "workflow_id": workflow.id,
            "component_id": 99999,
            "name": "Test Webhook"
        }

        # Act
        response = await authenticated_client.post(
            "/webhooks/create",
            json=webhook_data
        )

        # Assert
        assert response.status_code == 404
        assert "component not found" in response.json()["detail"].lower()

    async def test_create_webhook_non_input_source_component(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test creating webhook for non-input-source component fails"""
        # Arrange
        workflow = WorkflowFactory.create(owner=test_user)
        component = ComponentFactory.create(
            workflow=workflow,
            type="text_generation"  # Not input_sources
        )
        db_session.add_all([workflow, component])
        db_session.commit()

        webhook_data = {
            "workflow_id": workflow.id,
            "component_id": component.id,
            "name": "Test Webhook"
        }

        # Act
        response = await authenticated_client.post(
            "/webhooks/create",
            json=webhook_data
        )

        # Assert
        assert response.status_code == 404

    async def test_create_webhook_unauthorized(self, authenticated_client: AsyncClient, db_session):
        """Test creating webhook for workflow owned by another user"""
        # Arrange
        other_user = UserFactory.create(username="otheruser")
        workflow = WorkflowFactory.create(owner=other_user)
        component = ComponentFactory.create(workflow=workflow, type="input_sources")
        db_session.add_all([other_user, workflow, component])
        db_session.commit()

        webhook_data = {
            "workflow_id": workflow.id,
            "component_id": component.id,
            "name": "Test Webhook"
        }

        # Act
        response = await authenticated_client.post(
            "/webhooks/create",
            json=webhook_data
        )

        # Assert
        assert response.status_code == 404


@pytest.mark.asyncio
class TestListWebhooksEndpoint:
    """Test GET /webhooks/{workflow_id} endpoint"""

    async def test_list_webhooks_success(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test listing webhooks for a workflow"""
        # Arrange
        workflow = WorkflowFactory.create(owner=test_user)
        component1 = ComponentFactory.create(workflow=workflow, type="input_sources")
        component2 = ComponentFactory.create(workflow=workflow, type="input_sources")
        webhook1 = WebhookFactory.create(workflow=workflow, component=component1, name="Webhook 1")
        webhook2 = WebhookFactory.create(workflow=workflow, component=component2, name="Webhook 2")
        db_session.add_all([workflow, component1, component2, webhook1, webhook2])
        db_session.commit()

        # Act
        response = await authenticated_client.get(f"/webhooks/{workflow.id}")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert any(w["name"] == "Webhook 1" for w in data)
        assert any(w["name"] == "Webhook 2" for w in data)
        assert all("webhook_url" in w for w in data)

    async def test_list_webhooks_empty(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test listing webhooks when workflow has none"""
        # Arrange
        workflow = WorkflowFactory.create(owner=test_user)
        db_session.add(workflow)
        db_session.commit()

        # Act
        response = await authenticated_client.get(f"/webhooks/{workflow.id}")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 0

    async def test_list_webhooks_workflow_not_found(self, authenticated_client: AsyncClient):
        """Test listing webhooks for non-existent workflow"""
        # Act
        response = await authenticated_client.get("/webhooks/99999")

        # Assert
        assert response.status_code == 404

    async def test_list_webhooks_unauthorized(self, authenticated_client: AsyncClient, db_session):
        """Test listing webhooks for workflow owned by another user"""
        # Arrange
        other_user = UserFactory.create(username="otheruser")
        workflow = WorkflowFactory.create(owner=other_user)
        db_session.add_all([other_user, workflow])
        db_session.commit()

        # Act
        response = await authenticated_client.get(f"/webhooks/{workflow.id}")

        # Assert
        assert response.status_code == 404


@pytest.mark.asyncio
class TestReceiveFirefliesWebhookEndpoint:
    """Test POST /webhooks/fireflies/{webhook_id}/{token} endpoint"""

    async def test_receive_webhook_success(self, client: AsyncClient, db_session, test_user):
        """Test successful webhook reception"""
        # Arrange
        workflow = WorkflowFactory.create(owner=test_user)
        component = ComponentFactory.create(workflow=workflow, type="input_sources")
        webhook = WebhookFactory.create(
            workflow=workflow,
            component=component,
            webhook_token="test_token_123"
        )
        db_session.add_all([test_user, workflow, component, webhook])
        db_session.commit()

        fireflies_payload = {
            "meetingId": "meeting_123",
            "eventType": "Transcription completed",
            "meeting_title": "Sales Call"
        }

        # Mock the Fireflies service and background execution
        with patch("webhooks.fetch_transcript", new_callable=AsyncMock) as mock_fetch:
            with patch("webhooks.get_meeting_url", new_callable=AsyncMock) as mock_url:
                with patch("webhooks.execute_workflow_background") as mock_bg:
                    mock_fetch.return_value = {
                        "meeting_title": "Sales Call",
                        "transcript": "Sample transcript",
                        "participants": ["John Doe"]
                    }
                    mock_url.return_value = "https://fireflies.ai/meeting/123"

                    # Act
                    response = await client.post(
                        f"/webhooks/fireflies/{webhook.id}/test_token_123",
                        json=fireflies_payload
                    )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["meeting_id"] == "meeting_123"
        assert data["event_type"] == "Transcription completed"
        assert "execution_id" in data

    async def test_receive_webhook_invalid_token(self, client: AsyncClient, db_session, test_user):
        """Test webhook with invalid token"""
        # Arrange
        workflow = WorkflowFactory.create(owner=test_user)
        component = ComponentFactory.create(workflow=workflow, type="input_sources")
        webhook = WebhookFactory.create(
            workflow=workflow,
            component=component,
            webhook_token="correct_token"
        )
        db_session.add_all([test_user, workflow, component, webhook])
        db_session.commit()

        fireflies_payload = {
            "meetingId": "meeting_123",
            "eventType": "Transcription completed"
        }

        # Act
        response = await client.post(
            f"/webhooks/fireflies/{webhook.id}/wrong_token",
            json=fireflies_payload
        )

        # Assert
        assert response.status_code == 401
        assert "invalid webhook token" in response.json()["detail"].lower()

    async def test_receive_webhook_invalid_payload(self, client: AsyncClient, db_session, test_user):
        """Test webhook with invalid JSON payload"""
        # Arrange
        workflow = WorkflowFactory.create(owner=test_user)
        component = ComponentFactory.create(workflow=workflow, type="input_sources")
        webhook = WebhookFactory.create(
            workflow=workflow,
            component=component,
            webhook_token="test_token"
        )
        db_session.add_all([test_user, workflow, component, webhook])
        db_session.commit()

        # Act - Send invalid JSON
        response = await client.post(
            f"/webhooks/fireflies/{webhook.id}/test_token",
            content="invalid json",
            headers={"Content-Type": "application/json"}
        )

        # Assert
        assert response.status_code == 400

    async def test_receive_webhook_without_transcript_fetch(self, client: AsyncClient, db_session, test_user):
        """Test webhook processing when transcript fetch fails"""
        # Arrange
        workflow = WorkflowFactory.create(owner=test_user)
        component = ComponentFactory.create(workflow=workflow, type="input_sources")
        webhook = WebhookFactory.create(
            workflow=workflow,
            component=component,
            webhook_token="test_token"
        )
        db_session.add_all([test_user, workflow, component, webhook])
        db_session.commit()

        fireflies_payload = {
            "meetingId": "meeting_123",
            "eventType": "Transcription completed"
        }

        # Mock transcript fetch to fail
        with patch("webhooks.fetch_transcript", new_callable=AsyncMock) as mock_fetch:
            with patch("webhooks.get_meeting_url", new_callable=AsyncMock) as mock_url:
                with patch("webhooks.execute_workflow_background"):
                    mock_fetch.side_effect = Exception("API error")
                    mock_url.return_value = None

                    # Act
                    response = await client.post(
                        f"/webhooks/fireflies/{webhook.id}/test_token",
                        json=fireflies_payload
                    )

        # Assert - Should still succeed, but with fallback data
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

    async def test_receive_webhook_non_transcription_event(self, client: AsyncClient, db_session, test_user):
        """Test webhook with non-transcription event type"""
        # Arrange
        workflow = WorkflowFactory.create(owner=test_user)
        component = ComponentFactory.create(workflow=workflow, type="input_sources")
        webhook = WebhookFactory.create(
            workflow=workflow,
            component=component,
            webhook_token="test_token"
        )
        db_session.add_all([test_user, workflow, component, webhook])
        db_session.commit()

        fireflies_payload = {
            "meetingId": "meeting_123",
            "eventType": "Meeting started"  # Different event type
        }

        with patch("webhooks.execute_workflow_background"):
            # Act
            response = await client.post(
                f"/webhooks/fireflies/{webhook.id}/test_token",
                json=fireflies_payload
            )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["event_type"] == "Meeting started"


@pytest.mark.asyncio
class TestDeleteWebhookEndpoint:
    """Test DELETE /webhooks/{webhook_id} endpoint"""

    async def test_delete_webhook_success(self, authenticated_client: AsyncClient, db_session, test_user):
        """Test successful webhook deletion"""
        # Arrange
        workflow = WorkflowFactory.create(owner=test_user)
        component = ComponentFactory.create(workflow=workflow, type="input_sources")
        webhook = WebhookFactory.create(workflow=workflow, component=component)
        db_session.add_all([workflow, component, webhook])
        db_session.commit()
        webhook_id = webhook.id

        # Act
        response = await authenticated_client.delete(f"/webhooks/{webhook_id}")

        # Assert
        assert response.status_code == 200
        assert "deleted successfully" in response.json()["message"].lower()

        # Verify webhook is deleted
        list_response = await authenticated_client.get(f"/webhooks/{workflow.id}")
        assert len(list_response.json()) == 0

    async def test_delete_webhook_not_found(self, authenticated_client: AsyncClient):
        """Test deleting non-existent webhook"""
        # Act
        response = await authenticated_client.delete("/webhooks/99999")

        # Assert
        assert response.status_code == 404

    async def test_delete_webhook_unauthorized(self, authenticated_client: AsyncClient, db_session):
        """Test deleting webhook owned by another user"""
        # Arrange
        other_user = UserFactory.create(username="otheruser")
        workflow = WorkflowFactory.create(owner=other_user)
        component = ComponentFactory.create(workflow=workflow, type="input_sources")
        webhook = WebhookFactory.create(workflow=workflow, component=component)
        db_session.add_all([other_user, workflow, component, webhook])
        db_session.commit()

        # Act
        response = await authenticated_client.delete(f"/webhooks/{webhook.id}")

        # Assert
        assert response.status_code == 403
        assert "not authorized" in response.json()["detail"].lower()

    async def test_delete_webhook_unauthenticated(self, client: AsyncClient, db_session, test_user):
        """Test deleting webhook without authentication"""
        # Arrange
        workflow = WorkflowFactory.create(owner=test_user)
        component = ComponentFactory.create(workflow=workflow, type="input_sources")
        webhook = WebhookFactory.create(workflow=workflow, component=component)
        db_session.add_all([workflow, component, webhook])
        db_session.commit()

        # Act
        response = await client.delete(f"/webhooks/{webhook.id}")

        # Assert
        assert response.status_code == 401
