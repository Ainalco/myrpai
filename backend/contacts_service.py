"""
Contact system business logic.
Core functions: get_or_create_contact, log_activity, update_contact_stats, merge_contacts.
"""
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import func, text
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
import threading
import logging

import models
from database import SessionLocal

logger = logging.getLogger(__name__)

# Holds references to in-flight background embedding tasks so asyncio doesn't
# garbage-collect them before they finish. See asyncio.create_task() docs.
_pending_embed_tasks: set = set()

# Bounded thread pool for the sync-caller branch of _schedule_activity_embedding.
# A Pipedrive bulk-stage-change webhook can deliver 200+ activities in one burst;
# without a cap that was 200 fresh daemon threads, 200 DB connections, and 200
# concurrent OpenAI requests. A pool of 4 workers matches the same policy that
# bounds rag_service._dispatch_latency_record — I/O-bound work, no benefit past
# a few concurrent writes, and pool_size headroom preserved for real traffic.
_ACTIVITY_EMBED_MAX_WORKERS = 4
# Cap queued work so a sustained burst can't inflate memory forever. 200 is
# well beyond the steady-state load and aligns with the webhook batch size we
# actually observe in prod. Once full, new submissions are dropped with a log.
_ACTIVITY_EMBED_MAX_QUEUED = 200
_activity_embed_pool: Optional[ThreadPoolExecutor] = None
_activity_embed_queue_depth = 0
_activity_embed_pool_lock = threading.Lock()


def _get_activity_embed_pool() -> ThreadPoolExecutor:
    """Lazy-initialise the shared executor so import-time cost stays zero."""
    global _activity_embed_pool
    if _activity_embed_pool is None:
        with _activity_embed_pool_lock:
            if _activity_embed_pool is None:
                _activity_embed_pool = ThreadPoolExecutor(
                    max_workers=_ACTIVITY_EMBED_MAX_WORKERS,
                    thread_name_prefix="activity-embed",
                )
    return _activity_embed_pool

# Freemail domains — skip org creation for these
FREEMAIL_DOMAINS = frozenset({
    "gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "aol.com",
    "icloud.com", "mail.com", "protonmail.com", "zoho.com", "yandex.com",
    "live.com", "msn.com", "me.com", "fastmail.com", "tutanota.com", "hey.com",
})


def generate_initials(name: Optional[str], email: str) -> str:
    """Generate avatar initials from name or email."""
    if name:
        parts = name.split()
        if len(parts) >= 2:
            return (parts[0][0] + parts[-1][0]).upper()
        elif len(parts) == 1 and len(parts[0]) >= 2:
            return parts[0][:2].upper()
    return email[:2].upper()


def _extract_domain(email: str) -> str:
    """Extract domain from email address."""
    return email.rsplit("@", 1)[-1].lower()


def _get_or_create_org(
    db: Session,
    user_id: int,
    domain: str,
    org_name: Optional[str] = None,
) -> Optional[models.ContactOrganization]:
    """Get or create a contact organization by domain. Returns None for freemail domains."""
    if domain in FREEMAIL_DOMAINS:
        return None

    org = db.query(models.ContactOrganization).filter(
        models.ContactOrganization.user_id == user_id,
        models.ContactOrganization.domain == domain,
        models.ContactOrganization.deleted_at.is_(None),
    ).first()

    if org:
        return org

    # Use advisory lock to prevent race condition
    lock_key = hash(f"org:{user_id}:{domain}") & 0x7FFFFFFF
    try:
        db.execute(text(f"SELECT pg_advisory_xact_lock({lock_key})"))
    except Exception:
        # Graceful degradation if not PostgreSQL (e.g., tests with SQLite)
        pass

    # Double-check after acquiring lock
    org = db.query(models.ContactOrganization).filter(
        models.ContactOrganization.user_id == user_id,
        models.ContactOrganization.domain == domain,
        models.ContactOrganization.deleted_at.is_(None),
    ).first()
    if org:
        return org

    display_name = org_name or domain.split(".")[0].title()
    org = models.ContactOrganization(
        user_id=user_id,
        name=display_name,
        domain=domain,
    )
    db.add(org)
    db.flush()
    logger.info("Created contact org", extra={"user_id": user_id, "org_id": org.id, "domain": domain})
    return org


