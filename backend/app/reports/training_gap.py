"""Trainer view: "Where training is not landing", per move (flag TRAINING_GAP_ENABLED).

For each move, among consenting teachers who rehearsed it in the last TRAINING_GAP_WINDOW_DAYS days,
how many have a LATEST rehearsal of that move that still shows each target habit. The habits come
from what the tagger already stored for each teacher turn (the teaching acts and the child the turn
was addressed to), never from a model and never from free text:

* told_answer      the teacher told the answer in the rehearsal
* no_ask_why       no turn asked a child how or why
* no_named_child   no turn was addressed to a named child (group scenes only; one-on-one is exempt)
* no_concrete      no turn used concrete objects, for moves whose card expects them

These come from simulated rehearsals, not classroom observation, and the caption says so.

Privacy follows the other aggregate cards: own district, consenting teachers only, and a cell (one
move and one habit) is shown only when at least `AGGREGATION_SUPPRESSION_N` teachers are in it;
below that the cell carries no count and no share. A move with fewer than N rehearsing teachers has
every cell suppressed. Counts only: no teacher, child or text is ever returned. Teachers flagged
`is_demo` are labelled as demo data.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.config import settings, v2_enabled
from backend.app.db.models import Scene, Teacher, Turn
from backend.app.rehearsal.scene_runner import load_move_card
from backend.app.rule_engine.domain import TeachingAct

HABIT_TOLD = "told_answer"
HABIT_NO_ASK = "no_ask_why"
HABIT_NO_NAMED = "no_named_child"
HABIT_NO_CONCRETE = "no_concrete"
HABITS: tuple[str, ...] = (HABIT_TOLD, HABIT_NO_ASK, HABIT_NO_NAMED, HABIT_NO_CONCRETE)

_ASK = TeachingAct.ASK_TO_EXPLAIN.value
_TOLD = TeachingAct.TELL_ANSWER.value
_CONCRETE = TeachingAct.CONCRETE_REPRESENTATION.value
_NO_NAMED_VALUES = (None, "", "all")


def enabled() -> bool:
    return v2_enabled(settings.TRAINING_GAP_ENABLED)


@dataclass(frozen=True)
class RehearsalFacts:
    """What one teacher's latest rehearsal of one move showed (no ids of children, no text)."""

    teacher_id: str
    move_id: str
    group: bool  # three children (True) or one child (False)
    acts_by_turn: tuple[tuple[str, ...], ...]
    addressed_by_turn: tuple[str | None, ...]
    expects_concrete: bool
    is_demo: bool = False


@dataclass
class GapCell:
    habit: str
    n: int | None  # teachers in this cell's group; None when withheld
    count: int | None  # of them, how many show the habit; None when withheld
    share: int | None  # whole percent; None when withheld
    applicable: bool = True  # False: the habit does not apply to this move ("not applicable")


@dataclass
class GapRow:
    move_id: str
    suppressed: bool
    cells: list[GapCell] = field(default_factory=list)
    gap: int = -1  # largest share among the shown cells, for sorting


@dataclass
class TrainingGap:
    window_days: int
    n_teachers: int = 0  # consenting teachers with a rehearsal in the window
    includes_demo: bool = False
    all_demo: bool = False
    rows: list[GapRow] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return self.n_teachers == 0


def habits_of(f: RehearsalFacts) -> dict[str, bool | None]:
    """Habit -> shown (True/False), or None where the habit does not apply to this rehearsal."""
    all_acts = {a for turn in f.acts_by_turn for a in turn}
    shown: dict[str, bool | None] = {
        HABIT_TOLD: _TOLD in all_acts,
        HABIT_NO_ASK: _ASK not in all_acts,
        HABIT_NO_NAMED: (
            not any(a not in _NO_NAMED_VALUES for a in f.addressed_by_turn) if f.group else None
        ),
        HABIT_NO_CONCRETE: (_CONCRETE not in all_acts) if f.expects_concrete else None,
    }
    return shown


