"""ARP Digest web router (spec/09 §9.3, T32).

Routes:
- GET  /arp              ARP weekly digest dashboard
- POST /arp/observation  Record classroom observation -> ARPObservation + AdoptionEvidence (L4)
- POST /arp/answer       Answer escalated question -> Question.answer_hi + resolve ReviewItem + outbound Message
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.access import can_access_teacher, can_view_teacher_scores
from backend.app.auth.csrf import (
    CSRF_COOKIE_NAME,
    generate_csrf_token,
    set_csrf_cookie,
    verify_csrf_token,
)
from backend.app.auth.guards import require_role
from backend.app.core.messages import get_message
from backend.app.db.models import (
    AdoptionEvidence,
    AppUser,
    ARPObservation,
    Message,
    Question,
    ReviewItem,
    Teacher,
)
from backend.app.db.session import get_db_session
from backend.app.reports.arp_digest import build_arp_digest

logger = logging.getLogger("abhyas.web.arp")

router = APIRouter(prefix="/arp", tags=["arp"])

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def get_arp_dashboard(
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    current_user: Annotated[AppUser, Depends(require_role("arp"))],
    week: str | None = None,
) -> HTMLResponse:
    """Renders the weekly ARP cluster digest dashboard (§9.3)."""
    selected_week: date | None = None
    if week:
        try:
            selected_week = datetime.strptime(week, "%Y-%m-%d").date()
        except ValueError:
            selected_week = None

    digest_data = await build_arp_digest(db, current_user, week_start=selected_week)

    csrf_token = request.cookies.get(CSRF_COOKIE_NAME)
    token_to_set: str | None = None
    if not csrf_token:
        csrf_token = generate_csrf_token()
        token_to_set = csrf_token
    demo_banner_text = get_message("ui_demo_banner") if current_user.is_demo_account else ""

    saved_param = request.query_params.get("saved")
    msg_param = request.query_params.get("msg")
    saved_msg = ""
    if saved_param == "1":
        if msg_param == "obs":
            saved_msg = get_message("ui_arp_observation_success")
        elif msg_param == "ans":
            saved_msg = get_message("ui_arp_answer_success")

    resp = templates.TemplateResponse(
        request=request,
        name="arp.html",
        context={
            "request": request,
            "digest": digest_data,
            "user": current_user,
            "csrf_token": csrf_token,
            "get_message": get_message,
            "demo_mode": current_user.is_demo_account,
            "demo_banner_text": demo_banner_text,
            "saved_msg": saved_msg,
        },
    )
    if token_to_set:
        set_csrf_cookie(resp, token_to_set)
    return resp


@router.post("/observation", response_class=RedirectResponse)
async def post_arp_observation(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    current_user: Annotated[AppUser, Depends(require_role("arp"))],
    teacher_id: Annotated[str, Form()],
    move_id: Annotated[str, Form()],
    notes: Annotated[str, Form()] = "",
    observed_on: Annotated[str, Form()] = "",
) -> RedirectResponse:
    """Records an in-person classroom observation (§9.3, §10.2).

    Creates:
    1. ARPObservation row with checklist & notes
    2. AdoptionEvidence level 4 (source: arp_observation)
    """
    await verify_csrf_token(request)

    try:
        t_uuid = uuid.UUID(teacher_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid teacher_id"
        ) from None

    teacher = await db.get(Teacher, t_uuid)
    if not teacher or not can_access_teacher(current_user, teacher):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Teacher not found")

    # Observations may only be recorded for consenting teachers in the ARP's cluster
    if not can_view_teacher_scores(current_user, teacher):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Teacher has not consented to score sharing",
        )

    # Parse checklist items from form
    form_data = await request.form()
    checklist: dict[str, bool] = {}
    for key, val in form_data.items():
        if key.startswith("check_"):
            item_name = key[len("check_") :]
            checklist[item_name] = str(val).lower() in ("true", "1", "on", "yes")

    obs_date = date.today()
    if observed_on:
        try:
            obs_date = datetime.strptime(observed_on, "%Y-%m-%d").date()
        except ValueError:
            obs_date = date.today()

    observation = ARPObservation(
        arp_user_id=current_user.id,
        teacher_id=teacher.id,
        move_id=move_id or None,
        checklist=checklist,
        notes=notes.strip() or None,
        observed_on=obs_date,
    )
    db.add(observation)
    await db.flush()

    evidence = AdoptionEvidence(
        teacher_id=teacher.id,
        move_id=move_id or "UNKNOWN",
        level=4,
        source="arp_observation",
        detail={
            "observation_id": str(observation.id),
            "checklist": checklist,
            "notes": notes.strip(),
        },
        created_by=current_user.id,
    )
    db.add(evidence)
    await db.commit()

    logger.info(
        "Recorded ARP observation %s and evidence L4 for teacher %s by user %s",
        observation.id,
        teacher.id,
        current_user.id,
    )
    return RedirectResponse(url="/arp?saved=1&msg=obs", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/answer", response_class=RedirectResponse)
async def post_arp_answer(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    current_user: Annotated[AppUser, Depends(require_role("arp"))],
    question_id: Annotated[str, Form()],
    answer_hi: Annotated[str, Form()],
) -> RedirectResponse:
    """Answers an escalated teacher question (§8.4, §9.3).

    Actions:
    1. Sets Question.answer_hi and status 'arp_answered'
    2. Resolves corresponding ReviewItem (kind='question')
    3. Queues an outbound Message for the teacher
    """
    await verify_csrf_token(request)

    clean_answer = answer_hi.strip()
    if not clean_answer:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Answer text cannot be empty"
        )

    try:
        q_uuid = uuid.UUID(question_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid question_id"
        ) from None

    question = await db.get(Question, q_uuid)
    if not question:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question not found")

    teacher = await db.get(Teacher, question.teacher_id)
    if not teacher or not can_access_teacher(current_user, teacher):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Teacher not found in cluster"
        )

    if question.status != "escalated":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Question cannot be answered: status is '{question.status}', expected 'escalated'",
        )

    # Update question
    question.answer_hi = clean_answer
    question.status = "arp_answered"

    # Resolve ReviewItem
    stmt = select(ReviewItem).where(
        ReviewItem.kind == "question",
        ReviewItem.ref_id == str(question.id),
        ReviewItem.status == "open",
    )
    review_item = (await db.scalars(stmt)).first()
    now_utc = datetime.now(UTC)
    if review_item:
        review_item.status = "resolved"
        review_item.resolved_by = current_user.id
        review_item.resolved_at = now_utc
        review_item.resolution = {
            "answer_hi": clean_answer,
            "resolved_by_arp": str(current_user.id),
        }

    # Dispatch outbound message to teacher
    channel = teacher.preferred_channel or "web"
    header = get_message("ui_arp_answer_header")
    outbound_msg = Message(
        teacher_id=teacher.id,
        direction="out",
        channel=channel,
        channel_msg_id=f"arp-ans-{question.id}-{uuid.uuid4().hex[:6]}",
        kind="text",
        text=f"{header}\n\n{clean_answer}",
        speaker="arp",
        state_at="ASK",
    )
    db.add(outbound_msg)
    await db.commit()

    logger.info(
        "ARP %s answered question %s for teacher %s; review item resolved: %s",
        current_user.id,
        question.id,
        teacher.id,
        bool(review_item),
    )
    return RedirectResponse(url="/arp?saved=1&msg=ans", status_code=status.HTTP_303_SEE_OTHER)
