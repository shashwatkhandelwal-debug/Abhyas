"""Unit tests for Text-to-Speech (TTS), voices catalog, caching, and MockTTS (spec/06 §6.3, T17)."""

import base64
import tempfile
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
import respx

from backend.app.config import settings
from backend.app.speech.audio import duration_s
from backend.app.speech.cache import TTSCache, compute_cache_key, tts_cache
from backend.app.speech.tts import (
    MockTTS,
    SarvamTTS,
    TTSUnavailable,
    convert_digits_for_tts,
    get_tts_provider,
    split_sentences_for_tts,
)
from backend.app.speech.voices import (
    VOICE_CATALOG,
    VoiceSpec,
    get_voice,
    load_voices,
)


@pytest.fixture(autouse=True)
def isolate_tts_cache(tmp_path: Path) -> None:
    original_dir = tts_cache.cache_dir
    tts_cache.cache_dir = tmp_path
    yield
    tts_cache.cache_dir = original_dir


def test_convert_digits_for_tts() -> None:
    """convert_digits_for_tts converts numerals to spoken Hindi number words."""
    converted = convert_digits_for_tts("रवि ने 45 कहा। 52 में से 17 घटाओ।")
    assert "पैंतालीस" in converted
    assert "बावन" in converted
    assert "सत्रह" in converted
    assert "45" not in converted
    assert "52" not in converted
    assert "17" not in converted


def test_split_sentences_for_tts() -> None:
    """split_sentences_for_tts breaks scripts at sentence boundaries under limit."""
    short_text = "यह एक छोटा वाक्य है।"
    assert split_sentences_for_tts(short_text, max_chars=100) == [short_text]

    long_text = "पहला वाक्य। " * 50  # ~600 chars
    chunks = split_sentences_for_tts(long_text, max_chars=150)
    assert len(chunks) > 1
    for c in chunks:
        assert len(c) <= 150


def test_voice_catalog() -> None:
    """VOICE_CATALOG contains all spec personas with correct speakers and pitch."""
    assert "abhyas" in VOICE_CATALOG
    assert VOICE_CATALOG["abhyas"].provider_speaker == "ritu"
    assert VOICE_CATALOG["coach"].provider_speaker == "neha"
    assert VOICE_CATALOG["model_teacher"].provider_speaker == "pooja"

    # Child voices have pitch shifting
    assert VOICE_CATALOG["child_ravi"].pitch_factor == 1.22
    assert VOICE_CATALOG["child_priya"].pitch_factor == 1.18
    assert VOICE_CATALOG["child_aman"].pitch_factor == 1.25

    # get_voice returns matching voice or default
    assert get_voice("child_ravi").provider_speaker == "aayan"
    assert get_voice("unknown_xyz").provider_speaker == "ritu"

    # load_voices returns dictionary
    voices = load_voices()
    assert len(voices) >= 6


@pytest.mark.asyncio
async def test_mock_tts_synthesizes_valid_wav() -> None:
    """MockTTS produces valid 22.05 kHz WAV with length proportional to text."""
    mock_tts = MockTTS()
    voice = get_voice("abhyas")

    wav_bytes, ckey = await mock_tts.synthesize("नमस्ते, आज हम घटाव सीखेंगे।", voice)
    assert wav_bytes.startswith(b"RIFF")
    assert len(ckey) == 64
    dur = await duration_s(wav_bytes)
    assert 0.5 <= dur <= 5.0


@pytest.mark.asyncio
async def test_mock_tts_child_pitch_shifted() -> None:
    """MockTTS handles child voices with pitch shift factor."""
    mock_tts = MockTTS()
    voice = get_voice("child_ravi")  # pitch 1.22

    wav_bytes, ckey = await mock_tts.synthesize("पैंतालीस!", voice)
    assert wav_bytes.startswith(b"RIFF")
    dur = await duration_s(wav_bytes)
    assert dur > 0.1


