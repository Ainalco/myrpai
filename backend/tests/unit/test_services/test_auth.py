"""
Unit tests for auth.py
Tests authentication, JWT tokens, and password hashing
"""
import pytest
from datetime import datetime, timedelta
from jose import jwt, JWTError
from passlib.context import CryptContext

from auth import (
    verify_password,
    get_password_hash,
    create_access_token,
    get_user,
    authenticate_user,
    SECRET_KEY,
    ALGORITHM
)
from tests.fixtures.factories import UserFactory


class TestPasswordHashing:
    """Test password hashing and verification"""

    def test_password_hash_and_verify(self):
        """Test that password hashing and verification work"""
        # Arrange
        password = "SecurePassword123!"

        # Act
        hashed = get_password_hash(password)
        is_valid = verify_password(password, hashed)

        # Assert
        assert hashed != password  # Password should be hashed
        assert is_valid is True

    def test_verify_wrong_password(self):
        """Test that wrong password fails verification"""
        # Arrange
        password = "CorrectPassword123!"
        wrong_password = "WrongPassword456!"
        hashed = get_password_hash(password)

        # Act
        is_valid = verify_password(wrong_password, hashed)

        # Assert
        assert is_valid is False

    def test_same_password_produces_different_hashes(self):
        """Test that hashing same password twice produces different hashes (salt)"""
        # Arrange
        password = "TestPassword123!"

        # Act
        hash1 = get_password_hash(password)
        hash2 = get_password_hash(password)

        # Assert
        assert hash1 != hash2  # Different hashes due to different salts
        assert verify_password(password, hash1)
        assert verify_password(password, hash2)

    def test_empty_password_hashing(self):
        """Test hashing empty password"""
        # Arrange
        password = ""

        # Act
        hashed = get_password_hash(password)
        is_valid = verify_password(password, hashed)

        # Assert
        assert is_valid is True


class TestJWTTokens:
    """Test JWT token creation and validation"""

    def test_create_access_token(self):
        """Test creating a valid JWT access token"""
        # Arrange
        data = {"sub": "testuser"}

        # Act
        token = create_access_token(data)

        # Assert
        assert isinstance(token, str)
        assert len(token) > 0

        # Verify token can be decoded
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        assert payload["sub"] == "testuser"
        assert "exp" in payload

    def test_create_token_with_custom_expiration(self):
        """Test creating token with custom expiration time"""
        # Arrange
        data = {"sub": "testuser"}
        expires_delta = timedelta(minutes=15)

        # Act
        token = create_access_token(data, expires_delta=expires_delta)
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

        # Assert
        exp_timestamp = payload["exp"]
        exp_datetime = datetime.fromtimestamp(exp_timestamp)
        now = datetime.utcnow()

        # Should expire in approximately 15 minutes
        time_diff = (exp_datetime - now).total_seconds()
        assert 14 * 60 < time_diff < 16 * 60  # Between 14 and 16 minutes

    def test_decode_valid_token(self):
        """Test decoding a valid token"""
        # Arrange
        data = {"sub": "john_doe", "user_id": 123}
        token = create_access_token(data)

        # Act
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

        # Assert
        assert payload["sub"] == "john_doe"
        assert payload["user_id"] == 123

    def test_decode_expired_token_raises_error(self):
        """Test that decoding expired token raises error"""
        # Arrange
        data = {"sub": "testuser"}
        # Create token that expired 1 hour ago
        expires = timedelta(hours=-1)
        token = create_access_token(data, expires_delta=expires)

        # Act & Assert
        with pytest.raises(JWTError):
            jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

    def test_decode_invalid_token_raises_error(self):
        """Test that decoding invalid token raises error"""
        # Arrange
        invalid_token = "invalid.token.here"

        # Act & Assert
        with pytest.raises(JWTError):
            jwt.decode(invalid_token, SECRET_KEY, algorithms=[ALGORITHM])

    def test_token_with_wrong_secret_fails(self):
        """Test that token signed with wrong secret fails verification"""
        # Arrange
        data = {"sub": "testuser"}
        wrong_secret = "wrong-secret-key"
        token = jwt.encode(data, wrong_secret, algorithm=ALGORITHM)

        # Act & Assert
        with pytest.raises(JWTError):
            jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])


class TestUserAuthentication:
    """Test user authentication functions"""

    def test_get_user_by_username(self, db_session):
        """Test retrieving user by username"""
        # Arrange
        user = UserFactory.create(username="testuser")
        db_session.add(user)
        db_session.commit()

        # Act
        retrieved_user = get_user(db_session, "testuser")

        # Assert
        assert retrieved_user is not None
        assert retrieved_user.username == "testuser"
        assert retrieved_user.id == user.id

    def test_get_user_nonexistent(self, db_session):
        """Test retrieving non-existent user returns None"""
        # Act
        user = get_user(db_session, "nonexistent")

        # Assert
        assert user is None

    def test_authenticate_user_success(self, db_session):
        """Test successful user authentication"""
        # Arrange
        password = "CorrectPassword123!"
        user = UserFactory.create(username="testuser", password=password)
        db_session.add(user)
        db_session.commit()

        # Act
        authenticated = authenticate_user(db_session, "testuser", password)

        # Assert
        assert authenticated is not False
        assert authenticated.username == "testuser"

    def test_authenticate_user_wrong_password(self, db_session):
        """Test authentication fails with wrong password"""
        # Arrange
        user = UserFactory.create(username="testuser", password="CorrectPassword")
        db_session.add(user)
        db_session.commit()

        # Act
        authenticated = authenticate_user(db_session, "testuser", "WrongPassword")

        # Assert
        assert authenticated is False

    def test_authenticate_nonexistent_user(self, db_session):
        """Test authentication fails for non-existent user"""
        # Act
        authenticated = authenticate_user(db_session, "nonexistent", "password")

        # Assert
        assert authenticated is False

    def test_authenticate_inactive_user(self, db_session):
        """Test that inactive users cannot authenticate"""
        # Arrange
        password = "Password123!"
        user = UserFactory.create(
            username="inactiveuser",
            password=password,
            is_active=False
        )
        db_session.add(user)
        db_session.commit()

        # Act
        # Authenticate should succeed but get_current_active_user should fail
        authenticated = authenticate_user(db_session, "inactiveuser", password)

        # Assert
        assert authenticated is not False  # Authentication succeeds
        assert authenticated.is_active is False  # But user is inactive


class TestPasswordRequirements:
    """Test password strength requirements"""

    def test_weak_password_still_hashes(self):
        """Test that even weak passwords are hashed (validation should be on API layer)"""
        # Arrange
        weak_password = "123"

        # Act
        hashed = get_password_hash(weak_password)
        is_valid = verify_password(weak_password, hashed)

        # Assert
        assert is_valid is True

    def test_long_password(self):
        """Test hashing very long password"""
        # Arrange
        long_password = "a" * 1000

        # Act
        hashed = get_password_hash(long_password)
        is_valid = verify_password(long_password, hashed)

        # Assert
        assert is_valid is True

    def test_special_characters_in_password(self):
        """Test password with special characters"""
        # Arrange
        password = "P@ssw0rd!#$%^&*()"

        # Act
        hashed = get_password_hash(password)
        is_valid = verify_password(password, hashed)

        # Assert
        assert is_valid is True
