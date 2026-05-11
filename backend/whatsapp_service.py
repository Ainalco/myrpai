import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

import models
from ai_service import generate_whatsapp_message, flush_usage_log, set_usage_context
from variable_substitution import substitute_variables

logger = logging.getLogger(__name__)


class WhatsAppService:
    def __init__(self, db: Session, user: models.User):
        self.db = db
        self.user = user

    async def execute_whatsapp_async(
        self,
        config: dict,
        input_data: dict,
        workflow_id: Optional[int] = None,
        execution_id: Optional[int] = None,
        component_id: Optional[int] = None,
    ) -> dict:
        test_mode = bool(input_data.get("test_mode", False))
        workflow_id = workflow_id or input_data.get("workflow_id")
        execution_id = execution_id or input_data.get("execution_id")
        component_id = component_id or config.get("component_id")

        recipient_phone = self._resolve_phone(config, input_data)

        if not recipient_phone:
            if test_mode:
                return {
                    "status": "warning",
                    "data": {
                        "test_mode": True,
                        "warning": "No recipient WhatsApp phone number found",
                    },
                }

            queue_item = self._create_queue_item(
                workflow_id=workflow_id,
                execution_id=execution_id,
                component_id=component_id,
                recipient_phone=None,
                body="",
                scheduled_at=datetime.utcnow(),
                status="missing_phone",
                delivery_status="missing_phone",
                message_type="template",
                template_name=config.get("fallback_template", "meeting_followup_1"),
                error_message="No recipient WhatsApp phone number found",
            )

            return {
                "status": "warning",
                "data": {
                    "queue_id": queue_item.id,
                    "approval_status": queue_item.approval_status,
                    "delivery_status": "missing_phone",
                    "message": "WhatsApp message queued but missing recipient phone number",
                },
            }

        ai_prompt = config.get("ai_prompt") or config.get("prompt")
        if not ai_prompt:
            return {"status": "error", "error": "WhatsApp AI prompt is required"}

        component_outputs = input_data.get("__component_outputs__", {})
        processed_prompt = substitute_variables(
            ai_prompt,
            input_data,
            component_outputs,
            component_name="WhatsApp Component",
        )

        set_usage_context(
            user_id=self.user.id,
            source="whatsapp_generation",
            execution_id=execution_id,
            component_id=component_id,
        )

        message_body = await generate_whatsapp_message(
            prompt=processed_prompt,
            input_data=input_data,
            max_chars=4096,
            workflow_id=workflow_id,
            db=self.db,
        )

        message_body = self._clean_whatsapp_body(message_body)
        character_count = len(message_body)
        over_limit = character_count > 4096

        flush_usage_log(self.db)

        message_type = self.determine_message_type(recipient_phone)
        template_name = config.get("fallback_template", "meeting_followup_1")

        if test_mode:
            return {
                "status": "warning" if over_limit else "success",
                "data": {
                    "test_mode": True,
                    "recipient_phone": recipient_phone,
                    "message_body": message_body,
                    "message_type": message_type,
                    "template_name": template_name if message_type == "template" else None,
                    "character_count": character_count,
                    "max_chars": 4096,
                    "warning": "WhatsApp message exceeds 4096 characters" if over_limit else None,
                },
            }

        scheduled_at = self._resolve_scheduled_at(config)

        queue_item = self._create_queue_item(
            workflow_id=workflow_id,
            execution_id=execution_id,
            component_id=component_id,
            recipient_phone=recipient_phone,
            body=message_body,
            scheduled_at=scheduled_at,
            status="needs_edit" if over_limit else "pending",
            delivery_status="over_character_limit" if over_limit else "queued",
            message_type=message_type,
            template_name=template_name if message_type == "template" else None,
            error_message="WhatsApp message exceeds 4096 characters; edit before sending" if over_limit else None,
        )

        return {
            "status": "warning" if over_limit else "success",
            "data": {
                "queue_id": queue_item.id,
                "recipient_phone": recipient_phone,
                "message_body": message_body,
                "message_type": message_type,
                "approval_status": queue_item.approval_status,
                "scheduled_at": queue_item.scheduled_at.isoformat(),
                "warning": queue_item.error_message,
            },
        }

    def determine_message_type(self, recipient_phone: str) -> str:
        last_inbound = self.get_last_inbound_message(recipient_phone)
        if not last_inbound:
            return "template"

        now = datetime.now(timezone.utc)
        received_at = last_inbound.occurred_at
        if received_at and received_at.tzinfo is None:
            received_at = received_at.replace(tzinfo=timezone.utc)

        if received_at and now - received_at <= timedelta(hours=24):
            return "freeform"

        return "template"

    def get_last_inbound_message(self, recipient_phone: str):
        return (
            self.db.query(models.ContactActivity)
            .filter(
                models.ContactActivity.user_id == self.user.id,
                models.ContactActivity.activity_type == "whatsapp_message",
                models.ContactActivity.direction == "inbound",
                models.ContactActivity.source_id == recipient_phone,
            )
            .order_by(models.ContactActivity.occurred_at.desc())
            .first()
        )

    def _resolve_phone(self, config: dict, input_data: dict) -> Optional[str]:
        field = config.get("recipient_phone_field", "recipient_phone")

        candidates = [
            input_data.get(field),
            input_data.get("recipient_phone"),
            input_data.get("phone"),
            input_data.get("mobile"),
            input_data.get("contact_phone"),
        ]

        extracted = input_data.get("extracted_information") or {}
        if isinstance(extracted, dict):
            candidates.extend([
                extracted.get("phone"),
                extracted.get("Phone"),
                extracted.get("mobile"),
                extracted.get("Mobile"),
            ])

        for participant in input_data.get("participants", []) or []:
            if isinstance(participant, dict):
                candidates.extend([
                    participant.get("phone"),
                    participant.get("mobile"),
                ])

        for candidate in candidates:
            normalized = self._normalize_phone(candidate)
            if normalized:
                return normalized

        return None

    def _normalize_phone(self, value: Optional[str]) -> Optional[str]:
        if not value:
            return None

        cleaned = re.sub(r"[^\d+]", "", str(value).strip())

        if cleaned.startswith("00"):
            cleaned = "+" + cleaned[2:]

        if not cleaned.startswith("+"):
            return None

        digits = re.sub(r"\D", "", cleaned)
        if len(digits) < 8 or len(digits) > 15:
            return None

        return cleaned

    def _clean_whatsapp_body(self, body: str) -> str:
        body = re.sub(r"<[^>]+>", "", body or "")
        body = body.replace("\r\n", "\n").replace("\r", "\n")
        body = re.sub(r"\n{3,}", "\n\n", body)
        return body.strip()

    def _resolve_scheduled_at(self, config: dict) -> datetime:
        scheduled_at = datetime.utcnow()
        send_timing = config.get("send_timing", "immediate")

        if send_timing == "fixed_delay":
            delay_config = config.get("delay_config") or {}
            delay_hours = int(delay_config.get("delay_hours", config.get("delay_hours", 0)) or 0)
            delay_days = int(delay_config.get("delay_days", config.get("delay_days", 0)) or 0)
            scheduled_at += timedelta(hours=delay_hours, days=delay_days)

        elif send_timing == "ai_decides":
            scheduled_at += timedelta(hours=2)

        return scheduled_at

    def _create_queue_item(
        self,
        workflow_id,
        execution_id,
        component_id,
        recipient_phone,
        body,
        scheduled_at,
        status,
        delivery_status,
        message_type,
        template_name=None,
        error_message=None,
    ) -> models.EmailQueue:
        queue_item = models.EmailQueue(
            user_id=self.user.id,
            workflow_id=workflow_id,
            execution_id=execution_id,
            component_id=component_id,
            channel="whatsapp",
            recipient_email="",
            recipient_phone=recipient_phone,
            recipient_name=None,
            subject="[WhatsApp]",
            body=body,
            scheduled_at=scheduled_at,
            status=status,
            approval_status="pending",
            delivery_status=delivery_status,
            character_count=len(body or ""),
            whatsapp_template_name=template_name,
            is_template_message=message_type == "template",
            conversation_window_expires_at=(
                datetime.utcnow() + timedelta(hours=24)
                if message_type == "freeform"
                else None
            ),
            error_message=error_message,
        )

        self.db.add(queue_item)
        self.db.commit()
        self.db.refresh(queue_item)
        return queue_item
    
    
