"""The chat header (move title, "Step 4 of 7: Practice") follows the saved session state."""

from collections.abc import Iterator

import pytest

from backend.app.config import settings
from backend.app.core.messages import reset_ui_lang, set_ui_lang
from backend.app.rehearsal.scene_runner import load_move_card
from backend.app.sessions.state_machine import OnboardingStateEnum, SessionStateEnum
from backend.app.web.chat_view import STEP_OF_STATE, TOTAL_STEPS, build_view, move_title

READY = OnboardingStateEnum.READY.value
MOVE = "NUM_SUB_REGROUP_BUNDLES"


@pytest.fixture
def english() -> Iterator[None]:
    token = set_ui_lang("en")
    yield
    reset_ui_lang(token)


def test_every_weekly_state_has_a_step_within_the_seven() -> None:
    weekly = set(SessionStateEnum) - {SessionStateEnum.ASK}
    assert {s.value for s in weekly} == set(STEP_OF_STATE)
    assert set(STEP_OF_STATE.values()) == set(range(1, TOTAL_STEPS + 1))


def test_practice_is_step_four_of_seven_in_both_languages(english: None) -> None:
    view = build_view(onboarding=READY, move_id=MOVE, state="REHEARSE")
    assert view["step_label"] == "Step 4 of 7: Practice"
    token = set_ui_lang("hi")
    try:
        assert build_view(onboarding=READY, move_id=MOVE, state="REHEARSE")["step_label"] == (
            "चरण 4 / 7: अभ्यास"
        )
    finally:
        reset_ui_lang(token)


def test_ask_borrows_the_step_she_was_on(english: None) -> None:
    view = build_view(onboarding=READY, move_id=MOVE, state="ASK", prior_state="EXPLAIN_BACK")
    assert view["step"] == 2


def test_done_says_the_week_is_complete_and_setup_has_no_step(english: None) -> None:
    done = build_view(onboarding=READY, move_id=MOVE, state="DONE")
    assert done["step_label"] == "This week's practice is complete"
    setup = build_view(onboarding="ASK_NAME", move_id=MOVE, state="LEARN")
    assert setup["step_label"] == "" and setup["move_title"] == "Getting started"


@pytest.mark.parametrize("module_id", settings.MODULE_IDS)
def test_the_hindi_title_is_the_card_title_and_the_english_one_is_whole(module_id: str) -> None:
    assert move_title(module_id) == load_move_card(module_id).title_hi
    token = set_ui_lang("en")
    try:
        title = move_title(module_id)
    finally:
        reset_ui_lang(token)
    assert title.isascii() and len(title) > 20, "a full English title, not the Hindi one"


def test_a_long_title_is_never_shortened(english: None) -> None:
    title = build_view(onboarding=READY, move_id=MOVE, state="LEARN")["move_title"]
    assert title == "Subtraction with regrouping: opening a bundle"


def test_a_literacy_group_scene_shows_its_bar_before_her_first_line() -> None:
    """Literacy has no one-on-one option: its scene is created on her first line, so the view
    carries the board and the three children until then."""
    view = build_view(
        onboarding=READY, move_id="LIT_MATRA_BLENDING", state="REHEARSE_INTRO", context={}
    )
    preview = view["scene_preview"]
    assert preview["mode"] == "group" and preview["turn"] == 0
    assert [c["id"] for c in preview["children"]] == ["ravi", "priya", "aman"]
    assert preview["board"] == "मेला"


@pytest.mark.parametrize("stage", ["choose_mode", "choose_child", "diagnose", "scene"])
def test_no_preview_while_numeracy_is_choosing_or_a_scene_record_exists(stage: str) -> None:
    view = build_view(
        onboarding=READY, move_id=MOVE, state="REHEARSE_INTRO", context={"rehearse_stage": stage}
    )
    assert view["scene_preview"] is None


def test_no_preview_outside_the_practice_step() -> None:
    view = build_view(onboarding=READY, move_id="LIT_MATRA_BLENDING", state="FEEDBACK")
    assert view["scene_preview"] is None
