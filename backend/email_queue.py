from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, func
from pydantic import BaseModel
from datetime import datetime, date, timedelta
import logging

from database import get_db
from auth import get_current_active_user
import models

logger = logging.getLogger(__name__)

router = APIRouter()


# Pydantic models
class ContactInfo(BaseModel):
    id: int
    email: str
    name: Optional[str] = None
    title: Optional[str] = None
    company: Optional[str] = None
    avatar_initials: Optional[str] = None

    class Config:
        from_attributes = True


class ContactActivityInfo(BaseModel):
    id: int
    activity_type: str
    title: Optional[str] = None
    occurred_at: datetime
    is_new: bool

    class Config:
        from_attributes = True


class EmailQueueItem(BaseModel):
    id: int
    user_id: int
    workflow_id: Optional[int] = None
    execution_id: Optional[int] = None
    component_id: Optional[int] = None
    recipient_email: str
    recipient_name: Optional[str] = None
    subject: str
    body: str
    cc: Optional[list] = None
    bcc: Optional[list] = None
    scheduled_at: datetime
    sent_at: Optional[datetime] = None
    status: str
    error_message: Optional[str] = None
    retry_count: int
    max_retries: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    # New fields
    contact_id: Optional[int] = None
    original_subject: Optional[str] = None
    original_body: Optional[str] = None
    edit_source: Optional[str] = None
    approval_status: Optional[str] = "pending"
    approved_at: Optional[datetime] = None
    sequence_config_id: Optional[int] = None
    sequence_position: Optional[int] = None
    sequence_total: Optional[int] = None
    # AI reasoning
    timing_reason: Optional[str] = None
    generation_reason: Optional[str] = None
    org_warning: Optional[str] = None
    thread_id: Optional[str] = None
    message_id_header: Optional[str] = None
    thread_parent_component_id: Optional[int] = None
    thread_parent_component_name: Optional[str] = None
    thread_parent_queue_id: Optional[int] = None
    thread_fallback_reason: Optional[str] = None
    sender_provider: Optional[str] = None
    sender_account_email: Optional[str] = None
    # Fresh Check audit trail (#178) — populated by _rag_presend_decision and
    # dispatch_fresh_check_action. Rendered on the queue-review page so
    # admins can see why an email was cancelled/skipped/rescheduled, and
    # acted on via the override endpoint below.
    fresh_check_action: Optional[str] = None
    fresh_check_rule_triggered: Optional[str] = None
    fresh_check_reason: Optional[str] = None
    fresh_check_resume_date: Optional[date] = None
    # Nested data
    contact: Optional[ContactInfo] = None
    activities: Optional[List[ContactActivityInfo]] = None
    sequence_name: Optional[str] = None

    class Config:
        from_attributes = True


class EmailQueueStats(BaseModel):
    total: int
    pending: int
    approved: int
    sent: int
    sent_today: int
    failed: int
    cancelled: int
    skipped: int


class EmailQueueUpdate(BaseModel):
    subject: Optional[str] = None
    body: Optional[str] = None
    edit_source: Optional[str] = None  # 'ai' or 'manual'


class AIEditRequest(BaseModel):
    prompt: str


class AIEditResponse(BaseModel):
    id: int
    modified_subject: str
    modified_body: str
    changes_summary: str


