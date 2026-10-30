"""Coach review console router and API endpoints (spec/09 §9.5, T34).

Routes:
- GET  /review: Dashboard with queue tabs (low-confidence scores, questions mirror, guard failures, moves)
- GET  /review/items/{item_id}: Review item detail (transcript, acts, AI score, evidence quotes, correction form)
- POST /review/items/{item_id}/resolve: Save resolution, update review_item, save to calibration_label
- GET  /review/calibrate: Blind double-coding mode (transcript without AI scores)
- POST /review/calibrate: Save blind calibration score to calibration_label
- GET  /review/calibration.jsonl: Export calibration labels as JSON Lines
- GET  /review/moves/{move_id}: Move editor / review (key points, rubric, scenario, raw YAML)
- POST /review/moves/{move_id}/approve: Approve move (requires 2 distinct coaches)
- POST /review/moves/{move_id}/validate-yaml: Validate raw YAML against MoveCard schema
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

import yaml
from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.csrf import (
    CSRF_COOKIE_NAME,
    generate_csrf_token,
    set_csrf_cookie,
    verify_csrf_token,
)
from backend.app.auth.guards import require_role
from backend.app.config import settings
from backend.app.content_models import MoveCard
from backend.app.core.messages import get_message
from backend.app.db.models import (
    AppUser,
    CalibrationLabel,
    ContentRelease,
    ExplainScore,
    Move,
    Question,
    RehearsalScore,
    ReviewItem,
    Scene,
    Turn,
)
from backend.app.db.session import get_db_session
from backend.app.sessions.path import load_all_move_cards
from backend.app.web.ui_lang import register_ui_globals

logger = logging.getLogger("abhyas.web.review")

WEB_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = WEB_DIR / "templates"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
register_ui_globals(templates.env)

router = APIRouter(prefix="/review", tags=["Coach Review Console"])


def _is_valid_uuid(val: str | None) -> bool:
    if not val:
        return False
    try:
        uuid.UUID(str(val))
        return True
    except (ValueError, TypeError, AttributeError):
        return False


async def ensure_moves_in_db(session: AsyncSession) -> list[Move]:
    """Ensures ContentRelease and Move records exist in DB from seed YAMLs."""
    # 1. Ensure release exists
    rel = await session.get(ContentRelease, "rel-seed-v1")
    if not rel:
        rel = ContentRelease(id="rel-seed-v1", is_active=True, notes="Seed content release")
        session.add(rel)
        await session.flush()

    # 2. Check and sync moves
    cards = load_all_move_cards()
    moves: list[Move] = []
    for card in cards:
        stmt = select(Move).where(Move.id == card.id, Move.release_id == "rel-seed-v1")
        row = (await session.execute(stmt)).scalar_one_or_none()
        if not row:
            domain_val = card.domain.value if hasattr(card.domain, "value") else str(card.domain)
            row = Move(
                id=card.id,
                release_id="rel-seed-v1",
                domain=domain_val,
                title_hi=card.title_hi,
                sankul_month=card.sankul_month,
                status="in_review",
                payload=card.model_dump(),
                approvals=[],
            )
            session.add(row)
            await session.flush()
        moves.append(row)
    return moves


# ── Dashboard & Queue Tabs ───────────────────────────────────────────────


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def review_dashboard(
    request: Request,
    current_user: Annotated[AppUser, Depends(require_role("coach"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    tab: str = "scores",
    status_filter: str = "open",
) -> Response:
    """Renders the coach review console dashboard (§9.5)."""
    csrf_token = generate_csrf_token()

    # Tab counts for badges
    count_scores_stmt = select(func.count(ReviewItem.id)).where(
        ReviewItem.kind.in_(["rehearsal_score", "explain_score"]),
        ReviewItem.status == "open",
    )
    open_scores_count = (await session.execute(count_scores_stmt)).scalar() or 0

    count_questions_stmt = select(func.count(ReviewItem.id)).where(
        ReviewItem.kind == "question",
        ReviewItem.status == "open",
    )
    open_questions_count = (await session.execute(count_questions_stmt)).scalar() or 0

    count_guards_stmt = select(func.count(ReviewItem.id)).where(
        ReviewItem.kind == "guard_failure",
        ReviewItem.status == "open",
    )
    open_guards_count = (await session.execute(count_guards_stmt)).scalar() or 0

    # Moves sync
    db_moves = await ensure_moves_in_db(session)
    pending_moves_count = sum(1 for m in db_moves if m.status != "approved")

    # Fetch items for active tab
    items: list[dict[str, Any]] = []
    if tab == "scores":
        stmt_items = select(ReviewItem).where(
            ReviewItem.kind.in_(["rehearsal_score", "explain_score"])
        )
        if status_filter in ("open", "resolved"):
            stmt_items = stmt_items.where(ReviewItem.status == status_filter)
        stmt_items = stmt_items.order_by(ReviewItem.created_at.desc())
        raw_items = (await session.execute(stmt_items)).scalars().all()
        for ri in raw_items:
            items.append(
                {
                    "id": str(ri.id),
                    "kind": ri.kind,
                    "ref_id": ri.ref_id,
                    "reason": ri.reason or get_message("ui_review_reason_low_confidence"),
                    "status": ri.status,
                    "created_at": ri.created_at.strftime("%d %b %H:%M") if ri.created_at else "",
                    "resolution": ri.resolution,
                }
            )

    elif tab == "questions":
        stmt_q = select(ReviewItem).where(ReviewItem.kind == "question")
        if status_filter in ("open", "resolved"):
            stmt_q = stmt_q.where(ReviewItem.status == status_filter)
        stmt_q = stmt_q.order_by(ReviewItem.created_at.desc())
        raw_q = (await session.execute(stmt_q)).scalars().all()
        for ri in raw_q:
            items.append(
                {
                    "id": str(ri.id),
                    "kind": ri.kind,
                    "ref_id": ri.ref_id,
                    "reason": ri.reason or get_message("ui_review_reason_question_escalated"),
                    "status": ri.status,
                    "created_at": ri.created_at.strftime("%d %b %H:%M") if ri.created_at else "",
                    "resolution": ri.resolution,
                }
            )

    elif tab == "guards":
        stmt_g = select(ReviewItem).where(ReviewItem.kind == "guard_failure")
        if status_filter in ("open", "resolved"):
            stmt_g = stmt_g.where(ReviewItem.status == status_filter)
        stmt_g = stmt_g.order_by(ReviewItem.created_at.desc())
        raw_g = (await session.execute(stmt_g)).scalars().all()
        for ri in raw_g:
            items.append(
                {
                    "id": str(ri.id),
                    "kind": ri.kind,
                    "ref_id": ri.ref_id,
                    "reason": ri.reason or get_message("ui_review_reason_guard_failure"),
                    "status": ri.status,
                    "created_at": ri.created_at.strftime("%d %b %H:%M") if ri.created_at else "",
                    "resolution": ri.resolution,
                }
            )

    move_list_view: list[dict[str, Any]] = []
    for m in db_moves:
        approvals = m.approvals if isinstance(m.approvals, list) else []
        distinct_approvers = {
            a.get("user_id", a.get("username")) for a in approvals if isinstance(a, dict)
        }
        move_list_view.append(
            {
                "id": m.id,
                "title_hi": m.title_hi,
                "domain": m.domain,
                "status": m.status,
                "approvals_count": len(distinct_approvers),
                "approvals_required": settings.MOVE_APPROVALS_REQUIRED,
                "sankul_month": m.sankul_month or "-",
            }
        )

    response = templates.TemplateResponse(
        request=request,
        name="review.html",
        context={
            "request": request,
            "csrf_token": csrf_token,
            "user": current_user,
            "tab": tab,
            "status_filter": status_filter,
            "items": items,
            "moves": move_list_view,
            "open_scores_count": open_scores_count,
            "open_questions_count": open_questions_count,
            "open_guards_count": open_guards_count,
            "pending_moves_count": pending_moves_count,
            "success_msg": request.query_params.get("success"),
        },
    )
    set_csrf_cookie(response, csrf_token)
    return response


# ── Review Item Detail & Resolution ──────────────────────────────────────


@router.get("/items/{item_id}", response_class=HTMLResponse)
async def review_item_detail(
    request: Request,
    item_id: str,
    current_user: Annotated[AppUser, Depends(require_role("coach"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> Response:
    """Renders rehearsal transcript, act tags, AI scores & evidence quotes for review (§9.5)."""
    csrf_token = generate_csrf_token()

    if not _is_valid_uuid(item_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invalid item ID")

    item = await session.get(ReviewItem, uuid.UUID(item_id))
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review item not found")

    turns_view: list[dict[str, Any]] = []
    ai_score_view: dict[str, Any] | None = None
    criteria_view: list[dict[str, Any]] = []
    explain_view: dict[str, Any] | None = None
    question_view: dict[str, Any] | None = None
    guard_view: dict[str, Any] | None = None
    move_title = get_message("ui_review_default_move_title")

    if item.kind == "rehearsal_score" and _is_valid_uuid(item.ref_id):
        scene_uuid = uuid.UUID(item.ref_id)

        # 1. Turns with tags
        stmt_turns = select(Turn).where(Turn.scene_id == scene_uuid).order_by(Turn.idx)
        raw_turns = (await session.execute(stmt_turns)).scalars().all()
        for t in raw_turns:
            turns_view.append(
                {
                    "idx": t.idx,
                    "role": t.role,
                    "text": t.transcript or t.line_hi or "",
                    "acts": t.acts or [],
                    "speaker": (
                        get_message("ui_review_default_teacher")
                        if t.role == "teacher"
                        else (t.addressed_child or t.role.capitalize())
                    ),
                }
            )

        # 2. AI Score & Evidence quotes
        stmt_score = select(RehearsalScore).where(RehearsalScore.scene_id == scene_uuid)
        r_score = (await session.execute(stmt_score)).scalar_one_or_none()
        if r_score:
            ai_score_view = {
                "scores": r_score.scores,
                "evidence": r_score.evidence,
                "strength_hi": r_score.strength_hi,
                "change_hi": r_score.change_hi,
                "exact_words_hi": r_score.exact_words_hi,
                "confidence": r_score.confidence,
                "needs_review": r_score.needs_review,
            }
            if r_score.move_id:
                cards = [c for c in load_all_move_cards() if c.id == r_score.move_id]
                if cards:
                    move_title = cards[0].title_hi
                    rubric = cards[0].rubric
                    one_on_one_rubric = cards[0].rubric_one_on_one
                    if one_on_one_rubric is not None and set(r_score.scores) == {
                        c.id for c in one_on_one_rubric.criteria
                    }:
                        rubric = (
                            one_on_one_rubric  # a one-on-one scene was scored on its own rubric
                        )
                    for crit in rubric.criteria:
                        lvl_desc = (
                            ", ".join(f"{k}: {v}" for k, v in crit.levels.items())
                            if crit.levels
                            else ""
                        )
                        criteria_view.append(
                            {
                                "id": crit.id,
                                "title": crit.text_hi,
                                "desc": lvl_desc,
                                "ai_score": r_score.scores.get(crit.id),
                                "evidence": r_score.evidence.get(crit.id),
                            }
                        )

    elif item.kind == "explain_score" and _is_valid_uuid(item.ref_id):
        exp_uuid = uuid.UUID(item.ref_id)
        exp = await session.get(ExplainScore, exp_uuid)
        if exp:
            explain_view = {
                "transcript": exp.transcript,
                "points": exp.points,
                "misconceptions": exp.misconceptions or [],
                "confidence": exp.confidence,
                "needs_review": exp.needs_review,
            }

    elif item.kind == "question" and _is_valid_uuid(item.ref_id):
        q_uuid = uuid.UUID(item.ref_id)
        q = await session.get(Question, q_uuid)
        if q:
            question_view = {
                "text": q.text,
                "category": q.category,
                "status": q.status,
                "answer_hi": q.answer_hi,
                "confidence": q.confidence,
            }

    elif item.kind == "guard_failure":
        guard_view = {
            "reason": item.reason,
            "resolution": item.resolution,
        }

    response = templates.TemplateResponse(
        request=request,
        name="review_detail.html",
        context={
            "request": request,
            "csrf_token": csrf_token,
            "user": current_user,
            "item": item,
            "move_title": move_title,
            "turns": turns_view,
            "ai_score": ai_score_view,
            "criteria": criteria_view,
            "explain": explain_view,
            "question": question_view,
            "guard": guard_view,
        },
    )
    set_csrf_cookie(response, csrf_token)
    return response


@router.post("/items/{item_id}/resolve")
async def resolve_review_item(
    request: Request,
    item_id: str,
    current_user: Annotated[AppUser, Depends(require_role("coach"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    note: Annotated[str, Form()] = "",
) -> Response:
    """Saves coach resolution, updates review_item, and stores calibration label (§9.5)."""
    await verify_csrf_token(request)

    if not _is_valid_uuid(item_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invalid item ID")

    item = await session.get(ReviewItem, uuid.UUID(item_id))
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review item not found")

    form_data = await request.form()
    scores_dict: dict[str, int] = {}
    for k, v in form_data.items():
        if k.startswith("score_"):
            crit_name = k.replace("score_", "", 1)
            try:
                scores_dict[crit_name] = int(str(v))
            except (ValueError, TypeError):
                continue

    # Update ReviewItem
    item.status = "resolved"
    item.resolved_by = current_user.id
    item.resolved_at = datetime.now(UTC)
    item.resolution = {
        "scores": scores_dict,
        "note": note.strip(),
        "resolved_by_name": current_user.display_name or current_user.username,
    }

    # Create CalibrationLabel (blind=False)
    scene_id_val = (
        uuid.UUID(item.ref_id)
        if item.kind == "rehearsal_score" and _is_valid_uuid(item.ref_id)
        else None
    )
    exp_id_val = (
        uuid.UUID(item.ref_id)
        if item.kind == "explain_score" and _is_valid_uuid(item.ref_id)
        else None
    )

    calib = CalibrationLabel(
        scene_id=scene_id_val,
        explain_score_id=exp_id_val,
        coach_user_id=current_user.id,
        scores=scores_dict,
        note=note.strip() if note else None,
        blind=False,
    )
    session.add(calib)
    await session.commit()

    return RedirectResponse(
        url="/review?tab=scores&success=1",
        status_code=status.HTTP_303_SEE_OTHER,
    )


# ── Blind Calibration Mode ───────────────────────────────────────────────


@router.get("/calibrate", response_class=HTMLResponse)
async def blind_calibrate_view(
    request: Request,
    current_user: Annotated[AppUser, Depends(require_role("coach"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    scene_id: str | None = None,
) -> Response:
    """Shows rehearsal transcript WITHOUT AI scores for blind double-coding (§9.5)."""
    csrf_token = request.cookies.get(CSRF_COOKIE_NAME)
    token_to_set: str | None = None
    if not csrf_token:
        csrf_token = generate_csrf_token()
        token_to_set = csrf_token

    scene: Scene | None = None
    if scene_id and _is_valid_uuid(scene_id):
        scene = await session.get(Scene, uuid.UUID(scene_id))

    if not scene:
        # Pick randomly among ended scenes this coach has NOT yet labelled with blind=True
        subq = (
            select(CalibrationLabel.scene_id)
            .where(
                CalibrationLabel.coach_user_id == current_user.id,
                CalibrationLabel.blind.is_(True),
                CalibrationLabel.scene_id.is_not(None),
            )
            .scalar_subquery()
        )
        stmt_scenes = (
            select(Scene)
            .where(
                Scene.status == "ended",
                Scene.id.not_in(subq),
            )
            .order_by(func.random())
            .limit(1)
        )
        scene = (await session.execute(stmt_scenes)).scalar_one_or_none()

    turns_view: list[dict[str, Any]] = []
    criteria_view: list[dict[str, Any]] = []
    move_title = ""

    if scene and scene.move_id:
        cards = [c for c in load_all_move_cards() if c.id == scene.move_id]
        if cards and cards[0].rubric and cards[0].rubric.criteria:
            move_title = cards[0].title_hi
            for crit in cards[0].rubric.criteria:
                lvl_desc = (
                    ", ".join(f"{k}: {v}" for k, v in crit.levels.items()) if crit.levels else ""
                )
                criteria_view.append(
                    {
                        "id": crit.id,
                        "title": crit.text_hi,
                        "desc": lvl_desc,
                    }
                )

    if scene and criteria_view:
        stmt_turns = select(Turn).where(Turn.scene_id == scene.id).order_by(Turn.idx)
        raw_turns = (await session.execute(stmt_turns)).scalars().all()
        for t in raw_turns:
            turns_view.append(
                {
                    "idx": t.idx,
                    "role": t.role,
                    "text": t.transcript or t.line_hi or "",
                    "speaker": (
                        get_message("ui_review_default_teacher")
                        if t.role == "teacher"
                        else (t.addressed_child or t.role.capitalize())
                    ),
                }
            )
    else:
        # Scene has no valid move/rubric or no unlabelled scene exists: empty state
        scene = None
        criteria_view = []

    response = templates.TemplateResponse(
        request=request,
        name="review_calibrate.html",
        context={
            "request": request,
            "csrf_token": csrf_token,
            "user": current_user,
            "scene": scene,
            "move_title": move_title,
            "turns": turns_view,
            "criteria": criteria_view,
            "success": request.query_params.get("success"),
        },
    )
    if token_to_set:
        set_csrf_cookie(response, token_to_set)
    return response


@router.post("/calibrate")
async def save_blind_calibration(
    request: Request,
    current_user: Annotated[AppUser, Depends(require_role("coach"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    scene_id: Annotated[str, Form()],
    note: Annotated[str, Form()] = "",
) -> Response:
    """Stores blind double-coded scores into calibration_label (§9.5)."""
    await verify_csrf_token(request)

    if not _is_valid_uuid(scene_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid scene ID")

    scene_uuid = uuid.UUID(scene_id)
    scene = await session.get(Scene, scene_uuid)
    if not scene:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scene not found")

    # Enforce: scene must have a valid move with rubric criteria (no uncalibrated labels)
    if not scene.move_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Scene has no move associated",
        )
    cards = [c for c in load_all_move_cards() if c.id == scene.move_id]
    if not cards or not cards[0].rubric or not cards[0].rubric.criteria:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Move card or rubric criteria missing for scene",
        )

    # Enforce one blind label per (coach, scene)
    stmt_existing = select(CalibrationLabel).where(
        CalibrationLabel.scene_id == scene_uuid,
        CalibrationLabel.coach_user_id == current_user.id,
        CalibrationLabel.blind.is_(True),
    )
    existing = (await session.execute(stmt_existing)).scalars().first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A blind calibration label already exists for this coach and scene",
        )

    valid_crit_ids = {crit.id for crit in cards[0].rubric.criteria}

    form_data = await request.form()
    scores_dict: dict[str, int] = {}
    for k, v in form_data.items():
        if k.startswith("score_"):
            crit_name = k.replace("score_", "", 1)
            if crit_name not in valid_crit_ids:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Unknown rubric criterion '{crit_name}' for move {scene.move_id}",
                )
            try:
                score_val = int(str(v))
            except (ValueError, TypeError):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid score value for criterion '{crit_name}'",
                ) from None
            if score_val not in (0, 1, 2):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Score value {score_val} for criterion '{crit_name}' must be 0, 1, or 2",
                )
            scores_dict[crit_name] = score_val

    if not scores_dict:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one rubric score must be provided",
        )

    calib = CalibrationLabel(
        scene_id=scene_uuid,
        coach_user_id=current_user.id,
        scores=scores_dict,
        note=note.strip() if note else None,
        blind=True,
    )
    session.add(calib)
    await session.commit()

    return RedirectResponse(
        url="/review/calibrate?success=1",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/calibration.jsonl")
async def export_calibration_labels(
    current_user: Annotated[AppUser, Depends(require_role("coach"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> Response:
    """Exports all calibration records as JSON Lines (§9.5)."""
    stmt = select(CalibrationLabel).order_by(CalibrationLabel.created_at.desc())
    labels = (await session.execute(stmt)).scalars().all()

    lines: list[str] = []
    for label in labels:
        record = {
            "id": str(label.id),
            "scene_id": str(label.scene_id) if label.scene_id else None,
            "explain_score_id": str(label.explain_score_id) if label.explain_score_id else None,
            "coach_user_id": str(label.coach_user_id) if label.coach_user_id else None,
            "scores": label.scores,
            "note": label.note,
            "blind": label.blind,
            "created_at": label.created_at.isoformat() if label.created_at else None,
        }
        lines.append(json.dumps(record, ensure_ascii=False))

    content = "\n".join(lines) + ("\n" if lines else "")
    return Response(
        content=content,
        media_type="application/x-ndjson",
        headers={
            "Content-Disposition": 'attachment; filename="calibration.jsonl"',
            "Cache-Control": "no-cache",
        },
    )


# ── Move Review & Approval ───────────────────────────────────────────────


@router.get("/moves/{move_id}", response_class=HTMLResponse)
async def review_move_view(
    request: Request,
    move_id: str,
    current_user: Annotated[AppUser, Depends(require_role("coach"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> Response:
    """Renders move details, rubric, scripts, raw YAML and approval button (§9.5)."""
    csrf_token = generate_csrf_token()

    db_moves = await ensure_moves_in_db(session)
    move = next((m for m in db_moves if m.id == move_id), None)
    if not move:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Move not found")

    cards = [c for c in load_all_move_cards() if c.id == move_id]
    card = cards[0] if cards else None

    # Load raw YAML
    yaml_file = Path(__file__).parents[3] / "content" / "moves" / f"{move_id}.yaml"
    raw_yaml = (
        yaml_file.read_text(encoding="utf-8")
        if yaml_file.is_file()
        else yaml.dump(move.payload, allow_unicode=True)
    )

    approvals = move.approvals if isinstance(move.approvals, list) else []
    distinct_approvers = {
        a.get("user_id", a.get("username")) for a in approvals if isinstance(a, dict)
    }
    user_id_str = str(current_user.id)
    user_already_approved = (
        user_id_str in distinct_approvers or current_user.username in distinct_approvers
    )

    response = templates.TemplateResponse(
        request=request,
        name="review_move.html",
        context={
            "request": request,
            "csrf_token": csrf_token,
            "user": current_user,
            "move": move,
            "card": card,
            "raw_yaml": raw_yaml,
            "approvals": approvals,
            "approvals_count": len(distinct_approvers),
            "approvals_required": settings.MOVE_APPROVALS_REQUIRED,
            "user_already_approved": user_already_approved,
            "approved": request.query_params.get("approved"),
        },
    )
    set_csrf_cookie(response, csrf_token)
    return response


@router.post("/moves/{move_id}/approve")
async def approve_move(
    request: Request,
    move_id: str,
    current_user: Annotated[AppUser, Depends(require_role("coach"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> Response:
    """Records approval for a move. Requires 2 distinct coaches to become approved (§9.5)."""
    await verify_csrf_token(request)

    db_moves = await ensure_moves_in_db(session)
    move = next((m for m in db_moves if m.id == move_id), None)
    if not move:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Move not found")

    approvals = list(move.approvals) if isinstance(move.approvals, list) else []
    distinct_approvers = {
        a.get("user_id", a.get("username")) for a in approvals if isinstance(a, dict)
    }

    user_id_str = str(current_user.id)
    if user_id_str not in distinct_approvers and current_user.username not in distinct_approvers:
        approvals.append(
            {
                "user_id": user_id_str,
                "username": current_user.username,
                "display_name": current_user.display_name or current_user.username,
                "at": datetime.now(UTC).isoformat(),
            }
        )
        move.approvals = approvals

        distinct_approvers = {
            a.get("user_id", a.get("username")) for a in approvals if isinstance(a, dict)
        }
        if len(distinct_approvers) >= settings.MOVE_APPROVALS_REQUIRED:
            move.status = "approved"

        await session.commit()

    return RedirectResponse(
        url=f"/review/moves/{move_id}?approved=1",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/moves/{move_id}/validate-yaml")
async def validate_move_yaml(
    request: Request,
    move_id: str,
    current_user: Annotated[AppUser, Depends(require_role("coach"))],
) -> JSONResponse:
    """Validates raw YAML content against the MoveCard schema (§9.5)."""
    await verify_csrf_token(request)

    try:
        body = await request.json()
        yaml_content = body.get("yaml_content", "")
    except Exception:
        return JSONResponse(
            status_code=400,
            content={"valid": False, "error": "Invalid request body"},
        )

    try:
        parsed = yaml.safe_load(yaml_content)
        if not isinstance(parsed, dict):
            return JSONResponse(
                status_code=200,
                content={"valid": False, "error": "YAML must be a mapping dictionary"},
            )
        card = MoveCard.model_validate(parsed)
        return JSONResponse(
            status_code=200,
            content={
                "valid": True,
                "id": card.id,
                "title_hi": card.title_hi,
                "criteria_count": len(card.rubric.criteria),
            },
        )
    except Exception as exc:
        return JSONResponse(
            status_code=200,
            content={"valid": False, "error": str(exc)},
        )
