"""Unit tests for contacts_service._schedule_activity_embedding.

The sync-caller branch used to spawn an unbounded daemon thread per activity.
A Pipedrive bulk-stage-change burst of 200 activities would produce 200 live
threads, 200 DB connections, and 200 concurrent OpenAI requests — enough to
blow the pool and trip rate limits.

The fix routes sync-path submissions through a shared
ThreadPoolExecutor(max_workers=4) with a queue-depth cap that drops excess work
rather than letting the internal queue balloon.
"""
from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

import contacts_service


@pytest.fixture(autouse=True)
def reset_pool_state():
    """Module-level pool state leaks across tests otherwise. Tear down the
    executor between tests so each one starts from a clean slate."""
    yield
    pool = contacts_service._activity_embed_pool
    if pool is not None:
        pool.shutdown(wait=True, cancel_futures=True)
    contacts_service._activity_embed_pool = None
    contacts_service._activity_embed_queue_depth = 0


def _fake_db(account_id=1, org_id=2):
    """Stub Session.query(...).filter(...).first() so the pre-resolve block
    in _schedule_activity_embedding can read account_id / org_id without a
    real database."""
    contact = MagicMock(contact_organization_id=org_id)
    user = MagicMock(org_id="org-xyz")
    account = MagicMock(id=account_id)

    models = contacts_service.models
    first_map = {
        models.Contact: contact,
        models.User: user,
        models.Account: account,
    }

    def _query(model):
        q = MagicMock()
        q.filter.return_value.first.return_value = first_map.get(model)
        return q

    db = MagicMock()
    db.query.side_effect = _query
    return db


def _submit_one(activity_id: int, db=None, embed_side_effect=None):
    """Helper: call _schedule_activity_embedding once. embed_side_effect lets
    a test substitute the embedding coroutine so we can block threads on demand."""
    db = db or _fake_db()

    # Patch the three names looked up inside the function (they're imported
    # lazily to avoid a circular import with rag_service).
    with patch("rag_service.activity_source_type", return_value="activity"), \
         patch("rag_service.build_activity_summary", return_value="summary"), \
         patch(
             "rag_service.store_activity_summary",
             side_effect=embed_side_effect or _noop_store,
         ), \
         patch.object(contacts_service, "SessionLocal", return_value=MagicMock()):
        contacts_service._schedule_activity_embedding(
            db=db,
            user_id=1,
            contact_id=10,
            activity_id=activity_id,
            activity_type="email_sent",
            direction="outbound",
            subject="hi",
            summary="body",
            source_type=None,
            source_id=None,
            occurred_at=datetime.now(timezone.utc),
        )


async def _noop_store(**kwargs):
    return None


def test_sync_path_uses_bounded_pool():
    """After a sync-path submission, the module-level executor must exist and
    be capped at the documented worker count."""
    _submit_one(activity_id=1)

    pool = contacts_service._activity_embed_pool
    assert pool is not None
    assert pool._max_workers == contacts_service._ACTIVITY_EMBED_MAX_WORKERS

    pool.shutdown(wait=True)


def test_concurrent_submissions_respect_worker_cap():
    """Submit 20 activities whose embed task blocks until released. Observe
    how many threads the pool has active at the peak — it must never exceed
    _ACTIVITY_EMBED_MAX_WORKERS. Without the fix the count would track 1:1
    with submissions."""
    release = threading.Event()
    active_lock = threading.Lock()
    active_count = 0
    peak_active = 0

    async def _blocking_store(**kwargs):
        nonlocal active_count, peak_active
        with active_lock:
            active_count += 1
            peak_active = max(peak_active, active_count)
        # Hold the worker slot until the test releases.
        release.wait(timeout=5)
        with active_lock:
            active_count -= 1

    for i in range(20):
        _submit_one(activity_id=i, embed_side_effect=_blocking_store)

    # Let the first batch acquire their slots before we release.
    deadline = time.time() + 2
    while time.time() < deadline:
        with active_lock:
            if active_count >= contacts_service._ACTIVITY_EMBED_MAX_WORKERS:
                break
        time.sleep(0.01)

    release.set()
    contacts_service._activity_embed_pool.shutdown(wait=True)

    assert peak_active <= contacts_service._ACTIVITY_EMBED_MAX_WORKERS, (
        f"pool exceeded its cap: peak={peak_active} "
        f"max={contacts_service._ACTIVITY_EMBED_MAX_WORKERS}"
    )
    assert peak_active >= 1, "pool never ran any work"


def test_queue_cap_drops_excess_submissions(monkeypatch, caplog):
    """If the backlog exceeds _ACTIVITY_EMBED_MAX_QUEUED, further submissions
    must be dropped with a warning rather than queued. Otherwise a stuck pool
    (e.g. OpenAI outage) would grow RSS without bound."""
    import logging

    monkeypatch.setattr(contacts_service, "_ACTIVITY_EMBED_MAX_QUEUED", 3)

    # Pre-inflate the queue depth so the next submission sees a full backlog.
    contacts_service._activity_embed_queue_depth = 3

    with caplog.at_level(logging.WARNING, logger="contacts_service"):
        _submit_one(activity_id=999)

    dropped = [
        r for r in caplog.records
        if r.levelno == logging.WARNING
        and "Activity embedding pool saturated" in r.getMessage()
    ]
    assert len(dropped) == 1
    # Depth must not have been bumped for the dropped submission.
    assert contacts_service._activity_embed_queue_depth == 3

    # Reset so the autouse fixture can clean up.
    contacts_service._activity_embed_queue_depth = 0
