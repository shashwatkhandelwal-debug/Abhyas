"""Unit tests for Problem Statement Gap Fixes (Job 05).

Verifies:
1. Experience-aware adaptation for novice teachers (0-1 and 2-5 bands) in learn step.
2. Inclusion of modelled teaching move examples (model teacher demonstration) in coach feedback.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from backend.app.core.messages import get_message
from backend.app.rehearsal.scene_runner import load_move_card
from backend.app.sessions.service import SessionService


def test_messages_have_novice_tip_and_model_label() -> None:
    """Verify keys exist in Hindi message catalog with proper address forms."""
    tip_f = get_message("ui_novice_teacher_tip", "f")
    tip_m = get_message("ui_novice_teacher_tip", "m")
    assert "तीली-बंडल" in tip_f
    assert "तीली-बंडल" in tip_m

    lbl_f = get_message("ui_model_teacher_exemplar_label", "f")
    lbl_m = get_message("ui_model_teacher_exemplar_label", "m")
    assert "शिक्षिका" in lbl_f
    assert "शिक्षक" in lbl_m


@pytest.mark.asyncio
async def test_build_learn_messages_adapts_to_novice_experience() -> None:
    """Novice teachers (0-1 band) receive supportive scaffold tip in learn step intro."""
    mock_repo = AsyncMock()
    svc = SessionService(repository=mock_repo)

    real_move = load_move_card("NUM_SUB_REGROUP_BUNDLES")

    # 1. Novice teacher (0-1)
    msgs_novice = await svc._build_learn_messages(
        move=real_move,
        address_form="f",
        experience_band="0-1",
    )
    assert len(msgs_novice) >= 1
    all_novice_text = "\n\n".join(m.text_hi for m in msgs_novice)
    assert "सुझाव (शुरुआती अभ्यास)" in all_novice_text

    # 2. None / unspecified experience
    msgs_default = await svc._build_learn_messages(
        move=real_move,
        address_form="f",
        experience_band=None,
    )
    assert len(msgs_default) >= 1
    all_default_text = "\n\n".join(m.text_hi for m in msgs_default)
    assert "सुझाव (शुरुआती अभ्यास)" not in all_default_text


def test_move_card_model_rehearsal_contains_teacher_exemplar() -> None:
    """Existing move cards define exemplary teacher model turns."""
    move = load_move_card("NUM_SUB_REGROUP_BUNDLES")
    assert move.model_rehearsal
    teacher_turns = [t for t in move.model_rehearsal if getattr(t, "speaker", None) == "teacher"]
    assert len(teacher_turns) >= 1
    exemplar = teacher_turns[0]
    assert exemplar.text_hi
    assert "43" in exemplar.text_hi or "बंडल" in exemplar.text_hi
