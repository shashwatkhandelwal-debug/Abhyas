"""Shared Gemini Interactions API helpers for speech providers (spec/06 §6.2, §6.3).

Request/response shapes follow https://ai.google.dev/gemini-api/docs/audio,
https://ai.google.dev/gemini-api/docs/speech-generation and the Interaction
resource reference (https://ai.google.dev/api/interactions-api):
POST {base}/interactions with header x-goog-api-key; the response holds
``steps[]`` whose ``model_output`` steps carry ``content[]`` items of type
"text" (field ``text``) or "audio" (fields ``data``, ``mime_type``).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

logger = logging.getLogger("abhyas.speech.gemini")


async def post_interaction(
    client: httpx.AsyncClient,
    *,
    base_url: str,
    api_key: str,
    payload: dict[str, Any],
    timeout_s: float,
    label: str,
    error_cls: type[Exception],
) -> dict[str, Any]:
    """POSTs one Interactions request; retries once on timeout/network/5xx.

    Any other HTTP error (401/402/403/429 included) raises ``error_cls``
    immediately so a fallback provider can take over. The API key is only
    ever placed in the request header and never logged.
    """
    url = f"{base_url.rstrip('/')}/interactions"
    headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}

    max_retries = 1
    last_error: str = "unknown error"
    for attempt in range(max_retries + 1):
        try:
            response = await client.post(url, headers=headers, json=payload, timeout=timeout_s)
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            last_error = type(exc).__name__
        else:
            if response.status_code < 400:
                try:
                    body = response.json()
                except ValueError as exc:
                    raise error_cls(f"{label} returned invalid JSON") from exc
                if not isinstance(body, dict):
                    raise error_cls(f"{label} returned unexpected JSON")
                return body
            last_error = f"HTTP {response.status_code}"
            if response.status_code < 500:
                raise error_cls(f"{label} failed: {last_error}")

        if attempt < max_retries:
            logger.warning("%s attempt %d failed (%s), retrying...", label, attempt + 1, last_error)
            await asyncio.sleep(0.5)

    raise error_cls(f"{label} failed after retry: {last_error}")


def model_output_items(body: dict[str, Any], content_type: str) -> list[dict[str, Any]]:
    """Returns content items of ``content_type`` from all ``model_output`` steps, in order."""
    items: list[dict[str, Any]] = []
    steps = body.get("steps")
    if not isinstance(steps, list):
        return items
    for step in steps:
        if not isinstance(step, dict) or step.get("type") != "model_output":
            continue
        content = step.get("content")
        if not isinstance(content, list):
            continue
        items.extend(
            item for item in content if isinstance(item, dict) and item.get("type") == content_type
        )
    return items


__all__ = ["post_interaction", "model_output_items"]
