"""Unit tests for rag_service.validate_configured_models (issue #171).

The existing ``test_startup_validation.py`` covers the outer wrapper in
``main._validate_startup_models`` — it mocks out ``validate_configured_models``
entirely and asserts the wrapper's swallow-vs-raise policy.

This file exercises the *inner* function end-to-end. The asks in #171:

  1. SessionLocal() raising OperationalError must surface out — the outer
     wrapper (already tested) is what swallows transient DB errors, not
     this helper.
  2. Happy path with a valid config returns the {role: model_id} map.
  3. An invalid model id raises ConfiguredModelError so the outer wrapper
     can treat that as a fatal startup error.
  4. A failed ai_models lookup must NOT kill validation — the function
     logs and falls back to default-only validation. This is the lax path
     the C4 fix introduced and without a test a refactor could tighten it
     back to fatal.
"""
from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import OperationalError

import rag_service
from rag_service import (
    ConfiguredModelError,
    DEFAULT_HAIKU_MODEL,
    DEFAULT_SONNET_MODEL,
    validate_configured_models,
)


def _session_returning(ai_model_ids=None, raise_on_query=False):
    """Build a fake Session whose AiModel query returns the given ids (or
    raises if asked)."""
    session = MagicMock(name="test-session")
    q = MagicMock()
    if raise_on_query:
        q.all.side_effect = OperationalError("SELECT model_id", {}, Exception("down"))
    else:
        q.all.return_value = [(mid,) for mid in (ai_model_ids or [])]
    session.query.return_value = q
    return session


def test_happy_path_returns_validated_map():
    """Valid defaults in SystemConfig + ai_models row present → returns the
    {key: model_id} dict and does not raise."""
    session = _session_returning(ai_model_ids=[DEFAULT_HAIKU_MODEL, DEFAULT_SONNET_MODEL])
    with patch.object(rag_service, "get_haiku_model", return_value=DEFAULT_HAIKU_MODEL), \
         patch.object(rag_service, "get_sonnet_model", return_value=DEFAULT_SONNET_MODEL):
        result = validate_configured_models(db=session)

    assert result == {
        "rag.haiku_model": DEFAULT_HAIKU_MODEL,
        "rag.sonnet_model": DEFAULT_SONNET_MODEL,
    }


def test_empty_model_id_raises_configured_model_error():
    """Empty SystemConfig value is a real bug the operator needs to see —
    must raise so startup aborts (via the outer wrapper)."""
    session = _session_returning(ai_model_ids=[])
    with patch.object(rag_service, "get_haiku_model", return_value=""), \
         patch.object(rag_service, "get_sonnet_model", return_value=DEFAULT_SONNET_MODEL):
        with pytest.raises(ConfiguredModelError, match="rag.haiku_model.*empty"):
            validate_configured_models(db=session)


def test_non_claude_prefix_raises_configured_model_error():
    """A model id that doesn't start with 'claude-' is almost certainly a
    typo or paste from another provider — fail loud."""
    session = _session_returning(ai_model_ids=[])
    with patch.object(rag_service, "get_haiku_model", return_value="gpt-4o"), \
         patch.object(rag_service, "get_sonnet_model", return_value=DEFAULT_SONNET_MODEL):
        with pytest.raises(ConfiguredModelError, match="does not look like an Anthropic"):
            validate_configured_models(db=session)


def test_ai_models_query_failure_is_non_fatal(caplog):
    """If ai_models is unavailable (schema drift, rolling migration, etc.)
    the function must log a warning and continue with default-only
    validation — NOT raise. Otherwise a briefly-bad ai_models table blocks
    every worker from starting."""
    session = _session_returning(raise_on_query=True)
    with patch.object(rag_service, "get_haiku_model", return_value=DEFAULT_HAIKU_MODEL), \
         patch.object(rag_service, "get_sonnet_model", return_value=DEFAULT_SONNET_MODEL):
        with caplog.at_level(logging.WARNING, logger="rag_service"):
            result = validate_configured_models(db=session)

    assert result == {
        "rag.haiku_model": DEFAULT_HAIKU_MODEL,
        "rag.sonnet_model": DEFAULT_SONNET_MODEL,
    }
    warnings = [
        r for r in caplog.records
        if r.levelno == logging.WARNING
        and "could not load ai_models" in r.getMessage()
    ]
    assert len(warnings) == 1


