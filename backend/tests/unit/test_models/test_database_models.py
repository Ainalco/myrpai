"""
Unit tests for database models
Tests model creation, attributes, and basic functionality
"""
import pytest
from datetime import datetime
from sqlalchemy.exc import IntegrityError

import models
from tests.fixtures.factories import (
    UserFactory,
    WorkflowFactory,
    ComponentFactory,
    ConnectionFactory,
    ExecutionFactory,
    ComponentExecutionFactory,
    WebhookFactory,
    ApiKeyFactory,
    ExtractedVariableFactory,
    EmailQueueFactory
)


class TestUserModel:
    """Test User model"""

    def test_create_user(self, db_session):
        """Test creating a user"""
        # Arrange & Act
        user = UserFactory.create(
            username="testuser",
            email="test@example.com",
            full_name="Test User"
        )
        db_session.add(user)
        db_session.commit()

        # Assert
        assert user.id is not None
        assert user.username == "testuser"
        assert user.email == "test@example.com"
        assert user.is_active is True
        assert user.created_at is not None

    def test_user_unique_email(self, db_session):
        """Test that user email must be unique"""
        # Arrange
        user1 = UserFactory.create(email="duplicate@example.com")
        db_session.add(user1)
        db_session.commit()

        # Act & Assert
        user2 = UserFactory.create(email="duplicate@example.com")
        db_session.add(user2)
        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_user_unique_username(self, db_session):
        """Test that username must be unique"""
        # Arrange
        user1 = UserFactory.create(username="duplicate")
        db_session.add(user1)
        db_session.commit()

        # Act & Assert
        user2 = UserFactory.create(username="duplicate")
        db_session.add(user2)
        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_user_smtp_fields(self, db_session):
        """Test user SMTP configuration fields"""
        # Arrange & Act
        user = UserFactory.create(
            username="smtpuser",
            email="smtp@example.com"
        )
        user.smtp_host = "smtp.gmail.com"
        user.smtp_port = 587
        user.smtp_username = "user@gmail.com"
        user.smtp_password = "encrypted_password"
        user.smtp_use_tls = True
        user.smtp_from_email = "user@gmail.com"
        user.smtp_from_name = "Test User"

        db_session.add(user)
        db_session.commit()

        # Assert
        assert user.smtp_host == "smtp.gmail.com"
        assert user.smtp_port == 587
        assert user.smtp_use_tls is True

    def test_user_internal_domains(self, db_session):
        """Test user internal domains field"""
        # Arrange & Act
        user = UserFactory.create()
        user.internal_domains = "company.com,company.io"
        db_session.add(user)
        db_session.commit()

        # Assert
        assert user.internal_domains == "company.com,company.io"


class TestWorkflowModel:
    """Test Workflow model"""

    def test_create_workflow(self, db_session):
        """Test creating a workflow"""
        # Arrange & Act
        user = UserFactory.create()
        workflow = WorkflowFactory.create(
            owner=user,
            name="Test Workflow",
            description="Test description"
        )
        db_session.add_all([user, workflow])
        db_session.commit()

        # Assert
        assert workflow.id is not None
        assert workflow.name == "Test Workflow"
        assert workflow.owner_id == user.id
        assert workflow.is_active is True

    def test_workflow_owner_relationship(self, db_session):
        """Test workflow-user relationship"""
        # Arrange & Act
        user = UserFactory.create()
        workflow = WorkflowFactory.create(owner=user)
        db_session.add_all([user, workflow])
        db_session.commit()

        # Assert
        assert workflow.owner == user
        assert user.workflows[0] == workflow

    def test_workflow_cascade_delete_components(self, db_session):
        """Test that deleting workflow cascades to components"""
        # Arrange
        user = UserFactory.create()
        workflow = WorkflowFactory.create(owner=user)
        component = ComponentFactory.create(workflow=workflow)
        db_session.add_all([user, workflow, component])
        db_session.commit()
        component_id = component.id

        # Act
        db_session.delete(workflow)
        db_session.commit()

        # Assert
        deleted_component = db_session.query(models.Component).filter_by(id=component_id).first()
        assert deleted_component is None


class TestComponentModel:
    """Test Component model"""

    def test_create_component(self, db_session):
        """Test creating a component"""
        # Arrange
        user = UserFactory.create()
        workflow = WorkflowFactory.create(owner=user)

        # Act
        component = ComponentFactory.create(
            workflow=workflow,
            type="text_generation",
            name="Test Component",
            configuration={"test": "config"}
        )
        db_session.add_all([user, workflow, component])
        db_session.commit()

        # Assert
        assert component.id is not None
        assert component.type == "text_generation"
        assert component.workflow_id == workflow.id
        assert component.configuration == {"test": "config"}

    def test_component_workflow_relationship(self, db_session):
        """Test component-workflow relationship"""
        # Arrange & Act
        user = UserFactory.create()
        workflow = WorkflowFactory.create(owner=user)
        component = ComponentFactory.create(workflow=workflow)
        db_session.add_all([user, workflow, component])
        db_session.commit()

        # Assert
        assert component.workflow == workflow
        assert component in workflow.components

    def test_component_position_and_order(self, db_session):
        """Test component position and order fields"""
        # Arrange & Act
        user = UserFactory.create()
        workflow = WorkflowFactory.create(owner=user)
        component = ComponentFactory.create(
            workflow=workflow,
            position_x=100,
            position_y=200,
            order=5
        )
        db_session.add_all([user, workflow, component])
        db_session.commit()

        # Assert
        assert component.position_x == 100
        assert component.position_y == 200
        assert component.order == 5


