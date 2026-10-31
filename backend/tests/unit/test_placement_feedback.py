"""F5: the line after the onboarding practice names what she did and why the first move."""

from __future__ import annotations

from itertools import product

import pytest

from backend.app.core.messages import get_message, reset_ui_lang, set_ui_lang
from backend.app.sessions.placement_feedback import placement_feedback

TITLE = "TITLE"
ACTS = {
    "asked": "ask_to_explain",
    "words": "model_step_aloud",
    "objects": "concrete_representation",
    "told": "tell_answer",
}


def _says(acts: list[str], lang: str = "hi", form: str = "f", told_later: bool = False) -> str:
    token = set_ui_lang(lang)
    try:
        return placement_feedback(acts, TITLE, form, told_later=told_later)
    finally:
        reset_ui_lang(token)


@pytest.mark.parametrize("combo", list(product([False, True], repeat=5)))
def test_every_act_combination(combo: tuple[bool, ...]) -> None:
    """The four tagged acts and fix3 K2's "told the procedure in a later turn": 32 combinations."""
    asked, words, objects, told, told_later = combo
    acts = [v for flag, v in zip(combo[:4], ACTS.values(), strict=True) if flag]
    out = _says(acts, told_later=told_later)
    assert (get_message("placement_fb_told_later", "f") in out) == (told_later and not told)
    assert TITLE in out
    assert "{" not in out and "बहुत अच्छा! अब मुझे" not in out
    assert (get_message("placement_fb_asked", "f") in out) == asked
    assert (get_message("placement_fb_objects", "f") in out) == objects
    assert (get_message("placement_fb_told", "f") in out) == told
    assert (get_message("placement_fb_words", "f") in out) == (words and not objects)
    if not any(combo[:4]):
        assert get_message("placement_fb_none", "f") in out
    why = (
        "told"
        if told
        else "words"
        if words and not objects
        else "objects"
        if objects
        else "default"
    )
    assert get_message(f"placement_fb_why_{why}", "f", move_title=TITLE) in out


def test_the_user_example_shape() -> None:
    out = _says(["ask_to_explain", "model_step_aloud"])
    assert out.startswith("आपने रवि से पूछा कि 45 कैसे आया, अच्छा।")
    assert "शब्दों में समझाया" in out and "वही गलती" in out and "इसलिए हम" in out
    print("F5 asked+words:", out)


@pytest.mark.parametrize("form", ["f", "m"])
def test_english_is_all_english_and_address_form_is_accepted(form: str) -> None:
    out = _says(["tell_answer"], "en", form)
    print("F5 en told:", out)
    assert "You told Ravi" in out and not any("ऀ" <= c <= "ॿ" for c in out.replace(TITLE, ""))


def test_no_dashes() -> None:
    for acts in ([], list(ACTS.values())):
        for lang in ("hi", "en"):
            out = _says(acts, lang)
            assert "—" not in out and "–" not in out


def test_k2_the_live_case_a_question_then_the_procedure_told() -> None:
    """Ravi asked how he got 45, then the teacher dictated the steps: both are said."""
    out = _says(["ask_to_explain"], told_later=True)
    assert out.startswith("आपने रवि से पूछा कि 45 कैसे आया, अच्छा।")
    assert "फिर आपने खुद तरीका बता दिया; अगली बार रवि को खुद करने दें।" in out
    en = _says(["ask_to_explain"], "en", told_later=True)
    assert "Then you told the method yourself; next time let Ravi do it himself." in en
    assert not any("ऀ" <= c <= "ॿ" for c in en.replace(TITLE, ""))
    assert "—" not in out and "—" not in en
