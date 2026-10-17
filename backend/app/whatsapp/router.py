"""WhatsApp Webhook endpoint router (spec/07 §7.2).

Re-exports canonical router and endpoints from backend.app.channels.whatsapp.webhook.
"""

from backend.app.channels.whatsapp.webhook import router

__all__ = ["router"]
