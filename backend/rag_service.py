"""
RAG (Retrieval-Augmented Generation) service for Scurry AI.

Provides chunking, embedding, storage, and retrieval of text content
for context injection into AI prompts. Uses OpenAI text-embedding-3-small
for embeddings (never for generation) and pgvector for similarity search.

Vector index:
    content_embeddings.embedding is indexed with pgvector HNSW using
    vector_cosine_ops (see migrations 033 and 038). HNSW was chosen over
    IVFFlat because:
      * IVFFlat requires k-means over existing vectors — building it on an
        empty table (as Phase-3 migrations did) produces degenerate centroids
        and cratered recall.
      * IVFFlat's CREATE/REINDEX takes ACCESS EXCLUSIVE on the table. On a
        multi-million-row prod table that is minutes of write downtime.
      * HNSW builds incrementally, keeps recall stable as data grows, and
        can be built with CREATE INDEX CONCURRENTLY without blocking writes.

    retrieve_context() issues `SET LOCAL hnsw.ef_search = <N>` per query
    (see HNSW_EF_SEARCH_DEFAULT / SystemConfig key `rag.hnsw_ef_search`). The
    pgvector default of 40 is too low for recall@10 >= 0.9; we raise it to 100.

SystemConfig tuning keys:
    All values below are readable via get_config_float / get_config_int and are
    seeded by alembic migrations 034, 035, 041. Update them in the admin UI
    (PUT /system-config/{key}) to tune RAG/batch behaviour without a redeploy.

    rag.chunk_size                      int,    default 300      (words per chunk)
    rag.chunk_overlap                   int,    default 50       (word overlap between adjacent chunks)
    rag.similarity_threshold            float,  default 0.70     (min cosine similarity, 0..1)
    rag.structured_preference           float,  default 0.78     (score above which structured chunks are boosted, 0..1)
    rag.structured_preference_boost     float,  default 0.05     (additive similarity bump applied to boosted chunks, 0..0.2)
    rag.max_retrieval_results           int,    default 5        (top-k per retrieval block)
    rag.dedup_jaccard_threshold         float,  default 0.6      (drop-as-dup threshold, 0..1)
    rag.diversity_penalty               float,  default 0.5      (multiplier on similarity for already-used chunks, 0..1)
    rag.hnsw_ef_search                  int,    default 100      (pgvector HNSW search list, clamped to [10,1000])
    rag.haiku_model                     string, default DEFAULT_HAIKU_MODEL   (Anthropic model id for AI Filter + sufficiency)
    rag.sonnet_model                    string, default DEFAULT_SONNET_MODEL  (Anthropic model id for email gen + STOP/CONTINUE)
    rag.batch_api_threshold_hours       int,    default 24       (schedule-ahead hours that route through Batch API)
    rag.thin_transcript_tier1_threshold int,    default 2        (Tier 1 missing-field count that flags transcript as thin)
    rag.batch_submit_interval_seconds   int,    default 60       (batch worker cycle interval)
    rag.batch_reconcile_lookback_hours  int,    default 24       (how far back reconciliation scans Anthropic batches)
    rag.batch_stuck_threshold_hours     int,    default 26       (row age past which batch is failed; matches admin stuck cutoff)
    rag.batch_max_batch_size            int,    default 100      (max rows per Anthropic batch submit)
    rag.batch_max_poll_failures         int,    default 5        (consecutive poll errors before batch is failed)

Operator A/B changes: edit via PUT /system-config/{key}; the in-memory cache
is invalidated on write, so the next request picks the new value up. No
restart required.
"""

import asyncio
import hashlib
import os
import re
import json
import logging
import random
import time
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple

import httpx
from sqlalchemy.orm import Session
from sqlalchemy import text, and_, or_
from sqlalchemy.dialects.postgresql import insert as pg_insert

from database import SessionLocal
import models
from cache_service import cache_get, cache_set
from system_config import get_config, get_config_float, get_config_int
from tracing import traced_call, is_tracing, record_skip

logger = logging.getLogger(__name__)

# --- PII-in-logs policy (see backend/logging_config.py for the global rules) ---
#
# Retrieved chunks, email bodies, transcript text, and third-party request/
# response bodies can contain PII (names, emails, phone numbers, financial
# details). Rules for this module:
#
#   * INFO / WARNING / ERROR logs MUST NOT include chunk_text, email bodies,
#     transcript text, or raw third-party response bodies. Log structural
#     metadata only (ids, sizes, status codes, error codes/types).
#   * DEBUG logs MAY include a short preview of content, but only when routed
#     through _redact() AND only when RAG_DEBUG_PII=true is set. The default-
#     off gate prevents "raise log level to DEBUG for troubleshooting" from
#     leaking PII to the log aggregator.
#   * Third-party error bodies (OpenAI, Anthropic) echo the submitted input on
#     some failure modes. Never log the raw body — use _sanitize_openai_error
#     to pull out code/type/message, and redact the message.

_RAG_DEBUG_PII = os.getenv("RAG_DEBUG_PII", "").lower() in ("1", "true", "yes")


def _redact(text: Optional[str], max_chars: int = 100) -> str:
    """Truncate content to a short preview for DEBUG logs.

    Callers must still gate the log site on _RAG_DEBUG_PII — this helper only
    caps blast radius if the gate is accidentally flipped on.
    """
    if not text:
        return ""
    return text[:max_chars] + ("…" if len(text) > max_chars else "")


def _sanitize_openai_error(exc: "httpx.HTTPStatusError") -> str:
    """Summarize an OpenAI HTTP error without echoing submitted input.

    OpenAI error bodies have shape {"error": {"message", "type", "code", ...}}.
    On 400s the message may quote the offending input verbatim, so it is
    redacted to a short preview instead of logged in full.
    """
    try:
        body = exc.response.json()
        err = body.get("error", {}) if isinstance(body, dict) else {}
        parts = [f"status={exc.response.status_code}"]
        err_type = err.get("type")
        code = err.get("code")
        message = err.get("message")
        if err_type:
            parts.append(f"type={err_type}")
        if code:
            parts.append(f"code={code}")
        if message:
            parts.append(f"message={_redact(message, 200)}")
        return " ".join(parts)
    except Exception:
        return f"status={exc.response.status_code} (error body not parseable)"


# --- Constants (absolute fallbacks used when DB is unreachable) ---
# All values are overridden at runtime by SystemConfig; see the docstring at
# the top of this module for the full list of rag.* / batch.* keys, units,
# and expected ranges.
CHUNK_SIZE = 300
CHUNK_OVERLAP = 50
EMBEDDING_MODEL = "text-embedding-3-small"
# Passed explicitly to OpenAI and asserted on every response so model/dim drift
# (e.g. swapping to text-embedding-3-large at 3072) fails loud instead of
# silently corrupting rows. Must match the vector(N) column type in migration 033.
EMBEDDING_DIM = 1536
# OpenAI embeddings caps: 2048 inputs per request and ~300k tokens per request.
# Char-based heuristic (~4 chars/token for English) keeps us well under both
# without a tiktoken dep; assumption breaks for CJK, which we don't ingest.
EMBEDDINGS_MAX_INPUTS_PER_REQUEST = 2048
EMBEDDINGS_MAX_CHARS_PER_REQUEST = 600_000
EMBEDDINGS_MAX_CHARS_PER_INPUT = 30_000
# Sample rate for embedding-truncation warnings. Logs the 1st hit (so the
# problem is visible immediately) and then every Nth, so a bulk backfill on
# a corpus full of long transcripts doesn't drown operator log pipelines.
_EMBEDDING_TRUNCATION_LOG_EVERY = 50
EMBEDDINGS_MAX_ATTEMPTS = 6
EMBEDDINGS_BACKOFF_CAP_SECONDS = 60.0
SIMILARITY_THRESHOLD = 0.70
STRUCTURED_PREFERENCE = 0.78
STRUCTURED_PREFERENCE_BOOST = 0.05
MAX_RETRIEVAL_RESULTS = 5
DEDUP_JACCARD_THRESHOLD = 0.6
HNSW_EF_SEARCH_DEFAULT = 100  # pgvector default is 40; too low for recall@10 >= 0.9

DEFAULT_HAIKU_MODEL = "claude-haiku-4-5-20251001"
DEFAULT_SONNET_MODEL = "claude-sonnet-4-6"
DEFAULT_DIVERSITY_PENALTY = 0.5

# Single source of truth for the source_types the pre-send safety net
# both *ingests* (contacts_service._schedule_activity_embedding,
# store_generated_email) and *reads* (get_presend_snapshot). The two sides
# drifting silently would under-protect against the exact case the feature
# exists to catch — e.g. a deal_stage_changed write that the snapshot never
# queries. Keep ingest writes and the snapshot filter aligned via this tuple.
PRESEND_SOURCE_TYPES: Tuple[str, ...] = ("activity", "crm_change", "generated_email")

# Activity types that should ingest under source_type="crm_change" instead of
# the generic "activity" bucket. Used by activity_source_type(); any value
# added here must also be covered by PRESEND_SOURCE_TYPES.
CRM_CHANGE_ACTIVITY_TYPES: frozenset = frozenset({"deal_stage_changed", "contact_updated"})


def activity_source_type(activity_type: str) -> str:
    """Return the content_embeddings.source_type for a ContactActivity row.

    Centralizes the write-side decision so the read side (get_presend_snapshot)
    can rely on a closed set of source_types — see PRESEND_SOURCE_TYPES.
    """
    return "crm_change" if activity_type in CRM_CHANGE_ACTIVITY_TYPES else "activity"

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# Warn once when embeddings are requested without a configured key, instead of
# repeating a stack-trace-worthy error on every call. Set True after first warn.
_EMBEDDINGS_DISABLED_WARNED = False


# Fail fast at import if EMBEDDING_DIM drifts from the vector column type —
# silent corruption is worse than a boot failure, and the per-response dim
# assertion in _embed_batch_with_retry can't protect rows written by other
# paths that bypass it.
_column_dim = getattr(
    models.ContentEmbedding.__table__.c.embedding.type, "dim", None
)
if _column_dim is not None and _column_dim != EMBEDDING_DIM:
    raise RuntimeError(
        f"EMBEDDING_DIM ({EMBEDDING_DIM}) does not match the "
        f"content_embeddings.embedding column dim ({_column_dim}). "
        f"Update EMBEDDING_MODEL/EMBEDDING_DIM and run an Alembic migration "
        f"before starting the service."
    )


def embeddings_available() -> bool:
    """True when OPENAI_API_KEY is configured; RAG silently no-ops otherwise."""
    return bool(OPENAI_API_KEY)


# --- Config helpers ---

def _get_diversity_penalty(db: Session) -> float:
    try:
        return get_config_float("rag.diversity_penalty", db, default=DEFAULT_DIVERSITY_PENALTY)
    except Exception:
        return DEFAULT_DIVERSITY_PENALTY


