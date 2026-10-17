"""Unit tests for latency benchmark harness and report generation (spec/11 §11.3, T41)."""

from __future__ import annotations

from pathlib import Path

from eval.latency.benchmark_latency import (
    TurnMeasurement,
    generate_report,
    percentile,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
REPORT_PATH = REPO_ROOT / "eval" / "latency" / "REPORT.md"


def test_percentile_calculation() -> None:
    """Verifies statistical percentile computation."""
    data = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0]
    assert percentile(data, 0.50) == 50.0
    assert percentile(data, 0.95) == 100.0
    assert percentile([], 0.95) == 0.0


def test_generate_report_format_and_thresholds() -> None:
    """generate_report produces markdown with tables and target verification."""
    measurements = [
        TurnMeasurement(
            sample_id="s1_ask_ravi",
            concurrency=1,
            total_ms=45.0,
            stage_ms={"stt": 10.0, "engine": 2.0, "tts": 15.0},
            guard_fallback=False,
            bytes_up=1000,
            bytes_down=2000,
        ),
        TurnMeasurement(
            sample_id="s2_bundles_all",
            concurrency=3,
            total_ms=55.0,
            stage_ms={"stt": 12.0, "engine": 2.0, "tts": 18.0},
            guard_fallback=False,
            bytes_up=1200,
            bytes_down=2200,
        ),
    ]

    report = generate_report(measurements, target_ms=20_000)
    assert "# Latency Benchmark Report" in report
    assert "Voice-in → voice-out latency p95 < 20.0 s" in report
    assert "**PASSED**" in report
    assert "Per-Stage Latency Breakdown" in report
    assert "On-Device Low-Network Data Transfer Budget" in report
    assert "Architectural Latency Optimisations Implemented" in report


def test_latency_report_file_exists_and_passes_target() -> None:
    """eval/latency/REPORT.md must exist and record PASSED status."""
    assert REPORT_PATH.is_file(), f"Missing latency report at {REPORT_PATH}"
    content = REPORT_PATH.read_text(encoding="utf-8")
    assert "**PASSED**" in content
    assert "Latency by Concurrency" in content
    assert "Per-Stage Latency Breakdown" in content
    assert "< 20.0 s" in content
