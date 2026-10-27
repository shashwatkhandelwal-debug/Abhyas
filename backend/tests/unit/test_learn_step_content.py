"""Unit tests for learn-step content, key points display in UI language, and button rules (2026-10-26 fixes)."""

from __future__ import annotations

import re
from unittest.mock import AsyncMock, patch

import pytest
from test_state_machine import FakeSessionRepository

from backend.app.core.messages import reset_ui_lang, set_ui_lang
from backend.app.llm.roles.coach_suggestion import SuggestionResult
from backend.app.llm.schemas import RetrievedChunk
from backend.app.rehearsal.scene_runner import load_move_card
from backend.app.sessions.service import SessionService

DEVANAGARI = re.compile(r"[\u0900-\u097F]")


@pytest.mark.asyncio
async def test_learn_step_shows_3_to_4_key_points_in_hindi() -> None:
    token = set_ui_lang("hi")
    try:
        service = SessionService(repository=FakeSessionRepository())
        move = load_move_card("NUM_SUB_REGROUP_BUNDLES")
        messages = await service._build_learn_messages(move, address_form="f")

        assert len(messages) >= 1
        bubble1 = messages[0]
        text = bubble1.text_hi or ""

        # Check key points are displayed as 1., 2., 3., 4.
        for i in range(1, 5):
            assert f"{i}. " in text

        # Hindi key points from card
        assert "घटा" in text or "संख्या" in text
        # Voice note is NOT mentioned when audio_ref is None
        assert "वॉइस नोट" not in text
        assert "पहले 2 मिनट की यह आवाज़ सुनिए" not in text
    finally:
        reset_ui_lang(token)


@pytest.mark.asyncio
async def test_learn_step_shows_key_points_in_english_with_no_devanagari_in_bubble1() -> None:
    token = set_ui_lang("en")
    try:
        service = SessionService(repository=FakeSessionRepository())
        move = load_move_card("NUM_SUB_REGROUP_BUNDLES")
        messages = await service._build_learn_messages(move, address_form="f")

        assert len(messages) >= 1
        bubble1 = messages[0]
        text = bubble1.text_hi or ""

        # English intro and key points
        assert "This week's move:" in text
        assert "The key points are written below:" in text
        for i in range(1, 5):
            assert f"{i}. " in text

        # English text from card key points
        assert "subtract" in text.lower() or "bundle" in text.lower()

        # Pure English: zero Devanagari characters in Bubble 1
        assert not DEVANAGARI.search(text), f"Bubble 1 contains Devanagari: {text}"
        assert "voice note" not in text.lower()
    finally:
        reset_ui_lang(token)


@pytest.mark.asyncio
async def test_learn_step_has_one_understood_button_on_last_bubble_when_no_audio() -> None:
    service = SessionService(repository=FakeSessionRepository())
    move = load_move_card("NUM_SUB_REGROUP_BUNDLES")
    chunk = RetrievedChunk(
        chunk_id="test:p01:001",
        source_short_hi="निपुण भारत",
        page=10,
        text="अंश",
        score=0.9,
    )
    with patch(
        "backend.app.sessions.service.suggest_from_sources", new_callable=AsyncMock
    ) as mock_sugg:
        mock_sugg.return_value = SuggestionResult(
            suggestion_hi="सुझाव यहाँ।",
            chunk=chunk,
        )
        messages = await service._build_learn_messages(move, address_form="f", audio_ref=None)

    assert len(messages) == 2
    bubble1, bubble2 = messages[0], messages[1]

    # Bubble 1 has NO buttons
    assert bubble1.buttons is None or len(bubble1.buttons) == 0

    # Last bubble has buttons
    assert bubble2.buttons is not None and len(bubble2.buttons) >= 1
    btn_ids = [b.id for b in bubble2.buttons]
    assert btn_ids[0] == "btn_understood"
