"""STT Accuracy Evaluation (Task T62, spec/06 §6.2, spec/11 §11.2).

Evaluates Word Error Rate (WER) and Character Error Rate (CER) on NFC-normalised
Hindi text for recorded sample voice inputs in eval/samples/recorded/.
Never uses synthetic TTS audio as a stand-in for human speech.
"""

from __future__ import annotations

import argparse
import asyncio
import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TypeVar

import yaml

from backend.app.speech.audio import to_wav16k
from backend.app.speech.stt import STTProvider, get_stt_provider

T = TypeVar("T")


def clean_text_for_eval(text: str) -> str:
    """NFC-normalises Hindi text, strips punctuation, and collapses whitespace.

    Retains numerals and word characters for accurate error rate calculation.
    """
    if not text:
        return ""
    norm = unicodedata.normalize("NFC", text)
    # Strip common Indic and Latin punctuation: danda (।), double danda (॥), commas, etc.
    norm = re.sub(r"[।॥,\.!\?\":;\-—_/\(\)\[\]'\"`]", " ", norm)
    return re.sub(r"\s+", " ", norm).strip()


def levenshtein_distance(seq1: Sequence[T], seq2: Sequence[T]) -> int:
    """Computes exact Levenshtein edit distance using Wagner-Fischer algorithm."""
    m, n = len(seq1), len(seq2)
    if m == 0:
        return n
    if n == 0:
        return m

    prev = list(range(n + 1))
    curr = [0] * (n + 1)

    for i in range(1, m + 1):
        curr[0] = i
        elem1 = seq1[i - 1]
        for j in range(1, n + 1):
            cost = 0 if elem1 == seq2[j - 1] else 1
            curr[j] = min(
                prev[j] + 1,  # deletion
                curr[j - 1] + 1,  # insertion
                prev[j - 1] + cost,  # substitution
            )
        prev, curr = curr, prev

    return prev[n]


def compute_wer(reference: str, hypothesis: str) -> float:
    """Computes Word Error Rate (WER) on NFC-normalised cleaned text."""
    ref_clean = clean_text_for_eval(reference)
    hyp_clean = clean_text_for_eval(hypothesis)

    ref_words = ref_clean.split()
    hyp_words = hyp_clean.split()

    if not ref_words:
        return 0.0 if not hyp_words else 1.0

    dist = levenshtein_distance(ref_words, hyp_words)
    return dist / len(ref_words)


def compute_cer(reference: str, hypothesis: str) -> float:
    """Computes Character Error Rate (CER) on non-space characters of NFC text."""
    ref_clean = clean_text_for_eval(reference)
    hyp_clean = clean_text_for_eval(hypothesis)

    ref_chars = [c for c in ref_clean if not c.isspace()]
    hyp_chars = [c for c in hyp_clean if not c.isspace()]

    if not ref_chars:
        return 0.0 if not hyp_chars else 1.0

    dist = levenshtein_distance(ref_chars, hyp_chars)
    return dist / len(ref_chars)


@dataclass
class SampleEvalResult:
    """Evaluation result for an individual recorded sample."""

    sample_id: str
    audio_path: str
    reference_text: str
    hypothesis_text: str
    wer: float
    cer: float
    latency_ms: int


@dataclass
class STTEvalSummary:
    """Summary of STT evaluation run."""

    provider_name: str
    sample_count: int
    mean_wer: float
    mean_cer: float
    results: list[SampleEvalResult]
    report_md: str


async def prepare_wav_bytes(audio_path: Path) -> bytes:
    """Reads audio file and normalises to 16kHz mono WAV bytes.

    Falls back to raw bytes if ffmpeg cannot decode (e.g. mock test fixtures).
    """
    data = audio_path.read_bytes()
    try:
        return await to_wav16k(data)
    except Exception:
        return data


def load_reference_samples(samples_path: Path) -> dict[str, str]:
    """Loads sample reference texts keyed by sample ID from samples.yaml."""
    if not samples_path.is_file():
        return {}
    content = yaml.safe_load(samples_path.read_text(encoding="utf-8"))
    if not isinstance(content, dict) or "samples" not in content:
        return {}

    ref_map: dict[str, str] = {}
    for item in content["samples"]:
        if isinstance(item, dict) and "id" in item and "text_hi" in item:
            ref_map[str(item["id"])] = unicodedata.normalize("NFC", str(item["text_hi"]))
    return ref_map


def find_recorded_files(recorded_dir: Path) -> dict[str, Path]:
    """Finds all audio files matching <id>.(wav|ogg|m4a) in recorded_dir."""
    if not recorded_dir.is_dir():
        return {}

    valid_extensions = {".wav", ".ogg", ".m4a"}
    found: dict[str, Path] = {}
    for entry in sorted(recorded_dir.iterdir()):
        if entry.is_file() and entry.suffix.lower() in valid_extensions:
            sample_id = entry.stem
            # Do not overwrite if a preferred extension was already found
            if sample_id not in found:
                found[sample_id] = entry
    return found


