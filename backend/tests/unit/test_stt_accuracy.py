"""Unit tests for STT accuracy evaluation (Task T62, spec/06 §6.2, spec/11 §11.2)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from backend.app.speech.stt import Transcript
from eval.stt.stt_accuracy import (
    clean_text_for_eval,
    compute_cer,
    compute_wer,
    levenshtein_distance,
    run_stt_evaluation,
)


class FakeSTTProvider:
    """Fake STT provider for deterministic unit testing."""

    def __init__(self, responses: dict[str, str]) -> None:
        self.responses = responses
        self.call_count = 0

    async def transcribe(
        self,
        wav16k: bytes,
        lang: str = "hi-IN",
        keyterms: list[str] | None = None,
    ) -> Transcript:
        self.call_count += 1
        # Use header content or lookup from decoded string if encoded
        text = "रवि तुमने कैसे किया"
        for key, val in self.responses.items():
            if key.encode("utf-8") in wav16k:
                text = val
                break
        return Transcript(
            text=text,
            confidence=0.95,
            language=lang,
            provider="fake_stt",
            ms=120,
        )


def test_clean_text_for_eval() -> None:
    """Verifies punctuation removal, whitespace collapsing, and NFC normalisation."""
    raw = "रवि,  तुमने 43 में से 27 कैसे घटाया?  मुझे बताओ। "
    cleaned = clean_text_for_eval(raw)
    assert "।" not in cleaned
    assert "," not in cleaned
    assert "?" not in cleaned
    assert cleaned == "रवि तुमने 43 में से 27 कैसे घटाया मुझे बताओ"
    assert clean_text_for_eval("") == ""


def test_levenshtein_distance() -> None:
    """Verifies Wagner-Fischer edit distance on sequences."""
    assert levenshtein_distance([], []) == 0
    assert levenshtein_distance(["a", "b"], ["a", "b"]) == 0
    assert levenshtein_distance(["a", "b"], ["a", "c"]) == 1
    assert levenshtein_distance(["a"], ["a", "b", "c"]) == 2
    assert levenshtein_distance(["a", "b", "c"], ["b", "c"]) == 1


def test_compute_wer_and_cer() -> None:
    """Verifies WER and CER metric calculations."""
    ref = "रवि तुमने 43 में से 27 कैसे घटाया"
    hyp_exact = "रवि तुमने 43 में से 27 कैसे घटाया"
    assert compute_wer(ref, hyp_exact) == 0.0
    assert compute_cer(ref, hyp_exact) == 0.0

    # 1 word changed out of 8 words (1/8 = 0.125)
    hyp_diff_word = "रवि तुमने 43 में से 27 क्यों घटाया"
    wer = compute_wer(ref, hyp_diff_word)
    assert wer == 0.125

    # Completely different
    assert compute_wer("", hyp_exact) == 1.0
    assert compute_wer(ref, "") == 1.0
    assert compute_wer("", "") == 0.0


@pytest.mark.asyncio
async def test_run_stt_evaluation_no_recordings(tmp_path: Path) -> None:
    """Verifies that an empty recorded folder outputs 'No recordings yet' report."""
    samples_file = tmp_path / "samples.yaml"
    samples_file.write_text(
        yaml.dump(
            {
                "samples": [
                    {"id": "s1_ask_ravi", "text_hi": "रवि तुमने कैसे घटाया"},
                ]
            }
        ),
        encoding="utf-8",
    )
    recorded_dir = tmp_path / "recorded"
    recorded_dir.mkdir()
    report_file = tmp_path / "REPORT.md"

    summary = await run_stt_evaluation(
        samples_path=samples_file,
        recorded_dir=recorded_dir,
        report_path=report_file,
        provider_name="MockSTT",
    )

    assert summary.sample_count == 0
    assert summary.mean_wer == 0.0
    assert "No recordings yet" in summary.report_md
    assert report_file.is_file()
    assert "No recordings yet" in report_file.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_run_stt_evaluation_with_fake_provider(tmp_path: Path) -> None:
    """Verifies STT accuracy computation with sample files and a fake provider fixture."""
    samples_file = tmp_path / "samples.yaml"
    samples_file.write_text(
        yaml.dump(
            {
                "samples": [
                    {"id": "s1_ask_ravi", "text_hi": "रवि तुमने 43 में से 27 कैसे घटाया"},
                    {"id": "s2_bundles_all", "text_hi": "सब लोग देखो ये बंडल हैं"},
                ]
            }
        ),
        encoding="utf-8",
    )

    recorded_dir = tmp_path / "recorded"
    recorded_dir.mkdir()

    # Create dummy wav files with embedded marker text
    s1_wav = recorded_dir / "s1_ask_ravi.wav"
    s1_wav.write_bytes(b"RIFF....WAVEfmt ....data" + b"s1_marker")

    s2_ogg = recorded_dir / "s2_bundles_all.ogg"
    s2_ogg.write_bytes(b"OggS...." + b"s2_marker")

    # Unlisted recording should be skipped
    unlisted_wav = recorded_dir / "s99_unknown.wav"
    unlisted_wav.write_bytes(b"RIFF....WAVE" + b"unlisted")

    fake_provider = FakeSTTProvider(
        responses={
            "s1_marker": "रवि तुमने 43 में से 27 कैसे घटाया",  # exact match
            "s2_marker": "सब लोग सुनो ये बंडल हैं",  # 'सुनो' instead of 'देखो'
        }
    )

    report_file = tmp_path / "REPORT.md"
    summary = await run_stt_evaluation(
        samples_path=samples_file,
        recorded_dir=recorded_dir,
        report_path=report_file,
        provider=fake_provider,
        provider_name="FakeSTTProvider",
    )

    assert summary.sample_count == 2
    assert summary.results[0].sample_id == "s1_ask_ravi"
    assert summary.results[0].wer == 0.0
    assert summary.results[0].cer == 0.0

    assert summary.results[1].sample_id == "s2_bundles_all"
    assert summary.results[1].wer > 0.0

    assert summary.mean_wer > 0.0
    assert report_file.is_file()
    content = report_file.read_text(encoding="utf-8")
    assert "FakeSTTProvider" in content
    assert "`s1_ask_ravi`" in content
    assert "`s2_bundles_all`" in content
    assert "`s99_unknown`" not in content
