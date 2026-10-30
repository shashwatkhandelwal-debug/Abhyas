"""Trainer view web routes and CSV export (spec/09 §9.4, T33).

District-level training view backed by AggModuleBatch:
- Tables: batch x move aggregates with completion %, missed key points, inline SVG rubric bars, ladder distribution.
- Privacy-by-design: all metrics for groups with n < 10 are replaced with:
  "समूह छोटा है (n<10) — गोपनीयता हेतु छिपाया गया"
- Zero individual teacher data or PII is exposed anywhere.
- Deterministic training insight box computed from top missed key point where rate >= 40%.
- GET /trainer/export.csv provides export with identical privacy suppression.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.access import SUPPRESSION_MESSAGE
from backend.app.auth.csrf import generate_csrf_token, set_csrf_cookie
from backend.app.auth.guards import require_role
from backend.app.class_profile.library import citations
from backend.app.config import settings
from backend.app.core.messages import get_message, get_ui_lang
from backend.app.db.models import AppUser
from backend.app.db.session import get_db_session
from backend.app.rehearsal.scene_runner import load_move_card
from backend.app.reports.class_struggles import class_struggle_summary
from backend.app.reports.cluster_pack import build_cluster_pack
from backend.app.reports.module_progress import module_progress_summary
from backend.app.reports.reported_vs_observed import build_reported_vs_observed
from backend.app.reports.teaching_skills import teaching_skill_summary
from backend.app.reports.trainer_aggregates import (
    build_trainer_report,
    generate_trainer_csv,
)
from backend.app.reports.training_gap import build_training_gap
from backend.app.reports.training_gap import enabled as training_gap_enabled
from backend.app.sessions.titles import move_title
from backend.app.sessions.training_rating import (
    TrainingRatingSummary,
    training_rating_summary,
)
from backend.app.web import visit_observation
from backend.app.web.cluster_pack_page import card_context, pack_enabled, print_context
from backend.app.web.ui_lang import register_ui_globals

logger = logging.getLogger("abhyas.web.trainer")

WEB_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = WEB_DIR / "templates"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
register_ui_globals(templates.env)

router = APIRouter(prefix="/trainer", tags=["Trainer View (DIET/SCERT)"])


@router.get("", response_class=Response)
async def get_trainer_dashboard(
    request: Request,
    current_user: Annotated[AppUser, Depends(require_role("trainer"))],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    batch_id: Annotated[str | None, Query()] = None,
    move_id: Annotated[str | None, Query()] = None,
) -> Response:
    """Renders the Trainer View dashboard with n < 10 suppression (spec/09 §9.4)."""
    report = await build_trainer_report(
        session=db,
        user=current_user,
        selected_batch_id=batch_id,
        selected_move_id=move_id,
    )

    # Teachers' "rate the training" answers: own district, consenting teachers only, n<10 suppressed
    if current_user.district or current_user.role == "admin":
        ratings = await training_rating_summary(
            db,
            district=current_user.district,
            consenting_only=True,
            suppress_below=settings.AGGREGATION_SUPPRESSION_N,
        )
    else:
        ratings = TrainingRatingSummary(count=0, average=None)

    # Module progress: own district, consenting teachers, pilot and demo labelled, n<10 suppressed
    modules = await module_progress_summary(
        db,
        district=current_user.district if current_user.role != "admin" else None,
        suppress_below=settings.AGGREGATION_SUPPRESSION_N,
    )

    # "My class": what teachers said their classes struggle with; own district, consenting only,
    # nothing at all below n=10
    class_struggles = await class_struggle_summary(
        db,
        district=current_user.district if current_user.role != "admin" else None,
        suppress_below=settings.AGGREGATION_SUPPRESSION_N,
    )

    teaching_skills = await teaching_skill_summary(
        db,
        district=current_user.district if current_user.role != "admin" else None,
        suppress_below=settings.AGGREGATION_SUPPRESSION_N,
    )

    # Cluster meeting pack (flag CLUSTER_PACK_ENABLED, on in demo mode): own district, consenting only
    pack = (
        await build_cluster_pack(
            db, district=current_user.district if current_user.role != "admin" else None
        )
        if pack_enabled()
        else None
    )

    # Reported vs observed (flag OBSERVATION_ENABLED, on in demo mode): own district, consenting only
    rvo = (
        await build_reported_vs_observed(
            db, district=current_user.district if current_user.role != "admin" else None
        )
        if visit_observation.enabled()
        else None
    )

    # "Where training is not landing" (flag TRAINING_GAP_ENABLED, on in demo mode)
    training_gap = (
        await build_training_gap(
            db, district=current_user.district if current_user.role != "admin" else None
        )
        if training_gap_enabled()
        else None
    )
    gap_titles = (
        {r.move_id: move_title(r.move_id) for r in training_gap.rows} if training_gap else {}
    )

    csrf_token = generate_csrf_token()
    demo_banner_text = get_message("ui_demo_banner")

    resp = templates.TemplateResponse(
        request=request,
        name="trainer.html",
        context={
            "request": request,
            "report": report,
            "ratings": ratings,
            "modules": modules,
            "class_struggles": class_struggles,
            "teaching_skills": teaching_skills,
            "rvo": rvo,
            "training_gap": training_gap,
            "gap_titles": gap_titles,
            "suppression_n": settings.AGGREGATION_SUPPRESSION_N,
            "suppression_message": SUPPRESSION_MESSAGE,
            "user": current_user,
            "csrf_token": csrf_token,
            "get_message": get_message,
            "demo_mode": current_user.is_demo_account,
            "demo_banner_text": demo_banner_text,
            **card_context(pack, "/trainer/cluster-pack/print"),
        },
    )
    set_csrf_cookie(resp, csrf_token)
    return resp


@router.get("/move/{move_id}", response_class=HTMLResponse)
async def get_trainer_move_card(
    request: Request,
    move_id: str,
    current_user: Annotated[AppUser, Depends(require_role("trainer"))],
) -> HTMLResponse:
    """A move card's key points with their handbook citations (linked from the training-gap table)."""
    if not training_gap_enabled():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    try:
        card = load_move_card(move_id)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from exc
    english = get_ui_lang() == "en"
    points = [
        {
            "text": (kp.text_en or kp.text_hi) if english else kp.text_hi,
            "cites": [c.label_hi() for c in citations(kp.source_chunk_ids)],
        }
        for kp in card.key_points
    ]
    return templates.TemplateResponse(
        request=request,
        name="trainer_move.html",
        context={
            "request": request,
            "title": move_title(move_id),
            "summary": "" if english else card.summary_hi,
            "points": points,
            "get_message": get_message,
        },
    )


