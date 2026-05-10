"""Anthropic Batch API background worker.

Implements the correctness contract from
docs/superpowers/plans/2026-04-21-batch-api-idempotency.md:

  1. Two-phase write around every Anthropic submit call.
     Phase 1 (DB): mark row batch_stage="submitting" + write idempotency_key
                   and custom_id, then commit. This is the durable "we are
                   about to talk to Anthropic" marker.
     Phase 2 (DB): after Anthropic accepts the batch, record batch_id +
                   batch_stage="submitted", commit again.

     A crash between the Anthropic response and phase-2 leaves the row in
     "submitting" with no batch_id. Reconciliation (below) is what makes
     that recoverable instead of duplicate-submit fuel.

  2. Deterministic custom_id (`email_queue:{row.id}:{prompt_hash[:8]}`).
     Anthropic echoes custom_id on every result, so we can identify our
     work in a batch whose batch_id we failed to persist.

  3. Reconciliation before any resubmit.
     On startup and at the head of every submit cycle: for rows stuck in
     "submitting", scan Anthropic's recent ended batches and match by
     custom_id. If found, adopt the batch_id + ingest the result. If not
     found AND no batches are still in-progress, release the row back to
     "pending_submit" so the next cycle retries (with the same
     idempotency_key — the UNIQUE constraint still blocks concurrent
     duplicate submits).

  4. idempotency_key UNIQUE at the DB layer.
     A concurrent worker trying to claim the same row will fail the
     constraint on phase-1 commit, not after a wasted Anthropic call.

Prompt construction for each row is *not* handled here — it is the
responsibility of the AI generation layer tracked under Sarat's branch 91.
batch_worker calls the builder registered via `set_request_builder()`; if no
builder is registered, pending rows are left untouched.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import signal
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import anthropic_batch
import models
from anthropic_batch import AnthropicBatchError
from database import SessionLocal

logger = logging.getLogger(__name__)

# --- Tuning defaults (overridable via system_config) ---
DEFAULT_SUBMIT_INTERVAL = 60
DEFAULT_POLL_INTERVAL = 120
DEFAULT_RECONCILE_LOOKBACK_HOURS = 24
DEFAULT_MAX_BATCH_SIZE = 100
# A healthy Anthropic batch ends within 24h (documented SLA). 26h is the
# "something is wrong" threshold at which we stop trusting the batch and
# surface failure to the customer-visible retry path.
DEFAULT_STUCK_BATCH_THRESHOLD_HOURS = 26
# After this many consecutive polling errors on the same batch id, give up:
# mark the rows failed so the customer doesn't sit in limbo forever, log at
# ERROR, and let the fallback (synchronous Sonnet path, owned by #91) handle
# regeneration on the next cycle.
# Overridable via SystemConfig key `rag.batch_max_poll_failures` — ops can
# raise it when Anthropic is being flaky without a deploy.
DEFAULT_MAX_POLL_FAILURES_PER_BATCH = 5

# --- Status/stage constants ---
STAGE_PENDING_SUBMIT = "pending_submit"
STAGE_SUBMITTING = "submitting"
STAGE_SUBMITTED = "submitted"
STAGE_COMPLETED = "completed"
STAGE_FAILED = "failed"

# Anthropic processing_status classification. Note that "canceling" is a
# transient state that converts to "canceled" — we treat it as terminal
# failure anyway because no results will be produced once cancel is issued.
ANTHROPIC_STATE_SUCCESS = {"ended"}
ANTHROPIC_STATE_FAILURE = {"expired", "canceled", "canceling"}
ANTHROPIC_STATE_RUNNING = {"in_progress"}
# Kept for backwards compatibility (reconciliation still needs to identify
# any terminal state — both success and failure contribute ended batches).
ANTHROPIC_BATCH_ENDED_STATES = ANTHROPIC_STATE_SUCCESS | ANTHROPIC_STATE_FAILURE

# Consecutive poll-error counter, keyed by batch_id. In-memory; resets on
# worker restart, which is fine because restart re-runs reconciliation and
# surfaces any still-stuck rows via the age threshold.
_batch_poll_failures: Dict[str, int] = {}

# Row IDs where the FAILED-transition commit has already failed once. Prevents
# a log storm when the same stuck rows reappear on every poll cycle because
# their commits keep failing (DB pressure, constraint collision in the batch).
# Rows that commit successfully are discarded from the set; failed rows stay
# until the worker restarts or until the cap below is hit.
_stuck_rows_commit_failed: Set[int] = set()
# Hard cap on the dedup set so a pathological burst of stuck rows can't grow
# it without bound. If we ever hit the cap we log and reset rather than block
# new ids from being tracked.
_STUCK_ROWS_WARNED_CAP = 10_000

# --- Prompt-builder hook (registered by the AI generation layer) ---
RequestBuilder = Callable[[models.EmailQueue], Optional[Dict[str, Any]]]
_request_builder: Optional[RequestBuilder] = None


def set_request_builder(fn: Optional[RequestBuilder]) -> None:
    """Register the function that converts an EmailQueue row into an Anthropic
    per-request dict (`{"model": ..., "max_tokens": ..., "messages": [...]}`).

    Tests and Sarat's AI-generation wiring (branch 91) call this at startup.
    Returning None from the builder tells the worker to skip the row without
    marking it failed (e.g. prompt not ready yet)."""
    global _request_builder
    _request_builder = fn


# ---------------------------------------------------------------------------
# Deterministic keys
# ---------------------------------------------------------------------------

def compute_prompt_hash(prompt_body: str) -> str:
    return hashlib.sha256(prompt_body.encode("utf-8")).hexdigest()


def compute_idempotency_key(row_id: int, prompt_hash: str) -> str:
    material = f"{row_id}:{prompt_hash}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def compute_custom_id(row_id: int, prompt_hash: str) -> str:
    return f"email_queue:{row_id}:{prompt_hash[:8]}"


# ---------------------------------------------------------------------------
# Reconciliation
# ---------------------------------------------------------------------------

async def _collect_custom_id_map(
    lookback_hours: int,
) -> Tuple[Dict[str, Tuple[str, Dict[str, Any]]], bool]:
    """Scan Anthropic's recent batches and return {custom_id: (batch_id, result)}.

    Only ended batches contribute — in-progress batches don't expose their
    request manifest on GET, so we can't match against them yet. Returns
    (map, in_progress_seen) so callers can distinguish "definitively not
    there" from "still waiting to know".
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    custom_id_map: Dict[str, Tuple[str, Dict[str, Any]]] = {}
    in_progress_seen = False
    after_id: Optional[str] = None

    while True:
        try:
            page = await anthropic_batch.list_batches(limit=100, after_id=after_id)
        except AnthropicBatchError as e:
            logger.error("Reconciliation: list_batches failed: %s", e)
            return custom_id_map, True  # unknown state — treat as "still in flight"

        batches = page.get("data", []) or []
        if not batches:
            break

        for batch in batches:
            created_at_str = batch.get("created_at")
            if created_at_str:
                try:
                    created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
                except ValueError:
                    created_at = None
                if created_at and created_at < cutoff:
                    return custom_id_map, in_progress_seen

            state = batch.get("processing_status") or batch.get("status")
            if state not in ANTHROPIC_BATCH_ENDED_STATES:
                in_progress_seen = True
                continue

            results_url = batch.get("results_url")
            if not results_url:
                continue

            try:
                async for result in anthropic_batch.iterate_batch_results(results_url):
                    cid = result.get("custom_id")
                    if cid:
                        custom_id_map[cid] = (batch.get("id", ""), result)
            except AnthropicBatchError as e:
                logger.warning(
                    "Reconciliation: could not fetch results for batch %s: %s",
                    batch.get("id"), e,
                )
                continue

        if not page.get("has_more"):
            break
        after_id = page.get("last_id")
        if not after_id:
            break

    return custom_id_map, in_progress_seen