def _get_float(key: str, fallback: float, db: Optional[Session] = None) -> float:
    """Read a SystemConfig float, using an owned session when none is provided.
    Falls back to the hardcoded value if config lookup fails (e.g. DB unavailable)."""
    try:
        if db is not None:
            return get_config_float(key, db, default=fallback)
        _db = SessionLocal()
        try:
            return get_config_float(key, _db, default=fallback)
        finally:
            _db.close()
    except Exception:
        return fallback


def _get_int(key: str, fallback: int, db: Optional[Session] = None) -> int:
    try:
        if db is not None:
            return get_config_int(key, db, default=fallback)
        _db = SessionLocal()
        try:
            return get_config_int(key, _db, default=fallback)
        finally:
            _db.close()
    except Exception:
        return fallback


def get_chunk_size(db: Optional[Session] = None) -> int:
    return _get_int("rag.chunk_size", CHUNK_SIZE, db)


def get_chunk_overlap(db: Optional[Session] = None) -> int:
    return _get_int("rag.chunk_overlap", CHUNK_OVERLAP, db)


def get_similarity_threshold(db: Optional[Session] = None) -> float:
    return _get_float("rag.similarity_threshold", SIMILARITY_THRESHOLD, db)


def get_structured_preference(db: Optional[Session] = None) -> float:
    return _get_float("rag.structured_preference", STRUCTURED_PREFERENCE, db)


def get_structured_preference_boost(db: Optional[Session] = None) -> float:
    """Additive similarity boost applied to structured chunks scoring above
    rag.structured_preference. Operators can tune via SystemConfig to A/B how
    strongly text_gen_output/resource hits outrank raw transcript chunks."""
    return _get_float("rag.structured_preference_boost", STRUCTURED_PREFERENCE_BOOST, db)


def get_max_retrieval_results(db: Optional[Session] = None) -> int:
    return _get_int("rag.max_retrieval_results", MAX_RETRIEVAL_RESULTS, db)


def get_dedup_jaccard_threshold(db: Optional[Session] = None) -> float:
    return _get_float("rag.dedup_jaccard_threshold", DEDUP_JACCARD_THRESHOLD, db)


def get_hnsw_ef_search(db: Optional[Session] = None) -> int:
    """HNSW search-list size. Passed to `SET LOCAL hnsw.ef_search` per query.

    Clamped to [10, 1000] because the value is interpolated directly into SQL
    (GUC assignments don't accept bind parameters) and we want a bounded range.
    """
    value = _get_int("rag.hnsw_ef_search", HNSW_EF_SEARCH_DEFAULT, db)
    return max(10, min(1000, int(value)))


def get_haiku_model(db: Optional[Session] = None) -> str:
    """Return the configured Haiku model id, used for AI Filter and sufficiency checks."""
    try:
        _db = db or SessionLocal()
        _owned = db is None
        try:
            return get_config("rag.haiku_model", _db, default=DEFAULT_HAIKU_MODEL) or DEFAULT_HAIKU_MODEL
        finally:
            if _owned:
                _db.close()
    except Exception:
        return DEFAULT_HAIKU_MODEL


def get_sonnet_model(db: Optional[Session] = None) -> str:
    """Return the configured Sonnet model id, used for email generation and STOP/CONTINUE."""
    try:
        _db = db or SessionLocal()
        _owned = db is None
        try:
            return get_config("rag.sonnet_model", _db, default=DEFAULT_SONNET_MODEL) or DEFAULT_SONNET_MODEL
        finally:
            if _owned:
                _db.close()
    except Exception:
        return DEFAULT_SONNET_MODEL


class ConfiguredModelError(RuntimeError):
    """Raised at startup when a configured Anthropic model id is obviously bad.

    Bad model ids today fail silently: the Haiku sufficiency classifier, for
    example, returns non-standard output that falls through to SUFFICIENT, so
    a typo in rag.haiku_model looks like "classifier too permissive" instead
    of a config bug. Failing loud at startup keeps misconfiguration from
    reaching the RAG pipeline at all.
    """


def validate_configured_models(db: Optional[Session] = None) -> Dict[str, str]:
    """Sanity-check rag.haiku_model / rag.sonnet_model at startup.

    Checks performed:
      - value is non-empty
      - value starts with "claude-" (all Anthropic model ids do; catches typos
        like an OpenAI id being pasted into the admin UI)
      - value appears in the ai_models table OR matches the hardcoded default
        (ai_models carries pricing; a model id not present there will fall
        back to Sonnet 4.5 pricing silently, which is what we want to surface)

    Returns the validated {role: model_id} map. Raises ConfiguredModelError
    on the first bad value so the app aborts startup instead of booting into
    a broken state where email generation or AI Filters would silently misbehave.

    Dry API calls are intentionally *not* made here — a transient Anthropic
    outage should not block the service from starting, and any real
    validation that Anthropic accepts the id happens on the first real call
    (where it is already surfaced via handle_anthropic_error).
    """
    _db = db or SessionLocal()
    _owned = db is None
    try:
        configured = {
            "rag.haiku_model": (get_haiku_model(_db), DEFAULT_HAIKU_MODEL),
            "rag.sonnet_model": (get_sonnet_model(_db), DEFAULT_SONNET_MODEL),
        }

        known_ids: set = set()
        try:
            rows = _db.query(models.AiModel.model_id).all()
            known_ids = {r[0] for r in rows if r and r[0]}
        except Exception as e:
            logger.warning(
                "validate_configured_models: could not load ai_models (%s); "
                "falling back to default-only validation",
                e,
            )

        validated: Dict[str, str] = {}
        for key, (value, default) in configured.items():
            if not value or not value.strip():
                raise ConfiguredModelError(
                    f"SystemConfig '{key}' is empty — set it to a valid "
                    f"Anthropic model id (e.g. '{default}')."
                )
            v = value.strip()
            if not v.startswith("claude-"):
                raise ConfiguredModelError(
                    f"SystemConfig '{key}'={v!r} does not look like an Anthropic "
                    f"model id (must start with 'claude-'). Typo?"
                )
            if known_ids and v not in known_ids and v != default:
                # Not fatal — pricing will fall back — but surface it loud so
                # operators notice before it shows up as a billing discrepancy.
                logger.warning(
                    "SystemConfig '%s'=%r is not in ai_models table; billable "
                    "cost will use the default Sonnet pricing until the row is "
                    "added via /admin/models.",
                    key, v,
                )
            validated[key] = v

        logger.info("Configured Anthropic models validated: %s", validated)
        return validated
    finally:
        if _owned:
            _db.close()


# --- Chunking ---

def chunk_text(text_content: str, chunk_size: Optional[int] = None, overlap: Optional[int] = None) -> List[str]:
    """Split text into overlapping word-based chunks.

    When chunk_size/overlap are not supplied, values are resolved from SystemConfig
    so operators can tune retrieval without a deploy."""
    if not text_content or not text_content.strip():
        return []

    if chunk_size is None:
        chunk_size = get_chunk_size()
    if overlap is None:
        overlap = get_chunk_overlap()

    words = text_content.split()
    if len(words) <= chunk_size:
        return [text_content.strip()]

    chunks = []
    start = 0
    step = max(1, chunk_size - overlap)

    while start < len(words):
        end = min(start + chunk_size, len(words))
        chunk = " ".join(words[start:end])
        chunks.append(chunk.strip())
        if end >= len(words):
            break
        start += step

    return chunks


def chunk_structured_output(structured_data: Dict[str, Any]) -> List[Tuple[str, str]]:
    """Convert structured Text Gen output into (field_group, text) pairs for embedding.

    Each non-empty field group becomes a single chunk for embedding.
    Field groups: pain_points, next_steps, verbatim_quotes, meeting_summary,
    buying_signals, contact_info, unique_details, and any extraction point names.

    Args:
        structured_data: The extracted_information dict from Text Gen output.

    Returns:
        List of (field_group_name, text_content) tuples.
    """
    if not structured_data or not isinstance(structured_data, dict):
        return []

    # Map common extraction point names to canonical field groups
    field_group_mapping = {
        "pain points": "pain_points",
        "pain_points": "pain_points",
        "next steps": "next_steps",
        "next_steps": "next_steps",
        "action items": "next_steps",
        "action_items": "next_steps",
        "verbatim quotes": "verbatim_quotes",
        "verbatim_quotes": "verbatim_quotes",
        "key quotes": "verbatim_quotes",
        "meeting summary": "meeting_summary",
        "summary": "meeting_summary",
        "buying signals": "buying_signals",
        "buying_signals": "buying_signals",
        "contact info": "contact_info",
        "contact_info": "contact_info",
        "participants": "contact_info",
        "unique details": "unique_details",
        "unique_details": "unique_details",
        "budget": "buying_signals",
        "timeline": "buying_signals",
        "competitors": "unique_details",
    }

    result = []
    for key, value in structured_data.items():
        if value is None:
            continue

        # Normalize key
        normalized_key = key.lower().strip().replace("-", "_")
        field_group = field_group_mapping.get(normalized_key, normalized_key)

        # Convert value to readable text
        if isinstance(value, list):
            if not value:
                continue
            text_content = f"{key}:\n" + "\n".join(f"- {item}" for item in value)
        elif isinstance(value, dict):
            if not value:
                continue
            text_content = f"{key}:\n" + json.dumps(value, indent=2)
        elif isinstance(value, str):
            if not value.strip():
                continue
            text_content = f"{key}: {value}"
        else:
            text_content = f"{key}: {str(value)}"

        result.append((field_group, text_content))

    return result


# --- Embeddings ---

# Counter for truncation warnings. Module-level so sampling is consistent
# across calls within a process; resets on worker restart (which is fine —
# restart-level re-surfacing is desirable).
_embedding_truncation_count = 0


def _prepare_embedding_input(text: Optional[str]) -> str:
    """Normalise an input for the embeddings endpoint.

    Strips whitespace, substitutes a single "." for empty/None (the endpoint
    rejects empty strings), and enforces EMBEDDINGS_MAX_CHARS_PER_INPUT. When
    truncation happens, logs at WARNING on the 1st hit and every Nth hit so a
    bulk backfill through long transcripts is visible without flooding logs —
    previously the slice was silent, so operators had no way to correlate a
    recall drop on long inputs with this ceiling.
    """
    global _embedding_truncation_count
    stripped = text.strip() if text else ""
    if not stripped:
        return "."
    if len(stripped) > EMBEDDINGS_MAX_CHARS_PER_INPUT:
        _embedding_truncation_count += 1
        if (
            _embedding_truncation_count == 1
            or _embedding_truncation_count % _EMBEDDING_TRUNCATION_LOG_EVERY == 0
        ):
            logger.warning(
                "[RAG] truncating embedding input: %d chars -> %d chars "
                "(truncation #%d — recall on long inputs is capped; consider "
                "pre-chunking)",
                len(stripped),
                EMBEDDINGS_MAX_CHARS_PER_INPUT,
                _embedding_truncation_count,
            )
        return stripped[:EMBEDDINGS_MAX_CHARS_PER_INPUT]
    return stripped


