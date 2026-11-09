"""Tests for Guide honest fallback on low confidence, model unavailable, and odd/out-of-scope questions (Job 02)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from backend.app.llm.client import LLMUnavailable
from backend.app.llm.roles.guide_answerer import answer_guide_question
from backend.app.llm.roles.question_classifier import classify_question
from backend.app.llm.schemas import (
    GuideAnswerResult,
    QuestionClassificationResult,
    RetrievedChunk,
)


@pytest.fixture
def sample_chunks() -> list[RetrievedChunk]:
    return [
        RetrievedChunk(
            chunk_id="chunk_fln_01",
            source_short_hi="गणित संदर्शिका",
            section="संख्या ज्ञान",
            page=22,
            text="कक्षा 1 और 2 में ठोस वस्तुओं और तीलियों के माध्यम से गिनती और जोड़ का अभ्यास कराएँ।",
        )
    ]


@pytest.mark.asyncio
async def test_guide_low_confidence_honest_message(sample_chunks: list[RetrievedChunk]) -> None:
    """When confidence is below 0.60, Guide returns an honest low-confidence message explaining this."""
    mock_low_conf = {
        "answer_hi": "ठोस वस्तुओं और तीलियों से शायद गिनती का अभ्यास हो सकता है।",
        "source_ids": ["chunk_fln_01"],
        "try_this_week_hi": "",
        "confidence": 0.42,  # Below settings.GUIDE_CONFIDENCE_THRESHOLD (0.60)
    }

    with patch("backend.app.llm.roles.guide_answerer.call_tool", new_callable=AsyncMock) as m_tool:
        m_tool.return_value = mock_low_conf
        result = await answer_guide_question(
            question="क्या बच्चे रात में बिना सोए गणित सीख सकते हैं?",
            category="pedagogy",
            chunks=sample_chunks,
            address_form="f",
        )

        assert isinstance(result, GuideAnswerResult)
        assert result.escalated is True
        assert result.low_confidence is True
        assert result.used_fallback is True
        # Honest message explicitly cites confidence/clarity threshold
        assert "सरकारी दस्तावेज़ों में पर्याप्त स्पष्टता नहीं है" in result.answer_text_hi
        assert "60% से कम" in result.answer_text_hi
        assert "ARP की समीक्षा-सूची" in result.answer_text_hi


@pytest.mark.asyncio
async def test_guide_model_unavailable_honest_message(sample_chunks: list[RetrievedChunk]) -> None:
    """When the LLM model is unavailable, Guide returns an honest message explaining model unavailability."""
    with patch("backend.app.llm.roles.guide_answerer.call_tool", new_callable=AsyncMock) as m_tool:
        m_tool.side_effect = LLMUnavailable("Anthropic API 503 Overloaded")
        result = await answer_guide_question(
            question="गिनती सिखाने के लिए क्या करें?",
            category="pedagogy",
            chunks=sample_chunks,
            address_form="f",
        )

        assert isinstance(result, GuideAnswerResult)
        assert result.escalated is True
        assert result.model_unavailable is True
        assert result.used_fallback is True
        # Honest message explains service unavailability rather than guessing
        assert "हैंडबुक गाइड सेवा उपलब्ध नहीं है" in result.answer_text_hi
        assert "ARP की समीक्षा-सूची" in result.answer_text_hi


@pytest.mark.asyncio
async def test_guide_out_of_scope_weather_and_personal() -> None:
    """Out-of-scope questions (weather, personal, political) return polite scope boundary rejection."""
    out_of_scope_questions = [
        "कल लखनऊ में बारिश होगी क्या?",
        "आपकी उम्र कितनी है?",
        "विधानसभा चुनाव में कौन जीतेगा?",
    ]

    for q in out_of_scope_questions:
        with patch("backend.app.llm.roles.guide_answerer.call_tool", new_callable=AsyncMock) as m_tool:
            result = await answer_guide_question(
                question=q,
                category="out_of_scope",
                chunks=[],
                address_form="f",
            )
            assert m_tool.call_count == 0
            assert result.escalated is False
            assert "माफ़ कीजिए, मैं कक्षा 1-3 की पढ़ाई और कक्षा से जुड़े सवालों में ही मदद कर सकती हूँ" in result.answer_text_hi


@pytest.mark.asyncio
async def test_question_classifier_out_of_scope_odd_question() -> None:
    """Question classifier routes non-classroom / odd queries to out_of_scope or returns fallback."""
    mock_out_of_scope = {
        "category": "out_of_scope",
        "needs_clarification": False,
        "clarifying_question_hi": "",
        "search_query_hi": "मौसम का हाल",
        "confidence": 0.95,
    }

    with patch("backend.app.llm.roles.question_classifier.call_tool", new_callable=AsyncMock) as m_tool:
        m_tool.return_value = mock_out_of_scope
        res = await classify_question("कल का तापमान क्या रहेगा?")
        assert isinstance(res, QuestionClassificationResult)
        assert res.output.category == "out_of_scope"
        assert res.output.confidence == 0.95


@pytest.mark.asyncio
async def test_guide_odd_pedagogy_no_matching_sources_escalates() -> None:
    """Odd pedagogical question with no relevant sources retrieved escalates cleanly."""
    odd_question = "कक्षा में जादू से बच्चों को पहाड़े कैसे सिखाएँ?"
    # No matching chunks
    with patch("backend.app.llm.roles.guide_answerer.call_tool", new_callable=AsyncMock) as m_tool:
        result = await answer_guide_question(
            question=odd_question,
            category="pedagogy",
            chunks=[],
            address_form="f",
        )
        assert m_tool.call_count == 0
        assert result.escalated is True
        assert result.no_sources is True
        assert "सरकारी दस्तावेज़ों में नहीं मिला" in result.answer_text_hi
        assert "ARP की समीक्षा-सूची" in result.answer_text_hi
