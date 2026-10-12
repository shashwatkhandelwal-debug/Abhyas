"""Render evaluator sample inputs to audio files and expose demo chips (spec/13 §13.1, spec/14 T39).

Usage:
    python scripts/render_samples.py [--mock] [--force]

Reads:
    eval/samples/samples.yaml
Outputs:
    eval/samples/audio/<id>.wav
    eval/samples/audio/<id>.ogg
    eval/samples/demo_chips.json
"""

import argparse
import base64
import io
import json
import math
import os
import shutil
import struct
import sys
import unicodedata
import wave
from pathlib import Path
from typing import Any

import httpx
import yaml

DEFAULT_CHIP_LABELS: dict[str, str] = {
    "s1_ask_ravi": "रवि से पूछें",
    "s2_bundles_all": "बंडल दिखाएँ",
    "s3_tell_answer_hinglish": "उत्तर बताएँ (Hinglish)",
    "s4_explain_back": "खुद समझाएँ",
    "s5_question_multigrade": "बहु-कक्षा प्रश्न",
}


def is_nfc(text: str) -> bool:
    """Check if string is in NFC normalized form."""
    return text == unicodedata.normalize("NFC", text)


def normalize_nfc(text: str) -> str:
    """Normalize string to NFC format."""
    return unicodedata.normalize("NFC", text)


def load_samples(samples_file: Path) -> list[dict[str, Any]]:
    """Loads evaluator sample inputs from YAML file."""
    if not samples_file.exists():
        raise FileNotFoundError(f"Samples file not found at {samples_file}")

    with open(samples_file, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict) or "samples" not in data:
        raise ValueError(f"Invalid format in {samples_file}: expected root 'samples' key")

    samples: list[dict[str, Any]] = data["samples"]
    return samples


def generate_synthetic_wav(text: str, duration_s: float | None = None) -> bytes:
    """Generates a valid 16-bit PCM mono 16kHz WAV audio file in memory.

    Produces a smooth synthetic placeholder tone with envelope shaping
    whose length is proportional to the text length (simulating speech duration).
    """
    sample_rate = 16000
    if duration_s is None:
        # Base speech rate ~15-20 chars/sec
        duration_s = max(1.5, min(7.5, len(text) * 0.05))

    num_samples = int(sample_rate * duration_s)
    buffer = io.BytesIO()

    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)  # Mono
        wav_file.setsampwidth(2)  # 16-bit
        wav_file.setframerate(sample_rate)

        # Synthesize a soft dual-tone (220 Hz fundamental + 440 Hz overtone) with gentle attack/decay
        samples = []
        for i in range(num_samples):
            t = float(i) / sample_rate
            envelope = min(1.0, i / (0.05 * sample_rate)) * min(
                1.0, (num_samples - i) / (0.05 * sample_rate)
            )
            # Gentle pitch variation to mimic natural cadence
            f_fund = 220.0 + 15.0 * math.sin(2.0 * math.pi * 1.5 * t)
            val = 0.6 * math.sin(2.0 * math.pi * f_fund * t) + 0.4 * math.sin(
                2.0 * math.pi * (2.0 * f_fund) * t
            )
            sample_val = int(val * envelope * 8000.0)  # Max amplitude ~8000 (well within 32767)
            samples.append(struct.pack("<h", sample_val))

        wav_file.writeframes(b"".join(samples))

    return buffer.getvalue()


