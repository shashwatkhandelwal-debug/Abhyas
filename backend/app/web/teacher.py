"""Teacher Chat PWA router and static asset mounting (spec/09 §9.2).

Routes:
- GET /teacher          Teacher WhatsApp-like chat interface
- GET /chat             Teacher WhatsApp-like chat interface (alias)
- GET /teacher/progress Teacher progress page with evidence ladder and rubric score history
- POST /teacher/consent Update consent settings and record ConsentLog
- GET /teacher/delete   Confirmation page for account and data deletion
- POST /teacher/delete  Purge all teacher data and log out
- GET /manifest.json    Web App Manifest
- GET /sw.js            Service worker (Service-Worker-Allowed: /)
- GET /offline.html     Offline fallback page with cached checklist & history
"""

import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import yaml
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.access import scope_teachers_query
from backend.app.auth.csrf import (
    CSRF_COOKIE_NAME,
    generate_csrf_token,
    set_csrf_cookie,
    verify_csrf_token,
)
from backend.app.auth.guards import get_current_user, require_role
from backend.app.auth.session import clear_session_cookie
from backend.app.channels.web import WebChannel
from backend.app.class_profile.focus import enabled as focus_enabled
from backend.app.class_profile.followup import enabled as followup_enabled
from backend.app.class_profile.skills import skill_progress
from backend.app.class_profile.views import views_for
from backend.app.class_profile.visit_note import enabled as visit_note_enabled
from backend.app.config import settings, v2_enabled
from backend.app.content_models import MoveCard
from backend.app.core.messages import (
    get_message,
    get_ui_lang,
    localize_buttons,
    texts_for_lang,
)
from backend.app.db.models import (
    AdoptionEvidence,
    AppUser,
    ConsentLog,
    ExplainScore,
    Message,
    MovePath,
    RehearsalScore,
    Scene,
    SessionState,
    Teacher,
)
from backend.app.db.session import get_db_session
from backend.app.handbook.questions import chip_views, question_by_id
from backend.app.privacy.purge import purge_teacher_data
from backend.app.rehearsal.header import scene_header
from backend.app.sessions.modules import MODULE_STEPS, module_ids, module_views
from backend.app.sessions.repository import SessionRepository
from backend.app.sessions.service import SessionService
from backend.app.sessions.state_machine import OnboardingStateEnum
from backend.app.web.assets import STATIC_DIR, sw_build_version
from backend.app.web.chat_api import get_teacher_for_user
from backend.app.web.chat_view import load_chat_view
from backend.app.web.demo_samples import demo_sample_audio
from backend.app.web.ui_lang import register_ui_globals, speaker_label

IST = ZoneInfo("Asia/Kolkata")
logger = logging.getLogger("abhyas.web.teacher")

WEB_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = WEB_DIR / "templates"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
register_ui_globals(templates.env)

_IST = ZoneInfo("Asia/Kolkata")  # no-JS fallback for the bubble clock (JS shows the local time)

router = APIRouter(tags=["Teacher Web PWA"])

# Each shared demo teacher login says what its demo shows (fix3 K5).
_DEMO_BANNER_KEYS = {
    "teacher.demo1": "ui_demo_banner_demo1",
    "teacher.demo2": "ui_demo_banner_demo2",
    "teacher.demo3": "ui_demo_banner_demo3",
}


def _demo_banner_text(current_user: AppUser, step: int | None = None) -> str:
    """Shared demo logins are reset on login/logout; other demo views only show synthetic data.

    The instruction in a demo login's banner is only true up to a step (config); on pages that do
    not know the step (`step=None`) and past that step the banner is the plain demo line.
    """
    if current_user.is_demo and current_user.role == "teacher":
        last = settings.DEMO_BANNER_LAST_STEP.get(current_user.username, -1)
        if step is not None and step <= last:
            return get_message(_DEMO_BANNER_KEYS[current_user.username])
        return get_message("ui_demo_account_banner")
    return get_message("ui_demo_banner")


