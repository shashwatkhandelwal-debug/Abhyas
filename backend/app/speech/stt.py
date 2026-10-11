"""Speech-to-Text (STT) interface and provider protocol (spec/06 §6.2).

Task T16 implements Sarvam STT, split audio, and MockSTT.
"""

from typing import Protocol

from pydantic import BaseModel


class Transcript(BaseModel):
    text: str
    confidence: float
    language: str | None = None
    provider: str
    ms: int


class STTProvider(Protocol):
    async def transcribe(
        self, wav16k: bytes, lang: str = "hi-IN", keyterms: list[str] | None = None
    ) -> Transcript:
        """Transcribe 16kHz mono WAV audio to Hindi text."""
        ...


class MockSTT:
    """Mock STT provider for tests and development."""

    async def transcribe(
        self, wav16k: bytes, lang: str = "hi-IN", keyterms: list[str] | None = None
    ) -> Transcript:
        raise NotImplementedError("Spec 06 §6.2: Implemented in T16")


def get_stt_provider() -> STTProvider:
    """Returns configured STT provider instance."""
    raise NotImplementedError("Spec 06 §6.2: Implemented in T16")
