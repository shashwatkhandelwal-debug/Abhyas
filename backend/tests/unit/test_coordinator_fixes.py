"""Tests for the 6 review feedback items from Coordinator."""

from backend.app.rule_engine.bugs.literacy import read_correct
from backend.app.rule_engine.bugs.subtraction import sub_correct
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


# 1. Correct subtraction steps units step
def test_subtraction_scaffolded_correct_units_step() -> None:
    """For 43-27 correct steps must include units subtraction (13 - 7 = 6).

    allowed_numbers for SCAFFOLDED_CORRECT on 43-27 must contain 6 and 13.
    """
    prob = Problem(type="sub", a=43, b=27)
    out = sub_correct(prob)
    step_codes = [s.code for s in out.steps]
    assert "SUB_CANNOT" in step_codes
    assert "REGROUP_OPEN_BUNDLE" in step_codes
    assert "SUB_UNITS_NORMAL" in step_codes
    assert "SUB_TENS" in step_codes
    assert "ANSWER" in step_codes

    # Find SUB_UNITS_NORMAL step
    units_step = next(s for s in out.steps if s.code == "SUB_UNITS_NORMAL")
    assert 13 in units_step.nums
    assert 7 in units_step.nums
    assert 6 in units_step.nums
    assert "13 में से 7 घटाया, 6 आया" in units_step.text_hi

    # Also verify via RuleEngine scaffolded_correct turn
    scene = SceneState(
        move_id="M1",
        domain=Domain.NUMERACY,
        effective_acts=[TeachingAct.CONCRETE_REPRESENTATION],
        target_causes=["SUB_SMALLER_FROM_LARGER"],
        items=[prob],
        current_item=prob,
        children=[
            ChildRuntime(
                persona_id="ravi",
                misconception="SUB_SMALLER_FROM_LARGER",
                temperament="confident",
                state=ChildState.CAN_EXPLAIN,
            )
        ],
    )
    t = TaggedTurn(acts=[TeachingAct.CONCRETE_REPRESENTATION], addressed_child="ravi")
    res = RuleEngine.step(scene, t)
    assert res.responses[0].kind == ResponseKind.SCAFFOLDED_CORRECT
    assert 6 in res.responses[0].allowed_numbers
    assert 13 in res.responses[0].allowed_numbers


# 2. No chaining within one turn
def test_no_chaining_within_one_turn_all_addressed() -> None:
    """addressed 'all' + [concrete_representation, contrast_answers] on MISCONCEPTION -> PARTIAL (not CORRECT)."""
    scene = SceneState(
        move_id="M1",
        domain=Domain.NUMERACY,
        effective_acts=[TeachingAct.CONCRETE_REPRESENTATION, TeachingAct.CONTRAST_TWO_ANSWERS],
        target_causes=["SUB_SMALLER_FROM_LARGER"],
        items=[Problem(type="sub", a=52, b=17)],
        current_item=Problem(type="sub", a=52, b=17),
        children=[
            ChildRuntime(
                persona_id="ravi",
                misconception="SUB_SMALLER_FROM_LARGER",
                temperament="confident",
                state=ChildState.MISCONCEPTION,
            ),
            ChildRuntime(
                persona_id="priya",
                misconception="SUB_SMALLER_FROM_LARGER",
                temperament="shy",
                state=ChildState.MISCONCEPTION,
            ),
        ],
    )
    t = TaggedTurn(
        acts=[TeachingAct.CONCRETE_REPRESENTATION, TeachingAct.CONTRAST_TWO_ANSWERS],
        addressed_child="all",
    )
    RuleEngine.step(scene, t)
    for c in scene.children:
        # Both must stop at PARTIAL; neither must chain to CORRECT in one turn
        assert c.state == ChildState.PARTIAL


def test_no_chaining_place_value_turn_3() -> None:
    """Place-value turn with [model_step_aloud, concrete_representation] to all leaves CAN_EXPLAIN at PARTIAL."""
    scene = SceneState(
        move_id="PV_MOVE",
        domain=Domain.NUMERACY,
        effective_acts=[TeachingAct.CONCRETE_REPRESENTATION, TeachingAct.MODEL_STEP_ALOUD],
        target_causes=["PV_BUNDLE_AS_ONE"],
        items=[Problem(type="place_value", tens=4, ones=7)],
        current_item=Problem(type="place_value", tens=4, ones=7),
        children=[
            ChildRuntime(
                persona_id="ravi",
                misconception="PV_BUNDLE_AS_ONE",
                temperament="confident",
                state=ChildState.CAN_EXPLAIN,
            ),
        ],
    )
    t = TaggedTurn(
        acts=[TeachingAct.MODEL_STEP_ALOUD, TeachingAct.CONCRETE_REPRESENTATION],
        addressed_child="all",
    )
    RuleEngine.step(scene, t)
    assert scene.children[0].state == ChildState.PARTIAL


