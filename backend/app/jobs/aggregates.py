# TODO(T24): replace
"""Batch and module metrics aggregation job (spec/09 §9.4, spec/14 T24).

# NOTE (Lane C / T31): Minimal compute_aggregates_for_batch implemented for T24 / T31
# to aggregate real teacher rehearsal scores and adoption evidence into AggModuleBatch
# with strict suppression when sample size n < 10.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.config import settings
from backend.app.db.models import (
    AdoptionEvidence,
    AggModuleBatch,
    ExplainScore,
    RehearsalScore,
    Teacher,
)


async def compute_aggregates_for_batch(
    session: AsyncSession,
    batch_id: str,
    move_id: str,
) -> AggModuleBatch:
    """Computes AggModuleBatch record for a (batch_id, move_id) pair from real database rows."""
    stmt_teachers = select(Teacher).where(Teacher.batch_id == batch_id)
    teachers = (await session.execute(stmt_teachers)).scalars().all()
    n_teachers = len(teachers)
    now = datetime.now(UTC)

    if n_teachers < settings.AGGREGATION_SUPPRESSION_N:
        # Suppress aggregates when sample size n < 10 (spec/03 §3.5, spec/09 §9.4)
        return AggModuleBatch(
            batch_id=batch_id,
            move_id=move_id,
            n_teachers=n_teachers,
            explain_missing=None,
            rubric_dist=None,
            ladder_dist=None,
            active_rate=None,
            computed_at=now,
        )

    teacher_ids = [t.id for t in teachers]
    teacher_id_set = set(teacher_ids)

    # 1. Adoption ladder distribution (levels 1..5)
    ladder_dist: dict[str, int] = {str(lvl): 0 for lvl in range(1, 6)}
    stmt_ev = select(AdoptionEvidence).where(
        AdoptionEvidence.teacher_id.in_(teacher_ids),
        AdoptionEvidence.move_id == move_id,
    )
    raw_ev = (await session.execute(stmt_ev)).scalars().all()
    evidences = [ev for ev in raw_ev if ev.teacher_id in teacher_id_set]
    max_levels_by_teacher: dict[Any, int] = {}
    for ev in evidences:
        cur = max_levels_by_teacher.get(ev.teacher_id, 0)
        if ev.level > cur:
            max_levels_by_teacher[ev.teacher_id] = ev.level
    for lvl in max_levels_by_teacher.values():
        if 1 <= lvl <= 5:
            ladder_dist[str(lvl)] += 1

    # 2. Explain-back missing key points
    explain_missing: dict[str, int] = {}
    stmt_es = select(ExplainScore).where(
        ExplainScore.teacher_id.in_(teacher_ids),
        ExplainScore.move_id == move_id,
    )
    raw_es = (await session.execute(stmt_es)).scalars().all()
    escores = [es for es in raw_es if es.teacher_id in teacher_id_set]
    for es in escores:
        if es.points:
            for kpid, status in es.points.items():
                if status in ("missing", "partial"):
                    explain_missing[kpid] = explain_missing.get(kpid, 0) + 1

    # 3. Rubric score distribution
    rubric_dist: dict[str, dict[str, int]] = {}
    stmt_rs = select(RehearsalScore).where(
        RehearsalScore.teacher_id.in_(teacher_ids),
        RehearsalScore.move_id == move_id,
    )
    raw_rs = (await session.execute(stmt_rs)).scalars().all()
    rscores = [rs for rs in raw_rs if rs.teacher_id in teacher_id_set]
    for rs in rscores:
        if rs.scores:
            for crit_id, val in rs.scores.items():
                if crit_id not in rubric_dist:
                    rubric_dist[crit_id] = {"0": 0, "1": 0, "2": 0}
                val_str = str(val)
                if val_str in rubric_dist[crit_id]:
                    rubric_dist[crit_id][val_str] += 1

    # 4. Activity rate: proportion of batch teachers with at least one evidence or score
    active_teachers_count = len(
        {ev.teacher_id for ev in evidences} | {rs.teacher_id for rs in rscores}
    )
    active_rate = round(min(1.0, active_teachers_count / max(n_teachers, 1)), 2)

    return AggModuleBatch(
        batch_id=batch_id,
        move_id=move_id,
        n_teachers=n_teachers,
        explain_missing=explain_missing,
        rubric_dist=rubric_dist,
        ladder_dist=ladder_dist,
        active_rate=active_rate,
        computed_at=now,
    )
