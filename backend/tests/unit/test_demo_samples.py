"""The demo's sample lines: where they appear, what they say, and that they are not invented."""

from collections.abc import Iterator
from typing import Any

import pytest

from backend.app.core.messages import reset_ui_lang, set_ui_lang
from backend.app.web import demo_samples
from backend.app.web.demo_samples import build_samples, needs_regrouping, next_problem

SUB = {"type": "sub", "a": 43, "b": 27}
ONE_ON_ONE = {"mode": "one_on_one", "child_id": "ravi", "child_name": "रवि", "item": SUB}
GROUP = {
    "mode": "group",
    "children": [{"id": "ravi", "name": "रवि"}, {"id": "priya", "name": "प्रिया"}],
    "item": {"type": "read_word", "word": "मेला"},
}


@pytest.fixture
def english() -> Iterator[None]:
    token = set_ui_lang("en")
    yield
    reset_ui_lang(token)


def ids(samples: list[dict[str, Any]]) -> list[str]:
    return [s["id"] for s in samples]


def test_every_sample_is_complete_in_both_languages() -> None:
    allowed_scopes = {"scene", "diagnose", "explain_back", "any"}
    allowed_kinds = {"ask_how", "tell_answer", "new_problem", "static"}
    seen = set()
    for sample in demo_samples._load():
        assert sample["id"] not in seen
        seen.add(sample["id"])
        assert sample["scope"] in allowed_scopes and sample["text_kind"] in allowed_kinds
        for field in ("label", "note"):
            assert sample[field]["hi"].strip() and sample[field]["en"].strip(), sample["id"]
        assert len(sample["note"]["en"]) <= 90, "one line of explanation"


def test_a_scene_offers_ask_tell_and_a_new_problem_with_what_each_shows(english: None) -> None:
    got = build_samples(
        state="REHEARSE", stage="scene", scene=ONE_ON_ONE, move_id="NUM_SUB_REGROUP_BUNDLES"
    )
    assert ids(got) == [
        "s1_ask_ravi",
        "s3_tell_answer_hinglish",
        "s6_new_problem",
        "s5_question_multigrade",
    ]
    by_id = {s["id"]: s for s in got}
    assert by_id["s1_ask_ravi"]["label"] == "Ask रवि how they did it"
    assert by_id["s3_tell_answer_hinglish"]["label"] == "Say the answer (a mistake to try)"
    assert "repeats the answer" in by_id["s3_tell_answer_hinglish"]["note"]
    assert "explains their own method" in by_id["s1_ask_ravi"]["note"]
    assert by_id["s1_ask_ravi"]["text"] == "रवि, तुमने 43 में से 27 कैसे घटाया? मुझे एक-एक कदम बताओ।"
    assert by_id["s3_tell_answer_hinglish"]["text"] == "Sahi answer 16 hai, yaad rakho."
    assert by_id["s5_question_multigrade"]["label"] == "A question the handbook does not cover"
    assert by_id["s5_question_multigrade"]["note"] == "It will say so and pass it to your ARP."


def test_the_new_problem_is_the_next_card_item_that_needs_regrouping() -> None:
    got = {
        s["id"]: s
        for s in build_samples(
            state="REHEARSE", stage="scene", scene=ONE_ON_ONE, move_id="NUM_SUB_REGROUP_BUNDLES"
        )
    }
    assert got["s6_new_problem"]["text"] == "अब 61 में से 28 करो।"
    for fresh in (
        next_problem("NUM_SUB_REGROUP_BUNDLES", SUB),
        next_problem("NUM_ADD_CARRY_BUNDLES", {"type": "add", "a": 38, "b": 45}),
    ):
        assert fresh is not None and needs_regrouping(fresh)
    # from the card, not invented: it is one of the card's own items
    from backend.app.rehearsal.scene_runner import load_move_card

    items = load_move_card("NUM_SUB_REGROUP_BUNDLES").scenario.items
    assert next_problem("NUM_SUB_REGROUP_BUNDLES", SUB) in items


def test_needs_regrouping_for_subtraction_and_carrying() -> None:
    assert needs_regrouping({"type": "sub", "a": 43, "b": 27})
    assert not needs_regrouping({"type": "sub", "a": 48, "b": 27})
    assert needs_regrouping({"type": "add", "a": 38, "b": 45})
    assert not needs_regrouping({"type": "add", "a": 31, "b": 45})
    assert not needs_regrouping({"type": "read_word", "word": "मेला"})


def test_reading_scene_uses_the_word_and_has_no_arithmetic() -> None:
    got = {
        s["id"]: s["text"]
        for s in build_samples(
            state="REHEARSE", stage="", scene=GROUP, move_id="LIT_MATRA_BLENDING"
        )
    }
    assert got["s1_ask_ravi"].startswith("रवि, तुमने यह शब्द कैसे पढ़ा?")
    assert got["s3_tell_answer_hinglish"] == "Sahi shabd 'मेला' hai, yaad rakho."
    assert got["s6_new_problem"] == "अब यह शब्द पढ़ो: पानी"


def test_samples_follow_the_step() -> None:
    assert ids(build_samples(state="LEARN", stage="", scene=None, move_id="X")) == [
        "s5_question_multigrade"
    ]
    assert ids(build_samples(state="EXPLAIN_BACK", stage="", scene=None, move_id="X")) == [
        "s4_explain_back",
        "s5_question_multigrade",
    ]
    diag = build_samples(
        state="REHEARSE", stage="diagnose", scene=ONE_ON_ONE, move_id="NUM_SUB_REGROUP_BUNDLES"
    )
    assert ids(diag) == ["s2_diagnose_one_on_one", "s5_question_multigrade"]
    # the choosing steps have no scene yet: no lines about a child's answer
    choose = build_samples(
        state="REHEARSE_INTRO", stage="choose_mode", scene=None, move_id="NUM_SUB_REGROUP_BUNDLES"
    )
    assert ids(choose) == ["s5_question_multigrade"]


def test_place_value_has_no_new_problem_sample() -> None:
    scene = {**ONE_ON_ONE, "item": {"type": "place_value", "tens": 4, "ones": 7}}
    got = ids(
        build_samples(
            state="REHEARSE", stage="scene", scene=scene, move_id="NUM_PLACE_VALUE_BUNDLES"
        )
    )
    assert "s6_new_problem" not in got and "s1_ask_ravi" in got


def test_a_sample_with_a_rendered_voice_note_is_flagged_only_when_the_text_matches() -> None:
    text = "रवि, तुमने 43 में से 27 कैसे घटाया? मुझे एक-एक कदम बताओ।"
    same = build_samples(
        state="REHEARSE",
        stage="scene",
        scene=ONE_ON_ONE,
        move_id="NUM_SUB_REGROUP_BUNDLES",
        audio={"s1_ask_ravi": text},
    )
    other = build_samples(
        state="REHEARSE",
        stage="scene",
        scene=ONE_ON_ONE,
        move_id="NUM_SUB_REGROUP_BUNDLES",
        audio={"s1_ask_ravi": "कुछ और"},
    )
    assert same[0]["audio"] is True and other[0]["audio"] is False