# 3. Turn limit enforced on every return path
def test_turn_limit_enforced_on_silent_early_return() -> None:
    """7 turns + 8th turn that produces SILENT -> ended=True, end_reason='turn_limit'."""
    priya = ChildRuntime(
        persona_id="priya",
        misconception="SUB_SMALLER_FROM_LARGER",
        temperament="shy",
        state=ChildState.MISCONCEPTION,
        silent_turns=2,
    )
    scene = SceneState(
        move_id="M1",
        domain=Domain.NUMERACY,
        effective_acts=[TeachingAct.ASK_TO_EXPLAIN],
        target_causes=["SUB_SMALLER_FROM_LARGER"],
        items=[Problem(type="sub", a=52, b=17)],
        current_item=Problem(type="sub", a=52, b=17),
        children=[priya],
        teacher_turns=7,
        max_turns=8,
    )
    t = TaggedTurn(acts=[TeachingAct.REPEAT_QUESTION], addressed_child="priya")
    res = RuleEngine.step(scene, t)
    assert res.responses[0].kind == ResponseKind.SILENT
    assert res.ended is True
    assert res.end_reason == "turn_limit"
    assert scene.ended is True
    assert scene.end_reason == "turn_limit"


def test_turn_limit_enforced_on_confused_early_return() -> None:
    """7 turns + 8th turn with invalid problem (CONFUSED) -> ended=True, end_reason='turn_limit'."""
    scene = SceneState(
        move_id="M1",
        domain=Domain.NUMERACY,
        effective_acts=[TeachingAct.ASK_TO_EXPLAIN],
        target_causes=["SUB_SMALLER_FROM_LARGER"],
        items=[Problem(type="sub", a=52, b=17)],
        current_item=Problem(type="sub", a=52, b=17),
        children=[
            ChildRuntime(
                persona_id="ravi",
                misconception="SUB_SMALLER_FROM_LARGER",
                temperament="confident",
                state=ChildState.MISCONCEPTION,
            )
        ],
        teacher_turns=7,
        max_turns=8,
    )
    t = TaggedTurn(acts=[], addressed_child="ravi", problem=Problem(type="sub", a=5, b=2))
    res = RuleEngine.step(scene, t)
    assert res.responses[0].kind == ResponseKind.CONFUSED
    assert res.ended is True
    assert res.end_reason == "turn_limit"


# 4. guess_lexicon in SceneState
def test_scene_state_guess_lexicon() -> None:
    """Custom guess_lexicon on SceneState is used by rule engine."""
    scene = SceneState(
        move_id="LIT_MOVE",
        domain=Domain.LITERACY,
        effective_acts=[TeachingAct.PHONICS_SOUND_OUT],
        target_causes=["FIRST_AKSHAR_GUESS"],
        items=[Problem(type="read_word", word="मटर")],
        current_item=Problem(type="read_word", word="मटर"),
        children=[
            ChildRuntime(
                persona_id="ravi",
                misconception="FIRST_AKSHAR_GUESS",
                temperament="confident",
                state=ChildState.MISCONCEPTION,
            )
        ],
        guess_lexicon={"म": ["मकान"]},
    )
    t = TaggedTurn(acts=[], addressed_child="ravi")
    res = RuleEngine.step(scene, t)
    assert res.responses[0].answer == "मकान"


# 5. Correct reading steps
def test_read_correct_steps() -> None:
    """READ_AKSHARS renders aksharas joined with ' - ', words=aksharas, then ANSWER."""
    out_mela = read_correct(Problem(type="read_word", word="मेला"))
    assert len(out_mela.steps) == 2
    assert out_mela.steps[0].code == "READ_AKSHARS"
    assert out_mela.steps[0].text_hi == "मे - ला"
    assert out_mela.steps[0].words == ["मे", "ला"]
    assert out_mela.steps[1].code == "ANSWER"
    assert out_mela.steps[1].text_hi == "मेला"

    out_kitab = read_correct(Problem(type="read_word", word="किताब"))
    assert out_kitab.steps[0].code == "READ_AKSHARS"
    assert out_kitab.steps[0].text_hi == "कि - ता - ब"
    assert out_kitab.steps[0].words == ["कि", "ता", "ब"]
    assert out_kitab.steps[1].code == "ANSWER"
    assert out_kitab.steps[1].text_hi == "किताब"
