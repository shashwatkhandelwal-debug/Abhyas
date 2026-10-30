"""ARP weekly digest generator (spec/09 §9.3, T32).

Strict privacy enforcement:
- Non-consenting teachers (consent_share_scores == False) NEVER appear by name or individual score.
- Non-consenting teachers are represented only as an aggregate count row: 'अन्य N शिक्षक (स्कोर साझा नहीं)'.
- Suggested visit list contains consenting teachers only.
- Escalated questions for non-consenting teachers display anonymised code 'शिक्षक #<short hash>'.
- All queries strictly scoped to the requesting ARP user's cluster (and demo scope).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

import yaml
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.access import (
    get_teacher_display_name_for_arp,
    scope_teachers_query,
)
from backend.app.core.messages import get_message
from backend.app.db.models import (
    AdoptionEvidence,
    AppUser,
    Cluster,
    Question,
    RehearsalScore,
    SessionState,
    Teacher,
)

logger = logging.getLogger("abhyas.reports.arp_digest")

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
MOVES_DIR = REPO_ROOT / "content" / "moves"


class ARPDigestItem(BaseModel):
    teacher_name: str
    practised_move: str
    rehearsal_completed: bool
    struggled_on: list[str] = []
    asked_questions: list[str] = []


class ARPDigestSummary(BaseModel):
    cluster_id: str
    total_teachers: int
    active_teachers_count: int
    unanswered_questions_count: int
    consenting_teacher_details: list[ARPDigestItem]
    suggested_visits: list[str]


def generate_arp_digest(
    cluster_id: str,
    teachers_data: list[dict[str, Any]],
) -> ARPDigestSummary:
    """Generates the weekly digest sent to the cluster ARP (for scheduled job snapshot)."""
    active_count = 0
    consenting_items: list[ARPDigestItem] = []
    suggested_visits: list[str] = []

    for t in teachers_data:
        if t.get("practised_this_week"):
            active_count += 1

        # Strict privacy check
        if t.get("consent_share_scores"):
            item = ARPDigestItem(
                teacher_name=t["name"],
                practised_move=t.get("move_id", "N/A"),
                rehearsal_completed=t.get("rehearsal_completed", False),
                struggled_on=t.get("struggled_on", []),
                asked_questions=t.get("questions", []),
            )
            consenting_items.append(item)
            if t.get("needs_visit_support"):
                suggested_visits.append(t["name"])

    return ARPDigestSummary(
        cluster_id=cluster_id,
        total_teachers=len(teachers_data),
        active_teachers_count=active_count,
        unanswered_questions_count=sum(len(t.get("questions", [])) for t in teachers_data),
        consenting_teacher_details=consenting_items,
        suggested_visits=suggested_visits,
    )


@dataclass(frozen=True)
class RubricDot:
    criterion: str
    score: int  # 0, 1, 2
    dot_class: str  # "dot-0", "dot-1", "dot-2"


@dataclass(frozen=True)
class TeacherDigestRow:
    teacher_id: str
    name: str
    school: str
    move_id: str
    move_title: str
    step_reached: str
    max_evidence_level: int
    rubric_dots: list[RubricDot]
    needs_help: bool
    avg_score: float | None


@dataclass(frozen=True)
class SuggestedVisit:
    teacher_id: str
    name: str
    school: str
    move_id: str
    move_title: str
    avg_score: float | None
    peer_checklist: list[str]


@dataclass(frozen=True)
class EscalatedQuestionItem:
    question_id: str
    teacher_id: str
    teacher_display_name: str
    text: str
    category: str | None
    created_at: datetime


@dataclass(frozen=True)
class ARPDigestData:
    cluster_id: str
    cluster_name: str
    selected_week_start: date
    available_weeks: list[date]
    total_teachers: int
    active_teachers_count: int
    completed_loops_count: int
    moves_practised_count: int
    consenting_teachers: list[TeacherDigestRow]
    non_consenting_count: int
    suggested_visits: list[SuggestedVisit]
    escalated_questions: list[EscalatedQuestionItem]


def _load_move_metadata(move_id: str) -> tuple[str, list[str]]:
    """Loads move title_hi and peer_checklist from content YAML, with fallback."""
    if not move_id or move_id == "-":
        return "-", []
    yaml_path = MOVES_DIR / f"{move_id}.yaml"
    if yaml_path.is_file():
        try:
            with open(yaml_path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
                title = str(data.get("title_hi", move_id))
                checklist = [str(item) for item in data.get("peer_checklist", [])]
                return title, checklist
        except Exception as e:
            logger.warning("Failed loading move %s: %s", move_id, e)
    return move_id, []


async def build_arp_digest(
    db: AsyncSession,
    user: AppUser,
    week_start: date | None = None,
) -> ARPDigestData:
    """Builds complete DB-backed ARP digest for the given cluster and week."""
    today = date.today()
    current_monday = today - timedelta(days=today.weekday())
    available_weeks = [current_monday - timedelta(weeks=i) for i in range(6)]

    selected_week = week_start if (week_start and week_start in available_weeks) else current_monday

    cluster_id = user.cluster_id or ""
    cluster_name = "क्लस्टर"
    if cluster_id:
        cluster = await db.get(Cluster, cluster_id)
        if cluster and cluster.name:
            cluster_name = cluster.name
        else:
            cluster_name = cluster_id

    # 1. Fetch teachers scoped to user's role and cluster
    t_query = select(Teacher)
    t_query = scope_teachers_query(t_query, user)
    teachers_res = await db.scalars(t_query)
    teachers = list(teachers_res.all())
    total_teachers = len(teachers)

    if not teachers:
        return ARPDigestData(
            cluster_id=cluster_id,
            cluster_name=cluster_name,
            selected_week_start=selected_week,
            available_weeks=available_weeks,
            total_teachers=0,
            active_teachers_count=0,
            completed_loops_count=0,
            moves_practised_count=0,
            consenting_teachers=[],
            non_consenting_count=0,
            suggested_visits=[],
            escalated_questions=[],
        )

    teacher_ids: list[UUID] = [t.id for t in teachers]
    teacher_map: dict[UUID, Teacher] = {t.id: t for t in teachers}

    # 2. Fetch SessionState for selected week
    ss_query = select(SessionState).where(
        SessionState.teacher_id.in_(teacher_ids),
        SessionState.week_start == selected_week,
    )
    ss_res = await db.scalars(ss_query)
    session_states = list(ss_res.all())
    session_map: dict[UUID, SessionState] = {s.teacher_id: s for s in session_states}

    # Counts
    active_teachers_count = len(session_states)
    completed_loops_count = sum(
        1 for s in session_states if s.state in ("REFLECT_SELF", "REFLECT_PEER", "DONE")
    )
    moves_practised_set = {s.move_id for s in session_states if s.move_id}
    moves_practised_count = len(moves_practised_set)

    # 3. Max evidence levels per teacher
    ev_query = (
        select(AdoptionEvidence.teacher_id, func.max(AdoptionEvidence.level))
        .where(AdoptionEvidence.teacher_id.in_(teacher_ids))
        .group_by(AdoptionEvidence.teacher_id)
    )
    ev_res = await db.execute(ev_query)
    evidence_map: dict[UUID, int] = {row[0]: int(row[1]) for row in ev_res.all()}

    # 4. Latest rehearsal scores for each teacher
    # Order by created_at desc to pick latest
    rs_query = (
        select(RehearsalScore)
        .where(RehearsalScore.teacher_id.in_(teacher_ids))
        .order_by(RehearsalScore.created_at.desc())
    )
    rs_res = await db.scalars(rs_query)
    latest_score_map: dict[UUID, RehearsalScore] = {}
    for score in rs_res.all():
        if score.teacher_id not in latest_score_map:
            latest_score_map[score.teacher_id] = score

    # 5. Escalated questions for this cluster
    q_query = (
        select(Question)
        .where(
            Question.teacher_id.in_(teacher_ids),
            Question.status == "escalated",
        )
        .order_by(Question.created_at.desc())
    )
    q_res = await db.scalars(q_query)
    escalated_qs = list(q_res.all())
    teachers_with_open_questions = {q.teacher_id for q in escalated_qs}

    # Cache move metadata
    move_meta_cache: dict[str, tuple[str, list[str]]] = {}

    def get_move_meta(mid: str) -> tuple[str, list[str]]:
        if mid not in move_meta_cache:
            move_meta_cache[mid] = _load_move_metadata(mid)
        return move_meta_cache[mid]

    # 6. Partition consenting vs non-consenting
    consenting_rows: list[TeacherDigestRow] = []
    non_consenting_count = 0
    suggested_visits: list[SuggestedVisit] = []

    for t in teachers:
        # Strict privacy check: non-consenting teachers NEVER appear by name or score
        if not t.consent_share_scores:
            non_consenting_count += 1
            continue

        ss = session_map.get(t.id)
        move_id = ss.move_id if ss else "-"
        step_reached = ss.state if ss else "NEW"
        move_title, peer_checklist = get_move_meta(move_id)
        max_evidence = evidence_map.get(t.id, 1)

        # Rubric dots
        rubric_dots: list[RubricDot] = []
        avg_score: float | None = None
        has_low_score = False

        r_score = latest_score_map.get(t.id)
        if r_score and isinstance(r_score.scores, dict):
            num_scores: list[int] = []
            for crit_id, val in r_score.scores.items():
                try:
                    s_val = int(val)
                except (ValueError, TypeError):
                    s_val = 0
                num_scores.append(s_val)
                dot_class = f"dot-{s_val}" if s_val in (0, 1, 2) else "dot-0"
                rubric_dots.append(
                    RubricDot(criterion=str(crit_id), score=s_val, dot_class=dot_class)
                )
                if s_val == 0:
                    has_low_score = True
            if num_scores:
                avg_score = round(sum(num_scores) / len(num_scores), 2)
                if avg_score < 1.0:
                    has_low_score = True

        has_open_q = t.id in teachers_with_open_questions
        needs_help = has_low_score or has_open_q

        teacher_name = t.name or "शिक्षिका"
        school_name = t.school_id or "प्राथमिक विद्यालय"

        row = TeacherDigestRow(
            teacher_id=str(t.id),
            name=teacher_name,
            school=school_name,
            move_id=move_id,
            move_title=move_title,
            step_reached=step_reached,
            max_evidence_level=max_evidence,
            rubric_dots=rubric_dots,
            needs_help=needs_help,
            avg_score=avg_score,
        )
        consenting_rows.append(row)

        if needs_help:
            suggested_visits.append(
                SuggestedVisit(
                    teacher_id=str(t.id),
                    name=teacher_name,
                    school=school_name,
                    move_id=move_id,
                    move_title=move_title,
                    avg_score=avg_score,
                    peer_checklist=peer_checklist,
                )
            )

    # Sort suggested visits by lowest average score
    suggested_visits.sort(key=lambda v: v.avg_score if v.avg_score is not None else -1.0)

    # 7. Escalated questions with anonymisation for non-consenting teachers
    escalated_items: list[EscalatedQuestionItem] = []
    for q in escalated_qs:
        t_obj = teacher_map.get(q.teacher_id)
        if t_obj:
            t_display = get_teacher_display_name_for_arp(user, t_obj)
        else:
            t_display = get_message("ui_arp_anonymous_teacher", code="unknown")

        escalated_items.append(
            EscalatedQuestionItem(
                question_id=str(q.id),
                teacher_id=str(q.teacher_id),
                teacher_display_name=t_display,
                text=q.text,
                category=q.category,
                created_at=q.created_at,
            )
        )

    return ARPDigestData(
        cluster_id=cluster_id,
        cluster_name=cluster_name,
        selected_week_start=selected_week,
        available_weeks=available_weeks,
        total_teachers=total_teachers,
        active_teachers_count=active_teachers_count,
        completed_loops_count=completed_loops_count,
        moves_practised_count=moves_practised_count,
        consenting_teachers=consenting_rows,
        non_consenting_count=non_consenting_count,
        suggested_visits=suggested_visits,
        escalated_questions=escalated_items,
    )
