"""Unit tests for speech cost control, budget tracking, and caching (spec/06 §6.4)."""

import base64
import tempfile
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
import respx

from backend.app.config import settings
from backend.app.speech.cache import TTSCache, compute_cache_key
from backend.app.speech.spend import (
    SpeechBudgetExceededError,
    SpeechBudgetTracker,
    calculate_stt_cost,
    calculate_tts_cost,
    prewarm_fixed_audio,
    speech_budget,
)
from backend.app.speech.stt import SarvamSTT
from backend.app.speech.tts import MockTTS, SarvamTTS
from backend.app.speech.voices import get_voice

FIXTURES_DIR = Path(__file__).parents[1] / "fixtures" / "audio"


@pytest.fixture(autouse=True)
def reset_budget() -> None:
    speech_budget.reset()


@pytest.fixture
def wav_5s() -> bytes:
    file = FIXTURES_DIR / "sample_5s.wav"
    assert file.is_file(), f"Fixture missing: {file}"
    return file.read_bytes()


def test_calculate_stt_cost() -> None:
    """STT cost is billed in 15s increments at configured rate."""
    # 0s or negative -> 0.0
    assert calculate_stt_cost(0.0) == 0.0
    assert calculate_stt_cost(-5.0) == 0.0

    # 5s rounds up to 15s (0.25 min) -> 0.25 * 0.50 = 0.125 INR
    assert calculate_stt_cost(5.0) == 0.125

    # 15s -> 0.125 INR
    assert calculate_stt_cost(15.0) == 0.125

    # 16s rounds up to 30s (0.50 min) -> 0.50 * 0.50 = 0.250 INR
    assert calculate_stt_cost(16.0) == 0.25

    # 60s -> 1.0 min * 0.50 = 0.50 INR
    assert calculate_stt_cost(60.0) == 0.50


def test_calculate_tts_cost() -> None:
    """TTS cost is proportional to character count at configured rate."""
    assert calculate_tts_cost("") == 0.0

    # 1000 characters at 3.0 INR/1000 chars -> 3.0 INR
    text_1000 = "अ" * 1000
    assert calculate_tts_cost(text_1000) == 3.0

    # 100 characters -> 0.30 INR
    text_100 = "अ" * 100
    assert calculate_tts_cost(text_100) == 0.30


@pytest.mark.asyncio
async def test_speech_budget_tracker_limits() -> None:
    """Tracker accurately tracks spend and blocks when caps are reached."""
    tracker = SpeechBudgetTracker()
    assert tracker.daily_spend == 0.0
    assert tracker.total_spend == 0.0

    # Can spend within daily limit
    assert await tracker.can_spend(10.0) is True
    await tracker.record_spend("sarvam", "tts", 100, 10.0)
    assert tracker.daily_spend == 10.0
    assert tracker.total_spend == 10.0

    # Attempting to exceed daily cap (50.0 INR default)
    assert await tracker.can_spend(41.0) is False
    assert await tracker.can_spend(40.0) is True


@pytest.mark.asyncio
async def test_mock_by_default() -> None:
    """SPEECH_PROVIDER_LIVE is False by default; check_and_record incurs 0 cost."""
    assert settings.SPEECH_PROVIDER_LIVE is False
    stt_cost = await speech_budget.check_and_record_stt(30.0)
    assert stt_cost == 0.0
    assert speech_budget.daily_spend == 0.0

    tts_cost = await speech_budget.check_and_record_tts("नमस्ते")
    assert tts_cost == 0.0
    assert speech_budget.daily_spend == 0.0


@pytest.mark.asyncio
@respx.mock
async def test_live_mode_records_spend(wav_5s: bytes) -> None:
    """When SPEECH_PROVIDER_LIVE is True, STT and TTS record real spend."""
    mock_tts = MockTTS()
    sample_res = await mock_tts.synthesize("नमस्ते", get_voice("abhyas"))
    b64_audio = base64.b64encode(sample_res.audio).decode("utf-8")

    respx.post("https://api.sarvam.ai/speech-to-text").mock(
        return_value=httpx.Response(200, json={"transcript": "नमस्ते", "language_probability": 0.9})
    )
    respx.post("https://api.sarvam.ai/text-to-speech").mock(
        return_value=httpx.Response(200, json={"audios": [b64_audio]})
    )

    with (
        patch.object(settings, "SPEECH_PROVIDER_LIVE", True),
        patch.object(
            speech_budget,
            "get_spend_totals_db",
            side_effect=lambda: (speech_budget.daily_spend, speech_budget.total_spend),
        ),
        tempfile.TemporaryDirectory() as tmpdir,
        patch("backend.app.speech.tts.tts_cache", TTSCache(cache_dir=tmpdir, use_db=False)),
    ):
        stt = SarvamSTT(api_key="test-key")
        _ = await stt.transcribe(wav_5s)
        # 5s audio -> 0.125 INR spend recorded
        assert speech_budget.daily_spend == 0.125

        tts = SarvamTTS(api_key="test-key")
        _ = await tts.synthesize("नमस्ते", get_voice("abhyas"))
        # ~6 chars -> round(6/1000 * 3.0, 4) = 0.018 INR
        assert speech_budget.daily_spend > 0.125


