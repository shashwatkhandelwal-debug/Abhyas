"""Exhaustive unit tests targeting 100% line and branch coverage of rule_engine/."""

import pytest

from backend.app.rule_engine.bugs import (
    NotApplicable,
    add_carry_forgotten,
    add_carry_wrong_digit,
    add_correct,
    add_no_carry,
    first_akshar_guess,
    get_rule_info,
    pv_correct,
    read_correct,
    split_akshars,
    sub_borrow_no_decrement,
    sub_correct,
    sub_write_zero_when_stuck,
)
from backend.app.rule_engine.child_state import ChildState
from backend.app.rule_engine.domain import (
    ChildRuntime,
    Domain,
    Move,
    Persona,
    Problem,
    ResponseKind,
    SceneState,
    TaggedTurn,
    TeachingAct,
)
from backend.app.rule_engine.engine import (
    RehearsalRuleEngine,
    RuleEngine,
    _select_responder,
    _validate_problem,
)
from backend.app.rule_engine.misconceptions import (
    MISCONCEPTION_REGISTRY,
)
from backend.app.rule_engine.misconceptions import (
    add_no_carry as legacy_add_no_carry,
)
from backend.app.rule_engine.misconceptions import (
    matra_drop as legacy_matra_drop,
)
from backend.app.rule_engine.misconceptions import (
    sub_smaller_from_larger as legacy_sub_smaller_from_larger,
)


def test_domain_problem_keys() -> None:
    """Verify Problem.key() coverage across all problem types."""
    p_sub = Problem(type="sub", a=52, b=17)
    assert p_sub.key() == "sub:52-17"
    p_add = Problem(type="add", a=38, b=45)
    assert p_add.key() == "add:38+45"
    p_pv = Problem(type="place_value", tens=4, ones=7)
    assert p_pv.key() == "pv:4-7"
    p_word = Problem(type="read_word", word="मेला")
    assert p_word.key() == "word:मेला"


def test_akshar_empty() -> None:
    """Verify akshar splitter on empty string."""
    assert split_akshars("") == []


def test_registry_unknown_key() -> None:
    """Verify get_rule_info raises KeyError for unknown rule."""
    with pytest.raises(KeyError):
        get_rule_info("UNKNOWN_BUG_ID")


def test_bugs_missing_operands_and_non_manifesting() -> None:
    """Verify missing operands raise NotApplicable, and single-digit adds/non-regroup subs."""
    with pytest.raises(NotApplicable):
        sub_correct(Problem(type="sub", a=None, b=None))
    with pytest.raises(NotApplicable):
        add_correct(Problem(type="add", a=None, b=None))
    with pytest.raises(NotApplicable):
        pv_correct(Problem(type="place_value", tens=None, ones=None))
    with pytest.raises(NotApplicable):
        read_correct(Problem(type="read_word", word=None))

    # Single-digit addition without carry (s < 10)
    p_add_nocarry = Problem(type="add", a=12, b=23)  # 2+3=5, 1+2=3 -> 35
    assert add_correct(p_add_nocarry).answer == 35
    assert add_no_carry(p_add_nocarry).answer == 35
    assert add_carry_forgotten(p_add_nocarry).answer == 35
    assert add_carry_wrong_digit(p_add_nocarry).answer == 35

    # Subtraction without regrouping (u_top >= u_bot)
    p_sub_noregroup = Problem(type="sub", a=58, b=12)  # 8 >= 2
    assert sub_borrow_no_decrement(p_sub_noregroup).answer == 46
    assert sub_write_zero_when_stuck(p_sub_noregroup).answer == 46

    # Literacy first akshar guess when candidate equals target word -> takes 2nd
    # and when consonant not in default lexicon -> fallback
    p_lex_dup = Problem(type="read_word", word="मछली")
    res_dup = first_akshar_guess(p_lex_dup)
    assert res_dup.answer == "मगर"  # picks second candidate

    p_lex_unknown = Problem(type="read_word", word="हल")
    res_unknown = first_akshar_guess(p_lex_unknown)
    assert res_unknown.answer in ("हल", "हम")


def test_legacy_misconceptions_adapter() -> None:
    """Verify legacy misconceptions.py functions."""
    sub_res = legacy_sub_smaller_from_larger(52, 17)
    assert sub_res["answer"] == 45
    add_res = legacy_add_no_carry(38, 45)
    assert add_res["answer"] == 713
    mat_res = legacy_matra_drop("मेला")
    assert mat_res["answer"] == "मल"
    assert "SUB_SMALLER_FROM_LARGER" in MISCONCEPTION_REGISTRY


