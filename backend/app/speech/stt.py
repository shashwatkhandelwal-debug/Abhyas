"""Speech-to-Text (STT) interface, Transcript model, and provider protocol (spec/06 §6.2).

Task T16 implements Sarvam STT, split audio, and MockSTT.
"""

from typing import Protocol

from pydantic import BaseModel


class Transcript(BaseModel):
    """Normalized transcript result from an STT provider (spec/06 §6.2)."""

    text: str
    confidence: float
    language: str | None = None
    provider: str
    ms: int


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


class MockSTT:
    """Mock STT provider for tests and development (spec/06 §6.2)."""

    def __init__(self, default_text: str = "रवि, 52 में से 17 कैसे घटाया? बताओ।") -> None:
        self.default_text = default_text

    async def transcribe(
        self,
        wav16k: bytes,
        lang: str = "hi-IN",
        keyterms: list[str] | None = None,
    ) -> Transcript:
        """Returns mock transcript with default or fixture text."""
        return Transcript(
            text=self.default_text,
            confidence=0.9,
            language=lang,
            provider="mock",
            ms=100,
        )


def get_stt_provider() -> STTProvider:
    """Returns configured STT provider instance (owned by Lane B in T16)."""
    return MockSTT()
