"""Admin Operations Dashboard router (spec/09 §9.6, spec/14 T35).

Mounted by coordinator in main.py.

Routes:
- GET /admin
    Full system operations dashboard: latency percentiles, turn activity,
    guard metrics, LLM token consumption, WhatsApp template expenditure,
    scheduled jobs, active release status, and demo controls.
- POST /admin/reset-demo
    Resets demo teachers to clean initial state.
- POST /admin/fast-forward
    Fast-forwards pending scheduled jobs for a specific teacher.
"""

from __future__ import annotations

import logging
import math
import uuid
from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.csrf import (
    CSRF_COOKIE_NAME,
    generate_csrf_token,
    set_csrf_cookie,
    verify_csrf_token,
)
from backend.app.auth.guards import require_role
from backend.app.config import settings
from backend.app.core.messages import get_message
from backend.app.db.demo_data import SEED_TEACHER_IDS
from backend.app.db.models import (
    AdoptionEvidence,
    AppUser,
    CalibrationLabel,
    ContentRelease,
    ExplainScore,
    LLMCall,
    Message,
    Move,
    Question,
    RehearsalScore,
    ReviewItem,
    Scene,
    ScheduledJob,
    SessionState,
    Teacher,
    TemplateSend,
    Turn,
)
from backend.app.db.session import get_db_session
from backend.app.jobs.tick import fast_forward_teacher
from backend.app.sessions.state_machine import OnboardingStateEnum

logger = logging.getLogger("abhyas.web.admin")

WEB_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = WEB_DIR / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter(prefix="/admin", tags=["Admin Web"])


