"""The what-to-do-now line: wording that matches the buttons and inputs the flow really has."""

import re
from collections.abc import Iterator
from typing import Any

import pytest

from backend.app.core.messages import get_message, reset_ui_lang, set_ui_lang
from backend.app.sessions.state_machine import OnboardingStateEnum, SessionStateEnum
from backend.app.web.chat_view import build_view
from backend.app.web.next_action import (
    ONBOARDING_HINTS,
    WEEKLY_HINTS,
    next_action,
)

READY = OnboardingStateEnum.READY.value
MAX_CHARS = 100  # two lines on a 360 px phone at the card's font size, in either language

ONE_ON_ONE = {
    "mode": "one_on_one",
    "child_id": "ravi",
    "child_name": "Ravi",
    "turn": 0,
    "item": {"type": "sub", "a": 43, "b": 27, "tens": None, "ones": None, "word": None},
}
GROUP = {
    "mode": "group",
    "turn": 0,
    "children": [{"id": "ravi", "name": "Ravi"}, {"id": "priya", "name": "Priya"}],
    "item": {"type": "read_word", "a": None, "b": None, "tens": None, "ones": None, "word": "मेला"},
}


def hint(state: str, **kw: Any) -> dict[str, Any] | None:
    args: dict[str, Any] = {
        "onboarding": READY,
        "state": state,
        "context": {},
        "retries": 0,
        "address_form": "f",
        "started": True,
        "scene": None,
    }
    args.update(kw)
    return next_action(**args)


@pytest.fixture(params=["en", "hi"])
def lang(request: pytest.FixtureRequest) -> Iterator[str]:
    token = set_ui_lang(request.param)
    yield str(request.param)
    reset_ui_lang(token)


def test_learn_step_names_the_real_button(lang: str) -> None:
    h = hint("LEARN")
    assert h is not None
    assert get_message("btn_understood", "f") in h["text"]
    if lang == "en":
        assert h["text"] == "Read this, then tap 'Got it, next'."


def test_the_quoted_button_is_in_her_address_form() -> None:
    token = set_ui_lang("hi")
    try:
        female = hint("LEARN", address_form="f")
        male = hint("LEARN", address_form="m")
    finally:
        reset_ui_lang(token)
    assert female is not None and male is not None
    assert get_message("btn_understood", "f") in female["text"]
    assert get_message("btn_understood", "m") in male["text"]
    assert female["text"] != male["text"]


def test_every_weekly_state_and_onboarding_stage_has_a_short_line(lang: str) -> None:
    texts: list[str] = []
    for state in WEEKLY_HINTS:
        h = hint(state)
        assert h is not None, state
        texts.append(h["text"])
    for stage in ONBOARDING_HINTS:
        h = hint("LEARN", onboarding=stage)
        assert h is not None, stage
        texts.append(h["text"])
    for h2 in (
        hint("LEARN", onboarding="NEW", started=False),
        hint("LEARN", onboarding="NEW", started=True),
        hint("REHEARSE_INTRO", context={"rehearse_stage": "choose_mode"}),
        hint("REHEARSE_INTRO", context={"rehearse_stage": "choose_child"}),
        hint(
            "REHEARSE",
            context={"rehearse_stage": "diagnose", "rehearse_mode": "one_on_one"},
            scene=ONE_ON_ONE,
        ),
        hint(
            "REHEARSE",
            context={"rehearse_stage": "scene", "rehearse_mode": "one_on_one"},
            scene=ONE_ON_ONE,
        ),
        hint(
            "REHEARSE",
            retries=1,
            context={"rehearse_stage": "scene", "rehearse_mode": "one_on_one"},
            scene=ONE_ON_ONE,
        ),
        hint("REHEARSE", scene=GROUP),
        hint("REHEARSE", retries=2, scene=GROUP),
        hint("FEEDBACK", context={"resume_scene_id": "x"}),
        hint("FEEDBACK", context={"module_mode": True, "module_check_stage": "asking"}),
        hint("DONE", context={"rating_stage": "rating"}),
        hint("DONE", context={"rating_stage": "comment"}),
        hint("LEARN", context={"class_stage": "asking"}),
        hint("LEARN", context={"class_stage": "confirm"}),
        hint("LEARN", context={"skill_stage": "asking"}),
        hint("LEARN", context={"awaiting_delete_confirm": True}),
    ):
        assert h2 is not None
        texts.append(h2["text"])
    for text in texts:
        assert len(text) <= MAX_CHARS, f"{len(text)} chars: {text}"
        assert not re.search(r"[{}]", text), f"unfilled placeholder: {text}"
        assert text.strip() == text and text.endswith((".", "।", "?", ")")), text


