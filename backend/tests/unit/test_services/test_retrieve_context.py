"""Unit tests for rag_service.retrieve_context.

Covers the two behaviours most likely to silently regress:

  1. WHERE-clause assembly based on optional filters (source_types,
     contact_id, org_id, since). If one is dropped, retrieval silently
     returns the wrong scope — worse than returning zero rows, because it
     looks plausible.

  2. Similarity-threshold resolution. When callers omit the threshold we
     fall back to SystemConfig (rag.similarity_threshold). Drifting
     between the bind param and the default is how recall quietly sinks
     without anyone noticing until a customer complains.

No real database is required — pgvector operators wouldn't parse on
SQLite anyway. We stub db.execute so we can inspect the SQL text and
bind params produced for each combination of inputs, and stub
_record_retrieval_latency since the event-loop dispatch isn't the unit
under test.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import rag_service
from rag_service import retrieve_context


# Column order matching the SELECT in rag_service.retrieve_context. Tests may
# pass rows as tuples in this order for brevity; the factory converts them to
# dicts so retrieve_context's by-name indexing (`row["id"]`, etc.) works.
_ROW_COLUMN_NAMES = (
    "id", "source_type", "source_id", "chunk_text",
    "chunk_index", "metadata", "similarity",
)


def _fake_execute_factory(rows=None, raise_on_select=False):
    """Return a MagicMock that mimics Session.execute.

    Captures every SQL string it sees on `calls` so tests can assert both
    the SET LOCAL GUC adjustment AND the main SELECT were issued with the
    expected shape.

    retrieve_context consumes rows via `.mappings().all()`, so the factory
    wires provided rows through that path. Tuple rows are converted to dicts
    using _ROW_COLUMN_NAMES; dict rows are used as-is.
    """
    calls = []
    mapped_rows = [
        r if isinstance(r, dict) else dict(zip(_ROW_COLUMN_NAMES, r))
        for r in (rows or [])
    ]

    def _execute(stmt, params=None):
        sql_text = str(stmt)
        calls.append({"sql": sql_text, "params": params})
        result = MagicMock()
        # The SET LOCAL statement has no params and returns nothing useful.
        if "SET LOCAL" in sql_text:
            result.mappings.return_value.all.return_value = []
            return result
        if raise_on_select:
            raise RuntimeError("simulated query failure")
        result.mappings.return_value.all.return_value = mapped_rows
        return result

    mock = MagicMock(side_effect=_execute)
    mock.calls = calls
    return mock


@pytest.fixture
def mock_embedding(monkeypatch):
    """get_query_embedding returns a deterministic vector so we can inspect
    the embedding bind param."""
    async def _embed(_text):
        return [0.1, 0.2, 0.3]
    monkeypatch.setattr(rag_service, "get_query_embedding", _embed)
    return _embed


@pytest.fixture
def silence_latency_log(monkeypatch):
    """_record_retrieval_latency opens its own session. We don't want it
    to fire during unit tests — it's a side effect, not the unit under test."""
    monkeypatch.setattr(rag_service, "_record_retrieval_latency", lambda *a, **kw: None)


@pytest.fixture
def default_limits(monkeypatch):
    """Pin the SystemConfig-backed defaults so tests don't depend on DB state."""
    monkeypatch.setattr(rag_service, "get_max_retrieval_results", lambda db=None: 5)
    monkeypatch.setattr(rag_service, "get_similarity_threshold", lambda db=None: 0.7)
    monkeypatch.setattr(rag_service, "get_hnsw_ef_search", lambda db=None: 100)


def _select_call(calls):
    """Locate the main SELECT among all db.execute calls."""
    for c in calls:
        if "SELECT" in c["sql"] and "content_embeddings" in c["sql"]:
            return c
    raise AssertionError(f"No SELECT on content_embeddings found in calls: {calls}")


