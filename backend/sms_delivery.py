import asyncio
import logging
from typing import Optional

from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client

logger = logging.getLogger(__name__)


class TwilioAdapter:
    def __init__(self, account_sid: str, auth_token: str, from_number: str):
        self.client = Client(account_sid, auth_token)
        self.from_number = from_number

    async def send_sms(
        self,
        to: str,
        body: str,
        status_callback: Optional[str] = None,
    ) -> dict:
        if not to:
            raise ValueError("Recipient phone number is required")

        if not body:
            raise ValueError("SMS body is required")

        try:
            kwargs = {
                "body": body,
                "from_": self.from_number,
                "to": to,
            }

            if status_callback:
                kwargs["status_callback"] = status_callback

            message = await asyncio.to_thread(
                self.client.messages.create,
                **kwargs,
            )

            return {
                "sid": message.sid,
                "status": message.status,
                "segments": int(message.num_segments or 1),
                "price": message.price,
            }

        except TwilioRestException as exc:
            logger.error("Twilio SMS send failed: %s", exc)
            return {
                "sid": None,
                "status": "failed",
                "segments": None,
                "price": None,
                "error": str(exc),
                "twilio_code": getattr(exc, "code", None),
            }