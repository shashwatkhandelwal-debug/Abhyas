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

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.access import SUPPRESSION_MESSAGE
from backend.app.auth.csrf import generate_csrf_token, set_csrf_cookie
from backend.app.auth.guards import require_role
from backend.app.config import settings
from backend.app.core.messages import get_message
from backend.app.db.models import AppUser
from backend.app.db.session import get_db_session
from backend.app.reports.trainer_aggregates import (
    build_trainer_report,
    generate_trainer_csv,
)
from backend.app.sessions.training_rating import (
    TrainingRatingSummary,
    training_rating_summary,
)
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

    csrf_token = generate_csrf_token()
    demo_banner_text = get_message("ui_demo_banner")

    resp = templates.TemplateResponse(
        request=request,
        name="trainer.html",
        context={
            "request": request,
            "report": report,
            "ratings": ratings,
            "suppression_message": SUPPRESSION_MESSAGE,
            "user": current_user,
            "csrf_token": csrf_token,
            "get_message": get_message,
            "demo_mode": current_user.is_demo_account,
            "demo_banner_text": demo_banner_text,
        },
    )
    set_csrf_cookie(resp, csrf_token)
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