async def generate_embeddings(texts: List[str]) -> List[List[float]]:
    """Generate embeddings for a list of texts using OpenAI.

    Splits the input into sub-batches bounded by OpenAI's per-request caps
    (2048 inputs, ~300k tokens) so large backfills don't 400 on size. Transient
    429/5xx and network errors retry with exponential backoff + jitter. Each
    response is validated to match EMBEDDING_DIM — mismatched dims raise
    before any row is written.

    Returns an empty list when OPENAI_API_KEY is unset (soft no-op).
    """
    if not OPENAI_API_KEY:
        global _EMBEDDINGS_DISABLED_WARNED
        if not _EMBEDDINGS_DISABLED_WARNED:
            logger.warning(
                "[RAG] OPENAI_API_KEY not configured — embeddings disabled. "
                "RAG retrieval/ingestion will no-op until a key is set."
            )
            _EMBEDDINGS_DISABLED_WARNED = True
        record_skip(
            type="rag.skip",
            reason="openai_key_missing",
            metadata={"input_count": len(texts) if texts else 0},
        )
        return []

    if not texts:
        return []

    cleaned = [_prepare_embedding_input(t) for t in texts]

    async with traced_call(
        "openai.embeddings",
        request={
            "model": EMBEDDING_MODEL,
            "input_count": len(cleaned),
            "input_chars": sum(len(t) for t in cleaned),
            "input_preview": cleaned[0][:300] if cleaned else "",
            "dimensions": EMBEDDING_DIM,
        },
        metadata={"model": EMBEDDING_MODEL},
    ) as t:
        batches = _batch_embedding_inputs(cleaned)
        all_embeddings: List[List[float]] = []
        total = len(batches)
        for idx, batch in enumerate(batches, 1):
            embeds = await _embed_batch_with_retry(batch)
            all_embeddings.extend(embeds)
            logger.info(
                f"[RAG] Embedded batch {idx}/{total} "
                f"({len(batch)} inputs, {sum(len(t) for t in batch)} chars, "
                f"running total {len(all_embeddings)}/{len(cleaned)})"
            )
        if t:
            t["response"] = {
                "embedding_count": len(all_embeddings),
                "dimensions": len(all_embeddings[0]) if all_embeddings else 0,
                "batches": total,
            }
        return all_embeddings


# Cache query embeddings at request scope — the same query_text is reused across
# the 4 retrieve_context fan-out calls in get_email_context, so without a cache
# we would pay 4x OpenAI /embeddings round-trips per email. Embeddings are
# deterministic per model version, so a 1h TTL is safe: it only needs to outlive
# a single email-generation burst, and it auto-invalidates if EMBEDDING_MODEL
# ever changes (the model name is part of the key).
QUERY_EMBEDDING_CACHE_TTL_SECONDS = 3600


def _query_embedding_cache_key(query_text: str) -> str:
    digest = hashlib.sha256(
        f"{EMBEDDING_MODEL}\x00{query_text}".encode("utf-8")
    ).hexdigest()
    return f"rag:qemb:{digest}"


async def get_query_embedding(query_text: str) -> Optional[List[float]]:
    """Return an embedding for query_text, using a Redis cache to dedupe calls.

    Returns None when the embedding cannot be produced (no API key, upstream
    error). Callers should treat None the same way they would an empty result
    from generate_embeddings: skip retrieval rather than raise.
    """
    if not query_text:
        return None

    cache_key = _query_embedding_cache_key(query_text)
    cached = cache_get(cache_key)
    if cached and isinstance(cached, list) and len(cached) == EMBEDDING_DIM:
        return cached

    embeddings = await generate_embeddings([query_text])
    if not embeddings:
        return None
    vector = embeddings[0]
    cache_set(cache_key, vector, ttl=QUERY_EMBEDDING_CACHE_TTL_SECONDS)
    return vector


def _batch_embedding_inputs(texts: List[str]) -> List[List[str]]:
    """Split texts into sub-batches under OpenAI's input count and char-budget caps."""
    batches: List[List[str]] = []
    current: List[str] = []
    current_chars = 0
    for t in texts:
        t_len = len(t)
        would_overflow = (
            len(current) >= EMBEDDINGS_MAX_INPUTS_PER_REQUEST
            or (current and current_chars + t_len > EMBEDDINGS_MAX_CHARS_PER_REQUEST)
        )
        if would_overflow:
            batches.append(current)
            current, current_chars = [], 0
        current.append(t)
        current_chars += t_len
    if current:
        batches.append(current)
    return batches


def _embeddings_backoff(attempt: int) -> float:
    """Full-jitter exponential backoff, capped at EMBEDDINGS_BACKOFF_CAP_SECONDS."""
    base = min(EMBEDDINGS_BACKOFF_CAP_SECONDS, 2.0 ** (attempt - 1))
    return random.uniform(0, base)


async def _embed_batch_with_retry(batch: List[str]) -> List[List[float]]:
    """POST one batch to /v1/embeddings, retrying on 429/5xx/network errors."""
    last_exc: Optional[Exception] = None
    async with httpx.AsyncClient(timeout=60.0) as client:
        for attempt in range(1, EMBEDDINGS_MAX_ATTEMPTS + 1):
            try:
                response = await client.post(
                    "https://api.openai.com/v1/embeddings",
                    headers={
                        "Authorization": f"Bearer {OPENAI_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": EMBEDDING_MODEL,
                        "input": batch,
                        "dimensions": EMBEDDING_DIM,
                    },
                )
                response.raise_for_status()
                data = response.json()
                embeddings_data = sorted(data["data"], key=lambda x: x["index"])
                result = [item["embedding"] for item in embeddings_data]
                for i, vec in enumerate(result):
                    if len(vec) != EMBEDDING_DIM:
                        raise RuntimeError(
                            f"OpenAI returned embedding dim {len(vec)} for input {i}; "
                            f"expected {EMBEDDING_DIM}. Check EMBEDDING_MODEL and the "
                            f"content_embeddings.embedding column type "
                            f"(vector({EMBEDDING_DIM}))."
                        )
                return result
            except httpx.HTTPStatusError as e:
                status = e.response.status_code
                retryable = status == 429 or 500 <= status < 600
                last_exc = e
                if not retryable or attempt == EMBEDDINGS_MAX_ATTEMPTS:
                    # Never log e.response.text — on 400s the body echoes the
                    # submitted input (transcript/email text) verbatim.
                    logger.error(
                        f"OpenAI embeddings API error: {_sanitize_openai_error(e)}"
                    )
                    raise RuntimeError(
                        f"OpenAI embeddings API error: {status}"
                    ) from e
                delay = _embeddings_backoff(attempt)
                logger.warning(
                    f"[RAG] OpenAI {status} on batch of {len(batch)} inputs "
                    f"(attempt {attempt}/{EMBEDDINGS_MAX_ATTEMPTS}); "
                    f"retrying in {delay:.1f}s"
                )
                await asyncio.sleep(delay)
            except httpx.RequestError as e:
                last_exc = e
                if attempt == EMBEDDINGS_MAX_ATTEMPTS:
                    logger.error(f"OpenAI embeddings network error: {e}")
                    raise RuntimeError(
                        f"OpenAI embeddings network error: {e}"
                    ) from e
                delay = _embeddings_backoff(attempt)
                logger.warning(
                    f"[RAG] OpenAI network error on batch of {len(batch)} inputs "
                    f"(attempt {attempt}/{EMBEDDINGS_MAX_ATTEMPTS}); "
                    f"retrying in {delay:.1f}s: {e}"
                )
                await asyncio.sleep(delay)
    raise RuntimeError(f"Failed to generate embeddings: {last_exc}")


# --- Storage ---

async def store_embeddings(
    db: Session,
    account_id: int,
    source_type: str,
    source_id: str,
    chunks: List[str],
    contact_id: Optional[int] = None,
    org_id: Optional[int] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> int:
    """Chunk text, generate embeddings, and store in content_embeddings table.

    Uses upsert semantics via the UNIQUE(source_type, source_id, chunk_index) constraint.

    Args:
        db: Database session.
        account_id: Account owning this content.
        source_type: Type of source (resource, text_gen_output, transcript_chunk, etc.).
        source_id: Identifier for the source (e.g., "resource:42").
        chunks: Pre-chunked text segments.
        contact_id: Optional contact association.
        org_id: Optional organization association.
        metadata: Optional JSONB metadata.

    Returns:
        Number of embeddings stored.
    """
    if not chunks:
        return 0

    try:
        embeddings = await generate_embeddings(chunks)
    except Exception as e:
        logger.error(f"Failed to generate embeddings for {source_type}:{source_id}: {e}")
        return 0

    # Soft-degrade: when OPENAI_API_KEY is absent, generate_embeddings returns [].
    # Skip the write rather than persisting rows with NULL vectors.
    if not embeddings:
        return 0

    # Postgres-native upsert keyed on the uq_embedding_source_chunk unique
    # constraint (source_type, source_id, chunk_index). A prior implementation
    # read-then-wrote in a loop, which let two concurrent ingestions of the
    # same source_id (e.g. webhook retry + backfill) both SELECT a miss, both
    # INSERT, and the second commit raise IntegrityError — rolling back every
    # chunk added in the session, not just the conflicting row. ON CONFLICT
    # DO UPDATE is atomic per-row and race-safe.
    table = models.ContentEmbedding.__table__
    values = [
        {
            "account_id": account_id,
            "source_type": source_type,
            "source_id": source_id,
            "contact_id": contact_id,
            "org_id": org_id,
            "chunk_text": chunk,
            "chunk_index": i,
            "embedding": embedding,
            "metadata": metadata,
        }
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings))
    ]

    stmt = pg_insert(table).values(values)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_embedding_source_chunk",
        set_={
            "chunk_text": stmt.excluded.chunk_text,
            "embedding": stmt.excluded.embedding,
            "metadata": stmt.excluded.metadata,
            "contact_id": stmt.excluded.contact_id,
            "org_id": stmt.excluded.org_id,
        },
    )
    db.execute(stmt)
    db.commit()

    stored = len(values)
    logger.info(f"Stored {stored} embeddings for {source_type}:{source_id}")
    return stored


