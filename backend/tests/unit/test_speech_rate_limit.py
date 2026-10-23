"""Gemini rate limits: skip it for a while, fall back to Sarvam, then to "please type instead".

No real provider is called: every HTTP request goes to an in-process fake (httpx.MockTransport) and the
clock is controlled, so no quota is spent and nothing sleeps.
"""

from __future__ import annotations

import base64
import io
import wave
from collections.abc import Iterator
from typing import Any

import httpx
import pytest

from backend.app.config import settings
from backend.app.core.conversation import ConversationService
from backend.app.core.messages import get_message
from backend.app.core.types import InboundMessage
from backend.app.speech import stt as stt_mod
from backend.app.speech import tts as tts_mod
from backend.app.speech.gemini import post_interaction
from backend.app.speech.stt import (
    FallbackSTT,
    STTRateLimited,
    STTUnavailable,
    Transcript,
    get_stt_provider,
)
from backend.app.speech.tts import (
    FallbackTTS,
    TTSRateLimited,
    TTSUnavailable,
    get_tts_provider,
)
from backend.app.speech.voices import get_voice

GEMINI_HOST = "generativelanguage.googleapis.com"
SARVAM_HOST = "api.sarvam.ai"


def _wav(seconds: float = 1.0) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b"\x01\x02" * int(16000 * seconds))
    return buf.getvalue()


@pytest.fixture(autouse=True)
def _fresh_rate_limit_state() -> Iterator[None]:
    stt_mod.reset_rate_limits()
    tts_mod.reset_rate_limits()
    yield
    stt_mod.reset_rate_limits()
    tts_mod.reset_rate_limits()


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> Clock:
    c = Clock()
    monkeypatch.setattr(stt_mod, "_now", c)
    monkeypatch.setattr(tts_mod, "_now", c)
    return c


# ── the HTTP helper: 429 and quota bodies are rate limits, other errors are not ──────────────
class _Limited(Exception):
    pass


class _Down(Exception):
    pass


async def _post(handler: Any, *, with_rate_class: bool = True) -> dict[str, Any]:
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        return await post_interaction(
            client,
            base_url=f"https://{GEMINI_HOST}/v1beta",
            api_key="test-key",
            payload={},
            timeout_s=1.0,
            label="Gemini X",
            error_cls=_Down,
            max_retries=1,
            rate_limit_cls=_Limited if with_rate_class else None,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "body"),
    [
        (429, "{}"),
        (429, '{"error": {"status": "RESOURCE_EXHAUSTED"}}'),
        (403, '{"error": {"message": "Quota exceeded for this project"}}'),
        (400, '{"error": {"status": "RESOURCE_EXHAUSTED"}}'),
    ],
)
async def test_429_and_quota_bodies_raise_the_rate_limit_class_without_retrying(
    status: int, body: str
) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(status, text=body)

    with pytest.raises(_Limited):
        await _post(handler)
    assert calls == 1  # a rate limit is not retried against the same provider


@pytest.mark.asyncio
async def test_other_client_errors_and_missing_rate_class_stay_ordinary_failures() -> None:
    with pytest.raises(_Down):
        await _post(lambda r: httpx.Response(401, text='{"error": "bad key"}'))
    with pytest.raises(_Down):
        await _post(lambda r: httpx.Response(429, text="{}"), with_rate_class=False)
    with pytest.raises(_Down):
        await _post(lambda r: httpx.Response(400, text='{"error": "invalid audio"}'))


@pytest.mark.asyncio
async def test_a_5xx_is_retried_once_then_an_ordinary_failure() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503, text="busy")

    with pytest.raises(_Down):
        await _post(handler)
    assert calls == 2


# ── the STT chain with stubs: skip a limited primary for the cool-down ──────────────────────
class _StubSTT:
    def __init__(self, name: str, behaviour: str) -> None:
        self.name = name
        self.behaviour = behaviour
        self.calls = 0

    async def transcribe(
        self, wav16k: bytes, lang: str = "hi-IN", keyterms: list[str] | None = None
    ) -> Transcript:
        self.calls += 1
        if self.behaviour == "limited":
            raise STTRateLimited(f"{self.name} rate limited")
        if self.behaviour == "down":
            raise STTUnavailable(f"{self.name} down")
        return Transcript(text="नमस्ते", confidence=0.9, provider=self.name, ms=1)


