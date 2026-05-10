"""
Shared pytest fixtures for all tests
"""
import pytest
import asyncio
from typing import Generator, AsyncGenerator
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool
from httpx import AsyncClient, ASGITransport

from database import Base, get_db
from main import app
import models

# Test database URL (in-memory SQLite for speed)
TEST_DATABASE_URL = "sqlite:///:memory:"


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def engine():
    """Create test database engine with in-memory SQLite"""
    engine = create_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def db_session(engine) -> Generator[Session, None, None]:
    """
    Create a new database session with a savepoint for each test.
    All changes are rolled back after the test.
    """
    connection = engine.connect()
    transaction = connection.begin()
    session = sessionmaker(bind=connection)()

    # Begin a nested transaction (using SAVEPOINT)
    nested = connection.begin_nested()

    @event.listens_for(session, "after_transaction_end")
    def end_savepoint(session, transaction):
        nonlocal nested
        if not nested.is_active:
            nested = connection.begin_nested()

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def override_get_db(db_session):
    """Override the get_db dependency"""
    async def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    yield
    app.dependency_overrides.clear()


@pytest.fixture
async def client(override_get_db) -> AsyncGenerator[AsyncClient, None]:
    """Create async test client with database override"""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        follow_redirects=True
    ) as ac:
        yield ac


@pytest.fixture
def test_user(db_session):
    """Create a test user for use in tests"""
    from tests.fixtures.factories import UserFactory

    user = UserFactory.create(username="testuser", email="test@example.com")
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
async def authenticated_client(client, db_session, test_user) -> AsyncGenerator[AsyncClient, None]:
    """Create authenticated test client with a test user"""
    from auth import create_access_token

    # Create access token
    token = create_access_token(data={"sub": test_user.username})

    # Add authorization header
    client.headers["Authorization"] = f"Bearer {token}"
    client.user = test_user  # Store user for easy access in tests

    yield client


@pytest.fixture
def mock_openai_response():
    """Mock OpenAI API response"""
    return {
        "id": "chatcmpl-123",
        "object": "chat.completion",
        "created": 1677652288,
        "model": "gpt-4",
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": '{"name": "John Doe", "email": "john@example.com", "topic": "Sales Meeting"}'
            },
            "finish_reason": "stop"
        }],
        "usage": {
            "prompt_tokens": 50,
            "completion_tokens": 30,
            "total_tokens": 80
        }
    }


@pytest.fixture
def mock_fireflies_transcript():
    """Mock Fireflies transcript data"""
    return {
        "data": {
            "transcript": {
                "id": "trans_123",
                "title": "Q4 Planning Meeting",
                "date": "2024-01-15T10:00:00Z",
                "duration": 3600,
                "transcript_text": "Welcome everyone to the Q4 planning meeting. We need to discuss our sales targets.",
                "sentences": [
                    {
                        "text": "Welcome everyone to the Q4 planning meeting",
                        "speaker_name": "John Smith",
                        "start_time": 0
                    },
                    {
                        "text": "We need to discuss our sales targets",
                        "speaker_name": "John Smith",
                        "start_time": 5
                    }
                ],
                "participants": [
                    {"name": "John Smith", "email": "john@company.com"},
                    {"name": "Jane Doe", "email": "jane@company.com"}
                ],
                "summary": "Discussion about Q4 goals and targets"
            }
        }
    }


@pytest.fixture
def mock_pipedrive_fields():
    """Mock Pipedrive fields response"""
    return {
        "success": True,
        "data": [
            {
                "id": 1,
                "key": "title",
                "name": "Deal Title",
                "field_type": "varchar",
                "is_required": True
            },
            {
                "id": 2,
                "key": "value",
                "name": "Deal Value",
                "field_type": "monetary",
                "is_required": False
            },
            {
                "id": 3,
                "key": "person_id",
                "name": "Person",
                "field_type": "person",
                "is_required": False
            }
        ]
    }
