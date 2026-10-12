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
from backend.app.speech.client import get_speech_http_client
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

    async def synthesize(self, text_hi: str, voice: VoiceSpec) -> bytes:
        """Synthesizes Hindi text to WAV 22.05 kHz mono audio bytes."""
        ...


class MockTTS:
    """Mock TTS provider returning synthetic WAV audio bytes (spec/06 §6.3).

    Generates a valid 22.05 kHz mono WAV whose length is proportional
    to text length (so latency calculations and audio players work).
    """

    async def synthesize(self, text_hi: str, voice: VoiceSpec) -> bytes:
        """Synthesizes mock WAV audio."""
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
                return await pitch_shift(raw_wav, voice.pitch_factor)
            except Exception:
                return raw_wav

        return raw_wav


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

    async def synthesize(self, text_hi: str, voice: VoiceSpec) -> bytes:
        """Synthesizes Hindi text to WAV 22.05 kHz mono audio bytes (spec/06 §6.3)."""
        if not text_hi or not text_hi.strip():
            return b""

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
            return await pitch_shift(raw_wav, voice.pitch_factor)

        return raw_wav


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

    return MockTTS()


__all__ = [
    "VoiceSpec",
    "get_voice",
    "TTSProvider",
    "MockTTS",
    "SarvamTTS",
    "get_tts_provider",
    "convert_digits_for_tts",
    "split_sentences_for_tts",
    "TTSError",
    "TTSUnavailable",
]