@pytest.mark.asyncio
async def test_rate_limited_primary_is_skipped_for_the_cooldown_then_tried_again(
    clock: Clock,
) -> None:
    primary = _StubSTT("gemini", "limited")
    fallback = _StubSTT("sarvam", "ok")
    chain = FallbackSTT(primary, fallback, "gemini", "sarvam")  # type: ignore[arg-type]

    first = await chain.transcribe(b"wav")
    assert first.provider == "sarvam" and (primary.calls, fallback.calls) == (1, 1)
    second = await chain.transcribe(b"wav")  # inside the cool-down: gemini is not called
    assert second.provider == "sarvam" and (primary.calls, fallback.calls) == (1, 2)

    clock.now += settings.SPEECH_RATE_LIMIT_COOLDOWN_S + 1
    primary.behaviour = "ok"
    third = await chain.transcribe(b"wav")
    assert third.provider == "gemini" and primary.calls == 2


@pytest.mark.asyncio
async def test_an_ordinary_failure_falls_back_but_does_not_start_a_cooldown(clock: Clock) -> None:
    primary = _StubSTT("gemini", "down")
    fallback = _StubSTT("sarvam", "ok")
    chain = FallbackSTT(primary, fallback, "gemini", "sarvam")  # type: ignore[arg-type]
    await chain.transcribe(b"wav")
    await chain.transcribe(b"wav")
    assert primary.calls == 2 and fallback.calls == 2


@pytest.mark.asyncio
async def test_both_limited_or_down_raises_stt_unavailable(clock: Clock) -> None:
    chain = FallbackSTT(
        _StubSTT("gemini", "limited"),  # type: ignore[arg-type]
        _StubSTT("sarvam", "down"),  # type: ignore[arg-type]
        "gemini",
        "sarvam",
    )
    with pytest.raises(STTUnavailable):
        await chain.transcribe(b"wav")
    with pytest.raises(STTUnavailable):  # still inside the cool-down: only the fallback is tried
        await chain.transcribe(b"wav")


# ── the real providers against a fake server: Gemini 429, then Sarvam, then type instead ───────
class FakeSpeechServer:
    def __init__(self) -> None:
        self.gemini_calls = 0
        self.sarvam_calls = 0
        self.gemini_status = 429
        self.sarvam_status = 200

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.url.host == GEMINI_HOST:
            self.gemini_calls += 1
            return httpx.Response(self.gemini_status, text='{"error": "RESOURCE_EXHAUSTED"}')
        if request.url.host == SARVAM_HOST:
            self.sarvam_calls += 1
            if self.sarvam_status != 200:
                return httpx.Response(self.sarvam_status, text="down")
            if request.url.path.endswith("/speech-to-text"):
                return httpx.Response(200, json={"transcript": "रवि, कैसे किया?"})
            return httpx.Response(
                200, json={"audios": [base64.b64encode(_wav(0.2)).decode("ascii")]}
            )
        raise AssertionError(f"unexpected host {request.url.host}")


@pytest.fixture
def server(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeSpeechServer]:
    async def passthrough(wav: bytes) -> bytes:
        return wav

    async def one_second(_wav: bytes) -> float:
        return 1.0

    async def whole_clip(wav: bytes, max_s: float = 25.0) -> list[bytes]:
        return [wav]

    # no ffmpeg in these tests: audio handling is not what is under test
    monkeypatch.setattr(stt_mod, "trim_silence", passthrough)
    monkeypatch.setattr(stt_mod, "duration_s", one_second)
    monkeypatch.setattr(stt_mod, "split_for_stt", whole_clip)
    srv = FakeSpeechServer()
    client = httpx.AsyncClient(transport=httpx.MockTransport(srv.handler))
    monkeypatch.setattr(stt_mod, "get_speech_http_client", lambda: client)
    monkeypatch.setattr(tts_mod, "get_speech_http_client", lambda: client)
    monkeypatch.setattr(settings, "STT_PROVIDER", "gemini")
    monkeypatch.setattr(settings, "STT_FALLBACK_PROVIDER", "sarvam")
    monkeypatch.setattr(settings, "TTS_PROVIDER", "gemini")
    monkeypatch.setattr(settings, "TTS_FALLBACK_PROVIDER", "sarvam")
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "gemini-test-key")
    monkeypatch.setattr(settings, "SARVAM_API_KEY", "sarvam-test-key")
    yield srv


