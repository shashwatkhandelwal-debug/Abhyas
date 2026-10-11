"""WhatsApp Business Cloud API / BSP Client (§11)."""

import logging
from typing import Any, Optional
import httpx
from backend.app.config import settings

logger = logging.getLogger(__name__)


class WhatsAppClient:
    def __init__(self) -> None:
        self.access_token = settings.WHATSAPP_ACCESS_TOKEN
        self.phone_number_id = settings.WHATSAPP_PHONE_NUMBER_ID
        self.api_url = f"https://graph.facebook.com/v19.0/{self.phone_number_id}/messages"

    async def send_text_message(self, to_phone: str, text: str) -> dict[str, Any]:
        """Sends a standard text message (free within 24h window)."""
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to_phone,
            "type": "text",
            "text": {"preview_url": False, "body": text},
        }
        return await self._post_message(payload)

    async def send_audio_message(self, to_phone: str, audio_media_id_or_url: str) -> dict[str, Any]:
        """Sends an audio note (voice reply) to the teacher."""
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to_phone,
            "type": "audio",
            "audio": {"id": audio_media_id_or_url},
        }
        return await self._post_message(payload)

    async def send_interactive_buttons(
        self,
        to_phone: str,
        body_text: str,
        buttons: list[tuple[str, str]],  # (button_id, title)
    ) -> dict[str, Any]:
        """Sends quick-reply interactive buttons (e.g., Retry, Continue, Skip)."""
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to_phone,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": body_text},
                "action": {
                    "buttons": [
                        {"type": "reply", "reply": {"id": bid, "title": title}}
                        for bid, title in buttons[:3]
                    ]
                },
            },
        }
        return await self._post_message(payload)

    async def send_utility_template(
        self,
        to_phone: str,
        template_payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Sends pre-approved utility template outside 24h window."""
        payload = {
            "messaging_product": "whatsapp",
            "to": to_phone,
            "type": "template",
            "template": template_payload,
        }
        return await self._post_message(payload)

    async def _post_message(self, payload: dict[str, Any]) -> dict[str, Any]:
        if settings.WHATSAPP_ACCESS_TOKEN.startswith("mock"):
            logger.info("Mock WhatsApp send: %s", payload)
            return {"messages": [{"id": "mock_wamid_123"}]}

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(self.api_url, headers=headers, json=payload)
            resp.raise_for_status()
            return resp.json()  # type: ignore


whatsapp_client = WhatsAppClient()
