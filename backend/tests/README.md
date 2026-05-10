# Backend Testing Documentation

This directory contains comprehensive tests for the backend application, covering unit tests, integration tests, and end-to-end tests.

## Table of Contents

- [Test Structure](#test-structure)
- [Installation](#installation)
- [Running Tests](#running-tests)
- [Test Coverage](#test-coverage)
- [Writing Tests](#writing-tests)
- [Continuous Integration](#continuous-integration)

## Test Structure

The test suite is organized following the testing pyramid principle:

```
tests/
├── conftest.py                 # Shared fixtures and pytest configuration
├── requirements-dev.txt        # Testing dependencies
├── pytest.ini                  # Pytest configuration
├── fixtures/
│   ├── factories.py           # Factory Boy factories for test data
│   └── mock_responses.py      # Mock API responses for external services
├── unit/                      # Unit tests (70% of tests)
│   ├── test_models/          # Database model tests
│   ├── test_services/        # Service layer tests
│   └── test_utils/           # Utility function tests
├── integration/               # Integration tests (20% of tests)
│   └── test_api/             # API endpoint tests
└── e2e/                      # End-to-end tests (10% of tests)
```

### Test Distribution

- **Unit Tests (70%)**: Fast, isolated tests for individual functions and classes
- **Integration Tests (20%)**: Tests for API endpoints with database interactions
- **E2E Tests (10%)**: Complete workflow execution tests

## Installation

### 1. Set Up Virtual Environment (Recommended)

It's highly recommended to use a virtual environment to isolate project dependencies:

```bash
# Navigate to backend directory
cd backend

# Create virtual environment
python -m venv .venv

# Activate virtual environment
# On Windows:
.venv\Scripts\activate

# On macOS/Linux:
source .venv/bin/activate
```

### 2. Install Testing Dependencies

```bash
# Install production dependencies first (if not already installed)
pip install -r requirements.txt

# Install testing dependencies
pip install -r requirements-dev.txt
```

### 3. Set Up Test Environment

Create a `.env.test` file in the backend directory (optional):

```env
DATABASE_URL=sqlite:///./test.db
SECRET_KEY=test-secret-key-for-testing-only
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
ENCRYPTION_KEY=test-encryption-key-32-chars!!
DEPLOYMENT_MODE=development
```

## Running Tests

### Run All Tests

```bash
# From the backend directory
pytest

# Or with verbose output
pytest -v
```

### Run Specific Test Categories

```bash
# Run only unit tests
pytest tests/unit/

# Run only integration tests
pytest tests/integration/

# Run only API tests
pytest tests/integration/test_api/

# Run only database model tests
pytest tests/unit/test_models/
```

### Run Specific Test Files

```bash
# Run auth tests
pytest tests/integration/test_api/test_auth_api.py

# Run workflow tests
pytest tests/integration/test_api/test_workflows_api.py

# Run encryption tests
pytest tests/unit/test_utils/test_encryption.py
```

### Run Specific Test Classes or Functions

```bash
# Run a specific test class
pytest tests/integration/test_api/test_auth_api.py::TestLoginEndpoint

# Run a specific test function
pytest tests/integration/test_api/test_auth_api.py::TestLoginEndpoint::test_login_success

# Run tests matching a pattern
pytest -k "test_login"
```

### Run with Coverage

```bash
# Run tests with coverage report
pytest --cov=. --cov-report=html

# View coverage report
# Open htmlcov/index.html in your browser

# Run with terminal coverage report
pytest --cov=. --cov-report=term-missing
```

### Run Tests in Parallel

```bash
# Install pytest-xdist if not already installed
pip install pytest-xdist

# Run tests in parallel (faster for large test suites)
pytest -n auto
```

## Test Coverage

The test suite aims for **80%+ code coverage** across the backend.

### Current Coverage

| Category | Coverage Target |
|----------|----------------|
| Unit Tests | 80%+ |
| Integration Tests | 80%+ |
| Overall Backend | 80%+ |

### Viewing Coverage Reports

After running tests with coverage:

```bash
# Generate HTML coverage report
pytest --cov=. --cov-report=html

# Open the report
# Windows
start htmlcov/index.html

# macOS
open htmlcov/index.html

# Linux
xdg-open htmlcov/index.html
```

### Coverage by Module

```bash
# Check coverage for specific module
pytest --cov=auth --cov-report=term-missing

# Check coverage for multiple modules
pytest --cov=auth --cov=workflows --cov=components --cov-report=term-missing
```

## Writing Tests

### Test Naming Conventions

- Test files: `test_*.py` or `*_test.py`
- Test classes: `Test*` (e.g., `TestUserAuthentication`)
- Test functions: `test_*` (e.g., `test_user_can_login`)

### Using Fixtures

Common fixtures are defined in `conftest.py`:

```python
async def test_create_workflow(authenticated_client, db_session, test_user):
    """Test creating a workflow"""
    # authenticated_client: Pre-authenticated HTTP client
    # db_session: Database session with transaction rollback
    # test_user: Pre-created test user

    workflow_data = {"name": "Test Workflow"}
    response = await authenticated_client.post("/workflows/", json=workflow_data)
    assert response.status_code == 201
```

### Available Fixtures

- `engine`: SQLAlchemy test database engine
- `db_session`: Database session with automatic rollback
- `client`: Async HTTP client (unauthenticated)
- `authenticated_client`: Async HTTP client (authenticated as test_user)
- `test_user`: Pre-created test user
- `mock_openai_response`: Mock OpenAI API response
- `mock_fireflies_response`: Mock Fireflies API response
- `mock_pipedrive_response`: Mock Pipedrive API response

### Using Factory Boy

Create test data easily with factories:

```python
from tests.fixtures.factories import UserFactory, WorkflowFactory

def test_workflow_creation(db_session):
    user = UserFactory.create(username="testuser")
    workflow = WorkflowFactory.create(owner=user, name="My Workflow")

    db_session.add_all([user, workflow])
    db_session.commit()

    assert workflow.owner == user
```

### Mocking External Services

```python
from unittest.mock import patch, AsyncMock

@patch("ai_service.openai_client.ChatCompletion.create", new_callable=AsyncMock)
async def test_ai_generation(mock_openai):
    mock_openai.return_value = {"choices": [{"message": {"content": "AI response"}}]}

    result = await generate_text("prompt")
    assert "AI response" in result
```

### Async Test Examples

```python
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_async_endpoint(authenticated_client: AsyncClient):
    response = await authenticated_client.get("/workflows/")
    assert response.status_code == 200
```

## Test Organization

### Unit Tests

Located in `tests/unit/`, these test individual functions and classes in isolation:

- **`test_models/`**: Database model creation, validation, and relationships
- **`test_services/`**: Service layer logic (auth, cache, encryption)
- **`test_utils/`**: Utility functions (encryption, config)

### Integration Tests

Located in `tests/integration/`, these test API endpoints with real database interactions:

- **`test_api/test_auth_api.py`**: Authentication endpoints (register, login, /me)
- **`test_api/test_workflows_api.py`**: Workflow CRUD operations
- **`test_api/test_components_api.py`**: Component management
- **`test_api/test_executions_api.py`**: Workflow execution
- **`test_api/test_webhooks_api.py`**: Webhook creation and reception
- **`test_api/test_variables_api.py`**: Variable extraction and substitution

### E2E Tests

Located in `tests/e2e/`, these test complete user workflows:

- End-to-end workflow execution scenarios
- Multi-component workflow testing
- Real-world usage patterns

## Debugging Tests

### Run Tests with Debug Output

```bash
# Show print statements
pytest -s

# Show detailed test output
pytest -vv

# Show local variables on failure
pytest -l
```

### Run Failed Tests Only

```bash
# Run tests that failed in the last run
pytest --lf

# Run failed tests first, then others
pytest --ff
```

### Stop on First Failure

```bash
pytest -x
```

### Set Breakpoints

```python
def test_something():
    import pdb; pdb.set_trace()  # Python debugger
    # or
    breakpoint()  # Python 3.7+

    # Test code here
```

## Continuous Integration

### GitHub Actions

The test suite runs automatically on every push and pull request. See `.github/workflows/test.yml` for configuration.

### Pre-commit Hooks

Run tests before committing (optional):

```bash
# Install pre-commit
pip install pre-commit

# Set up git hooks
pre-commit install

# Run manually
pre-commit run --all-files
```

## Common Issues and Solutions

### Database Lock Errors

If you encounter database lock errors:

```bash
# Delete test database and rerun
rm test.db
pytest
```

### Import Errors

Ensure you're running pytest from the backend directory:

```bash
cd backend
pytest
```

### Fixture Not Found

Check that `conftest.py` is in the tests directory and properly structured.

### Async Test Failures

Ensure async tests are marked with `@pytest.mark.asyncio`:

```python
@pytest.mark.asyncio
async def test_async_function():
    result = await some_async_function()
    assert result is not None
```

## Best Practices

1. **Keep tests independent**: Each test should work in isolation
2. **Use descriptive names**: Test names should clearly describe what they test
3. **Follow AAA pattern**: Arrange, Act, Assert
4. **Mock external dependencies**: Don't make real API calls in tests
5. **Test edge cases**: Include tests for error conditions and boundary cases
6. **Maintain test data**: Use factories instead of hardcoded data
7. **Clean up after tests**: Use fixtures with proper teardown
8. **Keep tests fast**: Unit tests should run in milliseconds
9. **Document complex tests**: Add comments for non-obvious test logic
10. **Run tests frequently**: Test early and often during development

## Resources

- [Pytest Documentation](https://docs.pytest.org/)
- [Factory Boy Documentation](https://factoryboy.readthedocs.io/)
- [HTTPX Async Client](https://www.python-httpx.org/)
- [FastAPI Testing](https://fastapi.tiangolo.com/tutorial/testing/)

## Getting Help

If you encounter issues with tests:

1. Check this README for common solutions
2. Review the test files for examples
3. Check the conftest.py for available fixtures
4. Run tests with `-vv` for detailed output
5. Consult the team documentation or ask for help

---

**Last Updated**: 2025-01-27
**Test Coverage Target**: 80%+
**Total Tests**: 200+
