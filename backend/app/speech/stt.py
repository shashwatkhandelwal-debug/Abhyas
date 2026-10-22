"""Speech-to-Text (STT) interface, Transcript model, and provider implementations (spec/06 §6.2).

Includes Sarvam STT with auto-splitting for clips > 25s, keyterm boosting,
MockSTT with fixture matching, and fallback error handling.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import re
import time
import unicodedata
from pathlib import Path
from typing import Protocol

import httpx
from pydantic import BaseModel

from backend.app.config import settings
from backend.app.speech.audio import duration_s, split_for_stt, trim_silence
from backend.app.speech.client import get_speech_http_client
from backend.app.speech.gemini import model_output_items, post_interaction
from backend.app.speech.spend import SpeechBudgetExceededError, speech_budget

logger = logging.getLogger("abhyas.speech.stt")


class STTError(Exception):
    """Base exception for speech-to-text errors."""

    pass


class STTUnavailable(STTError):
    """Raised when STT service is unavailable, timed out, or exhausted retries (spec/06 §6.2)."""

    pass


class ProviderNotConfigured(STTError):
    """Raised when an optional STT provider (Bhashini, Google) lacks API credentials."""

    pass


class Transcript(BaseModel):
    """Normalized transcript result from an STT provider (spec/06 §6.2)."""

    text: str
    confidence: float
    language: str | None = None
    provider: str
    ms: int


def normalize_transcript_text(text: str) -> str:
    """Normalizes transcript text to NFC and collapses whitespace (spec/06 §6.2).

    Retains original numerals.
    """
    if not text:
        return ""
    # NFC normalization (spec requirement)
    norm = unicodedata.normalize("NFC", text)
    # Collapse multiple whitespace characters into single space
    norm = re.sub(r"\s+", " ", norm).strip()
    return norm


def calculate_confidence(text: str, returned_confidence: float | None = None) -> float:
    """Calculates confidence score (spec/06 §6.2).

    Set confidence = 0.9 when transcript is non-empty and contains >= 1 Devanagari or Latin word,
    else 0.0, unless provider explicitly returned a valid probability.
    """
    if returned_confidence is not None and 0.0 <= returned_confidence <= 1.0:
        return returned_confidence

    if not text or not text.strip():
        return 0.0

    # Check for at least 1 Devanagari (\u0900-\u097F) or Latin character
    if re.search(r"[\u0900-\u097Fa-zA-Z]", text):
        return 0.9

    return 0.0


class STTProvider(Protocol):
    """Protocol for STT providers (spec/06 §6.2)."""

    async def transcribe(
        self,
        wav16k: bytes,
        lang: str = "hi-IN",
        keyterms: list[str] | None = None,
    ) -> Transcript:
        """Transcribes 16kHz mono WAV audio to Hindi text."""
        ...


class SarvamSTT:
    """Sarvam AI Speech-to-Text provider (spec/06 §6.2).

    Calls POST https://api.sarvam.ai/speech-to-text with multipart/form-data.
    Clips > 25s are automatically split and processed in parallel.
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout_s: float | None = None,
        max_retries: int | None = None,
    ) -> None:
        self.api_key = api_key or settings.SARVAM_API_KEY
        self.base_url = (base_url or settings.SARVAM_BASE_URL).rstrip("/")
        self.model = model or settings.SARVAM_STT_MODEL
        self.timeout_s = timeout_s or settings.STT_TIMEOUT_S
        self.max_retries = settings.SPEECH_MAX_RETRIES if max_retries is None else max_retries

    async def _transcribe_single_clip(
        self,
        client: httpx.AsyncClient,
        clip_wav: bytes,
        lang: str,
        keyterms: list[str] | None = None,
    ) -> tuple[str, float]:
        """Transcribes a single audio clip <= 25s; retries up to self.max_retries on timeout/5xx."""
        url = f"{self.base_url}/speech-to-text"
        headers = {"api-subscription-key": self.api_key}

        # Format keyterms JSON array up to 50 items (spec/06 §6.2)
        keyterms_payload: str = "[]"
        if keyterms:
            keyterms_payload = json.dumps(keyterms[:50], ensure_ascii=False)

        files = {"file": ("audio.wav", clip_wav, "audio/wav")}
        data = {
            "model": self.model,
            "language_code": lang,
            "keyterms": keyterms_payload,
        }

        max_retries = self.max_retries
        last_error: Exception | None = None

        for attempt in range(max_retries + 1):
            try:
                response = await client.post(
                    url,
                    headers=headers,
                    files=files,
                    data=data,
                    timeout=self.timeout_s,
                )
                if response.status_code >= 500 and attempt < max_retries:
                    logger.warning(
                        "Sarvam STT returned status %d, retrying...", response.status_code
                    )
                    await asyncio.sleep(0.5)
                    continue

                response.raise_for_status()
                result_json = response.json()
                raw_text = result_json.get("transcript", "")
                language_prob = result_json.get("language_probability")
                prob_float = float(language_prob) if language_prob is not None else None
                conf = calculate_confidence(raw_text, returned_confidence=prob_float)
                return raw_text, conf

            except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as exc:
                last_error = exc
                if attempt < max_retries:
                    logger.warning(
                        "Sarvam STT attempt %d failed (%s), retrying...", attempt + 1, exc
                    )
                    await asyncio.sleep(0.5)
                    continue

        raise STTUnavailable(f"Sarvam STT failed after retry: {last_error}") from last_error

    async def transcribe(
        self,
        wav16k: bytes,
        lang: str = "hi-IN",
        keyterms: list[str] | None = None,
    ) -> Transcript:
        """Transcribes 16kHz mono WAV audio to Hindi text (spec/06 §6.2)."""
        if not wav16k:
            return Transcript(text="", confidence=0.0, language=lang, provider="sarvam", ms=0)

        t0 = time.perf_counter()
        if keyterms:
            logger.info("stt_hint_used provider=sarvam n=%d", len(keyterms))

        # Trim leading and trailing silence
        wav16k = await trim_silence(wav16k)

        # Check if splitting is necessary (Sarvam limit < 30s)
        dur = await duration_s(wav16k)
        try:
            await speech_budget.check_and_record_stt(dur, provider="sarvam")
        except SpeechBudgetExceededError:
            if settings.BHASHINI_API_KEY:
                try:
                    logger.info("Sarvam STT budget exceeded, falling back to Bhashini STT")
                    bhashini = BhashiniSTT()
                    return await bhashini.transcribe(wav16k, lang=lang, keyterms=keyterms)
                except Exception as bhash_exc:
                    logger.warning("Bhashini STT fallback failed: %s", bhash_exc)
                    raise
            raise

        if dur > 25.0:
            clips = await split_for_stt(wav16k, max_s=25.0)
        else:
            clips = [wav16k]

        client = get_speech_http_client()
        if len(clips) == 1:
            text, conf = await self._transcribe_single_clip(client, clips[0], lang, keyterms)
        else:
            results = await asyncio.gather(
                *(self._transcribe_single_clip(client, clip, lang, keyterms) for clip in clips)
            )
            text_parts = [t for (t, _) in results if t.strip()]
            text = " ".join(text_parts)
            conf = sum(c for (_, c) in results) / len(results) if results else 0.0

        latency_ms = int((time.perf_counter() - t0) * 1000)
        norm_text = normalize_transcript_text(text)

        return Transcript(
            text=norm_text,
            confidence=conf,
            language=lang,
            provider="sarvam",
            ms=latency_ms,
        )


