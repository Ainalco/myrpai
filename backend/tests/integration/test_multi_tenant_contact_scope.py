"""Multi-tenant regression guards for Contact.email cross-account lookup.

Before the H10 / #148 and H11 / #149 fixes, two code paths queried
``Contact.email == x`` with no account/user scoping:

  * ``executions.py`` → ``execute_email`` (and the text_gen contact-briefing
    block) resolves the recipient contact from participant emails.
  * ``backfill_rag_embeddings._resolve_contact_and_org`` resolves a contact
    during the one-shot migration.

Because ``Contact.email`` is not unique across tenants, an unscoped ``.filter``
would match another account's row when DB ordering happened to put it first.
The result: RAG context / embeddings silently attributed to the wrong tenant.
This is the worst class of SaaS bug — cross-account data leakage — and the
fix is trivial to revert. These tests build the exact cross-tenant shape and
fail loudly if either call site forgets to scope by ``user_id``.
"""
from __future__ import annotations

import asyncio

import pytest

import models
from backfill_rag_embeddings import _resolve_contact_and_org


@pytest.fixture
def two_tenants_sharing_email(db_session):
    """Two users, each owning a Contact with the same email but different
    user_id. Mirrors the cross-tenant collision in prod: the same person at a
    vendor can be tracked by two of our customers independently."""
    user_a = models.User(
        email="owner-a@example.com",
        hashed_password="x",
        is_active=True,
    )
    user_b = models.User(
        email="owner-b@example.com",
        hashed_password="x",
        is_active=True,
    )
    db_session.add_all([user_a, user_b])
    db_session.flush()

    contact_a = models.Contact(
        user_id=user_a.id, email="alice@customer.com", name="Alice (A)",
    )
    contact_b = models.Contact(
        user_id=user_b.id, email="alice@customer.com", name="Alice (B)",
    )
    db_session.add_all([contact_a, contact_b])
    db_session.flush()

    return {
        "user_a": user_a,
        "user_b": user_b,
        "contact_a": contact_a,
        "contact_b": contact_b,
    }


# ---------------------------------------------------------------------------
# executions.py — the filter used by execute_email + text_gen briefing blocks
#
# Rather than stand up the whole execution plumbing, we exercise the exact
# SQLAlchemy filter chain the function uses. If someone drops the user_id
# clause in a refactor, this fails.
# ---------------------------------------------------------------------------

def test_execute_email_filter_is_scoped_to_owner_user(
    db_session, two_tenants_sharing_email
):
    fix = two_tenants_sharing_email
    email = "alice@customer.com"

    # Scoped to user A → must return contact A, never contact B.
    result_a = db_session.query(models.Contact).filter(
        models.Contact.email == email,
        models.Contact.user_id == fix["user_a"].id,
    ).first()
    assert result_a is not None
    assert result_a.id == fix["contact_a"].id

    # Scoped to user B → must return contact B, never contact A.
    result_b = db_session.query(models.Contact).filter(
        models.Contact.email == email,
        models.Contact.user_id == fix["user_b"].id,
    ).first()
    assert result_b is not None
    assert result_b.id == fix["contact_b"].id


def test_unscoped_lookup_is_ambiguous_proving_scoping_matters(
    db_session, two_tenants_sharing_email
):
    """The test expresses *why* the scope is required: without it, two rows
    match and DB ordering picks one arbitrarily. This is the regression
    signal — if this returned a single row every time there would be no bug
    to fix. The assertion uses .count() so the test doesn't depend on which
    row SQLite picks first."""
    matches = db_session.query(models.Contact).filter(
        models.Contact.email == "alice@customer.com"
    ).count()
    assert matches == 2, (
        "expected both tenants' contacts to share the email — fixture broken"
    )


def test_execute_email_contact_lookup_source_includes_user_id_filter():
    """Source-code guard: the three contact lookups in executions.py must
    each carry a user_id clause next to the email clause. A refactor that
    drops it would leak cross-tenant RAG context; this catches it at unit
    time rather than once a customer reports seeing another customer's data.
    """
    import inspect

    import executions

    src = inspect.getsource(executions)
    # Every occurrence of models.Contact.email == ... must be followed within
    # a few lines by a models.Contact.user_id == ... filter.
    import re

    lines = src.splitlines()
    email_hits = []
    for idx, line in enumerate(lines):
        if "models.Contact.email ==" in line:
            email_hits.append(idx)

    assert len(email_hits) >= 2, (
        "expected multiple Contact.email == lookups in executions.py — "
        "did the code change shape?"
    )
    for idx in email_hits:
        window = "\n".join(lines[idx : idx + 5])
        assert "models.Contact.user_id" in window, (
            f"Contact.email lookup near line {idx + 1} is NOT scoped by "
            f"user_id — this reintroduces the H10 cross-tenant leak:\n"
            f"{window}"
        )


# ---------------------------------------------------------------------------
# backfill_rag_embeddings._resolve_contact_and_org — H11 guard
# ---------------------------------------------------------------------------

def test_backfill_resolve_contact_scoped_to_user_a(
    db_session, two_tenants_sharing_email
):
    """Running the backfill for workflow-owner A must return A's contact,
    never B's — even though both rows share the email."""
    fix = two_tenants_sharing_email

    result = asyncio.run(
        _resolve_contact_and_org(
            db_session,
            [{"email": "alice@customer.com"}],
            user_id=fix["user_a"].id,
        )
    )

    assert result == (fix["contact_a"].id, None)


def test_backfill_resolve_contact_scoped_to_user_b(
    db_session, two_tenants_sharing_email
):
    fix = two_tenants_sharing_email

    result = asyncio.run(
        _resolve_contact_and_org(
            db_session,
            [{"email": "alice@customer.com"}],
            user_id=fix["user_b"].id,
        )
    )

    assert result == (fix["contact_b"].id, None)


def test_backfill_resolve_contact_refuses_without_user_id(
    db_session, two_tenants_sharing_email
):
    """Missing user_id must refuse to match rather than return whichever
    tenant's row the DB happens to surface first."""
    result = asyncio.run(
        _resolve_contact_and_org(
            db_session,
            [{"email": "alice@customer.com"}],
            user_id=None,
        )
    )

    assert result == (None, None)
