"""Cluster meeting pack: what teachers reported in class check-ins, and what to practise together.

Counts only, never a teacher: the closed-list struggle ids from `class_checkin` rows of the last
`CLUSTER_PACK_WINDOW_DAYS` days, from teachers who agreed to share scores, in the viewer's own scope
(an ARP's cluster, a trainer's district). Privacy follows the other aggregate cards:

* fewer than `AGGREGATION_SUPPRESSION_N` such teachers in scope: the whole pack is suppressed (not
  even a count is returned);
* a struggle is named only when at least that many teachers reported it, so no small cell is shown.

The practice move is the struggle's own `move_id` from `content/class_struggles.yaml`; a struggle
with no move says so (and keeps its handbook tip and citations) instead of inventing one. Teachers
flagged `is_demo` are labelled as demo data.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.class_profile.library import ClassStruggle, citations, load_library
from backend.app.config import settings
from backend.app.core.messages import get_ui_lang
from backend.app.db.models import ClassCheckin, Teacher
from backend.app.llm.roles.guide_answerer import format_guide_citation
from backend.app.sessions.titles import move_title

_STRUGGLED = ("some", "most")


@dataclass
class PackItem:
    struggle_id: str
    label: str
    teachers: int
    move_id: str | None
    move_title: str  # "" when the struggle has no practice move yet
    tip: str
    sources: list[str] = field(default_factory=list)  # citation lines of the tip's chunks


@dataclass
class ClusterPack:
    n_teachers: int  # consenting teachers in scope with a check-in in the window
    window_days: int
    suppressed: bool = False
    includes_demo: bool = False
    all_demo: bool = False
    items: list[PackItem] = field(default_factory=list)

    @property
    def practice_item(self) -> PackItem | None:
        """The first named struggle that has a practice move (the one to practise together)."""
        return next((i for i in self.items if i.move_id), None)


def _plain(text: str) -> str:
    """Stored text shown as is: no literal markdown asterisks reach the page."""
    return text.replace("*", "")


def _item(s: ClassStruggle, teachers: int, *, en: bool) -> PackItem:
    cites = citations(s.chunk_ids)
    return PackItem(
        struggle_id=s.id,
        label=_plain(s.label_en if en else s.label_hi),
        teachers=teachers,
        move_id=s.move_id,
        move_title=move_title(s.move_id) if s.move_id else "",
        tip=_plain(s.tip_en if en else s.tip_hi),
        sources=[format_guide_citation(c.source_short_hi, c.page) for c in cites],
    )


async def build_cluster_pack(
    session: AsyncSession,
    *,
    cluster_id: str | None = None,
    district: str | None = None,
    suppress_below: int | None = None,
    now: datetime | None = None,
) -> ClusterPack:
    suppress = settings.AGGREGATION_SUPPRESSION_N if suppress_below is None else suppress_below
    window = settings.CLUSTER_PACK_WINDOW_DAYS
    cutoff = (now or datetime.now(UTC)) - timedelta(days=window)
    stmt = (
        select(
            ClassCheckin.teacher_id,
            ClassCheckin.outcome,
            ClassCheckin.struggle_ids,
            Teacher.is_demo,
        )
        .join(Teacher, Teacher.id == ClassCheckin.teacher_id)
        .where(Teacher.consent_share_scores.is_(True), ClassCheckin.created_at >= cutoff)
    )
    if cluster_id is not None:
        stmt = stmt.where(Teacher.cluster_id == cluster_id)
    if district is not None:
        stmt = stmt.where(Teacher.district == district)
    rows = (await session.execute(stmt)).all()

    teachers: dict[object, bool] = {}
    reported: dict[str, set[object]] = defaultdict(set)
    for teacher_id, outcome, struggle_ids, is_demo in rows:
        teachers[teacher_id] = bool(is_demo)
        if outcome in _STRUGGLED:
            for sid in struggle_ids or []:
                reported[str(sid)].add(teacher_id)

    n = len(teachers)
    if n == 0:
        return ClusterPack(n_teachers=0, window_days=window)
    pack = ClusterPack(
        n_teachers=n,
        window_days=window,
        includes_demo=any(teachers.values()),
        all_demo=all(teachers.values()),
    )
    if n < suppress:
        pack.suppressed = True
        return pack

    lib = load_library()
    order = {sid: i for i, sid in enumerate(lib.ids())}
    en = get_ui_lang() == "en"
    qualifying = [
        (sid, len(who))
        for sid, who in reported.items()
        if lib.get(sid) is not None and len(who) >= suppress
    ]
    qualifying.sort(key=lambda x: (-x[1], order[x[0]]))
    for sid, count in qualifying[: settings.CLUSTER_PACK_TOP]:
        struggle = lib.get(sid)
        if struggle is not None:
            pack.items.append(_item(struggle, count, en=en))
    return pack


__all__ = ["ClusterPack", "PackItem", "build_cluster_pack"]