def get_or_create_contact(
    db: Session,
    user_id: int,
    email: str,
    name: Optional[str] = None,
    organization_name: Optional[str] = None,
) -> models.Contact:
    """
    Get an existing contact or create a new one.
    Lookup is via contact_emails table (multi-email support).
    Uses PostgreSQL advisory locks to prevent race-condition duplicates.
    """
    email = email.strip().lower()

    # 1. Check contact_emails for existing match
    contact_email = db.query(models.ContactEmail).join(models.Contact).filter(
        models.Contact.user_id == user_id,
        models.ContactEmail.email == email,
        models.Contact.deleted_at.is_(None),
    ).first()

    if contact_email:
        return contact_email.contact

    # 2. Acquire advisory lock to prevent duplicates
    lock_key = hash(f"contact:{user_id}:{email}") & 0x7FFFFFFF
    try:
        db.execute(text(f"SELECT pg_advisory_xact_lock({lock_key})"))
    except Exception:
        pass  # Graceful degradation for non-PG databases

    # 3. Double-check after lock
    contact_email = db.query(models.ContactEmail).join(models.Contact).filter(
        models.Contact.user_id == user_id,
        models.ContactEmail.email == email,
        models.Contact.deleted_at.is_(None),
    ).first()
    if contact_email:
        return contact_email.contact

    # 4. Extract domain and get/create org
    domain = _extract_domain(email)
    org = _get_or_create_org(db, user_id, domain, organization_name)

    # 5. Create Contact
    contact = models.Contact(
        user_id=user_id,
        email=email,
        primary_email=email,
        name=name,
        company=organization_name or (org.name if org else None),
        avatar_initials=generate_initials(name, email),
        contact_organization_id=org.id if org else None,
        status="active",
        contact_count=0,
    )
    if org and org.dnc:
        contact.status = "do_not_contact"
    
    db.add(contact)
    db.flush()

    # 6. Create ContactEmail (primary)
    db.add(models.ContactEmail(
        contact_id=contact.id,
        email=email,
        is_primary=True,
    ))

    # 7. Create ContactStats (all zeros)
    db.add(models.ContactStats(contact_id=contact.id))

    db.flush()
    logger.info("Created contact", extra={"user_id": user_id, "contact_id": contact.id, "email": email})
    return contact


def log_activity(
    db: Session,
    user_id: int,
    contact_id: int,
    activity_type: str,
    direction: Optional[str] = None,
    source_type: Optional[str] = None,
    source_id: Optional[str] = None,
    email_queue_id: Optional[int] = None,
    deal_id: Optional[int] = None,
    thread_id: Optional[str] = None,
    subject: Optional[str] = None,
    summary: Optional[str] = None,
    title: Optional[str] = None,
    occurred_at: Optional[datetime] = None,
) -> models.ContactActivity:
    """
    Log an activity on a contact's timeline.
    Idempotent when source_id is provided (skips duplicate).
    Updates contact denormalized fields and stats.
    If occurred_at is provided, uses that timestamp instead of now (for CRM sync).
    """
    # Idempotency check
    if source_id and source_type:
        existing = db.query(models.ContactActivity).filter(
            models.ContactActivity.user_id == user_id,
            models.ContactActivity.source_type == source_type,
            models.ContactActivity.source_id == source_id,
        ).first()
        if existing:
            return existing

    now = datetime.now(timezone.utc)
    event_time = occurred_at or now
    activity = models.ContactActivity(
        contact_id=contact_id,
        user_id=user_id,
        email_queue_id=email_queue_id,
        activity_type=activity_type,
        title=title or f"{activity_type.replace('_', ' ').title()}",
        occurred_at=event_time,
        activity_at=event_time,
        is_new=True,
        direction=direction,
        source_type=source_type,
        source_id=source_id,
        deal_id=deal_id,
        thread_id=thread_id,
        subject=subject,
        summary=summary,
    )
    db.add(activity)

    # Update denormalized fields on contact
    contact = db.query(models.Contact).filter(models.Contact.id == contact_id).first()
    if contact:
        contact.last_activity_at = now
        contact.last_activity_type = activity_type
        contact.last_activity_direction = direction
        if activity_type == "email_sent":
            contact.last_contacted_at = now
            contact.contact_count = (contact.contact_count or 0) + 1

    # Increment stats
    stats = db.query(models.ContactStats).filter(
        models.ContactStats.contact_id == contact_id
    ).first()
    if stats:
        if activity_type == "email_sent":
            stats.emails_sent = (stats.emails_sent or 0) + 1
        elif direction == "inbound":
            stats.emails_received = (stats.emails_received or 0) + 1
        # Recompute reply rate
        if stats.emails_sent and stats.emails_sent > 0:
            stats.reply_rate = (stats.emails_received or 0) / stats.emails_sent * 100
        stats.last_computed_at = now

    db.flush()
    logger.info("Logged activity", extra={
        "user_id": user_id, "contact_id": contact_id,
        "activity_type": activity_type, "direction": direction,
    })

    # RAG Phase 5: embed a human-readable summary of the activity so the pre-send
    # safety net can detect fresh signals (replies, deal changes, etc.) before a
    # queued email goes out. Fire-and-forget — embedding failures never block logging.
    try:
        _schedule_activity_embedding(
            db=db,
            user_id=user_id,
            contact_id=contact_id,
            activity_id=activity.id,
            activity_type=activity_type,
            direction=direction,
            subject=subject,
            summary=summary,
            source_type=source_type,
            source_id=source_id,
            occurred_at=event_time,
        )
    except Exception as _e:
        logger.debug(f"Activity embedding scheduling failed (non-blocking): {_e}")

    return activity


