"""Regression tests for email_service._rag_presend_decision (T3 #176).

The Fresh Check pre-send gate has three structural invariants these
tests protect:

  1. **Tool-calling, never text parsing.** Haiku picks STOP/CONTINUE and
     Sonnet picks the action via Anthropic tool_use blocks. Any response
     missing the expected tool block, or with fields outside the enum,
     defers rather than interpreting free text. This is the
     prompt-injection boundary — adversarial reply content cannot drift
     the model into a fake "CONTINUE" because the only thing we read is
     the tool input dict.

  2. **DNC is always enforced.** Two gates: a deterministic DB-flag
     short-circuit (T1 #174) before any AI call, and an extended
     snapshot-[dnc] scan after the snapshot fetch but before Haiku. The
     DNC rule is locked-on regardless of workflow toggle state.

  3. **Anthropic outages don't ship stale email.** Timeouts, 5xxs, and
     malformed tool responses all route through _defer_or_fallback so
     scheduled_at is bumped. Only after N consecutive defers do we fall
     through to sending, to avoid pinning the queue during a sustained
     outage.

No real network calls are made; httpx.AsyncClient is mocked with
AsyncMock.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

import email_service
import models
from email_service import (
    PRESEND_CONTINUE,
    PRESEND_DEFER,
    PRESEND_FALLBACK,
    PRESEND_HOLD,
    _build_active_rules,
    _defer_or_fallback,
    _extract_tool_input,
    _FRESH_CHECK_ACTION_TOOL,
    _FRESH_CHECK_DECISION_TOOL,
    _PRESEND_REASON_MAX_LEN,
    _rag_presend_decision,
    _sanitize_persisted_text,
)


# ---------------------------------------------------------------------------
# _sanitize_persisted_text — defense-in-depth scrub for free text we
# render to admins. Issue #139. Still live after T3 for
# triggering_event / reasoning pulled from tool inputs.
# ---------------------------------------------------------------------------


def _naive(dt):
    """SQLite stores datetimes as TEXT and drops tzinfo on round-trip,
    so tz-aware values compared after a db_session.commit()+refresh come
    back naive. Normalize both sides for stable comparisons."""
    if dt is None or dt.tzinfo is None:
        return dt
    return dt.replace(tzinfo=None)


class TestSanitizePersistedText:
    def test_empty_returns_empty(self):
        assert _sanitize_persisted_text("", 200) == ""
        assert _sanitize_persisted_text(None, 200) == ""  # type: ignore[arg-type]

    def test_strips_html_tags(self):
        out = _sanitize_persisted_text("<script>x</script>hi <b>there</b>", 200)
        assert "<" not in out and ">" not in out
        assert "x" in out and "hi" in out and "there" in out

    def test_strips_control_chars(self):
        out = _sanitize_persisted_text("a\x00b\x07c\x1bd\x7fe", 200)
        assert out == "abcde"

    def test_collapses_whitespace(self):
        assert _sanitize_persisted_text("  a   b\n\t\nc  ", 200) == "a b c"

    def test_truncates_with_ellipsis(self):
        out = _sanitize_persisted_text("X" * 5000, 200)
        assert len(out) == 200
        assert out.endswith("…")

    def test_short_input_unchanged(self):
        assert _sanitize_persisted_text("ok", 200) == "ok"


# ---------------------------------------------------------------------------
# _build_active_rules — reads workflow.rag_settings.fresh_check, appends
# DNC regardless of toggle state.
# ---------------------------------------------------------------------------
class TestBuildActiveRules:
    def test_none_workflow_defaults_all_on(self):
        """Callers pass None when workflow_id is missing. Every rule
        (plus DNC) must be active — matches FreshCheckSettings defaults."""
        rules = _build_active_rules(None)
        ids = [r["id"] for r in rules]
        assert "dnc" in ids  # locked-on
        assert "reply_received" in ids
        assert "pulse_shift" in ids
        assert len(rules) == 8  # 7 togglable + DNC

    def test_explicit_off_removes_rule_but_keeps_dnc(self):
        wf = MagicMock()
        wf.rag_settings = {"fresh_check": {"reply_received": False, "pulse_shift": False}}
        rules = _build_active_rules(wf)
        ids = [r["id"] for r in rules]
        assert "reply_received" not in ids
        assert "pulse_shift" not in ids
        assert "dnc" in ids  # locked-on regardless of toggles
        assert "activity_logged" in ids  # other toggles default True

    def test_dnc_cannot_be_disabled(self):
        """Even an explicit fresh_check.dnc=False does not remove DNC —
        the DNC entry is appended unconditionally."""
        wf = MagicMock()
        wf.rag_settings = {"fresh_check": {"dnc": False}}
        ids = [r["id"] for r in _build_active_rules(wf)]
        assert "dnc" in ids

    def test_non_dict_rag_settings_defaults_all_on(self):
        """Legacy or mis-serialized rag_settings must not poison the
        rule list — treat as empty and default all toggles on."""
        wf = MagicMock()
        wf.rag_settings = "not a dict"
        rules = _build_active_rules(wf)
        assert len(rules) == 8


# ---------------------------------------------------------------------------
# _extract_tool_input — pulls tool_use blocks out of Anthropic responses.
# ---------------------------------------------------------------------------
class TestExtractToolInput:
    def test_returns_first_matching_tool_input(self):
        data = {
            "content": [
                {"type": "text", "text": "preamble"},
                {"type": "tool_use", "name": "make_fresh_check_decision", "input": {"decision": "STOP"}},
            ],
        }
        out = _extract_tool_input(data, "make_fresh_check_decision")
        assert out == {"decision": "STOP"}

    def test_returns_none_when_tool_absent(self):
        data = {"content": [{"type": "text", "text": "hi"}]}
        assert _extract_tool_input(data, "make_fresh_check_decision") is None

    def test_returns_none_on_name_mismatch(self):
        data = {"content": [{"type": "tool_use", "name": "other_tool", "input": {}}]}
        assert _extract_tool_input(data, "make_fresh_check_decision") is None

    def test_returns_none_when_input_is_not_dict(self):
        data = {"content": [{"type": "tool_use", "name": "make_fresh_check_decision", "input": "bad"}]}
        assert _extract_tool_input(data, "make_fresh_check_decision") is None

    def test_returns_none_on_malformed_payload(self):
        assert _extract_tool_input({}, "any") is None
        assert _extract_tool_input({"content": None}, "any") is None


# ---------------------------------------------------------------------------
# Fixtures
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
def contact(db_session, user, account):
    c = models.Contact(
        user_id=user.id,
        email="prospect@example.com",
        contact_organization_id=None,
    )
    db_session.add(c)
    db_session.commit()
    return c


@pytest.fixture
def email_row(db_session, user, contact):
    now = datetime.now(timezone.utc)
    e = models.EmailQueue(
        user_id=user.id,
        contact_id=contact.id,
        recipient_email="prospect@example.com",
        subject="Following up",
        body="Hi, circling back.",
        scheduled_at=now,
        status="pending",
        created_at=now - timedelta(minutes=10),
        rag_defer_count=0,
    )
    db_session.add(e)
    db_session.commit()
    return e


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------
def _haiku_tool_response(
    *,
    decision: str,
    rule_triggered: str = "reply_received",
    triggering_event: str = "Contact replied yesterday",
) -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status = MagicMock(return_value=None)
    resp.json = MagicMock(return_value={
        "content": [{
            "type": "tool_use",
            "id": "toolu_haiku",
            "name": "make_fresh_check_decision",
            "input": {
                "decision": decision,
                "rule_triggered": rule_triggered,
                "triggering_event": triggering_event,
            },
        }],
        "stop_reason": "tool_use",
    })
    return resp


def _sonnet_tool_response(
    *,
    action: str,
    reasoning: str = "Stale signal",
    resume_date: str = "",
) -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status = MagicMock(return_value=None)
    resp.json = MagicMock(return_value={
        "content": [{
            "type": "tool_use",
            "id": "toolu_sonnet",
            "name": "pick_fresh_check_action",
            "input": {
                "action": action,
                "reasoning": reasoning,
                "resume_date": resume_date,
            },
        }],
        "stop_reason": "tool_use",
    })
    return resp


def _text_only_response(text: str = "some drifted text") -> MagicMock:
    """Anthropic response WITHOUT a tool_use block — should always
    defer under the tool-calling contract."""
    resp = MagicMock()
    resp.raise_for_status = MagicMock(return_value=None)
    resp.json = MagicMock(return_value={
        "content": [{"type": "text", "text": text}],
        "stop_reason": "end_turn",
    })
    return resp


def _fake_httpx_client(*, response=None, responses=None, exc=None):
    """AsyncClient factory. Pass either a single `response`, a list of
    `responses` consumed in order (Haiku then Sonnet), or an `exc` to
    raise from .post()."""
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    if exc is not None:
        client.post = AsyncMock(side_effect=exc)
    elif responses is not None:
        client.post = AsyncMock(side_effect=responses)
    else:
        client.post = AsyncMock(return_value=response)
    return MagicMock(return_value=client)


def _fake_snapshot(
    has_contact_signal: bool = True,
    has_org_signal: bool = False,
    formatted: str = "- activity [2026-04-24]: Contact replied yesterday",
) -> dict:
    return {
        "has_contact_signal": has_contact_signal,
        "has_org_signal": has_org_signal,
        "formatted": formatted,
        "org_signals": "",
    }


@pytest.fixture(autouse=True)
def _anthropic_api_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")


@pytest.fixture
def patched_rag(monkeypatch):
    """Stub rag_service so tests don't hit the vector store."""
    import rag_service
    monkeypatch.setattr(
        rag_service, "get_presend_snapshot",
        AsyncMock(return_value=_fake_snapshot()),
    )
    monkeypatch.setattr(rag_service, "get_sonnet_model", MagicMock(return_value="sonnet-test"))
    monkeypatch.setattr(rag_service, "get_haiku_model", MagicMock(return_value="haiku-test"))
    return rag_service


