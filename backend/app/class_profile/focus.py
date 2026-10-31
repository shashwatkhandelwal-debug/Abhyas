"""Today's focus: one cited step when an opted-in teacher opens the chat (flag FOCUS_CARD_ENABLED).

Built on the existing `followup.tomorrow_focus` builder and `teacher.tomorrow_focus_opt_in`:

* After a check-in or a finished practice, the next time she opens the chat she is asked once
  (at most once in FOCUS_OFFER_INTERVAL_DAYS days): "show one short tip each day?" [yes] [not now].
* An opted-in teacher sees one "आज का सुझाव" message (one cited step from her last struggle) at most
  once a day (IST date), after any due follow-up. It ends with a next-step button and [turn off].
* Never during a scene she has started, and never without a stored citation.

When it was offered or shown is read from her own thread (the message carrying the focus buttons),
so no new column or context field exists. Only the web chat uses it today. Nothing is sent over
WhatsApp: a WhatsApp job would call `card_messages` for opted-in teachers inside the 24 hour window
(or an approved template), reusing the same builder; that is not built.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from backend.app.class_profile.followup import ist_date, tomorrow_focus
from backend.app.class_profile.library import StruggleLibrary, load_library
from backend.app.config import move_offered, settings, v2_enabled
from backend.app.core.messages import get_message
from backend.app.core.types import Button, OutboundMessage

BTN_YES = "btn_focus_yes"
BTN_NO = "btn_focus_no"
BTN_OFF = "btn_focus_off"
BTN_PRACTICE = "btn_focus_practice"
BTN_ASK = "btn_focus_ask"
ALL_BUTTONS = (BTN_YES, BTN_NO, BTN_OFF, BTN_PRACTICE, BTN_ASK)

# the buttons that identify a message in her thread
OFFER_MARKER = BTN_YES
CARD_MARKER = BTN_OFF


# Typed commands for the same two choices as the "Yes" and "Turn off" buttons (fix5)
_COMMAND = re.compile(
    r"^\s*(?:(?:daily|आज\s*का)\s+)?(?:tip|tips|सुझाव)\s+(?P<way>off|on|बंद|चालू)\s*[.!।]?\s*$",
    re.IGNORECASE,
)


def command_button(text: str | None) -> str | None:
    """ "tip off" / "tip on" (also "daily tip off", "सुझाव बंद") as the button it stands for."""
    m = _COMMAND.match(unicodedata.normalize("NFC", text or ""))
    if m is None:
        return None
    return BTN_OFF if m.group("way").lower() in ("off", "बंद") else BTN_YES


def enabled() -> bool:
    return v2_enabled(settings.FOCUS_CARD_ENABLED)


def offer_due(
    *, opted_in: bool, has_activity: bool, last_offer_at: datetime | None, now: datetime
) -> bool:
    """Ask once a week at most, only after a check-in or a finished practice, never twice."""
    if opted_in or not has_activity:
        return False
    if last_offer_at is None:
        return True
    return now - last_offer_at >= timedelta(days=settings.FOCUS_OFFER_INTERVAL_DAYS)


def card_due(*, opted_in: bool, last_card_at: datetime | None, now: datetime) -> bool:
    """One card per IST day for an opted-in teacher."""
    if not opted_in:
        return False
    return last_card_at is None or ist_date(last_card_at) < ist_date(now)


def offer_message(address_form: str = "f") -> OutboundMessage:
    return OutboundMessage(
        kind="buttons",
        text_hi=get_message("focus_offer", address_form),
        buttons=[
            Button(id=BTN_YES, title_hi=get_message(BTN_YES, address_form)),
            Button(id=BTN_NO, title_hi=get_message(BTN_NO, address_form)),
        ],
    )


def card_messages(
    struggle_id: str | None,
    *,
    address_form: str = "f",
    lib: StruggleLibrary | None = None,
) -> list[OutboundMessage]:
    """The card for her last struggle: [] when there is none or no stored chunk backs the tip."""
    lib = lib or load_library()
    focus = tomorrow_focus(
        struggle_id,
        opted_in=True,
        address_form=address_form,
        lib=lib,
        message_key="focus_card_body",
    )
    if focus is None:
        return []
    struggle = lib.get(focus.struggle_id)
    buttons: list[Button] = []
    if struggle is not None and struggle.move_id is not None and move_offered(struggle.move_id):
        buttons.append(Button(id=BTN_PRACTICE, title_hi=get_message(BTN_PRACTICE, address_form)))
    buttons.append(Button(id=BTN_ASK, title_hi=get_message(BTN_ASK, address_form)))
    buttons.append(Button(id=BTN_OFF, title_hi=get_message(BTN_OFF, address_form)))
    return [
        OutboundMessage(
            kind="buttons",
            text_hi=f"{get_message('focus_card_head', address_form)}\n{focus.text}",
            buttons=buttons,
            citations=list(focus.citations),
        )
    ]


@dataclass
class FocusResult:
    messages: list[OutboundMessage] = field(default_factory=list)
    opt_in: bool | None = None  # True / False: store it; None: leave it as it is
    practice: bool = False  # open the practice for her last struggle
    handbook: bool = False  # the handbook ask prompt
    handled: bool = True


def handle_button(button_id: str, address_form: str = "f") -> FocusResult:
    """One tap on a focus button. The caller stores `opt_in` and opens practice or the handbook."""
    if button_id == BTN_YES:
        return FocusResult(
            [OutboundMessage(kind="text", text_hi=get_message("focus_on_ack", address_form))],
            opt_in=True,
        )
    if button_id == BTN_NO:
        return FocusResult(
            [OutboundMessage(kind="text", text_hi=get_message("focus_snooze_ack", address_form))]
        )
    if button_id == BTN_OFF:
        return FocusResult(
            [OutboundMessage(kind="text", text_hi=get_message("focus_off_ack", address_form))],
            opt_in=False,
        )
    if button_id == BTN_PRACTICE:
        return FocusResult(practice=True)
    if button_id == BTN_ASK:
        return FocusResult(handbook=True)
    return FocusResult(handled=False)


def last_struggle(checkin_struggle_ids: list[list[str]], class_struggles: list[str]) -> str | None:
    """Her last struggle: the newest check-in that named one, else the first she chose in My class.

    `checkin_struggle_ids` is oldest first (as `recent_checkins` returns it).
    """
    for ids in reversed(checkin_struggle_ids):
        if ids:
            return ids[0]
    return class_struggles[0] if class_struggles else None


__all__ = [
    "ALL_BUTTONS",
    "BTN_ASK",
    "BTN_NO",
    "BTN_OFF",
    "BTN_PRACTICE",
    "BTN_YES",
    "CARD_MARKER",
    "OFFER_MARKER",
    "FocusResult",
    "card_due",
    "card_messages",
    "enabled",
    "handle_button",
    "last_struggle",
    "offer_due",
    "offer_message",
]
