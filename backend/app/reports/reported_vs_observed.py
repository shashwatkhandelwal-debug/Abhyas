"""Trainer view: "Reported vs observed", per struggle.

Reported: what consenting teachers said about a follow-up (worked / still stuck / could not try).
Observed: ARP visit notes where the practice for that struggle was seen. Counts only, never a
teacher, and the caption says these are self-reported and observed counts, not learning outcomes.

Privacy follows the other aggregate cards (`AGGREGATION_SUPPRESSION_N`, default 10):
* fewer than N consenting teachers in scope with a follow-up answer or an observation in the window:
  the whole card is suppressed, no counts at all;
* a struggle is listed only when at least N teachers answered a follow-up about it;
* the observed count of a row is shown only when at least N different teachers were observed on it,
  otherwise it is withheld (`observed is None`).
Teachers flagged `is_demo` are labelled as demo data.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.class_profile.library import load_library
from backend.app.config import settings
from backend.app.core.messages import get_ui_lang
from backend.app.db.models import (
    ClassFollowup,
    ClassFollowupOutcome,
    ClassVisitObservation,
    Teacher,
)


@dataclass
class RvoRow:
    struggle_id: str
    label: str
    teachers: int  # teachers who answered a follow-up about it
    worked: int
    stuck: int
    cant: int
    observed: int | None  # visits where the practice was seen; None = withheld (fewer than N)


@dataclass
class ReportedVsObserved:
    n_teachers: int
    window_days: int
    suppressed: bool = False
    includes_demo: bool = False
    all_demo: bool = False
    rows: list[RvoRow] = field(default_factory=list)


async def build_reported_vs_observed(
    session: AsyncSession,
    *,
    cluster_id: str | None = None,
    district: str | None = None,
    suppress_below: int | None = None,
    now: datetime | None = None,
) -> ReportedVsObserved:
    suppress = settings.AGGREGATION_SUPPRESSION_N if suppress_below is None else suppress_below
    window = settings.OBSERVATION_WINDOW_DAYS
    cutoff = (now or datetime.now(UTC)) - timedelta(days=window)

    def scoped(stmt: Any) -> Any:  # a select of any shape, narrowed to consenting teachers in scope
        stmt = stmt.where(Teacher.consent_share_scores.is_(True))
        if cluster_id is not None:
            stmt = stmt.where(Teacher.cluster_id == cluster_id)
        if district is not None:
            stmt = stmt.where(Teacher.district == district)
        return stmt

    followups = (
        await session.execute(
            scoped(
                select(
                    ClassFollowupOutcome.teacher_id,
                    ClassFollowup.struggle_id,
                    ClassFollowupOutcome.outcome,
                    Teacher.is_demo,
                )
                .join(ClassFollowup, ClassFollowup.id == ClassFollowupOutcome.followup_id)
                .join(Teacher, Teacher.id == ClassFollowupOutcome.teacher_id)
                .where(ClassFollowupOutcome.created_at >= cutoff)
            )
        )
    ).all()
    visits = (
        await session.execute(
            scoped(
                select(
                    ClassVisitObservation.teacher_id,
                    ClassVisitObservation.struggle_id,
                    ClassVisitObservation.practice_seen,
                    Teacher.is_demo,
                )
                .join(Teacher, Teacher.id == ClassVisitObservation.teacher_id)
                .where(ClassVisitObservation.created_at >= cutoff)
            )
        )
    ).all()

    teachers: dict[object, bool] = {}
    for teacher_id, _sid, _out, is_demo in followups:
        teachers[teacher_id] = bool(is_demo)
    for teacher_id, _sid, _seen, is_demo in visits:
        teachers[teacher_id] = bool(is_demo)
    n = len(teachers)
    result = ReportedVsObserved(n_teachers=n, window_days=window)
    if n == 0:
        return result
    result.includes_demo = any(teachers.values())
    result.all_demo = all(teachers.values())
    if n < suppress:
        result.suppressed = True
        return result

    who: dict[str, set[object]] = defaultdict(set)
    counts: dict[str, dict[str, int]] = defaultdict(lambda: {"worked": 0, "stuck": 0, "cant": 0})
    for teacher_id, sid, outcome, _demo in followups:
        who[str(sid)].add(teacher_id)
        if outcome in counts[str(sid)]:
            counts[str(sid)][outcome] += 1
    seen_by: dict[str, list[object]] = defaultdict(list)
    for teacher_id, sid, seen, _demo in visits:
        if seen and sid:
            seen_by[str(sid)].append(teacher_id)

    lib = load_library()
    order = {sid: i for i, sid in enumerate(lib.ids())}
    en = get_ui_lang() == "en"
    qualifying = [sid for sid, t in who.items() if len(t) >= suppress and lib.get(sid) is not None]
    qualifying.sort(key=lambda sid: (-sum(counts[sid].values()), order[sid]))
    for sid in qualifying[: settings.OBSERVATION_ROWS_MAX]:
        struggle = lib.get(sid)
        if struggle is None:
            continue
        observed_teachers = set(seen_by.get(sid, []))
        result.rows.append(
            RvoRow(
                struggle_id=sid,
                label=(struggle.label_en if en else struggle.label_hi).replace("*", ""),
                teachers=len(who[sid]),
                worked=counts[sid]["worked"],
                stuck=counts[sid]["stuck"],
                cant=counts[sid]["cant"],
                observed=len(seen_by.get(sid, [])) if len(observed_teachers) >= suppress else None,
            )
        )
    return result


__all__ = ["ReportedVsObserved", "RvoRow", "build_reported_vs_observed"]
