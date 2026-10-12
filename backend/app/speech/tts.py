"""Text-to-Speech (TTS) interface, VoiceSpec model, and provider implementations (spec/06 §6.3).

Includes Sarvam AI TTS (bulbul:v3), sentence chunking for long scripts,
digit-to-Hindi-word pronunciation conversion, pitch shifting, and MockTTS.
"""

from __future__ import annotations

import asyncio
import base64
import io
import logging
import re
import wave
from typing import Protocol

import httpx

from backend.app.config import settings
from backend.app.llm.hindi_numbers import to_words
from backend.app.speech.audio import pitch_shift
from backend.app.speech.cache import compute_cache_key, tts_cache
from backend.app.speech.client import get_speech_http_client
from backend.app.speech.spend import calculate_tts_cost, speech_budget
from backend.app.speech.voices import VoiceSpec, get_voice

logger = logging.getLogger("abhyas.speech.tts")


class TTSError(Exception):
    """Base exception for text-to-speech errors."""

    pass


class TTSUnavailable(TTSError):
    """Raised when TTS provider is unavailable or exhausted retries (spec/06 §6.3)."""

    pass


def convert_digits_for_tts(text_hi: str) -> str:
    """Converts Arabic digits in text to Hindi number words for TTS (spec/06 §6.3).

    Ensures "45" is spoken as "पैंतालीस", not "four five".
    """

    def _replace(match: re.Match[str]) -> str:
        try:
            num = int(match.group(0))
            if 0 <= num <= 199:
                return to_words(num)
        except Exception:
            pass
        return match.group(0)

    return re.sub(r"\b\d+\b", _replace, text_hi)


def split_sentences_for_tts(text_hi: str, max_chars: int = 1500) -> list[str]:
    """Splits long text into sentence chunks under max_chars for TTS (spec/06 §6.3).

    Splits at Devanagari purna viram (।), question mark (?), exclamation (!), or newlines.
    """
    if len(text_hi) <= max_chars:
        return [text_hi]

    # Split by sentence terminators while preserving them
    sentences = re.split(r"([।?!;\n]+)", text_hi)
    chunks: list[str] = []
    current_chunk = ""

    i = 0
    while i < len(sentences):
        sentence_part = sentences[i]
        delimiter = sentences[i + 1] if i + 1 < len(sentences) else ""
        i += 2

        combined = (sentence_part + delimiter).strip()
        if not combined:
            continue

        if len(current_chunk) + len(combined) + 1 <= max_chars:
            current_chunk = f"{current_chunk} {combined}".strip() if current_chunk else combined
        else:
            if current_chunk:
                chunks.append(current_chunk)
            current_chunk = combined

    if current_chunk:
        chunks.append(current_chunk)

    return chunks if chunks else [text_hi]


class TTSProvider(Protocol):
    """Protocol for TTS providers (spec/06 §6.3)."""

    async def synthesize(self, text_hi: str, voice: VoiceSpec) -> tuple[bytes, str]:
        """Synthesizes Hindi text to WAV 22.05 kHz mono audio bytes and returns (wav_bytes, cache_key)."""
        ...


