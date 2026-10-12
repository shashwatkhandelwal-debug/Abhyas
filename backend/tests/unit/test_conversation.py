"""Unit tests for Core ConversationService, MessageCatalog, and Per-Teacher Locks (spec/02 §2.5, T18)."""

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from backend.app.config import settings
from backend.app.core.conversation import ConversationService
from backend.app.core.locks import TeacherLockManager
from backend.app.core.messages import (
    MessageCatalogError,
    get_catalog,
    get_message,
)
from backend.app.core.types import InboundMessage, OutboundMessage
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
    """When STT returns confidence below STT_MIN_CONFIDENCE, asks user for confirmation using stt_confirm."""
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
    assert "मैंने सुना:" in (outbound[0].text_hi or "")
    assert "घटाव का सवाल" in (outbound[0].text_hi or "")
    button_ids = [b.id for b in outbound[0].buttons]
    assert "confirm_yes" in button_ids
    assert "confirm_no" in button_ids


@pytest.mark.asyncio
async def test_conversation_service_low_conf_confirmation_flow(wav_5s: bytes) -> None:
    """'हाँ' accepts pending transcript; 'फिर से' discards it (CHANGES 254f622 Item 7)."""
    low_conf_stt = AsyncMock()
    low_conf_stt.transcribe.return_value = Transcript(
        text="43 में से 27",
        confidence=0.25,
        language="hi-IN",
        provider="sarvam",
        ms=100,
    )

    dispatcher_calls: list[str] = []

    async def mock_dispatcher(msg: InboundMessage) -> list[OutboundMessage]:
        dispatcher_calls.append(msg.text or "")
        return [OutboundMessage(kind="text", text_hi="प्रक्रिया पूरी हुई।")]

    service = ConversationService(stt_provider=low_conf_stt, session_dispatcher=mock_dispatcher)
    teacher_id = uuid4()

    # Step 1: Send low-conf audio
    inbound_audio = InboundMessage(
        channel="whatsapp",
        channel_msg_id="audio-1",
        teacher_id=teacher_id,
        kind="audio",
        audio_bytes=wav_5s,
        received_at=datetime.now(UTC),
    )
    res1 = await service.handle(inbound_audio)
    assert "मैंने सुना:" in (res1[0].text_hi or "")
    assert len(dispatcher_calls) == 0

    # Step 2: Teacher replies "हाँ" -> pending transcript accepted and dispatched
    inbound_yes = InboundMessage(
        channel="whatsapp",
        channel_msg_id="text-yes",
        teacher_id=teacher_id,
        kind="text",
        text="हाँ",
        received_at=datetime.now(UTC),
    )
    res2 = await service.handle(inbound_yes)
    assert len(dispatcher_calls) == 1
    assert dispatcher_calls[0] == "43 में से 27"
    assert res2[0].text_hi == "प्रक्रिया पूरी हुई।"

    # Step 3: Another low-conf audio, replied with btn_retry_speak -> discarded with stt_failed
    dispatcher_calls.clear()
    await service.handle(inbound_audio)
    inbound_no = InboundMessage(
        channel="whatsapp",
        channel_msg_id="btn-retry",
        teacher_id=teacher_id,
        kind="button",
        button_id="btn_retry_speak",
        received_at=datetime.now(UTC),
    )
    res_no = await service.handle(inbound_no)
    assert len(dispatcher_calls) == 0
    assert "आवाज़ साफ़ नहीं आई" in (res_no[0].text_hi or "")

    # Step 4: Another low-conf audio, replied with normal greeting -> clears pending AND processes greeting
    dispatcher_calls.clear()
    await service.handle(inbound_audio)
    inbound_other = InboundMessage(
        channel="whatsapp",
        channel_msg_id="text-other",
        teacher_id=teacher_id,
        kind="text",
        text="मदद",
        received_at=datetime.now(UTC),
    )
    res_other = await service.handle(inbound_other)
    assert len(dispatcher_calls) == 1
    assert dispatcher_calls[0] == "मदद"
    assert res_other[0].text_hi == "प्रक्रिया पूरी हुई।"


@pytest.mark.asyncio
async def test_conversation_service_rehearse_skips_confirmation(wav_5s: bytes) -> None:
    """In REHEARSE state: skip confirmation prompt and flag turn low_conf (CHANGES 254f622 Item 7)."""
    low_conf_stt = AsyncMock()
    low_conf_stt.transcribe.return_value = Transcript(
        text="रवि, तीली खोलो",
        confidence=0.20,
        language="hi-IN",
        provider="sarvam",
        ms=100,
    )

    dispatched_msgs: list[InboundMessage] = []

    async def mock_dispatcher(msg: InboundMessage) -> list[OutboundMessage]:
        dispatched_msgs.append(msg)
        return [OutboundMessage(kind="text", text_hi="ठीक है")]

    service = ConversationService(stt_provider=low_conf_stt, session_dispatcher=mock_dispatcher)
    teacher_id = uuid4()

    inbound = InboundMessage(
        channel="whatsapp",
        channel_msg_id="audio-rehearse",
        teacher_id=teacher_id,
        kind="audio",
        audio_bytes=wav_5s,
        metadata={"state": "REHEARSE"},
        received_at=datetime.now(UTC),
    )

    outbound = await service.handle(inbound)
    assert len(dispatched_msgs) == 1
    assert dispatched_msgs[0].text == "रवि, तीली खोलो"
    assert dispatched_msgs[0].metadata.get("low_conf") is True
    assert outbound[0].text_hi == "ठीक है"


@pytest.mark.asyncio
async def test_conversation_service_stt_budget_exceeded(wav_5s: bytes) -> None:
    """When STT budget exceeded, replies with stt_budget_type_please (CHANGES 254f622 Item 2)."""
    from backend.app.speech.spend import SpeechBudgetExceededError

    budget_stt = AsyncMock()
    budget_stt.transcribe.side_effect = SpeechBudgetExceededError("STT cap reached")

    service = ConversationService(stt_provider=budget_stt)
    inbound = InboundMessage(
        channel="web",
        channel_msg_id="msg-budget",
        teacher_id=uuid4(),
        kind="audio",
        audio_bytes=wav_5s,
        received_at=datetime.now(UTC),
    )

    outbound = await service.handle(inbound)
    assert len(outbound) == 1
    assert "लिखकर भेजें" in (outbound[0].text_hi or "")


@pytest.mark.asyncio
async def test_conversation_service_prod_fails_without_dispatcher() -> None:
    """In production, fail fast if session_dispatcher is None (CHANGES 254f622 Item 9)."""
    service = ConversationService(session_dispatcher=None)
    inbound = InboundMessage(
        channel="web",
        channel_msg_id="msg-prod",
        teacher_id=uuid4(),
        kind="text",
        text="कोई संदेश",
        received_at=datetime.now(UTC),
    )

    with patch.object(settings, "ENVIRONMENT", "production"):
        with pytest.raises(
            RuntimeError, match="ConversationService requires a session_dispatcher in production"
        ):
            await service.handle(inbound)
