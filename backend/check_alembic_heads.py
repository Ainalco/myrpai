#!/usr/bin/env python3
"""Verify the alembic migration tree has exactly one head.

Two heads means two migrations branched off the same parent (typically two
PRs each adding "041_*" off "040"). Alembic refuses to upgrade in that
state. Catching it at PR time is cheaper than catching it at deploy time.

Run locally:   python3 backend/check_alembic_heads.py
Exit 0 = single head. Exit 1 = multiple heads or no migrations found.
"""
import re
import sys
from pathlib import Path

REVISION_RE = re.compile(
    r"^\s*revision\s*(?::[^=]*)?=\s*['\"]([^'\"]+)['\"]", re.MULTILINE
)
DOWN_REVISION_RE = re.compile(
    r"^\s*down_revision\s*(?::[^=]*)?=\s*(.+?)$", re.MULTILINE
)


def parse_down_revision(raw: str) -> list[str]:
    """down_revision can be None, a string, or a tuple/list of strings."""
    raw = raw.strip().rstrip(",").strip()
    if raw in ("None", ""):
        return []
    if raw[0] in "([" and raw[-1] in ")]":
        raw = raw[1:-1]
    parts = [p.strip().strip("'\"") for p in raw.split(",")]
    return [p for p in parts if p]


def main() -> int:
    versions_dir = Path(__file__).resolve().parent / "alembic" / "versions"
    if not versions_dir.is_dir():
        print(f"ERROR: {versions_dir} not found", file=sys.stderr)
        return 1

    revisions: dict[str, str] = {}
    parents: set[str] = set()

    for path in sorted(versions_dir.glob("*.py")):
        if path.name.startswith("__"):
            continue
        text = path.read_text()
        rev_match = REVISION_RE.search(text)
        if not rev_match:
            print(f"WARNING: {path.name} has no `revision = ...`", file=sys.stderr)
            continue
        revisions[rev_match.group(1)] = path.name
        down_match = DOWN_REVISION_RE.search(text)
        if down_match:
            for parent in parse_down_revision(down_match.group(1)):
                parents.add(parent)

    if not revisions:
        print("ERROR: no migration files found", file=sys.stderr)
        return 1

    heads = sorted(set(revisions) - parents)

    if len(heads) == 1:
        print(f"OK: single alembic head -> {heads[0]} ({revisions[heads[0]]})")
        return 0

    print(f"ERROR: expected 1 alembic head, found {len(heads)}:", file=sys.stderr)
    for h in heads:
        print(f"  - {h}  ({revisions[h]})", file=sys.stderr)
    print(
        "\nTwo heads = two migrations branched off the same parent."
        "\nRebase the second-merged migration:"
        "\n  1. Rename the file to the next sequential number"
        "\n  2. Update `revision = ...` to match the new name"
        "\n  3. Update `down_revision = ...` to point at the other head",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
