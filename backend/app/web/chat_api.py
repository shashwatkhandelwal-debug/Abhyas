"""Web channel chat API endpoints (spec/07 §7.3, spec/09 §9.2).

Endpoints:
- POST /api/chat/text     {client_msg_id, text} -> 202 {message_id}
- POST /api/chat/audio    multipart {client_msg_id, file} (<= 2 MB) -> 202 {message_id}
- POST /api/chat/button   {client_msg_id, button_id} -> 202 {message_id}
- GET  /api/chat/messages ?after=<message_id> -> {messages: [...], pending: bool}
- GET  /api/audio/{audio_ref}.{ext} -> cached audio with 1-year private immutable cache
- POST /api/chat/rating   {scene_id, rating} (1-5 realism) -> 200 {ok: true}
- POST /api/settings      {lite_mode: bool} -> 200 {ok: true, lite_mode: bool}
"""

import logging
import re
import unicodedata
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
)
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.csrf import verify_csrf_token
from backend.app.auth.guards import get_current_user
from backend.app.auth.rate_limit import check_chat_rate_limit, check_translate_rate_limit
from backend.app.channels.web import is_teacher_pending, mark_teacher_pending, process_inbound_web
from backend.app.config import settings
from backend.app.core.messages import localize_buttons
from backend.app.db.models import (
    AppUser,
    Message,
    MessageTranslation,
    RealismRating,
    Scene,
    Teacher,
)
from backend.app.db.session import get_db_session
from backend.app.llm.roles.translator import TranslationUnavailable, translate_to_english
from backend.app.rehearsal.header import scene_header
from backend.app.rehearsal.scene_store import scene_store
from backend.app.retrieval.search import get_guide_retriever
from backend.app.speech.cache import tts_cache
from backend.app.web.chat_view import load_chat_view

logger = logging.getLogger("abhyas.web.chat")

TRANSLATION_LANG = "en"

router = APIRouter(prefix="/api", tags=["Web Chat"])

MAX_AUDIO_BYTES = 2 * 1024 * 1024  # 2 MB limit (§7.3)


# ── Pydantic Request Models ──────────────────────────────────────────────────


class ChatTextRequest(BaseModel):
    client_msg_id: str = Field(description="Client-generated UUID for idempotency")
    text: str = Field(min_length=1, max_length=4096)


class ChatButtonRequest(BaseModel):
    client_msg_id: str = Field(description="Client-generated UUID for idempotency")
    button_id: str = Field(min_length=1, max_length=64)


class ChatRatingRequest(BaseModel):
    scene_id: uuid.UUID
    rating: int = Field(ge=1, le=5, description="Realism rating 1 to 5")


class SettingsUpdateRequest(BaseModel):
    lite_mode: bool | None = None


# ── Helper: Resolve Teacher ──────────────────────────────────────────────────


async def get_teacher_for_user(
    user: AppUser,
    db: AsyncSession,
    request: Request | None = None,
    as_teacher_id: str | uuid.UUID | None = None,
) -> Teacher:
    """Finds the Teacher record linked to the authenticated user.

    When current_user is admin:
    - Must specify ?as=<demo_teacher_id> (or as_teacher_id) pointing to an existing Teacher with is_demo=True.
    - If ?as= is missing, returns 400 Bad Request.
    - If ?as= points to a non-demo teacher or invalid ID, returns 400 Bad Request.
    """
    if user.role == "admin":
        target_raw = as_teacher_id
        if target_raw is None and request is not None:
            target_raw = request.query_params.get("as")

        if not target_raw:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Admin must select a demo teacher (?as=<demo_teacher_id>)",
            )

        try:
            target_uuid = (
                target_raw if isinstance(target_raw, uuid.UUID) else uuid.UUID(str(target_raw))
            )
        except (ValueError, TypeError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid teacher ID",
            ) from None

        demo_teacher = await db.get(Teacher, target_uuid)
        if not demo_teacher or not demo_teacher.is_demo:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only demo teachers can be impersonated",
            )
        return demo_teacher

    if user.teacher_id:
        teacher = await db.get(Teacher, user.teacher_id)
        if teacher:
            is_user_demo = getattr(user, "is_demo", False) or getattr(
                user, "is_demo_account", False
            )
            if is_user_demo and not teacher.is_demo:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Demo accounts can only access demo teachers",
                )
            return teacher

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="No linked teacher account",
    )


