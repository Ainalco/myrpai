"""
Fireflies meeting sync for the contact system.
When a Fireflies transcript is processed, creates MeetingHistory records
for each external participant and logs meeting activities on their timelines.

Used by:
  - webhooks.py (after Fireflies webhook fetches transcript)
"""
import json
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from datetime import datetime, timezone
import logging

import models
from contacts_service import get_or_create_contact, log_activity, update_contact_stats

logger = logging.getLogger(__name__)


def _parse_internal_domains(internal_domains_str: Optional[str]) -> List[str]:
    """Parse comma-separated internal domains string into a list."""
    if not internal_domains_str:
        return []
    return [d.strip().lower() for d in internal_domains_str.split(",") if d.strip()]


def _is_internal_email(email: str, internal_domains: List[str]) -> bool:
    """Check if an email belongs to an internal domain."""
    if not email or "@" not in email:
        return True  # Treat invalid emails as internal (skip them)
    domain = email.split("@")[-1].lower()
    return any(domain == d or domain.endswith("." + d) for d in internal_domains)


def _get_current_deal_stage(db: Session, contact_id: int) -> Optional[str]:
    """Get the current pipeline stage of the contact's most recent open deal."""
    deal = db.query(models.ContactDeal).filter(
        models.ContactDeal.contact_id == contact_id,
        models.ContactDeal.status == "open",
        models.ContactDeal.deleted_at.is_(None),
    ).order_by(models.ContactDeal.updated_at.desc().nullslast()).first()
    return deal.stage_name if deal else None


async def _analyze_meeting_transcript(transcript_text: str) -> Dict[str, Any]:
    """
    Call Claude to extract meeting intelligence from transcript.
    Returns dict with summary, key_points, objections, buying_signals.
    One call per meeting (shared across all participant contacts).
    """
    from ai_service import analyze_with_ai

    prompt = """Analyze this meeting transcript and return ONLY a JSON object with these fields:
- summary: 2-3 sentence summary of the meeting
- key_points: array of key discussion points (max 8, each a short sentence)
- objections: array of objections or concerns raised by the prospect (max 5, each a short phrase)
- buying_signals: array of positive buying indicators (max 5, each a short phrase)

If a field has no data, use an empty array [].
Return ONLY the JSON object, no markdown formatting."""

    try:
        result = await analyze_with_ai(prompt, {"transcript": transcript_text})
        # Try to parse as JSON
        if isinstance(result, str):
            # Clean markdown formatting if present
            cleaned = result.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            data = json.loads(cleaned)
        else:
            data = result

        return {
            "summary": data.get("summary", ""),
            "key_points": data.get("key_points", []),
            "objections": data.get("objections", []),
            "buying_signals": data.get("buying_signals", []),
        }
    except Exception as e:
        logger.error(f"Meeting transcript analysis failed: {e}")
        return {
            "summary": "Meeting transcript analysis unavailable.",
            "key_points": [],
            "objections": [],
            "buying_signals": [],
        }


