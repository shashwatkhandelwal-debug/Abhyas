"""Unit tests for Gemini STT/TTS providers and the speech fallback chain (spec/06 §6.2, §6.3)."""

import base64
import io
import json
import logging
import wave
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import patch

import httpx
import pytest
import respx
from pydantic import ValidationError

from backend.app.config import Settings, settings
from backend.app.speech import audio as audio_mod
from backend.app.speech.cache import compute_cache_key, tts_cache
from backend.app.speech.stt import (
    FallbackSTT,
    GeminiSTT,
    MockSTT,
    SarvamSTT,
    STTUnavailable,
    get_stt_provider,
)
from backend.app.speech.tts import (
    FallbackTTS,
    GeminiTTS,
    SarvamTTS,
    TTSUnavailable,
    get_tts_provider,
    tts_cache_key,
)
from backend.app.speech.voices import get_voice
from scripts.prewarm_tts import prewarm_tts

FIXTURES_DIR = Path(__file__).parents[1] / "fixtures" / "audio"
GEMINI_KEY = "test-gemini-key"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
SARVAM_STT_URL = "https://api.sarvam.ai/speech-to-text"
SARVAM_TTS_URL = "https://api.sarvam.ai/text-to-speech"
SPEECH_LOGGERS = ("abhyas.speech.gemini", "abhyas.speech.stt", "abhyas.speech.tts")


@pytest.fixture(autouse=True)
def isolate_tts_cache(tmp_path: Path) -> Iterator[None]:
    original_dir = tts_cache.cache_dir
    tts_cache.cache_dir = tmp_path
    yield
    tts_cache.cache_dir = original_dir


@pytest.fixture(autouse=True)
def fast_retries() -> Iterator[None]:
    async def _no_sleep(_: float) -> None:
        return None

    with patch("backend.app.speech.gemini.asyncio.sleep", _no_sleep):
        yield


@pytest.fixture
def wav_5s() -> bytes:
    return (FIXTURES_DIR / "sample_5s.wav").read_bytes()


