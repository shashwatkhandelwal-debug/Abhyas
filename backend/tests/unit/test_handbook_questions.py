"""Handbook question chips: every question points at a real chunk the BM25 retriever finds."""

from __future__ import annotations

import unicodedata
from datetime import date, timedelta
from uuid import UUID, uuid4

import pytest

from backend.app.config import settings
from backend.app.handbook.questions import (
    chip_by_index,
    chips_for,
    load_handbook_questions,
)
from backend.app.retrieval.search import get_guide_retriever


def test_between_min_and_max_questions_with_unique_ids_and_english() -> None:
    questions = load_handbook_questions()
    assert settings.HANDBOOK_QUESTIONS_MIN <= len(questions) <= settings.HANDBOOK_QUESTIONS_MAX
    assert len({q.id for q in questions}) == len(questions)
    assert len({q.chunk_id for q in questions}) == len(questions)  # each tied to its own chunk
    for q in questions:
        assert q.en.strip() and q.hi.strip()
        assert unicodedata.is_normalized("NFC", q.hi)


@pytest.mark.asyncio
async def test_every_question_retrieves_its_chunk_in_the_top_five_without_an_llm() -> None:
    retriever = get_guide_retriever()
    for q in load_handbook_questions():
        assert retriever.get_chunk(q.chunk_id) is not None, f"{q.id}: unknown chunk {q.chunk_id}"
        hits = await retriever.retrieve(
            q.hi,
            top_k=settings.HANDBOOK_VALIDATION_TOP_K,
            min_score=settings.RETRIEVAL_MIN_SCORE,
            min_matched_terms=settings.RETRIEVAL_MIN_MATCHED_TERMS,
        )
        assert q.chunk_id in [h.chunk_id for h in hits], f"{q.id}: chunk not in top five"


def test_chips_are_four_distinct_and_stable_for_a_teacher_on_a_day() -> None:
    teacher = uuid4()
    today = date(2026, 10, 23)
    first = chips_for(teacher, today)
    assert len(first) == settings.HANDBOOK_CHIPS_SHOWN == 4
    assert len({q.id for q in first}) == 4
    assert chips_for(teacher, today) == first
    assert chips_for(str(teacher), today) == first  # same id as text


def test_chips_rotate_across_days_and_differ_between_teachers() -> None:
    teacher = UUID(int=7)
    days = [date(2026, 10, 23) + timedelta(days=i) for i in range(10)]
    sets = {tuple(q.id for q in chips_for(teacher, d)) for d in days}
    assert len(sets) > 1
    others = {tuple(q.id for q in chips_for(UUID(int=n), days[0])) for n in range(20)}
    assert len(others) > 1


def test_chip_by_index_and_send_text_uses_the_ask_keyword() -> None:
    teacher = uuid4()
    day = date(2026, 10, 23)
    chip = chip_by_index(teacher, day, 0)
    assert chip is not None and chip == chips_for(teacher, day)[0]
    assert chip_by_index(teacher, day, 4) is None and chip_by_index(teacher, day, -1) is None
    from backend.app.core.intents import Intent, extract_ask_query, match_intent

    assert match_intent(chip.send_text()) == Intent.ASK
    assert extract_ask_query(chip.send_text()).startswith(chip.hi[:12])


def test_demo_teachers_get_chips_and_a_reset_cannot_change_them() -> None:
    """Chips are a pure function of teacher id and day: nothing in the demo reset touches them."""
    from backend.app.db.seed import DEMO_TEACHER_LOGINS

    day = date(2026, 10, 23)
    assert sorted(DEMO_TEACHER_LOGINS) == ["teacher.demo1", "teacher.demo2", "teacher.demo3"]
    for teacher_id, _position in DEMO_TEACHER_LOGINS.values():
        before = [q.id for q in chips_for(teacher_id, day)]
        assert len(before) == 4
        assert [q.id for q in chips_for(teacher_id, day)] == before


def test_every_question_has_a_stored_summary_for_the_fallback() -> None:
    retriever = get_guide_retriever()
    for q in load_handbook_questions():
        stored = retriever.get_chunk(q.chunk_id)
        assert stored is not None and str(stored.get("gloss_hi", "")).strip(), q.id
        assert stored.get("page") is not None, f"{q.id}: chunk has no page to cite"
