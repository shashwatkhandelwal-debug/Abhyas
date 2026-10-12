"""Unit tests for question_classifier role (spec/05 §5.8)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from backend.app.llm.client import LLMUnavailable
from backend.app.llm.guards import guard_question_classifier
from backend.app.llm.roles.question_classifier import classify_question
from backend.app.llm.schemas import (
    QuestionClassificationResult,
    QuestionClassifierOutput,
)


@pytest.mark.asyncio
async def test_classify_question_pedagogy_success() -> None:
    """Classifies a pedagogy question into pedagogy with valid search query."""
    mock_output = {
        "tool_name": "question_classifier",
        "input": {
            "category": "pedagogy",
            "needs_clarification": False,
            "clarifying_question_hi": "",
            "search_query_hi": "हासिल वाले जोड़ की गतिविधि",
            "confidence": 0.95,
        },
    }

    with patch(
        "backend.app.llm.roles.question_classifier.call_tool", new_callable=AsyncMock
    ) as m_tool:
        m_tool.return_value = mock_output
        result = await classify_question("कक्षा 2 में हासिल वाले जोड़ के लिए कौन सी गतिविधि कराएँ?")

        assert isinstance(result, QuestionClassificationResult)
        assert result.guarded is True
        assert result.used_fallback is False
        assert result.output.category == "pedagogy"
        assert result.output.search_query_hi == "हासिल वाले जोड़ की गतिविधि"
        assert result.output.confidence == 0.95


@pytest.mark.asyncio
async def test_classify_question_needs_clarification() -> None:
    """Ambiguous question triggers needs_clarification with respectful clarifying question."""
    mock_output = {
        "tool_name": "question_classifier",
        "input": {
            "category": "classroom_management",
            "needs_clarification": True,
            "clarifying_question_hi": "क्या आप बता सकती हैं कि बच्चे किस विषय में ध्यान नहीं देते?",
            "search_query_hi": "",
            "confidence": 0.88,
        },
    }

    with patch(
        "backend.app.llm.roles.question_classifier.call_tool", new_callable=AsyncMock
    ) as m_tool:
        m_tool.return_value = mock_output
        result = await classify_question("बच्चे ध्यान नहीं देते।")

        assert result.output.needs_clarification is True
        assert "आप" in result.output.clarifying_question_hi
        assert result.used_fallback is False


@pytest.mark.asyncio
async def test_classify_question_empty_input_fallback() -> None:
    """Empty question string triggers immediate clarification fallback without calling LLM."""
    with patch(
        "backend.app.llm.roles.question_classifier.call_tool", new_callable=AsyncMock
    ) as m_tool:
        result = await classify_question("   ")

        assert m_tool.call_count == 0
        assert result.output.needs_clarification is True
        assert result.used_fallback is True


@pytest.mark.asyncio
async def test_classify_question_retry_on_guard_failure() -> None:
    """Retries once if initial output fails guard (e.g. disrespectful register in clarifying question)."""
    invalid_out = {
        "tool_name": "question_classifier",
        "input": {
            "category": "classroom_management",
            "needs_clarification": True,
            "clarifying_question_hi": "तुम बताओ कि बच्चे क्यों नहीं पढ़ते?",  # Disrespectful तुम
            "search_query_hi": "",
            "confidence": 0.9,
        },
    }
    valid_out = {
        "tool_name": "question_classifier",
        "input": {
            "category": "classroom_management",
            "needs_clarification": True,
            "clarifying_question_hi": "आप बता सकती हैं कि समस्या कब आती है?",
            "search_query_hi": "",
            "confidence": 0.9,
        },
    }

    with patch(
        "backend.app.llm.roles.question_classifier.call_tool", new_callable=AsyncMock
    ) as m_tool:
        m_tool.side_effect = [invalid_out, valid_out]
        result = await classify_question("बच्चे पढ़ते नहीं हैं")

        assert m_tool.call_count == 2
        assert result.guarded is True
        assert result.used_fallback is False
        assert result.output.clarifying_question_hi == "आप बता सकती हैं कि समस्या कब आती है?"


@pytest.mark.asyncio
async def test_classify_question_deterministic_fallback_on_llm_unavailable() -> None:
    """Falls back to deterministic classification if LLM is unavailable."""
    with patch(
        "backend.app.llm.roles.question_classifier.call_tool", new_callable=AsyncMock
    ) as m_tool:
        m_tool.side_effect = LLMUnavailable("API error")
        result = await classify_question("कक्षा में तीलियों का उपयोग कैसे करें?")

        assert result.used_fallback is True
        assert result.output.category == "pedagogy"
        assert result.output.search_query_hi == "कक्षा में तीलियों का उपयोग कैसे करें?"
        assert result.output.confidence == 0.0


def test_question_classifier_goldens() -> None:
    """Verifies all golden fixtures in backend/tests/golden/question_classifier/ are valid."""
    golden_dir = Path(__file__).parents[1] / "golden" / "question_classifier"
    files = list(golden_dir.glob("*.json"))
    assert len(files) >= 5, f"Expected >= 5 golden fixtures, found {len(files)}"

    for f in files:
        data = json.loads(f.read_text(encoding="utf-8"))
        assert data["role"] == "question_classifier"
        out = QuestionClassifierOutput.model_validate(data["output"])
        is_valid, msg = guard_question_classifier(out)
        assert is_valid is True, f"Golden fixture {f.name} failed guard: {msg}"
