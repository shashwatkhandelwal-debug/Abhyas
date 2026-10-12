"""Unit tests for audio pipeline and conversion utilities (spec/06 §6.1, T15)."""

import tempfile
from pathlib import Path

import pytest

from backend.app.speech.audio import (
    MAX_INBOUND_AUDIO_S,
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

FIXTURES_DIR = Path(__file__).parents[1] / "fixtures" / "audio"


@pytest.fixture
def wav_5s() -> bytes:
    file = FIXTURES_DIR / "sample_5s.wav"
    assert file.is_file(), f"Fixture missing: {file}"
    return file.read_bytes()


@pytest.fixture
def ogg_5s() -> bytes:
    file = FIXTURES_DIR / "sample_5s.ogg"
    assert file.is_file(), f"Fixture missing: {file}"
    return file.read_bytes()


@pytest.fixture
def webm_5s() -> bytes:
    file = FIXTURES_DIR / "sample_5s.webm"
    assert file.is_file(), f"Fixture missing: {file}"
    return file.read_bytes()


@pytest.fixture
def mp4_5s() -> bytes:
    file = FIXTURES_DIR / "sample_5s.mp4"
    assert file.is_file(), f"Fixture missing: {file}"
    return file.read_bytes()


@pytest.fixture
def wav_60s() -> bytes:
    file = FIXTURES_DIR / "sample_60s.wav"
    assert file.is_file(), f"Fixture missing: {file}"
    return file.read_bytes()


def test_duration_s(wav_5s: bytes) -> None:
    """duration_s correctly measures length in seconds via ffprobe."""
    dur = duration_s(wav_5s)
    assert 4.9 <= dur <= 5.1

    assert duration_s(b"") == 0.0


def test_to_wav16k_from_ogg(ogg_5s: bytes) -> None:
    """to_wav16k converts WhatsApp OGG/Opus to 16 kHz mono WAV."""
    wav = to_wav16k(ogg_5s)
    assert wav.startswith(b"RIFF")
    dur = duration_s(wav)
    assert 4.9 <= dur <= 5.1


def test_to_wav16k_from_webm(webm_5s: bytes) -> None:
    """to_wav16k converts browser WebM/Opus to 16 kHz mono WAV."""
    wav = to_wav16k(webm_5s)
    assert wav.startswith(b"RIFF")
    dur = duration_s(wav)
    assert 4.9 <= dur <= 5.1


def test_to_wav16k_from_mp4(mp4_5s: bytes) -> None:
    """to_wav16k converts browser MP4/AAC to 16 kHz mono WAV."""
    wav = to_wav16k(mp4_5s)
    assert wav.startswith(b"RIFF")
    dur = duration_s(wav)
    assert 4.9 <= dur <= 5.1


def test_to_wav16k_empty_raises() -> None:
    """to_wav16k raises AudioProcessingError on empty input."""
    with pytest.raises(AudioProcessingError):
        to_wav16k(b"")


def test_to_ogg_opus(wav_5s: bytes) -> None:
    """to_ogg_opus converts WAV to WhatsApp-compatible OGG/Opus."""
    ogg = to_ogg_opus(wav_5s)
    assert ogg.startswith(b"OggS")
    dur = duration_s(ogg)
    assert 4.9 <= dur <= 5.1


def test_to_web(wav_5s: bytes) -> None:
    """to_web produces valid OGG/Opus audio."""
    web_audio = to_web(wav_5s)
    assert web_audio.startswith(b"OggS")


def test_to_mp3(wav_5s: bytes) -> None:
    """to_mp3 converts WAV to MP3 for Safari/iOS fallback."""
    mp3 = to_mp3(wav_5s)
    assert len(mp3) > 100
    dur = duration_s(mp3)
    assert 4.8 <= dur <= 5.2


def test_pitch_shift(wav_5s: bytes) -> None:
    """pitch_shift alters pitch factor for child voices."""
    # Factor 1.0 is a no-op identity
    same = pitch_shift(wav_5s, 1.0)
    assert same == wav_5s

    # Factor 1.22 produces valid WAV
    shifted = pitch_shift(wav_5s, 1.22)
    assert shifted.startswith(b"RIFF")
    dur = duration_s(shifted)
    assert 4.8 <= dur <= 5.2


def test_split_for_stt_short_audio(wav_5s: bytes) -> None:
    """split_for_stt returns single chunk when audio <= max_s."""
    chunks = split_for_stt(wav_5s, max_s=25.0)
    assert len(chunks) == 1
    assert chunks[0] == wav_5s


def test_split_for_stt_60s_audio(wav_60s: bytes) -> None:
    """split_for_stt cuts at silences nearest <= max_s."""
    chunks = split_for_stt(wav_60s, max_s=25.0)
    assert len(chunks) >= 3

    # Each chunk should be <= 25.5s
    for i, chunk in enumerate(chunks):
        assert chunk.startswith(b"RIFF")
        chunk_dur = duration_s(chunk)
        assert chunk_dur <= 26.0, f"Chunk {i} exceeded max duration: {chunk_dur}s"


def test_validate_audio_duration() -> None:
    """validate_audio_duration enforces maximum limits."""
    validate_audio_duration(30.0)
    validate_audio_duration(MAX_INBOUND_AUDIO_S)

    with pytest.raises(AudioTooLongError):
        validate_audio_duration(MAX_INBOUND_AUDIO_S + 0.5)


def test_no_temp_files_left_on_disk(wav_5s: bytes) -> None:
    """Verifies that audio processing does not leave files in temp dir."""
    temp_dir = Path(tempfile.gettempdir())
    files_before = set(temp_dir.iterdir())

    # Run conversions
    _ = to_wav16k(wav_5s)
    _ = to_ogg_opus(wav_5s)
    _ = to_mp3(wav_5s)
    _ = pitch_shift(wav_5s, 1.15)
    _ = split_for_stt(wav_5s, max_s=2.0)

    files_after = set(temp_dir.iterdir())
    new_files = files_after - files_before
    # Filter out files created by other OS processes by checking for audio prefixes if any
    audio_leaks = [f for f in new_files if f.suffix in {".wav", ".ogg", ".opus", ".mp3", ".webm"}]
    assert not audio_leaks, f"Leaked temporary audio files: {audio_leaks}"
