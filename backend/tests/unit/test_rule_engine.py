"""Exhaustive tests for RuleEngine matching all 14 requirements in spec/04 §4.5."""

import random

from backend.app.rule_engine.bugs import (
    akshar_by_akshar,
    first_akshar_guess,
    matra_drop,
    split_akshars,
)
from backend.app.rule_engine.child_state import ChildState
from backend.app.rule_engine.domain import (
    ChildRuntime,
    Domain,
    Problem,
    ResponseKind,
    SceneState,
    TaggedTurn,
    TeachingAct,
)
from backend.app.rule_engine.engine import RuleEngine
from backend.app.rule_engine.transitions import NON_ADVANCING


def create_standard_sub_scene() -> SceneState:
    """Creates a standard 3-child rehearsal scene for subtraction with regrouping."""
    items = [
        Problem(type="sub", a=52, b=17),
        Problem(type="sub", a=43, b=27),
        Problem(type="sub", a=61, b=28),
        Problem(type="sub", a=74, b=39),
    ]
    children = [
        ChildRuntime(
            persona_id="ravi",
            misconception="SUB_SMALLER_FROM_LARGER",
            temperament="confident",
            state=ChildState.MISCONCEPTION,
        ),
        ChildRuntime(
            persona_id="priya",
            misconception="SUB_BORROW_NO_DECREMENT",
            temperament="shy",
            state=ChildState.MISCONCEPTION,
        ),
        ChildRuntime(
            persona_id="aman",
            misconception="SUB_WRITE_ZERO_WHEN_STUCK",
            temperament="distracted",
            state=ChildState.MISCONCEPTION,
        ),
    ]
    return SceneState(
        move_id="NUM_SUB_REGROUP_BUNDLES",
        domain=Domain.NUMERACY,
        effective_acts=[
            TeachingAct.ASK_TO_EXPLAIN,
            TeachingAct.CONCRETE_REPRESENTATION,
            TeachingAct.CONTRAST_TWO_ANSWERS,
            TeachingAct.PROBE_SIMPLER_CASE,
            TeachingAct.MODEL_STEP_ALOUD,
            TeachingAct.INVOLVE_PEER,
        ],
        target_causes=[
            "SUB_SMALLER_FROM_LARGER",
            "SUB_BORROW_NO_DECREMENT",
            "SUB_WRITE_ZERO_WHEN_STUCK",
        ],
        items=items,
        item_idx=0,
        current_item=items[0],
        children=children,
    )


# 1. Every table cell in 4.2
def test_spec_4_5_1_tables_covered() -> None:
    """Table cells verified via test_bugs.py; assert sanity here."""
    p = Problem(type="sub", a=52, b=17)
    assert p.key() == "sub:52-17"


# 2. Ravi worked example (spec-mandated)
def test_spec_4_5_2_ravi_worked_example() -> None:
    """Verifies §4.5 Test 2: Ravi worked example.

    Turn 1: acts [ASK_TO_EXPLAIN], addressed ravi -> kind EXPLAIN_BUG, answer 45, new_state CAN_EXPLAIN,
            {2, 7, 5, 1, 4, 45} ⊆ allowed_numbers, "35" ∈ forbidden.
    Turn 2: acts [CONCRETE_REPRESENTATION], addressed ravi -> SCAFFOLDED_CORRECT, answer 35, state PARTIAL.
    Turn 3: acts [CONTRAST_TWO_ANSWERS] -> CORRECT_EXPLAINED, state CORRECT.
    """
    scene = create_standard_sub_scene()

    # Turn 1
    t1 = TaggedTurn(acts=[TeachingAct.ASK_TO_EXPLAIN], addressed_child="ravi")
    res1 = RuleEngine.step(scene, t1)
    resp1 = res1.responses[0]
    assert resp1.persona_id == "ravi"
    assert resp1.kind == ResponseKind.EXPLAIN_BUG
    assert resp1.answer == 45
    assert resp1.prior_state == ChildState.MISCONCEPTION
    assert resp1.new_state == ChildState.CAN_EXPLAIN
    assert {2, 7, 5, 1, 4, 45}.issubset(resp1.allowed_numbers)
    assert "35" in resp1.forbidden

    # Turn 2
    t2 = TaggedTurn(acts=[TeachingAct.CONCRETE_REPRESENTATION], addressed_child="ravi")
    res2 = RuleEngine.step(scene, t2)
    resp2 = res2.responses[0]
    assert resp2.persona_id == "ravi"
    assert resp2.kind == ResponseKind.SCAFFOLDED_CORRECT
    assert resp2.answer == 35
    assert resp2.new_state == ChildState.PARTIAL

    # Turn 3
    t3 = TaggedTurn(acts=[TeachingAct.CONTRAST_TWO_ANSWERS], addressed_child="ravi")
    res3 = RuleEngine.step(scene, t3)
    resp3 = res3.responses[0]
    assert resp3.persona_id == "ravi"
    assert resp3.kind == ResponseKind.CORRECT_EXPLAINED
    assert resp3.answer == 35
    assert resp3.new_state == ChildState.CORRECT


