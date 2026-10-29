"""The ARP class-visit checklist (flag OBSERVATION_ENABLED, ON in demo mode).

A short, closed-list form: which talk moves were seen, whether the practice from the teacher's last
check-in was seen, and one next step from a fixed list. No free text, no child data, and no teacher
identifier beyond the name the ARP page already shows. The struggle the practice belongs to is read
on the server from the teacher's own last check-in; the form can only say "seen" or not.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.class_profile.checkin_flow import struggle_label
from backend.app.class_profile.library import load_library
from backend.app.config import settings, v2_enabled
from backend.app.core.messages import get_message
from backend.app.db.models import ClassCheckin

TALK_FIELD = "talk"
NEXT_FIELD = "next_step"
SEEN_FIELD = "practice_seen"


def enabled() -> bool:
    return v2_enabled(settings.OBSERVATION_ENABLED)


class VisitFormError(ValueError):
    """The form carried something outside the closed lists."""


@dataclass(frozen=True)
class ParsedVisit:
    talk_moves: tuple[str, ...]
    practice_seen: bool
    next_step: str


def parse_form(talk: list[str], next_step: str | None, practice_seen: str | None) -> ParsedVisit:
    """Validates the three closed fields. Anything outside the lists is rejected, never stored."""
    moves = tuple(dict.fromkeys(talk))  # ticked twice counts once, order kept
    if any(m not in settings.OBSERVATION_TALK_MOVES for m in moves):
        raise VisitFormError("talk move")
    if next_step not in settings.OBSERVATION_NEXT_STEPS:
        raise VisitFormError("next step")
    return ParsedVisit(moves, practice_seen == "1", str(next_step))


async def last_struggles(db: AsyncSession, teacher_ids: list[UUID]) -> dict[UUID, str]:
    """Each teacher's most recent check-in struggle (the practice an ARP could look for)."""
    if not teacher_ids:
        return {}
    since = datetime.now(UTC) - timedelta(days=settings.OBSERVATION_WINDOW_DAYS)
    rows = (
        await db.execute(
            select(ClassCheckin.teacher_id, ClassCheckin.struggle_ids)
            .where(
                ClassCheckin.teacher_id.in_(teacher_ids),
                ClassCheckin.outcome.in_(("some", "most")),
                ClassCheckin.created_at >= since,
            )
            .order_by(ClassCheckin.created_at)
        )
    ).all()
    out: dict[UUID, str] = {}
    for teacher_id, struggle_ids in rows:  # later rows overwrite earlier ones
        if struggle_ids:
            out[teacher_id] = str(struggle_ids[0])
    return out


def form_rows(teachers: list[Any], struggles: dict[UUID, str]) -> list[dict[str, Any]]:
    """What the template needs per consenting teacher already listed on the page."""
    lib = load_library()
    rows: list[dict[str, Any]] = []
    for t in teachers:
        sid = struggles.get(UUID(str(t.teacher_id)))
        struggle = lib.get(sid) if sid else None
        rows.append(
            {
                "teacher_id": str(t.teacher_id),
                "name": t.name,
                "school": t.school,
                "struggle_label": struggle_label(struggle) if struggle is not None else "",
            }
        )
    return rows


def labels() -> dict[str, Any]:
    return {
        "talk": [(m, get_message(f"ui_visit_talk_{m}")) for m in settings.OBSERVATION_TALK_MOVES],
        "next": [(n, get_message(f"ui_visit_next_{n}")) for n in settings.OBSERVATION_NEXT_STEPS],
    }


__all__ = [
    "NEXT_FIELD",
    "ParsedVisit",
    "SEEN_FIELD",
    "TALK_FIELD",
    "VisitFormError",
    "enabled",
    "form_rows",
    "labels",
    "last_struggles",
    "parse_form",
]
