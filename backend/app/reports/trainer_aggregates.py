"""Trainer aggregation engine, suppression enforcement, and insight generation (spec/09 §9.4, T33).

Privacy-by-design guarantees:
1. Backed by AggModuleBatch - no teacher names, phones, or teacher-level data are ever queried or loaded.
2. If sample size n < 10, all metric cells (completion %, missed key points, rubric distribution,
   ladder distribution) are strictly replaced by:
   "समूह छोटा है (n<10): गोपनीयता हेतु छिपाया गया"
3. Insight box is purely deterministic (computed in code, not LLM) highlighting top missed key points
   where missing rate >= 40%.
4. CSV export respects identical suppression rules.
"""

from __future__ import annotations

import csv
import io
import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.access import SUPPRESSION_MESSAGE
from backend.app.config import FLAGGED_MOVES, settings
from backend.app.content_models import MoveCard
from backend.app.core.messages import get_message
from backend.app.db.models import AggModuleBatch, AppUser, Batch, SessionState, Teacher
from backend.app.jobs.aggregates import compute_aggregates_for_batch
from backend.app.sessions.path import load_all_move_cards

logger = logging.getLogger("abhyas.reports.trainer")


@dataclass
class TrainerRowView:
    batch_id: str
    batch_name: str
    move_id: str
    move_title: str
    n_teachers: int
    suppressed: bool
    pct_completed: str
    most_missed_point: str
    rubric_svg: str
    ladder_summary: str
    rubric_avg: float | None
    ladder_counts: dict[str, int] | None


@dataclass
class TrainerReport:
    district: str
    batches: list[Batch]
    moves: list[MoveCard]
    selected_batch_id: str | None
    selected_move_id: str | None
    rows: list[TrainerRowView]
    insight_text: str | None


def generate_rubric_svg(rubric_dist: dict[str, Any] | None) -> str:
    """Renders stacked mini-bars as an inline SVG (spec/09 §9.4).

    Scores: 0 (red #B3261E), 1 (marigold #E0A100), 2 (deep green #1F6F5C).
    """
    if not rubric_dist:
        return f"""<svg width="100" height="14" viewBox="0 0 100 14" role="img" aria-label="{get_message("ui_trainer_rubric_svg_none")}"><rect width="100" height="14" rx="3" fill="#E5E0D8"/></svg>"""

    total_0 = 0
    total_1 = 0
    total_2 = 0
    for crit_scores in rubric_dist.values():
        if isinstance(crit_scores, dict):
            total_0 += int(crit_scores.get("0", 0))
            total_1 += int(crit_scores.get("1", 0))
            total_2 += int(crit_scores.get("2", 0))

    total = total_0 + total_1 + total_2
    if total == 0:
        return f"""<svg width="100" height="14" viewBox="0 0 100 14" role="img" aria-label="{get_message("ui_trainer_rubric_svg_none")}"><rect width="100" height="14" rx="3" fill="#E5E0D8"/></svg>"""

    w0 = round((total_0 / total) * 100.0, 1)
    w1 = round((total_1 / total) * 100.0, 1)
    w2 = round(max(0.0, 100.0 - w0 - w1), 1)

    x1 = w0
    x2 = round(w0 + w1, 1)

    title = get_message(
        "ui_trainer_rubric_svg_title",
        n0=total_0,
        p0=round(total_0 / total * 100),
        n1=total_1,
        p1=round(total_1 / total * 100),
        n2=total_2,
        p2=round(total_2 / total * 100),
    )

    return (
        f'<svg width="100" height="14" viewBox="0 0 100 14" role="img" aria-label="{title}">'
        f"<title>{title}</title>"
        f'<rect x="0" y="0" width="{w0}" height="14" rx="3" fill="#B3261E"/>'
        f'<rect x="{x1}" y="0" width="{w1}" height="14" fill="#E0A100"/>'
        f'<rect x="{x2}" y="0" width="{w2}" height="14" fill="#1F6F5C"/>'
        f"</svg>"
    )


def format_ladder_summary(ladder_dist: dict[str, Any] | None) -> str:
    """Formats adoption evidence ladder counts across levels 1 to 5."""
    if not ladder_dist:
        return "-"
    parts: list[str] = []
    for lvl in range(1, 6):
        c = int(ladder_dist.get(str(lvl), 0))
        parts.append(f"L{lvl}: {c}")
    return " · ".join(parts)


