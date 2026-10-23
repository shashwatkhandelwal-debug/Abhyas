"""Unit tests for guide_answerer role (spec/05 §5.8)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from backend.app.config import settings
from backend.app.llm.client import LLMUnavailable
from backend.app.llm.guards import guard_guide_answerer
from backend.app.llm.roles.guide_answerer import (
    answer_guide_question,
    compose_guide_reply,
    format_guide_citation,
)
from backend.app.llm.schemas import (
    GuideAnswererOutput,
    GuideAnswerResult,
    RetrievedChunk,
)


@pytest.fixture
def sample_chunks() -> list[RetrievedChunk]:
    return [
        RetrievedChunk(
            chunk_id="chunk_math_01",
            source_short_hi="गणित संदर्शिका",
            section="घटाव और स्थानीय मान",
            page=45,
            text="कक्षा 2 में 52 में से 17 घटाते समय बंडल तीली का प्रयोग करें। 10 तीलियों का एक बंडल खोलकर 12 तीलियाँ बनाएँ।",
        ),
        RetrievedChunk(
            chunk_id="chunk_math_02",
            source_short_hi="शिक्षक संदर्शिका",
            section="गतिविधि",
            page=46,
            text="कक्षा में 3 बच्चों के छोटे समूह बनाकर तीलियों का अभ्यास कराएँ।",
        ),
    ]


@pytest.mark.asyncio
async def test_answer_guide_question_success(sample_chunks: list[RetrievedChunk]) -> None:
    """Answers question using retrieved excerpts and includes source citation and tip."""
    mock_output = {
        "answer_hi": "घटाव सिखाते समय 10 तीलियों का एक बंडल खोलकर समझाएँ ताकि बच्चे स्थानीय मान समझ सकें।",
        "source_ids": ["chunk_math_01"],
        "try_this_week_hi": "कक्षा में बंडल खोलकर अभ्यास कराएँ।",
        "confidence": 0.95,
    }

    with patch("backend.app.llm.roles.guide_answerer.call_tool", new_callable=AsyncMock) as m_tool:
        m_tool.return_value = mock_output
        result = await answer_guide_question(
            question="घटाव कैसे सिखाएँ?",
            category="pedagogy",
            chunks=sample_chunks,
            address_form="f",
        )

        assert isinstance(result, GuideAnswerResult)
        assert result.escalated is False
        assert result.guarded is True
        assert len(result.sources_cited) == 1
        assert result.sources_cited[0].chunk_id == "chunk_math_01"
        assert "स्रोत: गणित संदर्शिका, पृष्ठ 45" in result.answer_text_hi
        assert "इस हफ्ते आज़माएँ" in result.answer_text_hi


@pytest.mark.asyncio
async def test_answer_guide_question_out_of_scope(sample_chunks: list[RetrievedChunk]) -> None:
    """Out of scope questions return polite canned rejection without calling LLM."""
    with patch("backend.app.llm.roles.guide_answerer.call_tool", new_callable=AsyncMock) as m_tool:
        result = await answer_guide_question(
            question="कल बारिश होगी क्या?",
            category="out_of_scope",
            chunks=sample_chunks,
            address_form="f",
        )

        assert m_tool.call_count == 0
        assert result.escalated is False
        assert "माफ़ कीजिए" in result.answer_text_hi


@pytest.mark.asyncio
async def test_answer_guide_question_admin_routing(sample_chunks: list[RetrievedChunk]) -> None:
    """Admin questions return canned direction to BEO/ARP and escalate to ARP."""
    with patch("backend.app.llm.roles.guide_answerer.call_tool", new_callable=AsyncMock) as m_tool:
        result = await answer_guide_question(
            question="छुट्टी का फॉर्म कहाँ जमा करें?",
            category="admin",
            chunks=sample_chunks,
            address_form="f",
        )

        assert m_tool.call_count == 0
        assert result.escalated is True
        assert "BEO या ARP कार्यालय" in result.answer_text_hi


@pytest.mark.asyncio
async def test_answer_guide_question_empty_chunks_escalates() -> None:
    """Empty chunks escalate immediately to ask_escalated message."""
    with patch("backend.app.llm.roles.guide_answerer.call_tool", new_callable=AsyncMock) as m_tool:
        result = await answer_guide_question(
            question="कोई नया सवाल",
            category="pedagogy",
            chunks=[],
            address_form="f",
        )

        assert m_tool.call_count == 0
        assert result.escalated is True
        assert result.used_fallback is True
        assert "ARP की समीक्षा-सूची" in result.answer_text_hi


@pytest.mark.asyncio
async def test_answer_guide_question_low_retrieval_score_escalates() -> None:
    """If all retrieved chunks have scores below RETRIEVAL_MIN_SCORE, escalate immediately without calling LLM."""
    low_score_chunks = [
        RetrievedChunk(
            chunk_id="chunk_low_01",
            source_short_hi="गणित संदर्शिका",
            section="संख्या ज्ञान",
            page=12,
            text="कुछ जानकारी",
            score=settings.RETRIEVAL_MIN_SCORE / 2,  # below RETRIEVAL_MIN_SCORE
        ),
        RetrievedChunk(
            chunk_id="chunk_low_02",
            source_short_hi="गणित संदर्शिका",
            section="संख्या ज्ञान",
            page=13,
            text="अन्य जानकारी",
            score=settings.RETRIEVAL_MIN_SCORE * 0.9,  # below RETRIEVAL_MIN_SCORE
        ),
    ]

    with patch("backend.app.llm.roles.guide_answerer.call_tool", new_callable=AsyncMock) as m_tool:
        result = await answer_guide_question(
            question="कठिन सवाल?",
            category="pedagogy",
            chunks=low_score_chunks,
            address_form="f",
        )

        assert m_tool.call_count == 0
        assert result.escalated is True
        assert result.used_fallback is True
        assert "ARP की समीक्षा-सूची" in result.answer_text_hi


@pytest.mark.asyncio
async def test_answer_guide_question_low_confidence_escalates(
    sample_chunks: list[RetrievedChunk],
) -> None:
    """Confidence below threshold (< 0.6) escalates answer to ARP."""
    mock_output = {
        "answer_hi": "मार्गदर्शिका में इस प्रश्न का स्पष्ट उत्तर नहीं है।",
        "source_ids": ["chunk_math_01"],
        "try_this_week_hi": "",
        "confidence": 0.35,  # Below 0.60
    }

    with patch("backend.app.llm.roles.guide_answerer.call_tool", new_callable=AsyncMock) as m_tool:
        m_tool.return_value = mock_output
        result = await answer_guide_question(
            question="कक्षा 2 में त्रिकोणमिति कैसे पढ़ाएँ?",
            category="pedagogy",
            chunks=sample_chunks,
            address_form="f",
        )

        assert result.escalated is True
        assert "ARP की समीक्षा-सूची" in result.answer_text_hi


@pytest.mark.asyncio
async def test_answer_guide_question_retry_on_unauthorized_number(
    sample_chunks: list[RetrievedChunk],
) -> None:
    """Number not in source excerpt fails guard and triggers retry."""
    invalid_out = {
        "answer_hi": "कक्षा में 99 तीलियाँ लेकर समझाएँ।",  # 99 not in excerpts
        "source_ids": ["chunk_math_01"],
        "try_this_week_hi": "",
        "confidence": 0.9,
    }
    valid_out = {
        "answer_hi": "कक्षा में 10 तीलियों का बंडल खोलकर समझाएँ।",  # 10 is in excerpts
        "source_ids": ["chunk_math_01"],
        "try_this_week_hi": "तीलियों का उपयोग करें।",
        "confidence": 0.9,
    }

    with patch("backend.app.llm.roles.guide_answerer.call_tool", new_callable=AsyncMock) as m_tool:
        m_tool.side_effect = [invalid_out, valid_out]
        result = await answer_guide_question(
            question="तीलियाँ कैसे उपयोग करें?",
            category="pedagogy",
            chunks=sample_chunks,
            address_form="f",
        )

        assert m_tool.call_count == 2
        assert result.escalated is False
        assert result.guarded is True


@pytest.mark.asyncio
async def test_answer_guide_question_llm_unavailable_escalates(
    sample_chunks: list[RetrievedChunk],
) -> None:
    """LLMUnavailable escalates safely to ARP without retry."""
    with patch("backend.app.llm.roles.guide_answerer.call_tool", new_callable=AsyncMock) as m_tool:
        m_tool.side_effect = LLMUnavailable("API down")
        result = await answer_guide_question(
            question="जोड़ कैसे सिखाएँ?",
            category="pedagogy",
            chunks=sample_chunks,
            address_form="f",
        )

        assert m_tool.call_count == 1
        assert result.escalated is True
        assert result.used_fallback is True
        assert "ARP की समीक्षा-सूची" in result.answer_text_hi


def test_compose_guide_reply_deduplicates_sources(sample_chunks: list[RetrievedChunk]) -> None:
    """compose_guide_reply formats answer and deduplicates same source citations."""
    out = GuideAnswererOutput(
        answer_hi="मुख्य उत्तर यहाँ है।",
        source_ids=["chunk_math_01", "chunk_math_02"],
        try_this_week_hi="एक छोटी गतिविधि आज़माएँ।",
        confidence=0.95,
    )
    reply = compose_guide_reply(out, sample_chunks, address_form="m")
    assert "मुख्य उत्तर यहाँ है।" in reply
    assert "स्रोत: गणित संदर्शिका, पृष्ठ 45" in reply
    assert "स्रोत: शिक्षक संदर्शिका, पृष्ठ 46" in reply
    assert "इस हफ्ते आज़माएँ: एक छोटी गतिविधि आज़माएँ।" in reply


def test_guide_answerer_goldens() -> None:
    """Verifies all golden fixtures in backend/tests/golden/guide_answerer/ are valid."""
    golden_dir = Path(__file__).parents[1] / "golden" / "guide_answerer"
    files = list(golden_dir.glob("*.json"))
    assert len(files) >= 5, f"Expected >= 5 golden fixtures, found {len(files)}"

    for f in files:
        data = json.loads(f.read_text(encoding="utf-8"))
        assert data["role"] == "guide_answerer"
        out = GuideAnswererOutput.model_validate(data["output"])
        chunks = [RetrievedChunk.model_validate(c) for c in data["input"]["chunks"]]
        is_valid, msg = guard_guide_answerer(out, retrieved_chunks=chunks)
        assert is_valid is True, f"Golden fixture {f.name} failed guard: {msg}"


def test_format_guide_citation_standard() -> None:
    """format_guide_citation formats bracketed citation with Hindi page abbreviation."""
    cit = format_guide_citation("गणित संदर्शिका", 45)
    assert cit == "स्रोत: गणित संदर्शिका, पृष्ठ 45"


def test_format_guide_citation_no_page() -> None:
    """format_guide_citation formats source-only citation when page is None."""
    cit = format_guide_citation("निपुण दिशानिर्देश", None)
    assert cit == "[निपुण दिशानिर्देश]"


def test_format_guide_citation_raises_on_missing_catalog_key() -> None:
    """format_guide_citation raises KeyError when catalog key is missing."""
    with patch(
        "backend.app.llm.roles.guide_answerer.load_catalog_message",
        side_effect=KeyError("ask_source_citation"),
    ):
        with pytest.raises(KeyError):
            format_guide_citation("गणित संदर्शिका", 45)


def test_compose_guide_reply_calls_format_guide_citation(
    sample_chunks: list[RetrievedChunk],
) -> None:
    """compose_guide_reply invokes format_guide_citation and includes citation in reply text."""
    out = GuideAnswererOutput(
        answer_hi="मुख्य उत्तर।",
        source_ids=["chunk_math_01"],
        try_this_week_hi="एक छोटी गतिविधि।",
        confidence=0.9,
    )
    with patch(
        "backend.app.llm.roles.guide_answerer.format_guide_citation",
        wraps=format_guide_citation,
    ) as m_cit:
        reply = compose_guide_reply(out, sample_chunks, address_form="f")
        assert m_cit.call_count == 1
        assert "मुख्य उत्तर।" in reply
        assert "स्रोत: गणित संदर्शिका, पृष्ठ 45" in reply
