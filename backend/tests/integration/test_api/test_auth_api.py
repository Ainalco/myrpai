"""
Integration tests for authentication API endpoints
Tests /auth/* endpoints with database interactions
"""
import pytest
from httpx import AsyncClient

from tests.fixtures.factories import UserFactory


@pytest.mark.asyncio
class TestRegisterEndpoint:
    """Test POST /auth/register endpoint"""

    async def test_register_new_user_success(self, client: AsyncClient, db_session):
        """Test successful user registration"""
        # Arrange
        user_data = {
            "username": "newuser",
            "email": "newuser@example.com",
            "password": "SecurePass123!",
            "full_name": "New User"
        }

        # Act
        response = await client.post("/auth/register", json=user_data)

        # Assert
        assert response.status_code == 201
        data = response.json()
        assert data["username"] == "newuser"
        assert data["email"] == "newuser@example.com"
        assert data["full_name"] == "New User"
        assert "id" in data
        assert "password" not in data
        assert "hashed_password" not in data
        assert data["is_active"] is True

    async def test_register_duplicate_username(self, client: AsyncClient, db_session):
        """Test registration with duplicate username fails"""
        # Arrange
        existing_user = UserFactory.create(username="existinguser")
        db_session.add(existing_user)
        db_session.commit()

        user_data = {
            "username": "existinguser",
            "email": "new@example.com",
            "password": "Password123!"
        }

        # Act
        response = await client.post("/auth/register", json=user_data)

        # Assert
        assert response.status_code == 400
        assert "already registered" in response.json()["detail"].lower()

    async def test_register_duplicate_email(self, client: AsyncClient, db_session):
        """Test registration with duplicate email fails"""
        # Arrange
        existing_user = UserFactory.create(email="existing@example.com")
        db_session.add(existing_user)
        db_session.commit()

        user_data = {
            "username": "newuser",
            "email": "existing@example.com",
            "password": "Password123!"
        }

        # Act
        response = await client.post("/auth/register", json=user_data)

        # Assert
        assert response.status_code == 400
        assert "already registered" in response.json()["detail"].lower()

    async def test_register_missing_required_fields(self, client: AsyncClient):
        """Test registration fails with missing required fields"""
        # Arrange
        incomplete_data = {
            "username": "testuser"
            # Missing email and password
        }

        # Act
        response = await client.post("/auth/register", json=incomplete_data)

        # Assert
        assert response.status_code == 422  # Validation error

    async def test_register_invalid_email_format(self, client: AsyncClient):
        """Test registration fails with invalid email"""
        # Arrange
        user_data = {
            "username": "testuser",
            "email": "invalid-email",
            "password": "Password123!"
        }

        # Act
        response = await client.post("/auth/register", json=user_data)

        # Assert
        assert response.status_code == 422