def test_legacy_rehearsal_rule_engine_branches() -> None:
    """Verify all branches of legacy RehearsalRuleEngine."""
    move = Move(
        id="NUM_SUB_REGROUP_BUNDLES",
        version=1,
        status="approved",
        domain="numeracy",
        grade=[2],
        title_hi="बंडल और तीली",
        summary_hi="घटाव",
        module_ref={"source_id": "test", "section": "sec"},
        key_points=[],
        teaching_acts_effective=["ask_to_explain", "concrete_representation", "contrast_answers"],
        target_causes=["SUB_SMALLER_FROM_LARGER"],
        rubric={"criteria": []},
        feedback_bank={},
        learn_script_hi="",
        learn_summary_hi=[],
        scenario={"intro_hi": "", "items": [], "children": []},
        model_rehearsal=[],
        peer_checklist=[],
        reflection_questions=[],
    )
    engine = RehearsalRuleEngine(move)

    ravi = Persona(
        id="ravi",
        name="रवि",
        grade=2,
        voice_id="v1",
        misconceptions=["SUB_SMALLER_FROM_LARGER"],
        temperament="confident",
        speech_style_hi="",
    )

    # TELL_ANSWER
    res_tell = engine.evaluate_turn(
        child=ravi,
        current_state=ChildState.MISCONCEPTION,
        acts=[TeachingAct.TELL_ANSWER],
        problem_args=(52, 17),
        correct_answer=35,
    )
    assert res_tell.is_parrot is True
    assert res_tell.affect == "echo"

    # Effective act transition (ASK_TO_EXPLAIN: MISCONCEPTION -> CAN_EXPLAIN)
    res_trans = engine.evaluate_turn(
        child=ravi,
        current_state=ChildState.MISCONCEPTION,
        acts=[TeachingAct.ASK_TO_EXPLAIN],
        problem_args=(52, 17),
        correct_answer=35,
    )
    assert res_trans.new_state == ChildState.CAN_EXPLAIN
    assert res_trans.affect == "explaining"

    # Effective act transition (CONCRETE_REPRESENTATION: CAN_EXPLAIN -> PARTIAL)
    res_partial = engine.evaluate_turn(
        child=ravi,
        current_state=ChildState.CAN_EXPLAIN,
        acts=[TeachingAct.CONCRETE_REPRESENTATION],
        problem_args=(52, 17),
        correct_answer=35,
    )
    assert res_partial.new_state == ChildState.PARTIAL
    assert res_partial.affect == "tentative"

    # Other bug
    other_child = Persona(
        id="aman",
        name="अमन",
        grade=2,
        voice_id="v3",
        misconceptions=["UNKNOWN_BUG"],
        temperament="distracted",
        speech_style_hi="",
    )
    res_other = engine.evaluate_turn(
        child=other_child,
        current_state=ChildState.MISCONCEPTION,
        acts=[TeachingAct.REPEAT_QUESTION],
        problem_args=(52, 17),
        correct_answer=35,
    )
    assert res_other.answer == 35

    # CORRECT state
    res_corr = engine.evaluate_turn(
        child=ravi,
        current_state=ChildState.CORRECT,
        acts=[TeachingAct.REPEAT_QUESTION],
        problem_args=(52, 17),
        correct_answer=35,
    )
    assert res_corr.answer == 35

    # RuleEngineResult.to_dict()
    d = res_corr.to_dict()
    assert d["child_id"] == "ravi"
    assert d["answer"] == 35


def test_engine_validation_branches() -> None:
    """Verify _validate_problem across edge cases in numeracy and literacy."""
    # Numeracy: add valid and invalid
    assert _validate_problem(Problem(type="add", a=38, b=45), Domain.NUMERACY) is True
    assert _validate_problem(Problem(type="add", a=9, b=45), Domain.NUMERACY) is False
    assert _validate_problem(Problem(type="add", a=99, b=105), Domain.NUMERACY) is False
    assert _validate_problem(Problem(type="add", a=99, b=99), Domain.NUMERACY) is True  # 198 <= 199

    # Numeracy: place value valid and invalid
    assert _validate_problem(Problem(type="place_value", tens=4, ones=7), Domain.NUMERACY) is True
    assert _validate_problem(Problem(type="place_value", tens=0, ones=7), Domain.NUMERACY) is False
    assert _validate_problem(Problem(type="place_value", tens=10, ones=7), Domain.NUMERACY) is False
    assert _validate_problem(Problem(type="place_value", tens=4, ones=10), Domain.NUMERACY) is False

    # Numeracy: unsupported type
    assert _validate_problem(Problem(type="read_word", word="मेला"), Domain.NUMERACY) is False

    # Literacy: valid and invalid
    assert _validate_problem(Problem(type="read_word", word="किताब"), Domain.LITERACY) is True
    assert _validate_problem(Problem(type="read_word", word=None), Domain.LITERACY) is False
    assert _validate_problem(Problem(type="sub", a=52, b=17), Domain.LITERACY) is False
    # > 4 akshars
    assert (
        _validate_problem(Problem(type="read_word", word="विश्वविद्यालयीय"), Domain.LITERACY) is False
    )
    # English letters in Devanagari reading
    assert _validate_problem(Problem(type="read_word", word="abc"), Domain.LITERACY) is False


