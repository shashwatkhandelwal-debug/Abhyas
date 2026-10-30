"""My progress (flag MY_PROGRESS_ENABLED): her own last rehearsals and a plain trend, only for her.

Built from what is already stored for her scenes: the tagged acts of her turns and who each turn
was addressed to. No model, no child data, no free text is shown (her words are never quoted
here). Four yes or no facts per rehearsal: asked a child how or why, told the answer, used concrete
objects (sticks, bundles), named a child (group scenes only). The trend compares her earliest and
latest rehearsals of the SAME move; with fewer than two rehearsals it says so and offers practice.

The message goes into her own chat thread and nowhere else: no ARP, trainer or coach page and no CSV
imports this module (`test_my_progress_privacy.py` enforces it).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from zoneinfo import ZoneInfo

from backend.app.config import settings, v2_enabled
from backend.app.core.messages import get_message
from backend.app.core.types import Button, OutboundMessage
from backend.app.rehearsal.scene_store import TurnRecord
from backend.app.rule_engine.domain import TeachingAct
from backend.app.sessions.rehearsal_view import Rehearsal, TurnView
from backend.app.sessions.talk_moves import count_turns
from backend.app.sessions.titles import move_title

IST = ZoneInfo("Asia/Kolkata")
BTN_PRACTICE = "btn_mp_practice"
_CONCRETE = TeachingAct.CONCRETE_REPRESENTATION.value

ASKED, TOLD, CONCRETE, NAMED = "asked", "told", "concrete", "named"
FACTS = (ASKED, TOLD, CONCRETE, NAMED)
# Facts where "yes" is the good side (told is the reverse); the order is the priority of both lines
_GOOD_IF_YES = {ASKED: True, TOLD: False, CONCRETE: True, NAMED: True}
_STRENGTH_KEYS = {
    ASKED: "mp_s_asked",
    TOLD: "mp_s_notold",
    CONCRETE: "mp_s_concrete",
    NAMED: "mp_s_named",
}
_NEXT_KEYS = {TOLD: "mp_n_told", ASKED: "mp_n_asked", CONCRETE: "mp_n_concrete", NAMED: "mp_n_named"}
_NEXT_ORDER = (TOLD, ASKED, CONCRETE, NAMED)
_LABEL_KEYS = {
    ASKED: "mp_l_asked",
    TOLD: "mp_l_told",
    CONCRETE: "mp_l_concrete",
    NAMED: "mp_l_named",
}


def enabled() -> bool:
    return v2_enabled(settings.MY_PROGRESS_ENABLED)


def facts_of(r: Rehearsal) -> dict[str, bool | None]:
    """The four facts for one rehearsal; None when it does not apply or she did not speak."""
    records = [
        TurnRecord(
            turn_index=i, transcript=t.transcript, acts=list(t.acts), addressed_child=t.addressed_child
        )
        for i, t in enumerate(r.turns, 1)
    ]
    counts = count_turns(records, one_on_one=r.one_on_one)
    if counts.turns == 0:
        return dict.fromkeys(FACTS)
    concrete = any(
        _CONCRETE in rec.acts and "stop" not in rec.acts and (rec.transcript or "").strip()
        for rec in records
    )
    return {
        ASKED: counts.explain > 0,
        TOLD: counts.told > 0,
        CONCRETE: concrete,
        NAMED: None if r.one_on_one else counts.named > 0,
    }


def _is_good(fact: str, value: bool) -> bool:
    return value is _GOOD_IF_YES[fact]


def pick_pair(history: Sequence[Rehearsal]) -> tuple[Rehearsal, Rehearsal] | None:
    """Earliest and latest rehearsal of the move she practised most recently twice or more."""
    by_move: dict[str, list[Rehearsal]] = {}
    for r in sorted(history, key=lambda x: x.when):
        by_move.setdefault(r.move_id, []).append(r)
    pairs = [rows for rows in by_move.values() if len(rows) >= 2]
    if not pairs:
        return None
    rows = max(pairs, key=lambda rs: rs[-1].when)
    return rows[0], rows[-1]


def strength_and_next(
    before: dict[str, bool | None] | None, after: dict[str, bool | None]
) -> tuple[str | None, str]:
    """(strength key, next step key), deterministic: an improvement first, else any good fact."""
    strength: str | None = None
    if before is not None:
        for f in FACTS:
            b, a = before[f], after[f]
            if a is not None and b is not None and a != b and _is_good(f, a):
                strength = _STRENGTH_KEYS[f]
                break
    if strength is None:
        for f in FACTS:
            a = after[f]
            if a is not None and _is_good(f, a):
                strength = _STRENGTH_KEYS[f]
                break
    step = next(
        (_NEXT_KEYS[f] for f in _NEXT_ORDER if after[f] is not None and not _is_good(f, bool(after[f]))),
        "mp_n_keep",
    )
    return strength, step


def _yes_no(value: bool) -> str:
    return get_message("mp_yes" if value else "mp_no")


def _date(moment: datetime) -> str:
    return moment.astimezone(IST).strftime("%d/%m")


def progress_message(
    history: Sequence[Rehearsal], address_form: str, buttons: Sequence[Button]
) -> OutboundMessage:
    """One message: her last rehearsals, the trend (or why there is none), a strength and a step."""
    ordered = sorted(history, key=lambda r: r.when)
    shown = ordered[-settings.MY_PROGRESS_SHOWN :]
    lines: list[str] = []
    if shown:
        lines.append(get_message("mp_head", address_form, n=len(shown)))
        lines += [
            get_message("mp_row", address_form, i=i, move=move_title(r.move_id), date=_date(r.when))
            for i, r in enumerate(shown, 1)
        ]
    if len(ordered) < 2:
        lines.append(get_message("mp_too_few", address_form))
        return OutboundMessage(kind="buttons", text_hi="\n".join(lines), buttons=list(buttons))

    pair = pick_pair(ordered)
    latest = facts_of(ordered[-1])
    before: dict[str, bool | None] | None = None
    if pair is None:
        lines.append(get_message("mp_no_pair", address_form))
    else:
        first, last = pair
        before, latest = facts_of(first), facts_of(last)
        lines.append(get_message("mp_trend_head", address_form, move=move_title(last.move_id)))
        for f in FACTS:
            b, a = before[f], latest[f]
            if b is None or a is None:
                continue
            lines.append(
                get_message(
                    "mp_trend_line",
                    address_form,
                    label=get_message(_LABEL_KEYS[f], address_form),
                    before=_yes_no(b),
                    after=_yes_no(a),
                )
            )
    strength, step = strength_and_next(before, latest)
    lines.append(get_message(strength or "mp_s_none", address_form))
    lines.append(get_message(step, address_form))
    return OutboundMessage(kind="buttons", text_hi="\n".join(lines), buttons=list(buttons))


__all__ = [
    "BTN_PRACTICE",
    "Rehearsal",
    "TurnView",
    "enabled",
    "facts_of",
    "pick_pair",
    "progress_message",
    "strength_and_next",
]