@router.get("/", response_model=List[EmailQueueItem])
async def list_emails(
    status: Optional[str] = Query(None, description="Filter by status: pending, sent, failed, cancelled"),
    approval_status: Optional[str] = Query(None, description="Filter by approval_status: pending, approved, skipped"),
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0),
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get all queued emails for the current user with contact and activity data"""
    query = db.query(models.EmailQueue).options(
        joinedload(models.EmailQueue.contact),
        joinedload(models.EmailQueue.sequence_config),
        joinedload(models.EmailQueue.thread_parent_component),
    ).filter(
        models.EmailQueue.user_id == current_user.id
    )

    if status:
        query = query.filter(models.EmailQueue.status == status)

    if approval_status:
        query = query.filter(models.EmailQueue.approval_status == approval_status)

    # Order by scheduled_at descending (most recent first)
    query = query.order_by(models.EmailQueue.scheduled_at.desc())

    # Apply pagination
    emails = query.offset(offset).limit(limit).all()

    # Enrich with sequence name and activities
    result = []
    for email in emails:
        email_dict = {
            "id": email.id,
            "user_id": email.user_id,
            "workflow_id": email.workflow_id,
            "execution_id": email.execution_id,
            "component_id": email.component_id,
            "recipient_email": email.recipient_email,
            "recipient_name": email.recipient_name,
            "subject": email.subject,
            "body": email.body,
            "cc": email.cc,
            "bcc": email.bcc,
            "scheduled_at": email.scheduled_at,
            "sent_at": email.sent_at,
            "status": email.status,
            "error_message": email.error_message,
            "retry_count": email.retry_count,
            "max_retries": email.max_retries,
            "created_at": email.created_at,
            "updated_at": email.updated_at,
            "contact_id": email.contact_id,
            "original_subject": email.original_subject,
            "original_body": email.original_body,
            "edit_source": email.edit_source,
            "approval_status": email.approval_status,
            "approved_at": email.approved_at,
            "sequence_config_id": email.sequence_config_id,
            "sequence_position": email.sequence_position,
            "sequence_total": email.sequence_total,
            # AI reasoning — rendered in the queue-review hovercards.
            "timing_reason": email.timing_reason,
            "generation_reason": email.generation_reason,
            "org_warning": email.org_warning,
            "thread_id": email.thread_id,
            "message_id_header": email.message_id_header,
            "thread_parent_component_id": email.thread_parent_component_id,
            "thread_parent_component_name": email.thread_parent_component.name if email.thread_parent_component else None,
            "thread_parent_queue_id": email.thread_parent_queue_id,
            "thread_fallback_reason": email.thread_fallback_reason,
            "sender_provider": email.sender_provider,
            "sender_account_email": email.sender_account_email,
            # Fresh Check audit (#178) — required by the queue-review UI
            # so rows stopped by the pre-send gate render with their
            # action/rule/reason/resume_date and the override button.
            "fresh_check_action": email.fresh_check_action,
            "fresh_check_rule_triggered": email.fresh_check_rule_triggered,
            "fresh_check_reason": email.fresh_check_reason,
            "fresh_check_resume_date": email.fresh_check_resume_date,
            "contact": email.contact,
            "sequence_name": email.sequence_config.name if email.sequence_config else None,
            "activities": None
        }

        # Load activities if contact exists
        if email.contact_id:
            activities = db.query(models.ContactActivity).filter(
                models.ContactActivity.contact_id == email.contact_id
            ).order_by(
                models.ContactActivity.occurred_at.desc()
            ).limit(5).all()
            email_dict["activities"] = activities

        result.append(email_dict)

    return result


@router.get("/stats", response_model=EmailQueueStats)
async def get_email_stats(
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get enhanced email queue statistics"""
    base_query = db.query(models.EmailQueue).filter(
        models.EmailQueue.user_id == current_user.id
    )

    total = base_query.count()

    # Pending approval (not yet approved, not sent)
    pending = base_query.filter(
        models.EmailQueue.approval_status == "pending",
        models.EmailQueue.status == "pending"
    ).count()

    # Approved but not yet sent
    approved = base_query.filter(
        models.EmailQueue.approval_status == "approved",
        models.EmailQueue.status == "pending"
    ).count()

    # Sent total
    sent = base_query.filter(
        models.EmailQueue.status == "sent"
    ).count()

    # Sent today
    today_start = datetime.combine(date.today(), datetime.min.time())
    sent_today = base_query.filter(
        models.EmailQueue.status == "sent",
        models.EmailQueue.sent_at >= today_start
    ).count()

    # Failed
    failed = base_query.filter(
        models.EmailQueue.status == "failed"
    ).count()

    # Cancelled
    cancelled = base_query.filter(
        models.EmailQueue.status == "cancelled"
    ).count()

    # Skipped
    skipped = base_query.filter(
        models.EmailQueue.approval_status == "skipped"
    ).count()

    return EmailQueueStats(
        total=total,
        pending=pending,
        approved=approved,
        sent=sent,
        sent_today=sent_today,
        failed=failed,
        cancelled=cancelled,
        skipped=skipped
    )


