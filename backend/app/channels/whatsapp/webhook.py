"""WhatsApp Webhook endpoints and inbound background processor (spec/07 §7.1, §7.2).

Endpoints:
- GET /webhooks/whatsapp & GET /whatsapp/webhook (Meta verification handshake)
- POST /webhooks/whatsapp & POST /whatsapp/webhook (Meta inbound message events)

Inbound Pipeline (§7.1):
1. Signature verification (HMAC-SHA256)
2. Immediate 200 OK return within 2 seconds
3. Deduplication on (channel='whatsapp', channel_msg_id)
4. Teacher lookup or auto-creation (phone_hash + encrypted contact)
5. Background processing under per-teacher asyncio.Lock:
   - Media download & STT for audio notes
   - SessionService.handle_inbound dispatch
   - WhatsAppChannel.send outbound responses
"""

from __future__ import annotations

import logging
import unicodedata
import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from sqlalchemy import select

from backend.app.channels.web import get_teacher_lock
from backend.app.channels.whatsapp.channel import WhatsAppChannel
from backend.app.channels.whatsapp.media import download_whatsapp_media
from backend.app.channels.whatsapp.security import verify_whatsapp_signature
from backend.app.config import settings
from backend.app.core.messages import get_message
from backend.app.core.types import InboundMessage, OutboundMessage
from backend.app.db.models import Message, Teacher, TeacherContact
from backend.app.db.session import async_session_factory
from backend.app.privacy.hashing import (
    encrypt_phone_number,
    hash_phone_number,
    normalize_phone_number,
)
from backend.app.sessions.service import SessionService
from backend.app.speech.audio import AudioProcessingError, to_wav16k
from backend.app.speech.stt import get_stt_provider

logger = logging.getLogger("abhyas.channels.whatsapp.webhook")

router = APIRouter(tags=["WhatsApp"])

# In-memory deduplication set for fast duplicate rejection
_PROCESSED_MESSAGE_IDS: set[str] = set()

# Pluggable session factory hook for tests
_session_factory: Any = None


def get_whatsapp_session_factory() -> Any:
    if _session_factory is not None:
        return _session_factory
    return async_session_factory


def set_whatsapp_session_factory(factory: Any) -> None:
    global _session_factory
    _session_factory = factory


# ── Webhook Verification (GET) ─────────────────────────────────────────────


@router.get("/webhooks/whatsapp")
@router.get("/whatsapp/webhook")
async def verify_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
) -> Response:
    """Meta webhook verification endpoint (§7.2)."""
    if not settings.WHATSAPP_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="WhatsApp channel is disabled",
        )
    if not settings.WHATSAPP_VERIFY_TOKEN:
        logger.warning("WhatsApp verify token is not configured.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Verify token not configured",
        )
    if hub_mode == "subscribe" and hub_verify_token == settings.WHATSAPP_VERIFY_TOKEN:
        logger.info("WhatsApp webhook verified successfully.")
        return Response(content=hub_challenge, media_type="text/plain")

    logger.warning("WhatsApp webhook verification token mismatch.")
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Verification token mismatch")


# ── Webhook Receiver (POST) ────────────────────────────────────────────────


@router.post("/webhooks/whatsapp")
@router.post("/whatsapp/webhook")
async def receive_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_hub_signature_256: str | None = Header(None, alias="X-Hub-Signature-256"),
) -> dict[str, str]:
    """Receives inbound messages, verifies signature, persists, and queues background processing."""
    if not settings.WHATSAPP_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="WhatsApp channel is disabled",
        )

    if not settings.WHATSAPP_APP_SECRET:
        logger.error("WHATSAPP_APP_SECRET is not configured.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="WhatsApp webhook secret not configured",
        )

    body_bytes = await request.body()

    if not x_hub_signature_256 or not verify_whatsapp_signature(body_bytes, x_hub_signature_256):
        logger.error("Invalid WhatsApp webhook HMAC signature.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid signature",
        )

    try:
        payload = await request.json()
    except Exception as exc:
        logger.warning("Malformed JSON in webhook body: %s", exc)
        return {"status": "ignored"}

    entries = payload.get("entry", [])
    for entry in entries:
        changes = entry.get("changes", [])
        for change in changes:
            value = change.get("value", {})
            messages = value.get("messages", [])
            for raw_msg in messages:
                msg_id = raw_msg.get("id")
                from_phone = raw_msg.get("from")
                if not msg_id or not from_phone:
                    continue

                if msg_id in _PROCESSED_MESSAGE_IDS:
                    logger.info("Skipping duplicate message id: %s", msg_id)
                    continue
                _PROCESSED_MESSAGE_IDS.add(msg_id)

                # Queue asynchronous message processing
                background_tasks.add_task(
                    _dispatch_inbound_message,
                    raw_msg=raw_msg,
                )

    # Meta requires immediate 200 response (< 2 seconds)
    return {"status": "ok"}


# ── Inbound Dispatcher and Background Pipeline ─────────────────────────────


