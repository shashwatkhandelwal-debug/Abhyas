"""Track B practice scenes: comparing two-digit numbers and letter name versus letter sound."""

from __future__ import annotations

from typing import Any

import pytest

from backend.app.class_profile.library import load_library
from backend.app.config import move_offered, settings
from backend.app.content_models import PersonaCard
from backend.app.core.messages import get_message, set_ui_lang
from backend.app.llm.guards import guard_child_line
from backend.app.llm.roles.act_tagger import fallback_tag_act
from backend.app.llm.roles.child_voice import template_line
from backend.app.rehearsal.header import board_text, child_strip_label
from backend.app.rehearsal.scene_runner import load_move_card
from backend.app.rule_engine.bugs import cmp_correct, cmp_ones_first, get_rule_info
from backend.app.rule_engine.bugs.letter_sound import letter_name_for_sound
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

PERSONA = PersonaCard(
    id="ravi",
    name_hi="रवि",
    age=7,
    temperament="confident",
    voice_id="x",
    speech_style_hi="तेज़",
)
TEMPERAMENTS: dict[str, Any] = {"ravi": "confident", "priya": "shy", "aman": "distracted"}


def scene_for(move_id: str) -> SceneState:
    move = load_move_card(move_id)
    items = [Problem(**i) for i in move.scenario.items]
    children = [
        ChildRuntime(
            persona_id=c.persona_id,
            misconception=c.misconception,
            temperament=TEMPERAMENTS[c.persona_id],
        )
        for c in move.scenario.children
    ]
    return SceneState(
        move_id=move_id,
        domain=Domain(move.domain.value),
        effective_acts=list(move.teaching_acts_effective),
        target_causes=list(move.target_causes),
        items=items,
        current_item=items[0],
        children=children,
        max_turns=12,
    )


def turn(
    scene: SceneState, *acts: TeachingAct, who: str = "ravi", problem: Problem | None = None
) -> Any:
    res = RuleEngine.step(scene, TaggedTurn(acts=list(acts), addressed_child=who, problem=problem))
    return res.responses[0]


def guard_ok(resp: Any) -> bool:
    return guard_child_line(template_line(resp, PERSONA), resp)[0]


# T1: comparing numbers
@pytest.mark.parametrize(
    "a,b,bug,right",
    [
        (39, 41, 39, 41),
        (41, 39, 39, 41),
        (28, 33, 28, 33),
        (19, 21, 19, 21),
        (7, 41, 7, 41),
        (52, 8, 8, 52),
        (42, 47, 47, 47),
        (50, 50, 50, 50),
        (35, 35, 35, 35),
        (31, 38, 38, 38),
        (60, 71, 71, 71),
    ],
)
def test_compare_rule_pairs(a: int, b: int, bug: int, right: int) -> None:
    p = Problem(type="compare", a=a, b=b)
    assert cmp_ones_first(p).answer == bug
    assert cmp_correct(p).answer == right == p.answer()


def test_compare_registered_and_scene_wired() -> None:
    assert get_rule_info("CMP_ONES_FIRST").problem_types == ["compare"]
    move = load_move_card("NUM_COMPARE_BUNDLES")
    assert move.target_causes == ["CMP_ONES_FIRST"]
    assert move.scenario.items[0] == {"type": "compare", "a": 39, "b": 41}


def test_compare_ask_how_explains_bug_then_bundles_partial_then_correct() -> None:
    scene = scene_for("NUM_COMPARE_BUNDLES")
    first = turn(scene, TeachingAct.REPEAT_QUESTION)
    assert first.kind == ResponseKind.ANSWER and first.answer == 39 and first.forbidden == {"41"}
    r = turn(scene, TeachingAct.ASK_TO_EXPLAIN)
    assert r.kind == ResponseKind.EXPLAIN_BUG and r.answer == 39
    assert "9" in r.steps[0].text_hi and guard_ok(r)
    r = turn(scene, TeachingAct.CONCRETE_REPRESENTATION)
    assert r.kind == ResponseKind.SCAFFOLDED_CORRECT
    assert r.new_state == ChildState.PARTIAL and r.answer == 41
    assert guard_ok(r)
    r = turn(scene, TeachingAct.CONTRAST_TWO_ANSWERS)
    assert r.kind == ResponseKind.CORRECT_EXPLAINED and r.new_state == ChildState.CORRECT
    assert guard_ok(r) and "बंडल" in template_line(r, PERSONA)