class TestRetrieveContextQueryBuilding:
    @pytest.mark.asyncio
    async def test_base_query_only_account_filter(
        self, mock_embedding, silence_latency_log, default_limits
    ):
        db = MagicMock()
        db.execute = _fake_execute_factory(rows=[])

        await retrieve_context(db, query_text="hello", account_id=42)

        call = _select_call(db.execute.calls)
        assert "account_id = :account_id" in call["sql"]
        assert call["params"]["account_id"] == 42
        # No optional filters should have been spliced in.
        assert "source_type = ANY" not in call["sql"]
        assert "contact_id = :contact_id" not in call["sql"]
        assert "org_id" not in call["sql"]
        assert "created_at >= :since" not in call["sql"]

    @pytest.mark.asyncio
    async def test_source_types_filter_uses_any_array(
        self, mock_embedding, silence_latency_log, default_limits
    ):
        db = MagicMock()
        db.execute = _fake_execute_factory(rows=[])

        await retrieve_context(
            db, query_text="hello", account_id=1,
            source_types=["activity", "generated_email"],
        )

        call = _select_call(db.execute.calls)
        assert "source_type = ANY(:source_types)" in call["sql"]
        assert call["params"]["source_types"] == ["activity", "generated_email"]

    @pytest.mark.asyncio
    async def test_contact_id_filter_bound_correctly(
        self, mock_embedding, silence_latency_log, default_limits
    ):
        db = MagicMock()
        db.execute = _fake_execute_factory(rows=[])

        await retrieve_context(db, query_text="x", account_id=1, contact_id=99)

        call = _select_call(db.execute.calls)
        assert "contact_id = :contact_id" in call["sql"]
        assert call["params"]["contact_id"] == 99

    @pytest.mark.asyncio
    async def test_org_id_filter_includes_null_fallback(
        self, mock_embedding, silence_latency_log, default_limits
    ):
        """org-scoped retrieval must also match rows with NULL org_id, otherwise
        contact-level chunks (which don't carry an org_id) vanish from results."""
        db = MagicMock()
        db.execute = _fake_execute_factory(rows=[])

        await retrieve_context(db, query_text="x", account_id=1, org_id=7)

        call = _select_call(db.execute.calls)
        assert "(org_id = :org_id OR org_id IS NULL)" in call["sql"]
        assert call["params"]["org_id"] == 7

    @pytest.mark.asyncio
    async def test_since_filter_binds_datetime(
        self, mock_embedding, silence_latency_log, default_limits
    ):
        db = MagicMock()
        db.execute = _fake_execute_factory(rows=[])
        cutoff = datetime(2026, 4, 1, 12, 0, tzinfo=timezone.utc)

        await retrieve_context(db, query_text="x", account_id=1, since=cutoff)

        call = _select_call(db.execute.calls)
        assert "created_at >= :since" in call["sql"]
        assert call["params"]["since"] == cutoff

    @pytest.mark.asyncio
    async def test_all_filters_combined(
        self, mock_embedding, silence_latency_log, default_limits
    ):
        db = MagicMock()
        db.execute = _fake_execute_factory(rows=[])
        cutoff = datetime(2026, 4, 1, 12, 0, tzinfo=timezone.utc)

        await retrieve_context(
            db, query_text="x", account_id=1,
            source_types=["activity"], contact_id=2, org_id=3, since=cutoff,
        )

        call = _select_call(db.execute.calls)
        # All four filters present, joined by AND.
        for clause in [
            "source_type = ANY(:source_types)",
            "contact_id = :contact_id",
            "(org_id = :org_id OR org_id IS NULL)",
            "created_at >= :since",
        ]:
            assert clause in call["sql"], f"missing clause: {clause}"
        # AND-joined (not OR). The threshold clause is also AND'd.
        assert " AND " in call["sql"]

    @pytest.mark.asyncio
    async def test_exclude_contact_id_folds_into_where_clause(
        self, mock_embedding, silence_latency_log, default_limits
    ):
        """get_email_context used to post-filter the org block via a second
        ContentEmbedding.id.in_(...) query. The exclude_contact_id kwarg pushes
        that filter into the main SELECT — the follow-up query should be gone."""
        db = MagicMock()
        db.execute = _fake_execute_factory(rows=[])

        await retrieve_context(
            db, query_text="x", account_id=1, org_id=7, exclude_contact_id=99,
        )

        call = _select_call(db.execute.calls)
        assert "contact_id IS NULL OR contact_id <> :exclude_contact_id" in call["sql"]
        assert call["params"]["exclude_contact_id"] == 99

    @pytest.mark.asyncio
    async def test_exclude_contact_id_absent_by_default(
        self, mock_embedding, silence_latency_log, default_limits
    ):
        """Callers that don't set exclude_contact_id must not get the extra
        WHERE clause — the old behaviour (return everything) is the default."""
        db = MagicMock()
        db.execute = _fake_execute_factory(rows=[])

        await retrieve_context(db, query_text="x", account_id=1, org_id=7)

        call = _select_call(db.execute.calls)
        assert "exclude_contact_id" not in call["sql"]
        assert "exclude_contact_id" not in call["params"]

    @pytest.mark.asyncio
    async def test_result_uses_column_name_mapping(
        self, mock_embedding, silence_latency_log, default_limits
    ):
        """retrieve_context reads result columns by name (via .mappings().all())
        rather than positional index. A SELECT refactor that reorders columns
        must not silently shuffle field values into the wrong keys."""
        # Simulate two rows in column-name form. The *values* are deliberately
        # set so a positional mix-up would put the wrong type in the wrong
        # field (e.g. an int where a string is expected).
        mapped_rows = [
            {
                "id": 101,
                "source_type": "generated_email",
                "source_id": "email:5",
                "chunk_text": "body of email 5",
                "chunk_index": 0,
                "metadata": {"sent_at": "2026-04-20"},
                "similarity": 0.91,
            },
        ]

        def _execute(stmt, params=None):
            sql_text = str(stmt)
            if "SET LOCAL" in sql_text:
                r = MagicMock()
                r.mappings.return_value.all.return_value = []
                return r
            r = MagicMock()
            r.mappings.return_value.all.return_value = mapped_rows
            return r

        db = MagicMock()
        db.execute = MagicMock(side_effect=_execute)

        result = await retrieve_context(db, query_text="x", account_id=1)

        assert len(result) == 1
        row = result[0]
        assert row["id"] == 101
        assert row["source_type"] == "generated_email"
        assert row["source_id"] == "email:5"
        assert row["chunk_text"] == "body of email 5"
        assert row["metadata"] == {"sent_at": "2026-04-20"}
        assert row["similarity"] == pytest.approx(0.91)


