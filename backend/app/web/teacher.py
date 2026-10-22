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

import hashlib
import json
import logging
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

import yaml
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
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
from backend.app.config import settings
from backend.app.content_models import MoveCard
from backend.app.core.messages import get_message, texts_for_lang
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
from backend.app.privacy.purge import purge_teacher_data
from backend.app.rehearsal.header import scene_header
from backend.app.sessions.modules import MODULE_STEPS, module_ids, module_views
from backend.app.sessions.repository import SessionRepository
from backend.app.sessions.service import SessionService
from backend.app.web.chat_api import get_teacher_for_user
from backend.app.web.ui_lang import register_ui_globals

logger = logging.getLogger("abhyas.web.teacher")

WEB_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
register_ui_globals(templates.env)

router = APIRouter(tags=["Teacher Web PWA"])


def load_demo_chips() -> list[dict[str, Any]]:
    """Loads demo chips from eval/samples/demo_chips.json only when DEMO_MODE is True (§9.2)."""
    if not settings.DEMO_MODE:
        return []

    candidates = [
        Path("eval/samples/demo_chips.json"),
        WEB_DIR.parents[1] / "eval" / "samples" / "demo_chips.json",
    ]
    for p in candidates:
        if p.is_file():
            try:
                content = p.read_text(encoding="utf-8")
                data = json.loads(content)
                if isinstance(data, list):
                    from backend.app.speech.audio import is_wav_non_silent

                    audio_dir = p.parent / "audio"
                    for item in data:
                        if isinstance(item, dict):
                            sid = item.get("id")
                            wav_path = audio_dir / f"{sid}.wav" if sid else None
                            is_avail = bool(
                                wav_path and wav_path.is_file() and is_wav_non_silent(wav_path)
                            )
                            item["audio_available"] = is_avail
                            if not is_avail:
                                item["audio_url"] = None
                    return data
            except Exception as e:
                logger.warning("Failed to load demo_chips.json from %s: %s", p, e)
                return []
    return []


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
            "buttons": m.buttons,
            "citations": m.citations,
            "created_at": m.created_at.isoformat() if m.created_at else "",
            "time_str": (
                m.created_at.astimezone(UTC).strftime("%H:%M")
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

    board_problem = ""
    if active_scene and active_scene.engine_state:
        state = active_scene.engine_state
        board_prefix = get_message("ui_board_prefix")
        if state.get("board_problem"):
            board_problem = str(state["board_problem"])
        elif state.get("board_text"):
            board_problem = str(state["board_text"])
        elif state.get("board"):
            board_problem = str(state["board"])
        elif state.get("current_item_text"):
            board_problem = f"{board_prefix} {state['current_item_text']}"
        elif current_item := state.get("current_item"):
            if isinstance(current_item, dict):
                if current_item.get("text"):
                    board_problem = f"{board_prefix} {current_item['text']}"
                elif (
                    current_item.get("type") == "sub"
                    and "a" in current_item
                    and "b" in current_item
                ):
                    board_problem = f"{board_prefix} {current_item['a']} − {current_item['b']}"
                elif (
                    current_item.get("type") == "add"
                    and "a" in current_item
                    and "b" in current_item
                ):
                    board_problem = f"{board_prefix} {current_item['a']} + {current_item['b']}"
                elif current_item.get("word"):
                    board_problem = f"{board_prefix} {current_item['word']}"
            elif isinstance(current_item, str):
                board_problem = (
                    current_item
                    if current_item.startswith(board_prefix)
                    else f"{board_prefix} {current_item}"
                )

    header: dict[str, Any] | None = None
    if active_scene is not None and active_scene.engine_state:
        try:
            header = scene_header(active_scene.engine_state)
        except ValueError:
            header = None

    demo_chips = load_demo_chips() if is_demo else []
    demo_banner_text = get_message("ui_demo_banner")

    response = templates.TemplateResponse(
        request=request,
        name="teacher.html",
        context={
            "request": request,
            "csrf_token": csrf_token,
            "teacher_name": (
                teacher.name or current_user.display_name or get_message("ui_default_teacher_name")
            ),
            "move_title": get_message("ui_default_move_title"),
            "step_chip": get_message("ui_default_step_chip"),
            "board_problem": board_problem,
            "scene_header": header,
            "lite_mode": teacher.lite_mode,
            "demo_mode": is_demo,
            "demo_banner_text": demo_banner_text,
            "demo_chips": demo_chips,
            "initial_messages": initial_messages,
            "ui_strings": chat_ui_strings(),
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

    demo_banner_text = get_message("ui_demo_banner")

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
            "modules": module_views({r.module_id: r for r in rows}),
            "steps": MODULE_STEPS,
            "step_labels": {
                "learn": get_message("ui_modules_step_learn"),
                "diagnose": get_message("ui_modules_step_diagnose"),
                "practise": get_message("ui_modules_step_practise"),
                "check": get_message("ui_modules_step_check"),
            },
            "demo_mode": bool(current_user.is_demo or teacher.is_demo),
            "demo_banner_text": get_message("ui_demo_banner"),
        },
    )
    if token_to_set:
        set_csrf_cookie(response, token_to_set)
    return response


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
    if "application/json" in content_type:
        body = await request.json()
        new_share = bool(body.get("consent_share_scores", False))
        new_research = bool(body.get("consent_research", False))
    else:
        form = await request.form()
        new_share = form.get("consent_share_scores") in ("true", "1", "on", True)
        new_research = form.get("consent_research") in ("true", "1", "on", True)

    teacher.consent_share_scores = new_share
    teacher.consent_research = new_research

    now = datetime.now(UTC)
    log_share = ConsentLog(
        id=uuid.uuid4(),
        teacher_id=teacher.id,
        field="consent_share_scores",
        value=new_share,
        channel="web",
        created_at=now,
    )
    log_research = ConsentLog(
        id=uuid.uuid4(),
        teacher_id=teacher.id,
        field="consent_research",
        value=new_research,
        channel="web",
        created_at=now,
    )
    db.add(log_share)
    db.add(log_research)
    await db.commit()

    accept = request.headers.get("accept", "")
    if "application/json" in accept and "text/html" not in accept:
        return JSONResponse(
            content={
                "ok": True,
                "consent_share_scores": new_share,
                "consent_research": new_research,
            }
        )

    return RedirectResponse(
        url="/teacher/progress?saved=1",
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


def chat_ui_strings() -> dict[str, str]:
    """Strings for chat.js in the language of the current request (Hindi unless switched)."""
    strings: dict[str, str] = {}
    for prefix in CHAT_UI_PREFIXES:
        strings.update(texts_for_lang(prefix))
    return strings


_SW_VERSIONED_ASSETS = ("sw.js", "chat.js", "recorder.js", "app.css", "manifest.json")


def sw_build_version() -> str:
    """Cache-busting id: deploy SHA plus a digest of the shipped static files.

    The digest keeps the version moving when GIT_SHA is unset ("dev") or stale, so a changed
    chat.js can never be served from a cache named after an older build.
    """
    digest = hashlib.sha1(usedforsecurity=False)
    for name in _SW_VERSIONED_ASSETS:
        path = STATIC_DIR / name
        if path.is_file():
            digest.update(path.read_bytes())
    sha = re.sub(r"[^A-Za-z0-9]", "", settings.GIT_SHA)[:12] or "dev"
    return f"{sha}-{digest.hexdigest()[:8]}"


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
