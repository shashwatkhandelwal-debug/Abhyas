"""fix5 item 4: the wrong answer is stable; a new problem written with any minus sign is attempted."""

from __future__ import annotations

import pytest

from backend.app.llm.roles.act_tagger import _with_posed_problem, detect_problem_in_fallback
from backend.app.llm.schemas import ActTaggerOutput
from backend.app.rule_engine.domain import (
    ChildRuntime,
    ChildState,
    Domain,
    Problem,
    ResponseKind,
    SceneState,
    TaggedTurn,
    TeachingAct,
)
from backend.app.rule_engine.engine import RuleEngine

A = TeachingAct
BUG = "SUB_SMALLER_FROM_LARGER"


def _scene(item: Problem, state: ChildState = ChildState.MISCONCEPTION) -> SceneState:
    return SceneState(
        move_id="NUM_SUB_REGROUP_BUNDLES",
        domain=Domain.NUMERACY,
        effective_acts=[A.CONCRETE_REPRESENTATION, A.CONTRAST_TWO_ANSWERS, A.ASK_TO_EXPLAIN],
        target_causes=[BUG],
        items=[item],
        current_item=item,
        one_on_one=True,
        children=[
            ChildRuntime(persona_id="ravi", misconception=BUG, temperament="confident", state=state)
        ],
    )


@pytest.mark.parametrize(
    "text",
    [
        "अब 52 - 17 करो",
        "अब 52 − 17 करो",
        "अब 52 – 17 करो",
        "52—17",
        "नया सवाल: 52 घटा 17",
        "52 से 17 घटाओ",
    ],
)
def test_new_problem_is_found_with_every_minus_sign(text: str) -> None:
    got = detect_problem_in_fallback(text, Problem(type="sub", a=43, b=27))
    assert got is not None and (got.a, got.b) == (52, 17)


def test_a_problem_the_llm_tagger_missed_is_taken_from_the_text() -> None:
    parsed = ActTaggerOutput(acts=[A.REPEAT_QUESTION], addressed_child=None, problem=None)
    out = _with_posed_problem(parsed, "अब 52 − 17 करो", Problem(type="sub", a=43, b=27))
    assert out.problem is not None and (out.problem.a, out.problem.b) == (52, 17)
    assert A.GIVE_NEW_PROBLEM in out.acts
    keep = ActTaggerOutput(acts=[A.ASK_TO_EXPLAIN], addressed_child=None, problem=None)
    assert _with_posed_problem(keep, "तुमने कैसे किया?", Problem(type="sub", a=43, b=27)) == keep


def test_wrong_answer_is_the_same_on_every_turn_that_does_not_teach() -> None:
    scene = _scene(Problem(type="sub", a=52, b=17))
    answers = []
    for acts in ([A.REPEAT_QUESTION], [A.PRAISE_EFFORT], [A.REPEAT_QUESTION]):
        res = RuleEngine.step(scene, TaggedTurn(acts=acts, addressed_child="ravi"))
        assert res.responses[0].kind == ResponseKind.ANSWER
        answers.append(res.responses[0].answer)
    assert answers == [45, 45, 45]  # 35 is the right answer; he gives it only once taught or told


def test_new_problem_after_the_bundle_explanation_is_attempted_not_restated() -> None:
    scene = _scene(Problem(type="sub", a=43, b=27), ChildState.CORRECT)
    res = RuleEngine.step(
        scene,
        TaggedTurn(
            acts=[A.GIVE_NEW_PROBLEM],
            addressed_child="ravi",
            problem=Problem(type="sub", a=52, b=17),
        ),
    )
    r = res.responses[0]
    assert r.item.key() == Problem(type="sub", a=52, b=17).key()
    assert r.answer == 35  # taught: the new problem is solved on the new numbers, not "16" again
