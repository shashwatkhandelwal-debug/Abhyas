"""Web channel implementation and inbound processing pipeline (spec/07 §7.1, §7.3).

Provides:
- WebChannel conforming to Channel protocol
- Inbound message processing pipeline with per-teacher asyncio.Lock serialisation
- Pending task state tracker for client polling
- Pluggable ConversationService hook for testing
"""

import asyncio
import logging
import unicodedata
import uuid
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.conversation import ConversationService
from backend.app.core.messages import get_message
from backend.app.core.types import InboundMessage, OutboundMessage
from backend.app.db.models import Message, Teacher
from backend.app.db.session import async_session_factory
from backend.app.rehearsal.stt_hints import scene_child_name_hints
from backend.app.sessions.service import SessionService
from backend.app.speech.audio import AudioProcessingError, to_wav16k
from backend.app.speech.spend import SpeechBudgetExceededError
from backend.app.speech.stt import get_stt_provider

logger = logging.getLogger("abhyas.channels.web")

# ── Per-teacher Locks & Pending Status Tracking (§7.1, §7.3) ───────────────
_teacher_locks: dict[uuid.UUID, asyncio.Lock] = {}
_teacher_pending_count: dict[uuid.UUID, int] = defaultdict(int)
_state_lock = asyncio.Lock()


def get_teacher_lock(teacher_id: uuid.UUID) -> asyncio.Lock:
    """Returns or creates the serialisation lock for a teacher (§7.1)."""
    if teacher_id not in _teacher_locks:
        _teacher_locks[teacher_id] = asyncio.Lock()
    return _teacher_locks[teacher_id]


def is_teacher_pending(teacher_id: uuid.UUID) -> bool:
    """Returns True if a background turn is currently queued/processing for this teacher (§7.3)."""
    return _teacher_pending_count.get(teacher_id, 0) > 0


def mark_teacher_pending(teacher_id: uuid.UUID) -> None:
    """Increments the pending task count for a teacher."""
    _teacher_pending_count[teacher_id] += 1


def unmark_teacher_pending(teacher_id: uuid.UUID) -> None:
    """Decrements the pending task count for a teacher."""
    if _teacher_pending_count.get(teacher_id, 0) > 0:
        _teacher_pending_count[teacher_id] -= 1
        if _teacher_pending_count[teacher_id] == 0:
            _teacher_pending_count.pop(teacher_id, None)


def reset_web_channel_state() -> None:
    """Resets in-memory locks, pending counters, and mock factories (used in tests)."""
    _teacher_locks.clear()
    _teacher_pending_count.clear()
    global _session_factory, _session_service_factory, _conversation_service_factory
    _session_factory = None
    _session_service_factory = None
    _conversation_service_factory = None


# ── Pluggable Session / Session Factory Hooks ──────────────────────────────
_session_factory: Callable[[], Any] | None = None
_session_service_factory: Callable[[AsyncSession], Any] | None = None
_conversation_service_factory: Callable[[], Any] | None = None


def get_channel_session_factory() -> Any:
    """Returns the database session factory (or test override)."""
    if _session_factory is not None:
        return _session_factory
    return async_session_factory


def set_channel_session_factory(factory: Any) -> None:
    """Overrides database session factory for tests."""
    global _session_factory
    _session_factory = factory


def get_session_service(session: AsyncSession) -> Any:
    """Returns active SessionService instance (or test override)."""
    if _session_service_factory is not None:
        return _session_service_factory(session)
    if _conversation_service_factory is not None:
        target = _conversation_service_factory()

        class _Adapter:
            def __init__(self, obj: Any) -> None:
                self.obj = obj

            async def handle_inbound(self, inbound: InboundMessage) -> list[OutboundMessage]:
                if hasattr(self.obj, "handle_inbound"):
                    # Rule C justification: test mock target is untyped dynamic object conforming to duck-typing
                    return await self.obj.handle_inbound(inbound)  # type: ignore[no-any-return]
                # Rule C justification: test mock target is untyped dynamic object conforming to duck-typing
                return await self.obj.handle(inbound)  # type: ignore[no-any-return]

        return _Adapter(target)
    return SessionService(db_session=session)


def set_session_service_factory(factory: Callable[[AsyncSession], Any] | None) -> None:
    """Overrides SessionService factory for tests."""
    global _session_service_factory
    _session_service_factory = factory


def set_conversation_service_factory(factory: Callable[[], Any] | None) -> None:
    """Overrides ConversationService factory for tests (backward compatibility)."""
    global _conversation_service_factory
    _conversation_service_factory = factory


def get_conversation_service() -> Any:
    """Returns active ConversationService instance."""
    if _conversation_service_factory is not None:
        return _conversation_service_factory()
    return ConversationService()


# ── WebChannel Class (§7.3) ──────────────────────────────────────────────────


