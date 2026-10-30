"""Experience-aware start (flag FAST_START_ENABLED).

A teacher in one of the higher onboarding experience bands (`FAST_START_BANDS`, default 6-10 and
10+ years) sees [सीधे अभ्यास] next to the learn-step buttons when a move starts, with the line that
she can begin with practice and look at the key points at any time. Choosing it opens the practice
set-up and keeps [मुख्य बातें देखें] on that screen. New teachers (0-1 and 2-5 years) see nothing
different: model practice stays first for them.

The learn step is not marked done for a fast start. That is the same marker a check-in jump to
practice leaves (`checkin_jump_move`), so the module progress counts only the trainer view shows
skip the learn step, and nothing else changes in any score.
"""

from __future__ import annotations

from backend.app.class_profile.library import citations
from backend.app.config import settings, v2_enabled
from backend.app.content_models import MoveCard
from backend.app.core.messages import get_message, get_ui_lang
from backend.app.core.types import Button, OutboundMessage

BTN_FAST = "btn_fast_start"
BTN_KEYPOINTS = "btn_fast_keypoints"
ALL_BUTTONS = (BTN_FAST, BTN_KEYPOINTS)


def enabled() -> bool:
    return v2_enabled(settings.FAST_START_ENABLED)


def eligible(experience_band: str | None) -> bool:
    return enabled() and experience_band in settings.FAST_START_BANDS


def fast_button(address_form: str = "f") -> Button:
    return Button(id=BTN_FAST, title_hi=get_message(BTN_FAST, address_form))


def keypoints_button(address_form: str = "f") -> Button:
    return Button(id=BTN_KEYPOINTS, title_hi=get_message(BTN_KEYPOINTS, address_form))


def note(address_form: str = "f") -> str:
    return get_message("fast_start_note", address_form)


def add_keypoints_button(
    messages: list[OutboundMessage], address_form: str = "f"
) -> list[OutboundMessage]:
    """The set-up screen keeps [मुख्य बातें देखें]: on the last message, whatever its kind."""
    if not messages:
        return messages
    last = messages[-1]
    buttons = [*last.buttons, keypoints_button(address_form)]
    messages[-1] = last.model_copy(update={"kind": "buttons", "buttons": buttons})
    return messages


def keypoints_message(
    move: MoveCard, address_form: str = "f", extra_buttons: list[Button] | None = None
) -> OutboundMessage:
    """The move's key points in her language, with the stored sources of the ones that have any."""
    english = get_ui_lang() == "en"
    lines = [get_message("fast_keypoints_head", address_form)]
    sources: list[str] = []
    for i, kp in enumerate(move.key_points, 1):
        lines.append(f"{i}. {(kp.text_en or kp.text_hi) if english else kp.text_hi}")
        for c in citations(kp.source_chunk_ids):
            label = c.label_hi()
            if label not in sources:
                sources.append(label)
    if sources:
        lines.append(
            get_message("fast_keypoints_sources", address_form, sources="; ".join(sources))
        )
    return OutboundMessage(
        kind="buttons" if extra_buttons else "text",
        text_hi="\n".join(lines),
        buttons=[*(extra_buttons or []), keypoints_button(address_form)] if extra_buttons else [],
    )


__all__ = [
    "ALL_BUTTONS",
    "BTN_FAST",
    "BTN_KEYPOINTS",
    "add_keypoints_button",
    "eligible",
    "enabled",
    "fast_button",
    "keypoints_button",
    "keypoints_message",
    "note",
]
