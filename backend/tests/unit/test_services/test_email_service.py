"""Unit tests for email_service same-thread behavior."""

from datetime import datetime, timezone

import pytest

import contacts_service
import email_service
import models
from tests.fixtures.factories import UserFactory


class TestSameThreadReplyContext:
    """Test same-thread reply context resolution for queued emails."""

    def test_resolve_thread_parent_context_uses_configured_parent_component(self, db_session):
        user = UserFactory.create()
        contact = models.Contact(
            user_id=user.id,
            email="client@example.com",
            primary_email="client@example.com",
        )
        db_session.add_all([user, contact])
        db_session.flush()

        first_email = models.EmailQueue(
            user_id=user.id,
            contact_id=contact.id,
            component_id=501,
            execution_id=77,
            sequence_position=1,
            recipient_email="client@example.com",
            recipient_name="Client",
            subject="Intro",
            body="<p>First</p>",
            scheduled_at=datetime.now(timezone.utc),
            sent_at=datetime.now(timezone.utc),
            status="sent",
            thread_id="thread-123",
            message_id_header="<msg-1@example.com>",
        )
        second_email = models.EmailQueue(
            user_id=user.id,
            contact_id=contact.id,
            execution_id=77,
            sequence_position=2,
            recipient_email="client@example.com",
            recipient_name="Client",
            subject="Follow up",
            body="<p>Second</p>",
            scheduled_at=datetime.now(timezone.utc),
            status="pending",
            thread_parent_component_id=501,
        )
        db_session.add_all([first_email, second_email])
        db_session.commit()

        context = email_service._resolve_thread_parent_context(db_session, second_email)

        assert context["mode"] == "reply"
        assert context["parent_email"].id == first_email.id
        assert context["thread_id"] == "thread-123"
        assert context["in_reply_to"] == "<msg-1@example.com>"
        assert context["references"] == "<msg-1@example.com>"
        assert context["subject"] == "Intro"

    def test_resolve_thread_parent_context_falls_back_when_parent_not_sent(self, db_session):
        user = UserFactory.create()
        db_session.add(user)
        db_session.flush()

        parent_email = models.EmailQueue(
            user_id=user.id,
            component_id=321,
            execution_id=88,
            recipient_email="client@example.com",
            recipient_name="Client",
            subject="Intro",
            body="<p>First</p>",
            scheduled_at=datetime.now(timezone.utc),
            status="cancelled",
        )
        child_email = models.EmailQueue(
            user_id=user.id,
            execution_id=88,
            recipient_email="client@example.com",
            recipient_name="Client",
            subject="Follow up",
            body="<p>Second</p>",
            scheduled_at=datetime.now(timezone.utc),
            status="pending",
            thread_parent_component_id=321,
        )
        db_session.add_all([parent_email, child_email])
        db_session.commit()

        context = email_service._resolve_thread_parent_context(db_session, child_email)

        assert context["mode"] == "fallback"
        assert context["reason"] == "parent_not_sent"
        assert context["parent_email"].id == parent_email.id

    def test_resolve_thread_parent_context_skips_new_thread_emails(self, db_session):
        user = UserFactory.create()
        db_session.add(user)
        db_session.flush()

        first_email = models.EmailQueue(
            user_id=user.id,
            execution_id=88,
            sequence_position=1,
            recipient_email="client@example.com",
            recipient_name="Client",
            subject="Intro",
            body="<p>First</p>",
            scheduled_at=datetime.now(timezone.utc),
            status="pending",
        )
        db_session.add(first_email)
        db_session.commit()

        assert email_service._resolve_thread_parent_context(db_session, first_email) == {"mode": "new_thread"}


@pytest.mark.asyncio
async def test_process_email_queue_persists_gmail_thread_metadata(monkeypatch, db_session):
    user = UserFactory.create()
    db_session.add(user)
    db_session.flush()

    contact = models.Contact(
        user_id=user.id,
        email="client@example.com",
        primary_email="client@example.com",
    )
    db_session.add(contact)
    db_session.flush()

    prior_email = models.EmailQueue(
        user_id=user.id,
        contact_id=contact.id,
        component_id=111,
        recipient_email="client@example.com",
        recipient_name="Client",
        subject="Intro",
        body="<p>First</p>",
        scheduled_at=datetime.now(timezone.utc),
        sent_at=datetime.now(timezone.utc),
        status="sent",
        execution_id=123,
        sequence_position=1,
        thread_id="thread-abc",
        message_id_header="<prior@example.com>",
    )
    email_item = models.EmailQueue(
        user_id=user.id,
        contact_id=contact.id,
        component_id=222,
        recipient_email="client@example.com",
        recipient_name="Client",
        subject="Follow up",
        body="<p>Hello</p>",
        scheduled_at=datetime.now(timezone.utc),
        status="pending",
        execution_id=123,
        sequence_position=2,
        thread_parent_component_id=111,
    )
    db_session.add_all([prior_email, email_item])
    db_session.commit()

    captured = {}

    async def fake_send_email(**kwargs):
        captured.update(kwargs)
        return {
            "success": True,
            "thread_id": "thread-abc",
            "message_id_header": "<current@example.com>",
        }

    def fake_log_activity(**kwargs):
        captured["logged_thread_id"] = kwargs.get("thread_id")

    monkeypatch.setattr(email_service, "send_email", fake_send_email)
    monkeypatch.setattr(contacts_service, "log_activity", fake_log_activity)

    result = await email_service.process_email_queue(db_session)

    db_session.refresh(email_item)
    assert result["success"] is True
    assert captured["thread_id"] == "thread-abc"
    assert captured["in_reply_to"] == "<prior@example.com>"
    assert captured["references"] == "<prior@example.com>"
    assert captured["logged_thread_id"] == "thread-abc"
    assert email_item.status == "sent"
    assert email_item.thread_id == "thread-abc"
    assert email_item.message_id_header == "<current@example.com>"
    assert email_item.thread_parent_queue_id == prior_email.id


