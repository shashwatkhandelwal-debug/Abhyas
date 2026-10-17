"""WhatsApp Webhook HMAC signature verification (spec/02 §2.4, spec/07 §7.2).

Meta sends `X-Hub-Signature-256: sha256=<hex>` computed using the App Secret
over the raw request body bytes.
"""

from __future__ import annotations

import hashlib
import hmac
import logging

from backend.app.config import settings

logger = logging.getLogger("abhyas.channels.whatsapp.security")


def verify_whatsapp_signature(body_bytes: bytes, signature_header: str | None) -> bool:
    """Verifies SHA256 HMAC signature against settings.WHATSAPP_APP_SECRET.

    - Returns False if signature header is missing or malformed.
    - Returns False if WHATSAPP_APP_SECRET is empty.
    - Uses hmac.compare_digest for constant-time comparison to prevent timing attacks.
    """
    if not signature_header or not signature_header.startswith("sha256="):
        return False

    secret = settings.WHATSAPP_APP_SECRET
    if not secret:
        logger.error("WHATSAPP_APP_SECRET is empty; cannot verify webhook signature")
        return False

    parts = signature_header.split("sha256=", 1)
    if len(parts) != 2:
        return False
    expected_hex = parts[1].strip()

    computed_hex = hmac.new(
        key=secret.encode("utf-8"),
        msg=body_bytes,
        digestmod=hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(computed_hex, expected_hex)
