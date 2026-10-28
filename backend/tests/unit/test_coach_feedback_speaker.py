"""The end-of-scene feedback on the real SessionService path: who speaks, and the «quote»."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from test_one_on_one_flow import A, Harness, harness, texts  # noqa: F401  (harness is a fixture)

from backend.app.core.messages import get_message
from backend.app.core.types import OutboundMessage

SUB = "NUM_SUB_REGROUP_BUNDLES"
LIT = "LIT_MATRA_BLENDING"


def dump(tag: str, out: list[OutboundMessage]) -> None:
    for i, m in enumerate(out):
        print(f"[{tag}] #{i} kind={m.kind} speaker={m.speaker!r} text={m.text_hi!r}")


async def sub_feedback(h: Harness) -> list[OutboundMessage]:
    await h.setup(SUB, "ravi", "उल्टा घटा दिया, छोटी में से बड़ी")
    h.script += [([A.ASK_TO_EXPLAIN], "ravi", None), ([A.CONCRETE_REPRESENTATION], "ravi", None)]
    await h.say("रवि, तुमने 43 में से 27 कैसे घटाया? मुझे एक-एक कदम बताओ।")
    await h.say("देखो, ये 4 बंडल और 3 खुली तीलियाँ हैं, तो एक बंडल खोलो।")
    return await h.say("बस")


async def lit_feedback(h: Harness) -> list[OutboundMessage]:
    await h.start(LIT)
    await h.say(button="btn_listen")
    h.script += [([A.ASK_TO_EXPLAIN], "ravi", None)] * 8
    for line in ("रवि, तुमने यह शब्द कैसे पढ़ा?", "प्रिया, तुम बताओ।", "अमन, तुम भी बताओ।"):
        await h.say(line)
    return await h.say("बस")


@pytest.mark.asyncio
async def test_one_on_one_feedback_is_a_coach_bubble_that_carries_the_quote(
    harness: Callable[[], Harness],  # noqa: F811
) -> None:
    out = await sub_feedback(harness())
    dump("sub", out)
    quoted = [m for m in out if "«" in (m.text_hi or "")]
    assert len(quoted) == 1, "exactly one bubble carries the teacher's quote"
    bubble = quoted[0]
    assert bubble.speaker == "coach"
    quote = "रवि, तुमने 43 में से 27 कैसे घटाया? मुझे एक-एक कदम बताओ।"
    assert get_message("coach_quote_suffix", quote=quote) in (bubble.text_hi or "")
    # the header line and the question after it stay plain system text
    header = next(m for m in out if m.text_hi == get_message("feedback_header", "f"))
    assert header.speaker is None
    assert all(m.speaker is None for m in out if m.kind == "buttons")


@pytest.mark.asyncio
async def test_group_literacy_feedback_has_no_quote_and_only_the_advice_bubble_is_coach(
    harness: Callable[[], Harness],  # noqa: F811
) -> None:
    out = await lit_feedback(harness())
    dump("lit", out)
    assert not any("«" in (m.text_hi or "") for m in out)  # quotes exist only in one-on-one
    advice = [m for m in out if m.text_hi and "👍" in m.text_hi]
    assert len(advice) == 1 and advice[0].speaker == "coach"
    assert all(
        m.speaker is None
        for m in out
        if m.text_hi and "👍" not in m.text_hi and m.kind == "buttons"
    )
