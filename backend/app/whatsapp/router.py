"""WhatsApp Webhook endpoint router (§11)."""

import logging

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response, status

from backend.app.config import settings
from backend.app.whatsapp.models import WhatsAppWebhookPayload
from backend.app.whatsapp.security import verify_whatsapp_signature

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/whatsapp", tags=["WhatsApp"])

# Idempotency cache for processed WhatsApp message IDs
_PROCESSED_MESSAGE_IDS: set[str] = set()


@router.get("/webhook")
async def verify_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
) -> Response:
    """Meta webhook verification endpoint."""
    if not settings.WHATSAPP_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="WhatsApp channel is disabled",
        )
    if not settings.WHATSAPP_VERIFY_TOKEN:
        logger.warning("WhatsApp verify token is not configured.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Verify token not configured",
        )
    if hub_mode == "subscribe" and hub_verify_token == settings.WHATSAPP_VERIFY_TOKEN:
        logger.info("WhatsApp webhook verified successfully.")
        return Response(content=hub_challenge, media_type="text/plain")
    logger.warning("WhatsApp webhook verification failed.")
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Verification token mismatch")


@router.post("/webhook")
async def receive_webhook(
    request: Request,
    x_hub_signature_256: str = Header(None, alias="X-Hub-Signature-256"),
) -> dict[str, str]:
    """Receives inbound messages, verifies signature, ensures idempotency, and routes."""
    if not settings.WHATSAPP_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="WhatsApp channel is disabled",
        )

    if not settings.WHATSAPP_APP_SECRET:
        logger.error("WHATSAPP_APP_SECRET is not configured.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="WhatsApp webhook secret not configured",
        )

    body_bytes = await request.body()

    if not x_hub_signature_256 or not verify_whatsapp_signature(body_bytes, x_hub_signature_256):
        logger.error("Invalid webhook HMAC signature.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid signature",
        )

    payload_json = await request.json()
    try:
        payload = WhatsAppWebhookPayload.model_validate(payload_json)
    except Exception as e:
        logger.warning("Unrecognized webhook payload structure: %s", e)
        return {"status": "ignored"}

    # Process events
    for entry in payload.entry:
        for change in entry.changes:
            value = change.get("value", {})
            messages = value.get("messages", [])
            for msg in messages:
                msg_id = msg.get("id")
                if msg_id in _PROCESSED_MESSAGE_IDS:
                    logger.info("Skipping duplicate message id: %s", msg_id)
                    continue
                _PROCESSED_MESSAGE_IDS.add(msg_id)

                from_phone = msg.get("from")
                msg_type = msg.get("type")
                logger.info("Received WhatsApp message from %s (type: %s)", from_phone, msg_type)

    return {"status": "ok"}
