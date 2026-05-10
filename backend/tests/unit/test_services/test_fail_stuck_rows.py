"""Unit tests for batch_worker._fail_stuck_rows log-storm dedup.

Without the fix, a commit failure during the stuck-row sweep caused every
subsequent poll to re-log ERROR for every unchanged row — a log storm
proportional to stuck_rows * poll_frequency. The fix commits each row
independently and logs ERROR exactly once per row per process lifetime.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

import batch_worker


@pytest.fixture(autouse=True)
def reset_dedup_set():
    """The stuck-row dedup set is module-level; tests must start clean."""
    batch_worker._stuck_rows_commit_failed.clear()
    yield
    batch_worker._stuck_rows_commit_failed.clear()


def _stuck_row(row_id: int):
    """Minimal MagicMock shaped like a models.EmailQueue row."""
    r = MagicMock()
    r.id = row_id
    r.batch_id = f"batch-{row_id}"
    r.batch_submitted_at = datetime.now(timezone.utc) - timedelta(hours=48)
    r.batch_status = None
    return r


def _db_returning(stuck_rows):
    """Stub db.query(...).filter(...)...all() to return the given rows."""
    db = MagicMock()
    db.query.return_value.filter.return_value.filter.return_value.filter.return_value.all.return_value = stuck_rows
    return db


def test_logs_error_once_per_row_when_commit_succeeds(caplog):
    rows = [_stuck_row(1), _stuck_row(2)]
    db = _db_returning(rows)

    with caplog.at_level(logging.ERROR, logger="batch_worker"):
        marked = batch_worker._fail_stuck_rows(db, threshold_hours=24)

    assert marked == 2
    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errors) == 2
    assert db.commit.call_count == 2
    # All rows were committed; dedup set should be empty so a future cycle
    # with different rows re-logs at ERROR.
    assert batch_worker._stuck_rows_commit_failed == set()


def test_commit_failure_is_isolated_per_row(caplog):
    """Row 1's commit fails; rows 2 and 3 must still be marked + committed."""
    rows = [_stuck_row(1), _stuck_row(2), _stuck_row(3)]
    db = _db_returning(rows)

    call_count = {"n": 0}

    def _commit_side_effect():
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("simulated DB error on row 1")

    db.commit.side_effect = _commit_side_effect

    with caplog.at_level(logging.WARNING, logger="batch_worker"):
        marked = batch_worker._fail_stuck_rows(db, threshold_hours=24)

    # 2 of 3 committed successfully.
    assert marked == 2
    assert 1 in batch_worker._stuck_rows_commit_failed
    # The failed row must have a WARNING log about its commit failure.
    warnings = [
        r for r in caplog.records
        if r.levelno == logging.WARNING
        and "Failed to commit stuck-row FAILED transition" in r.getMessage()
    ]
    assert len(warnings) == 1
    # Rollback fired for the bad commit.
    assert db.rollback.call_count == 1


def test_no_error_storm_on_repeated_stuck_row(caplog):
    """Simulates poll N+1: the same stuck row is back because its earlier
    commit failed. The ERROR log must NOT fire again — that's the whole
    point of the dedup set."""
    rows = [_stuck_row(42)]
    db = _db_returning(rows)
    # Pre-seed the dedup set as if a previous poll's commit had failed for
    # this row.
    batch_worker._stuck_rows_commit_failed.add(42)
    # Still simulate the commit failing again this cycle.
    db.commit.side_effect = RuntimeError("still broken")

    with caplog.at_level(logging.DEBUG, logger="batch_worker"):
        marked = batch_worker._fail_stuck_rows(db, threshold_hours=24)

    assert marked == 0
    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert errors == [], f"re-logged ERROR on repeat encounter: {errors}"
    # And no repeat WARNING either — we only warn once.
    warnings = [
        r for r in caplog.records
        if r.levelno == logging.WARNING
        and "Failed to commit stuck-row FAILED transition" in r.getMessage()
    ]
    assert warnings == []


def test_summary_info_line_is_emitted(caplog):
    rows = [_stuck_row(1), _stuck_row(2)]
    db = _db_returning(rows)

    with caplog.at_level(logging.INFO, logger="batch_worker"):
        batch_worker._fail_stuck_rows(db, threshold_hours=24)

    summary = [
        r for r in caplog.records
        if r.levelno == logging.INFO
        and "fail_stuck_rows: marked" in r.getMessage()
    ]
    assert len(summary) == 1


def test_dedup_set_resets_when_cap_hit(caplog, monkeypatch):
    """Safety valve: if the dedup set ever fills up (pathological worst case),
    we clear it with a WARNING rather than leak memory forever."""
    monkeypatch.setattr(batch_worker, "_STUCK_ROWS_WARNED_CAP", 3)
    batch_worker._stuck_rows_commit_failed.update({100, 101, 102})

    rows = [_stuck_row(200)]
    db = _db_returning(rows)

    with caplog.at_level(logging.WARNING, logger="batch_worker"):
        batch_worker._fail_stuck_rows(db, threshold_hours=24)

    resets = [
        r for r in caplog.records
        if r.levelno == logging.WARNING
        and "Resetting _stuck_rows_commit_failed dedup set" in r.getMessage()
    ]
    assert len(resets) == 1
    # Post-reset, the set should contain only whatever rows the current cycle
    # failed to commit (here: none — commit is a MagicMock that succeeds).
    assert 100 not in batch_worker._stuck_rows_commit_failed


def test_zero_threshold_is_a_noop():
    """threshold_hours <= 0 should short-circuit without even querying."""
    db = MagicMock()
    assert batch_worker._fail_stuck_rows(db, threshold_hours=0) == 0
    db.query.assert_not_called()
