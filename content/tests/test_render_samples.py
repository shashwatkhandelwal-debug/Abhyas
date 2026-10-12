"""Tests for scripts/render_samples.py and evaluator demo chips (spec/13 §13.1, spec/14 T39)."""

import json
import subprocess
import sys
import unicodedata
import wave
from pathlib import Path

from scripts.render_samples import (
    DEFAULT_CHIP_LABELS,
    generate_synthetic_wav,
    is_nfc,
    load_samples,
    render_all_samples,
)


def test_load_samples_valid() -> None:
    """Samples YAML loads correctly and contains 3-5 valid sample definitions."""
    samples = load_samples(Path("eval/samples/samples.yaml"))
    assert 3 <= len(samples) <= 5
    for s in samples:
        assert "id" in s
        assert "text_hi" in s
        assert is_nfc(s["text_hi"])
        assert s["id"] in DEFAULT_CHIP_LABELS


def test_generate_synthetic_wav_format() -> None:
    """Synthetic WAV generator produces valid 16kHz mono 16-bit PCM WAV bytes."""
    wav_bytes = generate_synthetic_wav("परीक्षण वाक्य", duration_s=1.0)
    assert len(wav_bytes) > 44

    import io

    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        assert wf.getnchannels() == 1
        assert wf.getsampwidth() == 2
        assert wf.getframerate() == 16000
        assert wf.getnframes() == 16000


def test_render_all_samples_mock_run(tmp_path: Path) -> None:
    """render_all_samples in mock mode creates wav, ogg, and demo_chips.json."""
    audio_dir = tmp_path / "audio"
    recorded_dir = tmp_path / "recorded"
    chips_file = tmp_path / "demo_chips.json"

    ret = render_all_samples(
        samples_file=Path("eval/samples/samples.yaml"),
        audio_dir=audio_dir,
        recorded_dir=recorded_dir,
        chips_output=chips_file,
        force=True,
        mock=True,
    )
    assert ret == 0

    # Verify audio files exist and are valid WAVs
    samples = load_samples(Path("eval/samples/samples.yaml"))
    for s in samples:
        s_id = s["id"]
        wav_file = audio_dir / f"{s_id}.wav"
        ogg_file = audio_dir / f"{s_id}.ogg"
        assert wav_file.exists(), f"Missing WAV for {s_id}"
        assert ogg_file.exists(), f"Missing OGG for {s_id}"
        assert wav_file.stat().st_size > 1000

        with wave.open(str(wav_file), "rb") as wf:
            assert wf.getnchannels() == 1
            assert wf.getnframes() > 0

    # Verify demo_chips.json
    assert chips_file.exists()
    with open(chips_file, encoding="utf-8") as f:
        chips_data = json.load(f)

    assert len(chips_data) == len(samples)
    for chip in chips_data:
        assert "id" in chip
        assert "step" in chip
        assert "chip_label" in chip
        assert "text_hi" in chip
        assert "audio_file" in chip
        assert "expected_behavior" in chip
        assert chip["text_hi"] == unicodedata.normalize("NFC", chip["text_hi"])
        assert chip["chip_label"] == unicodedata.normalize("NFC", chip["chip_label"])


def test_render_all_samples_recorded_override(tmp_path: Path) -> None:
    """Pre-recorded audio in recorded_dir takes precedence over synthetic generator."""
    audio_dir = tmp_path / "audio"
    recorded_dir = tmp_path / "recorded"
    recorded_dir.mkdir(parents=True, exist_ok=True)
    chips_file = tmp_path / "demo_chips.json"

    # Place a dummy recorded file for s1_ask_ravi
    custom_wav = generate_synthetic_wav("कस्टम रिकॉर्डिंग", duration_s=0.5)
    (recorded_dir / "s1_ask_ravi.wav").write_bytes(custom_wav)

    render_all_samples(
        samples_file=Path("eval/samples/samples.yaml"),
        audio_dir=audio_dir,
        recorded_dir=recorded_dir,
        chips_output=chips_file,
        force=True,
        mock=True,
    )

    with open(chips_file, encoding="utf-8") as f:
        chips = json.load(f)

    s1_chip = next(c for c in chips if c["id"] == "s1_ask_ravi")
    assert s1_chip["source"] == "human_recorded"


def test_cli_execution() -> None:
    """Running render_samples via CLI succeeds cleanly."""
    cmd = [sys.executable, "scripts/render_samples.py", "--mock"]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    assert proc.returncode == 0
    assert "Successfully rendered 5 evaluator samples" in proc.stdout
