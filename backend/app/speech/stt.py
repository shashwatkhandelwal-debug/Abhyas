"""Speech-to-Text (STT) adapter interface and providers (§10)."""

from abc import ABC, abstractmethod

from pydantic import BaseModel

from backend.app.config import settings


class Transcript(BaseModel):
    text: str
    words: list[str] = []
    confidence: float = 1.0


class STTProvider(ABC):
    @abstractmethod
    async def transcribe(self, audio_bytes: bytes, lang_hint: str = "hi") -> Transcript:
        """Transcribe audio bytes to text. Deletes/does not persist raw audio."""
        pass


class IndicConformerSTT(STTProvider):
    """Adapter for self-hosted or API-backed AI4Bharat IndicConformer."""

    def __init__(self, endpoint: str = settings.STT_ENDPOINT):
        self.endpoint = endpoint

    async def transcribe(self, audio_bytes: bytes, lang_hint: str = "hi") -> Transcript:
        # In real deployment, posts audio to IndicConformer service
        # Audio is processed in memory and never written to permanent disk
        return Transcript(
            text="रवि, ५२ में से १७ कैसे घटाया? बताओ।",
            words=["रवि,", "५२", "में", "से", "१७", "कैसे", "घटाया?", "बताओ।"],
            confidence=0.95,
        )


class MockSTT(STTProvider):
    """Mock STT for testing and local development."""

    async def transcribe(self, audio_bytes: bytes, lang_hint: str = "hi") -> Transcript:
        return Transcript(
            text="Ravi, 52 mein se 17 kaise ghataya? Batao.",
            words=["Ravi,", "52", "mein", "se", "17", "kaise", "ghataya?", "Batao."],
            confidence=0.98,
        )


def get_stt_provider() -> STTProvider:
    if settings.STT_PROVIDER == "indic_conformer":
        return IndicConformerSTT()
    return MockSTT()
