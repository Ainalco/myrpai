"""
Redis cache service for API response caching
"""
import redis
import json
import logging
import os
from typing import Optional, Any

logger = logging.getLogger(__name__)

# Redis connection setup
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
redis_client: Optional[redis.Redis] = None

def get_redis_client() -> Optional[redis.Redis]:
    """Get or create Redis client connection"""
    global redis_client

    if redis_client is None:
        try:
            redis_client = redis.from_url(
                REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5
            )
            # Test connection
            redis_client.ping()
            logger.info("Redis connection established successfully")
        except Exception as e:
            logger.warning(f"Failed to connect to Redis: {e}. Caching will be disabled.")
            redis_client = None

    return redis_client


def cache_get(key: str) -> Optional[Any]:
    """
    Get value from cache

    Args:
        key: Cache key

    Returns:
        Cached value if found, None otherwise
    """
    try:
        client = get_redis_client()
        if client is None:
            return None

        cached = client.get(key)
        if cached:
            logger.debug(f"Cache HIT for key: {key}")
            return json.loads(cached)

        logger.debug(f"Cache MISS for key: {key}")
        return None
    except Exception as e:
        logger.warning(f"Cache get error for key {key}: {e}")
        return None


def cache_set(key: str, value: Any, ttl: int = 900) -> bool:
    """
    Set value in cache with TTL

    Args:
        key: Cache key
        value: Value to cache (must be JSON serializable)
        ttl: Time to live in seconds (default: 15 minutes)

    Returns:
        True if successful, False otherwise
    """
    try:
        client = get_redis_client()
        if client is None:
            return False

        client.setex(
            key,
            ttl,
            json.dumps(value)
        )
        logger.debug(f"Cache SET for key: {key} (TTL: {ttl}s)")
        return True
    except Exception as e:
        logger.warning(f"Cache set error for key {key}: {e}")
        return False


def cache_delete(key: str) -> bool:
    """
    Delete value from cache

    Args:
        key: Cache key

    Returns:
        True if successful, False otherwise
    """
    try:
        client = get_redis_client()
        if client is None:
            return False

        client.delete(key)
        logger.debug(f"Cache DELETE for key: {key}")
        return True
    except Exception as e:
        logger.warning(f"Cache delete error for key {key}: {e}")
        return False


def cache_clear_pattern(pattern: str) -> int:
    """
    Clear all cache keys matching a pattern

    Args:
        pattern: Redis key pattern (e.g., "fireflies:*")

    Returns:
        Number of keys deleted
    """
    try:
        client = get_redis_client()
        if client is None:
            return 0

        keys = client.keys(pattern)
        if keys:
            deleted = client.delete(*keys)
            logger.info(f"Cleared {deleted} cache keys matching pattern: {pattern}")
            return deleted
        return 0
    except Exception as e:
        logger.warning(f"Cache clear pattern error for {pattern}: {e}")
        return 0