class TestRetrieveContextSimilarityThreshold:
    @pytest.mark.asyncio
    async def test_threshold_defaults_to_system_config(
        self, mock_embedding, silence_latency_log, default_limits, monkeypatch
    ):
        """When threshold is None, retrieve_context reads from SystemConfig."""
        monkeypatch.setattr(rag_service, "get_similarity_threshold", lambda db=None: 0.84)
        db = MagicMock()
        db.execute = _fake_execute_factory(rows=[])

        await retrieve_context(db, query_text="x", account_id=1)

        call = _select_call(db.execute.calls)
        assert call["params"]["threshold"] == 0.84

    @pytest.mark.asyncio
    async def test_explicit_threshold_overrides_default(
        self, mock_embedding, silence_latency_log, default_limits
    ):
        db = MagicMock()
        db.execute = _fake_execute_factory(rows=[])

        await retrieve_context(
            db, query_text="x", account_id=1, similarity_threshold=0.55,
        )

        call = _select_call(db.execute.calls)
        assert call["params"]["threshold"] == 0.55
        assert (
            "1 - (embedding <=> CAST(:query_embedding AS vector)) >= :threshold"
            in call["sql"]
        )

    @pytest.mark.asyncio
    async def test_threshold_zero_is_preserved_not_defaulted(
        self, mock_embedding, silence_latency_log, default_limits
    ):
        """An explicit threshold of 0.0 is a valid 'no-filter' knob — the
        function must treat it as given, not as 'missing' and re-default."""
        db = MagicMock()
        db.execute = _fake_execute_factory(rows=[])

        await retrieve_context(
            db, query_text="x", account_id=1, similarity_threshold=0.0,
        )

        call = _select_call(db.execute.calls)
        assert call["params"]["threshold"] == 0.0

    @pytest.mark.asyncio
    async def test_limit_defaults_to_system_config(
        self, mock_embedding, silence_latency_log, default_limits, monkeypatch
    ):
        monkeypatch.setattr(rag_service, "get_max_retrieval_results", lambda db=None: 11)
        db = MagicMock()
        db.execute = _fake_execute_factory(rows=[])

        await retrieve_context(db, query_text="x", account_id=1)

        call = _select_call(db.execute.calls)
        assert call["params"]["limit"] == 11
        # No penalize_ids → fetch_limit == limit.
        assert call["params"]["fetch_limit"] == 11