@router.get("/{email_id}", response_model=EmailQueueItem)
async def get_email(
    email_id: int,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get a specific email from the queue"""
    email = db.query(models.EmailQueue).filter(
        models.EmailQueue.id == email_id,
        models.EmailQueue.user_id == current_user.id
    ).first()

    if not email:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Email not found"
        )

    return email


@router.delete("/{email_id}")
async def cancel_email(
    email_id: int,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Cancel a scheduled email"""
    email = db.query(models.EmailQueue).filter(
        models.EmailQueue.id == email_id,
        models.EmailQueue.user_id == current_user.id
    ).first()

    if not email:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Email not found"
        )

    if email.status == "sent":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot cancel an email that has already been sent"
        )

    email.status = "cancelled"
    db.commit()

    return {"success": True, "message": f"Email {email_id} cancelled"}


@router.post("/{email_id}/retry")
async def retry_email(
    email_id: int,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Retry sending a failed email"""
    email = db.query(models.EmailQueue).filter(
        models.EmailQueue.id == email_id,
        models.EmailQueue.user_id == current_user.id
    ).first()

    if not email:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Email not found"
        )

    if email.status != "failed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only retry failed emails"
        )

    # Reset to pending status for retry
    email.status = "pending"
    email.error_message = None
    db.commit()

    return {"success": True, "message": f"Email {email_id} queued for retry"}


@router.post("/process-queue")
async def process_queue(
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Manually trigger email queue processing for the current user.
    This processes all pending emails that are due to be sent.
    """
    from email_service import process_email_queue

    try:
        # Process the queue
        result = await process_email_queue(db)

        if result.get("success"):
            stats = result.get("stats", {})
            return {
                "success": True,
                "message": "Email queue processed successfully",
                "stats": stats
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to process queue: {result.get('error')}"
            )

    except Exception as e:
        logger.error(f"Error processing email queue: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing email queue: {str(e)}"
        )


@router.put("/{email_id}", response_model=EmailQueueItem)
async def update_email(
    email_id: int,
    update_data: EmailQueueUpdate,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Update email subject and/or body (manual edit)"""
    email = db.query(models.EmailQueue).filter(
        models.EmailQueue.id == email_id,
        models.EmailQueue.user_id == current_user.id
    ).first()

    if not email:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Email not found"
        )

    if email.status == "sent":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot edit an email that has already been sent"
        )

    # Store original if not already saved
    if email.original_subject is None:
        email.original_subject = email.subject
    if email.original_body is None:
        email.original_body = email.body

    # Apply updates
    if update_data.subject is not None:
        email.subject = update_data.subject
    if update_data.body is not None:
        email.body = update_data.body

    email.edit_source = update_data.edit_source or "manual"
    db.commit()
    db.refresh(email)

    logger.info(f"Email {email_id} edited ({email.edit_source}) by user {current_user.id}")
    return email


@router.post("/{email_id}/ai-edit", response_model=AIEditResponse)
async def ai_edit_email(
    email_id: int,
    request: AIEditRequest,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Use AI to edit email content based on a prompt"""
    email = db.query(models.EmailQueue).options(
        joinedload(models.EmailQueue.contact)
    ).filter(
        models.EmailQueue.id == email_id,
        models.EmailQueue.user_id == current_user.id
    ).first()

    if not email:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Email not found"
        )

    if email.status == "sent":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot edit an email that has already been sent"
        )

    # Get contact context for AI
    contact_context = None
    if email.contact:
        activities = db.query(models.ContactActivity).filter(
            models.ContactActivity.contact_id == email.contact_id
        ).order_by(
            models.ContactActivity.occurred_at.desc()
        ).limit(5).all()

        contact_context = {
            "name": email.contact.name,
            "company": email.contact.company,
            "recent_activities": [
                {"type": a.activity_type, "title": a.title, "date": a.occurred_at.isoformat()}
                for a in activities
            ]
        }

    # Call AI service
    try:
        from ai_service import ai_edit_email_content, set_usage_context, flush_usage_log
        set_usage_context(user_id=current_user.id, source="email_edit")
        result = await ai_edit_email_content(
            original_subject=email.subject,
            original_body=email.body,
            edit_prompt=request.prompt,
            contact_context=contact_context,
            has_signature=bool(current_user.email_signature_enabled and current_user.email_signature),
        )
        flush_usage_log(db)
        db.flush()
    except Exception as e:
        logger.error(f"AI edit failed for email {email_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"AI edit failed: {str(e)}"
        )

    logger.info(f"Email {email_id} AI edit preview generated for user {current_user.id}")

    return AIEditResponse(
        id=email_id,
        modified_subject=result["modified_subject"],
        modified_body=result["modified_body"],
        changes_summary=result["changes_summary"]
    )


