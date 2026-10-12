"""Unit tests for Bhashini STT and TTS providers via ULCA pipeline API (spec/06 §6.2, §6.3)."""

import base64
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
import respx

from backend.app.config import settings
from backend.app.speech.stt import (
    BhashiniSTT,
    ProviderNotConfigured,
    get_stt_provider,
)
from backend.app.speech.tts import (
    BhashiniTTS,
    TTSUnavailable,
    get_tts_provider,
)
from backend.app.speech.voices import get_voice

FIXTURES_DIR = Path(__file__).parents[1] / "fixtures" / "audio"


@pytest.fixture
def wav_5s() -> bytes:
    file = FIXTURES_DIR / "sample_5s.wav"
    assert file.is_file(), f"Fixture missing: {file}"
    return file.read_bytes()


def test_bhashini_stt_missing_key_raises() -> None:
    """BhashiniSTT raises ProviderNotConfigured when BHASHINI_API_KEY is not set."""
    with patch.object(settings, "BHASHINI_API_KEY", ""):
        with pytest.raises(ProviderNotConfigured):
            BhashiniSTT(api_key="")


def test_bhashini_tts_missing_key_raises() -> None:
    """BhashiniTTS raises TTSUnavailable when BHASHINI_API_KEY is not set."""
    with patch.object(settings, "BHASHINI_API_KEY", ""):
        with pytest.raises(TTSUnavailable):
            BhashiniTTS(api_key="")


@pytest.mark.asyncio
@respx.mock
async def test_bhashini_stt_success(wav_5s: bytes) -> None:
    """BhashiniSTT calls ULCA pipeline ASR endpoint and returns normalized transcript."""
    respx.post("https://dhruva-api.bhashini.gov.in/services/inference/pipeline").mock(
        return_value=httpx.Response(
            200,
            json={
                "pipelineResponse": [
                    {
                        "taskType": "asr",
                        "output": [{"source": "रवि, 52 में से 17 कैसे घटाया?"}],
                    }
                ]
            },
        )
    )

    stt = BhashiniSTT(api_key="test-bhashini-key", user_id="test-user")
    transcript = await stt.transcribe(wav_5s, lang="hi-IN")

    assert transcript.provider == "bhashini"
    assert transcript.text == "रवि, 52 में से 17 कैसे घटाया?"
    assert transcript.confidence == 0.9
    assert transcript.ms >= 0


@pytest.mark.asyncio
@respx.mock
async def test_bhashini_tts_success(wav_5s: bytes) -> None:
    """BhashiniTTS calls ULCA pipeline TTS endpoint and returns WAV audio."""
    b64_audio = base64.b64encode(wav_5s).decode("utf-8")

    respx.post("https://dhruva-api.bhashini.gov.in/services/inference/pipeline").mock(
        return_value=httpx.Response(
            200,
            json={
                "pipelineResponse": [
                    {
                        "taskType": "tts",
                        "audio": [{"audioContent": b64_audio}],
                    }
                ]
            },
        )
    )

    tts = BhashiniTTS(api_key="test-bhashini-key", user_id="test-user")
    voice = get_voice("abhyas")
    result_wav, cache_key = await tts.synthesize("नमस्ते_भाषिनी", voice)

    assert result_wav.startswith(b"RIFF")
    assert len(result_wav) == len(wav_5s)
    assert len(cache_key) == 64


def test_get_stt_provider_bhashini() -> None:
    """get_stt_provider returns BhashiniSTT when STT_PROVIDER=bhashini with key."""
    with (
        patch.object(settings, "STT_PROVIDER", "bhashini"),
        patch.object(settings, "BHASHINI_API_KEY", "valid-key"),
    ):
        provider = get_stt_provider()
        assert isinstance(provider, BhashiniSTT)


def test_get_tts_provider_bhashini() -> None:
    """get_tts_provider returns BhashiniTTS when TTS_PROVIDER=bhashini with key."""
    with (
        patch.object(settings, "TTS_PROVIDER", "bhashini"),
        patch.object(settings, "BHASHINI_API_KEY", "valid-key"),
    ):
        provider = get_tts_provider()
        assert isinstance(provider, BhashiniTTS)
