"""The one-time "Start here" screen at 360x740: shown on first login, one button, skippable, once."""

from pathlib import Path
from typing import Any

import pytest
import yaml

from backend.tests.e2e.conftest import CUT_OFF, DEMO_PASSWORD, MOBILE, link_acks_within

REPO_ROOT = Path(__file__).resolve().parents[3]
USERS = ["teacher.demo1", "teacher.demo2", "teacher.demo3"]


def _t(key: str, lang: str = "hi") -> str:
    path = REPO_ROOT / f"content/messages_{lang}.yaml"
    return str(yaml.safe_load(path.read_text(encoding="utf-8"))[key]["text"])


@pytest.mark.parametrize("user", USERS)
def test_first_login_shows_the_screen_and_the_button_opens_the_right_step(
    open_chat: Any, user: str
) -> None:
    teacher = open_chat(user, viewport=MOBILE, skip_start=False)
    page = teacher.page
    assert page.url.endswith("/teacher/start"), "a first login lands on the Start here screen"
    # three short lines, one large button, a small Skip, nothing cut off, under 80 words
    assert page.locator(".start-lines li").count() == 3
    words = len(page.inner_text("main").split())
    assert words < 80, words
    button = page.locator("#start-go")
    assert button.inner_text().strip() == _t("ui_start_button")
    assert button.bounding_box()["height"] >= 48  # type: ignore[index]
    assert page.locator("#start-skip").inner_text().strip() == _t("ui_start_skip")
    assert page.evaluate(CUT_OFF) == []
    # the button opens the chat at this account's own step, with a visible next action
    link_acks_within(page, button.tap, "**/teacher?s=1")
    page.wait_for_selector("#chat-input")
    page.wait_for_function(
        "() => document.getElementById('next-card') && !document.getElementById('next-card').hidden"
    )
    step = {"teacher.demo1": "", "teacher.demo2": "4 / 7", "teacher.demo3": "1 / 7"}[user]
    assert step in page.locator("#header-step").inner_text()
    # once: a reload (and the plain /teacher address) opens the chat, not the screen
    page.goto(f"{teacher.base}/teacher")
    page.wait_for_selector("#chat-input")
    assert not page.url.endswith("/teacher/start")


def test_skip_opens_the_chat_and_a_new_login_shows_the_screen_again(
    open_chat: Any, server: str
) -> None:
    teacher = open_chat("teacher.demo3", viewport=MOBILE, skip_start=False)
    page = teacher.page
    page.tap("#start-skip")
    page.wait_for_selector("#chat-input")
    page.goto(f"{server}/logout")
    # demo accounts are reset on login, so the screen comes back every time
    page.goto(f"{server}/login")
    page.fill("#username", "teacher.demo3")
    page.fill("#password", DEMO_PASSWORD)
    page.click("button[type=submit]")
    page.wait_for_url("**/teacher/start")
    assert page.locator("#start-go").is_visible()


def test_english_start_screen_is_plain_english(open_chat: Any) -> None:
    teacher = open_chat("teacher.demo1", viewport=MOBILE, skip_start=False)
    page = teacher.page
    page.goto(f"{teacher.base}/lang/en?next=/teacher/start")
    assert page.locator("#start-go").inner_text().strip() == _t("ui_start_button", "en")
    assert page.locator(".start-lines li").nth(1).inner_text().strip() == _t("ui_start_do", "en")
    assert page.evaluate(CUT_OFF) == []
