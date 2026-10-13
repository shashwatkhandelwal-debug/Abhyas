"""Audio caching for TTS synthesized speech (spec/06 §6.3, CHANGES 254f622).

Stores cached audio in Postgres via `tts_audio` table (cache_key, ogg, mp3, created_at).
Local directory cache is preserved as a development/test fallback when settings.ENVIRONMENT != 'production'.
Deterministic key: sha256(voice_id + provider_speaker + model + pace + pitch + gender + NFC text).
"""

from __future__ import annotations

import hashlib
import logging
import unicodedata
from pathlib import Path
from typing import Any

from sqlalchemy import select

from backend.app.config import settings
from backend.app.db.models import TTSAudio
from backend.app.db.session import async_session_factory
from backend.app.speech.audio import to_mp3, to_ogg_opus
from backend.app.speech.voices import VoiceSpec

logger = logging.getLogger("abhyas.speech.cache")


def compute_cache_key(
    text_hi: str,
    voice_id: str,
    voice: VoiceSpec,
) -> str:
    """Computes deterministic cache key for TTS synthesis (spec/06 §6.3).

    key = sha256(voice_id + provider_speaker + model + pace + pitch + gender + NFC text)
    """
    nfc_text = unicodedata.normalize("NFC", text_hi)
    raw = (
        f"{voice_id}:"
        f"{voice.provider_speaker}:"
        f"{voice.model}:"
        f"{voice.pace:.2f}:"
        f"{voice.pitch_factor:.2f}:"
        f"{voice.gender}:"
        f"{nfc_text}"
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class TTSCache:
    """Postgres-backed cache with optional local filesystem fallback (CHANGES 254f622 Item 3)."""

    def __init__(
        self,
        cache_dir: Path | str | None = None,
        use_db: bool | None = None,
    ) -> None:
        if cache_dir is None:
            self.cache_dir = Path(__file__).parents[3] / "tts_cache"
        else:
            self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # In production, DB is the primary storage; disk cache is used in dev/testing
        if use_db is not None:
            self.use_db = use_db
        else:
            self.use_db = bool(settings.DATABASE_URL)
        self.use_disk = settings.ENVIRONMENT != "production"

    def _file_path(self, key: str, fmt: str) -> Path:
        return self.cache_dir / f"{key}.{fmt}"

    async def get(self, key: str, fmt: str = "ogg") -> bytes | None:
        """Retrieves cached audio bytes from Postgres tts_audio table or dev disk cache."""
        # 1. Try querying Postgres tts_audio table
        if self.use_db:
            try:
                async with async_session_factory() as session:
                    stmt = select(TTSAudio).where(TTSAudio.cache_key == key)
                    result = await session.execute(stmt)
                    audio_row = result.scalar_one_or_none()
                    await session.rollback()
                    if audio_row:
                        if fmt == "ogg" and audio_row.ogg:
                            return bytes(audio_row.ogg)
                        if fmt == "mp3" and audio_row.mp3:
                            return bytes(audio_row.mp3)
            except Exception as exc:
                logger.warning("Database TTS cache get query error: %s", exc)

        # 2. Try disk cache if in dev or fallback
        if self.use_disk:
            file = self._file_path(key, fmt)
            if file.is_file():
                try:
                    return file.read_bytes()
                except Exception as exc:
                    logger.warning("Failed reading cached audio %s: %s", file, exc)

        return None

    def get_sync(self, key: str, fmt: str = "ogg") -> bytes | None:
        """Synchronous read from local disk cache for dev/testing."""
        if self.use_disk:
            file = self._file_path(key, fmt)
            if file.is_file():
                try:
                    return file.read_bytes()
                except Exception:
                    pass
        return None

    async def put_wav(self, key: str, wav_bytes: bytes) -> dict[str, Any]:
        """Caches WAV, generates & caches OGG and MP3 formats into Postgres and disk."""
        paths: dict[str, Any] = {}

        # 1. Local disk caching for dev/testing
        if self.use_disk:
            wav_path = self._file_path(key, "wav")
            wav_path.write_bytes(wav_bytes)
            paths["wav"] = wav_path

        ogg_bytes: bytes | None = None
        try:
            ogg_bytes = await to_ogg_opus(wav_bytes)
            if self.use_disk:
                ogg_path = self._file_path(key, "ogg")
                ogg_path.write_bytes(ogg_bytes)
                paths["ogg"] = ogg_path
        except Exception as exc:
            logger.warning("Failed converting OGG for %s: %s", key, exc)

        mp3_bytes: bytes | None = None
        try:
            mp3_bytes = await to_mp3(wav_bytes)
            if self.use_disk:
                mp3_path = self._file_path(key, "mp3")
                mp3_path.write_bytes(mp3_bytes)
                paths["mp3"] = mp3_path
        except Exception as exc:
            logger.warning("Failed converting MP3 for %s: %s", key, exc)

        # 2. Persist to Postgres tts_audio table
        if self.use_db and (ogg_bytes or mp3_bytes):
            try:
                async with async_session_factory() as session:
                    existing = await session.get(TTSAudio, key)
                    if existing:
                        if ogg_bytes:
                            existing.ogg = ogg_bytes
                        if mp3_bytes:
                            existing.mp3 = mp3_bytes
                    else:
                        record = TTSAudio(
                            cache_key=key,
                            ogg=ogg_bytes,
                            mp3=mp3_bytes,
                        )
                        session.add(record)
                    await session.commit()
            except Exception as exc:
                logger.error("Database TTS cache put error: %s", exc)

        return paths

    async def has(self, key: str, fmt: str = "ogg") -> bool:
        """Checks if format exists in cache for key."""
        audio = await self.get(key, fmt)
        return audio is not None

    def clear(self) -> None:
        """Clears local cached audio files."""
        if self.cache_dir.is_dir():
            for f in self.cache_dir.glob("*.*"):
                try:
                    f.unlink()
                except Exception:
                    pass


# Default singleton cache
tts_cache = TTSCache()

__all__ = [
    "compute_cache_key",
    "TTSCache",
    "tts_cache",
]
