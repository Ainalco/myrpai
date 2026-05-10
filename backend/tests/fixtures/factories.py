"""
Factory Boy factories for creating test data
"""
import factory
from factory.alchemy import SQLAlchemyModelFactory
from faker import Faker
from passlib.context import CryptContext
from datetime import datetime

import models

fake = Faker()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class BaseFactory(SQLAlchemyModelFactory):
    """Base factory with common configuration"""
    class Meta:
        abstract = True
        sqlalchemy_session_persistence = "commit"


class UserFactory(BaseFactory):
    """Factory for creating User instances"""
    class Meta:
        model = models.User

    username = factory.Sequence(lambda n: f"user{n}")
    email = factory.LazyAttribute(lambda obj: f"{obj.username}@example.com")
    full_name = factory.Faker("name")
    hashed_password = factory.LazyFunction(
        lambda: pwd_context.hash("TestPassword123!")
    )
    is_active = True
    created_at = factory.LazyFunction(datetime.utcnow)

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        """Override create to handle password hashing"""
        if 'password' in kwargs:
            password = kwargs.pop('password')
            kwargs['hashed_password'] = pwd_context.hash(password)
        return super()._create(model_class, *args, **kwargs)


class WorkflowFactory(BaseFactory):
    """Factory for creating Workflow instances"""
    class Meta:
        model = models.Workflow

    name = factory.Faker("sentence", nb_words=3)
    description = factory.Faker("paragraph")
    universal_rules = factory.Faker("sentence")
    owner = factory.SubFactory(UserFactory)
    is_active = True
    created_at = factory.LazyFunction(datetime.utcnow)


class ComponentFactory(BaseFactory):
    """Factory for creating Component instances"""
    class Meta:
        model = models.Component

    workflow = factory.SubFactory(WorkflowFactory)
    type = factory.Iterator([
        "input_sources",
        "text_generation",
        "email",
        "action",
        "ai_filter",
        "conditional_logic"
    ])
    name = factory.Faker("word")
    description = factory.Faker("sentence")
    configuration = factory.LazyFunction(lambda: {})
    order = factory.Sequence(lambda n: n)
    position_x = factory.Faker("random_int", min=0, max=1000)
    position_y = factory.Faker("random_int", min=0, max=1000)
    created_at = factory.LazyFunction(datetime.utcnow)


class ConnectionFactory(BaseFactory):
    """Factory for creating Connection instances"""
    class Meta:
        model = models.Connection

    from_component = factory.SubFactory(ComponentFactory)
    to_component = factory.SubFactory(ComponentFactory)
    condition = factory.Faker("word")
    created_at = factory.LazyFunction(datetime.utcnow)


class ExecutionFactory(BaseFactory):
    """Factory for creating Execution instances"""
    class Meta:
        model = models.Execution

    workflow = factory.SubFactory(WorkflowFactory)
    status = factory.Iterator(["running", "completed", "failed"])
    started_at = factory.LazyFunction(datetime.utcnow)
    input_data = factory.LazyFunction(lambda: {"test": "data"})
    results = factory.LazyFunction(lambda: {"output": "result"})


class ComponentExecutionFactory(BaseFactory):
    """Factory for creating ComponentExecution instances"""
    class Meta:
        model = models.ComponentExecution

    execution = factory.SubFactory(ExecutionFactory)
    component = factory.SubFactory(ComponentFactory)
    status = factory.Iterator(["pending", "running", "completed", "failed"])
    started_at = factory.LazyFunction(datetime.utcnow)
    output = factory.LazyFunction(lambda: {"result": "test"})


class WebhookFactory(BaseFactory):
    """Factory for creating Webhook instances"""
    class Meta:
        model = models.Webhook

    workflow = factory.SubFactory(WorkflowFactory)
    component = factory.SubFactory(ComponentFactory)
    name = factory.Faker("word")
    description = factory.Faker("sentence")
    token = factory.Faker("uuid4")
    is_active = True
    created_at = factory.LazyFunction(datetime.utcnow)


class ApiKeyFactory(BaseFactory):
    """Factory for creating ApiKey instances"""
    class Meta:
        model = models.ApiKey

    user = factory.SubFactory(UserFactory)
    service_name = factory.Iterator(["fireflies", "pipedrive", "openai"])
    encrypted_key = factory.Faker("sha256")
    is_active = True
    created_at = factory.LazyFunction(datetime.utcnow)


class ExtractedVariableFactory(BaseFactory):
    """Factory for creating ExtractedVariable instances"""
    class Meta:
        model = models.ExtractedVariable

    execution = factory.SubFactory(ExecutionFactory)
    workflow = factory.SubFactory(WorkflowFactory)
    variable_name = factory.Faker("word")
    variable_key = factory.LazyAttribute(lambda obj: obj.variable_name.lower().replace(" ", "_"))
    variable_value = factory.Faker("word")
    data_type = factory.Iterator(["string", "number", "boolean", "array", "object"])
    created_at = factory.LazyFunction(datetime.utcnow)


class EmailQueueFactory(BaseFactory):
    """Factory for creating EmailQueue instances"""
    class Meta:
        model = models.EmailQueue

    user = factory.SubFactory(UserFactory)
    workflow = factory.SubFactory(WorkflowFactory)
    execution = factory.SubFactory(ExecutionFactory)
    recipient_email = factory.Faker("email")
    recipient_name = factory.Faker("name")
    subject = factory.Faker("sentence")
    body = factory.Faker("paragraph")
    status = factory.Iterator(["pending", "sent", "failed", "cancelled"])
    retry_count = 0
    max_retries = 3
    created_at = factory.LazyFunction(datetime.utcnow)
