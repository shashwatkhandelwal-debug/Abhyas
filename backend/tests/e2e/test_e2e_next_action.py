"""The "what to do now" line above the composer, in a real browser."""

from pathlib import Path
from typing import Any

import pytest
import yaml

from backend.tests.e2e.conftest import CLIPPED, DESKTOP, MOBILE

REPO_ROOT = Path(__file__).resolve().parents[3]
LINES_IN_TEXT = """() => { const el = document.getElementById('next-text');
  return el.getBoundingClientRect().height / parseFloat(getComputedStyle(el).lineHeight); }"""


def _text(lang: str, key: str) -> str:
    path = REPO_ROOT / f"content/messages_{lang}.yaml"
    return str(yaml.safe_load(path.read_text(encoding="utf-8"))[key]["text"])


@pytest.mark.parametrize(
    ("lang", "viewport"),
    [("hi", MOBILE), ("en", MOBILE), ("en", DESKTOP)],
    ids=["hi", "en", "desktop"],
)
def test_learn_step_says_what_to_tap(open_chat: Any, lang: str, viewport: dict[str, int]) -> None:
    page = open_chat("teacher.demo3", lang=lang, viewport=viewport).page
    card = page.locator("#next-card")
    assert card.is_visible()
    button = _text(lang, "btn_understood")
    expected = _text(lang, "hint_learn").format(understood=button)
    assert page.locator("#next-text").inner_text().strip() == expected
    assert page.evaluate(LINES_IN_TEXT) <= 2.05, "never longer than two lines"
    assert page.evaluate(CLIPPED, "#next-card, #next-card *") == []
    # the button it names is on the page
    assert page.locator(".reply-chip", has_text=button).count() >= 1


def test_scene_line_says_how_to_keep_going_then_goes_once_she_speaks(open_chat: Any) -> None:
    page = open_chat("teacher.demo2", lang="en").page  # the seeded scene is already under way
    assert page.locator("#next-text").inner_text().strip() == _text(
        "en", "hint_scene_one_next"
    ).format(child="Ravi")
    suggest = page.locator("#next-suggest")
    line = "Ravi, let us make 43 with bundles of ten and loose sticks."
    assert suggest.inner_text().strip() == line
    assert page.evaluate(LINES_IN_TEXT) <= 2.05
    suggest.click()
    assert page.input_value("#chat-input") == line
    page.press("#chat-input", "Enter")
    page.wait_for_selector("#next-card", state="hidden", timeout=2000)
    page.wait_for_function(
        "() => [...document.querySelectorAll('.msg-row.outbound')].pop().innerText.includes('Ravi')",
        timeout=20_000,
    )
    page.wait_for_timeout(2500)  # a poll or two: it stays hidden
    assert not page.locator("#next-card").is_visible()


def test_a_new_teacher_is_told_to_say_hello_then_what_to_tap(open_chat: Any) -> None:
    page = open_chat("teacher.demo1", lang="en").page
    assert page.locator("#next-text").inner_text().strip() == _text("en", "hint_start")
    page.locator("#next-suggest").click()
    assert page.input_value("#chat-input") == _text("en", "hint_start_suggest")
    page.press("#chat-input", "Enter")
    agree = _text("en", "btn_agree")
    page.wait_for_function(
        "(t) => document.getElementById('next-text').innerText.includes(t)",
        arg=agree,
        timeout=20_000,
    )
    assert page.locator("#next-card").is_visible()
    assert page.locator(".reply-chip", has_text=agree).count() >= 1
