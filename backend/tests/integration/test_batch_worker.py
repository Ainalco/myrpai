"""Integration tests for the Anthropic Batch API worker.

Covers the three failure modes from
docs/superpowers/plans/2026-04-21-batch-api-idempotency.md:

  1. Crash between Anthropic response and phase-2 DB commit must NOT trigger
     a duplicate Anthropic submit on restart. Reconciliation must adopt the
     orphaned batch via custom_id.
  2. Concurrent workers cannot both claim the same row — the UNIQUE
     constraint on idempotency_key forces the loser to error at phase-1
     before any Anthropic call.
  3. A row stuck in `submitting` with an already-ended batch on the
     Anthropic side moves straight to `completed` via reconciliation
     without any fresh submit.

The Anthropic HTTP client (`anthropic_batch`) is mocked with AsyncMock — no
real network calls.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.exc import IntegrityError

import anthropic_batch
import batch_worker
import models


def _build_test_request(row: models.EmailQueue) -> Dict[str, Any]:
    return {
        "model": "claude-test",
        "max_tokens": 10,
        "messages": [{"role": "user", "content": f"row:{row.id}"}],
    }


def _expected_custom_id(row_id: int, request_dict: Dict[str, Any]) -> str:
    body = json.dumps(request_dict, sort_keys=True, separators=(",", ":"))
    prompt_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
    return batch_worker.compute_custom_id(row_id, prompt_hash)


def _make_pending_row(db_session, user) -> models.EmailQueue:
    row = models.EmailQueue(
        user_id=user.id,
        recipient_email="recip@example.com",
        subject="Hi",
        body="body",
        scheduled_at=datetime.now(timezone.utc),
        status="pending",
        batch_stage=batch_worker.STAGE_PENDING_SUBMIT,
    )
    db_session.add(row)
    db_session.commit()
    return row


async def _async_iter(items: List[Dict[str, Any]]):
    for item in items:
        yield item


@pytest.fixture
def test_user(db_session):
    # Build the User directly — the project's factory-boy scaffolding never
    # binds sqlalchemy_session, so UserFactory.create() raises in every test.
    # Bypassing it keeps these tests independent of that latent bug.
    user = models.User(
        email="batch@example.com",
        hashed_password="x" * 60,
        full_name="Batch User",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def register_builder():
    batch_worker.set_request_builder(_build_test_request)
    yield
    batch_worker.set_request_builder(None)


@pytest.mark.integration
@pytest.mark.asyncio
class TestCrashRecovery:
    """Acceptance test 1: SIGKILL between Anthropic response and phase-2 commit
    must NOT cause a duplicate submit on worker restart."""

    async def test_crash_after_anthropic_before_phase2_does_not_resubmit(
        self, db_session, test_user, register_builder
    ):
        row = _make_pending_row(db_session, test_user)
        expected_cid = _expected_custom_id(row.id, _build_test_request(row))

        create_batch_mock = AsyncMock(return_value={
            "id": "batch_abc123",
            "processing_status": "in_progress",
        })

        # --- First cycle: complete submit normally ---
        with patch("batch_worker.anthropic_batch.create_batch", create_batch_mock):
            result = await batch_worker.submit_pending_batches(db_session)

        assert result["submitted"] == 1
        assert create_batch_mock.await_count == 1
        db_session.refresh(row)
        assert row.batch_stage == batch_worker.STAGE_SUBMITTED
        assert row.batch_id == "batch_abc123"
        assert row.custom_id == expected_cid
        assert row.idempotency_key is not None

        # --- Simulate the crash: phase-2 writes are lost (batch_id + stage
        #     never landed), row is stuck in "submitting" with idempotency_key
        #     and custom_id intact (those were phase-1). ---
        row.batch_id = None
        row.batch_stage = batch_worker.STAGE_SUBMITTING
        row.batch_submitted_at = None
        row.batch_status = None
        db_session.commit()

        # --- Restart: reconciliation must adopt the batch and MUST NOT call
        #     create_batch again. ---
        list_mock = AsyncMock(return_value={
            "data": [{
                "id": "batch_abc123",
                "processing_status": "ended",
                "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "results_url": "https://api.anthropic.com/fake/results",
            }],
            "has_more": False,
        })
        results_mock = lambda _url: _async_iter([
            {
                "custom_id": expected_cid,
                "result": {"type": "succeeded", "message": {"content": [{"type": "text", "text": "ok"}]}},
            }
        ])

        create_batch_mock.reset_mock()
        with patch("batch_worker.anthropic_batch.create_batch", create_batch_mock), \
             patch("batch_worker.anthropic_batch.list_batches", list_mock), \
             patch("batch_worker.anthropic_batch.iterate_batch_results", results_mock):
            recon = await batch_worker.reconcile_submitting_rows(
                db_session, lookback_hours=24
            )
            # Reconcile should have adopted the row; no submit cycle needed,
            # but we still call it to prove it won't re-claim the row.
            resubmit = await batch_worker.submit_pending_batches(db_session)

        assert recon["reconciled"] == 1
        assert recon["released"] == 0
        assert create_batch_mock.await_count == 0, (
            "Anthropic create_batch must NOT be called again after reconcile adopted the batch"
        )
        assert resubmit["submitted"] == 0
        db_session.refresh(row)
        assert row.batch_stage == batch_worker.STAGE_COMPLETED
        assert row.batch_id == "batch_abc123"


@pytest.mark.integration
@pytest.mark.asyncio
class TestIdempotencyKeyUniqueness:
    """Acceptance test 2: UNIQUE(idempotency_key) blocks a concurrent submit
    of the same row before the Anthropic call is made."""

    async def test_duplicate_idempotency_key_blocks_second_write(
        self, db_session, test_user
    ):
        row = _make_pending_row(db_session, test_user)
        req = _build_test_request(row)
        body = json.dumps(req, sort_keys=True, separators=(",", ":"))
        prompt_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
        idem = batch_worker.compute_idempotency_key(row.id, prompt_hash)

        # Worker A claims the row.
        row.idempotency_key = idem
        row.prompt_hash = prompt_hash
        row.custom_id = batch_worker.compute_custom_id(row.id, prompt_hash)
        row.batch_stage = batch_worker.STAGE_SUBMITTING
        db_session.commit()

        # Worker B attempts to write the SAME idempotency_key on a different row.
        # The UNIQUE constraint must fail at the DB layer (before any
        # Anthropic network call could happen). The violation can surface
        # either at the explicit commit or sooner via autoflush triggered by
        # the first attribute access on `dup` after the preceding commit
        # expired it — either path is an acceptable outcome.
        dup = _make_pending_row(db_session, test_user)
        dup_id = dup.id  # snapshot before expiration-triggered autoflush
        with pytest.raises(IntegrityError):
            dup.idempotency_key = idem
            dup.prompt_hash = prompt_hash
            dup.custom_id = batch_worker.compute_custom_id(dup_id, prompt_hash)
            dup.batch_stage = batch_worker.STAGE_SUBMITTING
            db_session.commit()
        db_session.rollback()


@pytest.mark.integration
@pytest.mark.asyncio
class TestReconciliation:
    """Acceptance test 3: a row stuck in `submitting` with a matching
    custom_id on the Anthropic side is adopted into `completed` without
    any fresh submit."""

    async def test_reconcile_adopts_existing_batch_by_custom_id(
        self, db_session, test_user, register_builder
    ):
        row = _make_pending_row(db_session, test_user)
        req = _build_test_request(row)
        body = json.dumps(req, sort_keys=True, separators=(",", ":"))
        prompt_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
        cid = batch_worker.compute_custom_id(row.id, prompt_hash)
        row.idempotency_key = batch_worker.compute_idempotency_key(row.id, prompt_hash)
        row.prompt_hash = prompt_hash
        row.custom_id = cid
        row.batch_stage = batch_worker.STAGE_SUBMITTING
        db_session.commit()

        create_batch_mock = AsyncMock()
        list_mock = AsyncMock(return_value={
            "data": [{
                "id": "batch_existing",
                "processing_status": "ended",
                "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "results_url": "https://api.anthropic.com/fake/results",
            }],
            "has_more": False,
        })
        results_mock = lambda _url: _async_iter([
            {"custom_id": cid, "result": {"type": "succeeded"}}
        ])

        with patch("batch_worker.anthropic_batch.create_batch", create_batch_mock), \
             patch("batch_worker.anthropic_batch.list_batches", list_mock), \
             patch("batch_worker.anthropic_batch.iterate_batch_results", results_mock):
            result = await batch_worker.reconcile_submitting_rows(
                db_session, lookback_hours=24
            )

        assert result["reconciled"] == 1
        assert create_batch_mock.await_count == 0
        db_session.refresh(row)
        assert row.batch_stage == batch_worker.STAGE_COMPLETED
        assert row.batch_id == "batch_existing"

    async def test_reconcile_releases_row_when_no_in_flight_match(
        self, db_session, test_user, register_builder
    ):
        """If Anthropic has no matching custom_id AND no in-progress batches,
        the row is safe to release back to pending_submit for retry."""
        row = _make_pending_row(db_session, test_user)
        row.idempotency_key = "deadbeef" * 8
        row.prompt_hash = "x" * 64
        row.custom_id = f"email_queue:{row.id}:xxxxxxxx"
        row.batch_stage = batch_worker.STAGE_SUBMITTING
        db_session.commit()

        list_mock = AsyncMock(return_value={"data": [], "has_more": False})
        results_mock = lambda _url: _async_iter([])

        with patch("batch_worker.anthropic_batch.list_batches", list_mock), \
             patch("batch_worker.anthropic_batch.iterate_batch_results", results_mock):
            result = await batch_worker.reconcile_submitting_rows(
                db_session, lookback_hours=24
            )

        assert result["reconciled"] == 0
        assert result["released"] == 1
        db_session.refresh(row)
        assert row.batch_stage == batch_worker.STAGE_PENDING_SUBMIT


def _make_submitted_row(
    db_session,
    user,
    batch_id: str,
    submitted_at: datetime,
) -> models.EmailQueue:
    """Helper: a row already in batch_stage='submitted' with the given age."""
    row = models.EmailQueue(
        user_id=user.id,
        recipient_email="recip@example.com",
        subject="Hi",
        body="body",
        scheduled_at=datetime.now(timezone.utc),
        status="pending",
        batch_stage=batch_worker.STAGE_SUBMITTED,
        batch_id=batch_id,
        batch_status="in_progress",
        batch_submitted_at=submitted_at,
        idempotency_key=f"idem_{batch_id}_{user.id}_{submitted_at.timestamp()}",
        custom_id=f"email_queue:{batch_id}:xxxxxxxx",
        prompt_hash="x" * 64,
    )
    db_session.add(row)
    db_session.commit()
    return row


@pytest.fixture(autouse=True)
def _reset_poll_failure_counter():
    """The module-level _batch_poll_failures dict persists across tests; reset
    it so each test sees a clean backoff state."""
    batch_worker._batch_poll_failures.clear()
    yield
    batch_worker._batch_poll_failures.clear()


@pytest.mark.integration
@pytest.mark.asyncio
class TestPollTerminalStates:
    """Poll loop must drive rows to failed-fast when Anthropic reports a
    terminal-failure state — expired, canceled, canceling. Without this, rows
    submitted to an expired batch sit in 'submitted' forever."""

    async def test_expired_batch_fails_rows_in_one_cycle(self, db_session, test_user):
        row = _make_submitted_row(
            db_session, test_user, batch_id="batch_exp",
            submitted_at=datetime.now(timezone.utc) - timedelta(hours=2),
        )

        get_mock = AsyncMock(return_value={
            "id": "batch_exp", "processing_status": "expired",
        })
        with patch("batch_worker.anthropic_batch.get_batch", get_mock):
            result = await batch_worker.poll_submitted_batches(db_session)

        assert result["failed_terminal"] == 1
        db_session.refresh(row)
        assert row.batch_stage == batch_worker.STAGE_FAILED
        assert row.status == "failed"
        assert row.batch_status == "expired"
        assert row.error_message and "expired" in row.error_message

    async def test_canceled_batch_fails_rows_in_one_cycle(self, db_session, test_user):
        row = _make_submitted_row(
            db_session, test_user, batch_id="batch_cancel",
            submitted_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )

        get_mock = AsyncMock(return_value={
            "id": "batch_cancel", "processing_status": "canceled",
        })
        with patch("batch_worker.anthropic_batch.get_batch", get_mock):
            result = await batch_worker.poll_submitted_batches(db_session)

        assert result["failed_terminal"] == 1
        db_session.refresh(row)
        assert row.batch_stage == batch_worker.STAGE_FAILED
        assert row.batch_status == "canceled"

    async def test_in_progress_batch_is_left_alone(self, db_session, test_user):
        row = _make_submitted_row(
            db_session, test_user, batch_id="batch_running",
            submitted_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )

        get_mock = AsyncMock(return_value={
            "id": "batch_running", "processing_status": "in_progress",
        })
        with patch("batch_worker.anthropic_batch.get_batch", get_mock):
            result = await batch_worker.poll_submitted_batches(db_session)

        assert result["still_running"] == 1
        assert result["failed_terminal"] == 0
        db_session.refresh(row)
        assert row.batch_stage == batch_worker.STAGE_SUBMITTED


@pytest.mark.integration
@pytest.mark.asyncio
class TestStuckBatchFailsafe:
    """A row whose batch_submitted_at is older than the stuck threshold must
    be failed out regardless of what Anthropic says, so customers don't sit
    in limbo when a batch id silently breaks."""

    async def test_stuck_row_is_failed_before_anthropic_is_even_called(
        self, db_session, test_user
    ):
        old_submit = datetime.now(timezone.utc) - timedelta(hours=48)
        row = _make_submitted_row(
            db_session, test_user, batch_id="batch_zombie",
            submitted_at=old_submit,
        )

        # get_batch should NOT be called for a stuck row — failsafe fires
        # before the Anthropic round-trip.
        get_mock = AsyncMock(return_value={
            "id": "batch_zombie", "processing_status": "in_progress",
        })
        with patch("batch_worker.anthropic_batch.get_batch", get_mock):
            result = await batch_worker.poll_submitted_batches(
                db_session, stuck_threshold_hours=26,
            )

        assert result["failed_stuck"] == 1
        db_session.refresh(row)
        assert row.batch_stage == batch_worker.STAGE_FAILED
        assert row.status == "failed"
        assert row.error_message and "26h" in row.error_message


@pytest.mark.integration
@pytest.mark.asyncio
class TestPollHttpBackoff:
    """N consecutive poll failures on the same batch id must eventually give
    up and fail the rows so they re-enter the retry/fallback path."""

    async def test_below_threshold_keeps_polling(self, db_session, test_user):
        row = _make_submitted_row(
            db_session, test_user, batch_id="batch_flaky",
            submitted_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )

        get_mock = AsyncMock(side_effect=anthropic_batch.AnthropicBatchError("500"))
        with patch("batch_worker.anthropic_batch.get_batch", get_mock):
            # Exhaust N-1 attempts — row stays submitted, counter accumulates.
            for _ in range(batch_worker.DEFAULT_MAX_POLL_FAILURES_PER_BATCH - 1):
                result = await batch_worker.poll_submitted_batches(db_session)
                assert result["failed_poll_errors"] == 0

        db_session.refresh(row)
        assert row.batch_stage == batch_worker.STAGE_SUBMITTED
        assert batch_worker._batch_poll_failures.get("batch_flaky") == (
            batch_worker.DEFAULT_MAX_POLL_FAILURES_PER_BATCH - 1
        )

    async def test_at_threshold_fails_rows_and_clears_counter(
        self, db_session, test_user
    ):
        row = _make_submitted_row(
            db_session, test_user, batch_id="batch_dead",
            submitted_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )

        get_mock = AsyncMock(side_effect=anthropic_batch.AnthropicBatchError("500"))
        with patch("batch_worker.anthropic_batch.get_batch", get_mock):
            for _ in range(batch_worker.DEFAULT_MAX_POLL_FAILURES_PER_BATCH):
                result = await batch_worker.poll_submitted_batches(db_session)

        assert result["failed_poll_errors"] == 1
        db_session.refresh(row)
        assert row.batch_stage == batch_worker.STAGE_FAILED
        assert row.status == "failed"
        assert row.error_message and "poll failed" in row.error_message
        # Counter cleared after giving up.
        assert "batch_dead" not in batch_worker._batch_poll_failures

    async def test_successful_poll_resets_counter(self, db_session, test_user):
        _ = _make_submitted_row(
            db_session, test_user, batch_id="batch_recovers",
            submitted_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )

        flaky = AsyncMock(side_effect=anthropic_batch.AnthropicBatchError("500"))
        with patch("batch_worker.anthropic_batch.get_batch", flaky):
            await batch_worker.poll_submitted_batches(db_session)
            await batch_worker.poll_submitted_batches(db_session)
        assert batch_worker._batch_poll_failures.get("batch_recovers") == 2

        healthy = AsyncMock(return_value={
            "id": "batch_recovers", "processing_status": "in_progress",
        })
        with patch("batch_worker.anthropic_batch.get_batch", healthy):
            await batch_worker.poll_submitted_batches(db_session)

        assert "batch_recovers" not in batch_worker._batch_poll_failures