def test_engine_invalid_problem_confused_response() -> None:
    """When teacher presents an invalid problem, responder returns CONFUSED without state change."""
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
    )
    # Teacher gives out-of-scope problem: 5 - 2 (not two-digit)
    t = TaggedTurn(
        acts=[],
        addressed_child="ravi",
        problem=Problem(type="sub", a=5, b=2),
    )
    res = RuleEngine.step(scene, t)
    assert res.responses[0].kind == ResponseKind.CONFUSED
    assert scene.children[0].state == ChildState.MISCONCEPTION


def test_engine_give_new_problem_advance_item() -> None:
    """When GIVE_NEW_PROBLEM is in acts without explicit problem, advances item_idx."""
    p1 = Problem(type="sub", a=52, b=17)
    p2 = Problem(type="sub", a=43, b=27)
    scene = SceneState(
        move_id="M1",
        domain=Domain.NUMERACY,
        effective_acts=[TeachingAct.ASK_TO_EXPLAIN],
        target_causes=["SUB_SMALLER_FROM_LARGER"],
        items=[p1, p2],
        item_idx=0,
        current_item=p1,
        children=[
            ChildRuntime(
                persona_id="ravi",
                misconception="SUB_SMALLER_FROM_LARGER",
                temperament="confident",
            )
        ],
    )
    t = TaggedTurn(acts=[TeachingAct.GIVE_NEW_PROBLEM], problem=None, addressed_child="ravi")
    RuleEngine.step(scene, t)
    assert scene.item_idx == 1
    assert scene.current_item.a == 43


def test_engine_scold_non_shy_child() -> None:
    """When teacher scolds a confident child, affect is upset but does not silence."""
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
            )
        ],
    )
    t = TaggedTurn(acts=[TeachingAct.SCOLD], addressed_child="ravi")
    res = RuleEngine.step(scene, t)
    assert res.responses[0].affect == "upset"
    assert res.responses[0].kind == ResponseKind.ANSWER


def test_engine_involve_peer_advances_listening_can_explain() -> None:
    """When INVOLVE_PEER is used and responder is CORRECT, peer in CAN_EXPLAIN moves to PARTIAL."""
    scene = SceneState(
        move_id="M1",
        domain=Domain.NUMERACY,
        effective_acts=[TeachingAct.INVOLVE_PEER, TeachingAct.CONTRAST_TWO_ANSWERS],
        target_causes=["SUB_SMALLER_FROM_LARGER", "SUB_BORROW_NO_DECREMENT"],
        items=[Problem(type="sub", a=52, b=17)],
        current_item=Problem(type="sub", a=52, b=17),
        children=[
            ChildRuntime(
                persona_id="ravi",
                misconception="SUB_SMALLER_FROM_LARGER",
                temperament="confident",
                state=ChildState.PARTIAL,
            ),
            ChildRuntime(
                persona_id="priya",
                misconception="SUB_BORROW_NO_DECREMENT",
                temperament="shy",
                state=ChildState.CAN_EXPLAIN,
            ),
        ],
    )
    # Turn: Ravi advances to CORRECT, INVOLVE_PEER is in acts
    t = TaggedTurn(
        acts=[TeachingAct.CONTRAST_TWO_ANSWERS, TeachingAct.INVOLVE_PEER], addressed_child="ravi"
    )
    RuleEngine.step(scene, t)
    assert scene.children[0].state == ChildState.CORRECT
    # Priya, who was listening in CAN_EXPLAIN, advances to PARTIAL
    assert scene.children[1].state == ChildState.PARTIAL


def test_select_responder_involve_peer_roster_wrapping() -> None:
    """When INVOLVE_PEER is in acts, picks next child after last_responder in roster order."""
    c1 = ChildRuntime(
        persona_id="ravi", misconception="SUB_SMALLER_FROM_LARGER", temperament="confident"
    )
    c2 = ChildRuntime(
        persona_id="priya",
        misconception="SUB_BORROW_NO_DECREMENT",
        temperament="shy",
        silent_turns=1,
    )
    c3 = ChildRuntime(
        persona_id="aman", misconception="SUB_WRITE_ZERO_WHEN_STUCK", temperament="distracted"
    )

    scene = SceneState(
        move_id="M1",
        domain=Domain.NUMERACY,
        effective_acts=[TeachingAct.INVOLVE_PEER],
        target_causes=["SUB_SMALLER_FROM_LARGER"],
        items=[Problem(type="sub", a=52, b=17)],
        current_item=Problem(type="sub", a=52, b=17),
        children=[c1, c2, c3],
        last_responder="ravi",
    )
    # Next child after ravi is priya, but priya is silent -> skips to aman!
    t = TaggedTurn(acts=[TeachingAct.INVOLVE_PEER], addressed_child=None)
    responder = _select_responder(scene, t)
    assert responder.persona_id == "aman"

    # If all next children are silent:
    c3.silent_turns = 1
    responder_fallback = _select_responder(scene, t)
    assert responder_fallback.persona_id == "priya"  # immediate next in roster order fallback


