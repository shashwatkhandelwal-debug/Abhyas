"""Deterministic personal move-path scoring (spec/08 §8.5, T23).

Pure functions: no I/O, no clock, no database. Callers pass move metadata taken from
the published content (`MoveCard`) and teacher facts taken from the database.

    score = month_rank * 10
          - 15 if placement used tell_answer and the move's effective acts include ask_to_explain
          - 10 if the teacher teaches class 1 and (move is literacy or id starts NUM_PLACE_VALUE)
          - 5 * (2 - min rubric score on the move's criteria in the last attempt)   # done moves only
          - 8 if a question the teacher asked matched one of the move's tags
          + 100 if the move is already DONE with evidence >= 2

Lower score = sooner. Reasons are machine-readable codes (never Hindi text): the
presentation layer maps them to catalog strings.

Spec gaps resolved here (record in PROGRESS.md > Decisions):
- A past `sankul_month` is treated as due now (rank 0), not pushed a year out.
- A move with no/unknown `sankul_month` gets `UNSCHEDULED_MONTH_RANK`, so it never
  outranks a scheduled move on that term alone.
- The class-1 bonus applies when the teacher teaches class 1 AND the move is literacy
  or a place-value move (the spec line is ambiguous about precedence).
"""

from __future__ import annotations

import calendar
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field

MONTH_WEIGHT = 10
TELL_ANSWER_BONUS = -15
CLASS_ONE_BONUS = -10
WEAK_RUBRIC_WEIGHT = 5
QUESTION_TAG_BONUS = -8
DONE_PENALTY = 100
DONE_MIN_EVIDENCE = 2
UNSCHEDULED_MONTH_RANK = 11

_MONTHS = {name.lower(): i for i, name in enumerate(calendar.month_name) if name}


@dataclass(frozen=True, slots=True)
class MoveFacts:
    id: str
    domain: str
    sankul_month: str | None
    effective_acts: frozenset[str]
    tags: frozenset[str]


@dataclass(frozen=True, slots=True)
class TeacherFacts:
    current_month: int
    classes: tuple[int, ...] = ()
    placement_used_tell_answer: bool = False
    done_evidence: Mapping[str, int] = field(
        default_factory=dict
    )  # move_id -> max level, DONE moves
    min_rubric: Mapping[str, float] = field(
        default_factory=dict
    )  # move_id -> min score, last attempt
    question_tags: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class PathEntry:
    position: int
    move_id: str
    score: int
    reasons: tuple[str, ...]


def month_number(name: str | None) -> int | None:
    """1-12 from an English month name ('September'), else None."""
    if name is None:
        return None
    return _MONTHS.get(name.strip().lower())


def month_rank(sankul_month: str | None, current_month: int) -> int:
    if not 1 <= current_month <= 12:
        raise ValueError("current_month must be 1-12")
    month = month_number(sankul_month)
    if month is None:
        return UNSCHEDULED_MONTH_RANK
    return max(0, month - current_month)


def score_move(move: MoveFacts, teacher: TeacherFacts) -> tuple[int, tuple[str, ...]]:
    rank = month_rank(move.sankul_month, teacher.current_month)
    score = rank * MONTH_WEIGHT
    reasons = [f"month_rank={rank}"]

    if teacher.placement_used_tell_answer and "ask_to_explain" in move.effective_acts:
        score += TELL_ANSWER_BONUS
        reasons.append("tell_answer_needs_ask_to_explain")
    if 1 in teacher.classes and (
        move.domain == "literacy" or move.id.startswith("NUM_PLACE_VALUE")
    ):
        score += CLASS_ONE_BONUS
        reasons.append("class_1_priority")

    done_level = teacher.done_evidence.get(move.id)
    if done_level is not None and move.id in teacher.min_rubric:
        weakness = 2 - min(2.0, max(0.0, teacher.min_rubric[move.id]))
        weak = round(WEAK_RUBRIC_WEIGHT * weakness)
        if weak:
            score -= weak
            reasons.append("revisit_weak_rubric")
    if move.tags & teacher.question_tags:
        score += QUESTION_TAG_BONUS
        reasons.append("matches_teacher_question")
    if done_level is not None and done_level >= DONE_MIN_EVIDENCE:
        score += DONE_PENALTY
        reasons.append("already_done")
    return score, tuple(reasons)


def rank_moves(
    moves: Sequence[MoveFacts],
    teacher: TeacherFacts,
    *,
    fixed_order: Sequence[str] | None = None,
    exclude: Collection[str] = (),
) -> list[PathEntry]:
    """Ordered path. `fixed_order` (first-year induction track) pins those moves first,
    in that order, skipping ids that do not exist; remaining moves follow by score.

    Ties break by earlier sankul month, then move id, so the result is deterministic.
    """
    candidates = {m.id: m for m in moves if m.id not in set(exclude)}
    scored = {mid: score_move(m, teacher) for mid, m in candidates.items()}

    pinned = [mid for mid in (fixed_order or ()) if mid in candidates]
    pinned = list(dict.fromkeys(pinned))
    rest = sorted(
        (mid for mid in candidates if mid not in set(pinned)),
        key=lambda mid: (
            scored[mid][0],
            month_number(candidates[mid].sankul_month) or 13,
            mid,
        ),
    )
    entries: list[PathEntry] = []
    for position, mid in enumerate(pinned + rest, start=1):
        score, reasons = scored[mid]
        if mid in pinned:
            reasons = ("first_year_induction_order", *reasons)
        entries.append(PathEntry(position=position, move_id=mid, score=score, reasons=reasons))
    return entries
