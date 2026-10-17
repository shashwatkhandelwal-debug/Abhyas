"""Unit tests for WhatsApp channel, client, media, templates, and 24-hour window (spec/07 §7.2)."""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx

from backend.app.channels.whatsapp.channel import WhatsAppChannel
from backend.app.channels.whatsapp.client import WhatsAppClient
from backend.app.channels.whatsapp.media import (
    clear_whatsapp_media_cache,
    download_whatsapp_media,
    get_cached_whatsapp_media_id,
    upload_whatsapp_media,
)
from backend.app.channels.whatsapp.security import verify_whatsapp_signature
from backend.app.channels.whatsapp.templates import (
    build_template_payload,
    is_template_approved,
    load_whatsapp_templates,
)
from backend.app.config import settings
from backend.app.core.types import OutboundMessage
from backend.app.db.models import Teacher, TeacherContact
from backend.app.privacy.hashing import (
    decrypt_phone_number,
    encrypt_phone_number,
    hash_phone_number,
    normalize_phone_number,
)
from backend.app.sessions.window import is_within_24h_window

# ── 1. Phone Hashing and Normalization Tests ───────────────────────────────


def test_normalize_phone_number() -> None:
    assert normalize_phone_number("9876543210") == "+919876543210"
    assert normalize_phone_number("919876543210") == "+919876543210"
    assert normalize_phone_number("+919876543210") == "+919876543210"
    assert normalize_phone_number("+1 (555) 123-4567") == "+15551234567"


def test_hash_phone_number_is_salted_and_deterministic() -> None:
    raw = "+919876543210"
    h1 = hash_phone_number(raw)
    h2 = hash_phone_number(raw)
    assert h1 == h2
    assert len(h1) == 64
    # Ensure salt is actually applied
    raw_unsalted = hashlib.sha256(raw.encode()).hexdigest()
    assert h1 != raw_unsalted


def test_phone_fernet_encryption_roundtrip() -> None:
    raw = "+919876543210"
    encrypted = encrypt_phone_number(raw)
    assert isinstance(encrypted, bytes)
    assert raw.encode() not in encrypted  # Ciphertext hides plaintext
    decrypted = decrypt_phone_number(encrypted)
    assert decrypted == raw


# ── 2. 24-Hour Service Window Tests ─────────────────────────────────────────


def test_is_within_24h_window_active() -> None:
    now = datetime.now(UTC)
    last_inbound = now - timedelta(hours=2)
    assert is_within_24h_window(last_inbound, now=now) is True

    # Exactly 23h 59m ago
    last_inbound_edge = now - timedelta(hours=23, minutes=59)
    assert is_within_24h_window(last_inbound_edge, now=now) is True


def test_is_within_24h_window_expired() -> None:
    now = datetime.now(UTC)
    last_inbound = now - timedelta(hours=25)
    assert is_within_24h_window(last_inbound, now=now) is False

    # None inbound timestamp is outside window
    assert is_within_24h_window(None, now=now) is False


# ── 3. Template Catalog and Approval Tests ──────────────────────────────────


def test_load_whatsapp_templates() -> None:
    templates = load_whatsapp_templates()
    assert "abhyas_weekly_move" in templates
    assert "abhyas_reminder" in templates
    assert "abhyas_followup_question" in templates


def test_is_template_approved_flag() -> None:
    # Seed templates start as approved: false
    assert is_template_approved("abhyas_weekly_move") is False

    # Mock an approved template
    templates = load_whatsapp_templates()
    templates["mock_approved"] = {"name": "mock_approved", "approved": True}
    assert is_template_approved("mock_approved") is True


def test_build_template_payload() -> None:
    payload = build_template_payload(
        template_name="abhyas_weekly_move",
        parameters=["सुनीता", "हासिल वाला घटाव"],
        language_code="hi",
    )
    assert payload["name"] == "abhyas_weekly_move"
    assert payload["language"]["code"] == "hi"
    assert len(payload["components"][0]["parameters"]) == 2
    assert payload["components"][0]["parameters"][0]["text"] == "सुनीता"


# ── 4. Webhook Signature Verification Tests ─────────────────────────────────


def test_verify_whatsapp_signature(monkeypatch: pytest.MonkeyPatch) -> None:
    secret = "test_webhook_app_secret_12345"
    monkeypatch.setattr(settings, "WHATSAPP_APP_SECRET", secret)

    body = b'{"object": "whatsapp_business_account"}'
    valid_sig = f"sha256={hashlib.sha256(secret.encode() + body).hexdigest()}"  # Wrong digest
    assert verify_whatsapp_signature(body, valid_sig) is False

    import hmac

    correct_hex = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    correct_sig = f"sha256={correct_hex}"
    assert verify_whatsapp_signature(body, correct_sig) is True

    # Bad header formats
    assert verify_whatsapp_signature(body, "") is False
    assert verify_whatsapp_signature(body, "invalid_no_sha") is False
    assert verify_whatsapp_signature(body, None) is False


# ── 5. Media Upload / Download and Caching Tests ─────────────────────────────


@pytest.mark.asyncio
async def test_media_cache_ttl() -> None:
    clear_whatsapp_media_cache()
    key = "test_cache_key_001"
    assert get_cached_whatsapp_media_id(key) is None

    # Upload in mock mode populates cache
    media_id = await upload_whatsapp_media(b"test_audio_bytes", cache_key=key)
    assert media_id.startswith("mock_media_")
    assert get_cached_whatsapp_media_id(key) == media_id


