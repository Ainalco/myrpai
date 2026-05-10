"""Integration tests for the Fresh Check T2 producers (#175).

Covers the two producers that have live call sites on this branch:

  1. The Pulse crossover producer — _maybe_emit_pulse_shift_embedding in
     contacts_service.py. Fires a [pulse] ContentEmbedding the moment a
     contact's sentiment/intent/engagement crosses into a negative state.
     The tests parametrize prior→new transitions so a drift in the
     crossover rule is caught before T3 consumes these tags.

  2. The Pipedrive deal-lost producer — _emit_deal_lost_org_signal in
     pipedrive_sync.py. Fires an [org_signal] ContentEmbedding when a
     deal's status changes to "lost", so sibling contacts at the same
     org see the signal on their next pre-send check.

The dormant producers (emit_cross_workflow_signal, emit_dnc_signal) have
no live call sites on this branch — tests for those land alongside the
reply-ingest / DNC-setter PRs that supply the call sites.

store_embeddings / emit_org_signal are mocked rather than exercised end
to end: these tests pin the *contract* (what gets emitted and when),
not the embedding backend which is covered elsewhere.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import models


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def organization(db_session):
    o = models.Organization(name="Test Org", slug="test-org")
    db_session.add(o)
    db_session.commit()
    return o


@pytest.fixture
def user(db_session, organization):
    u = models.User(
        email="seller@example.com",
        hashed_password="x" * 60,
        full_name="Seller",
        is_active=True,
        org_id=organization.id,
    )
    db_session.add(u)
    db_session.commit()
    return u


@pytest.fixture
def account(db_session, user):
    a = models.Account(org_id=user.org_id)
    db_session.add(a)
    db_session.commit()
    return a


@pytest.fixture
def contact_org(db_session, user):
    o = models.ContactOrganization(user_id=user.id, name="Prospect Co")
    db_session.add(o)
    db_session.commit()
    return o


@pytest.fixture
def contact(db_session, user, contact_org):
    c = models.Contact(
        user_id=user.id,
        email="prospect@example.com",
        name="Prospect Person",
        contact_organization_id=contact_org.id,
    )
    db_session.add(c)
    db_session.commit()
    return c


# ---------------------------------------------------------------------------
# Pulse crossover producer
# ---------------------------------------------------------------------------
class TestPulseCrossover:
    """_maybe_emit_pulse_shift_embedding dispatches iff the new Pulse state
    crosses *into* a negative bucket from a non-negative prior.

    The tests mock _dispatch_pulse_embedding so we test the crossover rule
    in isolation — the dispatch path (asyncio task or thread pool) is
    covered by the activity-embed scheduler tests."""

    @staticmethod
    def _pulse(sentiment=None, intent=None, engagement=None, summary="ok"):
        p = models.ContactPulse()
        p.sentiment = sentiment
        p.intent = intent
        p.engagement_level = engagement
        p.summary = summary
        return p

    @staticmethod
    def _now():
        return datetime(2026, 4, 24, 12, 0, tzinfo=timezone.utc)

    def _call(
        self, db_session, user, contact,
        *, prev_sent=None, prev_intent=None, prev_eng=None,
        new_sent=None, new_intent=None, new_eng=None,
    ):
        """Invoke the producer with a captured dispatch mock. Returns the
        mock so callers can assert_called / assert_not_called and inspect
        the dispatched summary_text."""
        from contacts_service import _maybe_emit_pulse_shift_embedding

        new_pulse = self._pulse(
            sentiment=new_sent, intent=new_intent, engagement=new_eng,
            summary="summary text",
        )

        with patch("contacts_service._dispatch_pulse_embedding") as mock_dispatch:
            _maybe_emit_pulse_shift_embedding(
                db=db_session,
                user_id=user.id,
                contact=contact,
                prev_sentiment=prev_sent,
                prev_intent=prev_intent,
                prev_engagement=prev_eng,
                new_pulse=new_pulse,
                now=self._now(),
            )
        return mock_dispatch

    # -----------------------------------------------------------------
    # Sentiment path
    # -----------------------------------------------------------------
    def test_positive_to_negative_fires(self, db_session, user, account, contact):
        mock = self._call(db_session, user, contact, prev_sent="positive", new_sent="negative")
        mock.assert_called_once()
        kwargs = mock.call_args.kwargs
        assert kwargs["account_id"] == account.id
        assert kwargs["contact_id"] == contact.id
        assert kwargs["org_id"] == contact.contact_organization_id
        assert "[pulse]" in kwargs["summary_text"]
        assert "sentiment positive → negative" in kwargs["summary_text"]

    def test_neutral_to_negative_fires(self, db_session, user, account, contact):
        mock = self._call(db_session, user, contact, prev_sent="neutral", new_sent="negative")
        mock.assert_called_once()

    def test_none_to_negative_fires(self, db_session, user, account, contact):
        """Fresh pulse (no prior) + first read is negative → fire. Docs
        say we treat "no prior" as if it were previously positive."""
        mock = self._call(db_session, user, contact, prev_sent=None, new_sent="negative")
        mock.assert_called_once()
        assert "sentiment unknown → negative" in mock.call_args.kwargs["summary_text"]

    def test_already_negative_does_not_fire(self, db_session, user, account, contact):
        """No crossover — already negative. Avoids spamming [pulse] on
        every hourly refresh of a persistently-negative contact."""
        mock = self._call(db_session, user, contact, prev_sent="negative", new_sent="negative")
        mock.assert_not_called()

    def test_positive_stays_positive(self, db_session, user, account, contact):
        mock = self._call(db_session, user, contact, prev_sent="positive", new_sent="positive")
        mock.assert_not_called()

    def test_sentiment_case_insensitive(self, db_session, user, account, contact):
        """Upstream AI responses have drifted in case before. Be permissive."""
        mock = self._call(db_session, user, contact, prev_sent="Positive", new_sent="Negative")
        mock.assert_called_once()

    # -----------------------------------------------------------------
    # Intent path
    # -----------------------------------------------------------------
    def test_intent_not_interested_crossover_fires(self, db_session, user, account, contact):
        mock = self._call(
            db_session, user, contact,
            prev_intent="evaluating", new_intent="not_interested",
        )
        mock.assert_called_once()
        assert "intent evaluating → not_interested" in mock.call_args.kwargs["summary_text"]

    def test_intent_stays_not_interested_does_not_fire(self, db_session, user, account, contact):
        mock = self._call(
            db_session, user, contact,
            prev_intent="not_interested", new_intent="not_interested",
        )
        mock.assert_not_called()

    # -----------------------------------------------------------------
    # Engagement path — the soft signal, gated by sentiment
    # -----------------------------------------------------------------
    def test_engagement_low_with_non_positive_sentiment_fires(self, db_session, user, account, contact):
        """engagement crossover + non-positive sentiment → fire. This is
        the "contact went quiet and isn't happy" signal."""
        mock = self._call(
            db_session, user, contact,
            prev_eng="medium", new_eng="low",
            new_sent="neutral",
        )
        mock.assert_called_once()

    def test_engagement_low_with_positive_sentiment_does_not_fire(
        self, db_session, user, account, contact,
    ):
        """Brand-new contact with "low" engagement + "positive" sentiment
        is a cold lead, not a negative signal. Suppressing this prevents
        [pulse] chatter on every new contact."""
        mock = self._call(
            db_session, user, contact,
            prev_eng="high", new_eng="low",
            new_sent="positive",
        )
        mock.assert_not_called()

    def test_engagement_stays_low_does_not_fire(self, db_session, user, account, contact):
        mock = self._call(
            db_session, user, contact,
            prev_eng="low", new_eng="low",
            new_sent="negative",  # sentiment is crossover material — but prev here is None so it also fires
            prev_sent="negative",  # make prev also negative so neither axis crosses
        )
        mock.assert_not_called()

    # -----------------------------------------------------------------
    # Resolution failures — no-op, never raise
    # -----------------------------------------------------------------
    def test_user_without_org_id_does_not_fire(self, db_session, contact_org):
        """If we can't resolve an account_id, the producer silently
        no-ops. Misconfigured users must not block Pulse generation."""
        from contacts_service import _maybe_emit_pulse_shift_embedding

        lone_user = models.User(
            email="lone@example.com",
            hashed_password="x" * 60,
            full_name="Lone",
            is_active=True,
            org_id=None,
        )
        db_session.add(lone_user)
        db_session.flush()  # assign lone_user.id before FK-referencing it
        lone_contact = models.Contact(
            user_id=lone_user.id,
            email="p@example.com",
            name="P",
        )
        db_session.add(lone_contact)
        db_session.commit()

        new_pulse = self._pulse(sentiment="negative")
        with patch("contacts_service._dispatch_pulse_embedding") as mock_dispatch:
            _maybe_emit_pulse_shift_embedding(
                db=db_session,
                user_id=lone_user.id,
                contact=lone_contact,
                prev_sentiment="positive",
                prev_intent=None,
                prev_engagement=None,
                new_pulse=new_pulse,
                now=self._now(),
            )
        mock_dispatch.assert_not_called()

    def test_no_account_row_does_not_fire(self, db_session, user, contact):
        """User has org_id but no Account row → no account_id → no fire.
        Deliberately skip the `account` fixture so no Account exists."""
        from contacts_service import _maybe_emit_pulse_shift_embedding

        new_pulse = self._pulse(sentiment="negative")
        with patch("contacts_service._dispatch_pulse_embedding") as mock_dispatch:
            _maybe_emit_pulse_shift_embedding(
                db=db_session,
                user_id=user.id,
                contact=contact,
                prev_sentiment="positive",
                prev_intent=None,
                prev_engagement=None,
                new_pulse=new_pulse,
                now=self._now(),
            )
        mock_dispatch.assert_not_called()


# ---------------------------------------------------------------------------
# Pipedrive deal-lost producer
# ---------------------------------------------------------------------------
class TestDealLostOrgSignal:
    """_emit_deal_lost_org_signal is the on-ramp from the Pipedrive sync
    into rag_service.emit_org_signal. We mock emit_org_signal so the
    tests stay out of OpenAI / SessionLocal territory and focus on:

      - the correct account_id / org_id / originating_contact_id
      - a deterministic source_id that dedupes on re-sync
      - the signal_text shape that T3 will read off the snapshot
      - no-op behavior when contact has no org, user has no org, or no
        Account row exists
    """

    @pytest.mark.asyncio
    async def test_lost_deal_emits_org_signal(self, db_session, user, account, contact, contact_org):
        from pipedrive_sync import _emit_deal_lost_org_signal

        with patch("rag_service.emit_org_signal", new_callable=AsyncMock) as mock_emit:
            await _emit_deal_lost_org_signal(
                db=db_session,
                user_id=user.id,
                contact_id=contact.id,
                deal_external_id="12345",
                deal_title="Acme SOW",
            )

        mock_emit.assert_awaited_once()
        kwargs = mock_emit.await_args.kwargs
        assert kwargs["account_id"] == account.id
        assert kwargs["org_id"] == contact_org.id
        assert kwargs["originating_contact_id"] == contact.id
        assert kwargs["source_id"] == "org_signal:deal_lost:12345"
        assert "Acme SOW" in kwargs["signal_text"]
        assert "lost" in kwargs["signal_text"].lower()

    @pytest.mark.asyncio
    async def test_source_id_is_deterministic(self, db_session, user, account, contact, contact_org):
        """Same deal_external_id must produce the same source_id across
        re-sync so the uq_embedding_source_chunk constraint dedupes the
        ContentEmbedding row instead of doubling it up."""
        from pipedrive_sync import _emit_deal_lost_org_signal

        source_ids = []
        with patch("rag_service.emit_org_signal", new_callable=AsyncMock) as mock_emit:
            for _ in range(3):
                await _emit_deal_lost_org_signal(
                    db=db_session,
                    user_id=user.id,
                    contact_id=contact.id,
                    deal_external_id="stable-deal-id",
                    deal_title="Same Deal",
                )
            for call in mock_emit.await_args_list:
                source_ids.append(call.kwargs["source_id"])

        assert len(set(source_ids)) == 1, f"source_id drifted across calls: {source_ids}"

    @pytest.mark.asyncio
    async def test_missing_deal_id_falls_back_to_synthetic_source_id(
        self, db_session, user, account, contact, contact_org,
    ):
        """Pipedrive has returned empty IDs in historical outages. The
        fallback source_id uses (contact_id, org_id) so at least we
        don't crash — the trade-off is we may dedupe two distinct
        unknown-id losses into one row. Acceptable for a rare path."""
        from pipedrive_sync import _emit_deal_lost_org_signal

        with patch("rag_service.emit_org_signal", new_callable=AsyncMock) as mock_emit:
            await _emit_deal_lost_org_signal(
                db=db_session,
                user_id=user.id,
                contact_id=contact.id,
                deal_external_id="",
                deal_title="Unknown deal",
            )

        mock_emit.assert_awaited_once()
        source_id = mock_emit.await_args.kwargs["source_id"]
        assert source_id.startswith("org_signal:deal_lost:")
        assert f"c{contact.id}" in source_id
        assert f"d{contact_org.id}" in source_id

    @pytest.mark.asyncio
    async def test_contact_without_org_is_noop(self, db_session, user, account):
        """A contact not yet linked to a ContactOrganization has nothing
        to key the org signal to — skip the emit rather than writing a
        row with org_id=NULL that sibling contacts can't match."""
        from pipedrive_sync import _emit_deal_lost_org_signal

        orgless = models.Contact(
            user_id=user.id,
            email="solo@example.com",
            name="Solo Person",
            contact_organization_id=None,
        )
        db_session.add(orgless)
        db_session.commit()

        with patch("rag_service.emit_org_signal", new_callable=AsyncMock) as mock_emit:
            await _emit_deal_lost_org_signal(
                db=db_session,
                user_id=user.id,
                contact_id=orgless.id,
                deal_external_id="99",
                deal_title="Orgless Deal",
            )

        mock_emit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_user_without_org_id_is_noop(self, db_session, contact_org):
        """User must have an org_id to resolve an Account — otherwise we
        have no account_id to write the embedding under."""
        from pipedrive_sync import _emit_deal_lost_org_signal

        orgless_user = models.User(
            email="lone@example.com",
            hashed_password="x" * 60,
            full_name="Lone",
            is_active=True,
            org_id=None,
        )
        db_session.add(orgless_user)
        db_session.flush()  # assign orgless_user.id before FK-referencing it
        lone_contact = models.Contact(
            user_id=orgless_user.id,
            email="p@example.com",
            contact_organization_id=contact_org.id,
        )
        db_session.add(lone_contact)
        db_session.commit()

        with patch("rag_service.emit_org_signal", new_callable=AsyncMock) as mock_emit:
            await _emit_deal_lost_org_signal(
                db=db_session,
                user_id=orgless_user.id,
                contact_id=lone_contact.id,
                deal_external_id="99",
                deal_title="Deal",
            )

        mock_emit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_account_row_is_noop(self, db_session, user, contact):
        """User.org_id is set but no Account row exists for it. Skip the
        `account` fixture deliberately to make this happen."""
        from pipedrive_sync import _emit_deal_lost_org_signal

        with patch("rag_service.emit_org_signal", new_callable=AsyncMock) as mock_emit:
            await _emit_deal_lost_org_signal(
                db=db_session,
                user_id=user.id,
                contact_id=contact.id,
                deal_external_id="99",
                deal_title="Deal",
            )

        mock_emit.assert_not_awaited()
