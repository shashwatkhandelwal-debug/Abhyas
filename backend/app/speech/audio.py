"""Audio processing utilities via async ffmpeg subprocess (spec/06 §6.1).

All conversions use non-blocking asyncio.create_subprocess_exec with stdin/stdout pipes,
timeout enforcement, and process termination on timeout.
Never persist teacher audio to disk.
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import re
import shutil
import wave
from pathlib import Path

logger = logging.getLogger("abhyas.speech.audio")

# Duration limits in seconds (spec/06 §6.1)
MAX_INBOUND_AUDIO_S: float = 90.0
EXPLAIN_BACK_MAX_SECONDS: float = 60.0
REHEARSE_TURN_MAX_S: float = 30.0


class AudioProcessingError(Exception):
    """Raised when an audio conversion or probe operation fails."""

    pass


class AudioTooLongError(AudioProcessingError):
    """Raised when inbound audio duration exceeds maximum limit (90 s)."""

    pass


def get_ffmpeg_path() -> str:
    """Resolves path to ffmpeg executable across platforms."""
    path = shutil.which("ffmpeg")
    if path:
        return path

    # Check winget / common install locations on Windows
    for base in [
        os.environ.get("LOCALAPPDATA", ""),
        os.environ.get("USERPROFILE", ""),
    ]:
        if base:
            winget_dir = Path(base) / "AppData" / "Local" / "Microsoft" / "WinGet" / "Packages"
            if not winget_dir.is_dir():
                winget_dir = Path(base) / "Microsoft" / "WinGet" / "Packages"
            if winget_dir.is_dir():
                for candidate in winget_dir.glob("**/bin/ffmpeg.exe"):
                    if candidate.is_file():
                        return str(candidate)

    return "ffmpeg"


def get_ffprobe_path() -> str:
    """Resolves path to ffprobe executable across platforms."""
    path = shutil.which("ffprobe")
    if path:
        return path

    # Check winget / common install locations on Windows
    for base in [
        os.environ.get("LOCALAPPDATA", ""),
        os.environ.get("USERPROFILE", ""),
    ]:
        if base:
            winget_dir = Path(base) / "AppData" / "Local" / "Microsoft" / "WinGet" / "Packages"
            if not winget_dir.is_dir():
                winget_dir = Path(base) / "Microsoft" / "WinGet" / "Packages"
            if winget_dir.is_dir():
                for candidate in winget_dir.glob("**/bin/ffprobe.exe"):
                    if candidate.is_file():
                        return str(candidate)

    return "ffprobe"


async def _run_subprocess_async(
    cmd: list[str],
    input_bytes: bytes | None = None,
    timeout_s: float = 15.0,
) -> tuple[int, bytes, bytes]:
    """Runs a subprocess non-blockingly via asyncio.create_subprocess_exec.

    Enforces timeout and kills the process on timeout, ensuring the event loop is never blocked.
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE if input_bytes is not None else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except Exception as exc:
        raise AudioProcessingError(f"Failed to start subprocess '{cmd[0]}': {exc}") from exc

    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input=input_bytes),
            timeout=timeout_s,
        )
        returncode = proc.returncode if proc.returncode is not None else -1
        return returncode, stdout, stderr
    except TimeoutError as exc:
        try:
            proc.kill()
            await proc.wait()
        except Exception:
            pass
        raise AudioProcessingError(f"Subprocess '{cmd[0]}' timed out after {timeout_s}s") from exc


def validate_audio_duration(duration: float, max_s: float = MAX_INBOUND_AUDIO_S) -> None:
    """Validates that audio duration does not exceed limit (spec/06 §6.1)."""
    if duration > max_s:
        raise AudioTooLongError(
            f"Audio duration {duration:.1f}s exceeds maximum allowed duration {max_s:.1f}s"
        )


def _get_wav_header_duration(audio_bytes: bytes) -> float | None:
    """Fast-path extractor for duration from WAV headers."""
    if audio_bytes.startswith(b"RIFF") and b"WAVE" in audio_bytes[:16]:
        try:
            with wave.open(io.BytesIO(audio_bytes), "rb") as wf:
                frames = wf.getnframes()
                rate = wf.getframerate()
                nchannels = wf.getnchannels()
                sampwidth = wf.getsampwidth()
                frame_size = nchannels * sampwidth
                actual_max_frames = (len(audio_bytes) - 44) // frame_size if frame_size > 0 else 0
                if actual_max_frames > 0 and (frames <= 0 or frames > actual_max_frames):
                    frames = actual_max_frames
                if rate > 0 and frames > 0:
                    return float(frames) / float(rate)
        except Exception:
            pass
    return None


