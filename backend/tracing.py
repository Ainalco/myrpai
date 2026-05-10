"""Per-request API call tracing.

Used by the component test endpoint's "Run Test with Data" mode. When a trace
buffer is enabled in the current async context, instrumented call sites push
structured entries onto it; the test endpoint returns the buffer in its
response so the UI can render an API Call History panel.

Pattern mirrors backend/logging_config.py's request_id_var: a ContextVar holds
either None (tracing disabled, record_trace is a no-op) or a list (tracing
enabled, entries are appended).

Trace entries are returned to the authenticated user who triggered the test, so
we keep raw payloads — but we cap large strings to avoid bloating responses.
Never write trace bodies to backend logs (PII policy, see logging_config.py).
"""
from __future__ import annotations

import contextvars
import time
import uuid
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timezone
from typing import Any, Optional

# None = tracing disabled. List = tracing enabled, entries appended here.
_trace_buffer: contextvars.ContextVar[Optional[list]] = contextvars.ContextVar(
    "trace_buffer", default=None
)

# Cap individual string fields in trace payloads to keep responses bounded.
_MAX_STRING_LEN = 8000


def is_tracing() -> bool:
    return _trace_buffer.get() is not None


def get_trace() -> list:
    """Return the current trace buffer (or an empty list if disabled)."""
    buf = _trace_buffer.get()
    return list(buf) if buf is not None else []


@contextmanager
def trace_session():
    """Enable tracing for the duration of the with-block.

    Yields the buffer list so the caller can read it after the block exits.
    Resets the ContextVar token on exit so nested sessions don't leak.
    """
    buf: list = []
    token = _trace_buffer.set(buf)
    try:
        yield buf
    finally:
        _trace_buffer.reset(token)


def _truncate(value: Any) -> Any:
    """Trim long strings; recurse into dicts/lists. Leaves other types alone."""
    if isinstance(value, str):
        if len(value) > _MAX_STRING_LEN:
            return value[:_MAX_STRING_LEN] + f"... [truncated {len(value) - _MAX_STRING_LEN} chars]"
        return value
    if isinstance(value, dict):
        return {k: _truncate(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_truncate(v) for v in value]
    return value


def record_trace(
    *,
    type: str,
    started_at: datetime,
    duration_ms: float,
    request: Optional[dict] = None,
    response: Optional[dict] = None,
    error: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> None:
    """Append a trace entry if tracing is enabled. No-op otherwise."""
    buf = _trace_buffer.get()
    if buf is None:
        return
    buf.append({
        "id": str(uuid.uuid4()),
        "type": type,
        "started_at": started_at.astimezone(timezone.utc).isoformat(),
        "duration_ms": round(duration_ms, 2),
        "request": _truncate(request) if request is not None else None,
        "response": _truncate(response) if response is not None else None,
        "error": error,
        "metadata": metadata or {},
    })


def record_skip(
    *,
    type: str,
    reason: str,
    metadata: Optional[dict] = None,
) -> None:
    """Record a structured skip event so the UI can render *why* a path no-oped.

    Used at gating points where RAG (or any traced subsystem) decides not to
    run — e.g. no contact resolved, OpenAI key missing, no historical
    embeddings. The UI surfaces these as diagnostic reasons rather than
    inferring "RAG didn't fire" from the absence of trace entries.
    """
    record_trace(
        type=type,
        started_at=datetime.now(timezone.utc),
        duration_ms=0.0,
        request=None,
        response={"skipped": True, "reason": reason},
        error=None,
        metadata=metadata,
    )


@asynccontextmanager
async def traced_call(
    call_type: str,
    *,
    request: Optional[dict] = None,
    metadata: Optional[dict] = None,
):
    """Async context manager: time the block and record a trace entry.

    Usage:
        async with traced_call("anthropic.sonnet", request={"prompt": p}) as t:
            resp = await client.post(...)
            t["response"] = {"text": resp.text, "tokens": resp.usage.total}

    The yielded dict supports keys: "response", "error", "metadata".
    On exception, error is auto-recorded and the exception re-raised.
    """
    if _trace_buffer.get() is None:
        yield {}
        return

    started_at = datetime.now(timezone.utc)
    start = time.perf_counter()
    slot: dict = {"response": None, "error": None, "metadata": dict(metadata or {})}
    try:
        yield slot
    except Exception as exc:
        slot["error"] = f"{exc.__class__.__name__}: {exc}"
        raise
    finally:
        record_trace(
            type=call_type,
            started_at=started_at,
            duration_ms=(time.perf_counter() - start) * 1000,
            request=request,
            response=slot.get("response"),
            error=slot.get("error"),
            metadata=slot.get("metadata"),
        )