def _parse_meeting_date(date_str: Optional[str]) -> Optional[datetime]:
    """Parse Fireflies meeting date (ISO format or Unix timestamp)."""
    if not date_str:
        return None
    try:
        # Try ISO format first
        if "T" in str(date_str):
            dt = datetime.fromisoformat(str(date_str).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        # Try Unix timestamp (seconds or milliseconds)
        ts = float(date_str)
        if ts > 1e12:  # Milliseconds
            ts = ts / 1000
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    except (ValueError, TypeError, OSError):
        return None


async def sync_meeting_to_contacts(
    db: Session,
    user_id: int,
    transcript_data: Dict[str, Any],
    meeting_url: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Sync a Fireflies meeting transcript into MeetingHistory records
    for each external participant.

    Args:
        db: Database session
        user_id: Owner user ID (from workflow)
        transcript_data: Full transcript data from fetch_transcript()
        meeting_url: Fireflies meeting URL (optional)

    Returns:
        Dict with sync results: contactsLinked, meetingsCreated
    """
    meeting_id = transcript_data.get("meeting_id", "")
    if not meeting_id:
        return {"success": False, "error": "No meeting_id in transcript data"}

    # Get user for internal domains
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        return {"success": False, "error": "User not found"}

    internal_domains = _parse_internal_domains(user.internal_domains)

    # Extract external participants
    participants = transcript_data.get("participants", [])
    external_participants = []
    for p in participants:
        if isinstance(p, dict):
            email = (p.get("email") or "").strip().lower()
            name = p.get("name", "")
        else:
            continue
        if email and not _is_internal_email(email, internal_domains):
            external_participants.append({"email": email, "name": name})

    if not external_participants:
        logger.info(f"No external participants in meeting {meeting_id}")
        return {"success": True, "contactsLinked": 0, "meetingsCreated": 0}

    # Analyze transcript with AI (once per meeting, shared across contacts)
    transcript_text = transcript_data.get("transcript", "")
    if transcript_text:
        analysis = await _analyze_meeting_transcript(transcript_text)
    else:
        analysis = {
            "summary": transcript_data.get("meeting_title", "Meeting"),
            "key_points": [],
            "objections": [],
            "buying_signals": [],
        }

    # Parse meeting metadata
    meeting_date = _parse_meeting_date(transcript_data.get("meeting_date"))
    duration_seconds = transcript_data.get("duration", 0)
    duration_minutes = int(duration_seconds / 60) if duration_seconds else None
    meeting_title = transcript_data.get("meeting_title", "Meeting")

    # All participant names for the participants JSON field
    all_participant_names = [
        p.get("name") or p.get("email", "Unknown") if isinstance(p, dict) else str(p)
        for p in participants
    ]

    result = {
        "success": True,
        "contactsLinked": 0,
        "meetingsCreated": 0,
    }

    now = datetime.now(timezone.utc)

    for participant in external_participants:
        try:
            # Get or create contact for this participant
            contact = get_or_create_contact(
                db=db,
                user_id=user_id,
                email=participant["email"],
                name=participant["name"] or None,
            )
            result["contactsLinked"] += 1

            # Idempotency: check if this meeting already exists for this contact
            existing = db.query(models.MeetingHistory).filter(
                models.MeetingHistory.contact_id == contact.id,
                models.MeetingHistory.external_meeting_id == str(meeting_id),
            ).first()

            if existing:
                continue  # Already synced

            # Get current deal stage for context
            deal_stage = _get_current_deal_stage(db, contact.id)

            # Create MeetingHistory record (unique constraint prevents duplicates on race)
            meeting = models.MeetingHistory(
                contact_id=contact.id,
                user_id=user_id,
                external_meeting_id=str(meeting_id),
                source="Fireflies",
                meeting_date=meeting_date or now,
                summary=analysis["summary"],
                key_points=analysis["key_points"],
                objections=analysis["objections"],
                buying_signals=analysis["buying_signals"],
                deal_stage_at_time=deal_stage,
                duration_minutes=duration_minutes,
                participants=all_participant_names,
                raw_transcript_url=meeting_url,
            )
            db.add(meeting)
            try:
                with db.begin_nested():  # SAVEPOINT — only rolls back this insert, not the whole tx
                    db.flush()
            except IntegrityError:
                continue  # Concurrent webhook created it first — skip gracefully

            # Log activity on contact timeline
            log_activity(
                db=db,
                user_id=user_id,
                contact_id=contact.id,
                activity_type="meeting",
                direction="internal",
                source_type="scurry_transcript",
                source_id=f"fireflies_meeting_{meeting_id}",
                summary=f"{meeting_title}: {analysis['summary'][:100]}" if analysis["summary"] else meeting_title,
                title=f"Meeting: {meeting_title}",
                occurred_at=meeting_date or now,
            )

            # Update contact stats (meetings_count)
            update_contact_stats(db, contact.id)

            result["meetingsCreated"] += 1

        except Exception as e:
            logger.error(f"Failed to sync meeting {meeting_id} for {participant['email']}: {e}")
            continue

    db.commit()

    logger.info("Fireflies meeting sync complete", extra={
        "user_id": user_id,
        "meeting_id": meeting_id,
        "contacts_linked": result["contactsLinked"],
        "meetings_created": result["meetingsCreated"],
    })

    return result


async def backfill_meetings_from_fireflies(
    db: Session,
    user_id: int,
    limit: int = 50,
) -> Dict[str, Any]:
    """
    Backfill MeetingHistory from recent Fireflies transcripts.
    Fetches the last N transcripts, skips any already synced,
    and runs sync_meeting_to_contacts for each new one.
    """
    import asyncio
    from fireflies_service import list_recent_transcripts, fetch_transcript, get_meeting_url

    result = {
        "success": True,
        "transcriptsChecked": 0,
        "transcriptsSkipped": 0,
        "transcriptsSynced": 0,
        "meetingsCreated": 0,
        "contactsLinked": 0,
        "errors": 0,
    }

    # Step 1: Get recent transcript IDs
    try:
        transcripts = await list_recent_transcripts(db=db, user_id=user_id, limit=limit)
    except Exception as e:
        logger.error(f"Failed to list Fireflies transcripts: {e}")
        return {"success": False, "error": f"Failed to list transcripts: {str(e)}"}

    if not transcripts:
        return result

    transcript_ids = [t["id"] for t in transcripts if t.get("id")]
    result["transcriptsChecked"] = len(transcript_ids)

    # Step 2: Check which meetings are already synced (batch pre-check)
    existing_ids = set()
    if transcript_ids:
        rows = db.query(models.MeetingHistory.external_meeting_id).filter(
            models.MeetingHistory.user_id == user_id,
            models.MeetingHistory.external_meeting_id.in_([str(tid) for tid in transcript_ids]),
        ).distinct().all()
        existing_ids = {row[0] for row in rows}

    # Step 3: Process new transcripts
    for t_summary in transcripts:
        t_id = t_summary.get("id")
        if not t_id:
            continue

        if str(t_id) in existing_ids:
            result["transcriptsSkipped"] += 1
            continue

        try:
            # Fetch full transcript (includes participants + text for AI)
            transcript_data = await fetch_transcript(t_id, db=db, user_id=user_id)
            if not transcript_data:
                result["errors"] += 1
                continue

            meeting_url = await get_meeting_url(t_id, db=db, user_id=user_id)

            # Sync to contacts (creates MeetingHistory + activities)
            sync_result = await sync_meeting_to_contacts(
                db=db,
                user_id=user_id,
                transcript_data=transcript_data,
                meeting_url=meeting_url,
            )

            if sync_result.get("meetingsCreated", 0) > 0:
                result["transcriptsSynced"] += 1
                result["meetingsCreated"] += sync_result.get("meetingsCreated", 0)
                result["contactsLinked"] += sync_result.get("contactsLinked", 0)
            else:
                result["transcriptsSkipped"] += 1

        except Exception as e:
            logger.error(f"Failed to backfill transcript {t_id}: {e}")
            result["errors"] += 1
            continue

        # Throttle: 200ms between transcripts (AI call + 2 API calls each)
        await asyncio.sleep(0.2)

    logger.info("Fireflies backfill complete", extra={
        "user_id": user_id,
        "checked": result["transcriptsChecked"],
        "synced": result["transcriptsSynced"],
        "skipped": result["transcriptsSkipped"],
        "meetings_created": result["meetingsCreated"],
    })

    return result
