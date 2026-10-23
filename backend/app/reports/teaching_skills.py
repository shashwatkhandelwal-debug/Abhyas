"""Trainer aggregate of "What do you want to get better at?": counts per skill, never a teacher.

Same rules as the class-struggle card: own district, teachers who agreed to share scores only, and
nothing at all (not even per-skill counts) below `AGGREGATION_SUPPRESSION_N` teachers.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.class_profile.skills import load_skills
from backend.app.db.models import Teacher


@dataclass
class SkillCount:
    skill_id: str
    label: str
    teachers: int


@dataclass
class TeachingSkillSummary:
    n_teachers: int  # consenting teachers in scope who chose at least one skill
    suppressed: bool = False
    rows: list[SkillCount] = field(default_factory=list)


async def teaching_skill_summary(
    session: AsyncSession,
    *,
    district: str | None = None,
    suppress_below: int,
) -> TeachingSkillSummary:
    stmt = select(Teacher.teaching_skills).where(Teacher.consent_share_scores.is_(True))
    if district is not None:
        stmt = stmt.where(Teacher.district == district)
    chosen = [list(r) for r in (await session.execute(stmt)).scalars().all() if r]
    n = len(chosen)
    if n == 0:
        return TeachingSkillSummary(n_teachers=0)
    if n < suppress_below:
        return TeachingSkillSummary(n_teachers=n, suppressed=True)
    lib = load_skills()
    counts: Counter[str] = Counter()
    for ids in chosen:
        counts.update({i for i in ids if lib.get(i) is not None})
    rows = []
    for sid, count in counts.most_common():
        skill = lib.get(sid)
        if skill is not None:
            rows.append(SkillCount(sid, skill.label, count))
    return TeachingSkillSummary(n_teachers=n, rows=rows)
