"""The relapse line names telling the answer only when a tell-answer act really happened."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from test_coach_outcome import NEW, RAVI, run
from test_one_on_one_flow import A, Harness, harness  # noqa: F401  (harness is a fixture)

from backend.app.core.messages import get_message, reset_ui_lang, set_ui_lang
from backend.app.core.pronouns import child_pronouns
from backend.app.rehearsal.scene_store import TurnRecord
from backend.app.rule_engine.domain import ChildResponse, ChildState, Problem, ResponseKind
from backend.app.sessions.outcome import outcome_line

TOLD_KEY = "coach_outcome_relapse"
SCAFFOLD_KEY = "coach_outcome_relapse_scaffold"


def _relapse_turns(acts_first: list[str]) -> list[TurnRecord]:
    relapse = ChildResponse(
        persona_id="ravi",
        kind=ResponseKind.RELAPSE,
        prior_state=ChildState.PARTIAL,
        new_state=ChildState.PARTIAL,
        affect="hesitant",
        item=Problem(type="sub", a=61, b=28),
    )
    return [
        TurnRecord(turn_index=1, transcript="x", acts=acts_first),
        TurnRecord(
            turn_index=2, transcript="y", acts=["give_new_problem"], child_responses=[relapse]
        ),
    ]


@pytest.mark.parametrize("lang", ["hi", "en"])
def test_relapse_after_tell_answer_says_so(lang: str) -> None:
    token = set_ui_lang(lang)
    try:
        line = outcome_line(_relapse_turns(["tell_answer"]), "f")
        assert line == get_message(
            TOLD_KEY, "f", child=get_message("speaker_ravi", "f"), **child_pronouns("ravi")
        )
    finally:
        reset_ui_lang(token)


@pytest.mark.parametrize("lang", ["hi", "en"])
def test_relapse_after_bundles_does_not_claim_tell_answer(lang: str) -> None:
    token = set_ui_lang(lang)
    try:
        line = outcome_line(_relapse_turns(["concrete_representation"]), "f")
        assert line == get_message(
            SCAFFOLD_KEY, "f", child=get_message("speaker_ravi", "f"), **child_pronouns("ravi")
        )
        assert line != get_message(
            TOLD_KEY, "f", child=get_message("speaker_ravi", "f"), **child_pronouns("ravi")
        )
        if lang == "hi":
            assert "उत्तर बताने" not in line
        else:
            assert "telling" not in line.lower() and "told" not in line.lower()
    finally:
        reset_ui_lang(token)


@pytest.mark.asyncio
async def test_real_path_tell_then_new_problem(harness: Callable[[], Harness]) -> None:  # noqa: F811
    text = await run(harness(), [([A.TELL_ANSWER], None, None), ([A.GIVE_NEW_PROBLEM], None, NEW)])
    print("\n--- TELL THEN NEW PROBLEM ---\n" + text)
    assert text.startswith(
        get_message("coach_outcome_told", "f", child=RAVI, **child_pronouns("ravi"))
    )


@pytest.mark.asyncio
async def test_real_path_bundles_then_new_problem(harness: Callable[[], Harness]) -> None:  # noqa: F811
    text = await run(
        harness(),
        [
            ([A.ASK_TO_EXPLAIN], None, None),
            ([A.CONCRETE_REPRESENTATION], None, None),
            ([A.GIVE_NEW_PROBLEM], None, NEW),
        ],
    )
    print("\n--- BUNDLES THEN NEW PROBLEM ---\n" + text)
    assert text.startswith(get_message(SCAFFOLD_KEY, "f", child=RAVI, **child_pronouns("ravi")))
    first = text.splitlines()[0]
    assert "उत्तर बताने" not in first and "उत्तर बता दिया" not in first
