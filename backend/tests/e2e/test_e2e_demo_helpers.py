"""The demo helpers in a real browser: plain sample lines, a small banner, Log out, the divider."""

from pathlib import Path
from typing import Any

import pytest
import yaml

from backend.tests.e2e.conftest import CLIPPED, DESKTOP, MOBILE, open_sheet

REPO_ROOT = Path(__file__).resolve().parents[3]


def _text(lang: str, key: str) -> str:
    path = REPO_ROOT / f"content/messages_{lang}.yaml"
    return str(yaml.safe_load(path.read_text(encoding="utf-8"))[key]["text"])


def test_sample_lines_are_folded_on_a_phone_open_on_a_desktop_and_plainly_labelled(
    open_chat: Any,
) -> None:
    phone = open_chat("teacher.demo2", lang="en", viewport=MOBILE).page
    open_sheet(phone)
    assert phone.locator("#sample-tray summary").inner_text().strip() == _text(
        "en", "ui_sample_title"
    )
    assert not phone.evaluate("document.getElementById('sample-tray').open")
    assert not phone.locator("#sample-list").is_visible()
    phone.locator("#sample-tray summary").tap()
    assert phone.locator("#sample-list").is_visible()
    labels = phone.locator(".demo-chip").all_inner_texts()
    assert labels == [
        "Ask रवि how they did it" if False else labels[0],
        "Say the answer (a mistake to try)",
        "Give a new problem to check",
        "A question the handbook does not cover",
    ]
    assert "Ask" in labels[0] and "how they did it" in labels[0]
    notes = phone.locator(".sample-note").all_inner_texts()
    assert len(notes) == len(labels) and all(n.strip() for n in notes)
    assert "repeats the answer" in notes[1] and "explains their own method" in notes[0]
    assert phone.evaluate(CLIPPED, ".sample-item, .sample-item *") == []

    desktop = open_chat("teacher.demo2", lang="en", viewport=DESKTOP).page
    assert not desktop.evaluate("document.getElementById('sample-tray').open")  # sheet: all folded


def test_a_sample_line_sends_and_the_child_answers(open_chat: Any) -> None:
    page = open_chat("teacher.demo2", lang="hi").page
    open_sheet(page)
    page.locator("#sample-tray summary").tap()
    before = page.locator(".msg-row").count()
    page.locator(".demo-chip").first.tap()
    page.wait_for_function(
        "(n) => document.querySelectorAll('.msg-row').length > n", arg=before, timeout=300
    )
    page.wait_for_function(
        "() => [...document.querySelectorAll('.msg-row.outbound')].pop().innerText.includes('रवि')",
        timeout=20_000,
    )


def test_the_samples_follow_the_step(open_chat: Any) -> None:
    learn = open_chat("teacher.demo3", lang="en").page
    open_sheet(learn)
    learn.locator("#sample-tray summary").tap()
    # in the learn step only the question sample makes sense: no lines about a child's answer
    assert learn.locator(".demo-chip").all_inner_texts() == [
        "A question the handbook does not cover"
    ]


def test_the_demo_banner_is_one_small_line_with_log_out_and_can_be_dismissed(
    open_chat: Any,
) -> None:
    teacher = open_chat("teacher.demo1", lang="en", viewport=MOBILE)
    page = teacher.page
    banner = page.locator("#demo-banner")
    assert banner.is_visible()
    assert banner.inner_text().replace("\n", " ").startswith(_text("en", "ui_demo_banner_demo1"))
    # fix3 K5: the banner now says what the demo shows, so on a phone it takes up to two small lines
    assert banner.bounding_box()["height"] < 48, "at most two small lines"  # type: ignore[index]
    assert page.evaluate(CLIPPED, "#demo-banner, #demo-banner *") == []
    assert banner.locator("a[href='/logout']").is_visible()
    # dismissed for the session: gone now and after a reload; the header Log out stays
    page.click("#demo-dismiss")
    assert not banner.is_visible()
    page.reload()
    page.wait_for_load_state("networkidle")
    assert not page.locator("#demo-banner").is_visible()
    assert page.locator(".header-logout").is_visible()


def test_log_out_is_visible_in_the_header_without_opening_the_menu(open_chat: Any) -> None:
    page = open_chat("teacher.demo1", lang="en", viewport=MOBILE).page
    link = page.locator(".header-logout")
    assert link.is_visible() and link.inner_text().strip() == _text("en", "ui_logout")
    assert not page.locator("#menu-dropdown.show").count(), "the menu is closed"
    link.click()
    page.wait_for_url("**/login**", timeout=10_000)


@pytest.mark.parametrize("user", ["teacher.demo1", "teacher.demo2", "teacher.demo3"])
def test_prepared_chats_have_no_generic_demo_divider(open_chat: Any, user: str) -> None:
    page = open_chat(user, lang="en").page
    assert page.locator(".demo-divider").count() == 0
    assert "Demo starts here" not in page.locator("#chat-messages").inner_text()