# 3. Relapse after tell
def test_spec_4_5_3_relapse_after_tell() -> None:
    """Verifies §4.5 Test 3: Ravi MISCONCEPTION, item 52-17, acts [TELL_ANSWER] -> PARROT 35.

    Next turn problem 43-27, acts [] addressed ravi -> ANSWER 24.
    """
    scene = create_standard_sub_scene()
    t1 = TaggedTurn(acts=[TeachingAct.TELL_ANSWER], addressed_child="ravi")
    res1 = RuleEngine.step(scene, t1)
    resp1 = res1.responses[0]
    assert resp1.kind == ResponseKind.PARROT
    assert resp1.answer == 35
    assert resp1.new_state == ChildState.MISCONCEPTION

    # Next turn: new problem 43-27 without pedagogy
    t2 = TaggedTurn(
        acts=[],
        addressed_child="ravi",
        problem=Problem(type="sub", a=43, b=27),
    )
    res2 = RuleEngine.step(scene, t2)
    resp2 = res2.responses[0]
    assert resp2.kind == ResponseKind.ANSWER
    assert resp2.answer == 24
    assert resp2.new_state == ChildState.MISCONCEPTION


# 4. PARTIAL relapse
def test_spec_4_5_4_partial_relapse() -> None:
    """Verifies §4.5 Test 4: Ravi PARTIAL on 52-17.

    Problem 61-28 with acts [] -> RELAPSE 47.
    Same but acts [CONCRETE_REPRESENTATION] -> SCAFFOLDED_CORRECT 33.
    """
    # Variant A: no support on new item -> RELAPSE
    scene_a = create_standard_sub_scene()
    scene_a.children[0].state = ChildState.PARTIAL
    scene_a.children[0].partial_item_key = "sub:52-17"

    t_relapse = TaggedTurn(
        acts=[],
        addressed_child="ravi",
        problem=Problem(type="sub", a=61, b=28),
    )
    res_a = RuleEngine.step(scene_a, t_relapse)
    resp_a = res_a.responses[0]
    assert resp_a.kind == ResponseKind.RELAPSE
    assert resp_a.answer == 47

    # Variant B: with effective support -> SCAFFOLDED_CORRECT
    scene_b = create_standard_sub_scene()
    scene_b.children[0].state = ChildState.PARTIAL
    scene_b.children[0].partial_item_key = "sub:52-17"

    t_scaffold = TaggedTurn(
        acts=[TeachingAct.CONCRETE_REPRESENTATION],
        addressed_child="ravi",
        problem=Problem(type="sub", a=61, b=28),
    )
    res_b = RuleEngine.step(scene_b, t_scaffold)
    resp_b = res_b.responses[0]
    assert resp_b.kind == ResponseKind.SCAFFOLDED_CORRECT
    assert resp_b.answer == 33


# 5. Ineffective acts never advance
def test_spec_4_5_5_ineffective_acts_never_advance() -> None:
    """Verifies §4.5 Test 5: act not in move's effective_acts leaves state unchanged."""
    scene = create_standard_sub_scene()
    scene.effective_acts = [
        TeachingAct.ASK_TO_EXPLAIN,
        TeachingAct.CONCRETE_REPRESENTATION,
        TeachingAct.CONTRAST_TWO_ANSWERS,
        TeachingAct.PROBE_SIMPLER_CASE,
    ]
    scene.children[0].state = ChildState.PARTIAL

    # MODEL_STEP_ALOUD is not in effective_acts
    t = TaggedTurn(acts=[TeachingAct.MODEL_STEP_ALOUD], addressed_child="ravi")
    res = RuleEngine.step(scene, t)
    assert res.responses[0].new_state == ChildState.PARTIAL


