"""Unit-level coverage for backfill_rag_embeddings.py.

This script was 279 lines with zero tests — any regression silently produced
wrong data. The ask in #168 is broad coverage for the pieces that affect
correctness: tenant + contact resolution, happy path, idempotency, dry-run,
and partial-failure isolation.

Full end-to-end integration would need Postgres with pgvector loaded because
ContentEmbedding carries a vector() column. These tests stay at unit level
by mocking the embedding-write seam and driving the helpers directly.
"""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

import backfill_rag_embeddings
from backfill_rag_embeddings import (
    _email_candidates,
    _resolve_contact_and_org,
    _resolve_tenant,
    _text_gen_candidates,
    backfill_emails,
    backfill_text_gen,
)


# ---------------------------------------------------------------------------
# Tenant resolution (_resolve_tenant)
# ---------------------------------------------------------------------------

def _make_db_for_tenant(workflow=None, user=None, account=None):
    """Shape a MagicMock Session that answers the three queries _resolve_tenant
    makes, by dispatching on the model class passed to db.query()."""
    import models

    db = MagicMock()
    first_map = {}
    if workflow is not None:
        first_map[models.Workflow] = workflow
    if user is not None:
        first_map[models.User] = user
    if account is not None:
        first_map[models.Account] = account

    def _query(model):
        q = MagicMock()
        q.filter.return_value.first.return_value = first_map.get(model)
        return q

    db.query.side_effect = _query
    return db


def test_resolve_tenant_none_when_workflow_missing():
    db = _make_db_for_tenant(workflow=None)
    assert asyncio.run(_resolve_tenant(db, workflow_id=1)) == (None, None)


def test_resolve_tenant_none_when_workflow_id_is_none():
    db = MagicMock()
    assert asyncio.run(_resolve_tenant(db, workflow_id=None)) == (None, None)
    # No DB hit when workflow_id is None.
    db.query.assert_not_called()


def test_resolve_tenant_returns_owner_when_account_missing():
    """Workflow has an owner but their org has no account row — must still
    return the owner so the contact-scope lookup downstream works."""
    wf = MagicMock(owner_id=7)
    user = MagicMock(org_id="org-xyz")
    db = _make_db_for_tenant(workflow=wf, user=user, account=None)

    assert asyncio.run(_resolve_tenant(db, workflow_id=1)) == (None, 7)


def test_resolve_tenant_full_path():
    wf = MagicMock(owner_id=7)
    user = MagicMock(org_id="org-xyz")
    acct = MagicMock(id=42)
    db = _make_db_for_tenant(workflow=wf, user=user, account=acct)

    assert asyncio.run(_resolve_tenant(db, workflow_id=1)) == (42, 7)


# ---------------------------------------------------------------------------
# Contact + org resolution (_resolve_contact_and_org)
#
# H11 / #149 — this helper used to resolve Contact.email globally, which
# cross-linked another tenant's contact when two accounts shared an email.
# ---------------------------------------------------------------------------

def test_resolve_contact_and_org_requires_user_id():
    """No user_id → refuse to resolve rather than risk cross-tenant match."""
    db = MagicMock()
    assert asyncio.run(
        _resolve_contact_and_org(db, [{"email": "a@b.com"}], user_id=None)
    ) == (None, None)
    db.query.assert_not_called()


def test_resolve_contact_and_org_scopes_by_user_id():
    """The contact query must carry a user_id filter so we only match the
    workflow owner's contacts — H11's cross-tenant leak guard."""
    db = MagicMock()
    contact = MagicMock(id=101, contact_organization_id=55)
    filter_chain = db.query.return_value.filter.return_value
    filter_chain.first.return_value = contact

    result = asyncio.run(
        _resolve_contact_and_org(
            db,
            [{"email": "alice@acme.com"}],
            user_id=9,
        )
    )

    assert result == (101, 55)
    # The filter call must receive both email and user_id constraints — a
    # regression that dropped user_id would pass only the email filter.
    filter_args = db.query.return_value.filter.call_args.args
    assert len(filter_args) == 2, (
        "Contact lookup must filter by BOTH email and user_id — "
        f"got {len(filter_args)} filter args"
    )


def test_resolve_contact_and_org_skips_participants_without_email():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None

    assert asyncio.run(
        _resolve_contact_and_org(
            db,
            [{"name": "no-email"}, "string-not-a-dict", {"email": "x@y.com"}],
            user_id=1,
        )
    ) == (None, None)


