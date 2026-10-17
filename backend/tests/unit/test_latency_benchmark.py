"""Unit tests for latency benchmark harness and report generation (spec/11 §11.3, T41)."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

from backend.app.config import settings
from eval.latency.benchmark_latency import (
    TurnMeasurement,
    async_main,
    generate_report,
    get_effective_provider,
    measure_http_turn,
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


def test_get_effective_provider() -> None:
    """Verifies effective runtime provider detection (Follow-up a)."""
    # 1. Unset keys -> mock with descriptive reason
    with (
        patch.object(settings, "LLM_PROVIDER", "anthropic"),
        patch.object(settings, "STT_PROVIDER", "sarvam"),
        patch.object(settings, "TTS_PROVIDER", "sarvam"),
        patch.object(settings, "ANTHROPIC_API_KEY", None),
        patch.object(settings, "SARVAM_API_KEY", None),
    ):
        assert get_effective_provider("llm") == "mock (no ANTHROPIC_API_KEY)"
        assert get_effective_provider("stt") == "mock (no SARVAM_API_KEY)"
        assert get_effective_provider("tts") == "mock (no SARVAM_API_KEY)"

    # 2. Configured as mock directly
    with patch.object(settings, "LLM_PROVIDER", "mock"):
        assert get_effective_provider("llm") == "mock (mock)"

    # 3. Live keys configured
    with (
        patch.object(settings, "LLM_PROVIDER", "anthropic"),
        patch.object(settings, "STT_PROVIDER", "sarvam"),
        patch.object(settings, "TTS_PROVIDER", "sarvam"),
        patch.object(settings, "ANTHROPIC_API_KEY", "sk-ant-test"),
        patch.object(settings, "SARVAM_API_KEY", "sarvam-test"),
    ):
        assert "anthropic" in get_effective_provider("llm")
        assert "sarvam" in get_effective_provider("stt")
        assert "sarvam" in get_effective_provider("tts")


def test_generate_report_format_and_thresholds() -> None:
    """generate_report produces markdown with tables, effective provider headers, and unit formatting."""
    measurements = [
        TurnMeasurement(
            sample_id="s1_ask_ravi",
            concurrency=1,
            total_ms=45.0,
            stage_ms={"stt": 10.0, "engine": 2.0, "tts": 15.0},
            guard_fallback=False,
            bytes_up=1000,
            bytes_down=2000,
            ok=True,
        ),
        TurnMeasurement(
            sample_id="s2_bundles_all",
            concurrency=3,
            total_ms=55.0,
            stage_ms={"stt": 12.0, "engine": 2.0, "tts": 18.0},
            guard_fallback=False,
            bytes_up=1200,
            bytes_down=2200,
            ok=True,
        ),
    ]

    # Case 1: Mock provider active -> NOT MEASURED (mock providers), KB formatting (Follow-up c)
    with (
        patch.object(settings, "LLM_PROVIDER", "anthropic"),
        patch.object(settings, "ANTHROPIC_API_KEY", None),
        patch.object(settings, "SARVAM_API_KEY", None),
    ):
        mock_report = generate_report(measurements, target_ms=20_000)
        assert "# Latency Benchmark Report" in mock_report
        assert "NOT MEASURED (mock providers)" in mock_report
        assert "LLM Provider (effective):" in mock_report
        assert "mock (no ANTHROPIC_API_KEY)" in mock_report
        assert "Per-Stage Latency Breakdown" in mock_report
        assert "estimate on mock payloads" in mock_report
        # Assert follow-up c: does NOT display "0.00 MB"
        assert "0.00 MB" not in mock_report
        assert "2/2 completed" in mock_report

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

    # Case 3: Hosted HTTP deployment target display
    with patch.object(settings, "LLM_PROVIDER", "mock"):
        http_report = generate_report(
            measurements, target_ms=20_000, base_url="https://abhyas-demo.onrender.com"
        )
        assert "Hosted HTTP Deployment (`https://abhyas-demo.onrender.com`)" in http_report


@pytest.mark.asyncio
async def test_measure_http_turn_mock() -> None:
    """Verifies that measure_http_turn posts audio, polls messages, and calculates metrics."""
    poll_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal poll_count
        if request.url.path == "/api/chat/audio":
            return httpx.Response(202, json={"message_id": "test-msg-123", "status": "accepted"})
        elif request.url.path == "/api/chat/messages":
            poll_count += 1
            if poll_count == 1:
                return httpx.Response(200, json={"pending": True, "messages": []})
            return httpx.Response(
                200,
                json={
                    "pending": False,
                    "messages": [
                        {
                            "id": "out-1",
                            "direction": "out",
                            "text": "नमस्ते",
                            "audio_ref": "audio-test-1",
                        }
                    ],
                },
            )
        elif request.url.path == "/api/audio/audio-test-1.wav":
            return httpx.Response(200, content=b"RIFF\x00\x00\x00\x00WAVE")
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        meas = await measure_http_turn(
            client=client,
            csrf_token="test-csrf",
            sample_id="s1_ask_ravi",
            audio_bytes=b"RIFF1234WAVE",
            concurrency=1,
            timeout_s=5.0,
        )
        assert meas.sample_id == "s1_ask_ravi"
        assert meas.concurrency == 1
        assert meas.total_ms > 0
        assert meas.ok is True
        assert "post_audio" in meas.stage_ms
        assert "polling_roundtrip" in meas.stage_ms
        assert "audio_download" in meas.stage_ms
        assert meas.bytes_up == len(b"RIFF1234WAVE")
        assert meas.bytes_down > 0


@pytest.mark.asyncio
async def test_measure_http_turn_timeout_and_p95_exclusion() -> None:
    """Verifies that timeouts set ok=False and are excluded from p95 calculations (Blocker 2)."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/chat/audio":
            return httpx.Response(
                202, json={"message_id": "test-msg-timeout", "status": "accepted"}
            )
        elif request.url.path == "/api/chat/messages":
            # Never ready: always pending=True, no messages
            return httpx.Response(200, json={"pending": True, "messages": []})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        meas = await measure_http_turn(
            client=client,
            csrf_token="test-csrf",
            sample_id="s1_ask_ravi",
            audio_bytes=b"RIFF1234WAVE",
            concurrency=1,
            timeout_s=0.1,  # fast timeout
        )
        assert meas.ok is False
        assert meas.error_msg is not None
        assert "timed out" in meas.error_msg.lower()

    # Verify that a failed turn is excluded from p95 and marks the report FAILED
    good_turn = TurnMeasurement(
        sample_id="s1_ask_ravi",
        concurrency=1,
        total_ms=50.0,
        stage_ms={"stt": 10.0},
        ok=True,
    )
    failed_turn = TurnMeasurement(
        sample_id="s2_bundles_all",
        concurrency=1,
        total_ms=30000.0,  # 30 seconds timeout
        stage_ms={"stt": 10.0},
        ok=False,
        error_msg="timed out",
    )

    report = generate_report([good_turn, failed_turn], target_ms=20_000)
    # The failed 30s turn MUST NOT inflate the p95 to 30.00 s
    assert "30.00 s" not in report
    # Completed turns reported as 1/2
    assert "1/2 completed" in report
    # Marked FAILED because of turn failure
    assert "FAILED" in report


def test_url_mode_missing_wav_exits_nonzero(monkeypatch: pytest.MonkeyPatch) -> None:
    """In --url mode, missing or silent WAVs must exit non-zero with 'make samples' instruction (Blocker 1)."""
    monkeypatch.setattr(
        sys,
        "argv",
        ["benchmark_latency.py", "--url", "http://testserver", "--turns", "1"],
    )

    with pytest.raises(SystemExit) as exc_info:
        asyncio.run(async_main())

    assert exc_info.value.code != 0


def test_latency_report_file_exists() -> None:
    """eval/latency/REPORT.md must exist and record valid benchmark sections."""
    assert REPORT_PATH.is_file(), f"Missing latency report at {REPORT_PATH}"
    content = REPORT_PATH.read_text(encoding="utf-8")
    assert "# Latency Benchmark Report" in content
    assert "Latency by Concurrency" in content
    assert "Per-Stage Latency Breakdown" in content
    assert "< 20.0 s" in content
