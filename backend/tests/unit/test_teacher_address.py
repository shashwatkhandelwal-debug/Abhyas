"""Child lines and teacher-facing text follow the onboarding choice (f = she, m = he), on the real
SessionService path with mocks (tagger scripted, no LLM)."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from test_one_on_one_flow import A, Harness, harness  # noqa: F401  (harness is a fixture)

from backend.app.core.messages import get_message
from backend.app.core.types import OutboundMessage
from backend.app.llm.roles.act_tagger import fallback_tag_act
from backend.app.llm.roles.child_voice import template_line
from backend.app.rule_engine.domain import ChildResponse, ChildState, Problem, ResponseKind

SUB = "NUM_SUB_REGROUP_BUNDLES"
LIT = "LIT_MATRA_BLENDING"
FEMALE_FORMS = ("दीदी", "मैडम")


async def _set_form(h: Harness, form: str) -> None:
    ctx = await h.ctx()
    ctx.address_form = form
    await h.service._sync_context_to_db(ctx, h.teacher_id)


def _child_lines(out: list[OutboundMessage]) -> list[str]:
    return [m.text_hi or "" for m in out if m.speaker not in (None, "coach", "teacher")]


def _check(lines: list[str], form: str) -> None:
    assert lines, "no child line was spoken"
    joined = " ".join(lines)
    if form == "m":
        assert not any(w in joined for w in FEMALE_FORMS), joined
        assert "सर" in joined, joined
    else:
        assert "सर," not in joined and not joined.startswith("सर"), joined
        assert any(w in joined for w in FEMALE_FORMS), joined


@pytest.mark.asyncio
@pytest.mark.parametrize("form", ["f", "m"])
async def test_one_on_one_child_addresses_teacher_by_choice(
    harness: Callable[[], Harness],  # noqa: F811
    form: str,
) -> None:
    h = harness()
    await h.start(SUB)
    await _set_form(h, form)
    await h.say(button="btn_listen")
    await h.say(button="btn_rehearse_one")
    await h.say(button="btn_child_ravi")
    await h.say("उल्टा घटा दिया, छोटी में से बड़ी")
    h.script += [([A.GIVE_NEW_PROBLEM], "ravi", Problem(type="sub", a=9000, b=17))]
    out = await h.say("रवि, अब 9000 में से 17 घटाओ।")
    lines = _child_lines(out)
    print(f"ONE-ON-ONE {form}: {lines}")
    _check(lines, form)


@pytest.mark.asyncio
@pytest.mark.parametrize("form", ["f", "m"])
async def test_group_children_address_teacher_by_choice(
    harness: Callable[[], Harness],  # noqa: F811
    form: str,
) -> None:
    h = harness()
    await h.start(LIT)
    await _set_form(h, form)
    await h.say(button="btn_listen")
    seen: list[str] = []
    for _ in range(4):
        h.script += [([A.OFF_TASK], None, None)]
        seen += _child_lines(await h.say("बाहर देखो, बारिश आ रही है।"))
        if any(w in " ".join(seen) for w in (*FEMALE_FORMS, "सर")):
            break
    print(f"GROUP {form}: {seen}")
    _check(seen, form)


@pytest.mark.parametrize("form", ["f", "m"])
def test_confused_template_line_follows_choice(form: str) -> None:
    line = template_line(
        ChildResponse(
            persona_id="ravi",
            kind=ResponseKind.CONFUSED,
            prior_state=ChildState.MISCONCEPTION,
            new_state=ChildState.MISCONCEPTION,
            affect="neutral",
            item=Problem(type="sub", a=52, b=17),
        ),
        None,
        0,
        form,
    )
    assert line.startswith("सर," if form == "m" else "दीदी,")


@pytest.mark.parametrize("form", ["f", "m"])
def test_hindi_teacher_facing_lines_have_matching_form(form: str) -> None:
    consent = get_message("consent_details", form)
    hint = get_message("hint_model", form, listen="सुनें", skip="छोड़ें")
    if form == "m":
        assert "चुनते हैं" in consent and "चुनती हैं" not in consent
        assert "शिक्षिका" not in hint and "करते हैं" in hint
    else:
        assert "चुनती हैं" in consent and "शिक्षिका" in hint


@pytest.mark.parametrize("form", ["f", "m"])
def test_english_lines_are_neutral_for_both_choices(form: str) -> None:
    for key in ("consent_details", "hint_model", "ask_experience"):
        text = get_message(key, form, lang="en", listen="x", skip="y", name="N")
        assert text == get_message(key, "f", lang="en", listen="x", skip="y", name="N")
        assert "madam" not in text.lower() and "sir" not in text.lower()


@pytest.mark.parametrize(
    "line",
    ["देखो, मैं करके दिखाती हूँ — पहले 2 में से 7 नहीं गया", "देखो, मैं करके दिखाता हूँ — पहले 2 में से 7 नहीं गया"],
)
def test_keyword_tagger_reads_both_genders_of_model_step(line: str) -> None:
    out = fallback_tag_act(line, scene_persona_ids=["ravi"], current_item=None)
    assert A.MODEL_STEP_ALOUD in out.acts