class MockTTS:
    """Mock TTS provider returning synthetic WAV audio bytes (spec/06 §6.3).

    Generates a valid 22.05 kHz mono WAV whose length is proportional
    to text length (so latency calculations and audio players work).
    """

    async def synthesize(self, text_hi: str, voice: VoiceSpec) -> tuple[bytes, str]:
        """Synthesizes mock WAV audio and returns (wav_bytes, cache_key)."""
        cache_key = compute_cache_key(text_hi, voice.provider_speaker, voice)
        if not text_hi or not text_hi.strip():
            return b"", cache_key

        cached_audio = (
            await tts_cache.get(cache_key, "ogg")
            or await tts_cache.get(cache_key, "mp3")
            or await tts_cache.get(cache_key, "wav")
        )
        if cached_audio is not None:
            return cached_audio, cache_key

        clean_text = convert_digits_for_tts(text_hi)
        # Duration proportional to character count: ~0.06s per character, min 0.5s, max 10.0s
        duration_s = max(0.5, min(10.0, len(clean_text) * 0.06))
        sample_rate = 22050
        n_frames = int(sample_rate * duration_s)

        out_io = io.BytesIO()
        with wave.open(out_io, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            # Write silent frames
            wf.writeframes(b"\x00\x00" * n_frames)

        raw_wav = out_io.getvalue()
        if abs(voice.pitch_factor - 1.0) > 0.001:
            try:
                raw_wav = await pitch_shift(raw_wav, voice.pitch_factor)
            except Exception:
                pass

        await tts_cache.put_wav(cache_key, raw_wav)
        return raw_wav, cache_key


class SarvamTTS:
    """Sarvam AI Text-to-Speech provider (spec/06 §6.3).

    Calls POST https://api.sarvam.ai/text-to-speech with bulbul:v3 model.
    Applies pitch shifting for child personas when voice.pitch_factor != 1.0.
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout_s: float | None = None,
    ) -> None:
        self.api_key = api_key or settings.SARVAM_API_KEY
        self.base_url = (base_url or settings.SARVAM_BASE_URL).rstrip("/")
        self.timeout_s = timeout_s or settings.LLM_TIMEOUT_SECONDS

    async def _synthesize_chunk(
        self,
        client: httpx.AsyncClient,
        text_chunk: str,
        voice: VoiceSpec,
    ) -> bytes:
        """Synthesizes a single text chunk with 1 retry on failure."""
        url = f"{self.base_url}/text-to-speech"
        headers = {
            "api-subscription-key": self.api_key,
            "Content-Type": "application/json",
        }
        payload = {
            "text": text_chunk,
            "language_code": "hi-IN",
            "model": voice.model,
            "speaker": voice.provider_speaker,
            "pace": voice.pace,
            "speech_sample_rate": 22050,
        }

        max_retries = 1
        last_error: Exception | None = None

        for attempt in range(max_retries + 1):
            try:
                response = await client.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=self.timeout_s,
                )
                if response.status_code >= 500 and attempt < max_retries:
                    logger.warning(
                        "Sarvam TTS returned status %d, retrying...", response.status_code
                    )
                    await asyncio.sleep(0.5)
                    continue

                response.raise_for_status()
                result_json = response.json()
                audios = result_json.get("audios", [])
                if not audios:
                    raise TTSUnavailable("Sarvam TTS returned empty audios array")

                b64_data = audios[0]
                return base64.b64decode(b64_data)

            except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as exc:
                last_error = exc
                if attempt < max_retries:
                    logger.warning(
                        "Sarvam TTS attempt %d failed (%s), retrying...", attempt + 1, exc
                    )
                    await asyncio.sleep(0.5)
                    continue

        raise TTSUnavailable(f"Sarvam TTS failed after retries: {last_error}") from last_error

    async def synthesize(self, text_hi: str, voice: VoiceSpec) -> tuple[bytes, str]:
        """Synthesizes Hindi text to WAV 22.05 kHz mono audio bytes (spec/06 §6.3)."""
        cache_key = compute_cache_key(text_hi, voice.provider_speaker, voice)
        if not text_hi or not text_hi.strip():
            return b"", cache_key

        # Check cache for delivered format (ogg/mp3/wav) before budget check or provider calls
        cached_audio = (
            await tts_cache.get(cache_key, "ogg")
            or await tts_cache.get(cache_key, "mp3")
            or await tts_cache.get(cache_key, "wav")
        )
        if cached_audio is not None:
            return cached_audio, cache_key

        # Budget guard: if cap exceeded, fallback to Bhashini (if configured) -> lite mode (CHANGES 254f622 Item 2)
        if settings.SPEECH_PROVIDER_LIVE:
            cost = calculate_tts_cost(text_hi)
            if not await speech_budget.can_spend(cost):
                logger.warning(
                    "Sarvam TTS budget exceeded (cost %.4f INR). Checking Bhashini fallback...",
                    cost,
                )
                if settings.BHASHINI_API_KEY:
                    try:
                        bhashini = BhashiniTTS()
                        return await bhashini.synthesize(text_hi, voice)
                    except Exception as exc:
                        logger.warning(
                            "Bhashini fallback failed: %s. Falling back to lite mode.", exc
                        )
                return b"", cache_key
            await speech_budget.record_spend("sarvam", "tts", len(text_hi), cost)

        # 1. Convert numerals in child lines / text to Hindi words (spec/06 §6.3)
        prepared_text = convert_digits_for_tts(text_hi)

        # 2. Chunk text if > 1500 chars (learn scripts)
        chunks = split_sentences_for_tts(prepared_text, max_chars=1500)

        client = get_speech_http_client()
        wav_parts: list[bytes] = []
        for chunk in chunks:
            part = await self._synthesize_chunk(client, chunk, voice)
            wav_parts.append(part)

        # Combine WAV parts if chunked
        if len(wav_parts) == 1:
            raw_wav = wav_parts[0]
        else:
            raw_wav = _concat_wav_bytes(wav_parts)

        # 3. Apply pitch shift if child voice (voice.pitch_factor != 1.0)
        if abs(voice.pitch_factor - 1.0) > 0.001:
            raw_wav = await pitch_shift(raw_wav, voice.pitch_factor)

        # Store synthesized audio in cache
        await tts_cache.put_wav(cache_key, raw_wav)

        return raw_wav, cache_key


class BhashiniTTS:
    """Bhashini TTS provider via ULCA pipeline API (spec/06 §6.3)."""

    def __init__(
        self,
        api_key: str | None = None,
        user_id: str | None = None,
        pipeline_url: str = "https://dhruva-api.bhashini.gov.in/services/inference/pipeline",
    ) -> None:
        self.api_key = api_key or settings.BHASHINI_API_KEY
        self.user_id = user_id or settings.BHASHINI_USER_ID
        self.pipeline_url = pipeline_url
        if not self.api_key:
            raise TTSUnavailable("Bhashini TTS is not configured (BHASHINI_API_KEY missing)")

    async def synthesize(self, text_hi: str, voice: VoiceSpec) -> tuple[bytes, str]:
        """Synthesizes Hindi text to WAV audio via Bhashini ULCA pipeline."""
        cache_key = compute_cache_key(text_hi, voice.provider_speaker, voice)
        if not text_hi or not text_hi.strip():
            return b"", cache_key

        cached_audio = (
            await tts_cache.get(cache_key, "ogg")
            or await tts_cache.get(cache_key, "mp3")
            or await tts_cache.get(cache_key, "wav")
        )
        if cached_audio is not None:
            return cached_audio, cache_key

        if settings.SPEECH_PROVIDER_LIVE:
            await speech_budget.record_spend("bhashini", "tts", len(text_hi), 0.0)

        prepared_text = convert_digits_for_tts(text_hi)
        client = get_speech_http_client()
        # Item 4: remove hardcoded speaker list, use voice.gender directly
        gender = "female" if voice.gender == "f" else "male"

        payload = {
            "pipelineTasks": [
                {
                    "taskType": "tts",
                    "config": {
                        "language": {"sourceLanguage": "hi"},
                        "serviceId": "ai4bharat/indic-tts-hi--gpu",
                        "gender": gender,
                    },
                }
            ],
            "inputData": {
                "input": [{"source": prepared_text}],
            },
        }
        headers = {
            "Authorization": self.api_key,
            "userID": self.user_id,
            "ulcaApiKey": self.api_key,
            "Content-Type": "application/json",
        }

        try:
            resp = await client.post(
                self.pipeline_url,
                json=payload,
                headers=headers,
                timeout=settings.LLM_TIMEOUT_SECONDS,
            )
            resp.raise_for_status()
            data = resp.json()
            pipeline_response = data.get("pipelineResponse", [])
            if not pipeline_response or not pipeline_response[0].get("audio"):
                raise TTSUnavailable("Bhashini TTS returned empty audio response")
            b64_audio = pipeline_response[0]["audio"][0].get("audioContent", "")
            raw_wav = base64.b64decode(b64_audio)
        except Exception as exc:
            raise TTSUnavailable(f"Bhashini TTS request failed: {exc}") from exc

        if abs(voice.pitch_factor - 1.0) > 0.001:
            raw_wav = await pitch_shift(raw_wav, voice.pitch_factor)

        await tts_cache.put_wav(cache_key, raw_wav)
        return raw_wav, cache_key


def _concat_wav_bytes(wav_chunks: list[bytes]) -> bytes:
    """Concatenates multiple 22.05 kHz 16-bit mono WAV audio chunks."""
    all_frames = b""
    sample_rate = 22050

    for chunk in wav_chunks:
        try:
            with wave.open(io.BytesIO(chunk), "rb") as wf:
                sample_rate = wf.getframerate()
                all_frames += wf.readframes(wf.getnframes())
        except Exception:
            pass

    out_io = io.BytesIO()
    with wave.open(out_io, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(all_frames)

    return out_io.getvalue()


def get_tts_provider() -> TTSProvider:
    """Returns configured TTS provider instance (spec/06 §6.3)."""
    if settings.TTS_PROVIDER == "mock" or (
        settings.TTS_PROVIDER == "sarvam"
        and not settings.SARVAM_API_KEY
        and settings.ENVIRONMENT != "production"
    ):
        return MockTTS()

    if settings.TTS_PROVIDER == "sarvam":
        return SarvamTTS()

    if settings.TTS_PROVIDER == "bhashini":
        return BhashiniTTS()

    return MockTTS()


__all__ = [
    "VoiceSpec",
    "get_voice",
    "TTSProvider",
    "MockTTS",
    "SarvamTTS",
    "BhashiniTTS",
    "get_tts_provider",
    "convert_digits_for_tts",
    "split_sentences_for_tts",
    "TTSError",
    "TTSUnavailable",
]
