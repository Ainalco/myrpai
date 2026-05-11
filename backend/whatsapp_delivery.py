import httpx


class WhatsAppAdapter:
    BASE_URL = "https://graph.facebook.com/v25.0"

    def __init__(self, phone_number_id: str, access_token: str):
        self.phone_number_id = phone_number_id
        self.access_token = access_token

    async def send_message(self, to: str, body: str) -> dict:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.BASE_URL}/{self.phone_number_id}/messages",
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                    "Content-Type": "application/json",
                },
                json={
                    "messaging_product": "whatsapp",
                    "recipient_type": "individual",
                    "to": to,
                    "type": "text",
                    "text": {
                        "preview_url": True,
                        "body": body,
                    },
                },
            )
            response.raise_for_status()
            data = response.json()

        return {
            "message_id": data["messages"][0]["id"],
            "status": "sent",
            "raw": data,
        }

    async def send_template_message(
        self,
        to: str,
        template_name: str,
        params: list[str],
        language_code: str = "en",
    ) -> dict:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.BASE_URL}/{self.phone_number_id}/messages",
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                    "Content-Type": "application/json",
                },
                json={
                    "messaging_product": "whatsapp",
                    "recipient_type": "individual",
                    "to": to,
                    "type": "template",
                    "template": {
                        "name": template_name,
                        "language": {"code": language_code},
                        "components": [
                            {
                                "type": "body",
                                "parameters": [
                                    {"type": "text", "text": str(p)}
                                    for p in params
                                ],
                            }
                        ],
                    },
                },
            )
            response.raise_for_status()
            data = response.json()

        return {
            "message_id": data["messages"][0]["id"],
            "status": "sent",
            "raw": data,
        }