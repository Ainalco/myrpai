"""
Contact persons router — all /contacts endpoints.
Serves the frontend ContactPersonsPage with exact JSON shapes.
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, joinedload, selectinload
from sqlalchemy import func
from datetime import datetime, timezone
import logging
import csv
import io

from database import get_db
from auth import get_current_active_user
import models
from contacts_schemas import (
    ContactListItem, ContactListResponse, StatusCounts, ContactStatsResponse,
    ContactDetailResponse, ContactPulseResponse, ContactDealResponse,
    TimelineEventResponse, ThreadResponse, ThreadMessageResponse,
    MeetingResponse, ContactCreateRequest, ContactUpdateRequest,
    ContactStatusRequest, ContactNoteRequest, ContactMergeRequest,
    format_relative_time, format_rate, format_date_long, format_datetime_short,
    format_date_short,
)
from contacts_service import (
    get_or_create_contact, log_activity, update_contact_stats,
    merge_contacts, record_email_sent, generate_initials,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def _build_stats_response(stats: Optional[models.ContactStats]) -> ContactStatsResponse:
    """Build stats response dict from ContactStats model."""
    if not stats:
        return ContactStatsResponse()
    return ContactStatsResponse(
        sent=stats.emails_sent or 0,
        received=stats.emails_received or 0,
        rate=format_rate(stats.reply_rate),
        meetings=stats.meetings_count or 0,
        sequences=stats.active_sequences or 0,
        openDeals=stats.open_deals or 0,
        dealValue=stats.total_deal_value or 0,
    )


def _build_list_item(contact: models.Contact) -> ContactListItem:
    """Build a ContactListItem from a Contact model with eager-loaded relations."""
    org = contact.organization
    email_list = [ce.email for ce in (contact.contact_emails or [])]
    if not email_list:
        email_list = [contact.email]

    return ContactListItem(
        id=contact.id,
        name=contact.name,
        email=contact.email,
        orgId=contact.contact_organization_id,
        orgName=org.name if org else contact.company,
        status=contact.status or "active",
        pipedrive=bool(contact.external_person_id and contact.crm_provider == "pipedrive"),
        lastActivity=format_relative_time(contact.last_activity_at),
        stats=_build_stats_response(contact.stats),
        emails=email_list,
    )


@router.get("/", response_model=ContactListResponse)
async def list_contacts(
    search: Optional[str] = Query(None, description="Search by name, email, or company"),
    status: Optional[str] = Query(None, description="Filter by status: active, paused, do_not_contact, bounced"),
    cursor: Optional[int] = Query(None, description="Cursor for pagination (last contact ID)"),
    limit: int = Query(50, le=200),
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """List contacts with search, status filter, cursor pagination, and status counts."""
    base_filter = [
        models.Contact.user_id == current_user.id,
        models.Contact.deleted_at.is_(None),
    ]

    # --- Status counts (across ALL contacts, unfiltered) ---
    count_rows = db.query(
        models.Contact.status,
        func.count(models.Contact.id),
    ).filter(*base_filter).group_by(models.Contact.status).all()

    counts_map = {row[0]: row[1] for row in count_rows}
    counts = StatusCounts(
        active=counts_map.get("active", 0),
        paused=counts_map.get("paused", 0),
        dnc=counts_map.get("do_not_contact", 0),
        bounced=counts_map.get("bounced", 0),
    )

    # --- Filtered query ---
    query = db.query(models.Contact).options(
        joinedload(models.Contact.organization),
        joinedload(models.Contact.stats),
        selectinload(models.Contact.contact_emails),
    ).filter(*base_filter)

    if search:
        search_filter = f"%{search}%"
        query = query.filter(
            (models.Contact.name.ilike(search_filter))
            | (models.Contact.email.ilike(search_filter))
            | (models.Contact.company.ilike(search_filter))
        )

    if status:
        query = query.filter(models.Contact.status == status)

    # Cursor-based pagination (ordered by id desc for deterministic paging)
    query = query.order_by(models.Contact.id.desc())
    if cursor:
        query = query.filter(models.Contact.id < cursor)

    results = query.limit(limit + 1).all()
    has_more = len(results) > limit
    items = results[:limit]
    next_cursor = items[-1].id if has_more and items else None

    return ContactListResponse(
        items=[_build_list_item(c) for c in items],
        counts=counts,
        nextCursor=next_cursor,
        hasMore=has_more,
    )


# IMPORTANT: /export MUST come before /{contact_id} to avoid route capture
@router.get("/export")
async def export_contacts(
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Export all contacts as CSV."""
    contacts = db.query(models.Contact).options(
        joinedload(models.Contact.organization),
        joinedload(models.Contact.stats),
    ).filter(
        models.Contact.user_id == current_user.id,
        models.Contact.deleted_at.is_(None),
    ).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Name", "Email", "Organization", "Status", "Emails Sent", "Emails Received", "Reply Rate", "Open Deals"])

    for c in contacts:
        s = c.stats
        writer.writerow([
            c.name or "",
            c.email,
            c.organization.name if c.organization else c.company or "",
            c.status or "active",
            s.emails_sent if s else 0,
            s.emails_received if s else 0,
            f"{s.reply_rate:.1f}%" if s and s.reply_rate else "0.0%",
            s.open_deals if s else 0,
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=contacts.csv"},
    )


@router.post("/sync-crm")
async def sync_all_contacts_crm(
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Trigger Pipedrive sync for all contacts due for sync."""
    from pipedrive_sync import sync_all_contacts_pipedrive
    result = await sync_all_contacts_pipedrive(db, current_user.id)
    return result


@router.post("/sync-meetings")
async def backfill_meetings(
    limit: int = Query(50, le=100, description="Max transcripts to process"),
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Backfill MeetingHistory from recent Fireflies transcripts."""
    from fireflies_sync import backfill_meetings_from_fireflies
    result = await backfill_meetings_from_fireflies(db, current_user.id, limit=limit)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Backfill failed"))
    return result


@router.get("/{contact_id}", response_model=ContactDetailResponse)
async def get_contact_detail(
    contact_id: int,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Get full contact detail with all tab data (pulse, deals, timeline, threads, meetings)."""
    contact = db.query(models.Contact).options(
        joinedload(models.Contact.organization),
        joinedload(models.Contact.stats),
        joinedload(models.Contact.pulse),
        selectinload(models.Contact.contact_emails),
        selectinload(models.Contact.deals),
        selectinload(models.Contact.thread_digests),
        selectinload(models.Contact.meetings),
    ).filter(
        models.Contact.id == contact_id,
        models.Contact.user_id == current_user.id,
        models.Contact.deleted_at.is_(None),
    ).first()

    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    # Load activities separately with limit (can be large)
    activities = db.query(models.ContactActivity).filter(
        models.ContactActivity.contact_id == contact_id,
        models.ContactActivity.user_id == current_user.id,
    ).order_by(models.ContactActivity.activity_at.desc().nullslast()).limit(100).all()

    org = contact.organization
    email_list = [ce.email for ce in (contact.contact_emails or [])]
    if not email_list:
        email_list = [contact.email]

    # Build deals with deal title lookup
    deal_map = {}
    deals_response = []
    for deal in (contact.deals or []):
        if deal.deleted_at:
            continue
        deal_map[deal.id] = deal.title
        # Build external CRM URL if deal is from Pipedrive
        external_url = None
        if deal.crm_provider == "pipedrive" and deal.external_deal_id:
            external_url = f"https://app.pipedrive.com/deal/{deal.external_deal_id}"

        deals_response.append(ContactDealResponse(
            id=deal.id,
            title=deal.title,
            status=deal.status or "open",
            stage=deal.stage_name,
            value=deal.value,
            expected=format_date_long(deal.expected_close_date),
            externalUrl=external_url,
        ))

    # Build timeline from activities
    timeline = []
    for act in activities:
        deal_title = deal_map.get(act.deal_id) if act.deal_id else None
        if deal_title and " - " in deal_title:
            deal_title = deal_title.split(" - ", 1)[1]
        timeline.append(TimelineEventResponse(
            id=act.id,
            type=act.activity_type,
            dir=act.direction,
            source=act.source_type,
            subject=act.subject,
            summary=act.summary or act.title,
            at=format_datetime_short(act.activity_at or act.occurred_at),
            deal=deal_title,
        ))

    # Build threads from thread_digests
    threads = []
    for td in (contact.thread_digests or []):
        messages = []
        if td.thread_id:
            eq_items = db.query(models.EmailQueue).filter(
                models.EmailQueue.thread_id == td.thread_id,
                models.EmailQueue.user_id == current_user.id,
                models.EmailQueue.status == "sent",
            ).order_by(models.EmailQueue.sent_at).all()

            user_email = current_user.smtp_username or current_user.email
            for eq in eq_items:
                messages.append(ThreadMessageResponse(
                    id=str(eq.id),
                    sender="you",
                    to=eq.recipient_email,
                    subject=eq.subject,
                    body=eq.body,
                    at=format_datetime_short(eq.sent_at or eq.scheduled_at),
                ))

        threads.append(ThreadResponse(
            id=td.thread_id or str(td.id),
            summary=td.summary,
            sentiment=td.sentiment,
            status=td.thread_status,
            msgs=td.message_count or 0,
            lastAt=format_date_short(td.last_message_at),
            messages=messages,
        ))

    # Build meetings
    meetings_response = []
    for m in (contact.meetings or []):
        meetings_response.append(MeetingResponse(
            id=m.id,
            date=format_date_long(m.meeting_date),
            source=m.source,
            summary=m.summary,
            keyPoints=m.key_points or [],
            objections=m.objections or [],
            signals=m.buying_signals or [],
            stage=m.deal_stage_at_time,
        ))

    # Build pulse (always return an object — frontend does c.pulse.sentiment without null checks)
    if contact.pulse:
        p = contact.pulse
        pulse_response = ContactPulseResponse(
            summary=p.summary,
            sentiment=p.sentiment,
            engagement=p.engagement_level,
            intent=p.intent,
            action=p.recommended_action,
            topics=p.key_topics or [],
            objections=p.key_objections or [],
            lastMeeting=format_date_long(p.last_meeting_date),
        )
    else:
        pulse_response = ContactPulseResponse(
            summary="No intelligence data yet. Pulse generates after interactions.",
            sentiment="unknown",
            engagement="low",
            intent="evaluating",
            action="send_followup",
        )

    return ContactDetailResponse(
        id=contact.id,
        name=contact.name,
        email=contact.email,
        orgId=contact.contact_organization_id,
        orgName=org.name if org else contact.company,
        status=contact.status or "active",
        pipedrive=bool(contact.external_person_id and contact.crm_provider == "pipedrive"),
        lastActivity=format_relative_time(contact.last_activity_at),
        emails=email_list,
        stats=_build_stats_response(contact.stats),
        pulse=pulse_response,
        deals=deals_response,
        timeline=timeline,
        threads=threads,
        meetings=meetings_response,
    )


# --- Write Endpoints (P1) ---

@router.post("/", response_model=ContactDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_contact(
    data: ContactCreateRequest,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Create a new contact (calls get_or_create_contact internally)."""
    contact = get_or_create_contact(
        db=db,
        user_id=current_user.id,
        email=data.email,
        name=data.name,
        organization_name=data.organization_name,
    )
    db.commit()
    return await get_contact_detail(contact.id, current_user, db)


@router.put("/{contact_id}", response_model=ContactDetailResponse)
async def update_contact(
    contact_id: int,
    data: ContactUpdateRequest,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Update contact fields."""
    contact = db.query(models.Contact).filter(
        models.Contact.id == contact_id,
        models.Contact.user_id == current_user.id,
        models.Contact.deleted_at.is_(None),
    ).first()

    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    if data.name is not None:
        contact.name = data.name
        contact.avatar_initials = generate_initials(data.name, contact.email)
    if data.email is not None:
        contact.email = data.email
        contact.primary_email = data.email
    if data.title is not None:
        contact.title = data.title
    if data.company is not None:
        contact.company = data.company
    if data.contact_organization_id is not None:
        contact.contact_organization_id = data.contact_organization_id

    db.commit()
    return await get_contact_detail(contact_id, current_user, db)


@router.put("/{contact_id}/status")
async def update_contact_status(
    contact_id: int,
    data: ContactStatusRequest,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Set contact status (active/paused/do_not_contact/bounced) with DNC org propagation."""
    if data.status not in ("active", "paused", "do_not_contact", "bounced"):
        raise HTTPException(status_code=400, detail="Invalid status")

    contact = db.query(models.Contact).filter(
        models.Contact.id == contact_id,
        models.Contact.user_id == current_user.id,
        models.Contact.deleted_at.is_(None),
    ).first()

    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    contact.status = data.status

    if data.status == "do_not_contact" and contact.contact_organization_id:
        org = db.query(models.ContactOrganization).filter(
            models.ContactOrganization.id == contact.contact_organization_id,
            models.ContactOrganization.user_id == current_user.id,
        ).first()
        if org and org.do_not_contact_propagation:
            db.query(models.Contact).filter(
                models.Contact.contact_organization_id == org.id,
                models.Contact.user_id == current_user.id,
                models.Contact.deleted_at.is_(None),
                models.Contact.id != contact_id,
            ).update({"status": "do_not_contact"})

    db.commit()
    return {"success": True, "status": data.status}


@router.delete("/{contact_id}")
async def delete_contact(
    contact_id: int,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Soft-delete a contact."""
    contact = db.query(models.Contact).filter(
        models.Contact.id == contact_id,
        models.Contact.user_id == current_user.id,
        models.Contact.deleted_at.is_(None),
    ).first()

    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    contact.deleted_at = datetime.now(timezone.utc)
    db.commit()
    return {"success": True}


@router.post("/{contact_id}/note")
async def add_contact_note(
    contact_id: int,
    data: ContactNoteRequest,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Add a note to the contact timeline."""
    contact = db.query(models.Contact).filter(
        models.Contact.id == contact_id,
        models.Contact.user_id == current_user.id,
        models.Contact.deleted_at.is_(None),
    ).first()

    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    activity = log_activity(
        db=db,
        user_id=current_user.id,
        contact_id=contact_id,
        activity_type="note",
        direction="internal",
        summary=data.content,
        title="Note added",
    )
    db.commit()
    return {"success": True, "activityId": activity.id}


@router.post("/{contact_id}/merge")
async def merge_contact(
    contact_id: int,
    data: ContactMergeRequest,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Merge another contact into this one."""
    try:
        kept = merge_contacts(
            db=db,
            user_id=current_user.id,
            keep_id=contact_id,
            merge_id=data.merge_id,
        )
        db.commit()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"success": True, "keptId": kept.id}


@router.post("/{contact_id}/refresh-pulse")
async def refresh_contact_pulse(
    contact_id: int,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Regenerate the Contact Pulse AI intelligence summary."""
    from contacts_service import generate_contact_pulse

    contact = db.query(models.Contact).filter(
        models.Contact.id == contact_id,
        models.Contact.user_id == current_user.id,
        models.Contact.deleted_at.is_(None),
    ).first()
    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    pulse = await generate_contact_pulse(db, current_user.id, contact_id)
    db.commit()
    return {"success": True, "generatedAt": pulse.generated_at.isoformat() if pulse.generated_at else None}


@router.post("/{contact_id}/sync-crm")
async def sync_contact_crm(
    contact_id: int,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Trigger Pipedrive sync for a single contact."""
    from pipedrive_sync import sync_contact_pipedrive
    result = await sync_contact_pipedrive(db, current_user.id, contact_id)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Sync failed"))
    return result
