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
import unicodedata
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Response,
    UploadFile,
    status,
)
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.guards import get_current_user
from backend.app.channels.web import is_teacher_pending, mark_teacher_pending, process_inbound_web
from backend.app.config import settings
from backend.app.db.models import AppUser, Message, RealismRating, Teacher, TTSCache
from backend.app.db.session import get_db_session
from backend.app.speech.tts import MockTTS, VoiceSpec

logger = logging.getLogger("abhyas.web.chat")

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


async def get_teacher_for_user(user: AppUser, db: AsyncSession) -> Teacher:
    """Finds the Teacher record linked to the authenticated user."""
    if user.teacher_id:
        teacher = await db.get(Teacher, user.teacher_id)
        if teacher:
            return teacher

    if user.role == "admin":
        stmt = select(Teacher).limit(1)
        res = (await db.execute(stmt)).scalar_one_or_none()
        if res:
            return res

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="शिक्षक खाता लिंक नहीं है (No linked teacher account)",
    )


# ── Routes ───────────────────────────────────────────────────────────────────


@router.post("/chat/text", status_code=status.HTTP_202_ACCEPTED)
async def send_chat_text(
    req: ChatTextRequest,
    background_tasks: BackgroundTasks,
    current_user: Annotated[AppUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict[str, Any]:
    """Inbound text endpoint with deduplication and async processing (§7.3)."""
    teacher = await get_teacher_for_user(current_user, db)
    clean_text = unicodedata.normalize("NFC", req.text.strip())
    if not clean_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="संदेश खाली नहीं हो सकता (Message cannot be empty)",
        )

    # 1. Deduplication on (channel, channel_msg_id) (§7.1, §7.3)
    stmt = select(Message).where(
        Message.channel == "web",
        Message.channel_msg_id == req.client_msg_id,
    )
    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing:
        return {"message_id": str(existing.id), "status": "duplicate_ignored"}

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


@router.post("/chat/audio", status_code=status.HTTP_202_ACCEPTED)
async def send_chat_audio(
    background_tasks: BackgroundTasks,
    current_user: Annotated[AppUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    client_msg_id: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
) -> dict[str, Any]:
    """Inbound audio upload endpoint (multipart, <= 2 MB) (§7.3)."""
    teacher = await get_teacher_for_user(current_user, db)

    audio_bytes = await file.read()
    if len(audio_bytes) > MAX_AUDIO_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="ऑडियो फ़ाइल 2 MB से अधिक है (Audio file exceeds 2 MB limit)",
        )
    if len(audio_bytes) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ऑडियो फ़ाइल खाली है (Empty audio file)",
        )

    # Deduplication check
    stmt = select(Message).where(
        Message.channel == "web",
        Message.channel_msg_id == client_msg_id,
    )
    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing:
        return {"message_id": str(existing.id), "status": "duplicate_ignored"}

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


@router.post("/chat/button", status_code=status.HTTP_202_ACCEPTED)
async def send_chat_button(
    req: ChatButtonRequest,
    background_tasks: BackgroundTasks,
    current_user: Annotated[AppUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict[str, Any]:
    """Inbound button reply endpoint (§7.3)."""
    teacher = await get_teacher_for_user(current_user, db)

    # Deduplication check
    stmt = select(Message).where(
        Message.channel == "web",
        Message.channel_msg_id == req.client_msg_id,
    )
    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing:
        return {"message_id": str(existing.id), "status": "duplicate_ignored"}

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
    after: str | None = None,
) -> dict[str, Any]:
    """Polls recent messages, returning pending state and new messages after cursor (§7.3)."""
    teacher = await get_teacher_for_user(current_user, db)

    if after:
        try:
            after_uuid = uuid.UUID(after)
            after_msg = await db.get(Message, after_uuid)
            if after_msg and after_msg.teacher_id == teacher.id:
                stmt = (
                    select(Message)
                    .where(
                        Message.teacher_id == teacher.id,
                        Message.created_at > after_msg.created_at,
                    )
                    .order_by(Message.created_at.asc())
                )
            else:
                stmt = (
                    select(Message)
                    .where(Message.teacher_id == teacher.id)
                    .order_by(Message.created_at.asc())
                    .limit(50)
                )
        except ValueError:
            stmt = (
                select(Message)
                .where(Message.teacher_id == teacher.id)
                .order_by(Message.created_at.asc())
                .limit(50)
            )
    else:
        stmt = (
            select(Message)
            .where(Message.teacher_id == teacher.id)
            .order_by(Message.created_at.asc())
            .limit(50)
        )

    result = await db.execute(stmt)
    messages = result.scalars().all()

    messages_data = [
        {
            "id": str(m.id),
            "direction": m.direction,
            "channel": m.channel,
            "kind": m.kind,
            "text": m.text,
            "audio_ref": m.audio_ref,
            "buttons": m.buttons,
            "speaker": m.speaker,
            "template_name": m.template_name,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in messages
    ]

    pending = is_teacher_pending(teacher.id)

    return {
        "messages": messages_data,
        "pending": pending,
    }


@router.get("/audio/{audio_ref}.{ext}")
async def get_audio_file(
    audio_ref: str,
    ext: Literal["ogg", "mp3", "wav"],
    current_user: Annotated[AppUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> Response:
    """Returns cached synthetic audio with private immutable cache-control headers (§7.3)."""
    stmt = select(TTSCache).where(TTSCache.key == audio_ref)
    result = await db.execute(stmt)
    entry = result.scalar_one_or_none()

    content_types: dict[str, str] = {
        "ogg": "audio/ogg",
        "mp3": "audio/mpeg",
        "wav": "audio/wav",
    }
    media_type = content_types.get(ext, "audio/ogg")

    if entry and entry.bytes:
        return Response(
            content=entry.bytes,
            media_type=entry.mime or media_type,
            headers={"Cache-Control": "private, max-age=31536000, immutable"},
        )

    # In dev/test/mock mode, synthesize fallback WAV audio
    if settings.ENVIRONMENT in ("development", "test"):
        mock_tts = MockTTS()
        data = await mock_tts.synthesize(
            text_hi="अभ्यास",
            voice=VoiceSpec(provider_speaker="mock", model="mock"),
        )
        return Response(
            content=data,
            media_type="audio/wav",
            headers={"Cache-Control": "private, max-age=31536000, immutable"},
        )

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="ऑडियो फ़ाइल नहीं मिली (Audio file not found)",
    )


@router.post("/chat/rating")
async def post_chat_rating(
    req: ChatRatingRequest,
    current_user: Annotated[AppUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict[str, Any]:
    """Records teacher realism rating (1 to 5) for a rehearsal scene (§7.3)."""
    teacher = await get_teacher_for_user(current_user, db)

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


@router.post("/settings")
async def update_settings(
    req: SettingsUpdateRequest,
    current_user: Annotated[AppUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict[str, Any]:
    """Updates teacher preferences (e.g. lite mode) (§7.3)."""
    teacher = await get_teacher_for_user(current_user, db)

    if req.lite_mode is not None:
        teacher.lite_mode = req.lite_mode

    await db.commit()
    return {"ok": True, "lite_mode": teacher.lite_mode}