class TestRetrieveContextPrecomputedEmbedding:
    @pytest.mark.asyncio
    async def test_query_vector_skips_embedding_call(
        self, silence_latency_log, default_limits, monkeypatch
    ):
        """If the caller pre-computes the embedding, we must not re-embed."""
        called = {"n": 0}

        async def _embed(_t):
            called["n"] += 1
            return [9.9, 9.9, 9.9]

        monkeypatch.setattr(rag_service, "get_query_embedding", _embed)

        db = MagicMock()
        db.execute = _fake_execute_factory(rows=[])

        await retrieve_context(
            db, query_text="x", account_id=1,
            query_vector=[0.11, 0.22, 0.33],
        )

        assert called["n"] == 0
        call = _select_call(db.execute.calls)
        assert call["params"]["query_embedding"] == "[0.11,0.22,0.33]"

    @pytest.mark.asyncio
    async def test_embedding_failure_returns_empty_without_sql(
        self, silence_latency_log, default_limits, monkeypatch
    ):
        """If get_query_embedding returns None (OpenAI outage / no key),
        retrieve_context must bail early rather than building a query with
        a None vector."""
        async def _embed(_t):
            return None

        monkeypatch.setattr(rag_service, "get_query_embedding", _embed)

        db = MagicMock()
        db.execute = _fake_execute_factory(rows=[])

        result = await retrieve_context(db, query_text="x", account_id=1)

        assert result == []
        # No SELECT should have been issued.
        assert not any(
            "SELECT" in c["sql"] and "content_embeddings" in c["sql"]
            for c in db.execute.calls
        )

    @pytest.mark.asyncio
    async def test_embedding_exception_swallowed_and_returns_empty(
        self, silence_latency_log, default_limits, monkeypatch
    ):
        """If get_query_embedding *raises* (not just returns None), the error
        is logged and the call degrades to [] — the retrieval path must not
        propagate OpenAI failures into the AI pipeline."""
        async def _embed(_t):
            raise RuntimeError("openai 500")

        monkeypatch.setattr(rag_service, "get_query_embedding", _embed)

        db = MagicMock()
        db.execute = _fake_execute_factory(rows=[])

        result = await retrieve_context(db, query_text="x", account_id=1)

        assert result == []
        assert not any(
            "SELECT" in c["sql"] and "content_embeddings" in c["sql"]
            for c in db.execute.calls
        )


class TestRetrieveContextDiversityPenalty:
    @pytest.mark.asyncio
    async def test_penalize_ids_triggers_over_fetch(
        self, mock_embedding, silence_latency_log, default_limits
    ):
        """When the caller wants diversity penalties applied, we over-fetch
        (3x) so there are losers that can be demoted below the cut."""
        db = MagicMock()
        db.execute = _fake_execute_factory(rows=[])

        await retrieve_context(
            db, query_text="x", account_id=1, limit=5,
            penalize_ids=[1, 2], penalty_multiplier=0.5,
        )

        call = _select_call(db.execute.calls)
        assert call["params"]["fetch_limit"] == 15
        assert call["params"]["limit"] == 5

    @pytest.mark.asyncio
    async def test_penalty_multiplier_demotes_matching_ids(
        self, mock_embedding, silence_latency_log, default_limits
    ):
        """A chunk listed in penalize_ids should have its similarity scaled
        by penalty_multiplier and get resorted below unpenalized peers."""
        rows = [
            (1, "activity", "a:1", "old chunk", 0, None, 0.95),   # penalized
            (2, "activity", "a:2", "fresh chunk", 0, None, 0.80),  # survives
            (3, "activity", "a:3", "fresh chunk2", 0, None, 0.78),  # survives
        ]
        db = MagicMock()
        db.execute = _fake_execute_factory(rows=rows)

        result = await retrieve_context(
            db, query_text="x", account_id=1, limit=2,
            penalize_ids=[1], penalty_multiplier=0.5,
        )

        # Row 1 was 0.95 but gets 0.95 * 0.5 = 0.475, so rows 2 and 3 now
        # outrank it. Limit=2 → rows 2 and 3.
        assert [r["id"] for r in result] == [2, 3]

    @pytest.mark.asyncio
    async def test_penalty_multiplier_one_is_no_op(
        self, mock_embedding, silence_latency_log, default_limits
    ):
        """penalty_multiplier == 1.0 should not perturb the DB-ordered result."""
        rows = [
            (1, "activity", "a:1", "x", 0, None, 0.95),
            (2, "activity", "a:2", "y", 0, None, 0.80),
        ]
        db = MagicMock()
        db.execute = _fake_execute_factory(rows=rows)

        result = await retrieve_context(
            db, query_text="x", account_id=1, limit=2,
            penalize_ids=[1], penalty_multiplier=1.0,
        )

        assert [r["id"] for r in result] == [1, 2]
        assert result[0]["similarity"] == 0.95

    @pytest.mark.asyncio
    async def test_penalty_marks_penalized_rows_and_resorts(
        self, mock_embedding, silence_latency_log, default_limits
    ):
        """Penalized rows should be explicitly marked and re-ranked."""
        rows = [
            (10, "activity", "a:10", "older", 0, None, 0.90),  # penalized
            (11, "activity", "a:11", "newer", 0, None, 0.85),
        ]
        db = MagicMock()
        db.execute = _fake_execute_factory(rows=rows)

        result = await retrieve_context(
            db, query_text="x", account_id=1, limit=2,
            penalize_ids=[10], penalty_multiplier=0.5,
        )

        # 10 becomes 0.45 and drops below 11.
        assert [r["id"] for r in result] == [11, 10]
        penalized = next(r for r in result if r["id"] == 10)
        assert penalized["similarity"] == pytest.approx(0.45)
        assert penalized["_penalized"] is True

    @pytest.mark.asyncio
    async def test_penalty_with_no_matching_ids_keeps_order(
        self, mock_embedding, silence_latency_log, default_limits
    ):
        """When no row ids match penalize_ids, ordering should remain unchanged."""
        rows = [
            (21, "activity", "a:21", "x", 0, None, 0.91),
            (22, "activity", "a:22", "y", 0, None, 0.83),
        ]
        db = MagicMock()
        db.execute = _fake_execute_factory(rows=rows)

        result = await retrieve_context(
            db, query_text="x", account_id=1, limit=2,
            penalize_ids=[999], penalty_multiplier=0.5,
        )

        assert [r["id"] for r in result] == [21, 22]
        assert all("_penalized" not in r for r in result)


