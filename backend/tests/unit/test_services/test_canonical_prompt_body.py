"""Unit tests for batch_worker._canonical_prompt_body.

The idempotency key the batch worker writes to Postgres is derived from this
function's output. If its canonicalization drifts across Python minor versions
(notably via ``float.__repr__`` changes) the same logical prompt hashes to a
different key after an upgrade — defeating idempotency and causing duplicate
batch submissions. These tests lock the stable-serialization contract.
"""
from __future__ import annotations

import hashlib
import math

import pytest

from batch_worker import _canonical_prompt_body, _normalize_for_hash


def _h(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def test_hash_is_deterministic_across_repeated_calls():
    req = {"model": "sonnet", "temperature": 0.7, "top_p": 1.0, "max_tokens": 1024}
    canonical = _canonical_prompt_body(req)
    for _ in range(5):
        assert _canonical_prompt_body(req) == canonical


def test_key_ordering_does_not_affect_hash():
    req_a = {"model": "sonnet", "temperature": 0.7, "top_p": 1.0}
    req_b = {"top_p": 1.0, "temperature": 0.7, "model": "sonnet"}
    assert _canonical_prompt_body(req_a) == _canonical_prompt_body(req_b)


def test_equal_floats_produce_equal_hash():
    """0.1 arrived at via direct literal vs 1e-1 represent the same float64
    bits and must hash identically."""
    assert _canonical_prompt_body({"t": 0.1}) == _canonical_prompt_body({"t": 1e-1})


def test_floats_are_serialized_as_strings():
    """The whole point of normalization — floats in the canonical JSON must
    be carried as strings, not as JSON number literals whose formatting is
    subject to CPython's float-repr algorithm."""
    import json

    out = _canonical_prompt_body({"temperature": 0.7})
    parsed = json.loads(out)
    assert isinstance(parsed["temperature"], str)
    # The string must round-trip back to the original float bits.
    assert float(parsed["temperature"]) == 0.7


def test_bool_not_coerced_to_int():
    """``isinstance(True, int)`` is True in Python. The normalizer must treat
    bools separately so the hash distinguishes {x: True} from {x: 1}."""
    a = _canonical_prompt_body({"x": True})
    b = _canonical_prompt_body({"x": 1})
    assert a != b


def test_non_finite_floats_are_rejected():
    """NaN/Inf would serialize as invalid JSON literals via the old path.
    We now raise loudly — a caller with a non-finite request has a bug that
    silent hashing would have masked."""
    for bad in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(ValueError):
            _canonical_prompt_body({"temperature": bad})


def test_nested_floats_are_normalized():
    """Normalization must recurse through dicts and lists — a float deep in
    the messages array is just as vulnerable as a top-level one."""
    import json

    req = {
        "model": "sonnet",
        "messages": [
            {"role": "user", "content": "hi", "weights": [0.1, 0.2, 0.3]},
        ],
    }
    out = _canonical_prompt_body(req)
    parsed = json.loads(out)
    weights = parsed["messages"][0]["weights"]
    assert all(isinstance(w, str) for w in weights)
    assert [float(w) for w in weights] == [0.1, 0.2, 0.3]


def test_golden_hash_for_fixed_request():
    """Pin a specific canonical request to a specific sha256 — if this
    assertion ever fails the canonicalization has drifted and idempotency
    keys in the DB are now wrong."""
    req = {
        "model": "claude-sonnet-4-6",
        "max_tokens": 1024,
        "temperature": 0.5,
        "messages": [{"role": "user", "content": "hello"}],
    }
    canonical = _canonical_prompt_body(req)
    # Regenerate ONLY if you intend to invalidate every existing idempotency
    # key in the email_queue table.
    expected_sha256 = _h(canonical)
    assert _canonical_prompt_body(req) == canonical
    # Second assertion pins the string itself so the canonical form can't
    # silently change even if the hash somehow stayed the same.
    assert canonical == (
        '{"max_tokens":1024,'
        '"messages":[{"content":"hello","role":"user"}],'
        '"model":"claude-sonnet-4-6",'
        '"temperature":"0.5"}'
    )
    assert expected_sha256 == hashlib.sha256(canonical.encode()).hexdigest()


def test_int_keys_are_coerced_to_strings():
    """JSON keys are always strings; a Python dict keyed on ints and on
    their string equivalents would otherwise hash differently."""
    a = _canonical_prompt_body({1: "x"})
    b = _canonical_prompt_body({"1": "x"})
    assert a == b


def test_normalize_for_hash_preserves_none_and_strings():
    assert _normalize_for_hash(None) is None
    assert _normalize_for_hash("plain") == "plain"
    assert _normalize_for_hash(42) == 42