async def reconcile_submitting_rows(db: Session, lookback_hours: int) -> Dict[str, int]:
    """Resolve every row stuck in batch_stage="submitting".

    Called on worker startup AND at the head of every submit cycle. Must run
    to completion before submit_pending_batches touches any row, otherwise
    a crash-then-restart can issue a second submit before we notice the first.
    """
    rows = (
        db.query(models.EmailQueue)
        .filter(models.EmailQueue.batch_stage == STAGE_SUBMITTING)
        .all()
    )
    if not rows:
        return {"reconciled": 0, "released": 0, "still_pending": 0}

    logger.info("Reconciling %d rows stuck in 'submitting'", len(rows))
    custom_id_map, in_progress_seen = await _collect_custom_id_map(lookback_hours)

    reconciled = 0
    released = 0
    still_pending = 0

    for row in rows:
        hit = custom_id_map.get(row.custom_id or "")
        if hit:
            batch_id, result = hit
            row.batch_id = batch_id
            row.batch_stage = STAGE_COMPLETED
            row.batch_status = "ended"
            _apply_batch_result_to_row(row, result)
            reconciled += 1
            continue

        if in_progress_seen:
            still_pending += 1
            continue

        # No evidence Anthropic ever saw this row — safe to release for retry.
        # The same idempotency_key is preserved; a concurrent worker that tried
        # to claim this row while we were reconciling would have hit the UNIQUE
        # constraint and backed off.
        row.batch_stage = STAGE_PENDING_SUBMIT
        released += 1

    db.commit()
    logger.info(
        "Reconcile done: %d adopted, %d released for retry, %d awaiting in-flight batches",
        reconciled, released, still_pending,
    )
    return {"reconciled": reconciled, "released": released, "still_pending": still_pending}


