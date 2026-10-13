"""WhatsApp webhook signature verification and security (§11)."""

import hashlib
import hmac

from backend.app.config import settings


def verify_whatsapp_signature(payload_bytes: bytes, signature_header: str) -> bool:
    """Verifies SHA256 signature from WhatsApp / Meta Cloud API."""
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    if not settings.WHATSAPP_APP_SECRET:
        return False

    expected_sig = signature_header.split("sha256=")[1]
    computed_sig = hmac.new(
        key=settings.WHATSAPP_APP_SECRET.encode("utf-8"),
        msg=payload_bytes,
        digestmod=hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(computed_sig, expected_sig)
