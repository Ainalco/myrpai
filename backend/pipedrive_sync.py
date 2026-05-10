"""
Pipedrive CRM sync for the contact system.
Syncs persons and deals from Pipedrive into contact_deals and updates contact/org metadata.

Used by:
  - pipedrive_worker.py (background sync every 5 min)
  - contacts.py (manual POST /contacts/{id}/sync-crm endpoint)
"""
import httpx
import asyncio
import re
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import or_, and_, func
from datetime import datetime, timedelta, timezone
import logging

import models
from contacts_service import log_activity, update_contact_stats, generate_initials

logger = logging.getLogger(__name__)

PIPEDRIVE_API_BASE = "https://api.pipedrive.com/v1"

# Smart interval thresholds
INTERVAL_ACTIVE = timedelta(minutes=15)   # Contacts with open deals or recent activity
INTERVAL_DORMANT = timedelta(hours=6)     # Everything else
ACTIVE_WINDOW = timedelta(hours=48)       # "Recently active" = activity within 48h


async def _get_api_key(db: Session, user_id: int) -> Optional[str]:
    """Get user's Pipedrive API key from encrypted storage."""
    from pipedrive_service import get_pipedrive_api_key
    return await get_pipedrive_api_key(db, user_id)


async def _fetch_person_deals(api_key: str, person_id: int) -> List[dict]:
    """Fetch ALL deals for a Pipedrive person (paginated)."""
    all_deals = []
    start = 0

    async with httpx.AsyncClient(timeout=30.0) as client:
        while True:
            response = await client.get(
                f"{PIPEDRIVE_API_BASE}/persons/{person_id}/deals",
                params={
                    "api_token": api_key,
                    "status": "all_not_deleted",
                    "start": start,
                    "limit": 100,
                },
            )
            # Retry once on rate limit
            if response.status_code == 429:
                logger.warning("Pipedrive 429 in _fetch_person_deals, sleeping 30s")
                await asyncio.sleep(30)
                response = await client.get(
                    f"{PIPEDRIVE_API_BASE}/persons/{person_id}/deals",
                    params={
                        "api_token": api_key,
                        "status": "all_not_deleted",
                        "start": start,
                        "limit": 100,
                    },
                )
            response.raise_for_status()
            data = response.json()

            items = data.get("data") or []
            all_deals.extend(items)

            pagination = data.get("additional_data", {}).get("pagination", {})
            if pagination.get("more_items_in_collection"):
                start = pagination.get("next_start", start + 100)
            else:
                break

    return all_deals


async def _get_stage_map(db: Session, user_id: int) -> Dict[str, str]:
    """Get Pipedrive stage_id → stage_name mapping (cached 24h in pipedrive_service)."""
    from pipedrive_service import get_deal_stages
    result = await get_deal_stages(db, user_id)
    if result.get("success"):
        return result.get("stages", {})
    return {}


