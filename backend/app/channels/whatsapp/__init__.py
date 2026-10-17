"""WhatsApp channel package (spec/02 §2.4, spec/07 §7.2)."""

from backend.app.channels.whatsapp.channel import WhatsAppChannel
from backend.app.channels.whatsapp.client import WhatsAppClient, whatsapp_client
from backend.app.channels.whatsapp.media import (
    clear_whatsapp_media_cache,
    download_whatsapp_media,
    upload_whatsapp_media,
)
from backend.app.channels.whatsapp.security import verify_whatsapp_signature
from backend.app.channels.whatsapp.templates import (
    build_template_payload,
    get_template_by_name,
    is_template_approved,
    load_whatsapp_templates,
)
from backend.app.channels.whatsapp.webhook import (
    process_inbound_whatsapp,
    router,
)

__all__ = [
    "WhatsAppChannel",
    "WhatsAppClient",
    "whatsapp_client",
    "router",
    "verify_whatsapp_signature",
    "process_inbound_whatsapp",
    "download_whatsapp_media",
    "upload_whatsapp_media",
    "clear_whatsapp_media_cache",
    "load_whatsapp_templates",
    "get_template_by_name",
    "is_template_approved",
    "build_template_payload",
]