@router.get("/chat", response_class=HTMLResponse)
@router.get("/teacher", response_class=HTMLResponse)
async def teacher_chat_page(
    request: Request,
    current_user: Annotated[AppUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> Response:
    """Renders WhatsApp-like teacher chat PWA interface (§9.2)."""
    # Guard: only teacher or admin can view teacher chat (§9.7)
    if current_user.role not in ("teacher", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Teacher or admin role required",
        )

    teacher = await get_teacher_for_user(current_user, db, request=request)

    # First visit: the one-time Start here screen (never in the way of a link that asks something,
    # and ?s=1 always opens the chat, so a failed save can never loop)
    if (
        teacher.start_seen_at is None
        and (current_user.is_demo or teacher.consent_service)
        and not request.query_params.get("s")
        and not request.query_params.get("ask")
    ):
        return RedirectResponse(url="/teacher/start", status_code=status.HTTP_303_SEE_OTHER)

    # The follow-up that is due ("How did yesterday's practice go?", flag FOLLOWUP_ENABLED) is
    # offered once, as a message in the thread, before the thread is read below
    if followup_enabled() and teacher.onboarding_state == OnboardingStateEnum.READY.value:
        try:
            offer = await SessionService(db_session=db).offer_followup(teacher.id)
            if offer:
                await WebChannel().send(teacher, offer, session=db)
                await db.commit()
        except Exception:
            logger.warning("follow-up offer failed", exc_info=True)

    # What her ARP saw in her class (flag OBSERVATION_TO_TEACHER_ENABLED): a note, never a rating
    if visit_note_enabled() and teacher.onboarding_state == OnboardingStateEnum.READY.value:
        try:
            note_msgs = await SessionService(db_session=db).offer_visit_note(teacher.id)
            if note_msgs:
                await WebChannel().send(teacher, note_msgs, session=db)
                await db.commit()
        except Exception:
            logger.warning("visit note failed", exc_info=True)

    # "Today's focus" (flag FOCUS_CARD_ENABLED): the opt-in question or one cited tip, after the
    # follow-up above and before the thread is read, so it sits in order in the thread
    if focus_enabled() and teacher.onboarding_state == OnboardingStateEnum.READY.value:
        try:
            focus_msgs = await SessionService(db_session=db).offer_focus(teacher.id)
            if focus_msgs:
                await WebChannel().send(teacher, focus_msgs, session=db)
                await db.commit()
        except Exception:
            logger.warning("focus card failed", exc_info=True)

    # CSRF cookie resolution for client scripts and forms
    csrf_token = request.cookies.get(CSRF_COOKIE_NAME)
    token_to_set: str | None = None
    if not csrf_token:
        csrf_token = generate_csrf_token()
        token_to_set = csrf_token

    # Fetch last 50 messages for instant server-rendered thread
    stmt = (
        select(Message)
        .where(Message.teacher_id == teacher.id)
        .order_by(Message.created_at.asc())
        .limit(50)
    )
    result = await db.execute(stmt)
    db_messages = result.scalars().all()

    initial_messages = [
        {
            "id": str(m.id),
            "direction": m.direction,
            "kind": m.kind,
            "text": m.text,
            "speaker": m.speaker,
            "audio_ref": m.audio_ref,
            "buttons": localize_buttons(m.buttons, teacher.address_form),
            "citations": m.citations,
            "created_at": m.created_at.isoformat() if m.created_at else "",
            "time_str": (
                m.created_at.astimezone(_IST).strftime("%I:%M %p").lower()
                if m.created_at
                else get_message("ui_time_just_now")
            ),
        }
        for m in db_messages
    ]

    is_demo = bool(
        settings.DEMO_MODE
        or settings.STT_PROVIDER == "mock"
        or current_user.is_demo
        or request.query_params.get("demo") == "1"
    )

    # Fetch active scene for board problem (empty string when no scene)
    active_scene = None
    try:
        stmt_scene = (
            select(Scene)
            .where(Scene.teacher_id == teacher.id, Scene.status == "active")
            .order_by(Scene.started_at.desc())
            .limit(1)
        )
        scene_res = (await db.execute(stmt_scene)).scalar_one_or_none()
        if isinstance(scene_res, Scene):
            active_scene = scene_res
    except Exception:
        active_scene = None

    header: dict[str, Any] | None = None
    if active_scene is not None and active_scene.engine_state:
        try:
            header = scene_header(active_scene.engine_state)
        except ValueError:
            header = None
    view = await load_chat_view(
        db, teacher, header, with_samples=is_demo, sample_audio=demo_sample_audio()
    )
    header = header or view.get("scene_preview")

    demo_banner_text = _demo_banner_text(current_user, int(view.get("step") or 0))
    # "Ask the handbook": four questions per teacher per day, in a scene too (a question there is
    # answered and the teacher is told how to go back); a link from the modules page
    # (?ask=hb03) sends that question once the chat opens.
    handbook_chips = chip_views(teacher.id, datetime.now(IST).date(), get_ui_lang())
    autosend = ""
    asked = question_by_id(request.query_params.get("ask", ""))
    if asked is not None:
        autosend = asked.send_text()

    response = templates.TemplateResponse(
        request=request,
        name="teacher.html",
        context={
            "request": request,
            "csrf_token": csrf_token,
            "teacher_name": (
                teacher.name or current_user.display_name or get_message("ui_default_teacher_name")
            ),
            "view": view,
            "scene_header": header,
            "lite_mode": teacher.lite_mode,
            "consent_share_scores": bool(teacher.consent_share_scores),
            "demo_mode": is_demo,
            "demo_banner_text": demo_banner_text,
            "demo_banner_last_step": settings.DEMO_BANNER_LAST_STEP.get(current_user.username, -1),
            "handbook_chips": handbook_chips,
            "handbook_autosend": autosend,
            "handbook_prefix": settings.HANDBOOK_ASK_PREFIX,
            "initial_messages": initial_messages,
            "address_form": teacher.address_form,
            # "After class: how did it go?" chip: onboarded (flag, ON in demo); in a scene it pauses it
            "checkin_entry": bool(
                v2_enabled(settings.CLASS_CHECKIN_ENABLED)
                and teacher.onboarding_state == OnboardingStateEnum.READY.value
            ),
            "level_entry": bool(
                v2_enabled(settings.LEVEL_SORTER_ENABLED)
                and teacher.onboarding_state == OnboardingStateEnum.READY.value
            ),
            "ui_strings": chat_ui_strings(teacher.address_form),
            "rec_config": {
                "maxSec": settings.REC_MAX_SECONDS,
                "minSec": settings.REC_MIN_SECONDS,
                "holdMs": settings.REC_HOLD_MS,
            },
        },
    )
    if token_to_set:
        set_csrf_cookie(response, token_to_set)
    return response


def _load_available_moves() -> dict[str, MoveCard]:
    """Loads MoveCard objects from content/moves."""
    candidates = [
        Path("content/moves"),
        WEB_DIR.parents[1] / "content" / "moves",
    ]
    for c in candidates:
        if c.is_dir():
            moves: dict[str, MoveCard] = {}
            for p in c.glob("*.yaml"):
                try:
                    data = yaml.safe_load(p.read_text(encoding="utf-8"))
                    card = MoveCard.model_validate(data)
                    moves[card.id] = card
                except Exception as e:
                    logger.debug("Could not load move card from %s: %s", p, e)
            if moves:
                return moves
    return {}


def get_ladder_labels() -> list[tuple[int, str]]:
    """Returns evidence ladder level numbers and labels loaded from message catalog."""
    return [
        (1, get_message("ui_ladder_level_1")),
        (2, get_message("ui_ladder_level_2")),
        (3, get_message("ui_ladder_level_3")),
        (4, get_message("ui_ladder_level_4")),
        (5, get_message("ui_ladder_level_5")),
    ]


@router.get("/teacher/progress", response_class=HTMLResponse)
async def teacher_progress_page(
    request: Request,
    current_user: Annotated[AppUser, Depends(require_role("teacher"))],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> Response:
    """Renders teacher progress page with evidence ladder, rubric history, and consent toggles (spec/09 §9.2)."""
    teacher = await get_teacher_for_user(current_user, db, request=request)

    # Scoped query enforcement via auth.access.scope_teachers_query (§3.3)
    scoped_stmt = select(Teacher).where(Teacher.id == teacher.id)
    scoped_stmt = scope_teachers_query(scoped_stmt, current_user)
    scoped_teacher = (await db.execute(scoped_stmt)).scalar_one_or_none()
    if not scoped_teacher:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden",
        )

    csrf_token = request.cookies.get(CSRF_COOKIE_NAME)
    token_to_set: str | None = None
    if not csrf_token:
        csrf_token = generate_csrf_token()
        token_to_set = csrf_token

    is_demo = bool(
        settings.DEMO_MODE
        or settings.STT_PROVIDER == "mock"
        or current_user.is_demo
        or teacher.is_demo
        or request.query_params.get("demo") == "1"
    )
    is_saved = request.query_params.get("saved") == "1"

    all_moves = _load_available_moves()

    # Discover active moves or move paths for this teacher
    stmt_mp = (
        select(MovePath).where(MovePath.teacher_id == teacher.id).order_by(MovePath.position.asc())
    )
    move_paths = (await db.execute(stmt_mp)).scalars().all()
    move_ids: list[str] = [mp.move_id for mp in move_paths if mp.move_id]

    stmt_ss = (
        select(SessionState)
        .where(SessionState.teacher_id == teacher.id)
        .order_by(SessionState.updated_at.desc())
    )
    for ss in (await db.execute(stmt_ss)).scalars().all():
        if ss.move_id and ss.move_id not in move_ids:
            move_ids.append(ss.move_id)

    stmt_ae_ids = (
        select(AdoptionEvidence.move_id).where(AdoptionEvidence.teacher_id == teacher.id).distinct()
    )
    for mid in (await db.execute(stmt_ae_ids)).scalars().all():
        if mid and mid not in move_ids:
            move_ids.append(mid)

    stmt_rs_ids = (
        select(RehearsalScore.move_id).where(RehearsalScore.teacher_id == teacher.id).distinct()
    )
    for rs_mid in (await db.execute(stmt_rs_ids)).scalars().all():
        if rs_mid and rs_mid not in move_ids:
            move_ids.append(rs_mid)

    if not move_ids:
        if "NUM_SUB_REGROUP_BUNDLES" in all_moves:
            move_ids = ["NUM_SUB_REGROUP_BUNDLES"]
        elif all_moves:
            move_ids = [next(iter(all_moves.keys()))]
        else:
            move_ids = ["NUM_SUB_REGROUP_BUNDLES"]

    move_cards: list[dict[str, Any]] = []
    all_scored: list[tuple[datetime, str, dict[str, Any]]] = []

    for m_id in move_ids:
        card = all_moves.get(m_id)
        title_hi = card.title_hi if card and card.title_hi else m_id

        # 1. Evidence ladder: 5 steps filled up to max level
        stmt_lvl = select(func.max(AdoptionEvidence.level)).where(
            AdoptionEvidence.teacher_id == teacher.id,
            AdoptionEvidence.move_id == m_id,
        )
        max_level = (await db.execute(stmt_lvl)).scalar() or 0
        ladder_steps = [
            {
                "level": lvl,
                "label": lbl,
                "filled": lvl <= max_level,
            }
            for lvl, lbl in get_ladder_labels()
        ]

        # 2. Rubric score history: inline CSS bars
        stmt_scores = (
            select(RehearsalScore)
            .where(
                RehearsalScore.teacher_id == teacher.id,
                RehearsalScore.move_id == m_id,
            )
            .order_by(RehearsalScore.created_at.asc())
        )
        rscores = (await db.execute(stmt_scores)).scalars().all()
        score_history: list[dict[str, Any]] = []
        for s_idx, rs in enumerate(rscores):
            all_scored.append(
                (
                    rs.created_at or datetime.min.replace(tzinfo=UTC),
                    m_id,
                    rs.scores if isinstance(rs.scores, dict) else {},
                )
            )
            num_vals: list[float] = []
            if isinstance(rs.scores, dict):
                for v in rs.scores.values():
                    if isinstance(v, (int, float)):
                        num_vals.append(float(v))
                    elif (
                        isinstance(v, dict)
                        and "score" in v
                        and isinstance(v["score"], (int, float))
                    ):
                        num_vals.append(float(v["score"]))
            avg_score = round(sum(num_vals) / len(num_vals), 1) if num_vals else 0.0
            pct = min(100, max(0, int((avg_score / 2.0) * 100)))
            score_history.append(
                {
                    "attempt": rs.attempt or (s_idx + 1),
                    "avg_score": avg_score,
                    "pct": pct,
                }
            )

        # 3. Explain-back key points covered
        stmt_explain = (
            select(ExplainScore)
            .where(
                ExplainScore.teacher_id == teacher.id,
                ExplainScore.move_id == m_id,
            )
            .order_by(ExplainScore.created_at.desc())
            .limit(1)
        )
        last_explain = (await db.execute(stmt_explain)).scalar_one_or_none()
        has_explain_score = last_explain is not None
        points_dict: dict[str, Any] = (
            last_explain.points if last_explain and isinstance(last_explain.points, dict) else {}
        )

        points_covered: list[dict[str, Any]] = []
        if card and card.key_points:
            for kp in card.key_points:
                status_val = points_dict.get(kp.id)
                is_cov = bool(
                    status_val in ("covered", True)
                    or str(status_val).lower() in ("covered", "true")
                )
                points_covered.append(
                    {
                        "id": kp.id,
                        "title_hi": kp.text_hi,
                        "covered": is_cov,
                    }
                )
        elif points_dict:
            for k_id, status_val in points_dict.items():
                is_cov = bool(
                    status_val in ("covered", True)
                    or str(status_val).lower() in ("covered", "true")
                )
                points_covered.append(
                    {
                        "id": k_id,
                        "title_hi": k_id,
                        "covered": is_cov,
                    }
                )

        move_cards.append(
            {
                "move_id": m_id,
                "title_hi": title_hi,
                "max_level": max_level,
                "ladder_steps": ladder_steps,
                "score_history": score_history,
                "has_explain_score": has_explain_score,
                "points_covered": points_covered,
            }
        )

    # What she chose to get better at: first and latest level on that rubric criterion
    skill_cards = skill_progress(
        [(m, sc) for _, m, sc in sorted(all_scored, key=lambda row: row[0])],
        [str(i) for i in teacher.teaching_skills or []],
    )

    demo_banner_text = _demo_banner_text(current_user)

    response = templates.TemplateResponse(
        request=request,
        name="progress.html",
        context={
            "request": request,
            "csrf_token": csrf_token,
            "teacher_name": (
                teacher.name or current_user.display_name or get_message("ui_default_teacher_name")
            ),
            "demo_mode": is_demo,
            "demo_banner_text": demo_banner_text,
            "is_saved": is_saved,
            "consent_share_scores": teacher.consent_share_scores,
            "consent_research": teacher.consent_research,
            "move_cards": move_cards,
            "skill_cards": skill_cards,
            "skill_min_scenes": settings.SKILL_PROGRESS_MIN_SCENES,
            "skill_max_level": settings.SKILL_LEVEL_MAX,
        },
    )
    if token_to_set:
        set_csrf_cookie(response, token_to_set)
    return response


@router.get("/teacher/modules", response_class=HTMLResponse)
async def teacher_modules_page(
    request: Request,
    current_user: Annotated[AppUser, Depends(require_role("teacher"))],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> Response:
    """Module picker: the three numeracy modules with step-by-step progress."""
    teacher = await get_teacher_for_user(current_user, db, request=request)
    rows = await SessionRepository(db).get_module_progress(teacher.id)
    csrf_token = request.cookies.get(CSRF_COOKIE_NAME)
    token_to_set: str | None = None
    if not csrf_token:
        csrf_token = generate_csrf_token()
        token_to_set = csrf_token
    response = templates.TemplateResponse(
        request=request,
        name="modules.html",
        context={
            "request": request,
            "csrf_token": csrf_token,
            "teacher_name": teacher.name or get_message("ui_default_teacher_name"),
            "modules": module_views(
                {r.module_id: r for r in rows}, [str(i) for i in teacher.class_struggles or []]
            ),
            "class_saved": views_for([str(i) for i in teacher.class_struggles or []]),
            "steps": MODULE_STEPS,
            "step_labels": {
                "learn": get_message("ui_modules_step_learn"),
                "diagnose": get_message("ui_modules_step_diagnose"),
                "practise": get_message("ui_modules_step_practise"),
                "check": get_message("ui_modules_step_check"),
            },
            "demo_mode": bool(current_user.is_demo or teacher.is_demo),
            "demo_banner_text": _demo_banner_text(current_user),
            "handbook_chips": chip_views(teacher.id, datetime.now(IST).date(), get_ui_lang()),
        },
    )
    if token_to_set:
        set_csrf_cookie(response, token_to_set)
    return response


@router.get("/teacher/start", response_class=HTMLResponse)
async def start_here_page(
    request: Request,
    current_user: Annotated[AppUser, Depends(require_role("teacher"))],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> Response:
    """The one-time Start here screen: what Abhyas is, what she does, what she gets, one button."""
    await get_teacher_for_user(current_user, db, request=request)
    csrf_token = request.cookies.get(CSRF_COOKIE_NAME)
    token_to_set: str | None = None
    if not csrf_token:
        csrf_token = generate_csrf_token()
        token_to_set = csrf_token
    response = templates.TemplateResponse(
        request=request, name="start.html", context={"request": request, "csrf_token": csrf_token}
    )
    if token_to_set:
        set_csrf_cookie(response, token_to_set)
    return response


@router.post("/teacher/start")
async def start_here_done(
    request: Request,
    current_user: Annotated[AppUser, Depends(require_role("teacher"))],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> Response:
    """The button or Skip: remember it and open the chat (at whatever step the account is on)."""
    await verify_csrf_token(request)
    teacher = await get_teacher_for_user(current_user, db, request=request)
    teacher.start_seen_at = datetime.now(UTC)
    try:
        await db.commit()
    except SQLAlchemyError:
        await db.rollback()
        logger.warning("could not save start_seen_at", exc_info=True)
    return RedirectResponse(url="/teacher?s=1", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/teacher/modules/{module_id}/start")
async def start_teacher_module(
    module_id: str,
    request: Request,
    current_user: Annotated[AppUser, Depends(require_role("teacher"))],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> Response:
    """Starts (or restarts) a module: the chat opens on its learn step."""
    await verify_csrf_token(request)
    if module_id not in module_ids():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown module")
    teacher = await get_teacher_for_user(current_user, db, request=request)
    service = SessionService(db_session=db)
    outbound = await service.start_module(teacher.id, module_id)
    await WebChannel().send(teacher, outbound, session=db)
    await db.commit()
    return RedirectResponse(url="/teacher", status_code=status.HTTP_303_SEE_OTHER)


DEFAULT_CONSENT_REDIRECT = "/teacher/progress?saved=1"


def safe_consent_redirect_url(url: str | None) -> str:
    """Restricts redirect_to to local paths starting with a single '/' (rejects '//', schemes, backslashes)."""
    if not url:
        return DEFAULT_CONSENT_REDIRECT
    url = url.strip()
    if not url.startswith("/") or url.startswith("//") or "\\" in url or "://" in url:
        return DEFAULT_CONSENT_REDIRECT
    parsed = urlsplit(url)
    if parsed.scheme or parsed.netloc:
        return DEFAULT_CONSENT_REDIRECT
    return url


@router.post("/teacher/consent")
async def update_teacher_consent(
    request: Request,
    current_user: Annotated[AppUser, Depends(require_role("teacher"))],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> Response:
    """Updates teacher consent preferences, creates ConsentLog entries, and redirects back (spec/09 §9.2)."""
    await verify_csrf_token(request)

    teacher = await get_teacher_for_user(current_user, db, request=request)

    scoped_stmt = select(Teacher).where(Teacher.id == teacher.id)
    scoped_stmt = scope_teachers_query(scoped_stmt, current_user)
    scoped_teacher = (await db.execute(scoped_stmt)).scalar_one_or_none()
    if not scoped_teacher:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden",
        )

    content_type = request.headers.get("content-type", "")
    redirect_to = DEFAULT_CONSENT_REDIRECT
    now = datetime.now(UTC)
    if "application/json" in content_type:
        body = await request.json()
        if "consent_share_scores" in body:
            teacher.consent_share_scores = bool(body["consent_share_scores"])
            db.add(
                ConsentLog(
                    id=uuid.uuid4(),
                    teacher_id=teacher.id,
                    field="consent_share_scores",
                    value=teacher.consent_share_scores,
                    channel="web",
                    created_at=now,
                )
            )
        if "consent_research" in body:
            teacher.consent_research = bool(body["consent_research"])
            db.add(
                ConsentLog(
                    id=uuid.uuid4(),
                    teacher_id=teacher.id,
                    field="consent_research",
                    value=teacher.consent_research,
                    channel="web",
                    created_at=now,
                )
            )
    else:
        form = await request.form()
        if "redirect_to" in form:
            redirect_to = safe_consent_redirect_url(str(form["redirect_to"]))
        else:
            redirect_to = DEFAULT_CONSENT_REDIRECT

        form_source = str(form.get("form_source", "")).lower()

        def _parse_checkbox(field_name: str) -> bool:
            values = form.getlist(field_name)
            return any(str(v).lower() in ("true", "1", "on", "yes") for v in values)

        # Detect which form posted:
        is_class_form = (
            form_source == "class"
            or redirect_to == "/teacher/class"
            or (
                "consent_share_scores" in form
                and "consent_research" not in form
                and "progress" not in redirect_to
            )
        )
        is_progress_form = (
            form_source == "progress" or "progress" in redirect_to or "consent_research" in form
        )

        if is_class_form:
            # Class form only controls consent_share_scores
            new_share = (
                _parse_checkbox("consent_share_scores") if "consent_share_scores" in form else False
            )
            teacher.consent_share_scores = new_share
            db.add(
                ConsentLog(
                    id=uuid.uuid4(),
                    teacher_id=teacher.id,
                    field="consent_share_scores",
                    value=new_share,
                    channel="web",
                    created_at=now,
                )
            )
        elif is_progress_form:
            # Progress form controls both consent_share_scores and consent_research
            new_share = (
                _parse_checkbox("consent_share_scores") if "consent_share_scores" in form else False
            )
            teacher.consent_share_scores = new_share
            db.add(
                ConsentLog(
                    id=uuid.uuid4(),
                    teacher_id=teacher.id,
                    field="consent_share_scores",
                    value=new_share,
                    channel="web",
                    created_at=now,
                )
            )

            new_research = (
                _parse_checkbox("consent_research") if "consent_research" in form else False
            )
            teacher.consent_research = new_research
            db.add(
                ConsentLog(
                    id=uuid.uuid4(),
                    teacher_id=teacher.id,
                    field="consent_research",
                    value=new_research,
                    channel="web",
                    created_at=now,
                )
            )
        else:
            if "consent_share_scores" in form:
                new_share = _parse_checkbox("consent_share_scores")
                teacher.consent_share_scores = new_share
                db.add(
                    ConsentLog(
                        id=uuid.uuid4(),
                        teacher_id=teacher.id,
                        field="consent_share_scores",
                        value=new_share,
                        channel="web",
                        created_at=now,
                    )
                )
            if "consent_research" in form:
                new_research = _parse_checkbox("consent_research")
                teacher.consent_research = new_research
                db.add(
                    ConsentLog(
                        id=uuid.uuid4(),
                        teacher_id=teacher.id,
                        field="consent_research",
                        value=new_research,
                        channel="web",
                        created_at=now,
                    )
                )

    await db.commit()

    accept = request.headers.get("accept", "")
    if "application/json" in accept and "text/html" not in accept:
        return JSONResponse(
            content={
                "ok": True,
                "consent_share_scores": teacher.consent_share_scores,
                "consent_research": teacher.consent_research,
            }
        )

    return RedirectResponse(
        url=redirect_to,
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/teacher/delete", response_class=HTMLResponse)
async def get_delete_confirm_page(
    request: Request,
    current_user: Annotated[AppUser, Depends(require_role("teacher"))],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> Response:
    """Renders data and account deletion confirmation dialog page (spec/09 §9.2)."""
    teacher = await get_teacher_for_user(current_user, db, request=request)

    scoped_stmt = select(Teacher).where(Teacher.id == teacher.id)
    scoped_stmt = scope_teachers_query(scoped_stmt, current_user)
    scoped_teacher = (await db.execute(scoped_stmt)).scalar_one_or_none()
    if not scoped_teacher:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden",
        )

    csrf_token = request.cookies.get(CSRF_COOKIE_NAME)
    token_to_set: str | None = None
    if not csrf_token:
        csrf_token = generate_csrf_token()
        token_to_set = csrf_token

    response = templates.TemplateResponse(
        request=request,
        name="delete.html",
        context={
            "request": request,
            "csrf_token": csrf_token,
            "address_form": teacher.address_form,
            "teacher_name": (
                teacher.name or current_user.display_name or get_message("ui_default_teacher_name")
            ),
        },
    )
    if token_to_set:
        set_csrf_cookie(response, token_to_set)
    return response


@router.post("/teacher/delete")
async def delete_teacher_account_data(
    request: Request,
    current_user: Annotated[AppUser, Depends(require_role("teacher"))],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> Response:
    """Purges all teacher data, clears session cookie, and redirects to /login (spec/08, spec/09 §9.2)."""
    await verify_csrf_token(request)

    teacher = await get_teacher_for_user(current_user, db, request=request)

    scoped_stmt = select(Teacher).where(Teacher.id == teacher.id)
    scoped_stmt = scope_teachers_query(scoped_stmt, current_user)
    scoped_teacher = (await db.execute(scoped_stmt)).scalar_one_or_none()
    if not scoped_teacher:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden",
        )

    teacher_id = teacher.id
    from backend.app.db.seed import DEMO_TEACHER_LOGINS, reset_demo_teacher

    if current_user.username in DEMO_TEACHER_LOGINS:
        # A shared demo login must survive: "delete" restores its seeded state (like logout does).
        await reset_demo_teacher(db, current_user.username)
    else:
        await purge_teacher_data(db, teacher_id)
    await db.commit()

    accept = request.headers.get("accept", "")
    if "application/json" in accept and "text/html" not in accept:
        json_resp = JSONResponse(content={"ok": True, "redirect": "/login"})
        clear_session_cookie(json_resp)
        return json_resp

    redir_resp = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    clear_session_cookie(redir_resp)
    return redir_resp


@router.get("/manifest.json")
async def get_manifest() -> FileResponse:
    """Serves PWA manifest with Devanagari app metadata (§9.2)."""
    manifest_file = STATIC_DIR / "manifest.json"
    return FileResponse(manifest_file, media_type="application/manifest+json")


# Catalog keys chat.js needs (served as JSON in the page; the JS holds no UI text of its own).
CHAT_UI_PREFIX = "ui_chat_"
CHAT_UI_PREFIXES = (CHAT_UI_PREFIX, "speaker_", "ui_time_")


def chat_ui_strings(address_form: str | None = "f") -> dict[str, str]:
    """Strings for chat.js in the language of the current request (Hindi unless switched).

    `speaker_model_teacher` follows her address form (neutral unless feminine), see `speaker_label`.
    """
    strings: dict[str, str] = {}
    for prefix in CHAT_UI_PREFIXES:
        strings.update(texts_for_lang(prefix))
    strings["speaker_model_teacher"] = speaker_label("model_teacher", address_form)
    return strings


@router.get("/sw.js")
async def get_service_worker() -> Response:
    """Serves the service worker with its cache name stamped with the build version (§9.2).

    The stamp makes the script's bytes change on every deploy, which is what makes browsers
    install the new worker; no-cache keeps the HTTP cache from hiding that.
    """
    body = (STATIC_DIR / "sw.js").read_text(encoding="utf-8")
    return Response(
        body.replace("__BUILD_VERSION__", sw_build_version()),
        media_type="application/javascript",
        headers={"Service-Worker-Allowed": "/", "Cache-Control": "no-cache"},
    )


@router.get("/offline.html", response_class=HTMLResponse)
async def get_offline_page(request: Request) -> Response:
    """Serves the offline fallback page (§9.2); it carries both languages (the SW caches one copy)."""
    return templates.TemplateResponse(request=request, name="offline.html", context={})


@router.get("/waking", response_class=HTMLResponse)
async def get_waking_page(request: Request) -> Response:
    """Cold-start page: the service worker serves it when the hosting answers 502/503/504."""
    return templates.TemplateResponse(request=request, name="waking.html", context={})