def _schedule_activity_embedding(
    db: Session,
    user_id: int,
    contact_id: int,
    activity_id: int,
    activity_type: str,
    direction: Optional[str],
    subject: Optional[str],
    summary: Optional[str],
    source_type: Optional[str],
    source_id: Optional[str],
    occurred_at: datetime,
) -> None:
    """Embed the activity into content_embeddings for RAG pre-send checks.

    The caller's SQLAlchemy Session is NEVER handed to the embedding coroutine
    — store_embeddings() calls db.commit(), which would commit the caller's
    in-progress transaction mid-request. The task opens a fresh SessionLocal()
    and closes it in finally.

    When a running event loop exists (async caller), the work is scheduled with
    asyncio.create_task(). When there is no running loop (sync caller, e.g. a
    threadpool worker), the work runs in a dedicated daemon thread so we never
    block the caller and never invoke asyncio.run() in a thread that could be
    hosting a loop elsewhere.

    Never raises — failures are logged and swallowed.
    """
    import asyncio
    from rag_service import activity_source_type, build_activity_summary, store_activity_summary

    # Resolve account_id/org_id with the caller's session (reads only). These
    # values are captured as primitives so the background task does not depend
    # on the caller's session at all.
    account_id: Optional[int] = None
    org_id: Optional[int] = None
    try:
        contact = db.query(models.Contact).filter(models.Contact.id == contact_id).first()
        if contact:
            org_id = contact.contact_organization_id
        user = db.query(models.User).filter(models.User.id == user_id).first()
        if user and user.org_id:
            acct = db.query(models.Account).filter(models.Account.org_id == user.org_id).first()
            if acct:
                account_id = acct.id
    except Exception as e:
        logger.debug(f"Activity embedding: could not resolve account_id: {e}")
        return

    if not account_id:
        return

    # Resolve source_type via the shared helper so the value is always one of
    # rag_service.PRESEND_SOURCE_TYPES (which get_presend_snapshot queries).
    embed_source_type = activity_source_type(activity_type)
    embed_source_id = f"activity:{activity_id}"

    summary_text = build_activity_summary(
        activity_type=activity_type,
        direction=direction,
        subject=subject,
        summary=summary,
        occurred_at=occurred_at,
    )

    async def _embed() -> None:
        session = SessionLocal()
        try:
            await store_activity_summary(
                db=session,
                account_id=account_id,
                source_type=embed_source_type,
                source_id=embed_source_id,
                summary=summary_text,
                contact_id=contact_id,
                org_id=org_id,
                occurred_at=occurred_at,
            )
        except Exception as e:
            logger.warning(f"Activity embedding failed for activity {activity_id}: {e}")
            try:
                session.rollback()
            except Exception:
                pass
        finally:
            session.close()

    # Narrow check: get_running_loop() raises RuntimeError only for "no running
    # event loop" — catch exactly that and nothing else.
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None:
        task = loop.create_task(_embed())
        _pending_embed_tasks.add(task)
        task.add_done_callback(_pending_embed_tasks.discard)
        return

    global _activity_embed_queue_depth

    # Drop under sustained burst rather than let the internal queue grow
    # without bound. The pool's queue is memory-resident; in prod a stuck pool
    # (e.g. OpenAI outage) would otherwise balloon RSS by ~payload * queued.
    with _activity_embed_pool_lock:
        if _activity_embed_queue_depth >= _ACTIVITY_EMBED_MAX_QUEUED:
            logger.warning(
                "Activity embedding pool saturated (%d pending); dropping activity %d",
                _activity_embed_queue_depth,
                activity_id,
            )
            return
        _activity_embed_queue_depth += 1

    def _runner() -> None:
        global _activity_embed_queue_depth
        try:
            asyncio.run(_embed())
        except Exception as e:
            logger.debug(f"Activity embedding sync run failed: {e}")
        finally:
            with _activity_embed_pool_lock:
                _activity_embed_queue_depth -= 1

    try:
        _get_activity_embed_pool().submit(_runner)
    except RuntimeError as e:
        # Pool can reject submissions post-shutdown (e.g. during interpreter
        # teardown). Roll back the depth bump and log — the caller still
        # succeeds because embedding is fire-and-forget.
        with _activity_embed_pool_lock:
            _activity_embed_queue_depth -= 1
        logger.debug(f"Activity embedding pool unavailable: {e}")