class TestRetrieveContextFailureModes:
    @pytest.mark.asyncio
    async def test_db_execute_failure_returns_empty(
        self, mock_embedding, silence_latency_log, default_limits
    ):
        """A query-level exception (index issue, pgvector quirk) must degrade
        to [] rather than raise — retrieval is best-effort in the AI pipeline."""
        db = MagicMock()
        db.execute = _fake_execute_factory(raise_on_select=True)

        result = await retrieve_context(db, query_text="x", account_id=1)

        assert result == []

    @pytest.mark.asyncio
    async def test_set_local_hnsw_failure_is_nonfatal(
        self, mock_embedding, silence_latency_log, default_limits
    ):
        """Old pgvector / missing GUC shouldn't break retrieval — the SET LOCAL
        is raised-and-logged, and the SELECT still runs."""
        mapped_rows = [
            {
                "id": 1, "source_type": "activity", "source_id": "a:1",
                "chunk_text": "chunk", "chunk_index": 0,
                "metadata": None, "similarity": 0.9,
            },
        ]

        def _execute(stmt, params=None):
            sql_text = str(stmt)
            if "SET LOCAL" in sql_text:
                raise RuntimeError("hnsw.ef_search not available")
            r = MagicMock()
            r.mappings.return_value.all.return_value = mapped_rows
            return r

        db = MagicMock()
        db.execute = MagicMock(side_effect=_execute)

        result = await retrieve_context(db, query_text="x", account_id=1)

        assert len(result) == 1
        assert result[0]["id"] == 1

    @pytest.mark.asyncio
    async def test_set_local_ef_search_rejects_non_int(
        self, mock_embedding, silence_latency_log, monkeypatch
    ):
        """If get_hnsw_ef_search is ever refactored to return a non-numeric
        value, the int() cast must raise and the SET LOCAL must not execute —
        otherwise the f-string interpolation becomes a SQL injection sink."""
        monkeypatch.setattr(rag_service, "get_max_retrieval_results", lambda db=None: 5)
        monkeypatch.setattr(rag_service, "get_similarity_threshold", lambda db=None: 0.7)
        monkeypatch.setattr(
            rag_service,
            "get_hnsw_ef_search",
            lambda db=None: "100; DROP TABLE content_embeddings; --",
        )

        db = MagicMock()
        db.execute = _fake_execute_factory(rows=[])

        await retrieve_context(db, query_text="x", account_id=1)

        set_local_calls = [c for c in db.execute.calls if "SET LOCAL" in c["sql"]]
        assert set_local_calls == []

    @pytest.mark.asyncio
    async def test_set_local_ef_search_rejects_out_of_range(
        self, mock_embedding, silence_latency_log, monkeypatch
    ):
        """If the clamp in get_hnsw_ef_search ever regresses, the range assert
        at the call site must still refuse to interpolate the value."""
        monkeypatch.setattr(rag_service, "get_max_retrieval_results", lambda db=None: 5)
        monkeypatch.setattr(rag_service, "get_similarity_threshold", lambda db=None: 0.7)
        monkeypatch.setattr(rag_service, "get_hnsw_ef_search", lambda db=None: 5)

        db = MagicMock()
        db.execute = _fake_execute_factory(rows=[])

        await retrieve_context(db, query_text="x", account_id=1)

        set_local_calls = [c for c in db.execute.calls if "SET LOCAL" in c["sql"]]
        assert set_local_calls == []
