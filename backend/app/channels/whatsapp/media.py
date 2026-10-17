"""WhatsApp Cloud API media download and upload handlers (spec/07 §7.2).

Media Download:
- GET /{media_id} -> {url, mime_type}
- GET url with Bearer token -> bytes (in memory, max 16 MB)

Media Upload:
- POST /{WHATSAPP_PHONE_NUMBER_ID}/media multipart file
- Caches media ID per content hash / TTS cache key for 25 days (Meta IDs expire ~30 days)
"""

from __future__ import annotations

import hashlib
import logging
import time
from typing import Any, Final

import httpx

from backend.app.config import settings

logger = logging.getLogger("abhyas.channels.whatsapp.media")

MAX_MEDIA_BYTES: Final = 16 * 1024 * 1024  # 16 MB limit per spec/07 §7.2
MEDIA_CACHE_TTL_SECONDS: Final = 25 * 86400  # 25 days cache TTL

# In-memory media cache: key -> (media_id, expire_timestamp)
_MEDIA_CACHE: dict[str, tuple[str, float]] = {}


def cache_whatsapp_media_id(key: str, media_id: str) -> None:
    """Caches a Meta media ID for 25 days."""
    expire_at = time.time() + MEDIA_CACHE_TTL_SECONDS
    _MEDIA_CACHE[key] = (media_id, expire_at)


def get_cached_whatsapp_media_id(key: str) -> str | None:
    """Returns cached media ID if not expired."""
    entry = _MEDIA_CACHE.get(key)
    if not entry:
        return None
    media_id, expire_at = entry
    if time.time() > expire_at:
        _MEDIA_CACHE.pop(key, None)
        return None
    return media_id


def clear_whatsapp_media_cache() -> None:
    """Clears in-memory media cache (useful in tests)."""
    _MEDIA_CACHE.clear()


async def download_whatsapp_media(media_id: str) -> bytes:
    """Downloads media from Meta Cloud API given media_id.

    Returns bytes in memory, enforcing the 16 MB maximum size limit.
    """
    token = settings.WHATSAPP_ACCESS_TOKEN
    if not token or token.startswith("mock") or not settings.WHATSAPP_ENABLED:
        logger.info("Mock media download for id %s", media_id)
        # Return mock audio payload
        return b"RIFF" + b"\x00" * 1024

    version = settings.WHATSAPP_GRAPH_VERSION
    meta_url = f"https://graph.facebook.com/{version}/{media_id}"
    headers = {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient(timeout=15.0) as client:
        # Step 1: retrieve direct download URL
        meta_resp = await client.get(meta_url, headers=headers)
        meta_resp.raise_for_status()
        data: dict[str, Any] = meta_resp.json()
        direct_url = data.get("url")
        file_size = data.get("file_size", 0)

        if not direct_url:
            raise ValueError(f"No download URL returned by Meta for media_id {media_id}")
        if file_size > MAX_MEDIA_BYTES:
            raise ValueError(f"Media size {file_size} exceeds maximum {MAX_MEDIA_BYTES} bytes")

        # Step 2: download binary payload with Authorization header
        file_resp = await client.get(direct_url, headers=headers)
        file_resp.raise_for_status()
        content = file_resp.content

        if len(content) > MAX_MEDIA_BYTES:
            raise ValueError(
                f"Downloaded media bytes {len(content)} exceeds limit {MAX_MEDIA_BYTES}"
            )

        return content


async def upload_whatsapp_media(
    audio_bytes: bytes,
    mime_type: str = "audio/ogg; codecs=opus",
    cache_key: str | None = None,
) -> str:
    """Uploads audio file to Meta WhatsApp Cloud API and returns media ID.

    Checks and populates 25-day media cache.
    """
    key = cache_key or hashlib.sha256(audio_bytes).hexdigest()
    cached = get_cached_whatsapp_media_id(key)
    if cached:
        return cached

    token = settings.WHATSAPP_ACCESS_TOKEN
    phone_number_id = settings.WHATSAPP_PHONE_NUMBER_ID
    if not token or token.startswith("mock") or not settings.WHATSAPP_ENABLED:
        logger.info("Mock media upload (%d bytes)", len(audio_bytes))
        mock_id = f"mock_media_{key[:12]}"
        cache_whatsapp_media_id(key, mock_id)
        return mock_id

    version = settings.WHATSAPP_GRAPH_VERSION
    upload_url = f"https://graph.facebook.com/{version}/{phone_number_id}/media"
    headers = {"Authorization": f"Bearer {token}"}

    filename = "voice.ogg" if "ogg" in mime_type else "audio.mp3"
    files = {"file": (filename, audio_bytes, mime_type)}
    data = {"messaging_product": "whatsapp", "type": mime_type}

    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(upload_url, headers=headers, data=data, files=files)
        resp.raise_for_status()
        resp_data: dict[str, Any] = resp.json()
        media_id = str(resp_data["id"])
        cache_whatsapp_media_id(key, media_id)
        return media_id