@router.post("/{email_id}/revert", response_model=EmailQueueItem)
async def revert_email(
    email_id: int,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Revert email to original content"""
    email = db.query(models.EmailQueue).filter(
        models.EmailQueue.id == email_id,
        models.EmailQueue.user_id == current_user.id
    ).first()

    if not email:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Email not found"
        )

    if email.status == "sent":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot revert an email that has already been sent"
        )

    if email.original_subject is None and email.original_body is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No original content to revert to"
        )

    # Revert to original
    if email.original_subject is not None:
        email.subject = email.original_subject
    if email.original_body is not None:
        email.body = email.original_body

    # Clear edit tracking
    email.original_subject = None
    email.original_body = None
    email.edit_source = None
    email.ai_edit_prompt = None
    db.commit()
    db.refresh(email)

    logger.info(f"Email {email_id} reverted by user {current_user.id}")
    return email


@router.post("/{email_id}/approve")
async def approve_email(
    email_id: int,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Approve an email for sending"""
    email = db.query(models.EmailQueue).filter(
        models.EmailQueue.id == email_id,
        models.EmailQueue.user_id == current_user.id
    ).first()

    if not email:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Email not found"
        )

    if email.status == "sent":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email has already been sent"
        )

    if email.approval_status == "approved":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email is already approved"
        )

    email.approval_status = "approved"
    email.approved_at = datetime.utcnow()
    db.commit()

    logger.info(f"Email {email_id} approved by user {current_user.id}")
    return {"success": True, "message": f"Email {email_id} approved"}


@router.post("/{email_id}/skip")
async def skip_email(
    email_id: int,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Skip an email (don't send it)"""
    email = db.query(models.EmailQueue).filter(
        models.EmailQueue.id == email_id,
        models.EmailQueue.user_id == current_user.id
    ).first()

    if not email:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Email not found"
        )

    if email.status == "sent":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email has already been sent"
        )

    email.approval_status = "skipped"
    email.status = "cancelled"  # Also mark as cancelled so it won't be sent
    db.commit()

    logger.info(f"Email {email_id} skipped by user {current_user.id}")
    return {"success": True, "message": f"Email {email_id} skipped"}


