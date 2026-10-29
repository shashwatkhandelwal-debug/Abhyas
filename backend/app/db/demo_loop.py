"""The connected demo history around one struggle: regrouping in subtraction (NUM_SUB_REGROUP).

All of it is labelled demo data and exists only when `settings.DEMO_MODE` is on:

* demo2: a check-in for the struggle one day ago and a follow-up due TODAY (dates are computed from
  "now", so it is due on every login). The chat offers it when she opens it.
* demo3: an older check-in on the same struggle, answered "still stuck", so the adaptive path
  picks a different next practice than it does for a teacher with no history.
* the synthetic cohort (consenting teachers only): a follow-up and an answer for each seeded check-in
  with a struggle, and a class-visit note for the first `DEMO_VISIT_TEACHERS` teachers reporting
  regrouping, so the cluster pack and "reported vs observed" have content at n of 10 or more.

Seeding runs from `seed_database` (the seed command, `SEED_ON_BOOT=true` on a deploy) and, for the two
shared logins, from `reset_demo_teacher` on every demo login and logout. Nothing here is called by
a normal teacher flow. Rows use deterministic ids so a re-seed deletes and re-creates them; the
cohort's follow-ups and answers go with their check-ins (cascade), the visit notes are deleted here.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.class_profile.followup import next_school_day
from backend.app.config import settings
from backend.app.db.models import (
    ClassCheckin,
    ClassFollowup,
    ClassFollowupOutcome,
    ClassVisitObservation,
    Teacher,
)

IST = ZoneInfo("Asia/Kolkata")
STRUGGLE = "NUM_SUB_REGROUP"
MODULE = "NUM_SUB_REGROUP_BUNDLES"
DEMO_VISIT_TEACHERS = 12  # distinct teachers with a visit note on regrouping (at or above 10)
_OUTCOME_CYCLE = ("worked", "stuck", "stuck", "cant", "worked", "stuck")
_REASON_CYCLE = ("time", "multigrade", "absent", "other")
_TALK_CYCLE = (
    ["named_child", "why_how"],
    ["why_how", "think_time"],
    ["not_told"],
    ["named_child", "think_time", "why_how"],
)
_NEXT_CYCLE = ("ask_named", "ask_why", "hold_answer", "wait_time", "repeat")


def _id(kind: int, n: int) -> uuid.UUID:
    return uuid.UUID(f"00000000-0000-0001-{kind:04x}-{n:012x}")


CHECKIN_KIND, FOLLOWUP_KIND, OUTCOME_KIND, VISIT_KIND = 0x0008, 0x0009, 0x000A, 0x000B
DEMO2_N, DEMO3_N = 0xD02001, 0xD03001


def _ist_day(moment: datetime) -> date:
    return moment.astimezone(IST).date()


async def seed_login_loop(session: AsyncSession, teacher_id: uuid.UUID, now: datetime) -> None:
    """demo2 and demo3 only; every other teacher id is ignored. No-op outside demo mode."""
    from backend.app.db.seed import TEACHER_DEMO2_ID, TEACHER_DEMO3_ID

    if not settings.DEMO_MODE or teacher_id not in (TEACHER_DEMO2_ID, TEACHER_DEMO3_ID):
        return
    is_two = teacher_id == TEACHER_DEMO2_ID
    n = DEMO2_N if is_two else DEMO3_N
    checkin_at = now - timedelta(days=1 if is_two else 4)
    await session.execute(delete(ClassCheckin).where(ClassCheckin.id == _id(CHECKIN_KIND, n)))
    session.add(
        ClassCheckin(
            id=_id(CHECKIN_KIND, n),
            teacher_id=teacher_id,
            module_id=MODULE,
            outcome="most",
            struggle_ids=[STRUGGLE],
            created_at=checkin_at,
        )
    )
    await session.flush()
    due = _ist_day(now) if is_two else next_school_day(_ist_day(checkin_at))
    session.add(
        ClassFollowup(
            id=_id(FOLLOWUP_KIND, n),
            teacher_id=teacher_id,
            checkin_id=_id(CHECKIN_KIND, n),
            struggle_id=STRUGGLE,
            due_date=due,
            offered_at=None if is_two else now - timedelta(days=3),
            is_demo=True,
            created_at=checkin_at,
        )
    )
    await session.flush()
    if not is_two:  # demo3 already answered: still stuck
        session.add(
            ClassFollowupOutcome(
                id=_id(OUTCOME_KIND, n),
                teacher_id=teacher_id,
                followup_id=_id(FOLLOWUP_KIND, n),
                outcome="stuck",
                created_at=now - timedelta(days=2),
            )
        )
    await session.flush()


async def seed_cohort_loop(session: AsyncSession, teachers: list[Teacher], now: datetime) -> None:
    """Follow-up answers and visit notes for the seeded cohort's check-ins (demo mode only)."""
    cohort = [t.id for t in teachers[3:]]
    await session.execute(
        delete(ClassVisitObservation).where(ClassVisitObservation.teacher_id.in_(cohort))
    )
    if not settings.DEMO_MODE or not cohort:
        return
    rows = (
        (
            await session.execute(
                select(ClassCheckin)
                .where(
                    ClassCheckin.teacher_id.in_(cohort), ClassCheckin.outcome.in_(("some", "most"))
                )
                .order_by(ClassCheckin.id)
            )
        )
        .scalars()
        .all()
    )
    visited: list[uuid.UUID] = []
    for i, checkin in enumerate(rows):
        if not checkin.struggle_ids:
            continue
        n = int(str(checkin.id)[-12:], 16)
        due = next_school_day(_ist_day(checkin.created_at))
        session.add(
            ClassFollowup(
                id=_id(FOLLOWUP_KIND, n),
                teacher_id=checkin.teacher_id,
                checkin_id=checkin.id,
                struggle_id=str(checkin.struggle_ids[0]),
                due_date=due,
                offered_at=checkin.created_at + timedelta(days=1),
                is_demo=True,
                created_at=checkin.created_at,
            )
        )
        await session.flush()
        outcome = _OUTCOME_CYCLE[i % len(_OUTCOME_CYCLE)]
        session.add(
            ClassFollowupOutcome(
                id=_id(OUTCOME_KIND, n),
                teacher_id=checkin.teacher_id,
                followup_id=_id(FOLLOWUP_KIND, n),
                outcome=outcome,
                reason=_REASON_CYCLE[i % len(_REASON_CYCLE)] if outcome == "cant" else None,
                created_at=checkin.created_at + timedelta(days=1, hours=2),
            )
        )
        if (
            checkin.struggle_ids[0] == STRUGGLE
            and checkin.teacher_id not in visited
            and len(visited) < DEMO_VISIT_TEACHERS
        ):
            visited.append(checkin.teacher_id)
            k = len(visited)
            session.add(
                ClassVisitObservation(
                    id=_id(VISIT_KIND, k),
                    teacher_id=checkin.teacher_id,
                    arp_user_id=None,
                    talk_moves=list(_TALK_CYCLE[k % len(_TALK_CYCLE)]),
                    practice_seen=True,
                    struggle_id=STRUGGLE,
                    next_step=_NEXT_CYCLE[k % len(_NEXT_CYCLE)],
                    observed_on=_ist_day(checkin.created_at) + timedelta(days=2),
                    is_demo=True,
                    created_at=checkin.created_at + timedelta(days=2),
                )
            )
    await session.flush()


__all__ = ["DEMO_VISIT_TEACHERS", "seed_cohort_loop", "seed_login_loop"]