# ── Routes ───────────────────────────────────────────────────────────────────


@router.post(
    "/chat/text",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(verify_csrf_token)],
)
async def send_chat_text(
    req: ChatTextRequest,
    background_tasks: BackgroundTasks,
    current_user: Annotated[AppUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    request: Request,
) -> dict[str, Any]:
    """Inbound text endpoint with deduplication and async processing (§7.3)."""
    check_chat_rate_limit(str(current_user.id))
    teacher = await get_teacher_for_user(current_user, db, request=request)
    clean_text = unicodedata.normalize("NFC", req.text.strip())
    if not clean_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Message cannot be empty",
        )

    # 1. Deduplication on (channel, channel_msg_id) scoped by teacher_id (§7.1, §7.3)
    stmt = select(Message).where(
        Message.channel == "web",
        Message.channel_msg_id == req.client_msg_id,
    )
    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing:
        if existing.teacher_id == teacher.id:
            return {"message_id": str(existing.id), "status": "duplicate_ignored"}
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Client message ID conflict across teachers",
        )

    # 2. Persist inbound message immediately
    msg_id = uuid.uuid4()
    inbound_msg = Message(
        id=msg_id,
        teacher_id=teacher.id,
        direction="in",
        channel="web",
        channel_msg_id=req.client_msg_id,
        kind="text",
        text=clean_text,
        created_at=datetime.now(UTC),
    )
    db.add(inbound_msg)
    teacher.last_inbound_at = datetime.now(UTC)
    await db.commit()

    # 3. Schedule async processing under teacher lock
    mark_teacher_pending(teacher.id)
    background_tasks.add_task(
        process_inbound_web,
        teacher_id=teacher.id,
        message_id=msg_id,
        kind="text",
        text=clean_text,
    )

    return {"message_id": str(msg_id), "status": "accepted"}


@router.post(
    "/chat/audio",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(verify_csrf_token)],
)
async def send_chat_audio(
    background_tasks: BackgroundTasks,
    current_user: Annotated[AppUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    request: Request,
    client_msg_id: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
) -> dict[str, Any]:
    """Inbound audio upload endpoint (multipart, <= 2 MB) (§7.3)."""
    check_chat_rate_limit(str(current_user.id))
    teacher = await get_teacher_for_user(current_user, db, request=request)

    audio_bytes = await file.read(MAX_AUDIO_BYTES + 1)
    if len(audio_bytes) > MAX_AUDIO_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Audio file exceeds 2 MB limit",
        )
    if len(audio_bytes) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty audio file",
        )

    # Deduplication check scoped by teacher_id
    stmt = select(Message).where(
        Message.channel == "web",
        Message.channel_msg_id == client_msg_id,
    )
    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing:
        if existing.teacher_id == teacher.id:
            return {"message_id": str(existing.id), "status": "duplicate_ignored"}
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Client message ID conflict across teachers",
        )

    # Persist audio message with text null pending STT
    msg_id = uuid.uuid4()
    inbound_msg = Message(
        id=msg_id,
        teacher_id=teacher.id,
        direction="in",
        channel="web",
        channel_msg_id=client_msg_id,
        kind="audio",
        text=None,
        created_at=datetime.now(UTC),
    )
    db.add(inbound_msg)
    teacher.last_inbound_at = datetime.now(UTC)
    await db.commit()

    # Schedule async STT and conversation processing
    mark_teacher_pending(teacher.id)
    background_tasks.add_task(
        process_inbound_web,
        teacher_id=teacher.id,
        message_id=msg_id,
        kind="audio",
        audio_bytes=audio_bytes,
    )

    return {"message_id": str(msg_id), "status": "accepted"}