class MockSTT:
    """Mock STT provider for tests and development (spec/06 §6.2).

    Returns fixture text if available (from backend/tests/fixtures/audio/*.json),
    or falls back to MOCK_STT_TEXT env.
    """

    def __init__(
        self,
        default_text: str | None = None,
        fixtures_dir: Path | str | None = None,
    ) -> None:
        self.default_text = default_text or settings.MOCK_STT_TEXT
        if fixtures_dir is None:
            self.fixtures_dir = Path(__file__).parents[2] / "tests" / "fixtures" / "audio"
        else:
            self.fixtures_dir = Path(fixtures_dir)

    def _find_fixture_text(self, wav16k: bytes) -> str | None:
        """Looks for a json fixture in fixtures directory matching the audio."""
        if not self.fixtures_dir.is_dir():
            return None

        # Check direct audio hash match
        content_hash = hashlib.sha256(wav16k).hexdigest()[:8]
        for f in self.fixtures_dir.glob("*.json"):
            if content_hash in f.stem:
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                    if isinstance(data, dict) and "text" in data:
                        return str(data["text"])
                except Exception:
                    continue

        # Check sample_5s.json fixture default
        default_fixture = self.fixtures_dir / "sample_5s.json"
        if default_fixture.is_file():
            try:
                data = json.loads(default_fixture.read_text(encoding="utf-8"))
                if isinstance(data, dict) and "text" in data:
                    return str(data["text"])
            except Exception:
                pass

        return None

    async def transcribe(
        self,
        wav16k: bytes,
        lang: str = "hi-IN",
        keyterms: list[str] | None = None,
    ) -> Transcript:
        """Returns mock transcript with fixture or default Hindi text."""
        fixture_text = self._find_fixture_text(wav16k)
        raw_text = fixture_text if fixture_text is not None else self.default_text
        norm_text = normalize_transcript_text(raw_text)
        conf = calculate_confidence(norm_text)

        return Transcript(
            text=norm_text,
            confidence=conf,
            language=lang,
            provider="mock",
            ms=100,
        )


