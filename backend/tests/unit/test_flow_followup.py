"""F1: the follow-up with a lead-in, shown before the scene, ending in a next step (mocks only).

The scene is the real one (rule engine on the in-memory store); the act tagger is scripted. The
follow-up is offered by `offer_followup` exactly as the chat page does when she opens it.
"""

# ruff: noqa: F811  (the harness fixture is reused by name)
from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from test_one_on_one_flow import Harness, harness  # noqa: F401
from test_state_machine import FakeSessionRepository  # noqa: F401

from backend.app.class_profile import followup
from backend.app.config import settings
from backend.app.core.messages import get_message, reset_ui_lang, set_ui_lang
from backend.app.core.types import OutboundMessage
from backend.app.rule_engine.domain import TeachingAct
from backend.app.sessions.state_machine import SessionStateEnum

IST = ZoneInfo("Asia/Kolkata")
TODAY = date(2026, 10, 30)
MODULE = "NUM_SUB_REGROUP_BUNDLES"
STRUGGLE = "NUM_SUB_REGROUP"
A = TeachingAct


@pytest.fixture(autouse=True)
def flags(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "CLASS_CHECKIN_ENABLED", True)
    monkeypatch.setattr(settings, "FOLLOWUP_ENABLED", True)
    monkeypatch.setattr(settings, "LEVEL_SORTER_ENABLED", True)
    monkeypatch.setattr(settings, "DEMO_MODE", False)
    moment = datetime(2026, 10, 30, 10, 0, tzinfo=IST).astimezone(UTC)
    monkeypatch.setattr(followup, "utcnow", lambda: moment)


@pytest.fixture(params=["hi", "en"])
def lang(request: pytest.FixtureRequest) -> Iterator[str]:
    token = set_ui_lang(request.param)
    yield request.param
    reset_ui_lang(token)


def repo_of(h: Harness) -> Any:
    return h.service.repo


async def due_followup(h: Harness, outcome: str = "most", struggle: str = STRUGGLE) -> Any:
    repo = repo_of(h)
    chk = await repo.record_class_checkin(h.teacher_id, MODULE, outcome, [struggle])
    return await repo.create_followup(h.teacher_id, chk.id, struggle, TODAY)


def texts_of(out: list[OutboundMessage]) -> str:
    return "\n".join(m.text_hi or "" for m in out)


def button_ids(out: list[OutboundMessage]) -> list[str]:
    return [b.id for m in out for b in m.buttons]


async def land_in_scene(h: Harness) -> None:
    await h.setup(MODULE, "ravi", "उल्टा घटा दिया")


@pytest.mark.asyncio
async def test_landing_in_a_scene_shows_the_lead_in_first_and_the_scene_is_untouched(
    harness: Callable[[], Harness], lang: str
) -> None:
    h = harness()
    await land_in_scene(h)
    await due_followup(h)
    turns_before = (await h.scene()).scene_state.teacher_turns
    out = await h.service.offer_followup(h.teacher_id)
    assert len(out) == 1
    text = out[0].text_hi or ""
    module = get_message(f"btn_chk_mod_{MODULE}")
    assert module in text
    assert get_message("fu_leadin_most") in text
    assert button_ids(out) == [followup.BTN_WORKED, followup.BTN_STUCK, followup.BTN_CANT]
    assert (await h.scene()).scene_state.teacher_turns == turns_before == 0


@pytest.mark.asyncio
async def test_lead_in_uses_the_stored_outcome(harness: Callable[[], Harness], lang: str) -> None:
    h = harness()
    await land_in_scene(h)
    await due_followup(h, outcome="some")
    out = await h.service.offer_followup(h.teacher_id)
    assert get_message("fu_leadin_some") in (out[0].text_hi or "")


@pytest.mark.asyncio
@pytest.mark.parametrize("scene", [True, False])
@pytest.mark.parametrize(
    "path", ["worked", "stuck", "cant_time", "cant_multigrade", "cant_absent", "cant_other"]
)
async def test_every_answer_ends_with_a_next_step_and_a_button(
    harness: Callable[[], Harness], lang: str, path: str, scene: bool
) -> None:
    h = harness()
    if scene:
        await land_in_scene(h)
    else:
        await h.start(MODULE)
        ctx = await h.ctx()
        ctx.current_state = SessionStateEnum.DONE
        await h.service._sync_context_to_db(ctx, h.teacher_id)
    await due_followup(h)
    await h.service.offer_followup(h.teacher_id)
    if path == "worked":
        out = await h.say(button=followup.BTN_WORKED)
    elif path == "stuck":
        out = await h.say(button=followup.BTN_STUCK)
    else:
        out = await h.say(button=followup.BTN_CANT)
        assert button_ids(out) == [f"{followup.WHY_PREFIX}{r}" for r in followup.REASONS]
        out = await h.say(button=f"{followup.WHY_PREFIX}{path.split('_')[1]}")
    assert out and out[-1].buttons, "the answer must not be a dead end"
    if scene:
        assert out[-1].buttons[0].id == followup.BTN_BACK
        text = out[-1].text_hi or ""
        assert "43 − 27" in text
        assert get_message("speaker_ravi") in text
    for m in out:  # WhatsApp: at most 3 reply buttons, titles within 20 characters
        assert len(m.buttons) <= 4
        assert all(len(b.title_hi) <= 20 for b in m.buttons)
    assert len(out[-1].buttons) <= 3


@pytest.mark.asyncio
async def test_the_back_button_returns_to_the_scene_and_nothing_else_changes(
    harness: Callable[[], Harness], lang: str
) -> None:
    h = harness()
    await land_in_scene(h)
    await due_followup(h)
    await h.service.offer_followup(h.teacher_id)
    await h.say(button=followup.BTN_WORKED)
    before = (await h.scene()).scene_state.teacher_turns
    state_before = (await h.ctx()).current_state
    out = await h.say(button=followup.BTN_BACK)
    assert get_message("speaker_ravi") in texts_of(out)
    assert (await h.scene()).scene_state.teacher_turns == before
    assert (await h.ctx()).current_state == state_before


@pytest.mark.asyncio
async def test_no_second_follow_up_the_same_day(harness: Callable[[], Harness]) -> None:
    h = harness()
    await h.start(MODULE)
    await due_followup(h)
    assert await h.service.offer_followup(h.teacher_id)
    await h.say(button=followup.BTN_WORKED)
    await due_followup(h, outcome="some")  # another due row, still the same day
    assert await h.service.offer_followup(h.teacher_id) == []


@pytest.mark.asyncio
async def test_a_follow_up_is_never_inserted_after_she_has_spoken_in_the_scene(
    harness: Callable[[], Harness],
) -> None:
    h = harness()
    await land_in_scene(h)
    h.script += [([A.ASK_TO_EXPLAIN], None, None)]
    await h.say("तुमने कैसे किया?")
    assert (await h.scene()).scene_state.teacher_turns >= 1
    await due_followup(h)
    assert await h.service.offer_followup(h.teacher_id) == []
    # and it is still due: nothing was marked offered, so it shows once the scene is over
    row = repo_of(h)._followups[-1]
    assert row.offered_at is None


@pytest.mark.asyncio
async def test_a_stuck_answer_in_a_scene_still_returns_to_the_scene(
    harness: Callable[[], Harness], lang: str
) -> None:
    h = harness()
    await land_in_scene(h)
    await due_followup(h)
    await h.service.offer_followup(h.teacher_id)
    out = await h.say(button=followup.BTN_STUCK)
    assert out[-1].buttons[0].id == followup.BTN_BACK