@pytest.fixture
def patched_config(monkeypatch):
    import system_config

    def _fake(key, _db, default=0):
        return {
            "rag.presend_defer_max": 3,
            "rag.presend_defer_delay_seconds": 300,
        }.get(key, default)

    monkeypatch.setattr(system_config, "get_config_int", _fake)
    return system_config


# ---------------------------------------------------------------------------
# _defer_or_fallback (unchanged behavior from T1).
# ---------------------------------------------------------------------------
class TestDeferOrFallback:
    def test_first_defer_reschedules(self, db_session, email_row, patched_config):
        before = email_row.scheduled_at
        result = _defer_or_fallback(db_session, email_row, reason="timeout")
        assert result == PRESEND_DEFER
        assert email_row.rag_defer_count == 1
        assert email_row.scheduled_at > before

    def test_falls_back_after_max(self, db_session, email_row, patched_config):
        email_row.rag_defer_count = 3
        db_session.commit()
        pre_sched = email_row.scheduled_at
        result = _defer_or_fallback(db_session, email_row, reason="timeout")
        assert result == PRESEND_FALLBACK
        assert email_row.rag_defer_count == 4
        assert email_row.scheduled_at == pre_sched


# ---------------------------------------------------------------------------
# Fresh Check tool-calling — Haiku/Sonnet happy paths and error handling.
# ---------------------------------------------------------------------------
class TestFreshCheckTooling:
    @pytest.mark.asyncio
    async def test_haiku_continue_skips_sonnet(
        self, db_session, user, account, contact, email_row, patched_rag, patched_config,
    ):
        """Haiku says CONTINUE → Sonnet is never called ($0 saved on
        every clean email). The $ path matters at scale. T4 (#177) also
        persists a CONTINUE audit trail so the queue-review UI shows a
        Fresh Check pass on every gated email, not just stops."""
        factory = _fake_httpx_client(responses=[_haiku_tool_response(
            decision="CONTINUE", rule_triggered="none", triggering_event="",
        )])
        with patch("httpx.AsyncClient", factory):
            result = await _rag_presend_decision(db_session, email_row, user)

        assert result == PRESEND_CONTINUE
        assert email_row.status == "pending"
        assert email_row.fresh_check_action == "continue"
        assert email_row.fresh_check_rule_triggered == "none"
        assert email_row.fresh_check_reason  # non-empty audit reason
        # Only ONE post call (Haiku). If Sonnet got called the factory
        # would burn through its single scripted response and raise.
        assert factory.return_value.post.call_count == 1

    @pytest.mark.asyncio
    async def test_haiku_stop_triggers_sonnet_and_cancels(
        self, db_session, user, account, contact, email_row, patched_rag, patched_config,
    ):
        """Haiku STOP + Sonnet cancel_sequence → email cancelled, HOLD
        returned, audit fields persisted for T4 to cascade from."""
        factory = _fake_httpx_client(responses=[
            _haiku_tool_response(
                decision="STOP", rule_triggered="reply_received",
                triggering_event="Prospect replied yesterday",
            ),
            _sonnet_tool_response(
                action="cancel_sequence",
                reasoning="Prospect said not interested",
            ),
        ])
        with patch("httpx.AsyncClient", factory):
            result = await _rag_presend_decision(db_session, email_row, user)

        assert result == PRESEND_HOLD
        assert email_row.status == "cancelled"
        assert email_row.fresh_check_action == "cancel_sequence"
        assert email_row.fresh_check_rule_triggered == "reply_received"
        assert "not interested" in (email_row.fresh_check_reason or "")
        assert email_row.rag_defer_count == 0
        assert factory.return_value.post.call_count == 2

    @pytest.mark.asyncio
    async def test_haiku_stop_reschedule_bumps_scheduled_at_preserving_time_of_day(
        self, db_session, user, account, contact, email_row, patched_rag, patched_config,
    ):
        """Sonnet action=reschedule moves scheduled_at to the resume_date
        but preserves the original hour:minute — spec §07 requires
        time-of-day preservation so "morning send" stays a morning send
        after the shift."""
        # Lock a known scheduled_at so the time-of-day preservation is
        # observable.
        email_row.scheduled_at = datetime(2026, 4, 24, 9, 30, tzinfo=timezone.utc)
        db_session.commit()

        factory = _fake_httpx_client(responses=[
            _haiku_tool_response(
                decision="STOP", rule_triggered="crm_change",
                triggering_event="Deal pushed to next quarter",
            ),
            _sonnet_tool_response(
                action="reschedule",
                reasoning="Resume after deal close",
                resume_date="2026-06-15",
            ),
        ])
        with patch("httpx.AsyncClient", factory):
            result = await _rag_presend_decision(db_session, email_row, user)

        assert result == PRESEND_HOLD
        assert email_row.status == "pending"  # rescheduled, not cancelled
        assert email_row.fresh_check_action == "reschedule"
        assert email_row.fresh_check_resume_date is not None
        assert email_row.fresh_check_resume_date.isoformat() == "2026-06-15"
        # Time-of-day preserved.
        assert email_row.scheduled_at.hour == 9
        assert email_row.scheduled_at.minute == 30
        assert email_row.scheduled_at.date().isoformat() == "2026-06-15"

    @pytest.mark.asyncio
    async def test_missing_haiku_tool_block_defers(
        self, db_session, user, account, contact, email_row, patched_rag, patched_config,
    ):
        """Tool-calling contract: a text-only response is drift. Defer
        rather than try to interpret free text."""
        factory = _fake_httpx_client(responses=[_text_only_response("DECISION: CONTINUE")])
        with patch("httpx.AsyncClient", factory):
            result = await _rag_presend_decision(db_session, email_row, user)

        assert result == PRESEND_DEFER
        assert email_row.status == "pending"
        assert email_row.rag_defer_count == 1

    @pytest.mark.asyncio
    async def test_haiku_stop_with_invalid_rule_defers(
        self, db_session, user, account, contact, email_row, patched_rag, patched_config,
    ):
        """A STOP verdict with rule_triggered='none' is internally
        inconsistent — defer so the admin can investigate rather than
        cancel a real email on a ghost."""
        factory = _fake_httpx_client(responses=[_haiku_tool_response(
            decision="STOP", rule_triggered="none", triggering_event="???",
        )])
        with patch("httpx.AsyncClient", factory):
            result = await _rag_presend_decision(db_session, email_row, user)

        assert result == PRESEND_DEFER

    @pytest.mark.asyncio
    async def test_haiku_unexpected_decision_defers(
        self, db_session, user, account, contact, email_row, patched_rag, patched_config,
    ):
        """A decision value outside {CONTINUE, STOP} means the tool
        schema's enum was ignored — defer."""
        factory = _fake_httpx_client(responses=[_haiku_tool_response(
            decision="MAYBE", rule_triggered="reply_received",
        )])
        with patch("httpx.AsyncClient", factory):
            result = await _rag_presend_decision(db_session, email_row, user)

        assert result == PRESEND_DEFER

    @pytest.mark.asyncio
    async def test_missing_sonnet_tool_block_defers(
        self, db_session, user, account, contact, email_row, patched_rag, patched_config,
    ):
        """Haiku STOP → Sonnet text-only response → defer. Critically,
        the email is NOT cancelled — the admin will see it re-queued."""
        factory = _fake_httpx_client(responses=[
            _haiku_tool_response(decision="STOP"),
            _text_only_response("I think we should cancel"),
        ])
        with patch("httpx.AsyncClient", factory):
            result = await _rag_presend_decision(db_session, email_row, user)

        assert result == PRESEND_DEFER
        assert email_row.status == "pending"  # NOT cancelled
        assert email_row.fresh_check_action is None

    @pytest.mark.asyncio
    async def test_sonnet_invalid_action_defers(
        self, db_session, user, account, contact, email_row, patched_rag, patched_config,
    ):
        factory = _fake_httpx_client(responses=[
            _haiku_tool_response(decision="STOP"),
            _sonnet_tool_response(action="delete_everything", reasoning="oops"),
        ])
        with patch("httpx.AsyncClient", factory):
            result = await _rag_presend_decision(db_session, email_row, user)

        assert result == PRESEND_DEFER
        assert email_row.fresh_check_action is None

    @pytest.mark.asyncio
    async def test_sonnet_reschedule_with_missing_date_defers(
        self, db_session, user, account, contact, email_row, patched_rag, patched_config,
    ):
        """reschedule without a parseable resume_date is unactionable —
        defer rather than pick an arbitrary date or fall through."""
        factory = _fake_httpx_client(responses=[
            _haiku_tool_response(decision="STOP"),
            _sonnet_tool_response(action="reschedule", resume_date=""),
        ])
        with patch("httpx.AsyncClient", factory):
            result = await _rag_presend_decision(db_session, email_row, user)

        assert result == PRESEND_DEFER

    @pytest.mark.asyncio
    async def test_sonnet_reschedule_with_non_iso_date_defers(
        self, db_session, user, account, contact, email_row, patched_rag, patched_config,
    ):
        factory = _fake_httpx_client(responses=[
            _haiku_tool_response(decision="STOP"),
            _sonnet_tool_response(action="reschedule", resume_date="next tuesday"),
        ])
        with patch("httpx.AsyncClient", factory):
            result = await _rag_presend_decision(db_session, email_row, user)

        assert result == PRESEND_DEFER

    @pytest.mark.asyncio
    async def test_haiku_timeout_defers(
        self, db_session, user, account, contact, email_row, patched_rag, patched_config,
    ):
        """Haiku network failure → defer, do not send."""
        factory = _fake_httpx_client(exc=httpx.ReadTimeout("timeout"))
        with patch("httpx.AsyncClient", factory):
            result = await _rag_presend_decision(db_session, email_row, user)
        assert result == PRESEND_DEFER
        assert email_row.status == "pending"

    @pytest.mark.asyncio
    async def test_sonnet_timeout_defers(
        self, db_session, user, account, contact, email_row, patched_rag, patched_config,
    ):
        """Haiku returns STOP cleanly → Sonnet times out → defer. Email
        must NOT be cancelled on a transient outage mid-chain."""
        factory = _fake_httpx_client(responses=[
            _haiku_tool_response(decision="STOP"),
            httpx.ReadTimeout("sonnet timeout"),
        ])
        with patch("httpx.AsyncClient", factory):
            result = await _rag_presend_decision(db_session, email_row, user)
        assert result == PRESEND_DEFER
        assert email_row.status == "pending"

    @pytest.mark.asyncio
    async def test_triggering_event_strips_html_before_persist(
        self, db_session, user, account, contact, email_row, patched_rag, patched_config,
    ):
        """Adversarial HTML in Sonnet's `reasoning` (the field that ends
        up as `fresh_check_reason`) must be scrubbed before persist —
        admins view this text in the queue-review UI. Issue #139
        guardrail carried over. _rag_presend_decision prefers
        `reasoning` over `triggering_event`, so this test pins the
        sanitization on the field that actually lands in the DB."""
        factory = _fake_httpx_client(responses=[
            _haiku_tool_response(
                decision="STOP", rule_triggered="reply_received",
                triggering_event="prospect replied angrily",
            ),
            _sonnet_tool_response(
                action="cancel_sequence",
                reasoning="<script>alert('xss')</script>reply was negative <b>and</b> rude",
            ),
        ])
        with patch("httpx.AsyncClient", factory):
            result = await _rag_presend_decision(db_session, email_row, user)

        assert result == PRESEND_HOLD
        persisted = " ".join([
            email_row.fresh_check_reason or "",
            email_row.error_message or "",
        ])
        assert "<script>" not in persisted
        assert "<b>" not in persisted
        assert "alert('xss')" in persisted  # tags stripped, inert text retained
        assert "reply was negative" in persisted

    @pytest.mark.asyncio
    async def test_reason_truncated_to_cap(
        self, db_session, user, account, contact, email_row, patched_rag, patched_config,
    ):
        """A 5000-char reasoning (e.g. injected paragraph of phishing
        content) must be truncated before persist."""
        long = "A" * 5000
        factory = _fake_httpx_client(responses=[
            _haiku_tool_response(decision="STOP", rule_triggered="reply_received"),
            _sonnet_tool_response(action="cancel_sequence", reasoning=long),
        ])
        with patch("httpx.AsyncClient", factory):
            await _rag_presend_decision(db_session, email_row, user)

        persisted_reason = email_row.fresh_check_reason or ""
        assert len(persisted_reason) <= _PRESEND_REASON_MAX_LEN
        assert "AAAA" in persisted_reason

    @pytest.mark.asyncio
    async def test_defer_streak_eventually_falls_back(
        self, db_session, user, account, contact, email_row, patched_rag, patched_config,
    ):
        """After max defers the gate stops deferring and lets the send
        proceed — otherwise a sustained Anthropic outage would pin every
        email in the queue forever."""
        factory = _fake_httpx_client(exc=httpx.ReadTimeout("timeout"))

        results = []
        with patch("httpx.AsyncClient", factory):
            for _ in range(5):
                results.append(await _rag_presend_decision(db_session, email_row, user))

        assert results[:3] == [PRESEND_DEFER, PRESEND_DEFER, PRESEND_DEFER]
        assert PRESEND_FALLBACK in results[3:]

    @pytest.mark.asyncio
    async def test_clean_decision_resets_defer_streak(
        self, db_session, user, account, contact, email_row, patched_rag, patched_config,
    ):
        """A clean CONTINUE after a defer streak zeros the counter so
        the next transient blip doesn't instantly fall through."""
        email_row.rag_defer_count = 2
        db_session.commit()
        factory = _fake_httpx_client(responses=[
            _haiku_tool_response(decision="CONTINUE", rule_triggered="none", triggering_event=""),
        ])
        with patch("httpx.AsyncClient", factory):
            await _rag_presend_decision(db_session, email_row, user)
        assert email_row.rag_defer_count == 0


