"""Audio caching for TTS synthesized speech (spec/06 §6.3).

Key = sha256(voice_id + provider_speaker + model + pace + pitch + NFC text).
Stores final OGG, MP3, and WAV files in `tts_cache`.
"""

from __future__ import annotations

import hashlib
import logging
import unicodedata
from pathlib import Path

from backend.app.speech.audio import to_mp3, to_ogg_opus
from backend.app.speech.voices import VoiceSpec

logger = logging.getLogger("abhyas.speech.cache")


def compute_cache_key(
    text_hi: str,
    voice_id: str,
    voice: VoiceSpec,
) -> str:
    """Computes deterministic cache key for TTS synthesis (spec/06 §6.3).

    key = sha256(voice_id + provider_speaker + model + pace + pitch + NFC text)
    """
    nfc_text = unicodedata.normalize("NFC", text_hi)
    raw = (
        f"{voice_id}:"
        f"{voice.provider_speaker}:"
        f"{voice.model}:"
        f"{voice.pace:.2f}:"
        f"{voice.pitch_factor:.2f}:"
        f"{nfc_text}"
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class TTSCache:
    """File-backed cache for synthesized audio clips (spec/06 §6.3)."""

    def __init__(self, cache_dir: Path | str | None = None) -> None:
        if cache_dir is None:
            self.cache_dir = Path(__file__).parents[3] / "tts_cache"
        else:
            self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _file_path(self, key: str, fmt: str) -> Path:
        return self.cache_dir / f"{key}.{fmt}"

    def get(self, key: str, fmt: str = "ogg") -> bytes | None:
        """Retrieves cached audio bytes for key and format, or None if absent."""
        file = self._file_path(key, fmt)
        if file.is_file():
            try:
                return file.read_bytes()
            except Exception as exc:
                logger.warning("Failed reading cached audio %s: %s", file, exc)
        return None

    def put_wav(self, key: str, wav_bytes: bytes) -> dict[str, Path]:
        """Caches WAV and automatically generates & caches OGG and MP3 formats (spec/06 §6.3)."""
        paths: dict[str, Path] = {}

        wav_path = self._file_path(key, "wav")
        wav_path.write_bytes(wav_bytes)
        paths["wav"] = wav_path

        try:
            ogg_bytes = to_ogg_opus(wav_bytes)
            ogg_path = self._file_path(key, "ogg")
            ogg_path.write_bytes(ogg_bytes)
            paths["ogg"] = ogg_path
        except Exception as exc:
            logger.warning("Failed caching OGG for %s: %s", key, exc)

        try:
            mp3_bytes = to_mp3(wav_bytes)
            mp3_path = self._file_path(key, "mp3")
            mp3_path.write_bytes(mp3_bytes)
            paths["mp3"] = mp3_path
        except Exception as exc:
            logger.warning("Failed caching MP3 for %s: %s", key, exc)

        return paths

    def has(self, key: str, fmt: str = "ogg") -> bool:
        """Checks if format exists in cache for key."""
        return self._file_path(key, fmt).is_file()

    def clear(self) -> None:
        """Clears all cached audio files."""
        if self.cache_dir.is_dir():
            for f in self.cache_dir.glob("*.*"):
                try:
                    f.unlink()
                except Exception:
                    pass


# Default singleton cache
tts_cache = TTSCache()