def test_select_responder_no_confident_fallback() -> None:
    """When no confident child exists and all are CORRECT, falls back to first child."""
    c_distracted = ChildRuntime(
        persona_id="aman",
        misconception="SUB_WRITE_ZERO_WHEN_STUCK",
        temperament="distracted",
        state=ChildState.CORRECT,
    )
    scene = SceneState(
        move_id="M1",
        domain=Domain.NUMERACY,
        effective_acts=[],
        target_causes=[],
        items=[Problem(type="sub", a=52, b=17)],
        current_item=Problem(type="sub", a=52, b=17),
        children=[c_distracted],
    )
    t = TaggedTurn(acts=[], addressed_child=None)
    responder = _select_responder(scene, t)
    assert responder.persona_id == "aman"


def test_literacy_custom_guess_lexicon() -> None:
    """Verify literacy first_akshar_guess uses custom guess_lexicon from context."""
    from backend.app.rule_engine.bugs.literacy import first_akshar_guess

    res = first_akshar_guess(
        Problem(type="read_word", word="मटर"), context={"guess_lexicon": {"म": ["मकान"]}}
    )
    assert res.answer == "मकान"


def test_validate_problem_unknown_domain() -> None:
    """Verify _validate_problem returns False for unsupported domain."""
    assert _validate_problem(Problem(type="add", a=1, b=2), "unknown_domain") is False  # type: ignore[arg-type]


def test_rule_engine_init() -> None:
    """Verify RuleEngine constructor accepts move parameter."""
    engine = RuleEngine(move=None)
    assert engine.move is None


def test_engine_invalid_problem_multi_children() -> None:
    """When teacher presents invalid problem with multiple children, others get turns_since_addressed incremented."""
    scene = SceneState(
        move_id="M1",
        domain=Domain.NUMERACY,
        effective_acts=[],
        target_causes=[],
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
    t = TaggedTurn(acts=[], addressed_child="ravi", problem=Problem(type="sub", a=5, b=2))
    res = RuleEngine.step(scene, t)
    assert res.responses[0].persona_id == "ravi"
    assert scene.children[1].turns_since_addressed == 1


def test_engine_tell_answer_deferred_item_switch() -> None:
    """TELL_ANSWER with a new valid problem defers item switch until after response is calculated."""
    scene = SceneState(
        move_id="M1",
        domain=Domain.NUMERACY,
        effective_acts=[],
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
        ],
    )
    new_prob = Problem(type="sub", a=64, b=28)
    t = TaggedTurn(acts=[TeachingAct.TELL_ANSWER], addressed_child="ravi", problem=new_prob)
    res = RuleEngine.step(scene, t)
    assert res.responses[0].kind == ResponseKind.PARROT
    assert scene.current_item == new_prob


def test_engine_place_value_allowed_numbers() -> None:
    """Place value problems populate tens, 10, and ones in allowed_numbers."""
    scene = SceneState(
        move_id="M1",
        domain=Domain.NUMERACY,
        effective_acts=[TeachingAct.CONCRETE_REPRESENTATION],
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
    t = TaggedTurn(acts=[TeachingAct.CONCRETE_REPRESENTATION], addressed_child="ravi")
    res = RuleEngine.step(scene, t)
    assert 4 in res.responses[0].allowed_numbers
    assert 10 in res.responses[0].allowed_numbers
    assert 7 in res.responses[0].allowed_numbers


def test_engine_literacy_allowed_words() -> None:
    """Literacy problems populate allowed_words with tokens of the string answer."""
    scene = SceneState(
        move_id="M1",
        domain=Domain.LITERACY,
        effective_acts=[TeachingAct.PHONICS_SOUND_OUT],
        target_causes=["MATRA_DROP"],
        items=[Problem(type="read_word", word="किताब")],
        current_item=Problem(type="read_word", word="किताब"),
        children=[
            ChildRuntime(
                persona_id="ravi",
                misconception="MATRA_DROP",
                temperament="confident",
                state=ChildState.MISCONCEPTION,
            ),
        ],
    )
    t = TaggedTurn(acts=[], addressed_child="ravi")
    res = RuleEngine.step(scene, t)
    assert "कतब" in res.responses[0].allowed_words
