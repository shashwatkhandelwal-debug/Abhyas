"""Ask-the-handbook chips in a real browser: a tap must visibly do something, at once, everywhere.

Reproduces the first-use report ("tapping appears to do nothing") on demo1 (idle chat) and demo2
(inside the one-on-one scene), in Hindi and English, on a phone and a desktop viewport: the
question bubble shows at once and is in view, the chip says "Sending...", the typing bubble says
the handbook is being searched, and the cited answer arrives in view. In the scene the reply also
says how to go back. Also: a stale cached chat.js can no longer be used by a page of a new build.
"""

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

from backend.tests.e2e.conftest import DESKTOP, MOBILE, open_sheet

REPO_ROOT = Path(__file__).resolve().parents[3]
FEEDBACK_WITHIN_MS = 300
ANSWER_WITHIN_MS = 20_000


def _catalog(lang: str) -> dict[str, Any]:
    path = REPO_ROOT / f"content/messages_{lang}.yaml"
    return dict(yaml.safe_load(path.read_text(encoding="utf-8")))


def _text(lang: str, key: str) -> str:
    return str(_catalog(lang)[key]["text"])


# A row's top edge is inside the thread's visible area (not scrolled off, not under the tray)
IN_VIEW = """(row) => {
  const box = document.getElementById('chat-messages').getBoundingClientRect();
  const r = row.getBoundingClientRect();
  return r.top >= box.top - 1 && r.top < box.bottom - 8 && r.bottom > box.top;
}"""

CASES = [
    pytest.param("teacher.demo1", "hi", MOBILE, "light", id="demo1-hi-mobile"),
    pytest.param("teacher.demo1", "en", DESKTOP, "light", id="demo1-en-desktop"),
    pytest.param("teacher.demo2", "hi", MOBILE, "dark", id="demo2-hi-mobile-dark"),
    pytest.param("teacher.demo2", "en", DESKTOP, "light", id="demo2-en-desktop"),
]


@pytest.mark.parametrize(("user", "lang", "viewport", "scheme"), CASES)
def test_chip_tap_shows_question_typing_and_cited_answer(
    open_chat: Any, user: str, lang: str, viewport: dict[str, int], scheme: str
) -> None:
    teacher = open_chat(user, lang=lang, viewport=viewport, scheme=scheme)
    page = teacher.page
    chips = page.locator(".handbook-chip[data-id]")
    assert chips.count() >= 1, "the handbook chips are on the page (in a scene too)"
    open_sheet(page)
    chip = chips.first
    before = page.locator(".msg-row").count()

    chip.tap() if viewport["width"] < 500 else chip.click()

    # within 300 ms: the question bubble is in view, the chip and the typing bubble say what is going on
    page.wait_for_function(
        "(n) => document.querySelectorAll('.msg-row').length > n",
        arg=before,
        timeout=FEEDBACK_WITHIN_MS,
    )
    question_row = page.locator(".msg-row.inbound").last
    assert page.evaluate(IN_VIEW, question_row.element_handle()), "the question bubble is in view"
    assert chip.inner_text().strip() == _text(lang, "ui_chat_msg_sending")
    page.wait_for_function(
        "() => document.getElementById('pending-bubble').classList.contains('active')",
        timeout=FEEDBACK_WITHIN_MS,
    )
    assert page.locator("#pending-text").inner_text().strip() == _text(
        lang, "ui_chat_typing_handbook"
    )

    # then: a tick on the chip, and the cited answer in view
    page.wait_for_function(
        "() => document.querySelector('.handbook-chip.sent') !== null", timeout=5000
    )
    answer = page.locator(".msg-row.outbound:has(.source-chip)").last
    answer.wait_for(timeout=ANSWER_WITHIN_MS)
    assert answer.locator(".source-chip").count() >= 1, "the answer carries a citation"
    assert page.evaluate(IN_VIEW, answer.element_handle()), "the answer bubble is in view"
    assert not page.locator("#pending-bubble.active").count(), "typing indicator cleared"

    if user == "teacher.demo2":
        # in the scene the last bubble says who she is talking to and what to do next
        ravi = "Ravi" if lang == "en" else "रवि"
        page.wait_for_function(
            "(t) => { const rows = [...document.querySelectorAll('.msg-row.outbound')];"
            " return rows.length > 0 && rows[rows.length - 1].innerText.includes(t); }",
            arg=ravi,
            timeout=ANSWER_WITHIN_MS,
        )
    # the chips come back once the tick has been shown
    page.wait_for_function(
        "() => document.querySelectorAll('.handbook-chip[disabled]').length === 0", timeout=5000
    )
    assert teacher.errors == []


def test_stale_cached_chat_js_cannot_break_a_new_build(open_chat: Any) -> None:
    """The first load after a deploy used to run last deploy's cached chat.js against the new HTML."""
    teacher = open_chat("teacher.demo1", viewport=MOBILE)
    page = teacher.page
    page.wait_for_function("() => navigator.serviceWorker.controller !== null", timeout=10_000)
    # Poison every cache the way an older build left it: a chat.js with no chip handler, by its bare
    # URL (what an older page asked for) and under the current versioned URL's neighbours.
    poisoned = page.evaluate(
        """async () => {
          const stale = () => new Response('window.__STALE = true;', {headers: {'Content-Type': 'application/javascript'}});
          let n = 0;
          for (const key of await caches.keys()) {
            const cache = await caches.open(key);
            for (const req of await cache.keys()) {
              if (/\\/static\\/chat\\.js/.test(req.url)) { await cache.put(req.url.split('?')[0], stale()); n++; }
            }
          }
          return n;
        }"""
    )
    assert poisoned >= 1
    page.reload()
    page.wait_for_load_state("networkidle")
    assert page.evaluate("typeof setupHandbookChips") == "function", "the new chat.js ran"
    assert page.evaluate("window.__STALE === undefined")
    script_src = page.locator("script[src*='chat.js']").get_attribute("src") or ""
    assert re.search(r"chat\.js\?v=[\w-]+$", script_src), script_src
    before = page.locator(".msg-row").count()
    open_sheet(page)
    page.locator(".handbook-chip[data-id]").first.tap()
    page.wait_for_function(
        "(n) => document.querySelectorAll('.msg-row').length > n",
        arg=before,
        timeout=FEEDBACK_WITHIN_MS,
    )
