"""Lock the pre-send ingest <-> retrieval contract.

contacts_service._schedule_activity_embedding writes deal_stage_changed /
contact_updated activities under source_type="crm_change". If
rag_service.get_presend_snapshot ever filters to only ("activity",
"generated_email"), those embeddings become dead data and the pre-send safety
net silently stops catching the exact case it was built for (stale email
after a deal moved between generation and send).

These tests pin both halves to the shared PRESEND_SOURCE_TYPES constant so
the write and read sides cannot drift.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

import models
from rag_service import (
    CRM_CHANGE_ACTIVITY_TYPES,
    PRESEND_SOURCE_TYPES,
    activity_source_type,
    get_presend_snapshot,
)


class TestPresendSourceTypesContract:
    """Fast guards that fail loudly if someone drops a type from one side."""

    def test_presend_source_types_covers_crm_change(self):
        assert "activity" in PRESEND_SOURCE_TYPES
        assert "crm_change" in PRESEND_SOURCE_TYPES
        assert "generated_email" in PRESEND_SOURCE_TYPES

    def test_activity_source_type_routes_crm_changes(self):
        for at in CRM_CHANGE_ACTIVITY_TYPES:
            assert activity_source_type(at) == "crm_change"

    def test_activity_source_type_defaults_to_activity(self):
        assert activity_source_type("reply_received") == "activity"
        assert activity_source_type("email_sent") == "activity"
        assert activity_source_type("note_added") == "activity"

    def test_every_ingested_source_type_is_queryable(self):
        """Whatever ingest writes for any plausible activity_type must land
        inside the retrieval filter — that is the whole point of the constant."""
        samples = [
            "reply_received", "email_sent", "email_opened", "email_clicked",
            "deal_stage_changed", "contact_updated", "meeting", "note_added",
            "bounced",
        ]
        for at in samples:
            assert activity_source_type(at) in PRESEND_SOURCE_TYPES, (
                f"activity_type={at!r} maps to source_type={activity_source_type(at)!r}, "
                f"which is not queried by get_presend_snapshot — it would be dead data."
            )


@pytest.fixture
def org(db_session):
    o = models.Organization(name="Test Org", slug="test-org")
    db_session.add(o)
    db_session.commit()
    return o


@pytest.fixture
def account(db_session, org):
    a = models.Account(org_id=org.id)
    db_session.add(a)
    db_session.commit()
    return a


@pytest.fixture
def contact(db_session, org, account):
    u = models.User(
        email="seller@example.com",
        hashed_password="x" * 60,
        full_name="Seller",
        is_active=True,
        org_id=org.id,
    )
    db_session.add(u)
    db_session.commit()
    c = models.Contact(user_id=u.id, email="prospect@example.com")
    db_session.add(c)
    db_session.commit()
    return c


class TestGetPresendSnapshotEndToEnd:
    """Exercises the actual query. The embedding column is left NULL — the
    snapshot filter is pure metadata (source_type / contact_id / created_at)
    and never touches the vector index, so this runs cleanly on SQLite."""

    @pytest.mark.asyncio
    async def test_crm_change_row_is_returned(self, db_session, account, contact):
        email_created_at = datetime.now(timezone.utc) - timedelta(hours=1)
        after = datetime.now(timezone.utc)

        row = models.ContentEmbedding(
            account_id=account.id,
            source_type="crm_change",
            source_id="activity:9001",
            contact_id=contact.id,
            chunk_text=(
                "Deal stage changed 2026-04-22: "
                "from_stage=qualified, to_stage=closed_lost"
            ),
            chunk_index=0,
            embedding=None,
            chunk_metadata={"occurred_at": after.isoformat()},
        )
        db_session.add(row)
        db_session.commit()
        # Pin created_at above server_default so the >= filter is deterministic.
        row.created_at = after
        db_session.commit()

        snapshot = await get_presend_snapshot(
            db=db_session,
            account_id=account.id,
            email_created_at=email_created_at,
            contact_id=contact.id,
            org_id=None,
            limit=8,
        )

        assert snapshot is not None, (
            "crm_change row created after the email should surface — if this "
            "fails, get_presend_snapshot is filtering out the type that "
            "contacts_service writes for deal_stage_changed / contact_updated."
        )
        assert snapshot["has_contact_signal"] is True
        assert "crm_change" in snapshot["formatted"]
        assert "closed_lost" in snapshot["formatted"]
        contact_rows = snapshot.get("contact_rows") or []
        assert any(r.source_type == "crm_change" for r in contact_rows)

    @pytest.mark.asyncio
    async def test_row_before_email_is_excluded(self, db_session, account, contact):
        """Stage changes from before the email was queued are not signals — the
        safety net only fires on state that changed between generation and send."""
        email_created_at = datetime.now(timezone.utc)

        row = models.ContentEmbedding(
            account_id=account.id,
            source_type="crm_change",
            source_id="activity:old",
            contact_id=contact.id,
            chunk_text="Deal stage changed (older than the queued email)",
            chunk_index=0,
            embedding=None,
        )
        db_session.add(row)
        db_session.commit()
        row.created_at = email_created_at - timedelta(days=1)
        db_session.commit()

        snapshot = await get_presend_snapshot(
            db=db_session,
            account_id=account.id,
            email_created_at=email_created_at,
            contact_id=contact.id,
        )
        assert snapshot is None
