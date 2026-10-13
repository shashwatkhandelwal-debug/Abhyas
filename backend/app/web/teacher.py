"""Teacher Chat PWA router and static asset mounting (spec/09 §9.2).

Routes:
- GET /teacher         Teacher WhatsApp-like chat interface
- GET /manifest.json   Web App Manifest
- GET /sw.js           Service worker (Service-Worker-Allowed: /)
- GET /offline.html    Offline fallback page with cached checklist & history
"""

import json
import logging
from datetime import UTC
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.csrf import (
    CSRF_COOKIE_NAME,
    generate_csrf_token,
    set_csrf_cookie,
)
from backend.app.auth.guards import get_current_user
from backend.app.config import settings
from backend.app.db.models import AppUser, Message, Scene
from backend.app.db.session import get_db_session
from backend.app.web.chat_api import get_teacher_for_user

logger = logging.getLogger("abhyas.web.teacher")

WEB_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

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
            "demo_chips": demo_chips,
            "initial_messages": initial_messages,
        },
    )
    if token_to_set:
        set_csrf_cookie(response, token_to_set)
    return response


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