# ---------------------------------------------------------------------------
# Email backfill happy path + partial failure isolation
#
# backfill_emails fans out one SessionLocal per row on purpose so a single
# row's embedding failure can't poison the session shared with subsequent
# rows. These tests lock that invariant.
# ---------------------------------------------------------------------------

def _fake_session_factory(rows_by_id, resolve_tenant_result=(42, 7)):
    """Build a stand-in for SessionLocal() that yields fresh MagicMock
    sessions, each answering EmailQueue lookups from rows_by_id."""
    import models

    def _make():
        db = MagicMock()

        def _query(model):
            q = MagicMock()
            if model is models.EmailQueue:
                q.filter.return_value.first.side_effect = lambda: rows_by_id.get(
                    _query.last_requested_id
                )
            elif model is models.Contact:
                q.filter.return_value.first.return_value = MagicMock(
                    contact_organization_id=None
                )
            else:
                q.filter.return_value.first.return_value = None
            return q

        _query.last_requested_id = None
        # We can't easily peek at the filter args, so instead expose a
        # helper on the session.
        db.query.side_effect = _query

        orig_query = db.query

        # ... emulate per-id lookups differently: patch at _filter level.
        def _smart_query(model):
            q = MagicMock()
            if model is models.EmailQueue:
                def _filter(cond):
                    # The caller writes EmailQueue.id == eq_id, so introspect
                    # the right-hand value from the compiled comparison.
                    try:
                        eq_id = cond.right.value
                    except AttributeError:
                        eq_id = None
                    inner = MagicMock()
                    inner.first.return_value = rows_by_id.get(eq_id)
                    return inner
                q.filter.side_effect = _filter
            elif model is models.Contact:
                q.filter.return_value.first.return_value = None
            else:
                q.filter.return_value.first.return_value = None
            return q

        db.query.side_effect = _smart_query
        return db

    return _make


def test_backfill_emails_happy_path(monkeypatch):
    """10 candidate rows, all succeed → ok=10, fail=0, skipped=0, and
    store_generated_email is called once per row with the right kwargs."""
    email_rows = {
        i: MagicMock(
            id=i, contact_id=None, sequence_run_id=None,
            workflow_id=1, subject=f"subj-{i}", body=f"body-{i}",
        )
        for i in range(1, 11)
    }

    monkeypatch.setattr(
        backfill_rag_embeddings,
        "_email_candidates",
        lambda db, limit: list(email_rows.keys()),
    )
    monkeypatch.setattr(
        backfill_rag_embeddings,
        "SessionLocal",
        _fake_session_factory(email_rows),
    )

    async def _fake_resolve(db, workflow_id):
        return (42, 7)

    monkeypatch.setattr(backfill_rag_embeddings, "_resolve_tenant", _fake_resolve)

    calls = []

    async def _fake_store(**kwargs):
        calls.append(kwargs)
        return 1

    monkeypatch.setattr(backfill_rag_embeddings, "store_generated_email", _fake_store)

    ok, fail, skipped = asyncio.run(backfill_emails(limit=None, dry_run=False))

    assert (ok, fail, skipped) == (10, 0, 0)
    assert len(calls) == 10
    # Verify the first call carries the expected fields.
    first = calls[0]
    assert first["email_queue_id"] == 1
    assert first["account_id"] == 42
    assert first["subject"] == "subj-1"


def test_backfill_emails_partial_failure_does_not_stop_the_rest(monkeypatch):
    """Row 5's embedding raises. Rows 1-4 and 6-10 must still process — the
    per-row session structure is the whole point of the H5 fix."""
    email_rows = {
        i: MagicMock(
            id=i, contact_id=None, sequence_run_id=None,
            workflow_id=1, subject=f"s{i}", body=f"b{i}",
        )
        for i in range(1, 11)
    }

    monkeypatch.setattr(
        backfill_rag_embeddings,
        "_email_candidates",
        lambda db, limit: list(email_rows.keys()),
    )
    monkeypatch.setattr(
        backfill_rag_embeddings,
        "SessionLocal",
        _fake_session_factory(email_rows),
    )

    async def _fake_resolve(db, workflow_id):
        return (42, 7)

    monkeypatch.setattr(backfill_rag_embeddings, "_resolve_tenant", _fake_resolve)

    async def _fake_store(**kwargs):
        if kwargs["email_queue_id"] == 5:
            raise RuntimeError("OpenAI 500")
        return 1

    monkeypatch.setattr(backfill_rag_embeddings, "store_generated_email", _fake_store)

    ok, fail, skipped = asyncio.run(backfill_emails(limit=None, dry_run=False))

    # 9 rows succeeded, 1 failed. No rows were stranded after the bad one.
    assert ok == 9
    assert fail == 1
    assert skipped == 0


