"""fix5: typed "tip off" / "tip on", and the subtraction explain-back matcher scored on a partial answer."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from test_one_on_one_flow import Harness, harness, texts  # noqa: F401

from backend.app.class_profile import focus
from backend.app.core.messages import get_message
from backend.app.llm.keypoints import match_key_points
from backend.app.llm.roles.fidelity_checker import compose_fidelity_reply, fallback_fidelity
from backend.app.rehearsal.scene_runner import load_move_card
from backend.app.sessions.state_machine import SessionStateEnum

# ── the daily tip ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("text", "button"),
    [
        ("tip off", focus.BTN_OFF),
        ("Tip Off", focus.BTN_OFF),
        ("daily tip off", focus.BTN_OFF),
        ("tip off.", focus.BTN_OFF),
        ("सुझाव बंद", focus.BTN_OFF),
        ("आज का सुझाव बंद", focus.BTN_OFF),
        ("tip on", focus.BTN_YES),
        ("daily tip on", focus.BTN_YES),
        ("सुझाव चालू", focus.BTN_YES),
    ],
)
def test_tip_commands_map_to_the_existing_buttons(text: str, button: str) -> None:
    assert focus.command_button(text) == button


@pytest.mark.parametrize(
    "text",
    ["tip", "turn the tip off please", "give me a tip", "tip off for the children", "", None],
)
def test_other_text_is_not_a_tip_command(text: str | None) -> None:
    assert focus.command_button(text) is None


@pytest.mark.asyncio
async def test_tip_off_and_on_change_the_opt_in_and_confirm_in_one_line(
    harness: Callable[[], Harness],  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("backend.app.config.settings.FOCUS_CARD_ENABLED", True)
    h = harness()
    await h.start("NUM_SUB_REGROUP_BUNDLES")
    ctx = await h.ctx()
    ctx.current_state = SessionStateEnum.LEARN
    await h.service._sync_context_to_db(ctx, h.teacher_id)
    teacher = await h.service.repo.get_or_create_teacher(h.teacher_id)
    teacher.tomorrow_focus_opt_in = True

    out = await h.say("tip off")
    assert texts(out) == get_message("focus_off_ack", "f")
    assert (await h.service.repo.get_or_create_teacher(h.teacher_id)).tomorrow_focus_opt_in is False

    out = await h.say("tip on")
    assert texts(out) == get_message("focus_on_ack", "f")
    assert (await h.service.repo.get_or_create_teacher(h.teacher_id)).tomorrow_focus_opt_in is True


# ── subtraction explain-back: a partial answer scores 2 of the key points ────

MOVE = load_move_card("NUM_SUB_REGROUP_BUNDLES")

# Says kp1 (children subtract the smaller from the larger; first ask how) and kp2 (bundles of 10 and
# loose sticks: 43 is 4 bundles and 3 sticks); says nothing of opening a bundle or the rest.
TWO_POINTS = (
    "जब इकाई में ऊपर की संख्या छोटी हो तो बच्चे बड़ी में से छोटी घटा देते हैं और उल्टा करते हैं, "
    "इसलिए पहले बच्चे से पूछें कि उसने कैसे किया, उसका तरीका क्या है। फिर 10-10 तीलियों के बंडल बनवाएँ, "
    "दहाई और इकाई दिखाएँ, जैसे 43 यानी 4 बंडल और 3 खुली तीलियाँ।"
)
OFF_TOPIC = "आज मौसम बहुत अच्छा था और बच्चे बाहर खेल रहे थे"


def test_explain_back_covering_two_points_scores_two() -> None:
    statuses = {m.id: m.status for m in match_key_points(MOVE, TWO_POINTS)}
    assert statuses["kp1"] == "covered" and statuses["kp2"] == "covered"
    assert [k for k, v in statuses.items() if v == "covered"] == ["kp1", "kp2"]
    assert all(statuses[k] == "missing" for k in ("kp3", "kp4", "kp5"))
    out = fallback_fidelity(MOVE, TWO_POINTS)
    reply = compose_fidelity_reply(MOVE, out)
    assert reply.startswith(
        get_message("fidelity_reply_summary", lang="hi", n_covered=2, n_total=len(MOVE.key_points))
    )


def test_off_topic_explain_back_scores_zero_on_the_subtraction_move() -> None:
    assert not [m for m in match_key_points(MOVE, OFF_TOPIC) if m.status != "missing"]
