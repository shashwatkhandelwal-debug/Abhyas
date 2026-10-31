"""fix5: unrecognised free text of 4+ words goes to the Guide at every step except a running scene."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from test_one_on_one_flow import Harness, harness, texts  # noqa: F401

from backend.app.core.messages import get_message
from backend.app.sessions.state_machine import SessionStateEnum

QUESTION = "मेरी कक्षा में कक्षा 1 और 2 के बच्चे साथ बैठते हैं, घटाव एक साथ कैसे सिखाऊँ?"
PLAIN_LONG = "मेरे विद्यालय में अगले हफ्ते निरीक्षण है और बच्चे कम आते हैं"
UNCLEAR = get_message("unclear", "f")

STEPS = [
    SessionStateEnum.MODEL,
    SessionStateEnum.TRY_IN_CLASS,
    SessionStateEnum.REFLECT_PEER,
    SessionStateEnum.REFLECT_SELF,
    SessionStateEnum.DONE,
    SessionStateEnum.FEEDBACK,
]


async def _at(h: Harness, state: SessionStateEnum) -> None:
    await h.start("NUM_SUB_REGROUP_BUNDLES")
    ctx = await h.ctx()
    ctx.current_state = state
    await h.service._sync_context_to_db(ctx, h.teacher_id)


@pytest.mark.parametrize("state", STEPS)
@pytest.mark.parametrize("text", [QUESTION, PLAIN_LONG])
async def test_long_free_text_reaches_the_guide(
    harness: Callable[[], Harness],  # noqa: F811
    state: SessionStateEnum,
    text: str,
) -> None:
    h = harness()
    await _at(h, state)
    out = await h.say(text)
    assert out
    assert UNCLEAR not in texts(out)
    ctx = await h.ctx()
    assert ctx.current_state == state  # the step is kept, the question is a side trip


async def test_help_still_shows_the_menu_and_short_noise_is_still_unclear(
    harness: Callable[[], Harness],  # noqa: F811
) -> None:
    h = harness()
    await _at(h, SessionStateEnum.TRY_IN_CLASS)
    help_out = texts(await h.say("help"))
    assert help_out and UNCLEAR not in help_out
    assert UNCLEAR in texts(await h.say("हम्म ठीक"))  # fewer than 4 words stays "unclear"
