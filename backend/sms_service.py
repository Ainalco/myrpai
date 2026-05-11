import logging
import re
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

import models
from ai_service import generate_sms_message, flush_usage_log, set_usage_context
from variable_substitution import substitute_variables

logger = logging.getLogger(__name__)

OPT_OUT_TEXT = "Reply STOP to unsubscribe"


class SMSService:
    def __init__(self, db: Session, user: models.User):
        self.db = db
        self.user = user

    async def execute_sms_async(
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
        max_segments = int(config.get("max_segments", 1))
        max_chars = max_segments * 160
        include_opt_out = config.get("include_opt_out", True)

        if not recipient_phone:
            if test_mode:
                return {
                    "status": "warning",
                    "data": {
                        "test_mode": True,
                        "warning": "No recipient phone number found",
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
                error_message="No recipient phone number found",
            )

            return {
                "status": "warning",
                "data": {
                    "queue_id": queue_item.id,
                    "approval_status": queue_item.approval_status,
                    "delivery_status": "missing_phone",
                    "message": "SMS queued but missing recipient phone number",
                },
            }

        ai_prompt = config.get("ai_prompt") or config.get("prompt")
        if not ai_prompt:
            return {"status": "error", "error": "SMS AI prompt is required"}

        component_outputs = input_data.get("__component_outputs__", {})
        processed_prompt = substitute_variables(
            ai_prompt,
            input_data,
            component_outputs,
            component_name="SMS Component",
        )

        if include_opt_out and OPT_OUT_TEXT not in processed_prompt:
            processed_prompt = (
                f"{processed_prompt}\n\n"
                f"Mandatory ending: {OPT_OUT_TEXT}. This counts toward the character limit."
            )

        set_usage_context(
            user_id=self.user.id,
            source="sms_generation",
            execution_id=execution_id,
            component_id=component_id,
        )

        sms_body = await generate_sms_message(
            prompt=processed_prompt,
            input_data=input_data,
            max_chars=max_chars,
            workflow_id=workflow_id,
            db=self.db,
        )

        sms_body = self._clean_sms_body(sms_body)

        if include_opt_out and OPT_OUT_TEXT not in sms_body:
            sms_body = f"{sms_body.rstrip()} {OPT_OUT_TEXT}"

        character_count = len(sms_body)
        segments = max(1, (character_count + 159) // 160)
        over_limit = character_count > max_chars

        flush_usage_log(self.db)

        if test_mode:
            return {
                "status": "warning" if over_limit else "success",
                "data": {
                    "test_mode": True,
                    "recipient_phone": recipient_phone,
                    "message_body": sms_body,
                    "character_count": character_count,
                    "segments": segments,
                    "max_chars": max_chars,
                    "warning": "SMS exceeds max character limit" if over_limit else None,
                },
            }

        scheduled_at = self._resolve_scheduled_at(config)

        queue_item = self._create_queue_item(
            workflow_id=workflow_id,
            execution_id=execution_id,
            component_id=component_id,
            recipient_phone=recipient_phone,
            body=sms_body,
            scheduled_at=scheduled_at,
            status="needs_edit" if over_limit else "pending",
            delivery_status="over_character_limit" if over_limit else "queued",
            character_count=character_count,
            sms_segments=segments,
            error_message="SMS exceeds max character limit; edit before sending" if over_limit else None,
        )

        return {
            "status": "warning" if over_limit else "success",
            "data": {
                "queue_id": queue_item.id,
                "recipient_phone": recipient_phone,
                "message_body": sms_body,
                "character_count": character_count,
                "segments": segments,
                "max_chars": max_chars,
                "approval_status": queue_item.approval_status,
                "scheduled_at": queue_item.scheduled_at.isoformat(),
                "warning": queue_item.error_message,
            },
        }

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

        value = str(value).strip()
        if not value:
            return None

        cleaned = re.sub(r"[^\d+]", "", value)

        if len(cleaned) < 8:
            return None

        return cleaned

    def _clean_sms_body(self, body: str) -> str:
        body = re.sub(r"<[^>]+>", "", body or "")
        body = body.replace("\n", " ").replace("\r", " ")
        body = re.sub(r"\s+", " ", body).strip()
        return body

    def _resolve_scheduled_at(self, config: dict) -> datetime:
        scheduled_at = datetime.utcnow()
        send_timing = config.get("send_timing", "immediate")

        if send_timing == "fixed_delay":
            delay_value = int(config.get("delay_value", 0))
            delay_unit = config.get("delay_unit", "minutes")

            if delay_unit == "minutes":
                scheduled_at += timedelta(minutes=delay_value)
            elif delay_unit == "hours":
                scheduled_at += timedelta(hours=delay_value)
            elif delay_unit == "days":
                scheduled_at += timedelta(days=delay_value)

        elif send_timing == "ai_decides":
            scheduled_at += timedelta(hours=2)

        return scheduled_at

    def _create_queue_item(
        self,
        workflow_id: Optional[int],
        execution_id: Optional[int],
        component_id: Optional[int],
        recipient_phone: Optional[str],
        body: str,
        scheduled_at: datetime,
        status: str,
        delivery_status: Optional[str],
        character_count: Optional[int] = None,
        sms_segments: Optional[int] = None,
        error_message: Optional[str] = None,
    ) -> models.EmailQueue:
        queue_item = models.EmailQueue(
            user_id=self.user.id,
            workflow_id=workflow_id,
            execution_id=execution_id,
            component_id=component_id,
            channel="sms",
            recipient_email="",
            recipient_phone=recipient_phone,
            recipient_name=None,
            subject="[SMS]",
            body=body,
            scheduled_at=scheduled_at,
            status=status,
            approval_status="pending",
            delivery_status=delivery_status,
            character_count=character_count,
            sms_segments=sms_segments,
            error_message=error_message,
        )

        self.db.add(queue_item)
        self.db.commit()
        self.db.refresh(queue_item)

        return queue_item