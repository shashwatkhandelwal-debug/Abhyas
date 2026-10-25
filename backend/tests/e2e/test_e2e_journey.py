"""The whole first-time teacher journey at 360x740, on each demo account.

Log in, read the screen, tap a handbook chip, tap a sample line, work through the practice, open My
class and the module picker, log out. The run fails if any tap shows nothing within 300 ms, if any
visible text is cut off, or if a step arrives without a visible next action. Mock providers; Hindi UI
(what the judges see first).
"""

from pathlib import Path
from typing import Any

import pytest
import yaml

from backend.tests.e2e.conftest import (
    CUT_OFF,
    MOBILE,
    link_acks_within,
    tap_and_expect,
    tap_reply,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
NEW_ROW = "(n) => document.querySelectorAll('.msg-row').length > n"
FEEDBACK_SEEN = "(t) => [...document.querySelectorAll('.msg-row.outbound')].some((r) => r.innerText.includes(t))"


def _t(key: str) -> str:
    path = REPO_ROOT / "content/messages_hi.yaml"
    return str(yaml.safe_load(path.read_text(encoding="utf-8"))[key]["text"])


def fits(page: Any, where: str) -> None:
    cut = page.evaluate(CUT_OFF)
    assert cut == [], f"text cut off on {where}: {cut}"


def has_next_action(page: Any, where: str) -> None:
    card = page.locator("#next-card")
    try:
        card.wait_for(
            state="visible", timeout=8000
        )  # the reply (and the step) may still be on its way
    except Exception:
        pass
    assert card.is_visible() and page.locator("#next-text").inner_text().strip(), (
        f"no visible next action on {where}"
    )


def settle(page: Any) -> None:
    page.wait_for_function(
        "() => !document.querySelector('#pending-bubble.active')", timeout=30_000
    )
    page.wait_for_timeout(1800)  # the reply bubble is rendered by the next poll


def say(page: Any, text: str) -> None:
    page.fill("#chat-input", text)
    before = page.locator(".msg-row").count()
    tap_and_expect(page, lambda: page.press("#chat-input", "Enter"), NEW_ROW, before)
    settle(page)


def tap_handbook_chip(page: Any) -> None:
    chip = page.locator(".handbook-chip[data-id]").first
    before = page.locator(".msg-row").count()
    tap_and_expect(page, chip.tap, NEW_ROW, before)
    page.wait_for_selector(".msg-row.outbound:has(.source-chip)", timeout=30_000)
    page.wait_for_function(
        "() => !document.querySelector('.handbook-chip[disabled]')", timeout=10_000
    )
    settle(page)


def tap_sample_line(page: Any) -> None:
    summary = page.locator("#sample-tray summary")
    tap_and_expect(page, summary.tap, "() => document.getElementById('sample-tray').open")
    chip = page.locator(".demo-chip").first
    before = page.locator(".msg-row").count()
    tap_and_expect(page, chip.tap, NEW_ROW, before)
    settle(page)


def end_practice_and_wait_for_feedback(page: Any) -> None:
    page.once("dialog", lambda d: d.accept())
    page.click("#sh-end")
    page.wait_for_function(FEEDBACK_SEEN, arg=_t("feedback_header"), timeout=40_000)
    settle(page)


def open_pages_and_log_out(page: Any, base: str) -> None:
    """My class and the module picker through the menu, then Log out from the header."""
    for label_key, path in (
        ("ui_menu_my_class", "/teacher/class"),
        ("ui_chat_menu_modules", "/teacher/modules"),
    ):
        tap_and_expect(
            page,
            page.locator("#menu-toggle-btn").tap,
            "() => document.getElementById('menu-dropdown').classList.contains('show')",
        )
        link = page.locator("#menu-dropdown a", has_text=_t(label_key))
        link_acks_within(page, link.tap, f"**{path}")
        page.wait_for_load_state("networkidle")
        fits(page, path)
        page.goto(f"{base}/teacher")  # back to the chat for the next page
        page.wait_for_selector("#chat-input")
    link_acks_within(page, page.locator(".header-logout").tap, "**/login**")
    fits(page, "the login page")


def test_demo2_one_on_one_journey(open_chat: Any, server: str) -> None:
    """demo2 opens inside a one-on-one scene: read, ask the handbook, a sample line, finish it."""
    page = open_chat("teacher.demo2", viewport=MOBILE).page
    fits(page, "demo2 on arrival")
    has_next_action(page, "demo2 on arrival")
    tap_handbook_chip(page)
    fits(page, "demo2 after a handbook answer")
    tap_sample_line(page)
    fits(page, "demo2 after a sample line")
    # she has now spoken twice (the seeded first line and the sample): End practice
    end_practice_and_wait_for_feedback(page)
    fits(page, "demo2 feedback")
    has_next_action(page, "demo2 feedback")
    open_pages_and_log_out(page, server)


def test_demo3_group_scene_journey(open_chat: Any, server: str) -> None:
    """demo3 opens at the learn step of a reading move: learn, say it back, a group scene, feedback."""
    page = open_chat("teacher.demo3", viewport=MOBILE).page
    fits(page, "demo3 on arrival")
    has_next_action(page, "demo3 on arrival")
    tap_handbook_chip(page)
    tap_reply(page, _t("btn_understood"))
    has_next_action(page, "demo3 say-it-back step")
    tap_sample_line(page)  # in the say-it-back step the sample is the explain-the-move line
    has_next_action(page, "demo3 model step")
    tap_reply(page, _t("btn_skip"))
    has_next_action(page, "demo3 scene")
    fits(page, "demo3 scene")
    say(page, "रवि, तुमने यह शब्द कैसे पढ़ा?")
    say(page, "प्रिया, तुम बताओ, यह शब्द कैसे पढ़ा?")
    say(page, "अमन, तुम भी बताओ।")  # a group scene needs three lines before the coach speaks
    end_practice_and_wait_for_feedback(page)
    fits(page, "demo3 feedback")
    open_pages_and_log_out(page, server)


def test_demo1_first_time_teacher_from_hello_to_feedback(open_chat: Any, server: str) -> None:
    """demo1 is a brand-new teacher: hello, consent, profile, placement, then the first practice."""
    page = open_chat("teacher.demo1", viewport=MOBILE).page
    fits(page, "demo1 on arrival")
    has_next_action(page, "demo1 on arrival")
    tap_handbook_chip(page)
    say(page, "नमस्ते")
    has_next_action(page, "consent")
    tap_reply(page, _t("btn_agree"))
    has_next_action(page, "join code")
    say(page, "नहीं")  # no join code: the real database path (this used to be a server error)
    assert "तकनीकी" not in page.inner_text("#chat-messages")
    has_next_action(page, "name")
    say(page, "सुमन")
    has_next_action(page, "address")
    tap_reply(page, _t("btn_female"))
    has_next_action(page, "experience")
    say(page, "2-5 साल")  # free words: stored as a band (this used to be a server error)
    assert "तकनीकी" not in page.inner_text("#chat-messages")
    has_next_action(page, "classes")
    say(page, "2")
    has_next_action(page, "placement")
    say(page, "रवि, तुमने 52 में से 17 कैसे घटाया?")
    say(page, "तुमने बंडल खोलकर देखा क्या?")
    has_next_action(page, "learn")
    fits(page, "the learn step")
    tap_reply(page, _t("btn_understood"))
    has_next_action(page, "say it back")
    tap_reply(page, _t("btn_skip"))
    has_next_action(page, "model")
    tap_reply(page, _t("btn_skip"))
    has_next_action(page, "choose who to practise with")
    tap_reply(page, _t("btn_rehearse_one"))
    has_next_action(page, "choose the child")
    tap_reply(page, _t("btn_child_ravi"))
    has_next_action(page, "diagnose")
    tap_reply(page, _t("btn_skip"))  # skip the diagnosis: the scene starts
    has_next_action(page, "the scene")
    fits(page, "the scene")
    tap_sample_line(page)  # a sample line is one of her two lines
    say(page, "आओ बंडल से बनाते हैं: 4 बंडल और 3 तीलियाँ। अब 27 निकालो।")
    end_practice_and_wait_for_feedback(page)
    fits(page, "feedback")
    has_next_action(page, "feedback")
    open_pages_and_log_out(page, server)


@pytest.mark.parametrize("user", ["teacher.demo1", "teacher.demo2", "teacher.demo3"])
def test_english_ui_arrival_is_whole_and_has_a_next_action(open_chat: Any, user: str) -> None:
    page = open_chat(user, viewport=MOBILE, lang="en").page
    fits(page, f"{user} in English")
    has_next_action(page, f"{user} in English")
