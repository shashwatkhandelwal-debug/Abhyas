"""WhatsApp package exports."""

from backend.app.whatsapp.client import WhatsAppClient, whatsapp_client
from backend.app.whatsapp.models import (
    WhatsAppAudioMessage,
    WhatsAppInteractiveReply,
    WhatsAppMessage,
    WhatsAppTextMessage,
    WhatsAppWebhookPayload,
)
from backend.app.whatsapp.router import router as whatsapp_router
from backend.app.whatsapp.security import verify_whatsapp_signature
from backend.app.whatsapp.templates import (
    build_arp_digest_template,
    build_two_day_followup_template,
    build_weekly_move_prompt_template,
)

__all__ = [
    "whatsapp_router",
    "whatsapp_client",
    "WhatsAppClient",
    "verify_whatsapp_signature",
    "WhatsAppWebhookPayload",
    "WhatsAppMessage",
    "WhatsAppTextMessage",
    "WhatsAppAudioMessage",
    "WhatsAppInteractiveReply",
    "build_weekly_move_prompt_template",
    "build_two_day_followup_template",
    "build_arp_digest_template",
]