async def process_whatsapp_queue(db: Session, user_id: Optional[int] = None) -> dict:
    from api_keys import get_whatsapp_settings
    from whatsapp_delivery import WhatsAppAdapter

    now = datetime.utcnow()

    query = db.query(models.EmailQueue).filter(
        models.EmailQueue.channel == "whatsapp",
        models.EmailQueue.status == "pending",
        models.EmailQueue.approval_status == "approved",
        models.EmailQueue.scheduled_at <= now,
    )

    if user_id is not None:
        query = query.filter(models.EmailQueue.user_id == user_id)

    items = query.all()

    sent = 0
    failed = 0

    for item in items:
        try:
            if not item.recipient_phone:
                item.status = "failed"
                item.delivery_status = "missing_phone"
                item.error_message = "Missing recipient WhatsApp phone number"
                failed += 1
                continue

            settings = get_whatsapp_settings(db, item.user_id)

            if not settings:
                item.status = "failed"
                item.delivery_status = "missing_credentials"
                item.error_message = "WhatsApp settings not configured"
                failed += 1
                continue

            phone_number_id = settings.get("phone_number_id")
            access_token = settings.get("access_token")

            if not phone_number_id or not access_token:
                item.status = "failed"
                item.delivery_status = "missing_credentials"
                item.error_message = "WhatsApp phone_number_id or access_token is missing"
                failed += 1
                continue

            adapter = WhatsAppAdapter(
                phone_number_id=phone_number_id,
                access_token=access_token,
            )

            # Meta usually expects phone without "+"
            to_phone = item.recipient_phone.replace("+", "")

            if item.is_template_message:
                result = await adapter.send_template_message(
                    to=to_phone,
                    template_name=item.whatsapp_template_name or "meeting_followup_1",
                    params=[
                        item.recipient_name or "there",
                        "our conversation",
                        item.body[:900],
                    ],
                )
            else:
                result = await adapter.send_message(
                    to=to_phone,
                    body=item.body,
                )

            item.whatsapp_message_id = result.get("message_id")
            item.delivery_status = "sent"
            item.status = "sent"
            item.sent_at = datetime.utcnow()
            item.error_message = None
            sent += 1

        except Exception as exc:
            item.status = "failed"
            item.delivery_status = "failed"
            item.error_message = str(exc)
            failed += 1

    db.commit()

    return {
        "success": True,
        "processed": len(items),
        "sent": sent,
        "failed": failed,
    }