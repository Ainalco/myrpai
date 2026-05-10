"""Anthropic Message Batches HTTP client.

Thin async wrapper around /v1/messages/batches that follows the raw-httpx
pattern used in ai_service.py (no SDK dependency). Surface is intentionally
small — just what batch_worker.py needs for the two-phase-write + reconcile
flow documented in docs/superpowers/plans/2026-04-21-batch-api-idempotency.md.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, AsyncIterator, Dict, List, Optional
from urllib.parse import urlparse

import httpx


logger = logging.getLogger(__name__)

ANTHROPIC_BASE_URL = "https://api.anthropic.com"
ANTHROPIC_VERSION = "2023-06-01"
BATCHES_BETA_HEADER = "message-batches-2024-09-24"

# SSRF guard: results_url is a server-supplied string that gets hit with the
# x-api-key header attached. Pin it to hosts Anthropic actually serves results
# from so a spoofed/compromised response can't redirect us at internal IPs or
# exfiltrate the API key.
ALLOWED_RESULTS_HOSTS = frozenset({"api.anthropic.com"})

# Separate timeout for batch submit (synchronous, accepts the manifest) vs.
# results fetch (can stream many MB). Both bounded so the worker can't hang.
DEFAULT_SUBMIT_TIMEOUT = 60.0
DEFAULT_RESULTS_TIMEOUT = 300.0


class AnthropicBatchError(Exception):
    """Raised when the Batches API returns a non-2xx response we can't recover from."""


def _sanitize_error(
    op: str,
    status_code: int,
    headers: Any,
    body: Any,
) -> str:
    """Summarize an Anthropic HTTP error without echoing submitted prompt content.

    Anthropic 4xx error bodies frequently echo the offending `messages` content
    (draft email bodies, transcript excerpts, CRM contact details). The raw
    body MUST NOT end up in centralized logs — see the PII-in-logs policy in
    logging_config.py. This helper mirrors rag_service._sanitize_openai_error:
    keep status + error.type + error.code + request_id; drop error.message
    because it can contain submitted input verbatim.
    """
    parts = [f"{op} HTTP {status_code}"]
    details: List[str] = []
    try:
        if isinstance(body, (bytes, bytearray)):
            text = body.decode("utf-8", errors="replace")
        else:
            text = body or ""
        data = json.loads(text) if text else {}
        err = data.get("error", {}) if isinstance(data, dict) else {}
        err_type = err.get("type")
        code = err.get("code")
        if err_type:
            details.append(f"type={err_type}")
        if code:
            details.append(f"code={code}")
    except Exception:
        details.append("error body not parseable")
    try:
        req_id = None
        if headers is not None:
            req_id = headers.get("request-id") or headers.get("x-request-id")
        if req_id:
            details.append(f"request_id={req_id}")
    except Exception:
        pass
    if details:
        parts.append("(" + " ".join(details) + ")")
    return " ".join(parts)


def _headers() -> Dict[str, str]:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise AnthropicBatchError("ANTHROPIC_API_KEY not configured")
    return {
        "x-api-key": api_key,
        "anthropic-version": ANTHROPIC_VERSION,
        "anthropic-beta": BATCHES_BETA_HEADER,
        "content-type": "application/json",
    }


async def create_batch(requests: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Submit a batch. Each request entry must carry `custom_id` + `params`.

    `custom_id` is what batch_worker uses to reconcile results back to
    email_queue rows; callers MUST set it deterministically.
    """
    if not requests:
        raise AnthropicBatchError("create_batch called with empty requests list")
    for req in requests:
        if not req.get("custom_id"):
            raise AnthropicBatchError("every request in a batch must set custom_id")

    async with httpx.AsyncClient(timeout=DEFAULT_SUBMIT_TIMEOUT) as client:
        resp = await client.post(
            f"{ANTHROPIC_BASE_URL}/v1/messages/batches",
            headers=_headers(),
            json={"requests": requests},
        )
        if resp.status_code >= 400:
            raise AnthropicBatchError(
                _sanitize_error("create_batch", resp.status_code, resp.headers, resp.text)
            )
        return resp.json()


async def get_batch(batch_id: str) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=DEFAULT_SUBMIT_TIMEOUT) as client:
        resp = await client.get(
            f"{ANTHROPIC_BASE_URL}/v1/messages/batches/{batch_id}",
            headers=_headers(),
        )
        if resp.status_code >= 400:
            raise AnthropicBatchError(
                _sanitize_error("get_batch", resp.status_code, resp.headers, resp.text)
            )
        return resp.json()


async def list_batches(
    limit: int = 100,
    after_id: Optional[str] = None,
) -> Dict[str, Any]:
    """List recent batches. Used by reconciliation on worker startup.

    Returns the raw page — caller paginates via `has_more` + `last_id` so it
    can stop early once the reconciliation window (e.g. 24h) is exceeded.
    """
    params: Dict[str, Any] = {"limit": max(1, min(100, limit))}
    if after_id:
        params["after_id"] = after_id

    async with httpx.AsyncClient(timeout=DEFAULT_SUBMIT_TIMEOUT) as client:
        resp = await client.get(
            f"{ANTHROPIC_BASE_URL}/v1/messages/batches",
            headers=_headers(),
            params=params,
        )
        if resp.status_code >= 400:
            raise AnthropicBatchError(
                _sanitize_error("list_batches", resp.status_code, resp.headers, resp.text)
            )
        return resp.json()


def _validate_results_url(url: str) -> None:
    parsed = urlparse(url or "")
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_RESULTS_HOSTS:
        raise AnthropicBatchError(
            f"refusing to fetch batch results from unexpected URL "
            f"(scheme={parsed.scheme!r}, host={parsed.hostname!r})"
        )


async def iterate_batch_results(
    results_url: str,
) -> AsyncIterator[Dict[str, Any]]:
    """Stream results from a completed batch (jsonl)."""
    _validate_results_url(results_url)
    async with httpx.AsyncClient(timeout=DEFAULT_RESULTS_TIMEOUT) as client:
        async with client.stream("GET", results_url, headers=_headers()) as resp:
            if resp.status_code >= 400:
                body = await resp.aread()
                raise AnthropicBatchError(
                    _sanitize_error(
                        "iterate_batch_results", resp.status_code, resp.headers, body
                    )
                )
            async for line in resp.aiter_lines():
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError as e:
                    logger.warning("Skipping malformed batch result line: %s", e)
                    continue
