"""The first line of the coach feedback names what happened, from acts and recorded answers only."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from test_one_on_one_flow import A, Harness, harness, texts  # noqa: F401  (harness is a fixture)

from backend.app.core.messages import get_message
from backend.app.rule_engine.domain import ChildState, Problem, ResponseKind

NEW = Problem(type="sub", a=61, b=28)
RAVI = get_message("speaker_ravi")


def advice_bubble(out: list) -> str | None:  # type: ignore[type-arg]
    """The bubble with the coach's advice (strength, change, exact words), if this reply has it."""
    body = [m.text_hi for m in out if m.text_hi and "👍" in m.text_hi]
    return body[0] if body else None


async def run(h: Harness, script: list) -> str:  # type: ignore[type-arg]
    await h.setup("NUM_SUB_REGROUP_BUNDLES", "ravi", "उल्टा घटा दिया, छोटी में से बड़ी")
    h.script += [*script, ([], None, None)]
    for i, _ in enumerate(script):
        found = advice_bubble(await h.say(f"मेरी बात {i + 1}"))  # a new-problem check ends the scene
        if found:
            return found
    found = advice_bubble(await h.say("बस"))
    assert found, "no feedback"
    return found


@pytest.mark.asyncio
async def test_telling_the_answer_is_named_first(harness: Callable[[], Harness]) -> None:  # noqa: F811
    h = harness()
    text = await run(h, [([A.TELL_ANSWER], None, None), ([A.GIVE_NEW_PROBLEM], None, NEW)])
    assert text.startswith(get_message("coach_outcome_told", "f", child=RAVI)), text[:120]
    scene = await h.store.get(next(iter(h.store._scenes)))
    kinds = [r.kind for t in scene.turns for r in t.child_responses]
    assert ResponseKind.PARROT in kinds


@pytest.mark.asyncio
async def test_asking_to_explain_is_named(harness: Callable[[], Harness]) -> None:  # noqa: F811
    text = await run(harness(), [([A.ASK_TO_EXPLAIN], None, None)] * 2)
    assert text.startswith(get_message("coach_outcome_explain", "f", child=RAVI)), text[:120]


@pytest.mark.asyncio
async def test_concrete_material_is_named(harness: Callable[[], Harness]) -> None:  # noqa: F811
    text = await run(
        harness(), [([A.ASK_TO_EXPLAIN], None, None), ([A.CONCRETE_REPRESENTATION], None, None)]
    )
    assert text.startswith(get_message("coach_outcome_concrete", "f", child=RAVI)), text[:120]


@pytest.mark.asyncio
async def test_a_check_on_a_new_problem_is_named(harness: Callable[[], Harness]) -> None:  # noqa: F811
    text = await run(
        harness(),
        [
            ([A.ASK_TO_EXPLAIN], None, None),
            ([A.CONCRETE_REPRESENTATION], None, None),
            ([A.CONTRAST_TWO_ANSWERS], None, None),
            ([A.GIVE_NEW_PROBLEM], None, NEW),
        ],
    )
    assert text.startswith(get_message("coach_outcome_checked", "f", child=RAVI)), text[:120]


@pytest.mark.asyncio
async def test_the_line_is_the_same_whatever_the_coach_model_says(
    harness: Callable[[], Harness],  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Deterministic data: swapping the coach's output changes the advice, not this line, and the
    children's answers are the rule engine's either way."""
    from backend.app.llm.roles import coach as coach_role

    script = [([A.TELL_ANSWER], None, None), ([A.GIVE_NEW_PROBLEM], None, NEW)]
    first = await run(harness(), script)
    real = coach_role.fallback_coach_feedback

    def other(**kw):  # type: ignore[no-untyped-def]
        fb = real(**kw)
        return fb.model_copy(update={"strength_hi": "कुछ और ही बात", "change_hi": "कुछ और बदलाव"})

    monkeypatch.setattr("backend.app.llm.roles.coach.fallback_coach_feedback", other)
    h2 = harness()
    second = await run(h2, script)
    told = get_message("coach_outcome_told", "f", child=RAVI)
    assert first.startswith(told) and second.startswith(told)
    scene = await h2.store.get(next(iter(h2.store._scenes)))
    assert scene.turns[0].child_responses[0].kind == ResponseKind.PARROT
    assert scene.scene_state.children[0].state in (ChildState.MISCONCEPTION, ChildState.PARTIAL)


def test_no_line_when_nothing_stands_out() -> None:
    from backend.app.sessions.outcome import outcome_line

    assert outcome_line([]) == ""


def _scaffolded_turn() -> list:  # type: ignore[type-arg]
    from backend.app.rehearsal.scene_store import TurnRecord
    from backend.app.rule_engine.domain import ChildResponse

    response = ChildResponse(
        persona_id="ravi",
        kind=ResponseKind.SCAFFOLDED_CORRECT,
        prior_state=ChildState.MISCONCEPTION,
        new_state=ChildState.PARTIAL,
        affect="encouraged",
        item=Problem(type="sub", a=43, b=27),
    )
    return [TurnRecord(turn_index=1, transcript="x", acts=[], child_responses=[response])]


def test_a_literacy_scene_never_gets_the_bundles_and_sticks_wording() -> None:
    from backend.app.content_models import Domain
    from backend.app.sessions.outcome import outcome_line

    turns = _scaffolded_turn()
    literacy = outcome_line(turns, "f", Domain.LITERACY)
    assert literacy == get_message("coach_outcome_concrete_literacy", "f", child=RAVI)
    assert "बंडल" not in literacy and "तीलियाँ" not in literacy
    # numeracy (and callers that pass no domain) keep the bundles-and-sticks line
    expected = get_message("coach_outcome_concrete", "f", child=RAVI)
    assert outcome_line(turns, "f", Domain.NUMERACY) == expected
    assert outcome_line(turns, "f") == expected
