"""One language per line: no English wrapper glued to Hindi content, and no Hindi wrapper to English.

Walks the whole weekly loop (and the question flow from several steps) in each UI language and
checks every bot line. Hindi *content* (a move's key points, checklist, scene text, the coach's
words to the children) may appear in the English UI, but as its own block, never inside an English
sentence; the English UI never shows an English line with a Hindi sentence in the middle of it.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from test_state_machine import FakeSessionRepository

from backend.app.core.messages import reset_ui_lang, set_ui_lang
from backend.app.core.types import InboundMessage, OutboundMessage
from backend.app.sessions.service import SessionService

DEVANAGARI = re.compile("[ऀ-ॿ]")
# words that are really English (have a lower-case letter; ARP, FLN, NIPUN do not count)
ENGLISH_WORD = re.compile(r"\b[A-Za-z]*[a-z][A-Za-z]*\b")


def inbound(t: UUID, text: str | None = None, button: str | None = None) -> InboundMessage:
    return InboundMessage(
        channel="whatsapp",
        channel_msg_id=f"m-{uuid4().hex[:8]}",
        teacher_id=t,
        kind="button" if button else "text",
        text=text,
        button_id=button,
        received_at=datetime.now(UTC),
    )


def mixed_lines(messages: list[OutboundMessage], ui: str) -> list[str]:
    """Lines that carry both scripts as running text (two or more real English words and Devanagari)."""
    bad: list[str] = []
    for m in messages:
        for line in (m.text_hi or "").split("\n"):
            if not DEVANAGARI.search(line):
                continue
            words = [w for w in ENGLISH_WORD.findall(line) if len(w) >= 3]
            if len(words) >= 2:
                bad.append(line.strip()[:140])
        for b in m.buttons or []:
            if DEVANAGARI.search(b.title_hi) and len(ENGLISH_WORD.findall(b.title_hi)) >= 2:
                bad.append(f"button: {b.title_hi}")
    return bad


@pytest.fixture(params=["en", "hi"])
def ui(request: pytest.FixtureRequest) -> Iterator[str]:
    token = set_ui_lang(request.param)
    yield str(request.param)
    reset_ui_lang(token)


async def walk_the_week(service: SessionService, t: UUID) -> list[OutboundMessage]:
    """Everything the bot says from consent to the end of the week."""
    seen: list[OutboundMessage] = []

    async def say(text: str | None = None, button: str | None = None) -> None:
        seen.extend(await service.handle_inbound(inbound(t, text, button)))

    await say("hello")
    await say(button="btn_agree")
    await say("no")
    await say("Suman")
    await say(button="btn_female")
    await say("2-5 years")
    await say("2")
    await say(button="btn_yes")
    await say("Ravi, how did you get 45?")
    await say("Did you open a bundle?")
    await say(button="btn_understood")
    await say("The key idea is to ask the child to explain and to use bundles of ten.")
    await say(button="btn_listen")
    await say(button="btn_rehearse_group")
    await say("Ravi, how did you subtract?")
    await say("Show me with sticks.")
    await say("Priya, what do you think?")
    await say("stop")
    await say(button="btn_continue")
    await say(button="btn_peer")
    for _ in range(4):
        await say(button="btn_yes")
    await say("4")
    await say(button="btn_trate_skip")
    return seen


async def test_the_whole_week_has_one_language_per_line(ui: str) -> None:
    service = SessionService(repository=FakeSessionRepository())
    seen = await walk_the_week(service, uuid4())
    assert len(seen) > 20
    assert mixed_lines(seen, ui) == []


@pytest.mark.parametrize("state_button", [None, "btn_understood", "btn_listen"])
async def test_the_question_flow_resumes_in_one_language(ui: str, state_button: str | None) -> None:
    """Ask a question from the learn, say-it-back and model steps: the answer, then "carry on"."""
    service = SessionService(repository=FakeSessionRepository())
    t = uuid4()
    for text, button in (
        ("hello", None),
        (None, "btn_agree"),
        ("no", None),
        ("Suman", None),
        (None, "btn_female"),
        ("2-5 years", None),
        ("2", None),
        (None, "btn_yes"),
        ("Ravi, how did you get 45?", None),
        ("Did you open a bundle?", None),
    ):
        await service.handle_inbound(inbound(t, text, button))
    if state_button == "btn_listen":
        await service.handle_inbound(inbound(t, None, "btn_understood"))
        await service.handle_inbound(inbound(t, "Ask to explain and use bundles of ten.", None))
    elif state_button:
        await service.handle_inbound(inbound(t, None, state_button))
    out = await service.handle_inbound(inbound(t, "question: how do I involve parents?", None))
    assert len(out) >= 2
    assert mixed_lines(out, ui) == []


async def test_the_question_the_handbook_does_not_cover_says_what_happens_next(ui: str) -> None:
    """The sample question is sent from the learn step: the reply must be the question flow (not "tap
    the buttons"), must not guess, and must say in one sentence that the ARP will see it in her list."""
    from backend.app.core.messages import get_message
    from backend.app.web.demo_samples import _load

    sample = next(s for s in _load() if s["id"] == "s5_question_multigrade")
    assert sample["text_hi"].startswith("सवाल:"), "the ask keyword makes it a question in any step"
    service = SessionService(repository=FakeSessionRepository())
    t = uuid4()
    for text, button in (
        ("hello", None),
        (None, "btn_agree"),
        ("no", None),
        ("Suman", None),
        (None, "btn_female"),
        ("2-5 years", None),
        ("2", None),
        (None, "btn_yes"),
        ("Ravi, how did you get 45?", None),
        ("Did you open a bundle?", None),
    ):
        await service.handle_inbound(inbound(t, text, button))
    out = await service.handle_inbound(inbound(t, sample["text_hi"], None))
    spoken = "\n".join(m.text_hi or "" for m in out)
    review_list = {
        get_message("ask_escalated", "f"),
        get_message("ask_not_in_sources", "f"),
    }
    assert any(sentence in spoken for sentence in review_list), spoken[:300]
    assert "ARP" in spoken
    assert mixed_lines(out, ui) == []
