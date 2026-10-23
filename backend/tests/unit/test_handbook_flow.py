"""Handbook chips through the ask path, the deterministic fallback, and the learn-step tip."""

from __future__ import annotations

import unicodedata
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from backend.app.config import settings
from backend.app.core.messages import get_message
from backend.app.core.types import InboundMessage, OutboundMessage
from backend.app.handbook.fallback import fallback_reply, match_handbook_question
from backend.app.handbook.questions import load_handbook_questions
from backend.app.llm.roles.coach_suggestion import SuggestionResult
from backend.app.llm.schemas import (
    GuideAnswererOutput,
    GuideAnswerResult,
    RetrievedChunk,
)
from backend.app.rehearsal.scene_runner import load_move_card
from backend.app.retrieval.search import get_guide_retriever
from backend.app.sessions.service import SessionService
from backend.app.sessions.state_machine import OnboardingStateEnum, SessionStateEnum
from backend.tests.unit.test_state_machine import FakeSessionRepository

QUESTIONS = load_handbook_questions()
TIP_MARKER = get_message("learn_handbook_tip", "f", tip="", citation="").split(":")[0]


def _inbound(teacher_id: Any, text: str) -> InboundMessage:
    return InboundMessage(
        channel="web",
        channel_msg_id=f"m-{uuid4().hex[:8]}",
        teacher_id=teacher_id,
        kind="text",
        text=text,
        received_at=datetime.now(UTC),
    )


async def _ready(service: SessionService, repo: FakeSessionRepository) -> Any:
    teacher_id = uuid4()
    teacher = await repo.get_or_create_teacher(teacher_id)
    teacher.onboarding_state = OnboardingStateEnum.READY.value
    await repo.save_teacher(teacher)
    ctx = await service.get_or_create_context(teacher_id)
    ctx.onboarding_state = OnboardingStateEnum.READY
    ctx.current_state = SessionStateEnum.LEARN
    await service._sync_context_to_db(ctx, teacher_id)
    return teacher_id


def _body(out: list[OutboundMessage]) -> str:
    return "\n".join(m.text_hi or "" for m in out)


def _not_found_texts() -> list[str]:
    return [
        get_message(key, "f") for key in ("ask_not_in_sources", "ask_escalated", "ask_out_of_scope")
    ]


def test_matching_accepts_the_chip_text_with_or_without_the_ask_keyword() -> None:
    q = QUESTIONS[0]
    assert match_handbook_question(q.send_text()) == q
    assert match_handbook_question(q.hi) == q
    assert match_handbook_question(f"  {q.hi}?  ") == q
    assert match_handbook_question("मौसम कैसा है?") is None
    assert match_handbook_question("") is None


@pytest.mark.asyncio
@pytest.mark.parametrize("question", QUESTIONS, ids=[q.id for q in QUESTIONS])
async def test_chip_question_with_the_mock_llm_gets_a_cited_answer_never_not_found(
    question: Any,
) -> None:
    """No patches: the mock LLM cites a chunk id that is not in the excerpts, so the answerer
    escalates, and the chip falls back to its own chunk's stored summary with source and page."""
    repo = FakeSessionRepository()
    service = SessionService(repository=repo)
    teacher_id = await _ready(service, repo)
    with patch("backend.app.sessions.service.classify_question", new_callable=AsyncMock) as cls:
        out = await service.handle_inbound(_inbound(teacher_id, question.send_text()))
        cls.assert_not_called()  # a curated question needs no classifier
    answer = out[0]
    assert answer.citations, f"{question.id}: no citation"
    assert answer.citations[0].page is not None
    assert answer.citations[0].line_hi in (answer.text_hi or "")
    assert get_message("handbook_source_label", "f") in (answer.text_hi or "")
    for text in _not_found_texts():
        assert text not in _body(out)
    stored = [q for q in repo._questions if q.status == "answered"]
    assert stored and stored[-1].source_ids == [question.chunk_id]
    assert unicodedata.is_normalized("NFC", answer.text_hi or "")


@pytest.mark.asyncio
@pytest.mark.parametrize("question", QUESTIONS, ids=[q.id for q in QUESTIONS])
async def test_chip_question_with_a_model_that_cites_its_chunk_gets_the_generated_answer(
    question: Any,
) -> None:
    retriever = get_guide_retriever()
    stored = retriever.get_chunk(question.chunk_id)
    assert stored is not None
    answer_hi = str(stored["gloss_hi"])
    tool_output = {
        "answer_hi": answer_hi,
        "source_ids": [question.chunk_id],
        "try_this_week_hi": "",
        "confidence": 0.9,
    }
    repo = FakeSessionRepository()
    service = SessionService(repository=repo)
    teacher_id = await _ready(service, repo)
    with patch("backend.app.llm.roles.guide_answerer.call_tool", new_callable=AsyncMock) as tool:
        tool.return_value = tool_output
        out = await service.handle_inbound(_inbound(teacher_id, question.send_text()))
    answer = out[0]
    assert answer.speaker == "guide"
    assert answer_hi in (answer.text_hi or "")
    assert [c.chunk_id for c in answer.citations] == [question.chunk_id]
    assert get_message("handbook_source_label", "f") in (answer.text_hi or "")


