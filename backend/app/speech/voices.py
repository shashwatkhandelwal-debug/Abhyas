"""Voice catalog and VoiceSpec definitions for Abhyas TTS (spec/06 §6.3).

Provides voice specifications for system narrator, coach, model teacher,
and 3 simulated primary school children (Ravi, Priya, Aman).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel

logger = logging.getLogger("abhyas.speech.voices")


class VoiceSpec(BaseModel):
    """Specification of voice model, speaker, pacing, pitch factor, and gender (spec/06 §6.3)."""

    provider_speaker: str
    model: str = "bulbul:v3"
    pace: float = 1.0
    pitch_factor: float = 1.0
    gender: Literal["f", "m"] = "f"


# Default canonical voice catalog (spec/06 §6.3)
VOICE_CATALOG: dict[str, VoiceSpec] = {
    # System narrator / learn scripts
    "abhyas": VoiceSpec(
        provider_speaker="ritu",
        model="bulbul:v3",
        pace=0.95,
        pitch_factor=1.0,
        gender="f",
    ),
    # Coach feedback
    "coach": VoiceSpec(
        provider_speaker="neha",
        model="bulbul:v3",
        pace=0.95,
        pitch_factor=1.0,
        gender="f",
    ),
    # Model rehearsal teacher
    "model_teacher": VoiceSpec(
        provider_speaker="pooja",
        model="bulbul:v3",
        pace=1.0,
        pitch_factor=1.0,
        gender="f",
    ),
    # Confident boy (Ravi)
    "child_ravi": VoiceSpec(
        provider_speaker="aayan",
        model="bulbul:v3",
        pace=1.15,
        pitch_factor=1.22,
        gender="m",
    ),
    # Shy girl (Priya)
    "child_priya": VoiceSpec(
        provider_speaker="suhani",
        model="bulbul:v3",
        pace=0.90,
        pitch_factor=1.18,
        gender="f",
    ),
    # Distracted boy (Aman)
    "child_aman": VoiceSpec(
        provider_speaker="soham",
        model="bulbul:v3",
        pace=1.05,
        pitch_factor=1.25,
        gender="m",
    ),
}


def load_voices(path: Path | str | None = None) -> dict[str, VoiceSpec]:
    """Loads voices from YAML file or falls back to built-in VOICE_CATALOG (spec/06 §6.3)."""
    voices = dict(VOICE_CATALOG)

    if path is None:
        yaml_path = Path(__file__).parents[2] / "content" / "voices.yaml"
    else:
        yaml_path = Path(path)

    if yaml_path.is_file():
        try:
            content = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
            if isinstance(content, dict):
                for voice_id, spec_dict in content.items():
                    if isinstance(spec_dict, dict):
                        voices[voice_id] = VoiceSpec(**spec_dict)
        except Exception as exc:
            logger.warning("Failed loading voices from %s: %s, using defaults", yaml_path, exc)

    return voices


def get_voice(voice_id: str) -> VoiceSpec:
    """Returns VoiceSpec for given voice identifier (spec/06 §6.3)."""
    if voice_id in VOICE_CATALOG:
        return VOICE_CATALOG[voice_id]

    logger.warning("Voice %s not found in catalog, falling back to 'abhyas'", voice_id)
    return VOICE_CATALOG["abhyas"]
