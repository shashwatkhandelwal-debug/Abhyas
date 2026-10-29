"""How a button screen is rendered on WhatsApp (the web chat shows `msg.buttons` as written).

Meta allows at most `WHATSAPP_REPLY_BUTTONS_MAX` reply buttons per message and
`WHATSAPP_BUTTON_TITLE_MAX` characters per title. A screen with more options goes out as one
interactive list (the client cuts it at `WHATSAPP_LIST_ROWS_MAX` rows; no screen in the repo has
more than `CHECKIN_MAX_BUTTONS`). Titles are shortened here only; the web keeps them.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.app.config import settings
from backend.app.core.types import Button

_REPLAY = "btn_replay"


@dataclass
class ButtonPlan:
    """Either one reply-button message, or one list message (never both)."""

    reply_buttons: list[tuple[str, str]] = field(default_factory=list)
    list_rows: list[tuple[str, str, str | None]] = field(default_factory=list)


def _title(title: str) -> str:
    return title[: settings.WHATSAPP_BUTTON_TITLE_MAX]


def plan_buttons(buttons: list[Button], *, has_audio: bool) -> ButtonPlan:
    """Reply buttons when they fit, else list rows; the replay button needs an audio to replay."""
    kept = [b for b in buttons if not (b.id == _REPLAY and not has_audio)]
    if len(kept) <= settings.WHATSAPP_REPLY_BUTTONS_MAX:
        return ButtonPlan(reply_buttons=[(b.id, _title(b.title_hi)) for b in kept])
    return ButtonPlan(list_rows=[(b.id, _title(b.title_hi), None) for b in kept])


__all__ = ["ButtonPlan", "plan_buttons"]