# ---------------------------------------------------------------------------
# Submit (two-phase write)
# ---------------------------------------------------------------------------

def _select_pending_rows(db: Session, limit: int) -> List[models.EmailQueue]:
    return (
        db.query(models.EmailQueue)
        .filter(models.EmailQueue.batch_stage == STAGE_PENDING_SUBMIT)
        .order_by(models.EmailQueue.id.asc())
        .limit(limit)
        .all()
    )


def _prepare_row_for_submit(
    row: models.EmailQueue,
    builder: RequestBuilder,
) -> Optional[Dict[str, Any]]:
    """Compute deterministic keys and the per-request body for one row.

    Returns the Anthropic request dict (with custom_id injected) or None if
    the builder declined to produce one."""
    request = builder(row)
    if request is None:
        return None

    # prompt_hash is stable across restarts, so idempotency_key is too.
    prompt_body = _canonical_prompt_body(request)
    prompt_hash = compute_prompt_hash(prompt_body)
    idem = compute_idempotency_key(row.id, prompt_hash)
    cid = compute_custom_id(row.id, prompt_hash)

    row.prompt_hash = prompt_hash
    row.idempotency_key = idem
    row.custom_id = cid
    row.batch_request_payload = request

    request_with_id = dict(request)
    request_with_id["custom_id"] = cid
    return request_with_id


