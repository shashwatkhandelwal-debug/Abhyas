"""fix7: a Guide answer at steps 5-7 ends with that step's own quick replies, on the REAL demo2 seed."""

# ruff: noqa: F811  (the seeded-database fixtures are imported from the demo-loop tests)
from __future__ import annotations

import os

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from test_demo_loop_postgres import (  # noqa: F401
    flags,
    seeded_db,
    session,
)
from test_fix6_demo2_free_text import EN, HI, _demo2, _msg, _state, _texts

from backend.app.core.messages import get_message

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL not set"
)

# (moves to reach the step, state, button ids expected after the Guide answer)
STEPS = {
    "step5": ([("बस", None)], "FEEDBACK", ["btn_retry", "btn_continue", "btn_progress"]),
    "step6": (
        [("बस", None), (None, "btn_continue")],
        "TRY_IN_CLASS",
        ["btn_peer", "btn_self", "btn_later"],
    ),
    "step7_peer": (
        [("बस", None), (None, "btn_continue"), (None, "btn_peer")],
        "REFLECT_PEER",
        ["btn_yes", "btn_no"],
    ),
    "step7_self": (
        [("बस", None), (None, "btn_continue"), (None, "btn_self")],
        "REFLECT_SELF",
        [],
    ),
}


@pytest.mark.asyncio
@pytest.mark.parametrize("question", [HI, EN], ids=["hindi", "english"])
@pytest.mark.parametrize("step", list(STEPS))
async def test_guide_answer_resends_the_steps_buttons(
    session: AsyncSession, step: str, question: str
) -> None:
    moves, state, ids = STEPS[step]
    service = await _demo2(session)
    for text, button in moves:
        await service.handle_inbound(_msg(text, button))
    out = await service.handle_inbound(_msg(question))
    carry_on = out[-1]
    assert get_message("ask_resume", "f") in (carry_on.text_hi or "")
    assert [b.id for b in carry_on.buttons or []] == ids
    assert "{" not in (carry_on.text_hi or "")  # no raw placeholder from the catalogue
    assert await _state(service) == state


@pytest.mark.asyncio
@pytest.mark.parametrize("word", ["continue", "Continue", "next", "Next"])
async def test_typed_continue_and_next_at_step_5_move_on(session: AsyncSession, word: str) -> None:
    service = await _demo2(session)
    await service.handle_inbound(_msg("बस"))
    assert await _state(service) == "FEEDBACK"
    out = await service.handle_inbound(_msg(word))
    assert await _state(service) == "TRY_IN_CLASS"
    assert get_message("unclear", "f") not in _texts(out)
