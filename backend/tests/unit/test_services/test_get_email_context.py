"""Regression tests for rag_service.get_email_context.

The org block used to re-query ContentEmbedding.id.in_(...) after retrieval to
strip out chunks belonging to the current contact (those are already in the
PREVIOUS OUTREACH / CONTACT HISTORY blocks). The fix folds that filter into the
main SELECT via retrieve_context(exclude_contact_id=...).

These tests lock the new contract so a refactor can't reintroduce the extra
round-trip, and verify the ORG SELECT actually carries the exclusion clause.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

import rag_service
from rag_service import get_email_context


@pytest.fixture
def patched_deps(monkeypatch):
    """Stub the expensive RAG dependencies with in-memory fakes so the unit
    test doesn't need pgvector / Redis / Anthropic."""
    async def _embed(_text):
        return [0.1, 0.2, 0.3]
    monkeypatch.setattr(rag_service, "get_query_embedding", _embed)
    monkeypatch.setattr(rag_service, "_get_diversity_penalty", lambda db: 0.5)


def test_org_block_exclusion_is_pushed_into_retrieve_context_call(monkeypatch, patched_deps):
    """When both contact_id and org_id are set, the org-scope retrieve_context
    call must carry exclude_contact_id=contact_id — otherwise we're back to
    post-filtering, which was the whole point of this fix."""
    captured_calls = []

    async def _fake_retrieve_context(**kwargs):
        captured_calls.append(kwargs)
        return []

    monkeypatch.setattr(rag_service, "retrieve_context", _fake_retrieve_context)

    db = MagicMock()

    import asyncio
    asyncio.run(
        get_email_context(
            db=db,
            account_id=1,
            query_text="hello",
            contact_id=99,
            org_id=7,
        )
    )

    org_calls = [
        c for c in captured_calls
        if "text_gen_output" in (c.get("source_types") or [])
        and "generated_email" in (c.get("source_types") or [])
    ]
    assert len(org_calls) == 1, f"expected one org-scope retrieve_context call, got {org_calls}"
    assert org_calls[0]["exclude_contact_id"] == 99
    assert org_calls[0]["org_id"] == 7


def test_no_extra_content_embedding_query_after_retrieval(monkeypatch, patched_deps):
    """The fix removes the `db.query(models.ContentEmbedding.id).filter(...).all()`
    post-filter. The test stubs retrieve_context to return distinct org rows and
    asserts db.query was never invoked — all filtering happens in the main SELECT."""
    async def _fake_retrieve_context(**kwargs):
        src = kwargs.get("source_types") or []
        # Seed just enough rows so dedupe/format code paths run.
        if "resource" in src:
            return []
        return [
            {
                "id": 101, "source_type": "text_gen_output", "source_id": "tg:1",
                "chunk_text": "org insight", "chunk_index": 0, "metadata": None,
                "similarity": 0.88,
            },
        ]

    monkeypatch.setattr(rag_service, "retrieve_context", _fake_retrieve_context)

    db = MagicMock()

    import asyncio
    result = asyncio.run(
        get_email_context(
            db=db,
            account_id=1,
            query_text="hello",
            contact_id=99,
            org_id=7,
        )
    )

    # The extra post-filter used db.query(models.ContentEmbedding.id) — after
    # the fix, that entry point must not be touched.
    db.query.assert_not_called()
    # Sanity: context was still produced.
    assert result["formatted"]
