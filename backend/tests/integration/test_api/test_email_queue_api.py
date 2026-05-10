"""Integration tests for the email queue API endpoints.

Focus is on the Fresh Check override endpoint added in T5 (#178). The
override path is the single human-driven escape hatch when the pre-send
gate stopped an email the admin wants to send anyway, so it has to be
reliable AND stubborn about refusing unsafe overrides (DNC, already-sent
emails, and emails without a Fresh Check decision on them).

These tests also pin the serialization of the four new fresh_check_*
fields on the GET /emails/{id} list path — the frontend queue review UI
depends on those fields being present whenever they're set on the DB
row.

**Fixture strategy.** The project's shared factory-boy scaffolding never
binds `sqlalchemy_session` on the factory classes, so conftest's
`test_user` / `authenticated_client` fixtures raise `RuntimeError: No
session provided.` on first use. The same note exists in
test_batch_worker.py. Rather than fight the factory, these tests build
models directly and mint the auth token locally.
"""
import pytest
from datetime import date, datetime, timedelta, timezone
from httpx import AsyncClient, ASGITransport

import models
from auth import create_access_token
from database import get_db
from main import app


# ---------------------------------------------------------------------------
# Local fixtures — sidestep the broken shared ones.
# ---------------------------------------------------------------------------
@pytest.fixture
def queue_user(db_session):
    """Create a test user directly. Factory-boy's session binding is
    latent-broken project-wide, so we do this by hand."""
    user = models.User(
        email="fresh_check_admin@example.com",
        hashed_password="x" * 60,
        full_name="Fresh Check Admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def other_user(db_session):
    """Second user used for cross-tenant isolation tests."""
    user = models.User(
        email="fresh_check_other@example.com",
        hashed_password="x" * 60,
        full_name="Other User",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
async def queue_client(db_session, queue_user):
    """Authenticated client bound to queue_user. The shared
    authenticated_client fixture in conftest relies on the broken
    factory path, so we wire our own. JWT `sub` is the user id (see
    auth.get_current_user)."""
    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    token = create_access_token(data={"sub": str(queue_user.id)})
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        follow_redirects=True,
    ) as client:
        client.headers["Authorization"] = f"Bearer {token}"
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
async def unauth_client(db_session):
    """Client with no Authorization header — for the 401 test."""
    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        follow_redirects=True,
    ) as client:
        yield client
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Helper: build an EmailQueue row with a Fresh Check decision pre-applied.
# ---------------------------------------------------------------------------
def _seed_queued_email(
    db_session,
    *,
    user,
    fresh_check_action=None,
    fresh_check_rule_triggered=None,
    fresh_check_reason=None,
    fresh_check_resume_date=None,
    status="cancelled",
    scheduled_at=None,
    rag_defer_count=3,
    error_message="Fresh Check stopped this email",
):
    """Defaults model what `_rag_presend_decision` writes on a STOP:
    status='cancelled' + populated fresh_check_* fields."""
    row = models.EmailQueue(
        user_id=user.id,
        recipient_email="prospect@example.com",
        recipient_name="Prospect",
        subject="Following up",
        body="Hi, circling back.",
        status=status,
        fresh_check_action=fresh_check_action,
        fresh_check_rule_triggered=fresh_check_rule_triggered,
        fresh_check_reason=fresh_check_reason,
        fresh_check_resume_date=fresh_check_resume_date,
        scheduled_at=scheduled_at
        or datetime.now(timezone.utc) + timedelta(days=7),
        rag_defer_count=rag_defer_count,
        error_message=error_message,
        retry_count=0,
        max_retries=3,
        created_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    db_session.add(row)
    db_session.commit()
    return row


# ---------------------------------------------------------------------------
# POST /emails/{id}/override-fresh-check
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
class TestOverrideFreshCheckEndpoint:
    """The override endpoint is the admin escape hatch from a Fresh Check
    STOP. It should succeed loudly on rewindable decisions, refuse on
    DNC + already-sent, and be airtight cross-tenant."""

    async def test_override_clears_decision_and_requeues(
        self, queue_client: AsyncClient, db_session, queue_user,
    ):
        """Happy path — cancel_sequence decision is cleared, status
        flipped back to pending, scheduled_at bumped to "now" so the
        worker picks the row up on the next cycle, defer streak reset."""
        future_sched = datetime.now(timezone.utc) + timedelta(days=14)
        email = _seed_queued_email(
            db_session,
            user=queue_user,
            fresh_check_action="cancel_sequence",
            fresh_check_rule_triggered="reply_received",
            fresh_check_reason="Prospect replied yesterday",
            status="cancelled",
            scheduled_at=future_sched,
            rag_defer_count=5,
        )

        response = await queue_client.post(
            f"/emails/{email.id}/override-fresh-check",
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["success"] is True
        assert "cancel_sequence" in body["message"]

        db_session.refresh(email)
        assert email.fresh_check_action is None
        assert email.fresh_check_rule_triggered is None
        assert email.fresh_check_reason is None
        assert email.fresh_check_resume_date is None
        assert email.error_message is None
        assert email.status == "pending"
        assert email.rag_defer_count == 0
        # scheduled_at rewound from +14 days to ~now. The endpoint uses
        # `datetime.utcnow()` which is tz-naive; SQLite round-trips
        # datetimes as naive too. Normalize both sides to naive UTC.
        sched_naive = email.scheduled_at
        if sched_naive.tzinfo is not None:
            sched_naive = sched_naive.replace(tzinfo=None)
        assert sched_naive < future_sched.replace(tzinfo=None)

    async def test_override_requeues_rescheduled_email(
        self, queue_client: AsyncClient, db_session, queue_user,
    ):
        """Reschedule stops leave status='pending' but with a moved
        scheduled_at — the override path should still unwind both the
        schedule and the audit fields."""
        resume = date.today() + timedelta(days=30)
        email = _seed_queued_email(
            db_session,
            user=queue_user,
            fresh_check_action="reschedule",
            fresh_check_rule_triggered="crm_change",
            fresh_check_reason="Deal pushed to next quarter",
            fresh_check_resume_date=resume,
            status="pending",
            scheduled_at=datetime.combine(
                resume, datetime.min.time(),
            ).replace(tzinfo=timezone.utc),
        )

        response = await queue_client.post(
            f"/emails/{email.id}/override-fresh-check",
        )

        assert response.status_code == 200
        db_session.refresh(email)
        assert email.fresh_check_action is None
        assert email.fresh_check_resume_date is None
        assert email.status == "pending"

    async def test_override_refuses_dnc_stop(
        self, queue_client: AsyncClient, db_session, queue_user,
    ):
        """DNC is rule 8 — locked-on by design. The override endpoint
        must refuse so an admin can't click past the safety net; the
        message should point them at the DNC flag instead."""
        email = _seed_queued_email(
            db_session,
            user=queue_user,
            fresh_check_action="cancel_sequence",
            fresh_check_rule_triggered="dnc",
            fresh_check_reason="Contact is Do Not Contact (contact)",
        )

        response = await queue_client.post(
            f"/emails/{email.id}/override-fresh-check",
        )

        assert response.status_code == 400
        detail = response.json()["detail"].lower()
        assert "dnc" in detail or "do not contact" in detail

        # State must be untouched on refusal.
        db_session.refresh(email)
        assert email.fresh_check_action == "cancel_sequence"
        assert email.fresh_check_rule_triggered == "dnc"
        assert email.status == "cancelled"

    async def test_override_refuses_already_sent(
        self, queue_client: AsyncClient, db_session, queue_user,
    ):
        """You can't un-send an email. Once status='sent', the override
        endpoint refuses even if fresh_check_action is populated (rare
        race but possible)."""
        email = _seed_queued_email(
            db_session,
            user=queue_user,
            fresh_check_action="cancel_sequence",
            fresh_check_rule_triggered="reply_received",
            status="sent",
        )

        response = await queue_client.post(
            f"/emails/{email.id}/override-fresh-check",
        )

        assert response.status_code == 400
        assert "sent" in response.json()["detail"].lower()

    async def test_override_refuses_when_no_fresh_check_action(
        self, queue_client: AsyncClient, db_session, queue_user,
    ):
        """An email that never went through the gate has nothing to
        override. 400 rather than silent success guards against
        accidental requeues from the UI."""
        email = _seed_queued_email(
            db_session,
            user=queue_user,
            fresh_check_action=None,
            fresh_check_rule_triggered=None,
            status="cancelled",
        )

        response = await queue_client.post(
            f"/emails/{email.id}/override-fresh-check",
        )

        assert response.status_code == 400
        detail = response.json()["detail"].lower()
        assert "override" in detail or "no fresh check" in detail

    async def test_override_returns_404_for_missing_email(
        self, queue_client: AsyncClient,
    ):
        response = await queue_client.post(
            "/emails/9999999/override-fresh-check",
        )
        assert response.status_code == 404

    async def test_override_refuses_other_users_email(
        self, queue_client: AsyncClient, db_session, queue_user, other_user,
    ):
        """Cross-tenant safety: the filter on user_id means another
        user's email must surface as 404, not 403 (the two are
        equivalent for the caller and avoid leaking existence)."""
        their_email = _seed_queued_email(
            db_session,
            user=other_user,
            fresh_check_action="cancel_sequence",
            fresh_check_rule_triggered="reply_received",
        )

        response = await queue_client.post(
            f"/emails/{their_email.id}/override-fresh-check",
        )
        assert response.status_code == 404

        # The other user's email state must be unchanged.
        db_session.refresh(their_email)
        assert their_email.fresh_check_action == "cancel_sequence"
        assert their_email.status == "cancelled"

    async def test_override_requires_authentication(
        self, unauth_client: AsyncClient, db_session, queue_user,
    ):
        """No Authorization header → denied. FastAPI's HTTPBearer
        returns 403 by default for missing credentials; accept either
        since both carry the same "unauthorized" semantic."""
        email = _seed_queued_email(
            db_session,
            user=queue_user,
            fresh_check_action="cancel_sequence",
            fresh_check_rule_triggered="reply_received",
        )
        response = await unauth_client.post(
            f"/emails/{email.id}/override-fresh-check",
        )
        assert response.status_code in (401, 403)


# ---------------------------------------------------------------------------
# GET /emails/ — verify the four new fresh_check_* fields surface through
# the Pydantic serializer. The queue-review UI depends on these being
# present whenever the DB row has them.
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
class TestEmailQueueItemFreshCheckSerialization:
    async def test_fresh_check_fields_surface_in_list_response(
        self, queue_client: AsyncClient, db_session, queue_user,
    ):
        resume = date(2026, 6, 15)
        _seed_queued_email(
            db_session,
            user=queue_user,
            fresh_check_action="reschedule",
            fresh_check_rule_triggered="crm_change",
            fresh_check_reason="Deal pushed — resume after close",
            fresh_check_resume_date=resume,
            status="pending",
        )

        response = await queue_client.get("/emails/")
        assert response.status_code == 200
        rows = response.json()
        assert len(rows) >= 1
        row = next(r for r in rows if r["fresh_check_action"] == "reschedule")
        assert row["fresh_check_rule_triggered"] == "crm_change"
        assert row["fresh_check_reason"] == "Deal pushed — resume after close"
        assert row["fresh_check_resume_date"] == resume.isoformat()

    async def test_fresh_check_fields_null_when_unset(
        self, queue_client: AsyncClient, db_session, queue_user,
    ):
        """Pre-gate emails (or emails that passed CONTINUE before T4
        landed the audit write) have null fresh_check fields. The
        serializer must render those as JSON null, not omit the key."""
        _seed_queued_email(
            db_session,
            user=queue_user,
            fresh_check_action=None,
            fresh_check_rule_triggered=None,
            fresh_check_reason=None,
            fresh_check_resume_date=None,
            status="pending",
        )

        response = await queue_client.get("/emails/")
        assert response.status_code == 200
        rows = response.json()
        assert len(rows) >= 1
        row = rows[0]
        assert "fresh_check_action" in row
        assert row["fresh_check_action"] is None
        assert "fresh_check_rule_triggered" in row
        assert row["fresh_check_rule_triggered"] is None
        assert row["fresh_check_reason"] is None
        assert row["fresh_check_resume_date"] is None

    async def test_same_thread_fields_surface_in_list_response(
        self, queue_client: AsyncClient, db_session, queue_user,
    ):
        parent = models.EmailQueue(
            user_id=queue_user.id,
            recipient_email="prospect@example.com",
            recipient_name="Prospect",
            subject="Intro",
            body="Hi there",
            status="sent",
            scheduled_at=datetime.now(timezone.utc) - timedelta(days=2),
            sent_at=datetime.now(timezone.utc) - timedelta(days=2),
            component_id=10,
            thread_id="thread-123",
            message_id_header="<parent@example.com>",
        )
        db_session.add(parent)
        db_session.flush()

        child = models.EmailQueue(
            user_id=queue_user.id,
            recipient_email="prospect@example.com",
            recipient_name="Prospect",
            subject="Follow-up",
            body="Circling back",
            status="pending",
            scheduled_at=datetime.now(timezone.utc) + timedelta(days=1),
            component_id=11,
            thread_id="thread-123",
            message_id_header="<child@example.com>",
            thread_parent_component_id=10,
            thread_parent_queue_id=parent.id,
            thread_fallback_reason="parent_not_sent",
        )
        db_session.add(child)
        db_session.commit()

        response = await queue_client.get("/emails/")
        assert response.status_code == 200
        rows = response.json()
        row = next(r for r in rows if r["id"] == child.id)
        assert row["thread_id"] == "thread-123"
        assert row["message_id_header"] == "<child@example.com>"
        assert row["thread_parent_component_id"] == 10
        assert row["thread_parent_queue_id"] == parent.id
        assert row["thread_fallback_reason"] == "parent_not_sent"
