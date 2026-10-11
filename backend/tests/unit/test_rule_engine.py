"""Unit tests for the Deterministic Rule Engine (§5.2, Milestone M2)."""

from backend.app.rule_engine.child_state import ChildState
from backend.app.rule_engine.domain import (
    KeyPoint,
    Move,
    Persona,
    Rubric,
    Scenario,
    SourceRef,
    TeachingAct,
)
from backend.app.rule_engine.engine import RehearsalRuleEngine
from backend.app.rule_engine.misconceptions import sub_smaller_from_larger


def create_sample_place_value_move() -> Move:
    from backend.app.content_models import FeedbackItem, MoveStatus, RubricCriterion, ScenarioChild

    return Move(
        id="NUM_BUNDLES_PLACE_VALUE",
        version=1,
        status=MoveStatus.APPROVED,
        domain="numeracy",
        grade=[2],
        title_hi="बंडल और तीली से हासिल का घटाव",
        summary_hi="बंडल और तीली से हासिल का घटाव सिखाना",
        module_ref=SourceRef(source_id="UP FLN Ganit Sandarshika", section="Adhyay 4"),
        sankul_month="October",
        key_points=[
            KeyPoint(id="kp1", text_hi="दहाई को बंडल बनाकर खोलना समझाना", must_have=True),
        ],
        teaching_acts_effective=[
            "ask_to_explain",
            "concrete_representation",
            "contrast_answers",
        ],
        target_causes=["SUB_SMALLER_FROM_LARGER"],
        rubric=Rubric(
            criteria=[
                RubricCriterion(
                    id="crit1",
                    text_hi="बंडल का उपयोग",
                    levels={0: "नहीं किया", 1: "आंशिक", 2: "पूर्ण"},
                )
            ]
        ),
        feedback_bank={
            "crit1": FeedbackItem(
                strength_hi="आपने बंडल का उपयोग किया।",
                change_hi="अगली बार तीली भी गिनवाएँ।",
                exact_words_hi="10 का बंडल खोलकर देखो।",
            )
        },
        learn_script_hi="दो मिनट का ऑडियो",
        learn_summary_hi=["दहाई खोलना"],
        model_rehearsal=[],
        scenario=Scenario(
            intro_hi="52 - 17 का अभ्यास",
            items=[{"question": "52 - 17", "expected_correct": 35}],
            children=[ScenarioChild(persona_id="ravi", misconception="SUB_SMALLER_FROM_LARGER")],
        ),
        peer_checklist=["क्या शिक्षक ने तीली-बंडल का उपयोग किया?"],
        reflection_questions=["बच्चों को कहाँ कठिनाई हुई?"],
    )


def test_sub_smaller_from_larger_computation():
    """Verify procedural bug math computation for 52 - 17 = 45."""
    res = sub_smaller_from_larger(52, 17)
    assert res["answer"] == 45
    assert 45 in res["numbers_involved"]
    assert 2 in res["numbers_involved"]
    assert 7 in res["numbers_involved"]


def test_ravi_worked_example_acceptance_criteria():
    """Verifies §5.2 Worked Example: Ravi with SUB_SMALLER_FROM_LARGER.

    1. Initial state: MISCONCEPTION (computes 45)
    2. Teacher says 'ask_to_explain' -> moves to CAN_EXPLAIN
    3. Teacher provides 'concrete_representation' -> moves to PARTIAL
    """
    move = create_sample_place_value_move()
    engine = RehearsalRuleEngine(move)

    ravi = Persona(
        id="ravi",
        name="रवि",
        grade=2,
        voice_id="child_boy_1",
        misconceptions=["SUB_SMALLER_FROM_LARGER"],
        temperament="confident",
        speech_style_hi="सीधा और उत्साही",
    )

    # Step 1: Initial error turn with ask_to_explain
    result_1 = engine.evaluate_turn(
        child=ravi,
        current_state=ChildState.MISCONCEPTION,
        acts=[TeachingAct.ASK_TO_EXPLAIN],
        problem_args=(52, 17),
        correct_answer=35,
    )
    assert result_1.prior_state == ChildState.MISCONCEPTION
    assert result_1.new_state == ChildState.CAN_EXPLAIN
    assert result_1.answer == 45
    assert 45 in result_1.numbers_involved

    # Step 2: Teacher applies concrete representation
    result_2 = engine.evaluate_turn(
        child=ravi,
        current_state=result_1.new_state,
        acts=[TeachingAct.CONCRETE_REPRESENTATION],
        problem_args=(52, 17),
        correct_answer=35,
    )
    assert result_2.prior_state == ChildState.CAN_EXPLAIN
    assert result_2.new_state == ChildState.PARTIAL
    assert result_2.answer == 35


def test_relapse_after_tell_answer():
    """Verifies §5.2 and Milestone M2:

    'Telling the answer yields a correct echo followed by the same bug on the next item.'
    """
    move = create_sample_place_value_move()
    engine = RehearsalRuleEngine(move)

    ravi = Persona(
        id="ravi",
        name="रवि",
        grade=2,
        voice_id="child_boy_1",
        misconceptions=["SUB_SMALLER_FROM_LARGER"],
        temperament="confident",
        speech_style_hi="सीधा और उत्साही",
    )

    # Teacher just tells the answer
    result_told = engine.evaluate_turn(
        child=ravi,
        current_state=ChildState.MISCONCEPTION,
        acts=[TeachingAct.TELL_ANSWER],
        problem_args=(52, 17),
        correct_answer=35,
    )
    assert result_told.is_parrot is True
    assert result_told.answer == 35
    assert result_told.new_state == ChildState.MISCONCEPTION  # State not advanced

    # On next item (e.g., 43 - 27), child relapses with same procedural bug
    result_next = engine.evaluate_turn(
        child=ravi,
        current_state=result_told.new_state,
        acts=[TeachingAct.REPEAT_QUESTION],
        problem_args=(43, 27),
        correct_answer=16,
    )
    # 43 - 27 with SUB_SMALLER_FROM_LARGER: units 7 - 3 = 4, tens 4 - 2 = 2 -> 24
    assert result_next.answer == 24
    assert result_next.new_state == ChildState.MISCONCEPTION
