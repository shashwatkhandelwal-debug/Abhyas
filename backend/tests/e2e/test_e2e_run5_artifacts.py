"""Full mock rehearsals to the end with "बस", in a real browser on the seeded database.

demo2 (subtraction): the board's bundles and sticks before and after the regroup, then the coach's
feedback with the quote badge. demo3 (literacy): the group scene to the end. The coach texts are
printed (run with -s) and, when RUN5_SHOTS_DIR is set, screenshots at 393x852 in both themes are
saved there. Without that variable the test only asserts.
"""

import os
from pathlib import Path
from typing import Any

import pytest

from backend.tests.e2e.conftest import tap_reply
from backend.tests.e2e.test_e2e_journey import (
    _t,
    end_practice_and_wait_for_feedback,
    say,
    tap_sample_line,
)

VIEWPORT = {"width": 393, "height": 852}
SHOTS = os.environ.get("RUN5_SHOTS_DIR", "")
REGROUP_LINE = "देखो, ये 4 बंडल और 3 खुली तीलियाँ हैं, 3 में से 7 नहीं निकलतीं, तो एक बंडल खोलो।"
LAST_COACH = """() => {
  const rows = [...document.querySelectorAll('.msg-row.outbound')];
  const out = rows.filter((r) => r.querySelector('.bubble-text')).map((r) => r.querySelector('.bubble-text').innerText);
  return out;
}"""
BOARD = "() => document.getElementById('sb-manipulatives').getAttribute('aria-label')"
COUNTS = """() => ({
  bundles: document.querySelectorAll('#sb-manipulatives .drawn-bundle').length,
  sticks: document.querySelectorAll('#sb-manipulatives .drawn-stick').length,
  regrouped: document.getElementById('sb-manipulatives').classList.contains('regrouped'),
})"""


def _shot(page: Any, name: str) -> None:
    if SHOTS:
        Path(SHOTS).mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(Path(SHOTS) / f"{name}.png"))


def _feedback_texts(page: Any) -> list[str]:
    texts: list[str] = page.evaluate(LAST_COACH)
    header = _t("feedback_header")
    start = next(i for i, t in enumerate(texts) if header in t)
    return texts[start:]


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_demo2_subtraction_scene_to_the_end(open_chat: Any, scheme: str) -> None:
    page = open_chat("teacher.demo2", viewport=VIEWPORT, scheme=scheme).page
    before = page.evaluate(COUNTS)
    assert before == {"bundles": 4, "sticks": 3, "regrouped": False}, before
    print(f"\n[demo2 {scheme}] board before: {page.evaluate(BOARD)}")
    _shot(page, f"board_before_regroup_{scheme}")

    say(page, REGROUP_LINE)  # concrete representation: Ravi reaches PARTIAL, one bundle opens
    after = page.evaluate(COUNTS)
    assert after == {"bundles": 3, "sticks": 13, "regrouped": True}, after
    print(f"[demo2 {scheme}] board after: {page.evaluate(BOARD)}")
    _shot(page, f"board_after_regroup_{scheme}")

    end_practice_and_wait_for_feedback(page)
    texts = _feedback_texts(page)
    print(f"[demo2 {scheme}] coach feedback ({len(texts)} bubbles):")
    for text in texts:
        print("  | " + text.replace("\n", "\n  | "))
    badges = page.locator(".evidence-quote-badge").count()
    print(f"[demo2 {scheme}] quote badges on the page: {badges}")
    if badges:
        page.locator(".evidence-quote-badge").first.scroll_into_view_if_needed()
    _shot(page, f"coach_feedback_quote_badge_{scheme}")


def test_demo3_literacy_scene_to_the_end(open_chat: Any) -> None:
    page = open_chat("teacher.demo3", viewport=VIEWPORT).page
    tap_reply(page, _t("btn_understood"))
    tap_sample_line(page)  # the say-it-back step
    tap_reply(page, _t("btn_skip"))  # skip the model step: the group scene starts
    say(page, "रवि, तुमने यह शब्द कैसे पढ़ा?")
    say(page, "प्रिया, तुम बताओ, यह शब्द कैसे पढ़ा?")
    say(page, "अमन, तुम भी बताओ।")
    end_practice_and_wait_for_feedback(page)
    texts = _feedback_texts(page)
    print(f"\n[demo3] coach feedback ({len(texts)} bubbles):")
    for text in texts:
        print("  | " + text.replace("\n", "\n  | "))
    assert texts