def test_compare_told_answer_parrots_then_relapses_on_new_pair() -> None:
    scene = scene_for("NUM_COMPARE_BUNDLES")
    r = turn(scene, TeachingAct.TELL_ANSWER)
    assert r.kind == ResponseKind.PARROT and r.answer == 41
    r = turn(scene, TeachingAct.GIVE_NEW_PROBLEM, problem=Problem(type="compare", a=28, b=33))
    assert r.kind == ResponseKind.ANSWER and r.answer == 28
    turn(scene, TeachingAct.CONCRETE_REPRESENTATION)
    r = turn(scene, TeachingAct.GIVE_NEW_PROBLEM, problem=Problem(type="compare", a=47, b=52))
    assert r.kind == ResponseKind.RELAPSE and r.answer == 47
    label = child_strip_label(scene.children[0], scene)
    assert get_message("ui_strip_relapse_m") in label


def test_compare_guard_allows_exactly_the_numbers_in_play() -> None:
    scene = scene_for("NUM_COMPARE_BUNDLES")
    r = turn(scene, TeachingAct.ASK_TO_EXPLAIN)
    assert r.allowed_numbers == {1, 39, 41, 9}
    assert guard_child_line("9 और 1 में 9 बड़ा है, तो 39 बड़ा", r)[0]
    bad, why = guard_child_line("7 और 1 में 7 बड़ा है, तो 39 बड़ा", r)
    assert not bad and "7" in why


def test_compare_board_and_tagger_hindi_english() -> None:
    p = Problem(type="compare", a=39, b=41)
    assert board_text(p) == "39 और 41: कौन बड़ा?"
    set_ui_lang("en")
    try:
        assert board_text(p) == "39 and 41: which is bigger?"
    finally:
        set_ui_lang("hi")
    tagged = fallback_tag_act("अब ये सवाल: 28 और 33, कौन बड़ा?", ["ravi"], p)
    assert tagged.problem is not None and (tagged.problem.a, tagged.problem.b) == (28, 33)
    same = fallback_tag_act("रवि, 39 और 41 में से कौन बड़ा है?", ["ravi"], p)
    assert same.problem is None


def test_compare_validation_accepts_one_digit_rejects_out_of_range() -> None:
    scene = scene_for("NUM_COMPARE_BUNDLES")
    r = turn(scene, TeachingAct.GIVE_NEW_PROBLEM, problem=Problem(type="compare", a=7, b=41))
    assert r.kind != ResponseKind.CONFUSED
    r = turn(scene, TeachingAct.GIVE_NEW_PROBLEM, problem=Problem(type="compare", a=7, b=410))
    assert r.kind == ResponseKind.CONFUSED


# T2: letter sounds
def test_letter_rule_words() -> None:
    assert letter_name_for_sound(Problem(type="read_word", word="बकरी")).answer == "ब से बतख"
    assert letter_name_for_sound(Problem(type="read_word", word="कमल")).answer == "क से कबूतर"
    assert letter_name_for_sound(Problem(type="read_word", word="बतख")).answer == "ब से बस"
    correct = get_rule_info("LETTER_NAME_FOR_SOUND").correct_fn(
        Problem(type="read_word", word="नदी"), None
    )
    assert correct.answer == "नदी"


