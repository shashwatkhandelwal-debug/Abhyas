"""Script to generate audio test fixtures for T15 / T16 (spec/06 §6.1, spec/14)."""

import json
import subprocess
from pathlib import Path

from backend.app.speech.audio import get_ffmpeg_path


def main() -> None:
    ffmpeg = get_ffmpeg_path()
    fixtures_dir = Path(__file__).parents[1] / "backend" / "tests" / "fixtures" / "audio"
    fixtures_dir.mkdir(parents=True, exist_ok=True)

    wav_5s = fixtures_dir / "sample_5s.wav"
    ogg_5s = fixtures_dir / "sample_5s.ogg"
    webm_5s = fixtures_dir / "sample_5s.webm"
    mp4_5s = fixtures_dir / "sample_5s.mp4"
    wav_60s = fixtures_dir / "sample_60s.wav"
    meta_5s = fixtures_dir / "sample_5s.json"

    # 1. 5s sine tone WAV (16kHz mono)
    print("Generating sample_5s.wav...")
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=5",
            "-ar",
            "16000",
            "-ac",
            "1",
            str(wav_5s),
        ],
        check=True,
    )

    # 2. 5s OGG Opus
    print("Generating sample_5s.ogg...")
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-i",
            str(wav_5s),
            "-c:a",
            "libopus",
            "-b:a",
            "24k",
            str(ogg_5s),
        ],
        check=True,
    )

    # 3. 5s WebM Opus
    print("Generating sample_5s.webm...")
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-i",
            str(wav_5s),
            "-c:a",
            "libopus",
            "-b:a",
            "24k",
            str(webm_5s),
        ],
        check=True,
    )

    # 4. 5s MP4 AAC
    print("Generating sample_5s.mp4...")
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-i",
            str(wav_5s),
            "-c:a",
            "aac",
            "-b:a",
            "32k",
            str(mp4_5s),
        ],
        check=True,
    )

    # 5. 60s WAV with tones and silences at ~20s and ~41s
    # 20s tone + 1s silence + 20s tone + 1s silence + 18s tone = 60s
    print("Generating sample_60s.wav...")
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=20",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=16000:cl=mono:d=1",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=20",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=16000:cl=mono:d=1",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=18",
            "-filter_complex",
            "[0:a][1:a][2:a][3:a][4:a]concat=n=5:v=0:a=1[out]",
            "-map",
            "[out]",
            "-ar",
            "16000",
            "-ac",
            "1",
            str(wav_60s),
        ],
        check=True,
    )

    # 6. JSON metadata for mock STT
    print("Generating sample_5s.json...")
    meta_5s.write_text(
        json.dumps(
            {
                "text": "रवि, 52 में से 17 कैसे घटाया? बताओ।",
                "language": "hi-IN",
                "confidence": 0.9,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print("Done! Fixtures generated successfully in", fixtures_dir)


if __name__ == "__main__":
    main()
