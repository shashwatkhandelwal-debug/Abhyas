"""Teacher Chat PWA router and static asset mounting (spec/09 §9.2).

Routes:
- GET /teacher          Teacher WhatsApp-like chat interface
- GET /teacher/progress Teacher progress page with evidence ladder and rubric score history
- POST /teacher/consent Update consent settings and record ConsentLog
- GET /teacher/delete   Confirmation page for account and data deletion
- POST /teacher/delete  Purge all teacher data and log out
- GET /manifest.json    Web App Manifest
- GET /sw.js            Service worker (Service-Worker-Allowed: /)
- GET /offline.html     Offline fallback page with cached checklist & history
"""

import json
import logging
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
from backend.app.config import settings
from backend.app.content_models import MoveCard
from backend.app.core.messages import get_message
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
from backend.app.web.chat_api import get_teacher_for_user

logger = logging.getLogger("abhyas.web.teacher")

WEB_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.globals["get_message"] = get_message

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
                    return data
            except Exception as e:
                logger.warning("Failed to load demo_chips.json from %s: %s", p, e)
                return []
    return []


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
            detail="यह पृष्ठ केवल शिक्षकों के लिए है (Teacher role required)",
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
            "time_str": m.created_at.astimezone(UTC).strftime("%H:%M") if m.created_at else "अभी",
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
        if state.get("board_problem"):
            board_problem = str(state["board_problem"])
        elif state.get("board_text"):
            board_problem = str(state["board_text"])
        elif state.get("board"):
            board_problem = str(state["board"])
        elif state.get("current_item_text"):
            board_problem = f"बोर्ड: {state['current_item_text']}"
        elif current_item := state.get("current_item"):
            if isinstance(current_item, dict):
                if current_item.get("text"):
                    board_problem = f"बोर्ड: {current_item['text']}"
                elif (
                    current_item.get("type") == "sub"
                    and "a" in current_item
                    and "b" in current_item
                ):
                    board_problem = f"बोर्ड: {current_item['a']} − {current_item['b']}"
                elif (
                    current_item.get("type") == "add"
                    and "a" in current_item
                    and "b" in current_item
                ):
                    board_problem = f"बोर्ड: {current_item['a']} + {current_item['b']}"
                elif current_item.get("word"):
                    board_problem = f"बोर्ड: {current_item['word']}"
            elif isinstance(current_item, str):
                board_problem = (
                    current_item if current_item.startswith("बोर्ड:") else f"बोर्ड: {current_item}"
                )

    demo_chips = load_demo_chips() if is_demo else []
    try:
        demo_banner_text = get_message("ui_demo_banner")
    except Exception:
        demo_banner_text = "डेमो डेटा — वास्तविक शिक्षक नहीं"

    response = templates.TemplateResponse(
        "teacher.html",
        {
            "request": request,
            "csrf_token": csrf_token,
            "teacher_name": teacher.name or current_user.display_name or "शिक्षिका",
            "move_title": "दो अंकों की हासिल वाली घटाव",
            "step_chip": "चरण 4/7 · अभ्यास",
            "board_problem": board_problem,
            "lite_mode": teacher.lite_mode,
            "demo_mode": is_demo,
            "demo_banner_text": demo_banner_text,
            "demo_chips": demo_chips,
            "initial_messages": initial_messages,
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


LADDER_LABELS = [
    (1, "अभ्यास किया"),
    (2, "स्वयं बताया"),
    (3, "साथी ने देखा"),
    (4, "ARP ने देखा"),
    (5, "बच्चों में सुधार"),
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
            detail="यह पृष्ठ देखने की अनुमति नहीं है (Access forbidden)",
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
            for lvl, lbl in LADDER_LABELS
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

    try:
        demo_banner_text = get_message("ui_demo_banner")
    except Exception:
        demo_banner_text = "डेमो डेटा — वास्तविक शिक्षक नहीं"

    response = templates.TemplateResponse(
        "progress.html",
        {
            "request": request,
            "csrf_token": csrf_token,
            "teacher_name": teacher.name or current_user.display_name or "शिक्षिका",
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
            detail="यह पृष्ठ देखने की अनुमति नहीं है (Access forbidden)",
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
            detail="यह पृष्ठ देखने की अनुमति नहीं है (Access forbidden)",
        )

    csrf_token = request.cookies.get(CSRF_COOKIE_NAME)
    token_to_set: str | None = None
    if not csrf_token:
        csrf_token = generate_csrf_token()
        token_to_set = csrf_token

    response = templates.TemplateResponse(
        "delete.html",
        {
            "request": request,
            "csrf_token": csrf_token,
            "teacher_name": teacher.name or current_user.display_name or "शिक्षिका",
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
            detail="यह पृष्ठ देखने की अनुमति नहीं है (Access forbidden)",
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


@router.get("/sw.js")
async def get_service_worker() -> FileResponse:
    """Serves service worker script with Service-Worker-Allowed root header (§9.2)."""
    sw_file = STATIC_DIR / "sw.js"
    return FileResponse(
        sw_file,
        media_type="application/javascript",
        headers={"Service-Worker-Allowed": "/"},
    )


@router.get("/offline.html", response_class=HTMLResponse)
async def get_offline_page() -> FileResponse:
    """Serves offline fallback page (§9.2)."""
    offline_file = STATIC_DIR / "offline.html"
    return FileResponse(offline_file, media_type="text/html")
