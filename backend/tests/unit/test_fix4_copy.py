"""fix4 copy fixes: pronoun for the scene child, and the class-link line only when it is true."""

from __future__ import annotations

from backend.app.class_profile.followup import back_to_scene_message
from backend.app.content_models import Domain
from backend.app.core.messages import get_message, reset_ui_lang, set_ui_lang
from backend.app.rehearsal.scene_store import TurnRecord
from backend.app.rule_engine.domain import ResponseKind
from backend.app.sessions.outcome import class_link_key
from backend.tests.unit.test_child_k1 import _resp


def _turn(persona_id: str, kind: ResponseKind) -> TurnRecord:
    response = _resp(kind).model_copy(update={"persona_id": persona_id})
    return TurnRecord(turn_index=1, transcript="x", acts=[], child_responses=[response])


def test_class_link_names_the_child_only_when_the_child_made_the_mistake() -> None:
    made = [_turn("ravi", ResponseKind.EXPLAIN_BUG)]
    relapse = [_turn("ravi", ResponseKind.RELAPSE)]
    read_right = [_turn("aman", ResponseKind.CORRECT_EXPLAINED)]
    other_child = [_turn("priya", ResponseKind.EXPLAIN_BUG)]
    assert class_link_key(made, "ravi", Domain.NUMERACY) == "coach_class_link"
    assert class_link_key(relapse, "ravi", Domain.NUMERACY) == "coach_class_link"
    assert class_link_key(read_right, "aman", Domain.NUMERACY) == "coach_class_link_general"
    assert class_link_key(other_child, "ravi", Domain.NUMERACY) == "coach_class_link_general"


def test_class_link_for_a_literacy_move_never_says_real_objects() -> None:
    key = class_link_key([_turn("priya", ResponseKind.EXPLAIN_BUG)], "priya", Domain.LITERACY)
    assert key == "coach_class_link_literacy"
    for lang in ("hi", "en"):
        for k in (key, "coach_class_link_general_literacy"):
            text = get_message(k, lang=lang, label="x", child="y")
            assert "real objects" not in text and "ठोस" not in text, (lang, k)


def test_class_link_texts_exist_in_both_languages_and_name_no_unfilled_slot() -> None:
    for lang in ("hi", "en"):
        for k in (
            "coach_class_link",
            "coach_class_link_literacy",
            "coach_class_link_general",
            "coach_class_link_general_literacy",
        ):
            text = get_message(k, lang=lang, label="L", child="C")
            assert "{" not in text and "L" in text


def test_ask_ravi_how_he_got_this_answer() -> None:
    token = set_ui_lang("en")
    try:
        for child_id, name, pronoun in (("ravi", "Ravi", "he"), ("priya", "Priya", "she")):
            scene = {"mode": "one_on_one", "board": "45", "child_name": name, "child_id": child_id}
            text = back_to_scene_message(scene).text_hi
            assert f"how {pronoun} got this answer" in text and "they" not in text
    finally:
        reset_ui_lang(token)


def test_blank_lines_are_trimmed_in_every_outbound_text() -> None:
    from backend.app.core.outbound_text import normalize_outbound
    from backend.app.core.types import OutboundMessage

    msg = OutboundMessage(kind="text", text_hi="पहला\n\n\n\n\nदूसरा\n \n \nतीसरा\n\n")
    (out,) = normalize_outbound([msg])
    assert out.text_hi == "पहला\n\nदूसरा\n\nतीसरा"


def test_the_guide_source_label_matches_the_hindi_answer_even_in_an_english_ui() -> None:
    token = set_ui_lang("en")
    try:
        label = get_message("handbook_source_label", lang="hi")
    finally:
        reset_ui_lang(token)
    assert label == "FLN प्रशिक्षण पैकेज से"
