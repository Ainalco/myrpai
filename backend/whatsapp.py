import os
from datetime import datetime
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

import models
from auth import get_current_active_user
from database import get_db
from whatsapp_service import WhatsAppService


router = APIRouter()


class WhatsAppSendRequest(BaseModel):
    config: dict
    input_data: dict
    workflow_id: Optional[int] = None
    execution_id: Optional[int] = None
    component_id: Optional[int] = None


class WhatsAppUpdateRequest(BaseModel):
    body: str


class WhatsAppAIEditRequest(BaseModel):
    prompt: str


@router.post("/send")
async def send_whatsapp_component(
    payload: WhatsAppSendRequest,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    service = WhatsAppService(db, current_user)

    return await service.execute_whatsapp_async(
        config=payload.config,
        input_data=payload.input_data,
        workflow_id=payload.workflow_id,
        execution_id=payload.execution_id,
        component_id=payload.component_id,
    )


@router.get("/queue")
async def list_whatsapp_queue(
    status: Optional[str] = Query(None),
    approval_status: Optional[str] = Query(None),
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0),
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    query = db.query(models.EmailQueue).filter(
        models.EmailQueue.user_id == current_user.id,
        models.EmailQueue.channel == "whatsapp",
    )

    if status:
        query = query.filter(models.EmailQueue.status == status)

    if approval_status:
        query = query.filter(models.EmailQueue.approval_status == approval_status)

    return (
        query.order_by(models.EmailQueue.scheduled_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


@router.post("/queue/{queue_id}/approve")
async def approve_whatsapp(
    queue_id: int,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    item = db.query(models.EmailQueue).filter(
        models.EmailQueue.id == queue_id,
        models.EmailQueue.user_id == current_user.id,
        models.EmailQueue.channel == "whatsapp",
    ).first()

    if not item:
        raise HTTPException(status_code=404, detail="WhatsApp queue item not found")

    if item.status == "sent":
        raise HTTPException(status_code=400, detail="WhatsApp message has already been sent")

    if item.status in {"missing_phone", "needs_edit"}:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot approve WhatsApp message with status {item.status}",
        )

    item.approval_status = "approved"
    item.approved_at = datetime.utcnow()
    db.commit()

    return {"success": True, "message": "WhatsApp message approved"}


@router.post("/queue/{queue_id}/edit")
async def edit_whatsapp(
    queue_id: int,
    payload: WhatsAppUpdateRequest,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    item = db.query(models.EmailQueue).filter(
        models.EmailQueue.id == queue_id,
        models.EmailQueue.user_id == current_user.id,
        models.EmailQueue.channel == "whatsapp",
    ).first()

    if not item:
        raise HTTPException(status_code=404, detail="WhatsApp queue item not found")

    if item.status == "sent":
        raise HTTPException(status_code=400, detail="Cannot edit sent WhatsApp message")

    body = payload.body.strip()

    if not body:
        raise HTTPException(status_code=400, detail="Message body cannot be empty")

    item.body = body
    item.character_count = len(body)
    item.edit_source = "manual"

    if item.character_count <= 4096:
        item.status = "pending"
        item.delivery_status = "queued"
        item.error_message = None
    else:
        item.status = "needs_edit"
        item.delivery_status = "over_character_limit"
        item.error_message = "WhatsApp message exceeds 4096 characters"

    db.commit()
    db.refresh(item)

    return item


@router.post("/queue/{queue_id}/ai-edit")
async def ai_edit_whatsapp(
    queue_id: int,
    payload: WhatsAppAIEditRequest,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    item = db.query(models.EmailQueue).filter(
        models.EmailQueue.id == queue_id,
        models.EmailQueue.user_id == current_user.id,
        models.EmailQueue.channel == "whatsapp",
    ).first()

    if not item:
        raise HTTPException(status_code=404, detail="WhatsApp queue item not found")

    if item.status == "sent":
        raise HTTPException(status_code=400, detail="Cannot AI-edit sent WhatsApp message")

    try:
        from ai_service import generate_whatsapp_message, set_usage_context, flush_usage_log

        set_usage_context(
            user_id=current_user.id,
            source="whatsapp_edit",
            execution_id=item.execution_id,
            component_id=item.component_id,
        )

        edited_body = await generate_whatsapp_message(
            prompt=(
                "Edit this WhatsApp message based on the user's instruction.\n\n"
                f"User instruction:\n{payload.prompt}\n\n"
                f"Current WhatsApp message:\n{item.body}\n\n"
                "Return only the revised WhatsApp message body."
            ),
            input_data={
                "current_body": item.body,
                "edit_instruction": payload.prompt,
                "recipient_phone": item.recipient_phone,
                "recipient_name": item.recipient_name,
            },
            max_chars=4096,
            workflow_id=item.workflow_id,
            db=db,
        )

        flush_usage_log(db)

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"AI edit failed: {str(exc)}",
        )

    edited_body = edited_body.strip()

    return {
        "id": item.id,
        "modified_body": edited_body,
        "character_count": len(edited_body),
        "changes_summary": "WhatsApp message revised with AI",
    }


@router.post("/queue/{queue_id}/skip")
async def skip_whatsapp(
    queue_id: int,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    item = db.query(models.EmailQueue).filter(
        models.EmailQueue.id == queue_id,
        models.EmailQueue.user_id == current_user.id,
        models.EmailQueue.channel == "whatsapp",
    ).first()

    if not item:
        raise HTTPException(status_code=404, detail="WhatsApp queue item not found")

    if item.status == "sent":
        raise HTTPException(status_code=400, detail="Cannot skip sent WhatsApp message")

    item.approval_status = "skipped"
    item.status = "cancelled"
    db.commit()

    return {"success": True, "message": "WhatsApp message skipped"}



@router.delete("/queue/{queue_id}")
async def delete_whatsapp(
    queue_id: int,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    item = db.query(models.EmailQueue).filter(
        models.EmailQueue.id == queue_id,
        models.EmailQueue.user_id == current_user.id,
        models.EmailQueue.channel == "whatsapp",
    ).first()

    if not item:
        raise HTTPException(status_code=404, detail="WhatsApp queue item not found")

    if item.status == "sent":
        raise HTTPException(status_code=400, detail="Cannot delete sent WhatsApp message")

    db.delete(item)
    db.commit()

    return {"success": True, "message": "WhatsApp message deleted"}


@router.post("/process-queue")
async def process_queue(
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    from whatsapp_service import process_whatsapp_queue

    return await process_whatsapp_queue(
        db=db,
        user_id=current_user.id,
    )


@router.get("/webhook", response_class=PlainTextResponse)
async def verify_meta_webhook(
    hub_mode: Optional[str] = Query(None, alias="hub.mode"),
    hub_verify_token: Optional[str] = Query(None, alias="hub.verify_token"),
    hub_challenge: Optional[str] = Query(None, alias="hub.challenge"),
):
    expected_token = os.getenv("WHATSAPP_WEBHOOK_VERIFY_TOKEN")

    if not expected_token:
        raise HTTPException(
            status_code=500,
            detail="WHATSAPP_WEBHOOK_VERIFY_TOKEN is not configured",
        )

    if hub_mode == "subscribe" and hub_verify_token == expected_token:
        return PlainTextResponse(content=hub_challenge or "")

    raise HTTPException(status_code=403, detail="Webhook verification failed")


@router.post("/webhook")
async def receive_meta_webhook(
    request: Request,
    db: Session = Depends(get_db),
):
    payload = await request.json()

    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})

            for status_item in value.get("statuses", []):
                message_id = status_item.get("id")
                delivery_status = status_item.get("status")

                if not message_id:
                    continue

                item = db.query(models.EmailQueue).filter(
                    models.EmailQueue.whatsapp_message_id == message_id,
                    models.EmailQueue.channel == "whatsapp",
                ).first()

                if not item:
                    continue

                item.delivery_status = delivery_status

                if delivery_status in {"sent", "delivered", "read"}:
                    item.status = "sent"
                    if not item.sent_at:
                        item.sent_at = datetime.utcnow()

                elif delivery_status == "failed":
                    item.status = "failed"
                    item.error_message = str(status_item.get("errors") or "")

            for message in value.get("messages", []):
                from_phone = message.get("from")
                timestamp = message.get("timestamp")
                message_type = message.get("type")
                text_body = None

                if message_type == "text":
                    text_body = (message.get("text") or {}).get("body")

                if not from_phone:
                    continue

                # MVP note:
                # This stores inbound WhatsApp activity for 24-hour window detection.
                # If multiple users connect WhatsApp numbers, replace user_id resolution
                # with phone_number_id -> user lookup from encrypted WhatsApp settings.
                user_id = _resolve_user_id_from_webhook_value(db, value)

                if not user_id:
                    continue

                occurred_at = datetime.utcnow()
                if timestamp:
                    try:
                        occurred_at = datetime.utcfromtimestamp(int(timestamp))
                    except Exception:
                        occurred_at = datetime.utcnow()

                activity = models.ContactActivity(
                    user_id=user_id,
                    activity_type="whatsapp_message",
                    direction="inbound",
                    source_type="whatsapp",
                    source_id=from_phone,
                    title="Inbound WhatsApp message",
                    summary=text_body,
                    raw_content=str(message),
                    occurred_at=occurred_at,
                    activity_at=occurred_at,
                    is_new=True,
                    extra_data={
                        "message_id": message.get("id"),
                        "phone_number_id": (value.get("metadata") or {}).get("phone_number_id"),
                        "display_phone_number": (value.get("metadata") or {}).get("display_phone_number"),
                        "message_type": message_type,
                    },
                )
                db.add(activity)

    db.commit()

    return {"success": True}


@router.get("/templates")
async def list_whatsapp_templates(
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    from api_keys import get_whatsapp_settings

    settings = get_whatsapp_settings(db, current_user.id)

    if not settings:
        raise HTTPException(
            status_code=400,
            detail="WhatsApp settings are not configured",
        )

    business_account_id = settings.get("business_account_id")
    access_token = settings.get("access_token")

    if not business_account_id or not access_token:
        raise HTTPException(
            status_code=400,
            detail="WhatsApp Business Account ID or access token is missing",
        )

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"https://graph.facebook.com/v25.0/{business_account_id}/message_templates",
            headers={"Authorization": f"Bearer {access_token}"},
        )

    if response.status_code >= 400:
        raise HTTPException(
            status_code=response.status_code,
            detail=response.text,
        )

    return response.json()


def _resolve_user_id_from_webhook_value(db: Session, value: dict) -> Optional[int]:
    """
    MVP resolver for inbound webhook messages.

    Best production version:
    - Read phone_number_id from value["metadata"]["phone_number_id"]
    - Match it against encrypted WhatsApp settings
    - Return that user's ID

    For now, this tries to locate an existing WhatsApp queue row that used
    the same business phone metadata is not available in EmailQueue yet.
    So we safely return None instead of guessing the wrong user.
    """
    phone_number_id = (value.get("metadata") or {}).get("phone_number_id")

    if not phone_number_id:
        return None

    # TODO:
    # Implement phone_number_id -> user_id lookup when WhatsApp settings
    # are stored in ApiKey encrypted JSON and searchable by a safe metadata column.
    return None