async def duration_s(audio_bytes: bytes) -> float:
    """Returns duration of audio bytes in seconds asynchronously (spec/06 §6.1)."""
    if not audio_bytes:
        return 0.0

    # 1. Fast path for WAV headers using Python wave standard library
    wav_dur = _get_wav_header_duration(audio_bytes)
    if wav_dur is not None:
        return wav_dur

    # 2. Try ffprobe container duration via async subprocess
    ffprobe = get_ffprobe_path()
    try:
        retcode, stdout, _ = await _run_subprocess_async(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                "pipe:0",
            ],
            input_bytes=audio_bytes,
            timeout_s=10.0,
        )
        if retcode == 0:
            out = stdout.decode("utf-8", errors="replace").strip()
            if out and out != "N/A":
                return float(out)
    except Exception:
        pass

    # 3. Stream decode via ffmpeg null output (for unseekable pipes)
    ffmpeg = get_ffmpeg_path()
    try:
        retcode, _, stderr_bytes = await _run_subprocess_async(
            [ffmpeg, "-v", "info", "-i", "pipe:0", "-f", "null", "-"],
            input_bytes=audio_bytes,
            timeout_s=10.0,
        )
        stderr = stderr_bytes.decode("utf-8", errors="replace")
        times = re.findall(r"time=(\d+):(\d+):(\d+(?:\.\d+)?)", stderr)
        if times:
            h, m, s = times[-1]
            return int(h) * 3600 + int(m) * 60 + float(s)
    except Exception as exc:
        raise AudioProcessingError(f"Failed to calculate audio duration: {exc}") from exc

    raise AudioProcessingError("Could not determine audio duration from stream")


def duration_s_sync(audio_bytes: bytes) -> float:
    """Synchronous helper for duration_s."""
    wav_dur = _get_wav_header_duration(audio_bytes)
    if wav_dur is not None:
        return wav_dur
    return asyncio.run(duration_s(audio_bytes))


async def to_wav16k(audio_bytes: bytes, mime: str | None = None) -> bytes:
    """Converts inbound audio to 16 kHz mono WAV for STT asynchronously (spec/06 §6.1).

    Supports OGG/Opus (WhatsApp), WebM/Opus, MP4/AAC, MP3, etc.
    Never writes audio to disk.
    """
    if not audio_bytes:
        raise AudioProcessingError("Cannot convert empty audio bytes")

    ffmpeg = get_ffmpeg_path()
    cmd = [
        ffmpeg,
        "-v",
        "error",
        "-i",
        "pipe:0",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-f",
        "wav",
        "pipe:1",
    ]

    retcode, stdout, stderr = await _run_subprocess_async(
        cmd, input_bytes=audio_bytes, timeout_s=15.0
    )
    if retcode != 0:
        err = stderr.decode("utf-8", errors="replace").strip()
        raise AudioProcessingError(f"ffmpeg to_wav16k failed (code {retcode}): {err}")

    return stdout


def to_wav16k_sync(audio_bytes: bytes, mime: str | None = None) -> bytes:
    """Synchronous helper for to_wav16k."""
    return asyncio.run(to_wav16k(audio_bytes, mime))


async def to_wav(audio_bytes: bytes, fmt: str = "ogg", sample_rate: int = 22050) -> bytes:
    """Converts OGG or MP3 audio bytes to 22.05 kHz 16-bit mono WAV (spec/06 §6.1)."""
    if not audio_bytes:
        return b""
    if fmt == "wav" and audio_bytes.startswith(b"RIFF"):
        return audio_bytes
    if audio_bytes.startswith(b"RIFF"):
        return audio_bytes

    ffmpeg = get_ffmpeg_path()
    cmd = [
        ffmpeg,
        "-v",
        "error",
        "-i",
        "pipe:0",
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        "-f",
        "wav",
        "pipe:1",
    ]

    retcode, stdout, stderr = await _run_subprocess_async(
        cmd, input_bytes=audio_bytes, timeout_s=15.0
    )
    if retcode != 0:
        err = stderr.decode("utf-8", errors="replace").strip()
        raise AudioProcessingError(f"ffmpeg to_wav failed (code {retcode}): {err}")

    return stdout