def update_contact_stats(db: Session, contact_id: int) -> None:
    """
    Recompute all stats from scratch (safe full recalc).
    Call this after bulk operations or when incremental updates may have drifted.
    """
    stats = db.query(models.ContactStats).filter(
        models.ContactStats.contact_id == contact_id
    ).first()
    if not stats:
        stats = models.ContactStats(contact_id=contact_id)
        db.add(stats)

    stats.emails_sent = db.query(func.count(models.ContactActivity.id)).filter(
        models.ContactActivity.contact_id == contact_id,
        models.ContactActivity.activity_type == "email_sent",
    ).scalar() or 0

    stats.emails_received = db.query(func.count(models.ContactActivity.id)).filter(
        models.ContactActivity.contact_id == contact_id,
        models.ContactActivity.direction == "inbound",
    ).scalar() or 0

    stats.reply_rate = (
        (stats.emails_received / stats.emails_sent * 100)
        if stats.emails_sent > 0 else 0.0
    )

    stats.meetings_count = db.query(func.count(models.MeetingHistory.id)).filter(
        models.MeetingHistory.contact_id == contact_id,
    ).scalar() or 0

    stats.active_sequences = db.query(func.count(models.SequenceRun.id)).filter(
        models.SequenceRun.contact_id == contact_id,
        models.SequenceRun.status == "active",
    ).scalar() or 0

    stats.open_deals = db.query(func.count(models.ContactDeal.id)).filter(
        models.ContactDeal.contact_id == contact_id,
        models.ContactDeal.status == "open",
        models.ContactDeal.deleted_at.is_(None),
    ).scalar() or 0

    # Total deal value includes open + won deals (excludes lost)
    stats.total_deal_value = db.query(func.coalesce(func.sum(models.ContactDeal.value), 0)).filter(
        models.ContactDeal.contact_id == contact_id,
        models.ContactDeal.status.in_(["open", "won"]),
        models.ContactDeal.deleted_at.is_(None),
    ).scalar() or 0

    stats.last_computed_at = datetime.now(timezone.utc)
    db.flush()


