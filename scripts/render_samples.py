"""Render evaluator sample voice notes into eval/samples/audio/ (spec/06 §6.3, spec/14 T39).

Reads eval/samples/samples.yaml, synthesizes audio for each sample using
an adult teacher voice via the configured TTS provider (or MockTTS if keys absent),
and outputs:
- eval/samples/audio/<id>.wav
- eval/samples/demo_chips.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any

import yaml

from backend.app.config import settings
from backend.app.speech.audio import is_wav_non_silent
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
    "s2_diagnose_one_on_one": "उलझन पहचानें (1-1)",
    "s3_tell_answer_hinglish": "सीधा उत्तर बताएँ (हिंग्लिश)",
    "s4_explain_back": "तरीका समझाएँ (Explain-back)",
    "s5_question_multigrade": "बहु-कक्षा सवाल (Ask)",
}

# English chip labels for the English UI (the sample utterances themselves stay Hindi)
CHIP_LABELS_EN: dict[str, str] = {
    "s1_ask_ravi": "Ask Ravi how he did it",
    "s2_diagnose_one_on_one": "Spot the confusion (1-1)",
    "s3_tell_answer_hinglish": "Tell the answer (Hinglish)",
    "s4_explain_back": "Explain the move (explain-back)",
    "s5_question_multigrade": "Multi-grade question (Ask)",
}


async def render_samples(allow_mock: bool = False) -> None:
    """Renders all sample audio files and writes demo_chips.json."""
    if not SAMPLES_YAML_PATH.is_file():
        raise FileNotFoundError(f"Missing samples specification: {SAMPLES_YAML_PATH}")

    # Blocker 1: Must error when TTS_PROVIDER is mock unless --allow-mock is passed explicitly
    if (settings.TTS_PROVIDER == "mock" or not settings.SARVAM_API_KEY) and not allow_mock:
        logger.error(
            "TTS_PROVIDER is 'mock' (or SARVAM_API_KEY is not configured). "
            "Evaluator voice notes must be rendered with a real TTS provider (Sarvam AI) "
            "or real recorded voice notes, not MockTTS (silent audio). "
            "To allow mock audio for test execution, pass --allow-mock explicitly."
        )
        sys.exit(1)

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
        "Rendering %d evaluator samples using voice '%s' (provider: %s)...",
        len(raw_samples),
        voice.provider_speaker,
        settings.TTS_PROVIDER,
    )

    for s in raw_samples:
        sample_id: str = s["id"]
        text_hi: str = s["text_hi"]
        step: str = s.get("step", "REHEARSE")
        expect: str = s.get("expect", "")
        chip_label: str = CHIP_LABELS.get(sample_id, text_hi[:20])
        chip_label_en: str = CHIP_LABELS_EN.get(sample_id, chip_label)

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

        # audio_available must be computed: file exists and is not silent
        audio_avail = is_wav_non_silent(out_wav_path)

        chips.append(
            {
                "id": sample_id,
                "step": step,
                "text_hi": text_hi,
                "expect": expect,
                "chip_label": chip_label,
                "chip_label_en": chip_label_en,
                "audio_available": audio_avail,
                "audio_url": f"/api/demo-sample/{sample_id}.wav" if audio_avail else None,
            }
        )

    DEMO_CHIPS_JSON_PATH.write_text(
        json.dumps(chips, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("Successfully processed %d samples in %s", len(chips), OUTPUT_AUDIO_DIR)
    logger.info("Generated demo chips manifest at %s", DEMO_CHIPS_JSON_PATH)


def main() -> None:
    """Entry point for make samples."""
    parser = argparse.ArgumentParser(description="Render evaluator sample voice notes")
    parser.add_argument(
        "--allow-mock",
        action="store_true",
        help="Allow synthesizing with MockTTS (generates silent audio for testing)",
    )
    args = parser.parse_args()
    asyncio.run(render_samples(allow_mock=args.allow_mock))


if __name__ == "__main__":
    main()