class BhashiniSTT:
    """Bhashini STT provider via ULCA pipeline API (spec/06 §6.2)."""

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
            raise ProviderNotConfigured("Bhashini STT is not configured (BHASHINI_API_KEY missing)")

    async def transcribe(
        self,
        wav16k: bytes,
        lang: str = "hi-IN",
        keyterms: list[str] | None = None,
    ) -> Transcript:
        """Transcribes 16kHz mono WAV audio to Hindi text via Bhashini ULCA pipeline."""
        if not wav16k:
            return Transcript(text="", confidence=0.0, language=lang, provider="bhashini", ms=0)

        t0 = time.perf_counter()
        wav16k = await trim_silence(wav16k)
        dur = await duration_s(wav16k)
        await speech_budget.check_and_record_stt(dur, provider="bhashini")

        client = get_speech_http_client()
        b64_audio = base64.b64encode(wav16k).decode("utf-8")
        source_lang = lang.split("-")[0] if "-" in lang else lang

        payload = {
            "pipelineTasks": [
                {
                    "taskType": "asr",
                    "config": {
                        "language": {"sourceLanguage": source_lang},
                        "serviceId": "ai4bharat/conformer-hi-gpu--gpu",
                    },
                }
            ],
            "inputData": {
                "audio": [{"audioContent": b64_audio}],
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
                timeout=settings.STT_TIMEOUT_S,
            )
            resp.raise_for_status()
            data = resp.json()
            pipeline_response = data.get("pipelineResponse", [])
            raw_text = ""
            if pipeline_response:
                outputs = pipeline_response[0].get("output", [])
                if outputs:
                    raw_text = outputs[0].get("source", "")
        except Exception as exc:
            raise STTUnavailable(f"Bhashini STT request failed: {exc}") from exc

        latency_ms = int((time.perf_counter() - t0) * 1000)
        norm_text = normalize_transcript_text(raw_text)
        conf = calculate_confidence(norm_text)
        return Transcript(
            text=norm_text,
            confidence=conf,
            language=lang,
            provider="bhashini",
            ms=latency_ms,
        )


class GoogleSTT:
    """Google Cloud Speech-to-Text v2 stub (optional) (spec/06 §6.2)."""

    def __init__(self) -> None:
        if not settings.GOOGLE_APPLICATION_CREDENTIALS:
            raise ProviderNotConfigured(
                "Google STT is not configured (GOOGLE_APPLICATION_CREDENTIALS missing)"
            )

    async def transcribe(
        self,
        wav16k: bytes,
        lang: str = "hi-IN",
        keyterms: list[str] | None = None,
    ) -> Transcript:
        raise ProviderNotConfigured("Google STT integration pending credentials")


class GeminiSTT:
    """Gemini audio-understanding STT via the Interactions API (spec/06 §6.2).

    Sends the whole 16 kHz WAV inline (base64) with a verbatim-transcription
    instruction; keyterms are passed as spelling hints in the instruction.
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout_s: float | None = None,
        max_retries: int | None = None,
    ) -> None:
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.base_url = base_url or settings.GEMINI_BASE_URL
        self.model = model or settings.GEMINI_STT_MODEL
        self.timeout_s = timeout_s or settings.STT_TIMEOUT_S
        self.max_retries = settings.SPEECH_MAX_RETRIES if max_retries is None else max_retries

    @staticmethod
    def _instruction(keyterms: list[str] | None) -> str:
        instruction = (
            "Transcribe this Hindi audio verbatim in Devanagari script. "
            "Write numbers exactly as spoken. Return only the transcript, "
            "with no translation, labels, quotes or commentary."
        )
        if keyterms:
            hints = ", ".join(keyterms[: settings.GEMINI_STT_MAX_KEYTERMS])
            instruction += f" Spelling hints for words that may occur: {hints}"
        return instruction

    async def transcribe(
        self,
        wav16k: bytes,
        lang: str = "hi-IN",
        keyterms: list[str] | None = None,
    ) -> Transcript:
        """Transcribes 16kHz mono WAV audio to Hindi text via Gemini (spec/06 §6.2)."""
        if not wav16k:
            return Transcript(text="", confidence=0.0, language=lang, provider="gemini", ms=0)

        t0 = time.perf_counter()
        if keyterms:
            logger.info("stt_hint_used provider=gemini n=%d", len(keyterms))
        wav16k = await trim_silence(wav16k)
        b64_audio = base64.b64encode(wav16k).decode("ascii")
        if len(b64_audio) > settings.GEMINI_STT_MAX_BYTES:
            raise STTUnavailable("Gemini STT clip exceeds inline request size limit")

        dur = await duration_s(wav16k)
        await speech_budget.check_and_record_stt(dur, provider="gemini")

        payload = {
            "model": self.model,
            "input": [
                {"type": "text", "text": self._instruction(keyterms)},
                {"type": "audio", "data": b64_audio, "mime_type": "audio/wav"},
            ],
        }
        body = await post_interaction(
            get_speech_http_client(),
            base_url=self.base_url,
            api_key=self.api_key,
            payload=payload,
            timeout_s=self.timeout_s,
            label="Gemini STT",
            error_cls=STTUnavailable,
            max_retries=self.max_retries,
        )
        if not isinstance(body.get("steps"), list):
            raise STTUnavailable("Gemini STT response has no steps")
        raw_text = "".join(str(item.get("text", "")) for item in model_output_items(body, "text"))

        latency_ms = int((time.perf_counter() - t0) * 1000)
        norm_text = normalize_transcript_text(raw_text)
        return Transcript(
            text=norm_text,
            confidence=calculate_confidence(norm_text, None),
            language=lang,
            provider="gemini",
            ms=latency_ms,
        )


class FallbackSTT:
    """Tries the primary STT provider, then the fallback on STTUnavailable (spec/06 §6.2)."""

    def __init__(
        self,
        primary: STTProvider,
        fallback: STTProvider,
        primary_name: str,
        fallback_name: str,
    ) -> None:
        self.primary = primary
        self.fallback = fallback
        self.primary_name = primary_name
        self.fallback_name = fallback_name

    async def transcribe(
        self,
        wav16k: bytes,
        lang: str = "hi-IN",
        keyterms: list[str] | None = None,
    ) -> Transcript:
        try:
            return await self.primary.transcribe(wav16k, lang=lang, keyterms=keyterms)
        except STTUnavailable:
            logger.warning(
                "STT provider %s unavailable, falling back to %s",
                self.primary_name,
                self.fallback_name,
            )
        try:
            return await self.fallback.transcribe(wav16k, lang=lang, keyterms=keyterms)
        except STTUnavailable as exc:
            logger.error(
                "STT providers %s and %s both unavailable", self.primary_name, self.fallback_name
            )
            raise STTUnavailable(
                f"STT providers {self.primary_name} and {self.fallback_name} both unavailable"
            ) from exc


def _build_stt_provider(name: str, max_retries: int | None = None) -> STTProvider:
    """Builds one STT provider; keyless Sarvam/Gemini become MockSTT outside production."""
    if name == "mock":
        return MockSTT()

    if name == "sarvam":
        if not settings.SARVAM_API_KEY and settings.ENVIRONMENT != "production":
            return MockSTT()
        return SarvamSTT(max_retries=max_retries)

    if name == "gemini":
        if not settings.GEMINI_API_KEY and settings.ENVIRONMENT != "production":
            return MockSTT()
        return GeminiSTT(max_retries=max_retries)

    if name == "bhashini":
        return BhashiniSTT()

    if name == "google":
        return GoogleSTT()

    return MockSTT()


def get_stt_provider() -> STTProvider:
    """Returns configured STT provider instance based on settings (spec/06 §6.2).

    Wraps the primary in FallbackSTT only when STT_FALLBACK_PROVIDER is set and
    differs from STT_PROVIDER; the primary then gets no retry so a failing call
    hands over to the fallback after a single attempt.
    """
    fallback_name = settings.STT_FALLBACK_PROVIDER
    if fallback_name == "none" or fallback_name == settings.STT_PROVIDER:
        return _build_stt_provider(settings.STT_PROVIDER)

    try:
        fallback = _build_stt_provider(fallback_name)
    except ProviderNotConfigured:
        logger.warning("STT fallback provider %s not configured, using primary only", fallback_name)
        return _build_stt_provider(settings.STT_PROVIDER)
    primary = _build_stt_provider(settings.STT_PROVIDER, max_retries=0)
    return FallbackSTT(primary, fallback, settings.STT_PROVIDER, fallback_name)
