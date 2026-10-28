"""The handbook fallback (answer service down) speaks the teacher's language and never dumps the
English original: the lead-in comes from the catalogue, the summary is the stored Hindi gloss, the
source chip carries the original passage."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any
from unittest.mock import patch
from uuid import uuid4

import pytest

from backend.app.core.messages import get_message, reset_ui_lang, set_ui_lang
from backend.app.core.types import InboundMessage
from backend.app.handbook.fallback import fallback_reply
from backend.app.handbook.questions import load_handbook_questions
from backend.app.retrieval.search import get_guide_retriever
from backend.app.sessions.service import SessionService
from backend.tests.unit.test_handbook_flow import _ready
from backend.tests.unit.test_state_machine import FakeSessionRepository

QUESTIONS = load_handbook_questions()
DEVANAGARI = re.compile("[ऀ-ॿ]")
LATIN_WORD = re.compile(r"[A-Za-z]{3,}")


def _lead_in(lang: str) -> str:
    return get_message("handbook_fallback", "f", lang=lang).split("{summary}")[0].strip()


@pytest.mark.parametrize("lang", ["hi", "en"])
@pytest.mark.parametrize("question", QUESTIONS, ids=[q.id for q in QUESTIONS])
def test_fallback_has_the_lead_in_the_hindi_summary_and_the_citation_but_not_the_english_original(
    lang: str, question: Any
) -> None:
    token = set_ui_lang(lang)
    try:
        result = fallback_reply(question, get_guide_retriever(), "f")
    finally:
        reset_ui_lang(token)
    assert result is not None
    text, cites = result
    stored = get_guide_retriever().get_chunk(question.chunk_id)
    assert stored is not None
    assert text.startswith(_lead_in(lang))
    assert str(stored["gloss_hi"]) in text  # the Hindi summary, as stored
    assert cites and cites[0].line_hi in text  # the citation
    original = str(stored["text"])
    assert original[:80] not in text and len(text) < 700  # no English passage
    if lang == "hi":
        assert not LATIN_WORD.search(_lead_in("hi"))
        lead_and_tail = text.replace(str(stored["gloss_hi"]), "").replace(cites[0].line_hi, "")
        assert DEVANAGARI.search(lead_and_tail) and not LATIN_WORD.search(lead_and_tail)
    else:
        assert LATIN_WORD.search(_lead_in("en"))


def test_both_catalogues_carry_the_lead_in_with_the_same_placeholders() -> None:
    hi = get_message("handbook_fallback", "f", lang="hi")
    en = get_message("handbook_fallback", "f", lang="en")
    for token in ("{summary}", "{citation}"):
        assert token in hi and token in en
    assert DEVANAGARI.search(hi) and not DEVANAGARI.search(en)


@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["hi", "en"])
async def test_a_chip_question_in_the_chat_gets_the_fallback_in_the_ui_language(lang: str) -> None:
    """End to end with the mock LLM (its answer fails the guard, so the fallback is used)."""
    question = QUESTIONS[0]
    repo = FakeSessionRepository()
    service = SessionService(repository=repo)
    teacher_id = await _ready(service, repo)
    inbound = InboundMessage(
        channel="web",
        channel_msg_id=f"m-{uuid4().hex[:8]}",
        teacher_id=teacher_id,
        kind="text",
        text=question.send_text(),
        received_at=datetime.now(UTC),
    )
    token = set_ui_lang(lang)
    try:
        with patch("backend.app.sessions.service.classify_question") as cls:
            out = await service.handle_inbound(inbound)
            cls.assert_not_called()
    finally:
        reset_ui_lang(token)
    answer = out[0]
    stored = get_guide_retriever().get_chunk(question.chunk_id)
    assert stored is not None
    body = answer.text_hi or ""
    assert body.startswith(_lead_in(lang))
    assert str(stored["gloss_hi"]) in body
    assert str(stored["text"])[:80] not in body
    assert answer.citations  # the source chip that opens the original passage
