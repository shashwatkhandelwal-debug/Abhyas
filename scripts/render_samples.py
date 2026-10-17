"""Render evaluator sample voice notes into eval/samples/audio/ (spec/06 §6.3, spec/14 T39).

Reads eval/samples/samples.yaml, synthesizes audio for each sample using
an adult teacher voice via the configured TTS provider (or MockTTS if keys absent),
and outputs:
- eval/samples/audio/<id>.wav
- eval/samples/demo_chips.json
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

import yaml

from backend.app.speech.tts import get_tts_provider
from backend.app.speech.voices import get_voice

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("abhyas.scripts.render_samples")

REPO_ROOT = Path(__file__).resolve().parent.parent
SAMPLES_YAML_PATH = REPO_ROOT / "eval" / "samples" / "samples.yaml"
OUTPUT_AUDIO_DIR = REPO_ROOT / "eval" / "samples" / "audio"
DEMO_CHIPS_JSON_PATH = REPO_ROOT / "eval" / "samples" / "demo_chips.json"
RECORDED_DIR = REPO_ROOT / "eval" / "samples" / "recorded"

CHIP_LABELS: dict[str, str] = {
    "s1_ask_ravi": "रवि से तरीका पूछें",
    "s2_bundles_all": "बंडल-तीली से समझाएँ",
    "s3_tell_answer_hinglish": "सीधा उत्तर बताएँ (हिंग्लिश)",
    "s4_explain_back": "तरीका समझाएँ (Explain-back)",
    "s5_question_multigrade": "बहु-कक्षा सवाल (Ask)",
}


async def render_samples() -> None:
    """Renders all sample audio files and writes demo_chips.json."""
    if not SAMPLES_YAML_PATH.is_file():
        raise FileNotFoundError(f"Missing samples specification: {SAMPLES_YAML_PATH}")

    OUTPUT_AUDIO_DIR.mkdir(parents=True, exist_ok=True)

    data: dict[str, Any] = yaml.safe_load(SAMPLES_YAML_PATH.read_text(encoding="utf-8"))
    raw_samples: list[dict[str, Any]] = data.get("samples", [])
    if not raw_samples:
        raise ValueError("No samples found in samples.yaml")

    tts = get_tts_provider()
    # Adult teacher voice (model_teacher / pooja)
    voice = get_voice("model_teacher")

    chips: list[dict[str, Any]] = []

    logger.info(
        "Rendering %d evaluator samples using voice '%s'...",
        len(raw_samples),
        voice.provider_speaker,
    )

    for s in raw_samples:
        sample_id: str = s["id"]
        text_hi: str = s["text_hi"]
        step: str = s.get("step", "REHEARSE")
        expect: str = s.get("expect", "")
        chip_label: str = CHIP_LABELS.get(sample_id, text_hi[:20])

        out_wav_path = OUTPUT_AUDIO_DIR / f"{sample_id}.wav"

        # 1. Check if human-recorded sample exists (H15)
        recorded_candidate_wav = RECORDED_DIR / f"{sample_id}.wav"
        recorded_candidate_ogg = RECORDED_DIR / f"{sample_id}.ogg"

        audio_bytes: bytes = b""
        if recorded_candidate_wav.is_file():
            logger.info("Using recorded WAV for %s", sample_id)
            audio_bytes = recorded_candidate_wav.read_bytes()
            out_wav_path.write_bytes(audio_bytes)
        elif recorded_candidate_ogg.is_file():
            logger.info("Using recorded OGG for %s", sample_id)
            audio_bytes = recorded_candidate_ogg.read_bytes()
            out_wav_path.write_bytes(audio_bytes)
        else:
            # 2. Synthesize via TTS provider
            logger.info("Synthesizing audio for '%s': %s", sample_id, text_hi)
            res = await tts.synthesize(text_hi, voice=voice)
            audio_bytes = res.audio
            out_wav_path.write_bytes(audio_bytes)

        chips.append(
            {
                "id": sample_id,
                "step": step,
                "text_hi": text_hi,
                "expect": expect,
                "chip_label": chip_label,
                "audio_available": len(audio_bytes) > 0,
                "audio_url": f"/api/demo-sample/{sample_id}.wav",
            }
        )

    DEMO_CHIPS_JSON_PATH.write_text(
        json.dumps(chips, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("Successfully rendered %d samples to %s", len(chips), OUTPUT_AUDIO_DIR)
    logger.info("Generated demo chips manifest at %s", DEMO_CHIPS_JSON_PATH)


def main() -> None:
    """Entry point for make samples."""
    asyncio.run(render_samples())


if __name__ == "__main__":
    main()