async def to_ogg_opus(wav_bytes: bytes) -> bytes:
    """Converts WAV audio to WhatsApp-compatible OGG/Opus mono 48 kHz (spec/06 §6.1)."""
    if not wav_bytes:
        raise AudioProcessingError("Cannot convert empty WAV bytes to OGG/Opus")

    ffmpeg = get_ffmpeg_path()
    cmd = [
        ffmpeg,
        "-v",
        "error",
        "-i",
        "pipe:0",
        "-c:a",
        "libopus",
        "-b:a",
        "24k",
        "-ac",
        "1",
        "-ar",
        "48000",
        "-application",
        "voip",
        "-f",
        "ogg",
        "pipe:1",
    ]

    retcode, stdout, stderr = await _run_subprocess_async(
        cmd, input_bytes=wav_bytes, timeout_s=15.0
    )
    if retcode != 0:
        err = stderr.decode("utf-8", errors="replace").strip()
        raise AudioProcessingError(f"ffmpeg to_ogg_opus failed (code {retcode}): {err}")

    return stdout


async def to_web(wav_bytes: bytes) -> bytes:
    """Converts WAV audio to web format (OGG/Opus) (spec/06 §6.1)."""
    return await to_ogg_opus(wav_bytes)


async def to_mp3(wav_bytes: bytes) -> bytes:
    """Converts WAV audio to MP3 32k for Safari/iOS web playback (spec/06 §6.1)."""
    if not wav_bytes:
        raise AudioProcessingError("Cannot convert empty WAV bytes to MP3")

    ffmpeg = get_ffmpeg_path()
    cmd = [
        ffmpeg,
        "-v",
        "error",
        "-i",
        "pipe:0",
        "-b:a",
        "32k",
        "-f",
        "mp3",
        "pipe:1",
    ]

    retcode, stdout, stderr = await _run_subprocess_async(
        cmd, input_bytes=wav_bytes, timeout_s=15.0
    )
    if retcode != 0:
        err = stderr.decode("utf-8", errors="replace").strip()
        raise AudioProcessingError(f"ffmpeg to_mp3 failed (code {retcode}): {err}")

    return stdout


async def pitch_shift(wav_bytes: bytes, factor: float) -> bytes:
    """Applies pitch shift to WAV audio for child voice variation asynchronously (spec/06 §6.1).

    Uses ffmpeg filter: asetrate={sample_rate}*{factor},aresample={sample_rate},atempo={1/factor}.
    """
    if not wav_bytes:
        raise AudioProcessingError("Cannot pitch shift empty audio")

    if abs(factor - 1.0) < 0.001:
        return wav_bytes

    if not wav_bytes.startswith(b"RIFF"):
        wav_bytes = await to_wav(wav_bytes)

    # Detect sample rate from WAV header if available, default to 22050 per spec
    sample_rate = 22050
    if wav_bytes.startswith(b"RIFF") and b"WAVE" in wav_bytes[:16]:
        try:
            with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
                sr = wf.getframerate()
                if sr > 0:
                    sample_rate = sr
        except Exception:
            pass

    ffmpeg = get_ffmpeg_path()
    inv_factor = 1.0 / factor
    new_rate = int(round(sample_rate * factor))
    filter_expr = f"asetrate={new_rate},aresample={sample_rate},atempo={inv_factor:.4f}"

    cmd = [
        ffmpeg,
        "-v",
        "error",
        "-i",
        "pipe:0",
        "-af",
        filter_expr,
        "-f",
        "wav",
        "pipe:1",
    ]

    retcode, stdout, stderr = await _run_subprocess_async(
        cmd, input_bytes=wav_bytes, timeout_s=15.0
    )
    if retcode != 0:
        err = stderr.decode("utf-8", errors="replace").strip()
        raise AudioProcessingError(f"ffmpeg pitch_shift failed (code {retcode}): {err}")

    return stdout