@router.get("/cluster-pack/print", response_class=HTMLResponse)
async def get_cluster_pack_print(
    request: Request,
    current_user: Annotated[AppUser, Depends(require_role("trainer"))],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> HTMLResponse:
    """The one-screen, printable meeting agenda (server-rendered, no JavaScript)."""
    if not pack_enabled():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    pack = await build_cluster_pack(
        db, district=current_user.district if current_user.role != "admin" else None
    )
    resp = templates.TemplateResponse(
        request=request,
        name="cluster_pack_print.html",
        context={"request": request, **print_context(pack, "ui_pack_scope_trainer")},
    )
    resp.headers["Cache-Control"] = "no-store"
    return resp


@router.get("/export.csv")
async def export_trainer_csv(
    current_user: Annotated[AppUser, Depends(require_role("trainer"))],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    batch_id: Annotated[str | None, Query()] = None,
    move_id: Annotated[str | None, Query()] = None,
) -> Response:
    """Exports batch-level aggregates as CSV with identical n < 10 suppression (spec/09 §9.4)."""
    report = await build_trainer_report(
        session=db,
        user=current_user,
        selected_batch_id=batch_id,
        selected_move_id=move_id,
    )
    csv_content = generate_trainer_csv(report)
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="trainer_aggregates.csv"',
            "Cache-Control": "no-store",
        },
    )