def _parse_date(date_str: Optional[str]) -> Optional[datetime]:
    """Parse Pipedrive date string (YYYY-MM-DD) into datetime."""
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def _parse_datetime(dt_str: Optional[str]) -> Optional[datetime]:
    """Parse Pipedrive datetime string (YYYY-MM-DD HH:MM:SS or YYYY-MM-DD) into timezone-aware datetime."""
    if not dt_str:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(dt_str, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _strip_html(html: Optional[str]) -> str:
    """Strip HTML tags from Pipedrive note content, preserving line breaks."""
    if not html:
        return ""
    import html as html_mod
    text = html
    # Block-level elements → newlines
    text = re.sub(r'<br\s*/?>',  '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</(?:p|div|h[1-6]|tr|blockquote)>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<li[^>]*>', '\n• ', text, flags=re.IGNORECASE)
    text = re.sub(r'<hr[^>]*>', '\n---\n', text, flags=re.IGNORECASE)
    # Strip remaining tags
    text = re.sub(r'<[^>]+>', '', text)
    # Decode HTML entities (&amp; &lt; &nbsp; etc.)
    text = html_mod.unescape(text)
    # Collapse 3+ consecutive newlines into 2
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


# Pipedrive activity type → our activity_type
_ACTIVITY_TYPE_MAP = {
    "call": "call",
    "meeting": "meeting",
    "email": "email_sent",
    "task": "note",
    "deadline": "note",
    "lunch": "meeting",
}


async def _emit_deal_lost_org_signal(
    *,
    db: Session,
    user_id: int,
    contact_id: int,
    deal_external_id: str,
    deal_title: str,
) -> None:
    """Fresh Check rule 5 helper: when a Pipedrive deal moves to "lost",
    emit an [org_signal] ContentEmbedding keyed on the contact's org so
    sibling contacts see the signal on their next pre-send snapshot.

    Resolves account_id and org_id with the caller's session (reads only),
    then delegates to rag_service.emit_org_signal which opens a fresh
    session and commits its own write — the caller's transaction is never
    touched. No-op if the contact has no org or the account can't be
    resolved.
    """
    from rag_service import emit_org_signal

    contact = db.query(models.Contact).filter(models.Contact.id == contact_id).first()
    if not contact or not contact.contact_organization_id:
        return

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user or not user.org_id:
        return
    acct = db.query(models.Account).filter(models.Account.org_id == user.org_id).first()
    if not acct:
        return

    # Deterministic source_id dedupes re-sync of the same deal.
    source_id = f"org_signal:deal_lost:{deal_external_id or f'c{contact_id}d{contact.contact_organization_id}'}"
    signal_text = f"Deal lost at sibling contact: {deal_title or 'Untitled deal'}"

    await emit_org_signal(
        account_id=acct.id,
        org_id=contact.contact_organization_id,
        signal_text=signal_text,
        source_id=source_id,
        originating_contact_id=contact_id,
        occurred_at=datetime.now(timezone.utc),
    )

# Pipedrive activity type → direction
_ACTIVITY_DIR_MAP = {
    "call": "outbound",
    "meeting": "internal",
    "email": "outbound",
    "task": "internal",
    "deadline": "internal",
    "lunch": "internal",
}


async def _fetch_person_activities(api_key: str, person_id: int) -> List[dict]:
    """Fetch ALL activities for a Pipedrive person (paginated)."""
    all_activities = []
    start = 0

    async with httpx.AsyncClient(timeout=30.0) as client:
        while True:
            response = await client.get(
                f"{PIPEDRIVE_API_BASE}/persons/{person_id}/activities",
                params={
                    "api_token": api_key,
                    "start": start,
                    "limit": 100,
                },
            )
            if response.status_code == 429:
                logger.warning("Pipedrive 429 in _fetch_person_activities, sleeping 30s")
                await asyncio.sleep(30)
                response = await client.get(
                    f"{PIPEDRIVE_API_BASE}/persons/{person_id}/activities",
                    params={"api_token": api_key, "start": start, "limit": 100},
                )
            response.raise_for_status()
            data = response.json()

            items = data.get("data") or []
            all_activities.extend(items)

            pagination = data.get("additional_data", {}).get("pagination", {})
            if pagination.get("more_items_in_collection"):
                start = pagination.get("next_start", start + 100)
            else:
                break

    return all_activities


async def _fetch_person_notes(api_key: str, person_id: int) -> List[dict]:
    """Fetch ALL notes for a Pipedrive person (paginated)."""
    all_notes = []
    start = 0

    async with httpx.AsyncClient(timeout=30.0) as client:
        while True:
            response = await client.get(
                f"{PIPEDRIVE_API_BASE}/notes",
                params={
                    "api_token": api_key,
                    "person_id": person_id,
                    "start": start,
                    "limit": 100,
                },
            )
            if response.status_code == 429:
                logger.warning("Pipedrive 429 in _fetch_person_notes, sleeping 30s")
                await asyncio.sleep(30)
                response = await client.get(
                    f"{PIPEDRIVE_API_BASE}/notes",
                    params={"api_token": api_key, "person_id": person_id, "start": start, "limit": 100},
                )
            response.raise_for_status()
            data = response.json()

            items = data.get("data") or []
            all_notes.extend(items)

            pagination = data.get("additional_data", {}).get("pagination", {})
            if pagination.get("more_items_in_collection"):
                start = pagination.get("next_start", start + 100)
            else:
                break

    return all_notes


def _sync_pipedrive_activity(
    db: Session,
    user_id: int,
    contact_id: int,
    act_data: dict,
    deal_id_map: Dict[str, int],
) -> bool:
    """
    Sync a single Pipedrive activity into ContactActivity.
    Returns True if a new activity was created (not a duplicate).
    """
    pd_activity_id = str(act_data.get("id", ""))
    source_id = f"pipedrive_activity_{pd_activity_id}"

    # Pre-check existence (reliable, no timing heuristic)
    already_exists = db.query(models.ContactActivity.id).filter(
        models.ContactActivity.user_id == user_id,
        models.ContactActivity.source_type == "crm_sync",
        models.ContactActivity.source_id == source_id,
    ).first() is not None

    if already_exists:
        return False

    pd_type = act_data.get("type", "task")
    activity_type = _ACTIVITY_TYPE_MAP.get(pd_type, "note")
    direction = _ACTIVITY_DIR_MAP.get(pd_type, "internal")

    subject_text = act_data.get("subject", "")
    note_text = _strip_html(act_data.get("note", ""))
    summary = note_text if note_text else subject_text

    # Best timestamp: done_time > due_date > add_time
    event_time = (
        _parse_datetime(act_data.get("marked_as_done_time"))
        or _parse_date(act_data.get("due_date"))
        or _parse_datetime(act_data.get("add_time"))
        or datetime.now(timezone.utc)
    )

    # Map Pipedrive deal_id to our internal deal_id
    pd_deal_id = str(act_data.get("deal_id", "")) if act_data.get("deal_id") else None
    our_deal_id = deal_id_map.get(pd_deal_id) if pd_deal_id else None

    log_activity(
        db=db,
        user_id=user_id,
        contact_id=contact_id,
        activity_type=activity_type,
        direction=direction,
        source_type="crm_sync",
        source_id=source_id,
        deal_id=our_deal_id,
        subject=subject_text or None,
        summary=summary or None,
        title=f"{pd_type.title()}: {subject_text[:60]}" if subject_text else f"Pipedrive {pd_type}",
        occurred_at=event_time,
    )

    return True


def _sync_pipedrive_note(
    db: Session,
    user_id: int,
    contact_id: int,
    note_data: dict,
    deal_id_map: Dict[str, int],
) -> bool:
    """
    Sync a single Pipedrive note into ContactActivity.
    Returns True if a new activity was created (not a duplicate).
    """
    pd_note_id = str(note_data.get("id", ""))
    source_id = f"pipedrive_note_{pd_note_id}"

    # Pre-check existence (reliable, no timing heuristic)
    already_exists = db.query(models.ContactActivity.id).filter(
        models.ContactActivity.user_id == user_id,
        models.ContactActivity.source_type == "crm_sync",
        models.ContactActivity.source_id == source_id,
    ).first() is not None

    if already_exists:
        return False

    content = _strip_html(note_data.get("content", ""))
    event_time = _parse_datetime(note_data.get("add_time")) or datetime.now(timezone.utc)

    # Map Pipedrive deal_id to our internal deal_id
    pd_deal_id = str(note_data.get("deal_id", "")) if note_data.get("deal_id") else None
    our_deal_id = deal_id_map.get(pd_deal_id) if pd_deal_id else None

    # Truncate content for title
    title_preview = content[:60] + "..." if len(content) > 60 else content
    title_preview = title_preview.replace("\n", " ").strip()

    log_activity(
        db=db,
        user_id=user_id,
        contact_id=contact_id,
        activity_type="note",
        direction="internal",
        source_type="crm_sync",
        source_id=source_id,
        deal_id=our_deal_id,
        summary=content or None,
        title=f"Pipedrive note: {title_preview}" if title_preview else "Pipedrive note",
        occurred_at=event_time,
    )

    return True


def _upsert_deal(
    db: Session,
    user_id: int,
    contact: models.Contact,
    deal_data: dict,
    stage_map: Dict[str, str],
) -> Dict[str, str]:
    """
    Create or update a single ContactDeal from Pipedrive deal data.
    Returns {"action": "created"/"updated"/"unchanged", "title": str, "old_stage": str|None, "new_stage": str|None}
    """
    external_deal_id = str(deal_data.get("id"))
    title = deal_data.get("title", "Untitled Deal")
    status = deal_data.get("status", "open")  # open, won, lost
    stage_id = str(deal_data.get("stage_id", ""))
    stage_name = stage_map.get(stage_id, f"Stage {stage_id}")
    value = deal_data.get("value")
    if value is not None:
        try:
            value = float(value)
        except (ValueError, TypeError):
            value = None
    currency = deal_data.get("currency", "USD")
    expected_close = _parse_date(deal_data.get("expected_close_date"))

    # Lookup existing deal
    existing = db.query(models.ContactDeal).filter(
        models.ContactDeal.contact_id == contact.id,
        models.ContactDeal.external_deal_id == external_deal_id,
        models.ContactDeal.crm_provider == "pipedrive",
    ).first()

    if existing:
        old_stage = existing.stage_name
        old_status = existing.status
        changed = False

        if existing.title != title:
            existing.title = title
            changed = True
        if existing.status != status:
            existing.status = status
            changed = True
        if existing.stage_name != stage_name:
            existing.stage_name = stage_name
            changed = True
        if existing.value != value:
            existing.value = value
            changed = True
        if existing.currency != currency:
            existing.currency = currency
            changed = True
        if existing.expected_close_date != expected_close:
            existing.expected_close_date = expected_close
            changed = True

        if changed:
            db.flush()

            action = "updated"
            # Determine what kind of change to log
            if old_stage != stage_name and old_stage and stage_name:
                return {"action": action, "title": title, "change": "stage", "old_stage": old_stage, "new_stage": stage_name}
            elif old_status != status:
                return {"action": action, "title": title, "change": "status", "old_status": old_status, "new_status": status}
            else:
                return {"action": action, "title": title, "change": "fields"}
        else:
            return {"action": "unchanged", "title": title}

    else:
        # Create new ContactDeal
        new_deal = models.ContactDeal(
            contact_id=contact.id,
            user_id=user_id,
            contact_organization_id=contact.contact_organization_id,
            external_deal_id=external_deal_id,
            crm_provider="pipedrive",
            title=title,
            status=status,
            stage_name=stage_name,
            value=value,
            expected_close_date=expected_close,
            currency=currency,
        )
        db.add(new_deal)
        db.flush()
        return {"action": "created", "title": title, "new_stage": stage_name, "deal_id": new_deal.id}


async def sync_contact_pipedrive(
    db: Session,
    user_id: int,
    contact_id: int,
) -> Dict[str, Any]:
    """
    Sync a single contact with Pipedrive.
    1. Find Pipedrive person by email(s)
    2. Link external_person_id
    3. Link Pipedrive org to ContactOrganization
    4. Fetch all deals → upsert ContactDeal rows
    5. Log activities for new/changed deals
    6. Update stats
    7. Set crm_synced_at

    Returns sync result dict.
    """
    # Load contact with emails
    contact = db.query(models.Contact).options(
        selectinload(models.Contact.contact_emails),
    ).filter(
        models.Contact.id == contact_id,
        models.Contact.user_id == user_id,
        models.Contact.deleted_at.is_(None),
    ).first()

    if not contact:
        return {"success": False, "error": "Contact not found"}

    # Get Pipedrive API key
    api_key = await _get_api_key(db, user_id)
    if not api_key:
        return {"success": False, "error": "Pipedrive API key not configured"}

    now = datetime.now(timezone.utc)
    result = {
        "success": True,
        "personFound": False,
        "externalPersonId": None,
        "dealsTotal": 0,
        "dealsCreated": 0,
        "dealsUpdated": 0,
        "activitiesSynced": 0,
        "notesSynced": 0,
        "orgLinked": False,
        "orgName": None,
    }

    # --- Step 1: Find Pipedrive person by email(s) ---
    from pipedrive_service import find_person_by_email

    emails = [ce.email for ce in (contact.contact_emails or [])]
    if not emails:
        emails = [contact.email]

    person = None
    person_id = None
    for email in emails:
        search_result = await find_person_by_email(db, user_id, email)
        if search_result.get("found"):
            person = search_result.get("person", {})
            person_id = search_result.get("person_id")
            break

    if not person or not person_id:
        # Person not found — set crm_synced_at so we don't re-check every 5 min
        contact.crm_synced_at = now
        db.commit()
        result["personFound"] = False
        return result

    result["personFound"] = True
    result["externalPersonId"] = str(person_id)

    # --- Step 2: Link person ---
    contact.external_person_id = str(person_id)
    contact.crm_provider = "pipedrive"

    # Update contact name from Pipedrive (authoritative source for real names)
    pipedrive_name = person.get("name")
    if pipedrive_name and pipedrive_name != contact.name:
        contact.name = pipedrive_name
        contact.avatar_initials = generate_initials(pipedrive_name, contact.email or "")

    # --- Step 3: Link Pipedrive org ---
    pipedrive_org = person.get("organization") or {}
    pipedrive_org_id = pipedrive_org.get("id") if isinstance(pipedrive_org, dict) else None
    pipedrive_org_name = pipedrive_org.get("name") if isinstance(pipedrive_org, dict) else None

    if pipedrive_org_id and contact.contact_organization_id:
        org = db.query(models.ContactOrganization).filter(
            models.ContactOrganization.id == contact.contact_organization_id,
            models.ContactOrganization.user_id == user_id,
        ).first()
        if org:
            org.external_org_id = str(pipedrive_org_id)
            org.crm_provider = "pipedrive"
            if pipedrive_org_name and org.name != pipedrive_org_name:
                org.name = pipedrive_org_name
            result["orgLinked"] = True
            result["orgName"] = org.name

    # --- Step 4: Fetch all deals for person ---
    try:
        pipedrive_deals = await _fetch_person_deals(api_key, person_id)
    except Exception as e:
        logger.error(f"Failed to fetch deals for person {person_id}: {e}")
        contact.crm_synced_at = now
        db.commit()
        result["error"] = f"Failed to fetch deals: {str(e)}"
        return result

    # --- Step 5: Get stage mapping ---
    stage_map = await _get_stage_map(db, user_id)

    # --- Step 6: Upsert deals ---
    for deal_data in pipedrive_deals:
        try:
            upsert_result = _upsert_deal(db, user_id, contact, deal_data, stage_map)
            action = upsert_result.get("action")
            title = upsert_result.get("title", "")

            if action == "created":
                result["dealsCreated"] += 1
                log_activity(
                    db=db,
                    user_id=user_id,
                    contact_id=contact_id,
                    activity_type="deal_stage_change",
                    direction="internal",
                    source_type="crm_sync",
                    source_id=f"pipedrive_deal_{deal_data.get('id')}_created",
                    deal_id=upsert_result.get("deal_id"),
                    summary=f"New deal synced: {title} at {upsert_result.get('new_stage', 'Unknown')}",
                    title=f"New deal: {title}",
                )
            elif action == "updated":
                result["dealsUpdated"] += 1
                change = upsert_result.get("change")
                if change == "stage":
                    log_activity(
                        db=db,
                        user_id=user_id,
                        contact_id=contact_id,
                        activity_type="deal_stage_change",
                        direction="internal",
                        source_type="crm_sync",
                        source_id=f"pipedrive_deal_{deal_data.get('id')}_stage_{upsert_result.get('new_stage')}",
                        summary=f"{title}: {upsert_result.get('old_stage')} → {upsert_result.get('new_stage')}",
                        title=f"Stage change: {title}",
                    )
                elif change == "status":
                    log_activity(
                        db=db,
                        user_id=user_id,
                        contact_id=contact_id,
                        activity_type="deal_status_change",
                        direction="internal",
                        source_type="crm_sync",
                        source_id=f"pipedrive_deal_{deal_data.get('id')}_status_{upsert_result.get('new_status')}",
                        summary=f"{title}: {upsert_result.get('old_status')} → {upsert_result.get('new_status')}",
                        title=f"Deal {upsert_result.get('new_status')}: {title}",
                    )

                    # Fresh Check rule 5 — deal moved to Lost. Emit an org-wide
                    # signal so sibling contacts at the same org see it on
                    # their next pre-send check. Fire-and-forget: any failure
                    # is swallowed so Pipedrive sync itself never breaks.
                    if (upsert_result.get("new_status") or "").lower() == "lost":
                        try:
                            await _emit_deal_lost_org_signal(
                                db=db,
                                user_id=user_id,
                                contact_id=contact_id,
                                deal_external_id=str(deal_data.get("id") or ""),
                                deal_title=title,
                            )
                        except Exception as e:
                            logger.debug(f"[RAG] deal-lost org_signal skipped: {e}")
        except Exception as e:
            logger.error(f"Failed to upsert deal {deal_data.get('id')}: {e}")
            continue

    result["dealsTotal"] = len(pipedrive_deals)

    # --- Step 7: Build deal_id map for activity/note linking ---
    our_deals = db.query(models.ContactDeal).filter(
        models.ContactDeal.contact_id == contact.id,
        models.ContactDeal.crm_provider == "pipedrive",
        models.ContactDeal.deleted_at.is_(None),
    ).all()
    deal_id_map = {d.external_deal_id: d.id for d in our_deals}

    # --- Step 8: Sync Pipedrive activities (calls, meetings, tasks, emails) ---
    try:
        pd_activities = await _fetch_person_activities(api_key, person_id)
        for act_data in pd_activities:
            try:
                was_new = _sync_pipedrive_activity(db, user_id, contact_id, act_data, deal_id_map)
                if was_new:
                    result["activitiesSynced"] += 1
            except Exception as e:
                logger.error(f"Failed to sync activity {act_data.get('id')}: {e}")
                continue
    except Exception as e:
        logger.error(f"Failed to fetch activities for person {person_id}: {e}")

    # --- Step 9: Sync Pipedrive notes ---
    try:
        pd_notes = await _fetch_person_notes(api_key, person_id)
        for note_data in pd_notes:
            try:
                was_new = _sync_pipedrive_note(db, user_id, contact_id, note_data, deal_id_map)
                if was_new:
                    result["notesSynced"] += 1
            except Exception as e:
                logger.error(f"Failed to sync note {note_data.get('id')}: {e}")
                continue
    except Exception as e:
        logger.error(f"Failed to fetch notes for person {person_id}: {e}")

    # --- Step 10: Recompute stats + set synced_at ---
    update_contact_stats(db, contact_id)
    contact.crm_synced_at = now
    db.commit()

    logger.info("Pipedrive sync complete", extra={
        "user_id": user_id, "contact_id": contact_id,
        "person_id": person_id, "deals_total": len(pipedrive_deals),
        "deals_created": result["dealsCreated"], "deals_updated": result["dealsUpdated"],
        "activities_synced": result["activitiesSynced"], "notes_synced": result["notesSynced"],
    })

    return result


def get_contacts_due_for_sync(db: Session, user_id: int, limit: int = 30) -> List[models.Contact]:
    """
    Query contacts that are due for Pipedrive sync based on smart interval logic.
    Priority: never synced > active+overdue > dormant+overdue.
    Returns up to `limit` contacts.
    """
    now = datetime.now(timezone.utc)
    active_cutoff = now - ACTIVE_WINDOW        # 48h ago
    active_interval = now - INTERVAL_ACTIVE     # 15 min ago
    dormant_interval = now - INTERVAL_DORMANT   # 6h ago

    # Base filter: user's non-deleted contacts
    base = and_(
        models.Contact.user_id == user_id,
        models.Contact.deleted_at.is_(None),
    )

    # Priority 1: Never synced (crm_synced_at IS NULL)
    never_synced = db.query(models.Contact).filter(
        base,
        models.Contact.crm_synced_at.is_(None),
    ).order_by(models.Contact.id).limit(limit).all()

    remaining = limit - len(never_synced)
    if remaining <= 0:
        return never_synced

    # Get IDs of contacts with open deals (for "active" classification)
    contacts_with_open_deals = db.query(models.ContactDeal.contact_id).filter(
        models.ContactDeal.user_id == user_id,
        models.ContactDeal.status == "open",
        models.ContactDeal.deleted_at.is_(None),
    ).distinct().subquery()

    # Priority 2: Active contacts (open deals OR recent activity) overdue for sync
    active_overdue = db.query(models.Contact).filter(
        base,
        models.Contact.crm_synced_at.isnot(None),
        models.Contact.crm_synced_at < active_interval,
        or_(
            models.Contact.id.in_(db.query(contacts_with_open_deals)),
            and_(
                models.Contact.last_activity_at.isnot(None),
                models.Contact.last_activity_at > active_cutoff,
            ),
        ),
    ).order_by(models.Contact.crm_synced_at).limit(remaining).all()

    remaining -= len(active_overdue)
    if remaining <= 0:
        return never_synced + active_overdue

    # Priority 3: Dormant contacts overdue for sync
    already_fetched_ids = [c.id for c in never_synced + active_overdue]
    dormant_overdue = db.query(models.Contact).filter(
        base,
        models.Contact.crm_synced_at.isnot(None),
        models.Contact.crm_synced_at < dormant_interval,
        ~models.Contact.id.in_(already_fetched_ids) if already_fetched_ids else True,
    ).order_by(models.Contact.crm_synced_at).limit(remaining).all()

    return never_synced + active_overdue + dormant_overdue


async def sync_all_contacts_pipedrive(
    db: Session,
    user_id: int,
) -> Dict[str, Any]:
    """
    Sync all contacts due for sync for a given user.
    Called by the background worker and the bulk manual endpoint.
    """
    api_key = await _get_api_key(db, user_id)
    if not api_key:
        return {"success": False, "error": "Pipedrive API key not configured"}

    contacts = get_contacts_due_for_sync(db, user_id, limit=30)

    totals = {
        "success": True,
        "contactsSynced": 0,
        "personsFound": 0,
        "dealsCreated": 0,
        "dealsUpdated": 0,
        "activitiesSynced": 0,
        "notesSynced": 0,
        "errors": 0,
    }

    def _accumulate(result):
        totals["contactsSynced"] += 1
        if result.get("personFound"):
            totals["personsFound"] += 1
        totals["dealsCreated"] += result.get("dealsCreated", 0)
        totals["dealsUpdated"] += result.get("dealsUpdated", 0)
        totals["activitiesSynced"] += result.get("activitiesSynced", 0)
        totals["notesSynced"] += result.get("notesSynced", 0)

    for contact in contacts:
        try:
            result = await sync_contact_pipedrive(db, user_id, contact.id)
            _accumulate(result)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                logger.warning("Pipedrive rate limit hit (429), sleeping 30s before resuming")
                await asyncio.sleep(30)
                try:
                    result = await sync_contact_pipedrive(db, user_id, contact.id)
                    _accumulate(result)
                except Exception:
                    totals["errors"] += 1
            else:
                logger.error(f"Pipedrive API error for contact {contact.id}: {e}")
                totals["errors"] += 1
        except Exception as e:
            logger.error(f"Sync failed for contact {contact.id}: {e}")
            totals["errors"] += 1
            continue

        # Rate limit: 100ms between contacts
        await asyncio.sleep(0.1)

    logger.info("Bulk Pipedrive sync complete", extra={
        "user_id": user_id,
        "contacts_synced": totals["contactsSynced"],
        "persons_found": totals["personsFound"],
        "deals_created": totals["dealsCreated"],
    })

    return totals