def test_unknown_model_with_empty_ai_models_is_allowed():
    """Empty ai_models table → only the hardcoded default check applies.
    A custom model id is accepted (it will use default Sonnet pricing but
    that's flagged via a separate warning in the outer check — not this
    function's job to police)."""
    session = _session_returning(ai_model_ids=[])
    with patch.object(rag_service, "get_haiku_model", return_value="claude-haiku-custom-123"), \
         patch.object(rag_service, "get_sonnet_model", return_value=DEFAULT_SONNET_MODEL):
        result = validate_configured_models(db=session)

    assert result["rag.haiku_model"] == "claude-haiku-custom-123"


def test_unknown_model_with_populated_ai_models_logs_warning(caplog):
    """If ai_models is populated but missing this id, log a WARNING and
    continue — not fatal, but operators need to notice."""
    session = _session_returning(ai_model_ids=[DEFAULT_HAIKU_MODEL, DEFAULT_SONNET_MODEL])
    with patch.object(rag_service, "get_haiku_model", return_value="claude-haiku-unknown"), \
         patch.object(rag_service, "get_sonnet_model", return_value=DEFAULT_SONNET_MODEL):
        with caplog.at_level(logging.WARNING, logger="rag_service"):
            result = validate_configured_models(db=session)

    assert result["rag.haiku_model"] == "claude-haiku-unknown"
    warnings = [
        r for r in caplog.records
        if r.levelno == logging.WARNING
        and "not in ai_models table" in r.getMessage()
    ]
    assert len(warnings) == 1


def test_session_local_raises_propagates_to_caller(monkeypatch):
    """When called with db=None the function opens SessionLocal(). If that
    raises (transient DB boot race), the exception must bubble up — the
    outer main._validate_startup_models wrapper is responsible for
    swallowing it. Keeping the inner function opaque here is the whole
    point of the C4 layering: the helper never swallows transient errors
    silently."""
    monkeypatch.setattr(
        rag_service,
        "SessionLocal",
        MagicMock(side_effect=OperationalError("connect", {}, Exception("down"))),
    )

    with pytest.raises(OperationalError):
        validate_configured_models(db=None)


def test_owned_session_is_closed_on_success(monkeypatch):
    """Path ownership contract: when the caller omits db, the owned session
    must be closed in the finally block so startup doesn't leak a
    connection."""
    owned = MagicMock(name="owned")
    owned.query.return_value.all.return_value = []
    monkeypatch.setattr(rag_service, "SessionLocal", MagicMock(return_value=owned))

    with patch.object(rag_service, "get_haiku_model", return_value=DEFAULT_HAIKU_MODEL), \
         patch.object(rag_service, "get_sonnet_model", return_value=DEFAULT_SONNET_MODEL):
        validate_configured_models(db=None)

    owned.close.assert_called_once()


def test_owned_session_is_closed_on_configured_model_error(monkeypatch):
    """Even when we raise ConfiguredModelError, the owned session must be
    released — otherwise a boot-time config bug plus rapid restart loop
    would burn through the pool."""
    owned = MagicMock(name="owned")
    owned.query.return_value.all.return_value = []
    monkeypatch.setattr(rag_service, "SessionLocal", MagicMock(return_value=owned))

    with patch.object(rag_service, "get_haiku_model", return_value=""), \
         patch.object(rag_service, "get_sonnet_model", return_value=DEFAULT_SONNET_MODEL):
        with pytest.raises(ConfiguredModelError):
            validate_configured_models(db=None)

    owned.close.assert_called_once()


def test_caller_db_is_not_closed(monkeypatch):
    """When the caller passes its own session, we must NOT close it —
    that's the caller's responsibility. A regression that closes caller
    sessions would break execute_workflow's surrounding transaction."""
    caller_db = _session_returning(ai_model_ids=[])
    # Ensure SessionLocal is never even reached.
    monkeypatch.setattr(rag_service, "SessionLocal", MagicMock(side_effect=AssertionError))

    with patch.object(rag_service, "get_haiku_model", return_value=DEFAULT_HAIKU_MODEL), \
         patch.object(rag_service, "get_sonnet_model", return_value=DEFAULT_SONNET_MODEL):
        validate_configured_models(db=caller_db)

    caller_db.close.assert_not_called()