def test_one_on_one_scene_asks_for_the_method_with_the_boards_numbers() -> None:
    token = set_ui_lang("en")
    try:
        h = hint(
            "REHEARSE",
            context={"rehearse_stage": "scene", "rehearse_mode": "one_on_one"},
            scene=ONE_ON_ONE,
        )
    finally:
        reset_ui_lang(token)
    assert h is not None
    assert h["text"] == "Ask Ravi how they did it. Tap the example or say your own."
    assert h["suggest"] == "Ravi, how did you take 27 from 43?"


def test_after_her_first_line_the_scene_line_says_how_to_keep_going() -> None:
    """Same step key (she dismisses it once for the whole scene); the wording follows her turn count."""
    ctx = {"rehearse_stage": "scene", "rehearse_mode": "one_on_one"}
    token = set_ui_lang("en")
    try:
        first = hint("REHEARSE", context=ctx, scene=ONE_ON_ONE)
        later = hint("REHEARSE", context=ctx, scene={**ONE_ON_ONE, "turn": 1})
        group_later = hint("REHEARSE", scene={**GROUP, "turn": 3})
        d = hint(
            "REHEARSE",
            context={"rehearse_stage": "diagnose", "rehearse_mode": "one_on_one"},
            scene=ONE_ON_ONE,
        )
    finally:
        reset_ui_lang(token)
    assert first is not None and later is not None and first["key"] == later["key"] == "scene_one"
    assert first["text"] != later["text"] and "concrete" in later["text"]
    assert later["suggest"] == "Ravi, let us make 43 with bundles of ten and loose sticks."
    assert group_later is not None and group_later["key"] == "scene_group"
    assert d is not None and "Ravi" in d["text"] and "Skip" in d["text"]
    assert d["suggest"] is None, "the diagnosis is hers to make: no suggested answer"


def test_retry_line_differs_and_the_group_scene_points_at_the_names() -> None:
    ctx = {"rehearse_stage": "scene", "rehearse_mode": "one_on_one"}
    first = hint("REHEARSE", context=ctx, scene=ONE_ON_ONE)
    again = hint("REHEARSE", retries=1, context=ctx, scene=ONE_ON_ONE)
    assert first is not None and again is not None and first["text"] != again["text"]
    group = hint("REHEARSE", scene=GROUP)
    assert group is not None and group["key"] == "scene_group"
    assert group["suggest"] is not None


def test_a_question_in_progress_comes_before_the_weekly_step() -> None:
    assert hint("LEARN", context={"awaiting_delete_confirm": True})["key"] == "hint_delete"  # type: ignore[index]
    assert hint("LEARN", context={"class_stage": "asking"})["key"] == "hint_class_ask"  # type: ignore[index]
    assert hint("DONE", context={"rating_stage": "rating"})["key"] == "hint_rating"  # type: ignore[index]


def test_new_teacher_is_told_to_say_hello_then_to_agree() -> None:
    first = hint("LEARN", onboarding="NEW", started=False)
    later = hint("LEARN", onboarding="NEW", started=True)
    assert first is not None and first["key"] == "hint_start" and first["suggest"]
    assert later is not None and later["key"] == "hint_consent"


def test_build_view_carries_the_line_for_a_literacy_scene_before_her_first_line() -> None:
    view = build_view(onboarding=READY, move_id="LIT_MATRA_BLENDING", state="REHEARSE_INTRO")
    assert view["hint"]["key"] == "scene_group"
    assert (
        view["hint"]["suggest"] and "मेला" not in view["hint"]["suggest"]
    )  # the word is on the board
    assert SessionStateEnum.REHEARSE.value in ("REHEARSE",)


def test_buttons_stored_in_hindi_show_in_the_ui_language() -> None:
    """The line names 'Got it, next'; a Hindi-stored message must show that button in English."""
    from backend.app.core.messages import localize_buttons

    stored = [
        {"id": "btn_understood", "title_hi": get_message("btn_understood", "f", lang="hi")},
        {"id": "btn_made_up", "title_hi": "ठीक है"},
    ]
    assert localize_buttons(stored, "f") == stored, "Hindi UI: untouched"
    token = set_ui_lang("en")
    try:
        shown = localize_buttons(stored, "f")
    finally:
        reset_ui_lang(token)
    assert shown[0]["title_hi"] == "Got it, next"
    assert shown[1] == stored[1], "an id with no catalogue entry keeps its stored title"
    assert localize_buttons(None) is None