def _wav_24k(seconds: float = 1.0) -> bytes:
    out = io.BytesIO()
    with wave.open(out, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(24000)
        wf.writeframes(b"\x10\x00" * int(24000 * seconds))
    return out.getvalue()


def _text_response(text: str) -> dict[str, Any]:
    return {
        "object": "interaction",
        "status": "completed",
        "steps": [{"type": "model_output", "content": [{"type": "text", "text": text}]}],
    }


def _audio_response(wav: bytes) -> dict[str, Any]:
    return {
        "object": "interaction",
        "status": "completed",
        "steps": [
            {
                "type": "model_output",
                "content": [
                    {
                        "type": "audio",
                        "data": base64.b64encode(wav).decode("ascii"),
                        "mime_type": "audio/wav",
                    }
                ],
            }
        ],
    }


def _sent_json(route: respx.Route, index: int = 0) -> dict[str, Any]:
    body: dict[str, Any] = json.loads(route.calls[index].request.content)
    return body


# ── GeminiSTT ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@respx.mock
async def test_gemini_stt_success(wav_5s: bytes) -> None:
    route = respx.post(GEMINI_URL).mock(
        return_value=httpx.Response(200, json=_text_response("रवि, 52 में से 17 घटाओ।"))
    )
    stt = GeminiSTT(api_key=GEMINI_KEY)
    result = await stt.transcribe(wav_5s)

    assert result.provider == "gemini"
    assert result.text == "रवि, 52 में से 17 घटाओ।"
    assert result.confidence == 0.9
    request = route.calls[0].request
    assert request.headers["x-goog-api-key"] == GEMINI_KEY
    body = _sent_json(route)
    assert body["model"] == settings.GEMINI_STT_MODEL
    audio_items = [i for i in body["input"] if i["type"] == "audio"]
    assert len(audio_items) == 1
    assert audio_items[0]["mime_type"] == "audio/wav"
    assert base64.b64decode(audio_items[0]["data"]).startswith(b"RIFF")


@pytest.mark.asyncio
@respx.mock
async def test_gemini_stt_keyterms_in_request(wav_5s: bytes) -> None:
    route = respx.post(GEMINI_URL).mock(
        return_value=httpx.Response(200, json=_text_response("हासिल"))
    )
    keyterms = ["हासिल", "दहाई"] + [f"शब्द{i}" for i in range(60)]
    await GeminiSTT(api_key=GEMINI_KEY).transcribe(wav_5s, keyterms=keyterms)

    prompt = " ".join(i["text"] for i in _sent_json(route)["input"] if i["type"] == "text")
    assert "हासिल" in prompt
    assert "दहाई" in prompt
    assert "शब्द47" in prompt  # 50th term kept
    assert "शब्द48" not in prompt  # capped at 50


@pytest.mark.asyncio
@respx.mock
async def test_gemini_stt_retries_once_on_5xx(wav_5s: bytes) -> None:
    route = respx.post(GEMINI_URL)
    route.side_effect = [
        httpx.Response(503),
        httpx.Response(200, json=_text_response("नमस्ते")),
    ]
    result = await GeminiSTT(api_key=GEMINI_KEY).transcribe(wav_5s)
    assert result.text == "नमस्ते"
    assert route.call_count == 2


@pytest.mark.asyncio
@respx.mock
async def test_gemini_stt_429_raises_unavailable_without_retry(wav_5s: bytes) -> None:
    route = respx.post(GEMINI_URL).mock(return_value=httpx.Response(429))
    with pytest.raises(STTUnavailable):
        await GeminiSTT(api_key=GEMINI_KEY).transcribe(wav_5s)
    assert route.call_count == 1


@pytest.mark.asyncio
async def test_gemini_stt_rejects_oversized_clip(wav_5s: bytes) -> None:
    async def _passthrough(wav: bytes) -> bytes:
        return wav

    with (
        patch.object(settings, "GEMINI_STT_MAX_BYTES", 1000),
        patch("backend.app.speech.stt.trim_silence", _passthrough),
        pytest.raises(STTUnavailable),
    ):
        await GeminiSTT(api_key=GEMINI_KEY).transcribe(wav_5s)


# ── GeminiTTS ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@respx.mock
async def test_gemini_tts_success_returns_wav() -> None:
    wav = _wav_24k()
    route = respx.post(GEMINI_URL).mock(return_value=httpx.Response(200, json=_audio_response(wav)))
    result = await GeminiTTS(api_key=GEMINI_KEY).synthesize("आज 45 सीखेंगे", get_voice("abhyas"))

    assert result.fmt == "wav"
    assert result.audio == wav
    assert result.cache_hit is False
    with wave.open(io.BytesIO(result.audio), "rb") as wf:
        assert wf.getframerate() == 24000
    body = _sent_json(route)
    assert body["model"] == settings.GEMINI_TTS_MODEL
    assert body["response_format"] == {"type": "audio"}
    assert body["generation_config"]["speech_config"] == [{"voice": settings.GEMINI_TTS_VOICE_F}]
    sent_text = body["input"][0]["content"][0]["text"]
    assert "पैंतालीस" in sent_text and "45" not in sent_text


@pytest.mark.asyncio
@respx.mock
async def test_gemini_tts_child_voice_is_pitch_shifted() -> None:
    wav = _wav_24k()
    route = respx.post(GEMINI_URL).mock(return_value=httpx.Response(200, json=_audio_response(wav)))
    voice = get_voice("child_ravi")

    with patch("backend.app.speech.tts.pitch_shift", wraps=audio_mod.pitch_shift) as pitch_spy:
        result = await GeminiTTS(api_key=GEMINI_KEY).synthesize("पैंतालीस!", voice)

    pitch_spy.assert_called_once()
    assert pitch_spy.call_args.args[1] == voice.pitch_factor
    assert result.fmt == "wav"
    assert result.audio.startswith(b"RIFF")
    assert result.audio != wav
    assert _sent_json(route)["generation_config"]["speech_config"] == [
        {"voice": settings.GEMINI_TTS_VOICE_M}
    ]


@pytest.mark.asyncio
@respx.mock
async def test_gemini_tts_429_raises_unavailable() -> None:
    respx.post(GEMINI_URL).mock(return_value=httpx.Response(429))
    with pytest.raises(TTSUnavailable):
        await GeminiTTS(api_key=GEMINI_KEY).synthesize("नमस्ते", get_voice("abhyas"))


# ── Fallback chain ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
@respx.mock
async def test_stt_chain_gemini_429_uses_sarvam(wav_5s: bytes) -> None:
    respx.post(GEMINI_URL).mock(return_value=httpx.Response(429))
    sarvam = respx.post(SARVAM_STT_URL).mock(
        return_value=httpx.Response(200, json={"transcript": "सरवम पाठ"})
    )
    with (
        patch.object(settings, "STT_PROVIDER", "gemini"),
        patch.object(settings, "STT_FALLBACK_PROVIDER", "sarvam"),
        patch.object(settings, "GEMINI_API_KEY", GEMINI_KEY),
        patch.object(settings, "SARVAM_API_KEY", "test-key"),
    ):
        provider = get_stt_provider()
        assert isinstance(provider, FallbackSTT)
        result = await provider.transcribe(wav_5s)

    assert result.provider == "sarvam"
    assert result.text == "सरवम पाठ"
    assert sarvam.call_count == 1


@pytest.mark.asyncio
@respx.mock
async def test_tts_chain_gemini_429_uses_sarvam() -> None:
    sarvam_wav = _wav_24k(0.5)
    respx.post(GEMINI_URL).mock(return_value=httpx.Response(429))
    sarvam = respx.post(SARVAM_TTS_URL).mock(
        return_value=httpx.Response(
            200, json={"audios": [base64.b64encode(sarvam_wav).decode("ascii")]}
        )
    )
    with (
        patch.object(settings, "TTS_PROVIDER", "gemini"),
        patch.object(settings, "TTS_FALLBACK_PROVIDER", "sarvam"),
        patch.object(settings, "GEMINI_API_KEY", GEMINI_KEY),
        patch.object(settings, "SARVAM_API_KEY", "test-key"),
    ):
        provider = get_tts_provider()
        assert isinstance(provider, FallbackTTS)
        result = await provider.synthesize("फॉलबैक", get_voice("abhyas"))

    assert result.audio == sarvam_wav
    assert sarvam.call_count == 1


@pytest.mark.asyncio
@respx.mock
async def test_stt_chain_both_fail_raises(wav_5s: bytes) -> None:
    respx.post(GEMINI_URL).mock(return_value=httpx.Response(429))
    respx.post(SARVAM_STT_URL).mock(return_value=httpx.Response(503))
    with (
        patch.object(settings, "STT_PROVIDER", "gemini"),
        patch.object(settings, "STT_FALLBACK_PROVIDER", "sarvam"),
        patch.object(settings, "GEMINI_API_KEY", GEMINI_KEY),
        patch.object(settings, "SARVAM_API_KEY", "test-key"),
        patch("backend.app.speech.stt.asyncio.sleep", return_value=None),
        pytest.raises(STTUnavailable),
    ):
        await get_stt_provider().transcribe(wav_5s)


@pytest.mark.asyncio
@respx.mock
async def test_tts_chain_both_fail_raises() -> None:
    respx.post(GEMINI_URL).mock(return_value=httpx.Response(403))
    respx.post(SARVAM_TTS_URL).mock(return_value=httpx.Response(401))
    with (
        patch.object(settings, "TTS_PROVIDER", "gemini"),
        patch.object(settings, "TTS_FALLBACK_PROVIDER", "sarvam"),
        patch.object(settings, "GEMINI_API_KEY", GEMINI_KEY),
        patch.object(settings, "SARVAM_API_KEY", "test-key"),
        patch("backend.app.speech.tts.asyncio.sleep", return_value=None),
        pytest.raises(TTSUnavailable),
    ):
        await get_tts_provider().synthesize("दोनों विफल", get_voice("abhyas"))


def test_fallback_none_leaves_providers_unchanged() -> None:
    with (
        patch.object(settings, "STT_PROVIDER", "sarvam"),
        patch.object(settings, "TTS_PROVIDER", "sarvam"),
        patch.object(settings, "STT_FALLBACK_PROVIDER", "none"),
        patch.object(settings, "TTS_FALLBACK_PROVIDER", "none"),
        patch.object(settings, "SARVAM_API_KEY", "test-key"),
    ):
        assert type(get_stt_provider()) is SarvamSTT
        assert type(get_tts_provider()) is SarvamTTS

    with (
        patch.object(settings, "STT_PROVIDER", "gemini"),
        patch.object(settings, "TTS_PROVIDER", "gemini"),
        patch.object(settings, "STT_FALLBACK_PROVIDER", "none"),
        patch.object(settings, "TTS_FALLBACK_PROVIDER", "none"),
        patch.object(settings, "GEMINI_API_KEY", GEMINI_KEY),
    ):
        assert type(get_stt_provider()) is GeminiSTT
        assert type(get_tts_provider()) is GeminiTTS


def test_fallback_same_as_primary_is_not_wrapped() -> None:
    with (
        patch.object(settings, "STT_PROVIDER", "gemini"),
        patch.object(settings, "STT_FALLBACK_PROVIDER", "gemini"),
        patch.object(settings, "GEMINI_API_KEY", GEMINI_KEY),
    ):
        assert type(get_stt_provider()) is GeminiSTT


def test_gemini_without_key_uses_mock_in_dev() -> None:
    with (
        patch.object(settings, "STT_PROVIDER", "gemini"),
        patch.object(settings, "STT_FALLBACK_PROVIDER", "none"),
        patch.object(settings, "GEMINI_API_KEY", ""),
        patch.object(settings, "ENVIRONMENT", "development"),
    ):
        assert isinstance(get_stt_provider(), MockSTT)


@pytest.mark.asyncio
@respx.mock
async def test_logs_never_contain_api_key(
    wav_5s: bytes, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Loggers may have been disabled by an earlier logging.config call in the same process
    for name in SPEECH_LOGGERS:
        monkeypatch.setattr(logging.getLogger(name), "disabled", False)
    caplog.set_level(logging.DEBUG)  # root: capture third-party (httpx) records for the key check
    caplog.set_level(logging.WARNING, logger="abhyas.speech")
    respx.post(GEMINI_URL).mock(side_effect=[httpx.Response(500), httpx.Response(429)] * 2)
    respx.post(SARVAM_STT_URL).mock(return_value=httpx.Response(200, json={"transcript": "ठीक"}))
    respx.post(SARVAM_TTS_URL).mock(
        return_value=httpx.Response(
            200, json={"audios": [base64.b64encode(_wav_24k(0.2)).decode("ascii")]}
        )
    )
    with (
        patch.object(settings, "STT_PROVIDER", "gemini"),
        patch.object(settings, "TTS_PROVIDER", "gemini"),
        patch.object(settings, "STT_FALLBACK_PROVIDER", "sarvam"),
        patch.object(settings, "TTS_FALLBACK_PROVIDER", "sarvam"),
        patch.object(settings, "GEMINI_API_KEY", GEMINI_KEY),
        patch.object(settings, "SARVAM_API_KEY", "test-key"),
    ):
        await get_stt_provider().transcribe(wav_5s)
        await get_tts_provider().synthesize("लॉग जाँच", get_voice("abhyas"))

    speech_records = [r for r in caplog.records if r.name.startswith("abhyas.speech")]
    assert speech_records, "expected retry/fallback log records"
    assert GEMINI_KEY not in caplog.text
    for record in caplog.records:
        assert GEMINI_KEY not in str(record.args)


# ── Cache key per provider ─────────────────────────────────────────────────


def test_cache_key_includes_provider() -> None:
    voice = get_voice("child_ravi")
    text = "रवि ने 45 कहा।"
    sarvam_key = compute_cache_key(text, voice.provider_speaker, voice, provider="sarvam")
    gemini_key = compute_cache_key(text, voice.provider_speaker, voice, provider="gemini")
    assert sarvam_key != gemini_key
    assert tts_cache_key(SarvamTTS(api_key="test-key"), text, voice) == sarvam_key
    assert tts_cache_key(GeminiTTS(api_key=GEMINI_KEY), text, voice) == gemini_key


@pytest.mark.asyncio
@respx.mock
async def test_sarvam_cached_clip_not_served_to_gemini() -> None:
    sarvam_wav = _wav_24k(0.4)
    gemini_wav = _wav_24k(0.7)
    respx.post(SARVAM_TTS_URL).mock(
        return_value=httpx.Response(
            200, json={"audios": [base64.b64encode(sarvam_wav).decode("ascii")]}
        )
    )
    gemini = respx.post(GEMINI_URL).mock(
        return_value=httpx.Response(200, json=_audio_response(gemini_wav))
    )
    voice = get_voice("abhyas")
    text = "साझा कैश नहीं"

    sarvam_res = await SarvamTTS(api_key="test-key").synthesize(text, voice)
    gemini_res = await GeminiTTS(api_key=GEMINI_KEY).synthesize(text, voice)

    assert sarvam_res.cache_key != gemini_res.cache_key
    assert gemini_res.cache_hit is False
    assert gemini_res.audio == gemini_wav
    assert gemini.call_count == 1


# ── Retries with / without fallback ────────────────────────────────────────


@pytest.mark.asyncio
@respx.mock
async def test_stt_primary_gets_no_retry_when_fallback_configured(wav_5s: bytes) -> None:
    gemini = respx.post(GEMINI_URL).mock(return_value=httpx.Response(503))
    respx.post(SARVAM_STT_URL).mock(return_value=httpx.Response(200, json={"transcript": "ठीक"}))
    with (
        patch.object(settings, "STT_PROVIDER", "gemini"),
        patch.object(settings, "STT_FALLBACK_PROVIDER", "sarvam"),
        patch.object(settings, "GEMINI_API_KEY", GEMINI_KEY),
        patch.object(settings, "SARVAM_API_KEY", "test-key"),
    ):
        provider = get_stt_provider()
        assert isinstance(provider, FallbackSTT)
        assert isinstance(provider.primary, GeminiSTT) and provider.primary.max_retries == 0
        assert isinstance(provider.fallback, SarvamSTT) and provider.fallback.max_retries == 1
        result = await provider.transcribe(wav_5s)

    assert gemini.call_count == 1
    assert result.provider == "sarvam"


@pytest.mark.asyncio
@respx.mock
async def test_tts_primary_gets_no_retry_when_fallback_configured() -> None:
    gemini = respx.post(GEMINI_URL).mock(return_value=httpx.Response(503))
    respx.post(SARVAM_TTS_URL).mock(
        return_value=httpx.Response(
            200, json={"audios": [base64.b64encode(_wav_24k(0.3)).decode("ascii")]}
        )
    )
    with (
        patch.object(settings, "TTS_PROVIDER", "gemini"),
        patch.object(settings, "TTS_FALLBACK_PROVIDER", "sarvam"),
        patch.object(settings, "GEMINI_API_KEY", GEMINI_KEY),
        patch.object(settings, "SARVAM_API_KEY", "test-key"),
    ):
        provider = get_tts_provider()
        assert isinstance(provider, FallbackTTS)
        assert isinstance(provider.primary, GeminiTTS) and provider.primary.max_retries == 0
        assert isinstance(provider.fallback, SarvamTTS) and provider.fallback.max_retries == 1
        result = await provider.synthesize("एक ही प्रयास", get_voice("abhyas"))

    assert gemini.call_count == 1
    assert result.audio.startswith(b"RIFF")


@pytest.mark.asyncio
@respx.mock
async def test_sarvam_primary_gets_no_retry_when_gemini_fallback(wav_5s: bytes) -> None:
    sarvam = respx.post(SARVAM_STT_URL).mock(return_value=httpx.Response(503))
    respx.post(GEMINI_URL).mock(return_value=httpx.Response(200, json=_text_response("जेमिनी")))
    with (
        patch.object(settings, "STT_PROVIDER", "sarvam"),
        patch.object(settings, "STT_FALLBACK_PROVIDER", "gemini"),
        patch.object(settings, "GEMINI_API_KEY", GEMINI_KEY),
        patch.object(settings, "SARVAM_API_KEY", "test-key"),
    ):
        result = await get_stt_provider().transcribe(wav_5s)

    assert sarvam.call_count == 1
    assert result.provider == "gemini"


@pytest.mark.asyncio
@respx.mock
async def test_no_fallback_keeps_one_retry(wav_5s: bytes) -> None:
    gemini = respx.post(GEMINI_URL)
    gemini.side_effect = [
        httpx.Response(503),
        httpx.Response(200, json=_text_response("दूसरा प्रयास")),
        httpx.Response(503),
        httpx.Response(200, json=_audio_response(_wav_24k(0.3))),
    ]
    with (
        patch.object(settings, "STT_PROVIDER", "gemini"),
        patch.object(settings, "TTS_PROVIDER", "gemini"),
        patch.object(settings, "STT_FALLBACK_PROVIDER", "none"),
        patch.object(settings, "TTS_FALLBACK_PROVIDER", "none"),
        patch.object(settings, "GEMINI_API_KEY", GEMINI_KEY),
    ):
        stt = get_stt_provider()
        tts = get_tts_provider()
        assert isinstance(stt, GeminiSTT) and stt.max_retries == 1
        assert isinstance(tts, GeminiTTS) and tts.max_retries == 1
        transcript = await stt.transcribe(wav_5s)
        synth = await tts.synthesize("दोबारा", get_voice("abhyas"))

    assert transcript.text == "दूसरा प्रयास"
    assert synth.audio.startswith(b"RIFF")
    assert gemini.call_count == 4

    with (
        patch.object(settings, "STT_PROVIDER", "sarvam"),
        patch.object(settings, "TTS_PROVIDER", "sarvam"),
        patch.object(settings, "STT_FALLBACK_PROVIDER", "none"),
        patch.object(settings, "TTS_FALLBACK_PROVIDER", "none"),
        patch.object(settings, "SARVAM_API_KEY", "test-key"),
    ):
        sarvam_stt = get_stt_provider()
        sarvam_tts = get_tts_provider()
        assert isinstance(sarvam_stt, SarvamSTT) and sarvam_stt.max_retries == 1
        assert isinstance(sarvam_tts, SarvamTTS) and sarvam_tts.max_retries == 1


# ── Pre-warm script with provider-scoped keys ──────────────────────────────


@pytest.mark.asyncio
@respx.mock
async def test_prewarm_script_stores_clips_under_synthesizing_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    text = "अभ्यास में स्वागत है।"
    msg_file = tmp_path / "messages_hi.yaml"
    msg_file.write_text(f'msg_1:\n  audio: true\n  text: "{text}"\n', encoding="utf-8")
    moves_dir = tmp_path / "moves"
    moves_dir.mkdir()
    voice = get_voice("abhyas")
    gemini_key = compute_cache_key(text, voice.provider_speaker, voice, provider="gemini")
    sarvam_key = compute_cache_key(text, voice.provider_speaker, voice, provider="sarvam")

    gemini = respx.post(GEMINI_URL)
    gemini.side_effect = [
        httpx.Response(429),  # run 1: primary fails, Sarvam synthesizes
        httpx.Response(200, json=_audio_response(_wav_24k(0.3))),  # run 2: Gemini succeeds
    ]
    respx.post(SARVAM_TTS_URL).mock(
        return_value=httpx.Response(
            200, json={"audios": [base64.b64encode(_wav_24k(0.2)).decode("ascii")]}
        )
    )
    chain = FallbackTTS(
        GeminiTTS(api_key=GEMINI_KEY, max_retries=0),
        SarvamTTS(api_key="test-key"),
        "gemini",
        "sarvam",
    )

    clock = [1000.0]
    monkeypatch.setattr("backend.app.speech.tts._now", lambda: clock[0])

    first = await prewarm_tts(messages_path=msg_file, moves_dir=moves_dir, tts_provider=chain)
    assert first["synthesized"] == 1
    assert await tts_cache.has(sarvam_key, "wav") is True
    assert await tts_cache.has(gemini_key, "wav") is False

    # the 429 paused Gemini; once the cool-down is over the next run uses it again
    clock[0] += settings.SPEECH_RATE_LIMIT_COOLDOWN_S + 1
    second = await prewarm_tts(messages_path=msg_file, moves_dir=moves_dir, tts_provider=chain)
    assert second["synthesized"] == 1
    assert await tts_cache.has(gemini_key, "wav") is True

    third = await prewarm_tts(messages_path=msg_file, moves_dir=moves_dir, tts_provider=chain)
    assert third["already_cached"] == 1
    assert third["synthesized"] == 0


@pytest.mark.asyncio
async def test_prewarm_script_not_mock_with_only_gemini_key(tmp_path: Path) -> None:
    msg_file = tmp_path / "messages_hi.yaml"
    msg_file.write_text('msg_1:\n  audio: true\n  text: "नमस्ते"\n', encoding="utf-8")
    moves_dir = tmp_path / "moves"
    moves_dir.mkdir()
    with (
        patch.object(settings, "TTS_PROVIDER", "gemini"),
        patch.object(settings, "TTS_FALLBACK_PROVIDER", "none"),
        patch.object(settings, "GEMINI_API_KEY", GEMINI_KEY),
        patch.object(settings, "SARVAM_API_KEY", ""),
        patch.object(settings, "ENVIRONMENT", "development"),
    ):
        res = await prewarm_tts(messages_path=msg_file, moves_dir=moves_dir, dry_run=True)
    assert res["total_targets"] == 1
    assert res["synthesized"] == 1


# ── Spend ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@respx.mock
async def test_gemini_usage_recorded_at_zero_cost(wav_5s: bytes) -> None:
    respx.post(GEMINI_URL).mock(
        side_effect=[
            httpx.Response(200, json=_text_response("नमस्ते")),
            httpx.Response(200, json=_audio_response(_wav_24k(0.3))),
        ]
    )
    recorded: list[tuple[str, str, int, float]] = []

    async def _record(provider: str, kind: str, units: int, amount_inr: float) -> None:
        recorded.append((provider, kind, units, amount_inr))

    async def _can_spend(_: float) -> bool:
        return True

    with (
        patch.object(settings, "SPEECH_PROVIDER_LIVE", True),
        patch("backend.app.speech.spend.speech_budget.record_spend", _record),
        patch("backend.app.speech.spend.speech_budget.can_spend", _can_spend),
    ):
        await GeminiSTT(api_key=GEMINI_KEY).transcribe(wav_5s)
        await GeminiTTS(api_key=GEMINI_KEY).synthesize("खर्च जाँच", get_voice("abhyas"))

    assert [(p, k, c) for p, k, _, c in recorded] == [
        ("gemini", "stt", 0.0),
        ("gemini", "tts", 0.0),
    ]


# ── Config ────────────────────────────────────────────────────────────────

_PROD_SECRETS: dict[str, Any] = {
    "ENVIRONMENT": "production",
    "ANTHROPIC_API_KEY": "valid-anthropic-key",
    "SESSION_SECRET": "a" * 64,
    "PHONE_HASH_SALT": "b" * 32,
    "PHONE_ENC_KEY": "valid-fernet-key",
    "DEMO_PASSWORD": "rotated-prod-password-9988",
    "ADMIN_PASSWORD": "rotated-admin-password-9988",
}


def test_production_requires_gemini_key_for_primary_or_fallback() -> None:
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            **_PROD_SECRETS,
            STT_PROVIDER="sarvam",
            TTS_PROVIDER="sarvam",
            STT_FALLBACK_PROVIDER="gemini",
            TTS_FALLBACK_PROVIDER="none",
            SARVAM_API_KEY="valid-sarvam-key",
            GEMINI_API_KEY="",
        )
    assert "GEMINI_API_KEY" in str(exc_info.value)

    cfg = Settings(
        **_PROD_SECRETS,
        STT_PROVIDER="gemini",
        TTS_PROVIDER="gemini",
        STT_FALLBACK_PROVIDER="sarvam",
        TTS_FALLBACK_PROVIDER="sarvam",
        SARVAM_API_KEY="valid-sarvam-key",
        GEMINI_API_KEY=GEMINI_KEY,
    )
    assert cfg.STT_FALLBACK_PROVIDER == "sarvam"


def test_production_rejects_mock_fallback() -> None:
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            **_PROD_SECRETS,
            STT_PROVIDER="gemini",
            TTS_PROVIDER="gemini",
            STT_FALLBACK_PROVIDER="none",
            TTS_FALLBACK_PROVIDER="mock",
            GEMINI_API_KEY=GEMINI_KEY,
        )
    assert "TTS_FALLBACK_PROVIDER" in str(exc_info.value)


def test_gemini_defaults() -> None:
    cfg = Settings(ENVIRONMENT="development")
    assert cfg.GEMINI_BASE_URL == "https://generativelanguage.googleapis.com/v1beta"
    assert cfg.GEMINI_STT_MODEL == "gemini-3.8-flash"
    assert cfg.GEMINI_TTS_MODEL == "gemini-3.8-flash-tts"
    assert (cfg.GEMINI_TTS_VOICE_F, cfg.GEMINI_TTS_VOICE_M) == ("Kore", "Puck")
    assert cfg.GEMINI_STT_COST_INR_PER_MIN == 0.0
    assert cfg.GEMINI_TTS_COST_INR_PER_1K_CHARS == 0.0