class TestConnectionModel:
    """Test Connection model"""

    def test_create_connection(self, db_session):
        """Test creating a connection between components"""
        # Arrange
        user = UserFactory.create()
        workflow = WorkflowFactory.create(owner=user)
        comp1 = ComponentFactory.create(workflow=workflow)
        comp2 = ComponentFactory.create(workflow=workflow)

        # Act
        connection = ConnectionFactory.create(
            from_component=comp1,
            to_component=comp2,
            condition="success"
        )
        db_session.add_all([user, workflow, comp1, comp2, connection])
        db_session.commit()

        # Assert
        assert connection.id is not None
        assert connection.from_component_id == comp1.id
        assert connection.to_component_id == comp2.id
        assert connection.condition == "success"


class TestExecutionModel:
    """Test Execution model"""

    def test_create_execution(self, db_session):
        """Test creating an execution"""
        # Arrange
        user = UserFactory.create()
        workflow = WorkflowFactory.create(owner=user)

        # Act
        execution = ExecutionFactory.create(
            workflow=workflow,
            status="running",
            input_data={"test": "data"}
        )
        db_session.add_all([user, workflow, execution])
        db_session.commit()

        # Assert
        assert execution.id is not None
        assert execution.workflow_id == workflow.id
        assert execution.status == "running"
        assert execution.input_data == {"test": "data"}

    def test_execution_workflow_relationship(self, db_session):
        """Test execution-workflow relationship"""
        # Arrange & Act
        user = UserFactory.create()
        workflow = WorkflowFactory.create(owner=user)
        execution = ExecutionFactory.create(workflow=workflow)
        db_session.add_all([user, workflow, execution])
        db_session.commit()

        # Assert
        assert execution.workflow == workflow
        assert execution in workflow.executions

    def test_execution_timing_fields(self, db_session):
        """Test execution timing fields"""
        # Arrange & Act
        user = UserFactory.create()
        workflow = WorkflowFactory.create(owner=user)
        execution = ExecutionFactory.create(
            workflow=workflow,
            status="completed",
            completed_at=datetime.utcnow(),
            total_execution_time=1500
        )
        db_session.add_all([user, workflow, execution])
        db_session.commit()

        # Assert
        assert execution.completed_at is not None
        assert execution.total_execution_time == 1500


class TestComponentExecutionModel:
    """Test ComponentExecution model"""

    def test_create_component_execution(self, db_session):
        """Test creating a component execution"""
        # Arrange
        user = UserFactory.create()
        workflow = WorkflowFactory.create(owner=user)
        component = ComponentFactory.create(workflow=workflow)
        execution = ExecutionFactory.create(workflow=workflow)

        # Act
        comp_exec = ComponentExecutionFactory.create(
            execution=execution,
            component=component,
            status="completed",
            output_data={"result": "test"}
        )
        db_session.add_all([user, workflow, component, execution, comp_exec])
        db_session.commit()

        # Assert
        assert comp_exec.id is not None
        assert comp_exec.execution_id == execution.id
        assert comp_exec.component_id == component.id
        assert comp_exec.status == "completed"

    def test_component_execution_relationships(self, db_session):
        """Test component execution relationships"""
        # Arrange & Act
        user = UserFactory.create()
        workflow = WorkflowFactory.create(owner=user)
        component = ComponentFactory.create(workflow=workflow)
        execution = ExecutionFactory.create(workflow=workflow)
        comp_exec = ComponentExecutionFactory.create(
            execution=execution,
            component=component
        )
        db_session.add_all([user, workflow, component, execution, comp_exec])
        db_session.commit()

        # Assert
        assert comp_exec.execution == execution
        assert comp_exec.component == component
        assert comp_exec in execution.component_executions


class TestExtractedVariableModel:
    """Test ExtractedVariable model"""

    def test_create_extracted_variable(self, db_session):
        """Test creating an extracted variable"""
        # Arrange
        user = UserFactory.create()
        workflow = WorkflowFactory.create(owner=user)
        execution = ExecutionFactory.create(workflow=workflow)

        # Act
        variable = ExtractedVariableFactory.create(
            workflow=workflow,
            execution=execution,
            variable_name="Client Name",
            variable_key="client_name",
            variable_value="Acme Corp",
            data_type="string"
        )
        db_session.add_all([user, workflow, execution, variable])
        db_session.commit()

        # Assert
        assert variable.id is not None
        assert variable.variable_name == "Client Name"
        assert variable.variable_value == "Acme Corp"
        assert variable.data_type == "string"

    def test_extracted_variable_json_value(self, db_session):
        """Test storing complex JSON values"""
        # Arrange
        user = UserFactory.create()
        workflow = WorkflowFactory.create(owner=user)
        execution = ExecutionFactory.create(workflow=workflow)

        # Act
        variable = ExtractedVariableFactory.create(
            workflow=workflow,
            execution=execution,
            variable_name="Tags",
            variable_value=["urgent", "vip", "enterprise"],
            data_type="array"
        )
        db_session.add_all([user, workflow, execution, variable])
        db_session.commit()

        # Assert
        assert variable.variable_value == ["urgent", "vip", "enterprise"]