async def run_stt_evaluation(
    samples_path: Path,
    recorded_dir: Path,
    report_path: Path,
    provider: STTProvider | None = None,
    provider_name: str | None = None,
) -> STTEvalSummary:
    """Runs STT evaluation on recorded samples and writes eval/stt/REPORT.md."""
    if provider is None:
        provider = get_stt_provider()
    if provider_name is None:
        provider_name = getattr(provider, "__class__", type(provider)).__name__

    ref_map = load_reference_samples(samples_path)
    recorded_map = find_recorded_files(recorded_dir)

    # Filter to recordings that have a reference transcript in samples.yaml
    active_samples = [
        (sample_id, recorded_map[sample_id], ref_map[sample_id])
        for sample_id in sorted(recorded_map.keys())
        if sample_id in ref_map
    ]

    now_iso = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")

    if not active_samples:
        report_md = f"""# STT Accuracy Report

- **Status**: No recordings yet
- **Provider**: {provider_name}
- **Samples evaluated (n)**: 0
- **Generated**: {now_iso}

> [!NOTE]
> Synthetic TTS audio is strictly never used as a stand-in for human speech in STT accuracy benchmarks.
> When human voice notes are placed in `eval/samples/recorded/<id>.(wav|ogg|m4a)`, run `make eval-stt` to evaluate WER and CER.
"""
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report_md, encoding="utf-8")
        return STTEvalSummary(
            provider_name=provider_name,
            sample_count=0,
            mean_wer=0.0,
            mean_cer=0.0,
            results=[],
            report_md=report_md,
        )

    results: list[SampleEvalResult] = []
    total_wer = 0.0
    total_cer = 0.0

    for sample_id, audio_file, ref_text in active_samples:
        wav_bytes = await prepare_wav_bytes(audio_file)
        transcript = await provider.transcribe(wav16k=wav_bytes, lang="hi-IN")
        hyp_text = unicodedata.normalize("NFC", transcript.text)

        wer = compute_wer(ref_text, hyp_text)
        cer = compute_cer(ref_text, hyp_text)

        total_wer += wer
        total_cer += cer

        results.append(
            SampleEvalResult(
                sample_id=sample_id,
                audio_path=str(audio_file.name),
                reference_text=ref_text,
                hypothesis_text=hyp_text,
                wer=wer,
                cer=cer,
                latency_ms=transcript.ms,
            )
        )

    n = len(results)
    mean_wer = total_wer / n if n > 0 else 0.0
    mean_cer = total_cer / n if n > 0 else 0.0

    table_rows: list[str] = []
    for r in results:
        table_rows.append(
            f"| `{r.sample_id}` | {r.reference_text} | {r.hypothesis_text or '*(empty)*'} | {r.wer * 100:.1f}% | {r.cer * 100:.1f}% | {r.latency_ms} ms |"
        )
    rows_str = "\n".join(table_rows)

    report_md = f"""# STT Accuracy Report

- **Status**: Completed
- **Provider**: {provider_name}
- **Samples evaluated (n)**: {n}
- **Mean WER**: {mean_wer * 100:.2f}%
- **Mean CER**: {mean_cer * 100:.2f}%
- **Generated**: {now_iso}

| Sample ID | Reference Transcript | Recognized Transcript | WER | CER | Latency |
|---|---|---|---|---|---|
{rows_str}
"""
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report_md, encoding="utf-8")

    return STTEvalSummary(
        provider_name=provider_name,
        sample_count=n,
        mean_wer=mean_wer,
        mean_cer=mean_cer,
        results=results,
        report_md=report_md,
    )


def main() -> None:
    """CLI entrypoint for STT accuracy evaluation."""
    parser = argparse.ArgumentParser(description="Evaluate STT accuracy on recorded samples.")
    parser.add_argument(
        "--samples-file",
        type=Path,
        default=Path("eval/samples/samples.yaml"),
        help="Path to evaluator samples YAML file",
    )
    parser.add_argument(
        "--recorded-dir",
        type=Path,
        default=Path("eval/samples/recorded"),
        help="Directory containing recorded audio files",
    )
    parser.add_argument(
        "--report-path",
        type=Path,
        default=Path("eval/stt/REPORT.md"),
        help="Path to output markdown report",
    )

    args = parser.parse_args()
    summary = asyncio.run(
        run_stt_evaluation(
            samples_path=args.samples_file,
            recorded_dir=args.recorded_dir,
            report_path=args.report_path,
        )
    )
    print(
        f"STT Evaluation complete: n={summary.sample_count}, "
        f"mean WER={summary.mean_wer * 100:.1f}%, mean CER={summary.mean_cer * 100:.1f}%"
    )


if __name__ == "__main__":
    main()