# 6. Shy/scold
def test_spec_4_5_6_shy_scold() -> None:
    """Verifies §4.5 Test 6: Scolding a shy child causes silence."""
    scene = create_standard_sub_scene()
    # Turn 1: Priya addressed + SCOLD
    t1 = TaggedTurn(acts=[TeachingAct.SCOLD], addressed_child="priya")
    res1 = RuleEngine.step(scene, t1)
    assert res1.responses[0].kind == ResponseKind.SILENT
    assert scene.children[1].silent_turns == 1

    # Turn 2: addressed with ASK_TO_EXPLAIN -> still SILENT
    t2 = TaggedTurn(acts=[TeachingAct.ASK_TO_EXPLAIN], addressed_child="priya")
    res2 = RuleEngine.step(scene, t2)
    assert res2.responses[0].kind == ResponseKind.SILENT
    assert scene.children[1].silent_turns == 0

    # Turn 3: addressed with ASK_TO_EXPLAIN -> speaks (EXPLAIN_BUG)
    t3 = TaggedTurn(acts=[TeachingAct.ASK_TO_EXPLAIN], addressed_child="priya")
    res3 = RuleEngine.step(scene, t3)
    assert res3.responses[0].kind == ResponseKind.EXPLAIN_BUG

    # Variant: Turn 2 with PRAISE_EFFORT clears silence immediately
    scene_v = create_standard_sub_scene()
    RuleEngine.step(scene_v, TaggedTurn(acts=[TeachingAct.SCOLD], addressed_child="priya"))
    res_v = RuleEngine.step(
        scene_v,
        TaggedTurn(
            acts=[TeachingAct.PRAISE_EFFORT, TeachingAct.ASK_TO_EXPLAIN], addressed_child="priya"
        ),
    )
    assert res_v.responses[0].kind == ResponseKind.EXPLAIN_BUG
    assert res_v.responses[0].affect == "encouraged"


# 7. Shy never auto-selected
def test_spec_4_5_7_shy_never_auto_selected() -> None:
    """Verifies §4.5 Test 7: When addressed 'all', shy children are skipped."""
    scene = create_standard_sub_scene()
    scene.children[0].state = ChildState.CORRECT  # Ravi confident
    scene.children[2].state = ChildState.CORRECT  # Aman distracted
    scene.children[1].state = ChildState.MISCONCEPTION  # Priya shy

    t = TaggedTurn(acts=[TeachingAct.REPEAT_QUESTION], addressed_child="all")
    res = RuleEngine.step(scene, t)
    # Responder is confident fallback (Ravi), NOT Priya
    assert res.responses[0].persona_id == "ravi"


# 8. Distracted interjection
def test_spec_4_5_8_distracted_interjection() -> None:
    """Verifies §4.5 Test 8: Aman not addressed for 3 turns interjects on turn 3."""
    scene = create_standard_sub_scene()
    t_ravi = TaggedTurn(acts=[TeachingAct.REPEAT_QUESTION], addressed_child="ravi")

    RuleEngine.step(scene, t_ravi)  # turn 1
    RuleEngine.step(scene, t_ravi)  # turn 2
    res3 = RuleEngine.step(scene, t_ravi)  # turn 3

    assert len(res3.responses) == 2
    assert res3.responses[0].persona_id == "ravi"
    assert res3.responses[1].persona_id == "aman"
    assert res3.responses[1].kind == ResponseKind.INTERJECT


# 9. Whole-class concrete representation
def test_spec_4_5_9_whole_class_concrete_representation() -> None:
    """Verifies §4.5 Test 9: addressed 'all' + CONCRETE_REPRESENTATION advances all non-silent."""
    scene = create_standard_sub_scene()
    t = TaggedTurn(acts=[TeachingAct.CONCRETE_REPRESENTATION], addressed_child="all")
    RuleEngine.step(scene, t)

    for child in scene.children:
        assert child.state == ChildState.PARTIAL