def calc_percentile(values: Sequence[float | int], p: float) -> int:
    """Calculates linear-interpolated integer percentile."""
    if not values:
        return 0
    sorted_vals = sorted(values)
    k = (len(sorted_vals) - 1) * (p / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return int(round(sorted_vals[int(k)]))
    d0 = sorted_vals[int(f)] * (c - k)
    d1 = sorted_vals[int(c)] * (k - f)
    return int(round(d0 + d1))


async def get_system_info(db: AsyncSession) -> dict[str, Any]:
    """Retrieves runtime environment, provider status, and active content release."""
    stmt = (
        select(ContentRelease)
        .where(ContentRelease.is_active == True)  # noqa: E712
        .limit(1)
    )
    release = (await db.execute(stmt)).scalar_one_or_none()

    moves_count_stmt = select(func.count(Move.id))
    moves_count = (await db.execute(moves_count_stmt)).scalar() or 0

    return {
        "environment": settings.ENVIRONMENT,
        "llm_provider": settings.LLM_PROVIDER,
        "stt_provider": settings.STT_PROVIDER,
        "tts_provider": settings.TTS_PROVIDER,
        "release_id": release.id if release else "None",
        "release_notes": release.notes if release else "None",
        "release_date": (release.published_at.strftime("%Y-%m-%d %H:%M") if release else "N/A"),
        "moves_count": moves_count,
    }


async def get_latency_stats(db: AsyncSession) -> dict[str, Any]:
    """Calculates p50 and p95 latency for last 24h & 7d, overall and by role/stage."""
    now = datetime.now(UTC)
    t_24h = now - timedelta(hours=24)
    t_7d = now - timedelta(days=7)

    stmt = select(LLMCall.role, LLMCall.latency_ms, LLMCall.created_at).where(
        LLMCall.created_at >= t_7d, LLMCall.latency_ms.isnot(None)
    )
    rows = (await db.execute(stmt)).all()

    all_24h: list[int] = []
    all_7d: list[int] = []
    by_role_24h: dict[str, list[int]] = defaultdict(list)
    by_role_7d: dict[str, list[int]] = defaultdict(list)

    for role, lat_ms, created_at in rows:
        if lat_ms is not None:
            r_name = role or "unknown"
            all_7d.append(lat_ms)
            by_role_7d[r_name].append(lat_ms)
            if created_at >= t_24h:
                all_24h.append(lat_ms)
                by_role_24h[r_name].append(lat_ms)

    roles = sorted(set(list(by_role_7d.keys()) + list(by_role_24h.keys())))
    role_rows: list[dict[str, Any]] = []
    for r in roles:
        v24 = by_role_24h.get(r, [])
        v7d = by_role_7d.get(r, [])
        role_rows.append(
            {
                "role": r,
                "calls_24h": len(v24),
                "p50_24h": calc_percentile(v24, 50),
                "p95_24h": calc_percentile(v24, 95),
                "calls_7d": len(v7d),
                "p50_7d": calc_percentile(v7d, 50),
                "p95_7d": calc_percentile(v7d, 95),
            }
        )

    return {
        "overall_p50_24h": calc_percentile(all_24h, 50),
        "overall_p95_24h": calc_percentile(all_24h, 95),
        "overall_calls_24h": len(all_24h),
        "overall_p50_7d": calc_percentile(all_7d, 50),
        "overall_p95_7d": calc_percentile(all_7d, 95),
        "overall_calls_7d": len(all_7d),
        "by_role": role_rows,
    }


async def get_turns_stats(db: AsyncSession) -> dict[str, Any]:
    """Calculates turns count for last 24h, 7d, and total by role."""
    now = datetime.now(UTC)
    t_24h = now - timedelta(hours=24)
    t_7d = now - timedelta(days=7)

    total_stmt = select(func.count(Turn.id))
    total_turns = (await db.execute(total_stmt)).scalar() or 0

    stmt_24h = select(func.count(Turn.id)).where(Turn.created_at >= t_24h)
    turns_24h = (await db.execute(stmt_24h)).scalar() or 0

    stmt_7d = select(func.count(Turn.id)).where(Turn.created_at >= t_7d)
    turns_7d = (await db.execute(stmt_7d)).scalar() or 0

    stmt_role = select(Turn.role, func.count(Turn.id)).group_by(Turn.role)
    role_counts = dict((await db.execute(stmt_role)).all())

    return {
        "total": total_turns,
        "turns_24h": turns_24h,
        "turns_7d": turns_7d,
        "by_role": role_counts,
    }


async def get_guard_stats(db: AsyncSession) -> dict[str, Any]:
    """Computes guard pass, retry, and fallback percentages plus recent failures."""
    stmt = select(LLMCall.outcome, func.count(LLMCall.id)).group_by(LLMCall.outcome)
    rows = dict((await db.execute(stmt)).all())

    pass_count = rows.get("pass", 0)
    retry_count = rows.get("retry", 0)
    fallback_count = rows.get("fallback", 0)
    total = pass_count + retry_count + fallback_count

    stmt_gf = select(func.count(ReviewItem.id)).where(ReviewItem.kind == "guard_failure")
    guard_failure_items = (await db.execute(stmt_gf)).scalar() or 0

    pass_pct = round((pass_count / total * 100.0), 1) if total > 0 else 100.0
    retry_pct = round((retry_count / total * 100.0), 1) if total > 0 else 0.0
    fallback_pct = round((fallback_count / total * 100.0), 1) if total > 0 else 0.0

    stmt_recent = (
        select(ReviewItem)
        .where(ReviewItem.kind == "guard_failure")
        .order_by(ReviewItem.created_at.desc())
        .limit(5)
    )
    recent_failures = (await db.execute(stmt_recent)).scalars().all()

    return {
        "total": total,
        "pass_count": pass_count,
        "pass_pct": pass_pct,
        "retry_count": retry_count,
        "retry_pct": retry_pct,
        "fallback_count": fallback_count,
        "fallback_pct": fallback_pct,
        "review_items_count": guard_failure_items,
        "recent_failures": recent_failures,
    }


async def get_llm_token_stats(db: AsyncSession) -> list[dict[str, Any]]:
    """Retrieves token consumption totals grouped by runtime role."""
    stmt = (
        select(
            LLMCall.role,
            func.count(LLMCall.id).label("calls"),
            func.sum(LLMCall.input_tokens).label("in_tokens"),
            func.sum(LLMCall.output_tokens).label("out_tokens"),
        )
        .group_by(LLMCall.role)
        .order_by(func.count(LLMCall.id).desc())
    )
    rows = (await db.execute(stmt)).all()
    result: list[dict[str, Any]] = []
    for r in rows:
        m = r._mapping
        in_tok = int(m["in_tokens"] or 0)
        out_tok = int(m["out_tokens"] or 0)
        result.append(
            {
                "role": str(m["role"] or "unknown"),
                "calls": int(m["calls"] or 0),
                "input_tokens": in_tok,
                "output_tokens": out_tok,
                "total_tokens": in_tok + out_tok,
            }
        )
    return result


async def get_template_stats(db: AsyncSession) -> dict[str, Any]:
    """Calculates WhatsApp template sends and estimated cost for the current week."""
    now = datetime.now(UTC)
    today = now.date()
    week_start = datetime.combine(
        today - timedelta(days=today.weekday()), datetime.min.time(), tzinfo=UTC
    )

    stmt = (
        select(
            TemplateSend.template_name,
            TemplateSend.category,
            func.count(TemplateSend.id).label("count"),
            func.sum(TemplateSend.est_cost_inr).label("cost"),
        )
        .where(TemplateSend.sent_at >= week_start)
        .group_by(TemplateSend.template_name, TemplateSend.category)
    )
    rows = (await db.execute(stmt)).all()

    total_sends = sum(int(r._mapping["count"] or 0) for r in rows)
    total_cost = sum(float(r._mapping["cost"] or 0.0) for r in rows)

    return {
        "total_sends": total_sends,
        "total_cost_inr": round(total_cost, 2),
        "templates": [
            {
                "template_name": str(r._mapping["template_name"] or "unknown"),
                "category": str(r._mapping["category"] or "utility"),
                "count": int(r._mapping["count"] or 0),
                "cost_inr": round(float(r._mapping["cost"] or 0.0), 3),
            }
            for r in rows
        ],
    }


async def get_scheduled_jobs_stats(db: AsyncSession) -> dict[str, Any]:
    """Retrieves scheduled job counts and lists recent pending/failed executions."""
    stmt_counts = select(ScheduledJob.status, func.count(ScheduledJob.id)).group_by(
        ScheduledJob.status
    )
    status_counts = dict((await db.execute(stmt_counts)).all())

    stmt_recent = select(ScheduledJob).order_by(ScheduledJob.run_at.desc()).limit(10)
    recent_jobs = (await db.execute(stmt_recent)).scalars().all()

    return {
        "pending": status_counts.get("pending", 0),
        "failed": status_counts.get("failed", 0),
        "done": status_counts.get("done", 0),
        "cancelled": status_counts.get("cancelled", 0),
        "recent_jobs": recent_jobs,
    }


async def get_demo_teachers(db: AsyncSession) -> list[dict[str, Any]]:
    """Returns demo teacher records for fast-forward controls."""
    stmt = (
        select(Teacher)
        .where(Teacher.is_demo == True)  # noqa: E712
        .order_by(Teacher.name)
    )
    teachers = (await db.execute(stmt)).scalars().all()
    return [
        {
            "id": str(t.id),
            "name": t.name or "डेमो शिक्षक",
            "school_id": t.school_id or "-",
            "onboarding_state": t.onboarding_state,
        }
        for t in teachers
    ]


async def reset_demo_data(session: AsyncSession) -> dict[str, int]:
    """Resets evaluator demo teachers (teacher.demo1..3) to clean initial state (spec/09 §9.6).

    Preserves the 51-teacher background cohort so trainer and ARP dashboards remain unsuppressed.
    """
    demo_teacher_ids = list(SEED_TEACHER_IDS)

    # 1. Clean up calibration labels referencing demo scenes
    stmt_scenes = select(Scene.id).where(Scene.teacher_id.in_(demo_teacher_ids))
    demo_scene_ids = list((await session.execute(stmt_scenes)).scalars().all())
    if demo_scene_ids:
        await session.execute(
            delete(CalibrationLabel).where(CalibrationLabel.scene_id.in_(demo_scene_ids))
        )

    # 2. Clean up review items referencing demo questions or scores
    stmt_q = select(Question.id).where(Question.teacher_id.in_(demo_teacher_ids))
    q_ids = [str(qid) for qid in (await session.execute(stmt_q)).scalars().all()]

    stmt_rs = select(RehearsalScore.id).where(RehearsalScore.teacher_id.in_(demo_teacher_ids))
    rs_ids = [str(rid) for rid in (await session.execute(stmt_rs)).scalars().all()]

    stmt_es = select(ExplainScore.id).where(ExplainScore.teacher_id.in_(demo_teacher_ids))
    es_ids = [str(eid) for eid in (await session.execute(stmt_es)).scalars().all()]

    ref_ids_to_delete = q_ids + rs_ids + es_ids
    if ref_ids_to_delete:
        await session.execute(delete(ReviewItem).where(ReviewItem.ref_id.in_(ref_ids_to_delete)))

    # 3. Clean up scheduled jobs referencing demo teachers
    stmt_jobs = select(ScheduledJob)
    all_jobs = (await session.execute(stmt_jobs)).scalars().all()
    target_t_ids = {str(tid) for tid in demo_teacher_ids}
    jobs_to_delete = [
        j.id for j in all_jobs if j.payload and str(j.payload.get("teacher_id")) in target_t_ids
    ]
    if jobs_to_delete:
        await session.execute(delete(ScheduledJob).where(ScheduledJob.id.in_(jobs_to_delete)))

    # 4. Delete questions, evidence, scores, turns, scenes, messages, session states for demo teachers
    await session.execute(delete(Question).where(Question.teacher_id.in_(demo_teacher_ids)))
    await session.execute(
        delete(AdoptionEvidence).where(AdoptionEvidence.teacher_id.in_(demo_teacher_ids))
    )
    await session.execute(delete(Turn).where(Turn.teacher_id.in_(demo_teacher_ids)))
    await session.execute(delete(Scene).where(Scene.teacher_id.in_(demo_teacher_ids)))
    await session.execute(
        delete(RehearsalScore).where(RehearsalScore.teacher_id.in_(demo_teacher_ids))
    )
    await session.execute(delete(ExplainScore).where(ExplainScore.teacher_id.in_(demo_teacher_ids)))
    await session.execute(delete(Message).where(Message.teacher_id.in_(demo_teacher_ids)))
    await session.execute(delete(SessionState).where(SessionState.teacher_id.in_(demo_teacher_ids)))

    # 5. Reset demo 1, 2, 3 to baseline seed states
    t1 = await session.get(Teacher, SEED_TEACHER_IDS[0])
    if t1:
        t1.onboarding_state = OnboardingStateEnum.NEW
        t1.last_inbound_at = None

    t2 = await session.get(Teacher, SEED_TEACHER_IDS[1])
    if t2:
        t2.onboarding_state = OnboardingStateEnum.READY
        t2.last_inbound_at = datetime.now(UTC)
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
        s2 = SessionState(
            teacher_id=t2.id,
            week_start=week_start,
            move_id="NUM_SUB_REGROUP_BUNDLES",
            state="REHEARSE",
            prior_state="MODEL",
            rehearse_attempts=1,
            context={
                "current_move_id": "NUM_SUB_REGROUP_BUNDLES",
                "current_state": "REHEARSE",
            },
        )
        session.add(s2)

    t3 = await session.get(Teacher, SEED_TEACHER_IDS[2])
    if t3:
        t3.onboarding_state = OnboardingStateEnum.READY
        t3.last_inbound_at = datetime.now(UTC)

    await session.commit()
    logger.info("Admin reset demo seed records for %d teachers", len(demo_teacher_ids))
    return {"reset_teachers": len(demo_teacher_ids)}


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def admin_dashboard(
    request: Request,
    _admin: Annotated[AppUser, Depends(require_role("admin"))],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    msg: str | None = None,
    advanced: int | None = None,
) -> Response:
    """Renders the comprehensive operations admin dashboard."""
    csrf_token = request.cookies.get(CSRF_COOKIE_NAME) or generate_csrf_token()

    sys_info = await get_system_info(db)
    latency_stats = await get_latency_stats(db)
    turns_stats = await get_turns_stats(db)
    guard_stats = await get_guard_stats(db)
    token_stats = await get_llm_token_stats(db)
    template_stats = await get_template_stats(db)
    job_stats = await get_scheduled_jobs_stats(db)
    demo_teachers = await get_demo_teachers(db)

    response = templates.TemplateResponse(
        request=request,
        name="admin.html",
        context={
            "request": request,
            "admin_user": _admin,
            "csrf_token": csrf_token,
            "system_info": sys_info,
            "latency_stats": latency_stats,
            "turns_stats": turns_stats,
            "guard_stats": guard_stats,
            "token_stats": token_stats,
            "template_stats": template_stats,
            "job_stats": job_stats,
            "demo_teachers": demo_teachers,
            "msg": msg,
            "advanced": advanced,
            "get_message": get_message,
        },
    )
    if not request.cookies.get(CSRF_COOKIE_NAME):
        set_csrf_cookie(response, csrf_token)
    return response


@router.post(
    "/reset-demo",
    dependencies=[Depends(verify_csrf_token)],
)
async def admin_reset_demo(
    _admin: Annotated[AppUser, Depends(require_role("admin"))],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> RedirectResponse:
    """Handles demo cohort reset form submission."""
    await reset_demo_data(db)
    return RedirectResponse(url="/admin?msg=reset_ok", status_code=status.HTTP_303_SEE_OTHER)


@router.post(
    "/fast-forward",
    dependencies=[Depends(verify_csrf_token)],
)
async def admin_fast_forward(
    teacher_id: Annotated[str, Form(...)],
    _admin: Annotated[AppUser, Depends(require_role("admin"))],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> RedirectResponse:
    """Handles fast-forwarding scheduled jobs for a selected demo teacher."""
    try:
        t_uuid = uuid.UUID(teacher_id.strip())
    except ValueError:
        return RedirectResponse(url="/admin?msg=error", status_code=status.HTTP_303_SEE_OTHER)

    teacher = await db.get(Teacher, t_uuid)
    if not teacher:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Teacher not found")

    if not teacher.is_demo:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot fast-forward a non-demo teacher",
        )

    result = await fast_forward_teacher(t_uuid)
    return RedirectResponse(
        url=f"/admin?msg=ff_ok&advanced={result.advanced}",
        status_code=status.HTTP_303_SEE_OTHER,
    )
