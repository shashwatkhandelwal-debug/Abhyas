"""Shared HTTP client for speech providers (spec/06 §6.4).

Provides a shared httpx.AsyncClient singleton for Sarvam and Bhashini API calls,
maintaining connection keep-alive pools without per-request allocation.
"""

from __future__ import annotations

import httpx

from backend.app.config import settings

_speech_http_client: httpx.AsyncClient | None = None


def get_speech_http_client() -> httpx.AsyncClient:
    """Returns shared singleton httpx.AsyncClient for Sarvam and Bhashini."""
    global _speech_http_client
    if _speech_http_client is None or _speech_http_client.is_closed:
        _speech_http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(settings.STT_TIMEOUT_S),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )
    return _speech_http_client


async def close_speech_http_client() -> None:
    """Closes shared speech HTTP client on shutdown."""
    global _speech_http_client
    if _speech_http_client is not None and not _speech_http_client.is_closed:
        await _speech_http_client.aclose()
        _speech_http_client = None
