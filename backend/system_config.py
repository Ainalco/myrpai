from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
import logging
import threading
import time

from database import get_db
from auth import get_current_active_user
import models

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# In-memory cache
#
# The cache is process-local. In a multi-worker deployment (Gunicorn/Uvicorn
# with workers > 1) each worker holds its own dict, so a PUT served by one
# worker would otherwise leave the others pinned to the stale value until
# restart. To make operator config changes take effect on all workers within
# ~1 second, we piggyback on Redis as a cross-process generation counter:
#
#   * Every successful PUT increments ``system_config:generation``.
#   * Each ``get_config`` call samples the counter at most once per
#     GENERATION_CHECK_INTERVAL_SECONDS and invalidates the local cache when
#     it advances. Failing Redis degrades gracefully to the old single-process
#     behaviour — PUTs still clear the handling worker's cache.
# ---------------------------------------------------------------------------
_cache: dict[str, str] = {}
_cache_loaded: bool = False
_cache_lock = threading.Lock()

_GENERATION_KEY = "system_config:generation"
_GENERATION_CHECK_INTERVAL_SECONDS = 1.0
_cache_generation: int = 0
_last_generation_check: float = 0.0


def _read_remote_generation() -> Optional[int]:
    """Return the current Redis generation counter, or None if Redis is
    unavailable (in which case we stay on single-process invalidation)."""
    try:
        from cache_service import get_redis_client

        client = get_redis_client()
        if client is None:
            return None
        raw = client.get(_GENERATION_KEY)
        return int(raw) if raw is not None else 0
    except Exception as e:
        logger.debug("Could not read system_config generation: %s", e)
        return None


def _bump_remote_generation() -> None:
    """Advance the Redis generation counter so peer workers invalidate."""
    try:
        from cache_service import get_redis_client

        client = get_redis_client()
        if client is None:
            return
        client.incr(_GENERATION_KEY)
    except Exception as e:
        logger.warning("Could not bump system_config generation: %s", e)


def _maybe_check_remote_generation() -> None:
    """Invalidate the local cache when a peer worker has bumped the counter.

    Throttled to at most once per _GENERATION_CHECK_INTERVAL_SECONDS so the
    hot path doesn't pay a Redis round-trip on every config lookup."""
    global _last_generation_check, _cache_generation
    now = time.time()
    if now - _last_generation_check < _GENERATION_CHECK_INTERVAL_SECONDS:
        return
    _last_generation_check = now
    remote = _read_remote_generation()
    if remote is None or remote == _cache_generation:
        return
    logger.info(
        "SystemConfig cache invalidated via generation bump (local=%d, remote=%d)",
        _cache_generation, remote,
    )
    invalidate_cache()
    _cache_generation = remote


def _load_cache(db: Session) -> None:
    """Load all SystemConfig rows into the in-memory cache."""
    global _cache, _cache_loaded
    rows = db.query(models.SystemConfig).all()
    _cache = {row.key: row.value for row in rows}
    _cache_loaded = True
    logger.debug("SystemConfig cache loaded with %d entries", len(_cache))


def get_config(key: str, db: Session, default: Optional[str] = None) -> Optional[str]:
    """Return the cached config value for *key*, loading the cache if needed."""
    _maybe_check_remote_generation()
    global _cache_loaded
    if not _cache_loaded:
        with _cache_lock:
            if not _cache_loaded:
                _load_cache(db)
    return _cache.get(key, default)


def get_config_float(key: str, db: Session, default: float = 0.0) -> float:
    """Return the config value for *key* as a float."""
    raw = get_config(key, db)
    if raw is None:
        return default
    try:
        return float(raw)
    except (ValueError, TypeError):
        return default


def get_config_int(key: str, db: Session, default: int = 0) -> int:
    """Return the config value for *key* as an int."""
    raw = get_config(key, db)
    if raw is None:
        return default
    try:
        return int(raw)
    except (ValueError, TypeError):
        return default


def invalidate_cache() -> None:
    """Mark the cache as stale so it will be reloaded on next access."""
    global _cache_loaded
    _cache_loaded = False


# ---------------------------------------------------------------------------
# Superadmin dependency
# ---------------------------------------------------------------------------
async def _require_superadmin(
    current_user: models.User = Depends(get_current_active_user),
) -> models.User:
    if not current_user.is_superadmin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Superadmin access required",
        )
    return current_user


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------
class SystemConfigUpdate(BaseModel):
    value: str
    description: Optional[str] = None


class SystemConfigOut(BaseModel):
    key: str
    value: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@router.get("", response_model=list[SystemConfigOut])
async def list_system_config(
    current_user: models.User = Depends(_require_superadmin),
    db: Session = Depends(get_db),
):
    """List all system configuration entries (superadmin only)."""
    rows = db.query(models.SystemConfig).order_by(models.SystemConfig.key).all()
    return rows


@router.put("/{key}", response_model=SystemConfigOut)
async def update_system_config(
    key: str,
    payload: SystemConfigUpdate,
    current_user: models.User = Depends(_require_superadmin),
    db: Session = Depends(get_db),
):
    """Create or update a system configuration entry (superadmin only)."""
    row = db.query(models.SystemConfig).filter(models.SystemConfig.key == key).first()
    if row is None:
        row = models.SystemConfig(key=key, value=payload.value, description=payload.description)
        db.add(row)
    else:
        row.value = payload.value
        if payload.description is not None:
            row.description = payload.description
    db.commit()
    db.refresh(row)
    invalidate_cache()
    # Advance the Redis generation so peer workers pick up the change on their
    # next lookup. Falls through silently if Redis is unavailable; the local
    # worker's cache is still invalidated above.
    _bump_remote_generation()
    logger.info("SystemConfig key '%s' updated by user %s", key, current_user.id)
    return row