@pytest.mark.asyncio
class TestLoginEndpoint:
    """Test POST /auth/login endpoint"""

    async def test_login_success(self, client: AsyncClient, db_session):
        """Test successful login returns JWT token"""
        # Arrange
        password = "TestPass123!"
        user = UserFactory.create(username="testuser", password=password)
        db_session.add(user)
        db_session.commit()

        # Act
        response = await client.post(
            "/auth/login",
            json={"username": "testuser", "password": password}
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert len(data["access_token"]) > 0

    async def test_login_wrong_password(self, client: AsyncClient, db_session):
        """Test login fails with wrong password"""
        # Arrange
        user = UserFactory.create(username="testuser", password="CorrectPassword")
        db_session.add(user)
        db_session.commit()

        # Act
        response = await client.post(
            "/auth/login",
            json={"username": "testuser", "password": "WrongPassword"}
        )

        # Assert
        assert response.status_code == 401
        assert "Incorrect username or password" in response.json()["detail"]

    async def test_login_nonexistent_user(self, client: AsyncClient):
        """Test login fails for non-existent user"""
        # Act
        response = await client.post(
            "/auth/login",
            json={"username": "nonexistent", "password": "password"}
        )

        # Assert
        assert response.status_code == 401
        assert "Incorrect username or password" in response.json()["detail"]

    async def test_login_inactive_user(self, client: AsyncClient, db_session):
        """Test login succeeds but token indicates inactive user"""
        # Arrange
        password = "TestPass123!"
        user = UserFactory.create(
            username="inactiveuser",
            password=password,
            is_active=False
        )
        db_session.add(user)
        db_session.commit()

        # Act
        response = await client.post(
            "/auth/login",
            json={"username": "inactiveuser", "password": password}
        )

        # Assert
        # Login should succeed, but /auth/me should fail
        assert response.status_code == 200

    async def test_login_missing_credentials(self, client: AsyncClient):
        """Test login fails with missing credentials"""
        # Act
        response = await client.post("/auth/login", json={})

        # Assert
        assert response.status_code == 422


@pytest.mark.asyncio
class TestGetCurrentUserEndpoint:
    """Test GET /auth/me endpoint"""

    async def test_get_current_user_authenticated(self, authenticated_client: AsyncClient):
        """Test getting current user with valid token"""
        # Act
        response = await authenticated_client.get("/auth/me")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "username" in data
        assert "email" in data
        assert "id" in data
        assert data["username"] == "testuser"

    async def test_get_current_user_unauthenticated(self, client: AsyncClient):
        """Test getting current user without token fails"""
        # Act
        response = await client.get("/auth/me")

        # Assert
        assert response.status_code == 401

    async def test_get_current_user_invalid_token(self, client: AsyncClient):
        """Test getting current user with invalid token fails"""
        # Arrange
        client.headers["Authorization"] = "Bearer invalid-token"

        # Act
        response = await client.get("/auth/me")

        # Assert
        assert response.status_code == 401

    async def test_get_current_user_expired_token(self, client: AsyncClient, db_session):
        """Test getting current user with expired token fails"""
        # Arrange
        from auth import create_access_token
        from datetime import timedelta

        user = UserFactory.create()
        db_session.add(user)
        db_session.commit()

        # Create expired token
        expired_token = create_access_token(
            data={"sub": user.username},
            expires_delta=timedelta(minutes=-30)
        )

        client.headers["Authorization"] = f"Bearer {expired_token}"

        # Act
        response = await client.get("/auth/me")

        # Assert
        assert response.status_code == 401


@pytest.mark.asyncio
class TestUpdateUserSettingsEndpoint:
    """Test PATCH /auth/me/settings endpoint"""

    async def test_update_internal_domains(self, authenticated_client: AsyncClient, db_session):
        """Test updating user's internal domains"""
        # Arrange
        settings_data = {
            "internal_domains": "company.com,company.io"
        }

        # Act
        response = await authenticated_client.patch("/auth/me/settings", json=settings_data)

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["internal_domains"] == "company.com,company.io"

    async def test_update_settings_unauthenticated(self, client: AsyncClient):
        """Test updating settings without authentication fails"""
        # Arrange
        settings_data = {"internal_domains": "company.com"}

        # Act
        response = await client.patch("/auth/me/settings", json=settings_data)

        # Assert
        assert response.status_code == 401


@pytest.mark.asyncio
class TestUpdateSMTPSettingsEndpoint:
    """Test POST /auth/me/smtp endpoint"""

    async def test_update_smtp_settings(self, authenticated_client: AsyncClient):
        """Test updating SMTP settings"""
        # Arrange
        smtp_data = {
            "smtp_host": "smtp.gmail.com",
            "smtp_port": 587,
            "smtp_username": "user@gmail.com",
            "smtp_password": "app_password",
            "smtp_use_tls": True,
            "smtp_from_email": "user@gmail.com",
            "smtp_from_name": "Test User"
        }

        # Act
        response = await authenticated_client.post("/auth/me/smtp", json=smtp_data)

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["smtp_host"] == "smtp.gmail.com"
        assert data["smtp_port"] == 587
        assert "smtp_password" not in data  # Password should be encrypted and not returned

    async def test_update_smtp_missing_required_fields(self, authenticated_client: AsyncClient):
        """Test updating SMTP with missing fields fails"""
        # Arrange
        incomplete_data = {
            "smtp_host": "smtp.gmail.com"
            # Missing other required fields
        }

        # Act
        response = await authenticated_client.post("/auth/me/smtp", json=incomplete_data)

        # Assert
        assert response.status_code == 422


@pytest.mark.asyncio
class TestSMTPTestEndpoint:
    """Test POST /auth/me/smtp/test endpoint"""

    async def test_smtp_test_endpoint_exists(self, authenticated_client: AsyncClient):
        """Test that SMTP test endpoint exists"""
        # Arrange
        smtp_data = {
            "smtp_host": "smtp.gmail.com",
            "smtp_port": 587,
            "smtp_username": "user@gmail.com",
            "smtp_password": "password",
            "smtp_use_tls": True
        }

        # Act
        response = await authenticated_client.post("/auth/me/smtp/test", json=smtp_data)

        # Assert
        # May fail due to invalid credentials, but endpoint should exist
        assert response.status_code in [200, 400, 422, 500]