@router.post(
    "/chat/button",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(verify_csrf_token)],
)
async def send_chat_button(
    req: ChatButtonRequest,
    background_tasks: BackgroundTasks,
    current_user: Annotated[AppUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    request: Request,
) -> dict[str, Any]:
    """Inbound button reply endpoint (§7.3)."""
    check_chat_rate_limit(str(current_user.id))
    teacher = await get_teacher_for_user(current_user, db, request=request)

    # Deduplication check scoped by teacher_id
    stmt = select(Message).where(
        Message.channel == "web",
        Message.channel_msg_id == req.client_msg_id,
    )
    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing:
        if existing.teacher_id == teacher.id:
            return {"message_id": str(existing.id), "status": "duplicate_ignored"}
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Client message ID conflict across teachers",
        )

    msg_id = uuid.uuid4()
    inbound_msg = Message(
        id=msg_id,
        teacher_id=teacher.id,
        direction="in",
        channel="web",
        channel_msg_id=req.client_msg_id,
        kind="button",
        text=req.button_id,
        created_at=datetime.now(UTC),
    )
    db.add(inbound_msg)
    teacher.last_inbound_at = datetime.now(UTC)
    await db.commit()

    mark_teacher_pending(teacher.id)
    background_tasks.add_task(
        process_inbound_web,
        teacher_id=teacher.id,
        message_id=msg_id,
        kind="button",
        button_id=req.button_id,
    )

    return {"message_id": str(msg_id), "status": "accepted"}