@pytest.mark.asyncio
@respx.mock
async def test_sarvam_tts_success() -> None:
    """SarvamTTS calls API, decodes base64 WAV audio, and returns valid bytes and cache key."""
    # Create minimal 1-second WAV
    mock_tts = MockTTS()
    sample_wav, _ = await mock_tts.synthesize("नमस्ते", get_voice("abhyas"))
    b64_audio = base64.b64encode(sample_wav).decode("utf-8")

    respx.post("https://api.sarvam.ai/text-to-speech").mock(
        return_value=httpx.Response(
            200,
            json={"audios": [b64_audio]},
        )
    )

    tts = SarvamTTS(api_key="test-key")
    voice = VoiceSpec(provider_speaker="ritu", model="bulbul:v3", pace=0.95, pitch_factor=1.0)
    result, ckey = await tts.synthesize("नमस्ते_नया", voice)

    assert result.startswith(b"RIFF")
    assert len(result) == len(sample_wav)
    assert len(ckey) == 64


@pytest.mark.asyncio
@respx.mock
async def test_sarvam_tts_retry_on_500() -> None:
    """SarvamTTS retries on 500 error and recovers."""
    mock_tts = MockTTS()
    sample_wav, _ = await mock_tts.synthesize("नमस्ते", get_voice("abhyas"))
    b64_audio = base64.b64encode(sample_wav).decode("utf-8")

    route = respx.post("https://api.sarvam.ai/text-to-speech")
    route.side_effect = [
        httpx.Response(500, text="Server Error"),
        httpx.Response(200, json={"audios": [b64_audio]}),
    ]

    tts = SarvamTTS(api_key="test-key")
    voice = VoiceSpec(provider_speaker="ritu", model="bulbul:v3")
    result, ckey = await tts.synthesize("नमस्ते_retry", voice)

    assert result.startswith(b"RIFF")
    assert route.call_count == 2


@pytest.mark.asyncio
@respx.mock
async def test_sarvam_tts_failure_after_retries() -> None:
    """SarvamTTS raises TTSUnavailable when API fails after retry."""
    respx.post("https://api.sarvam.ai/text-to-speech").mock(
        return_value=httpx.Response(502, text="Bad Gateway")
    )

    tts = SarvamTTS(api_key="test-key")
    voice = VoiceSpec(provider_speaker="ritu", model="bulbul:v3")
    with pytest.raises(TTSUnavailable):
        await tts.synthesize("अनपेक्षित_त्रुटि_पाठ", voice)


@pytest.mark.asyncio
async def test_tts_cache_operations() -> None:
    """TTSCache computes keys, saves audio formats, and reads from cache."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = TTSCache(cache_dir=tmpdir, use_db=False)
        voice = get_voice("child_ravi")
        text = "रवि ने 45 कहा।"

        key = compute_cache_key(text, "child_ravi", voice)
        assert len(key) == 64  # sha256 hex string

        # Initially empty
        assert await cache.has(key, "wav") is False
        assert await cache.get(key, "wav") is None

        # Put synthetic WAV
        out_io = Path(__file__).parents[1] / "fixtures" / "audio" / "sample_5s.wav"
        wav_bytes = out_io.read_bytes()
        paths = await cache.put_wav(key, wav_bytes)

        assert "wav" in paths
        assert "ogg" in paths
        assert "mp3" in paths

        assert await cache.has(key, "wav") is True
        assert await cache.has(key, "ogg") is True
        assert await cache.has(key, "mp3") is True

        retrieved_wav = await cache.get(key, "wav")
        assert retrieved_wav == wav_bytes


def test_get_tts_provider_mock() -> None:
    """get_tts_provider returns MockTTS when provider is mock."""
    with patch.object(settings, "TTS_PROVIDER", "mock"):
        provider = get_tts_provider()
        assert isinstance(provider, MockTTS)


def test_get_tts_provider_sarvam() -> None:
    """get_tts_provider returns SarvamTTS when configured with key."""
    with (
        patch.object(settings, "TTS_PROVIDER", "sarvam"),
        patch.object(settings, "SARVAM_API_KEY", "test-key"),
    ):
        provider = get_tts_provider()
        assert isinstance(provider, SarvamTTS)