def merge_contacts(
    db: Session,
    user_id: int,
    keep_id: int,
    merge_id: int,
) -> models.Contact:
    """
    Merge merge_id into keep_id. Moves all child records, soft-deletes the merged contact.
    """
    keep = db.query(models.Contact).filter(
        models.Contact.id == keep_id,
        models.Contact.user_id == user_id,
        models.Contact.deleted_at.is_(None),
    ).first()
    merge = db.query(models.Contact).filter(
        models.Contact.id == merge_id,
        models.Contact.user_id == user_id,
        models.Contact.deleted_at.is_(None),
    ).first()

    if not keep or not merge:
        raise ValueError("Both contacts must exist and belong to user")

    # Move all child records from merge -> keep
    db.query(models.ContactEmail).filter(
        models.ContactEmail.contact_id == merge_id
    ).update({"contact_id": keep_id})

    db.query(models.ContactActivity).filter(
        models.ContactActivity.contact_id == merge_id
    ).update({"contact_id": keep_id})

    db.query(models.ContactDeal).filter(
        models.ContactDeal.contact_id == merge_id
    ).update({"contact_id": keep_id})

    db.query(models.ThreadDigest).filter(
        models.ThreadDigest.contact_id == merge_id
    ).update({"contact_id": keep_id})

    db.query(models.MeetingHistory).filter(
        models.MeetingHistory.contact_id == merge_id
    ).update({"contact_id": keep_id})

    db.query(models.SequenceRun).filter(
        models.SequenceRun.contact_id == merge_id
    ).update({"contact_id": keep_id})

    db.query(models.EmailQueue).filter(
        models.EmailQueue.contact_id == merge_id
    ).update({"contact_id": keep_id})

    # Log the merge as an activity
    now = datetime.now(timezone.utc)
    db.add(models.ContactActivity(
        contact_id=keep_id,
        user_id=user_id,
        activity_type="contact_merged",
        title=f"Merged with {merge.name or merge.email}",
        occurred_at=now,
        activity_at=now,
        is_new=False,
    ))

    # Soft-delete the merged contact
    merge.deleted_at = now

    # Delete orphaned stats/pulse from merged contact
    db.query(models.ContactStats).filter(
        models.ContactStats.contact_id == merge_id
    ).delete()
    db.query(models.ContactPulse).filter(
        models.ContactPulse.contact_id == merge_id
    ).delete()

    # Recompute stats on kept contact
    db.flush()
    update_contact_stats(db, keep_id)

    logger.info("Merged contacts", extra={
        "user_id": user_id, "keep_id": keep_id, "merge_id": merge_id,
    })
    return keep


