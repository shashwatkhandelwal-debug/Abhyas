"""Text-to-Speech (TTS) interface and provider protocol (spec/06 §6.3).

Task T17 implements Sarvam TTS, pitch shifting, caching, and voices.
"""

from typing import Protocol

from pydantic import BaseModel


class VoiceSpec(BaseModel):
    provider_speaker: str
    model: str
    pace: float = 1.0
    pitch_factor: float = 1.0


class TTSProvider(Protocol):
    async def synthesize(self, text_hi: str, voice: VoiceSpec) -> bytes:
        """Synthesize Hindi text to WAV 22.05 kHz mono audio bytes."""
        ...


class MockTTS:
    """Mock TTS provider returning synthetic audio."""

    async def synthesize(self, text_hi: str, voice: VoiceSpec) -> bytes:
        raise NotImplementedError("Spec 06 §6.3: Implemented in T17")


def get_tts_provider() -> TTSProvider:
    """Returns configured TTS provider instance."""
    raise NotImplementedError("Spec 06 §6.3: Implemented in T17")
