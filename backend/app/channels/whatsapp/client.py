"""WhatsApp Cloud API client (spec/07 §7.2).

Direct Meta Graph API client with:
- Text messages (up to 4096 characters)
- Voice/audio messages (via uploaded media ID)
- Interactive buttons (up to 3 quick reply buttons, title <= 20 chars)
- Interactive list (when > 3 options, up to 10 rows)
- Pre-approved utility templates (for messages outside 24h window)
- Rate limiting: token bucket 20 msg/s global
- Exponential backoff retry on 429 and 5xx (0.5 s, 2 s, 8 s)
- Mock mode for test / empty token
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any, Final

import httpx

from backend.app.channels.whatsapp.media import download_whatsapp_media, upload_whatsapp_media
from backend.app.channels.whatsapp.templates import build_template_payload
from backend.app.config import settings

logger = logging.getLogger("abhyas.channels.whatsapp.client")

MAX_TEXT_LENGTH: Final = 4096
RATE_LIMIT_RPS: Final = 20.0
RETRY_DELAYS: Final = (0.5, 2.0, 8.0)


class _RateLimiter:
    """Global token bucket rate limiter (20 msg/s per spec/07 §7.2)."""

    def __init__(self, rate: float = RATE_LIMIT_RPS) -> None:
        self.rate = rate
        self.capacity = rate
        self.tokens = rate
        self.last_update = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_update
            self.last_update = now
            self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
            if self.tokens < 1.0:
                wait_time = (1.0 - self.tokens) / self.rate
                await asyncio.sleep(wait_time)
                self.tokens = 0.0
            else:
                self.tokens -= 1.0


_global_rate_limiter = _RateLimiter()


class WhatsAppClient:
    """Meta WhatsApp Cloud API Client."""

    def __init__(self) -> None:
        self._limiter = _global_rate_limiter

    @property
    def api_url(self) -> str:
        version = settings.WHATSAPP_GRAPH_VERSION
        phone_id = settings.WHATSAPP_PHONE_NUMBER_ID
        return f"https://graph.facebook.com/{version}/{phone_id}/messages"

    async def send_text(self, to_e164: str, text: str) -> dict[str, Any]:
        """Sends a standard text message (<= 4096 chars)."""
        body_text = text[:MAX_TEXT_LENGTH]
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to_e164,
            "type": "text",
            "text": {"preview_url": False, "body": body_text},
        }
        return await self._post_with_retry(payload)

    async def send_audio(self, to_e164: str, media_id: str) -> dict[str, Any]:
        """Sends an audio/voice message."""
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to_e164,
            "type": "audio",
            "audio": {"id": media_id},
        }
        return await self._post_with_retry(payload)

    async def send_interactive_buttons(
        self,
        to_e164: str,
        body_text: str,
        buttons: list[tuple[str, str]],  # (button_id, title)
    ) -> dict[str, Any]:
        """Sends quick reply interactive buttons (max 3 buttons, title <= 20 chars)."""
        action_buttons = [
            {
                "type": "reply",
                "reply": {
                    "id": bid,
                    "title": title[: settings.WHATSAPP_BUTTON_TITLE_MAX],
                },
            }
            for bid, title in buttons[: settings.WHATSAPP_REPLY_BUTTONS_MAX]
        ]
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to_e164,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": body_text[:MAX_TEXT_LENGTH]},
                "action": {"buttons": action_buttons},
            },
        }
        return await self._post_with_retry(payload)

    async def send_interactive_list(
        self,
        to_e164: str,
        body_text: str,
        button_label: str,
        rows: list[tuple[str, str, str | None]],  # (id, title, description)
    ) -> dict[str, Any]:
        """Sends interactive list message (> 3 options, max 10 rows)."""
        section_rows = [
            {
                "id": rid,
                "title": title[: settings.WHATSAPP_BUTTON_TITLE_MAX],
                **({"description": desc[:72]} if desc else {}),
            }
            for rid, title, desc in rows[: settings.WHATSAPP_LIST_ROWS_MAX]
        ]
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to_e164,
            "type": "interactive",
            "interactive": {
                "type": "list",
                "body": {"text": body_text[:MAX_TEXT_LENGTH]},
                "action": {
                    "button": button_label[:20],
                    "sections": [{"rows": section_rows}],
                },
            },
        }
        return await self._post_with_retry(payload)

    async def send_template(
        self,
        to_e164: str,
        template_name: str,
        language_code: str = "hi",
        parameters: list[str] | None = None,
    ) -> dict[str, Any]:
        """Sends pre-approved utility template outside 24h window."""
        template_payload = build_template_payload(
            template_name=template_name,
            parameters=parameters,
            language_code=language_code,
        )
        payload = {
            "messaging_product": "whatsapp",
            "to": to_e164,
            "type": "template",
            "template": template_payload,
        }
        return await self._post_with_retry(payload)

    async def upload_media(
        self,
        audio_bytes: bytes,
        mime_type: str = "audio/ogg; codecs=opus",
        cache_key: str | None = None,
    ) -> str:
        """Uploads audio file to Meta and returns media ID."""
        return await upload_whatsapp_media(audio_bytes, mime_type, cache_key)

    async def download_media(self, media_id: str) -> bytes:
        """Downloads audio file from Meta given media ID."""
        return await download_whatsapp_media(media_id)

    async def _post_with_retry(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Posts payload with rate limiting and exponential backoff retry on 429/5xx."""
        token = settings.WHATSAPP_ACCESS_TOKEN
        if not token or token.startswith("mock") or not settings.WHATSAPP_ENABLED:
            logger.info(
                "Mock WhatsApp dispatch to %s (type: %s)", payload.get("to"), payload.get("type")
            )
            return {"messages": [{"id": f"mock_wamid_{uuid.uuid4().hex[:16]}"}]}

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        last_exc: Exception | None = None
        for attempt, delay in enumerate(RETRY_DELAYS, start=1):
            await self._limiter.acquire()
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.post(self.api_url, headers=headers, json=payload)
                    if resp.status_code in (429, 500, 502, 503, 504):
                        logger.warning(
                            "Meta Graph API error status %d (attempt %d/%d): %s",
                            resp.status_code,
                            attempt,
                            len(RETRY_DELAYS),
                            resp.text,
                        )
                        if attempt < len(RETRY_DELAYS):
                            await asyncio.sleep(delay)
                            continue
                        resp.raise_for_status()

                    resp.raise_for_status()
                    return resp.json()  # type: ignore[no-any-return]
            except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                last_exc = exc
                if attempt < len(RETRY_DELAYS):
                    logger.warning("WhatsApp request error: %s; retrying in %fs", exc, delay)
                    await asyncio.sleep(delay)
                else:
                    logger.error("WhatsApp request failed after %d attempts: %s", attempt, exc)
                    raise

        if last_exc:
            raise last_exc
        return {"status": "ok"}


whatsapp_client = WhatsAppClient()