@pytest.mark.asyncio
@respx.mock
async def test_tts_budget_exhaustion_triggers_lite_mode() -> None:
    """When TTS budget cap is reached, SarvamTTS falls back to lite mode (empty bytes) when Bhashini not set."""
    route = respx.post("https://api.sarvam.ai/text-to-speech").mock(
        return_value=httpx.Response(200, json={"audios": [""]})
    )

    with (
        patch.object(settings, "SPEECH_PROVIDER_LIVE", True),
        patch.object(settings, "SPEECH_DAILY_BUDGET_INR", 1.0),
        patch.object(settings, "BHASHINI_API_KEY", ""),
        tempfile.TemporaryDirectory() as tmpdir,
        patch("backend.app.speech.tts.tts_cache", TTSCache(cache_dir=tmpdir, use_db=False)),
    ):
        # Exhaust budget
        await speech_budget.record_spend("sarvam", "tts", 100, 1.0)
        tts = SarvamTTS(api_key="test-key")
        result = await tts.synthesize("नमस्ते शिक्षक जी", get_voice("abhyas"))

        # Returns empty bytes (text-only reply)
        assert result.audio == b""
        assert result.fmt == "wav"
        assert result.cache_hit is False
        # API was never called because budget guard intercepted it
        assert route.call_count == 0


@pytest.mark.asyncio
@respx.mock
async def test_cap_hit_order_fallback_to_bhashini(wav_5s: bytes) -> None:
    """Cap-hit order: Sarvam cap reached -> Bhashini (if configured) -> lite mode (CHANGES 254f622 Item 2)."""
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

    with (
        patch.object(settings, "SPEECH_PROVIDER_LIVE", True),
        patch.object(settings, "SPEECH_DAILY_BUDGET_INR", 1.0),
        patch.object(settings, "BHASHINI_API_KEY", "test-bhashini-key"),
        patch.object(settings, "BHASHINI_USER_ID", "test-user"),
        tempfile.TemporaryDirectory() as tmpdir,
        patch("backend.app.speech.tts.tts_cache", TTSCache(cache_dir=tmpdir, use_db=False)),
    ):
        await speech_budget.record_spend("sarvam", "tts", 100, 1.0)
        tts = SarvamTTS(api_key="test-key")
        result = await tts.synthesize("नमस्ते शिक्षक जी", get_voice("abhyas"))

        # Successfully synthesizes via Bhashini fallback
        assert result.audio.startswith(b"RIFF")
        assert len(result.audio) == len(wav_5s)
        assert result.fmt == "wav"
        assert result.cache_hit is False


@pytest.mark.asyncio
async def test_stt_budget_exhaustion_raises_error(wav_5s: bytes) -> None:
    """When STT budget cap is reached and Bhashini not set, raises SpeechBudgetExceededError."""
    with (
        patch.object(settings, "SPEECH_PROVIDER_LIVE", True),
        patch.object(settings, "SPEECH_DAILY_BUDGET_INR", 0.05),
        patch.object(settings, "BHASHINI_API_KEY", ""),
    ):
        # 5s audio cost is 0.125 INR, which exceeds 0.05 INR cap
        stt = SarvamSTT(api_key="test-key")
        with pytest.raises(SpeechBudgetExceededError):
            await stt.transcribe(wav_5s)


@pytest.mark.asyncio
@respx.mock
async def test_cache_hit_results_in_zero_spend(wav_5s: bytes) -> None:
    """When audio is present in cache, TTS returns it immediately with zero spend and no API call."""
    route = respx.post("https://api.sarvam.ai/text-to-speech").mock(
        return_value=httpx.Response(200, json={"audios": []})
    )

    with (
        patch.object(settings, "SPEECH_PROVIDER_LIVE", True),
        tempfile.TemporaryDirectory() as tmpdir,
    ):
        test_cache = TTSCache(cache_dir=tmpdir, use_db=False)
        voice = get_voice("abhyas")
        text = "नमस्ते"
        key = compute_cache_key(text, voice.provider_speaker, voice, provider="sarvam")

        # Put in cache beforehand
        await test_cache.put_wav(key, wav_5s)
        cached_audio = await test_cache.get(key, "ogg")

        with patch("backend.app.speech.tts.tts_cache", test_cache):
            tts = SarvamTTS(api_key="test-key")
            result = await tts.synthesize(text, voice)

            assert result.audio == cached_audio
            assert result.cache_key == key
            assert result.fmt == "ogg"
            assert result.cache_hit is True
            # Zero spend recorded
            assert speech_budget.daily_spend == 0.0
            # Zero API calls made
            assert route.call_count == 0


@pytest.mark.asyncio
async def test_prewarm_fixed_audio() -> None:
    """prewarm_fixed_audio populates the cache with static audio lines."""
    with tempfile.TemporaryDirectory() as tmpdir:
        test_cache = TTSCache(cache_dir=tmpdir, use_db=False)
        mock_tts = MockTTS()

        prewarmed_keys = await prewarm_fixed_audio(
            tts=mock_tts,
            cache=test_cache,
            extra_lines=[("abhyas", "यह एक परीक्षण लाइन है।")],
        )

        assert len(prewarmed_keys) > 0
        # All prewarmed keys exist in cache as wav, ogg, mp3
        for k in prewarmed_keys:
            assert await test_cache.has(k, "wav") is True
            assert await test_cache.has(k, "ogg") is True
            assert await test_cache.has(k, "mp3") is True


@pytest.mark.asyncio
async def test_spend_fails_closed_in_live_mode_on_db_query_failure() -> None:
    """When SPEECH_PROVIDER_LIVE=true and DB spend query fails, can_spend returns False (fails closed)."""
    tracker = SpeechBudgetTracker()

    with (
        patch.object(settings, "SPEECH_PROVIDER_LIVE", True),
        patch.object(tracker, "get_daily_spend_db", return_value=None),
        patch.object(tracker, "get_total_spend_db", return_value=None),
    ):
        # Even with 0 INR spend, DB query failure fails closed in live mode
        can_proceed = await tracker.can_spend(0.01)
        assert can_proceed is False