def test_backfill_emails_dry_run_does_not_touch_store(monkeypatch):
    """--dry-run must count candidates without calling the embedding layer
    (and without opening per-row sessions)."""
    email_ids = list(range(1, 4))
    monkeypatch.setattr(
        backfill_rag_embeddings,
        "_email_candidates",
        lambda db, limit: email_ids,
    )
    # SessionLocal() is still called once for phase 1 (candidate scan); we
    # don't assert it was untouched, only that the store path wasn't reached.

    called = {"store": 0, "resolve_tenant": 0}

    async def _fake_store(**kwargs):
        called["store"] += 1

    async def _fake_resolve(db, workflow_id):
        called["resolve_tenant"] += 1
        return (42, 7)

    monkeypatch.setattr(backfill_rag_embeddings, "store_generated_email", _fake_store)
    monkeypatch.setattr(backfill_rag_embeddings, "_resolve_tenant", _fake_resolve)
    monkeypatch.setattr(
        backfill_rag_embeddings,
        "SessionLocal",
        _fake_session_factory({}),
    )

    ok, fail, skipped = asyncio.run(backfill_emails(limit=None, dry_run=True))

    assert (ok, fail, skipped) == (3, 0, 0)
    assert called["store"] == 0
    assert called["resolve_tenant"] == 0


def test_backfill_emails_idempotent_when_candidates_empty(monkeypatch):
    """Re-running on a fully backfilled DB is the common support scenario —
    it must count 0 work and never call the embedding layer."""
    monkeypatch.setattr(
        backfill_rag_embeddings,
        "_email_candidates",
        lambda db, limit: [],
    )
    monkeypatch.setattr(
        backfill_rag_embeddings,
        "SessionLocal",
        _fake_session_factory({}),
    )

    async def _must_not_run(**kwargs):
        raise AssertionError("store_generated_email called on empty candidate list")

    monkeypatch.setattr(backfill_rag_embeddings, "store_generated_email", _must_not_run)

    assert asyncio.run(backfill_emails(limit=None, dry_run=False)) == (0, 0, 0)


# ---------------------------------------------------------------------------
# Text gen backfill — smaller smoke because most logic is same shape
# ---------------------------------------------------------------------------

def test_backfill_text_gen_skips_when_no_account_id(monkeypatch):
    """If _resolve_tenant cannot produce an account_id, the execution is
    counted as failed rather than silently writing NULL-account embeddings."""
    candidates = [(1, True, False)]  # one execution, needs text_gen only
    monkeypatch.setattr(
        backfill_rag_embeddings,
        "_text_gen_candidates",
        lambda db, limit: candidates,
    )

    execution = MagicMock(
        id=1, workflow_id=1, input_data={"transcript": "hello"},
        results={"extracted_information": {"k": "v"}},
    )
    import models

    def _session_factory():
        db = MagicMock()

        def _query(model):
            q = MagicMock()
            if model is models.Execution:
                q.filter.return_value.first.return_value = execution
            else:
                q.filter.return_value.first.return_value = None
            return q

        db.query.side_effect = _query
        return db

    monkeypatch.setattr(backfill_rag_embeddings, "SessionLocal", _session_factory)

    async def _no_account(db, workflow_id):
        return (None, None)

    monkeypatch.setattr(backfill_rag_embeddings, "_resolve_tenant", _no_account)

    store_calls = {"n": 0}

    async def _fake_store(**kwargs):
        store_calls["n"] += 1

    monkeypatch.setattr(backfill_rag_embeddings, "store_text_gen_output", _fake_store)
    monkeypatch.setattr(backfill_rag_embeddings, "store_transcript_chunks", _fake_store)

    ok, fail, skipped = asyncio.run(backfill_text_gen(limit=None, dry_run=False))

    # No account_id → counted as fail, embedding writer not called at all.
    assert fail == 1
    assert ok == 0
    assert store_calls["n"] == 0
