"""Text-to-Speech (TTS) adapter interface and providers (§10)."""

from abc import ABC, abstractmethod
from typing import Optional
from backend.app.config import settings


class TTSProvider(ABC):
    @abstractmethod
    async def synthesize(self, text: str, voice_id: str, lang: str = "hi") -> bytes:
        """Synthesize text to speech (OGG/Opus format for WhatsApp)."""
        pass


class IndicParlerTTS(TTSProvider):
    """Adapter for AI4Bharat Indic Parler-TTS with distinct voices."""
    def __init__(self, endpoint: str = settings.TTS_ENDPOINT):
        self.endpoint = endpoint
        self._cache: dict[str, bytes] = {}

    async def synthesize(self, text: str, voice_id: str, lang: str = "hi") -> bytes:
        cache_key = f"{voice_id}:{text}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Synthesize audio bytes (simulated OGG payload in scaffold)
        dummy_ogg_header = b"OggS\x00\x02\x00\x00\x00\x00\x00\x00\x00\x00"
        audio_data = dummy_ogg_header + text.encode("utf-8")
        self._cache[cache_key] = audio_data
        return audio_data


class MockTTS(TTSProvider):
    """Mock TTS for testing and local development."""
    async def synthesize(self, text: str, voice_id: str, lang: str = "hi") -> bytes:
        return b"OggS\x00\x02\x00\x00\x00\x00\x00\x00\x00\x00mock_audio_bytes"


def get_tts_provider() -> TTSProvider:
    if settings.TTS_PROVIDER == "indic_parler_tts":
        return IndicParlerTTS()
    return MockTTS()
