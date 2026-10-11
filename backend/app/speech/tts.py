"""Text-to-Speech (TTS) interface, VoiceSpec model, and provider protocol (spec/06 §6.3).

Task T17 implements Sarvam TTS, pitch shifting, caching, and voices.
"""

from typing import Protocol

from pydantic import BaseModel


class VoiceSpec(BaseModel):
    """Specification of voice model, speaker, pacing, and pitch factor (spec/06 §6.3)."""

    provider_speaker: str
    model: str
    pace: float = 1.0
    pitch_factor: float = 1.0


class TTSProvider(Protocol):
    """Protocol for TTS providers (spec/06 §6.3)."""

    async def synthesize(self, text_hi: str, voice: VoiceSpec) -> bytes:
        """Synthesizes Hindi text to WAV 22.05 kHz mono audio bytes."""
        ...


class MockTTS:
    """Mock TTS provider returning synthetic audio bytes (spec/06 §6.3)."""

    async def synthesize(self, text_hi: str, voice: VoiceSpec) -> bytes:
        """Returns dummy 44-byte WAV header for testing without hitting external API."""
        return b"RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00D\xac\x00\x00\x88X\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00"


def get_tts_provider() -> TTSProvider:
    """Returns configured TTS provider instance (owned by Lane B in T17)."""
    return MockTTS()