def test_letter_told_word_repeats_then_misreads_new_word() -> None:
    scene = scene_for("LIT_LETTER_SOUND_PAIRS")
    r = turn(scene, TeachingAct.REPEAT_QUESTION)
    assert r.kind == ResponseKind.ANSWER and r.answer == "ब से बतख" and guard_ok(r)
    r = turn(scene, TeachingAct.TELL_ANSWER)
    assert r.kind == ResponseKind.PARROT and r.answer == "बकरी"
    r = turn(scene, TeachingAct.GIVE_NEW_PROBLEM, problem=Problem(type="read_word", word="कमल"))
    assert r.kind == ResponseKind.ANSWER and r.answer == "क से कबूतर" and guard_ok(r)


def test_letter_sound_out_partial_then_correct_then_relapse() -> None:
    scene = scene_for("LIT_LETTER_SOUND_PAIRS")
    r = turn(scene, TeachingAct.PHONICS_SOUND_OUT)
    assert r.new_state == ChildState.PARTIAL and r.answer == "बकरी" and guard_ok(r)
    r = turn(scene, TeachingAct.MODEL_STEP_ALOUD)
    assert r.new_state == ChildState.CORRECT and guard_ok(r)
    scene2 = scene_for("LIT_LETTER_SOUND_PAIRS")
    turn(scene2, TeachingAct.PHONICS_SOUND_OUT)
    r = turn(scene2, TeachingAct.GIVE_NEW_PROBLEM, problem=Problem(type="read_word", word="गमला"))
    assert r.kind == ResponseKind.RELAPSE and r.answer == "ग से गाय"


def test_letter_guard_allows_only_the_scene_words() -> None:
    scene = scene_for("LIT_LETTER_SOUND_PAIRS")
    r = turn(scene, TeachingAct.REPEAT_QUESTION)
    assert guard_child_line("ब से बतख!", r)[0]
    assert not guard_child_line("बकरी!", r)[0]
    assert r.forbidden == {"बकरी"}


# flags
def _flags(monkeypatch: pytest.MonkeyPatch, on: bool) -> None:
    monkeypatch.setattr(settings, "DEMO_MODE", False)
    monkeypatch.setattr(settings, "SCENE_NUM_COMPARE_ENABLED", on)
    monkeypatch.setattr(settings, "SCENE_LIT_LETTER_SOUND_ENABLED", on)


def test_flags_off_library_has_no_new_practice(monkeypatch: pytest.MonkeyPatch) -> None:
    _flags(monkeypatch, False)
    lib = load_library()
    compare = lib.get("NUM_COMPARE")
    letter = lib.get("LIT_LETTER_SOUND")
    assert compare is not None and compare.move_id is None
    assert letter is not None and letter.move_id is None and letter.misconception_ids == []
    assert not move_offered("NUM_COMPARE_BUNDLES") and move_offered("NUM_SUB_REGROUP_BUNDLES")
    from backend.app.class_profile import checkin_flow

    assert {m.id for m in checkin_flow.modules(lib)} == {
        "NUM_PLACE_VALUE_BUNDLES",
        "NUM_ADD_CARRY_BUNDLES",
        "NUM_SUB_REGROUP_BUNDLES",
        "LIT_MATRA_BLENDING",
        "OTHER_numeracy",
        "OTHER_literacy",
    }


def test_flags_on_check_in_offers_practice(monkeypatch: pytest.MonkeyPatch) -> None:
    _flags(monkeypatch, True)
    lib = load_library()
    compare = lib.get("NUM_COMPARE")
    letter = lib.get("LIT_LETTER_SOUND")
    assert compare is not None and compare.move_id == "NUM_COMPARE_BUNDLES"
    assert letter is not None and letter.move_id == "LIT_LETTER_SOUND_PAIRS"
    from backend.app.class_profile import checkin_flow

    ids = {m.id for m in checkin_flow.modules(lib)}
    assert {"NUM_COMPARE_BUNDLES", "LIT_LETTER_SOUND_PAIRS"} <= ids


def test_new_moves_never_in_weekly_path() -> None:
    from backend.app.sessions.path import compute_move_path

    ids = [e.move_id for e in compute_move_path("t1")]
    assert "NUM_COMPARE_BUNDLES" not in ids and "LIT_LETTER_SOUND_PAIRS" not in ids
