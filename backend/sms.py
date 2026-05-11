from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

import models
from auth import get_current_active_user
from database import get_db
from sms_service import SMSService

router = APIRouter()


class SMSSendRequest(BaseModel):
    config: dict
    input_data: dict
    workflow_id: Optional[int] = None
    execution_id: Optional[int] = None
    component_id: Optional[int] = None


class SMSUpdateRequest(BaseModel):
    body: str


@router.post("/send")
async def send_sms_component(
    payload: SMSSendRequest,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    service = SMSService(db, current_user)
    return await service.execute_sms_async(
        config=payload.config,
        input_data=payload.input_data,
        workflow_id=payload.workflow_id,
        execution_id=payload.execution_id,
        component_id=payload.component_id,
    )


@router.get("/queue")
async def list_sms_queue(
    status: Optional[str] = Query(None),
    approval_status: Optional[str] = Query(None),
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0),
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    query = db.query(models.EmailQueue).filter(
        models.EmailQueue.user_id == current_user.id,
        models.EmailQueue.channel == "sms",
    )

    if status:
        query = query.filter(models.EmailQueue.status == status)

    if approval_status:
        query = query.filter(models.EmailQueue.approval_status == approval_status)

    return query.order_by(models.EmailQueue.scheduled_at.desc()).offset(offset).limit(limit).all()


@router.post("/queue/{queue_id}/approve")
async def approve_sms(
    queue_id: int,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    item = db.query(models.EmailQueue).filter(
        models.EmailQueue.id == queue_id,
        models.EmailQueue.user_id == current_user.id,
        models.EmailQueue.channel == "sms",
    ).first()

    if not item:
        raise HTTPException(status_code=404, detail="SMS queue item not found")

    if item.status == "sent":
        raise HTTPException(status_code=400, detail="SMS has already been sent")

    if item.status in {"missing_phone", "needs_edit"}:
        raise HTTPException(status_code=400, detail=f"Cannot approve SMS with status {item.status}")

    item.approval_status = "approved"
    item.approved_at = datetime.utcnow()
    db.commit()

    return {"success": True, "message": "SMS approved"}


@router.post("/queue/{queue_id}/edit")
async def edit_sms(
    queue_id: int,
    payload: SMSUpdateRequest,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    item = db.query(models.EmailQueue).filter(
        models.EmailQueue.id == queue_id,
        models.EmailQueue.user_id == current_user.id,
        models.EmailQueue.channel == "sms",
    ).first()

    if not item:
        raise HTTPException(status_code=404, detail="SMS queue item not found")

    if item.status == "sent":
        raise HTTPException(status_code=400, detail="Cannot edit sent SMS")

    body = payload.body.strip()
    item.body = body
    item.character_count = len(body)
    item.sms_segments = max(1, (len(body) + 159) // 160)
    item.edit_source = "manual"

    if item.character_count <= 480:
        item.status = "pending"
        item.delivery_status = "queued"
        item.error_message = None

    db.commit()
    db.refresh(item)

    return item


@router.post("/queue/{queue_id}/skip")
async def skip_sms(
    queue_id: int,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    item = db.query(models.EmailQueue).filter(
        models.EmailQueue.id == queue_id,
        models.EmailQueue.user_id == current_user.id,
        models.EmailQueue.channel == "sms",
    ).first()

    if not item:
        raise HTTPException(status_code=404, detail="SMS queue item not found")

    item.approval_status = "skipped"
    item.status = "cancelled"
    db.commit()

    return {"success": True, "message": "SMS skipped"}


@router.delete("/queue/{queue_id}")
async def delete_sms(
    queue_id: int,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    item = db.query(models.EmailQueue).filter(
        models.EmailQueue.id == queue_id,
        models.EmailQueue.user_id == current_user.id,
        models.EmailQueue.channel == "sms",
    ).first()

    if not item:
        raise HTTPException(status_code=404, detail="SMS queue item not found")

    if item.status == "sent":
        raise HTTPException(status_code=400, detail="Cannot delete sent SMS")

    db.delete(item)
    db.commit()

    return {"success": True, "message": "SMS deleted"}


@router.post("/webhook/status")
async def twilio_status_callback(
    request: Request,
    db: Session = Depends(get_db),
):
    form = await request.form()
    message_sid = form.get("MessageSid")
    message_status = form.get("MessageStatus")

    if not message_sid:
        return {"success": False, "message": "Missing MessageSid"}

    item = db.query(models.EmailQueue).filter(
        models.EmailQueue.twilio_message_sid == message_sid,
        models.EmailQueue.channel == "sms",
    ).first()

    if not item:
        return {"success": False, "message": "SMS not found"}

    item.delivery_status = message_status

    if message_status == "delivered":
        item.status = "sent"
    elif message_status in {"failed", "undelivered"}:
        item.status = "failed"
        item.error_message = f"Twilio delivery status: {message_status}"

    db.commit()

    return {"success": True}