async def _detect_silence_intervals(wav_bytes: bytes) -> list[tuple[float, float]]:
    """Detects silence intervals asynchronously using ffmpeg silencedetect filter (spec/06 §6.1)."""
    ffmpeg = get_ffmpeg_path()
    cmd = [
        ffmpeg,
        "-v",
        "info",
        "-i",
        "pipe:0",
        "-af",
        "silencedetect=noise=-35dB:d=0.4",
        "-f",
        "null",
        "-",
    ]

    try:
        _, _, stderr_bytes = await _run_subprocess_async(cmd, input_bytes=wav_bytes, timeout_s=20.0)
    except Exception:
        return []

    stderr = stderr_bytes.decode("utf-8", errors="replace")
    starts = [float(m) for m in re.findall(r"silence_start:\s*([0-9.]+)", stderr)]
    ends = [float(m) for m in re.findall(r"silence_end:\s*([0-9.]+)", stderr)]

    intervals: list[tuple[float, float]] = []
    for i in range(min(len(starts), len(ends))):
        if ends[i] > starts[i]:
            intervals.append((starts[i], ends[i]))
    return intervals


async def split_for_stt(wav_bytes: bytes, max_s: float = 25.0) -> list[bytes]:
    """Splits WAV audio into chunks <= max_s at silence boundaries asynchronously (spec/06 §6.1).

    Uses silencedetect=noise=-35dB:d=0.4 to find nearest silence <= max_s.
    If no silence is found, makes a hard cut at max_s.
    Returns list of WAV audio chunks.
    """
    if not wav_bytes:
        return []

    dur = await duration_s(wav_bytes)
    if dur <= max_s:
        return [wav_bytes]

    silence_intervals = await _detect_silence_intervals(wav_bytes)
    silence_midpoints = [(s + e) / 2.0 for (s, e) in silence_intervals]

    # Calculate split points
    cut_times: list[float] = [0.0]
    current = 0.0

    while current + max_s < dur:
        # Search for silence midpoints in (current + 1.0, current + max_s]
        candidates = [p for p in silence_midpoints if current + 1.0 <= p <= current + max_s]
        if candidates:
            # Cut at the silence nearest <= max_s (i.e. highest candidate in range)
            next_cut = candidates[-1]
        else:
            # Hard cut if none found
            next_cut = current + max_s
        cut_times.append(next_cut)
        current = next_cut

    cut_times.append(dur)

    ffmpeg = get_ffmpeg_path()
    chunks: list[bytes] = []

    for i in range(len(cut_times) - 1):
        t_start = cut_times[i]
        t_end = cut_times[i + 1]
        if t_end - t_start < 0.05:
            continue

        cmd = [
            ffmpeg,
            "-v",
            "error",
            "-i",
            "pipe:0",
            "-af",
            f"atrim=start={t_start:.3f}:end={t_end:.3f},asetpts=PTS-STARTPTS",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-f",
            "wav",
            "pipe:1",
        ]

        try:
            retcode, stdout, _ = await _run_subprocess_async(
                cmd, input_bytes=wav_bytes, timeout_s=15.0
            )
            if retcode == 0 and len(stdout) > 44:
                chunks.append(stdout)
            else:
                logger.warning("Failed cutting chunk %d (%s to %s)", i, t_start, t_end)
        except Exception as exc:
            logger.warning("Error cutting chunk %d: %s", i, exc)

    return chunks if chunks else [wav_bytes]


async def trim_silence(wav_bytes: bytes) -> bytes:
    """Trims leading and trailing silence from WAV audio (spec/06 §6.1)."""
    if not wav_bytes or len(wav_bytes) <= 44:
        return wav_bytes

    ffmpeg = get_ffmpeg_path()
    cmd = [
        ffmpeg,
        "-v",
        "error",
        "-i",
        "pipe:0",
        "-af",
        "silenceremove=start_periods=1:start_duration=0.1:start_threshold=-40dB:detection=peak,areverse,silenceremove=start_periods=1:start_duration=0.1:start_threshold=-40dB:detection=peak,areverse",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-f",
        "wav",
        "pipe:1",
    ]

    try:
        retcode, stdout, _ = await _run_subprocess_async(cmd, input_bytes=wav_bytes, timeout_s=15.0)
        if retcode == 0 and len(stdout) > 44:
            return stdout
    except Exception:
        pass

    return wav_bytes


__all__ = [
    "AudioProcessingError",
    "AudioTooLongError",
    "MAX_INBOUND_AUDIO_S",
    "EXPLAIN_BACK_MAX_SECONDS",
    "REHEARSE_TURN_MAX_S",
    "get_ffmpeg_path",
    "get_ffprobe_path",
    "validate_audio_duration",
    "duration_s",
    "duration_s_sync",
    "to_wav",
    "to_wav16k",
    "to_wav16k_sync",
    "to_ogg_opus",
    "to_web",
    "to_mp3",
    "pitch_shift",
    "split_for_stt",
    "trim_silence",
]