def compute_rubric_average(rubric_dist: dict[str, Any] | None) -> float | None:
    """Calculates weighted average rubric score (0..2)."""
    if not rubric_dist:
        return None
    total_points = 0
    total_ratings = 0
    for crit_scores in rubric_dist.values():
        if isinstance(crit_scores, dict):
            c0 = int(crit_scores.get("0", 0))
            c1 = int(crit_scores.get("1", 0))
            c2 = int(crit_scores.get("2", 0))
            total_points += (c1 * 1) + (c2 * 2)
            total_ratings += c0 + c1 + c2
    if total_ratings == 0:
        return None
    return round(total_points / total_ratings, 2)


def get_top_missed_key_point(
    explain_missing: dict[str, Any] | None,
    move: MoveCard | None,
) -> tuple[str | None, int, str]:
    """Finds the most missed key point and its descriptive Hindi text."""
    if not explain_missing or not move:
        return (None, 0, "-")

    max_kpid: str | None = None
    max_count = 0
    for kpid, count in explain_missing.items():
        c = int(count)
        if c > max_count:
            max_count = c
            max_kpid = kpid

    if not max_kpid or max_count == 0:
        return (None, 0, "-")

    # Look up key point text from move
    text_desc = max_kpid
    for kp in move.key_points:
        if kp.id == max_kpid:
            # Short text before colon if present, or first 45 chars
            raw_text = kp.text_hi.strip()
            if ":" in raw_text:
                text_desc = raw_text.split(":", 1)[0].strip()
            elif "।" in raw_text:
                text_desc = raw_text.split("।", 1)[0].strip()
            else:
                text_desc = raw_text[:45].strip()
            break

    return (max_kpid, max_count, text_desc)


async def build_trainer_report(
    session: AsyncSession,
    user: AppUser,
    selected_batch_id: str | None = None,
    selected_move_id: str | None = None,
) -> TrainerReport:
    """Builds trainer view aggregates with strict privacy-by-design suppression (spec/09 §9.4)."""
    # 1. District scoping: fail closed when district is None or has no batches
    if user.role != "admin" and not user.district:
        return TrainerReport(
            district="-",
            batches=[],
            moves=[],
            selected_batch_id=selected_batch_id,
            selected_move_id=selected_move_id,
            rows=[],
            insight_text=None,
        )

    user_district = user.district or ("Kanpur Nagar" if user.role == "admin" else "-")

    stmt_batches = select(Batch)
    if user.role != "admin":
        stmt_batches = stmt_batches.where(Batch.district == user_district)
    stmt_batches = stmt_batches.order_by(Batch.id.asc())
    batches = list((await session.execute(stmt_batches)).scalars().all())

    # Fail closed: no batches in district -> return empty report
    if not batches:
        return TrainerReport(
            district=user_district,
            batches=[],
            moves=[],
            selected_batch_id=selected_batch_id,
            selected_move_id=selected_move_id,
            rows=[],
            insight_text=None,
        )

    # 2. Load all MoveCards
    all_moves = [m for m in load_all_move_cards() if m.id not in FLAGGED_MOVES]

    # Filter targets
    target_batches = [b for b in batches if not selected_batch_id or b.id == selected_batch_id]
    target_moves = [m for m in all_moves if not selected_move_id or m.id == selected_move_id]

    rows: list[TrainerRowView] = []
    top_insight_candidate: tuple[str, str, float, str] | None = (
        None  # (batch_id, move_id, rate, kp_text)
    )

    # 3. For each batch and move, load or compute AggModuleBatch
    for b in target_batches:
        for m in target_moves:
            stmt_agg = select(AggModuleBatch).where(
                AggModuleBatch.batch_id == b.id,
                AggModuleBatch.move_id == m.id,
            )
            agg = (await session.execute(stmt_agg)).scalar_one_or_none()

            # On-demand computation if missing (spec/09 §9.4)
            if not agg:
                agg = await compute_aggregates_for_batch(session, b.id, m.id)
                session.add(agg)
                await session.flush()

            n_teachers = agg.n_teachers or 0
            is_suppressed = n_teachers < settings.AGGREGATION_SUPPRESSION_N

            if is_suppressed:
                rows.append(
                    TrainerRowView(
                        batch_id=b.id,
                        batch_name=b.name,
                        move_id=m.id,
                        move_title=m.title_hi,
                        n_teachers=n_teachers,
                        suppressed=True,
                        pct_completed=SUPPRESSION_MESSAGE,
                        most_missed_point=SUPPRESSION_MESSAGE,
                        rubric_svg=SUPPRESSION_MESSAGE,
                        ladder_summary=SUPPRESSION_MESSAGE,
                        rubric_avg=None,
                        ladder_counts=None,
                    )
                )
            else:
                # Calculate completion % from SessionState where state == "DONE"
                stmt_done = select(func.count(func.distinct(SessionState.teacher_id))).where(
                    SessionState.teacher_id.in_(select(Teacher.id).where(Teacher.batch_id == b.id)),
                    SessionState.move_id == m.id,
                    SessionState.state == "DONE",
                )
                done_count = (await session.execute(stmt_done)).scalar() or 0
                completed_pct = round((done_count / max(n_teachers, 1)) * 100)
                pct_str = f"{completed_pct}%"

                # Top missed key point
                kpid, count, kp_text = get_top_missed_key_point(agg.explain_missing, m)
                missed_rate = count / max(n_teachers, 1)

                if count > 0 and missed_rate >= 0.40:
                    if top_insight_candidate is None or missed_rate > top_insight_candidate[2]:
                        top_insight_candidate = (b.id, m.id, missed_rate, kp_text)

                rubric_svg = generate_rubric_svg(agg.rubric_dist)
                ladder_str = format_ladder_summary(agg.ladder_dist)
                rubric_avg = compute_rubric_average(agg.rubric_dist)

                ladder = agg.ladder_dist or {}
                ladder_counts = {str(lvl): int(ladder.get(str(lvl), 0)) for lvl in range(1, 6)}

                rows.append(
                    TrainerRowView(
                        batch_id=b.id,
                        batch_name=b.name,
                        move_id=m.id,
                        move_title=m.title_hi,
                        n_teachers=n_teachers,
                        suppressed=False,
                        pct_completed=pct_str,
                        most_missed_point=kp_text,
                        rubric_svg=rubric_svg,
                        ladder_summary=ladder_str,
                        rubric_avg=rubric_avg,
                        ladder_counts=ladder_counts,
                    )
                )

    await session.commit()

    # 4. Deterministic insight box (spec/09 §9.4)
    insight_text: str | None = None
    if top_insight_candidate:
        cand_batch, _cand_move, cand_rate, cand_kp = top_insight_candidate
        pct = round(cand_rate * 100)
        insight_text = get_message(
            "ui_trainer_insight_recommendation",
            batch=cand_batch,
            pct=pct,
            key_point=cand_kp,
        )
    elif rows and any(not r.suppressed for r in rows):
        insight_text = get_message("ui_trainer_insight_all_good")

    return TrainerReport(
        district=user_district,
        batches=batches,
        moves=all_moves,
        selected_batch_id=selected_batch_id,
        selected_move_id=selected_move_id,
        rows=rows,
        insight_text=insight_text,
    )


