"""Unit tests for Speech-to-Text (STT) providers and MockSTT (spec/06 §6.2, T16)."""

from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
import respx

from backend.app.config import settings
from backend.app.speech.stt import (
    BhashiniSTT,
    GoogleSTT,
    MockSTT,
    ProviderNotConfigured,
    SarvamSTT,
    STTUnavailable,
    calculate_confidence,
    get_stt_provider,
    normalize_transcript_text,
)

FIXTURES_DIR = Path(__file__).parents[1] / "fixtures" / "audio"


@pytest.fixture
def wav_5s() -> bytes:
    file = FIXTURES_DIR / "sample_5s.wav"
    assert file.is_file(), f"Fixture missing: {file}"
    return file.read_bytes()


@pytest.fixture
def wav_60s() -> bytes:
    file = FIXTURES_DIR / "sample_60s.wav"
    assert file.is_file(), f"Fixture missing: {file}"
    return file.read_bytes()


def test_normalize_transcript_text() -> None:
    """normalize_transcript_text ensures NFC normalization and whitespace collapse."""
    # Decomposed vs precomposed Devanagari (NFD vs NFC)
    nfd_text = "क\u093c"  # क़ in NFD
    norm = normalize_transcript_text(f"  {nfd_text}   \n  घटाव   45  ")
    assert norm == "क़ घटाव 45"
    assert unicodedata_is_nfc(norm)


def unicodedata_is_nfc(text: str) -> bool:
    import unicodedata

    return unicodedata.normalize("NFC", text) == text


def test_calculate_confidence() -> None:
    """calculate_confidence awards 0.9 for non-empty Devanagari/Latin, else 0.0."""
    assert calculate_confidence("") == 0.0
    assert calculate_confidence("   ") == 0.0
    assert calculate_confidence("123 45") == 0.0
    assert calculate_confidence("नमस्ते") == 0.9
    assert calculate_confidence("Hello") == 0.9
    # Explicit provider probability overrides heuristic
    assert calculate_confidence("नमस्ते", returned_confidence=0.85) == 0.85


@pytest.mark.asyncio
async def test_mock_stt(wav_5s: bytes) -> None:
    """MockSTT returns fixture text or MOCK_STT_TEXT default."""
    mock_stt = MockSTT(fixtures_dir=FIXTURES_DIR)
    transcript = await mock_stt.transcribe(wav_5s)

    assert transcript.provider == "mock"
    assert "रवि" in transcript.text
    assert transcript.confidence == 0.9
    assert transcript.language == "hi-IN"


@pytest.mark.asyncio
@respx.mock
async def test_sarvam_stt_success(wav_5s: bytes) -> None:
    """SarvamSTT successfully transcribes audio clip via API."""
    respx.post("https://api.sarvam.ai/speech-to-text").mock(
        return_value=httpx.Response(
            200,
            json={
                "transcript": "रवि, 52 में से 17 कैसे घटाया?",
                "language_probability": 0.95,
            },
        )
    )

    stt = SarvamSTT(api_key="test-sarvam-key")
    transcript = await stt.transcribe(
        wav_5s,
        lang="hi-IN",
        keyterms=["रवि", "घटाव"],
    )

    assert transcript.provider == "sarvam"
    assert transcript.text == "रवि, 52 में से 17 कैसे घटाया?"
    assert transcript.confidence == 0.95
    assert transcript.ms >= 0


@pytest.mark.asyncio
@respx.mock
async def test_sarvam_stt_retry_on_500(wav_5s: bytes) -> None:
    """SarvamSTT retries on 500 server error and succeeds on retry."""
    route = respx.post("https://api.sarvam.ai/speech-to-text")
    route.side_effect = [
        httpx.Response(500, text="Internal server error"),
        httpx.Response(200, json={"transcript": "तीली और बंडल"}),
    ]

    stt = SarvamSTT(api_key="test-sarvam-key")
    transcript = await stt.transcribe(wav_5s)

    assert transcript.text == "तीली और बंडल"
    assert route.call_count == 2


@pytest.mark.asyncio
@respx.mock
async def test_sarvam_stt_failure_after_retries(wav_5s: bytes) -> None:
    """SarvamSTT raises STTUnavailable after retrying."""
    respx.post("https://api.sarvam.ai/speech-to-text").mock(
        return_value=httpx.Response(503, text="Service Unavailable")
    )

    stt = SarvamSTT(api_key="test-sarvam-key")
    with pytest.raises(STTUnavailable):
        await stt.transcribe(wav_5s)


@pytest.mark.asyncio
@respx.mock
async def test_sarvam_stt_splits_long_audio(wav_60s: bytes) -> None:
    """SarvamSTT splits clips > 25s and calls API in parallel."""
    route = respx.post("https://api.sarvam.ai/speech-to-text")
    route.mock(
        return_value=httpx.Response(
            200,
            json={"transcript": "भाग एक"},
        )
    )

    stt = SarvamSTT(api_key="test-sarvam-key")
    transcript = await stt.transcribe(wav_60s)

    # 60s audio splits into >= 3 chunks
    assert route.call_count >= 3
    assert "भाग एक" in transcript.text


def test_bhashini_stub_unconfigured() -> None:
    """BhashiniSTT raises ProviderNotConfigured when key missing."""
    with patch.object(settings, "BHASHINI_API_KEY", ""):
        with pytest.raises(ProviderNotConfigured):
            BhashiniSTT()


def test_google_stub_unconfigured() -> None:
    """GoogleSTT raises ProviderNotConfigured when credentials missing."""
    with patch.object(settings, "GOOGLE_APPLICATION_CREDENTIALS", ""):
        with pytest.raises(ProviderNotConfigured):
            GoogleSTT()


def test_get_stt_provider_mock() -> None:
    """get_stt_provider returns MockSTT when configured as mock."""
    with patch.object(settings, "STT_PROVIDER", "mock"):
        provider = get_stt_provider()
        assert isinstance(provider, MockSTT)


def test_get_stt_provider_sarvam_fallback_in_dev() -> None:
    """get_stt_provider falls back to MockSTT in dev when Sarvam key is missing."""
    with (
        patch.object(settings, "STT_PROVIDER", "sarvam"),
        patch.object(settings, "SARVAM_API_KEY", ""),
        patch.object(settings, "ENVIRONMENT", "development"),
    ):
        provider = get_stt_provider()
        assert isinstance(provider, MockSTT)


def test_get_stt_provider_sarvam_configured() -> None:
    """get_stt_provider returns SarvamSTT when key is configured."""
    with (
        patch.object(settings, "STT_PROVIDER", "sarvam"),
        patch.object(settings, "SARVAM_API_KEY", "valid-key"),
    ):
        provider = get_stt_provider()
        assert isinstance(provider, SarvamSTT)