@pytest.mark.asyncio
async def test_gemini_429_on_a_voice_note_falls_back_to_sarvam(
    server: FakeSpeechServer, clock: Clock
) -> None:
    result = await get_stt_provider().transcribe(_wav())
    assert result.provider == "sarvam" and "रवि" in result.text
    assert (server.gemini_calls, server.sarvam_calls) == (1, 1)
    again = await get_stt_provider().transcribe(_wav())  # a new provider object, same cool-down
    assert again.provider == "sarvam" and server.gemini_calls == 1  # gemini not asked again
    assert server.sarvam_calls == 2


@pytest.mark.asyncio
async def test_when_sarvam_fails_too_the_whatsapp_path_asks_the_teacher_to_type(
    server: FakeSpeechServer, clock: Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    from datetime import UTC, datetime
    from uuid import uuid4

    from backend.app.core import conversation as conversation_mod

    async def keep(wav: bytes, mime: str | None = None) -> bytes:
        return wav

    async def no_hints(_teacher_id: Any) -> list[str]:
        return []

    monkeypatch.setattr(conversation_mod, "to_wav16k", keep)
    monkeypatch.setattr(conversation_mod, "scene_child_name_hints", no_hints)
    server.sarvam_status = 500
    service = ConversationService(stt_provider=get_stt_provider())
    inbound = InboundMessage(
        channel="whatsapp",
        channel_msg_id="m-limit",
        teacher_id=uuid4(),
        kind="audio",
        audio_bytes=_wav(),
        received_at=datetime.now(UTC),
    )
    out = await service.handle(inbound)
    assert len(out) == 1
    assert out[0].text_hi == get_message("stt_unavailable_type_please", "f")
    assert "लिखकर" in (out[0].text_hi or "")  # a next step, never blank or a raw error


# ── TTS: Gemini 429, then Sarvam, then text without audio ───────────────────────────────────
@pytest.mark.asyncio
async def test_gemini_tts_429_falls_back_to_sarvam_and_then_is_skipped(
    server: FakeSpeechServer, clock: Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    class NoCache:
        async def get(self, *_a: Any, **_k: Any) -> None:
            return None

        async def put_wav(self, *_a: Any, **_k: Any) -> None:
            return None

    monkeypatch.setattr(tts_mod, "tts_cache", NoCache())
    voice = get_voice("coach")  # adult voice: no pitch shift, so no ffmpeg in the test
    first = await get_tts_provider().synthesize("बहुत अच्छा।", voice)
    assert first.audio and (server.gemini_calls, server.sarvam_calls) == (1, 1)
    await get_tts_provider().synthesize("एक बार और।", voice)
    assert server.gemini_calls == 1 and server.sarvam_calls == 2  # gemini skipped in the cool-down


class _StubTTS:
    provider_name = "stub"

    def __init__(self, behaviour: str) -> None:
        self.behaviour = behaviour

    async def synthesize(self, text_hi: str, voice: Any) -> Any:
        if self.behaviour == "limited":
            raise TTSRateLimited("limited")
        raise TTSUnavailable("down")


@pytest.mark.asyncio
async def test_both_tts_providers_failing_raises_so_callers_send_text_only(clock: Clock) -> None:
    chain = FallbackTTS(_StubTTS("limited"), _StubTTS("down"), "gemini", "sarvam")  # type: ignore[arg-type]
    with pytest.raises(TTSUnavailable):
        await chain.synthesize("x", get_voice("ravi"))
