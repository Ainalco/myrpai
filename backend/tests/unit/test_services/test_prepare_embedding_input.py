"""Unit tests for rag_service._prepare_embedding_input.

Previously the 30k-char truncation was a silent ``text[:30000]`` slice — a
long Fireflies transcript lost context with no log line to correlate against
a recall drop. The new helper logs at WARNING on the 1st hit and every Nth
hit thereafter so the ceiling is visible without flooding logs on a bulk
backfill.
"""
from __future__ import annotations

import logging

import pytest

import rag_service
from rag_service import (
    EMBEDDINGS_MAX_CHARS_PER_INPUT,
    _prepare_embedding_input,
)


@pytest.fixture(autouse=True)
def reset_truncation_counter():
    rag_service._embedding_truncation_count = 0
    yield
    rag_service._embedding_truncation_count = 0


def test_short_input_passes_through_unchanged():
    out = _prepare_embedding_input("hello world")
    assert out == "hello world"
    assert rag_service._embedding_truncation_count == 0


def test_whitespace_is_stripped():
    assert _prepare_embedding_input("   padded   ") == "padded"


def test_empty_and_none_substituted_with_placeholder():
    """The embeddings endpoint rejects empty strings — the old slice used
    the same ``.`` fallback and we preserve it here."""
    assert _prepare_embedding_input(None) == "."
    assert _prepare_embedding_input("") == "."
    assert _prepare_embedding_input("   ") == "."


def test_long_input_truncated_at_limit(caplog):
    long_text = "a" * (EMBEDDINGS_MAX_CHARS_PER_INPUT + 5000)

    with caplog.at_level(logging.WARNING, logger="rag_service"):
        out = _prepare_embedding_input(long_text)

    assert len(out) == EMBEDDINGS_MAX_CHARS_PER_INPUT
    warnings = [
        r for r in caplog.records
        if r.levelno == logging.WARNING
        and "truncating embedding input" in r.getMessage()
    ]
    assert len(warnings) == 1
    msg = warnings[0].getMessage()
    assert str(EMBEDDINGS_MAX_CHARS_PER_INPUT) in msg
    assert str(EMBEDDINGS_MAX_CHARS_PER_INPUT + 5000) in msg


def test_repeated_truncations_are_sampled(caplog, monkeypatch):
    """A bulk backfill full of long transcripts must not flood the log — we
    warn on the 1st hit and every Nth, and silently count the rest."""
    monkeypatch.setattr(rag_service, "_EMBEDDING_TRUNCATION_LOG_EVERY", 10)
    long_text = "b" * (EMBEDDINGS_MAX_CHARS_PER_INPUT + 1)

    with caplog.at_level(logging.WARNING, logger="rag_service"):
        for _ in range(25):
            _prepare_embedding_input(long_text)

    warnings = [
        r for r in caplog.records
        if r.levelno == logging.WARNING
        and "truncating embedding input" in r.getMessage()
    ]
    # 1st, 10th, 20th = 3 warnings across 25 truncations.
    assert len(warnings) == 3
    assert rag_service._embedding_truncation_count == 25


def test_input_exactly_at_limit_is_not_flagged(caplog):
    """Off-by-one guard — an input equal to the limit must NOT warn."""
    exact = "c" * EMBEDDINGS_MAX_CHARS_PER_INPUT

    with caplog.at_level(logging.WARNING, logger="rag_service"):
        out = _prepare_embedding_input(exact)

    assert len(out) == EMBEDDINGS_MAX_CHARS_PER_INPUT
    warnings = [
        r for r in caplog.records
        if r.levelno == logging.WARNING
        and "truncating embedding input" in r.getMessage()
    ]
    assert warnings == []
    assert rag_service._embedding_truncation_count == 0


@pytest.mark.asyncio
async def test_generate_embeddings_uses_helper(monkeypatch, caplog):
    """End-to-end: generate_embeddings must route every input through the
    helper so the warning fires from the real call path — not just in
    isolation. Also pins that short inputs are silent."""
    # Disable the OpenAI call entirely.
    monkeypatch.setattr(rag_service, "OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(
        rag_service,
        "_batch_embedding_inputs",
        lambda texts: [texts] if texts else [],
    )

    async def _fake_embed(_batch):
        return [[0.0] * rag_service.EMBEDDING_DIM for _ in _batch]

    monkeypatch.setattr(rag_service, "_embed_batch_with_retry", _fake_embed)

    long_text = "x" * (EMBEDDINGS_MAX_CHARS_PER_INPUT + 1)
    with caplog.at_level(logging.WARNING, logger="rag_service"):
        await rag_service.generate_embeddings(["short one", long_text])

    warnings = [
        r for r in caplog.records
        if r.levelno == logging.WARNING
        and "truncating embedding input" in r.getMessage()
    ]
    assert len(warnings) == 1