async def store_resource(
    db: Session,
    account_id: int,
    resource_id: int,
    text_content: str,
    resource_label: str = "",
) -> int:
    """Store a resource's text content as embeddings.

    Called after a resource is uploaded/saved. Chunks the text and embeds it.
    Resources are account-level (contact_id=NULL).

    Args:
        db: Database session.
        account_id: Account owning the resource.
        resource_id: Resource ID.
        text_content: Extracted text from the resource (PDF or link content).
        resource_label: Human-readable label for metadata.

    Returns:
        Number of chunks stored.
    """
    source_id = f"resource:{resource_id}"
    chunks = chunk_text(text_content)

    if not chunks:
        logger.warning(f"No text to embed for resource {resource_id}")
        return 0

    metadata = {
        "resource_id": resource_id,
        "resource_label": resource_label,
    }

    return await store_embeddings(
        db=db,
        account_id=account_id,
        source_type="resource",
        source_id=source_id,
        chunks=chunks,
        contact_id=None,
        org_id=None,
        metadata=metadata,
    )


async def store_text_gen_output(
    db: Session,
    account_id: int,
    execution_id: int,
    extracted_information: Dict[str, Any],
    contact_id: Optional[int] = None,
    org_id: Optional[int] = None,
    meeting_date: Optional[str] = None,
) -> int:
    """Embed structured Text Gen output by field group.

    Each non-empty field group becomes one embedding with source_type="text_gen_output".

    Returns:
        Number of embeddings stored.
    """
    field_groups = chunk_structured_output(extracted_information)
    if not field_groups:
        return 0

    chunks = [text_content for _, text_content in field_groups]
    field_names = [field_group for field_group, _ in field_groups]

    source_id = f"execution:{execution_id}"
    metadata = {
        "execution_id": execution_id,
        "field_groups": field_names,
        "meeting_date": meeting_date,
    }

    return await store_embeddings(
        db=db,
        account_id=account_id,
        source_type="text_gen_output",
        source_id=source_id,
        chunks=chunks,
        contact_id=contact_id,
        org_id=org_id,
        metadata=metadata,
    )


async def store_transcript_chunks(
    db: Session,
    account_id: int,
    execution_id: int,
    transcript: str,
    contact_id: Optional[int] = None,
    org_id: Optional[int] = None,
    meeting_date: Optional[str] = None,
) -> int:
    """Embed raw transcript as overlapping chunks (fallback retrieval layer).

    Returns:
        Number of chunks stored.
    """
    chunks = chunk_text(transcript)
    if not chunks:
        return 0

    source_id = f"transcript:{execution_id}"
    metadata = {
        "execution_id": execution_id,
        "meeting_date": meeting_date,
    }

    return await store_embeddings(
        db=db,
        account_id=account_id,
        source_type="transcript_chunk",
        source_id=source_id,
        chunks=chunks,
        contact_id=contact_id,
        org_id=org_id,
        metadata=metadata,
    )


# --- Retrieval ---

