"""Trainer aggregate of "My class" choices: counts per struggle, never a teacher.

Same rules as the other trainer cards: own district, teachers who agreed to share scores only, and
nothing at all (not even per-struggle counts) below `AGGREGATION_SUPPRESSION_N` teachers.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.class_profile.library import load_library
from backend.app.core.messages import get_ui_lang
from backend.app.db.models import Teacher


@dataclass
class StruggleCount:
    struggle_id: str
    label: str
    teachers: int


@dataclass
class ClassStruggleSummary:
    n_teachers: int  # consenting teachers in scope who chose at least one struggle
    suppressed: bool = False
    rows: list[StruggleCount] = field(default_factory=list)


async def class_struggle_summary(
    session: AsyncSession,
    *,
    district: str | None = None,
    suppress_below: int,
) -> ClassStruggleSummary:
    stmt = select(Teacher.class_struggles).where(Teacher.consent_share_scores.is_(True))
    if district is not None:
        stmt = stmt.where(Teacher.district == district)
    chosen = [list(r) for r in (await session.execute(stmt)).scalars().all() if r]
    n = len(chosen)
    if n == 0:
        return ClassStruggleSummary(n_teachers=0)
    if n < suppress_below:
        return ClassStruggleSummary(n_teachers=n, suppressed=True)
    lib = load_library()
    en = get_ui_lang() == "en"
    counts: Counter[str] = Counter()
    for ids in chosen:
        counts.update({i for i in ids if lib.get(i) is not None})
    rows = []
    for sid, count in counts.most_common():
        s = lib.get(sid)
        if s is not None:
            rows.append(StruggleCount(sid, s.label_en if en else s.label_hi, count))
    return ClassStruggleSummary(n_teachers=n, rows=rows)