@pytest.mark.asyncio
async def test_label_only_when_citations_exist_and_only_for_chip_questions() -> None:
    repo = FakeSessionRepository()
    service = SessionService(repository=repo)
    teacher_id = await _ready(service, repo)
    label = get_message("handbook_source_label", "f")
    # a typed question that is not a chip: escalated, no citation, no label
    escalated = GuideAnswerResult(
        output=GuideAnswererOutput(answer_hi="x", source_ids=[], confidence=0.0),
        answer_text_hi="x",
        escalated=True,
        sources_cited=[],
        guarded=True,
        used_fallback=True,
    )
    with patch("backend.app.sessions.service.answer_guide_question", new_callable=AsyncMock) as ans:
        ans.return_value = escalated
        out = await service.handle_inbound(_inbound(teacher_id, "सवाल: स्कूल की छुट्टियाँ कब हैं?"))
    assert label not in _body(out)
    assert not out[0].citations
    # a chip question whose own chunk is unavailable: honest escalation, still no label
    q = QUESTIONS[0]
    with (
        patch("backend.app.sessions.service.answer_guide_question", new_callable=AsyncMock) as ans,
        patch("backend.app.sessions.service.fallback_reply", return_value=None),
    ):
        ans.return_value = escalated
        out = await service.handle_inbound(_inbound(teacher_id, q.send_text()))
    assert label not in _body(out)
    assert not out[0].citations


def test_fallback_reply_needs_the_stored_summary_and_names_source_and_page() -> None:
    q = QUESTIONS[1]
    retriever = get_guide_retriever()
    result = fallback_reply(q, retriever, "f")
    assert result is not None
    text, cites = result
    stored = retriever.get_chunk(q.chunk_id)
    assert stored is not None
    assert str(stored["gloss_hi"]) in text
    assert cites[0].chunk_id == q.chunk_id and cites[0].page == stored.get("page")

    class NoChunks:
        def get_chunk(self, chunk_id: str) -> None:
            return None

    assert fallback_reply(q, NoChunks(), "f") is None  # type: ignore[arg-type]


# ── a tip on each module's learning step ─────────────────────────────────────


class _SpyRetriever:
    def __init__(self, hits: list[Any]) -> None:
        self.hits = hits
        self.calls: list[dict[str, Any]] = []

    async def retrieve(self, query: str, **kwargs: Any) -> list[Any]:
        self.calls.append({"query": query, **kwargs})
        return self.hits


def _official_hit() -> Any:
    chunk = get_guide_retriever().get_chunk(settings.COACH_SUGGESTION_SOURCE_ID + ":p447:324")
    assert chunk is not None

    class Hit:
        chunk_id = "nishtha_fln:p447:324"
        source = settings.COACH_SUGGESTION_SOURCE_ID
        source_short_hi = str(chunk.get("source_short_hi") or "FLN")
        section = str(chunk["section"])
        page = chunk.get("page")
        text = str(chunk["text"])
        gloss_hi = str(chunk["gloss_hi"])
        keywords_hi: list[str] = []
        similarity_score = 0.5

    return Hit()


@pytest.mark.asyncio
async def test_learn_step_gets_one_cited_tip_through_the_coach_suggestion_gates() -> None:
    hit = _official_hit()
    spy = _SpyRetriever([hit])
    service = SessionService(repository=FakeSessionRepository())
    service.retriever = spy  # type: ignore[assignment]
    move = load_move_card("NUM_SUB_REGROUP_BUNDLES")
    chunk = RetrievedChunk(
        chunk_id=hit.chunk_id,
        source_short_hi=hit.source_short_hi,
        section=hit.section,
        page=hit.page,
        text=hit.text,
    )
    with patch(
        "backend.app.sessions.service.suggest_from_sources", new_callable=AsyncMock
    ) as suggest:
        suggest.return_value = SuggestionResult(suggestion_hi="बच्चे को खुद सोचने दें।", chunk=chunk)
        text, cites = await service._learn_intro(move, "f")
    assert "बच्चे को खुद सोचने दें।" in text
    assert any(c.chunk_id == hit.chunk_id for c in cites)
    # same gates as the coach's source suggestion: official only, score and matched-terms floors
    tip_call = next(c for c in spy.calls if c.get("top_k") == settings.HANDBOOK_TIP_POOL)
    assert tip_call["official_only"] is True
    assert tip_call["min_score"] == settings.RETRIEVAL_MIN_SCORE
    assert tip_call["min_matched_terms"] == settings.RETRIEVAL_MIN_MATCHED_TERMS
    suggest.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "result",
    [
        SuggestionResult(),  # no support / model found nothing
        SuggestionResult(used_fallback=True),  # guard failed twice
    ],
    ids=["no-support", "guard-failure"],
)
async def test_no_support_or_guard_failure_means_no_tip(result: SuggestionResult) -> None:
    spy = _SpyRetriever([_official_hit()])
    service = SessionService(repository=FakeSessionRepository())
    service.retriever = spy  # type: ignore[assignment]
    move = load_move_card("NUM_SUB_REGROUP_BUNDLES")
    with patch(
        "backend.app.sessions.service.suggest_from_sources", new_callable=AsyncMock
    ) as suggest:
        suggest.return_value = result
        text, _ = await service._learn_intro(move, "f")
    assert TIP_MARKER not in text


@pytest.mark.asyncio
async def test_no_official_chunks_means_no_llm_call_for_the_tip() -> None:
    spy = _SpyRetriever([])
    service = SessionService(repository=FakeSessionRepository())
    service.retriever = spy  # type: ignore[assignment]
    move = load_move_card("NUM_SUB_REGROUP_BUNDLES")
    with patch("backend.app.llm.roles.coach_suggestion.call_tool", new_callable=AsyncMock) as tool:
        text, cites = await service._learn_intro(move, "f")
    tool.assert_not_called()
    assert cites == []
    assert TIP_MARKER not in text
