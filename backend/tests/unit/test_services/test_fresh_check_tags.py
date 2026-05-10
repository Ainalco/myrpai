"""Regression tests for the Fresh Check tag surface (#175 T2).

Pins two contracts:

  1. activity_tag() maps every activity_type currently written by the
     ingest paths to the correct Fresh Check tag. Drift here means T3's
     Haiku rule-matcher would silently miss signals the producer emits.

  2. build_activity_summary() prefixes its output with the tag. Snapshots
     are regex-scanned by T3 on chunk_text alone, so a missing or
     malformed prefix is indistinguishable from "signal didn't occur".
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from rag_service import (
    FRESH_CHECK_TAG_ACTIVITY,
    FRESH_CHECK_TAG_CRM_CHANGE,
    FRESH_CHECK_TAG_INBOX,
    FRESH_CHECK_TAG_NOTE,
    FRESH_CHECK_TAG_REPLY,
    FRESH_CHECK_TAGS,
    activity_tag,
    build_activity_summary,
)


class TestActivityTag:
    @pytest.mark.parametrize(
        "activity_type,expected",
        [
            # Spec-canonical values (#175 tag→producer matrix)
            ("reply_received", FRESH_CHECK_TAG_REPLY),
            ("email_received", FRESH_CHECK_TAG_INBOX),
            ("deal_stage_changed", FRESH_CHECK_TAG_CRM_CHANGE),
            ("contact_updated", FRESH_CHECK_TAG_CRM_CHANGE),
            # Values actually written by today's ingest paths
            ("email_sent", FRESH_CHECK_TAG_ACTIVITY),
            ("meeting", FRESH_CHECK_TAG_ACTIVITY),
            ("call", FRESH_CHECK_TAG_ACTIVITY),
            ("note", FRESH_CHECK_TAG_ACTIVITY),
            ("contact_merged", FRESH_CHECK_TAG_CRM_CHANGE),
            # Pipedrive singulars — these ARE written in pipedrive_sync.py
            # and have historically drifted from the spec's plural form.
            # Covering both guards against the map losing one during a
            # refactor.
            ("deal_stage_change", FRESH_CHECK_TAG_CRM_CHANGE),
            ("deal_status_change", FRESH_CHECK_TAG_CRM_CHANGE),
            # Unknown / future values fall through to the generic bucket
            # rather than leaking a novel tag into the snapshot.
            ("made_up_type", FRESH_CHECK_TAG_ACTIVITY),
            ("", FRESH_CHECK_TAG_ACTIVITY),
        ],
    )
    def test_maps_activity_type_to_tag(self, activity_type, expected):
        assert activity_tag(activity_type) == expected

    def test_flagged_note_upgrades_to_note_tag(self):
        """A note_added with flag_type metadata is rule-7 material and
        upgrades from [activity] to [note]. Plain notes stay [activity]."""
        assert activity_tag("note_added") == FRESH_CHECK_TAG_ACTIVITY
        assert activity_tag("note_added", extra={"flag_type": "alert"}) == FRESH_CHECK_TAG_NOTE
        assert activity_tag("note", extra={"flag_type": "alert"}) == FRESH_CHECK_TAG_NOTE
        # Empty flag_type is a falsy hint — do NOT upgrade.
        assert activity_tag("note", extra={"flag_type": ""}) == FRESH_CHECK_TAG_ACTIVITY
        assert activity_tag("note", extra={}) == FRESH_CHECK_TAG_ACTIVITY

    def test_returned_tag_is_in_closed_set(self):
        """Every tag returned by the mapper must be one of the declared
        FRESH_CHECK_TAGS. Prevents a typo-new-tag from silently shipping."""
        for at in (
            "reply_received", "email_received", "meeting", "call", "note",
            "note_added", "email_sent", "deal_stage_change", "deal_status_change",
            "contact_merged", "contact_updated", "unknown_future_type",
        ):
            assert activity_tag(at) in FRESH_CHECK_TAGS


class TestBuildActivitySummaryTagPrefix:
    def _when(self) -> datetime:
        return datetime(2026, 4, 24, 12, 0, tzinfo=timezone.utc)

    def test_reply_prefixed_with_reply_tag(self):
        out = build_activity_summary(
            activity_type="reply_received",
            direction="inbound",
            subject="Re: Proposal",
            summary="SOW looks great, question about SLA",
            occurred_at=self._when(),
        )
        assert out.startswith(FRESH_CHECK_TAG_REPLY + " ")
        assert "Contact replied" in out
        assert "SOW looks great" in out

    def test_inbox_prefixed_with_inbox_tag(self):
        out = build_activity_summary(
            activity_type="email_received",
            direction="inbound",
            subject="Intro",
            summary=None,
            occurred_at=self._when(),
        )
        assert out.startswith(FRESH_CHECK_TAG_INBOX + " ")

    def test_crm_change_prefixed(self):
        out = build_activity_summary(
            activity_type="deal_stage_change",
            direction="internal",
            subject=None,
            summary="Big deal: Negotiation → Lost",
            occurred_at=self._when(),
            extra={"from_stage": "Negotiation", "to_stage": "Lost"},
        )
        assert out.startswith(FRESH_CHECK_TAG_CRM_CHANGE + " ")
        assert "from_stage=Negotiation" in out
        assert "to_stage=Lost" in out

    def test_generic_activity_prefixed(self):
        out = build_activity_summary(
            activity_type="meeting",
            direction=None,
            subject="Discovery Call",
            summary="30 minute kick-off meeting",
            occurred_at=self._when(),
        )
        assert out.startswith(FRESH_CHECK_TAG_ACTIVITY + " ")

    def test_unknown_activity_type_falls_back_to_activity_tag(self):
        """A new activity_type that isn't in the map must not leak a bare
        verb into the snapshot. The tag prefix is the read-side contract."""
        out = build_activity_summary(
            activity_type="some_future_event",
            direction=None,
            subject=None,
            summary="did a thing",
            occurred_at=self._when(),
        )
        assert out.startswith(FRESH_CHECK_TAG_ACTIVITY + " ")

    def test_tag_precedes_verb_with_single_space(self):
        """The snapshot trimmer (_trim_rag_formatted_by_blocks) splits on
        newlines but T3's matcher sees each row. Lock the exact shape
        '[tag] Verb YYYY-MM-DD ...' so regex expectations don't drift."""
        out = build_activity_summary(
            activity_type="reply_received",
            direction=None,
            subject=None,
            summary="ok",
            occurred_at=self._when(),
        )
        # Tag, one space, then the verb — no double space, no leading
        # whitespace.
        assert out.startswith("[reply] Contact replied 2026-04-24")
