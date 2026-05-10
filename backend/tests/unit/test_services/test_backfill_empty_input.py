"""Regression tests for empty-input handling in the RAG backfill script.

Before these tests existed, ``backfill_text_gen`` (and ``backfill_emails``)
would hit a NameError on the final log line when the candidate query returned
zero rows — because ``processed`` was only incremented inside the loop and
never defined otherwise. Running the script against an already-backfilled
database therefore crashed instead of logging "nothing to do".

The tests monkey-patch the SQL candidate helpers to return an empty list so
we exercise the exit path without standing up a real DB.
"""
from __future__ import annotations

import asyncio
import logging

import pytest

import backfill_rag_embeddings
from backfill_rag_embeddings import backfill_emails, backfill_text_gen


def test_backfill_text_gen_handles_empty_candidate_list(monkeypatch, caplog):
    """Zero candidates → zero processed, zero ok/fail/skipped, no exception,
    and the final progress line is emitted with processed=0."""
    monkeypatch.setattr(
        backfill_rag_embeddings,
        "_text_gen_candidates",
        lambda db, limit: [],
    )

    with caplog.at_level(logging.INFO, logger="backfill_rag_embeddings"):
        ok, fail, skipped = asyncio.run(backfill_text_gen(limit=None, dry_run=False))

    assert (ok, fail, skipped) == (0, 0, 0)

    final = [
        r for r in caplog.records
        if r.levelno == logging.INFO
        and "Text gen final progress" in r.getMessage()
    ]
    assert len(final) == 1
    assert "processed=0" in final[0].getMessage()


def test_backfill_emails_handles_empty_candidate_list(monkeypatch, caplog):
    """Matching regression guard for #165 — same NameError risk on the
    emails path if ``processed`` ever loses its pre-loop initialization."""
    monkeypatch.setattr(
        backfill_rag_embeddings,
        "_email_candidates",
        lambda db, limit: [],
    )

    with caplog.at_level(logging.INFO, logger="backfill_rag_embeddings"):
        ok, fail, skipped = asyncio.run(backfill_emails(limit=None, dry_run=False))

    assert (ok, fail, skipped) == (0, 0, 0)

    final = [
        r for r in caplog.records
        if r.levelno == logging.INFO
        and "Emails final progress" in r.getMessage()
    ]
    assert len(final) == 1
    assert "processed=0" in final[0].getMessage()


def test_processed_initialized_before_loop_in_source():
    """Source-code guard: both backfill entrypoints must assign processed=0
    before the loop. A refactor that drops the initialization would let the
    old NameError come back on empty input — this test catches it at unit
    time, not during an ops-hours re-run."""
    import inspect

    for fn in (backfill_text_gen, backfill_emails):
        src = inspect.getsource(fn)
        # Roughly: the first occurrence of "processed" in the function body
        # must be an assignment, not a +=.
        first_assign = src.find("processed = 0")
        first_inc = src.find("processed += 1")
        assert first_assign != -1, f"{fn.__name__} missing processed=0 init"
        assert first_assign < first_inc, (
            f"{fn.__name__} increments processed before initializing it"
        )
