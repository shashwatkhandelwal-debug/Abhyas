"""Unit tests for WhatsApp webhook endpoint security and routing (§11)."""

import hashlib
import hmac
import json
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from backend.app.config import settings
from backend.app.whatsapp.router import router as whatsapp_router


@pytest.fixture
def whatsapp_app() -> FastAPI:
    app = FastAPI()
    app.include_router(whatsapp_router)
    return app


def _sign_payload(payload_bytes: bytes, secret: str) -> str:
    sig = hmac.new(
        key=secret.encode("utf-8"),
        msg=payload_bytes,
        digestmod=hashlib.sha256,
    ).hexdigest()
    return f"sha256={sig}"


@pytest.mark.asyncio
async def test_get_webhook_verify_disabled_returns_404(
    whatsapp_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When WHATSAPP_ENABLED is False, GET /whatsapp/webhook must return 404."""
    monkeypatch.setattr(settings, "WHATSAPP_ENABLED", False)
    async with AsyncClient(
        transport=ASGITransport(app=whatsapp_app), base_url="http://test"
    ) as client:
        resp = await client.get(
            "/whatsapp/webhook",
            params={"hub.mode": "subscribe", "hub.verify_token": "token", "hub.challenge": "123"},
        )
        assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_webhook_verify_empty_verify_token_rejected(
    whatsapp_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When WHATSAPP_VERIFY_TOKEN is empty, GET verification must reject with 403."""
    monkeypatch.setattr(settings, "WHATSAPP_ENABLED", True)
    monkeypatch.setattr(settings, "WHATSAPP_VERIFY_TOKEN", "")
    async with AsyncClient(
        transport=ASGITransport(app=whatsapp_app), base_url="http://test"
    ) as client:
        resp = await client.get(
            "/whatsapp/webhook",
            params={"hub.mode": "subscribe", "hub.verify_token": "", "hub.challenge": "123"},
        )
        assert resp.status_code == 403


@pytest.mark.asyncio
async def test_get_webhook_verify_success(
    whatsapp_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When valid verify token and subscribe mode are passed, returns hub.challenge."""
    monkeypatch.setattr(settings, "WHATSAPP_ENABLED", True)
    monkeypatch.setattr(settings, "WHATSAPP_VERIFY_TOKEN", "valid_verify_token_123")
    async with AsyncClient(
        transport=ASGITransport(app=whatsapp_app), base_url="http://test"
    ) as client:
        resp = await client.get(
            "/whatsapp/webhook",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "valid_verify_token_123",
                "hub.challenge": "challenge_response_456",
            },
        )
        assert resp.status_code == 200
        assert resp.text == "challenge_response_456"


@pytest.mark.asyncio
async def test_get_webhook_verify_token_mismatch_returns_403(
    whatsapp_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When verify token mismatches, returns 403 Forbidden."""
    monkeypatch.setattr(settings, "WHATSAPP_ENABLED", True)
    monkeypatch.setattr(settings, "WHATSAPP_VERIFY_TOKEN", "valid_verify_token_123")
    async with AsyncClient(
        transport=ASGITransport(app=whatsapp_app), base_url="http://test"
    ) as client:
        resp = await client.get(
            "/whatsapp/webhook",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "wrong_token",
                "hub.challenge": "123",
            },
        )
        assert resp.status_code == 403


@pytest.mark.asyncio
async def test_post_webhook_disabled_returns_404(
    whatsapp_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When WHATSAPP_ENABLED is False, POST /whatsapp/webhook must return 404."""
    monkeypatch.setattr(settings, "WHATSAPP_ENABLED", False)
    async with AsyncClient(
        transport=ASGITransport(app=whatsapp_app), base_url="http://test"
    ) as client:
        resp = await client.post("/whatsapp/webhook", json={"entry": []})
        assert resp.status_code == 404


@pytest.mark.asyncio
async def test_post_webhook_empty_app_secret_returns_503(
    whatsapp_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When WHATSAPP_APP_SECRET is empty, POST /whatsapp/webhook must return 503."""
    monkeypatch.setattr(settings, "WHATSAPP_ENABLED", True)
    monkeypatch.setattr(settings, "WHATSAPP_APP_SECRET", "")
    async with AsyncClient(
        transport=ASGITransport(app=whatsapp_app), base_url="http://test"
    ) as client:
        resp = await client.post("/whatsapp/webhook", json={"entry": []})
        assert resp.status_code == 503


@pytest.mark.asyncio
async def test_post_webhook_forged_body_signed_with_empty_key_returns_401(
    whatsapp_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A forged body signed with an empty key must be rejected with 401."""
    monkeypatch.setattr(settings, "WHATSAPP_ENABLED", True)
    monkeypatch.setattr(settings, "WHATSAPP_APP_SECRET", "super-secret-key-1234")

    payload_data: dict[str, Any] = {"entry": []}
    body_bytes = json.dumps(payload_data).encode("utf-8")
    forged_sig = _sign_payload(body_bytes, "")

    async with AsyncClient(
        transport=ASGITransport(app=whatsapp_app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/whatsapp/webhook",
            content=body_bytes,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": forged_sig,
            },
        )
        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_post_webhook_missing_or_invalid_signature_returns_401(
    whatsapp_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Missing or corrupted signature returns 401."""
    monkeypatch.setattr(settings, "WHATSAPP_ENABLED", True)
    monkeypatch.setattr(settings, "WHATSAPP_APP_SECRET", "super-secret-key-1234")

    body_bytes = b'{"entry": []}'

    async with AsyncClient(
        transport=ASGITransport(app=whatsapp_app), base_url="http://test"
    ) as client:
        # Missing header
        resp1 = await client.post(
            "/whatsapp/webhook",
            content=body_bytes,
            headers={"Content-Type": "application/json"},
        )
        assert resp1.status_code == 401

        # Corrupted signature header
        resp2 = await client.post(
            "/whatsapp/webhook",
            content=body_bytes,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": "sha256=invalidhex",
            },
        )
        assert resp2.status_code == 401


@pytest.mark.asyncio
async def test_post_webhook_valid_signature_success(
    whatsapp_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Properly signed payload is processed and accepted."""
    secret = "production-grade-test-secret-999"
    monkeypatch.setattr(settings, "WHATSAPP_ENABLED", True)
    monkeypatch.setattr(settings, "WHATSAPP_APP_SECRET", secret)

    sample_payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "123456",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "1234567890",
                                "phone_number_id": "0987654321",
                            },
                            "messages": [
                                {
                                    "from": "919876543210",
                                    "id": "wamid.test.001",
                                    "timestamp": "1700000000",
                                    "type": "text",
                                    "text": {"body": "नमस्ते"},
                                }
                            ],
                        },
                        "field": "messages",
                    }
                ],
            }
        ],
    }
    body_bytes = json.dumps(sample_payload).encode("utf-8")
    valid_sig = _sign_payload(body_bytes, secret)

    with patch(
        "backend.app.channels.whatsapp.webhook._dispatch_inbound_message",
        new_callable=AsyncMock,
    ) as mock_dispatch:
        async with AsyncClient(
            transport=ASGITransport(app=whatsapp_app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/whatsapp/webhook",
                content=body_bytes,
                headers={
                    "Content-Type": "application/json",
                    "X-Hub-Signature-256": valid_sig,
                },
            )
            assert resp.status_code == 200
            assert resp.json() == {"status": "ok"}
            mock_dispatch.assert_called_once()