async def generate_contact_pulse(
    db: Session,
    user_id: int,
    contact_id: int,
) -> models.ContactPulse:
    """
    Generate or refresh the AI Contact Pulse for a contact.
    Summarizes all activities, deals, meetings into actionable intelligence.
    """
    import json
    from ai_service import analyze_with_ai

    contact = db.query(models.Contact).filter(
        models.Contact.id == contact_id,
        models.Contact.user_id == user_id,
        models.Contact.deleted_at.is_(None),
    ).first()
    if not contact:
        raise ValueError("Contact not found")

    # Gather context
    recent_activities = db.query(models.ContactActivity).filter(
        models.ContactActivity.contact_id == contact_id,
    ).order_by(models.ContactActivity.activity_at.desc().nullslast()).limit(30).all()

    deals = db.query(models.ContactDeal).filter(
        models.ContactDeal.contact_id == contact_id,
        models.ContactDeal.deleted_at.is_(None),
    ).all()

    meetings = db.query(models.MeetingHistory).filter(
        models.MeetingHistory.contact_id == contact_id,
    ).order_by(models.MeetingHistory.meeting_date.desc()).limit(5).all()

    stats = db.query(models.ContactStats).filter(
        models.ContactStats.contact_id == contact_id,
    ).first()

    # Build prompt context
    activities_text = "\n".join([
        f"- [{a.activity_type}] {a.summary or a.title} ({a.direction or 'n/a'}, {a.activity_at})"
        for a in recent_activities
    ])

    deals_text = "\n".join([
        f"- {d.title}: {d.status} ({d.stage_name}), ${d.value or 0}"
        for d in deals
    ]) or "No deals"

    meetings_text = "\n".join([
        f"- {m.meeting_date}: {m.summary}"
        for m in meetings
    ]) or "No meetings"

    stats_text = ""
    if stats:
        stats_text = f"Emails sent: {stats.emails_sent}, Received: {stats.emails_received}, Reply rate: {stats.reply_rate:.1f}%, Meetings: {stats.meetings_count}"

    prompt = f"""Analyze this contact and provide a JSON intelligence summary.

Contact: {contact.name or contact.email}
Company: {contact.company or 'Unknown'}
Status: {contact.status}
Stats: {stats_text}

Recent Activity (newest first):
{activities_text or "No activities"}

Deals:
{deals_text}

Meetings:
{meetings_text}

Return ONLY a JSON object with these fields:
- summary: 1-2 sentence executive summary of this contact's engagement
- sentiment: "positive", "neutral", or "negative"
- engagement: "high", "medium", or "low"
- intent: "interested", "evaluating", or "not_interested"
- action: "continue_sequence", "pause", "send_followup", or "close_out"
- topics: array of key discussion topics (max 5)
- objections: array of objections or concerns raised (max 5)
"""

    try:
        result = await analyze_with_ai(prompt, "")
        data = json.loads(result) if isinstance(result, str) else result
    except Exception as e:
        logger.error(f"Pulse generation failed for contact {contact_id}: {e}")
        data = {
            "summary": "Unable to generate pulse — insufficient data.",
            "sentiment": "unknown",
            "engagement": "low",
            "intent": "evaluating",
            "action": "send_followup",
            "topics": [],
            "objections": [],
        }

    now = datetime.now(timezone.utc)

    # Get last meeting date
    last_meeting = db.query(models.MeetingHistory.meeting_date).filter(
        models.MeetingHistory.contact_id == contact_id,
    ).order_by(models.MeetingHistory.meeting_date.desc()).first()

    # Upsert pulse
    pulse = db.query(models.ContactPulse).filter(
        models.ContactPulse.contact_id == contact_id,
    ).first()

    if not pulse:
        pulse = models.ContactPulse(
            contact_id=contact_id,
            user_id=user_id,
        )
        db.add(pulse)

    # Snapshot the previous pulse state BEFORE overwriting it so we can
    # detect a "crossed into negative" transition for the Fresh Check rule 4
    # producer (#175). A fresh pulse (no prior row) is treated as if it had
    # previously been positive — we do not want to fire [pulse] on every
    # new contact's first negative read, only on genuine shifts.
    prev_sentiment = pulse.sentiment
    prev_intent = pulse.intent
    prev_engagement = pulse.engagement_level

    pulse.summary = data.get("summary")
    pulse.sentiment = data.get("sentiment")
    pulse.engagement_level = data.get("engagement")
    pulse.intent = data.get("intent")
    pulse.recommended_action = data.get("action")
    pulse.key_topics = data.get("topics", [])
    pulse.key_objections = data.get("objections", [])
    pulse.last_meeting_date = last_meeting[0] if last_meeting else None
    pulse.generated_at = now

    db.flush()
    logger.info("Generated contact pulse", extra={"user_id": user_id, "contact_id": contact_id})

    # Fresh Check rule 4 — [pulse] embedding on negative-state crossover.
    # Non-blocking: any failure is logged and swallowed so pulse generation
    # itself never fails because of an embedding hiccup.
    try:
        _maybe_emit_pulse_shift_embedding(
            db=db,
            user_id=user_id,
            contact=contact,
            prev_sentiment=prev_sentiment,
            prev_intent=prev_intent,
            prev_engagement=prev_engagement,
            new_pulse=pulse,
            now=now,
        )
    except Exception as e:
        logger.debug(f"[RAG] Pulse shift embedding skipped (non-blocking): {e}")

    return pulse


def _maybe_emit_pulse_shift_embedding(
    db: Session,
    user_id: int,
    contact: "models.Contact",
    prev_sentiment: Optional[str],
    prev_intent: Optional[str],
    prev_engagement: Optional[str],
    new_pulse: "models.ContactPulse",
    now: datetime,
) -> None:
    """Emit a [pulse] ContentEmbedding when a contact's Pulse just crossed
    into a negative state. "Crossed" means the prior value was not negative
    (or there was no prior pulse at all) and the new value is negative.

    Uses the same fire-and-forget scheduling pattern as
    _schedule_activity_embedding so the caller never blocks on OpenAI I/O,
    and never commits the caller's in-progress transaction.
    """
    def _is_negative_sentiment(v: Optional[str]) -> bool:
        return (v or "").lower() == "negative"

    def _is_negative_intent(v: Optional[str]) -> bool:
        return (v or "").lower() == "not_interested"

    def _is_negative_engagement(v: Optional[str]) -> bool:
        # "low" alone is a soft signal and would fire on brand-new contacts;
        # pair it with a non-positive sentiment so we only flag genuine decay.
        return (v or "").lower() == "low"

    new_sent = new_pulse.sentiment
    new_intent = new_pulse.intent
    new_engagement = new_pulse.engagement_level

    # Strongest signals fire independently. The soft engagement signal only
    # fires when sentiment is non-positive, to avoid chatter on cold leads.
    crossed = False
    reasons = []
    if _is_negative_sentiment(new_sent) and not _is_negative_sentiment(prev_sentiment):
        crossed = True
        reasons.append(f"sentiment {prev_sentiment or 'unknown'} → {new_sent}")
    if _is_negative_intent(new_intent) and not _is_negative_intent(prev_intent):
        crossed = True
        reasons.append(f"intent {prev_intent or 'unknown'} → {new_intent}")
    if (
        _is_negative_engagement(new_engagement)
        and not _is_negative_engagement(prev_engagement)
        and (new_sent or "").lower() != "positive"
    ):
        crossed = True
        reasons.append(f"engagement {prev_engagement or 'unknown'} → {new_engagement}")

    if not crossed:
        return

    # Resolve account_id up front — the background task does not see the
    # caller's session, so we capture primitives here.
    account_id: Optional[int] = None
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user and user.org_id:
        acct = db.query(models.Account).filter(models.Account.org_id == user.org_id).first()
        if acct:
            account_id = acct.id
    if not account_id:
        return

    from rag_service import FRESH_CHECK_TAG_PULSE, store_activity_summary

    contact_name = contact.name or contact.email or f"contact {contact.id}"
    summary_text = (
        f"{FRESH_CHECK_TAG_PULSE} Pulse shifted negative {now.strftime('%Y-%m-%d')}: "
        f"{contact_name} — {'; '.join(reasons)}. Summary: {new_pulse.summary or ''}"
    ).strip()

    _dispatch_pulse_embedding(
        account_id=account_id,
        contact_id=contact.id,
        org_id=contact.contact_organization_id,
        summary_text=summary_text,
        occurred_at=now,
    )


