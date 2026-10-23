"""The chat header and the scene bar in a real browser (first-use feedback: cut-off title, the
problem shown twice, three child chips in a one-on-one scene, an unexplained row of dots)."""

from pathlib import Path
from typing import Any

import pytest
import yaml

from backend.tests.e2e.conftest import CLIPPED, DESKTOP, MOBILE, tap_reply

REPO_ROOT = Path(__file__).resolve().parents[3]


def _text(lang: str, key: str) -> str:
    path = REPO_ROOT / f"content/messages_{lang}.yaml"
    return str(yaml.safe_load(path.read_text(encoding="utf-8"))[key]["text"])


@pytest.mark.parametrize(
    ("lang", "viewport"),
    [("hi", MOBILE), ("en", MOBILE), ("en", DESKTOP)],
    ids=["hi-mobile", "en-mobile", "en-desktop"],
)
def test_one_on_one_scene_bar_is_compact_whole_and_about_one_child(
    open_chat: Any, lang: str, viewport: dict[str, int]
) -> None:
    page = open_chat("teacher.demo2", lang=lang, viewport=viewport).page
    # one header: the full move title (it wraps), "Step 4 of 7: Practice", nothing cut off
    title = page.locator("#header-move-title").inner_text().strip()
    assert title == _text(lang, "move_title_NUM_SUB_REGROUP_BUNDLES")
    step = page.locator("#header-step").inner_text().strip()
    expected = _text(lang, "ui_step_label").format(n=4, total=7, name=_text(lang, "ui_step_4"))
    assert step == expected
    assert page.evaluate(CLIPPED, ".chat-header, .chat-header *, #scene-bar, #scene-bar *") == []
    # the scene bar: who, her turn, one board card
    bar = page.locator("#scene-bar")
    assert bar.is_visible()
    child = _text(lang, "speaker_ravi")
    assert page.locator("#sb-title").inner_text() == _text(lang, "ui_scene_one_title").format(
        child=child
    )
    turn = page.locator("#sb-turn").inner_text()
    assert turn.startswith(_text(lang, "ui_scene_turn").split("{")[0]), turn
    assert page.locator("#sb-board").inner_text() == "43 − 27"
    assert page.locator(".board-problem").count() == 1, "the problem is shown once"
    # only that child: no other children, no switcher, no unexplained row of dots
    assert page.locator(".child-pill").count() == 0
    assert page.locator("#sh-steps, .sh-cue, .rehearse-strip, #scene-header").count() == 0
    visible = page.inner_text("body")
    for other in ("priya", "aman"):
        assert _text(lang, f"speaker_{other}") not in visible


def test_end_practice_keeps_its_confirmation(open_chat: Any) -> None:
    page = open_chat("teacher.demo2", lang="en").page
    asked: list[str] = []
    page.once("dialog", lambda d: (asked.append(d.message), d.dismiss()))
    page.click("#sh-end")
    assert asked == [_text("en", "ui_chat_scene_end_confirm")]
    assert page.locator("#scene-bar").is_visible(), "dismissing the confirm keeps the scene"


def test_no_scene_bar_before_a_scene(open_chat: Any) -> None:
    page = open_chat("teacher.demo1").page
    assert not page.locator("#scene-bar").is_visible()
    assert page.locator(".child-pill").count() == 0
    assert page.locator("#header-move-title").inner_text().strip() == _text("hi", "ui_step_setup")


def test_group_scene_lists_the_three_children_and_a_name_tap_fills_the_input(
    open_chat: Any,
) -> None:
    page = open_chat("teacher.demo3").page  # a reading move: the scene is a group of three
    tap_reply(page, _text("hi", "btn_understood"))  # learn -> say it back
    tap_reply(page, _text("hi", "btn_skip"))  # skip -> model
    tap_reply(page, _text("hi", "btn_skip"))  # skip -> the scene
    page.wait_for_selector("#scene-bar:not([hidden])")
    names = page.locator("#sb-children .child-pill").all_inner_texts()
    assert names == [_text("hi", f"speaker_{p}") for p in ("ravi", "priya", "aman")]
    assert page.locator("#sb-board").inner_text() == "मेला"
    page.locator("#sb-children .child-pill", has_text=_text("hi", "speaker_priya")).tap()
    assert page.input_value("#chat-input") == f"{_text('hi', 'speaker_priya')}, "
    assert page.evaluate(CLIPPED, "#scene-bar, #scene-bar *") == []
