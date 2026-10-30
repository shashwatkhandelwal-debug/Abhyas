"""F3: the onboarding name step stores a name, not the sentence around it."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from test_state_machine import FakeSessionRepository

from backend.app.core.messages import get_message
from backend.app.core.name_extract import extract_name
from backend.app.core.types import InboundMessage
from backend.app.sessions.service import SessionService
from backend.app.sessions.state_machine import OnboardingStateEnum

CASES = [
    ("मेरा नाम रिया है।", "रिया"),
    ("मेरा नाम रिया है", "रिया"),
    ("मेरा नाम है रिया", "रिया"),
    ("मेरा नाम रिया", "रिया"),
    ("मैं रिया हूँ", "रिया"),
    ("मैं रिया हूं।", "रिया"),
    ("नाम रिया है", "रिया"),
    ("मुझे रिया कहते हैं", "रिया"),
    ("रिया है मेरा नाम", "रिया"),
    ("my name is Riya", "Riya"),
    ("My name is Riya.", "Riya"),
    ("i am Riya", "Riya"),
    ("I'm Riya Sharma", "Riya Sharma"),
    ("call me Riya", "Riya"),
    ("this is Riya", "Riya"),
    ("name is Riya", "Riya"),
    ("mera naam Riya hai", "Riya"),
    ("रिया", "रिया"),
    ("रिया।", "रिया"),
    ("रिया शर्मा", "रिया शर्मा"),
    ("रिया जी", "रिया"),
    ("रिया मैडम", "रिया"),
    ("रिया दीदी", "रिया"),
    ("Riya ma'am", "Riya"),
    ("सर", None),
    ("मेरा नाम रिया शर्मा जी है", "रिया शर्मा"),
    ("मेरा नाम रिया कुमारी शर्मा है", "रिया शर्मा"),  # first and last name
    ("  मेरा   नाम   रिया   है  ", "रिया"),
    ("मेरा नाम रिया है!!", "रिया"),
    ("रिया‍", None),
    ("हाँ, मेरा नाम रिया है", "रिया"),
    ("हाँ, मेरा नाम रिया है।", "रिया"),
    ("जी मेरा नाम रिया है", "रिया"),
    ("yes, my name is Riya", "Riya"),
]


@pytest.mark.parametrize(("text", "expected"), CASES)
def test_extract_name(text: str, expected: str | None) -> None:
    assert extract_name(text, "hi") == expected
    assert extract_name(text, "en") == expected


@pytest.mark.parametrize(
    "text",
    [
        "आज मैं स्कूल जा रही हूँ और बच्चों को पढ़ाना है",
        "this is a very long sentence about my school",
        "<b>रिया</b>",
        "मेरा नाम <script>alert(1)</script> है",
        "रिया 123",
        "मेरा नाम रिया 2 है",
        "",
        "   ",
        "।",
        "@#$%",
        "हाँ।",
        "हां",
        "जी",
        "नहीं",
        "ना",
        "ठीक है",
        "ok",
        "okay",
        "yes",
        "no",
        "hmm",
        "haan",
        "ji",
        "nahi",
        "theek hai",
    ],
)
def test_not_a_name_is_not_stored(text: str) -> None:
    assert extract_name(text, "hi") is None


def test_none_input() -> None:
    assert extract_name(None) is None


def test_the_result_is_nfc() -> None:
    import unicodedata

    decomposed = unicodedata.normalize("NFD", "मेरा नाम क्रिया है")
    out = extract_name(decomposed)
    assert out is not None and out == unicodedata.normalize("NFC", out)


def test_no_template_uses_safe_on_a_name() -> None:
    root = Path(__file__).resolve().parents[2] / "app" / "web" / "templates"
    for page in root.glob("*.html"):
        for line in page.read_text(encoding="utf-8").splitlines():
            if "|safe" in line.replace(" ", "") or "| safe" in line:
                assert "name" not in line.lower().replace("rubric", ""), (page.name, line)


async def _run(text: str) -> tuple[str | None, str, list[str]]:
    svc = SessionService(repository=FakeSessionRepository())
    tid = uuid4()
    ctx = await svc.get_or_create_context(tid)
    ctx.onboarding_state = OnboardingStateEnum.PROFILE_NAME
    await svc._sync_context_to_db(ctx, tid)
    out = await svc.handle_inbound(
        InboundMessage(
            channel="web",
            channel_msg_id="m1",
            teacher_id=tid,
            kind="text",
            text=text,
            received_at=datetime.now(UTC),
        )
    )
    ctx = await svc.get_or_create_context(tid)
    return ctx.name, ctx.onboarding_state.value, [m.text_hi or "" for m in out]


@pytest.mark.asyncio
async def test_the_service_stores_the_name_and_moves_on() -> None:
    name, state, said = await _run("मेरा नाम रिया है।")
    assert name == "रिया" and state == "PROFILE_ADDRESS"
    assert said == [get_message("ask_address_form", "f")]


@pytest.mark.asyncio
@pytest.mark.parametrize("text", ["हाँ।", "जी", "yes", "ok", "<b>रिया</b>", "आज मैं स्कूल जा रही हूँ और बच्चों को पढ़ाना है"])
async def test_the_service_asks_again_and_stores_nothing(text: str) -> None:
    name, state, said = await _run(text)
    assert not name and state == "PROFILE_NAME"
    assert said == [get_message("ask_name_again", "f")]