@pytest.mark.asyncio
async def test_process_email_queue_generates_subject_on_thread_fallback(monkeypatch, db_session):
    user = UserFactory.create()
    db_session.add(user)
    db_session.flush()

    parent_email = models.EmailQueue(
        user_id=user.id,
        component_id=111,
        recipient_email="client@example.com",
        recipient_name="Client",
        subject="",
        body="<p>First</p>",
        scheduled_at=datetime.now(timezone.utc),
        status="cancelled",
        execution_id=123,
        sequence_position=1,
    )
    email_item = models.EmailQueue(
        user_id=user.id,
        component_id=222,
        recipient_email="client@example.com",
        recipient_name="Client",
        subject="",
        body="<p>Hello</p>",
        scheduled_at=datetime.now(timezone.utc),
        status="pending",
        execution_id=123,
        sequence_position=2,
        thread_parent_component_id=111,
    )
    db_session.add_all([parent_email, email_item])
    db_session.commit()

    captured = {}

    async def fake_send_email(**kwargs):
        captured.update(kwargs)
        return {"success": True, "message_id_header": "<current@example.com>"}

    async def fake_generate_fallback_subject(email):
        return "Generated fallback subject"

    monkeypatch.setattr(email_service, "send_email", fake_send_email)
    monkeypatch.setattr(email_service, "_generate_fallback_subject", fake_generate_fallback_subject)

    result = await email_service.process_email_queue(db_session)

    db_session.refresh(email_item)
    assert result["success"] is True
    assert captured["subject"] == "Generated fallback subject"
    assert email_item.subject == "Generated fallback subject"
    assert email_item.thread_fallback_reason == "parent_not_sent"
    assert email_item.thread_parent_queue_id is None


@pytest.mark.asyncio
async def test_process_email_queue_falls_back_when_sender_account_changes(monkeypatch, db_session):
    user = UserFactory.create()
    db_session.add(user)
    db_session.flush()

    prior_email = models.EmailQueue(
        user_id=user.id,
        component_id=111,
        recipient_email="client@example.com",
        recipient_name="Client",
        subject="Intro",
        body="<p>First</p>",
        scheduled_at=datetime.now(timezone.utc),
        sent_at=datetime.now(timezone.utc),
        status="sent",
        execution_id=123,
        sequence_position=1,
        thread_id="thread-abc",
        message_id_header="<prior@example.com>",
        sender_provider="gmail",
        sender_account_email="old@example.com",
    )
    email_item = models.EmailQueue(
        user_id=user.id,
        component_id=222,
        recipient_email="client@example.com",
        recipient_name="Client",
        subject="",
        body="<p>Hello</p>",
        scheduled_at=datetime.now(timezone.utc),
        status="pending",
        execution_id=123,
        sequence_position=2,
        thread_parent_component_id=111,
    )
    db_session.add_all([prior_email, email_item])
    db_session.commit()

    captured = {}

    async def fake_send_email(**kwargs):
        captured.update(kwargs)
        return {
            "success": True,
            "message_id_header": "<current@example.com>",
            "sender_provider": "gmail",
            "sender_account_email": "new@example.com",
        }

    async def fake_generate_fallback_subject(email):
        return "Generated fallback subject"

    async def fake_resolve_sender(user, **kwargs):
        return {"provider": "gmail", "email": "new@example.com"}

    monkeypatch.setattr(email_service, "send_email", fake_send_email)
    monkeypatch.setattr(email_service, "_generate_fallback_subject", fake_generate_fallback_subject)
    monkeypatch.setattr(email_service, "resolve_current_sender_identity", fake_resolve_sender)

    result = await email_service.process_email_queue(db_session)

    db_session.refresh(email_item)
    assert result["success"] is True
    assert captured["subject"] == "Generated fallback subject"
    assert captured["thread_id"] is None
    assert captured["in_reply_to"] is None
    assert captured["references"] is None
    assert email_item.thread_fallback_reason == "different_account"
    assert email_item.sender_account_email == "new@example.com"
