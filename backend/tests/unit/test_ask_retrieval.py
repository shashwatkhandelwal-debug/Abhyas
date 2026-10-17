"""Unit tests for BM25 retrieval and full ASK conversation flow (spec/08 §8.3-8.4, spec/10 §10.4, T22)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from backend.app.core.messages import get_message
from backend.app.core.types import InboundMessage
from backend.app.llm.schemas import (
    GuideAnswererOutput,
    GuideAnswerResult,
    QuestionClassificationResult,
    QuestionClassifierOutput,
)
from backend.app.retrieval.search import GuideRetriever, tokenize_hindi
from backend.app.sessions.service import SessionService
from backend.app.sessions.state_machine import OnboardingStateEnum, SessionStateEnum
from backend.tests.unit.test_state_machine import FakeSessionRepository


def make_inbound(
    teacher_id: Any,
    text: str | None = None,
    button_id: str | None = None,
) -> InboundMessage:
    return InboundMessage(
        channel="whatsapp",
        channel_msg_id=f"msg-{uuid4().hex[:8]}",
        teacher_id=teacher_id,
        kind="button" if button_id else "text",
        text=text,
        button_id=button_id,
        received_at=datetime.now(UTC),
    )


# ── 1. BM25 Retrieval Tests ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tokenize_hindi_unicode_punctuation() -> None:
    """Verifies that Hindi tokenizer preserves matras and splits on whitespace/punctuation."""
    tokens = tokenize_hindi("हासिल वाला घटाव, बंडल खोलकर! 43-27?")
    assert "हासिल" in tokens
    assert "घटाव" in tokens
    assert "बंडल" in tokens
    assert "खोलकर" in tokens
    assert "43" in tokens
    assert "27" in tokens


@pytest.mark.asyncio
async def test_bm25_retrieval_subtraction_query() -> None:
    """Tests BM25 retrieval returns relevant subtraction chunks."""
    retriever = GuideRetriever()
    results = await retriever.retrieve("हासिल वाला घटाव बंडल खोलकर", top_k=3)

    assert len(results) > 0
    top_chunk = results[0]
    assert top_chunk.similarity_score > 0
    assert top_chunk.source_short_hi == "अभ्यास मूव सारांश"
    # Either chunk ID is from NUM_SUB_REGROUP_BUNDLES or move_id is
    sub_chunks = [
        c for c in results if c.move_id == "NUM_SUB_REGROUP_BUNDLES" or "NUM_SUB" in c.chunk_id
    ]
    assert len(sub_chunks) >= 1
    assert "घटाव" in top_chunk.text or "बंडल" in top_chunk.text


@pytest.mark.asyncio
async def test_bm25_retrieval_subtraction_regrouping_realistic_teacher_query() -> None:
    """Verifies a realistic teacher query about subtraction regrouping / borrowing
    matches NUM_SUB_REGROUP_BUNDLES chunks with positive BM25 similarity score."""
    retriever = GuideRetriever()
    query = "जब बच्चे 43 में से 27 घटाते समय हासिल में अटकें तो बंडल खोलना कैसे समझाएं?"
    results = await retriever.retrieve(query, top_k=3)

    assert len(results) > 0
    assert any(c.move_id == "NUM_SUB_REGROUP_BUNDLES" for c in results)
    sub_chunk = next(c for c in results if c.move_id == "NUM_SUB_REGROUP_BUNDLES")
    assert sub_chunk.similarity_score > 0
    assert sub_chunk.source_short_hi == "अभ्यास मूव सारांश"
    assert "घटाव" in sub_chunk.section or "घटाव" in sub_chunk.text or "बंडल" in sub_chunk.text


@pytest.mark.asyncio
async def test_bm25_retrieval_place_value_query() -> None:
    """Tests BM25 retrieval returns relevant place value chunks."""
    retriever = GuideRetriever()
    results = await retriever.retrieve("स्थानीय मान बंडल और खुली तीलियाँ", top_k=3)

    assert len(results) > 0
    top_chunk = results[0]
    assert top_chunk.similarity_score > 0
    pv_chunks = [
        c for c in results if c.move_id == "NUM_PLACE_VALUE_BUNDLES" or "PLACE_VALUE" in c.chunk_id
    ]
    assert len(pv_chunks) >= 1
    assert "स्थानीय" in top_chunk.text or "दहाई" in top_chunk.text or "बंडल" in top_chunk.text


@pytest.mark.asyncio
async def test_bm25_retrieval_empty_or_unrelated_query() -> None:
    """Tests BM25 retrieval handles whitespace or zero-overlap queries cleanly."""
    retriever = GuideRetriever()
    empty_results = await retriever.retrieve("   ", top_k=3)
    assert empty_results == []

    unrelated_results = await retriever.retrieve("अंतरिक्ष रॉकेट प्रक्षेपण केंद्र", top_k=3)
    assert unrelated_results == []


# ── 2. Full ASK Flow in SessionService Tests ──────────────────────────────────


@pytest.mark.asyncio
async def test_ask_flow_pedagogy_answered_and_resumed() -> None:
    """Tests pedagogy question during rehearsal: classified, retrieved, answered, and resumes state."""
    repo = FakeSessionRepository()
    service = SessionService(repository=repo)
    t_id = uuid4()

    # Setup teacher in READY onboarding and REHEARSE state
    teacher = await repo.get_or_create_teacher(t_id)
    teacher.onboarding_state = OnboardingStateEnum.READY.value
    teacher.address_form = "f"
    await repo.save_teacher(teacher)

    ctx = await service.get_or_create_context(t_id)
    ctx.onboarding_state = OnboardingStateEnum.READY
    ctx.current_state = SessionStateEnum.REHEARSE
    ctx.current_move_id = "NUM_SUB_REGROUP_BUNDLES"
    await service._sync_context_to_db(ctx, t_id)

    # Mock classifier and answerer
    mock_classify = QuestionClassificationResult(
        output=QuestionClassifierOutput(
            category="pedagogy",
            needs_clarification=False,
            clarifying_question_hi="",
            search_query_hi="घटाव बंडल खोलना",
            confidence=0.95,
        ),
        used_fallback=False,
    )

    mock_answer = GuideAnswerResult(
        output=GuideAnswererOutput(
            answer_hi="कक्षा में 10-10 तीलियों के बंडल खोलकर घटाव समझाएँ।",
            source_ids=["NUM_SUB_REGROUP_BUNDLES_kp2"],
            try_this_week_hi="बंडल खोलकर अभ्यास कराएँ।",
            confidence=0.92,
        ),
        answer_text_hi="कक्षा में 10-10 तीलियों के बंडल खोलकर घटाव समझाएँ।\n\nस्रोत: अभ्यास मूव सारांश\n\nइस हफ्ते आज़माएँ: बंडल खोलकर अभ्यास कराएँ।",
        escalated=False,
        sources_cited=[],
        guarded=True,
        used_fallback=False,
    )

    with (
        patch("backend.app.sessions.service.classify_question", new_callable=AsyncMock) as m_cls,
        patch(
            "backend.app.sessions.service.answer_guide_question", new_callable=AsyncMock
        ) as m_ans,
    ):
        m_cls.return_value = mock_classify
        m_ans.return_value = mock_answer

        outbounds = await service.handle_inbound(
            make_inbound(t_id, text="सवाल: 43 में से 27 घटाते समय बंडल कैसे समझाएं?")
        )

        assert len(outbounds) == 2
        # Message 1: Guide Answer
        assert "अभ्यास मूव सारांश" in outbounds[0].text_hi
        assert "बंडल खोलकर घटाव" in outbounds[0].text_hi

        # Message 2: Resume note + previous state prompt
        assert get_message("ask_resume", "f") in outbounds[1].text_hi
        assert "कक्षा 2" in outbounds[1].text_hi or "तैयार हों" in outbounds[1].text_hi

        # DB checks: Question persisted as answered
        questions = [q for q in repo._questions if q.teacher_id == t_id]
        assert len(questions) == 1
        assert questions[0].category == "pedagogy"
        assert questions[0].status == "answered"

        # Context restored to REHEARSE
        ctx_after = await service.get_or_create_context(t_id)
        assert ctx_after.current_state == SessionStateEnum.REHEARSE
        assert ctx_after.prior_state_before_ask is None


@pytest.mark.asyncio
async def test_ask_flow_out_of_scope_canned_reply() -> None:
    """Tests out of scope question returns canned polite decline and resumes state."""
    repo = FakeSessionRepository()
    service = SessionService(repository=repo)
    t_id = uuid4()

    teacher = await repo.get_or_create_teacher(t_id)
    teacher.onboarding_state = OnboardingStateEnum.READY.value
    await repo.save_teacher(teacher)

    ctx = await service.get_or_create_context(t_id)
    ctx.onboarding_state = OnboardingStateEnum.READY
    ctx.current_state = SessionStateEnum.LEARN
    await service._sync_context_to_db(ctx, t_id)

    mock_classify = QuestionClassificationResult(
        output=QuestionClassifierOutput(
            category="out_of_scope",
            needs_clarification=False,
            clarifying_question_hi="",
            search_query_hi="",
            confidence=0.99,
        ),
        used_fallback=False,
    )

    with patch("backend.app.sessions.service.classify_question", new_callable=AsyncMock) as m_cls:
        m_cls.return_value = mock_classify

        outbounds = await service.handle_inbound(make_inbound(t_id, text="सवाल: कल मौसम कैसा रहेगा?"))

        assert len(outbounds) == 2
        # Message 1: Out of scope polite message
        expected_msg = get_message("ask_out_of_scope", "f")
        assert expected_msg in outbounds[0].text_hi

        # Message 2: Resumed state prompt
        assert get_message("ask_resume", "f") in outbounds[1].text_hi

        # DB question logged
        questions = [q for q in repo._questions if q.teacher_id == t_id]
        assert len(questions) == 1
        assert questions[0].category == "out_of_scope"

        # Context resumed to LEARN
        ctx_after = await service.get_or_create_context(t_id)
        assert ctx_after.current_state == SessionStateEnum.LEARN


@pytest.mark.asyncio
async def test_ask_flow_admin_escalation_to_review_item() -> None:
    """Tests admin question escalates to ARP ReviewItem and resumes state."""
    repo = FakeSessionRepository()
    service = SessionService(repository=repo)
    t_id = uuid4()

    teacher = await repo.get_or_create_teacher(t_id)
    teacher.onboarding_state = OnboardingStateEnum.READY.value
    await repo.save_teacher(teacher)

    ctx = await service.get_or_create_context(t_id)
    ctx.onboarding_state = OnboardingStateEnum.READY
    ctx.current_state = SessionStateEnum.EXPLAIN_BACK
    await service._sync_context_to_db(ctx, t_id)

    outbounds = await service.handle_inbound(
        make_inbound(t_id, text="admin: अवकाश के लिए आवेदन कैसे करें?")
    )

    assert len(outbounds) == 2
    # Message 1: Admin canned response
    assert get_message("ask_admin", "f") in outbounds[0].text_hi

    # Message 2: Resumed state prompt
    assert get_message("ask_resume", "f") in outbounds[1].text_hi

    # ReviewItem created
    questions = [q for q in repo._questions if q.teacher_id == t_id]
    assert len(questions) == 1
    assert questions[0].category == "admin"
    assert questions[0].status == "escalated"

    review_items = repo._review_items
    assert len(review_items) == 1
    assert review_items[0].kind == "question"
    assert review_items[0].ref_id == str(questions[0].id)

    # State restored to EXPLAIN_BACK
    ctx_after = await service.get_or_create_context(t_id)
    assert ctx_after.current_state == SessionStateEnum.EXPLAIN_BACK


@pytest.mark.asyncio
async def test_ask_flow_clarifying_question_roundtrip() -> None:
    """Tests ambiguous question asks for clarification once, then answers upon clarification."""
    repo = FakeSessionRepository()
    service = SessionService(repository=repo)
    t_id = uuid4()

    teacher = await repo.get_or_create_teacher(t_id)
    teacher.onboarding_state = OnboardingStateEnum.READY.value
    await repo.save_teacher(teacher)

    ctx = await service.get_or_create_context(t_id)
    ctx.onboarding_state = OnboardingStateEnum.READY
    ctx.current_state = SessionStateEnum.LEARN
    await service._sync_context_to_db(ctx, t_id)

    mock_clarify_needed = QuestionClassificationResult(
        output=QuestionClassifierOutput(
            category="pedagogy",
            needs_clarification=True,
            clarifying_question_hi="आप किस कक्षा या विषय के बारे में पूछ रही हैं?",
            search_query_hi="",
            confidence=0.8,
        ),
        used_fallback=False,
    )

    mock_clarified = QuestionClassificationResult(
        output=QuestionClassifierOutput(
            category="pedagogy",
            needs_clarification=False,
            clarifying_question_hi="",
            search_query_hi="कक्षा 2 गणित हासिल",
            confidence=0.95,
        ),
        used_fallback=False,
    )

    mock_answer = GuideAnswerResult(
        output=GuideAnswererOutput(
            answer_hi="कक्षा 2 के लिए तीलियों का उपयोग करें।",
            source_ids=["NUM_SUB_REGROUP_BUNDLES_learn"],
            try_this_week_hi="तीलियों से अभ्यास कराएं।",
            confidence=0.9,
        ),
        answer_text_hi="कक्षा 2 के लिए तीलियों का उपयोग करें।\n\nस्रोत: अभ्यास मूव सारांश",
        escalated=False,
        sources_cited=[],
        guarded=True,
        used_fallback=False,
    )

    with (
        patch("backend.app.sessions.service.classify_question", new_callable=AsyncMock) as m_cls,
        patch(
            "backend.app.sessions.service.answer_guide_question", new_callable=AsyncMock
        ) as m_ans,
    ):
        m_cls.return_value = mock_clarify_needed
        m_ans.return_value = mock_answer

        # Turn 1: Vague question
        out1 = await service.handle_inbound(make_inbound(t_id, text="सवाल: बच्चे समझ नहीं पा रहे"))
        assert len(out1) == 1
        assert "किस कक्षा या विषय" in out1[0].text_hi

        ctx1 = await service.get_or_create_context(t_id)
        assert ctx1.current_state == SessionStateEnum.ASK
        assert ctx1.clarifying_already_asked is True

        # Turn 2: Clarification answer
        m_cls.return_value = mock_clarified
        out2 = await service.handle_inbound(make_inbound(t_id, text="कक्षा 2 में हासिल वाला घटाव"))
        assert len(out2) == 2
        assert "कक्षा 2 के लिए तीलियों" in out2[0].text_hi
        assert get_message("ask_resume", "f") in out2[1].text_hi

        ctx2 = await service.get_or_create_context(t_id)
        assert ctx2.current_state == SessionStateEnum.LEARN
        assert ctx2.clarifying_already_asked is False
