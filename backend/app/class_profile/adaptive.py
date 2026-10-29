"""Adaptive next practice (flag ADAPTIVE_PATH_ENABLED): which of HER moves comes next, and why.

A deterministic chooser, no LLM. It only picks among moves already in her path (nothing is removed
or added) and the stored path itself is never rewritten. Signals, all from the closed lists:

* check-ins: "most struggled" weighs most, "some" less (`ADAPTIVE_MOST_WEIGHT`, `ADAPTIVE_SOME_WEIGHT`),
  attributed to the move of the struggle (`move_id` in `content/class_struggles.yaml`);
* follow-up answers: "still stuck" raises that move, "worked" lowers it;
* experience band from onboarding: a new teacher (`ADAPTIVE_NEW_TEACHER_BANDS`) gets the first
  foundation move of her path a bonus equal to a "most struggled" check-in, so the basics (where the
  model teacher shows the method first) come before a single class signal.

With no history in the window the chooser returns None and the old order stands. Everything older
than `ADAPTIVE_HISTORY_DAYS` is ignored. Existing "My class" ordering is
`personalise.order_path` (called from `SessionService._after_class_saved`); this does not replace it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from backend.app.class_profile.checkin_flow import struggle_label
from backend.app.class_profile.library import StruggleLibrary, load_library
from backend.app.config import settings, v2_enabled
from backend.app.core.messages import get_message

SIGNAL_MOST = "most"
SIGNAL_SOME = "some"
SIGNAL_STUCK = "stuck"
SIGNAL_WORKED = "worked"
SIGNAL_NEW = "new"


def enabled() -> bool:
    return v2_enabled(settings.ADAPTIVE_PATH_ENABLED)


@dataclass(frozen=True)
class CheckinSignal:
    outcome: str  # well / some / most
    struggle_ids: Sequence[str]
    when: datetime


@dataclass(frozen=True)
class FollowupSignal:
    struggle_id: str
    outcome: str  # worked / stuck / cant
    when: datetime


@dataclass(frozen=True)
class Choice:
    move_id: str
    signal: str
    struggle_id: str | None  # the struggle behind the reason (None for "new")


def reason_text(choice: Choice, lib: StruggleLibrary | None = None) -> str:
    """The one-line "Why this next" from the catalog, built from the signal used."""
    if choice.signal == SIGNAL_NEW or choice.struggle_id is None:
        return get_message("adp_why_new")
    struggle = (lib or load_library()).get(choice.struggle_id)
    label = struggle_label(struggle) if struggle is not None else ""
    return get_message(f"adp_why_{choice.signal}", label=label)


def choose_next(
    candidates: Sequence[str],
    *,
    checkins: Sequence[CheckinSignal],
    followups: Sequence[FollowupSignal],
    experience_band: str | None,
    now: datetime,
    lib: StruggleLibrary | None = None,
) -> Choice | None:
    """The next move among `candidates` (her path order, finished moves already left out)."""
    if not candidates:
        return None
    lib = lib or load_library()
    since = now - timedelta(days=settings.ADAPTIVE_HISTORY_DAYS)
    # (weight, signal, struggle id) per move; positive raises it, negative lowers it
    marks: dict[str, list[tuple[int, str, str | None]]] = {m: [] for m in candidates}

    def add(struggle_id: str, weight: int, signal: str) -> None:
        struggle = lib.get(struggle_id)
        if struggle is not None and struggle.move_id in marks:
            marks[struggle.move_id].append((weight, signal, struggle_id))

    for c in checkins:
        if c.when < since or c.outcome not in (SIGNAL_MOST, SIGNAL_SOME):
            continue
        weight = (
            settings.ADAPTIVE_MOST_WEIGHT
            if c.outcome == SIGNAL_MOST
            else (settings.ADAPTIVE_SOME_WEIGHT)
        )
        for sid in c.struggle_ids:
            add(sid, weight, c.outcome)
    for f in followups:
        if f.when < since:
            continue
        if f.outcome == SIGNAL_STUCK:
            add(f.struggle_id, settings.ADAPTIVE_STUCK_WEIGHT, SIGNAL_STUCK)
        elif f.outcome == SIGNAL_WORKED:
            add(f.struggle_id, -settings.ADAPTIVE_WORKED_WEIGHT, SIGNAL_WORKED)

    if not any(marks.values()):
        return None  # no history: the old order stands
    if experience_band in settings.ADAPTIVE_NEW_TEACHER_BANDS:
        marks[candidates[0]].append((settings.ADAPTIVE_MOST_WEIGHT, SIGNAL_NEW, None))

    scores = {m: sum(w for w, _, _ in rows) for m, rows in marks.items()}
    best = max(scores.values())
    chosen = next(m for m in candidates if scores[m] == best)  # a tie keeps her path order
    positives = [row for row in marks[chosen] if row[0] > 0]
    if positives:
        _, signal, why_sid = max(positives, key=lambda r: r[0])
        return Choice(chosen, signal, why_sid)
    # nothing raised it: the move that came first was lowered by "worked"; say so
    lowered = [row for row in marks[candidates[0]] if row[0] < 0]
    if chosen != candidates[0] and lowered:
        return Choice(chosen, SIGNAL_WORKED, lowered[0][2])
    return None


__all__ = [
    "Choice",
    "CheckinSignal",
    "FollowupSignal",
    "SIGNAL_MOST",
    "SIGNAL_NEW",
    "SIGNAL_SOME",
    "SIGNAL_STUCK",
    "SIGNAL_WORKED",
    "choose_next",
    "enabled",
    "reason_text",
]