def synthesize_sarvam_tts(
    text_hi: str,
    api_key: str,
    speaker: str = "pooja",
    model: str = "bulbul:v3",
) -> bytes | None:
    """Calls Sarvam AI Text-to-Speech API for adult teacher voice synthesis."""
    url = "https://api.sarvam.ai/text-to-speech"
    headers = {
        "api-subscription-key": api_key,
        "Content-Type": "application/json",
    }
    payload = {
        "text": text_hi,
        "language_code": "hi-IN",
        "model": model,
        "speaker": speaker,
        "pace": 1.0,
        "speech_sample_rate": 22050,
    }

    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(url, headers=headers, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                audios = data.get("audios", [])
                if audios:
                    return base64.b64decode(audios[0])
            print(f"Sarvam TTS failed with status {resp.status_code}: {resp.text}")
    except Exception as exc:
        print(f"Exception during Sarvam TTS request: {exc}")

    return None


def render_all_samples(
    samples_file: Path = Path("eval/samples/samples.yaml"),
    audio_dir: Path = Path("eval/samples/audio"),
    recorded_dir: Path = Path("eval/samples/recorded"),
    chips_output: Path = Path("eval/samples/demo_chips.json"),
    force: bool = False,
    mock: bool = False,
) -> int:
    """Renders all evaluator samples to audio and generates demo chips manifest."""
    samples = load_samples(samples_file)
    audio_dir.mkdir(parents=True, exist_ok=True)

    sarvam_key = os.environ.get("SARVAM_API_KEY") if not mock else None
    ffmpeg_available = shutil.which("ffmpeg") is not None

    chips: list[dict[str, Any]] = []

    for s in samples:
        s_id = s["id"]
        step = s.get("step", "REHEARSE")
        text_hi = normalize_nfc(s["text_hi"])
        expect = normalize_nfc(s.get("expect", ""))
        label_hi = DEFAULT_CHIP_LABELS.get(s_id, s_id)

        wav_path = audio_dir / f"{s_id}.wav"
        ogg_path = audio_dir / f"{s_id}.ogg"

        audio_bytes: bytes | None = None
        source_desc = "placeholder"

        # 1. Check for human pre-recording (preferred per spec/14 H15)
        recorded_ogg = recorded_dir / f"{s_id}.ogg"
        recorded_wav = recorded_dir / f"{s_id}.wav"

        if recorded_ogg.exists():
            print(f"[{s_id}] Using human recording: {recorded_ogg.name}")
            audio_bytes = recorded_ogg.read_bytes()
            ogg_path.write_bytes(audio_bytes)
            # If wav does not exist, also write copy or convert
            wav_path.write_bytes(audio_bytes)
            source_desc = "human_recorded"
        elif recorded_wav.exists():
            print(f"[{s_id}] Using human recording: {recorded_wav.name}")
            audio_bytes = recorded_wav.read_bytes()
            wav_path.write_bytes(audio_bytes)
            ogg_path.write_bytes(audio_bytes)
            source_desc = "human_recorded"
        elif (not force) and wav_path.exists() and ogg_path.exists():
            print(f"[{s_id}] Audio already exists, keeping existing files.")
            source_desc = "existing"
        else:
            # 2. Try Sarvam TTS if key available
            if sarvam_key:
                print(f"[{s_id}] Synthesizing via Sarvam TTS (adult teacher voice)...")
                audio_bytes = synthesize_sarvam_tts(text_hi, sarvam_key)
                if audio_bytes:
                    source_desc = "sarvam_tts"

            # 3. Fallback to synthetic PCM WAV
            if not audio_bytes:
                print(f"[{s_id}] Generating synthetic placeholder audio...")
                audio_bytes = generate_synthetic_wav(text_hi)
                source_desc = "synthetic_placeholder"

            wav_path.write_bytes(audio_bytes)

            # Generate OGG format
            if ffmpeg_available:
                try:
                    import subprocess

                    cmd = [
                        "ffmpeg",
                        "-y",
                        "-i",
                        str(wav_path),
                        "-c:a",
                        "libopus",
                        "-b:a",
                        "24k",
                        "-ac",
                        "1",
                        "-ar",
                        "48000",
                        str(ogg_path),
                    ]
                    subprocess.run(
                        cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                    )
                except Exception:
                    # Fallback to direct bytes
                    ogg_path.write_bytes(audio_bytes)
            else:
                # Without ffmpeg, write audio bytes so both files exist
                ogg_path.write_bytes(audio_bytes)

        chips.append(
            {
                "id": s_id,
                "step": step,
                "chip_label": label_hi,
                "text_hi": text_hi,
                "audio_file": f"{s_id}.wav",
                "audio_ogg": f"{s_id}.ogg",
                "audio_relative_path": f"eval/samples/audio/{s_id}.wav",
                "source": source_desc,
                "expected_behavior": expect,
            }
        )

    # Save chips manifest
    chips_output.parent.mkdir(parents=True, exist_ok=True)
    with open(chips_output, "w", encoding="utf-8") as f:
        json.dump(chips, f, ensure_ascii=False, indent=2)

    print(
        f"Successfully rendered {len(chips)} evaluator samples and generated chips at {chips_output}"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Render evaluator sample inputs to audio and generate demo chips."
    )
    parser.add_argument(
        "--samples-file",
        type=Path,
        default=Path("eval/samples/samples.yaml"),
        help="Path to evaluator samples YAML file",
    )
    parser.add_argument(
        "--audio-dir",
        type=Path,
        default=Path("eval/samples/audio"),
        help="Output directory for audio files",
    )
    parser.add_argument(
        "--recorded-dir",
        type=Path,
        default=Path("eval/samples/recorded"),
        help="Directory with pre-recorded human samples",
    )
    parser.add_argument(
        "--chips-output",
        type=Path,
        default=Path("eval/samples/demo_chips.json"),
        help="Output path for demo chips JSON",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-rendering even if audio files exist",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Force mock/placeholder audio generation",
    )

    args = parser.parse_args()
    return render_all_samples(
        samples_file=args.samples_file,
        audio_dir=args.audio_dir,
        recorded_dir=args.recorded_dir,
        chips_output=args.chips_output,
        force=args.force,
        mock=args.mock,
    )


if __name__ == "__main__":
    sys.exit(main())
