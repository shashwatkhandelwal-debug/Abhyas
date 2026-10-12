"""Audio processing utilities via ffmpeg subprocess (spec/06 §6.1).

All conversions use ffmpeg subprocess with stdin/stdout pipes.
Never persist teacher audio to disk.
"""

from __future__ import annotations

import io
import logging
import os
import re
import shutil
import subprocess
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


def validate_audio_duration(duration: float, max_s: float = MAX_INBOUND_AUDIO_S) -> None:
    """Validates that audio duration does not exceed limit (spec/06 §6.1)."""
    if duration > max_s:
        raise AudioTooLongError(
            f"Audio duration {duration:.1f}s exceeds maximum allowed duration {max_s:.1f}s"
        )


def duration_s(audio_bytes: bytes) -> float:
    """Returns duration of audio bytes in seconds (spec/06 §6.1)."""
    if not audio_bytes:
        return 0.0

    # 1. Fast path for WAV headers using Python wave standard library
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

    # 2. Try ffprobe container duration
    ffprobe = get_ffprobe_path()
    try:
        proc = subprocess.run(
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
            input=audio_bytes,
            capture_output=True,
            check=False,
            timeout=10,
        )
        if proc.returncode == 0:
            out = proc.stdout.decode("utf-8", errors="replace").strip()
            if out and out != "N/A":
                return float(out)
    except Exception:
        pass

    # 3. Stream decode via ffmpeg null output (works for unseekable pipes)
    ffmpeg = get_ffmpeg_path()
    try:
        proc = subprocess.run(
            [ffmpeg, "-v", "info", "-i", "pipe:0", "-f", "null", "-"],
            input=audio_bytes,
            capture_output=True,
            check=False,
            timeout=10,
        )
        stderr = proc.stderr.decode("utf-8", errors="replace")
        times = re.findall(r"time=(\d+):(\d+):(\d+(?:\.\d+)?)", stderr)
        if times:
            h, m, s = times[-1]
            return int(h) * 3600 + int(m) * 60 + float(s)
    except Exception as exc:
        raise AudioProcessingError(f"Failed to calculate audio duration: {exc}") from exc

    raise AudioProcessingError("Could not determine audio duration from stream")


def to_wav16k(audio_bytes: bytes, mime: str | None = None) -> bytes:
    """Converts inbound audio to 16 kHz mono WAV for STT (spec/06 §6.1).

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

    try:
        proc = subprocess.run(
            cmd,
            input=audio_bytes,
            capture_output=True,
            check=False,
            timeout=15,
        )
    except Exception as exc:
        raise AudioProcessingError(f"ffmpeg conversion to wav16k failed: {exc}") from exc

    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", errors="replace").strip()
        raise AudioProcessingError(f"ffmpeg to_wav16k failed (code {proc.returncode}): {err}")

    return proc.stdout


def to_ogg_opus(wav_bytes: bytes) -> bytes:
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

    try:
        proc = subprocess.run(
            cmd,
            input=wav_bytes,
            capture_output=True,
            check=False,
            timeout=15,
        )
    except Exception as exc:
        raise AudioProcessingError(f"ffmpeg conversion to ogg_opus failed: {exc}") from exc

    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", errors="replace").strip()
        raise AudioProcessingError(f"ffmpeg to_ogg_opus failed (code {proc.returncode}): {err}")

    return proc.stdout


def to_web(wav_bytes: bytes) -> bytes:
    """Converts WAV audio to web format (OGG/Opus) (spec/06 §6.1)."""
    return to_ogg_opus(wav_bytes)


def to_mp3(wav_bytes: bytes) -> bytes:
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

    try:
        proc = subprocess.run(
            cmd,
            input=wav_bytes,
            capture_output=True,
            check=False,
            timeout=15,
        )
    except Exception as exc:
        raise AudioProcessingError(f"ffmpeg conversion to mp3 failed: {exc}") from exc

    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", errors="replace").strip()
        raise AudioProcessingError(f"ffmpeg to_mp3 failed (code {proc.returncode}): {err}")

    return proc.stdout


def pitch_shift(wav_bytes: bytes, factor: float) -> bytes:
    """Applies pitch shift to WAV audio for child voice variation (spec/06 §6.1).

    Uses ffmpeg filter: asetrate={sample_rate}*{factor},aresample={sample_rate},atempo={1/factor}.
    """
    if not wav_bytes:
        raise AudioProcessingError("Cannot pitch shift empty audio")

    if abs(factor - 1.0) < 0.001:
        return wav_bytes

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

    try:
        proc = subprocess.run(
            cmd,
            input=wav_bytes,
            capture_output=True,
            check=False,
            timeout=15,
        )
    except Exception as exc:
        raise AudioProcessingError(f"ffmpeg pitch_shift failed: {exc}") from exc

    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", errors="replace").strip()
        raise AudioProcessingError(f"ffmpeg pitch_shift failed (code {proc.returncode}): {err}")

    return proc.stdout


def _detect_silence_intervals(wav_bytes: bytes) -> list[tuple[float, float]]:
    """Detects silence intervals using ffmpeg silencedetect filter (spec/06 §6.1)."""
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
        proc = subprocess.run(
            cmd,
            input=wav_bytes,
            capture_output=True,
            check=False,
            timeout=20,
        )
    except Exception:
        return []

    stderr = proc.stderr.decode("utf-8", errors="replace")
    starts = [float(m) for m in re.findall(r"silence_start:\s*([0-9.]+)", stderr)]
    ends = [float(m) for m in re.findall(r"silence_end:\s*([0-9.]+)", stderr)]

    intervals: list[tuple[float, float]] = []
    for i in range(min(len(starts), len(ends))):
        if ends[i] > starts[i]:
            intervals.append((starts[i], ends[i]))
    return intervals


def split_for_stt(wav_bytes: bytes, max_s: float = 25.0) -> list[bytes]:
    """Splits WAV audio into chunks <= max_s at silence boundaries (spec/06 §6.1).

    Uses silencedetect=noise=-35dB:d=0.4 to find nearest silence <= max_s.
    If no silence is found, makes a hard cut at max_s.
    Returns list of WAV audio chunks.
    """
    if not wav_bytes:
        return []

    dur = duration_s(wav_bytes)
    if dur <= max_s:
        return [wav_bytes]

    silence_intervals = _detect_silence_intervals(wav_bytes)
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
            proc = subprocess.run(
                cmd,
                input=wav_bytes,
                capture_output=True,
                check=False,
                timeout=15,
            )
            if proc.returncode == 0 and len(proc.stdout) > 44:
                chunks.append(proc.stdout)
            else:
                logger.warning("Failed cutting chunk %d (%s to %s)", i, t_start, t_end)
        except Exception as exc:
            logger.warning("Error cutting chunk %d: %s", i, exc)

    return chunks if chunks else [wav_bytes]