@router.post("/{email_id}/unskip")
async def unskip_email(
    email_id: int,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Move a skipped email back to pending approval"""
    email = db.query(models.EmailQueue).filter(
        models.EmailQueue.id == email_id,
        models.EmailQueue.user_id == current_user.id
    ).first()

    if not email:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Email not found"
        )

    if email.approval_status != "skipped":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only skipped emails can be moved back to pending"
        )

    email.approval_status = "pending"
    email.status = "pending"
    db.commit()

    logger.info(f"Email {email_id} unskipped (moved to pending) by user {current_user.id}")
    return {"success": True, "message": f"Email {email_id} moved back to pending"}


@router.post("/{email_id}/unapprove")
async def unapprove_email(
    email_id: int,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Move an approved email back to pending (unapprove)"""
    email = db.query(models.EmailQueue).filter(
        models.EmailQueue.id == email_id,
        models.EmailQueue.user_id == current_user.id
    ).first()

    if not email:
        raise HTTPException(status_code=404, detail="Email not found")

    if email.approval_status != "approved" or email.status != "pending":
        raise HTTPException(status_code=400, detail="Can only unapprove emails that are approved and not yet sent")

    email.approval_status = "pending"
    email.approved_at = None
    db.commit()

    return {"success": True, "message": "Email moved back to pending"}


@router.post("/{email_id}/override-fresh-check")
async def override_fresh_check(
    email_id: int,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Admin override for a Fresh Check decision (#178 T5).

    Clears the fresh_check_* audit fields and moves the email back to
    `status='pending'` with `scheduled_at=now()` so the worker picks it
    up on the next cycle. Used by the queue-review UI when an admin
    disagrees with Scurry's STOP/reschedule decision and wants to force
    a send.

    Refuses to override:
      - emails that have already been sent (nothing to override)
      - emails that were cancelled by the DNC rule (rule 8 is locked-on
        by design; overriding it would defeat the safety net — admins
        must clear the contact's dnc_status DB flag first)
    """
    email = db.query(models.EmailQueue).filter(
        models.EmailQueue.id == email_id,
        models.EmailQueue.user_id == current_user.id,
    ).first()
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")

    if email.status == "sent":
        raise HTTPException(
            status_code=400, detail="Email has already been sent",
        )

    if not email.fresh_check_action:
        raise HTTPException(
            status_code=400,
            detail="No Fresh Check decision to override on this email",
        )

    if email.fresh_check_rule_triggered == "dnc":
        # DNC is the one rule an admin cannot click past. Clearing the
        # underlying dnc_status flag is the intentional path; surfacing
        # that requirement prevents "oops, I clicked override" regrets.
        raise HTTPException(
            status_code=400,
            detail=(
                "Cannot override a DNC stop. Clear the contact or "
                "organization DNC flag first, then re-queue."
            ),
        )

    prior_action = email.fresh_check_action
    email.fresh_check_action = None
    email.fresh_check_rule_triggered = None
    email.fresh_check_reason = None
    email.fresh_check_resume_date = None
    email.error_message = None
    email.status = "pending"
    email.scheduled_at = datetime.utcnow()
    email.rag_defer_count = 0
    db.commit()

    logger.info(
        "Fresh Check override on email %s by user %s — was %s",
        email_id, current_user.id, prior_action,
    )
    return {
        "success": True,
        "message": f"Fresh Check {prior_action} overridden; email requeued",
    }


@router.post("/approve-all")
async def approve_all_emails(
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Approve all pending emails"""
    # Get count first
    pending_count = db.query(models.EmailQueue).filter(
        models.EmailQueue.user_id == current_user.id,
        models.EmailQueue.approval_status == "pending",
        models.EmailQueue.status == "pending"
    ).count()

    if pending_count == 0:
        return {"success": True, "approved_count": 0, "message": "No pending emails to approve"}

    # Bulk update
    db.query(models.EmailQueue).filter(
        models.EmailQueue.user_id == current_user.id,
        models.EmailQueue.approval_status == "pending",
        models.EmailQueue.status == "pending"
    ).update({
        "approval_status": "approved",
        "approved_at": datetime.utcnow()
    })

    db.commit()

    logger.info(f"User {current_user.id} approved all {pending_count} pending emails")
    return {
        "success": True,
        "approved_count": pending_count,
        "message": f"Approved {pending_count} emails"
    }
