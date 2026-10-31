"""fix6: free text of 4+ words reaches the Guide from the REAL teacher.demo2 seeded state.

fix5 tested hand-built contexts; the hosted app answered "did not understand" at step 6.
This drives the seeded demo2 chat the way the judge did: type "बस", press Continue, then ask (the seeded follow-up card is still unanswered).
"""

# ruff: noqa: F811  (the seeded-database fixtures are imported from the demo-loop tests)
from __future__ import annotations

import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from test_demo_loop_postgres import (  # noqa: F401
    FIXED,
    flags,
    seeded_db,
    session,
)

from backend.app.core.messages import get_message
from backend.app.core.types import InboundMessage, OutboundMessage
from backend.app.db.demo_loop import seed_login_loop
from backend.app.db.seed import TEACHER_DEMO2_ID, reset_demo_teacher
from backend.app.sessions.service import SessionService

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL not set"
)

HI = "मेरी कक्षा में कक्षा 1 और 2 के बच्चे साथ बैठते हैं, घटाव एक साथ कैसे सिखाऊँ?"
EN = "How do I teach subtraction to Class 1 and Class 2 children sitting together?"


def _msg(text: str | None = None, button: str | None = None) -> InboundMessage:
    return InboundMessage(
        channel="web",
        channel_msg_id=f"m-{uuid4().hex[:8]}",
        teacher_id=TEACHER_DEMO2_ID,
        kind="button" if button else "text",
        text=text,
        button_id=button,
        received_at=datetime.now(UTC),
    )


def _texts(out: list[OutboundMessage]) -> str:
    return "\n".join(m.text_hi or "" for m in out)


async def _demo2(session: AsyncSession) -> SessionService:
    await reset_demo_teacher(session, "teacher.demo2")
    await seed_login_loop(session, TEACHER_DEMO2_ID, FIXED)
    await session.commit()
    return SessionService(db_session=session)


async def _state(service: SessionService) -> str:
    return (await service.get_or_create_context(TEACHER_DEMO2_ID)).current_state.value


# the judge's path: "बस" (FEEDBACK, step 5), Continue (TRY_IN_CLASS, step 6), then the buttons
STEPS = {
    "step5_feedback": ([("बस", None)], "FEEDBACK"),
    "step6_try_in_class": ([("बस", None), (None, "btn_continue")], "TRY_IN_CLASS"),
    "step7_reflect_peer": (
        [("बस", None), (None, "btn_continue"), (None, "btn_peer")],
        "REFLECT_PEER",
    ),
    "step7_reflect_self": (
        [("बस", None), (None, "btn_continue"), (None, "btn_self")],
        "REFLECT_SELF",
    ),
}


@pytest.mark.asyncio
@pytest.mark.parametrize("question", [HI, EN], ids=["hindi", "english"])
@pytest.mark.parametrize("step", list(STEPS))
async def test_demo2_long_free_text_reaches_the_guide_at_steps_5_to_7(
    session: AsyncSession, step: str, question: str
) -> None:
    moves, expected_state = STEPS[step]
    service = await _demo2(session)
    ctx = await service.get_or_create_context(TEACHER_DEMO2_ID)
    assert ctx.followup_stage == "ask"  # the seeded follow-up card is still waiting for a tap
    for text, button in moves:
        await service.handle_inbound(_msg(text, button))
    assert await _state(service) == expected_state
    out = await service.handle_inbound(_msg(question))
    assert out
    assert get_message("unclear", "f") not in _texts(out)
    assert await _state(service) == expected_state  # a side trip: the step and its buttons stay


@pytest.mark.asyncio
async def test_demo2_checklist_progress_is_not_eaten_by_the_question(session: AsyncSession) -> None:
    service = await _demo2(session)
    for text, button in (("बस", None), (None, "btn_continue"), (None, "btn_peer")):
        await service.handle_inbound(_msg(text, button))
    await service.handle_inbound(_msg(HI))
    out = await service.handle_inbound(_msg(None, "btn_yes"))  # answers item 1, shows item 2
    assert "2/5" in _texts(out)


@pytest.mark.asyncio
async def test_demo2_help_and_short_noise_keep_their_old_answers(session: AsyncSession) -> None:
    service = await _demo2(session)
    for text, button in (("बस", None), (None, "btn_continue")):
        await service.handle_inbound(_msg(text, button))
    assert get_message("unclear", "f") in _texts(await service.handle_inbound(_msg("हम्म ठीक")))