def compute_gap(
    facts: Iterable[RehearsalFacts], *, suppress_below: int, window_days: int
) -> TrainingGap:
    """The table from each teacher's latest rehearsal per move (one fact per teacher and move)."""
    by_move: dict[str, list[RehearsalFacts]] = {}
    teachers: dict[str, bool] = {}
    for f in facts:
        by_move.setdefault(f.move_id, []).append(f)
        teachers[f.teacher_id] = teachers.get(f.teacher_id, True) and f.is_demo
    gap = TrainingGap(
        window_days=window_days,
        n_teachers=len(teachers),
        includes_demo=any(teachers.values()),
        all_demo=bool(teachers) and all(teachers.values()),
    )
    for move_id, group in by_move.items():
        row = GapRow(move_id=move_id, suppressed=len(group) < suppress_below)
        per_habit = [habits_of(f) for f in group]
        for habit in HABITS:
            applicable = [h[habit] for h in per_habit if h[habit] is not None]
            if not applicable:
                row.cells.append(GapCell(habit, None, None, None, applicable=False))
                continue
            n = len(applicable)
            if row.suppressed or n < suppress_below:
                row.cells.append(GapCell(habit, None, None, None))
                continue
            count = sum(1 for v in applicable if v)
            share = round(100 * count / n)
            row.cells.append(GapCell(habit, n, count, share))
            row.gap = max(row.gap, share)
        gap.rows.append(row)
    gap.rows.sort(key=lambda r: (r.suppressed, -r.gap, r.move_id))
    return gap


async def build_training_gap(
    session: AsyncSession, *, district: str | None = None, now: datetime | None = None
) -> TrainingGap:
    """Latest rehearsal per consenting teacher and move in the window, then `compute_gap`."""
    now = now or datetime.now(UTC)
    window = settings.TRAINING_GAP_WINDOW_DAYS
    stmt = (
        select(
            Scene.id,
            Scene.teacher_id,
            Scene.move_id,
            Scene.engine_state,
            Scene.started_at,
            Teacher.is_demo,
        )
        .join(Teacher, Teacher.id == Scene.teacher_id)
        .where(
            Scene.started_at >= now - timedelta(days=window),
            Scene.move_id.is_not(None),
            Teacher.consent_share_scores.is_(True),
        )
        .order_by(Scene.started_at.desc())
    )
    if district is not None:
        stmt = stmt.where(Teacher.district == district)
    scenes = list((await session.execute(stmt)).all())
    if not scenes:
        return TrainingGap(window_days=window)

    turn_rows = (
        await session.execute(
            select(Turn.scene_id, Turn.acts, Turn.addressed_child)
            .where(Turn.scene_id.in_([s[0] for s in scenes]), Turn.role == "teacher")
            .order_by(Turn.idx)
        )
    ).all()
    turns: dict[Any, list[tuple[tuple[str, ...], str | None]]] = {}
    for scene_id, acts, addressed in turn_rows:
        turns.setdefault(scene_id, []).append((tuple(acts or ()), addressed))

    expects: dict[str, bool] = {}
    latest: dict[tuple[Any, str], RehearsalFacts] = {}
    for scene_id, teacher_id, move_id, state, _started, is_demo in scenes:  # newest first
        key = (teacher_id, str(move_id))
        if key in latest or scene_id not in turns:
            continue
        if move_id not in expects:
            try:
                card = load_move_card(str(move_id))
                expects[move_id] = _CONCRETE in card.teaching_acts_effective
            except (FileNotFoundError, ValueError):
                expects[move_id] = False
        mine = turns[scene_id]
        latest[key] = RehearsalFacts(
            teacher_id=str(teacher_id),
            move_id=str(move_id),
            group=not bool((state or {}).get("one_on_one")),
            acts_by_turn=tuple(a for a, _ in mine),
            addressed_by_turn=tuple(c for _, c in mine),
            expects_concrete=expects[move_id],
            is_demo=bool(is_demo),
        )
    return compute_gap(
        latest.values(), suppress_below=settings.AGGREGATION_SUPPRESSION_N, window_days=window
    )


def training_gap_rows(gap: TrainingGap) -> list[dict[str, str | int]]:
    """The table as flat rows (one per move and habit) for the CSV download.

    Withheld cells carry empty count, share and n, so the file has the same suppression as the page.
    """
    out: list[dict[str, str | int]] = []
    for row in gap.rows:
        for cell in row.cells:
            out.append(
                {
                    "move_id": row.move_id,
                    "habit": cell.habit,
                    "teachers": "" if cell.n is None else cell.n,
                    "count": "" if cell.count is None else cell.count,
                    "share_percent": "" if cell.share is None else cell.share,
                    "status": (
                        "not_applicable"
                        if not cell.applicable
                        else "withheld"
                        if cell.n is None
                        else "shown"
                    ),
                }
            )
    return out


__all__ = [
    "HABITS",
    "GapCell",
    "GapRow",
    "RehearsalFacts",
    "TrainingGap",
    "build_training_gap",
    "compute_gap",
    "enabled",
    "habits_of",
    "training_gap_rows",
]
