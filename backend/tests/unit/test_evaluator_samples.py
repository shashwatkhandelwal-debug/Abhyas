"""Unit tests for evaluator audio samples and demo chips (spec/06 §6.3, spec/14 T39)."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import pytest
import yaml
from httpx import ASGITransport, AsyncClient

from backend.app.auth.guards import get_current_user
from backend.app.db.models import AppUser
from backend.app.main import app

REPO_ROOT = Path(__file__).resolve().parents[3]
SAMPLES_YAML = REPO_ROOT / "eval" / "samples" / "samples.yaml"
AUDIO_DIR = REPO_ROOT / "eval" / "samples" / "audio"
DEMO_CHIPS_JSON = REPO_ROOT / "eval" / "samples" / "demo_chips.json"


def test_samples_yaml_conforms_to_spec() -> None:
    """samples.yaml must contain at least 5 evaluator samples with id, text_hi, step, expect."""
    assert SAMPLES_YAML.is_file(), f"Missing samples.yaml at {SAMPLES_YAML}"
    data: dict[str, Any] = yaml.safe_load(SAMPLES_YAML.read_text(encoding="utf-8"))
    samples = data.get("samples", [])
    assert len(samples) >= 5, f"Expected >= 5 samples, found {len(samples)}"

    for s in samples:
        assert "id" in s and s["id"].strip()
        assert "text_hi" in s and s["text_hi"].strip()
        assert "step" in s and s["step"].strip()
        assert "expect" in s and s["expect"].strip()


def test_rendered_audio_files_exist_and_are_valid_wav() -> None:
    """make samples must output valid RIFF WAV audio files in eval/samples/audio/."""
    assert AUDIO_DIR.is_dir(), f"Missing audio dir at {AUDIO_DIR}"
    data: dict[str, Any] = yaml.safe_load(SAMPLES_YAML.read_text(encoding="utf-8"))
    samples = data.get("samples", [])

    for s in samples:
        wav_path = AUDIO_DIR / f"{s['id']}.wav"
        assert wav_path.is_file(), f"Missing audio file for sample {s['id']}: {wav_path}"
        bytes_data = wav_path.read_bytes()
        assert len(bytes_data) > 44, f"WAV file too small: {len(bytes_data)} bytes"
        assert bytes_data.startswith(b"RIFF"), f"File {wav_path} does not start with RIFF header"
        assert b"WAVE" in bytes_data[:12], f"File {wav_path} does not contain WAVE marker"


def test_demo_chips_json_validity() -> None:
    """demo_chips.json must match samples with labels and audio_available."""
    assert DEMO_CHIPS_JSON.is_file(), f"Missing demo_chips.json at {DEMO_CHIPS_JSON}"
    chips: list[dict[str, Any]] = json.loads(DEMO_CHIPS_JSON.read_text(encoding="utf-8"))
    assert len(chips) >= 5, f"Expected >= 5 demo chips, found {len(chips)}"

    for chip in chips:
        assert "id" in chip
        assert "chip_label" in chip and chip["chip_label"].strip()
        assert "text_hi" in chip and chip["text_hi"].strip()
        assert chip.get("audio_available") is True
        assert "audio_url" in chip


@pytest.mark.asyncio
async def test_get_demo_sample_audio_endpoint() -> None:
    """GET /api/demo-sample/{sample_id}.wav returns audio with correct headers."""
    mock_user = AppUser(
        id=uuid.uuid4(),
        username="teacher.demo",
        role="teacher",
        display_name="डेमो शिक्षिका",
        password_hash="hash",
    )
    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/demo-sample/s1_ask_ravi.wav")
            assert resp.status_code == 200
            assert resp.headers["content-type"].startswith("audio/wav")
            assert len(resp.content) > 44
            assert resp.content.startswith(b"RIFF")
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_get_demo_sample_audio_not_found_and_traversal() -> None:
    """Directory traversal and nonexistent samples return 404."""
    mock_user = AppUser(
        id=uuid.uuid4(),
        username="teacher.demo",
        role="teacher",
        display_name="डेमो शिक्षिका",
        password_hash="hash",
    )
    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp1 = await client.get("/api/demo-sample/nonexistent_sample_xyz.wav")
            assert resp1.status_code == 404

            resp2 = await client.get("/api/demo-sample/.._.._something.wav")
            assert resp2.status_code == 404
    finally:
        app.dependency_overrides.pop(get_current_user, None)