@pytest.mark.asyncio
@respx.mock
async def test_media_download_live_and_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "WHATSAPP_ENABLED", True)
    monkeypatch.setattr(settings, "WHATSAPP_ACCESS_TOKEN", "EAAtesttoken123")
    monkeypatch.setattr(settings, "WHATSAPP_GRAPH_VERSION", "v23.0")

    meta_route = respx.get("https://graph.facebook.com/v23.0/media_123").respond(
        status_code=200,
        json={"url": "https://lookaside.fbsbx.com/test_audio.ogg", "file_size": 2048},
    )
    dl_route = respx.get("https://lookaside.fbsbx.com/test_audio.ogg").respond(
        status_code=200,
        content=b"OGG_TEST_AUDIO_STREAM_DATA",
    )

    data = await download_whatsapp_media("media_123")
    assert data == b"OGG_TEST_AUDIO_STREAM_DATA"
    assert meta_route.called
    assert dl_route.called


# ── 6. WhatsAppClient Graph API Calls (respx mocked) ─────────────────────────


@pytest.mark.asyncio
@respx.mock
async def test_client_send_text_message(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "WHATSAPP_ENABLED", True)
    monkeypatch.setattr(settings, "WHATSAPP_ACCESS_TOKEN", "EAAtesttoken123")
    monkeypatch.setattr(settings, "WHATSAPP_PHONE_NUMBER_ID", "phone_id_999")
    monkeypatch.setattr(settings, "WHATSAPP_GRAPH_VERSION", "v23.0")

    route = respx.post("https://graph.facebook.com/v23.0/phone_id_999/messages").respond(
        status_code=200,
        json={"messages": [{"id": "wamid.HBgL"}]},
    )

    client = WhatsAppClient()
    res = await client.send_text("+919876543210", "नमस्ते शिक्षक जी")
    assert res["messages"][0]["id"] == "wamid.HBgL"
    assert route.called
    sent_json = route.calls.last.request.read()
    assert b"messaging_product" in sent_json
    assert b"text" in sent_json


@pytest.mark.asyncio
@respx.mock
async def test_client_send_interactive_buttons(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "WHATSAPP_ENABLED", True)
    monkeypatch.setattr(settings, "WHATSAPP_ACCESS_TOKEN", "EAAtesttoken123")
    monkeypatch.setattr(settings, "WHATSAPP_PHONE_NUMBER_ID", "phone_id_999")
    monkeypatch.setattr(settings, "WHATSAPP_GRAPH_VERSION", "v23.0")

    route = respx.post("https://graph.facebook.com/v23.0/phone_id_999/messages").respond(
        status_code=200,
        json={"messages": [{"id": "wamid.HBgL_btn"}]},
    )

    client = WhatsAppClient()
    res = await client.send_interactive_buttons(
        to_e164="+919876543210",
        body_text="आगे क्या करना चाहेंगे?",
        buttons=[("btn_retry", "फिर से"), ("btn_next", "आगे बढ़ें")],
    )
    assert res["messages"][0]["id"] == "wamid.HBgL_btn"
    assert route.called
    sent_json = route.calls.last.request.read()
    assert b"interactive" in sent_json
    assert b"btn_retry" in sent_json


@pytest.mark.asyncio
@respx.mock
async def test_client_exponential_retry_on_503(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "WHATSAPP_ENABLED", True)
    monkeypatch.setattr(settings, "WHATSAPP_ACCESS_TOKEN", "EAAtesttoken123")
    monkeypatch.setattr(settings, "WHATSAPP_PHONE_NUMBER_ID", "phone_id_999")
    monkeypatch.setattr(settings, "WHATSAPP_GRAPH_VERSION", "v23.0")

    # Fast-forward retry delays for unit test
    with patch("backend.app.channels.whatsapp.client.RETRY_DELAYS", (0.01, 0.02, 0.03)):
        # First 2 attempts return 503, third attempt succeeds
        route = respx.post("https://graph.facebook.com/v23.0/phone_id_999/messages").mock(
            side_effect=[
                httpx.Response(503, text="Service Unavailable"),
                httpx.Response(503, text="Service Unavailable"),
                httpx.Response(200, json={"messages": [{"id": "wamid.retry_success"}]}),
            ]
        )

        client = WhatsAppClient()
        res = await client.send_text("+919876543210", "पुनः प्रयास")
        assert res["messages"][0]["id"] == "wamid.retry_success"
        assert route.call_count == 3


# ── 7. WhatsAppChannel Protocol & Window Logic Tests ────────────────────────


@pytest.mark.asyncio
async def test_whatsapp_channel_protocol_conformance() -> None:
    channel = WhatsAppChannel()
    assert channel.name == "whatsapp"
    assert hasattr(channel, "send")
    assert hasattr(channel, "can_send_freeform")


@pytest.mark.asyncio
async def test_whatsapp_channel_outside_window_unapproved_template_skipped() -> None:
    channel = WhatsAppChannel()
    now = datetime.now(UTC)

    teacher = Teacher(
        id=uuid.uuid4(),
        phone_hash=hash_phone_number("+919876543210"),
        preferred_channel="whatsapp",
        last_inbound_at=now - timedelta(hours=30),  # > 24h expired
    )

    outbound = OutboundMessage(
        kind="text",
        text_hi="यह संदेश बाहर है",
        template_name="abhyas_unapproved_mock",  # Not approved in catalog
    )

    # Mock DB session and TeacherContact
    fake_session = AsyncMock()
    from unittest.mock import MagicMock

    mock_result = MagicMock()
    contact = TeacherContact(
        teacher_id=teacher.id,
        phone_enc=encrypt_phone_number("+919876543210"),
    )
    mock_result.scalar_one_or_none.return_value = contact
    fake_session.execute.return_value = mock_result

    with patch("backend.app.channels.whatsapp.channel.whatsapp_client.send_template") as mock_send:
        await channel.send(teacher, [outbound], session=fake_session)
        # Should NOT dispatch unapproved template outside window
        assert not mock_send.called