@router.get("/chat/messages")
async def get_chat_messages(
    current_user: Annotated[AppUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    request: Request,
    after: str | None = None,
    audio_since: str | None = None,
) -> dict[str, Any]:
    """Polls recent messages, returning pending state and new messages after cursor (§7.3)."""
    server_time = datetime.now(UTC)
    teacher = await get_teacher_for_user(current_user, db, request=request)

    audio_since_dt: datetime | None = None
    if audio_since:
        try:
            audio_since_dt = datetime.fromisoformat(audio_since)
        except ValueError:
            audio_since_dt = None

    if after:
        try:
            after_uuid = uuid.UUID(after)
            after_msg = await db.get(Message, after_uuid)
            if after_msg and after_msg.teacher_id == teacher.id:
                new_msgs_cond = (Message.created_at > after_msg.created_at) | (
                    (Message.created_at == after_msg.created_at) & (Message.id != after_msg.id)
                )
                cutoff_dt = audio_since_dt or after_msg.created_at
                # Re-send rows changed after creation: a reply whose TTS audio just landed, or a
                # voice note whose STT transcript was just filled in (the PWA swaps the text in).
                audio_updated_cond = (
                    (Message.updated_at > Message.created_at)
                    & (Message.updated_at >= cutoff_dt)
                    & (
                        Message.audio_ref.isnot(None)
                        | ((Message.direction == "in") & (Message.kind == "audio"))
                    )
                )
                stmt = (
                    select(Message)
                    .where(
                        Message.teacher_id == teacher.id,
                        new_msgs_cond | audio_updated_cond,
                    )
                    .order_by(Message.created_at.asc(), Message.id.asc())
                )
            else:
                stmt = (
                    select(Message)
                    .where(Message.teacher_id == teacher.id)
                    .order_by(Message.created_at.asc(), Message.id.asc())
                    .limit(50)
                )
        except ValueError:
            stmt = (
                select(Message)
                .where(Message.teacher_id == teacher.id)
                .order_by(Message.created_at.asc(), Message.id.asc())
                .limit(50)
            )
    else:
        stmt = (
            select(Message)
            .where(Message.teacher_id == teacher.id)
            .order_by(Message.created_at.asc(), Message.id.asc())
            .limit(50)
        )

    result = await db.execute(stmt)
    messages = result.scalars().all()

    messages_data = [
        {
            "id": str(m.id),
            # Lets the PWA match its optimistic bubble (keyed by client_msg_id) to this row
            "client_msg_id": (
                m.channel_msg_id if m.channel == "web" and m.direction == "in" else None
            ),
            "direction": m.direction,
            "channel": m.channel,
            "kind": m.kind,
            "text": m.text,
            "audio_ref": m.audio_ref,
            "buttons": localize_buttons(m.buttons, teacher.address_form),
            "citations": m.citations,
            "speaker": m.speaker,
            "template_name": m.template_name,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in messages
    ]

    pending = is_teacher_pending(teacher.id)

    # One-on-one header (child, progress cue, turn counter); null outside a one-on-one scene
    scene_record = await scene_store.get_active_for_teacher(teacher.id)
    header = scene_header(scene_record.scene_state, scene_record.active) if scene_record else None

    view = await load_chat_view(db, teacher, header)
    return {
        "messages": messages_data,
        "pending": pending,
        "scene": header or view.get("scene_preview"),
        "view": view,
        "server_time": server_time.isoformat(),
    }


# Bubbles whose text is generated Hindi (children, coach, model teacher, guide answers). Other bot
# messages are system text already shown in the user's UI language.
TRANSLATABLE_SPEAKERS = frozenset({"ravi", "priya", "aman", "coach", "guide", "model_teacher"})


class TranslateRequest(BaseModel):
    message_id: uuid.UUID


@router.post("/chat/translate", dependencies=[Depends(verify_csrf_token)])
async def translate_message(
    body: TranslateRequest,
    current_user: Annotated[AppUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    request: Request,
) -> dict[str, Any]:
    """English translation of one of the caller's own child/coach/guide bubbles.

    The Hindi text is never changed. Translations are cached per (message, 'en'); a repeat call
    makes no LLM call and does not count against the rate limit.
    """
    teacher = await get_teacher_for_user(current_user, db, request=request)
    msg = await db.get(Message, body.message_id)
    if msg is None or msg.teacher_id != teacher.id:
        raise HTTPException(status_code=404, detail="message_not_found")
    if msg.direction != "out" or not msg.text or msg.speaker not in TRANSLATABLE_SPEAKERS:
        raise HTTPException(status_code=400, detail="not_translatable")
    if len(msg.text) > settings.TRANSLATE_MAX_SOURCE_CHARS:
        raise HTTPException(status_code=400, detail="too_long")

    cached = await db.get(MessageTranslation, (msg.id, TRANSLATION_LANG))
    if cached is not None:
        return {"text": cached.text, "cached": True}

    check_translate_rate_limit(str(current_user.id))
    try:
        text_en = await translate_to_english(msg.text)
    except TranslationUnavailable:
        raise HTTPException(status_code=502, detail="translation_failed") from None

    db.add(MessageTranslation(message_id=msg.id, lang=TRANSLATION_LANG, text=text_en))
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()  # a concurrent request stored it first; both texts are equivalent
    return {"text": text_en, "cached": False}


@router.get("/source/{chunk_id:path}")
async def get_source_excerpt(
    chunk_id: str,
    current_user: Annotated[AppUser, Depends(get_current_user)],
) -> dict[str, Any]:
    """Excerpt behind a citation: the stored source passage and where it sits in the document."""
    chunk = get_guide_retriever().get_chunk(chunk_id)
    if chunk is None:
        raise HTTPException(status_code=404, detail="source_not_found")
    return {
        "chunk_id": chunk["chunk_id"],
        "source_short_hi": chunk.get("source_short_hi") or chunk.get("short_hi", ""),
        "title": chunk.get("title", ""),
        "heading": chunk.get("heading") or chunk.get("section", ""),
        "lang": chunk.get("lang", "hi"),
        "page": chunk.get("pdf_page_start") or chunk.get("page"),
        "page_end": chunk.get("pdf_page_end"),
        "printed_page": chunk.get("printed_page_start"),
        "gloss_hi": chunk.get("gloss_hi", ""),
        "text": chunk.get("text", ""),
        "ocr": bool(chunk.get("ocr", False)),
    }


@router.get("/audio/{audio_ref}.{ext}")
async def get_audio_file(
    audio_ref: str,
    ext: Literal["ogg", "mp3", "wav"],
    current_user: Annotated[AppUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    request: Request,
) -> Response:
    """Returns cached synthetic audio with private immutable cache-control headers (§7.3)."""
    # 1. Ownership check: admin, coach, arp have access; teachers can only access their own audio
    if current_user.role not in ("admin", "coach", "arp"):
        teacher = await get_teacher_for_user(current_user, db, request=request)
        is_owner = False

        stmt_msg = (
            select(Message.id)
            .where(
                Message.teacher_id == teacher.id,
                Message.audio_ref == audio_ref,
            )
            .limit(1)
        )
        if (await db.execute(stmt_msg)).scalar_one_or_none() is not None:
            is_owner = True
        else:
            stmt_scenes = (
                select(Scene.engine_state)
                .where(Scene.teacher_id == teacher.id)
                .order_by(Scene.started_at.desc())
                .limit(10)
            )
            scenes_res = await db.execute(stmt_scenes)
            for (state_dict,) in scenes_res.all():
                if state_dict and audio_ref in str(state_dict):
                    is_owner = True
                    break

        if not is_owner:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Audio file not found",
            )

    audio_bytes = await tts_cache.get(audio_ref, ext)
    if not audio_bytes:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Audio file not found",
        )

    content_types: dict[str, str] = {
        "ogg": "audio/ogg",
        "mp3": "audio/mpeg",
        "wav": "audio/wav",
    }
    media_type = content_types.get(ext, "audio/ogg")
    return Response(
        content=audio_bytes,
        media_type=media_type,
        headers={"Cache-Control": "private, max-age=31536000, immutable"},
    )


@router.post(
    "/chat/rating",
    dependencies=[Depends(verify_csrf_token)],
)
async def post_chat_rating(
    req: ChatRatingRequest,
    current_user: Annotated[AppUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    request: Request,
) -> dict[str, Any]:
    """Records teacher realism rating (1 to 5) for a rehearsal scene (§7.3)."""
    teacher = await get_teacher_for_user(current_user, db, request=request)

    rating_entry = RealismRating(
        id=uuid.uuid4(),
        teacher_id=teacher.id,
        scene_id=req.scene_id,
        rating=req.rating,
        created_at=datetime.now(UTC),
    )
    db.add(rating_entry)
    await db.commit()

    return {"ok": True}


@router.post(
    "/settings",
    dependencies=[Depends(verify_csrf_token)],
)
async def update_settings(
    req: SettingsUpdateRequest,
    current_user: Annotated[AppUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    request: Request,
) -> dict[str, Any]:
    """Updates teacher preferences (e.g. lite mode) (§7.3)."""
    teacher = await get_teacher_for_user(current_user, db, request=request)

    if req.lite_mode is not None:
        teacher.lite_mode = req.lite_mode

    await db.commit()
    return {"ok": True, "lite_mode": teacher.lite_mode}


@router.get("/demo-sample/{sample_id}.{ext}")
async def get_demo_sample_audio(
    sample_id: str,
    ext: Literal["ogg", "wav"],
    current_user: Annotated[AppUser, Depends(get_current_user)],
) -> Response:
    """Returns rendered demo sample audio from eval/samples/audio/ (§9.2)."""
    clean_id = re.sub(r"[^a-zA-Z0-9_-]", "", sample_id)
    candidates = [
        Path("eval/samples/audio") / f"{clean_id}.{ext}",
        Path(__file__).resolve().parents[3] / "eval" / "samples" / "audio" / f"{clean_id}.{ext}",
    ]
    for p in candidates:
        if p.is_file():
            media_type = "audio/wav" if ext == "wav" else "audio/ogg"
            return Response(content=p.read_bytes(), media_type=media_type)

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Sample audio not found",
    )
