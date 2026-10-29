"""Cause and effect in the scene, in a real browser on the real database: tell Ravi the answer
(he repeats it), give a new problem (he slips back), end the practice: the first line of the
feedback says what happened."""

from pathlib import Path
from typing import Any

import yaml

from backend.tests.e2e.conftest import MOBILE, open_sheet

REPO_ROOT = Path(__file__).resolve().parents[3]


def _t(key: str, **fmt: str) -> str:
    path = REPO_ROOT / "content/messages_hi.yaml"
    return str(yaml.safe_load(path.read_text(encoding="utf-8"))[key]["text"]).format(**fmt)


def test_telling_the_answer_is_named_in_the_first_line_of_the_feedback(open_chat: Any) -> None:
    page = open_chat("teacher.demo2", viewport=MOBILE).page
    open_sheet(page)
    page.locator("#sample-tray summary").tap()
    page.locator(".demo-chip", has_text="उत्तर बता दें").tap()
    page.wait_for_function(
        "() => [...document.querySelectorAll('.msg-row.outbound')].pop().innerText.includes('16')",
        timeout=30_000,
    )
    page.wait_for_function("() => !document.querySelector('#pending-bubble.active')")
    open_sheet(page)  # a sent chip closes the sheet
    page.locator(".demo-chip", has_text="जाँचने के लिए नया सवाल").tap()
    page.wait_for_function("() => !document.querySelector('#pending-bubble.active')")
    page.wait_for_timeout(2500)
    page.once("dialog", lambda d: d.accept())
    page.click("#sh-end")
    told = _t("coach_outcome_told", child="रवि")
    page.wait_for_function(
        "(t) => [...document.querySelectorAll('.msg-row.outbound .bubble-text')].some((p) => p.innerText.startsWith(t))",
        arg=told,
        timeout=40_000,
    )