class WebChannel:
    """Web channel implementation persisting outbound messages for polling clients."""

    name: str = "web"

    async def send(
        self,
        teacher: Teacher,
        msgs: list[OutboundMessage],
        session: AsyncSession | None = None,
    ) -> None:
        """Persists outbound messages to the database for retrieval by the web client."""
        if not msgs:
            return

        async def _persist(s: AsyncSession) -> None:
            # Strictly increasing timestamps keep a multi-message reply in order: the
            # poll orders by (created_at, id) and coarse clocks gave equal created_at.
            base = datetime.now(UTC)
            for position, msg in enumerate(msgs):
                if msg.already_persisted or getattr(msg, "_already_persisted", False):
                    continue
                text = msg.text_hi
                if text and msg.citations:
                    # The web UI shows citations as tappable chips under the bubble
                    for c in msg.citations:
                        text = text.replace(c.line_hi, "")
                    text = text.strip()
                db_msg = Message(
                    id=msg.message_id or uuid.uuid4(),
                    teacher_id=teacher.id,
                    direction="out",
                    channel="web",
                    channel_msg_id=str(uuid.uuid4()),
                    kind=msg.kind,
                    text=unicodedata.normalize("NFC", text) if text else None,
                    audio_ref=msg.audio_ref,
                    buttons=[b.model_dump() for b in msg.buttons] if msg.buttons else None,
                    citations=[c.model_dump() for c in msg.citations] if msg.citations else None,
                    speaker=msg.speaker,
                    template_name=msg.template_name,
                    created_at=base + timedelta(microseconds=position),
                )
                s.add(db_msg)
            await s.commit()

        if session is not None:
            await _persist(session)
        else:
            async with async_session_factory() as new_session:
                await _persist(new_session)

    async def can_send_freeform(self, teacher: Teacher) -> bool:
        """Web channel has no 24-hour window restriction (§7.3)."""
        return True


# ── Background Inbound Pipeline Processor (§7.1, §7.3) ───────────────────────


async def process_inbound_web(
    teacher_id: uuid.UUID,
    message_id: uuid.UUID,
    kind: Literal["text", "audio", "button"],
    text: str | None = None,
    audio_bytes: bytes | None = None,
    button_id: str | None = None,
) -> None:
    """Asynchronously processes inbound web message under per-teacher serialisation lock.

    Pipeline:
    1. Acquire teacher lock
    2. STT if audio
    3. Update inbound Message row with transcript
    4. Call ConversationService.handle()
    5. Dispatch outbounds via WebChannel.send()
    6. Release lock and update pending indicator
    """
    try:
        lock = get_teacher_lock(teacher_id)
        async with lock:
            factory = get_channel_session_factory()
            async with factory() as session:
                teacher = await session.get(Teacher, teacher_id)
                if not teacher:
                    logger.error("Teacher %s not found for inbound processing", teacher_id)
                    return

                final_text = text

                # Step 2: STT if audio
                if kind == "audio" and audio_bytes:
                    address_form = teacher.address_form or "f"
                    wav_data = audio_bytes
                    try:
                        wav_data = await to_wav16k(audio_bytes)
                    except (AudioProcessingError, OSError, ValueError) as exc:
                        logger.warning(
                            "Audio conversion to_wav16k failed: %s; falling back to raw bytes", exc
                        )
                    failure_key: str | None = None
                    transcript_text = ""
                    try:
                        stt = get_stt_provider()
                        transcript = await stt.transcribe(
                            wav_data, keyterms=await scene_child_name_hints(teacher_id)
                        )
                        transcript_text = unicodedata.normalize("NFC", transcript.text).strip()
                        if not transcript_text:
                            failure_key = "stt_failed"
                    except SpeechBudgetExceededError:
                        failure_key = "stt_budget_type_please"
                    except Exception as exc:  # provider down, timeout, bad audio...
                        logger.warning("STT failed for web voice note %s: %s", message_id, exc)
                        failure_key = "stt_failed"
                    db_msg = await session.get(Message, message_id)
                    if failure_key is not None:
                        # Never leave the chat silent: resolve the "transcribing…" bubble and
                        # tell the teacher in Hindi to speak again or type.
                        logger.info(
                            "web_stt_failed reason=%s message_id=%s", failure_key, message_id
                        )
                        if db_msg:
                            db_msg.text = get_message("stt_unclear_label", address_form)
                            db_msg.updated_at = datetime.now(UTC)
                            await session.commit()
                        retry = OutboundMessage(
                            kind="text", text_hi=get_message(failure_key, address_form)
                        )
                        await WebChannel().send(teacher, [retry], session=session)
                        return
                    final_text = transcript_text
                    if db_msg:
                        db_msg.text = final_text
                        # Bump updated_at so /api/chat/messages re-sends the row and the PWA
                        # can swap the "transcribing…" placeholder for the transcript.
                        db_msg.updated_at = datetime.now(UTC)
                        await session.commit()

                # Step 3: Button payload handling
                elif kind == "button" and button_id:
                    final_text = button_id
                    db_msg = await session.get(Message, message_id)
                    if db_msg and not db_msg.text:
                        db_msg.text = button_id
                        await session.commit()

                # Step 4: Dispatch to SessionService
                inbound = InboundMessage(
                    channel="web",
                    channel_msg_id=str(message_id),
                    teacher_id=teacher_id,
                    kind=kind,
                    text=final_text,
                    button_id=button_id,
                    received_at=datetime.now(UTC),
                )

                session_service = get_session_service(session)
                outbounds = await session_service.handle_inbound(inbound)

                # Step 5: Send outbounds via WebChannel
                if outbounds:
                    web_channel = WebChannel()
                    await web_channel.send(teacher, outbounds, session=session)

    except Exception:
        logger.exception(
            "Error in process_inbound_web for teacher %s msg %s", teacher_id, message_id
        )
        await _send_failure_reply(teacher_id)
    finally:
        unmark_teacher_pending(teacher_id)


async def _send_failure_reply(teacher_id: uuid.UUID) -> None:
    """Tells the teacher something went wrong instead of leaving the chat silent.

    Uses a fresh session: the pipeline's session may be in a failed transaction.
    """
    try:
        factory = get_channel_session_factory()
        async with factory() as session:
            teacher = await session.get(Teacher, teacher_id)
            if teacher is None:
                return
            reply = OutboundMessage(
                kind="text",
                text_hi=get_message("system_error_retry", teacher.address_form or "f"),
            )
            await WebChannel().send(teacher, [reply], session=session)
    except Exception:
        logger.exception("Could not send failure reply to teacher %s", teacher_id)
