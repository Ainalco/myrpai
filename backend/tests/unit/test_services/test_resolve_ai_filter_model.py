"""Unit tests for conditional_logic.resolve_ai_filter_model.

The original form opened a fresh SessionLocal() on every call to read a kill
switch, even though most callers already had a ``db`` in hand. These tests
lock the current contract:

  * When ``db`` is passed, SessionLocal() is NOT called.
  * When ``db`` is omitted, SessionLocal() IS called exactly once and the
    session is closed afterwards.
  * Kill switch > per-component config > "sonnet" default.
  * A raised exception while reading system_config never bubbles up —
    resolution falls through to the per-component / default path.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import conditional_logic
from conditional_logic import resolve_ai_filter_model


def test_uses_caller_db_without_opening_new_session():
    db = MagicMock(name="caller-db")

    with patch("system_config.get_config", return_value=None) as mock_get, \
         patch("database.SessionLocal") as mock_session_local:
        choice = resolve_ai_filter_model({"model": "haiku"}, db=db)

    mock_get.assert_called_once_with("ai_filter.default_model", db)
    mock_session_local.assert_not_called()
    assert choice == "haiku"


def test_opens_and_closes_session_when_db_is_none():
    owned_session = MagicMock(name="owned-session")

    with patch("system_config.get_config", return_value=None), \
         patch("database.SessionLocal", return_value=owned_session) as mock_session_local:
        choice = resolve_ai_filter_model({"model": "sonnet"})

    mock_session_local.assert_called_once()
    owned_session.close.assert_called_once()
    assert choice == "sonnet"


def test_kill_switch_wins_over_per_component():
    db = MagicMock()
    with patch("system_config.get_config", return_value="haiku"):
        choice = resolve_ai_filter_model({"model": "sonnet"}, db=db)
    assert choice == "haiku"


def test_per_component_wins_when_kill_switch_not_set():
    db = MagicMock()
    with patch("system_config.get_config", return_value=None):
        choice = resolve_ai_filter_model({"model": "haiku"}, db=db)
    assert choice == "haiku"


def test_defaults_to_sonnet_when_nothing_configured():
    db = MagicMock()
    with patch("system_config.get_config", return_value=None):
        choice = resolve_ai_filter_model({}, db=db)
    assert choice == "sonnet"


def test_invalid_kill_switch_value_falls_through():
    """If the kill-switch value is something unexpected, it must not be
    returned verbatim — fall through to per-component or default."""
    db = MagicMock()
    with patch("system_config.get_config", return_value="opus"):
        choice = resolve_ai_filter_model({"model": "haiku"}, db=db)
    assert choice == "haiku"


def test_system_config_exception_is_swallowed():
    """A failure reading system_config must never break an AI filter — the
    resolver falls back to per-component config and logs a warning."""
    db = MagicMock()
    with patch("system_config.get_config", side_effect=RuntimeError("boom")):
        choice = resolve_ai_filter_model({"model": "haiku"}, db=db)
    assert choice == "haiku"