async def retrieve_context(
    db: Session,
    query_text: str,
    account_id: int,
    source_types: Optional[List[str]] = None,
    contact_id: Optional[int] = None,
    org_id: Optional[int] = None,
    limit: Optional[int] = None,
    similarity_threshold: Optional[float] = None,
    penalize_ids: Optional[List[int]] = None,
    penalty_multiplier: float = 1.0,
    since: Optional[datetime] = None,
    query_vector: Optional[List[float]] = None,
    exclude_contact_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Retrieve relevant content chunks by cosine similarity.

    When limit/similarity_threshold are omitted, values are resolved from
    SystemConfig (rag.max_retrieval_results, rag.similarity_threshold).

    Callers that fan out multiple retrievals against the same query should
    pre-compute the embedding via get_query_embedding() and pass it as
    query_vector to avoid re-embedding on every call.
    """
    if limit is None:
        limit = get_max_retrieval_results(db)
    if similarity_threshold is None:
        similarity_threshold = get_similarity_threshold(db)

    started_at = time.perf_counter()

    async with traced_call(
        "rag.retrieve_context",
        request={
            "query_text": query_text,
            "account_id": account_id,
            "source_types": source_types,
            "contact_id": contact_id,
            "org_id": org_id,
            "limit": limit,
            "similarity_threshold": similarity_threshold,
            "exclude_contact_id": exclude_contact_id,
            "penalize_ids": penalize_ids,
            "penalty_multiplier": penalty_multiplier,
        },
        metadata={"limit": limit, "similarity_threshold": similarity_threshold},
    ) as t:
        if query_vector is not None:
            query_embedding = query_vector
        else:
            try:
                query_embedding = await get_query_embedding(query_text)
            except Exception as e:
                logger.error(f"Failed to generate query embedding: {e}")
                query_embedding = None

            if query_embedding is None:
                asyncio.create_task(
                    _dispatch_latency_record(account_id, started_at, 0)
                )
                if t:
                    t["response"] = {"results": [], "reason": "no query embedding"}
                return []

        # Build the SQL query using pgvector cosine distance
        # cosine_distance = 1 - cosine_similarity, so we use <=> operator and convert
        embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

        where_clauses = ["account_id = :account_id"]
        params: Dict[str, Any] = {"account_id": account_id, "limit": limit}

        if source_types:
            where_clauses.append("source_type = ANY(:source_types)")
            params["source_types"] = source_types

        if contact_id is not None:
            where_clauses.append("contact_id = :contact_id")
            params["contact_id"] = contact_id

        if org_id is not None:
            where_clauses.append("(org_id = :org_id OR org_id IS NULL)")
            params["org_id"] = org_id

        if exclude_contact_id is not None:
            where_clauses.append(
                "(contact_id IS NULL OR contact_id <> :exclude_contact_id)"
            )
            params["exclude_contact_id"] = exclude_contact_id

        if since is not None:
            where_clauses.append("created_at >= :since")
            params["since"] = since

        where_sql = " AND ".join(where_clauses)

        fetch_limit = limit * 3 if penalize_ids else limit
        sql = text(f"""
            SELECT
                id,
                source_type,
                source_id,
                chunk_text,
                chunk_index,
                metadata,
                1 - (embedding <=> CAST(:query_embedding AS vector)) AS similarity
            FROM content_embeddings
            WHERE {where_sql}
              AND 1 - (embedding <=> CAST(:query_embedding AS vector)) >= :threshold
            ORDER BY embedding <=> CAST(:query_embedding AS vector)
            LIMIT :fetch_limit
        """)
        params["query_embedding"] = embedding_str
        params["threshold"] = similarity_threshold
        params["fetch_limit"] = fetch_limit

        try:
            ef_search = int(get_hnsw_ef_search(db))
            if not 10 <= ef_search <= 1000:
                raise ValueError(f"ef_search out of range: {ef_search}")
            db.execute(text(f"SET LOCAL hnsw.ef_search = {ef_search}"))
        except Exception as e:
            logger.debug(f"Could not SET LOCAL hnsw.ef_search: {e}")

        try:
            rows = db.execute(sql, params).mappings().all()
        except Exception as e:
            logger.error(f"RAG retrieval query failed: {e}")
            # Roll back so callers can keep using the same session for
            # subsequent writes. Without this the transaction stays aborted
            # and every later query dies with InFailedSqlTransaction.
            try:
                db.rollback()
            except Exception as rb_err:
                logger.warning(f"RAG retrieval rollback failed: {rb_err}")
            asyncio.create_task(
                _dispatch_latency_record(account_id, started_at, 0)
            )
            if t:
                t["error"] = f"pgvector query failed: {e}"
                t["response"] = {"results": [], "reason": "query failed"}
            return []

        results = [
            {
                "id": row["id"],
                "source_type": row["source_type"],
                "source_id": row["source_id"],
                "chunk_text": row["chunk_text"],
                "chunk_index": row["chunk_index"],
                "metadata": row["metadata"],
                "similarity": float(row["similarity"]),
            }
            for row in rows
        ]

        if penalize_ids and penalty_multiplier != 1.0:
            penalize_set = set(penalize_ids)
            for r in results:
                if r["id"] in penalize_set:
                    r["similarity"] = r["similarity"] * penalty_multiplier
                    r["_penalized"] = True
            results.sort(key=lambda x: x["similarity"], reverse=True)

        final_results = results[:limit]
        asyncio.create_task(
            _dispatch_latency_record(account_id, started_at, len(final_results))
        )
        if t:
            # Include a slim per-result view: chunk preview + score.
            t["response"] = {
                "result_count": len(final_results),
                "results": [
                    {
                        "id": r["id"],
                        "source_type": r["source_type"],
                        "source_id": r["source_id"],
                        "chunk_index": r["chunk_index"],
                        "similarity": r["similarity"],
                        "chunk_preview": (r["chunk_text"] or "")[:400],
                    }
                    for r in final_results
                ],
            }
        return final_results


# Cap concurrent latency inserts so observability can never starve the DB pool.
# get_email_context fans out ~4 retrieve_context calls per email; without a bound,
# bursty traffic (e.g. 20 concurrent emails) holds up to 80 connections purely
# for logging. 4 keeps in-flight inserts well under SessionLocal's pool_size.
_LATENCY_SEMAPHORE_LIMIT = 4
_LATENCY_MAX_PENDING = _LATENCY_SEMAPHORE_LIMIT * 2
_latency_insert_semaphore: Optional[asyncio.Semaphore] = None
_latency_pending_count = 0

# Track failure count so a broken rag_retrieval_log surfaces at WARNING without
# flooding logs on every retrieval. We warn on the 1st failure and every 100th
# thereafter, and reset the counter on the next success so transient outages
# re-warn instead of staying silent.
_LATENCY_WRITE_FAILURE_LOG_EVERY = 100
_latency_write_failure_count = 0


def _get_latency_semaphore() -> asyncio.Semaphore:
    global _latency_insert_semaphore
    if _latency_insert_semaphore is None:
        _latency_insert_semaphore = asyncio.Semaphore(_LATENCY_SEMAPHORE_LIMIT)
    return _latency_insert_semaphore


async def _dispatch_latency_record(
    account_id: Optional[int],
    started_at: float,
    result_count: int,
) -> None:
    """Run the latency insert under a bounded semaphore, off the event loop.

    Shed samples when the backlog is large rather than letting tasks queue
    without bound — under sustained overload, dropping latency samples is
    strictly preferable to starving the DB pool that serves real traffic.
    """
    global _latency_pending_count
    if _latency_pending_count >= _LATENCY_MAX_PENDING:
        logger.debug("RAG latency logger saturated; dropping sample")
        return
    _latency_pending_count += 1
    try:
        async with _get_latency_semaphore():
            await asyncio.get_running_loop().run_in_executor(
                None, _record_retrieval_latency, account_id, started_at, result_count
            )
    finally:
        _latency_pending_count -= 1


def _record_retrieval_latency(
    account_id: Optional[int],
    started_at: float,
    result_count: int,
) -> None:
    """Persist per-call retrieval latency for the admin observability dashboard.

    Uses an isolated session so a commit here can't interfere with the caller's
    transaction. Best-effort: failures must never break the retrieval path.

    Synchronous by design: async callers (retrieve_context) must dispatch this
    via _dispatch_latency_record so the commit does not block the event loop
    and in-flight inserts stay bounded. TODO: migrate to a Redis-buffered flush
    in batch_worker.py (option C) if rag_retrieval_log volume outgrows the
    in-process semaphore.
    """
    global _latency_write_failure_count
    latency_ms = int((time.perf_counter() - started_at) * 1000)
    session = SessionLocal()
    try:
        session.execute(
            text(
                "INSERT INTO rag_retrieval_log (account_id, latency_ms, result_count) "
                "VALUES (:account_id, :latency_ms, :result_count)"
            ),
            {
                "account_id": account_id,
                "latency_ms": latency_ms,
                "result_count": result_count,
            },
        )
        session.commit()
        if _latency_write_failure_count:
            logger.warning(
                "RAG retrieval latency logging recovered after %d failed writes",
                _latency_write_failure_count,
            )
            _latency_write_failure_count = 0
    except Exception:
        _latency_write_failure_count += 1
        if (
            _latency_write_failure_count == 1
            or _latency_write_failure_count % _LATENCY_WRITE_FAILURE_LOG_EVERY == 0
        ):
            logger.warning(
                "Failed to record RAG retrieval latency (failure #%d) — observability write path is broken",
                _latency_write_failure_count,
                exc_info=True,
            )
        try:
            session.rollback()
        except Exception:
            pass
    finally:
        session.close()


def deduplicate_results(
    results: List[Dict[str, Any]],
    jaccard_threshold: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """Remove near-duplicate chunks from retrieval results.

    Dedupes by source_id (keeping highest similarity per source) and by word
    Jaccard overlap. Threshold defaults to SystemConfig rag.dedup_jaccard_threshold
    so ops can tune without a deploy; 0.6 is the seeded default and preserves
    legitimate repeated concepts that a 0.8 cut would drop.
    """
    if not results:
        return []

    if jaccard_threshold is None:
        jaccard_threshold = get_dedup_jaccard_threshold()

    best_per_source: Dict[str, Dict[str, Any]] = {}
    for r in results:
        sid = r["source_id"]
        if sid not in best_per_source or r["similarity"] > best_per_source[sid]["similarity"]:
            best_per_source[sid] = r

    deduped = list(best_per_source.values())

    final = []
    for candidate in sorted(deduped, key=lambda x: x["similarity"], reverse=True):
        candidate_words = set(candidate["chunk_text"].lower().split())
        is_dup = False
        for accepted in final:
            accepted_words = set(accepted["chunk_text"].lower().split())
            if not candidate_words or not accepted_words:
                continue
            intersection = len(candidate_words & accepted_words)
            union = len(candidate_words | accepted_words)
            if union > 0 and intersection / union > jaccard_threshold:
                is_dup = True
                break
        if not is_dup:
            final.append(candidate)

    return final


async def smart_retrieve(
    db: Session,
    query_text: str,
    account_id: int,
    source_types: Optional[List[str]] = None,
    contact_id: Optional[int] = None,
    org_id: Optional[int] = None,
    limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Intelligent retrieval that prefers structured results over raw transcript chunks.

    Limit, similarity threshold, structured-preference, and the boost applied
    to structured chunks are all resolved from SystemConfig so operators can
    A/B tune retrieval without a deploy."""
    if limit is None:
        limit = get_max_retrieval_results(db)
    structured_pref = get_structured_preference(db)
    structured_boost = get_structured_preference_boost(db)

    results = await retrieve_context(
        db=db,
        query_text=query_text,
        account_id=account_id,
        source_types=source_types,
        contact_id=contact_id,
        org_id=org_id,
        limit=limit * 2,
        similarity_threshold=get_similarity_threshold(db),
    )

    if not results:
        return []

    for r in results:
        if r["source_type"] in ("text_gen_output", "resource"):
            if r["similarity"] >= structured_pref:
                r["_adjusted_similarity"] = r["similarity"] + structured_boost
            else:
                r["_adjusted_similarity"] = r["similarity"]
        else:
            r["_adjusted_similarity"] = r["similarity"]

    # Sort by adjusted similarity
    results.sort(key=lambda x: x["_adjusted_similarity"], reverse=True)

    # Deduplicate
    deduped = deduplicate_results(results)

    # Clean up internal field and limit
    for r in deduped:
        r.pop("_adjusted_similarity", None)

    return deduped[:limit]


# --- Contact Briefing (Phase 3) ---

async def get_contact_briefing(
    db: Session,
    account_id: int,
    contact_id: int,
    org_id: Optional[int] = None,
    query_context: str = "",
) -> Optional[str]:
    """Build a relationship context briefing for a contact from historical embeddings."""
    if is_tracing():
        async with traced_call(
            "rag.get_contact_briefing",
            request={
                "account_id": account_id,
                "contact_id": contact_id,
                "org_id": org_id,
                "query_context": query_context,
            },
        ) as t:
            result = await _get_contact_briefing_impl(db, account_id, contact_id, org_id, query_context)
            if t:
                t["response"] = {
                    "has_briefing": result is not None,
                    "briefing_chars": len(result) if result else 0,
                    "briefing_preview": (result or "")[:1000],
                }
            return result
    return await _get_contact_briefing_impl(db, account_id, contact_id, org_id, query_context)


async def _get_contact_briefing_impl(
    db: Session,
    account_id: int,
    contact_id: int,
    org_id: Optional[int],
    query_context: str,
) -> Optional[str]:
    source_types = ["text_gen_output", "activity", "generated_email", "transcript_chunk"]

    # Check what historical signal we have for this contact AND their org. We
    # gate on the union: a brand-new individual contact at a known org
    # (e.g. a different person at the same company) is a real and common case
    # — we should still produce a briefing using sibling-contact and org-level
    # chunks rather than declare "no history".
    contact_count = db.query(models.ContentEmbedding).filter(
        and_(
            models.ContentEmbedding.account_id == account_id,
            models.ContentEmbedding.contact_id == contact_id,
            models.ContentEmbedding.source_type.in_(source_types),
        )
    ).count()

    org_count = 0
    if org_id:
        org_count = db.query(models.ContentEmbedding).filter(
            and_(
                models.ContentEmbedding.account_id == account_id,
                models.ContentEmbedding.org_id == org_id,
                models.ContentEmbedding.source_type.in_(source_types),
            )
        ).count()

    if contact_count == 0 and org_count == 0:
        logger.info(
            f"No historical embeddings for contact {contact_id} or org {org_id}, skipping briefing"
        )
        record_skip(
            type="rag.skip",
            reason="contact_has_no_history",
            metadata={
                "contact_id": contact_id,
                "account_id": account_id,
                "org_id": org_id,
            },
        )
        return None

    # Use the current meeting context as the query, or a generic one
    query = query_context if query_context else "relationship history and prior meeting context"

    # Retrieve contact-level context (may be empty; that's fine, org fallback follows)
    contact_results: List[Dict[str, Any]] = []
    if contact_count > 0:
        contact_results = await smart_retrieve(
            db=db,
            query_text=query,
            account_id=account_id,
            source_types=source_types,
            contact_id=contact_id,
            limit=5,
        )

    # Retrieve org-level context whenever we have an org. We widen the source
    # types vs the old behaviour (which only included text_gen_output) so a
    # never-met-this-person-but-known-company case still surfaces real prior
    # meeting transcripts and emails rather than just structured summaries.
    # When the contact has no history, we lean harder on org context (limit 5
    # instead of 3) and explicitly exclude the current contact's own rows
    # (there are none, but it's cheap insurance against schema drift).
    org_results: List[Dict[str, Any]] = []
    if org_count > 0:
        org_limit = 5 if contact_count == 0 else 3
        org_results = await smart_retrieve(
            db=db,
            query_text=query,
            account_id=account_id,
            source_types=["text_gen_output", "transcript_chunk", "generated_email"],
            org_id=org_id,
            limit=org_limit,
        )

    # Combine and deduplicate
    all_results = contact_results + org_results
    if not all_results:
        record_skip(
            type="rag.skip",
            reason="briefing_returned_empty",
            metadata={"contact_id": contact_id, "account_id": account_id, "org_id": org_id},
        )
        return None

    deduped = deduplicate_results(all_results)
    if not deduped:
        record_skip(
            type="rag.skip",
            reason="briefing_returned_empty",
            metadata={"contact_id": contact_id, "account_id": account_id, "org_id": org_id},
        )
        return None

    # Format the briefing
    sections = []
    for r in deduped:
        source_label = {
            "text_gen_output": "Prior Meeting Analysis",
            "transcript_chunk": "Prior Meeting Transcript",
            "activity": "Contact Activity",
            "generated_email": "Previous Email",
        }.get(r["source_type"], r["source_type"])

        meeting_date = ""
        if r.get("metadata") and isinstance(r["metadata"], dict):
            md = r["metadata"].get("meeting_date")
            if md:
                meeting_date = f" ({md})"

        sections.append(f"[{source_label}{meeting_date}]\n{r['chunk_text']}")

    briefing = "\n\n".join(sections)
    return briefing


# --- Resource Retrieval for Email (Phase 2) ---

async def retrieve_resource_context(
    db: Session,
    account_id: int,
    query_text: str,
    limit: int = MAX_RETRIEVAL_RESULTS,
) -> Optional[str]:
    """Retrieve relevant resource chunks for email generation.

    Queries pgvector for resource embeddings relevant to the email's purpose.
    Returns a formatted RELEVANT RESOURCES block, or None if nothing found.

    Args:
        db: Database session.
        account_id: Account scope.
        query_text: Query built from email purpose + key_topics.
        limit: Max chunks to retrieve.

    Returns:
        Formatted RELEVANT RESOURCES block string, or None.
    """
    results = await retrieve_context(
        db=db,
        query_text=query_text,
        account_id=account_id,
        source_types=["resource"],
        limit=limit,
    )

    if not results:
        return None

    deduped = deduplicate_results(results)
    if not deduped:
        return None

    sections = []
    for r in deduped:
        label = ""
        if r.get("metadata") and isinstance(r["metadata"], dict):
            label = r["metadata"].get("resource_label", "")
        source_label = f" ({label})" if label else ""
        sections.append(f"[Resource{source_label}]\n{r['chunk_text']}")

    block = "\n\n".join(sections)
    return block


# --- PDF Text Extraction ---

# Hard byte cap for PDF extraction. PyPDF2/pdfplumber copy the stream into
# memory as they parse, so a 1GB PDF — whether real or a hostile upload —
# would blow the upload worker's RSS. 50MB is well above legitimate sales
# collateral while keeping peak RSS bounded. Anything bigger is rejected
# before parse rather than discovered via OOMKiller.
PDF_MAX_BYTES = 50 * 1024 * 1024
# The regex fallback decodes raw bytes to Latin-1, which allocates a string
# of equal length. Bounding the decoded slice keeps the allocation small
# even if the outer size cap is ever raised.
PDF_REGEX_FALLBACK_MAX_BYTES = 2 * 1024 * 1024


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extract text content from a PDF file.

    Tries PyPDF2, then pdfplumber, then a regex fallback. Logs which method
    succeeded and the extracted character count so we can diagnose empty/thin
    uploads without re-fetching the PDF.

    Hardening against hostile uploads:
      * Rejects inputs above ``PDF_MAX_BYTES`` before touching any parser so
        a compression-bomb / giant-PDF can't drive the worker OOM.
      * The regex fallback decodes at most ``PDF_REGEX_FALLBACK_MAX_BYTES``
        to avoid a second-order allocation on large inputs.
      * Every parser branch is wrapped in ``except Exception`` — PyPDF2 has
        historically raised miscellaneous exceptions on malformed / deeply-
        nested PDFs; we catch them, log once, and fall through so a bad PDF
        never takes down an upload.
    """
    if not pdf_bytes:
        return ""
    if len(pdf_bytes) > PDF_MAX_BYTES:
        logger.warning(
            "Rejecting PDF above size cap: %d bytes > %d",
            len(pdf_bytes), PDF_MAX_BYTES,
        )
        return ""

    method = None
    text_out = ""

    try:
        from PyPDF2 import PdfReader
        import io
        reader = PdfReader(io.BytesIO(pdf_bytes))
        text_parts = [p.extract_text() for p in reader.pages if p.extract_text()]
        if text_parts:
            text_out = "\n\n".join(text_parts)
            method = "PyPDF2"
    except ImportError:
        pass
    except Exception as e:
        logger.warning(f"PyPDF2 extraction failed, will try fallbacks: {e}")

    if not text_out:
        try:
            import pdfplumber
            import io
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                text_parts = [p.extract_text() for p in pdf.pages if p.extract_text()]
                if text_parts:
                    text_out = "\n\n".join(text_parts)
                    method = "pdfplumber"
        except ImportError:
            pass
        except Exception as e:
            logger.warning(f"pdfplumber extraction failed, will try regex fallback: {e}")

    if not text_out:
        try:
            # Decode only the capped prefix so a 50MB PDF doesn't allocate a
            # 50MB Latin-1 string just to be sliced to 10k chars at the end.
            prefix = pdf_bytes[:PDF_REGEX_FALLBACK_MAX_BYTES]
            raw_text = prefix.decode("latin-1", errors="ignore")
            # Cap regex fallback output at 10k chars — it's a last-resort and
            # tends to pick up binary garbage if we don't bound it.
            text_out = " ".join(re.findall(r'\((.*?)\)', raw_text))[:10000]
            method = "regex_fallback"
        except Exception as e:
            logger.error(f"All PDF extraction methods failed: {e}")
            return ""

    char_count = len(text_out)
    if char_count < 100:
        logger.warning(
            f"PDF extraction via {method} returned only {char_count} chars — "
            "likely a scanned/image-only PDF"
        )
    else:
        logger.info(f"PDF extraction via {method}: {char_count} chars")
    return text_out


# --- Phase 4: Generated email embedding + multi-block email context ---

async def store_generated_email(
    account_id: int,
    email_queue_id: int,
    subject: str,
    body: str,
    contact_id: Optional[int] = None,
    org_id: Optional[int] = None,
    sequence_run_id: Optional[int] = None,
    workflow_id: Optional[int] = None,
) -> int:
    """Embed a generated email as a single chunk: subject + first ~100 words of body.

    We intentionally do NOT embed the full body — the opening is the highest-signal
    part for determining what was already discussed with this contact.

    Opens a dedicated SessionLocal() for the write. store_embeddings() commits,
    and passing the caller's execution session in would flush any uncommitted
    mutations on it — breaking transaction atomicity for the surrounding
    execute_email flow. Mirrors contacts_service._schedule_activity_embedding.
    """
    if not subject and not body:
        return 0

    # Strip HTML so we don't embed markup noise
    plain_body = re.sub(r"<[^>]+>", " ", body or "")
    plain_body = re.sub(r"\s+", " ", plain_body).strip()
    first_100_words = " ".join(plain_body.split()[:100])

    snippet = f"Subject: {subject or ''}\n\n{first_100_words}".strip()
    if not snippet:
        return 0

    source_id = f"email:{email_queue_id}"
    metadata = {
        "email_queue_id": email_queue_id,
        "sequence_run_id": sequence_run_id,
        "workflow_id": workflow_id,
        "sent_at": datetime.now(timezone.utc).isoformat(),
    }

    session = SessionLocal()
    try:
        return await store_embeddings(
            db=session,
            account_id=account_id,
            source_type="generated_email",
            source_id=source_id,
            chunks=[snippet],
            contact_id=contact_id,
            org_id=org_id,
            metadata=metadata,
        )
    except Exception:
        try:
            session.rollback()
        except Exception:
            pass
        raise
    finally:
        session.close()


async def store_activity_summary(
    db: Session,
    account_id: int,
    source_type: str,
    source_id: str,
    summary: str,
    contact_id: Optional[int] = None,
    org_id: Optional[int] = None,
    occurred_at: Optional[datetime] = None,
) -> int:
    """Embed a human-readable activity/CRM summary.

    Used for the pre-send safety net: replies, deal stage changes, notes.
    source_type must be one of PRESEND_SOURCE_TYPES (typically "activity" or
    "crm_change" — see activity_source_type()).
    """
    if not summary or not summary.strip():
        return 0

    metadata = {
        "occurred_at": (occurred_at or datetime.now(timezone.utc)).isoformat(),
    }

    return await store_embeddings(
        db=db,
        account_id=account_id,
        source_type=source_type,
        source_id=source_id,
        chunks=[summary.strip()],
        contact_id=contact_id,
        org_id=org_id,
        metadata=metadata,
    )


# --- Phase 5 T2 producers: org_signal, cross_workflow, dnc (issue #175) ---
#
# All three producers open a fresh SessionLocal() and commit inside
# store_embeddings(). The caller's in-progress transaction is never
# touched — mirrors the session-isolation pattern in
# contacts_service._schedule_activity_embedding. Callers do `await
# emit_*(...)` without passing their own session.

async def _emit_tagged_embedding(
    *,
    account_id: int,
    tag: str,
    signal_text: str,
    source_id: str,
    contact_id: Optional[int],
    org_id: Optional[int],
    extra_metadata: Optional[Dict[str, Any]] = None,
    occurred_at: Optional[datetime] = None,
) -> int:
    """Internal helper for the T2 producers. Ensures the tag prefix is
    present, packages metadata, and writes via a fresh session."""
    from database import SessionLocal

    tagged = signal_text.strip()
    if not tagged.startswith(tag):
        tagged = f"{tag} {tagged}"

    metadata: Dict[str, Any] = {
        "occurred_at": (occurred_at or datetime.now(timezone.utc)).isoformat(),
    }
    if extra_metadata:
        metadata.update(extra_metadata)

    session = SessionLocal()
    try:
        return await store_embeddings(
            db=session,
            account_id=account_id,
            source_type="activity",
            source_id=source_id,
            chunks=[tagged],
            contact_id=contact_id,
            org_id=org_id,
            metadata=metadata,
        )
    except Exception as e:
        logger.warning(f"[RAG] T2 producer emit failed ({tag} / {source_id}): {e}")
        try:
            session.rollback()
        except Exception:
            pass
        return 0
    finally:
        session.close()


async def emit_org_signal(
    account_id: int,
    org_id: int,
    signal_text: str,
    source_id: str,
    originating_contact_id: Optional[int] = None,
    occurred_at: Optional[datetime] = None,
) -> int:
    """Emit an [org_signal] ContentEmbedding that sibling contacts at the
    same org will pick up in their pre-send snapshots.

    The row is written with contact_id = originating_contact_id so the
    existing snapshot filter (`contact_id != current OR IS NULL`) naturally
    excludes the originating contact from seeing an echo of their own
    signal, while every sibling at the same org_id sees it. Used by Fresh
    Check rule 5 on deal → Lost and on negative [reply] events.

    source_id must be stable across retries of the same event to dedupe
    (e.g. "org_signal:deal_lost:{deal_id}"). Caller's responsibility.
    """
    return await _emit_tagged_embedding(
        account_id=account_id,
        tag=FRESH_CHECK_TAG_ORG_SIGNAL,
        signal_text=signal_text,
        source_id=source_id,
        contact_id=originating_contact_id,
        org_id=org_id,
        extra_metadata={"originating_contact_id": originating_contact_id},
        occurred_at=occurred_at,
    )


async def emit_cross_workflow_signal(
    account_id: int,
    contact_id: int,
    workflow_id: int,
    signal_text: str,
    source_id: str,
    org_id: Optional[int] = None,
    occurred_at: Optional[datetime] = None,
) -> int:
    """Emit a [cross_workflow] ContentEmbedding keyed on contact_id so a
    reply in one workflow is visible to the same contact's pre-send check
    in a different workflow (Fresh Check rule 1).

    No live call sites exist yet — reply-ingestion has not landed in this
    branch. This helper is wired in advance so the inbox-sync / webhook PR
    can call it in one line. When reply-ingest lands, call this from the
    handler that records the reply, passing the originating workflow_id so
    T3's UI can surface which workflow the signal came from.
    """
    return await _emit_tagged_embedding(
        account_id=account_id,
        tag=FRESH_CHECK_TAG_CROSS_WORKFLOW,
        signal_text=signal_text,
        source_id=source_id,
        contact_id=contact_id,
        org_id=org_id,
        extra_metadata={"source_workflow_id": workflow_id},
        occurred_at=occurred_at,
    )


async def emit_dnc_signal(
    account_id: int,
    signal_text: str,
    source_id: str,
    contact_id: Optional[int] = None,
    org_id: Optional[int] = None,
    occurred_at: Optional[datetime] = None,
) -> int:
    """Emit a [dnc] ContentEmbedding on a DNC status flip (Fresh Check
    rule 8). The deterministic DB-flag short-circuit in
    _rag_presend_decision catches synced DNC state; this producer covers
    the case where the flip was observed via webhook but hasn't been
    written to contact.dnc_status / contact_organization.dnc_status yet,
    so T3's snapshot-based DNC scan still catches it.

    No live call sites exist yet — the DNC setter endpoints have not
    landed. When they do (whether via a CRM webhook handler or a manual
    flag endpoint), call this helper from the same handler that flips
    dnc_status so the two signals are consistent.
    """
    return await _emit_tagged_embedding(
        account_id=account_id,
        tag=FRESH_CHECK_TAG_DNC,
        signal_text=signal_text,
        source_id=source_id,
        contact_id=contact_id,
        org_id=org_id,
        occurred_at=occurred_at,
    )


async def get_email_context(
    db: Session,
    account_id: int,
    query_text: str,
    contact_id: Optional[int] = None,
    org_id: Optional[int] = None,
    sequence_run_id: Optional[int] = None,
    used_chunk_ids: Optional[List[int]] = None,
    apply_diversity: bool = True,
    limit_per_block: int = 5,
) -> Dict[str, Any]:
    """Build the four context blocks injected into every email prompt."""
    if is_tracing():
        async with traced_call(
            "rag.get_email_context",
            request={
                "account_id": account_id,
                "query_text": query_text,
                "contact_id": contact_id,
                "org_id": org_id,
                "sequence_run_id": sequence_run_id,
                "used_chunk_ids_count": len(used_chunk_ids) if used_chunk_ids else 0,
                "apply_diversity": apply_diversity,
                "limit_per_block": limit_per_block,
            },
        ) as t:
            result = await _get_email_context_impl(
                db, account_id, query_text, contact_id, org_id, sequence_run_id,
                used_chunk_ids, apply_diversity, limit_per_block,
            )
            if t:
                blocks = result.get("blocks", [])
                t["response"] = {
                    "block_count": len(blocks),
                    "block_headers": [b[0] if isinstance(b, (list, tuple)) and b else str(b) for b in blocks],
                    "used_chunk_ids": result.get("used_chunk_ids", []),
                    "formatted_chars": len(result.get("formatted", "") or ""),
                    "formatted_preview": (result.get("formatted") or "")[:1500],
                }
            return result
    return await _get_email_context_impl(
        db, account_id, query_text, contact_id, org_id, sequence_run_id,
        used_chunk_ids, apply_diversity, limit_per_block,
    )


async def _get_email_context_impl(
    db: Session,
    account_id: int,
    query_text: str,
    contact_id: Optional[int],
    org_id: Optional[int],
    sequence_run_id: Optional[int],
    used_chunk_ids: Optional[List[int]],
    apply_diversity: bool,
    limit_per_block: int,
) -> Dict[str, Any]:
    penalize = used_chunk_ids if apply_diversity else None
    penalty = _get_diversity_penalty(db) if apply_diversity else 1.0

    # Embed once for all 4 blocks — without this we issue 4 /embeddings calls
    # per email for the same query_text. get_query_embedding also caches across
    # emails via Redis so repeated variants (e.g. same contact, next sequence
    # step) usually hit the cache.
    shared_vector = await get_query_embedding(query_text)
    if shared_vector is None:
        return {"blocks": [], "used_chunk_ids": [], "formatted": None}

    async def _fetch(source_types, contact_filter=None, org_filter=None, exclude_contact=None):
        return await retrieve_context(
            db=db,
            query_text=query_text,
            account_id=account_id,
            source_types=source_types,
            contact_id=contact_filter,
            org_id=org_filter,
            limit=limit_per_block,
            penalize_ids=penalize,
            penalty_multiplier=penalty,
            query_vector=shared_vector,
            exclude_contact_id=exclude_contact,
        )

    # Fan out the 4 retrievals concurrently — they hit independent indexes and
    # don't depend on each other's results, so sequential await is pure latency.
    # The ORG block pushes "not the current contact" into the WHERE clause via
    # exclude_contact_id so we don't need a follow-up ContentEmbedding.id.in_()
    # query to strip duplicates of blocks 2/3.
    resources_task = _fetch(["resource"])
    previous_outreach_task = (
        _fetch(["generated_email"], contact_filter=contact_id)
        if contact_id
        else None
    )
    contact_history_task = (
        _fetch(["text_gen_output"], contact_filter=contact_id)
        if contact_id
        else None
    )
    org_results_task = (
        _fetch(
            ["text_gen_output", "generated_email"],
            org_filter=org_id,
            exclude_contact=contact_id,
        )
        if org_id
        else None
    )

    pending = [
        t for t in (resources_task, previous_outreach_task, contact_history_task, org_results_task)
        if t is not None
    ]
    gathered = await asyncio.gather(*pending) if pending else []
    results_iter = iter(gathered)
    resources = next(results_iter)
    previous_outreach: List[Dict[str, Any]] = (
        next(results_iter) if previous_outreach_task is not None else []
    )
    contact_history: List[Dict[str, Any]] = (
        next(results_iter) if contact_history_task is not None else []
    )
    org_results = next(results_iter) if org_results_task is not None else []

    # Org context — already pre-filtered in SQL via exclude_contact_id when a
    # contact_id is present.
    org_context: List[Dict[str, Any]] = list(org_results) if org_id else []

    # Dedupe each block and collect chunk ids
    blocks: List[Tuple[str, str]] = []
    collected_ids: List[int] = []

    def _format_block(header: str, results: List[Dict[str, Any]], label_map: Dict[str, str]) -> Optional[str]:
        if not results:
            return None
        deduped = deduplicate_results(results)[:limit_per_block]
        if not deduped:
            return None
        sections: List[str] = []
        for r in deduped:
            collected_ids.append(r["id"])
            label = label_map.get(r["source_type"], r["source_type"])
            date_str = ""
            md = r.get("metadata") or {}
            if isinstance(md, dict):
                d = md.get("meeting_date") or md.get("occurred_at") or md.get("sent_at")
                if d:
                    date_str = f" ({str(d)[:10]})"
            sections.append(f"[{label}{date_str}]\n{r['chunk_text']}")
        return "\n\n".join(sections)

    resource_labels = {"resource": "Resource"}
    email_labels = {"generated_email": "Previous Email"}
    history_labels = {"text_gen_output": "Prior Meeting Analysis"}
    org_labels = {"text_gen_output": "Org Meeting", "generated_email": "Org Previous Email"}

    for header, data, labels in (
        ("RELEVANT RESOURCES", resources, resource_labels),
        ("PREVIOUS OUTREACH", previous_outreach, email_labels),
        ("CONTACT HISTORY", contact_history, history_labels),
        ("ORG CONTEXT", org_context, org_labels),
    ):
        formatted = _format_block(header, data, labels)
        if formatted:
            blocks.append((header, formatted))

    if not blocks:
        return {"blocks": [], "used_chunk_ids": [], "formatted": None}

    parts = []
    for header, body in blocks:
        parts.append(f"--- {header} ---\n{body}\n--- END {header} ---")
    formatted_all = "\n\n".join(parts)

    return {
        "blocks": blocks,
        "used_chunk_ids": collected_ids,
        "formatted": formatted_all,
    }


# --- Phase 5: Pre-send safety net ---

def _trim_rag_formatted_by_blocks(text_val: str, max_chars: int) -> str:
    """Trim a formatted RAG snapshot to max_chars without cutting a row mid-line.

    The presend and email-context formatters emit blocks of the shape:
        --- HEADER ---
        - row one
        - row two

        --- OTHER HEADER ---
        - row three

    A raw string slice can cut a row mid-sentence, leak partial PII, and
    trail with a bare "..." that the model treats as content. This helper
    drops whole trailing lines until the budget fits, strips any orphaned
    "--- HEADER ---" left without rows, and appends a clear truncation
    marker so the model knows the context was cut.
    """
    if len(text_val) <= max_chars:
        return text_val

    MARKER = "\n... [truncated]"
    budget = max_chars - len(MARKER)
    if budget <= 0:
        return ""

    lines = text_val.split("\n")
    kept: List[str] = []
    current_len = 0
    for line in lines:
        added = len(line) + (1 if kept else 0)  # +1 for the newline separator
        if current_len + added > budget:
            break
        kept.append(line)
        current_len += added

    # Drop trailing orphan header (header with no rows beneath after trim) and
    # any blank separator line immediately before it.
    def _is_header(s: str) -> bool:
        return s.startswith("--- ") and s.endswith(" ---")

    while kept and _is_header(kept[-1]):
        kept.pop()
        while kept and kept[-1] == "":
            kept.pop()

    while kept and kept[-1] == "":
        kept.pop()

    if not kept:
        return ""

    return "\n".join(kept) + MARKER


async def get_presend_snapshot(
    db: Session,
    account_id: int,
    email_created_at: datetime,
    contact_id: Optional[int] = None,
    org_id: Optional[int] = None,
    limit: int = 8,
) -> Optional[Dict[str, Any]]:
    """Query embeddings filtered to activity/crm_change/generated_email rows
    created AFTER the email was queued. Scoped to contact_id and org_id.

    Returns None when nothing found — caller should skip the AI STOP/CONTINUE
    check entirely ($0 cost path).
    """
    if is_tracing():
        async with traced_call(
            "rag.get_presend_snapshot",
            request={
                "account_id": account_id,
                "email_created_at": email_created_at.isoformat() if email_created_at else None,
                "contact_id": contact_id,
                "org_id": org_id,
                "limit": limit,
            },
        ) as t:
            result = await _get_presend_snapshot_impl(
                db, account_id, email_created_at, contact_id, org_id, limit,
            )
            if t:
                t["response"] = {
                    "found": result is not None,
                    "has_contact_signal": (result or {}).get("has_contact_signal", False),
                    "has_org_signal": (result or {}).get("has_org_signal", False),
                    "formatted_preview": ((result or {}).get("formatted") or "")[:1000],
                }
            return result
    return await _get_presend_snapshot_impl(
        db, account_id, email_created_at, contact_id, org_id, limit,
    )


async def _get_presend_snapshot_impl(
    db: Session,
    account_id: int,
    email_created_at: datetime,
    contact_id: Optional[int],
    org_id: Optional[int],
    limit: int,
) -> Optional[Dict[str, Any]]:
    if not contact_id and not org_id:
        return None

    # Must match the set of source_types written by the ingest path
    # (contacts_service._schedule_activity_embedding, store_generated_email).
    # PRESEND_SOURCE_TYPES is the shared constant — do not hardcode a local
    # list here or the two sides can drift.
    source_types = list(PRESEND_SOURCE_TYPES)

    # Build where clause for contact signals
    contact_rows = []
    if contact_id:
        try:
            contact_rows = db.query(models.ContentEmbedding).filter(
                and_(
                    models.ContentEmbedding.account_id == account_id,
                    models.ContentEmbedding.contact_id == contact_id,
                    models.ContentEmbedding.source_type.in_(source_types),
                    models.ContentEmbedding.created_at >= email_created_at,
                )
            ).order_by(models.ContentEmbedding.created_at.desc()).limit(limit).all()
        except Exception as e:
            logger.error(f"Presend contact query failed: {e}")

    # Org signals (other contacts at same org)
    org_rows = []
    if org_id:
        try:
            q = db.query(models.ContentEmbedding).filter(
                and_(
                    models.ContentEmbedding.account_id == account_id,
                    models.ContentEmbedding.org_id == org_id,
                    models.ContentEmbedding.source_type.in_(source_types),
                    models.ContentEmbedding.created_at >= email_created_at,
                )
            )
            if contact_id:
                q = q.filter(
                    or_(
                        models.ContentEmbedding.contact_id != contact_id,
                        models.ContentEmbedding.contact_id.is_(None),
                    )
                )
            org_rows = q.order_by(models.ContentEmbedding.created_at.desc()).limit(limit).all()
        except Exception as e:
            logger.error(f"Presend org query failed: {e}")

    if not contact_rows and not org_rows:
        return None

    def _format_rows(rows, header):
        if not rows:
            return ""
        lines = [f"--- {header} ---"]
        for r in rows:
            md = r.chunk_metadata or {}
            when = ""
            if isinstance(md, dict) and md.get("occurred_at"):
                when = f" [{str(md['occurred_at'])[:16]}]"
            lines.append(f"- {r.source_type}{when}: {r.chunk_text[:500]}")
        return "\n".join(lines)

    contact_block = _format_rows(contact_rows, f"CONTACT SIGNALS (after {email_created_at.isoformat()})")
    org_block = _format_rows(org_rows, "ORG-LEVEL SIGNALS")

    formatted = "\n\n".join(p for p in (contact_block, org_block) if p)

    # Cap to ~400 tokens (1 token ~= 4 chars, so ~1600 chars). Trim by whole
    # rows so we never feed Sonnet a half-cut line (which is both lower-quality
    # context and a partial-PII leak).
    formatted = _trim_rag_formatted_by_blocks(formatted, max_chars=1600)

    return {
        "contact_signals": contact_block,
        "org_signals": org_block,
        "formatted": formatted,
        "has_contact_signal": bool(contact_rows),
        "has_org_signal": bool(org_rows),
        "contact_rows": contact_rows,
        "org_rows": org_rows,
    }


# --- Phase 6: Haiku context sufficiency gate ---

async def check_context_sufficiency(
    rag_context: str,
    query: str,
    db: Optional[Session] = None,
) -> Tuple[str, Optional[str]]:
    """Ask Haiku whether the current RAG context is sufficient to answer the query.

    Returns ("SUFFICIENT", None) or ("MISSING", "5–10 word description of gap").
    Any unexpected output defaults to SUFFICIENT to avoid blocking generation.

    Failure-open: if Haiku call itself fails, return SUFFICIENT.
    """
    if not rag_context or not rag_context.strip():
        # No context to evaluate — caller decides whether that's a problem
        return ("SUFFICIENT", None)

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return ("SUFFICIENT", None)

    model = get_haiku_model(db)

    system_prompt = (
        "You are a context-sufficiency checker. You will see retrieved RAG context and the user's query. "
        "Respond with EXACTLY one of:\n"
        "  SUFFICIENT\n"
        "  MISSING: <5-10 word description of the specific gap>\n"
        "Respond with nothing else — no explanations, no punctuation beyond what is shown."
    )
    user_msg = f"Query:\n{query[:1000]}\n\nContext:\n{rag_context[:6000]}"

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": model,
                    "max_tokens": 64,
                    "system": [
                        {
                            "type": "text",
                            "text": system_prompt,
                            "cache_control": {"type": "ephemeral"},
                        }
                    ],
                    "messages": [{"role": "user", "content": user_msg}],
                },
            )
            resp.raise_for_status()
            data = resp.json()
            # Accumulate tokens under the Haiku call (won't have usage_context set if caller didn't set it — that's fine)
            try:
                from ai_service import _accumulate_tokens
                _accumulate_tokens(data)
            except Exception:
                pass
            out = data["content"][0]["text"].strip()
    except Exception as e:
        logger.warning(f"Haiku sufficiency check failed (defaulting SUFFICIENT): {e}")
        return ("SUFFICIENT", None)

    up = out.upper()
    if up.startswith("SUFFICIENT"):
        return ("SUFFICIENT", None)
    if up.startswith("MISSING"):
        # Extract the gap description after "MISSING:"
        _, _, gap = out.partition(":")
        gap = gap.strip() or "unspecified gap"
        return ("MISSING", gap)
    # Any other output defaults to SUFFICIENT. A misconfigured Haiku model id
    # is the most common cause — Anthropic returns a non-empty body that
    # doesn't start with the expected tokens. Logging at WARNING (not DEBUG)
    # surfaces this in ops dashboards so a typo in rag.haiku_model doesn't
    # masquerade as "the sufficiency check is too permissive".
    logger.warning(
        "Haiku sufficiency returned unexpected output %r (model=%s) — "
        "defaulting SUFFICIENT. If this repeats, check rag.haiku_model.",
        out, model,
    )
    return ("SUFFICIENT", None)


# --- Phase 5 helper: build activity summary for embedding ---

# Fresh Check tag constants (issue #175). Tags are prefixed onto every
# embedded summary so T3's Haiku rule-matcher can regex over chunk_text
# without having to join back to the source activity row. The set of
# allowed tags lives in FRESH_CHECK_TAGS; anything outside the set will
# silently fall through to [activity] rather than leak a novel marker
# into the snapshot.
FRESH_CHECK_TAG_REPLY = "[reply]"
FRESH_CHECK_TAG_INBOX = "[inbox]"
FRESH_CHECK_TAG_ACTIVITY = "[activity]"
FRESH_CHECK_TAG_PULSE = "[pulse]"
FRESH_CHECK_TAG_ORG_SIGNAL = "[org_signal]"
FRESH_CHECK_TAG_CRM_CHANGE = "[crm_change]"
FRESH_CHECK_TAG_NOTE = "[note]"
FRESH_CHECK_TAG_DNC = "[dnc]"
FRESH_CHECK_TAG_CROSS_WORKFLOW = "[cross_workflow]"

FRESH_CHECK_TAGS: frozenset = frozenset({
    FRESH_CHECK_TAG_REPLY,
    FRESH_CHECK_TAG_INBOX,
    FRESH_CHECK_TAG_ACTIVITY,
    FRESH_CHECK_TAG_PULSE,
    FRESH_CHECK_TAG_ORG_SIGNAL,
    FRESH_CHECK_TAG_CRM_CHANGE,
    FRESH_CHECK_TAG_NOTE,
    FRESH_CHECK_TAG_DNC,
    FRESH_CHECK_TAG_CROSS_WORKFLOW,
})

# activity_type → tag prefix. Covers both the values currently written by
# the ingest paths (email_sent, meeting, call, note, contact_merged,
# deal_stage_change, deal_status_change) and the values anticipated by
# the Fresh Check spec (#175) so that when reply-ingest and webhook
# contact_updated land the tags are already in place. A value missing
# from this map falls through to [activity].
_ACTIVITY_TYPE_TAG_MAP: Dict[str, str] = {
    # Rule 1 producers
    "reply_received": FRESH_CHECK_TAG_REPLY,
    # Rule 2 producers
    "email_received": FRESH_CHECK_TAG_INBOX,
    # Rule 6 producers — CRM change (structural, not a touchpoint)
    "deal_stage_changed": FRESH_CHECK_TAG_CRM_CHANGE,
    "deal_stage_change": FRESH_CHECK_TAG_CRM_CHANGE,     # current Pipedrive writer
    "deal_status_change": FRESH_CHECK_TAG_CRM_CHANGE,    # current Pipedrive writer
    "deal_status_changed": FRESH_CHECK_TAG_CRM_CHANGE,
    "contact_updated": FRESH_CHECK_TAG_CRM_CHANGE,
    "contact_merged": FRESH_CHECK_TAG_CRM_CHANGE,
    # Rule 3 producers (generic touchpoints) — explicit listing keeps the
    # fallback path from silently swallowing future type renames.
    "email_sent": FRESH_CHECK_TAG_ACTIVITY,
    "email_opened": FRESH_CHECK_TAG_ACTIVITY,
    "email_clicked": FRESH_CHECK_TAG_ACTIVITY,
    "meeting": FRESH_CHECK_TAG_ACTIVITY,
    "call": FRESH_CHECK_TAG_ACTIVITY,
    "bounced": FRESH_CHECK_TAG_ACTIVITY,
    "note": FRESH_CHECK_TAG_ACTIVITY,
    "note_added": FRESH_CHECK_TAG_ACTIVITY,
}


def activity_tag(activity_type: str, extra: Optional[Dict[str, Any]] = None) -> str:
    """Return the Fresh Check tag prefix for an activity_type.

    Notes with an explicit flag marker in extra (e.g. {"flag_type": "alert"})
    upgrade from [activity] to [note] per the spec matrix; plain notes stay
    in the generic [activity] bucket until they carry a flag signal.
    """
    tag = _ACTIVITY_TYPE_TAG_MAP.get(activity_type, FRESH_CHECK_TAG_ACTIVITY)
    if activity_type in ("note", "note_added") and isinstance(extra, dict) and extra.get("flag_type"):
        return FRESH_CHECK_TAG_NOTE
    return tag


def build_activity_summary(
    activity_type: str,
    direction: Optional[str],
    subject: Optional[str],
    summary: Optional[str],
    extra: Optional[Dict[str, Any]] = None,
    occurred_at: Optional[datetime] = None,
) -> str:
    """Build a human-readable single-line summary of a ContactActivity for embedding.

    The output is prefixed with a Fresh Check tag (see activity_tag()) so
    T3's rule-matcher can scan the snapshot without re-joining to the
    source activity. Examples:
      - "[reply] Contact replied 2026-04-09: SOW looks great..."
      - "[activity] Email sent 2026-04-10: subject 'Quick follow-up'"
      - "[crm_change] Deal stage changed 2026-04-10: from_stage=Negotiation..."
    """
    when = (occurred_at or datetime.now(timezone.utc)).strftime("%Y-%m-%d")
    verb_map = {
        "email_sent": "Email sent",
        "email_received": "Email received",
        "reply_received": "Contact replied",
        "email_opened": "Email opened",
        "email_clicked": "Link clicked",
        "meeting": "Meeting",
        "note_added": "Note added",
        "bounced": "Email bounced",
        "deal_stage_changed": "Deal stage changed",
        "contact_updated": "Contact updated",
    }
    verb = verb_map.get(activity_type, activity_type.replace("_", " ").title())

    detail_parts: List[str] = []
    if summary:
        detail_parts.append(summary.strip())
    elif subject:
        detail_parts.append(f"subject '{subject.strip()}'")
    if extra:
        # Surface stage changes, deal value moves, etc.
        for k in ("from_stage", "to_stage", "deal_value"):
            if extra.get(k):
                detail_parts.append(f"{k}={extra[k]}")

    detail = ", ".join(detail_parts) if detail_parts else ""
    dir_suffix = f" ({direction})" if direction else ""
    tag = activity_tag(activity_type, extra)
    return f"{tag} {verb} {when}{dir_suffix}: {detail}".strip().rstrip(":")
