"""Module progress for the trainer and ARP dashboards, with pilot / demo labels.

Teachers flagged `is_demo` (the shared demo logins and the synthetic cohort) are counted under
the "demo" label; every other teacher is a "pilot" teacher. Only teachers who agreed to share
scores are counted, no names are returned, and the trainer view hides groups below the
aggregation threshold (the same n < 10 rule as the other trainer tables).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models import ModuleProgress, Teacher
from backend.app.sessions.modules import MODULE_STEPS, module_card, module_ids, step_flags

LABEL_PILOT = "pilot"
LABEL_DEMO = "demo"


@dataclass
class ModuleGroupRow:
    module_id: str
    title_hi: str
    label: str  # pilot | demo
    teachers: int = 0
    steps: dict[str, int] = field(default_factory=lambda: dict.fromkeys(MODULE_STEPS, 0))
    passed: int = 0
    suppressed: bool = False


async def module_progress_summary(
    session: AsyncSession,
    *,
    district: str | None = None,
    cluster_id: str | None = None,
    suppress_below: int | None = None,
) -> list[ModuleGroupRow]:
    """One row per (module, label) that has at least one consenting teacher with progress."""
    stmt = (
        select(ModuleProgress, Teacher.is_demo)
        .join(Teacher, Teacher.id == ModuleProgress.teacher_id)
        .where(Teacher.consent_share_scores.is_(True))
    )
    if district is not None:
        stmt = stmt.where(Teacher.district == district)
    if cluster_id is not None:
        stmt = stmt.where(Teacher.cluster_id == cluster_id)
    rows = (await session.execute(stmt)).all()

    groups: dict[tuple[str, str], ModuleGroupRow] = {}
    for progress, is_demo in rows:
        if progress.module_id not in module_ids():
            continue
        label = LABEL_DEMO if is_demo else LABEL_PILOT
        key = (progress.module_id, label)
        group = groups.get(key)
        if group is None:
            group = ModuleGroupRow(
                module_id=progress.module_id,
                title_hi=module_card(progress.module_id).title_hi,
                label=label,
            )
            groups[key] = group
        group.teachers += 1
        for step, done in step_flags(progress).items():
            group.steps[step] += int(done)
        group.passed += int(bool(progress.check_passed))

    order = {mid: i for i, mid in enumerate(module_ids())}
    result = sorted(groups.values(), key=lambda g: (order[g.module_id], g.label != LABEL_PILOT))
    if suppress_below is not None:
        for group in result:
            if group.teachers < suppress_below:
                group.suppressed = True
                group.steps = dict.fromkeys(MODULE_STEPS, 0)
                group.passed = 0
    return result