async def _dispatch_inbound_message(raw_msg: dict[str, Any]) -> None:
    """Parses message payload, retrieves/creates teacher, and triggers inbound processing."""
    msg_id = raw_msg.get("id", "")
    from_phone = normalize_phone_number(str(raw_msg.get("from", "")))
    msg_type = raw_msg.get("type", "text")

    text_body: str | None = None
    audio_id: str | None = None
    button_id: str | None = None
    kind: Literal["text", "audio", "button"] = "text"

    if msg_type == "text":
        kind = "text"
        text_body = raw_msg.get("text", {}).get("body", "")
    elif msg_type == "audio":
        kind = "audio"
        audio_id = raw_msg.get("audio", {}).get("id")
    elif msg_type == "interactive":
        kind = "button"
        interactive = raw_msg.get("interactive", {})
        button_reply = interactive.get("button_reply", {})
        list_reply = interactive.get("list_reply", {})
        button_id = button_reply.get("id") or list_reply.get("id")
        text_body = button_id
    elif msg_type == "button":
        kind = "button"
        button_id = raw_msg.get("button", {}).get("payload")
        text_body = button_id
    else:
        # Unsupported type (sticker, image, location, etc.)
        kind = "text"
        text_body = None

    now = datetime.now(UTC)
    phone_hash = hash_phone_number(from_phone)

    try:
        factory = get_whatsapp_session_factory()
        async with factory() as session:
            # 1. Deduplication check in DB
            dup_stmt = select(Message).where(
                Message.channel == "whatsapp",
                Message.channel_msg_id == msg_id,
            )
            existing = (await session.execute(dup_stmt)).scalar_one_or_none()
            if existing:
                logger.info("Message %s already recorded in DB; skipping", msg_id)
                return

            # 2. Teacher lookup or auto-creation (§7.2)
            teacher_stmt = select(Teacher).where(Teacher.phone_hash == phone_hash)
            teacher = (await session.execute(teacher_stmt)).scalar_one_or_none()

            if not teacher:
                teacher_id = uuid.uuid4()
                teacher = Teacher(
                    id=teacher_id,
                    phone_hash=phone_hash,
                    preferred_channel="whatsapp",
                    onboarding_state="NEW",
                    last_inbound_at=now,
                    created_at=now,
                )
                session.add(teacher)
                # Store encrypted phone in teacher_contact table
                contact = TeacherContact(
                    teacher_id=teacher_id,
                    phone_enc=encrypt_phone_number(from_phone),
                )
                session.add(contact)
            else:
                teacher.last_inbound_at = now
                # Ensure contact exists
                c_stmt = select(TeacherContact).where(TeacherContact.teacher_id == teacher.id)
                existing_contact = (await session.execute(c_stmt)).scalar_one_or_none()
                if not existing_contact:
                    new_contact = TeacherContact(
                        teacher_id=teacher.id,
                        phone_enc=encrypt_phone_number(from_phone),
                    )
                    session.add(new_contact)

            # 3. Persist inbound Message row
            db_msg_id = uuid.uuid4()
            db_msg = Message(
                id=db_msg_id,
                teacher_id=teacher.id,
                direction="in",
                channel="whatsapp",
                channel_msg_id=msg_id,
                kind=kind,
                text=text_body,
                created_at=now,
            )
            session.add(db_msg)
            await session.commit()
            teacher_id = teacher.id

        # 4. Process under per-teacher serialisation lock (§7.1)
        await process_inbound_whatsapp(
            teacher_id=teacher_id,
            message_id=db_msg_id,
            kind=kind,
            raw_msg_type=msg_type,
            text=text_body,
            audio_id=audio_id,
            button_id=button_id,
        )
    except Exception as exc:
        logger.warning("Error processing inbound WhatsApp message %s: %s", msg_id, exc)


async def process_inbound_whatsapp(
    teacher_id: uuid.UUID,
    message_id: uuid.UUID,
    kind: Literal["text", "audio", "button"],
    raw_msg_type: str = "text",
    text: str | None = None,
    audio_id: str | None = None,
    button_id: str | None = None,
) -> None:
    """Processes inbound WhatsApp message under per-teacher serialisation lock."""
    lock = get_teacher_lock(teacher_id)
    async with lock:
        async with async_session_factory() as session:
            teacher = await session.get(Teacher, teacher_id)
            if not teacher:
                logger.error("Teacher %s not found in process_inbound_whatsapp", teacher_id)
                return

            # Check for unsupported media types (image, sticker, etc.)
            if raw_msg_type not in ("text", "audio", "interactive", "button"):
                unsupported_msg = get_message(
                    "unsupported_type", default="यह संदेश प्रारूप समर्थित नहीं है। कृपया पाठ या आवाज़ में भेजें।"
                )
                outbound = OutboundMessage(
                    kind="text",
                    text_hi=unsupported_msg,
                    speaker="coach",
                )
                channel = WhatsAppChannel()
                await channel.send(teacher, [outbound], session=session)
                return

            final_text = text

            # STT for voice notes
            if kind == "audio" and audio_id:
                try:
                    audio_bytes = await download_whatsapp_media(audio_id)
                    wav_data = audio_bytes
                    try:
                        wav_data = await to_wav16k(audio_bytes)
                    except (AudioProcessingError, OSError, ValueError) as exc:
                        logger.warning("Audio to_wav16k conversion error: %s", exc)

                    stt = get_stt_provider()
                    transcript = await stt.transcribe(wav_data)
                    final_text = unicodedata.normalize("NFC", transcript.text)

                    # Update inbound message with transcript
                    db_msg = await session.get(Message, message_id)
                    if db_msg:
                        db_msg.text = final_text
                        await session.commit()
                except Exception as exc:
                    logger.error("STT transcription failed for audio %s: %s", audio_id, exc)
                    final_text = ""

            elif kind == "button" and button_id:
                final_text = button_id
                db_msg = await session.get(Message, message_id)
                if db_msg and not db_msg.text:
                    db_msg.text = button_id
                    await session.commit()

            # Dispatch to SessionService
            inbound = InboundMessage(
                channel="whatsapp",
                channel_msg_id=str(message_id),
                teacher_id=teacher_id,
                kind=kind,
                text=final_text,
                button_id=button_id,
                received_at=datetime.now(UTC),
            )

            session_service = SessionService(db_session=session)
            outbounds = await session_service.handle_inbound(inbound)

            # Send outbounds via WhatsAppChannel
            if outbounds:
                channel = WhatsAppChannel()
                await channel.send(teacher, outbounds, session=session)