# ---------------------------------------------------------------------------
# Cold-path short-circuits — no AI call made at all.
# ---------------------------------------------------------------------------
class TestColdShortCircuits:
    @pytest.mark.asyncio
    async def test_no_snapshot_short_circuits_no_api_call(
        self, db_session, user, account, contact, email_row, monkeypatch, patched_config,
    ):
        """$0 path: snapshot helper returns None, Haiku is never called."""
        import rag_service
        monkeypatch.setattr(rag_service, "get_presend_snapshot", AsyncMock(return_value=None))
        monkeypatch.setattr(rag_service, "get_sonnet_model", MagicMock(return_value="x"))
        monkeypatch.setattr(rag_service, "get_haiku_model", MagicMock(return_value="x"))

        factory = _fake_httpx_client(exc=RuntimeError("should never be called"))
        with patch("httpx.AsyncClient", factory):
            result = await _rag_presend_decision(db_session, email_row, user)
        assert result == PRESEND_CONTINUE
        factory.assert_not_called()

    @pytest.mark.asyncio
    async def test_snapshot_with_no_signals_short_circuits(
        self, db_session, user, account, contact, email_row, monkeypatch, patched_config,
    ):
        """Snapshot exists but carries neither contact nor org signals —
        pass straight through without calling Haiku. Edge case mostly
        hit under test snapshots."""
        import rag_service
        empty = _fake_snapshot(has_contact_signal=False, has_org_signal=False, formatted="")
        monkeypatch.setattr(rag_service, "get_presend_snapshot", AsyncMock(return_value=empty))
        monkeypatch.setattr(rag_service, "get_sonnet_model", MagicMock(return_value="x"))
        monkeypatch.setattr(rag_service, "get_haiku_model", MagicMock(return_value="x"))

        factory = _fake_httpx_client(exc=RuntimeError("should never be called"))
        with patch("httpx.AsyncClient", factory):
            result = await _rag_presend_decision(db_session, email_row, user)
        assert result == PRESEND_CONTINUE
        factory.assert_not_called()

    @pytest.mark.asyncio
    async def test_user_without_org_id_short_circuits(
        self, db_session, email_row, patched_rag, patched_config,
    ):
        lone_user = models.User(
            email="lone@example.com",
            hashed_password="x" * 60,
            full_name="Lone",
            is_active=True,
            org_id=None,
        )
        db_session.add(lone_user)
        db_session.commit()

        factory = _fake_httpx_client(exc=RuntimeError("should never be called"))
        with patch("httpx.AsyncClient", factory):
            result = await _rag_presend_decision(db_session, email_row, lone_user)
        assert result == PRESEND_CONTINUE
        factory.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_contact_and_no_org_short_circuits(
        self, db_session, user, account, email_row, patched_rag, patched_config,
    ):
        email_row.contact_id = None
        db_session.commit()

        factory = _fake_httpx_client(exc=RuntimeError("should never be called"))
        with patch("httpx.AsyncClient", factory):
            result = await _rag_presend_decision(db_session, email_row, user)
        assert result == PRESEND_CONTINUE
        factory.assert_not_called()

    @pytest.mark.asyncio
    async def test_missing_anthropic_key_returns_continue(
        self, db_session, user, account, contact, email_row,
        patched_rag, patched_config, monkeypatch,
    ):
        """No ANTHROPIC_API_KEY → we cannot call Haiku. Documented
        fallback is CONTINUE — blocking every email on a misconfigured
        instance is worse than running without the gate."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        factory = _fake_httpx_client(exc=RuntimeError("should never be called"))
        with patch("httpx.AsyncClient", factory):
            result = await _rag_presend_decision(db_session, email_row, user)
        assert result == PRESEND_CONTINUE
        factory.assert_not_called()


# ---------------------------------------------------------------------------
# Snapshot-[dnc] extended short-circuit (#176 T3 extension of the T1 gate).
# ---------------------------------------------------------------------------
class TestSnapshotDncShortCircuit:
    @pytest.mark.asyncio
    async def test_dnc_tag_in_snapshot_cancels_without_ai_call(
        self, db_session, user, account, contact, email_row, monkeypatch, patched_config,
    ):
        """A [dnc] event in the fresh snapshot cancels the sequence
        before Haiku runs — covers webhook-delivered DNC that has not
        yet persisted to contact.dnc_status. Catches the gap between
        the DB-flag gate and the eventual-consistency of T2's
        emit_dnc_signal producer."""
        import rag_service

        snapshot = _fake_snapshot(
            has_contact_signal=True,
            formatted=(
                "- activity [2026-04-24]: [dnc] Contact marked Do Not Contact\n"
                "- activity [2026-04-23]: Some earlier event"
            ),
        )
        monkeypatch.setattr(rag_service, "get_presend_snapshot", AsyncMock(return_value=snapshot))
        monkeypatch.setattr(rag_service, "get_sonnet_model", MagicMock(return_value="x"))
        monkeypatch.setattr(rag_service, "get_haiku_model", MagicMock(return_value="x"))

        factory = _fake_httpx_client(exc=RuntimeError("Haiku must not be called"))
        with patch("httpx.AsyncClient", factory):
            result = await _rag_presend_decision(db_session, email_row, user)

        assert result == PRESEND_HOLD
        assert email_row.status == "cancelled"
        assert email_row.fresh_check_action == "cancel_sequence"
        assert email_row.fresh_check_rule_triggered == "dnc"
        assert "snapshot" in (email_row.fresh_check_reason or "").lower()
        factory.assert_not_called()

    @pytest.mark.asyncio
    async def test_snapshot_without_dnc_tag_proceeds_to_haiku(
        self, db_session, user, account, contact, email_row, patched_rag, patched_config,
    ):
        """Signals present but no [dnc] → flow through to Haiku normally.
        Prevents an over-eager substring match on "dn" etc."""
        factory = _fake_httpx_client(responses=[
            _haiku_tool_response(decision="CONTINUE", rule_triggered="none", triggering_event=""),
        ])
        with patch("httpx.AsyncClient", factory):
            result = await _rag_presend_decision(db_session, email_row, user)
        assert result == PRESEND_CONTINUE
        # Haiku was called.
        assert factory.return_value.post.call_count == 1


# ---------------------------------------------------------------------------
# DNC DB-flag short-circuit (#174 T1 — unchanged contract).
#
# Runs BEFORE any snapshot fetch, embedding read, or AI call. These tests
# pin that contract: flipping dnc_status on the contact or its org must
# cancel the row + downstream sequence and stop the function returning
# before httpx.AsyncClient is ever constructed.
# ---------------------------------------------------------------------------
class TestDncShortCircuit:
    @pytest.fixture
    def contact_org(self, db_session, user):
        o = models.ContactOrganization(user_id=user.id, name="Prospect Co")
        db_session.add(o)
        db_session.commit()
        return o

    @staticmethod
    def _make_queue_row(db_session, user, contact, **overrides):
        now = datetime.now(timezone.utc)
        defaults = dict(
            user_id=user.id,
            contact_id=contact.id,
            recipient_email=contact.email,
            subject="sibling",
            body="...",
            scheduled_at=now + timedelta(days=1),
            status="pending",
            created_at=now,
            rag_defer_count=0,
        )
        defaults.update(overrides)
        row = models.EmailQueue(**defaults)
        db_session.add(row)
        db_session.commit()
        return row

    @pytest.mark.asyncio
    async def test_contact_dnc_cancels_without_ai_call(
        self, db_session, user, account, contact, email_row, patched_rag, patched_config,
    ):
        contact.dnc_status = True
        db_session.commit()

        import rag_service
        snapshot_mock = rag_service.get_presend_snapshot

        factory = _fake_httpx_client(exc=RuntimeError("DNC gate must not call Haiku"))
        with patch("httpx.AsyncClient", factory):
            result = await _rag_presend_decision(db_session, email_row, user)

        assert result == PRESEND_HOLD
        assert email_row.status == "cancelled"
        assert email_row.fresh_check_action == "cancel_sequence"
        assert email_row.fresh_check_rule_triggered == "dnc"
        assert email_row.fresh_check_reason == "Contact is Do Not Contact (contact)"
        assert "DNC" in (email_row.error_message or "")
        assert email_row.rag_defer_count == 0
        factory.assert_not_called()
        snapshot_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_org_dnc_cancels_without_ai_call(
        self, db_session, user, account, contact, contact_org, email_row,
        patched_rag, patched_config,
    ):
        contact.contact_organization_id = contact_org.id
        contact_org.dnc_status = True
        db_session.commit()

        factory = _fake_httpx_client(exc=RuntimeError("DNC gate must not call Haiku"))
        with patch("httpx.AsyncClient", factory):
            result = await _rag_presend_decision(db_session, email_row, user)

        assert result == PRESEND_HOLD
        assert email_row.status == "cancelled"
        assert email_row.fresh_check_rule_triggered == "dnc"
        assert email_row.fresh_check_reason == "Contact is Do Not Contact (org)"
        factory.assert_not_called()

    @pytest.mark.asyncio
    async def test_both_contact_and_org_dnc_records_combined_scope(
        self, db_session, user, account, contact, contact_org, email_row,
        patched_rag, patched_config,
    ):
        contact.contact_organization_id = contact_org.id
        contact.dnc_status = True
        contact_org.dnc_status = True
        db_session.commit()

        with patch("httpx.AsyncClient", _fake_httpx_client(exc=RuntimeError("nope"))):
            result = await _rag_presend_decision(db_session, email_row, user)

        assert result == PRESEND_HOLD
        assert email_row.fresh_check_reason == "Contact is Do Not Contact (contact+org)"

    @pytest.mark.asyncio
    async def test_neither_dnc_falls_through_to_haiku(
        self, db_session, user, account, contact, email_row, patched_rag, patched_config,
    ):
        assert contact.dnc_status is False
        factory = _fake_httpx_client(responses=[
            _haiku_tool_response(decision="CONTINUE", rule_triggered="none", triggering_event=""),
        ])
        with patch("httpx.AsyncClient", factory):
            result = await _rag_presend_decision(db_session, email_row, user)

        assert result == PRESEND_CONTINUE
        assert email_row.status == "pending"
        # Post-#177: CONTINUE persists audit rather than leaving fields None.
        assert email_row.fresh_check_action == "continue"

    @pytest.mark.asyncio
    async def test_cascade_cancels_siblings_via_sequence_run_id(
        self, db_session, user, contact, email_row, patched_rag, patched_config,
    ):
        contact.dnc_status = True
        email_row.sequence_run_id = 12345
        db_session.commit()

        pending_sibling = self._make_queue_row(
            db_session, user, contact,
            sequence_run_id=12345, subject="sibling-pending",
        )
        sent_sibling = self._make_queue_row(
            db_session, user, contact,
            sequence_run_id=12345, subject="sibling-sent", status="sent",
        )
        unrelated = self._make_queue_row(
            db_session, user, contact,
            sequence_run_id=99999, subject="different-sequence",
        )

        with patch("httpx.AsyncClient", _fake_httpx_client(exc=RuntimeError("nope"))):
            result = await _rag_presend_decision(db_session, email_row, user)

        assert result == PRESEND_HOLD
        db_session.refresh(pending_sibling)
        db_session.refresh(sent_sibling)
        db_session.refresh(unrelated)

        assert pending_sibling.status == "cancelled"
        assert pending_sibling.fresh_check_action == "cancel_sequence"
        assert pending_sibling.fresh_check_rule_triggered == "dnc"
        assert sent_sibling.status == "sent"
        assert sent_sibling.fresh_check_action is None
        assert unrelated.status == "pending"
        assert unrelated.fresh_check_action is None

    @pytest.mark.asyncio
    async def test_cascade_falls_back_to_execution_id_when_no_sequence_run(
        self, db_session, user, contact, email_row, patched_rag, patched_config,
    ):
        contact.dnc_status = True
        email_row.sequence_run_id = None
        email_row.execution_id = 77
        email_row.sequence_position = 2
        db_session.commit()

        downstream = self._make_queue_row(
            db_session, user, contact,
            sequence_run_id=None, execution_id=77, sequence_position=3,
            subject="downstream",
        )
        earlier = self._make_queue_row(
            db_session, user, contact,
            sequence_run_id=None, execution_id=77, sequence_position=1,
            subject="earlier",
        )

        with patch("httpx.AsyncClient", _fake_httpx_client(exc=RuntimeError("nope"))):
            await _rag_presend_decision(db_session, email_row, user)

        db_session.refresh(downstream)
        db_session.refresh(earlier)
        assert downstream.status == "cancelled"
        assert downstream.fresh_check_rule_triggered == "dnc"
        assert earlier.status == "pending"
        assert earlier.fresh_check_action is None

    @pytest.mark.asyncio
    async def test_dnc_short_circuit_runs_before_rag_service_import(
        self, db_session, user, account, contact, email_row, patched_config, monkeypatch,
    ):
        """Even if rag_service is unimportable (infra regression), a
        DNC contact must still be gated."""
        contact.dnc_status = True
        db_session.commit()

        import rag_service
        monkeypatch.setattr(
            rag_service, "get_presend_snapshot",
            AsyncMock(side_effect=RuntimeError("embedding backend down")),
        )

        with patch("httpx.AsyncClient", _fake_httpx_client(exc=RuntimeError("nope"))):
            result = await _rag_presend_decision(db_session, email_row, user)

        assert result == PRESEND_HOLD
        assert email_row.fresh_check_rule_triggered == "dnc"


# ---------------------------------------------------------------------------
# dispatch_fresh_check_action (#177 T4) — cascade executor for the four
# Sonnet-picked actions. Tests target the dispatcher directly rather than
# going through the full _rag_presend_decision flow so cascade mechanics
# are exercised in isolation.
# ---------------------------------------------------------------------------
from email_service import dispatch_fresh_check_action  # noqa: E402


class TestDispatchFreshCheckAction:
    @staticmethod
    def _make_sibling(db_session, email_row, *, sequence_run_id, status="pending", **extra):
        """Make a sibling EmailQueue row in the same sequence_run."""
        now = datetime.now(timezone.utc)
        defaults = dict(
            user_id=email_row.user_id,
            contact_id=email_row.contact_id,
            recipient_email=email_row.recipient_email,
            subject="downstream",
            body="...",
            scheduled_at=now + timedelta(days=1),
            status=status,
            created_at=now,
            rag_defer_count=0,
            sequence_run_id=sequence_run_id,
        )
        defaults.update(extra)
        row = models.EmailQueue(**defaults)
        db_session.add(row)
        db_session.commit()
        return row

    # ------------------------------------------------------------------
    # No-op paths
    # ------------------------------------------------------------------
    def test_unset_action_is_noop(self, db_session, email_row):
        """Defensive: safe to call on an email with no decision recorded."""
        email_row.fresh_check_action = None
        db_session.commit()
        # Simply must not raise.
        dispatch_fresh_check_action(db_session, email_row)
        db_session.commit()

    def test_cancel_email_does_not_touch_siblings(
        self, db_session, user, contact, email_row,
    ):
        """cancel_email is this-row-only — siblings must stay pending."""
        email_row.sequence_run_id = 111
        email_row.fresh_check_action = "cancel_email"
        email_row.fresh_check_rule_triggered = "crm_change"
        sibling = self._make_sibling(db_session, email_row, sequence_run_id=111)

        dispatch_fresh_check_action(db_session, email_row)
        db_session.commit()
        db_session.refresh(sibling)
        assert sibling.status == "pending"
        assert sibling.fresh_check_action is None

    def test_skip_email_does_not_touch_siblings(
        self, db_session, user, contact, email_row,
    ):
        """skip_email is a per-row action until T1 Q3 resolves the enum.
        fresh_check_action='skip_email' disambiguates in the UI; the
        dispatcher does NOT cascade to downstream rows."""
        email_row.sequence_run_id = 222
        email_row.fresh_check_action = "skip_email"
        email_row.fresh_check_rule_triggered = "reply_received"
        sibling = self._make_sibling(db_session, email_row, sequence_run_id=222)

        dispatch_fresh_check_action(db_session, email_row)
        db_session.commit()
        db_session.refresh(sibling)
        assert sibling.status == "pending"
        assert sibling.fresh_check_action is None

    # ------------------------------------------------------------------
    # cancel_sequence cascade
    # ------------------------------------------------------------------
    def test_cancel_sequence_cascades_pending_siblings(
        self, db_session, user, contact, email_row,
    ):
        """All pending siblings get cancelled with matching audit fields."""
        email_row.sequence_run_id = 333
        email_row.fresh_check_action = "cancel_sequence"
        email_row.fresh_check_rule_triggered = "reply_received"
        email_row.fresh_check_reason = "Prospect replied"
        sibling_a = self._make_sibling(db_session, email_row, sequence_run_id=333)
        sibling_b = self._make_sibling(db_session, email_row, sequence_run_id=333)

        dispatch_fresh_check_action(db_session, email_row)
        db_session.commit()
        db_session.refresh(sibling_a)
        db_session.refresh(sibling_b)
        assert sibling_a.status == "cancelled"
        assert sibling_a.fresh_check_action == "cancel_sequence"
        assert sibling_a.fresh_check_rule_triggered == "reply_received"
        assert "reply_received" in (sibling_a.error_message or "")
        assert sibling_b.status == "cancelled"

    def test_cancel_sequence_leaves_sent_rows_untouched(
        self, db_session, user, contact, email_row,
    ):
        """Already-sent rows are archival — do not rewrite their status
        or audit fields, even during a cascade."""
        email_row.sequence_run_id = 444
        email_row.fresh_check_action = "cancel_sequence"
        email_row.fresh_check_rule_triggered = "crm_change"
        sent = self._make_sibling(db_session, email_row, sequence_run_id=444, status="sent")

        dispatch_fresh_check_action(db_session, email_row)
        db_session.commit()
        db_session.refresh(sent)
        assert sent.status == "sent"
        assert sent.fresh_check_action is None

    def test_cancel_sequence_skips_manually_edited_siblings(
        self, db_session, user, contact, email_row,
    ):
        """Admin overrides win over the AI's cancel decision — a row
        with edit_source='manual' stays pending so the admin's deliberate
        edit isn't stomped. See #177 open question on manually-edited
        rows; this PR resolves it as "skip on cascade, respect manual
        intent"."""
        email_row.sequence_run_id = 555
        email_row.fresh_check_action = "cancel_sequence"
        email_row.fresh_check_rule_triggered = "reply_received"
        manual = self._make_sibling(
            db_session, email_row, sequence_run_id=555, edit_source="manual",
        )
        ai_edited = self._make_sibling(
            db_session, email_row, sequence_run_id=555, edit_source="ai",
        )

        dispatch_fresh_check_action(db_session, email_row)
        db_session.commit()
        db_session.refresh(manual)
        db_session.refresh(ai_edited)
        assert manual.status == "pending"
        assert manual.fresh_check_action is None
        assert ai_edited.status == "cancelled"
        assert ai_edited.fresh_check_action == "cancel_sequence"

    def test_cancel_sequence_does_not_touch_different_sequence(
        self, db_session, user, contact, email_row,
    ):
        """Siblings in a different sequence_run must be untouched —
        cascade scope is bounded by sequence_run_id."""
        email_row.sequence_run_id = 666
        email_row.fresh_check_action = "cancel_sequence"
        email_row.fresh_check_rule_triggered = "reply_received"
        other_seq = self._make_sibling(
            db_session, email_row, sequence_run_id=999, subject="different-seq",
        )

        dispatch_fresh_check_action(db_session, email_row)
        db_session.commit()
        db_session.refresh(other_seq)
        assert other_seq.status == "pending"
        assert other_seq.fresh_check_action is None

    def test_cancel_sequence_falls_back_to_execution_id(
        self, db_session, user, contact, email_row,
    ):
        """Legacy rows with sequence_run_id=NULL must still cascade via
        execution_id + sequence_position > current — matches the DNC
        fallback semantic."""
        email_row.sequence_run_id = None
        email_row.execution_id = 42
        email_row.sequence_position = 1
        email_row.fresh_check_action = "cancel_sequence"
        email_row.fresh_check_rule_triggered = "reply_received"
        downstream = self._make_sibling(
            db_session, email_row, sequence_run_id=None,
            execution_id=42, sequence_position=2,
        )
        earlier = self._make_sibling(
            db_session, email_row, sequence_run_id=None,
            execution_id=42, sequence_position=0,
        )

        dispatch_fresh_check_action(db_session, email_row)
        db_session.commit()
        db_session.refresh(downstream)
        db_session.refresh(earlier)
        assert downstream.status == "cancelled"
        # Rows earlier in the sequence are treated as handled already.
        assert earlier.status == "pending"

    # ------------------------------------------------------------------
    # reschedule cascade
    # ------------------------------------------------------------------
    def test_reschedule_shifts_this_row_and_siblings_by_offset(
        self, db_session, user, contact, email_row,
    ):
        """offset_days = resume_date - scheduled_at.date(); apply to
        this row and every downstream pending sibling. timedelta math
        preserves UTC hour/minute exactly."""
        from datetime import date
        email_row.scheduled_at = datetime(2026, 4, 24, 9, 30, tzinfo=timezone.utc)
        email_row.sequence_run_id = 777
        email_row.fresh_check_action = "reschedule"
        email_row.fresh_check_rule_triggered = "crm_change"
        email_row.fresh_check_resume_date = date(2026, 6, 15)  # +52 days

        sibling = self._make_sibling(
            db_session, email_row, sequence_run_id=777,
            scheduled_at=datetime(2026, 4, 26, 14, 0, tzinfo=timezone.utc),
        )
        db_session.commit()

        dispatch_fresh_check_action(db_session, email_row)
        db_session.commit()
        db_session.refresh(sibling)

        # This email moves from 2026-04-24 → 2026-06-15 (offset = 52 days).
        assert email_row.scheduled_at.date().isoformat() == "2026-06-15"
        assert email_row.scheduled_at.hour == 9
        assert email_row.scheduled_at.minute == 30
        # Sibling was on 2026-04-26 14:00 → 2026-06-17 14:00 (same +52).
        assert sibling.scheduled_at.date().isoformat() == "2026-06-17"
        assert sibling.scheduled_at.hour == 14
        assert sibling.scheduled_at.minute == 0
        # Inter-row cadence (2 days) preserved.
        delta = sibling.scheduled_at - email_row.scheduled_at
        assert delta == timedelta(days=2, hours=4, minutes=30)
        # Sibling audit updated too.
        assert sibling.fresh_check_action == "reschedule"
        assert sibling.fresh_check_resume_date == email_row.fresh_check_resume_date

    def test_reschedule_preserves_utc_across_dst_boundary(
        self, db_session, user, contact, email_row,
    ):
        """scheduled_at is UTC-native; timedelta(days=N) preserves the
        exact UTC time regardless of any DST transition the offset
        spans. Local wall-clock drift across DST is accepted and
        documented (spec §07 time-of-day rule is UTC-keyed here)."""
        from datetime import date
        # March 8 2026 → March 20 2026 spans US DST spring-forward.
        email_row.scheduled_at = datetime(2026, 3, 1, 13, 0, tzinfo=timezone.utc)
        email_row.sequence_run_id = 888
        email_row.fresh_check_action = "reschedule"
        email_row.fresh_check_rule_triggered = "activity_logged"
        email_row.fresh_check_resume_date = date(2026, 3, 20)

        dispatch_fresh_check_action(db_session, email_row)
        db_session.commit()
        assert email_row.scheduled_at.date().isoformat() == "2026-03-20"
        assert email_row.scheduled_at.hour == 13
        assert email_row.scheduled_at.minute == 0

    def test_reschedule_handles_negative_offset(
        self, db_session, user, contact, email_row,
    ):
        """Sonnet can in principle resume earlier than the current
        scheduled_at (e.g. "prospect wants the email NOW"). A negative
        offset must shift backwards, not error out."""
        from datetime import date
        email_row.scheduled_at = datetime(2026, 6, 15, 8, 0, tzinfo=timezone.utc)
        email_row.sequence_run_id = 990
        email_row.fresh_check_action = "reschedule"
        email_row.fresh_check_rule_triggered = "reply_received"
        email_row.fresh_check_resume_date = date(2026, 6, 1)  # -14 days

        sibling = self._make_sibling(
            db_session, email_row, sequence_run_id=990,
            scheduled_at=datetime(2026, 6, 17, 8, 0, tzinfo=timezone.utc),
        )
        db_session.commit()

        dispatch_fresh_check_action(db_session, email_row)
        db_session.commit()
        db_session.refresh(sibling)

        assert email_row.scheduled_at.date().isoformat() == "2026-06-01"
        assert sibling.scheduled_at.date().isoformat() == "2026-06-03"  # +2 preserved

    def test_reschedule_skips_manually_edited_siblings(
        self, db_session, user, contact, email_row,
    ):
        """Same manual-override semantic as cancel_sequence — an admin's
        bespoke reschedule is not overwritten by the AI's."""
        from datetime import date
        email_row.scheduled_at = datetime(2026, 5, 1, 10, 0, tzinfo=timezone.utc)
        email_row.sequence_run_id = 1010
        email_row.fresh_check_action = "reschedule"
        email_row.fresh_check_rule_triggered = "crm_change"
        email_row.fresh_check_resume_date = date(2026, 5, 20)

        orig = datetime(2026, 5, 3, 10, 0, tzinfo=timezone.utc)
        manual_sibling = self._make_sibling(
            db_session, email_row, sequence_run_id=1010,
            scheduled_at=orig, edit_source="manual",
        )
        db_session.commit()

        dispatch_fresh_check_action(db_session, email_row)
        db_session.commit()
        db_session.refresh(manual_sibling)

        # Manual sibling keeps its original scheduled_at. SQLite strips
        # tzinfo on round-trip, so compare naive-vs-naive.
        assert _naive(manual_sibling.scheduled_at) == _naive(orig)
        assert manual_sibling.fresh_check_action is None

    def test_reschedule_without_resume_date_is_noop(
        self, db_session, email_row,
    ):
        """Defensive: if fresh_check_resume_date is somehow unset (e.g.
        a partial-write bug), we must not shift scheduled_at to an
        unspecified anchor — skip and log."""
        email_row.scheduled_at = datetime(2026, 4, 24, 9, 0, tzinfo=timezone.utc)
        email_row.fresh_check_action = "reschedule"
        email_row.fresh_check_resume_date = None
        original = email_row.scheduled_at

        dispatch_fresh_check_action(db_session, email_row)
        db_session.commit()
        assert _naive(email_row.scheduled_at) == _naive(original)

    def test_unknown_action_logs_and_returns(self, db_session, email_row):
        """A bad fresh_check_action value is a bug somewhere upstream;
        the dispatcher refuses to guess and simply returns without
        touching state."""
        email_row.scheduled_at = datetime(2026, 4, 24, 9, 0, tzinfo=timezone.utc)
        email_row.status = "pending"
        email_row.fresh_check_action = "teleport_to_mars"
        original_status = email_row.status
        original_sched = email_row.scheduled_at

        dispatch_fresh_check_action(db_session, email_row)
        db_session.commit()
        assert email_row.status == original_status
        assert _naive(email_row.scheduled_at) == _naive(original_sched)
