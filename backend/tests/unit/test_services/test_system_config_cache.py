"""Unit tests for system_config cache invalidation.

The PR's docstring promises that config changes take effect immediately.
These tests lock both halves of that contract:

  * Same-process PUT → next GET returns the new value (in-memory invalidation).
  * Peer-process PUT (simulated by advancing the Redis generation counter)
    → next GET after the throttle window invalidates the stale local cache.
  * Redis unavailable → degrade gracefully; local invalidation still works.
"""
from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

import system_config


@pytest.fixture(autouse=True)
def reset_cache_state():
    """The module-level cache leaks across tests otherwise."""
    system_config._cache = {}
    system_config._cache_loaded = False
    system_config._cache_generation = 0
    system_config._last_generation_check = 0.0
    yield
    system_config._cache = {}
    system_config._cache_loaded = False
    system_config._cache_generation = 0
    system_config._last_generation_check = 0.0


def _db_with_rows(rows):
    db = MagicMock()
    db.query.return_value.all.return_value = rows
    return db


def _row(key, value):
    r = MagicMock()
    r.key = key
    r.value = value
    return r


def test_cache_loads_on_first_access():
    db = _db_with_rows([_row("ai_filter.default_model", "haiku")])
    # Redis absent so generation check is a no-op.
    with patch("system_config._read_remote_generation", return_value=None):
        assert system_config.get_config("ai_filter.default_model", db) == "haiku"
    db.query.assert_called_once()  # loaded exactly once


def test_cache_reused_on_subsequent_access():
    db = _db_with_rows([_row("k", "v1")])
    with patch("system_config._read_remote_generation", return_value=None):
        system_config.get_config("k", db)
        system_config.get_config("k", db)
        system_config.get_config("k", db)
    # One load across three reads — the cache is actually doing its job.
    db.query.assert_called_once()


def test_invalidate_cache_forces_reload():
    rows_first = [_row("k", "v1")]
    rows_second = [_row("k", "v2")]
    db = MagicMock()
    # Return v1 first, v2 on reload.
    db.query.return_value.all.side_effect = [rows_first, rows_second]

    with patch("system_config._read_remote_generation", return_value=None):
        assert system_config.get_config("k", db) == "v1"
        system_config.invalidate_cache()
        assert system_config.get_config("k", db) == "v2"


def test_peer_worker_bump_invalidates_on_next_check(monkeypatch):
    """Simulates another worker's PUT having bumped the Redis counter — after
    the throttle window, the local GET must reload and return the new value."""
    # Shrink the throttle so the test doesn't need real sleep.
    monkeypatch.setattr(system_config, "_GENERATION_CHECK_INTERVAL_SECONDS", 0.0)

    rows_first = [_row("k", "v1")]
    rows_second = [_row("k", "v2")]
    db = MagicMock()
    db.query.return_value.all.side_effect = [rows_first, rows_second]

    # First access: remote gen == local gen (both 0). Cache loads normally.
    with patch("system_config._read_remote_generation", return_value=0):
        assert system_config.get_config("k", db) == "v1"

    # Peer worker bumps gen to 1. Next access detects it and reloads.
    with patch("system_config._read_remote_generation", return_value=1):
        assert system_config.get_config("k", db) == "v2"

    assert system_config._cache_generation == 1


def test_redis_unavailable_falls_back_to_process_local(monkeypatch):
    """When Redis can't be reached, generation-based invalidation is skipped
    but the caller's PUT still clears its own worker's cache."""
    monkeypatch.setattr(system_config, "_GENERATION_CHECK_INTERVAL_SECONDS", 0.0)

    db = _db_with_rows([_row("k", "v1")])
    with patch("system_config._read_remote_generation", return_value=None):
        assert system_config.get_config("k", db) == "v1"

    # Invalidate locally (what the PUT handler does). New DB read returns v2.
    db.query.return_value.all.return_value = [_row("k", "v2")]
    system_config.invalidate_cache()

    with patch("system_config._read_remote_generation", return_value=None):
        assert system_config.get_config("k", db) == "v2"


def test_generation_check_is_throttled(monkeypatch):
    """The Redis counter must NOT be sampled on every call — hot-path
    latency would suffer otherwise. The throttle window gates it."""
    monkeypatch.setattr(system_config, "_GENERATION_CHECK_INTERVAL_SECONDS", 10.0)
    db = _db_with_rows([_row("k", "v1")])

    with patch("system_config._read_remote_generation", return_value=0) as mock_read:
        for _ in range(50):
            system_config.get_config("k", db)

    # At most one check during the throttle window — the initial one.
    assert mock_read.call_count <= 1


def test_bump_remote_generation_handles_redis_failure(caplog):
    """Redis outage must not break PUT handling — the local invalidation
    still runs, we just log and move on."""
    import logging

    with patch(
        "cache_service.get_redis_client",
        side_effect=RuntimeError("redis unreachable"),
    ):
        with caplog.at_level(logging.WARNING, logger="system_config"):
            system_config._bump_remote_generation()

    warnings = [
        r for r in caplog.records
        if r.levelno == logging.WARNING
        and "Could not bump system_config generation" in r.getMessage()
    ]
    assert len(warnings) == 1


def test_put_handler_invalidates_and_bumps(monkeypatch):
    """End-to-end: the HTTP PUT handler must both clear the local cache and
    advance the Redis generation counter so peer workers see the change."""
    import asyncio

    # Arrange: pre-seed local cache as if a prior read had populated it.
    system_config._cache = {"k": "stale"}
    system_config._cache_loaded = True

    row = MagicMock(key="k", value="fresh", description=None)
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = row

    called = {"bumped": False}

    def _fake_bump():
        called["bumped"] = True

    monkeypatch.setattr(system_config, "_bump_remote_generation", _fake_bump)

    payload = system_config.SystemConfigUpdate(value="fresh")
    asyncio.run(
        system_config.update_system_config(
            key="k",
            payload=payload,
            current_user=MagicMock(id=1),
            db=db,
        )
    )

    assert system_config._cache_loaded is False  # local invalidated
    assert called["bumped"] is True  # peer workers notified
