"""Button caps are per channel: web shows up to 5 titles as written, WhatsApp keeps Meta's limits."""

from __future__ import annotations

import json
from typing import Any

import pytest
import respx

from backend.app.channels.whatsapp.buttons import plan_buttons
from backend.app.channels.whatsapp.client import WhatsAppClient
from backend.app.class_profile import checkin_flow
from backend.app.config import settings
from backend.app.core.types import Button, OutboundMessage
from backend.app.sessions.state_machine import SessionContext

LONG = "यह शीर्षक बीस अक्षरों से बहुत लंबा है"  # 36 characters


def _five_option_screen() -> OutboundMessage:
    ctx = SessionContext(
        teacher_id="t", week_start="2026-10-19", current_move_id="NUM_SUB_REGROUP_BUNDLES"
    )
    msg = checkin_flow.start(ctx).messages[0]
    assert len(msg.buttons or []) == settings.CHECKIN_MAX_BUTTONS == 5
    return msg


def test_web_keeps_five_buttons_and_long_titles() -> None:
    msg = _five_option_screen()
    assert len(msg.buttons or []) == 5  # WebChannel persists `msg.buttons` unchanged
    wide = Button(id="x", title_hi=LONG)
    assert wide.title_hi == LONG and len(LONG) > settings.WHATSAPP_BUTTON_TITLE_MAX


def test_whatsapp_five_options_are_not_reply_buttons() -> None:
    plan = plan_buttons(_five_option_screen().buttons or [], has_audio=False)
    assert plan.reply_buttons == []  # never more than 3 reply buttons
    assert len(plan.list_rows) == 5  # the existing list pattern carries all five
    assert all(len(title) <= settings.WHATSAPP_BUTTON_TITLE_MAX for _, title, _ in plan.list_rows)


@pytest.mark.parametrize("n", [1, 2, 3])
def test_whatsapp_up_to_three_stay_reply_buttons(n: int) -> None:
    plan = plan_buttons([Button(id=f"b{i}", title_hi="ठीक") for i in range(n)], has_audio=False)
    assert len(plan.reply_buttons) == n and plan.list_rows == []


def test_whatsapp_replay_button_dropped_without_audio_and_can_fit_after() -> None:
    buttons = [Button(id=i, title_hi="ठीक") for i in ("btn_replay", "a", "b", "c")]
    assert len(plan_buttons(buttons, has_audio=False).reply_buttons) == 3
    assert len(plan_buttons(buttons, has_audio=True).list_rows) == 4


def test_long_titles_are_shortened_on_whatsapp_only() -> None:
    web = [Button(id=f"b{i}", title_hi=LONG) for i in range(2)]
    assert [b.title_hi for b in web] == [LONG, LONG]  # web: as written
    for count in (2, 5):  # reply-button path and list path
        buttons = [Button(id=f"b{i}", title_hi=LONG) for i in range(count)]
        plan = plan_buttons(buttons, has_audio=False)
        titles = [t for _, t in plan.reply_buttons] or [t for _, t, _ in plan.list_rows]
        assert titles == [LONG[: settings.WHATSAPP_BUTTON_TITLE_MAX]] * count


@pytest.mark.asyncio
@respx.mock
async def test_client_payload_respects_meta_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "WHATSAPP_ENABLED", True)
    monkeypatch.setattr(settings, "WHATSAPP_ACCESS_TOKEN", "EAAtesttoken123")
    monkeypatch.setattr(settings, "WHATSAPP_PHONE_NUMBER_ID", "pid")
    monkeypatch.setattr(settings, "WHATSAPP_GRAPH_VERSION", "v23.0")
    route = respx.post("https://graph.facebook.com/v23.0/pid/messages").respond(
        200, json={"messages": [{"id": "wamid.x"}]}
    )
    client = WhatsAppClient()
    plan = plan_buttons([Button(id=f"b{i}", title_hi=LONG) for i in range(5)], has_audio=False)
    await client.send_interactive_list("+919876543210", "चुनें", "विकल्प", plan.list_rows)
    await client.send_interactive_buttons(
        "+919876543210", "चुनें", [(f"b{i}", LONG) for i in range(5)]
    )
    lst: dict[str, Any] = json.loads(route.calls[0].request.read())["interactive"]
    rows = lst["action"]["sections"][0]["rows"]
    assert len(rows) == 5 and all(len(r["title"]) <= 20 for r in rows)
    btn: dict[str, Any] = json.loads(route.calls[1].request.read())["interactive"]
    sent = btn["action"]["buttons"]
    assert len(sent) == 3 and all(len(b["reply"]["title"]) <= 20 for b in sent)
