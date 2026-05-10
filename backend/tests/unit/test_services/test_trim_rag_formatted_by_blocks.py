"""Unit tests for rag_service._trim_rag_formatted_by_blocks.

The raw slice `formatted[:1597] + "..."` used to cut rows mid-sentence, which:
  * leaks half an email / half a phone number as partial PII,
  * feeds the model a malformed snippet,
  * trails with a bare "..." that looks like content rather than truncation.

The helper must drop whole rows, strip orphaned headers, and end with a clear
truncation marker.
"""
from __future__ import annotations

import pytest

from rag_service import _trim_rag_formatted_by_blocks


MARKER = "... [truncated]"


def test_short_input_returned_unchanged():
    text = "--- HEADER ---\n- row one\n- row two"
    assert _trim_rag_formatted_by_blocks(text, max_chars=1000) == text


def test_trim_preserves_whole_lines():
    """Build a snapshot of 3 rows ~800 chars each (~2400 total). With a 1600
    budget the trimmed result must end on a line boundary — no half-sentence."""
    rows = [
        "- activity [2026-04-20 10:00]: " + ("Alice emailed about renewal. " * 20),
        "- activity [2026-04-21 11:00]: " + ("Bob replied with a counter-offer. " * 20),
        "- activity [2026-04-22 12:00]: " + ("Charlie flagged legal concerns. " * 20),
    ]
    text = "--- CONTACT SIGNALS ---\n" + "\n".join(rows)

    out = _trim_rag_formatted_by_blocks(text, max_chars=1600)

    assert len(out) <= 1600
    assert out.endswith(MARKER)

    # The body before the marker must be whole lines joined by "\n".
    body = out[: -len("\n" + MARKER)]
    for line in body.split("\n"):
        assert line == "--- CONTACT SIGNALS ---" or line.startswith("- activity")


def test_orphan_header_is_dropped():
    """A header whose rows all fall past the budget must not survive alone —
    a bare '--- ORG-LEVEL SIGNALS ---' in the prompt is useless and may
    confuse the model."""
    # Fill the contact block so ORG-LEVEL header fits but none of its rows do.
    contact_rows = "\n".join(f"- activity: {'x' * 100}" for _ in range(10))
    org_rows = "\n".join(f"- activity: {'y' * 200}" for _ in range(5))
    text = (
        "--- CONTACT SIGNALS ---\n" + contact_rows + "\n\n"
        "--- ORG-LEVEL SIGNALS ---\n" + org_rows
    )

    # Pick a budget that fits the contact block + header line but not the first
    # org row.
    budget = len("--- CONTACT SIGNALS ---\n" + contact_rows) + len(
        "\n\n--- ORG-LEVEL SIGNALS ---"
    ) + 5

    out = _trim_rag_formatted_by_blocks(text, max_chars=budget)

    # ORG-LEVEL SIGNALS must have been dropped as an orphan.
    assert "--- ORG-LEVEL SIGNALS ---" not in out
    assert "--- CONTACT SIGNALS ---" in out
    assert out.endswith(MARKER)


def test_truncation_marker_appended_when_cut():
    text = "--- HEADER ---\n" + "\n".join(f"- row {i}: {'a' * 50}" for i in range(20))
    out = _trim_rag_formatted_by_blocks(text, max_chars=300)
    assert out.endswith(MARKER)


def test_marker_never_pushes_output_over_budget():
    """Budget is a hard ceiling — output must never exceed max_chars even
    after the marker is appended."""
    text = "--- HEADER ---\n" + "\n".join(f"- row {i}: {'z' * 50}" for i in range(50))
    for budget in (100, 250, 500, 1000, 1600):
        out = _trim_rag_formatted_by_blocks(text, max_chars=budget)
        assert len(out) <= budget, (
            f"budget={budget} overflowed: got {len(out)} chars"
        )


def test_budget_smaller_than_marker_returns_empty():
    """If max_chars is so small the marker itself doesn't fit, return empty
    rather than emit a partial/misleading result."""
    text = "--- HEADER ---\n- row one\n- row two"
    out = _trim_rag_formatted_by_blocks(text, max_chars=len(MARKER) - 1)
    # Note: MARKER in code is "\n... [truncated]" (16 chars) — budget of 5
    # leaves no room even for the marker alone.
    assert out == ""
