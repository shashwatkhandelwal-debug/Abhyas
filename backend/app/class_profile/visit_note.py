"""What an ARP saw in her class, shown back to her (flag OBSERVATION_TO_TEACHER_ENABLED).

When an ARP saves a class-visit observation, the teacher sees it the next time she opens the chat,
framed as a note and never as a rating:

    "आपके ARP ने देखा: <what worked>. एक बात आज़माएँ: <next step>."   [ठीक है]

Both parts come from the closed lists the ARP form already uses (talk moves seen, the practice
seen, one next step), in the same words the ARP's own form carries. No score, no level and no free
text is involved, and nothing here writes anything: the note reads the observation and never feeds
a score, an evidence level or any report. When it was shown is read from her own thread (the message
carrying the [ठीक है] button), so no new column exists.
"""

from __future__ import annotations

from collections.abc import Sequence

from backend.app.class_profile.checkin_flow import struggle_label
from backend.app.class_profile.library import load_library
from backend.app.config import settings, v2_enabled
from backend.app.core.messages import get_message
from backend.app.core.types import Button, OutboundMessage

BTN_OK = "btn_obs_ok"


def enabled() -> bool:
    return v2_enabled(settings.OBSERVATION_TO_TEACHER_ENABLED)


def worked_text(talk_moves: Sequence[str], struggle_id: str | None, practice_seen: bool) -> str:
    """What the ARP saw, as a short list in the ARP form's own wording ("" is never returned)."""
    parts = [
        get_message(f"ui_visit_talk_{m}")
        for m in talk_moves
        if m in settings.OBSERVATION_TALK_MOVES
    ]
    if practice_seen and struggle_id:
        struggle = load_library().get(struggle_id)
        if struggle is not None:
            parts.append(get_message("ui_visit_practice_seen", label=struggle_label(struggle)))
    return "; ".join(parts) if parts else get_message("obs_worked_none")


def note_message(
    talk_moves: Sequence[str],
    struggle_id: str | None,
    practice_seen: bool,
    next_step: str,
    address_form: str = "f",
) -> OutboundMessage:
    """The note with its one [ठीक है] button. An unknown next step is left out, never invented."""
    worked = worked_text(talk_moves, struggle_id, practice_seen)
    try_text = (
        get_message(f"ui_visit_next_{next_step}")
        if next_step in settings.OBSERVATION_NEXT_STEPS
        else ""
    )
    key = "obs_note" if try_text else "obs_note_no_step"
    return OutboundMessage(
        kind="buttons",
        text_hi=get_message(key, address_form, worked=worked, step=try_text),
        buttons=[Button(id=BTN_OK, title_hi=get_message(BTN_OK, address_form))],
    )


def ack_message(address_form: str = "f") -> OutboundMessage:
    return OutboundMessage(kind="text", text_hi=get_message("obs_ok_ack", address_form))


__all__ = ["BTN_OK", "ack_message", "enabled", "note_message", "worked_text"]