def _dispatch_pulse_embedding(
    *,
    account_id: int,
    contact_id: int,
    org_id: Optional[int],
    summary_text: str,
    occurred_at: datetime,
) -> None:
    """Fire-and-forget scheduler for the [pulse] embedding write. Uses the
    same asyncio-task-or-thread-pool split as _schedule_activity_embedding."""
    import asyncio
    from rag_service import store_activity_summary

    source_id = f"pulse:{contact_id}:{int(occurred_at.timestamp())}"

    async def _embed() -> None:
        session = SessionLocal()
        try:
            await store_activity_summary(
                db=session,
                account_id=account_id,
                source_type="activity",
                source_id=source_id,
                summary=summary_text,
                contact_id=contact_id,
                org_id=org_id,
                occurred_at=occurred_at,
            )
        except Exception as e:
            logger.warning(f"[RAG] Pulse embedding failed for contact {contact_id}: {e}")
            try:
                session.rollback()
            except Exception:
                pass
        finally:
            session.close()

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None:
        task = loop.create_task(_embed())
        _pending_embed_tasks.add(task)
        task.add_done_callback(_pending_embed_tasks.discard)
        return

    # Sync caller — punt to the shared bounded pool the activity embed
    # scheduler already uses so we inherit its backpressure.
    global _activity_embed_queue_depth
    with _activity_embed_pool_lock:
        if _activity_embed_queue_depth >= _ACTIVITY_EMBED_MAX_QUEUED:
            logger.warning(
                "[RAG] Pulse embedding dropped — activity pool queue full (%d pending)",
                _activity_embed_queue_depth,
            )
            return
        _activity_embed_queue_depth += 1

    def _runner() -> None:
        global _activity_embed_queue_depth
        try:
            asyncio.run(_embed())
        except Exception as e:
            logger.debug(f"[RAG] Pulse embedding sync run failed: {e}")
        finally:
            with _activity_embed_pool_lock:
                _activity_embed_queue_depth -= 1

    try:
        _get_activity_embed_pool().submit(_runner)
    except RuntimeError as e:
        with _activity_embed_pool_lock:
            _activity_embed_queue_depth -= 1
        logger.debug(f"[RAG] Pulse embedding pool unavailable: {e}")


# --- Legacy compatibility wrappers ---

def record_email_sent(
    db: Session,
    contact: models.Contact,
    email_queue_id: int,
    subject: str,
) -> None:
    """Record that an email was sent to a contact. Legacy wrapper around log_activity."""
    log_activity(
        db=db,
        user_id=contact.user_id,
        contact_id=contact.id,
        activity_type="email_sent",
        direction="outbound",
        source_type="scurry_sequence",
        email_queue_id=email_queue_id,
        subject=subject,
        title=f"Email sent: {subject[:50]}{'...' if len(subject) > 50 else ''}",
    )