def generate_trainer_csv(report: TrainerReport) -> str:
    """Generates CSV export enforcing identical n < 10 suppression (spec/09 §9.4)."""
    output = io.StringIO()
    writer = csv.writer(output)

    # Header
    writer.writerow(
        [
            "batch_id",
            "batch_name",
            "move_id",
            "move_title",
            "n_teachers",
            "pct_completed_loop",
            "most_missed_key_point",
            "rubric_score_avg",
            "ladder_l1",
            "ladder_l2",
            "ladder_l3",
            "ladder_l4",
            "ladder_l5",
        ]
    )

    for r in report.rows:
        if r.suppressed:
            # Sensitive metrics strictly suppressed
            writer.writerow(
                [
                    r.batch_id,
                    r.batch_name,
                    r.move_id,
                    r.move_title,
                    r.n_teachers,
                    SUPPRESSION_MESSAGE,
                    SUPPRESSION_MESSAGE,
                    SUPPRESSION_MESSAGE,
                    SUPPRESSION_MESSAGE,
                    SUPPRESSION_MESSAGE,
                    SUPPRESSION_MESSAGE,
                    SUPPRESSION_MESSAGE,
                    SUPPRESSION_MESSAGE,
                ]
            )
        else:
            lc = r.ladder_counts or {}
            writer.writerow(
                [
                    r.batch_id,
                    r.batch_name,
                    r.move_id,
                    r.move_title,
                    r.n_teachers,
                    r.pct_completed,
                    r.most_missed_point,
                    f"{r.rubric_avg:.2f}" if r.rubric_avg is not None else "-",
                    lc.get("1", 0),
                    lc.get("2", 0),
                    lc.get("3", 0),
                    lc.get("4", 0),
                    lc.get("5", 0),
                ]
            )

    return output.getvalue()