class TestApiKeyModel:
    """Test ApiKey model"""

    def test_create_api_key(self, db_session):
        """Test creating an API key"""
        # Arrange
        user = UserFactory.create()

        # Act
        api_key = ApiKeyFactory.create(
            user=user,
            service_name="fireflies",
            encrypted_key="encrypted_key_value"
        )
        db_session.add_all([user, api_key])
        db_session.commit()

        # Assert
        assert api_key.id is not None
        assert api_key.user_id == user.id
        assert api_key.service_name == "fireflies"
        assert api_key.is_active is True

    def test_api_key_user_relationship(self, db_session):
        """Test API key-user relationship"""
        # Arrange & Act
        user = UserFactory.create()
        api_key = ApiKeyFactory.create(user=user)
        db_session.add_all([user, api_key])
        db_session.commit()

        # Assert
        assert api_key.user == user


class TestWebhookModel:
    """Test Webhook model"""

    def test_create_webhook(self, db_session):
        """Test creating a webhook"""
        # Arrange
        user = UserFactory.create()
        workflow = WorkflowFactory.create(owner=user)
        component = ComponentFactory.create(workflow=workflow, type="input_sources")

        # Act
        webhook = WebhookFactory.create(
            workflow=workflow,
            component=component,
            name="Fireflies Webhook",
            webhook_token="unique_token_123"
        )
        db_session.add_all([user, workflow, component, webhook])
        db_session.commit()

        # Assert
        assert webhook.id is not None
        assert webhook.workflow_id == workflow.id
        assert webhook.component_id == component.id
        assert webhook.webhook_token == "unique_token_123"

    def test_webhook_unique_token(self, db_session):
        """Test that webhook token must be unique"""
        # Arrange
        user = UserFactory.create()
        workflow = WorkflowFactory.create(owner=user)
        comp1 = ComponentFactory.create(workflow=workflow, type="input_sources")
        comp2 = ComponentFactory.create(workflow=workflow, type="input_sources")

        webhook1 = WebhookFactory.create(
            workflow=workflow,
            component=comp1,
            webhook_token="duplicate_token"
        )
        db_session.add_all([user, workflow, comp1, comp2, webhook1])
        db_session.commit()

        # Act & Assert
        webhook2 = WebhookFactory.create(
            workflow=workflow,
            component=comp2,
            webhook_token="duplicate_token"
        )
        db_session.add(webhook2)
        with pytest.raises(IntegrityError):
            db_session.commit()


class TestEmailQueueModel:
    """Test EmailQueue model"""

    def test_create_email_queue(self, db_session):
        """Test creating an email queue entry"""
        # Arrange
        user = UserFactory.create()
        workflow = WorkflowFactory.create(owner=user)
        execution = ExecutionFactory.create(workflow=workflow)
        component = ComponentFactory.create(workflow=workflow, type="email")

        # Act
        email = EmailQueueFactory.create(
            user=user,
            workflow=workflow,
            execution=execution,
            component=component,
            recipient_email="client@example.com",
            subject="Test Email",
            body="Email body",
            status="pending"
        )
        db_session.add_all([user, workflow, execution, component, email])
        db_session.commit()

        # Assert
        assert email.id is not None
        assert email.recipient_email == "client@example.com"
        assert email.status == "pending"
        assert email.retry_count == 0

    def test_email_queue_cc_bcc_json(self, db_session):
        """Test storing CC and BCC as JSON"""
        # Arrange
        user = UserFactory.create()
        workflow = WorkflowFactory.create(owner=user)

        # Act
        email = EmailQueueFactory.create(
            user=user,
            workflow=workflow,
            recipient_email="primary@example.com",
            subject="Test",
            body="Body"
        )
        email.cc = ["cc1@example.com", "cc2@example.com"]
        email.bcc = ["bcc@example.com"]
        db_session.add_all([user, workflow, email])
        db_session.commit()

        # Assert
        assert email.cc == ["cc1@example.com", "cc2@example.com"]
        assert email.bcc == ["bcc@example.com"]

    def test_email_queue_relationships(self, db_session):
        """Test email queue relationships"""
        # Arrange & Act
        user = UserFactory.create()
        workflow = WorkflowFactory.create(owner=user)
        execution = ExecutionFactory.create(workflow=workflow)
        component = ComponentFactory.create(workflow=workflow, type="email")
        email = EmailQueueFactory.create(
            user=user,
            workflow=workflow,
            execution=execution,
            component=component
        )
        db_session.add_all([user, workflow, execution, component, email])
        db_session.commit()

        # Assert
        assert email.user == user
        assert email.workflow == workflow
        assert email.execution == execution
        assert email.component == component
