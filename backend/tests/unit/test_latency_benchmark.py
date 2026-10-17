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
    """generate_report produces markdown with tables and mock/live target verification."""
    from unittest.mock import patch

    from backend.app.config import settings

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

    # Case 1: Mock provider active -> NOT MEASURED (mock providers)
    with patch.object(settings, "LLM_PROVIDER", "mock"):
        mock_report = generate_report(measurements, target_ms=20_000)
        assert "# Latency Benchmark Report" in mock_report
        assert "NOT MEASURED (mock providers)" in mock_report
        assert "Per-Stage Latency Breakdown" in mock_report
        assert "estimate on mock payloads" in mock_report

    # Case 2: Real providers configured -> PASSED
    with (
        patch.object(settings, "LLM_PROVIDER", "anthropic"),
        patch.object(settings, "STT_PROVIDER", "sarvam"),
        patch.object(settings, "TTS_PROVIDER", "sarvam"),
        patch.object(settings, "ANTHROPIC_API_KEY", "sk-ant-test"),
        patch.object(settings, "SARVAM_API_KEY", "sarvam-test"),
    ):
        live_report = generate_report(measurements, target_ms=20_000)
        assert "**PASSED**" in live_report
        assert "Target Compliance (< 20s)" in live_report


def test_latency_report_file_exists() -> None:
    """eval/latency/REPORT.md must exist and record valid benchmark sections."""
    assert REPORT_PATH.is_file(), f"Missing latency report at {REPORT_PATH}"
    content = REPORT_PATH.read_text(encoding="utf-8")
    assert "# Latency Benchmark Report" in content
    assert "Latency by Concurrency" in content
    assert "Per-Stage Latency Breakdown" in content
    assert "< 20.0 s" in content
