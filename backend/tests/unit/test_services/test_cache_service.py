"""
Unit tests for cache_service.py
Tests Redis caching functionality with mocked Redis client
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
import json

from cache_service import (
    get_redis_client,
    cache_get,
    cache_set,
    cache_delete,
    cache_clear_pattern
)


class TestGetRedisClient:
    """Test get_redis_client function"""

    @patch("cache_service.redis.from_url")
    def test_get_redis_client_success(self, mock_from_url):
        """Test successful Redis client creation"""
        # Arrange
        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_from_url.return_value = mock_client

        # Reset the global client
        import cache_service
        cache_service.redis_client = None

        # Act
        client = get_redis_client()

        # Assert
        assert client is not None
        mock_client.ping.assert_called_once()

    @patch("cache_service.redis.from_url")
    def test_get_redis_client_connection_failure(self, mock_from_url):
        """Test Redis client creation when connection fails"""
        # Arrange
        mock_from_url.side_effect = Exception("Connection failed")

        # Reset the global client
        import cache_service
        cache_service.redis_client = None

        # Act
        client = get_redis_client()

        # Assert
        assert client is None

    @patch("cache_service.redis.from_url")
    def test_get_redis_client_returns_existing(self, mock_from_url):
        """Test that existing client is returned"""
        # Arrange
        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_from_url.return_value = mock_client

        # Reset and create client
        import cache_service
        cache_service.redis_client = None
        first_client = get_redis_client()

        # Act - Call again
        second_client = get_redis_client()

        # Assert
        assert first_client is second_client
        mock_from_url.assert_called_once()  # Should only be called once


class TestCacheGet:
    """Test cache_get function"""

    @patch("cache_service.get_redis_client")
    def test_cache_get_hit(self, mock_get_client):
        """Test successful cache hit"""
        # Arrange
        mock_client = Mock()
        test_data = {"key": "value", "number": 123}
        mock_client.get.return_value = json.dumps(test_data)
        mock_get_client.return_value = mock_client

        # Act
        result = cache_get("test_key")

        # Assert
        assert result == test_data
        mock_client.get.assert_called_once_with("test_key")

    @patch("cache_service.get_redis_client")
    def test_cache_get_miss(self, mock_get_client):
        """Test cache miss"""
        # Arrange
        mock_client = Mock()
        mock_client.get.return_value = None
        mock_get_client.return_value = mock_client

        # Act
        result = cache_get("nonexistent_key")

        # Assert
        assert result is None
        mock_client.get.assert_called_once_with("nonexistent_key")

    @patch("cache_service.get_redis_client")
    def test_cache_get_no_redis(self, mock_get_client):
        """Test cache get when Redis is unavailable"""
        # Arrange
        mock_get_client.return_value = None

        # Act
        result = cache_get("test_key")

        # Assert
        assert result is None

    @patch("cache_service.get_redis_client")
    def test_cache_get_error(self, mock_get_client):
        """Test cache get handles errors gracefully"""
        # Arrange
        mock_client = Mock()
        mock_client.get.side_effect = Exception("Redis error")
        mock_get_client.return_value = mock_client

        # Act
        result = cache_get("test_key")

        # Assert
        assert result is None  # Should return None on error


class TestCacheSet:
    """Test cache_set function"""

    @patch("cache_service.get_redis_client")
    def test_cache_set_success(self, mock_get_client):
        """Test successful cache set"""
        # Arrange
        mock_client = Mock()
        mock_get_client.return_value = mock_client
        test_data = {"key": "value"}

        # Act
        result = cache_set("test_key", test_data, ttl=60)

        # Assert
        assert result is True
        mock_client.setex.assert_called_once_with(
            "test_key",
            60,
            json.dumps(test_data)
        )

    @patch("cache_service.get_redis_client")
    def test_cache_set_default_ttl(self, mock_get_client):
        """Test cache set with default TTL"""
        # Arrange
        mock_client = Mock()
        mock_get_client.return_value = mock_client
        test_data = {"key": "value"}

        # Act
        result = cache_set("test_key", test_data)

        # Assert
        assert result is True
        mock_client.setex.assert_called_once()
        # Check that default TTL (900) was used
        call_args = mock_client.setex.call_args
        assert call_args[0][1] == 900

    @patch("cache_service.get_redis_client")
    def test_cache_set_complex_data(self, mock_get_client):
        """Test caching complex nested data"""
        # Arrange
        mock_client = Mock()
        mock_get_client.return_value = mock_client
        complex_data = {
            "nested": {
                "data": ["array", "items"],
                "number": 42,
                "boolean": True
            }
        }

        # Act
        result = cache_set("test_key", complex_data)

        # Assert
        assert result is True
        mock_client.setex.assert_called_once()

    @patch("cache_service.get_redis_client")
    def test_cache_set_no_redis(self, mock_get_client):
        """Test cache set when Redis is unavailable"""
        # Arrange
        mock_get_client.return_value = None

        # Act
        result = cache_set("test_key", {"data": "value"})

        # Assert
        assert result is False

    @patch("cache_service.get_redis_client")
    def test_cache_set_error(self, mock_get_client):
        """Test cache set handles errors gracefully"""
        # Arrange
        mock_client = Mock()
        mock_client.setex.side_effect = Exception("Redis error")
        mock_get_client.return_value = mock_client

        # Act
        result = cache_set("test_key", {"data": "value"})

        # Assert
        assert result is False


class TestCacheDelete:
    """Test cache_delete function"""

    @patch("cache_service.get_redis_client")
    def test_cache_delete_success(self, mock_get_client):
        """Test successful cache delete"""
        # Arrange
        mock_client = Mock()
        mock_client.delete.return_value = 1
        mock_get_client.return_value = mock_client

        # Act
        result = cache_delete("test_key")

        # Assert
        assert result is True
        mock_client.delete.assert_called_once_with("test_key")

    @patch("cache_service.get_redis_client")
    def test_cache_delete_no_redis(self, mock_get_client):
        """Test cache delete when Redis is unavailable"""
        # Arrange
        mock_get_client.return_value = None

        # Act
        result = cache_delete("test_key")

        # Assert
        assert result is False

    @patch("cache_service.get_redis_client")
    def test_cache_delete_error(self, mock_get_client):
        """Test cache delete handles errors gracefully"""
        # Arrange
        mock_client = Mock()
        mock_client.delete.side_effect = Exception("Redis error")
        mock_get_client.return_value = mock_client

        # Act
        result = cache_delete("test_key")

        # Assert
        assert result is False


class TestCacheClearPattern:
    """Test cache_clear_pattern function"""

    @patch("cache_service.get_redis_client")
    def test_cache_clear_pattern_success(self, mock_get_client):
        """Test successful pattern-based cache clear"""
        # Arrange
        mock_client = Mock()
        mock_client.keys.return_value = ["key1", "key2", "key3"]
        mock_client.delete.return_value = 3
        mock_get_client.return_value = mock_client

        # Act
        result = cache_clear_pattern("prefix:*")

        # Assert
        assert result == 3
        mock_client.keys.assert_called_once_with("prefix:*")
        mock_client.delete.assert_called_once_with("key1", "key2", "key3")

    @patch("cache_service.get_redis_client")
    def test_cache_clear_pattern_no_matches(self, mock_get_client):
        """Test clearing pattern with no matching keys"""
        # Arrange
        mock_client = Mock()
        mock_client.keys.return_value = []
        mock_get_client.return_value = mock_client

        # Act
        result = cache_clear_pattern("nonexistent:*")

        # Assert
        assert result == 0
        mock_client.keys.assert_called_once_with("nonexistent:*")
        mock_client.delete.assert_not_called()

    @patch("cache_service.get_redis_client")
    def test_cache_clear_pattern_no_redis(self, mock_get_client):
        """Test pattern clear when Redis is unavailable"""
        # Arrange
        mock_get_client.return_value = None

        # Act
        result = cache_clear_pattern("prefix:*")

        # Assert
        assert result == 0

    @patch("cache_service.get_redis_client")
    def test_cache_clear_pattern_error(self, mock_get_client):
        """Test pattern clear handles errors gracefully"""
        # Arrange
        mock_client = Mock()
        mock_client.keys.side_effect = Exception("Redis error")
        mock_get_client.return_value = mock_client

        # Act
        result = cache_clear_pattern("prefix:*")

        # Assert
        assert result == 0


class TestCacheIntegration:
    """Integration tests for cache operations"""

    @patch("cache_service.get_redis_client")
    def test_cache_set_and_get_roundtrip(self, mock_get_client):
        """Test setting and getting the same data"""
        # Arrange
        mock_client = Mock()
        test_data = {"message": "Hello", "count": 42}

        def mock_setex(key, ttl, value):
            # Store the value to return it later
            mock_client._stored_data = value

        def mock_get(key):
            return getattr(mock_client, '_stored_data', None)

        mock_client.setex = mock_setex
        mock_client.get = mock_get
        mock_get_client.return_value = mock_client

        # Act
        set_result = cache_set("test_key", test_data)
        get_result = cache_get("test_key")

        # Assert
        assert set_result is True
        assert get_result == test_data

    @patch("cache_service.get_redis_client")
    def test_cache_set_delete_get(self, mock_get_client):
        """Test setting, deleting, then getting (should be None)"""
        # Arrange
        mock_client = Mock()
        test_data = {"data": "value"}

        stored_data = {}

        def mock_setex(key, ttl, value):
            stored_data[key] = value

        def mock_delete(key):
            if key in stored_data:
                del stored_data[key]

        def mock_get(key):
            return stored_data.get(key)

        mock_client.setex = mock_setex
        mock_client.delete = mock_delete
        mock_client.get = mock_get
        mock_get_client.return_value = mock_client

        # Act
        cache_set("test_key", test_data)
        cache_delete("test_key")
        result = cache_get("test_key")

        # Assert
        assert result is None