def _normalize_for_hash(obj: Any) -> Any:
    """Recursively normalize a request body so ``_canonical_prompt_body`` is
    stable across Python versions and platforms.

    CPython's default ``float.__repr__`` has changed before (3.1's shortest-
    round-trip algorithm was the last big shift, but subnormals and edge
    values have wobbled since). Floats also expose NaN / Infinity, which
    ``json.dumps`` emits as invalid JSON literals by default. Rather than
    trust the serializer's float formatting, we convert every float to a
    fixed-format decimal string here — the canonical JSON then carries a
    string, which is lexically stable no matter how Python prints floats.
    """
    import math

    if isinstance(obj, bool):
        # bool is a subclass of int in Python — keep this branch above the
        # int one so ``True`` does not get coerced to ``1`` in the hash.
        return obj
    if isinstance(obj, float):
        if not math.isfinite(obj):
            raise ValueError(f"non-finite float in prompt body: {obj!r}")
        # 17 significant digits is enough to uniquely identify every IEEE-754
        # double — same precision CPython uses internally for round-trip.
        return format(obj, ".17g")
    if isinstance(obj, dict):
        # Coerce keys to strings so int-keyed dicts (JSON doesn't support
        # those) hash the same as their string-keyed equivalent.
        return {str(k): _normalize_for_hash(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_normalize_for_hash(v) for v in obj]
    return obj


def _canonical_prompt_body(request: Dict[str, Any]) -> str:
    """Stable serialization used to hash the prompt. We only need
    determinism, not human-readability.

    Floats are canonicalised via ``_normalize_for_hash`` so a Python minor-
    version upgrade cannot shift the idempotency key under us. NaN / Inf in
    the request raise loudly (they would serialize as invalid JSON anyway).
    """
    import json
    normalized = _normalize_for_hash(request)
    return json.dumps(
        normalized,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
        ensure_ascii=True,
    )


async def submit_pending_batches(
    db: Session,
    max_batch_size: int = DEFAULT_MAX_BATCH_SIZE,
) -> Dict[str, int]:
    """Claim pending rows and submit them as ONE batch per call.

    Phase 1 commit claims all selected rows atomically. If a concurrent worker
    has already claimed any of them, the UNIQUE(idempotency_key) constraint
    raises IntegrityError — we roll back and yield the cycle.
    """
    if _request_builder is None:
        logger.debug("No request builder registered; skipping submit cycle")
        return {"submitted": 0, "skipped": 0, "failed": 0}

    rows = _select_pending_rows(db, max_batch_size)
    if not rows:
        return {"submitted": 0, "skipped": 0, "failed": 0}

    # --- Phase 1: prepare + mark submitting + commit ---
    requests: List[Dict[str, Any]] = []
    claimed: List[models.EmailQueue] = []
    skipped = 0

    for row in rows:
        try:
            req = _prepare_row_for_submit(row, _request_builder)
        except Exception as e:
            logger.error("Row %s: request builder raised, marking failed: %s", row.id, e)
            row.batch_stage = STAGE_FAILED
            continue
        if req is None:
            skipped += 1
            continue
        row.batch_stage = STAGE_SUBMITTING
        requests.append(req)
        claimed.append(row)

    if not claimed:
        db.commit()  # persist any FAILED / stage resets
        return {"submitted": 0, "skipped": skipped, "failed": 0}

    try:
        db.commit()
    except IntegrityError as e:
        # Concurrent worker already claimed one of these rows — our entire
        # claim must roll back cleanly. No Anthropic call has happened yet.
        db.rollback()
        logger.warning("Phase-1 commit hit UNIQUE collision, yielding cycle: %s", e)
        return {"submitted": 0, "skipped": skipped, "failed": 0, "conflict": True}

    # --- Network: durable submit ---
    try:
        resp = await anthropic_batch.create_batch(requests)
    except Exception as e:
        # Anthropic call failed. Release the rows so the next cycle retries.
        # idempotency_key stays the same, so re-submit is still idempotent.
        logger.error("Anthropic create_batch failed: %s", e)
        for row in claimed:
            db.refresh(row)
            row.batch_stage = STAGE_PENDING_SUBMIT
        db.commit()
        return {"submitted": 0, "skipped": skipped, "failed": len(claimed)}

    batch_id = resp.get("id")
    if not batch_id:
        logger.error("Anthropic response missing batch id: %r", resp)
        for row in claimed:
            db.refresh(row)
            row.batch_stage = STAGE_PENDING_SUBMIT
        db.commit()
        return {"submitted": 0, "skipped": skipped, "failed": len(claimed)}

    # --- Phase 2: record batch_id + flip to submitted ---
    now = datetime.now(timezone.utc)
    for row in claimed:
        row.batch_id = batch_id
        row.batch_stage = STAGE_SUBMITTED
        row.batch_status = resp.get("processing_status") or "in_progress"
        row.batch_submitted_at = now
    db.commit()

    logger.info("Submitted batch %s with %d rows", batch_id, len(claimed))
    return {"submitted": len(claimed), "skipped": skipped, "failed": 0, "batch_id": batch_id}


# ---------------------------------------------------------------------------
# Poll submitted batches for completion
# ---------------------------------------------------------------------------

async def poll_submitted_batches(
    db: Session,
    stuck_threshold_hours: int = DEFAULT_STUCK_BATCH_THRESHOLD_HOURS,
) -> Dict[str, int]:
    """Poll each submitted batch and drive its rows to a terminal state.

    Handles four cases per batch:
      1. Terminal success (processing_status=="ended") — fetch results and
         ingest them into rows, flipping batch_stage to "completed".
      2. Terminal failure (expired / canceled / canceling) — fail the rows
         fast with a clear error_message so the customer-visible retry
         pipeline can pick them up on the next tick. Without this, rows
         submitted to an expired batch sit in "submitted" forever.
      3. Still running (in_progress, or any state we don't recognize) —
         leave the rows alone and count as still_running.
      4. HTTP error from Anthropic — increment the per-batch failure
         counter; after `rag.batch_max_poll_failures` consecutive errors,
         treat the batch as lost and fail its rows.

    Separately, before checking the batch state, any row whose
    batch_submitted_at is older than stuck_threshold_hours is failed out —
    this catches cases where the batch id itself became unreachable or the
    batch silently died on Anthropic's side.
    """
    # --- Stuck-batch failsafe: rows past the max-age threshold are failed
    #     BEFORE we talk to Anthropic, so a dead batch id that can't even
    #     be polled still gets surfaced. ---
    stuck = _fail_stuck_rows(db, stuck_threshold_hours)

    submitted = (
        db.query(models.EmailQueue.batch_id)
        .filter(models.EmailQueue.batch_stage == STAGE_SUBMITTED)
        .filter(models.EmailQueue.batch_id.isnot(None))
        .distinct()
        .all()
    )
    batch_ids = [r[0] for r in submitted]
    if not batch_ids:
        return {
            "completed": 0, "still_running": 0,
            "failed_terminal": 0, "failed_stuck": stuck, "failed_poll_errors": 0,
        }

    completed = 0
    still_running = 0
    failed_terminal = 0
    failed_poll_errors = 0

    max_poll_failures = _read_int_config(
        "rag.batch_max_poll_failures", DEFAULT_MAX_POLL_FAILURES_PER_BATCH
    )

    for batch_id in batch_ids:
        try:
            batch = await anthropic_batch.get_batch(batch_id)
        except AnthropicBatchError as e:
            count = _batch_poll_failures.get(batch_id, 0) + 1
            _batch_poll_failures[batch_id] = count
            if count >= max_poll_failures:
                logger.error(
                    "Poll: batch %s has failed %d consecutive times (%s) — "
                    "marking rows failed so sync fallback can regenerate",
                    batch_id, count, e,
                )
                failed_poll_errors += _fail_rows_for_batch(
                    db, batch_id,
                    reason=f"Anthropic poll failed {count} times: {e}",
                )
                _batch_poll_failures.pop(batch_id, None)
            else:
                logger.warning(
                    "Poll: get_batch(%s) failed (%d/%d): %s",
                    batch_id, count, max_poll_failures, e,
                )
            continue

        # Successful HTTP call — reset the per-batch failure counter.
        _batch_poll_failures.pop(batch_id, None)

        state = batch.get("processing_status") or batch.get("status") or "unknown"

        if state in ANTHROPIC_STATE_FAILURE:
            logger.error(
                "Poll: batch %s reached terminal failure state '%s' — "
                "failing rows so the retry path can regenerate",
                batch_id, state,
            )
            failed_terminal += _fail_rows_for_batch(
                db, batch_id,
                reason=f"Anthropic batch {state}",
                batch_status=state,
            )
            continue

        if state not in ANTHROPIC_STATE_SUCCESS:
            # in_progress OR any state we don't recognize — be conservative
            # and leave rows alone; the stuck-batch failsafe above is the
            # safety net if this persists.
            still_running += 1
            continue

        results_url = batch.get("results_url")
        if not results_url:
            logger.warning("Batch %s ended but has no results_url", batch_id)
            continue

        try:
            async for result in anthropic_batch.iterate_batch_results(results_url):
                cid = result.get("custom_id")
                if not cid:
                    continue
                row = (
                    db.query(models.EmailQueue)
                    .filter(models.EmailQueue.custom_id == cid)
                    .first()
                )
                if row is None:
                    logger.warning("No row matches custom_id %s from batch %s", cid, batch_id)
                    continue
                _apply_batch_result_to_row(row, result)
            db.commit()
            completed += 1
        except AnthropicBatchError as e:
            logger.error("Poll: streaming results for %s failed: %s", batch_id, e)
            db.rollback()

    return {
        "completed": completed,
        "still_running": still_running,
        "failed_terminal": failed_terminal,
        "failed_stuck": stuck,
        "failed_poll_errors": failed_poll_errors,
    }


def _fail_rows_for_batch(
    db: Session,
    batch_id: str,
    reason: str,
    batch_status: Optional[str] = None,
) -> int:
    """Mark every row attached to `batch_id` as failed with a clear message.

    Sets batch_stage=failed, status=failed, error_message=reason so the
    existing retry path (which looks at status="failed") can pick them up.
    Returns the number of rows transitioned. Commits.
    """
    rows = (
        db.query(models.EmailQueue)
        .filter(models.EmailQueue.batch_id == batch_id)
        .filter(models.EmailQueue.batch_stage == STAGE_SUBMITTED)
        .all()
    )
    for row in rows:
        row.batch_stage = STAGE_FAILED
        if batch_status:
            row.batch_status = batch_status
        row.status = "failed"
        row.error_message = reason
    if rows:
        db.commit()
    return len(rows)


def _fail_stuck_rows(db: Session, threshold_hours: int) -> int:
    """Fail out rows that have been in `submitted` longer than the threshold.

    This is the last-line-of-defense for cases where Anthropic's batch
    simply stopped responding or the batch id became invalid. Without this,
    rows silently sit forever and customers see "AI emails stopped sending".

    Each row's FAILED transition is committed independently so a bad row
    can't block the rest, and the ERROR log for each stuck row fires exactly
    once per process lifetime — subsequent poll cycles that re-encounter the
    same row (because its commit failed earlier) stay silent to avoid a log
    storm proportional to stuck_rows * poll_frequency. A single INFO summary
    line at end-of-cycle gives operators the counters they need.
    """
    if threshold_hours <= 0:
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(hours=threshold_hours)
    stuck = (
        db.query(models.EmailQueue)
        .filter(models.EmailQueue.batch_stage == STAGE_SUBMITTED)
        .filter(models.EmailQueue.batch_submitted_at.isnot(None))
        .filter(models.EmailQueue.batch_submitted_at < cutoff)
        .all()
    )
    if not stuck:
        return 0

    # If the dedup set has grown past the cap, reset it rather than block new
    # ids — losing some dedup state is strictly better than leaking memory.
    if len(_stuck_rows_commit_failed) >= _STUCK_ROWS_WARNED_CAP:
        logger.warning(
            "Resetting _stuck_rows_commit_failed dedup set (size=%d hit cap=%d)",
            len(_stuck_rows_commit_failed),
            _STUCK_ROWS_WARNED_CAP,
        )
        _stuck_rows_commit_failed.clear()

    marked = 0
    skipped_already_warned = 0
    commit_errors = 0
    for row in stuck:
        first_encounter = row.id not in _stuck_rows_commit_failed
        if first_encounter:
            logger.error(
                "Batch %s row %s exceeded stuck threshold (submitted %s) — failing",
                row.batch_id, row.id, row.batch_submitted_at,
            )
        else:
            skipped_already_warned += 1

        row.batch_stage = STAGE_FAILED
        row.batch_status = row.batch_status or "stuck"
        row.status = "failed"
        row.error_message = (
            f"Batch did not complete within {threshold_hours}h "
            f"(submitted at {row.batch_submitted_at})"
        )
        try:
            db.commit()
            _stuck_rows_commit_failed.discard(row.id)
            marked += 1
        except Exception as e:
            commit_errors += 1
            if first_encounter:
                logger.warning(
                    "Failed to commit stuck-row FAILED transition for row %s: %s",
                    row.id, e,
                )
            try:
                db.rollback()
            except Exception:
                pass
            _stuck_rows_commit_failed.add(row.id)

    logger.info(
        "fail_stuck_rows: marked %d rows as failed, skipped %d already-warned, "
        "%d commit errors",
        marked, skipped_already_warned, commit_errors,
    )
    return marked


def _apply_batch_result_to_row(row: models.EmailQueue, result: Dict[str, Any]) -> None:
    """Translate an Anthropic result record into the row's terminal state.

    Only responsibility is advancing the state machine:
      - succeeded → batch_stage=completed, status=pending (ready for SMTP)
      - any error → batch_stage=failed, error_message populated

    The AI-generation layer owns parsing the actual message content into
    subject/body — hook here when #91 lands the real ingestion path."""
    result_type = (result.get("result") or {}).get("type") or result.get("type")
    if result_type in ("succeeded", "message"):
        row.batch_stage = STAGE_COMPLETED
        row.batch_status = "ended"
        if row.status == "pending" or row.status is None:
            row.status = "pending"
        return

    row.batch_stage = STAGE_FAILED
    row.batch_status = "ended"
    err = (result.get("result") or {}).get("error") or {}
    row.error_message = f"Batch result error: {err.get('message') or err.get('type') or 'unknown'}"
    row.status = "failed"


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def _read_int_config(key: str, default: int) -> int:
    db = SessionLocal()
    try:
        from system_config import get_config_int
        return get_config_int(key, db, default=default)
    except Exception:
        return default
    finally:
        db.close()


async def run_one_cycle() -> Dict[str, Any]:
    """Single iteration of the worker loop. Exposed for tests."""
    lookback = _read_int_config(
        "rag.batch_reconcile_lookback_hours", DEFAULT_RECONCILE_LOOKBACK_HOURS
    )
    max_batch = _read_int_config(
        "rag.batch_max_batch_size", DEFAULT_MAX_BATCH_SIZE
    )

    db = SessionLocal()
    try:
        recon = await reconcile_submitting_rows(db, lookback)
    finally:
        db.close()

    db = SessionLocal()
    try:
        submit = await submit_pending_batches(db, max_batch)
    finally:
        db.close()

    stuck_threshold = _read_int_config(
        "rag.batch_stuck_threshold_hours", DEFAULT_STUCK_BATCH_THRESHOLD_HOURS
    )
    db = SessionLocal()
    try:
        poll = await poll_submitted_batches(db, stuck_threshold_hours=stuck_threshold)
    finally:
        db.close()

    return {"reconcile": recon, "submit": submit, "poll": poll}


async def batch_worker_loop() -> None:
    logger.info("Batch worker started")
    submit_interval = _read_int_config(
        "rag.batch_submit_interval_seconds", DEFAULT_SUBMIT_INTERVAL
    )

    stop_event = asyncio.Event()

    def _handle_signal(*_: Any) -> None:
        stop_event.set()

    # Inside a coroutine, get_running_loop() is preferred over get_event_loop():
    # 3.12 emits a DeprecationWarning when get_event_loop() is called without a
    # current loop, and 3.14 is slated to drop that fallback entirely.
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _handle_signal)
        except NotImplementedError:
            # Windows asyncio loop doesn't support add_signal_handler.
            pass

    while not stop_event.is_set():
        try:
            await run_one_cycle()
        except Exception as e:
            logger.error("Batch worker cycle raised: %s", e, exc_info=True)

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=submit_interval)
        except asyncio.TimeoutError:
            continue

    logger.info("Batch worker stopped")


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    try:
        asyncio.run(batch_worker_loop())
    except KeyboardInterrupt:
        logger.info("Batch worker interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error("Fatal error in batch worker: %s", e, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
