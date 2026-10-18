"""Unit tests for cost report calculations and formatting (T61, spec/11)."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.config import settings
from backend.app.db.models import LLMCall, SpeechSpend
from eval.cost.cost_report import (
    compute_llm_call_cost_usd,
    format_markdown_report,
    generate_cost_metrics,
)


def test_compute_llm_call_cost_haiku() -> None:
    """Verifies Haiku 5.5 cost calculation per MTok."""
    cost = compute_llm_call_cost_usd(
        model="claude-haiku-5-5",
        input_tokens=1_000_000,
        output_tokens=1_000_000,
        cache_read_tokens=1_000_000,
    )
    assert round(cost, 4) == round(0.10 + 0.50 + 0.01, 4)


def test_compute_llm_call_cost_sonnet() -> None:
    """Verifies Sonnet 5.5 cost calculation per MTok."""
    cost = compute_llm_call_cost_usd(
        model="claude-sonnet-5-5",
        input_tokens=1_000_000,
        output_tokens=1_000_000,
        cache_read_tokens=1_000_000,
    )
    assert round(cost, 4) == round(2.00 + 10.00 + 0.10, 4)


@pytest.mark.asyncio
async def test_generate_cost_metrics_calculation() -> None:
    """Verifies end-to-end metrics calculation on fixture data."""
    mock_session = AsyncMock(spec=AsyncSession)

    # 1. Scalar calls: n_teachers=2, n_completed_loops=1
    mock_session.scalar.side_effect = [2, 1]

    now = datetime(2026, 10, 15, 10, 0, 0, tzinfo=UTC)

    # 2. LLM calls: 1 Haiku call, 1 Sonnet call, 1 Mock call
    llm_rows = [
        LLMCall(
            role="child_voice",
            model="claude-haiku-5-5",
            input_tokens=1000,
            output_tokens=100,
            cache_read_tokens=500,
            created_at=now,
        ),
        LLMCall(
            role="coach",
            model="claude-sonnet-5-5",
            input_tokens=2000,
            output_tokens=300,
            cache_read_tokens=1000,
            created_at=now,
        ),
        LLMCall(
            role="mock",
            model="mock",
            input_tokens=100,
            output_tokens=50,
            cache_read_tokens=0,
            created_at=now,
        ),
    ]

    # 3. Speech spend: 1 STT (Sarvam), 1 TTS (Sarvam), 1 Mock
    speech_rows = [
        SpeechSpend(
            at=now,
            provider="sarvam",
            kind="stt",
            units=60,
            cost_inr=0.50,
        ),
        SpeechSpend(
            at=now,
            provider="sarvam",
            kind="tts",
            units=1000,
            cost_inr=3.00,
        ),
        SpeechSpend(
            at=now,
            provider="mock",
            kind="stt",
            units=30,
            cost_inr=0.00,
        ),
    ]

    scalars_mock_llm = MagicMock()
    scalars_mock_llm.all.return_value = llm_rows

    scalars_mock_speech = MagicMock()
    scalars_mock_speech.all.return_value = speech_rows

    mock_session.scalars.side_effect = [scalars_mock_llm, scalars_mock_speech]

    # Compute metrics (exclude mock, hosted label)
    metrics = await generate_cost_metrics(
        mock_session, include_mock=False, force_env_label="hosted"
    )

    assert metrics.environment_label == "hosted"
    assert metrics.n_teachers == 2
    assert metrics.n_completed_loops == 1
    assert metrics.n_llm_calls == 2  # mock excluded
    assert metrics.n_speech_records == 2  # mock excluded

    expected_usd = 0.000155 + 0.0071
    expected_llm_inr = expected_usd * settings.USD_TO_INR
    expected_speech_inr = 3.50
    expected_total_inr = expected_llm_inr + expected_speech_inr

    assert abs(metrics.llm_cost_usd - expected_usd) < 1e-4
    assert abs(metrics.llm_cost_inr - expected_llm_inr) < 0.05
    assert metrics.speech_cost_inr == 3.50
    assert abs(metrics.total_cost_inr - expected_total_inr) < 0.05

    # Per teacher & per loop
    assert abs(metrics.cost_per_teacher_inr - (expected_total_inr / 2.0)) < 0.05
    assert abs(metrics.cost_per_completed_loop_inr - expected_total_inr) < 0.05

    # Verify Markdown format
    report_md = format_markdown_report(metrics)
    assert "# Abhyas Cost Report (hosted)" in report_md
    assert "₹3.50" in report_md
    assert "Cost per Teacher" in report_md
    assert "Cost per Completed Weekly Loop (DONE)" in report_md
    assert "claude-haiku-5-5" in report_md
    assert "claude-sonnet-5-5" in report_md
    assert "sarvam" in report_md
    assert "https://platform.claude.com/docs/en/about-claude/pricing" in report_md
    assert "https://docs.sarvam.ai/api-reference-docs/pricing" in report_md


@pytest.mark.asyncio
async def test_generate_cost_metrics_mock_mode() -> None:
    """Verifies mock mode includes mock rows and sets local/mock label."""
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.scalar.side_effect = [1, 0]

    now = datetime(2026, 10, 16, 12, 0, 0, tzinfo=UTC)
    llm_rows = [
        LLMCall(
            role="mock",
            model="mock",
            input_tokens=50,
            output_tokens=20,
            cache_read_tokens=0,
            created_at=now,
        )
    ]
    scalars_mock_llm = MagicMock()
    scalars_mock_llm.all.return_value = llm_rows

    scalars_mock_speech = MagicMock()
    scalars_mock_speech.all.return_value = []

    mock_session.scalars.side_effect = [scalars_mock_llm, scalars_mock_speech]

    metrics = await generate_cost_metrics(mock_session, include_mock=True)
    assert metrics.environment_label == "local/mock"
    assert metrics.n_llm_calls == 1
    report_md = format_markdown_report(metrics)
    assert "# Abhyas Cost Report (local/mock)" in report_md
