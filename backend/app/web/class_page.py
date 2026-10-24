"""The "My class" page: pick or describe where the class struggles (works without JavaScript).

Routes (teacher role):
- GET  /teacher/class            current choice, chips, a text box, "say it by voice"
- POST /teacher/class/start      open the chat on the "where is your class struggling?" question
- POST /teacher/class/describe   her words -> what we understood (shown to confirm, nothing saved)
- POST /teacher/class/save       save the confirmed or ticked ids (closed list, at most 3, ordered)
- POST /teacher/class/clear      remove her choice
- POST /teacher/class/skills/save   save what she wants to get better at (closed list, at most 2)
- POST /teacher/class/skills/clear  remove that choice
- POST /teacher/class/skills/start  open the chat on the question, to answer by voice or text

Chips and typed words go through the same `resolve_struggles` as the chat; saving filters every id
through the closed library.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from backend.app.auth.csrf import (
    CSRF_COOKIE_NAME,
    generate_csrf_token,
    set_csrf_cookie,
    verify_csrf_token,
)
from backend.app.auth.guards import require_role
from backend.app.channels.web import WebChannel
from backend.app.class_profile.flow import clean_ids, resolve_struggles
from backend.app.class_profile.library import load_library
from backend.app.class_profile.skills import clean_skill_ids, load_skills, skill_views
from backend.app.class_profile.views import StruggleView, chip_views, views_for
from backend.app.config import settings
from backend.app.core.messages import get_message
from backend.app.db.models import AppUser
from backend.app.db.session import get_db_session
from backend.app.sessions.service import SessionService
from backend.app.web.chat_api import get_teacher_for_user
from backend.app.web.ui_lang import register_ui_globals

logger = logging.getLogger("abhyas.web.class_page")

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
register_ui_globals(templates.env)

router = APIRouter(tags=["My class"])


def _order_from_form(form_ids: list[str], order_field: str) -> list[str]:
    """Ticked ids in the order she ticked them (the script fills `order`); library order if absent."""
    lib = load_library()
    ticked = [i for i in form_ids if i in set(lib.ids())]
    ordered = [i for i in order_field.split(",") if i in ticked]
    rest = [i for i in lib.ids() if i in ticked and i not in ordered]
    return clean_ids(ordered + rest, lib)


async def _render(
    request: Request,
    db: AsyncSession,
    current_user: AppUser,
    *,
    pending: list[StruggleView] | None = None,
    pending_ids: list[str] | None = None,
    notice: str = "",
    no_match: bool = False,
) -> Response:
    teacher = await get_teacher_for_user(current_user, db, request=request)
    csrf_token = request.cookies.get(CSRF_COOKIE_NAME)
    token_to_set: str | None = None
    if not csrf_token:
        csrf_token = generate_csrf_token()
        token_to_set = csrf_token
    saved_ids = [str(i) for i in teacher.class_struggles or []]
    lib = load_library()
    response = templates.TemplateResponse(
        request=request,
        name="class.html",
        context={
            "request": request,
            "csrf_token": csrf_token,
            "teacher_name": teacher.name or get_message("ui_default_teacher_name"),
            "saved": views_for(saved_ids, lib),
            "chips": chip_views(lib),
            "max_chosen": settings.STRUGGLE_MAX_CHOSEN,
            "pending": pending,
            "pending_ids": ",".join(pending_ids or []),
            "notice": notice,
            "no_match": no_match,
            "other_tip": lib.other.tip_hi,
            "skills_all": skill_views(load_skills().ids()),
            "skills_saved": skill_views([str(i) for i in teacher.teaching_skills or []]),
            "skills_saved_ids": [str(i) for i in teacher.teaching_skills or []],
            "skill_max": settings.TEACHING_SKILLS_MAX,
            "consent_share_scores": bool(teacher.consent_share_scores),
            "demo_mode": bool(current_user.is_demo or teacher.is_demo),
            "demo_banner_text": get_message("ui_demo_banner"),
        },
    )
    if token_to_set:
        set_csrf_cookie(response, token_to_set)
    return response


@router.get("/teacher/class", response_class=HTMLResponse)
async def class_page(
    request: Request,
    current_user: Annotated[AppUser, Depends(require_role("teacher"))],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> Response:
    notice = ""
    if request.query_params.get("saved") == "1":
        notice = get_message("ui_class_saved")
    elif request.query_params.get("cleared") == "1":
        notice = get_message("ui_class_cleared")
    elif request.query_params.get("skills_saved") == "1":
        notice = get_message("ui_skills_notice_saved")
    elif request.query_params.get("skills_cleared") == "1":
        notice = get_message("ui_skills_notice_cleared")
    return await _render(request, db, current_user, notice=notice)


@router.post("/teacher/class/start")
async def class_start(
    request: Request,
    current_user: Annotated[AppUser, Depends(require_role("teacher"))],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> Response:
    """Open the chat on the question, so she can answer by voice or text."""
    await verify_csrf_token(request)
    teacher = await get_teacher_for_user(current_user, db, request=request)
    outbound = await SessionService(db_session=db).start_class_profile(teacher.id)
    await WebChannel().send(teacher, outbound, session=db)
    await db.commit()
    return RedirectResponse(url="/teacher", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/teacher/class/describe")
async def class_describe(
    request: Request,
    current_user: Annotated[AppUser, Depends(require_role("teacher"))],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> Response:
    await verify_csrf_token(request)
    form = await request.form()
    text = str(form.get("text") or "")
    resolution = await resolve_struggles(text)
    if not resolution.ids:
        return await _render(request, db, current_user, no_match=True)
    return await _render(
        request,
        db,
        current_user,
        pending=views_for(resolution.ids),
        pending_ids=resolution.ids,
    )


@router.post("/teacher/class/save")
async def class_save(
    request: Request,
    current_user: Annotated[AppUser, Depends(require_role("teacher"))],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> Response:
    await verify_csrf_token(request)
    form = await request.form()
    ids_field = str(form.get("ids") or "")
    if ids_field:  # confirmed from "what I understood"
        ids = clean_ids([i for i in ids_field.split(",") if i])
    else:  # ticked chips
        ids = _order_from_form(
            [str(v) for v in form.getlist("struggle")], str(form.get("order") or "")
        )
    teacher = await get_teacher_for_user(current_user, db, request=request)
    await SessionService(db_session=db).set_class_struggles(teacher.id, ids)
    await db.commit()
    return RedirectResponse(url="/teacher/class?saved=1", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/teacher/class/clear")
async def class_clear(
    request: Request,
    current_user: Annotated[AppUser, Depends(require_role("teacher"))],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> Response:
    await verify_csrf_token(request)
    teacher = await get_teacher_for_user(current_user, db, request=request)
    await SessionService(db_session=db).set_class_struggles(teacher.id, [])
    await db.commit()
    return RedirectResponse(url="/teacher/class?cleared=1", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/teacher/class/skills/save")
async def skills_save(
    request: Request,
    current_user: Annotated[AppUser, Depends(require_role("teacher"))],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> Response:
    await verify_csrf_token(request)
    form = await request.form()
    ids = clean_skill_ids([str(v) for v in form.getlist("skill")])
    teacher = await get_teacher_for_user(current_user, db, request=request)
    await SessionService(db_session=db).set_teaching_skills(teacher.id, ids)
    await db.commit()
    return RedirectResponse(
        url="/teacher/class?skills_saved=1", status_code=status.HTTP_303_SEE_OTHER
    )


@router.post("/teacher/class/skills/clear")
async def skills_clear(
    request: Request,
    current_user: Annotated[AppUser, Depends(require_role("teacher"))],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> Response:
    await verify_csrf_token(request)
    teacher = await get_teacher_for_user(current_user, db, request=request)
    await SessionService(db_session=db).set_teaching_skills(teacher.id, [])
    await db.commit()
    return RedirectResponse(
        url="/teacher/class?skills_cleared=1", status_code=status.HTTP_303_SEE_OTHER
    )


@router.post("/teacher/class/skills/start")
async def skills_start(
    request: Request,
    current_user: Annotated[AppUser, Depends(require_role("teacher"))],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> Response:
    """Open the chat on the question, so she can answer by voice or text."""
    await verify_csrf_token(request)
    teacher = await get_teacher_for_user(current_user, db, request=request)
    outbound = await SessionService(db_session=db).start_teaching_skills(teacher.id)
    await WebChannel().send(teacher, outbound, session=db)
    await db.commit()
    return RedirectResponse(url="/teacher", status_code=status.HTTP_303_SEE_OTHER)
