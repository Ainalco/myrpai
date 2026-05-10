"""Regression tests for the execute_email ↔ store_generated_email transaction
boundary (tracked as H2 / #142).

Before the H2 fix, ``store_generated_email`` accepted the caller's SQLAlchemy
session and called ``db.commit()`` mid-flow — committing any uncommitted
execute_email mutations as a side effect. The fix isolates the embedding
write into a dedicated SessionLocal() so the caller's transaction atomicity
is preserved.

These tests lock the contract against a silent regression:

  * store_generated_email must open its own session, not accept one from the
    caller.
  * A failure inside the embedding path must leave the caller's transaction
    untouched (no implicit commit of caller state).
  * execute_email's post-queue RAG block must (a) commit used_chunk_ids on
    the caller's session BEFORE touching store_generated_email, and
    (b) wrap the embedding call in try/except so an embedding failure never
    flips the overall execute_email status.
"""
from __future__ import annotations

import asyncio
import inspect
from unittest.mock import MagicMock, patch

import pytest

import rag_service
from rag_service import store_generated_email


def test_store_generated_email_does_not_accept_caller_db():
    """Signature guard — the H2 regression would bring back a `db=` kwarg so
    callers can pass their own session. The isolated-session fix makes that
    impossible by construction."""
    sig = inspect.signature(store_generated_email)
    assert "db" not in sig.parameters, (
        "store_generated_email regained a `db` kwarg — callers can pass "
        "their own session again, re-introducing the H2 transaction-boundary "
        "bug. Keep the function owning its own SessionLocal()."
    )


def test_store_generated_email_opens_and_closes_own_session(monkeypatch):
    """Behavioural check: every invocation allocates SessionLocal() exactly
    once and closes it on exit, regardless of success or failure upstream."""
    opened = MagicMock(name="owned-session")
    monkeypatch.setattr(rag_service, "SessionLocal", MagicMock(return_value=opened))

    async def _fake_store_embeddings(**kwargs):
        return 1

    monkeypatch.setattr(rag_service, "store_embeddings", _fake_store_embeddings)

    asyncio.run(
        store_generated_email(
            account_id=1,
            email_queue_id=42,
            subject="hi",
            body="hello there",
        )
    )

    rag_service.SessionLocal.assert_called_once()
    opened.close.assert_called_once()
    opened.rollback.assert_not_called()


def test_store_generated_email_rolls_back_and_reraises_on_failure(monkeypatch):
    """If store_embeddings raises, the owned session must rollback and the
    exception must propagate — swallowing would hide real data loss."""
    opened = MagicMock(name="owned-session")
    monkeypatch.setattr(rag_service, "SessionLocal", MagicMock(return_value=opened))

    async def _failing(**kwargs):
        raise RuntimeError("embedding failed")

    monkeypatch.setattr(rag_service, "store_embeddings", _failing)

    with pytest.raises(RuntimeError, match="embedding failed"):
        asyncio.run(
            store_generated_email(
                account_id=1,
                email_queue_id=42,
                subject="hi",
                body="hello",
            )
        )

    opened.rollback.assert_called_once()
    opened.close.assert_called_once()


def test_store_generated_email_short_circuits_on_empty_content(monkeypatch):
    """Empty subject + body must not open a session at all — the helper
    returns 0 immediately. Protects against throwing a pointless connection
    at the pool during edge cases."""
    monkeypatch.setattr(rag_service, "SessionLocal", MagicMock())

    result = asyncio.run(
        store_generated_email(
            account_id=1,
            email_queue_id=42,
            subject="",
            body="",
        )
    )

    assert result == 0
    rag_service.SessionLocal.assert_not_called()


def test_execute_email_commits_used_chunk_ids_before_embedding():
    """Source-code guard for the ordering contract in execute_email:

    The used_chunk_ids assignment + db.commit() must happen BEFORE the
    store_generated_email call, so a failure during the embedding step does
    not roll back the chunk-id audit trail. The RAG block must also be
    wrapped in try/except so an embedding failure is logged rather than
    surfaced as an execute_email error."""
    import executions

    src = inspect.getsource(executions.ComponentExecutor.execute_email)

    # Commit of used_chunk_ids on the caller's session must precede the RAG
    # import / call. A refactor that reorders these would mean a
    # store_generated_email failure rolls back used_chunk_ids too.
    commit_idx = src.find("_eq.used_chunk_ids")
    rag_import_idx = src.find("from rag_service import store_generated_email")
    rag_call_idx = src.find("await store_generated_email")
    assert commit_idx != -1 and rag_import_idx != -1 and rag_call_idx != -1, (
        "post-queue RAG block structure has changed — update this test"
    )
    assert commit_idx < rag_import_idx < rag_call_idx, (
        "used_chunk_ids must be committed before store_generated_email runs"
    )

    # The RAG block's outermost try/except must catch Exception and log,
    # not re-raise — otherwise an embedding failure marks the whole
    # execute_email as failed.
    rag_try_except_signature = "except Exception as _rag_err"
    assert rag_try_except_signature in src, (
        "execute_email's post-queue RAG block no longer swallows embedding "
        "failures — an OpenAI outage would now fail the email component."
    )
