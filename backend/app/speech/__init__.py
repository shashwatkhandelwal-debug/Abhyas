"""Speech module exports (spec/06)."""

from backend.app.speech.audio import (
    AudioProcessingError,
    AudioTooLongError,
    duration_s,
    pitch_shift,
    split_for_stt,
    to_mp3,
    to_ogg_opus,
    to_wav16k,
    to_web,
    validate_audio_duration,
)
from backend.app.speech.cache import TTSCache, compute_cache_key, tts_cache
from backend.app.speech.stt import (
    MockSTT,
    SarvamSTT,
    STTError,
    STTProvider,
    STTUnavailable,
    Transcript,
    calculate_confidence,
    get_stt_provider,
    normalize_transcript_text,
)
from backend.app.speech.tts import (
    MockTTS,
    SarvamTTS,
    TTSError,
    TTSProvider,
    TTSUnavailable,
    convert_digits_for_tts,
    get_tts_provider,
    split_sentences_for_tts,
)
from backend.app.speech.voices import VOICE_CATALOG, VoiceSpec, get_voice, load_voices

__all__ = [
    # Audio pipeline
    "to_wav16k",
    "duration_s",
    "split_for_stt",
    "to_ogg_opus",
    "to_web",
    "to_mp3",
    "pitch_shift",
    "validate_audio_duration",
    "AudioProcessingError",
    "AudioTooLongError",
    # STT
    "STTProvider",
    "Transcript",
    "MockSTT",
    "SarvamSTT",
    "get_stt_provider",
    "STTError",
    "STTUnavailable",
    "normalize_transcript_text",
    "calculate_confidence",
    # TTS
    "TTSProvider",
    "MockTTS",
    "SarvamTTS",
    "get_tts_provider",
    "TTSError",
    "TTSUnavailable",
    "convert_digits_for_tts",
    "split_sentences_for_tts",
    # Voices
    "VoiceSpec",
    "VOICE_CATALOG",
    "get_voice",
    "load_voices",
    # Cache
    "TTSCache",
    "tts_cache",
    "compute_cache_key",
]