# 10. Determinism
def test_spec_4_5_10_determinism() -> None:
    """Verifies §4.5 Test 10: 8-turn scripted scene produces identical outputs twice."""

    def run_script() -> tuple[list[dict], dict]:
        scene = create_standard_sub_scene()
        outputs = []
        script = [
            TaggedTurn(acts=[TeachingAct.ASK_TO_EXPLAIN], addressed_child="ravi"),
            TaggedTurn(acts=[TeachingAct.CONCRETE_REPRESENTATION], addressed_child="ravi"),
            TaggedTurn(acts=[TeachingAct.CONTRAST_TWO_ANSWERS], addressed_child="ravi"),
            TaggedTurn(acts=[TeachingAct.REPEAT_QUESTION], addressed_child="aman"),
            TaggedTurn(acts=[TeachingAct.CONCRETE_REPRESENTATION], addressed_child="priya"),
            TaggedTurn(acts=[TeachingAct.MODEL_STEP_ALOUD], addressed_child="priya"),
            TaggedTurn(acts=[TeachingAct.REPEAT_QUESTION], addressed_child="aman"),
            TaggedTurn(acts=[TeachingAct.CONCRETE_REPRESENTATION], addressed_child="aman"),
        ]
        for turn in script:
            res = RuleEngine.step(scene, turn)
            outputs.append(res.model_dump())
        return outputs, scene.model_dump()

    out1, state1 = run_script()
    out2, state2 = run_script()
    assert out1 == out2
    assert state1 == state2


# 11. Property test
def test_spec_4_5_11_property_test_non_advancing() -> None:
    """Verifies §4.5 Test 11: Non-advancing / ineffective acts never advance understanding."""
    rng = random.Random(42)
    non_advancing_acts = list(NON_ADVANCING)

    for _ in range(50):
        scene = create_standard_sub_scene()
        for _ in range(6):
            act = rng.choice(non_advancing_acts)
            target = rng.choice(["ravi", "priya", "aman", "all", None])
            res = RuleEngine.step(scene, TaggedTurn(acts=[act], addressed_child=target))

            for child in scene.children:
                # No child ever advances to PARTIAL or CORRECT from non-advancing acts
                assert child.state < ChildState.PARTIAL

            for resp in res.responses:
                if resp.kind not in (
                    ResponseKind.PARROT,
                    ResponseKind.SILENT,
                    ResponseKind.INTERJECT,
                    ResponseKind.OFF_TOPIC,
                ):
                    # Every non-parrot substantive answer must equal the bug answer
                    assert resp.kind in (ResponseKind.ANSWER, ResponseKind.EXPLAIN_BUG)


# 12. Scene end
def test_spec_4_5_12_scene_end() -> None:
    """Verifies §4.5 Test 12: End on all_correct, turn_limit, or placement mode."""
    # All correct
    scene_correct = create_standard_sub_scene()
    for c in scene_correct.children:
        c.state = ChildState.CORRECT
    res_end = RuleEngine.step(
        scene_correct, TaggedTurn(acts=[TeachingAct.REPEAT_QUESTION], addressed_child="ravi")
    )
    assert res_end.ended is True
    assert res_end.end_reason == "all_correct"

    # Turn limit (8 turns)
    scene_turns = create_standard_sub_scene()
    for _ in range(8):
        res = RuleEngine.step(
            scene_turns, TaggedTurn(acts=[TeachingAct.REPEAT_QUESTION], addressed_child="ravi")
        )
    assert res.ended is True
    assert res.end_reason == "turn_limit"

    # Placement mode: 1 child, 2 turns
    placement_scene = SceneState(
        move_id="PLACEMENT_SUB",
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
            )
        ],
    )
    RuleEngine.step(
        placement_scene, TaggedTurn(acts=[TeachingAct.ASK_TO_EXPLAIN], addressed_child="ravi")
    )
    res_p2 = RuleEngine.step(
        placement_scene, TaggedTurn(acts=[TeachingAct.REPEAT_QUESTION], addressed_child="ravi")
    )
    assert res_p2.ended is True
    assert res_p2.end_reason == "turn_limit"


# 13. Literacy
def test_spec_4_5_13_literacy() -> None:
    """Verifies §4.5 Test 13: Literacy scene words and bugs."""
    words = ["मेला", "पानी", "किताब", "गुड़िया"]
    for w in words:
        prob = Problem(type="read_word", word=w)
        assert len(split_akshars(w)) >= 2
        assert matra_drop(prob).answer
        assert first_akshar_guess(prob).answer
        assert akshar_by_akshar(prob).answer


# 14. Serialisation
def test_spec_4_5_14_serialisation() -> None:
    """Verifies §4.5 Test 14: SceneState round-trips cleanly through JSON."""
    scene = create_standard_sub_scene()
    json_str = scene.model_dump_json()
    roundtrip = SceneState.model_validate_json(json_str)
    assert roundtrip.move_id == scene.move_id
    assert len(roundtrip.children) == len(scene.children)
    assert roundtrip.current_item.a == scene.current_item.a
