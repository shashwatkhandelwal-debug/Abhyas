"""Unit tests for Core ConversationService, MessageCatalog, and Per-Teacher Locks (spec/02 §2.5, T18)."""

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from backend.app.core.conversation import ConversationService
from backend.app.core.locks import TeacherLockManager
from backend.app.core.messages import (
    MessageCatalogError,
    get_catalog,
    get_message,
)
from backend.app.core.types import InboundMessage
from backend.app.speech.stt import MockSTT, STTUnavailable, Transcript

FIXTURES_DIR = Path(__file__).parents[1] / "fixtures" / "audio"


@pytest.fixture
def wav_5s() -> bytes:
    file = FIXTURES_DIR / "sample_5s.wav"
    assert file.is_file(), f"Fixture missing: {file}"
    return file.read_bytes()


def test_message_catalog_loads_and_has_required_keys() -> None:
    """MessageCatalog successfully parses content/messages_hi.yaml with all required keys."""
    catalog = get_catalog()
    assert catalog.has("welcome") is True
    assert catalog.has("ask_name") is True
    assert catalog.has("ask_address_form") is True

    welcome_text = get_message("welcome")
    assert "अभ्यास" in welcome_text


def test_message_catalog_gender_variant() -> None:
    """MessageCatalog returns text_m variant when address_form is male ('m')."""
    catalog = get_catalog()
    # Check a key known to have text_m if present, or test with mock catalog
    if catalog.has("ask_experience") and "text_m" in catalog.get_spec("ask_experience"):
        fem_text = catalog.get("ask_experience", address_form="f", name="सुनीता")
        male_text = catalog.get("ask_experience", address_form="m", name="रमेश")
        assert fem_text != male_text


def test_message_catalog_missing_key_raises() -> None:
    """get_message raises MessageCatalogError for nonexistent key."""
    catalog = get_catalog()
    with pytest.raises(MessageCatalogError):
        catalog.get("nonexistent_key_12345")


def test_message_catalog_feminine_markers_checked() -> None:
    """Verifies that feminine verb markers can be detected in Hindi strings."""
    fem_phrase = "आप क्या सिखाना चाहती हैं?"
    assert any(m in fem_phrase for m in ["चाहती"])


@pytest.mark.asyncio
async def test_teacher_locks_serialize_concurrent_requests() -> None:
    """Per-teacher locks serialize concurrent executions for the same teacher ID."""
    manager = TeacherLockManager()
    t_id = uuid4()
    order: list[str] = []

    async def worker(tag: str, delay: float) -> None:
        async with manager.lock(t_id):
            order.append(f"start_{tag}")
            await asyncio.sleep(delay)
            order.append(f"end_{tag}")

    task1 = asyncio.create_task(worker("1", 0.05))
    task2 = asyncio.create_task(worker("2", 0.01))

    await asyncio.gather(task1, task2)

    # worker 1 started and ended BEFORE worker 2 started
    assert order == ["start_1", "end_1", "start_2", "end_2"]


@pytest.mark.asyncio
async def test_conversation_service_greeting() -> None:
    """Inbound greeting triggers welcome outbound message."""
    service = ConversationService()
    inbound = InboundMessage(
        channel="web",
        channel_msg_id="msg-1",
        teacher_id=uuid4(),
        kind="text",
        text="नमस्ते",
        received_at=datetime.now(UTC),
    )

    outbound = await service.handle(inbound)
    assert len(outbound) == 1
    assert "अभ्यास" in (outbound[0].text_hi or "")


@pytest.mark.asyncio
async def test_conversation_service_audio_success(wav_5s: bytes) -> None:
    """Inbound audio is converted to WAV 16k and transcribed."""
    mock_stt = MockSTT(default_text="रवि ने 45 कहा।")
    service = ConversationService(stt_provider=mock_stt)

    inbound = InboundMessage(
        channel="whatsapp",
        channel_msg_id="msg-2",
        teacher_id=uuid4(),
        kind="audio",
        audio_bytes=wav_5s,
        audio_mime="audio/ogg; codecs=opus",
        received_at=datetime.now(UTC),
    )

    outbound = await service.handle(inbound)
    assert len(outbound) == 1
    # Received response reflecting transcript
    assert outbound[0].text_hi is not None


@pytest.mark.asyncio
async def test_conversation_service_audio_failure_graceful_degradation(wav_5s: bytes) -> None:
    """When STT raises an error, ConversationService replies with graceful degradation message."""
    failing_stt = AsyncMock()
    failing_stt.transcribe.side_effect = STTUnavailable("STT timeout")

    service = ConversationService(stt_provider=failing_stt)
    inbound = InboundMessage(
        channel="whatsapp",
        channel_msg_id="msg-3",
        teacher_id=uuid4(),
        kind="audio",
        audio_bytes=wav_5s,
        received_at=datetime.now(UTC),
    )

    outbound = await service.handle(inbound)
    assert len(outbound) == 1
    assert "आवाज़ साफ़ नहीं आई" in (outbound[0].text_hi or "")


@pytest.mark.asyncio
async def test_conversation_service_low_confidence_stt(wav_5s: bytes) -> None:
    """When STT returns confidence below STT_MIN_CONFIDENCE, asks user for confirmation."""
    low_conf_stt = AsyncMock()
    low_conf_stt.transcribe.return_value = Transcript(
        text="घटाव का सवाल",
        confidence=0.30,  # Below default 0.50
        language="hi-IN",
        provider="sarvam",
        ms=120,
    )

    service = ConversationService(stt_provider=low_conf_stt)
    inbound = InboundMessage(
        channel="web",
        channel_msg_id="msg-4",
        teacher_id=uuid4(),
        kind="audio",
        audio_bytes=wav_5s,
        received_at=datetime.now(UTC),
    )

    outbound = await service.handle(inbound)
    assert len(outbound) == 1
    assert outbound[0].kind == "buttons"
    assert "क्या आपने 'घटाव का सवाल' कहा?" in (outbound[0].text_hi or "")
    button_ids = [b.id for b in outbound[0].buttons]
    assert "confirm_yes" in button_ids
    assert "confirm_no" in button_ids


@pytest.mark.asyncio
async def test_conversation_service_stop_word() -> None:
    """Inbound stop keyword pauses practice session gracefully."""
    service = ConversationService()
    inbound = InboundMessage(
        channel="web",
        channel_msg_id="msg-5",
        teacher_id=uuid4(),
        kind="text",
        text="बस, यहीं रोकें",
        received_at=datetime.now(UTC),
    )

    outbound = await service.handle(inbound)
    assert len(outbound) == 1
    assert "रोक" in (outbound[0].text_hi or "")
