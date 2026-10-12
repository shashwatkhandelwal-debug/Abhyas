"""Audition candidate speakers for child and adult personas (spec/06 §6.3, T17).

Synthesizes sample lines with Sarvam bulbul:v3 speakers to compare voices by ear.
Saves audio output files to auditions/ directory.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from backend.app.speech.audio import to_ogg_opus
from backend.app.speech.tts import get_tts_provider
from backend.app.speech.voices import VoiceSpec

SAMPLE_LINES = [
    ("ravi_line", "रवि, 52 में से 17 कैसे घटाया? बताओ।", 1.22),
    ("priya_line", "पैंतालीस!", 1.18),
    ("aman_line", "सर, तीली बंडल से दिखाओ।", 1.25),
    ("coach_line", "शाबाश! आपने बच्चे से उसके सोचने का तरीका पूछा।", 1.0),
]

CANDIDATE_SPEAKERS = [
    ("ritu", "bulbul:v3", 0.95),
    ("neha", "bulbul:v3", 0.95),
    ("pooja", "bulbul:v3", 1.0),
    ("aayan", "bulbul:v3", 1.15),
    ("suhani", "bulbul:v3", 0.90),
    ("soham", "bulbul:v3", 1.05),
    ("shweta", "bulbul:v3", 1.0),
    ("rahul", "bulbul:v3", 1.0),
]


async def audition() -> None:
    output_dir = Path(__file__).parents[1] / "auditions"
    output_dir.mkdir(parents=True, exist_ok=True)

    tts = get_tts_provider()
    print(f"Using TTS provider: {type(tts).__name__}")
    print(f"Saving audition clips to: {output_dir}")

    for tag, line, pitch in SAMPLE_LINES:
        print(f"\nAuditioning line: '{line}' (pitch factor: {pitch})")
        for speaker, model, pace in CANDIDATE_SPEAKERS:
            voice = VoiceSpec(
                provider_speaker=speaker,
                model=model,
                pace=pace,
                pitch_factor=pitch,
            )
            wav_bytes = await tts.synthesize(line, voice)
            wav_path = output_dir / f"{tag}_{speaker}.wav"
            wav_path.write_bytes(wav_bytes)

            try:
                ogg_bytes = await to_ogg_opus(wav_bytes)
                ogg_path = output_dir / f"{tag}_{speaker}.ogg"
                ogg_path.write_bytes(ogg_bytes)
            except Exception:
                pass

            print(f"  Generated {wav_path.name} ({len(wav_bytes)} bytes)")

    print("\nAudition complete! Listen to clips in auditions/ to compare candidate voices.")


def main() -> None:
    asyncio.run(audition())


if __name__ == "__main__":
    main()
