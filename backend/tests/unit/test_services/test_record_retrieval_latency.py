"""Unit tests for rag_service._record_retrieval_latency.

The latency logger is best-effort — it must never raise — but its failure mode
is "write a warning the operator will actually see", not "swallow silently at
DEBUG". These tests pin both halves of that contract.
"""
from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest

import rag_service
from rag_service import _record_retrieval_latency


@pytest.fixture(autouse=True)
def reset_failure_counter():
    """The failure counter is module-level; reset it around every test so
    tests don't leak state into each other."""
    rag_service._latency_write_failure_count = 0
    yield
    rag_service._latency_write_failure_count = 0


@pytest.fixture
def failing_session(monkeypatch):
    """Stub SessionLocal() so session.execute() raises — simulating a schema
    drift, DB outage, or connection-pool error on the log table."""
    session = MagicMock()
    session.execute.side_effect = RuntimeError("simulated DB failure")
    monkeypatch.setattr(rag_service, "SessionLocal", lambda: session)
    return session


@pytest.fixture
def ok_session(monkeypatch):
    session = MagicMock()
    monkeypatch.setattr(rag_service, "SessionLocal", lambda: session)
    return session


def test_write_failure_logs_warning_with_exc_info(failing_session, caplog):
    """First failure must surface at WARNING with a traceback — operators
    can't tell the observability pipeline is broken from DEBUG logs."""
    with caplog.at_level(logging.WARNING, logger="rag_service"):
        _record_retrieval_latency(account_id=1, started_at=0.0, result_count=0)

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "Failed to record RAG retrieval latency" in warnings[0].getMessage()
    assert warnings[0].exc_info is not None
    failing_session.rollback.assert_called_once()
    failing_session.close.assert_called_once()


def test_write_failure_does_not_raise(failing_session):
    """Caller contract: the retrieval path never sees an exception from the
    observability write, even when the DB is unreachable."""
    _record_retrieval_latency(account_id=1, started_at=0.0, result_count=0)


def test_repeated_failures_are_sampled(failing_session, caplog):
    """Persistent failures must not flood logs — only the 1st and every
    100th hit should warn. Between those we still bump the counter but stay
    quiet."""
    with caplog.at_level(logging.WARNING, logger="rag_service"):
        for _ in range(150):
            _record_retrieval_latency(account_id=1, started_at=0.0, result_count=0)

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    # 1st failure + 100th failure = 2 warnings across 150 calls.
    assert len(warnings) == 2
    assert rag_service._latency_write_failure_count == 150


def test_recovery_logs_once_and_resets_counter(monkeypatch, caplog):
    """After a spell of failures, the next successful write should emit a
    single recovery warning and reset the counter so a future outage re-warns
    on its 1st failure."""
    bad = MagicMock()
    bad.execute.side_effect = RuntimeError("simulated DB failure")
    good = MagicMock()

    monkeypatch.setattr(rag_service, "SessionLocal", lambda: bad)

    with caplog.at_level(logging.WARNING, logger="rag_service"):
        _record_retrieval_latency(account_id=1, started_at=0.0, result_count=0)
        _record_retrieval_latency(account_id=1, started_at=0.0, result_count=0)
        assert rag_service._latency_write_failure_count == 2

        monkeypatch.setattr(rag_service, "SessionLocal", lambda: good)
        _record_retrieval_latency(account_id=1, started_at=0.0, result_count=0)

    good.commit.assert_called_once()
    assert rag_service._latency_write_failure_count == 0

    recovery = [
        r for r in caplog.records
        if r.levelno == logging.WARNING and "recovered" in r.getMessage()
    ]
    assert len(recovery) == 1


def test_success_path_does_not_warn(ok_session, caplog):
    """Steady-state success must not produce warnings — the counter only
    fires recovery messaging when there was something to recover from."""
    with caplog.at_level(logging.WARNING, logger="rag_service"):
        _record_retrieval_latency(account_id=1, started_at=0.0, result_count=0)

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert warnings == []
    ok_session.commit.assert_called_once()
