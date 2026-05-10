"""Unit tests for backfill_rag_embeddings SQL candidate helpers.

Previously the backfill loaded every distinct already-embedded source_id into
a Python set on each run. The new helpers push that filter into SQL via
NOT EXISTS, keeping memory constant regardless of embedding-table size.
"""
from __future__ import annotations

import inspect
import re

import pytest

import backfill_rag_embeddings
from backfill_rag_embeddings import _email_candidates, _text_gen_candidates


def test_already_embedded_ids_helper_is_gone():
    """The in-memory scan helper must not come back under the old name."""
    assert not hasattr(backfill_rag_embeddings, "_already_embedded_ids"), (
        "_already_embedded_ids returned — the full-table scan regression is back"
    )


def test_text_gen_candidates_uses_not_exists_pattern():
    """Source-code smoke check: the helper must build a NOT EXISTS-style
    filter rather than materialising every already-embedded source_id. Pairs
    with the behavioural smoke test below."""
    src = inspect.getsource(_text_gen_candidates)
    # Two .exists() calls — one for text_gen_output, one for transcript_chunk.
    assert src.count(".exists()") == 2, (
        f"expected 2 .exists() correlated subqueries in source, got "
        f"{src.count('.exists()')}"
    )
    # Each must be inverted into NOT EXISTS via ~.
    assert src.count("~(") >= 2


def test_email_candidates_uses_not_exists_pattern():
    src = inspect.getsource(_email_candidates)
    assert ".exists()" in src
    assert "~(" in src


def test_text_gen_candidates_returns_three_tuples_shape():
    """Smoke: consumer loop unpacks (id, need_text_gen, need_transcript) per
    row. Verify empty result path doesn't choke."""
    from database import SessionLocal

    session = SessionLocal()
    try:
        # Monkey-patch Query.all globally for this call so we don't touch
        # the DB — we only care about the unpacking contract.
        from sqlalchemy.orm import Query

        orig_all = Query.all
        Query.all = lambda self: []  # type: ignore[method-assign]
        try:
            result = _text_gen_candidates(session, limit=None)
        finally:
            Query.all = orig_all  # type: ignore[method-assign]
        assert result == []
    finally:
        session.close()


def test_email_candidates_returns_int_list_shape():
    from database import SessionLocal

    session = SessionLocal()
    try:
        from sqlalchemy.orm import Query

        orig_all = Query.all
        Query.all = lambda self: []  # type: ignore[method-assign]
        try:
            result = _email_candidates(session, limit=None)
        finally:
            Query.all = orig_all  # type: ignore[method-assign]
        assert result == []
    finally:
        session.close()


def test_text_gen_candidates_passes_limit_through():
    """The limit parameter must reach the query object — without it, a
    --limit 100 invocation would scan the full executions table."""
    from database import SessionLocal
    from sqlalchemy.orm import Query

    session = SessionLocal()
    try:
        captured = {}
        orig_limit = Query.limit

        def _spy_limit(self, n):
            captured["limit"] = n
            return orig_limit(self, n)

        Query.limit = _spy_limit  # type: ignore[method-assign]

        orig_all = Query.all
        Query.all = lambda self: []  # type: ignore[method-assign]

        try:
            _text_gen_candidates(session, limit=42)
        finally:
            Query.limit = orig_limit  # type: ignore[method-assign]
            Query.all = orig_all  # type: ignore[method-assign]

        assert captured.get("limit") == 42
    finally:
        session.close()


def test_email_candidates_passes_limit_through():
    from database import SessionLocal
    from sqlalchemy.orm import Query

    session = SessionLocal()
    try:
        captured = {}
        orig_limit = Query.limit

        def _spy_limit(self, n):
            captured["limit"] = n
            return orig_limit(self, n)

        Query.limit = _spy_limit  # type: ignore[method-assign]

        orig_all = Query.all
        Query.all = lambda self: []  # type: ignore[method-assign]

        try:
            _email_candidates(session, limit=17)
        finally:
            Query.limit = orig_limit  # type: ignore[method-assign]
            Query.all = orig_all  # type: ignore[method-assign]

        assert captured.get("limit") == 17
    finally:
        session.close()
