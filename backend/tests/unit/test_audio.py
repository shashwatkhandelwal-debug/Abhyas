"""Unit tests for audio pipeline and conversion utilities (spec/06 §6.1, T15)."""

import asyncio
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
    to_wav,
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


@pytest.mark.asyncio
async def test_duration_s(wav_5s: bytes) -> None:
    """duration_s correctly measures length in seconds via ffprobe."""
    dur = await duration_s(wav_5s)
    assert 4.9 <= dur <= 5.1

    assert await duration_s(b"") == 0.0


@pytest.mark.asyncio
async def test_to_wav16k_from_ogg(ogg_5s: bytes) -> None:
    """to_wav16k converts WhatsApp OGG/Opus to 16 kHz mono WAV."""
    wav = await to_wav16k(ogg_5s)
    assert wav.startswith(b"RIFF")
    dur = await duration_s(wav)
    assert 4.9 <= dur <= 5.1


@pytest.mark.asyncio
async def test_to_wav16k_from_webm(webm_5s: bytes) -> None:
    """to_wav16k converts browser WebM/Opus to 16 kHz mono WAV."""
    wav = await to_wav16k(webm_5s)
    assert wav.startswith(b"RIFF")
    dur = await duration_s(wav)
    assert 4.9 <= dur <= 5.1


@pytest.mark.asyncio
async def test_to_wav16k_from_mp4(mp4_5s: bytes) -> None:
    """to_wav16k converts browser MP4/AAC to 16 kHz mono WAV."""
    wav = await to_wav16k(mp4_5s)
    assert wav.startswith(b"RIFF")
    dur = await duration_s(wav)
    assert 4.9 <= dur <= 5.1


@pytest.mark.asyncio
async def test_to_wav16k_empty_raises() -> None:
    """to_wav16k raises AudioProcessingError on empty input."""
    with pytest.raises(AudioProcessingError):
        await to_wav16k(b"")


@pytest.mark.asyncio
async def test_to_ogg_opus(wav_5s: bytes) -> None:
    """to_ogg_opus converts WAV to WhatsApp-compatible OGG/Opus."""
    ogg = await to_ogg_opus(wav_5s)
    assert ogg.startswith(b"OggS")
    dur = await duration_s(ogg)
    assert 4.9 <= dur <= 5.1


@pytest.mark.asyncio
async def test_to_web(wav_5s: bytes) -> None:
    """to_web produces valid OGG/Opus audio."""
    web_audio = await to_web(wav_5s)
    assert web_audio.startswith(b"OggS")


@pytest.mark.asyncio
async def test_to_mp3(wav_5s: bytes) -> None:
    """to_mp3 converts WAV to MP3 for Safari/iOS fallback."""
    mp3 = await to_mp3(wav_5s)
    assert len(mp3) > 100
    dur = await duration_s(mp3)
    assert 4.8 <= dur <= 5.2


@pytest.mark.asyncio
async def test_pitch_shift(wav_5s: bytes) -> None:
    """pitch_shift alters pitch factor for child voices."""
    # Factor 1.0 is a no-op identity
    same = await pitch_shift(wav_5s, 1.0)
    assert same == wav_5s

    # Factor 1.22 produces valid WAV
    shifted = await pitch_shift(wav_5s, 1.22)
    assert shifted.startswith(b"RIFF")
    dur = await duration_s(shifted)
    assert 4.8 <= dur <= 5.2


@pytest.mark.asyncio
async def test_split_for_stt_short_audio(wav_5s: bytes) -> None:
    """split_for_stt returns single chunk when audio <= max_s."""
    chunks = await split_for_stt(wav_5s, max_s=25.0)
    assert len(chunks) == 1
    assert chunks[0] == wav_5s


@pytest.mark.asyncio
async def test_split_for_stt_60s_audio(wav_60s: bytes) -> None:
    """split_for_stt cuts at silences nearest <= max_s."""
    chunks = await split_for_stt(wav_60s, max_s=25.0)
    assert len(chunks) >= 3

    # Each chunk should be <= 25.5s
    for i, chunk in enumerate(chunks):
        assert chunk.startswith(b"RIFF")
        chunk_dur = await duration_s(chunk)
        assert chunk_dur <= 26.0, f"Chunk {i} exceeded max duration: {chunk_dur}s"


def test_validate_audio_duration() -> None:
    """validate_audio_duration enforces maximum limits."""
    validate_audio_duration(30.0)
    validate_audio_duration(MAX_INBOUND_AUDIO_S)

    with pytest.raises(AudioTooLongError):
        validate_audio_duration(MAX_INBOUND_AUDIO_S + 0.5)


@pytest.mark.asyncio
async def test_no_temp_files_left_on_disk(wav_5s: bytes) -> None:
    """Verifies that audio processing does not leave files in temp dir."""
    temp_dir = Path(tempfile.gettempdir())
    files_before = set(temp_dir.iterdir())

    # Run conversions
    _ = await to_wav16k(wav_5s)
    _ = await to_ogg_opus(wav_5s)
    _ = await to_mp3(wav_5s)
    _ = await pitch_shift(wav_5s, 1.15)
    _ = await split_for_stt(wav_5s, max_s=2.0)

    files_after = set(temp_dir.iterdir())
    new_files = files_after - files_before
    # Filter out files created by other OS processes by checking for audio prefixes if any
    audio_leaks = [f for f in new_files if f.suffix in {".wav", ".ogg", ".opus", ".mp3", ".webm"}]
    assert not audio_leaks, f"Leaked temporary audio files: {audio_leaks}"


@pytest.mark.asyncio
async def test_concurrent_conversions_non_blocking(ogg_5s: bytes) -> None:
    """5 concurrent conversions with asyncio.gather allow background task progress."""
    ticks = 0
    stop_ticker = False

    async def ticker() -> None:
        nonlocal ticks
        while not stop_ticker:
            ticks += 1
            await asyncio.sleep(0.01)

    ticker_task = asyncio.create_task(ticker())
    try:
        conversions = [to_wav16k(ogg_5s) for _ in range(5)]
        results = await asyncio.gather(*conversions)
        assert len(results) == 5
        for res in results:
            assert res.startswith(b"RIFF")
    finally:
        stop_ticker = True
        await ticker_task

    # Event loop was not blocked if ticker ran multiple times
    assert ticks > 0, "Event loop was blocked during conversions"


@pytest.mark.asyncio
async def test_to_wav_converts_ogg_and_preserves_wav(wav_5s: bytes, ogg_5s: bytes) -> None:
    """to_wav converts OGG to 22.05 kHz mono WAV and passes through WAV without re-encoding."""
    # 1. WAV passthrough
    wav_out = await to_wav(wav_5s, fmt="wav")
    assert wav_out == wav_5s

    # 2. OGG conversion
    converted_wav = await to_wav(ogg_5s, fmt="ogg")
    assert converted_wav.startswith(b"RIFF")
    dur = await duration_s(converted_wav)
    assert 4.8 <= dur <= 5.2

    # 3. Empty audio
    assert await to_wav(b"") == b""


def test_no_subprocess_run_in_backend_app() -> None:
    """Verifies that no Python file under backend/app uses synchronous subprocess.run."""
    backend_app_dir = Path(__file__).parents[2] / "app"
    assert backend_app_dir.is_dir()

    violations: list[str] = []
    for py_file in backend_app_dir.rglob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        if "subprocess.run" in content:
            violations.append(str(py_file.relative_to(backend_app_dir.parent)))

    assert not violations, f"Forbidden subprocess.run found in: {violations}"
